# type: ignore
import enum
import json
from functools import partial
from random import choice

import discord
from discord import DiscordException, ui
from discord.ext import commands

from utils import Bot, CallbackButton, CustomLogger, Settings, SettingsEnum

from .repository import Join2CreateRepository


class ButtonEnum(enum.Enum):
    SET_USER_LIMIT = enum.auto()
    CLAIM_OWNERSHIP = enum.auto()
    BAN_ROLE = enum.auto()
    UNBAN_ROLE = enum.auto()
    BAN_USER = enum.auto()
    UNBAN_USER = enum.auto()
    CHANGE_BITRATE = enum.auto()
    RESET_PERMISSIONS = enum.auto()


async def create_overwrite_from_select(
    *, channel: discord.VoiceChannel, overwrite_items: list[discord.Role | discord.Member], banning: bool, bot: Bot
) -> dict[discord.Member | discord.Role, discord.PermissionOverwrite]:
    permission_overwrites = channel.overwrites
    derived_overwrites = {}
    if not banning:
        join2create_repo = Join2CreateRepository(bot.db.session_maker)
        current_join2create = await join2create_repo.get(channel)
        if current_join2create is not None:
            derived_channel: discord.VoiceChannel | None = await bot.get_or_fetch(
                discord.VoiceChannel, current_join2create.derived_channel
            )
            if derived_channel is not None:
                derived_overwrites = derived_channel.overwrites

    for o_item in overwrite_items:
        if banning:
            permission_overwrites[o_item] = discord.PermissionOverwrite.from_pair(
                allow=discord.Permissions.none(),
                deny=discord.Permissions.all(),
            )
        elif o_item in derived_overwrites:
            permission_overwrites[o_item] = derived_overwrites[o_item]
        else:
            permission_overwrites.pop(o_item, None)
    return permission_overwrites


def _apply_j2c_permissions(
    overwrites: dict[discord.Role | discord.Member | discord.Object, discord.PermissionOverwrite],
    target: discord.Role | discord.Member | discord.User | discord.Object,
) -> None:
    existing_target = next((t for t in overwrites if getattr(t, "id", None) == target.id), None)
    if existing_target is not None:
        existing_ow = overwrites[existing_target]
        ow = discord.PermissionOverwrite.from_pair(*existing_ow.pair())
        key = existing_target
    else:
        ow = discord.PermissionOverwrite()
        key = target
    ow.update(view_channel=True, connect=True, move_members=True)
    overwrites[key] = ow


async def _get_team_role(bot: Bot, guild: discord.Guild) -> discord.Role | None:
    team_role_setting = await bot.db.get_setting(setting=SettingsEnum.TeamRole, guild=guild)
    if not isinstance(team_role_setting, Settings):
        return None
    team_role = guild.get_role(team_role_setting.value)
    if team_role is None and hasattr(guild, "get_or_fetch"):
        team_role = await guild.get_or_fetch(discord.Role, team_role_setting.value, default=None)
    return team_role


async def build_join2create_overwrites(
    *,
    derived_overwrites: dict[discord.Role | discord.Member, discord.PermissionOverwrite],
    guild: discord.Guild | None,
    owner: discord.Member | discord.User | discord.Object | None,
    bot: Bot,
) -> dict[discord.Role | discord.Member | discord.Object, discord.PermissionOverwrite]:
    overwrites = dict(derived_overwrites)

    if guild is not None:
        team_role = await _get_team_role(bot, guild)
        if team_role is not None:
            _apply_j2c_permissions(overwrites, team_role)

    if owner is not None:
        _apply_j2c_permissions(overwrites, owner)

    return overwrites


async def _next_button_func(interaction: discord.Interaction, next_function: ButtonEnum):
    """
    Gate function that validates the user can use the button before sending a modal.

    This function handles common validation checks (interaction context, guild context, voice channel)
    and then dispatches to the appropriate modal based on the next_function parameter.

    Args:
        interaction (discord.Interaction): The interaction that triggered the callback.
        next_function (ButtonEnum): The type of modal to display. Options: ``ButtonEnum.SET_USER_LIMIT``, ``ButtonEnum.CHANGE_BITRATE``, etc.

    Raises:
        DiscordException: If validation fails (no interaction, not in guild, or not in voice channel).
    """
    # Validate interaction exists
    if interaction is None or interaction.user is None:
        raise DiscordException("Interaction triggered without interaction context.")

    # Validate user is in a guild (not a DM)
    elif isinstance(interaction.user, discord.User):
        raise DiscordException("Interaction triggered out of guild context.")

    # Validate user is in a voice channel
    elif interaction.user.voice:
        channel = interaction.user.voice.channel

        if channel != interaction.channel:
            await interaction.respond("You must be in the same channel to change its settings.", ephemeral=True)
            return

        client: Bot = interaction.client
        join2create_repo = Join2CreateRepository(client.db.session_maker)
        temp_voice = await join2create_repo.get(channel)
        if temp_voice is None:
            await interaction.respond("This channel is not a temporary voice channel.", ephemeral=True)
            return

        if next_function != ButtonEnum.CLAIM_OWNERSHIP and interaction.user.id != temp_voice.owner_id:
            await interaction.respond(
                f"You are not the owner of this channel <@{temp_voice.owner_id}> is the owner!",
                ephemeral=True,
                allowed_mentions=None,
            )
            return

        # Dispatch to appropriate modal based on next_function parameter
        match next_function:
            case ButtonEnum.SET_USER_LIMIT:
                await interaction.response.send_modal(SetUserLimit())
            case ButtonEnum.CLAIM_OWNERSHIP:
                await transfer_ownership(interaction, channel, temp_voice)
            case ButtonEnum.BAN_ROLE:
                await interaction.response.send_modal(BanRole())
            case ButtonEnum.UNBAN_ROLE:
                await interaction.response.send_modal(UnbanRole())
            case ButtonEnum.BAN_USER:
                await interaction.response.send_modal(BanUser())
            case ButtonEnum.UNBAN_USER:
                await interaction.response.send_modal(UnbanUser())
            case ButtonEnum.CHANGE_BITRATE:
                await interaction.response.send_modal(ChangeBitRate(int(interaction.guild.bitrate_limit / 1000)))
            case ButtonEnum.RESET_PERMISSIONS:
                await reset_permission(interaction, channel, temp_voice)
            case _:
                raise DiscordException(f"Unknown modal function: {next_function}")

    else:
        await interaction.respond("You must be in the voice channel to change its settings.", ephemeral=True)


class SetUserLimit(ui.DesignerModal):
    def __init__(self):
        super().__init__(title="Set user limit")
        self.add_item(
            ui.Label("Set member limit").set_input_text(placeholder="0-99"),
        )

    async def callback(self, interaction: discord.Interaction):
        label: ui.Label = self.children[0]
        component: ui.InputText = label.item
        try:
            if component.value is not None:
                new_limit = int(component.value)
                if new_limit < 0 or new_limit > 99:
                    raise ValueError
                if new_limit == 0:
                    new_limit = None

                channel: discord.VoiceChannel = interaction.channel

                await channel.edit(
                    user_limit=new_limit,
                    reason=f"[J2C] {interaction.user.global_name} changed user limit to {new_limit or 'no limit'}.",
                )
                await interaction.respond(f"Changed user limit to {new_limit or 'no limit'}.", ephemeral=True)
            else:
                raise ValueError
        except ValueError:
            await interaction.respond("Please enter a valid number between 0-99 (0 is unlimited).", ephemeral=True)


def _get_target_overwrite(
    channel: discord.VoiceChannel,
    target: discord.Member | discord.User | discord.Role | discord.Object,
) -> discord.PermissionOverwrite:
    if hasattr(channel, "overwrites_for"):
        ow = channel.overwrites_for(target)
        if isinstance(ow, discord.PermissionOverwrite):
            return discord.PermissionOverwrite.from_pair(*ow.pair())
    existing = next((t for t in getattr(channel, "overwrites", {}) if getattr(t, "id", None) == target.id), None)
    if existing is not None:
        return discord.PermissionOverwrite.from_pair(*channel.overwrites[existing].pair())
    return discord.PermissionOverwrite()


async def _cleanup_previous_owner_permissions(
    *,
    channel: discord.VoiceChannel,
    previous_owner_id: int,
    derived_channel_id: int,
    bot: Bot,
) -> None:
    prev_target = (channel.guild.get_member(previous_owner_id) if channel.guild else None) or discord.Object(
        id=previous_owner_id
    )

    derived_channel = await bot.get_or_fetch(discord.VoiceChannel, derived_channel_id)
    derived_overwrites = getattr(derived_channel, "overwrites", {}) if derived_channel else {}

    has_derived_ow = any(getattr(t, "id", None) == previous_owner_id for t in derived_overwrites)
    if has_derived_ow and hasattr(derived_channel, "overwrites_for"):
        ow = derived_channel.overwrites_for(prev_target)
        new_ow = (
            discord.PermissionOverwrite.from_pair(*ow.pair()) if isinstance(ow, discord.PermissionOverwrite) else None
        )
    elif has_derived_ow:
        prev_ow = next(
            (ow for t, ow in derived_overwrites.items() if getattr(t, "id", None) == previous_owner_id),
            None,
        )
        new_ow = discord.PermissionOverwrite.from_pair(*prev_ow.pair()) if prev_ow is not None else None
    else:
        new_ow = None

    try:
        await channel.set_permissions(prev_target, overwrite=new_ow)
    except (discord.Forbidden, discord.HTTPException):
        pass


async def transfer_ownership(interaction: discord.Interaction, channel: discord.VoiceChannel, temp_voice):
    """
    Transfers ownership of the temporary voice channel to the interaction user.

    Args:
        interaction (discord.Interaction): The interaction that triggered the callback.
        channel (discord.VoiceChannel): The voice channel to transfer ownership of.
        temp_voice (Join2Create): The database entry for the temporary voice channel.
    """
    if interaction.user.id == temp_voice.owner_id:
        await interaction.respond("You are already the owner of this channel.", ephemeral=True)
        return

    if temp_voice.owner_id in [m.id for m in channel.members]:
        await interaction.respond("The owner of this channel is still in the channel.", ephemeral=True)
        return

    client: Bot = interaction.client
    join2create_repo = Join2CreateRepository(client.db.session_maker)
    # Transfer ownership in the database
    await join2create_repo.update(channel, interaction.user)

    owner_ow = _get_target_overwrite(channel, interaction.user)
    owner_ow.update(view_channel=True, connect=True, move_members=True)
    try:
        await channel.set_permissions(interaction.user, overwrite=owner_ow)
    except (discord.Forbidden, discord.HTTPException):
        pass

    await _cleanup_previous_owner_permissions(
        channel=channel,
        previous_owner_id=temp_voice.owner_id,
        derived_channel_id=temp_voice.derived_channel,
        bot=client,
    )

    if interaction.message:
        await interaction.message.edit(view=VoiceBoard(client=client, voice_owner=interaction.user))
    await interaction.respond(f"You are now the owner of {channel.name}.", ephemeral=True)


class BanRole(ui.DesignerModal):
    def __init__(self):
        super().__init__(title="Ban Role")
        self.add_item(
            ui.Label(
                "Select roles to ban",
                ui.Select(
                    select_type=discord.ComponentType.role_select, placeholder="Select a role to ban", max_values=10
                ),
            )
        )

    async def callback(self, interaction: discord.Interaction):
        label: ui.Label = self.children[0]
        select: ui.Select = label.item
        selected_roles: list[discord.Role] = select.values
        if not selected_roles:
            return  # this case can't happen since the field is required to be filled

        team_role_setting = await interaction.client.db.get_setting(
            setting=SettingsEnum.TeamRole, guild=interaction.guild
        )
        if isinstance(team_role_setting, Settings):
            selected_roles = [role for role in selected_roles if role.id != team_role_setting.value]
            if not selected_roles:
                await interaction.respond("The team role cannot be banned.", ephemeral=True)
                return

        channel: discord.VoiceChannel = interaction.channel
        await channel.edit(
            overwrites=await create_overwrite_from_select(
                channel=channel,
                overwrite_items=selected_roles,
                banning=True,
                bot=interaction.client,
            )
        )
        await interaction.respond(
            f"Banned {'\n'.join([role.mention for role in selected_roles])} from {channel.mention}.", ephemeral=True
        )


class UnbanRole(ui.DesignerModal):
    def __init__(self):
        super().__init__(title="Unban Role")
        self.add_item(
            ui.Label(
                "Select roles to unban",
                ui.Select(
                    select_type=discord.ComponentType.role_select, placeholder="Select a role to unban", max_values=10
                ),
            )
        )

    async def callback(self, interaction: discord.Interaction):
        label: ui.Label = self.children[0]
        select: ui.Select = label.item
        selected_roles: list[discord.Role] = select.values
        if not selected_roles:
            return  # this case can't happen since the field is required to be filled
        channel: discord.VoiceChannel = interaction.channel
        await channel.edit(
            overwrites=await create_overwrite_from_select(
                channel=channel,
                overwrite_items=selected_roles,
                banning=False,
                bot=interaction.client,
            )
        )
        await interaction.respond(
            f"Unbanned {'\n'.join([role.mention for role in selected_roles])} from {channel.mention}.", ephemeral=True
        )


def _is_team_member(
    user: discord.Member | discord.User,
    guild: discord.Guild | None,
    team_role_id: int | None,
) -> bool:
    if team_role_id is None:
        return False
    member = user if isinstance(user, discord.Member) else (guild.get_member(user.id) if guild else None)
    if member is None:
        return False
    return any(getattr(r, "id", None) == team_role_id for r in getattr(member, "roles", []))


class BanUser(ui.DesignerModal):
    def __init__(self):
        super().__init__(title="Ban User")
        self.add_item(
            ui.Label(
                "Select user to ban",
                ui.Select(
                    select_type=discord.ComponentType.user_select, placeholder="Select a user to ban", max_values=10
                ),
            )
        )

    async def callback(self, interaction: discord.Interaction):
        label: ui.Label = self.children[0]
        select: ui.Select = label.item
        selected_users: list[discord.Member] = select.values
        if not selected_users:
            return  # this case can't happen since the field is required to be filled

        team_role_setting = await interaction.client.db.get_setting(
            setting=SettingsEnum.TeamRole, guild=interaction.guild
        )
        team_role_id = team_role_setting.value if isinstance(team_role_setting, Settings) else None

        selected_users = [
            u
            for u in selected_users
            if u.id not in (interaction.user.id, interaction.client.user.id)
            and not _is_team_member(u, interaction.guild, team_role_id)
        ]
        if not selected_users:
            await interaction.respond("You cannot ban yourself, the bot, or team members.", ephemeral=True)
            return
        channel: discord.VoiceChannel = interaction.channel
        await channel.edit(
            overwrites=await create_overwrite_from_select(
                channel=channel,
                overwrite_items=selected_users,
                banning=True,
                bot=interaction.client,
            )
        )
        for user in selected_users:
            if user in channel.members:
                try:
                    await user.move_to(None, reason=f"Banned from {channel.name} by {interaction.user}")
                except (discord.Forbidden, discord.HTTPException):
                    pass
        await interaction.respond(
            f"Banned {'\n'.join([u.mention for u in selected_users])} from {channel.mention}.",
            ephemeral=True,
            allowed_mentions=None,
        )


class UnbanUser(ui.DesignerModal):
    def __init__(self):
        super().__init__(title="Unban User")
        self.add_item(
            ui.Label(
                "Select user to unban",
                ui.Select(
                    select_type=discord.ComponentType.user_select, placeholder="Select a user to unban", max_values=10
                ),
            )
        )

    async def callback(self, interaction: discord.Interaction):
        label: ui.Label = self.children[0]
        select: ui.Select = label.item
        selected_user: list[discord.Member] = select.values
        if not selected_user:
            return  # this case can't happen since the field is required to be filled
        channel: discord.VoiceChannel = interaction.channel
        await channel.edit(
            overwrites=await create_overwrite_from_select(
                channel=channel,
                overwrite_items=selected_user,
                banning=False,
                bot=interaction.client,
            )
        )
        await interaction.respond(
            f"Unbanned {'\n'.join([u.mention for u in selected_user])} from {channel.mention}.",
            ephemeral=True,
            allowed_mentions=None,
        )


class ChangeBitRate(ui.DesignerModal):
    def __init__(self, max_bitrate_kbps: int):
        super().__init__(title="Change Bitrate")
        self.add_item(
            ui.Label("Set the bitrate in KB/s").set_input_text(
                placeholder=f"Minimum: 8; Maximum: {max_bitrate_kbps} KB/s",
            )
        )
        self.bit_multiplicator = 10**3

    async def callback(self, interaction: discord.Interaction):
        label: ui.Label = self.children[0]
        component: ui.InputText = label.item
        try:
            if component.value is not None:
                new_limit = int(component.value)
                if not (
                    8 * self.bit_multiplicator <= new_limit * self.bit_multiplicator <= interaction.guild.bitrate_limit
                ):
                    raise ValueError

                await interaction.channel.edit(bitrate=new_limit * self.bit_multiplicator)
                await interaction.respond(f"Changed bitrate to `{new_limit}`KB/s!", ephemeral=True)

        except ValueError:
            await interaction.respond(
                f"Please only enter values between 8 and {int(interaction.guild.bitrate_limit / self.bit_multiplicator)}",
                ephemeral=True,
            )


async def reset_permission(interaction: discord.Interaction, channel: discord.VoiceChannel, current_join2create):
    bot: Bot = interaction.client
    derived_channel: discord.VoiceChannel | None = await bot.get_or_fetch(
        discord.VoiceChannel, current_join2create.derived_channel
    )
    if derived_channel is None:
        return await interaction.respond(
            "Couldn't find original join2create channel. Couldn't reset permissions!", ephemeral=True
        )

    owner = channel.guild.get_member(current_join2create.owner_id) if channel.guild else None
    if owner is None and interaction.user.id == current_join2create.owner_id:
        owner = interaction.user
    if owner is None and channel.guild and hasattr(channel.guild, "get_or_fetch"):
        owner = await channel.guild.get_or_fetch(discord.Member, current_join2create.owner_id, default=None)
    if owner is None:
        owner = discord.Object(id=current_join2create.owner_id)

    overwrites = await build_join2create_overwrites(
        derived_overwrites=derived_channel.overwrites,
        guild=channel.guild,
        owner=owner,
        bot=bot,
    )
    await channel.edit(overwrites=overwrites)
    await interaction.respond(f"Reset permissions to the permissions of {derived_channel.mention}", ephemeral=True)


class VoiceBoard(ui.DesignerView):
    """
    Interactive view for voice channel owners to manage their temporary voice channel settings.

    Uses CallbackButtons with functools.partial to pass custom arguments (next_function) to the
    _send_modal gate function. This allows a single validation gate to dispatch to different
    modals based on which button was pressed.

    Example:
        Each button is created with partial(_send_modal, next_function="action_name") so when
        clicked, _send_modal receives both the interaction and the action_name parameter.
    """

    def __init__(self, client: Bot, voice_owner: discord.Member | None = None):
        super().__init__(timeout=None)
        self.logger = CustomLogger("Join2Create/VoiceBoard", client.boot_time)
        self.voice_owner = voice_owner

        container = ui.Container(color=client.user.color if client.user else discord.Color.blue())
        if self.voice_owner and self.voice_owner.display_avatar and self.voice_owner.display_avatar.url:
            container.add_section(
                ui.TextDisplay(
                    f"## Voice Board\nHere can {self.voice_owner.display_name} change settings for this channel."
                ),
                accessory=ui.Thumbnail(self.voice_owner.display_avatar.url),
            )
        elif self.voice_owner:
            container.add_text(f"## Voice Board\nHere can {self.voice_owner.mention} change settings for this channel.")
        else:
            container.add_text("## Voice Board\nHere can the owner change settings for this channel.")

        # User Limit Button: Uses partial to pass "set_user_limit" as next_function parameter
        # When clicked, _send_modal will validate the user, then dispatch to SetUserLimit modal
        limit = CallbackButton(
            label="Set User Limit",
            style=discord.ButtonStyle.blurple,
            emoji=":1234:",
            custom_id="j2c__user_limit_button",
            callback=partial(_next_button_func, next_function=ButtonEnum.SET_USER_LIMIT),
        )
        owner = CallbackButton(
            label="Claim Ownership",
            style=discord.ButtonStyle.blurple,
            emoji=":crown:",
            custom_id="j2c__claim_ownership_button",
            callback=partial(_next_button_func, next_function=ButtonEnum.CLAIM_OWNERSHIP),
        )
        container.add_row(limit, owner)

        r_ban = CallbackButton(
            label="Ban role",
            style=discord.ButtonStyle.blurple,
            emoji=":no_entry_sign:",
            custom_id="j2c__role_ban_button",
            callback=partial(_next_button_func, next_function=ButtonEnum.BAN_ROLE),
        )
        r_unban = CallbackButton(
            label="Unban role",
            style=discord.ButtonStyle.blurple,
            emoji=":ticket:",
            custom_id="j2c__role_unban_button",
            callback=partial(_next_button_func, next_function=ButtonEnum.UNBAN_ROLE),
        )
        container.add_row(r_ban, r_unban)

        u_ban = CallbackButton(
            label="Ban user",
            style=discord.ButtonStyle.blurple,
            emoji=":hammer:",
            custom_id="j2c__ban_button",
            callback=partial(_next_button_func, next_function=ButtonEnum.BAN_USER),
        )
        u_unban = CallbackButton(
            label="Unban user",
            style=discord.ButtonStyle.blurple,
            emoji=":love_letter:",
            custom_id="j2c__unban_button",
            callback=partial(_next_button_func, next_function=ButtonEnum.UNBAN_USER),
        )
        container.add_row(u_ban, u_unban)

        bitrate = CallbackButton(
            label="Change Bitrate",
            style=discord.ButtonStyle.blurple,
            emoji=":space_invader:",
            custom_id="j2c__bitrate_button",
            callback=partial(_next_button_func, next_function=ButtonEnum.CHANGE_BITRATE),
        )
        reset = CallbackButton(
            label="Reset permissions",
            style=discord.ButtonStyle.blurple,
            emoji=":arrows_counterclockwise:",
            custom_id="j2c__reset_permission_button",
            callback=partial(_next_button_func, next_function=ButtonEnum.RESET_PERMISSIONS),
        )
        container.add_row(bitrate, reset)
        self.add_item(container)


class Join2Create(commands.Cog):
    def __init__(self, client):
        self.client: Bot = client
        self.logger = CustomLogger(self.qualified_name, self.client.boot_time)
        self.join2create_repo = Join2CreateRepository(self.client.db.session_maker)
        with open("assets/suffix.json") as f:
            self.status = json.load(f)
            self.suffixes = [*self.status]

    async def _handle_join(self, member: discord.Member, trigger_channel: discord.VoiceChannel):
        join2create_setting = await self.client.db.get_setting(
            setting=SettingsEnum.Join2CreateChannel, guild=member.guild
        )
        if not isinstance(join2create_setting, Settings) or trigger_channel.id != join2create_setting.value:
            return

        channel_name = choice(self.suffixes)
        member_name = member.display_name
        if member_name[-1].lower() != "s" and self.status[channel_name]["s_flag"]:
            member_name += "s"

        overwrites = await build_join2create_overwrites(
            derived_overwrites=trigger_channel.overwrites,
            guild=member.guild,
            owner=member,
            bot=self.client,
        )

        try:
            channel = await trigger_channel.category.create_voice_channel(
                name=f"{member_name}{channel_name}",
                user_limit=25,
                reason="Join2Create",
                overwrites=overwrites,
            )
        except (discord.Forbidden, discord.HTTPException, discord.InvalidArgument) as e:
            self.logger.error(e)
            return

        if self.status[channel_name]["status"]:
            status = choice(self.status[channel_name]["status"])
            await channel.set_status(status=status, reason="Join2Create")

        check = await self.join2create_repo.create(channel, member, derived_channel=trigger_channel)
        if not check:
            await channel.delete(reason="Join2Create-Failed")
            self.logger.error("Database entry for temp voice channel could not be created")
            return
        self.logger.debug(f"{member.name} created {channel.name} in {member.guild}")
        try:
            await member.move_to(channel)
        except (discord.Forbidden, discord.HTTPException) as e:
            self.logger.error(f"Couldn't move member | {e}")
            return
        await channel.send(view=VoiceBoard(client=self.client, voice_owner=member))

    async def _handle_leave(self, member: discord.Member, channel: discord.VoiceChannel):
        if await self.join2create_repo.get(channel):
            if len([m for m in channel.members if not m.bot]) == 0:
                await self.join2create_repo.delete(channel)
                self.logger.debug(f"{channel.name} was deleted on {member.guild}")
                await channel.delete(reason="Join2Delete")

    @commands.Cog.listener("on_voice_state_update")
    async def on_join2create(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        """
        Checks if a person joins a dedicated voice channel. If so creates a new voice channel and moves the person to it
        Creates a new database entry for the new voice channel and deletes it if everyone left it.

        Args:
            member (discord.Member): member who updated his voice state
            before (discord.VoiceState): members voice state before
            after (discord.VoiceState): members voice state after
        """
        if before.channel == after.channel:
            return
        if after.channel is not None:
            await self._handle_join(member, after.channel)
        if before.channel is not None:
            await self._handle_leave(member, before.channel)

    @commands.Cog.listener("on_ready", once=True)
    async def on_ready(self):
        self.client.add_view(VoiceBoard(client=self.client))
        self.logger.info("Added persistent view for VoiceBoard")


def setup(client: Bot):
    client.add_cog(Join2Create(client))

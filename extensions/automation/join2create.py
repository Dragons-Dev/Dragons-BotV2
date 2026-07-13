# type: ignore
import enum
import json
import typing
from functools import partial
from random import choice

import discord
from discord import DiscordException, Interaction, ui
from discord.ext import commands

from utils import Bot, CallbackButton, CustomLogger, Settings, SettingsEnum


class ButtonEnum(enum.Enum):
    SET_USER_LIMIT = enum.auto()
    CLAIM_OWNERSHIP = enum.auto()
    BAN_ROLE = enum.auto()
    UNBAN_ROLE = enum.auto()
    BAN_USER = enum.auto()
    UNBAN_USER = enum.auto()
    CHANGE_BITRATE = enum.auto()
    RESET_PERMISSIONS = enum.auto()


async def _send_modal(interaction: discord.Interaction = None, next_function: ButtonEnum = None):
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

        if interaction.user.voice.channel != interaction.channel:
            await interaction.respond("You must be in the same channel to change its settings.", ephemeral=True)
            return

        # Dispatch to appropriate modal based on next_function parameter
        match next_function:
            case ButtonEnum.SET_USER_LIMIT:
                await interaction.response.send_modal(SetUserLimit(client=interaction.client, channel=channel))
            case ButtonEnum.CLAIM_OWNERSHIP:
                await transfer_ownership(interaction, channel)
            case ButtonEnum.BAN_ROLE:
                await interaction.response.send_modal(BanRole(client=interaction.client, channel=channel))
            case ButtonEnum.UNBAN_ROLE:
                ...
            case ButtonEnum.BAN_USER:
                ...
            case ButtonEnum.UNBAN_USER:
                ...
            case ButtonEnum.CHANGE_BITRATE:
                ...
            case ButtonEnum.RESET_PERMISSIONS:
                ...
            case _:
                raise DiscordException(f"Unknown modal function: {next_function}")

    else:
        raise DiscordException("Interaction without context.")


class SetUserLimit(ui.DesignerModal):
    def __init__(self, client: Bot, channel: discord.VoiceChannel):
        super().__init__(title="Set user limit")
        self.client = client
        self.channel = channel
        self.add_item(
            ui.Label("Set member limit").set_input_text(placeholder="0-99"),
        )

    async def callback(self, interaction: Interaction):
        label: ui.Label = self.children[0]
        component: ui.InputText = label.item
        client: Bot = interaction.client
        try:
            if component.value is not None:
                new_limit = int(component.value)
                if new_limit < 0 or new_limit > 99:
                    raise ValueError
                if new_limit == 0:
                    new_limit = None

                channel: discord.VoiceChannel = interaction.channel
                await client.db.get_temp_voice(channel)

                await channel.edit(
                    user_limit=new_limit,
                    reason=f"[J2C] {interaction.user.global_name} changed user limit to {new_limit or 'no limit'}.",
                )
                await interaction.respond(f"Changed user limit to {new_limit or 'no limit'}.", ephemeral=True)
            else:
                raise ValueError
        except ValueError:
            await interaction.respond("Please enter a valid number between 0-99 (0 is unlimited).", ephemeral=True)


async def transfer_ownership(interaction: Interaction, channel: discord.VoiceChannel):
    """
    Transfers ownership of the temporary voice channel to the interaction user.

    Args:
        interaction (discord.Interaction): The interaction that triggered the callback.
        channel (discord.VoiceChannel): The voice channel to transfer ownership of.

    Raises:
        DiscordException: If the user is not in the voice channel or if the channel is not a temporary voice channel.
    """
    client: Bot = interaction.client
    temp_voice = await client.db.get_temp_voice(channel)
    if temp_voice is None:
        await interaction.respond("This channel is not a temporary voice channel.", ephemeral=True)
        return

    if interaction.user not in channel.members:
        await interaction.respond("You must be in the voice channel to claim ownership.", ephemeral=True)
        return

    if not [m.id == temp_voice.owner_id for m in channel.members]:
        # Transfer ownership in the database
        await client.db.update_temp_voice(channel, interaction.user)

        await interaction.respond(f"You are now the owner of {channel.name}.", ephemeral=True)


class BanRole(ui.DesignerModal):
    def __init__(self, client: Bot, channel: discord.VoiceChannel):
        super().__init__(title="Ban Role")
        self.client = client
        self.channel = channel
        self.add_item(
            ui.Label(
                "Select roles to ban",
                ui.Select(
                    select_type=discord.ComponentType.role_select, placeholder="Select a role to ban", max_values=10
                ),
            )
        )

    async def callback(self, interaction: Interaction):
        label: ui.Label = self.children[0]
        select: ui.Select = label.item
        selected_roles: list[discord.Role] | None = select.values if select.values else None
        if not selected_roles:
            return  # await interaction.response.defer(invisible=True, ephemeral=True)
        permission_overwrites = {}
        channel: discord.VoiceChannel = interaction.channel
        for selected_role in selected_roles:
            permission_overwrites[selected_role] = discord.PermissionOverwrite.from_pair(
                allow=discord.Permissions.none(), deny=discord.Permissions.all()
            )
        print(permission_overwrites)
        await channel.edit(overwrites=permission_overwrites)
        await interaction.respond(
            f"Banned {'\n'.join([role.mention for role in selected_roles])} from {channel.mention}.", ephemeral=True
        )


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

    def __init__(self, client: Bot, voice_owner: discord.Member):
        super().__init__(timeout=None)
        self.logger = CustomLogger("Join2Create/VoiceBoard", client.boot_time)
        self.voice_owner = voice_owner

        container = ui.Container(color=client.user.color)
        if self.voice_owner.display_avatar and self.voice_owner.display_avatar.url:
            container.add_section(
                ui.TextDisplay(
                    f"## Voice Board\nHere can {self.voice_owner.display_name} change settings for this channel."
                ),
                accessory=ui.Thumbnail(self.voice_owner.display_avatar.url),
            )
        else:
            container.add_text(f"## Voice Board\nHere can {self.voice_owner.mention} change settings for this channel.")

        # User Limit Button: Uses partial to pass "set_user_limit" as next_function parameter
        # When clicked, _send_modal will validate the user, then dispatch to SetUserLimit modal
        limit = CallbackButton(
            label="Set User Limit",
            style=discord.ButtonStyle.blurple,
            emoji=":1234:",
            callback=partial(_send_modal, next_function=ButtonEnum.SET_USER_LIMIT),
        )
        owner = CallbackButton(
            label="Claim Ownership",
            style=discord.ButtonStyle.blurple,
            emoji=":crown:",
            callback=partial(_send_modal, next_function=ButtonEnum.CLAIM_OWNERSHIP),
        )
        container.add_row(limit, owner)

        r_ban = CallbackButton(
            label="Ban role",
            style=discord.ButtonStyle.blurple,
            emoji=":no_entry_sign:",
            callback=partial(_send_modal, next_function=ButtonEnum.BAN_ROLE),
        )
        r_unban = CallbackButton(
            label="Unban role",
            style=discord.ButtonStyle.blurple,
            emoji=":ticket:",
            callback=partial(_send_modal, next_function=ButtonEnum.UNBAN_ROLE),
        )
        container.add_row(r_ban, r_unban)

        u_ban = CallbackButton(
            label="Ban user",
            style=discord.ButtonStyle.blurple,
            emoji=":hammer:",
            callback=partial(_send_modal, next_function=ButtonEnum.BAN_USER),
        )
        u_unban = CallbackButton(
            label="Unban user",
            style=discord.ButtonStyle.blurple,
            emoji=":love_letter:",
            callback=partial(_send_modal, next_function=ButtonEnum.UNBAN_USER),
        )
        container.add_row(u_ban, u_unban)

        bitrate = CallbackButton(
            label="Change Bitrate",
            style=discord.ButtonStyle.blurple,
            emoji=":space_invader:",
            callback=partial(_send_modal, next_function=ButtonEnum.CHANGE_BITRATE),
        )
        reset = CallbackButton(
            label="Reset permissions",
            style=discord.ButtonStyle.blurple,
            emoji=":arrows_counterclockwise:",
            callback=partial(_send_modal, next_function=ButtonEnum.RESET_PERMISSIONS),
        )
        container.add_row(bitrate, reset)
        self.add_item(container)


class Join2Create(commands.Cog):
    def __init__(self, client):
        self.client: Bot = client
        self.logger = CustomLogger(self.qualified_name, self.client.boot_time)
        with open("assets/suffix.json") as f:
            self.status = json.load(f)
            self.suffixes = [*self.status]

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
            join2create_setting = await self.client.db.get_setting(
                setting=SettingsEnum.Join2CreateChannel, guild=member.guild
            )
            if join2create_setting is None:
                return
            if type(join2create_setting) is not Settings:
                return
            if after.channel.id == join2create_setting.value:
                verified_role = await self.client.db.get_setting(setting=SettingsEnum.VerifiedRole, guild=member.guild)
                if verified_role is None:
                    role = member.guild.default_role
                elif type(verified_role) is not Settings:
                    role = member.guild.default_role  # I don't like you mypy this overhead is only for you!
                else:
                    role = member.guild.get_role(verified_role.value)
                perms = {
                    role: discord.PermissionOverwrite(
                        stream=True,
                        connect=True,
                        speak=True,
                        use_voice_activation=True,
                        read_message_history=True,
                        read_messages=True,
                        send_messages=True,
                    ),
                    member: discord.PermissionOverwrite(
                        move_members=True, view_channel=True, use_external_apps=True, connect=True, send_messages=True
                    ),
                    self.client.user: discord.PermissionOverwrite(
                        move_members=True, manage_channels=True, view_channel=True
                    ),
                }
                if member.guild.premium_subscriber_role:
                    perms[member.guild.premium_subscriber_role] = discord.PermissionOverwrite(move_members=True)
                if member.guild.default_role != role:
                    perms[member.guild.default_role] = discord.PermissionOverwrite(view_channel=False)
                else:
                    perms[member.guild.default_role] = discord.PermissionOverwrite(view_channel=True)
                channel_name = choice(self.suffixes)
                member_name = member.display_name
                if member_name[-1].lower() != "s":
                    if self.status[channel_name]["s_flag"]:
                        member_name += "s"

                try:
                    channel = await after.channel.category.create_voice_channel(
                        name=f"{member_name}{channel_name}",
                        user_limit=25,
                        reason="Join2Create",
                        overwrites=perms,
                    )
                except (discord.Forbidden, discord.HTTPException, discord.InvalidArgument) as e:
                    self.logger.error(e)
                    return

                if self.status[channel_name]:
                    status = choice(self.status[channel_name]["status"])
                    await channel.set_status(status=status, reason="Join2Create")

                check = await self.client.db.create_temp_voice(channel, member)
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
                # Here was the voice board created before
                # TODO: Reimplement VoiceBoard

        if before.channel is not None:
            if await self.client.db.get_temp_voice(before.channel):
                if len([m for m in before.channel.members if not m.bot]) == 0:
                    await self.client.db.delete_temp_voice(before.channel)
                    self.logger.debug(f"{before.channel.name} was deleted on {member.guild}")
                    await before.channel.delete(reason="Join2Delete")

    @commands.Cog.listener("on_ready", once=True)
    async def on_ready(self):
        return
        self.client.add_view(VoiceBoard())
        self.logger.info("Added persistent view for VoiceBoard")


def setup(client: Bot):
    client.add_cog(Join2Create(client))

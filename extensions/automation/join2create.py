import json
from random import choice

import discord
from discord import ui
from discord.ext import commands

import utils
from utils import Bot, CustomLogger, Settings, SettingsEnum


class InputModal(ui.Modal):
    def __init__(self, title: str, channel_ctx: discord.VoiceChannel, interaction: discord.Interaction):
        self.title = title
        self.channel = channel_ctx or interaction.user.voice.channel
        if self.title == "Set User Limit":
            items = [
                ui.InputText(
                    label="User Limit", placeholder="0-99 is allowed, 0 means unlimited!", min_length=1, max_length=2
                )
            ]
        elif self.title == "Reset permissions":
            items = [ui.TextDisplay(content="Resets all set permissions for this channel")]
        elif self.title == "Unban roles":
            channel_overwrites = self.channel.overwrites
            options = []
            for overwrite_key in [*channel_overwrites.keys()]:
                if isinstance(overwrite_key, discord.Role):
                    permission = channel_overwrites[overwrite_key]
                    if not permission.view_channel and permission.view_channel is not None:
                        options.append(discord.SelectOption(label=overwrite_key.name, value=str(overwrite_key.id)))
            options.sort(key=lambda option: option.label.lower())
            if len(options) == 0:
                items = [ui.TextDisplay(content="No role has been banned")]
            elif 100 >= len(options):
                items = [
                    ui.TextDisplay(
                        content="This will unban a role from this channel.\nUnbanning does show the channel to them."
                    )
                ]
                required_selects = len(options) // 25 + (1 if len(options) % 25 != 0 else 0)
                parts = [options[i * 25 : (i + 1) * 25] for i in range(required_selects)]
                for i in range(required_selects):
                    items.append(
                        ui.Select(
                            label="Role to unban from this channel",
                            placeholder="Select role to unban",
                            options=parts[i],
                            select_type=discord.ComponentType.string_select,
                            min_values=1,
                            max_values=len(parts[i]),
                            required=False,
                        )
                    )
            else:
                items = [ui.TextDisplay(content="Too many roles have been banned, please unban them manually")]
        elif self.title == "Ban roles":
            items = [
                ui.TextDisplay(
                    content="This will ban a role from this channel.\n"
                    "Banning the role hides the channel from user with the role."
                ),
                ui.Select(
                    label="User to ban from this channel",
                    placeholder="Select a user to ban",
                    select_type=discord.ComponentType.role_select,
                    min_values=1,
                    max_values=25,
                ),
            ]
        elif self.title == "Unban a user":
            channel_overwrites = self.channel.overwrites
            options = []
            for overwrite_key in [*channel_overwrites.keys()]:
                if not isinstance(overwrite_key, discord.Role):
                    permission = channel_overwrites[overwrite_key]
                    if not permission.view_channel and permission.view_channel is not None:
                        options.append(discord.SelectOption(label=overwrite_key.name, value=str(overwrite_key.id)))
            options.sort(key=lambda option: option.label.lower())
            if len(options) == 0:
                items = [ui.TextDisplay(content="No user has been banned")]
            elif 100 >= len(options):
                items = [
                    ui.TextDisplay(
                        content="This will unban a user from this channel.\n"
                        "Unbanning them does show the channel to them."
                    )
                ]
                required_selects = len(options) // 25 + (1 if len(options) % 25 != 0 else 0)
                parts = [options[i * 25 : (i + 1) * 25] for i in range(required_selects)]
                for i in range(required_selects):
                    items.append(
                        ui.Select(
                            label="User to unban from this channel",
                            placeholder="Select user to unban",
                            options=parts[i],
                            select_type=discord.ComponentType.string_select,
                            min_values=1,
                            max_values=len(parts[i]),
                            required=False,
                        )
                    )
            else:
                items = [ui.TextDisplay(content="Too many user have been banned, please unban them manually")]
        elif self.title == "Ban a user":
            items = [
                ui.TextDisplay(
                    content="This will ban a user from this channel.\n"
                    "Banning them does hide the channel from them, and kicks them if they are in it."
                ),
                ui.Select(
                    label="User to ban from this channel",
                    placeholder="Select a user to ban",
                    select_type=discord.ComponentType.user_select,
                    min_values=1,
                    max_values=25,
                ),
            ]
        elif self.title == "Change bitrate":
            voice_quality_options = [
                discord.SelectOption(label="8 kbps", value="8000"),
                discord.SelectOption(label="16 kbps", value="16000"),
                discord.SelectOption(label="32 kbps", value="32000"),
                discord.SelectOption(label="64 kbps (Discords Default)", value="64000"),
                discord.SelectOption(label="96 kbps", value="96000"),
            ]
            if self.channel.guild.bitrate_limit >= 128000:
                voice_quality_options.append(discord.SelectOption(label="128 kbps", value="128000"))
            if self.channel.guild.bitrate_limit >= 256000:
                voice_quality_options.append(discord.SelectOption(label="256 kbps", value="256000"))
            if self.channel.guild.bitrate_limit >= 384000:
                voice_quality_options.append(discord.SelectOption(label="384 kbps", value="384000"))
            items = [
                ui.Select(
                    label="Bitrate",
                    placeholder="Select a bitrate",
                    options=voice_quality_options,
                    min_values=1,
                    max_values=1,
                ),
                ui.TextDisplay(
                    f"The higher the bitrate the better the quality but also the higher the data usage.\n"
                    f"It's currently set to `{self.channel.bitrate // 1000}` kbps"
                ),
            ]
        else:
            items = [ui.TextDisplay("The Bot ran into an error, please contact the developer!")]

        super().__init__(*items, title=self.title, timeout=300)

    async def callback(self, interaction: discord.Interaction):
        client: utils.Bot = interaction.client  # type: ignore # mypy is dumb
        voice_channel = await client.db.get_temp_voice(interaction.user.voice.channel)
        if voice_channel is None:
            await interaction.respond("This is not a join2create channel", ephemeral=True)
        else:
            if interaction.user.id == voice_channel.owner_id:
                if self.title == "Set User Limit":
                    user_limit = int(self.children[0].value[0])
                    if user_limit < 0 or user_limit > 99:
                        await interaction.respond("User limit must be between 0 and 99", ephemeral=True)
                        return
                    await interaction.user.voice.channel.edit(
                        user_limit=user_limit, reason=f"Changed by {interaction.user.display_name} via VoiceBoard"
                    )
                    await interaction.respond(
                        f"User Limit changed to {user_limit} by {interaction.user.display_name}", ephemeral=True
                    )

                elif self.title == "Reset permissions":
                    channel_obj: discord.VoiceChannel | None = await discord.utils.get_or_fetch(
                        client, "channel", voice_channel.channel, default=None
                    )  # get the full j2c object
                    if channel_obj is None:
                        await interaction.respond("This channel does not exist anymore", ephemeral=True)
                        return

                    new_overwrite = {}
                    channel_overwrites = channel_obj.overwrites  # gather all permissions
                    for overwrite_key in [*channel_overwrites.keys()]:
                        overwrite = self.channel.overwrites_for(overwrite_key)
                        overwrite.view_channel = None
                        overwrite.connect = None  # reset view and connect permissions
                        new_overwrite[overwrite_key] = overwrite
                    await self.channel.edit(overwrites=new_overwrite)
                    await interaction.respond(
                        "Permissions resetted to default.",
                        ephemeral=True,
                    )

                elif self.title == "Unban roles":
                    try:
                        unban_select = []
                        for component in range(1, len(self.children)):
                            if isinstance(self.children[component], ui.Select):
                                for value in [*self.children[component].values]:
                                    unban_select.append(value)
                    except IndexError:
                        return
                    channel_obj: discord.VoiceChannel | None = await discord.utils.get_or_fetch(
                        client, "channel", voice_channel.channel, default=None
                    )  # get the full j2c object
                    if channel_obj is None:
                        await interaction.respond("This channel does not exist anymore", ephemeral=True)
                        return
                    if len(unban_select) == 0:
                        return await interaction.respond("No roles selected", ephemeral=True)
                    unban_role_list = []
                    new_overwrite = self.channel.overwrites  # get all permissions
                    for option in unban_select:
                        unban_role = interaction.guild.get_role(int(option))
                        unban_role_list.append(unban_role)
                        overwrite = channel_obj.overwrites_for(unban_role)
                        overwrite.view_channel = None
                        overwrite.connect = None
                        new_overwrite[unban_role] = overwrite  # reset their permissions to the default
                    await self.channel.edit(overwrites=new_overwrite)  # set the new permissions

                    await interaction.respond(
                        f"Unbanned {', '.join([f'`{r.name}`' for r in unban_role_list if r.id != interaction.user.id])} from this channel",
                        ephemeral=True,
                    )

                elif self.title == "Ban roles":
                    try:
                        roles = self.children[1].values
                    except IndexError:
                        return
                    channel_obj: discord.VoiceChannel | None = await discord.utils.get_or_fetch(
                        client, "channel", voice_channel.channel, default=None
                    )  # get the full j2c object
                    if channel_obj is None:
                        await interaction.respond("This channel does not exist anymore", ephemeral=True)
                        return
                    new_overwrite = self.channel.overwrites
                    for role in roles:  # iterate through all selected roles
                        overwrite = channel_obj.overwrites_for(role)
                        overwrite.view_channel = False
                        overwrite.connect = False
                        new_overwrite[role] = overwrite
                    await self.channel.edit(overwrites=new_overwrite)  # set the new permissions

                    await interaction.respond(
                        f"Banned {', '.join([f'`{r.name}`' for r in roles if r.id != interaction.user.id])} from this channel",
                        ephemeral=True,
                    )

                elif self.title == "Unban a user":
                    try:
                        unban_select = []
                        for component in range(1, len(self.children)):
                            if isinstance(self.children[component], ui.Select):
                                for value in [*self.children[component].values]:
                                    unban_select.append(value)
                    except IndexError:
                        return
                    channel_obj: discord.VoiceChannel | None = await discord.utils.get_or_fetch(
                        client, "channel", voice_channel.channel, default=None
                    )  # get the full j2c object
                    if channel_obj is None:
                        await interaction.respond("This channel does not exist anymore", ephemeral=True)
                        return
                    if len(unban_select) == 0:
                        return await interaction.respond("No user selected", ephemeral=True)
                    new_overwrite = self.channel.overwrites  # get all permissions
                    unban_user_list = []
                    for option in unban_select:  # iterate through all selected users
                        unban_user = await client.get_or_fetch_user(int(option))
                        unban_user_list.append(unban_user)
                        overwrite = channel_obj.overwrites_for(unban_user)
                        overwrite.view_channel = None
                        overwrite.connect = None  # reset their permissions to the default
                        new_overwrite[unban_user] = overwrite
                    await self.channel.edit(overwrites=new_overwrite)  # set the new permissions

                    await interaction.respond(
                        f"Unbanned {', '.join([f'`{m.name}`' for m in unban_user_list])} from this channel",
                        ephemeral=True,
                    )

                elif self.title == "Ban a user":
                    try:
                        users = self.children[1].values
                    except IndexError:
                        return
                    channel_obj: discord.VoiceChannel | None = await discord.utils.get_or_fetch(
                        client, "channel", voice_channel.channel, default=None
                    )
                    if channel_obj is None:
                        await interaction.respond("This channel does not exist anymore", ephemeral=True)
                        return
                    new_overwrite = self.channel.overwrites
                    for user in users:
                        if user.id == interaction.user.id:  # prevent the user banning himself
                            continue
                        if user.id == client.user.id:  # prevent ourselves getting banned
                            continue
                        overwrite = channel_obj.overwrites_for(user)
                        overwrite.view_channel = False
                        overwrite.connect = False
                        new_overwrite[user] = overwrite
                        if user in channel_obj.members:
                            try:
                                await user.move_to(None, reason=f"Banned from {channel_obj.name} by {interaction.user}")
                            except (discord.Forbidden, discord.HTTPException):
                                pass
                    await self.channel.edit(overwrites=new_overwrite)
                    await interaction.respond(
                        f"Banned {', '.join([f'`{m.display_name}`' for m in users if m.id != interaction.user.id or m.id != client.user.id])} from this channel",
                        ephemeral=True,
                    )

                elif self.title == "Change bitrate":
                    try:
                        bitrate = int(self.children[0].values[0])
                        if bitrate < 8000 or bitrate > interaction.user.voice.channel.guild.bitrate_limit:
                            await interaction.respond(
                                f"Bitrate must be between 8 and {interaction.user.voice.channel.guild.bitrate_limit} kbps",
                                ephemeral=True,
                            )
                            return
                        await interaction.user.voice.channel.edit(
                            bitrate=bitrate, reason=f"Changed by {interaction.user.display_name} via VoiceBoard"
                        )
                        await interaction.respond(f"Changed bitrate to {bitrate // 1000} kbps", ephemeral=True)
                    except ValueError:
                        await interaction.respond("Invalid bitrate", ephemeral=True)
            else:
                await interaction.respond(
                    f"You are not the owner of this channel <@{voice_channel.owner_id}> is the owner!", ephemeral=True
                )


class VoiceBoard(ui.View):
    def __init__(self, channel: discord.VoiceChannel = None):
        super().__init__(timeout=None)
        self.channel = channel

        self.button_names = {
            "j2c__user_limit_button": "Set User Limit",
            "j2c__claim_ownership_button": "Claim Ownership",
            "j2c__reset_permission_button": "Reset permissions",
            "j2c__role_unban_button": "Unban roles",
            "j2c__role_ban_button": "Ban roles",
            "j2c__unban_button": "Unban a user",
            "j2c__ban_button": "Ban a user",
            "j2c__bitrate_button": "Change bitrate",
        }

        buttons = [
            discord.ui.Button(
                label="Set User Limit",
                emoji="🔢",
                style=discord.ButtonStyle.primary,
                custom_id="j2c__user_limit_button",
                row=0,
            ),
            discord.ui.Button(
                label="Claim Ownership",
                emoji="👑",
                style=discord.ButtonStyle.primary,
                custom_id="j2c__claim_ownership_button",
                row=0,
            ),
            discord.ui.Button(
                label="Reset Permission",
                emoji="🔄",
                style=discord.ButtonStyle.primary,
                custom_id="j2c__reset_permission_button",
                row=1,
            ),
            discord.ui.Button(
                label="Unban Roles",
                emoji="🎫",
                style=discord.ButtonStyle.primary,
                custom_id="j2c__role_unban_button",
                row=1,
            ),
            discord.ui.Button(
                label="Ban Roles",
                emoji="🚫",
                style=discord.ButtonStyle.primary,
                custom_id="j2c__role_ban_button",
                row=2,
            ),
            discord.ui.Button(
                label="Unban a user",
                emoji="💌",
                style=discord.ButtonStyle.primary,
                custom_id="j2c__unban_button",
                row=2,
            ),
            discord.ui.Button(
                label="Ban a user",
                emoji="🔨",
                style=discord.ButtonStyle.primary,
                custom_id="j2c__ban_button",
                row=3,
            ),
            discord.ui.Button(
                label="Change Bitrate",
                emoji="👾",
                style=discord.ButtonStyle.primary,
                custom_id="j2c__bitrate_button",
                row=3,
            ),
        ]

        for button in buttons:
            button.callback = self.set_callback
            self.add_item(button)


    async def set_callback(self, interaction: discord.Interaction):
        if interaction.custom_id == "j2c__claim_ownership_button":
            await self._claim_channel(interaction)
        else:
            await self._send_modal(interaction)

    async def _claim_channel(self, interaction: discord.Interaction):
        client: utils.Bot = interaction.client  # type: ignore # mypy is dumb
        voice_channel = await client.db.get_temp_voice(interaction.user.voice.channel)
        if voice_channel is None:
            await interaction.respond("This is not a join2create channel", ephemeral=True)
        else:
            if voice_channel.owner_id == interaction.user.id:
                await interaction.response.send_message("You are already the owner of this channel", ephemeral=True)
                return
            if voice_channel.owner_id in [member.id for member in interaction.user.voice.channel.members]:
                await interaction.response.send_message(
                    "The owner is still in the channel, you cannot claim it!", ephemeral=True
                )
                return
            voice_channel.owner_id = interaction.user.id
            await client.db.update_temp_voice(
                interaction.guild.get_channel(voice_channel.channel),
                interaction.user,
                voice_channel.locked,
                voice_channel.ghosted,
            )
            await interaction.response.send_message(f"Channel ownership transferred to {interaction.user.mention}!")
            return

    async def _send_modal(self, interaction: discord.Interaction):
        if interaction.custom_id in self.button_names.keys():
            await interaction.response.send_modal(
                InputModal(
                    f"{self.button_names[interaction.custom_id]}", channel_ctx=self.channel, interaction=interaction
                )
            )
        else:
            await interaction.respond("This button is not yet keyed to an interaction.", ephemeral=True)


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
                try:
                    await channel.send(view=VoiceBoard(channel=channel))
                except (discord.Forbidden, discord.HTTPException) as e:
                    self.logger.error(f"Couldn't create VoiceBoard{e}")
                    return

        if before.channel is not None:
            if await self.client.db.get_temp_voice(before.channel):
                if len([m for m in before.channel.members if not m.bot]) == 0:
                    await self.client.db.delete_temp_voice(before.channel)
                    self.logger.debug(f"{before.channel.name} was deleted on {member.guild}")
                    await before.channel.delete(reason="Join2Delete")

    @commands.slash_command(name="join2create_debug", description="Debug info for join2create")
    async def join2create_debug(self, ctx: discord.ApplicationContext):
        await ctx.respond(
            view=VoiceBoard(channel=ctx.author.voice.channel if ctx.author.voice else ctx.channel), ephemeral=True
        )

    @commands.Cog.listener("on_ready", once=True)
    async def on_ready(self):
        self.client.add_view(VoiceBoard())
        self.logger.info("Added persistent view for VoiceBoard")


def setup(client: Bot):
    client.add_cog(Join2Create(client))

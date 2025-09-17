import json
from random import choice

import discord
from discord import ui
from discord.ext import commands

import utils
from utils import Bot, CustomLogger, Settings, SettingsEnum


class InputModal(ui.Modal):
    def __init__(self, title: str, channel_ctx: discord.VoiceChannel):
        self.title = title  # .split("-")[1].strip()
        print(self.title)
        self.channel = channel_ctx
        if self.title == "Set User Limit":
            items = [
                ui.InputText(
                    label="User Limit", placeholder="0-99 is allowed, 0 means unlimited!", min_length=1, max_length=2
                )
            ]
        elif self.title == "Reset permissions":
            items = [ui.TextDisplay(content="This feature is not implemented yet")]
        elif self.title == "Blacklist roles":
            items = [ui.TextDisplay(content="This feature is not implemented yet")]
        elif self.title == "Whitelist roles":
            items = [ui.TextDisplay(content="This feature is not implemented yet")]
        elif self.title == "Invite a user":
            items = [ui.TextDisplay(content="This feature is not implemented yet")]
        elif self.title == "Ban a user":
            items = [ui.TextDisplay(content="This feature is not implemented yet")]
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
                elif self.title == "Reset permissions":
                    ...
                elif self.title == "Blacklist roles":
                    ...
                elif self.title == "Whitelist roles":
                    ...
                elif self.title == "Invite a user":
                    ...
                elif self.title == "Ban a user":
                    ...
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
            "j2c__blacklist_button": "Blacklist roles",
            "j2c__whitelist_button": "Whitelist roles",
            "j2c__invite_button": "Invite a user",
            "j2c__ban_button": "Ban a user",
            "j2c__bitrate_button": "Change bitrate",
        }

        container = ui.Container(color=discord.Color.blue(), id=100)

        user_limit_button = discord.ui.Button(
            style=discord.ButtonStyle.primary,
            label="Set User Limit",
            emoji="🔢",
            custom_id="j2c__user_limit_button",
            id=101,
        )
        claim_ownership_button = discord.ui.Button(
            style=discord.ButtonStyle.primary,
            label="Claim Ownership",
            emoji="👑",
            custom_id="j2c__claim_ownership_button",
            id=102,
        )
        blacklist_button = discord.ui.Button(
            style=discord.ButtonStyle.primary,
            label="Blacklist Roles",
            emoji="🚫",
            custom_id="j2c__blacklist_button",
            id=103,
        )
        whitelist_button = discord.ui.Button(
            style=discord.ButtonStyle.primary,
            label="Whitelist Roles",
            emoji="🎫",
            custom_id="j2c__whitelist_button",
            id=104,
        )
        invite_button = discord.ui.Button(
            style=discord.ButtonStyle.primary, label="Invite a user", emoji="💌", custom_id="j2c__invite_button", id=105
        )
        ban_button = discord.ui.Button(
            style=discord.ButtonStyle.primary, label="Ban a user", emoji="🔨", custom_id="j2c__ban_button", id=106
        )
        bitrate_button = discord.ui.Button(
            style=discord.ButtonStyle.primary,
            label="Change Bitrate",
            emoji="👾",
            custom_id="j2c__bitrate_button",
            id=107,
        )
        buttons = [
            user_limit_button,
            claim_ownership_button,
            blacklist_button,
            whitelist_button,
            invite_button,
            ban_button,
            bitrate_button,
        ]
        for button in buttons:
            button.callback = self.set_callback
            container.add_item(button)
            container.add_item(ui.Separator(divider=False))
        self.add_item(container)

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
                InputModal(f"{self.button_names[interaction.custom_id]}", self.channel)
            )
        else:
            await interaction.respond("Not Workie", ephemeral=True)


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
                    member: discord.PermissionOverwrite(move_members=True),
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
                    if channel_name not in ["says 'YIPPIE'", ".exe", "has ADHD", "is broke", "went insane"]:
                        member_name += "s"

                try:
                    channel = await after.channel.category.create_voice_channel(
                        name=f"{member_name} {channel_name}",
                        user_limit=25,
                        reason="Join2Create",
                        overwrites=perms,
                    )
                except (discord.Forbidden, discord.HTTPException, discord.InvalidArgument) as e:
                    self.logger.error(e)
                    return

                if self.status[channel_name]:
                    status = choice(self.status[channel_name])
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
                    await channel.send(view=VoiceBoard())
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


def setup(client):
    client.add_cog(Join2Create(client))

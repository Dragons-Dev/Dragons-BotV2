import json
from random import choice

import discord
from discord import ui
from discord.ext import commands

import utils
from utils import Bot, CustomLogger, Settings, SettingsEnum


class InputModal(ui.Modal):
    def __init__(self, title: str, channel_ctx: discord.VoiceChannel):
        self.title = title
        self.channel = channel_ctx
        if title == ":1234: - Set User Limit":
            ...
        elif title == ":lock: - Lock/Unlock Channel for the default role":
            ...
        elif title == ":ghost: - Hide/Unhide Channel from the default role":
            ...
        elif title == ":flag_black: - Blacklist roles":
            ...
        elif title == ":flag_white: - Whitelist roles":
            ...
        elif title == ":love_letter: - Invite a user":
            self.title = "Invite someone"
            items = [
                ui.TextInput(
                    label="W.I.P.",
                    placeholder="This feature is not implemented yet",
                    style=discord.TextStyle.short,
                    required=True,
                    max_length=0
                )
            ]
        elif title == ":space_invader: - Change bitrate":
            self.title = "Change bitrate"
            voice_quality_options = [
                discord.SelectOption(label="8 kbps", value="8000"),
                discord.SelectOption(label="16 kbps", value="16000"),
                discord.SelectOption(label="32 kbps", value="32000"),
                discord.SelectOption(label="64 kbps (Discords Default)", value="64000"),
                discord.SelectOption(label="96 kbps", value="96000")
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
                    description=f"The higher the bitrate the better the quality but also the higher the data usage. Currently {self.channel.bitrate // 1000} kbps",
                    options=voice_quality_options,
                    min_values=1,
                    max_values=1
                )
            ]
        else:
            items = [ui.TextDisplay("The Bot ran into an error, please contact the developer!")]

        super().__init__(
            *items,
            title=self.title,
            timeout=300
        )

    async def callback(self, interaction: discord.Interaction):
        # await interaction.response.send_message(f"You entered: {self.children[0].values[0]}", ephemeral=True)
        client: utils.Bot = interaction.client  # type: ignore # mypy is dumb
        voice_channel = await client.db.get_temp_voice(interaction.user.voice.channel)
        if voice_channel is None:
            await interaction.respond("This is not a join2create channel", ephemeral=True)
        else:
            if interaction.user.id == voice_channel.owner_id:
                if self.title == ":space_invader: - Change bitrate":
                    try:
                        bitrate = int(self.children[0].values[0])
                        if bitrate < 8000 or bitrate > interaction.user.voice.channel.guild.bitrate_limit:
                            await interaction.respond(
                                f"Bitrate must be between 8 and {interaction.user.voice.channel.guild.bitrate_limit} kbps",
                                ephemeral=True)
                            return
                        await interaction.user.voice.channel.edit(bitrate=bitrate,
                                                                  reason="Changed by owner via VoiceBoard")
                        await interaction.respond(f"Changed bitrate to {bitrate // 1000} kbps", ephemeral=True)
                    except ValueError:
                        await interaction.respond("Invalid bitrate", ephemeral=True)
            else:
                await interaction.respond(
                    f"You are not the owner of this channel <@{voice_channel.owner_id}> is the owner!",
                    ephemeral=True
                )


class VoiceBoard(ui.View):
    def __init__(self, channel: discord.VoiceChannel = None):
        super().__init__(timeout=None)
        self.channel = channel

        text_container = ui.Container(
            color=discord.Color.dark_gold()
        )

        text_container.add_item(
            ui.TextDisplay(
                """
    ## **Voice Controller**

    :1234: - Set User Limit
    :crown: - Claim Ownership
    :lock: - Lock/Unlock Channel for the default role
    :ghost: - Hide/Unhide Channel from the default role
    :flag_black: - Blacklist roles
    :flag_white: - Whitelist roles
    :love_letter: - Invite a user
    :space_invader: - Change bitrate
                """
            )
        )

        self.add_item(text_container)

    @ui.button(emoji=":crown", label="Claim channel", style=discord.ButtonStyle.blurple, row=0, id=100)
    async def claim_channel(self, button: ui.Button, interaction: discord.Interaction):
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
                    "The owner is still in the channel, you cannot claim it!",
                    ephemeral=True
                )
                return
            voice_channel.owner_id = interaction.user.id
            await client.db.update_temp_voice(
                interaction.guild.get_channel(voice_channel.channel),
                interaction.user,
                voice_channel.locked,
                voice_channel.ghosted
            )
            await interaction.response.send_message(f"Channel ownership transferred to {interaction.user.mention}!")
            return

    @ui.button(emoji=":1234:", label="Set User Limit", style=discord.ButtonStyle.blurple, row=1, id=101)
    async def set_user_limit(self, button: ui.Button, interaction: discord.Interaction):
        await interaction.response.send_modal(InputModal(":1234: - Set User Limit", self.channel))

    @ui.button(emoji=":space_invader:", label="Change bitrate", style=discord.ButtonStyle.blurple, row=1, id=102)
    async def set_bitrate(self, button: ui.Button, interaction: discord.Interaction):
        await interaction.response.send_modal(InputModal(":space_invader: - Change bitrate", self.channel))


class Join2Create(commands.Cog):
    def __init__(self, client):
        self.client: Bot = client
        self.logger = CustomLogger(self.qualified_name, self.client.boot_time)
        with open("assets/suffix.json") as f:
            self.statuse = json.load(f)
            self.suffixes = [*self.statuse]

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
            join2create_setting = await self.client.db.get_setting(setting=SettingsEnum.Join2CreateChannel,
                                                                   guild=member.guild)
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
                try:
                    channel = await after.channel.category.create_voice_channel(
                        name=f"{member.display_name} {channel_name}",
                        user_limit=25,
                        reason="Join2Create",
                        overwrites=perms,
                    )
                except (discord.Forbidden, discord.HTTPException, discord.InvalidArgument) as e:
                    self.logger.error(e)
                    return

                if self.statuse[channel_name]:
                    status = choice(self.statuse[channel_name])
                    await channel.set_status(
                        status= status,
                        reason="Join2Create"
                    )



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
        await ctx.respond(view=VoiceBoard(
            channel=ctx.author.voice.channel if ctx.author.voice else ctx.channel
        ), ephemeral=True)

def setup(client):
    client.add_cog(Join2Create(client))

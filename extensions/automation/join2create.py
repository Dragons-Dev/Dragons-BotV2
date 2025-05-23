from random import choice

import discord
from discord.ext import commands
from pycord.multicog import subcommand

from utils import Bot, CustomLogger, Settings, SettingsEnum


class Join2Create(commands.Cog):
    def __init__(self, client):
        self.client: Bot = client
        self.logger = CustomLogger(self.qualified_name, self.client.boot_time)
        with open("assets/suffix.txt") as f:
            self.suffixes = f.readlines()

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
                    member.guild.default_role: discord.PermissionOverwrite(view_channel=False),
                    member.guild.premium_subscriber_role: discord.PermissionOverwrite(move_members=True),
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
                channel = await after.channel.category.create_voice_channel(
                    name=f"{member.display_name} {choice(self.suffixes)}",
                    user_limit=25,
                    reason="Join2Create",
                    overwrites=perms,
                )
                await self.client.db.create_temp_voice(channel, member)
                self.logger.debug(f"{member.name} created {channel.name} in {member.guild}")
                await member.move_to(channel)

        if before.channel is not None:
            if await self.client.db.get_temp_voice(before.channel):
                if len([m for m in before.channel.members if not m.bot]) == 0:
                    await self.client.db.delete_temp_voice(before.channel)
                    self.logger.debug(f"{before.channel.name} was deleted on {member.guild}")
                    await before.channel.delete(reason="Join2Delete")

    @subcommand("join2create")
    @commands.slash_command(name="setting", description="Manage settings for your voice channel")
    @discord.option(
        "option",
        description="The option you want to change",
        input_type=str,
        required=True,
        choices=[
            "allowed roles",
            "bitrate",
            "user limit",
            "name"
        ],
        parameter_name="option"
    )
    async def join2create_settings(self, ctx: discord.ApplicationContext, option: str):
        await ctx.response.send_message(f"Not implemented but you choose {option}!", ephemeral=True)

def setup(client):
    client.add_cog(Join2Create(client))

from random import choice

import discord
from discord.ext import commands

from utils import Bot, CustomLogger, SettingsEnum


class Join2Create(commands.Cog):
    def __init__(self, client):
        self.client: Bot = client
        self.logger = CustomLogger(self.qualified_name, self.client.boot)

    @commands.Cog.listener("on_voice_state_update")
    async def on_join2create(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        """
        Checks if a person joins a dedicated voice channel. If so creates a new voice channel and moves the person to it
        Creates a new database entry for the new voice channel and deletes it if everyone left it.
        """
        if after is not None:
            if after.channel == await self.client.db.get_setting(
                setting=SettingsEnum.Join2CreateChannel, guild=member.guild
            ):
                role = member.guild.get_role(
                    await self.client.db.get_setting(setting=SettingsEnum.VerifiedRole, guild=member.guild)
                )
                with open("funny_names.txt") as f:
                    names = f.readlines()
                # TODO: Create overwrite

                channel = await after.channel.category.create_voice_channel(
                    name=choice(names), user_limit=25, reason="Join2Create"
                )
                await member.move_to(channel)


def setup(client):
    client.add_cog(Join2Create(client))

from random import choice

import discord
from discord.ext import commands

from utils import Bot, CustomLogger, SettingsEnum


class Join2Create(commands.Cog):
    def __init__(self, client):
        self.client: Bot = client
        self.logger = CustomLogger(self.qualified_name, self.client.boot)
        with open("suffix.txt") as f:
            self.suffixes = f.readlines()

    @commands.Cog.listener("on_voice_state_update")
    async def on_join2create(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        """
        Checks if a person joins a dedicated voice channel. If so creates a new voice channel and moves the person to it
        Creates a new database entry for the new voice channel and deletes it if everyone left it.
        """
        # TODO: filter everything out that is no join or leave event

        if after.channel is not None:
            self.logger.debug(f"{member.name} joined {after.channel.name} on {member.guild}")
            self.client.dispatch("internal_voice_join", member, after)
            if after.channel.id == await self.client.db.get_setting(
                setting=SettingsEnum.Join2CreateChannel, guild=member.guild
            ):
                role = member.guild.get_role(
                    await self.client.db.get_setting(setting=SettingsEnum.VerifiedRole, guild=member.guild)
                )

                # TODO: Create overwrite

                channel = await after.channel.category.create_voice_channel(
                    name=f"{member.display_name} {choice(self.suffixes)}", user_limit=25, reason="Join2Create"
                )
                await self.client.db.join2create(channel, member)
                await member.move_to(channel)

        if before.channel is not None:
            self.logger.debug(f"{member.name} left {before.channel.name} on {member.guild}")
            self.client.dispatch("internal_voice_leave", member, before)
            if await self.client.db.join2get(before.channel):
                if len([m for m in before.channel.members if not m.bot]) == 0:
                    await self.client.db.join2delete(before.channel)


def setup(client):
    client.add_cog(Join2Create(client))

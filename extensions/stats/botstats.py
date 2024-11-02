from datetime import datetime

import discord
from discord.ext import commands, tasks

import utils
from utils import Bot, CustomLogger


class BotStats(commands.Cog):
    def __init__(self, client):
        self.client: Bot = client
        self.logger = CustomLogger(self.qualified_name, self.client.boot_time)
        self.pings = []
        self.avg_ping.start()
        self.save_voice_to_db.start()
        self.voice_seconds = {}

    @tasks.loop(minutes=1)
    async def avg_ping(self):
        await self.client.wait_until_ready()
        if len(self.pings) >= 10:
            del self.pings[0]
        self.pings.append(self.client.latency)

    def avg_latency(self) -> float:
        """
        Returns: the average latency of the bot
        """
        return (sum(self.pings) / len(self.pings)) * 1000

    @commands.Cog.listener("on_application_command")
    async def on_application_command(self, cmd: discord.ApplicationContext):
        if not cmd.guild:
            return
        await self.client.db.update_user_stat(cmd.author, utils.StatTypeEnum.CommandsUsed, 1, cmd.guild)

    @commands.Cog.listener("on_message")
    async def on_msg(self, msg: discord.Message):
        if msg.author.bot:
            return
        if not msg.guild:
            return
        await self.client.db.update_user_stat(msg.author, utils.StatTypeEnum.MessagesSent, 1, msg.guild)

    @tasks.loop(minutes=5)
    async def save_voice_to_db(self):
        await self.client.wait_until_ready()
        for guild_id, users in self.voice_seconds.items():
            for user_id, data in users.items():
                await self._update_voice_seconds(data["user"], data["guild"], True)
                self.voice_seconds[guild_id][user_id]["time"] = datetime.now()

    async def _update_voice_seconds(self, member: discord.Member, before_guild: discord.Guild, update: bool = False):
        before_guild_cache = self.voice_seconds.get(str(before_guild.id))
        if before_guild_cache is None:
            return self.logger.error(
                f"Before guild cache is none Guild: {before_guild.id} | Voice Cache: {self.voice_seconds}"
            )
        else:
            user_id_cache: dict[str, datetime] = before_guild_cache.get(str(member.id))  # type: ignore
            if user_id_cache is None:
                return self.logger.error(
                    f"User cache is none Guild: {before_guild.id} Member: {member.id} | Voice Cache: {self.voice_seconds}"
                )

            db_time = datetime.now() - user_id_cache["time"]
            db_time = int(db_time.total_seconds())  # type: ignore
            await self.client.db.update_user_stat(
                member, utils.StatTypeEnum.VoiceTime, db_time, before_guild  # type: ignore
            )

            if not update:
                del self.voice_seconds[str(before_guild.id)][str(member.id)]


    @commands.Cog.listener("on_voice_state_update")
    async def on_voice_state_update(
            self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState
    ):
        if before.channel:
            if after.channel:
                if before.channel != after.channel:
                    if before.channel.guild.id == after.channel.guild.id:
                        return  # don't care if it's still the same discord guild
                    else:
                        await self._update_voice_seconds(member, member.guild)
                        try:
                            self.voice_seconds[f"{after.channel.guild.id}"]
                        except KeyError:
                            self.voice_seconds[f"{after.channel.guild.id}"] = {}
                        self.voice_seconds[f"{after.channel.guild.id}"][f"{member.id}"] = {
                            "time": datetime.now(),
                            "user": member,
                            "guild": member.guild,
                        }
                else:
                    return  # this path is triggered if someone does something in a voice channel
            else:
                await self._update_voice_seconds(member, member.guild)

        elif after.channel:
            try:
                self.voice_seconds[f"{after.channel.guild.id}"]
            except KeyError:
                self.voice_seconds[f"{after.channel.guild.id}"] = {}
            self.voice_seconds[f"{after.channel.guild.id}"][f"{member.id}"] = {
                "time": datetime.now(),
                "user": member,
                "guild": member.guild,
            }
        else:
            self.logger.error("Neither before nor after channel")
            return


def setup(client):
    client.add_cog(BotStats(client))

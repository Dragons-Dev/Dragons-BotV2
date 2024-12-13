from datetime import datetime

import discord
from discord.ext import commands, tasks

import utils
from utils import Bot, CustomLogger


class TimedUser:
    def __init__(self, user: discord.Member, guild: discord.Guild):
        self.user = user
        self.guild = guild
        self.time = datetime.now()

    def __repr__(self):
        return f"TimedUser(user={self.user}, guild={self.guild}, time={(datetime.now() - self.time).total_seconds()})"


class BotStats(commands.Cog):
    def __init__(self, client):
        self.client: Bot = client
        self.logger = CustomLogger(self.qualified_name, self.client.boot_time)
        self.pings = []
        self.avg_ping.start()
        self.save_voice_to_db.start()
        self.voice_time_cache = {}  # structure: {guild_id: {user_id: TimedUser}}}

    def _add_or_update_user(self, user: discord.Member, guild: discord.Guild):
        if str(guild.id) not in self.voice_time_cache:
            self.voice_time_cache[str(guild.id)] = {}
        self.voice_time_cache[str(guild.id)][str(user.id)] = TimedUser(user, guild)

    def _get_user(self, guild: int, user: int) -> TimedUser | None:
        try:
            return self.voice_time_cache[str(guild)][str(user)]
        except KeyError:
            return None

    def _delete_user(self, guild: int, user: int):
        try:
            del self.voice_time_cache[str(guild)][str(user)]
            if len(self.voice_time_cache[str(guild)]) == 0:
                del self.voice_time_cache[str(guild)]
        except KeyError:
            return self.logger.error(
                f"Couldn't get user: {user}, guild: {guild} | Voice Cache: {self.voice_time_cache}"
            )

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
        for guild_id in self.voice_time_cache:
            for user_id in self.voice_time_cache[guild_id]:
                user: TimedUser = self.voice_time_cache[guild_id][user_id]
                await self._update_voice_seconds(user.user, user.guild, update=True)
                self._add_or_update_user(user.user, user.guild)

    async def _update_voice_seconds(self, member: discord.Member, guild: discord.Guild, update: bool = False):
        db_time = datetime.now() - self._get_user(guild.id, member.id).time  # type: ignore
        db_time = int(db_time.total_seconds())
        await self.client.db.update_user_stat(
            user=member,
            stat_type=utils.StatTypeEnum.VoiceTime,
            value=db_time,
            guild=guild
        )
        if not update:
            self._delete_user(guild.id, member.id)

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
                        self._add_or_update_user(member, member.guild)  # if they switched servers
                else:
                    if after.self_deaf:
                        await self._update_voice_seconds(member, member.guild)
                        # we don't want to count the members time if they are deafened
                    if before.self_deaf and not after.self_deaf:
                        self._add_or_update_user(member, member.guild)
                        # but we want to start counting again if they've undeafen themselves
                    return  # this path is triggered if someone does something in a voice channel
            else:
                await self._update_voice_seconds(member, member.guild)  # if they left a voice channel
        elif after.channel:
            self._add_or_update_user(member, member.guild)  # if they joined a voice channel
        else:
            self.logger.error("Neither before nor after channel")
            return

    @commands.Cog.listener("on_start_done")
    async def on_start_done(self):
        for guild in self.client.guilds:
            for channel in guild.voice_channels:
                for member in channel.members:
                    if member.voice.self_deaf:
                        pass
                    else:
                        self._add_or_update_user(member, guild)


def setup(client):
    client.add_cog(BotStats(client))

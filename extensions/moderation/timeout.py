# type: ignore
from datetime import timedelta

import discord
from discord.ext import commands
import pycord.multicog as pycog

from utils import Bot, CustomLogger, InfractionsEnum, is_team


_DURATION_PARSERS = {
    "s": lambda v: timedelta(seconds=v),
    "m": lambda v: timedelta(minutes=v),
    "h": lambda v: timedelta(hours=v),
    "d": lambda v: timedelta(days=v),
    "w": lambda v: timedelta(days=27, hours=23, minutes=59) if v == 4 else timedelta(weeks=v),
}


def _parse_duration(length: str, logger: CustomLogger) -> timedelta:
    if length and length[:-1].isdigit():
        parser = _DURATION_PARSERS.get(length[-1])
        if parser is not None:
            return parser(int(length[:-1]))
    logger.critical(f"Invalid duration provided: {length}")
    return timedelta(seconds=1)


class Timeout(commands.Cog):
    def __init__(self, client):
        self.client: Bot = client
        self.logger = CustomLogger(self.qualified_name, self.client.boot_time)

    @pycog.subcommand("mod")
    @commands.slash_command(name="timeout", description="Timeouts a given member for a given time")
    @is_team()
    @discord.option("member", description="The member you want to timeout", input_type=discord.Member, required=True)
    @discord.option("reason", description="The reason for the timeout", input_type=str, required=True)
    async def timeout(
        self,
        ctx: discord.ApplicationContext,
        member: discord.Member,
        length: discord.Option(
            name="timeout_time",
            description="For how long the timeout will be",
            input_type=str,
            required=True,
            choices=[
                "10s",
                "30s",
                "1m",
                "5m",
                "10m",
                "30m",
                "1h",
                "2h",
                "12h",
                "1d",
                "1w",
                "2w",
                "4w",
            ],
        ),
        reason: str,
    ):
        if member.bot:
            return await ctx.response.send_message("I do not timeout any bot", ephemeral=True)
        if member.top_role >= ctx.guild.me.top_role:
            return await ctx.response.send_message(
                "I can't timeout that member since his top role is higher or even to mine", ephemeral=True
            )
        try:
            until = _parse_duration(length, self.logger)
            self.client.dispatch(
                "moderation_action",
                InfractionsEnum.Timeout,
                member,
                ctx.guild,
                reason,
                ctx.author,
                ctx=ctx,
                duration=until,
            )
        except (discord.Forbidden, discord.HTTPException) as e:
            raise e


def setup(client):
    client.add_cog(Timeout(client))

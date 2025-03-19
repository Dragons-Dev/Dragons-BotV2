from datetime import datetime, timedelta

import discord
import pycord.multicog as pycog
from discord.ext import commands
from discord.utils import format_dt, get_or_fetch

from utils import Bot, ButtonInfo, CustomLogger, InfractionsEnum, SettingsEnum, is_team


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
        length: discord.Option(  # type: ignore
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
            if length[-1] == "s":
                length = int(length[:-1])
                until = timedelta(seconds=length)
            elif length[-1] == "m":
                length = int(length[:-1])
                until = timedelta(minutes=length)
            elif length[-1] == "h":
                length = int(length[:-1])
                until = timedelta(hours=length)
            elif length[-1] == "d":
                length = int(length[:-1])
                until = timedelta(days=length)
            elif length[-1] == "w":
                length = int(length[:-1])
                until = timedelta(weeks=length)
                if length == 4:
                    until = timedelta(days=27, hours=23, minutes=59)
            else:
                until = timedelta(seconds=1)
                self.logger.critical(f"Invalid duration provided: {length}")
            await member.timeout_for(duration=until, reason=reason)
            await self.client.db.create_infraction(
                user=member, infraction=InfractionsEnum.Timeout, reason=reason, guild=ctx.guild
            )
            infractions = await self.client.db.get_infraction(case_id=None, user=member)
            if len(infractions) == 1:
                case = infractions.case_id
            else:
                case = infractions[-1].case_id
            em = discord.Embed(title="Timeout successful", color=discord.Color.brand_green())
            em.add_field(name="User", value=member.mention, inline=False)
            em.add_field(name="Moderator", value=ctx.author.mention, inline=False)
            em.add_field(name="Until", value=format_dt((datetime.now() + until), "R"), inline=False)
            em.add_field(name="Reason", value=reason, inline=False)
            em.add_field(name="Date", value=format_dt(datetime.now(), "F"), inline=False)
            em.set_footer(text=f"Case ID: {case}")
            await ctx.response.send_message(
                embed=em,
                view=ButtonInfo("A copy of this was sent to the timeouted member and the log channel!"),
                ephemeral=True,
            )
            member_em = em.copy()
            member_em.title = "Timeout"
            member_em.colour = discord.Color.yellow()
            try:
                await member.send(
                    embed=member_em,
                    view=ButtonInfo("A copy of this was sent to the log channel and was stored in the database!"),
                )
            except discord.HTTPException or discord.Forbidden:
                pass
            setting = await self.client.db.get_setting(setting=SettingsEnum.ModLogChannel, guild=ctx.guild)
            if setting:
                log_channel: discord.TextChannel = await get_or_fetch(ctx.guild, "channel", setting.value, default=None)
                if log_channel:
                    await log_channel.send(embed=member_em)
        except discord.Forbidden or discord.HTTPException as e:
            raise e


def setup(client):
    client.add_cog(Timeout(client))

from datetime import datetime

import discord
import pycord.multicog as pycog
from discord.ext import commands

from utils import Bot, ButtonConfirm, ButtonInfo, CustomLogger, is_team


class Kick(commands.Cog):
    def __init__(self, client):
        self.client: Bot = client
        self.logger = CustomLogger(self.qualified_name, self.client.boot_time)

    @pycog.subcommand("mod", independent=True)
    @commands.slash_command(name="kick", description="Kicks a given member")
    @is_team()
    @discord.option("member", description="The member you want to kick", input_type=discord.Member, required=True)
    @discord.option("reason", description="The reason for the kick", input_type=str, required=True)
    async def kick(
        self,
        ctx: discord.ApplicationContext,
        member: discord.Member,
        reason: str,
    ):
        if member.top_role >= ctx.guild.me.top_role:
            return await ctx.response.send_message(
                "I can't kick that member since his top role is higher or even to mine", ephemeral=True
            )
        em = discord.Embed(title="Kick successful", color=discord.Color.brand_green(), timestamp=datetime.now())
        em.add_field(name="User", value=member.mention, inline=False)
        em.add_field(name="Moderator", value=ctx.author.mention, inline=False)
        em.add_field(name="Reason", value=reason, inline=False)

        view = ButtonConfirm(cancel_title="Kick cancelled!")
        msg = await ctx.response.send_message(f"Do you really want to kick {member.mention}", view=view, ephemeral=True)
        view.original_msg = msg
        await view.wait()
        if view.value is None or not view.value:
            return
        else:
            try:
                member_em = em.copy()
                member_em.title = "Kick"
                member_em.colour = discord.Color.brand_red()
                await member.send(
                    embed=member_em,
                    view=ButtonInfo("A copy of this was sent to the log channel and was stored in the database!"),
                )
            except discord.HTTPException or discord.Forbidden:
                pass
            await member.kick(reason=reason)
            await ctx.followup.send(
                embed=em,
                view=ButtonInfo("A copy of this was sent to the kicked member and the log channel!"),
                ephemeral=True,
            )

    @kick.error
    async def kick_error_handler(self, ctx: discord.ApplicationContext, exc: discord.DiscordException):
        if isinstance(exc, discord.ApplicationCommandInvokeError):
            return await ctx.response.send_message(
                embed=discord.Embed(
                    title="Error", description=f"This user is no member of this guild.", color=discord.Color.brand_red()
                ),
                ephemeral=True,
            )
        else:
            raise exc


def setup(client):
    client.add_cog(Kick(client))

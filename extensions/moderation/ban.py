from datetime import datetime

import discord
from discord.ext import commands

from utils import Bot, ButtonConfirm, ButtonInfo, CustomLogger, is_team


class Ban(commands.Cog):
    def __init__(self, client):
        self.client: Bot = client
        self.logger = CustomLogger(self.qualified_name, self.client.boot_time)

    @commands.slash_command(name="ban", description="Bans a given member")
    @is_team()
    @discord.option("member", description="The member you want to ban", input_type=discord.Member, required=True)
    @discord.option("reason", description="The reason for the ban", input_type=str, required=True)
    async def ban(
        self,
        ctx: discord.ApplicationContext,
        member: discord.Member,
        reason: str,
    ):
        if member.top_role >= ctx.guild.me.top_role:
            return await ctx.response.send_message(
                "I can't ban that member since his top role is higher or even to mine", ephemeral=True
            )
        em = discord.Embed(title="Ban successful", color=discord.Color.brand_green(), timestamp=datetime.now())
        em.add_field(name="User", value=member.mention, inline=False)
        em.add_field(name="Moderator", value=ctx.author.mention, inline=False)
        em.add_field(name="Reason", value=reason, inline=False)

        view = ButtonConfirm(cancel_title="Ban cancelled!")
        msg = await ctx.response.send_message(f"Do you really want to ban {member.mention}", view=view, ephemeral=True)
        view.original_msg = msg
        await view.wait()
        if view.value is None or not view.value:
            return
        else:
            try:
                member_em = em.copy()
                member_em.title = "Ban"
                member_em.colour = discord.Color.brand_red()
                await member.send(
                    embed=member_em,
                    view=ButtonInfo("A copy of this was sent to the log channel and was stored in the database!"),
                )
            except discord.HTTPException or discord.Forbidden:
                pass
            await member.ban(reason=reason)
            await ctx.followup.send(
                embed=em,
                view=ButtonInfo("A copy of this was sent to the banned member and the log channel!"),
                ephemeral=True,
            )


def setup(client):
    client.add_cog(Ban(client))

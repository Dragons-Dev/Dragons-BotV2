import typing as t
from datetime import datetime

import discord
import pycord.multicog as pycog
from discord.ext import commands
from discord.utils import format_dt, get_or_fetch

from utils import (
    Bot,
    ButtonConfirm,
    ButtonInfo,
    CustomLogger,
    InfractionsEnum,
    SettingsEnum,
    is_team,
)


class Ban(commands.Cog):
    def __init__(self, client):
        self.client: Bot = client
        self.logger = CustomLogger(self.qualified_name, self.client.boot_time)

    @pycog.subcommand("mod")
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
        try:
            if member.top_role >= ctx.guild.me.top_role:
                return await ctx.response.send_message(
                    "I can't ban that member since his top role is higher or even to mine", ephemeral=True
                )
        except AttributeError:
            # if the member is not in the guild, we cannot check roles
            pass
        em = discord.Embed(title="Ban successful", color=discord.Color.brand_green())
        em.add_field(name="User", value=member.mention, inline=False)
        em.add_field(name="Moderator", value=ctx.author.mention, inline=False)
        em.add_field(name="Reason", value=reason, inline=False)
        em.add_field(name="Date", value=format_dt(datetime.now(), "F"), inline=False)

        view = ButtonConfirm(cancel_title="Ban cancelled!")
        msg = await ctx.response.send_message(f"Do you really want to ban {member.mention}", view=view, ephemeral=True)
        view.original_msg = msg
        await view.wait()
        if view.value is None or not view.value:
            return
        else:
            case_id = await self.client.db.create_infraction(
                user=member, infraction=InfractionsEnum.Ban, reason=reason, guild=ctx.guild
            )
            em.set_footer(text=f"Case ID: {case_id}")
            member_em = em.copy()
            member_em.title = "Ban"
            member_em.colour = discord.Color.brand_red()
            try:
                await member.send(
                    embed=member_em,
                    view=ButtonInfo("A copy of this was sent to the log channel and was stored in the database!"),
                )
            except discord.HTTPException or discord.Forbidden:
                pass
            await ctx.guild.ban(member, reason=reason)
            setting = await self.client.db.get_setting(setting=SettingsEnum.ModLogChannel, guild=ctx.guild)
            if setting:
                if isinstance(setting, (tuple, list, t.Sequence)):
                    log_channel: discord.TextChannel = await get_or_fetch(
                        ctx.guild, "channel", setting[0].value, default=None
                    )
                else:
                    log_channel: discord.TextChannel = await get_or_fetch(
                        ctx.guild, "channel", setting.value, default=None
                    )

                    log_channel: discord.TextChannel = await get_or_fetch(ctx.guild, "channel", setting.value,
                                                                          default=None)

                if log_channel:
                    await log_channel.send(embed=member_em)
            await ctx.followup.send(
                embed=em,
                view=ButtonInfo("A copy of this was sent to the banned member and the log channel!"),
                ephemeral=True,
            )

    @ban.error
    async def ban_error_handler(self, ctx: discord.ApplicationContext, exc: discord.ApplicationCommandError):
        if isinstance(exc, discord.ApplicationCommandInvokeError):
            try:  # this most likely fails if we try to invoke the warn command with a user_id
                member_id = ctx.selected_options[0].get(
                    "value"
                )  # this is heavily dependent on the order returned by Discord
                reason = ctx.selected_options[1].get("value")  # this might be the first point of failure
                member = await ctx.bot.get_or_fetch_user(member_id)
                await ctx.invoke(self.ban, member=member, reason=reason)
            except Exception as e:  # we can't invoke the warn command or can't fetch/get the user
                try:
                    self.logger.error(
                        f"Failed to invoke the ban command with "
                        f"the following parameters: "
                        f"CTX: {ctx.selected_options}, "
                        f"Member ID: {member_id}, "
                        f"Reason: {reason}",
                        exc_info=e,
                    )
                except Exception as f:  # we can't get the parameters for the warn command
                    self.logger.critical(f"Failed to get the parameters for the ban command: {f}", exc_info=f)
            finally:
                await ctx.response.send_message(
                    embed=discord.Embed(
                        title="Error",
                        description="An unexpected error occurred. Please try again later or contact the developer on "
                                    "[GitHub](https://github.com/Dragons-Dev/Dragons-BotV2).\n",
                        color=discord.Color.brand_red(),
                    ),
                    ephemeral=True,
                )
        else:
            raise exc


def setup(client):
    client.add_cog(Ban(client))

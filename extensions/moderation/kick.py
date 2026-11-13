import discord
from discord.ext import commands
import pycord.multicog as pycog

from extensions.internal.error_handler import error_embed
from utils import (
    Bot,
    ButtonConfirm,
    CommandDisabledError,
    CustomLogger,
    InfractionsEnum,
    is_team,
)


class Kick(commands.Cog):
    def __init__(self, client):
        self.client: Bot = client
        self.logger = CustomLogger(self.qualified_name, self.client.boot_time)

    @pycog.subcommand("mod")
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

        view = ButtonConfirm(cancel_title="Kick cancelled!")
        msg = await ctx.response.send_message(f"Do you really want to kick {member.mention}", view=view, ephemeral=True)
        view.original_msg = msg
        await view.wait()
        if view.value is None or not view.value:
            return

        self.client.dispatch(
            "moderation_action",
            InfractionsEnum.Kick,
            member,
            ctx.guild,
            reason,
            ctx.author,
            ctx=ctx,
        )

    @kick.error
    async def kick_error_handler(self, ctx: discord.ApplicationContext, exc: discord.DiscordException):
        if isinstance(exc, discord.ApplicationCommandInvokeError):
            return await ctx.response.send_message(
                embed=discord.Embed(
                    title="Error", description="This user is no member of this guild.", color=discord.Color.brand_red()
                ),
                ephemeral=True,
            )
        elif isinstance(exc, CommandDisabledError):
            await ctx.response.send_message(
                embed=error_embed(
                    title="Command disabled",
                    description=f"The command `/{ctx.command.qualified_name}` is disabled in this guild.",
                ),
                ephemeral=True,
            )
        else:
            raise exc


def setup(client):
    client.add_cog(Kick(client))

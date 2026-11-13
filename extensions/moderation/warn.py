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


class Warn(commands.Cog):
    def __init__(self, client):
        self.client: Bot = client
        self.logger = CustomLogger(self.qualified_name, self.client.boot_time)

    @pycog.subcommand("mod")
    @commands.slash_command(name="warn", description="Warns a given member")
    @is_team()
    @discord.option(
        "member",
        description="The member you want to warn",
        input_type=discord.SlashCommandOptionType.user,
        required=True,
    )
    @discord.option("reason", description="The reason for the warn", input_type=str, required=True)
    async def warn(
        self,
        ctx: discord.ApplicationContext,
        member: discord.Member | discord.User,
        reason: str,
    ):
        try:
            if member.top_role >= ctx.guild.me.top_role:
                return await ctx.response.send_message(
                    "I can't warn that member since his top role is higher or even to mine", ephemeral=True
                )
        except AttributeError:
            # if the member is not in the guild, we cannot check roles
            pass

        view = ButtonConfirm(cancel_title="Warn cancelled!")
        msg = await ctx.response.send_message(f"Do you really want to warn {member.mention}", view=view, ephemeral=True)
        view.original_msg = msg
        await view.wait()
        if view.value is None or not view.value:
            return

        self.client.dispatch(
            "moderation_action",
            InfractionsEnum.Warn,
            member,
            ctx.guild,
            reason,
            ctx.author,
            ctx=ctx,
        )

    @warn.error
    async def warn_error_handler(self, ctx: discord.ApplicationContext, exc: discord.DiscordException):
        if isinstance(exc, discord.ApplicationCommandInvokeError):
            try:  # this most likely fails if we try to invoke the warn command with a user_id
                member_id = ctx.selected_options[0].get(
                    "value"
                )  # this is heavily dependent on the order returned by Discord
                reason = ctx.selected_options[1].get("value")  # this might be the first point of failure
                member = await ctx.bot.get_or_fetch_user(member_id)
                await ctx.invoke(self.warn, member=member, reason=reason)
            except Exception as e:  # we can't invoke the warn command or can't fetch/get the user
                try:
                    self.logger.error(
                        f"Failed to invoke the warn command with "
                        f"the following parameters: "
                        f"CTX: {ctx.selected_options}, "
                        f"Member ID: {member_id}, "
                        f"Reason: {reason}",
                        exc_info=e,
                    )
                except Exception as f:  # we can't get the parameters for the warn command
                    self.logger.critical(f"Failed to get the parameters for the warn command: {f}", exc_info=f)
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
    client.add_cog(Warn(client))

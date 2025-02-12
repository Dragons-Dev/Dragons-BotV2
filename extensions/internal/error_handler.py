import discord
from discord.ext import commands

from utils import Bot, CustomLogger


def error_embed(title: str, description: str) -> discord.Embed:
    return discord.Embed(
        title=title,
        description=description,
        color=discord.Color.brand_red(),
        footer=discord.EmbedFooter(text="If you think this behavior is wrong please contact dtheicydragon on discord!"),
    )


class ErrorHandler(commands.Cog):
    def __init__(self, client):
        self.client: Bot = client
        self.logger = CustomLogger(self.qualified_name, self.client.boot_time)

    @commands.Cog.listener("on_application_command_error")
    async def app_cmd_error(self, ctx: discord.ApplicationContext, exc: discord.DiscordException):
        if ctx.command.has_error_handler():
            return
        self.logger.warning(f"Commandname: {ctx.command.name}   Exception: {exc}: {type(exc)}")
        match type(exc):
            case discord.CheckFailure:
                await ctx.response.send_message(
                    embed=error_embed(
                        title="Check failure",
                        description=f"A validation check failed. Most likely you do not have the correct permission to "
                        f"execute `/{ctx.command.qualified_name}`.",
                    ),
                    ephemeral=True,
                )
            case commands.NotOwner:
                await ctx.response.send_message(
                    embed=error_embed(
                        title="Not owner",
                        description=f"You must be the owner of the bot to execute `{ctx.command.qualified_name}`.",
                    ),
                    ephemeral=True,
                )
            case _:
                raise exc


def setup(client):
    client.add_cog(ErrorHandler(client))

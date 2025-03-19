import discord
from discord.ext import commands
from discord.utils import get_or_fetch

from .classes import InsufficientPermission
from .enums import SettingsEnum


def is_team():
    """
    Decorator to check if the member executing the command has the configured team role.
    if no team role is set it checks the discord permissions
    """

    async def predicate(ctx: discord.ApplicationContext):
        team_role = await ctx.bot.db.get_setting(setting=SettingsEnum.TeamRole, guild=ctx.guild)
        if team_role is None:
            if ctx.author.guild_permissions.administrator or ctx.author.guild_permissions.manage_guild:
                return True
            else:
                raise InsufficientPermission(
                    "You need to be an administrator or have the manage_guild permission to execute this command.")

        else:
            role = await get_or_fetch(ctx.guild, "role", team_role.value, default=None)
            if role is None:
                raise PermissionError("The team role is not set up correctly. Please contact the guild owner!.")
            else:
                if role in ctx.author.roles:
                    return True

    return commands.check(predicate)

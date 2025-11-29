import discord
from discord import SlashCommandGroup
from discord.ext import commands

from utils import Bot, CustomLogger, CommandDisabledError, is_team


def strip_emoji(command_name: str) -> str:
    if command_name.startswith("🟢 ") or command_name.startswith("🔴 "):
        return command_name[2:]
    return command_name


async def autocomplete_commands(ctx: discord.AutocompleteContext) -> list[str]:
    bot: Bot = ctx.bot
    guild = ctx.interaction.guild
    if guild is None:
        return ["You can't disable commands in DMs."]  # Should not happen due to context restriction
    all_commands = [
        cmd.qualified_name
        for cmd in bot.walk_application_commands()
        if not isinstance(cmd, SlashCommandGroup) and cmd.name != "toggle-command"
    ]
    filtered = []
    if ctx.value:  # all_commands filter SlashCommandGroups because they are not executable commands
        filtered.extend([c for c in all_commands if ctx.value.lower() in c.lower()])
    emojified_commands = []
    try:
        for cmd in filtered if len(filtered) > 0 else all_commands:
            if await bot.db.is_command_enabled(guild=guild, command_name=cmd):
                emojified_commands.append(f"🟢 {cmd}")
            else:
                emojified_commands.append(f"🔴 {cmd}")
        return emojified_commands
    except Exception as e:
        bot.logger.critical(f"Error emojifying commands_list: {e}")
        return filtered if len(filtered) > 0 else all_commands


class EnabledCommands(commands.Cog):
    def __init__(self, client):
        self.client: Bot = client
        self.logger = CustomLogger(self.qualified_name, self.client.boot_time)
        self.client.add_check(self.command_enabled_check)

    async def command_enabled_check(self, ctx: discord.ApplicationContext) -> bool:
        if not ctx.guild:
            return True
        cmd_enabled = await self.client.db.is_command_enabled(ctx.guild, ctx.command.qualified_name)
        if not cmd_enabled:
            raise CommandDisabledError(f"The command `/{ctx.command.qualified_name}` is disabled in this guild.")
        return True

    @commands.slash_command(
        name="toggle-command",
        description="Toggles whether a command is enabled or disabled",
        context={discord.InteractionContextType.guild},
    )
    @is_team()
    @discord.option(
        name="command",
        description="The command to toggle",
        autocomplete=autocomplete_commands,
        required=True,
        parameter_name="cmd",
    )
    async def toggle_command(self, ctx: discord.ApplicationContext, cmd):
        command = strip_emoji(cmd)
        new_state = await self.client.db.toggle_command(ctx.guild, command)
        await ctx.respond(
            f"Command `{'🟢' if new_state else '🔴'} {command}` has been {'enabled' if new_state else 'disabled'}",
            ephemeral=True,
        )


def setup(client):
    client.add_cog(EnabledCommands(client))

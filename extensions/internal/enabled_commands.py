import discord
from discord import SlashCommandGroup
from discord.ext import commands

from utils import Bot, CustomLogger, CommandDisabledError, is_team


def strip_emojy(command_name: str) -> str:
    if command_name.startswith("🟢 ") or command_name.startswith("🔴 "):
        return command_name[2:]
    return command_name


async def get_available_commands(ctx: discord.AutocompleteContext) -> list[str]:
    bot: Bot = ctx.bot
    guild = ctx.interaction.guild
    if guild is None:
        return ["You can't disable commands in DMs."]  # Should not happen due to context restriction
    all_commands = [cmd.qualified_name for cmd in bot.walk_application_commands() if type(cmd) is not SlashCommandGroup]
    if ctx.value:  # all_commands filter SlashCommandGroups because they are not executable commands
        emojified_commands = []
        try:
            for cmd in all_commands:
                if await bot.db.is_command_enabled(guild=guild, command_name=cmd):
                    emojified_commands.append(f"🟢 {cmd}")
                else:
                    emojified_commands.append(f"🔴 {cmd}")
            filtered = [c for c in emojified_commands if ctx.value.lower() in c.lower()]
            return filtered
        except Exception as e:
            bot.logger.critical(f"Error emojifying commands_list: {e}")
            return [c for c in all_commands if ctx.value.lower() in c.lower()]
    else:
        emojified_commands = []
        try:
            for cmd in all_commands:
                if await bot.db.is_command_enabled(guild=guild, command_name=cmd):
                    emojified_commands.append(f"🟢 {cmd}")
                else:
                    emojified_commands.append(f"🔴 {cmd}")
            return emojified_commands
        except Exception as e:
            bot.logger.critical(f"Error emojifying commands_list: {e}")
            return all_commands


class EnabledCommands(commands.Cog):
    def __init__(self, client):
        self.client: Bot = client
        self.logger = CustomLogger(self.qualified_name, self.client.boot_time)
        self.client.add_check(self.command_enabled_check)

    async def command_enabled_check(self, ctx: discord.ApplicationContext) -> bool:
        print(f"Command: {ctx.command.name} was used in guild {ctx.guild.id} by {ctx.author.name}")
        if not ctx.guild:
            return True
        cmd_enabled = await self.client.db.is_command_enabled(ctx.guild, ctx.command.name)
        if not cmd_enabled:
            raise CommandDisabledError(f"{ctx.command.name} is not enabled")
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
        autocomplete=get_available_commands,
        required=True,
        parameter_name="cmd",
    )
    async def toggle_command(self, ctx: discord.ApplicationContext, cmd):
        command = strip_emojy(cmd)
        await self.client.db.toggle_command(ctx.guild, command)
        await ctx.respond(f"Toggling command `{command}`...", ephemeral=True)


def setup(client):
    client.add_cog(EnabledCommands(client))

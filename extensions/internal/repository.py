import discord
from sqlalchemy import select

from utils.orm_database.repository import BaseRepository

from .models import EnabledCommands

__all__ = ["EnabledCommandsRepository"]


class EnabledCommandsRepository(BaseRepository):
    """Repository for guild command enable/disable state."""

    async def is_command_enabled(self, guild: discord.Guild, command_name: str) -> bool:
        """
        Checks if a specific command is enabled for a given guild.

        Args:
            guild: The Discord guild to check the command status for.
            command_name: The name of the command to check.

        Returns:
            True if the command is enabled for the guild, or if no record exists (default enabled).
            False if the command is explicitly disabled.
        """
        async with self.session() as session:
            query = select(EnabledCommands).where(
                EnabledCommands.guild_id == guild.id, EnabledCommands.command_name == command_name
            )
            result: EnabledCommands | None = (await session.execute(query)).scalar_one_or_none()
            if result is None:
                return True
            return bool(result.enabled)

    async def toggle_command(self, guild: discord.Guild, command_name: str) -> bool:
        """
        Toggles the enabled status of a command for a guild.
        Args:
            guild: The guild the command is being toggled in.
            command_name: the fully qualified name of the command to toggle.

        Returns: The new state of the command (enabled/disabled).
        """
        async with self.session() as session:
            query = select(EnabledCommands).where(
                EnabledCommands.guild_id == guild.id, EnabledCommands.command_name == command_name
            )
            result: EnabledCommands | None = (await session.execute(query)).scalar_one_or_none()
            new_state: bool
            if result is None:
                obj = EnabledCommands(guild_id=guild.id, command_name=command_name, enabled=False)
                session.add(obj)
                new_state = False  # Command not in DB means it was enabled; now disabling it
            else:
                result.enabled = not bool(result.enabled)
                new_state = bool(result.enabled)
            return new_state

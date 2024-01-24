import discord
from discord.ext import commands

from utils import Bot, CustomLogger


class ModBackground(commands.Cog):
    def __init__(self, client):
        self.client: Bot = client
        self.logger = CustomLogger(self.qualified_name, self.client.boot)

    @commands.Cog.listener("on_audit_log_entry")
    async def audit_listener(self, entry: discord.AuditLogEntry):
        match type(entry.target):
            case discord.Guild:
                self.logger.debug(f"Guild")
            case discord.abc.GuildChannel:
                self.logger.debug(f"GuildChannel")
            case discord.Member:
                self.logger.debug(f"Member")
            case discord.User:
                self.logger.debug(f"User")
            case discord.Role:
                self.logger.debug(f"Role")
            case discord.Invite:
                self.logger.debug(f"Invite")
            case discord.Emoji:
                self.logger.debug(f"Emoji")
            case discord.StageInstance:
                self.logger.debug(f"StageInstance")
            case discord.GuildSticker:
                self.logger.debug(f"GuildSticker")
            case discord.Thread:
                self.logger.debug(f"Thread")
            case discord.Object:
                self.logger.warning(f"Got discord.Object ({type(entry.target)}) Target: {entry.target}")
            case _:
                self.logger.warning(f"Got unidentified target: {entry.target}")


def setup(client):
    client.add_cog(ModBackground(client))

import discord
from discord.ext import commands

from utils import Bot, CustomLogger


class CommandGroups(commands.Cog):
    def __init__(self, client):
        self.client: Bot = client
        self.logger = CustomLogger(self.qualified_name, self.client.boot_time)

    mod = discord.SlashCommandGroup("mod", contexts=[discord.InteractionContextType.guild])


def setup(client):
    client.add_cog(CommandGroups(client))
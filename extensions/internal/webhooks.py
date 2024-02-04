import discord
from discord.ext import commands

from utils import Bot, CustomLogger


class InternalHooks(commands.Cog):
    def __init__(self, client):
        self.client: Bot = client
        self.logger = CustomLogger(self.qualified_name, self.client.boot)


def setup(client):
    client.add_cog(InternalHooks(client))

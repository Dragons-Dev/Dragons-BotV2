import io
from datetime import datetime

import chat_exporter
import discord
import pycord.multicog as pycog
from discord.ext import commands

from utils import Bot, CustomLogger, is_team


class ChannelExporter(commands.Cog):
    def __init__(self, client):
        self.client: Bot = client
        self.logger = CustomLogger(self.qualified_name, self.client.boot_time)

    @pycog.subcommand("mod", independent=True)
    @is_team()
    @commands.slash_command(name="export", description="Exports a channel to a single html file to archive it.")
    async def export(self, ctx: discord.ApplicationContext):
        await ctx.response.defer(ephemeral=True, invisible=False)
        transscript = await chat_exporter.export(
            channel=ctx.channel,
            guild=ctx.guild,
            military_time=True,
            fancy_times=True,
            bot=self.client,
        )

        temp = io.StringIO(transscript)
        file = discord.File(
            fp=temp, filename=f"{datetime.now().strftime('%Y-%m-%d')}-{ctx.channel.name}-" f"{ctx.author.name}.html"
        )
        await ctx.followup.send(f"{ctx.channel.name} export", file=file)


def setup(client):
    client.add_cog(ChannelExporter(client))

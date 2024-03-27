from typing import cast

import discord
import pycord.multicog as pycog
import wavelink
from discord.ext import commands

from utils import Bot, CustomLogger


class MusicConnect(commands.Cog):
    def __init__(self, client):
        self.client: Bot = client
        self.logger = CustomLogger(self.qualified_name, self.client.boot_time)

    @pycog.subcommand("music", independent=True)
    @commands.slash_command(name="play", description="Connect the bot to the voice channel and play the query")
    async def connect(
        self, ctx: discord.ApplicationContext, query: discord.Option(str, description="Search for anything to play it!")  # type: ignore
    ):
        if not ctx.guild:
            await ctx.response.send_message("I can't offer this service in dm's", ephemeral=True)
        player = cast(wavelink.Player, ctx.voice_client)
        if not ctx.voice_client:
            try:
                player = await ctx.author.voice.channel.connect(cls=wavelink.Player)
                await ctx.response.send_message(f"Joined {ctx.author.voice.channel.mention}", ephemeral=True)
            except AttributeError:
                await ctx.response.send_message(
                    f"Seems like you are not in a voice channel, please join one first!", ephemeral=True
                )
                return
            except discord.ClientException:
                await ctx.response.send_message("Something went wrong! Please try again.")
                return

        if not hasattr(player, "home"):
            player.home = ctx.channel
        elif player.home != ctx.channel:
            await ctx.response.send_message(
                f"You can only play songs in {player.home.mention}, as the player has already started there.",
                ephemeral=True,
            )
            return

        tracks: wavelink.Search = await wavelink.Playable.search(query)
        if not tracks:
            await ctx.send(f"{ctx.author.mention} - Could not find any tracks with that query. Please try again.")
            return

        if isinstance(tracks, wavelink.Playlist):
            # tracks is a playlist...
            added: int = await player.queue.put_wait(tracks)
            await ctx.send(f"Added the playlist **`{tracks.name}`** ({added} songs) to the queue.")
        else:
            track: wavelink.Playable = tracks[0]
            await player.queue.put_wait(track)
            await ctx.send(f"Added **`{track}`** to the queue.")

        if not player.playing:
            # Play now since we aren't playing anything...
            await player.play(player.queue.get(), volume=30)


def setup(client: Bot):
    client.add_cog(MusicConnect(client))

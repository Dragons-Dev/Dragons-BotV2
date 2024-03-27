import discord
import wavelink
from discord.ext import commands

from utils import Bot, CustomLogger


class MusicEvents(commands.Cog):
    def __init__(self, client):
        self.client: Bot = client
        self.logger = CustomLogger(self.qualified_name, self.client.boot_time)

    @commands.Cog.listener("on_wavelink_node_ready")
    async def on_wavelink_node_ready(self, payload: wavelink.NodeReadyEventPayload) -> None:
        self.logger.info(f"Node {payload.node!r} is ready!")

    @commands.Cog.listener("on_wavelink_stats_update")
    async def on_wavelink_stats_ready(self, payload: wavelink.StatsEventPayload) -> None:
        self.logger.debug(f"Wavelink stats are updated!")

    @commands.Cog.listener("on_wavelink_track_start")
    async def on_wavelink_track_start(self, payload: wavelink.TrackStartEventPayload):
        self.logger.debug("New track started!")

    @commands.Cog.listener("on_wavelink_track_end")
    async def on_wavelink_track_end(self, payload: wavelink.TrackEndEventPayload):
        try:
            track = payload.player.queue.get()
            payload.player.queue.delete(0)
        except wavelink.QueueEmpty:
            return

        await payload.player.play(track)

    @commands.Cog.listener("on_wavelink_track_exception")
    async def on_wavelink_track_exception(self, payload: wavelink.TrackExceptionEventPayload):
        self.logger.warning("Track had an exception!")

    @commands.Cog.listener("on_wavelink_track_stuck")
    async def on_wavelink_track_stuck(self, payload: wavelink.TrackStuckEventPayload):
        self.logger.debug("Track Stuck")

    @commands.Cog.listener("on_wavelink_websocket_closed")
    async def on_wavelink_websocket_closed(self, payload: wavelink.WebsocketClosedEventPayload):
        self.logger.debug("Websocket closed")

    @commands.Cog.listener("on_wavelink_node_closed")
    async def on_wavelink_node_closed(self, node: wavelink.Node, players: list[wavelink.Player]):
        self.logger.debug(f"{node.identifier} closed had {len(players)} players")

    @commands.Cog.listener("on_wavelink_extra_event")
    async def on_wavelink_extra_event(self, payload: wavelink.ExtraEventPayload):
        self.logger.debug(payload)


def setup(client):
    client.add_cog(MusicEvents(client))

import discord
from discord.ext import commands, tasks
from twitchio.client import Client

from utils import Bot, CustomLogger, SettingsEnum, Settings
from config import TWITCH_CLIENT_ID, TWITCH_CLIENT_SECRET


class TwitchAnnouncer(commands.Cog):
    def __init__(self, client):
        self.client: Bot = client
        self.logger = CustomLogger(self.qualified_name, self.client.boot_time)
        self.twitch_client = Client(client_id=TWITCH_CLIENT_ID, client_secret=TWITCH_CLIENT_SECRET)
        self.live_streaming = []


    @commands.Cog.listener("on_start_done")
    async def on_start_done(self):
        self.check_twitch.start()

    @tasks.loop(minutes=5)
    async def check_twitch(self):
        listed_streamer = await self.client.db.get_twitch_streams(guild=None)
        if not listed_streamer:
            return
        if not self.twitch_client.tokens:
            await self.twitch_client.login()
        all_streams = []
        if len(listed_streamer) > 100:
            sublist = []
            for index, l_stream in enumerate(listed_streamer):
                sublist.append(l_stream.streamer)
                if len(sublist) > 99:
                    streams = await self.twitch_client.fetch_streams(user_logins = sublist)
                    all_streams.extend(streams)
                    sublist.clear()
        else:
            streams = await self.twitch_client.fetch_streams(user_logins=[l.streamer for l in listed_streamer])
            all_streams.extend(streams)

        containers = []
        for stream in all_streams:
            if stream.user.name in self.live_streaming:
                continue
            self.live_streaming.append(stream.user.name)
            container = discord.ui.Container(color=discord.Color.from_rgb(156, 89, 182))
            t_display=discord.ui.TextDisplay(f"# **{stream.user.display_name}** is live on Twitch!\n\n"
                                             f"**{stream.title}**")
            container.add_section(t_display,
                                  accessory=discord.ui.Button(url=f"https://www.twitch.tv/{stream.user.name}", label="Stream", style=discord.ButtonStyle.link))

            container.add_separator()
            container.add_text(f"**Activity:** {stream.game_name if stream.game_name else 'Unknown'}\n"
                               f"**Stream start:** {discord.utils.format_dt(stream.started_at, style='R')}\n")

            preview_url = stream.thumbnail.url_for(1920, 1080)
            preview_item = discord.MediaGalleryItem(
                url=preview_url, description=f"Preview from {stream.user.name}'s Twitch Stream"
            )
            container.add_gallery(preview_item)
            containers.append(container)

        if not containers:
            return
        channels = await self.client.db.get_setting(
            SettingsEnum.SocialMediaChannel,
            None
        )
        if not channels:
            self.logger.warning("No social media channel set, cannot send Twitch announcements.")
            return
        elif isinstance(channels, Settings):
            channel = channels.value
            text_channel = await self.client.get_or_fetch(discord.TextChannel, channel, default=None)
            if text_channel:
                await text_channel.send(view=discord.ui.DesignerView(*containers))
        else:
            for channel in channels:
                text_channel = await self.client.get_or_fetch(discord.TextChannel, channel.value, default=None)
                if text_channel:
                    await text_channel.send(view=discord.ui.DesignerView(*containers))

def setup(client):
    client.add_cog(TwitchAnnouncer(client))

import discord
from discord.ext import commands, tasks
from discord.utils import get_or_fetch

from utils import Bot, CustomLogger
from utils.enums import SettingsEnum, WebhookType

TAGESSCHAU_IMAGE = "https://www.ard.de/static/media/appIcon.ts.b846aebc4c4b299d0fbd.jpg"


class InternalHooks(commands.Cog):
    def __init__(self, client):
        self.client: Bot = client
        self.logger = CustomLogger(self.qualified_name, self.client.boot_time)
        self.send_queue: list[tuple[discord.Embed, WebhookType]] = []
        self.webhooks = {}

    async def get_or_fetch_webhook(self, guild_id: int, channel_id: int) -> discord.Webhook:
        """
        Tries getting a webhook from the local cache. if this fails it fetches the webhooks from the discord channel and
         saves them to the cache.
        Args:
            guild_id: ``int`` The guild id of the channel you want to get the webhook for
            channel_id: ``int`` The channel id you want to get the webhooks from.

        Returns:
            ``discord.Webhook`` the webhook associated with this bot and the discord channel.
        """
        guild: discord.Guild = await get_or_fetch(self.client, "guild", guild_id, default=None)
        channel: discord.TextChannel = await get_or_fetch(guild, "channel", channel_id, default=None)
        if str(guild_id) not in self.webhooks:
            self.webhooks[str(guild_id)] = {}
        if self.webhooks[str(guild_id)].get(str(channel_id)):
            return self.webhooks[str(guild_id)][(str(channel_id))]
        hooks = await channel.webhooks()
        if f"{self.client.user.name} Webhook" in [hook.name for hook in hooks]:
            webhook = [hook for hook in hooks if hook.name == f"{self.client.user.name} Webhook"][0]
            self.webhooks[str(guild_id)][str(channel_id)] = webhook
        else:
            webhook = await channel.create_webhook(name=f"{self.client.user.name} Webhook")
            self.webhooks[str(guild_id)][str(channel_id)] = webhook
        return webhook

    @tasks.loop(minutes=1)
    async def send_news(self):
        if len(self.send_queue) <= 0:
            return

        sub_lists: dict[WebhookType, list[discord.Embed]] = {}
        rem_list = []
        for msg, rcv in self.send_queue:  # preparing the messages to send.
            message: discord.Embed = msg
            receiver: WebhookType = rcv
            if receiver not in sub_lists:
                sub_lists[receiver] = []
            if len(sub_lists[receiver]) >= 10:
                pass
            else:
                sub_lists[receiver].append(message)
                rem_list.append((message, receiver))

        [self.send_queue.remove(item) for item in rem_list]  # type: ignore

        if sub_lists[WebhookType.Tagesschau] is not None:
            resp = await self.client.db.get_global_setting(
                SettingsEnum.TagesschauChannel)  # get all guilds which want news
            for channel_id, guild_id in resp:  # type: ignore
                webhook = await self.get_or_fetch_webhook(guild_id, channel_id)
                await webhook.send(
                    embeds=sub_lists[WebhookType.Tagesschau],
                    username="Tagesschau",
                    avatar_url=TAGESSCHAU_IMAGE
                )

    @commands.Cog.listener("on_webhook_entry")
    async def on_webhook_entry(self, entries: list[tuple[discord.Embed, WebhookType]]):
        self.send_queue.extend(entries)
        self.logger.debug(f"{len(entries)} messages added to queue.")
        self.logger.debug(f"{len(self.send_queue)} messages in queue.")

    @commands.Cog.listener("on_start_done")
    async def start_done(self):
        self.send_news.start()


def setup(client):
    client.add_cog(InternalHooks(client))

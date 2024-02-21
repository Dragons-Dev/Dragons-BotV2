from typing import no_type_check

import discord
from discord.ext import commands
from discord.utils import get_or_fetch

from utils import Bot, CustomLogger
from utils.enums import SettingsEnum


class ModBackground(commands.Cog):
    def __init__(self, client):
        self.client: Bot = client
        self.logger = CustomLogger(self.qualified_name, self.client.boot_time)
        self.audit_webhooks = {}

    @no_type_check  # mypy isn't really happy with this so duck you mypy
    @commands.Cog.listener("on_audit_log_entry")
    async def audit_listener(self, entry: discord.AuditLogEntry):
        audit_channel = await self.client.db.get_setting(SettingsEnum.AuditLogChannel, entry.guild)
        audit_channel = await get_or_fetch(obj=entry.guild, attr="channel", id=audit_channel, default=None)
        try:
            audit_webhook = self.audit_webhooks[f"{audit_channel.guild.id}"]
        except KeyError:
            webhooks = await audit_channel.webhooks()
            for webhook in webhooks:
                if webhook.name == "Audit-Webhook":
                    self.audit_webhooks[f"{audit_channel.guild.id}"] = webhook
                    audit_webhook = webhook
                    break
            else:
                audit_webhook = await audit_channel.create_webhook(
                    name="Audit-Webhook", reason="Creating Audit-Webhook"
                )
                self.audit_webhooks[f"{audit_channel.guild.id}"] = audit_webhook

        await audit_webhook.send(
            content=entry.action,
            username=f"{self.client.user.name} Log",
            avatar_url=self.client.user.avatar.url,
        )

        match type(entry.target):
            case discord.Guild:
                self.logger.debug(f"Guild")

            case discord.VoiceChannel:
                self.logger.debug(f"VoiceChannel")

            case discord.StageChannel:
                self.logger.debug(f"StageChannel")

            case discord.ForumChannel:
                self.logger.debug(f"ForumChannel")

            case discord.CategoryChannel:
                self.logger.debug(f"CategoryChannel")

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
                self.logger.warning(f"Got unidentified target: {type(entry.target)}")


def setup(client):
    client.add_cog(ModBackground(client))

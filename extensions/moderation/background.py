import discord
from discord.ext import commands

from utils import Bot, CustomLogger
from utils.enums import SettingsEnum


class ModBackground(commands.Cog):
    def __init__(self, client):
        self.client: Bot = client
        self.logger = CustomLogger(self.qualified_name, self.client.boot)

    @commands.Cog.listener("on_audit_log_entry")
    async def audit_listener(self, entry: discord.AuditLogEntry):
        audit_channel = await self.client.db.get_setting(SettingsEnum.AuditLogChannel, entry.guild)
        audit_channel = self.client.get_channel(audit_channel)

        webhooks = await audit_channel.webhooks()  # type: ignore
        for webhook in webhooks:
            if webhook.name == "Audit-Webhook":
                hook = webhook
                break
        else:
            hook = await audit_channel.create_webhook(  # type: ignore
                name="Audit-Webhook", reason="Creating Audit-Webhook"
            )

        await hook.send(
            content=entry.action,
            username="TheDragons Audit-Log",
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

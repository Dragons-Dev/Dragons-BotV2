from collections.abc import Sequence
from datetime import datetime, timedelta
import typing as t

import discord
from discord.ext import commands
from discord.utils import format_dt

from utils import (
    Bot,
    ButtonInfo,
    CustomLogger,
    InfractionsEnum,
    SettingsEnum,
)

from .repository import InfractionsRepository

PAST_TENSE_ACTIONS = {
    InfractionsEnum.Ban: "banned",
    InfractionsEnum.Kick: "kicked",
    InfractionsEnum.Timeout: "timeouted",
    InfractionsEnum.Warn: "warned",
}


class ModerationEvents(commands.Cog):
    def __init__(self, client: Bot, infractions_repo: InfractionsRepository | None = None):
        self.client: Bot = client
        self.logger = CustomLogger(self.qualified_name, getattr(self.client, "boot_time", datetime.now()))
        if infractions_repo is not None:
            self.infractions_repo = infractions_repo
        elif hasattr(self.client, "db") and hasattr(self.client.db, "session_maker"):
            self.infractions_repo = InfractionsRepository(self.client.db.session_maker)
        else:
            self.infractions_repo = None  # type: ignore[assignment]

    async def _execute_discord_action(
        self,
        action: InfractionsEnum,
        member: discord.Member | discord.User,
        guild: discord.Guild,
        reason: str,
        **kwargs,
    ) -> bool:
        try:
            if action == InfractionsEnum.Ban:
                await guild.ban(member, reason=reason)
            elif action == InfractionsEnum.Kick:
                if hasattr(member, "kick"):
                    await member.kick(reason=reason)
                elif hasattr(guild, "kick"):
                    await guild.kick(member, reason=reason)
            elif action == InfractionsEnum.Timeout:
                duration: timedelta = kwargs["duration"]
                await member.timeout_for(duration=duration, reason=reason)
            elif action == InfractionsEnum.Warn:
                pass
            return True
        except (discord.Forbidden, discord.HTTPException) as e:
            self.logger.error(
                f"Failed to execute {action.value} on {member} in guild {guild.id}: {e}",
                exc_info=e,
            )
            return False

    def _build_moderation_embed(
        self,
        action: InfractionsEnum,
        member: discord.Member | discord.User,
        moderator: discord.Member | discord.User | discord.ClientUser,
        reason: str,
        case_id: int,
        **kwargs,
    ) -> discord.Embed:
        is_red = action in (InfractionsEnum.Ban, InfractionsEnum.Kick)
        color = discord.Color.brand_red() if is_red else discord.Color.yellow()
        title = kwargs.get("embed_title", action.value)

        embed = discord.Embed(title=title, color=color)
        embed.add_field(name="User", value=member.mention, inline=False)
        embed.add_field(name="Moderator", value=moderator.mention, inline=False)
        if action == InfractionsEnum.Timeout and "duration" in kwargs:
            embed.add_field(
                name="Until",
                value=format_dt(datetime.now() + kwargs["duration"], "R"),
                inline=False,
            )
        embed.add_field(name="Reason", value=kwargs.get("log_reason", reason), inline=False)
        embed.add_field(name="Date", value=format_dt(datetime.now(), "F"), inline=False)
        embed.set_footer(text=f"Case ID: {case_id}")
        return embed

    async def _send_dm(
        self,
        member: discord.Member | discord.User,
        embed: discord.Embed,
        **kwargs,
    ) -> None:
        if not hasattr(member, "send"):
            return
        dm_info_text = kwargs.get(
            "dm_info_text",
            "A copy of this was sent to the log channel and was stored in the database!",
        )
        view = ButtonInfo(dm_info_text)
        extra_embeds = kwargs.get("extra_embeds")
        try:
            if extra_embeds:
                await member.send(embeds=[embed, *extra_embeds], view=view)
            else:
                await member.send(embed=embed, view=view)
        except (discord.Forbidden, discord.HTTPException):
            pass

    async def _send_mod_log(
        self,
        guild: discord.Guild,
        embed: discord.Embed,
    ) -> None:
        if not hasattr(self.client, "db") or not hasattr(self.client.db, "get_setting"):
            return
        setting = await self.client.db.get_setting(setting=SettingsEnum.ModLogChannel, guild=guild)
        if not setting:
            return

        channel_id = setting[0].value if isinstance(setting, (tuple, list, Sequence)) else setting.value
        log_channel: discord.TextChannel | None = None
        if hasattr(guild, "get_or_fetch"):
            log_channel = await guild.get_or_fetch(discord.TextChannel, channel_id, default=None)
        elif hasattr(guild, "get_channel"):
            log_channel = guild.get_channel(channel_id)

        if log_channel:
            try:
                await log_channel.send(embed=embed)
            except (discord.Forbidden, discord.HTTPException) as e:
                self.logger.warning(
                    f"Failed to send mod log to channel {channel_id} in guild {guild.id}: {e}",
                    exc_info=e,
                )

    async def _send_ctx_response(
        self,
        ctx: discord.ApplicationContext,
        embed: discord.Embed,
        view: discord.ui.View | None = None,
        ephemeral: bool = True,
    ) -> None:
        is_done = False
        if hasattr(ctx, "response"):
            is_done_attr = getattr(ctx.response, "is_done", False)
            is_done = is_done_attr() if callable(is_done_attr) else bool(is_done_attr)

        send_kwargs: dict[str, t.Any] = {"embed": embed, "ephemeral": ephemeral}
        if view is not None:
            send_kwargs["view"] = view

        if is_done and hasattr(ctx, "followup"):
            await ctx.followup.send(**send_kwargs)
        elif hasattr(ctx, "response") and hasattr(ctx.response, "send_message"):
            await ctx.response.send_message(**send_kwargs)
        elif hasattr(ctx, "send"):
            await ctx.send(**send_kwargs)

    async def _send_moderator_feedback(
        self,
        ctx: discord.ApplicationContext,
        action: InfractionsEnum,
        member: discord.Member | discord.User,
        moderator: discord.Member | discord.User | discord.ClientUser,
        reason: str,
        case_id: int,
        **kwargs,
    ) -> None:
        mod_embed = discord.Embed(title=f"{action.value} successful", color=discord.Color.brand_green())
        mod_embed.add_field(name="User", value=member.mention, inline=False)
        mod_embed.add_field(name="Moderator", value=moderator.mention, inline=False)
        if action == InfractionsEnum.Timeout and "duration" in kwargs:
            mod_embed.add_field(
                name="Until",
                value=format_dt(datetime.now() + kwargs["duration"], "R"),
                inline=False,
            )
        mod_embed.add_field(name="Reason", value=reason, inline=False)
        mod_embed.add_field(name="Date", value=format_dt(datetime.now(), "F"), inline=False)
        mod_embed.set_footer(text=f"Case ID: {case_id}")

        target_name = PAST_TENSE_ACTIONS.get(action, f"{action.value.lower()}ed")
        view = ButtonInfo(
            kwargs.get(
                "mod_info_text",
                f"A copy of this was sent to the {target_name} member and the log channel!",
            )
        )
        await self._send_ctx_response(ctx, embed=mod_embed, view=view, ephemeral=True)

    @commands.Cog.listener("on_moderation_action")
    async def on_moderation_action(
        self,
        action: InfractionsEnum | str,
        member: discord.Member | discord.User,
        guild: discord.Guild,
        reason: str,
        moderator: discord.Member | discord.User | discord.ClientUser,
        **kwargs,
    ) -> int | None:
        if isinstance(action, str):
            try:
                action = InfractionsEnum(action.capitalize())
            except ValueError:
                action = InfractionsEnum(action)

        # 1. Create Database Infraction to obtain case_id
        case_id = await self.infractions_repo.create_infraction(
            user=member, infraction=action, reason=reason, guild=guild
        )

        # 2. Build Standardized Embeds
        embed = self._build_moderation_embed(action, member, moderator, reason, case_id, **kwargs)

        # 3. DM the Disciplined User before removal (Ban/Kick) while still in guild
        if action in (InfractionsEnum.Ban, InfractionsEnum.Kick):
            await self._send_dm(member, embed, **kwargs)

        # 4. Execute Discord Moderation Action
        success = await self._execute_discord_action(action, member, guild, reason, **kwargs)
        if not success:
            ctx = kwargs.get("ctx")
            if ctx is not None:
                err_embed = discord.Embed(
                    title=f"Failed to {action.value.lower()} user",
                    description=f"An error occurred while attempting to {action.value.lower()} {member.mention}.",
                    color=discord.Color.brand_red(),
                )
                await self._send_ctx_response(ctx, embed=err_embed, ephemeral=True)
            return None

        # DM disciplined user after successful action for non-removal actions (Timeout/Warn)
        if action not in (InfractionsEnum.Ban, InfractionsEnum.Kick):
            await self._send_dm(member, embed, **kwargs)

        # 5. Send to ModLogChannel
        await self._send_mod_log(guild, embed)

        # 6. Send Moderator Feedback (if ctx is provided in kwargs)
        ctx = kwargs.get("ctx")
        if ctx is not None:
            feedback_kwargs = {k: v for k, v in kwargs.items() if k != "ctx"}
            await self._send_moderator_feedback(ctx, action, member, moderator, reason, case_id, **feedback_kwargs)

        return case_id

    @commands.Cog.listener("on_moderation_ban")
    async def on_moderation_ban(
        self,
        member: discord.Member | discord.User,
        guild: discord.Guild,
        reason: str,
        moderator: discord.Member | discord.User | discord.ClientUser,
        **kwargs,
    ) -> int | None:
        return await self.on_moderation_action(InfractionsEnum.Ban, member, guild, reason, moderator, **kwargs)

    @commands.Cog.listener("on_moderation_kick")
    async def on_moderation_kick(
        self,
        member: discord.Member | discord.User,
        guild: discord.Guild,
        reason: str,
        moderator: discord.Member | discord.User | discord.ClientUser,
        **kwargs,
    ) -> int | None:
        return await self.on_moderation_action(InfractionsEnum.Kick, member, guild, reason, moderator, **kwargs)

    @commands.Cog.listener("on_moderation_timeout")
    async def on_moderation_timeout(
        self,
        member: discord.Member | discord.User,
        guild: discord.Guild,
        reason: str,
        moderator: discord.Member | discord.User | discord.ClientUser,
        **kwargs,
    ) -> int | None:
        return await self.on_moderation_action(InfractionsEnum.Timeout, member, guild, reason, moderator, **kwargs)

    @commands.Cog.listener("on_moderation_warn")
    async def on_moderation_warn(
        self,
        member: discord.Member | discord.User,
        guild: discord.Guild,
        reason: str,
        moderator: discord.Member | discord.User | discord.ClientUser,
        **kwargs,
    ) -> int | None:
        return await self.on_moderation_action(InfractionsEnum.Warn, member, guild, reason, moderator, **kwargs)


def setup(client: Bot):
    client.add_cog(ModerationEvents(client))

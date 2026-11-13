from collections.abc import Sequence
from datetime import datetime, timedelta, timezone
import inspect
import random
import re
from typing import Literal

import discord
from discord.ext import commands, tasks
from pycord import multicog as pycog

from utils import Bot, CustomLogger
from utils.enums import SettingsEnum

from .models import (
    MAX_BET_OPTIONS,
    BetOption,
    BetPool,
    BetWager,
    format_scales,
    get_dragon_scale_emoji,
    get_guild_id,
)
from .repository import EconomyRepository, GamblingRepository

__all__ = ["Gambling", "setup"]

SLOT_SYMBOLS = ["🍒", "🍋", "🔔", "💎", "🐉"]


def _calculate_slot_multiplier(symbols: list[str], dragon_symbol: str = "🐉") -> int:
    s1, s2, s3 = symbols
    if s1 == s2 == s3:
        return 10 if s1 in ("🐉", dragon_symbol) else 5
    if s1 == s2 or s2 == s3 or s1 == s3:
        return 2
    return 0


def _parse_bet_duration(text: str) -> timedelta | None:
    clean = text.strip().lower()
    if not clean:
        return None
    matches = re.findall(r"(\d+)\s*([smhdw])", clean)
    reconstructed = re.sub(r"(\d+)\s*([smhdw])", "", clean).strip()
    if reconstructed or not matches:
        return None
    multipliers = {"s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800}
    total_seconds = sum(int(amt) * multipliers[unit] for amt, unit in matches)
    if total_seconds <= 0:
        return None
    return timedelta(seconds=total_seconds)


def _parse_bet_options(text: str) -> list[str]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    seen: set[str] = set()
    result: list[str] = []
    for line in lines:
        if len(line) > 100:
            raise ValueError(f"Option '{line[:20]}...' exceeds maximum length of 100 characters.")
        key = line.casefold()
        if key not in seen:
            seen.add(key)
            result.append(line)
        if len(result) >= MAX_BET_OPTIONS:
            break
    return result


def _ensure_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _is_expired(locks_at: datetime | None) -> bool:
    if locks_at is None:
        return False
    return datetime.now(timezone.utc) >= _ensure_utc(locks_at)


def _get_embed_status_and_color(pool: BetPool) -> tuple[str, discord.Color]:
    if not pool.is_open:
        if pool.winning_option == "CANCELLED":
            return "❌ Cancelled", discord.Color.red()
        return f"🏆 Resolved (Winner: **{pool.winning_option}**)", discord.Color.green()
    if pool.is_locked:
        return "🔒 Wagering Locked", discord.Color.orange()
    return "🟢 Open for Wagers", discord.Color.gold()


def _format_pool_options_text(
    options: Sequence[BetOption],
    wagers: Sequence[BetWager],
    guild: discord.Guild | None,
    bot: Bot | None = None,
) -> str:
    if not options:
        return "*No options yet. Use '➕ Add Option & Bet' below to add the first option!*"
    opt_lines: list[str] = []
    for opt in options:
        opt_wagers = [w for w in wagers if w.choice.casefold() == opt.label.casefold()]
        opt_total = sum(w.amount for w in opt_wagers)
        bettor_count = len(opt_wagers)
        suffix = "bettors" if bettor_count != 1 else "bettor"
        opt_lines.append(f"• **{opt.label}**: {format_scales(opt_total, guild, bot)} ({bettor_count} {suffix})")
    return "\n".join(opt_lines)


def _add_resolution_field_if_closed(
    embed: discord.Embed,
    pool: BetPool,
    wagers: Sequence[BetWager],
    total_pool: int,
    guild: discord.Guild | None,
    bot: Bot | None = None,
) -> None:
    if pool.is_open or pool.winning_option == "CANCELLED":
        return
    win_wagers = [w for w in wagers if w.choice.casefold() == (pool.winning_option or "").casefold()]
    if not win_wagers:
        embed.add_field(
            name="Resolution",
            value=f"No participants wagered on **{pool.winning_option}**. All wagers were refunded!",
            inline=False,
        )
    else:
        embed.add_field(
            name="Resolution",
            value=f"{len(win_wagers)} winner(s) split the pool of {format_scales(total_pool, guild, bot)}!",
            inline=False,
        )


def _build_bet_embed(
    pool: BetPool,
    options: Sequence[BetOption],
    wagers: Sequence[BetWager],
    guild: discord.Guild | None,
    bot: Bot | None = None,
) -> discord.Embed:
    total_pool = sum(w.amount for w in wagers)
    status_text, color = _get_embed_status_and_color(pool)

    embed = discord.Embed(
        title=f"🎲 Bet Pool #{pool.id}: {pool.title}",
        color=color,
    )
    embed.add_field(name="Status", value=status_text, inline=True)
    embed.add_field(name="Creator", value=f"<@{pool.creator_id}>", inline=True)
    custom_text = "Allowed ✅" if pool.allow_custom_options else "Locked ❌"
    embed.add_field(name="Custom Options", value=custom_text, inline=True)

    if pool.locks_at:
        ts = int(_ensure_utc(pool.locks_at).timestamp())
        embed.add_field(name="Locks At", value=f"<t:{ts}:R> (<t:{ts}:f>)", inline=False)

    options_value = _format_pool_options_text(options, wagers, guild, bot)
    embed.add_field(name="Options", value=options_value, inline=False)
    embed.add_field(name="Total Pool", value=format_scales(total_pool, guild, bot), inline=False)

    _add_resolution_field_if_closed(embed, pool, wagers, total_pool, guild, bot)
    return embed


def _build_bet_pool_view(cog: "Gambling", pool: BetPool, options: Sequence[BetOption]) -> discord.ui.View:
    return BetPoolView(cog, pool, options)


class BetOptionSelect(discord.ui.Select):
    def __init__(self, cog: "Gambling", pool_id: int, options: Sequence[BetOption]):
        self.cog = cog
        self.pool_id = pool_id
        select_options = [
            discord.SelectOption(label=opt.label[:100], value=opt.label[:100]) for opt in options[:MAX_BET_OPTIONS]
        ]
        super().__init__(
            placeholder="Select an option to place a bet...",
            min_values=1,
            max_values=1,
            options=select_options,
            custom_id=f"bet_opt_select_{pool_id}",
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(PlaceWagerModal(self.cog, self.pool_id, self.values[0]))


class AddOptionButton(discord.ui.Button):
    def __init__(self, cog: "Gambling", pool_id: int):
        self.cog = cog
        self.pool_id = pool_id
        super().__init__(
            label="➕ Add Option & Bet",
            style=discord.ButtonStyle.primary,
            custom_id=f"bet_add_opt_{pool_id}",
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(AddCustomOptionModal(self.cog, self.pool_id))


class LockButton(discord.ui.Button):
    def __init__(self, cog: "Gambling", pool_id: int, creator_id: int):
        self.cog = cog
        self.pool_id = pool_id
        self.creator_id = creator_id
        super().__init__(
            label="🔒 Lock Bets",
            style=discord.ButtonStyle.secondary,
            custom_id=f"bet_lock_{pool_id}",
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        if not await self.cog._is_authorized_resolver(interaction, self.creator_id):
            await interaction.response.send_message(
                "Only the creator or a team member can lock this bet.",
                ephemeral=True,
            )
            return
        guild_id = get_guild_id(interaction)
        success = await self.cog.gambling_repo.lock_bet_pool(self.pool_id, guild_id)
        if not success:
            await interaction.response.send_message(
                "Bet pool could not be locked (may already be locked or closed).",
                ephemeral=True,
            )
            return
        await interaction.response.send_message("Betting is now locked for this pool.", ephemeral=True)
        await self.cog._update_bet_message(self.pool_id, guild_id)


class ResolveButton(discord.ui.Button):
    def __init__(self, cog: "Gambling", pool_id: int, creator_id: int, options: Sequence[BetOption]):
        self.cog = cog
        self.pool_id = pool_id
        self.creator_id = creator_id
        self.options = options
        super().__init__(
            label="🏆 Resolve",
            style=discord.ButtonStyle.success,
            custom_id=f"bet_resolve_{pool_id}",
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        if not await self.cog._is_authorized_resolver(interaction, self.creator_id):
            await interaction.response.send_message(
                "Only the creator or a team member can resolve this bet.",
                ephemeral=True,
            )
            return
        pool_options = await self.cog.gambling_repo.get_pool_options(self.pool_id)
        await interaction.response.send_message(
            "Select the winning option or enter a custom outcome:",
            view=ResolveBetView(self.cog, self.pool_id, pool_options),
            ephemeral=True,
        )


class CancelButton(discord.ui.Button):
    def __init__(self, cog: "Gambling", pool_id: int, creator_id: int):
        self.cog = cog
        self.pool_id = pool_id
        self.creator_id = creator_id
        super().__init__(
            label="❌ Cancel",
            style=discord.ButtonStyle.danger,
            custom_id=f"bet_cancel_{pool_id}",
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        if not await self.cog._is_authorized_resolver(interaction, self.creator_id):
            await interaction.response.send_message(
                "Only the creator or a team member can cancel this bet.",
                ephemeral=True,
            )
            return
        guild_id = get_guild_id(interaction)
        success = await self.cog.gambling_repo.cancel_bet_pool(self.pool_id, guild_id)
        if not success:
            await interaction.response.send_message(
                "Bet pool could not be cancelled (may already be closed).",
                ephemeral=True,
            )
            return
        await interaction.response.send_message("Bet pool cancelled and all wagers refunded.", ephemeral=True)
        await self.cog._update_bet_message(self.pool_id, guild_id)


class BetPoolView(discord.ui.View):
    def __init__(self, cog: "Gambling", pool: BetPool, options: Sequence[BetOption]):
        super().__init__(timeout=None)
        self.cog = cog
        self.pool = pool
        self.options = options
        self._add_components()

    def _add_components(self) -> None:
        if self.pool.is_open and not self.pool.is_locked:
            if self.options:
                self.add_item(BetOptionSelect(self.cog, self.pool.id, self.options))
            if self.pool.allow_custom_options and len(self.options) < MAX_BET_OPTIONS:
                self.add_item(AddOptionButton(self.cog, self.pool.id))
            self.add_item(LockButton(self.cog, self.pool.id, self.pool.creator_id))
            self.add_item(ResolveButton(self.cog, self.pool.id, self.pool.creator_id, self.options))
            self.add_item(CancelButton(self.cog, self.pool.id, self.pool.creator_id))
        elif self.pool.is_open and self.pool.is_locked:
            self.add_item(ResolveButton(self.cog, self.pool.id, self.pool.creator_id, self.options))
            self.add_item(CancelButton(self.cog, self.pool.id, self.pool.creator_id))


class ResolveBetView(discord.ui.View):
    def __init__(self, cog: "Gambling", pool_id: int, options: Sequence[BetOption]):
        super().__init__(timeout=180)
        self.cog = cog
        self.pool_id = pool_id
        if options:
            self.add_item(ResolveOptionSelect(cog, pool_id, options))
        self.add_item(CustomOutcomeButton(cog, pool_id))


class ResolveOptionSelect(discord.ui.Select):
    def __init__(self, cog: "Gambling", pool_id: int, options: Sequence[BetOption]):
        self.cog = cog
        self.pool_id = pool_id
        select_options = [
            discord.SelectOption(label=opt.label[:100], value=opt.label[:100]) for opt in options[:MAX_BET_OPTIONS]
        ]
        super().__init__(
            placeholder="Select winning option...",
            min_values=1,
            max_values=1,
            options=select_options,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        await self.cog._handle_resolve(interaction, self.pool_id, self.values[0])


class CustomOutcomeButton(discord.ui.Button):
    def __init__(self, cog: "Gambling", pool_id: int):
        self.cog = cog
        self.pool_id = pool_id
        super().__init__(
            label="📝 Custom / Other Outcome",
            style=discord.ButtonStyle.primary,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(CustomOutcomeModal(self.cog, self.pool_id))


class CustomOutcomeModal(discord.ui.Modal):
    def __init__(self, cog: "Gambling", pool_id: int):
        super().__init__(title="Custom Winning Outcome")
        self.cog = cog
        self.pool_id = pool_id
        self.outcome_input = discord.ui.InputText(
            label="Winning Outcome",
            placeholder="e.g. Draw, Overtime, No Result",
            max_length=100,
            required=True,
        )
        self.add_item(self.outcome_input)

    async def callback(self, interaction: discord.Interaction) -> None:
        clean = self.outcome_input.value.strip()
        if not clean:
            await interaction.response.send_message("Outcome cannot be empty.", ephemeral=True)
            return
        await self.cog._handle_resolve(interaction, self.pool_id, clean)


class PlaceWagerModal(discord.ui.Modal):
    def __init__(self, cog: "Gambling", pool_id: int, option_label: str):
        super().__init__(title=f"Bet on: {option_label[:20]}")
        self.cog = cog
        self.pool_id = pool_id
        self.option_label = option_label
        self.amount_input = discord.ui.InputText(
            label="Wager Amount (Dragon Scales)",
            placeholder="Enter an amount greater than 0",
            min_length=1,
            max_length=15,
            required=True,
        )
        self.add_item(self.amount_input)

    async def callback(self, interaction: discord.Interaction) -> None:
        try:
            amount = int(self.amount_input.value.strip())
        except ValueError:
            await interaction.response.send_message("Wager amount must be a valid integer.", ephemeral=True)
            return
        if amount <= 0:
            await interaction.response.send_message("Wager amount must be greater than 0.", ephemeral=True)
            return

        guild_id = get_guild_id(interaction)
        pool = await self.cog.gambling_repo.get_bet_pool(self.pool_id, guild_id)
        if pool is None or not pool.is_open:
            await interaction.response.send_message("This bet pool is closed or does not exist.", ephemeral=True)
            return
        if pool.is_locked or _is_expired(pool.locks_at):
            await interaction.response.send_message("Wagering has closed for this bet pool.", ephemeral=True)
            await self.cog._update_bet_message(self.pool_id, guild_id)
            return

        wagers = await self.cog.gambling_repo.get_pool_wagers(self.pool_id, guild_id)
        user_wager = next((w for w in wagers if w.user_id == interaction.user.id), None)
        if user_wager and user_wager.choice.casefold() != self.option_label.casefold():
            await interaction.response.send_message(
                f"You have already wagered on '{user_wager.choice}'. You cannot bet on multiple options.",
                ephemeral=True,
            )
            return

        bal = await self.cog.economy_repo.get_balance(interaction.user.id, guild_id)
        if bal < amount:
            await interaction.response.send_message(
                f"You do not have enough Dragon Scales. "
                f"Current balance: {format_scales(bal, interaction.guild, self.cog.client)}.",
                ephemeral=True,
            )
            return

        success = await self.cog.gambling_repo.place_wager(
            self.pool_id, interaction.user.id, guild_id, self.option_label, amount
        )
        if not success:
            await interaction.response.send_message("Failed to place wager. Please try again.", ephemeral=True)
            return

        await interaction.response.send_message(
            f"Successfully wagered **{format_scales(amount, interaction.guild, self.cog.client)}** "
            f"on **{self.option_label}**!",
            ephemeral=True,
        )
        await self.cog._update_bet_message(self.pool_id, guild_id)


class AddCustomOptionModal(discord.ui.Modal):
    def __init__(self, cog: "Gambling", pool_id: int):
        super().__init__(title="Add Option & Place Wager")
        self.cog = cog
        self.pool_id = pool_id
        self.label_input = discord.ui.InputText(
            label="Option Label",
            placeholder="Enter option description (max 100 chars)",
            max_length=100,
            required=True,
        )
        self.amount_input = discord.ui.InputText(
            label="Wager Amount (Dragon Scales)",
            placeholder="Enter an amount greater than 0",
            min_length=1,
            max_length=15,
            required=True,
        )
        self.add_item(self.label_input)
        self.add_item(self.amount_input)

    async def callback(self, interaction: discord.Interaction) -> None:
        clean_label = self.label_input.value.strip()
        if not clean_label or len(clean_label) > 100:
            await interaction.response.send_message(
                "Option label must be between 1 and 100 characters.", ephemeral=True
            )
            return

        try:
            amount = int(self.amount_input.value.strip())
        except ValueError:
            await interaction.response.send_message("Wager amount must be a valid integer.", ephemeral=True)
            return
        if amount <= 0:
            await interaction.response.send_message("Wager amount must be greater than 0.", ephemeral=True)
            return

        guild_id = get_guild_id(interaction)
        success_opt, opt, msg = await self.cog.gambling_repo.add_bet_option(
            self.pool_id, guild_id, interaction.user.id, clean_label
        )
        if not success_opt or opt is None:
            await interaction.response.send_message(msg, ephemeral=True)
            return

        wagers = await self.cog.gambling_repo.get_pool_wagers(self.pool_id, guild_id)
        user_wager = next((w for w in wagers if w.user_id == interaction.user.id), None)
        if user_wager and user_wager.choice.casefold() != opt.label.casefold():
            await interaction.response.send_message(
                f"You have already wagered on '{user_wager.choice}'. You cannot bet on multiple options.",
                ephemeral=True,
            )
            return

        bal = await self.cog.economy_repo.get_balance(interaction.user.id, guild_id)
        if bal < amount:
            await interaction.response.send_message(
                f"You do not have enough Dragon Scales. "
                f"Current balance: {format_scales(bal, interaction.guild, self.cog.client)}.",
                ephemeral=True,
            )
            return

        success_wager = await self.cog.gambling_repo.place_wager(
            self.pool_id, interaction.user.id, guild_id, opt.label, amount
        )
        if not success_wager:
            await interaction.response.send_message("Failed to place wager on option.", ephemeral=True)
            return

        await interaction.response.send_message(
            f"Successfully added option **{opt.label}** and wagered "
            f"**{format_scales(amount, interaction.guild, self.cog.client)}**!",
            ephemeral=True,
        )
        await self.cog._update_bet_message(self.pool_id, guild_id)


class BetCreateModal(discord.ui.Modal):
    def __init__(self, cog: "Gambling"):
        super().__init__(title="Create Prediction Bet")
        self.cog = cog
        self.title_input = discord.ui.InputText(
            label="Bet Title / Question",
            placeholder="e.g. Who will win the dragon race?",
            max_length=200,
            required=True,
        )
        self.options_input = discord.ui.InputText(
            label="Initial Options (one per line, optional)",
            style=discord.InputTextStyle.paragraph,
            placeholder="Red Dragon\nBlue Dragon\nGreen Dragon",
            max_length=2000,
            required=False,
        )
        self.duration_input = discord.ui.InputText(
            label="Auto-Lock Duration (e.g. 30m, 2h, 1d)",
            placeholder="Optional duration, e.g. 30m, 2h, 1d",
            max_length=20,
            required=False,
        )
        self.add_item(self.title_input)
        self.add_item(self.options_input)
        self.add_item(self.duration_input)

    async def callback(self, interaction: discord.Interaction) -> None:
        title = self.title_input.value.strip()
        if not title:
            await interaction.response.send_message("Bet title cannot be empty.", ephemeral=True)
            return

        try:
            options = _parse_bet_options(self.options_input.value or "")
        except ValueError as e:
            await interaction.response.send_message(str(e), ephemeral=True)
            return

        duration_str = (self.duration_input.value or "").strip()
        duration: timedelta | None = None
        if duration_str:
            duration = _parse_bet_duration(duration_str)
            if duration is None:
                await interaction.response.send_message(
                    f"Invalid duration '{duration_str}'. Use formats like 30m, 2h, 1d, 1w.",
                    ephemeral=True,
                )
                return

        view = BetSetupView(self.cog, title, options, duration)
        embed = view.build_preview_embed(interaction.guild)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


class BetSetupView(discord.ui.View):
    def __init__(
        self,
        cog: "Gambling",
        title: str,
        options: list[str],
        duration: timedelta | None,
    ):
        super().__init__(timeout=300)
        self.cog = cog
        self.title = title
        self.options = options
        self.duration = duration
        self.allow_custom = True
        self._update_buttons()

    def _update_buttons(self) -> None:
        self.clear_items()
        toggle_label = "Custom Options: Allowed ✅" if self.allow_custom else "Custom Options: Locked ❌"
        toggle_style = discord.ButtonStyle.success if self.allow_custom else discord.ButtonStyle.secondary
        toggle_btn = discord.ui.Button(
            label=toggle_label,
            style=toggle_style,
            disabled=(len(self.options) == 0),
        )
        toggle_btn.callback = self._on_toggle_custom
        self.add_item(toggle_btn)

        publish_btn = discord.ui.Button(label="Publish Bet 🚀", style=discord.ButtonStyle.primary)
        publish_btn.callback = self._on_publish
        self.add_item(publish_btn)

        cancel_btn = discord.ui.Button(label="Cancel", style=discord.ButtonStyle.secondary)
        cancel_btn.callback = self._on_cancel
        self.add_item(cancel_btn)

    def build_preview_embed(self, guild: discord.Guild | None) -> discord.Embed:
        embed = discord.Embed(
            title=f"Preview: {self.title}",
            description="Review your bet settings before publishing to the channel.",
            color=discord.Color.blue(),
        )
        if self.options:
            opts_str = "\n".join(f"{i + 1}. {opt}" for i, opt in enumerate(self.options))
        else:
            opts_str = "*No initial options. Participants can add options after publishing.*"
        embed.add_field(name="Initial Options", value=opts_str, inline=False)
        embed.add_field(
            name="Custom Options",
            value="Allowed" if self.allow_custom else "Locked",
            inline=True,
        )
        duration_desc = f"{int(self.duration.total_seconds() // 60)} minutes" if self.duration else "None (Manual Lock)"
        embed.add_field(name="Auto-Lock", value=duration_desc, inline=True)
        return embed

    async def _on_toggle_custom(self, interaction: discord.Interaction) -> None:
        if len(self.options) == 0:
            await interaction.response.send_message(
                "Custom options must be allowed when starting with 0 options.",
                ephemeral=True,
            )
            return
        self.allow_custom = not self.allow_custom
        self._update_buttons()
        embed = self.build_preview_embed(interaction.guild)
        await interaction.response.edit_message(embed=embed, view=self)

    async def _on_publish(self, interaction: discord.Interaction) -> None:
        guild_id = get_guild_id(interaction)
        locks_at = datetime.now(timezone.utc) + self.duration if self.duration else None

        pool = await self.cog.gambling_repo.create_bet_pool(
            guild_id=guild_id,
            creator_id=interaction.user.id,
            title=self.title,
            options=self.options,
            allow_custom_options=self.allow_custom,
            locks_at=locks_at,
        )
        options = await self.cog.gambling_repo.get_pool_options(pool.id)
        embed = _build_bet_embed(pool, options, [], interaction.guild, self.cog.client)
        view = _build_bet_pool_view(self.cog, pool, options)

        channel = interaction.channel
        if channel is None or not hasattr(channel, "send"):
            await interaction.response.send_message("Could not access channel to send bet.", ephemeral=True)
            return

        msg = await channel.send(embed=embed, view=view)
        await self.cog.gambling_repo.set_pool_message(pool.id, guild_id, channel.id, msg.id)

        jump_url = getattr(msg, "jump_url", "")
        jump_link = f" [Jump to Bet]({jump_url})" if jump_url else ""
        await interaction.response.edit_message(
            content=f"Bet Pool #{pool.id} published successfully!{jump_link}",
            embed=None,
            view=None,
        )

    async def _on_cancel(self, interaction: discord.Interaction) -> None:
        await interaction.response.edit_message(
            content="Bet creation cancelled.",
            embed=None,
            view=None,
        )


class Gambling(commands.Cog):
    """Cog handling gambling mini-games and custom prediction bet pools."""

    def __init__(
        self,
        client: Bot,
        gambling_repo: GamblingRepository | None = None,
        economy_repo: EconomyRepository | None = None,
    ):
        self.client: Bot = client
        self.logger = CustomLogger(self.qualified_name, self.client.boot_time)
        self.gambling_repo = gambling_repo or GamblingRepository(self.client.db.session_maker)
        self.economy_repo = economy_repo or EconomyRepository(self.client.db.session_maker)

    def cog_unload(self) -> None:
        if self.auto_lock_task.is_running():
            self.auto_lock_task.cancel()

    @commands.Cog.listener("on_start_done")
    async def on_start_done(self) -> None:
        if not self.auto_lock_task.is_running():
            self.auto_lock_task.start()
        await self._register_persistent_views()

    async def _register_persistent_views(self) -> None:
        try:
            open_pools = await self.gambling_repo.get_all_open_bet_pools()
            for pool in open_pools:
                if pool.message_id is not None:
                    options = await self.gambling_repo.get_pool_options(pool.id)
                    view = _build_bet_pool_view(self, pool, options)
                    self.client.add_view(view, message_id=pool.message_id)
        except Exception as e:
            self.logger.error(f"Error registering persistent bet pool views: {e}")

    @tasks.loop(seconds=30)
    async def auto_lock_task(self) -> None:
        try:
            expired_pools = await self.gambling_repo.auto_lock_expired_pools()
            for pool in expired_pools:
                await self._update_bet_message(pool.id, pool.guild_id)
        except Exception as e:
            self.logger.error(f"Error in auto_lock_task: {e}")

    @auto_lock_task.before_loop
    async def before_auto_lock_task(self) -> None:
        wait_ready = getattr(self.client, "wait_until_ready", None)
        if callable(wait_ready):
            res = wait_ready()
            if inspect.isawaitable(res):
                await res

    async def _deduct_or_notify(self, ctx: discord.ApplicationContext, amount: int) -> bool:
        if amount <= 0:
            await ctx.response.send_message("The bet amount must be greater than 0.", ephemeral=True)
            return False
        guild_id = get_guild_id(ctx)
        success = await self.economy_repo.remove_balance(ctx.author.id, guild_id, amount)
        if not success:
            bal = await self.economy_repo.get_balance(ctx.author.id, guild_id)
            await ctx.response.send_message(
                f"You do not have enough Dragon Scales. Current balance: {format_scales(bal, ctx.guild, self.client)}.",
                ephemeral=True,
            )
            return False
        return True

    async def _is_authorized_resolver(
        self,
        ctx_or_interaction: discord.ApplicationContext | discord.Interaction,
        creator_id: int,
    ) -> bool:
        user = (
            ctx_or_interaction.user
            if isinstance(ctx_or_interaction, discord.Interaction)
            else ctx_or_interaction.author
        )
        if user.id == creator_id:
            return True
        guild_perms = getattr(user, "guild_permissions", None)
        if guild_perms and getattr(guild_perms, "administrator", False):
            return True

        guild = ctx_or_interaction.guild
        if guild is not None and hasattr(self.client, "db") and self.client.db:
            team_setting = await self.client.db.get_setting(SettingsEnum.TeamRole, guild)
            if team_setting is not None:
                role_id = getattr(team_setting, "value", None)
                roles = getattr(user, "roles", [])
                if role_id and any(getattr(r, "id", None) == role_id for r in roles):
                    return True
        return False

    async def _handle_resolve(
        self,
        interaction: discord.Interaction,
        pool_id: int,
        winning_choice: str,
    ) -> None:
        guild_id = get_guild_id(interaction)
        payouts = await self.gambling_repo.resolve_bet_pool(pool_id, guild_id, winning_choice)
        if payouts is None:
            await interaction.response.send_message(
                f"Bet pool #{pool_id} could not be resolved or was already closed.",
                ephemeral=True,
            )
            return

        if not payouts:
            await interaction.response.send_message(
                f"Resolved Bet #{pool_id} with outcome **{winning_choice}**.\n"
                "No participants wagered on this outcome, so all wagers have been refunded!",
                ephemeral=True,
            )
        else:
            total_distributed = sum(payouts.values())
            await interaction.response.send_message(
                f"Resolved Bet #{pool_id} with outcome **{winning_choice}**!\n"
                f"Distributed **{format_scales(total_distributed, interaction.guild, self.client)}** "
                f"to {len(payouts)} winner(s).",
                ephemeral=True,
            )
        await self._update_bet_message(pool_id, guild_id)

    async def _update_bet_message(self, pool_id: int, guild_id: int) -> None:
        pool = await self.gambling_repo.get_bet_pool(pool_id, guild_id)
        if pool is None or not pool.channel_id or not pool.message_id:
            return
        options = await self.gambling_repo.get_pool_options(pool.id)
        wagers = await self.gambling_repo.get_pool_wagers(pool.id, guild_id)

        try:
            channel = self.client.get_channel(pool.channel_id)
            if channel is None:
                channel = await self.client.fetch_channel(pool.channel_id)
            guild = getattr(channel, "guild", None)
            msg = await channel.fetch_message(pool.message_id)  # type: ignore[union-attr]
            embed = _build_bet_embed(pool, options, wagers, guild, self.client)
            view = _build_bet_pool_view(self, pool, options)
            await msg.edit(embed=embed, view=view)
        except Exception as e:
            self.logger.debug(f"Could not update bet message for pool #{pool_id}: {e}")

    @pycog.subcommand("gamble")
    @commands.slash_command(name="coinflip", description="Bet Dragon Scales on a coin flip.")
    @discord.option("choice", input_type=str, description="Heads or tails", choices=["heads", "tails"])
    @discord.option("amount", input_type=int, description="The amount of Dragon Scales to bet", min_value=1)
    async def coinflip(
        self,
        ctx: discord.ApplicationContext,
        choice: Literal["heads", "tails"],
        amount: int,
    ) -> None:
        if not await self._deduct_or_notify(ctx, amount):
            return

        guild_id = get_guild_id(ctx)
        flip = random.choice(["heads", "tails"])
        won = choice.lower() == flip
        if won:
            payout = amount * 2
            await self.economy_repo.add_balance(ctx.author.id, guild_id, payout)
            new_bal = await self.economy_repo.get_balance(ctx.author.id, guild_id)
            embed = discord.Embed(
                title="🪙 Coinflip — Winner!",
                description=(
                    f"The coin landed on **{flip}**!\n"
                    f"You won **{format_scales(payout, ctx.guild, self.client)}**!\n"
                    f"New balance: {format_scales(new_bal, ctx.guild, self.client)}."
                ),
                color=discord.Color.green(),
            )
        else:
            new_bal = await self.economy_repo.get_balance(ctx.author.id, guild_id)
            embed = discord.Embed(
                title="🪙 Coinflip — Lost",
                description=(
                    f"The coin landed on **{flip}**.\n"
                    f"You lost **{format_scales(amount, ctx.guild, self.client)}**.\n"
                    f"New balance: {format_scales(new_bal, ctx.guild, self.client)}."
                ),
                color=discord.Color.red(),
            )
        await ctx.response.send_message(embed=embed)

    @pycog.subcommand("gamble")
    @commands.slash_command(name="dice", description="Bet Dragon Scales on a 6-sided dice roll.")
    @discord.option("guess", input_type=int, description="Your dice guess (1 to 6)", min_value=1, max_value=6)
    @discord.option("amount", input_type=int, description="The amount of Dragon Scales to bet", min_value=1)
    async def dice(
        self,
        ctx: discord.ApplicationContext,
        guess: int,
        amount: int,
    ) -> None:
        if not (1 <= guess <= 6):
            await ctx.response.send_message("Your guess must be between 1 and 6.", ephemeral=True)
            return

        if not await self._deduct_or_notify(ctx, amount):
            return

        guild_id = get_guild_id(ctx)
        roll = random.randint(1, 6)
        won = guess == roll
        if won:
            payout = amount * 6
            await self.economy_repo.add_balance(ctx.author.id, guild_id, payout)
            new_bal = await self.economy_repo.get_balance(ctx.author.id, guild_id)
            embed = discord.Embed(
                title="🎲 Dice Roll — Winner!",
                description=(
                    f"The die rolled a **{roll}**!\n"
                    f"You won **{format_scales(payout, ctx.guild, self.client)}**!\n"
                    f"New balance: {format_scales(new_bal, ctx.guild, self.client)}."
                ),
                color=discord.Color.green(),
            )
        else:
            new_bal = await self.economy_repo.get_balance(ctx.author.id, guild_id)
            embed = discord.Embed(
                title="🎲 Dice Roll — Lost",
                description=(
                    f"The die rolled a **{roll}** (your guess: {guess}).\n"
                    f"You lost **{format_scales(amount, ctx.guild, self.client)}**.\n"
                    f"New balance: {format_scales(new_bal, ctx.guild, self.client)}."
                ),
                color=discord.Color.red(),
            )
        await ctx.response.send_message(embed=embed)

    @pycog.subcommand("gamble")
    @commands.slash_command(name="slots", description="Bet Dragon Scales on the slot machine.")
    @discord.option("amount", input_type=int, description="The amount of Dragon Scales to bet", min_value=1)
    async def slots(
        self,
        ctx: discord.ApplicationContext,
        amount: int,
    ) -> None:
        if not await self._deduct_or_notify(ctx, amount):
            return

        guild_id = get_guild_id(ctx)
        dragon_emoji = get_dragon_scale_emoji(ctx.guild, self.client)
        slot_symbols = [dragon_emoji if s == "🐉" else s for s in SLOT_SYMBOLS]
        raw_symbols = random.choices(slot_symbols, k=3)
        symbols = [dragon_emoji if s == "🐉" else s for s in raw_symbols]
        multiplier = _calculate_slot_multiplier(symbols, dragon_emoji)
        slot_display = f"[ {' | '.join(symbols)} ]"

        if multiplier > 0:
            payout = amount * multiplier
            await self.economy_repo.add_balance(ctx.author.id, guild_id, payout)
            new_bal = await self.economy_repo.get_balance(ctx.author.id, guild_id)
            embed = discord.Embed(
                title="🎰 Slots — Winner!",
                description=(
                    f"**{slot_display}**\n\n"
                    f"Multiplier: **{multiplier}x**!\n"
                    f"You won **{format_scales(payout, ctx.guild, self.client)}**!\n"
                    f"New balance: {format_scales(new_bal, ctx.guild, self.client)}."
                ),
                color=discord.Color.green(),
            )
        else:
            new_bal = await self.economy_repo.get_balance(ctx.author.id, guild_id)
            embed = discord.Embed(
                title="🎰 Slots — Lost",
                description=(
                    f"**{slot_display}**\n\n"
                    "No matching symbols.\n"
                    f"You lost **{format_scales(amount, ctx.guild, self.client)}**.\n"
                    f"New balance: {format_scales(new_bal, ctx.guild, self.client)}."
                ),
                color=discord.Color.red(),
            )
        await ctx.response.send_message(embed=embed)

    @pycog.subcommand("gamble")
    @commands.slash_command(name="bet", description="Create a new prediction bet pool.")
    async def bet(self, ctx: discord.ApplicationContext) -> None:
        modal = BetCreateModal(self)
        await ctx.response.send_modal(modal)

    @pycog.subcommand("gamble")
    @commands.slash_command(name="bet_list", description="List all open prediction bet pools.")
    async def bet_list(self, ctx: discord.ApplicationContext) -> None:
        guild_id = get_guild_id(ctx)
        pools = await self.gambling_repo.get_open_bet_pools(guild_id)
        if not pools:
            await ctx.response.send_message("There are currently no open bet pools in this server.", ephemeral=True)
            return

        embed = discord.Embed(
            title="Active Prediction Bet Pools",
            color=discord.Color.gold(),
        )
        for pool in pools[:10]:
            wagers = await self.gambling_repo.get_pool_wagers(pool.id, guild_id)
            total_pool = sum(w.amount for w in wagers)
            status_icon = "🔒 Locked" if pool.is_locked else "🟢 Open"
            jump = ""
            if pool.channel_id and pool.message_id:
                jump = f" • [Jump to Bet](https://discord.com/channels/{guild_id}/{pool.channel_id}/{pool.message_id})"

            embed.add_field(
                name=f"#{pool.id}: {pool.title}",
                value=(
                    f"Status: **{status_icon}** • Total Pool: **{format_scales(total_pool, ctx.guild, self.client)}**"
                    f"{jump}"
                ),
                inline=False,
            )
        if len(pools) > 10:
            embed.set_footer(text=f"Showing 10 of {len(pools)} open bet pools.")
        await ctx.response.send_message(embed=embed, ephemeral=True)


def setup(client: Bot) -> None:
    client.add_cog(Gambling(client))

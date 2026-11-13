from datetime import datetime
from typing import Any

import discord
from sqlalchemy import BigInteger, Boolean, DateTime, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from utils.orm_database.models import Base

__all__ = [
    "MAX_BET_OPTIONS",
    "BetOption",
    "BetPool",
    "BetWager",
    "EconomyWallet",
    "format_scales",
    "get_dragon_scale_emoji",
    "get_guild_id",
]

MAX_BET_OPTIONS: int = 25


def get_guild_id(ctx: discord.ApplicationContext | discord.Interaction) -> int:
    guild = ctx.guild
    if guild is None:
        return 0
    return guild.id


def get_dragon_scale_emoji(guild: discord.Guild | None = None, bot: Any | None = None) -> str:
    """
    Resolve the Dragon Scale emoji using guild override -> global app emoji -> Unicode fallback.

    :param guild: Discord guild to check for custom dragon_scale emoji
    :param bot: Bot instance containing cached application emojis
    :return: Emoji string (e.g. '<:dragon_scale:123>' or '🐉')
    """
    if guild is not None and hasattr(guild, "emojis") and guild.emojis:
        custom_emoji = discord.utils.get(guild.emojis, name="dragon_scale")
        if custom_emoji is not None:
            return str(custom_emoji)

    if bot is not None:
        app_emojis = getattr(bot, "app_emojis", None)
        if isinstance(app_emojis, dict):
            app_emoji = app_emojis.get("dragon_scale")
            if isinstance(app_emoji, str) and app_emoji:
                return app_emoji

    return "🐉"


def format_scales(amount: int, guild: discord.Guild | None = None, bot: Any | None = None) -> str:
    """
    Format an amount of Dragon Scales with custom guild/app emoji or fallback.

    :param amount: Amount of Dragon Scales
    :param guild: Discord guild to check for custom dragon_scale emoji
    :param bot: Bot instance to check for global application dragon_scale emoji
    :return: Formatted string (e.g. '1,000 🐉 Dragon Scales')
    """
    emoji = get_dragon_scale_emoji(guild, bot)
    suffix = "Dragon Scale" if amount == 1 else "Dragon Scales"
    return f"{amount:,} {emoji} {suffix}"


class EconomyWallet(Base):
    """Database model for user economy balances."""

    __tablename__ = "economy_wallets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    guild_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    balance: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)

    __table_args__ = (UniqueConstraint("user_id", "guild_id", name="_user_guild_wallet_uc"),)

    def __repr__(self) -> str:
        return f"<EconomyWallet(user_id={self.user_id}, guild_id={self.guild_id}, balance={self.balance})>"


class BetOption(Base):
    """Database model for an option in a prediction bet pool."""

    __tablename__ = "economy_bet_options"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    pool_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    label: Mapped[str] = mapped_column(String(100), nullable=False)
    creator_id: Mapped[int] = mapped_column(BigInteger, nullable=False)

    def __repr__(self) -> str:
        return f"<BetOption(id={self.id}, pool_id={self.pool_id}, label={self.label!r})>"


class BetPool(Base):
    """Database model for prediction bet pools."""

    __tablename__ = "economy_bet_pools"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    guild_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    channel_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    message_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    creator_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    allow_custom_options: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_open: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_locked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    locks_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    winning_option: Mapped[str | None] = mapped_column(String(100), nullable=True)

    def __repr__(self) -> str:
        return (
            f"<BetPool(id={self.id}, guild_id={self.guild_id}, title={self.title!r}, "
            f"is_open={self.is_open}, is_locked={self.is_locked})>"
        )


class BetWager(Base):
    """Database model for user wagers placed on a bet pool."""

    __tablename__ = "economy_bet_wagers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    pool_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    guild_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    choice: Mapped[str] = mapped_column(String(100), nullable=False)
    amount: Mapped[int] = mapped_column(BigInteger, nullable=False)

    __table_args__ = (UniqueConstraint("pool_id", "user_id", name="_pool_user_wager_uc"),)

    def __repr__(self) -> str:
        return (
            f"<BetWager(id={self.id}, pool_id={self.pool_id}, user_id={self.user_id}, "
            f"choice={self.choice!r}, amount={self.amount})>"
        )

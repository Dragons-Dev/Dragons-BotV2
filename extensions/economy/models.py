import discord
from sqlalchemy import BigInteger, Boolean, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from utils.orm_database.models import Base

__all__ = ["BetPool", "BetWager", "EconomyWallet", "format_scales", "get_guild_id"]


def get_guild_id(ctx: discord.ApplicationContext) -> int:
    guild = ctx.guild
    if guild is None:
        return 0
    return guild.id


def format_scales(amount: int, guild: discord.Guild | None = None) -> str:
    """
    Format an amount of Dragon Scales with custom guild emoji or fallback.

    :param amount: Amount of Dragon Scales
    :param guild: Discord guild to check for custom dragon_scale emoji
    :return: Formatted string (e.g. '1,000 🐉 Dragon Scales')
    """
    emoji = "🐉"
    if guild is not None and hasattr(guild, "emojis") and guild.emojis:
        custom_emoji = discord.utils.get(guild.emojis, name="dragon_scale")
        if custom_emoji is not None:
            emoji = str(custom_emoji)

    suffix = "Dragon Scale" if amount == 1 else "Dragon Scales"
    return f"{amount:,} {emoji} {suffix}"


class EconomyWallet(Base):
    """Database model for user guild wallets."""

    __tablename__ = "economy_wallets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    guild_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    balance: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)

    __table_args__ = (UniqueConstraint("user_id", "guild_id", name="_user_guild_economy_uc"),)

    def __repr__(self) -> str:
        return f"<EconomyWallet(user_id={self.user_id}, guild_id={self.guild_id}, balance={self.balance})>"


class BetPool(Base):
    """Database model for prediction bet pools."""

    __tablename__ = "economy_bet_pools"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    guild_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    creator_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    title: Mapped[str] = mapped_column(String, nullable=False)
    option_a: Mapped[str] = mapped_column(String, nullable=False)
    option_b: Mapped[str] = mapped_column(String, nullable=False)
    is_open: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    winning_option: Mapped[str | None] = mapped_column(String, nullable=True)

    def __repr__(self) -> str:
        return f"<BetPool(id={self.id}, guild_id={self.guild_id}, title={self.title!r}, is_open={self.is_open})>"


class BetWager(Base):
    """Database model for bet pool wagers."""

    __tablename__ = "economy_bet_wagers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    pool_id: Mapped[int] = mapped_column(Integer, nullable=False)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    guild_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    choice: Mapped[str] = mapped_column(String, nullable=False)  # "A" or "B"
    amount: Mapped[int] = mapped_column(BigInteger, nullable=False)

    __table_args__ = (UniqueConstraint("pool_id", "user_id", name="_pool_user_wager_uc"),)

    def __repr__(self) -> str:
        return (
            f"<BetWager(id={self.id}, pool_id={self.pool_id}, user_id={self.user_id}, "
            f"choice={self.choice!r}, amount={self.amount})>"
        )

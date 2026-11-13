import discord
from sqlalchemy import BigInteger, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from utils.orm_database.models import Base

__all__ = ["EconomyWallet", "format_scales"]


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

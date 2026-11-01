from datetime import date

from sqlalchemy import BigInteger, Date, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from utils.orm_database.models import Base

__all__ = ["UserStats"]


class UserStats(Base):
    __tablename__ = "userstats"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    guild_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    stat_type: Mapped[str] = mapped_column(String, nullable=False)
    value: Mapped[int] = mapped_column(Integer, default=0)
    day: Mapped[date] = mapped_column(Date, default=date.today, nullable=False)

    __table_args__ = (
        # Prevents duplicate entries for the same day and user
        UniqueConstraint("user_id", "guild_id", "stat_type", "day", name="_user_guild_stat_day_uc"),
    )

    def __repr__(self):
        return f"<UserStats(user_id={self.user_id}, stat_type={self.stat_type}, value={self.value}, guild={self.guild_id})>"

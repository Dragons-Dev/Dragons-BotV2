from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from utils.orm_database.models import Base

__all__ = ["Infractions", "Modmail"]


class Infractions(Base):
    __tablename__ = "infractions"
    case_id: Mapped[int] = mapped_column(Integer, autoincrement=True, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger)
    infraction: Mapped[str] = mapped_column(String)
    reason: Mapped[str] = mapped_column(String)
    date: Mapped[datetime] = mapped_column(DateTime)
    guild: Mapped[int] = mapped_column(BigInteger)

    def __repr__(self):
        return f"<Infractions(id={self.case_id}, user_id={self.user_id}, infraction={self.infraction}, reason={self.reason}, date={self.date}, guild={self.guild})>"

    def __len__(self):
        return 1


class Modmail(Base):
    __tablename__ = "modmail"
    user_id: Mapped[int] = mapped_column(BigInteger)
    guild_id: Mapped[int] = mapped_column(BigInteger)
    uuid: Mapped[str] = mapped_column(String, primary_key=True)
    anon: Mapped[bool] = mapped_column(Boolean)

    def __repr__(self):
        return f"<Modmail(user_id={self.user_id}, guild_id={self.guild_id}, uuid={self.uuid}, anon={self.anon})>"

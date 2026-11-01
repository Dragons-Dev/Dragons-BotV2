from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from utils.orm_database.models import Base

__all__ = ["Events", "ConfirmationDB"]


class Events(Base):
    __tablename__ = "Events"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    host: Mapped[int] = mapped_column(BigInteger)
    name: Mapped[str] = mapped_column(String)
    time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    mode: Mapped[str] = mapped_column(String)

    def __repr__(self):
        return f"<{self.__tablename__}(id={self.id}, host={self.host}, name={self.name}, time={self.time}, mode={self.mode})>"


class ConfirmationDB(Base):
    __tablename__ = "Confirmation"
    event_id: Mapped[str] = mapped_column(String, ForeignKey("Events.id"), primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    confirmation: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    reminders: Mapped[str] = mapped_column(String)

    def __repr__(self):
        return f"<{self.__tablename__}(event_id={self.event_id}, user_id={self.user_id}, confirmation={self.confirmation}, reminders={self.reminders})>"

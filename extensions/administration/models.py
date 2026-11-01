from sqlalchemy import Boolean, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from utils.orm_database.models import Base

__all__ = ["BotStatus"]


class BotStatus(Base):
    __tablename__ = "botstatus"
    id: Mapped[int] = mapped_column(Integer, autoincrement=True, primary_key=True)
    status: Mapped[str | None] = mapped_column(String, nullable=True)
    activity_type: Mapped[int | None] = mapped_column(Integer, nullable=True)
    activity_name: Mapped[str | None] = mapped_column(String, nullable=True)
    is_active: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    def __repr__(self):
        return (
            f"<BotStatus(status={self.status}, activity_type={self.activity_type}, activity_name={self.activity_name})>"
        )

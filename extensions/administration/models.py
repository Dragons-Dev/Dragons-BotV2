from sqlalchemy import Boolean, Column, Integer, String

from utils.orm_database.models import Base

__all__ = ["BotStatus"]


class BotStatus(Base):
    __tablename__ = "botstatus"
    id = Column(Integer, autoincrement=True, primary_key=True)
    status = Column(String)
    activity_type = Column(Integer)
    activity_name = Column(String)
    is_active = Column(Boolean)

    def __repr__(self):
        return (
            f"<BotStatus(status={self.status}, activity_type={self.activity_type}, activity_name={self.activity_name})>"
        )

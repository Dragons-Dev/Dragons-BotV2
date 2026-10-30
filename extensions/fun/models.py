from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String

from utils.orm_database.models import Base

__all__ = ["Events", "ConfirmationDB"]


class Events(Base):
    __tablename__ = "Events"
    id = Column(String, primary_key=True)
    host = Column(Integer)
    name = Column(String)
    time = Column(DateTime(timezone=True))
    mode = Column(String)

    def __repr__(self):
        return f"<{self.__tablename__}(id={self.id}, host={self.host}, name={self.name}, time={self.time}, mode={self.mode})>"


class ConfirmationDB(Base):
    __tablename__ = "Confirmation"
    event_id = Column(String, ForeignKey("Events.id"), primary_key=True)
    user_id = Column(Integer, primary_key=True)
    confirmation = Column(Boolean, nullable=True)
    reminders = Column(String)

    def __repr__(self):
        return f"<{self.__tablename__}(event_id={self.event_id}, user_id={self.user_id}, confirmation={self.confirmation}, reminders={self.reminders})>"

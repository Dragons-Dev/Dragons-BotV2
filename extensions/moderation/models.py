from sqlalchemy import Boolean, Column, DateTime, Integer, String

from utils.orm_database.models import Base

__all__ = ["Infractions", "Modmail"]


class Infractions(Base):
    __tablename__ = "infractions"
    case_id = Column(Integer, autoincrement=True, primary_key=True)
    user_id = Column(Integer)
    infraction = Column(String)
    reason = Column(String)
    date = Column(DateTime)
    guild = Column(Integer)

    def __repr__(self):
        return f"<Infractions(id={self.case_id}, user_id={self.user_id}, infraction={self.infraction}, reason={self.reason}, date={self.date}, guild={self.guild})>"

    def __len__(self):
        return 1


class Modmail(Base):
    __tablename__ = "modmail"
    user_id = Column(Integer)
    guild_id = Column(Integer)
    uuid = Column(String, primary_key=True)
    anon = Column(Boolean)

    def __repr__(self):
        return f"<Modmail(user_id={self.user_id}, guild_id={self.guild_id}, uuid={self.uuid}, anon={self.anon})>"

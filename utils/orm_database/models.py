from sqlalchemy import Boolean, Column, DateTime, Integer, String
from sqlalchemy.ext.asyncio import AsyncAttrs
from sqlalchemy.orm import DeclarativeBase

__all__ = ["Base", "Settings", "Infractions", "Join2Create", "Modmail", "UserStats"]


class Base(AsyncAttrs, DeclarativeBase):
    pass


class Settings(Base):
    __tablename__ = "settings"
    setting = Column(String, primary_key=True)
    value = Column(Integer, primary_key=True)
    guild = Column(Integer, primary_key=True)

    def __repr__(self):
        return f"<Settings(setting='{self.setting}', value={self.value}, guild={self.guild})>"


class Infractions(Base):
    __tablename__ = "infractions"
    case_id = Column(Integer, autoincrement=True, primary_key=True)
    user_id = Column(Integer)
    infraction = Column(String)
    reason = Column(String)
    date = Column(DateTime)
    guild = Column(Integer)

    def __repr__(self):
        return f"<Infractions(id={self.id}, user_id={self.user_id}, infraction={self.infraction}, reason={self.reason}, date={self.date}, guild={self.guild})>"


class Join2Create(Base):
    __tablename__ = "join2create"
    channel = Column(Integer, primary_key=True)
    owner_id = Column(Integer)
    locked = Column(Boolean)
    ghosted = Column(Boolean)

    def __repr__(self):
        return f"<Join2Create(channel={self.channel}, owner_id={self.owner_id}, locked={self.locked}, ghosted={self.ghosted})>"


class Modmail(Base):
    __tablename__ = "modmail"
    user_id = Column(Integer)
    guild_id = Column(Integer)
    uuid = Column(String, primary_key=True)
    anon = Column(Boolean)

    def __repr__(self):
        return f"<Modmail(user_id={self.user_id}, guild_id={self.guild_id}, uuid={self.uuid}, anon={self.anon})>"


class UserStats(Base):
    __tablename__ = "userstats"
    user_id = Column(Integer, primary_key=True)
    stat_type = Column(String, primary_key=True)
    value = Column(Integer, primary_key=True)
    guild_id = Column(Integer, primary_key=True)

    def __repr__(self):
        return f"<UserStats(user_id={self.user_id}, stat_type={self.stat_type}, value={self.value}, guild={self.guild})>"

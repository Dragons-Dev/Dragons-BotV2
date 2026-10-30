from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String
from sqlalchemy.ext.asyncio import AsyncAttrs
from sqlalchemy.orm import DeclarativeBase

__all__ = [
    "Base",
    "Settings",
    "MigrationHistory",
]


class Base(AsyncAttrs, DeclarativeBase):
    pass


class Settings(Base):
    __tablename__ = "settings"
    setting = Column(String, primary_key=True)
    value = Column(Integer, primary_key=True)
    guild = Column(Integer, primary_key=True)

    def __repr__(self):
        return f"<Settings(setting='{self.setting}', value={self.value}, guild={self.guild})>"

    def __len__(self):
        return 1


class MigrationHistory(Base):
    __tablename__ = "migration_history"
    script_name = Column(String, primary_key=True)
    version = Column(String, nullable=False)
    applied_at = Column(DateTime, default=datetime.now, nullable=False)

    def __repr__(self):
        return f"<MigrationHistory(script_name='{self.script_name}', version='{self.version}', applied_at={self.applied_at})>"

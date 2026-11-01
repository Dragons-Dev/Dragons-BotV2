from datetime import datetime

from sqlalchemy import BigInteger, DateTime, String
from sqlalchemy.ext.asyncio import AsyncAttrs
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

__all__ = [
    "Base",
    "Settings",
    "MigrationHistory",
]


class Base(AsyncAttrs, DeclarativeBase):
    pass


class Settings(Base):
    __tablename__ = "settings"
    setting: Mapped[str] = mapped_column(String, primary_key=True)
    value: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    guild: Mapped[int] = mapped_column(BigInteger, primary_key=True)

    def __repr__(self):
        return f"<Settings(setting='{self.setting}', value={self.value}, guild={self.guild})>"

    def __len__(self):
        return 1


class MigrationHistory(Base):
    __tablename__ = "migration_history"
    script_name: Mapped[str] = mapped_column(String, primary_key=True)
    version: Mapped[str] = mapped_column(String, nullable=False)
    applied_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, nullable=False)

    def __repr__(self):
        return f"<MigrationHistory(script_name='{self.script_name}', version='{self.version}', applied_at={self.applied_at})>"

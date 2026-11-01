from sqlalchemy import BigInteger, Boolean, String
from sqlalchemy.orm import Mapped, mapped_column

from utils.orm_database.models import Base

__all__ = ["EnabledCommands"]


class EnabledCommands(Base):
    __tablename__ = "enabledcommands"
    guild_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    command_name: Mapped[str] = mapped_column(String, primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean)

    def __repr__(self):
        return f"<EnabledCommands(guild_id={self.guild_id}, command_name={self.command_name}, enabled={self.enabled})>"

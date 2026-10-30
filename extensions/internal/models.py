from sqlalchemy import Boolean, Column, Integer, String

from utils.orm_database.models import Base

__all__ = ["EnabledCommands"]


class EnabledCommands(Base):
    __tablename__ = "enabledcommands"
    guild_id = Column(Integer, primary_key=True)
    command_name = Column(String, primary_key=True)
    enabled = Column(Boolean)

    def __repr__(self):
        return f"<EnabledCommands(guild_id={self.guild_id}, command_name={self.command_name}, enabled={self.enabled})>"

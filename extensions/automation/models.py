from sqlalchemy import Column, Integer

from utils.orm_database.models import Base

__all__ = ["Join2Create"]


class Join2Create(Base):
    __tablename__ = "join2create"
    channel = Column(Integer, primary_key=True)
    owner_id = Column(Integer)
    derived_channel = Column(Integer)

    def __repr__(self):
        return (
            f"<Join2Create(channel={self.channel}, owner_id={self.owner_id}, derived_channel={self.derived_channel})>"
        )

from sqlalchemy import BigInteger
from sqlalchemy.orm import Mapped, mapped_column

from utils.orm_database.models import Base

__all__ = ["Join2Create"]


class Join2Create(Base):
    __tablename__ = "join2create"
    channel: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    owner_id: Mapped[int] = mapped_column(BigInteger)
    derived_channel: Mapped[int] = mapped_column(BigInteger)

    def __repr__(self):
        return (
            f"<Join2Create(channel={self.channel}, owner_id={self.owner_id}, derived_channel={self.derived_channel})>"
        )

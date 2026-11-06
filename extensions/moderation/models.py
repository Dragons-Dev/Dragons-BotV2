from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Integer, LargeBinary, String
from sqlalchemy.orm import Mapped, mapped_column

from utils.orm_database.models import Base

__all__ = ["ArchivedTranscript", "CachedAttachment", "Infractions", "Modmail"]


class Infractions(Base):
    __tablename__ = "infractions"
    case_id: Mapped[int] = mapped_column(Integer, autoincrement=True, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger)
    infraction: Mapped[str] = mapped_column(String)
    reason: Mapped[str] = mapped_column(String)
    date: Mapped[datetime] = mapped_column(DateTime)
    guild: Mapped[int] = mapped_column(BigInteger)

    def __repr__(self):
        return f"<Infractions(id={self.case_id}, user_id={self.user_id}, infraction={self.infraction}, reason={self.reason}, date={self.date}, guild={self.guild})>"

    def __len__(self):
        return 1


class Modmail(Base):
    __tablename__ = "modmail"
    user_id: Mapped[int] = mapped_column(BigInteger)
    guild_id: Mapped[int] = mapped_column(BigInteger)
    uuid: Mapped[str] = mapped_column(String, primary_key=True)
    anon: Mapped[bool] = mapped_column(Boolean)

    def __repr__(self):
        return f"<Modmail(user_id={self.user_id}, guild_id={self.guild_id}, uuid={self.uuid}, anon={self.anon})>"


class CachedAttachment(Base):
    __tablename__ = "cached_attachments"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    channel_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    message_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    attachment_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    filename: Mapped[str] = mapped_column(String, nullable=False)
    content_type: Mapped[str] = mapped_column(String, default="application/octet-stream", nullable=False)
    data: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)

    def __repr__(self) -> str:
        return (
            f"<CachedAttachment(id={self.id}, channel_id={self.channel_id}, "
            f"message_id={self.message_id}, attachment_id={self.attachment_id}, filename={self.filename!r})>"
        )


class ArchivedTranscript(Base):
    __tablename__ = "archived_transcripts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    guild_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    channel_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    channel_name: Mapped[str] = mapped_column(String, nullable=False)
    exported_by: Mapped[int] = mapped_column(BigInteger, nullable=False)
    html_content: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, nullable=False)

    def __repr__(self) -> str:
        return (
            f"<ArchivedTranscript(id={self.id}, guild_id={self.guild_id}, "
            f"channel_id={self.channel_id}, channel_name={self.channel_name!r}, exported_by={self.exported_by})>"
        )

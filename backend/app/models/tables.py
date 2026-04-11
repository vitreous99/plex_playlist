"""
SQLAlchemy ORM table definitions.

Defines the persistent data model for the library metadata cache.
"""

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.database import Base


class Track(Base):
    """Cached representation of a Plex music library track.

    Stores essential metadata extracted during library sync so that
    the prompt processor can query the local catalogue without
    hitting the Plex server on every request.
    """

    __tablename__ = "tracks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    rating_key: Mapped[int] = mapped_column(Integer, unique=True, nullable=False, index=True)
    title: Mapped[str] = mapped_column(String, nullable=False)
    artist: Mapped[str] = mapped_column(String, nullable=False)
    album: Mapped[str | None] = mapped_column(String, nullable=True)
    genre: Mapped[str | None] = mapped_column(String, nullable=True)
    style: Mapped[str | None] = mapped_column(String, nullable=True)
    has_sonic_analysis: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    synced_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    def __repr__(self) -> str:
        return (
            f"<Track(id={self.id}, rating_key={self.rating_key}, "
            f"title={self.title!r}, artist={self.artist!r})>"
        )

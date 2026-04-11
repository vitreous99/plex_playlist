"""
Library metadata synchronisation service.

Iterates over all tracks in the Plex music library and upserts each
one into the local SQLite cache. The sync state (progress, timestamps,
in-progress flag) is maintained in a module-level SyncState object so
the status endpoint can return live progress.

Design notes:
- Uses INSERT OR REPLACE (SQLite dialect) for idempotent upserts keyed
  on `rating_key`.
- Genres and moods are stored as comma-separated strings.
- Artist and album names are taken from grandparentTitle / parentTitle
  to avoid N+1 HTTP calls to the Plex server.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.schemas import SyncStatus
from app.services.plex_client import PlexConnectionError, get_music_section

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Shared sync state (module-level singleton)
# ---------------------------------------------------------------------------

_sync_state = SyncStatus()


def get_sync_status() -> SyncStatus:
    """Return a snapshot of the current sync state."""
    return _sync_state.model_copy()


# ---------------------------------------------------------------------------
# SQL helpers
# ---------------------------------------------------------------------------

_UPSERT_SQL = text(
    """
    INSERT INTO tracks
        (rating_key, title, artist, album, genre, style,
         has_sonic_analysis, synced_at)
    VALUES
        (:rating_key, :title, :artist, :album, :genre, :style,
         :has_sonic_analysis, :synced_at)
    ON CONFLICT(rating_key) DO UPDATE SET
        title              = excluded.title,
        artist             = excluded.artist,
        album              = excluded.album,
        genre              = excluded.genre,
        style              = excluded.style,
        has_sonic_analysis = excluded.has_sonic_analysis,
        synced_at          = excluded.synced_at
    """
)


def _join_tags(tags: list) -> Optional[str]:
    """Convert a list of PlexAPI MediaTag objects to a comma-separated string.

    Returns None when the list is empty so the DB column stores NULL
    rather than an empty string.
    """
    if not tags:
        return None
    return ", ".join(tag.tag for tag in tags if tag.tag) or None


# ---------------------------------------------------------------------------
# Core sync function
# ---------------------------------------------------------------------------

_BATCH_SIZE = 100


async def run_sync(session: AsyncSession) -> SyncStatus:
    """Synchronise the Plex music library into the local SQLite cache.

    Designed to be called from a FastAPI BackgroundTasks job. Updates
    the module-level ``_sync_state`` throughout so callers can poll
    ``GET /api/sync/status`` for live progress.

    Args:
        session: An async SQLAlchemy session connected to the cache DB.

    Returns:
        The final SyncStatus after the sync completes (or fails).

    Raises:
        PlexConnectionError: If the Plex server cannot be reached.
    """
    global _sync_state  # noqa: PLW0603

    if _sync_state.in_progress:
        logger.warning("Sync already in progress — skipping duplicate request.")
        return get_sync_status()

    _sync_state = SyncStatus(in_progress=True, synced_tracks=0, total_tracks=0)
    logger.info("Library sync started.")

    try:
        music_section = get_music_section()
        logger.info("Fetching all tracks from Plex library '%s' …", music_section.title)
        tracks = music_section.searchTracks()
        total = len(tracks)
        _sync_state.total_tracks = total
        logger.info("Found %d tracks — beginning upsert loop.", total)

        synced = 0
        for track in tracks:
            now = datetime.now(timezone.utc)
            artist_name: str = getattr(track, "grandparentTitle", None) or ""
            album_name: Optional[str] = getattr(track, "parentTitle", None)
            genre_str = _join_tags(getattr(track, "genres", []))
            style_str = _join_tags(getattr(track, "moods", []))
            has_sonic = bool(getattr(track, "hasSonicAnalysis", False))

            await session.execute(
                _UPSERT_SQL,
                {
                    "rating_key": track.ratingKey,
                    "title": track.title or "",
                    "artist": artist_name,
                    "album": album_name,
                    "genre": genre_str,
                    "style": style_str,
                    "has_sonic_analysis": has_sonic,
                    "synced_at": now,
                },
            )
            synced += 1
            _sync_state.synced_tracks = synced
            if synced % _BATCH_SIZE == 0:
                await session.commit()
                logger.debug("Upserted %d / %d tracks.", synced, total)

        await session.commit()
        _sync_state = SyncStatus(
            synced_tracks=synced,
            total_tracks=total,
            last_synced_at=datetime.now(timezone.utc),
            in_progress=False,
        )
        logger.info("Library sync complete — %d / %d tracks synced.", synced, total)
        return get_sync_status()

    except PlexConnectionError:
        _sync_state = SyncStatus(
            synced_tracks=_sync_state.synced_tracks,
            total_tracks=_sync_state.total_tracks,
            last_synced_at=None,
            in_progress=False,
        )
        logger.exception("Sync aborted: could not connect to Plex.")
        raise
    except Exception:
        _sync_state = SyncStatus(
            synced_tracks=_sync_state.synced_tracks,
            total_tracks=_sync_state.total_tracks,
            last_synced_at=None,
            in_progress=False,
        )
        logger.exception("Sync aborted: unexpected error.")
        raise

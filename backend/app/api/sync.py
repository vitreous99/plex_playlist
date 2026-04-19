"""
Sync API endpoints.

POST /api/sync        — Trigger library metadata sync as a background job.
GET  /api/sync/status — Return live sync progress and completion state.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, BackgroundTasks, status

from app.models.schemas import SyncStatus
from app.services import sync as sync_service
from app.services.plex_client import PlexConnectionError
from sqlalchemy import text

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/sync", tags=["Sync"])


async def _run_sync_task() -> None:
    """Background task wrapper — catches and logs all errors.
    
    Creates its own database session to avoid issues with the request-scoped
    session being closed before the background task completes.
    """
    from app.models.database import async_session_factory
    
    try:
        async with async_session_factory() as session:
            await sync_service.run_sync(session)
    except PlexConnectionError as exc:
        logger.error("Background sync failed (Plex connection): %s", exc)
    except Exception:
        logger.exception("Background sync failed with unexpected error.")


@router.post(
    "",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Trigger library sync",
    response_description="Sync job accepted and started in background.",
)
async def trigger_sync(
    background_tasks: BackgroundTasks,
) -> dict:
    """Start a background metadata sync from Plex to the local SQLite cache.

    If a sync is already in progress the request is still accepted but
    the existing job continues undisturbed — no second job is started.

    Returns a 202 Accepted response immediately; poll
    ``GET /api/sync/status`` for progress.
    """
    current = sync_service.get_sync_status()
    if current.in_progress:
        return {
            "message": "Sync already in progress.",
            "status": current.model_dump(mode="json"),
        }

    background_tasks.add_task(_run_sync_task)
    logger.info("Sync job enqueued via POST /api/sync.")
    return {"message": "Library sync started.", "status": sync_service.get_sync_status().model_dump(mode="json")}


@router.get(
    "/status",
    response_model=SyncStatus,
    summary="Get sync status",
)
async def get_status() -> SyncStatus:
    """Return the current sync state.

    Fields:
    - **synced_tracks** — rows written so far.
    - **total_tracks** — total tracks found in Plex library.
    - **last_synced_at** — timestamp of the last completed sync.
    - **in_progress** — whether a sync job is currently running.
    """
    return sync_service.get_sync_status()


@router.get(
    "/count",
    summary="Get persisted track count",
)
async def get_persisted_count() -> dict:
    """Return the number of tracks persisted in the SQLite cache.

    This queries the on-disk SQLite file (so it reflects persisted state
    even if the in-memory sync state was lost due to a restart).
    """
    from app.models.database import async_session_factory

    async with async_session_factory() as session:
        result = await session.execute(text("SELECT count(*) FROM tracks"))
        count = result.scalar_one_or_none() or 0

    return {"persisted_tracks": int(count)}

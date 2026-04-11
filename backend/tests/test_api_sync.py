"""
Tests for the sync API endpoints.

POST /api/sync        - trigger background sync
GET  /api/sync/status - return sync state
"""

from unittest.mock import patch

import pytest
from httpx import AsyncClient

from app.models.schemas import SyncStatus
from app.services.plex_client import PlexConnectionError


@pytest.mark.asyncio
async def test_get_sync_status_initial(client: AsyncClient) -> None:
    """GET /api/sync/status returns initial zero state."""
    response = await client.get("/api/sync/status")
    assert response.status_code == 200
    body = response.json()
    assert body["synced_tracks"] == 0
    assert body["total_tracks"] == 0
    assert body["in_progress"] is False
    assert body["last_synced_at"] is None


@pytest.mark.asyncio
async def test_post_sync_returns_202(client: AsyncClient) -> None:
    """POST /api/sync returns 202 Accepted."""
    # Patch run_sync so it doesn't actually try to contact Plex
    with patch("app.api.sync._run_sync_task"):
        response = await client.post("/api/sync")
    assert response.status_code == 202


@pytest.mark.asyncio
async def test_post_sync_returns_message(client: AsyncClient) -> None:
    """POST /api/sync returns a 'started' message."""
    with patch("app.api.sync._run_sync_task"):
        response = await client.post("/api/sync")
    body = response.json()
    assert "message" in body
    assert "sync" in body["message"].lower()


@pytest.mark.asyncio
async def test_post_sync_already_in_progress(client: AsyncClient) -> None:
    """POST /api/sync when already in progress still returns 202."""
    import app.services.sync as sync_service
    sync_service._sync_state = SyncStatus(in_progress=True, synced_tracks=5, total_tracks=100)

    with patch("app.api.sync._run_sync_task"):
        response = await client.post("/api/sync")
    assert response.status_code == 202
    body = response.json()
    assert "in progress" in body["message"].lower()


@pytest.mark.asyncio
async def test_get_sync_status_reflects_state(client: AsyncClient) -> None:
    """GET /api/sync/status reflects module-level sync state."""
    import app.services.sync as sync_service
    from datetime import datetime, timezone
    sync_service._sync_state = SyncStatus(
        synced_tracks=42,
        total_tracks=100,
        last_synced_at=datetime.now(timezone.utc),
        in_progress=False,
    )

    response = await client.get("/api/sync/status")
    assert response.status_code == 200
    body = response.json()
    assert body["synced_tracks"] == 42
    assert body["total_tracks"] == 100
    assert body["in_progress"] is False
    assert body["last_synced_at"] is not None

"""
Tests for the /health endpoint.

Validates the health-check response structure and status code.
"""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health_returns_200(client: AsyncClient) -> None:
    """GET /health should return 200 with status 'ok'."""
    response = await client.get("/health")

    assert response.status_code == 200

    body = response.json()
    assert body["status"] == "ok"
    assert "timestamp" in body
    assert "version" in body


@pytest.mark.asyncio
async def test_health_contains_version(client: AsyncClient) -> None:
    """GET /health should include the application version."""
    response = await client.get("/health")
    body = response.json()

    assert body["version"] == "0.1.0"

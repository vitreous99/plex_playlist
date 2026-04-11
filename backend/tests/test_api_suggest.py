"""
Tests for the suggest API endpoint.

POST /api/suggest
"""

from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

from app.models.schemas import PlaylistResponse, SuggestedTrack
from app.services.ollama_client import OllamaError


def _make_playlist(track_count: int = 3) -> PlaylistResponse:
    return PlaylistResponse(
        name="Rainy Jazz",
        description="Chill jazz for a rainy evening.",
        tracks=[
            SuggestedTrack(title=f"Track {i}", artist=f"Artist {i}", reasoning="Good.")
            for i in range(track_count)
        ],
    )


@pytest.mark.asyncio
async def test_suggest_returns_200_with_playlist(client: AsyncClient) -> None:
    """POST /api/suggest returns 200 with a valid PlaylistResponse."""
    playlist = _make_playlist(3)

    with patch(
        "app.api.suggest.build_prompt",
        new_callable=AsyncMock,
        return_value=("sys", "usr"),
    ), patch(
        "app.api.suggest.generate_playlist",
        new_callable=AsyncMock,
        return_value=playlist,
    ):
        response = await client.post(
            "/api/suggest",
            json={"prompt": "chill jazz for a rainy night", "track_count": 3},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "Rainy Jazz"
    assert len(body["tracks"]) == 3
    assert body["tracks"][0]["title"] == "Track 0"


@pytest.mark.asyncio
async def test_suggest_returns_503_when_ollama_down(client: AsyncClient) -> None:
    """POST /api/suggest returns 503 when Ollama is unavailable."""
    with patch(
        "app.api.suggest.build_prompt",
        new_callable=AsyncMock,
        return_value=("sys", "usr"),
    ), patch(
        "app.api.suggest.generate_playlist",
        new_callable=AsyncMock,
        side_effect=OllamaError("Connection refused"),
    ):
        response = await client.post(
            "/api/suggest",
            json={"prompt": "jazz", "track_count": 5},
        )

    assert response.status_code == 503
    body = response.json()
    assert "Connection refused" in body["detail"]


@pytest.mark.asyncio
async def test_suggest_returns_404_on_empty_playlist(client: AsyncClient) -> None:
    """POST /api/suggest returns 404 when LLM returns empty playlist."""
    empty_playlist = PlaylistResponse(name="Empty", description="Nothing.", tracks=[])

    with patch(
        "app.api.suggest.build_prompt",
        new_callable=AsyncMock,
        return_value=("sys", "usr"),
    ), patch(
        "app.api.suggest.generate_playlist",
        new_callable=AsyncMock,
        return_value=empty_playlist,
    ):
        response = await client.post(
            "/api/suggest",
            json={"prompt": "something obscure", "track_count": 10},
        )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_suggest_validates_prompt_too_short(client: AsyncClient) -> None:
    """POST /api/suggest returns 422 when prompt is too short."""
    response = await client.post(
        "/api/suggest",
        json={"prompt": "ab", "track_count": 5},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_suggest_validates_track_count_too_high(client: AsyncClient) -> None:
    """POST /api/suggest returns 422 when track_count exceeds 100."""
    response = await client.post(
        "/api/suggest",
        json={"prompt": "valid prompt", "track_count": 200},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_suggest_default_track_count(client: AsyncClient) -> None:
    """POST /api/suggest uses default track_count of 20 when not specified."""
    playlist = _make_playlist(20)

    captured_count = []

    async def mock_generate(sys, usr, count):
        captured_count.append(count)
        return playlist

    with patch(
        "app.api.suggest.build_prompt",
        new_callable=AsyncMock,
        return_value=("sys", "usr"),
    ), patch(
        "app.api.suggest.generate_playlist",
        side_effect=mock_generate,
    ):
        response = await client.post(
            "/api/suggest",
            json={"prompt": "upbeat morning vibes"},
        )

    assert response.status_code == 200
    assert captured_count[0] == 20


@pytest.mark.asyncio
async def test_suggest_response_schema(client: AsyncClient) -> None:
    """POST /api/suggest response contains required fields."""
    playlist = _make_playlist(2)

    with patch(
        "app.api.suggest.build_prompt",
        new_callable=AsyncMock,
        return_value=("sys", "usr"),
    ), patch(
        "app.api.suggest.generate_playlist",
        new_callable=AsyncMock,
        return_value=playlist,
    ):
        response = await client.post(
            "/api/suggest",
            json={"prompt": "chill jazz", "track_count": 2},
        )

    body = response.json()
    assert "name" in body
    assert "description" in body
    assert "tracks" in body
    for track in body["tracks"]:
        assert "title" in track
        assert "artist" in track
        assert "reasoning" in track

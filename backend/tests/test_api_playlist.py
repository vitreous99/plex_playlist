"""
Tests for Playlist APIs (Phase 3).
"""

import pytest
from unittest.mock import patch, MagicMock

@pytest.mark.asyncio
@patch('app.api.clients.fetch_clients')
async def test_api_clients_returns_list(mock_fetch_clients, client):
    mock_fetch_clients.return_value = [
        {"name": "Web Client", "identifier": "web-1", "product": "Plex Web", "address": "127.0.0.1"}
    ]
    
    response = await client.get("/api/clients")
    
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["name"] == "Web Client"

@pytest.mark.asyncio
@patch('app.api.playlist.build_playlist')
@patch('app.api.playlist.dispatch_playback')
async def test_api_playlist_play_success(mock_dispatch, mock_build, client):
    mock_build.return_value = [MagicMock()]
    mock_dispatch.return_value = {"client": "TV", "status": "playing", "track_count": 1}
    
    response = await client.post(
        "/api/playlist/play",
        json={"prompt": "test prompt", "track_count": 10, "client_name": "TV"}
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["client"] == "TV"
    assert data["status"] == "playing"

@pytest.mark.asyncio
@patch('app.api.playlist.build_playlist')
@patch('app.api.playlist.get_server')
@patch('plexapi.playlist.Playlist')
async def test_api_playlist_save_success(mock_playlist_class, mock_get_server, mock_build, client):
    mock_build.return_value = [MagicMock()]
    mock_get_server.return_value = MagicMock()
    
    response = await client.post(
        "/api/playlist/save",
        json={"prompt": "test prompt", "track_count": 10, "playlist_name": "My Save"}
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["playlist_name"] == "My Save"
    mock_playlist_class.create.assert_called_once()

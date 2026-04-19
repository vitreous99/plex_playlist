"""
Tests for the Client Dispatcher (Phase 3).
"""

import pytest
from unittest.mock import patch, MagicMock
from app.services.client_dispatcher import get_clients, dispatch_playback

class MockClient:
    def __init__(self, name, product="Plex Client", address="127.0.0.1"):
        self.title = name
        self.machineIdentifier = f"id-{name}"
        self.product = product
        self.address = address
        self.playMedia = MagicMock()

@patch('app.services.client_dispatcher.get_server')
def test_client_discovery(mock_get_server):
    mock_server = MagicMock()
    mock_get_server.return_value = mock_server
    
    mock_server.clients.return_value = [
        MockClient("TV"),
        MockClient("Phone", product="Plex for iOS")
    ]
    
    clients = get_clients()
    
    assert len(clients) == 2
    assert clients[0]["name"] == "TV"
    assert clients[1]["product"] == "Plex for iOS"

@patch('app.services.client_dispatcher.get_server')
@patch('app.services.client_dispatcher.PlayQueue')
def test_dispatch_playback_success(mock_pq, mock_get_server):
    mock_server = MagicMock()
    mock_get_server.return_value = mock_server
    
    tv_client = MockClient("TV")
    mock_server.client.return_value = tv_client
    
    mock_pq.create.return_value = MagicMock()
    
    tracks = [MagicMock()]
    
    result = dispatch_playback(tracks, "TV")
    
    assert result["status"] == "playing"
    assert result["client"] == "TV"
    tv_client.playMedia.assert_called_once()
    mock_pq.create.assert_called_once()

@patch('app.services.client_dispatcher.get_server')
def test_dispatch_playback_client_not_found(mock_get_server):
    mock_server = MagicMock()
    mock_get_server.return_value = mock_server
    
    # PlexAPI raises an exception when client is not found
    mock_server.client.side_effect = Exception("Client not found")
    
    tracks = [MagicMock()]
    
    with pytest.raises(Exception, match="Client 'Unknown Device' not found"):
        dispatch_playback(tracks, "Unknown Device")

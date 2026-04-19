"""
Tests for the Playlist Builder orchestration (Phase 3).
"""

import pytest
from unittest.mock import patch, MagicMock
from app.models.schemas import SuggestedTrack
from app.models.tables import Track as DbTrack
from app.services.playlist_builder import build_playlist

class MockPlexTrack:
    def __init__(self, rating_key, title="Mock"):
        self.ratingKey = rating_key
        self.title = title

@pytest.mark.asyncio
@patch('app.services.playlist_builder.generate_playlist')
@patch('app.services.playlist_builder.match_tracks')
@patch('app.services.playlist_builder.expand_with_sonic_similarity')
async def test_build_playlist_success(
    mock_expand, mock_match, mock_generate, db_session
):
    # Mock LLM generation
    mock_generate.return_value = MagicMock(
        name="Test Playlist",
        tracks=[
            SuggestedTrack(title="Song 1", artist="Artist A", reasoning="test"),
            SuggestedTrack(title="Song 2", artist="Artist B", reasoning="test")
        ]
    )
    
    # Mock track matcher
    mock_match.return_value = ([DbTrack(rating_key=1), DbTrack(rating_key=2)], [])
    
    # Mock sonic expansion
    mock_expand.return_value = [MockPlexTrack(1), MockPlexTrack(2), MockPlexTrack(3)]
    
    # Run
    result = await build_playlist(db_session, "some prompt", 3)
    
    assert len(result) == 3
    mock_generate.assert_called_once()
    mock_match.assert_called_once()
    mock_expand.assert_called_once()

@pytest.mark.asyncio
@patch('app.services.playlist_builder.generate_playlist')
@patch('app.services.playlist_builder.match_tracks')
@patch('app.services.playlist_builder.build_sonic_adventure')
async def test_build_playlist_with_adventure(
    mock_adventure, mock_match, mock_generate, db_session
):
    # Mock LLM generation for a transition prompt
    mock_generate.return_value = MagicMock(
        name="Transition Playlist",
        tracks=[
            SuggestedTrack(title="Start Song", artist="Artist A", reasoning="start"),
            SuggestedTrack(title="End Song", artist="Artist B", reasoning="end")
        ]
    )
    
    # Mock track matcher
    mock_match.return_value = ([DbTrack(rating_key=1), DbTrack(rating_key=10)], [])
    
    # Mock sonic adventure
    mock_adventure.return_value = [MockPlexTrack(1), MockPlexTrack(5), MockPlexTrack(10)]
    
    # Run with a transition prompt
    result = await build_playlist(db_session, "start with Folk, end with Metal", 3)
    
    assert len(result) == 3
    mock_adventure.assert_called_once()

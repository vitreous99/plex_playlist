"""
Tests for the Sonic Engine (Phase 3).
"""

import pytest
from unittest.mock import MagicMock, patch
from app.models.tables import Track as DbTrack
from app.services.sonic_engine import expand_with_sonic_similarity, build_sonic_adventure

class MockPlexTrack:
    def __init__(self, rating_key, title="Mock"):
        self.ratingKey = rating_key
        self.title = title
    
    def sonicallySimilar(self, limit=10, maxDistance=0.25):
        # Return mock similar tracks
        return [MockPlexTrack(self.ratingKey + 100), MockPlexTrack(self.ratingKey + 200)]
        
    def sonicAdventure(self, to):
        # Return a mock path
        return [self, MockPlexTrack(500), MockPlexTrack(600), to]

@patch('app.services.sonic_engine.get_music_section')
def test_sonically_similar_expansion(mock_get_section):
    # Setup mock section
    mock_section = MagicMock()
    mock_get_section.return_value = mock_section
    
    def mock_fetch(rating_key):
        return MockPlexTrack(rating_key)
        
    mock_section.fetchItem = mock_fetch
    
    seeds = [DbTrack(rating_key=1), DbTrack(rating_key=2)]
    
    result = expand_with_sonic_similarity(seeds, target_count=4)
    
    assert len(result) == 4
    # The first 2 should be the seeds
    assert result[0].ratingKey == 1
    assert result[1].ratingKey == 2

@patch('app.services.sonic_engine.get_music_section')
def test_sonic_adventure_bridging(mock_get_section):
    mock_section = MagicMock()
    mock_get_section.return_value = mock_section
    
    def mock_fetch(rating_key):
        return MockPlexTrack(rating_key)
        
    mock_section.fetchItem = mock_fetch
    
    source = DbTrack(rating_key=1)
    target = DbTrack(rating_key=10)
    
    result = build_sonic_adventure(source, target, target_count=5)
    
    assert len(result) == 4
    assert result[0].ratingKey == 1
    assert result[-1].ratingKey == 10

@patch('app.services.sonic_engine.get_music_section')
def test_sonic_engine_limits(mock_get_section):
    mock_section = MagicMock()
    mock_get_section.return_value = mock_section
    
    def mock_fetch(rating_key):
        return MockPlexTrack(rating_key)
        
    mock_section.fetchItem = mock_fetch
    
    seeds = [DbTrack(rating_key=1)]
    
    # Even if sonicallySimilar returns tracks, limit to target_count
    result = expand_with_sonic_similarity(seeds, target_count=2)
    assert len(result) == 2

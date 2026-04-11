"""
Tests for the Track Matcher (Phase 3).
"""

import pytest
from app.models.schemas import SuggestedTrack
from app.models.tables import Track
from app.services.track_matcher import match_tracks, string_similarity

def test_string_similarity():
    assert string_similarity("Hello", "hello") == 1.0
    assert string_similarity("Hello", "world") < 0.5
    assert string_similarity("The Beatles", "Beatles") > 0.7

@pytest.mark.asyncio
async def test_track_matcher_exact_match(db_session):
    # Setup mock data
    track = Track(
        rating_key=1,
        title="Bohemian Rhapsody",
        artist="Queen",
        album="A Night at the Opera"
    )
    db_session.add(track)
    await db_session.commit()

    suggestions = [
        SuggestedTrack(title="Bohemian Rhapsody", artist="Queen", reasoning="Classic")
    ]

    matched, unmatched = await match_tracks(db_session, suggestions)
    
    assert len(matched) == 1
    assert len(unmatched) == 0
    assert matched[0].title == "Bohemian Rhapsody"

@pytest.mark.asyncio
async def test_track_matcher_fuzzy_match(db_session):
    track = Track(
        rating_key=2,
        title="Stairway to Heaven",
        artist="Led Zeppelin",
        album="Led Zeppelin IV"
    )
    db_session.add(track)
    await db_session.commit()

    suggestions = [
        SuggestedTrack(title="Stairway 2 Heaven", artist="Led Zeplin", reasoning="Typo match")
    ]

    matched, unmatched = await match_tracks(db_session, suggestions, threshold=0.7)
    
    assert len(matched) == 1
    assert len(unmatched) == 0
    assert matched[0].title == "Stairway to Heaven"

@pytest.mark.asyncio
async def test_track_matcher_unmatched_logged(db_session, caplog):
    track = Track(
        rating_key=3,
        title="Hotel California",
        artist="Eagles",
        album="Hotel California"
    )
    db_session.add(track)
    await db_session.commit()

    suggestions = [
        SuggestedTrack(title="Nonexistent Song", artist="Unknown Band", reasoning="Not in DB")
    ]

    matched, unmatched = await match_tracks(db_session, suggestions)
    
    assert len(matched) == 0
    assert len(unmatched) == 1
    assert "Unmatched track: 'Nonexistent Song' by 'Unknown Band'" in caplog.text

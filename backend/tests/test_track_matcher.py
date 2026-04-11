"""
Tests for the Track Matcher (Phase 3).
"""

import pytest

pytestmark = pytest.mark.skip(reason="Phase 3 not implemented yet")

def test_track_matcher_exact_match() -> None:
    """Track matcher should successfully find exact matches by title and artist."""
    pass

def test_track_matcher_fuzzy_match() -> None:
    """Track matcher should use fuzzy logic to find tracks with slight typos."""
    pass

def test_track_matcher_unmatched_logged() -> None:
    """Track matcher should return unmatched tracks and log them correctly."""
    pass

"""
Track Matcher module.

Matches LLM generated track suggestions to real Plex tracks from the local SQLite cache.
"""

import logging
from difflib import SequenceMatcher
from typing import Sequence, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import or_

from app.models.schemas import SuggestedTrack
from app.models.tables import Track

logger = logging.getLogger(__name__)

def string_similarity(a: str, b: str) -> float:
    """Return similarity ratio between two strings (case-insensitive)."""
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()

async def match_tracks(
    session: AsyncSession,
    suggestions: Sequence[SuggestedTrack],
    threshold: float = 0.8
) -> Tuple[list[Track], list[SuggestedTrack]]:
    """
    Attempt to match LLM suggestions to real Plex tracks in the local cache.
    Returns a tuple of (matched_tracks, unmatched_suggestions).
    """
    matched: list[Track] = []
    unmatched: list[SuggestedTrack] = []

    for suggestion in suggestions:
        # First try exact match by title and artist
        stmt = select(Track).where(
            Track.title.ilike(suggestion.title),
            Track.artist.ilike(suggestion.artist)
        )
        result = await session.execute(stmt)
        exact_match = result.scalars().first()

        if exact_match:
            matched.append(exact_match)
            continue

        # If no exact match, try fuzzy matching
        # Pull all tracks and score them. This is feasible because the local
        # SQLite cache is typically small (10k-50k tracks) and we can optimize
        # if needed later. But we can just use the first words to filter initially.
        title_words = suggestion.title.split()
        artist_words = suggestion.artist.split()
        
        conditions = []
        if title_words:
            conditions.append(Track.title.ilike(f"%{title_words[0]}%"))
        if artist_words:
            conditions.append(Track.artist.ilike(f"%{artist_words[0]}%"))
            
        if conditions:
            stmt_fuzzy = select(Track).where(or_(*conditions))
        else:
            stmt_fuzzy = select(Track)
            
        result_fuzzy = await session.execute(stmt_fuzzy)
        candidates = result_fuzzy.scalars().all()

        best_match = None
        best_score = 0.0

        for candidate in candidates:
            title_score = string_similarity(suggestion.title, candidate.title)
            artist_score = string_similarity(suggestion.artist, candidate.artist)
            
            combined_score = (title_score * 0.6) + (artist_score * 0.4)
            
            if combined_score > best_score:
                best_score = combined_score
                best_match = candidate

        if best_match and best_score >= threshold:
            logger.debug(f"Fuzzy matched '{suggestion.title}' by '{suggestion.artist}' "
                         f"to '{best_match.title}' by '{best_match.artist}' "
                         f"(score: {best_score:.2f})")
            matched.append(best_match)
        else:
            logger.warning(f"Unmatched track: '{suggestion.title}' by '{suggestion.artist}'")
            unmatched.append(suggestion)

    return matched, unmatched

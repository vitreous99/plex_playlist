"""
Track Matcher module.

Matches LLM generated track suggestions to real Plex tracks from the local SQLite cache.
"""

import logging
from difflib import SequenceMatcher
from typing import Callable, Optional, Sequence, Tuple

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
    threshold: float = 0.8,
    on_event: Optional[Callable] = None,
) -> Tuple[list[Track], list[SuggestedTrack]]:
    """
    Attempt to match LLM suggestions to real Plex tracks in the local cache.
    Uses a progressive matching strategy:
    1. Exact match on title + artist
    2. Fuzzy match (title + artist combined score)
    3. Artist-first approach: find artist, then best track by that artist
    
    Args:
        session: Async database session.
        suggestions: LLM-suggested tracks.
        threshold: Similarity threshold for matching.
        on_event: Optional callback for streaming events.
    
    Returns a tuple of (matched_tracks, unmatched_suggestions).
    """
    matched: list[Track] = []
    unmatched: list[SuggestedTrack] = []
    matched_keys: set[int] = set()  # prevent the same DB row appearing twice

    for idx, suggestion in enumerate(suggestions):
        # First try exact match by title and artist
        stmt = select(Track).where(
            Track.title.ilike(suggestion.title),
            Track.artist.ilike(suggestion.artist)
        )
        result = await session.execute(stmt)
        exact_match = result.scalars().first()

        if exact_match:
            if exact_match.rating_key not in matched_keys:
                matched.append(exact_match)
                matched_keys.add(exact_match.rating_key)
            logger.debug(f"Exact matched '{suggestion.title}' by '{suggestion.artist}'")
            if on_event:
                try:
                    on_event({
                        "phase": "matching",
                        "step": f"track_{idx+1}_matched",
                        "message": f"✓ Matched: {suggestion.title}",
                        "detail": {
                            "track_number": idx + 1,
                            "suggested_title": suggestion.title,
                            "suggested_artist": suggestion.artist,
                            "matched_title": exact_match.title,
                            "matched_artist": exact_match.artist,
                            "match_type": "exact",
                            "score": 1.0,
                        },
                        "timing_ms": 0,
                        "progress": 0.5 + (0.25 * (idx / max(len(suggestions), 1))),
                    })
                except Exception as e:
                    logger.debug(f"Error emitting track_matched event: {e}")
            continue

        # Second: Try fuzzy matching with initial filter
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
        
        # If filtering by first words yields no candidates, try a broader search
        if not candidates and (title_words or artist_words):
            logger.debug(
                f"No candidates found for '{suggestion.title}' by '{suggestion.artist}' "
                f"with first-word filter. Expanding search..."
            )
            broad_conditions = []
            for word in title_words:
                if len(word) > 2:
                    broad_conditions.append(Track.title.ilike(f"%{word}%"))
            for word in artist_words:
                if len(word) > 2:
                    broad_conditions.append(Track.artist.ilike(f"%{word}%"))
            
            if broad_conditions:
                stmt_broad = select(Track).where(or_(*broad_conditions))
                result_broad = await session.execute(stmt_broad)
                candidates = result_broad.scalars().all()

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
                         f"to '{best_match.title}' by '{best_match.artist}' (score: {best_score:.2f})")
            if best_match.rating_key not in matched_keys:
                matched.append(best_match)
                matched_keys.add(best_match.rating_key)
            if on_event:
                try:
                    on_event({
                        "phase": "matching",
                        "step": f"track_{idx+1}_matched",
                        "message": f"✓ Matched: {suggestion.title}",
                        "detail": {
                            "track_number": idx + 1,
                            "suggested_title": suggestion.title,
                            "suggested_artist": suggestion.artist,
                            "matched_title": best_match.title,
                            "matched_artist": best_match.artist,
                            "match_type": "fuzzy",
                            "score": round(best_score, 2),
                        },
                        "timing_ms": 0,
                        "progress": 0.5 + (0.25 * (idx / max(len(suggestions), 1))),
                    })
                except Exception as e:
                    logger.debug(f"Error emitting track_matched event: {e}")
            continue
        
        # Third: Artist-first approach - find any track by the suggested artist
        artist_search = select(Track).where(
            Track.artist.ilike(f"%{suggestion.artist}%")
        )
        result_artist = await session.execute(artist_search)
        artist_tracks = result_artist.scalars().all()
        
        if artist_tracks:
            # If we found tracks by this artist, pick the best title match
            best_artist_match = None
            best_title_score = 0.0
            
            for artist_track in artist_tracks:
                title_score = string_similarity(suggestion.title, artist_track.title)
                if title_score > best_title_score:
                    best_title_score = title_score
                    best_artist_match = artist_track
            
            if best_artist_match and best_title_score >= 0.5:  # Lower threshold for artist-first match
                logger.info(
                    f"Artist-first matched '{suggestion.title}' by '{suggestion.artist}' "
                    f"to '{best_artist_match.title}' by '{best_artist_match.artist}' "
                    f"(title score: {best_title_score:.2f})"
                )
                if best_artist_match.rating_key not in matched_keys:
                    matched.append(best_artist_match)
                    matched_keys.add(best_artist_match.rating_key)
                if on_event:
                    try:
                        on_event({
                            "phase": "matching",
                            "step": f"track_{idx+1}_matched",
                            "message": f"✓ Matched: {suggestion.title}",
                            "detail": {
                                "track_number": idx + 1,
                                "suggested_title": suggestion.title,
                                "suggested_artist": suggestion.artist,
                                "matched_title": best_artist_match.title,
                                "matched_artist": best_artist_match.artist,
                                "match_type": "artist-first",
                                "score": round(best_title_score, 2),
                            },
                            "timing_ms": 0,
                            "progress": 0.5 + (0.25 * (idx / max(len(suggestions), 1))),
                        })
                    except Exception as e:
                        logger.debug(f"Error emitting track_matched event: {e}")
                continue
        
        # If all strategies fail, try relaxed fuzzy match on best candidate found
        if best_match and best_score >= 0.6:
            logger.info(f"Fuzzy matched (relaxed) '{suggestion.title}' by '{suggestion.artist}' "
                        f"to '{best_match.title}' by '{best_match.artist}' (score: {best_score:.2f})")
            if best_match.rating_key not in matched_keys:
                matched.append(best_match)
                matched_keys.add(best_match.rating_key)
            if on_event:
                try:
                    on_event({
                        "phase": "matching",
                        "step": f"track_{idx+1}_matched",
                        "message": f"✓ Matched (relaxed): {suggestion.title}",
                        "detail": {
                            "track_number": idx + 1,
                            "suggested_title": suggestion.title,
                            "suggested_artist": suggestion.artist,
                            "matched_title": best_match.title,
                            "matched_artist": best_match.artist,
                            "match_type": "fuzzy-relaxed",
                            "score": round(best_score, 2),
                        },
                        "timing_ms": 0,
                        "progress": 0.5 + (0.25 * (idx / max(len(suggestions), 1))),
                    })
                except Exception as e:
                    logger.debug(f"Error emitting track_matched event: {e}")
            continue
        
        logger.warning(f"Unmatched track: '{suggestion.title}' by '{suggestion.artist}' "
                      f"(best score: {best_score:.2f}, artist tracks found: {len(artist_tracks) if 'artist_tracks' in locals() else 0})")
        unmatched.append(suggestion)
        if on_event:
            try:
                on_event({
                    "phase": "matching",
                    "step": f"track_{idx+1}_unmatched",
                    "message": f"✗ Not found: {suggestion.title}",
                    "detail": {
                        "track_number": idx + 1,
                        "suggested_title": suggestion.title,
                        "suggested_artist": suggestion.artist,
                        "best_score": round(best_score, 2) if best_score else 0,
                    },
                    "timing_ms": 0,
                    "progress": 0.5 + (0.25 * (idx / max(len(suggestions), 1))),
                })
            except Exception as e:
                logger.debug(f"Error emitting track_unmatched event: {e}")

    return matched, unmatched

"""
Prompt processor — NLP keyword extraction and LLM system-prompt builder.

Pipeline:
  1. Strip stopwords from the user prompt to extract semantic keywords.
  2. Query the local SQLite cache for matching artists and genres.
  3. Build a structured system prompt instructing the LLM to select
     tracks exclusively from the user's library.
"""

from __future__ import annotations

import json
import logging
import re

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.schemas import PlaylistResponse
from app.services.library_search import (
    get_distinct_artists,
    get_distinct_genres,
    search_tracks_by_keywords,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Stopword list
# ---------------------------------------------------------------------------

_STOPWORDS: frozenset[str] = frozenset(
    {
        "a", "an", "the", "and", "or", "but", "in", "on", "at", "to",
        "for", "of", "with", "by", "from", "is", "are", "was", "were",
        "be", "been", "being", "have", "has", "had", "do", "does", "did",
        "will", "would", "could", "should", "may", "might", "can", "shall",
        "i", "me", "my", "we", "our", "you", "your", "he", "she", "it",
        "they", "them", "their", "that", "this", "these", "those", "what",
        "which", "who", "how", "when", "where", "why",
        "make", "want", "need", "give", "get", "some", "like", "just",
        "songs", "tracks", "music", "playlist", "mix", "list", "song",
        "track", "album", "artist", "band", "something", "feel", "feeling",
    }
)

MAX_CONTEXT_ITEMS = 40


# ---------------------------------------------------------------------------
# Keyword extraction
# ---------------------------------------------------------------------------


def extract_keywords(prompt: str) -> list[str]:
    """Extract semantic keywords from a natural-language prompt.

    Lowercases, removes punctuation, splits on whitespace, then filters
    out stopwords and single-character tokens.

    Args:
        prompt: Raw user input string.

    Returns:
        Ordered list of unique, meaningful keywords.
    """
    cleaned = re.sub(r"[^\w\s]", " ", prompt.lower())
    tokens = cleaned.split()
    seen: set[str] = set()
    keywords: list[str] = []
    for token in tokens:
        if token not in _STOPWORDS and len(token) > 1 and token not in seen:
            seen.add(token)
            keywords.append(token)
    logger.debug("extract_keywords(%r) → %r", prompt, keywords)
    return keywords


# ---------------------------------------------------------------------------
# Context pool builder
# ---------------------------------------------------------------------------


async def build_context_pool(
    session: AsyncSession,
    keywords: list[str],
) -> dict[str, list[str]]:
    """Query the cache and return matching artists, genres, and sample tracks.

    Args:
        session:  Async DB session.
        keywords: Keywords extracted from the user prompt.

    Returns:
        Dict with keys "artists", "genres", "sample_tracks".
    """
    all_artists = await get_distinct_artists(session)
    all_genres = await get_distinct_genres(session)
    kw_lower = {k.lower() for k in keywords}

    matching_artists = [
        a for a in all_artists
        if any(kw in a.lower() for kw in kw_lower)
    ][:MAX_CONTEXT_ITEMS]

    matching_genres = [
        g for g in all_genres
        if any(kw in g.lower() for kw in kw_lower)
    ][:MAX_CONTEXT_ITEMS]

    sample_tracks: list[str] = []
    if keywords:
        tracks = await search_tracks_by_keywords(session, keywords, limit=MAX_CONTEXT_ITEMS)
        sample_tracks = [
            f"{t.title} — {t.artist}" + (f" [{t.album}]" if t.album else "")
            for t in tracks
        ]

    # Broad fallback if no keyword matches
    if not matching_artists:
        matching_artists = all_artists[:MAX_CONTEXT_ITEMS]
    if not matching_genres:
        matching_genres = all_genres[:MAX_CONTEXT_ITEMS]

    return {
        "artists": matching_artists,
        "genres": matching_genres,
        "sample_tracks": sample_tracks,
    }


# ---------------------------------------------------------------------------
# System prompt builder
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT_TEMPLATE = """\
You are an expert music curator for a personal Plex music library.
Your task is to generate a playlist based on the user's request.
You MUST only suggest tracks that could plausibly exist in the user's library.

## Library Context

Artists available (up to {max_items}):
{artists}

Genres available (up to {max_items}):
{genres}

Sample matching tracks:
{sample_tracks}

## Instructions
- Select exactly {track_count} tracks from this library.
- Prioritise tracks matching the mood, genre, or feel of the request.
- Prefer artists and genres listed in Library Context.
- Provide a concise reasoning for each track (1-2 sentences).
- Return ONLY a valid JSON object conforming to this schema:
{schema}
"""


def build_system_prompt(
    context_pool: dict[str, list[str]],
    track_count: int,
) -> str:
    """Build the system prompt injected into the LLM conversation.

    Args:
        context_pool: Output of ``build_context_pool``.
        track_count:  Number of tracks the LLM should return.

    Returns:
        Fully-formed system prompt string.
    """
    artists_block = (
        "\n".join(f"  - {a}" for a in context_pool["artists"]) or "  (none found)"
    )
    genres_block = (
        "\n".join(f"  - {g}" for g in context_pool["genres"]) or "  (none found)"
    )
    tracks_block = (
        "\n".join(f"  - {t}" for t in context_pool["sample_tracks"])
        or "  (no matching tracks found)"
    )
    schema_str = json.dumps(PlaylistResponse.model_json_schema(), indent=2)
    return _SYSTEM_PROMPT_TEMPLATE.format(
        max_items=MAX_CONTEXT_ITEMS,
        artists=artists_block,
        genres=genres_block,
        sample_tracks=tracks_block,
        track_count=track_count,
        schema=schema_str,
    )


async def build_prompt(
    session: AsyncSession,
    user_prompt: str,
    track_count: int,
) -> tuple[str, str]:
    """Full pipeline: keywords → context pool → system + user prompts.

    Args:
        session:      Async DB session.
        user_prompt:  Raw user input.
        track_count:  Number of tracks requested.

    Returns:
        Tuple of (system_prompt, user_message) ready for the LLM.
    """
    keywords = extract_keywords(user_prompt)
    context_pool = await build_context_pool(session, keywords)
    system_prompt = build_system_prompt(context_pool, track_count)
    user_message = (
        f"Please create a {track_count}-track playlist for: {user_prompt}"
    )
    logger.info(
        "Built prompt for %d tracks with %d keyword(s).",
        track_count,
        len(keywords),
    )
    return system_prompt, user_message

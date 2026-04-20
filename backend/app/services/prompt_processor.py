"""
Prompt processor — NLP keyword extraction and LLM system-prompt builder.

Pipeline:
  1. Pass user prompt to LLM to extract smart search terms (genres, moods, artists).
  2. Query the local SQLite cache for matching artists, genres, and tracks using those terms.
  3. Build a structured system prompt instructing the LLM to select
     tracks exclusively from the user's library.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from typing import Callable, Optional

from ollama import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.schemas import PlaylistIntent, PlaylistResponse, SeedSelection
from app.models.tables import Track
from app.services.library_search import (
    get_distinct_artists,
    get_distinct_genres,
    get_artists_by_genres,
    search_tracks_by_keywords,
)
from app.services.vector_index import search_vector_index
from app.trace import get_trace_id

logger = logging.getLogger(__name__)

MAX_CONTEXT_ITEMS = 40

# Stopwords for keyword extraction
_STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from",
    "has", "he", "in", "is", "it", "of", "on", "or", "that", "the",
    "to", "was", "will", "with", "you", "your", "me", "my", "what",
    "when", "where", "which", "who", "why", "how", "but", "if", "so",
}

# ---------------------------------------------------------------------------
# Phase 5: Keyword extraction (missing implementation)
# ---------------------------------------------------------------------------


def extract_keywords(text: str) -> list[str]:
    """Extract meaningful keywords from text by tokenizing and filtering.

    Tokenizes on whitespace and punctuation, removes stopwords and single chars,
    and deduplicates results. Returns lowercased, alphanumeric-only terms.

    Args:
        text: Input string to extract keywords from.

    Returns:
        List of cleaned, lowercase keyword strings.
    """
    logger.info("KEYWORDS | INPUT: %r", text)
    
    # Tokenize: split on whitespace and punctuation
    tokens = re.findall(r"\b\w+\b", text.lower())

    # Filter: remove stopwords, single chars, and deduplicate
    keywords = []
    seen = set()
    for token in tokens:
        if token not in _STOPWORDS and len(token) > 1 and token not in seen:
            keywords.append(token)
            seen.add(token)

    logger.info("KEYWORDS | EXTRACTED: %s", keywords)
    return keywords


# ---------------------------------------------------------------------------
# Phase 5: Intent parsing (structured semantic extraction)
# ---------------------------------------------------------------------------

_INTENT_PARSER_PROMPT = """\
Analyze the user's music playlist request and extract a structured intent.

Return a JSON object with:
- mood: Emotional vibe (e.g., "relaxed", "energetic", "melancholic", "happy"). Leave EMPTY if not explicitly mentioned.
- tempo: Tempo preference (e.g., "slow", "medium", "fast"). Leave EMPTY if not explicitly mentioned.
- genre_hint: Optional primary genre (e.g., "jazz", "rock", "hiphop", "ambient"). If user mentions ANY music genre/style, extract it here. Leave empty if no genre requested.
- exclude: List of terms to exclude (e.g., ["christmas", "sad"]).

CRITICAL RULES:
1. GENRE DETECTION: If user says "hiphop", "hip-hop", "rap", "r&b", "trap", "jazz", "rock", "pop", "metal", "indie", "electronic", "ambient", "lo-fi", etc., extract it as genre_hint.
2. Only populate mood/tempo if EXPLICITLY stated in request. Do NOT infer defaults.
3. If user asks to avoid something (e.g., "no sad songs", "no christmas"), populate exclude.
4. Return ONLY valid JSON conforming to the schema.

Examples:
- "gimme some true hiphop" → {{"mood": "", "tempo": "", "genre_hint": "hiphop", "exclude": []}}
- "relaxed jazz afternoon" → {{"mood": "relaxed", "tempo": "", "genre_hint": "jazz", "exclude": []}}
- "upbeat pop no sad stuff" → {{"mood": "upbeat", "tempo": "", "genre_hint": "pop", "exclude": ["sad"]}}

User Request: "{user_prompt}"
"""


async def parse_intent(user_prompt: str) -> PlaylistIntent:
    """Extract structured intent from user prompt via Ollama (Gemma).

    Calls the LLM to parse mood, tempo, genre hints, and exclusions from the
    natural language request, returning a structured PlaylistIntent for vector
    search and seed selection.

    Args:
        user_prompt: Natural-language playlist request.

    Returns:
        PlaylistIntent with mood, tempo, genre_hint, exclude fields.

    Raises:
        RuntimeError: If Ollama is unreachable or response is invalid JSON.
    """
    client = AsyncClient(host=settings.OLLAMA_BASE_URL)
    schema = PlaylistIntent.model_json_schema()
    prompt_text = _INTENT_PARSER_PROMPT.format(user_prompt=user_prompt)

    try:
        response = await client.chat(
            model=settings.DEFAULT_MODEL,
            messages=[{"role": "user", "content": prompt_text}],
            format=schema,
            options={"temperature": 0},
        )
    except Exception as exc:
        logger.error(f"Failed to parse intent: {exc}")
        raise RuntimeError(f"Intent parsing failed: {exc}") from exc

    raw = response.message.content
    logger.debug(f"Intent parser response: {raw}")
    intent = PlaylistIntent.model_validate(json.loads(raw))
    logger.info(f"Parsed intent: mood={intent.mood}, tempo={intent.tempo}, exclude={intent.exclude}")
    return intent


# ---------------------------------------------------------------------------
# Phase 5: Seed selection (pick best candidates for sonic expansion)
# ---------------------------------------------------------------------------

_SEED_SELECTOR_PROMPT = """\
Given a list of candidate tracks and a musical vibe, select the 2-3 BEST tracks
to use as seeds for semantic expansion. These will be passed to Plex's sonic engine
for finding similar tracks.

CRITERIA:
- Vibe: {mood} mood, {tempo} tempo, {genre_hint} genre
- Best fits the mood and tempo described above.
- Diverse enough to avoid repetitive expansion.

Candidates:
{candidates_list}

Return a JSON object with "indices" = [1-based positions of selected tracks].
Example: {{"indices": [2, 5]}}
"""


async def select_seeds(
    intent: PlaylistIntent,
    candidates: list[Track],
    on_event: Optional[Callable] = None,
) -> list[Track]:
    """Ask Gemma to pick the 2–3 best sonic seeds from candidate tracks.

    Filters candidates by exclude list and optional genre_hint, then sends 
    remaining candidates to Ollama for semantic selection based on mood/tempo/genre_hint.

    Args:
        intent:      Extracted PlaylistIntent (mood, tempo, genre, exclude).
        candidates:  Full list of candidate Track objects from vector search.
        on_event:    Optional callback for streaming events.

    Returns:
        List of 2–3 Track objects selected as sonic seeds.
    """
    # Filter by exclude list, and reorder by genre_hint match
    excluded_tracks = []
    genre_matched = []
    other_tracks = []
    
    for track in candidates:
        skip = False
        
        # Check exclude list
        for exclude_term in intent.exclude:
            exclude_lower = exclude_term.lower()
            if (exclude_lower in (track.genre or "").lower() or
                exclude_lower in (track.style or "").lower() or
                exclude_lower in track.title.lower() or
                exclude_lower in track.artist.lower()):
                skip = True
                break
        
        if skip:
            excluded_tracks.append(track)
            continue
        
        # Categorize by genre match: genre-matched tracks first (better for selection)
        if intent.genre_hint:
            genre_hint_lower = intent.genre_hint.lower()
            track_genre = (track.genre or "").lower()
            track_style = (track.style or "").lower()
            # Check if track's genre/style contains the hint
            if (genre_hint_lower in track_genre or 
                genre_hint_lower in track_style or
                track_genre.find(genre_hint_lower) != -1):
                genre_matched.append(track)
            else:
                other_tracks.append(track)
        else:
            other_tracks.append(track)
    
    # Reorder: genre-matched first, then others
    filtered_candidates = genre_matched + other_tracks

    if not filtered_candidates:
        # Fallback: if genre filtering was too strict, relax it
        if intent.genre_hint:
            logger.warning(
                f"No candidates matched genre_hint '{intent.genre_hint}'; "
                "relaxing filter to use top 2 from all candidates."
            )
        else:
            logger.warning("All candidates filtered by exclude list; using top 2 anyway.")
        return candidates[:2]

    # Build candidate list string
    candidates_list = "\n".join([
        f"{i}. {t.title} — {t.artist} ({t.genre or 'Unknown'})"
        for i, t in enumerate(filtered_candidates, start=1)
    ])

    # When genre_hint is present, prioritize it in the seed selection prompt
    genre_emphasis = ""
    if intent.genre_hint and genre_matched:
        genre_emphasis = f"\n⭐ NOTE: Prefer tracks from the top of the list (genre-matched to {intent.genre_hint}) if possible."
    
    prompt_text = _SEED_SELECTOR_PROMPT.format(
        mood=intent.mood or "(any mood)",
        tempo=intent.tempo or "(any tempo)",
        genre_hint=intent.genre_hint or "(any)",
        candidates_list=candidates_list,
    ) + genre_emphasis

    client = AsyncClient(host=settings.OLLAMA_BASE_URL)
    schema = SeedSelection.model_json_schema()

    try:
        response = await client.chat(
            model=settings.DEFAULT_MODEL,
            messages=[{"role": "user", "content": prompt_text}],
            format=schema,
            options={"temperature": 0},
        )
    except Exception as exc:
        logger.error(f"Failed to select seeds: {exc}")
        # Fallback: return top 2
        return filtered_candidates[:2]

    raw = response.message.content
    logger.debug(f"Seed selector response: {raw}")
    try:
        selection = SeedSelection.model_validate(json.loads(raw))
        # Map 1-based indices to Track objects
        selected = []
        for idx in selection.indices:
            if 1 <= idx <= len(filtered_candidates):
                selected.append(filtered_candidates[idx - 1])
        if selected:
            logger.info(f"Selected {len(selected)} seeds: {[t.title for t in selected]}")
            return selected
        else:
            logger.warning("Selected indices out of range; using top 2 fallback.")
            return filtered_candidates[:2]
    except Exception as exc:
        logger.warning(f"Seed selection parsing failed: {exc}; using fallback.")
        return filtered_candidates[:2]

# ---------------------------------------------------------------------------
# Pass 1: Term Extraction Prompt Builder
# ---------------------------------------------------------------------------

_TERM_EXTRACTOR_PROMPT = """\
Analyze the following music playlist request and extract 3 to 5 single-word search terms (genres, moods, or artists) to query a database. 

CRITICAL INSTRUCTIONS:
- If the user explicitly asks NOT to play a certain type of music, DO NOT include that term. Instead, output terms that represent the OPPOSITE mood.
- Ignore seasonal/holiday terms if they do not match the current time of year.
- Return ONLY a comma-separated list of lowercase words. Do not include any conversational text.

User Request: "{user_prompt}"
"""


def build_term_extraction_prompt(user_prompt: str) -> str:
    """Builds the prompt to ask the LLM for database search terms."""
    return _TERM_EXTRACTOR_PROMPT.format(user_prompt=user_prompt)

# ---------------------------------------------------------------------------
# Context pool builder
# ---------------------------------------------------------------------------


async def build_context_pool(
    session: AsyncSession,
    search_terms: list[str],
    vector_query: str | None = None,
    genre_hint: str | None = None,
    on_event: Optional[Callable] = None,
) -> dict[str, list[str]]:
    """Query the cache and return matching artists, genres, and sample tracks.

    Phase 5 variant: Uses vector search (semantic similarity) instead of LIKE queries
    if vector_query is provided. Falls back to keyword-based matching.
    
    If genre_hint is provided, prioritizes that genre in results.

    Args:
        session:       Async DB session.
        search_terms:  Smart search terms generated by the LLM (legacy support).
        vector_query:  Optional semantic query string for vector search (Phase 5).
        genre_hint:    Optional genre to prioritize (e.g., "hiphop", "jazz").
        on_event:      Optional callback for streaming events.

    Returns:
        Dict with keys "artists", "genres", "sample_tracks".
    """
    logger.info(
        "CONTEXT_POOL | START | search_terms=%s | vector_query=%r | genre_hint=%r",
        search_terms,
        vector_query,
        genre_hint,
    )
    
    all_artists = await get_distinct_artists(session)
    all_genres = await get_distinct_genres(session)
    
    logger.info("CONTEXT_POOL | Available genres (%d): %s", len(all_genres), all_genres[:10])
    
    sample_tracks: list[str] = []

    # Phase 5: Try vector search if query provided
    if vector_query:
        try:
            rating_keys = search_vector_index(vector_query, top_k=MAX_CONTEXT_ITEMS)
            if rating_keys:
                # Load Track objects from database
                result = await session.execute(
                    select(Track).where(Track.rating_key.in_(rating_keys))
                )
                tracks = result.scalars().all()
                sample_tracks = [
                    f"{t.title} — {t.artist}" + (f" [{t.album}]" if t.album else "")
                    for t in tracks
                ]
                logger.info(f"Vector search found {len(sample_tracks)} tracks for '{vector_query}'")
        except Exception as exc:
            logger.warning(f"Vector search failed: {exc}; falling back to keyword search.")
            sample_tracks = []

    # Fallback: keyword-based search if vector search didn't return results
    if not sample_tracks and search_terms:
        kw_lower = {k.lower() for k in search_terms}

        matching_artists = [
            a for a in all_artists
            if any(kw in a.lower() for kw in kw_lower)
        ][:MAX_CONTEXT_ITEMS]

        matching_genres = [
            g for g in all_genres
            if any(kw in g.lower() for kw in kw_lower)
        ][:MAX_CONTEXT_ITEMS]

        tracks = await search_tracks_by_keywords(session, search_terms, limit=MAX_CONTEXT_ITEMS)
        sample_tracks = [
            f"{t.title} — {t.artist}" + (f" [{t.album}]" if t.album else "")
            for t in tracks
        ]
    else:
        # Extract artist/genre from sample tracks already loaded
        matching_artists = list({t.artist for t in [
            Track(artist=a, title="", rating_key=0)  # Dummy for type safety
            for a in all_artists
        ]})[:MAX_CONTEXT_ITEMS] if all_artists else []
        matching_genres = all_genres[:MAX_CONTEXT_ITEMS] if all_genres else []

    # If genre_hint provided, prioritize matching genre
    if genre_hint:
        genre_hint_lower = genre_hint.lower()
        # Normalize genre hint: remove spaces, hyphens, parentheses
        genre_hint_normalized = re.sub(r'[\s\-\(\)]', '', genre_hint_lower)
        
        # Find genres that match the hint (allowing flexible spacing/punctuation)
        matching_genre_for_hint = [
            g for g in all_genres
            if genre_hint_normalized in re.sub(r'[\s\-\(\)]', '', g.lower())
            or genre_hint_lower in g.lower()
        ]
        if matching_genre_for_hint:
            # Re-prioritize genres with the matching one first
            matching_genres = matching_genre_for_hint + [
                g for g in matching_genres if g not in matching_genre_for_hint
            ]
            logger.info(
                f"Genre hint '{genre_hint}' matched {len(matching_genre_for_hint)} genres: {matching_genre_for_hint}"
            )
            
            # Get artists filtered by these genres
            genre_filtered_artists = await get_artists_by_genres(session, matching_genre_for_hint)
            if genre_filtered_artists:
                matching_artists = genre_filtered_artists[:MAX_CONTEXT_ITEMS]
                logger.info(
                    f"Genre filter found {len(genre_filtered_artists)} artists for genres {matching_genre_for_hint}"
                )

    # Broad fallback if no matches
    if not matching_artists:
        matching_artists = all_artists[:MAX_CONTEXT_ITEMS]
    if not matching_genres:
        matching_genres = all_genres[:MAX_CONTEXT_ITEMS]

    logger.info(
        "CONTEXT_POOL | COMPLETE | artists=%d | genres=%d | samples=%d",
        len(matching_artists),
        len(matching_genres),
        len(sample_tracks),
    )

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
Focus on titles and artists that match the context provided below.

## Real-World Context
Current Date: {current_date}
Current Season: {current_season}

## Library Context
Artists available in library:
{artists}

Genres available in library:
{genres}

Sample matching tracks from your search:
{sample_tracks}

## Instructions
- Select exactly {track_count} tracks from the user's library.
- Suggest track titles and artists that exist in the context above.
- Prioritise tracks matching the mood, genre, or feel of the user's request.
- Provide a concise reasoning for each track (1-2 sentences).

## Negative Constraints (CRITICAL)
- DO NOT include holiday-specific music (e.g., Christmas, Halloween, Thanksgiving) UNLESS the user explicitly requests it, or it perfectly matches the Current Season provided above.
- If the prompt is broad (e.g., "rainy sunday afternoon"), default to universally appropriate tracks and avoid highly niche, depressing, or holiday-themed extremes.

- Return ONLY a valid JSON object conforming to this schema:
{schema}
"""


def get_current_season() -> str:
    """Helper to determine the current season based on the month."""
    month = datetime.now().month
    if month in [12, 1, 2]:
        return "Winter"
    elif month in [3, 4, 5]:
        return "Spring"
    elif month in [6, 7, 8]:
        return "Summer"
    else:
        return "Autumn/Fall"


def build_system_prompt(
    context_pool: dict[str, list[str]],
    track_count: int,
) -> str:
    """Build the system prompt injected into the LLM conversation."""
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
    
    # Inject real-world context
    current_date = datetime.now().strftime("%B %d, %Y")
    current_season = get_current_season()

    prompt = _SYSTEM_PROMPT_TEMPLATE.format(
        current_date=current_date,
        current_season=current_season,
        max_items=MAX_CONTEXT_ITEMS,
        artists=artists_block,
        genres=genres_block,
        sample_tracks=tracks_block,
        track_count=track_count,
        schema=schema_str,
    )
    
    logger.info(
        "SYSTEM_PROMPT | track_count=%d | artists_sample=%s | genres_sample=%s",
        track_count,
        list(context_pool["artists"])[:3] if context_pool["artists"] else [],
        list(context_pool["genres"])[:3] if context_pool["genres"] else [],
    )
    
    return prompt


async def build_prompt(
    session: AsyncSession,
    user_prompt: str,
    search_terms: list[str],
    track_count: int,
    intent: PlaylistIntent | None = None,
) -> tuple[str, str]:
    """Full pipeline: smart terms → context pool → system + user prompts.

    Args:
        session:      Async DB session.
        user_prompt:  Raw user input.
        search_terms: Smart search terms generated by the LLM pass 1.
        track_count:  Number of tracks requested.
        intent:       Optional parsed intent with genre_hint, mood, etc.

    Returns:
        Tuple of (system_prompt, user_message) ready for the LLM.
    """
    logger.info("BUILD_PROMPT | START | user_prompt=%r | track_count=%d", user_prompt, track_count)
    
    genre_hint = intent.genre_hint if intent else None
    context_pool = await build_context_pool(
        session, search_terms, genre_hint=genre_hint
    )
    system_prompt = build_system_prompt(context_pool, track_count)
    user_message = (
        f"Please create a {track_count}-track playlist for: {user_prompt}"
    )
    
    logger.info("BUILD_PROMPT | COMPLETE | user_message_len=%d", len(user_message))
    
    return system_prompt, user_message

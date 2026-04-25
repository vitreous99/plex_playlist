"""
Playlist assembly pipeline.
"""

import logging
from typing import Callable, Optional, Sequence

from sqlalchemy.ext.asyncio import AsyncSession
from plexapi.audio import Track as PlexTrack

from app.services.ollama_client import generate_playlist
from app.services.track_matcher import match_tracks
from app.services.sonic_engine import expand_with_sonic_similarity, build_sonic_adventure
from app.services.prompt_processor import extract_keywords, build_context_pool, build_system_prompt, parse_intent

logger = logging.getLogger(__name__)

async def build_playlist(
    session: AsyncSession,
    prompt: str,
    track_count: int,
    on_event: Optional[Callable] = None,
) -> list[PlexTrack]:
    """
    Orchestrate the full playlist building pipeline.
    
    1. Generate suggestions using LLM
    2. Match suggestions to local Plex cache (with retry on failure)
    3. Expand matched tracks using Sonic features
    
    Args:
        session: Async database session.
        prompt: User prompt.
        track_count: Target number of tracks.
        on_event: Optional callback for streaming events.
    """
    logger.info(f"Building playlist for prompt: '{prompt}' (target: {track_count})")
    
    # 1. Generate suggestions via LLM
    # We ask for a smaller number of seeds to then expand sonically
    seed_count = min(track_count, max(5, track_count // 4)) 
    
    # Detect if this is a transition prompt
    is_transition = "start with" in prompt.lower() and "end with" in prompt.lower()
    
    if is_transition:
        # For transition, we just need 2 endpoints
        seed_count = 2
    
    # Build the system prompt from context
    keywords = extract_keywords(prompt)
    intent = await parse_intent(prompt)
    context_pool = await build_context_pool(
        session,
        keywords,
        vector_query=prompt,
        genre_hint=intent.genre_hint or None,
        on_event=on_event,
    )
    system_prompt = build_system_prompt(context_pool, seed_count, intent=intent)
    
    llm_response = await generate_playlist(system_prompt, prompt, seed_count, on_event=on_event)
    
    # 2. Match tracks with retry logic
    matched, unmatched = await match_tracks(session, llm_response.tracks, on_event=on_event)
    
    # If matching fails initially, retry with lower threshold
    if not matched and unmatched:
        logger.warning(
            f"Initial matching failed for all {len(unmatched)} tracks. "
            f"Retrying with relaxed matching threshold."
        )
        # Retry with even lower threshold
        matched, unmatched = await match_tracks(session, llm_response.tracks, threshold=0.6, on_event=on_event)
    
    if not matched:
        # Log diagnostic info
        logger.error(
            f"Could not match any suggested tracks to the local database. "
            f"Attempted tracks: {[f'{t.title} by {t.artist}' for t in llm_response.tracks]}"
        )
        return []
        
    logger.info(f"Successfully matched {len(matched)} / {len(llm_response.tracks)} suggested tracks")
    
    # 3. Sonic Expansion
    if is_transition and len(matched) >= 2:
        logger.info("Transition prompt detected. Using Sonic Adventure.")
        return build_sonic_adventure(
            source_track=matched[0],
            target_track=matched[-1],
            target_count=track_count,
            on_event=on_event,
        )
    else:
        logger.info("Using standard Sonic Similarity expansion.")
        return expand_with_sonic_similarity(
            seed_tracks=matched,
            target_count=track_count,
            on_event=on_event,
        )

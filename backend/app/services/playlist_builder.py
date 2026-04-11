"""
Playlist assembly pipeline.
"""

import logging
from typing import Sequence

from sqlalchemy.ext.asyncio import AsyncSession
from plexapi.audio import Track as PlexTrack

from app.services.ollama_client import generate_playlist
from app.services.track_matcher import match_tracks
from app.services.sonic_engine import expand_with_sonic_similarity, build_sonic_adventure

logger = logging.getLogger(__name__)

async def build_playlist(
    session: AsyncSession,
    prompt: str,
    track_count: int
) -> list[PlexTrack]:
    """
    Orchestrate the full playlist building pipeline.
    
    1. Generate suggestions using LLM
    2. Match suggestions to local Plex cache
    3. Expand matched tracks using Sonic features
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
        
    llm_response = await generate_playlist(session, prompt, seed_count)
    
    # 2. Match tracks
    matched, unmatched = await match_tracks(session, llm_response.tracks)
    
    if not matched:
        logger.error("Could not match any suggested tracks to the local database.")
        return []
        
    # 3. Sonic Expansion
    if is_transition and len(matched) >= 2:
        logger.info("Transition prompt detected. Using Sonic Adventure.")
        return build_sonic_adventure(
            source_track=matched[0],
            target_track=matched[-1],
            target_count=track_count
        )
    else:
        logger.info("Using standard Sonic Similarity expansion.")
        return expand_with_sonic_similarity(
            seed_tracks=matched,
            target_count=track_count
        )

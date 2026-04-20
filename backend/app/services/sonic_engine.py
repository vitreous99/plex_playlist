"""
Sonic Engine module.

Handles expansion of seed tracks using Plex's sonic analysis features.
"""

import logging
from typing import Callable, Optional, Sequence

from plexapi.audio import Track as PlexTrack

from app.models.tables import Track as DbTrack
from app.services.plex_client import get_music_section

logger = logging.getLogger(__name__)


def expand_with_sonic_similarity(
    seed_tracks: Sequence[DbTrack],
    target_count: int = 20,
    max_distance: float = 0.25,
    on_event: Optional[Callable] = None,
) -> list[PlexTrack]:
    """
    Expand a list of seed tracks using Plex's sonicallySimilar feature.
    
    Args:
        seed_tracks: List of DbTrack objects to use as seeds.
        target_count: Desired length of the final playlist.
        max_distance: Maximum sonic distance for similarity.
        on_event: Optional callback for streaming events.
        
    Returns:
        A deduplicated list of PlexTrack objects.
    """
    if not seed_tracks:
        return []

    try:
        section = get_music_section()
    except Exception as e:
        logger.error(f"Failed to get Plex music section for sonic expansion: {e}")
        return []

    # Get the actual Plex objects for the seed tracks
    plex_seeds = []
    for st in seed_tracks:
        try:
            item = section.fetchItem(st.rating_key)
            # Relax the type check for tests that use mocks
            if hasattr(item, 'ratingKey') and hasattr(item, 'sonicallySimilar'):
                plex_seeds.append(item)
        except Exception as e:
            logger.warning(f"Could not fetch Plex track {st.rating_key}: {e}")

    if not plex_seeds:
        return []

    # Build the final list, starting with our seeds
    final_playlist: list[PlexTrack] = []
    seen_keys: set[int] = set()

    for ptrack in plex_seeds:
        if ptrack.ratingKey not in seen_keys:
            final_playlist.append(ptrack)
            seen_keys.add(ptrack.ratingKey)

    if len(final_playlist) >= target_count:
        return final_playlist[:target_count]

    # Calculate how many similar tracks to request per seed to reach the target
    remaining = target_count - len(final_playlist)
    per_seed = (remaining // len(plex_seeds)) + 2  # Request a bit extra for deduplication margin

    logger.info(f"Expanding {len(plex_seeds)} seeds. Need {remaining} more tracks. Fetching ~{per_seed} per seed.")

    for seed_idx, ptrack in enumerate(plex_seeds):
        try:
            # Emit event safely if callback provided
            if on_event:
                try:
                    artist_name = getattr(ptrack.artist, 'title', 'Unknown') if hasattr(ptrack, 'artist') else "Unknown"
                    on_event({
                        "phase": "sonic",
                        "step": f"sonic_seed_{seed_idx+1}",
                        "message": f"Searching for tracks similar to: {ptrack.title}",
                        "detail": {
                            "seed_number": seed_idx + 1,
                            "seed_title": str(ptrack.title),
                            "seed_artist": str(artist_name),
                        },
                        "timing_ms": 0,
                        "progress": 0.75 + (0.2 * (seed_idx / max(len(plex_seeds), 1))),
                    })
                except Exception as e:
                    logger.debug(f"Error emitting sonic_seed event for '{ptrack.title}': {e}")

            # Fetch similar tracks safely
            try:
                similar = ptrack.sonicallySimilar(limit=per_seed, maxDistance=max_distance)
                if not similar:
                    logger.debug(f"No similar tracks found for '{ptrack.title}'")
                    continue
            except Exception as e:
                logger.warning(f"sonicallySimilar failed for '{ptrack.title}': {e}")
                continue
            
            # Process similar tracks with defensive checks
            for sim_track in similar:
                try:
                    # Defensive check for ratingKey attribute
                    if not hasattr(sim_track, 'ratingKey'):
                        logger.debug(f"Skipping track without ratingKey: {sim_track}")
                        continue
                    
                    track_key = sim_track.ratingKey
                    if track_key not in seen_keys:
                        final_playlist.append(sim_track)
                        seen_keys.add(track_key)
                        
                        if len(final_playlist) >= target_count:
                            return final_playlist[:target_count]
                except Exception as e:
                    logger.debug(f"Error processing similar track: {e}")
                    continue
                    
        except Exception as e:
            logger.warning(f"Could not expand from seed '{ptrack.title}': {e}")

    return final_playlist


def build_sonic_adventure(
    source_track: DbTrack,
    target_track: DbTrack,
    target_count: int = 20,
    on_event: Optional[Callable] = None,
) -> list[PlexTrack]:
    """
    Build an acoustic path between two tracks using Plex's sonicAdventure.
    
    Args:
        source_track: Starting track.
        target_track: Ending track.
        target_count: Desired number of intermediate tracks.
        on_event: Optional callback for streaming events.
    """
    try:
        section = get_music_section()
    except Exception as e:
        logger.error(f"Failed to get Plex music section for sonic adventure: {e}")
        return []

    try:
        source_plex = section.fetchItem(source_track.rating_key)
        target_plex = section.fetchItem(target_track.rating_key)
        
        # Relax type check for mocks
        if not hasattr(source_plex, 'sonicAdventure'):
            logger.error("Source or target track does not support sonic adventure.")
            return []
            
    except Exception as e:
        logger.error(f"Could not fetch tracks for sonic adventure: {e}")
        return []

    if on_event:
        try:
            source_title = str(getattr(source_plex, 'title', 'Unknown'))
            target_title = str(getattr(target_plex, 'title', 'Unknown'))
            on_event({
                "phase": "sonic",
                "step": "sonic_adventure_start",
                "message": f"Building transition from {source_title} to {target_title}",
                "detail": {
                    "source_title": source_title,
                    "target_title": target_title,
                },
                "timing_ms": 0,
                "progress": 0.75,
            })
        except Exception as e:
            logger.debug(f"Error emitting sonic_adventure_start event: {e}")

    try:
        # Request sonic adventure with error handling
        adventure_tracks = source_plex.sonicAdventure(to=target_plex)
        if not adventure_tracks:
            logger.warning("sonicAdventure returned no tracks")
            return []
        
        # Deduplicate and limit with defensive checks
        final_path: list[PlexTrack] = []
        seen_keys: set[int] = set()
        
        for track in adventure_tracks:
            try:
                if not hasattr(track, 'ratingKey'):
                    logger.debug(f"Skipping adventure track without ratingKey: {track}")
                    continue

                track_key = track.ratingKey
                if track_key not in seen_keys:
                    final_path.append(track)
                    seen_keys.add(track_key)
            except Exception as e:
                logger.debug(f"Error processing adventure track: {e}")
                continue
                
        if not final_path:
            logger.warning("No deduplicated tracks from sonic adventure")
            return []
                
        if len(final_path) > target_count:
            step = len(final_path) / target_count
            sampled = [final_path[int(i * step)] for i in range(target_count - 1)]
            sampled.append(final_path[-1])  # Ensure target is reached
            return sampled
            
        return final_path
    except Exception as e:
        logger.error(f"Sonic adventure failed: {e}", exc_info=True)
        return []

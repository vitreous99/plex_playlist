"""
Sonic Engine module.

Handles expansion of seed tracks using Plex's sonic analysis features.
"""

import logging
from typing import Sequence

from plexapi.audio import Track as PlexTrack

from app.models.tables import Track as DbTrack
from app.services.plex_client import get_music_section

logger = logging.getLogger(__name__)

def expand_with_sonic_similarity(
    seed_tracks: Sequence[DbTrack],
    target_count: int = 20,
    max_distance: float = 0.25
) -> list[PlexTrack]:
    """
    Expand a list of seed tracks using Plex's sonicallySimilar feature.
    
    Args:
        seed_tracks: List of DbTrack objects to use as seeds.
        target_count: Desired length of the final playlist.
        max_distance: Maximum sonic distance for similarity.
        
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

    for ptrack in plex_seeds:
        try:
            # Check if track has sonic data by calling sonicallySimilar
            # (PlexAPI might raise an error if not analyzed, or return empty list)
            similar = ptrack.sonicallySimilar(limit=per_seed, maxDistance=max_distance)
            
            for sim_track in similar:
                if sim_track.ratingKey not in seen_keys:
                    final_playlist.append(sim_track)
                    seen_keys.add(sim_track.ratingKey)
                    
                    if len(final_playlist) >= target_count:
                        return final_playlist[:target_count]
        except Exception as e:
            logger.debug(f"Could not get similar tracks for '{ptrack.title}': {e}")

    return final_playlist

def build_sonic_adventure(
    source_track: DbTrack,
    target_track: DbTrack,
    target_count: int = 20
) -> list[PlexTrack]:
    """
    Build an acoustic path between two tracks using Plex's sonicAdventure.
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

    try:
        # Request sonic adventure
        adventure_tracks = source_plex.sonicAdventure(to=target_plex)
        
        # Deduplicate and limit
        final_path: list[PlexTrack] = []
        seen_keys: set[int] = set()
        
        for track in adventure_tracks:
            if hasattr(track, 'ratingKey') and track.ratingKey not in seen_keys:
                final_path.append(track)
                seen_keys.add(track.ratingKey)
                
        if len(final_path) > target_count:
            step = len(final_path) / target_count
            sampled = [final_path[int(i * step)] for i in range(target_count - 1)]
            sampled.append(final_path[-1]) # Ensure target is reached
            return sampled
            
        return final_path
    except Exception as e:
        logger.error(f"Sonic adventure failed: {e}")
        return []

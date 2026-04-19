"""
Plex client discovery and playback dispatcher.
"""

import logging
from typing import Sequence

from plexapi.audio import Track as PlexTrack
from plexapi.playqueue import PlayQueue

from app.services.plex_client import get_server

logger = logging.getLogger(__name__)

def get_clients() -> list[dict]:
    """Discover available playback clients on the Plex network."""
    try:
        server = get_server()
        clients = server.clients()
        
        return [
            {
                "name": client.title,
                "identifier": client.machineIdentifier,
                "product": client.product,
                "address": getattr(client, "address", "Unknown")
            }
            for client in clients
        ]
    except Exception as e:
        logger.error(f"Failed to fetch Plex clients: {e}")
        return []

def dispatch_playback(tracks: Sequence[PlexTrack], client_name: str) -> dict:
    """
    Create a PlayQueue and push it to the specified client.
    """
    if not tracks:
        raise ValueError("No tracks provided for playback.")
        
    try:
        server = get_server()
        client = server.client(client_name)
    except Exception as e:
        logger.error(f"Client '{client_name}' not found: {e}")
        raise ValueError(f"Client '{client_name}' not found or unreachable.") from e

    try:
        logger.info(f"Creating PlayQueue with {len(tracks)} tracks")
        # Ensure we pass the server and tracks list
        # Depending on plexapi version, items could be a list
        playqueue = PlayQueue.create(server, items=list(tracks))
        
        logger.info(f"Dispatching playback to {client_name}")
        client.playMedia(playqueue)
        
        return {
            "status": "playing",
            "client": client_name,
            "track_count": len(tracks)
        }
    except Exception as e:
        logger.error(f"Playback dispatch failed: {e}")
        # Try proxyThroughServer if direct play fails
        try:
            logger.info("Attempting playback via proxyThroughServer")
            client.proxyThroughServer()
            client.playMedia(playqueue)
            return {
                "status": "playing (proxied)",
                "client": client_name,
                "track_count": len(tracks)
            }
        except Exception as proxy_err:
            logger.error(f"Proxy playback also failed: {proxy_err}")
            raise RuntimeError(f"Could not dispatch playback to {client_name}") from proxy_err

"""
Plex client discovery and playback dispatcher.
"""

import asyncio
import logging
from typing import Sequence
from urllib.parse import urlparse

from plexapi.audio import Track as PlexTrack
from plexapi.playqueue import PlayQueue

from app.config import settings
from app.services.plex_client import get_server

logger = logging.getLogger(__name__)


def _lan_address_params() -> dict:
    """Return address/port overrides for playMedia using PLEX_LAN_URL.

    Plex clients receive the server address as query params in the playMedia
    command. When the app connects via 127.0.0.1, PlexAPI would embed that
    loopback address — clients on the LAN can't reach it. This extracts the
    LAN IP and port from PLEX_LAN_URL so clients stream directly from the
    local server rather than going via plex.tv relay.
    """
    lan_url = settings.PLEX_LAN_URL
    if not lan_url or lan_url == settings.PLEX_URL:
        return {}
    parsed = urlparse(lan_url)
    params = {}
    if parsed.hostname:
        params["address"] = parsed.hostname
    if parsed.port:
        params["port"] = parsed.port
    return params

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
    
    Synchronous wrapper for backward compatibility. Use dispatch_playback_async
    for the full feature set including keep-alive functionality.
    """
    # This is a sync wrapper that blocks on the async function
    # Prefer using dispatch_playback_async in new code
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(
            dispatch_playback_async(tracks, client_name)
        )
    finally:
        loop.close()


async def dispatch_playback_async(tracks: Sequence[PlexTrack], client_name: str) -> dict:
    """
    Create a PlayQueue and push it to the specified client.
    
    Also starts the keep-alive service to prevent the device from sleeping
    during playback (if enabled in configuration).
    """
    if not tracks:
        raise ValueError("No tracks provided for playback.")
        
    try:
        server = get_server()
        client = server.client(client_name)
    except Exception as e:
        logger.error(f"Client '{client_name}' not found: {e}")
        raise ValueError(f"Client '{client_name}' not found or unreachable.") from e

    lan_params = _lan_address_params()
    if lan_params:
        logger.info(f"Using LAN address override for playback: {lan_params}")

    try:
        logger.info(f"Creating PlayQueue with {len(tracks)} tracks")
        playqueue = PlayQueue.create(server, items=list(tracks))

        logger.info(f"Dispatching playback to {client_name}")
        client.playMedia(playqueue, **lan_params)
        
        # Start keep-alive task in background to prevent device sleep
        if settings.KEEP_ALIVE_ENABLED:
            try:
                from app.services.keep_alive import start_keep_alive
                shield_ip = settings.SHIELD_IP or None
                asyncio.create_task(
                    start_keep_alive(
                        duration_minutes=settings.KEEP_ALIVE_DURATION_MINUTES,
                        interval_minutes=settings.KEEP_ALIVE_INTERVAL_MINUTES,
                        shield_ip=shield_ip
                    )
                )
                logger.info("Keep-alive task started for playback")
            except Exception as e:
                logger.warning(f"Failed to start keep-alive task: {e}")
                # Don't fail playback if keep-alive fails

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
            client.playMedia(playqueue, **lan_params)
            
            # Start keep-alive task in background
            if settings.KEEP_ALIVE_ENABLED:
                try:
                    from app.services.keep_alive import start_keep_alive
                    shield_ip = settings.SHIELD_IP or None
                    asyncio.create_task(
                        start_keep_alive(
                            duration_minutes=settings.KEEP_ALIVE_DURATION_MINUTES,
                            interval_minutes=settings.KEEP_ALIVE_INTERVAL_MINUTES,
                            shield_ip=shield_ip
                        )
                    )
                    logger.info("Keep-alive task started for proxied playback")
                except Exception as ka_e:
                    logger.warning(f"Failed to start keep-alive task: {ka_e}")
            
            return {
                "status": "playing (proxied)",
                "client": client_name,
                "track_count": len(tracks)
            }
        except Exception as proxy_err:
            logger.error(f"Proxy playback also failed: {proxy_err}")
            raise RuntimeError(f"Could not dispatch playback to {client_name}") from proxy_err

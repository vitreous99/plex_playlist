"""
Device keep-alive service — prevents NVIDIA Shield from sleeping during playback.

Sends periodic ADB wake commands to keep the device active while music is playing.
"""

import asyncio
import logging
from typing import Optional
import httpx

from app.config import settings

logger = logging.getLogger(__name__)

# Global task tracking to avoid duplicate keep-alive tasks
_keep_alive_task: Optional[asyncio.Task] = None
_keep_alive_lock = asyncio.Lock()


async def _send_keep_alive_ping(shield_ip: Optional[str] = None) -> bool:
    """
    Send a keep-alive ping to the Shield via ADB bridge.
    
    Sends a KEYCODE_HOME event to keep the device awake without interrupting playback.
    
    Args:
        shield_ip: Optional Shield IP:port override
        
    Returns:
        True if ping succeeded, False otherwise
    """
    try:
        adb_url = settings.ADB_BRIDGE_URL.rstrip("/")
        ping_url = f"{adb_url}/ping"
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                ping_url,
                params={"ip": shield_ip} if shield_ip else {},
                timeout=10.0,
            )
            response.raise_for_status()
            result = response.json()
            
            if result.get("status") == "pong":
                logger.debug("Keep-alive ping sent successfully")
                return True
            else:
                logger.warning(f"Unexpected ping response: {result}")
                return False
                
    except httpx.TimeoutException:
        logger.warning("Keep-alive ping timed out")
        return False
    except httpx.ConnectError as e:
        logger.warning(f"Cannot connect to ADB bridge for keep-alive: {e}")
        return False
    except Exception as e:
        logger.warning(f"Error sending keep-alive ping: {e}")
        return False


async def _keep_alive_loop(
    duration_minutes: int = 90,
    interval_minutes: int = 10,
    shield_ip: Optional[str] = None
) -> None:
    """
    Keep device awake by sending periodic pings.
    
    Args:
        duration_minutes: Total time to keep alive (default 90 minutes)
        interval_minutes: Interval between pings (default 10 minutes)
        shield_ip: Optional Shield IP:port override
    """
    interval_seconds = interval_minutes * 60
    duration_seconds = duration_minutes * 60
    elapsed = 0
    
    logger.info(
        f"Starting keep-alive loop for {duration_minutes} minutes "
        f"(ping every {interval_minutes} minutes)"
    )
    
    while elapsed < duration_seconds:
        try:
            # Send ping
            await _send_keep_alive_ping(shield_ip)
            
            # Wait for next ping interval or until duration expires
            remaining = duration_seconds - elapsed
            wait_time = min(interval_seconds, remaining)
            
            logger.debug(f"Keep-alive: next ping in {interval_minutes} minutes")
            await asyncio.sleep(wait_time)
            elapsed += wait_time
            
        except asyncio.CancelledError:
            logger.info("Keep-alive loop cancelled")
            break
        except Exception as e:
            logger.error(f"Unexpected error in keep-alive loop: {e}")
            # Continue trying even if one ping fails
            try:
                await asyncio.sleep(interval_seconds)
                elapsed += interval_seconds
            except asyncio.CancelledError:
                break
    
    logger.info("Keep-alive loop completed")


async def start_keep_alive(
    duration_minutes: int = 90,
    interval_minutes: int = 10,
    shield_ip: Optional[str] = None
) -> None:
    """
    Start the keep-alive background task.
    
    Prevents NVIDIA Shield from sleeping during playlist playback. Creates a
    background task that sends periodic pings to keep the device active.
    
    Args:
        duration_minutes: Total time to keep alive (default 90 minutes)
        interval_minutes: Interval between pings in minutes (default 10 minutes)
        shield_ip: Optional Shield IP:port override
    """
    global _keep_alive_task
    
    async with _keep_alive_lock:
        # Cancel existing task if any
        if _keep_alive_task and not _keep_alive_task.done():
            logger.info("Cancelling existing keep-alive task")
            _keep_alive_task.cancel()
            try:
                await _keep_alive_task
            except asyncio.CancelledError:
                pass
        
        # Start new keep-alive task
        _keep_alive_task = asyncio.create_task(
            _keep_alive_loop(duration_minutes, interval_minutes, shield_ip)
        )
        logger.info("Keep-alive task started")


def cancel_keep_alive() -> None:
    """Cancel any running keep-alive task."""
    global _keep_alive_task
    
    if _keep_alive_task and not _keep_alive_task.done():
        logger.info("Cancelling keep-alive task")
        _keep_alive_task.cancel()

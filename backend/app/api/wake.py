"""
Wake Device API — orchestrates waking Nvidia Shield and launching Plexamp.

This router provides endpoints to wake the device via ADB, wait for registration,
and return the refreshed client list to the frontend.
"""

import logging
from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel
import httpx

from app.config import settings
from app.services.client_dispatcher import get_clients as fetch_clients

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/wake", tags=["Wake"])

# =============================================================================
# Models
# =============================================================================
class WakeClientResponse(BaseModel):
    """Response from wake endpoint with client list."""
    status: str  # "awake", "error"
    message: str
    clients: list = []


# =============================================================================
# Endpoints
# =============================================================================
@router.post("")
async def wake_device(shield_ip: Optional[str] = None) -> WakeClientResponse:
    """
    Wake Nvidia Shield, launch Plexamp, and return refreshed client list.

    The ADB bridge will:
    1. Connect to Shield via ADB
    2. Send KEYCODE_WAKEUP to wake the screen
    3. Launch Plexamp via am start
    4. Wait for Plexamp to register with Plex Server

    Then we refresh and return the updated client list.

    Args:
        shield_ip: Optional Shield IP:port to override SHIELD_IP config.

    Returns:
        WakeClientResponse with wake status and updated clients list.
    """
    logger.info("Wake device endpoint called")

    try:
        # Call ADB bridge wake endpoint
        adb_url = settings.ADB_BRIDGE_URL.rstrip("/")
        wake_url = f"{adb_url}/wake"
        
        logger.info(f"Calling ADB bridge at {wake_url}")
        async with httpx.AsyncClient() as client:
            response = await client.post(
                wake_url,
                params={"ip": shield_ip} if shield_ip else {},
                timeout=35.0,  # 5s buffer beyond ADB bridge's 30s operation
            )
            response.raise_for_status()
            wake_result = response.json()

        logger.info(f"ADB bridge wake result: {wake_result['status']}")

        if wake_result["status"] != "awake":
            return WakeClientResponse(
                status="error",
                message=f"ADB bridge wake failed: {wake_result.get('message', 'Unknown error')}",
                clients=[],
            )

        # Refresh client list
        logger.info("Refreshing Plex client list after wake")
        try:
            clients = fetch_clients()
            logger.info(f"Found {len(clients)} clients after wake")
        except Exception as e:
            logger.warning(f"Error fetching clients after wake: {e}")
            clients = []

        return WakeClientResponse(
            status="awake",
            message=wake_result.get("message", "Shield woken and Plexamp launched"),
            clients=clients,
        )

    except httpx.TimeoutException:
        logger.error("Wake request timed out")
        return WakeClientResponse(
            status="error",
            message="Wake operation timed out (ADB bridge unreachable or slow)",
            clients=[],
        )
    except httpx.ConnectError as e:
        logger.error(f"Cannot connect to ADB bridge at {settings.ADB_BRIDGE_URL}: {e}")
        return WakeClientResponse(
            status="error",
            message=f"Cannot connect to ADB bridge. Is it running? ({settings.ADB_BRIDGE_URL})",
            clients=[],
        )
    except Exception as e:
        logger.error(f"Unexpected error in wake endpoint: {e}", exc_info=True)
        return WakeClientResponse(
            status="error",
            message=f"Unexpected error: {str(e)}",
            clients=[],
        )

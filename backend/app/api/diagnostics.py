import logging
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.models.database import get_session
from app.models.tables import Track
from app.services.plex_client import get_server, PlexConnectionError
import httpx
from app.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/diagnostics", tags=["Diagnostics"])

async def check_ollama_health() -> bool:
    try:
        async with httpx.AsyncClient() as client:
            res = await client.get(f"{settings.OLLAMA_BASE_URL.rstrip('/')}/api/tags", timeout=5.0)
            return res.status_code == 200
    except Exception:
        return False

async def check_adb_health() -> bool:
    try:
        async with httpx.AsyncClient() as client:
            res = await client.get(f"{settings.ADB_BRIDGE_URL.rstrip('/')}/health", timeout=5.0)
            return res.status_code == 200
    except Exception:
        return False

@router.get("")
async def get_diagnostics(session: AsyncSession = Depends(get_session)):
    """Get system health diagnostics."""
    diagnostics = {
        "plex": {"status": "unknown", "message": ""},
        "ollama": {"status": "unknown", "message": ""},
        "adb_bridge": {"status": "unknown", "message": ""},
        "gpu": {"status": "unknown", "message": "Not detected"}, # Stubbed for now, could check via command line
        "sync": {"synced_tracks": 0, "last_sync": None},
        "model": settings.DEFAULT_MODEL
    }

    # Check Plex
    try:
        server = get_server()
        diagnostics["plex"] = {"status": "ok", "message": f"Connected to {server.friendlyName}"}
    except PlexConnectionError as e:
        diagnostics["plex"] = {"status": "error", "message": str(e)}
    except Exception as e:
        diagnostics["plex"] = {"status": "error", "message": f"Unexpected error: {e}"}

    # Check Ollama
    try:
        is_healthy = await check_ollama_health()
        if is_healthy:
            diagnostics["ollama"] = {"status": "ok", "message": "Connected"}
        else:
            diagnostics["ollama"] = {"status": "error", "message": "Unreachable or unhealthy"}
    except Exception as e:
        diagnostics["ollama"] = {"status": "error", "message": str(e)}

    # Check ADB Bridge
    try:
        is_healthy = await check_adb_health()
        if is_healthy:
            diagnostics["adb_bridge"] = {"status": "ok", "message": "Connected"}
        else:
            diagnostics["adb_bridge"] = {"status": "error", "message": "Unreachable or unhealthy"}
    except Exception as e:
        diagnostics["adb_bridge"] = {"status": "error", "message": str(e)}

    # Check Sync status
    try:
        stmt = select(func.count(Track.id))
        result = await session.execute(stmt)
        count = result.scalar() or 0
        
        diagnostics["sync"]["synced_tracks"] = count
        
        # Get last sync time
        stmt_time = select(func.max(Track.synced_at))
        result_time = await session.execute(stmt_time)
        last_sync = result_time.scalar()
        
        if last_sync:
            diagnostics["sync"]["last_sync"] = last_sync.isoformat()
            
    except Exception as e:
        logger.error(f"Failed to get sync diagnostics: {e}")

    return diagnostics

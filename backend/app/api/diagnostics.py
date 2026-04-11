from fastapi import APIRouter

router = APIRouter(prefix="/api/diagnostics", tags=["Diagnostics"])

@router.get("")
async def get_diagnostics():
    """Get system health diagnostics (Phase 3 Stub)."""
    return {
        "plex": {"status": "ok", "message": "Connected"},
        "ollama": {"status": "ok", "message": "Connected"},
        "gpu": {"status": "unknown", "message": "Not detected"},
        "sync": {"synced_tracks": 0, "last_sync": None},
        "model": "llama3.2:3b"
    }

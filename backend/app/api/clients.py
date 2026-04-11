from fastapi import APIRouter

router = APIRouter(prefix="/api/clients", tags=["Clients"])

@router.get("")
async def get_clients():
    """Get available Plex clients (Phase 3 Stub)."""
    return [
        {"name": "Web Client", "identifier": "web-1", "product": "Plex Web", "address": "127.0.0.1"},
        {"name": "Shield TV", "identifier": "shield-1", "product": "Plex for Android", "address": "192.168.1.10"}
    ]

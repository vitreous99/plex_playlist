from fastapi import APIRouter
from app.services.client_dispatcher import get_clients as fetch_clients

router = APIRouter(prefix="/api/clients", tags=["Clients"])

@router.get("")
async def get_clients():
    """Get available Plex clients."""
    return fetch_clients()

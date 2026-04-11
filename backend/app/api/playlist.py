from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional

router = APIRouter(prefix="/api/playlist", tags=["Playlist"])

class PlayRequest(BaseModel):
    prompt: str
    track_count: int
    client_name: Optional[str] = None

class SaveRequest(BaseModel):
    prompt: str
    track_count: int
    playlist_name: Optional[str] = None

@router.post("/play")
async def play_playlist(req: PlayRequest):
    """Dispatch playback to a specific client (Phase 3 Stub)."""
    return {
        "message": f"Playback dispatched to {req.client_name}",
        "client": req.client_name,
        "status": "playing"
    }

@router.post("/save")
async def save_playlist(req: SaveRequest):
    """Save playlist permanently in Plex (Phase 3 Stub)."""
    name = req.playlist_name or "Generated Playlist"
    return {
        "message": f"Playlist '{name}' saved successfully",
        "playlist_name": name,
        "track_count": req.track_count
    }

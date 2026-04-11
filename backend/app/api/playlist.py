import logging
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from app.models.database import get_session
from app.services.playlist_builder import build_playlist
from app.services.client_dispatcher import dispatch_playback
from app.services.plex_client import get_server

logger = logging.getLogger(__name__)

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
async def play_playlist(req: PlayRequest, session: AsyncSession = Depends(get_session)):
    """Generate a playlist and dispatch playback to a specific client."""
    if not req.client_name:
        raise HTTPException(status_code=400, detail="client_name is required for playback")
        
    try:
        tracks = await build_playlist(session, req.prompt, req.track_count)
        
        if not tracks:
            raise HTTPException(status_code=404, detail="Could not generate a matching playlist.")
            
        result = dispatch_playback(tracks, req.client_name)
        return {
            "message": f"Playback dispatched to {req.client_name}",
            "client": result["client"],
            "status": result["status"],
            "track_count": result["track_count"]
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error in play_playlist: {e}")
        raise HTTPException(status_code=500, detail="Internal server error during playback dispatch.")

@router.post("/save")
async def save_playlist(req: SaveRequest, session: AsyncSession = Depends(get_session)):
    """Generate a playlist and save it permanently in Plex."""
    name = req.playlist_name or "Generated Playlist"
    
    try:
        tracks = await build_playlist(session, req.prompt, req.track_count)
        
        if not tracks:
            raise HTTPException(status_code=404, detail="Could not generate a matching playlist.")
            
        server = get_server()
        
        # Determine the name. If it exists, plexapi might just create a duplicate
        # or we might want to check and append a number. For simplicity, we just create.
        logger.info(f"Saving playlist '{name}' with {len(tracks)} tracks to Plex.")
        from plexapi.playlist import Playlist
        Playlist.create(server, title=name, items=tracks)
        
        return {
            "message": f"Playlist '{name}' saved successfully",
            "playlist_name": name,
            "track_count": len(tracks)
        }
    except Exception as e:
        logger.error(f"Error saving playlist: {e}")
        raise HTTPException(status_code=500, detail="Failed to save playlist to Plex.")

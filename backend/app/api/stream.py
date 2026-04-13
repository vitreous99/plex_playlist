"""
SSE streaming endpoint for real-time playlist generation with activity feed.

Streams all pipeline phases (LLM → matching → sonic expansion) as Server-Sent Events
to provide live UI feedback. Results are cached server-side for fast Play/Save operations.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone
from typing import Any, AsyncGenerator, Callable, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import get_session
from app.models.schemas import PlaylistResponse, PromptRequest
from app.services.playlist_builder import build_playlist

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/playlist", tags=["Playlist Streaming"])

# ---------------------------------------------------------------------------
# Result Cache
# ---------------------------------------------------------------------------

@dataclass
class CachedPlaylist:
    """Cached playlist data from a generation."""
    generation_id: str
    playlist_response: PlaylistResponse
    tracks: list[Any]  # list[PlexTrack]
    created_at: datetime


# In-memory cache (TTL: 30 minutes)
_cache: dict[str, CachedPlaylist] = {}
_CACHE_TTL = timedelta(minutes=30)


def _cleanup_cache() -> None:
    """Remove expired cache entries."""
    now = datetime.now(timezone.utc)
    expired = [
        gen_id
        for gen_id, entry in _cache.items()
        if now - entry.created_at > _CACHE_TTL
    ]
    for gen_id in expired:
        del _cache[gen_id]
        logger.debug(f"Cache expired: {gen_id}")


def _cache_set(
    generation_id: str,
    playlist_response: PlaylistResponse,
    tracks: list[Any],
) -> None:
    """Cache a generated playlist."""
    _cleanup_cache()
    _cache[generation_id] = CachedPlaylist(
        generation_id=generation_id,
        playlist_response=playlist_response,
        tracks=tracks,
        created_at=datetime.now(timezone.utc),
    )
    logger.debug(f"Cached generation: {generation_id} ({len(tracks)} tracks)")


def _cache_get(generation_id: str) -> Optional[CachedPlaylist]:
    """Retrieve a cached playlist."""
    entry = _cache.get(generation_id)
    if entry and datetime.now(timezone.utc) - entry.created_at <= _CACHE_TTL:
        return entry
    if entry:
        del _cache[generation_id]
    return None


# ---------------------------------------------------------------------------
# SSE Event Helpers
# ---------------------------------------------------------------------------


@dataclass
class StreamEvent:
    """A single event on the generation stream."""
    phase: str  # "prompt", "llm", "matching", "sonic"
    step: str   # e.g. "keywords", "context_pool", "llm_call", "track_1_revealed", "matching", "sonic_seed_1"
    message: str  # Human-readable message
    detail: dict[str, Any] = None  # Optional structured detail
    timing_ms: int = 0  # Elapsed time for this step
    progress: float = 0.0  # 0.0 to 1.0 overall progress


def sse_format(event: StreamEvent | dict) -> str:
    """Format an event as SSE data line."""
    # Handle both StreamEvent objects and dicts from external callbacks
    if isinstance(event, dict):
        data = event
    else:
        data = {
            "phase": event.phase,
            "step": event.step,
            "message": event.message,
            "detail": event.detail or {},
            "timing_ms": event.timing_ms,
            "progress": event.progress,
        }
    return f"data: {json.dumps(data)}\n\n"


# ---------------------------------------------------------------------------
# Streaming Playlist Builder
# ---------------------------------------------------------------------------


async def build_playlist_streamed(
    session: AsyncSession,
    prompt: str,
    track_count: int,
    on_event: Callable[[StreamEvent], None],
) -> tuple[PlaylistResponse, list[Any]]:
    """
    Build a playlist with event callbacks at each step.
    
    Returns:
        Tuple of (PlaylistResponse, list[PlexTrack] matched tracks)
    """
    # Import here to avoid circular imports
    from app.services.prompt_processor import (
        extract_keywords,
        build_context_pool,
        build_system_prompt,
    )
    from app.services.ollama_client import generate_playlist
    from app.services.track_matcher import match_tracks
    from app.services.sonic_engine import (
        expand_with_sonic_similarity,
        build_sonic_adventure,
    )

    start_time = datetime.now(timezone.utc)

    def elapsed_ms() -> int:
        return int((datetime.now(timezone.utc) - start_time).total_seconds() * 1000)

    # --- Phase 1: Prompt Processing ---
    on_event(
        StreamEvent(
            phase="prompt",
            step="phase_start",
            message="Preparing prompt and context...",
            progress=0.0,
        )
    )

    # Extract keywords
    step_start = datetime.now(timezone.utc)
    keywords = extract_keywords(prompt)
    step_ms = int((datetime.now(timezone.utc) - step_start).total_seconds() * 1000)
    on_event(
        StreamEvent(
            phase="prompt",
            step="keywords",
            message=f"Extracted {len(keywords)} keywords",
            detail={"keywords": keywords},
            timing_ms=step_ms,
            progress=0.1,
        )
    )

    # Build context pool
    step_start = datetime.now(timezone.utc)
    context_pool = await build_context_pool(session, keywords)
    step_ms = int((datetime.now(timezone.utc) - step_start).total_seconds() * 1000)
    on_event(
        StreamEvent(
            phase="prompt",
            step="context_pool",
            message=f"Built context: {len(context_pool['artists'])} artists, {len(context_pool['genres'])} genres, {len(context_pool['sample_tracks'])} sample tracks",
            detail={
                "artist_count": len(context_pool["artists"]),
                "genre_count": len(context_pool["genres"]),
                "sample_count": len(context_pool["sample_tracks"]),
            },
            timing_ms=step_ms,
            progress=0.15,
        )
    )

    # Build system prompt
    system_prompt = build_system_prompt(context_pool, track_count)
    on_event(
        StreamEvent(
            phase="prompt",
            step="prompt_ready",
            message="System prompt prepared",
            progress=0.2,
        )
    )

    # --- Phase 2: LLM Generation ---
    on_event(
        StreamEvent(
            phase="llm",
            step="phase_start",
            message="Calling LLM to generate suggestions...",
            progress=0.2,
        )
    )

    step_start = datetime.now(timezone.utc)
    playlist_response = await generate_playlist(
        system_prompt, prompt, track_count, on_event=on_event
    )
    step_ms = int((datetime.now(timezone.utc) - step_start).total_seconds() * 1000)

    on_event(
        StreamEvent(
            phase="llm",
            step="phase_complete",
            message=f"LLM generated {len(playlist_response.tracks)} track suggestions",
            detail={
                "tracks_count": len(playlist_response.tracks),
                "playlist_name": playlist_response.name,
            },
            timing_ms=step_ms,
            progress=0.5,
        )
    )

    # --- Phase 3: Track Matching ---
    on_event(
        StreamEvent(
            phase="matching",
            step="phase_start",
            message=f"Matching {len(playlist_response.tracks)} suggestions to Plex library...",
            progress=0.5,
        )
    )

    step_start = datetime.now(timezone.utc)
    matched, unmatched = await match_tracks(
        session, playlist_response.tracks, on_event=on_event
    )
    step_ms = int((datetime.now(timezone.utc) - step_start).total_seconds() * 1000)

    if not matched and unmatched:
        logger.warning("Initial matching failed. Retrying with relaxed threshold...")
        matched, unmatched = await match_tracks(
            session, unmatched, threshold=0.6, on_event=on_event
        )

    if not matched:
        logger.error("Could not match any suggestions to library")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Could not match suggested tracks to your library. Try a different prompt.",
        )

    on_event(
        StreamEvent(
            phase="matching",
            step="phase_complete",
            message=f"Matched {len(matched)}/{len(playlist_response.tracks)} tracks",
            detail={"matched": len(matched), "total": len(playlist_response.tracks)},
            timing_ms=step_ms,
            progress=0.75,
        )
    )

    # --- Phase 4: Sonic Expansion ---
    on_event(
        StreamEvent(
            phase="sonic",
            step="phase_start",
            message="Expanding playlist using sonic analysis...",
            progress=0.75,
        )
    )

    step_start = datetime.now(timezone.utc)

    # Detect transition prompt
    is_transition = (
        "start with" in prompt.lower() and "end with" in prompt.lower()
    )

    try:
        if is_transition and len(matched) >= 2:
            logger.info("Transition prompt detected. Using Sonic Adventure.")
            final_tracks = build_sonic_adventure(
                source_track=matched[0],
                target_track=matched[-1],
                target_count=track_count,
                on_event=on_event,
            )
        else:
            logger.info("Using standard Sonic Similarity expansion.")
            final_tracks = expand_with_sonic_similarity(
                seed_tracks=matched,
                target_count=track_count,
                on_event=on_event,
            )
    except Exception as e:
        logger.error(f"Sonic expansion failed: {e}", exc_info=True)
        # Fall back to matched tracks if sonic expansion fails
        final_tracks = list(matched) if matched else []
        
        on_event(
            StreamEvent(
                phase="sonic",
                step="phase_warning",
                message=f"Sonic expansion encountered an error, using {len(final_tracks)} matched tracks instead",
                detail={"error": str(e)},
                progress=0.95,
            )
        )

    step_ms = int((datetime.now(timezone.utc) - step_start).total_seconds() * 1000)
    on_event(
        StreamEvent(
            phase="sonic",
            step="phase_complete",
            message=f"Expanded to {len(final_tracks)} final tracks",
            detail={"final_count": len(final_tracks)},
            timing_ms=step_ms,
            progress=0.95,
        )
    )

    # --- Complete ---
    total_ms = elapsed_ms()
    on_event(
        StreamEvent(
            phase="complete",
            step="generation_complete",
            message=f"Playlist generation complete ({total_ms}ms total)",
            detail={
                "total_time_ms": total_ms,
                "final_track_count": len(final_tracks),
            },
            progress=1.0,
        )
    )

    return playlist_response, final_tracks


# ---------------------------------------------------------------------------
# SSE Streaming Generator
# ---------------------------------------------------------------------------


async def event_stream_generator(
    session: AsyncSession,
    prompt: str,
    track_count: int,
) -> AsyncGenerator[str, None]:
    """
    Generate SSE events for playlist generation.
    
    Yields formatted SSE lines (data: {json}\n\n).
    Catches events from the pipeline via a queue and formats them.
    """
    generation_id = str(uuid.uuid4())
    event_queue: asyncio.Queue[Optional[StreamEvent]] = asyncio.Queue()

    def on_event(event: StreamEvent) -> None:
        """Callback from pipeline to queue an event."""
        asyncio.create_task(event_queue.put(event))

    async def run_pipeline() -> None:
        """Run the pipeline in a background task."""
        try:
            playlist_response, final_tracks = await build_playlist_streamed(
                session, prompt, track_count, on_event
            )
            # Cache the result
            _cache_set(generation_id, playlist_response, final_tracks)

            # Yield final complete event with all data
            final_event = StreamEvent(
                phase="complete",
                step="done",
                message="Ready to play or save",
                detail={
                    "generation_id": generation_id,
                    "playlist_name": playlist_response.name,
                    "playlist_description": playlist_response.description,
                    "tracks": [
                        {
                            "title": t.title if hasattr(t, "title") else str(t),
                            "artist": t.artist if hasattr(t, "artist") else "",
                        }
                        for t in final_tracks[:10]  # First 10 tracks in detail
                    ],
                    "total_tracks": len(final_tracks),
                },
                progress=1.0,
            )
            await event_queue.put(final_event)
        except Exception as exc:
            logger.exception("Error in pipeline streaming")
            error_event = StreamEvent(
                phase="error",
                step="pipeline_error",
                message=f"Error: {str(exc)}",
                detail={"error": str(exc), "generation_id": generation_id},
            )
            await event_queue.put(error_event)
        finally:
            # Signal completion
            await event_queue.put(None)

    # Start the pipeline task
    pipeline_task = asyncio.create_task(run_pipeline())

    # Read from queue and yield events
    while True:
        try:
            event = await asyncio.wait_for(event_queue.get(), timeout=60.0)
        except asyncio.TimeoutError:
            logger.warning(f"Event stream timeout for {generation_id}")
            timeout_event = StreamEvent(
                phase="error",
                step="timeout",
                message="Pipeline timed out",
                detail={"generation_id": generation_id},
            )
            yield sse_format(timeout_event)
            break

        if event is None:
            # Pipeline finished
            break

        yield sse_format(event)

    # Ensure pipeline task is cleaned up
    if not pipeline_task.done():
        pipeline_task.cancel()
        try:
            await pipeline_task
        except asyncio.CancelledError:
            pass


# ---------------------------------------------------------------------------
# API Endpoint
# ---------------------------------------------------------------------------


@router.post(
    "/generate-stream",
    summary="Generate playlist with real-time activity feed",
    response_class=StreamingResponse,
)
async def generate_playlist_stream(
    request: PromptRequest,
    session: AsyncSession = Depends(get_session),
) -> StreamingResponse:
    """
    Stream a playlist generation with real-time SSE events.
    
    Each event will be JSON with:
    - phase: "prompt", "llm", "matching", "sonic", "complete", "error"
    - step: detailed step identifier (e.g., "keywords", "llm_call", "track_3_revealed")
    - message: human-readable message
    - detail: structured data (keywords, track info, timing breakdown, etc.)
    - timing_ms: elapsed time for this step
    - progress: 0.0-1.0 overall progress
    
    The final event includes a generation_id that can be used for cached Play/Save.
    """
    logger.info(
        "SSE stream start: prompt=%r, track_count=%d",
        request.prompt,
        request.track_count,
    )

    return StreamingResponse(
        event_stream_generator(session, request.prompt, request.track_count),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        },
    )


@router.get("/cache/{generation_id}")
async def get_cached_playlist(generation_id: str) -> dict[str, Any]:
    """
    Retrieve cached playlist metadata and results.
    
    Used by Play/Save endpoints to avoid re-running the pipeline.
    """
    entry = _cache_get(generation_id)
    if not entry:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Generation {generation_id} not found or expired",
        )

    return {
        "generation_id": entry.generation_id,
        "playlist_name": entry.playlist_response.name,
        "playlist_description": entry.playlist_response.description,
        "track_count": len(entry.tracks),
        "created_at": entry.created_at.isoformat(),
    }

"""
Ollama API integration with retry and over-request logic.

Calls the Ollama chat endpoint using the ollama Python library in async
mode. Enforces structured JSON output via format=PlaylistResponse schema.

Retry strategy:
  - Max 3 attempts per call.
  - On JSON parse failure → immediate retry.
  - On under-count → re-prompt asking for 50% more tracks.
  - On connection error → re-raise immediately.
"""

from __future__ import annotations

import json
import logging
from typing import Callable, Optional

from ollama import AsyncClient, ResponseError

from app.config import settings
from app.models.schemas import PlaylistResponse, SuggestedTrack
from app.trace import get_trace_id

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 3


class OllamaError(RuntimeError):
    """Raised when Ollama is unreachable or returns an error."""


def _deduplicate_tracks(tracks: list[SuggestedTrack]) -> list[SuggestedTrack]:
    """Remove duplicate tracks (same title + artist, case-insensitive)."""
    seen: set[tuple[str, str]] = set()
    unique: list[SuggestedTrack] = []
    for t in tracks:
        key = (t.title.lower(), t.artist.lower())
        if key not in seen:
            seen.add(key)
            unique.append(t)
    return unique


async def _call_ollama(
    system_prompt: str,
    user_message: str,
    track_count: int,
    attempt: int,
    on_event: Optional[Callable] = None,
) -> PlaylistResponse:
    """Make a single chat call to Ollama and parse the response.

    Args:
        system_prompt: System context message.
        user_message: User request message.
        track_count: Number of tracks requested.
        attempt: Attempt number (1-based).
        on_event: Optional callback for streaming events.

    Raises:
        json.JSONDecodeError: If the response is not valid JSON.
        OllamaError: If the Ollama service returns an error.
    """
    client = AsyncClient(host=settings.OLLAMA_BASE_URL)
    schema = PlaylistResponse.model_json_schema()
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]
    
    logger.info(
        "LLM_CALL | attempt=%d/%d | model=%s | track_count=%d | system_len=%d | user_len=%d",
        attempt, MAX_ATTEMPTS, settings.DEFAULT_MODEL, track_count,
        len(system_prompt), len(user_message),
    )
    
    try:
        response = await client.chat(
            model=settings.DEFAULT_MODEL,
            messages=messages,
            format=schema,
            options={"temperature": 0},
        )
    except ResponseError as exc:
        raise OllamaError(
            f"Ollama API error (attempt {attempt}): {exc}"
        ) from exc
    except Exception as exc:
        raise OllamaError(
            f"Cannot reach Ollama at '{settings.OLLAMA_BASE_URL}' "
            f"(attempt {attempt}): {exc}"
        ) from exc

    raw: str = response.message.content
    playlist = PlaylistResponse.model_validate(json.loads(raw))
    
    logger.info(
        "LLM_RESPONSE | attempt=%d | response_len=%d | track_count=%d",
        attempt, len(raw), len(playlist.tracks),
    )
    
    return playlist


async def generate_playlist(
    system_prompt: str,
    user_message: str,
    track_count: int,
    on_event: Optional[Callable] = None,
) -> PlaylistResponse:
    """Orchestrate Ollama calls with retry and over-request logic.

    Attempt flow:
      1. Call Ollama with the given prompts.
      2. If JSON parse fails → log and retry (max MAX_ATTEMPTS).
      3. If returned tracks < track_count → ask for significantly more, accumulate,
         deduplicate, then trim to track_count on success.
      4. After MAX_ATTEMPTS failures → raise OllamaError.

    Args:
        system_prompt: System context message.
        user_message:  User request message.
        track_count:   Desired number of tracks in the final playlist.
        on_event:      Optional callback for streaming events.

    Returns:
        PlaylistResponse with up to track_count deduplicated tracks.

    Raises:
        OllamaError: If all attempts fail or Ollama is unreachable.
    """
    logger.info("GENERATE_PLAYLIST | START | requested_count=%d", track_count)
    
    all_tracks: list[SuggestedTrack] = []
    current_message = user_message
    current_count = track_count
    last_playlist: PlaylistResponse | None = None
    total_requested = track_count  # Track cumulative requests for intelligent retry

    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            playlist = await _call_ollama(
                system_prompt, current_message, current_count, attempt, on_event=on_event
            )
            last_playlist = playlist
        except json.JSONDecodeError as exc:
            logger.warning(
                "LLM_RETRY | attempt=%d/%d | reason=json_parse_failed | error=%s",
                attempt, MAX_ATTEMPTS, str(exc)[:100],
            )
            if attempt == MAX_ATTEMPTS:
                raise OllamaError(
                    f"Ollama returned invalid JSON after {MAX_ATTEMPTS} attempts."
                ) from exc
            continue
        except OllamaError:
            raise  # Propagate connection errors immediately

        all_tracks.extend(playlist.tracks)
        all_tracks = _deduplicate_tracks(all_tracks)
        got = len(all_tracks)
        logger.info(
            "DEDUPLICATION | attempt=%d | raw=%d | deduped=%d | total=%d / %d",
            attempt, len(playlist.tracks), got, got, track_count,
        )

        # Emit track_revealed events
        if on_event:
            for i, track in enumerate(playlist.tracks):
                try:
                    on_event({
                        "phase": "llm",
                        "step": f"track_{i+1}_revealed",
                        "message": f"Track {i+1}: {track.title}",
                        "detail": {
                            "track_number": i + 1,
                            "title": track.title,
                            "artist": track.artist,
                            "album": track.album or "",
                            "reasoning": track.reasoning,
                        },
                        "timing_ms": 0,
                        "progress": 0.3 + (0.2 * (i / max(len(playlist.tracks), 1))),
                    })
                except Exception as e:
                    logger.debug(f"Error emitting track_revealed event: {e}")

        if got >= track_count:
            final_tracks = all_tracks[:track_count]
            logger.info(
                "GENERATE_PLAYLIST | COMPLETE | final_count=%d | requested_count=%d",
                len(final_tracks),
                track_count,
            )
            return PlaylistResponse(
                name=playlist.name,
                description=playlist.description,
                tracks=final_tracks,
            )

        # Close enough — accept ≥90% to avoid expensive retry for 1-2 tracks
        shortfall = track_count - got
        if shortfall <= max(1, track_count // 10):
            logger.info(
                "[attempt %d/%d] Close enough (%d/%d) — returning partial result.",
                attempt, MAX_ATTEMPTS, got, track_count,
            )
            return PlaylistResponse(
                name=playlist.name,
                description=playlist.description,
                tracks=all_tracks[:track_count],
            )

        # Under-count: re-prompt for significantly more tracks
        attempts_remaining = MAX_ATTEMPTS - attempt
        
        # Request progressively more as attempts dwindle
        if attempts_remaining == 2:
            extra_needed = int(shortfall * 1.5)  # 150% of shortfall on 2nd attempt
        elif attempts_remaining == 1:
            extra_needed = int(shortfall * 2.0)  # 200% of shortfall on final attempt
        else:
            extra_needed = shortfall + (track_count // 2)  # shortfall + 50% buffer
        
        logger.warning(
            "[attempt %d/%d] Under-count (%d/%d) — requesting %d more (%.1f%% boost).",
            attempt, MAX_ATTEMPTS, got, track_count, extra_needed,
            (extra_needed / max(shortfall, 1)) * 100.0,
        )
        current_count = extra_needed
        total_requested += extra_needed
        current_message = (
            f"The previous response only had {got} tracks total. "
            f"Please provide {extra_needed} MORE completely different tracks "
            "for the same request. Do not repeat any previously suggested tracks. "
            "Provide a diverse set to maximize matching likelihood."
        )

    # Exhausted retries — return best effort
    name = last_playlist.name if last_playlist else "Generated Playlist"
    desc = last_playlist.description if last_playlist else "Partial results."
    logger.warning(
        "Returning %d tracks after %d attempts (requested %d).",
        len(all_tracks), MAX_ATTEMPTS, track_count,
    )
    return PlaylistResponse(name=name, description=desc, tracks=all_tracks[:track_count])

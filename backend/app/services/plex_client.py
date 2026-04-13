"""
Plex server connection utility.

Provides a lazily-initialised PlexServer connection and a helper to
retrieve the music library section. All connection errors are caught and
re-raised as descriptive PlexConnectionError exceptions so callers never
see raw PlexAPI internals.
"""

from __future__ import annotations

import logging

from plexapi.exceptions import BadRequest, NotFound, Unauthorized
from plexapi.library import MusicSection
from plexapi.server import PlexServer

from app.config import settings

logger = logging.getLogger(__name__)


class PlexConnectionError(RuntimeError):
    """Raised when connecting to or querying the Plex server fails."""


# ---------------------------------------------------------------------------
# Module-level singleton — created on first call to get_server()
# ---------------------------------------------------------------------------
_plex_server: PlexServer | None = None


def get_server() -> PlexServer:
    """Return the shared PlexServer instance, creating it if necessary.

    Raises:
        PlexConnectionError: If the server is unreachable or the token
            is invalid.
    """
    global _plex_server  # noqa: PLW0603

    if _plex_server is not None:
        return _plex_server

    url = settings.PLEX_URL
    token = settings.PLEX_TOKEN

    # Ensure the URL contains a scheme; PlexAPI expects a full URL.
    if "://" not in url:
        url = "http://" + url

    if not token:
        raise PlexConnectionError(
            "PLEX_TOKEN is not set. "
            "Please configure it in your .env file."
        )

    logger.info("Connecting to Plex server at %s …", url)
    try:
        _plex_server = PlexServer(url, token, timeout=30)
        logger.info(
            "Connected to Plex server '%s' (version %s).",
            _plex_server.friendlyName,
            _plex_server.version,
        )
        return _plex_server
    except Unauthorized as exc:
        raise PlexConnectionError(
            f"Plex authentication failed for URL '{url}'. "
            "Check that PLEX_TOKEN is correct."
        ) from exc
    except (BadRequest, NotFound) as exc:
        raise PlexConnectionError(
            f"Plex server at '{url}' returned an error: {exc}"
        ) from exc
    except Exception as exc:
        raise PlexConnectionError(
            f"Could not connect to Plex server at '{url}': {exc}"
        ) from exc


def reset_server() -> None:
    """Clear the cached server instance (useful for testing or re-auth)."""
    global _plex_server  # noqa: PLW0603
    _plex_server = None


def get_music_section() -> MusicSection:
    """Return the first Music library section from the connected Plex server.

    Raises:
        PlexConnectionError: If no Music library is found or the server
            cannot be reached.
    """
    server = get_server()
    try:
        sections = server.library.sections()
        music_sections = [s for s in sections if s.type == "artist"]
        if not music_sections:
            raise PlexConnectionError(
                "No Music library found on the Plex server. "
                "Ensure a Music library is configured in Plex."
            )
        section = music_sections[0]
        logger.debug("Using music section: '%s'", section.title)
        return section  # type: ignore[return-value]
    except PlexConnectionError:
        raise
    except Exception as exc:
        raise PlexConnectionError(
            f"Failed to retrieve Plex library sections: {exc}"
        ) from exc

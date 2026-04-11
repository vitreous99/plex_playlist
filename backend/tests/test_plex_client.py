"""
Tests for the Plex server connection utility (plex_client.py).

All tests mock the PlexServer to avoid requiring a live Plex instance.
"""

from unittest.mock import MagicMock, patch

import pytest

from app.services.plex_client import PlexConnectionError, get_music_section, get_server, reset_server


# ---------------------------------------------------------------------------
# get_server()
# ---------------------------------------------------------------------------


def test_get_server_raises_when_token_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    """get_server() raises PlexConnectionError when PLEX_TOKEN is empty."""
    monkeypatch.setattr("app.services.plex_client.settings.PLEX_TOKEN", "")
    reset_server()
    with pytest.raises(PlexConnectionError, match="PLEX_TOKEN is not set"):
        get_server()


def test_get_server_raises_on_unauthorized(monkeypatch: pytest.MonkeyPatch) -> None:
    """get_server() raises PlexConnectionError on Unauthorized error."""
    from plexapi.exceptions import Unauthorized

    monkeypatch.setattr("app.services.plex_client.settings.PLEX_TOKEN", "bad-token")
    reset_server()
    with patch("app.services.plex_client.PlexServer", side_effect=Unauthorized("bad")):
        with pytest.raises(PlexConnectionError, match="authentication failed"):
            get_server()


def test_get_server_raises_on_connection_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """get_server() raises PlexConnectionError on generic connection failure."""
    monkeypatch.setattr("app.services.plex_client.settings.PLEX_TOKEN", "some-token")
    reset_server()
    with patch("app.services.plex_client.PlexServer", side_effect=ConnectionError("refused")):
        with pytest.raises(PlexConnectionError, match="Could not connect"):
            get_server()


def test_get_server_returns_cached_instance(monkeypatch: pytest.MonkeyPatch) -> None:
    """get_server() returns the same instance on repeated calls (singleton)."""
    monkeypatch.setattr("app.services.plex_client.settings.PLEX_TOKEN", "valid-token")
    reset_server()
    mock_server = MagicMock()
    mock_server.friendlyName = "TestPlex"
    mock_server.version = "1.0"

    with patch("app.services.plex_client.PlexServer", return_value=mock_server) as mock_cls:
        s1 = get_server()
        s2 = get_server()
        assert s1 is s2
        assert mock_cls.call_count == 1  # Only constructed once


def test_reset_server_clears_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    """reset_server() clears the singleton so the next call reconnects."""
    monkeypatch.setattr("app.services.plex_client.settings.PLEX_TOKEN", "valid-token")
    reset_server()
    mock_server = MagicMock()
    mock_server.friendlyName = "TestPlex"
    mock_server.version = "1.0"

    with patch("app.services.plex_client.PlexServer", return_value=mock_server) as mock_cls:
        get_server()
        reset_server()
        get_server()
        assert mock_cls.call_count == 2  # Constructed twice after reset


# ---------------------------------------------------------------------------
# get_music_section()
# ---------------------------------------------------------------------------


def test_get_music_section_returns_first_artist_section(monkeypatch: pytest.MonkeyPatch) -> None:
    """get_music_section() returns the first Music (type=artist) section."""
    monkeypatch.setattr("app.services.plex_client.settings.PLEX_TOKEN", "valid-token")
    reset_server()

    music_section = MagicMock()
    music_section.type = "artist"
    music_section.title = "My Music"

    other_section = MagicMock()
    other_section.type = "movie"

    mock_server = MagicMock()
    mock_server.friendlyName = "TestPlex"
    mock_server.version = "1.0"
    mock_server.library.sections.return_value = [other_section, music_section]

    with patch("app.services.plex_client.PlexServer", return_value=mock_server):
        section = get_music_section()
        assert section is music_section


def test_get_music_section_raises_when_no_music_library(monkeypatch: pytest.MonkeyPatch) -> None:
    """get_music_section() raises PlexConnectionError when no Music section exists."""
    monkeypatch.setattr("app.services.plex_client.settings.PLEX_TOKEN", "valid-token")
    reset_server()

    movie_section = MagicMock()
    movie_section.type = "movie"

    mock_server = MagicMock()
    mock_server.friendlyName = "TestPlex"
    mock_server.version = "1.0"
    mock_server.library.sections.return_value = [movie_section]

    with patch("app.services.plex_client.PlexServer", return_value=mock_server):
        with pytest.raises(PlexConnectionError, match="No Music library"):
            get_music_section()

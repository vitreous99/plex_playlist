"""
Tests for application configuration.

Validates that the Settings model loads environment variables
correctly and provides sensible defaults.
"""

import os

import pytest


def test_settings_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    """Settings should provide sensible defaults for Ollama and model.

    We explicitly remove env vars that conftest sets so we can test
    the real defaults baked into the Settings class.
    """
    monkeypatch.delenv("OLLAMA_BASE_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)

    from app.config import Settings

    s = Settings(
        PLEX_URL="http://test:32400",
        PLEX_TOKEN="abc123",
    )
    assert s.OLLAMA_BASE_URL == "http://ollama:11434"
    assert s.DEFAULT_MODEL == "llama3.2:3b"
    assert s.CLIENT_NAME == "PlexPlaylist"


def test_settings_override_via_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Settings should pick up overridden environment variables."""
    monkeypatch.setenv("PLEX_URL", "http://custom:32400")
    monkeypatch.setenv("PLEX_TOKEN", "custom-token")
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://custom-ollama:11434")
    monkeypatch.setenv("DEFAULT_MODEL", "mistral:7b")
    monkeypatch.setenv("CLIENT_NAME", "CustomClient")

    from app.config import Settings

    s = Settings()
    assert s.PLEX_URL == "http://custom:32400"
    assert s.PLEX_TOKEN == "custom-token"
    assert s.OLLAMA_BASE_URL == "http://custom-ollama:11434"
    assert s.DEFAULT_MODEL == "mistral:7b"
    assert s.CLIENT_NAME == "CustomClient"


def test_settings_database_url_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """Settings should provide a default DATABASE_URL for SQLite."""
    monkeypatch.delenv("DATABASE_URL", raising=False)

    from app.config import Settings

    s = Settings(
        PLEX_URL="http://test:32400",
        PLEX_TOKEN="abc123",
    )
    assert "sqlite" in s.DATABASE_URL
    assert "library_cache" in s.DATABASE_URL

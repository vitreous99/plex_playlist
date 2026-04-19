"""
Application configuration via environment variables.

Uses pydantic-settings to load and validate environment variables
with sensible defaults for Docker Compose networking.
"""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Plex configuration
    PLEX_URL: str = "http://127.0.0.1:32400"
    # LAN URL used when dispatching playback to clients — must be the address
    # reachable by all LAN devices (not 127.0.0.1). Plex clients receive this
    # address so they can stream media locally without going via plex.tv relay.
    PLEX_LAN_URL: str = "http://127.0.0.1:32400"
    # Do not hard-code tokens in source; set `PLEX_TOKEN` in .env or environment.
    PLEX_TOKEN: str = ""
    CLIENT_NAME: str = "PlexPlaylist"

    # Ollama configuration
    # App runs network_mode:host so Docker service names don't resolve; use 127.0.0.1.
    OLLAMA_BASE_URL: str = "http://127.0.0.1:11434"
    DEFAULT_MODEL: str = "gemma:latest"

    # ADB Bridge configuration
    ADB_BRIDGE_URL: str = "http://127.0.0.1:9001"

    # Database configuration
    DATABASE_URL: str = "sqlite+aiosqlite:///db/library_cache.db"

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": True,
    }


# Singleton settings instance
settings = Settings()

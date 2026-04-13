"""
Application configuration via environment variables.

Uses pydantic-settings to load and validate environment variables
with sensible defaults for Docker Compose networking.
"""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Plex configuration
    PLEX_URL: str = "localhost:32400"
    # Do not hard-code tokens in source; set `PLEX_TOKEN` in .env or environment.
    PLEX_TOKEN: str = ""
    CLIENT_NAME: str = "PlexPlaylist"

    # Ollama configuration
    OLLAMA_BASE_URL: str = "http://ollama:11434"
    DEFAULT_MODEL: str = "gemma:latest"

    # ADB Bridge configuration
    ADB_BRIDGE_URL: str = "http://adb-bridge:9000"

    # Database configuration
    DATABASE_URL: str = "sqlite+aiosqlite:///db/library_cache.db"

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": True,
    }


# Singleton settings instance
settings = Settings()

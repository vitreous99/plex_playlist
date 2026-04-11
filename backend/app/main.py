"""
Plex Playlist — FastAPI Application Entry Point.

Bootstraps the application, initialises the database, and registers
routes and middleware.
"""

import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import suggest as suggest_router
from app.api import sync as sync_router
from app.config import settings
from app.models.database import init_db

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger("plex_playlist")


# ---------------------------------------------------------------------------
# Lifespan handler (startup / shutdown)
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan: runs once at startup and once at shutdown."""
    logger.info("Starting Plex Playlist application …")
    logger.info("Database URL: %s", settings.DATABASE_URL)
    logger.info("Ollama URL : %s", settings.OLLAMA_BASE_URL)
    logger.info("Plex URL   : %s", settings.PLEX_URL)

    # Initialise the database (create tables if they don't exist)
    await init_db()
    logger.info("Database initialised successfully.")

    yield  # Application is running

    logger.info("Shutting down Plex Playlist application.")


# ---------------------------------------------------------------------------
# Application factory
# ---------------------------------------------------------------------------
app = FastAPI(
    title="Plex Playlist",
    description="Intelligent Semantic Music Orchestrator — natural-language playlist generation for Plex.",
    version="0.1.0",
    lifespan=lifespan,
)

# ---------------------------------------------------------------------------
# CORS middleware (permissive for development)
# ---------------------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------
@app.get("/health", tags=["Infrastructure"])
async def health_check() -> dict:
    """Return a simple health-check response.

    Used by Docker HEALTHCHECK and monitoring tools to verify
    the application is running.
    """
    return {
        "status": "ok",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "version": app.version,
    }


# ---------------------------------------------------------------------------
# Register API routers
# ---------------------------------------------------------------------------
app.include_router(sync_router.router)
app.include_router(suggest_router.router)

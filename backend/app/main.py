"""
Plex Playlist — FastAPI Application Entry Point.

Bootstraps the application, initialises the database, and registers
routes and middleware.
"""

import logging
import secrets
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import AsyncGenerator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.api import suggest as suggest_router
from app.api import sync as sync_router
from app.api import playlist as playlist_router
from app.api import stream as stream_router
from app.api import clients as clients_router
from app.api import diagnostics as diagnostics_router
from app.api import wake as wake_router
from app.config import settings
from app.models.database import init_db
from app.trace import get_trace_id, set_trace_id, TraceIDFormatter


# Configure logging with trace ID support
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | [%(trace_id)s] | %(name)s | %(message)s",
)

# Apply custom formatter to all handlers
trace_formatter = TraceIDFormatter(
    "%(asctime)s | %(levelname)-8s | [%(trace_id)s] | %(name)s | %(message)s"
)
root_logger = logging.getLogger()
for handler in root_logger.handlers:
    handler.setFormatter(trace_formatter)

# Apply to uvicorn loggers specifically
for uvicorn_logger_name in ['uvicorn', 'uvicorn.access', 'uvicorn.error']:
    uvicorn_logger = logging.getLogger(uvicorn_logger_name)
    for handler in uvicorn_logger.handlers:
        handler.setFormatter(trace_formatter)

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
# Trace ID Middleware
# ---------------------------------------------------------------------------
async def trace_id_middleware(request: Request, call_next):
    """Generate trace ID and inject into context for all downstream operations."""
    # Check if client provided a trace ID header, otherwise generate one
    trace_id = request.headers.get('X-Trace-ID')
    if not trace_id:
        # Generate a short random ID (8 chars: XXXXXXXX)
        trace_id = secrets.token_hex(4)  # 8 hex chars
    
    # Set in context
    set_trace_id(trace_id)
    
    # Add to response headers so client can correlate
    response = await call_next(request)
    response.headers['X-Trace-ID'] = trace_id
    
    logger.info("Request: %s %s", request.method, request.url.path)
    
    return response


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

# Add trace ID middleware
app.middleware("http")(trace_id_middleware)


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
app.include_router(playlist_router.router)
app.include_router(stream_router.router)
app.include_router(clients_router.router)
app.include_router(wake_router.router)
app.include_router(diagnostics_router.router)

"""
Shared pytest fixtures for the Plex Playlist test suite.

Provides an in-memory async SQLite database and a configured
FastAPI test client.
"""

import os
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.database import Base, get_session

# ---------------------------------------------------------------------------
# Override settings BEFORE importing the app so that the config module
# picks up test values.
# ---------------------------------------------------------------------------
os.environ.setdefault("PLEX_URL", "http://localhost:32400")
os.environ.setdefault("PLEX_TOKEN", "test-token")
os.environ.setdefault("OLLAMA_BASE_URL", "http://localhost:11434")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")


# ---------------------------------------------------------------------------
# In-memory async engine for tests
# ---------------------------------------------------------------------------
_test_engine = create_async_engine(
    "sqlite+aiosqlite:///:memory:",
    echo=False,
    connect_args={"check_same_thread": False},
)

_test_session_factory = async_sessionmaker(
    bind=_test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


@pytest_asyncio.fixture(autouse=True)
async def setup_database():
    """Create all tables before each test and drop them after."""
    async with _test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with _test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


async def _override_get_session() -> AsyncGenerator[AsyncSession, None]:
    """Provide an in-memory session for dependency injection override."""
    async with _test_session_factory() as session:
        yield session


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Yield a fresh async session connected to the in-memory DB."""
    async with _test_session_factory() as session:
        yield session


@pytest_asyncio.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    """Yield an HTTPX AsyncClient wired to the FastAPI app.

    Overrides the database session dependency so tests hit the
    in-memory database instead of the on-disk SQLite file.
    """
    from app.main import app

    app.dependency_overrides[get_session] = _override_get_session

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()

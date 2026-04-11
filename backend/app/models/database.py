"""
Database engine, session factory, and base model.

Provides async SQLAlchemy infrastructure for the SQLite-backed
library cache.
"""

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

# Async engine — SQLite via aiosqlite
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    # SQLite-specific: enable WAL mode for better concurrent read performance
    connect_args={"check_same_thread": False},
)

# Session factory
async_session_factory = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""

    pass


async def init_db() -> None:
    """Create all tables if they don't already exist.

    Called during application startup via the FastAPI lifespan handler.
    """
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_session() -> AsyncSession:  # type: ignore[misc]
    """Dependency-injectable async session generator.

    Usage in FastAPI::

        @router.get("/example")
        async def example(session: AsyncSession = Depends(get_session)):
            ...
    """
    async with async_session_factory() as session:
        yield session  # type: ignore[misc]

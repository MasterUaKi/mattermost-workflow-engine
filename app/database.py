# Author: Oleh Riabtsev
# File: app/database.py
# Created: 2026-11-23
# Version: 1.1.0

"""
Asynchronous database connection and session factory module (SQLite / PostgreSQL)
built on SQLAlchemy 2.0.
"""

from collections.abc import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase
from app.config import get_settings

settings = get_settings()

# Create SQLAlchemy 2.0 async engine
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    future=True,
)

# Async session factory
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


class Base(DeclarativeBase):
    """Base class for all declarative SQLAlchemy 2.0 models."""
    pass


async def init_db() -> None:
    """Creates database tables on application startup for the MVP."""
    from app import models  # noqa: F401 — import to register ORM model metadata

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency providing a scoped async database session per request."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise

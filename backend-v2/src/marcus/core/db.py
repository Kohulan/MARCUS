"""Database foundation: lazy async (API) and sync (workers) engines plus the ORM base.

Engines are created on first use from get_settings(), never at import time, so tests can
change settings first. Call reset_engines() after changing the database URL.
"""

from collections.abc import AsyncIterator
from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.ext.asyncio import (
    AsyncAttrs,
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from marcus.core.settings import get_settings


def async_db_url(url: str) -> str:
    return url.replace("+psycopg", "+asyncpg") if "+asyncpg" not in url else url


def sync_db_url(url: str) -> str:
    """Map the async URL to the sync driver (workers have no event loop)."""
    return url.replace("+asyncpg", "+psycopg")


class Base(AsyncAttrs, DeclarativeBase):
    """Base class for all ORM models."""


@lru_cache
def get_async_engine() -> AsyncEngine:
    return create_async_engine(
        async_db_url(get_settings().database_url), echo=False, pool_pre_ping=True
    )


@lru_cache
def get_sync_engine() -> Engine:
    return create_engine(sync_db_url(get_settings().database_url), echo=False, pool_pre_ping=True)


@lru_cache
def get_async_sessionmaker() -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(get_async_engine(), expire_on_commit=False)


@lru_cache
def get_sync_sessionmaker() -> sessionmaker[Session]:
    return sessionmaker(get_sync_engine(), expire_on_commit=False)


def async_session() -> AsyncSession:
    """New async session (use as `async with async_session() as s`)."""
    return get_async_sessionmaker()()


def sync_session() -> Session:
    """New sync session (use as `with sync_session() as s`)."""
    return get_sync_sessionmaker()()


def reset_engines() -> None:
    """Forget cached engines/sessionmakers (after changing settings). Does not dispose pools."""
    for fn in (
        get_async_engine, get_sync_engine, get_async_sessionmaker, get_sync_sessionmaker,
    ):  # fmt: skip
        fn.cache_clear()


async def get_db() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency that yields an async database session."""
    async with async_session() as session:
        yield session

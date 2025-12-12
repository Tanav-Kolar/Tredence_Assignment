"""
Database connection and session management.

Provides async database engine and session factory using SQLModel with asyncpg.
"""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel

from app.db.config import settings


# Create async engine with asyncpg
engine = create_async_engine(
    settings.database_url,
    echo=settings.debug,
    future=True,
)

# Async session factory
async_session_factory = sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def init_db() -> None:
    """
    Initialize the database by creating all tables.
    
    This function should be called on application startup to ensure
    all SQLModel tables are created in the PostgreSQL database.
    """
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)


async def close_db() -> None:
    """
    Close the database engine connection pool.
    
    This function should be called on application shutdown to properly
    release all database connections.
    """
    await engine.dispose()


@asynccontextmanager
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Async context manager for database sessions.
    
    Provides a transactional scope around a series of operations.
    Automatically commits on success or rolls back on exception.
    
    Yields:
        AsyncSession: An async database session for executing queries.
    
    Example:
        async with get_session() as session:
            result = await session.execute(select(Workflow))
            workflows = result.scalars().all()
    """
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def get_session_dependency() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency for database sessions.
    
    Use with FastAPI's Depends() to inject database sessions into route handlers.
    
    Yields:
        AsyncSession: An async database session for executing queries.
    
    Example:
        @app.get("/items")
        async def get_items(session: AsyncSession = Depends(get_session_dependency)):
            ...
    """
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise

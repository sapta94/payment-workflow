from collections.abc import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.core.config import get_settings

settings = get_settings()

# The URL and driver are configured by DATABASE_URL in .env.  For example:
# mysql+asyncmy://user:password@localhost:3306/payment_workflow
engine: AsyncEngine = create_async_engine(
    settings.database_url,
    pool_pre_ping=True,
    pool_recycle=3_600,
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    autoflush=False,
    expire_on_commit=False,
)

vault_engine : AsyncEngine = create_async_engine(
    settings.vault_database_url,
    pool_pre_ping=True,
    pool_recycle=3_600,
)

AsyncVaultSessionLocal = async_sessionmaker(
    bind=vault_engine,
    autoflush=False,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy ORM models."""


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Provide one asynchronous database session per request."""
    async with AsyncSessionLocal() as session:
        yield session

async def get_vault_db() -> AsyncGenerator[AsyncSession, None]:
    """Provide one asynchronous database session per request."""
    async with AsyncVaultSessionLocal() as session:
        yield session

async def check_database_connection() -> str:
    """Raise an exception when MySQL cannot be reached."""
    async with engine.connect() as connection:
        result = await connection.execute(text("SELECT VERSION()"))
        result = str(result.scalar_one())
        print(f"✅ Connection successful! MySQL version: {result}")
        return result


async def close_database_connection() -> None:
    """Close all pooled database connections during application shutdown."""
    await engine.dispose()

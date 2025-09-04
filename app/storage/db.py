from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import declarative_base

from app.settings import Settings


Base = declarative_base()
_engine: AsyncEngine | None = None
SessionLocal: async_sessionmaker[AsyncSession] | None = None


async def init_db(settings: Settings) -> None:
    global _engine, SessionLocal
    if _engine is None:
        _engine = create_async_engine(settings.sqlalchemy_database_uri, future=True, echo=False)
        SessionLocal = async_sessionmaker(bind=_engine, expire_on_commit=False, class_=AsyncSession)
        # Import models to register them with SQLAlchemy metadata before optionally creating tables
        from app.domain import models  # noqa: F401
        # Create tables only if explicitly enabled (dev bootstrap). For production use Alembic migrations.
        if getattr(settings, "auto_create_tables", False):
            async with _engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)


async def dispose_db() -> None:
    global _engine
    if _engine is not None:
        await _engine.dispose()
        _engine = None


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    if SessionLocal is None:
        raise RuntimeError("Database is not initialized. Call init_db() first.")
    async with SessionLocal() as session:
        yield session
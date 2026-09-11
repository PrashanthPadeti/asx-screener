"""
ASX Screener — Database Session
Async SQLAlchemy session factory + asyncpg pool
"""
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from app.core.config import settings


# Async engine (FastAPI endpoints)
#
# pool_recycle is not a tuning knob here, it is a memory bound. A TimescaleDB
# backend accumulates relcache and catcache entries for every chunk it touches
# and never returns that memory to the OS, so a connection SQLAlchemy keeps
# forever (the pool_recycle=-1 default) only grows. Measured on the 4GB
# production box: 20 permanently pooled backends, all idle, ~370MB RSS each.
# Retiring a connection every 30 minutes caps how much any one can accrue.
#
# The pool is sized for 2 vCPU, where Postgres cannot usefully run more than a
# handful of queries at once. Brief queueing under a burst is the intended
# trade against exhausting the box.
engine = create_async_engine(
    settings.DATABASE_URL,
    pool_size=5,
    max_overflow=5,
    pool_recycle=1800,
    pool_pre_ping=True,
    echo=settings.DEBUG,
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncSession:
    """FastAPI dependency — yields a DB session per request."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

import logging
from contextlib import asynccontextmanager
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession

from .config import get_database_url, get_async_database_url

logger = logging.getLogger(__name__)

# SQLite database URLs from centralized configuration
DATABASE_URL = get_database_url()

# Create sync engine for migrations and basic operations
engine = create_engine(
    DATABASE_URL,
    poolclass=StaticPool,
    connect_args={"check_same_thread": False},
    echo=False,
)

# Create async engine for async operations
ASYNC_DATABASE_URL = get_async_database_url()
async_engine = create_async_engine(
    ASYNC_DATABASE_URL,
    poolclass=StaticPool,
    connect_args={"check_same_thread": False},
    echo=False,
)

logger.info(f"Using SQLite database: {DATABASE_URL}")
logger.info(f"Using async SQLite database: {ASYNC_DATABASE_URL}")

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
AsyncSessionLocal = sessionmaker(
    autocommit=False, autoflush=False, bind=async_engine, class_=AsyncSession
)

Base = declarative_base()


def get_db():
    """Database dependency for FastAPI (sync)"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@asynccontextmanager
async def get_async_session():
    """Async database session context manager"""
    async with AsyncSessionLocal() as session:
        yield session
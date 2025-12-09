import logging
from sqlalchemy import text
from .database import engine, Base
from .models import User, Conversation, Message, MediaAsset, Device, IngestRun

logger = logging.getLogger(__name__)


def create_tables():
    """Create all database tables"""
    Base.metadata.create_all(bind=engine)


def init_database():
    """Initialize database with tables and SQLite optimizations"""
    logger.info("Creating database tables...")
    create_tables()
    
    # Enable SQLite WAL mode for better concurrent access
    with engine.connect() as conn:
        try:
            # Apply SQLite optimizations
            conn.execute(text("PRAGMA journal_mode=WAL"))
            conn.execute(text("PRAGMA synchronous=NORMAL"))
            conn.execute(text("PRAGMA cache_size=1000"))
            conn.execute(text("PRAGMA temp_store=MEMORY"))
            conn.commit()
            logger.info("SQLite optimizations applied")
        except Exception as e:
            logger.error(f"SQLite optimization failed: {e}")
    
    logger.info("Database initialization complete")


if __name__ == "__main__":
    init_database()
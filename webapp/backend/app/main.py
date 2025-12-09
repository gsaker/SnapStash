import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings, get_ingest_config
from .init_db import init_database
from .services.ingest_loop import get_ingest_loop_service
from .api import health, ingest, messages, media, conversations, users, stats, scheduler, search
from .api import settings as settings_api

# Configure logging for Docker
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()  # This ensures logs go to stdout/stderr for Docker
    ]
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Get settings from centralized configuration
    settings = get_settings()
    
    # Startup
    logger.info("🚀 SnapStash Backend starting up...")
    if not settings.skip_db_init:
        logger.info("📊 Initializing database...")
        init_database()
        logger.info("✅ Database initialization complete")
    else:
        logger.info("⏭️ Skipping database initialization (SKIP_DB_INIT=true)")
    
    # Initialize and start ingestion loop if configured
    if not settings.disable_ingest_loop:
        logger.info("🔄 Starting ingestion loop...")
        ingest_service = await get_ingest_loop_service()
        
        # Use centralized configuration for ingestion
        ingest_config = get_ingest_config()
        await ingest_service.update_config(ingest_config)
            
        await ingest_service.start()
        logger.info("✅ Ingestion loop started")
    else:
        logger.info("⏭️ Ingestion loop disabled (DISABLE_INGEST_LOOP=true)")
        
    logger.info("✅ Backend startup complete")
    yield
    
    # Shutdown
    if not settings.disable_ingest_loop:
        logger.info("🛑 Stopping ingestion loop...")
        ingest_service = await get_ingest_loop_service()
        await ingest_service.stop()
        logger.info("✅ Ingestion loop stopped")
    logger.info("👋 Backend shutdown complete")


# Get settings for app configuration
settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    description="FastAPI backend for Snapchat data extraction and analysis",
    version=settings.app_version,
    lifespan=lifespan,
    redirect_slashes=False  # Prevent 307 redirects with internal Docker hostnames
)

# Configure CORS - allow all origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(health.router)
app.include_router(ingest.router)
app.include_router(messages.router)
app.include_router(media.router)
app.include_router(conversations.router)
app.include_router(users.router)
app.include_router(stats.router)
app.include_router(scheduler.router)
app.include_router(settings_api.router)
app.include_router(search.router)

@app.get("/")
async def root():
    return {"message": f"{settings.app_name} API", "version": settings.app_version}
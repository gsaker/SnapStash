"""
Continuous ingestion loop service for Snapchat data extraction.

This service runs continuous extraction cycles, starting a new run immediately
after the previous one completes. It includes configurable delays between runs
and proper error handling to ensure the loop continues even if individual runs fail.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from contextlib import asynccontextmanager

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_async_session
from ..config import get_settings, get_ingest_config
from ..services.storage import StorageService
from .ingestion_service import IngestionService

logger = logging.getLogger(__name__)


class IngestLoopService:
    """
    Manages continuous ingestion of Snapchat data with configurable scheduling.
    
    Supports two modes:
    1. Continuous mode: Starts new run immediately after previous completes
    2. Interval mode: Runs on fixed intervals (e.g., every N minutes)
    """
    
    def __init__(self):
        self.scheduler: Optional[AsyncIOScheduler] = None
        self.is_running = False
        self.current_run_id: Optional[int] = None
        self.last_run_time: Optional[datetime] = None
        self.consecutive_failures = 0
        self.max_consecutive_failures = 5
        
        # Load configuration from centralized settings
        self.config = get_ingest_config()
        
    async def initialize(self, config_overrides: Optional[Dict[str, Any]] = None):
        """Initialize the ingestion loop service."""
        if config_overrides:
            self.config.update(config_overrides)
            
        self.scheduler = AsyncIOScheduler()
        logger.info(f"Initialized ingestion loop in {self.config['mode']} mode")
        
    async def start(self):
        """Start the ingestion scheduler."""
        if not self.scheduler:
            raise RuntimeError("Service not initialized. Call initialize() first.")
            
        if self.is_running:
            logger.warning("Ingestion loop is already running")
            return
            
        self.scheduler.start()
        self.is_running = True
        
        if self.config["mode"] == "continuous":
            # Start continuous ingestion immediately
            self.scheduler.add_job(
                self._continuous_ingest_loop,
                trigger="date",  # Run once immediately
                run_date=datetime.now(),
                id="continuous_ingest",
                replace_existing=True
            )
            logger.info("Started continuous ingestion loop")
        else:
            # Schedule interval-based ingestion
            self.scheduler.add_job(
                self._run_single_ingest,
                trigger=IntervalTrigger(minutes=self.config["interval_minutes"]),
                id="interval_ingest",
                replace_existing=True
            )
            logger.info(f"Started interval ingestion (every {self.config['interval_minutes']} minutes)")
    
    async def stop(self):
        """Stop the ingestion scheduler."""
        if self.scheduler and self.scheduler.running:
            self.scheduler.shutdown(wait=True)
        self.is_running = False
        logger.info("Stopped ingestion loop")
        
    async def _continuous_ingest_loop(self):
        """
        Main continuous ingestion loop.
        Runs indefinitely, starting new ingestion immediately after previous completes.
        """
        logger.info("Starting continuous ingestion loop")
        
        while self.is_running:
            try:
                # Run a single ingestion cycle
                await self._run_single_ingest()
                
                # Reset failure counter on success
                self.consecutive_failures = 0
                
                # Brief delay before starting next run
                if self.config["delay_between_runs_seconds"] > 0:
                    logger.info(f"Waiting {self.config['delay_between_runs_seconds']} seconds before next run")
                    await asyncio.sleep(self.config["delay_between_runs_seconds"])
                    
            except Exception as e:
                self.consecutive_failures += 1
                logger.error(f"Ingestion run failed (attempt {self.consecutive_failures}): {e}")
                
                # If too many consecutive failures, increase delay exponentially
                if self.consecutive_failures >= self.max_consecutive_failures:
                    backoff_delay = min(300, 30 * (2 ** (self.consecutive_failures - self.max_consecutive_failures)))
                    logger.error(f"Too many consecutive failures. Backing off for {backoff_delay} seconds")
                    await asyncio.sleep(backoff_delay)
                else:
                    # Short delay before retrying
                    await asyncio.sleep(60)
                    
                # Continue the loop even after failures
                continue
    
    async def _run_single_ingest(self):
        """Run a single ingestion cycle using the centralized ingestion service."""
        if self.current_run_id is not None:
            logger.warning("Previous ingestion run still in progress, skipping")
            return

        from ..database import SessionLocal

        # Use synchronous session for storage service
        session = SessionLocal()
        try:
            # Reload configuration from database before each run
            logger.info("Reloading configuration from database...")
            self.config = get_ingest_config()
            logger.info(f"Loaded config: SSH={self.config['ssh_host']}:{self.config['ssh_port']}, "
                       f"Mode={self.config['mode']}, ExtractMedia={self.config['extract_media']}")

            storage = StorageService(session)

            # Create or get device record
            device_data = {
                "name": f"Loop Device ({self.config['ssh_host']})" if self.config['ssh_host'] else "Loop Device (No Host)",
                "ssh_host": self.config["ssh_host"] or "localhost",
                "ssh_port": self.config["ssh_port"],
                "ssh_user": self.config["ssh_user"],
                "is_active": True
            }
            device = storage.upsert_device(device_data)
            
            # Create new ingest run
            ingest_run = storage.create_ingest_run({
                "device_id": device.id,
                "extraction_type": "continuous_loop", 
                "status": "pending",
                "extraction_settings": self.config.copy()
            })
            self.current_run_id = ingest_run.id
            session.commit()  # Commit the run creation before starting
            
            try:
                logger.info(f"� Starting loop ingestion run {ingest_run.id}")
                
                # Create the centralized ingestion service
                ingestion_service = IngestionService(session)
                
                # Convert internal config to the format expected by the service
                service_config = {
                    'ssh_host': self.config["ssh_host"],
                    'ssh_port': self.config["ssh_port"],
                    'ssh_user': self.config["ssh_user"],
                    'ssh_key_path': self.config.get("ssh_key_path"),
                    'extract_media': self.config["extract_media"],
                    'timeout': self.config["timeout_seconds"]
                }
                
                # Execute the ingestion using the centralized service
                result = await ingestion_service.run_ingestion(ingest_run.id, service_config)
                
                self.last_run_time = datetime.now()
                logger.info(f"✅ Loop ingestion run {ingest_run.id} completed successfully: {result}")
                
            except Exception as e:
                logger.error(f"❌ Loop ingestion run {ingest_run.id} failed: {e}")
                raise
                
            finally:
                self.current_run_id = None
                
        finally:
            session.close()
    
    async def get_status(self) -> Dict[str, Any]:
        """Get current status of the ingestion loop."""
        return {
            "is_running": self.is_running,
            "mode": self.config["mode"],
            "current_run_id": self.current_run_id,
            "last_run_time": self.last_run_time.isoformat() if self.last_run_time else None,
            "consecutive_failures": self.consecutive_failures,
            "config": {
                "interval_minutes": self.config["interval_minutes"],
                "delay_between_runs_seconds": self.config["delay_between_runs_seconds"],
                "extract_media": self.config["extract_media"],
                "timeout_seconds": self.config["timeout_seconds"],
            },
            "scheduler_running": self.scheduler.running if self.scheduler else False,
        }
    
    async def update_config(self, new_config: Dict[str, Any]) -> bool:
        """Update configuration. Returns True if restart is needed."""
        restart_required_keys = {"mode", "interval_minutes"}
        needs_restart = any(key in new_config for key in restart_required_keys)
        
        self.config.update(new_config)
        logger.info(f"Updated configuration: {new_config}")
        
        return needs_restart
    
    async def force_run(self) -> int:
        """Force an immediate ingestion run. Returns the run ID."""
        if self.current_run_id is not None:
            raise RuntimeError("An ingestion run is already in progress")
            
        # Schedule immediate run
        job = self.scheduler.add_job(
            self._run_single_ingest,
            trigger="date",
            run_date=datetime.now(),
            id=f"forced_run_{datetime.now().timestamp()}",
        )
        
        # Wait a moment for the run to start and get an ID
        await asyncio.sleep(0.1)
        return self.current_run_id


# Global service instance
_ingest_loop_service: Optional[IngestLoopService] = None


async def get_ingest_loop_service() -> IngestLoopService:
    """Get the global ingestion loop service instance."""
    global _ingest_loop_service
    if _ingest_loop_service is None:
        _ingest_loop_service = IngestLoopService()
        # Initialize with default config, can be overridden via API
        await _ingest_loop_service.initialize()
    return _ingest_loop_service


@asynccontextmanager
async def ingest_loop_lifespan():
    """Context manager for managing ingestion loop lifecycle."""
    service = await get_ingest_loop_service()
    try:
        await service.start()
        yield service
    finally:
        await service.stop()
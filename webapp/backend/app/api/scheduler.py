"""
API endpoints for controlling the ingestion scheduler.
"""

import logging
from typing import Dict, Any, Optional
from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel

from ..services.ingest_loop import get_ingest_loop_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/scheduler", tags=["scheduler"])


class SchedulerConfigUpdate(BaseModel):
    """Request model for updating scheduler configuration."""
    mode: str = None  # "continuous" or "interval" 
    interval_minutes: int = None
    delay_between_runs_seconds: int = None
    extract_media: bool = None
    timeout_seconds: int = None
    ssh_host: str = None
    ssh_user: str = None
    ssh_port: int = None


class SchedulerStatusResponse(BaseModel):
    """Response model for scheduler status."""
    is_running: bool
    mode: str
    current_run_id: Optional[int] = None
    last_run_time: Optional[str] = None
    consecutive_failures: int
    config: Dict[str, Any]
    scheduler_running: bool


class SchedulerResponse(BaseModel):
    """Generic scheduler response."""
    success: bool
    message: str
    data: Dict[str, Any] = None


@router.get("/status", response_model=SchedulerStatusResponse)
async def get_scheduler_status():
    """Get current status of the ingestion scheduler."""
    try:
        service = await get_ingest_loop_service()
        status = await service.get_status()
        return SchedulerStatusResponse(**status)
    except Exception as e:
        logger.error(f"Failed to get scheduler status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/start", response_model=SchedulerResponse)
async def start_scheduler():
    """Start the ingestion scheduler."""
    try:
        service = await get_ingest_loop_service()
        if service.is_running:
            return SchedulerResponse(
                success=False,
                message="Scheduler is already running"
            )
        
        await service.start()
        return SchedulerResponse(
            success=True,
            message="Scheduler started successfully"
        )
    except Exception as e:
        logger.error(f"Failed to start scheduler: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/stop", response_model=SchedulerResponse) 
async def stop_scheduler():
    """Stop the ingestion scheduler."""
    try:
        service = await get_ingest_loop_service()
        if not service.is_running:
            return SchedulerResponse(
                success=False,
                message="Scheduler is not running"
            )
        
        await service.stop()
        return SchedulerResponse(
            success=True,
            message="Scheduler stopped successfully"
        )
    except Exception as e:
        logger.error(f"Failed to stop scheduler: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/restart", response_model=SchedulerResponse)
async def restart_scheduler():
    """Restart the ingestion scheduler."""
    try:
        service = await get_ingest_loop_service()
        
        # Stop if running
        if service.is_running:
            await service.stop()
        
        # Start again
        await service.start()
        
        return SchedulerResponse(
            success=True,
            message="Scheduler restarted successfully"
        )
    except Exception as e:
        logger.error(f"Failed to restart scheduler: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/force-run", response_model=SchedulerResponse)
async def force_ingestion_run():
    """Force an immediate ingestion run."""
    try:
        service = await get_ingest_loop_service()
        
        if not service.is_running:
            return SchedulerResponse(
                success=False,
                message="Scheduler is not running. Start the scheduler first."
            )
        
        run_id = await service.force_run()
        return SchedulerResponse(
            success=True,
            message=f"Forced ingestion run started",
            data={"run_id": run_id}
        )
    except RuntimeError as e:
        return SchedulerResponse(
            success=False,
            message=str(e)
        )
    except Exception as e:
        logger.error(f"Failed to force ingestion run: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/config", response_model=SchedulerResponse)
async def update_scheduler_config(config_update: SchedulerConfigUpdate):
    """Update scheduler configuration."""
    try:
        service = await get_ingest_loop_service()
        
        # Filter out None values
        new_config = {k: v for k, v in config_update.model_dump().items() if v is not None}
        
        if not new_config:
            return SchedulerResponse(
                success=False,
                message="No configuration updates provided"
            )
        
        # Validate mode if provided
        if "mode" in new_config and new_config["mode"] not in ["continuous", "interval"]:
            return SchedulerResponse(
                success=False,
                message="Invalid mode. Must be 'continuous' or 'interval'"
            )
        
        # Update configuration
        needs_restart = await service.update_config(new_config)
        
        message = "Configuration updated successfully"
        if needs_restart and service.is_running:
            # Restart scheduler to apply critical changes
            await service.stop()
            await service.start()
            message += " (scheduler restarted to apply changes)"
        
        return SchedulerResponse(
            success=True,
            message=message,
            data={"needs_restart": needs_restart, "updated_config": new_config}
        )
        
    except Exception as e:
        logger.error(f"Failed to update scheduler config: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/config", response_model=Dict[str, Any])
async def get_scheduler_config():
    """Get current scheduler configuration."""
    try:
        service = await get_ingest_loop_service()
        return service.config
    except Exception as e:
        logger.error(f"Failed to get scheduler config: {e}")
        raise HTTPException(status_code=500, detail=str(e))
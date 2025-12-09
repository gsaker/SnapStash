import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import get_db, SessionLocal
from ..services.ingestion_service import IngestionService
from ..services.storage import StorageService
from ..models import IngestRun

router = APIRouter(prefix="/api/ingest", tags=["ingest"])

# Configure logging
logger = logging.getLogger(__name__)


class IngestRequest(BaseModel):
    ssh_host: str
    ssh_user: str = "root"
    ssh_port: int = 22
    ssh_key_path: Optional[str] = None
    extract_media: bool = True
    timeout: int = 300


class IngestResponse(BaseModel):
    run_id: int
    status: str
    message: str
    started_at: datetime


async def run_ingest_process(
    request: IngestRequest,
    run_id: int
):
    """Background task to run the complete ingest process using the centralized service."""
    logger.info(f"🚀 Starting API ingest process for run_id {run_id}")
    
    # Create a new database session for the background task
    db_session = SessionLocal()
    
    try:
        # Create the centralized ingestion service
        ingestion_service = IngestionService(db_session)
        
        # Convert request to config format expected by the service
        config = {
            'ssh_host': request.ssh_host,
            'ssh_port': request.ssh_port,
            'ssh_user': request.ssh_user,
            'ssh_key_path': request.ssh_key_path,
            'extract_media': request.extract_media,
            'timeout': request.timeout
        }
        
        # Execute the ingestion using the centralized service
        result = await ingestion_service.run_ingestion(run_id, config)
        logger.info(f"✅ API ingestion completed: {result}")
        
    except Exception as e:
        logger.error(f"❌ API ingestion failed for run {run_id}: {e}")
        raise
    finally:
        db_session.close()


@router.post("/run", response_model=IngestResponse)
async def trigger_ingest(
    request: IngestRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """Trigger a complete SSH extraction and parsing run."""
    storage_service = StorageService(db)
    
    # Check if another run is in progress
    latest_runs = storage_service.get_latest_ingest_runs(limit=1)
    if latest_runs and latest_runs[0].status in ["pending", "in_progress", "running"]:
        raise HTTPException(
            status_code=409,
            detail="Another ingest run is already in progress"
        )
    
    # Get or create device for this SSH host
    device = storage_service.upsert_device({
        "name": f"SSH Device ({request.ssh_host})",
        "ssh_host": request.ssh_host,
        "ssh_user": request.ssh_user,
        "ssh_port": request.ssh_port,
        "is_active": True
    })
    db.commit()  # Commit device first to get its ID
    
    # Create new ingest run
    ingest_run = storage_service.create_ingest_run({
        "device_id": device.id,
        "extraction_type": "full",
        "status": "pending",
        "extraction_settings": {
            "ssh_host": request.ssh_host,
            "ssh_user": request.ssh_user,
            "ssh_port": request.ssh_port,
            "extract_media": request.extract_media,
            "timeout": request.timeout
        }
    })
    db.commit()
    
    # Add background task
    background_tasks.add_task(run_ingest_process, request, ingest_run.id)
    
    return IngestResponse(
        run_id=ingest_run.id,
        status="pending",
        message="Ingest run started successfully",
        started_at=ingest_run.started_at
    )


@router.get("/runs")
async def get_ingest_runs(
    limit: int = 10,
    db: Session = Depends(get_db)
):
    """Get latest ingest runs with their status."""
    storage_service = StorageService(db)
    runs = storage_service.get_latest_ingest_runs(limit=limit)
    
    return {
        "runs": [
            {
                "id": run.id,
                "status": run.status,
                "extraction_type": run.extraction_type,
                "started_at": run.started_at,
                "completed_at": run.completed_at,
                "messages_extracted": run.messages_extracted,
                "media_files_extracted": run.media_files_extracted,
                "parsing_errors": run.parsing_errors,
                "error_message": run.error_message
            }
            for run in runs
        ]
    }


@router.get("/runs/{run_id}")
async def get_ingest_run(
    run_id: int,
    db: Session = Depends(get_db)
):
    """Get detailed information about a specific ingest run."""
    storage_service = StorageService(db)
    
    # Get run by ID
    run = db.query(IngestRun).filter(IngestRun.id == run_id).first()
    
    if not run:
        raise HTTPException(status_code=404, detail="Ingest run not found")
    
    return {
        "id": run.id,
        "status": run.status,
        "extraction_type": run.extraction_type,
        "started_at": run.started_at,
        "completed_at": run.completed_at,
        "messages_extracted": run.messages_extracted,
        "media_files_extracted": run.media_files_extracted,
        "parsing_errors": run.parsing_errors,
        "error_message": run.error_message,
        "error_details": run.error_details,
        "extraction_settings": run.extraction_settings
    }
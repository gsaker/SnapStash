from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..database import get_db
from ..services.storage import StorageService

router = APIRouter(prefix="/api/stats", tags=["statistics"])


@router.get("")
async def get_overall_stats(
    db: Session = Depends(get_db)
):
    """Get overall system statistics."""
    storage_service = StorageService(db)
    
    # Get database info
    db_info = StorageService.get_database_info()
    
    # Get message statistics
    message_stats = storage_service.get_message_stats()
    
    # Get media statistics
    media_stats = storage_service.get_media_stats()
    
    # Get latest ingest runs
    latest_runs = storage_service.get_latest_ingest_runs(limit=5)
    
    return {
        "timestamp": datetime.utcnow().isoformat(),
        "database": db_info,
        "messages": message_stats,
        "media": media_stats,
        "latest_runs": [
            {
                "id": run.id,
                "status": run.status,
                "extraction_type": run.extraction_type,
                "started_at": run.started_at,
                "completed_at": run.completed_at,
                "messages_extracted": run.messages_extracted,
                "media_files_extracted": run.media_files_extracted,
                "parsing_errors": run.parsing_errors
            }
            for run in latest_runs
        ]
    }


@router.get("/activity")
async def get_activity_stats(
    days: int = Query(7, ge=1, le=365, description="Number of days to analyze"),
    db: Session = Depends(get_db)
):
    """Get activity statistics over time."""
    storage_service = StorageService(db)
    return storage_service.get_activity_stats(days)


@router.get("/parsing")
async def get_parsing_stats(
    db: Session = Depends(get_db)
):
    """Get statistics about parsing success rates."""
    storage_service = StorageService(db)
    return storage_service.get_parsing_stats()


@router.get("/storage")
async def get_storage_stats(
    db: Session = Depends(get_db)
):
    """Get storage and file system statistics."""
    storage_service = StorageService(db)
    return storage_service.get_storage_stats()


@router.post("/populate-dm-names")
async def populate_dm_names(
    db: Session = Depends(get_db)
):
    """Populate names for individual DM conversations based on participants."""
    storage_service = StorageService(db)
    return storage_service.populate_individual_dm_names()

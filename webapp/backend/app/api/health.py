from datetime import datetime
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..database import get_db
from ..services.storage import StorageService

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health")
async def health_check():
    """Basic health check endpoint."""
    return {
        "status": "healthy",
        "service": "gz-snapchat-backend",
        "timestamp": datetime.utcnow().isoformat()
    }


@router.get("/info")
async def system_info():
    """Get system information and database statistics."""
    db_info = StorageService.get_database_info()
    
    return {
        "service": "gz-snapchat-backend",
        "version": "0.1.0",
        "timestamp": datetime.utcnow().isoformat(),
        "database": db_info
    }
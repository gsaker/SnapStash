"""
Devices API Endpoints
Provides REST API for managing push notification device tokens
"""

import logging
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime

from ..database import get_db
from ..models import PushDeviceToken
from ..schemas import (
    PushDeviceTokenCreate,
    PushDeviceTokenResponse,
    ApiResponse
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/devices", tags=["devices"])


@router.post("/register", response_model=ApiResponse)
async def register_device(
    request: PushDeviceTokenCreate,
    db: Session = Depends(get_db)
):
    """
    Register a device for push notifications.
    
    If the device token already exists, updates the last_seen timestamp
    and reactivates it if it was deactivated.
    """
    try:
        # Check if token already exists
        existing = db.query(PushDeviceToken).filter(
            PushDeviceToken.token == request.device_token
        ).first()
        
        if existing:
            # Update existing token
            existing.is_active = True
            existing.last_seen = datetime.utcnow()
            existing.app_version = request.app_version
            db.commit()
            
            logger.info(f"Updated existing device token: {request.device_token[:20]}...")
            return ApiResponse(
                success=True,
                message="Device token updated",
                data={"status": "updated", "device_id": existing.id}
            )
        
        # Create new token entry
        new_device = PushDeviceToken(
            token=request.device_token,
            platform=request.platform,
            app_version=request.app_version,
            is_active=True
        )
        db.add(new_device)
        db.commit()
        db.refresh(new_device)
        
        logger.info(f"Registered new device token: {request.device_token[:20]}...")
        return ApiResponse(
            success=True,
            message="Device token registered",
            data={"status": "registered", "device_id": new_device.id}
        )
        
    except Exception as e:
        logger.error(f"Error registering device token: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/unregister/{token}", response_model=ApiResponse)
async def unregister_device(
    token: str,
    db: Session = Depends(get_db)
):
    """
    Unregister a device from push notifications.
    
    This deactivates the token rather than deleting it,
    allowing for easy re-registration.
    """
    try:
        device = db.query(PushDeviceToken).filter(
            PushDeviceToken.token == token
        ).first()
        
        if not device:
            raise HTTPException(status_code=404, detail="Device token not found")
        
        device.is_active = False
        db.commit()
        
        logger.info(f"Deactivated device token: {token[:20]}...")
        return ApiResponse(
            success=True,
            message="Device token deactivated"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error unregistering device token: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("", response_model=List[PushDeviceTokenResponse])
async def list_devices(
    active_only: bool = True,
    platform: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """
    List all registered device tokens.
    
    Query parameters:
    - active_only: Only return active tokens (default: true)
    - platform: Filter by platform (ios, android)
    """
    try:
        query = db.query(PushDeviceToken)
        
        if active_only:
            query = query.filter(PushDeviceToken.is_active == True)
        
        if platform:
            query = query.filter(PushDeviceToken.platform == platform)
        
        devices = query.order_by(PushDeviceToken.last_seen.desc()).all()
        return devices
        
    except Exception as e:
        logger.error(f"Error listing devices: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/count")
async def count_devices(
    active_only: bool = True,
    db: Session = Depends(get_db)
):
    """
    Get count of registered devices by platform.
    """
    try:
        query = db.query(PushDeviceToken)
        
        if active_only:
            query = query.filter(PushDeviceToken.is_active == True)
        
        ios_count = query.filter(PushDeviceToken.platform == "ios").count()
        android_count = query.filter(PushDeviceToken.platform == "android").count()
        total = ios_count + android_count
        
        return {
            "total": total,
            "ios": ios_count,
            "android": android_count
        }
        
    except Exception as e:
        logger.error(f"Error counting devices: {e}")
        raise HTTPException(status_code=500, detail=str(e))

"""
Test API Endpoints
Provides endpoints for testing push notifications and other features
"""

import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import get_db
from ..services.apns_service import get_apns_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/test", tags=["test"])


class TestNotificationRequest(BaseModel):
    """Request model for test notification"""
    title: str
    body: str
    conversation_id: Optional[str] = None
    image_url: Optional[str] = None
    sender_avatar_url: Optional[str] = None
    sender_id: Optional[str] = None


@router.post("/notification")
async def send_test_notification(
    request: TestNotificationRequest,
    db: Session = Depends(get_db)
):
    """
    Send a test push notification to all registered iOS devices.

    This is useful for testing the APNs configuration and verifying
    that push notifications are working correctly.
    """
    try:
        apns_service = get_apns_service(db)

        # Send notification to all active iOS devices
        result = await apns_service.send_notification(
            title=request.title,
            body=request.body,
            conversation_id=request.conversation_id,
            image_url=request.image_url,
            sender_avatar_url=request.sender_avatar_url,
            sender_id=request.sender_id,
        )

        logger.info(f"Test notification sent: {result}")

        return {
            "success": True,
            "message": "Test notification sent",
            "result": result
        }

    except Exception as e:
        logger.error(f"Error sending test notification: {e}")
        raise HTTPException(status_code=500, detail=str(e))

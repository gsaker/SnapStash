"""
Apple Push Notification Service (APNs) Integration
Sends native iOS push notifications using the APNs HTTP/2 API
"""

import logging
import os
from typing import Optional, List, Dict, Any
from datetime import datetime
from sqlalchemy.orm import Session

from .settings_service import get_settings_service

logger = logging.getLogger(__name__)

# Path to APNs credentials
APNS_KEY_PATH = "/app/data/apns_keys"


class APNsService:
    """Service for sending iOS push notifications via APNs"""

    def __init__(self, db: Optional[Session] = None):
        """Initialize APNs service with optional database session"""
        self.db = db
        self.settings_service = get_settings_service(db)
        self._client = None
        self._key_path = None
        self._key_id = None
        self._team_id = None
        self._bundle_id = None
        self._use_sandbox = True

    def _is_enabled(self) -> bool:
        """Check if APNs notifications are enabled"""
        return self.settings_service.get_setting("apns_enabled", False)

    def _get_credentials(self) -> bool:
        """Load APNs credentials from settings"""
        self._key_id = self.settings_service.get_setting("apns_key_id")
        self._team_id = self.settings_service.get_setting("apns_team_id")
        self._bundle_id = self.settings_service.get_setting("apns_bundle_id", "com.george.SnapStash")
        self._use_sandbox = self.settings_service.get_setting("apns_use_sandbox", True)
        
        # Check for key file
        key_filename = self.settings_service.get_setting("apns_key_filename", "AuthKey.p8")
        self._key_path = os.path.join(APNS_KEY_PATH, key_filename)
        
        if not os.path.exists(self._key_path):
            logger.warning(f"APNs key file not found: {self._key_path}")
            return False
        
        if not self._key_id or not self._team_id:
            logger.warning("APNs key_id or team_id not configured")
            return False
        
        return True

    def _get_client(self):
        """Get or create the APNs client"""
        if self._client is not None:
            return self._client

        if not self._get_credentials():
            return None

        try:
            from aioapns import APNs, NotificationRequest

            # Read the key file content
            with open(self._key_path, 'r') as f:
                key_content = f.read()

            # Create APNs client with token-based authentication
            self._client = APNs(
                key=key_content,
                key_id=self._key_id,
                team_id=self._team_id,
                topic=self._bundle_id,
                use_sandbox=self._use_sandbox
            )

            logger.info(f"APNs client initialized (sandbox={self._use_sandbox}, bundle={self._bundle_id})")
            return self._client

        except ImportError:
            logger.error("aioapns library not installed. Run: pip install aioapns")
            return None
        except Exception as e:
            logger.error(f"Failed to initialize APNs client: {e}")
            return None

    def _get_active_tokens(self) -> List[str]:
        """Get all active iOS device tokens from database"""
        if not self.db:
            logger.warning("No database session provided to APNs service")
            return []
        
        try:
            from ..models import PushDeviceToken
            
            devices = self.db.query(PushDeviceToken).filter(
                PushDeviceToken.platform == "ios",
                PushDeviceToken.is_active == True
            ).all()
            
            return [device.token for device in devices]
            
        except Exception as e:
            logger.error(f"Failed to fetch device tokens: {e}")
            return []

    async def send_notification(
        self,
        title: str,
        body: str,
        conversation_id: Optional[str] = None,
        badge: Optional[int] = None,
        sound: str = "default",
        tokens: Optional[List[str]] = None,
        image_url: Optional[str] = None,
        sender_avatar_url: Optional[str] = None,
        sender_id: Optional[str] = None,
        category: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Send a push notification to iOS devices.

        Args:
            title: Notification title
            body: Notification body text
            conversation_id: Optional conversation ID for deep linking
            badge: Optional badge count to display
            sound: Sound to play (default: "default")
            tokens: Optional list of specific tokens to send to.
                   If not provided, sends to all active iOS devices.
            image_url: Optional URL to an image to attach to the notification

        Returns:
            Dict with success count and failed tokens
        """
        if not self._is_enabled():
            logger.debug("APNs notifications are disabled")
            return {"success_count": 0, "failed_tokens": [], "skipped": True}

        client = self._get_client()
        if not client:
            logger.error("APNs client not available")
            return {"success_count": 0, "failed_tokens": [], "error": "Client not initialized"}

        # Get tokens to send to
        if tokens is None:
            tokens = self._get_active_tokens()
        
        if not tokens:
            logger.debug("No active iOS device tokens found")
            return {"success_count": 0, "failed_tokens": [], "skipped": True}

        try:
            from aioapns import NotificationRequest

            # Build custom data payload
            custom_data = {}
            if conversation_id:
                custom_data["conversation_id"] = conversation_id
            if image_url:
                custom_data["image_url"] = image_url
            if sender_avatar_url:
                custom_data["sender_avatar_url"] = sender_avatar_url
            if sender_id:
                custom_data["sender_id"] = sender_id

            success_count = 0
            failed_tokens = []

            # Send to each device
            for token in tokens:
                try:
                    # Build alert payload
                    alert_payload = {
                        "title": title,
                        "body": body
                    }

                    # Build aps payload
                    aps_payload = {
                        "alert": alert_payload,
                        "sound": sound
                    }

                    # Add badge if provided
                    if badge is not None:
                        aps_payload["badge"] = badge

                    if conversation_id:
                        aps_payload["thread-id"] = conversation_id

                    if category:
                        aps_payload["category"] = category

                    # Enable mutable-content so the Notification Service Extension can attach images
                    if image_url or sender_avatar_url:
                        aps_payload["mutable-content"] = 1
                        logger.info(
                            "APNs rich payload enabled: image_url=%s sender_avatar_url=%s conversation_id=%s",
                            image_url,
                            sender_avatar_url,
                            conversation_id,
                        )

                    # Create notification request
                    request = NotificationRequest(
                        device_token=token,
                        message={
                            "aps": aps_payload,
                            **custom_data
                        }
                    )

                    # Send notification (aioapns is async)
                    response = await client.send_notification(request)

                    # Check if successful
                    if response.is_successful:
                        success_count += 1
                        logger.debug(f"Push sent to {token[:20]}...")
                    else:
                        error_str = f"Status: {response.status}, Description: {response.description}"
                        logger.warning(f"Failed to send push to {token[:20]}...: {error_str}")
                        failed_tokens.append({"token": token, "error": error_str})

                        # Mark token as inactive if it's invalid
                        if response.status in [400, 410]:  # BadDeviceToken or Unregistered
                            self._deactivate_token(token)

                except Exception as send_error:
                    error_str = str(send_error)
                    logger.warning(f"Failed to send push to {token[:20]}...: {error_str}")
                    failed_tokens.append({"token": token, "error": error_str})

            logger.info(f"APNs: Sent {success_count}/{len(tokens)} notifications")

            return {
                "success_count": success_count,
                "failed_tokens": failed_tokens,
                "total_tokens": len(tokens)
            }

        except Exception as e:
            logger.error(f"Error sending APNs notifications: {e}")
            return {"success_count": 0, "failed_tokens": [], "error": str(e)}

    def _deactivate_token(self, token: str):
        """Mark a device token as inactive"""
        if not self.db:
            return
        
        try:
            from ..models import PushDeviceToken
            
            device = self.db.query(PushDeviceToken).filter(
                PushDeviceToken.token == token
            ).first()
            
            if device:
                device.is_active = False
                self.db.commit()
                logger.info(f"Deactivated invalid token: {token[:20]}...")
                
        except Exception as e:
            logger.error(f"Failed to deactivate token: {e}")

    async def send_text_message_notification(
        self,
        sender_username: str,
        text: str,
        conversation_id: Optional[str] = None,
        sender_avatar_url: Optional[str] = None,
        sender_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Send notification for a new text message.

        Args:
            sender_username: Username of the message sender
            text: Message text content
            conversation_id: ID of the conversation for deep linking

        Returns:
            Result dict from send_notification
        """
        # Check if sender should be excluded
        exclude_name = self.settings_service.get_setting("dm_exclude_name")
        if exclude_name and sender_username == exclude_name:
            logger.debug(f"Skipping APNs notification for excluded sender: {sender_username}")
            return {"success_count": 0, "skipped": True}

        # Truncate body for notification
        body = text[:200] + "..." if len(text) > 200 else text

        return await self.send_notification(
            title=sender_username,
            body=body,
            conversation_id=conversation_id,
            sender_avatar_url=sender_avatar_url,
            sender_id=sender_id,
            category="message" if sender_avatar_url else None,
        )

    async def send_media_message_notification(
        self,
        sender_username: str,
        media_type: str,
        conversation_id: Optional[str] = None,
        text: Optional[str] = None,
        media_url: Optional[str] = None,
        sender_avatar_url: Optional[str] = None,
        sender_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Send notification for a new media message.

        Args:
            sender_username: Username of the message sender
            media_type: Type of media (image, video, etc.)
            conversation_id: ID of the conversation for deep linking
            text: Optional text accompanying the media
            media_url: Optional URL to the media file for rich notifications

        Returns:
            Result dict from send_notification
        """
        # Check if sender should be excluded
        exclude_name = self.settings_service.get_setting("dm_exclude_name")
        if exclude_name and sender_username == exclude_name:
            logger.debug(f"Skipping APNs notification for excluded sender: {sender_username}")
            return {"success_count": 0, "skipped": True}

        # Build body
        if text:
            body = text[:200] + "..." if len(text) > 200 else text
        else:
            body = f"Sent a {media_type}"

        # Only attach images to notifications (notification_service determines if media_url is image-capable)
        image_url = media_url
        logger.info(
            "APNs media notification: media_type=%s conversation_id=%s image_url=%s",
            media_type,
            conversation_id,
            image_url,
        )

        return await self.send_notification(
            title=sender_username,
            body=body,
            conversation_id=conversation_id,
            image_url=image_url,
            sender_avatar_url=sender_avatar_url,
            sender_id=sender_id,
            category="message" if sender_avatar_url else None,
        )


# Global APNs service instance
_apns_service: Optional[APNsService] = None


def get_apns_service(db: Optional[Session] = None) -> APNsService:
    """Get the global APNs service instance"""
    global _apns_service
    if _apns_service is None or db is not None:
        _apns_service = APNsService(db)
    return _apns_service

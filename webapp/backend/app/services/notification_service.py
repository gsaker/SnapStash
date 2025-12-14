"""
Notification Service
Sends notifications via ntfy for new Snapchat messages and media.
Also integrates with APNs for native iOS push notifications.
"""

import logging
import os
import base64
from typing import Optional, Dict, Any
import httpx
from sqlalchemy.orm import Session

from .settings_service import get_settings_service

logger = logging.getLogger(__name__)


class NotificationService:
    """Service for sending ntfy notifications and APNs push notifications"""

    def __init__(self, db: Optional[Session] = None):
        """Initialize notification service with optional database session"""
        self.db = db
        self.settings_service = get_settings_service(db)
        self._apns_service = None

    def _get_apns_service(self):
        """Lazy load APNs service"""
        if self._apns_service is None:
            from .apns_service import get_apns_service
            self._apns_service = get_apns_service(self.db)
        return self._apns_service

    def _get_sender_avatar_url(self, sender_id: Optional[str]) -> Optional[str]:
        if not sender_id:
            logger.warning("_get_sender_avatar_url called with no sender_id")
            return None
        if not self.db:
            logger.warning("_get_sender_avatar_url called with no database session")
            return None
        try:
            from ..models import User

            user = self.db.query(User).filter(User.id == sender_id).first()
            if not user:
                logger.warning(f"User not found for sender_id: {sender_id}")
                return None
            if not user.bitmoji_url:
                logger.warning(f"User {sender_id} has no bitmoji_url")
                return None
            logger.info(f"Found bitmoji_url for {sender_id}: {user.bitmoji_url}")
            return user.bitmoji_url
        except Exception as e:
            logger.error(f"Failed to resolve sender avatar URL for {sender_id}: {e}")
            return None

    def _is_enabled(self) -> bool:
        """Check if ntfy notifications are enabled"""
        return self.settings_service.get_setting("ntfy_enabled", False)

    def _create_basic_auth_header(self, username: str, password: str) -> str:
        """Create basic auth header from username and password"""
        credentials = f"{username}:{password}"
        encoded_credentials = base64.b64encode(credentials.encode('utf-8')).decode('utf-8')
        return f"Basic {encoded_credentials}"

    def _get_headers(self) -> Dict[str, str]:
        """Get HTTP headers for ntfy requests"""
        headers = {}

        # Add authentication - prefer username/password over token
        username = self.settings_service.get_setting("ntfy_username")
        password = self.settings_service.get_setting("ntfy_password")
        auth_token = self.settings_service.get_setting("ntfy_auth_token")

        if username and password:
            # Use Basic authentication with username/password
            headers["Authorization"] = self._create_basic_auth_header(username, password)
        elif auth_token:
            # Fall back to Bearer token authentication
            headers["Authorization"] = f"Bearer {auth_token}"

        # Add priority
        priority = self.settings_service.get_setting("ntfy_priority", "default")
        if priority:
            headers["Priority"] = priority

        return headers

    async def send_notification(
        self,
        topic: Optional[str],
        title: str,
        message: str,
        tags: Optional[str] = None,
        click_url: Optional[str] = None,
    ) -> bool:
        """
        Send a text notification to ntfy using JSON format

        Args:
            topic: ntfy topic to send to
            title: Notification title
            message: Notification message
            tags: Comma-separated emoji tags (e.g. "warning,skull")
            click_url: URL to open when notification is clicked

        Returns:
            True if notification was sent successfully, False otherwise
        """
        if not self._is_enabled():
            logger.debug("Ntfy notifications are disabled")
            return False

        if not topic:
            logger.warning("No ntfy topic configured, skipping notification")
            return False

        try:
            server_url = self.settings_service.get_setting("ntfy_server_url", "https://ntfy.sh")
            # POST to root URL when using JSON format
            url = server_url.rstrip('/')

            # Build JSON payload
            payload = {
                "topic": topic,
                "message": message,
                "title": title,
                "icon": "https://static.vecteezy.com/system/resources/previews/023/741/177/non_2x/snapchat-logo-icon-social-media-icon-free-png.png",
            }

            # Add optional fields
            if tags:
                # Convert comma-separated string to array
                payload["tags"] = [tag.strip() for tag in tags.split(",")]

            if click_url:
                payload["click"] = click_url

            # Get priority from settings
            priority = self.settings_service.get_setting("ntfy_priority", "default")
            # Map priority names to numbers for JSON API
            priority_map = {
                "min": 1,
                "low": 2,
                "default": 3,
                "high": 4,
                "urgent": 5,
            }
            if priority in priority_map:
                payload["priority"] = priority_map[priority]

            # Build headers for authentication
            headers = {
                "Content-Type": "application/json",
            }

            # Add authentication - prefer username/password over token
            username = self.settings_service.get_setting("ntfy_username")
            password = self.settings_service.get_setting("ntfy_password")
            auth_token = self.settings_service.get_setting("ntfy_auth_token")

            if username and password:
                headers["Authorization"] = self._create_basic_auth_header(username, password)
            elif auth_token:
                headers["Authorization"] = f"Bearer {auth_token}"

            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(url, json=payload, headers=headers)

                if response.status_code == 200:
                    logger.info(f"Notification sent successfully to topic: {topic}")
                    return True
                else:
                    logger.error(f"Failed to send notification: {response.status_code} - {response.text}")
                    return False

        except Exception as e:
            logger.error(f"Error sending ntfy notification: {e}")
            return False

    async def send_media_notification(
        self,
        topic: Optional[str],
        title: str,
        message: str,
        file_path: str,
        filename: str,
        tags: Optional[str] = None,
        click_url: Optional[str] = None,
    ) -> bool:
        """
        Send a notification with media file attachment to ntfy

        Args:
            topic: ntfy topic to send to
            title: Notification title
            message: Notification message
            file_path: Path to the media file to attach
            filename: Filename to use for the attachment
            tags: Comma-separated emoji tags (e.g. "warning,skull")
            click_url: URL to open when notification is clicked

        Returns:
            True if notification was sent successfully, False otherwise
        """
        if not self._is_enabled():
            logger.debug("Ntfy notifications are disabled")
            return False

        if not topic:
            logger.warning("No ntfy topic configured, skipping notification")
            return False

        try:
            from pathlib import Path

            file_path_obj = Path(file_path)
            if not file_path_obj.exists():
                logger.error(f"Media file does not exist: {file_path}")
                # Fallback to text notification
                return await self.send_notification(topic, title, message, tags, click_url)

            # Get file size for logging
            file_size = file_path_obj.stat().st_size
            logger.info(f"Sending media notification: {filename} ({file_size} bytes)")

            server_url = self.settings_service.get_setting("ntfy_server_url", "https://ntfy.sh")
            url = f"{server_url}/{topic}"

            # Build headers - using header format for file uploads
            headers = {
                "Title": title,
                "Filename": filename,
                "Message": message,
                "Icon": "https://static.vecteezy.com/system/resources/previews/023/741/177/non_2x/snapchat-logo-icon-social-media-icon-free-png.png",
            }

            if tags:
                headers["Tags"] = tags

            if click_url:
                headers["Click"] = click_url

            # Add authentication - prefer username/password over token
            username = self.settings_service.get_setting("ntfy_username")
            password = self.settings_service.get_setting("ntfy_password")
            auth_token = self.settings_service.get_setting("ntfy_auth_token")

            if username and password:
                headers["Authorization"] = self._create_basic_auth_header(username, password)
            elif auth_token:
                headers["Authorization"] = f"Bearer {auth_token}"

            # Read the file data
            with open(file_path, 'rb') as f:
                file_data = f.read()

            # Send with longer timeout for file uploads
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(url, content=file_data, headers=headers)

                if response.status_code == 200:
                    logger.info(f"Media notification sent successfully: {filename}")
                    return True
                else:
                    logger.error(f"Failed to send media notification: {response.status_code} - {response.text}")
                    return False

        except Exception as e:
            logger.error(f"Error sending media notification: {e}")
            return False

    async def send_text_message_notification(
        self,
        sender_username: str,
        text: str,
        conversation_name: Optional[str] = None,
        conversation_id: Optional[str] = None,
        sender_id: Optional[str] = None,
    ) -> bool:
        """
        Send notification for a new text message

        Args:
            sender_username: Username of the message sender
            text: Message text content
            conversation_name: Name of the conversation (optional)
            conversation_id: ID of the conversation for deep linking (optional)

        Returns:
            True if notification was sent successfully
        """
        # Check if sender should be excluded from notifications
        exclude_name = self.settings_service.get_setting("dm_exclude_name")
        if exclude_name and sender_username == exclude_name:
            logger.debug(f"Skipping notification for excluded sender: {sender_username}")
            return False

        # Send APNs notification (native iOS push)
        try:
            apns = self._get_apns_service()
            sender_avatar_url = self._get_sender_avatar_url(sender_id)
            await apns.send_text_message_notification(
                sender_username=sender_username,
                text=text,
                conversation_id=conversation_id,
                sender_avatar_url=sender_avatar_url,
                sender_id=sender_id,
            )
        except Exception as e:
            logger.warning(f"APNs notification failed: {e}")

        # Send ntfy notification
        topic = self.settings_service.get_setting("ntfy_text_topic")
        if not topic:
            logger.debug("No text message topic configured")
            return False

        # Build click URL with conversation ID for deep linking
        click_url = f"SnapStash://conversation?id={conversation_id}" if conversation_id else "SnapStash://"

        # Don't truncate - send full message like the reference implementation
        return await self.send_notification(
            topic=topic,
            title=sender_username,  # Just sender name as title
            message=text,  # Full message text
            tags="snapchat",
            click_url=click_url,
        )

    async def send_media_message_notification(
        self,
        sender_username: str,
        media_type: str,
        media_id: int,
        conversation_name: Optional[str] = None,
        text: Optional[str] = None,
        file_path: Optional[str] = None,
        conversation_id: Optional[str] = None,
        sender_id: Optional[str] = None,
    ) -> bool:
        """
        Send notification for a new media message

        Args:
            sender_username: Username of the message sender
            media_type: Type of media (image, video, etc.)
            media_id: Database ID of the media asset
            conversation_name: Name of the conversation (optional)
            text: Optional text accompanying the media
            file_path: Optional path to the media file (for attachment)
            conversation_id: ID of the conversation for deep linking (optional)

        Returns:
            True if notification was sent successfully
        """
        # Check if sender should be excluded from notifications
        exclude_name = self.settings_service.get_setting("dm_exclude_name")
        if exclude_name and sender_username == exclude_name:
            logger.debug(f"Skipping notification for excluded sender: {sender_username}")
            return False

        # Send APNs notification (native iOS push)
        try:
            apns = self._get_apns_service()
            sender_avatar_url = self._get_sender_avatar_url(sender_id)

            # Build media URL for rich notifications (images only)
            normalized_media_type = (media_type or "").lower()
            image_extensions = (".jpg", ".jpeg", ".png", ".gif", ".webp", ".heic", ".heif")
            looks_like_image = (
                normalized_media_type in {"image", "photo"}
                or "image" in normalized_media_type
                or any((file_path or "").lower().endswith(ext) for ext in image_extensions)
            )

            media_url = None
            if looks_like_image and media_id:
                # Construct full URL to media endpoint
                # The iOS app will use its configured API base URL + this path
                media_url = f"/api/media/{media_id}/file"

            logger.info(
                "Media notification: media_id=%s media_type=%s looks_like_image=%s file_path=%s media_url=%s",
                media_id,
                media_type,
                looks_like_image,
                file_path,
                media_url,
            )

            await apns.send_media_message_notification(
                sender_username=sender_username,
                media_type=media_type,
                conversation_id=conversation_id,
                text=text,
                media_url=media_url,
                sender_avatar_url=sender_avatar_url,
                sender_id=sender_id,
            )
        except Exception as e:
            logger.warning(f"APNs notification failed: {e}")

        # Send ntfy notification
        topic = self.settings_service.get_setting("ntfy_media_topic")
        if not topic:
            logger.debug("No media message topic configured")
            return False

        # Title is just sender name (no emoji to avoid encoding issues)
        title = sender_username

        # Message is either the text or "Sent a {media_type}"
        if text:
            message_body = text
        else:
            message_body = f"Sent a {media_type}"

        # Build click URL with conversation ID for deep linking
        click_url = f"SnapStash://conversation?id={conversation_id}" if conversation_id else "SnapStash://"

        # Try to send with file attachment if enabled and file exists
        if self.settings_service.get_setting("ntfy_attach_media", True) and file_path:
            from pathlib import Path

            # Generate filename
            import os
            ext = os.path.splitext(file_path)[1] or ".jpg"
            filename = f"snapchat_{media_type}_{media_id}{ext}"

            # Send media notification with file attachment
            return await self.send_media_notification(
                topic=topic,
                title=title,
                message=message_body,
                file_path=file_path,
                filename=filename,
                tags="snapchat,media",
                click_url=click_url,
            )
        else:
            # Fallback to text notification without attachment
            return await self.send_notification(
                topic=topic,
                title=title,
                message=message_body,
                tags="snapchat,media",
                click_url=click_url,
            )

    async def send_batch_notification(
        self,
        new_text_count: int,
        new_media_count: int,
        topic: Optional[str] = None,
    ) -> bool:
        """
        Send a batch notification for multiple new messages

        Args:
            new_text_count: Number of new text messages
            new_media_count: Number of new media messages
            topic: Optional topic override (uses text topic by default)

        Returns:
            True if notification was sent successfully
        """
        if new_text_count == 0 and new_media_count == 0:
            return False

        # Use text topic by default, or media topic if only media
        if not topic:
            if new_text_count > 0:
                topic = self.settings_service.get_setting("ntfy_text_topic")
            else:
                topic = self.settings_service.get_setting("ntfy_media_topic")

        if not topic:
            logger.debug("No topic configured for batch notification")
            return False

        # Build message
        parts = []
        if new_text_count > 0:
            parts.append(f"{new_text_count} text message{'s' if new_text_count != 1 else ''}")
        if new_media_count > 0:
            parts.append(f"{new_media_count} media message{'s' if new_media_count != 1 else ''}")

        message = f"Received {' and '.join(parts)}"

        return await self.send_notification(
            topic=topic,
            title="New Snapchat Messages",
            message=message,
            tags="bell,snapchat",
        )

    async def send_ingestion_complete_notification(
        self,
        messages_count: int,
        media_count: int,
        errors_count: int = 0,
    ) -> bool:
        """
        Send notification when ingestion is complete

        Args:
            messages_count: Number of messages processed
            media_count: Number of media files processed
            errors_count: Number of errors encountered

        Returns:
            True if notification was sent successfully
        """
        # Send to text topic by default
        topic = self.settings_service.get_setting("ntfy_text_topic")
        if not topic:
            logger.debug("No topic configured for ingestion notifications")
            return False

        if errors_count > 0:
            title = "Snapchat Ingestion Complete (with errors)"
            tags = "warning,snapchat"
        else:
            title = "Snapchat Ingestion Complete"
            tags = "white_check_mark,snapchat"

        message = f"Processed {messages_count} messages and {media_count} media files"
        if errors_count > 0:
            message += f"\nEncountered {errors_count} errors"

        return await self.send_notification(
            topic=topic,
            title=title,
            message=message,
            tags=tags,
        )

    async def send_ingestion_error_notification(
        self,
        error_message: str,
    ) -> bool:
        """
        Send notification when ingestion fails

        Args:
            error_message: Error message to include

        Returns:
            True if notification was sent successfully
        """
        # Send to text topic by default
        topic = self.settings_service.get_setting("ntfy_text_topic")
        if not topic:
            logger.debug("No topic configured for error notifications")
            return False

        # Truncate long error messages
        display_error = error_message[:200] + "..." if len(error_message) > 200 else error_message

        return await self.send_notification(
            topic=topic,
            title="Snapchat Ingestion Failed",
            message=f"Error: {display_error}",
            tags="x,snapchat,warning",
        )


# Global notification service instance
_notification_service: Optional[NotificationService] = None


def get_notification_service(db: Optional[Session] = None) -> NotificationService:
    """Get the global notification service instance"""
    global _notification_service
    if _notification_service is None:
        _notification_service = NotificationService(db)
    return _notification_service

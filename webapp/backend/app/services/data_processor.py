#!/usr/bin/env python3
"""
Data Processor Service
Processes unified parser data and stores in database.
Business logic component that uses StorageService for data access.
"""

import logging
import asyncio
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any
from sqlalchemy.orm import Session

from .storage import StorageService
from .notification_service import get_notification_service

logger = logging.getLogger(__name__)


class DataProcessorService:
    """Process unified parser data and store in database"""
    
    def __init__(self, db: Session):
        self.db = db
        self.storage = StorageService(db)
    
    def process_parser_results(
        self,
        messages: List[Dict[str, Any]],
        media_assets: List[Dict[str, Any]],
        ingest_run_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Process results from unified parser and store in database
        
        Args:
            messages: List of message dictionaries from parser
            media_assets: List of media asset dictionaries from parser
            ingest_run_id: Optional ingest run ID to link results to
        
        Returns:
            Dictionary with processing results and statistics
        """
        try:
            results = {
                "users_processed": 0,
                "conversations_processed": 0,
                "messages_processed": 0,
                "media_assets_processed": 0,
                "errors": [],
                "warnings": [],
            }
            
            # Extract unique users from messages
            unique_users = {}
            for msg in messages:
                # Handle both nested sender format and flat format
                if "sender" in msg:
                    sender = msg["sender"]
                    if "id" in sender:
                        unique_users[sender["id"]] = sender
                elif "sender_id" in msg:
                    # Unified parser flat format
                    sender_id = msg["sender_id"]
                    if sender_id:
                        unique_users[sender_id] = {
                            "id": sender_id,
                            "username": msg.get("username", ""),
                            "display_name": msg.get("display_name", ""),
                            "bitmoji_avatar_id": msg.get("bitmoji_avatar_id", "") or None,
                            "bitmoji_selfie_id": msg.get("bitmoji_selfie_id", "") or None
                        }
            
            # Process users
            logger.info(f"Processing {len(unique_users)} unique users")
            for user_data in unique_users.values():
                try:
                    self.storage.upsert_user(user_data)
                    results["users_processed"] += 1
                except Exception as e:
                    error_msg = f"Error processing user {user_data.get('id')}: {e}"
                    logger.error(error_msg)
                    results["errors"].append(error_msg)
            
            # Commit users before proceeding
            try:
                self.db.commit()
                logger.info(f"Successfully committed {results['users_processed']} users")
            except Exception as e:
                logger.error(f"Failed to commit users: {e}")
                self.db.rollback()
                results["errors"].append(f"Failed to commit users: {e}")
            
            # Extract unique conversations
            unique_conversations = {}
            for msg in messages:
                if "conversation_id" in msg:
                    conv_id = msg["conversation_id"]
                    if conv_id not in unique_conversations:
                        # Safely convert timestamp to float - use _ms version for milliseconds
                        timestamp = msg.get("creation_timestamp_ms", 0)
                        try:
                            timestamp = float(timestamp) if timestamp else 0
                        except (ValueError, TypeError):
                            timestamp = 0
                        
                        unique_conversations[conv_id] = {
                            "id": conv_id,
                            "last_message_at": datetime.fromtimestamp(timestamp / 1000) if timestamp > 0 else datetime.utcnow()
                        }
                    else:
                        # Update with latest timestamp
                        timestamp = msg.get("creation_timestamp_ms", 0)
                        try:
                            timestamp = float(timestamp) if timestamp else 0
                        except (ValueError, TypeError):
                            timestamp = 0
                            
                        if timestamp > 0:
                            msg_time = datetime.fromtimestamp(timestamp / 1000)
                            if msg_time > unique_conversations[conv_id]["last_message_at"]:
                                unique_conversations[conv_id]["last_message_at"] = msg_time
            
            # Process conversations
            logger.info(f"Processing {len(unique_conversations)} unique conversations")
            for conv_data in unique_conversations.values():
                try:
                    self.storage.upsert_conversation(conv_data)
                    results["conversations_processed"] += 1
                except Exception as e:
                    error_msg = f"Error processing conversation {conv_data.get('id')}: {e}"
                    logger.error(error_msg)
                    results["errors"].append(error_msg)
            
            # Commit conversations before proceeding
            try:
                self.db.commit()
                logger.info(f"Successfully committed {results['conversations_processed']} conversations")
            except Exception as e:
                logger.error(f"Failed to commit conversations: {e}")
                self.db.rollback()
                results["errors"].append(f"Failed to commit conversations: {e}")
            
            # Process messages first - handle linked media assets inline
            logger.info(f"Processing {len(messages)} messages")
            processed_media_cache_ids = set()  # Track media already processed via messages
            new_messages_data = []  # Track newly created messages for notifications

            for msg_data in messages:
                try:
                    # Convert message data to database format
                    db_message_data = self._convert_message_for_db(msg_data)

                    # Skip messages without sender_id (required field)
                    if not db_message_data.get("sender_id"):
                        results["warnings"].append(f"Skipping message without sender_id: {db_message_data.get('server_message_id', 'unknown')}")
                        continue

                    # Skip messages without creation_timestamp (required field)
                    if not db_message_data.get("creation_timestamp"):
                        results["warnings"].append(f"Skipping message without creation_timestamp: {db_message_data.get('server_message_id', 'unknown')}")
                        continue

                    # Handle linked media asset from DataLinker
                    if "media_asset" in msg_data and msg_data["media_asset"]:
                        try:
                            media_data = msg_data["media_asset"]
                            asset, is_new_asset = self.storage.create_media_asset(media_data)
                            db_message_data["media_asset_id"] = asset.id
                            results["media_assets_processed"] += 1
                            if isinstance(msg_data.get("media_asset"), dict):
                                msg_data["media_asset"]["id"] = asset.id
                            msg_data["media_asset_id"] = asset.id

                            # Track this media so we don't process it again
                            if asset.cache_id:
                                processed_media_cache_ids.add(asset.cache_id)

                        except Exception as e:
                            error_msg = f"Error processing linked media asset for message: {e}"
                            logger.error(error_msg)
                            results["errors"].append(error_msg)

                    message, is_new = self.storage.create_message(db_message_data)
                    results["messages_processed"] += 1

                    # Track newly created messages for notifications
                    if is_new:
                        new_messages_data.append(msg_data)

                except Exception as e:
                    error_msg = f"Error processing message: {e}"
                    logger.error(error_msg)
                    results["errors"].append(error_msg)

            # Process any standalone media assets (not linked to messages)
            standalone_media_count = 0
            for media_data in media_assets:
                try:
                    # Skip if already processed via message linking
                    if media_data.get("cache_id") in processed_media_cache_ids:
                        continue

                    asset, is_new = self.storage.create_media_asset(media_data)
                    results["media_assets_processed"] += 1
                    standalone_media_count += 1

                except Exception as e:
                    error_msg = f"Error processing standalone media asset {media_data.get('original_filename')}: {e}"
                    logger.error(error_msg)
                    results["errors"].append(error_msg)
            
            if standalone_media_count > 0:
                logger.info(f"Processed {standalone_media_count} standalone media assets")
            
            # Commit all data
            try:
                self.db.commit()
                logger.info(f"Successfully committed {results['messages_processed']} messages and {results['media_assets_processed']} media assets")
            except Exception as e:
                logger.error(f"Failed to commit data: {e}")
                self.db.rollback()
                results["errors"].append(f"Failed to commit data: {e}")

            # Send individual notifications for newly created messages
            if len(new_messages_data) > 0:
                try:
                    notification_service = get_notification_service(self.db)
                    logger.info(f"Sending notifications for {len(new_messages_data)} new messages")

                    # Send individual notifications for each new message
                    for msg_data in new_messages_data:
                        try:
                            # Filter out messages from ad conversations (one-sided non-group chats)
                            conversation_id = msg_data.get("conversation_id")
                            if conversation_id and self.storage.is_conversation_ad(conversation_id):
                                logger.debug(f"Skipping notification for ad conversation: {conversation_id}")
                                continue

                            # Get sender information
                            sender_username = msg_data.get("username", "")
                            display_name = msg_data.get("display_name", "")
                            sender = display_name if display_name else sender_username
                            if not sender:
                                sender = f"User {msg_data.get('sender_id', 'Unknown')}"

                            content_type = msg_data.get("content_type", 1)
                            text = msg_data.get("text", "")

                            # Send appropriate notification based on content type
                            if content_type == 1:  # Text only
                                if text:
                                    asyncio.create_task(
                                        notification_service.send_text_message_notification(
                                            sender_username=sender,
                                            text=text,
                                            conversation_id=conversation_id,
                                            sender_id=msg_data.get("sender_id"),
                                        )
                                    )
                            elif content_type == 0 or content_type == 2:  # Media or mixed
                                # Get media information if available
                                media_asset = msg_data.get("media_asset")
                                if media_asset:
                                    media_type = media_asset.get("file_type", "media")
                                    media_id = media_asset.get("id") or msg_data.get("media_asset_id") or 0
                                    try:
                                        media_id = int(media_id)
                                    except (TypeError, ValueError):
                                        media_id = 0
                                    file_path = media_asset.get("file_path", "")
                                    logger.info(
                                        "Message media detected: conversation_id=%s content_type=%s media_id=%s media_type=%s file_path=%s media_asset_keys=%s",
                                        conversation_id,
                                        content_type,
                                        media_id,
                                        media_type,
                                        file_path,
                                        sorted(list(media_asset.keys())),
                                    )

                                    # Prepare message text
                                    if text:
                                        message_text = text
                                    else:
                                        message_text = f"Sent a {media_type}"

                                    asyncio.create_task(
                                        notification_service.send_media_message_notification(
                                            sender_username=sender,
                                            media_type=media_type,
                                            media_id=media_id,
                                            text=message_text,
                                            file_path=file_path if file_path else None,
                                            conversation_id=conversation_id,
                                            sender_id=msg_data.get("sender_id"),
                                        )
                                    )
                                else:
                                    # Media message but no asset info, send text notification
                                    message_text = text if text else "Sent media"
                                    logger.info(
                                        "Message media detected but missing media_asset: conversation_id=%s content_type=%s",
                                        conversation_id,
                                        content_type,
                                    )
                                    asyncio.create_task(
                                        notification_service.send_text_message_notification(
                                            sender_username=sender,
                                            text=message_text,
                                            conversation_id=conversation_id
                                        )
                                    )

                        except Exception as e:
                            logger.warning(f"Failed to send notification for individual message: {e}")

                except Exception as e:
                    logger.warning(f"Failed to initialize notification service: {e}")

            logger.info(f"Processing completed: {results}")
            return results

        except Exception as e:
            logger.error(f"Error in unified data processing: {e}")
            self.db.rollback()
            raise
    
    def _convert_message_for_db(self, parser_message: Dict[str, Any]) -> Dict[str, Any]:
        """Convert parser message format to database message format"""
        db_message = {}
        
        # Direct field mappings
        field_mappings = {
            "text": "text",
            "content_type": "content_type", 
            "cache_id": "cache_id",
            "creation_timestamp_ms": "creation_timestamp",  # Use the _ms version for integer timestamp
            "read_timestamp_ms": "read_timestamp",  # Use the _ms version for integer timestamp
            "parsing_successful": "parsing_successful",
            "raw_message_content": "raw_message_content",
            "client_message_id": "client_message_id",
            "server_message_id": "server_message_id",
            "conversation_id": "conversation_id",
            "sender_id": "sender_id",  # Add direct sender_id mapping
        }
        
        for parser_key, db_key in field_mappings.items():
            if parser_key in parser_message:
                value = parser_message[parser_key]
                
                # Handle timestamp fields - convert to integers if needed
                if parser_key in ["creation_timestamp_ms", "read_timestamp_ms"]:
                    try:
                        if value is not None:
                            value = int(value) if value else None
                        # For creation_timestamp, provide fallback if None
                        if parser_key == "creation_timestamp_ms" and value is None:
                            from datetime import datetime
                            value = int(datetime.utcnow().timestamp() * 1000)
                    except (ValueError, TypeError):
                        # For creation_timestamp, use current timestamp as fallback
                        if parser_key == "creation_timestamp_ms":
                            from datetime import datetime
                            value = int(datetime.utcnow().timestamp() * 1000)
                        else:
                            value = None
                
                db_message[db_key] = value
        
        # Handle sender (nested object) - fallback for legacy format
        if "sender" in parser_message and isinstance(parser_message["sender"], dict) and "id" in parser_message["sender"]:
            if "sender_id" not in db_message or not db_message["sender_id"]:
                db_message["sender_id"] = parser_message["sender"]["id"]
        
        return db_message

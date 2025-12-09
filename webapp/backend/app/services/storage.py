#!/usr/bin/env python3
"""
Storage Service Layer
Handles persistence of unified Snapchat objects (Users, Conversations, Messages, MediaAssets).
"""

import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple, Any, Set
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy import and_, desc, asc, func, or_

from ..database import get_db, engine, SessionLocal
from ..models import User, Conversation, Message, MediaAsset, IngestRun, Device, ConversationParticipant, Base
from ..config import get_settings
import html

logger = logging.getLogger(__name__)


class StorageService:
    """Handles database operations for Snapchat data"""
    
    def __init__(self, db: Session):
        self.db = db
    
    # User operations
    def upsert_user(self, user_data: Dict[str, Any]) -> User:
        """Create or update a user"""
        try:
            existing_user = self.db.query(User).filter(User.id == user_data["id"]).first()
            
            if existing_user:
                # Update existing user
                for key, value in user_data.items():
                    if hasattr(existing_user, key):
                        setattr(existing_user, key, value)
                existing_user.updated_at = datetime.utcnow()
                logger.debug(f"Updated user {user_data['id']}")
                return existing_user
            else:
                # Create new user
                new_user = User(**user_data)
                self.db.add(new_user)
                logger.debug(f"Created new user {user_data['id']}")
                return new_user
                
        except Exception as e:
            logger.error(f"Error upserting user {user_data.get('id')}: {e}")
            self.db.rollback()
            raise
    
    def get_user_by_id(self, user_id: str) -> Optional[User]:
        """Get user by ID"""
        return self.db.query(User).filter(User.id == user_id).first()
    
    def get_users(self, limit: int = 100, offset: int = 0) -> List[User]:
        """Get paginated list of users"""
        return self.db.query(User).offset(offset).limit(limit).all()
    
    # Conversation operations
    def upsert_conversation(self, conversation_data: Dict[str, Any]) -> Conversation:
        """Create or update a conversation"""
        try:
            existing_conv = self.db.query(Conversation).filter(
                Conversation.id == conversation_data["id"]
            ).first()
            
            if existing_conv:
                # Update existing conversation
                for key, value in conversation_data.items():
                    if hasattr(existing_conv, key):
                        setattr(existing_conv, key, value)
                existing_conv.updated_at = datetime.utcnow()
                logger.debug(f"Updated conversation {conversation_data['id']}")
                return existing_conv
            else:
                # Create new conversation
                new_conv = Conversation(**conversation_data)
                self.db.add(new_conv)
                logger.debug(f"Created new conversation {conversation_data['id']}")
                return new_conv
                
        except Exception as e:
            logger.error(f"Error upserting conversation {conversation_data.get('id')}: {e}")
            self.db.rollback()
            raise
    
    def get_conversation_by_id(self, conversation_id: str) -> Optional[Conversation]:
        """Get conversation by ID"""
        return self.db.query(Conversation).filter(Conversation.id == conversation_id).first()
    
    def is_conversation_ad(self, conversation_id: str) -> bool:
        """
        Check if a conversation is likely an advertisement.
        
        An ad is defined as:
        - Non-group chat AND
        - Has only one unique sender (one-sided conversation)
        
        Returns:
            True if the conversation appears to be an ad, False otherwise
        """
        conversation = self.get_conversation_by_id(conversation_id)
        if not conversation:
            return False
        
        # Group chats are not ads
        if conversation.is_group_chat:
            return False
        
        # Check if conversation has only one unique sender
        unique_sender_count = (
            self.db.query(func.count(func.distinct(Message.sender_id)))
            .filter(Message.conversation_id == conversation_id)
            .scalar()
        )
        
        # One-sided non-group chat = likely an ad
        return unique_sender_count == 1
    
    def get_conversations(self, limit: int = 100, offset: int = 0, exclude_ads: bool = False) -> List[Conversation]:
        """Get paginated list of conversations"""
        query = (self.db.query(Conversation)
                .order_by(desc(Conversation.last_message_at)))
        
        if exclude_ads:
            # Filter out conversations that are likely ads:
            # 1. Non-group chats AND
            # 2. Have only one unique sender (one-sided conversations)
            from sqlalchemy import func, and_
            
            # Subquery to get conversations with only one unique sender
            one_sided_convs = (
                self.db.query(Message.conversation_id)
                .group_by(Message.conversation_id)
                .having(func.count(func.distinct(Message.sender_id)) == 1)
                .subquery()
            )
            
            # Exclude non-group chats that are one-sided
            query = query.filter(
                ~and_(
                    Conversation.is_group_chat == False,
                    Conversation.id.in_(one_sided_convs)
                )
            )
        
        return query.offset(offset).limit(limit).all()

    def upsert_conversation_participants(self, conversation_id: str, participants: List[Dict[str, Any]]) -> List[ConversationParticipant]:
        """Create or update conversation participants for a group chat"""
        try:
            # Remove existing participants for this conversation
            self.db.query(ConversationParticipant).filter(
                ConversationParticipant.conversation_id == conversation_id
            ).delete()
            
            # Add new participants
            new_participants = []
            for participant_data in participants:
                participant_obj = ConversationParticipant(
                    conversation_id=conversation_id,
                    user_id=participant_data['user_id'],
                    join_timestamp=participant_data.get('join_timestamp'),
                    unknown_field_2=participant_data.get('unknown_field_2'),
                    unknown_field_3=participant_data.get('unknown_field_3'),
                    unknown_field_9=participant_data.get('unknown_field_9')
                )
                self.db.add(participant_obj)
                new_participants.append(participant_obj)
            
            logger.debug(f"Upserted {len(new_participants)} participants for conversation {conversation_id}")
            return new_participants
            
        except Exception as e:
            logger.error(f"Error upserting participants for conversation {conversation_id}: {e}")
            self.db.rollback()
            raise

    def get_conversation_participants(self, conversation_id: str) -> List[ConversationParticipant]:
        """Get all participants for a conversation"""
        return (self.db.query(ConversationParticipant)
                .filter(ConversationParticipant.conversation_id == conversation_id)
                .all())

    def populate_individual_dm_names(self) -> Dict[str, Any]:
        """Populate names for individual DM conversations based on the other participant"""
        results = {
            'conversations_updated': 0,
            'conversations_skipped': 0,
            'errors': []
        }
        
        try:
            # Get all individual conversations without names
            individual_conversations = self.db.query(Conversation).filter(
                Conversation.is_group_chat == False,
                or_(Conversation.group_name.is_(None), Conversation.group_name == '')
            ).all()
            
            logger.info(f"Found {len(individual_conversations)} individual conversations without names")
            
            for conversation in individual_conversations:
                try:
                    # Get unique senders in this conversation
                    unique_senders = self.db.query(Message.sender_id).filter(
                        Message.conversation_id == conversation.id
                    ).distinct().all()
                    
                    sender_ids = [sender[0] for sender in unique_senders]
                    
                    if len(sender_ids) == 2:
                        # This is a proper DM between 2 people
                        # Get user details for both participants
                        users = self.db.query(User).filter(User.id.in_(sender_ids)).all()
                        
                        if len(users) == 2:
                            # Get settings for DM exclude name
                            settings = get_settings()
                            exclude_name = settings.dm_exclude_name
                            
                            # Build list of participant names, excluding the configured name if set
                            dm_name_parts = []
                            for user in users:
                                raw_name = user.display_name or user.username or user.id[:8]
                                # Decode HTML entities (e.g., &#9829; -> ♥)
                                name = html.unescape(raw_name)
                                # Skip the excluded name if configured
                                if exclude_name and name == exclude_name:
                                    continue
                                dm_name_parts.append(name)
                            
                            # Determine final DM name
                            if len(dm_name_parts) == 1:
                                # One participant after exclusion - use just that name
                                dm_name = dm_name_parts[0]
                            elif len(dm_name_parts) == 2:
                                # Both participants included - sort and join with " & "
                                dm_name_parts.sort()
                                dm_name = " & ".join(dm_name_parts)
                            else:
                                # Fallback - use all names if exclusion didn't work
                                all_names = [html.unescape(user.display_name or user.username or user.id[:8]) for user in users]
                                all_names.sort()
                                dm_name = " & ".join(all_names)
                            
                            # Update conversation
                            conversation.group_name = dm_name
                            results['conversations_updated'] += 1
                            
                            logger.debug(f"Updated DM conversation {conversation.id} with name: {dm_name}")
                        else:
                            logger.debug(f"Could not find both users for conversation {conversation.id}")
                            results['conversations_skipped'] += 1
                    else:
                        logger.debug(f"Conversation {conversation.id} has {len(sender_ids)} senders, skipping")
                        results['conversations_skipped'] += 1
                        
                except Exception as e:
                    error_msg = f"Error processing conversation {conversation.id}: {e}"
                    logger.error(error_msg)
                    results['errors'].append(error_msg)
            
            # Commit changes
            self.db.commit()
            logger.info(f"Updated {results['conversations_updated']} individual conversation names")
            
        except Exception as e:
            error_msg = f"Error in populate_individual_dm_names: {e}"
            logger.error(error_msg)
            results['errors'].append(error_msg)
            self.db.rollback()
        
        return results
    
    # Message operations
    def create_message(self, message_data: Dict[str, Any]) -> Tuple[Message, bool]:
        """
        Create a new message (with deduplication based on conversation_id + creation_timestamp)

        Returns:
            Tuple[Message, bool]: The message object and a boolean indicating if it was newly created (True) or already existed (False)
        """
        try:
            # Check for duplicate message based on conversation_id + creation_timestamp
            if "conversation_id" in message_data and "creation_timestamp" in message_data:
                existing_message = self.db.query(Message).filter(
                    Message.conversation_id == message_data["conversation_id"],
                    Message.creation_timestamp == message_data["creation_timestamp"]
                ).first()

                if existing_message:
                    # Update the existing message with new data, preserving existing non-null values
                    updated = self._update_message_fields(existing_message, message_data)

                    if updated:
                        # Update the updated_at timestamp
                        existing_message.updated_at = datetime.utcnow()
                        self.db.flush()  # Ensure the update is saved
                        #logger.info(f"Updated existing message {existing_message.id} (preserved non-null values) for conversation {message_data['conversation_id']} at timestamp {message_data['creation_timestamp']}")
                    else:
                        logger.debug(f"Message for conversation {message_data['conversation_id']} at timestamp {message_data['creation_timestamp']} already exists with identical data")

                    return existing_message, False  # Return False for existing message
            
            # Ensure required foreign key entities exist
            if "sender_id" in message_data:
                if not self.get_user_by_id(message_data["sender_id"]):
                    logger.warning(f"Creating message for non-existent user {message_data['sender_id']}")

            if "conversation_id" in message_data:
                if not self.get_conversation_by_id(message_data["conversation_id"]):
                    logger.warning(f"Creating message for non-existent conversation {message_data['conversation_id']}")

            new_message = Message(**message_data)
            self.db.add(new_message)
            logger.debug(f"Created new message for conversation {message_data.get('conversation_id')}")
            return new_message, True  # Return True for newly created message

        except Exception as e:
            logger.error(f"Error creating message: {e}")
            self.db.rollback()
            raise
    
    def _update_message_fields(self, existing_message: Message, new_data: Dict[str, Any]) -> bool:
        """
        Update existing message with new data, preserving existing non-null values.
        Only updates a field if the new value is not None/empty and different from current value.
        Returns True if any fields were updated, False otherwise.
        """
        updated = False

        # List of fields that can be updated (excluding primary key, foreign keys, and timestamps)
        updatable_fields = [
            'server_message_id', 'client_message_id', 'text', 'content_type',
            'cache_id', 'read_timestamp', 'parsing_successful', 'raw_message_content',
            'media_asset_id'
        ]

        for field in updatable_fields:
            if field in new_data:
                new_value = new_data[field]
                current_value = getattr(existing_message, field)

                # Skip update if new value is None or empty string and we already have a value
                if current_value is not None and current_value != '':
                    if new_value is None or new_value == '':
                        logger.debug(f"Preserving existing value for field {field} on message {existing_message.id}: keeping '{current_value}'")
                        continue

                # Update if new value is different and not empty/None
                if new_value != current_value and new_value is not None:
                    # For string fields, also check for empty strings
                    if isinstance(new_value, str) and new_value == '' and current_value is not None:
                        logger.debug(f"Preserving existing value for field {field} on message {existing_message.id}: keeping '{current_value}'")
                        continue

                    setattr(existing_message, field, new_value)
                    updated = True
                    logger.debug(f"Updated field {field} on message {existing_message.id}: {current_value} -> {new_value}")

        return updated
    
    def get_messages_by_conversation(
        self,
        conversation_id: str,
        limit: int = 100,
        offset: int = 0,
        since_timestamp: Optional[int] = None,
        until_timestamp: Optional[int] = None,
        content_type: Optional[str] = None,
        has_media: Optional[bool] = None
    ) -> List[Message]:
        """Get messages for a conversation in reverse chronological order (newest first), optionally filtered by timestamp and other criteria"""
        from sqlalchemy.orm import joinedload

        query = (self.db.query(Message)
                .options(joinedload(Message.sender), joinedload(Message.media_asset))
                .filter(Message.conversation_id == conversation_id)
                .order_by(desc(Message.creation_timestamp)))

        if since_timestamp:
            query = query.filter(Message.creation_timestamp >= since_timestamp)

        if until_timestamp:
            query = query.filter(Message.creation_timestamp <= until_timestamp)

        if content_type:
            query = query.filter(Message.content_type == content_type)

        if has_media is not None:
            if has_media:
                query = query.filter(Message.media_references.isnot(None))
            else:
                query = query.filter(Message.media_references.is_(None))

        return query.offset(offset).limit(limit).all()
    
    def get_messages_by_sender(
        self,
        sender_id: str,
        limit: int = 100,
        offset: int = 0
    ) -> List[Message]:
        """Get messages from a specific sender"""
        from sqlalchemy.orm import joinedload
        
        return (self.db.query(Message)
                .options(joinedload(Message.sender), joinedload(Message.media_asset))
                .filter(Message.sender_id == sender_id)
                .order_by(desc(Message.creation_timestamp))
                .offset(offset)
                .limit(limit)
                .all())
    
    def get_message_stats(self) -> Dict[str, Any]:
        """Get message statistics"""
        total_messages = self.db.query(func.count(Message.id)).scalar()
        total_conversations = self.db.query(func.count(Conversation.id)).scalar()
        total_users = self.db.query(func.count(User.id)).scalar()
        
        # Messages by content type
        text_messages = self.db.query(func.count(Message.id)).filter(Message.content_type == 1).scalar()
        media_messages = self.db.query(func.count(Message.id)).filter(Message.content_type == 0).scalar()
        mixed_messages = self.db.query(func.count(Message.id)).filter(Message.content_type == 2).scalar()
        
        return {
            "total_messages": total_messages,
            "total_conversations": total_conversations,
            "total_users": total_users,
            "messages_by_type": {
                "text": text_messages,
                "media": media_messages,
                "mixed": mixed_messages
            }
        }
    
    # Media Asset operations
    def create_media_asset(self, media_data: Dict[str, Any]) -> Tuple[MediaAsset, bool]:
        """
        Create a new media asset

        Returns:
            Tuple[MediaAsset, bool]: The media asset object and a boolean indicating if it was newly created (True) or already existed (False)
        """
        try:
            # Debug logging to understand the media_data structure
            logger.info(f"Creating media asset with data keys: {list(media_data.keys())}")
            if 'file_name' in media_data:
                logger.error(f"Found incorrect 'file_name' field in media_data: {media_data}")
                # Fix the field name on the fly
                media_data['original_filename'] = media_data.pop('file_name')
                logger.info(f"Fixed field name to 'original_filename'")

            # Check for existing asset by file hash to prevent duplicates
            if "file_hash" in media_data and media_data["file_hash"]:
                existing_asset = self.db.query(MediaAsset).filter(
                    MediaAsset.file_hash == media_data["file_hash"]
                ).first()

                if existing_asset:
                    logger.debug(f"Media asset with hash {media_data['file_hash']} already exists")
                    return existing_asset, False  # Return False for existing asset

            new_asset = MediaAsset(**media_data)
            self.db.add(new_asset)
            logger.debug(f"Created new media asset: {media_data.get('original_filename', 'unknown')}")
            return new_asset, True  # Return True for newly created asset

        except Exception as e:
            logger.error(f"Error creating media asset: {e}")
            logger.error(f"Media data that caused error: {media_data}")
            self.db.rollback()
            raise
    
    def get_media_asset_by_id(self, asset_id: int) -> Optional[MediaAsset]:
        """Get media asset by ID"""
        return self.db.query(MediaAsset).filter(MediaAsset.id == asset_id).first()
    
    def get_media_assets_by_cache_id(self, cache_id: str) -> List[MediaAsset]:
        """Get media assets by cache ID"""
        return self.db.query(MediaAsset).filter(MediaAsset.cache_id == cache_id).all()
    
    def get_media_assets_by_sender(
        self,
        sender_id: str,
        file_type: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[MediaAsset]:
        """Get media assets from a specific sender"""
        query = self.db.query(MediaAsset).filter(MediaAsset.sender_id == sender_id)
        
        if file_type:
            query = query.filter(MediaAsset.file_type == file_type)
        
        return (query.order_by(desc(MediaAsset.file_timestamp))
                .offset(offset)
                .limit(limit)
                .all())
    
    def link_message_to_media(self, message_id: int, media_asset_id: int) -> bool:
        """Link a message to a media asset"""
        try:
            message = self.db.query(Message).filter(Message.id == message_id).first()
            if message:
                message.media_asset_id = media_asset_id
                logger.debug(f"Linked message {message_id} to media asset {media_asset_id}")
                return True
            return False
        except Exception as e:
            logger.error(f"Error linking message to media: {e}")
            self.db.rollback()
            raise
    
    def get_existing_media_file_paths(self) -> Set[str]:
        """Get set of all existing media file paths to prevent duplicate transfers"""
        result = self.db.query(MediaAsset.file_path).filter(
            MediaAsset.file_path.isnot(None)
        ).all()
        return {path[0] for path in result if path[0]}
    
    def get_existing_media_filenames(self) -> Set[str]:
        """Get set of all existing media filenames to prevent duplicate transfers"""
        # Get filenames from database
        result = self.db.query(MediaAsset.original_filename).filter(
            MediaAsset.original_filename.isnot(None)
        ).all()
        db_filenames = {filename[0] for filename in result if filename[0]}
        
        # Also check filesystem for orphaned files not in database
        fs_filenames = set()
        import os
        media_dirs = [
            '/app/data/media_storage/shared',
            'data/media_storage/shared'  # relative path fallback
        ]
        
        for media_dir in media_dirs:
            if os.path.exists(media_dir):
                try:
                    for filename in os.listdir(media_dir):
                        if filename.startswith('.'):
                            continue
                        # Remove extension to match database format
                        base_name = filename.split('.')[0]
                        fs_filenames.add(base_name)
                    break  # Use first directory that exists
                except Exception as e:
                    logger.debug(f"Could not read media directory {media_dir}: {e}")
                    continue
        
        # Combine both sets
        all_filenames = db_filenames.union(fs_filenames)
        logger.debug(f"Found {len(db_filenames)} files in database, {len(fs_filenames)} files in filesystem, {len(all_filenames)} total unique files")
        
        return all_filenames
    
    def get_existing_cache_ids_from_messages(self) -> List[str]:
        """Get all cache IDs that are referenced by messages"""
        result = self.db.query(Message.cache_id).filter(
            Message.cache_id.isnot(None),
            Message.cache_id != ''
        ).distinct().all()
        return [cache_id[0] for cache_id in result if cache_id[0]]
    
    def get_total_message_count(self) -> int:
        """Get total count of messages in database for change detection"""
        return self.db.query(func.count(Message.id)).scalar() or 0
    
    # Device operations
    def upsert_device(self, device_data: Dict[str, Any]) -> Device:
        """Create or update a device"""
        try:
            # Try to find existing device by SSH host
            ssh_host = device_data.get('ssh_host')
            existing_device = None
            if ssh_host:
                existing_device = (self.db.query(Device)
                                 .filter(Device.ssh_host == ssh_host)
                                 .first())
            
            if existing_device:
                # Update existing device
                for key, value in device_data.items():
                    if hasattr(existing_device, key):
                        setattr(existing_device, key, value)
                existing_device.last_seen = datetime.utcnow()
                logger.info(f"Updated device {existing_device.id}")
                return existing_device
            else:
                # Create new device
                device_data['last_seen'] = datetime.utcnow()
                new_device = Device(**device_data)
                self.db.add(new_device)
                self.db.flush()  # Flush to get the device ID
                logger.info(f"Created new device: {device_data.get('name')} (ID: {new_device.id})")
                return new_device
                
        except Exception as e:
            logger.error(f"Error upserting device: {e}")
            self.db.rollback()
            raise
    
    def get_device_by_id(self, device_id: int) -> Optional[Device]:
        """Get device by ID"""
        return self.db.query(Device).filter(Device.id == device_id).first()
    
    # Ingest Run operations
    def create_ingest_run(self, run_data: Dict[str, Any]) -> IngestRun:
        """Create a new ingest run"""
        try:
            new_run = IngestRun(**run_data)
            self.db.add(new_run)
            logger.info(f"Created new ingest run for device {run_data.get('device_id')}")
            return new_run
        except Exception as e:
            logger.error(f"Error creating ingest run: {e}")
            self.db.rollback()
            raise
    
    def update_ingest_run(
        self, 
        run_id: int, 
        status: Optional[str] = None,
        messages_extracted: Optional[int] = None,
        media_files_extracted: Optional[int] = None,
        parsing_errors: Optional[int] = None,
        error_message: Optional[str] = None,
        error_details: Optional[Dict[str, Any]] = None,
        extraction_settings: Optional[Dict[str, Any]] = None
    ) -> Optional[IngestRun]:
        """Update an ingest run with results"""
        try:
            run = self.db.query(IngestRun).filter(IngestRun.id == run_id).first()
            if not run:
                return None
            
            if status:
                run.status = status
                if status == "completed":
                    run.completed_at = datetime.utcnow()
            
            if messages_extracted is not None:
                run.messages_extracted = messages_extracted
            
            if media_files_extracted is not None:
                run.media_files_extracted = media_files_extracted
            
            if parsing_errors is not None:
                run.parsing_errors = parsing_errors
            
            if error_message:
                run.error_message = error_message
                
            if error_details:
                run.error_details = error_details
                
            if extraction_settings:
                run.extraction_settings = extraction_settings
            
            self.db.commit()
            run.updated_at = datetime.utcnow()
            logger.info(f"Updated ingest run {run_id} with status {status}")
            return run
            
        except Exception as e:
            logger.error(f"Error updating ingest run: {e}")
            self.db.rollback()
            raise
    
    def get_latest_ingest_runs(self, limit: int = 10) -> List[IngestRun]:
        """Get latest ingest runs"""
        return (self.db.query(IngestRun)
                .order_by(desc(IngestRun.started_at))
                .limit(limit)
                .all())
    
    def get_last_source_message_count(self) -> int:
        """Get the source message count from the last successful ingest run.
        This is used for change detection - if the source count hasn't changed,
        we can skip heavy processing.
        """
        try:
            last_successful_run = (self.db.query(IngestRun)
                .filter(IngestRun.status == "completed")
                .order_by(desc(IngestRun.completed_at))
                .first())
            
            if last_successful_run and last_successful_run.extraction_settings:
                return last_successful_run.extraction_settings.get('source_message_count', 0)
            return 0
        except Exception as e:
            logger.warning(f"Failed to get last source message count: {e}")
            return 0

    def get_last_source_timestamp(self) -> int:
        """Get the latest source message timestamp from the last successful ingest run.
        This is used for fast change detection - if the timestamp hasn't changed,
        we can skip heavy processing.
        """
        try:
            last_successful_run = (self.db.query(IngestRun)
                .filter(IngestRun.status == "completed")
                .order_by(desc(IngestRun.completed_at))
                .first())
            
            if last_successful_run and last_successful_run.extraction_settings:
                return last_successful_run.extraction_settings.get('source_latest_timestamp', 0)
            return 0
        except Exception as e:
            logger.warning(f"Failed to get last source timestamp: {e}")
            return 0
    
    # Bulk operations for unified parser
    def bulk_insert_unified_data(
        self, 
        users: List[Dict[str, Any]],
        conversations: List[Dict[str, Any]],
        messages: List[Dict[str, Any]],
        media_assets: List[Dict[str, Any]]
    ) -> Dict[str, int]:
        """Bulk insert data from unified parser"""
        try:
            results = {
                "users_created": 0,
                "conversations_created": 0,
                "messages_created": 0,
                "media_assets_created": 0,
                "errors": 0
            }
            
            # Insert users first
            for user_data in users:
                try:
                    self.upsert_user(user_data)
                    results["users_created"] += 1
                except Exception as e:
                    logger.error(f"Error inserting user: {e}")
                    results["errors"] += 1
            
            # Then conversations
            for conv_data in conversations:
                try:
                    self.upsert_conversation(conv_data)
                    results["conversations_created"] += 1
                except Exception as e:
                    logger.error(f"Error inserting conversation: {e}")
                    results["errors"] += 1
            
            # Then media assets (before messages so we can link them)
            for media_data in media_assets:
                try:
                    self.create_media_asset(media_data)
                    results["media_assets_created"] += 1
                except Exception as e:
                    logger.error(f"Error inserting media asset: {e}")
                    results["errors"] += 1
            
            # Finally messages
            for message_data in messages:
                try:
                    self.create_message(message_data)
                    results["messages_created"] += 1
                except Exception as e:
                    logger.error(f"Error inserting message: {e}")
                    results["errors"] += 1
            
            # Commit all changes
            self.db.commit()
            logger.info(f"Bulk insert completed: {results}")
            return results
            
        except Exception as e:
            logger.error(f"Error in bulk insert: {e}")
            self.db.rollback()
            raise
    
    def commit(self):
        """Commit current transaction"""
        try:
            self.db.commit()
        except Exception as e:
            logger.error(f"Error committing transaction: {e}")
            self.db.rollback()
            raise
    
    def rollback(self):
        """Rollback current transaction"""
        self.db.rollback()


    # Additional methods for message API endpoints
    def get_message_by_id(self, message_id: int) -> Optional[Message]:
        """Get a specific message by ID"""
        from sqlalchemy.orm import joinedload
        
        return (self.db.query(Message)
                .options(joinedload(Message.sender), joinedload(Message.media_asset))
                .filter(Message.id == message_id)
                .first())
    
    def get_messages_with_filters(
        self,
        since_timestamp: Optional[int] = None,
        until_timestamp: Optional[int] = None,
        content_type: Optional[int] = None,
        has_media: Optional[bool] = None,
        limit: int = 50,
        offset: int = 0
    ) -> List[Message]:
        """Get messages with various filters"""
        from sqlalchemy.orm import joinedload
        
        query = (self.db.query(Message)
                .options(joinedload(Message.sender), joinedload(Message.media_asset)))
        
        if since_timestamp:
            query = query.filter(Message.creation_timestamp >= since_timestamp)
        
        if until_timestamp:
            query = query.filter(Message.creation_timestamp <= until_timestamp)
        
        if content_type is not None:
            query = query.filter(Message.content_type == content_type)
        
        if has_media is not None:
            if has_media:
                query = query.filter(Message.media_asset_id.isnot(None))
            else:
                query = query.filter(Message.media_asset_id.is_(None))
        
        return (query.order_by(desc(Message.creation_timestamp))
                .offset(offset)
                .limit(limit)
                .all())
    
    def get_message_stats_by_conversation(self, conversation_id: str) -> Dict[str, Any]:
        """Get message statistics for a conversation"""
        return {
            "total_messages": self.db.query(Message).filter(Message.conversation_id == conversation_id).count(),
            "text_messages": self.db.query(Message).filter(
                and_(Message.conversation_id == conversation_id, Message.content_type == 1)
            ).count(),
            "media_messages": self.db.query(Message).filter(
                and_(Message.conversation_id == conversation_id, Message.content_type.in_([0, 2]))
            ).count(),
            "messages_with_media": self.db.query(Message).filter(
                and_(Message.conversation_id == conversation_id, Message.media_asset_id.isnot(None))
            ).count()
        }
    
    def get_message_stats_by_sender(self, sender_id: str) -> Dict[str, Any]:
        """Get message statistics for a sender"""
        return {
            "total_messages": self.db.query(Message).filter(Message.sender_id == sender_id).count(),
            "text_messages": self.db.query(Message).filter(
                and_(Message.sender_id == sender_id, Message.content_type == 1)
            ).count(),
            "media_messages": self.db.query(Message).filter(
                and_(Message.sender_id == sender_id, Message.content_type.in_([0, 2]))
            ).count(),
            "messages_with_media": self.db.query(Message).filter(
                and_(Message.sender_id == sender_id, Message.media_asset_id.isnot(None))
            ).count()
        }
    
    def get_media_assets_with_filters(
        self,
        file_type: Optional[str] = None,
        category: Optional[str] = None,
        limit: int = 50,
        offset: int = 0
    ) -> List[MediaAsset]:
        """Get media assets with filters"""
        query = self.db.query(MediaAsset)
        
        if file_type:
            query = query.filter(MediaAsset.file_type == file_type)
        
        if category:
            query = query.filter(MediaAsset.category == category)
        
        return (query.order_by(desc(MediaAsset.file_timestamp))
                .offset(offset)
                .limit(limit)
                .all())
    
    def get_media_stats(self, file_type: Optional[str] = None) -> Dict[str, Any]:
        """Get general media statistics"""
        query = self.db.query(MediaAsset)
        if file_type:
            query = query.filter(MediaAsset.file_type == file_type)
        
        total_count = query.count()
        total_size = query.with_entities(func.sum(MediaAsset.file_size)).scalar() or 0
        
        return {
            "total_assets": total_count,
            "total_size_bytes": total_size,
            "total_size_mb": round(total_size / (1024 * 1024), 2),
            "by_type": {
                "image": self.db.query(MediaAsset).filter(MediaAsset.file_type == "image").count(),
                "video": self.db.query(MediaAsset).filter(MediaAsset.file_type == "video").count(),
                "audio": self.db.query(MediaAsset).filter(MediaAsset.file_type == "audio").count(),
            }
        }
    
    def get_media_stats_by_sender(self, sender_id: str, file_type: Optional[str] = None) -> Dict[str, Any]:
        """Get media statistics for a specific sender"""
        query = self.db.query(MediaAsset).filter(MediaAsset.sender_id == sender_id)
        if file_type:
            query = query.filter(MediaAsset.file_type == file_type)
        
        total_count = query.count()
        total_size = query.with_entities(func.sum(MediaAsset.file_size)).scalar() or 0
        
        return {
            "sender_id": sender_id,
            "total_assets": total_count,
            "total_size_bytes": total_size,
            "total_size_mb": round(total_size / (1024 * 1024), 2),
            "by_type": {
                "image": self.db.query(MediaAsset).filter(
                    and_(MediaAsset.sender_id == sender_id, MediaAsset.file_type == "image")
                ).count(),
                "video": self.db.query(MediaAsset).filter(
                    and_(MediaAsset.sender_id == sender_id, MediaAsset.file_type == "video")
                ).count(),
                "audio": self.db.query(MediaAsset).filter(
                    and_(MediaAsset.sender_id == sender_id, MediaAsset.file_type == "audio")
                ).count(),
            }
        }
    
    # Additional methods for conversation and user endpoints
    def get_conversation_participants(self, conversation_id: str) -> List[Tuple[User, Dict[str, Any]]]:
        """Get all participants in a conversation with their message counts"""
        from sqlalchemy import distinct
        
        # Get unique senders in this conversation
        participant_ids = (self.db.query(distinct(Message.sender_id))
                         .filter(Message.conversation_id == conversation_id)
                         .all())
        
        participants = []
        for (sender_id,) in participant_ids:
            user = self.get_user_by_id(sender_id)
            if user:
                message_count = (self.db.query(Message)
                               .filter(and_(Message.conversation_id == conversation_id, 
                                          Message.sender_id == sender_id))
                               .count())
                participants.append((user, {"message_count": message_count}))
        
        return participants
    
    def get_conversation_media_stats(self, conversation_id: str) -> Dict[str, Any]:
        """Get media statistics for a conversation"""
        # Get all messages with media in this conversation
        media_query = (self.db.query(MediaAsset)
                      .join(Message, MediaAsset.id == Message.media_asset_id)
                      .filter(Message.conversation_id == conversation_id))
        
        total_media = media_query.count()
        total_size = media_query.with_entities(func.sum(MediaAsset.file_size)).scalar() or 0
        
        return {
            "total_media_files": total_media,
            "total_size_bytes": total_size,
            "total_size_mb": round(total_size / (1024 * 1024), 2),
            "by_type": {
                "image": media_query.filter(MediaAsset.file_type == "image").count(),
                "video": media_query.filter(MediaAsset.file_type == "video").count(),
                "audio": media_query.filter(MediaAsset.file_type == "audio").count()
            }
        }
    
    def search_users(self, search_term: str, limit: int = 50, offset: int = 0) -> List[User]:
        """Search users by username or display name"""
        return (self.db.query(User)
                .filter(or_(
                    User.username.ilike(f"%{search_term}%"),
                    User.display_name.ilike(f"%{search_term}%")
                ))
                .order_by(User.username)
                .offset(offset)
                .limit(limit)
                .all())
    
    def get_user_conversations(self, user_id: str, limit: int = 20) -> List[Tuple[Conversation, Dict[str, Any]]]:
        """Get conversations that a user has participated in"""
        # Get unique conversation IDs for this user
        conv_ids = (self.db.query(distinct(Message.conversation_id))
                   .filter(Message.sender_id == user_id)
                   .limit(limit)
                   .all())
        
        conversations = []
        for (conv_id,) in conv_ids:
            conversation = self.get_conversation_by_id(conv_id)
            if conversation:
                # Get stats for this user in this conversation
                message_count = (self.db.query(Message)
                               .filter(and_(Message.conversation_id == conv_id,
                                          Message.sender_id == user_id))
                               .count())
                media_count = (self.db.query(Message)
                             .filter(and_(Message.conversation_id == conv_id,
                                        Message.sender_id == user_id,
                                        Message.media_asset_id.isnot(None)))
                             .count())
                
                conversations.append((conversation, {
                    "message_count": message_count,
                    "media_count": media_count
                }))
        
        return sorted(conversations, key=lambda x: x[0].last_message_at or x[0].created_at, reverse=True)
    
    def get_user_activity(self, user_id: str, days: int = 30) -> Dict[str, Any]:
        """Get user activity over the specified number of days"""
        from datetime import datetime, timedelta
        
        # Calculate timestamp range (Snapchat uses milliseconds)
        end_time = datetime.utcnow()
        start_time = end_time - timedelta(days=days)
        start_ms = int(start_time.timestamp() * 1000)
        end_ms = int(end_time.timestamp() * 1000)
        
        # Get messages in time range
        messages_count = (self.db.query(Message)
                         .filter(and_(
                             Message.sender_id == user_id,
                             Message.creation_timestamp >= start_ms,
                             Message.creation_timestamp <= end_ms
                         ))
                         .count())
        
        # Get media in time range
        media_count = (self.db.query(Message)
                      .filter(and_(
                          Message.sender_id == user_id,
                          Message.creation_timestamp >= start_ms,
                          Message.creation_timestamp <= end_ms,
                          Message.media_asset_id.isnot(None)
                      ))
                      .count())
        
        return {
            "messages_sent": messages_count,
            "media_shared": media_count,
            "avg_messages_per_day": round(messages_count / days, 2),
            "avg_media_per_day": round(media_count / days, 2)
        }

    @staticmethod
    def get_database_info() -> Dict[str, Any]:
        """Get database information and statistics"""
        with SessionLocal() as db:
            try:
                # Table counts
                tables_info = {
                    "users": db.query(func.count(User.id)).scalar() or 0,
                    "conversations": db.query(func.count(Conversation.id)).scalar() or 0,
                    "messages": db.query(func.count(Message.id)).scalar() or 0,
                    "media_assets": db.query(func.count(MediaAsset.id)).scalar() or 0,
                    "devices": db.query(func.count(Device.id)).scalar() or 0,
                    "ingest_runs": db.query(func.count(IngestRun.id)).scalar() or 0,
                }
                
                # Message statistics
                message_stats = {}
                if tables_info["messages"] > 0:
                    message_stats = {
                        "text_messages": db.query(func.count(Message.id)).filter(Message.content_type == 1).scalar() or 0,
                        "media_messages": db.query(func.count(Message.id)).filter(Message.content_type == 0).scalar() or 0,
                        "mixed_messages": db.query(func.count(Message.id)).filter(Message.content_type == 2).scalar() or 0,
                        "successful_parsing": db.query(func.count(Message.id)).filter(Message.parsing_successful == True).scalar() or 0,
                        "failed_parsing": db.query(func.count(Message.id)).filter(Message.parsing_successful == False).scalar() or 0,
                    }
                
                # Media statistics
                media_stats = {}
                if tables_info["media_assets"] > 0:
                    media_types = db.query(
                        MediaAsset.file_type,
                        func.count(MediaAsset.id).label('count')
                    ).group_by(MediaAsset.file_type).all()
                    
                    media_stats = {
                        "by_type": {media_type: count for media_type, count in media_types},
                        "with_cache_id": db.query(func.count(MediaAsset.id)).filter(MediaAsset.cache_id.isnot(None)).scalar() or 0,
                        "linked_to_messages": db.query(func.count(MediaAsset.id)).join(Message, MediaAsset.id == Message.media_asset_id).scalar() or 0,
                    }
                
                # Latest ingest run info
                latest_run = None
                if tables_info["ingest_runs"] > 0:
                    latest_run_obj = db.query(IngestRun).order_by(desc(IngestRun.started_at)).first()
                    if latest_run_obj:
                        latest_run = {
                            "id": latest_run_obj.id,
                            "status": latest_run_obj.status,
                            "started_at": latest_run_obj.started_at.isoformat() if latest_run_obj.started_at else None,
                            "completed_at": latest_run_obj.completed_at.isoformat() if latest_run_obj.completed_at else None,
                            "messages_extracted": latest_run_obj.messages_extracted,
                            "media_files_extracted": latest_run_obj.media_files_extracted,
                            "parsing_errors": latest_run_obj.parsing_errors,
                        }
                
                return {
                    "table_counts": tables_info,
                    "message_statistics": message_stats,
                    "media_statistics": media_stats,
                    "latest_ingest_run": latest_run,
                    "database_engine": str(engine.url),
                    "timestamp": datetime.utcnow().isoformat(),
                }
                
            except Exception as e:
                logger.error(f"Error getting database info: {e}")
                raise

    @staticmethod
    def initialize_database():
        """Initialize database tables"""
        try:
            Base.metadata.create_all(bind=engine)
            logger.info("Database tables created successfully")
        except Exception as e:
            logger.error(f"Error initializing database: {e}")
            raise

    @staticmethod
    def run_migrations():
        """Run database migrations using Alembic"""
        import subprocess
        import os
        
        try:
            # Change to backend directory
            backend_dir = "/app"  # Inside Docker container
            
            # Run Alembic upgrade
            result = subprocess.run(
                ["python", "-m", "alembic", "upgrade", "head"],
                cwd=backend_dir,
                capture_output=True,
                text=True,
                timeout=60
            )
            
            if result.returncode == 0:
                logger.info("Database migrations completed successfully")
                logger.info(f"Migration output: {result.stdout}")
                return True
            else:
                logger.error(f"Migration failed: {result.stderr}")
                return False
                
        except Exception as e:
            logger.error(f"Error running migrations: {e}")
            return False

    @staticmethod
    def reset_database():
        """Reset database (drop and recreate all tables)"""
        try:
            logger.warning("Resetting database - all data will be lost!")
            
            # Drop all tables
            Base.metadata.drop_all(bind=engine)
            logger.info("All tables dropped")
            
            # Recreate tables
            Base.metadata.create_all(bind=engine)
            logger.info("All tables recreated")
            
            return True
            
        except Exception as e:
            logger.error(f"Error resetting database: {e}")
            return False

    # Enhanced Statistics Methods
    def get_activity_stats(self, days: int) -> Dict[str, Any]:
        """Get activity statistics for the specified number of days"""
        from datetime import timedelta
        
        end_time = datetime.utcnow()
        start_time = end_time - timedelta(days=days)
        start_ms = int(start_time.timestamp() * 1000)
        end_ms = int(end_time.timestamp() * 1000)
        
        # Messages created in time period
        messages_in_period = (self.db.query(Message)
                             .filter(Message.creation_timestamp >= start_ms)
                             .filter(Message.creation_timestamp <= end_ms)
                             .count())
        
        # Media files in time period
        media_in_period = (self.db.query(MediaAsset)
                          .filter(MediaAsset.file_timestamp >= start_time)
                          .count())
        
        # Ingest runs in time period
        runs_in_period = (self.db.query(IngestRun)
                         .filter(IngestRun.started_at >= start_time)
                         .count())
        
        # Top users by message count
        top_users = (self.db.query(Message.sender_id, func.count(Message.id))
                    .filter(Message.creation_timestamp >= start_ms)
                    .filter(Message.creation_timestamp <= end_ms)
                    .group_by(Message.sender_id)
                    .order_by(desc(func.count(Message.id)))
                    .limit(10)
                    .all())
        
        # Top conversations by message count
        top_conversations = (self.db.query(Message.conversation_id, func.count(Message.id))
                           .filter(Message.creation_timestamp >= start_ms)
                           .filter(Message.creation_timestamp <= end_ms)
                           .group_by(Message.conversation_id)
                           .order_by(desc(func.count(Message.id)))
                           .limit(10)
                           .all())
        
        return {
            "period_days": days,
            "start_date": start_time.isoformat(),
            "end_date": end_time.isoformat(),
            "activity": {
                "messages": messages_in_period,
                "media_files": media_in_period,
                "ingest_runs": runs_in_period,
                "avg_messages_per_day": round(messages_in_period / days, 2),
                "avg_media_per_day": round(media_in_period / days, 2)
            },
            "top_users": [
                {"user_id": user_id, "message_count": count}
                for user_id, count in top_users
            ],
            "top_conversations": [
                {"conversation_id": conv_id, "message_count": count}
                for conv_id, count in top_conversations
            ]
        }

    def get_parsing_stats(self) -> Dict[str, Any]:
        """Get statistics about parsing success rates"""
        # Overall parsing success
        total_messages = self.db.query(Message).count()
        successful_messages = self.db.query(Message).filter(Message.parsing_successful == True).count()
        failed_messages = total_messages - successful_messages
        
        success_rate = (successful_messages / total_messages * 100) if total_messages > 0 else 0
        
        # Content type breakdown
        content_type_stats = {}
        for content_type in [0, 1, 2, 4]:  # media, text, mixed, audio
            count = self.db.query(Message).filter(Message.content_type == content_type).count()
            successful = (self.db.query(Message)
                         .filter(Message.content_type == content_type)
                         .filter(Message.parsing_successful == True)
                         .count())
            
            content_type_names = {0: "media", 1: "text", 2: "mixed", 4: "audio"}
            content_type_name = content_type_names.get(content_type, f"type_{content_type}")
            content_type_stats[content_type_name] = {
                "total": count,
                "successful": successful,
                "failed": count - successful,
                "success_rate": (successful / count * 100) if count > 0 else 0
            }
        
        # Recent parsing errors
        recent_failed = (self.db.query(Message)
                        .filter(Message.parsing_successful == False)
                        .order_by(desc(Message.id))
                        .limit(10)
                        .all())
        
        # Ingest run parsing stats
        ingest_runs = (self.db.query(IngestRun)
                      .order_by(desc(IngestRun.started_at))
                      .limit(10)
                      .all())
        
        return {
            "overall": {
                "total_messages": total_messages,
                "successful_messages": successful_messages,
                "failed_messages": failed_messages,
                "success_rate": round(success_rate, 2)
            },
            "content_types": content_type_stats,
            "recent_failures": [
                {
                    "id": msg.id,
                    "conversation_id": msg.conversation_id,
                    "content_type": msg.content_type,
                    "creation_timestamp": datetime.fromtimestamp(msg.creation_timestamp / 1000, tz=timezone.utc).isoformat()
                }
                for msg in recent_failed
            ],
            "ingest_run_stats": [
                {
                    "id": run.id,
                    "messages_extracted": run.messages_extracted or 0,
                    "parsing_errors": run.parsing_errors or 0,
                    "success_rate": round(
                        ((run.messages_extracted or 0) - (run.parsing_errors or 0)) / 
                        max(run.messages_extracted or 1, 1) * 100, 2
                    ) if run.messages_extracted else 0,
                    "started_at": run.started_at
                }
                for run in ingest_runs
            ]
        }

    def get_storage_stats(self) -> Dict[str, Any]:
        """Get storage and system statistics"""
        # Database size
        db_info = self.get_database_info()
        
        # File system usage for media files
        total_media_size = (self.db.query(func.sum(MediaAsset.file_size))
                           .scalar()) or 0
        
        # Media type breakdown
        media_type_stats = {}
        for file_type in ['image', 'video', 'audio']:
            count = self.db.query(MediaAsset).filter(MediaAsset.file_type == file_type).count()
            size = (self.db.query(func.sum(MediaAsset.file_size))
                   .filter(MediaAsset.file_type == file_type)
                   .scalar()) or 0
            
            media_type_stats[file_type] = {
                "count": count,
                "total_size": size,
                "avg_size": round(size / count, 2) if count > 0 else 0
            }
        
        # Recent media files
        recent_media = (self.db.query(MediaAsset)
                       .order_by(desc(MediaAsset.file_timestamp))
                       .limit(10)
                       .all())
        
        return {
            "database": db_info,
            "media_storage": {
                "total_media_files": self.db.query(MediaAsset).count(),
                "total_media_size": total_media_size,
                "avg_file_size": round(total_media_size / max(self.db.query(MediaAsset).count(), 1), 2),
                "media_types": media_type_stats
            },
            "recent_media": [
                {
                    "id": media.id,
                    "original_filename": media.original_filename,
                    "file_type": media.file_type,
                    "file_size": media.file_size,
                    "file_timestamp": media.file_timestamp
                }
                for media in recent_media
            ]
        }
    
    def fix_missing_media_links(self) -> Dict[str, int]:
        """
        Fix messages that have cache_ids matching media assets but missing media_asset_id links.
        Returns statistics about the fixing process.
        """
        try:
            # Find messages with cache_ids but no media_asset_id
            messages_missing_media = self.db.query(Message).filter(
                Message.cache_id.isnot(None),
                Message.cache_id != "",
                Message.media_asset_id.is_(None)
            ).all()
            
            # Find media assets indexed by cache_id
            media_assets = self.db.query(MediaAsset).filter(
                MediaAsset.cache_id.isnot(None),
                MediaAsset.cache_id != ""
            ).all()
            
            media_by_cache_id = {asset.cache_id: asset for asset in media_assets}
            
            # Link messages to media assets by matching cache_id
            linked_count = 0
            for message in messages_missing_media:
                if message.cache_id in media_by_cache_id:
                    message.media_asset_id = media_by_cache_id[message.cache_id].id
                    linked_count += 1
                    logger.info(f"Linked message {message.id} (cache_id: {message.cache_id}) to media_asset {message.media_asset_id}")
            
            if linked_count > 0:
                self.db.commit()
                logger.info(f"Successfully linked {linked_count} messages to media assets")
            
            return {
                "messages_checked": len(messages_missing_media),
                "media_assets_available": len(media_assets),
                "links_created": linked_count,
                "messages_still_missing_media": len(messages_missing_media) - linked_count
            }
            
        except Exception as e:
            logger.error(f"Error fixing missing media links: {e}")
            self.db.rollback()
            raise

    def reparse_broken_text_messages(self) -> Dict[str, Any]:
        """
        Reparse messages that have raw_message_content but missing text field.
        This fixes messages that were broken by previous imports that overwrote text with None.
        """
        try:
            from ..parsers._protobuf_parser import ProtobufParser

            # Find messages with content_type=1 (text) or 2 (mixed) that have no text
            broken_messages = self.db.query(Message).filter(
                or_(Message.content_type == 1, Message.content_type == 2),
                or_(Message.text.is_(None), Message.text == ''),
                Message.raw_message_content.isnot(None),
                Message.raw_message_content != ''
            ).all()

            logger.info(f"Found {len(broken_messages)} potentially broken text messages")

            stats = {
                "messages_checked": len(broken_messages),
                "messages_repaired": 0,
                "messages_still_broken": 0,
                "errors": []
            }

            parser = ProtobufParser()

            for message in broken_messages:
                try:
                    # Convert hex string back to bytes
                    raw_bytes = bytes.fromhex(message.raw_message_content)

                    # Re-parse the protobuf
                    text_message, cache_id, parsed_success = parser.parse_message(raw_bytes, message.content_type)

                    # Apply emoji encoding if we got text
                    if text_message:
                        text_message = parser.encode_chat_message(text_message)

                        # Update the message
                        message.text = text_message
                        message.parsing_successful = parsed_success
                        if cache_id and not message.cache_id:
                            message.cache_id = cache_id
                        message.updated_at = datetime.utcnow()

                        stats["messages_repaired"] += 1
                        logger.info(f"Repaired message {message.id}: restored text = '{text_message[:50]}...'")
                    else:
                        stats["messages_still_broken"] += 1
                        logger.warning(f"Could not repair message {message.id}: no text extracted from protobuf")

                except Exception as e:
                    error_msg = f"Error reparsing message {message.id}: {e}"
                    logger.error(error_msg)
                    stats["errors"].append(error_msg)
                    stats["messages_still_broken"] += 1

            # Commit all changes
            if stats["messages_repaired"] > 0:
                self.db.commit()
                logger.info(f"Successfully repaired {stats['messages_repaired']} broken text messages")
            else:
                logger.info("No messages were repaired")

            return stats

        except Exception as e:
            error_msg = f"Error in reparse_broken_text_messages: {e}"
            logger.error(error_msg)
            self.db.rollback()
            return {
                "messages_checked": 0,
                "messages_repaired": 0,
                "messages_still_broken": 0,
                "errors": [error_msg]
            }

    def cleanup_duplicate_messages(self) -> Dict[str, Any]:
        """
        Clean up existing duplicate messages based on conversation_id + creation_timestamp.
        Merges data from duplicates into the earliest message (lowest ID) and removes the rest.
        """
        try:
            # Find duplicates: messages with same conversation_id and creation_timestamp
            duplicate_groups = (
                self.db.query(Message.conversation_id, Message.creation_timestamp, func.count(Message.id))
                .group_by(Message.conversation_id, Message.creation_timestamp)
                .having(func.count(Message.id) > 1)
                .all()
            )
            
            logger.info(f"Found {len(duplicate_groups)} groups of duplicate messages")
            
            stats = {
                "duplicate_groups_found": len(duplicate_groups),
                "messages_merged": 0,
                "messages_removed": 0,
                "errors": []
            }
            
            for conv_id, timestamp, count in duplicate_groups:
                try:
                    # Get all messages in this duplicate group, ordered by ID (earliest first)
                    duplicates = (
                        self.db.query(Message)
                        .filter(Message.conversation_id == conv_id)
                        .filter(Message.creation_timestamp == timestamp)
                        .order_by(Message.id)
                        .all()
                    )
                    
                    if len(duplicates) <= 1:
                        continue
                    
                    # Keep the first message (earliest ID), merge data from others
                    primary_message = duplicates[0]
                    duplicate_messages = duplicates[1:]
                    
                    logger.info(f"Processing {len(duplicates)} duplicates for conversation {conv_id} at timestamp {timestamp}")
                    
                    # Merge data from duplicate messages into the primary message
                    for duplicate in duplicate_messages:
                        # Create a data dict from the duplicate
                        duplicate_data = {
                            'server_message_id': duplicate.server_message_id,
                            'client_message_id': duplicate.client_message_id,
                            'text': duplicate.text,
                            'content_type': duplicate.content_type,
                            'cache_id': duplicate.cache_id,
                            'read_timestamp': duplicate.read_timestamp,
                            'parsing_successful': duplicate.parsing_successful,
                            'raw_message_content': duplicate.raw_message_content,
                            'media_asset_id': duplicate.media_asset_id
                        }
                        
                        # Use our existing merge logic
                        self._update_message_fields(primary_message, duplicate_data)
                    
                    # Update the primary message's updated_at timestamp
                    primary_message.updated_at = datetime.utcnow()
                    
                    # Remove the duplicate messages
                    for duplicate in duplicate_messages:
                        self.db.delete(duplicate)
                        stats["messages_removed"] += 1
                    
                    stats["messages_merged"] += 1
                    
                except Exception as e:
                    error_msg = f"Error processing duplicates for conversation {conv_id} at timestamp {timestamp}: {e}"
                    logger.error(error_msg)
                    stats["errors"].append(error_msg)
            
            # Commit all changes
            self.db.commit()
            logger.info(f"Cleanup completed: {stats}")
            return stats
            
        except Exception as e:
            error_msg = f"Error in cleanup_duplicate_messages: {e}"
            logger.error(error_msg)
            self.db.rollback()
            return {
                "duplicate_groups_found": 0,
                "messages_merged": 0,
                "messages_removed": 0,
                "errors": [error_msg]
            }


# Factory function for dependency injection
def get_storage_service(db: Session = None) -> StorageService:
    """Get storage service instance"""
    if db is None:
        db = next(get_db())
    return StorageService(db)
"""
Centralized ingestion service for Snapchat data extraction.

This service consolidates the core ingestion logic that was previously
duplicated between the manual API endpoint and the automated ingestion loop.
It handles the complete workflow: SSH extraction -> parsing -> storage.
"""

import asyncio
import logging
import os
import shutil
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional

from sqlalchemy.orm import Session

from ..config import get_settings
from ..parsers.snapchat_unified import SnapchatUnifiedParser
from ..services.ssh_pull import SSHPullService
from ..services.storage import StorageService
from .data_processor import DataProcessorService

logger = logging.getLogger(__name__)


class IngestionService:
    """
    Centralized service for handling Snapchat data ingestion.
    
    This service provides a single, consistent implementation of the ingestion
    workflow that can be used by both manual API requests and automated loops.
    """
    
    def __init__(self, db_session: Session):
        self.db_session = db_session
        self.storage_service = StorageService(db_session)
        
    async def run_ingestion(self, run_id: int, config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute the complete ingestion workflow for a specific run.
        
        Args:
            run_id: The ID of the IngestRun record to update
            config: Configuration containing SSH settings and extraction options
            
        Returns:
            Dictionary with ingestion results including counts and any errors
            
        Raises:
            Exception: If any critical step fails
        """
        logger.info(f"🚀 Starting ingestion process for run_id {run_id}")
        logger.info(f"📋 Config: ssh_host={config.get('ssh_host')}, extract_media={config.get('extract_media', True)}")
        
        try:
            # Update status to running
            logger.info(f"📊 Updating run {run_id} status to 'running'")
            self.storage_service.update_ingest_run(run_id, status="running")
            self.db_session.commit()
            
            # Create SSH service
            logger.info(f"🔌 Creating SSH service for {config.get('ssh_user', 'root')}@{config['ssh_host']}:{config.get('ssh_port', 22)}")
            ssh_service = SSHPullService(
                ssh_host=config['ssh_host'],
                ssh_port=config.get('ssh_port', 22),
                ssh_user=config.get('ssh_user', 'root'),
                ssh_key_path=config.get('ssh_key_path'),
                timeout=config.get('timeout', 300)
            )
            
            # Create temporary directory for extraction
            with tempfile.TemporaryDirectory() as temp_dir:
                extract_dir = os.path.join(temp_dir, "extraction")
                os.makedirs(extract_dir, exist_ok=True)
                logger.info(f"📁 Created extraction directory: {extract_dir}")
                
                # Step 1: Extract databases
                logger.info(f"📥 Starting database extraction...")
                db_result = await ssh_service.extract_databases(extract_dir)
                logger.info(f"📥 Database extraction result: {db_result}")
                if not db_result.get('success', False):
                    error_msg = db_result.get('error', 'Database extraction failed')
                    raise Exception(f"Database extraction failed: {error_msg}")
                
                # Step 2: Initialize parser and get timestamp for tracking (no skip logic)
                # Full transfer every run as configured
                logger.info(f"🔄 Running full transfer (change detection disabled)...")
                parser = SnapchatUnifiedParser(extract_dir)
                current_timestamp = parser.get_latest_source_timestamp()
                last_timestamp = self.storage_service.get_last_source_timestamp()
                
                logger.info(f"📊 Timestamp tracking: latest={current_timestamp}, previous={last_timestamp}")
                logger.info(f"🔄 Proceeding with full processing (forced every cycle)")
                
                # Step 2.1: Now load friends data (only if we're doing full processing)
                logger.info(f"👥 Loading friends data...")
                parser.load_friends_data()
                
                # Step 2.2: Extract messages (only if we're doing full processing)
                logger.info(f"📨 Extracting messages...")
                messages = parser.extract_messages()
                
                # Step 3: Extract media with optimization if requested
                media_result = {'success': True}
                extract_media = config.get('extract_media', True)
                if extract_media:
                    # Get cache IDs that are referenced by messages
                    message_cache_ids = [msg.get('cache_id') for msg in messages if msg.get('cache_id')]
                    logger.info(f"🎯 Found {len(message_cache_ids)} cache IDs in messages")
                    
                    # Get existing media filenames to avoid re-downloading
                    existing_media_files = self.storage_service.get_existing_media_filenames()
                    logger.info(f"📁 Found {len(existing_media_files)} existing media files in database")
                    if existing_media_files:
                        sample_existing = list(existing_media_files)[:5]
                        logger.info(f"📁 Sample existing filenames: {sample_existing}")
                    
                    logger.info(f"🖼️ Starting optimized media extraction...")
                    media_result = await ssh_service.extract_media_optimized(
                        output_dir=extract_dir,
                        message_cache_ids=message_cache_ids,
                        existing_media_filenames=existing_media_files
                    )
                    
                    if not media_result.get('success', False):
                        # Log warning but continue without media
                        logger.warning(f"⚠️ Warning: Optimized media extraction failed: {media_result.get('error', 'Unknown error')}")
                        logger.info(f"🔄 Falling back to legacy media extraction...")
                        media_result = await ssh_service.extract_media(extract_dir)
                        if not media_result.get('success', False):
                            logger.warning(f"⚠️ Warning: Legacy media extraction also failed: {media_result.get('error', 'Unknown error')}")
                    else:
                        transferred_files = media_result.get('transferred_files', [])
                        cache_files = media_result.get('cache_files', [])
                        logger.info(f"✅ Optimized extraction: {len(transferred_files)} new media files + {len(cache_files)} cache files")
                
                # Step 4: Complete parsing by extracting conversations and linking media
                # REUSE the already-loaded friends data and extracted messages (no re-parsing!)
                logger.info(f"🔗 Linking media to messages (reusing pre-extracted data)...")
                
                # Extract conversations (this is lightweight compared to message extraction)
                parser.extract_conversations()
                conversations = parser.get_all_conversations()
                valid_conversations = [c for c in conversations if c.get('is_group_chat') or c.get('participants')]
                logger.info(f"📞 Found {len(conversations)} total conversations ({len(valid_conversations)} with valid metadata)")
                
                # Scan for media files and link to messages
                parser.scan_media_files()
                unified_messages = parser.link_media_to_messages()
                
                # Log unified parsing summary
                text_messages = sum(1 for m in unified_messages if m.get('text'))
                media_messages_count = sum(1 for m in unified_messages if m.get('media_asset'))
                logger.info(f"=== Unified Parsing Summary ===")
                logger.info(f"Total unified messages: {len(unified_messages)}")
                logger.info(f"Text messages: {text_messages}")
                logger.info(f"Media messages: {media_messages_count}")
                
                # Extract media assets from unified results
                media_assets = []
                for unified_msg in unified_messages:
                    if unified_msg.get('media_asset'):
                        media_assets.append(unified_msg['media_asset'])
                
                # Use unified_messages as our messages list for processing
                messages = unified_messages
                
                logger.info(f"📊 Processing results: {len(messages)} messages, {len(media_assets)} media assets")
                
                # Step 5: Copy media files to permanent storage BEFORE processing
                if media_assets and extract_media:
                    logger.info(f"📂 Copying {len(media_assets)} media files to permanent storage...")
                    media_assets = self._copy_media_to_permanent_storage(extract_dir, media_assets, run_id)
                    logger.info(f"📂 Successfully prepared {len(media_assets)} media files for storage")
                    
                    # Step 5.5: Update media asset file paths in messages after copying
                    self._update_message_media_paths(messages, media_assets)
                
                # Step 6: Process and store results
                processor = DataProcessorService(self.db_session)
                processor_results = processor.process_parser_results(messages, media_assets, run_id)
                logger.info(f"📊 Processor results: {processor_results}")
                
                # Step 6.5: Process and store conversation data (only if we have valid data)
                if valid_conversations:
                    conversation_results = self._process_conversations(valid_conversations)
                    logger.info(f"📞 Conversation processing results: {conversation_results}")
                else:
                    logger.info("📞 No valid conversation metadata found - skipping conversation processing")

                # Step 6.6: Populate DM names for individual conversations (always run after processing messages)
                logger.info("📞 Populating DM names for individual conversations...")
                # Create a conversation parser instance for DM population
                from ..parsers._conversation_parser import ConversationParser
                conversation_parser = ConversationParser(Path(extract_dir))
                dm_results = conversation_parser.populate_dm_names(self.storage_service)
                logger.info(f"📞 DM name population results: {dm_results}")
                
                # Step 7: Post-ingestion linking cleanup
                logger.info("🔗 Running post-ingestion message-media linking cleanup...")
                linking_results = self._link_orphaned_messages_and_media()
                logger.info(f"🔗 Post-ingestion linking results: {linking_results}")
                
                # Step 8: Update final run status
                self.storage_service.update_ingest_run(
                    run_id,
                    status="completed",
                    messages_extracted=processor_results["messages_processed"],
                    media_files_extracted=processor_results["media_assets_processed"],
                    parsing_errors=len(processor_results.get("errors", [])),
                    error_details=processor_results.get("errors", []),
                    extraction_settings={'source_latest_timestamp': current_timestamp}
                )
                
            self.db_session.commit()
            
            # Return success results
            return {
                "success": True,
                "messages_processed": processor_results["messages_processed"],
                "media_assets_processed": processor_results["media_assets_processed"],
                "errors": processor_results.get("errors", [])
            }
            
        except Exception as e:
            logger.error(f"Ingestion run {run_id} failed: {e}")
            # Update run status to failed
            self.storage_service.update_ingest_run(
                run_id,
                status="failed",
                error_message=str(e),
                error_details={"exception": str(e)}
            )
            self.db_session.commit()
            raise
    
    def _copy_media_to_permanent_storage(self, temp_dir: str, media_assets: List[Dict], run_id: int) -> List[Dict]:
        """
        Copy media files from temporary directory to permanent storage, avoiding duplicates by filename.
        
        Args:
            temp_dir: Temporary directory containing extracted media files
            media_assets: List of media asset dictionaries with file paths and metadata
            run_id: The ingestion run ID (for logging purposes)
            
        Returns:
            Updated list of media assets with permanent storage paths
        """
        settings = get_settings()
        permanent_dir = Path(settings.media_storage_path)
        permanent_dir.mkdir(parents=True, exist_ok=True)
        
        # Use shared storage instead of run-specific folders to avoid duplicates
        shared_storage_dir = permanent_dir / "shared"
        shared_storage_dir.mkdir(exist_ok=True)
        
        updated_media_assets = []
        
        for media_asset in media_assets:
            temp_file_path = Path(temp_dir) / media_asset['file_path']
            
            if not temp_file_path.exists():
                logger.warning(f"Media file not found in temp directory: {temp_file_path}")
                continue
                
            # Create permanent file path using cache_key or original filename
            cache_key = media_asset.get('cache_key', 'unknown')
            original_filename = media_asset.get('original_filename', 'unknown.file')
            mime_type = media_asset.get('mime_type', 'application/octet-stream')
            
            # Use cache_key as filename if available, otherwise use original filename
            if cache_key and cache_key != 'unknown':
                # Get file extension from original filename, or derive from MIME type
                original_ext = Path(original_filename).suffix
                if original_ext:
                    # Use original extension if it exists
                    permanent_filename = f"{cache_key}{original_ext}"
                else:
                    # Derive extension from detected MIME type
                    ext = self._get_file_extension_from_mime_type(mime_type)
                    permanent_filename = f"{cache_key}{ext}"
                    logger.debug(f"Added extension {ext} based on MIME type {mime_type} for {cache_key}")
            else:
                # Check if original filename has extension, otherwise add one from MIME type
                if Path(original_filename).suffix:
                    permanent_filename = original_filename
                else:
                    ext = self._get_file_extension_from_mime_type(mime_type)
                    name_without_ext = Path(original_filename).stem
                    permanent_filename = f"{name_without_ext}{ext}"
                    logger.debug(f"Added extension {ext} based on MIME type {mime_type} for {original_filename}")
                
            permanent_file_path = shared_storage_dir / permanent_filename
            
            # Check if file already exists in shared storage
            if permanent_file_path.exists():
                logger.debug(f"Media file already exists, reusing: {permanent_file_path}")
                # Update the media asset with existing path
                updated_media_asset = media_asset.copy()
                # Use relative path from the parent of media_storage_path (typically /app)
                app_root = Path(settings.media_storage_path).parent
                updated_media_asset['file_path'] = str(permanent_file_path.relative_to(app_root))
                
                # IMPORTANT: Update original_filename to match the actual stored filename
                # This ensures database consistency with the filesystem
                updated_media_asset['original_filename'] = permanent_filename.split('.')[0]  # Remove extension to match database format
                logger.debug(f"Updated original_filename from '{media_asset.get('original_filename')}' to '{updated_media_asset['original_filename']}' for existing file")
                
                updated_media_assets.append(updated_media_asset)
                continue
            
            try:
                # Copy the file to permanent storage
                shutil.copy2(temp_file_path, permanent_file_path)
                logger.debug(f"Copied new media file: {temp_file_path} -> {permanent_file_path}")
                
                # Update the media asset with permanent path (relative to app root)
                updated_media_asset = media_asset.copy()
                # Use relative path from the parent of the parent of media_storage_path (typically /app)
                app_root = Path(settings.media_storage_path).parent.parent
                updated_media_asset['file_path'] = str(permanent_file_path.relative_to(app_root))
                
                # IMPORTANT: Update original_filename to match the actual stored filename
                # This ensures database consistency with the filesystem
                updated_media_asset['original_filename'] = permanent_filename.split('.')[0]  # Remove extension to match database format
                logger.debug(f"Updated original_filename from '{media_asset.get('original_filename')}' to '{updated_media_asset['original_filename']}' to match stored file")
                
                updated_media_assets.append(updated_media_asset)
                
            except Exception as e:
                logger.error(f"Failed to copy media file {temp_file_path}: {e}")
                continue
        
        logger.info(f"Successfully processed {len(updated_media_assets)} media files (some may have been reused from existing storage)")
        return updated_media_assets
    
    def _update_message_media_paths(self, messages: List[Dict], updated_media_assets: List[Dict]) -> None:
        """
        Update the file paths in media_asset objects nested within messages after copying to permanent storage.
        
        Args:
            messages: List of message objects that may contain media_asset objects
            updated_media_assets: List of media assets with updated file paths from copying
        """
        # Create a mapping from original file paths to updated file paths
        path_mapping = {}
        for updated_asset in updated_media_assets:
            # We need to match by something unique like file_hash or original_filename + file_size
            key = (updated_asset.get('original_filename'), updated_asset.get('file_size'))
            if key != (None, None):
                path_mapping[key] = updated_asset['file_path']
        
        # Create another mapping by cache_key if available
        cache_key_mapping = {}
        for updated_asset in updated_media_assets:
            cache_key = updated_asset.get('cache_key')
            if cache_key:
                cache_key_mapping[cache_key] = updated_asset['file_path']
        
        # Update media asset paths in messages
        updated_count = 0
        for message in messages:
            if message.get('media_asset'):
                media_asset = message['media_asset']
                
                # Try to match by filename + file_size first
                key = (media_asset.get('original_filename'), media_asset.get('file_size'))
                if key in path_mapping:
                    old_path = media_asset.get('file_path')
                    media_asset['file_path'] = path_mapping[key]
                    updated_count += 1
                    logger.debug(f"Updated media path in message: {old_path} -> {media_asset['file_path']}")
                    continue
                
                # Try to match by cache_key as fallback
                cache_key = media_asset.get('cache_key')
                if cache_key and cache_key in cache_key_mapping:
                    old_path = media_asset.get('file_path')
                    media_asset['file_path'] = cache_key_mapping[cache_key]
                    updated_count += 1
                    logger.debug(f"Updated media path in message via cache_key: {old_path} -> {media_asset['file_path']}")
        
        if updated_count > 0:
            logger.info(f"Updated file paths in {updated_count} message media assets")
        else:
            logger.warning("No message media assets were updated - check path mapping logic")
    
    def _get_file_extension_from_mime_type(self, mime_type: str) -> str:
        """Convert MIME type to appropriate file extension"""
        mime_to_ext = {
            'image/jpeg': '.jpg',
            'image/jpg': '.jpg', 
            'image/png': '.png',
            'image/gif': '.gif',
            'image/webp': '.webp',
            'image/bmp': '.bmp',
            'image/tiff': '.tiff',
            'video/mp4': '.mp4',
            'video/quicktime': '.mov',
            'video/x-msvideo': '.avi',
            'video/webm': '.webm',
            'video/mpeg': '.mpeg',
            'video/x-ms-wmv': '.wmv',
            'audio/mpeg': '.mp3',
            'audio/wav': '.wav',
            'audio/ogg': '.ogg',
            'audio/mp4': '.m4a',
        }
        return mime_to_ext.get(mime_type.lower(), '.bin')

    def _process_conversations(self, conversations: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Process and store conversation data including participants for group chats"""
        results = {
            'conversations_processed': 0,
            'group_chats_processed': 0,
            'participants_processed': 0,
            'errors': []
        }
        
        for conversation_data in conversations:
            try:
                # Prepare conversation data for storage
                conversation_record_data = {
                    'id': conversation_data['id'],
                    'is_group_chat': conversation_data['is_group_chat'],
                    'group_name': conversation_data.get('group_name'),
                    'participant_count': conversation_data.get('participant_count')
                }
                
                # Upsert conversation
                conversation_record = self.storage_service.upsert_conversation(conversation_record_data)
                results['conversations_processed'] += 1
                
                # If it's a group chat with participants, process them
                if conversation_data['is_group_chat'] and conversation_data.get('participants'):
                    participants_data = conversation_data['participants']
                    
                    # Only process participants if we have user data in the database
                    valid_participants = []
                    for participant in participants_data:
                        user_id = participant['user_id']
                        # Check if user exists in database before adding participant
                        user = self.storage_service.get_user_by_id(user_id)
                        if user:
                            valid_participants.append(participant)
                        else:
                            logger.debug(f"Skipping participant {user_id} - user not found in database")
                    
                    if valid_participants:
                        # Upsert participants
                        self.storage_service.upsert_conversation_participants(
                            conversation_data['id'], 
                            valid_participants
                        )
                        results['participants_processed'] += len(valid_participants)
                        results['group_chats_processed'] += 1
                        
                        logger.debug(f"Processed group chat '{conversation_record_data.get('group_name', 'Unnamed')}' "
                                   f"with {len(valid_participants)} participants")
                
            except Exception as e:
                error_msg = f"Failed to process conversation {conversation_data.get('id', 'unknown')}: {e}"
                logger.error(error_msg)
                results['errors'].append(error_msg)
        
        return results

    def _link_orphaned_messages_and_media(self) -> Dict[str, Any]:
        """
        Final cleanup step to link any messages and media assets that failed to link during parsing.
        This catches timing issues where both message and media exist but weren't linked.
        
        Returns:
            Dictionary with linking results and statistics
        """
        try:
            from ..models import Message, MediaAsset
            
            results = {
                "orphaned_messages_found": 0,
                "orphaned_media_found": 0,
                "links_created": 0,
                "errors": []
            }
            
            # Find messages with cache_ids that have no linked media asset
            orphaned_messages = self.db_session.query(Message).filter(
                Message.cache_id.isnot(None),
                Message.cache_id != '',
                Message.media_asset_id.is_(None)
            ).all()
            
            results["orphaned_messages_found"] = len(orphaned_messages)
            logger.info(f"Found {len(orphaned_messages)} orphaned messages with cache_ids")
            
            # Find media assets with cache_ids that have no linked message
            orphaned_media = self.db_session.query(MediaAsset).filter(
                MediaAsset.cache_id.isnot(None),
                MediaAsset.cache_id != '',
                MediaAsset.cache_id.notin_(
                    self.db_session.query(Message.cache_id).filter(
                        Message.cache_id.isnot(None),
                        Message.media_asset_id.isnot(None)
                    )
                )
            ).all()
            
            results["orphaned_media_found"] = len(orphaned_media)
            logger.info(f"Found {len(orphaned_media)} orphaned media assets with cache_ids")
            
            # Create a lookup map of cache_id -> media_asset_id for fast linking
            media_lookup = {}
            for media_asset in orphaned_media:
                if media_asset.cache_id:
                    media_lookup[media_asset.cache_id] = media_asset.id
            
            # Link orphaned messages to their corresponding media assets
            links_created = 0
            for message in orphaned_messages:
                if message.cache_id and message.cache_id in media_lookup:
                    try:
                        message.media_asset_id = media_lookup[message.cache_id]
                        links_created += 1
                        logger.debug(f"Linked message {message.id} (cache_id: {message.cache_id}) to media asset {media_lookup[message.cache_id]}")
                    except Exception as e:
                        error_msg = f"Failed to link message {message.id} with cache_id {message.cache_id}: {e}"
                        logger.error(error_msg)
                        results["errors"].append(error_msg)
            
            results["links_created"] = links_created
            
            # Commit the changes
            if links_created > 0:
                self.db_session.commit()
                logger.info(f"✅ Successfully created {links_created} message-media links")
            else:
                logger.info("No new links needed to be created")
            
            return results
            
        except Exception as e:
            error_msg = f"Error in post-ingestion linking: {e}"
            logger.error(error_msg)
            self.db_session.rollback()
            return {
                "orphaned_messages_found": 0,
                "orphaned_media_found": 0,
                "links_created": 0,
                "errors": [error_msg]
            }

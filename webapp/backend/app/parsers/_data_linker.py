"""
Data linking component for Snapchat data.
Handles linking messages to media assets via cache IDs.
"""

import logging
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple

from ..utils.db_utils import WALConsolidator

logger = logging.getLogger(__name__)

class DataLinker:
    """
    Component responsible for linking messages to media assets via cache IDs.
    """
    
    def __init__(self, db_dir: Path):
        self.db_dir = db_dir
    
    def load_cache_mappings(self) -> List[Tuple[str, str]]:
        """Load cache ID to cache key mappings from cache_controller.db (like original extractor)"""
        cache_db_path = self.db_dir / "native_content_manager" / "cache_controller.db"
        
        if not cache_db_path.exists():
            logger.warning(f"Cache controller DB not found at: {cache_db_path}")
            return []
            
        try:
            conn = WALConsolidator.connect_with_wal_support(str(cache_db_path))
            cursor = conn.cursor()
            
            # Load all cache file claims for pattern matching (like original extractor)
            cursor.execute("""
                SELECT CACHE_KEY, EXTERNAL_KEY 
                FROM CACHE_FILE_CLAIM
            """)
            
            cache_file_claims = cursor.fetchall()
            conn.close()
            logger.info(f"Loaded {len(cache_file_claims)} cache file claims from database")
            
            return cache_file_claims
            
        except Exception as e:
            logger.error(f"Error loading cache mappings: {e}")
            return []

    def map_cache_id_to_cache_key(self, cache_id: str, cache_file_claims: List[Tuple[str, str]]) -> Optional[str]:
        """Map cache ID to actual cache key using pattern matching like original extractor"""
        if not cache_id or not cache_file_claims:
            return None
        
        # Find cache key for this cache ID using substring match (like original)
        for cache_key, external_key in cache_file_claims:
            if external_key and cache_id in external_key:
                logger.debug(f"Cache ID {cache_id} -> Cache Key {cache_key} (via external_key: {external_key})")
                return cache_key
        
        logger.debug(f"No cache key found for cache ID: {cache_id}")
        return None

    def link_media_to_messages(self, messages: List[Dict[str, Any]], media_files: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Link media files to messages via cache_id and return unified message objects"""
        unified_messages = []
        
        # Create lookup maps
        media_by_cache_key = {media['cache_key']: media for media in media_files}
        
        # Load cache file claims for pattern matching
        cache_file_claims = self.load_cache_mappings()
        
        # Debug: Log sample cache IDs from messages and media
        message_cache_ids = [msg.get('cache_id') for msg in messages if msg.get('cache_id')]
        media_cache_keys = [media.get('cache_key') for media in media_files]
        
        logger.info(f"Sample message cache IDs (first 5): {message_cache_ids[:5]}")
        logger.info(f"Sample media cache keys (first 5): {media_cache_keys[:5]}")
        logger.info(f"Cache file claims available: {len(cache_file_claims)}")
        
        # Debug: Show sample cache file claims to understand the format
        if cache_file_claims:
            sample_claims = cache_file_claims[:3]
            logger.info(f"Sample cache file claims (cache_key, external_key): {sample_claims}")
            
            # Test pattern matching approach with first few message cache IDs
            found_mappings = 0
            for cache_id in message_cache_ids[:10]:  # Check first 10
                cache_key = self.map_cache_id_to_cache_key(cache_id, cache_file_claims)
                if cache_key:
                    found_mappings += 1
                    logger.info(f"Pattern match: {cache_id} -> {cache_key}")
            logger.info(f"Found {found_mappings} pattern matches out of {len(message_cache_ids[:10])} checked")
        
        linked_count = 0
        for message in messages:
            # Start with message data
            unified_message = message.copy()
            unified_message['media_asset'] = None
            
            # Try to find linked media
            if message.get('cache_id'):
                cache_id = message['cache_id']
                media_asset = None
                
                # Method 1: Direct cache key lookup
                if cache_id in media_by_cache_key:
                    media_asset = media_by_cache_key[cache_id]
                    logger.debug(f"Method 1: Direct match for cache_id {cache_id}")
                
                # Method 2: Use pattern matching to find cache key (like original extractor)
                if not media_asset:
                    cache_key = self.map_cache_id_to_cache_key(cache_id, cache_file_claims)
                    if cache_key and cache_key in media_by_cache_key:
                        media_asset = media_by_cache_key[cache_key]
                        logger.debug(f"Method 2: Pattern matched cache_id {cache_id} to cache_key {cache_key}")
                    elif cache_key:  # Only try filename matching if cache_key is not None
                        # Also check if cache_key matches any filename
                        for media in media_files:
                            if (media.get('original_filename') and 
                                (cache_key in media['original_filename'] or media['original_filename'].startswith(cache_key))):
                                media_asset = media
                                logger.debug(f"Method 2b: Found cache_key {cache_key} in filename {media['original_filename']}")
                                break
                
                # Method 3: Search by partial cache ID match in filenames
                if not media_asset:
                    for media in media_files:
                        if cache_id in media['original_filename'] or cache_id in media['cache_key']:
                            media_asset = media
                            logger.debug(f"Method 3: Partial match for cache_id {cache_id} in filename {media['original_filename']}")
                            break
                
                # Method 4: Check if cache_id is a substring of any cache_key or vice versa
                if not media_asset:
                    for media in media_files:
                        media_cache_key = media.get('cache_key', '')
                        if (cache_id and media_cache_key and 
                            (cache_id.lower() in media_cache_key.lower() or 
                             media_cache_key.lower() in cache_id.lower())):
                            media_asset = media
                            logger.debug(f"Method 4: Substring match between cache_id {cache_id} and cache_key {media_cache_key}")
                            break
                
                if media_asset:
                    # Update sender_id and cache_id in media_asset to match the message
                    media_asset['sender_id'] = message.get('sender_id', 'unknown')
                    media_asset['cache_id'] = cache_id  # Set the actual cache_id from the message
                    unified_message['media_asset'] = media_asset
                    linked_count += 1
                    logger.debug(f"Linked message {message.get('server_message_id')} to media {media_asset['original_filename']} with cache_id {cache_id}")
                else:
                    logger.debug(f"No media found for cache_id: {cache_id}")
            
            unified_messages.append(unified_message)
        
        # Log media linking statistics
        linked_media_count = sum(1 for msg in unified_messages if msg.get('media_asset'))
        total_media_files = len(media_files)
        unlinked_media_count = total_media_files - linked_media_count
        
        logger.info(f"Media linking results:")
        logger.info(f"  Total media files found: {total_media_files}")
        logger.info(f"  Media files linked to messages: {linked_media_count}")
        logger.info(f"  Unlinked media files (not processed): {unlinked_media_count}")
        
        # Note: We only process media files that are linked to existing chat messages.
        # Standalone media files are not processed as they lack proper conversation context.
        
        # Sort by timestamp
        unified_messages.sort(key=lambda x: x.get('creation_timestamp_ms', 0))
        
        logger.info(f"Created {len(unified_messages)} unified messages")
        return unified_messages

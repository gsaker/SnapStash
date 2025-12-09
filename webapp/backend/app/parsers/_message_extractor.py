"""
Message extraction component for Snapchat data.
Handles extracting and parsing messages from the arroyo database.
"""

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Any

from ..utils.db_utils import WALConsolidator
from ._protobuf_parser import ProtobufParser

logger = logging.getLogger(__name__)

class MessageExtractor:
    """
    Component responsible for extracting messages from the arroyo database.
    """
    
    def __init__(self, db_dir: Path, friends_data: Dict[str, Dict[str, str]] = None):
        self.db_dir = db_dir
        self.friends_data = friends_data or {}
        self.protobuf_parser = ProtobufParser()
    
    def get_message_count(self) -> int:
        """Get count of messages without full extraction - fast operation for change detection"""
        arroyo_db_path = self.db_dir / "arroyo.db"
        
        try:
            conn = WALConsolidator.connect_with_wal_support(str(arroyo_db_path))
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM conversation_message")
            count = cursor.fetchone()[0]
            conn.close()
            return count
        except Exception as e:
            logger.error(f"Error counting messages: {e}")
            return -1  # Return -1 to indicate error, forcing full processing
    
    def get_latest_message_timestamp(self) -> int:
        """Get the latest message timestamp - very fast indexed query for change detection"""
        arroyo_db_path = self.db_dir / "arroyo.db"
        
        try:
            conn = WALConsolidator.connect_with_wal_support(str(arroyo_db_path))
            cursor = conn.cursor()
            cursor.execute("SELECT MAX(creation_timestamp) FROM conversation_message")
            result = cursor.fetchone()[0]
            conn.close()
            return result if result is not None else 0
        except Exception as e:
            logger.error(f"Error getting latest message timestamp: {e}")
            return -1  # Return -1 to indicate error, forcing full processing
    
    def extract_messages(self) -> List[Dict[str, Any]]:
        """Extract and parse messages from arroyo.db"""
        arroyo_db_path = self.db_dir / "arroyo.db"
        messages = []
        
        try:
            conn = WALConsolidator.connect_with_wal_support(str(arroyo_db_path))
            
            query = """
                SELECT 
                    client_conversation_id,
                    server_message_id,
                    message_content,
                    creation_timestamp,
                    read_timestamp,
                    content_type,
                    sender_id
                FROM conversation_message
                ORDER BY client_conversation_id, creation_timestamp
            """
            
            cursor = conn.cursor()
            processed_count = 0
            
            logger.info("Processing messages with schema-based parsing...")
            
            for row in cursor.execute(query):
                (client_conv_id, server_msg_id, message_content, 
                 creation_ts, read_ts, content_type, sender_id) = row
                
                processed_count += 1
                
                # Skip if message_content is None or empty
                if message_content is None or len(message_content) == 0:
                    text_message = None
                    cache_id = None
                    parsed_success = False
                else:
                    # Parse protobuf content using schema-based parsing
                    text_message, cache_id, parsed_success = self.protobuf_parser.parse_message(message_content, content_type)
                
                # Apply emoji encoding to text messages
                if text_message:
                    text_message = self.protobuf_parser.encode_chat_message(text_message)
                
                # Get friend info
                friend_info = self.friends_data.get(sender_id, {})
                
                # Convert timestamps to ISO format
                creation_time = None
                read_time = None
                if creation_ts:
                    try:
                        creation_time = datetime.fromtimestamp(creation_ts / 1000, tz=timezone.utc).isoformat()
                    except:
                        pass
                if read_ts:
                    try:
                        read_time = datetime.fromtimestamp(read_ts / 1000, tz=timezone.utc).isoformat()
                    except:
                        pass
                
                message_data = {
                    'conversation_id': client_conv_id,
                    'server_message_id': server_msg_id,
                    'content_type': content_type,
                    'sender_id': sender_id,
                    'username': friend_info.get('username', ''),
                    'display_name': friend_info.get('display_name', ''),
                    'creation_timestamp': creation_time,
                    'creation_timestamp_ms': creation_ts,  # Keep original for sorting
                    'read_timestamp': read_time,
                    'read_timestamp_ms': read_ts,
                    'text': text_message,
                    'cache_id': cache_id,
                    'parsing_successful': parsed_success,
                    'raw_message_content': message_content.hex() if message_content else None
                }
                
                messages.append(message_data)
                
                # Log progress every 100 messages
                if processed_count % 100 == 0:
                    logger.info(f"Processed {processed_count} messages...")
            
            conn.close()
            
            # Calculate success stats
            successfully_parsed = sum(1 for m in messages if m['parsing_successful'])
            text_messages = sum(1 for m in messages if m['text'])
            media_messages = sum(1 for m in messages if m['cache_id'])
            
            logger.info(f"=== Message Extraction Summary ===")
            logger.info(f"Total messages processed: {len(messages)}")
            logger.info(f"Successfully parsed: {successfully_parsed} ({successfully_parsed/len(messages)*100:.1f}%)")
            logger.info(f"Text messages extracted: {text_messages}")
            logger.info(f"Media messages extracted: {media_messages}")
            
        except Exception as e:
            logger.error(f"Error extracting messages: {e}")
        
        return messages

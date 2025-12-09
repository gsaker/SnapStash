"""
Conversation parsing component for Snapchat data.
Handles extracting conversation metadata and participants from arroyo database.
"""

import logging
import os
import sys
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple

# Fix for protobuf compatibility
os.environ['PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION'] = 'python'

# Add root directory to path for conversation_pb2 import
sys.path.append(str(Path(__file__).parent.parent.parent.parent))

try:
    from conversation_pb2 import ConversationMetadata
    PROTOBUF_AVAILABLE = True
except ImportError:
    PROTOBUF_AVAILABLE = False

from ..utils.db_utils import WALConsolidator

logger = logging.getLogger(__name__)

class ConversationParser:
    """
    Component responsible for extracting conversation metadata from arroyo database.
    Identifies group chats and extracts participant information.
    """
    
    def __init__(self, db_dir: Path):
        self.db_dir = db_dir
        if not PROTOBUF_AVAILABLE:
            logger.warning("ConversationMetadata protobuf not available - group chat parsing disabled")
    
    def parse_conversations(self) -> List[Dict[str, Any]]:
        """Parse all conversations and extract metadata"""
        arroyo_db_path = self.db_dir / "arroyo.db"
        conversations = []
        
        if not arroyo_db_path.exists():
            logger.warning(f"Arroyo database not found at {arroyo_db_path}")
            return conversations
        
        try:
            conn = WALConsolidator.connect_with_wal_support(str(arroyo_db_path))
            cursor = conn.cursor()
            
            # Get all conversations with metadata
            query = """
                SELECT 
                    client_conversation_id,
                    conversation_metadata,
                    length(conversation_metadata) as metadata_size
                FROM conversation
                ORDER BY length(conversation_metadata) DESC
            """
            
            logger.info("Processing conversations...")
            
            for row in cursor.execute(query):
                client_conv_id, metadata_blob, metadata_size = row
                
                # Start with assumption it's an individual chat
                conversation_data = {
                    'id': client_conv_id,
                    'is_group_chat': False,
                    'group_name': None,
                    'participant_count': None,
                    'participants': []
                }
                
                # Only try to parse as group chat if we have large metadata AND protobuf parsing is available
                if metadata_size > 100 and PROTOBUF_AVAILABLE and metadata_blob:
                    group_name, participants = self._parse_group_metadata(metadata_blob)
                    
                    # Only mark as group chat if we successfully parsed participants
                    if participants and len(participants) > 2:
                        conversation_data['is_group_chat'] = True
                        conversation_data['group_name'] = group_name
                        conversation_data['participant_count'] = len(participants)
                        conversation_data['participants'] = participants
                    else:
                        logger.debug(f"Conversation {client_conv_id} has large metadata but no valid participants - treating as individual chat")
                
                conversations.append(conversation_data)
            
            conn.close()
            
            # Log summary
            group_chats = [c for c in conversations if c['is_group_chat']]
            individual_chats = [c for c in conversations if not c['is_group_chat']]
            
            logger.info(f"=== Conversation Parsing Summary ===")
            logger.info(f"Total conversations: {len(conversations)}")
            logger.info(f"Group chats: {len(group_chats)}")
            logger.info(f"Individual chats: {len(individual_chats)}")
            
            if group_chats:
                logger.info(f"Group chats with parsed names: {sum(1 for c in group_chats if c['group_name'])}")
                logger.info(f"Total participants parsed: {sum(c['participant_count'] or 0 for c in group_chats)}")
            
        except Exception as e:
            logger.error(f"Error parsing conversations: {e}")
        
        return conversations
    
    def _parse_group_metadata(self, metadata_blob: bytes) -> Tuple[Optional[str], List[Dict[str, Any]]]:
        """Parse protobuf metadata to extract group name and participants"""
        try:
            conversation_metadata = ConversationMetadata()
            conversation_metadata.ParseFromString(metadata_blob)
            
            # Extract group name (may be empty)
            group_name = conversation_metadata.group_name if conversation_metadata.group_name else None
            
            # Extract participants
            participants = []
            for participant in conversation_metadata.participants:
                participant_data = {
                    'user_id': participant.user_id.hex(),  # Convert bytes to hex string
                    'join_timestamp': participant.timestamp,
                    'unknown_field_2': participant.unknown_field_2,
                    'unknown_field_3': participant.unknown_field_3,
                    'unknown_field_9': participant.unknown_field_9
                }
                participants.append(participant_data)
            
            return group_name, participants
            
        except Exception as e:
            logger.warning(f"Failed to parse protobuf metadata: {e}")
            return None, []
    
    def populate_dm_names(self, storage_service) -> Dict[str, Any]:
        """Populate names for individual DM conversations using the storage service"""
        logger.info("Starting DM name population...")
        try:
            return storage_service.populate_individual_dm_names()
        except Exception as e:
            error_msg = f"Error in populate_dm_names: {e}"
            logger.error(error_msg)
            return {
                'conversations_updated': 0,
                'conversations_skipped': 0,
                'errors': [error_msg]
            }
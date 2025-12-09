"""
Protobuf parsing component for Snapchat data.
Handles validation and parsing of protobuf binary data from messages.
"""

import os
import sys
import logging
from pathlib import Path
from typing import Optional, Tuple, Any

# Optional imports - gracefully handle missing dependencies
try:
    import numpy as np
    NUMPY_AVAILABLE = True
except ImportError:
    np = None
    NUMPY_AVAILABLE = False

logger = logging.getLogger(__name__)

class ProtobufParser:
    """
    Component responsible for parsing protobuf binary data from Snapchat messages.
    """
    
    def __init__(self):
        # Import protobuf decoder if available
        self.Snapchat_pb2 = None
        try:
            # Try relative import first (for plugin context)
            from . import Snapchat_pb2
            self.Snapchat_pb2 = Snapchat_pb2
        except ImportError:
            try:
                # Try from original code directory
                sys.path.append('/app/originalcode')
                import Snapchat_pb2
                self.Snapchat_pb2 = Snapchat_pb2
            except ImportError:
                try:
                    # Try alternative path
                    sys.path.append(str(Path(__file__).parent.parent.parent.parent / "originalcode"))
                    import Snapchat_pb2
                    self.Snapchat_pb2 = Snapchat_pb2
                except ImportError:
                    logger.warning("Could not load protobuf decoder - protobuf parsing will be disabled")
                    self.Snapchat_pb2 = None

    def validate_protobuf_data(self, data) -> bool:
        """Validate if the data looks like valid protobuf"""
        if data is None or len(data) == 0:
            return False
        
        if isinstance(data, str):
            try:
                data = data.encode('latin-1')
            except (UnicodeDecodeError, UnicodeEncodeError):
                return False
        
        if not isinstance(data, bytes) or len(data) < 2:
            return False
        
        # Basic protobuf format validation
        try:
            first_byte = data[0] if isinstance(data[0], int) else ord(data[0])
            wire_type = first_byte & 0x07
            return wire_type <= 5
        except (IndexError, TypeError):
            return False

    def parse_schema(self, data, content_type) -> Tuple[Any, Any]:
        """Parse protobuf using schema-based method (primary method)"""
        if not NUMPY_AVAILABLE:
            return f"ERROR - numpy not available for content_type {content_type}", None
            
        try:
            if not self.validate_protobuf_data(data) or not self.Snapchat_pb2:
                return f"INFO - Invalid or empty protobuf data for content_type {content_type}", np.nan
            
            # Ensure data is in bytes format
            if isinstance(data, str):
                try:
                    data = data.encode('latin-1')
                except (UnicodeDecodeError, UnicodeEncodeError):
                    return f"ERROR - Cannot convert string data to bytes for content_type {content_type}", np.nan
            
            # Clear the schema before parsing new data
            schema = self.Snapchat_pb2.root()
            schema.Clear()
            schema.ParseFromString(data)
            
            if content_type == 0:
                # Handle content_type 0: try to get cacheId from startMedia
                return self._extract_cache_id_from_start_media(schema)
                    
            elif content_type == 1:
                # Handle content_type 1: try to get message from chat
                return self._extract_chat_message(schema)
                    
            elif content_type == 2:
                # Handle content_type 2: try to get both cacheId and mediatext
                return self._extract_media_data(schema)
                    
            elif content_type == 4:
                # Handle content_type 4: Audio files - use same cacheId extraction as content_type 0
                return self._extract_audio_cache_id(schema)
            else: 
                return f"ERROR - Unknown content_type: {content_type}", np.nan
                
        except Exception as e:
            logger.debug(f"Schema parsing failed for content_type {content_type}: {str(e)}")
            return "ERROR - Failed to parse protobuf data", np.nan

    def _extract_cache_id_from_start_media(self, schema) -> Tuple[Any, Any]:
        """Extract cache ID from startMedia structure"""
        try:
            if (hasattr(schema, 'Content') and 
                hasattr(schema.Content, 'startMedia') and
                hasattr(schema.Content.startMedia, 'unknown') and
                hasattr(schema.Content.startMedia.unknown, 'unknown') and
                hasattr(schema.Content.startMedia.unknown.unknown, 'unknown') and
                hasattr(schema.Content.startMedia.unknown.unknown.unknown, 'cacheId')):
                return (schema.Content.startMedia.unknown.unknown.unknown.cacheId, np.nan)
            # Alternative path for different structure
            elif (hasattr(schema, 'Content') and 
                  hasattr(schema.Content, 'startMedia') and
                  hasattr(schema.Content.startMedia, 'unknown') and
                  hasattr(schema.Content.startMedia.unknown, 'unknown') and
                  hasattr(schema.Content.startMedia.unknown.unknown, 'cacheId')):
                return (schema.Content.startMedia.unknown.unknown.cacheId, np.nan)
            else:
                return ("INFO - No cacheId found in expected structure", np.nan)
        except Exception as e:
            return (f"ERROR - Failed to extract cacheId: {str(e)}", np.nan)

    def _extract_chat_message(self, schema) -> Tuple[Any, Any]:
        """Extract chat message from chat structure"""
        try:
            if (hasattr(schema, 'Content') and 
                hasattr(schema.Content, 'chat') and
                hasattr(schema.Content.chat, 'chatMessage') and
                hasattr(schema.Content.chat.chatMessage, 'message')):
                message_text = schema.Content.chat.chatMessage.message
                # Clean up the message text (remove null bytes and extra whitespace)
                if message_text:
                    message_text = message_text.replace('\x00', '').strip()
                    if message_text:
                        return (message_text, np.nan)
                return ("INFO - Empty message found in chat structure", np.nan)
            else:
                return ("INFO - No message found in expected chat structure", np.nan)
        except Exception as e:
            return (f"ERROR - Failed to extract chat message: {str(e)}", np.nan)

    def _extract_media_data(self, schema) -> Tuple[Any, Any]:
        """Extract both cache ID and media text from media structure"""
        try:
            cache_id = None
            media_text = None
            
            # Try to get cacheId using same paths as content_type 0
            if (hasattr(schema, 'Content') and 
                hasattr(schema.Content, 'startMedia') and
                hasattr(schema.Content.startMedia, 'unknown') and
                hasattr(schema.Content.startMedia.unknown, 'unknown') and
                hasattr(schema.Content.startMedia.unknown.unknown, 'unknown') and
                hasattr(schema.Content.startMedia.unknown.unknown.unknown, 'cacheId')):
                cache_id = schema.Content.startMedia.unknown.unknown.unknown.cacheId
            elif (hasattr(schema, 'Content') and 
                  hasattr(schema.Content, 'startMedia') and
                  hasattr(schema.Content.startMedia, 'unknown') and
                  hasattr(schema.Content.startMedia.unknown, 'unknown') and
                  hasattr(schema.Content.startMedia.unknown.unknown, 'cacheId')):
                cache_id = schema.Content.startMedia.unknown.unknown.cacheId
            # Additional cache ID path from chat mediatext (from original code)
            elif (hasattr(schema, 'Content') and 
                  hasattr(schema.Content, 'chat') and
                  hasattr(schema.Content.chat, 'mediatext') and
                  hasattr(schema.Content.chat.mediatext, 'mediatext2') and
                  hasattr(schema.Content.chat.mediatext.mediatext2, 'cacheId')):
                cache_id = schema.Content.chat.mediatext.mediatext2.cacheId
            
            # Try to get mediatext
            if (hasattr(schema, 'Content') and 
                hasattr(schema.Content, 'chat') and
                hasattr(schema.Content.chat, 'mediatext') and
                hasattr(schema.Content.chat.mediatext, 'mediatext2') and
                hasattr(schema.Content.chat.mediatext.mediatext2, 'mediatextFinal')):
                media_text = schema.Content.chat.mediatext.mediatext2.mediatextFinal
                if media_text:
                    media_text = media_text.replace('\x00', '').strip()
            
            if cache_id is None and media_text is None:
                return ("INFO - No media data found in expected structure", np.nan)
            
            return (cache_id if cache_id else "No cacheId", media_text if media_text else np.nan)
        except Exception as e:
            return (f"ERROR - Failed to extract media data: {str(e)}", np.nan)

    def _extract_audio_cache_id(self, schema) -> Tuple[Any, Any]:
        """Extract cache ID for audio files"""
        try:
            if (hasattr(schema, 'Content') and 
                hasattr(schema.Content, 'startMedia') and
                hasattr(schema.Content.startMedia, 'unknown') and
                hasattr(schema.Content.startMedia.unknown, 'unknown') and
                hasattr(schema.Content.startMedia.unknown.unknown, 'unknown') and
                hasattr(schema.Content.startMedia.unknown.unknown.unknown, 'cacheId')):
                return (schema.Content.startMedia.unknown.unknown.unknown.cacheId, np.nan)
            # Alternative path for different structure
            elif (hasattr(schema, 'Content') and 
                  hasattr(schema.Content, 'startMedia') and
                  hasattr(schema.Content.startMedia, 'unknown') and
                  hasattr(schema.Content.startMedia.unknown, 'unknown') and
                  hasattr(schema.Content.startMedia.unknown.unknown, 'cacheId')):
                return (schema.Content.startMedia.unknown.unknown.cacheId, np.nan)
            # Additional cache ID path from chat mediatext (for audio with text)
            elif (hasattr(schema, 'Content') and 
                  hasattr(schema.Content, 'chat') and
                  hasattr(schema.Content.chat, 'mediatext') and
                  hasattr(schema.Content.chat.mediatext, 'mediatext2') and
                  hasattr(schema.Content.chat.mediatext.mediatext2, 'cacheId')):
                return (schema.Content.chat.mediatext.mediatext2.cacheId, np.nan)
            else:
                return ("INFO - No cacheId found in expected structure for audio", np.nan)
        except Exception as e:
            return (f"ERROR - Failed to extract audio cacheId: {str(e)}", np.nan)

    def parse_message(self, data, content_type) -> Tuple[Optional[str], Optional[str], bool]:
        """Parse protobuf message using schema-based parsing"""
        if not self.validate_protobuf_data(data) or data is None or len(data) == 0:
            return None, None, False
        
        # Use schema-based parsing
        parsed_message_schema, extra_message_schema = self.parse_schema(data, content_type)
        
        # Check if schema parsing was successful (not an error or info message)
        if not (isinstance(parsed_message_schema, str) and ('ERROR' in parsed_message_schema or 'INFO' in parsed_message_schema)):
            # Schema parsing succeeded
            text_msg = parsed_message_schema if content_type == 1 else (extra_message_schema if content_type == 2 else None)
            cache_id = parsed_message_schema if content_type in [0, 2, 4] else None
            
            return text_msg, cache_id, True
        else:
            # Schema parsing failed - return None values
            return None, None, False

    def encode_chat_message(self, message) -> Optional[str]:
        """Encode chat message to handle emojis and special characters (from original)"""
        if message is None or (NUMPY_AVAILABLE and message is np.nan):
            return None
        
        try:
            if isinstance(message, list) and len(message) >= 1:
                encoded_message = ''
                if len(message) >= 2:
                    for char in message:
                        tmp = char.encode('cp1252', 'xmlcharrefreplace')
                        tmp = tmp.decode('cp1252')
                        encoded_message += tmp
                else:
                    char = message[0].encode('cp1252', 'xmlcharrefreplace')
                    encoded_message = char.decode('cp1252')
                return encoded_message
            elif isinstance(message, str):
                # Handle single string
                encoded_message = message.encode('cp1252', 'xmlcharrefreplace')
                return encoded_message.decode('cp1252')
            else:
                return message
        except Exception as e:
            logger.warning(f"Failed to encode message: {e}")
            return message

    def is_valid_message_text(self, text) -> bool:
        """Validate if text looks like a real message"""
        if not text or not isinstance(text, str):
            return False
        
        text = text.strip()
        
        # Length checks
        if len(text) < 1 or len(text) > 2000:
            return False
        
        # Must be printable
        if not text.isprintable():
            return False
        
        # Reject if mostly non-alphanumeric
        alphanumeric_count = sum(1 for c in text if c.isalnum())
        if len(text) > 3 and alphanumeric_count / len(text) < 0.3:
            return False
        
        # Reject UUIDs
        if len(text) == 36 and text.count('-') == 4:
            return False
        
        # Reject hex-like strings
        if len(text) > 20 and all(c in '0123456789abcdefABCDEF-' for c in text.replace('-', '')):
            return False
        
        return True

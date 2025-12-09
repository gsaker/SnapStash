#!/usr/bin/env python3
"""
Unified Snapchat Parser (Orchestrator)
Orchestrates message extraction and media mapping using focused components.
Emits normalized Message and MediaAsset objects.
"""

import os
import logging
from pathlib import Path
from typing import Dict, List, Any

from ._friends_loader import FriendsLoader
from ._message_extractor import MessageExtractor
from ._media_scanner import MediaScanner
from ._data_linker import DataLinker
from ._conversation_parser import ConversationParser

# Fix for protobuf compatibility
os.environ['PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION'] = 'python'

# Optional imports - gracefully handle missing dependencies
try:
    import pandas as pd
    import filetype
    import numpy as np
    DEPENDENCIES_AVAILABLE = True
except ImportError:
    # Create placeholder variables for missing dependencies
    pd = None
    filetype = None
    np = None
    DEPENDENCIES_AVAILABLE = False

logger = logging.getLogger(__name__)

class SnapchatUnifiedParser:
    """
    Unified parser orchestrator that coordinates focused components.
    Parses Snapchat databases to emit normalized Message and MediaAsset objects.
    """
    
    def __init__(self, data_dir: str):
        if not DEPENDENCIES_AVAILABLE:
            raise ImportError("Required dependencies not available: pandas, filetype, protobuf, numpy")
        
        self.data_dir = Path(data_dir)
        
        # Check if databases are in snapchat subdirectory (from SSH extraction)
        snapchat_db_dir = self.data_dir / "com.snapchat.android" / "databases"
        snapchat_app_dir = self.data_dir / "com.snapchat.android"
        if snapchat_db_dir.exists():
            self.db_dir = snapchat_db_dir
            self.media_base_dir = snapchat_app_dir  # Use snapchat app dir for media scanning
            logger.info(f"Using Snapchat database directory: {self.db_dir}")
            logger.info(f"Using Snapchat media base directory: {self.media_base_dir}")
        else:
            self.db_dir = self.data_dir
            self.media_base_dir = self.data_dir  # Use root dir for media scanning
            logger.info(f"Using root database directory: {self.db_dir}")
            logger.info(f"Using root media base directory: {self.media_base_dir}")
        
        # Initialize components
        self.friends_loader = FriendsLoader(self.db_dir)
        self.media_scanner = MediaScanner(self.media_base_dir)
        self.data_linker = DataLinker(self.db_dir)
        self.conversation_parser = ConversationParser(self.db_dir)
        
        # State tracking
        self.friends_data = {}
        self.extracted_messages = []
        self.extracted_media = []
        self.extracted_conversations = []

    def load_friends_data(self) -> Dict[str, Dict[str, str]]:
        """Extract friends/user data from main.db using FriendsLoader component"""
        self.friends_data = self.friends_loader.load_friends_data()
        return self.friends_data

    def get_source_message_count(self) -> int:
        """Get count of messages without full extraction - fast operation for change detection"""
        message_extractor = MessageExtractor(self.db_dir)
        return message_extractor.get_message_count()

    def get_latest_source_timestamp(self) -> int:
        """Get the latest message timestamp - very fast indexed query for change detection"""
        message_extractor = MessageExtractor(self.db_dir)
        return message_extractor.get_latest_message_timestamp()

    def extract_messages(self) -> List[Dict[str, Any]]:
        """Extract and parse messages from arroyo.db using MessageExtractor component"""
        message_extractor = MessageExtractor(self.db_dir, self.friends_data)
        self.extracted_messages = message_extractor.extract_messages()
        return self.extracted_messages

    def scan_media_files(self) -> List[Dict[str, Any]]:
        """Scan for media files using MediaScanner component"""
        self.extracted_media = self.media_scanner.scan_media_files(self.data_dir)
        return self.extracted_media

    def extract_conversations(self) -> List[Dict[str, Any]]:
        """Extract and parse conversation metadata using ConversationParser component"""
        self.extracted_conversations = self.conversation_parser.parse_conversations()
        return self.extracted_conversations

    def link_media_to_messages(self) -> List[Dict[str, Any]]:
        """Link media files to messages using DataLinker component"""
        return self.data_linker.link_media_to_messages(self.extracted_messages, self.extracted_media)

    def parse(self) -> List[Dict[str, Any]]:
        """
        Main orchestration method that coordinates all components to parse Snapchat data
        """
        logger.info("Starting unified Snapchat parsing...")
        
        # Load friends data first
        self.load_friends_data()
        
        # Extract conversations and group chat metadata
        self.extract_conversations()
        
        # Extract messages from arroyo.db
        self.extract_messages()
        
        # Scan for media files
        self.scan_media_files()
        
        # Link media to messages and create unified objects
        unified_messages = self.link_media_to_messages()
        
        # Log summary
        text_messages = sum(1 for m in unified_messages if m.get('text'))
        media_messages = sum(1 for m in unified_messages if m.get('media_asset'))
        linked_messages = sum(1 for m in unified_messages if m.get('text') and m.get('media_asset'))
        
        logger.info(f"=== Unified Parsing Summary ===")
        logger.info(f"Total unified messages: {len(unified_messages)}")
        logger.info(f"Text messages: {text_messages}")
        logger.info(f"Media messages: {media_messages}")
        logger.info(f"Messages with both text and media: {linked_messages}")
        
        return unified_messages

    def get_all_media_assets(self) -> List[Dict[str, Any]]:
        """Get all media assets (both linked and unlinked)"""
        return self.extracted_media.copy()

    def get_all_conversations(self) -> List[Dict[str, Any]]:
        """Get all conversation metadata including group chat information"""
        # Extract conversations if not already done
        if not self.extracted_conversations:
            self.extract_conversations()
        return self.extracted_conversations.copy()


def parse_snapchat_data(data_dir: str) -> List[Dict[str, Any]]:
    """
    Convenience function to parse Snapchat data from a directory
    
    Args:
        data_dir: Path to directory containing Snapchat database files
        
    Returns:
        List of unified message objects with optional media assets
    """
    parser = SnapchatUnifiedParser(data_dir)
    return parser.parse()

"""
Friends data loading component for Snapchat data.
Handles loading user and friends data from the main database.
"""

import logging
from pathlib import Path
from typing import Dict

from ..utils.db_utils import WALConsolidator

logger = logging.getLogger(__name__)

class FriendsLoader:
    """
    Component responsible for loading friends and user data from the main database.
    """
    
    def __init__(self, db_dir: Path):
        self.db_dir = db_dir
    
    def load_friends_data(self) -> Dict[str, Dict[str, str]]:
        """Extract friends/user data from main.db"""
        main_db_path = self.db_dir / "main.db"
        friends = {}
        
        try:
            conn = WALConsolidator.connect_with_wal_support(str(main_db_path))
            cursor = conn.cursor()
            
            query = """
                SELECT userId, username, displayName, bitmojiAvatarId, bitmojiSelfieId
                FROM Friend
            """

            for row in cursor.execute(query):
                user_id, username, display_name, bitmoji_avatar_id, bitmoji_selfie_id = row

                # Apply emoji encoding to display name (same as original)
                encoded_display_name = ''
                if display_name:
                    try:
                        for char in display_name:
                            tmp = char.encode('cp1252', 'xmlcharrefreplace')
                            tmp = tmp.decode('cp1252')
                            encoded_display_name += tmp
                    except:
                        encoded_display_name = display_name or ''

                friends[user_id] = {
                    'username': username or '',
                    'display_name': encoded_display_name,
                    'bitmoji_avatar_id': bitmoji_avatar_id or '',
                    'bitmoji_selfie_id': bitmoji_selfie_id or ''
                }
            
            conn.close()
            logger.info(f"Loaded {len(friends)} friends from database")
            
        except Exception as e:
            logger.warning(f"Failed to load friends data: {e}")
            # Try alternative query in case table structure is different
            try:
                conn = WALConsolidator.connect_with_wal_support(str(main_db_path))
                cursor = conn.cursor()
                
                # Check what tables exist
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
                tables = [row[0] for row in cursor.fetchall()]
                logger.info(f"Available tables in main.db: {tables}")
                
                if 'Friend' in tables:
                    # Check columns in Friend table
                    cursor.execute("PRAGMA table_info(Friend);")
                    columns = [row[1] for row in cursor.fetchall()]
                    logger.info(f"Columns in Friend table: {columns}")
                
                conn.close()
            except Exception as e2:
                logger.warning(f"Failed to diagnose database structure: {e2}")
        
        return friends

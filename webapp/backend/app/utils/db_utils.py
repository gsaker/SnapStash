"""
Database utilities for SQLite WAL file handling and other database operations
"""

import os
import sqlite3
import logging

logger = logging.getLogger(__name__)


class WALConsolidator:
    """Utility for consolidating SQLite WAL files"""
    
    @staticmethod
    def consolidate_wal_database(db_path: str) -> bool:
        """Consolidate WAL database files into main database"""
        try:
            wal_file = db_path + '-wal'
            shm_file = db_path + '-shm'
            
            # Check if only WAL and SHM files exist (no main database file)
            if not os.path.exists(db_path) and (os.path.exists(wal_file) or os.path.exists(shm_file)):
                logger.warning(f"Main database file {db_path} missing but WAL/SHM files exist")
                
                # Create empty main database first
                try:
                    conn = sqlite3.connect(db_path)
                    conn.execute("PRAGMA journal_mode=WAL;")  # Enable WAL mode first
                    conn.close()
                    logger.info(f"Created placeholder main database: {db_path}")
                except Exception as e:
                    logger.error(f"Failed to create placeholder database: {e}")
                    return False
            
            # Connect and force WAL consolidation
            conn = sqlite3.connect(db_path)
            
            # First enable WAL mode to ensure proper handling of WAL files
            conn.execute("PRAGMA journal_mode=WAL;")
            
            # Force checkpoint to consolidate all WAL data into main database
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE);")  # Use TRUNCATE for better reliability
            
            # Now switch to DELETE mode to disable WAL
            conn.execute("PRAGMA journal_mode=DELETE;")
            
            conn.close()
            
            # Delete WAL and SHM files if they exist after consolidation
            for file_path in [wal_file, shm_file]:
                if os.path.exists(file_path):
                    try:
                        os.remove(file_path)
                        logger.info(f"Removed {file_path}")
                    except Exception as e:
                        logger.warning(f"Failed to remove {file_path}: {e}")
            
            logger.info(f"Consolidated WAL database: {db_path}")
            return True
            
        except Exception as e:
            logger.warning(f"Failed to consolidate WAL database {db_path}: {e}")
            return False
    
    @staticmethod
    def connect_with_wal_support(db_path: str):
        """Connect to a database with robust WAL file handling"""
        wal_file = str(db_path) + '-wal'
        shm_file = str(db_path) + '-shm'
        
        # If main database doesn't exist but WAL/SHM files do, consolidate first
        if not os.path.exists(db_path) and (os.path.exists(wal_file) or os.path.exists(shm_file)):
            logger.info(f"Main database missing, attempting to consolidate WAL files for: {db_path}")
            success = WALConsolidator.consolidate_wal_database(str(db_path))
            if not success:
                raise Exception(f"Failed to consolidate WAL files for {db_path}")
        
        # If WAL files exist alongside main database, consolidate to ensure we get all data
        elif os.path.exists(db_path) and (os.path.exists(wal_file) or os.path.exists(shm_file)):
            logger.info(f"WAL files detected, consolidating to ensure complete data: {db_path}")
            WALConsolidator.consolidate_wal_database(str(db_path))
        
        # Connect to the consolidated database
        conn = sqlite3.connect(str(db_path))
        conn.execute("PRAGMA journal_mode=DELETE;")  # Ensure WAL mode is disabled for consistency
        return conn
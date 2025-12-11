"""
Local Database Extractor Service

Handles extraction of Snapchat data from pre-extracted databases
that are mounted locally instead of using SSH to extract from a live device.
"""

import os
import shutil
import logging
from pathlib import Path
from typing import Optional

from ..config import get_settings

logger = logging.getLogger(__name__)


class LocalExtractor:
    """
    Extracts Snapchat data from locally mounted pre-extracted databases.

    Expected directory structure for extracted DBs:
    /path/to/extracted/dbs/
        main.db              - Friends/user data
        arroyo.db            - Messages data
        cache_controller.db  - Cache mappings
        (optional) media/    - Extracted media files
    """

    REQUIRED_DBS = ["arroyo.db", "main.db"]
    OPTIONAL_DBS = ["cache_controller.db"]

    def __init__(self, extracted_dbs_path: Optional[str] = None):
        """
        Initialize the local extractor.

        Args:
            extracted_dbs_path: Path to directory containing extracted databases.
                               Falls back to config if not provided.
        """
        settings = get_settings()
        self.source_path = Path(extracted_dbs_path or settings.extracted_dbs_path or "")

        if not self.source_path or not self.source_path.exists():
            logger.warning(f"Extracted DBs path not set or doesn't exist: {self.source_path}")

    def validate_source_databases(self) -> tuple[bool, list[str]]:
        """
        Validate that required source databases exist.

        Returns:
            Tuple of (is_valid, list_of_missing_files)
        """
        if not self.source_path or not self.source_path.exists():
            return False, ["Source path does not exist"]

        missing = []
        for db_name in self.REQUIRED_DBS:
            db_path = self.source_path / db_name
            if not db_path.exists():
                missing.append(db_name)

        return len(missing) == 0, missing

    def copy_databases_to_data_dir(self, data_dir: str) -> dict:
        """
        Copy extracted databases to the data directory for parsing.

        This mimics the structure created by SSH extraction so the
        existing SnapchatUnifiedParser can process the data.

        Args:
            data_dir: Target data directory (e.g., /app/data)

        Returns:
            Dictionary with copy results and statistics
        """
        results = {
            "success": False,
            "databases_copied": [],
            "media_copied": False,
            "errors": [],
            "target_path": None
        }

        # Validate source databases exist
        is_valid, missing = self.validate_source_databases()
        if not is_valid:
            results["errors"].append(f"Missing required databases: {', '.join(missing)}")
            return results

        # Create target directory structure matching SSH extraction
        # The parser expects: data_dir/com.snapchat.android/databases/
        target_db_dir = Path(data_dir) / "com.snapchat.android" / "databases"
        target_db_dir.mkdir(parents=True, exist_ok=True)
        results["target_path"] = str(target_db_dir)

        # Copy required and optional databases
        all_dbs = self.REQUIRED_DBS + self.OPTIONAL_DBS
        for db_name in all_dbs:
            source_db = self.source_path / db_name
            target_db = target_db_dir / db_name

            if source_db.exists():
                try:
                    # Also copy WAL and SHM files if they exist
                    shutil.copy2(source_db, target_db)
                    results["databases_copied"].append(db_name)
                    logger.info(f"Copied {db_name} to {target_db}")

                    # Copy associated WAL files
                    for ext in ["-wal", "-shm"]:
                        wal_source = source_db.with_suffix(source_db.suffix + ext)
                        if wal_source.exists():
                            wal_target = target_db.with_suffix(target_db.suffix + ext)
                            shutil.copy2(wal_source, wal_target)
                            logger.info(f"Copied {db_name}{ext}")

                except Exception as e:
                    error_msg = f"Failed to copy {db_name}: {str(e)}"
                    logger.error(error_msg)
                    results["errors"].append(error_msg)
            else:
                if db_name in self.REQUIRED_DBS:
                    results["errors"].append(f"Required database not found: {db_name}")

        # Copy media files if present
        source_media = self.source_path / "media"
        if source_media.exists() and source_media.is_dir():
            target_media = Path(data_dir) / "com.snapchat.android" / "files"
            try:
                if target_media.exists():
                    shutil.rmtree(target_media)
                shutil.copytree(source_media, target_media)
                results["media_copied"] = True
                logger.info(f"Copied media directory to {target_media}")
            except Exception as e:
                logger.warning(f"Failed to copy media directory: {e}")
                # Media is optional, don't fail the whole operation

        # Determine overall success
        results["success"] = len(results["errors"]) == 0 and len(results["databases_copied"]) >= len(self.REQUIRED_DBS)

        return results

    def get_source_info(self) -> dict:
        """
        Get information about the source database directory.

        Returns:
            Dictionary with source directory information
        """
        info = {
            "path": str(self.source_path),
            "exists": self.source_path.exists() if self.source_path else False,
            "databases": [],
            "has_media": False,
            "total_size_mb": 0
        }

        if not self.source_path or not self.source_path.exists():
            return info

        total_size = 0
        for db_name in self.REQUIRED_DBS + self.OPTIONAL_DBS:
            db_path = self.source_path / db_name
            if db_path.exists():
                size = db_path.stat().st_size
                total_size += size
                info["databases"].append({
                    "name": db_name,
                    "size_mb": round(size / (1024 * 1024), 2),
                    "required": db_name in self.REQUIRED_DBS
                })

        media_path = self.source_path / "media"
        if media_path.exists() and media_path.is_dir():
            info["has_media"] = True
            for f in media_path.rglob("*"):
                if f.is_file():
                    total_size += f.stat().st_size

        info["total_size_mb"] = round(total_size / (1024 * 1024), 2)

        return info

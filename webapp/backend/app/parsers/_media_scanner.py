"""
Media scanning component for Snapchat data.
Handles scanning directories and identifying media files.
"""

import hashlib
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Any, Optional

# Separate import for python-magic since it has system dependencies
try:
    import magic
    MAGIC_AVAILABLE = True
except ImportError:
    magic = None
    MAGIC_AVAILABLE = False

logger = logging.getLogger(__name__)

class MediaScanner:
    """
    Component responsible for scanning directories and identifying media files.
    """
    
    def __init__(self, media_base_dir: Path):
        self.media_base_dir = media_base_dir
    
    def identify_file_type(self, file_path: Path) -> Optional[str]:
        """Identify file type using python-magic or fallback"""
        # First try magic detection (more reliable for files without extensions)
        if MAGIC_AVAILABLE:
            try:
                mime_type = magic.from_file(str(file_path), mime=True)
                logger.debug(f"Detected MIME type for {file_path}: {mime_type}")
                if mime_type.startswith('image/'):
                    return 'image'
                elif mime_type.startswith('video/'):
                    return 'video'
                elif mime_type.startswith('audio/'):
                    return 'audio'
                elif 'webp' in mime_type.lower():
                    return 'image'
                # Return the detected type even if not image/video/audio for logging
                return mime_type
            except Exception as e:
                logger.debug(f"Magic detection failed for {file_path}: {e}")
        
        # Fallback to file extension
        ext = file_path.suffix.lower()
        if ext in ['.jpg', '.jpeg', '.png', '.webp', '.gif', '.bmp', '.tiff']:
            return 'image'
        elif ext in ['.mp4', '.mov', '.avi', '.webm', '.mpeg', '.wmv']:
            return 'video'
        elif ext in ['.mp3', '.wav', '.ogg', '.m4a', '.aac', '.flac']:
            return 'audio'
        
        # For files without extensions, try a more permissive approach
        if not ext:
            # Check file size - very small files are likely not media
            if file_path.stat().st_size < 1024:  # Less than 1KB
                return 'too_small'
            # For files without extensions that are reasonably sized, try to peek at content
            try:
                with open(file_path, 'rb') as f:
                    header = f.read(16)
                    # Check for common image/video/audio headers
                    if header.startswith(b'\xff\xd8\xff'):  # JPEG
                        return 'image'
                    elif header.startswith(b'\x89PNG'):  # PNG
                        return 'image' 
                    elif header.startswith(b'RIFF') and b'WEBP' in header:  # WebP
                        return 'image'
                    elif b'ftyp' in header[:16]:  # More flexible MP4 detection - look for "ftyp" box
                        return 'video'
                    elif header.startswith(b'\x1a\x45\xdf\xa3'):  # Matroska/WebM
                        return 'video'
                    elif header.startswith(b'\xff\xfb') or header.startswith(b'\xff\xf3') or header.startswith(b'\xff\xf2'):  # MP3
                        return 'audio'
                    elif header.startswith(b'RIFF') and b'WAVE' in header[:16]:  # WAV
                        return 'audio'
                    elif header.startswith(b'OggS'):  # OGG
                        return 'audio'
            except Exception as e:
                logger.debug(f"Header inspection failed for {file_path}: {e}")
                
        return 'unknown'

    def extract_exif_timestamp(self, file_path: Path) -> Optional[int]:
        """Extract timestamp from EXIF data if available"""
        try:
            # Only try EXIF extraction for image files
            file_type = self.identify_file_type(file_path)
            if file_type != 'image':
                return None
            
            # Try to extract EXIF timestamp using PIL
            from PIL import Image
            from PIL.ExifTags import TAGS
            from datetime import datetime
            
            with Image.open(file_path) as img:
                exif_data = img._getexif()
                if exif_data:
                    for tag_id, value in exif_data.items():
                        tag = TAGS.get(tag_id, tag_id)
                        if tag in ['DateTime', 'DateTimeOriginal', 'DateTimeDigitized']:
                            try:
                                # Parse EXIF datetime format: "YYYY:MM:DD HH:MM:SS"
                                dt = datetime.strptime(value, "%Y:%m:%d %H:%M:%S")
                                return int(dt.timestamp() * 1000)  # Convert to milliseconds
                            except (ValueError, TypeError):
                                continue
        except Exception as e:
            logger.debug(f"Could not extract EXIF timestamp from {file_path}: {e}")
        
        return None

    def get_mime_type(self, file_path: Path) -> str:
        """Get MIME type for a file"""
        if MAGIC_AVAILABLE:
            try:
                return magic.from_file(str(file_path), mime=True)
            except Exception:
                pass
        
        # Fallback based on extension
        ext = file_path.suffix.lower()
        mime_map = {
            # Images
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.png': 'image/png',
            '.webp': 'image/webp',
            '.gif': 'image/gif',
            '.bmp': 'image/bmp',
            '.tiff': 'image/tiff',
            # Videos
            '.mp4': 'video/mp4',
            '.mov': 'video/quicktime',
            '.avi': 'video/x-msvideo',
            '.webm': 'video/webm',
            '.mpeg': 'video/mpeg',
            '.wmv': 'video/x-ms-wmv',
            # Audio
            '.mp3': 'audio/mpeg',
            '.wav': 'audio/wav',
            '.ogg': 'audio/ogg',
            '.m4a': 'audio/mp4',
            '.aac': 'audio/aac',
            '.flac': 'audio/flac'
        }
        return mime_map.get(ext, 'application/octet-stream')

    def scan_media_files(self, data_dir: Path) -> List[Dict[str, Any]]:
        """Scan for media files in native_content_manager (where all media files are stored)"""
        media_files = []
        
        # Only scan native_content_manager since that's where all the media files are
        dir_path = "files/native_content_manager"
        category = "native_cache"
        full_path = self.media_base_dir / dir_path
        
        if full_path.exists():
            logger.info(f"Fast scanning {category}: {full_path}")
            media_files = self.scan_directory_for_media(full_path, category, data_dir)
        else:
            logger.warning(f"Native content manager not found: {full_path}")
        
        logger.info(f"Found {len(media_files)} media files")
        return media_files

    def scan_directory_for_media(self, directory: Path, category: str, data_dir: Path) -> List[Dict[str, Any]]:
        """Scan a single directory for media files"""
        media_files = []
        
        if not directory.exists():
            logger.debug(f"Directory not found for {category}: {directory}")
            return media_files
        
        # Count total files in directory for debugging
        total_files = sum(1 for file_path in directory.rglob('*') if file_path.is_file())
        logger.info(f"Scanning {category}: found {total_files} files in {directory}")
        
        files_processed = 0
        media_found = 0
        
        for file_path in directory.rglob('*'):
            if not file_path.is_file():
                continue
            
            files_processed += 1
            if files_processed <= 5:  # Log first few files for debugging
                logger.debug(f"Checking file {files_processed}: {file_path.name} ({file_path.stat().st_size} bytes)")
                
            file_type = self.identify_file_type(file_path)
            if file_type not in ['image', 'video', 'audio']:
                if files_processed <= 5:  # Log first few rejections
                    logger.debug(f"Rejected {file_path.name}: type='{file_type}' (not image/video/audio)")
                continue
            
            media_found += 1
            
            # Generate file hash
            try:
                file_hash = hashlib.md5(file_path.read_bytes()).hexdigest()
            except Exception as e:
                logger.warning(f"Could not generate hash for {file_path}: {e}")
                continue
            
            # Try to extract timestamp from EXIF
            exif_timestamp = self.extract_exif_timestamp(file_path)
            timestamp_source = 'exif' if exif_timestamp else 'file'
            timestamp = exif_timestamp if exif_timestamp else int(file_path.stat().st_mtime * 1000)
            
            # Extract cache key from filename
            cache_key = file_path.name.split('_')[0] if '_' in file_path.name else file_path.name
            
            # Calculate relative path from the original data_dir (for consistency)
            try:
                relative_path = str(file_path.relative_to(data_dir))
            except ValueError:
                # Fallback if path is not relative to data_dir
                relative_path = str(file_path.relative_to(self.media_base_dir))
            
            media_data = {
                'file_path': relative_path,
                'original_filename': file_path.name,  # Use correct field name for MediaAsset model
                'file_hash': file_hash,
                'file_size': file_path.stat().st_size,
                'file_type': file_type,
                'mime_type': self.get_mime_type(file_path),
                'category': category,
                'cache_key': cache_key,
                'cache_id': None,  # Will be set during message linking
                'sender_id': 'unknown',  # Will be updated when linked to a message
                'file_timestamp': datetime.fromtimestamp(timestamp / 1000, tz=timezone.utc),
                'timestamp_source': timestamp_source
            }
            
            media_files.append(media_data)
        
        logger.info(f"Completed scanning {category}: {files_processed} files processed, {media_found} media files found")
        return media_files

"""
SSH Pull Service - Database and Media Extraction via SSH Tar Stream

Port of the SSH tar-stream approach from android_ssh_extractor.py for extracting
Snapchat databases and media files from Android devices via SSH.
"""

import asyncio
import os
import logging
import tempfile
import tarfile
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any, Set
from datetime import datetime

from ..utils.db_utils import WALConsolidator

logger = logging.getLogger(__name__)


class SSHPullService:
    """SSH service for extracting Snapchat data using tar streams"""
    
    def __init__(
        self,
        ssh_host: str,
        ssh_port: int = 22,
        ssh_user: str = "root",
        ssh_key_path: Optional[str] = None,
        timeout: int = 300
    ):
        self.ssh_host = ssh_host
        self.ssh_port = ssh_port
        self.ssh_user = ssh_user
        self.ssh_key_path = ssh_key_path
        self.timeout = timeout
        
        # Remote paths based on original extractor
        self.remote_snapchat_data_path = "/data/data/com.snapchat.android/"
        
        # Auto-discover SSH key if not provided
        if not self.ssh_key_path:
            self.ssh_key_path = self._find_ssh_key()
    
    def _find_ssh_key(self) -> Optional[str]:
        """Find SSH key in common locations (data folder first, then fallback)"""
        # Priority 1: Check data folder (where uploaded keys are stored)
        data_folder_keys = [
            '/app/data/ssh_keys/id_rsa',
            '/app/data/ssh_keys/id_ed25519',
            '/app/data/ssh_keys/id_ecdsa',
        ]

        # Priority 2: Original hardcoded locations (for backwards compatibility)
        fallback_keys = [
            '/app/originalcode/id_rsa',
            '/app/originalcode/id_ed25519',
            '/app/originalcode/id_ecdsa',
            os.path.expanduser('~/.ssh/id_rsa'),
            os.path.expanduser('~/.ssh/id_ed25519'),
            os.path.expanduser('~/.ssh/id_ecdsa')
        ]

        # Check data folder first
        for key_path in data_folder_keys:
            if os.path.exists(key_path):
                logger.info(f"Found SSH key in data folder: {key_path}")
                return key_path

        # Then check fallback locations
        for key_path in fallback_keys:
            if os.path.exists(key_path):
                logger.info(f"Found SSH key: {key_path}")
                return key_path

        logger.info("No SSH key found, using default authentication")
        return None
    
    async def test_connection(self) -> Tuple[bool, str]:
        """Test SSH connectivity"""
        try:
            success, output = await self._run_ssh_command("echo 'SSH connection test successful'")
            return success, output
        except Exception as e:
            return False, str(e)
    
    async def _run_ssh_command(self, command: str, use_sudo: bool = False) -> Tuple[bool, str]:
        """Execute SSH command with proper options and key handling"""
        if use_sudo:
            command = f"sudo {command}"
        
        ssh_cmd = [
            "ssh",
            "-p", str(self.ssh_port),
            "-o", "StrictHostKeyChecking=no",
            "-o", "UserKnownHostsFile=/dev/null",
            "-o", "ConnectTimeout=30"
        ]
        
        # Add SSH key if available
        if self.ssh_key_path:
            ssh_cmd.extend(["-i", self.ssh_key_path])
        
        ssh_cmd.extend([
            f"{self.ssh_user}@{self.ssh_host}",
            command
        ])
        
        logger.debug(f"Executing SSH command: {' '.join(ssh_cmd)}")
        
        try:
            # Run in executor to avoid blocking
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                lambda: subprocess.run(
                    ssh_cmd,
                    capture_output=True,
                    text=True,
                    timeout=self.timeout
                )
            )
            
            if result.returncode == 0:
                logger.debug("SSH command executed successfully")
                return True, result.stdout
            else:
                logger.error(f"SSH command failed with return code {result.returncode}")
                logger.error(f"SSH stderr: {result.stderr}")
                return False, result.stderr
                
        except subprocess.TimeoutExpired:
            logger.error("SSH command timed out")
            return False, "Command timed out"
        except Exception as e:
            logger.error(f"SSH command failed: {e}")
            return False, str(e)
    
    async def extract_databases(self, output_dir: str) -> Dict[str, Any]:
        """
        Extract Snapchat databases using SSH tar stream
        
        This implements the ultra-fast single command approach from the original extractor.
        """
        logger.info("Starting database extraction via SSH tar stream...")
        
        try:
            logger.info("=== Starting SSH Tar Stream Database Extraction ===")
            logger.info(f"Target: {self.ssh_user}@{self.ssh_host}:{self.ssh_port}")
            logger.info(f"Output directory: {output_dir}")
            logger.info("Using SSH tar stream for databases - single compressed transfer")
            
            # Ensure output directory exists
            os.makedirs(output_dir, exist_ok=True)
            
            # Define the database files we want to include
            # Include cache mappings database for media optimization
            database_items = [
                "com.snapchat.android/databases/arroyo.db",
                "com.snapchat.android/databases/main.db",
                "com.snapchat.android/databases/arroyo.db-wal",
                "com.snapchat.android/databases/arroyo.db-shm", 
                "com.snapchat.android/databases/main.db-wal",
                "com.snapchat.android/databases/main.db-shm",
                "com.snapchat.android/databases/native_content_manager/"
            ]
            
            # Build tar command for databases
            data_path_clean = self.remote_snapchat_data_path.rstrip('/')
            base_dir = os.path.dirname(data_path_clean)  # Go up to data_ce/null/0 level
            
            tar_files_str = ' '.join(database_items)
            tar_cmd = f'cd {base_dir} && echo \\"Starting database tar from $(pwd)\\" >&2 && tar -cf - {tar_files_str} 2>&2 || echo \\"TAR_FAILED\\" >&2'
            
            logger.info(f"Streaming tar archive of {len(database_items)} database files...")
            logger.debug(f"Tar command: {tar_cmd}")
            
            # Create local tar file path
            local_tar_path = os.path.join(output_dir, "databases_stream.tar")
            
            # Build SSH command to stream tar
            ssh_cmd = [
                "ssh",
                "-p", str(self.ssh_port),
                "-o", "StrictHostKeyChecking=no", 
                "-o", "UserKnownHostsFile=/dev/null",
                "-o", "ConnectTimeout=30"
            ]
            
            # Add SSH key if available
            if self.ssh_key_path:
                ssh_cmd.extend(["-i", self.ssh_key_path])
            
            ssh_cmd.extend([
                f"{self.ssh_user}@{self.ssh_host}",
                tar_cmd
            ])
            
            logger.info("Executing SSH database tar stream transfer...")
            
            # Execute SSH command and stream directly to local tar file
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                self._execute_tar_stream,
                ssh_cmd,
                local_tar_path
            )
            
            if result['success']:
                # Verify tar file exists and has content
                if os.path.exists(local_tar_path) and os.path.getsize(local_tar_path) > 0:
                    logger.info(f"Successfully streamed database tar: {local_tar_path} ({os.path.getsize(local_tar_path)} bytes)")
                    
                    # Extract the tar file
                    extracted_files = await self._extract_tar_file(local_tar_path, output_dir)
                    
                    # Clean up tar file
                    os.remove(local_tar_path)
                    
                    return {
                        'success': True,
                        'extracted_files': extracted_files,
                        'message': f"Successfully extracted {len(extracted_files)} database files"
                    }
                else:
                    raise Exception("SSH tar stream completed but local file is missing or empty")
            else:
                raise Exception(f"SSH tar stream failed: {result['error']}")
                
        except Exception as e:
            logger.error(f"SSH database tar stream extraction failed: {e}")
            
            # Clean up on failure
            if 'local_tar_path' in locals() and os.path.exists(local_tar_path):
                try:
                    os.remove(local_tar_path)
                except:
                    pass
            
            return {
                'success': False,
                'error': str(e),
                'extracted_files': []
            }
    
    async def extract_media_optimized(
        self, 
        output_dir: str, 
        message_cache_ids: Optional[List[str]] = None,
        existing_media_filenames: Optional[Set[str]] = None
    ) -> Dict[str, Any]:
        """
        Extract Snapchat media files using optimized workflow:
        1. Extract cache_controller.db for mappings
        2. Discover remote media files  
        3. Transfer only files linked to messages that we don't already have
        """
        logger.info("Starting optimized Snapchat media extraction...")
        
        try:
            from .media_discovery import MediaDiscoveryService
            
            # Initialize media discovery service
            discovery_service = MediaDiscoveryService(
                ssh_host=self.ssh_host,
                ssh_port=self.ssh_port,
                ssh_user=self.ssh_user,
                ssh_key_path=self.ssh_key_path,
                timeout=self.timeout
            )
            
            logger.info("=== Phase 1: Check Cache Mappings (Already Extracted) ===")
            # Cache mappings should already be extracted in the initial database extraction
            # Check if cache controller database exists
            cache_db_path = Path(output_dir) / "com.snapchat.android" / "databases" / "native_content_manager" / "cache_controller.db"
            if cache_db_path.exists():
                logger.info(f"✅ Cache mappings database already available: {cache_db_path}")
                cache_result = {
                    'success': True,
                    'extracted_files': [str(cache_db_path.relative_to(output_dir))],
                    'message': 'Cache mappings already extracted with initial databases'
                }
            else:
                logger.warning(f"⚠️ Cache mappings not found, falling back to separate extraction")
                # Fallback to separate extraction if not found
                cache_result = await discovery_service.extract_cache_mappings_db(output_dir)
                if not cache_result['success']:
                    return cache_result
            
            logger.info("=== Phase 2: Discover Remote Media Files ===")
            # Discover all media files on remote device
            discovery_result = await discovery_service.discover_remote_media_files()
            if not discovery_result['success']:
                return discovery_result
            
            logger.info(f"Discovered {discovery_result['total_files']} remote media files")
            
            # If no message cache IDs provided, we can't determine what to transfer
            if not message_cache_ids:
                logger.warning("No message cache IDs provided - cannot determine needed media files")
                return {
                    'success': True,
                    'extracted_files': cache_result['extracted_files'],
                    'transferred_files': [],
                    'message': "Only cache mappings extracted - no message cache IDs provided"
                }
            
            logger.info("=== Phase 3: Load Cache Mappings ===")
            # Load cache mappings from extracted database
            cache_mappings = self._load_cache_mappings_from_db(output_dir)
            logger.info(f"Loaded {len(cache_mappings)} cache mappings")
            
            logger.info("=== Phase 4: Determine Needed Files ===")
            # Determine which files we actually need
            existing_filenames = existing_media_filenames or set()
            needed_files = discovery_service.determine_needed_media_files(
                discovered_files=discovery_result,
                existing_media_filenames=existing_filenames,
                cache_mappings=cache_mappings,
                message_cache_ids=set(message_cache_ids)
            )
            
            total_needed = sum(len(files) for files in needed_files.values())
            logger.info(f"Need to transfer {total_needed} media files")
            
            if total_needed == 0:
                logger.info("No new media files need to be transferred")
                return {
                    'success': True,
                    'extracted_files': cache_result['extracted_files'],
                    'transferred_files': [],
                    'message': "No new media files needed - all are already stored locally"
                }
            
            logger.info("=== Phase 5: Transfer Needed Media Files ===")
            # Transfer only the files we need
            transfer_result = await discovery_service.transfer_specific_media_files(
                needed_files=needed_files,
                output_dir=output_dir
            )
            
            if transfer_result['success']:
                all_extracted_files = cache_result['extracted_files'] + transfer_result['transferred_files']
                
                return {
                    'success': True,
                    'extracted_files': all_extracted_files,
                    'transferred_files': transfer_result['transferred_files'],
                    'cache_files': cache_result['extracted_files'],
                    'message': f"Optimized extraction: {len(cache_result['extracted_files'])} cache files + {len(transfer_result['transferred_files'])} media files"
                }
            else:
                return transfer_result
                
        except Exception as e:
            logger.error(f"Optimized media extraction failed: {e}")
            return {
                'success': False,
                'error': str(e),
                'extracted_files': []
            }
    
    def _load_cache_mappings_from_db(self, output_dir: str) -> List[Tuple[str, str]]:
        """Load cache mappings from extracted cache_controller.db"""
        cache_db_path = Path(output_dir) / "com.snapchat.android" / "databases" / "native_content_manager" / "cache_controller.db"
        
        if not cache_db_path.exists():
            logger.warning(f"Cache controller DB not found at: {cache_db_path}")
            return []
        
        try:
            # Use the WAL consolidator to ensure we get all data
            WALConsolidator.consolidate_wal_database(str(cache_db_path))
            
            conn = WALConsolidator.connect_with_wal_support(str(cache_db_path))
            cursor = conn.cursor()
            
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

    async def extract_media(self, output_dir: str) -> Dict[str, Any]:
        """
        Legacy media extraction method - kept for backward compatibility
        Use extract_media_optimized() for better performance
        """
        logger.warning("Using legacy media extraction - consider using extract_media_optimized() for better performance")
        
        try:
            logger.info("=== Starting SSH Tar Stream Media Extraction (Legacy) ===")
            logger.info(f"Target: {self.ssh_user}@{self.ssh_host}:{self.ssh_port}")
            logger.info(f"Output directory: {output_dir}")
            logger.info("Using SSH tar stream - single compressed transfer")
            
            # Ensure output directory exists
            os.makedirs(output_dir, exist_ok=True)
            
            # Define the media files and directories we want to include
            # Updated based on actual Android directory structure
            media_items = [
                "databases/arroyo.db",
                "databases/main.db", 
                "databases/arroyo.db-wal",
                "databases/arroyo.db-shm",
                "databases/main.db-wal",
                "databases/main.db-shm",
                "databases/native_content_manager/",  # Contains cache_controller.db for cache key mapping
                # Primary media locations (where actual media files are stored)
                "files/native_content_manager/",  # Main media cache
                "cache/disk_cache/",              # Additional media cache
                # File manager directories that actually exist
                "files/file_manager/chat_snap/",
                "files/file_manager/snap/", 
                "files/file_manager/media/",
                "files/file_manager/camera_roll_media/",
                "files/file_manager/chat_wallpaper_media/",
                "files/file_manager/impala/",
                # Legacy directories (may not exist on newer versions, but include for compatibility)
                "files/file_manager/snap_first_frame/",
                "files/file_manager/story_snap/",
                "files/file_manager/snap_loading_frame/",
                "files/file_manager/chat_media/",
                "files/file_manager/memories_media/"
            ]
            
            # Build tar command that creates a compressed stream
            data_path_clean = self.remote_snapchat_data_path.rstrip('/')
            base_dir = os.path.dirname(data_path_clean)  # Go up one level to include com.snapchat.android
            
            # Create the tar files list with the com.snapchat.android prefix
            tar_files = []
            for item in media_items:
                tar_files.append(f'com.snapchat.android/{item}')
            
            tar_files_str = ' '.join(tar_files)
            
            # Test directory access first
            test_cmd = f'"ls -la {base_dir}/com.snapchat.android/ | head -10"'
            logger.info("Testing directory access...")
            test_success, test_output = await self._run_ssh_command(test_cmd)
            
            if test_success:
                logger.info(f"Directory test successful: {test_output[:200]}...")
            else:
                logger.warning(f"Directory test failed: {test_output}")
            
            # Create tar command that sends ONLY tar data to stdout and messages to stderr
            tar_cmd = f'cd {base_dir} && echo \\"Starting tar from $(pwd)\\" >&2 && tar -cf - {tar_files_str} 2>&2 || echo \\"TAR_FAILED\\" >&2'
            
            logger.info(f"Streaming tar archive of {len(media_items)} media items...")
            logger.debug(f"Tar command: {tar_cmd}")
            
            # Create local tar file path
            local_tar_path = os.path.join(output_dir, "snapchat_media_stream.tar")
            
            # Build SSH command to stream tar
            ssh_cmd = [
                "ssh",
                "-p", str(self.ssh_port),
                "-o", "StrictHostKeyChecking=no",
                "-o", "UserKnownHostsFile=/dev/null", 
                "-o", "ConnectTimeout=30"
            ]
            
            # Add SSH key if available
            if self.ssh_key_path:
                ssh_cmd.extend(["-i", self.ssh_key_path])
            
            ssh_cmd.extend([
                f"{self.ssh_user}@{self.ssh_host}",
                tar_cmd
            ])
            
            logger.info("Executing SSH media tar stream transfer...")
            
            # Execute SSH command and stream directly to local tar file
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                self._execute_tar_stream,
                ssh_cmd,
                local_tar_path
            )
            
            if result['success']:
                if os.path.exists(local_tar_path) and os.path.getsize(local_tar_path) > 0:
                    logger.info(f"Successfully streamed media tar: {local_tar_path} ({os.path.getsize(local_tar_path)} bytes)")
                    
                    # Verify tar file integrity
                    await self._verify_tar_file(local_tar_path)
                    
                    # Extract the tar file
                    extracted_files = await self._extract_tar_file(local_tar_path, output_dir)
                    
                    # Clean up tar file
                    os.remove(local_tar_path)
                    
                    return {
                        'success': True,
                        'extracted_files': extracted_files,
                        'message': f"Successfully extracted {len(extracted_files)} media files"
                    }
                else:
                    raise Exception("SSH tar stream completed but local file is missing or empty")
            else:
                raise Exception(f"SSH tar stream failed: {result['error']}")
                
        except Exception as e:
            logger.error(f"SSH tar stream media extraction failed: {e}")
            
            # Clean up on failure
            if 'local_tar_path' in locals() and os.path.exists(local_tar_path):
                try:
                    os.remove(local_tar_path)
                except:
                    pass
            
            return {
                'success': False,
                'error': str(e),
                'extracted_files': []
            }
    
    def _execute_tar_stream(self, ssh_cmd: List[str], local_tar_path: str) -> Dict[str, Any]:
        """Execute SSH tar stream command and save to local file"""
        try:
            with open(local_tar_path, 'wb') as local_tar_file:
                result = subprocess.run(
                    ssh_cmd,
                    stdout=local_tar_file,
                    stderr=subprocess.PIPE,
                    timeout=self.timeout
                )
            
            # Log any messages from stderr
            if result.stderr:
                stderr_output = result.stderr.decode()
                logger.info(f"SSH tar stderr output: {stderr_output}")
            
            if result.returncode == 0:
                return {'success': True}
            else:
                return {'success': False, 'error': result.stderr.decode()}
                
        except subprocess.TimeoutExpired:
            return {'success': False, 'error': "SSH tar stream timed out"}
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    async def _verify_tar_file(self, tar_path: str) -> None:
        """Verify tar file integrity by checking header"""
        with open(tar_path, 'rb') as f:
            header = f.read(512)  # Tar header is 512 bytes
            if len(header) >= 512:
                # Check for tar magic number at offset 257
                magic = header[257:262]
                if magic == b'ustar':
                    logger.info("Tar file appears to have valid header")
                else:
                    logger.warning(f"Tar file may be corrupted - magic bytes: {magic}")
                    logger.warning(f"First 50 bytes: {header[:50]}")
            else:
                logger.warning(f"Tar file too small: {len(header)} bytes")
    
    async def _extract_tar_file(self, tar_path: str, output_dir: str) -> List[str]:
        """Extract tar file and return list of extracted files"""
        extracted_files = []
        
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None,
            self._extract_tar_sync,
            tar_path,
            output_dir,
            extracted_files
        )
        
        return extracted_files
    
    def _extract_tar_sync(self, tar_path: str, output_dir: str, extracted_files: List[str]) -> None:
        """Synchronous tar extraction"""
        with tarfile.open(tar_path, 'r') as tar:
            tar.extractall(output_dir)
            
            # Track extracted files
            for member in tar.getmembers():
                if member.isfile():
                    extracted_files.append(member.name)
        
        # Log extraction results
        logger.info(f"Extracted tar file to {output_dir}")
        for root, dirs, files in os.walk(output_dir):
            if files:
                logger.debug(f"Directory {root}: {len(dirs)} dirs, {len(files)} files")
                if files and logger.isEnabledFor(logging.DEBUG):
                    logger.debug(f"Sample files: {files[:5]}")



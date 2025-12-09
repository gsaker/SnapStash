#!/usr/bin/env python3
"""
Media Discovery Service
Efficiently discovers media files on remote device using SSH find commands
and determines which files need to be transferred based on local storage.
"""

import asyncio
import os
import json
import logging
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any, Set
from datetime import datetime

logger = logging.getLogger(__name__)


class MediaDiscoveryService:
    """Service for discovering and managing media files without transferring everything"""
    
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
        
        # Remote paths based on current SSH service
        self.remote_snapchat_data_path = "/data/data/com.snapchat.android/"
        
        # Auto-discover SSH key if not provided (same logic as SSH service)
        if not self.ssh_key_path:
            self.ssh_key_path = self._find_ssh_key()
    
    def _find_ssh_key(self) -> Optional[str]:
        """Find SSH key in common locations"""
        potential_keys = [
            '/app/originalcode/id_rsa',
            '/app/originalcode/id_ed25519', 
            '/app/originalcode/id_ecdsa',
            os.path.expanduser('~/.ssh/id_rsa'),
            os.path.expanduser('~/.ssh/id_ed25519'),
            os.path.expanduser('~/.ssh/id_ecdsa')
        ]
        
        for key_path in potential_keys:
            if os.path.exists(key_path):
                logger.info(f"Found SSH key: {key_path}")
                return key_path
        
        logger.info("No SSH key found, using default authentication")
        return None
    
    async def _run_ssh_command(self, command: str, use_sudo: bool = True) -> Tuple[bool, str]:
        """Execute SSH command with proper options and key handling"""
        if use_sudo:
            command = f"{command}"
        
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
    
    async def discover_remote_media_files(self) -> Dict[str, Any]:
        """
        Discover all media files on the remote device using fast find command
        Only scans native_content_manager since that's where all media files are
        """
        logger.info("Starting fast remote media file discovery...")
        
        try:
            # Only scan native_content_manager since that's where all the media files are
            media_directory = "files/native_content_manager"
            full_remote_path = f"{self.remote_snapchat_data_path.rstrip('/')}/{media_directory}"
            
            # Use simple find command since -printf doesn't work reliably on Android
            find_cmd = f"find {full_remote_path} -type f 2>/dev/null || true"
            
            logger.info(f"Fast discovery in: {media_directory}")
            success, output = await self._run_ssh_command(find_cmd)
            
            discovered_files = {}
            total_files = 0
            
            if success and output.strip():
                dir_files = {}
                for line in output.strip().split('\n'):
                    if not line.strip():
                        continue
                    
                    try:
                        # Full path from find command
                        full_file_path = line.strip()
                        
                        # Extract filename and relative path
                        filename = os.path.basename(full_file_path)
                        # Get the path relative to the base snapchat data directory, removing the prefix
                        relative_file_path = full_file_path.replace(f"{self.remote_snapchat_data_path}/", "").lstrip("/")
                        
                        # Assume all files in native_content_manager are media files (as requested)
                        # Create file metadata with minimal info since we can't get size/mtime easily
                        file_info = {
                            'remote_path': full_file_path,
                            'relative_path': relative_file_path,
                            'filename': filename,
                            'size': 0,  # We'll assume it's a valid media file
                            'mtime': 0,  # Not needed for our optimization
                            'directory': media_directory,
                            'cache_key': self._extract_cache_key(filename)
                        }
                        #logger.info(f"Discovered file: {file_info}")
                        
                        dir_files[filename] = file_info
                        total_files += 1
                    except Exception as e:
                        logger.debug(f"Could not parse find output line: {line} - {e}")
                        continue
                
                discovered_files[media_directory] = dir_files
                logger.info(f"Fast discovery found {len(dir_files)} media files")
                if dir_files:
                    sample_discovered = list(dir_files.keys())[:5]
                    logger.info(f"Sample discovered filenames: {sample_discovered}")
            else:
                logger.debug(f"No files found or error in directory: {media_directory}")
                discovered_files[media_directory] = {}
            
            logger.info(f"=== Fast Remote Media Discovery Summary ===")
            logger.info(f"Total media files discovered: {total_files}")
            
            return {
                'success': True,
                'total_files': total_files,
                'directories': discovered_files,
                'scan_timestamp': datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Remote media discovery failed: {e}")
            return {
                'success': False,
                'error': str(e),
                'total_files': 0,
                'directories': {}
            }
    
    def _extract_cache_key(self, filename: str) -> str:
        """Extract cache key from filename (same logic as parser)"""
        if '_' in filename:
            return filename.split('_')[0]
        return filename.split('.')[0] if '.' in filename else filename
    
    async def extract_cache_mappings_db(self, output_dir: str) -> Dict[str, Any]:
        """
        Extract only the cache_controller.db for cache mappings
        Much faster than transferring all media
        """
        logger.info("Extracting cache mappings database...")
        
        try:
            os.makedirs(output_dir, exist_ok=True)
            
            # Define the specific cache mapping files we need
            cache_db_items = [
                "com.snapchat.android/databases/native_content_manager/cache_controller.db",
                "com.snapchat.android/databases/native_content_manager/cache_controller.db-wal",
                "com.snapchat.android/databases/native_content_manager/cache_controller.db-shm"
            ]
            
            # Build tar command for cache database only
            data_path_clean = self.remote_snapchat_data_path.rstrip('/')
            base_dir = os.path.dirname(data_path_clean)
            
            tar_files_str = ' '.join(cache_db_items)
            tar_cmd = f'cd {base_dir} && echo "Starting cache DB tar from $(pwd)" >&2 && tar -cf - {tar_files_str} 2>&2 || echo "TAR_FAILED" >&2'
            
            logger.info("Streaming cache mappings database...")
            
            # Create local tar file path
            local_tar_path = os.path.join(output_dir, "cache_mappings.tar")
            
            # Build SSH command to stream tar
            ssh_cmd = [
                "ssh",
                "-p", str(self.ssh_port),
                "-o", "StrictHostKeyChecking=no",
                "-o", "UserKnownHostsFile=/dev/null",
                "-o", "ConnectTimeout=30"
            ]
            
            if self.ssh_key_path:
                ssh_cmd.extend(["-i", self.ssh_key_path])
            
            ssh_cmd.extend([
                f"{self.ssh_user}@{self.ssh_host}",
                f"{tar_cmd}"
            ])
            
            # Execute SSH tar stream
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                self._execute_tar_stream,
                ssh_cmd,
                local_tar_path
            )
            
            if result['success']:
                if os.path.exists(local_tar_path) and os.path.getsize(local_tar_path) > 0:
                    logger.info(f"Successfully streamed cache mappings: {local_tar_path} ({os.path.getsize(local_tar_path)} bytes)")
                    
                    # Extract the tar file
                    extracted_files = await self._extract_tar_file(local_tar_path, output_dir)
                    
                    # Clean up tar file
                    os.remove(local_tar_path)
                    
                    return {
                        'success': True,
                        'extracted_files': extracted_files,
                        'message': f"Successfully extracted {len(extracted_files)} cache mapping files"
                    }
                else:
                    raise Exception("Cache mappings tar stream completed but local file is missing or empty")
            else:
                raise Exception(f"Cache mappings tar stream failed: {result['error']}")
                
        except Exception as e:
            logger.error(f"Cache mappings extraction failed: {e}")
            
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
    
    async def _extract_tar_file(self, tar_path: str, output_dir: str) -> List[str]:
        """Extract tar file and return list of extracted files"""
        import tarfile
        
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
        import tarfile
        
        with tarfile.open(tar_path, 'r') as tar:
            tar.extractall(output_dir)
            
            # Track extracted files
            for member in tar.getmembers():
                if member.isfile():
                    extracted_files.append(member.name)
        
        logger.info(f"Extracted tar file to {output_dir}")
    
    def determine_needed_media_files(
        self, 
        discovered_files: Dict[str, Any],
        existing_media_filenames: Set[str],
        cache_mappings: List[Tuple[str, str]],
        message_cache_ids: Set[str]
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Determine which media files need to be transferred based on:
        1. Files we don't already have (by filename)
        2. Files that are referenced by messages (via cache mappings)
        """
        needed_files = {}
        total_needed = 0
        
        # Create lookup map for cache_id -> cache_key mappings
        cache_id_to_key = {}
        for cache_key, external_key in cache_mappings:
            for cache_id in message_cache_ids:
                if external_key and cache_id in external_key:
                    cache_id_to_key[cache_id] = cache_key
                    break
        
        logger.info(f"Found {len(cache_id_to_key)} cache ID to cache key mappings")
        logger.info(f"Message cache IDs to check: {len(message_cache_ids)}")
        logger.info(f"Sample cache mappings: {list(cache_id_to_key.items())[:3]}")
        logger.info(f"Existing media filenames count: {len(existing_media_filenames)}")
        if existing_media_filenames:
            sample_existing = list(existing_media_filenames)[:5]
            logger.info(f"Sample existing filenames: {sample_existing}")
        

        
        for directory, dir_files in discovered_files.get('directories', {}).items():
            directory_needed = []
            
            for filename, file_info in dir_files.items():
                cache_key = file_info['cache_key']
                
                # Skip if we already have this file (check both full filename and cache key)
                if filename in existing_media_filenames:
                    logger.info(f"✅ Skipping already existing file: {filename}")
                    continue
                elif cache_key in existing_media_filenames:
                    logger.info(f"✅ Skipping already existing file by cache key: {filename} (cache_key: {cache_key})")
                    continue
                else:
                    logger.debug(f"🔍 Checking if file {filename} is referenced by messages...")
                
                # Check if this file is referenced by any message
                is_referenced = False
                
                # Method 1: Direct cache key match
                if cache_key in cache_id_to_key.values():
                    is_referenced = True
                    logger.debug(f"Method 1: Direct cache key match for {cache_key}")
                
                # Method 2: Check if any message cache_id maps to this cache_key
                if not is_referenced:
                    for cache_id in message_cache_ids:
                        if cache_id_to_key.get(cache_id) == cache_key:
                            is_referenced = True
                            logger.debug(f"Method 2: Cache ID {cache_id} maps to cache key {cache_key}")
                            break
                
                # Method 3: Partial string matching (fallback)
                if not is_referenced:
                    for cache_id in message_cache_ids:
                        if cache_id and cache_key and (cache_id in cache_key or cache_key in cache_id):
                            is_referenced = True
                            logger.debug(f"Method 3: Partial match between cache_id {cache_id} and cache_key {cache_key}")
                            break
                
                if is_referenced:
                    directory_needed.append(file_info)
                    total_needed += 1
                else:
                    logger.debug(f"Skipping unreferenced file: {filename} (cache_key: {cache_key})")
            
            if directory_needed:
                needed_files[directory] = directory_needed
                logger.info(f"Need {len(directory_needed)} files from {directory}")
        
        logger.info(f"=== Media Transfer Analysis ===")
        logger.info(f"Total files needed: {total_needed}")
        logger.info(f"Directories with needed files: {len(needed_files)}")
        
        return needed_files
    
    async def transfer_specific_media_files(
        self, 
        needed_files: Dict[str, List[Dict[str, Any]]], 
        output_dir: str
    ) -> Dict[str, Any]:
        """
        Transfer only the specific media files that are needed
        Uses selective tar command to transfer only required files
        """
        if not needed_files:
            logger.info("No media files need to be transferred")
            return {'success': True, 'transferred_files': [], 'message': "No files needed"}
        
        logger.info("Starting selective media file transfer...")
        
        try:
            os.makedirs(output_dir, exist_ok=True)
            
            # Build list of specific files to transfer
            files_to_transfer = []
            for directory, dir_files in needed_files.items():
                for file_info in dir_files:
                    # Use remote_path which is the full absolute path on the device
                    remote_path = file_info['remote_path']
                    files_to_transfer.append(remote_path)
            logger.info(f"Files to transfer: {files_to_transfer}")

            if not files_to_transfer:
                return {'success': True, 'transferred_files': [], 'message': "No files to transfer"}
            
            logger.info(f"Transferring {len(files_to_transfer)} specific media files...")
            
            # Build selective tar command - run tar from root since we're using absolute paths
            base_dir = "/"  # Run tar from root to handle absolute paths
            
            # Create tar command with file list written to temporary file on Android device
            # Write file list to /data/local/tmp (which should be writable) on Android devices
            temp_file_list = '/data/local/tmp/snapchat_media_files.txt'
            
            # First, create the file list on the remote device using multiple echo commands
            # This avoids the command line length limit issue
            logger.info(f"Creating file list on remote device with {len(files_to_transfer)} files...")
            
            # Split into smaller chunks to avoid command line limits
            chunk_size = 5  # Very small chunks to avoid command line length issues
            file_chunks = [files_to_transfer[i:i + chunk_size] for i in range(0, len(files_to_transfer), chunk_size)]
            
            # Create commands to write the file list - write each file individually to avoid command line limits
            create_file_cmds = []
            for i, filename in enumerate(files_to_transfer):
                # Escape single quotes in filenames by replacing ' with '\''
                escaped_filename = filename.replace("'", "'\\''")
                
                if i == 0:
                    # First file - overwrite the temp file
                    create_file_cmds.append(f"echo '{escaped_filename}' > {temp_file_list}")
                else:
                    # Subsequent files - append to the temp file  
                    create_file_cmds.append(f"echo '{escaped_filename}' >> {temp_file_list}")
            
            # Combine all file creation commands
            create_all_files_cmd = ' && '.join(create_file_cmds)
            
            tar_cmd = f'cd {base_dir} && {create_all_files_cmd} && tar -cf - -T {temp_file_list} 2>&2 && rm {temp_file_list} || (echo "TAR_FAILED" >&2 && rm -f {temp_file_list})'
            
            # Create local tar file path
            local_tar_path = os.path.join(output_dir, "selective_media.tar")
            
            # Build SSH command
            ssh_cmd = [
                "ssh",
                "-p", str(self.ssh_port),
                "-o", "StrictHostKeyChecking=no",
                "-o", "UserKnownHostsFile=/dev/null",
                "-o", "ConnectTimeout=30"
            ]
            
            if self.ssh_key_path:
                ssh_cmd.extend(["-i", self.ssh_key_path])
            
            ssh_cmd.extend([
                f"{self.ssh_user}@{self.ssh_host}",
                f"{tar_cmd}"
            ])
            
            logger.info("Executing selective media transfer...")
            
            # Execute SSH command
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                self._execute_tar_stream,
                ssh_cmd,
                local_tar_path
            )
            
            if result['success']:
                if os.path.exists(local_tar_path) and os.path.getsize(local_tar_path) > 0:
                    logger.info(f"Successfully transferred selective media: {local_tar_path} ({os.path.getsize(local_tar_path)} bytes)")
                    
                    # Extract the tar file
                    extracted_files = await self._extract_tar_file(local_tar_path, output_dir)
                    
                    # Debug: check what directory structure was created
                    logger.info(f"Checking directory structure after extraction...")
                    data_dir_path = Path(output_dir) / "data" / "data" / "com.snapchat.android"
                    com_dir_path = Path(output_dir) / "com.snapchat.android" 
                    
                    if data_dir_path.exists():
                        logger.info(f"Found extracted files in: {data_dir_path}")
                        # Move files from data/data/com.snapchat.android to com.snapchat.android
                        if not com_dir_path.exists():
                            com_dir_path.mkdir(parents=True)
                        
                        # Move the files directory
                        source_files = data_dir_path / "files"
                        target_files = com_dir_path / "files"
                        if source_files.exists() and not target_files.exists():
                            import shutil
                            shutil.move(str(source_files), str(target_files))
                            logger.info(f"Moved files from {source_files} to {target_files}")
                    
                    # Clean up tar file
                    os.remove(local_tar_path)
                    
                    return {
                        'success': True,
                        'transferred_files': extracted_files,
                        'message': f"Successfully transferred {len(extracted_files)} media files"
                    }
                else:
                    raise Exception("Selective media transfer completed but local file is missing or empty")
            else:
                raise Exception(f"Selective media transfer failed: {result['error']}")
        
        except Exception as e:
            logger.error(f"Selective media transfer failed: {e}")
            
            # Clean up on failure
            if 'local_tar_path' in locals() and os.path.exists(local_tar_path):
                try:
                    os.remove(local_tar_path)
                except:
                    pass
            
            return {
                'success': False,
                'error': str(e),
                'transferred_files': []
            }
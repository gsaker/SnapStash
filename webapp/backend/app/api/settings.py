"""
Settings API Endpoints
Provides REST API for managing application settings
"""

import logging
import os
from typing import List
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import AppSettings
from ..schemas import (
    AppSetting,
    UserConfigurableSettings,
    SettingsUpdateRequest,
    ApiResponse
)
from ..services.settings_service import get_settings_service, SettingsService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/settings", tags=["settings"])

# SSH key storage path
SSH_KEY_STORAGE_PATH = "/app/data/ssh_keys"


@router.get("", response_model=UserConfigurableSettings)
@router.get("/", response_model=UserConfigurableSettings)
async def get_settings(
    db: Session = Depends(get_db)
):
    """
    Get all user-configurable settings.

    Returns the current values of all settings that can be configured
    via the frontend interface.
    """
    try:
        settings_service = get_settings_service(db)
        settings = settings_service.get_all_settings()
        return settings
    except Exception as e:
        logger.error(f"Error getting settings: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("", response_model=ApiResponse)
@router.put("/", response_model=ApiResponse)
async def update_settings(
    request: SettingsUpdateRequest,
    db: Session = Depends(get_db)
):
    """
    Update user-configurable settings.

    Updates one or more settings with new values. Only non-null values
    in the request will be updated.
    """
    try:
        settings_service = get_settings_service(db)
        success = settings_service.update_settings(request.settings)

        if success:
            return ApiResponse(
                success=True,
                message="Settings updated successfully",
                data=settings_service.get_all_settings().model_dump()
            )
        else:
            raise HTTPException(status_code=500, detail="Failed to update settings")
    except Exception as e:
        logger.error(f"Error updating settings: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/raw", response_model=List[AppSetting])
async def get_raw_settings(
    category: str = None,
    db: Session = Depends(get_db)
):
    """
    Get raw settings from database.

    Optional query parameter:
    - category: Filter settings by category (ssh, ingest, ui, etc.)

    This endpoint is primarily for debugging and advanced users.
    """
    try:
        query = db.query(AppSettings)

        if category:
            query = query.filter(AppSettings.category == category)

        settings = query.all()
        return settings
    except Exception as e:
        logger.error(f"Error getting raw settings: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/initialize", response_model=ApiResponse)
async def initialize_settings(
    db: Session = Depends(get_db)
):
    """
    Initialize settings with default values.

    Creates default settings in the database if they don't exist.
    This is safe to call multiple times - it won't overwrite existing values.
    """
    try:
        settings_service = get_settings_service(db)
        settings_service.initialize_defaults()
        return ApiResponse(
            success=True,
            message="Settings initialized successfully",
            data=None
        )
    except Exception as e:
        logger.error(f"Error initializing settings: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/clear-cache", response_model=ApiResponse)
async def clear_settings_cache():
    """
    Clear the settings cache.

    Forces the next settings request to read from the database.
    Useful after manual database changes.
    """
    try:
        settings_service = get_settings_service()
        settings_service.clear_cache()
        return ApiResponse(
            success=True,
            message="Settings cache cleared successfully",
            data=None
        )
    except Exception as e:
        logger.error(f"Error clearing settings cache: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/ssh-key/upload", response_model=ApiResponse)
async def upload_ssh_key(
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    """
    Upload an SSH private key file.

    The key will be stored securely in /app/data/ssh_keys/ and the
    ssh_key_path setting will be automatically updated.

    Accepts common SSH key formats:
    - id_rsa (RSA)
    - id_ed25519 (Ed25519)
    - id_ecdsa (ECDSA)
    - Or any custom name
    """
    try:
        # Ensure storage directory exists
        os.makedirs(SSH_KEY_STORAGE_PATH, mode=0o700, exist_ok=True)

        # Validate file size (max 10KB for SSH keys)
        contents = await file.read()
        if len(contents) > 10 * 1024:
            raise HTTPException(
                status_code=400,
                detail="SSH key file is too large. Maximum size is 10KB."
            )

        # Validate it looks like an SSH key
        content_str = contents.decode('utf-8', errors='ignore')
        if not any(marker in content_str for marker in [
            'BEGIN OPENSSH PRIVATE KEY',
            'BEGIN RSA PRIVATE KEY',
            'BEGIN EC PRIVATE KEY',
            'BEGIN DSA PRIVATE KEY',
            'BEGIN PRIVATE KEY'
        ]):
            raise HTTPException(
                status_code=400,
                detail="File does not appear to be a valid SSH private key."
            )

        # Use the original filename or default to id_rsa
        filename = file.filename if file.filename else "id_rsa"

        # Sanitize filename (remove any path components)
        filename = os.path.basename(filename)

        # Save the file
        key_path = os.path.join(SSH_KEY_STORAGE_PATH, filename)
        with open(key_path, 'wb') as f:
            f.write(contents)

        # Set correct permissions (readable only by owner)
        os.chmod(key_path, 0o600)

        # Update the ssh_key_path setting
        settings_service = get_settings_service(db)
        settings_service.set_setting("ssh_key_path", key_path)

        logger.info(f"SSH key uploaded successfully: {key_path}")

        return ApiResponse(
            success=True,
            message=f"SSH key uploaded successfully as {filename}",
            data={"ssh_key_path": key_path, "filename": filename}
        )

    except UnicodeDecodeError:
        raise HTTPException(
            status_code=400,
            detail="File does not appear to be a valid text-based SSH key."
        )
    except Exception as e:
        logger.error(f"Error uploading SSH key: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/ssh-key/info", response_model=ApiResponse)
async def get_ssh_key_info(db: Session = Depends(get_db)):
    """
    Get information about the currently configured SSH key.

    Returns the path and whether the file exists.
    """
    try:
        settings_service = get_settings_service(db)
        ssh_key_path = settings_service.get_setting("ssh_key_path")

        if not ssh_key_path:
            return ApiResponse(
                success=True,
                message="No SSH key configured",
                data={"configured": False, "path": None, "exists": False}
            )

        exists = os.path.exists(ssh_key_path)
        filename = os.path.basename(ssh_key_path) if ssh_key_path else None

        return ApiResponse(
            success=True,
            message="SSH key info retrieved",
            data={
                "configured": True,
                "path": ssh_key_path,
                "filename": filename,
                "exists": exists
            }
        )

    except Exception as e:
        logger.error(f"Error getting SSH key info: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/ssh-key", response_model=ApiResponse)
async def delete_ssh_key(db: Session = Depends(get_db)):
    """
    Delete the currently configured SSH key file.

    Removes the file from storage and clears the ssh_key_path setting.
    """
    try:
        settings_service = get_settings_service(db)
        ssh_key_path = settings_service.get_setting("ssh_key_path")

        if not ssh_key_path:
            raise HTTPException(
                status_code=404,
                detail="No SSH key configured"
            )

        # Delete the file if it exists
        if os.path.exists(ssh_key_path):
            os.remove(ssh_key_path)
            logger.info(f"Deleted SSH key file: {ssh_key_path}")

        # Clear the setting
        settings_service.set_setting("ssh_key_path", None)

        return ApiResponse(
            success=True,
            message="SSH key deleted successfully",
            data=None
        )

    except Exception as e:
        logger.error(f"Error deleting SSH key: {e}")
        raise HTTPException(status_code=500, detail=str(e))

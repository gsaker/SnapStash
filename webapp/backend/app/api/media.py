import os
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import get_db
from ..services.storage import StorageService
from ..schemas import MediaAssetResponse, PaginationMeta

router = APIRouter(prefix="/api/media", tags=["media"])


class MediaListResponse(BaseModel):
    media: List[MediaAssetResponse]
    pagination: PaginationMeta


@router.get("", response_model=MediaListResponse)
async def get_media_assets(
    sender_id: Optional[str] = Query(None, description="Filter by sender ID"),
    file_type: Optional[str] = Query(None, description="Filter by file type (image, video, audio)"),
    cache_id: Optional[str] = Query(None, description="Filter by cache ID"),
    category: Optional[str] = Query(None, description="Filter by category"),
    limit: int = Query(50, ge=1, le=500, description="Number of media items to return"),
    offset: int = Query(0, ge=0, description="Number of media items to skip"),
    db: Session = Depends(get_db)
):
    """Get media assets with optional filtering and pagination."""
    storage_service = StorageService(db)
    
    if sender_id:
        media_assets = storage_service.get_media_assets_by_sender(
            sender_id=sender_id,
            file_type=file_type,
            limit=limit,
            offset=offset
        )
    elif cache_id:
        media_assets = storage_service.get_media_assets_by_cache_id(cache_id)
        # Apply additional filters
        if file_type:
            media_assets = [ma for ma in media_assets if ma.file_type == file_type]
        if category:
            media_assets = [ma for ma in media_assets if ma.category == category]
        # Apply pagination
        media_assets = media_assets[offset:offset + limit]
    else:
        # Get all media with filters
        media_assets = storage_service.get_media_assets_with_filters(
            file_type=file_type,
            category=category,
            limit=limit,
            offset=offset
        )
    
    # Get total count for pagination
    total_count = len(media_assets)
    
    return MediaListResponse(
        media=[
            MediaAssetResponse(
                id=asset.id,
                file_path=asset.file_path,
                file_hash=asset.file_hash,
                file_size=asset.file_size,
                file_type=asset.file_type,
                mime_type=asset.mime_type,
                cache_key=asset.cache_key,
                cache_id=asset.cache_id,
                sender_id=asset.sender_id,
                category=asset.category,
                timestamp_source=asset.timestamp_source,
                mapping_method=asset.mapping_method,
                file_timestamp=asset.file_timestamp,
                created_at=asset.created_at,
                updated_at=asset.updated_at
            )
            for asset in media_assets
        ],
        pagination=PaginationMeta(
            total=total_count,
            limit=limit,
            offset=offset,
            has_next=total_count == limit,
            has_prev=offset > 0
        )
    )


@router.get("/{media_id}")
async def get_media_asset(
    media_id: int,
    db: Session = Depends(get_db)
):
    """Get detailed information about a specific media asset."""
    storage_service = StorageService(db)
    
    media_asset = storage_service.get_media_asset_by_id(media_id)
    if not media_asset:
        raise HTTPException(status_code=404, detail="Media asset not found")
    
    response_data = {
        "id": media_asset.id,
        "file_path": media_asset.file_path,
        "file_hash": media_asset.file_hash,
        "file_size": media_asset.file_size,
        "file_type": media_asset.file_type,
        "mime_type": media_asset.mime_type,
        "cache_key": media_asset.cache_key,
        "cache_id": media_asset.cache_id,
        "sender_id": media_asset.sender_id,
        "category": media_asset.category,
        "timestamp_source": media_asset.timestamp_source,
        "mapping_method": media_asset.mapping_method,
        "file_timestamp": media_asset.file_timestamp,
        "created_at": media_asset.created_at,
        "updated_at": media_asset.updated_at
    }
    
    # Include sender info if available
    if media_asset.sender:
        response_data["sender"] = {
            "id": media_asset.sender.id,
            "username": media_asset.sender.username,
            "display_name": media_asset.sender.display_name
        }
    
    return response_data


@router.get("/{media_id}/file")
async def serve_media_file(
    media_id: int,
    db: Session = Depends(get_db)
):
    """Serve the actual media file for download or viewing."""
    storage_service = StorageService(db)
    
    media_asset = storage_service.get_media_asset_by_id(media_id)
    if not media_asset:
        raise HTTPException(status_code=404, detail="Media asset not found")
    
    # Build full file path - handle both relative and absolute paths
    if media_asset.file_path.startswith("/app/"):
        full_file_path = media_asset.file_path
    elif media_asset.file_path.startswith("data/"):
        full_file_path = f"/app/{media_asset.file_path}"
    elif media_asset.file_path.startswith("com.snapchat.android/"):
        # Handle legacy Android file paths - check if file exists in extraction directory
        # For backward compatibility with files that have Android paths in database
        full_file_path = f"/app/{media_asset.file_path}"
        if not os.path.exists(full_file_path):
            # Try to find the file in media_storage based on original_filename
            import hashlib
            from pathlib import Path
            
            # Try to find the file in media_storage/shared/ by filename
            if media_asset.original_filename:
                # Try exact filename first
                media_storage_path = Path("/app/data/media_storage/shared") / media_asset.original_filename
                if media_storage_path.exists():
                    full_file_path = str(media_storage_path)
                else:
                    # Try with common extensions if original has no extension
                    if not Path(media_asset.original_filename).suffix:
                        for ext in ['.jpg', '.png', '.mp4', '.webp']:
                            test_path = Path("/app/data/media_storage/shared") / f"{media_asset.original_filename}{ext}"
                            if test_path.exists():
                                full_file_path = str(test_path)
                                break
    else:
        # Legacy relative paths - construct full path
        full_file_path = f"/app/data/{media_asset.file_path}"
    
    # Check if file exists on disk
    if not os.path.exists(full_file_path):
        raise HTTPException(
            status_code=404, 
            detail=f"Media file not found on disk: {full_file_path}"
        )
    
    # Determine filename for download
    filename = os.path.basename(full_file_path)
    
    # Return file response with appropriate media type
    return FileResponse(
        path=full_file_path,
        media_type=media_asset.mime_type or "application/octet-stream",
        filename=filename
    )


@router.get("/by-cache/{cache_id}")
async def get_media_by_cache_id(
    cache_id: str,
    db: Session = Depends(get_db)
):
    """Get media assets by cache ID."""
    storage_service = StorageService(db)
    
    media_assets = storage_service.get_media_assets_by_cache_id(cache_id)
    if not media_assets:
        raise HTTPException(status_code=404, detail="No media found for this cache ID")
    
    return [
        {
            "id": asset.id,
            "file_path": asset.file_path,
            "file_hash": asset.file_hash,
            "file_size": asset.file_size,
            "file_type": asset.file_type,
            "mime_type": asset.mime_type,
            "cache_key": asset.cache_key,
            "cache_id": asset.cache_id,
            "sender_id": asset.sender_id,
            "category": asset.category,
            "created_at": asset.created_at
        }
        for asset in media_assets
    ]


@router.get("/stats/summary")
async def get_media_stats(
    sender_id: Optional[str] = Query(None),
    file_type: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    """Get media statistics and counts."""
    storage_service = StorageService(db)
    
    if sender_id:
        stats = storage_service.get_media_stats_by_sender(sender_id, file_type)
    else:
        stats = storage_service.get_media_stats(file_type)
    
    return stats


@router.post("/fix-missing-links")
async def fix_missing_media_links(db: Session = Depends(get_db)):
    """Fix messages that have cache_ids matching media assets but missing media_asset_id links."""
    storage_service = StorageService(db)
    results = storage_service.fix_missing_media_links()
    return {
        "success": True,
        "message": f"Fixed {results['links_created']} missing media links",
        "details": results
    }
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import get_db
from ..services.storage import StorageService
from ..schemas import MessageResponse, PaginationMeta

router = APIRouter(prefix="/api/messages", tags=["messages"])


class MessageListResponse(BaseModel):
    messages: List[dict]  # Use dict to allow flexible structure with relationships
    pagination: PaginationMeta


@router.get("", response_model=MessageListResponse)
async def get_messages(
    conversation_id: Optional[str] = Query(None, description="Filter by conversation ID"),
    sender_id: Optional[str] = Query(None, description="Filter by sender ID"),
    since: Optional[datetime] = Query(None, description="Get messages after this timestamp"),
    until: Optional[datetime] = Query(None, description="Get messages before this timestamp"),
    content_type: Optional[int] = Query(None, description="Filter by content type (0=media, 1=text, 2=mixed)"),
    has_media: Optional[bool] = Query(None, description="Filter messages with/without media"),
    limit: int = Query(50, ge=1, le=1000, description="Number of messages to return"),
    offset: int = Query(0, ge=0, description="Number of messages to skip"),
    db: Session = Depends(get_db)
):
    """Get messages with optional filtering and pagination."""
    storage_service = StorageService(db)
    
    # Convert datetime parameters to milliseconds if provided
    since_ms = int(since.timestamp() * 1000) if since else None
    until_ms = int(until.timestamp() * 1000) if until else None
    
    if conversation_id:
        messages = storage_service.get_messages_by_conversation(
            conversation_id=conversation_id,
            since_timestamp=since_ms,
            until_timestamp=until_ms,
            content_type=content_type,
            has_media=has_media,
            limit=limit,
            offset=offset
        )
    elif sender_id:
        messages = storage_service.get_messages_by_sender(
            sender_id=sender_id,
            since_timestamp=since_ms,
            until_timestamp=until_ms,
            content_type=content_type,
            has_media=has_media,
            limit=limit,
            offset=offset
        )
    else:
        # Get all messages with filtering
        messages = storage_service.get_messages_with_filters(
            since_timestamp=since_ms,
            until_timestamp=until_ms,
            content_type=content_type,
            has_media=has_media,
            limit=limit,
            offset=offset
        )
    
    # Get total count for pagination
    total_count = len(messages)  # This is simplified - in production we'd do a separate count query
    
    return MessageListResponse(
        messages=[
            {
                "id": msg.id,
                "text": msg.text,
                "content_type": msg.content_type,
                "creation_timestamp": msg.creation_timestamp,
                "read_timestamp": msg.read_timestamp,
                "sender_id": msg.sender_id,
                "conversation_id": msg.conversation_id,
                "cache_id": msg.cache_id,
                "media_asset_id": msg.media_asset_id,
                "parsing_successful": msg.parsing_successful,
                "raw_message_content": msg.raw_message_content,
                "created_at": msg.created_at,
                "updated_at": msg.updated_at,
                "sender": {
                    "id": msg.sender.id,
                    "username": msg.sender.username,
                    "display_name": msg.sender.display_name
                } if msg.sender else None,
                "media_asset": {
                    "id": msg.media_asset.id,
                    "file_path": msg.media_asset.file_path,
                    "file_hash": msg.media_asset.file_hash,
                    "file_size": msg.media_asset.file_size,
                    "file_type": msg.media_asset.file_type,
                    "mime_type": msg.media_asset.mime_type,
                    "cache_key": msg.media_asset.cache_key,
                    "cache_id": msg.media_asset.cache_id,
                    "category": msg.media_asset.category,
                    "created_at": msg.media_asset.created_at
                } if msg.media_asset else None
            }
            for msg in messages
        ],
        pagination=PaginationMeta(
            total=total_count,
            limit=limit,
            offset=offset,
            has_next=total_count == limit,  # Simplified check
            has_prev=offset > 0
        )
    )


@router.get("/{message_id}")
async def get_message(
    message_id: int,
    db: Session = Depends(get_db)
):
    """Get a specific message by ID."""
    storage_service = StorageService(db)
    
    message = storage_service.get_message_by_id(message_id)
    if not message:
        raise HTTPException(status_code=404, detail="Message not found")
    
    response_data = {
        "id": message.id,
        "text": message.text,
        "content_type": message.content_type,
        "creation_timestamp": message.creation_timestamp,
        "read_timestamp": message.read_timestamp,
        "sender_id": message.sender_id,
        "conversation_id": message.conversation_id,
        "cache_id": message.cache_id,
        "media_asset_id": message.media_asset_id,
        "parsing_successful": message.parsing_successful,
        "raw_message_content": message.raw_message_content,
        "created_at": message.created_at,
        "updated_at": message.updated_at
    }
    
    # Include media asset if linked
    if message.media_asset:
        response_data["media_asset"] = {
            "id": message.media_asset.id,
            "file_path": message.media_asset.file_path,
            "file_hash": message.media_asset.file_hash,
            "file_size": message.media_asset.file_size,
            "file_type": message.media_asset.file_type,
            "mime_type": message.media_asset.mime_type,
            "cache_key": message.media_asset.cache_key,
            "cache_id": message.media_asset.cache_id,
            "category": message.media_asset.category,
            "created_at": message.media_asset.created_at
        }
    
    # Include sender info if available
    if message.sender:
        response_data["sender"] = {
            "id": message.sender.id,
            "username": message.sender.username,
            "display_name": message.sender.display_name
        }
    
    return response_data


@router.get("/stats/summary")
async def get_message_stats(
    conversation_id: Optional[str] = Query(None),
    sender_id: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    """Get message statistics and counts."""
    storage_service = StorageService(db)

    if conversation_id:
        stats = storage_service.get_message_stats_by_conversation(conversation_id)
    elif sender_id:
        stats = storage_service.get_message_stats_by_sender(sender_id)
    else:
        stats = storage_service.get_message_stats()

    return stats


@router.post("/repair/broken-text")
async def repair_broken_text_messages(
    db: Session = Depends(get_db)
):
    """
    Repair broken text messages that have raw_message_content but missing text field.
    This fixes messages that were broken by previous imports that overwrote text with None.
    """
    storage_service = StorageService(db)

    try:
        results = storage_service.reparse_broken_text_messages()
        return {
            "success": True,
            "message": f"Repaired {results['messages_repaired']} out of {results['messages_checked']} broken messages",
            "details": results
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to repair messages: {str(e)}")
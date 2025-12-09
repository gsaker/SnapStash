from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import get_db
from ..services.storage import StorageService
from ..schemas import ConversationResponse, PaginationMeta, LastMessagePreview
from ..config import get_runtime_dm_exclude_name

router = APIRouter(prefix="/api/conversations", tags=["conversations"])


def apply_dm_exclude_name(conversation_name: Optional[str], is_group_chat: bool) -> Optional[str]:
    """
    Apply dm_exclude_name filter to conversation names.
    For DM conversations, removes the excluded name from the conversation title.
    """
    if not conversation_name or is_group_chat:
        return conversation_name

    exclude_name = get_runtime_dm_exclude_name()
    if not exclude_name:
        return conversation_name

    # Split by common separators: " and ", " & "
    if " and " in conversation_name:
        parts = [p.strip() for p in conversation_name.split(" and ")]
    elif " & " in conversation_name:
        parts = [p.strip() for p in conversation_name.split(" & ")]
    else:
        # Single name or unrecognized format
        return conversation_name

    # Filter out the excluded name
    filtered_parts = [p for p in parts if p != exclude_name]

    # Return the filtered result
    if len(filtered_parts) == 1:
        return filtered_parts[0]
    elif len(filtered_parts) > 1:
        return " & ".join(filtered_parts)
    else:
        # All names were excluded (shouldn't happen normally)
        return conversation_name


class ConversationWithPreview(BaseModel):
    id: str
    group_name: Optional[str] = None
    is_group_chat: bool = False
    participant_count: Optional[int] = None
    last_message_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    last_message_preview: Optional[LastMessagePreview] = None


class ConversationListResponse(BaseModel):
    conversations: List[ConversationWithPreview]
    pagination: PaginationMeta


@router.get("", response_model=ConversationListResponse)
async def get_conversations(
    limit: int = Query(50, ge=1, le=500, description="Number of conversations to return"),
    offset: int = Query(0, ge=0, description="Number of conversations to skip"),
    exclude_ads: bool = Query(False, description="Exclude conversations that appear to be ads (one-sided non-group chats)"),
    db: Session = Depends(get_db)
):
    """Get conversations with pagination, ordered by last message."""
    storage_service = StorageService(db)
    
    conversations = storage_service.get_conversations(
        limit=limit,
        offset=offset,
        exclude_ads=exclude_ads
    )
    
    # Get total count for pagination
    total_count = len(conversations)
    
    # Build response with last message preview
    conversation_responses = []
    for conv in conversations:
        # Get the last message for this conversation
        last_messages = storage_service.get_messages_by_conversation(
            conversation_id=conv.id,
            limit=1
        )
        
        last_message_preview = None
        if last_messages:
            msg = last_messages[0]
            media_type = None
            has_media = msg.media_asset_id is not None
            
            if has_media and msg.media_asset:
                asset = msg.media_asset
                if asset.file_type:
                    ft = asset.file_type.lower()
                    if ft == 'image' or (asset.mime_type and asset.mime_type.startswith('image/')):
                        media_type = 'image'
                    elif ft == 'video' or (asset.mime_type and asset.mime_type.startswith('video/')):
                        media_type = 'video'
                    elif ft == 'audio' or (asset.mime_type and asset.mime_type.startswith('audio/')):
                        media_type = 'audio'
            
            last_message_preview = LastMessagePreview(
                text=msg.text,
                has_media=has_media,
                media_type=media_type,
                sender_name=msg.sender.display_name if msg.sender else None,
                timestamp=msg.creation_timestamp
            )
        
        conversation_responses.append(
            ConversationWithPreview(
                id=conv.id,
                group_name=apply_dm_exclude_name(conv.group_name, conv.is_group_chat),
                is_group_chat=conv.is_group_chat,
                participant_count=conv.participant_count,
                last_message_at=conv.last_message_at,
                created_at=conv.created_at,
                updated_at=conv.updated_at,
                last_message_preview=last_message_preview
            )
        )
    
    return ConversationListResponse(
        conversations=conversation_responses,
        pagination=PaginationMeta(
            total=total_count,
            limit=limit,
            offset=offset,
            has_next=total_count == limit,
            has_prev=offset > 0
        )
    )


@router.get("/{conversation_id}")
async def get_conversation(
    conversation_id: str,
    include_messages: bool = Query(False, description="Include recent messages in response"),
    message_limit: int = Query(20, ge=1, le=100, description="Limit for recent messages"),
    db: Session = Depends(get_db)
):
    """Get detailed information about a specific conversation."""
    storage_service = StorageService(db)
    
    conversation = storage_service.get_conversation_by_id(conversation_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    
    response_data = {
        "id": conversation.id,
        "group_name": apply_dm_exclude_name(conversation.group_name, conversation.is_group_chat),
        "is_group_chat": conversation.is_group_chat,
        "participant_count": conversation.participant_count,
        "last_message_at": conversation.last_message_at,
        "created_at": conversation.created_at,
        "updated_at": conversation.updated_at
    }
    
    # Include recent messages if requested
    if include_messages:
        messages = storage_service.get_messages_by_conversation(
            conversation_id,
            limit=message_limit
        )
        response_data["recent_messages"] = [
            {
                "id": msg.id,
                "text": msg.text,
                "content_type": msg.content_type,
                "creation_timestamp": msg.creation_timestamp,
                "sender_id": msg.sender_id,
                "media_asset_id": msg.media_asset_id,
                "parsing_successful": msg.parsing_successful
            }
            for msg in messages
        ]
    
    # Get conversation statistics
    stats = storage_service.get_message_stats_by_conversation(conversation_id)
    response_data["statistics"] = stats
    
    return response_data


@router.get("/{conversation_id}/participants")
async def get_conversation_participants(
    conversation_id: str,
    db: Session = Depends(get_db)
):
    """Get all participants (senders) in a conversation."""
    storage_service = StorageService(db)
    
    # Check if conversation exists
    conversation = storage_service.get_conversation_by_id(conversation_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    
    # Get unique participants from messages
    participants = storage_service.get_conversation_participants(conversation_id)
    
    return {
        "conversation_id": conversation_id,
        "participants": [
            {
                "id": user.id,
                "username": user.username,
                "display_name": user.display_name,
                "message_count": participant_stats.get("message_count", 0)
            }
            for user, participant_stats in participants
        ]
    }


@router.get("/{conversation_id}/stats")
async def get_conversation_statistics(
    conversation_id: str,
    db: Session = Depends(get_db)
):
    """Get detailed statistics for a conversation."""
    storage_service = StorageService(db)
    
    # Check if conversation exists
    conversation = storage_service.get_conversation_by_id(conversation_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    
    # Get message statistics
    message_stats = storage_service.get_message_stats_by_conversation(conversation_id)
    
    # Get media statistics for this conversation
    media_stats = storage_service.get_conversation_media_stats(conversation_id)
    
    return {
        "conversation_id": conversation_id,
        "messages": message_stats,
        "media": media_stats,
        "last_updated": conversation.last_message_at
    }
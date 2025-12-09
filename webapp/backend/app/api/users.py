from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import get_db
from ..services.storage import StorageService
from ..schemas import UserResponse, PaginationMeta
from ..config import get_runtime_dm_exclude_name

router = APIRouter(prefix="/api/users", tags=["users"])


def apply_dm_exclude_name_to_conversation(conversation_name: Optional[str], is_group_chat: bool) -> Optional[str]:
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


class UserListResponse(BaseModel):
    users: List[UserResponse]
    pagination: PaginationMeta


@router.get("/current")
async def get_current_user(db: Session = Depends(get_db)):
    """Get the current user (device owner) based on configuration."""
    # Get DM exclude name from database settings or environment
    dm_exclude_name = get_runtime_dm_exclude_name()
    storage_service = StorageService(db)

    if not dm_exclude_name:
        raise HTTPException(
            status_code=404,
            detail="Current user not configured. Set DM_EXCLUDE_NAME in settings."
        )

    # Find user by display name matching DM_EXCLUDE_NAME
    users = storage_service.search_users(dm_exclude_name, limit=10)

    # Look for exact match
    current_user = None
    for user in users:
        if (user.display_name == dm_exclude_name or
            user.username == dm_exclude_name):
            current_user = user
            break

    if not current_user and users:
        # If no exact match, use the first result as a fallback
        current_user = users[0]

    if not current_user:
        raise HTTPException(
            status_code=404,
            detail=f"User with name '{dm_exclude_name}' not found in database"
        )

    return {
        "id": current_user.id,
        "username": current_user.username,
        "display_name": current_user.display_name,
        "created_at": current_user.created_at,
        "updated_at": current_user.updated_at,
        "is_current_user": True
    }


@router.get("", response_model=UserListResponse)
async def get_users(
    search: Optional[str] = Query(None, description="Search by username or display name"),
    limit: int = Query(50, ge=1, le=500, description="Number of users to return"),
    offset: int = Query(0, ge=0, description="Number of users to skip"),
    db: Session = Depends(get_db)
):
    """Get users with optional search and pagination."""
    storage_service = StorageService(db)
    
    if search:
        users = storage_service.search_users(search, limit=limit, offset=offset)
    else:
        users = storage_service.get_users(limit=limit, offset=offset)
    
    # Get total count for pagination
    total_count = len(users)
    
    return UserListResponse(
        users=[
            UserResponse(
                id=user.id,
                username=user.username,
                display_name=user.display_name,
                created_at=user.created_at,
                updated_at=user.updated_at
            )
            for user in users
        ],
        pagination=PaginationMeta(
            total=total_count,
            limit=limit,
            offset=offset,
            has_next=total_count == limit,
            has_prev=offset > 0
        )
    )


@router.get("/{user_id}")
async def get_user(
    user_id: str,
    include_stats: bool = Query(True, description="Include user statistics"),
    db: Session = Depends(get_db)
):
    """Get detailed information about a specific user."""
    storage_service = StorageService(db)
    
    user = storage_service.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    response_data = {
        "id": user.id,
        "username": user.username,
        "display_name": user.display_name,
        "created_at": user.created_at,
        "updated_at": user.updated_at
    }
    
    # Include statistics if requested
    if include_stats:
        message_stats = storage_service.get_message_stats_by_sender(user_id)
        media_stats = storage_service.get_media_stats_by_sender(user_id)
        
        response_data["statistics"] = {
            "messages": message_stats,
            "media": media_stats
        }
    
    return response_data


@router.get("/{user_id}/conversations")
async def get_user_conversations(
    user_id: str,
    limit: int = Query(20, ge=1, le=100, description="Number of conversations to return"),
    db: Session = Depends(get_db)
):
    """Get conversations that a user has participated in."""
    storage_service = StorageService(db)
    
    # Check if user exists
    user = storage_service.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Get conversations for this user
    conversations = storage_service.get_user_conversations(user_id, limit=limit)
    
    return {
        "user_id": user_id,
        "conversations": [
            {
                "id": conv.id,
                "group_name": apply_dm_exclude_name_to_conversation(conv.group_name, conv.is_group_chat),
                "is_group_chat": conv.is_group_chat,
                "participant_count": conv.participant_count,
                "last_message_at": conv.last_message_at,
                "message_count": conv_stats.get("message_count", 0),
                "media_count": conv_stats.get("media_count", 0)
            }
            for conv, conv_stats in conversations
        ]
    }


@router.get("/{user_id}/activity")
async def get_user_activity(
    user_id: str,
    days: int = Query(30, ge=1, le=365, description="Number of days to analyze"),
    db: Session = Depends(get_db)
):
    """Get user activity statistics over time."""
    storage_service = StorageService(db)
    
    # Check if user exists
    user = storage_service.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Get activity data
    activity = storage_service.get_user_activity(user_id, days=days)
    
    return {
        "user_id": user_id,
        "period_days": days,
        "activity": activity
    }
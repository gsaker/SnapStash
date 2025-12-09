from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload

from ..database import get_db
from ..models import Message, User, Conversation
from ..schemas import PaginationMeta

router = APIRouter(prefix="/api/search", tags=["search"])


class SearchResultMessage(BaseModel):
    id: int
    text: Optional[str]
    content_type: int
    creation_timestamp: int
    read_timestamp: Optional[int]
    sender_id: str
    conversation_id: str
    media_asset_id: Optional[int]
    sender: Optional[dict]
    conversation: Optional[dict]
    
    class Config:
        from_attributes = True


class SearchResponse(BaseModel):
    query: str
    results: List[SearchResultMessage]
    pagination: PaginationMeta


@router.get("", response_model=SearchResponse)
async def search_messages(
    q: str = Query(..., min_length=1, description="Search query text"),
    sender_id: Optional[str] = Query(None, description="Filter by sender ID"),
    conversation_id: Optional[str] = Query(None, description="Filter by conversation ID"),
    since: Optional[datetime] = Query(None, description="Search messages after this timestamp"),
    until: Optional[datetime] = Query(None, description="Search messages before this timestamp"),
    limit: int = Query(50, ge=1, le=500, description="Number of results to return"),
    offset: int = Query(0, ge=0, description="Number of results to skip"),
    db: Session = Depends(get_db)
):
    """
    Search through messages for text content.
    
    - **q**: The search query (required, searches message text)
    - **sender_id**: Optional filter by sender
    - **conversation_id**: Optional filter by conversation
    - **since**: Optional filter for messages after this datetime
    - **until**: Optional filter for messages before this datetime
    - **limit**: Maximum number of results (default 50, max 500)
    - **offset**: Pagination offset
    """
    # Build base query with eager loading
    query = db.query(Message).options(
        joinedload(Message.sender),
        joinedload(Message.conversation)
    )
    
    # Search in message text (case-insensitive)
    query = query.filter(Message.text.ilike(f"%{q}%"))
    
    # Apply optional filters
    if sender_id:
        query = query.filter(Message.sender_id == sender_id)
    
    if conversation_id:
        query = query.filter(Message.conversation_id == conversation_id)
    
    if since:
        since_ms = int(since.timestamp() * 1000)
        query = query.filter(Message.creation_timestamp >= since_ms)
    
    if until:
        until_ms = int(until.timestamp() * 1000)
        query = query.filter(Message.creation_timestamp <= until_ms)
    
    # Get total count before pagination
    total_count = query.count()
    
    # Apply ordering (most recent first) and pagination
    query = query.order_by(Message.creation_timestamp.desc())
    query = query.offset(offset).limit(limit)
    
    messages = query.all()
    
    # Build response
    results = []
    for msg in messages:
        results.append(SearchResultMessage(
            id=msg.id,
            text=msg.text,
            content_type=msg.content_type,
            creation_timestamp=msg.creation_timestamp,
            read_timestamp=msg.read_timestamp,
            sender_id=msg.sender_id,
            conversation_id=msg.conversation_id,
            media_asset_id=msg.media_asset_id,
            sender={
                "id": msg.sender.id,
                "username": msg.sender.username,
                "display_name": msg.sender.display_name
            } if msg.sender else None,
            conversation={
                "id": msg.conversation.id,
                "group_name": msg.conversation.group_name,
                "is_group_chat": msg.conversation.is_group_chat
            } if msg.conversation else None
        ))
    
    return SearchResponse(
        query=q,
        results=results,
        pagination=PaginationMeta(
            total=total_count,
            limit=limit,
            offset=offset,
            has_next=offset + len(results) < total_count,
            has_prev=offset > 0
        )
    )

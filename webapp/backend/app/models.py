from datetime import datetime
from enum import Enum
from typing import Optional

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    BigInteger,
    JSON,
    Index,
)
from sqlalchemy.orm import relationship

from .database import Base


class User(Base):
    """Snapchat friend/user model"""
    
    __tablename__ = "users"

    id = Column(String, primary_key=True)  # sender_id from Snapchat
    username = Column(String, unique=True, nullable=False)
    display_name = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    sent_messages = relationship("Message", foreign_keys="Message.sender_id", back_populates="sender")
    media_assets = relationship("MediaAsset", back_populates="sender")


class Conversation(Base):
    """Snapchat conversation model"""
    
    __tablename__ = "conversations"

    id = Column(String, primary_key=True)  # client_conversation_id
    
    # Group chat fields (null for individual DMs)
    group_name = Column(String, nullable=True)  # Group name from protobuf
    is_group_chat = Column(Boolean, default=False)  # True if >2 participants
    participant_count = Column(Integer, nullable=True)  # Number of participants
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_message_at = Column(DateTime, nullable=True)

    # Relationships
    messages = relationship("Message", back_populates="conversation", cascade="all, delete-orphan")
    participants = relationship("ConversationParticipant", back_populates="conversation", cascade="all, delete-orphan")


class Message(Base):
    """Unified message model for text and media"""
    
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    server_message_id = Column(String, nullable=True)
    client_message_id = Column(String, nullable=True)
    
    # Foreign keys
    sender_id = Column(String, ForeignKey("users.id"), nullable=False)
    conversation_id = Column(String, ForeignKey("conversations.id"), nullable=False)
    media_asset_id = Column(Integer, ForeignKey("media_assets.id"), nullable=True)
    
    # Message content
    text = Column(Text, nullable=True)  # Text content from protobuf
    content_type = Column(Integer, nullable=False)  # 0=media, 1=text, 2=mixed
    cache_id = Column(String, nullable=True)  # media_cache_id from protobuf
    
    # Timestamps (stored as milliseconds, same as Snapchat)
    creation_timestamp = Column(BigInteger, nullable=False)
    read_timestamp = Column(BigInteger, nullable=True)
    
    # Parsing metadata
    parsing_successful = Column(Boolean, default=False)
    raw_message_content = Column(Text, nullable=True)  # base64 encoded protobuf
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    sender = relationship("User", foreign_keys=[sender_id], back_populates="sent_messages")
    conversation = relationship("Conversation", back_populates="messages")
    media_asset = relationship("MediaAsset", back_populates="message")

    # Indexes for performance
    __table_args__ = (
        Index("idx_messages_conversation_timestamp", "conversation_id", "creation_timestamp"),
        Index("idx_messages_sender_timestamp", "sender_id", "creation_timestamp"),
        Index("idx_messages_cache_id", "cache_id"),
        Index("idx_messages_raw_content", "raw_message_content"),  # For deduplication
    )


class MediaAsset(Base):
    """Media files associated with messages"""
    
    __tablename__ = "media_assets"

    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # Foreign keys
    sender_id = Column(String, ForeignKey("users.id"), nullable=False)
    
    # File information
    original_filename = Column(String, nullable=True)
    file_path = Column(String, nullable=False)  # Path to stored file
    file_hash = Column(String, nullable=True)
    file_size = Column(BigInteger, nullable=True)
    file_type = Column(String, nullable=True)  # image, video, etc.
    mime_type = Column(String, nullable=True)
    
    # Snapchat-specific identifiers
    cache_key = Column(String, nullable=True)
    cache_id = Column(String, nullable=True)
    
    # Metadata
    category = Column(String, nullable=True)  # chat_snap, snap, etc.
    timestamp_source = Column(String, nullable=True)  # exif, filename, db
    mapping_method = Column(String, nullable=True)  # How file was mapped to sender
    
    # Timestamps
    file_timestamp = Column(DateTime, nullable=True)  # From EXIF or filename
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    sender = relationship("User", back_populates="media_assets")
    message = relationship("Message", back_populates="media_asset")

    # Indexes
    __table_args__ = (
        Index("idx_media_sender", "sender_id"),
        Index("idx_media_cache_key", "cache_key"),
        Index("idx_media_cache_id", "cache_id"),
        Index("idx_media_file_hash", "file_hash"),
    )


class Device(Base):
    """Device information for SSH extraction"""
    
    __tablename__ = "devices"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False)
    
    # SSH connection details
    ssh_host = Column(String, nullable=False)
    ssh_port = Column(Integer, default=22)
    ssh_user = Column(String, nullable=False)
    ssh_key_path = Column(String, nullable=True)
    
    # Device metadata
    android_version = Column(String, nullable=True)
    snapchat_version = Column(String, nullable=True)
    last_seen = Column(DateTime, nullable=True)
    
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    ingest_runs = relationship("IngestRun", back_populates="device", cascade="all, delete-orphan")


class IngestRun(Base):
    """Tracks data extraction runs"""
    
    __tablename__ = "ingest_runs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # Foreign keys
    device_id = Column(Integer, ForeignKey("devices.id"), nullable=False)
    
    # Run details
    status = Column(String, nullable=False)  # pending, running, completed, failed
    extraction_type = Column(String, nullable=False)  # database, media, full
    
    # Timestamps
    started_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
    
    # Results
    messages_extracted = Column(Integer, default=0)
    media_files_extracted = Column(Integer, default=0)
    parsing_errors = Column(Integer, default=0)
    
    # Error information
    error_message = Column(Text, nullable=True)
    error_details = Column(JSON, nullable=True)
    
    # Metadata
    extraction_settings = Column(JSON, nullable=True)  # Config used for this run
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    device = relationship("Device", back_populates="ingest_runs")

    # Indexes
    __table_args__ = (
        Index("idx_ingest_runs_device_started", "device_id", "started_at"),
        Index("idx_ingest_runs_status", "status"),
    )


class ConversationParticipant(Base):
    """Links users to conversations (for group chats)"""

    __tablename__ = "conversation_participants"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # Foreign keys
    conversation_id = Column(String, ForeignKey("conversations.id"), nullable=False)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)

    # Participant metadata from protobuf
    join_timestamp = Column(BigInteger, nullable=True)  # When they joined (from protobuf)
    unknown_field_2 = Column(BigInteger, nullable=True)  # Unknown protobuf field
    unknown_field_3 = Column(BigInteger, nullable=True)  # Unknown protobuf field
    unknown_field_9 = Column(BigInteger, nullable=True)  # Unknown protobuf field

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    conversation = relationship("Conversation", back_populates="participants")
    user = relationship("User")

    # Indexes and constraints
    __table_args__ = (
        Index("idx_conversation_participants_conv", "conversation_id"),
        Index("idx_conversation_participants_user", "user_id"),
    )


class AppSettings(Base):
    """Application settings that can be configured via the frontend"""

    __tablename__ = "app_settings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    key = Column(String, unique=True, nullable=False, index=True)
    value = Column(String, nullable=True)
    value_type = Column(String, nullable=False)  # string, int, bool, float
    description = Column(String, nullable=True)
    category = Column(String, nullable=True)  # ssh, ingest, ui, etc.

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Indexes
    __table_args__ = (
        Index("idx_settings_category", "category"),
    )
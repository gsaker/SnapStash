from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


# User schemas
class UserBase(BaseModel):
    username: str
    display_name: Optional[str] = None
    bitmoji_avatar_id: Optional[str] = None
    bitmoji_selfie_id: Optional[str] = None


class UserCreate(UserBase):
    id: str


class UserUpdate(UserBase):
    username: Optional[str] = None
    display_name: Optional[str] = None
    bitmoji_avatar_id: Optional[str] = None
    bitmoji_selfie_id: Optional[str] = None


class User(UserBase):
    id: str
    created_at: datetime
    updated_at: datetime
    bitmoji_url: Optional[str] = None

    class Config:
        from_attributes = True


# Conversation schemas
class ConversationBase(BaseModel):
    group_name: Optional[str] = None
    is_group_chat: bool = False
    participant_count: Optional[int] = None


class ConversationCreate(ConversationBase):
    id: str


class Conversation(ConversationBase):
    id: str
    group_name: Optional[str] = None
    is_group_chat: bool = False
    participant_count: Optional[int] = None
    created_at: datetime
    updated_at: datetime
    last_message_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# Last message preview for conversation list
class LastMessagePreview(BaseModel):
    text: Optional[str] = None
    has_media: bool = False
    media_type: Optional[str] = None  # 'image', 'video', 'audio'
    sender_name: Optional[str] = None
    timestamp: Optional[int] = None


# MediaAsset schemas
class MediaAssetBase(BaseModel):
    original_filename: Optional[str] = None
    file_path: str
    file_hash: Optional[str] = None
    file_size: Optional[int] = None
    file_type: Optional[str] = None
    mime_type: Optional[str] = None
    cache_key: Optional[str] = None
    cache_id: Optional[str] = None
    category: Optional[str] = None
    timestamp_source: Optional[str] = None
    mapping_method: Optional[str] = None
    file_timestamp: Optional[datetime] = None


class MediaAssetCreate(MediaAssetBase):
    sender_id: str


class MediaAsset(MediaAssetBase):
    id: int
    sender_id: str
    created_at: datetime
    updated_at: datetime
    sender: Optional[User] = None

    class Config:
        from_attributes = True


# Message schemas
class MessageBase(BaseModel):
    text: Optional[str] = None
    content_type: int
    cache_id: Optional[str] = None
    creation_timestamp: int
    read_timestamp: Optional[int] = None
    parsing_successful: bool = False


class MessageCreate(MessageBase):
    sender_id: str
    conversation_id: str
    server_message_id: Optional[str] = None
    client_message_id: Optional[str] = None
    raw_message_content: Optional[str] = None


class MessageUpdate(BaseModel):
    text: Optional[str] = None
    parsing_successful: Optional[bool] = None
    media_asset_id: Optional[int] = None


class Message(MessageBase):
    id: int
    sender_id: str
    conversation_id: str
    server_message_id: Optional[str] = None
    client_message_id: Optional[str] = None
    media_asset_id: Optional[int] = None
    created_at: datetime
    updated_at: datetime
    
    # Related objects
    sender: Optional[User] = None
    media_asset: Optional[MediaAsset] = None

    class Config:
        from_attributes = True


# Device schemas
class DeviceBase(BaseModel):
    name: str
    ssh_host: str
    ssh_port: int = 22
    ssh_user: str
    ssh_key_path: Optional[str] = None
    android_version: Optional[str] = None
    snapchat_version: Optional[str] = None
    is_active: bool = True


class DeviceCreate(DeviceBase):
    pass


class DeviceUpdate(BaseModel):
    name: Optional[str] = None
    ssh_host: Optional[str] = None
    ssh_port: Optional[int] = None
    ssh_user: Optional[str] = None
    ssh_key_path: Optional[str] = None
    android_version: Optional[str] = None
    snapchat_version: Optional[str] = None
    is_active: Optional[bool] = None


class Device(DeviceBase):
    id: int
    last_seen: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# IngestRun schemas
class IngestRunBase(BaseModel):
    extraction_type: str = Field(description="Type of extraction: database, media, or full")
    extraction_settings: Optional[Dict[str, Any]] = None


class IngestRunCreate(IngestRunBase):
    device_id: int


class IngestRunUpdate(BaseModel):
    status: Optional[str] = None
    completed_at: Optional[datetime] = None
    messages_extracted: Optional[int] = None
    media_files_extracted: Optional[int] = None
    parsing_errors: Optional[int] = None
    error_message: Optional[str] = None
    error_details: Optional[Dict[str, Any]] = None


class IngestRun(IngestRunBase):
    id: int
    device_id: int
    status: str
    started_at: datetime
    completed_at: Optional[datetime] = None
    messages_extracted: int = 0
    media_files_extracted: int = 0
    parsing_errors: int = 0
    error_message: Optional[str] = None
    error_details: Optional[Dict[str, Any]] = None
    created_at: datetime
    updated_at: datetime
    
    # Related objects
    device: Optional[Device] = None

    class Config:
        from_attributes = True


# API Response schemas
class ApiResponse(BaseModel):
    success: bool
    message: str
    data: Optional[Any] = None


class PaginationMeta(BaseModel):
    total: int
    limit: int
    offset: int
    has_next: bool
    has_prev: bool


class PaginatedResponse(BaseModel):
    success: bool = True
    data: List[Any]
    meta: PaginationMeta


# Query schemas
class MessageQuery(BaseModel):
    conversation_id: Optional[str] = None
    sender_id: Optional[str] = None
    content_type: Optional[int] = None
    since_timestamp: Optional[int] = None
    until_timestamp: Optional[int] = None
    has_media: Optional[bool] = None
    page: int = 1
    limit: int = Field(default=50, le=100)


class ConversationWithStats(Conversation):
    message_count: int = 0
    media_count: int = 0
    last_sender: Optional[User] = None


# Stats schemas
class SystemStats(BaseModel):
    total_users: int
    total_conversations: int
    total_messages: int
    total_media_assets: int
    total_devices: int
    active_devices: int
    last_ingest_run: Optional[IngestRun] = None
    database_size_mb: Optional[float] = None


# Settings schemas
class AppSettingBase(BaseModel):
    key: str
    value: Optional[str] = None
    value_type: str = Field(description="Type of value: string, int, bool, float")
    description: Optional[str] = None
    category: Optional[str] = None


class AppSettingCreate(AppSettingBase):
    pass


class AppSettingUpdate(BaseModel):
    value: Optional[str] = None
    description: Optional[str] = None


class AppSetting(AppSettingBase):
    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class UserConfigurableSettings(BaseModel):
    """User-facing settings that can be configured via frontend"""
    # SSH Configuration
    ssh_host: Optional[str] = Field(None, description="SSH host for Android device connection")
    ssh_port: int = Field(8022, description="SSH port for device connection")
    ssh_user: str = Field("root", description="SSH username for device connection")
    ssh_key_path: Optional[str] = Field(None, description="Path to SSH private key file")

    # Media extraction
    extract_media: bool = Field(True, description="Enable media file extraction during ingest")

    # Ingestion configuration
    ingest_timeout_seconds: int = Field(300, description="Timeout for individual ingest operations in seconds")
    ingest_mode: str = Field("continuous", description="Ingestion mode: 'continuous' or 'interval'")
    ingest_delay_seconds: int = Field(0, description="Delay after run completion in seconds (continuous mode)")

    # DM naming
    dm_exclude_name: Optional[str] = Field(None, description="Name to exclude from DM conversation titles")

    # Ntfy notifications
    ntfy_enabled: bool = Field(False, description="Enable ntfy notifications")
    ntfy_server_url: str = Field("https://ntfy.sh", description="ntfy server URL")
    ntfy_media_topic: Optional[str] = Field(None, description="ntfy topic for media message notifications")
    ntfy_text_topic: Optional[str] = Field(None, description="ntfy topic for text message notifications")
    ntfy_username: Optional[str] = Field(None, description="ntfy username for basic authentication (optional)")
    ntfy_password: Optional[str] = Field(None, description="ntfy password for basic authentication (optional)")
    ntfy_auth_token: Optional[str] = Field(None, description="ntfy authentication token (optional, alternative to username/password)")
    ntfy_priority: str = Field("default", description="ntfy notification priority (min, low, default, high, urgent)")
    ntfy_attach_media: bool = Field(True, description="Attach media files to notifications")


class SettingsUpdateRequest(BaseModel):
    """Request model for updating multiple settings at once"""
    settings: UserConfigurableSettings


# Response model aliases for API endpoints
MessageResponse = Message
MediaAssetResponse = MediaAsset
ConversationResponse = Conversation
UserResponse = User
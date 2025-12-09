"""
Application Configuration
Centralized configuration management using Pydantic BaseSettings.
"""

import os
from typing import Optional, List
from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables"""
    
    # Database configuration
    database_url: str = Field(
        default="sqlite:///./gz_snapchat.db",
        description="Database URL for SQLite database"
    )
    skip_db_init: bool = Field(
        default=False,
        description="Skip database initialization on startup"
    )
    
    # SSH connection settings
    ssh_host: Optional[str] = Field(
        default=None,
        description="SSH host for Android device connection"
    )
    ssh_user: str = Field(
        default="root",
        description="SSH username for device connection"
    )
    ssh_port: int = Field(
        default=22,
        description="SSH port for device connection"
    )
    ssh_key_path: Optional[str] = Field(
        default=None,
        description="Path to SSH private key file"
    )
    ssh_timeout: int = Field(
        default=300,
        description="SSH operation timeout in seconds"
    )
    
    # Media extraction settings
    extract_media: bool = Field(
        default=True,
        description="Enable media file extraction during ingest"
    )
    media_storage_path: str = Field(
        default="/app/data/media_storage",
        description="Path for permanent media file storage"
    )
    
    # Ingestion loop configuration
    disable_ingest_loop: bool = Field(
        default=False,
        description="Disable automatic ingestion loop"
    )
    ingest_mode: str = Field(
        default="continuous",
        description="Ingestion mode: 'continuous' or 'interval'"
    )
    ingest_interval_minutes: int = Field(
        default=15,
        description="Interval between ingest runs in minutes (interval mode)"
    )
    ingest_delay_seconds: int = Field(
        default=10,
        description="Delay after run completion in seconds (continuous mode)"
    )
    ingest_timeout_seconds: int = Field(
        default=600,
        description="Timeout for individual ingest operations in seconds"
    )
    ingest_max_retries: int = Field(
        default=3,
        description="Maximum retry attempts for failed operations"
    )
    
    # API configuration
    api_host: str = Field(
        default="0.0.0.0",
        description="API server host"
    )
    api_port: int = Field(
        default=8067,
        description="API server port"
    )
    cors_origins: List[str] = Field(
        default=["http://localhost:3067"],
        description="Allowed CORS origins"
    )
    
    # Logging configuration
    log_level: str = Field(
        default="INFO",
        description="Logging level (DEBUG, INFO, WARNING, ERROR)"
    )
    
    # DM naming configuration
    dm_exclude_name: Optional[str] = Field(
        default=None,
        description="Name to exclude from DM conversation titles (e.g., your own name)"
    )
    
    # Application metadata
    app_name: str = Field(
        default="SnapStash Backend",
        description="Application name"
    )
    app_version: str = Field(
        default="0.1.0",
        description="Application version"
    )
    app_env: str = Field(
        default="production",
        description="Application environment (dev, production)"
    )
    
    class Config:
        env_file = ".env"
        env_prefix = ""
        case_sensitive = False
        
        # Environment variable mappings for backwards compatibility
        fields = {
            "database_url": {
                "env": ["DATABASE_URL", "SQLITE_DATABASE_URL"]
            },
            "skip_db_init": {
                "env": ["SKIP_DB_INIT"]
            },
            "ssh_host": {
                "env": ["SSH_HOST"]
            },
            "ssh_user": {
                "env": ["SSH_USER"]
            },
            "ssh_port": {
                "env": ["SSH_PORT"]
            },
            "ssh_key_path": {
                "env": ["SSH_KEY_PATH"]
            },
            "ssh_timeout": {
                "env": ["SSH_TIMEOUT", "TIMEOUT_SECONDS"]
            },
            "extract_media": {
                "env": ["EXTRACT_MEDIA"]
            },
            "media_storage_path": {
                "env": ["MEDIA_STORAGE_PATH"]
            },
            "disable_ingest_loop": {
                "env": ["DISABLE_INGEST_LOOP"]
            },
            "ingest_mode": {
                "env": ["INGEST_MODE"]
            },
            "ingest_interval_minutes": {
                "env": ["INGEST_INTERVAL_MINUTES"]
            },
            "ingest_delay_seconds": {
                "env": ["INGEST_DELAY_SECONDS"]
            },
            "ingest_timeout_seconds": {
                "env": ["INGEST_TIMEOUT_SECONDS"]
            },
            "log_level": {
                "env": ["LOG_LEVEL", "LOGGING_LEVEL"]
            },
            "dm_exclude_name": {
                "env": ["DM_EXCLUDE_NAME"]
            },
            "app_env": {
                "env": ["APP_ENV"]
            },
            "cors_origins": {
                "env": ["CORS_ORIGINS"]
            }
        }


# Global settings instance
settings = Settings()


def get_settings() -> Settings:
    """Get application settings instance"""
    return settings


def get_database_url() -> str:
    """Get database URL with proper formatting"""
    return settings.database_url


def get_async_database_url() -> str:
    """Get async database URL with proper formatting"""
    return settings.database_url.replace("sqlite://", "sqlite+aiosqlite://")


def get_ssh_config() -> dict:
    """Get SSH configuration as dictionary"""
    return {
        "ssh_host": settings.ssh_host,
        "ssh_user": settings.ssh_user,
        "ssh_port": settings.ssh_port,
        "ssh_key_path": settings.ssh_key_path,
        "timeout": settings.ssh_timeout
    }


def get_ingest_config() -> dict:
    """
    Get ingestion configuration as dictionary.

    This function now attempts to get settings from the database first,
    falling back to environment variables if database settings are not available.
    """
    try:
        from .services.settings_service import get_settings_service

        # Try to get settings from database
        settings_service = get_settings_service()
        runtime_settings = settings_service.get_all_settings()

        return {
            "mode": runtime_settings.ingest_mode,
            "interval_minutes": settings.ingest_interval_minutes,  # Not user-configurable
            "delay_between_runs_seconds": runtime_settings.ingest_delay_seconds,
            "timeout_seconds": runtime_settings.ingest_timeout_seconds,
            "max_retries": settings.ingest_max_retries,  # Not user-configurable
            "extract_media": runtime_settings.extract_media,
            "ssh_host": runtime_settings.ssh_host,
            "ssh_user": runtime_settings.ssh_user,
            "ssh_port": runtime_settings.ssh_port,
            "ssh_key_path": runtime_settings.ssh_key_path
        }
    except Exception:
        # Fallback to environment variables if database is not available
        return {
            "mode": settings.ingest_mode,
            "interval_minutes": settings.ingest_interval_minutes,
            "delay_between_runs_seconds": settings.ingest_delay_seconds,
            "timeout_seconds": settings.ingest_timeout_seconds,
            "max_retries": settings.ingest_max_retries,
            "extract_media": settings.extract_media,
            "ssh_host": settings.ssh_host,
            "ssh_user": settings.ssh_user,
            "ssh_port": settings.ssh_port,
            "ssh_key_path": settings.ssh_key_path
        }


def get_runtime_dm_exclude_name() -> Optional[str]:
    """
    Get the DM exclude name from database settings or environment.

    Returns the name to exclude from DM conversation titles.
    """
    try:
        from .services.settings_service import get_settings_service

        settings_service = get_settings_service()
        return settings_service.get_setting("dm_exclude_name")
    except Exception:
        # Fallback to environment variable
        return settings.dm_exclude_name
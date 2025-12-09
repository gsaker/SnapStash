"""
Settings Service
Manages application settings stored in database with fallback to environment variables.
"""

import logging
from typing import Optional, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import select

from ..models import AppSettings
from ..schemas import UserConfigurableSettings
from ..database import SessionLocal

logger = logging.getLogger(__name__)


class SettingsService:
    """Service for managing application settings"""

    # Default values for user-configurable settings
    DEFAULTS = {
        "ssh_host": {"value": None, "type": "string", "category": "ssh", "description": "SSH host for Android device connection"},
        "ssh_port": {"value": "8022", "type": "int", "category": "ssh", "description": "SSH port for device connection"},
        "ssh_user": {"value": "root", "type": "string", "category": "ssh", "description": "SSH username for device connection"},
        "ssh_key_path": {"value": None, "type": "string", "category": "ssh", "description": "Path to SSH private key file"},
        "extract_media": {"value": "true", "type": "bool", "category": "ingest", "description": "Enable media file extraction during ingest"},
        "ingest_timeout_seconds": {"value": "300", "type": "int", "category": "ingest", "description": "Timeout for individual ingest operations in seconds"},
        "ingest_mode": {"value": "continuous", "type": "string", "category": "ingest", "description": "Ingestion mode: 'continuous' or 'interval'"},
        "ingest_delay_seconds": {"value": "0", "type": "int", "category": "ingest", "description": "Delay after run completion in seconds (continuous mode)"},
        "dm_exclude_name": {"value": None, "type": "string", "category": "ui", "description": "Name to exclude from DM conversation titles"},
        "ntfy_enabled": {"value": "false", "type": "bool", "category": "notifications", "description": "Enable ntfy notifications"},
        "ntfy_server_url": {"value": "https://ntfy.sh", "type": "string", "category": "notifications", "description": "ntfy server URL"},
        "ntfy_media_topic": {"value": None, "type": "string", "category": "notifications", "description": "ntfy topic for media message notifications"},
        "ntfy_text_topic": {"value": None, "type": "string", "category": "notifications", "description": "ntfy topic for text message notifications"},
        "ntfy_username": {"value": None, "type": "string", "category": "notifications", "description": "ntfy username for basic authentication (optional)"},
        "ntfy_password": {"value": None, "type": "string", "category": "notifications", "description": "ntfy password for basic authentication (optional)"},
        "ntfy_auth_token": {"value": None, "type": "string", "category": "notifications", "description": "ntfy authentication token (optional, alternative to username/password)"},
        "ntfy_priority": {"value": "default", "type": "string", "category": "notifications", "description": "ntfy notification priority (min, low, default, high, urgent)"},
        "ntfy_attach_media": {"value": "true", "type": "bool", "category": "notifications", "description": "Attach media files to notifications"},
    }

    def __init__(self, db: Optional[Session] = None):
        """Initialize settings service with optional database session"""
        self.db = db
        self._cache: Dict[str, Any] = {}
        self._cache_initialized = False

    def _get_db(self) -> Session:
        """Get database session"""
        if self.db:
            return self.db
        return SessionLocal()

    def _should_close_db(self) -> bool:
        """Check if we should close the database session"""
        return self.db is None

    def _convert_value(self, value: Optional[str], value_type: str) -> Any:
        """Convert string value to appropriate type"""
        if value is None:
            return None

        if value_type == "int":
            return int(value)
        elif value_type == "bool":
            return value.lower() in ("true", "1", "yes", "on")
        elif value_type == "float":
            return float(value)
        else:  # string
            return value

    def _to_string(self, value: Any, value_type: str) -> Optional[str]:
        """Convert value to string for storage"""
        if value is None:
            return None
        if value_type == "bool":
            return "true" if value else "false"
        return str(value)

    def initialize_defaults(self):
        """Initialize database with default settings if they don't exist"""
        db = self._get_db()
        try:
            for key, config in self.DEFAULTS.items():
                # Check if setting exists
                existing = db.query(AppSettings).filter(AppSettings.key == key).first()
                if not existing:
                    # Create with default value
                    setting = AppSettings(
                        key=key,
                        value=config["value"],
                        value_type=config["type"],
                        description=config["description"],
                        category=config["category"]
                    )
                    db.add(setting)
            db.commit()
            logger.info("Initialized default settings in database")
        except Exception as e:
            logger.error(f"Error initializing default settings: {e}")
            db.rollback()
        finally:
            if self._should_close_db():
                db.close()

    def get_setting(self, key: str, default: Any = None) -> Any:
        """Get a single setting value by key"""
        # Check cache first
        if key in self._cache:
            return self._cache[key]

        db = self._get_db()
        try:
            setting = db.query(AppSettings).filter(AppSettings.key == key).first()
            if setting:
                value = self._convert_value(setting.value, setting.value_type)
                self._cache[key] = value
                return value

            # Return default if not found
            if key in self.DEFAULTS:
                default_config = self.DEFAULTS[key]
                value = self._convert_value(default_config["value"], default_config["type"])
                return value

            return default
        finally:
            if self._should_close_db():
                db.close()

    def set_setting(self, key: str, value: Any) -> bool:
        """Set a single setting value"""
        db = self._get_db()
        try:
            setting = db.query(AppSettings).filter(AppSettings.key == key).first()

            # Get value type from defaults or existing setting
            value_type = "string"
            if key in self.DEFAULTS:
                value_type = self.DEFAULTS[key]["type"]
            elif setting:
                value_type = setting.value_type

            value_str = self._to_string(value, value_type)

            if setting:
                setting.value = value_str
            else:
                # Create new setting
                description = self.DEFAULTS.get(key, {}).get("description", "")
                category = self.DEFAULTS.get(key, {}).get("category", "general")
                setting = AppSettings(
                    key=key,
                    value=value_str,
                    value_type=value_type,
                    description=description,
                    category=category
                )
                db.add(setting)

            db.commit()

            # Update cache
            self._cache[key] = value

            logger.info(f"Updated setting {key} = {value}")
            return True
        except Exception as e:
            logger.error(f"Error setting {key}: {e}")
            db.rollback()
            return False
        finally:
            if self._should_close_db():
                db.close()

    def get_all_settings(self) -> UserConfigurableSettings:
        """Get all user-configurable settings as a structured object"""
        return UserConfigurableSettings(
            ssh_host=self.get_setting("ssh_host"),
            ssh_port=self.get_setting("ssh_port", 8022),
            ssh_user=self.get_setting("ssh_user", "root"),
            ssh_key_path=self.get_setting("ssh_key_path"),
            extract_media=self.get_setting("extract_media", True),
            ingest_timeout_seconds=self.get_setting("ingest_timeout_seconds", 300),
            ingest_mode=self.get_setting("ingest_mode", "continuous"),
            ingest_delay_seconds=self.get_setting("ingest_delay_seconds", 0),
            dm_exclude_name=self.get_setting("dm_exclude_name"),
            ntfy_enabled=self.get_setting("ntfy_enabled", False),
            ntfy_server_url=self.get_setting("ntfy_server_url", "https://ntfy.sh"),
            ntfy_media_topic=self.get_setting("ntfy_media_topic"),
            ntfy_text_topic=self.get_setting("ntfy_text_topic"),
            ntfy_username=self.get_setting("ntfy_username"),
            ntfy_password=self.get_setting("ntfy_password"),
            ntfy_auth_token=self.get_setting("ntfy_auth_token"),
            ntfy_priority=self.get_setting("ntfy_priority", "default"),
            ntfy_attach_media=self.get_setting("ntfy_attach_media", True),
        )

    def update_settings(self, settings: UserConfigurableSettings) -> bool:
        """Update multiple settings at once"""
        try:
            # Convert settings object to dict
            settings_dict = settings.model_dump()

            # Update each setting
            for key, value in settings_dict.items():
                if value is not None:  # Only update non-None values
                    self.set_setting(key, value)

            return True
        except Exception as e:
            logger.error(f"Error updating settings: {e}")
            return False

    def clear_cache(self):
        """Clear the settings cache"""
        self._cache.clear()
        self._cache_initialized = False
        logger.info("Settings cache cleared")


# Global settings service instance
_settings_service: Optional[SettingsService] = None


def get_settings_service(db: Optional[Session] = None) -> SettingsService:
    """Get the global settings service instance"""
    global _settings_service
    if _settings_service is None:
        _settings_service = SettingsService(db)
        _settings_service.initialize_defaults()
    return _settings_service


def get_runtime_config() -> Dict[str, Any]:
    """Get runtime configuration as a dictionary (for backwards compatibility)"""
    service = get_settings_service()
    settings = service.get_all_settings()
    return settings.model_dump()

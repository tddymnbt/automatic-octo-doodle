"""Configuration module for Daily Gospel / Daily Bread Shorts.

This module centralizes all environment variable access and provides
type-safe configuration. Secret values are NEVER logged or exposed.

Usage:
    from src.config import settings
    
    if settings.dry_run:
        print("Running in dry mode")
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _get_env(name: str, default: str = "") -> str:
    """Get environment variable value. Never log the value."""
    return os.getenv(name, default)


def _get_int(name: str, default: int = 0) -> int:
    """Get integer environment variable with fallback."""
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _get_bool(name: str, default: bool = False) -> bool:
    """Get boolean environment variable (true/false strings)."""
    value = os.getenv(name, "").lower()
    if not value:
        return default
    return value in ("true", "1", "yes", "on")


def _get_float(name: str, default: float = 0.0) -> float:
    """Get float environment variable with fallback."""
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return float(value)
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    """Application configuration from environment variables.
    
    Secret fields (never printed/logged):
    - gemini_api_key
    - meta_page_access_token
    - meta_page_id
    
    Non-secret configuration is safe to print.
    """
    
    # === SECRETS (never log these) ===
    gemini_api_key: str = field(default_factory=lambda: _get_env("GEMINI_API_KEY"))
    meta_page_access_token: str = field(default_factory=lambda: _get_env("META_PAGE_ACCESS_TOKEN"))
    meta_page_id: str = field(default_factory=lambda: _get_env("META_PAGE_ID"))
    
    # === AI MODELS ===
    ai_model: str = field(default_factory=lambda: _get_env("AI_MODEL", "gemini-3.5-flash-lite"))
    tts_model: str = field(default_factory=lambda: _get_env("TTS_MODEL", "gemini-3.1-flash-tts-preview"))
    tts_provider: str = field(default_factory=lambda: _get_env("TTS_PROVIDER", "kokoro"))
    tts_retry_count: int = field(default_factory=lambda: _get_int("TTS_RETRY_COUNT", 2))
    kokoro_voice: str = field(default_factory=lambda: _get_env("KOKORO_VOICE", "am_fenrir"))
    kokoro_speed: float = field(default_factory=lambda: _get_float("KOKORO_SPEED", 0.85))
    kokoro_lang: str = field(default_factory=lambda: _get_env("KOKORO_LANG", "a"))
    
    # === AUDIO (reverb) SETTINGS ===
    reverb_enabled: bool = field(default_factory=lambda: _get_bool("REVERB_ENABLED", True))
    reverb_delay: int = field(default_factory=lambda: _get_int("REVERB_DELAY", 30))
    reverb_decay: float = field(default_factory=lambda: _get_float("REVERB_DECAY", 0.4))
    reverb_wet: float = field(default_factory=lambda: _get_float("REVERB_WET", 0.06))

    # === VIDEO SETTINGS ===
    video_width: int = field(default_factory=lambda: _get_int("VIDEO_WIDTH", 1080))
    video_height: int = field(default_factory=lambda: _get_int("VIDEO_HEIGHT", 1920))
    video_fps: int = field(default_factory=lambda: _get_int("VIDEO_FPS", 30))
    target_duration_seconds: int = field(default_factory=lambda: _get_int("TARGET_DURATION_SECONDS", 45))
    min_duration_seconds: int = field(default_factory=lambda: _get_int("MIN_DURATION_SECONDS", 30))
    max_duration_seconds: int = field(default_factory=lambda: _get_int("MAX_DURATION_SECONDS", 60))
    
    # === RUNTIME SETTINGS ===
    dry_run: bool = field(default_factory=lambda: _get_bool("DRY_RUN", True))
    log_level: str = field(default_factory=lambda: _get_env("LOG_LEVEL", "INFO"))
    # Publishing slot identity (1-5) set by the CI workflow from the dispatch
    # input. Pure observability label at launch — does not gate behavior.
    slot: str = field(default_factory=lambda: _get_env("SLOT", "1"))
    
    # === CONTENT SETTINGS ===
    story_language: str = field(default_factory=lambda: _get_env("STORY_LANGUAGE", "en"))
    content_style: str = field(default_factory=lambda: _get_env("CONTENT_STYLE", "gospel_daily_bread"))
    
    # === FACEBOOK SETTINGS ===
    facebook_graph_version: str = field(default_factory=lambda: _get_env("FACEBOOK_GRAPH_VERSION", ""))
    facebook_retry_count: int = field(default_factory=lambda: _get_int("FACEBOOK_RETRY_COUNT", 3))
    
    # === FEATURE FLAGS ===
    max_visuals_per_video: int = field(default_factory=lambda: _get_int("MAX_VISUALS_PER_VIDEO", 8))
    enable_ambient_audio: bool = field(default_factory=lambda: _get_bool("ENABLE_AMBIENT_AUDIO", True))
    enable_background: bool = field(default_factory=lambda: _get_bool("ENABLE_BACKGROUND", True))
    enable_subtitles: bool = field(default_factory=lambda: _get_bool("ENABLE_SUBTITLES", True))

    # === AMBIENT / BACKGROUND TUNING ===
    ambient_level: float = field(default_factory=lambda: _get_float("AMBIENT_LEVEL", 0.15))
    ambient_fade_in: float = field(default_factory=lambda: _get_float("AMBIENT_FADE_IN", 2.0))
    ambient_fade_out: float = field(default_factory=lambda: _get_float("AMBIENT_FADE_OUT", 2.0))
    ambient_duck: bool = field(default_factory=lambda: _get_bool("AMBIENT_DUCK", True))

    # === PATHS ===
    project_root: Path = field(default_factory=lambda: Path(__file__).parent.parent)
    output_dir: Path = field(default_factory=lambda: Path(_get_env("OUTPUT_DIR", "output")))
    assets_dir: Path = field(default_factory=lambda: Path(_get_env("ASSETS_DIR", "assets/backgrounds")))
    background_dir: Path = field(default_factory=lambda: Path(_get_env("BACKGROUND_DIR", "assets/backgrounds")))
    ambient_dir: Path = field(default_factory=lambda: Path(_get_env("AMBIENT_DIR", "assets/ambient")))
    data_dir: Path = field(default_factory=lambda: Path(_get_env("DATA_DIR", "data")))
    
    def has_secret(self, name: str) -> bool:
        """Check if a secret is present WITHOUT revealing its value."""
        value = getattr(self, name, None)
        return bool(value)
    
    def validate_secrets(self) -> list[str]:
        """Return list of missing secret names. NEVER return values."""
        missing = []
        if not self.gemini_api_key:
            missing.append("GEMINI_API_KEY")
        if not self.meta_page_access_token:
            missing.append("META_PAGE_ACCESS_TOKEN")
        if not self.meta_page_id:
            missing.append("META_PAGE_ID")
        return missing
    
    def validate_config(self) -> list[str]:
        """Return list of configuration issues."""
        issues = []
        
        if self.video_width <= 0:
            issues.append("VIDEO_WIDTH must be positive")
        if self.video_height <= 0:
            issues.append("VIDEO_HEIGHT must be positive")
        if self.video_fps <= 0:
            issues.append("VIDEO_FPS must be positive")
        if self.target_duration_seconds < self.min_duration_seconds:
            issues.append("TARGET_DURATION_SECONDS must be >= MIN_DURATION_SECONDS")
        if self.target_duration_seconds > self.max_duration_seconds:
            issues.append("TARGET_DURATION_SECONDS must be <= MAX_DURATION_SECONDS")
        
        return issues
    
    def to_dict(self, include_secrets: bool = False) -> dict:
        """Convert settings to dictionary.
        
        Args:
            include_secrets: If True, include secret values (DANGEROUS).
                           Only for debugging with explicit user consent.
        """
        result = {
            "ai_model": self.ai_model,
            "tts_model": self.tts_model,
            "tts_provider": self.tts_provider,
            "kokoro_voice": self.kokoro_voice,
            "kokoro_speed": self.kokoro_speed,
            "kokoro_lang": self.kokoro_lang,
            "reverb_enabled": self.reverb_enabled,
            "reverb_delay": self.reverb_delay,
            "reverb_decay": self.reverb_decay,
            "reverb_wet": self.reverb_wet,
            "video_width": self.video_width,
            "video_height": self.video_height,
            "video_fps": self.video_fps,
            "target_duration_seconds": self.target_duration_seconds,
            "min_duration_seconds": self.min_duration_seconds,
            "max_duration_seconds": self.max_duration_seconds,
            "dry_run": self.dry_run,
            "log_level": self.log_level,
            "slot": self.slot,
            "story_language": self.story_language,
            "content_style": self.content_style,
            "facebook_graph_version": self.facebook_graph_version,
            "facebook_retry_count": self.facebook_retry_count,
            "max_visuals_per_video": self.max_visuals_per_video,
            "enable_ambient_audio": self.enable_ambient_audio,
            "enable_background": self.enable_background,
            "enable_subtitles": self.enable_subtitles,
            "ambient_level": self.ambient_level,
            "ambient_fade_in": self.ambient_fade_in,
            "ambient_fade_out": self.ambient_fade_out,
            "ambient_duck": self.ambient_duck,
        }
        
        if include_secrets:
            # Only when explicitly requested - log a warning
            import warnings
            warnings.warn(
                "to_dict(include_secrets=True) called - ensure this is not logged",
                UserWarning,
                stacklevel=2
            )
            result["gemini_api_key"] = self.gemini_api_key
            result["meta_page_access_token"] = self.meta_page_access_token
            result["meta_page_id"] = self.meta_page_id
        
        return result


# Global settings instance - loads once at import time
settings = Settings()

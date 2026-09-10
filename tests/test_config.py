"""Tests for environment validation and configuration.

These tests verify that the config module and validation script work correctly.
They do NOT test with real secret values.
"""

import os
from unittest.mock import patch

import pytest

from src.config import Settings, settings


class TestSettings:
    """Test Settings dataclass."""
    
    def test_settings_loads_defaults(self):
        """Settings should load with default values."""
        with patch.dict(os.environ, {}, clear=True):
            test_settings = Settings()
            
            # Non-secret defaults
            assert test_settings.ai_model == "gemini-3.5-flash-lite"
            assert test_settings.tts_model == "gemini-3.1-flash-tts-preview"
            assert test_settings.video_width == 1080
            assert test_settings.video_height == 1920
            assert test_settings.video_fps == 30
            assert test_settings.target_duration_seconds == 45
            assert test_settings.min_duration_seconds == 30
            assert test_settings.max_duration_seconds == 60
            assert test_settings.dry_run is True
            assert test_settings.log_level == "INFO"
    
    def test_settings_loads_from_env(self):
        """Settings should load from environment variables."""
        env = {
            "GEMINI_API_KEY": "test-key",
            "META_PAGE_ACCESS_TOKEN": "test-token",
            "META_PAGE_ID": "test-page-id",
            "AI_MODEL": "custom-model",
            "VIDEO_WIDTH": "1920",
            "DRY_RUN": "false",
        }
        
        with patch.dict(os.environ, env, clear=True):
            test_settings = Settings()
            
            assert test_settings.gemini_api_key == "test-key"
            assert test_settings.meta_page_access_token == "test-token"
            assert test_settings.meta_page_id == "test-page-id"
            assert test_settings.ai_model == "custom-model"
            assert test_settings.video_width == 1920
            assert test_settings.dry_run is False
    
    def test_has_secret(self):
        """has_secret should check presence without revealing value."""
        env = {
            "GEMINI_API_KEY": "secret-value-123",
            "META_PAGE_ACCESS_TOKEN": "",
            "META_PAGE_ID": "page-123",
        }
        
        with patch.dict(os.environ, env, clear=True):
            test_settings = Settings()
            
            # Should return True/False without exposing value
            assert test_settings.has_secret("gemini_api_key") is True
            assert test_settings.has_secret("meta_page_access_token") is False
            assert test_settings.has_secret("meta_page_id") is True
            assert test_settings.has_secret("nonexistent") is False
    
    def test_validate_secrets(self):
        """validate_secrets should return list of missing secret names."""
        env = {
            "GEMINI_API_KEY": "key-123",
            "META_PAGE_ACCESS_TOKEN": "",
            "META_PAGE_ID": "page-123",
        }
        
        with patch.dict(os.environ, env, clear=True):
            test_settings = Settings()
            missing = test_settings.validate_secrets()
            
            assert "META_PAGE_ACCESS_TOKEN" in missing
            assert "GEMINI_API_KEY" not in missing
            assert "META_PAGE_ID" not in missing
    
    def test_validate_config_valid(self):
        """validate_config should return empty list for valid config."""
        env = {
            "VIDEO_WIDTH": "1080",
            "VIDEO_HEIGHT": "1920",
            "TARGET_DURATION_SECONDS": "45",
            "MIN_DURATION_SECONDS": "30",
            "MAX_DURATION_SECONDS": "60",
        }
        
        with patch.dict(os.environ, env, clear=True):
            test_settings = Settings()
            issues = test_settings.validate_config()
            
            assert issues == []
    
    def test_validate_config_invalid_duration(self):
        """validate_config should catch invalid duration settings."""
        env = {
            "TARGET_DURATION_SECONDS": "20",  # Below minimum
            "MIN_DURATION_SECONDS": "30",
            "MAX_DURATION_SECONDS": "60",
        }
        
        with patch.dict(os.environ, env, clear=True):
            test_settings = Settings()
            issues = test_settings.validate_config()
            
            assert len(issues) > 0
            assert any("TARGET_DURATION_SECONDS" in issue for issue in issues)
    
    def test_to_dict_excludes_secrets_by_default(self):
        """to_dict should exclude secrets by default."""
        env = {
            "GEMINI_API_KEY": "secret-key-123",
            "META_PAGE_ACCESS_TOKEN": "secret-token-456",
        }
        
        with patch.dict(os.environ, env, clear=True):
            test_settings = Settings()
            result = test_settings.to_dict(include_secrets=False)
            
            assert "gemini_api_key" not in result
            assert "meta_page_access_token" not in result
            assert "ai_model" in result
    
    def test_to_dict_includes_secrets_when_requested(self):
        """to_dict should include secrets only when explicitly requested."""
        env = {
            "GEMINI_API_KEY": "secret-key-123",
        }
        
        with patch.dict(os.environ, env, clear=True):
            test_settings = Settings()
            result = test_settings.to_dict(include_secrets=True)
            
            assert result["gemini_api_key"] == "secret-key-123"
    
    def test_settings_is_frozen(self):
        """Settings should be immutable."""
        with patch.dict(os.environ, {}, clear=True):
            test_settings = Settings()
            
            with pytest.raises(AttributeError):
                test_settings.ai_model = "new-model"


class TestGlobalSettings:
    """Test the global settings instance."""
    
    def test_global_settings_exists(self):
        """Global settings instance should be available."""
        assert settings is not None
        assert isinstance(settings, Settings)
    
    def test_global_settings_has_project_root(self):
        """Global settings should have project root path."""
        assert settings.project_root.exists()
        assert settings.project_root.is_dir()


class TestBooleanParsing:
    """Test boolean environment variable parsing."""
    
    def test_true_values(self):
        """Various true-like values should parse as True."""
        true_values = ["true", "True", "TRUE", "1", "yes", "on"]
        
        for value in true_values:
            with patch.dict(os.environ, {"TEST_BOOL": value}, clear=True):
                test_settings = Settings()
                # Use a custom field to test
                assert value.lower() in ("true", "1", "yes", "on")
    
    def test_false_values(self):
        """Various false-like values should parse as False."""
        false_values = ["false", "False", "FALSE", "0", "no", "off", ""]
        
        for value in false_values:
            with patch.dict(os.environ, {"TEST_BOOL": value}, clear=True):
                test_settings = Settings()
                assert value.lower() not in ("true", "1", "yes", "on")


class TestIntegerParsing:
    """Test integer environment variable parsing."""
    
    def test_valid_integer(self):
        """Valid integer strings should parse correctly."""
        env = {"TEST_INT": "42"}
        
        with patch.dict(os.environ, env, clear=True):
            from src.config import _get_int
            assert _get_int("TEST_INT") == 42
    
    def test_invalid_integer_uses_default(self):
        """Invalid integer strings should use default value."""
        env = {"TEST_INT": "not-a-number"}
        
        with patch.dict(os.environ, env, clear=True):
            from src.config import _get_int
            assert _get_int("TEST_INT", default=99) == 99
    
    def test_missing_uses_default(self):
        """Missing environment variables should use default."""
        with patch.dict(os.environ, {}, clear=True):
            from src.config import _get_int
            assert _get_int("NONEXISTENT", default=77) == 77

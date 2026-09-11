"""Tests for the ambient audio selector."""

import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from src.assets.ambient import AmbientSelector


@pytest.fixture
def temp_ambient_dir():
    """Create a temporary ambient directory with test audio files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        ambient_dir = Path(tmpdir)

        files = {
            "mixkit-close-sea-waves-loop-1195.wav",
            "mixkit-light-rain-loop-2393.wav",
            "mixkit-thunder-rumble-during-a-storm-2395.wav",
            "mixkit-campfire-night-wind-1736.wav",
            "mixkit-forest-birds.wav",
        }
        for name in files:
            (ambient_dir / name).write_bytes(b"fake audio data")

        yield ambient_dir


@pytest.fixture
def empty_ambient_dir():
    """Create an empty ambient directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


class TestAmbientSelectorInit:
    """Test AmbientSelector initialization."""

    def test_default_init(self):
        """Default initialization should use settings.ambient_dir."""
        with patch("src.assets.ambient.settings") as mock_settings:
            mock_settings.ambient_dir = Path("/tmp/ambient")
            selector = AmbientSelector()
            assert selector._dir == Path("/tmp/ambient")

    def test_custom_init(self):
        """Custom initialization should use provided path."""
        selector = AmbientSelector(ambient_dir="/custom/ambient")
        assert selector._dir == Path("/custom/ambient")


class TestAmbientSelection:
    """Test ambient audio selection."""

    def test_select_by_category(self, temp_ambient_dir):
        """Should select matching category audio."""
        selector = AmbientSelector(ambient_dir=temp_ambient_dir)
        result = selector.select_ambient(["ocean"])
        assert result.has_audio
        assert result.path is not None
        assert "sea-waves" in result.path.name
        assert result.graded == "category:ocean"

    def test_select_first_category_wins(self, temp_ambient_dir):
        """Should prefer first category in provided order."""
        selector = AmbientSelector(ambient_dir=temp_ambient_dir)
        # Both ocean (sea-waves) and rain (light-rain) exist.
        result = selector.select_ambient(["ocean", "rain"])
        assert result.path is not None
        assert "sea-waves" in result.path.name

    def test_default_fallback(self, temp_ambient_dir):
        """Should fall back to calm default when no category matches."""
        selector = AmbientSelector(ambient_dir=temp_ambient_dir)
        result = selector.select_ambient(["unknown-category"])
        assert result.has_audio
        assert result.path is not None
        assert result.graded == "default"
        assert "campfire" in result.path.name

    def test_empty_categories_uses_default(self, temp_ambient_dir):
        """Empty category list should fall back to default track."""
        selector = AmbientSelector(ambient_dir=temp_ambient_dir)
        result = selector.select_ambient([])
        assert result.path is not None
        assert result.has_audio
        assert result.graded == "default"

    def test_missing_dir_returns_none(self):
        """Missing ambient dir should return no audio."""
        selector = AmbientSelector(ambient_dir="/nonexistent/ambient")
        result = selector.select_ambient(["ocean"])
        assert result.has_audio is False
        assert result.path is None

    def test_empty_dir_returns_none(self, empty_ambient_dir):
        """Empty ambient dir should return no audio."""
        selector = AmbientSelector(ambient_dir=empty_ambient_dir)
        result = selector.select_ambient(["ocean"])
        assert result.has_audio is False

    def test_custom_preference(self, temp_ambient_dir):
        """Custom preference map should take precedence."""
        custom = {"rain": "thunder-rumble"}
        selector = AmbientSelector(ambient_dir=temp_ambient_dir, category_preference=custom)
        result = selector.select_ambient(["rain"])
        assert result.has_audio
        assert result.path is not None
        assert "thunder" in result.path.name

    def test_filename_substring_case_insensitive(self, temp_ambient_dir):
        """Substring matching should be case-insensitive."""
        selector = AmbientSelector(ambient_dir=temp_ambient_dir, default_substr="CAMPFIRE")
        result = selector.select_ambient([])
        assert result.path is not None
        assert result.has_audio
        assert "campfire" in result.path.name
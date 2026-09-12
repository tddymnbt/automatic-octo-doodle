"""Tests for asset models."""

from pathlib import Path

import pytest

from src.assets.models import Asset, AssetCategory, AssetSelection


class TestAssetCategory:
    """Test AssetCategory enum."""
    
    def test_all_categories_exist(self):
        """All expected categories should exist."""
        expected = [
            "bedroom", "forest", "rain", "city", "hallway",
            "cafe", "ocean", "night", "window", "street",
            "gospel", "sunrise", "mountains", "garden", "church", "nature",
        ]
        actual = AssetCategory.all_categories()
        assert sorted(actual) == sorted(expected)
    
    def test_from_string_lowercase(self):
        """Category should be created from lowercase string."""
        assert AssetCategory.from_string("bedroom") == AssetCategory.BEDROOM
        assert AssetCategory.from_string("forest") == AssetCategory.FOREST
    
    def test_from_string_uppercase(self):
        """Category should be created from uppercase string."""
        assert AssetCategory.from_string("BEDROOM") == AssetCategory.BEDROOM
        assert AssetCategory.from_string("Forest") == AssetCategory.FOREST
    
    def test_from_string_with_whitespace(self):
        """Category should handle whitespace."""
        assert AssetCategory.from_string("  bedroom  ") == AssetCategory.BEDROOM
    
    def test_from_string_invalid(self):
        """Invalid category should raise ValueError."""
        with pytest.raises(ValueError, match="Unknown category"):
            AssetCategory.from_string("invalid")
    
    def test_category_values(self):
        """Category values should match expected strings."""
        assert AssetCategory.BEDROOM.value == "bedroom"
        assert AssetCategory.OCEAN.value == "ocean"
        assert AssetCategory.NIGHT.value == "night"


class TestAsset:
    """Test Asset dataclass."""
    
    def test_valid_asset(self):
        """Valid asset should create successfully."""
        asset = Asset(
            path=Path("/assets/bedroom/image.jpg"),
            category=AssetCategory.BEDROOM,
            filename="image.jpg",
        )
        assert asset.category == AssetCategory.BEDROOM
        assert asset.filename == "image.jpg"
    
    def test_asset_with_dimensions(self):
        """Asset should accept dimensions."""
        asset = Asset(
            path=Path("/assets/image.png"),
            category=AssetCategory.FOREST,
            filename="image.png",
            width=1920,
            height=1080,
        )
        assert asset.width == 1920
        assert asset.height == 1080
    
    def test_asset_is_image(self):
        """Image file should be detected correctly."""
        asset = Asset(
            path=Path("/assets/image.jpg"),
            category=AssetCategory.BEDROOM,
            filename="image.jpg",
        )
        assert asset.is_image is True
        assert asset.is_video is False
    
    def test_asset_is_video(self):
        """Video file should be detected correctly."""
        asset = Asset(
            path=Path("/assets/video.mp4"),
            category=AssetCategory.CITY,
            filename="video.mp4",
        )
        assert asset.is_video is True
        assert asset.is_image is False
    
    def test_asset_repr(self):
        """Asset repr should show category and filename."""
        asset = Asset(
            path=Path("/assets/bedroom/test.jpg"),
            category=AssetCategory.BEDROOM,
            filename="test.jpg",
        )
        assert "bedroom" in repr(asset)
        assert "test.jpg" in repr(asset)


class TestAssetSelection:
    """Test AssetSelection dataclass."""
    
    def test_empty_selection(self):
        """Empty selection should have no assets."""
        selection = AssetSelection(
            assets=[],
            categories_used=[],
            total_assets=10,
            selected_count=0,
        )
        assert selection.has_assets is False
    
    def test_selection_with_assets(self):
        """Selection with assets should report correctly."""
        asset = Asset(
            path=Path("/assets/test.jpg"),
            category=AssetCategory.BEDROOM,
            filename="test.jpg",
        )
        selection = AssetSelection(
            assets=[asset],
            categories_used=[AssetCategory.BEDROOM],
            total_assets=10,
            selected_count=1,
        )
        assert selection.has_assets is True
        assert selection.selected_count == 1

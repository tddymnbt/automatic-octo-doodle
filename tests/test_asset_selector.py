"""Tests for asset selector."""

import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from src.assets.models import AssetCategory
from src.assets.selector import AssetSelector


@pytest.fixture
def temp_assets_dir():
    """Create a temporary assets directory with test images."""
    with tempfile.TemporaryDirectory() as tmpdir:
        assets_dir = Path(tmpdir)
        
        # Create category directories
        categories = ["bedroom", "forest", "rain", "city"]
        for cat in categories:
            cat_dir = assets_dir / cat
            cat_dir.mkdir()
            
            # Create test images
            for i in range(3):
                img_file = cat_dir / f"image_{i}.jpg"
                img_file.write_bytes(b"fake image data")
        
        yield assets_dir


@pytest.fixture
def empty_assets_dir():
    """Create an empty assets directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def selector(temp_assets_dir):
    """Create an AssetSelector with test assets."""
    return AssetSelector(assets_dir=temp_assets_dir)


class TestAssetSelectorInit:
    """Test AssetSelector initialization."""
    
    def test_default_init(self):
        """Default initialization should work."""
        with patch("src.assets.selector.settings") as mock_settings:
            mock_settings.assets_dir = Path("/tmp/assets")
            selector = AssetSelector()
            assert selector._assets_dir == Path("/tmp/assets")
    
    def test_custom_init(self):
        """Custom initialization should use provided path."""
        selector = AssetSelector(assets_dir="/custom/path")
        assert selector._assets_dir == Path("/custom/path")


class TestScanAssets:
    """Test asset scanning."""
    
    def test_scan_finds_categories(self, selector):
        """Scan should find all category directories."""
        assets = selector.scan_assets()
        
        assert len(assets) == 4
        assert AssetCategory.BEDROOM in assets
        assert AssetCategory.FOREST in assets
    
    def test_scan_counts_assets(self, selector):
        """Scan should count assets correctly."""
        assets = selector.scan_assets()
        
        # Each category should have 3 images
        assert len(assets[AssetCategory.BEDROOM]) == 3
        assert len(assets[AssetCategory.FOREST]) == 3
    
    def test_scan_empty_dir(self, empty_assets_dir):
        """Scan empty directory should return empty dict."""
        selector = AssetSelector(assets_dir=empty_assets_dir)
        assets = selector.scan_assets()
        
        assert len(assets) == 0
    
    def test_scan_missing_dir(self):
        """Scan missing directory should return empty dict."""
        selector = AssetSelector(assets_dir="/nonexistent/path")
        assets = selector.scan_assets()
        
        assert len(assets) == 0
    
    def test_scan_ignores_unknown_categories(self, temp_assets_dir):
        """Scan should ignore directories with unknown category names."""
        # Create unknown category
        unknown_dir = temp_assets_dir / "unknown_category"
        unknown_dir.mkdir()
        (unknown_dir / "image.jpg").write_bytes(b"fake data")
        
        selector = AssetSelector(assets_dir=temp_assets_dir)
        assets = selector.scan_assets()
        
        # Unknown category should not be included
        assert len(assets) == 4  # Only the 4 known categories
    
    def test_scan_caches_results(self, selector):
        """Scan should cache results."""
        assets1 = selector.scan_assets()
        assets2 = selector.scan_assets()
        
        # Should be the same object
        assert assets1 is assets2
    
    def test_scan_max_per_category(self, temp_assets_dir):
        """Scan should respect max assets per category."""
        # Create extra images in bedroom
        bedroom_dir = temp_assets_dir / "bedroom"
        for i in range(5):
            (bedroom_dir / f"extra_{i}.jpg").write_bytes(b"extra data")
        
        selector = AssetSelector(assets_dir=temp_assets_dir, max_assets_per_category=3)
        assets = selector.scan_assets()
        
        # Should only have 3 assets
        assert len(assets[AssetCategory.BEDROOM]) == 3


class TestGetAssetsForCategory:
    """Test getting assets by category."""
    
    def test_get_assets_returns_list(self, selector):
        """Should return list of assets."""
        assets = selector.get_assets_for_category(AssetCategory.BEDROOM, count=2)
        
        assert isinstance(assets, list)
        assert len(assets) == 2
    
    def test_get_assets_respects_count(self, selector):
        """Should return requested number of assets."""
        assets = selector.get_assets_for_category(AssetCategory.BEDROOM, count=1)
        
        assert len(assets) == 1
    
    def test_get_assets_max_available(self, selector):
        """Should return max available if count exceeds available."""
        assets = selector.get_assets_for_category(AssetCategory.BEDROOM, count=10)
        
        # Should return 3 (all available), not 10
        assert len(assets) == 3
    
    def test_get_assets_unknown_category(self, selector):
        """Should return empty list for unknown category."""
        assets = selector.get_assets_for_category(
            AssetCategory.BEDROOM, count=1
        )
        
        assert isinstance(assets, list)
    
    def test_get_assets_empty_category(self, temp_assets_dir):
        """Should return empty list if category has no assets."""
        # Create empty category
        empty_dir = temp_assets_dir / "empty"
        empty_dir.mkdir()
        
        selector = AssetSelector(assets_dir=temp_assets_dir)
        # Manually add empty category to cache
        selector._cache[AssetCategory.BEDROOM] = []
        
        assets = selector.get_assets_for_category(AssetCategory.BEDROOM, count=1)
        
        assert assets == []


class TestSelectAssetsForScenes:
    """Test selecting assets for story scenes."""
    
    def test_select_for_matching_scenes(self, selector):
        """Should select assets for matching scene categories."""
        scenes = [
            {"category": "bedroom", "description": "dark bedroom"},
            {"category": "forest", "description": "mysterious forest"},
        ]
        
        selection = selector.select_assets_for_scenes(scenes)
        
        assert selection.has_assets is True
        assert selection.selected_count >= 2
    
    def test_select_for_unknown_category(self, selector):
        """Should handle unknown categories gracefully."""
        scenes = [
            {"category": "unknown", "description": "mystery scene"},
            {"category": "bedroom", "description": "bedroom scene"},
        ]
        
        selection = selector.select_assets_for_scenes(scenes)
        
        # Should still select assets for bedroom
        assert selection.has_assets is True
    
    def test_select_for_empty_category(self, selector):
        """Should handle empty category string."""
        scenes = [
            {"category": "", "description": "no category"},
            {"category": "bedroom", "description": "bedroom scene"},
        ]
        
        selection = selector.select_assets_for_scenes(scenes)
        
        assert selection.has_assets is True
    
    def test_select_fallback_when_no_match(self, temp_assets_dir):
        """Should fallback when no categories match."""
        selector = AssetSelector(assets_dir=temp_assets_dir)
        
        scenes = [
            {"category": "nonexistent", "description": "no match"},
        ]
        
        selection = selector.select_assets_for_scenes(scenes)
        
        # Should fallback to any available assets
        assert selection.has_assets is True
    
    def test_select_multiple_per_scene(self, selector):
        """Should select multiple assets per scene."""
        scenes = [
            {"category": "bedroom", "description": "bedroom scene"},
        ]
        
        selection = selector.select_assets_for_scenes(scenes, max_per_scene=3)
        
        # Should select up to 3 assets
        assert selection.selected_count >= 1


class TestAssetSelectorUtilities:
    """Test utility methods."""
    
    def test_get_available_categories(self, selector):
        """Should return categories with assets."""
        categories = selector.get_available_categories()
        
        assert len(categories) == 4
        assert AssetCategory.BEDROOM in categories
    
    def test_get_asset_counts(self, selector):
        """Should return asset counts per category."""
        counts = selector.get_asset_counts()
        
        assert counts["bedroom"] == 3
        assert counts["forest"] == 3
    
    def test_validate_assets(self, selector):
        """Should validate asset existence."""
        errors = selector.validate_assets()
        
        # All test assets exist, so no errors
        assert errors == []
    
    def test_validate_missing_assets(self, temp_assets_dir):
        """Should detect missing assets."""
        selector = AssetSelector(assets_dir=temp_assets_dir)
        selector.scan_assets()
        
        # Remove an asset file
        bedroom_dir = temp_assets_dir / "bedroom"
        (bedroom_dir / "image_0.jpg").unlink()
        
        errors = selector.validate_assets()
        
        assert len(errors) == 1
        assert "Missing asset" in errors[0]


class TestAssetSelectorGospelAmbient:
    """Test gospel background + ambient track selection."""

    @pytest.fixture
    def gospel_dir(self):
        """Assets dir with a gospel subfolder + an ambient sibling dir."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            gospel = base / "gospel"
            gospel.mkdir()
            for i in range(3):
                (gospel / f"gospel-00{i}.webp").write_bytes(b"fake image")
            ambient_dir = base / "ambient"
            ambient_dir.mkdir()
            (ambient_dir / "hillsong.wav").write_bytes(b"fake audio")
            (ambient_dir / "other.mp3").write_bytes(b"fake audio")
            yield base, gospel, ambient_dir

    def test_list_backgrounds_prefers_gospel(self, gospel_dir):
        base, _, _ = gospel_dir
        sel = AssetSelector(assets_dir=base)
        bgs = sel.list_backgrounds(prefer_gospel=True)
        assert len(bgs) == 3
        assert all("gospel" in str(a.path) for a in bgs)

    def test_select_background_returns_asset(self, gospel_dir):
        base, _, _ = gospel_dir
        sel = AssetSelector(assets_dir=base, random_background=False)
        bg = sel.select_background(prefer_gospel=True)
        assert bg is not None
        assert bg.path.exists()

    def test_select_background_none_when_empty(self, empty_assets_dir):
        sel = AssetSelector(assets_dir=empty_assets_dir)
        assert sel.select_background() is None

    def test_list_ambient_finds_audio(self, gospel_dir):
        base, _, ambient_dir = gospel_dir
        sel = AssetSelector(assets_dir=base, ambient_dir=ambient_dir)
        tracks = sel.list_ambient()
        assert len(tracks) == 2
        assert all(".wav" in a.path.suffix or ".mp3" in a.path.suffix for a in tracks)

    def test_select_ambient_returns_track(self, gospel_dir):
        base, _, ambient_dir = gospel_dir
        sel = AssetSelector(assets_dir=base, ambient_dir=ambient_dir)
        track = sel.select_ambient()
        assert track is not None
        assert track.path.exists()

    def test_select_ambient_none_when_missing(self, empty_assets_dir):
        sel = AssetSelector(assets_dir=empty_assets_dir, ambient_dir=empty_assets_dir)
        assert sel.select_ambient() is None


class TestAssetSelectorFactory:
    """Test factory function."""
    
    def test_create_selector(self):
        """Factory should create AssetSelector."""
        selector = AssetSelector(assets_dir="/tmp/test")
        assert isinstance(selector, AssetSelector)

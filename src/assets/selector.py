"""Asset selector for automatic background image selection.

This module scans asset directories, categorizes images by folder name,
and selects compatible assets based on story scene requirements.
"""

from __future__ import annotations

import logging
import random
from pathlib import Path

from src.assets.models import Asset, AssetCategory, AssetSelection
from src.config import settings

logger = logging.getLogger(__name__)

# Supported image extensions
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".webm"}
ALL_MEDIA_EXTENSIONS = IMAGE_EXTENSIONS | VIDEO_EXTENSIONS


class AssetSelector:
    """Selects visual assets based on story scene requirements.
    
    This selector:
    1. Scans asset directories for available media
    2. Categorizes assets by folder name
    3. Selects assets matching scene categories
    4. Handles missing assets gracefully
    """
    
    def __init__(
        self,
        assets_dir: Path | str | None = None,
        max_assets_per_category: int = 10,
    ) -> None:
        """Initialize the asset selector.
        
        Args:
            assets_dir: Path to assets directory (default: from settings)
            max_assets_per_category: Max assets to load per category
        """
        self._assets_dir = Path(assets_dir) if assets_dir else settings.assets_dir
        self._max_per_category = max_assets_per_category
        self._cache: dict[AssetCategory, list[Asset]] = {}
        
        logger.info(f"Asset selector initialized: {self._assets_dir}")
    
    def scan_assets(self) -> dict[AssetCategory, list[Asset]]:
        """Scan asset directory and categorize all available media.
        
        Returns:
            Dictionary mapping categories to their assets
        """
        if self._cache:
            return self._cache
        
        assets: dict[AssetCategory, list[Asset]] = {}
        
        if not self._assets_dir.exists():
            logger.warning(f"Assets directory not found: {self._assets_dir}")
            return assets
        
        # Scan each subdirectory
        for category_dir in self._assets_dir.iterdir():
            if not category_dir.is_dir():
                continue
            
            # Try to match directory name to category
            try:
                category = AssetCategory.from_string(category_dir.name)
            except ValueError:
                logger.debug(f"Skipping unknown category directory: {category_dir.name}")
                continue
            
            # Scan for media files in this category
            category_assets = self._scan_category_dir(category_dir, category)
            
            if category_assets:
                # Limit assets per category
                assets[category] = category_assets[:self._max_per_category]
                logger.info(f"Found {len(assets[category])} assets in '{category.value}'")
        
        self._cache = assets
        return assets
    
    def _scan_category_dir(
        self,
        directory: Path,
        category: AssetCategory,
    ) -> list[Asset]:
        """Scan a single category directory for media files.
        
        Args:
            directory: Directory to scan
            category: Category for assets in this directory
            
        Returns:
            List of Asset objects
        """
        assets = []
        
        for file_path in directory.iterdir():
            if not file_path.is_file():
                continue
            
            if file_path.suffix.lower() not in ALL_MEDIA_EXTENSIONS:
                continue
            
            asset = Asset(
                path=file_path,
                category=category,
                filename=file_path.name,
            )
            assets.append(asset)
        
        # Sort by filename for consistent selection
        assets.sort(key=lambda a: a.filename)
        
        return assets
    
    def get_assets_for_category(
        self,
        category: AssetCategory,
        count: int = 1,
    ) -> list[Asset]:
        """Get random assets for a specific category.
        
        Args:
            category: Asset category
            count: Number of assets to select
            
        Returns:
            List of selected assets (may be fewer than requested)
        """
        # Ensure assets are scanned
        if not self._cache:
            self.scan_assets()
        
        available = self._cache.get(category, [])
        
        if not available:
            logger.warning(f"No assets available for category: {category.value}")
            return []
        
        # Select random assets without replacement
        count = min(count, len(available))
        selected = random.sample(available, count)
        
        logger.debug(f"Selected {len(selected)} assets from '{category.value}'")
        return selected
    
    def select_assets_for_scenes(
        self,
        scenes: list[dict],
        max_per_scene: int = 2,
    ) -> AssetSelection:
        """Select assets for a list of story scenes.
        
        Args:
            scenes: List of scene dictionaries with 'category' field
            max_per_scene: Maximum assets to select per scene
            
        Returns:
            AssetSelection with selected assets
        """
        selected_assets: list[Asset] = []
        categories_used: list[AssetCategory] = []
        
        for scene in scenes:
            category_str = scene.get("category", "")
            
            if not category_str:
                logger.debug("Scene has no category, skipping")
                continue
            
            try:
                category = AssetCategory.from_string(category_str)
            except ValueError:
                logger.warning(f"Unknown category '{category_str}', skipping")
                continue
            
            # Get assets for this category
            assets = self.get_assets_for_category(category, count=max_per_scene)
            
            if assets:
                selected_assets.extend(assets)
                if category not in categories_used:
                    categories_used.append(category)
        
        # Fallback: if no assets selected, try to get any available
        if not selected_assets:
            logger.warning("No matching assets found, using fallback selection")
            selected_assets = self._fallback_selection(max_count=4)
        
        return AssetSelection(
            assets=selected_assets,
            categories_used=categories_used,
            total_assets=self._count_total_assets(),
            selected_count=len(selected_assets),
        )
    
    def _fallback_selection(self, max_count: int = 4) -> list[Asset]:
        """Fallback selection when no matching assets found.
        
        Args:
            max_count: Maximum assets to select
            
        Returns:
            List of assets from any available category
        """
        if not self._cache:
            self.scan_assets()
        
        all_assets: list[Asset] = []
        for assets in self._cache.values():
            all_assets.extend(assets)
        
        if not all_assets:
            return []
        
        # Select random assets from all available
        count = min(max_count, len(all_assets))
        return random.sample(all_assets, count)
    
    def _count_total_assets(self) -> int:
        """Count total available assets across all categories."""
        return sum(len(assets) for assets in self._cache.values())
    
    def get_available_categories(self) -> list[AssetCategory]:
        """Get list of categories with available assets.
        
        Returns:
            List of categories that have at least one asset
        """
        if not self._cache:
            self.scan_assets()
        
        return [cat for cat, assets in self._cache.items() if assets]
    
    def get_asset_counts(self) -> dict[str, int]:
        """Get count of assets per category.
        
        Returns:
            Dictionary mapping category names to counts
        """
        if not self._cache:
            self.scan_assets()
        
        return {cat.value: len(assets) for cat, assets in self._cache.items()}
    
    def validate_assets(self) -> list[str]:
        """Validate that all cached assets exist on disk.
        
        Returns:
            List of error messages for missing assets
        """
        errors = []
        
        for category, assets in self._cache.items():
            for asset in assets:
                if not asset.exists:
                    errors.append(f"Missing asset: {asset.path}")
        
        return errors


def create_asset_selector(
    assets_dir: Path | str | None = None,
) -> AssetSelector:
    """Factory function to create an asset selector.
    
    Args:
        assets_dir: Optional path to assets directory
        
    Returns:
        AssetSelector instance
    """
    return AssetSelector(assets_dir=assets_dir)

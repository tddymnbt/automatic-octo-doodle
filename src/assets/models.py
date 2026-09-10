"""Data models for visual assets."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path


class AssetCategory(str, Enum):
    """Valid asset categories for scene matching."""
    
    BEDROOM = "bedroom"
    FOREST = "forest"
    RAIN = "rain"
    CITY = "city"
    HALLWAY = "hallway"
    CAFE = "cafe"
    OCEAN = "ocean"
    NIGHT = "night"
    WINDOW = "window"
    STREET = "street"
    
    @classmethod
    def from_string(cls, value: str) -> AssetCategory:
        """Convert string to AssetCategory.
        
        Args:
            value: Category string (case-insensitive)
            
        Returns:
            Matching AssetCategory
            
        Raises:
            ValueError: Unknown category
        """
        try:
            return cls(value.lower().strip())
        except ValueError:
            raise ValueError(
                f"Unknown category: '{value}'. "
                f"Valid categories: {[c.value for c in cls]}"
            )
    
    @classmethod
    def all_categories(cls) -> list[str]:
        """Get all category names."""
        return [c.value for c in cls]


@dataclass
class Asset:
    """Represents a visual asset (image or video)."""
    
    path: Path
    category: AssetCategory
    filename: str
    width: int = 0
    height: int = 0
    duration_seconds: float = 0.0  # For video assets
    
    @property
    def exists(self) -> bool:
        """Check if asset file exists."""
        return self.path.exists()
    
    @property
    def is_image(self) -> bool:
        """Check if asset is an image."""
        return self.path.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}
    
    @property
    def is_video(self) -> bool:
        """Check if asset is a video."""
        return self.path.suffix.lower() in {".mp4", ".mov", ".avi", ".webm"}
    
    def __repr__(self) -> str:
        return f"Asset({self.category.value}/{self.filename})"


@dataclass
class AssetSelection:
    """Result of asset selection for a story."""
    
    assets: list[Asset]
    categories_used: list[AssetCategory]
    total_assets: int
    selected_count: int
    
    @property
    def has_assets(self) -> bool:
        """Check if any assets were selected."""
        return self.selected_count > 0

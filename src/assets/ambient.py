"""Ambient audio selection for ASMR videos.

The pipeline mixes a single ambient bed under the narration (see
src/video/ffmpeg.py). This module picks one ambient WAV that matches the
story's dominant scene category, falling back to a calm default and finally to
a random track if no mapping matches.

The mapping keys are substrings matched against the ambient filename. Scene
category names come from src.assets.models.AssetCategory + the scene
"category" field in story data.
"""

from __future__ import annotations

import logging
import random
from dataclasses import dataclass, field
from pathlib import Path

from src.config import settings

logger = logging.getLogger(__name__)

# Supported ambient audio extensions
AMBIENT_EXTENSIONS = {".wav", ".mp3", ".aac", ".m4a", ".ogg", ".flac"}

# Category -> preferred ambient filename substring (first match wins).
# Kept explicit so artists can re-theme without touching render code.
CATEGORY_PREFERENCE: dict[str, str] = {
    "ocean": "close-sea-waves",
    "rain": "light-rain",
    "storm": "thunder-rumble",
    "city": "urban-ambience",
    "street": "city-traffic",
    "cafe": "office-ambience",
    "office": "office-ambience",
    "forest": "wind-in-the-forest",
    "night": "night-forest",
    "bedroom": "pond-ambience",
    "window": "night-forest",
    "hallway": "horror-ambience",
}

# Calm generic ASMR default when no category matches.
DEFAULT_AMBIENT_SUBSTR = "campfire-night-wind"


@dataclass
class AmbientSelection:
    """Result of ambient audio selection."""

    path: Path | None
    category: str = ""
    graded: str = "none"
    available_count: int = 0

    @property
    def has_audio(self) -> bool:
        return self.path is not None


class AmbientSelector:
    """Choose an ambient audio bed for a story.

    Scans an ambient directory for audio files and selects one based on the
    story's scene categories.
    """

    def __init__(
        self,
        ambient_dir: Path | str | None = None,
        category_preference: dict[str, str] | None = None,
        default_substr: str = DEFAULT_AMBIENT_SUBSTR,
    ) -> None:
        self._dir = Path(ambient_dir) if ambient_dir else settings.ambient_dir
        self._preference = category_preference or CATEGORY_PREFERENCE
        self._default_substr = default_substr
        self._cache: list[Path] | None = None

    def _scan(self) -> list[Path]:
        """Scan ambient dir for supported audio files (cached)."""
        if self._cache is not None:
            return self._cache
        files: list[Path] = []
        if not self._dir.exists():
            logger.warning(f"Ambient directory not found: {self._dir}")
            files = []
        else:
            files = [
                p
                for p in sorted(self._dir.iterdir())
                if p.is_file() and p.suffix.lower() in AMBIENT_EXTENSIONS
            ]
        self._cache = files
        return files

    def select_ambient(self, categories: list[str]) -> AmbientSelection:
        """Pick an ambient track matching the given scene categories.

        Args:
            categories: Scene category strings from the story (may be empty).

        Returns:
            AmbientSelection with the chosen audio path (or None if none found).
        """
        files = self._scan()
        if not files:
            logger.warning("No ambient audio files available")
            return AmbientSelection(path=None, available_count=0)

        chosen: Path | None = None
        graded = "none"

        # 1) Try to match the most common first-seen category order.
        for cat in categories:
            key = cat.lower().strip()
            substr = self._preference.get(key)
            if not substr:
                continue
            match = self._find_matching(substr, files)
            if match:
                chosen, graded = match, f"category:{key}"
                break

        # 2) Fall back to the calm default track if present.
        if chosen is None:
            match = self._find_matching(self._default_substr, files)
            if match:
                chosen, graded = match, "default"

        # 3) Last resort: random track.
        if chosen is None:
            chosen = random.choice(files)
            graded = "random"

        logger.info(f"Ambient selected: {chosen.name} (match: {graded})")
        return AmbientSelection(
            path=chosen,
            category=graded,
            graded=graded,
            available_count=len(files),
        )

    def _find_matching(self, substr: str, files: list[Path]) -> Path | None:
        """Return the first file whose name contains the substring."""
        return next((f for f in files if substr.lower() in f.stem.lower()), None)


def create_ambient_selector(
    ambient_dir: Path | str | None = None,
) -> AmbientSelector:
    """Factory to create an AmbientSelector."""
    return AmbientSelector(ambient_dir=ambient_dir)
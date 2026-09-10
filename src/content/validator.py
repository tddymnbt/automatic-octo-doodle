"""Content validator for stories.

Validates story data against structural, safety, and business rules.
"""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass, field

from src.content.schema import StoryData

logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    """Result of content validation."""
    
    is_valid: bool = True
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    
    def add_error(self, message: str) -> None:
        """Add a validation error."""
        self.errors.append(message)
        self.is_valid = False
    
    def add_warning(self, message: str) -> None:
        """Add a validation warning."""
        self.warnings.append(message)


class StoryValidator:
    """Validates story data against requirements.
    
    Validation rules:
    1. Structure: All required fields present and valid
    2. Duration: Narration fits target duration
    3. Scenes: Valid scene structure and categories
    4. Content: No unsafe or inappropriate content
    5. Uniqueness: Content hash for duplicate detection
    """
    
    # Valid asset categories
    VALID_CATEGORIES = {
        "bedroom", "forest", "rain", "city", "hallway",
        "cafe", "ocean", "night", "window", "street",
    }
    
    # Duration constraints
    MIN_DURATION_SECONDS = 30
    MAX_DURATION_SECONDS = 60
    TARGET_DURATION_SECONDS = 45
    
    # Words per minute for ASMR narration
    ASMR_WPM = 150
    
    # Content safety patterns (basic checks)
    UNSAFE_PATTERNS = [
        r"\b(kill|murder|die|death|violent|assault)\b",
        r"\b(hate|racist|bigot|discriminat)\b",
        r"\b(sexual|nude|porn|erotic)\b",
        r"\b(drug|cocaine|heroin|meth)\b",
    ]
    
    def __init__(
        self,
        min_duration: int = MIN_DURATION_SECONDS,
        max_duration: int = MAX_DURATION_SECONDS,
        target_duration: int = TARGET_DURATION_SECONDS,
    ) -> None:
        """Initialize validator with duration constraints.
        
        Args:
            min_duration: Minimum allowed duration in seconds
            max_duration: Maximum allowed duration in seconds
            target_duration: Target duration in seconds
        """
        self.min_duration = min_duration
        self.max_duration = max_duration
        self.target_duration = target_duration
    
    def validate(self, story: StoryData) -> ValidationResult:
        """Validate a story against all rules.
        
        Args:
            story: Story data to validate
            
        Returns:
            ValidationResult with errors and warnings
        """
        result = ValidationResult()
        
        # Run all validation checks
        self._validate_structure(story, result)
        self._validate_duration(story, result)
        self._validate_scenes(story, result)
        self._validate_content(story, result)
        
        # Generate content hash
        story.content_hash = self._compute_hash(story)
        
        if result.is_valid:
            logger.info(f"Story validation passed: '{story.title}'")
        else:
            logger.warning(f"Story validation failed: {result.errors}")
        
        return result
    
    def _validate_structure(self, story: StoryData, result: ValidationResult) -> None:
        """Validate story structure."""
        # Title
        if len(story.title) < 5:
            result.add_error("Title too short (minimum 5 characters)")
        if len(story.title) > 100:
            result.add_error("Title too long (maximum 100 characters)")
        
        # Hook
        if len(story.hook) < 10:
            result.add_error("Hook too short (minimum 10 characters)")
        if len(story.hook) > 200:
            result.add_error("Hook too long (maximum 200 characters)")
        
        # Narration
        if len(story.narration) < 50:
            result.add_error("Narration too short (minimum 50 characters)")
        if len(story.narration) > 2000:
            result.add_error("Narration too long (maximum 2000 characters)")
        
        # Scenes
        if not story.scenes:
            result.add_error("Story must have at least one scene")
        if len(story.scenes) > 10:
            result.add_error("Story has too many scenes (maximum 10)")
    
    def _validate_duration(self, story: StoryData, result: ValidationResult) -> None:
        """Validate story duration."""
        estimated_seconds = story.estimate_duration_seconds()
        
        if estimated_seconds < self.min_duration:
            result.add_error(
                f"Narration too short for target duration "
                f"(~{estimated_seconds:.0f}s vs {self.min_duration}s minimum)"
            )
            result.add_warning(
                f"Consider adding more content to reach {self.target_duration} seconds"
            )
        
        if estimated_seconds > self.max_duration:
            result.add_error(
                f"Narration too long for target duration "
                f"(~{estimated_seconds:.0f}s vs {self.max_duration}s maximum)"
            )
            result.add_warning(
                f"Consider trimming content to fit {self.target_duration} seconds"
            )
        
        # Check scene durations sum
        scene_total = sum(s.duration_seconds for s in story.scenes)
        if abs(scene_total - estimated_seconds) > 10:
            result.add_warning(
                f"Scene durations ({scene_total:.0f}s) don't match "
                f"narration estimate ({estimated_seconds:.0f}s)"
            )
    
    def _validate_scenes(self, story: StoryData, result: ValidationResult) -> None:
        """Validate scene structure."""
        for i, scene in enumerate(story.scenes):
            # Duration
            if scene.duration_seconds <= 0:
                result.add_error(f"Scene {i+1} duration must be positive")
            if scene.duration_seconds > 30:
                result.add_warning(f"Scene {i+1} is very long ({scene.duration_seconds}s)")
            
            # Description
            if len(scene.description) < 5:
                result.add_error(f"Scene {i+1} description too short")
            
            # Category
            if scene.category and scene.category not in self.VALID_CATEGORIES:
                result.add_warning(
                    f"Scene {i+1} category '{scene.category}' not in known categories"
                )
    
    def _validate_content(self, story: StoryData, result: ValidationResult) -> None:
        """Basic content safety checks."""
        # Combine text for checking
        full_text = f"{story.title} {story.hook} {story.narration}".lower()
        
        # Check for unsafe patterns
        for pattern in self.UNSAFE_PATTERNS:
            if re.search(pattern, full_text, re.IGNORECASE):
                result.add_warning(f"Content may contain unsafe language matching: {pattern}")
        
        # Check hashtags
        for tag in story.hashtags:
            if not tag.startswith("#"):
                result.add_error(f"Hashtag must start with #: {tag}")
    
    def _compute_hash(self, story: StoryData) -> str:
        """Compute content hash for duplicate detection.
        
        Hashes the narration text to detect similar stories.
        """
        content = story.narration.lower().strip()
        content = re.sub(r"\s+", " ", content)
        return hashlib.sha256(content.encode()).hexdigest()[:16]
    
    def is_duplicate(self, story: StoryData, recent_hashes: list[str]) -> bool:
        """Check if story content is a duplicate.
        
        Args:
            story: Story to check
            recent_hashes: List of recent content hashes
            
        Returns:
            True if duplicate detected
        """
        return story.content_hash in recent_hashes

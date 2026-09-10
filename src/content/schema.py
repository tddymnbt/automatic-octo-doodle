"""Pydantic models for story data.

These models define the structure of generated stories.
They enforce validation at the data level.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class Scene(BaseModel):
    """A single scene in the story.
    
    Each scene maps to a visual asset category and has a duration.
    """
    
    description: str = Field(
        ...,
        min_length=5,
        max_length=200,
        description="Visual description for asset matching (e.g., 'rainy bedroom at night')"
    )
    duration_seconds: float = Field(
        ...,
        gt=0,
        le=30,
        description="Scene duration in seconds"
    )
    category: str = Field(
        default="",
        max_length=50,
        description="Asset category for matching (e.g., 'bedroom', 'forest', 'rain')"
    )
    
    @field_validator("category")
    @classmethod
    def normalize_category(cls, v: str) -> str:
        """Normalize category to lowercase."""
        return v.lower().strip()


class StoryData(BaseModel):
    """Complete story data for video generation.
    
    This is the output of the story generator and input
    to the video rendering pipeline.
    """
    
    title: str = Field(
        ...,
        min_length=5,
        max_length=100,
        description="Story title"
    )
    hook: str = Field(
        ...,
        min_length=10,
        max_length=200,
        description="Opening hook (first sentence to grab attention)"
    )
    narration: str = Field(
        ...,
        min_length=50,
        max_length=2000,
        description="Full narration text for TTS"
    )
    scenes: list[Scene] = Field(
        ...,
        min_length=1,
        max_length=10,
        description="List of visual scenes"
    )
    hashtags: list[str] = Field(
        default_factory=lambda: ["#ASMR", "#ShortStory", "#Relaxing"],
        max_length=10,
        description="Hashtags for social media"
    )
    caption: str = Field(
        default="",
        max_length=500,
        description="Caption for social media post"
    )
    content_hash: str = Field(
        default="",
        description="Hash of content for duplicate detection"
    )
    
    @field_validator("hashtags")
    @classmethod
    def ensure_hashtag_prefix(cls, v: list[str]) -> list[str]:
        """Ensure all hashtags start with #."""
        return [tag if tag.startswith("#") else f"#{tag}" for tag in v]
    
    @field_validator("narration")
    @classmethod
    def clean_narration(cls, v: str) -> str:
        """Clean narration text for TTS."""
        # Remove excessive whitespace
        import re
        v = re.sub(r"\s+", " ", v).strip()
        return v
    
    def estimate_duration_seconds(self) -> float:
        """Estimate total duration based on narration length.
        
        Assumes ~150 words per minute for calm ASMR narration.
        Returns estimated seconds.
        """
        word_count = len(self.narration.split())
        words_per_minute = 150
        minutes = word_count / words_per_minute
        return minutes * 60
    
    def scene_categories(self) -> list[str]:
        """Get unique scene categories for asset selection."""
        return list(set(scene.category for scene in self.scenes if scene.category))

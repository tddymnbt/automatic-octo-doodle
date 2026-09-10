"""Tests for content schema models."""

import pytest
from pydantic import ValidationError

from src.content.schema import Scene, StoryData


class TestScene:
    """Test Scene model."""
    
    def test_valid_scene(self):
        """Valid scene should create successfully."""
        scene = Scene(
            description="rainy bedroom at night",
            duration_seconds=7.0,
            category="bedroom",
        )
        assert scene.description == "rainy bedroom at night"
        assert scene.duration_seconds == 7.0
        assert scene.category == "bedroom"
    
    def test_scene_normalizes_category(self):
        """Category should be normalized to lowercase."""
        scene = Scene(
            description="dark forest",
            duration_seconds=5.0,
            category="Forest",
        )
        assert scene.category == "forest"
    
    def test_scene_empty_category(self):
        """Empty category should be allowed."""
        scene = Scene(
            description="mysterious room",
            duration_seconds=5.0,
            category="",
        )
        assert scene.category == ""
    
    def test_scene_short_description_fails(self):
        """Short description should fail validation."""
        with pytest.raises(ValidationError):
            Scene(
                description="hi",
                duration_seconds=5.0,
            )
    
    def test_scene_long_description_fails(self):
        """Long description should fail validation."""
        with pytest.raises(ValidationError):
            Scene(
                description="x" * 201,
                duration_seconds=5.0,
            )
    
    def test_scene_zero_duration_fails(self):
        """Zero duration should fail validation."""
        with pytest.raises(ValidationError):
            Scene(
                description="valid description",
                duration_seconds=0,
            )
    
    def test_scene_negative_duration_fails(self):
        """Negative duration should fail validation."""
        with pytest.raises(ValidationError):
            Scene(
                description="valid description",
                duration_seconds=-5.0,
            )
    
    def test_scene_long_duration_warning(self):
        """Long duration should still be allowed."""
        scene = Scene(
            description="long scene description",
            duration_seconds=30.0,
        )
        assert scene.duration_seconds == 30.0


class TestStoryData:
    """Test StoryData model."""
    
    def test_valid_story(self):
        """Valid story should create successfully."""
        story = StoryData(
            title="The Mystery Room",
            hook="Every night, she heard a sound from behind the wall.",
            narration="Every night, Mara heard a sound from behind the wall. It was soft, like whispering. She never could understand what it said.",
            scenes=[
                Scene(description="bedroom at night", duration_seconds=10.0, category="bedroom"),
                Scene(description="mysterious door", duration_seconds=10.0, category="hallway"),
            ],
        )
        assert story.title == "The Mystery Room"
        assert len(story.scenes) == 2
    
    def test_story_default_hashtags(self):
        """Default hashtags should be provided."""
        story = StoryData(
            title="Test Title",
            hook="Test hook sentence here.",
            narration="Test narration text that is long enough to pass validation rules.",
            scenes=[Scene(description="test scene", duration_seconds=5.0)],
        )
        assert "#ASMR" in story.hashtags
        assert "#ShortStory" in story.hashtags
    
    def test_story_hashtag_prefix_auto_added(self):
        """Hashtags without # should get prefix added."""
        story = StoryData(
            title="Test Title",
            hook="Test hook sentence here.",
            narration="Test narration text that is long enough to pass validation rules.",
            scenes=[Scene(description="test scene", duration_seconds=5.0)],
            hashtags=["Mystery", "ASMR"],
        )
        assert story.hashtags[0] == "#Mystery"
        assert story.hashtags[1] == "#ASMR"
    
    def test_story_narration_whitespace_cleaned(self):
        """Excessive whitespace in narration should be cleaned."""
        story = StoryData(
            title="Test Title",
            hook="Test hook sentence here.",
            narration="This  has   too    many     spaces   between   words.",
            scenes=[Scene(description="test scene", duration_seconds=5.0)],
        )
        assert "  " not in story.narration
    
    def test_story_short_title_fails(self):
        """Short title should fail validation."""
        with pytest.raises(ValidationError):
            StoryData(
                title="Hi",
                hook="Test hook sentence here.",
                narration="Test narration.",
                scenes=[Scene(description="test scene", duration_seconds=5.0)],
            )
    
    def test_story_long_title_fails(self):
        """Long title should fail validation."""
        with pytest.raises(ValidationError):
            StoryData(
                title="x" * 101,
                hook="Test hook sentence here.",
                narration="Test narration.",
                scenes=[Scene(description="test scene", duration_seconds=5.0)],
            )
    
    def test_story_short_hook_fails(self):
        """Short hook should fail validation."""
        with pytest.raises(ValidationError):
            StoryData(
                title="Valid Title Here",
                hook="Short",
                narration="Test narration.",
                scenes=[Scene(description="test scene", duration_seconds=5.0)],
            )
    
    def test_story_short_narration_fails(self):
        """Short narration should fail validation."""
        with pytest.raises(ValidationError):
            StoryData(
                title="Valid Title Here",
                hook="Valid hook sentence here.",
                narration="Too short",
                scenes=[Scene(description="test scene", duration_seconds=5.0)],
            )
    
    def test_story_no_scenes_fails(self):
        """Story with no scenes should fail validation."""
        with pytest.raises(ValidationError):
            StoryData(
                title="Valid Title Here",
                hook="Valid hook sentence here.",
                narration="Valid narration text that is long enough.",
                scenes=[],
            )
    
    def test_estimate_duration(self):
        """Duration estimation should work correctly."""
        # 150 words = 60 seconds at 150 WPM
        narration = " ".join(["word"] * 150)
        story = StoryData(
            title="Test Title",
            hook="Test hook sentence.",
            narration=narration,
            scenes=[Scene(description="test scene", duration_seconds=5.0)],
        )
        assert story.estimate_duration_seconds() == 60.0
    
    def test_scene_categories(self):
        """Scene categories should be extracted correctly."""
        story = StoryData(
            title="Test Title",
            hook="Test hook sentence.",
            narration="Test narration text that is long enough to pass validation.",
            scenes=[
                Scene(description="scene 1", duration_seconds=5.0, category="bedroom"),
                Scene(description="scene 2", duration_seconds=5.0, category="forest"),
                Scene(description="scene 3", duration_seconds=5.0, category="bedroom"),
            ],
        )
        categories = story.scene_categories()
        assert "bedroom" in categories
        assert "forest" in categories
        assert len(categories) == 2  # Unique categories only


class TestStoryDataEdgeCases:
    """Test edge cases for StoryData."""
    
    def test_story_with_empty_caption(self):
        """Empty caption should be allowed."""
        story = StoryData(
            title="Test Title",
            hook="Test hook sentence here.",
            narration="Test narration text that is long enough to pass validation rules.",
            scenes=[Scene(description="test scene", duration_seconds=5.0)],
            caption="",
        )
        assert story.caption == ""
    
    def test_story_serialization(self):
        """Story should serialize to dict correctly."""
        story = StoryData(
            title="Test Title",
            hook="Test hook sentence here.",
            narration="Test narration text that is long enough to pass validation rules.",
            scenes=[Scene(description="test scene", duration_seconds=5.0, category="bedroom")],
            hashtags=["#ASMR"],
        )
        data = story.model_dump()
        assert data["title"] == "Test Title"
        assert len(data["scenes"]) == 1
        assert data["scenes"][0]["category"] == "bedroom"
    
    def test_story_from_dict(self):
        """Story should deserialize from dict correctly."""
        data = {
            "title": "Test Title",
            "hook": "Test hook sentence here.",
            "narration": "Test narration text that is long enough to pass validation rules.",
            "scenes": [{"description": "test scene", "duration_seconds": 5.0}],
        }
        story = StoryData(**data)
        assert story.title == "Test Title"

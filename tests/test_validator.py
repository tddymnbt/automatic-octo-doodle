"""Tests for content validator."""

import pytest

from src.content.schema import Scene, StoryData
from src.content.validator import StoryValidator, ValidationResult


@pytest.fixture
def validator():
    """Create a validator with default settings."""
    return StoryValidator(
        min_duration=30,
        max_duration=60,
        target_duration=45,
    )


@pytest.fixture
def valid_story():
    """Create a valid test story."""
    return StoryData(
        title="The Room That Only Appeared in the Rain",
        hook="Every time it rained, Mara saw a door that wasn't there before.",
        narration=(
            "Every time it rained, Mara saw a door that wasn't there before. "
            "It appeared in the hallway, between the closet and the bathroom. "
            "The wood was dark, almost black, with a brass handle that glowed faintly. "
            "She never opened it. Not at first. But one night, the rain was heavier than usual, "
            "and the door was slightly ajar. She reached for the handle. It was warm. "
            "Behind it was a room she had never seen. A room filled with soft light "
            "and the sound of rain that never stopped."
        ),
        scenes=[
            Scene(description="rainy bedroom at night", duration_seconds=10.0, category="bedroom"),
            Scene(description="dark hallway with door", duration_seconds=10.0, category="hallway"),
            Scene(description="mysterious glowing room", duration_seconds=10.0, category="night"),
            Scene(description="rainy window view", duration_seconds=10.0, category="rain"),
        ],
        hashtags=["#ASMR", "#ShortStory", "#Mystery", "#Relaxing"],
        caption="A door that only appears in the rain... 🌧️",
    )


class TestValidationResult:
    """Test ValidationResult class."""
    
    def test_default_is_valid(self):
        """Default result should be valid."""
        result = ValidationResult()
        assert result.is_valid is True
        assert result.errors == []
        assert result.warnings == []
    
    def test_add_error(self):
        """Adding error should mark as invalid."""
        result = ValidationResult()
        result.add_error("Something wrong")
        assert result.is_valid is False
        assert "Something wrong" in result.errors
    
    def test_add_warning(self):
        """Adding warning should not affect validity."""
        result = ValidationResult()
        result.add_warning("Something minor")
        assert result.is_valid is True
        assert "Something minor" in result.warnings


class TestStoryValidator:
    """Test StoryValidator class."""
    
    def test_valid_story_passes(self, validator, valid_story):
        """Valid story should pass validation."""
        result = validator.validate(valid_story)
        assert result.is_valid is True
        assert result.errors == []
    
    def test_valid_story_has_hash(self, validator, valid_story):
        """Valid story should have content hash computed."""
        validator.validate(valid_story)
        assert valid_story.content_hash != ""
        assert len(valid_story.content_hash) == 16
    
    def test_short_title_fails(self, validator):
        """Short title should fail validation."""
        # Use model_construct to bypass Pydantic validation and test our validator
        story = StoryData.model_construct(
            title="Hi",
            hook="Valid hook sentence here.",
            narration="Valid narration text that is long enough to pass all validation rules.",
            scenes=[Scene.model_construct(description="test scene", duration_seconds=5.0)],
        )
        result = validator.validate(story)
        assert result.is_valid is False
        assert any("Title" in e for e in result.errors)
    
    def test_long_title_fails(self, validator):
        """Long title should fail validation."""
        story = StoryData.model_construct(
            title="x" * 101,
            hook="Valid hook sentence here.",
            narration="Valid narration text that is long enough to pass all validation rules.",
            scenes=[Scene.model_construct(description="test scene", duration_seconds=5.0)],
        )
        result = validator.validate(story)
        assert result.is_valid is False
        assert any("Title" in e for e in result.errors)
    
    def test_short_hook_fails(self, validator):
        """Short hook should fail validation."""
        story = StoryData.model_construct(
            title="Valid Title Here",
            hook="Short",
            narration="Valid narration text that is long enough to pass all validation rules.",
            scenes=[Scene.model_construct(description="test scene", duration_seconds=5.0)],
        )
        result = validator.validate(story)
        assert result.is_valid is False
        assert any("Hook" in e for e in result.errors)
    
    def test_short_narration_fails(self, validator):
        """Short narration should fail validation."""
        story = StoryData.model_construct(
            title="Valid Title Here",
            hook="Valid hook sentence here.",
            narration="Too short",
            scenes=[Scene.model_construct(description="test scene", duration_seconds=5.0)],
        )
        result = validator.validate(story)
        assert result.is_valid is False
        assert any("Narration" in e for e in result.errors)
    
    def test_no_scenes_fails(self, validator):
        """No scenes should fail validation."""
        story = StoryData.model_construct(
            title="Valid Title Here",
            hook="Valid hook sentence here.",
            narration="Valid narration text that is long enough to pass all validation rules.",
            scenes=[],
        )
        result = validator.validate(story)
        assert result.is_valid is False
        assert any("scene" in e.lower() for e in result.errors)
    
    def test_invalid_scene_category_warns(self, validator):
        """Invalid scene category should produce warning."""
        story = StoryData(
            title="Valid Title Here",
            hook="Valid hook sentence here.",
            narration="Valid narration text that is long enough to pass all validation rules.",
            scenes=[Scene(description="test scene", duration_seconds=5.0, category="invalid")],
        )
        result = validator.validate(story)
        assert any("category" in w.lower() for w in result.warnings)
    
    def test_valid_scene_categories(self, validator):
        """Valid scene categories should not warn."""
        story = StoryData(
            title="Valid Title Here",
            hook="Valid hook sentence here.",
            narration="Valid narration text that is long enough to pass all validation rules.",
            scenes=[
                Scene(description="bedroom scene", duration_seconds=5.0, category="bedroom"),
                Scene(description="forest scene", duration_seconds=5.0, category="forest"),
            ],
        )
        result = validator.validate(story)
        assert not any("category" in w.lower() for w in result.warnings)
    
    def test_short_narration_warns_duration(self, validator):
        """Short narration should warn about duration."""
        story = StoryData(
            title="Valid Title Here",
            hook="Valid hook sentence here.",
            narration="This is a short narration that is just barely long enough to pass the minimum length check but will not meet the duration requirement.",
            scenes=[Scene(description="test scene", duration_seconds=5.0)],
        )
        result = validator.validate(story)
        # Should have errors or warnings about duration
        assert len(result.errors) > 0 or len(result.warnings) > 0
    
    def test_content_hash_deterministic(self, validator):
        """Same narration should produce same hash."""
        story1 = StoryData(
            title="Title One",
            hook="Hook one here.",
            narration="Same narration text for both stories to ensure hash consistency.",
            scenes=[Scene(description="scene", duration_seconds=5.0)],
        )
        story2 = StoryData(
            title="Title Two",
            hook="Hook two here.",
            narration="Same narration text for both stories to ensure hash consistency.",
            scenes=[Scene(description="scene", duration_seconds=5.0)],
        )
        
        validator.validate(story1)
        validator.validate(story2)
        
        assert story1.content_hash == story2.content_hash
    
    def test_content_hash_different_for_different_content(self, validator):
        """Different narration should produce different hash."""
        story1 = StoryData(
            title="Title One",
            hook="Hook one here.",
            narration="This is the first story with unique content that differs.",
            scenes=[Scene(description="scene", duration_seconds=5.0)],
        )
        story2 = StoryData(
            title="Title Two",
            hook="Hook two here.",
            narration="This is the second story with completely different content.",
            scenes=[Scene(description="scene", duration_seconds=5.0)],
        )
        
        validator.validate(story1)
        validator.validate(story2)
        
        assert story1.content_hash != story2.content_hash
    
    def test_is_duplicate(self, validator):
        """Duplicate detection should work correctly."""
        story = StoryData(
            title="Test Title",
            hook="Test hook sentence for testing.",
            narration="Test narration for duplicate checking purposes that is long enough to pass validation.",
            scenes=[Scene(description="scene", duration_seconds=5.0)],
        )
        
        validator.validate(story)
        
        # Should be duplicate of itself
        assert validator.is_duplicate(story, [story.content_hash]) is True
        
        # Should not be duplicate of different hash
        assert validator.is_duplicate(story, ["different_hash_here"]) is False


class TestStoryValidatorCustomSettings:
    """Test StoryValidator with custom settings."""
    
    def test_custom_duration_constraints(self):
        """Custom duration constraints should be respected."""
        validator = StoryValidator(min_duration=10, max_duration=30, target_duration=20)
        
        # Story that fits within custom constraints (~12 seconds at 150 WPM)
        story = StoryData(
            title="Short Story",
            hook="A brief hook for testing purposes.",
            narration="A short story that fits within ten to thirty seconds of narration time for testing purposes with enough words to be valid and pass the minimum duration check.",
            scenes=[Scene(description="scene", duration_seconds=5.0)],
        )
        
        result = validator.validate(story)
        # Should not have duration errors with relaxed constraints
        duration_errors = [e for e in result.errors if "duration" in e.lower()]
        assert len(duration_errors) == 0

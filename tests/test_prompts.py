"""Tests for story prompts."""


from src.content.prompts import StoryPrompts


class TestStoryPrompts:
    """Test StoryPrompts class."""
    
    def test_story_prompt_formatting(self):
        """Story prompt should format correctly."""
        prompt = StoryPrompts.story_prompt(
            language="en",
            content_style="calm_mysterious",
            target_duration=45,
        )
        
        assert "en" in prompt
        assert "calm_mysterious" in prompt
        assert "45" in prompt
        assert "112 words" in prompt  # 45 * 150 / 60 = 112.5, truncated to 112
    
    def test_story_prompt_default_values(self):
        """Story prompt should use defaults when not specified."""
        prompt = StoryPrompts.story_prompt()
        
        assert "en" in prompt
        assert "calm_mysterious_atmospheric" in prompt
        assert "45" in prompt
    
    def test_story_prompt_json_structure(self):
        """Story prompt should include JSON structure."""
        prompt = StoryPrompts.story_prompt()
        
        assert '"title"' in prompt
        assert '"hook"' in prompt
        assert '"narration"' in prompt
        assert '"scenes"' in prompt
        assert '"hashtags"' in prompt
    
    def test_story_prompt_categories(self):
        """Story prompt should list available categories."""
        prompt = StoryPrompts.story_prompt()
        
        assert "bedroom" in prompt
        assert "forest" in prompt
        assert "rain" in prompt
        assert "ocean" in prompt
    
    def test_safety_prompt_formatting(self):
        """Safety prompt should format correctly."""
        prompt = StoryPrompts.safety_prompt(
            title="Test Title",
            narration="Test narration content.",
        )
        
        assert "Test Title" in prompt
        assert "Test narration content." in prompt
    
    def test_safety_prompt_truncates_long_narration(self):
        """Safety prompt should truncate long narration."""
        long_narration = "word " * 200
        prompt = StoryPrompts.safety_prompt(
            title="Test",
            narration=long_narration,
        )
        
        # Should not contain full narration
        assert long_narration not in prompt
    
    def test_story_system_instruction(self):
        """System instruction should contain key guidelines."""
        system = StoryPrompts.STORY_SYSTEM
        
        assert "original" in system.lower()
        assert "fictional" in system.lower()
        assert "asmr" in system.lower()
        assert "safe" in system.lower() or "harmful" in system.lower()
    
    def test_story_user_prompt_rules(self):
        """User prompt should contain generation rules."""
        prompt = StoryPrompts.story_prompt()
        
        assert "hook" in prompt.lower()
        assert "scene" in prompt.lower()
        assert "category" in prompt.lower()


class TestWordCountCalculation:
    """Test word count calculation in prompts."""
    
    def test_word_count_for_30_seconds(self):
        """30 seconds should target ~75 words."""
        prompt = StoryPrompts.story_prompt(target_duration=30)
        assert "75 words" in prompt
    
    def test_word_count_for_60_seconds(self):
        """60 seconds should target ~150 words."""
        prompt = StoryPrompts.story_prompt(target_duration=60)
        assert "150 words" in prompt
    
    def test_word_count_for_45_seconds(self):
        """45 seconds should target ~112 words."""
        prompt = StoryPrompts.story_prompt(target_duration=45)
        # 45 * 150 / 60 = 112.5, truncated to 112
        assert "112 words" in prompt

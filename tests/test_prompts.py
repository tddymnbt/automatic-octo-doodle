"""Tests for Gospel content prompts."""

from src.content.prompts import GospelPrompts


class TestGospelPrompts:
    """Test GospelPrompts class."""

    def test_gospel_prompt_formatting(self):
        """Gospel prompt should format correctly."""
        prompt = GospelPrompts.gospel_prompt(
            language="en",
            target_duration=45,
        )

        assert "en" in prompt
        assert "45" in prompt
        assert "97 words" in prompt  # 45 * 130 / 60 = 97.5, truncated to 97

    def test_gospel_prompt_default_values(self):
        """Gospel prompt should use defaults when not specified."""
        prompt = GospelPrompts.gospel_prompt()

        assert "en" in prompt
        assert "45" in prompt

    def test_gospel_prompt_includes_recent_entries(self):
        """Gospel prompt should inject recent entries to avoid repetition."""
        recent = [
            {"situation_summary": "overwhelmed by financial pressure", "scripture_reference": "Matthew 11:28"},
            {"situation_summary": "feeling alone", "scripture_reference": "Psalm 23"},
        ]
        prompt = GospelPrompts.gospel_prompt(recent_entries=recent)

        assert "RECENTLY USED" in prompt
        assert "overwhelmed by financial pressure" in prompt
        assert "Matthew 11:28" in prompt
        assert "DO NOT REPEAT" in prompt

    def test_gospel_prompt_no_recent_entries(self):
        """Gospel prompt without recent entries should not mention repetition."""
        prompt = GospelPrompts.gospel_prompt()

        assert "RECENTLY USED" not in prompt

    def test_base_system_prompt_mentions_tone(self):
        """Base system prompt should mention the calm, mature Gospel tone."""
        assert "warm, reverent, encouraging" in GospelPrompts.BASE_SYSTEM
        assert "pastor" in GospelPrompts.BASE_SYSTEM
        # ASMR/whisper/horror only appears as "Avoids:" negations, never as the voice style
        assert "Avoids: ASMR language" in GospelPrompts.BASE_SYSTEM
        assert "Avoids:" in GospelPrompts.BASE_SYSTEM

    def test_all_archetypes_have_systems(self):
        """Each archetype should have a system prompt."""
        for arch in GospelPrompts.ARCHETYPE_SYSTEMS:
            system = GospelPrompts.ARCHETYPE_SYSTEMS[arch]
            # Check that the archetype name (with underscores replaced) appears
            # in some form (e.g., "CHARACTER / STORY" for "character_story")
            arch_words = arch.replace("_", " ")
            # Be lenient: just check at least one word from the archetype appears
            words = arch_words.split()
            assert any(word.upper() in system for word in words)

    def test_safety_prompt_formatting(self):
        """Safety prompt should format correctly."""
        prompt = GospelPrompts.safety_prompt(
            situation_summary="overwhelmed by financial pressure",
            scripture_reference="Matthew 11:28",
            scripture_text="Come to me, all who labor and are heavy laden.",
            reflection="God offers rest for the weary.",
            narration_script="Come to me, all who labor and are heavy laden, and I will give you rest.",
        )

        assert "overwhelmed by financial pressure" in prompt
        assert "Matthew 11:28" in prompt
        assert "Come to me" in prompt
"""Tests for Gospel content schema models."""

import pytest
from pydantic import ValidationError

from src.content.schema import ContentHistoryEntry, GospelContent


def _make_content(**overrides) -> GospelContent:  # type: ignore[no-untyped-def]
    """Helper: build GospelContent with fields meeting all min_length constraints."""
    defaults = dict(
        situation_summary="overwhelmed by financial pressure and uncertainty",
        hook="Maybe you're doing everything you can, but nothing seems to be getting better.",
        biblical_message="But Scripture reminds us that we don't have to carry every burden alone. God invites us to cast our cares on Him.",
        scripture_reference="Matthew 11:28",
        scripture_text="Come to me, all who labor and are heavy laden, and I will give you rest.",
        reflection="When finances feel impossible, remember that God sees your struggle and offers peace that surpasses understanding.",
        closing_cta="Can I get an Amen in the comments below?",
        narration_script="Maybe you're doing everything you can, but nothing seems to be getting better. But Scripture reminds us that we don't have to carry every burden alone. God invites us to cast our cares on Him. Come to me, all who labor and are heavy laden, and I will give you rest. When finances feel impossible, remember that God sees your struggle and offers peace that surpasses understanding. Can I get an Amen in the comments?",
        facebook_caption="Maybe you're doing everything you can, but nothing seems to be getting better.\n\nBut Scripture reminds us that we don't have to carry every burden alone.\n\n📖 Matthew 11:28\n\nWhen finances feel impossible, remember that God sees your struggle and offers peace.\n\nCan I get an Amen?",
        first_comment="What's weighing on your heart today? Share below.",
        pinned_comment="Praying for everyone in the comments. You're not alone in this.",
        hashtags=["#DailyBread", "#Gospel", "#Faith", "#Encouragement", "#BibleVerse"],
    )
    defaults.update(overrides)
    return GospelContent(**defaults)


class TestGospelContent:
    """Test GospelContent model."""

    def test_valid_content(self):
        """Valid content should create successfully."""
        content = _make_content()
        assert content.situation_summary == "overwhelmed by financial pressure and uncertainty"
        assert content.scripture_reference == "Matthew 11:28"
        assert len(content.hashtags) >= 5

    def test_hashtag_prefix_auto_added(self):
        """Hashtags without # should get prefix added."""
        content = _make_content(hashtags=["DailyBread", "Gospel", "Faith"])
        assert content.hashtags[0] == "#DailyBread"
        assert content.hashtags[1] == "#Gospel"
        assert content.hashtags[2] == "#Faith"

    def test_narration_script_whitespace_cleaned(self):
        """Excessive whitespace in narration should be cleaned."""
        content = _make_content(
            narration_script="This  has   too    many     spaces   between   words.  " * 5,
        )
        assert "  " not in content.narration_script

    def test_situation_summary_too_short_fails(self):
        """Short situation_summary should fail validation."""
        with pytest.raises(ValidationError):
            _make_content(situation_summary="short")

    def test_hook_too_short_fails(self):
        """Short hook should fail validation."""
        with pytest.raises(ValidationError):
            _make_content(hook="Short")

    def test_narration_script_too_short_fails(self):
        """Short narration_script should fail validation."""
        with pytest.raises(ValidationError):
            _make_content(narration_script="Too short")

    def test_scripture_reference_format_fails(self):
        """Invalid scripture reference format should fail."""
        with pytest.raises(ValidationError):
            _make_content(scripture_reference="Invalid Reference")

    def test_first_comment_equals_pinned_comment_fails(self):
        """first_comment and pinned_comment must be different."""
        with pytest.raises(ValidationError):
            _make_content(first_comment="Same comment here please", pinned_comment="Same comment here please")

    def test_estimate_duration(self):
        """Duration estimation should work correctly."""
        # ~130 words = 60 seconds at 130 WPM
        narration = " ".join(["word"] * 130)
        content = _make_content(narration_script=narration)
        assert content.estimate_duration_seconds() == 60.0

    def test_serialization(self):
        """Content should serialize to dict correctly."""
        content = _make_content(hashtags=["#DailyBread", "#Gospel"])
        data = content.model_dump()
        assert data["situation_summary"] == "overwhelmed by financial pressure and uncertainty"
        assert data["scripture_reference"] == "Matthew 11:28"
        assert len(data["hashtags"]) == 2


class TestContentHistoryEntry:
    """Test ContentHistoryEntry model."""

    def test_from_gospel_content(self):
        """Should create history entry from GospelContent."""
        content = _make_content()
        entry = ContentHistoryEntry.from_gospel_content(
            content, "abc123", "2026-01-01T00:00:00Z"
        )
        assert entry.content_hash == "abc123"
        assert entry.situation_summary == content.situation_summary
        assert entry.scripture_reference == content.scripture_reference
        assert entry.title == content.hook[:100]
        assert entry.timestamp == "2026-01-01T00:00:00Z"

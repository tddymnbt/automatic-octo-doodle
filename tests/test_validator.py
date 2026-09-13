"""Tests for the Gospel content validator."""

import pytest

from src.content.prompts import GospelPrompts
from src.content.schema import GospelContent
from src.content.validator import GospelValidator


def make_content(**overrides) -> GospelContent:
    """Create a GospelContent fixture.

    Uses ``model_construct`` to bypass Pydantic field-level validation so
    tests can inject out-of-range values and exercise the validator's
    defensive checks (the schema itself would otherwise reject them at
    construction time).
    """
    defaults = {
        "situation_summary": "feeling overwhelmed by financial pressure",
        "hook": "Maybe you're doing everything you can, but nothing seems to be getting better.",
        "biblical_message": "But Scripture reminds us that we don't have to carry every burden alone.",
        "scripture_reference": "Matthew 11:28",
        "scripture_text": "Come to me, all who labor and are heavy laden, and I will give you rest.",
        "reflection": "When finances feel impossible, remember that God sees your struggle and offers peace.",
        "closing_cta": "Can I get an Amen in the comments?",
        "narration_script": (
            "Maybe you're doing everything you can, but nothing seems to be getting better. "
            "But Scripture reminds us that we don't have to carry every burden alone. "
            "Jesus says, Come to me, all who labor and are heavy laden, and I will give you rest. "
            "When finances feel impossible, remember that God sees your struggle and offers peace "
            "that surpasses understanding. Can I get an Amen in the comments?"
        ),
        "facebook_caption": (
            "Feeling overwhelmed by financial pressure?\n\n"
            "God invites you to cast every burden on Him.\n\n📖 Matthew 11:28\n\n"
            "He offers rest for the weary. You don't have to carry it alone.\n\n"
            "Can I get an Amen?\n\n#DailyBread #Gospel #Faith #Encouragement #BibleVerse"
        ),
        "first_comment": "What's weighing on your heart today? Share below 👇",
        "pinned_comment": "Praying for everyone in the comments. You're not alone.",
        "hashtags": ["#DailyBread", "#Gospel", "#Faith", "#Encouragement", "#BibleVerse"],
    }
    defaults.update(overrides)
    return GospelContent.model_construct(**defaults)


@pytest.fixture
def validator():
    return GospelValidator()


class TestValidateStructure:
    """Test structural validation."""

    def test_valid_content_passes(self, validator):
        """Valid content should pass validation."""
        result = validator.validate(make_content())
        assert result.is_valid is True
        assert result.errors == []

    def test_short_situation_fails(self, validator):
        """Too-short situation_summary should fail."""
        result = validator.validate(make_content(situation_summary="short"))
        assert not result.is_valid
        assert any("situation_summary" in e for e in result.errors)

    def test_short_hook_fails(self, validator):
        """Too-short hook should fail."""
        result = validator.validate(make_content(hook="Too short"))
        assert not result.is_valid
        assert any("hook" in e for e in result.errors)

    def test_short_narration_fails(self, validator):
        """Too-short narration should fail."""
        result = validator.validate(make_content(narration_script="Too short"))
        assert not result.is_valid
        assert any("narration_script" in e for e in result.errors)

    def test_hashtag_missing_prefix_fails(self, validator):
        """Hashtag without # should fail."""
        result = validator.validate(
            make_content(hashtags=["DailyBread", "#Gospel"])
        )
        assert not result.is_valid
        assert any("hashtag" in e.lower() for e in result.errors)


class TestValidateDuration:
    """Test duration validation."""

    def test_too_short_fails(self, validator):
        """Very short narration should fail duration check."""
        # ~5 words
        result = validator.validate(
            make_content(narration_script="just a few words here")
        )
        assert not result.is_valid
        assert any("duration" in e.lower() or "Narration" in e for e in result.errors)

    def test_warns_on_estimate(self, validator):
        """Valid content should add a duration warning with estimate."""
        result = validator.validate(make_content())
        assert any("Estimated duration" in w for w in result.warnings)


class TestValidateScripture:
    """Test scripture validation."""

    def test_bad_reference_warns(self, validator):
        """Non-standard reference should warn, not fail."""
        result = validator.validate(make_content(scripture_reference="Matthew"))
        assert any("reference format" in w for w in result.warnings)

    def test_short_scripture_text_fails(self, validator):
        """Too-short scripture text should fail."""
        result = validator.validate(make_content(scripture_text="Short"))
        assert not result.is_valid
        assert any("Scripture text" in e for e in result.errors)


class TestValidateConsistency:
    """Test consistency validation."""

    def test_same_comments_fail(self, validator):
        """Matching first/pinned comments should fail."""
        result = validator.validate(
            make_content(first_comment="Same comment text here.", pinned_comment="Same comment text here.")
        )
        assert not result.is_valid
        assert any("must be different" in e for e in result.errors)

    def test_caption_missing_reference_warns(self, validator):
        """Caption missing scripture reference should warn."""
        result = validator.validate(
            make_content(facebook_caption="A caption without the scripture reference anywhere in it.")
        )
        assert any("doesn't include scripture" in w for w in result.warnings)

    def test_no_gospel_hashtag_warns(self, validator):
        """Missing gospel hashtags should warn."""
        result = validator.validate(
            make_content(hashtags=["#foo", "#bar"])
        )
        assert any("gospel-appropriate hashtags" in w for w in result.warnings)


class TestContentHash:
    """Test duplicate detection."""

    def test_hash_is_deterministic(self, validator):
        """Same content should produce same hash."""
        c1 = make_content()
        c2 = make_content()
        validator.validate(c1)
        validator.validate(c2)
        assert c1.content_hash == c2.content_hash

    def test_different_content_different_hash(self, validator):
        """Different content should produce different hash."""
        c1 = make_content()
        c2 = make_content(situation_summary="different situation entirely here")
        validator.validate(c1)
        validator.validate(c2)
        assert c1.content_hash != c2.content_hash

    def test_is_duplicate(self, validator):
        """is_duplicate should detect known hashes."""
        c = make_content()
        validator.validate(c)
        assert validator.is_duplicate(c, [c.content_hash]) is True
        assert validator.is_duplicate(c, ["0000000000000000"]) is False


class TestSafetyValidation:
    """Test content safety checks."""

    def test_unsafe_pattern_warns(self, validator):
        """Violent language should produce a warning."""
        result = validator.validate(
            make_content(situation_summary="exposed to violent crime in the neighborhood")
        )
        assert any("unsafe language" in w for w in result.warnings)


class TestCheckDiversity:
    """Near-duplicate detection via Jaccard similarity."""

    def test_empty_history_valid(self, validator):
        """No history -> diversity check passes (valid)."""
        result = validator.check_diversity(make_content(), [])
        assert result.is_valid is True

    def test_distinct_content_valid(self, validator):
        """A clearly different story passes."""
        content = make_content(
            narration_script="The lilies of the field do not toil. God clothes creation in beauty.",
        )
        history = [
            "The frantic pace of the city never lets you rest or find peace anywhere.",
            "Greed in the marketplace twists good gifts into chains that bind us all.",
        ]
        result = validator.check_diversity(content, history)
        assert result.is_valid is True

    def test_near_duplicate_story_flagged(self, validator):
        """A near-identical story fails."""
        content = make_content(
            narration_script="The shepherd leads me beside still waters and restores my weary soul.",
        )
        history = [
            "The shepherd leads me beside still waters and restores my weary soul each day.",
        ]
        result = validator.check_diversity(content, history)
        assert not result.is_valid
        assert any("Narration too similar" in e for e in result.errors)

    def test_caption_duplication_flagged(self, validator):
        """A near-identical caption fails."""
        content = make_content(
            facebook_caption="Cast every burden on Him for He cares for you. Rest in His peace.",
        )
        content.narration_script = "a completely unrelated narration about mountains and valleys"
        history_texts = ["unrelated history text entirely"]
        history_captions = ["Cast every burden on Him for He cares for you. Rest in His peace."]
        result = validator.check_diversity(
            content, history_texts, history_captions=history_captions
        )
        assert not result.is_valid
        assert any("Caption too similar" in e for e in result.errors)


class TestCaptionCtaVariety:
    """Verify caption/CTA variety is possible (structure-driven)."""

    def test_all_cta_patterns_are_unique(self):
        """CTA_PATTERNS contains no duplicates."""
        from src.content.diversity import CTA_PATTERNS

        assert len(CTA_PATTERNS) == len(set(CTA_PATTERNS))
        assert len(CTA_PATTERNS) >= 12  # at least a dozen variants

    def test_all_caption_styles_are_unique(self):
        """CAPTION_STYLES contains no duplicates."""
        from src.content.diversity import CAPTION_STYLES

        assert len(CAPTION_STYLES) == len(set(CAPTION_STYLES))
        assert len(CAPTION_STYLES) >= 6

    def test_prompt_includes_cta_pattern_when_provided(self):
        """Gospel prompt includes CTA pattern directive."""
        prompt = GospelPrompts.gospel_prompt(
            cta_pattern="affirm_truth",
        )
        assert "cta_pattern: affirm_truth" in prompt

    def test_prompt_includes_caption_style_when_provided(self):
        """Gospel prompt includes caption style directive."""
        prompt = GospelPrompts.gospel_prompt(
            caption_style="devotional_style",
        )
        assert "caption_style: devotional_style" in prompt
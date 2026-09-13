"""Pydantic models for Gospel / Daily Bread content.

These models define the structure of generated Gospel content.
They enforce validation at the data level and serve as the single
source of truth for narration, captions, comments, and subtitles.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator, model_validator


class GospelContent(BaseModel):
    """Complete Gospel content for video generation and publishing.

    This is the single source of truth for all outputs:
    - narration_script -> TTS
    - narration_script -> subtitles (via speech-aligned segments)
    - facebook_caption -> Reel description
    - first_comment -> first comment on post
    - pinned_comment -> pinned comment on post
    - scripture_reference -> history tracking (anti-repetition)
    - situation_summary -> history tracking (anti-repetition)
    """

    # === SITUATION & HOOK ===
    situation_summary: str = Field(
        ...,
        min_length=10,
        max_length=200,
        description="Brief summary of the real-life situation (e.g., 'feeling overwhelmed by financial pressure')",
    )
    hook: str = Field(
        ...,
        min_length=15,
        max_length=250,
        description="Opening hook — the first sentence spoken/read, relatable and engaging",
    )

    # === BIBLICAL RESPONSE ===
    biblical_message: str = Field(
        ...,
        min_length=30,
        max_length=800,
        description="What God's Word teaches about this situation — the core biblical truth",
    )

    # === SCRIPTURE ===
    scripture_reference: str = Field(
        ...,
        min_length=3,
        max_length=50,
        description="Bible reference (e.g., 'Matthew 11:28', 'Psalm 23:1-4', 'Philippians 4:6-7')",
    )
    scripture_text: str = Field(
        ...,
        min_length=20,
        max_length=500,
        description="Actual Scripture text (quoted accurately, not paraphrased)",
    )

    # === REFLECTION & APPLICATION ===
    reflection: str = Field(
        ...,
        min_length=30,
        max_length=800,
        description="Brief reflection: how this Scripture applies to the viewer's current situation",
    )

    # === CTA ===
    closing_cta: str = Field(
        ...,
        min_length=15,
        max_length=200,
        description="Natural engagement CTA (e.g., 'Can I get an Amen in the comments?')",
    )

    # === FULL NARRATION SCRIPT (SINGLE SOURCE) ===
    narration_script: str = Field(
        ...,
        min_length=100,
        max_length=3000,
        description="Complete narration for TTS — combines hook, biblical message, scripture, reflection, CTA into spoken form",
    )

    # === SOCIAL MEDIA OUTPUTS (DERIVED FROM SAME CONTENT) ===
    facebook_caption: str = Field(
        ...,
        min_length=50,
        max_length=500,
        description="Facebook Reel caption/description — social-media-formatted summary of the message",
    )
    first_comment: str = Field(
        ...,
        min_length=20,
        max_length=300,
        description="First comment to post — invites viewers to share their situation",
    )
    pinned_comment: str = Field(
        ...,
        min_length=20,
        max_length=300,
        description="Pinned comment — invites deeper conversation, different from first comment",
    )

    # === METADATA ===
    hashtags: list[str] = Field(
        default_factory=lambda: ["#DailyBread", "#Gospel", "#Faith", "#Encouragement", "#BibleVerse"],
        max_length=12,
        description="Hashtags for social media",
    )
    content_hash: str = Field(
        default="",
        description="Hash of content for duplicate detection (set after generation)",
    )

    # === CONTENT-DIVERSITY METADATA (Phase C) ===
    # These drive archetype/theme/scripture/structure rotation and are
    # persisted to run history. All default to empty so fully manual
    # GospelContent construction (tests, legacy callers) keeps working.
    archetype: str = Field(
        default="",
        max_length=40,
        description="Content archetype (e.g. spiritual_principle, scripture_first)",
    )
    primary_theme: str = Field(
        default="",
        max_length=80,
        description="Primary spiritual theme/principle (e.g. gratitude, forgiveness)",
    )
    secondary_themes: list[str] = Field(
        default_factory=list,
        max_length=8,
        description="Secondary themes touched by the piece",
    )
    tone: str = Field(
        default="",
        max_length=40,
        description="Tone tag (e.g. reflective, exhorting, tender)",
    )
    opening_pattern: str = Field(
        default="",
        max_length=60,
        description="Classifier tag for how the piece opens (e.g. reflective_question)",
    )
    conclusion_pattern: str = Field(
        default="",
        max_length=60,
        description="Classifier tag for how the piece concludes",
    )
    caption_style: str = Field(
        default="",
        max_length=60,
        description="Caption structure tag (e.g. verse_first, question_first)",
    )
    cta_pattern: str = Field(
        default="",
        max_length=60,
        description="Call-to-action classifier tag (e.g. comment_share, reflection_prompt)",
    )
    key_concepts: list[str] = Field(
        default_factory=list,
        max_length=20,
        description="Short keywords summarizing the piece for near-duplicate analysis",
    )

    # JSON-encoded convenience for history storage (single-line JSONL rows).
    @property
    def secondary_themes_json(self) -> str:
        import json

        return json.dumps(self.secondary_themes)

    @property
    def key_concepts_json(self) -> str:
        import json

        return json.dumps(self.key_concepts)

    @property
    def scripture_book(self) -> str:
        """Derive the Bible book from scripture_reference (empty if unparsable)."""
        from src.content.diversity import parse_scripture_book

        return parse_scripture_book(self.scripture_reference)

    @field_validator("hashtags")
    @classmethod
    def ensure_hashtag_prefix(cls, v: list[str]) -> list[str]:
        """Ensure all hashtags start with #."""
        return [tag if tag.startswith("#") else f"#{tag}" for tag in v]

    @field_validator("narration_script")
    @classmethod
    def clean_narration(cls, v: str) -> str:
        """Clean narration text for TTS."""
        import re
        v = re.sub(r"\s+", " ", v).strip()
        return v

    @field_validator("scripture_reference")
    @classmethod
    def validate_scripture_reference(cls, v: str) -> str:
        """Basic format check for scripture reference."""
        v = v.strip()
        if not v:
            raise ValueError("Scripture reference cannot be empty")
        # Accept common formats: "John 3:16", "Psalm 23:1-4", "Philippians 4:6-7"
        import re
        if not re.match(r"^[A-Za-z]+\s+\d+:\d+(?:-\d+)?$", v) and not re.match(
            r"^\d?\s*[A-Za-z]+\s+\d+:\d+(?:-\d+)?$", v
        ):
            raise ValueError(
                f"Scripture reference must be in format 'Book Chapter:Verse' or 'Book Chapter:Verse-Verse', got: {v}"
            )
        return v

    @model_validator(mode="after")
    def check_comments_distinct(self) -> GospelContent:
        """first_comment and pinned_comment must be different."""
        if self.first_comment.strip() == self.pinned_comment.strip():
            raise ValueError(
                "first_comment and pinned_comment must be different"
            )
        return self

    def estimate_duration_seconds(self) -> float:
        """Estimate total duration based on narration length.

        Assumes ~130 words per minute for calm Gospel narration (slower than ASMR).
        Returns estimated seconds.
        """
        word_count = len(self.narration_script.split())
        words_per_minute = 130  # slower, deliberate Gospel delivery
        minutes = word_count / words_per_minute
        return minutes * 60


class ContentHistoryEntry(BaseModel):
    """Lightweight history entry for anti-repetition tracking."""

    content_hash: str
    situation_summary: str
    scripture_reference: str
    title: str
    timestamp: str

    @classmethod
    def from_gospel_content(cls, content: GospelContent, content_hash: str, timestamp: str) -> ContentHistoryEntry:
        return cls(
            content_hash=content_hash,
            situation_summary=content.situation_summary,
            scripture_reference=content.scripture_reference,
            title=content.hook[:100],  # use hook as title proxy
            timestamp=timestamp,
        )
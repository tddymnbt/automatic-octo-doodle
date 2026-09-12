"""Content validator for Gospel / Daily Bread content.

Validates Gospel content against structural, theological, and business rules.
"""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass, field

from src.content.schema import GospelContent

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


class GospelValidator:
    """Validates Gospel content against requirements.

    Validation rules:
    1. Structure: All required fields present and valid
    2. Duration: Narration fits target duration
    3. Scripture: Reference format and text match
    4. Content: No unsafe or theologically problematic content
    5. Uniqueness: Content hash for duplicate detection
    6. Consistency: All social media outputs align with core message
    """

    # Duration constraints
    MIN_DURATION_SECONDS = 20
    MAX_DURATION_SECONDS = 60
    TARGET_DURATION_SECONDS = 45

    # Words per minute for Gospel narration
    GOSPEL_WPM = 130

    # Content safety patterns
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
        """Initialize validator with duration constraints."""
        self.min_duration = min_duration
        self.max_duration = max_duration
        self.target_duration = target_duration

    def validate(self, content: GospelContent) -> ValidationResult:
        """Validate Gospel content against all rules."""
        result = ValidationResult()

        # Run all validation checks
        self._validate_structure(content, result)
        self._validate_duration(content, result)
        self._validate_scripture(content, result)
        self._validate_content_safety(content, result)
        self._validate_consistency(content, result)

        # Generate content hash
        content.content_hash = self._compute_hash(content)

        if result.is_valid:
            logger.info(f"Gospel content validation passed: '{content.hook[:60]}...'")
        else:
            logger.warning(f"Gospel content validation failed: {result.errors}")

        return result

    def _validate_structure(self, content: GospelContent, result: ValidationResult) -> None:
        """Validate required fields and lengths."""
        # situation_summary
        if len(content.situation_summary) < 10:
            result.add_error("situation_summary too short (minimum 10 characters)")
        if len(content.situation_summary) > 200:
            result.add_error("situation_summary too long (maximum 200 characters)")

        # hook
        if len(content.hook) < 15:
            result.add_error("hook too short (minimum 15 characters)")
        if len(content.hook) > 250:
            result.add_error("hook too long (maximum 250 characters)")

        # biblical_message
        if len(content.biblical_message) < 30:
            result.add_error("biblical_message too short (minimum 30 characters)")
        if len(content.biblical_message) > 800:
            result.add_error("biblical_message too long (maximum 800 characters)")

        # scripture_reference
        if len(content.scripture_reference) < 3:
            result.add_error("scripture_reference too short")
        if len(content.scripture_reference) > 50:
            result.add_error("scripture_reference too long")

        # scripture_text
        if len(content.scripture_text) < 20:
            result.add_error("scripture_text too short (minimum 20 characters)")
        if len(content.scripture_text) > 500:
            result.add_error("scripture_text too long (maximum 500 characters)")

        # reflection
        if len(content.reflection) < 30:
            result.add_error("reflection too short (minimum 30 characters)")
        if len(content.reflection) > 800:
            result.add_error("reflection too long (maximum 800 characters)")

        # closing_cta
        if len(content.closing_cta) < 15:
            result.add_error("closing_cta too short (minimum 15 characters)")
        if len(content.closing_cta) > 200:
            result.add_error("closing_cta too long (maximum 200 characters)")

        # narration_script
        if len(content.narration_script) < 100:
            result.add_error("narration_script too short (minimum 100 characters)")
        if len(content.narration_script) > 3000:
            result.add_error("narration_script too long (maximum 3000 characters)")

        # facebook_caption
        if len(content.facebook_caption) < 50:
            result.add_error("facebook_caption too short (minimum 50 characters)")
        if len(content.facebook_caption) > 500:
            result.add_error("facebook_caption too long (maximum 500 characters)")

        # first_comment
        if len(content.first_comment) < 20:
            result.add_error("first_comment too short (minimum 20 characters)")
        if len(content.first_comment) > 300:
            result.add_error("first_comment too long (maximum 300 characters)")

        # pinned_comment
        if len(content.pinned_comment) < 20:
            result.add_error("pinned_comment too short (minimum 20 characters)")
        if len(content.pinned_comment) > 300:
            result.add_error("pinned_comment too long (maximum 300 characters)")

        # hashtags
        for tag in content.hashtags:
            if not tag.startswith("#"):
                result.add_error(f"Hashtag must start with #: {tag}")

    def _validate_duration(self, content: GospelContent, result: ValidationResult) -> None:
        """Validate narration duration fits target range."""
        estimated_seconds = content.estimate_duration_seconds()

        if estimated_seconds < self.min_duration:
            result.add_error(
                f"Narration too short ({estimated_seconds:.0f}s < {self.min_duration}s minimum). "
                f"Add more content to narration_script."
            )
        elif estimated_seconds > self.max_duration:
            result.add_error(
                f"Narration too long ({estimated_seconds:.0f}s > {self.max_duration}s maximum). "
                f"Trim narration_script."
            )
        else:
            result.add_warning(
                f"Estimated duration: {estimated_seconds:.0f}s (target ~{self.target_duration}s)"
            )

    def _validate_scripture(self, content: GospelContent, result: ValidationResult) -> None:
        """Validate scripture reference format and basic consistency."""
        ref = content.scripture_reference.strip()
        text = content.scripture_text.strip()

        # Basic reference format validation
        import re
        if not re.match(r"^\d?\s*[A-Za-z]+\s+\d+:\d+(?:-\d+)?$", ref):
            result.add_warning(
                f"Scripture reference format may be non-standard: '{ref}'. "
                f"Expected format like 'John 3:16' or 'Psalm 23:1-4'."
            )

        # Ensure scripture text is not empty and reasonably long
        if len(text) < 20:
            result.add_error("Scripture text appears too short to be a real verse")

        # Check that reflection doesn't just repeat scripture
        reflection_words = set(content.reflection.lower().split())
        scripture_words = set(text.lower().split())
        overlap = len(reflection_words & scripture_words)
        if overlap > len(scripture_words) * 0.7:
            result.add_warning(
                "Reflection appears to mostly repeat scripture text rather than apply it"
            )

    def _validate_content_safety(self, content: GospelContent, result: ValidationResult) -> None:
        """Basic content safety and theological checks."""
        # Check for unsafe patterns in all text fields
        full_text = (
            f"{content.situation_summary} {content.hook} {content.biblical_message} "
            f"{content.reflection} {content.closing_cta} {content.narration_script} "
            f"{content.facebook_caption} {content.first_comment} {content.pinned_comment}"
        ).lower()

        for pattern in self.UNSAFE_PATTERNS:
            if re.search(pattern, full_text, re.IGNORECASE):
                result.add_warning(f"Content may contain unsafe language matching: {pattern}")

        # Theological red flags (basic)
        theological_red_flags = [
            (r"\b(name it and claim it)\b", "Prosperity gospel language"),
            (r"\b(seed faith)\b", "Seed faith theology"),
            (r"\b(sow a seed)\b", "Seed faith language"),
            (r"\b(guaranteed|guarantee)\b.*\b(healing|money|breakthrough)\b", "Guaranteed outcomes"),
            (r"\b(if you have enough faith)\b", "Faith-as-formula language"),
        ]
        for pattern, description in theological_red_flags:
            if re.search(pattern, full_text, re.IGNORECASE):
                result.add_warning(f"Theological concern: {description} detected")

    def _validate_consistency(self, content: GospelContent, result: ValidationResult) -> None:
        """Validate that all social media outputs align with core message."""
        # Check that facebook_caption mentions the scripture reference
        if content.scripture_reference not in content.facebook_caption:
            result.add_warning(
                f"Facebook caption doesn't include scripture reference ({content.scripture_reference})"
            )

        # Check that first_comment and pinned_comment are different
        if content.first_comment.strip().lower() == content.pinned_comment.strip().lower():
            result.add_error("first_comment and pinned_comment must be different")

        # Check that both comments relate to the situation
        situation_keywords = set(content.situation_summary.lower().split())
        first_comment_words = set(content.first_comment.lower().split())
        pinned_words = set(content.pinned_comment.lower().split())

        # Basic relevance check
        if not (situation_keywords & first_comment_words):
            result.add_warning("first_comment may not relate to the situation")

        if not (situation_keywords & pinned_words):
            result.add_warning("pinned_comment may not relate to the situation")

        # Check hashtags contain gospel-appropriate tags
        gospel_tags = {"#dailybread", "#gospel", "#faith", "#encouragement", "#bibleverse", "#christian"}
        has_gospel_tag = any(tag.lower() in gospel_tags for tag in content.hashtags)
        if not has_gospel_tag:
            result.add_warning("Consider adding gospel-appropriate hashtags (#DailyBread, #Gospel, #Faith, etc.)")

    def _compute_hash(self, content: GospelContent) -> str:
        """Compute content hash for duplicate detection."""
        # Hash narration + scripture + situation for substantive duplicate detection
        h = hashlib.sha256()
        h.update(content.narration_script.encode("utf-8"))
        h.update(content.scripture_reference.encode("utf-8"))
        h.update(content.situation_summary.encode("utf-8"))
        return h.hexdigest()[:16]

    def is_duplicate(self, content: GospelContent, recent_hashes: list[str]) -> bool:
        """Check if content is a duplicate of recent content."""
        return content.content_hash in recent_hashes
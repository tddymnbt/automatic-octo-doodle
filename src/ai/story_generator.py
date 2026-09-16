"""Gospel content generator using Gemini AI (Phase C+: archetype-driven).

This module generates original Daily Bread / Gospel encouragement content
using the Gemini API. It handles prompt construction, response parsing,
validation, and diversity-aware generation with rotation across archetypes.
"""

from __future__ import annotations

import hashlib
import json
import logging
import random
import time
from dataclasses import dataclass
from typing import Any

from src.ai.client import GeminiClient, GeminiClientError
from src.config import settings
from src.content.diversity import (
    ARCHETYPE_PRINCIPLES,
    ARCHETYPES,
    PRINCIPLES,
    SLOT_ARCHETYPE_BIAS,
    SLOT_PRINCIPLE_BIAS,
    select_caption_style,
    select_conclusion_pattern,
    select_cta_pattern,
    select_opening_pattern,
    select_with_slot_bias,
)
from src.content.prompts import GospelPrompts
from src.content.schema import GospelContent
from src.content.validator import GospelValidator, ValidationResult
from src.history.store import _normalize_scripture

logger = logging.getLogger(__name__)


@dataclass
class GenerationResult:
    """Result of Gospel content generation."""

    success: bool
    content: GospelContent | None = None
    validation: ValidationResult | None = None
    error: str | None = None
    attempts: int = 0
    generation_time_ms: int = 0


class GospelGenerator:
    """Generates Daily Gospel encouragement content using Gemini AI.

    This generator:
    1. Selects an underused content archetype (weighted LSUR)
    2. Selects a principle/theme within that archetype
    3. Consults history for recency/coverage to avoid repetition
    4. Constructs archetype-specific prompts with anti-repetition context
    5. Calls Gemini API for content generation
    6. Parses and validates the response
    7. Computes content hash for duplicate detection
    8. Returns structured GospelContent
    """

    def __init__(
        self,
        client: GeminiClient | None = None,
        validator: GospelValidator | None = None,
    ) -> None:
        """Initialize the Gospel generator.

        Args:
            client: Optional GeminiClient instance. Creates new if not provided.
            validator: Optional GospelValidator instance. Creates new if not provided.
        """
        self._client = client or GeminiClient()
        self._validator = validator or GospelValidator(
            min_duration=settings.min_duration_seconds,
            max_duration=settings.max_duration_seconds,
            target_duration=settings.target_duration_seconds,
        )
        self._model = settings.ai_model
        # Seed random for controlled rotation across runs
        self._rng = random.Random()

    def generate(
        self,
        language: str | None = None,
        max_attempts: int = 3,
        blocked_scriptures: list[str] | None = None,
    ) -> GenerationResult:
        """Generate a new Gospel content piece.

        Args:
            language: Content language (default: from settings)
            max_attempts: Maximum generation attempts
            blocked_scriptures: Scriptures on cooldown (exact refs) that must
                be avoided. Candputed in ``main`` from history and enforced
                here so regeneration naturally avoids them.

        Returns:
            GenerationResult with content or error
        """
        language = language or settings.story_language

        start_time = time.time()
        last_error: str | None = None

        for attempt in range(1, max_attempts + 1):
            logger.info(f"Generating Gospel content (attempt {attempt}/{max_attempts})")

            try:
                # Generate content
                content = self._call_gemini(language, blocked_scriptures)

                # Compute content hash
                content.content_hash = self._compute_hash(content)

                # Hard cooldown gate: reject a scripture that was recently used
                if blocked_scriptures:
                    norm_ref = _normalize_scripture(content.scripture_reference)
                    norm_blocked = {
                        _normalize_scripture(v)
                        for v in blocked_scriptures
                        if _normalize_scripture(v)
                    }
                    if norm_ref and norm_ref in norm_blocked:
                        logger.warning(
                            f"Scripture on cooldown (attempt {attempt}): "
                            f"{content.scripture_reference} — regenerating"
                        )
                        last_error = (
                            f"Scripture on cooldown: {content.scripture_reference}"
                        )
                        continue

                # Validate
                validation = self._validator.validate(content)

                if validation.is_valid:
                    elapsed = int((time.time() - start_time) * 1000)
                    logger.info(
                        f"Gospel content generated successfully in {elapsed}ms: "
                        f"'{content.hook[:60]}...' (archetype={content.archetype})"
                    )
                    return GenerationResult(
                        success=True,
                        content=content,
                        validation=validation,
                        attempts=attempt,
                        generation_time_ms=elapsed,
                    )
                else:
                    logger.warning(
                        f"Gospel content validation failed (attempt {attempt}): "
                        f"{validation.errors}"
                    )
                    last_error = f"Validation failed: {'; '.join(validation.errors)}"

            except GeminiClientError as e:
                logger.error(f"Gemini API error (attempt {attempt}): {e}")
                last_error = str(e)

                # Don't retry auth errors
                if "auth" in str(e).lower() or "invalid" in str(e).lower():
                    break

            except Exception as e:
                logger.error(f"Unexpected error (attempt {attempt}): {e}")
                last_error = f"Unexpected error: {type(e).__name__}"

        elapsed = int((time.time() - start_time) * 1000)
        return GenerationResult(
            success=False,
            error=last_error or "Generation failed after all attempts",
            attempts=max_attempts,
            generation_time_ms=elapsed,
        )

    def _call_gemini(
        self, language: str, blocked_scriptures: list[str] | None = None
    ) -> GospelContent:
        """Call Gemini API to generate Gospel content with archetype/rotation logic.

        Args:
            language: Content language

        Returns:
            Parsed GospelContent

        Raises:
            GeminiClientError: API call failed
        """
        # Load recent history for anti-repetition + rotation context
        recent_entries: list[dict] = []
        recent_principles: list[str] = []
        recent_verses: list[str] = []
        recent_books: list[str] = []
        recent_openings: list[str] = []
        recent_conclusions: list[str] = []
        recent_caption_styles: list[str] = []
        recent_cta_patterns: list[str] = []
        history = None

        try:
            from src.history.store import HistoryStore

            history = HistoryStore()
            # Last 30 published records for diversity context
            for record in history.load_history():
                if record.status != "published" or record.dry_run:
                    continue
                if record.situation_summary and record.scripture_reference:
                    recent_entries.append({
                        "situation_summary": record.situation_summary,
                        "scripture_reference": record.scripture_reference,
                    })
                if record.primary_theme:
                    recent_principles.append(record.primary_theme)
                if record.scripture_reference:
                    recent_verses.append(record.scripture_reference)
                if record.scripture_book:
                    recent_books.append(record.scripture_book)
                if record.opening_pattern:
                    recent_openings.append(record.opening_pattern)
                if record.conclusion_pattern:
                    recent_conclusions.append(record.conclusion_pattern)
                if record.caption_style:
                    recent_caption_styles.append(record.caption_style)
                if record.cta_pattern:
                    recent_cta_patterns.append(record.cta_pattern)
            # Bound prompt size
            recent_entries = recent_entries[-20:]
            recent_principles = recent_principles[-10:]
            recent_verses = recent_verses[-10:]
            recent_books = recent_books[-10:]
            recent_openings = recent_openings[-5:]
            recent_conclusions = recent_conclusions[-5:]
            recent_caption_styles = recent_caption_styles[-5:]
            recent_cta_patterns = recent_cta_patterns[-5:]
        except Exception:
            logger.debug("Could not load history for diversity; continuing without")

        # ---- ARCHETYPE & PRINCIPLE SELECTION (weighted LSUR with slot bias) ----
        # Pick archetype with slot bias
        archetype_counts = history.field_counts("archetype") if history else {}
        slot = settings.slot
        archetype = select_with_slot_bias(
            ARCHETYPES,
            recent_keys=[r.get("archetype", "") for r in recent_entries],
            counts=archetype_counts,
            slot=slot,
            slot_bias=SLOT_ARCHETYPE_BIAS,
            min_spacing=2,
            recency_weight=2.0,
            coverage_weight=0.8,
            rng=self._rng,
        )

        # Pick primary theme (principle) within archetype with slot bias
        principles = ARCHETYPE_PRINCIPLES.get(archetype, PRINCIPLES)
        theme_counts = history.field_counts("primary_theme") if history else {}
        primary_theme = select_with_slot_bias(
            principles,
            recent_keys=recent_principles,
            counts=theme_counts,
            slot=slot,
            slot_bias=SLOT_PRINCIPLE_BIAS,
            min_spacing=3,
            recency_weight=1.5,
            coverage_weight=1.0,
            rng=self._rng,
        )

        # Pick structure patterns (rotation)
        opening_counts = history.field_counts("opening_pattern") if history else {}
        opening_pattern = select_opening_pattern(
            recent_openings, counts=opening_counts, rng=self._rng
        )
        conclusion_counts = history.field_counts("conclusion_pattern") if history else {}
        conclusion_pattern = select_conclusion_pattern(
            recent_conclusions, counts=conclusion_counts, rng=self._rng
        )
        caption_counts = history.field_counts("caption_style") if history else {}
        caption_style = select_caption_style(
            recent_caption_styles, counts=caption_counts, rng=self._rng
        )
        cta_counts = history.field_counts("cta_pattern") if history else {}
        cta_pattern = select_cta_pattern(
            recent_cta_patterns, counts=cta_counts, rng=self._rng
        )

        # Build user prompt with diversity directives
        user_prompt = GospelPrompts.gospel_prompt(
            language=language,
            target_duration=settings.target_duration_seconds,
            recent_entries=recent_entries or None,
            archetype=archetype,
            primary_theme=primary_theme,
            avoid_principles=recent_principles,
            avoid_verses=recent_verses,
            avoid_openings=recent_openings,
            opening_pattern=opening_pattern,
            conclusion_pattern=conclusion_pattern,
            caption_style=caption_style,
            cta_pattern=cta_pattern,
            blocked_scriptures=blocked_scriptures,
        )

        # Call API with archetype-specific system prompt
        system_instruction = GospelPrompts.ARCHETYPE_SYSTEMS[archetype]

        response_text = self._client.generate_json(
            model=self._model,
            contents=user_prompt,
            system_instruction=system_instruction,
            temperature=0.8,
            max_output_tokens=3000,
        )

        # Parse JSON response
        content_dict = self._parse_response(response_text)

        # Convert to GospelContent
        return self._dict_to_content(content_dict)

    def _parse_response(self, response_text: str) -> dict[str, Any]:
        """Parse JSON response from Gemini.

        Args:
            response_text: Raw response text

        Returns:
            Parsed dictionary

        Raises:
            ValueError: Invalid JSON
        """
        # Try to extract JSON from response (may have markdown code block)
        text = response_text.strip()

        # Remove markdown code block if present
        if text.startswith("```"):
            lines = text.split("\n")
            json_lines = []
            in_block = False
            for line in lines:
                if line.startswith("```") and not in_block:
                    in_block = True
                    continue
                elif line.startswith("```") and in_block:
                    break
                elif in_block:
                    json_lines.append(line)
            text = "\n".join(json_lines)

        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON response: {e}")
            logger.debug(f"Response text: {response_text[:500]}")
            raise ValueError(f"Invalid JSON response: {e}") from e

    def _dict_to_content(self, data: dict[str, Any]) -> GospelContent:
        """Convert dictionary to GospelContent.

        Args:
            data: Parsed response dictionary

        Returns:
            GospelContent instance

        Raises:
            ValueError: Invalid data structure
        """
        # Validate required fields
        required = [
            "situation_summary",
            "hook",
            "biblical_message",
            "scripture_reference",
            "scripture_text",
            "reflection",
            "closing_cta",
            "narration_script",
            "facebook_caption",
            "first_comment",
            "pinned_comment",
            "archetype",
            "primary_theme",
        ]
        for field in required:
            if field not in data or not data[field]:
                raise ValueError(f"Missing required field: {field}")

        # Ensure secondary_themes is a list
        secondary_themes = data.get("secondary_themes", [])
        if isinstance(secondary_themes, str):
            try:
                import json

                secondary_themes = json.loads(secondary_themes)
            except json.JSONDecodeError:
                secondary_themes = []

        # Ensure key_concepts is a list
        key_concepts = data.get("key_concepts", [])
        if isinstance(key_concepts, str):
            try:
                import json

                key_concepts = json.loads(key_concepts)
            except json.JSONDecodeError:
                key_concepts = []

        return GospelContent(
            situation_summary=data["situation_summary"],
            hook=data["hook"],
            biblical_message=data["biblical_message"],
            scripture_reference=data["scripture_reference"],
            scripture_text=data["scripture_text"],
            reflection=data["reflection"],
            closing_cta=data["closing_cta"],
            narration_script=data["narration_script"],
            facebook_caption=data["facebook_caption"],
            first_comment=data["first_comment"],
            pinned_comment=data["pinned_comment"],
            hashtags=data.get("hashtags", ["#DailyBread", "#Gospel", "#Faith", "#Encouragement", "#BibleVerse"]),
            archetype=data.get("archetype", ""),
            primary_theme=data.get("primary_theme", ""),
            secondary_themes=secondary_themes,
            tone=data.get("tone", ""),
            opening_pattern=data.get("opening_pattern", ""),
            conclusion_pattern=data.get("conclusion_pattern", ""),
            caption_style=data.get("caption_style", ""),
            cta_pattern=data.get("cta_pattern", ""),
            key_concepts=key_concepts,
        )

    def _compute_hash(self, content: GospelContent) -> str:
        """Compute SHA256 hash of content for duplicate detection.

        Hashes the core message fields to detect substantive duplicates.
        """
        # Use the narration script as the primary hash source
        # since it contains the complete message
        h = hashlib.sha256()
        h.update(content.narration_script.encode("utf-8"))
        h.update(content.scripture_reference.encode("utf-8"))
        h.update(content.situation_summary.encode("utf-8"))
        return h.hexdigest()[:16]

    def validate_content(self, content: GospelContent) -> ValidationResult:
        """Validate a content piece without generating.

        Args:
            content: Content to validate

        Returns:
            ValidationResult
        """
        return self._validator.validate(content)

    def check_safety(self, content: GospelContent) -> dict[str, Any]:
        """Run safety check on content.

        Args:
            content: Content to check

        Returns:
            Safety check result
        """
        prompt = GospelPrompts.safety_prompt(
            situation_summary=content.situation_summary,
            scripture_reference=content.scripture_reference,
            scripture_text=content.scripture_text,
            reflection=content.reflection,
            narration_script=content.narration_script,
        )

        try:
            response = self._client.generate_json(
                model=self._model,
                contents=prompt,
                system_instruction="You are a content safety reviewer for Christian content.",
                temperature=0.1,
            )
            return json.loads(response)
        except Exception as e:
            logger.error(f"Safety check failed: {e}")
            return {"safe": False, "issues": [str(e)], "severity": "unknown"}
"""Gospel content generator using Gemini AI.

This module generates original Daily Bread / Gospel encouragement content
using the Gemini API. It handles prompt construction, response parsing,
and validation.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import dataclass
from typing import Any

from src.ai.client import GeminiClient, GeminiClientError
from src.config import settings
from src.content.prompts import GospelPrompts
from src.content.schema import GospelContent
from src.content.validator import GospelValidator, ValidationResult

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
    1. Constructs appropriate prompts with anti-repetition context
    2. Calls Gemini API for content generation
    3. Parses and validates the response
    4. Computes content hash for duplicate detection
    5. Returns structured GospelContent
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

    def generate(
        self,
        language: str | None = None,
        max_attempts: int = 3,
    ) -> GenerationResult:
        """Generate a new Gospel content piece.

        Args:
            language: Content language (default: from settings)
            max_attempts: Maximum generation attempts

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
                content = self._call_gemini(language)

                # Compute content hash
                content.content_hash = self._compute_hash(content)

                # Validate
                validation = self._validator.validate(content)

                if validation.is_valid:
                    elapsed = int((time.time() - start_time) * 1000)
                    logger.info(
                        f"Gospel content generated successfully in {elapsed}ms: "
                        f"'{content.hook[:60]}...'"
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

    def _call_gemini(self, language: str) -> GospelContent:
        """Call Gemini API to generate Gospel content.

        Args:
            language: Content language

        Returns:
            Parsed GospelContent

        Raises:
            GeminiClientError: API call failed
        """
        # Load recent history for anti-repetition
        recent_entries: list[dict] = []
        try:
            from src.history.store import HistoryStore

            history = HistoryStore()
            for record in history.load_history():
                if record.situation_summary and record.scripture_reference:
                    recent_entries.append({
                        "situation_summary": record.situation_summary,
                        "scripture_reference": record.scripture_reference,
                    })
            # Keep last 20 to bound prompt size
            recent_entries = recent_entries[-20:]
        except Exception:
            logger.debug("Could not load history for anti-repetition; continuing without")

        # Build prompt
        user_prompt = GospelPrompts.gospel_prompt(
            language=language,
            target_duration=settings.target_duration_seconds,
            recent_entries=recent_entries or None,
        )

        # Call API
        response_text = self._client.generate_json(
            model=self._model,
            contents=user_prompt,
            system_instruction=GospelPrompts.GOSPEL_SYSTEM,
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
        ]
        for field in required:
            if field not in data or not data[field]:
                raise ValueError(f"Missing required field: {field}")

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
"""Story generator using Gemini AI.

This module generates original ASMR stories using the Gemini API.
It handles prompt construction, response parsing, and validation.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from typing import Any

from src.ai.client import GeminiClient, GeminiClientError
from src.config import settings
from src.content.prompts import StoryPrompts
from src.content.schema import Scene, StoryData
from src.content.validator import StoryValidator, ValidationResult

logger = logging.getLogger(__name__)


@dataclass
class GenerationResult:
    """Result of story generation."""
    
    success: bool
    story: StoryData | None = None
    validation: ValidationResult | None = None
    error: str | None = None
    attempts: int = 0
    generation_time_ms: int = 0


class StoryGenerator:
    """Generates ASMR stories using Gemini AI.
    
    This generator:
    1. Constructs appropriate prompts
    2. Calls Gemini API for story generation
    3. Parses and validates the response
    4. Returns structured StoryData
    """
    
    def __init__(
        self,
        client: GeminiClient | None = None,
        validator: StoryValidator | None = None,
    ) -> None:
        """Initialize the story generator.
        
        Args:
            client: Optional GeminiClient instance. Creates new if not provided.
            validator: Optional StoryValidator instance. Creates new if not provided.
        """
        self._client = client or GeminiClient()
        self._validator = validator or StoryValidator(
            min_duration=settings.min_duration_seconds,
            max_duration=settings.max_duration_seconds,
            target_duration=settings.target_duration_seconds,
        )
        self._model = settings.ai_model
    
    def generate(
        self,
        language: str | None = None,
        content_style: str | None = None,
        max_attempts: int = 3,
    ) -> GenerationResult:
        """Generate a new story.
        
        Args:
            language: Story language (default: from settings)
            content_style: Content style (default: from settings)
            max_attempts: Maximum generation attempts
            
        Returns:
            GenerationResult with story or error
        """
        language = language or settings.story_language
        content_style = content_style or settings.content_style
        
        start_time = time.time()
        last_error: str | None = None
        
        for attempt in range(1, max_attempts + 1):
            logger.info(f"Generating story (attempt {attempt}/{max_attempts})")
            
            try:
                # Generate story
                story = self._call_gemini(language, content_style)
                
                # Validate
                validation = self._validator.validate(story)
                
                if validation.is_valid:
                    elapsed = int((time.time() - start_time) * 1000)
                    logger.info(
                        f"Story generated successfully in {elapsed}ms: '{story.title}'"
                    )
                    return GenerationResult(
                        success=True,
                        story=story,
                        validation=validation,
                        attempts=attempt,
                        generation_time_ms=elapsed,
                    )
                else:
                    logger.warning(
                        f"Story validation failed (attempt {attempt}): "
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
    
    def _call_gemini(self, language: str, content_style: str) -> StoryData:
        """Call Gemini API to generate a story.

        Args:
            language: Story language
            content_style: Content style

        Returns:
            Parsed StoryData

        Raises:
            GeminiClientError: API call failed
        """
        # Load recent published titles to avoid duplicates
        recent_titles: list[str] = []
        try:
            from src.history.store import HistoryStore

            history = HistoryStore()
            for record in history.load_history():
                if record.story_title:
                    recent_titles.append(record.story_title)
            # Keep last 20 to bound prompt size
            recent_titles = recent_titles[-20:]
        except Exception:
            logger.debug("Could not load history for title dedup; continuing without")

        # Build prompt
        user_prompt = StoryPrompts.story_prompt(
            language=language,
            content_style=content_style,
            target_duration=settings.target_duration_seconds,
            recent_titles=recent_titles or None,
        )
        
        # Call API
        response_text = self._client.generate_json(
            model=self._model,
            contents=user_prompt,
            system_instruction=StoryPrompts.STORY_SYSTEM,
            temperature=0.8,
            max_output_tokens=2000,
        )
        
        # Parse JSON response
        story_dict = self._parse_response(response_text)
        
        # Convert to StoryData
        return self._dict_to_story(story_dict)
    
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
            # Find the JSON content between code blocks
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
    
    def _dict_to_story(self, data: dict[str, Any]) -> StoryData:
        """Convert dictionary to StoryData.
        
        Args:
            data: Parsed response dictionary
            
        Returns:
            StoryData instance
            
        Raises:
            ValueError: Invalid data structure
        """
        # Extract scenes
        scenes_data = data.get("scenes", [])
        scenes = []
        for scene_dict in scenes_data:
            scenes.append(Scene(
                description=scene_dict.get("description", ""),
                duration_seconds=float(scene_dict.get("duration_seconds", 5)),
                category=scene_dict.get("category", ""),
            ))
        
        # Build StoryData
        return StoryData(
            title=data.get("title", "Untitled"),
            hook=data.get("hook", ""),
            narration=data.get("narration", ""),
            scenes=scenes,
            hashtags=data.get("hashtags", ["#ASMR", "#ShortStory"]),
            caption=data.get("caption", ""),
        )
    
    def validate_story(self, story: StoryData) -> ValidationResult:
        """Validate a story without generating.
        
        Args:
            story: Story to validate
            
        Returns:
            ValidationResult
        """
        return self._validator.validate(story)
    
    def check_safety(self, story: StoryData) -> dict[str, Any]:
        """Run safety check on story content.
        
        Args:
            story: Story to check
            
        Returns:
            Safety check result
        """
        prompt = StoryPrompts.safety_prompt(story.title, story.narration)
        
        try:
            response = self._client.generate_json(
                model=self._model,
                contents=prompt,
                system_instruction="You are a content safety reviewer.",
                temperature=0.1,
            )
            return json.loads(response)
        except Exception as e:
            logger.error(f"Safety check failed: {e}")
            return {"safe": False, "issues": [str(e)], "severity": "unknown"}

"""Gemini API client wrapper.

This module provides a thin wrapper around the google-genai SDK.
The client is initialized with an API key from environment variables.
"""

from __future__ import annotations

import logging
from typing import Any

from google import genai
from google.genai import types

from src.config import settings

logger = logging.getLogger(__name__)


class GeminiClientError(Exception):
    """Base exception for Gemini client errors."""


class GeminiAuthError(GeminiClientError):
    """Authentication error - invalid API key."""


class GeminiRateLimitError(GeminiClientError):
    """Rate limit exceeded."""


class GeminiClient:
    """Wrapper around the Google GenAI client.
    
    This client handles:
    - API key management (from environment)
    - Request/response handling
    - Error classification
    - Logging (without exposing credentials)
    """
    
    def __init__(self, api_key: str | None = None) -> None:
        """Initialize the Gemini client.
        
        Args:
            api_key: Optional API key override. If not provided,
                    uses GEMINI_API_KEY from environment.
        """
        key = api_key or settings.gemini_api_key
        if not key:
            raise GeminiAuthError("GEMINI_API_KEY not configured")
        
        try:
            self._client = genai.Client(api_key=key)
            logger.info("Gemini client initialized")
        except Exception as e:
            logger.error(f"Failed to initialize Gemini client: {type(e).__name__}")
            raise GeminiAuthError(f"Failed to initialize client: {type(e).__name__}") from e
    
    def generate_content(
        self,
        model: str,
        contents: str,
        system_instruction: str | None = None,
        response_mime_type: str | None = None,
        temperature: float | None = None,
        max_output_tokens: int | None = None,
    ) -> str:
        """Generate content using the specified model.
        
        Args:
            model: Model name (e.g., "gemini-3.5-flash-lite")
            contents: User prompt text
            system_instruction: Optional system prompt
            response_mime_type: Optional MIME type (e.g., "application/json")
            temperature: Optional temperature (0.0-2.0)
            max_output_tokens: Optional max output tokens
            
        Returns:
            Generated text response
            
        Raises:
            GeminiAuthError: Invalid API key
            GeminiRateLimitError: Rate limit exceeded
            GeminiClientError: Other API errors
        """
        # Build config
        config_kwargs: dict[str, Any] = {}
        if system_instruction:
            config_kwargs["system_instruction"] = system_instruction
        if response_mime_type:
            config_kwargs["response_mime_type"] = response_mime_type
        if temperature is not None:
            config_kwargs["temperature"] = temperature
        if max_output_tokens is not None:
            config_kwargs["max_output_tokens"] = max_output_tokens
        
        config = types.GenerateContentConfig(**config_kwargs) if config_kwargs else None
        
        try:
            response = self._client.models.generate_content(
                model=model,
                contents=contents,
                config=config,
            )
            
            if response.text is None:
                raise GeminiClientError("Empty response from Gemini API")
            
            return response.text
            
        except Exception as e:
            error_msg = str(e).lower()
            
            # Classify errors
            if "api key" in error_msg or "invalid" in error_msg or "401" in error_msg:
                raise GeminiAuthError("Invalid API key") from e
            elif "rate" in error_msg or "429" in error_msg:
                raise GeminiRateLimitError("Rate limit exceeded") from e
            elif "quota" in error_msg:
                raise GeminiRateLimitError("Quota exceeded") from e
            else:
                raise GeminiClientError(f"Gemini API error: {type(e).__name__}") from e
    
    def generate_json(
        self,
        model: str,
        contents: str,
        system_instruction: str | None = None,
        temperature: float | None = None,
        max_output_tokens: int | None = None,
    ) -> str:
        """Generate JSON content using the specified model.
        
        Convenience method that sets response_mime_type to application/json.
        
        Args:
            model: Model name
            contents: User prompt text
            system_instruction: Optional system prompt
            temperature: Optional temperature
            max_output_tokens: Optional max output tokens
            
        Returns:
            JSON string response
        """
        return self.generate_content(
            model=model,
            contents=contents,
            system_instruction=system_instruction,
            response_mime_type="application/json",
            temperature=temperature,
            max_output_tokens=max_output_tokens,
        )

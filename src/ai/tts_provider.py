"""TTS provider using Gemini AI.

This module provides text-to-speech generation using Gemini's TTS models.
It implements a Protocol-based interface for future replaceability.
"""

from __future__ import annotations

import base64
import logging
import wave
from pathlib import Path
from typing import Protocol, runtime_checkable

from google.genai import types

from src.ai.client import (
    GeminiAuthError,
    GeminiClient,
    GeminiClientError,
)
from src.config import settings

logger = logging.getLogger(__name__)


# Audio output settings
AUDIO_SAMPLE_RATE = 24000
AUDIO_CHANNELS = 1
AUDIO_SAMPLE_WIDTH = 2  # 16-bit = 2 bytes


@runtime_checkable
class TTSProvider(Protocol):
    """Protocol for TTS providers.
    
    Any TTS provider must implement this interface.
    This allows swapping providers without changing the pipeline.
    """
    
    def synthesize(
        self,
        text: str,
        voice_instruction: str = "",
    ) -> bytes:
        """Convert text to speech audio.
        
        Args:
            text: Text to convert to speech
            voice_instruction: Optional voice style instruction
            
        Returns:
            Audio data as bytes (WAV format)
            
        Raises:
            TTSProviderError: If synthesis fails
        """
        ...
    
    def synthesize_to_file(
        self,
        text: str,
        output_path: Path | str,
        voice_instruction: str = "",
    ) -> Path:
        """Convert text to speech and save to file.
        
        Args:
            text: Text to convert to speech
            output_path: Path to save audio file
            voice_instruction: Optional voice style instruction
            
        Returns:
            Path to saved audio file
            
        Raises:
            TTSProviderError: If synthesis fails
        """
        ...


class TTSProviderError(Exception):
    """Base exception for TTS provider errors."""


class TTSAuthError(TTSProviderError):
    """TTS authentication/configuration failure (bad or missing API key)."""


class GeminiTTSError(TTSProviderError):
    """Gemini-specific TTS error."""


def _is_transient_tts_error(e: Exception) -> bool:
    """Return True if a TTS exception is worth retrying.

    Auth errors (bad/expired key) must never be retried — retrying burns
    quota and only delays the inevitable. Rate limits and generic API
    errors (5xx, network) are transient.
    """
    from src.ai.client import GeminiAuthError, GeminiRateLimitError

    if isinstance(e, GeminiAuthError):
        return False
    if isinstance(e, GeminiRateLimitError):
        return True
    # Generic client errors (network / 5xx) are potentially transient.
    return isinstance(e, GeminiClientError)


def _get_tts_provider_name() -> str:
    """Return the configured TTS provider name, defaulting to 'kokoro'.

    Reads ``TTS_PROVIDER`` from the environment (via settings when available).
    """
    try:
        from src.config import settings
        name = str(settings.tts_provider).lower().strip()
    except Exception:
        import os
        name = os.getenv("TTS_PROVIDER", "kokoro").lower().strip()
    return name or "kokoro"


class GeminiTTSProvider:
    """TTS provider using Gemini AI.
    
    This provider uses Gemini's TTS model to generate speech.
    It supports:
    - Expressive audio tags for narration control
    - Multiple voice options
    - Calm, intimate ASMR-style delivery
    """
    
    # Default voice for ASMR narration
    DEFAULT_VOICE = "Kore"
    
    # ASMR voice instruction template
    ASMR_VOICE_INSTRUCTION = """Read the narration as a calm, intimate ASMR-style storyteller.
Use a soft, slow pace with natural pauses.
Keep the delivery soothing and slightly mysterious.
Do not sound theatrical or exaggerated.
Prioritize clear pronunciation and a relaxing cadence."""
    
    def __init__(
        self,
        client: GeminiClient | None = None,
        model: str | None = None,
        voice: str | None = None,
    ) -> None:
        """Initialize the TTS provider.
        
        Args:
            client: Optional GeminiClient instance
            model: TTS model name (default: from settings)
            voice: Voice name (default: Kore)
        """
        self._client = client or GeminiClient()
        self._model = model or settings.tts_model
        self._voice = voice or self.DEFAULT_VOICE
        
        logger.info(f"Gemini TTS initialized with voice: {self._voice}")
    
    def synthesize(
        self,
        text: str,
        voice_instruction: str = "",
    ) -> bytes:
        """Convert text to speech audio.

        Args:
            text: Text to convert to speech
            voice_instruction: Optional voice style instruction.
                             If empty, uses default ASMR instruction.
                             NOTE: This is prepended to the text content.

        Returns:
            Audio data as WAV bytes

        Raises:
            GeminiTTSError: If synthesis fails
        """
        if not text or not text.strip():
            raise GeminiTTSError("Text cannot be empty")

        # Use ASMR instruction if none provided
        instruction = voice_instruction or self.ASMR_VOICE_INSTRUCTION

        try:
            logger.info(f"Generating TTS for {len(text)} characters")

            from src.config import settings
            from src.utils.retry import retry_transient

            # Prepend instruction to guide the voice style
            full_text = f"{instruction}\n\n{text}"

            def _call() -> bytes:
                response = self._client._client.models.generate_content(
                    model=self._model,
                    contents=full_text,
                    config=types.GenerateContentConfig(
                        response_modalities=["AUDIO"],
                        speech_config=types.SpeechConfig(
                            voice_config=types.VoiceConfig(
                                prebuilt_voice_config=types.PrebuiltVoiceConfig(
                                    voice_name=self._voice,
                                )
                            )
                        ),
                    ),
                )
                # Extract audio data from response
                audio_bytes = self._extract_audio(response)
                return audio_bytes

            audio_bytes = retry_transient(
                _call,
                attempts=settings.tts_retry_count + 1,
                base_delay=2.0,
                backoff=2.0,
                recoverable=_is_transient_tts_error,
                context="Gemini TTS synthesis",
            )

            # Convert raw PCM to WAV
            wav_bytes = self._pcm_to_wav(audio_bytes)

            logger.info(f"TTS generated successfully: {len(wav_bytes)} bytes")
            return wav_bytes

        except GeminiAuthError as e:
            logger.error(f"Gemini TTS auth error: {e}")
            raise TTSAuthError("Gemini TTS authentication failed") from e
        except GeminiClientError as e:
            logger.error(f"Gemini TTS error: {e}")
            raise GeminiTTSError(f"TTS generation failed: {e}") from e
        except TTSAuthError:
            raise
        except Exception as e:
            logger.error(f"Unexpected TTS error: {type(e).__name__}: {e}")
            raise GeminiTTSError(f"TTS generation failed: {type(e).__name__}") from e
    
    def synthesize_to_file(
        self,
        text: str,
        output_path: Path | str,
        voice_instruction: str = "",
    ) -> Path:
        """Convert text to speech and save to file.
        
        Args:
            text: Text to convert to speech
            output_path: Path to save audio file
            voice_instruction: Optional voice style instruction
            
        Returns:
            Path to saved audio file
        """
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        
        wav_bytes = self.synthesize(text, voice_instruction)
        output.write_bytes(wav_bytes)
        
        logger.info(f"TTS saved to: {output}")
        return output
    
    def _extract_audio(self, response) -> bytes:
        """Extract audio data from Gemini response.
        
        Args:
            response: Gemini API response
            
        Returns:
            Raw PCM audio bytes
            
        Raises:
            GeminiTTSError: If no audio in response
        """
        try:
            # Navigate response structure
            candidates = response.candidates
            if not candidates:
                raise GeminiTTSError("No candidates in response")
            
            candidate = candidates[0]
            content = candidate.content
            
            if not content or not content.parts:
                raise GeminiTTSError("No content parts in response")
            
            # Find audio part
            for part in content.parts:
                if hasattr(part, "inline_data") and part.inline_data:
                    audio_data = part.inline_data
                    if hasattr(audio_data, "data") and audio_data.data:
                        # Decode base64 audio data
                        return base64.b64decode(audio_data.data)
            
            raise GeminiTTSError("No audio data found in response")
            
        except GeminiTTSError:
            raise
        except Exception as e:
            raise GeminiTTSError(f"Failed to extract audio: {e}") from e
    
    def _pcm_to_wav(self, pcm_data: bytes) -> bytes:
        """Convert raw PCM audio to WAV format.
        
        Args:
            pcm_data: Raw PCM audio data
            
        Returns:
            WAV format audio bytes
        """
        import io
        
        buffer = io.BytesIO()
        
        with wave.open(buffer, "wb") as wav_file:
            wav_file.setnchannels(AUDIO_CHANNELS)
            wav_file.setsampwidth(AUDIO_SAMPLE_WIDTH)
            wav_file.setframerate(AUDIO_SAMPLE_RATE)
            wav_file.writeframes(pcm_data)
        
        return buffer.getvalue()
    
    def get_available_voices(self) -> list[str]:
        """Get list of available Gemini TTS voices.
        
        Returns:
            List of voice names
        """
        # Known Gemini TTS voices
        return [
            "Kore",      # Female, warm
            "Fenrir",    # Male, deep
            "Puck",      # Male, friendly
            "Charon",    # Male, professional
            "Leda",      # Female, soft
            "Orus",      # Male, calm
            "Zephyr",    # Female, clear
            "Aoede",     # Female, expressive
        ]


def create_tts_provider(
    client: GeminiClient | None = None,
    model: str | None = None,
    voice: str | None = None,
    provider: str | None = None,
) -> TTSProvider:
    """Factory to create a TTS provider based on configuration.

    Selects the provider from ``TTS_PROVIDER`` config:
        - "kokoro" (default) -> :class:`KokoroTTSProvider` (local, no API key)
        - "gemini"          -> :class:`GeminiTTSProvider` (optional, API key)

    Args:
        client: Optional GeminiClient (gemini provider only)
        model: Optional model name (gemini provider only)
        voice: Optional voice name
        provider: Optional explicit override; defaults to TTS_PROVIDER config

    Returns:
        An initialized TTS provider implementing the TTSProvider Protocol.

    Raises:
        TTSProviderError: If the provider name is unknown
    """
    name = (provider or _get_tts_provider_name()).lower().strip()

    if name == "gemini" or name == "google" or name == "gemini_tts":
        return GeminiTTSProvider(client=client, model=model, voice=voice)
    elif name == "kokoro" or name == "k":
        from src.ai.kokoro_provider import KokoroTTSProvider
        kwargs: dict = {}
        if voice:
            kwargs["voice"] = voice
        try:
            from src.config import settings
            if settings.kokoro_voice:
                kwargs.setdefault("voice", settings.kokoro_voice)
            if settings.kokoro_speed:
                kwargs["speed"] = settings.kokoro_speed
        except Exception:
            pass
        return KokoroTTSProvider(**kwargs)
    else:
        raise TTSProviderError(f"Unknown TTS provider: {name}")

"""Kokoro TTS provider.

Kokoro is a lightweight (82M parameter), open-weight text-to-speech model that
runs locally on CPU. It is the PRIMARY production TTS provider because it:

- Requires no paid API key
- Runs fully offline on a CPU (GitHub Actions runners included)
- Produces natural, calm voices suitable for ASMR narration
- Weights are downloaded from HuggingFace (hexgrad/Kokoro-82M) and reused

The provider is fitted behind the same ``TTSProvider`` Protocol as Gemini, so
switching TTS providers is a configuration change, not a code change.

Voice naming (Kokoro):
    af_<name> = American English, female
    am_<name> = American English, male
    bf_<name> = British English, female
    bm_<name> = British English, male

Output: 24 kHz mono WAV (Kokoro native sample rate). This is a hard-coded
property of the model and matches the renderer's expectations.
"""
from __future__ import annotations

import io
import logging
from pathlib import Path

# Optional imports - Kokoro is only required when this provider is selected.
try:
    import numpy as np
    import soundfile as sf
    _SFDEP = True
except ImportError:  # pragma: no cover
    np = None
    sf = None
    _SFDEP = False

from src.ai.tts_provider import TTSProviderError

logger = logging.getLogger(__name__)

# Kokoro native output sample rate
KOKORO_SAMPLE_RATE = 24000


class KokoroTTSUnavailableError(TTSProviderError):
    """Kokoro package or system dependency (espeak-ng) is not installed."""


class KokoroTTSProvider:
    """Text-to-speech provider using the local Kokoro model.

    This provider uses the ``kokoro`` Python package (KPipeline) to generate
    speech entirely on-device. It does not call any external API and requires
    no TTS credential.
    """

    # Default calm, warm female American voice suited to ASMR narration.
    DEFAULT_VOICE = "af_heart"
    # Alternative voices (documented for easy configuration):
    #   af_bella  - female, soft
    #   af_nicole - female, calming
    #   am_michael - male, calm
    DEFAULT_LANG_CODE = "a"  # American English

    # The ASMR narration isn't steered by natural language at runtime (Kokoro
    # picks a fixed voice); this constant documents the target style that the
    # DEFAULT_VOICE was chosen for.
    ASMR_VOICE_INSTRUCTION = (
        "Calm, intimate, soft nighttime storytelling. Slow, gentle pacing. "
        "Warm and slightly mysterious. Whispers-style narration for ASMR."
    )

    def __init__(
        self,
        voice: str | None = None,
        lang_code: str | None = None,
        speed: float = 1.0,
        device: str | None = None,
        pipeline=None,
        repo_id: str | None = None,
    ) -> None:
        """Initialize the Kokoro provider.

        Args:
            voice: Kokoro voice name (default: af_heart)
            lang_code: Kokoro language code (default: 'a' = American English)
            speed: Speech speed multiplier (default 1.0; slower for ASMR)
            device: Device override ('cpu' or 'cuda'); default None (auto CPU)
            pipeline: Optional pre-built KPipeline (for tests/dependency injection)
            repo_id: Optional HuggingFace repo id for weights

        Raises:
            KokoroTTSUnavailableError: If kokoro/soundfile/numpy are missing
        """
        self._voice = voice or self.DEFAULT_VOICE
        self._lang_code = lang_code or self.DEFAULT_LANG_CODE
        self._speed = speed
        self._device = device or "cpu"
        self._repo_id = repo_id
        self._pipeline = pipeline
        self._owns_pipeline = pipeline is None

        if not _SFDEP:
            raise KokoroTTSUnavailableError(
                "soundfile/numpy not installed. Install with: "
                "pip install kokoro soundfile numpy"
            )

        logger.info(
            f"Kokoro TTS provider initialized: voice={self._voice}, "
            f"lang={self._lang_code}, speed={self._speed}, device={self._device}"
        )

    def _get_pipeline(self):
        """Lazily build the Kokoro pipeline (loads model weights on first use).

        Returns:
            A kokoro.KPipeline instance configured for CPU inference.
        """
        if self._pipeline is not None:
            return self._pipeline

        try:
            from kokoro import KPipeline
        except ImportError as e:
            raise KokoroTTSUnavailableError(
                "kokoro package not installed. Install with: pip install kokoro"
            ) from e

        logger.info("Loading Kokoro model weights (first run downloads from HuggingFace)...")
        kwargs: dict = {"lang_code": self._lang_code, "device": self._device}
        if self._repo_id:
            kwargs["repo_id"] = self._repo_id
        self._pipeline = KPipeline(**kwargs)
        logger.info("Kokoro KPipeline ready")
        return self._pipeline

    def synthesize(self, text: str, voice_instruction: str = "") -> bytes:
        """Convert text to speech audio (WAV bytes).

        Args:
            text: Text to speak
            voice_instruction: Ignored for Kokoro (voice is fixed via config).
                             Accepted for protocol compatibility.

        Returns:
            24 kHz mono WAV bytes

        Raises:
            KokoroTTSUnavailableError: If kokoro or its system deps are missing
            TTSProviderError: If synthesis fails or produces no audio
        """
        if not text or not text.strip():
            raise TTSProviderError("Text cannot be empty")

        # Kokoro drives pacing via fixed voice + speed, not natural language.
        # A slower speed suits the calm ASMR delivery.
        speed = self._speed

        try:
            pipeline = self._get_pipeline()
            logger.info(
                f"Kokoro TTS: {len(text)} chars, voice={self._voice}, speed={speed}"
            )
            samples = []
            for result in pipeline(
                text, voice=self._voice, speed=speed, split_pattern=r"[\n.]+"
            ):
                audio = result.audio
                if audio is None:
                    continue
                samples.append(audio.detach().cpu().float().numpy())

            if not samples:
                raise TTSProviderError("Kokoro produced no audio samples")

            audio_np = np.concatenate(samples)
            logger.info(
                f"Kokoro TTS success: {len(audio_np)} samples "
                f"(~{len(audio_np) / KOKORO_SAMPLE_RATE:.1f}s)"
            )

            buf = io.BytesIO()
            sf.write(buf, audio_np, KOKORO_SAMPLE_RATE, format="WAV", subtype="PCM_16")
            return buf.getvalue()

        except KokoroTTSUnavailableError:
            raise
        except TTSProviderError:
            raise
        except Exception as e:
            logger.error(f"Kokoro TTS error: {type(e).__name__}: {e}")
            raise TTSProviderError(
                f"Kokoro TTS generation failed: {type(e).__name__}"
            ) from e

    def synthesize_to_file(
        self,
        text: str,
        output_path: Path | str,
        voice_instruction: str = "",
    ) -> Path:
        """Convert text to speech and save to a WAV file.

        Args:
            text: Text to speak
            output_path: Path to save the WAV file
            voice_instruction: Ignored for Kokoro.

        Returns:
            Path to the saved WAV file
        """
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)

        wav_bytes = self.synthesize(text, voice_instruction)
        output.write_bytes(wav_bytes)

        logger.info(f"Kokoro TTS saved to: {output} ({len(wav_bytes)} bytes)")
        return output

    def get_available_voices(self) -> list[str]:
        """Return documented calm American English voices for this provider."""
        return [
            "af_heart",    # female, warm (default)
            "af_bella",    # female, soft
            "af_nicole",   # female, gentle
            "af_sarah",    # female, clear
            "am_michael",  # male, calm
            "am_adam",     # male, soft
            "bf_emma",     # British female, calm
            "bm_george",   # British male, calm
        ]

    def voice_label(self) -> str:
        """Human-readable label for the configured voice."""
        return f"Kokoro-82M voice '{self._voice}' at {self._speed}x speed"


def create_kokoro_provider(
    voice: str | None = None,
    lang_code: str | None = None,
    speed: float = 1.0,
    device: str | None = None,
    pipeline=None,
    repo_id: str | None = None,
) -> KokoroTTSProvider:
    """Create a Kokoro TTS provider (factory convenience)."""
    return KokoroTTSProvider(
        voice=voice,
        lang_code=lang_code,
        speed=speed,
        device=device,
        pipeline=pipeline,
        repo_id=repo_id,
    )
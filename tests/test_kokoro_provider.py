"""Tests for Kokoro TTS provider."""

from unittest.mock import MagicMock

import pytest

from src.ai.kokoro_provider import (
    KOKORO_SAMPLE_RATE,
    KokoroTTSProvider,
    KokoroTTSUnavailableError,
    create_kokoro_provider,
)
from src.ai.tts_provider import TTSProviderError


def make_fake_audio(seconds: float, sample_rate: int = KOKORO_SAMPLE_RATE) -> "object":
    """Create a fake torch tensor-like audio object."""
    import numpy as np

    # Mock torch tensor: must support .detach().cpu().float().numpy()
    class FakeAudio:
        def __init__(self, samples: int):
            self._arr = np.zeros(samples, dtype=np.float32)

        def detach(self):
            return self

        def cpu(self):
            return self

        def float(self):
            return self

        def numpy(self):
            return self._arr

    return FakeAudio(int(seconds * sample_rate))


def fake_pipeline(*args, **kwargs):
    """Return a generator of fake results with `.audio` attributes."""
    del kwargs  # voice isn't threaded into duration
    # Approximate 1 second of audio per ~12 chars, min 0.5s
    duration = max(0.5, len(str(args[0])) / 10.0)
    results = []
    for i in range(3):
        r = MagicMock()
        r.audio = make_fake_audio(duration / 3.0)
        results.append(r)
    return iter(results)


class TestKokoroCreation:
    """Test KokoroTTSProvider class creation."""

    def test_default_voice_is_am_fenrir(self):
        """Default voice should be am_fenrir (deep male Gospel)."""
        assert KokoroTTSProvider.DEFAULT_VOICE == "am_fenrir"

    def test_asmr_instruction_defined(self):
        """Voice instruction should document the reverent Gospel style."""
        assert "calm" in KokoroTTSProvider.ASMR_VOICE_INSTRUCTION.lower()

    def test_implements_protocol(self):
        """KokoroTTSProvider should implement TTSProvider protocol."""
        assert hasattr(KokoroTTSProvider, "synthesize")
        assert hasattr(KokoroTTSProvider, "synthesize_to_file")

    def test_speed_default(self):
        """Default speed should be 1.0."""
        provider = KokoroTTSProvider()
        assert provider._speed == 1.0

    def test_documented_voices(self):
        """Provider should document calm ASMR voices."""
        provider = KokoroTTSProvider.__new__(KokoroTTSProvider)
        voices = provider.get_available_voices()
        assert "af_heart" in voices
        assert len(voices) >= 5


class TestKokoroSynthesize:
    """Test KokoroTTSProvider.synthesize with injected fake pipeline."""

    def test_synthesize_returns_valid_wav(self):
        """Synthesize should return valid WAV bytes."""
        provider = KokoroTTSProvider(pipeline=object())  # non-None to skip loading
        provider._pipeline = MagicMock(side_effect=fake_pipeline)
        provider._speed = 1.0

        wav = provider.synthesize("Hello, this is a test narration.")
        assert wav.startswith(b"RIFF")
        assert len(wav) > 1000

    def test_synthesize_empty_text_raises(self):
        """Empty text should raise TTSProviderError."""
        provider = KokoroTTSProvider(pipeline=MagicMock())
        with pytest.raises(TTSProviderError, match="empty"):
            provider.synthesize("")

    def test_synthesize_no_samples_raises(self):
        """If pipeline returns no audio, raise TTSProviderError."""
        provider = KokoroTTSProvider(pipeline=object())
        provider._pipeline = MagicMock(return_value=iter([]))
        with pytest.raises(TTSProviderError, match="no audio"):
            provider.synthesize("some text here")

    def test_synthesize_error_raises(self):
        """Pipeline errors should be wrapped in TTSProviderError."""
        provider = KokoroTTSProvider(pipeline=object())

        def boom(*args, **kwargs):
            raise RuntimeError("model failure")

        provider._pipeline = boom
        with pytest.raises(TTSProviderError, match="generation failed"):
            provider.synthesize("some text")

    def test_voice_instruction_ignored(self):
        """voice_instruction is ignored (Kokoro voice is config-driven)."""
        provider = KokoroTTSProvider(pipeline=MagicMock(side_effect=fake_pipeline))
        wav1 = provider.synthesize("A calm sentence.")
        wav2 = provider.synthesize("A calm sentence.", voice_instruction="whatever")
        assert wav1[:4] == b"RIFF"
        assert wav2[:4] == b"RIFF"


class TestKokoroSynthesizeToFile:
    """Test KokoroTTSProvider.synthesize_to_file."""

    def test_saves_wav_file(self, tmp_path):
        """Should save valid WAV at the given path."""
        provider = KokoroTTSProvider(pipeline=object())
        provider._pipeline = MagicMock(side_effect=fake_pipeline)
        provider._speed = 1.0

        out = tmp_path / "narration.wav"
        result = provider.synthesize_to_file("Some narration text.", out)
        assert result == out
        assert out.exists()
        assert out.read_bytes().startswith(b"RIFF")

    def test_creates_parent_dirs(self, tmp_path):
        """Should create parent directories automatically."""
        provider = KokoroTTSProvider(pipeline=object())
        provider._pipeline = MagicMock(side_effect=fake_pipeline)
        provider._speed = 1.0

        nested = tmp_path / "a" / "b" / "c" / "n.wav"
        provider.synthesize_to_file("Text", nested)
        assert nested.exists()


class TestKokoroUnavailable:
    """Test behavior when Kokoro dependencies are missing."""

    def test_raises_if_soundfile_missing(self):
        """If soundfile/numpy missing, raise KokoroTTSUnavailableError."""
        import src.ai.kokoro_provider as kp

        # Simulate missing soundfile dependency
        original = kp._SFDEP
        kp._SFDEP = False
        try:
            with pytest.raises(KokoroTTSUnavailableError):
                KokoroTTSProvider()
        finally:
            kp._SFDEP = original


class TestCreateKokoroProvider:
    """Test create_kokoro_provider factory."""

    def test_factory_returns_provider(self):
        """Factory should return a KokoroTTSProvider."""
        p = create_kokoro_provider()
        assert isinstance(p, KokoroTTSProvider)

    def test_factory_passes_voice(self):
        """Factory should pass voice override."""
        p = create_kokoro_provider(voice="af_nicole")
        assert p._voice == "af_nicole"
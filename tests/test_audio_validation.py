"""Tests for the audio validation gate."""

import struct
import wave
from pathlib import Path
from unittest.mock import patch

import pytest

from src.audio.validator import (
    TTS_DECODE_FAILED,
    TTS_DURATION_INVALID,
    TTS_EMPTY_AUDIO,
    TTS_INVALID_AUDIO,
    TTS_NEAR_SILENT,
    AudioValidationResult,
    AudioValidator,
    validate_audio,
)


def write_wav(
    path: Path,
    seconds: float,
    sample_rate: int = 24000,
    channels: int = 1,
    sample_width: int = 2,
    amplitude: int = 8000,  # audible tone amplitude
):
    """Write a synthetic WAV file."""
    n_frames = int(seconds * sample_rate)
    data = b"".join(
        struct.pack("<h", int(amplitude * 0.5)) for _ in range(n_frames)
    )
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(sample_width)
        wf.setframerate(sample_rate)
        wf.writeframes(data)
    return path


def write_silent_wav(path: Path, seconds: float, sample_rate: int = 24000):
    """Write a WAV containing pure silence (RMS ~0)."""
    n_frames = int(seconds * sample_rate)
    data = b"\x00\x00" * n_frames
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(data)
    return path


class TestFileExistsCheck:
    """Test audio file existence."""

    @patch("src.audio.validator.AudioValidator._ffmpeg_can_decode", return_value=True)
    def test_missing_file_rejected(self, mock_decode):
        """Non-existent file should be rejected with TTS_EMPTY_AUDIO."""
        v = AudioValidator()
        result = v.validate(Path("/nonexistent/audio.wav"))
        assert not result.is_valid
        assert TTS_EMPTY_AUDIO in result.error_codes

    @patch("src.audio.validator.AudioValidator._ffmpeg_can_decode", return_value=True)
    def test_tiny_file_rejected(self, mock_decode, tmp_path):
        """Suspiciously tiny file should be rejected."""
        tiny = tmp_path / "tiny.wav"
        tiny.write_bytes(b"RIFF\x00\x00")  # not even a real WAV
        v = AudioValidator()
        result = v.validate(tiny)
        assert not result.is_valid
        assert TTS_EMPTY_AUDIO in result.error_codes or TTS_INVALID_AUDIO in result.error_codes


class TestInvalidContainer:
    """Test invalid WAV container rejection."""

    @patch("src.audio.validator.AudioValidator._ffmpeg_can_decode", return_value=True)
    def test_non_wav_rejected(self, mock_decode, tmp_path):
        """A non-WAV file with enough bytes should be rejected as invalid."""
        fake = tmp_path / "fake.wav"
        fake.write_bytes(b"NOT A WAV FILE AT ALL " * 2000)  # ~42,000 bytes
        v = AudioValidator()
        result = v.validate(fake)
        assert not result.is_valid
        assert TTS_INVALID_AUDIO in result.error_codes


class TestDurationCheck:
    """Test duration bounds."""

    @patch("src.audio.validator.AudioValidator._ffmpeg_can_decode", return_value=True)
    def test_too_short_rejected(self, mock_decode, tmp_path):
        """Audio shorter than min_duration should be rejected."""
        wav = write_wav(tmp_path / "short.wav", seconds=1.0)
        v = AudioValidator(min_duration=20.0, max_duration=75.0)
        result = v.validate(wav)
        assert not result.is_valid
        assert TTS_DURATION_INVALID in result.error_codes

    @patch("src.audio.validator.AudioValidator._ffmpeg_can_decode", return_value=True)
    def test_too_long_rejected(self, mock_decode, tmp_path):
        """Audio longer than max_duration should be rejected."""
        wav = write_wav(tmp_path / "long.wav", seconds=90.0)
        v = AudioValidator(min_duration=20.0, max_duration=75.0)
        result = v.validate(wav)
        assert not result.is_valid
        assert TTS_DURATION_INVALID in result.error_codes


class TestSilenceCheck:
    """Test near-silent rejection."""

    @patch("src.audio.validator.AudioValidator._ffmpeg_can_decode", return_value=True)
    def test_silent_audio_rejected(self, mock_decode, tmp_path):
        """Pure-silence WAV should be rejected as near-silent."""
        wav = write_silent_wav(tmp_path / "silent.wav", seconds=30.0)
        v = AudioValidator(min_duration=20.0, max_duration=75.0)
        result = v.validate(wav)
        assert not result.is_valid
        assert TTS_NEAR_SILENT in result.error_codes

    @patch("src.audio.validator.AudioValidator._ffmpeg_can_decode", return_value=True)
    def test_audible_audio_accepted(self, mock_decode, tmp_path):
        """Audible audio within duration range should pass."""
        wav = write_wav(tmp_path / "good.wav", seconds=40.0, amplitude=8000)
        v = AudioValidator(min_duration=20.0, max_duration=75.0)
        result = v.validate(wav)
        assert result.is_valid
        assert result.info["duration"] == pytest.approx(40.0, abs=0.5)
        assert result.info["rms"] > 0.005


class TestDecodeCheck:
    """Test FFmpeg decode gate."""

    def test_decode_failure_rejected(self, tmp_path):
        """If FFmpeg cannot decode, file should be rejected."""
        wav = write_wav(tmp_path / "good.wav", seconds=40.0)
        v = AudioValidator(min_duration=20.0, max_duration=75.0)

        with patch.object(
            AudioValidator, "_ffmpeg_can_decode", return_value=False
        ):
            result = v.validate(wav)
        assert not result.is_valid
        assert TTS_DECODE_FAILED in result.error_codes

    def test_decode_success_accepted(self, tmp_path):
        """If FFmpeg decodes successfully, file passes."""
        wav = write_wav(tmp_path / "good.wav", seconds=40.0)
        v = AudioValidator(min_duration=20.0, max_duration=75.0)
        with patch.object(
            AudioValidator, "_ffmpeg_can_decode", return_value=True
        ):
            result = v.validate(wav)
        assert result.is_valid

        # Real ffprobe test
        ffprobe_result = v._ffmpeg_can_decode(wav)
        assert ffprobe_result is True


class TestValidateAudioHelper:
    """Test validate_audio convenience function."""

    def test_validate_audio_return_type(self, tmp_path):
        """validate_audio should return AudioValidationResult."""
        wav = write_wav(tmp_path / "g.wav", seconds=40.0)
        result = validate_audio(wav, min_duration=20.0, max_duration=75.0)
        assert isinstance(result, AudioValidationResult)

    def test_missing_defaults(self):
        """Missing file with defaults is rejected."""
        result = validate_audio("/does/not/exist.wav")
        assert not result.is_valid


class TestRMSComputation:
    """Test RMS helper."""

    def test_silence_rms_zero(self):
        from src.audio.validator import _rms_from_samples
        assert _rms_from_samples(b"\x00\x00" * 100) == 0.0

    def test_full_scale_rms(self):
        from src.audio.validator import _rms_from_samples
        # 16-bit full scale constant tone -> RMS = 0.5 (relative to 32767)
        data = struct.pack("<h", 32767) * 100
        rms = _rms_from_samples(data)
        assert 0.49 < rms <= 1.0

    def test_empty_rms_zero(self):
        from src.audio.validator import _rms_from_samples
        assert _rms_from_samples(b"") == 0.0
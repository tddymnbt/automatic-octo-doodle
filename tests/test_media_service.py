"""Tests for the MediaService (ffmpeg-skill integration layer)."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.video.media_service import (
    SCRIPTS_DIR,
    MediaProbeError,
    MediaService,
    MediaServiceError,
    MediaVerificationResult,
    MediaVerifyError,
    create_media_service,
)


def make_probe_data(overrides: dict | None = None) -> dict:
    """Create a realistic ffmpeg-skill probe JSON."""
    data = {
        "file": "/tmp/video.mp4",
        "format": "mp4",
        "duration": 45.2,
        "size_bytes": 1024 * 1024,
        "bitrate": 1000 * 1000,
        "video": {
            "codec": "h264",
            "width": 1080,
            "height": 1920,
            "fps": 30.0,
            "pix_fmt": "yuv420p",
            "hdr": False,
            "color_primaries": "bt709",
            "color_transfer": "bt709",
        },
        "audio": {"codec": "aac", "channels": 1, "sample_rate": 24000},
        "subtitle_streams": 0,
        "data_streams": 0,
    }
    if overrides:
        # shallow merge for top-level, deep merge for video/audio
        for k, v in overrides.items():
            if k in ("video", "audio") and isinstance(v, dict):
                data[k].update(v)
            else:
                data[k] = v
    return data


def write_wav(path: Path, seconds: float = 45.0, sample_rate: int = 24000):
    """Write a synthetic WAV for input probing."""
    import struct
    import wave
    frames = int(seconds * sample_rate)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(struct.pack("<h", 8000) * frames)


class TestInit:
    """Test MediaService initialization."""

    def test_default_scripts_dir_is_vendored(self):
        """Default scripts dir should point at the vendored media/scripts."""
        svc = MediaService.__new__(MediaService)
        assert SCRIPTS_DIR.name == "scripts"
        assert (SCRIPTS_DIR / "probe.py").exists()
        assert (SCRIPTS_DIR / "check.py").exists()

    def test_missing_scripts_raises(self, tmp_path):
        """MediaService should raise if probe.py is missing."""
        empty = tmp_path / "empty"
        empty.mkdir()
        with pytest.raises(MediaServiceError, match="scripts missing"):
            MediaService(scripts_dir=empty)


class TestProbe:
    """Test media probing."""

    @patch("src.video.media_service.MediaService._run_script")
    @patch("src.video.media_service.VideoRenderer")
    def test_probe_parses_facts(self, mock_renderer, mock_run, tmp_path):
        """Probe should return structured facts."""
        mock_run.return_value = make_probe_data()
        svc = MediaService(scripts_dir=SCRIPTS_DIR, renderer=mock_renderer)
        facts = svc.probe(tmp_path / "v.mp4")
        assert facts["video"]["width"] == 1080
        assert facts["video"]["height"] == 1920
        assert facts["video"]["fps"] == 30.0
        assert facts["audio"]["codec"] == "aac"
        assert facts["duration"] == 45.2

    @patch("src.video.media_service.MediaService._run_script")
    @patch("src.video.media_service.VideoRenderer")
    def test_probe_runs_with_json_flag(self, mock_renderer, mock_run, tmp_path):
        """Probe should pass --json to the script."""
        mock_run.return_value = make_probe_data()
        svc = MediaService(scripts_dir=SCRIPTS_DIR, renderer=mock_renderer)
        svc.probe(tmp_path / "v.mp4")
        args = mock_run.call_args[0][1]
        assert str(tmp_path / "v.mp4") in args
        assert "--json" in args

    @patch("src.video.media_service.MediaService._run_script")
    @patch("src.video.media_service.VideoRenderer")
    def test_probe_failure_raises_probe_error(self, mock_renderer, mock_run, tmp_path):
        """A failed probe should raise MediaProbeError."""
        mock_run.side_effect = MediaServiceError("probe failed: boom")
        svc = MediaService(scripts_dir=SCRIPTS_DIR, renderer=mock_renderer)
        with pytest.raises(MediaProbeError):
            svc.probe(tmp_path / "missing.mp4")


class TestVerify:
    """Test media verification against platform + exact contract."""

    def _check_payload(self, rows: list[dict], failed: int = 0) -> dict:
        return {
            "status": "completed",
            "checks": rows,
            "failed": failed,
            "warnings": 0,
            "ok": failed == 0,
        }

    def test_verify_passes_compliant(self, tmp_path):
        """Compliant Reels file should pass verification."""
        rows = [
            {"check": "duration", "status": "PASS", "value": "45.20s", "expected": "<= 90"},
            {"check": "aspect", "status": "PASS", "value": "9:16", "expected": "9:16"},
            {"check": "resolution", "status": "PASS", "value": "1080x1920", "expected": "short side >= 1080"},
            {"check": "fps", "status": "PASS", "value": "30", "expected": "<= 60"},
            {"check": "video codec", "status": "PASS", "value": "h264", "expected": "h264/hevc"},
            {"check": "pixel format", "status": "PASS", "value": "yuv420p", "expected": "yuv420p"},
            {"check": "audio", "status": "PASS", "value": "aac 1ch 24000Hz", "expected": "present"},
        ]
        with patch("src.video.media_service.MediaService._run_script") as mock_run:
            mock_run.side_effect = [
                self._check_payload(rows),
                make_probe_data(),
            ]
            svc = MediaService(scripts_dir=SCRIPTS_DIR, renderer=MagicMock())
            result = svc.verify(tmp_path / "final.mp4")

        assert result.valid is True
        assert result.errors == []
        assert result.warnings == []
        assert result.probe["video"]["width"] == 1080

    def test_verify_rejects_failed_rows(self, tmp_path):
        """FAIL rows should become errors and invalidate the result."""
        rows = [
            {"check": "aspect", "status": "FAIL", "value": "4:3", "expected": "9:16"},
            {"check": "audio", "status": "PASS", "value": "aac", "expected": "present"},
        ]
        with patch("src.video.media_service.MediaService._run_script") as mock_run:
            mock_run.side_effect = [
                self._check_payload(rows, failed=1),
                make_probe_data(),
            ]
            svc = MediaService(scripts_dir=SCRIPTS_DIR, renderer=MagicMock())
            result = svc.verify(tmp_path / "bad.mp4")

        assert result.valid is False
        assert any("aspect" in e for e in result.errors)

    def test_verify_rejects_wrong_dimensions(self, tmp_path):
        """Exact-contract check should reject wrong dimensions."""
        rows = [{"check": "aspect", "status": "PASS", "value": "9:16", "expected": "9:16"}]
        probe = make_probe_data({"video": {"width": 1920, "height": 1080}})
        with patch("src.video.media_service.MediaService._run_script") as mock_run:
            mock_run.side_effect = [
                self._check_payload(rows),
                probe,
            ]
            svc = MediaService(scripts_dir=SCRIPTS_DIR, renderer=MagicMock())
            result = svc.verify(tmp_path / "landscape.mp4")

        assert result.valid is False
        assert any("width" in e for e in result.errors)
        assert any("height" in e for e in result.errors)

    def test_verify_rejects_too_short(self, tmp_path):
        """Exact-contract check should reject videos < 30s."""
        rows = [{"check": "duration", "status": "PASS", "value": "45.20s", "expected": "<= 90"}]
        probe = make_probe_data({"duration": 12.0})
        with patch("src.video.media_service.MediaService._run_script") as mock_run:
            mock_run.side_effect = [
                self._check_payload(rows),
                probe,
            ]
            svc = MediaService(scripts_dir=SCRIPTS_DIR, renderer=MagicMock())
            result = svc.verify(tmp_path / "short.mp4")

        assert result.valid is False
        assert any("duration" in e for e in result.errors)

    def test_verify_no_audio(self, tmp_path):
        """A file without audio should be rejected."""
        rows = [{"check": "audio", "status": "WARN", "value": "none", "expected": "audio stream"}]
        probe = make_probe_data({"audio": None})
        with patch("src.video.media_service.MediaService._run_script") as mock_run:
            mock_run.side_effect = [
                self._check_payload(rows, failed=0),
                probe,
            ]
            svc = MediaService(scripts_dir=SCRIPTS_DIR, renderer=MagicMock())
            result = svc.verify(tmp_path / "noaudio.mp4")

        assert result.valid is False
        assert any("audio" in e.lower() for e in result.errors)

    def test_verify_passes_warnings(self, tmp_path):
        """WARN rows should not invalidate; they surface as warnings."""
        rows = [{"check": "sample rate", "status": "WARN", "value": "22050Hz", "expected": "44100 or 48000"}]
        with patch("src.video.media_service.MediaService._run_script") as mock_run:
            mock_run.side_effect = [
                self._check_payload(rows, failed=0),
                make_probe_data(),
            ]
            svc = MediaService(scripts_dir=SCRIPTS_DIR, renderer=MagicMock())
            result = svc.verify(tmp_path / "warn.mp4")

        assert result.valid is True
        assert any("sample rate" in w for w in result.warnings)

    def test_verify_runs_reels_platform(self, tmp_path):
        """verify should use --platform reels."""
        rows = [{"check": "aspect", "status": "PASS", "value": "9:16", "expected": "9:16"}]
        with patch("src.video.media_service.MediaService._run_script") as mock_run:
            mock_run.side_effect = [
                self._check_payload(rows),
                make_probe_data(),
            ]
            svc = MediaService(scripts_dir=SCRIPTS_DIR, renderer=MagicMock())
            svc.verify(tmp_path / "v.mp4", platform="reels")
            args = mock_run.call_args_list[0][0][1]
            assert "--platform" in args
            assert "reels" in args

    def test_verify_probe_failure_raises(self, tmp_path):
        """If the probe during verify fails, raise MediaVerifyError."""
        rows = [{"check": "aspect", "status": "PASS", "value": "9:16"}]
        with patch("src.video.media_service.MediaService._run_script") as mock_run:
            mock_run.side_effect = [
                self._check_payload(rows),
                MediaServiceError("probe failed"),
            ]
            svc = MediaService(scripts_dir=SCRIPTS_DIR, renderer=MagicMock())
            with pytest.raises(MediaVerifyError):
                svc.verify(tmp_path / "v.mp4")


class TestResultShape:
    """Test MediaVerificationResult."""

    def test_defaults(self):
        r = MediaVerificationResult()
        assert r.valid is True
        assert r.errors == []
        assert r.warnings == []
        assert r.error_count == 0
        assert r.warning_count == 0

    def test_to_dict(self):
        r = MediaVerificationResult(valid=False, errors=["e1"], warnings=["w1"])
        d = r.to_dict()
        assert d["valid"] is False
        assert d["errors"] == ["e1"]
        assert d["warnings"] == ["w1"]


class TestFactory:
    """Test create_media_service factory."""

    def test_factory_returns_service(self):
        svc = create_media_service()
        assert isinstance(svc, MediaService)

    def test_factory_accepts_renderer(self):
        renderer = MagicMock()
        svc = create_media_service(renderer=renderer)
        assert svc.renderer is renderer


class TestIntegrationWithVendoredScripts:
    """Real execution against vendored ffmpeg-skill scripts (needs ffmpeg)."""

    @pytest.mark.skipif(
        not (SCRIPTS_DIR / "probe.py").exists() or not (SCRIPTS_DIR / "check.py").exists(),
        reason="vendored scripts not present",
    )
    def test_real_probe_on_synthetic_wav(self, tmp_path):
        """The vendored probe.py should probe a real WAV."""
        import shutil
        if not shutil.which("ffprobe"):
            pytest.skip("ffprobe not available")
        wav = tmp_path / "test.wav"
        write_wav(wav, seconds=1.0)
        svc = MediaService(scripts_dir=SCRIPTS_DIR, renderer=MagicMock())
        facts = svc.probe(wav)
        assert facts.get("audio", {}).get("codec") == "pcm_s16le"
        assert facts.get("duration", 0) == pytest.approx(1.0, abs=0.2)
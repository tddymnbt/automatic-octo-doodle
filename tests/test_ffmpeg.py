"""Tests for FFmpeg video renderer."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.video.ffmpeg import FFmpegError, FFmpegNotFoundError, VideoRenderer, create_video_renderer


class TestVideoRendererInit:
    """Test VideoRenderer initialization."""

    @patch("src.video.ffmpeg.shutil.which")
    @patch("src.video.ffmpeg.Path.exists")
    def test_init_with_ffmpeg(self, mock_exists, mock_which):
        """Should initialize when FFmpeg is found."""
        mock_which.return_value = "/usr/bin/ffmpeg"
        mock_exists.return_value = False

        renderer = VideoRenderer()

        assert renderer._ffmpeg_path == "/usr/bin/ffmpeg"
        assert renderer.width == 1080
        assert renderer.height == 1920
        assert renderer.fps == 30

    @patch("src.video.ffmpeg.shutil.which")
    @patch("src.video.ffmpeg.Path.exists")
    def test_init_ffmpeg_not_found(self, mock_exists, mock_which):
        """Should raise error when FFmpeg not found."""
        mock_which.return_value = None
        mock_exists.return_value = False

        with pytest.raises(FFmpegNotFoundError):
            VideoRenderer()

    @patch("src.video.ffmpeg.shutil.which")
    @patch("src.video.ffmpeg.Path.exists")
    def test_init_custom_settings(self, mock_exists, mock_which):
        """Should accept custom settings."""
        mock_which.return_value = "/usr/bin/ffmpeg"
        mock_exists.return_value = False

        renderer = VideoRenderer(width=1920, height=1080, fps=60)

        assert renderer.width == 1920
        assert renderer.height == 1080
        assert renderer.fps == 60

    @patch("src.video.ffmpeg.shutil.which", return_value="/usr/bin/ffmpeg")
    @patch("src.video.ffmpeg.Path.exists", return_value=False)
    def test_subtitles_not_probed_on_init(self, mock_exists, mock_which):
        """Constructing a renderer should NOT probe filter support (shell out)."""
        renderer = VideoRenderer()
        assert renderer._subtitles_available is None
        # No subprocess probe on construction.


class TestVideoRendererRunFFmpeg:
    """Test FFmpeg command execution."""

    @patch("src.video.ffmpeg.shutil.which", return_value="/usr/bin/ffmpeg")
    @patch("src.video.ffmpeg.Path.exists", return_value=False)
    @patch("src.video.ffmpeg.subprocess.run")
    def test_run_ffmpeg_success(self, mock_run, mock_exists, mock_which):
        """Should run FFmpeg command successfully."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stderr = ""
        mock_run.return_value = mock_result

        renderer = VideoRenderer()
        result = renderer._run_ffmpeg(["ffmpeg", "-version"])

        assert result == mock_result
        mock_run.assert_called_once()

    @patch("src.video.ffmpeg.shutil.which", return_value="/usr/bin/ffmpeg")
    @patch("src.video.ffmpeg.Path.exists", return_value=False)
    @patch("src.video.ffmpeg.subprocess.run")
    def test_run_ffmpeg_failure(self, mock_run, mock_exists, mock_which):
        """Should raise error on FFmpeg failure."""
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "Error: invalid argument"
        mock_run.return_value = mock_result

        renderer = VideoRenderer()

        with pytest.raises(FFmpegError, match="FFmpeg failed"):
            renderer._run_ffmpeg(["ffmpeg", "-badflag"])


class TestSubtitlesSupported:
    """Test subtitle filter capability probe."""

    @patch("src.video.ffmpeg.shutil.which", return_value="/usr/bin/ffmpeg")
    @patch("src.video.ffmpeg.Path.exists", return_value=False)
    @patch("src.video.ffmpeg.subprocess.run")
    def test_has_subtitles_filter(self, mock_run, mock_exists, mock_which):
        """Probe should detect the subtitles filter when present."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = (
            "Filters:\n"
            "  .. subtitles        V->V  Render text subtitles onto input video\n"
        )
        mock_run.return_value = mock_result

        renderer = VideoRenderer()
        renderer.enable_subtitles = True
        assert renderer._has_filter("subtitles") is True


class TestApplyReverb:
    """Test reverb application."""

    @patch("src.video.ffmpeg.shutil.which", return_value="/usr/bin/ffmpeg")
    @patch("src.video.ffmpeg.Path.exists", return_value=False)
    @patch("src.video.ffmpeg.subprocess.run")
    def test_applies_aecho(self, mock_run, mock_exists, mock_which, tmp_path):
        """Should apply subtle aecho reverb with configured params."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_run.return_value = mock_result

        renderer = VideoRenderer()
        inp = tmp_path / "narration.wav"
        inp.write_bytes(b"fake audio")
        out = tmp_path / "reverb.wav"

        result = renderer.apply_reverb(inp, out, delay_ms=30, decay=0.4, wet=0.06)

        assert result == out
        cmd = mock_run.call_args[0][0]
        # cmd = [ffmpeg, -y, -i, inp, -af, aecho=1:0.06:30:0.4, -ar, 24000, out]
        assert any("aecho" in arg for arg in cmd)
        assert cmd[5] == "aecho=1:0.06:30:0.4"
        assert "-ar" in cmd
        assert "24000" in cmd


class TestRenderBlackVideo:
    """Test the black-background render path."""

    @patch("src.video.ffmpeg.shutil.which", return_value="/usr/bin/ffmpeg")
    @patch("src.video.ffmpeg.Path.exists", return_value=False)
    @patch("src.video.ffmpeg.subprocess.run")
    def test_render_black_video(self, mock_run, mock_exists, mock_which, tmp_path):
        """Should render black video with reverb and subtitles (mocked)."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_run.return_value = mock_result

        renderer = VideoRenderer()
        renderer._subtitles_available = True

        narration = tmp_path / "narration.wav"
        narration.write_bytes(b"fake audio")
        subtitle = tmp_path / "subs.srt"
        subtitle.write_text("1\n00:00:00,000 --> 00:00:02,000\nAmen.\n")
        output = tmp_path / "output.mp4"

        with patch.object(renderer, "validate_video") as mock_validate:
            mock_validate.return_value = {
                "valid": True,
                "width": 1080,
                "height": 1920,
                "fps": 30,
                "duration": 45,
                "has_audio": True,
            }
            result = renderer.render_black_video(
                narration_wav=narration,
                subtitle_srt=subtitle,
                output_path=output,
                reverb=True,
            )

        assert result == output
        assert mock_run.call_count >= 1


class TestValidateVideo:
    """Test video validation."""

    @patch("src.video.ffmpeg.shutil.which", return_value="/usr/bin/ffmpeg")
    @patch("src.video.ffmpeg.Path.exists", return_value=False)
    @patch("src.video.ffmpeg.subprocess.run")
    def test_validate_video_success(self, mock_run, mock_exists, mock_which):
        """Should validate video correctly."""
        with patch("pathlib.Path.exists", return_value=True):
            def side_effect(cmd, **kwargs):
                mock_result = MagicMock()
                mock_result.returncode = 0
                if "format=duration" in " ".join(cmd):
                    mock_result.stdout = '{"format": {"duration": "45.5"}}'
                elif "a:0" in " ".join(cmd):
                    mock_result.stdout = '{"streams": [{"codec_name": "aac"}]}'
                else:
                    mock_result.stdout = '{"streams": [{"width": 1080, "height": 1920, "r_frame_rate": "30/1", "codec_name": "h264"}]}'
                return mock_result
            mock_run.side_effect = side_effect

            renderer = VideoRenderer()
            result = renderer.validate_video(Path("/tmp/video.mp4"))

        assert result["valid"] is True
        assert result["width"] == 1080
        assert result["height"] == 1920
        assert result["has_audio"] is True

    @patch("src.video.ffmpeg.shutil.which", return_value="/usr/bin/ffmpeg")
    @patch("src.video.ffmpeg.Path.exists", return_value=False)
    @patch("src.video.ffmpeg.subprocess.run")
    def test_validate_video_no_audio(self, mock_run, mock_exists, mock_which):
        """Should fail validation when no audio stream present."""
        def side_effect(cmd, **kwargs):
            mock_result = MagicMock()
            mock_result.returncode = 0
            if "format=duration" in " ".join(cmd):
                mock_result.stdout = '{"format": {"duration": "45.5"}}'
            elif "a:0" in " ".join(cmd):
                mock_result.stdout = '{"streams": []}'
            else:
                mock_result.stdout = '{"streams": [{"width": 1080, "height": 1920, "r_frame_rate": "30/1", "codec_name": "h264"}]}'
            return mock_result
        mock_run.side_effect = side_effect

        renderer = VideoRenderer()

        with pytest.raises(FFmpegError, match="No audio stream"):
            with patch("pathlib.Path.exists", return_value=True):
                renderer.validate_video(Path("/tmp/video.mp4"))


class TestRenderBackgroundAmbient:
    """Test rendering with a background image/video + ambient audio."""

    def _renderer(self):
        """Renderer with subtitles available, ffmpeg mocked."""
        from unittest.mock import MagicMock, patch

        with patch("src.video.ffmpeg.shutil.which", return_value="/usr/bin/ffmpeg"), \
             patch("src.video.ffmpeg.Path.exists", return_value=False):
            r = VideoRenderer()
        r._subtitles_available = True
        return r

    def _start_ffmpeg_mock(self, stdout: str = ""):
        """Start a subprocess.run mock; returns the mock (for call_args)."""
        from unittest.mock import MagicMock, patch
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = stdout
        mock_patcher = patch("src.video.ffmpeg.subprocess.run", return_value=mock_result)
        mock_run = mock_patcher.start()
        return mock_patcher, mock_run, mock_result

    def test_background_image_uses_loop(self, tmp_path, monkeypatch):
        """A still-image background should be looped into an infinite stream."""
        mp, m, _ = self._start_ffmpeg_mock()
        try:
            r = self._renderer()
            bg = tmp_path / "bg.webp"
            bg.write_bytes(b"fake image")
            narr = tmp_path / "n.wav"
            narr.write_bytes(b"fake")
            srt = tmp_path / "s.srt"
            srt.write_text("1\n00:00:00,000 --> 00:00:02,000\nAmen.\n")
            out = tmp_path / "o.mp4"
            with patch.object(r, "validate_video", return_value={"valid": True}):
                r.render_black_video(
                    narration_wav=narr, subtitle_srt=srt, output_path=out,
                    background_path=bg,
                )
            cmd = m.call_args[0][0]
            assert "-loop" in cmd
            assert "1" in cmd
            assert str(bg) in cmd
            # scale/crop to target
            filter_complex = cmd[cmd.index("-filter_complex") + 1]
            assert "scale=1080:1920" in filter_complex
            assert "crop=1080:1920" in filter_complex
        finally:
            mp.stop()

    def test_background_video_uses_stream_loop(self, tmp_path, monkeypatch):
        """A video background should use -stream_loop -1 (not -loop 1)."""
        mp, m, _ = self._start_ffmpeg_mock()
        try:
            r = self._renderer()
            bg = tmp_path / "bg.webm"
            bg.write_bytes(b"fake video")
            narr = tmp_path / "n.wav"
            narr.write_bytes(b"fake")
            srt = tmp_path / "s.srt"
            srt.write_text("1\n00:00:00,000 --> 00:00:02,000\nAmen.\n")
            out = tmp_path / "o.mp4"
            with patch.object(r, "validate_video", return_value={"valid": True}):
                r.render_black_video(
                    narration_wav=narr, subtitle_srt=srt, output_path=out,
                    background_path=bg,
                )
            cmd = m.call_args[0][0]
            assert "-stream_loop" in cmd
            assert "-1" in cmd
            assert "-loop" not in cmd
        finally:
            mp.stop()

    def test_ambient_duck_uses_sidechain_and_asplit(self, tmp_path, monkeypatch):
        """Ambient ducking should use sidechaincompress + asplit so narration
        stays clear and the ambient is ducked under the voice."""
        mp, m, _ = self._start_ffmpeg_mock(stdout="45.0\n")
        try:
            r = self._renderer()
            narr = tmp_path / "n.wav"
            narr.write_bytes(b"fake")
            amb = tmp_path / "amb.wav"
            amb.write_bytes(b"fake ambient")
            srt = tmp_path / "s.srt"
            srt.write_text("1\n00:00:00,000 --> 00:00:02,000\nAmen.\n")
            out = tmp_path / "o.mp4"
            with patch.object(r, "validate_video", return_value={"valid": True}):
                r.render_black_video(
                    narration_wav=narr, subtitle_srt=srt, output_path=out,
                    ambient_wav=amb, ambient_level=0.15,
                    ambient_fade_in=2.0, ambient_fade_out=2.0,
                    ambient_duck=True,
                )
            cmd = m.call_args[0][0]
            fc = cmd[cmd.index("-filter_complex") + 1]
            assert "sidechaincompress" in fc
            assert "asplit=2" in fc
            assert "volume=0.15" in fc
            assert "afade=t=in:st=0:d=2.0" in fc
            assert "amix=inputs=2:duration=first:normalize=0" in fc
        finally:
            mp.stop()

    def test_ambient_no_duck_plain_amix(self, tmp_path, monkeypatch):
        """Without duck, ambient should mix plainly (no sidechain)."""
        mp, m, _ = self._start_ffmpeg_mock(stdout="45.0\n")
        try:
            r = self._renderer()
            narr = tmp_path / "n.wav"; narr.write_bytes(b"fake")
            amb = tmp_path / "amb.wav"; amb.write_bytes(b"fake")
            srt = tmp_path / "s.srt"; srt.write_text("1\n00:00:00,000 --> 00:00:02,000\nAmen.\n")
            out = tmp_path / "o.mp4"
            with patch.object(r, "validate_video", return_value={"valid": True}):
                r.render_black_video(
                    narration_wav=narr, subtitle_srt=srt, output_path=out,
                    ambient_wav=amb, ambient_duck=False,
                )
            cmd = m.call_args[0][0]
            fc = cmd[cmd.index("-filter_complex") + 1]
            assert "sidechaincompress" not in fc
            assert "amix=inputs=2:duration=first:normalize=0" in fc
        finally:
            mp.stop()


class TestFactory:
    """Test factory function."""

    @patch("src.video.ffmpeg.shutil.which", return_value="/usr/bin/ffmpeg")
    @patch("src.video.ffmpeg.Path.exists", return_value=False)
    def test_create_video_renderer(self, mock_exists, mock_which):
        """Factory should create renderer."""
        renderer = create_video_renderer()
        assert isinstance(renderer, VideoRenderer)

    @patch("src.video.ffmpeg.shutil.which", return_value="/usr/bin/ffmpeg")
    @patch("src.video.ffmpeg.Path.exists", return_value=False)
    def test_create_with_custom_settings(self, mock_exists, mock_which):
        """Factory should accept custom settings."""
        renderer = create_video_renderer(width=1920, height=1080)
        assert renderer.width == 1920
        assert renderer.height == 1080


class TestErrorHierarchy:
    """Test exception hierarchy."""

    def test_ffmpeg_error_base(self):
        """FFmpegError should be Exception."""
        assert issubclass(FFmpegError, Exception)

    def test_ffmpeg_not_found_error(self):
        """FFmpegNotFoundError should inherit from FFmpegError."""
        assert issubclass(FFmpegNotFoundError, FFmpegError)

    def test_error_messages(self):
        """Errors should have proper messages."""
        err = FFmpegError("test message")
        assert str(err) == "test message"

        err2 = FFmpegNotFoundError("not found")
        assert str(err2) == "not found"
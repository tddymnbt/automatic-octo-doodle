"""Tests for FFmpeg video renderer."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.assets.models import Asset, AssetCategory
from src.content.schema import Scene, StoryData
from src.video.ffmpeg import FFmpegError, FFmpegNotFoundError, VideoRenderer, create_video_renderer


class TestVideoRendererInit:
    """Test VideoRenderer initialization."""
    
    @patch("src.video.ffmpeg.shutil.which")
    def test_init_with_ffmpeg(self, mock_which):
        """Should initialize when FFmpeg is found."""
        mock_which.return_value = "/usr/bin/ffmpeg"
        
        renderer = VideoRenderer()
        
        assert renderer._ffmpeg_path == "/usr/bin/ffmpeg"
        assert renderer.width == 1080
        assert renderer.height == 1920
        assert renderer.fps == 30
    
    @patch("src.video.ffmpeg.shutil.which")
    def test_init_ffmpeg_not_found(self, mock_which):
        """Should raise error when FFmpeg not found."""
        mock_which.return_value = None
        
        with pytest.raises(FFmpegNotFoundError):
            VideoRenderer()
    
    @patch("src.video.ffmpeg.shutil.which")
    def test_init_custom_settings(self, mock_which):
        """Should accept custom settings."""
        mock_which.return_value = "/usr/bin/ffmpeg"
        
        renderer = VideoRenderer(width=1920, height=1080, fps=60)
        
        assert renderer.width == 1920
        assert renderer.height == 1080
        assert renderer.fps == 60


class TestVideoRendererRunFFmpeg:
    """Test FFmpeg command execution."""
    
    @patch("src.video.ffmpeg.shutil.which", return_value="/usr/bin/ffmpeg")
    @patch("src.video.ffmpeg.subprocess.run")
    def test_run_ffmpeg_success(self, mock_run, mock_which):
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
    @patch("src.video.ffmpeg.subprocess.run")
    def test_run_ffmpeg_failure(self, mock_run, mock_which):
        """Should raise error on FFmpeg failure."""
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "Error: invalid argument"
        mock_run.return_value = mock_result
        
        renderer = VideoRenderer()
        
        with pytest.raises(FFmpegError, match="FFmpeg failed"):
            renderer._run_ffmpeg(["ffmpeg", "-invalid"])
    
    @patch("src.video.ffmpeg.shutil.which", return_value="/usr/bin/ffmpeg")
    @patch("src.video.ffmpeg.subprocess.run")
    def test_run_ffmpeg_timeout(self, mock_run, mock_which):
        """Should raise error on timeout."""
        import subprocess
        mock_run.side_effect = subprocess.TimeoutExpired("ffmpeg", 300)
        
        renderer = VideoRenderer()
        
        with pytest.raises(FFmpegError, match="timed out"):
            renderer._run_ffmpeg(["ffmpeg", "-version"])


class TestCreateImageSegment:
    """Test image segment creation."""
    
    @patch("src.video.ffmpeg.shutil.which", return_value="/usr/bin/ffmpeg")
    @patch("src.video.ffmpeg.subprocess.run")
    def test_create_image_segment(self, mock_run, mock_which):
        """Should create image segment with Ken Burns effect."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_run.return_value = mock_result
        
        renderer = VideoRenderer()
        asset = Asset(
            path=Path("/assets/image.jpg"),
            category=AssetCategory.BEDROOM,
            filename="image.jpg",
        )
        output = Path("/tmp/segment.mp4")
        
        renderer._create_image_segment(
            asset=asset,
            duration=5.0,
            output=output,
            is_first=True,
            is_last=False,
        )
        
        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        assert cmd[0] == "/usr/bin/ffmpeg"
        assert "-loop" in cmd
        assert "1" in cmd
        assert str(asset.path) in cmd
        assert "zoompan" in " ".join(cmd)


class TestCreateVideoSegment:
    """Test video segment creation."""
    
    @patch("src.video.ffmpeg.shutil.which", return_value="/usr/bin/ffmpeg")
    @patch("src.video.ffmpeg.subprocess.run")
    def test_create_video_segment(self, mock_run, mock_which):
        """Should create video segment from video asset."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_run.return_value = mock_result
        
        renderer = VideoRenderer()
        asset = Asset(
            path=Path("/assets/video.mp4"),
            category=AssetCategory.CITY,
            filename="video.mp4",
        )
        output = Path("/tmp/segment.mp4")
        
        renderer._create_video_segment(
            asset=asset,
            duration=5.0,
            output=output,
        )
        
        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        assert "-an" in cmd  # No audio from source


class TestWriteConcatFile:
    """Test concat file writing."""
    
    @patch("src.video.ffmpeg.shutil.which", return_value="/usr/bin/ffmpeg")
    def test_write_concat_file(self, mock_which, tmp_path):
        """Should write concat file correctly."""
        renderer = VideoRenderer()
        
        segments = [
            Path("/tmp/seg1.mp4"),
            Path("/tmp/seg2.mp4"),
        ]
        concat_file = tmp_path / "concat.txt"
        
        renderer._write_concat_file(segments, concat_file)
        
        content = concat_file.read_text()
        assert "file '/tmp/seg1.mp4'" in content
        assert "file '/tmp/seg2.mp4'" in content


class TestRenderFinalVideo:
    """Test final video rendering."""
    
    @patch("src.video.ffmpeg.shutil.which", return_value="/usr/bin/ffmpeg")
    @patch("src.video.ffmpeg.subprocess.run")
    def test_render_final_video_narration_only(self, mock_run, mock_which, tmp_path):
        """Should render with narration only."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_run.return_value = mock_result
        
        renderer = VideoRenderer()
        
        concat_file = tmp_path / "concat.txt"
        concat_file.write_text("file 'seg1.mp4'\nfile 'seg2.mp4'")
        
        narration = tmp_path / "narration.wav"
        narration.write_bytes(b"fake audio")
        
        subtitle = tmp_path / "subs.srt"
        subtitle.write_text("1\n00:00:00,000 --> 00:00:02,000\nHello")
        
        output = tmp_path / "output.mp4"
        
        renderer._render_final_video(
            concat_file=concat_file,
            narration_audio=narration,
            subtitle_file=subtitle,
            output_path=output,
            ambient_audio=None,
            ambient_volume=0.1,
        )
        
        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        assert "-f" in cmd
        assert "concat" in cmd
        assert "subtitles" in " ".join(cmd)
        # The subtitle path must be absolute (ffmpeg resolves relative to CWD)
        assert str(subtitle.resolve()) in " ".join(cmd)


class TestValidateVideo:
    """Test video validation."""
    
    @patch("src.video.ffmpeg.shutil.which", return_value="/usr/bin/ffmpeg")
    @patch("src.video.ffmpeg.subprocess.run")
    @patch("src.video.ffmpeg.Path.exists")
    def test_validate_video_success(self, mock_exists, mock_run, mock_which):
        """Should validate video correctly."""
        mock_exists.return_value = True
        
        # Mock ffprobe responses
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
        validation = renderer.validate_video(Path("/tmp/video.mp4"))
        
        assert validation["valid"] is True
        assert validation["width"] == 1080
        assert validation["height"] == 1920
        assert abs(validation["fps"] - 30) < 0.1
        assert validation["duration"] == 45.5
        assert validation["has_audio"] is True
    
    @patch("src.video.ffmpeg.shutil.which", return_value="/usr/bin/ffmpeg")
    @patch("src.video.ffmpeg.subprocess.run")
    @patch("src.video.ffmpeg.Path.exists")
    def test_validate_video_wrong_dimensions(self, mock_exists, mock_run, mock_which):
        """Should fail validation for wrong dimensions."""
        mock_exists.return_value = True
        
        def side_effect(cmd, **kwargs):
            mock_result = MagicMock()
            mock_result.returncode = 0
            mock_result.stdout = '{"streams": [{"width": 1920, "height": 1080, "r_frame_rate": "30/1", "codec_name": "h264"}]}'
            return mock_result
        
        mock_run.side_effect = side_effect
        
        renderer = VideoRenderer()
        
        with pytest.raises(FFmpegError, match="Width mismatch"):
            renderer.validate_video(Path("/tmp/video.mp4"))
    
    @patch("src.video.ffmpeg.shutil.which", return_value="/usr/bin/ffmpeg")
    @patch("src.video.ffmpeg.subprocess.run")
    @patch("src.video.ffmpeg.Path.exists")
    def test_validate_video_no_audio(self, mock_exists, mock_run, mock_which):
        """Should fail validation for missing audio."""
        mock_exists.return_value = True
        
        def side_effect(cmd, **kwargs):
            mock_result = MagicMock()
            mock_result.returncode = 0
            if "a:0" in " ".join(cmd):
                mock_result.stdout = '{"streams": []}'
            else:
                mock_result.stdout = '{"streams": [{"width": 1080, "height": 1920, "r_frame_rate": "30/1", "codec_name": "h264"}]}'
            return mock_result
        
        mock_run.side_effect = side_effect
        
        renderer = VideoRenderer()
        
        with pytest.raises(FFmpegError, match="No audio stream"):
            renderer.validate_video(Path("/tmp/video.mp4"))


class TestFullRenderPipeline:
    """Test full render pipeline (mocked)."""
    
    @patch("src.video.ffmpeg.shutil.which", return_value="/usr/bin/ffmpeg")
    @patch("src.video.ffmpeg.subprocess.run")
    def test_render_story(self, mock_run, mock_which, tmp_path):
        """Should render complete story video."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_run.return_value = mock_result
        
        renderer = VideoRenderer()
        
        # Create story with valid narration length
        story = StoryData(
            title="Test Story",
            hook="Test hook sentence here.",
            narration="This is the first scene with some narration. This is the second scene with more narration text.",
            scenes=[
                Scene(description="bedroom", duration_seconds=3.0, category="bedroom"),
                Scene(description="forest", duration_seconds=3.0, category="forest"),
            ],
        )
        
        # Create assets
        assets = [
            Asset(path=tmp_path / "bedroom.jpg", category=AssetCategory.BEDROOM, filename="bedroom.jpg"),
            Asset(path=tmp_path / "forest.jpg", category=AssetCategory.FOREST, filename="forest.jpg"),
        ]
        
        # Create dummy files
        (tmp_path / "bedroom.jpg").write_bytes(b"fake image")
        (tmp_path / "forest.jpg").write_bytes(b"fake image")
        narration = tmp_path / "narration.wav"
        narration.write_bytes(b"fake audio")
        subtitle = tmp_path / "subs.srt"
        subtitle.write_text("1\n00:00:00,000 --> 00:00:03,000\nFirst scene.\n")
        output = tmp_path / "output.mp4"
        
        # Mock validate_video to return success
        with patch.object(renderer, "validate_video") as mock_validate:
            mock_validate.return_value = {
                "valid": True,
                "width": 1080,
                "height": 1920,
                "fps": 30,
                "duration": 45,
                "has_audio": True,
            }
            
            result = renderer.render(
                story=story,
                assets=assets,
                narration_audio=narration,
                subtitle_file=subtitle,
                output_path=output,
            )
            
            assert result == output
            # Should have been called multiple times for segments + final
            assert mock_run.call_count >= 3


class TestFactory:
    """Test factory function."""
    
    @patch("src.video.ffmpeg.shutil.which", return_value="/usr/bin/ffmpeg")
    def test_create_video_renderer(self, mock_which):
        """Factory should create renderer."""
        renderer = create_video_renderer()
        assert isinstance(renderer, VideoRenderer)
    
    @patch("src.video.ffmpeg.shutil.which", return_value="/usr/bin/ffmpeg")
    def test_create_with_custom_settings(self, mock_which):
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
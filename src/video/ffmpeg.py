"""FFmpeg video renderer for ASMR story videos.

This module renders the final video by combining:
- Background images (with pan/zoom effects)
- TTS narration audio
- Burned-in subtitles
- Optional ambient audio

Output: 1080x1920 H.264/AAC MP4 at 30 FPS
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import tempfile
from pathlib import Path

from src.assets.models import Asset, AssetCategory
from src.content.schema import StoryData

logger = logging.getLogger(__name__)


class FFmpegError(Exception):
    """Base exception for FFmpeg errors."""


class FFmpegNotFoundError(FFmpegError):
    """FFmpeg executable not found."""


class VideoRenderer:
    """Renders ASMR story videos using FFmpeg.
    
    This renderer:
    1. Creates a visual sequence from assets matching story scenes
    2. Applies pan/zoom effects (Ken Burns style)
    3. Adds narration audio
    4. Burns in subtitles
    5. Outputs validated MP4
    """
    
    # Video output settings
    WIDTH = 1080
    HEIGHT = 1920
    FPS = 30
    VIDEO_CODEC = "libx264"
    AUDIO_CODEC = "aac"
    PIXEL_FORMAT = "yuv420p"
    
    # Transition settings
    TRANSITION_DURATION = 0.5  # Crossfade duration in seconds
    
    def __init__(
        self,
        width: int = WIDTH,
        height: int = HEIGHT,
        fps: int = FPS,
        video_codec: str = VIDEO_CODEC,
        audio_codec: str = AUDIO_CODEC,
        pixel_format: str = PIXEL_FORMAT,
        enable_subtitles: bool = True,
    ) -> None:
        """Initialize the video renderer.
        
        Args:
            width: Output width
            height: Output height
            fps: Frame rate
            video_codec: Video codec
            audio_codec: Audio codec
            pixel_format: Pixel format
            enable_subtitles: Whether to burn subtitles into the video.
                Requires an FFmpeg build with the 'subtitles' filter (libass).
                Some Homebrew snapshots omit libass; disable this if your
                FFmpeg lacks the filter. The GitHub Actions runner installs a
                libass-enabled FFmpeg, so CI should keep this enabled.
        """
        self.width = width
        self.height = height
        self.fps = fps
        self.video_codec = video_codec
        self.audio_codec = audio_codec
        self.pixel_format = pixel_format
        self.enable_subtitles = enable_subtitles
        
        # Check FFmpeg availability
        self._ffmpeg_path = self._find_ffmpeg()
        logger.info(f"Video renderer initialized: {width}x{height}@{fps}fps, subtitles={'yes' if enable_subtitles else 'no'}")
    
    def _find_ffmpeg(self) -> str:
        """Find FFmpeg executable."""
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            raise FFmpegNotFoundError("FFmpeg not found in PATH")
        return ffmpeg
    
    def render(
        self,
        story: StoryData,
        assets: list[Asset],
        narration_audio: Path,
        subtitle_file: Path,
        output_path: Path,
        ambient_audio: Path | None = None,
        ambient_volume: float = 0.1,
    ) -> Path:
        """Render the final video.
        
        Args:
            story: Story data with scenes
            assets: Selected visual assets
            narration_audio: Path to TTS narration WAV
            subtitle_file: Path to SRT subtitle file
            output_path: Output MP4 path
            ambient_audio: Optional ambient audio file
            ambient_volume: Ambient audio volume (0.0-1.0)
            
        Returns:
            Path to rendered video
            
        Raises:
            FFmpegError: If rendering fails
        """
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Create temporary directory for intermediate files
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            
            # Build visual segments
            segment_files = self._build_visual_segments(
                story, assets, tmpdir_path
            )
            
            if not segment_files:
                raise FFmpegError("No visual segments created")
            
            # Concatenate segments
            concat_file = tmpdir_path / "concat.txt"
            self._write_concat_file(segment_files, concat_file)
            
            # Build final video
            self._render_final_video(
                concat_file=concat_file,
                narration_audio=narration_audio,
                subtitle_file=subtitle_file,
                output_path=output_path,
                ambient_audio=ambient_audio,
                ambient_volume=ambient_volume,
            )
        
        # Validate output
        self.validate_video(output_path)
        
        logger.info(f"Video rendered: {output_path}")
        return output_path
    
    def _build_visual_segments(
        self,
        story: StoryData,
        assets: list[Asset],
        tmpdir: Path,
    ) -> list[Path]:
        """Build visual segments for each scene.
        
        Args:
            story: Story data
            assets: Available assets
            tmpdir: Temporary directory
            
        Returns:
            List of segment video file paths
        """
        segment_files = []
        
        # Group assets by category (using string keys since scene.category is a string)
        assets_by_category: dict[str, list[Asset]] = {}
        for asset in assets:
            cat_str = asset.category.value if isinstance(asset.category, AssetCategory) else str(asset.category)
            if cat_str not in assets_by_category:
                assets_by_category[cat_str] = []
            assets_by_category[cat_str].append(asset)
        
        for i, scene in enumerate(story.scenes):
            # Get asset for this scene (scene.category is a string)
            scene_category = scene.category
            scene_assets = assets_by_category.get(scene_category, [])
            
            if not scene_assets:
                logger.warning(f"No assets for scene {i+1} category '{scene_category}'")
                # Use first available asset as fallback
                for cat_assets in assets_by_category.values():
                    if cat_assets:
                        scene_assets = cat_assets
                        break
            
            if not scene_assets:
                raise FFmpegError("No visual assets available")
            
            # Use first matching asset
            asset = scene_assets[0]
            
            # Create segment
            segment_file = tmpdir / f"segment_{i:02d}.mp4"
            
            if asset.is_image:
                self._create_image_segment(
                    asset=asset,
                    duration=scene.duration_seconds,
                    output=segment_file,
                    is_first=(i == 0),
                    is_last=(i == len(story.scenes) - 1),
                )
            elif asset.is_video:
                self._create_video_segment(
                    asset=asset,
                    duration=scene.duration_seconds,
                    output=segment_file,
                )
            else:
                raise FFmpegError(f"Unsupported asset type: {asset.path}")
            
            segment_files.append(segment_file)
        
        return segment_files
    
    def _create_image_segment(
        self,
        asset: Asset,
        duration: float,
        output: Path,
        is_first: bool = False,
        is_last: bool = False,
    ) -> None:
        """Create video segment from still image with Ken Burns effect.
        
        Args:
            asset: Image asset
            duration: Segment duration in seconds
            output: Output file path
            is_first: Whether this is the first segment
            is_last: Whether this is the last segment
        """
        # Ken Burns effect: slow zoom/pan
        # Calculate zoom factor (start at 1.0, end at 1.15 over duration)
        zoom_start = 1.0
        zoom_end = 1.15
        
        # Build filter complex
        filters = [
            # Scale and crop to maintain aspect
            f"scale={self.width}:{self.height}:force_original_aspect_ratio=increase",
            f"crop={self.width}:{self.height}",
            # Apply zoom/pan animation
            (
                f"zoompan=z='min({zoom_start}+(zoom/100),{zoom_end})':"
                f"d={int(duration * self.fps)}:s={self.width}x{self.height}"
            ),
            # Fade in/out
            (
                f"fade=t=in:st=0:d={self.TRANSITION_DURATION},"
                f"fade=t=out:st={duration - self.TRANSITION_DURATION}:d={self.TRANSITION_DURATION}"
            ),
        ]
        
        filter_str = ",".join(filters)
        
        cmd = [
            self._ffmpeg_path,
            "-y",  # Overwrite
            "-loop", "1",
            "-i", str(asset.path),
            "-t", str(duration),
            "-vf", filter_str,
            "-c:v", self.video_codec,
            "-pix_fmt", self.pixel_format,
            "-r", str(self.fps),
            "-preset", "medium",
            "-crf", "23",
            str(output),
        ]
        
        self._run_ffmpeg(cmd)
    
    def _create_video_segment(
        self,
        asset: Asset,
        duration: float,
        output: Path,
    ) -> None:
        """Create video segment from video asset.
        
        Args:
            asset: Video asset
            duration: Target duration
            output: Output file path
        """
        cmd = [
            self._ffmpeg_path,
            "-y",
            "-i", str(asset.path),
            "-t", str(duration),
            "-vf", f"scale={self.width}:{self.height}:force_original_aspect_ratio=increase,crop={self.width}:{self.height}",
            "-c:v", self.video_codec,
            "-pix_fmt", self.pixel_format,
            "-r", str(self.fps),
            "-preset", "medium",
            "-crf", "23",
            "-an",  # No audio from source video
            str(output),
        ]
        
        self._run_ffmpeg(cmd)
    
    def _write_concat_file(self, segment_files: list[Path], concat_file: Path) -> None:
        """Write FFmpeg concat file.
        
        Args:
            segment_files: List of segment paths
            concat_file: Output concat file path
        """
        content = "\n".join(f"file '{f}'" for f in segment_files)
        concat_file.write_text(content)
    
    def _render_final_video(
        self,
        concat_file: Path,
        narration_audio: Path,
        subtitle_file: Path,
        output_path: Path,
        ambient_audio: Path | None,
        ambient_volume: float,
    ) -> None:
        """Render final video with audio and subtitles.
        
        Args:
            concat_file: Concat file with segments
            narration_audio: Narration audio file
            subtitle_file: SRT subtitle file
            output_path: Output video path
            ambient_audio: Optional ambient audio
            ambient_volume: Ambient volume level
        """
        # Build video filter list; subtitle burn only if enabled
        video_filters: list[str] = []
        if self.enable_subtitles:
            # Pass the absolute subtitle path to ffmpeg's subtitles filter.
            # FFmpeg resolves the path relative to the PROCESS CWD, not the
            # temp dir, so we must use an absolute path. Escape quote + backslash
            # for ffmpeg's filtergraph quoting.
            sub_path = str(subtitle_file.resolve())
            sub_path = sub_path.replace("\\", "\\\\").replace("'", "'\\''")
            # force_style colon-options are protected by quoting the whole value.
            video_filters.append(
                f"subtitles='{sub_path}':force_style="
                "'FontSize=48,FontName=Arial,Outline=2,Shadow=2,Alignment=2,MarginV=100'"
            )
        
        # Audio filter
        if ambient_audio and ambient_audio.exists():
            # Mix narration with ambient
            audio_filter = (
                f"[1:a]volume=1.0[nar];"
                f"[2:a]volume={ambient_volume}[amb];"
                f"[nar][amb]amix=inputs=2:duration=first:dropout_transition=0[aout]"
            )
            inputs = [
                "-f", "concat", "-safe", "0", "-i", str(concat_file),
                "-i", str(narration_audio),
                "-i", str(ambient_audio),
            ]
        else:
            # Narration only
            audio_filter = "[1:a]anull[aout]"
            inputs = [
                "-f", "concat", "-safe", "0", "-i", str(concat_file),
                "-i", str(narration_audio),
            ]
        
        cmd = [
            self._ffmpeg_path,
            "-y",
            *inputs,
            "-filter_complex", f"{audio_filter}",
            "-map", "0:v",
            "-map", "[aout]",
        ]
        if video_filters:
            cmd += ["-vf", ",".join(video_filters)]
        cmd += [
            "-c:v", self.video_codec,
            "-pix_fmt", self.pixel_format,
            "-r", str(self.fps),
            "-c:a", self.audio_codec,
            "-b:a", "128k",
            "-preset", "medium",
            "-crf", "23",
            "-shortest",
            str(output_path),
        ]
        
        self._run_ffmpeg(cmd)
    
    def _run_ffmpeg(self, cmd: list[str]) -> subprocess.CompletedProcess:
        """Run FFmpeg command.
        
        Args:
            cmd: FFmpeg command arguments
            
        Returns:
            Completed process result
            
        Raises:
            FFmpegError: If command fails
        """
        logger.debug(f"Running FFmpeg: {' '.join(cmd)}")
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300,  # 5 minute timeout
            )
        except subprocess.TimeoutExpired:
            raise FFmpegError("FFmpeg timed out after 5 minutes")
        except FileNotFoundError:
            raise FFmpegNotFoundError("FFmpeg executable not found")
        
        if result.returncode != 0:
            logger.error(f"FFmpeg failed: {result.stderr}")
            raise FFmpegError(f"FFmpeg failed with code {result.returncode}: {result.stderr[:500]}")
        
        return result
    
    def validate_video(self, video_path: Path) -> dict:
        """Validate rendered video meets specifications.
        
        Args:
            video_path: Path to video file
            
        Returns:
            Dictionary with validation results
            
        Raises:
            FFmpegError: If validation fails
        """
        if not video_path.exists():
            raise FFmpegError(f"Video file not found: {video_path}")
        
        # Use ffprobe to get video info
        cmd = [
            "ffprobe",
            "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=width,height,r_frame_rate,codec_name",
            "-of", "json",
            str(video_path),
        ]
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if result.returncode != 0:
                raise FFmpegError(f"ffprobe failed: {result.stderr}")
        except FileNotFoundError:
            raise FFmpegError("ffprobe not found")
        
        import json
        info = json.loads(result.stdout)
        
        if not info.get("streams"):
            raise FFmpegError("No video stream found")
        
        stream = info["streams"][0]
        
        # Parse frame rate
        fps_str = stream.get("r_frame_rate", "0/1")
        if "/" in fps_str:
            num, den = map(int, fps_str.split("/"))
            actual_fps = num / den if den > 0 else 0
        else:
            actual_fps = float(fps_str)
        
        # Get duration
        duration_cmd = [
            "ffprobe",
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "json",
            str(video_path),
        ]
        duration_result = subprocess.run(duration_cmd, capture_output=True, text=True)
        duration_info = json.loads(duration_result.stdout)
        duration = float(duration_info.get("format", {}).get("duration", 0))
        
        # Get audio info
        audio_cmd = [
            "ffprobe",
            "-v", "error",
            "-select_streams", "a:0",
            "-show_entries", "stream=codec_name",
            "-of", "json",
            str(video_path),
        ]
        audio_result = subprocess.run(audio_cmd, capture_output=True, text=True)
        audio_info = json.loads(audio_result.stdout)
        has_audio = bool(audio_info.get("streams"))
        
        # Validate
        validation = {
            "valid": True,
            "errors": [],
            "warnings": [],
            "width": stream.get("width"),
            "height": stream.get("height"),
            "fps": actual_fps,
            "duration": duration,
            "video_codec": stream.get("codec_name"),
            "has_audio": has_audio,
        }
        
        # Check dimensions
        if stream.get("width") != self.width:
            validation["errors"].append(f"Width mismatch: {stream.get('width')} != {self.width}")
            validation["valid"] = False
        
        if stream.get("height") != self.height:
            validation["errors"].append(f"Height mismatch: {stream.get('height')} != {self.height}")
            validation["valid"] = False
        
        # Check FPS (allow small tolerance)
        if abs(actual_fps - self.fps) > 1:
            validation["warnings"].append(f"FPS mismatch: {actual_fps:.2f} != {self.fps}")
        
        # Check duration (30-60 seconds)
        if duration < 30:
            validation["warnings"].append(f"Video too short: {duration:.1f}s < 30s")
        elif duration > 60:
            validation["warnings"].append(f"Video too long: {duration:.1f}s > 60s")
        
        # Check audio
        if not has_audio:
            validation["errors"].append("No audio stream found")
            validation["valid"] = False
        
        if validation["errors"]:
            raise FFmpegError(f"Video validation failed: {'; '.join(validation['errors'])}")
        
        logger.info(f"Video validated: {self.width}x{self.height}@{actual_fps:.1f}fps, {duration:.1f}s")
        return validation


def create_video_renderer(
    width: int = VideoRenderer.WIDTH,
    height: int = VideoRenderer.HEIGHT,
    fps: int = VideoRenderer.FPS,
) -> VideoRenderer:
    """Factory function to create a video renderer.
    
    Args:
        width: Output width
        height: Output height
        fps: Frame rate
        
    Returns:
        VideoRenderer instance
    """
    return VideoRenderer(width=width, height=height, fps=fps)
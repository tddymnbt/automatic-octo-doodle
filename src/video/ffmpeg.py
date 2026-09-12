"""FFmpeg video renderer for Daily Gospel / Daily Bread Shorts.

This module renders the final video by combining:
- A solid black background (technical MVP: no images/stock/AI art)
- TTS narration audio
- Subtle church/chapel-style reverb applied to the narration
- Burned-in subtitles

Output: 1080x1920 H.264/AAC MP4 at 30 FPS
"""

from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


class FFmpegError(Exception):
    """Base exception for FFmpeg errors."""


class FFmpegNotFoundError(FFmpegError):
    """FFmpeg executable not found."""


class VideoRenderer:
    """Renders Daily Gospel / Daily Bread videos using FFmpeg.
    
    This renderer:
    1. Uses a solid black background by default (technical MVP), or a
       supplied background image/video layered beneath subtitles.
    2. Applies subtle church/chapel-style reverb to the narration.
    3. Optionally mixes a low ambient track (faded in/out, ducked under
       the voice) so narration stays clear and foreground.
    4. Burns in subtitles (middle-aligned).
    5. Outputs a validated 1080x1920 H.264/AAC MP4 at 30 FPS.
    """
    
    # Video output settings
    WIDTH = 1080
    HEIGHT = 1920
    FPS = 30
    VIDEO_CODEC = "libx264"
    AUDIO_CODEC = "aac"
    PIXEL_FORMAT = "yuv420p"

    # Background video extensions (looped); anything else treated as still image.
    VIDEO_SUFFIXES = {".mp4", ".mov", ".avi", ".webm"}
    
    # Reverb defaults (subtle church/chapel acoustic space).
    REVERB_DISABLED = False
    REVERB_DELAY = 30      # ms: time between reflections
    REVERB_DECAY = 0.4     # amplitude decay of the echoes (0=off, <1 = decay)
    REVERB_WET = 0.06      # gain of the reflections (small = subtle)

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
        
        self._ffmpeg_path = self._find_ffmpeg()
        # Whether the subtitles (libass) filter is available. Probed lazily on
        # first render and cached, so constructing a renderer doesn't shell out
        # (keeps unit tests that mock subprocess.run predictable).
        self._subtitles_available: bool | None = None

    def _subtitles_supported(self) -> bool:
        """Return True if the FFmpeg build provides the subtitles filter.

        Some Homebrew FFmpeg builds omit libass; degrade gracefully rather
        than fail the whole render. CI's apt FFmpeg (and most distro builds)
        ship it. Result is cached after the first probe.
        """
        if self._subtitles_available is None:
            self._subtitles_available = self._has_filter("subtitles")
            if self.enable_subtitles and not self._subtitles_available:
                logger.warning(
                    "FFmpeg build lacks the 'subtitles' filter (no libass); "
                    "rendering WITHOUT burned-in subtitles. Install a libass-"
                    "enabled FFmpeg to restore subtitle support."
                )
        return self._subtitles_available

    def _find_ffmpeg(self) -> str:
        """Find FFmpeg executable, preferring a libass-enabled build.

        Homebrew's regular ``ffmpeg`` formula ships without libass (no
        ``subtitles``/``ass`` filters); ``ffmpeg-full`` includes it. Prefer the
        full build when present so burned-in subtitles work locally, fall back
        to PATH. The GitHub Actions runner installs a libass-enabled FFmpeg,
        so CI resolves via PATH.
        """
        for candidate in (
            "/opt/homebrew/opt/ffmpeg-full/bin/ffmpeg",
            "/usr/local/opt/ffmpeg-full/bin/ffmpeg",
        ):
            if Path(candidate).exists():
                return candidate
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            raise FFmpegNotFoundError("FFmpeg not found in PATH")
        return ffmpeg

    def _has_filter(self, name: str) -> bool:
        """Return True if the FFmpeg build provides the given filter."""
        try:
            result = subprocess.run(
                [self._ffmpeg_path, "-hide_banner", "-filters"],
                capture_output=True,
                text=True,
                timeout=30,
            )
        except (subprocess.SubprocessError, OSError):
            return False
        # -filters lines look like: "  .. subtitles       V->V  Convert ..."
        # Match the filter name as a standalone token in the line.
        return any(
            name in line.split()
            for line in result.stdout.splitlines()
        )

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
                timeout=600,  # 10 minute timeout (CI runners are slower)
            )
        except subprocess.TimeoutExpired:
            raise FFmpegError("FFmpeg timed out after 10 minutes")
        except FileNotFoundError:
            raise FFmpegNotFoundError("FFmpeg executable not found")
        
        if result.returncode != 0:
            logger.error(f"FFmpeg failed: {result.stderr}")
            raise FFmpegError(f"FFmpeg failed with code {result.returncode}: {result.stderr[:500]}")
        
        return result
    
    def apply_reverb(
        self,
        input_wav: Path,
        output_wav: Path,
        *,
        delay_ms: int | None = None,
        decay: float | None = None,
        wet: float | None = None,
    ) -> Path:
        """Apply subtle church-style reverb to a WAV file using FFmpeg ``aecho``.

        The aecho filter adds early reflections at the given delay. ``wet``
        controls the reflection amplitude; ``decay`` is the echo's own decay
        factor. Values default to the class constants for a soft chapel feel.
        """
        delay_ms = delay_ms if delay_ms is not None else self.REVERB_DELAY
        decay = decay if decay is not None else self.REVERB_DECAY
        wet = wet if wet is not None else self.REVERB_WET
        out = Path(output_wav)
        out.parent.mkdir(parents=True, exist_ok=True)
        cmd = [
            self._ffmpeg_path, "-y",
            "-i", str(input_wav),
            "-af", f"aecho=1:{wet}:{delay_ms}:{decay}",
            "-ar", "24000",
            str(out),
        ]
        self._run_ffmpeg(cmd)
        logger.info(f"Reverb applied: {out}")
        return out

    def render_black_video(
        self,
        narration_wav: Path,
        subtitle_srt: Path,
        output_path: Path,
        *,
        subtitle_style: str | None = None,
        reverb: bool = True,
        reverb_delay_ms: int | None = None,
        reverb_decay: float | None = None,
        reverb_wet: float | None = None,
        sync_segments: list | None = None,
        background_path: Path | str | None = None,
        ambient_wav: Path | str | None = None,
        ambient_level: float = 0.15,
        ambient_fade_in: float = 2.0,
        ambient_fade_out: float = 2.0,
        ambient_duck: bool = True,
    ) -> Path:
        """Render an MP4 (black or background-image subject) with burned-in subtitles.

        Pipeline:
          narration.wav
            -> optional reverb (aecho)
            -> black 1080x1920 video (colour source) OR a background
               image/video scaled+scaled-cropped to 1080x1920
            + optional ambient track: low level, faded in/out, ducked under
              the narration so the voice stays clear and foreground
            + subtitle SRT/ASS (ass filter / libass), middle-aligned
            -> 1080x1920 H.264/AAC MP4

        Args:
            narration_wav: 24 kHz mono WAV (raw or post-reverb)
            subtitle_srt: SRT file with segment-aligned text (fallback)
            output_path: final MP4 destination
            subtitle_style: optional override for force_style string (SRT path only)
            reverb: apply aecho reverb before mixing
            reverb_delay_ms: ms between reflections
            reverb_decay: amplitude decay factor
            reverb_wet: reflection gain
            sync_segments: optional speech-aligned segments (SyncedSegment) for
                accurate ASS generation with absolute positioning. If provided,
                an ASS file is created and burned instead of the SRT path.
            background_path: optional image (.jpg/.webp/.png) or video
                (.mp4/.webm) used as the visual base layer. If None, a pure
                black background is used (backward-compatible).
            ambient_wav: optional ambient/background audio track. Mixed at a
                low level (ambient_level), faded in/out, and optionally ducked
                under the narration so the voice stays clear.
            ambient_level: ambient volume as a fraction of narration (e.g.
                0.15 = 15%). Relative to the ducked/attenuated ambient.
            ambient_fade_in: seconds to fade ambient in from silence.
            ambient_fade_out: seconds to fade ambient out to silence at the end.
            ambient_duck: duck the ambient under the narration (sidechain).

        Returns:
            Path to the final rendered MP4
        """
        from src.video.subtitles import entries_to_ass

        # ---- Reverb on narration (unchanged) ----
        audio_wav = narration_wav
        if reverb:
            tmp = output_path.parent / (output_path.stem + "_reverb.wav")
            audio_wav = self.apply_reverb(
                narration_wav, tmp,
                delay_ms=reverb_delay_ms, decay=reverb_decay, wet=reverb_wet,
            )

        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)

        # ---- Subtitle burn-in filter (unchanged) ----
        if sync_segments:
            from src.video.subtitles import SubtitleGenerator, entries_to_ass
            gen = SubtitleGenerator()
            entries = gen.from_synced_segments(sync_segments)
            ass_path = out.parent / (out.stem + "_subs.ass")
            ass_text = entries_to_ass(
                entries,
                width=self.width,
                height=self.height,
                font_name="DejaVu Sans",
                font_size=56,
                margin_v=0,
                primary="FFFFFF",
                outline_color="000000",
            )
            ass_path.write_text(ass_text, encoding="utf-8")
            sub_path = str(ass_path.resolve()).replace("\\", "\\\\").replace("'", "'\\''")
            vf = f"ass='{sub_path}'"
            logger.info(f"Using ASS burn-in: {ass_path}")
        else:
            if subtitle_style is None:
                subtitle_style = (
                    "FontName=DejaVu Sans,"
                    "FontSize=34,"
                    "PrimaryColour=&H00FFFFFF,"
                    "OutlineColour=&H80000000,"
                    "BorderStyle=1,"
                    "Outline=2,"
                    "Shadow=1,"
                    "Alignment=5,"
                    "MarginV=0"
                )
            sub_path = str(subtitle_srt.resolve()).replace("\\", "\\\\").replace("'", "'\\''")
            style_safe = subtitle_style.replace("'", "'\\''")
            vf = f"subtitles='{sub_path}':force_style='{style_safe}'"
            logger.info(f"Using SRT burn-in: {subtitle_srt}")

        # ---- Build the FFmpeg command ----
        cmd = [self._ffmpeg_path, "-y"]

        # Input 0: video source (background image/video OR pure black).
        bg = Path(background_path) if background_path is not None else None
        use_background = bg is not None and bg.exists()
        if use_background:
            assert bg is not None
            if bg.suffix.lower() in self.VIDEO_SUFFIXES:
                # Video background: loop to cover narration
                cmd += ["-stream_loop", "-1", "-i", str(bg)]
            else:
                # Still image background: loop as an infinite video stream
                cmd += ["-loop", "1", "-i", str(bg)]
        else:
            cmd += [
                "-f", "lavfi",
                "-i", f"color=c=black:s={self.width}x{self.height}:r={self.fps}:d=900",
            ]

        # Input 1: narration (post-reverb).
        cmd += ["-i", str(Path(audio_wav))]

        # Input 2 (optional): ambient track.
        amb = Path(ambient_wav) if ambient_wav is not None else None
        use_ambient = amb is not None and amb.exists()
        if use_ambient:
            cmd += ["-i", str(amb)]

        # ---- Audio filtergraph ----
        # Label narration always [1:a]; ambient (if any) is [2:a].
        fc = []
        narration_dur = self._probe_duration(Path(audio_wav)) if use_ambient else 0.0

        if use_ambient:
            amb_fade_out_st = max(0.0, narration_dur - ambient_fade_out)
            amb_filter = (
                f"[2:a]aresample=48000,volume={ambient_level},"
                f"afade=t=in:st=0:d={ambient_fade_in},"
                f"afade=t=out:st={amb_fade_out_st:.3f}:d={ambient_fade_out}[aa]"
            )
            fc.append(amb_filter)
            if ambient_duck:
                # Fork narration: one copy drives sidechain, one mixes with
                # attenuated ambient. (FFmpeg requires asplit for labels
                # consumed by multiple filters.)
                fc.append("[1:a]aresample=48000,volume=1.0,asplit=2[narr][side]")
                fc.append(
                    "[aa][side]sidechaincompress="
                    "threshold=0.05:ratio=6:attack=20:release=300[duck]"
                )
                fc.append("[narr][duck]amix=inputs=2:duration=first:normalize=0[a]")
            else:
                fc.append("[1:a]aresample=48000,volume=1.0[na]")
                fc.append("[na][aa]amix=inputs=2:duration=first:normalize=0[a]")
        else:
            fc.append("[1:a]aresample=48000[a]")

        # ---- Video filtergraph ----
        if use_background:
            v0 = (
                f"[0:v]scale={self.width}:{self.height}:force_original_aspect_ratio=increase,"
                f"crop={self.width}:{self.height},"
            )
        else:
            v0 = "[0:v]"
        fc.append(f"{v0}{vf},format=yuv420p[v]")

        cmd += ["-filter_complex", ";".join(fc)]

        encode_args = [
            "-map", "[v]", "-map", "[a]",
            "-c:v", self.video_codec,
            "-pix_fmt", self.pixel_format,
            "-color_range", "tv",
            "-colorspace", "bt709",
            "-r", str(self.fps),
            "-c:a", self.audio_codec,
            "-ar", "48000",
            "-b:a", "128k",
            "-preset", "medium",
            "-crf", "23",
            "-shortest",
            str(out),
        ]
        cmd += encode_args
        self._run_ffmpeg(cmd)

        bg_desc = str(bg) if use_background else "black"
        logger.info(f"Video rendered ({bg_desc} background): {out}")
        return out

    def _probe_duration(self, media: Path) -> float:
        """Return the duration (seconds) of a media file via ffprobe.

        Returns 0.0 if probing fails (e.g. in unit tests where ffprobe is
        mocked away) rather than raising, so render is never blocked.
        """
        ffprobe = shutil.which("ffprobe")
        if not ffprobe and self._ffmpeg_path:
            # Derive ffprobe from the ffmpeg path (same dir).
            candidate = str(Path(self._ffmpeg_path).with_name("ffprobe"))
            if Path(candidate).exists():
                ffprobe = candidate
        if not ffprobe:
            logger.warning("ffprobe not found; ambient fade-out timing degraded")
            return 0.0
        try:
            result = subprocess.run(
                [
                    ffprobe, "-v", "error",
                    "-show_entries", "format=duration",
                    "-of", "csv=p=0",
                    str(media),
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )
            return float(result.stdout.strip())
        except (ValueError, subprocess.SubprocessError, OSError):
            return 0.0

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
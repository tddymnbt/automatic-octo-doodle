"""Media service - unified media execution + verification layer.

This module is the application's single boundary for media operations:

    Application
        ↓
    MediaService / VideoService
        ↓
    ffmpeg-skill (vendored scripts) / VideoRenderer
        ↓
    FFmpeg / ffprobe

It wraps:
- The vendored ffmpeg-skill CLI tools (probe/check) for deterministic
  media probing and platform-compliance verification.
- The existing VideoRenderer for composition (black background,
  narration audio, reverb, subtitles).

The application calls MediaService methods instead of scattering raw
ffmpeg/ffprobe commands across modules.

Flow: probe → check → verify → structured result.
"""
from __future__ import annotations

import json
import logging
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from src.video.ffmpeg import VideoRenderer

logger = logging.getLogger(__name__)

# Default path to vendored ffmpeg-skill scripts (project-relative)
SCRIPTS_DIR = Path(__file__).resolve().parent.parent.parent / "media" / "scripts"


class MediaServiceError(Exception):
    """Base error for media service operations."""


class MediaProbeError(MediaServiceError):
    """Media probing failed."""


class MediaVerifyError(MediaServiceError):
    """Media verification failed (deliverable does not meet contract)."""


@dataclass
class MediaVerificationResult:
    """Structured result of a media verification."""

    valid: bool = True
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    checks: list[dict] = field(default_factory=list)
    probe: dict = field(default_factory=dict)

    @property
    def error_count(self) -> int:
        return len(self.errors)

    @property
    def warning_count(self) -> int:
        return len(self.warnings)

    def to_dict(self) -> dict:
        return {
            "valid": self.valid,
            "errors": self.errors,
            "warnings": self.warnings,
            "checks": self.checks,
            "probe": self.probe,
        }


class MediaService:
    """Unified media probe/verify/render service backed by ffmpeg-skill + VideoRenderer.

    Attributes:
        scripts_dir: Path to vendored ffmpeg-skill scripts.
        renderer: VideoRenderer used for compositing.
    """

    # Production delivery contract (Reels-compatible), kept explicit.
    CONTRACT_WIDTH = 1080
    CONTRACT_HEIGHT = 1920
    CONTRACT_FPS = 30
    CONTRACT_MIN_DURATION = 30
    CONTRACT_MAX_DURATION = 60
    CONTRACT_VIDEO_CODEC = "h264"
    CONTRACT_AUDIO_CODEC = "aac"

    def __init__(
        self,
        scripts_dir: Path | str | None = None,
        renderer: VideoRenderer | None = None,
        python: str = "python3",
    ) -> None:
        """Initialize the media service.

        Args:
            scripts_dir: Path to vendored ffmpeg-skill scripts.
                Defaults to the project's media/scripts.
            renderer: Optional VideoRenderer (defaults to a standard one).
        """
        self.scripts_dir = Path(scripts_dir) if scripts_dir else SCRIPTS_DIR
        self.python = python
        self.renderer = renderer or VideoRenderer()
        self._check_scripts()

    def _check_scripts(self) -> None:
        """Verify required ffmpeg-skill scripts exist."""
        missing = [s for s in ("probe.py", "check.py", "caption.py") if not (self.scripts_dir / s).exists()]
        if missing:
            raise MediaServiceError(
                f"ffmpeg-skill scripts missing in {self.scripts_dir}: {', '.join(missing)}. "
                "Vendor them via 'npx ffmpeg-skill --project' or commit media/scripts/."
            )

    def _script(self, name: str) -> Path:
        return self.scripts_dir / f"{name}.py"

    def _run_script(
        self,
        name: str,
        args: list[str],
        *,
        check: bool = True,
        timeout: int = 120,
    ) -> dict:
        """Run a vendored ffmpeg-skill script and parse its JSON output.

        Args:
            name: Script name without .py
            args: CLI arguments after the script name
            check: If True, raise MediaServiceError on non-zero exit
            timeout: Subprocess timeout in seconds

        Returns:
            Parsed JSON dict (status: completed/failed + result fields)
        """
        script = self._script(name)
        cmd = [self.python, str(script), *args]
        logger.debug(f"Media service running: {' '.join(cmd)}")
        try:
            proc = subprocess.run(
                cmd, capture_output=True, text=True, timeout=timeout, check=False,
            )
        except FileNotFoundError as e:
            raise MediaServiceError(
                f"Python interpreter '{self.python}' not found; cannot run media scripts"
            ) from e
        except subprocess.TimeoutExpired as e:
            raise MediaServiceError(f"Media script {name} timed out after {timeout}s") from e

        stdout = proc.stdout or ""
        try:
            data = json.loads(stdout)
        except json.JSONDecodeError:
            if proc.returncode != 0:
                raise MediaServiceError(
                    f"Media script {name} failed (exit {proc.returncode}): {proc.stderr.strip()[:500]}"
                )
            raise MediaServiceError(f"Media script {name} produced non-JSON output: {stdout[:300]}")

        # If the script returned a structured error (status:failed), surface it.
        if data.get("status") == "failed":
            msg = data.get("error", {}).get("message") or "unknown error"
            if check:
                raise MediaServiceError(f"Media script {name} failed: {msg}")
        # For non-zero exits where no structured JSON error was returned,
        # raise only if check=True.
        elif proc.returncode != 0:
            msg = proc.stderr.strip()[:500] or f"exit code {proc.returncode}"
            if check:
                raise MediaServiceError(f"Media script {name} failed (exit {proc.returncode}): {msg}")
        return data

    # ------------------------------------------------------------------
    # PROBE
    # ------------------------------------------------------------------
    def probe(self, media_path: Path | str) -> dict:
        """Probe a media file and return structured facts.

        Uses the vendored ffmpeg-skill probe.py.

        Returns:
            Dict with format/duration/video/audio facts.

        Raises:
            MediaProbeError: If probing fails.
        """
        path = Path(media_path)
        try:
            data = self._run_script("probe", [str(path), "--json"])
        except MediaServiceError as e:
            raise MediaProbeError(str(e)) from e
        # probe.py prints the probe document directly (no status envelope).
        if data.get("status") == "failed":
            raise MediaProbeError(f"probe failed on {path}: {data.get('error', {}).get('message')}")
        # Normalize: return the probe document itself.
        return data if "video" in data or "audio" in data or "format" in data else {}

    # ------------------------------------------------------------------
    # VERIFY
    # ------------------------------------------------------------------
    def verify(
        self,
        media_path: Path | str,
        *,
        platform: str = "reels",
        exact_contract: bool = True,
    ) -> MediaVerificationResult:
        """Verify a media file against the platform spec (and exact contract).

        Runs ffmpeg-skill check.py --platform <platform> and additionally
        checks the exact project contract (1080x1920, 30fps, h264/aac,
        30-60s) via probe.

        Args:
            media_path: Path to the media file
            platform: check.py platform (default reels)
            exact_contract: If True, also enforce the exact project contract.

        Returns:
            MediaVerificationResult with errors/warnings.

        Raises:
            MediaProbeError: If the file cannot be probed.
        """
        path = Path(media_path)
        result = MediaVerificationResult()

        # 1. Platform compliance via ffmpeg-skill check.py
        # check.py exits 1 when FAILs are found — use check=False to get the data.
        try:
            check_data = self._run_script(
                "check", [str(path), "--platform", platform, "--json", "--no-loudness"],
                check=False,
            )
        except MediaServiceError as e:
            raise MediaVerifyError(f"check failed on {path}: {e}") from e

        # If check.py itself crashed (no JSON), fail the verification.
        if check_data.get("status") == "failed":
            raise MediaVerifyError(
                f"check.py returned failure on {path}: "
                f"{check_data.get('error', {}).get('message', 'unknown')}"
            )

        checks = check_data.get("checks", [])
        result.checks = checks
        for c in checks:
            if c.get("status") == "FAIL":
                result.errors.append(f"{c.get('check')}: {c.get('value')} (expected {c.get('expected')})")
            elif c.get("status") == "WARN":
                result.warnings.append(f"{c.get('check')}: {c.get('value')} (expected {c.get('expected')})")

        # 2. Exact contract probe
        if exact_contract:
            try:
                probe = self.probe(path)
            except MediaProbeError as e:
                raise MediaVerifyError(f"verify probe failed on {path}: {e}") from e
            result.probe = probe
            v = probe.get("video") or {}
            a = probe.get("audio") or {}
            dur = probe.get("duration") or 0.0

            if v.get("width") != self.CONTRACT_WIDTH:
                result.errors.append(f"width: {v.get('width')} != {self.CONTRACT_WIDTH}")
            if v.get("height") != self.CONTRACT_HEIGHT:
                result.errors.append(f"height: {v.get('height')} != {self.CONTRACT_HEIGHT}")
            fps = v.get("fps") or 0
            if fps and abs(fps - self.CONTRACT_FPS) > 1.0:
                result.warnings.append(f"fps: {fps:.1f} != {self.CONTRACT_FPS}")
            if dur < self.CONTRACT_MIN_DURATION:
                result.errors.append(f"duration: {dur:.1f}s < {self.CONTRACT_MIN_DURATION}s")
            elif dur > self.CONTRACT_MAX_DURATION:
                result.errors.append(f"duration: {dur:.1f}s > {self.CONTRACT_MAX_DURATION}s")
            if v.get("codec") and v["codec"] != self.CONTRACT_VIDEO_CODEC:
                result.errors.append(f"video codec: {v.get('codec')} != {self.CONTRACT_VIDEO_CODEC}")
            if a.get("codec") and a["codec"] != self.CONTRACT_AUDIO_CODEC:
                result.errors.append(f"audio codec: {a.get('codec')} != {self.CONTRACT_AUDIO_CODEC}")
            if not a:
                result.errors.append("no audio stream")

        result.valid = not result.errors
        logger.info(
            f"Media verification: valid={result.valid}, "
            f"{len(result.errors)} errors, {len(result.warnings)} warnings"
        )
        return result

    # ------------------------------------------------------------------
    # CONTACT SHEET (visual QA, not used for production gating)
    # ------------------------------------------------------------------
    def contact_sheet(
        self,
        media_path: Path | str,
        output_path: Path | str,
        *,
        cols: int = 3,
        rows: int = 3,
    ) -> Path:
        """Generate a contact sheet PNG for visual QA.

        Uses the vendored look.py script. Intended for development/QA
        review only; not used as a production gate.

        Returns:
            Path to the generated contact sheet.
        """
        script = self.scripts_dir / "look.py"
        if not script.exists():
            raise MediaServiceError("look.py not present in vendored scripts")
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        cmd = [
            self.python, str(script), str(Path(media_path)),
            "-o", str(out), "--tiles", f"{cols}x{rows}",
        ]
        subprocess.run(cmd, capture_output=True, text=True, timeout=120, check=False)
        if not out.exists():
            raise MediaServiceError(f"contact sheet not produced: {out}")
        return out

    # ------------------------------------------------------------------
    # CAPTION (optional subtitle burn helper)
    # ------------------------------------------------------------------
    def caption(self, media_path: Path | str, srt_path: Path | str, output_path: Path | str) -> Path:
        """Burn an SRT into a video using the vendored caption.py.

        Convenience wrapper; the main pipeline burns subtitles during render
        via VideoRenderer. This is available for standalone caption jobs.
        """
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        self._run_script(
            "caption",
            [str(Path(media_path)), "--srt", str(Path(srt_path)), "-o", str(out), "--json"],
        )
        return out


def create_media_service(
    scripts_dir: Path | str | None = None,
    renderer: VideoRenderer | None = None,
) -> MediaService:
    """Factory to create a MediaService."""
    return MediaService(scripts_dir=scripts_dir, renderer=renderer)
#!/usr/bin/env python3
"""Gospel test pipeline — Kokoro male TTS + subtle reverb + black video + burned subtitles.

Usage (from repo root, with the venv active):

    python scripts/test_gospel.py [--text "...scripture..."] \
        [--output output/gospel_test.mp4] [--voice am_fenrir] [--speed 0.85]

If --text is omitted a default Gospel passage (John 1:1-5) is used so the
script is a zero-friction smoke test. Produces a real 1080x1920 H.264/AAC MP4
with reverb-processed audio and burned-in, speech-aligned subtitles.

Pipeline:
    scripture text
      -> Kokoro (am_fenrir) speech-aligned TTS
      -> reverb (FFmpeg aecho)
      -> black 1080x1920 video
      + segment-synced SRT burned in
      -> final MP4
"""
from __future__ import annotations

import argparse
import json
import logging
import subprocess
import sys
from pathlib import Path

# Add project root to path for imports when run from repo root.
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except ImportError:
    pass

from src.ai.kokoro_provider import create_kokoro_provider
from src.ai.tts_provider import create_tts_provider
from src.config import settings
from src.video.ffmpeg import FFmpegError, VideoRenderer
from src.video.subtitles import SubtitleGenerator

DEFAULT_TEXT = (
    "In the beginning was the Word, and the Word was with God. "
    "And the Word was God. In him was life, and the life was the light of men. "
    "The light shines in the darkness, and the darkness has not overcome it."
)


def build_aligned_srt(
    sync_segments, output_srt: Path, subtitle_gen: SubtitleGenerator,
) -> Path:
    """Write an SRT whose timing follows Kokoro's speech alignment."""
    entries = subtitle_gen.from_synced_segments(sync_segments)
    output_srt.write_text(
        "\n".join(e.to_srt() for e in entries), encoding="utf-8"
    )
    return output_srt


def _probe_duration_ffprobe(wav_path: Path) -> float | None:
    """Return the WAV duration (s) via ffprobe, or None if it fails."""
    try:
        proc = subprocess.run(
            [
                "ffprobe", "-v", "error", "-show_entries", "format=duration",
                "-of", "json", str(wav_path),
            ],
            capture_output=True, text=True, timeout=30,
        )
        data = json.loads(proc.stdout)
        return float(data.get("format", {}).get("duration", 0.0))
    except Exception:
        return None


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--text", default=DEFAULT_TEXT, help="Scripture text to narrate")
    ap.add_argument("--voice", default=None, help="Kokoro voice override")
    ap.add_argument("--speed", type=float, default=None, help="Kokoro speed override")
    ap.add_argument("--no-reverb", action="store_true", help="Skip reverb")
    ap.add_argument("--output", default=str(ROOT / "output" / "gospel_test.mp4"))
    args = ap.parse_args()

    output_path = Path(args.output)
    output_dir = output_path.parent
    output_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("Gospel Test Pipeline")
    print("=" * 60)
    print(f"Voice       : {args.voice or settings.kokoro_voice or 'am_fenrir'}")
    print(f"Speed       : {args.speed or settings.kokoro_speed or 0.85}")
    print(f"Reverb      : {'OFF' if args.no_reverb else 'ON'}")
    print(f"Output      : {output_path}")
    print()

    # ---- Step 1: Kokoro speech-aligned TTS ----
    try:
        # Prefer the Kokoro provider directly for aligned timing, regardless
        # of the configured default provider (Gemini fallback has no alignment).
        provider = create_kokoro_provider(
            voice=args.voice or settings.kokoro_voice or None,
            speed=args.speed or settings.kokoro_speed or 1.0,
        )
    except Exception:
        # Fall back to the configured provider if Kokoro init fails.
        provider = create_tts_provider()

    narration_path = output_dir / "gospel_narration.wav"
    sync_segments = None

    if hasattr(provider, "synthesize_aligned"):
        try:
            wav_bytes, sync_segments = provider.synthesize_aligned(args.text)
            narration_path.write_bytes(wav_bytes)
            print(
                f"[1/4] Kokoro TTS ok: {narration_path} "
                f"({len(sync_segments)} synced segments)"
            )
        except Exception as e:
            print(f"  ✗ aligned TTS failed ({e}); using plain TTS path")
            sync_segments = None

    if sync_segments is None:
        provider.synthesize_to_file(args.text, narration_path)
        print(f"[1/4] Kokoro TTS ok (plain): {narration_path}")

    # ---- Step 2: speech-aligned SRT ----
    subtitle_path = output_dir / "gospel_subtitles.srt"
    gen = SubtitleGenerator()
    if sync_segments:
        build_aligned_srt(sync_segments, subtitle_path, gen)
        print(f"[2/4] Segment-aligned subtitles: {subtitle_path}")
    else:
        # No alignment available -> fall back to WPM-based timing scaled to
        # the real audio duration via ffprobe.
        dur = _probe_duration_ffprobe(narration_path)
        gen.save_srt(args.text, subtitle_path, total_duration=dur)
        print(f"[2/4] Subtitles (WPM + ffprobe timing fallback): {subtitle_path}")

    # ---- Step 3: black video + reverb + burned subs ----
    renderer = VideoRenderer(enable_subtitles=settings.enable_subtitles)
    try:
        renderer.render_black_video(
            narration_wav=narration_path,
            subtitle_srt=subtitle_path,
            output_path=output_path,
            reverb=not args.no_reverb,
            reverb_delay_ms=settings.reverb_delay if settings.reverb_enabled else None,
            reverb_decay=settings.reverb_decay,
            reverb_wet=settings.reverb_wet,
            sync_segments=sync_segments,
        )
        print(f"[3/4] Video rendered: {output_path}")
    except FFmpegError as e:
        print(f"  ✗ render failed: {e}")
        return 1
    except Exception as e:
        print(f"  ✗ render error: {e}")
        return 1

    # ---- Step 4: validate ----
    try:
        validation = renderer.validate_video(output_path)
        ok = validation.get("valid")
        print(f"[4/4] Validation: {'PASS' if ok else 'FAIL'}")
        for k, v in validation.items():
            if k in ("valid", "errors", "warnings"):
                if k == "warnings" and v:
                    print(f"      warnings: {v}")
                continue
            print(f"      {k}: {v}")
        if not ok:
            print(f"      errors: {validation.get('errors')}")
            return 1
    except Exception as e:
        print(f"  ✗ validation error: {e}")
        return 1

    print()
    print("Gospel test complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
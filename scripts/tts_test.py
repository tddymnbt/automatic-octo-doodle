"""Deterministic Kokoro TTS functional test.

Proves the full Kokoro path works end-to-end locally:

    1. Builds a KokoroTTSProvider via the config-driven factory
    2. Synthesizes a short fixed narration + calm ASMR instruction
    3. Validates the result with the hard audio gate
    4. Confirms FFmpeg can decode it

This uses a SHORT narration (a few seconds), so it exercises the real
provider without burning a full 45s render or any Gemini quota.

Usage:
    python scripts/tts_test.py [--voice af_heart]

Exit code 0 = success, non-zero = failure.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Add project root to path for imports
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


# A short, deterministic, calm narration used for the smoke test.
TEST_NARRATION = (
    "The old clockmaker wound the key one last time, "
    "and the silence of midnight seemed to listen."
)
ASMR_INSTRUCTION = (
    "Calm, intimate, soft nighttime storytelling. Slow, gentle pacing. "
    "Warm and slightly mysterious. Whispers-style narration for ASMR."
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Kokoro TTS smoke test")
    parser.add_argument("--voice", default=None, help="Kokoro voice (default: af_heart)")
    parser.add_argument("--out", default="/tmp/kokoro_tts_test.wav", help="Output WAV path")
    args = parser.parse_args()

    print("=" * 60)
    print("Kokoro TTS Functional Test")
    print("=" * 60)

    # 1. Build provider via factory
    try:
        from src.ai.tts_provider import create_tts_provider
        tts = create_tts_provider(provider="kokoro", voice=args.voice)
        print(f"Provider: {tts.voice_label()}")
    except Exception as e:
        print(f"✗ Failed to create Kokoro provider: {e}")
        return 1

    # 2. Synthesize
    wav_path = Path(args.out)
    try:
        tts.synthesize_to_file(TEST_NARRATION, wav_path, voice_instruction=ASMR_INSTRUCTION)
        size = wav_path.stat().st_size
        print(f"✓ Synthesized: {wav_path} ({size} bytes)")
    except Exception as e:
        print(f"✗ Synthesis failed: {e}")
        return 1

    # 3. Validate with hard audio gate
    try:
        from src.audio.validator import validate_audio
        validation = validate_audio(
            wav_path,
            min_duration=0.5,  # smoke test is short, only reject pathological
            max_duration=60.0,
        )
        if not validation.is_valid:
            print("✗ Audio validation failed:")
            for err in validation.errors:
                print(f"   - {err}")
            return 1
        print(f"✓ Audio valid: duration={validation.info.get('duration', 0):.1f}s, "
              f"RMS={validation.info.get('rms', 0):.4f}")
    except Exception as e:
        print(f"✗ Audio validation error: {e}")
        return 1

    # 4. Confirm FFmpeg can decode
    import subprocess
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "a:0",
         "-show_entries", "stream=codec_name,sample_rate,channels",
         "-of", "csv=p=0", str(wav_path)],
        capture_output=True, text=True, timeout=30, check=False,
    )
    if result.returncode != 0:
        print(f"✗ FFmpeg could not decode: {result.stderr.strip()}")
        return 1
    print(f"✓ FFmpeg decodes: {result.stdout.strip()}")

    print()
    print("=" * 60)
    print("Kokoro TTS test PASSED")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
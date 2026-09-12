"""Daily Gospel / Daily Bread Shorts — Main entry point.

This module orchestrates the complete pipeline:
1. Validate environment
2. Generate Gospel content (situation → Scripture → reflection → CTA)
3. Generate Kokoro male narration with speech-aligned segment timing
4. Validate audio (hard gate)
5. Generate speech-accurate subtitles (from Kokoro's aligned segments)
6. Render black 1080x1920 video with burned-in subtitles + subtle reverb
7. Verify media (ffmpeg-skill platform compliance + exact contract)
8. Publish to Facebook Reels + post first comment + pin comment

Source of truth: one generated GospelContent flows into narration, subtitles,
caption, first comment, and pinned comment — no component invents its own
message.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

# Add project root to path for imports
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Load .env file if present
try:
    from dotenv import load_dotenv
    load_dotenv(project_root / ".env")
except ImportError:
    pass

from src.config import settings

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

TOTAL_PHASES = 8


def _record_history(
    history,
    **kwargs,
) -> None:
    """Record a history entry, never letting history failures block the pipeline."""
    if history is None:
        return
    try:
        history.record(**kwargs)
    except Exception as e:
        logger.warning(f"History recording failed (non-fatal): {e}")


def _synced_segments_for(tts, text: str) -> tuple[list, Path]:
    """Generate narration and return (segments, wav_path).

    Prefers the speech-aligned path (Kokoro ``synthesize_aligned``) so
    subtitles follow the actual narration timing. Falls back to plain
    synthesis + a WAV written via ``synthesize_to_file`` and empty segments
    (subtitle timing then falls back to WPM estimates).
    """
    from src.ai.kokoro_provider import KokoroTTSProvider

    if isinstance(tts, KokoroTTSProvider):
        wav_bytes, segments = tts.synthesize_aligned(text)
        wav_path = Path("output") / "narration.wav"
        wav_path.parent.mkdir(parents=True, exist_ok=True)
        wav_path.write_bytes(wav_bytes)
        return segments, wav_path

    # Fallback provider (e.g. Gemini): write via the protocol method.
    wav_path = tts.synthesize_to_file(text, Path("output") / "narration.wav")
    return [], wav_path


def main() -> int:
    """Run the Daily Gospel Shorts pipeline."""
    print("=" * 60)
    print("Daily Gospel / Daily Bread Shorts Pipeline")
    print("=" * 60)
    print(f"Mode: {'DRY RUN' if settings.dry_run else 'LIVE'}")
    print(f"Model: {settings.ai_model}")
    print(f"TTS Provider: {settings.tts_provider} (voice: {settings.kokoro_voice})")
    print(f"Target Duration: {settings.target_duration_seconds}s")
    print()

    # Validate environment first
    missing_secrets = settings.validate_secrets()
    if missing_secrets:
        logger.error(f"Missing secrets: {', '.join(missing_secrets)}")
        print("ERROR: Missing required secrets. Run validate_environment.py")
        return 1
    config_issues = settings.validate_config()
    if config_issues:
        logger.error(f"Configuration issues: {', '.join(config_issues)}")
        print(f"ERROR: {', '.join(config_issues)}")
        return 1

    # Phase 1: Validate environment
    print(f"[1/{TOTAL_PHASES}] Validating environment...")
    print("  ✓ Environment validated")

    # Phase 2: Generate Gospel content
    print(f"[2/{TOTAL_PHASES}] Generating Gospel content...")
    try:
        from src.ai.story_generator import GospelGenerator

        generator = GospelGenerator()
        result = generator.generate()

        if not result.success:
            logger.error(f"Gospel content generation failed: {result.error}")
            print(f"  ✗ Gospel content generation failed: {result.error}")
            return 1

        content = result.content
        print(f"  ✓ Content generated: '{content.hook[:60]}...'")
        print(f"    Scripture: {content.scripture_reference}")
        print(f"    Duration estimate: ~{content.estimate_duration_seconds():.0f}s")

    except Exception as e:
        logger.error(f"Gospel content generation error: {e}")
        print(f"  ✗ Gospel content generation error: {e}")
        return 1

    # Phase 2b: Duplicate detection (idempotency gate)
    history = None
    try:
        from src.history.store import STATUS_DUPLICATE, HistoryStore

        history = HistoryStore()
        if history.was_published(content.content_hash):
            print(f"  ⚠ Duplicate content detected (already published): '{content.hook[:60]}'")
            print("    Skipping pipeline to avoid duplicate Reel.")
            history.record(
                story_hash=content.content_hash,
                situation_summary=content.situation_summary,
                scripture_reference=content.scripture_reference,
                status=STATUS_DUPLICATE,
                slot=settings.slot,
                dry_run=settings.dry_run,
                attempts=result.attempts,
            )
            return 0
        print(f"  ✓ No duplicate detected (hash={content.content_hash})")
    except Exception as e:
        logger.warning(f"Duplicate check skipped: {e}")

    # Duplicate's content_hash must be set even if generation resets it.
    content_hash = content.content_hash

    # Phase 3: Generate narration (Kokoro) + speech-aligned timing
    print(f"[3/{TOTAL_PHASES}] Generating narration...")
    segments = []
    audio_path: Path | None = None
    try:
        from src.ai.tts_provider import TTSAuthError, create_tts_provider

        tts = create_tts_provider()
        segments, audio_path = _synced_segments_for(tts, content.narration_script)
        print(f"  ✓ Narration generated: {audio_path}")
        print(f"    Speech-aligned segments: {len(segments)}")
    except TTSAuthError as e:
        logger.error(f"TTS authentication failed: {e}")
        print("  ✗ TTS authentication failed — check TTS credentials/config")
        return 1
    except Exception as e:
        logger.error(f"TTS generation error: {e}")
        print(f"  ✗ TTS generation error: {e}")
        return 1

    # Phase 4: Validate audio (hard gate — no video from unusable audio)
    print(f"[4/{TOTAL_PHASES}] Validating audio...")
    actual_audio_duration = content.estimate_duration_seconds()
    try:
        from src.audio.validator import validate_audio

        validation = validate_audio(
            audio_path,
            min_duration=settings.min_duration_seconds - 5.0,
            max_duration=settings.max_duration_seconds + 5.0,
        )
        if not validation.is_valid:
            for err in validation.errors:
                logger.error(f"Audio validation failed: {err}")
                print(f"  ✗ {err}")
            return 1
        actual_audio_duration = validation.info.get("duration", actual_audio_duration)
        print(f"  ✓ Audio valid: duration={actual_audio_duration:.1f}s, "
              f"RMS={validation.info.get('rms', 0):.4f}")
    except Exception as e:
        logger.error(f"Audio validation error: {e}")
        print(f"  ✗ Audio validation error: {e}")
        return 1

    # Phase 5: Generate subtitles
    print(f"[5/{TOTAL_PHASES}] Generating subtitles...")
    subtitle_path: Path | None = None
    try:
        from src.video.subtitles import SubtitleGenerator

        subtitle_gen = SubtitleGenerator()
        subtitle_path = Path("output") / "subtitles.srt"
        if segments:
            # Speech-accurate: subtitles follow the aligned segment timing.
            subtitle_gen.save_srt(
                content.narration_script, subtitle_path,
            )  # placeholder overwritten below
            srt_text = subtitle_gen.srt_from_synced_segments(segments)
            subtitle_path.write_text(srt_text, encoding="utf-8")
            print(f"  ✓ Subtitles generated (speech-aligned): {subtitle_path} "
                  f"({len(segments)} segments)")
        else:
            # Fallback: WPM-based timing using the actual audio duration.
            subtitle_gen.save_srt(
                content.narration_script, subtitle_path,
                total_duration=actual_audio_duration,
            )
            print(f"  ✓ Subtitles generated (duration-fitted): {subtitle_path}")
    except Exception as e:
        logger.error(f"Subtitle generation error: {e}")
        print(f"  ✗ Subtitle generation error: {e}")
        return 1

    # Phase 6: Render video (background/black + burned-in subtitles + reverb
    # + optional ambient)
    print(f"[6/{TOTAL_PHASES}] Rendering video...")
    video_path = Path("output") / "final.mp4"
    try:
        from src.video.ffmpeg import VideoRenderer

        renderer = VideoRenderer(enable_subtitles=settings.enable_subtitles)

        # Select a Gospel background (image/webp) and an ambient track when
        # enabled. Both degrade gracefully to black / narration-only.
        background_asset = None
        ambient_asset = None
        from src.assets.selector import AssetSelector

        selector = AssetSelector(assets_dir=settings.background_dir, ambient_dir=settings.ambient_dir)
        if settings.enable_background:
            background_asset = selector.select_background(prefer_gospel=True)
        if settings.enable_ambient_audio:
            ambient_asset = selector.select_ambient()

        renderer.render_black_video(
            narration_wav=audio_path,
            subtitle_srt=subtitle_path,
            output_path=video_path,
            reverb=settings.reverb_enabled,
            reverb_delay_ms=settings.reverb_delay,
            reverb_decay=settings.reverb_decay,
            reverb_wet=settings.reverb_wet,
            sync_segments=segments or None,
            background_path=background_asset.path if background_asset else None,
            ambient_wav=ambient_asset.path if ambient_asset else None,
            ambient_level=settings.ambient_level,
            ambient_fade_in=settings.ambient_fade_in,
            ambient_fade_out=settings.ambient_fade_out,
            ambient_duck=settings.ambient_duck,
        )
        bg_note = f", background={'YES' if background_asset else 'black'}, ambient={'YES' if ambient_asset else 'no'}"
        print(f"  ✓ Video rendered ({bg_note.strip()})\n    {video_path}")
    except Exception as e:
        logger.error(f"Video rendering error: {e}")
        print(f"  ✗ Video rendering error: {e}")
        return 1

    # Phase 6b: Verify media (ffmpeg-skill platform compliance + exact contract)
    print(f"[6b/{TOTAL_PHASES}] Verifying media...")
    try:
        from src.video.media_service import MediaService

        media = MediaService(renderer=renderer)
        verification = media.verify(video_path, platform="reels")
        if not verification.valid:
            for err in verification.errors:
                logger.error(f"Media verification error: {err}")
                print(f"  ✗ {err}")
            return 1
        for warn in verification.warnings:
            logger.warning(f"Media verification warning: {warn}")
            print(f"  ⚠ {warn}")
        print(
            f"  ✓ Video verified: 1080x1920 @30fps, "
            f"{verification.probe.get('duration', 0):.1f}s, valid MP4"
        )
    except Exception as e:
        logger.error(f"Media verification error: {e}")
        print(f"  ✗ Media verification error: {e}")
        return 1

    # Phase 7: Publish Reel via Facebook Graph API
    print(f"[7/{TOTAL_PHASES}] Publishing to Facebook...")
    post_id = ""
    try:
        from src.facebook.reels import FacebookPublishError, ReelsPublisher

        publisher = ReelsPublisher()
        result = publisher.publish(
            video_path=video_path,
            story=content,
            title=content.hook[:100],
        )
        if result.dry_run:
            print(f"  ✓ {result.message}")
            _record_history(
                history,
                story_hash=content_hash,
                situation_summary=content.situation_summary,
                scripture_reference=content.scripture_reference,
                status="dry_run",
                dry_run=True,
                video_path=str(video_path),
                duration_s=actual_audio_duration,
                attempts=result.attempts,
                tts_provider=settings.tts_provider,
                slot=settings.slot,
            )
        elif result.published:
            post_id = result.post_id
            print(
                f"  ✓ Reel published: post_id={post_id} "
                f"(video_id={result.video_id})"
            )
            logger.info(f"Reel published: post_id={post_id}")
            _record_history(
                history,
                story_hash=content_hash,
                situation_summary=content.situation_summary,
                scripture_reference=content.scripture_reference,
                status="published",
                dry_run=False,
                video_path=str(video_path),
                post_id=post_id,
                video_id=result.video_id,
                duration_s=actual_audio_duration,
                attempts=result.attempts,
                tts_provider=settings.tts_provider,
                slot=settings.slot,
            )
        else:
            logger.error(
                f"Reels publish returned unsuccessful result: {result.to_dict()}"
            )
            print("  ✗ Reels publish failed (see logs)")
            return 1
    except FacebookPublishError as e:
        logger.error(f"Facebook publish error: {e}")
        print(f"  ✗ Facebook publish error: {e}")
        _record_history(
            history,
            story_hash=content_hash,
            situation_summary=content.situation_summary,
            scripture_reference=content.scripture_reference,
            status="failed",
            dry_run=settings.dry_run,
            error=str(e),
            slot=settings.slot,
        )
        return 1
    except Exception as e:
        logger.error(f"Facebook publish error: {e}")
        print(f"  ✗ Facebook publish error: {e}")
        return 1

    # Phase 8: Post first comment + pin comment (only on live publish)
    print(f"[8/{TOTAL_PHASES}] Posting comments...")
    if not post_id:
        print("  - DRY RUN: skipped comment posting")
        return 0

    try:
        from src.facebook.reels import FacebookPublishError, ReelsPublisher

        publisher = ReelsPublisher()
        posted = publisher.publish_comments(
            post_id=post_id,
            first_comment=content.first_comment,
            pinned_comment=content.pinned_comment,
        )
        print(f"  ✓ First comment posted: id={posted['first_comment_id'] or 'n/a'}")
        print(f"  ✓ Pinned comment posted: id={posted['pinned_comment_id'] or 'n/a'}")
        if posted.get("pinned"):
            print("  ✓ Pinned comment pinned")
        else:
            print("  ⚠ Pin failed (may need pages_manage_engagement permission)")
    except FacebookPublishError as e:
        logger.warning(f"Comment posting failed (non-fatal): {e}")
        print(f"  ⚠ Comment posting failed: {e}")

    print()
    print("=" * 60)
    print("Pipeline complete!")
    print("=" * 60)

    return 0


if __name__ == "__main__":
    sys.exit(main())
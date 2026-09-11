"""ASMR Story Shorts - Main entry point.

This module orchestrates the complete pipeline:
1. Validate environment
2. Generate story
3. Generate TTS narration
4. Validate audio (hard gate)
5. Select visual assets
6. Generate subtitles
7. Render video with FFmpeg
8. Publish to Facebook Reels
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
    """Record a history entry, never letting history failures block the pipeline.

    ``history`` may be None (history init failed earlier) — in that case this
    is a no-op.
    """
    if history is None:
        return
    try:
        history.record(**kwargs)
    except Exception as e:
        logger.warning(f"History recording failed (non-fatal): {e}")


def main() -> int:
    """Run the ASMR Story Shorts pipeline."""
    print("=" * 60)
    print("ASMR Story Shorts Pipeline")
    print("=" * 60)
    print(f"Mode: {'DRY RUN' if settings.dry_run else 'LIVE'}")
    print(f"Model: {settings.ai_model}")
    print(f"TTS Provider: {settings.tts_provider}")
    print(f"Target Duration: {settings.target_duration_seconds}s")
    print()

    # Validate environment first
    missing_secrets = settings.validate_secrets()
    if missing_secrets:
        logger.error(f"Missing secrets: {', '.join(missing_secrets)}")
        print("ERROR: Missing required secrets. Run validate_environment.py")
        return 1

    # Phase 1: Validate environment
    print(f"[1/{TOTAL_PHASES}] Validating environment...")
    print("  ✓ Environment validated")

    # Phase 2: Generate story
    print(f"[2/{TOTAL_PHASES}] Generating story...")
    try:
        from src.ai.story_generator import StoryGenerator

        generator = StoryGenerator()
        result = generator.generate()

        if not result.success:
            logger.error(f"Story generation failed: {result.error}")
            print(f"  ✗ Story generation failed: {result.error}")
            return 1

        story = result.story
        print(f"  ✓ Story generated: '{story.title}'")
        print(f"    Scenes: {len(story.scenes)}")
        print(f"    Duration estimate: ~{story.estimate_duration_seconds():.0f}s")

    except Exception as e:
        logger.error(f"Story generation error: {e}")
        print(f"  ✗ Story generation error: {e}")
        return 1

    # Phase 2b: Duplicate detection (idempotency gate)
    # If this story's content hash was already published live in a previous
    # run, skip the entire pipeline to avoid duplicate Reels. History failures
    # must never block the pipeline (log and continue with history=None).
    history = None
    try:
        from src.history.store import STATUS_DUPLICATE, HistoryStore

        history = HistoryStore()
        if history.was_published(story.content_hash):
            print(f"  ⚠ Duplicate story detected (already published): '{story.title}'")
            print("    Skipping pipeline to avoid duplicate Reel.")
            history.record(
                story_hash=story.content_hash,
                story_title=story.title,
                status=STATUS_DUPLICATE,
                dry_run=settings.dry_run,
                attempts=result.attempts,
            )
            return 0
        print(f"  ✓ No duplicate detected (hash={story.content_hash})")
    except Exception as e:
        logger.warning(f"Duplicate check skipped: {e}")

    # Phase 3: Generate TTS
    print(f"[3/{TOTAL_PHASES}] Generating narration...")
    try:
        from src.ai.tts_provider import TTSAuthError, create_tts_provider

        tts = create_tts_provider()
        audio_path = Path("output") / "narration.wav"
        tts.synthesize_to_file(story.narration, audio_path)
        print(f"  ✓ Narration generated: {audio_path}")

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
    actual_audio_duration: float = story.estimate_duration_seconds()
    try:
        from src.audio.validator import validate_audio

        validation = validate_audio(
            audio_path,
            min_duration=settings.min_duration_seconds - 5.0,  # allow some slack
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

    # Phase 4b: Align scene durations to actual audio length
    # The AI estimates durations from word count (150 WPM), but the TTS
    # provider renders at its own pace. Scale scenes proportionally so the
    # visual track matches the narration, preventing -shortest truncation.
    estimated_duration = story.estimate_duration_seconds()
    if estimated_duration > 0 and actual_audio_duration > 0:
        scale = actual_audio_duration / estimated_duration
        for scene in story.scenes:
            scene.duration_seconds = round(scene.duration_seconds * scale, 2)
        logger.info(
            f"Scene durations scaled {estimated_duration:.1f}s → "
            f"{actual_audio_duration:.1f}s (factor {scale:.3f})"
        )

    # Phase 5: Select visuals
    print(f"[5/{TOTAL_PHASES}] Selecting visual assets...")
    selected_assets: list = []
    try:
        from src.assets.selector import AssetSelector

        selector = AssetSelector()
        scenes = [{"category": s.category, "description": s.description} for s in story.scenes]
        selection = selector.select_assets_for_scenes(scenes)
        selected_assets = selection.assets

        if selection.has_assets:
            print(f"  ✓ Selected {selection.selected_count} assets")
            print(f"    Categories: {[c.value for c in selection.categories_used]}")
        else:
            print("  ⚠ No matching assets found (will use placeholders)")

    except Exception as e:
        logger.error(f"Asset selection error: {e}")
        print(f"  ⚠ Asset selection skipped: {e}")

    # Phase 6: Generate subtitles
    print(f"[6/{TOTAL_PHASES}] Generating subtitles...")
    try:
        from src.video.subtitles import SubtitleGenerator

        subtitle_gen = SubtitleGenerator()
        subtitle_path = Path("output") / "subtitles.srt"
        subtitle_gen.save_srt(story.narration, subtitle_path, total_duration=actual_audio_duration)
        print(f"  ✓ Subtitles generated: {subtitle_path}")

    except Exception as e:
        logger.error(f"Subtitle generation error: {e}")
        print(f"  ✗ Subtitle generation error: {e}")
        return 1

    # Phase 6b: Select ambient audio (matching story categories)
    ambient_audio_path: Path | None = None
    if settings.enable_ambient_audio:
        print(f"[6b/{TOTAL_PHASES}] Selecting ambient audio...")
        try:
            from src.assets.ambient import AmbientSelector

            selector = AmbientSelector()
            ambient_selection = None
            if story is None:
                logger.error("Story not available for ambient selection")
                print("  ⚠ Story not available for ambient selection")
            else:
                ambient_selection = selector.select_ambient([s.category for s in story.scenes])
            ambient_path = ambient_selection.path if ambient_selection else None
            if ambient_path is not None:
                ambient_audio_path = ambient_path
                graded = ambient_selection.graded if ambient_selection else "none"
                print(
                    f"  ✓ Ambient selected: {ambient_path.name} "
                    f"(match: {graded})"
                )
            else:
                print(f"  ⚠ No ambient audio found in {selector._dir}")
        except Exception as e:
            logger.error(f"Ambient selection error: {e}")
            print(f"  ⚠ Ambient selection skipped: {e}")

    # Phase 7: Render video via MediaService (composition + verification layer)
    print(f"[7/{TOTAL_PHASES}] Rendering video...")
    try:
        from src.video.ffmpeg import VideoRenderer
        from src.video.media_service import MediaService

        media = MediaService(renderer=VideoRenderer(enable_subtitles=settings.enable_subtitles))
        video_path = Path("output") / "final.mp4"

        # PROBE inputs (deterministic media facts before render)
        narration_probe = media.probe(audio_path)
        logger.info(
            f"Narration probe: {narration_probe.get('audio', {}).get('codec')} "
            f"@{narration_probe.get('audio', {}).get('sample_rate')}Hz, "
            f"{narration_probe.get('duration', 0):.1f}s"
        )

        media.render(
            story=story,
            assets=selected_assets,
            narration_audio=audio_path,
            subtitle_file=subtitle_path,
            output_path=video_path,
            ambient_audio=ambient_audio_path,
        )
        print(f"  ✓ Video rendered: {video_path}")

        # CHECK + VERIFY (ffmpeg-skill platform compliance + exact contract)
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
        logger.error(f"Video rendering error: {e}")
        print(f"  ✗ Video rendering error: {e}")
        return 1

    # Phase 8: Publish Reel via Facebook Graph API
    print(f"[8/{TOTAL_PHASES}] Publishing to Facebook...")
    try:
        from src.facebook.reels import FacebookPublishError, ReelsPublisher

        publisher = ReelsPublisher()
        result = publisher.publish(
            video_path=video_path,
            story=story,
            title=story.title,
        )
        if result.dry_run:
            print(f"  ✓ {result.message}")
            _record_history(
                history,
                story_hash=story.content_hash,
                story_title=story.title,
                status="dry_run",
                dry_run=True,
                video_path=str(video_path),
                attempts=result.attempts,
                tts_provider=settings.tts_provider,
            )
        elif result.published:
            print(
                f"  ✓ Reel published: post_id={result.post_id} "
                f"(video_id={result.video_id})"
            )
            logger.info(f"Reel published: post_id={result.post_id}")
            _record_history(
                history,
                story_hash=story.content_hash,
                story_title=story.title,
                status="published",
                dry_run=False,
                video_path=str(video_path),
                post_id=result.post_id,
                video_id=result.video_id,
                attempts=result.attempts,
                tts_provider=settings.tts_provider,
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
            story_hash=story.content_hash,
            story_title=story.title,
            status="failed",
            dry_run=settings.dry_run,
            error=str(e),
        )
        return 1
    except Exception as e:
        logger.error(f"Facebook publish error: {e}")
        print(f"  ✗ Facebook publish error: {e}")
        return 1

    print()
    print("=" * 60)
    print("Pipeline complete!")
    print("=" * 60)

    return 0


if __name__ == "__main__":
    sys.exit(main())

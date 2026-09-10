# ffmpeg-skill (vendored media scripts)

**Version:** 0.12.5
**License:** MIT (see LICENSE in this directory)
**Source:** https://github.com/kajisho5/ffmpeg-skill

## What are these scripts?

Standalone Python CLI tools from [kajisho5/ffmpeg-skill](https://github.com/kajisho5/ffmpeg-skill) that provide deterministic media operations: probe → edit → check → verify.

These are vendored (committed directly) so the pipeline has **no runtime Node/npm dependency** and works entirely offline with only FFmpeg/ffprobe on PATH.

## Scripts used by this project

| Script | Purpose in pipeline |
|---|---|
| `probe.py` | Structured media facts (duration, fps, resolution, codecs, pixel format, VFR, HDR) |
| `check.py` | Platform compliance check (`--platform reels`: 9:16, ≥1080 height, h264/hevc, yuv420p, loudness) |
| `caption.py` | Burn SRT/ASS subtitles into video (optional: animated/karaoke) |

## How to invoke

```bash
python3 media/scripts/probe.py output/final.mp4 --json
python3 media/scripts/check.py output/final.mp4 --platform reels --json
python3 media/scripts/caption.py input.mp4 --srt subs.srt --json
```

## Requirements

- FFmpeg/ffprobe on PATH
- Python 3.9+ (stdlib only — no extra packages)
- The `subtitles` filter requires a libass-enabled FFmpeg build (GitHub Actions runner has this; local Homebrew may not)

## Updating

To update to a newer ffmpeg-skill release, manually replace the files in `media/scripts/` from the new npm package release and update the version line above.

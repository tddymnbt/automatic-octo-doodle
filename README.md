# ASMR Story Shorts (Daily Bread Pivot)

Automated pipeline for creating and publishing **Gospel / Daily Bread encouragement videos** to Facebook Reels.

## Overview

This project generates original short Gospel encouragement videos (30–60 seconds) and publishes them to Facebook Reels automatically using:

- **Gemini AI** for content generation (story, Scripture, reflection, caption, comments)
- **Kokoro** (local, offline, free) for TTS narration — Gemini TTS optional fallback
- **FFmpeg** for video rendering with Ken Burns background motion
- **Meta Graph API** for Facebook publishing
- **GitHub Actions** for automation

The pipeline is **theme-driven**, not problem-driven: it rotates across **7 content archetypes**, **20 spiritual principles**, and **multiple structural patterns** so every post feels fresh without relying on a fixed taxonomy of human struggles.

## Cost

Designed to run at **$0** using:

- Free Gemini API tier (story generation only)
- Kokoro open-weight TTS (offline, no API key)
- GitHub Actions (2,000 minutes/month free)
- FFmpeg (open source)
- Facebook Page API (free)

## Architecture

```
cron-job.org → GitHub Actions → Pipeline → Facebook Page
Pipeline:
  1. Diversity Engine selects archetype + principle + patterns
     (slot-stratified LSUR rotation with history awareness)
  2. Gemini 3.5 Flash-Lite → GospelContent (JSON, all fields)
  3. Kokoro TTS (am_fenrir/am_onyx by slot) → aligned narration WAV
  4. Audio validation gate (hard)
  5. Asset Selector → background (round-robin from 21 gospel WebP) + ambient (round-robin from 6 piano WAV)
  6. Subtitle Generator → speech-aligned ASS (middle-centered)
  7. MediaService + FFmpeg → 1080×1920 H.264/AAC MP4 (Ken Burns zoompan)
  8. MediaService verify → ffmpeg-skill Reels compliance
  9. Meta Graph API → Publish Reel + first comment + pinned comment
  10. History Store → append run record (git-backed for cross-run idempotency)
```

## Content Diversity System (Phase A–G)

The pipeline avoids the "problem → verse → encouragement" loop by using a **multi-dimensional rotation engine** built on a lightweight, $0, stdlib-only diversity module (`src/content/diversity.py`).

### Content Archetypes (7)

Each piece starts from a distinct creative direction:

| Archetype | Entry Point | Typical Tone |
|-----------|-------------|--------------|
| `biblical_reflection` | A biblical truth/doctrine | reverent, grounded |
| `everyday_observation` | An ordinary moment/scene | gentle, observant |
| `character_story` | A biblical figure/event | narrative, empathetic |
| `spiritual_principle` | A named principle (grace, patience, etc.) | formative, encouraging |
| `question_reflection` | A sincere reflective question | contemplative, honest |
| `scripture_first` | The Scripture text itself | devotional, authoritative |
| `seasonal_contextual` | Time, season, or life-moment | timely, pastoral |

### Spiritual Principles (20)

A **restrained vocabulary** of themes that rotates — problems like anxiety *can* surface naturally but are **never the primary mechanism**:

```
patience, grace, obedience, forgiveness, gratitude, humility,
perseverance, wisdom, trust, hope, service, compassion,
contentment, repentance, faithfulness, rest, peace, love, courage, joy
```

### Structural Pattern Rotation

Every dimension rotates via **weighted Least-Recently-Used + Coverage** (`select_lsru`) so the full library circulates without immediate repeats:

| Dimension | Variants | Rotation |
|-----------|----------|----------|
| Opening Pattern | 8 (reflective_question, declarative_truth, everyday_scene, ...) | LSUR |
| Conclusion Pattern | 7 (scripture_echo, personal_challenge, communal_affirmation, ...) | LSUR |
| Caption Style | 6 (verse_first, question_first, devotional_style, ...) | LSUR |
| CTA Pattern | 12 (affirm_truth, pursue_principle, notice_god, meditate_verse, ...) | LSUR |

### Slot Stratification (5 daily slots)

Each slot has a gentle bias so the day naturally spreads:

| Slot | Local (UTC+8) | Archetype Bias | Principle Bias |
|------|---------------|----------------|----------------|
| 1 | 07:00 | spiritual_principle, scripture_first, biblical_reflection | trust, faithfulness, rest |
| 2 | 11:00 | everyday_observation, question_reflection, seasonal_contextual | gratitude, contentment, peace |
| 3 | 15:00 | character_story, spiritual_principle, scripture_first | courage, perseverance, hope |
| 4 | 19:00 | question_reflection, everyday_observation, seasonal_contextual | wisdom, patience, humility |
| 5 | 23:00 | scripture_first, biblical_reflection, character_story | grace, love, joy |

### Near-Duplicate Detection

After generation, a **trigram Jaccard similarity** check runs against recent history:

- Story narration: reject if similarity ≥ 0.58
- Caption: reject if similarity ≥ 0.50

This catches reworded near-duplicates that exact-hash deduplication misses.

### Asset Rotation (Backgrounds + Ambient)

- **21 gospel WebP backgrounds** + **6 ambient piano WAVs** tracked in Git LFS
- **Strict round-robin (`select_round_robin`)** cycles assets so every background / ambient track is used once before any repeats — true full-cycle variety
- History records `background_used` / `ambient_used`; recency is read to pick the least-recently-used asset next

## Media Pipeline (ffmpeg-skill)

The rendering layer uses a vendored copy of [kajisho5/ffmpeg-skill](https://github.com/kajisho5/ffmpeg-skill) (MIT) for deterministic media operations:

- `probe.py` — structured media facts before/after render
- `check.py --platform reels` — PASS/FAIL against Reels spec (9:16, ≥1080 height, h264, yuv420p, ≤90s)
- `caption.py` — optional SRT/ASS subtitle burning (behind VideoRenderer)
- `look.py` — contact sheets for visual QA (development only)

All scripts vendored under `media/scripts/` (MIT, no runtime npm/node required). Composition remains in `src/video/ffmpeg.py`; `MediaService` at `src/video/media_service.py` is the single application boundary for probe → render → verify.

## Video Rendering (Ken Burns)

Renderer in `src/video/ffmpeg.py` produces 1080×1920 H.264/AAC MP4 at 30fps with:

- **Background** — selectable gospel WebP image (pre-scaled & center-cropped once to 1080×1920 cover), then fed through `zoompan` for slow Ken Burns push-in across the full clip (`d = narration frames`). Subtitles burned **after** zoom so text stays crisp and upright.
- **Ambient** — random ambient piano WAV mixed low (15%), faded in/out, ducked under narration via sidechain compression.
- **Reverb** — optional `aecho` church/chapel hall on narration (`REVERB_ENABLED`).

Why Ken Burns + pre-scale matters:

- **Performance**: previous implementation re-ran `scale+crop` every frame (CPU-heavy). Pre-scaling once + `zoompan` expanding a single frame is ~7× faster (≈53s → ≈7–19s locally), comfortably under CI's 15-min FFmpeg timeout.
- **Distribution**: motionless background reads to Facebook as "static image with audio" (limited Reels reach). Slow zoom gives genuine video motion so the Reel is treated as real video.

## Facebook Publisher

`src/facebook/reels.py` uploads the validated MP4 via Meta Graph API `video_reels` endpoint (three-step resumable upload):

1. `POST /{page_id}/video_reels?upload_phase=START` → returns `video_id` + `upload_url`
2. `PUT {upload_url}` (binary video, `Authorization: OAuth ***`) → uploads video
3. `POST /{page_id}/video_reels?upload_phase=FINISH&video_id=...` → publishes Reel

Features:

- Dry-run mode — never hits network; prints what would be posted
- Caption building — title + caption + hashtags, capped at 500 chars
- Typed errors — `FacebookAuthError` (invalid token/perms), `FacebookRateLimitError` (613), `FacebookPublishError` (transient)
- Bounded retries — only on transient failures (5xx/network); non-transient (auth/perm/invalid-param) fail immediately
- No secret leakage — access token never logged or included in errors
- Rate limit — 30 Reels/24h enforced by Meta; app enforces same

Required permissions on Page access token: `pages_read_engagement`, `pages_manage_posts`.

## Run History & Idempotency

`src/history/store.py` records every run in `data/run_history.jsonl` (JSONL, one line per run):

- **Exact-duplicate prevention**: `was_published(hash)` skips any story whose content hash was already published live (dry-runs / failures never block)
- **30-day scripture cooldown**: `ScriptureCooldown` blocks any **exact** bible reference (e.g. `Matthew 1:16`) from republishing within 30 days of its last live use. Only exact `Book chapter:verse` matches gate; `Matthew 1:17` / `Matthew 2:1` are unaffected. Dry-runs and failed publishes never count. The blocked list is injected into the LLM prompt as a hard "do not use" list, and the generator re-rolls if the model picks a blocked verse.
- **Diversity metadata persisted**: `archetype`, `primary_theme`, `scripture_book`, `opening_pattern`, `caption_style`, `cta_pattern`, `background_used`, `ambient_used`, `voice_used`, plus full `story_text` for near-dup checks
- **Append-only, stdlib-only** — no database, no paid services
- **Corrupt lines tolerated** — skipped with warning, never fatal
- **No secrets stored** — tokens, page IDs, credentials never appear in history

History is git-backed: GitHub Actions `persist-history` job (`if: always()`, best-effort, `continue-on-error: true`) commits `data/run_history.jsonl` back to the repo so duplicate detection works across serverless runners. The file is carried from the `generate-and-publish` job to `persist-history` via an **artifact upload/download** (they run on different VMs, so a filesystem write alone would be lost).

## CI / CD

Two GitHub Actions workflows:

- **`.github/workflows/daily.yml`** — production pipeline. Triggers via `workflow_dispatch` (Actions UI) and `repository_dispatch` (cron-job.org). **No built-in `schedule`** — cron-job.org is the sole scheduler (5 slots/day). Runs full pipeline, then persists run history. `concurrency: asmr-pipeline` prevents overlapping runs. `SLOT` comes from dispatch input/`client_payload.slot` and drives voice cycling.
- **`.github/workflows/ci.yml`** — runs on every push/PR: `pytest` + `ruff check src tests scripts` + config validation (no secrets required).

`ruff.toml` encodes project lint conventions (bare `except Exception` in phase handlers, deliberate `subprocess.run` without `check` in tests, etc.).

## Scheduling with cron-job.org

Pipeline runs with your PC **off** via GitHub Actions + free [cron-job.org](https://cron-job.org) scheduled triggers. cron-job.org fires a `repository_dispatch` event; GitHub runs the workflow. Five daily publishing slots (7am, 11am, 3pm, 7pm, 11pm local, UTC+8), each a separate cron-job.org job that posts a distinct `slot`.

> **Live by default**: a `repository_dispatch` event has **no `dry_run` input**. The workflow's `DRY_RUN` reads `inputs.dry_run` (Actions UI form only), so **every cron-job.org dispatch runs LIVE and publishes a real Reel**. To test the render without publishing, use the Actions UI **Run workflow** with `dry_run: true` (+ optionally `upload_artifact: true` to download the MP4).

### 1. Create a GitHub PAT (one-time)

- GitHub → Settings → Developer settings → **Personal access tokens**
- **Fine-grained** (recommended): repo access to this repository, **Actions: read and write** (repository_dispatch requires Actions permission — `Contents: write` alone is **not** sufficient)
- Or **classic** token with the `repo` scope
- Store in your password manager — **never commit it**. This PAT lives inside cron-job.org, not in GitHub.

### 2. Create five cron jobs (web console, ~2 minutes each)

For **each** of the 5 slots (only the schedule time and `client_payload.slot` differ):

1. Sign up / log in at [cron-job.org](https://cron-job.org)
2. **Create job** → name it e.g. `ASMR Slot 1 (7am)`
3. **URL:** `https://api.github.com/repos/tddymnbt/automatic-octo-doodle/dispatches`
4. **Request method:** `POST`
5. **Authorization:** use cron-job.org's **HTTP Authorization** field → type **Bearer** → value = your PAT (a plain `Authorization` request header may be stripped). Ensure `Content-Type: application/json`. **Headers:**
   | Header | Value |
   |---|---|
   | `Accept` | `application/vnd.github+json` |
   | `X-GitHub-Api-Version` | `2022-11-28` |
6. **Request body:** carry the slot in `client_payload`:
   ```json
   {"event_type":"trigger-pipeline","client_payload":{"slot":"1"}}
   ```
7. **Execution schedule:** daily at the slot's local (UTC+8) time:
   | Slot | UTC+8 time | `client_payload.slot` |
   |------|-----------|----------------------|
   | 1 | 07:00 | `"1"` |
   | 2 | 11:00 | `"2"` |
   | 3 | 15:00 | `"3"` |
   | 4 | 19:00 | `"4"` |
   | 5 | 23:00 | `"5"` |
8. Save. cron-job.org now fires the pipeline at each slot.

Why the body carries **only `slot`**: `dry_run` and `upload_artifact` in `client_payload` are **ignored** by the workflow (both read `inputs.*`, which `repository_dispatch` lacks). A dispatch always publishes live; artifact upload only happens when you set it in the Actions UI.

> cron-job.org's 30s request timeout does **not** affect the pipeline: the dispatch POST returns HTTP 204 almost instantly and GitHub runs the workflow asynchronously on its own runner (FFmpeg timeout 15 min, job timeout 6h). A `403 Forbidden` from GitHub means the request reached GitHub but was rejected for auth reasons — check the PAT's Actions/repo scope and how cron-job.org sends the Bearer token.

> The `repository_dispatch` event only triggers workflows committed to the **default branch**. The workflow's `concurrency: asmr-pipeline` guard means even if two slots fire close together, only one pipeline runs (5 slots → 5 publishes/day).

### Manual trigger (also useful for testing)

```bash
python scripts/trigger_pipeline.py --repo owner/repo --token "$GITHUB_PAT"
# Optional: --payload '{"slot": "1", "dry_run": true}' — NOTE: dry_run in the
# payload is not consumed by the workflow; this always fires a live publish.
```

The script is stdlib-only, prints `✓ Repository dispatch sent...` on success (HTTP 204), and **never prints or logs the token**.

## Quick Start

### Prerequisites

- Python 3.11+
- FFmpeg
- GitHub account
- Google AI Studio / Gemini API access
- Facebook Page with Meta developer access (`pages_read_engagement`, `pages_manage_posts`)

### Local Development

1. Clone the repository:
   ```bash
   git clone <repository-url>
   cd asmr-story-reels
   ```

2. Create virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # or `venv\Scripts\activate` on Windows
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Create `.env` file (copy from `.env.example`):
   ```bash
   cp .env.example .env
   ```

5. Add your credentials to `.env`:
   ```
   GEMINI_API_KEY=your_key_here
   META_PAGE_ACCESS_TOKEN=your_token_here
   META_PAGE_ID=your_page_id_here
   ```

6. Run dry mode:
   ```bash
   python src/main.py
   ```

### GitHub Actions Setup

1. Add repository secrets:
   - `GEMINI_API_KEY`
   - `META_PAGE_ACCESS_TOKEN`
   - `META_PAGE_ID`

2. The workflow runs automatically or can be triggered manually.

## Configuration

See `.env.example` for all configuration options. Key settings:

| Setting | Default | Description |
|---------|---------|-------------|
| `DRY_RUN` | `true` | Skip Facebook publishing |
| `VIDEO_WIDTH` | `1080` | Output width |
| `VIDEO_HEIGHT` | `1920` | Output height |
| `TARGET_DURATION_SECONDS` | `45` | Target video length |
| `KOKORO_VOICE` | (slot-driven) | `am_fenrir` (odd slots) / `am_onyx` (even) |
| `RANDOM_AMBIENT` | `true` | Randomize ambient track per run |
| `ENABLE_BACKGROUND` | `true` | Enable gospel background images |
| `REVERB_ENABLED` | `false` | Subtle church reverb on narration |

## Project Structure

```
├── .github/workflows/    # GitHub Actions
├── assets/               # Background images (LFS), ambient audio (LFS)
├── src/                  # Application code
│   ├── ai/               # Gemini API, TTS, story generator
│   ├── content/          # Gospel generation, validation, diversity
│   ├── video/            # FFmpeg, subtitles, media service
│   ├── facebook/         # Meta Graph API publisher
│   ├── assets/           # Asset selection (round-robin rotation)
│   ├── history/          # Run history store (JSONL)
│   └── utils/            # Retry helpers
├── tests/                # Test suite (364 passing)
├── scripts/              # Utility scripts (trigger, validate, diagnose)
├── data/                 # Runtime data (gitignored except run_history.jsonl)
├── media/scripts/        # Vendored ffmpeg-skill scripts
├── .env.example          # Configuration template
├── AGENTS.md             # Secret handling rules
├── requirements.txt      # Python dependencies
└── ruff.toml             # Lint configuration
```

## Security

- **Never commit `.env`** — it's in `.gitignore`
- **Never expose secrets** — see `AGENTS.md` for rules
- **GitHub Secrets** for CI credentials
- **No secrets in logs** — validated at runtime
- **Secret scanning** — `scripts/scan_secrets.py` runs in CI on every push/PR (detects tracked `.env` files, secret-named assignments in source)
- **Dependabot** — daily dependency checks for pip and GitHub Actions (free, GitHub-native)

## Hardening & Reliability

- **Bounded retries** — TTS (Gemini fallback), story generation, and Facebook publisher all use bounded retries with exponential backoff; auth errors fail immediately and are never retried
- **TTS auth-failure fast-path** — invalid/expired Gemini API key aborts pipeline before any render or publish work
- **Safe diagnostics** — `scripts/diagnose.py` prints system/config/history summary with zero secret exposure (run locally or in CI)
- **History idempotency** — `data/run_history.jsonl` (git-backed via GitHub Actions, crossed between jobs via artifact upload/download) prevents duplicate publishes across runs; exact scripture references are additionally hard-blocked for 30 days (`ScriptureCooldown`)

## Development

### Running Tests

```bash
pytest tests/
```

### Environment Validation

```bash
python scripts/validate_environment.py
```

### Safe Diagnostics

```bash
python scripts/diagnose.py          # full diagnostics
python scripts/diagnose.py --brief  # one-liner
```

### Secret Scan

```bash
python scripts/scan_secrets.py       # scan git-tracked files
python scripts/scan_secrets.py --no-git  # scan entire workspace
```

## Go-Live Checklist

One-time setup before the first live run:

### 1. Commit all source code

```bash
git add -A
git commit -m "feat: complete pipeline — Phases A–G"
git push origin main
```

CI will run automatically on push (pytest + ruff + secret scan + config validation).

### 2. Add GitHub Actions secrets

Go to **Settings → Secrets and variables → Actions → New repository secret**:

| Secret | Value |
|--------|-------|
| `GEMINI_API_KEY` | Your Google AI Studio API key |
| `META_PAGE_ACCESS_TOKEN` | Facebook Page access token (`pages_read_engagement` + `pages_manage_posts`) |
| `META_PAGE_ID` | Your Facebook Page ID |

### 3. Verify CI passes

Check the **Actions** tab — the CI workflow should show ✓ on `main`.

### 4. First live run (manual, dry-run → live)

```bash
# Dry-run first (via Actions UI: dry_run=true, upload_artifact=true to see the MP4)
#   GitHub → Actions → Daily ASMR Story Reel → Run workflow

# Live test via GitHub CLI (if installed)
gh workflow run daily.yml
```

### 5. Verify the Reel appeared on your Facebook Page

Check your Page's Reels tab for the new post.

### 6. Set up cron-job.org daily schedule

Follow the steps in **Scheduling with cron-job.org** above to automate daily runs.

### 7. Monitor first week

- Check **Actions** tab for failed runs
- Review `data/run_history.jsonl` (committed by the `persist-history` job)
- Check `python scripts/diagnose.py` for system health

### Prerequisites Summary

- Python 3.11+
- FFmpeg (installed by workflow; local dev needs manual install)
- espeak-ng (installed by workflow; needed for Kokoro TTS)
- Google AI Studio account + API key (free tier)
- Facebook Page with `pages_read_engagement` + `pages_manage_posts` permissions
- GitHub PAT (for cron-job.org; classic `repo` scope or fine-grained with **Actions: read and write** — this is what the 403 error indicates if mis-scoped)

## License

Private project - not for distribution.
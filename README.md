# ASMR Story Shorts

Automated pipeline for creating and publishing ASMR-style story videos to Facebook Reels.

## Overview

This project generates original short ASMR story videos (30-60 seconds) and publishes them to Facebook Reels automatically using:

- **Gemini AI** for story generation and content metadata
- **Kokoro** (local, offline, free) for TTS narration — Gemini TTS optional fallback
- **FFmpeg** for video rendering
- **Meta Graph API** for Facebook publishing
- **GitHub Actions** for automation

## Cost

This pipeline is designed to run at **$0** using:
- Free Gemini API tier (story generation only)
- Kokoro open-weight TTS (offline, no API key)
- GitHub Actions (2,000 minutes/month free)
- FFmpeg (open source)
- Facebook Page API (free)

## Architecture

```
cron-job.org → GitHub Actions → Pipeline → Facebook Page
Pipeline:
  Gemini 3.5 Flash-Lite → Story + metadata
  Kokoro TTS (offline)   → Narration WAV
  Audio validation gate  → reject silent/broken audio
  Asset selection        → Ken Burns visuals
  Subtitle generation    → SRT
  MediaService + FFmpeg  → Render 1080×1920 H.264/AAC MP4
  MediaService verify    → ffmpeg-skill reels compliance check
  Meta Graph API         → Publish Reel
```

## Media Pipeline (ffmpeg-skill)

The rendering layer uses a vendored copy of [kajisho5/ffmpeg-skill](https://github.com/kajisho5/ffmpeg-skill) (MIT) for deterministic media operations:

- **`probe.py`** — structured media facts before and after render
- **`check.py --platform reels`** — PASS/FAIL against Reels spec (9:16, ≥1080 height, h264, yuv420p, ≤90s)
- **`caption.py`** — optional SRT/ASS subtitle burning (behind VideoRenderer)
- **`look.py`** — contact sheets for visual QA (development only)

All scripts are vendored under `media/scripts/` (MIT, no runtime npm/node required). Composition remains in `src/video/ffmpeg.py`; the `MediaService` wrapper at `src/video/media_service.py` is the single application boundary for probe → render → verify.

## Facebook Publisher

The Reels publisher at `src/facebook/reels.py` uploads the validated MP4 to a Facebook Page using the Meta Graph API `video_reels` endpoint (three-step resumable upload):

1. `POST /{page_id}/video_reels?upload_phase=START` → returns `video_id` + `upload_url`
2. `PUT {upload_url}` (binary video, `Authorization: OAuth <token>`) → uploads video
3. `POST /{page_id}/video_reels?upload_phase=FINISH&video_id=...` → publishes the Reel

Features:
- **Dry-run mode** — never hits the network; prints what would be posted
- **Caption building** — title + caption + hashtags, capped at 500 characters
- **Typed errors** — `FacebookAuthError` (invalid token/perms), `FacebookRateLimitError` (613), `FacebookPublishError` (transient)
- **Bounded retries** — only on transient failures (5xx/network); non-transient (auth/perm/invalid-param) fail immediately
- **No secret leakage** — access token never logged or included in errors
- **Rate limit** — 30 Reels/24h enforced by Meta; app enforces same

Required permissions on the Page access token: `pages_read_engagement`, `pages_manage_posts`.

## Run History & Idempotency

The pipeline records every run in `data/run_history.jsonl` (path from `DATA_DIR`, default `data/`) via `src/history/store.py`:

- **One JSON line per run** — run_id, timestamp, content hash, status, story title, publish ids, error
- **Duplicate prevention** — a story whose content hash was already *published live* is skipped before TTS/render/publish (`was_published`)
- **Dry-run / failed / duplicate-skip records never block future publishing** — only real live publishes count
- **Append-only, stdlib only** — no database, no paid services
- **Corrupt lines tolerated** — a bad line is skipped with a warning, never fatal
- **No secrets stored** — tokens, page ids and credentials never appear in history

History recording is non-fatal: if the history file can't be written, the pipeline continues (with a warning).

> **Cross-run persistence:** GitHub Actions runners are ephemeral — `data/` does not survive between runs unless persisted. The daily workflow persists history by **committing `data/run_history.jsonl` back to the repo** (a dedicated `persist-history` job, `if: always()`, best-effort), so duplicate detection works across cron runs.

## CI / CD

Two GitHub Actions workflows:

- **`.github/workflows/daily.yml`** — the production pipeline. Triggers via `workflow_dispatch`, `repository_dispatch` (for cron-job.org), and a daily `schedule`. Runs the full pipeline (story → TTS → audio gate → assets → subtitles → render → verify → publish → history), then persists run history back to the repo. `concurrency` prevents overlapping runs; `DRY_RUN` maps from the `dry_run` dispatch input.
- **`.github/workflows/ci.yml`** — runs on every push/PR: `pytest` + `ruff check src tests scripts` + config validation (no secrets required).

`ruff.toml` encodes the project's lint conventions (bare `except Exception` phase handlers, deliberate `subprocess.run` without `check` in tests, etc.).

## Scheduling with cron-job.org

The pipeline runs with your PC **off** via GitHub Actions + a free [cron-job.org](https://cron-job.org) scheduled trigger. cron-job.org fires a `repository_dispatch` event; GitHub runs the workflow.

### 1. Create a GitHub PAT (one-time)

- GitHub → Settings → Developer settings → **Personal access tokens**
- **Fine-grained** (recommended): repo access to this repository, **Contents: read and write**
- Or **classic** token with the `repo` scope
- Store it in your password manager — **never commit it**

### 2. Create the cron job (web console, ~2 minutes)

1. Sign up / log in at [cron-job.org](https://cron-job.org)
2. **Create job** → name it e.g. `ASMR pipeline daily`
3. **URL:** `https://api.github.com/repos/<owner>/<repo>/dispatches`
4. **Request method:** `POST`
5. **Headers:**
   | Header | Value |
   |---|---|
   | `Authorization` | `Bearer <your-GITHUB_PAT>` |
   | `Accept` | `application/vnd.github+json` |
   | `Content-Type` | `application/json` |
   | `X-GitHub-Api-Version` | `2022-11-28` |
6. **Request body:**
   ```json
   {"event_type": "trigger-pipeline"}
   ```
7. **Execution schedule:** daily at your preferred time (e.g. `00:12` UTC; the repo's built-in `0 12 * * *` schedule remains a secondary fallback)
8. Save. cron-job.org now fires the pipeline daily.

> The `repository_dispatch` event only triggers workflows committed to the **default branch**. The workflow's `concurrency: asmr-pipeline` guard means even if cron-job.org and GitHub's own schedule fire together, only one pipeline runs.

### Manual trigger (also useful for testing)

```bash
python scripts/trigger_pipeline.py --repo owner/repo --token "$GITHUB_PAT"
# Optional: --payload '{"dry_run": true}' for a dry-run publish
```

The script is stdlib-only, prints `✓ Repository dispatch sent...` on success (HTTP 204), and **never prints or logs the token**.

## Quick Start

### Prerequisites

- Python 3.11+
- FFmpeg
- GitHub account
- Google AI Studio / Gemini API access
- Facebook Page with Meta developer access (pages_read_engagement, pages_manage_posts)

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

## Project Structure

```
├── .github/workflows/    # GitHub Actions
├── assets/               # Background images, ambient audio
├── src/                  # Application code
│   ├── ai/               # Gemini API integration
│   ├── content/          # Story generation, validation
│   ├── video/            # FFmpeg, subtitles
│   ├── facebook/         # Meta Graph API
│   ├── assets/           # Asset selection
│   ├── history/          # Run history
│   └── utils/            # Retry helpers, shared utilities
├── tests/                # Test suite
├── scripts/              # Utility scripts
├── data/                 # Runtime data (gitignored)
├── .env.example          # Configuration template
├── AGENTS.md             # Secret handling rules
├── PLAN.md               # Implementation plan
└── requirements.txt      # Python dependencies
```

## Security

- **Never commit `.env`** - it's in `.gitignore`
- **Never expose secrets** - see `AGENTS.md` for rules
- **GitHub Secrets** for CI credentials
- **No secrets in logs** - validated at runtime
- **Secret scanning** — `scripts/scan_secrets.py` runs in CI on every push/PR (detects tracked `.env` files, secret-named assignments in source)
- **Dependabot** — daily dependency checks for pip and GitHub Actions (free, GitHub-native)

## Hardening & Reliability

- **Bounded retries** — TTS (Gemini fallback), story generation, and Facebook publisher all use bounded retries with exponential backoff; auth errors fail immediately and are never retried
- **TTS auth-failure fast-path** — invalid/expired Gemini API key aborts the pipeline before any render or publish work
- **Safe diagnostics** — `scripts/diagnose.py` prints system/config/history summary with zero secret exposure (run locally or in CI)
- **History idempotency** — `data/run_history.jsonl` (git-backed via GitHub Actions) prevents duplicate publishes across runs

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
git commit -m "feat: complete pipeline — Phases 0–14"
git push origin main
```
CI will run automatically on push (pytest + ruff + secret scan + config validation).

### 2. Add GitHub Actions secrets
Go to **Settings → Secrets and variables → Actions → New repository secret**:

| Secret | Value |
|---|---|
| `GEMINI_API_KEY` | Your Google AI Studio API key |
| `META_PAGE_ACCESS_TOKEN` | Facebook Page access token (`pages_read_engagement` + `pages_manage_posts`) |
| `META_PAGE_ID` | Your Facebook Page ID |

### 3. Verify CI passes
Check the **Actions** tab — the CI workflow should show ✓ on `main`.

### 4. First live run (manual, dry-run → live)
```bash
# Via GitHub CLI (if installed)
gh workflow run daily.yml -f dry_run=true

# Or via cron-job.org (see README § Scheduling)
# Or trigger manually:
python scripts/trigger_pipeline.py --repo owner/repo --token "$GITHUB_PAT"
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
- GitHub PAT (for cron-job.org; classic `repo` scope or fine-grained with Contents: write)

## License

Private project - not for distribution.

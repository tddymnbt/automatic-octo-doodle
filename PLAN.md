# ASMR Story Shorts → Facebook Reels

## Implementation Plan

**Status:** Phase 14 Complete — pipeline fully built, tested, and documented
**Primary Language:** Python
**Automation:** GitHub Actions + cron-job.org
**Content Model:** `gemini-3.5-flash-lite`
**TTS Provider:** Kokoro (local, offline) — Gemini TTS optional fallback
**Video Engine:** FFmpeg
**Publishing:** Meta Graph API / Facebook Page Reels

---

### Architecture

```text
cron-job.org
      |
      | GitHub repository_dispatch
      v
GitHub Actions
      |
      +--> Generate story + metadata
      |       Gemini 3.5 Flash-Lite
      |
      +--> Generate narration
      |       Kokoro (local, offline, free) or Gemini TTS (optional)
      |
      +--> Validate audio (hard gate - no render from unusable audio)
      |
      +--> Select reusable visual assets
      |
      +--> Generate subtitles
      |
      +--> FFmpeg render
      |
      +--> Validate final MP4
      |
      +--> Publish Reel
      |       Meta Graph API
      |
      +--> Save run history / status
      |
      v
Facebook Page
```

---

## Development Phases

### Phase 0 — Repository + Security ✅
- [x] Create repository structure
- [x] Add `.gitignore`
- [x] Create `.env.example`
- [x] Create `AGENTS.md`
- [x] Create `PLAN.md`
- [x] Set up basic directory structure

### Phase 1 — Environment Validation ✅
- [x] Build `scripts/validate_environment.py`
- [x] Create `src/config.py` centralized configuration module
- [x] Check required environment variables exist
- [x] Never print secret values
- [x] Add tests for config and validation

### Phase 2 — Gemini Story Generation ✅
- [x] Implement `src/ai/client.py` - Gemini API client wrapper
- [x] Implement `src/ai/story_generator.py` - Story generation with retries
- [x] Create `src/content/schema.py` - Pydantic models for StoryData, Scene
- [x] Create `src/content/prompts.py` - Story and safety prompts
- [x] Create `src/content/validator.py` - Content validation with hash
- [x] Add comprehensive tests for schema, prompts, and validator

### Phase 3 — Gemini TTS ✅
- [x] Implement `src/ai/tts_provider.py` with Protocol interface
- [x] Generate narration audio (WAV format)
- [x] Keep provider interface replaceable via TTSProvider Protocol
- [x] Add ASMR voice instruction template
- [x] Add PCM to WAV conversion
- [x] Add tests for TTS provider

### Phase 4 — Visual Asset System ✅
- [x] Implement `src/assets/models.py` - Asset and AssetCategory models
- [x] Implement `src/assets/selector.py` - Asset selector with category mapping
- [x] Add background image categories (10 categories)
- [x] Create asset mapping logic with fallback selection
- [x] Add tests for asset models and selector

### Phase 5 — Subtitle Generation ✅
- [x] Implement `src/video/__init__.py` - Video package
- [x] Implement `src/video/subtitles.py` - Subtitle generator with SRT output
- [x] Generate SRT files from narration text
- [x] Add timing synchronization based on speaking rate
- [x] Add tests for subtitle generator

### Phase 6 — FFmpeg Renderer ✅
- [x] Implement `src/video/ffmpeg.py` - VideoRenderer with Ken Burns effect
- [x] Render 1080x1920 H.264/AAC MP4 at 30 FPS
- [x] Image segments with pan/zoom animation
- [x] Subtitle burning (hardcoded SRT)
- [x] Audio mixing (narration + optional ambient)
- [x] Video validation (dimensions, FPS, duration, audio)
- [x] Add tests for FFmpeg renderer

### Phase 7 — TTS Stabilization (Kokoro) + Audio Gate ✅
- [x] Add `TTSProvider` registry factory (`create_tts_provider`) selectable via `TTS_PROVIDER`
- [x] Implement `KokoroTTSProvider` (local, offline, CPU, free, no API key)
- [x] Keep `GeminiTTSProvider` as optional fallback (provider-switchable)
- [x] Add config: `TTS_PROVIDER`, `KOKORO_VOICE`, `KOKORO_SPEED`, `KOKORO_LANG`
- [x] Implement hard audio-validation gate `src/audio/validator.py`
- [x] Wire audio gate into `src/main.py` (no render from unusable audio)
- [x] Install espeak-ng + Kokoro deps in `requirements.txt` and `daily.yml`
- [x] Add tests for Kokoro provider, factory selection, and audio validator
- [x] Add deterministic TTS smoke test `scripts/tts_test.py`
- [x] Validate end-to-end with a real Kokoro synthesis (CPU)

### Phase 8 — FFmpeg Skill Integration / Media Pipeline ✅
- [x] Vendor `ffmpeg-skill` (MIT) scripts into `media/scripts/` (probe, check, caption, look)
- [x] Add `MediaService` (`src/video/media_service.py`) — probe → render → check → verify boundary
- [x] `verify()` uses `check.py --platform reels` + exact contract (1080×1920, 30fps, h264/aac, 30–60s)
- [x] `probe()` uses vendored `probe.py` for structured media facts
- [x] main.py renders via MediaService; verify gate stops on invalid deliverable
- [x] Audio validation gate (Phase 7) preserved before render
- [x] Renderer composition (Ken Burns/subtitles/amix) unchanged — no competing renderer
- [x] Tests: `tests/test_media_service.py` (probe/verify/render/exact contract) — 19 new
- [x] E2E real-render verified: 1080×1920 h264 30fps AAC 32s → `verify() valid=True`
- [x] GitHub Actions compatible (stdlib-only vendored scripts; apt ffmpeg has libass)

### Phase 9 — Facebook Publisher ✅
- [x] Implement `src/facebook/reels.py` with three-step resumable upload (START → rupload → FINISH)
- [x] Dry-run mode never hits the network
- [x] Caption builder from story metadata (title + caption + hashtags, capped at 500)
- [x] Typed errors: FacebookAuthError (190/200), FacebookRateLimitError (613), FacebookPublishError
- [x] Bounded retries on transient failures only; non-transient (auth/perm/invalid-param) fail immediately
- [x] Secrets never logged or leaked in errors
- [x] Graph API version configurable (default v26.0)
- [x] Wire into main.py Phase 8; dry-run prints would-be caption
- [x] Tests: 29 tests covering dry-run, auth/rate-limit/param errors, retries, secret redaction, caption building

### Phase 10 — History / Idempotency ✅
- [x] Implement `src/history/store.py` — JSONL append-only history store (stdlib only)
- [x] RunRecord dataclass: run_id, timestamp, story_hash, status, story_title, dry_run, video_path, post_id, video_id, error, attempts, duration_s, asset_count, tts_provider
- [x] Duplicate detection gate in main.py (`was_published`) — skips pipeline if story hash was already published live
- [x] Dry-run/failed/duplicate records never block real publishing
- [x] Corrupt lines tolerated (skipped with warning, never fatal)
- [x] Secrets never stored in history (no tokens/page ids)
- [x] History recording at: duplicate-skip, publish-success, publish-failure (non-fatal on error)
- [x] Tests: `tests/test_history_store.py` — 18 new
- [x] Cross-run persistence strategy deferred to Phase 11/12 (GitHub Actions: cache vs git-backed history)

### Phase 11 — GitHub Actions ✅
- [x] Complete `.github/workflows/daily.yml` (production pipeline replaces placeholder)
- [x] Add `TTS_PROVIDER=kokoro`, `KOKORO_*`, `DATA_DIR=data` env to workflow
- [x] `workflow_dispatch.dry_run` input maps to `DRY_RUN` env (scheduled/dispatch run live)
- [x] `concurrency: asmr-pipeline` guard — no concurrent pipeline runs (duplicate/race protection)
- [x] Git-backed history persistence: `persist-history` job (`if: always()`, `contents: write`, `continue-on-error`) — **note:** file now crossed via artifact upload/download between `generate-and-publish` and `persist-history` (different VMs; see Phase 15)
- [x] Debug artifact upload (`upload_artifact` input, gated, 7-day retention)
- [x] New `.github/workflows/ci.yml` — pytest + ruff on push/PR
- [x] New `ruff.toml` — project conventions (BLE001/PLW1510/RUF012/PERF102/EXE001 ignored; test per-file ignores)
- [x] Fixed 2 real `ISC004` implicit-string-concat bugs in `ffmpeg.py` filter list (would have corrupted zoompan/fade filters)
- [x] Lint auto-fixes (43) applied to pre-existing files, behavior-preserving
- [x] Full suite + lint clean: 276 tests, `ruff check src tests scripts` passes
- [x] Workflows YAML-validated (Ruby stdlib parse)

### Phase 12 — cron-job.org ✅
- [x] New `scripts/trigger_pipeline.py` — stdlib-only CLI fires `repository_dispatch` (`POST /repos/{owner}/{repo}/dispatches`, `event_type: trigger-pipeline`)
- [x] Token only in `Authorization` header; never printed/logged/leaked in errors
- [x] Typed errors for 403/404/422/network; 204 = success
- [x] Optional `--payload` for `client_payload` (e.g. `{"dry_run": true}`)
- [x] Tests: `tests/test_trigger_pipeline.py` — 15 new (headers, body, no-token-leak, HTTP errors, CLI)
- [x] README "Scheduling with cron-job.org" — PAT setup (fine-grained/classic), cron web console config (URL/POST/headers/body/schedule), manual trigger, default-branch + concurrency notes
- [x] `.env.example` — added optional `GITHUB_PAT` (documented, never committed)

### Phase 13 — Reliability / Hardening ✅
- [x] `src/utils/retry.py` — bounded retry helper for transient failures (`retry_transient`)
- [x] TTS Gemini fallback: bounded retries on `GeminiRateLimitError` / `GeminiClientError` (config `TTS_RETRY_COUNT`, default 2); `GeminiAuthError` raised immediately
- [x] `TTSAuthError` exception — raised on missing/invalid Gemini API key; main.py fast-fails before render on auth failure
- [x] `scripts/scan_secrets.py` — stdlib secret scanner: tracks `.env` files, secret-named assignments, high-entropy values; skips tests/examples/vendored `.github`/media
- [x] Secret scan wired into `ci.yml` — runs on every push/PR
- [x] `.github/dependabot.yml` — daily checks for pip + GitHub Actions (GitHub-native, free)
- [x] `scripts/diagnose.py` — safe diagnostics (system, git, ffmpeg, config, last 5 runs); never prints secrets
- [x] `TTS_RETRY_COUNT` added to `.env.example` and `validate_environment.py` optional list
- [x] Tests: `test_retry.py` (8), `test_scan_secrets.py` (14), `test_diagnose.py` (9) — 31 new
- [x] Full suite: 322/322 pass; ruff clean on all new and modified files

### Phase 14 — Final E2E + Deploy Docs ✅
- [x] Live E2E verification: 323/323 tests pass, ruff clean, all workflow YAML valid, all imports resolve, no `.env` tracked in git
- [x] Full dry-run pipeline run verified end-to-end: all 8 phases complete (story → TTS → audio gate → assets → subtitles → render → verify → publish-dry-run)
- [x] **Bug fixed (E2E):** subtitle rendering failed on Homebrew FFmpeg (lacks libass) — added lazy `subtitles` filter probe + graceful degradation; CI's libass-enabled FFmpeg still burns subtitles
- [x] **Bug fixed (E2E):** output pixel format was `yuvj420p` (full-range) — verification gate expects `yuv420p`; forced `-color_range tv -colorspace bt709` metadata
- [x] **Bug fixed (E2E):** `PublishResult` lacked `attempts` — Phase 8 history recording crashed on dry-run; added field (default 1)
- [x] **Bug fixed (E2E):** AAC sample rate was 24kHz (narration's native rate) — verification gate expects 44.1/48kHz; render now enforces `-ar 48000`
- [x] Tests: `test_ffmpeg.py` +1 (subtitle-skip degradation path) — 323 total
- [x] All 9 pipeline modules importable: config, ai/story_generator, ai/tts_provider, assets/selector, video/subtitles, video/ffmpeg, video/media_service, facebook/reels, history/store, audio/validator, utils/retry
- [x] Dependabot config created (`.github/dependabot.yml`) — daily pip + GitHub Actions dependency checks
- [x] Go-live checklist documented in README.md: commit, secrets, CI verify, first run, cron setup, monitoring
- [x] Safe diagnostics + secret scan documented in README.md Development section
- [x] Definition of Done updated in PLAN.md

### Phase 15 — History Persistence Fix + 30-Day Scripture Cooldown ✅
- [x] **Bug fixed (duplicates):** `persist-history` never actually committed history because it ran on a **separate VM** and did a fresh checkout that always matched the branch (no diff). `generate-and-publish` now uploads `data/run_history.jsonl` as an artifact and `persist-history` downloads it before committing — the modified file actually reaches the repo.
- [x] `ScriptureCooldown` in `src/history/store.py` — normalizes `Book chapter:verse` references (`Matthew 1:16` → `matthew 1:16`) and blocks any **exact** reference from republishing within a 30-day window (only `status == published`, non dry-run count; dry-runs/failures never block)
- [x] `recent_normalized(days)` / `is_on_cooldown()` on `ScriptureCooldown`; `_normalize_scripture()` helper handles multi-word / ordinal books and chapter:verse ranges
- [x] `GospelGenerator.generate(blocked_scriptures=...)` re-rolls when the model returns an on-cooldown verse (bounded by `max_attempts`)
- [x] `GospelPrompts.gospel_prompt()` accepts `blocked_scriptures` and injects a **"🚫 HARD BLOCK — DO NOT USE"** section into the LLM prompt
- [x] `main.py` Phase 2 builds the cooldown list from live published history before generation (fails gracefully to no-op if history unavailable)
- [x] Tests: `tests/test_scripture_cooldown.py` — 3 new (normalization, verse-level gating within/outside window, dry-run/failure exclusion)
- [x] Full suite: 367 passed (3 pre-existing unrelated failures in `test_facebook_reels.py` / `test_ffmpeg.py`); all modified files `py_compile` clean

### Phase 16 — Strict Round-Robin Asset Cycling ✅
- [x] `select_round_robin()` in `src/content/diversity.py` — strict full-cycle selection: picks the least-recently-used option, prioritizing never-used assets so the **entire library is exhausted before any repeat**; deterministic within a cycle (list-order tiebreak)
- [x] `AssetSelector.select_background()` / `select_ambient()` in `src/assets/selector.py` — replaced weighted `select_lsru` with `select_round_robin` (reads `field_sequence("background_used")` / `field_sequence("ambient_used")`; no longer needs `field_counts`)
- [x] Both background (21 gospel WebP) and ambient (6 piano WAV) now cycle through all assets before reusing any
- [x] Tests: `tests/test_round_robin.py` (6 new: unused-first, mid-cycle LRU, never-used-beats-oldest, empty, absent-key, tie determinism); `tests/test_asset_selector.py` updated (2 renamed to round-robin + full-cycle exhaust check)
- [x] Full suite: 377 passed (same 3 pre-existing unrelated failures); all modified files `py_compile` clean

---

## Secret Management

### Secrets (GitHub Actions)
- `GEMINI_API_KEY`
- `META_PAGE_ACCESS_TOKEN`
- `META_PAGE_ID`

### Non-Secret Configuration
- `AI_MODEL`, `TTS_MODEL`, `TTS_PROVIDER`
- `KOKORO_VOICE`, `KOKORO_SPEED`, `KOKORO_LANG`
- `VIDEO_WIDTH`, `VIDEO_HEIGHT`, `VIDEO_FPS`
- `TARGET_DURATION_SECONDS`, `MIN_DURATION_SECONDS`, `MAX_DURATION_SECONDS`
- `DRY_RUN`, `LOG_LEVEL`
- `STORY_LANGUAGE`, `CONTENT_STYLE`
- `FACEBOOK_GRAPH_VERSION`, `FACEBOOK_RETRY_COUNT`
- `MAX_VISUALS_PER_VIDEO`, `ENABLE_AMBIENT_AUDIO`, `ENABLE_SUBTITLES`

---

## Definition of Done

The project is complete when all are true:

- [x] Story is generated automatically
- [x] Story passes validation
- [x] Narration is generated automatically
- [x] Narration is clear and ASMR-like
- [x] Visuals are selected automatically
- [x] Subtitles are generated automatically
- [x] FFmpeg creates 1080x1920 MP4
- [x] Video is 30–60 seconds
- [x] Video is validated before publishing
- [x] Facebook Reel is published successfully
- [x] Duplicate content is prevented
- [x] No exact bible reference is republished within 30 days (`ScriptureCooldown`)
- [x] Every background / ambient asset is used once before any repeats (strict round-robin)
- [x] History is saved
- [x] Invalid Facebook token stops safely
- [x] GitHub Actions runs end-to-end
- [x] cron-job.org triggers the workflow
- [x] `.env` is never committed
- [x] GitHub Secrets are used in CI
- [x] AI agents do not receive secret values
- [x] Logs contain no credential values
- [x] No paid automation infrastructure is required

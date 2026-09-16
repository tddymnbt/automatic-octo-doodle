"""Run history and idempotency tracking.

Stores one JSON record per pipeline run as JSONL (one JSON object per line)
in ``{data_dir}/run_history.jsonl``. The store is used to:

* Prevent duplicate Reels: a story whose content hash was already published
  live is skipped on subsequent runs.
* Keep an audit trail of runs (status, timestamps, publish ids, errors).
* Track situation summaries and scripture references for anti-repetition.

Design notes:

* **File-based, stdlib only** (``json``/``os``/``pathlib``) — no database,
  no paid services, GitHub Actions compatible.
* **Append-only**: each run appends one line; a crashed mid-write can at
  worst leave a partial line, which is tolerated on read (skipped with a
  warning, never fatal).
* **Secrets are never stored**: no tokens, no page ids, no credentials.
* **Dry-run records never count as published**: ``was_published()`` only
  returns True for records with ``status == "published"`` and
  ``dry_run == false``, so dry runs can't accidentally block real
  publishing later.
"""

from __future__ import annotations

import datetime as _dt
import json
import logging
import re
import time
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# History statuses
STATUS_PUBLISHED = "published"
STATUS_DUPLICATE = "skipped_duplicate"
STATUS_FAILED = "failed"
STATUS_DRY_RUN = "dry_run"


@dataclass
class RunRecord:
    """A single pipeline run record."""

    run_id: str
    timestamp: str
    story_hash: str
    status: str
    slot: str = ""
    story_title: str = ""
    situation_summary: str = ""
    scripture_reference: str = ""
    dry_run: bool = False
    video_path: str = ""
    post_id: str = ""
    video_id: str = ""
    error: str = ""
    attempts: int = 0
    duration_s: float = 0.0
    asset_count: int = 0
    tts_provider: str = ""

    # === Content-diversity metadata (Phase A+) ===
    # Stored so rotation/scoring can query dimensions the exact-hash
    # never covered. Empty defaults keep legacy JSONL records loadable.
    story_text: str = ""
    scripture_book: str = ""
    archetype: str = ""
    primary_theme: str = ""
    secondary_themes: str = ""  # JSON-encoded list for the JSONL row
    tone: str = ""
    opening_pattern: str = ""
    conclusion_pattern: str = ""
    caption_style: str = ""
    cta_pattern: str = ""
    key_concepts: str = ""  # JSON-encoded list
    background_used: str = ""
    ambient_used: str = ""
    voice_used: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary (JSON-safe)."""
        return asdict(self)


def _now_iso() -> str:
    """Current UTC time in ISO format."""
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def new_run_id() -> str:
    """Generate a unique run id."""
    return uuid.uuid4().hex[:12]


class HistoryStore:
    """Append-only JSONL store of pipeline run records."""

    #: Filename inside the data directory.
    FILENAME = "run_history.jsonl"

    def __init__(self, data_dir: str | Path | None = None) -> None:
        """Initialize the store.

        Args:
            data_dir: Directory for the history file. Defaults to
                ``settings.data_dir`` (env ``DATA_DIR`` or ``data/``).
        """
        if data_dir is None:
            from src.config import settings

            data_dir = settings.data_dir
        self.data_dir = Path(data_dir)
        self.path = self.data_dir / self.FILENAME

    # ------------------------------------------------------------------
    # Writing
    # ------------------------------------------------------------------

    def record_run(self, record: RunRecord) -> None:
        """Append a run record to the history file."""
        self.data_dir.mkdir(parents=True, exist_ok=True)

        line = json.dumps(record.to_dict(), sort_keys=True) + "\n"
        with self.path.open("a", encoding="utf-8") as f:
            f.write(line)

        logger.debug(f"Recorded run {record.run_id}: {record.status}")

    def record(
        self,
        *,
        story_hash: str,
        status: str,
        slot: str = "",
        story_title: str = "",
        situation_summary: str = "",
        scripture_reference: str = "",
        dry_run: bool = False,
        video_path: str = "",
        post_id: str = "",
        video_id: str = "",
        error: str = "",
        attempts: int = 0,
        duration_s: float = 0.0,
        asset_count: int = 0,
        tts_provider: str = "",
        story_text: str = "",
        scripture_book: str = "",
        archetype: str = "",
        primary_theme: str = "",
        secondary_themes: str = "",
        tone: str = "",
        opening_pattern: str = "",
        conclusion_pattern: str = "",
        caption_style: str = "",
        cta_pattern: str = "",
        key_concepts: str = "",
        background_used: str = "",
        ambient_used: str = "",
        voice_used: str = "",
    ) -> RunRecord:
        """Build and record a run in one call."""
        record = RunRecord(
            run_id=new_run_id(),
            timestamp=_now_iso(),
            story_hash=story_hash,
            status=status,
            slot=slot,
            story_title=story_title,
            situation_summary=situation_summary,
            scripture_reference=scripture_reference,
            dry_run=dry_run,
            video_path=video_path,
            post_id=post_id,
            video_id=video_id,
            error=error,
            attempts=attempts,
            duration_s=duration_s,
            asset_count=asset_count,
            tts_provider=tts_provider,
            story_text=story_text,
            scripture_book=scripture_book,
            archetype=archetype,
            primary_theme=primary_theme,
            secondary_themes=secondary_themes,
            tone=tone,
            opening_pattern=opening_pattern,
            conclusion_pattern=conclusion_pattern,
            caption_style=caption_style,
            cta_pattern=cta_pattern,
            key_concepts=key_concepts,
            background_used=background_used,
            ambient_used=ambient_used,
            voice_used=voice_used,
        )
        self.record_run(record)
        return record

    # ------------------------------------------------------------------
    # Reading
    # ------------------------------------------------------------------

    def load_history(self) -> list[RunRecord]:
        """Load all run records. Corrupt lines skipped with warning."""
        if not self.path.exists():
            return []

        records: list[RunRecord] = []
        with self.path.open("r", encoding="utf-8") as f:
            for line_no, line in enumerate(f, start=1):
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    # Handle legacy records missing new fields
                    data.setdefault("situation_summary", "")
                    data.setdefault("scripture_reference", "")
                    records.append(RunRecord(**data))
                except (json.JSONDecodeError, TypeError, ValueError) as e:
                    logger.warning(
                        f"Skipping corrupt history line {line_no}: {e}"
                    )
        return records

    def recent_entries(self, limit: int | None = None) -> list[dict]:
        """Return recent situation summaries and scripture references for anti-repetition."""
        entries = []
        for record in self.load_history():
            if record.situation_summary and record.scripture_reference:
                entries.append({
                    "situation_summary": record.situation_summary,
                    "scripture_reference": record.scripture_reference,
                })
        if limit is not None:
            return entries[-limit:]
        return entries

    def recent_hashes(self, limit: int | None = None) -> list[str]:
        """Return story hashes in file order."""
        hashes = [r.story_hash for r in self.load_history() if r.story_hash]
        if limit is not None:
            return hashes[-limit:]
        return hashes

    def was_published(self, story_hash: str) -> bool:
        """Return True if a story hash was already published live."""
        for record in self.load_history():
            if (
                record.story_hash == story_hash
                and record.status == STATUS_PUBLISHED
                and not record.dry_run
            ):
                return True
        return False

    def last_run(self) -> RunRecord | None:
        """Return the most recent run record, or None if empty."""
        if not self.path.exists():
            return None

        last_line: str | None = None
        with self.path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    last_line = line

        if not last_line:
            return None
        try:
            data = json.loads(last_line)
            data.setdefault("situation_summary", "")
            data.setdefault("scripture_reference", "")
            return RunRecord(**data)
        except (json.JSONDecodeError, TypeError, ValueError) as e:
            logger.warning(f"Skipping corrupt history last line: {e}")
            return None

    def published_hashes(self) -> list[str]:
        """Return hashes that were actually published live."""
        return [
            r.story_hash
            for r in self.load_history()
            if r.story_hash
            and r.status == STATUS_PUBLISHED
            and not r.dry_run
        ]

    # ------------------------------------------------------------------
    # Diversity / rotation queries (Phase A+)
    # ------------------------------------------------------------------

    def field_sequence(
        self,
        field: str,
        *,
        only_published: bool = False,
    ) -> list[str]:
        """Return the sequence of a record field's non-empty values, in order.

        Used to drive recency/coverage rotation. ``only_published=True``
        ignores dry-run/duplicate/failed records so only real publishes
        count toward rotation content.
        """
        values: list[str] = []
        for record in self.load_history():
            if only_published and (
                record.status != STATUS_PUBLISHED or record.dry_run
            ):
                continue
            value = getattr(record, field, "") or ""
            if value:
                values.append(value)
        return values

    def field_counts(
        self,
        field: str,
        *,
        only_published: bool = False,
    ) -> dict[str, int]:
        """Return a usage map of a record field's values (capitalize-canonical).

        Values are deduped by case-insensitive name (e.g. ``psalm`` and
        ``Psalm`` collapse) for fair rotation.
        """
        counts: dict[str, int] = {}
        for value in self.field_sequence(field, only_published=only_published):
            key = value.lower()
            counts[key] = counts.get(key, 0) + 1
        return counts

    def last_used(
        self,
        field: str,
        key: str,
        *,
        only_published: bool = False,
    ) -> int:
        """Return how many records back ``key`` last appeared in ``field``.

        0 = the most recent record; a large number = never/very old. Used to
        enforce asset and content recency spacing.
        """
        seq = self.field_sequence(field, only_published=only_published)
        deltas = [
            len(seq) - 1 - i for i, value in enumerate(seq) if value.lower() == key.lower()
        ]
        return min(deltas) if deltas else len(seq)


# ------------------------------------------------------------------
# Scripture cooldown (Phase: hard dedup)
# ------------------------------------------------------------------

#: Regex capturing ``Book Chapter:Verse`` (supports multi-word books like
#: "1 Corinthians", and chapter:verse "3:5-6", "3:5,7", or bare "3:5").
_SCRIPTURE_RE = re.compile(
    r"^\s*(?P<book>[\d]?\s*[A-Za-z][A-Za-z_\- .]*)"
    r"(?P<ref>\d+\s*:\s*[\d\,\.\-]+)\s*$"
)


def _normalize_scripture(reference: str) -> str | None:
    """Normalize a scripture reference to ``Book chapter:verse`` (lowercased).

    Returns ``None`` if the reference doesn't parse as a normal
    book/chapter/verse form (so malformed/odd refs are skipped rather than
    blocking everything).
    """
    ref = reference.strip()
    if not ref:
        return None
    m = _SCRIPTURE_RE.match(ref)
    if not m:
        return None
    book = re.sub(r"\s+", " ", m.group("book")).strip().rstrip("- ").lower()
    chap_verse = re.sub(r"\s+", "", m.group("ref")).lower()
    if not book or not chap_verse:
        return None
    return f"{book} {chap_verse}"


class ScriptureCooldown:
    """Resolve which scripture references are in cooldown.

    A reference is ``in`` cooldown if a *published* run used it within
    ``cooldown_days`` (default 30). Only exact ``Book chapter:verse``
    matches block publishing — e.g. ``matthew 1:16`` blocks ``matthew 1:16``
    but not ``matthew 1:17`` or ``matthew 2:1``.
    """

    def __init__(self, store: HistoryStore, cooldown_days: int = 30) -> None:
        self._store = store
        self.cooldown_days = cooldown_days

    def recent_normalized(self, *, only_published: bool = True, days: int | None = None) -> dict[str, str]:
        """Return a map ``{normalized_reference: raw_reference}`` of scripture
        refs seen in published runs within the (overridable) cooldown window.

        ``days`` defaults to ``cooldown_days`` (so the map matches the gate).
        """
        days = days if days is not None else self.cooldown_days
        cutoff = (
            _dt.datetime.now(_dt.timezone.utc)
            - _dt.timedelta(days=days)
        )
        seen: dict[str, str] = {}
        for record in self._store.load_history():
            if only_published and (
                record.status != STATUS_PUBLISHED or record.dry_run
            ):
                continue
            ts = record.timestamp
            if not ts:
                continue
            try:
                when = _dt.datetime.fromisoformat(ts.replace("Z", "+00:00"))
            except ValueError:
                when = None
            if when is None or when < cutoff:
                continue
            norm = _normalize_scripture(record.scripture_reference)
            if norm:
                seen[norm] = record.scripture_reference
        return seen

    def is_on_cooldown(self, reference: str, *, days: int | None = None) -> bool:
        """Return True if ``reference`` (or its normalized form) is on cooldown."""
        norm = _normalize_scripture(reference)
        if not norm:
            return False
        return norm in self.recent_normalized(only_published=True, days=days)
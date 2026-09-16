"""Sanity tests for the ScriptureCooldown logic (30-day hard block)."""
import datetime as _dt

from src.history.store import (
    HistoryStore,
    RunRecord,
    ScriptureCooldown,
    _normalize_scripture,
    _SCRIPTURE_RE,
)


def test_normalize_scripture():
    assert _normalize_scripture("Matthew 1:16") == "matthew 1:16"
    assert _normalize_scripture(" 1 Corinthians 3:5-6 ") == "1 corinthians 3:5-6"
    assert _normalize_scripture("Psalm 23:1") == "psalm 23:1"
    assert _normalize_scripture("John 3:16") == "john 3:16"
    assert _normalize_scripture("bad") is None
    assert _normalize_scripture("") is None


def _record(store: HistoryStore, ref: str, ts: str, status="published", dry=False):
    store.record_run(
        RunRecord(
            run_id="r",
            timestamp=ts,
            story_hash="h",
            status=status,
            scripture_reference=ref,
            dry_run=dry,
        )
    )


def test_cooldown_blocks_recent_published(tmp_path):
    store = HistoryStore(data_dir=tmp_path)
    now = _dt.datetime.now(_dt.timezone.utc)
    recent = (now - _dt.timedelta(days=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
    old = (now - _dt.timedelta(days=40)).strftime("%Y-%m-%dT%H:%M:%SZ")

    _record(store, "Matthew 1:16", recent)  # within 30 days -> blocked
    _record(store, "Psalm 23:1", old)       # outside 30 days -> allowed

    cd = ScriptureCooldown(store, cooldown_days=30)
    assert cd.is_on_cooldown("Matthew 1:16")
    assert not cd.is_on_cooldown("Matthew 1:17")  # verse-level only
    assert not cd.is_on_cooldown("Psalm 23:1")    # too old
    assert not cd.is_on_cooldown("Genesis 1:1")   # unused


def test_cooldown_ignores_dry_run_and_non_published(tmp_path):
    store = HistoryStore(data_dir=tmp_path)
    now = _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    _record(store, "John 3:16", now, status="dry_run", dry=True)
    _record(store, "Mark 1:1", now, status="failed")
    cd = ScriptureCooldown(store, cooldown_days=30)
    assert not cd.is_on_cooldown("John 3:16")
    assert not cd.is_on_cooldown("Mark 1:1")
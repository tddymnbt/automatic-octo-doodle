"""Tests for the run history / idempotency store."""

import json

import pytest

from src.history.store import (
    STATUS_DRY_RUN,
    STATUS_DUPLICATE,
    STATUS_FAILED,
    STATUS_PUBLISHED,
    HistoryStore,
    RunRecord,
    new_run_id,
)


@pytest.fixture
def store(tmp_path) -> HistoryStore:
    """A HistoryStore backed by a temp directory."""
    return HistoryStore(data_dir=tmp_path)


def test_new_run_id_unique():
    assert new_run_id() != new_run_id()
    assert len(new_run_id()) == 12


class TestRecordRun:
    """Append/persist behavior."""

    def test_record_creates_file(self, store: HistoryStore, tmp_path):
        store.record(story_hash="abc123", status=STATUS_PUBLISHED)
        assert store.path.exists()
        lines = store.path.read_text().strip().splitlines()
        assert len(lines) == 1

    def test_record_appends_not_overwrites(self, store: HistoryStore):
        store.record(story_hash="h1", status=STATUS_PUBLISHED)
        store.record(story_hash="h2", status=STATUS_DUPLICATE)
        lines = store.path.read_text().strip().splitlines()
        assert len(lines) == 2
        records = store.load_history()
        assert [r.story_hash for r in records] == ["h1", "h2"]

    def test_record_fields_persisted(self, store: HistoryStore):
        rec = store.record(
            story_hash="hash9",
            status=STATUS_PUBLISHED,
            story_title="The Title",
            dry_run=False,
            slot="3",
            video_path="output/final.mp4",
            post_id="12345",
            video_id="vid_1",
            attempts=2,
            duration_s=45.5,
            asset_count=8,
            tts_provider="kokoro",
        )
        assert rec.run_id
        assert rec.timestamp
        loaded = store.load_history()[0]
        assert loaded.story_title == "The Title"
        assert loaded.post_id == "12345"
        assert loaded.video_id == "vid_1"
        assert loaded.attempts == 2
        assert loaded.duration_s == 45.5
        assert loaded.asset_count == 8
        assert loaded.tts_provider == "kokoro"
        assert loaded.slot == "3"

    def test_record_slot_defaults_empty(self, store: HistoryStore):
        rec = store.record(story_hash="h", status=STATUS_PUBLISHED)
        assert rec.slot == ""

    def test_no_secrets_in_record(self, store: HistoryStore, tmp_path):
        # The store schema has no secret fields; ensure the dataclass has
        # no token/secret attributes at all.
        import dataclasses

        secret_names = {f.name for f in dataclasses.fields(RunRecord)}
        assert not secret_names.intersection(
            {"access_token", "token", "page_id", "api_key"}
        )

    def test_creates_data_dir(self, tmp_path):
        nested = tmp_path / "a" / "b"
        store = HistoryStore(data_dir=nested)
        store.record(story_hash="h", status=STATUS_PUBLISHED)
        assert nested.exists()


class TestLoadHistory:
    """Reading / tolerance of corrupt lines."""

    def test_empty_when_no_file(self, store: HistoryStore):
        assert store.load_history() == []
        assert store.recent_hashes() == []
        assert store.last_run() is None

    def test_corrupt_line_skipped(self, store: HistoryStore, tmp_path):
        store.path.write_text(
            json.dumps(
                {
                    "run_id": "r1",
                    "timestamp": "t",
                    "story_hash": "good",
                    "status": STATUS_PUBLISHED,
                }
            )
            + "\n"
            + "this is not json\n"
            + json.dumps(
                {
                    "run_id": "r2",
                    "timestamp": "t",
                    "story_hash": "good2",
                    "status": STATUS_DRY_RUN,
                }
            )
            + "\n"
        )
        records = store.load_history()
        assert len(records) == 2
        assert [r.story_hash for r in records] == ["good", "good2"]

    def test_recent_hashes_order(self, store: HistoryStore):
        store.record(story_hash="h1", status=STATUS_PUBLISHED)
        store.record(story_hash="h2", status=STATUS_PUBLISHED)
        store.record(story_hash="h3", status=STATUS_PUBLISHED)
        assert store.recent_hashes() == ["h1", "h2", "h3"]
        assert store.recent_hashes(limit=2) == ["h2", "h3"]

    def test_last_run_returns_most_recent(self, store: HistoryStore):
        store.record(story_hash="h1", status=STATUS_FAILED)
        store.record(story_hash="h2", status=STATUS_PUBLISHED)
        last = store.last_run()
        assert last is not None
        assert last.story_hash == "h2"
        assert last.status == STATUS_PUBLISHED


class TestWasPublished:
    """Duplicate detection semantics."""

    def test_true_after_live_publish(self, store: HistoryStore):
        store.record(story_hash="hashX", status=STATUS_PUBLISHED, dry_run=False)
        assert store.was_published("hashX") is True

    def test_false_for_unpublished_hash(self, store: HistoryStore):
        store.record(story_hash="hashA", status=STATUS_PUBLISHED)
        assert store.was_published("hashB") is False

    def test_dry_run_does_not_block(self, store: HistoryStore):
        store.record(story_hash="hashX", status=STATUS_DRY_RUN, dry_run=True)
        assert store.was_published("hashX") is False

    def test_failed_does_not_block(self, store: HistoryStore):
        store.record(story_hash="hashX", status=STATUS_FAILED)
        assert store.was_published("hashX") is False

    def test_duplicate_skip_does_not_block(self, store: HistoryStore):
        store.record(story_hash="hashX", status=STATUS_DUPLICATE)
        assert store.was_published("hashX") is False

    def test_published_hashes_only_live(self, store: HistoryStore):
        store.record(story_hash="h1", status=STATUS_PUBLISHED, dry_run=False)
        store.record(story_hash="h2", status=STATUS_DRY_RUN, dry_run=True)
        store.record(story_hash="h3", status=STATUS_FAILED)
        assert store.published_hashes() == ["h1"]


class TestDiversityQueries:
    """Rotation/recency queries on stored records."""

    def test_field_sequence_and_last_used(self, store: HistoryStore):
        store.record(
            story_hash="h1", status=STATUS_PUBLISHED, dry_run=False,
            background_used="gospel-01.webp", scripture_book="Matthew",
        )
        store.record(
            story_hash="h2", status=STATUS_PUBLISHED, dry_run=False,
            background_used="gospel-02.webp", scripture_book="Psalm",
        )
        store.record(
            story_hash="h3", status=STATUS_PUBLISHED, dry_run=False,
            background_used="gospel-01.webp", scripture_book="Matthew",
        )
        assert store.field_sequence("background_used") == [
            "gospel-01.webp", "gospel-02.webp", "gospel-01.webp",
        ]
        # gospel-01 last used 0 records back (the most recent).
        assert store.last_used("background_used", "gospel-01.webp") == 0
        assert store.last_used("background_used", "gospel-02.webp") == 1
        # never used -> large
        assert store.last_used("background_used", "never.webp") == 3

    def test_last_used_box_immediate_repeat(self, store: HistoryStore):
        store.record(
            story_hash="h1", status=STATUS_PUBLISHED, dry_run=False,
            ambient_used="piano.wav",
        )
        store.record(
            story_hash="h2", status=STATUS_PUBLISHED, dry_run=False,
            ambient_used="harp.wav",
        )
        assert store.last_used("ambient_used", "piano.wav") == 1  # not adjacent
        store.record(
            story_hash="h3", status=STATUS_PUBLISHED, dry_run=False,
            ambient_used="harp.wav",
        )
        assert store.last_used("ambient_used", "harp.wav") == 0  # just used
        assert store.last_used("ambient_used", "piano.wav") == 2

    def test_field_counts_case_insensitive(self, store: HistoryStore):
        store.record(
            story_hash="h1", status=STATUS_PUBLISHED, dry_run=False,
            scripture_book="Psalm",
        )
        store.record(
            story_hash="h2", status=STATUS_PUBLISHED, dry_run=False,
            scripture_book="psalm",
        )
        store.record(
            story_hash="h3", status=STATUS_PUBLISHED, dry_run=False,
            scripture_book="Matthew",
        )
        assert store.field_counts("scripture_book") == {"psalm": 2, "matthew": 1}

    def test_only_published_filters_dry_runs(self, store: HistoryStore):
        store.record(
            story_hash="h1", status=STATUS_PUBLISHED, dry_run=False,
            background_used="a.webp",
        )
        store.record(
            story_hash="h2", status=STATUS_DRY_RUN, dry_run=True,
            background_used="b.webp",
        )
        store.record(
            story_hash="h3", status=STATUS_PUBLISHED, dry_run=False,
            background_used="c.webp",
        )
        seq_all = store.field_sequence("background_used")
        seq_pub = store.field_sequence("background_used", only_published=True)
        assert seq_all == ["a.webp", "b.webp", "c.webp"]
        assert seq_pub == ["a.webp", "c.webp"]


class TestNewMetadataFields:
    """Phase A metadata round-trips through the store."""

    def test_record_persists_diversity_fields(self, store: HistoryStore):
        rec = store.record(
            story_hash="h", status=STATUS_PUBLISHED, dry_run=False,
            story_text="full narration text here",
            scripture_book="Matthew",
            archetype="scripture_first",
            primary_theme="rest",
            secondary_themes='["rest", "peace"]',
            tone="tender",
            opening_pattern="reflective_question",
            conclusion_pattern="scripture_echo",
            caption_style="verse_first",
            cta_pattern="comment_share",
            key_concepts='["rest", "burden"]',
            background_used="gospel-01.webp",
            ambient_used="piano.wav",
            voice_used="am_fenrir",
        )
        loaded = store.load_history()[0]
        assert loaded.story_text == "full narration text here"
        assert loaded.scripture_book == "Matthew"
        assert loaded.archetype == "scripture_first"
        assert loaded.primary_theme == "rest"
        assert loaded.secondary_themes == '["rest", "peace"]'
        assert loaded.tone == "tender"
        assert loaded.opening_pattern == "reflective_question"
        assert loaded.conclusion_pattern == "scripture_echo"
        assert loaded.caption_style == "verse_first"
        assert loaded.cta_pattern == "comment_share"
        assert loaded.key_concepts == '["rest", "burden"]'
        assert loaded.background_used == "gospel-01.webp"
        assert loaded.ambient_used == "piano.wav"
        assert loaded.voice_used == "am_fenrir"

    def test_legacy_record_loads_with_defaults(self, store: HistoryStore):
        # A record written before the diversity fields existed.
        store.path.write_text(
            '{"run_id":"r1","timestamp":"t","story_hash":"h1","status":"published","dry_run":false}\n',
            encoding="utf-8",
        )
        rec = store.load_history()[0]
        assert rec.archetype == ""
        assert rec.story_text == ""
        assert rec.background_used == ""
        assert rec.voice_used == ""


class TestRunRecordDataclass:
    """RunRecord serialization."""

    def test_to_dict(self):
        r = RunRecord(
            run_id="rid",
            timestamp="ts",
            story_hash="hash",
            status=STATUS_PUBLISHED,
            story_title="T",
            dry_run=False,
            slot="2",
            video_path="v",
            post_id="p",
            video_id="vid",
            error="",
            attempts=1,
            duration_s=1.0,
            asset_count=1,
            tts_provider="k",
        )
        d = r.to_dict()
        assert d["run_id"] == "rid"
        assert d["story_hash"] == "hash"
        assert d["post_id"] == "p"
        assert d["slot"] == "2"
        assert "access_token" not in d

    def test_roundtrip(self, store: HistoryStore):
        store.record(
            story_hash="h",
            status=STATUS_PUBLISHED,
            story_title="My Story",
            post_id="998",
        )
        rec = store.load_history()[0]
        assert rec.story_title == "My Story"
        assert rec.post_id == "998"
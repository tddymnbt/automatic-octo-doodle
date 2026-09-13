"""Tests for content diversity helpers ($0 semantic-ish + rotation scoring)."""

import random

from src.content.diversity import (
    jaccard_similarity,
    max_jaccard,
    ngram_set,
    normalize_text,
    parse_scripture_book,
    recency_index,
    select_lsru,
)


class TestParseScriptureBook:
    def test_single_book(self):
        assert parse_scripture_book("Matthew 11:28") == "Matthew"

    def test_multi_word_book(self):
        assert parse_scripture_book("1 Corinthians 13:4") == "1 Corinthians"

    def test_verse_range(self):
        assert parse_scripture_book("Psalm 23:1-4") == "Psalm"

    def test_unparsable_returns_empty(self):
        assert parse_scripture_book("just a book") == ""
        assert parse_scripture_book("") == ""


class TestNormalizeAndNgrams:
    def test_normalize_strips_punct_and_case(self):
        assert normalize_text("Hello, WORLD!!  How are you?") == "hello world how are you"

    def test_ngram_set_counts(self):
        grams = ngram_set("the cat sat on the mat", n=3)
        assert len(grams) == 4  # the-cat-sat, cat-sat-on, sat-on-the, on-the-mat

    def test_identical_texts_similarity_one(self):
        assert jaccard_similarity(ngram_set("a b c d"), ngram_set("a b c d")) == 1.0

    def test_disjoint_texts_low_similarity(self):
        a = ngram_set("completely different passage about grace")
        b = ngram_set("alpha beta gamma delta epsilon zeta")
        assert jaccard_similarity(a, b) < 0.3

    def test_max_jaccard_finds_best_candidate(self):
        text = "God is our refuge and strength"
        candidates = [
            "God is our refuge and strength always",
            "totally unrelated sentence",
        ]
        assert max_jaccard(text, candidates) > 0.5


class TestRecencyIndex:
    def test_most_recent_is_zero(self):
        assert recency_index(["a", "b", "c"], "c") == 0

    def test_older_is_higher(self):
        assert recency_index(["a", "b", "c"], "a") == 2

    def test_absent_is_length(self):
        seq = ["a", "b"]
        assert recency_index(seq, "z") == 2


class TestSelectLsru:
    def test_avoids_immediate_repeat(self):
        rng = random.Random(0)
        # 'a' was just used -> must NOT be selected next (min_spacing=1).
        pick = select_lsru(["a", "b", "c"], recent_keys=["a"], rng=rng)
        assert pick != "a"

    def test_respects_multiple_spacing(self):
        rng = random.Random(1)
        recent = ["a", "b"]
        pick = select_lsru(["a", "b", "c"], recent_keys=recent, min_spacing=2, rng=rng)
        assert pick not in ("a", "b")

    def test_prefers_underused_for_coverage(self):
        rng = random.Random(2)
        # counts heavily favour 'a'; with enough iterations 'a' should never win.
        counts = {"a": 100, "b": 1, "c": 1}
        wins = set()
        for _ in range(50):
            pick = select_lsru(
                ["a", "b", "c"], recent_keys=[], counts=counts, rng=rng,
            )
            wins.add(pick)
        assert wins <= {"b", "c"}

    def test_tight_library_falls_back_to_random(self):
        rng = random.Random(3)
        # Only one option within spacing -> falls back (never asserts/stalls).
        pick = select_lsru(["a"], recent_keys=["a"], min_spacing=2, rng=rng)
        assert pick == "a"
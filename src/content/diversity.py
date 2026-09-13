"""Content diversity utilities for the Daily Bread pipeline.

This module provides $0, stdlib-only helpers used across the diversity
system:

* Scripture reference parsing (derive the book from a reference).
* Lightweight text normalization + n-gram (Jaccard) similarity for
  near-duplicate detection. No embeddings, no external services.
* Weighted "least-recently-used + coverage" selection scoring, used both
  for content dimensions (archetype / theme / book) and, via
  ``src/assets/selector.py``, for image and sound rotation.

These helpers are pure and deterministic except where randomness is
deliberately injected via an optional ``rng`` so the sequence is not
predictable.
"""

from __future__ import annotations

import random
import re
from collections.abc import Iterable, Sequence

# ---------------------------------------------------------------------------
# Scripture parsing
# ---------------------------------------------------------------------------


# Content archetypes (Phase C). Each is a distinct creative starting point so
# the pipeline is theme/principle-driven, NOT a fixed problem taxonomy.
ARCHETYPES: tuple[str, ...] = (
    "biblical_reflection",
    "everyday_observation",
    "character_story",
    "spiritual_principle",
    "question_reflection",
    "scripture_first",
    "seasonal_contextual",
)

# Restrained spiritual-principle vocabulary. This is NOT an exhaustive list of
# human problems — it is a coverable theme space that rotates. Problems (like
# anxiety) can still surface naturally but are never the primary mechanism.
PRINCIPLES: tuple[str, ...] = (
    "patience",
    "grace",
    "obedience",
    "forgiveness",
    "gratitude",
    "humility",
    "perseverance",
    "wisdom",
    "trust",
    "hope",
    "service",
    "compassion",
    "contentment",
    "repentance",
    "faithfulness",
    "rest",
    "peace",
    "love",
    "courage",
    "joy",
)

# Default archetype -> preferred principles (a hint, not a hard lock).
ARCHETYPE_PRINCIPLES: dict[str, tuple[str, ...]] = {
    "spiritual_principle": PRINCIPLES,
    "biblical_reflection": PRINCIPLES,
    "scripture_first": PRINCIPLES,
    "character_story": ("faithfulness", "courage", "obedience", "trust", "perseverance"),
    "everyday_observation": ("gratitude", "contentment", "compassion", "service", "joy"),
    "question_reflection": ("trust", "hope", "wisdom", "peace"),
    "seasonal_contextual": ("gratitude", "hope", "grace", "peace"),
}


# ================================================================
# SLOT STRATIFICATION (Phase G)
# Each of the 5 daily slots gets a slight bias so the day naturally
# spreads across different archetypes and principles.
# ================================================================

# Slot -> archetype bias (first element is primary, others are alternates)
SLOT_ARCHETYPE_BIAS: dict[str, tuple[str, ...]] = {
    "1": ("spiritual_principle", "scripture_first", "biblical_reflection"),
    "2": ("everyday_observation", "question_reflection", "seasonal_contextual"),
    "3": ("character_story", "spiritual_principle", "scripture_first"),
    "4": ("question_reflection", "everyday_observation", "seasonal_contextual"),
    "5": ("scripture_first", "biblical_reflection", "character_story"),
}

# Slot -> principle bias (first is primary)
SLOT_PRINCIPLE_BIAS: dict[str, tuple[str, ...]] = {
    "1": ("trust", "faithfulness", "rest"),
    "2": ("gratitude", "contentment", "peace"),
    "3": ("courage", "perseverance", "hope"),
    "4": ("wisdom", "patience", "humility"),
    "5": ("grace", "love", "joy"),
}


def select_with_slot_bias(
    options: Sequence[str],
    recent_keys: Sequence[str],
    counts: dict[str, int] | None = None,
    *,
    slot: str = "1",
    slot_bias: dict[str, tuple[str, ...]] | None = None,
    min_spacing: int = 1,
    recency_weight: float = 2.0,
    coverage_weight: float = 0.8,
    rng: random.Random | None = None,
) -> str:
    """LSUR selection with slot-aware bias.

    If ``slot_bias`` provides a preferred sequence for the slot, those options
    get a score boost (so the slot tends toward its bias) but LSUR + coverage
    still apply so the slot doesn't lock into a single option forever.
    """
    rng = rng or random.Random()
    counts = counts or {}
    option_count = max(1, len(options))
    space = max(1, min_spacing)

    # Build bias scores (higher = more preferred)
    bias_scores: dict[str, float] = {}
    if slot_bias:
        bias_list = slot_bias.get(str(slot), ())
        for i, key in enumerate(bias_list):
            if key in options:
                bias_scores[key] = max(0.0, 1.0 - i * 0.2)

    candidates: list[tuple[str, float]] = []
    for key in options:
        rec = recency_index(recent_keys, key)
        if rec < space and rec != len(recent_keys):
            continue
        normalized_recency = rec / space
        normalized_coverage = counts.get(key, 0) / option_count
        bias = bias_scores.get(key, 0.0)
        score = (
            recency_weight * normalized_recency
            - coverage_weight * normalized_coverage
            + 0.8 * bias
            + (rng.random() * 0.3)
        )
        candidates.append((key, score))

    if not candidates:
        return rng.choice(list(options))

    candidates.sort(key=lambda pair: -pair[1])
    return candidates[0][0]


# ================================================================
# STRUCTURE PATTERN VOCABULARIES (Phase D)
# These classifier tags rotate so the *structure* of each piece varies.
# ================================================================

OPENING_PATTERNS: tuple[str, ...] = (
    "reflective_question",
    "declarative_truth",
    "everyday_scene",
    "character_intro",
    "scripture_echo",
    "personal_invitation",
    "seasonal_marker",
    "gentle_observation",
)

CONCLUSION_PATTERNS: tuple[str, ...] = (
    "scripture_echo",
    "personal_challenge",
    "communal_affirmation",
    "prayerful_sending",
    "practice_invitation",
    "question_linger",
    "declaration_trust",
)

CAPTION_STYLES: tuple[str, ...] = (
    "verse_first",
    "question_first",
    "observation_first",
    "principle_first",
    "testimony_style",
    "devotional_style",
)

CTA_PATTERNS: tuple[str, ...] = (
    "comment_share",
    "reflection_prompt",
    "affirm_truth",
    "share_testimony",
    "notice_god",
    "identify_character",
    "trust_prompt",
    "pursue_principle",
    "answer_question",
    "meditate_verse",
    "declare_truth",
    "seasonal_practice",
)


def parse_scripture_book(reference: str) -> str:
    """Return the Bible book name from a reference string.

    Examples:
        "Matthew 11:28"       -> "Matthew"
        "Psalm 23:1-4"        -> "Psalm"
        "1 Corinthians 13:4"  -> "1 Corinthians"
        "Philippians 4:6-7"   -> "Philippians"

    Returns an empty string if the reference has no recognizable
    ``Chapter:Verse`` tail (e.g. a bare book name).
    """
    ref = (reference or "").strip()
    match = re.match(r"^([A-Za-z0-9]+\s?[A-Za-z]+)\s+\d+:", ref)
    if not match:
        return ""
    book = match.group(1).strip()
    # Keep letters and an optional leading ordinal syllable (1/2/3).
    return book


# ---------------------------------------------------------------------------
# Text normalization + n-gram similarity ($0 near-duplicate detection)
# ---------------------------------------------------------------------------


def normalize_text(text: str) -> str:
    """Lowercase, strip punctuation, and collapse whitespace."""
    lowered = (text or "").lower()
    spaced = re.sub(r"[^a-z0-9\s]", " ", lowered)
    return re.sub(r"\s+", " ", spaced).strip()


def ngram_set(text: str, n: int = 3) -> set[tuple[str, ...]]:
    """Return the set of word n-grams for a text.

    ``normalize_text`` is applied first so punctuation and case do not
    affect similarity. ``n`` defaults to 3 (word trigrams); the caller
    may drop to 2 for shorter fields like captions.
    """
    tokens = normalize_text(text).split()
    grams: set[tuple[str, ...]] = set()
    for i in range(len(tokens) - n + 1):
        grams.add(tuple(tokens[i : i + n]))
    return grams


def jaccard_similarity(grams_a: set, grams_b: set) -> float:
    """Jaccard similarity between two n-gram sets (0.0 to 1.0)."""
    if not grams_a and not grams_b:
        return 0.0
    union = grams_a | grams_b
    if not union:
        return 0.0
    return len(grams_a & grams_b) / len(union)


def max_jaccard(text: str, candidates: Iterable[str], n: int = 3) -> float:
    """Return the highest Jaccard similarity of ``text`` vs any candidate."""
    gram_set = ngram_set(text, n)
    best = 0.0
    for candidate in candidates:
        if not candidate:
            continue
        best = max(best, jaccard_similarity(gram_set, ngram_set(candidate, n)))
    return best


# ---------------------------------------------------------------------------
# Weighted least-recently-used + coverage selection
# ---------------------------------------------------------------------------


def recency_index(recent_keys: Sequence[str], key: str) -> int:
    """Return how far back ``key`` was last seen in ``recent_keys``.

    0 = the most recent element; ``len(recent_keys)`` = not present at all
    (treated as "loved/forgotten", i.e. extremely distant).
    """
    last = len(recent_keys)
    for i, recent in enumerate(reversed(recent_keys)):
        if recent == key:
            last = i
            break
    return last


def select_lsru(
    options: Sequence[str],
    recent_keys: Sequence[str],
    counts: dict[str, int] | None = None,
    *,
    min_spacing: int = 1,
    recency_weight: float = 2.0,
    coverage_weight: float = 0.8,
    rng: random.Random | None = None,
) -> str:
    """Select an option using least-recently-used + coverage weighting.

    Scoring (higher wins):
        score = recency_weight * normalized_recency
                - coverage_weight * normalized_coverage
                + epsilon * rng.random()

    * ``min_spacing``: hard-excludes any option seen within the last
      ``min_spacing`` selections (the immediate-repeat prevention).
    * ``normalized_recency`` = recency_index / max(1, min_spacing): options
      further back get a larger boost.
    * ``normalized_coverage`` = usage / len(options): under-used options get
      a smaller penalty, so the whole collection eventually circulates.
    * ``epsilon``: small random jitter keeps the order from being a
      predictable in-order rotation.

    If every option is within ``min_spacing`` (a too-tight library), it
    loosens to a random pick among all options rather than failing.
    """
    rng = rng or random.Random()
    counts = counts or {}
    option_count = max(1, len(options))
    space = max(1, min_spacing)

    candidates: list[tuple[str, float]] = []
    for key in options:
        rec = recency_index(recent_keys, key)
        if rec < space and rec != len(recent_keys):
            # Too recent — enforce the immediate-repeat rule.
            continue
        normalized_recency = rec / space
        normalized_coverage = counts.get(key, 0) / option_count
        score = (
            recency_weight * normalized_recency
            - coverage_weight * normalized_coverage
            + (rng.random() * 0.3)
        )
        candidates.append((key, score))

    if not candidates:
        # Tight library: fall back to a plain random pick so callers always
        # get a result (never block a slot on asset rotation).
        return rng.choice(list(options))

    candidates.sort(key=lambda pair: -pair[1])
    return candidates[0][0]


def select_opening_pattern(
    recent_openings: Sequence[str],
    counts: dict[str, int] | None = None,
    rng: random.Random | None = None,
) -> str:
    """Select an opening pattern using LSUR rotation."""
    return select_lsru(
        OPENING_PATTERNS,
        recent_openings,
        counts,
        min_spacing=2,
        recency_weight=1.5,
        coverage_weight=1.0,
        rng=rng,
    )


def select_conclusion_pattern(
    recent_conclusions: Sequence[str],
    counts: dict[str, int] | None = None,
    rng: random.Random | None = None,
) -> str:
    """Select a conclusion pattern using LSUR rotation."""
    return select_lsru(
        CONCLUSION_PATTERNS,
        recent_conclusions,
        counts,
        min_spacing=2,
        recency_weight=1.5,
        coverage_weight=1.0,
        rng=rng,
    )


def select_caption_style(
    recent_styles: Sequence[str],
    counts: dict[str, int] | None = None,
    rng: random.Random | None = None,
) -> str:
    """Select a caption style using LSUR rotation."""
    return select_lsru(
        CAPTION_STYLES,
        recent_styles,
        counts,
        min_spacing=2,
        recency_weight=1.5,
        coverage_weight=1.0,
        rng=rng,
    )


def select_cta_pattern(
    recent_ctas: Sequence[str],
    counts: dict[str, int] | None = None,
    rng: random.Random | None = None,
) -> str:
    """Select a CTA pattern using LSUR rotation."""
    return select_lsru(
        CTA_PATTERNS,
        recent_ctas,
        counts,
        min_spacing=2,
        recency_weight=1.5,
        coverage_weight=1.0,
        rng=rng,
    )
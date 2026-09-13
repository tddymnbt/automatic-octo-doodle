"""Long-run coverage simulation tests (Phase G)."""

import random

from src.content.diversity import (
    ARCHETYPES,
    PRINCIPLES,
    SLOT_ARCHETYPE_BIAS,
    SLOT_PRINCIPLE_BIAS,
    select_lsru,
    select_with_slot_bias,
)


def simulate_slot_runs(
    slot: str,
    archetype_bias: dict[str, tuple[str, ...]],
    principle_bias: dict[str, tuple[str, ...]],
    num_runs: int = 200,
) -> tuple[dict[str, int], dict[str, int]]:
    """Simulate many runs for a single slot and return archetype/theme counts."""
    rng = random.Random(slot)  # deterministic per slot
    archetype_counts = {a: 0 for a in ARCHETYPES}
    principle_counts = {p: 0 for p in PRINCIPLES}

    for _ in range(num_runs):
        # Archetype selection
        arch_recent = [a for a, c in archetype_counts.items() for _ in range(c)]
        rng.shuffle(arch_recent)
        archetype = select_with_slot_bias(
            ARCHETYPES,
            recent_keys=arch_recent[-20:],
            counts=archetype_counts,
            slot=slot,
            slot_bias=archetype_bias,
            rng=rng,
        )
        archetype_counts[archetype] += 1

        # Principle selection within archetype
        principles = [p for p in PRINCIPLES if p in archetype_counts] or list(PRINCIPLES)
        # In real code, principles are filtered by ARCHETYPE_PRINCIPLES, but for
        # this simulation we just test the slot-bias function works.
        theme_recent = [p for p, c in principle_counts.items() for _ in range(c)]
        rng.shuffle(theme_recent)
        principle = select_with_slot_bias(
            PRINCIPLES,
            recent_keys=theme_recent[-10:],
            counts=principle_counts,
            slot=slot,
            slot_bias=principle_bias,
            rng=rng,
        )
        principle_counts[principle] += 1

    return archetype_counts, principle_counts


class TestSlotStratification:
    """Verify each slot naturally biases toward its configured archetypes/principles."""

    def test_slot_1_bias_spiritual_principle(self):
        """Slot 1 should favor spiritual_principle / scripture_first."""
        archetype_counts, principle_counts = simulate_slot_runs(
            "1", SLOT_ARCHETYPE_BIAS, SLOT_PRINCIPLE_BIAS, num_runs=100
        )
        # Slot 1 bias: spiritual_principle, scripture_first, biblical_reflection
        top_archetypes = sorted(archetype_counts.keys(), key=lambda k: archetype_counts[k], reverse=True)[:3]
        assert "spiritual_principle" in top_archetypes
        assert "scripture_first" in top_archetypes or "biblical_reflection" in top_archetypes

        # Principle bias: trust, faithfulness, rest
        top_principles = sorted(principle_counts.keys(), key=lambda k: principle_counts[k], reverse=True)[:4]
        assert "trust" in top_principles or "faithfulness" in top_principles

    def test_slot_2_bias_everyday_observation(self):
        """Slot 2 should favor everyday_observation / question_reflection."""
        archetype_counts, principle_counts = simulate_slot_runs(
            "2", SLOT_ARCHETYPE_BIAS, SLOT_PRINCIPLE_BIAS, num_runs=200
        )
        # Slot 2 bias: everyday_observation is first in the bias list.
        # With LSUR + coverage, the bias gives a boost but doesn't guarantee #1.
        # Check it's in the top 4 (out of 7 archetypes) — a meaningful preference.
        top_archetypes = sorted(archetype_counts.keys(), key=lambda k: archetype_counts[k], reverse=True)[:4]
        assert "everyday_observation" in top_archetypes, f"Top 4: {top_archetypes}"

        # Principle bias: gratitude, contentment, peace
        top_principles = sorted(principle_counts.keys(), key=lambda k: principle_counts[k], reverse=True)[:5]
        # With slot bias, gratitude or contentment should rank highly
        assert "gratitude" in top_principles or "contentment" in top_principles, f"Top 5: {top_principles}"

    def test_all_slots_differ(self):
        """Each slot should have a different top archetype over many runs."""
        slot_tops = {}
        for slot in ["1", "2", "3", "4", "5"]:
            counts, _ = simulate_slot_runs(
                slot, SLOT_ARCHETYPE_BIAS, SLOT_PRINCIPLE_BIAS, num_runs=100
            )
            top = max(counts.keys(), key=lambda k: counts[k])
            slot_tops[slot] = top

        # All 5 slots should ideally have different top archetypes
        # (At minimum, no more than 2 slots should share the same top)
        from collections import Counter

        top_distribution = Counter(slot_tops.values())
        for count in top_distribution.values():
            assert count <= 2, f"Top archetypes too concentrated: {slot_tops}"

    def test_coverage_over_long_run(self):
        """Over many runs, all archetypes and principles should be used at least once."""
        rng = random.Random(0)
        archetype_counts = {a: 0 for a in ARCHETYPES}
        principle_counts = {p: 0 for p in PRINCIPLES}

        # Simulate 500 runs across all slots (100 per slot)
        for slot in ["1", "2", "3", "4", "5"]:
            for _ in range(100):
                arch_recent = [a for a, c in archetype_counts.items() for _ in range(c)]
                rng.shuffle(arch_recent)
                archetype = select_with_slot_bias(
                    ARCHETYPES,
                    recent_keys=arch_recent[-20:],
                    counts=archetype_counts,
                    slot=slot,
                    slot_bias=SLOT_ARCHETYPE_BIAS,
                    rng=rng,
                )
                archetype_counts[archetype] += 1

                theme_recent = [p for p, c in principle_counts.items() for _ in range(c)]
                rng.shuffle(theme_recent)
                principle = select_with_slot_bias(
                    PRINCIPLES,
                    recent_keys=theme_recent[-10:],
                    counts=principle_counts,
                    slot=slot,
                    slot_bias=SLOT_PRINCIPLE_BIAS,
                    rng=rng,
                )
                principle_counts[principle] += 1

        # Every archetype should appear at least a few times
        for a in ARCHETYPES:
            assert archetype_counts[a] > 0, f"Archetype {a} never used"

        # Every principle should appear at least a few times
        for p in PRINCIPLES:
            assert principle_counts[p] > 0, f"Principle {p} never used"


class TestSelectWithSlotBias:
    """Unit tests for select_with_slot_bias."""

    def test_bias_boosts_preferred(self):
        """Preferred options in bias list should be selected more often."""
        rng = random.Random(42)
        options = ["a", "b", "c"]
        # Light usage so recency/coverage don't overwhelm bias
        # "a" is NOT in recent so min_spacing doesn't exclude it
        counts = {"a": 1, "b": 0, "c": 0}
        recent = ["b"]  # "a" is not recent

        # With bias for 'a', it should win despite light recency/coverage
        bias = {"1": ("a",)}
        pick = select_with_slot_bias(
            options, recent, counts, slot="1", slot_bias=bias, rng=rng
        )
        assert pick == "a"

    def test_no_bias_uses_lsur(self):
        """When no bias provided, behaves like select_lsru."""
        rng = random.Random(42)
        options = ["x", "y", "z"]
        counts = {"x": 5, "y": 0, "z": 0}
        recent = ["x"] * 5

        pick1 = select_with_slot_bias(options, recent, counts, slot="9", rng=rng)
        rng2 = random.Random(42)
        pick2 = select_lsru(options, recent, counts, rng=rng2)

        assert pick1 == pick2  # Same logic, same seed


class TestDiversityCoverage:
    """Coverage tests for structure patterns and CTA patterns."""

    def test_opening_patterns_coverable(self):
        """All opening patterns can be selected."""
        from src.content.diversity import OPENING_PATTERNS, select_opening_pattern

        rng = random.Random(0)
        counts = {p: 0 for p in OPENING_PATTERNS}
        recent = []
        for _ in range(50):
            pick = select_opening_pattern(recent, counts=counts, rng=rng)
            counts[pick] += 1
            recent.append(pick)

        # All 8 patterns should appear at least once in 50 runs
        assert all(c > 0 for c in counts.values())

    def test_conclusion_patterns_coverable(self):
        """All conclusion patterns can be selected."""
        from src.content.diversity import CONCLUSION_PATTERNS, select_conclusion_pattern

        rng = random.Random(1)
        counts = {p: 0 for p in CONCLUSION_PATTERNS}
        recent = []
        for _ in range(40):
            pick = select_conclusion_pattern(recent, counts=counts, rng=rng)
            counts[pick] += 1
            recent.append(pick)

        assert all(c > 0 for c in counts.values())

    def test_caption_styles_coverable(self):
        """All caption styles can be selected."""
        from src.content.diversity import CAPTION_STYLES, select_caption_style

        rng = random.Random(2)
        counts = {p: 0 for p in CAPTION_STYLES}
        recent = []
        for _ in range(30):
            pick = select_caption_style(recent, counts=counts, rng=rng)
            counts[pick] += 1
            recent.append(pick)

        assert all(c > 0 for c in counts.values())

    def test_cta_patterns_coverable(self):
        """All CTA patterns can be selected."""
        from src.content.diversity import CTA_PATTERNS, select_cta_pattern

        rng = random.Random(3)
        counts = {p: 0 for p in CTA_PATTERNS}
        recent = []
        for _ in range(60):
            pick = select_cta_pattern(recent, counts=counts, rng=rng)
            counts[pick] += 1
            recent.append(pick)

        assert all(c > 0 for c in counts.values())
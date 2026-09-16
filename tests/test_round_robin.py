"""Tests for strict full-cycle (round-robin) asset selection."""
import random

from src.content.diversity import select_round_robin


def test_unused_options_picked_first():
    """All options used before any repeats."""
    options = ["a", "b", "c"]
    recent = ["a"]
    # 'b'/'c' never used -> one of them must be chosen (not 'a' again)
    assert select_round_robin(options, recent) in {"b", "c"}


def test_midcycle_picks_least_recent_used():
    """After using a,b it should pick c then recycle oldest first."""
    options = ["a", "b", "c"]
    # Used a then b; neither ever repeated.
    assert select_round_robin(options, ["a", "b"]) == "c"
    # Now all used: oldest (a, used first) should be recycled first.
    assert select_round_robin(options, ["a", "b", "c"]) == "a"


def test_never_used_beats_oldest_used():
    """Unused option outranks an old-but-used one."""
    options = ["a", "b"]
    recent = ["a", "a", "a"]
    # b never used -> pick b
    assert select_round_robin(options, recent) == "b"


def test_empty_options():
    assert select_round_robin([], ["a"]) == ""


def test_not_in_recent_key_is_prioritized():
    """Key not appearing anywhere in recent_keys counts as never-used."""
    options = ["x", "y"]
    recent = ["z"]
    # x and y both never used -> list-order tiebreak picks first available 'x'
    assert select_round_robin(options, recent) == "x"


def test_deterministic_for_ties():
    """When multiple options equally recent, deterministic by list order."""
    rng = random.Random(42)
    options = ["p", "q", "r"]
    assert select_round_robin(options, [], rng) == "p"
    assert select_round_robin(options, [], rng) == "p"
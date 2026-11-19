"""Unit tests for the row coherence heuristic (Requirement 11)."""

from itertools import combinations

import pytest

from necropsy.engine.coherence import (
    COHERENCE_SIZE_LIMIT,
    coherence_gap,
    pair_at,
    row_coherence,
)


def test_hand_computed_three_rows():
    # Rows [0,0], [10,10], [30,30]; row MAD = mean |x - y| over the 2 columns.
    # adjacent: (0,1)=10, (1,2)=20 -> (10+20)/2 = 15
    # baseline over all pairs: (0,1)=10, (0,2)=30, (1,2)=20 -> 60/3 = 20
    # score = 15 / 20 = 0.75
    score, status = row_coherence(bytes([0, 0, 10, 10, 30, 30]), 3, 2)
    assert status == "scored"
    assert score == pytest.approx(0.75)


def test_identical_rows_unscorable():
    assert row_coherence(bytes([7, 7, 7]) * 4, 4, 3) == (None, "unscorable")


def test_one_row_unscorable():
    assert row_coherence(bytes([1, 2, 3]), 1, 3) == (None, "unscorable")


def test_over_size_limit_not_computed():
    assert COHERENCE_SIZE_LIMIT == 262_144
    # 262,145 expected bytes: height 262145 x stride 1.
    assert row_coherence(b"", 262_145, 1) == (None, "not_computed")


def test_sampling_is_deterministic_and_pair_at_matches_enumeration():
    height, stride = 50, 4  # 1,225 pairs > 1,024
    data = bytes((i * 37 + (i // stride) * 11) % 256 for i in range(height * stride))
    first = row_coherence(data, height, stride)
    assert first[1] == "scored"
    assert row_coherence(data, height, stride) == first

    expected = list(combinations(range(height), 2))
    assert len(expected) > 1024
    for k, pair in enumerate(expected):
        assert pair_at(k, height) == pair


def test_pair_at_small_heights():
    for h in (2, 3, 7):
        assert [pair_at(k, h) for k in range(h * (h - 1) // 2)] == list(combinations(range(h), 2))


def test_gap_two_scores():
    assert coherence_gap([0.2, 0.25]) == pytest.approx(0.2)


def test_gap_fewer_than_two_scores_is_none():
    assert coherence_gap([]) is None
    assert coherence_gap([0.5]) is None
    assert coherence_gap([0.5, None]) is None


def test_gap_second_lowest_zero_is_none():
    assert coherence_gap([0.0, 0.0, 0.3]) is None


def test_docstring_states_failure_modes():
    doc = " ".join((row_coherence.__doc__ or "").split())
    assert "Narrower strides score better" in doc
    assert "Identical bytes at an identical stride" in doc
    assert "different bit depths" in doc
    assert "A header can absorb whole rows" in doc

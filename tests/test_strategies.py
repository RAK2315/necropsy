"""Unit tests for revision strategies (Requirement 3.1).

Every expected value below is derived from requirements.md Requirement 3.1
and Decision Record item 5, or from design.md "Data Models". None is read
from the implementation.
"""

from dataclasses import replace

import pytest
from hypothesis import given, settings, strategies as st

from necropsy.engine.strategies import (
    STRATEGIES,
    inclusive_bounds,
    row_padding_variants,
    rle_pcx,
)
from necropsy.engine.types import FieldRecord, Hypothesis


def _pcx(**kw):
    """A PCX-origin hypothesis with every field set to a non-default value,
    so a strategy that disturbs an unrelated field is detected."""
    base = dict(
        width=5, height=6, bit_depth=8, header_size=128, row_alignment=1,
        encoding="none", data_end=999,
        fields=(FieldRecord("xmax", 0x08, "<H", (7,)),),
        probe_name="pcx", bounds=(2, 3, 9, 12), revision_path=("earlier",),
    )
    base.update(kw)
    return Hypothesis(**base)


def _by_name(name):
    return dict(STRATEGIES)[name]


# ---- Req 3.1 / Decision Record item 5: exactly three strategies, in order

def test_strategy_names_exact():
    # Req 3.1 "exactly three revision strategies", listed order.
    assert tuple(n for n, _ in STRATEGIES) == (
        "inclusive_bounds", "rle_pcx", "row_padding_variants")


# ---- Req 3.1 inclusive_bounds

def test_inclusive_bounds_zero_origin_gives_8x8():
    # Req 3.1 inclusive_bounds: width = xmax - xmin + 1 = 7 - 0 + 1 = 8,
    # height = ymax - ymin + 1 = 7 - 0 + 1 = 8.
    out = inclusive_bounds(_pcx(bounds=(0, 0, 7, 7)))
    assert len(out) == 1
    assert (out[0].width, out[0].height) == (8, 8)


def test_inclusive_bounds_nonzero_origin():
    # Req 3.1 inclusive_bounds with bounds (2, 3, 9, 12):
    # width = 9 - 2 + 1 = 8; height = 12 - 3 + 1 = 10.
    out = inclusive_bounds(_pcx())
    assert len(out) == 1
    assert (out[0].width, out[0].height) == (8, 10)


def test_inclusive_bounds_without_bounds_is_empty():
    # Req 3.1 "applies only to hypotheses with bounds set".
    assert inclusive_bounds(_pcx(bounds=None)) == ()


# ---- Req 3.1 rle_pcx

def test_rle_pcx_from_pcx_none_gives_rle_pcx():
    # Req 3.1 rle_pcx: PCX origin, encoding "none" -> one candidate "rle_pcx".
    out = rle_pcx(_pcx(encoding="none"))
    assert len(out) == 1
    assert out[0].encoding == "rle_pcx"


def test_rle_pcx_not_for_tga():
    # Req 3.1 rle_pcx: "only to hypotheses from the PCX probe".
    assert rle_pcx(_pcx(probe_name="tga", bounds=None)) == ()


def test_rle_pcx_already_rle_is_empty():
    # Req 3.1 rle_pcx: only when encoding == "none".
    assert rle_pcx(_pcx(encoding="rle_pcx")) == ()


# ---- Req 3.1 row_padding_variants

def test_row_padding_from_1_gives_2_then_4():
    # Req 3.1: one candidate per alignment in (2, 4) differing from current,
    # in that order. Current 1 -> (2, 4).
    out = row_padding_variants(_pcx(row_alignment=1))
    assert tuple(c.row_alignment for c in out) == (2, 4)


def test_row_padding_from_4_gives_2():
    # Req 3.1: current 4 excluded -> (2,).
    out = row_padding_variants(_pcx(row_alignment=4))
    assert tuple(c.row_alignment for c in out) == (2,)


def test_row_padding_from_2_gives_4():
    # Req 3.1: current 2 excluded -> (4,).
    out = row_padding_variants(_pcx(row_alignment=2))
    assert tuple(c.row_alignment for c in out) == (4,)


# ---- Req 3.1 revision_path and "every other field unchanged"

@pytest.mark.parametrize("name", [n for n, _ in STRATEGIES])
def test_revision_path_is_parent_path_plus_name_and_parent_unchanged(name):
    # Req 3.1: "each candidate's revision_path is its parent's path plus
    # the strategy name".
    parent = _pcx()
    snapshot = _pcx()
    cands = _by_name(name)(parent)
    assert cands, name  # the parent above is applicable to every strategy
    for c in cands:
        assert c.revision_path == ("earlier", name)
    assert parent == snapshot


def test_inclusive_bounds_changes_only_width_height_and_path():
    # Req 3.1 inclusive_bounds "produces one candidate with width = ... and
    # height = ...": nothing else changes. 9-2+1 = 8, 12-3+1 = 10.
    p = _pcx()
    (c,) = inclusive_bounds(p)
    assert c == replace(p, width=8, height=10,
                        revision_path=("earlier", "inclusive_bounds"))


def test_rle_pcx_changes_only_encoding_and_path():
    # Req 3.1 rle_pcx "produces one candidate with encoding = rle_pcx".
    p = _pcx()
    (c,) = rle_pcx(p)
    assert c == replace(p, encoding="rle_pcx",
                        revision_path=("earlier", "rle_pcx"))


def test_row_padding_changes_only_alignment_and_path():
    # Req 3.1 row_padding_variants: one candidate per alignment in (2, 4).
    p = _pcx(row_alignment=1)
    out = row_padding_variants(p)
    assert out == tuple(
        replace(p, row_alignment=a,
                revision_path=("earlier", "row_padding_variants"))
        for a in (2, 4))


# Feature: structure-inference-engine, Strategy never raises
_ints = st.integers(min_value=-(10 ** 30), max_value=10 ** 30)
_hypotheses = st.builds(
    Hypothesis,
    width=_ints,
    height=_ints,
    bit_depth=_ints,
    header_size=_ints,
    row_alignment=_ints,
    encoding=st.sampled_from(["none", "rle_pcx", "rle_tga"]),
    data_end=st.none() | _ints,
    probe_name=st.sampled_from(["pcx", "tga", "pbm", "tiff", "generic"]),
    bounds=st.none() | st.tuples(_ints, _ints, _ints, _ints),
)


@settings(max_examples=100)
@given(h=_hypotheses)
def test_each_strategy_never_raises(h):
    """Feature: structure-inference-engine, Strategy never raises.

    **Validates: Requirements 6.4, 6.7**
    """
    for name, fn in STRATEGIES:
        out = fn(h)
        assert isinstance(out, tuple), name
        assert all(isinstance(c, Hypothesis) for c in out), name


# ---- Task 14 (format-coverage), Requirements 6.5, 6.8

def test_row_padding_guarded_when_row_bytes_set():
    # Req 6.5: declared row bytes -> no padding candidate, at any alignment.
    for a in (1, 2, 4):
        assert row_padding_variants(_pcx(row_alignment=a, row_bytes=210, planes=3)) == ()


def test_row_padding_unguarded_when_row_bytes_unset():
    # Req 6.8: single-plane (row_bytes None) results are unchanged: (2, 4).
    out = row_padding_variants(_pcx(row_alignment=1, row_bytes=None, planes=1))
    assert tuple(c.row_alignment for c in out) == (2, 4)


def test_other_strategies_unchanged_with_row_bytes_set():
    # Req 6.5: inclusive_bounds and rle_pcx apply unchanged.
    p = _pcx(row_bytes=210, planes=3)
    (b,) = inclusive_bounds(p)
    assert b == replace(p, width=8, height=10,
                        revision_path=("earlier", "inclusive_bounds"))
    (r,) = rle_pcx(p)
    assert r == replace(p, encoding="rle_pcx", revision_path=("earlier", "rle_pcx"))


@settings(max_examples=100)
@given(h=_hypotheses, rb=st.none() | _ints, planes=st.integers(-5, 300))
def test_each_strategy_never_raises_with_row_bytes(h, rb, planes):
    """Strategies never raise when row_bytes and planes are set.

    **Validates: Requirements 6.5, 15.1**
    """
    h = replace(h, row_bytes=rb, planes=planes)
    for name, fn in STRATEGIES:
        out = fn(h)
        assert isinstance(out, tuple), name
        assert all(isinstance(c, Hypothesis) for c in out), name
    if rb is not None:
        assert row_padding_variants(h) == ()

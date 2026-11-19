"""Unit tests for revision strategies (Requirement 3.1, 3.7)."""

from necropsy.engine.strategies import (
    STRATEGIES,
    inclusive_bounds,
    row_padding_variants,
    rle_pcx,
)
from necropsy.engine.types import Hypothesis


def _hyp(**kw):
    base = dict(width=8, height=8, bit_depth=8, header_size=128, probe_name="pcx")
    base.update(kw)
    return Hypothesis(**base)


def test_strategy_names_exact():
    assert tuple(name for name, _ in STRATEGIES) == (
        "inclusive_bounds", "rle_pcx", "row_padding_variants")


def test_inclusive_bounds_gives_8x8():
    h = _hyp(width=7, height=7, bounds=(0, 0, 7, 7))
    out = inclusive_bounds(h)
    assert len(out) == 1
    assert (out[0].width, out[0].height) == (8, 8)


def test_inclusive_bounds_without_bounds_is_empty():
    assert inclusive_bounds(_hyp(bounds=None)) == ()


def test_rle_pcx_from_none():
    out = rle_pcx(_hyp(encoding="none"))
    assert len(out) == 1 and out[0].encoding == "rle_pcx"


def test_rle_pcx_not_for_tga():
    assert rle_pcx(_hyp(probe_name="tga")) == ()


def test_rle_pcx_already_rle():
    assert rle_pcx(_hyp(encoding="rle_pcx")) == ()


def test_row_padding_from_1():
    out = row_padding_variants(_hyp(row_alignment=1))
    assert [c.row_alignment for c in out] == [2, 4]


def test_row_padding_from_4():
    out = row_padding_variants(_hyp(row_alignment=4))
    assert [c.row_alignment for c in out] == [2]


def test_revision_path_extends_parent_and_parent_unchanged():
    parent = _hyp(bounds=(0, 0, 7, 7), revision_path=("earlier",))
    snapshot = _hyp(bounds=(0, 0, 7, 7), revision_path=("earlier",))
    for name, fn in STRATEGIES:
        cands = fn(parent)
        assert cands, name
        for c in cands:
            assert c.revision_path == ("earlier", name)
    assert parent == snapshot

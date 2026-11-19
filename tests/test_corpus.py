"""Corpus tests: exact outcomes for the nine sample files (Requirement 7).

Expected values come from requirements.md Requirement 7 and design.md
"Corpus Trace (measured)", not from the engine.
"""
import struct

import pytest

import make_samples
from necropsy.engine import Engine
from tests.conftest import CORPUS_NAMES, corpus_bytes

RESOLVED_NAMES = ("mystery_a", "mystery_b", "mystery_c", "mystery_e", "mystery_h", "mystery_i")


def run(name):
    return Engine().run(corpus_bytes(name))


def key_of(c):
    h = c.hypothesis
    return (h.width, h.height, h.bit_depth, h.header_size, h.row_alignment, h.encoding, h.data_end)


def check_resolved(name, stage, probe, w, h, bpp, header, align, stride, enc, region, trailer, path):
    r = run(name)
    assert r.status == "RESOLVED"
    assert r.stage == stage
    c = r.candidate
    hy = c.hypothesis
    assert hy.probe_name == probe
    assert (hy.width, hy.height, hy.bit_depth, hy.header_size) == (w, h, bpp, header)
    assert hy.row_alignment == align
    assert c.row_stride == stride
    assert hy.encoding == enc
    assert (c.data_start, c.data_end) == region
    assert c.trailer == trailer
    assert tuple(hy.revision_path) == path
    return r


def test_mystery_a():
    check_resolved("mystery_a", "probe", "pbm", 4, 4, 1, 7, 1, 1, "none", (7, 11), None, ())


def test_mystery_b():
    r = check_resolved("mystery_b", "revision", "pcx", 8, 8, 8, 128, 1, 8, "rle_pcx",
                       (128, 186), "pcx_palette_256", ("inclusive_bounds",))
    hits = [e for e in r.rejections
            if e.reason == "decoder_unconsumed" and e.source == "pcx"
            and e.hypothesis is not None
            and (e.hypothesis.width, e.hypothesis.height) == (7, 7)
            and e.hypothesis.encoding == "rle_pcx" and e.hypothesis.header_size == 128]
    assert hits


def test_mystery_c():
    r = check_resolved("mystery_c", "probe", "tga", 16, 16, 24, 18, 1, 48, "none", (18, 786), None, ())
    # Requirement 7.3: image_descriptor at 0x11, format "B", value 0x20 (top-left origin).
    descs = [f for f in r.candidate.hypothesis.fields if f.name == "image_descriptor"]
    assert len(descs) == 1
    fr = descs[0]
    assert fr.offset == 0x11
    assert fr.fmt == "B"
    assert fr.value == (0x20,)
    assert struct.unpack_from("B", corpus_bytes("mystery_c"), 0x11) == (0x20,)


def test_mystery_e():
    r = check_resolved("mystery_e", "probe", "tiff", 8, 8, 8, 86, 1, 8, "none", (86, 150), None, ())
    multi = [f for f in r.candidate.hypothesis.fields
             if f.fmt.lstrip("<>=!@")[:1].isdigit() is False
             and any(ch in f.fmt for ch in "HIiLlQq")]
    assert multi
    assert all(f.fmt.startswith(">") for f in multi)


def _ambiguous(name, true_key):
    r = run(name)
    assert r.status == "UNRESOLVED_AMBIGUITY"
    assert r.stage == "generic"
    keys = [key_of(c) for c in r.candidates]
    assert true_key in keys
    return r


def test_mystery_d():
    _ambiguous("mystery_d", (8, 8, 8, 40, 1, "none", None))


def test_mystery_f():
    r = _ambiguous("mystery_f", (12, 10, 8, 12, 1, "none", None))
    cand = next(c for c in r.candidates if key_of(c) == (12, 10, 8, 12, 1, "none", None))
    fmts = {f.fmt for f in cand.hypothesis.fields
            if f.name == "width" and f.offset == 0 and f.value[0] == 12}
    assert len(fmts & {"<H", "<I", "<i"}) >= 2


def test_mystery_g():
    _ambiguous("mystery_g", (8, 8, 24, 20, 1, "none", None))


def test_mystery_h():
    r = check_resolved("mystery_h", "revision", "pcx", 6, 6, 8, 128, 4, 8, "none",
                       (128, 176), None, ("inclusive_bounds", "row_padding_variants"))
    assert ("row_padding_variants", "inclusive_bounds") in [
        tuple(p) for p in r.candidate.alternative_paths]


def test_mystery_i():
    r = check_resolved("mystery_i", "revision", "pcx", 8, 8, 8, 128, 1, 8, "rle_pcx",
                       (128, 186), "pcx_palette_256", ("inclusive_bounds", "rle_pcx"))
    assert ("rle_pcx", "inclusive_bounds") in [tuple(p) for p in r.candidate.alternative_paths]


@pytest.mark.parametrize("name", RESOLVED_NAMES)
def test_resolved_pixels_exact(name):
    r = run(name)
    assert r.status == "RESOLVED"
    assert r.candidate.decoded == make_samples.pixels(name)


@pytest.mark.parametrize("name", CORPUS_NAMES)
def test_no_corpus_file_fails(name):
    assert run(name).status != "FAILED"

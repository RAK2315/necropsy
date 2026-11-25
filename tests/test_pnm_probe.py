"""PNM probe, binary P5 and P6 (format-coverage Task 4).

Requirements 3.1 to 3.8, 3.10, 15.1. Expected values come from the spec grammar.
"""
import pytest
from hypothesis import given, settings, strategies as st

from necropsy.engine.engine import Engine
from necropsy.engine.probes import PROBES, probe_pnm


def _seed(data):
    out = probe_pnm(data)
    assert out is not None and out.seed is not None
    return out


def test_probe_order_has_pnm_between_pbm_and_tiff():
    assert [n for n, _ in PROBES] == ["pcx", "tga", "pbm", "pnm", "tiff"]


def test_p5_header_fields_and_seed():
    data = b"P5\n3 2\n255\n" + bytes(range(6))
    out = _seed(data)
    s = out.seed
    assert out.rejections == ()
    assert (s.width, s.height, s.bit_depth, s.header_size) == (3, 2, 8, 11)
    assert (s.encoding, s.row_alignment, s.probe_name, s.maxval) == ("none", 1, "pnm", 255)
    f = {r.name: (r.offset, r.fmt, r.value) for r in s.fields}
    assert f["magic"] == (0, "2s", (b"P5",))
    assert f["width"] == (3, "1s", (b"3",))
    assert f["height"] == (5, "1s", (b"2",))
    assert f["maxval"] == (7, "3s", (b"255",))


def test_p6_16bit_depth():
    s = _seed(b"P6 2 2 65535\n" + bytes(24)).seed
    assert (s.bit_depth, s.maxval, s.header_size) == (48, 65535, 13)
    s = _seed(b"P6 2 2 256\n" + bytes(24)).seed
    assert s.bit_depth == 48
    s = _seed(b"P6 2 2 255\n" + bytes(12)).seed
    assert s.bit_depth == 24


def test_comments_and_crlf():
    data = b"P5\r\n# a comment\r\n2 # another\n2\r\n255\n" + bytes(4)
    out = _seed(data)
    assert out.rejections == ()
    s = out.seed
    assert (s.width, s.height, s.bit_depth) == (2, 2, 8)
    assert data[s.header_size:] == bytes(4)


def test_missing_single_whitespace_byte():
    out = _seed(b"P5\n2 2\n255")
    assert out.rejections[0].reason == "probe_precondition_failed"
    assert "whitespace" in out.rejections[0].detail


def test_comment_after_maxval_is_not_the_separator():
    out = _seed(b"P5\n2 2\n255#x\n" + bytes(4))
    assert out.rejections and out.rejections[0].reason == "probe_precondition_failed"


@pytest.mark.parametrize("header,field", [(b"P5\n0 2\n255\n", "width"), (b"P5\n2 0\n255\n", "height"),
                                          (b"P5\n2 2\n0\n", "maxval"), (b"P5\n2 2\n65536\n", "maxval")])
def test_unusable_values_still_seed_with_rejection(header, field):
    out = _seed(header + bytes(8))
    assert out.rejections[0].reason == "probe_precondition_failed"
    assert field in out.rejections[0].detail


@pytest.mark.parametrize("data", [b"P4\n2 2\n", b"P7\n2 2\n255\n", b"P0\n2 2\n255\n", b"P5x2 2\n255\n",
                                  b"P5", b"P1\n2 2\n0 1 1 0", b"P2\n2 2\n255\n1 2 3 4"])
def test_not_matched(data):
    assert probe_pnm(data) is None


def test_engine_resolves_p5_exact_pixels():
    raster = bytes([0, 10, 20, 30, 40, 50])
    r = Engine().run(b"P5\n# c\n3 2\n255\n" + raster)
    assert r.status == "RESOLVED"
    c = r.candidate
    assert c.hypothesis.probe_name == "pnm"
    assert (c.hypothesis.header_size, c.data_start, c.data_end) == (15, 15, 21)
    assert c.decoded == raster


def test_engine_resolves_p6_16bit_exact_bytes():
    raster = bytes(range(12))
    r = Engine().run(b"P6\n1 2\n65535\n" + raster)
    assert r.status == "RESOLVED"
    assert r.candidate.decoded == raster


def test_engine_rejects_sample_above_maxval():
    r = Engine().run(b"P5\n2 1\n15\n" + bytes([3, 16]))
    assert r.status != "RESOLVED" or r.candidate.hypothesis.probe_name != "pnm"


@settings(max_examples=200, deadline=None)
@given(st.binary(max_size=2048))
def test_probe_never_raises(data):
    out = probe_pnm(data)
    assert out is None or hasattr(out, "rejections")


@settings(max_examples=200, deadline=None)
@given(st.binary(max_size=64), st.sampled_from([b"P5", b"P6"]), st.sampled_from([b" ", b"\n", b"\r\n#"]))
def test_probe_never_raises_with_signature(tail, magic, sep):
    out = probe_pnm(magic + sep + tail)
    assert out is None or hasattr(out, "rejections")

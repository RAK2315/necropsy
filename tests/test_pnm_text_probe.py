"""PNM probe, plain text P1, P2, P3 (format-coverage Task 8). Requirements 1.1, 4.1, 4.2, 4.4, 4.13, 15.1."""
import pytest
from hypothesis import given, settings, strategies as st

from necropsy.engine.engine import Engine
from necropsy.engine.probes import probe_pnm


def _seed(data):
    out = probe_pnm(data)
    assert out is not None and out.seed is not None
    return out


def test_p1_seed_header_ends_after_height():
    data = b"P1\n2 2\n0 1 1 0\n"
    s = _seed(data).seed
    assert (s.width, s.height, s.bit_depth, s.maxval, s.encoding) == (2, 2, 1, 1, "pnm_text")
    assert s.header_size == 6  # index after the height token, no whitespace consumed
    assert data[s.header_size:] == b"\n0 1 1 0\n"


def test_p2_and_p3_seeds():
    s = _seed(b"P2\n2 1\n255\n1 2\n").seed
    assert (s.bit_depth, s.maxval, s.encoding, s.header_size) == (8, 255, "pnm_text", 10)  # 3 + 4 + 3 bytes
    s = _seed(b"P2\n2 1\n1000\n1 2\n").seed
    assert s.bit_depth == 16
    s = _seed(b"P3\n1 1\n255\n1 2 3\n").seed
    assert (s.bit_depth, s.encoding) == (24, "pnm_text")
    s = _seed(b"P3\n1 1\n65535\n1 2 3\n").seed
    assert s.bit_depth == 48


def test_p2_unusable_maxval_has_rejection():
    out = _seed(b"P2\n1 1\n0\n0\n")
    assert out.rejections[0].reason == "probe_precondition_failed"


def test_p1_p2_p3_still_not_matched_without_whitespace():
    assert probe_pnm(b"P1x2 2\n0000") is None


def test_p1_resolves_with_separators_and_with_digit_runs_identical_pixels():
    a = Engine().run(b"P1\n3 2\n1 0 1\n0 1 0\n")
    b = Engine().run(b"P1\n3 2\n101010\n")
    for r in (a, b):
        assert r.status == "RESOLVED"
        assert r.candidate.hypothesis.encoding == "pnm_text"
        assert r.candidate.decoded == bytes([0b10100000, 0b01000000])


def test_p1_letter_fails_with_decoder_malformed():
    r = Engine().run(b"P1\n2 2\n0 1 x 0\n")
    assert r.status == "FAILED"
    assert any(e.reason == "decoder_malformed" for e in r.rejections)


def test_p2_resolves_exact_values_and_comments():
    r = Engine().run(b"P2\n# c\n3 1\n255\n0 128 # mid\n255\n")
    assert r.status == "RESOLVED"
    assert r.candidate.decoded == bytes([0, 128, 255])


def test_p2_one_number_short_and_one_too_many_fail():
    short = Engine().run(b"P2\n3 1\n255\n1 2\n")
    assert short.status == "FAILED"
    assert any(e.reason == "decoder_underrun" for e in short.rejections)
    extra = Engine().run(b"P2\n3 1\n255\n1 2 3 4\n")
    assert extra.status == "FAILED"
    assert any(e.reason == "decoder_unconsumed" for e in extra.rejections)


def test_p2_number_above_maxval_fails():
    r = Engine().run(b"P2\n2 1\n15\n3 16\n")
    assert r.status == "FAILED"
    assert any(e.reason == "sample_above_maxval" for e in r.rejections)


def test_p2_without_whitespace_between_numbers_fails():
    r = Engine().run(b"P2\n2 1\n255\n255255\n")
    assert r.status == "FAILED"


def test_p3_16bit_exact_bytes():
    r = Engine().run(b"P3\n1 1\n65535\n0 256 65535\n")
    assert r.status == "RESOLVED"
    assert r.candidate.decoded == bytes([0, 0, 1, 0, 255, 255])


@settings(max_examples=200, deadline=None)
@given(st.binary(max_size=64), st.sampled_from([b"P1", b"P2", b"P3"]), st.sampled_from([b" ", b"\n", b"\r\n#"]))
def test_text_probe_never_raises(tail, magic, sep):
    out = probe_pnm(magic + sep + tail)
    assert out is None or hasattr(out, "rejections")

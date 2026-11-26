"""TIFF probe, Predictor refusal (format-coverage Requirement 10, Task 22).

Fixtures come from build_tiff in test_tiff_strips: tag 317 is added through `patch`
as a 12-byte IFD entry (tag, type, count, 4-byte value field).
"""
import struct

from hypothesis import given, settings, strategies as st

from necropsy.engine import Engine
from necropsy.engine.closure import check_closure
from necropsy.engine.probes import ProbeOutcome, probe_tiff
from tests.test_tiff_strips import LONG, SHORT, build_tiff, names

PIXELS = bytes(range(6))


def tiff(predictor_entry=None, compression=1, order=b"II"):
    o = "<" if order == b"II" else ">"
    patch = {259: (SHORT, 1, struct.pack(o + "H", compression) + b"\x00\x00")}
    extra = () if predictor_entry is None else ((317, predictor_entry),)
    return build_tiff(order, [PIXELS], 3, 2, 2, patch=patch, extra=extra)


def pred(value, typ=SHORT, count=1, order=b"II"):
    o = "<" if order == b"II" else ">"
    v = struct.pack(o + ("H" if typ == SHORT else "I"), value)
    return (typ, count, v.ljust(4, b"\x00"))


def detail(out):
    return " ".join(r.detail for r in out.rejections)


def test_predictor_2_refused_over_compression_1_5_and_8_both_orders():
    for order in (b"II", b"MM"):
        for c in (1, 5, 8):
            out = probe_tiff(tiff(pred(2, order=order), compression=c, order=order))
            assert out.seed.encoding == f"tiff_compression_{c}_predictor_2"  # Req 10.2, 10.4
            assert [r.reason for r in out.rejections] == ["probe_precondition_failed"]
            assert "predictor (tag 317) = 2 is declared and not implemented" in detail(out)
            fld = [f for f in out.seed.fields if f.name == "predictor"]
            assert len(fld) == 1 and fld[0].value == (2,)  # Req 10.1
            data = tiff(pred(2, order=order), compression=c, order=order)
            assert Engine().run(data).status == "FAILED"  # Req 10.5: no candidate
            # Req 10.6: the closure gate refuses the encoding name without decoding.
            verdict = check_closure(out.seed, data)
            assert not verdict.ok and verdict.reason == "unsupported_encoding"


def test_predictor_long_type_is_read_and_refused():
    out = probe_tiff(tiff(pred(3, typ=LONG)))
    assert out.seed.encoding == "tiff_compression_1_predictor_3"
    assert "= 3 is declared" in detail(out)


def test_predictor_1_and_absent_leave_the_seed_unchanged():
    absent = probe_tiff(tiff())
    one = probe_tiff(tiff(pred(1)))
    assert absent.rejections == () and one.rejections == ()  # Req 10.2: only p != 1 refuses
    assert absent.seed.encoding == one.seed.encoding == "none"
    assert "predictor" not in names(absent.seed)  # Req 10.1: absent adds no field
    assert Engine().run(tiff()).candidate.decoded == PIXELS
    assert Engine().run(tiff(pred(1))).candidate.decoded == PIXELS


def test_unreadable_predictor_is_refused_naming_tag_type_and_count():
    for entry, typ, count in ((pred(2, typ=2), 2, 1), (pred(2, count=2), 3, 2)):
        entry = (typ, count, entry[2])
        out = probe_tiff(tiff(entry))
        assert out.seed.encoding == "tiff_compression_1_predictor_unreadable"  # Req 10.3
        d = detail(out)
        assert "tag 317" in d and f"type {typ}" in d and f"count {count}" in d
        assert Engine().run(tiff(entry)).status == "FAILED"


@settings(max_examples=100, deadline=None)
@given(st.binary(max_size=300))
def test_probe_never_raises_with_predictor_entry(blob):
    # Arbitrary bytes after a valid header; the probe returns None or a ProbeOutcome.
    for data in (blob, tiff(pred(2)) + blob, b"II*\x00\x08\x00\x00\x00" + blob):
        out = probe_tiff(data)
        assert out is None or isinstance(out, ProbeOutcome)

"""TIFF probe, strip arrays (format-coverage Requirement 8, Task 18).

Every fixture is built here from the documented layout: header II/MM, 42, IFD at 8;
IFD = entry count (oH) + 12-byte entries (tag oH, type oH, count oI, value 4 bytes)
+ 4 bytes next-IFD; then the offset and byte-count arrays (when they do not fit in
the 4-byte value field), then the strip bytes.
"""
import struct

from hypothesis import given, settings, strategies as st

from necropsy.engine import Engine
from necropsy.engine.probes import ProbeOutcome, probe_tiff
from necropsy.engine.types import hypothesis_key

SHORT, LONG = 3, 4


def build_tiff(order, strips, w, h, rps, typ=LONG, with_rps=True, patch=None, extra=()):
    """Little (b"II") or big (b"MM") endian TIFF with one strip per element of `strips`."""
    o = "<" if order == b"II" else ">"
    fmt = o + ("H" if typ == SHORT else "I")
    size = 2 if typ == SHORT else 4
    n = len(strips)
    entries = {
        256: (SHORT, 1, struct.pack(o + "H", w) + b"\x00\x00"),
        257: (SHORT, 1, struct.pack(o + "H", h) + b"\x00\x00"),
        258: (SHORT, 1, struct.pack(o + "H", 8) + b"\x00\x00"),
        259: (SHORT, 1, struct.pack(o + "H", 1) + b"\x00\x00"),
    }
    if with_rps:
        entries[278] = (LONG, 1, struct.pack(o + "I", rps))
    n_entries = len(entries) + 2 + len(extra)
    ifd_end = 8 + 2 + 12 * n_entries + 4
    inline = n * size <= 4
    arr_len = 0 if inline else n * size
    pos = ifd_end + 2 * arr_len
    offs = []
    for s in strips:
        offs.append(pos)
        pos += len(s)
    counts = [len(s) for s in strips]
    if inline:
        v273 = b"".join(struct.pack(fmt, v) for v in offs).ljust(4, b"\x00")
        v279 = b"".join(struct.pack(fmt, v) for v in counts).ljust(4, b"\x00")
        tail_arrays = b""
    else:
        v273 = struct.pack(o + "I", ifd_end)
        v279 = struct.pack(o + "I", ifd_end + arr_len)
        tail_arrays = b"".join(struct.pack(fmt, v) for v in offs + counts)
    entries[273] = (typ, n, v273)
    entries[279] = (typ, n, v279)
    for tag, spec in (patch or {}).items():
        entries[tag] = spec
    all_entries = sorted(entries.items()) + list(extra)
    buf = bytearray(order + struct.pack(o + "H", 42) + struct.pack(o + "I", 8))
    buf += struct.pack(o + "H", len(all_entries))
    for tag, (t, c, v) in all_entries:
        buf += struct.pack(o + "HHI", tag, t, c) + v
    buf += b"\x00\x00\x00\x00"
    assert len(buf) == ifd_end or patch or extra
    return bytes(buf) + tail_arrays + b"".join(strips)


def names(seed):
    return [f.name for f in seed.fields]


# 2 x 5 image, 8-bit grey, RowsPerStrip 2: strips of 2, 2 and 1 rows (4, 4 and 2 bytes).
STRIPS = [bytes([1, 2, 3, 4]), bytes([5, 6, 7, 8]), bytes([9, 10])]
PIXELS = b"".join(STRIPS)


def test_long_array_via_pointer_both_orders_exact_pixels():
    for order in (b"II", b"MM"):
        data = build_tiff(order, STRIPS, 2, 5, 2)
        out = probe_tiff(data)
        s = out.seed
        assert out.rejections == ()
        assert names(s).count("strip_offset[2]") == 1 and names(s).count("strip_byte_count[0]") == 1
        assert s.rows_per_strip == 2
        assert len(s.ranges) == 3
        assert s.header_size == s.ranges[0][0] and s.data_end == s.ranges[-1][1]
        assert [e - b for b, e in s.ranges] == [4, 4, 2]  # last strip holds the remaining row
        r = Engine().run(data)
        assert r.status == "RESOLVED"
        assert r.candidate.decoded == PIXELS


def test_short_array_inline_both_orders_exact_pixels():
    strips = [bytes([1, 2, 3, 4]), bytes([5, 6, 7, 8])]  # 2 SHORT = 4 bytes: inline
    for order in (b"II", b"MM"):
        data = build_tiff(order, strips, 2, 4, 2, typ=SHORT)
        out = probe_tiff(data)
        assert out.rejections == ()
        offs = [f for f in out.seed.fields if f.name.startswith("strip_offset[")]
        assert [f.offset for f in offs] == [offs[0].offset, offs[0].offset + 2]
        assert offs[0].fmt == ("<H" if order == b"II" else ">H")
        r = Engine().run(data)
        assert r.status == "RESOLVED" and r.candidate.decoded == b"".join(strips)


def test_short_array_via_pointer():
    strips = [bytes([1, 2]), bytes([3, 4]), bytes([5, 6])]  # 3 SHORT = 6 bytes: pointer
    data = build_tiff(b"II", strips, 2, 3, 1, typ=SHORT)
    assert probe_tiff(data).rejections == ()
    assert Engine().run(data).candidate.decoded == b"".join(strips)


def test_default_rows_per_strip_contradicts_two_strips():
    data = build_tiff(b"II", STRIPS[:2], 2, 4, 2, with_rps=False)
    out = probe_tiff(data)
    assert out.seed.rows_per_strip == 4  # 2^32 - 1 clamped to height
    assert [r.reason for r in out.rejections] == ["probe_precondition_failed"]
    assert "strip count 2" in out.rejections[0].detail and "= 1" in out.rejections[0].detail


def test_count_mismatch_names_both_counts():
    patch = {279: (LONG, 3, struct.pack("<I", 8 + 2 + 12 * 8 + 4))}
    data = build_tiff(b"II", STRIPS[:2], 2, 4, 2, patch=patch) + bytes(12)
    out = probe_tiff(data)
    assert "probe_precondition_failed" in [r.reason for r in out.rejections]
    detail = " ".join(r.detail for r in out.rejections)
    assert "strip_offset count 2" in detail and "strip_byte_count count 3" in detail
    assert out.seed is not None


def test_strips_and_tiles_both_present():
    data = build_tiff(b"II", STRIPS[:2], 2, 4, 2, extra=[(324, (LONG, 1, struct.pack("<I", 0)))])
    out = probe_tiff(data)
    detail = " ".join(r.detail for r in out.rejections)
    assert "273" in detail and "324" in detail


def test_array_past_end_of_file_is_not_read():
    patch = {273: (LONG, 3, struct.pack("<I", 100000))}
    data = build_tiff(b"II", STRIPS[:2], 2, 4, 2, patch=patch)
    out = probe_tiff(data)
    assert "field_out_of_bounds" in [r.reason for r in out.rejections]
    assert out.seed.ranges == ()
    assert not [n for n in names(out.seed) if n.startswith("strip_offset")]


def test_count_above_max_ranges_reads_no_values():
    patch = {273: (LONG, 16385, struct.pack("<I", 8))}
    data = build_tiff(b"II", STRIPS[:2], 2, 4, 2, patch=patch)
    out = probe_tiff(data)
    assert any("16385" in r.detail for r in out.rejections)
    assert out.seed.ranges == ()
    assert not [n for n in names(out.seed) if n.startswith("strip_offset")]


def test_count_at_max_ranges_is_accepted_for_reading():
    n = 16384
    patch = {273: (LONG, n, struct.pack("<I", 8)), 279: (LONG, n, struct.pack("<I", 8))}
    data = build_tiff(b"II", STRIPS[:2], 2, 4, 2, patch=patch) + bytes(8 * n)
    out = probe_tiff(data)
    assert len(out.seed.ranges) == n  # read, then rejected by the strip-count rule
    assert any("strip count 16384" in r.detail for r in out.rejections)


def test_single_strip_unchanged():
    data = build_tiff(b"II", [bytes(range(6))], 3, 2, 2, with_rps=False)
    out = probe_tiff(data)
    s = out.seed
    assert out.rejections == ()
    assert s.ranges == () and s.rows_per_strip is None
    assert len(hypothesis_key(s)) == 7
    assert "strip_offset" in names(s) and "strip_byte_count" in names(s)
    assert Engine().run(data).candidate.decoded == bytes(range(6))


def test_single_strip_with_small_rows_per_strip_is_contradiction():
    data = build_tiff(b"II", [bytes(range(6))], 3, 2, 1)
    out = probe_tiff(data)
    assert [r.reason for r in out.rejections] == ["probe_precondition_failed"]
    assert out.seed.ranges == ()


@settings(max_examples=200, deadline=None)
@given(st.binary(max_size=300))
def test_probe_tiff_never_raises_on_arbitrary_bytes(blob):
    out = probe_tiff(blob)
    assert out is None or isinstance(out, ProbeOutcome)


@settings(max_examples=200, deadline=None)
@given(st.lists(st.tuples(st.integers(0, 140), st.integers(0, 255)), max_size=6),
       st.sampled_from([b"II", b"MM"]))
def test_probe_tiff_never_raises_on_mutated_strip_tiff(edits, order):
    buf = bytearray(build_tiff(order, STRIPS, 2, 5, 2))
    for pos, val in edits:
        if pos < len(buf):
            buf[pos] = val
    out = probe_tiff(bytes(buf))
    assert out is None or isinstance(out, ProbeOutcome)


# Requirement 8.3 / 8.10: a single-strip TIFF keeps the exact field list it had before task 18.
def _single_strip_snapshot():
    import json
    from pathlib import Path
    return json.loads(
        (Path(__file__).parent / "data" / "tiff_single_strip_fields.json").read_text()
    )


def test_single_strip_fields_equal_pre_task_18_snapshot_for_real_files():
    # Snapshot recorded from the probe at commit a42a573 (tools/snapshot_tiff_fields.py).
    from tools import real_corpus as rc
    checked = 0
    for name, expected in _single_strip_snapshot().items():
        out = probe_tiff((rc.REAL / name).read_bytes())
        fields = [[f.name, f.offset, f.fmt, repr(f.value)] for f in out.seed.fields]
        if any(n == "strip_offset[0]" for n, *_ in fields):
            continue  # multi-strip now: its field list legitimately grew
        assert fields == expected, name
        assert out.seed.ranges == () and out.seed.rows_per_strip is None, name
        checked += 1
    assert checked == 23


def test_single_strip_synthetic_has_no_rows_per_strip_field_but_still_checks_it():
    ok = probe_tiff(build_tiff(b"II", [bytes(range(6))], 3, 2, 2))
    assert "rows_per_strip" not in names(ok.seed) and ok.rejections == ()
    bad = probe_tiff(build_tiff(b"II", [bytes(range(6))], 3, 2, 1))
    assert "rows_per_strip" not in names(bad.seed)
    assert [r.reason for r in bad.rejections] == ["probe_precondition_failed"]
    multi = probe_tiff(build_tiff(b"II", STRIPS, 2, 5, 2))
    assert "rows_per_strip" in names(multi.seed)

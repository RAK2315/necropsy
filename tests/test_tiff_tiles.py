"""TIFF probe, tile arrays (format-coverage Requirement 9, Task 21).

Layout of every fixture: header (II or MM, 42, IFD at 8); IFD = entry count (oH) + 12-byte
entries (tag oH, type oH, count oI, value 4 bytes) + 4 next-IFD bytes; then the tile offset
and byte-count arrays (LONG, count >= 2, via pointer; count 1 inline); then the tiles.
Pixel (x, y) of the image is 10*y + x; a position beyond the image edge holds 200.
"""
import struct

from hypothesis import given, settings, strategies as st

from necropsy.engine import Engine
from necropsy.engine.probes import ProbeOutcome, probe_tiff

SHORT, LONG = 3, 4


def tiles_for(w, h, tw, tl):
    across, down = -(-w // tw), -(-h // tl)
    tiles = []
    for ty in range(down):
        for tx in range(across):
            t = bytearray()
            for y in range(ty * tl, ty * tl + tl):
                for x in range(tx * tw, tx * tw + tw):
                    t.append(10 * y + x if x < w and y < h else 200)
            tiles.append(bytes(t))
    return tiles


def image(w, h):
    return bytes(10 * y + x for y in range(h) for x in range(w))


def build(order, w, h, tw, tl, tiles, drop=(), counts_n=None, extra=()):
    """Tiled 8-bit grey TIFF. `drop` omits tags; `counts_n` forces the 325 count."""
    o = "<" if order == b"II" else ">"
    n = len(tiles)
    one = lambda v: struct.pack(o + "I", v)
    shorts = lambda v: struct.pack(o + "H", v) + b"\x00\x00"
    entries = {
        256: (SHORT, 1, shorts(w)), 257: (SHORT, 1, shorts(h)),
        258: (SHORT, 1, shorts(8)), 259: (SHORT, 1, shorts(1)),
        322: (SHORT, 1, shorts(tw)), 323: (SHORT, 1, shorts(tl)),
    }
    n_entries = len(entries) + 2 + len(extra)
    ifd_end = 8 + 2 + 12 * n_entries + 4
    inline = n == 1
    cn = n if counts_n is None else counts_n
    pos = ifd_end + (0 if inline else 8 * n)
    offs = []
    for t in tiles:
        offs.append(pos)
        pos += len(t)
    if inline:
        v324, v325, tail = one(offs[0]), one(len(tiles[0])), b""
    else:
        v324, v325 = one(ifd_end), one(ifd_end + 4 * n)
        tail = b"".join(one(v) for v in offs) + b"".join(one(len(t)) for t in tiles)
    entries[324] = (LONG, n, v324)
    entries[325] = (LONG, cn, v325)
    for tag in drop:
        entries.pop(tag, None)
    all_entries = sorted(entries.items()) + list(extra)
    buf = bytearray(order + struct.pack(o + "H", 42) + one(8))
    buf += struct.pack(o + "H", len(all_entries))
    for tag, (t, c, v) in all_entries:
        buf += struct.pack(o + "HHI", tag, t, c) + v
    buf += b"\x00\x00\x00\x00"
    return bytes(buf) + tail + b"".join(tiles)


def names(seed):
    return [f.name for f in seed.fields]


def detail(out):
    return " ".join(r.detail for r in out.rejections)


def test_partial_column_and_row_exact_pixels_both_orders():
    tiles = tiles_for(5, 3, 2, 2)   # 3 x 2 grid, last column 1 px, last row 1 row
    for order in (b"II", b"MM"):
        data = build(order, 5, 3, 2, 2, tiles)
        out = probe_tiff(data)
        s = out.seed
        assert out.rejections == ()
        assert s.tile == (2, 2) and len(s.ranges) == 6 and s.rows_per_strip is None
        assert names(s).count("tile_offset[5]") == 1 and names(s).count("tile_byte_count[0]") == 1
        assert s.header_size == s.ranges[0][0] and s.data_end == s.ranges[-1][1]
        r = Engine().run(data)
        assert r.status == "RESOLVED"
        assert r.candidate.decoded == image(5, 3)


def test_tile_order_and_position():
    # Tile k sits at column k mod across, row k div across: write tiles in reverse file order.
    tiles = tiles_for(4, 4, 2, 2)
    data = build(b"II", 4, 4, 2, 2, tiles)
    s = probe_tiff(data).seed
    assert [b for b, _ in s.ranges] == sorted(b for b, _ in s.ranges)
    assert Engine().run(data).candidate.decoded == image(4, 4)


def test_single_tile_inline():
    data = build(b"II", 2, 2, 2, 2, tiles_for(2, 2, 2, 2))
    out = probe_tiff(data)
    assert out.rejections == () and len(out.seed.ranges) == 1 and out.seed.tile == (2, 2)
    assert Engine().run(data).candidate.decoded == image(2, 2)


def test_missing_tile_tags_each_named():
    tiles = tiles_for(4, 4, 2, 2)
    for tag, word in ((322, "tile_width"), (323, "tile_length"), (325, "tile_byte_count")):
        out = probe_tiff(build(b"II", 4, 4, 2, 2, tiles, drop=(tag,)))
        assert [r.reason for r in out.rejections] == ["probe_precondition_failed"]
        assert word in detail(out)
        assert out.seed.ranges == () and out.seed.tile is None


def test_zero_tile_width_rejected():
    out = probe_tiff(build(b"II", 4, 4, 0, 2, tiles_for(4, 4, 2, 2)))
    assert "tile_width" in detail(out) and out.seed.tile is None


def test_unequal_counts_named():
    out = probe_tiff(build(b"II", 4, 4, 2, 2, tiles_for(4, 4, 2, 2), counts_n=3))
    assert "tile_offset count 4" in detail(out) and "tile_byte_count count 3" in detail(out)


def test_strips_and_tiles_both_present():
    extra = [(273, (LONG, 1, struct.pack("<I", 0)))]
    out = probe_tiff(build(b"II", 4, 4, 2, 2, tiles_for(4, 4, 2, 2), extra=extra))
    assert "273" in detail(out) and "324" in detail(out)


def test_tiles_do_not_require_273_or_279():
    out = probe_tiff(build(b"II", 4, 4, 2, 2, tiles_for(4, 4, 2, 2)))
    assert out.rejections == ()


def test_neither_273_nor_324_names_both():
    data = build(b"II", 4, 4, 2, 2, tiles_for(4, 4, 2, 2), drop=(324, 325))
    out = probe_tiff(data)
    assert "273" in detail(out) and "324" in detail(out)


def test_non_tiled_file_gains_no_tile_fields():
    data = build(b"II", 4, 4, 2, 2, tiles_for(4, 4, 2, 2), drop=(322, 323, 324, 325))
    assert not [n for n in names(probe_tiff(data).seed) if n.startswith("tile")]


@settings(max_examples=300, deadline=None)
@given(st.binary(max_size=300))
def test_never_raises_on_arbitrary_bytes(blob):
    for prefix in (b"", b"II*\x00\x08\x00\x00\x00", b"MM\x00*\x00\x00\x00\x08"):
        out = probe_tiff(prefix + blob)
        assert out is None or isinstance(out, ProbeOutcome)


@settings(max_examples=200, deadline=None)
@given(st.binary(min_size=0, max_size=40), st.integers(0, 80), st.sampled_from([b"II", b"MM"]))
def test_never_raises_on_mutated_tiled_file(noise, at, order):
    data = bytearray(build(order, 5, 3, 2, 2, tiles_for(5, 3, 2, 2)))
    data[at:at + len(noise)] = noise
    out = probe_tiff(bytes(data))
    assert out is None or isinstance(out, ProbeOutcome)

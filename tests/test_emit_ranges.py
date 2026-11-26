"""Emission of several data ranges: strips and tiles (format-coverage Task 35;
Requirements 17.6, 17.8, 17.9)."""
import hashlib
import json
import pathlib
import struct

import pytest
from hypothesis import given, settings, strategies as st

from necropsy.emit import emit_spec
from necropsy.emit.layout import build_layout
from necropsy.emit.render import _MAX_EMBED
from necropsy.engine import Engine
from tests.conftest import SAMPLES_DIR
from tests.support.reference_reader import extract_layout, parse, parse_candidates
from tests.test_emit_tiff import _run_emitted

REAL = SAMPLES_DIR / "real"
# Corpus files whose result holds a candidate with several ranges (measured before Task 35).
RANGED = [
    "goimage_blue-purple-pink.lzwcompressed.tiff", "goimage_invalid-palette-ref.tiff",
    "goimage_video-001-gray.tiff", "goimage_video-001-paletted.tiff",
    "libtiff_minisblack-1c-8b.tiff", "libtiff_palette-1c-8b.tiff", "libtiff_rgb-3c-8b.tiff",
    "pillow_12bit.cropped.tif", "pillow_tiff_strip_raw.tif", "pillow_tiff_tiled_raw.tif",
]


def _emit(data):
    result = Engine().run(data)
    spec = emit_spec(result, data)
    assert not hasattr(spec, "message"), getattr(spec, "message", "")
    return result, dict(spec.files), spec.slug


def _cands(result):
    one = getattr(result, "candidate", None)
    return [one] if one is not None else list(result.candidates)


# --- small TIFFs built from documented bytes --------------------------------------------------------
# Little-endian, one 8-bit sample per pixel. Header: "II", 42, IFD at 8. The IFD is a 2-byte count,
# 12-byte entries (tag, type, count, value) and a 4-byte next-IFD offset of 0. Arrays of LONG
# (type 4) values larger than 4 bytes sit after the IFD; the data sits after the arrays.
W, H = 10, 7


def _pixel(x, y):
    return (x * 13 + y * 7 + 1) & 0xFF


IMAGE = bytes(_pixel(x, y) for y in range(H) for x in range(W))


def _packbits_literal(raw):
    return b"".join(bytes((len(raw[i:i + 128]) - 1,)) + raw[i:i + 128] for i in range(0, len(raw), 128))


def _build(units, compression, tags):
    """`units` are the stored bytes of each strip or tile; `tags` the geometry entries
    ((tag, value), ...) which hold LONG values. The offset and byte-count arrays follow the IFD."""
    n = len(units)
    entries = [(256, 3, 1, W), (257, 3, 1, H), (258, 3, 1, 8), (259, 3, 1, compression),
               (262, 3, 1, 1), (277, 3, 1, 1)]
    entries += [(t, 3, 1, v) for t, v in tags if t not in (273, 279, 324, 325)]
    off_tag, cnt_tag = (324, 325) if any(t == 322 for t, _ in tags) else (273, 279)
    entries.append((off_tag, 4, n, None))
    entries.append((cnt_tag, 4, n, None))
    entries.sort(key=lambda e: e[0])
    ifd_size = 2 + 12 * len(entries) + 4
    arrays_at = 8 + ifd_size
    data_at = arrays_at + 8 * n
    offsets, pos = [], data_at
    for u in units:
        offsets.append(pos)
        pos += len(u)
    ifd = struct.pack("<H", len(entries))
    for tag, typ, count, val in entries:
        if val is None:
            val = arrays_at if tag == off_tag else arrays_at + 4 * n
        ifd += struct.pack("<HHII", tag, typ, count, val) if typ == 4 else \
            struct.pack("<HHIHH", tag, typ, count, val, 0)
    ifd += struct.pack("<I", 0)
    arrays = struct.pack("<%dI" % n, *offsets) + struct.pack("<%dI" % n, *[len(u) for u in units])
    return b"II" + struct.pack("<HI", 42, 8) + ifd + arrays + b"".join(units)


def _strips(rps):
    return [IMAGE[r * W:(r + rps) * W if (r + rps) * W <= len(IMAGE) else len(IMAGE)]
            for r in range(0, H * W // W, rps)]


def _tiles(tw, tl):
    across, down = -(-W // tw), -(-H // tl)
    tiles = []
    for ty in range(down):
        for tx in range(across):
            tiles.append(bytes(_pixel(tx * tw + c, ty * tl + r) if (tx * tw + c < W and ty * tl + r < H) else 0
                               for r in range(tl) for c in range(tw)))
    return tiles


STRIP_RAW = _build(_strips(3), 1, [(278, 3)])
STRIP_PACKBITS = _build([_packbits_literal(s) for s in _strips(3)], 32773, [(278, 3)])
TILE_RAW = _build(_tiles(4, 4), 1, [(322, 4), (323, 4)])
TILE_PACKBITS = _build([_packbits_literal(t) for t in _tiles(4, 4)], 32773, [(322, 4), (323, 4)])
SYNTH = {"strip_raw": STRIP_RAW, "strip_packbits": STRIP_PACKBITS,
         "tile_raw": TILE_RAW, "tile_packbits": TILE_PACKBITS}


@pytest.mark.parametrize("name", sorted(SYNTH))
def test_synthetic_files_resolve_to_the_image(name):
    r = Engine().run(SYNTH[name])
    assert r.status == "RESOLVED" and r.candidate.decoded == IMAGE, name
    assert len(r.candidate.hypothesis.ranges) > 1


# --- Requirement 17.6: kind, keys, note ---------------------------------------------------------------
def test_strip_layout_is_a_file_layout_with_literal_ranges_req_17_6():
    result, files, _ = _emit(STRIP_RAW)
    lay = build_layout(result, STRIP_RAW)
    h = result.candidate.hypothesis
    assert lay["kind"] == "file" and lay["tag_table"] is None
    assert lay["data"]["ranges"] == [list(r) for r in h.ranges]
    assert lay["image"]["rows_per_strip"] == 3 and "tile" not in lay["image"]
    assert lay["data"]["encoding"] == "none"
    assert "no array rule for strip and tile offsets" in lay["note"]
    assert "no array rule for strip and tile offsets" in files["requirements.md"]


def test_tile_layout_names_the_tile_and_compression_req_17_6():
    result, files, _ = _emit(TILE_PACKBITS)
    lay = build_layout(result, TILE_PACKBITS)
    assert lay["kind"] == "file" and lay["image"]["tile"] == [4, 4]
    assert "rows_per_strip" not in lay["image"]
    assert lay["data"]["encoding"] == "packbits"
    assert "WHEN the encoding is `packbits`, THE parser SHALL" in files["requirements.md"]


def test_layout_keys_are_only_those_of_the_requirement_req_17_6():
    allowed_image = {"width", "height", "bit_depth", "row_alignment", "rows_per_strip", "tile"}
    for data in SYNTH.values():
        lay = build_layout(Engine().run(data), data)
        assert set(lay["image"]) <= allowed_image
        assert set(lay["data"]) == {"start", "end", "encoding", "ranges", "trailers"}


def test_single_strip_layout_stays_kind_format_req_17_6():
    data = (REAL / "goimage_bw-deflate.tiff").read_bytes()
    lay = build_layout(Engine().run(data), data)
    assert lay["kind"] == "format" and "ranges" not in lay["data"]
    assert "rows_per_strip" not in lay["image"] and "tile" not in lay["image"]


def test_emission_without_ranges_unchanged_pin():
    # Hashes were taken from the emitter at the commit before Task 35: every sample and corpus
    # file with no multi-range candidate must emit byte for byte what it did.
    snap = json.loads((pathlib.Path(__file__).parent / "data"
                       / "emit_no_ranges_pre_t35_sha256.json").read_text(encoding="ascii"))
    assert len(snap) >= 60
    for name, want in snap.items():
        path = SAMPLES_DIR / name
        if not path.exists():            # external samples are keyed by bare name
            path = SAMPLES_DIR / "external" / name
        data = path.read_bytes()
        spec = emit_spec(Engine().run(data), data)
        got = {n: hashlib.sha256(t.encode("utf-8")).hexdigest() for n, t in sorted(spec.files)}
        assert got == want, name


# --- Requirement 17.8: the reader assembles what the engine assembles ----------------------------------
def _assert_reader_equals_engine(data):
    result, files, _ = _emit(data)
    layout = extract_layout(files["requirements.md"])
    outs = parse_candidates(layout, data)
    cands = _cands(result)
    assert len(outs) == len(cands)
    for out, c in zip(outs, cands):
        assert out["ok"] is True, out
        h = c.hypothesis
        assert (out["width"], out["height"], out["bit_depth"], out["row_alignment"]) == (
            h.width, h.height, h.bit_depth, h.row_alignment)
        assert (out["data_start"], out["data_end"]) == (c.data_start, c.data_end)
        assert out["pixels"] == c.decoded
    return result


@pytest.mark.parametrize("name", sorted(SYNTH))
def test_reader_assembles_synthetic_files_equal_to_the_engine(name):
    result = _assert_reader_equals_engine(SYNTH[name])
    layout = extract_layout(_emit(SYNTH[name])[1]["requirements.md"])
    assert parse(layout, SYNTH[name])["pixels"] == IMAGE


@pytest.mark.parametrize("name", RANGED)
def test_reader_assembles_corpus_files_equal_to_the_engine(name):
    data = (REAL / name).read_bytes()
    result = _assert_reader_equals_engine(data)
    assert any(c.hypothesis.ranges for c in _cands(result)), name


@pytest.mark.parametrize("name", ["goimage_blue-purple-pink.lzwcompressed.tiff",
                                  "goimage_video-001-paletted.tiff"])
def test_emitted_tests_pass_for_corpus_ranges_req_17_7_17_9(tmp_path, name):
    data = (REAL / name).read_bytes()
    assert len(data) <= _MAX_EMBED     # embedded, so the emitted tests decode it
    _run_emitted(tmp_path, data)


@pytest.mark.parametrize("name", sorted(SYNTH))
def test_emitted_tests_pass_for_synthetic_ranges_req_17_7_17_9(tmp_path, name):
    _run_emitted(tmp_path, SYNTH[name])


def test_reader_rejects_wrong_range_counts_and_sizes_req_17_8():
    layout = extract_layout(_emit(STRIP_RAW)[1]["requirements.md"])
    ok = parse(layout, STRIP_RAW)
    assert ok["ok"] is True and ok["pixels"] == IMAGE
    for mutate in (
        lambda l: l["data"]["ranges"].pop(),                                  # strip count
        lambda l: l["data"]["ranges"].__setitem__(0, [0, 5]),                 # overlaps header fields
        lambda l: l["data"]["ranges"].__setitem__(1, [l["data"]["ranges"][1][0], l["data"]["ranges"][1][1] - 1]),
        lambda l: l["data"]["ranges"].__setitem__(0, [-1, 3]),
        lambda l: l["data"]["ranges"].__setitem__(0, [10 ** 9, 10 ** 9 + 1]),
        lambda l: l["image"].__setitem__("rows_per_strip", 0),
    ):
        lay = json.loads(json.dumps(layout))
        mutate(lay)
        assert parse(lay, STRIP_RAW)["ok"] is False


def test_reader_overlapping_ranges_are_an_error_req_17_8():
    layout = extract_layout(_emit(STRIP_RAW)[1]["requirements.md"])
    rg = layout["data"]["ranges"]
    layout["data"]["ranges"][1] = [rg[0][0] + 1, rg[0][0] + 1 + (rg[1][1] - rg[1][0])]
    assert parse(layout, STRIP_RAW)["ok"] is False


def test_reader_checks_declared_sizes_before_allocating_req_17_8():
    huge = 2 ** 40
    for src, tile in ((TILE_RAW, [2 ** 20, 2 ** 20]), (TILE_PACKBITS, [2 ** 20, 2 ** 20]),
                      (STRIP_PACKBITS, None), (STRIP_RAW, None)):
        layout = extract_layout(_emit(src)[1]["requirements.md"])
        layout["image"]["width"] = layout["image"]["height"] = huge
        if tile is not None:
            layout["image"]["tile"] = tile
        else:
            layout["image"]["rows_per_strip"] = huge
            layout["data"]["ranges"] = layout["data"]["ranges"][:1]
        out = parse(layout, src)
        assert out["ok"] is False, out


# --- never raises -------------------------------------------------------------------------------------
_LAYOUT_TEXT = {n: json.dumps(extract_layout(_emit(d)[1]["requirements.md"])) for n, d in SYNTH.items()}
_RANGE = st.lists(st.integers(-5, 300), min_size=2, max_size=2)


@settings(max_examples=150, deadline=None)
@given(st.sampled_from(sorted(SYNTH)), st.lists(_RANGE, max_size=12),
       st.one_of(st.none(), st.lists(st.integers(-3, 2 ** 33), min_size=2, max_size=2)),
       st.integers(-3, 2 ** 33), st.integers(-3, 2 ** 33), st.integers(-3, 40),
       st.sampled_from(["none", "packbits", "lzw_tiff", "deflate_zlib", "lzma_xz", "pnm_text"]),
       st.binary(max_size=200))
def test_reader_ranges_assembly_never_raises(name, ranges, tile, width, height, rps, enc, tail):
    src = SYNTH[name]
    layout = json.loads(_LAYOUT_TEXT[name])
    layout["data"]["ranges"] = ranges
    layout["data"]["encoding"] = enc
    layout["image"]["width"] = width
    layout["image"]["height"] = height
    if tile is not None:
        layout["image"]["tile"] = tile
        layout["image"].pop("rows_per_strip", None)
    else:
        layout["image"].pop("tile", None)
        layout["image"]["rows_per_strip"] = rps
    for data in (src, src[:122] + tail, tail):
        out = parse(layout, data)
        assert isinstance(out, dict)
        if out["ok"]:
            assert len(out["pixels"]) == out["row_stride"] * out["height"]

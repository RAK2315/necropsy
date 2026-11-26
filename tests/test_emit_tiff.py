"""Emission of the TIFF compression mapping, the predictor entry and the four decoders
(format-coverage Task 33; Requirements 17.1, 17.3, 17.7, 17.8, 17.9)."""
import hashlib
import json
import os
import pathlib
import re
import struct
import subprocess
import sys
import zlib

import pytest
from hypothesis import given, settings, strategies as st

from necropsy.emit import emit_spec
from necropsy.emit.layout import build_layout
from necropsy.engine import Engine
from tests.conftest import SAMPLES_DIR
from tests.support import reference_reader
from tests.support.reference_reader import extract_layout, make_parser_module, parse

REAL = SAMPLES_DIR / "real"
PACKBITS = REAL / "goimage_bw-packbits.tiff"            # compression 32773
DEFLATE = REAL / "goimage_bw-deflate.tiff"              # compression 32946
LZMA = REAL / "pillow_hopper_lzma.tif"                  # compression 34925
LZW_BIG = REAL / "libtiff_lzw-single-strip.tiff"        # compression 5, ends without EOI, 76,264 bytes
NEW_MAPPING = {"1": "none", "32773": "packbits", "5": "lzw_tiff", "8": "deflate_zlib",
               "32946": "deflate_zlib", "34925": "lzma_xz"}


def _emit(data):
    result = Engine().run(data)
    spec = emit_spec(result, data)
    assert not hasattr(spec, "message"), getattr(spec, "message", "")
    return result, dict(spec.files), spec.slug


# --- a small LZW TIFF built from documented bytes -------------------------------------------------
W, H = 16, 8
PIXELS = bytes((x * 16 + y) & 0xFF for y in range(H) for x in range(W))


def _lzw_literals(pixels, eoi):
    """CLEAR, one literal code per byte, optional EOI, all 9 bits, most significant bit first.

    The decoder adds one table entry per code after the first, so 129 codes keep the table
    below 511 entries and the width stays 9."""
    codes = [256] + list(pixels) + ([257] if eoi else [])
    bits = "".join(format(c, "09b") for c in codes)
    bits += "0" * (-len(bits) % 8)
    return int(bits, 2).to_bytes(len(bits) // 8, "big")


def _tiff(strip, compression, w=W, h=H):
    """Little-endian TIFF: header (II, 42, IFD at 8), 9 entries of 12 bytes, strip at 122."""
    entries = [(256, 3, w), (257, 3, h), (258, 3, 8), (259, 3, compression), (262, 3, 1),
               (273, 4, 122), (277, 3, 1), (278, 3, h), (279, 4, len(strip))]
    ifd = struct.pack("<H", len(entries))
    for tag, typ, val in entries:
        ifd += struct.pack("<HHI", tag, typ, 1) + struct.pack("<I", val)
    return b"II" + struct.pack("<HI", 42, 8) + ifd + struct.pack("<I", 0) + strip


LZW_EOI = _tiff(_lzw_literals(PIXELS, True), 5)
LZW_NO_EOI = _tiff(_lzw_literals(PIXELS, False), 5)
PACKBITS_SMALL = _tiff(b"".join(bytes((0x7F,)) + PIXELS[i:i + 128] for i in range(0, len(PIXELS), 128)), 32773)
DEFLATE_SMALL = _tiff(zlib.compress(PIXELS), 8)


def test_synthetic_files_resolve_to_the_pixels():
    for data in (LZW_EOI, LZW_NO_EOI, PACKBITS_SMALL, DEFLATE_SMALL):
        r = Engine().run(data)
        assert r.status == "RESOLVED" and r.candidate.decoded == PIXELS, data[:4]


# --- Requirement 17.3: mapping and predictor entry ------------------------------------------------
@pytest.mark.parametrize("path", [PACKBITS, DEFLATE, LZMA, LZW_BIG], ids=lambda p: p.name)
def test_mapping_and_predictor_entry_req_17_3(path):
    data = path.read_bytes()
    lay = build_layout(Engine().run(data), data)
    enc = lay["data"]["encoding"]
    assert enc == {"field": "compression", "values": NEW_MAPPING, "otherwise": "unsupported"}
    entries = lay["tag_table"]["entries"]
    names = [e["name"] for e in entries]
    assert names.index("predictor") == names.index("planar_configuration") + 1
    assert entries[names.index("predictor")] == {
        "name": "predictor", "tag": 317, "default": 1, "expect": 1, "array": None}


def test_requirements_state_predictor_and_define_only_encodings_in_use_req_17_1():
    _, files, _ = _emit(PACKBITS.read_bytes())
    req = files["requirements.md"]
    assert "tag entry `predictor` from the entry whose tag equals 317" in req
    assert "IF the value of tag entry `predictor` is not 1" in req
    assert "WHEN the encoding is `packbits`, THE parser SHALL" in req
    assert "WHEN the encoding is `unsupported`, THE parser SHALL" in req
    # The mapping names every encoding, so the definitions of all four are present.
    for name in ("lzw_tiff", "deflate_zlib", "lzma_xz"):
        assert "WHEN the encoding is `%s`, THE parser SHALL" % name in req
    # An emitted spec of a layout that does not use a name does not define it.
    _, files_tga, _ = _emit((REAL / "pillow_200x32_rgb_tl_rle.tga").read_bytes())
    assert "`packbits`" not in files_tga["requirements.md"]


def test_lzw_definition_states_the_amended_end_rule_req_12_8():
    req = _emit(LZW_EOI)[1]["requirements.md"]
    assert "whole byte of the data region follows the byte that holds the last bit of EOI" in req
    assert "fewer than 8 bits remain, THEN THE parser SHALL accept" in req
    assert "8 or more bits remain, a whole unread byte is unconsumed" in req
    assert "ends only at EOI" not in req


# --- the reference reader reads each encoding -----------------------------------------------------
@pytest.mark.parametrize("path", [PACKBITS, DEFLATE, LZMA, LZW_BIG], ids=lambda p: p.name)
def test_reference_reader_decodes_equal_to_the_engine_req_17_9(path):
    data = path.read_bytes()
    result, files, _ = _emit(data)
    out = parse(extract_layout(files["requirements.md"]), data)
    assert out["ok"] is True, out
    c = result.candidate
    assert (out["width"], out["height"], out["bit_depth"], out["row_alignment"]) == (
        c.hypothesis.width, c.hypothesis.height, c.hypothesis.bit_depth, c.hypothesis.row_alignment)
    assert (out["data_start"], out["data_end"]) == (c.data_start, c.data_end)
    assert out["pixels"] == c.decoded


def test_reference_reader_lzw_end_rule_req_12_8():
    layout = extract_layout(_emit(LZW_EOI)[1]["requirements.md"])
    assert parse(layout, LZW_EOI)["pixels"] == PIXELS
    assert parse(layout, LZW_NO_EOI)["pixels"] == PIXELS        # strip ends, 7 padding bits left
    strip_at = 122

    def with_strip(strip):
        # keep the declared byte count of the layout's source in step with the strip
        return _tiff(strip, 5)

    ok_strip = LZW_EOI[strip_at:]
    assert parse(layout, with_strip(ok_strip + b"\x00"))["ok"] is False         # whole byte after EOI
    assert parse(layout, with_strip(LZW_NO_EOI[strip_at:] + b"\x00"))["ok"] is False   # whole unread byte
    assert parse(layout, with_strip(ok_strip[:-3]))["ok"] is False              # ends before the output is full


def test_reference_reader_packbits_deflate_lzma_ends_are_errors():
    pb = extract_layout(_emit(PACKBITS_SMALL)[1]["requirements.md"])
    assert parse(pb, PACKBITS_SMALL)["pixels"] == PIXELS
    assert parse(pb, _tiff(PACKBITS_SMALL[122:] + b"\x80", 32773))["ok"] is False   # 0x80 left after full
    assert parse(pb, _tiff(PACKBITS_SMALL[122:-5], 32773))["ok"] is False
    df = extract_layout(_emit(DEFLATE_SMALL)[1]["requirements.md"])
    assert parse(df, DEFLATE_SMALL)["pixels"] == PIXELS
    assert parse(df, _tiff(DEFLATE_SMALL[122:] + b"\x00", 8))["ok"] is False
    assert parse(df, _tiff(DEFLATE_SMALL[122:-2], 8))["ok"] is False
    assert parse(df, _tiff(zlib.compress(PIXELS + b"\x00"), 8))["ok"] is False
    assert parse(df, _tiff(zlib.compress(PIXELS[:-1]), 8))["ok"] is False
    data = LZMA.read_bytes()
    xz = extract_layout(_emit(data)[1]["requirements.md"])
    assert parse(xz, data)["ok"] is True
    cut = _tiff(b"\xfd7zXZ\x00\x00", 34925, 128, 128)        # a stream that ends inside its header
    assert parse(xz, cut)["ok"] is False


def test_reference_reader_refuses_a_predictor_other_than_1_req_17_3():
    layout = extract_layout(_emit(PACKBITS.read_bytes())[1]["requirements.md"])
    data = bytearray(PACKBITS_SMALL)
    assert parse(layout, bytes(data))["ok"] is True
    # Append a predictor entry (tag 317) = 2 by rebuilding the IFD with 10 entries.
    entries = [(256, 3, W), (257, 3, H), (258, 3, 8), (259, 3, 32773), (262, 3, 1),
               (273, 4, 134), (277, 3, 1), (278, 3, H), (279, 4, len(PACKBITS_SMALL) - 122), (317, 3, 2)]
    ifd = struct.pack("<H", len(entries))
    for tag, typ, val in entries:
        ifd += struct.pack("<HHI", tag, typ, 1) + struct.pack("<I", val)
    data = b"II" + struct.pack("<HI", 42, 8) + ifd + struct.pack("<I", 0) + PACKBITS_SMALL[122:]
    out = parse(layout, data)
    assert out["ok"] is False and "predictor" in out["error"]


@pytest.mark.parametrize("name,data", [("packbits", PACKBITS_SMALL), ("deflate", DEFLATE_SMALL),
                                       ("lzw", LZW_EOI), ("lzw_no_eoi", LZW_NO_EOI)])
def test_emitted_tests_pass_under_pytest_req_17_7_17_9(tmp_path, name, data):
    _run_emitted(tmp_path, data)


@pytest.mark.parametrize("path", [PACKBITS, DEFLATE, LZMA], ids=lambda p: p.name)
def test_emitted_tests_pass_under_pytest_for_corpus_req_17_7_17_9(tmp_path, path):
    _run_emitted(tmp_path, path.read_bytes())


def _run_emitted(tmp_path, data):
    _, files, slug = _emit(data)
    module = slug.replace("-", "_")
    (tmp_path / ("parser_%s.py" % module)).write_bytes(
        make_parser_module(files["requirements.md"]).encode("utf-8"))
    (tmp_path / ("test_%s.py" % module)).write_bytes(files["test_%s.py" % module].encode("utf-8"))
    env = dict(os.environ, PYTHONPATH=str(tmp_path))
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", str(tmp_path), "-q", "-p", "no:cacheprovider"],
        cwd=str(tmp_path), env=env, capture_output=True, text=True, timeout=300)
    out = proc.stdout + proc.stderr
    assert proc.returncode == 0, out
    assert re.search(r"(\d+) passed", out), out
    assert "skipped" not in out, out


def test_reference_reader_imports_nothing_from_necropsy_req_17_8():
    src = pathlib.Path(reference_reader.__file__).read_text(encoding="utf-8")
    assert not re.search(r"^\s*(import|from)\s+necropsy", src, re.M)
    assert re.search(r"^import zlib$", src, re.M) and re.search(r"^import lzma$", src, re.M)


# --- Requirement 17.11 / 17.3: only the mapping, the predictor entry and the definitions change ---
_BLOCK = re.compile(r"```necropsy-layout\n(.*?)\n```", re.S)


def _numbers_stripped(text):
    return re.sub(r"(?m)^\d+\. ", "", text)


def _undo_17_3(name, text):
    """Reverse the changes Requirement 17.3 and 17.1 make to a TIFF requirements.md, then strip
    criterion numbers (inserted lines renumber the criteria)."""
    if name != "requirements.md":
        return text

    def block(m):
        lay = json.loads(m.group(1))
        lay["data"]["encoding"]["values"] = {"1": "none"}
        lay["tag_table"]["entries"] = [e for e in lay["tag_table"]["entries"] if e["name"] != "predictor"]
        return "```necropsy-layout\n%s\n```" % json.dumps(lay, indent=2)

    text = _BLOCK.sub(block, text)
    text = re.sub(r"\(1 \u2192 `none`, [^)]*\), otherwise `unsupported`",
                  "(1 \u2192 `none`), otherwise `unsupported`", text)
    # Task 36 follow-up (Requirements 17.1, 17.11): the closure line of the compressed encodings
    # names them; undone to the run-length line the pins hold.
    new_closure = re.compile(r"WHEN the encoding is (packbits|lzw_tiff|deflate_zlib|lzma_xz), THE parser "
                             r"SHALL require the decoder to end as its definition above states and to "
                             r"produce exactly the expected bytes for each data range\.$")
    run_length = ("WHEN the encoding is a run-length encoding, THE parser SHALL require the decoder to "
                  "consume the whole data region and produce exactly row_stride \u00d7 height bytes.")
    keep = [run_length if new_closure.match(ln) else ln for ln in _numbers_stripped(text).split("\n")
            if not re.match(r"WHEN the encoding is `(packbits|lzw_tiff|deflate_zlib|lzma_xz)`", ln)
            and "tag entry `predictor`" not in ln]
    return "\n".join(keep)


def test_tiff_emission_unchanged_except_req_17_3():
    # Hashes were taken from the emitter before Task 33 changed it (criterion numbers stripped).
    snap = json.loads((pathlib.Path(__file__).parent / "data"
                       / "tiff_pre_t33_emit_sha256.json").read_text(encoding="ascii"))
    assert len(snap) >= 20
    for name, want in snap.items():
        data = (SAMPLES_DIR / name).read_bytes()
        result = Engine().run(data)
        cands = list(getattr(result, "candidates", ()) or ())
        if getattr(result, "candidate", None) is not None:
            cands.append(result.candidate)
        if any(c.hypothesis.ranges for c in cands):
            # Requirement 17.6 (Task 35): a candidate with several ranges is a layout of kind
            # `file` with `data.ranges`; those emissions are tested in tests/test_emit_ranges.py.
            continue
        spec = emit_spec(result, data)
        got = {n: hashlib.sha256(_undo_17_3(n, t).encode("utf-8")).hexdigest() for n, t in sorted(spec.files)}
        assert got == want, name


# --- never raises, bounded output ------------------------------------------------------------------
@settings(max_examples=60, deadline=None)
@given(st.binary(max_size=600), st.sampled_from([5, 32773, 8, 34925]))
def test_reference_reader_new_decoders_never_raise(body, compression):
    layouts = {5: LZW_EOI, 32773: PACKBITS_SMALL, 8: DEFLATE_SMALL, 34925: LZMA.read_bytes()}
    raw = layouts[compression]
    layout = extract_layout(_emit(raw)[1]["requirements.md"])
    for data in (raw[:122] + body, _tiff(body, compression)):
        out = parse(layout, data)
        assert isinstance(out, dict)
        if out["ok"]:
            assert len(out["pixels"]) == out["row_stride"] * out["height"]


@settings(max_examples=100, deadline=None)
@given(st.binary(max_size=2000))
def test_reference_reader_decoders_bound_their_output(body):
    for fn in (reference_reader._packbits, reference_reader._lzw_tiff,
               reference_reader._zlib_stream, reference_reader._xz_stream):
        try:
            got = fn(body, 0, len(body), 64)
        except reference_reader._Err:
            continue
        assert len(got) == 64

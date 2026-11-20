"""Acceptance tests for spec emission (Req 9.16, 9.17, 9.18).

The reference reader is given only the emitted requirements.md text. The original
corpus bytes are the input being parsed, and the engine result is the check.
"""
import os
import re
import subprocess
import sys

import pytest

from necropsy.emit import emit_spec
from necropsy.engine import Engine
from tests.conftest import corpus_bytes
from tests.support.reference_reader import (
    extract_layout, make_parser_module, parse, parse_candidates,
)


def _emit(name):
    data = corpus_bytes(name)
    result = Engine().run(data)
    spec = emit_spec(result, data)
    assert not hasattr(spec, "message"), getattr(spec, "message", "")
    return result, dict(spec.files), spec.slug


def _read_with_markdown_only(markdown, file_bytes):
    """Reference reading: format knowledge comes only from `markdown`."""
    layout = extract_layout(markdown)
    assert isinstance(layout, dict), layout
    return parse(layout, file_bytes)


def _candidates_with_markdown_only(markdown, file_bytes):
    layout = extract_layout(markdown)
    assert isinstance(layout, dict), layout
    return parse_candidates(layout, file_bytes)


def test_mystery_e_reference_reader_reproduces_layout():  # Req 9.16
    result, files, _ = _emit("mystery_e")
    out = _read_with_markdown_only(files["requirements.md"], corpus_bytes("mystery_e"))
    assert out["ok"] is True, out
    assert (out["width"], out["height"], out["bit_depth"]) == (8, 8, 8)
    assert (out["data_start"], out["data_end"]) == (86, 150)
    assert out["pixels"] == result.candidate.decoded
    assert len(out["pixels"]) == 64


@pytest.mark.parametrize("name", ["mystery_c", "mystery_e"])
def test_emitted_tests_pass_under_pytest(name, tmp_path):  # Req 9.17
    _, files, slug = _emit(name)
    module_src = make_parser_module(files["requirements.md"])
    test_name = "test_" + slug.replace("-", "_") + ".py"  # Req 9.1
    assert test_name in files, sorted(files)
    tests_src = files[test_name]
    assert "necropsy" not in module_src.replace("necropsy-layout", "")
    assert "import necropsy" not in tests_src and "from necropsy" not in tests_src

    module_name = "parser_" + slug.replace("-", "_")
    (tmp_path / (module_name + ".py")).write_bytes(module_src.encode("utf-8"))
    (tmp_path / test_name).write_bytes(tests_src.encode("utf-8"))
    for cfg in ("pytest.ini", "setup.cfg", "tox.ini", "pyproject.toml", "conftest.py"):
        assert not (tmp_path / cfg).exists(), cfg

    env = dict(os.environ)
    env["PYTHONPATH"] = str(tmp_path)
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", str(tmp_path), "-q", "-p", "no:cacheprovider"],
        cwd=str(tmp_path), env=env, capture_output=True, text=True, timeout=300,
    )
    out = proc.stdout + proc.stderr
    assert proc.returncode == 0, out
    m = re.search(r"(\d+) passed", out)
    assert m and int(m.group(1)) >= 1, out

def test_mystery_d_candidates_include_true_layout():  # Req 9.18
    _, files, _ = _emit("mystery_d")
    outs = _candidates_with_markdown_only(files["requirements.md"], corpus_bytes("mystery_d"))
    assert any(
        o.get("ok") and (o["width"], o["height"], o["bit_depth"], o["data_start"]) == (8, 8, 8, 40)
        for o in outs
    ), outs


# --- TGA 2.0 footer declared offsets (Req 9.23, 9.24, 9.25, 1.16) ------------

import json  # noqa: E402
import struct  # noqa: E402

from necropsy.emit import emit_spec as _emit_spec  # noqa: E402
from tests.conftest import SAMPLES_DIR  # noqa: E402

_FOOTER_SIG = b"TRUEVISION-XFILE.\x00"


def _tga_header():
    # 18 bytes: id_length 0, no colour map, image_type 3 (grey, uncompressed),
    # width 8 at 0x0C, height 8 at 0x0E, 8 bpp at 0x10, descriptor 0.
    return bytes([0, 0, 3]) + bytes(9) + struct.pack("<HH", 8, 8) + bytes([8, 0])


def _area(size=495, colour=0, stamp=0, scan=0):
    # Extension area: size <H at 0; inner <I offsets at 482, 486 and 490.
    a = bytearray(max(size, 495))
    struct.pack_into("<H", a, 0, size)
    struct.pack_into("<III", a, 482, colour, stamp, scan)
    return bytes(a)


def _tga(ext=0, dev=0, between=b"", area=b""):
    """Req 1.16 layout: header [0,18), pixels [18,82), `between`, `area`, 26-byte footer."""
    footer = struct.pack("<II", ext, dev) + _FOOTER_SIG
    return _tga_header() + bytes(range(64)) + between + area + footer


def _valid_tga_layout():
    data = _tga()                       # both offsets 0, length 108
    assert len(data) == 108
    result = Engine().run(data)
    spec = _emit_spec(result, data)
    layout = extract_layout(dict(spec.files)["requirements.md"])
    assert isinstance(layout, dict)
    return layout


_AREA94 = dict(ext=94, between=bytes(12))      # 12-byte gap at [82, 94)


@pytest.mark.parametrize("data", [
    _tga(),                                                                    # len 108
    _tga(dev=82, between=bytes(10)),                                           # len 118
    _tga(area=_area(stamp=82), **_AREA94),                                     # len 615
    _tga(area=_area(scan=82), **_AREA94),
    _tga(area=_area(colour=82), **_AREA94),
    _tga(ext=82, area=_area()),                                                # len 603
], ids=["none", "developer", "postage", "scan_line", "colour", "ext_min"])
def test_reference_reader_valid_declarations_end_region_at_82(data):  # Req 1.16, 9.25
    out = parse(_valid_tga_layout(), data)
    assert out["ok"] is True, out
    assert (out["data_start"], out["data_end"]) == (18, 82)
    assert out["pixels"] == bytes(range(64))


@pytest.mark.parametrize("data", [
    _tga(dev=10),                                          # below H = 18
    _tga(dev=82),                                          # len 108, F = 82: not below F
    _tga(ext=82, area=_area(size=494)),                    # size below 495
    _tga(ext=82, area=_area(size=496)[:495]),              # 82 + 496 > F = 577
    _tga(area=_area(stamp=10), **_AREA94),                 # inner offset below H
], ids=["dev_below_H", "dev_at_F", "size_494", "size_496", "inner_below_H"])
def test_reference_reader_rejects_invalid_declarations(data):  # Req 1.16, 9.25
    out = parse(_valid_tga_layout(), data)
    assert out["ok"] is False
    assert out["error"].startswith("declared "), out


def test_reference_reader_reads_no_inner_offset_of_invalid_area():  # Req 1.15
    layout = _valid_tga_layout()
    # An area that is invalid must be rejected as an area even though its inner offset would be valid.
    data = _tga(ext=82, area=_area(size=494, stamp=82))
    assert parse(layout, data)["error"] == "declared area invalid"


def test_pillow_p_16_spec_given_to_reference_reader_yields_region():  # Req 9.25
    data = (SAMPLES_DIR / "real" / "pillow_p_16.tga").read_bytes()
    result = Engine().run(data)
    spec = _emit_spec(result, data)
    files = dict(spec.files)
    out = _read_with_markdown_only(files["requirements.md"], data)
    assert out["ok"] is True, out
    assert (out["data_start"], out["data_end"]) == (560, 16944)
    assert len(out["pixels"]) == 16384
    req = files["requirements.md"]
    for text in (
        "THE parser SHALL treat an offset of 0 as the area being absent.",
        "THE parser SHALL treat a nonzero offset as valid if and only if it lies in "
        "[header_size, trailer_start).",
        "THE parser SHALL end the data region at the minimum of the trailer start and every "
        "valid nonzero declared offset",
        "THEN THE parser SHALL reject the file and SHALL read no offset inside that area.",
    ):
        assert text in req
    assert "below 495" in req and "`extension_area_offset`" in req
    assert "`postage_stamp_offset`" in req
    assert "`developer_area_offset` at position 0x0004" in req


def test_trailer_sentence_wording_tga_declared_vs_pcx_plain():  # Req 9.23
    tga = (SAMPLES_DIR / "real" / "pillow_p_16.tga").read_bytes()
    req = dict(_emit_spec(Engine().run(tga), tga).files)["requirements.md"]
    assert ("and end the data region at offset (file length - 26) or at the earliest "
            "valid declared offset below, whichever comes first.") in req
    _, pcx_files, _ = _emit("mystery_b")
    pcx_req = pcx_files["requirements.md"]
    assert "whichever comes first" not in pcx_req
    assert ("THE parser SHALL treat the trailing 769 bytes as trailer `pcx_palette_256` "
            "and end the data region at offset (file length - 769).") in pcx_req

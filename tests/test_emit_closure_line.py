"""The emitted closure line for compressed encodings (format-coverage Task 36 follow-up).

Requirement 17.1 (every encoding is defined in the emitted text with its end conditions) and 17.11
(the run-length closure line of rle_pcx and rle_tga stays as it was). The end rules the new line
defers to are Requirements 11 (packbits), 12.8 (lzw_tiff), 13.3 to 13.6 (deflate_zlib) and 14.3
(lzma_xz): those encodings are not run-length."""
import pytest

from necropsy.emit import emit_spec
from necropsy.engine import Engine
from tests.conftest import SAMPLES_DIR
from tests.test_emit_new_layouts import CASES, _source

REAL = SAMPLES_DIR / "real"
RUN_LENGTH = ("WHEN the encoding is a run-length encoding, THE parser SHALL require the decoder to "
              "consume the whole data region and produce exactly row_stride \u00d7 height bytes.")


def _new(name):
    return ("WHEN the encoding is %s, THE parser SHALL require the decoder to end as its definition "
            "above states and to produce exactly the expected bytes for each data range." % name)


def _requirements(data):
    spec = emit_spec(Engine().run(data), data)
    return dict(spec.files)["requirements.md"]


@pytest.mark.parametrize("filename", ["imagemagick_input.pcx", "imagemagick_input.tga"])
def test_rle_pcx_and_rle_tga_keep_the_run_length_line(filename):
    text = _requirements((REAL / filename).read_bytes())
    assert RUN_LENGTH in text
    assert "THE parser SHALL require the decoder to end as its definition above" not in text


@pytest.mark.parametrize("name,source", [
    ("packbits", lambda: (REAL / "goimage_bw-packbits.tiff").read_bytes()),
    ("lzw_tiff", lambda: (REAL / "libtiff_lzw-single-strip.tiff").read_bytes()),
    ("deflate_zlib", lambda: (REAL / "goimage_bw-deflate.tiff").read_bytes()),
    ("lzma_xz", lambda: (REAL / "pillow_hopper_lzma.tif").read_bytes()),
    ("packbits", lambda: _source("packbits")),
    ("lzw_tiff", lambda: _source("lzw_single_strip")),
    ("deflate_zlib", lambda: _source("deflate")),
    ("lzma_xz", lambda: _source("lzma")),
])
def test_compressed_tiff_encodings_get_their_own_closure_line(name, source):
    text = _requirements(source())
    assert _new(name) in text
    assert RUN_LENGTH not in text
    for other in ("packbits", "lzw_tiff", "deflate_zlib", "lzma_xz"):
        if other != name:
            assert _new(other) not in text


def test_uncompressed_tiff_keeps_the_run_length_line():
    text = _requirements((REAL / "goimage_bw-uncompressed.tiff").read_bytes())
    assert RUN_LENGTH in text


def test_the_synthetic_case_names_used_above_exist():
    assert {"packbits", "lzw_single_strip", "deflate", "lzma"} <= set(CASES)

"""The corpus comparer (format-coverage Task 38; Requirements 19.2, 19.3).

Crafted inputs test each canonical form against Pillow; a corpus run checks the verdict of the files whose difference
from Pillow is known and explained. A difference is recorded as its explanation only when the explanation reproduces
Pillow's bytes exactly; otherwise it stays a mismatch.
"""
from types import SimpleNamespace

import pytest

from necropsy.engine import Engine
from tools import real_corpus as rc

Image = pytest.importorskip("PIL.Image")


def cand(decoded, stride, w, h, bd, planes=1, maxval=None, encoding="rle_pcx"):
    hyp = SimpleNamespace(width=w, height=h, bit_depth=bd, planes=planes, maxval=maxval, encoding=encoding)
    return SimpleNamespace(hypothesis=hyp, decoded=decoded, row_stride=stride)


# ---- PCX planes ---------------------------------------------------------------------------

def test_pcx_three_planes_are_deinterleaved_to_rgb():
    # 2 x 2, bytes_per_line 4 (two padding bytes per plane run): row = R run, G run, B run.
    row0 = bytes([1, 2, 0, 0, 3, 4, 0, 0, 5, 6, 0, 0])
    row1 = bytes([7, 8, 0, 0, 9, 10, 0, 0, 11, 12, 0, 0])
    c = cand(row0 + row1, 12, 2, 2, 24, planes=3)
    hdr = {"bytes_per_line": 4, "bits_per_plane": 8}
    out = rc.ours_canonical({"format": "PCX", "header": hdr}, b"", c)
    assert out == (bytes([1, 3, 5, 2, 4, 6, 7, 9, 11, 8, 10, 12]), (2, 2, 3))


def test_pcx_four_one_bit_planes_give_the_palette_index():
    # 3 x 1, bytes_per_line 2; plane p holds bit p of the index. Pixel 0: planes 1,0,1,0 = 5; pixel 1: 0,1,0,1 = 10;
    # pixel 2: 1,1,1,1 = 15.
    planes = [0b10100000, 0b01100000, 0b10100000, 0b01100000]
    decoded = b"".join(bytes([p, 0]) for p in planes)
    c = cand(decoded, 8, 3, 1, 4, planes=4)
    hdr = {"bytes_per_line": 2, "bits_per_plane": 1}
    assert rc.ours_canonical({"format": "PCX", "header": hdr}, b"", c) == (bytes([5, 10, 15]), (3, 1, 1))


def test_pcx_planes_that_are_not_rgb_or_bit_planes_say_why():
    c = cand(bytes(8), 4, 2, 2, 8, planes=2)
    out = rc.ours_canonical({"format": "PCX", "header": {"bytes_per_line": 2, "bits_per_plane": 8}}, b"", c)
    assert isinstance(out, str) and "not handled" in out


# ---- unpacked samples ---------------------------------------------------------------------

def test_twelve_bit_samples_unpack_msb_first_and_scale():
    # Two samples per 3 bytes: 0xABC and 0x123.
    c = cand(bytes([0xAB, 0xC1, 0x23]), 3, 2, 1, 12, encoding="none")
    out = rc.ours_canonical({"format": "TIFF", "header": {}}, b"", c)
    assert out == (bytes([0xABC * 255 // 4095, 0x123 * 255 // 4095]), (2, 1, 1))


def test_sixteen_bit_pnm_samples_are_big_endian_and_scaled_by_maxval():
    c = cand(bytes([0xFF, 0xFF, 0x80, 0x00, 0x00, 0x01]), 6, 1, 1, 48, maxval=65535, encoding="none")
    out = rc.ours_canonical({"format": "PNM", "header": {}}, b"", c)
    assert out == (bytes([255, 0x8000 * 255 // 65535, 0]), (1, 1, 3))


# ---- against Pillow, on crafted files ------------------------------------------------------

def pillow_pair(tmp_path, name, data, fmt, header):
    path = tmp_path / name
    path.write_bytes(data)
    result = Engine().run(data)
    assert result.status == "RESOLVED"
    entry = {"format": fmt, "header": header}
    ours = rc.ours_canonical(entry, data, result.candidate)
    theirs = rc.pillow_canonical(path, entry)
    assert isinstance(ours, tuple) and isinstance(theirs, tuple)
    return entry, path, result.candidate, ours, theirs


def pnm16(magic, w, h, words):
    return magic + f"\n{w} {h}\n65535\n".encode() + b"".join(v.to_bytes(2, "big") for v in words)


def test_sixteen_bit_rgb_pnm_differs_from_pillow_by_rounding_only(tmp_path):
    words = [0, 1, 257, 32767, 32768, 65535, 12345, 54321, 40000]
    entry, path, c, ours, theirs = pillow_pair(tmp_path, "a.ppm", pnm16(b"P6", 3, 1, words), "PNM", {})
    assert ours[0] != theirs[0]
    why = rc.explain_difference(entry, path, c, ours, theirs)
    assert why and "rounds to nearest" in why


def test_sixteen_bit_grey_pnm_differs_from_pillow_by_clipping_only(tmp_path):
    words = [0, 1, 255, 256, 40000, 65535]
    entry, path, c, ours, theirs = pillow_pair(tmp_path, "a.pgm", pnm16(b"P5", 3, 2, words), "PNM", {})
    assert ours[0] != theirs[0]
    why = rc.explain_difference(entry, path, c, ours, theirs)
    assert why and "clips to 255" in why


def test_an_explanation_that_does_not_reproduce_pillows_bytes_is_refused(tmp_path):
    words = [0, 1, 257, 32767, 32768, 65535, 12345, 54321, 40000]
    entry, path, c, ours, theirs = pillow_pair(tmp_path, "a.ppm", pnm16(b"P6", 3, 1, words), "PNM", {})
    altered = (bytes([theirs[0][0] ^ 1]) + theirs[0][1:], theirs[1])
    assert rc.explain_difference(entry, path, c, ours, altered) is None


def test_plain_text_pnm_matches_pillow(tmp_path):
    p2 = b"P2\n3 2\n255\n0 10 20\n30 40 255\n"
    p3 = b"P3\n2 1\n255\n1 2 3 250 251 252\n"
    for name, data in (("t.pgm", p2), ("t.ppm", p3)):
        _, _, _, ours, theirs = pillow_pair(tmp_path, name, data, "PNM", {})
        assert ours == theirs


def rle_tga_32(descriptor, pixels):
    # 18-byte header: id_length 0, no colour map, image type 10 (RLE true colour), 5 bytes of colour map spec (zero),
    # x and y origin 0 (4 bytes), width, height (<H), 32 bits per pixel, descriptor. Then one raw packet:
    # header byte count - 1 (bit 7 clear), then the pixels as stored (B, G, R, A).
    header = bytes([0, 0, 10]) + bytes(5) + bytes(4) + len(pixels).to_bytes(2, "little") + (1).to_bytes(2, "little")
    header += bytes([32, descriptor])
    return header + bytes([len(pixels) - 1]) + b"".join(pixels)


def test_rle_tga_without_alpha_bits_compares_colour_and_says_alpha_is_not_compared(tmp_path):
    pixels = [bytes([10, 20, 30, 0]), bytes([40, 50, 60, 7])]           # B, G, R, A as stored
    # TGA 2.0 tail: a 495-byte extension area (size field <H = 495) whose attributes type (offset 494) is 0 = "no alpha", then the 26-byte
    # footer: extension offset (<I), developer directory offset 0 (<I), "TRUEVISION-XFILE.", 0.
    body = rle_tga_32(0x00, pixels)
    ext = (495).to_bytes(2, "little") + bytes(493)
    data = body + ext + len(body).to_bytes(4, "little") + bytes(4) + b"TRUEVISION-XFILE.\x00"
    entry, path, c, ours, theirs = pillow_pair(tmp_path, "a.tga", data, "TGA",
                                               {"descriptor": 0x00, "pixel_depth": 32, "image_type": 10})
    assert ours[0][0:3] == bytes([30, 20, 10]) == theirs[0][0:3]
    why = rc.explain_difference(entry, path, c, ours, theirs)
    assert ours[0][3::4] == bytes([0, 7]) and theirs[0][3::4] == bytes([255, 255])
    assert why and why.startswith("alpha not compared")


# ---- the corpus: verdicts of the files with known differences --------------------------------

MANIFEST = {e["file"]: e for e in rc.load_manifest()}

EXPECTED = {
    "goimage_bw-packbits.tiff": rc.WHITE_IS_ZERO_VERDICT,
    "goimage_bw-deflate.tiff": rc.WHITE_IS_ZERO_VERDICT,
    "goimage_invalid-palette-ref.tiff": "not comparable: Pillow refuses the file (UnidentifiedImageError)",
    "pillow_rgb32rle.tga": "alpha not compared: the file declares no alpha (descriptor alpha bits 0, extension attributes type 0) "
                           "and Pillow reports 255; R, G, B equal Pillow's",
    "pillow_hopper_16bit.pgm": "clips to 255",
    "libtiff_rgb-3c-16b.ppm": "rounds to nearest",
    "pillow_12bit.cropped.tif": "clips to 255",
    "pillow_p_4_planes.pcx": "match",
    "sdlimage_sample.pcx": "match",
    "imagemagick_input.pcx": "match",
    "sdlimage_sample.tga": "match",
    "pillow_la.tga": "match",
    "pillow_hopper_lzma.tif": "match",
    "goimage_blue-purple-pink.lzwcompressed.tiff": "match",
    "goimage_video-001-paletted.tiff": "match",
    "pillow_tiff_tiled_raw.tif": "match",
    "pillow_tiff_strip_raw.tif": "match",
    "imagemagick_input_p1.pbm": "match",
    "imagemagick_input_p2.pgm": "match",
    "imagemagick_input_p3.ppm": "match",
    "pillow_hopper_1bit_plain.pbm": "match",
    "pillow_200x32_p_tl_rle.tga": "match",
}


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_corpus_verdict(name):
    verdicts = rc.run_one(MANIFEST[name])["pixel_verdicts"]
    assert len(verdicts) == 1
    want = EXPECTED[name]
    assert verdicts[0] == want or (want != "match" and want in verdicts[0] and verdicts[0] != "match")
    assert not verdicts[0].startswith("not comparable") or name == "goimage_invalid-palette-ref.tiff"


def test_a_known_difference_is_never_recorded_as_a_match():
    for name in ("goimage_bw-packbits.tiff", "pillow_rgb32rle.tga", "pillow_hopper_16bit.pgm"):
        assert rc.run_one(MANIFEST[name])["pixel_verdicts"] != ["match"]

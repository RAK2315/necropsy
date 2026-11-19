"""Generate the nine extension-less image files used as the engine's test corpus.

Bytes are written by hand; no imaging libraries are used.
Run from anywhere: python spike/make_samples.py

Pixel content: every uncompressed sample is drawn from scene(), a simple
spatially coherent picture (sky gradient, sun disc, flat ground). The two
RLE-compressed PCX samples keep their original gradient-and-block content,
because changing their pixels would change the RLE stream length and
therefore the file size.
"""

import struct
from pathlib import Path

OUT = Path(__file__).resolve().parent / "samples"


def scene(w: int, h: int) -> list[list[int]]:
    """Greyscale scene: sky gradient, a sun disc, flat ground in the bottom third."""
    ground = h - max(1, h // 3)
    cx, cy = 0.7 * (w - 1), 0.3 * (h - 1)
    r2 = (0.25 * min(w, h)) ** 2
    img = []
    for y in range(h):
        row = []
        for x in range(w):
            if y >= ground:
                v = 60
            else:
                v = 220 - (140 * y) // max(1, h - 1)
            if (x - cx) ** 2 + (y - cy) ** 2 <= r2:
                v = 250
            row.append(v)
        img.append(row)
    return img


def scene_grey(w: int, h: int) -> bytes:
    return bytes(v for row in scene(w, h) for v in row)


def scene_bgr(w: int, h: int) -> bytes:
    out = bytearray()
    for row in scene(w, h):
        for v in row:
            out += bytes([v, (v * 3) // 4, v // 2])   # B, G, R
    return bytes(out)


def _pcx_row(y: int, w: int) -> list[int]:
    row = [(x + y) * 16 % 256 for x in range(w)]
    if y % 4 == 0:
        row = [200] * w   # a run, so RLE actually compresses something
    return row


def pcx_rle_rows() -> bytes:
    """The 64 decoded bytes (8 rows x 8) behind mystery_b and mystery_i."""
    return bytes(v for y in range(8) for v in _pcx_row(y, 8))


def pbm_rows() -> bytes:
    """The 4 packed row bytes of mystery_a (4x4 scene, thresholded, 1 = black)."""
    rows = bytearray()
    for row in scene(4, 4):
        byte = 0
        for x, v in enumerate(row):
            if v < 128:
                byte |= 0x80 >> x
        rows.append(byte)
    return bytes(rows)


def pcx_padded_pixels() -> bytes:
    """The 48 data bytes of mystery_h: 6 rows x (6 pixels + 2 zero pad bytes)."""
    out = bytearray()
    for row in scene(6, 6):
        out += bytes(row)
        out.extend([0] * 2)
    return bytes(out)


def pixels(name: str) -> bytes:
    """Decoded data-region bytes for a RESOLVED corpus file.

    Supported: mystery_a, b, c, e, h, i. The ambiguous files (d, f, g) raise
    KeyError; no single region is "decoded" for them.
    """
    return {
        "mystery_a": pbm_rows,
        "mystery_b": pcx_rle_rows,
        "mystery_c": lambda: scene_bgr(16, 16),
        "mystery_e": lambda: scene_grey(8, 8),
        "mystery_h": pcx_padded_pixels,
        "mystery_i": pcx_rle_rows,
    }[name]()


def build_pcx() -> bytes:
    """8x8, 8 bits per pixel, single plane, RLE encoded, 256-colour palette."""
    w, h = 8, 8
    header = bytearray(128)
    header[0] = 0x0A          # manufacturer
    header[1] = 5             # version 3.0+
    header[2] = 1             # RLE encoding
    header[3] = 8             # bits per pixel per plane
    struct.pack_into("<4H", header, 4, 0, 0, w - 1, h - 1)  # xmin ymin xmax ymax
    struct.pack_into("<2H", header, 12, 72, 72)              # dpi
    header[65] = 1            # colour planes
    struct.pack_into("<H", header, 66, w)                    # bytes per line
    struct.pack_into("<H", header, 68, 1)                    # palette info: colour

    rle = bytearray()
    for y in range(h):
        row = _pcx_row(y, w)
        x = 0
        while x < w:
            run = 1
            while x + run < w and row[x + run] == row[x] and run < 63:
                run += 1
            v = row[x]
            if run > 1 or v >= 0xC0:
                rle += bytes([0xC0 | run, v])
            else:
                rle.append(v)
            x += run

    palette = bytearray()
    for i in range(256):
        palette += bytes([i, (i * 3) % 256, 255 - i])
    return bytes(header) + bytes(rle) + b"\x0c" + bytes(palette)


def build_tga() -> bytes:
    """16x16, uncompressed true-colour, 24 bits per pixel, top-left origin."""
    w, h = 16, 16
    header = struct.pack(
        "<BBBHHBHHHHBB",
        0,      # id length
        0,      # no colour map
        2,      # uncompressed true-colour
        0, 0, 0,  # colour map spec
        0, 0,   # x/y origin
        w, h,
        24,     # bits per pixel
        0x20,   # descriptor: top-left origin
    )
    return header + scene_bgr(w, h)


def build_pbm() -> bytes:
    """4x4 binary (P4) bitmap of the scene, thresholded, rows padded to whole bytes."""
    w, h = 4, 4
    return f"P4\n{w} {h}\n".encode("ascii") + pbm_rows()


def build_dib() -> bytes:
    """8x8, uncompressed, 8 bits per pixel, bare BITMAPINFOHEADER (no file header)."""
    w, h = 8, 8
    header = struct.pack(
        "<IiiHHIIiiII",
        40,     # biSize: header size in bytes
        w,      # biWidth
        h,      # biHeight
        1,      # biPlanes
        8,      # biBitCount
        0,      # biCompression: BI_RGB
        64,     # biSizeImage: 8 rows x 8 bytes, DWORD-aligned
        0,      # biXPelsPerMeter
        0,      # biYPelsPerMeter
        0,      # biClrUsed
        0,      # biClrImportant
    )
    return header + scene_grey(w, h)


def build_tiff_be() -> bytes:
    """8x8, 8 bpp, big-endian TIFF ("MM"), minimal IFD with tags 256/257/258/273/278/279."""
    w, h, bpp = 8, 8, 8
    ifd_offset = 8
    n_entries = 6
    strip_offset = ifd_offset + 2 + n_entries * 12 + 4  # = 86
    strip_bytes = w * h * (bpp // 8)                     # = 64
    buf = bytearray()
    buf += b"\x4D\x4D"
    buf += struct.pack(">H", 42)
    buf += struct.pack(">I", ifd_offset)
    buf += struct.pack(">H", n_entries)

    def entry(tag, typ, count, value):
        if typ == 3:   # SHORT: the value is left-justified in the 4-byte field
            return struct.pack(">HHIHxx", tag, typ, count, value)
        return struct.pack(">HHII", tag, typ, count, value)

    buf += entry(256, 3, 1, w)
    buf += entry(257, 3, 1, h)
    buf += entry(258, 3, 1, bpp)
    buf += entry(273, 4, 1, strip_offset)
    buf += entry(278, 3, 1, h)
    buf += entry(279, 4, 1, strip_bytes)
    buf += struct.pack(">I", 0)
    assert len(buf) == strip_offset
    return bytes(buf) + scene_grey(w, h)


def build_raw32() -> bytes:
    """12x10, 8 bpp, no probe match; width/height as little-endian uint32."""
    w, h, bpp = 12, 10, 8
    header = struct.pack("<IIBxxx", w, h, bpp)   # 12 bytes
    return header + scene_grey(w, h)


def build_raw_unusual_hdr() -> bytes:
    """8x8, 24 bpp, no probe match; non-standard 20-byte header."""
    w, h, bpp = 8, 8, 24
    magic = bytes([0xAB, 0xCD, 0xEF, 0x01])
    header = magic + struct.pack("<HHB", w, h, bpp) + bytes(11)   # 20 bytes
    return header + scene_bgr(w, h)


def build_pcx_padded() -> bytes:
    """6x6, 8 bpp, uncompressed PCX with rows padded to 4-byte boundary (8 bytes/row)."""
    w, h, bpp = 6, 6, 8
    row_stride = 8   # ceil(6/4)*4 = 8
    header = bytearray(128)
    header[0] = 0x0A; header[1] = 5; header[2] = 0; header[3] = bpp
    struct.pack_into("<4H", header, 4, 0, 0, w - 1, h - 1)   # xmin=0 ymin=0 xmax=5 ymax=5
    struct.pack_into("<2H", header, 12, 72, 72)
    header[65] = 1
    struct.pack_into("<H", header, 66, row_stride)
    struct.pack_into("<H", header, 68, 1)
    return bytes(header) + pcx_padded_pixels()


def build_pcx_corrupt_encoding() -> bytes:
    """mystery_b's RLE-compressed PCX with header byte 0x02 corrupted to 0x00.

    The header falsely declares "uncompressed". A probe that trusts the
    declaration proposes encoding "none", fails closure, and the rle_pcx
    revision strategy has to recover the real encoding.
    """
    data = bytearray(build_pcx())
    assert data[2] == 1
    data[2] = 0
    return bytes(data)


ASSIGNMENT = {
    "mystery_a": build_pbm,
    "mystery_b": build_pcx,
    "mystery_c": build_tga,
    "mystery_d": build_dib,
    "mystery_e": build_tiff_be,
    "mystery_f": build_raw32,
    "mystery_g": build_raw_unusual_hdr,
    "mystery_h": build_pcx_padded,
    "mystery_i": build_pcx_corrupt_encoding,
}

EXPECTED_SIZES = {
    "mystery_a": 11, "mystery_b": 955, "mystery_c": 786, "mystery_d": 104,
    "mystery_e": 150, "mystery_f": 132, "mystery_g": 212, "mystery_h": 176,
    "mystery_i": 955,
}


def main() -> None:
    OUT.mkdir(exist_ok=True)
    for name, builder in ASSIGNMENT.items():
        data = builder()
        assert len(data) == EXPECTED_SIZES[name], (name, len(data))
        (OUT / name).write_bytes(data)
        print(f"{name}: {len(data)} bytes")


if __name__ == "__main__":
    main()

# Ground truth:
#   mystery_a = PBM (4x4, binary P4)
#   mystery_b = PCX RLE (8x8, 8bpp)
#   mystery_c = TGA (16x16, 24bpp, uncompressed)
#   mystery_d = DIB body (8x8, 8bpp, 40-byte header)
#   mystery_e = TIFF big-endian "MM" (8x8, 8bpp, strip_offset=86)
#   mystery_f = raw 32-bit dims (12x10, 8bpp, header=12)
#   mystery_g = raw unusual header (8x8, 24bpp, header=20)
#   mystery_h = PCX padded rows (6x6, 8bpp, row_stride=8, header=128)
#   mystery_i = PCX RLE, header byte 0x02 corrupted to 0x00 (8x8, 8bpp)

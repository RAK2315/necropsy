"""Generate three small, valid, extension-less image files for the spike.

Bytes are written by hand; no imaging libraries are used.
Run from anywhere: python spike/make_samples.py
"""

import struct
from pathlib import Path

OUT = Path(__file__).resolve().parent / "samples"


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

    pixels = bytearray()
    for y in range(h):
        row = [(x + y) * 16 % 256 for x in range(w)]
        if y % 4 == 0:
            row = [200] * w   # a run, so RLE actually compresses something
        x = 0
        while x < w:
            run = 1
            while x + run < w and row[x + run] == row[x] and run < 63:
                run += 1
            v = row[x]
            if run > 1 or v >= 0xC0:
                pixels += bytes([0xC0 | run, v])
            else:
                pixels.append(v)
            x += run

    palette = bytearray()
    for i in range(256):
        palette += bytes([i, (i * 3) % 256, 255 - i])
    return bytes(header) + bytes(pixels) + b"\x0c" + bytes(palette)


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
    pixels = bytearray()
    for y in range(h):
        for x in range(w):
            pixels += bytes([x * 16, y * 16, 128])  # B, G, R
    return header + bytes(pixels)


def build_pbm() -> bytes:
    """4x4 binary (P4) bitmap, a checkerboard, rows padded to whole bytes."""
    w, h = 4, 4
    rows = bytes([0b10100000, 0b01010000, 0b10100000, 0b01010000])
    return f"P4\n{w} {h}\n".encode("ascii") + rows


ASSIGNMENT = {
    "mystery_a": build_pbm,
    "mystery_b": build_pcx,
    "mystery_c": build_tga,
}


def main() -> None:
    OUT.mkdir(exist_ok=True)
    for name, builder in ASSIGNMENT.items():
        data = builder()
        (OUT / name).write_bytes(data)
        print(f"{name}: {len(data)} bytes")


if __name__ == "__main__":
    main()

# Ground truth (randomised once at authoring time):
#   mystery_a = PBM (4x4, binary P4)
#   mystery_b = PCX (8x8)
#   mystery_c = TGA (16x16, uncompressed)

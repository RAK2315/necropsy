"""Differential run of the engine over spike/samples/real/ against Pillow (real-corpus spec).

For every file: the engine's status, candidates, path, checks and termination; for
files Pillow decodes and the engine recovers, a byte comparison of the pixels in a
canonical form (rows top to bottom, channels R,G,B,A order, padding cropped).

This module measures. It adjusts no expectation: a mismatch is recorded as a mismatch.

Run: python -m tools.real_corpus   (needs Pillow; writes spike/real_corpus_results.json)
"""
from __future__ import annotations

import hashlib
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REAL = ROOT / "spike" / "samples" / "real"
OUT = ROOT / "spike" / "real_corpus_results.json"

# The six files the manifest records as invalid by construction (README, "Invalid by construction").
INVALID_BY_CONSTRUCTION = (
    "goimage_invalid-palette-ref.tiff",
    "pillow_01r_00.pcx",
    "pillow_cross_scan_line_truncated.tga",
    "pillow_negative_size.ppm",
    "pillow_ossfuzz-4836216264589312.pcx",
    "pillow_p_8.tga",
)


# In scope, valid, FAILED; rows left as measured. pillow_cross_scan_line.tga: format-coverage Task 12 (Requirement 5.9).\n# libtiff_deflate-last-strip-extra-data.tiff: format-coverage Task 39 (Requirement 19.4, Principle call 2).
OPEN_IN_SCOPE_FAILURES = ("libtiff_deflate-last-strip-extra-data.tiff", "pillow_cross_scan_line.tga")
NOTES = {
    "pillow_ossfuzz-4836216264589312.pcx": (
        "Invalid by construction, and RESOLVED by design. The PCX probe recognised the signature and declined "
        "because the encoding byte 0x20 has no reading (engine Requirement 2.10), recording one "
        "probe_precondition_failed. Generic Search then found that 129 bytes admit a 128-byte header plus one data "
        "byte: a 2x1 1-bit image. That is a literal statement about the byte arithmetic, not a recovery claim. No PCX claim is "
        "made: the emitted spec has layout kind `file` and says it describes this one file only."),
    "pillow_rgba16.tga": (
        "Known interpretation difference, not a recovery error. The 5-bit colour values match. Pillow expands bit 15 "
        "as alpha (set = transparent here); the engine returns raw words and interprets no channel semantics."),
}
for _n in OPEN_IN_SCOPE_FAILURES:
    NOTES[_n] = "Open: in scope, valid, and FAILED. Under diagnosis in another session; row left as measured."
NOTES["pillow_cross_scan_line.tga"] = (
    "its RLE data needs one byte that lies inside its declared TGA 2.0 footer; Pillow decodes it because it ignores "
    "the footer. The file is 49 bytes. With the 26-byte footer excluded, the data region is [18, 23) = 02 00 FF FF 00: "
    "a raw packet of 3 pixels, then a raw packet header that needs 1 more pixel byte, and that byte would be byte 23, "
    "the first byte of the footer (decoder_underrun). Read to the end of the file, 25 bytes are left over "
    "(decoder_unconsumed). Both readings fail, so FAILED is correct under the spec.")
NOTES["libtiff_deflate-last-strip-extra-data.tiff"] = (
    "its last strip carries more data than the strip holds; the engine refuses it and Pillow's libtiff does not. "
    "The image is 500 x 500 with RowsPerStrip 16, so the last of 32 strips is 4 rows = 2000 bytes, and the file's "
    "last strip inflates past 2000 bytes (decoder_overrun, range 31 [12508, 12789)). The first 31 strips inflate to "
    "exactly 8000 bytes. Closure fails on that strip, so FAILED is correct under the spec (Principle call 2).")
NOTES["goimage_invalid-palette-ref.tiff"] = (
    "Invalid by construction, and RESOLVED. The Deflate decoder decodes the same region as "
    "goimage_video-001-paletted.tiff (format-coverage design.md row 25). Pillow refuses the file "
    "(UnidentifiedImageError) for palette indices the engine does not read, so there is no pixel comparison. "
    "The expected status stays FAILED: this is an unexpected RESOLVED, reported under Requirement 19.5.")


def expectation(file: str, scope: str, invalid: bool) -> str:
    if file == "pillow_ossfuzz-4836216264589312.pcx":
        return "RESOLVED"          # literal two-pixel reading; see NOTES
    if invalid or scope == "out":
        return "FAILED"
    return "RESOLVED"


def load_manifest() -> list[dict]:
    return json.loads((REAL / "manifest.json").read_text(encoding="utf-8"))["files"]


def candidates_of(result) -> list:
    if result.status == "RESOLVED":
        return [result.candidate]
    return list(getattr(result, "candidates", ()))


# ---- canonical pixels -------------------------------------------------------------------

def _crop_rows(decoded: bytes, stride: int, width: int, bit_depth: int, height: int) -> list[bytes]:
    row_bytes = math.ceil(width * bit_depth / 8)
    return [decoded[y * stride: y * stride + row_bytes] for y in range(height)]


DECODED_ENCODINGS = ("none", "rle_pcx", "rle_tga", "pnm_text", "tiff_compression_5", "tiff_compression_8",
                     "tiff_compression_32946", "tiff_compression_32773", "tiff_compression_34925")


def _pcx_planes(hdr: dict, cand, w: int, ht: int) -> tuple[bytes, tuple] | str:
    """Multi-plane PCX (Requirement 6): each scanline is `planes` runs of bytes_per_line bytes, one run per plane."""
    h = cand.hypothesis
    planes, bpl, bpp = h.planes, hdr["bytes_per_line"], hdr["bits_per_plane"]
    if len(cand.decoded) < ht * cand.row_stride or cand.row_stride != planes * bpl:
        return "decoded buffer shorter than the declared rows"
    out = bytearray()
    for y in range(ht):
        row = cand.decoded[y * cand.row_stride:(y + 1) * cand.row_stride]
        if bpp == 8 and planes in (3, 4):           # de-interleave to R,G,B(,A)
            for x in range(w):
                out += bytes(row[p * bpl + x] for p in range(planes))
        elif bpp == 1:                              # plane p holds bit p of the palette index
            for x in range(w):
                out.append(sum(((row[p * bpl + x // 8] >> (7 - x % 8)) & 1) << p for p in range(planes)))
        else:
            return f"PCX {planes} planes of {bpp} bits not handled by the comparer"
    return bytes(out), (w, ht, planes if bpp == 8 else 1)


def _samples(cand, w: int, ht: int, bits: int, per_pixel: int) -> list[int]:
    """Unpack stored samples, most significant bit first (PNM 16-bit big-endian; TIFF 12-bit MSB-first)."""
    out = []
    for y in range(ht):
        row = cand.decoded[y * cand.row_stride:(y + 1) * cand.row_stride]
        acc = 0
        nbits = 0
        pos = 0
        for _ in range(w * per_pixel):
            while nbits < bits:
                acc = (acc << 8) | row[pos]
                pos += 1
                nbits += 8
            nbits -= bits
            out.append((acc >> nbits) & ((1 << bits) - 1))
            acc &= (1 << nbits) - 1
    return out


def _high_bit_depth(fmt: str, cand, w: int, ht: int, bd: int) -> tuple[bytes, tuple] | str:
    """PNM above 8 bits per sample and TIFF 12-bit: samples unpacked, then shown at 8 bits as v * 255 // maxval
    (Requirement 16.1). Pillow's own 8-bit conversion differs; see explain_difference."""
    h = cand.hypothesis
    if fmt == "TIFF":
        bits, per_pixel, maxval = 12, 1, 4095
    elif bd in (16, 48):
        bits, per_pixel, maxval = 16, bd // 16, h.maxval
    else:
        return f"PNM bit depth {bd} not handled by the comparer"
    if not maxval or len(cand.decoded) < ht * cand.row_stride:
        return "decoded buffer shorter than the declared rows"
    words = _samples(cand, w, ht, bits, per_pixel)
    return bytes(v * 255 // maxval for v in words), (w, ht, per_pixel)


def ours_canonical(entry: dict, data: bytes, cand) -> tuple[bytes, tuple] | str:
    """The engine's recovered pixels in canonical form, or a string saying why they cannot be compared.

    Canonical: rows top to bottom; per pixel the channels in R,G,B,A (or L,A, or index) order;
    1-bit images as one byte per pixel, 1 meaning white; TGA 16-bit colour as 4 bytes of 5,5,5,1 bits.
    Returns (bytes, (width, height, channels)).
    """
    h = cand.hypothesis
    w, ht, bd = h.width, h.height, h.bit_depth
    fmt = entry["format"]
    hdr = entry["header"]
    if h.encoding not in DECODED_ENCODINGS:
        return f"encoding {h.encoding} not handled by the comparer"
    # Every decoder returns the raster as stored (decoded bytes, one row_stride per row), so the canonical form of a
    # compressed layout is the canonical form of the same raster uncompressed.
    if fmt == "PCX" and h.planes > 1:
        return _pcx_planes(hdr, cand, w, ht)
    if (fmt == "PNM" and bd in (16, 48)) or (fmt == "TIFF" and bd == 12):
        return _high_bit_depth(fmt, cand, w, ht, bd)
    rows = _crop_rows(cand.decoded, cand.row_stride, w, bd, ht)
    if len(rows) != ht or any(len(r) != math.ceil(w * bd / 8) for r in rows):
        return "decoded buffer shorter than the declared rows"
    if fmt == "TGA":
        itype = data[2]
        if not data[0x11] & 0x20:
            rows = rows[::-1]                      # bit 5 clear: rows are stored bottom to top
        if bd == 8:
            ch = 1
            px = [bytes(r) for r in rows]
        elif bd == 16 and itype in (3, 11):
            ch = 2                                 # grey + alpha
            px = rows
        elif bd == 16:
            ch = 4                                 # 5-5-5-1, little-endian word
            px = []
            for r in rows:
                out = bytearray()
                for x in range(w):
                    word = r[2 * x] | (r[2 * x + 1] << 8)
                    out += bytes(((word >> 10) & 31, (word >> 5) & 31, word & 31, (word >> 15) & 1))
                px.append(bytes(out))
        elif bd in (24, 32):
            ch = bd // 8
            px = []
            for r in rows:
                out = bytearray(r)
                for x in range(w):
                    o = x * ch
                    out[o], out[o + 2] = r[o + 2], r[o]   # B,G,R(,A) to R,G,B(,A)
                px.append(bytes(out))
        else:
            return f"TGA bit depth {bd} not handled by the comparer"
        return b"".join(px), (w, ht, ch)
    if bd == 1:
        if fmt == "PNM":
            white_is = 0                             # PBM: 1 is black
        elif fmt == "PCX":
            white_is = 1
        elif fmt == "TIFF":
            white_is = 0 if hdr.get("photometric") == 0 else 1
        else:
            return "1-bit format not handled"
        out = bytearray()
        for r in rows:
            for x in range(w):
                bit = (r[x // 8] >> (7 - x % 8)) & 1
                out.append(1 if bit == white_is else 0)
        return bytes(out), (w, ht, 1)
    if bd == 8:
        return b"".join(rows), (w, ht, 1)
    if bd in (24, 32) and fmt in ("TIFF", "PNM"):
        return b"".join(rows), (w, ht, bd // 8)
    return f"{fmt} bit depth {bd} not handled by the comparer"


def _pillow_words(raw: bytes, mode: str) -> list[int]:
    """Pillow's raw grey samples: mode I is native-endian int32, mode I;16 is little-endian uint16."""
    if mode == "I":
        return [int.from_bytes(raw[i:i + 4], sys.byteorder, signed=True) for i in range(0, len(raw), 4)]
    return [int.from_bytes(raw[i:i + 2], "little") for i in range(0, len(raw), 2)]


def pillow_canonical(path: Path, entry: dict) -> tuple[bytes, tuple] | str:
    from PIL import Image
    Image.MAX_IMAGE_PIXELS = None
    try:
        with Image.open(path) as im:
            im.load()
            mode, (w, h) = im.mode, im.size
            raw = im.tobytes()
            if mode == "1":
                # Pillow 1-bit tobytes() packs rows; unpack to one byte per pixel, 1 = white.
                rb = math.ceil(w / 8)
                out = bytearray()
                for y in range(h):
                    row = raw[y * rb:(y + 1) * rb]
                    for x in range(w):
                        out.append(1 if (row[x // 8] >> (7 - x % 8)) & 1 else 0)
                return bytes(out), (w, h, 1)
            if mode in ("L", "P"):
                return raw, (w, h, 1)
            if mode in ("I", "I;16"):
                # Pillow's own 8-bit conversion of a >8-bit grey sample clips to 255 (convert("L"), convert("RGB")).
                return bytes(min(255, v) for v in _pillow_words(raw, mode)), (w, h, 1)
            if mode == "LA":
                return raw, (w, h, 2)
            if mode == "RGB":
                return raw, (w, h, 3)
            if mode == "RGBA":
                if entry["format"] == "TGA" and entry["header"].get("pixel_depth") == 16:
                    out = bytearray()
                    for i in range(0, len(raw), 4):
                        r, g, b, a = raw[i:i + 4]
                        out += bytes((r >> 3, g >> 3, b >> 3, 1 if a >= 128 else 0))
                    return bytes(out), (w, h, 4)
                return raw, (w, h, 4)
            return f"Pillow mode {mode} not handled by the comparer"
    except Exception as exc:  # Pillow refusing is recorded, not raised
        return f"Pillow error: {type(exc).__name__}: {exc}"


WHITE_IS_ZERO_VERDICT = "stored bytes; equals Pillow after WhiteIsZero inversion (tag 262 = 0)"


def _pillow_raw(path: Path) -> tuple[str, bytes]:
    from PIL import Image
    Image.MAX_IMAGE_PIXELS = None
    with Image.open(path) as im:
        im.load()
        return im.mode, im.tobytes()


def _tga_attributes_type(data: bytes) -> int | None:
    """The attributes type byte of a TGA 2.0 extension area (offset 494), or None when there is no such area."""
    if len(data) < 26 or not data[-18:] == b"TRUEVISION-XFILE.\x00":
        return None
    ext = int.from_bytes(data[-26:-22], "little")
    return data[ext + 494] if ext and ext + 495 <= len(data) else None


def explain_difference(entry: dict, path: Path, cand, ours: tuple, theirs: tuple) -> str | None:
    """Name a difference that is fully explained, or return None. A verdict is returned only after the explanation has
    been checked byte for byte against Pillow's pixels; anything else stays a mismatch (Requirement 19.3)."""
    h = cand.hypothesis
    fmt = entry["format"]
    mode, raw = _pillow_raw(path)
    if fmt == "PNM" and h.maxval == 65535 and h.bit_depth in (16, 48):
        words = _samples(cand, h.width, h.height, 16, h.bit_depth // 16)
        if mode == "RGB" and theirs[0] == bytes((v * 255 + 32767) // 65535 for v in words):
            return ("16-bit samples: engine v * 255 // maxval (Requirement 16.1); Pillow rounds to nearest, "
                    "(v * 255 + 32767) // 65535; every byte checked")
        if mode == "I" and _pillow_words(raw, mode) == words and theirs[0] == bytes(min(255, v) for v in words):
            return ("16-bit samples: engine v * 255 // maxval (Requirement 16.1); Pillow's mode I holds the same raw "
                    "samples and its 8-bit conversion clips to 255; every byte checked")
    if fmt == "TIFF" and h.bit_depth == 12 and mode == "I;16":
        words = _samples(cand, h.width, h.height, 12, 1)
        if _pillow_words(raw, mode) == words and theirs[0] == bytes(min(255, v) for v in words):
            return ("12-bit samples: engine v * 255 // 4095 (Requirement 16.1); Pillow's mode I;16 holds the same raw "
                    "samples and its 8-bit conversion clips to 255; every byte checked")
    if fmt == "TGA" and h.bit_depth == 32 and ours[1][2] == 4 and theirs[1][2] == 4 and not entry["header"]["descriptor"] & 0x0F:
        # Pillow fills alpha with 255 when the TGA 2.0 extension area's attributes type (offset 494) is 0, "no alpha".
        if _tga_attributes_type(path.read_bytes()) == 0 and ours[0][0::4] == theirs[0][0::4] \
                and ours[0][1::4] == theirs[0][1::4] and ours[0][2::4] == theirs[0][2::4] \
                and set(theirs[0][3::4]) <= {255}:
            return ("alpha not compared: the file declares no alpha (descriptor alpha bits 0, extension attributes "
                    "type 0) and Pillow reports 255; R, G, B equal Pillow's")
    return None


def first_difference(ours: tuple, theirs: tuple) -> str:
    """Where the canonical forms first differ: pixel (x, y), channel, both values. For reporting."""
    (w, _h, ch), a, b = ours[1], ours[0], theirs[0]
    for i, (p, q) in enumerate(zip(a, b)):
        if p != q:
            px = i // ch
            return f"pixel ({px % w}, {px // w}) channel {i % ch}: ours {p}, Pillow {q}"
    return "no differing byte in the common length"


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


# ---- the run ----------------------------------------------------------------------------

def describe(c) -> dict:
    h = c.hypothesis
    return {"width": h.width, "height": h.height, "bit_depth": h.bit_depth,
            "header_size": h.header_size, "row_alignment": h.row_alignment,
            "encoding": h.encoding, "probe": h.probe_name, "path": list(h.revision_path),
            "data_start": c.data_start, "data_end": c.data_end}


def run_one(entry: dict, with_pillow: bool = True) -> dict:
    from necropsy.engine import Engine
    path = REAL / entry["file"]
    data = path.read_bytes()
    result = Engine().run(data)
    cands = candidates_of(result)
    row = {
        "file": entry["file"],
        "format": entry["format"],
        "scope": entry["scope"],
        "scope_reason": entry["scope_reason"],
        "invalid_by_construction": entry["file"] in INVALID_BY_CONSTRUCTION,
        "our_status": result.status,
        "stage": getattr(result, "stage", None),
        "termination": getattr(result, "termination", None),
        "checks": result.total_checks,
        "candidates": [describe(c) for c in cands],
        "expected_status": expectation(entry["file"], entry["scope"],
                                       entry["file"] in INVALID_BY_CONSTRUCTION),
        "note": NOTES.get(entry["file"], ""),
        "pillow_error": entry["pillow"]["error"],
        "pillow_decodes": entry["pillow"]["decodes"],
        "pillow_mode": entry["pillow"]["mode"],
        "pillow_size": entry["pillow"]["size"],
    }
    verdicts = []
    pillow_hash = None
    if cands and entry["pillow"]["decodes"] and with_pillow:
        theirs = pillow_canonical(path, entry)
        if isinstance(theirs, tuple):
            pillow_hash = _sha(theirs[0])
        for c in cands:
            ours = ours_canonical(entry, data, c)
            if isinstance(ours, str):
                verdicts.append(f"not comparable: {ours}")
            elif isinstance(theirs, str):
                verdicts.append(f"not comparable: {theirs}")
            elif ours[1] != theirs[1]:
                verdicts.append(f"dimensions differ: ours {ours[1]}, Pillow {theirs[1]}")
            elif ours[0] == theirs[0]:
                # 1-bit WhiteIsZero: the engine's bytes are the stored ones; the canonical form inverts them like Pillow.
                white_is_zero = (entry["format"] == "TIFF" and c.hypothesis.bit_depth == 1
                                 and entry["header"].get("photometric") == 0)
                verdicts.append(WHITE_IS_ZERO_VERDICT if white_is_zero else "match")
            else:
                why = explain_difference(entry, path, c, ours, theirs)
                if why:
                    verdicts.append(why)
                else:
                    n = sum(1 for a, b in zip(ours[0], theirs[0]) if a != b)
                    verdicts.append(f"mismatch: {n} of {len(ours[0])} canonical bytes differ")
    elif cands and not entry["pillow"]["decodes"] and with_pillow:
        verdicts.append(f"not comparable: Pillow refuses the file ({(entry['pillow']['error'] or '').split(':')[0]})")
    row["pixel_verdicts"] = verdicts
    row["pillow_pixels_sha256"] = pillow_hash
    return row


def run_all(with_pillow: bool = True) -> list[dict]:
    return [run_one(e, with_pillow) for e in load_manifest()]


def _pillow_cell(r: dict) -> str:
    if r["pillow_decodes"]:
        return f"decodes (mode {r['pillow_mode']}) {r['pillow_size'][0]}x{r['pillow_size'][1]}"
    err = (r["pillow_error"] or "").split(":")[0]
    return f"refuses ({err})"


def _status_cell(r: dict) -> str:
    if r["our_status"] == "FAILED":
        return f"FAILED ({r['termination']})"
    return r["our_status"]


def _pixels_cell(r: dict) -> str:
    v = r["pixel_verdicts"]
    if not v:
        return "n/a"
    if v == ["match"]:
        return "match"
    text = "; ".join(v)
    if r["note"] and "interpretation" in r["note"]:
        return text + " (known interpretation difference)"
    return text


def write_markdown(rows: list[dict], path: Path) -> None:
    lines = [
        "# Real-corpus results",
        "",
        "Generated by `python -m tools.real_corpus` from `spike/samples/real/` (81 files). Do not edit by hand.",
        "Design, decisions and limits: `.kiro/specs/real-corpus/design.md`.",
        "",
        "| File | Format | Scope | Our status | Pillow 12.2.0 | Pixels vs Pillow | Note |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        scope = r["scope"]
        if r["invalid_by_construction"]:
            scope += ", invalid by construction"
        note = r["note"] or (r["scope_reason"] if r["scope"] == "out" else "")
        lines.append(f"| `{r['file']}` | {r['format']} | {scope} | {_status_cell(r)} | {_pillow_cell(r)} "
                     f"| {_pixels_cell(r)} | {note} |")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


MD_OUT = ROOT / "docs" / "REAL-CORPUS-RESULTS.md"


if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(ROOT))
    rows = run_all()
    OUT.write_text(json.dumps(rows, indent=1) + "\n", encoding="utf-8")
    write_markdown(rows, MD_OUT)
    for r in rows:
        print(f"{r['file']:55} {r['scope']:3} {r['our_status']:22} {r['termination'] or '':20} "
              f"{';'.join(r['pixel_verdicts'])[:60]}")
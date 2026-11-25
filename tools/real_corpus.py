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


# In scope, valid, FAILED; rows left as measured. pillow_cross_scan_line.tga: format-coverage Task 12 (Requirement 5.9).
OPEN_IN_SCOPE_FAILURES = ("pillow_cross_scan_line.tga",)
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
    if h.encoding != "none" and not (fmt == "PCX" and h.encoding == "rle_pcx"):
        return f"encoding {h.encoding} not handled by the comparer"
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
                verdicts.append("match")
            else:
                n = sum(1 for a, b in zip(ours[0], theirs[0]) if a != b)
                verdicts.append(f"mismatch: {n} of {len(ours[0])} canonical bytes differ")
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
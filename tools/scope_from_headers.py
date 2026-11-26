"""Set `scope` and `scope_reason` in spike/samples/real/manifest.json from each file's header bytes.

format-coverage Requirement 18.1 to 18.3, 18.5. Only the file's bytes are read (the format family comes from the file
name's extension, which is how the corpus names its files). No other manifest field decides scope, no engine result is
used, and nothing from `necropsy` is imported. Only `scope` and `scope_reason` are written.

Rules (Requirement 18.1):
- PCX: byte 0 is 0x0A, encoding byte (offset 2) is 0 or 1, and planes (offset 65) is at least 1.
- TGA: image type (offset 2) is 1, 2, 3, 9, 10 or 11.
- TIFF: Compression 1, 5, 8, 32773, 32946 or 34925; PlanarConfiguration 1; Predictor absent or 1; every BitsPerSample
  entry equal; strips (tag 273) or tiles (tag 324). Samples per pixel and a looping IFD chain are not limits.
- PNM: magic P1, P2, P3, P5 or P6 followed by a whitespace byte, or exactly b"P4\\n".

Usage: python -m tools.scope_from_headers          (rewrites the manifest)
       python -m tools.scope_from_headers --check  (exit 1 if the manifest differs)
"""
import json
import struct
import sys
from pathlib import Path

REAL = Path(__file__).resolve().parent.parent / "spike" / "samples" / "real"
MANIFEST = REAL / "manifest.json"

TIFF_COMPRESSIONS_IN = {1, 5, 8, 32773, 32946, 34925}
TIFF_COMPRESSION_NAMES = {
    1: "none", 2: "CCITT RLE", 3: "CCITT G3", 4: "CCITT G4", 5: "LZW", 6: "OJPEG", 7: "JPEG", 8: "Adobe Deflate",
    32773: "PackBits", 32946: "Deflate", 34676: "SGILog", 34677: "SGILog24", 34925: "LZMA", 50001: "WebP",
    50000: "ZSTD",
}
TGA_TYPES_IN = {1, 2, 3, 9, 10, 11}
PNM_WHITESPACE = b" \t\n\v\f\r"
_TIFF_TYPE_SIZE = {1: 1, 3: 2, 4: 4, 8: 2, 9: 4}
_TIFF_TYPE_FMT = {1: "B", 3: "H", 4: "I", 8: "h", 9: "i"}


def _tiff_ifd0(data):
    """Return {tag: [values]} of the first IFD, or None when the bytes do not hold a readable one."""
    if len(data) < 8 or data[:2] not in (b"II", b"MM"):
        return None
    e = "<" if data[:2] == b"II" else ">"
    if struct.unpack_from(e + "H", data, 2)[0] != 42:
        return None
    off = struct.unpack_from(e + "I", data, 4)[0]
    if off + 2 > len(data):
        return None
    n = struct.unpack_from(e + "H", data, off)[0]
    if off + 2 + 12 * n > len(data):
        return None
    tags = {}
    for i in range(n):
        tag, typ, count, raw = struct.unpack_from(e + "HHI4s", data, off + 2 + 12 * i)
        size = _TIFF_TYPE_SIZE.get(typ)
        if size is None or count > 1 << 20:
            tags[tag] = []
            continue
        total = size * count
        if total <= 4:
            blob = raw[:total]
        else:
            p = struct.unpack(e + "I", raw)[0]
            if p + total > len(data):
                return None
            blob = data[p:p + total]
        tags[tag] = list(struct.unpack(e + str(count) + _TIFF_TYPE_FMT[typ], blob))
    return tags


def _tiff_scope(data):
    t = _tiff_ifd0(data)
    if t is None:
        return "out", "malformed TIFF header"
    comp = (t.get(259) or [1])[0]
    name = TIFF_COMPRESSION_NAMES.get(comp, f"code {comp}")
    planar = (t.get(284) or [1])[0]
    predictor = (t.get(317) or [1])[0]
    bits = t.get(258) or [1]
    tiled = 324 in t
    layout = f"{len(t[324])} tiles" if tiled else (
        f"{len(t[273])} strip{'s' if len(t[273]) != 1 else ''}" if 273 in t else "no strips or tiles")
    if comp not in TIFF_COMPRESSIONS_IN:
        return "out", f"compression {name} ({comp})"
    if planar != 1:
        return "out", f"planar configuration {planar}"
    if predictor != 1:
        return "out", f"predictor {predictor}"
    if len(set(bits)) != 1:
        return "out", f"BitsPerSample entries differ {bits}"
    if 273 not in t and not tiled:
        return "out", "no strips or tiles"
    return "in", f"compression {name} ({comp}), {layout}"


def _pcx_scope(data):
    if len(data) < 128 or data[0] != 0x0A:
        return "out", "malformed PCX header"
    enc, planes = data[2], data[65]
    if enc not in (0, 1):
        return "out", f"PCX encoding byte {enc}"
    if planes < 1:
        return "out", f"PCX planes {planes}"
    return "in", f"PCX encoding {enc}, {planes} plane{'s' if planes != 1 else ''}"


def _tga_scope(data):
    if len(data) < 18:
        return "out", "malformed TGA header"
    t = data[2]
    if t not in TGA_TYPES_IN:
        return "out", f"TGA image type {t}"
    return "in", f"TGA image type {t}"


def _pnm_scope(data):
    if data[:3] == b"P4\n":
        return "in", "magic P4 followed by newline"
    if len(data) >= 2 and data[0:1] == b"P" and data[1:2] in (b"1", b"2", b"3", b"5", b"6"):
        if len(data) >= 3 and data[2] in PNM_WHITESPACE:
            return "in", f"magic P{chr(data[1])} followed by whitespace"
        return "out", f"magic P{chr(data[1])} not followed by a whitespace byte"
    if data[:2] == b"P4":
        return "out", "magic P4 not followed by a newline"
    return "out", "no PNM magic"


def scope_for(name, data):
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    if ext in ("tif", "tiff"):
        return _tiff_scope(data)
    if ext == "pcx":
        return _pcx_scope(data)
    if ext == "tga":
        return _tga_scope(data)
    if ext in ("pbm", "pgm", "ppm", "pnm"):
        return _pnm_scope(data)
    return "out", "unknown format"


def rewrite(manifest, real=REAL):
    """Return a copy of `manifest` with scope and scope_reason set from the file bytes; nothing else changes."""
    out = json.loads(json.dumps(manifest))
    for rec in out["files"]:
        rec["scope"], rec["scope_reason"] = scope_for(rec["file"], (real / rec["file"]).read_bytes())
    return out


def dumps(manifest):
    return json.dumps(manifest, indent=1, ensure_ascii=False)


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    current = json.loads(MANIFEST.read_text(encoding="utf-8"))
    text = dumps(rewrite(current))
    if "--check" in argv:
        return 0 if MANIFEST.read_text(encoding="utf-8") == text else 1
    MANIFEST.write_text(text, encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())

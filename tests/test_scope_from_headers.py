"""tools/scope_from_headers.py (format-coverage Requirement 18.1 to 18.3, 18.5, 18.6, Task 37).

The manifest on disk must equal the script's output, the script may change only `scope` and `scope_reason`, and no
file's bytes or SHA-256 change. The rules are exercised on bytes built here from their documented layouts.
"""
import hashlib
import json
import struct

from hypothesis import given, strategies as st

from tools import scope_from_headers as sfh

TEXT = sfh.MANIFEST.read_text(encoding="utf-8")
MANIFEST = json.loads(TEXT)


def test_manifest_equals_the_scripts_output():
    assert sfh.dumps(sfh.rewrite(MANIFEST)) == TEXT


def test_script_writes_only_scope_and_scope_reason_and_hashes_hold():
    new = sfh.rewrite(MANIFEST)
    assert len(new["files"]) == 81
    for a, b in zip(MANIFEST["files"], new["files"]):
        assert {k for k in a if a[k] != b[k]} <= {"scope", "scope_reason"}
        assert hashlib.sha256((sfh.REAL / a["file"]).read_bytes()).hexdigest() == a["sha256"] == b["sha256"]


def tiff(tags, big=False):
    """Little-endian TIFF with one IFD at offset 8; `tags` is {tag: (type, [values])}, all values inline (<= 4 bytes)."""
    entries = b""
    for tag in sorted(tags):
        typ, vals = tags[tag]
        raw = struct.pack("<" + {3: "H", 4: "I"}[typ] * len(vals), *vals).ljust(4, b"\0")
        entries += struct.pack("<HHI4s", tag, typ, len(vals), raw)
    return b"II*\0" + struct.pack("<I", 8) + struct.pack("<H", len(tags)) + entries + b"\0\0\0\0"


BASE = {256: (3, [1]), 257: (3, [1]), 258: (3, [8]), 259: (3, [1]), 273: (4, [0]), 279: (4, [1])}


def test_tiff_rules():
    assert sfh.scope_for("a.tif", tiff(BASE))[0] == "in"
    for comp in (1, 5, 8, 32773, 32946, 34925):
        assert sfh.scope_for("a.tif", tiff({**BASE, 259: (3, [comp])}))[0] == "in", comp
    assert sfh.scope_for("a.tif", tiff({**BASE, 259: (3, [4])})) == ("out", "compression CCITT G4 (4)")
    assert sfh.scope_for("a.tif", tiff({**BASE, 284: (3, [2])})) == ("out", "planar configuration 2")
    assert sfh.scope_for("a.tif", tiff({**BASE, 317: (3, [2])})) == ("out", "predictor 2")
    assert sfh.scope_for("a.tif", tiff({**BASE, 317: (3, [1])}))[0] == "in"
    assert sfh.scope_for("a.tif", tiff({**BASE, 258: (3, [8, 16])}))[0] == "out"
    tiled = {k: v for k, v in BASE.items() if k != 273}
    tiled[324] = (4, [0])
    assert sfh.scope_for("a.tif", tiff(tiled))[0] == "in"
    assert sfh.scope_for("a.tif", tiff(tiled)[:20]) == ("out", "malformed TIFF header")
    assert sfh.scope_for("a.tif", tiff({k: v for k, v in BASE.items() if k != 273})) == ("out", "no strips or tiles")


def test_pcx_tga_pnm_rules():
    pcx = bytearray(128)
    pcx[0], pcx[2], pcx[65] = 0x0A, 1, 3
    assert sfh.scope_for("a.pcx", bytes(pcx))[0] == "in"
    pcx[2] = 32
    assert sfh.scope_for("a.pcx", bytes(pcx)) == ("out", "PCX encoding byte 32")
    pcx[2], pcx[65] = 1, 0
    assert sfh.scope_for("a.pcx", bytes(pcx)) == ("out", "PCX planes 0")
    for t, scope in ((0, "out"), (1, "in"), (2, "in"), (3, "in"), (9, "in"), (10, "in"), (11, "in"), (32, "out")):
        assert sfh.scope_for("a.tga", bytes([0, 0, t]) + bytes(15))[0] == scope, t
    for magic, scope in ((b"P1 ", "in"), (b"P2\n", "in"), (b"P3\t", "in"), (b"P4\n", "in"), (b"P4 ", "out"),
                         (b"P5\r", "in"), (b"P6\n", "in"), (b"P63", "out"), (b"P7\n", "out"), (b"Q1\n", "out")):
        assert sfh.scope_for("a.pnm", magic + b"1 1\n")[0] == scope, magic


@given(st.binary(max_size=300), st.sampled_from(["a.tif", "a.pcx", "a.tga", "a.pbm", "a.xyz", "noext"]))
def test_never_raises_and_returns_scope_and_reason(data, name):
    scope, reason = sfh.scope_for(name, data)
    assert scope in ("in", "out") and isinstance(reason, str) and reason

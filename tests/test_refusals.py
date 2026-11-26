"""Refusals and the standard-library rule (format-coverage Requirements 2.2, 2.3, 2.5, 2.6, Task 27)."""
import ast
import pathlib
import struct
import sys

from hypothesis import given, settings, strategies as st

from necropsy.engine import Engine
from necropsy.engine import probes
from necropsy.engine.closure import check_closure
from necropsy.engine.probes import probe_tiff
from tests.test_tiff_strips import SHORT, build_tiff

PIXELS = bytes(range(6))
ENGINE_DIR = pathlib.Path(probes.__file__).parent


def tiff(compression=1, planar=None):
    # Tag 259 (Compression) and, optionally, tag 284 (PlanarConfiguration) are SHORT entries.
    patch = {259: (SHORT, 1, struct.pack("<H", compression) + b"\x00\x00")}
    if planar is not None:
        patch[284] = (SHORT, 1, struct.pack("<H", planar) + b"\x00\x00")
    return build_tiff(b"II", [PIXELS], 3, 2, 2, patch=patch)


def test_unsupported_compressions_fail_naming_the_code():  # Req 2.2
    for code in (2, 3, 4, 6, 7, 34676, 50000, 50001):
        data = tiff(compression=code)
        out = probe_tiff(data)
        assert out.seed.encoding == f"tiff_compression_{code}"
        verdict = check_closure(out.seed, data)
        assert not verdict.ok and verdict.reason == "unsupported_encoding"
        assert Engine().run(data).status == "FAILED"


def test_planar_configuration_2_is_refused():  # Req 2.3
    data = tiff(planar=2)
    out = probe_tiff(data)
    hits = [r for r in out.rejections if r.reason == "probe_precondition_failed"]
    assert hits and "planar_configuration 2 is not 1" in " ".join(r.detail for r in hits)
    assert Engine().run(data).status == "FAILED"


def bmp():
    # 14-byte file header (BM, size, 2 reserved words, offset 54) + 40-byte BITMAPINFOHEADER
    # (2x2, 1 plane, 24 bpp) + 16 pixel bytes.
    head = b"BM" + struct.pack("<IHHI", 70, 0, 0, 54)
    info = struct.pack("<IiiHHIIiiII", 40, 2, 2, 1, 24, 0, 16, 0, 0, 0, 0)
    return head + info + bytes(16)


def test_bmp_header_gets_no_seed_from_any_probe():  # Req 2.5
    data = bmp()
    assert len(data) == 70
    for name in dir(probes):
        fn = getattr(probes, name)
        if name.startswith("probe_") and callable(fn):
            out = fn(data)
            assert out is None or out.seed is None, name


def test_engine_modules_import_only_the_standard_library():  # Req 2.6
    stdlib = set(sys.stdlib_module_names)
    mods = sorted(ENGINE_DIR.glob("*.py"))
    assert mods
    for path in mods:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                roots = [a.name.split(".")[0] for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                if node.level:
                    continue  # relative: the engine itself
                roots = [(node.module or "").split(".")[0]]
            else:
                continue
            for root in roots:
                assert root in stdlib or root == "necropsy", f"{path.name} imports {root}"
                if root == "necropsy":
                    assert node.module is None or node.module.startswith("necropsy.engine") or node.module == "necropsy", path.name


@settings(max_examples=100, deadline=None)
@given(st.binary(max_size=200), st.sampled_from([2, 3, 4, 6, 7, 34676, 50000, 50001]))
def test_refused_compressions_never_raise(blob, code):
    for data in (tiff(code) + blob, blob):
        r = Engine().run(data)
        assert isinstance(r.status, str)

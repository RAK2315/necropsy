"""External samples (Pillow-written): exact pixels against source.ppm. Requirement 11.15 and 11.16."""
import pytest

from necropsy.engine import Engine
from tests.conftest import REPO_ROOT
from web.serialise import to_payload

EXT = REPO_ROOT / "spike" / "samples" / "external"


def read_ppm(path):
    raw = path.read_bytes()
    assert raw.startswith(b"P6\n")
    parts = raw.split(b"\n", 3)
    w, h = map(int, parts[1].split())
    return w, h, parts[3]


def payload(name):
    data = (EXT / name).read_bytes()
    return to_payload(Engine().run(data), data, 1.0)


def test_readme_states_provenance():
    text = (EXT / "README.md").read_text(encoding="utf-8")
    assert "Pillow" in text and "not by this project's code" in text and "PIL" not in text.split("Tool:")[0]


def test_source_ppm_is_the_fixed_size():
    w, h, body = read_ppm(EXT / "source.ppm")
    assert (w, h) == (64, 48) and len(body) == 64 * 48 * 3


def test_external_a_pcx_resolves_with_exact_palette_pixels():
    p = payload("external_a")
    assert p["status"] == "RESOLVED"
    c = p["candidates"][0]
    w, h, body = read_ppm(EXT / "source.ppm")
    import base64
    assert (c["render"]["width"], c["render"]["height"], c["render"]["channels"]) == (w, h, "rgb8")
    assert base64.b64decode(c["render"]["data_b64"]) == body
    assert "palette: pcx_palette_256" in c["render"]["note"]


# History: on 2026-11-19 the engine returned FAILED/exhausted for external_b with an arithmetic_mismatch of 26 bytes,
# because Pillow writes the TGA 2.0 footer and the Trailer Registry knew only pcx_palette_256. This test was a strict
# xfail until the engine added the tga2_footer entry (commit 53973dc); it then passed with no change here.
def test_external_b_tga_resolves_upright_with_flip_note():
    p = payload("external_b")
    assert p["status"] == "RESOLVED"
    c = p["candidates"][0]
    w, h, body = read_ppm(EXT / "source.ppm")
    import base64
    assert base64.b64decode(c["render"]["data_b64"]) == body            # upright, no flip in the test
    assert "rows flipped: file declares bottom-left origin" in c["render"]["note"]


def test_external_b_tga2_footer_is_excluded_from_the_data_region():
    """Regression guard for the tga2_footer trailer entry, from the 2026-11-19 finding.

    external_b is 18 header bytes + 64 x 48 x 3 pixel bytes + the 26-byte TGA 2.0 footer Pillow writes
    (extension-area offset, developer-area offset, "TRUEVISION-XFILE." and a NUL). The engine must
    recognise the footer and stop the data region exactly 26 bytes before the end of the file.
    """
    import base64
    data = (EXT / "external_b").read_bytes()
    assert len(data) == 18 + 64 * 48 * 3 + 26 and data[-18:] == b"TRUEVISION-XFILE.\x00"
    r = Engine().run(data)
    assert r.status == "RESOLVED"
    c = r.candidate
    assert c.trailer == "tga2_footer"
    assert (c.data_start, c.data_end) == (18, len(data) - 26)
    assert c.data_end - c.data_start == 64 * 48 * 3
    p = to_payload(r, data, 1.0)
    _, _, body = read_ppm(EXT / "source.ppm")
    assert base64.b64decode(p["candidates"][0]["render"]["data_b64"]) == body
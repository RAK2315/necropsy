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


# FINDING (2026-11-19): the engine returns FAILED/exhausted for external_b with an arithmetic_mismatch of 26 bytes.
# Pillow writes the TGA 2.0 footer (8 offset bytes + "TRUEVISION-XFILE.\0"), and the engine's trailer registry only
# knows pcx_palette_256. Per Requirement 11.15 nothing is adjusted to make this pass. Strict xfail: when the engine
# gains a TGA footer entry this test starts passing and the xfail must be removed.
@pytest.mark.xfail(strict=True, reason="finding: engine does not know the TGA 2.0 footer (26-byte discrepancy)")
def test_external_b_tga_resolves_upright_with_flip_note():
    p = payload("external_b")
    assert p["status"] == "RESOLVED"
    c = p["candidates"][0]
    w, h, body = read_ppm(EXT / "source.ppm")
    import base64
    assert base64.b64decode(c["render"]["data_b64"]) == body            # upright, no flip in the test
    assert "rows flipped: file declares bottom-left origin" in c["render"]["note"]


def test_external_b_finding_is_exactly_the_26_byte_footer():
    """Documents the finding so a change in the engine's behaviour is noticed."""
    data = (EXT / "external_b").read_bytes()
    r = Engine().run(data)
    assert r.status == "FAILED" and r.termination == "exhausted"
    assert r.rejections[0].reason == "arithmetic_mismatch" and r.rejections[0].discrepancy == 26
    assert data[-18:] == b"TRUEVISION-XFILE.\x00" and len(data) == 18 + 64 * 48 * 3 + 26
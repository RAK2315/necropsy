"""Visual-language rules that can go silently false (Requirement 13, 5.10, 4.3, 7.11).

- The accent colour is used only on recovered data: field bytes, the recovered image's frame, the closure line.
  Checked on computed styles in a real browser, on every screen, so inline styles and new rules are caught too.
- The page requests nothing from a third-party origin.
- No CRT phosphor, scanlines, glow or flicker in the stylesheet.
- With reduced motion, the replay opens at its final step and the image is fully drawn on first paint.
"""
import json
import re
import subprocess
from urllib.parse import urlparse

import pytest

from tests.conftest import REPO_ROOT
from tests.ui.test_spec_panel import base_url  # noqa: F401  (the real app on a local port)

PUBLIC = REPO_ROOT / "public"
PROBE = REPO_ROOT / "tools" / "visual_probe.mjs"

# Where the accent may appear. Each entry: (tag, a class that must be present).
ALLOWED_ACCENT = {
    ("span", "f"),          # a hex or ASCII cell inside a recovered field (".b.f", ".c.f")
    ("div", "well"),        # the recovered image's frame on the RESOLVED screen
    ("p", "closure"),       # the closure line
    ("p", "c-proof"),       # the closure line inside the declared-versus-actual box
}


@pytest.fixture(scope="module")
def report(base_url):  # noqa: F811
    out = subprocess.run(["node", str(PROBE), base_url], capture_output=True, text=True, encoding="utf-8", timeout=180)
    result = json.loads(out.stdout.strip().splitlines()[-1])
    if result.get("error") == "no browser":
        pytest.skip("no Edge or Chrome found to drive")
    assert "error" not in result, result
    return result


def _allowed(hit) -> bool:
    classes = set(str(hit["cls"]).split())
    return any(hit["tag"] == tag and cls in classes for tag, cls in ALLOWED_ACCENT)


def test_accent_only_on_recovered_data(report):
    offenders = {screen: sorted({f'{h["tag"]}.{".".join(str(h["cls"]).split())} ({",".join(h["props"])})'
                                 for h in hits if not _allowed(h)})
                 for screen, hits in report["accent"].items()}
    offenders = {k: v for k, v in offenders.items() if v}
    assert not offenders, f"accent used outside recovered data: {offenders}"


def test_accent_is_actually_present_where_it_belongs(report):
    # guards against a probe that sees nothing: the resolved screen must show accent field bytes, frame and closure line
    seen = {(h["tag"], c) for h in report["accent"]["resolved"] for c in str(h["cls"]).split()}
    for need in [("span", "f"), ("div", "well"), ("p", "c-proof")]:
        assert need in seen, f"expected the accent on {need} on the RESOLVED screen"
    assert any(("p", "closure") == (h["tag"], c) for h in report["accent"]["resolved_tga"] for c in str(h["cls"]).split())


def test_no_third_party_requests(report, base_url):  # noqa: F811
    own = urlparse(base_url).netloc
    foreign = [u for u in report["requests"] if urlparse(u).scheme in ("http", "https") and urlparse(u).netloc != own]
    assert report["requests"], "the probe recorded no requests at all"
    assert not foreign, f"third-party requests: {foreign}"


def test_reduced_motion_opens_at_the_final_step_with_the_image_drawn(report):
    r = report["reduced"]
    assert r["counter"] == "step 10 of 10"
    assert r["outcome"] == "visible"
    assert r["bottomRowAlpha"] == 255


def _public_text_files():
    return [p for p in PUBLIC.rglob("*") if p.suffix in {".html", ".css", ".js", ".json"}]


def test_no_external_urls_in_shipped_files():
    hits = []
    for p in _public_text_files():
        for m in re.finditer(r"""(?:src|href|url\()\s*=?\s*["']?(?:https?:)?//""", p.read_text(encoding="utf-8")):
            hits.append(f"{p.relative_to(REPO_ROOT)}: {m.group(0)}")
    assert not hits, hits


FORBIDDEN_CSS = {
    "text-shadow (glow)": r"text-shadow\s*:",
    "repeating gradient (scanlines)": r"repeating-(?:linear|radial)-gradient",
    "keyframe animation (flicker)": r"@keyframes",
    "blur or glow filter": r"filter\s*:\s*[^;]*(?:blur|drop-shadow)",
    "screen curvature": r"perspective\s*:|border-radius\s*:\s*50%\s*/",
    "mix-blend (phosphor)": r"mix-blend-mode\s*:",
}


@pytest.mark.parametrize("name,pattern", FORBIDDEN_CSS.items())
def test_no_crt_effects(name, pattern):
    css = (PUBLIC / "app.css").read_text(encoding="utf-8")
    assert not re.search(pattern, css, re.IGNORECASE), f"{name} found in app.css"
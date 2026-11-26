"""UI task 50: the page describes itself to crawlers and link previews. Built by Claude Code, not Kiro.

Found by two outside page checkers on 27 Nov: no share image, a one-word title, no description or canonical URL,
no structured data, no heading a crawler could read (the page is drawn by JavaScript), and no sign of who made it.
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HTML = (ROOT / "public" / "index.html").read_text(encoding="utf-8")


def meta(attr, name):
    m = re.search(rf'<meta {attr}="{re.escape(name)}" content="([^"]*)">', HTML)
    return m.group(1) if m else None


def test_title_description_and_canonical():
    assert "<title>NECROPSY: recover image files nothing can open</title>" in HTML
    assert len(meta("name", "description")) > 120
    assert '<link rel="canonical" href="https://necropsy.vercel.app/">' in HTML


def test_share_image_is_served_at_the_size_it_declares():
    from PIL import Image
    assert meta("property", "og:image") == "https://necropsy.vercel.app/img/og.jpg"
    with Image.open(ROOT / "public" / "img" / "og.jpg") as im:
        assert im.size == (int(meta("property", "og:image:width")), int(meta("property", "og:image:height")))
    assert meta("name", "twitter:card") == "summary_large_image"


def test_structured_data_parses_and_names_the_source():
    data = json.loads(re.search(r'<script type="application/ld\+json">(.*?)</script>', HTML, re.S).group(1))
    assert data["@type"] == "SoftwareApplication" and data["codeRepository"] == "https://github.com/RAK2315/necropsy"


def test_a_heading_and_text_exist_before_any_script_runs():
    static = HTML[HTML.index('<main id="view">'):HTML.index("</main>")]
    assert static.count("<h1>") == 1 and "nothing can open" in static
    assert len(re.sub(r"<[^>]+>", " ", static).split()) > 60


def test_footer_says_where_the_source_is():
    foot = HTML[HTML.index('<footer class="site-foot"'):HTML.index("</footer>")]
    assert "https://github.com/RAK2315/necropsy" in foot and "MIT" in foot

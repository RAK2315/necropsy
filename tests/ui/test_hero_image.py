"""UI task 49: the landing hero's background photograph. Built by Claude Code, not Kiro.

The image is decoration (an AI-generated illustration, recorded in docs/media/generated/README.md). It must stay
small, appear in the dark theme only, sit behind the content, and fade into the page background on the left so the
hero text keeps the plain background its contrast was tested on.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CSS = (ROOT / "public" / "app.css").read_text(encoding="utf-8")


def test_the_image_is_served_and_small():
    img = ROOT / "public" / "img" / "hero-grooves.jpg"
    assert img.is_file() and img.stat().st_size < 200_000


def test_the_background_is_dark_theme_only_behind_content_and_fades_to_bg():
    rule_start = CSS.index(':root:not([data-theme="light"]) .hero::before')
    rule = CSS[rule_start:CSS.index("}", rule_start)]
    assert "url('img/hero-grooves.jpg')" in rule
    assert "z-index: -1" in rule and "pointer-events: none" in rule
    assert "linear-gradient(90deg, var(--bg) 0%, var(--bg) 42%" in rule   # text column on the plain background
    assert CSS.count("hero-grooves.jpg") == 1                              # no light-theme or other use


def test_the_image_is_recorded_as_generated_decoration():
    readme = (ROOT / "docs" / "media" / "generated" / "README.md").read_text(encoding="utf-8")
    assert "platter-grooves.png" in readme and "decoration" in readme

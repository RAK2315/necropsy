"""UI task 51: the redesign. Built by Claude Code, not Kiro.

The examiner ghost appears where a person may need a next step (the start, the examining screen, several readings,
no reading, a refused file) and never on a recovered picture. Its lines come from public/js/ghost.js and follow the
glossary's rule: they say what the engine did, then what to do. The first screen shows three exhibits of different
size, not a row of identical cards. Every sample name is a button labelled "Examine <name>". Tried layouts that
differ only in row padding or encoding no longer read as the same line twice.
"""
import re
from pathlib import Path

from tests.ui.conftest import run_in_browser
from tests.ui.test_fourth_pass import HELPERS

ROOT = Path(__file__).resolve().parents[2]
GHOST_JS = (ROOT / "public" / "js" / "ghost.js").read_text(encoding="utf-8")

SCENARIO = HELPERS + r"""
(async () => {
  const ghosts = () => [...document.querySelectorAll('figure.ghost')].filter(__shown).map(g => ({ cap: g.dataset.cap, mood: g.dataset.mood,
    line: g.querySelector('.ghost-line').textContent }));
  await __until(() => document.querySelectorAll('.strip-tile[data-status]').length === 3, 'strip');
  const tiles = [...document.querySelectorAll('.strip-tile')].map(t => { const r = t.getBoundingClientRect();
    return { exhibit: t.querySelector('.exhibit').textContent, w: Math.round(r.width), h: Math.round(r.height) }; });
  const picks = [...document.querySelectorAll('.samples .pick')].map(b => ({ text: b.textContent, label: b.getAttribute('aria-label') }));
  const out = { start: ghosts(), tiles, picks };
  await __pick('mystery_i'); await __result(); out.resolved = ghosts();
  await __home(); await __pick('mystery_d'); await __result(); out.several = ghosts();
  await __home(); document.querySelector('[data-cap=tile-2]').click(); await __result(); out.none = ghosts();
  out.lines = [...document.querySelectorAll('ol.rej li .rl')].map(e => e.textContent);
  return JSON.stringify(out);
})()
"""


def _line(key):
    m = re.search(rf"\b{key}: '([^']+)'", GHOST_JS)
    return m.group(1)


def test_ghost_appears_where_a_next_step_is_needed_and_never_on_a_picture(base_url):
    got = run_in_browser(base_url, SCENARIO, reduced_motion=True)
    assert [(g["cap"], g["mood"], g["line"]) for g in got["start"]] == [("ghost-start", "wait", _line("idle"))]
    assert got["resolved"] == []
    assert [g["mood"] for g in got["several"]] == ["shrug"] and got["several"][0]["line"].startswith("18 pictures fit")
    assert [(g["mood"], g["line"]) for g in got["none"]] == [("flat", _line("none"))]


def test_three_exhibits_of_different_size(base_url):
    got = run_in_browser(base_url, SCENARIO, reduced_motion=True)
    assert [t["exhibit"] for t in got["tiles"]] == ["Exhibit A", "Exhibit B", "Exhibit C"]
    a, b, c = got["tiles"]
    assert a["w"] > b["w"] and b["w"] == c["w"], got["tiles"]           # A is the large one; B and C share a column


def test_every_sample_is_a_labelled_examine_button(base_url):
    got = run_in_browser(base_url, SCENARIO, reduced_motion=True)
    assert got["picks"] and all(p["label"] == f"Examine {p['text']}" for p in got["picks"])


def test_tried_layouts_are_distinct_lines(base_url):
    # mystery_b's first 300 bytes: the row-padding corrections try 2 and 4 bytes on the same size; each line says which
    got = run_in_browser(base_url, SCENARIO, reduced_motion=True)
    assert len(got["lines"]) == len(set(got["lines"])), got["lines"]
    assert any("rows padded to 2 bytes" in l for l in got["lines"]) and any("rows padded to 4 bytes" in l for l in got["lines"])


def test_ghost_lines_end_with_what_to_do_and_never_diagnose():
    for key in ("idle", "refused", "examining", "none"):
        line = _line(key)
        for word in ("corrupt", "damaged", "broken", "bad file", "invalid"):
            assert word not in line.lower(), (key, line)
    assert "Try another file" in _line("none") and "Try another file" in _line("refused")
    # the ghost is drawn in the text colour: the accent is for recovered data only (Requirement 13)
    css = (ROOT / "public" / "app.css").read_text(encoding="utf-8")
    ghost_rules = "\n".join(l for l in css.splitlines() if ".ghost" in l)
    assert "--accent" not in ghost_rules


def test_clickables_lift_on_hover_and_stay_still_with_reduced_motion():
    # UI task 52 (Rehaan): everything clickable grows a little on hover; with reduced motion nothing moves
    css = (ROOT / "public" / "app.css").read_text(encoding="utf-8")
    for sel in ("button.primary:hover", '.strip-tile[role="button"]:hover', ".samples li:hover", ".drop:hover"):
        assert re.search(re.escape(sel) + r"[^{]*\{[^}]*transform: scale\(1\.0\d+\)", css), sel
    reduced = css[css.rindex("@media (prefers-reduced-motion: reduce)"):]
    assert "transform: none" in reduced and "transition: none" in reduced

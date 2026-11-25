"""UI clarity pass, task 24: the start screen is a landing page. Built by Claude Code, not Kiro (see docs/UI-CLARITY-PASS.md).

Checked in a real browser against the real app: one headline, exactly one primary action that runs the real sample
through the same path as a dropped file, three outcome tiles each with an Open affordance, three how-it-works steps,
one plain line per sample, and the licence notice served and linked from the real sample's row.
"""
import json

from necropsy.engine import Engine
from tests.conftest import REPO_ROOT
from tests.ui.conftest import run_in_browser

PUBLIC = REPO_ROOT / "public" / "samples"

LANDING = r"""
(async () => {
  await __until(() => document.querySelectorAll('.strip-tile[data-status]').length === 3, 'strip');
  await __until(() => document.querySelector('.samples ul'), 'samples');
  const rows = [...document.querySelectorAll('.samples li')];
  const lic = document.querySelector('.samples a.lic');
  const licText = lic ? await (await fetch(lic.getAttribute('href'))).text() : '';
  const primary = document.querySelectorAll('[data-cap=primary]');
  const out = {
    h1: [...document.querySelectorAll('h1')].map(h => h.textContent.trim()),
    primary: primary.length, primaryTag: primary[0] && primary[0].tagName, primaryText: primary[0] && primary[0].textContent,
    buttonsMarkedPrimary: document.querySelectorAll('.primary').length,
    tiles: [...document.querySelectorAll('.strip-tile')].map(t => ({ input: t.querySelector('.strip-input').textContent,
      open: (t.querySelector('.strip-open') || {}).textContent || '', cap: t.dataset.cap, role: t.getAttribute('role') })),
    steps: document.querySelectorAll('[data-cap=how] li').length,
    rows: rows.map(li => ({ name: li.querySelector('.pick').textContent, desc: (li.querySelector('.desc') || {}).textContent || '',
      lic: (li.querySelector('a.lic') || {}).getAttribute ? li.querySelector('a.lic').getAttribute('href') : null })),
    licText,
    aboveFold: ['[data-cap=primary]', '[data-cap=drop]'].map(s => document.querySelector(s).getBoundingClientRect().bottom <= 720),
  };
  primary[0].click();
  await __until(() => document.querySelector('.exam-right:not(.pending) figcaption .dims'), 'result');
  out.result = { dims: document.querySelector('.exam-right figcaption .dims').textContent,
                 status: document.querySelector('.exam-right .chip .tech').textContent };
  out.analyzed = performance.getEntriesByType('resource').filter(e => e.name.includes('/samples/pillow_odd_stride.pcx')).length;
  return JSON.stringify(out);
})()
"""


def test_landing_page(base_url):
    got = run_in_browser(base_url, LANDING, reduced_motion=True)
    index = json.loads((PUBLIC / "index.json").read_text(encoding="utf-8"))

    assert len(got["h1"]) == 1 and got["h1"][0]
    assert got["primary"] == 1 and got["buttonsMarkedPrimary"] == 1 and got["primaryTag"] == "BUTTON"
    assert got["primaryText"] == "See it recover a real file"
    assert all(got["aboveFold"]), "the primary action and the drop zone must be visible at 1280x720 without scrolling"

    assert [t["input"] for t in got["tiles"]] == ["mystery_i", "mystery_d", "mystery_b, first 300 bytes"]
    assert [t["cap"] for t in got["tiles"]] == ["tile-0", "tile-1", "tile-2"]
    assert all(t["open"].startswith("Open") and t["role"] == "button" for t in got["tiles"])
    assert got["steps"] == 3

    assert [r["name"] for r in got["rows"]] == [e["name"] for e in index]
    assert [r["desc"] for r in got["rows"]] == [e["description"] for e in index]
    assert all(r["desc"] for r in got["rows"])
    licensed = [r for r in got["rows"] if r["lic"]]
    assert [r["name"] for r in licensed] == ["pillow_odd_stride.pcx"]
    assert licensed[0]["lic"] == "/samples/LICENSES/Pillow-MIT-CMU.txt"
    assert got["licText"] == (PUBLIC / "LICENSES" / "Pillow-MIT-CMU.txt").read_text(encoding="utf-8")

    h = Engine(deadline_seconds=5.0).run((PUBLIC / "pillow_odd_stride.pcx").read_bytes()).candidate.hypothesis
    assert got["result"] == {"dims": f"{h.width} × {h.height} · {h.bit_depth}-bit", "status": "RESOLVED"}
    assert got["analyzed"] == 1, "the primary action must fetch the served sample, the same path a sample button takes"

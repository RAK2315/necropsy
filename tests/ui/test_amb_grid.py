"""UI clarity pass, task 28: every ambiguous reading at a glance. Built by Claude Code, not Kiro.

In a real browser: one tile per reading, in payload order, all the same rendered size, each linking to its own card;
nothing on a tile but its picture and its own size. The markup-level neutrality checks are in
tests/ui/js/screens.test.mjs.
"""
from necropsy.engine import Engine
from tests.conftest import corpus_bytes
from tests.ui.conftest import run_in_browser

SCENARIO = r"""
(async () => {
  (await __until(() => [...document.querySelectorAll('.pick')].find(b => b.textContent === 'mystery_d'), 'sample')).click();
  await __until(() => document.querySelector('.verdict-bar:not(.pending)'), 'verdict');
  const grid = document.querySelector('[data-cap=amb-grid]');
  const tiles = [...grid.querySelectorAll('.amb-tile')];
  const box = (e) => { const r = e.getBoundingClientRect(); return `${Math.round(r.width)}x${Math.round(r.height)}`; };
  const out = {
    above: grid.compareDocumentPosition(document.querySelector('.cards')) & Node.DOCUMENT_POSITION_FOLLOWING ? true : false,
    n: tiles.length, sizes: [...new Set(tiles.map(box))], wells: [...new Set(tiles.map(t => box(t.querySelector('.amb-well'))))],
    canvases: grid.querySelectorAll('canvas').length,
    dims: tiles.map(t => t.querySelector('.amb-dims').textContent),
    styles: [...new Set(tiles.map(t => { const s = getComputedStyle(t); return [s.borderColor, s.backgroundColor, s.fontWeight, s.opacity].join('/'); }))],
    focused: [],
    overflow: tiles.filter(t => { const d = t.querySelector('.amb-dims'); return d.scrollWidth > d.clientWidth || d.scrollHeight > d.clientHeight; }).length,
  };
  for (const i of [0, 5, tiles.length - 1]) { tiles[i].click(); out.focused.push(document.activeElement.dataset.index); }
  return JSON.stringify(out);
})()
"""


def test_grid_shows_every_reading_alike(base_url):
    got = run_in_browser(base_url, SCENARIO)
    cands = Engine().run(corpus_bytes("mystery_d")).candidates
    n = len(cands)
    assert got["above"], "the grid sits above the cards"
    assert got["n"] == n and got["canvases"] == n
    assert len(got["sizes"]) == 1 and len(got["wells"]) == 1, (got["sizes"], got["wells"])
    assert len(got["styles"]) == 1, got["styles"]
    assert got["dims"] == [f"{c.hypothesis.width} × {c.hypothesis.height} · {c.hypothesis.bit_depth}-bit" for c in cands]
    assert got["focused"] == ["0", "5", str(n - 1)]
    assert got["overflow"] == 0, "a tile's size label overflows its tile"

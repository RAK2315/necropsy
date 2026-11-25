"""Outcome strip (Requirement 16): the three tiles show the engine's real output, and follow the response.

UI clarity pass, task 24 (Claude Code): the first tile examines mystery_i, not external_a; since UI task 38 it examines
imagemagick_input.tga, a real photograph; its pixels are compared
with the service's own render (web/pixels.py), so a tile that paints a stored copy or anything else still fails.

Run in a real browser against the real app. The second test rewrites every /api/analyze response in the browser,
so a tile that shows a constant, a stored copy or another sample's result fails.
"""
import base64

from necropsy.engine import Engine
from tests.conftest import REPO_ROOT, corpus_bytes
from tests.ui.conftest import run_in_browser

EXT = REPO_ROOT / "spike" / "samples" / "external"
REAL = REPO_ROOT / "spike" / "samples" / "real"

# Reads every tile once all three have finished. Pixels of the RESOLVED tile are sampled at each image pixel's
# centre on the scaled canvas, so they can be compared with the source image exactly.
READ_TILES = r"""
(async () => {
  await __until(() => document.querySelectorAll('.strip-tile[data-status]').length === 3, 'three tiles');
  const tiles = [...document.querySelectorAll('.strip-tile')];
  const out = { statuses: tiles.map(t => t.dataset.status), inputs: tiles.map(t => t.querySelector('.strip-input').textContent),
                lines: tiles.map(t => t.querySelector('.strip-line').textContent) };
  const cv = tiles[0].querySelector('canvas');
  const [w, h] = tiles[0].querySelector('.strip-dims').textContent.match(/^(\d+) × (\d+)/).slice(1).map(Number);
  const sx = cv.width / w, sy = cv.height / h, ctx = cv.getContext('2d'), px = [];
  for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) {
    const d = ctx.getImageData(Math.floor((x + 0.5) * sx), Math.floor((y + 0.5) * sy), 1, 1).data; px.push(d[0], d[1], d[2]);
  }
  let s = ''; for (const v of px) s += String.fromCharCode(v);
  out.resolved = { w, h, rgb_b64: btoa(s) };
  out.thumbs = tiles[1].querySelectorAll('.strip-thumb').length;
  out.thumbCanvases = tiles[1].querySelectorAll('.strip-thumb canvas').length;
  out.thumbSizes = [...new Set([...tiles[1].querySelectorAll('.strip-thumb')].map(b => b.getBoundingClientRect().width + 'x' + b.getBoundingClientRect().height))];
  out.failed = { term: tiles[2].querySelector('.strip-term').textContent,
                 rej: [...tiles[2].querySelectorAll('.strip-rej li .tech')].map(li => li.textContent) };
  out.fits = document.querySelector('.drop').getBoundingClientRect().bottom <= 720;
  const before = performance.getEntriesByType('resource').filter(e => e.name.includes('/api/analyze')).length;
  tiles[1].click();
  await __until(() => document.querySelectorAll('.card').length, 'ambiguity screen');
  out.openedCards = document.querySelectorAll('.card').length;
  out.extraRequests = performance.getEntriesByType('resource').filter(e => e.name.includes('/api/analyze')).length - before;
  return JSON.stringify(out);
})()
"""

# Applied in the browser to every /api/analyze response before the page sees it.
REWRITE = r"""
(p) => {
  if (p.status === 'RESOLVED') {
    for (const c of p.candidates) {
      const raw = atob(c.render.data_b64); let s = '';
      for (let i = 0; i < raw.length; i++) s += String.fromCharCode(255 - raw.charCodeAt(i));
      c.render.data_b64 = btoa(s);
    }
  } else if (p.status === 'UNRESOLVED_AMBIGUITY') {
    p.candidates = p.candidates.slice(0, 5);
  } else {
    p.termination = 'deadline_exceeded';
    p.rejections = p.rejections.slice().reverse();
  }
  return p;
}
"""


def _ppm_rgb():
    """The service's render of imagemagick_input.tga, the first tile since UI task 38: (w, h), rgb bytes."""
    import app as service
    c = service._analyse((REAL / "imagemagick_input.tga").read_bytes())["candidates"][0]["render"]
    px = base64.b64decode(c["data_b64"])
    if c["channels"] == "grey8":
        px = bytes(v for g in px for v in (g, g, g))
    return (c["width"], c["height"]), px


def _rejection_line(r):
    return f"{r.source}: {r.reason}" + ("" if r.discrepancy is None else f" (discrepancy={r.discrepancy})")


def test_tiles_show_the_engines_real_output(base_url):
    got = run_in_browser(base_url, READ_TILES)
    assert got["statuses"] == ["RESOLVED", "UNRESOLVED_AMBIGUITY", "FAILED"]
    assert got["inputs"] == ["imagemagick_input.tga", "mystery_d", "mystery_b, first 300 bytes"]

    (w, h), rgb = _ppm_rgb()
    assert (got["resolved"]["w"], got["resolved"]["h"]) == (w, h)
    assert base64.b64decode(got["resolved"]["rgb_b64"]) == rgb, "RESOLVED tile pixels differ from the service's render of imagemagick_input.tga"

    n = len(Engine().run(corpus_bytes("mystery_d")).candidates)
    assert got["thumbs"] == got["thumbCanvases"] == n
    assert len(got["thumbSizes"]) == 1, f"ambiguity thumbnails differ in size: {got['thumbSizes']}"

    failed = Engine().run(corpus_bytes("mystery_b")[:300])
    assert failed.status == "FAILED"
    assert got["failed"]["rej"] == [_rejection_line(r) for r in failed.rejections[:3]]
    assert got["lines"] == ["One reading fits the data exactly.", f"{n} readings fit, so NECROPSY does not choose.",
                            "No layout tried fits. Here is every one, and why."]
    assert got["fits"], "the strip and the drop zone do not fit in 1280x720"

    assert got["openedCards"] == n and got["extraRequests"] == 0


def test_tiles_follow_the_response_not_a_constant(base_url):
    got = run_in_browser(base_url, READ_TILES, rewrite=REWRITE)
    _, rgb = _ppm_rgb()
    assert base64.b64decode(got["resolved"]["rgb_b64"]) == bytes(255 - b for b in rgb)
    assert got["thumbs"] == 5
    assert got["lines"][1] == "5 readings fit, so NECROPSY does not choose."
    assert got["failed"]["term"] == "The search stopped at the 5 second deadline."
    failed = Engine().run(corpus_bytes("mystery_b")[:300])
    assert got["failed"]["rej"] == [_rejection_line(r) for r in list(reversed(failed.rejections))[:3]]
    assert got["openedCards"] == 5

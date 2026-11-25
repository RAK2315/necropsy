"""UI tasks 37 to 39, built by Claude Code, not Kiro (Rehaan, 25 Nov; see docs/UI-CLARITY-PASS.md).

In a real browser against the real app:
  39. (supersedes 37) once the answer arrives, the engine's recorded steps are shown one by one under "Examining <name>…",
      with no control, then the result opens with its replay at the end and its controls there, for going back over it.
  38. the demo shows real pictures: a photograph, a portrait scan and a signature from upstream test suites are listed
      first, and the first outcome tile is the photograph. Their results are the engine's, compared here with a fresh run.
"""
from necropsy.engine import Engine
from tests.conftest import REPO_ROOT
from tests.ui.conftest import run_in_browser

REAL = REPO_ROOT / "spike" / "samples" / "real"
PICTURES = ["imagemagick_input.tga", "pillow_hopper_1bit.pbm", "pillow_pil184.pcx"]

LIVE = r"""
(async () => {
  const shown = (e) => !!e && e.getClientRects().length > 0;
  (await __until(() => [...document.querySelectorAll('.pick')].find(b => b.textContent === 'mystery_h'), 'sample')).click();
  const out = { seen: [], captions: [] };
  // record each step line as it appears on the examining screen, until the result opens
  for (;;) {
    const busy = document.querySelector('#view > .busy');
    if (!busy) break;
    const items = [...busy.querySelectorAll('[data-cap=busy-steps] li .rh')].map(e => e.textContent);
    if (items.length > out.seen.length) {
      out.seen = items;
      out.captions.push(busy.querySelector('[data-cap=busy-caption]').textContent);
      out.title = busy.querySelector('.busy-text').textContent;
      out.bar = [busy.querySelector('progress').value, busy.querySelector('progress').max];
      out.note = busy.querySelector('.busy-note').textContent;
      out.controls = busy.querySelectorAll('button, select').length;
    }
    await new Promise(r => setTimeout(r, 40));
  }
  // read the moment the result opens: it must already be at the end, not replaying from the start
  out.counter = (await __until(() => document.querySelector('.rp-counter'), 'result')).textContent;
  out.answerAtOnce = !!document.querySelector('.exam-right:not(.pending) figcaption .dims');
  out.resultControls = [...document.querySelectorAll('.rp-bar button, .rp-bar .rp-speed')].filter(shown).length;
  return JSON.stringify(out);
})()
"""


def _line(r):
    """public/js/logic.js rejectionLine and hypothesisLine, restated from the payload the page receives."""
    h = r["hypothesis"]
    return f"{r['source']}: {r['reason']}" + ("" if r.get("discrepancy") is None else f" (discrepancy={r['discrepancy']})") +         f" · {h['width']} × {h['height']} · {h['bit_depth']}-bit · header {h['header_size']} · align {h['row_alignment']} · {h['encoding']}"


def test_the_steps_play_one_by_one_while_examining(base_url):
    got = run_in_browser(base_url, LIVE)
    import app as service
    rej = service._analyse((REPO_ROOT / "spike" / "samples" / "mystery_h").read_bytes())["rejections"]
    n = len(rej) + 1
    assert got["title"] == "Examining mystery_h…"
    assert got["seen"] == [_line(x) for x in rej] + ["result: RESOLVED"], "the lines must be the engine's own steps, in order"
    assert len(got["captions"]) >= n - 1, f"the steps appeared in {len(got['captions'])} batches, not one by one"
    assert got["captions"][-1].startswith("Fits: ")
    assert got["bar"] == [n, n]
    assert got["note"].startswith("The engine finished in ") and got["note"].endswith("ms; its steps are shown here at reading speed.")
    assert got["controls"] == 0, "no control on the examining screen: the steps play through"
    assert got["counter"] == f"step {n} of {n}", "the result opens at the end: the steps were already shown"
    assert got["answerAtOnce"], "the answer is there as soon as the result opens"
    assert got["resultControls"] == 5


PICTURES_JS = r"""
(async () => {
  await __until(() => document.querySelectorAll('.strip-tile[data-status]').length === 3, 'strip');
  const out = { first: [...document.querySelectorAll('.samples .pick')].slice(0, 3).map(b => b.textContent),
                tile: document.querySelector('[data-cap=tile-0] .strip-input').textContent, results: [] };
  for (const name of %s) {
    (await __until(() => [...document.querySelectorAll('.pick')].find(b => b.textContent === name), name)).click();
    await __until(() => document.querySelector('.exam-right:not(.pending) figcaption .dims'), name + ' result');
    const cv = document.querySelector('[data-cap=image] canvas');
    out.results.push({ name, dims: document.querySelector('.exam-right figcaption .dims').textContent,
                       status: document.querySelector('[data-cap=chip] .tech').textContent, drawn: !!cv && cv.width > 0 });
    document.getElementById('again').click();
  }
  return JSON.stringify(out);
})()
""" % PICTURES


def test_real_pictures_lead_the_demo(base_url):
    got = run_in_browser(base_url, PICTURES_JS, reduced_motion=True)
    assert got["first"] == PICTURES
    assert got["tile"] == "imagemagick_input.tga"
    for r in got["results"]:
        h = Engine(deadline_seconds=5.0).run((REAL / r["name"]).read_bytes()).candidate.hypothesis
        assert r == {"name": r["name"], "dims": f"{h.width} × {h.height} · {h.bit_depth}-bit", "status": "RESOLVED", "drawn": True}

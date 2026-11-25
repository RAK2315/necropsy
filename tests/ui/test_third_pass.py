"""UI tasks 37 and 38, built by Claude Code, not Kiro (Rehaan, 25 Nov; see docs/UI-CLARITY-PASS.md).

In a real browser against the real app:
  37. while the replay plays for the first time only its step counter shows: no Pause, step, speed or Skip control, and
      no skip in the answer column. Once it has reached its end, the controls appear.
  38. the demo shows real pictures: a photograph, a portrait scan and a signature from upstream test suites are listed
      first, and the first outcome tile is the photograph. Their results are the engine's, compared here with a fresh run.
"""
from necropsy.engine import Engine
from tests.conftest import REPO_ROOT
from tests.ui.conftest import run_in_browser

REAL = REPO_ROOT / "spike" / "samples" / "real"
PICTURES = ["imagemagick_input.tga", "pillow_hopper_1bit.pbm", "pillow_pil184.pcx"]

FIRST_RUN = r"""
(async () => {
  const shown = (e) => !!e && e.getClientRects().length > 0;
  const controls = () => [...document.querySelectorAll('.rp-bar button, .rp-bar .rp-speed')].filter(shown).length;
  (await __until(() => [...document.querySelectorAll('.pick')].find(b => b.textContent === 'mystery_i'), 'sample')).click();
  await __until(() => document.querySelector('.rp-counter') && document.querySelector('.rp-counter').textContent, 'replay running');
  const out = { during: controls(), counter: shown(document.querySelector('.rp-counter')),
                pendingButtons: document.querySelectorAll('[data-cap=answer-pending] button').length,
                skipVisible: shown(document.querySelector('[data-cap=skip]')) };
  const speed = document.querySelector('.rp-speed'); speed.value = '4'; speed.dispatchEvent(new Event('change'));   // a 5 s wait, not 20
  await __until(() => document.querySelector('.verdict-bar:not(.pending)'), 'first run ends');
  out.after = controls(); out.skipAfter = shown(document.querySelector('[data-cap=skip]'));
  return JSON.stringify(out);
})()
"""


def test_no_controls_until_the_first_run_ends(base_url):
    got = run_in_browser(base_url, FIRST_RUN)
    assert got["during"] == 0 and not got["skipVisible"], f"controls shown while the first run plays: {got}"
    assert got["counter"], "the step counter must show while the replay runs"
    assert got["pendingButtons"] == 0
    assert got["after"] == 5 and got["skipAfter"], f"controls must appear once the replay has ended: {got}"


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

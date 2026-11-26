"""Second UI clarity pass, built by Claude Code, not Kiro (see docs/UI-CLARITY-PASS.md).

In a real browser against the real app:
  1. the result is one column, in sequence (answer, why it is right, how it got there, evidence), and the answer and its
     one-line proof sit above the fold at 1600 x 900;
  2. the evidence (bytes, header values) starts collapsed behind a control that names it and its size, open on FAILED;
  3. the recovered image fills its frame, nearest-neighbour, true dimensions beneath it;
  4. a sample runs the upload flow: "Examining <name>…" with an activity indicator, then the result;
  5. the replay is bigger and slower;
and Rehaan's three requests: a light/dark switch, a visible "Examine another file", self-hosted fonts (Roboto and Poppins until UI task 51, Bricolage Grotesque since).
"""
import math
import re

from necropsy.engine import Engine
from tests.conftest import REPO_ROOT, corpus_bytes
from tests.ui.conftest import run_in_browser

PUBLIC = REPO_ROOT / "public"
IMAGE_W, IMAGE_H = 880, 340          # public/js/screens.js
LIGHT = "try { localStorage.setItem('necropsy-theme', 'light'); } catch (e) {}"

HELPERS = r"""
window.__pick = async (name) => (await __until(() => [...document.querySelectorAll('.pick')].find(b => b.textContent === name), name)).click();
window.__rest = async () => {
  const b = await __until(() => document.querySelector('[data-cap=skip]'), 'replay');
  if (!b.disabled) b.click();
  await __until(() => !document.querySelector('.exam-right.pending, .verdict-bar.pending'), 'at rest');
};
window.__home = async () => { document.getElementById('again').click(); await __until(() => document.querySelector('.pick'), 'home'); };
window.__box = (sel) => { const e = document.querySelector(sel); if (!e) return null; const r = e.getBoundingClientRect();
  return { top: Math.round(r.top + scrollY), bottom: Math.round(r.bottom + scrollY), left: Math.round(r.left), right: Math.round(r.right) }; };
"""

# ---- 1. one column, in sequence ----

ORDER = HELPERS + r"""
(async () => {
  const seq = { resolved: ['[data-cap=verdict]', '[data-cap=image]', '.closure', '[data-cap=replay]', '[data-region=facts]', '[data-region=evidence]'],
                ambiguity: ['[data-cap=verdict]', '[data-cap=amb-grid]', '.cards', '[data-cap=replay]', '[data-region=evidence]'],
                failed: ['[data-cap=verdict]', '[data-cap=failed-groups]', '[data-cap=replay]', '[data-region=evidence]'] };
  const read = (k) => seq[k].map(s => ({ sel: s, box: __box(s) }));
  const out = {};
  await __pick('mystery_i'); await __rest(); scrollTo(0, 0);
  out.resolved = read('resolved'); out.fold = { image: __box('[data-cap=image]').bottom, closure: __box('.closure').bottom };
  await __home(); await __pick('pillow_odd_stride.pcx'); await __rest(); scrollTo(0, 0);
  out.odd = read('resolved'); out.oddFold = { image: __box('[data-cap=image]').bottom, closure: __box('.closure').bottom };
  await __home(); await __pick('mystery_d'); await __rest(); out.ambiguity = read('ambiguity');
  await __home(); document.querySelector('[data-cap=tile-2]').click(); await __rest(); out.failed = read('failed');
  out.columns = document.querySelectorAll('.exam-left').length;
  return JSON.stringify(out);
})()
"""


def _in_sequence(items):
    for a, b in zip(items, items[1:]):
        assert a["box"] and b["box"], (a, b)
        assert b["box"]["top"] >= a["box"]["bottom"] - 1, f"{b['sel']} is beside or above {a['sel']}: {a['box']} {b['box']}"


def test_one_column_in_sequence_with_the_answer_above_the_fold(base_url):
    got = run_in_browser(base_url, ORDER, viewport="1600x900", reduced_motion=True)
    for screen in ("resolved", "odd", "ambiguity", "failed"):
        _in_sequence(got[screen])
    assert got["columns"] == 0
    for fold in (got["fold"], got["oddFold"]):
        assert fold["image"] <= 900 and fold["closure"] <= 900, f"the answer and its proof must fit above 900 px: {fold}"


# ---- 2. the evidence: collapsed in the second pass; shown in full since UI task 41, titles still give the size ----

EVIDENCE = HELPERS + r"""
(async () => {
  const read = () => [...document.querySelectorAll('[data-region=evidence] .region')].map(r => ({ cap: r.dataset.cap || '',
    title: r.querySelector('.r-title').textContent, shown: !!r.getClientRects().length }));
  const out = {};
  await __pick('mystery_i'); await __rest(); out.resolved = read();
  await __home(); await __pick('mystery_d'); await __rest(); out.ambiguity = read();
  await __home(); document.querySelector('[data-cap=tile-2]').click(); await __rest(); out.failed = read();
  out.details = document.querySelectorAll('details.ev').length;
  return JSON.stringify(out);
})()
"""


def test_evidence_is_shown_and_says_what_is_inside(base_url):
    got = run_in_browser(base_url, EVIDENCE, reduced_motion=True)
    i = Engine().run(corpus_bytes("mystery_i")).candidate.hypothesis
    n_i, n_d = len(corpus_bytes("mystery_i")), len(corpus_bytes("mystery_d"))
    assert got["resolved"] == [{"cap": "ev-fields", "title": f"What the header declares ({len(i.fields)} values)", "shown": True},
                               {"cap": "ev-bytes", "title": f"The file’s bytes ({n_i:,})", "shown": True}]
    assert got["ambiguity"] == [{"cap": "ev-fields", "title": "What the header declares", "shown": True},
                                {"cap": "ev-bytes", "title": f"The file’s bytes ({n_d:,})", "shown": True}]
    assert [(e["cap"], e["shown"]) for e in got["failed"]] == [("ev-bytes", True)]
    assert got["details"] == 0


# ---- 3. the image fills its frame ----

FILL = HELPERS + r"""
(async () => {
  const read = () => { const c = document.querySelector('[data-cap=image] canvas'), w = document.querySelector('[data-cap=image] .well');
    const cr = c.getBoundingClientRect(), wr = w.getBoundingClientRect();
    return { cw: c.width, ch: c.height, css: [Math.round(cr.width), Math.round(cr.height)], well: [Math.round(wr.width), Math.round(wr.height)],
             rendering: getComputedStyle(c).imageRendering, smoothing: c.getContext('2d').imageSmoothingEnabled,
             dims: document.querySelector('[data-cap=image] figcaption .dims').textContent }; };
  const out = {};
  await __pick('mystery_i'); await __rest(); out.i = read();
  await __home(); await __pick('pillow_odd_stride.pcx'); await __rest(); out.odd = read();
  return JSON.stringify(out);
})()
"""


def _fill(w, h):
    k = min(IMAGE_W / w, IMAGE_H / h)
    return max(1, math.floor(w * k)), max(1, math.floor(h * k))


def test_the_image_fills_its_frame(base_url):
    got = run_in_browser(base_url, FILL, reduced_motion=True)
    for key, name in (("i", "mystery_i"), ("odd", None)):
        data = corpus_bytes(name) if name else (PUBLIC / "samples" / "pillow_odd_stride.pcx").read_bytes()
        h = Engine().run(data).candidate.hypothesis
        g = got[key]
        assert (g["cw"], g["ch"]) == _fill(h.width, h.height), (key, g)
        assert g["css"] == [g["cw"], g["ch"]]
        assert g["well"][0] - g["css"][0] <= 2 and g["well"][1] - g["css"][1] <= 2, f"dead space around the image: {g}"
        assert g["rendering"] in ("pixelated", "crisp-edges") and g["smoothing"] is False
        assert g["dims"] == f"{h.width} × {h.height} · {h.bit_depth}-bit"
    assert got["i"]["cw"] >= 300, "an 8 x 8 recovery is shown large, not as a speck"


# ---- 4. a sample runs the upload flow ----

FLOW = HELPERS + r"""
(async () => {
  const out = {};
  const watch = async () => {
    const t0 = performance.now();
    const busy = await __until(() => document.querySelector('#view > .busy'), 'busy');
    const seen = { text: busy.querySelector('.busy-text').textContent, bar: !!busy.querySelector('progress:not([value])'),
                   role: busy.getAttribute('role'), state: document.querySelector('[data-cap=state]').textContent };
    await __until(() => !document.querySelector('#view > .busy'), 'result');
    seen.ms = performance.now() - t0;
    seen.steps = busy.querySelectorAll('[data-cap=busy-steps] li').length;     // shown one by one before the result (UI task 39)
    seen.counter = document.querySelector('.rp-counter').textContent;
    return seen;
  };
  await __until(() => document.querySelector('.pick'), 'start');
  const s = watch(); await __pick('mystery_i'); out.sample = await s;
  await __home();
  const bytes = new Uint8Array(await (await fetch('/samples/mystery_i')).arrayBuffer());
  const d = watch(); const dt = new DataTransfer(); dt.items.add(new File([bytes], 'mine.bin'));
  document.querySelector('.drop').dispatchEvent(new DragEvent('drop', { dataTransfer: dt, bubbles: true, cancelable: true }));
  out.drop = await d;
  await __home();
  const p = watch(); document.querySelector('[data-cap=primary]').click(); out.primary = await p;
  return JSON.stringify(out);
})()
"""


def test_a_sample_runs_the_upload_flow(base_url):
    got = run_in_browser(base_url, FLOW)
    for key, name in (("sample", "mystery_i"), ("drop", "mine.bin"), ("primary", "pillow_odd_stride.pcx")):
        g = got[key]
        assert g["text"] == f"Examining {name}…" and g["bar"] and g["role"] == "status", g
        assert g["state"].startswith(name) and g["state"].endswith("Examining…"), g
        assert g["ms"] >= 650, f"the busy screen must be seen, not flashed: {g['ms']:.0f} ms"
        assert g["steps"] > 1, "the engine's steps are shown on the examining screen"
        assert re.fullmatch(r"step (\d+) of \1", g["counter"]), "the result opens with its replay at the end"


# ---- 5. the replay, bigger and slower ----

REPLAY = HELPERS + r"""
(async () => {
  await __pick('mystery_i');
  const counter = await __until(() => { const c = document.querySelector('.rp-counter'); return c && c.textContent ? c : null; }, 'replay');
  const px = (sel) => parseFloat(getComputedStyle(document.querySelector(sel)).fontSize);
  const out = { caption: px('[data-cap=replay-caption]'), log: px('.rp-item .rl'), head: px('.rp-honest'), button: px('.rp-btn'),
                logHeight: document.querySelector('.rp-log').getBoundingClientRect().height };
  document.querySelector('.rp-bar button[title="Play or pause"]').click();   // it opens at the end (UI task 39); Play runs it again
  const first = counter.textContent; const t0 = performance.now();
  await __until(() => counter.textContent !== first, 'next frame');
  out.frameMs = performance.now() - t0;
  out.first = first; out.second = counter.textContent;
  return JSON.stringify(out);
})()
"""


def test_the_replay_is_bigger_and_slower(base_url):
    got = run_in_browser(base_url, REPLAY)
    assert got["caption"] >= 18 and got["log"] >= 14 and got["head"] >= 14 and got["button"] >= 14, got
    assert got["logHeight"] > 120, got
    assert got["frameMs"] >= 1000, f"one step at 1x must stay on screen at least a second: {got}"
    assert (got["first"], got["second"]) == ("step 1 of 20", "step 2 of 20"), "one step per frame for mystery_i"


# ---- Rehaan's requests: theme switch, a visible way back, the fonts ----

THEME = r"""
(async () => {
  await __until(() => document.querySelector('.pick'), 'start');
  const root = document.documentElement, b = document.querySelector('[data-cap=theme]');
  const read = () => ({ theme: root.dataset.theme, scheme: getComputedStyle(root).colorScheme, bg: getComputedStyle(document.body).backgroundColor,
                        label: b.textContent, pressed: b.getAttribute('aria-pressed'), stored: localStorage.getItem('necropsy-theme') });
  const out = { first: read() };
  b.click(); out.light = read();
  b.click(); out.dark = read();
  return JSON.stringify(out);
})()
"""


def test_theme_switch(base_url):
    got = run_in_browser(base_url, THEME)
    assert got["first"] == {"theme": "dark", "scheme": "dark", "bg": "rgb(18, 22, 27)", "label": "Light theme", "pressed": "false", "stored": None}
    assert got["light"] == {"theme": "light", "scheme": "light", "bg": "rgb(245, 246, 248)", "label": "Dark theme", "pressed": "true", "stored": "light"}
    assert got["dark"] == {**got["first"], "stored": "dark"}
    remembered = run_in_browser(base_url, "(async () => JSON.stringify({ theme: document.documentElement.dataset.theme, "
                                          "bg: getComputedStyle(document.body).backgroundColor }))()", prelude=LIGHT)
    assert remembered == {"theme": "light", "bg": "rgb(245, 246, 248)"}, "the choice is remembered and applied before paint"


AGAIN = HELPERS + r"""
(async () => {
  await __pick('mystery_i'); await __rest();
  const a = document.getElementById('again'), q = document.querySelector('[data-cap=theme]');
  const s = getComputedStyle(a), t = getComputedStyle(document.body), r = a.getBoundingClientRect();
  return JSON.stringify({ border: s.borderTopColor, text: t.color, color: s.color, weight: s.fontWeight, size: parseFloat(s.fontSize),
    quiet: a.classList.contains('quiet'), height: r.height, wider: r.width > q.getBoundingClientRect().width,
    arrow: getComputedStyle(a, '::before').content, top: r.top });
})()
"""


def test_examine_another_file_is_a_visible_control(base_url):
    got = run_in_browser(base_url, AGAIN)
    assert not got["quiet"] and got["border"] == got["text"] == got["color"], got
    assert int(got["weight"]) >= 600 and got["size"] >= 14 and got["height"] >= 30 and got["wider"], got
    assert got["arrow"] == '"← "' and got["top"] < 48, got


FONTS = r"""
(async () => {
  await __until(() => document.querySelector('.pick'), 'start');
  await document.fonts.ready;
  const fam = (sel) => getComputedStyle(document.querySelector(sel)).fontFamily.split(',')[0].replace(/"/g, '').trim();
  const loaded = [...document.fonts].filter(f => f.status === 'loaded').map(f => f.family.replace(/"/g, ''));
  const fonts = performance.getEntriesByType('resource').map(e => e.name).filter(n => n.includes('.woff2'));
  return JSON.stringify({ body: fam('body'), h1: fam('.hero h1'), brand: fam('.brand'), loaded, fonts, origin: location.origin,
    ok: document.fonts.check('700 40px "Bricolage Grotesque"') });
})()
"""


# UI task 51 replaced Roboto and Poppins (task 36) with one variable family, Bricolage Grotesque, still self-hosted.
def test_self_hosted_bricolage_grotesque(base_url):
    got = run_in_browser(base_url, FONTS)
    assert (got["body"], got["h1"], got["brand"]) == ("Bricolage Grotesque",) * 3
    assert got["ok"] and "Bricolage Grotesque" in got["loaded"], got["loaded"]
    assert got["fonts"] and all(u.startswith(got["origin"] + "/fonts/") for u in got["fonts"]), got["fonts"]
    for f in ("BricolageGrotesque-OFL.txt",):
        assert "SIL OPEN FONT LICENSE" in (PUBLIC / "fonts" / f).read_text(encoding="utf-8").upper()

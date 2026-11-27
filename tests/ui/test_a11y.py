"""Keyboard and contrast (Requirement 20), checked with real key presses in a real browser.

Keys go through CDP Input.dispatchKeyEvent, so focus moves as it would for a person: Tab order, focus rings,
Enter and Space, Escape. Contrast is measured on the colour pairs the page actually renders, read from computed
styles, and the ratio is computed here from the WCAG 2 definition.
"""
import pytest

from necropsy.engine import Engine
from tests.conftest import REPO_ROOT, corpus_bytes
from tests.ui.conftest import run_in_browser

EXT = REPO_ROOT / "spike" / "samples" / "external"

HELPERS = r"""
window.__desc = (e) => {
  if (!e || e === document.body || e === document.documentElement) return { kind: 'BODY' };
  const s = getComputedStyle(e);
  return { kind: 'EL', tag: e.tagName.toLowerCase(), id: e.id || '', cls: typeof e.className === 'string' ? e.className : '',
           text: (e.getAttribute('aria-label') || e.textContent || '').trim().slice(0, 40), act: (e.dataset && e.dataset.act) || '',
           outline: s.outlineStyle, ow: parseFloat(s.outlineWidth) || 0 };
};
window.__same = (a, b) => JSON.stringify(a) === JSON.stringify(b);
// Press Tab until the first stop comes round again. Returns every stop in order; `wrapped` is false if it never did.
window.__tabCycle = async (max = 400) => {
  document.activeElement && document.activeElement.blur();
  const stops = [];
  for (let i = 0; i < max; i++) {
    await __key('Tab');
    const d = __desc(document.activeElement);
    if (stops.length && d.kind === 'EL' && __same(d, stops.find(s => s.kind === 'EL'))) return { stops, wrapped: true };
    stops.push(d);
  }
  return { stops, wrapped: false };
};
window.__tabTo = async (pred, what, max = 400) => {
  for (let i = 0; i < max; i++) { await __key('Tab'); if (pred(document.activeElement)) return document.activeElement; }
  throw new Error('Tab never reached ' + what);
};
window.__start = async () => {
  await __until(() => document.querySelectorAll('.strip-tile[data-status]').length === 3, 'strip');
  await __until(() => document.querySelector('.samples ul, .samples > .drop-msg'), 'sample list');
};
window.__result = () => __until(() => document.querySelector('.vtab'), 'result screen');
"""

COUNTERS = r"""
window.__pickerOpens = 0; window.__linkClicks = 0;
HTMLInputElement.prototype.click = function () { if (this.type === 'file') window.__pickerOpens++; };
document.addEventListener('click', (e) => { const a = e.target.closest && e.target.closest('a.dl'); if (a) { e.preventDefault(); window.__linkClicks++; } }, true);
"""


def run(base_url, body, **kw):
    kw["prelude"] = COUNTERS + kw.get("prelude", "")
    return run_in_browser(base_url, HELPERS + body, **kw)


def _els(stops):
    return [s for s in stops if s["kind"] == "EL"]


def _count(stops, cls=None, tag=None, act=None):
    return sum(1 for s in _els(stops) if (cls is None or cls in s["cls"].split()) and (tag is None or s["tag"] == tag)
               and (act is None or s["act"] == act))


def _assert_focus_visible(stops):
    hidden = [s for s in _els(stops) if s["outline"] == "none" or s["ow"] <= 0]
    assert not hidden, f"no visible focus indicator on: {[(s['tag'], s['cls'], s['text']) for s in hidden]}"


# ---- 20.1 to 20.3: Tab reaches every control, focus is visible, nothing traps ----

def test_start_screen_tab_cycle(base_url):
    got = run(base_url, "(async () => { await __start(); return JSON.stringify(await __tabCycle()); })()")
    stops = got["stops"]
    assert got["wrapped"], "Tab never returned to the first control: focus is trapped"
    assert _count(stops, cls="strip-tile") == 3
    assert _count(stops, cls="drop") == 1
    assert _count(stops, cls="pick") == 15   # three real pictures added (UI task 38)
    assert _count(stops, cls="dl", tag="a") == 15
    _assert_focus_visible(stops)


def test_resolved_and_spec_tab_cycle(base_url):
    got = run(base_url, r"""
(async () => {
  await __start();
  [...document.querySelectorAll('.pick')].find(b => b.textContent === 'external_a').click();
  await __until(() => document.querySelector('.exam-right:not(.pending) .card-dl'), 'outcome');
  const exam = await __tabCycle();
  [...document.querySelectorAll('.vtab')].find(b => b.textContent === 'Emitted spec').click();
  const spec = await __tabCycle();
  return JSON.stringify({ exam, spec });
})()
""", reduced_motion=True)
    for name in ("exam", "spec"):
        assert got[name]["wrapped"], f"focus trapped on the {name} view"
        _assert_focus_visible(got[name]["stops"])
    exam, spec = got["exam"]["stops"], got["spec"]["stops"]
    assert _count(exam, cls="vtab") == 2 and _count(exam, tag="button") >= 4
    assert any(s["id"] == "again" for s in _els(exam))
    assert _count(exam, cls="rp-btn") >= 1 and _count(exam, cls="rp-speed") == 1
    assert _count(exam, act="png") == 1 and _count(exam, act="data") == 1
    assert _count(spec, cls="spec-tab") == 3
    assert any(s["text"] == "Download spec folder (.zip)" for s in _els(spec))


def test_ambiguity_tab_cycle(base_url):
    n = len(Engine().run(corpus_bytes("mystery_d")).candidates)
    got = run(base_url, r"""
(async () => {
  await __start();
  [...document.querySelectorAll('.pick')].find(b => b.textContent === 'mystery_d').click();
  await __until(() => document.querySelectorAll('.card').length, 'cards');
  return JSON.stringify(await __tabCycle(600));
})()
""")
    assert got["wrapped"]
    _assert_focus_visible(got["stops"])
    assert _count(got["stops"], cls="card") == n
    assert _count(got["stops"], act="png") == n and _count(got["stops"], act="data") == n


# ---- 20.1: Enter and Space do the same thing; 20.4: Escape returns to the start ----

def test_tile_enter_space_and_escape(base_url):
    got = run(base_url, r"""
(async () => {
  await __start();
  const out = {};
  for (const k of ['Enter', 'Space']) {
    await __tabTo(e => e.classList.contains('strip-tile') && e.dataset.slot === '1', 'ambiguity tile');
    await __key(k);
    await __result();
    out[k] = document.querySelectorAll('.card').length;
    await __key('Escape');
    await __start();
    out[k + '_back'] = !!document.querySelector('.drop') && !document.querySelector('.vtab');
  }
  return JSON.stringify(out);
})()
""")
    n = len(Engine().run(corpus_bytes("mystery_d")).candidates)
    assert got == {"Enter": n, "Enter_back": True, "Space": n, "Space_back": True}


def test_drop_zone_pick_and_sample_link_enter_space(base_url):
    got = run(base_url, r"""
(async () => {
  await __start();
  const out = { picker: [], links: [], picks: [] };
  for (const k of ['Enter', 'Space']) {
    await __tabTo(e => e.classList.contains('drop'), 'drop zone'); await __key(k); out.picker.push(__pickerOpens);
    await __tabTo(e => e.matches('a.dl') && e.getAttribute('download') === 'mystery_c', 'mystery_c download'); await __key(k);
    out.links.push(__linkClicks);
  }
  for (const k of ['Enter', 'Space']) {
    await __tabTo(e => e.classList.contains('pick') && e.textContent === 'mystery_c', 'mystery_c'); await __key(k);
    await __result(); out.picks.push(document.querySelector('.chip .tech').textContent);
    await __key('Escape'); await __start();
  }
  return JSON.stringify(out);
})()
""")
    assert got["picker"] == [1, 2], "Enter and Space do not both open the file picker"
    assert got["links"] == [1, 2], "Enter and Space do not both activate a sample download link"
    assert got["picks"] == ["RESOLVED", "RESOLVED"]


def test_result_controls_enter_space(base_url):
    got = run(base_url, r"""
(async () => {
  await __start();
  [...document.querySelectorAll('.pick')].find(b => b.textContent === 'mystery_i').click();
  await __until(() => document.querySelector('.exam-right:not(.pending) .card-dl'), 'outcome');
  const counter = () => document.querySelector('.rp-counter').textContent;
  const out = { counters: [counter()] };
  for (const k of ['Enter', 'Space']) { await __tabTo(e => e.title === 'Step back', 'step back'); await __key(k); out.counters.push(counter()); }
  const pngs = () => __blobs.filter(b => b.type === 'image/png' && b.b64).length;
  for (const [i, k] of [[1, 'Enter'], [2, 'Space']]) { await __tabTo(e => e.dataset.act === 'png', 'PNG'); await __key(k); await __until(() => pngs() === i, 'png ' + k); }
  out.pngs = __blobs.filter(b => b.type === 'image/png').length;
  await __tabTo(e => e.classList.contains('vtab') && e.textContent === 'Emitted spec', 'spec tab'); await __key('Enter');
  out.specShown = !document.querySelector('.view-spec').hidden;
  await __tabTo(e => e.classList.contains('vtab') && e.textContent === 'Examination', 'exam tab'); await __key('Space');
  out.examShown = !document.querySelector('.view-exam').hidden;
  [...document.querySelectorAll('.vtab')].find(b => b.textContent === 'Emitted spec').click();
  const sel = () => [...document.querySelectorAll('.spec-tab')].find(b => b.getAttribute('aria-selected') === 'true').textContent;
  await __tabTo(e => e.classList.contains('spec-tab') && e.textContent === 'design.md', 'design.md'); await __key('Enter'); out.tab1 = sel();
  await __tabTo(e => e.classList.contains('spec-tab') && e.textContent.startsWith('test_'), 'test file'); await __key('Space'); out.tab2 = sel();
  for (const k of ['Enter', 'Space']) {
    await __tabTo(e => e.textContent === 'Download spec folder (.zip)', 'zip'); await __key(k);
    await __until(() => __blobs.filter(b => b.type === 'application/zip' && b.b64).length === (k === 'Enter' ? 1 : 2), 'zip ' + k);
  }
  out.zips = __blobs.filter(b => b.type === 'application/zip').length;
  await __key('Escape');
  out.escaped = !!(await __until(() => document.querySelector('.drop'), 'start after Escape'));
  return JSON.stringify(out);
})()
""", reduced_motion=True)
    assert got["counters"] == ["step 20 of 20", "step 19 of 20", "step 18 of 20"]   # one step per frame since the second clarity pass
    assert got["pngs"] == 2
    assert got["specShown"] and got["examShown"]
    assert got["tab1"] == "design.md" and got["tab2"].startswith("test_")
    assert got["zips"] == 2 and got["escaped"]


def test_ambiguity_card_enter_space(base_url):
    got = run(base_url, r"""
(async () => {
  await __start();
  [...document.querySelectorAll('.pick')].find(b => b.textContent === 'mystery_d').click();
  await __until(() => document.querySelectorAll('.card').length, 'cards');
  const open = () => [...document.querySelectorAll('.card.open')].map(c => c.dataset.index);
  await __tabTo(e => e.classList.contains('card') && e.dataset.index === '0', 'card 0'); await __key('Enter'); const a = open();
  await __tabTo(e => e.classList.contains('card') && e.dataset.index === '1', 'card 1'); await __key('Space'); const b = open();
  return JSON.stringify({ a, b });
})()
""")
    assert got == {"a": ["0"], "b": ["1"]}


# ---- 20.5: canvas names from the payload ----

def test_every_canvas_is_named_from_the_payload(base_url):
    got = run(base_url, r"""
(async () => {
  await __start();
  const names = () => [...document.querySelectorAll('canvas')].map(c => c.getAttribute('aria-label'));
  const out = { start: names() };
  [...document.querySelectorAll('.pick')].find(b => b.textContent === 'external_b').click();
  await __until(() => document.querySelector('.exam-right:not(.pending) canvas'), 'image');
  out.resolved = names();
  await __key('Escape'); await __start();
  [...document.querySelectorAll('.pick')].find(b => b.textContent === 'mystery_d').click();
  await __until(() => document.querySelectorAll('.card canvas').length, 'cards');
  out.ambiguity = names();
  return JSON.stringify(out);
})()
""", reduced_motion=True)
    name = lambda h: f"Recovered image, {h.width} × {h.height}, {h.bit_depth}-bit"
    d = [c.hypothesis for c in Engine().run(corpus_bytes("mystery_d")).candidates]
    a = Engine().run((REPO_ROOT / "spike" / "samples" / "real" / "pillow_odd_stride.pcx").read_bytes()).candidate.hypothesis   # the first strip tile (UI task 52)
    b = Engine().run((EXT / "external_b").read_bytes()).candidate.hypothesis
    assert got["start"] == [name(a)] + [name(h) for h in d]
    assert got["resolved"] == [name(b)]
    assert got["ambiguity"] == [name(h) for h in d] * 2     # the at-a-glance grid (UI task 28), then the cards


# ---- 20.6: status text is announced ----

def test_status_text_is_announced(base_url):
    slow = r"""
(() => { const real = window.fetch.bind(window); window.__slowApi = false;
  window.fetch = (i, o) => (window.__slowApi && String(i && i.url || i).includes('/api/analyze'))
    ? new Promise(r => setTimeout(() => r(real(i, o)), 600)) : real(i, o); })();
"""
    got = run(base_url, r"""
(async () => {
  const live = (e) => !!(e && e.closest('[role="status"], [aria-live]'));
  await __start();
  const out = { dropMsg: live(document.querySelector('.drop-msg')),
                tiles: [...document.querySelectorAll('.strip-body')].every(live) };
  window.__slowApi = true;
  [...document.querySelectorAll('.pick')].find(b => b.textContent === 'mystery_i').click();
  out.analysing = live(await __until(() => document.querySelector('.busy'), 'Analysing'));
  window.__slowApi = false;
  await __result();
  out.counter = live(document.querySelector('.rp-counter'));
  [...document.querySelectorAll('.vtab')].find(b => b.textContent === 'Emitted spec').click();
  out.specStatus = live(document.querySelector('.spec-status'));
  await __key('Escape'); await __start();
  const dt = new DataTransfer(); dt.items.add(new File([new Uint8Array(40)], 'a.bin')); dt.items.add(new File(['x'], 'b.txt'));
  document.querySelector('.drop').dispatchEvent(new DragEvent('drop', { dataTransfer: dt, bubbles: true, cancelable: true }));
  out.notice = live(await __until(() => document.querySelector('.notice'), 'notice'));
  return JSON.stringify(out);
})()
""", prelude=slow)
    assert got == {"dropMsg": True, "tiles": True, "analysing": True, "counter": True, "specStatus": True, "notice": True}


# ---- 20.7: contrast of every rendered text pair ----

COLLECT = r"""
window.__pairs = (screen) => {
  const rgba = (c) => { const m = c.match(/[\d.]+/g).map(Number); return [m[0], m[1], m[2], m.length > 3 ? m[3] : 1]; };
  const bgOf = (e) => {
    const layers = [];
    for (let n = e; n; n = n.parentElement) { const c = rgba(getComputedStyle(n).backgroundColor); if (c[3] > 0) { layers.push(c); if (c[3] >= 1) break; } }
    if (!layers.length || layers[layers.length - 1][3] < 1) layers.push([255, 255, 255, 1]);
    let [r, g, b] = layers[layers.length - 1];
    for (let i = layers.length - 2; i >= 0; i--) { const [R, G, B, A] = layers[i]; r = R * A + r * (1 - A); g = G * A + g * (1 - A); b = B * A + b * (1 - A); }
    return [r, g, b];
  };
  const out = [];
  for (const e of document.querySelectorAll('body *')) {
    const text = [...e.childNodes].filter(n => n.nodeType === 3).map(n => n.textContent).join('').trim();
    if (!text) continue;
    const s = getComputedStyle(e);
    if (s.visibility !== 'visible' || !e.getClientRects().length) continue;
    if (e.closest(':disabled, [aria-disabled="true"]')) continue;
    let op = 1; for (let n = e; n; n = n.parentElement) op *= parseFloat(getComputedStyle(n).opacity);
    const fg = rgba(s.color);
    out.push({ screen, sel: e.tagName.toLowerCase() + (typeof e.className === 'string' && e.className ? '.' + e.className.trim().split(/\s+/).join('.') : ''),
               text: text.slice(0, 24), fg: fg.slice(0, 3), alpha: fg[3] * op, bg: bgOf(e) });
  }
  return out;
};
"""

SCREENS = r"""
(async () => {
  const pairs = [];
  await __start(); pairs.push(...__pairs('start'));
  const dt = new DataTransfer(); dt.items.add(new File([new Uint8Array(70000)], 'big.bin'));
  document.querySelector('.drop').dispatchEvent(new DragEvent('drop', { dataTransfer: dt, bubbles: true, cancelable: true }));
  await __until(() => document.querySelector('.drop-msg.bad'), 'error'); pairs.push(...__pairs('start-error'));
  [...document.querySelectorAll('.pick')].find(b => b.textContent === 'mystery_i').click();
  await __until(() => document.querySelector('.exam-right:not(.pending) .card-dl'), 'resolved');
  pairs.push(...__pairs('resolved'));
  document.querySelector('table.fields tbody tr').dispatchEvent(new MouseEvent('mouseenter'));
  await __until(() => document.querySelector('.hex-layer .b.hi'), 'highlight'); pairs.push(...__pairs('hex-highlight'));
  document.querySelector('.hex-layer .b.f').dispatchEvent(new MouseEvent('mouseover', { bubbles: true }));
  await __until(() => !document.querySelector('.hex-tip').hidden, 'tooltip'); pairs.push(...__pairs('hex-tooltip'));
  document.querySelector('.rp-bar button[title="Step back"]').click(); pairs.push(...__pairs('replay-mid'));
  [...document.querySelectorAll('.vtab')].find(b => b.textContent === 'Emitted spec').click(); pairs.push(...__pairs('spec'));
  document.getElementById('again').click(); await __start();
  [...document.querySelectorAll('.pick')].find(b => b.textContent === 'mystery_d').click();
  await __until(() => document.querySelectorAll('.card').length, 'cards');
  const card = document.querySelectorAll('.card')[1];
  card.dispatchEvent(new MouseEvent('mouseenter')); card.click(); pairs.push(...__pairs('ambiguity'));
  document.getElementById('again').click(); await __start();
  const cut = new Uint8Array(await (await fetch('/samples/mystery_b')).arrayBuffer()).slice(0, 300);
  const d2 = new DataTransfer(); d2.items.add(new File([cut], 'cut.pcx')); d2.items.add(new File(['x'], 'other.txt'));
  document.querySelector('.drop').dispatchEvent(new DragEvent('drop', { dataTransfer: d2, bubbles: true, cancelable: true }));
  await __until(() => document.querySelector('.verdict-bar:not(.pending) .fail-reason'), 'failed');
  pairs.push(...__pairs('failed'));
  return JSON.stringify(pairs);
})()
"""


def _lum(rgb):
    def ch(v):
        v = v / 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = (ch(v) for v in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(fg, bg):
    hi, lo = sorted((_lum(fg), _lum(bg)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def test_contrast_formula_matches_wcag_reference_values():
    assert round(contrast((0, 0, 0), (255, 255, 255)), 2) == 21.0
    assert round(contrast((119, 119, 119), (255, 255, 255)), 2) == 4.48     # #777 on white, the classic just-fail
    assert round(contrast((118, 118, 118), (255, 255, 255)), 2) == 4.54     # #767676 on white, the classic just-pass


LIGHT = "try { localStorage.setItem('necropsy-theme', 'light'); } catch (e) {}"


@pytest.fixture(scope="module", params=["dark", "light"])     # both themes meet 4.5:1 (second clarity pass)
def rendered_pairs(base_url, request):
    return run(base_url, COLLECT + SCREENS, reduced_motion=True, **({"prelude": LIGHT} if request.param == "light" else {}))


def test_every_rendered_text_pair_meets_4_5(rendered_pairs):
    failing = {}
    for p in rendered_pairs:
        a = p["alpha"]
        fg = [f * a + b * (1 - a) for f, b in zip(p["fg"], p["bg"])]
        r = contrast(fg, p["bg"])
        if r < 4.5:
            key = (p["sel"], tuple(round(v) for v in fg), tuple(round(v) for v in p["bg"]))
            failing.setdefault(key, (round(r, 2), p["screen"], p["text"]))
    assert not failing, "text below 4.5:1: " + "; ".join(
        f"{sel} {fg} on {bg} = {r} ({screen}: '{text}')" for (sel, fg, bg), (r, screen, text) in sorted(failing.items()))


def test_the_contrast_probe_saw_every_screen(rendered_pairs):
    screens = {p["screen"] for p in rendered_pairs}
    assert screens == {"start", "start-error", "resolved", "replay-mid", "hex-highlight", "hex-tooltip", "spec", "ambiguity", "failed"}
    assert len(rendered_pairs) > 300


# ---- 20.8: the page declares a dark colour scheme, so native controls (scrollbars included) render dark ----

def test_colour_scheme_is_dark_on_every_screen(base_url):
    got = run(base_url, r"""
(async () => {
  const scheme = () => getComputedStyle(document.documentElement).colorScheme;
  await __start();
  const out = { start: scheme() };
  [...document.querySelectorAll('.pick')].find(b => b.textContent === 'mystery_i').click();
  await __until(() => document.querySelector('.exam-right:not(.pending) canvas'), 'result');
  out.result = scheme();
  [...document.querySelectorAll('.vtab')].find(b => b.textContent === 'Emitted spec').click();
  await __until(() => document.querySelector('.spec-text'), 'spec');
  out.spec = scheme();
  return JSON.stringify(out);
})()
""", reduced_motion=True)
    assert got == {"start": "dark", "result": "dark", "spec": "dark"}

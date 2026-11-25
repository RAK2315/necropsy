"""UI tasks 40 to 46, built by Claude Code, not Kiro (Rehaan, 25 Nov; see docs/UI-CLARITY-PASS.md).

In a real browser against the real app:
  40. the header and state line stay on screen while the page scrolls;
  41. the evidence (header values, bytes) is part of the page again, not collapsed;
  42. explanations: why it fits worked through, each replay step explained (and every step on request), what each
      correction did, what each header value holds, what each failure reason means;
  43. a file that fits at the first check still shows that check on the examining screen, and several readings show
      each one that fits;
  44. a favicon, a mark beside the name, and the name goes back to the start;
  45. the landing page explains the three steps and groups the files by where they came from;
  46. no side-stripe callouts and no wide-tracked logo in the stylesheet.
Expected text is built here in Python from the payload, not from the page's JavaScript.
"""
import re
from decimal import ROUND_HALF_UP, Decimal

from tests.conftest import REPO_ROOT, corpus_bytes
from tests.ui.conftest import run_in_browser

PUBLIC = REPO_ROOT / "public"


def payload(data):
    import app as service
    return service._analyse(data)


HELPERS = r"""
window.__pick = async (name) => (await __until(() => [...document.querySelectorAll('.pick')].find(b => b.textContent === name), name)).click();
window.__result = async () => __until(() => document.querySelector('[data-cap=verdict]:not(.pending)'), 'result');
window.__home = async () => { document.getElementById('again').click(); await __until(() => document.querySelector('.pick'), 'home'); };
window.__shown = (e) => !!e && e.getClientRects().length > 0 && getComputedStyle(e).visibility === 'visible';
"""

# ---- 40 and 41 ----

STICKY = HELPERS + r"""
(async () => {
  await __pick('mystery_i'); await __result();
  scrollTo(0, document.body.scrollHeight);
  await new Promise(r => setTimeout(r, 200));
  const a = document.getElementById('again').getBoundingClientRect(), s = document.querySelector('[data-cap=state]').getBoundingClientRect();
  return JSON.stringify({ scrolled: scrollY > 400, againTop: a.top, againShown: a.height > 0, stateTop: s.top,
    details: document.querySelectorAll('details.ev').length,
    bytes: __shown(document.querySelector('[data-cap=ev-bytes] .hex-scroll')),
    fields: __shown(document.querySelector('[data-cap=ev-fields] table.fields')) });
})()
"""


def test_header_stays_and_evidence_is_inline(base_url):
    got = run_in_browser(base_url, STICKY, reduced_motion=True)
    assert got["scrolled"], got
    assert 0 <= got["againTop"] < 60 and got["againShown"], f"'Examine another file' scrolled away: {got}"
    assert 0 <= got["stateTop"] < 100, got
    assert got["details"] == 0 and got["bytes"] and got["fields"], f"the evidence must be shown without a click: {got}"


# ---- 42 ----

EXPLAIN = HELPERS + r"""
(async () => {
  const out = {};
  await __pick('mystery_i'); await __result();
  out.proof = document.querySelector('.proof-explain').textContent;
  out.why = document.querySelector('[data-cap=replay-why]').textContent;
  out.rxBefore = [...document.querySelectorAll('.rp-item .rx')].filter(__shown).length;
  document.querySelector('[data-cap=explain]').click();
  out.rx = [...document.querySelectorAll('.rp-item .rx')].filter(__shown).map(e => e.textContent);
  out.items = document.querySelectorAll('.rp-item').length;
  out.pressed = document.querySelector('[data-cap=explain]').getAttribute('aria-pressed');
  out.facts = [...document.querySelectorAll('.fact')].map(f => ({ title: f.querySelector('.fact-title').textContent, text: f.querySelector('.fact-text').textContent }));
  out.fp = [...document.querySelectorAll('table.fields tr')].slice(1).map(tr => [tr.children[1].firstChild.textContent, (tr.querySelector('.fp') || {}).textContent || '']);
  await __home(); document.querySelector('[data-cap=tile-2]').click(); await __result();
  out.reasonLines = [...document.querySelectorAll('.reason-line')].map(e => e.textContent);
  out.stageLines = [...document.querySelectorAll('.stage-line')].map(e => e.textContent);
  return JSON.stringify(out);
})()
"""


def test_explanations(base_url):
    got = run_in_browser(base_url, EXPLAIN, reduced_motion=True)
    p = payload(corpus_bytes("mystery_i"))
    c = p["candidates"][0]
    n = c["data_end"] - c["data_start"]
    assert f"Unpacked, its {n:,} stored bytes become exactly {c['height']} rows × {c['row_stride']} bytes = {c['expected_decoded_bytes']:,} bytes" in got["proof"], got["proof"]
    assert got["why"] == (f"The engine tried a {c['width']} × {c['height']} picture at {c['bit_depth']} bits per pixel, after a "
                          f"{c['header_size']}-byte header. It uses every byte of the picture data exactly, so it is accepted.")
    assert got["rxBefore"] == 0 and got["pressed"] == "true"
    assert len(got["rx"]) == got["items"] == len(p["rejections"]) + 1, "every step has its explanation once asked for"
    for r, text in zip(p["rejections"], got["rx"]):
        h = r["hypothesis"]
        assert f"a {h['width']} × {h['height']} picture at {h['bit_depth']} bits per pixel" in text, (r, text)
        if r["reason"] == "arithmetic_mismatch" and r["discrepancy"] > 0:
            assert f"The picture data is {r['discrepancy']:,} byte" in text and "longer than a picture this size needs" in text, text
    titles = [f["title"] for f in got["facts"]]
    assert titles[:2] == ["Counted the header’s bounds inclusively (+1)", "Tried PCX run-length decoding"], titles
    assert f"counting both ends gives {c['width']} × {c['height']}" in got["facts"][0]["text"]
    assert all(f["text"] for f in got["facts"])
    plain = dict(got["fp"])
    assert plain["xmin"] == "first column" and plain["bit_depth"] == "bits per pixel", plain
    assert got["reasonLines"] and all(t.strip() for t in got["reasonLines"]), got
    assert got["stageLines"] and all(t.strip() for t in got["stageLines"]), got


# ---- 43 ----

FIRST = HELPERS + r"""
(async () => {
  const out = {};
  for (const name of ['pillow_hopper_1bit.pbm', 'mystery_g']) {
    await __pick(name);
    const busy = await __until(() => document.querySelector('#view > .busy'), 'busy');
    let seen = 0, caption = '';
    while (document.querySelector('#view > .busy')) {
      const n = busy.querySelectorAll('[data-cap=busy-steps] li').length;
      if (n > seen) { seen = n; caption = busy.querySelector('[data-cap=busy-caption]').textContent; }
      await new Promise(r => setTimeout(r, 30));
    }
    out[name] = { seen, caption, lines: [...busy.querySelectorAll('[data-cap=busy-steps] li .rh')].map(e => e.textContent) };
    await __result(); await __home();
  }
  return JSON.stringify(out);
})()
"""


def test_first_check_files_still_show_their_checks(base_url):
    got = run_in_browser(base_url, FIRST)
    hop = payload((REPO_ROOT / "spike" / "samples" / "real" / "pillow_hopper_1bit.pbm").read_bytes())
    c = hop["candidates"][0]
    assert got["pillow_hopper_1bit.pbm"]["seen"] == 1
    assert got["pillow_hopper_1bit.pbm"]["caption"] == f"Fits: {c['width']} × {c['height']}, {c['bit_depth']}-bit."
    g = payload(corpus_bytes("mystery_g"))
    assert not g["rejections"]
    lines = got["mystery_g"]["lines"]
    assert len(lines) == len(g["candidates"]) + 1, lines
    for cand, line in zip(g["candidates"], lines):
        assert line.startswith(f"fits · {cand['width']} × {cand['height']} · {cand['bit_depth']}-bit · header {cand['header_size']}"), (cand, line)
    assert lines[-1] == "result: UNRESOLVED_AMBIGUITY"


# ---- 44 and 45 ----

LANDING = HELPERS + r"""
(async () => {
  await __until(() => document.querySelector('.sample-group'), 'groups');
  const icon = document.querySelector('link[rel=icon]');
  const out = { icon: icon && icon.getAttribute('href'), iconStatus: (await fetch(icon.getAttribute('href'))).status,
    mark: __shown(document.querySelector('#home svg.mark')), home: document.getElementById('home').tagName,
    steps: [...document.querySelectorAll('[data-cap=how] li strong')].map(e => e.textContent),
    groups: [...document.querySelectorAll('.sample-group')].map(g => ({ title: g.querySelector('h3').textContent,
      line: g.querySelector('.group-line').textContent, names: [...g.querySelectorAll('.pick')].map(b => b.textContent) })) };
  await __pick('mystery_h'); await __result();
  document.getElementById('home').click();
  out.back = !!(await __until(() => document.querySelector('[data-cap=hero]'), 'start'));
  return JSON.stringify(out);
})()
"""


def test_brand_favicon_and_landing(base_url):
    got = run_in_browser(base_url, LANDING, reduced_motion=True)
    assert got["icon"] == "/favicon.svg" and got["iconStatus"] == 200
    assert got["mark"] and got["home"] == "A" and got["back"]
    assert got["steps"] == ["It reads what the file declares.", "It tries the layouts those numbers allow.", "It accepts only an exact fit."]
    groups = {g["title"]: g["names"] for g in got["groups"]}
    assert list(groups) == ["Real pictures", "Test files made for NECROPSY", "Written by Pillow"]
    assert groups["Real pictures"] == ["imagemagick_input.tga", "pillow_hopper_1bit.pbm", "pillow_pil184.pcx", "pillow_odd_stride.pcx"]
    assert groups["Test files made for NECROPSY"] == ["mystery_" + c for c in "abcdefghi"]
    assert groups["Written by Pillow"] == ["external_a", "external_b"]
    assert all(g["line"] for g in got["groups"])


# ---- 46 ----

def test_no_side_stripes_or_wide_tracked_logo():
    css = (PUBLIC / "app.css").read_text(encoding="utf-8")
    stripes = re.findall(r"border-(?:left|right)\s*:\s*([2-9]|\d{2,})px", css)
    assert not stripes, f"side-stripe borders: {stripes}"
    brand = re.search(r"\.brand \{[^}]*\}", css).group(0)
    m = re.search(r"letter-spacing:\s*([0-9]*\.?[0-9]+)em", brand)
    assert m is None or float(m.group(1)) <= 0.08, f"the logo is tracked wide: {brand}"


# ---- 47: the ambiguity cards, read at a glance ----

CARDS = HELPERS + r"""
(async () => {
  await __pick('mystery_g'); await __result();
  return JSON.stringify([...document.querySelectorAll('.card')].map(c => ({ title: c.querySelector('.card-title').textContent,
    rows: [...c.querySelectorAll('.cf')].map(r => [r.querySelector('dt').textContent, r.querySelector('dd').textContent]) })));
})()
"""


def test_cards_are_labelled_rows(base_url):
    got = run_in_browser(base_url, CARDS, reduced_motion=True)
    cands = payload(corpus_bytes("mystery_g"))["candidates"]
    assert len(got) == len(cands)
    for card, c in zip(got, cands):
        assert card["title"] == f"{c['width']} × {c['height']} · {c['bit_depth']}-bit"
        # JavaScript's toFixed(4) rounds the exact binary value half up; Python's format rounds half to even
        coh = str(Decimal(c["coherence_score"]).quantize(Decimal("0.0001"), ROUND_HALF_UP)) if c["coherence_status"] == "scored"             else c["coherence_status"].replace("_", " ")
        assert card["rows"] == [["Header", f"{c['header_size']} bytes"],
                                ["Each row", f"{c['row_stride']} byte{'' if c['row_stride'] == 1 else 's'}" + (f", padded to {c['row_alignment']}" if c["row_alignment"] > 1 else "")],
                                ["Compression", "none" if c["encoding"] == "none" else "PCX run-length"],
                                ["Data bytes", f"{c['data_start']}–{c['data_end'] - 1}"],
                                ["Row similarity", coh]], card

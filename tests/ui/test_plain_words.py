"""UI clarity pass, task 26: a title and one plain line on every region, the glossary applied, no small text.
Built by Claude Code, not Kiro (see docs/UI-CLARITY-PASS.md).

The jargon scan reads every visible text node on every screen (landing, refusal, each outcome mid-replay and at rest,
the spec view) and fails on any engine term outside a `.tech` element or the emitter's verbatim text. Translate, never
diagnose: words that convict the file ("lies", "wrong", "false") are banned as well.
"""
import re

from necropsy.engine import Engine
from tests.conftest import corpus_bytes
from tests.ui.conftest import run_in_browser

COLLECT = r"""
window.__texts = (screen) => {
  const out = [];
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  for (let n = walker.nextNode(); n; n = walker.nextNode()) {
    const t = n.textContent.trim();
    const e = n.parentElement;
    if (!t || !e || e.closest('.tech, [data-verbatim], script, style, [hidden]')) continue;
    const s = getComputedStyle(e);
    if (s.visibility !== 'visible' || s.display === 'none' || !e.getClientRects().length) continue;
    out.push({ screen, text: t, sel: e.tagName.toLowerCase() + '.' + String(e.className).trim().split(/\s+/).join('.'), px: parseFloat(s.fontSize) });
  }
  return out;
};
window.__regions = () => [...document.querySelectorAll('.region')].filter(r => r.getClientRects().length).map(r => ({
  name: r.dataset.region, title: (r.querySelector(':scope > .region-head > .r-title') || {}).textContent || '',
  line: (r.querySelector(':scope > .region-head > .r-line') || {}).textContent || '' }));
window.__verdict = () => { const v = document.querySelector('[data-cap=verdict] .verdict-text'); return v ? v.textContent : null; };
window.__open = async (name) => {
  (await __until(() => [...document.querySelectorAll('.pick')].find(b => b.textContent === name), name)).click();
  await __until(() => document.querySelector('.rp-counter') && document.querySelector('.rp-counter').textContent, 'replay');
};
window.__rest = async () => {
  const b = document.querySelector('.rp-bar button[title="Skip to the end"]'); if (b && !b.disabled) b.click();
  await __until(() => !document.querySelector('.exam-right.pending, .verdict-bar.pending'), 'at rest');
  for (const d of document.querySelectorAll('details.ev')) d.open = true;    // scan the evidence too, not only what shows first
};
window.__home = async () => { document.getElementById('again').click(); await __until(() => document.querySelectorAll('.strip-tile[data-status]').length === 3, 'home'); };
"""

SCENARIO = COLLECT + r"""
(async () => {
  const texts = [], regions = {}, verdicts = {}, extra = {};
  await __until(() => document.querySelectorAll('.strip-tile[data-status]').length === 3, 'strip');
  await __until(() => document.querySelector('.samples ul'), 'samples');
  texts.push(...__texts('landing'));
  const dt = new DataTransfer(); dt.items.add(new File([new Uint8Array(70000)], 'big.bin'));
  document.querySelector('.drop').dispatchEvent(new DragEvent('drop', { dataTransfer: dt, bubbles: true, cancelable: true }));
  await __until(() => document.querySelector('.drop-msg.bad'), 'refusal'); texts.push(...__texts('refusal'));

  await __open('mystery_i'); texts.push(...__texts('resolved-mid'));
  await __rest(); texts.push(...__texts('resolved')); regions.resolved = __regions(); verdicts.resolved = __verdict();
  extra.contradiction = (document.querySelector('[data-cap=contradiction] .c-title') || {}).textContent || null;
  extra.chip = document.querySelector('[data-cap=chip]').textContent;
  [...document.querySelectorAll('.vtab')].find(b => b.textContent === 'Emitted spec').click();
  await __until(() => document.querySelector('[data-cap=spec] .spec-text'), 'spec');
  texts.push(...__texts('spec'));
  extra.specTitle = document.querySelector('[data-cap=spec] .r-title').textContent;

  await __home(); await __open('pillow_odd_stride.pcx'); await __rest();
  texts.push(...__texts('odd_stride')); regions.odd = __regions();
  extra.oddContradiction = !!document.querySelector('[data-cap=contradiction]');

  await __home(); await __open('mystery_d'); await __rest();
  texts.push(...__texts('ambiguity')); regions.ambiguity = __regions(); verdicts.ambiguity = __verdict();
  document.querySelector('.card').click(); texts.push(...__texts('ambiguity-selected'));

  await __home(); document.querySelector('[data-cap=tile-2]').click();
  await __until(() => document.querySelector('.rp-counter') && document.querySelector('.rp-counter').textContent, 'failed');
  texts.push(...__texts('failed-mid'));
  await __rest(); texts.push(...__texts('failed')); regions.failed = __regions(); verdicts.failed = __verdict();
  return JSON.stringify({ texts, regions, verdicts, extra });
})()
"""

# Engine terms that must not appear in visible text outside `.tech` (whole words, so file names such as
# pillow_odd_stride.pcx are not hits), and words that diagnose the file instead of translating a finding.
JARGON = [r"\bclosure\b", r"\bhypothes\w*", r"\bcandidates?\b", r"\bprobes?\b", r"\brevisions?\b", r"\btermination\b",
          r"\bstride\b", r"\bdecoder_\w+", r"\barithmetic_mismatch\b", r"\binclusive_bounds\b", r"\brow_padding\w*",
          r"\brle_pcx\b", r"\brow_mad\w*", r"\bUNRESOLVED_AMBIGUITY\b", r"\bRESOLVED\b", r"\bFAILED\b",
          r"\blies\b", r"\blying\b", r"\bwrong\b", r"\bfalse\b"]
CASE_SENSITIVE = {r"\bUNRESOLVED_AMBIGUITY\b", r"\bRESOLVED\b", r"\bFAILED\b"}

RAISED = {"card-line", "card-note", "card-coh", "rp-label", "hex-head", "gut", "eq", "strip-dims", "strip-more"}


def _scan(got):
    hits = set()
    for t in got["texts"]:
        for pat in JARGON:
            if re.search(pat, t["text"], 0 if pat in CASE_SENSITIVE else re.IGNORECASE):
                hits.add((t["screen"], t["sel"], pat, t["text"][:70]))
    return sorted(hits)


def test_plain_words_titles_and_sizes(base_url):
    got = run_in_browser(base_url, SCENARIO)

    hits = _scan(got)
    assert not hits, "engine terms or diagnoses outside .tech:\n" + "\n".join(map(str, hits))
    assert {t["screen"] for t in got["texts"]} == {"landing", "refusal", "resolved-mid", "resolved", "spec", "odd_stride",
                                                   "ambiguity", "ambiguity-selected", "failed-mid", "failed"}

    want = {"resolved": {"replay", "hex", "image", "proof", "facts", "fields", "evidence"},
            "odd": {"replay", "hex", "image", "proof", "facts", "fields", "evidence"},
            "ambiguity": {"replay", "hex", "fields", "glance", "cards", "evidence"}, "failed": {"replay", "hex", "groups", "evidence"}}
    for screen, names in want.items():
        regs = got["regions"][screen]
        assert {r["name"] for r in regs} == names, (screen, regs)
        assert all(r["title"].strip() and r["line"].strip() for r in regs), (screen, regs)

    h = Engine().run(corpus_bytes("mystery_i")).candidate.hypothesis
    n = len(Engine().run(corpus_bytes("mystery_d")).candidates)
    assert got["verdicts"] == {"resolved": f"Recovered: {h.width} × {h.height}, {h.bit_depth}-bit",
                               "ambiguity": f"{n} readings fit exactly. NECROPSY does not choose.",
                               "failed": "Not recovered: no layout tried fits the data exactly"}
    assert got["extra"]["contradiction"] == "Declared: no compression. Only run-length decoding fits."
    assert got["extra"]["oddContradiction"] is False, "odd_stride declares its compression; there is no contradiction to show"
    assert got["extra"]["chip"] == "Recovered RESOLVED"
    assert got["extra"]["specTitle"] == "A spec for this file’s format"

    small = sorted({(t["sel"], t["px"]) for t in got["texts"] if t["px"] < 12})
    assert not small, f"text below 12 px: {small}"
    raised = sorted({(t["sel"], t["px"]) for t in got["texts"] if RAISED & set(t["sel"].split(".")) and t["px"] < 12.5})
    assert not raised, f"text that was 11 to 11.5 px must now be 12.5 px: {raised}"

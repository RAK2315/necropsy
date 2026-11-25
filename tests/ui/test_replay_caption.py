"""UI clarity pass, task 27: the replay announces itself. Built by Claude Code, not Kiro.

A caption rewritten in plain words on every step, a header that says this is a slowed-down replay of a search that
already finished, a placeholder in the answer column while the answer is pending, and a replay with
nothing to replay hides its controls. The expected captions are written here in Python from the engine's own
rejections, independently of the page's JavaScript.
"""
import re

from necropsy.engine import Engine
from tests.conftest import corpus_bytes
from tests.ui.conftest import run_in_browser

# Same wording as public/js/words.js reasonText, restated here so the page is checked against the engine, not itself.
REASON = {
    "decoder_overrun": "a run would write past the size of the picture",
    "decoder_underrun": "the data ran out before the picture was full",
    "decoder_unconsumed": "decoding finished with bytes left over",
    "degenerate_hypothesis": "not a usable layout: a size is not positive, or the header overlaps the data",
    "field_out_of_bounds": "a declared position lies outside the file",
    "probe_precondition_failed": "a declared value is outside what the format allows",
    "unsupported_encoding": "this encoding is recognised but not decoded",
}


def reason(r):
    if r.reason == "arithmetic_mismatch":
        d = r.discrepancy
        return f"the data is {abs(d):,} byte{'' if abs(d) == 1 else 's'} {'longer' if d > 0 else 'shorter'} than this layout needs"
    return REASON[r.reason]


def caption(r, i, n):
    h = r.hypothesis
    what = f"Trying {h.width} × {h.height}, {h.bit_depth}-bit, header {h.header_size} bytes…" if h else "Checking the format’s own declarations…"
    return f"Step {i + 1} of {n}. {what} rejected: {reason(r)}."


STEPS = r"""
(async () => {
  (await __until(() => [...document.querySelectorAll('.pick')].find(b => b.textContent === 'mystery_i'), 'sample')).click();
  const cap = await __until(() => document.querySelector('[data-cap=replay-caption]'), 'caption');
  const out = { live: cap.getAttribute('aria-live'), head: document.querySelector('.rp-head').textContent };
  out.pendingNow = !!document.querySelector('.exam-right.pending [data-cap=answer-pending]');
  out.pendingText = (document.querySelector('[data-cap=answer-pending]') || {}).textContent || '';
  out.pendingButtons = document.querySelectorAll('[data-cap=answer-pending] button').length;
  document.querySelector('.rp-bar button[title="Play or pause"]').click();
  const back = document.querySelector('.rp-bar button[title="Step back"]');
  while (!back.disabled) back.click();
  const fwd = document.querySelector('.rp-bar button[title="Step forward"]');
  out.frames = [];
  for (;;) {
    out.frames.push({ counter: document.querySelector('.rp-counter').textContent, caption: cap.textContent });
    if (fwd.disabled) break;
    fwd.click();
  }
  out.pendingAtEnd = !!document.querySelector('[data-cap=answer-pending]');
  document.getElementById('again').click();
  (await __until(() => [...document.querySelectorAll('.pick')].find(b => b.textContent === 'mystery_d'), 'sample d')).click();
  await __until(() => document.querySelector('.verdict-bar:not(.pending)'), 'ambiguity verdict');
  const visible = (e) => !!e && e.getClientRects().length > 0 && getComputedStyle(e).visibility === 'visible';
  out.single = { head: document.querySelector('.rp-head').textContent,
    controls: [...document.querySelectorAll('.rp-bar button, .rp-speed')].filter(visible).length,
    caption: visible(document.querySelector('[data-cap=replay-caption]')),
    pending: !!document.querySelector('[data-cap=answer-pending]') };
  return JSON.stringify(out);
})()
"""


def test_replay_announces_itself(base_url):
    got = run_in_browser(base_url, STEPS)
    r = Engine().run(corpus_bytes("mystery_i"))
    h = r.candidate.hypothesis
    n_steps = len(r.rejections) + 1
    expected = [caption(x, i, n_steps) for i, x in enumerate(r.rejections)] + [f"Fits: {h.width} × {h.height}, {h.bit_depth}-bit."]

    assert got["live"] == "polite"
    assert re.fullmatch(r"Replaying the engine’s search\. It finished in [0-9.]+ ms; this replay slows it down so you "
                        r"can follow it\.", got["head"]), got["head"]

    frames = got["frames"]
    assert len(frames) > 2
    for f in frames:                                     # the caption describes the last step of the frame on screen
        last = int(re.search(r"(\d+) of \d+$", f["counter"]).group(1))
        assert f["caption"] == expected[last - 1], (f["counter"], f["caption"], expected[last - 1])
    captions = [f["caption"] for f in frames]
    assert all(a != b for a, b in zip(captions, captions[1:])), "the caption must change on every step"
    assert captions[-1] == expected[-1]

    assert got["pendingNow"] and got["pendingText"] == "The answer appears here when the replay ends."
    assert got["pendingButtons"] == 0, "UI task 37: no skip in the answer column while the first run plays"
    assert not got["pendingAtEnd"]

    n = Engine().run(corpus_bytes("mystery_d")).total_checks
    assert got["single"] == {"head": f"Nothing to replay: all {n} layouts checked fit.", "controls": 0, "caption": False, "pending": False}

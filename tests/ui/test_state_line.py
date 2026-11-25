"""UI clarity pass, task 25: a state line under the header on every screen. Built by Claude Code, not Kiro.

It answers which file, which stage, whether anything is running, and the verdict, and is announced (aria-live polite).
Driven in a real browser against the real app, with the analysis request slowed so the sending state can be seen.
"""
from necropsy.engine import Engine
from tests.conftest import corpus_bytes
from tests.ui.conftest import run_in_browser

SLOW = r"""
(() => { const real = window.fetch.bind(window); window.__slowApi = false;
  window.fetch = (i, o) => (window.__slowApi && String(i && i.url || i).includes('/api/analyze'))
    ? new Promise(r => setTimeout(() => r(real(i, o)), 700)) : real(i, o); })();
"""

SCENARIO = r"""
(async () => {
  const line = () => document.querySelector('[data-cap=state]');
  const text = () => line() ? line().textContent : null;
  const out = { live: line() && line().getAttribute('aria-live'), under: line() && line().previousElementSibling.tagName };
  await __until(() => document.querySelectorAll('.strip-tile[data-status]').length === 3, 'strip');
  await __until(() => document.querySelector('.samples ul'), 'samples');
  out.idle = text();
  window.__slowApi = true;
  [...document.querySelectorAll('.pick')].find(b => b.textContent === 'mystery_i').click();
  await __until(() => document.querySelector('.busy'), 'busy');
  out.sending = text();
  window.__slowApi = false;
  out.replaying = await __until(() => /Replaying/.test(text()) ? text() : null, 'replaying');
  document.querySelector('.rp-bar button[title="Skip to the end"]').click();
  out.doneAtFinal = text();
  await new Promise(r => setTimeout(r, 1500));
  out.doneLater = text();
  document.getElementById('again').click();
  await __until(() => document.querySelectorAll('.strip-tile[data-status]').length === 3, 'strip again');
  out.idleAgain = text();
  document.querySelector('[data-cap=tile-1]').click();
  await __until(() => /readings fit/.test(text()), 'ambiguity done');
  out.ambiguity = text();
  document.getElementById('again').click();
  await __until(() => document.querySelectorAll('.strip-tile[data-status]').length === 3, 'strip 3');
  document.querySelector('[data-cap=tile-2]').click();
  await __until(() => document.querySelector('.rp-bar button[title="Skip to the end"]'), 'failed replay');
  document.querySelector('.rp-bar button[title="Skip to the end"]').click();
  out.failed = text();
  document.getElementById('again').click();
  await __until(() => document.querySelector('.drop'), 'start');
  const dt = new DataTransfer(); dt.items.add(new File([new Uint8Array(70000)], 'big.bin'));
  document.querySelector('.drop').dispatchEvent(new DragEvent('drop', { dataTransfer: dt, bubbles: true, cancelable: true }));
  await __until(() => document.querySelector('.drop-msg.bad'), 'refusal');
  out.refused = text();
  return JSON.stringify(out);
})()
"""


def test_state_line_on_every_screen(base_url):
    got = run_in_browser(base_url, SCENARIO, prelude=SLOW)
    assert got["live"] == "polite" and got["under"] == "HEADER"
    assert got["idle"] == got["idleAgain"] == "No file loaded. Try a sample or drop your own."
    assert got["sending"] == "mystery_i · 955 bytes · Examining…"

    r = Engine().run(corpus_bytes("mystery_i"))
    h = r.candidate.hypothesis
    assert got["replaying"].startswith("mystery_i · 955 bytes · Finished in ") and " ms · Replaying the search: step " in got["replaying"]
    done = f"mystery_i · 955 bytes · Recovered: {h.width} × {h.height}, {h.bit_depth}-bit"
    assert got["doneAtFinal"] == done
    assert got["doneLater"] == done, "the state line must not say Replaying after the final step"

    n = len(Engine().run(corpus_bytes("mystery_d")).candidates)
    assert got["ambiguity"] == f"mystery_d · 104 bytes · {n} readings fit exactly. NECROPSY does not choose."
    assert got["failed"] == "mystery_b_first300 · 300 bytes · Not recovered: no layout tried fits the data exactly"
    assert got["refused"] == ("big.bin · Not examined: That file is 70,000 bytes. The limit is 65,536 bytes. "
                            "Try a smaller file or a fragment of it.")

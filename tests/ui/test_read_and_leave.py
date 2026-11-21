"""Two failure paths around a result, in a real browser.

1. A dropped file whose bytes cannot be read (file.arrayBuffer() rejects, as a dropped folder's entry can) must leave a
   message on the start screen, not nothing.
2. Leaving a result while its replay is running (Escape, or "Examine another file") must stop the replay. The replay
   calls onStep or onFinal exactly when it updates its step counter, so changes to the detached counter after leaving
   count those calls.
"""
import pytest

from tests.ui.conftest import run_in_browser

UNREADABLE = r"""
(async () => {
  await __until(() => document.querySelector('.drop'), 'start');
  const f = new File([new Uint8Array(10)], 'Holiday photos');                  // non-empty, so the empty-file rule does not apply
  Object.defineProperty(f, 'arrayBuffer', { value: () => Promise.reject(new DOMException('A requested file or directory could not be found', 'NotFoundError')) });
  let unhandled = 0;
  window.addEventListener('unhandledrejection', () => { unhandled++; });
  const dt = { files: [f] };
  const ev = new Event('drop', { bubbles: true, cancelable: true });
  Object.defineProperty(ev, 'dataTransfer', { value: dt });
  document.querySelector('.drop').dispatchEvent(ev);
  await new Promise(r => setTimeout(r, 1500));
  const msg = document.querySelector('.drop-msg');
  return JSON.stringify({ msg: msg ? msg.textContent : null, bad: !!(msg && msg.classList.contains('bad')),
                          onStart: !!document.querySelector('.drop'), busy: !!document.querySelector('.busy'), unhandled });
})()
"""


def test_an_unreadable_dropped_file_is_stated(base_url):
    got = run_in_browser(base_url, UNREADABLE)
    assert got["onStart"] and not got["busy"]
    assert got["bad"], f"no message on the start screen: {got}"
    assert got["msg"] == ("Holiday photos could not be read, so it was not examined. "
                          "If it is a folder, drop a file from inside it instead.")
    assert got["unhandled"] == 0


def leave(how):
    act = ("await __key('Escape');" if how == "escape" else "document.getElementById('again').click();")
    return r"""
(async () => {
  await __until(() => document.querySelector('.pick'), 'start');
  [...document.querySelectorAll('.pick')].find(b => b.textContent === 'mystery_i').click();
  const counter = await __until(() => { const c = document.querySelector('.rp-counter'); return c && c.textContent ? c : null; }, 'replay');
  const first = counter.textContent;
  await __until(() => counter.textContent !== first, 'replay running');        // it has advanced at least once
  const at = counter.textContent;
  """ + act + r"""
  await __until(() => document.querySelector('.drop'), 'start screen');
  let changes = 0;
  new MutationObserver((m) => { changes += m.length; }).observe(counter, { childList: true, characterData: true, subtree: true });
  await new Promise(r => setTimeout(r, 3000));     // at 1x a step is 600 ms: a running chain would change it about 5 times
  return JSON.stringify({ at, after: counter.textContent, changes, attached: document.contains(counter) });
})()
"""


@pytest.mark.parametrize("how", ["escape", "again"])
def test_leaving_a_result_stops_its_replay(base_url, how):
    got = run_in_browser(base_url, leave(how))
    assert got["attached"] is False
    assert got["changes"] == 0, f"the replay kept stepping after leaving ({how}): {got}"

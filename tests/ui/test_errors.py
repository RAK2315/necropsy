"""Error copy (Requirement 19): each failure path says what happened and what to do next, from the actual cause.

Real browser, real app. Network failures are faked in the browser by wrapping window.fetch for one URL, so each
test proves that the message the page shows comes from the cause it was given: a different status gives a
different number in the text, and a message written for another cause fails the exact-text assertion.
"""
import pytest

from tests.conftest import corpus_bytes
from tests.ui.conftest import run_in_browser

# Installed before page scripts. window.__fault = {urlPart: status | 'down'} makes matching requests answer that
# status, or throw as a lost connection would. window.__apiCalls counts /api/analyze requests that left the page.
FAULTS = r"""
window.__fault = window.__fault || {};
window.__apiCalls = 0;
(() => {
  const real = window.fetch.bind(window);
  window.fetch = (input, init) => {
    const url = String(input && input.url || input);
    if (url.includes('/api/analyze')) window.__apiCalls++;
    for (const [part, how] of Object.entries(window.__fault)) {
      if (url.includes(part)) {
        if (how === 'down') return Promise.reject(new TypeError('Failed to fetch'));
        return Promise.resolve(new Response('<html>error page</html>', { status: how, headers: { 'Content-Type': 'text/html' } }));
      }
    }
    return real(input, init);
  };
})();
"""

DROP = r"""
window.__drop = async (files) => {
  await __until(() => document.querySelector('.drop'), 'start');
  const dt = new DataTransfer(); for (const f of files) dt.items.add(f);
  document.querySelector('.drop').dispatchEvent(new DragEvent('drop', { dataTransfer: dt, bubbles: true, cancelable: true }));
};
window.__buttons = () => [...document.querySelectorAll('#view button')].map(b => b.textContent);
// The start screen is settled once its sample list has rendered or reported its own failure. showStart() fetches
// the list again on every re-render, so a count taken before this signal races that fetch.
window.__settled = () => __until(() => document.querySelector('.samples ul, .samples > .drop-msg'), 'sample list settled');
"""


def run(base_url, body, fault_at_load=None, rewrite=None):
    prelude = (f"window.__fault = {fault_at_load};" if fault_at_load else "") + FAULTS
    return run_in_browser(base_url, DROP + body, prelude=prelude, rewrite=rewrite)


def test_oversized_and_empty_files_are_refused_before_any_request(base_url):
    got = run(base_url, r"""
(async () => {
  await __until(() => document.querySelectorAll('.strip-tile[data-status]').length === 3, 'strip');
  await __settled();
  const before = __apiCalls, normal = __buttons().length;
  await __drop([new File([new Uint8Array(70000)], 'scan.raw')]);
  const big = (await __until(() => document.querySelector('.drop-msg.bad'), 'big')).textContent;
  document.querySelector('.drop-msg').classList.remove('bad');
  await __drop([new File([], 'empty.pcx')]);
  const empty = (await __until(() => document.querySelector('.drop-msg.bad'), 'empty')).textContent;
  return JSON.stringify({ big, empty, calls: __apiCalls - before, sameButtons: __buttons().length === normal });
})()
""")
    assert got["big"] == "That file is 70,000 bytes. The limit is 65,536 bytes. Try a smaller file or a fragment of it."
    assert got["empty"] == "empty.pcx is empty (0 bytes). There is nothing to examine. Choose a file that has content."
    assert got["calls"] == 0, "a refused file was sent to the service"
    assert got["sameButtons"], "an error added controls (Requirement 19.10)"


@pytest.mark.parametrize("how,expected", [
    (500, "The analysis service answered with HTTP 500. Your file was not examined. Try again."),
    (503, "The analysis service answered with HTTP 503. Your file was not examined. Try again."),
    ("'down'", "The analysis service could not be reached, so your file was not examined. Check your connection and try again."),
])
def test_service_failure_says_which(base_url, how, expected):
    got = run(base_url, f"""
(async () => {{
  await __until(() => document.querySelectorAll('.strip-tile[data-status]').length === 3, 'strip');
  await __settled();
  const normal = __buttons().length;
  window.__fault['/api/analyze'] = {how};
  [...document.querySelectorAll('.pick')].find(b => b.textContent === 'mystery_c').click();
  const msg = (await __until(() => document.querySelector('.drop-msg.bad'), 'message')).textContent;
  await __settled();
  return JSON.stringify({{ msg, sameButtons: __buttons().length === normal }});
}})()
""")
    assert got["msg"] == expected
    assert got["sameButtons"]


def test_service_413_uses_the_size_the_browser_holds(base_url):
    got = run(base_url, r"""
(async () => {
  await __until(() => document.querySelectorAll('.strip-tile[data-status]').length === 3, 'strip');
  window.__fault['/api/analyze'] = 413;
  [...document.querySelectorAll('.pick')].find(b => b.textContent === 'mystery_c').click();
  return JSON.stringify({ msg: (await __until(() => document.querySelector('.drop-msg.bad'), 'message')).textContent });
})()
""")
    size = len(corpus_bytes("mystery_c"))
    assert got["msg"] == f"That file is {size:,} bytes. The limit is 65,536 bytes. Try a smaller file or a fragment of it."


@pytest.mark.parametrize("how,shown", [(404, "HTTP 404"), ("'down'", "no connection")])
def test_sample_fetch_failure_is_stated_and_nothing_is_analysed(base_url, how, shown):
    got = run(base_url, f"""
(async () => {{
  await __until(() => document.querySelectorAll('.strip-tile[data-status]').length === 3, 'strip');
  const before = __apiCalls;
  window.__fault['/samples/mystery_c'] = {how};
  [...document.querySelectorAll('.pick')].find(b => b.textContent === 'mystery_c').click();
  const msg = (await __until(() => document.querySelector('.drop-msg.bad'), 'message')).textContent;
  return JSON.stringify({{ msg, calls: __apiCalls - before }});
}})()
""")
    assert got["msg"] == f"The sample mystery_c could not be loaded ({shown}). Try again, or drop a file of your own."
    assert got["calls"] == 0, "the error page was analysed as if it were the sample"


def test_sample_list_failure_is_stated_in_place(base_url):
    got = run(base_url, r"""
(async () => {
  const p = await __until(() => document.querySelector('.samples .drop-msg'), 'list message');
  return JSON.stringify({ msg: p.textContent, picks: document.querySelectorAll('.pick').length, drop: !!document.querySelector('.drop') });
})()
""", fault_at_load="{'/samples/index.json': 500}")
    assert got == {"msg": "The sample list could not be loaded. You can still drop a file of your own.", "picks": 0, "drop": True}


def test_strip_tile_names_the_sample_and_the_failure(base_url):
    got = run(base_url, r"""
(async () => {
  await __until(() => document.querySelectorAll('.strip-error').length === 3, 'three tile errors');
  const tiles = [...document.querySelectorAll('.strip-tile')];
  return JSON.stringify({ msgs: tiles.map(t => t.querySelector('.strip-error').textContent),
                          clickable: tiles.map(t => t.getAttribute('role')) });
})()
""", fault_at_load="{'/samples/imagemagick_input.tga': 503, '/samples/mystery_b': 'down', '/api/analyze': 502}")
    assert got["msgs"] == [
        "The sample imagemagick_input.tga could not be loaded (HTTP 503). Try again, or drop a file of your own.",
        "The analysis service answered with HTTP 502. Your file was not examined. Try again.",
        "The sample mystery_b could not be loaded (no connection). Try again, or drop a file of your own.",
    ]
    assert got["clickable"] == [None, None, None]


@pytest.mark.parametrize("how,expected", [
    (500, "The download failed: the service answered with HTTP 500. Try again."),
    ("'down'", "The download failed: the service could not be reached. Try again."),
])
def test_spec_zip_failure_says_which(base_url, how, expected):
    got = run(base_url, f"""
(async () => {{
  await __until(() => document.querySelector('.pick'), 'start');
  [...document.querySelectorAll('.pick')].find(b => b.textContent === 'mystery_e').click();
  const tab = await __until(() => [...document.querySelectorAll('.vtab')].find(b => b.textContent === 'Emitted spec'), 'result');
  tab.click();
  window.__fault['/api/spec.zip'] = {how};
  document.querySelector('.spec-head button').click();
  await __until(() => document.querySelector('.spec-status').textContent.startsWith('The download failed'), 'status');
  return JSON.stringify({{ msg: document.querySelector('.spec-status').textContent,
                           role: document.querySelector('.spec-status').getAttribute('role'),
                           enabled: !document.querySelector('.spec-head button').disabled }});
}})()
""")
    assert got == {"msg": expected, "role": "status", "enabled": True}


FAILED_SCREEN = r"""
(async () => {
  const b = new Uint8Array(await (await fetch('/samples/mystery_b')).arrayBuffer()).slice(0, 300);
  await __drop([new File([b], 'cut.pcx')]);
  const skip = await __until(() => document.querySelector('.rp-bar button[title="Skip to the end"]'), 'replay');
  if (!skip.disabled) skip.click();
  await __until(() => document.querySelector('.verdict-bar:not(.pending) .fail-reason'), 'failed screen');
  return JSON.stringify({ reason: document.querySelector('.fail-reason').textContent,
                          limit: [...document.querySelectorAll('.fail-limit')].map(p => p.textContent),
                          groups: document.querySelectorAll('.groups .stage').length });
})()
"""

STOPPED = ("The search stopped at its limit before it could try everything. That does not mean no layout exists. "
           "The rejections below show what was tried before it stopped.")


@pytest.mark.parametrize("termination,sentence", [
    ("deadline_exceeded", "The search stopped at the 5 second deadline."),
    ("search_cap_exceeded", "The search stopped at its 10,000-check cap."),
])
def test_failed_by_limit_keeps_10_1_and_adds_the_limit_note(base_url, termination, sentence):
    rewrite = f"(p) => {{ if (p.status === 'FAILED' && p.total_file_size === 300) p.termination = '{termination}'; return p; }}"
    got = run(base_url, FAILED_SCREEN, rewrite=rewrite)
    assert got["reason"] == sentence                     # Requirement 10.1, unchanged
    assert got["limit"] == [STOPPED]
    assert got["groups"] >= 1                            # "the rejections below" exist


def test_failed_exhausted_has_no_limit_note(base_url):
    got = run(base_url, FAILED_SCREEN)
    # the cut mystery_b matches the PCX probe, so Requirement 10.1 (amended) gives the probe-bounded sentence
    assert got["reason"] == ("The opening bytes match the PCX signature, so only layouts under its declarations were tried. "
                             "The direct layout search did not run.")
    assert got["limit"] == []

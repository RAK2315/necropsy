"""FAILED copy (Requirement 10.1, amended): a probe-matched search says it was bounded by the probe; a generic one does not.

Real browser, real app. The probe-matched file is the first 300 bytes of mystery_b (the PCX probe matches, every
reading under its declarations fails, Generic Search does not run). The generic file is built from a documented layout:
bytes that match no probe signature, followed by a TGA 2.0 footer whose extension-area offset points outside the file,
so Generic Search runs and records a field_out_of_bounds rejection per header length (engine task 18.5).
"""
import struct

from necropsy.engine import Engine
from tests.conftest import corpus_bytes
from tests.ui.conftest import run_in_browser
from web.serialise import stage_of

PROBE_SENTENCE = ("The bytes matched the PCX probe, so only readings under its declarations were tried. "
                  "Generic search did not run.")


def generic_failed_file() -> bytes:
    body = bytes((i * 37 + 11) % 251 + 3 for i in range(40))           # byte 0 is 0x0E: no probe signature
    return body + struct.pack("<II", 0xFFFFFFF0, 0) + b"TRUEVISION-XFILE.\x00"


def screen(base_url, data_js):
    return run_in_browser(base_url, f"""
(async () => {{
  const bytes = {data_js};
  await __until(() => document.querySelector('.drop'), 'start');
  const dt = new DataTransfer(); dt.items.add(new File([bytes], 'f.bin'));
  document.querySelector('.drop').dispatchEvent(new DragEvent('drop', {{ dataTransfer: dt, bubbles: true, cancelable: true }}));
  const skip = await __until(() => document.querySelector('.rp-bar button[title="Skip to the end"]'), 'replay');
  if (!skip.disabled) skip.click();
  await __until(() => document.querySelector('.exam-right:not(.pending) .fail-reason'), 'failed screen');
  return JSON.stringify({{ reason: document.querySelector('.fail-reason').textContent,
                          scope: [...document.querySelectorAll('.fail-scope')].map(p => p.textContent) }});
}})()
""")


def test_inputs_are_what_they_claim():
    cut = Engine().run(corpus_bytes("mystery_b")[:300])
    assert cut.status == "FAILED" and cut.termination == "exhausted"
    assert {stage_of(r.source) for r in cut.rejections} == {"probe", "revision"}
    gen = Engine().run(generic_failed_file())
    assert gen.status == "FAILED" and {stage_of(r.source) for r in gen.rejections} == {"generic"}


def test_probe_matched_failed_says_generic_search_did_not_run(base_url):
    got = screen(base_url, "new Uint8Array(await (await fetch('/samples/mystery_b')).arrayBuffer()).slice(0, 300)")
    assert got["reason"] == PROBE_SENTENCE
    assert not any("generic search ran" in s for s in got["scope"])


def test_generic_failed_keeps_the_generic_wording(base_url):
    data = ",".join(str(b) for b in generic_failed_file())
    got = screen(base_url, f"new Uint8Array([{data}])")
    termination = Engine().run(generic_failed_file()).termination
    assert termination == "no_hypothesis_checked"
    assert got["reason"] == "No hypothesis reached the closure gate."
    assert "probe" not in got["reason"].lower()
    assert any(s.startswith("No probe signature matched, so generic search ran.") for s in got["scope"])


def test_strip_tile_uses_the_same_sentence(base_url):
    got = run_in_browser(base_url, r"""
(async () => {
  await __until(() => document.querySelectorAll('.strip-tile[data-status]').length === 3, 'strip');
  return JSON.stringify({ term: document.querySelectorAll('.strip-tile')[2].querySelector('.strip-term').textContent });
})()
""")
    assert got["term"] == PROBE_SENTENCE

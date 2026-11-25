"""Capture hooks (UI clarity pass): every data-cap hook the recordings use exists on its screen. Added by Claude Code.

The list is tools/capture_hooks.json, which the recording preflight (video/scripts/check_selectors.mjs) also reads, so
a renamed or removed hook fails here before it can make a recording miss an element.
"""
import json

from tests.conftest import REPO_ROOT
from tests.ui.conftest import run_in_browser

HOOKS = json.loads((REPO_ROOT / "tools" / "capture_hooks.json").read_text(encoding="utf-8"))

SCENARIO = r"""
(async () => {
  const caps = () => [...new Set([...document.querySelectorAll('[data-cap]')].map(e => e.dataset.cap))];
  const out = {};
  await __until(() => document.querySelectorAll('.strip-tile[data-status]').length === 3, 'strip');
  await __until(() => document.querySelector('.samples ul'), 'samples');
  out.start = caps();
  out.sampleNames = [...document.querySelectorAll('[data-cap=sample]')].every(b => b.dataset.name === b.textContent);
  (await __until(() => [...document.querySelectorAll('.pick')].find(b => b.textContent === 'mystery_i'), 'mystery_i')).click();
  // the steps play on the examining screen (UI task 39)
  await __until(() => document.querySelector('[data-cap=busy-caption]') && document.querySelector('[data-cap=busy-caption]').textContent, 'replaying');
  out.replaying = caps();
  await __until(() => document.querySelector('[data-cap=fields]'), 'resolved');
  out.resolved = caps();
  document.querySelector('[data-cap=tab-spec]').click();
  await __until(() => document.querySelector('[data-cap=spec]'), 'spec');
  out.spec = caps().filter(c => document.querySelector(`[data-cap="${c}"]`).getClientRects().length);
  document.querySelector('[data-cap=again]').click();
  await __until(() => document.querySelectorAll('.strip-tile[data-status]').length === 3, 'home');
  document.querySelector('[data-cap=tile-1]').click();
  await __until(() => document.querySelector('[data-cap=amb-grid]'), 'ambiguity');
  out.ambiguity = caps();
  document.querySelector('[data-cap=again]').click();
  await __until(() => document.querySelectorAll('.strip-tile[data-status]').length === 3, 'home 2');
  document.querySelector('[data-cap=tile-2]').click();
  await __until(() => document.querySelector('[data-cap=failed-groups]'), 'failed');
  out.failed = caps();
  return JSON.stringify(out);
})()
"""


def test_every_capture_hook_exists_on_its_screen(base_url):
    got = run_in_browser(base_url, SCENARIO)
    missing = {screen: sorted(set(want) - set(got[screen])) for screen, want in HOOKS.items() if not screen.startswith("_")}
    missing = {k: v for k, v in missing.items() if v}
    assert not missing, f"capture hooks missing: {missing}"
    assert got["sampleNames"], "every sample hook carries data-name equal to the sample's name"

"""Task 16 acceptance pass: each demo beat on a deployed URL, in a fresh 1280x720 page, timed and captured.

python tools/acceptance.py https://necropsy.vercel.app

Time is performance.now() when the beat's state is on screen: milliseconds since the page started loading, with the
replay left to run at 1x (nothing skipped). Captures go to docs/acceptance/<beat>.png; results to results.md there.
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "acceptance"
RUNNER = ROOT / "tools" / "browser_run.mjs"

PICK = "const pick = async (n) => { await __until(() => document.querySelector('.pick'), 'start'); " \
       "[...document.querySelectorAll('.pick')].find(b => b.textContent === n).click(); };"
DROP = "const drop = async (files) => { await __until(() => document.querySelector('.drop'), 'start'); " \
       "const dt = new DataTransfer(); for (const f of files) dt.items.add(f); " \
       "document.querySelector('.drop').dispatchEvent(new DragEvent('drop', { dataTransfer: dt, bubbles: true, cancelable: true })); };"
DONE = "const t = Math.round(performance.now());"


def beat(js):
    return f"(async () => {{ {PICK} {DROP} {js} }})()"


BEATS = [
    ("13.5a", "resolved", "RESOLVED result with its recovered image (external_a)", beat(r"""
  await pick('external_a');
  await __until(() => document.querySelector('.exam-right:not(.pending) canvas.pixels'), 'image'); """ + DONE + r"""
  await new Promise(r => setTimeout(r, 2100));   // let the row reveal finish before the capture
  return JSON.stringify({ t, status: document.querySelector('.exam-right .chip').textContent,
                          image: document.querySelector('.exam-right canvas').getAttribute('aria-label') });""")),
    ("13.5b", "lying_header", "declared-versus-actual contradiction (mystery_i)", beat(r"""
  await pick('mystery_i');
  const box = await __until(() => document.querySelector('.exam-right:not(.pending) .contradiction'), 'contradiction'); """ + DONE + r"""
  await new Promise(r => setTimeout(r, 2100));   // capture after the row reveal, not mid-way
  const r = box.getBoundingClientRect();
  return JSON.stringify({ t, declared: box.querySelector('.declared').textContent, actual: box.querySelector('.actual').textContent,
                          inViewport: r.top >= 0 && r.bottom <= 720 });""")),
    ("13.5c", "ambiguity", "ambiguity screen, all candidates side by side (mystery_d)", beat(r"""
  await pick('mystery_d');
  await __until(() => document.querySelectorAll('.card canvas').length && !document.querySelector('.amb-lead.pending'), 'cards'); """ + DONE + r"""
  return JSON.stringify({ t, statement: document.querySelector('.amb-statement').textContent, cards: document.querySelectorAll('.card').length,
                          sizes: [...new Set([...document.querySelectorAll('.card')].map(c => c.offsetWidth + 'x' + c.offsetHeight))] });""")),
    ("13.5d", "failed", "FAILED screen for a non-image file (a text file)", beat(r"""
  await drop([new File([new TextEncoder().encode('Meeting notes. Nothing here is an image. '.repeat(30))], 'notes.txt')]);
  const p = await __until(() => document.querySelector('.exam-right:not(.pending) .fail-reason'), 'failed'); """ + DONE + r"""
  return JSON.stringify({ t, reason: p.textContent, termination: document.querySelector('.exam-right .source').textContent });""")),
    ("13.5e", "spec_panel", "emitted spec panel and its download (mystery_e)", beat(r"""
  await pick('mystery_e');
  const tab = await __until(() => [...document.querySelectorAll('.vtab')].find(b => b.textContent === 'Emitted spec'), 'result');
  tab.click();
  document.querySelector('.spec-head button').click();
  await __until(() => __blobs.length && __blobs[0].b64, 'zip');
  await __until(() => document.querySelector('.spec-status').textContent.startsWith('Downloaded'), 'status'); """ + DONE + r"""
  return JSON.stringify({ t, folder: document.querySelector('.spec-folder').textContent, zip: __blobs[0].name, zipBytes: atob(__blobs[0].b64).length,
                          tabs: [...document.querySelectorAll('.spec-tab')].map(b => b.textContent) });""")),
    ("16", "outcome_strip", "outcome strip: three real results on the first screen", beat(r"""
  await __until(() => document.querySelectorAll('.strip-tile[data-status]').length === 3, 'strip'); """ + DONE + r"""
  return JSON.stringify({ t, tiles: [...document.querySelectorAll('.strip-tile')].map(x => x.dataset.status + ': ' + x.querySelector('.strip-line').textContent),
                          dropFits: document.querySelector('.drop').getBoundingClientRect().bottom <= 720 });""")),
    ("17", "downloads", "PNG and data-region downloads (external_a)", beat(r"""
  await pick('external_a');
  const row = await __until(() => document.querySelector('.exam-right:not(.pending) .card-dl'), 'downloads');
  row.querySelector('[data-act="png"]').click(); await __until(() => __blobs.length === 1 && __blobs[0].b64, 'png');
  row.querySelector('[data-act="data"]').click(); await __until(() => __blobs.length === 2 && __blobs[1].b64, 'data'); """ + DONE + r"""
  await new Promise(r => setTimeout(r, 2100));   // capture after the row reveal, not mid-way
  return JSON.stringify({ t, files: __blobs.map(b => `${b.name} (${b.type}, ${atob(b.b64).length} bytes)`) });""")),
    ("18", "multi_drop", "three files dropped at once", beat(r"""
  const pcx = new Uint8Array(await (await fetch('/samples/external_a')).arrayBuffer());
  await drop([new File([pcx], 'holiday.pcx'), new File(['notes'], 'notes.txt'), new File([new Uint8Array(40)], 'blob.bin')]);
  const n = await __until(() => document.querySelector('#view > .notice'), 'notice');
  await __until(() => document.querySelector('.exam-right:not(.pending) canvas'), 'result'); """ + DONE + r"""
  await new Promise(r => setTimeout(r, 2100));   // capture after the row reveal, not mid-way
  return JSON.stringify({ t, notice: n.textContent, examined: document.querySelector('.exam-right .dims').textContent });""")),
    ("19", "error_copy", "error copy: a file over the limit", beat(r"""
  await drop([new File([new Uint8Array(70000)], 'scan.raw')]);
  const m = await __until(() => document.querySelector('.drop-msg.bad'), 'message'); """ + DONE + r"""
  return JSON.stringify({ t, message: m.textContent });""")),
    ("20", "keyboard", "keyboard: Tab to the second tile, Enter, then Escape", beat(r"""
  await __until(() => document.querySelectorAll('.strip-tile[data-status]').length === 3, 'strip');
  let presses = 0;
  while (!(document.activeElement && document.activeElement.dataset && document.activeElement.dataset.slot === '1')) { await __key('Tab'); if (++presses > 30) throw new Error('Tab never reached the tile'); }
  const ring = getComputedStyle(document.activeElement).outlineStyle;
  await __key('Enter');
  await __until(() => document.querySelectorAll('.card').length, 'opened'); const opened = document.querySelectorAll('.card').length;
  await __key('Escape');
  await __until(() => document.querySelector('.drop') && document.querySelectorAll('.strip-tile[data-status]').length === 3, 'back');
  while (!(document.activeElement && document.activeElement.dataset && document.activeElement.dataset.slot === '1')) await __key('Tab'); """ + DONE + r"""
  await __until(() => document.querySelector('.samples ul'), 'sample list, for the capture');
  return JSON.stringify({ t, tabPresses: presses, focusRing: ring, openedCards: opened, escapeReturned: true });""")),
]


def run(url, name, js):
    with tempfile.TemporaryDirectory() as d:
        sp = Path(d) / "s.js"
        sp.write_text(js, encoding="utf-8")
        out = subprocess.run(["node", str(RUNNER), url, str(sp), "--shot", str(OUT / f"{name}.png")],
                             capture_output=True, text=True, encoding="utf-8", timeout=120)
    lines = out.stdout.strip().splitlines()
    return json.loads(lines[-1]) if lines else {"error": out.stderr[-300:]}


def main(url):
    sys.stdout.reconfigure(encoding="utf-8")
    OUT.mkdir(parents=True, exist_ok=True)
    rows = ["| Req | Beat | Time on screen | Result | Capture |", "|---|---|---|---|---|"]
    ok_all = True
    for req, name, label, js in BEATS:
        r = run(url, name, js)
        ok = "error" not in r and r.get("t", 99999) < 20000
        ok_all &= ok
        t = r.pop("t", None)
        detail = "; ".join(f"{k}: {v}" for k, v in r.items())
        rows.append(f"| {req} | {label} | {'%.1f s' % (t / 1000) if t is not None else '-'} | {'pass' if ok else 'FAIL'}: {detail} | [{name}.png]({name}.png) |")
        print(rows[-1])
    (OUT / "results.md").write_text(f"# Acceptance pass on {url}\n\n" + "\n".join(rows) + "\n", encoding="utf-8")
    return 0 if ok_all else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))

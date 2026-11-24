// Dev tool: screenshot a page in headless Edge or Chrome at a fixed viewport, after running a script.
// node tools/screenshot.mjs <url> <out.png> [--w 1280] [--h 720] [--run "js"] [--runfile script.js] [--wait 800] [--full]
// Frame sequence and animated GIF (the script should start its page actions without awaiting them):
// node tools/screenshot.mjs <url> <out.gif> --frames 60 --every 150 [--zoom 1.25] [--crop x,y,w,h] [--gifw 720] [--fps 8] [--hold 2]
//   captures <frames> screenshots <every> ms apart, then builds a palette-optimised GIF with ffmpeg; the last frame is held <hold> s.
import { findBrowser, launch } from './headless.mjs';
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { spawnSync } from 'node:child_process';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

const args = process.argv.slice(2);
const [url, out] = args;
const opt = (name, dflt) => { const i = args.indexOf('--' + name); return i >= 0 ? args[i + 1] : dflt; };
const W = +opt('w', 1280), H = +opt('h', 720), WAIT = +opt('wait', 800);
const RUN = opt('runfile', '') ? readFileSync(opt('runfile'), 'utf8') : opt('run', '');
const FULL = args.includes('--full');
const FRAMES = +opt('frames', 0), EVERY = +opt('every', 150), ZOOM = opt('zoom', '');
const CROP = opt('crop', ''), GIFW = +opt('gifw', 720), FPS = +opt('fps', 8), HOLD = +opt('hold', 2);
if (!findBrowser()) throw new Error('no Edge or Chrome found');
// Downloads denied and profile removed afterwards: see tools/headless.mjs.
const browser = await launch('shot-', ['--hide-scrollbars', `--window-size=${W},${H}`], { timeoutMs: 100000 });
const { port } = browser;
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
try {
  let target;
  for (let i = 0; i < 60 && !target; i++) {
    try { target = (await (await fetch(`http://127.0.0.1:${port}/json/list`)).json()).find((t) => t.type === 'page'); } catch {}
    if (!target) await sleep(250);
  }
  const ws = new WebSocket(target.webSocketDebuggerUrl);
  await new Promise((r) => (ws.onopen = r));
  let id = 0; const waiting = new Map();
  ws.onmessage = (m) => { const d = JSON.parse(m.data); if (d.id && waiting.has(d.id)) waiting.get(d.id)(d); };
  const send = (method, params = {}) => new Promise((res) => { const i = ++id; waiting.set(i, res); ws.send(JSON.stringify({ id: i, method, params })); });
  await send('Emulation.setDeviceMetricsOverride', { width: W, height: H, deviceScaleFactor: +opt('dsf', 1), mobile: false });
  await send('Page.navigate', { url });
  await sleep(1200);
  if (ZOOM) await send('Runtime.evaluate', { expression: `document.documentElement.style.zoom='${ZOOM}'` });
  if (RUN) {
    const r = await send('Runtime.evaluate', { expression: RUN, awaitPromise: true, returnByValue: true });
    if (r.result?.exceptionDetails) console.error('script error:', JSON.stringify(r.result.exceptionDetails.exception?.description ?? r.result.exceptionDetails));
    else if (r.result?.result?.value !== undefined) console.log('script result:', JSON.stringify(r.result.result.value));
  }
  await sleep(WAIT);
  if (FRAMES) {
    const dir = mkdtempSync(join(tmpdir(), 'gif-'));
    try {
      const t0 = Date.now();
      for (let i = 0; i < FRAMES; i++) {
        const due = t0 + i * EVERY; const w = due - Date.now(); if (w > 0) await sleep(w);
        const r = await send('Page.captureScreenshot', { format: 'png' });
        writeFileSync(join(dir, `f${String(i).padStart(4, '0')}.png`), Buffer.from(r.result.data, 'base64'));
      }
      const rate = 1000 / EVERY;
      const [cx, cy, cw, ch] = CROP ? CROP.split(',') : []; const crop = CROP ? `crop=${cw}:${ch}:${cx}:${cy},` : '';
      const vf = `${crop}scale=${GIFW}:-1:flags=lanczos,fps=${FPS},tpad=stop_mode=clone:stop_duration=${HOLD},split[a][b];[a]palettegen=max_colors=128:stats_mode=diff[p];[b][p]paletteuse=dither=bayer:bayer_scale=4:diff_mode=rectangle`;
      const ff = spawnSync('ffmpeg', ['-v', 'error', '-y', '-framerate', String(rate), '-i', join(dir, 'f%04d.png'), '-vf', vf, '-loop', '0', out]);
      if (ff.status !== 0) throw new Error('ffmpeg: ' + ff.stderr.toString().slice(0, 400));
      console.log('wrote', out, FRAMES, 'frames');
    } finally { rmSync(dir, { recursive: true, force: true }); }
    ws.close();
  } else {
  const params = { format: 'png' };
  if (FULL) {
    const m = await send('Page.getLayoutMetrics');
    const c = m.result.cssContentSize;
    await send('Emulation.setDeviceMetricsOverride', { width: W, height: Math.ceil(c.height), deviceScaleFactor: 1, mobile: false });
    await sleep(200);
  }
  const shot = await send('Page.captureScreenshot', params);
  writeFileSync(out, Buffer.from(shot.result.data, 'base64'));
  console.log('wrote', out);
  ws.close();
  }
} finally { await browser.close(); }
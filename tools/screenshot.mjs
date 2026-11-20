// Dev tool: screenshot a page in headless Edge or Chrome at a fixed viewport, after running a script.
// node tools/screenshot.mjs <url> <out.png> [--w 1280] [--h 720] [--run "js"] [--runfile script.js] [--wait 800] [--full]
import { findBrowser, launch } from './headless.mjs';
import { readFileSync, writeFileSync } from 'node:fs';

const args = process.argv.slice(2);
const [url, out] = args;
const opt = (name, dflt) => { const i = args.indexOf('--' + name); return i >= 0 ? args[i + 1] : dflt; };
const W = +opt('w', 1280), H = +opt('h', 720), WAIT = +opt('wait', 800);
const RUN = opt('runfile', '') ? readFileSync(opt('runfile'), 'utf8') : opt('run', '');
const FULL = args.includes('--full');
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
  await send('Emulation.setDeviceMetricsOverride', { width: W, height: H, deviceScaleFactor: 1, mobile: false });
  await send('Page.navigate', { url });
  await sleep(1200);
  if (RUN) {
    const r = await send('Runtime.evaluate', { expression: RUN, awaitPromise: true, returnByValue: true });
    if (r.result?.exceptionDetails) console.error('script error:', JSON.stringify(r.result.exceptionDetails.exception?.description ?? r.result.exceptionDetails));
    else if (r.result?.result?.value !== undefined) console.log('script result:', JSON.stringify(r.result.result.value));
  }
  await sleep(WAIT);
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
} finally { await browser.close(); }
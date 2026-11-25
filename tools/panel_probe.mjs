// Test support: open the real page in headless Edge or Chrome, click a sample, open the Emitted spec view,
// read every tab's displayed text and capture the downloaded ZIP. Prints one JSON object on stdout.
// node tools/panel_probe.mjs <base-url> <sample-name>
import { findBrowser, launch } from './headless.mjs';

const [base, sample] = process.argv.slice(2);
if (!findBrowser()) { console.log(JSON.stringify({ error: 'no browser' })); process.exit(0); }
// Downloads denied and profile removed afterwards: see tools/headless.mjs.
const browser = await launch('probe-', [], { timeoutMs: 85000 });
const { port } = browser;
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// Runs in the page. Every wait polls for a condition, never a fixed delay.
const PAGE = `(async (sample) => {
  const until = async (fn, what) => { for (let i = 0; i < 800; i++) { const v = fn(); if (v) return v; await new Promise(r => setTimeout(r, 25)); } throw new Error('timed out waiting for ' + what); };
  const pick = await until(() => [...document.querySelectorAll('.pick')].find(b => b.textContent === sample), 'sample list');
  pick.click();
  const specTab = await until(() => [...document.querySelectorAll('.vtab')].find(b => b.textContent === 'Emitted spec'), 'result');
  specTab.click();
  const tabs = await until(() => { const t = [...document.querySelectorAll('.spec-tab')]; return t.length ? t : null; }, 'spec tabs');
  const files = {};
  for (const t of tabs) { t.click(); files[t.textContent] = document.querySelector('pre.spec-text').textContent; }
  const folder = document.querySelector('.spec-folder').textContent;
  let blob = null;
  const orig = URL.createObjectURL;
  URL.createObjectURL = (b) => { blob = b; return orig.call(URL, b); };
  document.querySelector('.spec-head button').click();
  await until(() => blob, 'zip download');
  const bytes = new Uint8Array(await blob.arrayBuffer());
  let bin = ''; for (let i = 0; i < bytes.length; i += 0x8000) bin += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
  return JSON.stringify({ folder, files, zip_b64: btoa(bin), zip_type: blob.type });
})`;

try {
  let target;
  for (let i = 0; i < 80 && !target; i++) {
    try { target = (await (await fetch(`http://127.0.0.1:${port}/json/list`)).json()).find((t) => t.type === 'page'); } catch {}
    if (!target) await sleep(250);
  }
  const ws = new WebSocket(target.webSocketDebuggerUrl);
  await new Promise((r) => (ws.onopen = r));
  let id = 0; const waiting = new Map(); const events = [];
  ws.onmessage = (m) => { const d = JSON.parse(m.data); if (d.id && waiting.has(d.id)) waiting.get(d.id)(d); else if (d.method) events.push(d.method); };
  const send = (method, params = {}) => new Promise((res) => { const i = ++id; waiting.set(i, res); ws.send(JSON.stringify({ id: i, method, params })); });
  await send('Page.enable');
  await send('Page.navigate', { url: base });
  for (let i = 0; i < 200 && !events.includes('Page.loadEventFired'); i++) await sleep(25);
  const r = await send('Runtime.evaluate', { expression: `${PAGE}(${JSON.stringify(sample)})`, awaitPromise: true, returnByValue: true });
  if (r.result.exceptionDetails) console.log(JSON.stringify({ error: r.result.exceptionDetails.exception?.description ?? 'page error' }));
  else console.log(r.result.result.value);
  ws.close();
} finally { await browser.close(); }
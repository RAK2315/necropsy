// Test support: run one scenario in a real headless Edge or Chrome page and print its JSON result.
// node tools/browser_run.mjs <url> <scenario.js> [--rewrite <rewrite.js>] [--prelude <prelude.js>] [--reduced-motion]
//   scenario.js  an async expression evaluated in the page after load; it must return a JSON string
//   rewrite.js   a JS function source `(payload) => payload`, applied in the browser to every /api/analyze response
//   prelude.js   extra JS run in the page before any page script (for example a window.fetch fault for one URL)
// Downloads made with URL.createObjectURL are captured: window.__blobs is an array of {name, type, b64}.
import { spawn } from 'node:child_process';
import { existsSync, mkdtempSync, readFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

const args = process.argv.slice(2);
const [url, scenarioPath] = args;
const opt = (k) => { const i = args.indexOf(k); return i >= 0 ? args[i + 1] : null; };
const rewritePath = opt('--rewrite');
const preludePath = opt('--prelude');
const reduced = args.includes('--reduced-motion');
const EXES = ['C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe', 'C:/Program Files/Google/Chrome/Application/chrome.exe',
  '/usr/bin/google-chrome', '/usr/bin/chromium', '/usr/bin/chromium-browser'];
const exe = EXES.find(existsSync);
if (!exe) { console.log(JSON.stringify({ error: 'no browser' })); process.exit(0); }

const port = 10100 + Math.floor(Math.random() * 400);
const proc = spawn(exe, ['--headless=new', `--remote-debugging-port=${port}`, `--user-data-dir=${mkdtempSync(join(tmpdir(), 'brun-'))}`,
  '--no-first-run', '--disable-gpu', '--window-size=1280,720', 'about:blank'], { stdio: 'ignore' });
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// Injected before any page script runs.
const PRELUDE = `
window.__until = async (fn, what) => { for (let i = 0; i < 800; i++) { let v; try { v = fn(); } catch (e) { v = null; } if (v) return v; await new Promise(r => setTimeout(r, 25)); } throw new Error('timed out: ' + what); };
window.__blobs = [];
(() => {
  const orig = URL.createObjectURL.bind(URL);
  URL.createObjectURL = (b) => {
    const rec = { name: null, type: b.type, b64: null };
    window.__blobs.push(rec);
    b.arrayBuffer().then((buf) => { const u = new Uint8Array(buf); let s = ''; for (let i = 0; i < u.length; i += 0x8000) s += String.fromCharCode(...u.subarray(i, i + 0x8000)); rec.b64 = btoa(s); });
    return orig(b);
  };
  const click = HTMLAnchorElement.prototype.click;
  HTMLAnchorElement.prototype.click = function () { const r = window.__blobs[window.__blobs.length - 1]; if (r && this.download) r.name = this.download; return click.call(this); };
})();
`;

try {
  let target;
  for (let i = 0; i < 80 && !target; i++) {
    try { target = (await (await fetch(`http://127.0.0.1:${port}/json/list`)).json()).find((t) => t.type === 'page'); } catch {}
    if (!target) await sleep(250);
  }
  const ws = new WebSocket(target.webSocketDebuggerUrl);
  await new Promise((r) => (ws.onopen = r));
  let id = 0; const waiting = new Map(); const events = [];
  const send = (method, params = {}) => new Promise((res) => { const i = ++id; waiting.set(i, res); ws.send(JSON.stringify({ id: i, method, params })); });
  const rewrite = rewritePath ? readFileSync(rewritePath, 'utf8') : null;
  ws.onmessage = async (m) => {
    const d = JSON.parse(m.data);
    if (d.id && waiting.has(d.id)) { waiting.get(d.id)(d); return; }
    if (d.method === 'Fetch.requestPaused') {
      const p = d.params;
      const body = await send('Fetch.getResponseBody', { requestId: p.requestId });
      const text = body.result.base64Encoded ? Buffer.from(body.result.body, 'base64').toString('utf8') : body.result.body;
      let out = text;
      try { out = JSON.stringify((0, eval)(`(${rewrite})`)(JSON.parse(text))); } catch (e) { out = text; }
      await send('Fetch.fulfillRequest', { requestId: p.requestId, responseCode: p.responseStatusCode,
        responseHeaders: [{ name: 'Content-Type', value: 'application/json' }], body: Buffer.from(out, 'utf8').toString('base64') });
      return;
    }
    if (d.method) events.push(d.method);
  };
  await send('Page.enable');
  await send('Emulation.setDeviceMetricsOverride', { width: 1280, height: 720, deviceScaleFactor: 1, mobile: false });
  if (reduced) await send('Emulation.setEmulatedMedia', { features: [{ name: 'prefers-reduced-motion', value: 'reduce' }] });
  if (rewrite) await send('Fetch.enable', { patterns: [{ urlPattern: '*/api/analyze', requestStage: 'Response' }] });
  await send('Page.addScriptToEvaluateOnNewDocument', { source: PRELUDE + (preludePath ? readFileSync(preludePath, 'utf8') : '') });
  await send('Page.navigate', { url });
  for (let i = 0; i < 400 && !events.includes('Page.loadEventFired'); i++) await sleep(25);
  const r = await send('Runtime.evaluate', { expression: readFileSync(scenarioPath, 'utf8'), awaitPromise: true, returnByValue: true });
  if (r.result.exceptionDetails) console.log(JSON.stringify({ error: r.result.exceptionDetails.exception?.description ?? 'page error' }));
  else console.log(r.result.result.value);
  ws.close();
} catch (e) {
  console.log(JSON.stringify({ error: String((e && e.message) || e) }));
} finally { proc.kill(); }

// Test support: drive the real page in headless Edge or Chrome through every screen and report, as JSON,
//   accent:   every element whose computed colour, background, border or outline is the accent colour, per screen
//   requests: every URL the page requested
import { findBrowser, launch } from './headless.mjs';
//   reduced:  what the RESOLVED screen looks like on first paint when the browser prefers reduced motion
// node tools/visual_probe.mjs <base-url>

const [base] = process.argv.slice(2);
if (!findBrowser()) { console.log(JSON.stringify({ error: 'no browser' })); process.exit(0); }
// Downloads denied and profile removed afterwards: see tools/headless.mjs.
const browser = await launch('vprobe-', ['--window-size=1280,720'], { timeoutMs: 170000 });
const { port } = browser;
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// In-page helpers, injected before each scenario.
const HELPERS = `
window.__until = async (fn, what) => { for (let i = 0; i < 600; i++) { const v = fn(); if (v) return v; await new Promise(r => setTimeout(r, 25)); } throw new Error('timed out: ' + what); };
window.__accentUsers = () => {
  const probe = document.createElement('span'); probe.style.color = getComputedStyle(document.documentElement).getPropertyValue('--accent').trim();
  document.body.append(probe); const accent = getComputedStyle(probe).color; probe.remove();
  const out = [];
  for (const e of document.querySelectorAll('body *')) {
    const s = getComputedStyle(e);
    if (s.visibility === 'hidden' || s.display === 'none' || !e.getClientRects().length) continue;
    const props = { color: s.color, background: s.backgroundColor, outline: s.outlineStyle !== 'none' ? s.outlineColor : '',
      'border-top': s.borderTopStyle !== 'none' ? s.borderTopColor : '', 'border-left': s.borderLeftStyle !== 'none' ? s.borderLeftColor : '' };
    const hits = Object.entries(props).filter(([, v]) => v === accent).map(([k]) => k);
    if (hits.length && (e.childElementCount === 0 || hits.some(h => h !== 'color'))) out.push({ tag: e.tagName.toLowerCase(), cls: e.className && e.className.baseVal === undefined ? e.className : '', props: hits });
  }
  return out;
};
window.__pick = async (name) => { const b = await __until(() => [...document.querySelectorAll('.pick')].find(x => x.textContent === name), 'sample ' + name); b.click(); };
window.__skip = async () => { const b = await __until(() => document.querySelector('.rp-bar button[title="Skip to the end"]'), 'replay'); if (!b.disabled) b.click(); await __until(() => !document.querySelector('.exam-right.pending, .verdict-bar.pending'), 'outcome'); };
window.__home = async () => { document.getElementById('again').click(); await __until(() => document.querySelector('.pick'), 'start'); };
`;

const SCENARIO = `(async () => {
  const shots = {};
  await __until(() => document.querySelector('.pick'), 'start');
  shots.start = __accentUsers();
  await __pick('mystery_i'); await __skip(); shots.resolved = __accentUsers();
  [...document.querySelectorAll('.vtab')].find(b => b.textContent === 'Emitted spec').click(); shots.spec = __accentUsers();
  await __home(); await __pick('mystery_c'); await __skip(); shots.resolved_tga = __accentUsers();
  await __home(); await __pick('mystery_d'); await __skip(); shots.ambiguity = __accentUsers();
  document.querySelector('.card').click(); shots.ambiguity_selected = __accentUsers();
  await __home();
  const dt = new DataTransfer(); dt.items.add(new File([new TextEncoder().encode('plain text, not an image. '.repeat(30))], 'notes.txt'));
  document.querySelector('.drop').dispatchEvent(new DragEvent('drop', { dataTransfer: dt, bubbles: true, cancelable: true }));
  await __skip(); shots.failed = __accentUsers();
  return JSON.stringify(shots);
})()`;

const REDUCED = `(async () => {
  await __pick('mystery_i');
  // Wait only for the result to exist, then read everything at once: first paint, no further waiting.
  // (Waiting for the image here would let a normal replay run to its end and pass by accident.)
  const counter = await __until(() => { const e = document.querySelector('.rp-counter'); return e && e.textContent ? e.textContent : null; }, 'counter');
  const outcome = getComputedStyle(document.querySelector('.exam-right')).visibility;
  const canvas = document.querySelector('.exam-right canvas.pixels');
  const px = canvas ? canvas.getContext('2d').getImageData(1, canvas.height - 2, 1, 1).data : [0, 0, 0, 0];   // bottom row: drawn only when the reveal is complete
  return JSON.stringify({ counter, outcome, bottomRowAlpha: px[3] });
})()`;

try {
  let target;
  for (let i = 0; i < 80 && !target; i++) {
    try { target = (await (await fetch(`http://127.0.0.1:${port}/json/list`)).json()).find((t) => t.type === 'page'); } catch {}
    if (!target) await sleep(250);
  }
  const ws = new WebSocket(target.webSocketDebuggerUrl);
  await new Promise((r) => (ws.onopen = r));
  let id = 0; const waiting = new Map(); const events = []; const requests = [];
  ws.onmessage = (m) => {
    const d = JSON.parse(m.data);
    if (d.id && waiting.has(d.id)) waiting.get(d.id)(d);
    else if (d.method === 'Network.requestWillBeSent') requests.push(d.params.request.url);
    else if (d.method) events.push(d.method);
  };
  const send = (method, params = {}) => new Promise((res) => { const i = ++id; waiting.set(i, res); ws.send(JSON.stringify({ id: i, method, params })); });
  const load = async () => {
    events.length = 0;
    await send('Page.navigate', { url: base });
    for (let i = 0; i < 400 && !events.includes('Page.loadEventFired'); i++) await sleep(25);
    await send('Runtime.evaluate', { expression: HELPERS });
  };
  const run = async (expr) => {
    const r = await send('Runtime.evaluate', { expression: expr, awaitPromise: true, returnByValue: true });
    if (r.result.exceptionDetails) throw new Error(r.result.exceptionDetails.exception?.description ?? 'page error');
    return JSON.parse(r.result.result.value);
  };
  await send('Page.enable'); await send('Network.enable');
  await send('Emulation.setDeviceMetricsOverride', { width: 1280, height: 720, deviceScaleFactor: 1, mobile: false });
  await load();
  const accent = await run(SCENARIO);
  await send('Emulation.setEmulatedMedia', { features: [{ name: 'prefers-reduced-motion', value: 'reduce' }] });
  await load();
  const reduced = await run(REDUCED);
  console.log(JSON.stringify({ accent, requests, reduced }));
  ws.close();
} catch (e) {
  console.log(JSON.stringify({ error: String(e && e.message || e) }));
} finally { await browser.close(); }
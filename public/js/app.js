import { renderResult, leaveResult } from './screens.js';
import { stripElement } from './strip.js';
import { playSteps } from './live.js';
import { stateText } from './words.js';
import {
  multiDropNotice, sizeMessage, emptyMessage, unreadableMessage, othersNotExamined, serviceStatusMessage, UNREACHABLE_MESSAGE,
  sampleFailMessage, SAMPLE_LIST_FAIL, LIMIT_BYTES,
} from './logic.js';

const MAX_UPLOAD = LIMIT_BYTES;
const view = document.getElementById('view');
const againBtn = document.getElementById('again');
const stateLine = document.getElementById('state');

/** The state line under the header (UI task 25). */
function setState(s) { stateLine.textContent = stateText(s); stateLine.dataset.phase = s.phase; }

function el(tag, attrs = {}, ...kids) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === 'class') e.className = v; else if (k === 'text') e.textContent = v; else e.setAttribute(k, v);
  }
  e.append(...kids);
  return e;
}

const fmt = (n) => n.toLocaleString('en-US');

/** POST bytes to the engine. Resolves to { payload } or { error: true, status, message }. Never rejects. */
async function requestAnalysis(bytes) {
  try {
    const r = await fetch('/api/analyze', { method: 'POST', body: bytes, headers: { 'Content-Type': 'application/octet-stream' } });
    if (r.status === 413) return { error: true, status: 413, message: sizeMessage(bytes.length) };
    if (!r.ok) return { error: true, status: r.status, message: serviceStatusMessage(r.status) };
    return { payload: await r.json() };
  } catch (e) {
    return { error: true, status: 0, message: UNREACHABLE_MESSAGE };
  }
}

function open(payload, bytes, name, notice = null) {
  againBtn.hidden = false;
  const base = { name, size: bytes.length, payload };
  renderResult(view, payload, bytes, { name, notice,
    onProgress: ({ step, of, final }) => setState(final ? { ...base, phase: 'done' } : { ...base, phase: 'replaying', step, of }) });
}

const PRIMARY = 'pillow_odd_stride.pcx';     // the primary action's sample: a real file from Pillow's test suite

/** Fetch a served sample and examine it exactly as a dropped file: the same busy screen, bytes in, analyse(bytes). */
async function runSample(name) {
  const t0 = performance.now();
  examining(name);
  let r;
  try { r = await fetch('/samples/' + name); } catch (e) { showStart(sampleFailMessage(name, 0), name); return; }
  if (!r.ok) { showStart(sampleFailMessage(name, r.status), name); return; }   // never analyse an error page
  analyse(new Uint8Array(await r.arrayBuffer()), name, null, t0);
}

async function showStart(message = '', name = '') {
  leaveResult();               // Escape and 'Examine another file' both come here: stop the replay
  againBtn.hidden = true;
  setState(message ? { phase: 'error', name, reason: message } : { phase: 'idle' });
  const input = el('input', { type: 'file', hidden: '' });
  const primary = el('button', { class: 'primary', type: 'button', 'data-cap': 'primary', text: 'See it recover a real file' });
  primary.addEventListener('click', () => runSample(PRIMARY));
  const hero = el('section', { class: 'hero', 'data-cap': 'hero' },
    el('h1', { text: 'Get the picture back from an image file nothing can open.' }),
    el('p', { class: 'hero-who', text: 'For archivists, investigators, and anyone holding an image in a format nothing reads any more.' }),
    el('p', { class: 'hero-what', text: 'NECROPSY reads what the file says about itself, accepts a layout only if it fits the data exactly, and otherwise tells you why.' }),
    el('div', { class: 'hero-act' }, primary,
      el('span', { class: 'primary-note', text: `${PRIMARY} · from Pillow’s test suite` })));
  const drop = el('button', { class: 'drop', type: 'button', 'data-cap': 'drop', text: 'Or drop your own file here, or click to choose one.' });
  const msg = el('p', { class: 'drop-msg' + (message ? ' bad' : ''), role: 'status', 'aria-live': 'polite', text: message });
  const how = el('section', { class: 'how', 'data-cap': 'how' }, el('h2', { text: 'How it works' }),
    el('ol', {},
      el('li', { text: 'It reads what the file declares about itself: size, depth, compression, where the data starts.' }),
      el('li', { text: 'It tries the layouts those declarations allow, and small corrections to them.' }),
      el('li', { text: 'It accepts a layout only if it fits the data exactly. If none or several do, it says so.' })));
  const samples = el('section', { class: 'samples' }, el('h2', { text: 'More files to try' }));
  const start = el('div', { class: 'start' }, hero, drop, input, msg, stripElement(requestAnalysis, present), how,
    el('p', { class: 'scope', text: 'NECROPSY reads PCX, TGA, PBM and TIFF declarations, and otherwise searches for headerless raster layouts.' }),
    samples);
  view.replaceChildren(start);

  const refuse = (text, name = '') => { msg.textContent = text; msg.classList.add('bad'); setState({ phase: 'error', name, reason: text }); };
  const take = (files) => {
    const list = [...(files || [])];
    if (!list.length) { refuse('Nothing to examine: drop a file.'); return; }
    const file = list[0];
    const notice = multiDropNotice(list.map((f) => f.name));
    if (file.size === 0) { refuse(emptyMessage(file.name) + othersNotExamined(list.length), file.name); return; }
    if (file.size > MAX_UPLOAD) { refuse(sizeMessage(file.size) + othersNotExamined(list.length), file.name); return; }
    file.arrayBuffer()
      .then((buf) => analyse(new Uint8Array(buf), file.name, notice))
      .catch(() => refuse(unreadableMessage(file.name) + othersNotExamined(list.length), file.name));   // e.g. a dropped folder
  };
  drop.addEventListener('click', () => input.click());
  input.addEventListener('change', () => take(input.files));
  for (const ev of ['dragenter', 'dragover']) drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.add('over'); });
  for (const ev of ['dragleave', 'drop']) drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.remove('over'); });
  drop.addEventListener('drop', (e) => { e.stopPropagation(); take(e.dataTransfer.files); });
  // a file dropped anywhere on the start screen still counts
  window.ondragover = (e) => e.preventDefault();
  window.ondrop = (e) => { e.preventDefault(); if (document.querySelector('.drop')) take(e.dataTransfer.files); };

  try {
    const r = await fetch('/samples/index.json');
    if (!r.ok) throw new Error(String(r.status));
    const index = await r.json();
    const list = el('ul');
    for (const s of index) {
      const pick = el('button', { class: 'pick', type: 'button', 'data-cap': 'sample', 'data-name': s.name, text: s.name });
      // a sample takes exactly the path a dropped file takes: bytes in, analyse(bytes)
      pick.addEventListener('click', () => runSample(s.name));
      const li = el('li', {}, pick, el('span', { class: 'size', text: `${fmt(s.size)} bytes` }),
        el('a', { class: 'dl', href: '/samples/' + s.name, download: s.name, text: 'download' }));
      const link = li.querySelector('a.dl');
      link.addEventListener('keydown', (e) => { if (e.key === ' ') { e.preventDefault(); link.click(); } });
      if (s.description) li.append(el('span', { class: 'desc', text: s.description }));
      if (s.provenance) {
        const prov = el('span', { class: 'prov', text: s.provenance });
        if (s.licence) prov.append(' · ', el('a', { class: 'lic', href: '/samples/' + s.licence, text: 'licence notice' }));
        li.append(prov);
      }
      list.append(li);
    }
    samples.append(list);
  } catch (e) {
    samples.append(el('p', { class: 'drop-msg bad', role: 'status', text: SAMPLE_LIST_FAIL }));
  }
}

// The busy screen stays up at least this long, so a fast answer still reads as "your file was examined" (second
// clarity pass, change 4). The state line and the replay header give the engine's real time.
const MIN_BUSY_MS = 700;

/** The busy screen, the same for a dropped file and a sample: the file's name and an activity indicator. */
function examining(name, size) {
  againBtn.hidden = true;
  const busy = document.querySelector('#view > .busy');
  if (!busy) {
    view.replaceChildren(el('div', { class: 'busy', role: 'status', 'data-cap': 'busy' },
      el('p', { class: 'busy-text', text: `Examining ${name}…` }), el('progress', { class: 'busy-bar', 'aria-label': `Examining ${name}` })));
  }
  setState({ phase: 'sending', name, size });
}

async function analyse(bytes, name, notice = null, t0 = performance.now()) {
  examining(name, bytes.length);
  const [result] = await Promise.all([requestAnalysis(bytes), new Promise((r) => setTimeout(r, MIN_BUSY_MS - (performance.now() - t0)))]);
  if (!document.querySelector('#view > .busy')) return;    // the busy screen was replaced before the answer came
  if (result.error) { showStart(result.message, name); return; }
  present(result.payload, bytes, name, notice);
}

/** The engine's steps one by one on the examining screen (UI task 39), then the result. Strip tiles come here too. */
async function present(payload, bytes, name, notice = null) {
  examining(name, bytes.length);
  const busy = document.querySelector('#view > .busy');
  const base = { name, size: bytes.length, payload };
  await playSteps(busy, payload, { alive: () => busy.isConnected,
    onStep: ({ step, of }) => setState({ ...base, phase: 'replaying', step, of }) });
  if (!busy.isConnected) return;     // left before the steps finished
  open(payload, bytes, name, notice);
}

againBtn.addEventListener('click', () => showStart());
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape' && !againBtn.hidden) { e.preventDefault(); showStart(); }
});
showStart();
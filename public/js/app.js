import { renderResult } from './screens.js';
import { stripElement } from './strip.js';
import {
  multiDropNotice, sizeMessage, emptyMessage, othersNotExamined, serviceStatusMessage, UNREACHABLE_MESSAGE,
  sampleFailMessage, SAMPLE_LIST_FAIL, LIMIT_BYTES,
} from './logic.js';

const MAX_UPLOAD = LIMIT_BYTES;
const view = document.getElementById('view');
const againBtn = document.getElementById('again');

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
  renderResult(view, payload, bytes, { name, notice });
}

async function showStart(message = '') {
  againBtn.hidden = true;
  const input = el('input', { type: 'file', hidden: '' });
  const drop = el('button', { class: 'drop', type: 'button', text: 'Drop in a file nothing can open.' });
  const msg = el('p', { class: 'drop-msg' + (message ? ' bad' : ''), role: 'status', 'aria-live': 'polite', text: message });
  const samples = el('section', { class: 'samples' }, el('h2', { text: 'No file to hand? Try one of these.' }));
  const start = el('div', { class: 'start' }, stripElement(requestAnalysis, open), drop, input, msg,
    el('p', { class: 'scope', text: 'NECROPSY reads PCX, TGA, PBM and TIFF declarations, and otherwise searches for headerless raster layouts.' }),
    samples);
  view.replaceChildren(start);

  const refuse = (text) => { msg.textContent = text; msg.classList.add('bad'); };
  const take = (files) => {
    const list = [...(files || [])];
    if (!list.length) { refuse('Nothing to examine: drop a file.'); return; }
    const file = list[0];
    const notice = multiDropNotice(list.map((f) => f.name));
    if (file.size === 0) { refuse(emptyMessage(file.name) + othersNotExamined(list.length)); return; }
    if (file.size > MAX_UPLOAD) { refuse(sizeMessage(file.size) + othersNotExamined(list.length)); return; }
    file.arrayBuffer().then((buf) => analyse(new Uint8Array(buf), file.name, notice));
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
      const pick = el('button', { class: 'pick', type: 'button', text: s.name });
      // a sample takes exactly the path a dropped file takes: bytes in, analyse(bytes)
      pick.addEventListener('click', async () => {
        let r;
        try { r = await fetch('/samples/' + s.name); } catch (e) { showStart(sampleFailMessage(s.name, 0)); return; }
        if (!r.ok) { showStart(sampleFailMessage(s.name, r.status)); return; }   // never analyse an error page
        analyse(new Uint8Array(await r.arrayBuffer()), s.name);
      });
      const li = el('li', {}, pick, el('span', { class: 'size', text: `${fmt(s.size)} bytes` }),
        el('a', { class: 'dl', href: '/samples/' + s.name, download: s.name, text: 'download' }));
      if (s.provenance) li.append(el('span', { class: 'prov', text: s.provenance }));
      list.append(li);
    }
    samples.append(list);
  } catch (e) {
    samples.append(el('p', { class: 'drop-msg bad', role: 'status', text: SAMPLE_LIST_FAIL }));
  }
}

async function analyse(bytes, name, notice = null) {
  againBtn.hidden = true;
  view.replaceChildren(el('p', { class: 'busy', role: 'status', text: 'Analysing…' }));
  const result = await requestAnalysis(bytes);
  if (result.error) { showStart(result.message); return; }
  open(result.payload, bytes, name, notice);
}

againBtn.addEventListener('click', () => showStart());
showStart();
import { renderResult } from './screens.js';

const MAX_UPLOAD = 65536;
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

async function showStart(message = '') {
  againBtn.hidden = true;
  const input = el('input', { type: 'file', hidden: '' });
  const drop = el('button', { class: 'drop', type: 'button', text: 'Drop in a file nothing can open.' });
  const msg = el('p', { class: 'drop-msg', role: 'status', 'aria-live': 'polite', text: message });
  const samples = el('section', { class: 'samples' }, el('h2', { text: 'No file to hand? Try one of these.' }));
  const start = el('div', { class: 'start' }, drop, input, msg,
    el('p', { class: 'scope', text: 'NECROPSY reads PCX, TGA, PBM and TIFF declarations, and otherwise searches for headerless raster layouts.' }),
    samples);
  view.replaceChildren(start);

  const refuse = (text) => { msg.textContent = text; msg.classList.add('bad'); };
  const take = (file) => {
    if (!file) return;
    if (file.size > MAX_UPLOAD) {
      refuse(`That file is ${fmt(file.size)} bytes. The limit is ${fmt(MAX_UPLOAD)} bytes.`);
      return;
    }
    file.arrayBuffer().then((buf) => analyse(new Uint8Array(buf)));
  };
  drop.addEventListener('click', () => input.click());
  input.addEventListener('change', () => take(input.files[0]));
  for (const ev of ['dragenter', 'dragover']) drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.add('over'); });
  for (const ev of ['dragleave', 'drop']) drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.remove('over'); });
  drop.addEventListener('drop', (e) => take(e.dataTransfer.files[0]));
  // a file dropped anywhere on the page still counts
  window.ondragover = (e) => e.preventDefault();
  window.ondrop = (e) => { e.preventDefault(); take(e.dataTransfer.files[0]); };

  try {
    const index = await (await fetch('/samples/index.json')).json();
    const list = el('ul');
    for (const s of index) {
      const pick = el('button', { class: 'pick', type: 'button', text: s.name });
      // a sample takes exactly the path a dropped file takes: bytes in, analyse(bytes)
      pick.addEventListener('click', async () => {
        const r = await fetch('/samples/' + s.name);
        analyse(new Uint8Array(await r.arrayBuffer()));
      });
      const li = el('li', {}, pick, el('span', { class: 'size', text: `${fmt(s.size)} bytes` }),
        el('a', { class: 'dl', href: '/samples/' + s.name, download: s.name, text: 'download' }));
      if (s.provenance) li.append(el('span', { class: 'prov', text: s.provenance }));
      list.append(li);
    }
    samples.append(list);
  } catch (e) {
    samples.hidden = true;
  }
}

async function analyse(bytes) {
  againBtn.hidden = true;
  view.replaceChildren(el('p', { class: 'busy', role: 'status', text: 'Analysing…' }));
  let payload;
  try {
    const r = await fetch('/api/analyze', { method: 'POST', body: bytes, headers: { 'Content-Type': 'application/octet-stream' } });
    if (r.status === 413) { showStart(`That file is larger than the ${fmt(MAX_UPLOAD)} byte limit.`); return; }
    if (!r.ok) { showStart('The analysis service did not answer. Try again.'); return; }
    payload = await r.json();
  } catch (e) {
    showStart('The analysis service could not be reached. Try again.');
    return;
  }
  againBtn.hidden = false;
  console.log('NECROPSY status:', payload.status);
  renderResult(view, payload, bytes);
}

againBtn.addEventListener('click', () => showStart());
showStart();
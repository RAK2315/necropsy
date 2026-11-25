// Outcome strip on the first screen (Requirement 16): three real results, requested as the page loads.
import { outcomeLine, failureSentence, rejectionLine, sampleFailMessage } from './logic.js';
import { CHIP, sourceText, rejectionPlain } from './words.js';
import { paint } from './image.js';

function el(tag, cls, text) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text !== undefined) e.textContent = text;
  return e;
}

// What each tile examines. Bytes come from the served samples, so the tile shows what any visitor would get.
const INPUTS = [
  // a real photograph since UI task 38 (Rehaan): the corpus's 8 × 8 mystery_i read as a test pattern, not a picture
  { label: 'imagemagick_input.tga', name: 'imagemagick_input.tga', bytes: async () => fetchSample('imagemagick_input.tga') },
  { label: 'mystery_d', name: 'mystery_d', bytes: async () => fetchSample('mystery_d') },
  { label: 'mystery_b, first 300 bytes', name: 'mystery_b_first300', bytes: async () => (await fetchSample('mystery_b')).slice(0, 300) },
];

class SampleError extends Error { constructor(name, status) { super(sampleFailMessage(name, status)); } }

async function fetchSample(name) {
  let r;
  try { r = await fetch('/samples/' + name); } catch (e) { throw new SampleError(name, 0); }
  if (!r.ok) throw new SampleError(name, r.status);
  return new Uint8Array(await r.arrayBuffer());
}

let loaded = null;    // one set of requests per page load

/** Start the three analyses once. Each entry resolves to { input, bytes, result } where result is from requestAnalysis. */
export function loadStrip(requestAnalysis) {
  if (!loaded) {
    loaded = INPUTS.map(async (input) => {
      try {
        const bytes = await input.bytes();
        return { input, bytes, result: await requestAnalysis(bytes) };
      } catch (e) {
        return { input, bytes: null, result: { error: true, message: e instanceof SampleError ? e.message : sampleFailMessage(input.name, 0) } };
      }
    });
  }
  return loaded;
}

function resolvedBody(p) {
  const c = p.candidates[0];
  const well = el('div', 'well strip-well');
  if (c.render && c.render.data_b64) well.append(paint(c.render, 196, 120, { bitDepth: c.bit_depth }).canvas);
  return [well, el('p', 'strip-dims', `${c.width} × ${c.height}, ${c.bit_depth}-bit. ${sourceText(c.probe_name)}`)];
}

function ambiguityBody(p) {
  const grid = el('div', 'strip-thumbs');
  for (const c of p.candidates) {
    const box = el('div', 'strip-thumb');
    if (c.render && c.render.data_b64) box.append(paint(c.render, 28, 28, { bitDepth: c.bit_depth }).canvas);
    else box.title = c.render ? c.render.failure : 'no image';
    grid.append(box);
  }
  return [grid];
}

function failedBody(p) {
  const out = [el('p', 'strip-term', failureSentence(p))];
  const list = el('ol', 'strip-rej');
  for (const r of p.rejections.slice(0, 3)) {
    const li = el('li', '', rejectionPlain(r));
    li.append(el('span', 'tech', rejectionLine(r)));
    list.append(li);
  }
  out.push(list);
  const more = p.rejections.length + (p.rejections_omitted || 0) - Math.min(3, p.rejections.length);
  if (more > 0) out.push(el('p', 'strip-more', `and ${more} more`));
  return out;
}

/** The strip element. open(payload, bytes, name) is called when a finished tile is chosen. */
export function stripElement(requestAnalysis, open) {
  const root = el('section', 'strip');
  root.setAttribute('aria-label', 'Three real results');
  root.append(el('h2', 'strip-title', 'Three honest answers'),
    el('p', 'strip-head', 'Three real files, examined live as this page loaded. Open any of them to see the working.'));
  const row = el('div', 'strip-row');
  root.append(row);
  loadStrip(requestAnalysis).forEach((pending, i) => {
    const tile = el('article', 'strip-tile');
    tile.dataset.slot = String(i);
    tile.dataset.cap = 'tile-' + i;
    const name = el('p', 'strip-input mono', INPUTS[i].label);
    const body = el('div', 'strip-body');
    body.setAttribute('aria-live', 'polite');
    body.append(el('p', 'strip-wait', 'Analysing…'));
    tile.append(name, body);
    row.append(tile);
    pending.then(({ input, bytes, result }) => {
      if (result.error) { body.replaceChildren(el('p', 'strip-wait strip-error', result.message)); return; }
      const p = result.payload;
      const kids = p.status === 'RESOLVED' ? resolvedBody(p) : p.status === 'UNRESOLVED_AMBIGUITY' ? ambiguityBody(p) : failedBody(p);
      body.replaceChildren(...kids);
      tile.append(el('p', 'strip-line', outcomeLine(p)), el('span', 'strip-open', 'Open →'));
      const chip = el('span', 'chip ' + (p.status === 'FAILED' ? 'chip-failed' : 'chip-ok'), CHIP[p.status] + ' ');
      chip.append(el('span', 'tech', p.status));
      tile.prepend(chip);
      tile.dataset.status = p.status;
      tile.tabIndex = 0;
      tile.setAttribute('role', 'button');
      tile.setAttribute('aria-label', `Open the result for ${input.label}: ${CHIP[p.status]}`);
      const go = () => open(p, bytes, input.name);
      tile.addEventListener('click', go);
      tile.addEventListener('keydown', (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); go(); } });
    });
  });
  return root;
}
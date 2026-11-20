// Outcome strip on the first screen (Requirement 16): three real results, requested as the page loads.
import { outcomeLine, terminationText, rejectionLine } from './logic.js';
import { paint } from './image.js';

function el(tag, cls, text) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text !== undefined) e.textContent = text;
  return e;
}

// What each tile examines. Bytes come from the served samples, so the tile shows what any visitor would get.
const INPUTS = [
  { label: 'external_a', name: 'external_a', bytes: async () => fetchSample('external_a') },
  { label: 'mystery_d', name: 'mystery_d', bytes: async () => fetchSample('mystery_d') },
  { label: 'mystery_b, first 300 bytes', name: 'mystery_b_first300', bytes: async () => (await fetchSample('mystery_b')).slice(0, 300) },
];

async function fetchSample(name) {
  const r = await fetch('/samples/' + name);
  if (!r.ok) throw new Error('sample ' + name);
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
        return { input, bytes: null, result: { error: true, message: 'The sample could not be loaded.' } };
      }
    });
  }
  return loaded;
}

function resolvedBody(p) {
  const c = p.candidates[0];
  const well = el('div', 'well strip-well');
  if (c.render && c.render.data_b64) well.append(paint(c.render, 196, 120).canvas);
  return [well, el('p', 'strip-dims mono', `${c.width} × ${c.height} · ${c.bit_depth}-bit · ${c.probe_name.toUpperCase()} probe`)];
}

function ambiguityBody(p) {
  const grid = el('div', 'strip-thumbs');
  for (const c of p.candidates) {
    const box = el('div', 'strip-thumb');
    if (c.render && c.render.data_b64) box.append(paint(c.render, 28, 28).canvas);
    else box.title = c.render ? c.render.failure : 'no image';
    grid.append(box);
  }
  return [grid];
}

function failedBody(p) {
  const out = [el('p', 'strip-term', terminationText(p.termination))];
  const list = el('ol', 'strip-rej mono');
  for (const r of p.rejections.slice(0, 3)) list.append(el('li', '', rejectionLine(r)));
  out.push(list);
  const more = p.rejections.length + (p.rejections_omitted || 0) - Math.min(3, p.rejections.length);
  if (more > 0) out.push(el('p', 'strip-more', `and ${more} more`));
  return out;
}

/** The strip element. open(payload, bytes, name) is called when a finished tile is chosen. */
export function stripElement(requestAnalysis, open) {
  const root = el('section', 'strip');
  root.setAttribute('aria-label', 'Three real results');
  root.append(el('p', 'strip-head', 'Three real results, analysed as this page loaded.'));
  const row = el('div', 'strip-row');
  root.append(row);
  loadStrip(requestAnalysis).forEach((pending, i) => {
    const tile = el('article', 'strip-tile');
    tile.dataset.slot = String(i);
    const name = el('p', 'strip-input mono', INPUTS[i].label);
    const body = el('div', 'strip-body');
    body.append(el('p', 'strip-wait', 'Analysing…'));
    tile.append(name, body);
    row.append(tile);
    pending.then(({ input, bytes, result }) => {
      if (result.error) { body.replaceChildren(el('p', 'strip-wait', result.message)); return; }
      const p = result.payload;
      const kids = p.status === 'RESOLVED' ? resolvedBody(p) : p.status === 'UNRESOLVED_AMBIGUITY' ? ambiguityBody(p) : failedBody(p);
      body.replaceChildren(...kids);
      tile.append(el('p', 'strip-line', outcomeLine(p)));
      tile.prepend(el('span', 'chip ' + (p.status === 'FAILED' ? 'chip-failed' : 'chip-ok'), p.status));
      tile.dataset.status = p.status;
      tile.tabIndex = 0;
      tile.setAttribute('role', 'button');
      tile.setAttribute('aria-label', `Open the ${p.status} result for ${input.label}`);
      const go = () => open(p, bytes, input.name);
      tile.addEventListener('click', go);
      tile.addEventListener('keydown', (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); go(); } });
    });
  });
  return root;
}
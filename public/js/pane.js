// Hex pane and field table. Static: draws one view of the file. The replay reuses show() with other views.
import { byteRoles, hex4, regions, valueText, equivalentNames } from './logic.js';
import { fieldPlain } from './words.js';

const ROW = 20;              // px per row; must match .hex-row in app.css
const MARGIN = 12;           // extra rows rendered above and below the visible ones
const HEX = Array.from({ length: 256 }, (_, i) => i.toString(16).toUpperCase().padStart(2, '0'));

function el(tag, cls, text) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text !== undefined) e.textContent = text;
  return e;
}

/**
 * createPane(bytes) -> { root, show(view), highlight(id|null), scrollTo(offset), onHover(fn) }
 * view = { cands: [candidate...], labels: (cand index) => text, regions: candidate|null, lit: Set<id>|null }
 *   cands      candidates whose field reads are drawn (one for a result, all of them for the ambiguity union)
 *   regions    the candidate whose header, data region and trailer are marked, or null to mark none
 *   lit        record ids drawn in the accent colour; null means all of them
 */
export function createPane(bytes) {
  const n = bytes.length;
  const rows = Math.max(1, Math.ceil(n / 16));
  const root = el('section', 'pane');
  root.setAttribute('aria-label', 'File bytes');
  const head = el('div', 'hex-head mono');
  head.append(el('span', 'gut', ''), el('span', 'off', 'offset'),
    el('span', 'hx', Array.from({ length: 16 }, (_, i) => i.toString(16).toUpperCase().padStart(2, '0')).join(' ')), el('span', 'asc', 'ascii'));
  const scroller = el('div', 'hex-scroll mono');
  scroller.tabIndex = 0;
  scroller.setAttribute('role', 'region');
  scroller.setAttribute('aria-label', `Hex view, ${n} bytes, ${rows} rows. Arrow and page keys scroll.`);
  const sizer = el('div', 'hex-sizer');
  sizer.style.height = rows * ROW + 'px';
  const layer = el('div', 'hex-layer');
  sizer.append(layer);
  scroller.append(sizer);
  const tip = el('div', 'hex-tip mono');
  tip.hidden = true;
  tip.setAttribute('role', 'tooltip');
  root.append(head, scroller, tip);

  let state = { records: [], byByte: new Map(), reg: null, lit: null, labels: () => '', cands: [] };
  let hi = null;
  let hoverFn = () => {};

  function roleOf(i) {
    const ids = state.byByte.get(i);
    const r = state.reg;
    let region = '';
    if (r) {
      if (r.trailer && i >= r.trailer.range[0] && i < r.trailer.range[1]) region = 'r-trailer';
      else if (i >= r.data[0] && i < r.data[1]) region = 'r-data';
      else if (i < r.header[1]) region = 'r-header';
    }
    const lit = ids && ids.some((id) => state.lit === null || state.lit.has(id));
    return { ids, region, lit };
  }

  function regionLabelAt(row) {
    const r = state.reg;
    if (!r) return '';
    const a = row * 16, b = a + 16;
    const starts = [];
    if (r.header[1] > 0 && a === 0) starts.push('header');
    if (r.data[0] >= a && r.data[0] < b && r.data[1] > r.data[0]) starts.push('data region');
    if (r.trailer && r.trailer.range[0] >= a && r.trailer.range[0] < b) starts.push('trailer: ' + r.trailer.name);
    return starts.join(' · ');
  }

  function draw() {
    const top = scroller.scrollTop, h = scroller.clientHeight || 400;
    const first = Math.max(0, Math.floor(top / ROW) - MARGIN);
    const last = Math.min(rows - 1, Math.ceil((top + h) / ROW) + MARGIN);
    const frag = document.createDocumentFragment();
    for (let row = first; row <= last; row++) {
      const line = el('div', 'hex-row');
      line.style.top = row * ROW + 'px';
      const gut = el('span', 'gut', regionLabelAt(row));
      const off = el('span', 'off', hex4(row * 16));
      const hx = el('span', 'hx');
      const asc = el('span', 'asc');
      for (let k = 0; k < 16; k++) {
        const i = row * 16 + k;
        if (i >= n) break;
        const { ids, region, lit } = roleOf(i);
        const b = bytes[i];
        const cell = el('span', 'b ' + region + (lit ? ' f' : ''), HEX[b]);
        const ch = el('span', 'c ' + region + (lit ? ' f' : ''), b >= 0x20 && b < 0x7f ? String.fromCharCode(b) : '.');
        if (ids) {
          cell.dataset.ids = ch.dataset.ids = ids.join(',');
          if (hi !== null && ids.includes(hi)) { cell.classList.add('hi'); ch.classList.add('hi'); }
          const startsHere = ids.filter((id) => state.records[id].range[0] === i);
          if (lit && startsHere.length) {
            cell.tabIndex = 0;
            cell.setAttribute('aria-label', startsHere.map((id) => describe(state.records[id])).join('; '));
          }
        }
        hx.append(cell);
        asc.append(ch);
      }
      line.append(gut, off, hx, asc);
      frag.append(line);
    }
    layer.replaceChildren(frag);
  }

  function describe(r) {
    return `${r.name} at ${hex4(r.offset)}, ${r.fmt}, value ${valueText(r)}`;
  }

  function showTip(ids, anchor) {
    if (!ids || !ids.length) { tip.hidden = true; return; }
    tip.replaceChildren();
    for (const id of ids) {
      const r = state.records[id];
      const line = el('div', 'tip-line');
      line.append(el('span', 'tn', r.name), el('span', '', ` ${hex4(r.offset)}  ${r.fmt}  `), el('span', 'tv', valueText(r)));
      if (state.cands.length > 1) line.append(el('span', 'tu', '  ' + r.users.map(state.labels).join(', ')));
      tip.append(line);
    }
    const a = anchor.getBoundingClientRect(), p = root.getBoundingClientRect();
    tip.style.left = Math.max(0, a.left - p.left) + 'px';
    tip.style.top = a.bottom - p.top + 4 + 'px';
    tip.hidden = false;
  }

  const idsOf = (t) => (t && t.dataset && t.dataset.ids ? t.dataset.ids.split(',').map(Number) : null);
  layer.addEventListener('mouseover', (e) => {
    const ids = idsOf(e.target);
    showTip(ids, e.target);
    hoverFn(ids ? ids[0] : null);
  });
  layer.addEventListener('mouseleave', () => { tip.hidden = true; hoverFn(null); });
  layer.addEventListener('focusin', (e) => { const ids = idsOf(e.target); showTip(ids, e.target); hoverFn(ids ? ids[0] : null); });
  layer.addEventListener('focusout', () => { tip.hidden = true; });
  let raf = 0;
  scroller.addEventListener('scroll', () => { tip.hidden = true; cancelAnimationFrame(raf); raf = requestAnimationFrame(draw); });

  return {
    root,
    show(view) {
      const { records, byByte } = byteRoles(view.cands);
      state = { records, byByte, reg: view.regions ? regions(view.regions, n) : null, lit: view.lit ?? null,
                labels: view.labels ?? (() => ''), cands: view.cands };
      draw();
      return records;
    },
    highlight(id) {
      if (id === hi) return;
      hi = id;
      // toggle classes in place: redrawing would replace the element under the pointer and re-fire mouseover
      for (const s of layer.querySelectorAll('[data-ids]')) {
        s.classList.toggle('hi', id !== null && s.dataset.ids.split(',').map(Number).includes(id));
      }
    },
    scrollTo(offset) {
      const row = Math.floor(offset / 16);
      const top = scroller.scrollTop, h = scroller.clientHeight;
      if (row * ROW < top || (row + 1) * ROW > top + h) scroller.scrollTop = Math.max(0, row * ROW - h / 3);
      draw();
    },
    onHover(fn) { hoverFn = fn; },
    redraw: draw,
  };
}

/** Field table for one candidate. Rows highlight their bytes in the pane, and the pane highlights rows. */
export function fieldTable(cand, records, pane) {
  const eq = equivalentNames(cand.fields);
  const table = el('table', 'fields mono');
  const thead = el('thead');
  const hr = el('tr');
  for (const h of ['offset', 'field', 'format', 'value']) hr.append(el('th', '', h));
  thead.append(hr);
  const tbody = el('tbody');
  const idFor = (f) => records.find((r) => r.name === f.name && r.offset === f.offset && r.fmt === f.fmt)?.id;
  const rowsById = new Map();
  for (const f of cand.fields) {
    const id = idFor(f);
    const tr = el('tr');
    tr.tabIndex = 0;
    tr.dataset.id = id;
    const name = el('td', '', f.name);
    const plain = fieldPlain(f.name);
    if (plain) name.append(el('span', 'fp', plain));     // what the field holds, in plain words (UI task 42)
    if (eq.has(f.name)) name.append(el('span', 'eq', ' equivalent read'));
    tr.append(el('td', '', hex4(f.offset)), name, el('td', '', f.fmt), el('td', 'v', valueText(f)));
    const on = () => { pane.highlight(id); pane.scrollTo(f.offset); mark(id); };
    tr.addEventListener('mouseenter', on);
    tr.addEventListener('focus', on);
    tr.addEventListener('mouseleave', () => { pane.highlight(null); mark(null); });
    if (!rowsById.has(id)) rowsById.set(id, []);
    rowsById.get(id).push(tr);
    tbody.append(tr);
  }
  table.append(thead, tbody);
  function mark(id) {
    for (const [k, trs] of rowsById) for (const tr of trs) tr.classList.toggle('hi', k === id);
  }
  pane.onHover((id) => { pane.highlight(id); mark(id); });
  return table;
}
// Result screens. RESOLVED is complete (task 9); UNRESOLVED_AMBIGUITY and FAILED are filled in by tasks 10 and 11.
import { closureLine, declaredVsActual, revisionDiffs, changeText } from './logic.js';
import { createPane, fieldTable } from './pane.js';
import { paint } from './image.js';

function el(tag, cls, text) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text !== undefined) e.textContent = text;
  return e;
}

const path = (p) => (p.length ? p.join(' → ') : '');

/** The image frame used on every screen: a fixed box with the image, or a failure reason, in the same place. */
export function imageFrame(cand, box, opts = {}) {
  const frame = el('figure', 'frame');
  frame.style.width = box + 'px';
  const well = el('div', 'well');
  well.style.width = well.style.height = box + 'px';
  let done = Promise.resolve();
  if (cand.render && cand.render.data_b64) {
    const p = paint(cand.render, box - 16, box - 16, opts);
    well.append(p.canvas);
    done = p.done;
  } else {
    well.append(el('p', 'no-image', cand.render ? cand.render.failure : 'no image'));
  }
  const cap = el('figcaption');
  cap.append(el('span', 'dims mono', `${cand.width} × ${cand.height} · ${cand.bit_depth}-bit`));
  if (cand.render && cand.render.note) cap.append(el('span', 'note', cand.render.note));
  frame.append(well, cap);
  return { frame, done };
}

function chip(status) {
  const c = el('span', 'chip ' + (status === 'FAILED' ? 'chip-failed' : 'chip-ok'), status);
  return c;
}

function kv(label, value, cls = '') {
  const row = el('div', 'kv');
  row.append(el('span', 'k', label), el('span', 'v mono ' + cls, value));
  return row;
}

function resolvedPanel(payload) {
  const c = payload.candidates[0];
  const side = el('div', 'exam-right');
  const head = el('div', 'result-head');
  head.append(chip('RESOLVED'), el('span', 'source', `from the ${c.probe_name === 'generic' ? 'generic search' : c.probe_name.toUpperCase() + ' probe'} · stage ${payload.stage}`));
  side.append(head);

  const { frame, done } = imageFrame(c, 264, { reveal: true });
  side.append(frame);

  const dva = declaredVsActual(payload);
  if (dva) {
    const box = el('div', 'contradiction');
    box.append(el('p', 'c-title', 'The header lies about its encoding'));
    const grid = el('div', 'c-grid');
    grid.append(el('span', 'k', 'declared'), el('span', 'mono declared', dva.declared),
                el('span', 'k', 'actual'), el('span', 'mono actual', dva.actual));
    box.append(grid, el('p', 'c-proof mono', closureLine(c)));
    side.append(box);
  } else {
    side.append(el('p', 'closure mono', closureLine(c)));
  }

  const facts = el('div', 'facts');
  if (c.trailer) facts.append(kv('trailer', c.trailer));
  if (c.revision_path.length) {
    facts.append(kv('revision path', path(c.revision_path)));
    for (const d of revisionDiffs(payload)) {
      const t = changeText(d.step, d.before, d.after);
      facts.append(kv('', t ? `${d.step}: ${t}` : d.step, 'sub'));
    }
  } else {
    facts.append(kv('revision path', 'none: the file\u2019s declarations closed without revision'));
  }
  for (const alt of c.alternative_paths) facts.append(kv('second route', path(alt) + ', reaching the same answer'));
  facts.append(kv('checks', `${payload.total_checks} closure check${payload.total_checks === 1 ? '' : 's'} · engine ${payload.engine_ms} ms`));
  side.append(facts);
  return { side, done };
}

export function renderResult(root, payload, bytes) {
  root.replaceChildren();
  const pane = createPane(bytes);
  const cands = payload.candidates ?? payload.partial_candidates ?? [];
  const wrap = el('div', 'exam');
  const left = el('div', 'exam-left');
  left.append(pane.root);
  wrap.append(left);
  root.append(wrap);
  if (payload.status === 'RESOLVED') {
    const c = cands[0];
    const records = pane.show({ cands: [c], regions: c });
    left.append(fieldTable(c, records, pane));
    wrap.append(resolvedPanel(payload).side);
  } else {
    pane.show({ cands: [], regions: null });
    const side = el('div', 'exam-right');
    const head = el('div', 'result-head');
    head.append(chip(payload.status));
    side.append(head);
    wrap.append(side);
  }
}
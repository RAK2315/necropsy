// Result screens. Task 8: the examination layout (hex pane and field table). Tasks 9 to 12 add the outcome panels.
import { createPane, fieldTable } from './pane.js';

function el(tag, cls, text) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text !== undefined) e.textContent = text;
  return e;
}

export function renderResult(root, payload, bytes) {
  root.replaceChildren();
  const pane = createPane(bytes);
  const cands = payload.candidates ?? payload.partial_candidates ?? [];
  const wrap = el('div', 'exam');
  const left = el('div', 'exam-left');
  left.append(el('p', 'status-line mono', payload.status), pane.root);
  wrap.append(left);
  root.append(wrap);
  if (payload.status === 'RESOLVED') {
    const c = cands[0];
    const records = pane.show({ cands: [c], regions: c });
    left.append(fieldTable(c, records, pane));
  } else {
    pane.show({ cands: [], regions: null });
  }
}
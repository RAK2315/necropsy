// Result screens: RESOLVED, UNRESOLVED_AMBIGUITY and FAILED.
import {
  closureLine, declaredVsActual, revisionDiffs, changeText, ambiguityStatement, COHERENCE_NOTE, cardsHTML, cardTitle,
  terminationText, failureGroups, rejectionLine, hypothesisLine, stageOf,
} from './logic.js';
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

// ---- UNRESOLVED_AMBIGUITY ----

const CARD_BOX = 184;

function ambiguityScreen(root, payload, bytes) {
  const cands = payload.candidates;
  const n = cands.length;
  const lead = el('section', 'amb-lead');
  const head = el('div', 'result-head');
  head.append(chip('UNRESOLVED_AMBIGUITY'), el('span', 'source', `stage ${payload.stage} · ${payload.total_checks} closure checks · engine ${payload.engine_ms} ms`));
  lead.append(head, el('p', 'amb-statement', ambiguityStatement(n)), el('p', 'amb-note', COHERENCE_NOTE));

  const wrap = el('div', 'exam amb');
  const left = el('div', 'exam-left sticky');
  const pane = createPane(bytes);
  const labels = (i) => cardTitle(cands[i]);
  const union = () => pane.show({ cands, labels, regions: null });
  const records = union();
  const paneNote = el('p', 'pane-note', 'Bytes read by any reading. Hover or focus a reading to see its layout.');
  const tableSlot = el('div', 'table-slot');
  tableSlot.append(el('p', 'pane-note', 'Select a reading to list its fields.'));
  left.append(paneNote, pane.root, tableSlot);

  const grid = el('div', 'cards');
  grid.innerHTML = cardsHTML(payload);                 // markup is a pure function of the payload (tested for neutrality)
  for (const well of grid.querySelectorAll('.card-well')) {
    const c = cands[Number(well.dataset.index)];
    well.style.width = well.style.height = CARD_BOX + 'px';
    if (c.render && c.render.data_b64) well.append(paint(c.render, CARD_BOX - 12, CARD_BOX - 12).canvas);
  }
  let selected = null;
  for (const card of grid.querySelectorAll('.card')) {
    const i = Number(card.dataset.index);
    const show = () => { pane.show({ cands: [cands[i]], regions: cands[i] }); paneNote.textContent = `Layout of ${cardTitle(cands[i])}.`; };
    const back = () => { union(); paneNote.textContent = 'Bytes read by any reading. Hover or focus a reading to see its layout.'; };
    card.addEventListener('mouseenter', show);
    card.addEventListener('focus', show);
    card.addEventListener('mouseleave', back);
    card.addEventListener('blur', back);
    const select = () => {
      if (selected !== null) grid.querySelector(`.card[data-index="${selected}"]`).classList.remove('open');
      selected = i;
      card.classList.add('open');
      tableSlot.replaceChildren(el('p', 'pane-note', `Fields of ${cardTitle(cands[i])}`), fieldTable(cands[i], records, pane));
    };
    card.addEventListener('click', select);
    card.addEventListener('keydown', (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); select(); } });
  }
  const right = el('div', 'exam-right');
  right.append(grid);
  wrap.append(left, right);
  root.append(lead, wrap);
}

// ---- FAILED ----

const GROUP_CAP = 200;

function failedPanel(payload) {
  const side = el('div', 'exam-right');
  const head = el('div', 'result-head');
  head.append(chip('FAILED'), el('span', 'source', `termination ${payload.termination}`));
  side.append(head, el('p', 'fail-reason', terminationText(payload.termination)));

  const total = payload.rejections.length + (payload.rejections_omitted || 0);
  const stages = new Set(payload.rejections.map((r) => stageOf(r.source)));
  const facts = el('div', 'facts');
  facts.append(kv('checks', `${payload.total_checks} closure check${payload.total_checks === 1 ? '' : 's'} · engine ${payload.engine_ms} ms`),
               kv('rejections', String(total)));
  side.append(facts);

  if (payload.termination === 'exhausted' && (!stages.size || stages.has('generic'))) {
    side.append(el('p', 'fail-scope', 'No probe signature matched, so generic search ran. No closing layout was found within its stated axes and budget. That does not mean the file has no layout.'));
    if (payload.total_checks === 0) {
      side.append(el('p', 'fail-scope', 'No combination of header length, width, height and bit depth fitted the file\u2019s size, so no hypothesis reached the closure gate.'));
    }
  }
  if (payload.termination === 'internal_error') {
    for (const r of payload.rejections) if (r.detail) side.append(el('p', 'mono fail-detail', r.detail));
  }
  if (payload.rejections_omitted > 0) {
    side.append(el('p', 'fail-scope', `Showing ${payload.rejections.length} of ${total} rejections. The rest did not fit in one response. Counts for all of them:`));
    const t = el('table', 'counts mono');
    for (const [stage, reasons] of Object.entries(payload.rejection_counts)) {
      for (const [reason, count] of Object.entries(reasons)) {
        const tr = el('tr');
        tr.append(el('td', '', stage), el('td', '', reason), el('td', 'num', String(count)));
        t.append(tr);
      }
    }
    side.append(t);
  }

  const groups = el('div', 'groups');
  for (const g of failureGroups(payload.rejections)) {
    const sec = el('section', 'stage');
    sec.append(el('h3', 'stage-title', `${g.stage} · ${g.count}`));
    for (const r of g.reasons) {
      const det = el('details', 'reason');
      if (g.count <= 12) det.open = true;
      det.append(el('summary', 'mono', `${r.reason} · ${r.count}`));
      const list = el('ol', 'rej mono');
      for (const item of r.items.slice(0, GROUP_CAP)) {
        const li = el('li');
        li.append(el('span', 'rl', rejectionLine(item)));
        if (item.hypothesis) li.append(el('span', 'rh', hypothesisLine(item.hypothesis)));
        if (item.detail && payload.termination !== 'internal_error') li.append(el('span', 'rh', item.detail));
        list.append(li);
      }
      det.append(list);
      if (r.items.length > GROUP_CAP) det.append(el('p', 'more', `${r.items.length - GROUP_CAP} more not shown`));
      sec.append(det);
    }
    groups.append(sec);
  }
  side.append(groups);

  if (payload.partial_candidates.length) {
    const sec = el('section', 'partial');
    sec.append(el('h3', 'stage-title', 'Closed before the search stopped'),
      el('p', 'fail-scope', 'These passed closure, but the search stopped before it could decide between them or rule others out. They are not an outcome.'));
    for (const c of payload.partial_candidates) sec.append(el('p', 'mono rh', cardTitle(c)));
    side.append(sec);
  }
  return side;
}

export function renderResult(root, payload, bytes) {
  root.replaceChildren();
  if (payload.status === 'UNRESOLVED_AMBIGUITY') { ambiguityScreen(root, payload, bytes); return; }
  const pane = createPane(bytes);
  const wrap = el('div', 'exam');
  const left = el('div', 'exam-left');
  left.append(pane.root);
  wrap.append(left);
  root.append(wrap);
  if (payload.status === 'RESOLVED') {
    const c = payload.candidates[0];
    const records = pane.show({ cands: [c], regions: c });
    left.append(fieldTable(c, records, pane));
    wrap.append(resolvedPanel(payload).side);
  } else {
    pane.show({ cands: [], regions: null });
    wrap.append(failedPanel(payload));
  }
}
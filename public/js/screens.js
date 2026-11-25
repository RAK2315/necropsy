// Result screens: RESOLVED, UNRESOLVED_AMBIGUITY and FAILED.
import {
  closureLine, declaredVsActual, revisionDiffs, changeText, ambiguityStatement, COHERENCE_NOTE, cardsHTML, cardTitle,
  terminationText, failureSentence, failureGroups, rejectionLine, hypothesisLine, stageOf, inputBase, STOPPED_AT_LIMIT,
} from './logic.js';
import { createPane, fieldTable } from './pane.js';
import { CHIP } from './words.js';
import { paint } from './image.js';
import { specPanel } from './spec.js';
import { createReplay } from './replay.js';
import { downloadRow, savePNG, saveData } from './downloads.js';

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
    const p = paint(cand.render, box - 16, box - 16, { ...opts, bitDepth: cand.bit_depth });
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

/** The outcome chip: the plain word leads; the engine's enum follows, small, for the README, API and specs. */
function chip(status) {
  const c = el('span', 'chip ' + (status === 'FAILED' ? 'chip-failed' : 'chip-ok'), CHIP[status] + ' ');
  c.dataset.cap = 'chip';
  c.append(el('span', 'tech', status));
  return c;
}

function kv(label, value, cls = '') {
  const row = el('div', 'kv');
  row.append(el('span', 'k', label), el('span', 'v mono ' + cls, value));
  return row;
}

function resolvedPanel(payload, bytes, base) {
  const c = payload.candidates[0];
  const side = el('div', 'exam-right');
  const head = el('div', 'result-head');
  head.append(chip('RESOLVED'), el('span', 'source', `from the ${c.probe_name === 'generic' ? 'generic search' : c.probe_name.toUpperCase() + ' probe'} · stage ${payload.stage}`));
  side.append(head);

  const { frame, done } = imageFrame(c, 264, { reveal: true });
  side.append(frame, downloadRow(c, bytes, base));

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

function ambiguityScreen(root, payload, bytes, base, onProgress) {
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
  const replay = createReplay(payload, {
    onFrame: onProgress,
    onStep: (s) => { pane.show(stepView(s)); paneNote.textContent = 'Replay: bytes read by this hypothesis.'; },
    onFinal: () => { union(); paneNote.textContent = 'Bytes read by any reading. Hover or focus a reading to see its layout.'; lead.classList.remove('pending'); right.classList.remove('pending'); },
  });
  left.append(replay.root, paneNote, pane.root, tableSlot);

  const grid = el('div', 'cards');
  grid.innerHTML = cardsHTML(payload);                 // markup is a pure function of the payload (tested for neutrality)
  for (const well of grid.querySelectorAll('.card-well')) {
    const c = cands[Number(well.dataset.index)];
    well.style.width = well.style.height = CARD_BOX + 'px';
    if (c.render && c.render.data_b64) well.append(paint(c.render, CARD_BOX - 12, CARD_BOX - 12, { bitDepth: c.bit_depth }).canvas);
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
    card.addEventListener('click', (e) => {
      const b = e.target.closest('.dl-btn');
      if (b) { e.stopPropagation(); if (b.dataset.act === 'png') savePNG(cands[i], base); else saveData(cands[i], bytes, base); return; }
      select();
    });
    card.addEventListener('keydown', (e) => { if (e.target === card && (e.key === 'Enter' || e.key === ' ')) { e.preventDefault(); select(); } });
  }
  const right = el('div', 'exam-right pending');
  right.append(grid);
  lead.classList.add('pending');
  wrap.append(left, right);
  root.append(lead, wrap);
  return replay;
}

// ---- FAILED ----

const GROUP_CAP = 200;

function failedPanel(payload) {
  const side = el('div', 'exam-right');
  const head = el('div', 'result-head');
  head.append(chip('FAILED'), el('span', 'source', `termination ${payload.termination}`));
  side.append(head, el('p', 'fail-reason', failureSentence(payload)));

  const total = payload.rejections.length + (payload.rejections_omitted || 0);
  const stages = new Set(payload.rejections.map((r) => stageOf(r.source)));
  const facts = el('div', 'facts');
  facts.append(kv('checks', `${payload.total_checks} closure check${payload.total_checks === 1 ? '' : 's'} · engine ${payload.engine_ms} ms`),
               kv('rejections', String(total)));
  side.append(facts);

  const generic = !stages.size || stages.has('generic');
  if (payload.termination === 'exhausted' && generic) {
    side.append(el('p', 'fail-scope', 'No probe signature matched, so generic search ran. No closing layout was found within its stated axes and budget. That does not mean the file has no layout.'));
  }
  if (payload.termination === 'deadline_exceeded' || payload.termination === 'search_cap_exceeded') {
    side.append(el('p', 'fail-scope fail-limit', STOPPED_AT_LIMIT));
  }
  if (payload.termination === 'no_hypothesis_checked') {
    side.append(el('p', 'fail-scope', generic
      ? 'No probe signature matched, so generic search ran. No combination of header length, width, height and bit depth fitted the file\u2019s size, so nothing was closure-checked. That does not mean the file has no layout.'
      : 'Nothing was closure-checked.'));
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

/** Two views of one result: the examination and the emitted spec, one click apart. */
function views(root, payload, bytes) {
  const bar = el('nav', 'viewbar');
  const exam = el('div', 'view-exam');
  const spec = el('div', 'view-spec');
  spec.hidden = true;
  const b1 = el('button', 'vtab', 'Examination');
  const b2 = el('button', 'vtab', 'Emitted spec');
  for (const b of [b1, b2]) b.type = 'button';
  let built = false;
  const show = (s) => {
    exam.hidden = s; spec.hidden = !s;
    b1.setAttribute('aria-pressed', String(!s)); b2.setAttribute('aria-pressed', String(s));
    if (s && !built) { spec.append(specPanel(payload, bytes)); built = true; }
  };
  b1.addEventListener('click', () => show(false));
  b2.addEventListener('click', () => show(true));
  bar.append(b1, b2);
  root.append(bar, exam, spec);
  show(false);
  return exam;
}

/** The pane view for one replay step: the rejected hypothesis's own field reads, no regions. */
function stepView(step) {
  const h = step.rejection.hypothesis;
  return { cands: h ? [{ fields: h.fields }] : [], regions: null };
}

let activeReplay = null;    // the replay of the result on screen, if any

/** Stop the current result's replay. Called whenever the result is left or replaced. */
export function leaveResult() {
  if (activeReplay) activeReplay.dispose();
  activeReplay = null;
}

export function renderResult(root, payload, bytes, opts = {}) {
  leaveResult();
  root.replaceChildren();
  if (opts.notice) {
    const n = el('p', 'notice', opts.notice);
    n.setAttribute('role', 'status');
    root.append(n);
  }
  const target = views(root, payload, bytes);
  const base = inputBase(opts.name);
  if (payload.status === 'UNRESOLVED_AMBIGUITY') {
    activeReplay = ambiguityScreen(target, payload, bytes, base, opts.onProgress);
    activeReplay.start();
    return;
  }
  const pane = createPane(bytes);
  const wrap = el('div', 'exam');
  const left = el('div', 'exam-left');
  const right = el('div', 'exam-right pending');
  wrap.append(left, right);
  target.append(wrap);
  let finalView, buildRight, table = null;
  if (payload.status === 'RESOLVED') {
    const c = payload.candidates[0];
    finalView = { cands: [c], regions: c };
    buildRight = () => right.replaceChildren(...resolvedPanel(payload, bytes, base).side.childNodes);   // built at the final step, so the image reveal starts then
  } else {
    finalView = { cands: [], regions: null };
    buildRight = () => right.replaceChildren(...failedPanel(payload).childNodes);
  }
  let built = false;
  const replay = createReplay(payload, {
    onFrame: opts.onProgress,
    onStep: (s) => pane.show(stepView(s)),
    onFinal: () => {
      const records = pane.show(finalView);
      if (!built) {
        built = true;
        buildRight();
        right.classList.remove('pending');
        if (payload.status === 'RESOLVED') { table = fieldTable(payload.candidates[0], records, pane); left.append(table); }
      }
    },
  });
  left.append(replay.root, pane.root);
  activeReplay = replay;
  replay.start();
}
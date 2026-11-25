// Result screens: RESOLVED, UNRESOLVED_AMBIGUITY and FAILED.
// UI clarity pass (tasks 26 to 28, built by Claude Code, not Kiro): a verdict heading above both columns, a title and
// one plain line on every region, and plain words from words.js, with the engine's own terms kept in `.tech`.
import {
  closureLine, declaredVsActual, revisionDiffs, changeText, COHERENCE_NOTE, cardsHTML, cardTitle, ambGridHTML,
  failureSentence, failureGroups, rejectionLine, hypothesisLine, stageOf, inputBase, STOPPED_AT_LIMIT,
} from './logic.js';
import { createPane, fieldTable } from './pane.js';
import { paint } from './image.js';
import { specPanel } from './spec.js';
import { createReplay } from './replay.js';
import { downloadRow, savePNG, saveData } from './downloads.js';
import {
  CHIP, verdictText, sourceText, correctionText, proofText, reasonText, rejectionPlain, stageText, encodingText,
} from './words.js';

function el(tag, cls, text) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text !== undefined) e.textContent = text;
  return e;
}

const fmt = (n) => Number(n).toLocaleString('en-US');
const path = (p) => (p.length ? p.join(' → ') : '');

/** A region's title and one plain line (task 26). */
function regionHead(title, line) {
  const h = el('div', 'region-head');
  h.append(el('h2', 'r-title', title), el('p', 'r-line', line));
  return h;
}

function region(name, title, line, ...kids) {
  const s = el('section', 'region');
  s.dataset.region = name;
  s.append(regionHead(title, line), ...kids);
  return s;
}

/**
 * The recovered image on the result screen (second clarity pass, change 3): scaled to fill its frame, nearest-neighbour,
 * so the frame is the image's own shape with no dead space. The true dimensions stay beneath it.
 */
export function fillFrame(cand, maxW, maxH, opts = {}) {
  const frame = el('figure', 'frame fill');
  const well = el('div', 'well');
  let done = Promise.resolve();
  if (cand.render && cand.render.data_b64) {
    const p = paint(cand.render, maxW, maxH, { ...opts, fill: true, bitDepth: cand.bit_depth });
    well.append(p.canvas);
    done = p.done;
  } else {
    well.classList.add('empty');
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
  row.append(el('span', 'k', label), el('span', 'v ' + cls, value));
  return row;
}

const checksTech = (p) => `${p.total_checks} closure check${p.total_checks === 1 ? '' : 's'} · engine ${p.engine_ms} ms`;

/** The full-width verdict heading above both columns, shown when the replay reaches its end. */
function verdictBar(payload) {
  const bar = el('section', 'verdict-bar pending');
  bar.dataset.cap = 'verdict';
  bar.append(el('p', 'verdict-wait', 'The verdict appears here when the replay ends.'));
  const head = el('div', 'verdict-head');
  head.append(chip(payload.status), el('h1', 'verdict-text', verdictText(payload)));
  bar.append(head);
  if (payload.status === 'RESOLVED') {
    const c = payload.candidates[0];
    const steps = c.revision_path.map((s) => correctionText(s, c));
    const how = steps.length
      ? `${sourceText(c.probe_name)} ${steps.length === 1 ? 'One correction' : `${steps.length} corrections`}: ${steps.join('; ')}.`
      : `${sourceText(c.probe_name)} No correction was needed.`;
    bar.append(el('p', 'verdict-sub', how));
  } else if (payload.status === 'UNRESOLVED_AMBIGUITY') {
    bar.append(el('p', 'verdict-sub', `${sourceText(payload.candidates[0].probe_name)} Each reading below fits the data exactly. The bytes alone cannot separate them.`));
  } else {
    bar.append(el('p', 'verdict-sub fail-reason', failureSentence(payload)));
  }
  return bar;
}

/** The engine's own technical line: stage, fit checks, engine time, revision path. Evidence, not narrative. */
function techLine(payload) {
  let t;
  if (payload.status === 'RESOLVED') {
    const c = payload.candidates[0];
    t = `stage ${payload.stage} · ${checksTech(payload)}${c.revision_path.length ? ' · revision path ' + path(c.revision_path) : ''}`;
  } else if (payload.status === 'UNRESOLVED_AMBIGUITY') t = `stage ${payload.stage} · ${checksTech(payload)}`;
  else t = `termination ${payload.termination} · ${checksTech(payload)}`;
  const p = el('p', 'tech ev-tech', t);
  p.dataset.cap = 'tech-line';
  return p;
}

/** One collapsed piece of evidence behind a control that says what is inside and how big it is (change 2). */
function drawer(cap, label, open, ...kids) {
  const d = el('details', 'ev');
  d.dataset.cap = cap;
  d.open = open;
  const sum = el('summary', 'ev-sum', label);
  d.append(sum, ...kids);
  return d;
}

/**
 * Level 4, the evidence: the technical line, then the file's bytes and the header values, each collapsed by default
 * except on FAILED, where the bytes are most of what there is to show.
 */
function evidence(payload, bytes, hexRegion, fieldsRegion, fieldsLabel) {
  const open = payload.status === 'FAILED';
  const kids = [techLine(payload), drawer('ev-bytes', `The file’s bytes (${fmt(bytes.length)})`, open, hexRegion)];
  if (fieldsRegion) kids.push(drawer('ev-fields', fieldsLabel, open, fieldsRegion));
  const sec = region('evidence', 'The evidence', 'The raw bytes and the values read from them, for checking the work.', ...kids);
  sec.classList.add('level-4');
  return sec;
}

// ---- RESOLVED ----

// The recovered image's frame on the result screen. With the verdict and the one-line proof it fits above the fold at
// 1600 × 900 (tests/ui/test_single_column.py).
const IMAGE_W = 880;
const IMAGE_H = 340;

function resolvedPanel(payload, bytes, base) {
  const c = payload.candidates[0];
  const side = el('div', 'exam-right');

  const dva = declaredVsActual(payload);
  if (dva) {
    // The two findings side by side; nothing more is claimed (Rehaan, 25 Nov). Built from the payload, not a fixed string.
    const box = el('div', 'contradiction');
    box.dataset.cap = 'contradiction';
    box.append(el('p', 'c-title', `Declared: ${encodingText(dva.word)}. Only ${dva.actual === 'rle_pcx' ? 'run-length decoding' : encodingText(dva.actual)} fits.`),
      el('p', 'tech', `encoding ${dva.declared} · fits as ${dva.actual}`));
    side.append(box);
  }

  const { frame, done } = fillFrame(c, IMAGE_W, IMAGE_H, { reveal: true });
  frame.dataset.cap = 'image';
  side.append(region('image', 'Recovered image', 'Decoded from this file’s own bytes.', frame, downloadRow(c, bytes, base)));

  side.append(region('proof', 'Why it fits', 'The check every reading must pass: the data decodes to exactly the size this layout needs.',
    el('p', 'closure', proofText(c)), el('p', 'tech', closureLine(c))));

  const facts = el('div', 'facts');
  if (c.trailer) facts.append(kv('trailer', `The last ${fmt(bytes.length - c.data_end)} bytes are read as a trailer, not pixels.`), kv('', c.trailer, 'tech'));
  if (c.revision_path.length) {
    for (const d of revisionDiffs(payload)) {
      const t = changeText(d.step, d.before, d.after);
      facts.append(kv('correction', correctionText(d.step, d.after)), kv('', t ? `${d.step}: ${t}` : d.step, 'tech'));
    }
  } else {
    facts.append(kv('corrections', 'None: the file’s own declarations fit without correction.'));
  }
  for (const alt of c.alternative_paths) facts.append(kv('second route', 'Another order of corrections reaches the same answer.'), kv('', path(alt), 'tech'));
  facts.append(kv('checked', `${fmt(payload.total_checks)} layout${payload.total_checks === 1 ? '' : 's'} checked in ${fmt(payload.engine_ms)} ms`));
  const how = region('facts', 'Corrections', 'The corrections tried, and how many layouts were checked.', facts);
  return { side, how, done };
}

// ---- UNRESOLVED_AMBIGUITY ----

const CARD_BOX = 184;
const GRID_BOX = 64;
const UNION_NOTE = 'Bytes read by any reading. Hover or focus a reading to see its layout.';

function ambiguityScreen(root, payload, bytes, base, onProgress) {
  const cands = payload.candidates;
  const bar = verdictBar(payload);

  const wrap = el('div', 'exam flow amb');
  const pane = createPane(bytes);
  pane.root.dataset.cap = 'hex';
  const labels = (i) => cardTitle(cands[i]);
  const union = () => pane.show({ cands, labels, regions: null });
  const records = union();
  const paneNote = el('p', 'pane-note', UNION_NOTE);
  const tableSlot = el('div', 'table-slot');
  tableSlot.append(el('p', 'pane-note', 'Select a reading to list its fields.'));
  const replay = createReplay(payload, {
    onFrame: onProgress,
    onStep: (s) => { pane.show(stepView(s)); paneNote.textContent = 'Replay: bytes read by the layout being tried.'; },
    onFinal: () => { union(); paneNote.textContent = UNION_NOTE; bar.classList.remove('pending'); right.classList.remove('pending'); right.querySelector('.answer-pending')?.remove(); },
  });
  const hexRegion = region('hex', 'The file’s bytes', 'Highlighted bytes were read as header fields by at least one reading.', paneNote, pane.root);
  const fieldsRegion = region('fields', 'What the header declares', 'Each value a reading takes from the file, and where it sits.', tableSlot);
  const ev = evidence(payload, bytes, hexRegion, fieldsRegion, `What each reading declares (${cands.length} readings)`);

  // at-a-glance grid (task 28): every reading at one size, in payload order, no score, no emphasis
  const glance = el('div', 'amb-grid');
  glance.dataset.cap = 'amb-grid';
  glance.innerHTML = ambGridHTML(payload);             // markup is a pure function of the payload (tested for neutrality)
  for (const well of glance.querySelectorAll('.amb-well')) {
    const c = cands[Number(well.dataset.index)];
    if (c.render && c.render.data_b64) well.append(paint(c.render, GRID_BOX - 8, GRID_BOX - 8, { bitDepth: c.bit_depth }).canvas);
  }

  const grid = el('div', 'cards');
  grid.innerHTML = cardsHTML(payload);                 // markup is a pure function of the payload (tested for neutrality)
  for (const well of grid.querySelectorAll('.card-well')) {
    const c = cands[Number(well.dataset.index)];
    well.style.width = well.style.height = CARD_BOX + 'px';
    if (c.render && c.render.data_b64) well.append(paint(c.render, CARD_BOX - 12, CARD_BOX - 12, { bitDepth: c.bit_depth }).canvas);
  }
  let selected = null;
  const select = (i) => {
    const card = grid.querySelector(`.card[data-index="${i}"]`);
    if (selected !== null) grid.querySelector(`.card[data-index="${selected}"]`).classList.remove('open');
    selected = i;
    card.classList.add('open');
    tableSlot.replaceChildren(el('p', 'pane-note', `Fields of ${cardTitle(cands[i])}`), fieldTable(cands[i], records, pane));
    ev.querySelector('[data-cap=ev-fields]').open = true;      // the person asked for this reading's values
  };
  for (const card of grid.querySelectorAll('.card')) {
    const i = Number(card.dataset.index);
    card.dataset.cap = 'card';
    const show = () => { pane.show({ cands: [cands[i]], regions: cands[i] }); paneNote.textContent = `Layout of ${cardTitle(cands[i])}.`; };
    const back = () => { union(); paneNote.textContent = UNION_NOTE; };
    card.addEventListener('mouseenter', show);
    card.addEventListener('focus', show);
    card.addEventListener('mouseleave', back);
    card.addEventListener('blur', back);
    card.addEventListener('click', (e) => {
      const b = e.target.closest('.dl-btn');
      if (b) { e.stopPropagation(); if (b.dataset.act === 'png') savePNG(cands[i], base); else saveData(cands[i], bytes, base); return; }
      select(i);
    });
    card.addEventListener('keydown', (e) => { if (e.target === card && (e.key === 'Enter' || e.key === ' ')) { e.preventDefault(); select(i); } });
  }
  for (const tile of glance.querySelectorAll('.amb-tile')) {
    tile.addEventListener('click', (e) => {
      e.preventDefault();
      const card = grid.querySelector(`.card[data-index="${tile.dataset.index}"]`);
      card.scrollIntoView({ block: 'nearest' });
      card.focus();
    });
  }
  const right = el('div', 'exam-right answer pending');
  const note = el('p', 'amb-note', COHERENCE_NOTE);
  note.append(' ', el('span', 'tech', 'row_mad_ratio'));
  right.append(region('glance', 'Every reading at a glance', 'Same size, in the order the engine found them. Select one to go to its card.', glance),
    region('cards', 'Readings that fit', 'Each one fits the data exactly. The bytes alone cannot separate them.', grid, note));
  const how = el('div', 'how-col level-3');
  how.append(replayRegion(replay));
  wrap.append(right, how, ev);
  root.append(bar, wrap);
  return replay;
}

// ---- FAILED ----

const GROUP_CAP = 200;

function failedPanel(payload) {
  const side = el('div', 'exam-right');
  const total = payload.rejections.length + (payload.rejections_omitted || 0);
  const stages = new Set(payload.rejections.map((r) => stageOf(r.source)));

  const generic = !stages.size || stages.has('generic');
  if (payload.termination === 'exhausted' && generic) {
    side.append(el('p', 'fail-scope', 'No format signature matched, so it searched layouts directly. No layout within that search’s limits fits the data exactly. That does not mean the file has no layout.'));
  }
  if (payload.termination === 'deadline_exceeded' || payload.termination === 'search_cap_exceeded') {
    side.append(el('p', 'fail-scope fail-limit', STOPPED_AT_LIMIT));
  }
  if (payload.termination === 'no_hypothesis_checked') {
    side.append(el('p', 'fail-scope', generic
      ? 'No format signature matched, so it searched layouts directly. No combination of header length, width, height and bit depth matched the file’s size, so no layout reached the fit check. That does not mean the file has no layout.'
      : 'No layout reached the fit check.'));
  }
  if (payload.termination === 'internal_error') {
    for (const r of payload.rejections) if (r.detail) side.append(el('p', 'tech fail-detail', r.detail));
  }
  if (payload.rejections_omitted > 0) {
    side.append(el('p', 'fail-scope', `Showing ${payload.rejections.length} of ${total} rejected layouts. The rest did not fit in one response. Counts for all of them:`));
    const t = el('table', 'counts tech');
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
  groups.dataset.cap = 'failed-groups';
  for (const g of failureGroups(payload.rejections)) {
    const sec = el('section', 'stage');
    const title = el('h3', 'stage-title', `${stageText(g.stage)} · ${g.count}`);
    title.append(' ', el('span', 'tech', g.stage));
    sec.append(title);
    for (const r of g.reasons) {
      const det = el('details', 'reason');
      if (g.count <= 12) det.open = true;
      const sum = el('summary', '', `${reasonText(r.reason)} · ${r.count}`);
      sum.append(' ', el('span', 'tech', r.reason));
      det.append(sum);
      const list = el('ol', 'rej');
      for (const item of r.items.slice(0, GROUP_CAP)) {
        const li = el('li');
        li.append(el('span', 'rl', rejectionPlain(item)));
        li.append(el('span', 'rh tech', [rejectionLine(item), item.hypothesis ? hypothesisLine(item.hypothesis) : ''].filter(Boolean).join(' · ')));
        if (item.detail && payload.termination !== 'internal_error') li.append(el('span', 'rh tech', item.detail));
        list.append(li);
      }
      det.append(list);
      if (r.items.length > GROUP_CAP) det.append(el('p', 'more', `${r.items.length - GROUP_CAP} more not shown`));
      sec.append(det);
    }
    groups.append(sec);
  }
  const facts = el('div', 'facts');
  facts.append(kv('checked', `${fmt(payload.total_checks)} layout${payload.total_checks === 1 ? '' : 's'} checked in ${fmt(payload.engine_ms)} ms`),
               kv('rejected', fmt(total)));
  side.append(region('groups', 'Layouts tried', 'Each layout that was tried, and why it did not fit.', facts, groups));

  if (payload.partial_candidates.length) {
    const sec = el('section', 'partial');
    sec.append(el('h3', 'stage-title', 'Fit before the search stopped'),
      el('p', 'fail-scope', 'These fit the data exactly, but the search stopped before it could decide between them or rule others out. They are not an outcome.'));
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
  b1.dataset.cap = 'tab-exam';
  b2.dataset.cap = 'tab-spec';
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

/** The pane view for one replay step: the rejected layout's own field reads, no regions. */
function stepView(step) {
  const h = step.rejection.hypothesis;
  return { cands: h ? [{ fields: h.fields }] : [], regions: null };
}

function replayRegion(replay) {
  replay.root.dataset.cap = 'replay';
  return region('replay', 'How the engine searched', 'Every layout it tried, in order, and why each one was rejected.', replay.root);
}

let activeReplay = null;    // the replay of the result on screen, if any

/** Stop the current result's replay. Called whenever the result is left or replaced. */
export function leaveResult() {
  if (activeReplay) activeReplay.dispose();
  activeReplay = null;
}

/**
 * The single-column result (second clarity pass, change 1), top to bottom with the weight falling at each step:
 *   level 1 the answer and level 2 why it is right (`.exam-right.answer`), level 3 how it got there (`.how-col`: the replay
 *   and the corrections), level 4 the evidence (`.evidence`: the technical line, the bytes, the header values).
 */
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
  const bar = verdictBar(payload);
  const pane = createPane(bytes);
  pane.root.dataset.cap = 'hex';
  const flow = el('div', 'exam flow');
  const answer = el('div', 'exam-right answer pending');
  const how = el('div', 'how-col');
  const hexLine = payload.status === 'RESOLVED'
    ? 'Shaded by the role this reading gives them: header, data, trailer. Highlighted bytes were read as header fields.'
    : 'No layout tried fits, so no byte has a role to shade.';
  const hex = region('hex', 'The file’s bytes', hexLine, pane.root);
  let finalView, buildAnswer, fieldsRegion = null, fieldsLabel = '';
  if (payload.status === 'RESOLVED') {
    const c = payload.candidates[0];
    finalView = { cands: [c], regions: c };
    fieldsRegion = region('fields', 'What the header declares', 'Each value the file states about itself, and where it sits.');
    fieldsLabel = `What the header declares (${c.fields.length} value${c.fields.length === 1 ? '' : 's'})`;
    buildAnswer = () => {                // built at the final step, so the image reveal starts then
      const r = resolvedPanel(payload, bytes, base);
      answer.replaceChildren(...r.side.childNodes);
      how.append(r.how);
    };
  } else {
    finalView = { cands: [], regions: null };
    buildAnswer = () => answer.replaceChildren(...failedPanel(payload).childNodes);
  }
  flow.append(answer, how, evidence(payload, bytes, hex, fieldsRegion, fieldsLabel));
  target.append(bar, flow);
  let built = false;
  const replay = createReplay(payload, {
    onFrame: opts.onProgress,
    onStep: (s) => pane.show(stepView(s)),
    onFinal: () => {
      const records = pane.show(finalView);
      if (!built) {
        built = true;
        buildAnswer();
        answer.classList.remove('pending');
        bar.classList.remove('pending');
        if (fieldsRegion) {
          const table = fieldTable(payload.candidates[0], records, pane);
          table.dataset.cap = 'fields';
          fieldsRegion.append(table);
        }
      }
    },
  });
  how.classList.add('level-3');
  how.append(replayRegion(replay));
  activeReplay = replay;
  replay.start();
}

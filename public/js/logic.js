// Pure functions over the Result payload. No DOM. Tested with node --test (tests/ui/js/).

const SIZES = { B: 1, b: 1, H: 2, h: 2, I: 4, i: 4, Q: 8, q: 8 };

/** Byte size of a struct format the engine emits: B, <H, >H, <I, >I, <i, >i, Ns. */
export function calcsize(fmt) {
  const f = String(fmt).replace(/^[<>=!@]/, '');
  const m = /^(\d*)([A-Za-z])$/.exec(f);
  if (!m) return 0;
  const n = m[1] === '' ? 1 : Number(m[1]);
  if (m[2] === 's') return n;
  return (SIZES[m[2]] ?? 0) * n;
}

/** Half-open byte range a field record covers. */
export function fieldRange(rec) {
  return [rec.offset, rec.offset + calcsize(rec.fmt)];
}

/** Header, data region and (only when a trailer matched) trailer, as half-open ranges. */
export function regions(cand, total) {
  return {
    header: [0, cand.data_start],
    data: [cand.data_start, cand.data_end],
    trailer: cand.trailer ? { name: cand.trailer, range: [cand.data_end, total] } : null,
  };
}

/** The value as text: one-element tuples show their element, bytes show as hex. */
export function valueText(rec) {
  const v = rec.value.map((x) => (x && typeof x === 'object' && 'bytes' in x ? `b'${hexToAscii(x.bytes)}'` : String(x)));
  return v.length === 1 ? v[0] : `(${v.join(', ')})`;
}

function hexToAscii(hex) {
  let s = '';
  for (let i = 0; i < hex.length; i += 2) {
    const b = parseInt(hex.slice(i, i + 2), 16);
    s += b >= 0x20 && b < 0x7f && b !== 0x27 && b !== 0x5c ? String.fromCharCode(b) : '\\x' + hex.slice(i, i + 2);
  }
  return s;
}

export const hex4 = (n) => '0x' + n.toString(16).toUpperCase().padStart(4, '0');

/**
 * For each candidate, its records with a stable id. Records of several candidates that are the same read
 * (name, offset, fmt) are merged into one entry listing every candidate that uses it.
 * Returns { records: [{id, name, offset, fmt, value, range, users: [candIndex...]}], byByte: Map<i, id[]> }.
 */
export function byteRoles(cands) {
  const records = [];
  const key = new Map();
  cands.forEach((c, ci) => {
    for (const f of c.fields) {
      const k = `${f.name}|${f.offset}|${f.fmt}`;
      let r = key.get(k);
      if (!r) {
        r = { id: records.length, name: f.name, offset: f.offset, fmt: f.fmt, value: f.value, range: fieldRange(f), users: [] };
        key.set(k, r);
        records.push(r);
      }
      if (!r.users.includes(ci)) r.users.push(ci);
    }
  });
  const byByte = new Map();
  for (const r of records) {
    for (let i = r.range[0]; i < r.range[1]; i++) {
      if (!byByte.has(i)) byByte.set(i, []);
      byByte.get(i).push(r.id);
    }
  }
  return { records, byByte };
}

/** Group names that occur more than once among one candidate's fields: equivalent reads. */
export function equivalentNames(fields) {
  const n = new Map();
  for (const f of fields) n.set(f.name, (n.get(f.name) ?? 0) + 1);
  return new Set([...n].filter(([, c]) => c > 1).map(([k]) => k));
}

export function stageOf(source) {
  if (['pcx', 'tga', 'pbm', 'tiff'].includes(source)) return 'probe';
  if (String(source).startsWith('revision:')) return 'revision';
  if (source === 'generic') return 'generic';
  return 'engine';
}

/** The replay steps: every rejection in payload order, then one final step. Nothing added, nothing reordered. */
export function buildSteps(payload) {
  const steps = payload.rejections.map((r, i) => ({ kind: 'rejection', index: i, rejection: r }));
  steps.push({ kind: 'final', status: payload.status });
  return steps;
}

/**
 * Frames for the replay. Each frame is [first, last] step indices, inclusive.
 * At speed 1 a frame lasts frameMs; the whole replay fits in maxMs. Every step belongs to exactly one frame.
 */
export function batch(stepCount, { frameMs = 600, maxMs = 10000 } = {}) {
  if (stepCount <= 0) return [];
  const maxFrames = Math.max(1, Math.floor(maxMs / frameMs));
  const per = Math.max(1, Math.ceil(stepCount / maxFrames));
  const frames = [];
  for (let i = 0; i < stepCount; i += per) frames.push([i, Math.min(stepCount - 1, i + per - 1)]);
  return frames;
}

/** Counter text for a frame. */
export function counterText([a, b], n) {
  return a === b ? `step ${a + 1} of ${n}` : `steps ${a + 1}–${b + 1} of ${n}`;
}

const sig = (h) => `${h.width} × ${h.height}`;

/**
 * For a RESOLVED revision result, what each revision step changed. Hypotheses come from the rejections whose source is the
 * probe name (the seed) or "revision:" + the path so far; the last one is the candidate. A missing step has before/after null.
 */
export function revisionDiffs(payload) {
  if (payload.status !== 'RESOLVED') return [];
  const c = payload.candidates[0];
  const path = c.revision_path;
  if (!path.length) return [];
  const find = (src) => payload.rejections.find((r) => r.source === src && r.hypothesis)?.hypothesis ?? null;
  const chain = [find(c.probe_name)];
  for (let k = 1; k < path.length; k++) chain.push(find('revision:' + path.slice(0, k).join('->')));
  chain.push(c);
  return path.map((name, k) => ({ step: name, before: chain[k], after: chain[k + 1] }));
}

/** Describe one change between two hypotheses, or null if either side is unknown. */
export function changeText(step, before, after) {
  if (!before || !after) return null;
  if (step === 'inclusive_bounds') return `${sig(before)} → ${sig(after)}`;
  if (step === 'rle_pcx') return `encoding ${before.encoding} → ${after.encoding}`;
  if (step === 'row_padding_variants') return `row alignment ${before.row_alignment} → ${after.row_alignment}`;
  return null;
}

/** The declared-versus-actual pair for a result whose revision path overrode the declared encoding. */
export function declaredVsActual(payload) {
  if (payload.status !== 'RESOLVED') return null;
  const c = payload.candidates[0];
  if (!c.revision_path.includes('rle_pcx')) return null;
  const rec = c.fields.find((f) => f.name === 'encoding');
  if (!rec) return null;
  const v = rec.value[0];
  const word = v === 0 ? 'none' : v === 1 ? 'rle_pcx' : String(v);
  return {
    declared: `${word} (byte ${'0x' + rec.offset.toString(16).toUpperCase().padStart(2, '0')} = 0x${Number(v).toString(16).toUpperCase().padStart(2, '0')})`,
    actual: c.encoding,
    offset: rec.offset,
    word,
  };
}

/** Closure line, worded exactly as the engine's pretty printer. */
export function closureLine(c) {
  if (c.encoding === 'rle_pcx') {
    return `closure: rle_pcx decoded [${c.data_start}, ${c.data_end}) to ${c.expected_decoded_bytes} bytes = ${c.row_stride} x ${c.height}, all input consumed`;
  }
  return `closure: [${c.data_start}, ${c.data_end}) holds ${c.data_end - c.data_start} bytes = ${c.row_stride} x ${c.height}`;
}

/** Largest integer scale at which a w × h image fits a box; at least 1. */
export function fitScale(w, h, boxW, boxH) {
  if (w <= 0 || h <= 0) return 1;
  return Math.max(1, Math.floor(Math.min(boxW / w, boxH / h)));
}

/** Displayed size: the integer scale, but never wider or taller than the box (a 64 × 1 still fits at scale 1). */
export function fitSize(w, h, boxW, boxH) {
  const s = fitScale(w, h, boxW, boxH);
  if (w * s <= boxW && h * s <= boxH) return { scale: s, width: w * s, height: h * s };
  const k = Math.min(boxW / w, boxH / h);                      // larger than the box even at 1: shrink, still nearest-neighbour
  return { scale: k, width: Math.max(1, Math.floor(w * k)), height: Math.max(1, Math.floor(h * k)) };
}
/** The largest nearest-neighbour size of a w × h image inside boxW × boxH, any scale, aspect kept: the image fills its frame. */
export function fillSize(w, h, boxW, boxH) {
  const k = Math.min(boxW / w, boxH / h);
  return { scale: k, width: Math.max(1, Math.floor(w * k)), height: Math.max(1, Math.floor(h * k)) };
}
// ---- UNRESOLVED_AMBIGUITY (Requirement 9) ----

export const escapeHTML = (s) => String(s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);

export function ambiguityStatement(n) {
  return `${n} readings fit these bytes exactly. The bytes cannot separate them, so NECROPSY does not choose.`;
}

// coherence.row_coherence: mean adjacent-row difference over the mean, lower is smoother. A heuristic; it never decides.
export const COHERENCE_NOTE =
  'The row similarity score on each card is a heuristic with known failure modes. It is shown for information only and does not choose between readings.';

export function coherenceText(c) {
  return c.coherence_status === 'scored' && typeof c.coherence_score === 'number'
    ? `row similarity score: ${c.coherence_score.toFixed(4)}`
    : `row similarity score: ${String(c.coherence_status).replace(/_/g, ' ')}`;
}

/** Card identity is the candidate's own geometry, never a rank. */
export const cardTitle = (c) => `${c.width} × ${c.height} · ${c.bit_depth}-bit · header ${c.header_size}`;

/**
 * Everything one ambiguity card shows. Same keys, same number of lines, for every candidate.
 * Nothing here depends on coherence except the coherence text itself.
 */
export function cardModel(c, index) {
  return {
    index,
    title: cardTitle(c),
    lines: [
      `${c.row_stride} byte${c.row_stride === 1 ? '' : 's'} per row` + (c.row_alignment > 1 ? `, padded to ${c.row_alignment}` : ''),
      c.encoding === 'none' ? 'no compression' : c.encoding === 'rle_pcx' ? 'PCX run-length' : c.encoding,
      c.data_end > c.data_start ? `data: bytes ${c.data_start} to ${c.data_end - 1}` : 'data: none',
    ],
    note: c.render && c.render.note ? c.render.note : '',
    failure: c.render && c.render.failure ? c.render.failure : '',
    coherence: coherenceText(c),
  };
}

/** Markup for one card. A pure function of the model; the image is painted into .well afterwards. */
export function cardHTML(m) {
  const well = m.failure ? `<p class="no-image">${escapeHTML(m.failure)}</p>` : '';
  return `<article class="card" id="card-${m.index}" tabindex="0" data-index="${m.index}" aria-label="${escapeHTML(m.title)}">`
    + `<div class="well card-well" data-index="${m.index}">${well}</div>`
    + `<h3 class="card-title mono">${escapeHTML(m.title)}</h3>`
    + m.lines.map((l) => `<p class="card-line mono">${escapeHTML(l)}</p>`).join('')
    + `<p class="card-note">${escapeHTML(m.note)}</p>`
    + `<p class="card-coh mono">${escapeHTML(m.coherence)}</p>`
    + `<div class="card-dl"><button type="button" class="dl-btn" data-act="png" data-index="${m.index}"${m.failure ? ' disabled title="no image to save"' : ''}>PNG</button>`
    + `<button type="button" class="dl-btn" data-act="data" data-index="${m.index}">data region</button></div>`
    + `</article>`;
}

/**
 * The at-a-glance grid (UI task 28): one identical tile per reading, in payload order, linking to its card.
 * A pure function of the payload. It shows no coherence at all, and no number but each tile's own size.
 */
export function ambGridHTML(payload) {
  return payload.candidates.map((c, i) => {
    const failure = c.render && c.render.failure ? `<span class="no-image">${escapeHTML(c.render.failure)}</span>` : '';
    return `<a class="amb-tile" href="#card-${i}" data-index="${i}" aria-label="${escapeHTML(cardTitle(c))}">`
      + `<span class="amb-well" data-index="${i}">${failure}</span>`
      + `<span class="amb-dims mono">${escapeHTML(`${c.width} × ${c.height} · ${c.bit_depth}-bit`)}</span></a>`;
  }).join('');
}

/** All cards in the payload's order, which is the engine's discovery order. */
export function cardsHTML(payload) {
  return payload.candidates.map((c, i) => cardHTML(cardModel(c, i))).join('');
}

// ---- FAILED (Requirement 10) ----

export function terminationText(t) {
  return {
    exhausted: 'Every layout within the search’s limits was tried, and none fits the data exactly.',
    no_hypothesis_checked: 'No layout reached the fit check.',
    deadline_exceeded: 'The search stopped at the 5 second deadline.',
    search_cap_exceeded: 'The search stopped at its 10,000-check cap.',
    input_too_short: 'The file is shorter than 3 bytes.',
    internal_error: 'The engine hit an internal error. The detail is below.',
  }[t] ?? t;
}

const STAGE_ORDER = ['probe', 'revision', 'generic', 'engine'];

/** Rejections grouped by stage, then reason, keeping the engine's order inside each group. */
export function failureGroups(rejections) {
  const stages = new Map();
  for (const r of rejections) {
    const s = stageOf(r.source);
    if (!stages.has(s)) stages.set(s, new Map());
    const byReason = stages.get(s);
    if (!byReason.has(r.reason)) byReason.set(r.reason, []);
    byReason.get(r.reason).push(r);
  }
  return STAGE_ORDER.filter((s) => stages.has(s)).map((s) => ({
    stage: s,
    count: [...stages.get(s).values()].reduce((a, l) => a + l.length, 0),
    reasons: [...stages.get(s)].map(([reason, items]) => ({ reason, count: items.length, items })),
  }));
}

export function rejectionLine(r) {
  const d = r.discrepancy === null || r.discrepancy === undefined ? '' : ` (discrepancy=${r.discrepancy})`;
  return `${r.source}: ${r.reason}${d}`;
}

export function hypothesisLine(h) {
  if (!h) return '';
  return `${h.width} × ${h.height} · ${h.bit_depth}-bit · header ${h.header_size} · align ${h.row_alignment} · ${h.encoding}`;
}
// ---- Outcome strip (Requirement 16) ----

/** The one line under a strip tile, filled from the payload. */
export function outcomeLine(payload) {
  if (payload.status === 'RESOLVED') return 'One reading fits the data exactly.';
  if (payload.status === 'UNRESOLVED_AMBIGUITY') return `${payload.candidates.length} readings fit, so NECROPSY does not choose.`;
  return 'No layout tried fits. Here is every one, and why.';
}


// ---- Downloads (Requirement 17) ----

/** Base name for downloads: the sample name, or the dropped file's name without extension, reduced to [A-Za-z0-9._-]. */
export function inputBase(name) {
  const stem = String(name || 'file').replace(/\.[^.]*$/, '') || 'file';
  return stem.replace(/[^A-Za-z0-9._-]+/g, '_').replace(/^_+|_+$/g, '') || 'file';
}

export function downloadNames(base, c) {
  const g = `${base}_${c.width}x${c.height}_${c.bit_depth}bit`;
  return { png: `${g}.png`, data: `${g}_data_${c.data_start}-${c.data_end}.bin` };
}

// ---- Several files dropped (Requirement 18) ----

/** null for a single file; otherwise the statement naming the examined file and every ignored one. */
export function multiDropNotice(names) {
  if (!names || names.length < 2) return null;
  const k = names.length, rest = names.slice(1);
  return `${k} files were dropped. NECROPSY examines one file at a time: it examined ${names[0]} and ignored ${k - 1} other${k - 1 === 1 ? '' : 's'}: ${rest.join(', ')}.`;
}
// ---- Error copy (Requirement 19): what happened and what to do next, from the actual cause ----

export const LIMIT_BYTES = 65536;
const n = (v) => Number(v).toLocaleString('en-US');

export const sizeMessage = (size) =>
  `That file is ${n(size)} bytes. The limit is ${n(LIMIT_BYTES)} bytes. Try a smaller file or a fragment of it.`;

export const emptyMessage = (name) =>
  `${name || 'The file'} is empty (0 bytes). There is nothing to examine. Choose a file that has content.`;

/** The sentence for the other files of a multi-file drop whose first file was refused (Requirement 18.3). */
export const unreadableMessage = (name) =>
  `${name || 'The file'} could not be read, so it was not examined. If it is a folder, drop a file from inside it instead.`;

export const othersNotExamined = (k) =>
  k > 1 ? ` The other ${k - 1} dropped file${k > 2 ? 's were' : ' was'} not examined.` : '';

export const serviceStatusMessage = (status) =>
  `The analysis service answered with HTTP ${status}. Your file was not examined. Try again.`;

export const UNREACHABLE_MESSAGE =
  'The analysis service could not be reached, so your file was not examined. Check your connection and try again.';

/** status: an HTTP status, or 0 when there was no connection. */
export const sampleFailMessage = (name, status) =>
  `The sample ${name} could not be loaded (${status ? `HTTP ${status}` : 'no connection'}). Try again, or drop a file of your own.`;

export const SAMPLE_LIST_FAIL = 'The sample list could not be loaded. You can still drop a file of your own.';

export const zipFailMessage = (status) => status
  ? `The download failed: the service answered with HTTP ${status}. Try again.`
  : 'The download failed: the service could not be reached. Try again.';

export const STOPPED_AT_LIMIT =
  'The search stopped at its limit before it could try everything. That does not mean no layout exists. The rejections below show what was tried before it stopped.';
// ---- FAILED sentence (Requirement 10.1, amended) ----

/**
 * The FAILED screen's sentence. When the search was exhausted and the rejections show a probe stage and no generic
 * stage, the probe's declarations bounded the search and Generic Search did not run (engine Decision Record 25).
 */
export function failureSentence(payload) {
  if (payload.termination === 'exhausted') {
    const rejections = payload.rejections || [];
    const stages = new Set(Object.keys(payload.rejection_counts || {}));
    for (const r of rejections) stages.add(stageOf(r.source));
    const probe = rejections.find((r) => stageOf(r.source) === 'probe');
    if (probe && stages.has('probe') && !stages.has('generic')) {
      return `The opening bytes match the ${probe.source.toUpperCase()} signature, so only layouts under its declarations were tried. The direct layout search did not run.`;
    }
  }
  return terminationText(payload.termination);
}

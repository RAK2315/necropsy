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
// Plain words for engine terms. One rule: TRANSLATE, NEVER DIAGNOSE.
// The UI may say in plain words what the engine found. It may not say what that implies about the file or its history.
// Every mapping names the engine function whose result it translates. Each was written from that code, not from
// what the term sounds like. The engine term itself stays on screen in a smaller `.tech` element.

// ---- Outcomes (engine.py: EngineResult.status) ----
export const CHIP = {
  RESOLVED: 'Recovered',
  UNRESOLVED_AMBIGUITY: 'Several readings fit',
  FAILED: 'Not recovered',
};

// ---- Rejection reasons (types.REASONS) ----
/** Plain words for one rejection. discrepancy is set only for arithmetic_mismatch. */
export function reasonText(reason, discrepancy) {
  switch (reason) {
    // closure.check_closure, encoding none: discrepancy = (data_end - header_size) - row_stride * height
    case 'arithmetic_mismatch':
      if (typeof discrepancy === 'number' && discrepancy > 0) return `the data is ${fmt(discrepancy)} byte${discrepancy === 1 ? '' : 's'} longer than this layout needs`;
      if (typeof discrepancy === 'number' && discrepancy < 0) return `the data is ${fmt(-discrepancy)} byte${discrepancy === -1 ? '' : 's'} shorter than this layout needs`;
      return 'the data is not the size this layout needs';
    // closure.rle_pcx_decode returns "overrun": a run would take the output past max_output_bytes
    case 'decoder_overrun': return 'a run would write past the size of the picture';
    // closure.rle_pcx_decode returns "underrun": the range ended (or a run marker was its last byte) before the output was full
    case 'decoder_underrun': return 'the data ran out before the picture was full';
    // closure.rle_pcx_decode returns "unconsumed": the output was full before the range ended
    case 'decoder_unconsumed': return 'decoding finished with bytes left over';
    // closure.check_closure: width, height or bit depth not positive, alignment not 1/2/4, header outside the file,
    // or a header field overlapping the data region
    case 'degenerate_hypothesis': return 'not a usable layout: a size is not positive, or the header overlaps the data';
    // closure.check_closure (data_end outside [header_size, len]), trailers.trailer_data_end, probes (TIFF offsets)
    case 'field_out_of_bounds': return 'a declared position lies outside the file';
    // probes.*: a declared value the format does not allow (for example a PCX encoding byte other than 0 or 1)
    case 'probe_precondition_failed': return 'a declared value is outside what the format allows';
    // closure.check_closure: an encoding other than none or rle_pcx
    case 'unsupported_encoding': return 'this encoding is recognised but not decoded';
    // engine.Engine._run_checked: len(data) < MIN_INPUT_BYTES
    case 'input_too_short': return 'the file is shorter than 3 bytes';
    // engine.Engine.run / closure.check_closure: an exception was caught
    case 'internal_error': return 'the engine hit an internal error';
    default: return reason;
  }
}

// ---- Revision steps (strategies.STRATEGIES) ----
/** Plain words for one correction. cand is the hypothesis after the step, for row_padding_variants' alignment. */
export function correctionText(step, cand) {
  // strategies.inclusive_bounds: width = xmax - xmin + 1, height = ymax - ymin + 1
  if (step === 'inclusive_bounds') return 'counted the header’s bounds inclusively (+1)';
  // strategies.rle_pcx: a PCX hypothesis with encoding none is tried as rle_pcx
  if (step === 'rle_pcx') return 'tried PCX run-length decoding';
  // strategies.row_padding_variants: row_alignment 2 and 4
  if (step === 'row_padding_variants') return cand && cand.row_alignment ? `tried rows padded to a multiple of ${cand.row_alignment} bytes` : 'tried rows padded to 2 or 4 bytes';
  return step;
}

// ---- Encodings (closure.check_closure) ----
export function encodingText(enc) {
  if (enc === 'none') return 'no compression';
  if (enc === 'rle_pcx') return 'PCX run-length';
  return enc;
}

// ---- Where a reading came from (engine.py stages; a probe's source is its format name) ----
export function sourceText(probeName) {
  // probes.*: the probe's signature check matched the opening bytes
  if (['pcx', 'tga', 'pbm', 'tiff'].includes(probeName)) return `Read as ${probeName.toUpperCase()}: the opening bytes match its signature.`;
  // generic.py: runs only when no probe matched; searches header size, width, height and bit depth
  if (probeName === 'generic') return 'No format signature matched, so it searched layouts directly.';
  return probeName;
}

/** Group heading for a stage of rejections (logic.stageOf). */
export function stageText(stage) {
  return {
    probe: 'Read from the header',              // probes.*
    revision: 'Corrections tried',              // strategies.* applied by engine._run
    generic: 'Layouts searched directly',       // generic.py
    engine: 'Engine',                           // engine.Engine.run guards
  }[stage] ?? stage;
}

// ---- Terminations (engine.py) ----
export function terminationPlain(t) {
  return {
    exhausted: 'every layout within the search’s limits was tried', // engine._exhausted with budget.checks > 0
    no_hypothesis_checked: 'no layout reached the check',              // engine._exhausted with budget.checks == 0
    deadline_exceeded: 'the search stopped at its 5 second deadline',   // budget.Budget deadline
    search_cap_exceeded: 'the search stopped at its 10,000-check cap',  // budget.Budget cap
    input_too_short: 'the file is shorter than 3 bytes',
    internal_error: 'the engine hit an internal error',
  }[t] ?? t;
}

// ---- The verdict: one sentence per result, used by the state line, the verdict heading and the replay's last step ----
export function verdictText(payload) {
  if (payload.status === 'RESOLVED') {
    const c = payload.candidates[0];
    return `Recovered: ${c.width} × ${c.height}, ${c.bit_depth}-bit`;
  }
  if (payload.status === 'UNRESOLVED_AMBIGUITY') return `${payload.candidates.length} readings fit exactly. NECROPSY does not choose.`;
  const t = payload.termination;
  if ((payload.partial_candidates || []).length) return 'Not recovered: the search stopped before it could decide';
  if (t === 'deadline_exceeded' || t === 'search_cap_exceeded') return `Not recovered: ${terminationPlain(t)}, and no layout tried so far fits`;
  if (t === 'no_hypothesis_checked') return 'Not recovered: no layout reached the check';
  if (t === 'input_too_short' || t === 'internal_error') return `Not recovered: ${terminationPlain(t)}`;
  return 'Not recovered: no layout tried fits the data exactly';
}

/** "Bytes a to b-1" for a half-open range [a, b). */
export const rangeText = (a, b) => (b > a ? `bytes ${fmt(a)} to ${fmt(b - 1)}` : 'no bytes');

/** Why a reading fits, in plain words, from closure.check_closure's accepted values. */
export function proofText(c) {
  const n = c.data_end - c.data_start;
  const rows = `${fmt(c.height)} rows of ${fmt(c.row_stride)} bytes`;
  if (c.encoding === 'rle_pcx') {
    return `The ${fmt(n)} data bytes decode to exactly ${fmt(c.expected_decoded_bytes)} bytes: ${rows}. Every data byte is used.`;
  }
  return `The ${fmt(n)} data bytes are exactly ${rows}. No byte is left over.`;
}

/** The plain line for one rejected layout. */
export function rejectionPlain(r) {
  const h = r.hypothesis;
  const what = h ? `${h.width} × ${h.height}, ${h.bit_depth}-bit, header ${fmt(h.header_size)} bytes` : 'The format’s own declarations';
  return `${what}: ${reasonText(r.reason, r.discrepancy)}`;
}

function fmt(v) { return Number(v).toLocaleString('en-US'); }

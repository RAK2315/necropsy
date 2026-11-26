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
    // closure.rle_pcx_decode and decoders.DECODERS return "overrun": the next write would take the output past max_output_bytes
    case 'decoder_overrun': return 'unpacking would write past the size of the picture';
    // closure.rle_pcx_decode and decoders.DECODERS return "underrun": the range ended before the output was full
    case 'decoder_underrun': return 'the data ran out before the picture was full';
    // closure.rle_pcx_decode and decoders.DECODERS return "unconsumed": the output was full before the range ended
    case 'decoder_unconsumed': return 'decoding finished with bytes left over';
    // decoders.DECODERS return "malformed": a byte, token or code the encoding gives no meaning (detail says which)
    case 'decoder_malformed': return 'the data holds something its encoding gives no meaning';
    // decoders._run_pnm_text "above_maxval", closure.check_closure (P5/P6): a sample is greater than the declared maximum value
    case 'sample_above_maxval': return 'a value is above the maximum the file declares';
    // closure.check_closure: width, height or bit depth not positive, alignment not 1/2/4, header outside the file,
    // or a header field overlapping the data region
    case 'degenerate_hypothesis': return 'not a usable layout: a size is not positive, or the header overlaps the data';
    // closure.check_closure (data_end outside [header_size, len]), trailers.trailer_data_end, probes (TIFF offsets)
    case 'field_out_of_bounds': return 'a declared position lies outside the file';
    // probes.*: a declared value the format does not allow (for example a PCX encoding byte other than 0 or 1)
    case 'probe_precondition_failed': return 'a declared value is outside what the format allows';
    // closure.check_closure: an encoding that is neither none, rle_pcx nor in decoders.DECODERS
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
  if (enc === 'rle_tga') return 'TGA run-length';                       // decoders._run_rle_tga
  if (enc === 'pnm_text') return 'numbers written as text';             // decoders._run_pnm_text
  if (enc === 'tiff_compression_32773') return 'PackBits';              // decoders._run_packbits
  if (enc === 'tiff_compression_5') return 'LZW';                       // decoders._run_lzw_tiff
  if (enc === 'tiff_compression_8' || enc === 'tiff_compression_32946') return 'Deflate';   // decoders._run_deflate_zlib
  if (enc === 'tiff_compression_34925') return 'LZMA';                  // decoders._run_lzma_xz
  if (typeof enc === 'string' && enc.startsWith('tiff_compression_')) return `TIFF compression ${enc.slice(17)}`;
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

/** What a stage of rejections is, in one line (UI task 42; engine._run's stages, logic.stageOf). */
export function stageExplain(stage) {
  return {
    probe: 'Layouts taken straight from what the file declares.',                              // probes.*
    revision: 'The same layouts with standard corrections applied, alone and together.',      // strategies.*
    generic: 'Layouts guessed from the file’s size alone, with no format recognised.',         // generic.py
    engine: 'Checks the engine runs before any layout.',                                       // engine.Engine.run guards
  }[stage] ?? '';
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

/**
 * The state line under the header (UI task 25): which file, which stage, whether anything is running, and the verdict.
 * s = { phase: 'idle' | 'sending' | 'replaying' | 'done' | 'error', name, size, payload, step, of, reason }
 */
export function stateText(s) {
  const file = s.name ? (s.size === undefined ? s.name : `${s.name} · ${fmt(s.size)} bytes`) : '';
  const join = (...p) => p.filter(Boolean).join(' · ');
  switch (s.phase) {
    case 'sending': return join(file, 'Examining…');
    case 'replaying': return join(file, `Finished in ${fmt(s.payload.engine_ms)} ms`, `Replaying the search: step ${s.step} of ${s.of}`);
    case 'done': return join(file, verdictText(s.payload));
    case 'error': return join(s.name || '', `Not examined: ${s.reason}`);
    default: return 'No file loaded. Try a sample or drop your own.';
  }
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

/**
 * One tried layout, short: size, depth, header, and whatever else sets it apart from its neighbours in the list (row
 * padding from strategies.row_padding_variants, the encoding from the probe or strategies.rle_pcx). Without the last
 * two, attempts that differ only in padding or encoding read as the same line twice (UI task 51).
 */
export function layoutShort(h) {
  const pad = h.row_alignment > 1 ? `, rows padded to ${h.row_alignment} bytes` : '';
  const enc = h.encoding && h.encoding !== 'none' ? `, ${encodingText(h.encoding)}` : '';
  return `${h.width} × ${h.height}, ${h.bit_depth}-bit, header ${fmt(h.header_size)} bytes${pad}${enc}`;
}

/** The plain line for one rejected layout. */
export function rejectionPlain(r) {
  const h = r.hypothesis;
  const what = h ? layoutShort(h) : 'The format’s own declarations';
  return `${what}: ${reasonText(r.reason, r.discrepancy)}`;
}

// ---- Explanations (UI task 42, Rehaan): what each finding means, for a reader who has never looked inside a file ----
// Same rule: they explain the check the engine ran and what it found, never what that implies about the file's history.

const bits = (n) => `${n} bit${n === 1 ? '' : 's'}`;
const bytesWord = (n) => `${fmt(n)} byte${n === 1 ? '' : 's'}`;

/** One layout in words: hypothesis or candidate fields (width, height, bit_depth, header_size). */
export function layoutWords(h) {
  return `a ${fmt(h.width)} × ${fmt(h.height)} picture at ${bits(h.bit_depth)} per pixel, after a ${fmt(h.header_size)}-byte header`;
}

/** Where a tried layout came from. rejection.source is the probe's format name, "revision:<step->step>" or "generic" (engine._run). */
export function sourceExplain(source, h) {
  if (source === 'generic') return 'No format matched, so the engine tried a layout directly:';           // generic.py
  if (source && source.startsWith('revision:')) {                                                          // strategies.* in engine._run
    const steps = source.slice('revision:'.length).split('->');
    return `With ${steps.length === 1 ? 'a correction' : 'corrections'} (${steps.map((s) => correctionText(s, h)).join(', then ')}), the engine tried`;
  }
  return 'The engine tried what the file declares:';                                                        // probes.*: the probe's own reading
}

/** Why a layout was set aside, in a sentence or two. Same sources as reasonText. */
export function reasonExplain(reason, d) {
  switch (reason) {
    case 'arithmetic_mismatch':        // closure.check_closure: discrepancy = data bytes - row bytes × height
      if (typeof d === 'number' && d > 0) return `The picture data is ${bytesWord(d)} longer than a picture this size needs. A layout is accepted only if it uses every byte, so this one is set aside.`;
      if (typeof d === 'number' && d < 0) return `The picture data is ${bytesWord(-d)} shorter than a picture this size needs, so it could not be filled.`;
      return 'The picture data is not the size this layout needs, so it cannot be used up exactly.';
    case 'decoder_overrun':            // closure.rle_pcx_decode, decoders.DECODERS "overrun"
      return 'The data was unpacked using the encoding this layout names. It produced more pixels than a picture this size holds, so this size does not fit.';
    case 'decoder_underrun':           // closure.rle_pcx_decode, decoders.DECODERS "underrun"
      return 'Unpacking the data used up every byte before a picture this size was full.';
    case 'decoder_unconsumed':         // closure.rle_pcx_decode, decoders.DECODERS "unconsumed"
      return 'Unpacking the data filled a picture this size with stored bytes still unused. A layout must use every byte.';
    case 'decoder_malformed':          // decoders.DECODERS "malformed"
      return 'While unpacking, the data held a byte, number or code that its encoding gives no meaning, so unpacking stopped there.';
    case 'sample_above_maxval':        // decoders._run_pnm_text "above_maxval"; closure.check_closure for P5/P6
      return 'The file declares the largest value a pixel may have. A pixel value here is larger than that, so this reading does not fit.';
    case 'degenerate_hypothesis':      // closure.check_closure
      return 'These numbers cannot describe a picture: a size is zero or less, or the header would overlap the pixels.';
    case 'field_out_of_bounds':        // closure.check_closure, trailers.trailer_data_end, TIFF offsets
      return 'A position the file gives, such as where its data starts or ends, lies outside the file.';
    case 'probe_precondition_failed':  // probes.*
      return 'A value the file states is one its format does not allow, so reading it as that format stops here.';
    case 'unsupported_encoding':       // closure.check_closure
      return 'The file names a compression NECROPSY recognises but does not unpack.';
    default: return reasonText(reason, d) + '.';
  }
}

/** The explanation of one replay step (logic.buildSteps, live.js), for the caption and the "Explain every step" view. */
export function stepExplain(payload, step) {
  if (step.kind === 'rejection') {
    const r = step.rejection, h = r.hypothesis;
    const what = h ? `${sourceExplain(r.source, h)} ${layoutWords(h)}.` : 'The engine read the format’s own declarations.';
    return `${what} ${reasonExplain(r.reason, r.discrepancy)}`;
  }
  if (step.kind === 'fit') return `The engine tried ${layoutWords(step.candidate)}. It uses every byte of the picture data exactly, so it fits.`;
  if (payload.status === 'RESOLVED') {
    const first = payload.rejections.length === 0 ? ' It was the first layout tried.' : '';
    return `The engine tried ${layoutWords(payload.candidates[0])}. It uses every byte of the picture data exactly, so it is accepted.${first}`;
  }
  if (payload.status === 'UNRESOLVED_AMBIGUITY') {
    return `Each of these ${payload.candidates.length} layouts uses every byte exactly, and nothing in the bytes separates them, so NECROPSY shows them all and does not choose.`;
  }
  return 'No layout tried used the data exactly, so nothing is recovered, rather than a guess.';
}

/** Why the accepted reading fits, worked through (closure.check_closure's accepted values). */
export function proofExplain(c) {
  const n = c.data_end - c.data_start;
  const pad = c.row_alignment > 1 ? `, padded to a multiple of ${c.row_alignment}` : '';
  const row = `Each row is ${fmt(c.width)} pixels at ${bits(c.bit_depth)}, which takes ${bytesWord(c.row_stride)}${pad}.`;
  if (c.encoding === 'rle_pcx') {
    return `${row} The picture data is stored as run-length data (a repeated byte stored once with a count). Unpacked, its ${fmt(n)} stored bytes become exactly ${fmt(c.height)} rows × ${bytesWord(c.row_stride)} = ${bytesWord(c.expected_decoded_bytes)}, and unpacking ends on the last stored byte. A different size would overflow or leave bytes unused.`;
  }
  return `${row} ${fmt(c.height)} rows × ${bytesWord(c.row_stride)} = ${bytesWord(c.height * c.row_stride)}: exactly the picture data, ${rangeText(c.data_start, c.data_end)}. A different size would leave bytes over or run short.`;
}

/** What one correction did, in plain words (strategies.*). before and after are the hypotheses around the step. */
export function correctionExplain(step, before, after) {
  if (step === 'inclusive_bounds') {           // strategies.inclusive_bounds: width = xmax - xmin + 1
    const was = before ? `${fmt(before.width)} × ${fmt(before.height)}` : 'one pixel short';
    const now = after ? `${fmt(after.width)} × ${fmt(after.height)}` : 'one pixel more';
    return `The file gives the picture’s first and last pixel positions. Subtracting them gives ${was}; counting both ends gives ${now}.`;
  }
  if (step === 'rle_pcx') {                    // strategies.rle_pcx: encoding none -> rle_pcx
    return 'Read as stored without compression, the data does not fit. Read as PCX run-length data, where a repeated byte is stored once with a count, it does.';
  }
  if (step === 'row_padding_variants') {       // strategies.row_padding_variants: row_alignment 2 or 4
    const a = after && after.row_alignment;
    return `Each row is read as padded with unused bytes up to a multiple of ${a || '2 or 4'} bytes.`;
  }
  return step;
}

/** What a recognised trailer is (trailers.TRAILER_REGISTRY), and why its bytes are not pixels. */
export function trailerExplain(name, n) {
  if (name === 'pcx_palette_256') return `The last ${bytesWord(n)} are a 256-colour palette, the colours the pixel values point to, stored after the pixels. They are not read as pixels.`;
  if (name === 'tga2_footer') return `The last ${bytesWord(n)} are a TGA 2.0 footer, a signature with pointers to extra information. They are not read as pixels.`;
  return `The last ${bytesWord(n)} are read as a trailer, not pixels.`;
}

/**
 * What a header field holds, in plain words (UI task 42). The names are the ones probes.py gives the values it reads
 * (probes.read(data, name, ...)); each line says what the field states, not what the engine concluded from it.
 */
const FIELD_PLAIN = {
  magic: 'the signature that names the format',
  width: 'width in pixels', height: 'height in pixels',
  bit_depth: 'bits per pixel', bits_per_sample: 'bits per colour sample', samples_per_pixel: 'colour samples per pixel',
  encoding: 'compression (0 none, 1 run-length)', compression: 'compression scheme',
  xmin: 'first column', ymin: 'first row', xmax: 'last column', ymax: 'last row', bounds: 'first and last column and row',
  planes: 'colour planes', bytes_per_line: 'bytes per row, as stored',
  id_length: 'length of the text label before the pixels', color_map_type: 'whether a palette is present',
  image_type: 'kind of picture and compression', color_map_length: 'colours in the palette',
  color_map_entry_size: 'bits per palette colour', image_descriptor: 'row order and alpha bits',
  byte_order: 'byte order (II or MM)', ifd_offset: 'where the first directory of values starts',
  ifd_entry_count: 'how many values the directory holds', tag: 'which value this entry gives', type: 'how the value is stored',
  count: 'how many items the value has', photometric_interpretation: 'how pixel values map to colour',
  planar_configuration: 'whether colour samples are interleaved', strip_offset: 'where the pixel data starts',
  strip_byte_count: 'how many bytes of pixel data', bits_per_sample_offset: 'where the bits per sample are stored',
};
export function fieldPlain(name) {
  return FIELD_PLAIN[name] || '';
}

function fmt(v) { return Number(v).toLocaleString('en-US'); }

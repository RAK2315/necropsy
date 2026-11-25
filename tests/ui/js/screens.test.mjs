// Ambiguity neutrality (Requirement 9.4, 9.6, 9.14) and FAILED grouping (Requirement 10.4, 10.5).
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import * as L from '../../../public/js/logic.js';

const cand = (w, h, bd, hdr, coh) => ({
  width: w, height: h, bit_depth: bd, header_size: hdr, row_alignment: 1, row_stride: Math.ceil(w * bd / 8),
  encoding: 'none', data_start: hdr, data_end: hdr + 64, coherence_method: 'row_mad_ratio', ...coh,
  render: { width: w, height: h, channels: 'grey8', data_b64: '', note: `${bd}-bit · grey · rows shown in stored order` },
  fields: [],
});
const geometry = [[8, 8, 8, 40], [64, 8, 1, 40], [1, 64, 8, 40], [64, 1, 8, 40]];
const payloadWith = (cohs) => ({ status: 'UNRESOLVED_AMBIGUITY', candidates: geometry.map((g, i) => cand(...g, cohs[i])) });

const scored = [0.11, 0.97, 0.42, null].map((s) => (s === null ? { coherence_score: null, coherence_status: 'unscorable' }
  : { coherence_score: s, coherence_status: 'scored' }));
const reversed = [0.97, 0.11, null, 0.42].map((s) => (s === null ? { coherence_score: null, coherence_status: 'not_computed' }
  : { coherence_score: s, coherence_status: 'scored' }));
const mask = (html) => html.replace(/<dd class="card-coh">[^<]*<\/dd>/g, '<dd class="card-coh">#</dd>');

test('cards are identical apart from the coherence text, whatever the coherence values', () => {
  const a = L.cardsHTML(payloadWith(scored));
  const b = L.cardsHTML(payloadWith(reversed));
  assert.notEqual(a, b);                     // the coherence text itself does differ
  assert.equal(mask(a), mask(b));            // and nothing else does: layout, order, classes, emphasis
});

test('cards keep the payload order and carry no rank', () => {
  const html = L.cardsHTML(payloadWith(scored));
  const titles = [...html.matchAll(/aria-label="([^"]*)"/g)].map((m) => m[1]);   // UI task 47: the full identity stays in the label
  assert.deepEqual(titles, geometry.map(([w, h, bd, hdr]) => `${w} × ${h} · ${bd}-bit · header ${hdr}`));
  for (const word of ['best', 'likely', 'selected', 'recommended', 'preferred', '#1', 'rank', 'aria-pressed="true"']) {
    assert.ok(!html.toLowerCase().includes(word.toLowerCase()), word);
  }
  // every card has the same structure: same class sequence
  const shape = (card) => [...card.matchAll(/class="([^"]*)"/g)].map((m) => m[1]).join('|');
  const cards = html.split('</article>').filter(Boolean);
  assert.equal(new Set(cards.map(shape)).size, 1);
});

test('coherence text formats', () => {
  // UI task 26: plain words; the method name (row_mad_ratio) is shown once, in .tech, under the cards
  assert.equal(L.coherenceText({ coherence_status: 'scored', coherence_score: 0.123456, coherence_method: 'row_mad_ratio' }),
    'row similarity score: 0.1235');
  assert.equal(L.coherenceText({ coherence_status: 'unscorable', coherence_score: null }), 'row similarity score: unscorable');
  assert.equal(L.coherenceText({ coherence_status: 'not_computed', coherence_score: null }), 'row similarity score: not computed');
});

test('a render failure sits in the same well as an image', () => {
  const c = { ...cand(8, 8, 16, 40, scored[0]), render: { failure: 'no renderer for 16-bit pixels' } };
  const html = L.cardHTML(L.cardModel(c, 0));
  assert.match(html, /<div class="well card-well" data-index="0"><p class="no-image">no renderer for 16-bit pixels<\/p><\/div>/);
});

test('the statement leads and states the count', () => {
  assert.equal(L.ambiguityStatement(3), '3 readings fit these bytes exactly. The bytes cannot separate them, so NECROPSY does not choose.');
});

test('no stylesheet rule singles out one card by position', () => {
  const css = readFileSync(new URL('../../../public/app.css', import.meta.url), 'utf8');
  assert.ok(!/\.card:(first|last|nth)-/.test(css));
});

test('failureGroups keeps engine order within stage and reason', () => {
  const rs = [
    { source: 'pcx', reason: 'decoder_unconsumed' },
    { source: 'revision:inclusive_bounds', reason: 'decoder_underrun', discrepancy: null },
    { source: 'revision:row_padding_variants', reason: 'arithmetic_mismatch', discrepancy: 4 },
    { source: 'revision:inclusive_bounds->rle_pcx', reason: 'decoder_underrun' },
  ];
  const g = L.failureGroups(rs);
  assert.deepEqual(g.map((x) => [x.stage, x.count]), [['probe', 1], ['revision', 3]]);
  assert.deepEqual(g[1].reasons.map((r) => [r.reason, r.count]), [['decoder_underrun', 2], ['arithmetic_mismatch', 1]]);
  assert.deepEqual(g[1].reasons[0].items.map((r) => r.source), ['revision:inclusive_bounds', 'revision:inclusive_bounds->rle_pcx']);
  assert.equal(L.rejectionLine(rs[2]), 'revision:row_padding_variants: arithmetic_mismatch (discrepancy=4)');
  assert.equal(L.rejectionLine(rs[0]), 'pcx: decoder_unconsumed');
});

test('termination text never claims the file has no valid layout', () => {
  for (const t of ['exhausted', 'no_hypothesis_checked', 'deadline_exceeded', 'search_cap_exceeded', 'input_too_short', 'internal_error']) {
    assert.notEqual(L.terminationText(t), t, `no sentence for ${t}`);
    assert.ok(!/no valid layout|not an image|cannot be (read|opened)/i.test(L.terminationText(t)), t);
  }
});
test('a render-failure card keeps both download controls, with PNG disabled (Requirement 17.6)', () => {
  const ok = L.cardHTML(L.cardModel(cand(8, 8, 8, 40, scored[0]), 0));
  const bad = L.cardHTML(L.cardModel({ ...cand(8, 8, 16, 40, scored[0]), render: { failure: 'no renderer for 16-bit pixels' } }, 0));
  assert.match(ok, /<button type="button" class="dl-btn" data-act="png" data-index="0">PNG<\/button>/);
  assert.match(bad, /<button type="button" class="dl-btn" data-act="png" data-index="0" disabled title="no image to save">PNG<\/button>/);
  for (const h of [ok, bad]) assert.match(h, /data-act="data" data-index="0">data region<\/button>/);
});

test('download names (Requirement 17.5)', () => {
  const c = { width: 64, height: 48, bit_depth: 8, data_start: 128, data_end: 393 };
  assert.deepEqual(L.downloadNames(L.inputBase('external_a'), c), { png: 'external_a_64x48_8bit.png', data: 'external_a_64x48_8bit_data_128-393.bin' });
  assert.equal(L.inputBase('Holiday Photo (1).PCX'), 'Holiday_Photo_1');
  assert.equal(L.inputBase(''), 'file');
  assert.equal(L.inputBase(undefined), 'file');
});
// ---- UI task 28 (Claude Code): the at-a-glance grid passes the same neutrality test as the cards, more strictly ----

test('the grid shows no coherence at all: swapping the coherence values leaves its markup identical', () => {
  const a = L.ambGridHTML(payloadWith(scored));
  const b = L.ambGridHTML(payloadWith(reversed));
  assert.equal(a, b);                                   // identical outright, not identical after masking
  assert.equal(a, L.ambGridHTML(payloadWith(scored)));  // and a pure function of the payload
  assert.ok(!/coher|similar|score|row_mad/i.test(a));
});

test('every grid tile has the same structure, keeps payload order and carries no rank', () => {
  const html = L.ambGridHTML(payloadWith(scored));
  const tiles = html.split('</a>').filter(Boolean);
  assert.equal(tiles.length, geometry.length);
  const shape = (t) => [...t.matchAll(/class="([^"]*)"/g)].map((m) => m[1]).join('|');
  assert.equal(new Set(tiles.map(shape)).size, 1);
  const labels = [...html.matchAll(/aria-label="([^"]*)"/g)].map((m) => m[1]);
  assert.deepEqual(labels, geometry.map(([w, h, bd, hdr]) => `${w} × ${h} · ${bd}-bit · header ${hdr}`));
  const shown = [...html.matchAll(/<span class="amb-dims mono">([^<]*)<\/span>/g)].map((m) => m[1]);
  assert.deepEqual(shown, geometry.map(([w, h, bd]) => `${w} × ${h} · ${bd}-bit`));   // no number but the tile's own size
  for (const word of ['best', 'likely', 'selected', 'recommended', 'preferred', '#1', 'rank', 'aria-pressed', 'aria-current', 'checked']) {
    assert.ok(!html.toLowerCase().includes(word.toLowerCase()), word);
  }
  assert.deepEqual([...html.matchAll(/href="#card-(\d+)"/g)].map((m) => Number(m[1])), geometry.map((_, i) => i));
});

test('a grid tile with no preview is the same tile, with the reason', () => {
  const p = payloadWith(scored);
  p.candidates[1] = { ...p.candidates[1], render: { failure: 'no renderer for 16-bit pixels' } };
  const html = L.ambGridHTML(p);
  const tiles = html.split('</a>').filter(Boolean);
  assert.match(tiles[1], /<span class="amb-well" data-index="1"><span class="no-image">no renderer for 16-bit pixels<\/span><\/span>/);
  const outer = (t) => t.match(/^<a class="([^"]*)"/)[1];
  assert.equal(new Set(tiles.map(outer)).size, 1);
});

test('no stylesheet rule singles out one grid tile by position', () => {
  const css = readFileSync(new URL('../../../public/app.css', import.meta.url), 'utf8');
  assert.ok(!/\.amb-(tile|well)[^{]*:(first|last|nth)-/.test(css));
});

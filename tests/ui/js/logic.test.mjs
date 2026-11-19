import test from 'node:test';
import assert from 'node:assert/strict';
import * as L from '../../../public/js/logic.js';

const rec = (name, offset, fmt, value) => ({ name, offset, fmt, value });

test('calcsize and fieldRange', () => {
  assert.equal(L.calcsize('B'), 1);
  assert.equal(L.calcsize('<H'), 2);
  assert.equal(L.calcsize('>I'), 4);
  assert.equal(L.calcsize('<i'), 4);
  assert.equal(L.calcsize('3s'), 3);
  assert.equal(L.calcsize('2s'), 2);
  assert.deepEqual(L.fieldRange(rec('ifd', 4, '>I', [8])), [4, 8]);
});

test('regions: trailer only when matched', () => {
  const c = { data_start: 128, data_end: 186, trailer: 'pcx_palette_256' };
  assert.deepEqual(L.regions(c, 955), { header: [0, 128], data: [128, 186], trailer: { name: 'pcx_palette_256', range: [186, 955] } });
  assert.equal(L.regions({ ...c, trailer: null }, 955).trailer, null);
});

test('byteRoles: equivalent reads of mystery_f stay separate and overlap', () => {
  const fields = [rec('width', 0, '<H', [12]), rec('width', 0, '<I', [12]), rec('width', 0, '<i', [12]), rec('height', 4, '<H', [10])];
  const { records, byByte } = L.byteRoles([{ fields }]);
  assert.equal(records.length, 4);
  assert.deepEqual(byByte.get(0), [0, 1, 2]);
  assert.deepEqual(byByte.get(2), [1, 2]);
  assert.deepEqual(byByte.get(4), [3]);
  assert.equal(byByte.has(6), false);
  assert.deepEqual([...L.equivalentNames(fields)], ['width']);
});

test('byteRoles: union over candidates names every user', () => {
  const a = { fields: [rec('width', 4, '<i', [8])] };
  const b = { fields: [rec('width', 4, '<i', [8]), rec('height', 8, '<i', [8])] };
  const { records } = L.byteRoles([a, b]);
  assert.deepEqual(records.map((r) => r.users), [[0, 1], [1]]);
});

test('buildSteps keeps payload order and adds only the final step', () => {
  const p = { status: 'RESOLVED', rejections: [{ source: 'pcx' }, { source: 'revision:a' }, { source: 'revision:b' }] };
  const s = L.buildSteps(p);
  assert.equal(s.length, 4);
  assert.deepEqual(s.slice(0, 3).map((x) => x.rejection.source), ['pcx', 'revision:a', 'revision:b']);
  assert.equal(s[3].kind, 'final');
});

test('batch: bounded to 10 s at 1x, contiguous, every step once, exact counter', () => {
  for (const n of [1, 2, 16, 17, 100, 212, 9999]) {
    const frames = L.batch(n);
    assert.ok(frames.length * 600 <= 10000, `n=${n}`);
    let next = 0;
    for (const [a, b] of frames) { assert.equal(a, next); assert.ok(b >= a); next = b + 1; }
    assert.equal(next, n);
  }
  assert.deepEqual(L.batch(3), [[0, 0], [1, 1], [2, 2]]);
  assert.equal(L.counterText([0, 0], 4), 'step 1 of 4');
  assert.equal(L.counterText([40, 79], 212), 'steps 41–80 of 212');
  assert.deepEqual(L.batch(0), []);
});

test('stageOf', () => {
  assert.deepEqual(['pcx', 'tiff', 'revision:x->y', 'generic', 'engine'].map(L.stageOf), ['probe', 'probe', 'revision', 'generic', 'engine']);
});

const H = (w, h, extra = {}) => ({ width: w, height: h, encoding: 'none', row_alignment: 1, ...extra });

const lying = {
  status: 'RESOLVED',
  rejections: [
    { source: 'pcx', hypothesis: H(7, 7) },
    { source: 'revision:inclusive_bounds', hypothesis: H(8, 8) },
    { source: 'revision:rle_pcx', hypothesis: H(7, 7, { encoding: 'rle_pcx' }) },
  ],
  candidates: [{ ...H(8, 8, { encoding: 'rle_pcx' }), probe_name: 'pcx', revision_path: ['inclusive_bounds', 'rle_pcx'],
    fields: [rec('encoding', 2, 'B', [0])], data_start: 128, data_end: 186, expected_decoded_bytes: 64, row_stride: 8 }],
};

test('revisionDiffs takes hypotheses from rejections and never reconstructs', () => {
  const d = L.revisionDiffs(lying);
  assert.deepEqual(d.map((x) => x.step), ['inclusive_bounds', 'rle_pcx']);
  assert.equal(L.changeText(d[0].step, d[0].before, d[0].after), '7 × 7 → 8 × 8');
  assert.equal(L.changeText(d[1].step, d[1].before, d[1].after), 'encoding none → rle_pcx');
  const missing = { ...lying, rejections: [lying.rejections[0]] };
  const d2 = L.revisionDiffs(missing);
  assert.equal(d2[1].before, null);
  assert.equal(L.changeText(d2[1].step, d2[1].before, d2[1].after), null);
});

test('declaredVsActual for the lying header', () => {
  assert.deepEqual(L.declaredVsActual(lying), { declared: 'none (byte 0x02 = 0x00)', actual: 'rle_pcx', offset: 2 });
  const plain = { ...lying, candidates: [{ ...lying.candidates[0], revision_path: ['inclusive_bounds'] }] };
  assert.equal(L.declaredVsActual(plain), null);
});

test('closureLine matches the pretty printer wording', () => {
  assert.equal(L.closureLine(lying.candidates[0]), 'closure: rle_pcx decoded [128, 186) to 64 bytes = 8 x 8, all input consumed');
  assert.equal(L.closureLine({ encoding: 'none', data_start: 18, data_end: 786, row_stride: 48, height: 16 }), 'closure: [18, 786) holds 768 bytes = 48 x 16');
});

test('valueText', () => {
  assert.equal(L.valueText(rec('w', 0, '<H', [12])), '12');
  assert.equal(L.valueText(rec('m', 0, '3s', [{ bytes: '50340a' }])), "b'P4\\x0a'");
});

test('fitScale and fitSize', () => {
  assert.equal(L.fitScale(8, 8, 224, 224), 28);
  assert.equal(L.fitScale(64, 1, 224, 224), 3);
  assert.deepEqual(L.fitSize(64, 1, 224, 224), { scale: 3, width: 192, height: 3 });
  assert.equal(L.fitSize(500, 10, 224, 224).width, 224);
});
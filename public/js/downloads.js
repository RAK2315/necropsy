// Downloads of recovered output (Requirement 17), built in the browser from data the page already holds.
import { toImageData } from './image.js';
import { downloadNames } from './logic.js';

function save(blob, name) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = name;
  document.body.append(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 10000);
}

/** The candidate's pixel buffer as a PNG at native size: one PNG pixel per image pixel, every pixel opaque. */
export function savePNG(cand, base) {
  if (!cand.render || !cand.render.data_b64) return;
  const c = document.createElement('canvas');
  c.width = cand.render.width;
  c.height = cand.render.height;
  c.getContext('2d').putImageData(toImageData(cand.render), 0, 0);
  c.toBlob((blob) => save(blob, downloadNames(base, cand).png), 'image/png');
}

/** Exactly the examined file's bytes [data_start, data_end), as stored. */
export function saveData(cand, bytes, base) {
  save(new Blob([bytes.slice(cand.data_start, cand.data_end)], { type: 'application/octet-stream' }), downloadNames(base, cand).data);
}

/** The two controls for the RESOLVED screen. */
export function downloadRow(cand, bytes, base) {
  const row = document.createElement('div');
  row.className = 'card-dl';
  const png = document.createElement('button');
  png.type = 'button'; png.className = 'dl-btn'; png.dataset.act = 'png'; png.textContent = 'PNG';
  if (!cand.render || !cand.render.data_b64) { png.disabled = true; png.title = 'no image to save'; }
  const data = document.createElement('button');
  data.type = 'button'; data.className = 'dl-btn'; data.dataset.act = 'data'; data.textContent = 'data region';
  png.addEventListener('click', () => savePNG(cand, base));
  data.addEventListener('click', () => saveData(cand, bytes, base));
  row.append(png, data);
  return row;
}
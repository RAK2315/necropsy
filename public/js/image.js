// Paint a pixel buffer from the payload to a canvas, nearest-neighbour, integer scale, optional row reveal.
import { fitSize } from './logic.js';

function decodeB64(s) {
  const bin = atob(s);
  const out = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
  return out;
}

export const prefersReducedMotion = () => window.matchMedia('(prefers-reduced-motion: reduce)').matches;

/** Fill an ImageData from a grey8 or rgb8 buffer. */
function toImageData(render) {
  const { width: w, height: h, channels } = render;
  const src = decodeB64(render.data_b64);
  const img = new ImageData(w, h);
  const d = img.data;
  if (channels === 'grey8') {
    for (let i = 0, j = 0; i < w * h; i++, j += 4) { const v = src[i]; d[j] = d[j + 1] = d[j + 2] = v; d[j + 3] = 255; }
  } else {
    for (let i = 0, s = 0, j = 0; i < w * h; i++, s += 3, j += 4) { d[j] = src[s]; d[j + 1] = src[s + 1]; d[j + 2] = src[s + 2]; d[j + 3] = 255; }
  }
  return img;
}

/**
 * Draw render into a new canvas sized to fit boxW × boxH. Returns { canvas, done: Promise }.
 * reveal: paint rows top to bottom over at most 2 s instead of all at once.
 */
export function paint(render, boxW, boxH, { reveal = false } = {}) {
  const { width: w, height: h } = render;
  const size = fitSize(w, h, boxW, boxH);
  const canvas = document.createElement('canvas');
  canvas.width = size.width;
  canvas.height = size.height;
  canvas.className = 'pixels';
  canvas.setAttribute('role', 'img');
  canvas.setAttribute('aria-label', `Recovered image, ${w} by ${h} pixels`);
  const src = document.createElement('canvas');
  src.width = w; src.height = h;
  src.getContext('2d').putImageData(toImageData(render), 0, 0);
  const ctx = canvas.getContext('2d');
  ctx.imageSmoothingEnabled = false;
  const sy = size.height / h;
  const drawRows = (n) => {
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.drawImage(src, 0, 0, w, n, 0, 0, size.width, Math.round(n * sy));
  };
  if (!reveal || prefersReducedMotion() || h < 2) {
    drawRows(h);
    return { canvas, done: Promise.resolve() };
  }
  const total = Math.min(2000, Math.max(500, h * 40));
  const done = new Promise((resolve) => {
    const t0 = performance.now();
    const step = (t) => {
      const n = Math.min(h, Math.max(1, Math.ceil(((t - t0) / total) * h)));
      drawRows(n);
      if (n < h) requestAnimationFrame(step); else resolve();
    };
    requestAnimationFrame(step);
  });
  return { canvas, done };
}
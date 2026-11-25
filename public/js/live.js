// The examining screen's step list (UI task 39, Rehaan): once the engine's answer arrives, its recorded steps are shown
// one by one under "Examining <name>…", then the result opens. Driven only by the payload, like the replay: no step is
// invented, and the line under the list says the engine's real time.
import { buildSteps, batch } from './logic.js';
import { captionText, stepItem } from './replay.js';
import { prefersReducedMotion } from './image.js';

const STEP_MS = 500;        // one frame on this screen; batch() keeps the whole list within MAX_MS
const MAX_MS = 10000;
const HOLD_MS = 900;        // the last line stays on screen this long before the result opens

function el(tag, cls, text) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text !== undefined) e.textContent = text;
  return e;
}

export const LIVE_TIMING = { stepMs: STEP_MS, maxMs: MAX_MS, holdMs: HOLD_MS };

/**
 * Show the payload's steps inside the busy screen `busy`. Resolves when the last one has been shown (at once with reduced
 * motion, or when there is only the final step). `onStep({ step, of })` is called for each frame; `alive()` returning false
 * (the screen was left) stops the list.
 */
export async function playSteps(busy, payload, { onStep = () => {}, alive = () => true } = {}) {
  const steps = buildSteps(payload);
  const n = steps.length;
  const frames = batch(n, { frameMs: STEP_MS, maxMs: MAX_MS });
  if (prefersReducedMotion() || frames.length <= 1) return;

  const bar = busy.querySelector('progress');
  bar.max = n;
  bar.value = 0;
  const caption = el('p', 'busy-caption');
  caption.dataset.cap = 'busy-caption';
  caption.setAttribute('aria-live', 'polite');
  const log = el('ol', 'busy-steps');
  log.dataset.cap = 'busy-steps';
  const note = el('p', 'busy-note', `The engine finished in ${payload.engine_ms} ms; its steps are shown here at reading speed.`);
  busy.classList.add('stepping');
  busy.append(caption, log, note);

  const wait = (ms) => new Promise((r) => setTimeout(r, ms));
  for (const [a, b] of frames) {
    if (!alive()) return;
    for (let i = a; i <= b; i++) log.append(stepItem(payload, steps[i], i));
    for (const li of log.children) li.classList.toggle('now', Number(li.value) - 1 >= a);
    log.scrollTop = log.scrollHeight;
    caption.textContent = captionText(payload, steps[b], b, n);
    bar.value = b + 1;
    onStep({ step: b + 1, of: n });
    await wait(b === n - 1 ? HOLD_MS : STEP_MS);
  }
}

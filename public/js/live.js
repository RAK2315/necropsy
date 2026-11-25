// The examining screen's step list (UI task 39, Rehaan): once the engine's answer arrives, its recorded steps are shown
// one by one under "Examining <name>…", then the result opens. Driven only by the payload, like the replay: no step is
// invented, and the line under the list says the engine's real time.
import { buildSteps, batch } from './logic.js';
import { captionText, stepItem } from './replay.js';
import { stepExplain } from './words.js';
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
 * The steps this screen shows: every rejection in order, then the layouts that fit, then the verdict. For a RESOLVED
 * result the one layout that fits is the verdict step. For several readings each one that fits is its own step (UI task
 * 43), so a file whose layouts all fit at once still shows its checks; they are listed after the rejections, because the
 * payload does not record where among them each fit was found.
 */
export function liveSteps(payload) {
  const steps = buildSteps(payload);
  if (payload.status !== 'UNRESOLVED_AMBIGUITY') return steps;
  const fits = payload.candidates.map((c, i) => ({ kind: 'fit', index: i, candidate: c }));
  return [...steps.slice(0, -1), ...fits, steps[steps.length - 1]];
}

/**
 * Show the payload's steps inside the busy screen `busy`. Resolves when the last one has been shown (at once with reduced
 * motion, or when there is only the final step). `onStep({ step, of })` is called for each frame; `alive()` returning false
 * (the screen was left) stops the list.
 */
export async function playSteps(busy, payload, { onStep = () => {}, alive = () => true } = {}) {
  const steps = liveSteps(payload);
  const n = steps.length;
  const frames = batch(n, { frameMs: STEP_MS, maxMs: MAX_MS });
  if (prefersReducedMotion()) return;    // even a one-step search shows its one check (UI task 43)

  const bar = busy.querySelector('progress');
  bar.max = n;
  bar.value = 0;
  const caption = el('p', 'busy-caption');
  caption.dataset.cap = 'busy-caption';
  caption.setAttribute('aria-live', 'polite');
  const why = el('p', 'busy-why');
  why.dataset.cap = 'busy-why';
  const log = el('ol', 'busy-steps');
  log.dataset.cap = 'busy-steps';
  const note = el('p', 'busy-note', `The engine finished in ${payload.engine_ms} ms; its steps are shown here at reading speed.`);
  busy.classList.add('stepping');
  busy.append(caption, why, log, note);

  const wait = (ms) => new Promise((r) => setTimeout(r, ms));
  for (const [a, b] of frames) {
    if (!alive()) return;
    for (let i = a; i <= b; i++) log.append(stepItem(payload, steps[i], i));
    for (const li of log.children) li.classList.toggle('now', Number(li.value) - 1 >= a);
    log.scrollTop = log.scrollHeight;
    caption.textContent = captionText(payload, steps[b], b, n);
    why.textContent = stepExplain(payload, steps[b]);
    bar.value = b + 1;
    onStep({ step: b + 1, of: n });
    await wait(b === n - 1 ? HOLD_MS : STEP_MS);
  }
}

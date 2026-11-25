// Replay of the engine's recorded steps (Requirement 7). Driven only by the payload: no request, no invented step.
import { buildSteps, batch, counterText, hypothesisLine, rejectionLine } from './logic.js';
import { rejectionPlain, verdictText, reasonText } from './words.js';
import { prefersReducedMotion } from './image.js';

// One frame at 1x. Slowed from 600 ms to 1 s in the second clarity pass (change 5) so a first-time viewer can read a step
// without pausing; batch() keeps the whole replay within MAX_MS at 1x (Requirement 7.7's 10 s, raised to 20 s).
const FRAME_MS = 1000;
const MAX_MS = 20000;
const SPEEDS = [0.5, 1, 2, 4];

function el(tag, cls, text) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text !== undefined) e.textContent = text;
  return e;
}

function button(label, title) {
  const b = el('button', 'rp-btn', label);
  b.type = 'button';
  b.title = title;
  b.setAttribute('aria-label', title);
  return b;
}

/** The caption for one step, in plain words (UI task 27). */
export function captionText(payload, step, index, total) {
  if (step.kind === 'final') {
    if (payload.status === 'RESOLVED') { const c = payload.candidates[0]; return `Fits: ${c.width} × ${c.height}, ${c.bit_depth}-bit.`; }
    return verdictText(payload) + (payload.status === 'FAILED' ? '.' : '');
  }
  const r = step.rejection, h = r.hypothesis;
  const what = h ? `Trying ${h.width} × ${h.height}, ${h.bit_depth}-bit, header ${h.header_size} bytes…` : 'Checking the format’s own declarations…';
  return `Step ${index + 1} of ${total}. ${what} rejected: ${reasonText(r.reason, r.discrepancy)}.`;
}

/** The line shown instead of the controls when there is nothing to replay: no layout checked was rejected. */
export function nothingToReplay(payload) {
  const n = payload.total_checks;
  return n === 1 ? 'Nothing to replay: the one layout checked fits.' : `Nothing to replay: all ${n} layouts checked fit.`;
}

/**
 * createReplay(payload, { onStep(step), onFinal() }) -> { root, start() }
 * onStep is called with the last rejection step of the current frame; onFinal when the final step is shown.
 */
export const REPLAY_TIMING = { frameMs: FRAME_MS, maxMs: MAX_MS };

export function createReplay(payload, { onStep, onFinal, onFrame = () => {} }) {
  const steps = buildSteps(payload);
  const n = steps.length;
  const frames = batch(n, { frameMs: FRAME_MS, maxMs: MAX_MS });
  const root = el('section', 'replay');
  root.setAttribute('aria-label', 'Replay of the engine\u2019s recorded steps');

  const head = el('div', 'rp-head');
  head.append(el('span', 'rp-honest', `Replaying the engine’s search. It finished in ${payload.engine_ms} ms; this replay slows it down so you can follow it.`));
  const omitted = payload.rejections_omitted || 0;
  if (omitted > 0) head.append(el('span', 'rp-honest', `Replaying ${payload.rejections.length} of ${payload.rejections.length + omitted} recorded rejections; the rest did not fit in one response.`));

  const bar = el('div', 'rp-bar');
  const back = button('\u2039', 'Step back');
  const play = button('Pause', 'Play or pause');
  const fwd = button('\u203a', 'Step forward');
  const end = button('Skip to end', 'Skip to the end');
  end.dataset.cap = 'skip';
  const speed = el('select', 'rp-speed');
  speed.setAttribute('aria-label', 'Replay speed');
  for (const s of SPEEDS) { const o = el('option', '', `${s}\u00d7`); o.value = String(s); if (s === 1) o.selected = true; speed.append(o); }
  const counter = el('span', 'rp-counter mono');
  counter.setAttribute('aria-live', 'polite');
  bar.append(back, play, fwd, end, speed, counter);

  const log = el('ol', 'rp-log');
  const items = steps.map((s, i) => {
    const li = el('li', 'rp-item');
    li.value = i + 1;
    if (s.kind === 'rejection') {
      li.append(el('span', 'rl', rejectionPlain(s.rejection)));
      li.append(el('span', 'rh tech', [rejectionLine(s.rejection), s.rejection.hypothesis ? hypothesisLine(s.rejection.hypothesis) : ''].filter(Boolean).join(' · ')));
    } else {
      li.append(el('span', 'rl final', verdictText(payload)), el('span', 'rh tech', `result: ${s.status}`));
    }
    log.append(li);
    return li;
  });
  const caption = el('p', 'rp-caption');
  caption.dataset.cap = 'replay-caption';
  caption.setAttribute('aria-live', 'polite');
  root.append(head, bar, caption, log);
  // one frame: every layout checked fits, so there is nothing to step through; the controls are not shown at all
  const single = frames.length === 1;
  if (single) {
    head.replaceChildren(el('span', 'rp-honest', nothingToReplay(payload)));
    bar.hidden = true;
    log.hidden = true;
    caption.hidden = true;
  }

  let frame = -1;
  let timer = 0;
  let playing = false;

  function show(f) {
    frame = Math.max(0, Math.min(frames.length - 1, f));
    const [a, b] = frames[frame];
    items.forEach((li, i) => {
      li.classList.toggle('now', i >= a && i <= b);
      li.classList.toggle('done', i < a);
    });
    const last = items[b];
    log.scrollTop = Math.max(0, last.offsetTop - log.clientHeight + last.offsetHeight + 4);
    counter.textContent = counterText([a, b], n);
    const s = steps[b];
    caption.textContent = captionText(payload, s, b, n);
    if (s.kind === 'final') onFinal(); else onStep(s);
    onFrame({ step: b + 1, of: n, final: s.kind === 'final' });
    if (frame === frames.length - 1) stop();
    back.disabled = frame === 0;
    fwd.disabled = end.disabled = frame === frames.length - 1;
  }
  function tick() { show(frame + 1); if (playing) schedule(); }
  function schedule() { clearTimeout(timer); timer = setTimeout(tick, FRAME_MS / Number(speed.value)); }
  function stop() { playing = false; clearTimeout(timer); play.textContent = 'Play'; }
  function go() {
    if (frame === frames.length - 1) show(0);
    playing = true; play.textContent = 'Pause'; schedule();
  }
  play.addEventListener('click', () => (playing ? stop() : go()));
  back.addEventListener('click', () => { stop(); show(frame - 1); });
  fwd.addEventListener('click', () => { stop(); show(frame + 1); });
  end.addEventListener('click', () => { stop(); show(frames.length - 1); });
  speed.addEventListener('change', () => { if (playing) schedule(); });

  return {
    root,
    start() {
      if (prefersReducedMotion() || frames.length === 1) { show(frames.length - 1); return; }
      show(0);
      go();
    },
    /** Jump to the final step (the answer column's own Skip button). */
    skip() { stop(); show(frames.length - 1); },
    single,
    /** Stop the timer chain for good: called when the result is left, so no onStep or onFinal runs after that. */
    dispose() { stop(); },
  };
}
// The examiner (UI task 51, Rehaan's call, 27 Nov 2026): a small line-drawn ghost with a loupe, who says one dry line
// on the screens where a person might not know what to do next: the empty drop zone, the examining screen, a result
// with several readings, a result with none, and a refused file. It never appears on a recovered picture, which speaks
// for itself.
//
// Its lines follow the glossary's one rule, translate, never diagnose: they say what the engine did or found, never
// what that implies about the file's history. Every line ends with what to do next, or says nothing is needed.
// It is drawn in the text colour, never the accent: the accent marks recovered data only (Requirement 13).

const SVG_NS = 'http://www.w3.org/2000/svg';

// One path for the body (a rounded head, straight sides, a three-scallop hem), two eyes, a loupe held to one side.
const BODY = 'M14 52 V26 C14 12 23 5 32 5 C41 5 50 12 50 26 V52 C47 49 44 49 41 52 C38 55 35 55 32 52 C29 49 26 49 23 52 C20 55 17 55 14 52 Z';

function svg(mood) {
  const s = document.createElementNS(SVG_NS, 'svg');
  s.setAttribute('viewBox', '0 0 72 60');
  s.setAttribute('aria-hidden', 'true');
  s.classList.add('ghost-mark');
  const add = (tag, attrs) => {
    const e = document.createElementNS(SVG_NS, tag);
    for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v);
    s.append(e);
    return e;
  };
  add('path', { d: BODY, class: 'g-body' });
  if (mood === 'squint') {             // examining: one eye narrowed at the bytes
    add('path', { d: 'M24 27 h6', class: 'g-line' });
    add('circle', { cx: 39, cy: 27, r: 2.4, class: 'g-eye' });
  } else if (mood === 'flat') {        // nothing fits: level eyes, level mouth
    add('path', { d: 'M24 27 h6 M36 27 h6', class: 'g-line' });
    add('path', { d: 'M28 37 h8', class: 'g-line' });
  } else if (mood === 'shrug') {       // several readings: eyes up, a small o
    add('circle', { cx: 27, cy: 25, r: 2.4, class: 'g-eye' });
    add('circle', { cx: 39, cy: 25, r: 2.4, class: 'g-eye' });
    add('circle', { cx: 33, cy: 36, r: 2, class: 'g-line' });
  } else {                             // waiting
    add('circle', { cx: 27, cy: 27, r: 2.4, class: 'g-eye' });
    add('circle', { cx: 39, cy: 27, r: 2.4, class: 'g-eye' });
  }
  // the loupe: a lens and a handle, held out to the right
  add('circle', { cx: 60, cy: 30, r: 7, class: 'g-line' });
  add('path', { d: 'M55 35 L49 41', class: 'g-line' });
  return s;
}

/** A ghost with its line. mood: 'wait' (default), 'squint', 'shrug' or 'flat'. Returns a <figure class="ghost">. */
export function ghost(line, mood = 'wait', cap = 'ghost') {
  const fig = document.createElement('figure');
  fig.className = 'ghost';
  fig.dataset.cap = cap;
  fig.dataset.mood = mood;
  const say = document.createElement('figcaption');
  say.className = 'ghost-line';
  say.textContent = line;
  fig.append(svg(mood), say);
  return fig;
}

/** Change what an existing ghost says, and its face. */
export function ghostSay(fig, line, mood) {
  if (!fig) return;
  fig.querySelector('.ghost-line').textContent = line;
  if (mood && mood !== fig.dataset.mood) {
    fig.dataset.mood = mood;
    fig.querySelector('svg').replaceWith(svg(mood));
  }
}

// The lines. Each names what the engine did, then what to do next.
export const GHOST = {
  // the drop zone, before anything happens
  idle: 'Give me a file nothing else will open. I read the bytes, and I show my working.',
  // a refused drop: the reason itself is in the message line under the drop zone
  refused: 'Not that one. The reason is just below. Try another file, or one of mine further down.',
  // the examining screen
  examining: 'Measuring. A layout only counts if every byte lands somewhere.',
  // several readings fit (engine status UNRESOLVED_AMBIGUITY)
  several: (n) => `${n} pictures fit these bytes exactly, and nothing in them says which one is right. So I'm not picking. Open any one to see its working.`,
  // nothing fits (engine status FAILED)
  none: 'Nothing I tried fits every byte. Every attempt is listed below, with the reason each was set aside. Try another file, or a sample.',
};

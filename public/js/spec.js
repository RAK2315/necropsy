// Emitted spec panel (Requirement 12). Shows the engine's emitted files as text and downloads them as a ZIP.

import { zipFailMessage } from './logic.js';

export const FRAMING = 'NECROPSY was built with spec-driven development, and it produces spec-driven development.';

function el(tag, cls, text) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text !== undefined) e.textContent = text;
  return e;
}

async function download(bytes, slug, button, status) {
  button.disabled = true;
  status.textContent = 'Preparing…';
  try {
    // The server holds nothing, so the browser sends the same bytes again and the server emits again.
    let r;
    try {
      r = await fetch('/api/spec.zip', { method: 'POST', body: bytes, headers: { 'Content-Type': 'application/octet-stream' } });
    } catch (e) { status.textContent = zipFailMessage(0); return; }
    if (!r.ok) { status.textContent = zipFailMessage(r.status); return; }
    const url = URL.createObjectURL(await r.blob());
    const a = el('a');
    a.href = url;
    a.download = `${slug}.zip`;
    document.body.append(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 10000);
    status.textContent = `Downloaded ${slug}.zip`;
  } catch (e) {
    status.textContent = zipFailMessage(0);
  } finally {
    button.disabled = false;
  }
}

/** Build the panel for one payload. bytes are the file the user examined. */
export function specPanel(payload, bytes) {
  const root = el('section', 'spec');
  root.dataset.cap = 'spec';
  root.setAttribute('aria-label', 'Emitted Kiro spec');
  const head0 = el('div', 'region-head');
  head0.append(el('h2', 'r-title', 'A spec for this file’s format'),
    el('p', 'r-line', 'Requirements, a design and an acceptance test. Give the folder to Kiro or a developer; a parser that passes the test reads this file.'));
  root.append(head0, el('p', 'spec-framing', FRAMING));
  const spec = payload.spec || {};
  if (spec.error) {
    root.append(el('p', 'spec-sub', 'A spec is written only when at least one reading fits the data exactly.'),
      el('p', 'spec-error tech', spec.error));
    return root;
  }
  const head = el('div', 'spec-head');
  const folder = el('span', 'spec-folder mono', `${spec.slug}/`);
  const button = el('button', 'quiet', 'Download spec folder (.zip)');
  button.type = 'button';
  const status = el('span', 'spec-status');
  status.setAttribute('role', 'status');
  button.addEventListener('click', () => download(bytes, spec.slug, button, status));
  head.append(folder, button, status);
  root.append(head);

  if (!spec.files) {
    root.append(el('p', 'spec-sub', 'The emitted files are too large to show here. Download the folder to read them.'));
    return root;
  }
  const names = Object.keys(spec.files);
  const tabs = el('div', 'spec-tabs');
  tabs.setAttribute('role', 'tablist');
  const body = el('pre', 'spec-text mono');
  body.dataset.verbatim = '';            // the emitter's own text, shown as written
  body.tabIndex = 0;
  body.setAttribute('role', 'tabpanel');
  const buttons = names.map((name, i) => {
    const b = el('button', 'spec-tab mono', name);
    b.type = 'button';
    b.setAttribute('role', 'tab');
    b.addEventListener('click', () => select(i));
    b.addEventListener('keydown', (e) => {
      if (e.key === 'ArrowRight' || e.key === 'ArrowLeft') {
        const j = (i + (e.key === 'ArrowRight' ? 1 : names.length - 1)) % names.length;
        select(j);
        buttons[j].focus();
      }
    });
    return b;
  });
  function select(i) {
    buttons.forEach((b, k) => b.setAttribute('aria-selected', String(k === i)));   // every tab is a Tab stop (Requirement 20.1); arrows also move
    body.textContent = spec.files[names[i]];          // plain text: no highlighting, cost linear in length
    body.scrollTop = 0;
  }
  tabs.append(...buttons);
  root.append(tabs, body);
  select(0);
  return root;
}
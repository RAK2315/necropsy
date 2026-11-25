// Light and dark themes (second clarity pass, Rehaan's request). Loaded before the stylesheet paints, so the remembered
// theme applies with no flash. Dark is the default; the choice is remembered in this browser only.
(() => {
  const KEY = 'necropsy-theme';
  const read = () => { try { return localStorage.getItem(KEY); } catch (e) { return null; } };
  const apply = (t) => { document.documentElement.dataset.theme = t === 'light' ? 'light' : 'dark'; };
  apply(read());
  const label = (b) => {
    const light = document.documentElement.dataset.theme === 'light';
    b.textContent = light ? 'Dark theme' : 'Light theme';
    b.setAttribute('aria-pressed', String(light));
    b.setAttribute('aria-label', light ? 'Light theme on. Switch to the dark theme' : 'Dark theme on. Switch to the light theme');
  };
  document.addEventListener('DOMContentLoaded', () => {
    const b = document.getElementById('theme');
    if (!b) return;
    label(b);
    b.addEventListener('click', () => {
      const next = document.documentElement.dataset.theme === 'light' ? 'dark' : 'light';
      apply(next);
      try { localStorage.setItem(KEY, next); } catch (e) { /* not remembered: still switched */ }
      label(b);
    });
  });
})();

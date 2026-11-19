// Result screens. Task 6 holds only a placeholder; tasks 9 to 12 replace it.
export function renderResult(root, payload, bytes) {
  root.replaceChildren();
  const p = document.createElement('p');
  p.className = 'busy';
  p.textContent = payload.status;
  root.append(p);
}
---
inclusion: fileMatch
fileMatchPattern: "necropsy/engine/**"
---

# Engine rules

Applies to everything under `necropsy/engine/`.

- Pure Python, standard library only. No network calls, no GPU, no
  native extensions, so it runs on a free hosting tier.
- Public entry points never raise. Every failure path returns a
  structured error value; wrap the top level as a last line of defence,
  but do not use that wrapper to hide bugs in inner code.
- Never trust a length, count, offset or dimension read from the input.
  Bounds-check every read against the buffer before slicing, and cap any
  allocation sized from input-declared values.
- State byte offsets, widths and endianness explicitly in code (named
  constants or `struct` format strings with `<` or `>`), matching the
  spec. Never rely on native byte order.
- Deterministic: the same bytes in produce the same result out. No
  randomness, clocks or global mutable state in the inference path.
- Keep inference and presentation separate. The engine returns data;
  it does not format output for the UI.

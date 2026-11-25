---
inclusion: fileMatch
fileMatchPattern: ["public/**", "web/**"]
---

# UI rules

Applies to everything under `public/` (the front end) and `web/` (the service's serialiser and pixel rendering).

Until 25 Nov 2026 this file's pattern was `necropsy/ui/**`, a path that never existed, so it was never included
automatically while the UI was built. The pattern above points at where the UI actually lives.

- The UI calls the engine; it never re-implements parsing or inference.
- Translate, never diagnose. The UI may say in plain words what the engine found. It may not say what that
  implies about the file or its history. "Decoding finished with bytes left over" translates
  `decoder_unconsumed`; "the file is cut short" is a diagnosis and is not allowed. Every plain-word mapping
  (`public/js/words.js`) names the engine function whose result it translates, and the engine's own term stays
  on screen in a smaller `.tech` element.
- Every feature must be demonstrable on screen in under 20 seconds.
  If a screen cannot show its value that quickly, simplify it.
- Engine failures are a normal outcome, not a crash. Render the
  structured error clearly; never show a stack trace to the user.
- Show the evidence: the raw bytes alongside the inferred structure, so
  a viewer can see why NECROPSY reached its conclusion.
- Must run on a free hosting tier. No GPU, no local-only dependencies,
  no third-party network calls during a recovery.
- Enforce an upload size limit before passing bytes to the engine.

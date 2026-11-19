---
inclusion: fileMatch
fileMatchPattern: "necropsy/ui/**"
---

# UI rules

Applies to everything under `necropsy/ui/`.

- The UI calls the engine; it never re-implements parsing or inference.
- Every feature must be demonstrable on screen in under 20 seconds.
  If a screen cannot show its value that quickly, simplify it.
- Engine failures are a normal outcome, not a crash. Render the
  structured error clearly; never show a stack trace to the user.
- Show the evidence: the raw bytes alongside the inferred structure, so
  a viewer can see why NECROPSY reached its conclusion.
- Must run on a free hosting tier. No GPU, no local-only dependencies,
  no third-party network calls during a recovery.
- Enforce an upload size limit before passing bytes to the engine.

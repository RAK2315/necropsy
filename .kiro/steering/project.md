---
inclusion: always
---

# NECROPSY project rules

Kiroween 2026 entry, Resurrection category. Solo build, deadline
4 Dec 2026.

## Scope discipline
- Build only what the current task asks for. Do not add formats,
  variants or options that were not explicitly requested.
- Prefer the smallest implementation that satisfies the acceptance
  criteria.

## Parser rules
- Parsers never raise on malformed input. Return a structured error.
- Every parser gets a Hypothesis property test asserting it never
  raises on arbitrary bytes.
- Byte offsets and struct formats must be stated explicitly in the
  spec before any implementation.

## Constraints
- Must run on a free hosting tier. No GPU, no local-only dependencies.
- No network calls during parsing.

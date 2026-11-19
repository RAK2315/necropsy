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

## Ambition
- This is a flagship build, not an MVP. Prefer the thorough
  implementation over the quick one.
- Every feature must be demonstrable on screen in under 20 seconds.
  If it cannot be shown, it does not get built.
- Finish and polish beat breadth. A smaller number of deeply working
  things wins over many shallow ones.

## Shell

- This is Windows PowerShell 5.1. Use ";" as the statement separator,
  never "&&".
- Prefer running a Python script file over a long inline -c command.
- If a command's output cannot be read after two attempts, stop and
  report it rather than retrying.

## Commits
- Commit after every completed task, never in batches.
- The git history is graded evidence of process. A repo with three
  commits looks like code written elsewhere and pasted in.

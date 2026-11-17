---
inclusion: always
---

# Parser conventions

- Parsers never raise on malformed input. They return a structured error.
- Implement only what the task asks for. Do not add formats, variants,
  or options that were not explicitly requested.
- Every parser gets a property-based test asserting it never raises on
  arbitrary bytes.

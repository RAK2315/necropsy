---
inclusion: fileMatch
fileMatchPattern: "tests/**"
---

# Test rules

Applies to everything under `tests/`.

- Run tests with `python -m pytest tests/<file> -q`.
- Every parser and every engine entry point has a Hypothesis property
  test asserting it never raises on arbitrary bytes
  (`st.binary()`), and that its return type is always the declared
  success or error type.
- Build binary fixtures in code from documented byte layouts, so every
  byte in a test is explained. Do not commit opaque binary blobs as
  test inputs, except the generated samples under `spike/samples/`.
- Tests are deterministic and offline: no network, no clock-dependent
  assertions, no reliance on test order.
- A test that checks a recovered image compares exact pixel values,
  not just "no error".

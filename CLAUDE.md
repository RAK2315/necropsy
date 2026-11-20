# NECROPSY

Kiroween 2026 hackathon entry. Resurrection category. Solo build.

## What it is
Drop in a file in an obsolete format that nothing can open. NECROPSY
infers its structure from raw bytes, writes a decoder, checks the output
is coherent, and recovers the contents.

## Hard constraints - never violate
- Deadline 4 Dec 2026, 2:00 PM PT.
- `.kiro/` MUST stay committed. Never add it to .gitignore, ever.
- LICENSE (MIT) must remain present and detectable.
- Repo stays PUBLIC on GitHub.
- Must deploy to a free tier with a working public URL. No GPU, no
  local-only runtime.
- Demo video must be under 3 minutes.

## Who does what
- Rehaan decides. Everything goes through him.
- Kiro builds everything that ships, through its spec workflow
  (requirements, design, tasks in EARS form, each task citing its
  requirement IDs): all engine and UI code, the specs and the tests.
  This is deliberate. Technological Implementation is 20% of the score
  and here means depth of Kiro usage, judged from `.kiro/` and the
  submission write-up.
- Claude Code researches, diagnoses, writes documentation and tooling,
  and writes the prompts Rehaan gives to Kiro. It also does git, CI,
  deploy config and the README, and verifies Kiro's work independently.
  A diagnosed defect goes to Kiro as a requirement or a task, never as
  a pasted diff.
- Until 20 Nov 2026 a separate Claude chat session wrote Kiro's prompts.
  Claude Code took that over on 20 Nov.
- Claude Code never writes engine or UI code. If asked to, it stops and
  says the work belongs in Kiro.
- Questions about the engine's principles go to Rehaan before they are
  settled: whether something is a declaration or format knowledge,
  whether a rejection rule is derivable or a threshold, whether a result
  is a defect or correct behaviour.

## Verification is the most valuable role
Kiro writes the spec, the implementation and the tests, so it grades its
own homework. Check it independently.
- Re-derive results from the spec, not from the code. For example,
  `spike/verify_independent.py` reproduced the corpus trace from
  requirements.md alone.
- Every number in a committed doc must come from running something or
  reading a file now. Never carry a figure over from memory or a spec.
- If a requested claim is false, say so and do not write it. If
  something cannot be verified, say so or mark a TODO. Never write a
  plausible figure.
- Kiro works in the same tree, often while you run. Never commit its
  uncommitted files unless asked, and stage only your own paths, never
  `git commit -a`. A sudden burst of test failures may be Kiro mid-edit,
  so check file timestamps before reporting it as a regression.

## Settled decisions - do not relitigate
1. Conventions versus declarations. A probe may read what a file states
   about itself (the TIFF byte-order mark, the PCX encoding byte, the TGA
   image descriptor). It must never encode knowledge that is not in the
   file (`xmax - xmin + 1`). Revision strategies recover conventions.
2. Closure is a hard gate on the decoded stream, never a score.
3. When several readings close, the engine reports all of them and
   chooses none. Coherence is a heuristic that never decides.
4. The emitted spec deliberately does NOT include a parser. The test file
   is the acceptance suite for a parser the reader writes from the
   document.
5. No CRT, scanline or horror styling. The look is forensic examination.
6. No Streamlit or Gradio.

## Project state (20 Nov 2026)
- Four Kiro specs in `.kiro/specs/`: `structure-inference-engine`,
  `necropsy-ui`, `gate-adversary`, `real-corpus`.
- Engine: four probes (PCX, TGA, PBM, TIFF), three revision strategies,
  generic search for headerless files, a closure gate on the decoded
  stream, ambiguity reporting instead of guessing, and spec emission.
  The Decision Record has 22 items. The spec was reopened three times:
  item 20 (the TIFF probe reads the BitsPerSample array), item 21 (a
  probe can say a declaration is impossible) and item 22 (the TGA 2.0
  footer's offsets end the data region).
- Tests in CI at `76feacb`: 769 Python passed, 1 skipped (the
  open-failures test, whose list is now empty), 22 front-end passed.
  CI installs Pillow so the pixel comparisons run.
- Real corpus: 81 files from six upstream decoder test suites in
  `spike/samples/real/`. 25 RESOLVED and 56 FAILED as committed in
  `docs/REAL-CORPUS-RESULTS.md`, with pixels compared to Pillow 12.2.0.
  Scope comes only from `manifest.json`.
- UI: tasks 1 to 15 and 17 to 19 done. The host gate passed on
  20 Nov: cold analyse 1.44 s on the idle canary. 16 (final deploy and
  acceptance) runs last. Live at https://necropsy.vercel.app.
  `necropsy-coldtest` has been used for its one cold hit: never
  redeploy it.
- The Hypothesis-found property-12 failure (a malformed TIFF) was
  addressed by Decision Record item 16: a file that broke its format's
  rules emits as a one-file layout.

## Still open
- Demo video, under 3 minutes, public on YouTube.
- The Kiro usage write-up and the Devpost submission.
- UI task 16, last.
- Revoke the Vercel protection bypass secret on both projects.
- Pre-submission checklist: `notes/submit.md` (gitignored).

## Conventions
- Parsers never raise on malformed input; they return structured errors.
- Every parser has a Hypothesis property test asserting it never raises
  on arbitrary bytes.
- Build only what was asked. No extra formats, variants or options.
- No UTF-8 BOM in `.kiro/` (it breaks steering front matter): `.githooks/pre-commit` runs `tools/check_no_bom.py` (`--fix` strips); enable per clone with `git config core.hooksPath .githooks`.

## Context
Full brief with positioning: notes/BRIEF.md
That file is gitignored. Never commit it and never quote it in any
file that gets committed.

## Environment
- Windows. PowerShell execution policy was Restricted and has been set
  to RemoteSigned for CurrentUser. If shell calls fail, check that first.
- Python 3.10.11 with pytest and hypothesis already installed.

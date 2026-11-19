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
- A Claude chat session (not Claude Code) governs. It researches the
  event, rules and competitors, makes architecture and scope decisions,
  reviews Kiro's output, and writes the prompts Rehaan pastes into Kiro
  and into Claude Code. It writes no project code.
- Kiro builds everything that ships: all engine and UI code, specs and
  tests. This is deliberate. Technological Implementation is 20% of the
  score and here means depth of Kiro usage, judged from `.kiro/` and the
  submission write-up.
- Claude Code (you) does everything unscored: scaffolding, git, repo
  hygiene, deploy config, docs, the README, and independent verification
  of Kiro's work.
- Never write engine or UI code. If asked to, stop and say it belongs
  in Kiro.

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

## Project state (19 Nov 2026)
- Engine: complete. 263 tests passed at commit `38bbbbc`. Four probes
  (PCX, TGA, PBM, TIFF), three revision strategies, generic search for
  headerless files, a closure gate on the decoded stream, ambiguity
  reporting instead of guessing, and spec emission for every format
  recovered.
- UI: spec written, tasks 1 to 5 of 16 done. Deployed at
  https://necropsy.vercel.app. A second, untouched Vercel project,
  `necropsy-coldtest`, is the canary for a 24-hour cold-start test due
  20 Nov 19:03 IST.
- External samples: a Pillow-written PCX resolves with pixels byte-equal
  to its source. A Pillow-written TGA fails on a 26-byte TGA 2.0 footer.
  The engine is being amended to add that trailer entry. The failing test
  (`tests/ui/test_external.py`) is a strict xfail, so it will turn into
  an error when the amendment lands and must then be un-marked.
- Known open bug: `tests/test_emit.py::test_property_12_emitted_layout_reproduces_engine`
  has a Hypothesis-found failing input (a malformed TIFF, 5x8 at 7 bpp)
  that the reference reader does not reproduce. Kiro to fix.

## Still open
- UI tasks 6 to 16.
- The cold-start gate.
- Demo video, under 3 minutes.
- The Kiro usage write-up.
- Devpost submission.

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

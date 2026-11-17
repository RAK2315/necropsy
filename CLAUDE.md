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

## Division of labour - important
- Kiro does ALL parser work: specs, implementation, property tests.
  That is scored at 20% of the total and must be genuine work.
- You (Claude Code) do scaffolding, git, deploy config, docs, the video
  script, and debugging when Kiro gets stuck.
- Never write parser implementation code. If asked, stop and say it
  belongs in Kiro.

## Conventions
- Parsers never raise on malformed input; they return structured errors.
- Every parser has a Hypothesis property test asserting it never raises
  on arbitrary bytes.
- Build only what was asked. No extra formats, variants or options.

## Context
Full brief with positioning: notes/BRIEF.md
That file is gitignored. Never commit it and never quote it in any
file that gets committed.

## Environment
- Windows. PowerShell execution policy was Restricted and has been set
  to RemoteSigned for CurrentUser. If shell calls fail, check that first.
- Python 3.10.11 with pytest and hypothesis already installed.

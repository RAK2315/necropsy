# UI clarity passes: tasks 24 to 47

## Who built this

Kiro built the engine and the original interface (UI tasks 1 to 23) through its spec workflow. This pass was built by a
second AI assistant, **Claude Code**, outside Kiro's spec workflow. Rehaan made that call on 25 Nov 2026 so the
interface could land a day early and the time could go to the recordings. It covers the whole visible surface of the
product as it now stands:

| Task | What | Commit |
|---|---|---|
| 24 | Landing page: headline, who it is for and what it does; one primary action ("See it recover a real file", running `pillow_odd_stride.pcx`); the drop zone as a secondary choice; the three outcome tiles in plain words, each with an Open affordance; three-step "How it works"; one plain line per sample, computed from a fresh engine run; the MIT-CMU notice served beside the real sample and linked from its row | `UI task 24` |
| 25 | A state line under the header on every screen: which file, its size, what is running, and the verdict, announced (`aria-live="polite"`) | `UI task 25` |
| 26 | A verdict heading above both columns; a title and one plain line on every region; the glossary applied, with each engine term kept in a smaller `.tech` element; 11 to 11.5 px text raised to 12.5 px; `.kiro/steering/ui.md` fixed | `UI task 26` |
| 27 | The replay announces itself: a caption rewritten on every step, a header that says this is a slowed-down replay of a search that already finished, a placeholder in the answer column while the answer is pending, and a replay with nothing to replay hides its controls | `UI task 27` |
| 28 | The ambiguity grid: every reading at one size, in payload order, linking to its card, with nothing on a tile but its picture and its own size | `UI task 28` |

Claude Code also wrote every test for these tasks and edited older Kiro-written UI tests where the markup they read
changed (first strip tile, chip text, sample counts, the failure copy, the accent rule's proof-line class). Each
commit names its task and carries a `Co-Authored-By: Claude` trailer.

A second pass the same day (tasks 29 to 36) and a third (tasks 37 and 38), both also Rehaan's call, are recorded in their own sections below.

Nothing in the engine or the API payload changed in either pass. The first pass kept the palette, fonts and theme; the
second added a light theme and self-hosted fonts at Rehaan's request. The no-CRT rule is unchanged.

## The rule: translate, never diagnose

The UI may say in plain words what the engine found. It may not say what that implies about the file or its history.
"Decoding finished with bytes left over" translates `decoder_unconsumed`. "The file is cut short" is a diagnosis and
is not allowed. The contradiction box puts the two findings side by side and claims nothing more: "Declared: no
compression. Only run-length decoding fits."

The glossary is `public/js/words.js`. Every mapping names the engine function whose result it translates and was
written from that code:

| Engine term | Computed by | Plain words |
|---|---|---|
| `arithmetic_mismatch` (discrepancy d) | `closure.check_closure`, encoding none: (data_end − header_size) − row_stride × height | the data is d bytes longer / shorter than this layout needs |
| `decoder_overrun` | `closure.rle_pcx_decode`: a run would take the output past the expected size | a run would write past the size of the picture |
| `decoder_underrun` | `closure.rle_pcx_decode`: the range ended (or a run marker was its last byte) before the output was full | the data ran out before the picture was full |
| `decoder_unconsumed` | `closure.rle_pcx_decode`: the output was full before the range ended | decoding finished with bytes left over |
| `degenerate_hypothesis` | `closure.check_closure`: a dimension not positive, alignment not 1, 2 or 4, header outside the file, or a header field overlapping the data | not a usable layout: a size is not positive, or the header overlaps the data |
| `field_out_of_bounds` | `closure.check_closure`, `trailers.trailer_data_end`, the TIFF probe | a declared position lies outside the file |
| `probe_precondition_failed` | `probes.*` | a declared value is outside what the format allows |
| `unsupported_encoding` | `closure.check_closure` | this encoding is recognised but not decoded |
| `inclusive_bounds` | `strategies.inclusive_bounds`: width = xmax − xmin + 1, height likewise | counted the header's bounds inclusively (+1) |
| `rle_pcx` (correction) | `strategies.rle_pcx` | tried PCX run-length decoding |
| `row_padding_variants` | `strategies.row_padding_variants`: alignment 2 and 4 | tried rows padded to a multiple of N bytes |
| closure | `closure.check_closure` | fits the data exactly; "The N data bytes decode to exactly M bytes: H rows of S bytes. Every data byte is used." |
| `exhausted` | `engine._exhausted` with checks > 0 | every layout within the search's limits was tried |
| `no_hypothesis_checked` | `engine._exhausted` with checks = 0 | no layout reached the fit check |
| generic stage | `generic.py`, runs only when no probe matched | no format signature matched, so it searched layouts directly |
| coherence `row_mad_ratio` | `coherence.row_coherence` | row similarity score, a heuristic shown for information only |
| `RESOLVED` / `UNRESOLVED_AMBIGUITY` / `FAILED` | `EngineResult.status` | Recovered / Several readings fit / Not recovered (the enum stays beside it, small) |

"Not recovered" is scoped on purpose: `FAILED` means nothing closed within the bounded search, not that no layout
exists. The verdict reads "Not recovered: no layout tried fits the data exactly".

## Decisions taken in this pass

- **Sample descriptions.** necropsy-ui Requirement 11.4 forbade any description of a sample. Rehaan approved one plain
  line per sample on 25 Nov 2026, so 11.4 is superseded. The line is computed by `tools/copy_samples.py` from a fresh
  engine run, and `tests/ui/test_samples.py` fails if it drifts from the engine or uses a word that diagnoses the file.
- **The first outcome tile** examines `mystery_i` instead of `external_a`, so the landing page shows the declared
  encoding that does not fit. Its pixel test now compares with the service's own render of `mystery_i`.
- **The real sample.** `pillow_odd_stride.pcx` is copied from `spike/samples/real/` after its sha256 is checked
  against the corpus manifest. Its MIT-CMU notice is served at `/samples/LICENSES/Pillow-MIT-CMU.txt`.
- **Steering.** `.kiro/steering/ui.md` matched `necropsy/ui/**`, a path that never existed, so it was never included
  automatically while Kiro built the interface. It now matches `public/**` and `web/**` and carries the rule above.
  `tests/test_steering.py` fails if any steering pattern matches no tracked file. The other four steering files
  resolve: `engine.md` (`necropsy/engine/**`) and `tests.md` (`tests/**`) match tracked files; `parsers.md` and
  `project.md` are always included. Whether Kiro's IDE accepts the two-pattern array form, which its steering
  documentation describes, has not been checked from inside Kiro.

## Capture hooks

Every element the recordings touch has a `data-cap` attribute. The one list is `tools/capture_hooks.json`, by screen.
`tests/ui/test_hooks.py` fails if a hook is missing from its screen, and the recording preflight
(`video/scripts/check_selectors.mjs v7`) reads the same list and exits 1 naming every hook that matches nothing.

## Verification

Same standard as Kiro's task 14: write the assertion, break the behaviour on purpose, confirm the test fails, restore,
confirm it passes. Each break is a JSON entry in `docs/ui-clarity-breaks/` and is run with
`python tools/break_check.py docs/ui-clarity-breaks/<task>.json`, which applies the break, runs the named test,
restores the file and compares its sha256 before and after. The outputs are beside each file.

| Task | Breaks | Caught | Test |
|---|---|---|---|
| 24 | 8 | 8 | `tests/ui/test_landing.py`, `tests/ui/test_samples.py` |
| 25 | 6 | 6 | `tests/ui/test_state_line.py` |
| 26 | 9 | 9 | `tests/ui/test_plain_words.py` (jargon scan over every screen, region titles, verdicts, font floor), `tests/test_steering.py` |
| 27 | 7 | 7 | `tests/ui/test_replay_caption.py` |
| 28 | 7 | 7 | `tests/ui/js/screens.test.mjs` (neutrality extended to the grid), `tests/ui/test_amb_grid.py` |
| hooks | 3 | 3 | `tests/ui/test_hooks.py` |

Every restore was byte-identical. Breaks that the tests caught include leaving "Replaying" on screen after the final
step, putting "closure" back into a heading, putting "lies" back into the contradiction box, freezing the replay
caption, sorting the grid by coherence, and pointing `ui.md` back at the path that does not exist.

Two defects were found by these tests before they shipped: the replay controls stayed visible when hidden (a
`display: flex` rule overrode `[hidden]`), and the grid's size labels overflowed their tiles (the overflow check was
added after a screenshot showed it, then the CSS was fixed).

Every existing guard stays green: the accent is used only on recovered data, no third-party requests, no CRT effects,
the keyboard and contrast tests, the Pillow render match, and the ambiguity neutrality test.

## Second pass: tasks 29 to 36

The first pass labelled every region; the layout still had no hierarchy. Eleven regions shared one background, border,
title size and weight, the two columns competed at every scroll position, and the hex dump was the largest object on the
screen. Rehaan set five changes and, separately, asked for a theme switch, a more visible way back and new fonts. All
eight were built by Claude Code, in one commit named `UI tasks 29 to 36`.

| Task | What |
|---|---|
| 29 | One column, in sequence, the weight falling at each level: the answer (the recovered image, large, under the verdict), why it fits (the one-line proof), how it got there (the replay and the corrections), the evidence (the technical line, the bytes, the header values). The answer and its proof fit above the fold at 1600 × 900. |
| 30 | The evidence starts collapsed, behind controls that say what is inside and how big it is ("The file’s bytes (14,313)", "What the header declares (8 values)"). Open by default on FAILED only. Selecting an ambiguous reading opens its header values. |
| 31 | The recovered image fills its frame (up to 880 × 340), scaled nearest-neighbour by any factor, so the frame is the image's own shape; the true dimensions stay beneath it. mystery_i's 8 × 8 shows at 340 × 340. |
| 32 | Clicking a sample (or the primary button) runs the same flow as a dropped file: "Examining <name>…" with an indeterminate progress bar and the name in the state line, held for at least 700 ms, then the result with its replay running. |
| 33 | The replay is bigger (caption 18 px, log 14 px, controls 14 px, a taller log) and slower: 1 s per frame at 1×, up from 600 ms. |
| 34 | A light and dark theme switch in the header. Dark stays the default; the choice is remembered in the browser and applied before first paint. Every colour is a theme token; the contrast test and the accent rule now run in both themes. |
| 35 | "Examine another file" is a solid, bordered control with an arrow, not a quiet one. |
| 36 | Roboto for text and Poppins for headings, self-hosted from `public/fonts/` (from the `@fontsource` 5.3.0 packages, SIL Open Font License 1.1, notices beside the files). The mono font is unchanged, so the hex columns keep their widths. |

**Requirements superseded.** necropsy-ui Requirement 7.7 bounded the replay at 10 s at 1×; with 1 s frames the bound
is now 20 s, so a replay of up to 20 steps shows one step per frame (mystery_i's 20 steps take 20 s at 1×). The
original two-column layout of the necropsy-ui design is replaced by the single column.

**Hooks added** to `tools/capture_hooks.json`: `theme` (start), `ev-bytes`, `ev-fields`, `tech-line` (results). The
busy screen is `[data-cap=busy]`.

**Verification.** `tests/ui/test_second_pass.py` (eight browser tests, one per task) and a `fillSize` unit test. The
existing contrast test and accent-rule probe were made to run in both themes. `tests/ui/test_plain_words.py` now opens
the evidence before its jargon scan, so collapsed text is still scanned; `tests/ui/test_state_line.py` reads the
state line once the sample's size is known, because the name now shows first.

Breaks: `docs/ui-clarity-breaks/p2.json`, output beside it. 20 breaks, each restore byte-identical. 19 were
caught on the first run. One was not: putting the accent on the chip's text colour in the light theme passed, because
the accent probe (`tools/visual_probe.mjs`, Kiro's) only counts a text colour on elements without child elements, and
the chip has one (its `.tech` enum). That blind spot predates this pass and applies in both themes; it is recorded here,
not fixed. The break was re-aimed at the chip's border, which the probe does count, and was caught in the light run and
passed in the dark run, as it should (the output shows both runs).

## Third pass: tasks 37 and 38

Rehaan's call, 25 Nov, after watching a sample run: the replay looked as if it had already run, because Pause, the step
buttons and two Skip controls were on screen from the first frame; and the demo's images were few-pixel test files, not
pictures. Both were built by Claude Code, in one commit named `UI tasks 37 and 38`.

| Task | What |
|---|---|
| 37 | While the replay plays for the first time only its step counter and caption show. Pause, the step buttons, the speed and "Skip to end" appear once it has reached its end, for going back over it. The answer column's "Skip to the answer" button is removed; its placeholder line stays. With reduced motion the replay opens at its end, so the controls show at once. |
| 38 | Three real pictures lead the sample list: `imagemagick_input.tga` (a photograph of a rose, from ImageMagick's test suite, ImageMagick License), `pillow_hopper_1bit.pbm` (a 1-bit portrait) and `pillow_pil184.pcx` (a handwritten signature), both from Pillow's test suite (MIT-CMU). They are corpus files from `spike/samples/real/`, checked against the manifest's sha256, each linked to its licence notice. The first outcome tile on the landing page examines the photograph instead of mystery_i. |

**What task 37 does not do.** The replay is still a replay: the engine finishes in milliseconds and the header says so.
The three real pictures resolve at their first check (each file's declarations fit the data at once), so their result
says "Nothing to replay" and shows no steps. No step is invented to make them look busier.

**Requirements superseded.** UI task 27's skip button in the answer placeholder is removed.

**Verification.** `tests/ui/test_third_pass.py`: the controls are hidden while the first run plays and shown after it,
and the three pictures lead the list, the first tile is the photograph, and each resolves to the engine's own
dimensions. `test_samples.py`, `test_landing.py`, `test_strip.py`, `test_a11y.py` and `test_replay_caption.py` were
updated for the new order, notices, first tile and placeholder. Older tests that click "Skip to end" during the first
run still do so programmatically; a hidden button still receives a scripted click.

Breaks: `docs/ui-clarity-breaks/p3.json`, output beside it. 6 breaks, all caught on the first run, each restore
byte-identical.

## Task 39: the steps on the examining screen

Rehaan's call, 25 Nov, the same day: under "Examining <name>…" the page should show the engine working through the
file, step by step, rather than a progress bar and then a finished result. Built by Claude Code.

Once the engine's answer arrives, its recorded steps are listed one by one under "Examining <name>…": a caption for the
current step in plain words, each step's line (the plain reading, then the engine's own terms), and a progress bar that
fills with them. 500 ms per step, at most 10 s in all (longer searches are shown a few steps at a time), and the last
line holds for 900 ms. Then the result opens with the answer already shown and its replay at the end, so the replay is
for going back over the steps, with its controls there from the start. The strip tiles open the same way. With reduced
motion, or when there is nothing to replay, the result opens at once.

It is still a replay of a search that has already finished, and the screen says so: a line under the list gives the
engine's real time ("The engine finished in 1.06 ms; its steps are shown here at reading speed"), and the state line
says "Replaying the search". Every line is the payload's own rejection, in order; none is invented.

**Superseded.** Task 37 (controls hidden during the result's first run) no longer applies, because the result's replay
no longer runs on arrival. The answer-pending placeholder of task 27 is removed, and the replay header now reads "The
engine’s search, step by step. It finished in N ms; press Play to watch it again at reading speed." The capture hooks for
the `replaying` screen are now `busy`, `busy-caption` and `busy-steps`.

**Verification.** `tests/ui/test_third_pass.py::test_the_steps_play_one_by_one_while_examining` reads every line as it
appears for mystery_h and compares the list with the payload's rejections, in order; checks the steps arrive one by one,
the bar fills, the real-time line is there, no control is on the screen, and the result opens at its last step with the
answer shown. Tests that waited for the replay to run on the result page were updated to wait for the result instead.

Breaks: `docs/ui-clarity-breaks/p4.json`, output beside it. 5 breaks, each restore byte-identical. 4 were caught on the
first run. One was not: making the result replay from the start again passed, because the test read the step counter
only once the answer was shown, which with the break is after the replay ends. The test now reads the counter the moment
the result opens; the rerun caught all 5.

## Fourth pass: tasks 40 to 46

Rehaan's call, 25 Nov: the page had become readable but not explainable. A reader with little background could see
what NECROPSY said without understanding what had been checked or why it counted. He also asked for a header that stays
on screen, the evidence back in the page, a favicon and a home link, a better landing page, and an end to formatting
that read as generated. All seven were built by Claude Code, in one commit named `UI tasks 40 to 46`.

| Task | What |
|---|---|
| 40 | The header and the state line stay at the top while the page scrolls, so "Examine another file" is always in reach. |
| 41 | The evidence is part of the page again: the header values and the file's bytes are shown in full, with their sizes in their titles. This reverses task 30, now that the single column puts them last. |
| 42 | Explanations, written from the engine's own values (glossary rule: translate, never diagnose; each function in `public/js/words.js` names the engine code it describes). "Why it fits" works the arithmetic through for the reading on screen. The replay shows what the current step means under its caption, and "Explain every step" opens that explanation on every line. Each correction says what it did, with the sizes before and after. A trailer says what it is. Each header value carries a plain name ("xmin: first column"). On the failed screen each stage and each reason says what it means. The byte view says how to read it. |
| 43 | A file that fits at its first check still shows that check on the examining screen, and a file with several readings shows each one that fits as its own step. They are listed after the rejections, because the payload does not record where among them each fit was found, and the screen does not claim an order it does not have. |
| 44 | A favicon (`public/favicon.svg`), a mark beside the name, and the name is a link back to the start. |
| 45 | The landing page: what NECROPSY is and what to do, beside how it works as a three-step sequence with a sentence each; the three answers it can give, named; and the files to try in three groups that say where they came from (real pictures from ImageMagick's and Pillow's test suites, test files made for NECROPSY, files written by Pillow). The real-picture group now includes `pillow_odd_stride.pcx`, so `tools/copy_samples.py` lists it fourth. |
| 46 | Formatting that read as generated: the side-stripe borders on the contradiction box and the multi-drop notice are gone, the logo is no longer tracked wide, and region titles, line lengths and spacing were set on one scale. A token that referred to itself (`--well: var(--well)`, from the second pass) left the image well without a background in the dark theme; it is fixed. |

**Superseded.** Task 30 (the evidence collapsed by default) is reversed by task 41.

**Verification.** `tests/ui/test_fourth_pass.py`: the header stays in view at the bottom of a scrolled result and the
evidence is shown without a click; the explanations agree with the payload (the worked proof for mystery_i, the current
step's explanation, one explanation per step once asked for with each rejection's own size and discrepancy, each
correction's before and after sizes, the plain names of header values, a line for each failure reason and stage); the
first-check and several-readings files show their checks, compared with the payload's candidates; the favicon is served,
the name goes home, the three steps and the three sample groups are as stated; and the stylesheet has no side stripe and
no wide-tracked logo. Older tests were updated for the new sample order, the evidence titles, the replay's sixth control,
and the "Nothing to replay" wording. `tools/panel_probe.mjs` now waits up to 20 s for a result, because mystery_d's 18
readings take about 10 s on the examining screen.

Breaks: `docs/ui-clarity-breaks/p5.json`, output beside it. 14 breaks, all caught on the first run, each restore
byte-identical.

## Task 47: the reading cards at a glance

Rehaan's call, 25 Nov: the cards for several readings were a stack of same-weight monospaced lines. Each card now leads
with its size as a heading ("8 × 24 · 8-bit") and lists the rest as labelled rows: Header, Each row, Compression,
Data bytes, Row similarity. Every card has the same rows in the same order, and the only thing that differs between
cards is their values, so the neutrality test (`tests/ui/js/screens.test.mjs`: cards identical apart from the
coherence value) still holds. The full identity, header length included, stays in each card's accessible label.

**Verification.** `tests/ui/test_fourth_pass.py::test_cards_are_labelled_rows` compares every card on mystery_g with the
payload. The neutrality test's mask was moved to the new coherence element. Breaks: `docs/ui-clarity-breaks/p6.json`,
3 breaks, each restore byte-identical. The first run counted for nothing, because the new test failed without a break:
it rounded the score in Python (half to even, 1.4062) where the page rounds in JavaScript (half up, 1.4063). The test
now rounds as the page does. The emphasis break was also re-aimed, because its first threshold (a score above 1) matched
no value in the neutrality test's fixtures. The rerun caught all 3.

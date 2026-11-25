# UI clarity passes: tasks 24 to 36

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

A second pass the same day (tasks 29 to 36, also Rehaan's call) is recorded in its own section below.

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

# Requirements Document

## Introduction

NECROPSY UI is the web interface over the Structure-Inference Engine. A user drops in a file that nothing can open. The UI shows the engine working out the file's structure from the raw bytes, and brings the contents back as an image.

The engine spec (`structure-inference-engine`) deliberately excludes the interface, the recovered image, the deployed URL and the demo path. This spec covers those four things. It does not change the engine. The engine stays importable and standard-library-only.

The UI has three outcome screens, and they must look different from each other:

- **RESOLVED**: one layout closes. The UI shows the fields, the closure line, the revision path and the recovered image.
- **UNRESOLVED_AMBIGUITY**: several layouts close and the bytes cannot separate them. This is a success. The UI shows every candidate with its own image and prefers none.
- **FAILED**: nothing closed. The UI shows what was tried, grouped by stage, and why the search stopped.

Design and Presentation carry 40% of the judging weight, and a judge may never read the code. Every requirement below that describes something visible is therefore stated in terms of what appears on screen.

## Glossary

- **Engine**: The Structure-Inference Engine. `Engine(deadline_seconds=5.0).run(data: bytes)` returns an `EngineResult`.
- **EngineResult**: One of `VerifiedHypothesis` (`status == "RESOLVED"`), `AmbiguousResult` (`"UNRESOLVED_AMBIGUITY"`) or `FailureReport` (`"FAILED"`), as defined in the engine's `design.md`. Every `EngineResult` carries `status`, `rejections`, `total_checks` and `total_file_size`.
- **Candidate**: The engine's record of a hypothesis that passed closure. It holds `hypothesis` (with `width`, `height`, `bit_depth`, `header_size`, `row_alignment`, `encoding`, `fields`, `probe_name`, `revision_path`), `row_stride`, `expected_decoded_bytes`, `data_start`, `data_end`, `trailer`, `coherence_score`, `coherence_status`, `coherence_method`, `alternative_paths` and `decoded`.
- **decoded**: `Candidate.decoded`. The pixel bytes of the data region after the encoding is undone, exactly `row_stride × height` bytes. It has no palette, no colour interpretation and no orientation.
- **FieldRecord**: A field the engine read: `name`, `offset`, `fmt` (a `struct` format) and `value` (the tuple `struct.unpack_from` returned).
- **RejectionEntry**: One failed hypothesis: `reason`, `source`, optional `hypothesis`, optional `discrepancy`, `detail`. `source` is a probe name (`pcx`, `tga`, `pbm`, `tiff`), `"revision:" + "->".join(path)`, `"generic"` or `"engine"`.
- **Ordered rejections**: `EngineResult.rejections`, in the order the engine produced them: probe phase, then revision phase breadth-first, then Generic Search.
- **Stage**: `probe`, `revision` or `generic`. The UI derives a rejection's stage from its `source`.
- **Seed**: The hypothesis a probe emits from the file's declarations. Its rejection has a probe name as `source` and an empty revision path.
- **Declared value**: A value the file states about itself, held in a `FieldRecord`. Example: the PCX encoding byte at `0x02`.
- **Replay**: A staged animation of the ordered rejections followed by the final result. It is not real time. The engine finishes in under 50 ms.
- **Replay step**: One `RejectionEntry`, or the final result. The replay contains no other step.
- **Hex pane**: The grid of the file's bytes, with an offset column, a hex column and an ASCII column.
- **Region**: A byte range in the hex pane with its own marking: header, data region or trailer.
- **Pixel buffer**: The UI's normalised image for one candidate: width, height, channel layout (`grey8` or `rgb8`) and the pixel bytes.
- **Render note**: A one-line caption under a rendered image that states the conventions applied to produce it.
- **Analysis service**: The thin Python web layer that accepts an upload, runs the Engine and returns JSON.
- **Result payload**: The JSON the Analysis service returns for one upload.
- **Sample**: A file offered as a one-click example. Either one of the nine corpus files in `spike/samples/` (`mystery_a` to `mystery_i`, written by `spike/make_samples.py`) or an external sample.
- **External sample**: A sample written by a tool outside this project (Pillow), committed in `spike/samples/external/` with a README stating its provenance.
- **PCX palette**: The 768 bytes that follow the `0x0C` marker of the `pcx_palette_256` trailer, read as 256 RGB triples. The trailer is 769 bytes long: the marker, then the palette.
- **Emitted spec**: The `EmittedSpec` the engine's `emit_spec(result, data)` returns: a slug and the files `requirements.md`, `design.md` and `test_<module>.py`, where `<module>` is the slug with `-` replaced by `_`. An earlier draft called the third file `tests.py`; the engine's emitter names it `test_<module>.py` and the UI uses the names as emitted.

## Decision Record

The brief leaves four questions to the architect. These are the answers. Decisions 1, 3 and 4 are final. Decision 2 is a recommendation with a verification gate, because no free host can be guaranteed in advance.

1. **Recovered image: client-side canvas, fed by a pixel buffer that Python builds.**
   - The server converts `Candidate.decoded` into a pixel buffer (`grey8` or `rgb8`). The browser paints that buffer to a `<canvas>` with nearest-neighbour scaling.
   - Reasons. The pixel conversion is the hero moment and the part most likely to be wrong (row stride, padding, BGR). Done in Python, it is tested by pytest against the pixel content `spike/make_samples.py` writes, and by the Hypothesis property test the project rules require. Done in JavaScript it would need a second test toolchain. The canvas gives the reveal animation, and an ambiguous result needs several images on one screen, which is cheap with canvases and needs no extra requests.
   - Rejected: server-side PNG. Python's `zlib` and `struct` could write PNGs, but a PNG is a finished picture that cannot be revealed row by row, and it adds an encoder that nothing else needs.
   - The cost is payload size. Requirement 2 caps it.
2. **Host: Vercel Hobby, one project serving the static frontend from its CDN and the FastAPI app as a Python function. Recommended, not confirmed. See the verification gate in Requirement 14.**
   - Facts checked against the vendors' documentation while writing this spec:
     - Vercel deploys a FastAPI `app` as a Vercel Function (docs/frameworks/backend/fastapi). Functions have a request and response body limit of 4.5 MB, a 300 s maximum duration on Hobby and 2 GB memory (docs/functions/limitations). Hobby allows 100 deployments per day (docs/limits).
     - Render free web services spin down after 15 minutes without traffic and take about one minute to spin up (render.com/docs/free). A judge would not wait. Rejected.
     - Hugging Face Spaces on free hardware go to sleep when unused (docs/hub/spaces-overview). The same page says duplicating a Docker Space requires a paid plan. Creation terms for a new free Docker Space were not confirmed. Not chosen.
   - Why Vercel fits. A function has no idle spin-down of a whole server. A static page is served from the CDN with no wake-up at all, so the drop zone appears instantly even when the function is cold. The engine's 5 s deadline sits far under the 300 s function limit. A 65,536-byte upload sits far under the 4.5 MB body limit.
   - What is not verified: the cold-start time of the Python function after 24 hours idle, Hobby usage allotments over the judging window (16 Dec 2026 to 29 Jan 2027) and the plan's non-commercial terms. Requirement 14 makes these a gate with a fallback.
   - Fallback if the gate fails: run the unchanged engine in the browser with Pyodide on a static host. The engine is pure standard-library Python, so this works with no server to sleep. It departs from the brief's "upload in, JSON out" and costs a multi-megabyte runtime download on first load, so it is a fallback only.
3. **Replay: animate client-side from the single result payload. No streaming.**
   - The engine returns the whole `EngineResult` at once, and its ordered `rejections` already are the reasoning. Streaming would need the engine to emit events while it runs, which the brief rules out ("no engine change is needed"), and a 50 ms run gains nothing from streaming.
   - A streamed replay would also tie the animation to network timing, so the speed control and the pause would not be exact.
   - The replay is therefore a presentation of data the engine already produced. It is labelled as a replay (Requirement 7).
4. **Samples: all nine go through exactly the code path a dropped file takes, are never labelled with their expected outcome, and sit below the drop zone as a secondary choice.** Requirement 11 states the rules and the one open item that needs the user's decision.

## Requirements

### Requirement 1: Analysis Service

**User Story:** As a judge visiting a public URL, I want to upload any file and get a result, so that the tool is safe to expose and works on files it has never seen.

#### Acceptance Criteria

1. THE Analysis service SHALL expose one endpoint that accepts the file as the raw request body (`application/octet-stream`) and returns the Result payload as JSON.
2. THE Analysis service SHALL pass the received bytes to `Engine(deadline_seconds=5.0).run(data)` unchanged and SHALL NOT read the filename, the content type or any header as input to inference.
3. THE Analysis service SHALL reject a body longer than 65,536 bytes with HTTP 413 and a JSON error body that states the limit, before running the Engine. The limit matches the largest input for which the engine specifies its time bound and the largest source the Spec Emitter embeds in `test_<module>.py`.
4. WHEN the body is empty or shorter than 3 bytes, THE Analysis service SHALL return HTTP 200 with the engine's `FAILED` result (`termination = "input_too_short"`). It SHALL NOT treat that case as a client error.
5. THE Analysis service SHALL never execute, import, unpack or shell out on uploaded bytes, and SHALL make no network call while handling a request.
6. THE Analysis service SHALL NOT write uploaded bytes to disk, log them, or keep them after the response is sent.
7. IF any exception reaches the endpoint, THEN THE Analysis service SHALL return HTTP 500 with a JSON error body that contains the exception class name and no stack trace. FOR any body of at most 65,536 bytes, THE endpoint SHALL return HTTP 200, so the 500 path is a defect indicator, not an expected outcome.
8. THE Analysis service SHALL import the engine, report and emit packages as they are. THE UI work SHALL NOT modify any file under `necropsy/`.
9. THE Analysis service SHALL measure the wall-clock time of the `Engine.run` call itself and include it in the Result payload as `engine_ms`. The UI SHALL display this figure, so that the viewer can see the real engine time next to the replay.

### Requirement 2: Result Payload

**User Story:** As the frontend, I want one JSON document that carries everything a screen needs, so that the replay and all three outcome screens are drawn from a single response.

#### Acceptance Criteria

1. THE Result payload SHALL carry `status` (`RESOLVED`, `UNRESOLVED_AMBIGUITY` or `FAILED`), `total_checks`, `total_file_size`, `engine_ms` and `rejections`.
2. FOR `RESOLVED`, THE payload SHALL carry `stage` and one candidate. FOR `UNRESOLVED_AMBIGUITY`, it SHALL carry `stage`, the engine's `reason` text, `coherence_gap` and every candidate in the engine's discovery order. FOR `FAILED`, it SHALL carry `termination` and `partial_candidates`.
3. EACH candidate in the payload SHALL carry its hypothesis parameters (`width`, `height`, `bit_depth`, `header_size`, `row_alignment`, `encoding`, `probe_name`, `revision_path`), every `FieldRecord` (`name`, `offset`, `fmt`, `value`), `row_stride`, `expected_decoded_bytes`, `data_start`, `data_end`, `trailer`, `coherence_score`, `coherence_status`, `coherence_method`, `alternative_paths` and a pixel buffer or a render-failure reason (Requirement 3.9).
4. EACH rejection in the payload SHALL carry `reason`, `source`, `discrepancy`, `detail` and, when present, the hypothesis parameters and its `FieldRecord`s. THE payload SHALL preserve the engine's order.
5. THE payload SHALL carry the Emitted spec's slug and three file texts, or the `EmitError` message, so that the spec panel needs no second request. WHERE the Emitted spec makes the response too large, the files MAY be fetched by a second request instead. That choice belongs to the design.
6. THE payload SHALL be at most 4,000,000 bytes serialised, which leaves headroom under the 4.5 MB platform limit.
7. WHEN the rejections would make the payload exceed that limit, THE Analysis service SHALL keep the first rejections in engine order that fit, and SHALL add `rejections_omitted` (the count dropped) and `rejection_counts`, a table of counts over all rejections grouped by stage and reason. It SHALL NOT reorder, sample or alter the rejections it keeps.
8. WHEN `rejections_omitted` is greater than 0, THE UI SHALL state, wherever it shows rejections or the replay, how many of how many it is showing.
9. THE total number of pixels converted to pixel buffers per payload SHALL NOT exceed 500,000. Candidates are converted in the engine's discovery order until the budget is spent. A candidate that is not converted SHALL carry the reason `not rendered: payload limit` and SHALL still be listed with all its other fields.
10. THE serialisation SHALL be a pure function of the `EngineResult`, the source bytes and the measured `engine_ms`. It SHALL NOT include `Candidate.decoded` itself, only the pixel buffer derived from it.

### Requirement 3: Pixel Decoding

**User Story:** As a user looking at a recovered file, I want the engine's raw pixel bytes turned into the picture they encode, with the right row stride, padding and channel order, so that the contents come back correctly.

This is the hero moment. The engine returns `decoded` bytes and the geometry. It does not turn them into an image.

#### Acceptance Criteria

1. THE pixel decoder SHALL be a pure Python function taking a candidate's `decoded`, `width`, `height`, `bit_depth`, `row_stride`, `probe_name`, an optional `palette` (768 bytes or `None`, Requirement 3.7) and `bottom_left` (a boolean, Requirement 3.6), and returning either a pixel buffer or a render-failure reason. It SHALL never raise on any input.
2. THE decoder SHALL address every pixel from the start of its row. Row `r` starts at byte `r × row_stride`. Bytes between the end of the row's pixel data and `row_stride` are padding and SHALL NOT be read as pixels.
3. THE decoder SHALL apply these layouts. `x` is the pixel column, `r` the row, `S = row_stride`, `d` the decoded bytes.

   | Bit depth | Pixel read | Output |
   |---|---|---|
   | 1 | `bit = (d[r×S + x//8] >> (7 − x%8)) & 1` (most significant bit first) | `grey8`: see criterion 4 |
   | 4 | `byte = d[r×S + x//2]`; `v = byte >> 4` when `x` is even, `byte & 0x0F` when `x` is odd | `grey8` with `v × 17` |
   | 8 | `i = d[r×S + x]` | with a palette: `rgb8` as `(P[3i], P[3i+1], P[3i+2])`, where `P` is the palette (criterion 7). Without: `grey8`, `i` as the grey level |
   | 24 | `o = r×S + 3x`; `B = d[o]`, `G = d[o+1]`, `R = d[o+2]` | `rgb8` as `(R, G, B)` |
   | 32 | `o = r×S + 4x`; `B = d[o]`, `G = d[o+1]`, `R = d[o+2]`; `d[o+3]` is not used | `rgb8` as `(R, G, B)`, opaque |

4. FOR bit depth 1, THE decoder SHALL map bit value 0 to grey 0 and 1 to grey 255, except that WHEN `probe_name == "pbm"` it SHALL map 1 to grey 0 and 0 to grey 255, because PBM declares 1 as black. The rule SHALL be the same for every candidate of one result.
5. THE decoder SHALL apply BGR byte order to every 24-bit and 32-bit candidate whatever its `probe_name`. The TGA probe's format declares BGR. The engine's Generic Search cannot know the channel order of a headerless file, and the corpus's headerless 24-bit file (`mystery_g`) stores BGR.
6. **Row orientation.** THE decoder SHALL render rows in the order stored, row 0 at the top, and the Render note SHALL state `rows shown in stored order`, except as follows.
   - WHEN a candidate has a `FieldRecord` named `image_descriptor` (the engine records one at offset `0x11` of a TGA seed), THE serialiser SHALL read bit 5 of its value, `(value[0] >> 5) & 1`, as the file's declared origin. Set means top-left: rows are rendered as stored and the note is unchanged. Clear means bottom-left: the serialiser SHALL pass `bottom_left = True`, THE decoder SHALL emit rows bottom to top (output row `y` is stored row `height - 1 - y`) at every bit depth, and the Render note SHALL say `rows flipped: file declares bottom-left origin`.
   - A record whose value is not a one-element tuple holding an integer SHALL be ignored, and the rows rendered as stored.
   - THE rule is per candidate. A candidate without such a record (every non-TGA candidate and every Generic Search candidate) is rendered as stored.
   - NO other orientation flag SHALL be read: not the TGA right-to-left bit (bit 4), and not the DIB height sign, because the engine does not report it.
   - THE image descriptor is a declaration in the file, in the same category as the TIFF byte-order mark. Reading it is correct parsing, not a convention.
7. **PCX palette.** WHEN a candidate's `trailer` is `pcx_palette_256` and its `bit_depth` is 8, THE serialiser SHALL read the 768 bytes at `[data_end + 1, data_end + 769)` of the source file as 256 RGB triples (byte order R, G, B, as the PCX format stores them) and pass them to the decoder as `palette`. THE decoder SHALL then map each 8-bit pixel value `i` through the palette (criterion 3). The rule rests on the engine's trailer identification and applies whatever the candidate's `probe_name`. The Render note SHALL state `palette: pcx_palette_256`.
   - WHEN no such trailer matched, or the bit depth is not 8, or the 768 bytes are not all inside the file, THE decoder SHALL render greyscale (the fallback), and the Render note SHALL say `greyscale; no palette`. A short palette SHALL NOT be padded or partly applied.
   - THE palette SHALL NOT be applied to 1-bit, 4-bit, 24-bit or 32-bit data.
   - IN an ambiguous result, THE same rule SHALL apply to every candidate by its own `trailer` and `bit_depth`.
8. THE decoder SHALL ignore the trailing bits of a row's last byte that lie beyond the width, for bit depths 1 and 4.
9. FOR a bit depth that is not 1, 4, 8, 24 or 32 (the engine's Generic Search can produce 16), THE decoder SHALL return the render-failure reason `no renderer for <n>-bit pixels`. The UI SHALL show that reason in the candidate's image frame, in the same place and weight as an image, and SHALL still show the candidate's geometry and fields.
10. IF `len(decoded) < row_stride × height`, or `width`, `height`, `bit_depth` or `row_stride` is not positive, or `row_stride < ceil(width × bit_depth / 8)`, THEN THE decoder SHALL return the render-failure reason `inconsistent geometry`. It SHALL NOT pad, truncate or guess.
11. THE decoder SHALL NOT scale, filter, interpolate or resample. The pixel buffer has exactly `width × height` pixels.
12. THE decoder SHALL produce the Render note for each image, one line stating: the bit depth, the channel order or colour source (`grey`, `palette` or `BGR→RGB`), and any of the conventions in criteria 4, 6 and 7 that applied.
13. THE decoder SHALL have a Hypothesis property test asserting it never raises and returns one of its two declared types for arbitrary `decoded` bytes and arbitrary integer geometry.
14. THE decoder SHALL be tested against ground truth computed independently of the decoder from `spike/make_samples.py`:
    - `mystery_c` (TGA, 24-bit, 16×16): the pixel buffer equals `scene(16, 16)` with `(R, G, B) = (v//2, (v×3)//4, v)` per pixel, where `v` is the scene value. This proves BGR order.
    - `mystery_h` (PCX, 6×6, stride 8, no trailer): the pixel buffer is 6×6 and equals `scene(6, 6)` as grey. This proves padding is skipped and the greyscale fallback.
    - `mystery_b` and `mystery_i` (PCX, 8×8, trailer `pcx_palette_256`): pixel `(x, y)` equals `(i, (3i) mod 256, 255 − i)` where `i = pcx_rle_rows()[y×8 + x]`, the palette `build_pcx()` writes. This proves the palette is read from after the marker and applied.
    - A synthetic 24-bit TGA-like buffer with `bottom_left = True` renders with its rows reversed and the flip note. `mystery_c` has descriptor `0x20` (top-left), so it renders as stored with the unchanged note.
    - A synthetic 8-bit buffer with a 769-byte trailer whose palette is not the identity, and one with a trailer shorter than 769 bytes, which SHALL render greyscale.
    - `mystery_e` (TIFF, 8×8): equals `scene(8, 8)` as grey.
    - `mystery_a` (PBM, 4×4): pixel `(x, y)` is black where `scene(4, 4)[y][x] < 128` and white elsewhere. This proves the PBM polarity.
    - 4-bit and 32-bit: a synthetic `decoded` buffer built in the test, with a padded stride, with odd width for 4-bit. No corpus file has these depths.
15. THE decoder SHALL be applied to every candidate of an `UNRESOLVED_AMBIGUITY` result, including those that are not preferred by any measure, with the same conventions for all.

### Requirement 4: Recovered Image Display

**User Story:** As a viewer, I want the recovered image to appear as a reveal, at a size I can see, so that the moment the bytes become a picture is visible.

#### Acceptance Criteria

1. THE UI SHALL paint each pixel buffer to a `<canvas>` using the browser's nearest-neighbour scaling (`image-rendering: pixelated` or the equivalent), by an integer scale factor.
2. THE UI SHALL choose the largest integer scale factor at which the image fits its frame. A frame is the fixed box the image sits in.
3. WHEN a `RESOLVED` result is shown, THE UI SHALL reveal the image row by row from the top, completing within 2 seconds at replay speed 1×. THE reveal SHALL be skipped when the replay is skipped or when the user prefers reduced motion.
4. THE UI SHALL show the Render note under every image.
5. THE UI SHALL show the image's pixel dimensions and bit depth next to it, for example `16 × 16 · 24-bit`.
6. WHEN the pixel buffer is a render-failure reason, THE UI SHALL show the reason in place of the canvas, inside an identical frame.

### Requirement 5: Hex Pane (Static)

**User Story:** As a viewer, I want to see the file's bytes with each identified field labelled, so that I can see that the structure came from the bytes.

The static pane is built and working before any animation is added. A static pane that works is the deliverable. Requirement 7 adds the animation on top.

#### Acceptance Criteria

1. THE hex pane SHALL show the uploaded bytes exactly, 16 bytes per row. Each row SHALL have an offset column formatted `0x%04X` as in the engine's pretty printer, 16 hex byte cells and an ASCII column in which bytes outside `0x20..0x7E` are shown as `.`.
2. FOR a file of up to 65,536 bytes (4,096 rows), THE hex pane SHALL render only the rows in view plus a margin, so that scrolling stays smooth and the page does not build tens of thousands of DOM nodes.
3. THE pane SHALL show every byte that no `FieldRecord` covers and that lies in no region in neutral grey.
4. THE pane SHALL show every byte covered by a `FieldRecord` of the displayed candidate in the accent colour, for the byte range `[offset, offset + struct.calcsize(fmt))`.
5. THE pane SHALL label each field with its name, offset, struct format and value. The label SHALL be reachable in the pane for every field (shown in place, or on hover or focus).
6. WHERE the ranges of several `FieldRecord`s overlap or are equivalent reads of the same bytes (the engine's `mystery_f` has `width` read as `<H`, `<I` and `<i` at `0x00`), THE pane SHALL list all of them in the label of those bytes and SHALL NOT hide any.
7. THE pane SHALL mark three regions distinctly from one another and from undecoded bytes:
   - the header, `[0, data_start)`;
   - the data region, `[data_start, data_end)`;
   - the matched trailer, `[data_end, total_file_size)`, only when `Candidate.trailer` is not `None`.
   Each region marking SHALL use a visible label (`header`, `data region`, `trailer: pcx_palette_256`) in addition to its tint, so that the marking does not depend on colour alone.
8. WHEN the candidate has no trailer, THE pane SHALL NOT mark any byte after `data_end` as a trailer.
9. WHEN the user hovers or focuses a labelled field in the pane, THE UI SHALL highlight the matching row in the field table. WHEN the user hovers or focuses a row in the field table, THE UI SHALL highlight its bytes in the pane and scroll them into view if they are out of view.
10. THE accent colour SHALL be used only for recovered data: field bytes, the recovered image's frame and the closure line. No other interface element SHALL use it.
   - ON the UNRESOLVED_AMBIGUITY screen, THE candidate image frames SHALL be neutral grey, not the accent. Reason: the accent marks what the file turned out to be, and on an ambiguous result nothing turned out to be anything. Accenting every candidate's frame would assert a recovery for each one while the screen's text says no choice was made.
11. THE pane SHALL be operable from the keyboard: it is focusable, scrolls with the arrow and page keys, and every labelled field is reachable by Tab.

### Requirement 6: Field Table

**User Story:** As a developer reading a result, I want every field the engine read in a table that matches the pretty printer, so that the UI and the engine's text output agree.

#### Acceptance Criteria

1. THE field table SHALL list every `FieldRecord` of the displayed candidate, in the engine's order, with columns: offset as `0x%04X`, name, struct format and value.
2. THE field table SHALL show the value as the tuple the engine returned, unwrapped by no one. A one-element tuple is shown as its single element in a form that still reads as a read result, and a multi-element or byte-string value is shown in full.
3. WHERE several records share a name, THE table SHALL show all of them and SHALL mark them as equivalent reads of one value. It SHALL NOT merge or drop any.
4. THE table and the hex pane SHALL share the highlight behaviour in Requirement 5.9.

### Requirement 7: Replay

**User Story:** As a viewer, I want to watch the inference unfold step by step at a speed I can follow, and to know it is a replay, so that the engine's work is visible and honest.

#### Acceptance Criteria

1. THE replay SHALL be driven only by the Result payload. THE UI SHALL NOT make a request to the server to animate.
2. THE replay steps SHALL be the payload's rejections in their given order, followed by one final step for the result. THE replay SHALL NOT contain a step the engine did not take, and SHALL NOT reorder the steps.
3. THE UI SHALL show a visible label on the replay, `Replay`, and the sentence `The engine finished in {engine_ms} ms. This is a replay of its recorded steps.`
4. THE replay SHALL provide: play, pause, step forward, step back, skip to end, and a speed control with at least 0.5×, 1×, 2× and 4×. THE replay SHALL start automatically when the analysis completes, at 1×.
5. EACH replay step SHALL show, in the hex pane and in a step log, the hypothesis the step concerns (width, height, bit depth, header size, alignment, encoding), its source and, for a rejection, its reason and discrepancy. The pane SHALL light the bytes of that step's `FieldRecord`s.
6. THE step log SHALL show a counter of the form `step {i} of {n}` that is always exact.
7. WHEN the number of steps would make the replay longer than 10 seconds at 1×, THE UI SHALL show several consecutive steps per frame. IN that case the counter SHALL show the true range, for example `steps 41–80 of 212`, and the log SHALL list every step shown. No step SHALL be skipped from the log.
8. THE final step SHALL show the outcome: the candidate's fields lit, its regions marked and its closure line (Requirement 8.2).
9. FOR a `RESOLVED` result whose seed closes with no rejections, THE replay MAY consist of the final step alone. THE UI SHALL NOT invent steps to lengthen it.
10. WHEN the final step shows a result's fields, THE pane MAY reveal the fields one at a time in file order. THE log SHALL then say `reads shown in file order`. This is a presentation of recorded reads, and the label states that it is not an engine step order.
11. WHEN the user prefers reduced motion, THE replay SHALL start at its final step and the controls SHALL still allow stepping through it.
12. THE replay SHALL be the second delivery. The static pane (Requirement 5) and all three outcome screens work with the replay disabled.

### Requirement 8: RESOLVED Screen

**User Story:** As a viewer, I want the resolved outcome to show how the file was understood and what it contained, so that the recovery is convincing.

#### Acceptance Criteria

1. THE screen SHALL show the status `RESOLVED`, the stage, the source (`probe_name`), the field table, the hex pane with its regions, and the recovered image with its dimensions and Render note.
2. THE screen SHALL show the closure line with the same wording as the engine's pretty printer (engine Requirement 8.4):
   - for `none`: `closure: [{start}, {end}) holds {end − start} bytes = {row_stride} x {height}`;
   - for `rle_pcx`: `closure: rle_pcx decoded [{start}, {end}) to {expected} bytes = {row_stride} x {height}, all input consumed`.
3. WHEN a trailer matched, THE screen SHALL show `trailer: {name}`.
4. THE screen SHALL show `revision_path`. WHEN it is empty, THE screen SHALL state that the file's declarations closed without revision.
5. WHEN `alternative_paths` is non-empty, THE screen SHALL show each alternative path and state that a second route reached the same answer.
6. WHEN `revision_path` is non-empty, THE screen SHALL show what each revision step changed. It SHALL take the seed hypothesis and each intermediate hypothesis from the rejections whose `source` is the probe name or `revision:` followed by the path so far, and the final hypothesis from the candidate. IF a step's hypothesis is not among the rejections, THE screen SHALL show the path name for that step without a diff. It SHALL NOT reconstruct the hypothesis.
7. WHEN `revision_path` contains `rle_pcx`, THE screen SHALL show the contradiction as a labelled pair, `declared` and `actual`:
   - `declared`: the value of the candidate's `FieldRecord` named `encoding` (for PCX, the byte at offset `0x02`), with its offset, for example `none (byte 0x02 = 0x00)`;
   - `actual`: `rle_pcx`, with the closure line that verified it.
   This is the lying-header beat in the demo path. It SHALL be visible without scrolling on a 1280×720 viewport.
8. WHEN `revision_path` contains `inclusive_bounds`, THE screen SHALL show the width and height the probe read and the width and height after revision (for example `7 × 7 → 8 × 8`), taken from the seed rejection and the candidate.
9. THE RESOLVED screen SHALL NOT use failure styling, warning styling or the wording `error`.

### Requirement 9: UNRESOLVED_AMBIGUITY Screen

**User Story:** As a viewer, I want to see that several layouts fit the bytes exactly and that the tool refuses to choose, so that I read it as honesty, not as uncertainty or a bug.

This screen shows the honesty mechanic. It is a success.

#### Acceptance Criteria

1. THE screen SHALL lead with a plain statement above the candidates, before any image, built from the number of candidates `n`: `{n} readings fit these bytes exactly. Each one passes closure. The bytes cannot separate them, so NECROPSY does not choose.` THE engine's `reason` text MAY be shown as well.
2. THE screen SHALL show the status as `UNRESOLVED_AMBIGUITY` with success styling, the same family as `RESOLVED`. It SHALL NOT use failure styling, warning styling, an error icon or the wording `error`, `failed` or `unable`.
3. THE screen SHALL show every candidate, each as one card, side by side in a wrapping grid, each with its own rendered image.
4. NO candidate SHALL be visually preferred. Specifically:
   - every card has the same size, the same frame size for its image, the same typography and the same colours;
   - no card is highlighted, outlined, badged, enlarged, pre-selected, pre-expanded, or ordered by any measure other than the engine's discovery order;
   - the cards are NOT numbered as a ranking. Each card is identified by its own geometry, for example `8 × 8 · 8-bit · header 40`;
   - the candidates are NEVER sorted by coherence, by size, by plausibility or by any other computed value, and the coherence gap SHALL NOT be shown;
   - no candidate is shown as "best", "likely", "selected" or "recommended".
5. EACH card SHALL show: its image in the common frame with its Render note, width × height, bit depth, header size, row alignment, encoding, the data region, and its coherence.
6. THE coherence SHALL be shown in the same position on every card, as `coherence (heuristic, row_mad_ratio): {score:.4f}` or `coherence (heuristic): {status}`, in the same type size and colour as the other card text. No bar, colour scale, ranking mark, or emphasis SHALL be derived from it.
7. THE screen SHALL include one sentence stating that coherence is a heuristic with known failure modes and does not choose between readings.
8. THE images SHALL be drawn at the largest integer scale that fits the common frame (Requirement 4.2). A candidate whose aspect ratio is extreme, such as 64 × 1, SHALL still be shown in the same frame size as the others, so that the difference in shape is visible and the frame size is not.
9. WHEN a candidate has a render-failure reason (Requirement 3.9, 3.10 or 2.9), THE card SHALL show it in the same frame and typography as an image.
10. THE hex pane on this screen SHALL show no candidate's layout by default. It SHALL show the union of the field reads of all candidates, each label naming every candidate geometry that uses it. WHEN the user hovers or focuses a card, THE pane SHALL show that candidate's fields and regions. WHEN the hover or focus ends, THE pane SHALL return to the union.
11. THE screen SHALL NOT mark any candidate's regions (header, data region, trailer) in the default pane, because the candidates have different regions.
12. THE field table on this screen SHALL show a candidate's fields only when the user selects its card. No card SHALL be selected on load.
13. THE screen SHALL show the stage that found the ambiguity (`probe`, `revision` or `generic`).
14. THE UI SHALL render the same ambiguity screen whatever the coherence values are, including `None` and `not_computed`. A test SHALL render the screen for two fixtures whose candidates are identical except for their coherence values and SHALL assert that the layout, the order, the sizes and the emphasis are identical, apart from the coherence text itself.

### Requirement 10: FAILED Screen

**User Story:** As a developer whose file did not resolve, I want to know what was tried and why each attempt was rejected, so that I can diagnose it.

#### Acceptance Criteria

1. THE screen SHALL show the status `FAILED` and the termination reason in plain words:
   - `exhausted`: `Every hypothesis within the search axes was tried and none closed.`
   - `no_hypothesis_checked`: `No hypothesis reached the closure gate.` When generic search ran, the screen SHALL add that no combination of header length, width, height and bit depth fitted the file's size, so nothing was closure-checked, and that this does not mean the file has no layout. (Added when the engine split this case out of `exhausted`, which had claimed checks that never ran.)
   - `deadline_exceeded`: `The search stopped at the {deadline} second deadline.`
   - `search_cap_exceeded`: `The search stopped at the 10,000 closure-check cap.`
   - `input_too_short`: `The file is shorter than 3 bytes.`
   - `internal_error`: `The engine hit an internal error. The detail is below.`
2. WHEN the stage was Generic Search and the termination is `exhausted`, THE screen SHALL state only that no closing layout was found within the stated axes and budget. It SHALL NOT state or imply that the file has no valid layout (engine Requirement 4.9).
3. THE screen SHALL show `total_checks` and the count of rejections.
4. THE screen SHALL group the rejections by stage (probe, revision, generic, engine) and, within a stage, by reason. Each group SHALL show its count and SHALL be collapsed or expanded by the user.
5. EACH rejection SHALL show its source, its reason, `(discrepancy={n})` when a discrepancy is set, its hypothesis parameters and its `detail` when present. THE rejections within a group SHALL keep the engine's order.
6. WHEN a group holds more than 200 rejections, THE UI SHALL show the first 200 and state how many more there are. WHERE `rejections_omitted` is greater than 0, THE UI SHALL also state it (Requirement 2.8) and show the count table `rejection_counts`.
7. WHEN `partial_candidates` is non-empty, THE screen SHALL list them under the heading `Closed before the search stopped` and state that the search stopped before it could decide, so that they are not an outcome.
8. THE hex pane SHALL be shown with the replay available, and with no field lit when the replay is at its end and no candidate exists.
9. THE screen SHALL show the engine's `FAILED` result for a non-image file (for example text, an executable or random bytes) as a normal, complete screen. It SHALL NOT show a generic error page.
10. THE screen SHALL be visually distinct from the two success screens.

### Requirement 11: Drop Zone and Samples

**User Story:** As a judge with no dead formats to hand, I want one-click examples, and I want to be sure the tool is not rigged for them.

#### Acceptance Criteria

1. THE first screen SHALL be a drop zone with one instruction, below the outcome strip of Requirement 16. It SHALL accept a file dropped on it and a file chosen with a file picker. (Amended: the screen was near-empty; the outcome strip now sits above the drop zone.)
2. THE drop zone SHALL be the primary control. THE samples SHALL appear below it as a secondary list under the heading `No file to hand? Try one of these.`
3. THE UI SHALL offer all nine corpus files, listed as `mystery_a` to `mystery_i` in that order, followed by the external samples (criterion 13). Each entry SHALL show its name and byte size.
4. NO sample entry SHALL show its format, its expected status, its outcome, a description of its content, or the word `corpus`, `test` or `demo`. A sample SHALL NOT be labelled with the answer. The one permitted addition is the provenance line on an external sample (criterion 14).
5. A sample click SHALL fetch the sample's bytes in the browser and submit them through the same code path and the same endpoint as a dropped file. THE Analysis service SHALL NOT receive a sample identifier, and the server SHALL contain no code that recognises a sample.
6. EACH sample entry SHALL also offer a download of its raw bytes, so that a viewer can save the file and drag it in from their own desktop. THE downloaded file SHALL be byte-identical to the file committed in `spike/samples/` or `spike/samples/external/`.
7. THE samples SHALL be served as static files. THE UI SHALL NOT carry a copy of any sample's expected result.
8. THE UI SHALL state in one line what the tool does with an arbitrary file: it reads PCX, TGA, PBM and TIFF declarations and otherwise searches for headerless raster layouts. THE UI SHALL NOT claim to open arbitrary formats.
9. WHEN a user drops a non-image file, THE UI SHALL show the engine's FAILED screen (Requirement 10). That behaviour SHALL be reachable in under 20 seconds from the first screen.
10. WHEN a dropped file exceeds 65,536 bytes, THE UI SHALL refuse it in the drop zone with a message that states the limit and SHALL NOT upload it.
11. WHILE an analysis request is in flight, THE UI SHALL show a plain `Analysing…` state with no progress percentage and no animation that implies engine steps.
12. THE analysis result for any sample SHALL be identical to the result for the same bytes dropped as a file whose name is changed to anything else. A test SHALL assert this for every sample.
13. **External samples.** THE project SHALL include at least two external samples, written by Pillow (the Python imaging library) and committed unmodified in `spike/samples/external/`, named `external_a` and `external_b` with no extension:
    - `external_a`: an 8-bit palettised PCX (Pillow mode `P`, saved as PCX, one plane, 256-colour palette);
    - `external_b`: an uncompressed 24-bit TGA (Pillow mode `RGB`, saved as TGA with no compression), with bottom-left origin, which is expected to be Pillow's default. IF the descriptor byte Pillow writes has bit 5 set, THEN the README SHALL record that, the orientation SHALL be set with Pillow's documented save option, and the option SHALL be recorded in the README.
    BOTH SHALL be written from one source image whose size is fixed in advance at 64 x 48 pixels. THE size SHALL NOT be changed after the engine has been run on the files. THE source image SHALL have at most 256 distinct colours, so the palettised write loses nothing, SHALL be generated by a committed script, `tools/make_external_samples.py`, which also calls Pillow to write both files, and SHALL be committed beside them as a binary PPM (`P6`), `spike/samples/external/source.ppm`, so that expected pixels can be read without an imaging library. Pillow is a development dependency of that script only. It SHALL NOT be a dependency of the engine, the Analysis service or the deployment.
14. THE file `spike/samples/external/README.md` SHALL state each external sample's provenance: the tool (Pillow) and its exact version (`PIL.__version__`), the Python version, the exact `save` calls with every argument, the source image and the script that made it, the date, the TGA descriptor byte as written, and the sentence that the file bytes were written by Pillow's encoders, not by this project's code. THE repository's top-level `README.md` SHALL point to it. THE UI SHALL show a one-line provenance on each external sample (`written by Pillow {version}`), and nothing else about it.
15. THE engine SHALL be run on the external samples with no change to any file under `necropsy/`. WHEN an external sample does not return `RESOLVED`, THE project SHALL report that as a finding, with the engine's output, and SHALL NOT adjust the engine, the sample, the image size, the `save` arguments or the expected values to make it pass. THE UI work depending on that sample SHALL wait for the user's decision.
16. FOR each external sample that resolves, THE serialiser test SHALL compare the rendered pixel buffer with the source PPM exactly, with no flip in the test. `external_a` SHALL render with its palette. `external_b` SHALL render upright because the decoder honours the `image_descriptor` record (Requirement 3.6), and its Render note SHALL state `rows flipped: file declares bottom-left origin`.

### Requirement 12: Emitted Spec Panel

**User Story:** As a judge asking whether this would work without Kiro, I want to see the Kiro spec NECROPSY produces from a recovered file and to take it away, so that the product's output mirrors its method.

#### Acceptance Criteria

1. THE UI SHALL show a spec panel for every `RESOLVED` and `UNRESOLVED_AMBIGUITY` result, with the Emitted spec's `requirements.md`, `design.md` and `test_<module>.py` selectable as tabs. The text SHALL be shown exactly as the engine's `emit_spec` returned it.
2. THE panel SHALL display the folder name `<slug>/` and the three file names.
3. THE panel SHALL show this one line of framing: `NECROPSY was built with spec-driven development, and it produces spec-driven development.`
4. THE panel SHALL offer a download button. THE download SHALL be a ZIP archive containing the folder `<slug>/` with exactly the three files `requirements.md`, `design.md` and `test_<module>.py`, each byte-identical to the Emitted spec's text encoded as UTF-8 without a BOM.
5. THE ZIP SHALL be built in memory. THE Analysis service SHALL NOT call the engine's `write_spec`, and no code in this spec SHALL write to the host's file system, because the chosen host's function file system is not a place to keep state.
6. THE ZIP SHALL be built from the Emitted spec the same request returned. THE download SHALL NOT re-run inference on bytes the server no longer holds. WHERE the design makes the download a second request, that request SHALL carry the three file texts or the source bytes from the browser, and the server SHALL emit again from them.
7. WHEN the result is `FAILED`, THE panel SHALL show the engine's `EmitError` message (`nothing recovered: FAILED/<termination>`) and no download button.
8. WHEN the result is `UNRESOLVED_AMBIGUITY`, THE panel SHALL show the emitted spec as the engine produced it. The UI SHALL NOT add a candidate preference to it.
9. THE panel SHALL be reachable from a result screen in one click, and a viewer SHALL be able to see the emitted `requirements.md` of a recovered file in under 20 seconds from the first screen.
10. THE panel SHALL show long files without freezing the page. `test_<module>.py` embeds the source as base64 and may be about 90,000 characters, so the panel SHALL show the text in a scrollable region and SHALL NOT highlight it by a method whose cost grows more than linearly with its length.

### Requirement 13: Visual Language and Demo Path

**User Story:** As a judge watching a video under three minutes, I want an interface that reads as a forensic examination, so that the design is distinct from other entries and each feature registers on screen.

#### Acceptance Criteria

1. THE UI SHALL use a cold neutral background, one warm accent colour used only for recovered data (Requirement 5.10), a monospace face for bytes and field names, and a clean sans-serif face for all other text.
2. THE UI SHALL NOT use CRT phosphor colouring, scanlines, screen curvature, glow or flicker, and SHALL NOT use skull, cobweb, blood or other horror imagery.
3. THE UI SHALL NOT use Streamlit, Gradio or a comparable generated-UI framework. THE frontend SHALL be hand-built.
4. THE UI SHALL NOT make the page's meaning depend on colour alone. Statuses, regions and the declared-versus-actual pair SHALL also carry text labels.
5. EACH of these SHALL be demonstrable on screen in under 20 seconds from the first screen, with no setup:
   - a RESOLVED result with its recovered image (a click on a sample);
   - the declared-versus-actual contradiction (the `mystery_i` sample);
   - the ambiguity screen with all candidates side by side (the `mystery_d`, `mystery_f` or `mystery_g` sample);
   - a FAILED screen (a non-image file);
   - the emitted spec panel and its download.
6. THE UI SHALL be designed for a desktop viewport of 1280×720 and above. A narrower layout is not required.
7. THE UI SHALL NOT load fonts, scripts, styles or images from a third-party origin, so that it works offline from its own host once loaded and makes no third-party request.
8. WHEN the user prefers reduced motion, THE UI SHALL disable the replay animation and the image reveal (Requirement 4.3, 7.11).

### Requirement 14: Deployment and Hosting

**User Story:** As the project owner, I want a public URL that answers during judging from 16 December 2026 to 29 January 2027, so that no judge meets a dead link.

#### Acceptance Criteria

1. THE deployment SHALL run on a free tier with no GPU, no paid plan and no local-only dependency, and SHALL be reachable at a public URL.
2. THE project SHALL have the deployment live at its public URL by day 10 of the build, running the real engine on at least one sample, and SHALL redeploy from the repository with one command or one push. THE deployment SHALL then be left with no requests for at least 24 hours and hit cold, and the measured wake time SHALL be recorded in `docs/KIRO-LOG.md` with the date, the idle duration and the figure in seconds. This is a hard pass/fail gate, not a monitoring task.
3. **Verification gate.** The gate is the cold hit in criterion 2. BEFORE the build commits further to the host (beyond the minimal deployment), the deployed URL SHALL pass all of these, and the results SHALL be recorded in `docs/KIRO-LOG.md`:
   - after at least 24 hours with no request, a request to the analysis endpoint with a sample returns within 5 seconds from the moment the page is requested, measured from a cold start;
   - the static first screen is served without waiting for the function;
   - the host's current terms for the plan, read on the day of the test, still allow a public hobby or hackathon project with the usage a judging period produces.
4. IF the cold hit exceeds 5 seconds, or any other point of the gate fails, THEN THE project SHALL switch hosts at once, not in December: to the fallback in Decision 2 or to another host that passes the same gate, which SHALL then be deployed and put through the same 24-hour idle test. THE user decides which host. The project SHALL NOT continue building UI on a host that has failed the gate.
5. THE project SHALL re-run the cold-start check on the deployed URL on 15 December 2026 and again at least once a week until 29 January 2027, and SHALL record each result in `docs/KIRO-LOG.md`.
6. THE deployed engine SHALL be exactly the repository's engine. THE deployment SHALL contain no copy of the engine, the report package or the emit package other than the repository's.
7. THE deployed backend SHALL need no database, no persistent file system, no secret and no network egress.

### Requirement 15: Engine Boundary and Verification

**User Story:** As the developer, I want the UI to depend only on the engine's published interface and to be tested the way the project requires, so that engine changes and UI changes do not collide.

#### Acceptance Criteria

1. THE UI SHALL depend on the engine only through `Engine`, the result types (`VerifiedHypothesis`, `AmbiguousResult`, `FailureReport`, `Candidate`, `Hypothesis`, `FieldRecord`, `RejectionEntry`), `emit_spec` and `EmittedSpec`/`EmitError`, as defined in the engine's `design.md`. IF the engine's interface differs from that document when this spec is implemented, THEN the UI work SHALL stop and report the difference rather than adapt silently.
2. THE UI work SHALL start only after the engine spec's tasks for the result types, the Engine, the Spec Emitter the `decoded` field of `Candidate`, and the amendment that records a `FieldRecord` named `image_descriptor` at offset `0x11` of a TGA seed are complete and committed.
3. THE serialiser, the pixel decoder and the Analysis service endpoint SHALL each have a Hypothesis property test asserting they never raise on arbitrary bytes of up to 65,536 bytes and return their declared types. FOR the endpoint, the assertion SHALL be HTTP 200 and valid JSON.
4. THE serialiser SHALL be tested against the nine corpus files, asserting for each the `status` Requirement 7 of the engine spec gives it, and, for the `RESOLVED` files, the pixel buffers in Requirement 3.14. IT SHALL also be tested against the external samples as Requirement 11.15 and 11.16 state.
5. THE test for the lying header SHALL assert, for `mystery_i`, that the payload carries `revision_path == ["inclusive_bounds", "rle_pcx"]`, the `alternative_paths` the engine gives, and a candidate `FieldRecord` named `encoding` with value `(0,)`, which is what the screen needs for `declared` and `actual`.
6. THE test for ambiguity SHALL assert, for `mystery_d`, `mystery_f` and `mystery_g`, that every candidate in the payload carries a pixel buffer or a render-failure reason, and that the payload's candidate order equals the engine's discovery order.
7. THE UI SHALL be accepted only after each screen in Requirement 13.5 has been run against the deployed URL and recorded as a screen capture, with the time it took.
8. THE frontend's pure logic (region computation, field byte ranges, replay step list, step batching) SHALL be written as functions separate from the DOM, so that they can be tested. THE choice of JavaScript test tool belongs to the design.
9. THE UI work SHALL add no feature, format, option or export beyond those stated in this spec.
10. EACH browser-observable claim (Requirements 12.4, 13, 16, 17, 18) SHALL be checked by a test that drives the real page, and each such test SHALL have been seen to fail against a deliberate break of the claim before it is relied on.

### Requirement 16: Outcome Strip on the First Screen

**User Story:** As a judge who has not touched anything yet, I want to see the three things NECROPSY can say about a file, using real output, so that I understand the product before I try it.

#### Acceptance Criteria

1. THE first screen SHALL show, above the drop zone, three tiles in this order: a RESOLVED result, an UNRESOLVED_AMBIGUITY result and a FAILED result.
2. EACH tile SHALL be produced by sending real bytes through the same `analyse` path and `/api/analyze` endpoint a dropped file uses, when the page loads. THE UI SHALL NOT ship a stored copy of any of these results (Requirement 11.7 applies).
   - RESOLVED: the sample `external_a`, written by Pillow, not by this project.
   - UNRESOLVED_AMBIGUITY: the sample `mystery_d`.
   - FAILED: the first 300 bytes of the sample `mystery_b`, built in the browser from the served file, and labelled as exactly that.
3. EACH tile SHALL name its input and carry one line, filled from the payload, never from a constant:
   - RESOLVED: the recovered image, and `One layout closes.`
   - UNRESOLVED_AMBIGUITY: every candidate's image at one common small size in discovery order, and `{n} readings fit, so NECROPSY does not choose.`, where `n` is the payload's candidate count.
   - FAILED: the termination sentence of Requirement 10.1, the first three rejections as Requirement 10.5 shows them, and `Nothing closed, and here is why.`
4. THE ambiguity tile SHALL obey Requirement 9.4: no candidate image larger, framed, ordered or marked differently from another.
5. WHILE a tile's request is in flight, THE tile SHALL show `Analysing…`. IF it fails, THE tile SHALL say so in place and the drop zone SHALL still work.
6. A click on a tile SHALL open that result's full screen from the payload already held, with no second request.
7. THE strip, the drop zone and its instruction SHALL fit in a 1280×720 viewport without scrolling.

### Requirement 17: Downloading Recovered Output

**User Story:** As a user who recovered a picture, I want to take it away, so that the recovery is useful beyond this page.

#### Acceptance Criteria

1. THE RESOLVED screen and every UNRESOLVED_AMBIGUITY card SHALL offer two downloads: `PNG` and `data region`.
2. THE `PNG` download SHALL be the candidate's pixel buffer at its native size, `width × height`, one PNG pixel per image pixel, with no scaling, smoothing or added alpha (every pixel opaque).
3. THE `data region` download SHALL be exactly the bytes `[data_start, data_end)` of the examined file, as stored (still encoded, for an RLE candidate).
4. THE downloads SHALL be built in the browser from data the page already holds, with no request.
5. THE download file names SHALL be `<input>_<width>x<height>_<bit_depth>bit.png` and `<input>_<width>x<height>_<bit_depth>bit_data_<data_start>-<data_end>.bin`, where `<input>` is the sample name, or the dropped file's name without its extension, reduced to `[A-Za-z0-9._-]`.
6. WHERE a candidate has a render-failure reason, its `PNG` control SHALL be present and disabled, so that every card keeps the same structure (Requirement 9.4). Its `data region` download SHALL still work.
7. THE download controls SHALL NOT use the accent colour (Requirement 5.10), and a click on a card's control SHALL NOT select the card.

### Requirement 18: Dropping Several Files

**User Story:** As a user who dropped several files at once, I want to be told what happened to them, so that nothing is ignored silently.

#### Acceptance Criteria

1. NECROPSY examines one file at a time. WHEN several files are dropped at once, THE UI SHALL examine the first file in the drop's order and SHALL state, on the result screen and before any result content, `{k} files were dropped. NECROPSY examines one file at a time: it examined {name} and ignored {k − 1} other{s}: {names}.`, naming every ignored file.
2. THE statement SHALL stay on the result screen until the user examines another file, and SHALL be announced to assistive technology.
3. WHEN the first file is over the size limit, THE UI SHALL refuse it as Requirement 11.10 states and SHALL also state that the others were not examined.
4. WHEN a drop carries no file (for example dragged text), THE UI SHALL say `Nothing to examine: drop a file.` and stay on the first screen.
5. THE file picker SHALL accept one file.
## Accepted Decisions and Remaining Open Items

Accepted by the user, and not to be reopened in design:

1. **Upload limit of 65,536 bytes** (Requirement 1.3).
2. **Rows are rendered as stored by default, and a TGA's declared origin is honoured** (Requirement 3.6). Bit 5 of the `image_descriptor` field flips a bottom-left TGA upright. The DIB height sign is not read, so a bottom-up DIB still appears upside down.
3. **16-bit and other depths get a placeholder card** (Requirement 3.9).
4. **PCX files with several colour planes are reported as the engine reports them**, normally as FAILED, with no workaround. The engine's PCX seed uses bits per plane and ignores the `planes` field.
5. **The PCX palette is applied** (Requirement 3.7), with greyscale as the fallback.
6. **External samples are required, written by Pillow** (Requirement 11.13 to 11.16). ImageMagick is dropped because it is not installed.
7. **The spec zip is rebuilt by the server.** The browser re-posts the held bytes to `/api/spec.zip`, the server re-runs the engine and emits. The engine is deterministic, and this avoids a JavaScript zip writer.

Open, to be settled by measurement:

1. **Host.** Vercel Hobby is the recommendation. Requirement 14 is a hard gate: live by day 10, idle 24 hours, cold hit measured and recorded, switch hosts at once if it fails.
2. **Engine amendment.** The UI depends on the engine recording `image_descriptor` at `0x11` of a TGA seed. The UI build starts when the user confirms that amendment is committed.
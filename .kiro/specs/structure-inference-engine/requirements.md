# Requirements Document

## Introduction

The Structure-Inference Engine is the core reasoning component of NECROPSY. It accepts an arbitrary byte sequence with no extension or format declaration and works out how the bytes are laid out as a raster image. It proposes structural hypotheses, verifies each against a closure gate, revises hypotheses that fail, and searches generically when no known format matches.

The engine has two successful outcomes and one failure outcome:

- **RESOLVED**: exactly one hypothesis closes. The engine returns it with the revision path that reached it.
- **UNRESOLVED_AMBIGUITY**: more than one hypothesis closes and the bytes cannot separate them. The engine returns every candidate and states why. This is a correct answer, not an error.
- **FAILED**: no hypothesis closed within the search axes and budget. The engine returns every hypothesis it tried and why each was rejected.

The engine never returns a guess it could not verify. When the engine resolves a file, or reaches an unresolved ambiguity, it can also emit a Kiro-format spec folder describing what it recovered, so that NECROPSY produces spec-driven development as well as using it.

## Glossary

- **Engine**: The Structure-Inference Engine. Its entry point is `Engine.run(data: bytes)`, which returns an `EngineResult`.
- **EngineResult**: One of `VerifiedHypothesis` (status `RESOLVED`), `AmbiguousResult` (status `UNRESOLVED_AMBIGUITY`) or `FailureReport` (status `FAILED`).
- **Hypothesis**: A candidate interpretation of the bytes: `width`, `height`, `bit_depth`, `header_size`, `row_alignment`, `encoding`, an optional declared `data_end`, the `FieldRecord`s it was built from, its origin (`probe_name` or `"generic"`), optional PCX bounds (`xmin`, `ymin`, `xmax`, `ymax`) and its `revision_path`.
- **Hypothesis key**: The tuple `(width, height, bit_depth, header_size, row_alignment, encoding, data_end)`. Two hypotheses with the same key are the same hypothesis.
- **FieldRecord**: A field read from the bytes: name, byte offset, `struct` format string, and the tuple returned by `struct.unpack_from`, never unwrapped.
- **Equivalent reads**: Several `FieldRecord`s with the same name that read the same value from different formats or offsets. Listing all of them states that the bytes cannot distinguish them.
- **Encoding**: The scheme applied to the data region. `"none"` and `"rle_pcx"` are decodable. `"rle_tga"` and `"tiff_compression_<n>"` are recognised declarations that this engine cannot decode.
- **Row stride**: `row_stride = round_up(ceil(width × bit_depth / 8), row_alignment)`, where `row_alignment ∈ {1, 2, 4}` and `round_up(n, a)` is the smallest multiple of `a` that is at least `n`.
- **Expected decoded bytes**: `row_stride × height`.
- **Data region**: The byte range `[header_size, data_end)`. `data_end` is the hypothesis's declared data end when it has one; otherwise it is `trailer_start` from the Trailer Registry; otherwise it is the file length.
- **Trailer Registry**: An ordered list of recognised trailers that a file writes about itself. Each entry has a name, a length, a byte signature, the signature's offset from the start of the trailer, and the hypothesis origins it applies to. An entry may carry declared offsets that end the data region earlier than the trailer start (Requirement 1.15).
- **Closure**: The binary property that decoding the data region under the declared encoding yields exactly the expected decoded bytes and consumes the entire data region.
- **Probe**: A format-specific reader that, on a signature match, emits one seed hypothesis from the format's fixed layout and the file's declarations.
- **Seed**: The hypothesis a probe emits. Revision operates only on seeds and their descendants.
- **Declaration**: A field in which the file states something about itself, such as the PCX encoding byte, the TIFF byte-order mark or the TIFF Compression tag. Reading a declaration is correct parsing.
- **Convention**: Knowledge that is not present in the file, such as "width is `xmax − xmin + 1`". Probes never apply conventions. Revision strategies discover them.
- **Revision Strategy**: A transformation of a hypothesis into new candidates. There are exactly three: `inclusive_bounds`, `rle_pcx` and `row_padding_variants`.
- **Revision path**: The ordered list of strategy names applied to reach a hypothesis. An empty list means a seed closed directly.
- **Generic Search**: The search used when no probe signature matches. Its axes are header length, field offset, field width, endianness, signedness and encoding.
- **Candidate**: A hypothesis that passed closure, with its row stride, expected decoded bytes, data region, trailer name, revision path, alternative paths, source and coherence fields.
- **Canonical path**: The revision path reported in `revision_path`. It is the first path to a hypothesis under the loop order pinned in Requirement 3.2.
- **Alternative paths**: Other revision paths of the same depth that reached the same hypothesis key. They are recorded in `alternative_paths` and are informational only.
- **Row coherence**: A heuristic score computed on candidates that already passed closure. It is reported and never used to gate, promote or order candidates.
- **Deadline**: The wall-clock limit for one `run()` call, default 5.0 seconds, configurable.
- **Search cap**: 10,000 closure checks per `run()` call, shared by the probe phase, the revision phase and generic search.
- **RejectionEntry**: One failed hypothesis: its parameters, its `FieldRecord`s, a reason from the reason vocabulary, an optional discrepancy and its source.
- **Spec Emitter**: The component that turns a `VerifiedHypothesis` or `AmbiguousResult` into a Kiro-format spec folder.
- **Layout block**: A fenced code block with info string `necropsy-layout` inside an emitted `requirements.md`. It holds a JSON description of the recovered layout in schema `necropsy-layout/1`.
- **Reference reader**: Test-support code that parses a file using only an emitted layout block. It imports nothing from the `necropsy` package.
- **Pretty_Printer**: A pure function that renders an `EngineResult` as text. It lives outside `necropsy/engine/`.

## Decision Record

These decisions are final. Each is recorded with its reason so later work does not reopen it.

1. **Closure is a hard gate.** A hypothesis that does not close is rejected. No plausibility score can admit it.
2. **Probes read declarations and never apply conventions.** A probe that reads a byte saying "RLE compressed", ignores it, fails closure and then has a revision strategy guess RLE would be theatre. A probe applies its format's fixed layout (offsets, field widths, header length, byte order) and reads declarations. Value conventions such as inclusive bounds are left to revision.
3. **A signature match always emits a seed, unless the declaration needed to build it is impossible.** (Amended by item 21.) Revision can only operate on seeds. A probe that matches but emits nothing would make every damaged file of that format unrecoverable. This is a general rule, not a TIFF special case.
4. **Closure consumes the whole data region.** The earlier decoder stopped when its output was full and never checked for leftover input, so wrong, smaller images closed. On mystery_b, 224 of 1,521 (width, height) pairs below 40 closed, including the naive 7×7. Closure now requires both an exact output length and full consumption of `[header_size, data_end)`. Trailers are handled by a registry of self-declaring trailers, not by format special cases.
5. **Three revision strategies, each with a corpus case.** `endianness_flip`, `field_width_variants` and `header_length_scan` were deleted from revision. Every probe knows its byte order, field widths and header length from its format specification (PCX 128, TGA 18 + id_length + colour map, PBM parsed from text, TIFF from tag 273), so none has an honest probe-revision case. They remain generic-search axes. `header_length_scan` also produced wrong closing answers on mystery_i.
6. **Every phase collects all closers.** Under the deleted four-strategy design, the correct answer for mystery_i surfaced only because `inclusive_bounds` happened to be listed first. Ordering is not evidence. The probe phase, the revision phase and generic search each collect every closing hypothesis at their stage, and more than one is an unresolved ambiguity.
7. **Ambiguity is a correct outcome.** A headerless blob does not contain the information needed to separate 8×8 at 8 bpp from 64×8 at 1 bpp. Both readings are true. Reporting that is correct behaviour, not a limitation.
8. **Row coherence is demoted to a reported heuristic.** Measured on the corpus, it ranked a wrong candidate first on mystery_d and mystery_g, and separated mystery_f's true answer from the runner-up by only 8.8%. It has three known failure modes, listed in Requirement 11. It never gates, promotes or orders.
9. **Field width that the bytes cannot distinguish is reported, not decided.** `<H`, `<I` and `<i` over the same bytes with zero high bytes are the same read. The engine lists every equivalent read.
10. **When two routes reach the same answer, both are reported.** With the revision loop order unpinned, hypotheses-outer gives `["inclusive_bounds", "row_padding_variants"]` for mystery_h and strategies-outer gives `["row_padding_variants", "inclusive_bounds"]`. Both reach the same hypothesis, deduplication kept whichever came first, and the corpus asserted one exact path, so list order was deciding the reported path. The loop order is now pinned and defines the canonical path and nothing else. Every other same-depth path to the same hypothesis is recorded in `alternative_paths`. Reporting only one of two routes to the same answer is the same failure as promoting one of two closing candidates: the engine states what it found.
11. **The pretty printer stays in this spec.** Task 11.3 specifies that the emitted `design.md` contains the closure arithmetic line from Requirement 8.4, so moving Requirements 8.4 to 8.7 to another spec would break spec emission's reference. The pretty printer is a text renderer, not a web UI; the UI spec needs its own rendering either way.
12. **The emitted test file is named for pytest's default collection.** The emitted folder is meant to drop into a real repository and drive a build. A reader who clones it, implements `parser_<module>` from the emitted requirements, and types `pytest` must see the tests run against that parser. A file named `tests.py` is not discovered by default, and a `pytest.ini` that works around a filename is worse than the right filename. The file is therefore `test_<module>.py`.
13. **A computed coherence score is never relabelled.** When a run stops after a candidate's coherence was computed, the engine keeps the score and reports `scored`. Only a candidate whose coherence step never ran is `not_computed`. This engine's whole claim is that it never reports something it did not establish; labelling a value it did compute as "not computed" is that same failure in miniature. Requirement 11.4 stays as written, and the engine conforms to it.
14. **The TGA probe reads the image descriptor.** Byte `0x11` bit 5 declares the row origin: set means top-left, clear means bottom-left. That is a declaration in the sense of item 2, the same category as the TIFF byte-order mark. A probe that does not read it makes the error that was reversed on TIFF. It is recorded and reported, not acted on, because consumers need it to render rows the right way up.
15. **The Trailer Registry knows the TGA 2.0 footer.** The 26-byte footer (two 4-byte offsets, then `TRUEVISION-XFILE.` and a NUL) is a declaration the file writes about itself. The registry was designed for exactly this addition: its entries were generalised from one marker byte to a byte signature, and no change to the closure gate was needed. Without it the engine fails on standard TGA 2.0 output from any real encoder; Pillow's `external_b` failed with a 26-byte `arithmetic_mismatch`. The entry also applies to Generic Search on purpose: an 18-byte literal signature is not a plausible false positive, and a headerless file carrying that footer genuinely has 26 bytes that are not pixel data. Generic Search tries `rle_pcx` only when the PCX palette trailer matched, so the new entry does not widen RLE guessing.
16. **A file that broke its declared format's rules is emitted as a file layout.** When the probe behind a result recorded `probe_precondition_failed` or `field_out_of_bounds`, the emitted spec has layout kind `file` with this file's literal values, and states that it describes this one file only, exactly as generic results do. A file that broke its declared format's rules cannot produce a truthful spec for that format. Emitting `default: 0` for the missing tag would have the document assert that TIFF permits StripOffsets to be absent and read as 0, which is false about TIFF. Teaching the reference reader that a missing tag reads as 0 would put format knowledge into a reader whose whole value is knowing no formats. Skipping such candidates in Property 12 would hide a real disagreement.
17. **Header fields and pixel data are disjoint.** An 82-byte big-endian TIFF with no StripOffsets tag resolved with data region [0, 64), so the engine asserted that the same bytes were both header fields it parsed and pixel data it decoded. That is not a format convention; it is internal self-contradiction, derivable from the engine's own output with no format knowledge. The closure arithmetic already treats header and data as disjoint, and Requirement 12 makes every hypothesis agree with it. The rule tests overlap with each field's byte range rather than "data starts after the last field", because a TIFF may legally place its IFD after the image data.
18. **A run that checked nothing does not say it tried everything.** `exhausted` states that hypotheses within the search axes were checked and none closed. For an input such as a text file, Generic Search can finish with 0 closure checks, and `exhausted` would then claim work that never happened. `no_hypothesis_checked` says only that no hypothesis reached the closure gate. `input_too_short` is the precedent for a termination that names its specific case.
19. **Cross-reference: closure alone admits about 2% of arbitrary layouts.** Measured in the `gate-adversary` spec (`.kiro/specs/gate-adversary/design.md`, "Finding"): the gate's strength comes from where hypotheses come from, not from closure in isolation. Documentation only; no requirement here changes.
20. **The TIFF probe reads the BitsPerSample array.** The probe discarded any tag whose count was not 1. For RGB and RGBA files BitsPerSample has one entry per sample (3 or 4), so it was recorded as missing even though the file declares it, and the probe then rejected `samples_per_pixel ≠ 1`. Four real files from upstream decoder suites failed as a result: `goimage_no_compress.tiff`, `goimage_no_rps.tiff`, `goimage_video-001-uncompressed.tiff` and `sdlimage_sample.tif`. This violated Decision Record item 2 and Requirement 2.4, that probes read the file's declarations. It was not a scope limit: the file states its bits per sample, and the probe threw the statement away. The fix reads the array, requires every entry to be equal (and records `probe_precondition_failed` rather than choosing one when they differ), drops the `samples_per_pixel` rejection, and accepts PlanarConfiguration 1 only, because planar configuration 2 is a different layout that the file declares. The arithmetic that confirmed it, each product equal to the declared StripByteCount of the file's single uncompressed strip at offset 8: 16 × 15 × 4 = 960 for both 16×15 files, 150 × 103 × 3 = 46350, and 23 × 42 × 3 = 2898.
21. **A probe can say that a file's declaration is impossible.** Item 3 is amended as a general rule: a signature match emits a seed unless a declared field required to construct that seed holds a value the probe has no reading for. In that case the probe records `probe_precondition_failed` with no seed, and Generic Search proceeds. The case that raised it is `pillow_ossfuzz-4836216264589312.pcx`: byte 0 is the PCX signature, and its encoding byte `0x20` has no meaning in PCX. Before this rule the probe returned silently and left no trace, so the failure screen and the replay could not show that PCX was considered. Building a seed would have meant guessing an encoding the file does not declare, which item 2 forbids, and it would have blocked Generic Search for every file starting with `0x0A`. The rule is not PCX-specific: it gives the engine a statement it could not make before, "I recognise what this file claims to be, and the declaration is impossible", which matters for a project about damaged files. A value the probe can name but cannot decode, such as a TIFF compression code, is still a reading and still produces a seed.
22. **The TGA 2.0 footer's offsets are declarations.** Same defect class as item 20 (TIFF BitsPerSample): the file declares where its non-pixel areas begin and the engine did not read it. `pillow_p_16.tga` (21,563 bytes, 128×128, 8 bpp colour-mapped, header 560) has an extension area at 21042 and a postage stamp at 16944 declared inside it. The old rule ended the data region at the footer start 21537 and failed with `arithmetic_mismatch`. The arithmetic that confirms the new rule: 16944 − 560 = 16384 = 128 × 128. Everything read is a fixed-position declaration of TGA 2.0, so the rule of item 2 and Requirement 2.4 holds (probes and the gate read declarations, never conventions) and the gate stays binary: no scoring and no choice between offsets, only the minimum. The rule lives with the `tga2_footer` registry entry, so it applies to every origin that entry applies to (`tga` and `generic`), for the same reason as item 15. An impossible declaration rejects the hypothesis with `field_out_of_bounds` instead of being ignored, because ignoring a declaration is a convention. 495 is the fixed size TGA 2.0 gives the extension area, the same category as the 26-byte footer and the 769-byte palette: the inner offsets read end at byte 494 of the area, so a declared size below the area's layout contradicts itself; it is not a tuned threshold.
23. **The TIFF probe reads PhotometricInterpretation.** The probe reads tag 262 when present, as a declared field `photometric_interpretation`. It is a declaration in the sense of item 2: the file states how sample values map to colour. Measured: `goimage_bw-uncompressed.tiff` and `libtiff_miniswhite-1c-1b.tiff` declare 262 = 0 (WhiteIsZero) and are displayed with every pixel inverted against Pillow, because nothing reads 262. The field is recorded and reported, not acted on, in the same category as the TGA image descriptor (item 14). It never enters closure, the seed, the hypothesis key or the Requirement 12 check, and it changes no result: the tag sits in the IFD with the other entries, so it adds no byte range that Requirement 12 does not already treat as header. Not taking: the web layer parsing the tag itself. Not taking: making tag 262 required; an absent tag adds no field (mystery_e has none). Expected diff: one extra field on TIFF candidates whose file has tag 262, and the matching line in their emitted specs. Nothing else.

## Requirements

### Requirement 1: Closure Gate

**User Story:** As a developer integrating the Engine, I want every hypothesis checked against an exact decoding of its data region, so that the Engine never returns a structurally inconsistent interpretation.

#### Acceptance Criteria

1. THE Engine SHALL compute `row_stride = round_up(ceil(width × bit_depth / 8), row_alignment)` and `expected_decoded_bytes = row_stride × height` using integer arithmetic only.
2. IF a hypothesis has `width ≤ 0`, `height ≤ 0`, `bit_depth ≤ 0`, `row_alignment ∉ {1, 2, 4}`, `header_size < 0` or `header_size > len(data)`, THEN THE Engine SHALL reject it with reason `degenerate_hypothesis` without decoding.
3. THE Engine SHALL determine `data_end` as the hypothesis's declared `data_end` when one is set, otherwise as `trailer_start` from the first matching Trailer Registry entry, otherwise as `len(data)`.
4. IF a declared `data_end` is greater than `len(data)` or less than `header_size`, THEN THE Engine SHALL reject the hypothesis with reason `field_out_of_bounds`.
5. THE Trailer Registry SHALL contain, in this order:
   - `pcx_palette_256`: length 769 bytes, one-byte signature `b"\x0c"` at offset 0 of the trailer (that is, at `len(data) − 769`), applying to hypotheses from the PCX probe and from Generic Search;
   - `tga2_footer`: length 26 bytes, signature `b"TRUEVISION-XFILE.\x00"` (18 bytes) at offset 8 of the trailer (that is, at `len(data) − 18`), applying to hypotheses from the TGA probe and from Generic Search.
   An entry SHALL match only when `len(data) − length ≥ header_size` and the bytes at `len(data) − length + signature_offset` equal the signature; `trailer_start` is then `len(data) − length`. Entries are tried in order and the first match wins.
6. THE closure gate SHALL read the Trailer Registry as data, so that adding an entry requires no change to the closure gate.
7. WHEN `encoding == "none"`, THE Engine SHALL accept the hypothesis only when `data_end − header_size == expected_decoded_bytes`, and otherwise reject it with reason `arithmetic_mismatch` and discrepancy `(data_end − header_size) − expected_decoded_bytes`.
8. WHEN `encoding == "rle_pcx"`, THE Engine SHALL run the PCX RLE decoder over `[header_size, data_end)` with `max_output_bytes = expected_decoded_bytes`, and accept the hypothesis only when the decoder reports `ok`.
9. THE PCX RLE decoder SHALL treat a byte `b ≥ 0xC0` as a run of `b & 0x3F` copies of the next byte, and any other byte as one literal byte.
10. THE PCX RLE decoder SHALL check, inside its loop and before writing, whether the next run or literal would exceed `max_output_bytes`, and return `overrun` without writing it. The decoder's output SHALL never exceed `max_output_bytes`.
11. THE PCX RLE decoder SHALL return `underrun` when the region ends before `max_output_bytes` bytes are produced, including when a run marker is the last byte of the region; `unconsumed` when the output is complete but region bytes remain; and `ok` only when the output length equals `max_output_bytes` and the decoder stopped exactly at `data_end`. For every result, `consumed_to` SHALL be the index of the first byte not consumed, which is the loop position when the decoder stopped:
    - `ok`: `data_end`;
    - `overrun`: the index after the value byte of the run that would overflow;
    - `underrun` because a run marker is the last byte of the region: `data_end`;
    - `underrun` because the region ended before the output was full: `data_end`;
    - `unconsumed`: the index of the first leftover byte;
    - out-of-range `start` or `end`, or negative `max_output_bytes`: `start`.
12. THE Engine SHALL map decoder results `overrun`, `underrun` and `unconsumed` to rejection reasons `decoder_overrun`, `decoder_underrun` and `decoder_unconsumed`.
13. WHEN `encoding` is any value other than `"none"` or `"rle_pcx"`, THE Engine SHALL reject the hypothesis with reason `unsupported_encoding`.
14. THE closure gate SHALL be binary. No score of any kind SHALL admit a hypothesis that fails closure or reject one that passes.
15. WHEN a hypothesis has no declared `data_end` and the `tga2_footer` registry entry matches, THE Engine SHALL read the footer's declared offsets and determine `data_end` as follows. Let `F = len(data) − 26` (the footer start) and `H = header_size`. All reads are little-endian.
    - `extension_area_offset`: `<I` at `F + 0`.
    - `developer_area_offset`: `<I` at `F + 4`.
    - IF `extension_area_offset` `E` is nonzero, THEN: `extension_size` `<H` at `E + 0`; `colour_correction_offset` `<I` at `E + 482`; `postage_stamp_offset` `<I` at `E + 486`; `scan_line_offset` `<I` at `E + 490`.
    - A declared offset of 0 means the area is absent.
    - A nonzero declared offset `o` is valid if and only if `H ≤ o < F`. IF any nonzero declared offset is not valid, THEN THE Engine SHALL reject the hypothesis with reason `field_out_of_bounds`.
    - The extension area is valid if and only if `extension_size ≥ 495` and `E + extension_size ≤ F`. IF it is not valid, THEN THE Engine SHALL reject the hypothesis with reason `field_out_of_bounds` and SHALL read none of its inner offsets.
    - `data_end` SHALL be the minimum of `F` and every nonzero declared offset. The reported trailer name SHALL remain `tga2_footer`.
    - This rule SHALL apply to every hypothesis whose origin the `tga2_footer` entry applies to (`tga` and `generic`), including the `data_end` that Generic Search uses to derive its size candidates (Requirement 4.5). An invalid declaration SHALL reject the hypotheses of that header length with `field_out_of_bounds`.
    - These declared offsets are not `FieldRecord`s of the hypothesis. They lie after the data region and SHALL NOT enter the check of Requirement 12.
16. THE Engine SHALL be tested with crafted TGA inputs, one per branch of criterion 15. Each input is a type-3 TGA with `width = 8`, `height = 8`, `bit_depth = 8`, `id_length = 0`, no colour map (`H = 18`), 64 pixel bytes at `[18, 82)`, and a 26-byte footer ending with `TRUEVISION-XFILE.\x00`. Unlisted footer and extension bytes are 0. The extension area has size 495 (`extension_size = 495`). The expected values come only from the rules of criterion 15:
    - `extension_area_offset = 0` and `developer_area_offset = 0`, length 108, `F = 82`: RESOLVED with data region `[18, 82)`.
    - `developer_area_offset = 82` only, with 10 bytes of developer data at `[82, 92)`, length 118, `F = 92`: RESOLVED with data region `[18, 82)`.
    - `extension_area_offset = 94`, with a 12-byte gap at `[82, 94)` and `postage_stamp_offset = 82`, length 615, `F = 589`: RESOLVED with data region `[18, 82)`.
    - The same input with `postage_stamp_offset = 0` and `scan_line_offset = 82`: RESOLVED with data region `[18, 82)`.
    - The same input with `postage_stamp_offset = 0` and `colour_correction_offset = 82`: RESOLVED with data region `[18, 82)`.
    - `extension_area_offset = 82`, all inner offsets 0, length 603, `F = 577`: RESOLVED with data region `[18, 82)`, where the extension offset is the minimum.
    - `developer_area_offset = 10` (below `H = 18`): `field_out_of_bounds`.
    - `developer_area_offset = F` (offset not below `F`): `field_out_of_bounds`.
    - `extension_area_offset = 82` with `extension_size = 494`: `field_out_of_bounds`.
    - `extension_area_offset = 82` with `extension_size = 496`, length 603, `F = 577` (`82 + 496 > 577`): `field_out_of_bounds`.
    - A valid extension area whose `postage_stamp_offset` is below `H`: `field_out_of_bounds`.

### Requirement 2: Probe Set

**User Story:** As a user dropping a file into NECROPSY, I want known formats read correctly from their own declarations, so that common files resolve quickly and damaged ones still produce a seed for revision.

#### Acceptance Criteria

1. THE Engine SHALL run the four probes in the order PCX, TGA, PBM, TIFF, and SHALL run every probe even after an earlier probe's seed closes.
2. IF a file is shorter than a probe's minimum length, or a probe's signature does not match, THEN THE probe SHALL emit no seed and record no `RejectionEntry`.
3. WHEN a probe's signature matches, THE probe SHALL emit exactly one seed carrying the values as read, UNLESS criterion 10 applies. Values that cannot be read SHALL be 0. WHERE a field is out of bounds, a precondition fails or the header cannot be parsed, THE probe SHALL additionally record a `RejectionEntry` with reason `field_out_of_bounds` or `probe_precondition_failed`.
4. THE probes SHALL apply only their format's fixed layout (field offsets, field widths, header length rules, byte order) and the file's declarations. THE probes SHALL NOT apply value conventions, including inclusive bounds.
5. **PCX probe.**
   - Minimum length: 128 bytes.
   - Signature: byte `0x00 == 0x0A`.
   - The encoding byte `0x02` is a declared field required to construct the seed. The probe has a reading for `0x00` and `0x01` only; any other value falls under criterion 10.
   - Fields:
     - `encoding` at `0x02` as `B`
     - `bit_depth` at `0x03` as `B`
     - `xmin` at `0x04` as `<H`
     - `ymin` at `0x06` as `<H`
     - `xmax` at `0x08` as `<H`
     - `ymax` at `0x0A` as `<H`
     - `planes` at `0x41` as `B`
     - `bytes_per_line` at `0x42` as `<H`
   - Seed: `width = xmax`, `height = ymax`, `bit_depth`, `header_size = 128`, `row_alignment = 1`, bounds set. `encoding = "none"` when byte `0x02 == 0x00` and `"rle_pcx"` when it is `0x01`, because that byte is the file's declaration of its encoding.
   - Precondition: `xmax ≥ xmin`, `ymax ≥ ymin` and `bytes_per_line > 0`; otherwise record `probe_precondition_failed`.
6. **TGA probe.**
   - Minimum length: 18 bytes.
   - Signature: byte `0x01 ∈ {0, 1}` (colour-map type) and byte `0x02 ∈ {1, 2, 3, 9, 10, 11}` (image type).
   - Fields:
     - `id_length` at `0x00` as `B`
     - `color_map_type` at `0x01` as `B`
     - `image_type` at `0x02` as `B`
     - `color_map_length` at `0x05` as `<H`
     - `color_map_entry_size` at `0x07` as `B`
     - `width` at `0x0C` as `<H`
     - `height` at `0x0E` as `<H`
     - `bit_depth` at `0x10` as `B`
     - `image_descriptor` at `0x11` as `B`. Bit 5 declares the row origin: set means top-left, clear means bottom-left. The probe records it on the seed and reports it; it does not change inference.
   - Seed: `header_size = 18 + id_length + color_map_type × color_map_length × ceil(color_map_entry_size / 8)`, `row_alignment = 1`.
   - Encoding: `"none"` for image types 1, 2 and 3; `"rle_tga"` for 9, 10 and 11.
   - Precondition: `width > 0` and `height > 0`; otherwise record `probe_precondition_failed`.
7. **PBM probe.**
   - Minimum length: 7 bytes.
   - Signature: bytes `0x00..0x02 == b"P4\n"`.
   - Header parsing:
     - Parse only within the first 1,024 bytes.
     - Skip lines beginning with `#`.
     - The next line must hold exactly two ASCII decimal tokens separated by whitespace: width, then height.
     - `header_size` is the offset of the byte after that line's newline.
   - Fields:
     - `magic` at `0x00` as `3s`
     - `width` at its token offset as `<n>s`, where `<n>` is the token length
     - `height` at its token offset as `<n>s`
   - Seed: `bit_depth = 1`, `row_alignment = 1`, `encoding = "none"`.
   - IF the header cannot be parsed, THEN the seed SHALL have `width = 0`, `height = 0`, `header_size = 3`, and the probe SHALL record `probe_precondition_failed`.
8. **TIFF probe.**
   - Minimum length: 8 bytes.
   - Signature: bytes `0x00..0x01 ∈ {b"II", b"MM"}`, and the `uint16` at `0x02` read in the declared byte order equals 42.
   - Byte order: the probe SHALL honour the byte-order mark. Every multi-byte read uses `<` for `II` and `>` for `MM`; the formats below write this prefix as `o`.
   - Fields:
     - `byte_order` at `0x00` as `2s`
     - `magic` at `0x02` as `oH`
     - `ifd_offset` at `0x04` as `oI`
     - `ifd_entry_count` at `ifd_offset` as `oH`
   - IFD entries:
     - Each entry is 12 bytes, at `ifd_offset + 2 + 12k`.
     - Layout: tag at `+0` as `oH`, type at `+2` as `oH`, count at `+4` as `oI`, value at `+8`.
     - A type 3 (SHORT) value is read as `oH` at `+8`. It is left-justified in the 4-byte value field.
     - A type 4 (LONG) value is read as `oI` at `+8`.
     - A tag is used only when its type is 3 or 4 and its count is 1, except tag 258 (`bits_per_sample`), which is read as an array.
   - BitsPerSample array (tag 258):
     - The count `n` SHALL satisfy `1 ≤ n ≤ 32` (`TIFF_MAX_SAMPLES`). A larger count SHALL record `probe_precondition_failed` and the values SHALL NOT be read.
     - WHEN `n × size(type) ≤ 4` (size 2 for SHORT, 4 for LONG), the `n` values SHALL be read consecutively from `+8`, left-justified in the value field. Otherwise the value field SHALL be read as `oI` at `+8`, and the `n` values SHALL be read consecutively from that offset.
     - EACH value SHALL be recorded as a `FieldRecord` named `bits_per_sample` at its own offset, with format `oH` (SHORT) or `oI` (LONG).
     - IF any value lies outside the file, THEN the probe SHALL record `field_out_of_bounds`, and `bits_per_sample` SHALL be treated as not read.
     - IF the values are not all equal, THEN the probe SHALL record `probe_precondition_failed` naming the values, and `bits_per_sample` SHALL be treated as not established (0). The probe SHALL NOT choose one of the values.
     - Otherwise `bits_per_sample` SHALL be the common value.
   - Tags used:
     - 256 `width`
     - 257 `height`
     - 258 `bits_per_sample`
     - 259 `compression` (default 1)
     - 262 `photometric_interpretation` (optional, no default; see below)
     - 273 `strip_offset`
     - 277 `samples_per_pixel` (default 1)
     - 279 `strip_byte_count`
     - 284 `planar_configuration` (default 1)
   - Seed: `bit_depth = bits_per_sample × samples_per_pixel`, `header_size = strip_offset`, declared `data_end = strip_offset + strip_byte_count`, `row_alignment = 1`. `encoding = "none"` when `compression == 1`, otherwise `"tiff_compression_<n>"`.
   - IF `ifd_offset + 2 > len(data)`, or the entry table runs past the end of the file, THEN the probe SHALL record `field_out_of_bounds` and emit the seed from the values read so far.
   - IF any of tags 256, 257, 258, 273 or 279 is missing, THEN the probe SHALL record `probe_precondition_failed`.
   - IF `planar_configuration ≠ 1`, THEN the probe SHALL record `probe_precondition_failed`. Planar configuration 2 stores each channel separately, which is a different layout, and the file declares which one it uses.
   - `samples_per_pixel` SHALL NOT be a precondition. It is read and multiplies `bits_per_sample` to give `bit_depth`.
   - `photometric_interpretation` (tag 262) SHALL be read by the same rule as the other single-valued tags: type SHORT or LONG, count 1, value at entry + 8 in the file's byte order, recorded as a `FieldRecord`. WHEN the tag is absent, or is not readable under that rule, THE probe SHALL record no field and no rejection. Its value SHALL NOT enter the seed, the hypothesis key or the closure check, and tag 262 SHALL NOT be in the required-tag list.
   - Only single-strip TIFF files are in scope.
9. WHEN exactly one distinct seed closes, THE Engine SHALL return `RESOLVED` with `revision_path = []`. WHEN more than one distinct seed closes, THE Engine SHALL return `UNRESOLVED_AMBIGUITY` with stage `probe`. WHEN no seed closes and at least one seed exists, THE Engine SHALL enter the revision phase with every seed as the seed pool.
10. WHERE a probe's signature matches but a declared field required to construct that probe's seed holds a value the probe has no reading for, THE probe SHALL emit no seed and SHALL record exactly one `RejectionEntry` with reason `probe_precondition_failed`, source the probe's name, no hypothesis, and a detail naming the field, its offset and its value. This criterion does not change which bytes form any probe's signature. A value the probe can name but the closure gate cannot decode (for example TIFF compression 5, read as `tiff_compression_5`) is a reading, not this case.

### Requirement 3: Revision Strategies

**User Story:** As a developer, I want failed seeds revised by a small set of strategies that each correspond to a real recovery case, so that damaged or unconventional files are recovered without the engine picking among answers by list order.

#### Acceptance Criteria

1. THE Engine SHALL define exactly three revision strategies. Each strategy produces zero or more candidates, and each candidate's `revision_path` is its parent's path plus the strategy name.
   - **`inclusive_bounds`**: applies only to hypotheses with bounds set. It produces one candidate with `width = xmax − xmin + 1` and `height = ymax − ymin + 1`.
   - **`rle_pcx`**: applies only to hypotheses from the PCX probe with `encoding == "none"`. It produces one candidate with `encoding = "rle_pcx"`.
   - **`row_padding_variants`**: produces one candidate for each `row_alignment` in `(2, 4)` that differs from the hypothesis's current alignment, in that order.
2. THE Engine SHALL search breadth-first by depth from 1 to 3. At each depth, the outer loop SHALL iterate over the hypotheses of the current frontier in frontier order, and the inner loop SHALL apply every strategy, in the order listed in criterion 1, to that hypothesis. The depth-1 frontier is the seeds in probe order. Each later frontier is the previous depth's non-closing candidates in the order they were checked. This loop order defines the canonical path and nothing else.
3. THE Engine SHALL skip, without a closure check, any candidate whose hypothesis key equals the key of a seed or of any previously checked candidate.
4. WHEN at least one candidate closes at a depth, THE Engine SHALL finish that depth, collect every closing candidate from it, and not search deeper.
5. WHEN exactly one candidate closes at that depth, THE Engine SHALL return `RESOLVED` with that candidate's `revision_path`. WHEN more than one closes, THE Engine SHALL return `UNRESOLVED_AMBIGUITY` with stage `revision`.
6. THE order of strategies and seeds SHALL determine only the enumeration order and which same-depth path is canonical. It SHALL NOT determine which candidates are returned, their alternative paths as a set, or the outcome.
7. THE Engine SHALL NOT change byte order, field width or header length during revision. These are Generic Search axes only.
8. WHEN no candidate closes by depth 3, THE Engine SHALL return `FAILED` with termination `exhausted`, and SHALL NOT enter Generic Search.
9. WHEN the Engine skips a candidate under criterion 3 because its key equals the key of a candidate first produced at the same depth, THE Engine SHALL record the skipped candidate's revision path as an alternative path for that key. A skipped candidate whose key matches a seed, or a candidate first produced at an earlier depth, SHALL NOT be recorded.
10. EACH closing candidate from the revision phase SHALL carry `alternative_paths`: the alternative paths recorded for its key, in the order found. THE Engine SHALL build closing candidates only after their depth is complete, so that alternatives found later in the same depth are included. Candidates from the probe phase and Generic Search SHALL have empty `alternative_paths`. `alternative_paths` is informational only and SHALL NOT affect the outcome, the candidate set or the candidate order.

### Requirement 4: Generic Search

**User Story:** As a developer, I want files that match no probe searched over explicit structural axes, with every closing layout reported, so that NECROPSY handles unknown formats without guessing.

#### Acceptance Criteria

1. WHEN no probe emitted a seed, THE Engine SHALL run Generic Search. This includes a probe that declined under Requirement 2.10; its rejection entry is kept.
2. THE Generic Search SHALL try header lengths `L ∈ {4, 8, 12, …, 256}`, every multiple of 4 from 4 to 256 inclusive, in ascending order, and only those with `L < len(data)`. This set already contains every power of 2 from 4 to 256.
3. FOR each header length `L`, THE Generic Search SHALL collect every read of width or height values: every pair of format `f ∈ {<H, >H, <I, >I, <i, >i}` and offset `o` with `o + size(f) ≤ L` whose value is greater than 0, grouped by value. `size` is 2 for `H` formats and 4 for `I` and `i` formats.
4. FOR each header length `L`, THE Generic Search SHALL collect every bit-depth read: every offset `o < L` whose byte is in `{1, 4, 8, 16, 24, 32}`, read as `B`, grouped by value.
5. FOR each header length `L`, THE Generic Search SHALL determine `data_end` with the Trailer Registry. It SHALL try `encoding = "none"` with decoded size `S = data_end − L`. Only when the matched trailer is `pcx_palette_256`, it SHALL also try `encoding = "rle_pcx"` with `S` equal to the run-length output of the whole region, counted without allocating; a truncated final run means the RLE encoding is skipped for that `L`.
6. FOR each encoding with `S > 0`, each width value `W` and each bit-depth value `B`, THE Generic Search SHALL:
   - compute `row_stride = ceil(W × B / 8)` with `row_alignment = 1`;
   - skip the combination when `S mod row_stride ≠ 0`;
   - otherwise set `height = S / row_stride`;
   - skip it unless `height` is a read value and at least one width read and one height read are at different offsets;
   - otherwise run one closure check.
7. EACH Generic Search candidate SHALL carry, as `FieldRecord`s, every equivalent read: one record named `width` per read of `W`, one named `height` per read of the height, and one named `bit_depth` per offset holding `B`.
8. THE Generic Search SHALL collect every closing candidate and SHALL NOT stop at the first. WHEN exactly one closes, THE Engine SHALL return `RESOLVED` with `probe_name = "generic"` and `revision_path = []`. WHEN more than one closes, THE Engine SHALL return `UNRESOLVED_AMBIGUITY` with stage `generic`. WHEN none closes, THE Engine SHALL return `FAILED` with termination `exhausted`, or `no_hypothesis_checked` when no hypothesis reached the closure gate (Requirement 5.12).
9. A `FAILED` result from Generic Search SHALL state only that no closing layout was found within the stated axes and budget. It SHALL NOT claim the file has no valid layout.

### Requirement 5: Failure Report and Termination

**User Story:** As a developer debugging an unresolvable file, I want a complete, ordered record of what was tried and why it stopped, so that I can diagnose the failure without re-running the Engine.

#### Acceptance Criteria

1. THE Engine SHALL accept `deadline_seconds` (default 5.0) at construction. It SHALL check elapsed wall-clock time:
   - before each probe;
   - before each closure check;
   - at the start of each Generic Search header length;
   - before each coherence computation.
2. WHEN the deadline has passed at a check, THE Engine SHALL stop and return `FAILED` with termination `deadline_exceeded`, the rejections so far and the candidates found so far.
3. THE Engine SHALL count closure checks across the probe phase, the revision phase and Generic Search against one shared cap of 10,000. WHEN a further check would exceed the cap, THE Engine SHALL return `FAILED` with termination `search_cap_exceeded`, the rejections so far and the candidates found so far.
4. FOR any input of at most 65,536 bytes, THE Engine SHALL return within `deadline_seconds + 0.25` seconds.
5. EACH `RejectionEntry` SHALL include:
   - the hypothesis parameters;
   - every `FieldRecord` of that hypothesis;
   - a reason from the vocabulary in criterion 6;
   - the discrepancy for `arithmetic_mismatch`, otherwise none;
   - its source: a probe name, a revision path, or `"generic"`.
6. THE reason vocabulary SHALL be exactly:
   - `arithmetic_mismatch`
   - `decoder_overrun`
   - `decoder_underrun`
   - `decoder_unconsumed`
   - `degenerate_hypothesis`
   - `field_out_of_bounds`
   - `probe_precondition_failed`
   - `unsupported_encoding`
   - `input_too_short`
   - `internal_error`
7. THE termination vocabulary of a `FailureReport` SHALL be exactly:
   - `exhausted`
   - `no_hypothesis_checked`
   - `deadline_exceeded`
   - `search_cap_exceeded`
   - `input_too_short`
   - `internal_error`
8. IF the input is shorter than 3 bytes, THEN THE Engine SHALL return `FAILED` with termination `input_too_short` and exactly one `RejectionEntry` with reason `input_too_short`, and SHALL run no probe.
9. THE Engine SHALL record rejections in the order produced: probe phase, then revision phase in breadth-first order, then Generic Search.
10. A `FailureReport` SHALL list any candidates that closed before termination as `partial_candidates`, and SHALL NOT present them as a resolved or ambiguous outcome.
11. EVERY `EngineResult` SHALL carry `rejections`, `total_checks` and `total_file_size`.
12. WHEN a run ends with no closing hypothesis and no hypothesis reached the closure gate (`total_checks == 0`), and no other termination applies, THE Engine SHALL return `FAILED` with termination `no_hypothesis_checked`. Its meaning is only that no hypothesis reached the closure gate. Termination `exhausted` SHALL mean that at least one hypothesis was closure-checked and none closed.

### Requirement 6: Never-Raise Contract

**User Story:** As a developer running NECROPSY on corrupted or adversarial files, I want every component to return a structured value instead of raising, so that no input crashes the system.

#### Acceptance Criteria

1. IF any exception reaches `Engine.run`, THEN THE Engine SHALL return `FAILED` with termination `internal_error` and exactly one `RejectionEntry` whose reason is `internal_error`, with detail `"<ExceptionClass>: <message>"`, and no hypothesis.
2. WHEN given a zero-length input, THE Engine SHALL return a `FailureReport`.
3. WHEN given any byte sequence, THE Engine SHALL return a `VerifiedHypothesis`, an `AmbiguousResult` or a `FailureReport`.
4. THE probes, revision strategies, closure gate, RLE decoder, Generic Search, coherence function, Pretty_Printer and Spec Emitter SHALL each return a structured value and never raise on any input.
5. THE Engine SHALL be tested with a Hypothesis property test over arbitrary byte inputs of up to 65,536 bytes, including mutated corpus files, asserting `run()` never raises and returns one of the three result types.
6. THE Engine SHALL be tested with a Hypothesis property test over the same inputs, using `deadline_seconds = 5.0`, asserting `run()` returns within 5.25 seconds.
7. EACH component in criterion 4 SHALL have its own Hypothesis property test asserting it never raises on arbitrary input and returns its declared type.

### Requirement 7: Test Corpus

**User Story:** As a developer validating the Engine against ground truth, I want each corpus file to assert its exact outcome, so that a strategy or search path that silently breaks fails a test.

#### Acceptance Criteria

1. WHEN given `spike/samples/mystery_a` (PBM P4, 11 bytes), THE Engine SHALL return `RESOLVED` from the PBM probe with `width = 4`, `height = 4`, `bit_depth = 1`, `header_size = 7`, `row_stride = 1` and `revision_path = []`.
2. WHEN given `spike/samples/mystery_b` (PCX, RLE, 955 bytes), THE Engine SHALL return `RESOLVED` from the PCX probe with:
   - `width = 8`, `height = 8`, `bit_depth = 8`, `header_size = 128`;
   - `encoding = "rle_pcx"` and data region `[128, 186)`;
   - trailer `pcx_palette_256`;
   - `revision_path = ["inclusive_bounds"]`;
   - the PCX probe's seed (7×7, `encoding = "rle_pcx"`, header 128) rejected with reason `decoder_unconsumed` and source `pcx`. This value was measured in task 2.3: the stream decodes 49 bytes before the region ends.
3. WHEN given `spike/samples/mystery_c` (TGA, 786 bytes), THE Engine SHALL return `RESOLVED` from the TGA probe with `width = 16`, `height = 16`, `bit_depth = 24`, `header_size = 18`, `row_stride = 48` and `revision_path = []`. Its `image_descriptor` `FieldRecord` SHALL be at offset `0x11` with format `B` and value `0x20` (top-left origin), and SHALL round-trip through `struct.unpack_from`.
4. WHEN given `spike/samples/mystery_d` (headerless DIB body, 104 bytes), THE Engine SHALL return `UNRESOLVED_AMBIGUITY` with stage `generic`, and its candidates SHALL include the hypothesis `width = 8`, `height = 8`, `bit_depth = 8`, `header_size = 40`, `encoding = "none"`. The test SHALL NOT assert candidate order.
5. WHEN given `spike/samples/mystery_e` (TIFF, big-endian `"MM"`, 150 bytes), THE Engine SHALL return `RESOLVED` from the TIFF probe with:
   - `width = 8`, `height = 8`, `bit_depth = 8`, `header_size = 86`;
   - declared data region `[86, 150)`;
   - `revision_path = []`;
   - every multi-byte `FieldRecord` using a `>` format.
6. WHEN given `spike/samples/mystery_f` (12 bytes of 32-bit dimensions, then pixels; 132 bytes), THE Engine SHALL return `UNRESOLVED_AMBIGUITY` with stage `generic`, and its candidates SHALL include `width = 12`, `height = 10`, `bit_depth = 8`, `header_size = 12`, `encoding = "none"`. That candidate's `width` records SHALL include reads at offset `0x00` in at least two distinct formats from `{<H, <I, <i}`, all with value 12.
7. WHEN given `spike/samples/mystery_g` (unusual 20-byte header, 212 bytes), THE Engine SHALL return `UNRESOLVED_AMBIGUITY` with stage `generic`, and its candidates SHALL include `width = 8`, `height = 8`, `bit_depth = 24`, `header_size = 20`, `encoding = "none"`.
8. WHEN given `spike/samples/mystery_h` (PCX, rows padded to 4 bytes, 176 bytes), THE Engine SHALL return `RESOLVED` from the PCX probe with `width = 6`, `height = 6`, `bit_depth = 8`, `header_size = 128`, `row_alignment = 4`, `row_stride = 8` and `revision_path = ["inclusive_bounds", "row_padding_variants"]`, and `alternative_paths` containing `["row_padding_variants", "inclusive_bounds"]`.
9. WHEN given `spike/samples/mystery_i` (PCX, RLE data, encoding byte corrupted to `0x00`, 955 bytes), THE Engine SHALL return `RESOLVED` from the PCX probe with `width = 8`, `height = 8`, `bit_depth = 8`, `header_size = 128`, `encoding = "rle_pcx"` and `revision_path = ["inclusive_bounds", "rle_pcx"]`, and `alternative_paths` containing `["rle_pcx", "inclusive_bounds"]`.
10. FOR every `RESOLVED` corpus file, THE corpus test SHALL compare the decoded pixel bytes exactly with the pixel content that `spike/make_samples.py` writes.
11. THE Engine SHALL return `FAILED` for none of the nine corpus files.
12. WHEN given `spike/samples/external/external_b` (TGA 2.0 written by Pillow, 24 bpp, 9,260 bytes), THE Engine SHALL return `RESOLVED` from the TGA probe with `width = 64`, `height = 48`, `bit_depth = 24`, `header_size = 18`, `revision_path = []`, trailer `tga2_footer`, and data region `[18, 9234)`, which excludes the 26-byte footer. Its `image_descriptor` SHALL be `0x00` (bottom-left origin). Its decoded bytes SHALL equal the pixels of `spike/samples/external/source.ppm` stored bottom row first, in BGR order.
13. WHEN given each of these files from `spike/samples/real/`, THE Engine SHALL return `RESOLVED` from the TIFF probe with `revision_path = []`, `encoding = "none"`, `header_size = 8` and the values below. Each data region equals the declared strip, and its length equals `width × height × bit_depth / 8`:
    - `goimage_no_compress.tiff`: 16×15, `bit_depth = 32` (4 samples of 8 bits), data region `[8, 968)`;
    - `goimage_no_rps.tiff`: 16×15, `bit_depth = 32`, data region `[8, 968)`;
    - `goimage_video-001-uncompressed.tiff`: 150×103, `bit_depth = 24` (3 samples of 8 bits), data region `[8, 46358)`;
    - `sdlimage_sample.tif`: 23×42, `bit_depth = 24`, data region `[8, 2906)`.
14. WHEN given `spike/samples/real/pillow_tiff_strip_planar_raw.tif` (PlanarConfiguration 2), THE Engine SHALL return `FAILED`, and the TIFF probe SHALL have recorded `probe_precondition_failed` naming the planar configuration.
15. WHEN given `spike/samples/real/pillow_ossfuzz-4836216264589312.pcx` (129 bytes, byte `0x00 = 0x0A`, encoding byte `0x02 = 0x20`), THE Engine SHALL return `RESOLVED` from Generic Search as a 2×1, 1-bit literal reading with header 128 and data region `[128, 129)`, and its rejection list SHALL contain exactly one entry: `probe_precondition_failed`, source `pcx`, no hypothesis, with a detail naming the encoding byte at `0x02` and its value `0x20`.
16. WHEN given `spike/samples/real/pillow_p_16.tga` (TGA, 21,563 bytes, 128×128, 8 bpp, colour-mapped), THE Engine SHALL return `RESOLVED` from the TGA probe with `width = 128`, `height = 128`, `bit_depth = 8`, `header_size = 560`, data region `[560, 16944)` (length 16,384 = 128 × 128) and trailer `tga2_footer`. Its decoded pixel bytes SHALL equal the pixel bytes Pillow decodes for that file.
17. WHEN given `spike/samples/real/pillow_rgb32rle.tga` (RLE, image type 10, extension area at 128486, scan-line table at 128981), THE Engine SHALL keep its current outcome: not `RESOLVED`, with the TGA seed rejected with reason `unsupported_encoding`.
18. WHEN given each of these TIFF files from `spike/samples/real/`, THE Engine SHALL return a candidate whose fields include exactly one `photometric_interpretation` `FieldRecord` with the stated value, and the status, candidate key and data region of each file SHALL be unchanged: `goimage_bw-uncompressed.tiff` = 0, `libtiff_miniswhite-1c-1b.tiff` = 0, `libtiff_test_ifd_loop_to_self.tif` = 1, `goimage_no_compress.tiff` = 2, `goimage_no_rps.tiff` = 2, `goimage_video-001-uncompressed.tiff` = 2, `sdlimage_sample.tif` = 2. WHEN given `spike/samples/mystery_e`, THE Engine SHALL return a candidate with no `photometric_interpretation` `FieldRecord`, and every other value in Requirement 7.5 unchanged.

### Requirement 8: Field Integrity and Rendering

**User Story:** As a developer verifying a result, I want every field reproducible from the bytes and every outcome rendered distinctly, so that results can be checked independently and the two success outcomes are never confused.

#### Acceptance Criteria

1. THE Engine SHALL record each field read as a `FieldRecord` with name, offset, format and the tuple returned by `struct.unpack_from`.
2. FOR every `FieldRecord` of every candidate in a `RESOLVED` or `UNRESOLVED_AMBIGUITY` result, `struct.unpack_from(record.fmt, data, record.offset)` SHALL equal `record.value`.
3. WHERE several `FieldRecord`s of a candidate share a name, they SHALL all hold the same interpreted value. The set states that the bytes cannot distinguish those reads.
4. WHEN rendering `RESOLVED`, THE Pretty_Printer SHALL output, in order:
   - the line `RESOLVED`;
   - a field table with columns offset as `0x%04X`, field name, struct format, and value;
   - the closure line:
     - for `none`: `closure: [{start}, {end}) holds {end − start} bytes = {row_stride} x {height}`;
     - for `rle_pcx`: `closure: rle_pcx decoded [{start}, {end}) to {expected} bytes = {row_stride} x {height}, all input consumed`;
   - the line `trailer: {name}` when a trailer matched;
   - the line `revision_path: {revision_path}`;
   - the line `alternative_paths: {alternative_paths}` when `alternative_paths` is non-empty.
5. WHEN rendering `UNRESOLVED_AMBIGUITY`, THE Pretty_Printer SHALL output:
   - the line `UNRESOLVED_AMBIGUITY: {n} candidates close; the bytes cannot distinguish them`;
   - the stage;
   - every candidate, numbered in discovery order, with its dimensions, bit depth, header size, alignment, encoding, and either `coherence (heuristic, row_mad_ratio): {score:.4f}` or `coherence (heuristic): {status}`.
   It SHALL mark no candidate as preferred.
6. WHEN rendering `FAILED`, THE Pretty_Printer SHALL output the line `FAILED: {termination}`, the rejection and check counts, and a numbered list of rejections. Each rejection shows its source, its reason, and `(discrepancy={n})` when a discrepancy is set.
7. THE Pretty_Printer SHALL be a pure function outside `necropsy/engine/`, and SHALL never raise.

### Requirement 9: Spec Emission

**User Story:** As a NECROPSY user, I want the engine to emit a Kiro-format spec for the format it recovered, so that a recovered format can drive a real spec-driven build without the original file.

#### Acceptance Criteria

1. WHEN given a `VerifiedHypothesis` or an `AmbiguousResult` together with the source bytes, THE Spec Emitter SHALL produce a folder named `<slug>/` containing exactly `requirements.md`, `design.md` and `test_<module>.py`, where `<module>` is the slug with `-` replaced by `_` (for example `test_tiff.py` or `test_unknown_9b3b124b.py`). The test file name SHALL match pytest's default discovery pattern `test_*.py`, so that running `pytest` in the folder finds it with no configuration. The test file imports `parser_<module>`, which the Spec Emitter deliberately does not emit; until a reader implements that module, `pytest` on the folder as emitted SHALL stop with `ModuleNotFoundError` and run no tests (measured: exit code 2, `1 error during collection`). THE Spec Emitter SHALL NOT emit a pytest configuration file.
2. THE slug SHALL be the probe name (`pcx`, `tga`, `pbm` or `tiff`) when a probe produced the result, and `unknown-<first 8 hex digits of the SHA-256 of the source bytes>` when Generic Search produced it.
3. THE emitted `requirements.md` SHALL use the Kiro requirements structure (Introduction, Glossary, Requirements with user stories and EARS acceptance criteria).
4. THE emitted `requirements.md` SHALL state, for every field, one acceptance criterion giving its name, offset in hex, struct format, endianness and size.
5. THE emitted `requirements.md` SHALL state the data region rule, the trailer rule if one applies, the encoding, and the closure rule that verified the result.
6. THE emitted `requirements.md` SHALL contain exactly one layout block in schema `necropsy-layout/1`.
7. WHEN a probe produced the result, THE emitted spec SHALL have layout kind `format` and describe the format's rules, including the byte-order rule and the IFD walk for TIFF, together with the values observed in the source file.
   - WHERE the result's revision path contains `inclusive_bounds`, the width and height rules SHALL be the inclusive-bounds expressions.
   - WHERE the revision path contains `rle_pcx`, the encoding SHALL be `rle_pcx`, and the spec SHALL state that the file's encoding declaration was overridden by revision.
   - FOR PBM, whose text header the layout schema cannot express, the layout kind SHALL be `file`, and the format's text-header rules SHALL be stated in prose.
8. WHEN Generic Search produced the result, THE emitted spec SHALL have layout kind `file`, and SHALL state explicitly that it describes this file's layout only and not a format.
9. WHEN the result is `UNRESOLVED_AMBIGUITY`, THE emitted `requirements.md` SHALL:
   - state every candidate;
   - state that each candidate passes closure;
   - state that the bytes cannot separate them, and that coherence is a heuristic with known failure modes;
   - assert no single candidate.
   Its layout block SHALL have kind `ambiguous` and list every candidate layout.
10. THE emitted `design.md` SHALL use the Kiro design structure and state:
    - the resolved structure or the candidates;
    - the stage and source;
    - the revision path;
    - the data region and trailer;
    - the closure arithmetic;
    - each candidate's coherence, labelled as a heuristic;
    - every rejected hypothesis with its reason. When there are more than 500 rejections, it shall list the first 500 and state how many were omitted.
11. THE emitted `test_<module>.py` SHALL contain Hypothesis property tests against the module `parser_<module>`:
    - `parse(data)` never raises on arbitrary bytes of up to 65,536 bytes;
    - every field record that `parse` reports round-trips through `struct.unpack_from`;
    - whenever `parse` succeeds, the decoded pixels contain exactly `row_stride × height` bytes.
    For an ambiguous result, the tests SHALL target `parse_candidates(data)` instead.
12. THE emitted `test_<module>.py` SHALL embed the source bytes in base64 as a fixture when the source is at most 65,536 bytes. Its fixture tests SHALL assert the observed field values and closure. When the source is larger, the fixture tests SHALL skip with a stated reason.
13. WHEN given a `FailureReport`, THE Spec Emitter SHALL write nothing and return an `EmitError` stating that nothing was recovered.
14. THE Spec Emitter SHALL be pure until a separate write step.
15. THE write step SHALL:
    - write only inside the given output directory;
    - accept only slugs matching `[a-z0-9-]+`;
    - refuse to overwrite an existing folder unless `overwrite = True`;
    - make no network call;
    - never raise.
16. WHEN the spec emitted for `mystery_e` is given to the reference reader, THE reference reader SHALL use only the emitted `requirements.md` as its source of format knowledge, and SHALL reproduce from `mystery_e`'s bytes:
    - `width = 8`, `height = 8`, `bit_depth = 8`;
    - data region `[86, 150)`;
    - pixel bytes identical to the engine's.
    The original file SHALL be used only to check the result.
17. WHEN a parser module is built from the reference reader and the emitted `requirements.md`, and placed in one folder with the emitted `test_<module>.py`, THEN running pytest on that folder, with no file argument and no configuration file, SHALL collect the emitted tests and pass, for `mystery_c` and `mystery_e`.
18. WHEN the spec emitted for `mystery_d` is given to the reference reader, THE reference reader SHALL enumerate candidates that include the true layout.
19. THE emitted `requirements.md` and `design.md` for `mystery_e` and `mystery_d` SHALL pass Kiro's spec format validation.
20. WHEN a probe produced the result and that probe recorded `probe_precondition_failed` or `field_out_of_bounds` (a `RejectionEntry` whose source is the probe's name and whose reason is one of those two), THE emitted spec SHALL have layout kind `file` with this file's literal values for the image dimensions, bit depth, alignment, data region and encoding, and SHALL state explicitly that it describes this one file only and not the format, because the file broke the format's own rules. This criterion takes precedence over criterion 7. For an `AmbiguousResult` it applies to each candidate separately.
21. WHERE the TIFF layout's tag table has an array entry (`bits_per_sample`), THE emitted `requirements.md` SHALL state its rules: the count range, where the values are read (inline when they fit the 4-byte value field, otherwise at the offset held in it), that every value must be equal, and that the field's value is that common value. THE reference reader SHALL apply those rules from the layout alone.
22. WHERE a tag table entry declares an expected value (`planar_configuration` = 1), THE emitted `requirements.md` SHALL state it, and THE reference reader SHALL return an error when the value read differs.
23. WHERE a layout's trailer carries declared offsets (the `tga2_footer`), THE emitted layout's `data.trailers` entry SHALL describe them as data: positions relative to the trailer start, struct formats, and the nested extension area with its size field, its minimum size 495 and the positions of its inner offsets.
24. WHERE a layout's trailer carries declared offsets, THE emitted `requirements.md` SHALL state the rule in EARS: an offset of 0 means the area is absent; a valid offset lies in `[header_size, footer_start)`; the minimum of the footer start and the valid offsets ends the data region; an invalid offset or an invalid extension area rejects the file.
25. WHERE a layout's trailer carries declared offsets, THE reference reader SHALL apply the rule of criterion 24 from the layout alone, with no format knowledge. The spec emitted for `pillow_p_16.tga`, given to the reference reader, SHALL yield the data region `[560, 16944)`.
26. WHERE the TIFF candidate read `photometric_interpretation`, THE emitted layout's tag table SHALL contain, after `planar_configuration`, the entry `{"name": "photometric_interpretation", "tag": 262, "default": null, "expect": null, "array": null, "optional": true}`, and THE emitted `requirements.md` SHALL contain one EARS line stating that WHERE tag 262 is present the parser SHALL read it as `photometric_interpretation` and that its absence adds no field. WHERE the candidate did not read it, the tag table and `requirements.md` SHALL be unchanged. THE reference reader SHALL treat an entry with `optional: true` whose tag is absent as adding no value and no field, and SHALL NOT raise. The value is reported only; no emitted rule acts on it.

### Requirement 10: Outcomes and Ambiguity

**User Story:** As a NECROPSY user, I want the engine to tell me clearly whether it found one answer, several equally valid answers or none, so that I can trust what it says.

#### Acceptance Criteria

1. EVERY `EngineResult` SHALL carry a `status` field with value `RESOLVED`, `UNRESOLVED_AMBIGUITY` or `FAILED`, so that a UI can render each outcome differently without inspecting other fields.
2. A `VerifiedHypothesis` SHALL hold exactly one candidate together with its source and `revision_path`.
3. AN `AmbiguousResult` SHALL hold at least two candidates with distinct hypothesis keys, in discovery order, together with:
   - its stage (`probe`, `revision` or `generic`);
   - a `reason` stating that every candidate passes closure and that the bytes cannot separate them.
4. THE Engine SHALL treat `RESOLVED` and `UNRESOLVED_AMBIGUITY` as successful outcomes, and `FAILED` as the only error outcome.
5. THE Engine SHALL promote no candidate of an `AmbiguousResult` by any heuristic, score or ordering.

### Requirement 11: Row Coherence Heuristic

**User Story:** As a user looking at an ambiguous result, I want a visual-plausibility hint on each candidate that is clearly labelled as a heuristic, so that I get useful information without the engine pretending to decide.

#### Acceptance Criteria

1. THE Engine SHALL compute row coherence only for candidates that have passed closure. Coherence SHALL never gate, promote or order candidates, and the outcome and candidate order SHALL be identical whatever values coherence returns.
2. THE Engine SHALL compute coherence over a candidate's decoded bytes, reshaped to `height` rows of `row_stride` bytes.
   - Let `mad(a, b)` be the mean over the row of `|a_k − b_k|`.
   - `adjacent` is the mean of `mad` over the vertically adjacent row pairs `(i, i + 1)`.
   - `baseline` is the mean of `mad` over every distinct row pair `(i, j)` with `i < j`. When there are more than 1,024 such pairs, it uses the 1,024 pairs chosen by `random.Random(0).sample(range(P), 1024)`, where `P` is the pair count and index `k` maps to the `k`-th pair in lexicographic order.
   - `coherence_score = adjacent / baseline`. A lower score means more coherent.
3. WHEN `height < 2`, or all rows are identical so that `baseline = 0`, THE candidate SHALL have `coherence_status = "unscorable"` and `coherence_score = None`.
4. THE candidate SHALL have `coherence_status = "not_computed"` and `coherence_score = None` whenever its coherence was not computed, for either of two reasons: `expected_decoded_bytes > 262,144`, so that computation time stays bounded; or the run terminated (deadline or cap) before that candidate's coherence step. No other status SHALL be used for these cases.
5. EVERY candidate SHALL report `coherence_score`, `coherence_status` (`scored`, `unscorable` or `not_computed`) and `coherence_method = "row_mad_ratio"`.
6. AN `AmbiguousResult` SHALL report `coherence_gap = (second − first) / second` over the two lowest scores, for information only. The gap SHALL be `None` when fewer than two candidates are scored or the second-lowest score is 0.
7. THE coherence function's docstring SHALL name its three known failure modes:
   - narrower strides score better on smooth images;
   - identical bytes at an identical stride, split into different bit depths, score identically;
   - a header can absorb whole rows.
8. IF any candidate is unscorable or not computed, THEN no candidate SHALL be promoted.

### Requirement 12: Header and Data Are Disjoint

**User Story:** As a user of NECROPSY, I want the engine never to claim that the same bytes are both header fields it parsed and pixel data it decoded, so that a resolved layout is internally consistent.

#### Acceptance Criteria

1. THE closure gate SHALL reject with reason `degenerate_hypothesis` any hypothesis whose data region `[data_start, data_end)` intersects the byte range `[offset, offset + struct.calcsize(fmt))` of any of that hypothesis's own `FieldRecord`s.
2. THE closure gate SHALL apply this check after determining `data_end` and before decoding, so that it applies to the probe phase, the revision phase and Generic Search alike.
3. THE check SHALL use only the hypothesis's own `FieldRecord`s and data region, and no format knowledge. A field located after the data region, such as a TIFF IFD placed after the image data, SHALL NOT cause a rejection.
4. A hypothesis with no `FieldRecord`s SHALL NOT be rejected by this rule.

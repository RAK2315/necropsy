# Requirements Document

## Introduction

The engine reads PCX, TGA, binary PBM (P4) and single-strip uncompressed TIFF. On real files it refuses a large share of layouts that those formats declare about themselves. The 81-file real corpus (`spike/samples/real/`) measures this: 26 files are in the engine's stated scope today and 55 are out of it, most of them for a reason that is a layout, not a limit of the closure gate.

This spec extends the engine to read six more declared layouts and nothing else:

1. PNM binary greymap and pixmap, P5 and P6.
2. PNM plain text, P1, P2 and P3.
3. TGA run-length image types 9, 10 and 11.
4. Multi-plane PCX (the `planes` byte at `0x41` greater than 1).
5. Uncompressed TIFF in several strips, then tiled uncompressed TIFF.
6. Compressed TIFF: PackBits (32773), LZW (5), Deflate (8 and 32946) and LZMA (34925).

Everything the engine rules already say still holds: the closure gate is a hard gate on the decoded stream (engine Decision Record items 1 and 4), probes read what a file states about itself and apply the format's fixed layout and never encode knowledge that is not in the file (item 2), and when several readings close the engine reports all of them and chooses none (items 6 and 7). This spec adds layouts and decoders. It does not change the gate, the revision strategies, Generic Search or the reason and termination vocabularies.

Engine requirement numbers are written "engine Requirement N.M". Requirement numbers below are this spec's own.

## Glossary

- **Data range**: a half-open byte interval `[start, end)` of the file that holds coded or raw pixel data. A hypothesis has one data range unless it declares several.
- **Unit**: the thing one data range holds: the whole image (today's layouts), one strip, one tile, or, for PCX, one scanline of all planes.
- **Decoder**: a function that turns one data range into the bytes of its unit. Decoders are `pnm_text`, `rle_tga`, `packbits`, `lzw_tiff`, `deflate_zlib` and `lzma_xz`. The existing `rle_pcx` decoder is unchanged.
- **Decoder result**: the four states `ok`, `overrun`, `underrun`, `unconsumed`, with `consumed_to`, defined for each decoder in Requirements 2 to 4 and 11 to 14 in the way engine Requirement 1.11 defines them for `rle_pcx`.
- **Declared row bytes**: a scanline length the file states directly, instead of one derived from width and bit depth. Only multi-plane PCX uses it (`planes Ã— bytes_per_line`).
- **Maximum value** (`maxval`): the PNM header's declared largest sample value. P1 has no such field and its maximum is 1.
- **Whole-strip rows**: the number of image rows a strip holds, `min(RowsPerStrip, height âˆ’ index Ã— RowsPerStrip)`; the last strip holds the remaining rows.
- **Tile grid**: `ceil(width / TileWidth)` tiles across and `ceil(height / TileLength)` down, in row-major order, which is the order of the TileOffsets array.
- **Predictor**: TIFF tag 317. A declared pre-compression transform.
- **Expected diff**: before a change, the list of corpus files whose status changes and the statement that nothing else does. After the change the same comparison is measured (Requirement 20).
- **Corpus**: the 81 files of `spike/samples/real/`. **Samples**: the 11 files of `spike/samples/` and `spike/samples/external/`.

## Principle calls

These five calls were decided by Claude Code on Rehaan's delegation, on 25 November 2026. They are requirements as written and are added to the engine Decision Record as items 28 to 32 (Task 1).

### Requirement 1: Principle calls

**User Story:** As the builder, I want the five rules that decide where the gate stands stated once, word for word, so that no later task re-derives them differently.

#### Acceptance Criteria

1. (Call 1, item 28) Text PNM (P1/P2/P3): a layout fits only if, after the header, the file holds exactly width Ã— height (Ã— 3 for P3) numbers, each within the declared maximum value (P1: 0 or 1), and nothing else but whitespace and comments.
2. (Call 2, item 29) Compressed TIFF (PackBits, LZW, Deflate, LZMA): a layout fits only if each strip decodes to exactly its rows Ã— row bytes AND decoding ends exactly at the declared end of the strip (all strip bytes consumed, nothing left). Files whose encoder pads strips will FAIL and are reported as such. Same hard gate as today, no tolerance.
3. (Call 3, item 30) TGA run-length data is one continuous stream of packets over the whole image. A packet that runs across the end of a row is not rejected: the TGA 2.0 specification says packets "should" not cross rows, which is advice to encoders, not a rule the file declares. Closure is the same as for every encoding: the output is exactly width Ã— height pixels and the packets end exactly at the end of the data region.
4. (Call 4, item 31) TIFF Predictor (tag 317) is a declaration. Four files in `spike/samples/real/` declare Predictor 2. A file declaring a Predictor value the engine does not implement is refused with that tag and value named. It is never decoded as if Predictor were 1. (Implementing Predictor 2 is not in this spec.)
5. (Call 5, item 32) PNM binary samples (P5/P6) follow the same maximum-value rule as call 1: a sample above the declared maximum value fails closure. The maximum value is the file's declaration, so this rule is derivable, not a threshold.

Requirements 3, 4, 5, 8 and 12 to 15 turn these calls into testable criteria.

## Requirements

### Requirement 2: Scope, refusals and the decoder contract

**User Story:** As a developer, I want the new layouts to be exactly the six listed, every other layout refused with its reason named, and every decoder to obey one contract, so that the engine does not drift into a general image library.

#### Acceptance Criteria

1. THE Engine SHALL read, beyond the layouts it reads before this spec, only the six layouts in the Introduction. A layout not listed there SHALL keep today's outcome.
2. WHEN a TIFF declares a Compression value other than 1, 5, 8, 32773, 32946 or 34925, THE TIFF probe SHALL emit the seed with `encoding = "tiff_compression_<n>"` for that value and THE closure gate SHALL reject it with reason `unsupported_encoding`. The rejection's hypothesis therefore names the code. This SHALL hold, by test, for CCITT (2, 3, 4), old-style JPEG (6), JPEG (7), SGILog (34676), ZSTD (50000) and WebP (50001).
3. WHEN a TIFF declares PlanarConfiguration other than 1, THE TIFF probe SHALL record `probe_precondition_failed` naming the planar configuration (unchanged from engine Requirement 2.8 and 7.14), and THE Engine SHALL return `FAILED`.
4. THE new PNM probe (Requirement 3) SHALL NOT match `P0`, `P4`, `P7`, `P8`, `P9`, or any file whose third byte is not whitespace. P4 stays with the PBM probe, exactly as engine Requirement 2.7 states it.
5. WHEN given the 54 bytes of a BMP file header (`BM`, size, reserved, data offset 54, `BITMAPINFOHEADER`) followed by pixel bytes, NO probe SHALL emit a seed. The result is whatever the engine returns for it today.
6. THE engine package `necropsy/engine/` SHALL import only the Python standard library and itself. A test SHALL parse every module under that package and fail on any other import. Pillow and every other image library stay in `tools/` and `tests/` only. `zlib` and `lzma` are the standard-library modules that Deflate and LZMA use. PackBits, LZW, TGA RLE and PNM text are written in this repository.
7. EVERY decoder SHALL have the signature `decode(data, start, end, <layout parameters>, max_output_bytes)` and SHALL return a decoder result `(status, data, consumed_to, detail)` with `status` one of `ok`, `overrun`, `underrun`, `unconsumed`, `data` the decoded bytes when `status` is `ok` and `None` otherwise, and `detail` a short string (empty when `ok`).
8. EVERY decoder SHALL check, before each write, whether the write would take the output beyond `max_output_bytes`, and if so SHALL return `overrun` without writing it. The output SHALL never exceed `max_output_bytes`. `zlib` and `lzma` SHALL be called with a `max_length` of `max_output_bytes + 1`, so that they never allocate more than that.
9. EVERY decoder SHALL return `ok` only when the output length equals `max_output_bytes` AND the decoder stopped exactly at `end`, as each decoder defines that stop. `consumed_to` SHALL be the index of the first byte not consumed, with the per-decoder definitions below.
10. WHEN `start < 0`, `end > len(data)`, `start > end` or `max_output_bytes < 0`, EVERY decoder SHALL return `underrun` with `consumed_to = start` and no output, the same way `rle_pcx_decode` does.
11. WHEN a stream is malformed in a way that no other state describes (a code with no meaning, a stray token, a corrupt `zlib` or `lzma` stream), THE decoder SHALL return `underrun`. The engine reason vocabulary (engine Requirement 5.6) gains no member, so no consumer needs to learn a new reason. The decoder's `detail` SHALL say what was malformed.
12. THE closure gate SHALL map decoder states to `decoder_overrun`, `decoder_underrun` and `decoder_unconsumed` (engine Requirement 1.12), and SHALL carry the decoder's `detail` on the `RejectionEntry`.
13. WHEN a hypothesis names a decoder encoding and `expected_decoded_bytes` is greater than `DECODE_CAP = 8,388,608` (8 MiB), THE closure gate SHALL reject it with reason `degenerate_hypothesis` and a detail naming the size and the cap, before any decoding. THE `none` encoding allocates nothing sized from the input and is not capped.
14. EVERY decoder, every new probe and every new closure rule SHALL have a Hypothesis property test, on `st.binary()`, asserting that it never raises and that its return type is the declared type (steering `parsers.md`).
15. NO decoder SHALL read the clock, a random source or global mutable state.

### Requirement 3: PNM probe and binary PNM (P5, P6)

**User Story:** As a user dropping a binary greymap or pixmap, I want the file read from its own header, so that it resolves without guessing.

#### Acceptance Criteria

1. THE Engine SHALL run five probes in the order PCX, TGA, PBM, PNM, TIFF, and SHALL run every probe even after an earlier one's seed closes. This amends engine Requirement 2.1 by adding the PNM probe between PBM and TIFF.
2. THE PNM probe SHALL have minimum length 4 bytes and signature: byte `0x00 == 0x50` (`P`), byte `0x01` in `{0x31, 0x32, 0x33, 0x35, 0x36}` (`1`, `2`, `3`, `5`, `6`), and byte `0x02` an ASCII whitespace byte (`0x20`, `0x09`, `0x0A`, `0x0B`, `0x0C`, `0x0D`). IF the signature does not match, THEN the probe SHALL emit no seed and record no rejection.
3. THE PNM probe SHALL parse the header only within `data[:1024]` with this grammar: the magic (2 bytes), then one or more whitespace bytes, with comments allowed anywhere a whitespace run is allowed (a comment is `#` and every byte up to and including the next `0x0A` or `0x0D`), then width as a run of ASCII digits, then whitespace or comments, then height, then, for P2, P3, P5 and P6 only, whitespace or comments and the maximum value. A token ends at the first byte that is not an ASCII digit.
4. FOR P5 and P6, exactly one whitespace byte SHALL follow the maximum value, and `header_size` SHALL be the index of the byte after it. A comment SHALL NOT sit between the maximum value and that byte.
5. THE probe SHALL record these `FieldRecord`s: `magic` at `0x00` as `2s`; `width`, `height` and (P2, P3, P5, P6) `maxval` each at its token offset as `<n>s`, `n` the token length.
6. FOR P5 and P6 the seed SHALL be: `width`, `height` as read; `maxval` as read; `bit_depth = 8` (P5) or `24` (P6) when `maxval â‰¤ 255`, and `16` (P5) or `48` (P6) when `256 â‰¤ maxval â‰¤ 65535`; `row_alignment = 1`; `encoding = "none"`; `probe_name = "pnm"`.
7. IF the header cannot be parsed, a dimension is 0, the maximum value is 0 or above 65535, or the single whitespace byte of criterion 4 is missing, THEN the probe SHALL still emit a seed with the values that could not be read set to 0 (a `bit_depth` of 0 when the maximum value is unusable) and SHALL record `probe_precondition_failed` with a detail naming the field.
8. THE closure gate SHALL apply the `none` rule of engine Requirement 1.7 to a P5 or P6 hypothesis unchanged: the data region `[header_size, len(data))` SHALL hold exactly `row_stride Ã— height` bytes. No PNM trailer SHALL exist: the data region ends at the end of the file.
9. WHEN a hypothesis has a `maxval` and encoding `none`, THE closure gate SHALL, after the length rule passes, read each sample of the data region (1 byte, or 2 bytes big-endian when `bit_depth` per sample is 16) and SHALL reject the hypothesis with reason `decoder_overrun`, and a detail naming the first offending sample's offset and value and the maximum, WHEN any sample is greater than `maxval`. This is Principle call 5, and it is derived from the file's own declaration, not from a threshold. No allocation SHALL be sized from `maxval`.
10. THE decoded bytes of an accepted P5 or P6 candidate SHALL be the raster bytes as stored: row-major, top row first, samples in the stored order (R, G, B for P6), 16-bit samples big-endian.

### Requirement 4: PNM plain text (P1, P2, P3)

**User Story:** As a user dropping an ASCII PNM, I want it read exactly as its header declares, with any number that does not fit refused.

#### Acceptance Criteria

1. FOR P1, P2 and P3 the PNM probe SHALL parse the header with Requirement 3's grammar, and `header_size` SHALL be the index of the byte after the last header token (the height for P1, the maximum value for P2 and P3). No whitespace byte is consumed beyond that token.
2. THE seed SHALL be: `bit_depth = 1` and `maxval = 1` (P1), `8` or `16` (P2), `24` or `48` (P3) with the maximum value read; `row_alignment = 1`; `encoding = "pnm_text"`; `probe_name = "pnm"`. For P2 and P3, `bit_depth` follows Requirement 3.6.
3. THE `pnm_text` decoder SHALL have the signature `pnm_text_decode(data, start, end, width, height, bit_depth, maxval, max_output_bytes)`, and SHALL treat `data[start:end]` as a sequence of whitespace, comments and tokens. Whitespace is `0x20`, `0x09`, `0x0A`, `0x0B`, `0x0C`, `0x0D`. A comment is `#` through the next `0x0A` or `0x0D`. A token is a maximal run of bytes that are neither whitespace nor `#`.
4. THE decoder SHALL expect exactly `N = width Ã— height` numbers (P1, P2) or `N = width Ã— height Ã— 3` numbers (P3; `bit_depth` 24 or 48), and each number SHALL be a token of ASCII digits whose value is at most `maxval`. A token of more than five digits after its leading zeros is above every possible maximum value.
5. THE decoder SHALL output: for `bit_depth = 1`, the pixels packed 8 per byte, most significant bit first, each row padded with zero bits to a whole byte, where a number 1 is a set bit (black, as in P4); for the other depths, one byte per number when `maxval â‰¤ 255`, and two bytes big-endian when `maxval > 255`.
6. WHEN the next number would be written and its value is greater than `maxval`, or the write would exceed `max_output_bytes`, THE decoder SHALL return `overrun` without writing it, with `consumed_to` the index after that token.
7. WHEN a token that is not all ASCII digits is met before `N` numbers are written, THE decoder SHALL return `underrun` with `consumed_to` the index of the token's first byte and a detail naming it. WHEN the region ends before `N` numbers are written, THE decoder SHALL return `underrun` with `consumed_to = end`.
8. WHEN `N` numbers are written and anything but whitespace and comments remains in `data[start:end]`, THE decoder SHALL return `unconsumed` with `consumed_to` the index of the first byte of the first stray token. This covers a `N + 1`th number.
9. WHEN `N` numbers are written and only whitespace and comments remain, THE decoder SHALL return `ok` with `consumed_to = end`.
10. THE closure gate SHALL run `pnm_text_decode` over `[header_size, len(data))` with `max_output_bytes = expected_decoded_bytes` and accept the hypothesis only when the decoder returns `ok` (engine Requirement 1.8 in the same form).
11. A P1 file that writes its pixels as runs of digits without separators SHALL fail closure under criterion 4, because a run is one token that is not 0 or 1. The result is reported as measured (Requirement 19.4).

### Requirement 5: TGA run-length (types 9, 10, 11)

**User Story:** As a user dropping an RLE TGA, I want the packets decoded as one stream and the image closed by arithmetic like every other layout.

#### Acceptance Criteria

1. THE TGA probe SHALL be unchanged: it already reads `image_type` at `0x02` and seeds `encoding = "rle_tga"` for 9, 10 and 11, with `header_size = 18 + id_length + color_map_type Ã— color_map_length Ã— ceil(color_map_entry_size / 8)`.
2. THE `rle_tga` decoder SHALL have the signature `rle_tga_decode(data, start, end, pixel_bytes, max_output_bytes)`, with `pixel_bytes = ceil(bit_depth / 8)`.
3. THE decoder SHALL read packets from `start` while fewer than `max_output_bytes` bytes are written and the region is not exhausted. A packet header is one byte `h`. WHEN `h â‰¥ 0x80`, THE packet is a run: the next `pixel_bytes` bytes are one pixel, written `(h & 0x7F) + 1` times. WHEN `h < 0x80`, THE packet is raw: the next `(h + 1) Ã— pixel_bytes` bytes are written as they are.
4. THE packets SHALL be one continuous stream over the whole image. A packet that runs across the end of a row SHALL NOT be rejected (Principle call 3).
5. WHEN a packet's write would take the output beyond `max_output_bytes`, THE decoder SHALL return `overrun` without writing it, with `consumed_to` the index after the packet's last byte.
6. WHEN the region ends inside a packet, or before `max_output_bytes` bytes are written, THE decoder SHALL return `underrun` with `consumed_to = end`.
7. WHEN `max_output_bytes` bytes are written and bytes of the region remain, THE decoder SHALL return `unconsumed` with `consumed_to` the index of the first leftover byte. WHEN it stops exactly at `end`, it SHALL return `ok`.
8. THE closure gate SHALL run the decoder over `[header_size, data_end)` with the `data_end` that the Trailer Registry gives (engine Requirements 1.3, 1.15 and 1.17), so that a TGA 2.0 footer, extension area and developer area are excluded exactly as they are for `none`.
9. THE closure gate SHALL stop rejecting `rle_tga` with `unsupported_encoding`. Every other unknown encoding SHALL still be rejected so (engine Requirement 1.13).
10. THE decoded bytes SHALL be the pixel bytes as stored, in the same layout as for image types 1, 2 and 3, so that the existing TGA orientation and channel rules apply unchanged.

### Requirement 6: Multi-plane PCX

**User Story:** As a user dropping a PCX with several colour planes, I want each scanline read as the file declares it, `planes Ã— bytes_per_line` bytes.

#### Acceptance Criteria

1. THE PCX probe SHALL keep every field and offset of engine Requirement 2.5 and SHALL read no new byte. The `planes` byte at `0x41` and `bytes_per_line` (`<H` at `0x42`) are already recorded.
2. WHEN `planes > 1`, THE seed SHALL additionally set `planes` to the declared value, `row_bytes = planes Ã— bytes_per_line`, and `bit_depth = bit_depth_byte Ã— planes` (the bits per pixel across all planes). WHEN `planes â‰¤ 1`, THE seed SHALL be exactly as before: `planes = 1`, `row_bytes` unset.
3. WHEN `row_bytes` is set, THE row stride SHALL be `row_bytes`, and `expected_decoded_bytes = row_bytes Ã— height`. The `row_alignment` SHALL NOT enter the row stride. This is a declaration read, not a convention.
4. WHEN `row_bytes` is set, THE closure gate SHALL reject the hypothesis with reason `degenerate_hypothesis` and a detail if `bit_depth` is not a multiple of `planes`, or `bytes_per_line < ceil(width Ã— (bit_depth / planes) / 8)`: a scanline whose declared plane length cannot hold the width contradicts itself.
5. THE `row_padding_variants` strategy SHALL produce no candidate for a hypothesis whose `row_bytes` is set, because the file already declares its padding. `inclusive_bounds` and `rle_pcx` SHALL apply unchanged. No strategy is added.
6. THE decoded bytes SHALL be the scanlines as stored: scanline by scanline, and within each scanline plane 0 first, then plane 1, each plane `bytes_per_line` bytes.
7. THE rest of the closure rules (the trailer registry's `pcx_palette_256` entry, `rle_pcx` decoding, engine Requirement 12) SHALL apply to multi-plane hypotheses unchanged.
8. THE result for a single-plane PCX SHALL be identical to the result before this spec (same status, keys, paths and rejections).

### Requirement 7: Several data ranges

**User Story:** As a developer, I want a layout with strips or tiles represented in the hypothesis and the result without changing what any existing field means.

#### Acceptance Criteria

1. THE `Hypothesis` SHALL gain these optional fields with these defaults, and every existing field and its meaning SHALL stay: `planes: int = 1`, `row_bytes: int | None = None`, `ranges: tuple[tuple[int, int], ...] = ()`, `rows_per_strip: int | None = None`, `tile: tuple[int, int] | None = None` (TileWidth, TileLength), `maxval: int | None = None`.
2. WHEN `ranges` is empty, THE data region SHALL be the single range `[header_size, data_end)` exactly as before. WHEN `ranges` is non-empty, `header_size` SHALL be the smallest range start and the declared `data_end` the largest range end, so that every existing consumer of those two fields sees the envelope of the data.
3. THE `hypothesis_key` SHALL stay the seven-tuple `(width, height, bit_depth, header_size, row_alignment, encoding, data_end)` for a hypothesis whose new fields are all at their defaults, and SHALL append one eighth element, the tuple `(planes, row_bytes, ranges, rows_per_strip, tile, maxval)`, otherwise. Two hypotheses with different ranges are therefore different hypotheses.
4. THE `Candidate` SHALL gain `ranges: tuple[tuple[int, int], ...] = ()`: the ranges that closed, in order. `data_start` and `data_end` SHALL be the smallest start and the largest end of those ranges, which is `[header_size, data_end)` for a single range, as before.
5. WHEN `ranges` is non-empty, THE closure gate SHALL check, for every range, that `0 â‰¤ start â‰¤ end â‰¤ len(data)`, and SHALL reject with reason `field_out_of_bounds` and a detail naming the range otherwise.
6. WHEN `ranges` is non-empty, THE closure gate SHALL apply engine Requirement 12 to every range separately: a range that intersects the byte range of any of the hypothesis's own `FieldRecord`s SHALL reject the hypothesis with reason `degenerate_hypothesis` and a detail naming the range and the field. A field between two ranges SHALL NOT cause a rejection.
7. WHEN `ranges` is non-empty, THE closure gate SHALL reject with reason `degenerate_hypothesis` and a detail naming the two ranges WHEN two non-empty ranges overlap. The same bytes cannot be the data of two units. This needs no format knowledge.
8. FOR strips, THE unit `i` SHALL be `rows_i = min(rows_per_strip, height âˆ’ i Ã— rows_per_strip)` image rows, and its expected bytes `rows_i Ã— row_stride`, where `row_stride` is the engine's row stride (`ceil(width Ã— bit_depth / 8)` at alignment 1). THE number of ranges SHALL equal `ceil(height / rows_per_strip)`; otherwise the hypothesis is rejected with `degenerate_hypothesis`.
9. FOR tiles, THE unit SHALL be one tile of `tile_length` rows of `ceil(tile_width Ã— bit_depth / 8)` bytes, whole, including the part beyond the image edge. THE number of ranges SHALL equal `ceil(width / tile_width) Ã— ceil(height / tile_length)`; otherwise the hypothesis is rejected with `degenerate_hypothesis`. WHEN `(tile_width Ã— bit_depth) mod 8 â‰  0`, THE hypothesis SHALL be rejected with `degenerate_hypothesis`: tile columns would not start on a byte.
10. THE closure gate SHALL check every range in order and SHALL stop at the first range that fails, rejecting the hypothesis with that range's reason, discrepancy (for `none`: `range length âˆ’ unit expected bytes`) and a detail that names the range's index. One failing range fails the hypothesis (Principle call 2: no tolerance).
11. FOR encoding `none`, EACH range's length SHALL equal its unit's expected bytes. FOR a decoder encoding, EACH range SHALL decode with status `ok` and `max_output_bytes` equal to its unit's expected bytes.
12. THE decoded bytes of a strip layout SHALL be the strips' bytes concatenated in order. THE decoded bytes of a tile layout SHALL be the image assembled from the tiles: for each tile, its rows are copied to the image at the tile's column and row, cropped on the right and bottom to the image, with each image row `row_stride` bytes. `expected_decoded_bytes` SHALL be `row_stride Ã— height` in both cases.
13. THE payload that `web/serialise.py` builds SHALL add `ranges`, `planes`, `row_bytes`, `rows_per_strip`, `tile` and `maxval` to a hypothesis or candidate only when its value is not the default, so that the payload of every result that exists today stays byte for byte the same. No existing payload key SHALL change meaning. `web/pixels.py` SHALL keep its `decode` signature working for every call that is made today.
14. THE `RejectionEntry` SHALL keep its fields. The decoder detail of Requirement 2.12 SHALL travel in the existing `detail` field.

### Requirement 8: TIFF strips

**User Story:** As a user dropping a TIFF written in several strips, I want the strip arrays read as the file declares them and the last strip to hold the remaining rows.

#### Acceptance Criteria

1. THE TIFF probe SHALL keep every field, tag and rule of engine Requirement 2.8, and SHALL additionally read these tags, each in the file's byte order, from the same IFD entries (tag at `+0` as `oH`, type at `+2` as `oH`, count at `+4` as `oI`, value at `+8`):
   - 278 `rows_per_strip`: SHORT or LONG, count 1; absent means `2^32 âˆ’ 1` (the TIFF default), which holds the whole image in one strip.
   - 273 `strip_offset` and 279 `strip_byte_count`: SHORT or LONG, count `n`.
2. THE probe SHALL read an array of count `n` (tags 273, 279, 324, 325) by the rule that engine Requirement 2.8 gives BitsPerSample: when `n Ã— size(type) â‰¤ 4` the `n` values are read consecutively at `+8`, left-justified; otherwise the value field is read as `oI` and the values are read consecutively from that offset. `n` SHALL satisfy `1 â‰¤ n â‰¤ 16,384` (`TIFF_MAX_RANGES`); otherwise the probe SHALL record `probe_precondition_failed` and read no values.
3. WHEN tag 273 has count 1, THE probe SHALL record `strip_offset` and `strip_byte_count` as today (each one `FieldRecord`, named as today) and SHALL leave `ranges` empty, so that single-strip results are unchanged.
4. WHEN tag 273 has count `n > 1`, THE probe SHALL record each value as its own `FieldRecord` named `strip_offset[i]` and `strip_byte_count[i]` at the value's own offset with format `oH` or `oI`, and SHALL build `ranges = ((strip_offset[i], strip_offset[i] + strip_byte_count[i]), ...)` and `rows_per_strip = min(rows_per_strip, height)`. The names carry the index so that engine Requirement 8.3 (equal names, equal values) is not violated.
5. IF any value of an array lies outside the file, THEN the probe SHALL record `field_out_of_bounds`, the array SHALL be treated as not read, and the other tags SHALL be read as before.
6. IF the counts of tags 273 and 279 differ, THEN the probe SHALL record `probe_precondition_failed` naming both counts and emit the seed from what was read.
7. IF the count of tag 273 differs from `ceil(height / rows_per_strip)`, THEN the probe SHALL record `probe_precondition_failed` naming both numbers. This applies to a single strip too: one strip with `RowsPerStrip < height` contradicts itself.
8. IF tags 273 and 324 are both present, THEN the probe SHALL record `probe_precondition_failed` naming both. The file cannot be both stripped and tiled.
9. FOR a multi-strip seed, `bit_depth = bits_per_sample Ã— samples_per_pixel`, `header_size` and `data_end` follow Requirement 7.2, `row_alignment = 1`, and `encoding` is `none` for Compression 1 or `tiff_compression_<n>` otherwise (Requirement 2.2).
10. THE result for every TIFF in the corpus that has one strip SHALL be unchanged in status, key, data region and fields. THE only new rejections that may appear on a single-strip file are those of criterion 7.
11. A strip layout with encoding `none` SHALL close under Requirement 7.10 and 7.11, and the decoded bytes SHALL equal the strips' bytes concatenated.

### Requirement 9: TIFF tiles

**User Story:** As a user dropping a tiled TIFF, I want the tiles read from their arrays and assembled into the image.

#### Acceptance Criteria

1. THE TIFF probe SHALL read tag 322 `tile_width` and 323 `tile_length` (SHORT or LONG, count 1) and tags 324 `tile_offset` and 325 `tile_byte_count` (SHORT or LONG, count `n`, read by Requirement 8.2).
2. WHEN tag 324 is present, THE probe SHALL record each tile offset and byte count as a `FieldRecord` named `tile_offset[i]` and `tile_byte_count[i]`, and SHALL build `ranges` from them in array order and `tile = (tile_width, tile_length)`. THE tile at array index `k` is at column `k mod across` and row `k div across` of the tile grid, where `across = ceil(width / tile_width)`.
3. IF tag 324 is present and any of 322, 323 or 325 is missing or zero, or the counts of 324 and 325 differ, THEN the probe SHALL record `probe_precondition_failed` naming the missing or unequal items.
4. THE probe SHALL NOT make 273 or 279 required when tag 324 is present. WHEN neither 273 nor 324 is present, `probe_precondition_failed` SHALL be recorded naming both, as it is today for 273.
5. FOR a tile seed, `bit_depth`, `header_size`, `data_end`, `row_alignment` and `encoding` follow Requirement 8.9.
6. THE tile layout SHALL close under Requirements 7.9 to 7.12, and THE assembled bytes SHALL equal the image row for row. A test SHALL build a tiled image with a partial last column and a partial last row and compare every assembled byte.

### Requirement 10: TIFF Predictor

**User Story:** As a user dropping a TIFF with a Predictor, I want it refused with the tag and value named, never decoded wrongly.

#### Acceptance Criteria

1. THE TIFF probe SHALL read tag 317 `predictor` by the single-valued rule (SHORT or LONG, count 1, value at `+8`, recorded as a `FieldRecord`). An absent tag means Predictor 1 and adds no field.
2. WHEN tag 317 is present and its value is not 1, THE probe SHALL emit the seed with `encoding = "tiff_compression_<c>_predictor_<p>"` (`c` the Compression value, `p` the Predictor value), which the closure gate rejects with `unsupported_encoding`, AND SHALL record `probe_precondition_failed` whose detail names tag 317 and the value, for example `predictor (tag 317) = 2 is declared and not implemented; the data is not decoded as if it were 1`.
3. WHEN tag 317 is present in a form the probe cannot read (a type other than SHORT or LONG, or a count other than 1), THE probe SHALL treat the Predictor as not established and apply criterion 2 with the detail naming the tag, the type and the count.
4. THE rule SHALL apply to every Compression value, uncompressed included, and SHALL hold before any decoder is wired in (Task order).
5. FOR the four corpus files that declare Predictor 2 (`goimage_video-001-strip-64.tiff`, `goimage_video-001-tile-64x64.tiff`, `pillow_hopper_lzw.tif`, `pillow_tiff_adobe_deflate.tif`), THE result SHALL be `FAILED` with the rejection of criterion 2 present, and no candidate.
6. THE closure gate SHALL NOT decode a hypothesis whose encoding names a predictor.

### Requirement 11: PackBits

**User Story:** As a user dropping a PackBits TIFF, I want each strip decoded exactly and refused when bytes are left over.

#### Acceptance Criteria

1. THE closure gate SHALL map `tiff_compression_32773` to the `packbits` decoder.
2. THE `packbits_decode(data, start, end, max_output_bytes)` SHALL read a header byte `n` as a signed byte. WHEN `0 â‰¤ n â‰¤ 127`, THE next `n + 1` bytes SHALL be written as they are. WHEN `-127 â‰¤ n â‰¤ -1`, THE next byte SHALL be written `1 âˆ’ n` times. WHEN `n = -128` (`0x80`), THE decoder SHALL write nothing and read the next header.
3. THE decoder SHALL read packets while fewer than `max_output_bytes` bytes are written and the region is not exhausted.
4. WHEN a packet's write would take the output beyond `max_output_bytes`, THE decoder SHALL return `overrun` without writing it, with `consumed_to` the index after that packet's last byte.
5. WHEN the region ends inside a packet or before `max_output_bytes` bytes are written, THE decoder SHALL return `underrun` with `consumed_to = end`.
6. WHEN `max_output_bytes` bytes are written and bytes of the region remain, THE decoder SHALL return `unconsumed` with `consumed_to` the index of the first leftover byte. A trailing `0x80` byte is a leftover byte (Principle call 2). WHEN it stops exactly at `end`, it SHALL return `ok`.
7. A strip whose encoder pads it SHALL therefore fail closure and be reported. No tolerance is added.

### Requirement 12: LZW

**User Story:** As a user dropping an LZW TIFF, I want each strip decoded by the TIFF LZW rules and its end defined to the bit, so that padding bits are not leftover bytes and a whole unread byte is.

#### Acceptance Criteria

1. THE closure gate SHALL map `tiff_compression_5` to the `lzw_tiff` decoder.
2. THE `lzw_tiff_decode(data, start, end, max_output_bytes)` SHALL read codes most significant bit first from `data[start:end]`, with these constants: `CLEAR = 256`, `EOI = 257`, first free table entry 258, initial code width 9 bits, maximum code width 12 bits. This is the TIFF 6.0 LZW. The old-style LZW of TIFF 5.0 (least significant bit first) has no reading here; a stream written that way is malformed under criterion 6.
3. THE decoder SHALL keep a table of byte strings: entries 0 to 255 are the single bytes. WHEN the table holds 258 entries (after a `CLEAR`), THE first code SHALL be a `CLEAR` or a literal below 256; anything else is malformed.
4. THE decoder SHALL grow the code width with early change: the width becomes 10 when the table reaches 511 entries, 11 at 1023, 12 at 2047, and stays 12. A table that is full (4094 entries) SHALL stay full until the next `CLEAR`.
5. WHEN a code is below the table's size, THE decoder SHALL output that entry. WHEN a code equals the table's size, THE decoder SHALL output the previous entry followed by its own first byte. A code above the table's size is malformed.
6. WHEN a code is malformed, THE decoder SHALL return `underrun` with `consumed_to` the index after the byte that holds the code's last bit, and a detail naming the code.
7. WHEN a code's output would take the total beyond `max_output_bytes`, THE decoder SHALL return `overrun` without writing it, with `consumed_to` the index after the byte that holds that code's last bit.
8. THE decoder SHALL end only at an `EOI` code. WHEN the region has fewer bits left than the current code width before an `EOI` is read, THE decoder SHALL return `underrun` with `consumed_to = end`. No end of data without `EOI` is accepted.
9. WHEN `EOI` is read, `consumed_to` SHALL be `start + ceil(bits_read / 8)`, where `bits_read` is the number of bits of all codes read including the `EOI`. THE bits after the last code inside the final byte are padding and are NOT leftover bytes. A whole unread byte is.
10. WHEN `EOI` is read with fewer than `max_output_bytes` bytes written, THE decoder SHALL return `underrun`. WHEN it is read with `max_output_bytes` bytes written and `consumed_to < end`, THE decoder SHALL return `unconsumed`. WHEN it is read with `max_output_bytes` bytes written and `consumed_to = end`, THE decoder SHALL return `ok`.
11. THE decoder's table SHALL be bounded: at most 4,096 entries, and the output at most `max_output_bytes`.
12. A test SHALL build LZW streams from a documented encoder in the test file (not from the decoder) and check: a stream that ends exactly (ok), one with one extra byte after `EOI` (unconsumed), one whose last byte holds `EOI` and padding bits (ok), one cut before `EOI` (underrun), one with a code above the table (underrun), one whose output is one byte too long (overrun), and a stream that crosses every code width from 9 to 12 bits and a `CLEAR` in the middle.

### Requirement 13: Deflate

**User Story:** As a user dropping a Deflate TIFF, I want each strip inflated with the standard library and refused unless the stream ends exactly at the strip's end.

#### Acceptance Criteria

1. THE closure gate SHALL map `tiff_compression_8` and `tiff_compression_32946` to the `deflate_zlib` decoder. Both codes name the same zlib stream.
2. THE `deflate_zlib_decode(data, start, end, max_output_bytes)` SHALL inflate `data[start:end]` with a `zlib` decompressor object called with `max_length = max_output_bytes + 1`.
3. WHEN the decompressor produces more than `max_output_bytes` bytes, THE decoder SHALL return `overrun`, with `consumed_to = end âˆ’ len(unconsumed_tail)`, and no output.
4. WHEN the stream is corrupt (`zlib.error`), THE decoder SHALL return `underrun` with `consumed_to = start` and a detail.
5. WHEN the stream is not complete (the decompressor is not at end of stream) or has produced fewer than `max_output_bytes` bytes, THE decoder SHALL return `underrun` with `consumed_to = end âˆ’ len(unused_data)` when the stream ended, otherwise `end`.
6. WHEN the stream is complete with `max_output_bytes` bytes and `unused_data` is not empty, THE decoder SHALL return `unconsumed` with `consumed_to = end âˆ’ len(unused_data)`. WHEN `unused_data` is empty, it SHALL return `ok`.

### Requirement 14: LZMA

**User Story:** As a user dropping an LZMA TIFF, I want each strip decompressed with the standard library and held to the same exact end.

#### Acceptance Criteria

1. THE closure gate SHALL map `tiff_compression_34925` to the `lzma_xz` decoder.
2. THE `lzma_xz_decode(data, start, end, max_output_bytes)` SHALL decompress `data[start:end]` as an xz stream (`lzma.FORMAT_XZ`), with a decompressor whose `memlimit` is 64 MiB and a `max_length` of `max_output_bytes + 1`. The corpus file `pillow_hopper_lzma.tif` holds an xz stream (magic `FD 37 7A 58 5A 00` at the strip start).
3. THE states SHALL follow Requirement 13.3 to 13.6 with `lzma` in place of `zlib`: output above the bound is `overrun`; `lzma.LZMAError` is `underrun` with `consumed_to = start`; an incomplete stream or short output is `underrun`; a complete stream with `max_output_bytes` bytes and leftover `unused_data` is `unconsumed`; an exact end is `ok`.
4. THE decoder SHALL NOT allocate more than the memory limit for a stream whose header declares a larger dictionary: that stream returns `underrun` with a detail naming the limit.

### Requirement 15: Never-raise and bounded cost

**User Story:** As a developer running NECROPSY on adversarial files, I want every new component to return a structured value in bounded time and memory.

#### Acceptance Criteria

1. THE PNM probe, the extended PCX and TIFF probes, the decoders of Requirements 4, 5 and 11 to 14, the closure rules of Requirements 3.9, 6.3 to 6.5 and 7, and the strategy guard of Requirement 6.5 SHALL each have a Hypothesis property test over `st.binary()` asserting they never raise and return the declared type.
2. THE engine's existing property tests (engine Requirement 6.5 and 6.6) SHALL run over inputs that include mutated copies of every file that a new layout resolves, and SHALL pass: `run()` never raises and returns within `deadline_seconds + 0.25`.
3. A test SHALL feed the LZW decoder a 65,536-byte stream built to expand as much as the table allows and `max_output_bytes = DECODE_CAP`, and SHALL assert the decoder returns within 2 seconds. WHEN the measured time is higher, THE `DECODE_CAP` SHALL be lowered in the same task, and the measurement and the new value SHALL be stated in `design.md`.
4. A test SHALL feed each decoder a stream whose declared output is far above the input (a zlib bomb, an LZMA bomb, a PackBits run of 128 bytes repeated) and assert that the output allocated never exceeds `max_output_bytes + 1`.
5. A TIFF whose arrays declare counts larger than `TIFF_MAX_RANGES` or larger than the bytes available SHALL cause no allocation sized from the count (the count is checked against the buffer before any list is built).

### Requirement 16: Rendering

**User Story:** As a user, I want every layout that now resolves to show its picture.

#### Acceptance Criteria

1. THE `web/pixels.py` `decode` SHALL render these, from the declarations the file states, with a note stating how the colour was read:
   - PNM P1: 1-bit, 1 = black, as P4 renders today.
   - PNM P2 and P5: grey; a sample `v` of `maxval` M is shown as `v Ã— 255 // M`; for `bit_depth = 16` the sample is the big-endian word.
   - PNM P3 and P6: RGB in stored order, scaled the same way, 16-bit words big-endian.
   - TGA 8, 15/16, 24 and 32 bit as today, for run-length types too: the decoded bytes have the same layout.
   - PCX with `planes = 3` or `4` and 8 bits per plane: the planes of each scanline as R, G, B (a fourth plane is ignored, as a fourth byte is for 32-bit pixels). PCX with `planes` 2 to 4 and 1 bit per plane: each pixel's index is the planes' bits, plane 0 the lowest bit, looked up in the 16-entry RGB palette that the header declares at `0x10` (48 bytes).
   - TIFF with several strips or tiles, or compressed: the assembled bytes are rendered as for one uncompressed strip.
   - TIFF and PNM 12-bit and 16-bit grey: 16 bits are read in the byte order the TIFF declares (`II` little, `MM` big; PNM big); 12 bits are packed most significant bit first; a sample `v` is shown as `v Ã— 255 // (2^bits âˆ’ 1)` (TIFF) or `v Ã— 255 // maxval` (PNM).
2. A layout that resolves and has no renderer (for example 16-bit RGB TIFF, or PCX with 2 to 4 planes of 2 bits) SHALL return `RenderFailure` with a reason naming the layout, as the 16-bit case does today. The design lists them.
3. THE `decode` function SHALL keep returning a `PixelBuffer` or a `RenderFailure` and never raise.
4. EVERY recovered-image test SHALL compare exact pixel values with values computed from the fixture's own definition.
5. THE `web/serialise.py` SHALL pass the header palette (PCX) and the byte order (TIFF) to `decode`, and SHALL add `pnm` to its probe list so that `stage_of("pnm")` is `probe`. Nothing under `public/` SHALL change.

### Requirement 17: Spec emission

**User Story:** As a user who wants the spec of what was recovered, I want every new encoding defined in EARS in the emitted document and tested against the engine's own decode.

#### Acceptance Criteria

1. THE emitted `requirements.md` SHALL define, in EARS and from the engine's own decoder, every encoding name it uses (engine Decision Record item 26): `pnm_text` (from Requirement 4), `rle_tga` (5), `packbits` (11), `lzw_tiff` (12), `deflate_zlib` (13) and `lzma_xz` (14), each as definitely as engine Requirement 9.28 defines `rle_pcx`, including the state of every end condition. The document SHALL define a name only when the layout uses it.
2. THE emitted TGA layout's encoding mapping SHALL send `image_type` 1, 2 and 3 to `none` and 9, 10 and 11 to `rle_tga`. THIS replaces engine Requirement 9.29 for 9, 10 and 11 only, because the engine now decodes them. THE name `unsupported` SHALL stay in the mapping as `otherwise`.
3. THE emitted TIFF layout's `compression` mapping SHALL send 1 to `none`, 32773 to `packbits`, 5 to `lzw_tiff`, 8 and 32946 to `deflate_zlib`, 34925 to `lzma_xz`, and every other value to `unsupported`. It SHALL carry a tag-table entry `{"name": "predictor", "tag": 317, "default": 1, "expect": 1, "array": null}` after `planar_configuration`, which the reference reader enforces by engine Requirement 9.22, and the document SHALL state it in EARS.
4. FOR a multi-plane PCX candidate, THE layout SHALL stay kind `format`, with `image.bit_depth = {"mul": ["bit_depth", "planes"]}` and `image.row_bytes = {"mul": ["planes", "bytes_per_line"]}`, and THE document SHALL state in EARS that each scanline holds `planes` planes of `bytes_per_line` bytes, plane 0 first. A single-plane PCX layout SHALL be byte for byte what it is today.
5. FOR a PNM candidate (probe `pnm`), THE layout SHALL be kind `file`, with this file's literal values, the `magic`, `width`, `height` and `maxval` token reads listed as fields (as PBM lists its tokens), and `image.maxval`. THE document SHALL state the header grammar of Requirement 3.3 in prose, as it does for PBM.
6. FOR a TIFF candidate with several ranges, THE layout SHALL be kind `file` with `data.ranges` this file's literal ranges and `image.rows_per_strip` or `image.tile`, and THE document SHALL state that it describes this one file only because the schema has no array rule for strip and tile offsets. A single-strip TIFF layout SHALL stay kind `format`. `necropsy-layout/1` adds only the keys `data.ranges`, `image.row_bytes`, `image.rows_per_strip`, `image.tile` and `image.maxval`, each only where used.
7. THE emitted `test_<module>.py` SHALL require a successful decode, equal to the engine's width, height, bit depth, row alignment, data region and pixel bytes, for every candidate whose encoding the spec names as decodable (`none`, `rle_pcx`, `pnm_text`, `rle_tga`, `packbits`, `lzw_tiff`, `deflate_zlib`, `lzma_xz`), with no skip and no `refused` clause, except the existing source-too-large skip (engine Requirement 9.12).
8. THE reference reader (`tests/support/reference_reader.py`) SHALL implement each new encoding, the `row_bytes` stride and the `data.ranges` assembly from the emitted `requirements.md` text and layout only, importing nothing from `necropsy`. `zlib` and `lzma` are standard library and are allowed.
9. WITH the reference reader as `parser_<module>`, THE emitted specs of one corpus file per new layout (a P5, a P6, a P2 or P3, an RLE TGA, a 3-plane PCX, a multi-strip TIFF, a tiled TIFF, a PackBits TIFF, an LZW TIFF, a Deflate TIFF and the LZMA TIFF) SHALL pass plain `pytest` with no file argument and no configuration file, and no skipped test other than the source-too-large skip.
10. A do-nothing parser whose `parse()` always returns `{"ok": False, "error": "encoding not supported"}` SHALL fail the emitted tests of each of those specs, and `tools/break_check.py` SHALL carry the check (engine Requirement 9.32 extended).
11. THE emitted specs of every file whose layout did not change SHALL differ from today's only in what criteria 2 and 3 change: the mapping lines and the encoding definitions in TGA and TIFF specs. A test SHALL compare every emitted spec of the samples and the corpus before and after, and fail on any other difference.
12. THE emitted `requirements.md` and `design.md` of the new layouts SHALL pass Kiro's spec format validation as engine Requirement 9.19 requires.

### Requirement 18: Corpus scope

**User Story:** As a reader of the results, I want scope decided from header bytes by stated rules, never from an engine result.

#### Acceptance Criteria

1. THE scope rules in `spike/samples/real/README.md` SHALL be rewritten as follows, and each is read from the file's header bytes:
   - PCX: encoding byte 0 or 1, and `planes â‰¥ 1`.
   - TGA: image type 1, 2, 3, 9, 10 or 11.
   - TIFF: Compression 1, 5, 8, 32773, 32946 or 34925; PlanarConfiguration 1; Predictor absent or 1; every BitsPerSample entry equal (engine Decision Record item 20); strips or tiles. Samples per pixel and a looping IFD chain are not limits.
   - PNM: magic `P1`, `P2`, `P3`, `P5` or `P6` followed by a whitespace byte, or exactly `P4\n`.
2. THE `scope` and `scope_reason` fields of every record in `spike/samples/real/manifest.json` SHALL be set by a script, `tools/scope_from_headers.py`, that reads only the file's bytes under the rules of criterion 1 and writes no other field. A test SHALL assert that the manifest equals the script's output. The SHA-256 of every file SHALL be unchanged.
3. THE `scope_reason` of an out-of-scope file SHALL name the byte that put it out (for example `compression CCITT G4`, `predictor 2`, `planar configuration 2`).
4. THE README's count table and its prose SHALL be recounted from the manifest.
5. NO scope SHALL be taken from an engine result, and NO scope rule SHALL be changed after a result is seen in order to make a result clean.
6. THE expected change is stated in `design.md`: 39 files change from out to in scope, none changes from in to out.

### Requirement 19: Corpus results

**User Story:** As a judge, I want the engine measured on files nobody here wrote, with every mismatch and every refusal stated as measured.

#### Acceptance Criteria

1. `python -m tools.real_corpus` SHALL regenerate `docs/REAL-CORPUS-RESULTS.md` and `spike/real_corpus_results.json` after the scope update.
2. THE canonical pixel comparer SHALL be extended so that EVERY file that is newly `RESOLVED` is compared with Pillow pixel for pixel: PNM grey and RGB, 8 and 16 bit, and 1-bit text; RLE TGA through the existing TGA path; PCX planes de-interleaved to RGB or to palette indices; TIFF strips, tiles and compressed strips through the existing TIFF path with its photometric rule, and 12-bit samples unpacked. A file that cannot be compared SHALL state why, and the reason SHALL be a measured fact about Pillow's mode, not a skip.
3. EVERY mismatch SHALL be recorded as a mismatch, with its cause stated in the file's note. NO comparison, expectation or scope rule SHALL be changed to remove one.
4. A file that is in scope, valid and `FAILED` SHALL be listed in `OPEN_IN_SCOPE_FAILURES` as a strict expected failure, as real-corpus Requirement 6 states. The files expected to land there are `pillow_hopper_1bit_plain.pbm` (Requirement 4.11) and `libtiff_deflate-last-strip-extra-data.tiff` (Principle call 2). THE note of each SHALL give the measured cause.
5. A file the engine now resolves that the manifest lists as invalid by construction (`goimage_invalid-palette-ref.tiff` is the expected case: Pillow refuses it for palette indices that the engine does not read) SHALL keep its expectation `FAILED` in the table's `expected` column and SHALL be reported as an unexpected `RESOLVED` with the cause stated. THE real-corpus test that asserts "five of six invalid files FAIL" SHALL be changed in its own task to assert the measured outcome, citing this criterion.
6. THE results table, the README at the repository root, and `.kiro/specs/real-corpus/design.md` counts SHALL state the measured counts. THE measured counts SHALL be written into this spec's `design.md` beside the predicted ones.

### Requirement 20: Process

**User Story:** As the builder, I want each change measured against what I said it would do, and the evidence of the work in the history.

#### Acceptance Criteria

1. BEFORE each task that changes behaviour, THE expected diff (which files change status, and nothing else) SHALL be the one `design.md` lists for that task, or SHALL be added to `design.md` in the same commit before the change is made.
2. AFTER each such task, THE diff SHALL be measured with `python -m tools.fc_diff` over the 11 samples and the 81 corpus files against `spike/fc_baseline.json`, and the output SHALL be stated in the commit message. IF any file other than the expected ones changes status, termination, candidate key or data region, THEN the work SHALL stop and report. Check counts and rejection counts MAY change and SHALL be reported.
3. EVERY task SHALL be one commit whose message names the task number and the requirement IDs.
4. THE whole suite SHALL pass at the end of every task that is not an expectation task: `python -m pytest tests -q` and `node --test tests/ui/js/logic.test.mjs tests/ui/js/screens.test.mjs`. WHEN an existing test's expectation is wrong because the engine is now right, THE test SHALL be changed in its own task, which cites the requirement that makes it wrong and says so in its commit message. NO test SHALL be deleted, skipped, weakened or marked expected-failure to get green, except the corpus entries of Requirement 19.4.
5. EVERY binary fixture SHALL be built in code from a documented byte layout (steering `tests.md`).
6. THE tasks SHALL be one probe, one decoder, one closure rule or one emitter change each, each with its tests.
7. THE front end under `public/` SHALL NOT be edited. Fields added to payloads are additive (Requirement 7.13).
8. THE work SHALL be developed and measured only against `spike/samples/` and `spike/samples/real/`.

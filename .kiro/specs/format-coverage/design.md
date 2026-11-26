# Design Document

## Overview

Six layouts, one mechanism each. The engine's shape does not change: probes read declarations and emit one seed; revision runs on seeds; the closure gate decodes the data region and accepts only an exact, fully consumed result. This design adds:

- one probe (PNM) and extensions to three (PCX, TGA already, TIFF);
- a small decoder module, `necropsy/engine/decoders.py`, with six decoders behind one contract and one dispatch table that the closure gate reads as data;
- hypothesis fields for declared row bytes, planes, several data ranges, tiles and a maximum value, all optional and defaulted so that no existing result moves;
- renderers, emitters and a reference reader for each new layout;
- measurement discipline: an expected diff per task, measured after it.

Nothing here changes the gate (closure stays binary), the revision strategies (still three, one guarded), Generic Search, or the termination vocabulary. It adds two members to the reason vocabulary, `sample_above_maxval` and `decoder_malformed`, because the screen puts each reason into plain words and none of the ten existing ones is true for those cases.

## Byte layouts

Steering requires offsets, widths and byte order before any task depends on them. `o` is `<` for `II` and `>` for `MM`. All reads are bounds-checked against the buffer before they happen.

### PNM header (new probe, `pnm`)

Text grammar, parsed only inside `data[:1024]`. ASCII whitespace is `0x20 0x09 0x0A 0x0B 0x0C 0x0D`.

| Step | Bytes | Rule |
|---|---|---|
| magic | `0x00`, `0x01` | `P` then one of `1 2 3 5 6`. FieldRecord `magic` at `0x00`, `2s`. |
| separator | from `0x02` | one or more whitespace bytes; the first (`0x02`) must be whitespace for the signature to match. A comment (`#` to the next `0x0A` or `0x0D`) may stand where whitespace may. |
| width | token | ASCII digits. FieldRecord `width` at the token's offset, `<n>s`. |
| separator | | whitespace and comments, at least one whitespace byte. |
| height | token | as width, FieldRecord `height`. |
| maxval | token | P2, P3, P5, P6 only, after whitespace and comments. FieldRecord `maxval`, `<n>s`. P1 has none. |
| raster start | | P5, P6: exactly one whitespace byte, then the raster at `header_size = index after it`. P1, P2, P3: `header_size = index after the last token`; the ASCII numbers follow. |

Sample size: `maxval ≤ 255` is 1 byte, `256..65535` is 2 bytes big-endian. Seed `bit_depth`: P1 1; P2, P5 `8` or `16`; P3, P6 `24` or `48`.

Worked check on a real file, `pillow_hopper_16bit.pgm`: `P5\n128 128\n65535\n` is 3 + 8 + 6 = 17 header bytes; 128 × 128 × 2 = 32768; 17 + 32768 = 32785, the file's length.

### PCX (unchanged reads, new use of two)

| Field | Offset | Format | Use |
|---|---|---|---|
| bit_depth | `0x03` | `B` | bits per plane |
| planes | `0x41` | `B` | `P`; new: `> 1` selects the planar layout |
| bytes_per_line | `0x42` | `<H` | new: `row_bytes = P × bytes_per_line` |

Scanline layout for `P > 1`: `P` planes of `bytes_per_line` bytes, plane 0 first. Worked check, `imagemagick_input.pcx`: 3 planes, `bytes_per_line` 70, 46 rows: 3 × 70 × 46 = 9660 decoded bytes.

### TGA RLE (unchanged probe reads)

Packet header `h` (1 byte): `h ≥ 0x80` run, `(h & 0x7F) + 1` copies of the next `pixel_bytes` bytes; `h < 0x80` raw, `h + 1` pixels follow. `pixel_bytes = ceil(bit_depth / 8)`. Worked check, `pillow_cross_scan_line.tga` (2 × 2, 8 bpp): 4 output bytes from packets that cross the end of row 0.

### TIFF (additional tags)

IFD entry, 12 bytes at `ifd_offset + 2 + 12k`: tag `oH` at `+0`, type `oH` at `+2`, count `oI` at `+4`, value field at `+8`. SHORT (3) is 2 bytes, LONG (4) is 4 bytes. New tags:

| Tag | Name | Type | Count | Notes |
|---|---|---|---|---|
| 278 | rows_per_strip | SHORT or LONG | 1 | absent = `2^32 − 1`; clamp to `height` |
| 273 | strip_offset | SHORT or LONG | n | array rule below |
| 279 | strip_byte_count | SHORT or LONG | n | array rule below |
| 317 | predictor | SHORT or LONG | 1 | absent = 1; not 1 refuses |
| 322 | tile_width | SHORT or LONG | 1 | |
| 323 | tile_length | SHORT or LONG | 1 | |
| 324 | tile_offset | SHORT or LONG | n | array rule |
| 325 | tile_byte_count | SHORT or LONG | n | array rule |

Array rule (the one BitsPerSample already uses): if `n × size ≤ 4` the `n` values lie consecutively from entry `+8`, left-justified; else `oI` at `+8` is a file offset and the values lie consecutively from it. `1 ≤ n ≤ 16,384`. Every element is its own FieldRecord at its own offset, named with its index (`strip_offset[3]`).

Worked check, `libtiff_deflate-last-strip-extra-data.tiff`: 500 × 500, `RowsPerStrip` 16, so `ceil(500/16) = 32` strips, 31 of 16 rows and a last of `500 − 31 × 16 = 4` rows. The first strip inflates to 8000 bytes = 16 × 500, which is correct. The file's last strip inflates to 8000 bytes, not 2000: this is the "extra data" and the strip fails closure (Principle call 2).

### Compressed-stream constants

| Codec | Compression | Constants |
|---|---|---|
| PackBits | 32773 | signed header byte; `0..127` literal `n + 1`; `−127..−1` run `1 − n`; `−128` no-op |
| LZW | 5 | MSB-first; `CLEAR 256`, `EOI 257`, first free `258`; width 9 to 12; early change at 511, 1023, 2047 |
| Deflate | 8, 32946 | zlib stream (`78 xx` header; `789c` in the corpus) |
| LZMA | 34925 | xz container, magic `FD 37 7A 58 5A 00` (corpus: `pillow_hopper_lzma.tif`) |

## Data model

```
Hypothesis (existing fields unchanged) +
    planes: int = 1
    row_bytes: int | None = None           # declared scanline bytes (PCX planes > 1)
    ranges: tuple[tuple[int,int], ...] = ()  # several data ranges
    rows_per_strip: int | None = None
    tile: tuple[int,int] | None = None     # (tile_width, tile_length)
    maxval: int | None = None              # PNM
Candidate (existing fields unchanged) + ranges: tuple[tuple[int,int], ...] = ()
ClosureVerdict (existing fields unchanged) + detail: str = ""
```

`hypothesis_key(h)` returns the existing 7-tuple when the six new fields are at their defaults, otherwise the 7-tuple plus `((planes, row_bytes, ranges, rows_per_strip, tile, maxval),)`. Every existing test that asserts the key keeps passing, and hypotheses that differ only in their ranges stay distinct.

`hypothesis_row_stride(h)` returns `h.row_bytes` when set, otherwise the existing `row_stride(width, bit_depth, row_alignment)`. Every place that computes a stride calls it (closure, `Engine._candidate`, `Engine._build`, `Engine._failure`).

For several ranges, `header_size` is the smallest start and the declared `data_end` the largest end. Consumers that read only those two fields (the hex view, `Candidate.data_start` and `data_end`) see the envelope of the data. The ranges themselves travel in `Hypothesis.ranges` and `Candidate.ranges`. The closure rules never use the envelope for a Requirement 12 test: they use each range.

`web/serialise.py` adds `ranges`, `planes`, `row_bytes`, `rows_per_strip`, `tile` and `maxval` to a hypothesis or candidate dict only when not at the default. A payload that exists today is byte for byte unchanged. The front end ignores keys it does not know.

## Decoders (`necropsy/engine/decoders.py`)

```
@dataclass(frozen=True)
class DecodeResult: status: str; data: bytes | None; consumed_to: int; detail: str = ""

DECODERS = {                       # data the closure gate reads
  "pnm_text":     ...,   # engine encoding "pnm_text"
  "rle_tga":      ...,   # engine encoding "rle_tga"
  "tiff_compression_32773": packbits_decode,
  "tiff_compression_5":     lzw_tiff_decode,
  "tiff_compression_8":     deflate_zlib_decode,
  "tiff_compression_32946": deflate_zlib_decode,
  "tiff_compression_34925": lzma_xz_decode,
}
DECODER_NAMES = {...}   # engine encoding -> emitted name (packbits, lzw_tiff, deflate_zlib, lzma_xz, rle_tga, pnm_text)
DECODE_CAP = 8 * 1024 * 1024
```

The hypothesis encoding for TIFF stays `tiff_compression_<n>`, so every existing key and emitted `layout.observed` is unchanged. The emitted name comes from `DECODER_NAMES`.

### Result states by decoder

`consumed_to` is the first byte not consumed. The first column is the state, the cells give `consumed_to`.

| State | pnm_text | rle_tga, packbits | lzw_tiff | deflate_zlib, lzma_xz |
|---|---|---|---|---|
| ok | `end` | `end` | `end` (output full and either EOI read with `start + ceil(bits/8) = end`, or the strip ends with fewer than 8 bits and fewer than one code left) | `end` |
| overrun | index after the number whose write would exceed the bound | index after the packet's last byte | index after the byte holding the code's last bit | `end − len(unconsumed_tail)` |
| underrun | region ended before `N` numbers: `end` | region ended in a packet or before the output was full: `end` | region ended with the output short, EOI or not: `end`; EOI with short output: index after the byte holding the `EOI`'s last bit | stream incomplete or short: `end − len(unused_data)` when it ended, else `end` |
| malformed | non-digit P2/P3 number, or a P1 byte that is not `0`, `1`, whitespace or comment: that byte's index | none (these formats have no meaningless packet) | a code above the table, or a first code that is neither `CLEAR` nor a literal: index after the byte holding its last bit | corrupt stream, or an `lzma` dictionary above the memory limit: `start` |
| above_maxval | index after the number (P1: the digit) above `maxval`; detail names offset, value, maximum | none | none | none |
| unconsumed | first byte of the first stray token | first leftover byte | `start + ceil(bits/8)` when `< end` | `end − len(unused_data)` |

Closure maps states to reasons: `overrun` to `decoder_overrun`, `underrun` to `decoder_underrun`, `unconsumed` to `decoder_unconsumed`, `malformed` to `decoder_malformed`, `above_maxval` to `sample_above_maxval`. The decoder's `detail` goes on the `RejectionEntry`.

Invalid arguments (`start < 0`, `end > len(data)`, `start > end`, `max_output_bytes < 0`): `underrun`, `consumed_to = start`, for every decoder.

LZW end rule, exactly: let `bits` be the sum of the widths of all codes read, including the `EOI`. The stream's last byte is byte `start + ceil(bits / 8) − 1`. Bits after the `EOI` inside that byte are padding. If that byte is `end − 1` the strip is consumed. If more bytes follow, at least one whole byte is unread and the result is `unconsumed`. If the region runs out of bits with no `EOI`, the result is `ok` when exactly `max_output_bytes` are written and the bits left are fewer than the current code width and fewer than 8 (Requirement 12.8 b); `unconsumed` when the output is full and a whole byte is left; `underrun` when the output is short.

### Algorithms, in outline

- `pnm_text_decode`: scan once from `start` to `end`. Skip whitespace and comments. For P1 (`bit_depth` 1) each byte after that is one number: `0` or `1` is written, `2` to `9` is `above_maxval`, any other byte is `malformed`. For P2 and P3 read a token. If the output is full and a number or byte appears, return `unconsumed`. Otherwise require all digits (else `malformed`); a token with more than 5 digits after leading zeros, or a value above `maxval`, is `above_maxval`; a write beyond `max_output_bytes` is `overrun`; write the sample (a bit for `bit_depth = 1`, packed into the row's current byte; 1 or 2 bytes otherwise). No `int()` is called on a token longer than 5 significant digits, so Python's digit-limit cannot raise.
- `rle_tga_decode` and `packbits_decode`: the loop of `rle_pcx_decode`: check the packet fits before writing, and stop when the output is full.
- `lzw_tiff_decode`: a bit reader over `data[start:end]` (a Python int accumulator, MSB first); a list of `bytes` table entries, at most 4096; output as a `bytearray`, extended by table entries, bounded by `max_output_bytes`. The early-change thresholds are 511, 1023 and 2047 table entries.
- `deflate_zlib_decode` and `lzma_xz_decode`: one decompressor object, one `decompress(chunk, max_length + 1)` call, then the state table above. A single call is enough because the whole range is passed at once.

## Closure gate changes

The gate keeps its order: degenerate arguments, `data_end` (trailer registry or declared), Requirement 12, then decode. New steps, in place:

1. **Stride.** `stride = hypothesis_row_stride(h)`; `expected = stride × height`.
2. **Declared row bytes (Requirement 6.4).** If `row_bytes` is set: `bit_depth % planes == 0` and `row_bytes ≥ planes × ceil(width × (bit_depth / planes) / 8)`, else `degenerate_hypothesis`. A single-plane hypothesis never sets `row_bytes`.
3. **Cap (Requirement 2.13).** For an encoding in `DECODERS`: `expected > DECODE_CAP` is `degenerate_hypothesis` with a detail.
4. **Ranges (Requirement 7).** If `ranges` is non-empty: bounds per range (`field_out_of_bounds`); Requirement 12 per range; pairwise disjoint; unit count against `rows_per_strip` or the tile grid; then for each range in order, the unit's expected bytes, then the decode or the `none` length rule; assemble. The loop stops at the first failing range.
5. **Single range.** `none` as today, then, when `maxval` is set, the sample rule (`sample_above_maxval`); or a decoder from `DECODERS`.
6. Any other encoding: `unsupported_encoding` as today. That includes `tiff_compression_<n>` for every `n` not in `DECODERS`, and `tiff_compression_<c>_predictor_<p>`.

Sample rule for `none` with `maxval`: with 1-byte samples, `max(region) ≤ maxval`; with 2-byte samples, the high bytes `region[0::2]` must not exceed `maxval >> 8`, and where equal the low byte must not exceed `maxval & 0xFF`. The first offender's offset and value go in the detail. No buffer is sized from `maxval`.

Strip assembly is `b"".join(unit bytes)`. Tile assembly copies each tile's rows into a `bytearray(stride × height)` at `(tile_col × tile_row_bytes, tile_row × tile_length)`, cropped to the image: `copy_bytes = min(tile_row_bytes, stride − x_bytes)`, rows `min(tile_length, height − y)`. The `bytearray` is `stride × height`, which is bounded because the strip or tile expected bytes already passed the cap check or, for `none`, are the lengths of ranges that exist in the file; the assembled size is checked against `DECODE_CAP` first for tiles.

## Probes

### PNM (new)

`probe_pnm(data)` returns `None` on a non-matching signature and otherwise a `ProbeOutcome`. It reuses the `read` helper and the `ProbeOutcome` type. Registered in `PROBES` between `pbm` and `tiff`, and in `web/serialise.py` `PROBES`. Seeds:

| Magic | `bit_depth` | `encoding` | `header_size` | `maxval` |
|---|---|---|---|---|
| P5 | 8 or 16 | `none` | after the one whitespace byte | as read |
| P6 | 24 or 48 | `none` | same | as read |
| P1 | 1 | `pnm_text` | after the height token | 1 (each `0` or `1` character is one number; separators optional) |
| P2 | 8 or 16 | `pnm_text` | after the maxval token | as read |
| P3 | 24 or 48 | `pnm_text` | same | as read |

The raster of P5 and P6 is the data region to the end of the file. For P1, P2 and P3 the region also runs to the end, so trailing bytes that are not whitespace or comments fail closure under Principle call 1.

### PCX

Reads the same bytes. When `planes > 1` it sets the three fields of Requirement 6.2. `row_padding_variants` returns no candidates when `row_bytes` is set; nothing else in `strategies.py` changes.

### TIFF

The probe becomes a longer walk of the same entry table. Order of the additions inside `_probe_tiff`: read tag 317 (single-valued), tags 278, 322, 323 (single-valued), arrays 273/279/324/325 through the BitsPerSample array routine (generalised to take a name). Seed construction branches three ways: one strip (unchanged path), several strips, tiles. Precondition checks are added to the `problems` list that the probe already builds; the seed is always emitted (item 3 of the Decision Record). No format is added; no tag is read that Requirement 8, 9 or 10 does not list.

FillOrder (tag 266), SampleFormat (339), ExtraSamples (338), JPEGTables and every other tag stay unread. This is stated under Limits.

## Rendering (`web/pixels.py`, `web/serialise.py`)

`decode()` keeps its signature and its return types. Three optional keyword arguments are added with defaults that reproduce today's calls: `maxval=None`, `byte_order=None` ("little" or "big", TIFF 16-bit and 12-bit) and `planes=1`, with `header_palette=None` for PCX. Cases, in the order the function tests them:

| Layout | Pixel bytes | Rendering |
|---|---|---|
| PNM `bit_depth` 1 | packed rows, 1 = black | the PBM table, `probe_name in ("pbm", "pnm")` |
| PNM 8, 16 | 1 or 2 bytes, big-endian | grey, `v × 255 // maxval` |
| PNM 24, 48 | R, G, B samples | RGB, same scaling |
| PCX `planes` 3 or 4, 8 bits per plane | R plane, G plane, B plane, per scanline | RGB |
| PCX `planes` 2 to 4, 1 bit per plane | planar bit rows | index to the header's 16-entry palette at `0x10` |
| TIFF/PNM 16 grey | 2 bytes | high byte after scaling; byte order from the declaration |
| TIFF 12 grey | packed MSB first | `v × 255 // 4095` |
| TGA RLE, TIFF multi-range and compressed | same as their uncompressed form | existing paths |

No renderer (reason returned): PCX with planes of other bit depths (2, 4), 16-bit RGB TIFF, 12-bit RGB TIFF. The corpus has none of these resolving. `libtiff_rgb-3c-16b.ppm` is 16-bit RGB PNM and is rendered (big-endian words).

Orientation: PNM and TIFF rows are top-down; TGA keeps its descriptor rule; PCX top-down. Unchanged.

## Emission

`necropsy-layout/1` gains only optional keys, each present only where used: `data.ranges`, `image.row_bytes`, `image.rows_per_strip`, `image.tile`, `image.maxval`. A layout that does not use them is byte-identical to today's.

| Result | Layout kind | What changes |
|---|---|---|
| TGA (any) | `format` | mapping: 1,2,3 `none`; 9,10,11 `rle_tga`; otherwise `unsupported`. `rle_tga` defined in EARS. |
| PCX `planes ≤ 1` | `format` | none |
| PCX `planes > 1` | `format` | `image.bit_depth = {"mul": ["bit_depth", "planes"]}`, `image.row_bytes = {"mul": ["planes", "bytes_per_line"]}`, EARS line for the planar scanline |
| PNM | `file` | literal values; token reads listed; header grammar in prose; `pnm_text` defined when used |
| TIFF one strip | `format` | compression mapping widened; `predictor` entry (expect 1); definitions for each decoder named |
| TIFF several ranges | `file` | literal `data.ranges`, `image.rows_per_strip` or `image.tile`; one-file note; decoders defined |

Why `file` for several ranges: the layout schema's expression language has no iteration over an array. Adding one is a larger schema change than any criterion in this spec asks for, and a `file` layout is the honest layout kind for a statement that is true of one file. It is listed under Limits.

The reference reader gains: `row_bytes` as the stride, `data.ranges` assembly for strips and tiles, and six decoders written from the emitted EARS text. It imports `zlib` and `lzma` from the standard library for `deflate_zlib` and `lzma_xz` and nothing from `necropsy`.

The emitted tests' "decodable" set (the `none` / `rle_pcx` pair in `necropsy/emit/render.py`) becomes the set of Requirement 17.7. Each emitted test requires `ok` and bytes equal to the engine's.

## Corpus scope and results

`tools/scope_from_headers.py` reads each corpus file's bytes, applies the rules of Requirement 18.1 and rewrites `scope` and `scope_reason` in the manifest. It reads no other manifest field to decide scope and imports nothing from `necropsy`. `tests/test_real_corpus.py` gains a test that the committed manifest equals the script's output.

`tools/real_corpus.py` gains canonical forms for: PNM grey and RGB at 8 and 16 bit (Pillow's mode for each is measured in Task 38 and recorded); PCX planes (de-interleave to RGB or to palette indices); TIFF 12-bit (unpack to 16-bit words); and uses the existing TGA and TIFF forms for the rest. A file Pillow decodes in a mode the comparer cannot map is reported "not comparable" with Pillow's mode named. That is a measured fact and is listed in the results.

## Expected diff per task

The list below is the prediction made from header bytes before any code exists. "Status" means the engine's status on the 11 samples and the 81 corpus files. A file not named in a row does not change status, termination, candidate key or data region in that task. Check counts and rejection counts may change and are reported. The prediction can be wrong, and a wrong prediction is a finding, not something to repair.

| Task | Files that change from FAILED to RESOLVED |
|---|---|
| 3, 5, 6, 7 | none (closure rule, renderer, decoder and dispatch only) |
| 4 | `imagemagick_input_p5.pgm`, `imagemagick_input_p6.ppm`, `libtiff_minisblack-1c-8b.pgm`, `libtiff_rgb-3c-16b.ppm`, `libtiff_rgb-3c-8b.ppm`, `pillow_hopper_16bit.pgm`, `pillow_hopper_8bit.pgm`, `pillow_hopper_8bit.ppm`, `sdlimage_sample.pnm` (9) |
| 8 | `imagemagick_input_p1.pbm`, `imagemagick_input_p2.pgm`, `imagemagick_input_p3.ppm`, `pillow_hopper_1bit_plain.pbm` (4). The last one writes digits in runs; read digit by digit (Requirement 4.4) it holds 10,967 ones and 5,417 zeros, 16,384 = 128 × 128 digits, and nothing else but whitespace, measured from the file's bytes. |
| 10 | none (decoder only) |
| 11 | `pillow_200x32_l_tl_rle.tga`, `pillow_200x32_p_tl_rle.tga`, `pillow_200x32_rgb_tl_rle.tga`, `pillow_la.tga`, `pillow_rgb32rle.tga`, `sdlimage_sample.tga` (6, measured in Task 11). `pillow_cross_scan_line_truncated.tga` stays FAILED (truncated data). `pillow_cross_scan_line.tga` stays FAILED too, which the first prediction missed: the file is 49 bytes; with its 26-byte TGA 2.0 footer excluded the data region is [18, 23) = `02 00 FF FF 00`, a raw packet of 3 pixels and then a raw packet header whose pixel byte would be byte 23, the first byte of the footer (`decoder_underrun`); read to the end of the file, 25 bytes are left over (`decoder_unconsumed`). Both readings fail. Pillow decodes it because it ignores the footer. |
| 13, 14 | none |
| 15 | `imagemagick_input.pcx`, `sdlimage_sample.pcx`, `pillow_p_4_planes.pcx` (3). `pillow_ossfuzz-4836216264589312.pcx` is unchanged (its encoding byte makes the probe decline). |
| 17 | none (closure rule, no probe yet) |
| 18 | `goimage_video-001-gray.tiff`, `libtiff_minisblack-1c-8b.tiff`, `libtiff_palette-1c-8b.tiff`, `libtiff_rgb-3c-8b.tiff`, `pillow_12bit.cropped.tif`, `pillow_tiff_strip_raw.tif` (6). `pillow_tiff_strip_planar_raw.tif` stays FAILED (planar 2). |
| 20 | none |
| 21 | `pillow_tiff_tiled_raw.tif` (1) |
| 22 | none in status. The four Predictor 2 files (`goimage_video-001-strip-64.tiff`, `goimage_video-001-tile-64x64.tiff`, `pillow_hopper_lzw.tif`, `pillow_tiff_adobe_deflate.tif`) keep FAILED and gain the rejection that names tag 317 and the value. |
| 23 | `goimage_bw-packbits.tiff` (1) |
| 24 | `goimage_blue-purple-pink.lzwcompressed.tiff`, `libtiff_lzw-single-strip.tiff` (2; the second ends without `EOI` and resolves under Requirement 12.8 b, measured 26 Nov 2026). `pillow_hopper_lzw.tif` stays FAILED (Predictor 2). |
| 25 | `goimage_bw-deflate.tiff`, `goimage_video-001-paletted.tiff`, `goimage_invalid-palette-ref.tiff` (3). `libtiff_deflate-last-strip-extra-data.tiff` stays FAILED (Principle call 2). |
| 26 | `pillow_hopper_lzma.tif` (1) |

Measured after Task 27 in `spike/real_corpus_results.json` (81 rows): 61 `RESOLVED`, 20 `FAILED`; the 36 rows above sum to 36 (9 + 4 + 6 + 3 + 6 + 1 + 1 + 2 + 3 + 1, row 24 counted as 2), and the 20 `FAILED` are the five in-scope and fifteen out-of-scope files named below. Task 28 checked this by reading the committed rows.

Total predicted: 36 new `RESOLVED` (37 before the bytes of `pillow_cross_scan_line.tga` were read in Task 12). The engine's `RESOLVED` count goes from 25 to 61, and `FAILED` from 56 to 20, of which the in-scope ones are `libtiff_deflate-last-strip-extra-data.tiff`, `pillow_cross_scan_line.tga`, `pillow_cross_scan_line_truncated.tga`, and the two that are invalid by construction today (`pillow_01r_00.pcx`, `pillow_p_8.tga`): five. The other 15 are out of scope.

Two predictions carry known risk, named here so that a surprise is not a repair:

- `goimage_invalid-palette-ref.tiff` is invalid by construction (Pillow refuses it for palette indices outside the palette). The engine does not read palette semantics. If the strips close, it is `RESOLVED`, and that contradicts the file's `FAILED` expectation. The measurement is written down (Requirement 19.5).
- `libtiff_lzw-single-strip.tiff` decodes about 3 MB (7795 × 3122, 1 bit). Pure-Python LZW on that size may approach the engine's 5-second deadline. A `deadline_exceeded` result would be recorded as measured.

The scope diff of the whole spec is the 39 files that the header rules move from out to in: the 36 above plus `libtiff_deflate-last-strip-extra-data.tiff`, `pillow_cross_scan_line_truncated.tga` and `pillow_cross_scan_line.tga`. Task 12 moved `pillow_cross_scan_line.tga` itself (in scope, FAILED, an open failure with the note above); Task 37 moves the other 38. The 16 files that stay out are the four CCITT TIFFs, `libtiff_ojpeg_zackthecat_subsamp22_single_strip.tiff`, `pillow_old-style-jpeg-compression.tif`, `libtiff_quad-tile.jpg.tiff`, `pillow_hopper_webp.tif`, `libtiff_logluv-3c-16b.tiff`, `pillow_tiff_strip_planar_raw.tif`, the four Predictor 2 files, `pillow_negative_size.ppm` and `pillow_ossfuzz-4836216264589312.pcx`.

## Decisions

D1. **A new probe for PNM, not a widened PBM probe.** The PBM probe's contract is the exact signature `P4\n` and a two-token header line (engine Requirement 2.7), and its tests pin that. A second probe leaves every P4 result byte for byte as it is and gives text and binary PNM their own grammar. The cost is one more name in `PROBES` and in the web stage list.

D2. **Two new reasons, `sample_above_maxval` and `decoder_malformed`.** An earlier draft reused `decoder_overrun` and `decoder_underrun`. Every reason is put into plain words on the screen (`decoder_overrun`: "a run would write past the size of the picture"; `decoder_underrun`: "the data ran out before the picture was full"), and a sample above the declared maximum, a corrupt stream or a stray token is neither, so the screen would state something false. The vocabulary of engine Requirement 5.6 therefore gains these two (Requirement 2.16), each with the decoder state it comes from (`above_maxval`, `malformed`). `underrun` keeps only "the region ended before the output was full", and `overrun` only "the output would exceed the bound". `web/serialise.py` passes both through unchanged; Claude Code adds their words in `public/js/words.js`, and until then the screen shows what it shows for an unknown reason. Nothing under `public/` is edited here.

D3. **P1 digits are numbers.** Principle call 1 stands as written. Its word "number" is, in P1, one `0` or `1` character, because whitespace between P1 pixels is optional in the format's fixed layout (Requirement 4.4). The wording is folded into Decision Record item 28. P2 and P3 keep their whitespace rule. In P1 a digit `2` to `9` is above the maximum 1 (`sample_above_maxval`), and any non-digit that is not whitespace or a comment is `decoder_malformed`. This reads the two instructions that overlap ("any character other than 0, 1, whitespace or a comment is malformed" and "a P1 digit greater than the maximum is `sample_above_maxval`") so that each state has one meaning; the digits `2` to `9` are the case where they meet.

D4. **Strips keep the single-strip path.** Count 1 leaves `ranges` empty and the hypothesis key unchanged. A multi-strip file takes the new path. This is why Requirement 8.10 can promise that no single-strip result moves.

D5. **Indexed FieldRecord names for arrays.** Engine Requirement 8.3 says FieldRecords that share a name hold the same value. Strip offsets differ from each other, so each is named with its index.

D6. **A disjointness rule between ranges.** Two units cannot own the same byte. This follows the reasoning of engine Decision Record item 17 and needs no format knowledge.

D7. **Predictor refusal by encoding name and by a probe rejection.** The encoding name sends the hypothesis to the existing `unsupported_encoding` path, so it can never reach a decoder. The probe rejection puts the tag and value in front of the reader.

D8. **LZW may end without `EOI` at the exact end.** Reversed 26 Nov 2026 (engine Decision Record item 33). Principle call 2 asks for exact output and an end exactly at the declared end. A strip that meets both without `EOI` (output full, fewer bits left than one code, no whole byte) is `ok`, because requiring `EOI` is an encoder convention the file does not declare. Output full with a whole byte left is still `unconsumed`; a short output is still `underrun`.

D9. **`DECODE_CAP` is 8 MiB.** It is below the largest corpus strip with room to spare (3 MB) and bounds both memory and the time of the pure-Python decoders. Requirement 15.3 measures the worst case and lowers the cap if the measure exceeds 2 seconds.

D10. **Multi-range emission is `file`.** See Emission.

D11. **LZMA reads xz only.** The one corpus LZMA file is xz. A `.lzma` (alone) stream or a raw stream would be `malformed`.

## Limits

- Predictor 2 and 3 are refused, not decoded (Principle call 4).
- FillOrder (tag 266) is not read. A TIFF with FillOrder 2 is decoded as if it were 1 and will fail closure, or in the uncompressed case resolve with bits reversed. No corpus file declares FillOrder 2 (measured from header bytes). Reading it is a separate decision.
- SampleFormat and ExtraSamples are not read; a floating-point or signed-sample TIFF resolves as integers and its renderer shows it so.
- Old-style (LSB-first) LZW is not read.
- P2 and P3 files with no whitespace between numbers fail (Requirement 4.13). P1 files with runs of digits are read (Requirement 4.4).
- Palette indices are not interpreted (a TIFF palette image resolves to its indices).
- Several-range TIFF specs are emitted as `file` layouts.
- Only xz LZMA; only zlib Deflate.
- BigTIFF (magic 43) is not read.

## Out of scope

CCITT G3/G4, JPEG, old-style JPEG, WebP, SGILog, ZSTD, planar configuration 2, BMP, PAM (`P7`), 16-bit RGB TIFF rendering, Predictor decoding, and anything else not in the six layouts. Pillow or any other image library inside the engine. Changes under `public/`.

## Demonstration (each under 20 seconds)

Each layout is shown by dropping one corpus file onto the existing upload screen. The result page already shows the recovered picture, the data range, the closure line and the emitted spec.

| Layout | File | What appears |
|---|---|---|
| P5 / P6 | `libtiff_minisblack-1c-8b.pgm` / `libtiff_rgb-3c-8b.ppm` | the picture, header 15, closure `exact` |
| P2 / P3 | `imagemagick_input_p2.pgm` / `imagemagick_input_p3.ppm` | the picture from ASCII numbers |
| RLE TGA | `pillow_200x32_rgb_tl_rle.tga` | the picture, `rle_tga` |
| Multi-plane PCX | `imagemagick_input.pcx` | the picture from three planes |
| Multi-strip TIFF | `libtiff_rgb-3c-8b.tiff` | 9 data ranges listed |
| Tiled TIFF | `pillow_tiff_tiled_raw.tif` | tile grid, assembled picture |
| PackBits / LZW / Deflate / LZMA | `goimage_bw-packbits.tiff` / `goimage_blue-purple-pink.lzwcompressed.tiff` / `goimage_bw-deflate.tiff` / `pillow_hopper_lzma.tif` | the picture and the decoder named |
| A refusal | `pillow_hopper_lzw.tif` | FAILED with `predictor (tag 317) = 2 is declared and not implemented` |

## Testing summary

| Level | Where | What |
|---|---|---|
| Decoder | `tests/test_decoders.py` | fixtures from documented encoders in the test file; every state of every decoder; Hypothesis never-raises on `st.binary()` |
| Closure | `tests/test_closure_ranges.py`, `tests/test_closure_maxval.py` | ranges, disjointness, per-range Requirement 12, tiles with partial edges, maxval rule |
| Probe | `tests/test_probe_pnm.py`, `tests/test_probes_planes_strips.py` | crafted headers byte by byte; never-raises |
| Engine | `tests/test_format_coverage.py` | crafted files for every layout: status, key, data region, exact pixels; refusals by name |
| Render | `tests/test_pixels_coverage.py` | exact RGB/grey values per layout |
| Emission | `tests/test_emit_coverage.py` | reference reader passes plain pytest on emitted specs; do-nothing parser fails; byte-diff of unchanged specs |
| Corpus | `tests/test_real_corpus.py` | live equals committed results; manifest equals scope script |

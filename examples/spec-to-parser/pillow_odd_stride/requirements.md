# Requirements Document

## Introduction

This document describes the layout of one source file as recovered by NECROPSY (slug `pcx`, layout kind `format`). It states the rules of the format together with the values observed in the source file.

The machine-readable layout is:

```necropsy-layout
{
  "schema": "necropsy-layout/1",
  "kind": "format",
  "slug": "pcx",
  "byte_order": null,
  "fields": [
    {
      "name": "manufacturer",
      "offset": 0,
      "fmt": "B",
      "expect": 10
    },
    {
      "name": "encoding",
      "offset": 2,
      "fmt": "B",
      "expect": null
    },
    {
      "name": "bit_depth",
      "offset": 3,
      "fmt": "B",
      "expect": null
    },
    {
      "name": "xmin",
      "offset": 4,
      "fmt": "<H",
      "expect": null
    },
    {
      "name": "ymin",
      "offset": 6,
      "fmt": "<H",
      "expect": null
    },
    {
      "name": "xmax",
      "offset": 8,
      "fmt": "<H",
      "expect": null
    },
    {
      "name": "ymax",
      "offset": 10,
      "fmt": "<H",
      "expect": null
    },
    {
      "name": "planes",
      "offset": 65,
      "fmt": "B",
      "expect": null
    },
    {
      "name": "bytes_per_line",
      "offset": 66,
      "fmt": "<H",
      "expect": null
    }
  ],
  "tag_table": null,
  "image": {
    "width": {
      "add": [
        {
          "sub": [
            "xmax",
            "xmin"
          ]
        },
        1
      ]
    },
    "height": {
      "add": [
        {
          "sub": [
            "ymax",
            "ymin"
          ]
        },
        1
      ]
    },
    "bit_depth": "bit_depth",
    "row_alignment": 1
  },
  "data": {
    "start": 128,
    "end": null,
    "encoding": {
      "field": "encoding",
      "values": {
        "0": "none",
        "1": "rle_pcx"
      }
    },
    "trailers": [
      {
        "name": "pcx_palette_256",
        "length": 769,
        "signature": "0c",
        "signature_offset": 0
      }
    ]
  },
  "equivalent_reads": {},
  "observed": {
    "width": 371,
    "height": 150,
    "bit_depth": 8,
    "row_alignment": 1,
    "data_start": 128,
    "data_end": 13544
  }
}
```

## Glossary

- **Parser**: A parser that reads the layout described in this document.
- **Source file**: The file NECROPSY analysed to produce this document.
- **Layout block**: The fenced `necropsy-layout` JSON block in the Introduction. It states the same rules in machine-readable form.
- **Closure**: The check that the data region decodes to exactly `row_stride` × `height` bytes.
- **Struct format**: A Python `struct` format string with an explicit byte-order prefix, or `@` where the prefix is declared by the file.

## Requirements

### Requirement 1: Signature and byte order

**User Story:** As a developer, I want the signature and byte order stated precisely, so that I can build a parser from this document alone.

#### Acceptance Criteria

1. THE parser SHALL require `manufacturer` at offset 0x0000 to equal 10 (0x0A), read using struct format `B` (single value, no byte order, 1 byte).

### Requirement 2: Fields

**User Story:** As a developer, I want the fields stated precisely, so that I can build a parser from this document alone.

#### Acceptance Criteria

1. THE parser SHALL read `manufacturer` at offset 0x0000 using struct format `B` (single value, no byte order, 1 byte).
2. THE parser SHALL read `encoding` at offset 0x0002 using struct format `B` (single value, no byte order, 1 byte).
3. THE parser SHALL read `bit_depth` at offset 0x0003 using struct format `B` (single value, no byte order, 1 byte).
4. THE parser SHALL read `xmin` at offset 0x0004 using struct format `<H` (little-endian, 2 bytes).
5. THE parser SHALL read `ymin` at offset 0x0006 using struct format `<H` (little-endian, 2 bytes).
6. THE parser SHALL read `xmax` at offset 0x0008 using struct format `<H` (little-endian, 2 bytes).
7. THE parser SHALL read `ymax` at offset 0x000A using struct format `<H` (little-endian, 2 bytes).
8. THE parser SHALL read `planes` at offset 0x0041 using struct format `B` (single value, no byte order, 1 byte).
9. THE parser SHALL read `bytes_per_line` at offset 0x0042 using struct format `<H` (little-endian, 2 bytes).

### Requirement 3: Data region and encoding

**User Story:** As a developer, I want the data region and encoding stated precisely, so that I can build a parser from this document alone.

#### Acceptance Criteria

1. THE parser SHALL take the image width as ((`xmax` - `xmin`) + 1), the height as ((`ymax` - `ymin`) + 1) and the bit depth as `bit_depth` bits per pixel, with rows padded to a multiple of 1 byte.
2. THE parser SHALL start the data region at 128.
3. THE parser SHALL end the data region at the end of the file, unless a trailer applies.
4. WHEN offset (file length - 769) is at or after the data start and the bytes starting 0 0 bytes after that offset equal the signature 0x0C, THE parser SHALL treat the trailing 769 bytes as trailer `pcx_palette_256` and end the data region at offset (file length - 769).
5. THE parser SHALL decode the data region using encoding selected by the value of `encoding` (0 → `none`, 1 → `rle_pcx`).
6. WHEN the encoding is `none`, THE parser SHALL treat the data region as the pixel bytes as stored, and SHALL require its length to equal row_stride × height.
7. WHEN the encoding is `rle_pcx`, THE parser SHALL decode by reading bytes from the data start while fewer than row_stride × height bytes have been produced and the data region is not exhausted: WHEN a byte b is at least 0xC0, it is a run marker, and the next byte v SHALL be written (b & 0x3F) times (a count of 0 writes nothing); a byte below 0xC0 is one literal output byte. IF the run marker is the last byte of the data region, THEN THE parser SHALL return an error. IF a run would exceed row_stride × height bytes of output, THEN THE parser SHALL return an error. IF the output is shorter than row_stride × height when the data region is exhausted, THEN THE parser SHALL return an error. IF unread bytes remain when the output is complete, THEN THE parser SHALL return an error.
8. THE parser SHALL read the bounds as inclusive, so that width = xmax - xmin + 1 and height = ymax - ymin + 1, as found by the `inclusive_bounds` revision.
9. WHEN parsing the source file, THE parser SHALL find that it closes only through the revision path `inclusive_bounds`.

### Requirement 4: Closure

**User Story:** As a developer, I want the closure rule stated precisely, so that I can build a parser from this document alone.

#### Acceptance Criteria

1. THE parser SHALL accept the data region only when its decoded size equals `row_stride` × `height` bytes, where row_stride = ceil(ceil(width × bit_depth / 8) / row_alignment) × row_alignment.
2. WHEN the encoding is `none`, THE parser SHALL require data_end - data_start to equal row_stride × height.
3. WHEN the encoding is a run-length encoding, THE parser SHALL require the decoder to consume the whole data region and produce exactly row_stride × height bytes.
4. WHEN parsing the source file, THE parser SHALL find row_stride = ceil(ceil(371 × 8 / 8) / 1) × 1 = 371 bytes, an expected size of 371 × 150 = 55650 bytes, and a data region [128, 13544) of 13416 bytes, so that closure holds.

### Requirement 5: Observed values

**User Story:** As a developer, I want the values observed in the source file, so that I can check my parser against it.

#### Acceptance Criteria

1. WHEN parsing the source file, THE parser SHALL return width = 371.
2. WHEN parsing the source file, THE parser SHALL return height = 150.
3. WHEN parsing the source file, THE parser SHALL return bit_depth = 8.
4. WHEN parsing the source file, THE parser SHALL return row_alignment = 1.
5. WHEN parsing the source file, THE parser SHALL return data_start = 128.
6. WHEN parsing the source file, THE parser SHALL return data_end = 13544.
7. THE file `test_pcx.py` SHALL be the acceptance suite for a parser that the reader implements from this document. It SHALL import a module named `parser_pcx` exposing `parse(data)`, returning a dict whose keys `ok`, `fields`, `width`, `height`, `bit_depth`, `row_alignment` and `pixels` are the ones the tests read. THE module `parser_pcx` SHALL NOT be emitted, so `pytest` on the folder as emitted SHALL stop with `ModuleNotFoundError` until the reader supplies it.

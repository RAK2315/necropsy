# Design Document

## Overview

Result `RESOLVED` for slug `pcx` (layout kind `format`): one layout closes. The structure is 371 x 150 at 8 bits per pixel, header size 128.

## Architecture

- stage: `revision`
- source: `pcx`
- revision_path: [inclusive_bounds]

## Components and Interfaces

- data region: [128, 13544)
- trailer: pcx_palette_256
- closure: rle_pcx decoded [128, 13544) to 55650 bytes = 371 x 150, all input consumed
- coherence: heuristic (row_mad_ratio) = 0.3208

## Data Models

| property | value |
|---|---|
| width | 371 |
| height | 150 |
| bit_depth | 8 |
| header_size | 128 |
| row_alignment | 1 |
| encoding | rle_pcx |
| row_stride | 371 |
| expected_decoded_bytes | 55650 |

| offset | field | struct format | value |
|---|---|---|---|
| 0x0002 | encoding | B | 1 |
| 0x0003 | bit_depth | B | 8 |
| 0x0004 | xmin | <H | 0 |
| 0x0006 | ymin | <H | 0 |
| 0x0008 | xmax | <H | 370 |
| 0x000A | ymax | <H | 149 |
| 0x0041 | planes | B | 1 |
| 0x0042 | bytes_per_line | <H | 371 |

## Correctness Properties

### Property 1: Closure holds

The data region decodes to exactly `row_stride` × `height` bytes. closure: rle_pcx decoded [128, 13544) to 55650 bytes = 371 x 150, all input consumed.

**Validates: Requirements 4.1, 3.1**

## Error Handling

Every hypothesis the engine tried and rejected is listed below with its source and reason. 7 rejections recorded.

1. source `pcx`, reason `decoder_overrun`
2. source `pcx`, reason `decoder_overrun`
3. source `revision:inclusive_bounds`, reason `decoder_unconsumed`
4. source `revision:row_padding_variants`, reason `decoder_overrun`
5. source `revision:row_padding_variants`, reason `decoder_overrun`
6. source `revision:row_padding_variants`, reason `decoder_overrun`
7. source `revision:row_padding_variants`, reason `decoder_overrun`


## Testing Strategy

Tests parse the embedded source and assert the observed values and closure, and check that `parse` never raises on arbitrary bytes.

THE file `test_pcx.py` SHALL be the acceptance suite for a parser that the reader implements from this document. It SHALL import a module named `parser_pcx` exposing `parse(data)`, returning a dict whose keys `ok`, `fields`, `width`, `height`, `bit_depth`, `row_alignment` and `pixels` are the ones the tests read. THE module `parser_pcx` SHALL NOT be emitted, so `pytest` on the folder as emitted SHALL stop with `ModuleNotFoundError` until the reader supplies it.

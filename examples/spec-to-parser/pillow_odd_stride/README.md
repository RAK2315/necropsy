# Spec to parser, clean room

`parser_pcx.py` was written from `requirements.md`, `design.md` and `test_pcx.py` in this folder only. No other file of the repo was read to write it. The three spec files are unedited (sha256 checked against `PROVENANCE.md`).

- `parser_pcx.py`: `parse(data)`. It never raises. Failures return `{"ok": False, "error": {"code", "message"}}`.
- `show.py`: parses `spike/samples/real/pillow_odd_stride.pcx` and writes `recovered.png` (371x150). Pillow only writes the PNG.

## pytest result (verbatim)

Command: `python -m pytest examples/spec-to-parser/pillow_odd_stride -q -p no:cacheprovider`

```
....                                                                     [100%]
4 passed in 0.72s
```

## Test failures along the way

None. The first run of the first complete `parser_pcx.py` passed 4 of 4, so no clause had to resolve a failure.

## Where the spec was silent (decisions, not failures)

The tests do not cover these. Each is my reading, not a spec clause.

- Error shape: the spec says "return an error" (3.7) but gives no format. I chose `{"ok": False, "error": {"code", "message"}}`.
- Inputs shorter than 128 bytes, `xmax < xmin` or `ymax < ymin`, and an `encoding` outside {0, 1} are not specified. Each returns an error.
- `design.md` lists 8 fields and omits `manufacturer`, while Requirement 2.1 reads it. I report all 9 in `fields`.
- `test_pcx.py` reads `data_start` and `data_end` from the result, and Requirement 5.7 does not list them among the keys. I return them.

## Step taken from outside the spec

The spec names the trailer `pcx_palette_256` (769 bytes, signature `0x0C`) but never says what it holds. `show.py` uses the 768 bytes after the `0x0C` byte as 256 R,G,B entries. That is the one step not stated in the spec, and `show.py` says so in a comment.

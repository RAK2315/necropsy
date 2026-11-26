# Held-out set: results

The held-out set was fixed on 25 Nov 2026, before any engine work on the `format-coverage` spec began. Its manifest and file hashes were committed that day in [`COMMITMENT.md`](COMMITMENT.md) (commit `33469d0`), while the files themselves were kept outside the repository. The agent building the engine never had them: a Kiro hook blocked any tool call that named them, and the Kiro prompt said they existed and must not be looked for.

The set was evaluated **once**, by Claude Code, on 26 Nov 2026, against the finished `format-coverage` engine at commit `66e85d3`. The results below are that run, as it came out. Nothing in the engine was changed between the run and this write-up. Any later engine change prompted by these results is recorded as such in the commit that makes it.

`python tools/heldout.py verify` was run before the evaluation: the manifest hashed to the committed value and all 55 files matched their committed hashes. The manifest, the files and the licence texts are now published next to this file, so the check can be repeated.

## Sources

| Source | Repository | Commit | Licence | Files | Licence text |
|---|---|---|---|---:|---|
| GDAL autotest data | OSGeo/gdal | `948f102a9e` | MIT | 27 | [GDAL-LICENSE.TXT](LICENSES/GDAL-LICENSE.TXT) |
| TwelveMonkeys ImageIO test data | haraldk/TwelveMonkeys | `7d63718033` | BSD-3-Clause | 17 | [TwelveMonkeys-BSD-3-Clause.txt](LICENSES/TwelveMonkeys-BSD-3-Clause.txt) |
| Apache Commons Imaging test data | apache/commons-imaging | `ccd63531b1` | Apache-2.0 | 11 | [commons-imaging-Apache-2.0.txt](LICENSES/commons-imaging-Apache-2.0.txt), [NOTICE](LICENSES/commons-imaging-NOTICE.txt) |

None of these repositories states a separate licence for its individual test files, so each file is recorded under its repository's licence, as in `spike/samples/real/`. None of the 55 files is byte-identical to any of the 81 real-corpus files. File names carry a prefix for their source (`gdal_`, `tm_`, `cimg_`).

## How it was measured

For each file: the engine's result, then the picture the web service would show (`web.serialise.to_payload`, the same code the live site uses), compared byte for byte with Pillow 12.2.0's decode converted to the same mode. This is a separate check from `tools/real_corpus.py`, written by Claude Code, so the comparison does not share code with the engine's own corpus tool. For the one 16-bit file, Pillow's samples were scaled the same way the render scales them (`v × 255 // 65535`) before comparing.

"Scope" in the table is read from each file's header bytes against the `format-coverage` rules (PNM P1 to P6; PCX encoding 0 or 1, any number of planes; TGA image types 1, 2, 3, 9, 10, 11; TIFF compression none, PackBits, LZW, Deflate or LZMA, planar configuration 1, no predictor). It is not an engine result.

## Summary

**55 files the engine had never seen. 43 RESOLVED, 12 FAILED. Every recovered picture that Pillow can also show is identical to Pillow's: 39 of 39. Of the 12 FAILED, 5 are files Pillow refuses too and 3 are out of scope; on the other 4, NECROPSY refused rather than drew a wrong picture.**

- **52 in scope:** 43 RESOLVED, 9 FAILED.
- **3 out of scope**, all FAILED with the reason named: one declares Predictor 2, two declare planar configuration 2.

Of the 43 RESOLVED files:

- **39 show exactly Pillow's pixels.**
- **3 are files Pillow refuses.** Two are multi-plane PCX files from Apache Commons Imaging; each renders identically to a sibling that Pillow does read (details below). The third is a 4-bit RGBA TIFF whose layout resolves but whose picture is drawn wrongly (below).
- **1 has no picture:** a 16-bit grey-and-alpha run-length TGA. The engine resolves it, but there is no renderer for 16-bit TGA pixels.

Of the 9 in-scope FAILED files:

- **4 are invalid by construction**, as the upstream test suite says, and Pillow refuses all four. FAILED is the right answer.
- **1 is a valid file that Pillow also refuses** (`gdal_contig_tiled.tif`).
- **4 are valid files that Pillow reads and NECROPSY does not yet.** In each case the engine stopped and reported why, instead of producing a wrong picture. Each cause is measured below, and each is a single, specific rule.

## Not recovered yet: four valid files

| File | What the engine reported | Cause, from the bytes |
|---|---|---|
| `tm_autodesk-3dsmax-extsize494.tga` | `field_out_of_bounds` on the footer reading; `decoder_unconsumed`, 521 bytes left, on the end-of-file reading | The TGA 2.0 extension area declares size 494. The engine's rule (Decision Record item 22) treats any size below 495 as a self-contradiction and rejects the footer reading. The upstream file name names Autodesk 3ds Max as the writer and the extension size 494. |
| `tm_0112eccd-2c29-4368-bcef-59c823b6e5d1.tga` | the same two rejections, 521 bytes left | Its extension area declares size 0, also below 495, so the same rule rejects the footer reading. |
| `tm_circle2.pnm` | `no_hypothesis_checked`, 0 checks | A binary PBM whose magic `P4` is followed by a space, not a newline. The PBM probe still requires the exact bytes `P4\n`, and the new PNM probe covers P1, P2, P3, P5 and P6 only, so no probe matched. |
| `tm_packbits-fillorder-2.tif` | `decoder_underrun`: the region ended inside a PackBits literal packet at offset 70719 | The strip ends inside a literal packet: the packet's header asks for more bytes than remain. Pillow decodes the file. The file also declares FillOrder 2, which the engine does not read. |

## The files Pillow refuses

- **`cimg_3plane8bppUncompressed.pcx`** (3 planes of 8 bits, encoding byte 0). RESOLVED. Its rendered picture is byte-identical to the rendered picture of `cimg_3plane8bppCompressed.pcx`, the same 10 × 10 image stored with run-length encoding, which Pillow reads and NECROPSY matches. Pillow raises `OSError: buffer overrun when reading image file`.
- **`cimg_3plane1bppCompressed.pcx`** (3 planes of 1 bit, an 8-colour image). RESOLVED. It renders as the same red "A" on white as its 2-plane and 4-plane siblings, both of which Pillow reads and NECROPSY matches. Pillow raises `OSError: unknown PCX mode`.
- **`tm_lzw-rgba-4444.tif`** (LZW, four 4-bit samples per pixel). The layout RESOLVES, but the picture is wrong: the four 4-bit samples are drawn as one 16-bit grey value, so a colour image of a camera appears as a grey one. This is a defect in the renderer (`web/pixels.py`), which does not take the samples per pixel into account at this bit depth. Pillow raises `UnidentifiedImageError`.
- **`gdal_contig_tiled.tif`**. FAILED. Its single 64 × 64 PackBits tile decodes to 7104 bytes (37 rows of the tile's 64-pixel width), where a full tile needs 12288. The encoder stopped at the image's last row instead of writing the whole tile. GDAL reads the file (its test suite groups it under "partial final strip/tiles"). Pillow refuses it too.

What these two files show: on held-out files that Pillow cannot open, NECROPSY recovered a picture, and each picture equals one Pillow does read from a sibling file. That is the claim, stated exactly; on this set Pillow also reads four valid files that NECROPSY does not yet, listed above.

## Every file

| File | Format | Header facts | Scope | NECROPSY | Pillow | Pixels (on-screen render vs Pillow) |
|---|---|---|---|---|---|---|
| `cimg_1plane8bppCompressed.pcx` | PCX | 1 plane(s), 8 bit, encoding 1 | in | RESOLVED | decodes | match |
| `cimg_2plane1bppCompressed.pcx` | PCX | 2 plane(s), 1 bit, encoding 1 | in | RESOLVED | decodes | match |
| `cimg_3plane1bppCompressed.pcx` | PCX | 3 plane(s), 1 bit, encoding 1 | in | RESOLVED | **refuses** | rendered; pillow refuses |
| `cimg_3plane8bppCompressed.pcx` | PCX | 3 plane(s), 8 bit, encoding 1 | in | RESOLVED | decodes | match |
| `cimg_3plane8bppUncompressed.pcx` | PCX | 3 plane(s), 8 bit, encoding 0 | in | RESOLVED | **refuses** | rendered; pillow refuses |
| `cimg_4plane1bppCompressed.pcx` | PCX | 4 plane(s), 1 bit, encoding 1 | in | RESOLVED | decodes | match |
| `cimg_Oregon_Scientific_DS6639_-_DSC_0307_-_small.pbm` | PNM | P4 | in | RESOLVED | decodes | match |
| `cimg_Oregon_Scientific_DS6639_-_DSC_0307_-_small.pcx` | PCX | 3 plane(s), 8 bit, encoding 1 | in | RESOLVED | decodes | match |
| `cimg_Oregon_Scientific_DS6639_-_DSC_0307_-_small.pgm` | PNM | P5 | in | RESOLVED | decodes | match |
| `cimg_Oregon_Scientific_DS6639_-_DSC_0307_-_small.ppm` | PNM | P6 | in | RESOLVED | decodes | match |
| `cimg_Oregon_Scientific_DS6639_-_DSC_0307_-_small.tga` | TGA | type 2, 24 bit | in | RESOLVED | decodes | match |
| `gdal_byte.pnm` | PNM | P5 | in | RESOLVED | decodes | match |
| `gdal_byte.tif` | TIFF | none, 1 strip(s), [8] bits | in | RESOLVED | decodes | match |
| `gdal_byte_DEFLATE.tif` | TIFF | Adobe Deflate, 1 strip(s), [8] bits | in | RESOLVED | decodes | match |
| `gdal_byte_DEFLATE_tiled.tif` | TIFF | Adobe Deflate, 4 tiles, [8] bits | in | RESOLVED | decodes | match |
| `gdal_byte_LZMA.tif` | TIFF | LZMA, 1 strip(s), [8] bits | in | RESOLVED | decodes | match |
| `gdal_byte_LZMA_tiled.tif` | TIFF | LZMA, 4 tiles, [8] bits | in | RESOLVED | decodes | match |
| `gdal_byte_LZW.tif` | TIFF | LZW, 1 strip(s), [8] bits | in | RESOLVED | decodes | match |
| `gdal_byte_LZW_predictor_2.tif` | TIFF | LZW, 1 strip(s), [8] bits, predictor 2 | out | FAILED (exhausted) | decodes |  |
| `gdal_byte_LZW_tiled.tif` | TIFF | LZW, 4 tiles, [8] bits | in | RESOLVED | decodes | match |
| `gdal_byte_NONE_tiled.tif` | TIFF | none, 4 tiles, [8] bits | in | RESOLVED | decodes | match |
| `gdal_byte_buggy_packbits.tif` | TIFF | PackBits, 20 strip(s), [8] bits | in | FAILED (exhausted) | **refuses** |  |
| `gdal_classictiff_four_strip_short.tif` | TIFF | none, 4 strip(s), [8] bits | in | RESOLVED | decodes | match |
| `gdal_classictiff_two_strip_be_short.tif` | TIFF | none, 2 strip(s), [8] bits | in | RESOLVED | decodes | match |
| `gdal_contig_strip.tif` | TIFF | PackBits, 1 strip(s), [8, 8, 8] bits | in | RESOLVED | decodes | match |
| `gdal_contig_tiled.tif` | TIFF | PackBits, 1 tiles, [8, 8, 8] bits | in | FAILED (exhausted) | **refuses** |  |
| `gdal_int_max.pgm` | PNM | P5 | in | FAILED (exhausted) | **refuses** |  |
| `gdal_lzw_corrupted.tif` | TIFF | LZW, 1 strip(s), [8] bits | in | FAILED (exhausted) | **refuses** |  |
| `gdal_packbits-not-enough-data.tif` | TIFF | PackBits, 1 strip(s), [1] bits | in | FAILED (exhausted) | **refuses** |  |
| `gdal_rgbsmall.ppm` | PNM | P6 | in | RESOLVED | decodes | match |
| `gdal_rgbsmall.tif` | TIFF | Deflate, 3 strip(s), [8, 8, 8] bits, planar 2 | out | FAILED (exhausted) | decodes |  |
| `gdal_rgbsmall_DEFLATE.tif` | TIFF | Adobe Deflate, 1 strip(s), [8, 8, 8] bits | in | RESOLVED | decodes | match |
| `gdal_rgbsmall_LZMA.tif` | TIFF | LZMA, 1 strip(s), [8, 8, 8] bits | in | RESOLVED | decodes | match |
| `gdal_rgbsmall_LZW.tif` | TIFF | LZW, 1 strip(s), [8, 8, 8] bits | in | RESOLVED | decodes | match |
| `gdal_rgbsmall_NONE_separate.tif` | TIFF | none, 3 strip(s), [8, 8, 8] bits, planar 2 | out | FAILED (exhausted) | decodes |  |
| `gdal_rgbsmall_NONE_tiled.tif` | TIFF | none, 8 tiles, [8, 8, 8] bits | in | RESOLVED | decodes | match |
| `gdal_stefan_full_rgba.tga` | TGA | type 2, 32 bit | in | RESOLVED | decodes | match |
| `gdal_uint16.pnm` | PNM | P5, maximum value 65535 | in | RESOLVED | decodes | match, with Pillow's 16-bit samples scaled as the render scales them (`v × 255 // 65535`); `results.json` holds the raw unscaled comparison |
| `tm_0112eccd-2c29-4368-bcef-59c823b6e5d1.tga` | TGA | type 10, 24 bit | in | FAILED (exhausted) | decodes |  |
| `tm_692c33d1-d0c3-4fe2-a059-f199d063bc7a.tga` | TGA | type 2, 24 bit | in | RESOLVED | decodes | match |
| `tm_alpha-no-extension.tga` | TGA | type 2, 32 bit | in | RESOLVED | decodes | match |
| `tm_autodesk-3dsmax-extsize494.tga` | TGA | type 10, 32 bit | in | FAILED (exhausted) | decodes |  |
| `tm_circle2.pnm` | PNM | P4 | in | FAILED (no_hypothesis_checked) | decodes |  |
| `tm_colors.ppm` | PNM | P3 | in | RESOLVED | decodes | match |
| `tm_feep.pgm` | PNM | P2 | in | RESOLVED | decodes | match |
| `tm_gogol.ppm` | PNM | P6 | in | RESOLVED | decodes | match |
| `tm_house.l.pgm` | PNM | P5 | in | RESOLVED | decodes | match |
| `tm_j.pbm` | PNM | P1 | in | RESOLVED | decodes | match |
| `tm_lzw-rgba-4444.tif` | TIFF | LZW, 1 strip(s), [4, 4, 4, 4] bits | in | RESOLVED | **refuses** | rendered; pillow refuses |
| `tm_monochrome16_top_left_rle.tga` | TGA | type 11, 16 bit | in | RESOLVED | decodes | no render: no renderer for 16-bit pixels |
| `tm_packbits-fillorder-2.tif` | TIFF | PackBits, 1 strip(s), [1] bits, fill order 2 | in | FAILED (exhausted) | decodes |  |
| `tm_rays2.pnm` | PNM | P5 | in | RESOLVED | decodes | match |
| `tm_sm_colors_pb.tif` | TIFF | PackBits, 2 strip(s), [8, 8, 8] bits | in | RESOLVED | decodes | match |
| `tm_sm_colors_pb_tile.tif` | TIFF | PackBits, 2 tiles, [8, 8, 8] bits | in | RESOLVED | decodes | match |
| `tm_sm_colors_tile.tif` | TIFF | none, 2 tiles, [8, 8, 8] bits | in | RESOLVED | decodes | match |

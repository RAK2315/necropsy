# Acceptance pass on https://necropsy.vercel.app

| Req | Beat | Time on screen | Result | Capture |
|---|---|---|---|---|
| 13.5a | RESOLVED result with its recovered image (external_a) | 2.5 s | pass: status: RESOLVED; image: Recovered image, 64 × 48, 8-bit | [resolved.png](resolved.png) |
| 13.5b | declared-versus-actual contradiction (mystery_i) | 6.3 s | pass: declared: none (byte 0x02 = 0x00); actual: rle_pcx; inViewport: True | [lying_header.png](lying_header.png) |
| 13.5c | ambiguity screen, all candidates side by side (mystery_d) | 0.8 s | pass: statement: 18 readings fit these bytes exactly. Each one passes closure. The bytes cannot separate them, so NECROPSY does not choose.; cards: 18; sizes: ['208x400'] | [ambiguity.png](ambiguity.png) |
| 13.5d | FAILED screen for a non-image file (a text file) | 1.0 s | pass: reason: No hypothesis reached the closure gate.; termination: termination no_hypothesis_checked | [failed.png](failed.png) |
| 13.5e | emitted spec panel and its download (mystery_e) | 1.0 s | pass: folder: tiff/; zip: tiff.zip; zipBytes: 5449; tabs: ['requirements.md', 'design.md', 'test_tiff.py'] | [spec_panel.png](spec_panel.png) |
| 16 | outcome strip: three real results on the first screen | 0.7 s | pass: tiles: ['RESOLVED: One layout closes.', 'UNRESOLVED_AMBIGUITY: 18 readings fit, so NECROPSY does not choose.', 'FAILED: Nothing closed, and here is why.']; dropFits: True | [outcome_strip.png](outcome_strip.png) |
| 17 | PNG and data-region downloads (external_a) | 2.6 s | pass: files: ['external_a_64x48_8bit.png (image/png, 488 bytes)', 'external_a_64x48_8bit_data_128-393.bin (application/octet-stream, 265 bytes)'] | [downloads.png](downloads.png) |
| 18 | three files dropped at once | 2.5 s | pass: notice: 3 files were dropped. NECROPSY examines one file at a time: it examined holiday.pcx and ignored 2 others: notes.txt, blob.bin.; examined: 64 × 48 · 8-bit | [multi_drop.png](multi_drop.png) |
| 19 | error copy: a file over the limit | 0.3 s | pass: message: That file is 70,000 bytes. The limit is 65,536 bytes. Try a smaller file or a fragment of it. | [error_copy.png](error_copy.png) |
| 20 | keyboard: Tab to the second tile, Enter, then Escape | 0.7 s | pass: tabPresses: 2; focusRing: solid; openedCards: 18; escapeReturned: True | [keyboard.png](keyboard.png) |

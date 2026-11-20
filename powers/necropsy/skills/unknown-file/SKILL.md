---
name: unknown-file
description: Use when you meet a file you cannot open, such as an image with no extension or an unrecognised binary. Calls NECROPSY's analyse tool to infer the file's structure from its bytes, reports every candidate layout, and never picks one when the bytes cannot separate them.
---

# Treating an unknown file

NECROPSY infers a file's layout from its bytes and checks each layout by arithmetic: the header, the pixel data and any trailer must account for every byte of the file. Use it instead of guessing from the file name, a few magic bytes, or what the file looks like.

## Steps

1. **Call `analyse` first.** Give it the file's `path`, or `data_base64` if you only hold the bytes. Do this before reading the file yourself or proposing a layout. The limit is 65,536 bytes. A larger file returns the error `file_too_large`: say so and stop. Do not truncate the file and analyse the piece.
2. **Read `status`**, then report in these terms:
   - **RESOLVED.** One layout closes. Report its width, height, bit depth, header size, encoding, data region and the closure line. You may rely on this layout.
   - **UNRESOLVED_AMBIGUITY.** Several layouts close and the bytes cannot separate them. This is a correct result. Report **every** candidate, with its count, in the order the tool returned them. Do not pick one. Do not rank them by `coherence_score`: it is a heuristic and the tool says it does not choose. State what extra information would decide (a file name, a declared format, a larger sample from the same source).
   - **FAILED.** Nothing closed. Report `termination` (for example `exhausted` or `no_hypothesis_checked`) and what `rejection_counts` says was tried. Stop. Do not offer a layout the tool did not return.
   **If the tool result arrives truncated** (Kiro shows a result over 30,000 characters as only its first and last 500 and saves the full output to a file), read the saved full output before answering. Never report candidates, a candidate count or a status from a truncated view: the middle of the result is where the other candidates are.
3. **Report only what the result contains.** Quote values from the payload. If the payload has no field for something, say that it is not known.
4. **Call `emit_spec` only when the user asks for a spec**, and only after `analyse`. It returns the spec files, or `nothing_recovered` with a message when the result is FAILED. For an ambiguous result the spec lists every candidate and prefers none: pass that on unchanged.

## Never

- Never choose between candidates on your own, by looks, by size, or by "most likely".
- Never describe a candidate as the file's format. A result describes this file's layout. It does not name a format unless a probe matched one.
- Never retry the tool with a modified file to get a better answer.

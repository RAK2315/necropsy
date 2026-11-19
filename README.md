# NECROPSY

NECROPSY takes a file whose format is unknown, works out from the raw bytes how it is laid out as a raster image, and recovers the pixels only when the layout can be checked exactly.

## The problem

Files outlive the software that wrote them, and an image saved in a format nothing installed today can open is effectively lost even though every byte is intact. This is often called the digital dark age. NECROPSY treats such a file as a specimen: it examines the bytes, proposes how they are structured, and checks each proposal before it trusts it.

## Live demo and video

- Live demo: TODO
- Demo video (under 3 minutes): TODO

## Screenshots

- TODO: screenshot. A RESOLVED recovery: the recovered image next to the field table and the closure line that verified it.
- TODO: screenshot. A declared-versus-actual contradiction: a PCX whose encoding byte declares "uncompressed" (mystery_i), where closure only holds once revision reads the data as RLE.
- TODO: screenshot. The ambiguity screen: several layouts that all pass closure, shown side by side with none marked as preferred.

## How it works

The engine (`necropsy/engine/`) has one entry point, `Engine().run(data)`. It returns exactly one of three outcomes: `RESOLVED`, `UNRESOLVED_AMBIGUITY` or `FAILED`.

### Probes read what the file declares about itself

There are four probes: PCX, TGA, PBM and TIFF. Each applies its format's fixed layout (offsets, field widths, header length, byte order) and reads the file's own declarations, such as the PCX encoding byte or the TIFF byte-order mark. When a signature matches, the probe always emits one seed hypothesis, even if the values it read are wrong, so that a damaged file can still be revised.

### Revision strategies recover from declarations that are wrong

A seed that fails closure is revised by exactly three strategies: `inclusive_bounds`, `rle_pcx` and `row_padding_variants`. Revision searches breadth-first to depth 3 and collects every closing candidate at a depth before deciding, so the order the strategies are listed in never picks the answer. Revision never changes byte order, field width or header length.

### Generic search handles files with no recognised header

When no probe signature matches, generic search tries header lengths 4, 8, ..., 256. At each length it tries every width and height read in `<H`, `>H`, `<I`, `>I`, `<i` and `>i`, and every bit depth in {1, 4, 8, 16, 24, 32}. It reports every closing layout, and lists every equivalent read of a field rather than choosing one.

### Closure is the gate

A hypothesis is accepted only when decoding its data region gives exactly `row_stride x height` bytes and consumes the whole region, where `row_stride = round_up(ceil(width x bit_depth / 8), row_alignment)`. The check is binary. No score can admit a hypothesis that fails it, or reject one that passes.

### The principle: declarations versus conventions

The design rests on one rule from the engine spec's Decision Record: **probes read declarations and never apply conventions.** A declaration is something the file states about itself, such as "this data is RLE compressed". A convention is knowledge that is not in the file, such as "width is `xmax - xmin + 1`". Probes read the first kind; revision strategies discover the second. The spec puts it this way: a probe that reads a byte saying "RLE compressed", ignores it, fails closure and then has a revision strategy guess RLE "would be theatre".

## What it will not do

**It will not choose between readings that the bytes cannot separate.** mystery_d is a headerless 104-byte blob, and 18 layouts pass closure on it. Two of them are 8x8 at 8 bpp and 64x8 at 1 bpp, both with a 40-byte header. They read the same 64 bytes at the same 8-byte row stride, and both are true readings of those bytes. The engine returns `UNRESOLVED_AMBIGUITY` with all 18 candidates and promotes none.

**Coherence is a heuristic that never decides.** Each candidate gets a row-coherence score (`row_mad_ratio`, lower is more coherent), which is reported but never used to gate, promote or order candidates. Its three known failure modes, from the spec and the code's docstring:

1. Narrower strides score better on smooth images.
2. Identical bytes at an identical stride, split into different bit depths, score identically.
3. A header can absorb whole rows.

All three are real on the corpus. On mystery_d, the true 8x8 at 8 bpp and the wrong 64x8 at 1 bpp both score 0.3342 (failure mode 2). The wrong 8x64 at 1 bpp scores 0.1646, which counts as more coherent than the true answer (failure mode 1). Only 9 of mystery_d's 18 candidates can be scored at all.

**Generic search is not exhaustive.** It covers the axes above, with a 5.0-second deadline and a cap of 10,000 closure checks per run. A `FAILED` result means no closing layout was found within those axes and that budget, not that the file has no valid layout.

**Other limits, from the specs and the code:**

- Only `none` and PCX RLE are decoded. TGA RLE and compressed TIFF are recognised from their declarations, then rejected as `unsupported_encoding`.
- Only single-strip TIFF files are in scope.
- The PCX seed uses bits per plane and ignores the `planes` field, so a PCX with several colour planes normally comes out `FAILED`.
- Rows are taken as stored. The UI spec plans to honour a TGA's declared origin, but the DIB height sign is not read, so a bottom-up DIB would appear upside down.
- The web UI is specified (`.kiro/specs/necropsy-ui/`) but not yet built: 0 of its 16 tasks are complete. Its hosting choice is still an open item in that spec.

## Spec emission

When the engine resolves a file, or reaches an unresolved ambiguity, `necropsy.emit` can write a Kiro-format spec folder for what it recovered: `requirements.md`, `design.md` and `test_<slug>.py`. The slug is the probe name (`pcx`, `tga`, `pbm`, `tiff`), or `unknown-<first 8 hex digits of SHA-256>` when generic search produced the result. A `FAILED` result emits nothing.

`requirements.md` states every field, the data region, the encoding and the closure rule in EARS form. It also embeds one machine-readable `necropsy-layout` block. This is the closure criterion from the spec emitted for mystery_e (`build/emitted/tiff/requirements.md`, lines 188 and 191):

> 1. THE parser SHALL accept the data region only when its decoded size equals `row_stride` × `height` bytes, where row_stride = ceil(ceil(width × bit_depth / 8) / row_alignment) × row_alignment.
>
> 4. WHEN parsing the source file, THE parser SHALL find row_stride = ceil(ceil(8 × 8 / 8) / 1) × 1 = 8 bytes, an expected size of 8 × 8 = 64 bytes, and a data region [86, 150) of 64 bytes, so that closure holds.

The emitted `test_<slug>.py` imports a module named `parser_<slug>`, which is not emitted. On its own, `pytest` in an emitted folder stops with `ModuleNotFoundError: No module named 'parser_tiff'`. The repo's acceptance test (`tests/test_emit_acceptance.py`) builds that module from the emitted `requirements.md` alone, using a reference reader that imports nothing from `necropsy`. It places the module next to the emitted tests and runs plain `pytest` in that folder. That passes for the TGA (mystery_c) and TIFF (mystery_e) specs.

`build/` is gitignored. The Quickstart shows how to regenerate the TIFF spec.

## The corpus

Nine samples in `spike/samples/`, generated byte by byte by `spike/make_samples.py`. The outcomes below come from running `Engine().run()` on each file at commit `38bbbbc`. They match the corpus trace recorded in the engine's `design.md`.

| File | What it is | Outcome | Checks | Revision path |
|---|---|---|---|---|
| mystery_a | 4x4 binary PBM (P4), 11 bytes | RESOLVED by PBM probe: 4x4, 1 bpp, header 7 | 1 | none |
| mystery_b | 8x8 RLE PCX with 256-colour palette, 955 bytes | RESOLVED: 8x8, 8 bpp, rle_pcx, region [128, 186), trailer `pcx_palette_256` | 4 | `inclusive_bounds` |
| mystery_c | 16x16 uncompressed 24-bit TGA, 786 bytes | RESOLVED by TGA probe: 16x16, 24 bpp, header 18 | 1 | none |
| mystery_d | 8x8 8 bpp DIB body with no file header, 104 bytes | UNRESOLVED_AMBIGUITY (generic): 18 candidates, including 8x8, 8 bpp, header 40 | 18 | - |
| mystery_e | 8x8 8 bpp big-endian TIFF ("MM"), 150 bytes | RESOLVED by TIFF probe: 8x8, 8 bpp, region [86, 150) | 1 | none |
| mystery_f | 12x10 8 bpp, dimensions as 32-bit little-endian, 132 bytes | UNRESOLVED_AMBIGUITY (generic): 8 candidates, including 12x10, 8 bpp, header 12 | 8 | - |
| mystery_g | 8x8 24 bpp with a non-standard 20-byte header, 212 bytes | UNRESOLVED_AMBIGUITY (generic): 8 candidates, including 8x8, 24 bpp, header 20 | 8 | - |
| mystery_h | 6x6 uncompressed PCX, rows padded to 4 bytes, 176 bytes | RESOLVED: 6x6, 8 bpp, alignment 4, stride 8 | 10 | `inclusive_bounds`, `row_padding_variants` |
| mystery_i | mystery_b with the encoding byte corrupted to 0x00, 955 bytes | RESOLVED: 8x8, 8 bpp, rle_pcx, region [128, 186) | 10 | `inclusive_bounds`, `rle_pcx` |

None of the nine files fails. For mystery_h and mystery_i, the engine also reports the second, reversed path that reaches the same answer at the same depth, as `alternative_paths`.

## Quickstart

Tested with Python 3.10.11, pytest 9.1.1 and Hypothesis 6.168.5 on Windows. Every command below was run in a fresh clone. The engine itself uses only the standard library.

```
git clone https://github.com/RAK2315/necropsy.git
cd necropsy
python -m pip install pytest hypothesis
```

Run the engine on a sample and print the report:

```
python -c "from necropsy.engine import Engine; from necropsy.report import render; print(render(Engine().run(open('spike/samples/mystery_e', 'rb').read())))"
```

The report for mystery_e starts with `RESOLVED`, then lists the field table, and ends with:

```
closure: [86, 150) holds 64 bytes = 8 x 8
revision_path: []
```

Swap in `mystery_d` to see an ambiguous result. Its report starts with `UNRESOLVED_AMBIGUITY: 18 candidates close; the bytes cannot distinguish them`.

Emit the spec for mystery_e into `build/emitted/tiff/`:

```
python -c "from necropsy.engine import Engine; from necropsy.emit import emit_spec, write_spec; d = open('spike/samples/mystery_e', 'rb').read(); print(write_spec(emit_spec(Engine().run(d), d), 'build/emitted'))"
```

Run the test suite:

```
python -m pytest tests -q
```

Result at commit `38bbbbc`: 263 passed, in 10.72 s on the development machine and 12.69 s in the fresh clone.

## Built with Kiro

Everything below can be checked in `.kiro/`, in `docs/KIRO-LOG.md` and in the git history. Figures are as of commit `38bbbbc`.

**Specs.** There are two specs, each with `requirements.md`, `design.md` and `tasks.md`:

- `.kiro/specs/structure-inference-engine/`: 11 requirements, 45 tasks, all checked off. The design records 15 numbered correctness properties.
- `.kiro/specs/necropsy-ui/`: 15 requirements and 16 tasks, none started yet.

Tasks cite the requirements they implement in `_Requirements: ..._` lines: 35 in the engine plan and 16 in the UI plan. 60 of the 82 commits are per-task commits named `Task <n>.<m>: ...`.

**Steering.** Five files in `.kiro/steering/`:

- `parsers.md` (always on): parsers return structured errors instead of raising, build only what the task asks, and give every parser a never-raises property test.
- `project.md` (always on): scope discipline, byte offsets and struct formats stated in the spec before implementation, free-tier hosting, no network calls during parsing, the 20-second demonstrability rule, PowerShell shell rules, and one commit per completed task.
- `engine.md` (`necropsy/engine/**`): standard library only, never raise, bounds-check every input-derived length, explicit endianness, deterministic output.
- `tests.md` (`tests/**`): never-raises properties for every parser and entry point, fixtures built from documented byte layouts, offline and deterministic tests.
- `ui.md` (`necropsy/ui/**`): the UI calls the engine and never re-implements inference, renders engine failures as normal outcomes, and shows raw bytes beside the inferred structure.

**Hooks.**

- `.kiro/hooks/kiro-usage-log.json` is a Kiro agent hook. On `PostFileSave` and `PostFileCreate` it appends the time, file and git HEAD to `docs/KIRO-LOG.md`, which holds 203 rows from 2026-11-19 08:56Z to 13:02Z.
- The BOM guard is a git pre-commit hook, not a Kiro hook. `.githooks/pre-commit` runs `tools/check_no_bom.py`, which blocks any commit that leaves a UTF-8 byte-order mark in `.kiro/`, because a BOM before `---` breaks steering front matter.

**Agents.** There are three custom agent definitions in `.kiro/agents/`:

- `dev` implements one task, runs its tests and commits it.
- `reviewer` reads and runs tests but cannot write. It checks changes against the spec.
- `spec` writes only inside `.kiro/specs/`.

**Property-based testing.** 22 Hypothesis `@given` tests across 8 test files cover all 15 numbered properties in the engine design, among them "Never raises", "Closure soundness", "Coherence cannot change the outcome" and "Emitted layout reproduces the engine". The full suite is 263 tests.

**Division of work.** The specs, all engine, emitter and report code, and all tests in `tests/` were written in Kiro. The UI spec was also written in Kiro; the UI itself is not built yet.

Claude Code did the rest:

- repository scaffolding and git
- the steering, hook and agent files
- the BOM guard
- the early spike in `spike/`
- independent verification: `spike/verify_independent.py`, written from `requirements.md` alone, reproduces every count in the design's corpus trace (`spike/VERIFY.md`), and `spike/TEST_AUDIT.md` audits two test files for tautology

The 15 commits made with Claude Code carry a `Co-Authored-By: Claude` trailer. None of the `Task` commits does.

## Repository layout

```
.kiro/                 specs, steering, hooks and agents (Kiro)
  specs/               structure-inference-engine and necropsy-ui specs
necropsy/engine/       probes, closure gate, revision strategies, generic search, coherence
necropsy/emit/         Kiro-format spec emitter and layout block
necropsy/report/       plain-text renderer for engine results
tests/                 unit, corpus and Hypothesis property tests
tests/support/         reference reader used to check emitted specs
spike/                 corpus generator, samples and independent verification
tools/                 usage-log hook script and BOM guard
.githooks/             pre-commit hook running the BOM guard
docs/KIRO-LOG.md       log of every file the Kiro agent wrote
```

## Licence

MIT. See `LICENSE`.

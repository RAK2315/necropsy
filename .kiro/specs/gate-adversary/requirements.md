# Requirements Document

## Introduction

This spec tests whether the engine can be fooled. It has two parts. The first is a measurement of how much of the closure gate's strength comes from closure alone. The second is a pass/fail test that the engine reads a file's declared dimensions rather than recognising the file.

The first version of this spec asserted that no wrong layout closes. That assertion was wrong, and the measurement showed why: `header_size` is a free parameter in the closure arithmetic, so almost any width, height, depth and alignment has a header size that fits the file. The engine never invents a header size. It comes from a probe reading a declared field, or from Generic Search's defined axes. A generator that invents header sizes draws from a space the engine cannot reach, so its closures are not reachable defects. Decision Record 4 of the engine spec was different: those layouts were reachable.

This spec does not change the engine or the closure gate. The engine spec `structure-inference-engine` is closed. It gains one cross-reference line in its Decision Record, and no requirement changes.

## Glossary

- **Closure gate**: `check_closure(hypothesis, data)` in `necropsy/engine/closure.py`.
- **Sample**: a file in `spike/samples/`: the nine corpus files `mystery_a` to `mystery_i`, and `external_a` and `external_b` from `spike/samples/external/`.
- **Blind generator**: a function of the file size only. It receives an integer, never the bytes and never an engine result.
- **Reported candidate set**: the candidates of the engine's result for a sample: one for RESOLVED, several for UNRESOLVED_AMBIGUITY.
- **Respelled layout**: a layout that closes with the same width, height, bit depth, header size, row stride, encoding and data region as a reported candidate, but has a different `hypothesis_key` (for example row alignment 2 where the stride is unchanged, or a declared `data_end` equal to the file end).
- **Perturbation**: a copy of a sample with one declared dimension field replaced by another value.
- **Tracks**: after a perturbation, every candidate of the result has, on the perturbed axis, the new declared value, or for PCX the new value plus one (PCX bounds are inclusive).

## Requirements

### Requirement 1: Blind measurement of closure alone

**User Story:** As the builder, I want to know how many arbitrary wrong layouts the closure gate admits on its own, so that I describe the gate's strength truthfully.

#### Acceptance Criteria

1. THE blind generator SHALL take one integer argument, the file size, and SHALL return the same layouts in the same order for the same size. A non-integer, boolean or negative argument SHALL yield no layouts.
2. THE blind generator SHALL NOT yield the same layout twice.
3. THE measurement SHALL run for every Sample.
4. THE measurement SHALL exclude from the count every generated layout whose `hypothesis_key` equals the key of a reported candidate. It SHALL read the reported candidate set for nothing else.
5. THE measurement SHALL report, per Sample: layouts generated, layouts excluded, layouts tried, layouts that closed, and respelled layouts. Respelled layouts SHALL be counted apart from closed layouts and SHALL NOT be added to them.
6. THE measurement SHALL write these numbers to `tools/adversary_counts.json`, with no timestamp, so that a rerun on unchanged code produces an identical file.
7. THE measurement SHALL NOT assert that the closed count is zero. It is a measurement. A non-zero count is not a defect, for the reason in the Introduction.
8. THE generated layouts SHALL include the class of Decision Record 4: width and height both below 40, header size 128, `rle_pcx`, on the 955-byte samples.

### Requirement 2: Perturbation of declared dimensions

**User Story:** As the builder, I want to show that a probe reads the file rather than recognising it, so that the claim "the engine infers structure" is tested on inputs shaped like real files.

#### Acceptance Criteria

1. FOR EACH Sample that a probe handles, THE test SHALL perturb the declared width and the declared height, each to: original minus 2, minus 1, plus 1, plus 2, twice the original, 0 and 1, omitting the original value and any value the field cannot hold.
2. THE test SHALL change exactly one field per perturbation, at the offsets stated in design.md.
3. WHEN the perturbed file is run through the engine, THE result SHALL be FAILED or a result whose candidates all track the change.
4. THE engine SHALL NOT return any candidate whose `hypothesis_key` equals the key of a candidate of the unperturbed sample.
5. IF a perturbation returns the unperturbed answer, THEN the test SHALL fail with a message naming the sample, axis and value. The builder SHALL stop and report it. The test SHALL NOT be weakened to make it pass.
6. FOR EACH Sample the test SHALL include at least one perturbation that tracks, so that the test cannot pass by every perturbation failing.
7. THE test SHALL verify that each table offset holds the original declared value, so that the table is checked against the file.
8. THE test SHALL fail when run against an engine that ignores the perturbed byte and returns the unperturbed result.
9. A Hypothesis property test SHALL perturb a randomly chosen Sample, axis and value over `0..65535`, and assert the same claim.
10. Samples with no probe (`mystery_d`, `mystery_f`, `mystery_g`) are out of scope for this requirement. They have no declared dimension to perturb.

### Requirement 3: Documentation of the finding

**User Story:** As a reader of the repository, I want the measurement and its conclusion written down, so that nobody rediscovers it as a bug.

#### Acceptance Criteria

1. THE design document SHALL record the finding: closure alone admits about 2% of arbitrary layouts, the per-sample counts, the `mystery_b` example of a 1×1 layout with a 185-byte header, and the conclusion that the gate's strength comes from the hypothesis source.
2. THE engine spec's Decision Record SHALL gain one cross-reference line to that finding. No engine requirement SHALL change.
3. THE closure gate SHALL NOT be modified by this spec.

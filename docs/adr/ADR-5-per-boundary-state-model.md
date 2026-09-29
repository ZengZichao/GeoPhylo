# ADR-5: Model each boundary as a triple of orthogonal states, not a bare age

- **Status**: Accepted (in force since 0.1.0)
- **Date of record**: 2026-09-11
- **Code**: `geophylo/data/models.py` (`Boundary`, `Interval`),
  `geophylo/data/builtin.py` (`_boundary_from_payload`, `_check_hierarchy`),
  `tools/build_snapshot.py` (`boundary_definition`, `boundary_qualifier`),
  `tests/test_data_contract.py`

## Context

A published boundary age is not one number. In the shipped 2026/06 snapshot the
following distinct situations all occur, and each one licenses different
downstream claims:

| Boundary | Age | Definition | Margin | `qualifier` |
| --- | --- | --- | --- | --- |
| base Jurassic | 201.4 ± 0.2 Ma | GSSP | published | `constrained` |
| top Jurassic | 143.1 ± 0.6 Ma | numeric estimate | published | `constrained` |
| base Quaternary | 2.58 Ma | GSSP | none published | `defined` |
| base Anisian | 247.0 Ma | numeric estimate | none published | `unknown` |
| top Phanerozoic | 0.0 Ma | present | — | `present` |

Two different facts are being conflated if all of this becomes a float:

1. **How the boundary is defined** — by a ratified GSSP, by a GSSA, by a numeric
   estimate, by the present, or not stated at all.
2. **What the numeric value's epistemic status is** — constrained by a stated
   margin, exactly defined, explicitly approximate (`~`), present-day, or
   unknown.

Downstream, `0.0` uncertainty versus "no uncertainty published" is the kind of
difference that silently turns into a false precision statement in a figure
caption.

## Decision

Represent a boundary as a frozen dataclass carrying orthogonal states:

```python
Boundary(age_ma, qualifier, uncertainty_ma, definition, source_iri)
```

- `qualifier ∈ {defined, constrained, approximate, present, unknown}` describes
  the **nature of the number**; `definition ∈ {gssp, gssa, numeric_estimate,
  present, unknown}` describes **how the boundary is defined**. They are stored
  separately and neither is derived from the other at query time.
- `uncertainty_ma` is `float | None`; `None` means upstream published no
  quantitative error and explicitly **does not** mean zero error.
- Derived properties keep the two axes consistent: `is_defined` is true for
  GSSP/GSSA only; `is_numeric` requires a numeric-bearing qualifier *and* a
  numeric-bearing definition, and treats `qualifier="unknown"` as *not*
  numerically constrained; `effective_uncertainty` returns `None` for
  `unknown`, never `0.0`.
- Both fields are validated enums at load time; unknown strings raise
  `DataValidationError`. `qualifier="approximate"` carries the chart's `~`,
  which the extractor reads from the upstream `skos:note "uncertain"` marker of
  a boundary endpoint — including inside a blank node, where the value is matched
  against the remainder of the line (`_NOTE_RE.search(rest)`) — and
  `boundary_qualifier()` ranks it *above* the GSSP/GSSA test, so a
  GSSP-defined boundary whose published number is explicitly approximate is
  recorded as `approximate` rather than `defined`. Both shipped snapshots carry
  all 36 such endpoints. Because these values live inside `intervals`, a change
  to this semantics changes the payload bytes, hence `versions.json`, the
  sentinel counts and any figure that prints those qualifiers: it is a **data
  change** and must ship as such (see `docs/data-policy.md`, "Snapshot update
  procedure"),
  not as a drive-by edit.
- Because one shared boundary appears in two adjacent records, the loader
  requires `age_ma`, `qualifier`, `uncertainty_ma` and `definition` to agree
  field by field for every boundary age shared between records
  (`_check_hierarchy`), and the generator derives both fields deterministically
  from upstream markers instead of copying them per record
  (`boundary_definition()`, `boundary_qualifier()`).

## Rejected alternatives

- **`age_ma: float` plus `error: float = 0.0`.** Rejected: conflates "no
  published error" with "error is zero", which is a falsifiable scientific
  claim the software cannot make.
- **One combined field (`"201.4 ± 0.2"`, `"~201.4"`, `"GSSP"` as a string).**
  Rejected: unparseable-by-contract, and it makes the shared-boundary
  consistency check impossible.
- **A single "precision" enum merging definition and qualifier.** Rejected: the
  states are genuinely orthogonal — a GSSP-defined boundary may carry a
  quantitative radiometric margin, and a numeric estimate may be flagged
  approximate — and collapsing them loses exactly the information a figure
  caption needs.
- **Filling missing metadata from a neighbouring rank or from pyrolite.**
  Rejected: the alternative that would keep it honest is to say `unknown`, which
  is what the experimental pyrolite backend is required to do (ADR-1).
- **Storing `datetime`/`uncertain-float` objects.** Rejected: no stdlib type
  expresses "defined by GSSP, ± 0.2 Ma" without a new dependency, and JSON
  round-tripping is the snapshot contract.

## Consequences

- The states are queryable, not printable: the renderer draws numeric boundary
  ages only (`render/ticks.format_age()` knows nothing about `qualifier`), so a
  figure that must show `~` or `±` reads them from
  `interval.older_boundary.qualifier` / `.uncertainty_ma` itself. Keeping the
  encoder out of the strip is what keeps the track geometry contract simple.
- Every snapshot is validated twice (hash, then per-field consistency), so a
  hand-edited snapshot fails loudly with `DataValidationError`.
- Honest `unknown` propagation means some derived fields are empty; the user
  guide documents `unknown` as a normal, expected state rather than a defect.
- Upstream inconsistencies must be reconciled deterministically in the
  generator and written to the generation log (e.g. one margin appearing as both
  1.36 and 1.6 Ma at 422.7 Ma resolves to the maximum, 1.6 Ma, and is logged) —
  ambiguity is resolved in code, not in a hand-edited JSON.
- Tests pin the model with sentinel values (`Jurassic 201.4 ± 0.2 → 143.1 ± 0.6`,
  `Phanerozoic 538.8 ± 0.6 → present`, `Wuchiapingian 259.857 ± 0.084`), so a
  semantics change cannot slip through as a data refresh.

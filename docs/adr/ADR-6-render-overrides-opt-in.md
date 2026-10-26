# ADR-6: Expose figure-quality knobs as opt-in overrides, keep conservative defaults

- **Status**: Accepted (in force since the render-override release; API additive)
- **Date of record**: 2026-10-26
- **Code**: `geophylo/render/ticks.py` (`format_age_exact`),
  `geophylo/render/labels.py` (`_candidate_sequence`, `apply_label_degradation`,
  `_collides`), `geophylo/render/linear.py` (`add_geo_axis`),
  `geophylo/render/result.py` (`RENDER_PARAMS`, `validate_render_params`),
  `tests/test_labels.py`, `tests/test_ticks.py`

## Context

Publication-grade figures need four behaviours that the library deliberately did
not implement, because each of them can invent information the source data does
not carry:

| Need | Why the library refused it |
| --- | --- |
| print `251.902 Ma` as `251.902`, not `252` | `format_age()` rounds `age >= 100` to whole Ma, so snapshot precision never reaches the page |
| one code register per band (`T3 · J1 · K1`, not `T3 · J1 · Lower Cretaceous`) | abbreviation was decided interval by interval, so a band could mix codes and full names |
| a label in every band even when no alias exists (`Aalenian -> Aal`) | the abbreviation gate refuses name-prefix truncation, because a truncated name is a token a reader cannot decode |
| ≥4 pt clearance between neighbours in a band | collision was box intersection only, so two labels could sit flush and read as one invented word |

Downstream figure scripts tended to compensate for all four at the script layer,
which meant the public API could not draw publication-grade figures without
per-project patching. That is the situation this record removes.

## Decision

Add four **opt-in** parameters to `add_geo_axis()`, and leave every default
unchanged:

| Parameter | Default | Effect when set |
| --- | --- | --- |
| `tick_format` | `"default"` | `"exact"` prints the stored precision (`format_age_exact`); or pass any `age -> str` callable |
| `track_register` | `"interval"` | `"uniform"` switches a whole *band* to official codes as soon as one interval in it had to abbreviate |
| `fallback_truncation` | `None` | `n >= 2` adds name-prefix candidates of `n` characters (descending to 2) as the **last** rung before hiding |
| `min_label_gap` | `0.0` | minimum clearance (pt) along the time dimension between two labels in the same band |

Two ordering rules are part of the decision, not implementation detail:

1. **Truncation ranks after rotation.** The ladder is
   full name -> abbreviation -> abbreviated rotated -> full name rotated ->
   name prefix -> hide. Rotation keeps the name readable as written; truncation
   invents a token. Putting truncation first would silently shorten labels that a
   rotated rendering would have preserved.
2. **`track_register` groups by band, not by call.** One `add_geo_axis()` call
   draws one band per rank; "same track" means one band. Grouping by call would
   let a crowded rank drag every other rank down to codes.

Counts land on the result object as `labels_shortened_n` / `labels_rotated_n`
(over *visible* labels), so a figure caption can quote the library's own
diagnostics instead of re-deriving them from private items.

## Rejected alternatives

- **Bake the paper's policy into the defaults.** Rejected: the defaults are the
  library's scientific position — never invent a token, never hide the fact that
  a name does not fit. Making truncation or rounding silent defaults would make
  every downstream figure inherit those choices.
- **A `precision="snapshot"` flag that only switches the tick formatter.**
  Rejected as too narrow: the same "print what the snapshot stores" need shows up
  wherever an age is printed, so the knob is the formatter itself
  (`tick_format="exact"` or a callable), not a one-off mode name.
- **Letting the caller supply a label-rendering callback.** Rejected: a callback
  would push layout policy out of the library entirely and re-create the
  script-layer problem one level up. Four narrow parameters keep the geometry
  contract (thickness is hard, time stays in the band) inside the library.
- **Deleting `guard_same_track_gaps` / `hide_track_overflows` from the figure
  scripts once the library grew `min_label_gap`.** Rejected: they now verify the
  rendered result with real glyph metrics, which the analytic placement estimate
  cannot see. They report `0` in practice and act as a regression alarm.

## Consequences

- Existing callers are unaffected: all four defaults reproduce the previous
  behaviour bit for bit.
- A figure that must match a published layout can now be written against the
  public API alone, with no library workaround in the caller.
- Adding a parameter is an additive change; changing a *default* would not be,
  and would require a new record rather than an edit here.
- Tests pin each knob's semantics independently of the figures
  (`tests/test_labels.py`, `tests/test_ticks.py`), so a future default change
  cannot pass CI by accident.

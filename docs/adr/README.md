# Architecture decision records

Long-form rationale for the non-obvious choices in `geophylo`. Each record
states what was decided, which alternatives were rejected, and what the
consequences bind future contributors to. Inline `ADR-n` markers in the source
docstrings refer to the records listed here.

Written in English; they document the code as shipped, so every claim is
anchored to a file (see the `Code:` line of each record). Chinese translations
of every record live alongside as `*.zh.md`; the English text is the
authoritative version. When a decision
changes, write a new record with the next number instead of rewriting an
existing one.

| # | Decision | Recorded in | Cited from |
| --- | --- | --- | --- |
| ADR-1 | Bundle deterministic ICS snapshots as the default data source; keep `pyrolite` an experimental, opt-in, read-only backend | [ADR-1-bundled-snapshots-over-pyrolite.md](ADR-1-bundled-snapshots-over-pyrolite.md) | `docs/user-guide.zh.md` §11, `docs/user-guide.en.md` §11 |
| ADR-2 | Draw every track in an inset `Axes` created from the host; never overlay artists on the host `Axes` | [ADR-2-inset-axes-for-tracks.md](ADR-2-inset-axes-for-tracks.md) | `geophylo/render/linear.py` (module docstring) |
| ADR-3 | Return a `GeoAxisResult` result object instead of an `Axes` | [ADR-3-result-object-not-axes.md](ADR-3-result-object-not-axes.md) | `geophylo/render/linear.py` (`add_geo_axis`), `geophylo/render/result.py` (`GeoAxisResult`) |
| ADR-4 | Adapters construct and validate coordinate contracts and do not draw | [ADR-4-adapters-build-contracts.md](ADR-4-adapters-build-contracts.md) | `geophylo/adapter/biopython.py` (module docstring) |
| ADR-5 | Model a boundary as orthogonal states (`age_ma`, `qualifier`, `uncertainty_ma`, `definition`) | [ADR-5-per-boundary-state-model.md](ADR-5-per-boundary-state-model.md) | `geophylo/data/models.py` (`Boundary`) |

## Reading order

Data layer first (ADR-1, ADR-5), then the coordinate/rendering layer
(ADR-2, ADR-3), then the adapters (ADR-4): the adapter decision only makes sense
once the `CoordinateSpec` contract and the "rendering never touches the host"
contract are in place.

## Scope

These five records cover only the decisions listed above. Other deliberate
choices that are *not* recorded here, and are documented elsewhere instead:

- the exception hierarchy and the "no raw `TypeError`/`ValueError` escapes a
  public entry point" rule → `geophylo/exceptions.py` and the user guide's
  troubleshooting section;
- append-only snapshots and the sentinel-assertion release ritual →
  [`docs/data-policy.md`](../data-policy.md);
- provenance of the derived `2024/12` snapshot →
  [`geophylo/data/snapshots/PROVENANCE.md`](../../geophylo/data/snapshots/PROVENANCE.md);


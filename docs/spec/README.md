# Normative Specification Index

English | [中文](README.zh.md)

Markers of the form "规范 N.N" ("Specification N.N") that appear in source-code comments and docstrings across this repository — along with the bare section numbers that immediately follow them, such as `（4.8）` and `（5.2 硬约束）` — all point to the identically numbered entry on this page. Every normative claim must ship with the package, so that the contracts the code claims to implement can be consulted and verified directly. Each section number has exactly two homes: it is written either into the docstring of the code it constrains (directly executable, directly testable) or onto this page. **There is no developer documentation to consult outside this repository.**

Conventions:

* The "Carrier" (载体) column states where the claim currently lives: in which piece of code or which document. The wording at that location is authoritative; this page serves only as an **index plus the parts that cannot be sunk into code** (cross-module invariants, rationale for chosen values, acceptance criteria).
* The "Verifiable by" (可核验方式) column names the test or probe that proves the claim holds. Every new entry must come with a verifiable-by method; otherwise the entry is nothing but a slogan.
* A section number not covered by this page is a dangling reference; treat it as a defect and fix it.

## 1 Scope and Positioning

| Section | Normative claim (summary) | Carrier | Verifiable by |
| --- | --- | --- | --- |
| 1.3 | This library draws only the geological time axis, never the tree; the tree is drawn by the caller, and the coordinate semantics are passed in via `CoordinateSpec` or `RadialSpec` | `geophylo/__init__.py`; sections 1–2 of `docs/user-guide.*.md` | `examples/circular_tree.py` (tree drawn by the recipe itself + `add_geo_ring`); `tests/test_polar.py::TestCircularTreeRecipe` |
| 1.4 | Stability matrix: stable API = `Timescale`, `Interval`, `Boundary`, `CoordinateSpec`, `spec_from_biophylo`, `add_geo_axis`, `GeoAxisResult`, `TimescaleBackend`, and `GeophyloError`; experimental symbols = `add_geo_ring`, `RadialSpec`, `radial_spec_from_biophylo`, and `spec_from_iplotx` (the API is not frozen) | `geophylo/__init__.py` docstring; feature overview in `README.md` | `tests/test_packaging.py` (top-level export surface); the `experimental` marker in `pyproject.toml` |
| 1.5 | Acceptance criterion: on the baseline figure (12×8 inches, `label_size=6`, `ranks=["Period","Epoch"]`), hidden interval-name labels ≤ 20% | section 6 of `docs/user-guide.*.md` | `tests/test_add_geo_axis.py::TestLayoutInvariants::test_label_visibility_baseline` |

## 2 Data Backends

| Section | Normative claim (summary) | Carrier | Verifiable by |
| --- | --- | --- | --- |
| 2.2 | Three rules for the pyrolite backend: strict rank filtering with no fallback; missing metadata is labeled `unknown` (colors use a neutral placeholder plus a warning, never fabricated); the version lower bound is `MIN_PYROLITE_VERSION` | module docstring of `geophylo/data/pyrolite_backend.py` and the docstrings of `_true_rank` and `_row_age` | `tests/test_pyrolite_backend.py` (requires pyrolite; skipped when absent), `tests/test_timescale_query.py::TestPyroliteRankHeuristic` (scope of the heuristic) |
| 2.3 | The four query channels of the backend protocol `TimescaleBackend`; field semantics of `Interval`, `Boundary`, and `BackendMetadata` (including `uncertainty_ma=None` ≠ zero uncertainty) | `geophylo/data/backend.py`, `geophylo/data/models.py` | `tests/test_models.py`, `tests/test_data_contract.py` |

## 3 Input Constraints

| Section | Normative claim (summary) | Carrier | Verifiable by |
| --- | --- | --- | --- |
| 3.2 | The public parameter-validation helpers are the single entry point for type and value-domain checks: raw third-party exceptions must not bubble up as part of the public contract | module docstrings of `geophylo/validation.py` and `geophylo/exceptions.py` | `tests/test_exceptions.py`, `tests/test_add_geo_axis.py::TestInputValidation` |

## 4 Public API Contracts

| Section | Normative claim (summary) | Carrier | Verifiable by |
| --- | --- | --- | --- |
| 4.1 | `Timescale` is the unified query facade; `age_range` (the legal domain) is kept separate from `min_age` and `max_age` (the drawing window); window semantics are "intersect, then clip" | `geophylo/timescale.py`, `geophylo/render/linear.py::_window_intervals` | `tests/test_timescale_query.py`, `tests/test_add_geo_axis.py::test_ediacaran_partial_overlap_drawn_clipped` |
| 4.2 | Four rules for age resolution: ① structural nodes do not participate in matching; ② a boundary value is attributed to the younger interval that has it as its `older_ma` (left-closed, right-open); ③ `0.0` resolves to the youngest (present) interval; ④ when several ranks match at once, the most specific wins (Age>Epoch>Period>Era>Eon), with snap tolerance 1e-9 | `geophylo/data/_query.py` (docstrings of `core_rank_pool`, `resolve_age`, `present_youngest`, `age_hit`) | `tests/test_timescale_query.py`, `tests/test_adapter_biopython.py::TestDegenerateTree` (cross-backend consistency is pinned by the `_query` unit tests) |
| 4.3 | Name lookup follows three channels `name → aliases → label`; within a channel exact matches take priority, and substring fallback happens only when no exact hit exists; with 0 hits or ≥2 hits, `IntervalNotFoundError` and `AmbiguousIntervalError` are raised respectively | `geophylo/data/_query.py::search_by_name` | `tests/test_timescale_query.py::TestQueries` |
| 4.4 | Input constraints and rejection behavior of `add_geo_axis()` and `add_geo_ring()`; `update()` shares the same value-domain validation as the creation path | `geophylo/render/linear.py::add_geo_axis`, `geophylo/render/result.py::validate_render_params` | `tests/test_add_geo_axis.py::TestInputValidation`, `tests/test_lifecycle.py::TestUpdateValidation` |
| 4.5 | Lifecycle: `update()` commits only after full validation (a failure leaves state untouched); the two-layer semantics of `sync()`; `finalize()` freezes the exact layout; `remove()` restores automatically only when the host view was not modified by the user in the meantime | per-method docstrings in `geophylo/render/result.py` | `tests/test_lifecycle.py`, `tests/test_add_geo_axis.py` |
| 4.6 | Tick contract: golden samples for `format_age` (`0.0→"0.00"`, `1.0→"1"`, `66.0→"66"`, `538.8→"539"`); `dedupe_ages` tolerance 1e-9; the 20% threshold of `fill_ages_style`; the three-level priority of `cap_ticks` and its "starting from the oldest end" direction; pixel-spacing filtering at `2 × label_size`; the `boundaries` style is exempt from `tick_max_count` while `tick_style="ages"` is subject to it, with the number dropped recorded in `GeoAxisResult.ticks_dropped` | `geophylo/render/ticks.py`, `geophylo/render/linear.py::_draw_ticks`, `geophylo/render/result.py::GeoAxisResult.ticks_dropped` | `tests/test_ticks.py`, `tests/test_add_geo_axis.py::TestTicksRendered` |
| 4.7 | Exception hierarchy: all public exceptions inherit from `GeophyloError`; `AmbiguousIntervalError` is also a subclass of `IntervalNotFoundError` (solely so that caller code that catches only "not found" keeps working); for catch order see the exception table in the user guide | `geophylo/exceptions.py`; section 12 of `docs/user-guide.*.md` | `tests/test_exceptions.py` |
| 4.8 | Five hard constraints of the polar path: single rank; native `PolarAxes` only; ring-segment radius = `spec.age_to_radius(age, radius_range=band_radius(band))` (**`band` participates in the geometry**); a `band` outside the current `rlim` raises `InvalidRadiusError`; `set_rlim` and `set_rorigin` are never called | module docstring of `geophylo/render/polar.py` plus `add_geo_ring`, `_validate_band`, `rebuild` | `tests/test_polar.py::TestBandGeometryDrivesRingRadii`, `TestNoRadialViewModification` |
| 4.9 | Consistency contract: the ring and the tree share one and the same `RadialSpec`; `age_to_radius` is a strictly monotonically decreasing affine map from `age_range → radius_range`, and clamping to the value range still goes through that same map (no second formula is introduced); `radius_to_age` is exactly invertible on the same range | module docstring of `geophylo/coordinate/radial.py` plus `age_to_radius`, `radius_to_age`, `band_radius` | `tests/test_radial_spec.py::TestRadiusMapping`, `tests/test_polar.py::TestBandGeometryDrivesRingRadii` |
| 4.10 | Adapters enforce a root branch length of `None` or `0`; a nonzero root branch length is explicitly rejected with two fix paths spelled out; degenerate trees (single leaf, or all-zero branch lengths) report their cause explicitly | `geophylo/adapter/biopython.py::_scan_tree`, `_require_positive_span` | `tests/test_adapter_biopython.py::TestDegenerateTree`, `tests/test_polar.py::test_zero_root_offset_required` |
| 4.11 | Render parameter value domains: `thickness_ratio ∈ (0, 0.5]`, `alpha ∈ [0,1]`, `label_size > 0`, `tick_max_count ≥ 1`, and `skip` must be a sequence of strings | `geophylo/validation.py`, `geophylo/render/result.py::validate_render_params` | `tests/test_lifecycle.py::TestUpdateValidation` |

## 5 Rendering Layer

| Section | Normative claim (summary) | Carrier | Verifiable by |
| --- | --- | --- | --- |
| 5.1 | Tracks are hosted in inset Axes (ADR-2): bounds are fractions of the host Axes; the time-axis limits numerically **copy** the host limits but without sharex; borders are drawn as separate `Line2D` objects following the near/far semantics | `geophylo/render/linear.py::_make_track_axes`, `_align_track_to_host`, `_draw_borders` | `tests/test_add_geo_axis.py::TestSideEffects`, `TestTrackGeometry` |
| 5.2 | Two invariants of thickness allocation (a feasibility precheck runs before allocation, and the total is conserved); label degradation order ① abbreviation ② rotation ③ hiding, with no steps skipped; **the two geometric hard constraints are evaluated against candidate rotation angles**, and labels are clamped into the track rectangle along the time axis; figure abbreviations accept only a single-segment short code, and a compound `ccgmShortCode` falls back to the full name | `geophylo/render/linear.py::compute_track_layout`, `geophylo/render/labels.py::apply_label_degradation`, `is_figure_abbreviation` | `tests/test_add_geo_axis.py::TestLayoutInvariants`, `tests/test_labels.py` (`TestAbbreviationGate`, `TestDegradation::test_rotated_candidate_*`, `test_edge_label_*`) |
| 5.3 | Polar labels are placed deterministically at the midpoint of `theta_range` and do not take part in the degradation pipeline; with `rotate_labels=True` the angle = `degrees(theta_center) + rotation` | `geophylo/render/polar.py::relayout`, `rebuild` | `tests/test_polar.py::TestRotateLabelsRadialAlignment` |
| 5.4 | Automatic contrasting color: alpha compositing first, then sRGB linearization and WCAG relative luminance decide black or white, with ties going to black; examples follow the fixed order `add_geo_axis → tight_layout → finalize → savefig` | `geophylo/render/labels.py::auto_label_color`, `examples/*.py` | `tests/test_labels.py::TestAutoLabelColor`, `tests/test_packaging.py` (example execution) |
| 5.6 | Per-boundary status model: `qualifier` (a numerical property) and `definition` (how the boundary is defined) are orthogonal; `unknown` always carries `uncertainty_ma=None` | `geophylo/data/models.py` (`Boundary` docstring), `docs/adr/ADR-5-*.md` | `tests/test_models.py`, `tests/test_data_contract.py` |
| 5.7 | Snapshot generation and hashing: `payload_sha256` covers the `intervals` array (metadata is not protected, see `PROVENANCE.md`); verification happens at load time | `geophylo/data/builtin.py` (`canonical_payload_bytes`, `load_snapshot`, `SnapshotBackend`), `docs/data-policy.md` | `tests/test_data_contract.py`, `tests/test_snapshot_provenance.py` |

## 6 Adapters and Recipes

| Section | Normative claim (summary) | Carrier | Verifiable by |
| --- | --- | --- | --- |
| 6.1 | Coordinate-alignment rationale: in Bio.Phylo the x coordinate is cumulative branch length from the root, so the adapter always produces `mode="root_distance"`; `age_range` comes from the data domain rather than the view limits; not checking ultrametricity or leaf ages is a deliberate design choice | module docstring of `geophylo/adapter/biopython.py` and the `spec_from_biophylo` docstring | `tests/test_adapter_biopython.py`, `tests/test_coordinate_spec.py` |
| 6.2 | The iplotx adapter: reads the layout data domain from `get_layout()`, and `age_conversion` is applied to root distances; radial layouts are explicitly rejected | module docstring of `geophylo/adapter/iplotx.py` | `tests/test_adapter_iplotx_contract.py`, `tests/test_adapter_iplotx.py` (skipped when `ete4` or `iplotx` is absent) |
| 6.3 | The circular-tree recipe (about 30 lines): the angular domain is divided evenly among leaves, internal nodes take the mean of their children's angles, and radii are always looked up in the same `RadialSpec` | `examples/circular_tree.py`; section 9.3 of `docs/user-guide.*.md` | `tests/test_polar.py::TestCircularTreeRecipe` |

## 7 Data and Documentation Consistency

| Section | Normative claim (summary) | Carrier | Verifiable by |
| --- | --- | --- | --- |
| 7.1 | The parameter table matches the code item by item (parameter names, defaults, rank weights, the 6 px floor, and the `label_size × 2` pixel-spacing rule) | section 6 of `docs/user-guide.*.md` ↔ `geophylo/render/linear.py` | `tests/test_docs_values.py` |
| 7.2 | Tolerance values: shared-boundary consistency and parent-child containment use 1e-9 (`geophylo/data/builtin.py::_TOL`); boundary snapping and window edge-flush use the same value (`_query.SNAP_TOL`). Rationale: upstream ages carry at most 4 decimal places (the base of the Holocene is 0.0117 Ma, for example); 1e-9 is far smaller than any meaningful geological time difference yet still absorbs floating-point noise from JSON round-trips | `geophylo/data/builtin.py` (the `_TOL` comment), `geophylo/data/_query.py` (`SNAP_TOL`) | `tests/test_data_contract.py`, `tests/test_timescale_query.py` |
| 7.4 | Zero-mutation promise on host view state: `add_geo_axis()` never touches limits, scale, autoscale, or `dataLim`; `remove()` never rewrites the view the user set in the meantime | `geophylo/render/result.py::remove`, `AxesState.matches`, `README.md`, section 7 of `docs/user-guide.*.md` | `tests/test_add_geo_axis.py::TestSideEffects`, `tests/test_lifecycle.py::TestRemoveDoesNotStompUserView` |
| 7.7 | Numeric discipline in documentation: every `<number> Ma` in user-facing documentation must come from the built-in snapshot boundary set; example scripts must not hand-write snapshot boundary values | `docs/user-guide.*.md`, `README.md`, `examples/*.py` | `tests/test_docs_values.py` |
| 7.8 | Capability-declaration tests and the non-blocking convention: capability tests for experimental backends do not block the release gate | module docstring of `geophylo/data/pyrolite_backend.py`, `pyproject.toml` markers | `tests/test_pyrolite_backend.py` |
| 7.9 | Repository documentation structure conventions: every ADR documents its rejected alternatives; `RELEASE.md` is a numbered two-step manual procedure; the boundary value domains declared in the types of `models.py` and validated by the loader share one source of truth | `docs/adr/ADR-1…5`, `RELEASE.md`, `geophylo/data/models.py` ↔ `geophylo/data/builtin.py` | `tests/test_docs_values.py` (`test_every_adr_documents_its_rejected_alternatives`, `test_release_notes_describe_a_two_step_procedure`, `test_boundary_value_domains_match_between_models_and_loader`, and one planted counterexample) |

## 8 Provenance and Reproducibility

| Section | Normative claim (summary) | Carrier | Verifiable by |
| --- | --- | --- | --- |
| 8.2 | The backend capability matrix (presence/absence of stable IDs, uncertainty, GSSP status, and colors) must be declared explicitly, with "unknown" distinguishable from "absent" | `geophylo/data/models.py::BackendMetadata` plus the `metadata` of both backends | `tests/test_pyrolite_backend.py`, `tests/test_data_contract.py` |
| 8.4 | Snapshot provenance (including the `derived_from` of the derived 2024/12 snapshot, the generation log, and field-by-field diffs) ships with the package and is cross-checked against the data bytes | `geophylo/data/snapshots/PROVENANCE.md`, `docs/data-policy.md`, `tools/build_snapshot.py` | `tests/test_snapshot_provenance.py` |

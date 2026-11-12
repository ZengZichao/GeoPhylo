# Changelog

English | [中文](CHANGELOG.zh-CN.md)

All notable changes to this project are documented in this file. Data changes
are listed separately from code changes (scientific data changes trigger at
least a minor release; transcription fixes are listed even when patch-level).

## [0.2.1] - 2026-10-27

Diagnostics and documentation fix release. The public API, the default
rendering behaviour, the bundled data and the three digital artefacts are all
unchanged from 0.2.0 (re-running figure 3 reproduces the delivered PNG/PDF
SHA-256 hashes byte for byte).

### Added
- Public exceptions gained a stable machine code `code`: class-level
  declarations `data.validation`, `rank.invalid`, `interval.not_found`,
  `interval.ambiguous`, `range.invalid`, `radius.invalid`, `axes.type`,
  `coordinate.spec`, which a call site that needs a finer distinction may
  narrow per instance with `code=`. Callers and tests should branch on it
  rather than on message wording or on `GEOPHYLO_LANG`. Section 12 of the
  manual gained a "Stable machine codes" paragraph, and
  `tests/test_exceptions.py` gained contract cases for code shape, uniqueness
  and per-instance narrowing.

### Fixed
- Duplicate FAQ numbering in the user manual: the three new entries
  (multi-rank geological time rings, ETE4/toytree, iplotx radial) collided
  with the former Q11–Q14 and are now unified as Q1–Q17; the Chinese manual
  was brought up to the same three entries, so both manuals carry an equal
  number of items.
- Replaced the stale promise in the manual that the radial adapter was
  "scheduled for v0.2" with "a later 0.x release".
- Added a "Stability and roadmap" section to README, making explicit that 0.2
  does not cover a stabilisation scope for the experimental symbols.

## [0.2.0] - 2026-10-26

### Added
- `add_geo_axis(tick_format=...)`: `"default"` keeps the previous rounding
  rule, `"exact"` prints each value at the precision the snapshot stores
  (`251.902` is no longer printed as `252`); any `age -> str` callable may
  also be passed.
- `add_geo_axis(track_register=...)`: `"uniform"` switches a whole track to
  the official short codes as soon as any interval in it has to be
  abbreviated, removing the mixed "code + full name" register.
- `add_geo_axis(fallback_truncation=...)`: an optional name-prefix fallback
  (take n characters first, decreasing to 2 when needed) that ranks after
  rotation and before hiding, so crowded intervals with no official alias are
  no longer left with hiding as their only option. All three are off by
  default and existing calls behave unchanged.
- `add_geo_axis(min_label_gap=...)`: the minimum clearance along the time
  dimension between adjacent labels in the same track (default 0, i.e.
  intersection only); the clearance is enforced during placement, so a label
  that cannot keep it steps down the degradation ladder instead of being
  drawn and then discarded.
- `GeoAxisResult` gained `labels_shortened_n` / `labels_rotated_n` (**visible**
  label counts), which a figure caption can quote directly;
  `labels_shortened` / `labels_rotated` remain the "did it ever happen" flags.
- Added `docs/adr/ADR-6-render-overrides-opt-in.md` (English and Chinese),
  recording the trade-offs of the four opt-in overrides and the rejected
  alternatives; the ADR-count guard and the numbered references to it were
  updated in step.
- Downstream figure scripts no longer need to carry patches: the
  `relabel_boundaries` (tick-precision override), `uniform_track_register`
  (whole-track register) and `prefix_fallback` (name-prefix fallback)
  workarounds were removed in favour of `tick_format="exact"` /
  `track_register="uniform"` / `fallback_truncation=3`. Equivalent re-runs
  produce byte-identical artefacts.
- Added `examples/figures/fig2.py`, `fig3.py`, `fig4.py`, `figb3.py`:
  pure-ASCII entry points for reproducing the paper's data figures from
  environments that cannot type Chinese paths (output is still named after
  the archiving scripts' stems; re-runs are byte-identical).

### Changed
- Exception and warning messages are English by default, with
  `GEOPHYLO_LANG=zh` switching them back to Chinese (`geophylo._i18n.msg`;
  both texts are written side by side at each call site, not machine
  translated). Migrated 203 `raise`/`warnings.warn` sites, covering every
  call site in `validation`, `coordinate`, `render`, `adapter` and `data`.
- README/README.zh-CN: corrected the PyPI availability statement
  (`geophylo 0.1.1` was published on 2026-10-18) and pointed the badge at the
  version on the index page.
- Archival metadata: added the second author to `creators` in `CITATION.cff`
  and `.zenodo.json`.

## [0.1.1] - 2026-10-02

Maintenance release; no changes to the public API or bundled data.

### Changed
- Maintenance automation: Dependabot (with a hold on major GitHub Actions
  bumps), pre-commit hooks, and community health files (SECURITY, Code of
  Conduct, issue/PR templates, FUNDING).

### Fixed
- CI: min-deps visual gate, sdist install check, and CodeQL quality alerts;
  the iplotx contract tests use a single `geophylo` import form.
- Release workflow now builds sdist + wheel on tag push and attaches them to
  the GitHub Release.

## [0.1.0] - 2026-09-30

Initial release.

### Added — stable public API
- `Timescale`, `Interval`, `Boundary`: reproducible access to bundled ICS
  snapshots across the five core geochronologic ranks, with per-boundary
  qualifier/uncertainty/definition states.
- `CoordinateSpec` with `absolute_age` and `root_distance` modes;
  `age_to_data()` pure mapping; explicitly-acknowledged-only range inference
  via `from_data_limits()`.
- `add_geo_axis()` + `GeoAxisResult`: inset-axes linear geological timescale
  with multi-rank tracks, numeric tick contract, label degradation, auto
  contrast colors, host-axes state preservation, and a keyed idempotent
  registry (`update/sync/finalize/remove/restore`).
- `spec_from_biophylo()`: Bio.Phylo adapter that validates branch lengths and
  always produces `root_distance` semantics.
- `TimescaleBackend` protocol; bundled snapshot backend with load-time schema,
  hierarchy, overlap, shared-boundary and hash validation.
- Exception hierarchy rooted at `GeophyloError`.

### Added — experimental
- `pyrolite_backend` (read-only, version-locked `pyrolite>=0.3.7`; import from
  `geophylo.data.pyrolite_backend`).
- Experimental symbols, API not frozen:
  `RadialSpec`, `radial_spec_from_biophylo()`, `add_geo_ring()` (single rank,
  native polar axes), `spec_from_iplotx()`.

### Data
- Bundled baseline snapshot `2026/06` (ICS chart v2026-06.5, pinned commit) and
  derived snapshot `2024/12` (reverted via upstream changeNotes, with the
  documented Wuchiapingian uncertainty restoration); see docs/data-policy.md.

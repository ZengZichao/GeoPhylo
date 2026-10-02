# Changelog

All notable changes to this project are documented in this file. Data changes
are listed separately from code changes (scientific data changes trigger at
least a minor release; transcription fixes are listed even when patch-level).

中文版：[CHANGELOG.zh-CN.md](CHANGELOG.zh-CN.md)

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

### Added — 实验性 / experimental
- `pyrolite_backend` (read-only, version-locked `pyrolite>=0.3.7`; import from
  `geophylo.data.pyrolite_backend`).
- Experimental symbols, API not frozen:
  `RadialSpec`, `radial_spec_from_biophylo()`, `add_geo_ring()` (single rank,
  native polar axes), `spec_from_iplotx()`.

### Data
- Bundled baseline snapshot `2026/06` (ICS chart v2026-06.5, pinned commit) and
  derived snapshot `2024/12` (reverted via upstream changeNotes, with the
  documented Wuchiapingian uncertainty restoration); see docs/data-policy.md.

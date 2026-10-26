# Changelog

All notable changes to this project are documented in this file. Data changes
are listed separately from code changes (scientific data changes trigger at
least a minor release; transcription fixes are listed even when patch-level).

中文版：[CHANGELOG.zh-CN.md](CHANGELOG.zh-CN.md)

## [0.2.0] - 2026-10-26

### Added
- `add_geo_axis(tick_format=...)`：`"default"` 保持原有取整规则，`"exact"` 按快照
  存储精度打印（`251.902` 不再印成 `252`），也可传入 `age -> str` 可调用对象。
- `add_geo_axis(track_register=...)`：`"uniform"` 使一条轨道在任一处被迫缩写时
  整轨改用官方代号，消除"代号 + 全名"混排。
- `add_geo_axis(fallback_truncation=...)`：可选的名称前缀回退（先取 n 个字符，
  必要时递减到 2 个），排在旋转之后、隐藏之前，让没有官方别名的拥挤区间不再只能
  隐藏。三者默认关闭，既有调用行为不变。
- `add_geo_axis(min_label_gap=...)`：同轨相邻标签沿时间维的最小净距（默认 0，只判
  相交）；净距在放置阶段执行，放不开的标签沿降级阶梯退让，而不是先画上再丢弃。
- `GeoAxisResult` 新增 `labels_shortened_n` / `labels_rotated_n`（**可见**标签计数），
  图注可直接引用；`labels_shortened`/`labels_rotated` 仍是"是否发生过"的布尔位。
- 新增 `docs/adr/ADR-6-render-overrides-opt-in.md`（中英），记录四个显式开启项的取舍
  与被否方案；ADR 份数守卫与各处编号引用同步更新。
- 下游作图脚本不再需要携带补丁：`relabel_boundaries`（刻度精度覆写）、
  `uniform_track_register`（整轨统一）、`prefix_fallback`（前缀回退）三处已删除，
  改用 `tick_format="exact"` / `track_register="uniform"` / `fallback_truncation=3`。
  等价重跑的产物逐字节一致。
- `examples/figures/fig2.py`、`fig3.py`、`fig4.py`、`figb3.py`：纯 ASCII 入口，供无法
  键入中文路径的环境复现论文数据图（输出仍按归档脚本的 stem 命名，重跑字节一致）。

### Changed
- 异常与警告消息默认改为英文，`GEOPHYLO_LANG=zh` 切回中文（`geophylo._i18n.msg`，
  双语在每个调用点并排书写，非机器翻译）。共迁移 203 处 `raise`/`warnings.warn`，
  覆盖 `validation`、`coordinate`、`render`、`adapter`、`data` 全部调用点。
- README/README.zh-CN：PyPI 可用性表述更正（`geophylo 0.1.1` 已于 2026-10-18 发布），
  徽章改为指向索引页版本。
- 归档元数据：`CITATION.cff` 与 `.zenodo.json` 的 `creators` 补第二位作者。

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

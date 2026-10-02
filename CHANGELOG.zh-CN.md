# 更新日志

[English](CHANGELOG.md) | 中文

本文件记录本项目的全部重要变更。数据变更与代码变更分开列出（科学数据变更至少
触发一次次版本号发布；即使只是订正级补丁，转录修正也会列出）。

## [0.1.1] - 2026-10-02

维护性发布；公共 API 与随包数据无变化。

### 变更
- 维护自动化：Dependabot（屏蔽 GitHub Actions 的 major 升级）、pre-commit
  钩子，以及社区健康文件（SECURITY、行为准则、issue/PR 模板、FUNDING）。

### 修复
- CI：min-deps 可视化门槛、sdist 安装检查与 CodeQL 质量告警；iplotx 契约
  测试统一为单一 `geophylo` 导入形式。
- 发布工作流现在在 tag 推送时构建 sdist + wheel 并挂到 GitHub Release。

## [0.1.0] - 2026-09-30

首次发布。

### 新增 — 稳定公共 API
- `Timescale`、`Interval`、`Boundary`：跨五个核心地质年代等级可复现地访问
  随包 ICS 快照，逐边界保留限定符/误差/定义状态。
- `CoordinateSpec`（`absolute_age` 与 `root_distance` 两种模式）；纯映射
  `age_to_data()`；只经 `from_data_limits()` 显式确认的推断式范围获取。
- `add_geo_axis()` + `GeoAxisResult`：内嵌轨道式线性地质时间轴，支持多等级
  轨道、数值刻度契约、标签自动降级、自动对比色、宿主 Axes 状态保持，以及
  带键的幂等注册表（`update/sync/finalize/remove/restore`）。
- `spec_from_biophylo()`：Bio.Phylo 适配器，校验分支长度并始终产生
  `root_distance` 语义。
- `TimescaleBackend` 协议；随包快照后端在加载时执行 schema、层级、重叠、
  共享边界与哈希校验。
- 以 `GeophyloError` 为根的异常体系。

### 新增 — 实验性
- `pyrolite_backend`（只读，版本锁定 `pyrolite>=0.3.7`；从
  `geophylo.data.pyrolite_backend` 导入）。
- 实验性符号（API 不冻结）：`RadialSpec`、`radial_spec_from_biophylo()`、
  `add_geo_ring()`（单等级、原生极坐标 Axes）、`spec_from_iplotx()`。

### 数据
- 随包基线快照 `2026/06`（ICS 图表 v2026-06.5，pinned commit）与推导快照
  `2024/12`（经上游 changeNotes 回推，含已记录的 Wuchiapingian 不确定度
  恢复）；见 docs/data-policy.md。

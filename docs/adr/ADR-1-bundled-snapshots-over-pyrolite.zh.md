# ADR-1：随包分发 ICS 快照作为默认数据源，而不是使用 pyrolite

[English](ADR-1-bundled-snapshots-over-pyrolite.md) | 中文

- **状态**：已接受（自 0.1.0 起生效）
- **记录日期**：2026-09-11
- **代码**：`geophylo/data/builtin.py`、`geophylo/data/backend.py`、
  `geophylo/data/pyrolite_backend.py`、`tools/build_snapshot.py`、
  `docs/data-policy.md`、`geophylo/data/snapshots/PROVENANCE.md`

## 背景

`geophylo` 画的是 ICS《国际年代地层表》。它画出的每个数字都是一条科学主张，
公开发表的图件必须多年之后仍可复现。这要求数据源 (a) 版本钉定、(b) 加载时
可校验、(c) 可离线使用、(d) 获得了再分发许可。`pyrolite` 已经自带一个
`Timescale` 辅助类，是该生态位里显然的既有实现，因此是最主要的竞争选项。

`TimescaleBackend` 协议（`geophylo/data/backend.py`）让这一选择可替换：核心库
只依赖这个最小只读接口，数据出处因此是实现细节而非 API 承诺。

## 决策

把 ICS 图表的确定性快照作为包数据随包分发，并将其设为默认且推荐的数据源。

- 快照由 `tools/build_snapshot.py` 从钉定的上游 release（tag `v2026-06.5`、
  commit `44d1043e…` 的 `chart.ttl`）生成，其副本归档在 `tools/source/` 下。
  相同输入，逐字节相同的输出。
- 每份快照自描述：`chart_version`、`source` 块、`license` 块，以及
  `hash.payload_sha256` —— 仅对 `intervals` 数组的规范化 JSON（键排序、紧凑
  分隔符、UTF-8）取 SHA-256。
- 加载时校验：schema、严格的年龄排序、层级包含、同 rank 重叠、共享边界一致性、
  颜色格式，以及对照 `versions.json` 的 payload 哈希。任何违例抛出
  `DataValidationError`。
- 快照目录只增不改；`versions.json` 是唯一索引，历史图表版式经
  `Timescale(version="2024/12")` 选用。
- `pyrolite` 仍可作为**实验性、显式安装、只读**后端使用（`geophylo[pyrolite]`，
  版本锁定 `>=0.3.7`）。它把所有无法核验的能力标为 `unknown` 而不编造元数据；
  其 `get_interval()` 恒抛 `IntervalNotFoundError`，因为 pyrolite 的数据表没有
  稳定标识符。

## 被否决的替代方案

- **把 `pyrolite` 作为必需的运行时数据源。** 否决：那会让每个画出的数字都依赖
  第三方的数据发布节奏与转录质量；它没有稳定 ID、没有父链接、没有 GSSP/GSSA
  定义、没有误差字段，而这些恰恰是本库要逐边界暴露的状态。它按名称回退的查询
  语义也与坐标层所需的严格 rank 行为不一致。
- **在导入/渲染时从 stratigraphy.org 抓取 `chart.ttl`（或图表 PDF）。** 否决：
  渲染时联网既不可复现、也不能离线使用、也无法引用到固定版本；本库完全不发起
  任何自动网络访问。
- **把 pyrolite 自带的数据表再出口为"我们的"快照。** 否决：那是二手出处——
  上游归因与钉定 commit 都会是 pyrolite 的而非我们的，而且我们无法核验或哈希
  这次提取。
- **只随包最新快照，文档写"旧图表请用更新版本"。** 否决：这会破坏跨图表版式的
  图件复现，而那正是 `versions.json` 与只增不改规则存在的理由。

## 后果

- 仓库再分发 CC-BY-4.0 数据，因此归因文件（`NOTICE`、`LICENSES/CC-BY-4.0.txt`、
  各快照的 `license` 块）是 sdist 与 wheel 的强制组成部分，并由
  `tests/packaging/check_wheel.py` 校验。
- 图表更新成为一次发布事件：重新生成、跑数据契约与视觉测试、刷新
  `tests/test_data_contract.py` 的哨兵计数、产出机器可读 diff，并把变更记入
  `CHANGELOG.md`。科学数据变化至少触发一次次版本号发布。
- 快照体积随每次追加版式增长（每个版式约 160 KB：v0.1.0 随包的两个版式分别为
  164,843 与 168,544 字节）。
- 推导版 `2024/12` 是重建而非上游归档版式；该局限在
  `geophylo/data/snapshots/PROVENANCE.md`、`versions.json`（`derived_from`）与
  `docs/data-policy.md` 中披露。
- 真正想用 pyrolite 数据的用户有一条真实而诚实的路径：实验性后端，把缺失的
  能力如实声明为 `unknown`。

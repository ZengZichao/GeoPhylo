# GeoPhylo

[English](README.md) | 中文

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.23060662.svg)](https://doi.org/10.5281/zenodo.23060662)
[![CI](https://github.com/ZengZichao/GeoPhylo/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/ZengZichao/GeoPhylo/actions/workflows/ci.yml)
[![CodeQL](https://github.com/ZengZichao/GeoPhylo/actions/workflows/codeql.yml/badge.svg?branch=main)](https://github.com/ZengZichao/GeoPhylo/actions/workflows/codeql.yml)
[![PyPI](https://img.shields.io/pypi/v/geophylo.svg)](https://pypi.org/project/geophylo/)

面向 Matplotlib Axes 的地质时间轴可视化库。它把 ICS（International Commission on
Stratigraphy，国际地层委员会）发布的《国际年代地层表》（International
Chronostratigraphic Chart）作为可复现的内置快照，叠加到时间校准树上，也叠加到
任何以 Ma（百万年）为横轴或纵轴的图上。

R 语言生态中的 `deeptime` 为 ggplot2、ggtree 提供了 `coord_geo()`；`geophylo`
为 Matplotlib 生态提供等价能力。本库把**坐标语义的正确性与可复现性**放在第一位：
遇到无法确定坐标语义的场景，本库会显式报错，不会静默猜测。

## 功能总览

- **可复现的 ICS 数据访问**：`Timescale` 读取随包分发的版本化快照，覆盖五个核心
  地质年代等级（geochronologic rank）：Eon、Era、Period、Epoch 和 Age。快照逐边界
  保留 `~` 近似值、定量误差（`±`），以及 GSSP（Global Boundary Stratotype Section
  and Point，全球界线层型剖面和点位）、GSSA（Global Standard Stratigraphic Age，
  全球标准地层年龄）定义状态。`Timescale(version="2024/12")` 可选用历史快照。
- **线性地质时间轴**：`add_geo_axis()` 在宿主 Axes 内部，用内嵌轨道（inset）叠加
  地质时间条带，支持多等级轨道、数值刻度、标签自动降级与自动对比色，并保证宿主
  Axes 的视图状态保持原样。
- **显式坐标契约**：`CoordinateSpec`（`absolute_age`、`root_distance` 两种
  模式）是坐标语义的唯一真值来源；`spec_from_biophylo()` 从 Bio.Phylo 树构造
  并校验契约。
- **环形布局（实验性）**：`RadialSpec` + `add_geo_ring()` 在原生极坐标 Axes 上
  叠加地质时间环；`radial_spec_from_biophylo()` 提供环形适配入口。这部分 API 是
  实验性的，签名不冻结。
- **强契约异常体系**：全部公共异常继承 `GeophyloError`。`AmbiguousIntervalError`
  是 `IntervalNotFoundError` 的子类，该继承关系为兼容既有 `except` 而保留。因此
  代码要先写 `except AmbiguousIntervalError`，再写
  `except IntervalNotFoundError`。详见用户手册“异常与捕获顺序”一节。

## 使用文档

- [中文使用文档](docs/user-guide.zh.md)（完整教程、参数详解、FAQ 和排错指南）
- [English user guide](docs/user-guide.en.md)（full tutorial, parameter
  reference, FAQ and troubleshooting）
- [数据政策](docs/data-policy.zh.md)（ICS 快照的来源、许可、更新和回退；
  英文权威版见 [data-policy.md](docs/data-policy.md)）
- [架构决策记录](docs/adr/README.zh.md)（ADR-1～ADR-5：非显然的选择和已否决的
  替代方案；英文权威版见 [adr/README.md](docs/adr/README.md)）

## 安装

> PyPI 发布尚未完成：下面带包名的 `pip install` 命令在发布前会解析失败。
> 发布前请从源码树安装：`pip install .`；完整测试环境用 `pip install -e ".[test]"`。

```bash
pip install geophylo            # 核心（仅需 matplotlib + numpy）
pip install "geophylo[biopython]"   # Bio.Phylo 适配
pip install "geophylo[iplotx]"      # iplotx 适配（实验性）
pip install "geophylo[pyrolite]"    # 实验性 pyrolite 只读后端
pip install "geophylo[test]"        # 测试
```

## 快速上手：Bio.Phylo 时间校准树

```python
from io import StringIO

import matplotlib.pyplot as plt
from Bio import Phylo

from geophylo import add_geo_axis, spec_from_biophylo

tree = Phylo.read(StringIO("((A:15.0, B:15.0):9.0, (C:14.0, D:14.0):10.0);"), "newick")

fig, ax = plt.subplots(figsize=(12, 8))
Phylo.draw(tree, axes=ax, do_show=False)

# root_age 来自外部时间校准结果；age_conversion 声明 branch length 单位 → Ma。
spec = spec_from_biophylo(tree, ax, time_axis="x", age_conversion=1.0, root_age=48.0)

result = add_geo_axis(ax, spec=spec, position="bottom",
                      ranks=["Period", "Epoch"], tick_style="boundaries")
plt.tight_layout()
result.finalize()   # 在 savefig 之前执行一次精确标签布局并固化
fig.savefig("timetree_with_geo.png", dpi=300)
```

## 快速上手：任意 Matplotlib 图（地层柱风格）

```python
import matplotlib.pyplot as plt
from geophylo import CoordinateSpec, add_geo_axis

fig, ax = plt.subplots(figsize=(12, 6))
ax.plot([0, 300], [0, 1])  # 任意图面内容
spec = CoordinateSpec.absolute(time_axis="x", age_range=(0.0, 300.0))
result = add_geo_axis(ax, spec=spec, position="bottom", ranks=["Period"])
plt.tight_layout()
result.finalize()
```

本库不会自行推断坐标范围。唯一的推断入口是
`CoordinateSpec.from_data_limits()`：

```python
CoordinateSpec.from_data_limits(ax, mode=..., time_axis=...,
                                acknowledge_inference=True)
```

缺省调用会抛出 `CoordinateError`，调用方必须显式传入
`acknowledge_inference=True` 来确认这次推断。

## 快速上手：数据查询

```python
from geophylo import Timescale

ts = Timescale()                              # 基线快照
ts.find_by_age(66.0, rank="Period").name      # 'Paleogene'
ts.get_interval("ics:period:jurassic").bounds # (older_ma, younger_ma)
list(ts.iter_intervals(ranks=["Epoch"], min_age=0, max_age=66))
```

## 环形树（实验性）

见 [examples/circular_tree.py](examples/circular_tree.py)。树由用户绘制，树和
`add_geo_ring()` 必须共用同一个 `RadialSpec` 实例。这样环上某半径处的年龄与树上
同一半径处的年龄，就在构造上保持一致。

## 数据来源与许可

内置快照由 `tools/build_snapshot.py` 从 ICS 官方版本化数据（CC-BY-4.0）确定性
生成，随包分发，只增不改。版本间的逐字段机器可读 diff 见
`geophylo/data/snapshots/diff-2024-12_to_2026-06.json`（由 `tools/make_diff.py`
生成），逐快照生成日志见 `tools/build-logs/`，推导快照 `2024/12` 的出处见
[`geophylo/data/snapshots/PROVENANCE.md`](GeoPhylo/data/snapshots/PROVENANCE.md)。

ICS 数据的引用与归因见 [NOTICE](NOTICE) 与
[数据政策（中文版）](docs/data-policy.zh.md)。本库代码以 MIT 许可发布
（见 [LICENSE](LICENSE)），第三方数据文件的许可与代码许可彼此独立。

## 兼容性

- Python 3.11～3.14；Matplotlib ≥ 3.10 且 < 4；NumPy ≥ 1.25。
- 本库可在无 GUI 环境运行（Agg 后端）。示例统一按
  `add_geo_axis() → tight_layout() → finalize() → savefig()` 的顺序组织。

## 开发

```bash
pip install -e ".[dev]"
pytest                       # 全部测试（阻塞门禁）
pytest -m "not experimental" # 只跑稳定 API
ruff check geophylo tests tools examples
mypy
```

发布（GitHub 公开 + Zenodo DOI）流程见
[RELEASE.zh-CN.md](RELEASE.zh-CN.md)（英文权威版见
[RELEASE.md](RELEASE.md)）。

## 作者与引用

- **作者**：曾子超（Zichao Zeng）—
  邮箱：zengzichao@sjtu.edu.cn —
  ORCID：[0000-0001-6553-970X](https://orcid.org/0000-0001-6553-970X) —
  上海交通大学生命科学技术学院。

若在研究中使用本库，请引用 GeoPhylo（机器可读引用记录见
[CITATION.cff](CITATION.cff)；Concept DOI 为 `10.5281/zenodo.23060662`，
v0.1.0 的 Version DOI 为 `10.5281/zenodo.23060663`），
并按 [NOTICE](NOTICE) 的要求同时引用《国际年代地层表》。

## 许可

源代码：MIT（[LICENSE](LICENSE)）。随包 ICS 图表数据：CC-BY-4.0
（[LICENSES/CC-BY-4.0.txt](LICENSES/CC-BY-4.0.txt)，归因说明见
[NOTICE](NOTICE)）。

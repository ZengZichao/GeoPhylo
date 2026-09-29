# 架构决策记录（Architecture decision records）

[English](README.md) | 中文

`geophylo` 中非显然选择的完整论证。每条记录写明决定了什么、否决了哪些替代方案、
以及后果对未来贡献者构成什么约束。源码 docstring 里的内联 `ADR-n` 标记指向此处
列出的记录。

权威版本以英文写成；它们记录的是随包发布的代码，因此每条主张都锚定到具体文件
（见每条记录的 `Code:` 行）。决策变化时，请以下一个编号写一条新记录，而不是
改写既有记录。

| # | 决策 | 记录于 | 被引用处 |
| --- | --- | --- | --- |
| ADR-1 | 随包分发确定性 ICS 快照作为默认数据源；`pyrolite` 保持为实验性、显式安装、只读的后端 | [ADR-1-bundled-snapshots-over-pyrolite.md](ADR-1-bundled-snapshots-over-pyrolite.md)（[中文](ADR-1-bundled-snapshots-over-pyrolite.zh.md)） | `docs/user-guide.zh.md` §11、`docs/user-guide.en.md` §11 |
| ADR-2 | 每条轨道画在由宿主创建的内嵌 `Axes` 里；绝不把 artist 直接叠加到宿主 `Axes` 上 | [ADR-2-inset-axes-for-tracks.md](ADR-2-inset-axes-for-tracks.md)（[中文](ADR-2-inset-axes-for-tracks.zh.md)） | `geophylo/render/linear.py`（模块 docstring） |
| ADR-3 | 返回 `GeoAxisResult` 结果对象，而不是返回宿主 `Axes` | [ADR-3-result-object-not-axes.md](ADR-3-result-object-not-axes.md)（[中文](ADR-3-result-object-not-axes.zh.md)） | `geophylo/render/linear.py`（`add_geo_axis`）、`geophylo/render/result.py`（`GeoAxisResult`） |
| ADR-4 | 适配器只构造并校验坐标契约，不负责绘图 | [ADR-4-adapters-build-contracts.md](ADR-4-adapters-build-contracts.md)（[中文](ADR-4-adapters-build-contracts.zh.md)） | `geophylo/adapter/biopython.py`（模块 docstring） |
| ADR-5 | 把边界建模为正交状态组（`age_ma`、`qualifier`、`uncertainty_ma`、`definition`） | [ADR-5-per-boundary-state-model.md](ADR-5-per-boundary-state-model.md)（[中文](ADR-5-per-boundary-state-model.zh.md)） | `geophylo/data/models.py`（`Boundary`） |

## 阅读顺序

先读数据层（ADR-1、ADR-5），再读坐标/渲染层（ADR-2、ADR-3），最后读适配器
（ADR-4）：只有先确立 `CoordinateSpec` 契约与"渲染绝不触碰宿主"契约，适配器
决策才说得通。

## 范围

这五条记录只覆盖上表所列决策。其他有意为之但**未**在此记录、而是记录在别处的
选择：

- 异常体系与"公共入口不得逃逸裸 `TypeError`/`ValueError`"规则 →
  `geophylo/exceptions.py` 与用户手册排错一节；
- 快照只增不改与哨兵断言发布仪式 →
  [`docs/data-policy.zh.md`](../data-policy.zh.md)（英文权威版
  [`docs/data-policy.md`](../data-policy.md)）；
- 推导快照 `2024/12` 的出处 →
  [`geophylo/data/snapshots/PROVENANCE.md`](../../geophylo/data/snapshots/PROVENANCE.md)；

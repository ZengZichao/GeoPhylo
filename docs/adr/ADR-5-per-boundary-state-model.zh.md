# ADR-5：把每个边界建模为一组正交状态，而不是一个裸年龄

[English](ADR-5-per-boundary-state-model.md) | 中文

- **状态**：已接受（自 0.1.0 起生效）
- **记录日期**：2026-09-11
- **代码**：`geophylo/data/models.py`（`Boundary`、`Interval`）、
  `geophylo/data/builtin.py`（`_boundary_from_payload`、`_check_hierarchy`）、
  `tools/build_snapshot.py`（`boundary_definition`、`boundary_qualifier`）、
  `tests/test_data_contract.py`

## 背景

一个公开发表的边界年龄不是一个数。在随包的 2026/06 快照里，下列不同情形全部
存在，而每一种都许可不同的下游主张：

| 边界 | 年龄 | 定义 | 误差 | `qualifier` |
| --- | --- | --- | --- | --- |
| base Jurassic | 201.4 ± 0.2 Ma | GSSP | 已公布 | `constrained` |
| top Jurassic | 143.1 ± 0.6 Ma | 数值估计 | 已公布 | `constrained` |
| base Quaternary | 2.58 Ma | GSSP | 未公布 | `defined` |
| base Anisian | 247.0 Ma | 数值估计 | 未公布 | `unknown` |
| top Phanerozoic | 0.0 Ma | present | — | `present` |

如果把这一切都压成一个浮点数，两类不同的事实就被混为一谈：

1. **边界是如何定义的** —— 经批准的 GSSP、GSSA、数值估计、present，或根本没有
   说明。
2. **数值的认识论状态是什么** —— 有声明误差约束、精确定义、显式近似（`~`）、
   present-day，或未知。

在下游，"0.0 的误差"与"未公布误差"的区别，正是会静默变成图注里虚假精度陈述的
那类差别。

## 决策

用一个冻结 dataclass 承载正交状态来表示边界：

```python
Boundary(age_ma, qualifier, uncertainty_ma, definition, source_iri)
```

- `qualifier ∈ {defined, constrained, approximate, present, unknown}` 描述
  **数字本身的性质**；`definition ∈ {gssp, gssa, numeric_estimate, present,
  unknown}` 描述**边界是如何定义的**。二者分开存储，查询时谁也不从谁派生。
- `uncertainty_ma` 是 `float | None`；`None` 表示上游未公布定量误差，显式
  **不**表示误差为零。
- 派生属性保持两条轴一致：`is_defined` 仅对 GSSP/GSSA 为真；`is_numeric` 要求
  qualifier 与 definition 同时可数值，并把 `qualifier="unknown"` 视为*未*受数值
  约束；`effective_uncertainty` 对 `unknown` 返回 `None`，永不返回 `0.0`。
- 两个字段在加载时按枚举校验；未知字符串抛 `DataValidationError`。
  `qualifier="approximate"` 承载图表的 `~`，提取器从边界端点的上游
  `skos:note "uncertain"` 标记读取它——包括空节点内部的情形，此时对行的剩余
  部分做匹配（`_NOTE_RE.search(rest)`）——并且 `boundary_qualifier()` 把它排在
  GSSP/GSSA 判定*之上*，因此一条 GSSP 定义、但其公布数值被上游明示为近似的
  边界被记为 `approximate` 而不是 `defined`。两份随包快照都携带全部 36 个这样的
  端点。因为这些值位于 `intervals` 内部，改动这一语义就会改动 payload 字节，
  进而牵动 `versions.json`、哨兵计数以及任何打印这些 qualifier 的图件：它是
  一次**数据变更**，必须按数据变更的流程发布（见 `docs/data-policy.md` 的
  "快照更新流程"），不能作为顺手修改混过去。
- 由于一条共享边界会出现在两条相邻记录里，加载器要求记录间共享的每个边界年龄
  在 `age_ma`、`qualifier`、`uncertainty_ma`、`definition` 四个字段上逐字段一致
  （`_check_hierarchy`）；生成器则从上游标记确定性地推导这两个字段，而不是逐
  记录拷贝（`boundary_definition()`、`boundary_qualifier()`）。

## 被否决的替代方案

- **`age_ma: float` 加 `error: float = 0.0`。** 否决：把"未公布误差"与"误差为
  零"混为一谈，而这是软件无权代替科学做出的可证伪主张。
- **单个合并字段（`"201.4 ± 0.2"`、`"~201.4"`、字符串 `"GSSP"`）。** 否决：
  契约上不可解析，而且共享边界一致性检查将无从做起。
- **把 definition 与 qualifier 合并成一个"精度"枚举。** 否决：两组状态是真
  正交的——GSSP 定义的边界可以带定量的放射测年误差，数值估计也可以被标记为
  近似——合并恰好会丢掉图注需要的那部分信息。
- **用邻近 rank 或 pyrolite 回填缺失元数据。** 否决：能保持诚实的替代做法就是
  写 `unknown`，这也正是实验性 pyrolite 后端被要求做到的（ADR-1）。
- **存储 `datetime`/`uncertain-float` 对象。** 否决：标准库没有能表达"由 GSSP
  定义、± 0.2 Ma"的类型，除非引入新依赖；而 JSON 往返本身就是快照契约。

## 后果

- 这些状态是可查询的，不是可打印的：渲染器只画数值边界年龄
  （`render/ticks.format_age()` 对 `qualifier` 一无所知），必须显示 `~` 或 `±`
  的图件应自行从 `interval.older_boundary.qualifier` / `.uncertainty_ma` 读取。
  把编码挡在条带之外，正是轨道几何契约保持简单的原因。
- 每份快照被校验两遍（哈希，然后逐字段一致性），手改的快照会以
  `DataValidationError` 大声失败。
- 诚实的 `unknown` 传播意味着某些派生字段为空；用户手册把 `unknown` 记录为
  正常的、预期的状态，而不是缺陷。
- 上游不一致必须在生成器中确定性调和并写入生成日志（例如 422.7 Ma 处同一误差
  同时出现 1.36 与 1.6 Ma 时，取最大值 1.6 Ma 并记录）——歧义在代码里消解，
  不在手工改过的 JSON 里消解。
- 测试用哨兵值钉住模型（`Jurassic 201.4 ± 0.2 → 143.1 ± 0.6`、
  `Phanerozoic 538.8 ± 0.6 → present`、`Wuchiapingian 259.857 ± 0.084`），语义
  变更无法伪装成一次数据刷新溜进门。

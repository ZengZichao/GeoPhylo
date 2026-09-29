# ADR-3：返回 `GeoAxisResult` 结果对象，而不是返回宿主 Axes

[English](ADR-3-result-object-not-axes.md) | 中文

- **状态**：已接受（自 0.1.0 起生效）
- **记录日期**：2026-09-11
- **代码**：`geophylo/render/result.py`、`geophylo/render/linear.py`
  （`add_geo_axis`）、`geophylo/render/polar.py`（`add_geo_ring`）、
  `tests/test_lifecycle.py`

## 背景

`add_geo_axis()` 总得返回点什么。返回宿主 `Axes` —— 许多 Matplotlib 辅助函数
从 `plt.plot` 借来的惯例 —— 看似"支持链式调用"，但在这里有主动误导性：调用
创建的对象*不是*宿主，宿主被刻意保持原样（ADR-2），而且条带需要生命周期
（宿主变化时重排、`savefig` 前显式冻结、拆除）。返回裸 `Axes` 还会让新建的
轨道在函数退出后无从寻找，因为调用方无法知道加了哪个子 Axes。

## 决策

返回专用的结果对象 `GeoAxisResult`，作为轨道的 axes、artist 与生命周期的唯一
入口。

- 属性暴露状态：`host_ax`、`geo_ax`、`artists`、`spec`、`position`、`key`、
  `params`，以及布局诊断 `labels_shortened`、`labels_rotated`、
  `labels_hidden`、`sync_degraded`。
- 方法管理生命周期：`update(**params)`、`sync()`、`relayout()`、`finalize()`、
  `remove()`、`restore()`、`attach_draw_callback()`。
- 该调用显式**不可**链式（`add_geo_axis(...).plot(...)` 不是有效用法）；
  `update()` 返回同一个结果对象以便反复改参数，`add_geo_axis(...)` 返回对象
  本身。
- `finalize()` 必须在 `tight_layout()`/`fig.canvas.draw()` 之后、`savefig()`
  之前调用；它把精确标签布局跑一次并冻结。随包示例统一遵循
  `add_geo_axis() → tight_layout() → finalize() → savefig()`。
- 每个结果对象按可选 `key` 参数注册进一张按宿主维系的弱引用表
  （`register_track`、`lookup_track`、`release_track`、`remove_all`），因此
  轨道可查找、可幂等替换，而不必返回宿主。

## 被否决的替代方案

- **返回宿主 `Axes`。** 否决：宿主并没有被修改，返回它会暗示错误含义；而且
  新建轨道及其降级诊断将不可达。
- **只返回轨道 `Axes`。** 否决：调用方能改样式，却无法重排、冻结或移除它，
  也没有载体携带 `sync()` 所需的宿主↔轨道配对。
- **返回 `tuple[GeoAxis, list[Artist]]`（`axhline` 式答案）。** 否决：参数、
  诊断与生命周期无处安放；第二次调用无从得知第一次做了什么。
- **返回 `None` 并要求 `lookup_track(ax, key)`。** 否决：让常见路径变笨拙，
  还把图件与测试必须断言的降级统计藏起来。
- **让所有方法返回 `self` 以支持流式链式调用。** 否决：跨过
  `finalize()`-before-`savefig()` 边界的链式调用会掩盖契约依赖的顺序要求；
  只有 `update()` 返回对象。

## 后果

- 文档写明的调用顺序是真实要求，误用表现为明显未冻结的布局而不是异常；用户
  手册在每个示例里都写明该顺序。
- 结果对象是布局降级的唯一上报处，"隐藏标签 ≤ 20%"的验收口径因此可以被机器
  校验。
- 持有宿主 `Axes` 的引用需要小心处理图窗拆除，因此有弱引用注册表与
  `remove_all()`。
- 生命周期行为的测试对对象断言而不是对像素断言，这让副作用契约
  （`AxesState.matches`）的验证保持廉价。

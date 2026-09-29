# ADR-2：轨道画在内嵌 Axes 上，而不是把 artist 叠加到宿主 Axes

[English](ADR-2-inset-axes-for-tracks.md) | 中文

- **状态**：已接受（自 0.1.0 起生效）
- **记录日期**：2026-09-11
- **代码**：`geophylo/render/linear.py`（`_make_track_axes`、
  `_align_track_to_host`）、`geophylo/render/polar.py`、
  `geophylo/render/result.py`（`AxesState`）、`tests/test_visual.py`、
  `tests/test_add_geo_axis.py`

## 背景

地质时间条带必须紧贴宿主面板并共享其时间维度，但宿主面板属于用户：它可能是
时间树、地层柱或散点图，它的 limits、scale、autoscale 标志和 `dataLim` 对面板
上其他内容都是承重的。Matplotlib 里把条带挂上去的方式有两种：

1. 用宿主的数据坐标，把 `Rectangle`/`Text` artist 直接加到宿主 `Axes` 上。
2. 创建一个按宿主 axes-fraction 定位的子（内嵌）`Axes`，让条带的 artist 归它
   所有。

方式 (1) 就是手画条带的做法，也正是本包装必须证明自己**没有**做的：
加到宿主 `Axes` 上的 `Rectangle` patch 会扩展 `dataLim`，画一条 0 到 541 Ma 的
条带会静默地把一个只跨 0 到 66 Ma 的面板重新缩放。方式 (2) 还额外给每条轨道
一个独立的第二维度（`[0, 1]` 的厚度轴），这是平面叠加无法表达的。

## 决策

每条轨道都渲染在由 `host_ax.inset_axes(bounds)` 创建的内嵌 `Axes` 里；叠加
路线完全不予实现。

- `bounds` 用宿主 axes-fraction 坐标给出。Matplotlib ≥ 3.10 的 `inset_axes`
  已经使用 `transAxes`，因此刻意**不再**重复传入 transform（重复传入会二次
  转换）。
- `thickness_ratio` 是*宿主*包围盒的比例，所以图窗缩放时轨道几何跟随宿主；
  布局计算（`MIN_TRACK_THICKNESS_PX`、标签排布）则按物理像素进行。
- 轨道的时间范围从宿主**数值拷贝**（`set_xlim(host.get_xlim())`）而**不是**
  用 `sharex` 共享，这样之后的宿主 autoscale 不会把轨道拖走；垂直范围钉在
  `[0, 1]`。因为是数值拷贝，`spec.age_to_data()` 的输出可以直接当轨道数据
  坐标用，不需要第二次变换。
- 在画任何东西之前，宿主的视图状态被快照进 `AxesState`（两个 limits、两个
  scale、两个 autoscale 标志、冻结的 `dataLim`），并在 `remove()`/`restore()`
  时恢复；`AxesState.matches()` 是测试所用的断言。
- 内嵌策略只针对线性轨道。极坐标环刻意**不**用内嵌：`add_geo_ring()` 直接画进
  调用者自己的极坐标 `Axes`（`geophylo/render/polar.py`，`owns_axes=False`），
  因为环的半径是相对用户已经在该 Axes 上设置的径向视图定义的；因此结果对象
  不拥有任何 Axes，`remove()` 不动宿主视图状态。

## 被否决的替代方案

- **在宿主 `Axes` 上叠加 patch。** 否决：污染 `dataLim` 与宿主 artist 列表、
  无法表达厚度维度，而且"宿主不被触碰"的契约会变得不可证明。
- **宿主与轨道之间 `sharex`/`sharey`。** 否决：共享在 autoscale 时是双向的，
  之后的宿主重缩放会静默改写轨道范围并破坏已记录的 `CoordinateSpec`。数值
  拷贝加显式 `sync()` 把控制方向保持为单向。
- **`axes.dividers`/`aux_axes` 风格的布局对象。** 否决：在受支持的 Matplotlib
  范围（≥ 3.10, < 4）内不是稳定 API，而且对 artist 而言还是同一个 `dataLim`
  问题。
- **要求用户手工预留空间**（例如预先缩小宿主）。否决：那样 `tight_layout` 与
  `finalize()` 的顺序就成了用户负担；内嵌加 `pad` 让几何成为库的责任。

## 后果

- 条带是真正的 `Axes`（`result.geo_ax`），用户可以直接对它做样式定制
  （spines、ticks、zorder），不必伸进宿主。
- 画出的每个 artist 都可寻址、可成组移除，这正是 `remove()` 精确且幂等的
  原因。
- 宿主一变，轨道几何必须重算，因此有 `draw_event` 回调、`sync()`，以及在
  `savefig` 前冻结精确标签布局的 `finalize()`。
- 基于像素的布局意味着输出几何依赖 `dpi`；随包示例因此都显式固定 `dpi`。
- "宿主不被触碰"是*被测试的*契约而非文档声明：视觉与生命周期测试逐字段比较
  `AxesState`。

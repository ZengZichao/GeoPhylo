# ADR-4：适配器构造并校验坐标契约，不负责绘图

[English](ADR-4-adapters-build-contracts.md) | 中文

- **状态**：已接受（自 0.1.0 起生效；iplotx 与环形条目为实验性）
- **记录日期**：2026-09-11
- **代码**：`geophylo/adapter/biopython.py`、`geophylo/adapter/iplotx.py`、
  `geophylo/coordinate/spec.py`、`geophylo/coordinate/radial.py`、
  `tests/test_adapter_biopython.py`、`tests/test_adapter_iplotx_contract.py`

## 背景

本库的立足点是时间树坐标轴必须自己说明自己的含义：要么绝对年龄，要么到根的
距离（真值表见用户手册 §4）。树库把这种几何隐式编码——`Bio.Phylo` 的
`Phylo.draw()` 画的是累计分支长度，`iplotx` 的水平布局经 `get_layout()` 也是
如此——而这些库都不知道 `CoordinateSpec` 的存在。问题在于：这层翻译放在哪里，
以及允许适配器做什么。

## 决策

适配器的职责是**构造并校验坐标契约**，永远不画图。

- `spec_from_biophylo(tree, ax, *, time_axis, age_conversion, root_age)` 返回
  一个 `CoordinateSpec`；它什么都不画、不加任何 artist。渲染留在
  `add_geo_axis(spec=...)` 之后，因此随包快照、离线 JSON 与适配器走的是同一条
  渲染路径。
- 它始终产生 `mode="root_distance"`。`Phylo.draw()` 的数据坐标*就是*到根的累计
  距离，在这个坐标系里给 `absolute_age` 会静默放错每一个区间；与其提供一个
  可能出错的模式，适配器干脆不提供。
- 它先校验树、再推导任何东西：根的 `branch_length` 必须为 `None` 或严格为零
  （非零的根分支长度会平移整张根距离↔年龄映射，而 `tree.distance()` 会把它
  计入），每条分支长度必须存在、为数值、有限且非负——统一收集并以一条
  `CoordinateError` 一次性报告——且 `age_conversion` 必须声明分支长度到 Ma 的
  换算，使模式选择是一个被陈述的事实而不是猜测。
- `spec_from_iplotx()` 遵循同样的规则，经 `artist.get_layout()` 读取布局；它
  完全不接受 `Axes`，因为 `Axes` 不携带任何树坐标信息。它显式拒绝径向布局；
  径向情形由独立入口 `radial_spec_from_biophylo()` 覆盖。
- 非超度量树是被有意支持的：叶片停在化石首现/末现是这类图件的常态，所以适配
  器校验的是单位与可达性，而不要求根到叶距离相等。

## 被否决的替代方案

- **`add_geo_axis_to_tree(tree, ax, ...)` 一步到位的便捷绘图。** 否决：它会把
  两个契约（树布局自由、条带生命周期）焊死在一起，并掩盖本库存在所要暴露的
  模式决策。`adapter → render` 方向不存在任何绘图边：适配器构造契约，绘图
  步骤永远由调用方写。
- **从坐标轴 limits 推断 `absolute_age` 还是 `root_distance`。** 否决：两种
  模式可以产生相同的数值范围；推断就是猜测，而本库的规则是坐标语义有歧义时
  抛 `CoordinateError` 而不是猜。`CoordinateSpec.from_data_limits()` 是唯一的
  推断入口，且强制 `acknowledge_inference=True`。
- **让适配器接受已画好的 `Axes` 并回读 artist。** 否决：Matplotlib 不会在
  artist 坐标里保留树拓扑，回读必然有损且不可核验——因此 `spec_from_iplotx()`
  拒绝 `Axes`、改为读取布局对象。
- **一个对 `.root` 鸭子类型、通吃任何树对象的通用适配器。** 否决：两个受支持
  的库恰恰在正确性要害处不同（超度量假设、布局所有权、径向支持），单一签名
  无论如何都得在内部分支。

## 后果

- 适配器是输入的纯函数，无需图窗即可测试：契约测试断言产出的 `mode`、
  `age_range` 与 `root_age`；iplotx 路径经伪造的 `TreeArtist` 测试。
- 绘图步骤永远由用户自己写，因此画树的库可替换（`Bio.Phylo`、`iplotx`、
  手绘）。
- 可选依赖保持可选：导入 `geophylo` 永不导入 `Bio`/`iplotx`；适配器在缺失时
  抛出带安装提示的 `ImportError`。
- 第三方失败不得以裸 `TypeError`/`ValueError` 逃逸：适配器把它们转换为
  `CoordinateError` 并保留因果链（见 `geophylo/exceptions.py` 的错误处理契约）。
- 由于没有绝对年龄的适配器路径，绝对年龄的时间树坐标轴必须用
  `CoordinateSpec.absolute(...)` 显式构造。

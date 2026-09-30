# GeoPhylo 中文使用文档

**版本**：对应 GeoPhylo 0.1.0（含实验性符号）
**适用环境**：Python 3.11～3.14 · Matplotlib ≥ 3.10 且 < 4 · NumPy ≥ 1.25
**配套英文文档**：[user-guide.en.md](user-guide.en.md)

---

## 目录

1. [简介](#1-简介)
2. [安装](#2-安装)
3. [五分钟上手](#3-五分钟上手)
4. [核心概念：坐标语义契约](#4-核心概念坐标语义契约)
5. [数据查询：Timescale](#5-数据查询timescale)
6. [线性地质时间轴：add_geo_axis()](#6-线性地质时间轴add_geo_axis)
7. [GeoAxisResult 生命周期](#7-geoaxisresult-生命周期)
8. [Bio.Phylo 适配：spec_from_biophylo()](#8-biophylo-适配spec_from_biophylo)
9. [环形时间环（实验性）：RadialSpec 与 add_geo_ring()](#9-环形时间环实验性radialspec-与-add_geo_ring)
10. [iplotx 适配（实验性）](#10-iplotx-适配实验性)
11. [pyrolite 后端（实验性）](#11-pyrolite-后端实验性)
12. [异常体系与排错指南](#12-异常体系与排错指南)
13. [常见问题 FAQ](#13-常见问题-faq)
14. [示例脚本索引](#14-示例脚本索引)
15. [数据来源、许可和引用](#15-数据来源许可和引用)

---

## 1. 简介

`geophylo` 是一个面向 Matplotlib 的地质时间轴可视化库。它把 ICS（International
Commission on Stratigraphy，国际地层委员会）发布的《国际年代地层表》（International
Chronostratigraphic Chart）作为**可复现的内置快照**，叠加到两类图上：时间校准系统
发育树（timetree），以及任何以 Ma（百万年）为横轴或纵轴的图。

R 语言生态中的 `deeptime` 通过 `coord_geo()` 为 ggplot2、ggtree 提供同类能力；
`geophylo` 为 Matplotlib 生态补齐这一环，并把**坐标语义的正确性与可复现性**放在
第一位：

- **无法确定坐标语义就报错，绝不静默猜测。** 每个公开入口都显式校验坐标语义。
  需要推断时，只能走带 `acknowledge_inference=True` 的唯一入口。
- **快照只增不改、可哈希校验。** ICS 数据以版本化 JSON 快照随包分发，
  加载时逐字节校验 SHA-256；同一版本的数据永远返回相同查询结果。
- **不改动宿主图。** 时间条带绘制在 inset 轨道 Axes 上，宿主 Axes 的 limits、
  scales、autoscale 状态与 `dataLim` 在调用前后逐字段不变。
- **强类型公共异常。** 所有异常继承 `GeophyloError`；第三方库的原始
  `TypeError`、`ValueError` 不会从公共入口传出。

**明确不做的事**：不绘制树本身（矩形树由 Bio.Phylo 或 iplotx 绘制，环形树按第 9 节
配方自绘）；不做时间校准或分子钟分析；不联网更新 ICS 数据。

---

## 2. 安装

### 2.1 环境要求

- Python 3.11～3.14，Matplotlib ≥ 3.10 且 < 4，NumPy ≥ 1.25。
- 核心功能只需要 Matplotlib 和 NumPy。Bio.Phylo、iplotx 和 pyrolite 三条路径各自
  对应一个可选附加组（extra），按需安装。
- 无 GUI 环境（服务器和 CI）无需任何额外配置，Agg 后端开箱即用。

### 2.2 安装方式

```bash
pip install geophylo                 # 核心（仅需 matplotlib + numpy）
pip install "geophylo[biopython]"    # Bio.Phylo 适配（稳定 API）
pip install "geophylo[iplotx]"       # iplotx 适配（实验性）
pip install "geophylo[pyrolite]"     # 实验性只读数据后端
pip install "geophylo[test,dev]"     # 测试、lint、类型检查
```

从源码安装（开发模式）：

```bash
git clone <仓库地址> geophylo
cd geophylo
pip install -e ".[dev]"
```

### 2.3 验证安装

```bash
pytest                # 全部测试
pytest -m "not experimental"   # 仅稳定 API 范围
```

---

## 3. 五分钟上手

### 3.1 Bio.Phylo 时间校准树 + 地质时间条带

```python
from io import StringIO

import matplotlib.pyplot as plt
from Bio import Phylo

from geophylo import add_geo_axis, spec_from_biophylo

tree = Phylo.read(
    StringIO("((A:15.0, B:15.0):9.0, (C:14.0, D:14.0):10.0);"), "newick"
)

fig, ax = plt.subplots(figsize=(12, 8))
Phylo.draw(tree, axes=ax, do_show=False)

# root_age 来自外部时间校准；age_conversion 声明 branch length 单位 → Ma。
spec = spec_from_biophylo(tree, ax, time_axis="x", age_conversion=1.0, root_age=48.0)

result = add_geo_axis(ax, spec=spec, position="bottom",
                      ranks=["Period", "Epoch"], tick_style="boundaries")
plt.tight_layout()
result.finalize()   # savefig 之前执行一次精确标签布局并固化
fig.savefig("timetree_with_geo.png", dpi=300)
```

推荐的调用顺序是 **`add_geo_axis()` → `tight_layout()` → `result.finalize()` →
`savefig()`**：文本实际尺寸只有在图尺寸确定后才能测量，`finalize()` 立即执行一次
精确标签布局并固化结果。

### 3.2 任意 Matplotlib 图（地层柱风格）

不画树、只想给一张以 Ma 为横轴的图加地质时间条带：

```python
import matplotlib.pyplot as plt
from geophylo import CoordinateSpec, add_geo_axis

fig, ax = plt.subplots(figsize=(10, 4))
# ... 在 ax 上绘制你的数据（x 轴为 Ma，0 在右侧时可 ax.invert_xaxis()）...

# 显式声明：时间沿 x、绝对年龄模式、坐标语义范围 0～298.9 Ma（石炭系-二叠系界线）
spec = CoordinateSpec.absolute(time_axis="x", age_range=(0.0, 298.9))
result = add_geo_axis(ax, spec=spec, position="bottom", ranks=["Period"])
result.finalize()
fig.savefig("strat_column.png", dpi=300)
```

### 3.3 数据查询（不画图）

```python
from geophylo import Timescale

ts = Timescale()                               # 基线快照（2026/06）
ts.find_by_age(66.0, rank="Period").name       # 'Paleogene'
ts.get_interval("ics:period:jurassic").bounds  # (older_ma, younger_ma)
list(ts.iter_intervals(ranks=["Epoch"], min_age=0, max_age=66))
```

---

## 4. 核心概念：坐标语义契约

### 4.1 为什么需要 CoordinateSpec

一张时间树图的横轴有两种可能含义：

- **绝对年龄**（`absolute_age`）：轴上每个数值就是一个 Ma 年龄；
- **根距离**（`root_distance`）：轴上每个数值是“到根的累积 branch length”，
  与 Ma 只差一个比例（外加一个根年龄锚点）。

两者视觉上可能完全一样，混淆它们会造成**科学错误**（条带整体错位或缩放）。
`geophylo` 的解法是显式声明：坐标语义写在一个冻结的 `CoordinateSpec` 对象里。该
对象是唯一真值来源，所有绘制函数只读取它，不做猜测。

### 4.2 构造方式

```python
from geophylo import CoordinateSpec

# 绝对年龄模式：root_age 必须为 None
spec = CoordinateSpec.absolute(time_axis="x", age_range=(0.0, 300.0))

# 根距离模式：root_age 必填（来自外部时间校准）
spec = CoordinateSpec.root_distance(time_axis="x", age_range=(0.0, 100.0),
                                    root_age=100.0)

# 也可以直接用构造函数（校验规则相同）
spec = CoordinateSpec(time_axis="x", mode="root_distance",
                      age_range=(0.0, 48.0), root_age=48.0)
```

字段含义：

| 字段 | 含义 | 约束 |
| --- | --- | --- |
| `time_axis` | 时间沿哪条轴 | `"x"` 或 `"y"` |
| `mode` | 坐标模式 | `"absolute_age"` 或 `"root_distance"` |
| `age_range` | 坐标语义范围 `(min_age, max_age)` | `0 <= min_age < max_age`；决定换算合法性域 |
| `root_age` | 根年龄（Ma） | `root_distance` 模式必填；`absolute_age` 模式必须为 `None` |

> **`age_range` 与绘制窗口的区别**：`age_range` 是调用方声明的坐标语义范围（换算
> 合法性域）；`min_age` 和 `max_age` 是某一次绘制的窗口（裁剪边界）。窗口可以比
> `age_range` 窄，但不能超出 `age_range`。

### 4.3 年龄 → 数据坐标

`spec.age_to_data(age_ma)` 是纯函数：

- `absolute_age` 模式：返回 `age_ma` 本身；
- `root_distance` 模式：返回 `root_age - age_ma`。

它**不处理轴反向**。`ax.invert_xaxis()` 一类的视图反向由 Matplotlib 负责：同一
age 的 patch 数据坐标在正反视图下完全相同，只是显示方向不同。域外输入（NaN、超
范围、负根距离）抛 `CoordinateError`。

### 4.4 真值表

| `mode` | `time_axis` | 轴方向 | `age_to_data(age)` | 显示效果 |
| --- | --- | --- | --- | --- |
| `absolute_age` | `x` | 正常 | `age` | 越老越靠右 |
| `absolute_age` | `x` | 反向 | `age` | 越老越靠左 |
| `absolute_age` | `y` | 正常 | `age` | 越老越靠上 |
| `absolute_age` | `y` | 反向 | `age` | 越老越靠下 |
| `root_distance` | `x` | 正常 | `root_age - age` | 根在左、叶在右 |
| `root_distance` | `x` | 反向 | `root_age - age` | 根在右、叶在左 |
| `root_distance` | `y` | 正常 | `root_age - age` | 根在下、叶在上 |
| `root_distance` | `y` | 反向 | `root_age - age` | 根在上、叶在下 |

显示方向建议：同一套图内的方向保持一致，并与地层学惯例（越老越靠左或靠下）
相符。水平时间树用 `root_distance` 模式时选**正常**视图（根在左、叶在右），用
`absolute_age` 模式时把 `x` 轴选为**反向**视图；镜像方向仅在确有排版理由时使用。

### 4.5 范围推断（默认拒绝）

从 Axes 数据范围推断 `age_range` 属于隐式假设，默认直接抛 `CoordinateError`。
确认数据范围可信后，可以显式放行这次推断：

```python
spec = CoordinateSpec.from_data_limits(
    ax, mode="absolute_age", time_axis="x",
    acknowledge_inference=True,   # 显式确认「我接受这次推断」
)
```

推断读取宿主 Axes 的**视图范围**（view limits，即 `get_xlim()`/`get_ylim()`）；轴反向时自动按数值
大小归一化。`root_distance` 模式推断时 `root_age` 仍必填。

---

## 5. 数据查询：Timescale

### 5.1 构造与版本

```python
from geophylo import Timescale

ts = Timescale()                    # 基线快照（versions.json 标注，当前为 2026/06）
ts = Timescale(version="2024/12")   # 任一已发布的历史快照
ts = Timescale.from_json("my.json") # 离线自定义时间表（同一 schema 校验）
ts = Timescale(backend="pyrolite")  # 实验性只读后端（见第 11 节）

ts.version        # '2026/06'
ts.ranks          # ('Eon', 'Era', 'Period', 'Epoch', 'Age')
ts.metadata       # BackendMetadata（数据版本、能力声明、rank 映射）
```

可用版本列表见 `geophylo.data.builtin.available_versions()`。请求未发布的版本时抛
`DataValidationError`（消息含可用版本列表）。

### 5.2 三条查询通道

**按稳定 ID 查询**（唯一接受 ID 的入口）：

```python
ts.get_interval("ics:period:jurassic")
ts.get_interval("ics:period:jurassic").bounds       # (201.4 ±0.2, 143.1 ±0.7) 数值部分
ts.get_interval("ics:period:jurassic").boundaries   # (Boundary, Boundary) 逐边界状态
```

传入名称时抛 `IntervalNotFoundError`，消息提示改用 `find_by_name()`。

**按名称或别名查询**（大小写折叠的子串匹配；通道优先级 name → aliases → label）：

```python
ts.find_by_name("Holocene")
ts.find_by_name("Jurassic")                                 # 精确名唯一命中
ts.find_by_name("cambrian", case_sensitive=False)           # 大小写不敏感的精确命中
ts.find_by_name("Upper", rank="Epoch", parent="ics:period:cretaceous")  # 用 rank+parent 消歧
```

命中 0 个时抛 `IntervalNotFoundError`；命中 ≥2 个时抛
`AmbiguousIntervalError`（`exc.candidates` 携带候选 ID 列表）。

**按年龄查询**（语义见 5.3）：

```python
ts.find_by_age(66.0, rank="Period").name    # 'Paleogene'
ts.find_by_age(66.0, rank="Era").name       # 'Cenozoic'
ts.find_by_age(0.0).name                    # 'Meghalayan'（最年轻 Age）
```

### 5.3 年龄边界语义（`find_by_age`）

1. 普通情况：返回满足 `older_ma >= age > younger_ma` 的区间；
2. 恰好落在内部边界上：归属**以该边界为 `older_ma` 的较年轻区间**
   （66.0 Ma → Paleogene，不是 Cretaceous）；
3. `0.0` Ma：显式归入最年轻区间；
4. 超过该 rank 最老边界：抛 `IntervalNotFoundError`，不外推；
5. 浮点吸附：与边界距离 ≤ 1e-9 的输入先吸附到边界再归属。

### 5.4 遍历（窗口**相交**语义）

```python
for interval in ts.iter_intervals(ranks=["Period", "Epoch"],
                                  min_age=100.0, max_age=200.0):
    print(interval.name, interval.bounds, interval.color)
```

返回**所有与窗口有交集的完整区间**（跨边界的区间也会返回，由绘制层负责裁剪），
排序确定：`older_ma` 降序 → rank 序（Eon > Era > Period > Epoch > Age）→ `id`。
`ranks=None` 表示全部五个核心 rank。

### 5.5 Interval 与逐边界状态

```python
iv = ts.get_interval("ics:period:cretaceous")
iv.name, iv.rank, iv.parent_id, iv.color
iv.older_ma, iv.younger_ma        # 边界数值（Ma，越老越大）
iv.bounds                         # (older_ma, younger_ma)
old_b, yng_b = iv.boundaries      # Boundary 对象
old_b.qualifier        # 'constrained' | 'defined' | 'approximate' | 'present' | 'unknown'
old_b.uncertainty_ma   # 定量误差（± Ma）或 None（None ≠ 0！）
old_b.definition       # 'gssp' | 'gssa' | 'numeric_estimate' | 'present' | 'unknown'
old_b.is_defined                  # 是否由 GSSP/GSSA 定义
iv.is_approximate_any()           # 任一端点带 ~ 近似值
iv.has_defined_boundary           # 任一端点由 GSSP/GSSA 定义
```

`definition` 的取值 `gssp` 和 `gssa` 分别指由 GSSP（Global Boundary Stratotype
Section and Point，全球界线层型剖面和点位）定义的界线，和由 GSSA（Global Standard
Stratigraphic Age，全球标准地层年龄）定义的界线。

结构节点（如 `Precambrian`、`Super-Eon`）只作为 `parent_id` 锚点存在，
不出现在 `ts.ranks` 中，也不参与时间轴绘制。

---

## 6. 线性地质时间轴：add_geo_axis()

### 6.1 完整签名

```python
result = add_geo_axis(
    ax,                          # 宿主 Axes（位置参数）
    *,                           # 以下全部为关键字参数
    spec,                        # CoordinateSpec，必填
    position="bottom",           # "bottom" | "top" | "left" | "right"
    ranks=None,                  # None → ("Period",)；或 str / 序列
    timescale=None,              # None → 默认内置快照
    thickness_ratio=0.12,        # 轨道总厚度占宿主边长比例，(0, 0.5]
    min_age=None,                # 绘制窗口；None → spec.age_range
    max_age=None,
    fill=True,                   # 是否按 ICS 官方色填充
    alpha=1.0,                   # 填充透明度 [0, 1]
    label=True,                  # 是否显示名称标签
    label_size=6.0,              # 标签字号（pt）
    label_color="auto",          # "auto" 按合成背景自动选黑/白
    skip=None,                   # 跳过显示的区间名称序列
    abbreviate=True,             # 空间不足时允许缩写（用官方缩写）
    border="both",               # "none" | "near" | "far" | "both"
    border_width=0.5,
    border_color="black",
    rotation=0.0,                # 标签固定旋转角（度）
    tick_style="none",           # "none" | "boundaries" | "ages"
    tick_max_count=10,           # 刻度硬上限
    key=None,                    # 轨道标识（幂等更新），见 7.2
    preserve_axes_state=True,    # 是否承诺不改动宿主视图状态
)
```

### 6.2 参数详解

**`position`** 决定轨道贴在宿主哪条边，并**唯一**决定时间方向：
`bottom`、`top` → 时间沿 x；`left`、`right` → 时间沿 y。
`spec.time_axis` 仅作一致性校验：`position="left"` 配 `spec.time_axis="x"`
会抛 `CoordinateError`（消息给出正确配对）。

**`ranks`** 支持多层级轨道。顺序策略：**第一个 rank 最靠近数据区**（near 侧）。
例如 `ranks=["Period", "Epoch"]` 在 `position="bottom"` 时 Period 在上、Epoch
在下。各轨道厚度按权重（Eon 0.8、Era 1.0、Period 1.2、Epoch 1.5 和 Age 2.0）初始
分配，再按最小 6 px 厚度校正。空间不足以让每条轨道达到最小厚度时抛
`InvalidRangeError`（可行性预检在分配前完成）。

这里的 6 px 是**运行时常量**，不是写死在布局里的字面量：它是
`geophylo.render.linear.MIN_TRACK_THICKNESS_PX`，`compute_track_layout()` 以
`min_px` 参数接收它。因此字号或图幅特殊的调用方可以给 `compute_track_layout()`
传入其他下限，`add_geo_axis()` 则一律使用该模块级值。空序列、重复 rank、非法 rank
（大小写敏感，`"period"` 不自动纠正）都抛 `InvalidRankError`。

**`min_age` 和 `max_age`（绘制窗口）**：`add_geo_axis()` 把窗口内的区间**裁剪**到
窗口边界。与窗口相交但跨边界的区间，会画出窗口内的可见片段（窗口相交语义，不会
漏绘）。窗口必须落在 `spec.age_range` 内。

**`tick_style`（数值刻度）**：

- `"none"`（默认）：只画色块和标签，不画数值刻度；
- `"boundaries"`：以窗口内各 rank 的区间边界为刻度，去重后按像素间距过滤
  （任何两个刻度中心间距 < `label_size × 2` px 时保留较老者）。该样式**不受**
  `tick_max_count` 约束：读者会把缺少一个边界数字理解成“该处不存在界线”，因此
  取舍只由像素间距决定；丢弃的候选数量记录在 `result.ticks_dropped`；
- `"ages"`：在边界基础上，对超过窗口 20% 的稀疏区段补充等距刻度，总量受
  `tick_max_count` 上限约束（裁剪优先级：rank 边界 > 整十、整百 Ma > 其他，每一层
  内部一律从最老一端优先保留）；`result.ticks_dropped` 记录上限与间距两层丢掉的
  候选数量。

间距过滤执行两遍：先按刻度**中心**（`label_size × 2` px），再按边缘对齐后的**文本
包围盒**，碰撞时一律保留较老者。贴窗口边缘的刻度数字改为按内沿对齐（不再居中），
因此不会越出轨道矩形；若对齐后的包围盒会与邻居数字粘连，则丢掉较年轻的那个数字
（而不是把两个数字画在一起）。

刻度一律显示 Ma 数值（`root_distance` 模式同样换算回 Ma 显示），并附带 `"Ma"`
单位标签。该标签放在轨道矩形**之外**、窗口较老的一端，不与任何刻度数字重叠。
格式化规则确定：`0 ≤ age < 1` 两位小数；`1 ≤ age < 100` 一位小数（整数值省略
小数点）；`age ≥ 100` 整数。例：`0.0 → "0.00"`、`1.0 → "1"`、`66.0 → "66"`、
`538.8 → "539"`。

**标签自动降级**（空间不足时按固定顺序，不跳步）：
① 缩写 → ② 旋转 → ③ 隐藏（rank 越核心、年代越老越优先保留）。
降级结果记录在 `result.labels_shortened`、`result.labels_rotated` 和
`result.labels_hidden`。
缩写这一步有两条规则：

- 只采纳快照 `aliases` 中的**单段短代码**——1～2 个字母后接至多 2 位数字、总长
  不超过 4 字符（如 `J`、`P1`、`T3`、`c7`）。ICS 图表会把“子统 + 阶”两级分组编码
  拼成复合短代码（如 `C2c6c7`、`C1c1`、`C2c5`）。这类 `ccgmShortCode` **不是缩写**，
  读者无法从图面上反解，因此对应区间改用**全名**标注。不按词长截断，以免凭空造出
  记号。用户显式 `abbreviate=False` 时整步跳过；
- 碰撞检测基于 renderer 实测的文本包围盒，两条几何约束都按**每个候选的旋转角**
  求值。厚度维是硬约束，旋转与不旋转的标签都**永不越过相邻轨道边界**。时间维上，
  标签可以溢出自身区间，进入**同一轨道矩形内**的空白。贴窗口边缘的标签会向内夹紧，
  使包围盒整体落在轨道矩形之内，绝不画到轨道或画框之外；夹紧后仍放不下者直接隐藏。
  裁剪后时间维宽度不足 `MIN_LABEL_LENGTH_PX`（0.5 px）的贴边片段不再产出名称标签。

**`label_color="auto"`** 会先做 alpha 合成（色块颜色和轨道背景按 `alpha` 混合），
再按 WCAG（Web Content Accessibility Guidelines，Web 内容无障碍指南）相对亮度选择
黑或白，保证半透明色块上的标签可读。

### 6.3 副作用契约

`preserve_axes_state=True`（默认）时，`add_geo_axis()` **不修改宿主 Axes 的任何视图
状态**：`get_xlim()`、`get_ylim()`、`get_xscale()`、`get_yscale()`、
`get_autoscalex_on()`、`get_autoscaley_on()` 和 `dataLim` 在调用前后逐字段相等。
轨道绘制在 `host_ax.inset_axes()` 创建的独立 Axes 上，其数据范围“复制宿主数值但不
共享”。把该参数设为 `False` 是本库留出的显式放行入口，允许实现改动宿主状态
（`result.restore()` 可还原）。

`remove()` 沿同一承诺的反方向成立。它**只在宿主视图仍与创建时的快照一致**时才自动
还原快照，此时还原是一次对用户不可见的幂等清理。若用户在本轨道存活期间改动了
limits、scale 或反向轴，`remove()` 会保留这些设置，不做反向改写，只清理本库新增的
Artist。确有需要回到创建时刻时，请显式调用 `result.restore()`。

---

## 7. GeoAxisResult 生命周期

### 7.1 五个生命周期方法

```python
result = add_geo_axis(ax, spec=spec)

result.update(ranks=["Period", "Epoch"], alpha=0.8)  # 原地重建（返回 self，可链式）
result.sync()        # 宿主 limits / 物理尺寸变化后重对齐 + 重排厚度
result.finalize()    # 立即执行一次精确标签布局并固化
result.remove()      # 移除全部 Artist、断开回调、释放 key
result.restore()     # 按创建时快照还原宿主 Axes 状态
```

- **`update()`** 只接受渲染参数（`ranks`、`thickness_ratio`、`min_age`、
  `max_age`、`fill`、`alpha`、`label`、`label_size`、`label_color`、`skip`、
  `abbreviate`、`border*`、`rotation`、`tick_style`、`tick_max_count`）。`spec`、
  `position`、`timescale` **不可**原地更新——这三个参数意味着坐标语义或承载 Axes
  变化，传入即抛 `CoordinateError`。所有取值域校验和几何预检通过后才提交：失败的
  `update()` 不改动任何状态（原 Artist 与原参数保持不变）。
- **`sync()`** 有两层语义：① 把轨道时间维数据范围重新复制为宿主当前值；
  ② 宿主物理尺寸变化后，用当前尺寸重新执行厚度分配（仍受 6 px 最小厚度和总量
  守恒约束）。空间不足时保持上次布局，并把 `result.sync_degraded` 置为
  `True`（诊断位）。`add_geo_axis()` 会注册 `draw_event` 回调：该回调检测到宿主
  limits 或图尺寸变化时自动调用 `sync()`，并在未 `finalize()` 前自动执行一次精确
  标签布局。
- **`finalize()`** 之后不再自动重排（适合 savefig 前固化）。`remove()` 会断开
  回调，避免泄漏。
- **`remove()`** 移除本库新增的全部 Artist，断开回调并释放 key。它同时还原宿主
  快照，但**仅当宿主视图仍与快照一致**时才这样做；用户在其间改动的视图保持原样
  （见 6.3）。
- **`restore()`** 无条件按快照还原宿主状态，是用户缩放、反向轴之后回到创建时刻
  的显式入口。一直使用默认 `preserve_axes_state=True` 且未改动视图时通常无需调用。

### 7.2 key 注册表（幂等更新）

```python
r1 = add_geo_axis(ax, spec=spec, key="main")
r2 = add_geo_axis(ax, spec=spec, key="main", ranks=["Era"])   # 原地 update，不叠加
assert r1 is r2
r1.remove()                                                    # key 释放
add_geo_axis(ax, spec=spec, key="main")                        # 全新轨道

from geophylo import remove_all
remove_all(ax)   # 清除该宿主上的全部轨道，返回数量
```

同一 `key` 重复调用时：若 `spec` 或 `position` 不同则抛 `CoordinateError`；
否则等价于 `update()`。注册表是一个以宿主 Axes 为键的弱引用映射，Axes 回收后自动
清理。本库不保证线程安全（与 Matplotlib 的单线程假设一致）。

---

## 8. Bio.Phylo 适配：spec_from_biophylo()

```python
from geophylo.adapter import spec_from_biophylo

spec = spec_from_biophylo(
    tree,                    # Bio.Phylo 树对象
    ax,                      # 已（或将要）绘制该树的 Axes
    time_axis="x",
    age_conversion=1.0,      # 每个 branch length 单位对应的 Ma 数；或 callable
    root_age=48.0,           # 外部时间校准给出的根年龄
    allow_unit_depth=False,  # 是否容忍等深回退
)
```

行为要点：

- **恒定产出 `mode="root_distance"` 的契约**——`Phylo.draw()` 的数据坐标就是
  累积 branch length，因此只有根距离模式能和宿主几何对齐。需要绝对年龄坐标系的
  调用方应自行构造 `CoordinateSpec`。
- **branch length 全量校验**：缺失（`None`）、NaN、负值和非有限值都会抛
  `CoordinateError`，并列出问题节点。注意：**全部缺失（None）** 才是 Bio.Phylo
  的等深回退（unit-depth fallback），此时坐标是拓扑深度而非时间，默认拒绝。显式传
  `allow_unit_depth=True` 可继续，但会发出“无时间学意义”的 `UserWarning`。NaN 和
  负值属于**数据错误**，`allow_unit_depth=True` 也不能放行。
- **根 branch length 必须为 0 或 None**：`Phylo.draw()` 与 `tree.distance()`
  会把根长度计入路径，平移“根距离 ↔ 年龄”对应。非零根长度会抛
  `CoordinateError`，消息给出两条修复路径：清零或置 None，或在距离计算中显式扣除。
- **`age_conversion` 必填**：`float`（线性比例）或 `callable(bl) -> Ma`。
  substitutions/site 一类的单位无法凭空换算成 Ma，这是语义前提而不是装饰。
- **`age_range` 从树的实际数据域推导**（不是视图范围 view limits——Bio.Phylo 会加
  约 5% 和 25% 的留白（padding））。最老叶超过 `root_age`（年龄为负）时抛
  `CoordinateError`。
- **`ax` 只用于两件事**：校验数值线性轴（log、日期和分类轴抛 `AxesTypeError`）、
  读取当前数据范围。轴对象本身不是时间语义的证据。

---

## 9. 环形时间环（实验性）：RadialSpec 与 add_geo_ring()

> 以下符号为实验性 API：接口可能调整，其测试带有 `experimental` 标记，
> `pytest -m "not experimental"` 可将其排除。

### 9.1 RadialSpec：半径编码时间，角度编码顺序

```python
import numpy as np
from geophylo import RadialSpec

radial = RadialSpec(
    age_range=(0.0, 63.0),         # (min_age, max_age)
    radius_range=(0.0, 1.0),       # (r_inner, r_outer)：内半径对应 max_age（根）
    theta_range=(0.0, 2 * np.pi),  # 树占据的角度跨度（弧度，自正 x 轴逆时针）
    root_age=63.0,                 # 需要把根距离换算成年龄时必填
)

radial.age_to_radius(63.0)   # 0.0（根在圆心）
radial.age_to_radius(0.0)    # 1.0（叶在外缘）
radial.radius_to_age(0.5)    # 31.5（严格单调的线性逆映射）
radial.band_radius((0.9, 1.0))             # 环带 → (r_inner, r_outer)
radial.band_radius((0.5, 1.0), unit="data")
```

**一致性契约（要害）**：环与树必须在**同一个** `RadialSpec` 实例下绘制——
树的每个节点用 `radial.age_to_radius(node_age)` 定位，环带用同一实例换算。
“树自己算一套半径、环另算一套”会产生静默错位，属于禁止行为。

角度跨 0 的自然输入（如 350° → 10°）按 `+2π` 展开解释；完整圆用
`abs(span − 2π) ≤ 1e-9` 容差判定。

### 9.2 add_geo_ring()

```python
from geophylo import add_geo_ring

result = add_geo_ring(
    ax,                    # 原生 Matplotlib 极坐标 Axes（fig.add_subplot(projection="polar")）
    spec=radial,           # RadialSpec
    rank="Period",         # 单个 rank（实验性限制；传序列抛 InvalidRankError）
    band=(0.9, 1.0),       # 环带占用的径向区间（参与几何计算，不只是参与校验）
    band_unit="radial_fraction",  # 或 "data"（与 radius_range 同单位）
    min_age=None, max_age=None,   # 绘制窗口；None → spec.age_range
    fill=True, alpha=1.0, label=True, label_size=5.0,
    skip=None, abbreviate=True,
    rotation=0.0,          # 标签固定旋转角
    rotate_labels=False,   # True：标签沿半径方向自动对齐（rotation 作为偏移叠加）
    key=None,              # 幂等更新
)
```

五条硬约束：

1. **只支持单一 rank**（多 rank 时间环尚无成立的布局模型）；
2. **只支持原生极坐标 Axes**（笛卡尔 Axes 抛 `AxesTypeError`；iplotx 的 radial
   布局在笛卡尔 Axes 上完成，不属于适用范围）；
3. **半径映射与树同源**：环上任意半径的年龄由
   `spec.radius_to_age(r, radius_range=spec.band_radius(band, band_unit))` 给出
   ——同一条线性映射的值域限制，实现不另立第二套映射；
4. **`band` 参与几何计算**（不只是参与校验）：`add_geo_ring()` 把 `spec.age_range`
   映射到换算后的环带 `(r_inner, r_outer)`，`max_age → r_inner`、
   `min_age → r_outer`。因此每个环段都落在环带之内，且高度恒为正（较年轻的边界给出
   较大的半径）。`min_age` 和 `max_age` 只决定**哪些区间画出来**，绝不重标环上的半径
   刻度，所以同一半径在环上与在树上对应同一个年龄。要让环与树在径向上逐点重合，就把
   环带设成树的半径范围（`band=(0.0, 1.0)`，或 `band_unit="data"` 时
   `band=radius_range`）；
5. **不修改径向视野**：从不调用 `set_rlim()`、`set_rorigin()`；换算后的环带落在
   当前 `rlim` 之外时抛 `InvalidRadiusError`（消息同时报告当前 rlim 和请求环带）。

返回值字段映射：`host_ax` 与 `geo_ax` 同为传入的极坐标 Axes；`sync()` 只重新
校验环带仍在 rlim 内；`restore()` 是空操作（环形路径从不触碰宿主状态）；
`remove()` 只移除环段 Artist，绝不删除调用方拥有的极坐标 Axes。

### 9.3 环形树配方（树由调用方绘制）

```python
import numpy as np
from io import StringIO
import matplotlib.pyplot as plt
from Bio import Phylo
from geophylo import add_geo_ring
from geophylo.adapter import radial_spec_from_biophylo

tree = Phylo.read(StringIO("((A:41.0, B:41.0):22.0, (C:35.0, D:35.0):28.0);"), "newick")
radial = radial_spec_from_biophylo(
    tree, age_conversion=1.0, root_age=63.0,
    r_inner=0.0, r_outer=1.0, theta_range=(0.0, 2 * np.pi),
)

fig = plt.figure(figsize=(8, 8))
ax = fig.add_subplot(111, projection="polar")

# 1) 画树：叶按顺序均分角域，内部节点取子节点平均角；半径一律查 spec。
leaves = tree.get_terminals()
theta = {id(leaf): radial.theta_range[0]
         + (radial.theta_range[1] - radial.theta_range[0]) * i / len(leaves)
         for i, leaf in enumerate(leaves)}
root_offset = tree.root.branch_length or 0.0
radius = {}
for clade in tree.find_clades(order="postorder"):
    age = radial.root_age - (tree.distance(clade) - root_offset)
    radius[id(clade)] = radial.age_to_radius(age)
    if clade.clades:
        theta[id(clade)] = float(np.mean([theta[id(c)] for c in clade.clades]))
for clade in tree.find_clades():
    for child in clade.clades:
        ax.plot([theta[id(clade)], theta[id(child)]],
                [radius[id(clade)], radius[id(child)]], color="black", lw=0.8)

# 2) 画环：同一 RadialSpec 实例 → 环上某半径处的年龄与树上同半径处逐点一致。
result = add_geo_ring(ax, spec=radial, rank="Period", band=(0.92, 1.0))
fig.savefig("circular_tree.png", dpi=300)
```

`radial_spec_from_biophylo()` 与线性侧共享同一套 branch length 校验
（含等深回退与非零根长度拒绝）；`r_inner` 和 `r_outer` 是调用方为树选定的半径范围，
必须显式给出。

---

## 10. iplotx 适配（实验性）

```python
import iplotx as ipx
from geophylo import spec_from_iplotx, add_geo_axis

artist = ipx.tree(tree, layout="horizontal")   # tree: ete4/Biopython/DendroPy 树
spec = spec_from_iplotx(artist, time_axis="x", age_conversion=1.0, root_age=48.0)
add_geo_axis(artist.axes, spec=spec, position="bottom")
```

- 通过 `artist.get_layout()` 读取布局数据域；`age_conversion` 作用在布局的
  根距离上（branch length 单位 → Ma）。
- 恒定产出 `mode="root_distance"`；`layout="vertical"` 时用 `time_axis="y"`。
- **显式拒绝 radial 布局**（抛 `AxesTypeError`）：iplotx 的 radial 在笛卡尔
  Axes 上绘制，与极坐标 `rlim` 没有定义好的对应关系；环形树请按第 9.3 节配方自绘。

---

## 11. pyrolite 后端（实验性）

```python
from geophylo import Timescale

ts = Timescale(backend="pyrolite")   # 需要 pip install "geophylo[pyrolite]"
ts.find_by_name("Ectasian")
```

- 只读包装 `pyrolite.util.time.Timescale` 的公开表；**不自动联网、不静默更新**。
- 版本锁定 `pyrolite>=0.3.7`（锚定 2024/12 数据与 Supereon 层级）。
- 能力受限：无稳定 ID（`get_interval()` 恒抛 `IntervalNotFoundError`）、无
  父子关系（`parent=` 不支持）、无 GSSP 和误差元数据（一律 `unknown`，
  不伪造成精确值）。
- 查询语义与内置后端**同源**（两后端都从 `geophylo.data._query` 取答案）：结构
  节点（`Supereon`、`Subepoch`、石炭纪的两个 `Sub-Period`）永不成为
  `find_by_age()` 的命中项；边界值归属以其为 `older_ma` 的较年轻区间（左闭右开）；
  `0.0 Ma` 归最年轻区间；多个 rank 同时命中时返回最具体者；
  `iter_intervals(ranks=None)` 指五个核心 rank（**不是**全部行），窗口同样带
  `1e-9` 容差；`find_by_name()` 走 `name → aliases → label` 三通道、通道内精确
  匹配优先。以上均已用 `pyrolite 0.3.7` 实测，而非静态推断。
- 内置快照仍是默认且推荐的来源（架构决策记录
  [ADR-1](adr/ADR-1-bundled-snapshots-over-pyrolite.md)）；
  pyrolite 后端仅用于交叉核对。
- 上游缺少颜色的行改用中性占位色 `#CCCCCC`，并在构造完成后用一次
  `UserWarning` 报告受影响行数：本库不会把缺失的元数据伪装成可信的 ICS 配色。

---

## 12. 异常体系与排错指南

所有公共异常继承 `geophylo.GeophyloError`。异常消息包含失败参数名、实际值和
修复建议。

| 异常 | 典型触发 | 排查建议 |
| --- | --- | --- |
| `DataValidationError` | 快照 schema、哈希、共享边界校验失败；请求未发布版本 | 检查 `available_versions()`；自定义 JSON 对照内置快照 schema；勿手改快照文件 |
| `InvalidRankError` | rank 拼写错误、`ranks` 为空或重复、给 `add_geo_ring` 传序列 | 核心 rank 为 `Eon/Era/Period/Epoch/Age`，大小写敏感 |
| `IntervalNotFoundError` | ID、名称、年龄查不到；该 rank 在该年龄无区间 | 名称查询改用 `find_by_name()`；年龄超出快照覆盖范围属正常拒绝 |
| `AmbiguousIntervalError` | 名称命中多个候选（如 `"Upper"`） | 加 `rank=` 或 `parent=` 消歧，或查看 `exc.candidates` 用 ID 精确查询 |
| `InvalidRangeError` | `min_age >= max_age`、负年龄、NaN、`thickness_ratio` 越界、`tick_max_count < 1`、轨道空间不足 | 按消息中的合法域修正参数 |
| `InvalidRadiusError` | `band` 倒置或越界；环带超出当前 `rlim` | 调整 `band`，或先 `ax.set_rlim()` 扩大视野 |
| `AxesTypeError` | log、日期和分类轴；非极坐标 Axes 传给 `add_geo_ring`；iplotx radial 布局 | 使用线性数值轴或原生极坐标轴 |
| `CoordinateError` | `position` 与 `spec.time_axis` 冲突；`root_age` 缺失或多余；未确认的推断；`age_to_data` 域外输入 | 按消息修正 `CoordinateSpec` 或参数配对 |

**捕获顺序要注意**：`AmbiguousIntervalError` 是 `IntervalNotFoundError` 的**子类**
（为兼容只捕获“查不到”的用户代码而保留），所以 `except IntervalNotFoundError`
会把“命中多个”一起吞掉。两类需要不同处理时，请把
`except AmbiguousIntervalError` 放在**前面**。

**通用排查清单**：

1. 报 `CoordinateError: position 与 spec.time_axis 冲突` → `bottom`、`top` 配
   `"x"`，`left`、`right` 配 `"y"`；
2. 条带看起来空白 → 检查绘制窗口 `min_age` 和 `max_age` 是否与数据范围相交；
   检查宿主轴是否反向（不影响正确性，只影响方向）；
3. `InvalidRangeError: thickness_ratio 不足以容纳 N 条轨道` → 减少 rank 数、
   增大 `thickness_ratio` 或加大图幅；
4. 标签隐藏过多 → 先增大 `thickness_ratio`；调整 `label_size` 改善可读性后仍拥挤
   时，用 `skip=` 手动跳过次要区间，或分成两条轨道显示；
5. 树和条带未对齐 → 确认条带使用的是 `spec_from_biophylo()`（根距离模式）产出的
   `spec`，且根 `branch_length` 已清零。

---

## 13. 常见问题 FAQ

**Q1：`add_geo_axis()` 会不会移动调用方的数据点，或改变坐标范围？**
不会。轨道在 inset Axes 上，宿主的 limits、scale、autoscale 和 `dataLim`
逐字段不变（有测试逐项断言）。这也是本库不提供“外部条带自动腾位”的原因。
需要外部空间时，请自行用 `constrained_layout` 或子图预留。

**Q2：为什么不能只传 `position="bottom"` 让库自己判断坐标？**
因为同一个轴可能对应两种科学含义（Ma 或根距离），猜错就是科学错误。
本库要求 `spec` 显式声明。确需从 Axes 推断时，也要通过
`CoordinateSpec.from_data_limits(..., acknowledge_inference=True)` 显式确认。

**Q3：轴反向（`invert_xaxis()`）需要特殊处理吗？**
不需要。`age_to_data()` 是纯函数，反向只改变显示方向，条带数据坐标不变。
这正是真值表（4.4 节）八行情形统一的原因。

**Q4：`age_range` 与 `min_age`、`max_age` 有什么区别？**
`age_range` 是坐标语义范围（换算合法性域），`min_age` 和 `max_age` 是本次绘制
窗口（裁剪边界）。想只画 0 Ma～66 Ma 的条带而宿主轴覆盖更宽时，`spec.age_range`
保持与轴一致，用 `min_age=0, max_age=66` 控制裁剪。

**Q5：`Timescale` 的数据会自动更新吗？**
不会。快照随包分发、只增不改。本库会把新版 ICS 数据作为**新版本快照**发布，
`Timescale(version=...)` 显式切换。这保证每张出图多年后仍可复现。

**Q6：可以叠加多条时间条带吗？**
可以。`ranks=["Period", "Epoch"]` 一次画两条；或用不同 `position` 叠加
（如 `bottom` 一条、`left` 一条）。带相同 `key` 的调用是幂等更新而非叠加。

**Q7：标签文字能换颜色或旋转吗？**
`label_color="auto"`（默认）按合成背景自动选黑或白，也可以指定任意颜色名或
十六进制值。`rotation` 给定固定角度；轨道方向（垂直轨道）会自动加 90° 基准角。

**Q8：环形树为什么要调用方自己画？**
角度编码的是分类单元顺序，属于树布局的职责，本库不推断拓扑到角度的映射。
第 9.3 节的配方大约 30 行即可完成，且保证与时间环共用同一半径映射。

**Q9：iplotx 适配和环形功能稳定吗？**
它们是实验性符号（`experimental`）：有完整测试但不承诺 API 冻结。
`spec_from_biophylo()` + `add_geo_axis()` 属于稳定 API 路径。

**Q10：如何复现库的示例图？**
见仓库 `examples/`：每个示例脚本的边界数值和颜色都从内置快照动态读取，无手写
数值；按示例自带的输出路径与 `dpi` 重跑即可复现同一张图。

**Q11：为什么白垩系底界是 143.1 Ma（贝里阿斯顶界 137.05 Ma），而不是常引用的
GTS2012 值 145.0 和 139.8？**
本快照的这两个数值取自 ICS 图表版本携带的 **GTS2020 时间校准**（上游锁定输入
pinned TTL 文件中相应界线节点的 `rdfs:isDefinedBy ts:gts2020`），不是抄录错误。
145.0 和 139.8 是 GTS2012 的校准值，两者本就不该混用。与旧表对照读图时，请在图注中
写明来源：本库图上的数字全部来自随包快照的 `chart_version`（可用
`Timescale().metadata.data_version` 复核）。

**Q12：为什么快照最老只到 4567 Ma，而不是多数时间标尺用的 4600？**
冥古宙和前寒武系的底界在上游 TTL 中就是 4567.0 Ma（原文描述 `A time period from
4567 to 4031 million years ago`），本库不修改上游数值。若坐标轴需要以 4600 作为
标尺起点，显式声明
`CoordinateSpec.absolute(time_axis="x", age_range=(0.0, 4600.0))` 并配
`max_age=4600.0` 即可。4567 和 4600 之间会留下一段没有色块的区间，这是“上游未给出
的单元一律不伪造”的直接结果，请在图注中说明。

**Q13：石炭纪的密西西比亚统和宾夕法尼亚亚统归为结构节点，怎么画出这个两分？**
ICS 图表把它们放在 `Sub-Period` 一层，本库按 ADR-5 将该层归为结构节点。它们不进入
`Timescale.ranks`，也不进入 `find_by_age()`、`iter_intervals()` 的默认池，
`ranks=["Sub-Period"]` 抛 `InvalidRankError`。可以绘制的是快照**确实携带**的下一级，
即六个世（Epoch）行：Lower、Middle 和 Upper Mississippian（358.86 至 323.4 Ma），
以及 Lower、Middle 和 Upper Pennsylvanian（323.4 至 298.9 Ma）。例如在石炭纪窗口上
叠加世级轨道：

```python
add_geo_axis(ax, spec=spec, position="bottom", ranks=["Period", "Epoch"],
             min_age=298.9, max_age=358.86)
```

世级轨道即给出密西西比和宾夕法尼亚的两分及其细分。注意这六个世的图面缩写会因
缩写闸门（见 6.2 节）回退全名，因为它们的别名是复合 `ccgmShortCode`。
`find_by_name("Mississippian")` 按设计抛 `AmbiguousIntervalError`（三个世级候选），
请用 `rank=` 或 `parent=` 消歧，或直接用 ID（如
`ics:epoch:lower-mississippian`）。

**Q14：`"Ma"` 单位标签出现在彩色条带外面，这是定位错误吗？**
不是，这是有意的锚定规则。标签钉在**窗口的较老一端**，并按显示像素向外偏移一段
间隙（`geophylo/render/linear.py` 的 `_draw_unit_label()`），因此不会和最老端的刻度
数字相撞。

标签落在画布的哪里取决于宿主轴。若宿主轴在窗口较老一端之外还有余量（默认的
`ax.set_xlim(0, 300)` 会带 5% 边距），标签出现在轨道外框之内、靠近边缘处；若窗口
较老一端恰好是轨道边缘（`ax.set_xlim(300, 0)`，无边距），标签落在轨道之外的页边
空白里（`clip_on=False`）。标签不会被轨道裁掉。想换位置时自行标注：从快照读出
较老端的年龄，自行给轴写单位。

---

## 14. 示例脚本索引

| 脚本 | 内容 |
| --- | --- |
| `examples/bio_phylo_timetree.py` | Bio.Phylo 时间树 + Period、Epoch 条带（主用例） |
| `examples/stratigraphic_column.py` | 不画树的地层柱风格用法（`CoordinateSpec.absolute`） |
| `examples/circular_tree.py` | 环形树配方 + 极坐标时间环（实验性） |
| `examples/iplotx_timetree.py` | iplotx `TreeArtist` 适配（实验性，需 `geophylo[iplotx]`） |

运行任意示例：

```bash
python examples/bio_phylo_timetree.py
```

示例统一遵循 `add_geo_axis() → tight_layout() → finalize() → savefig()` 顺序，
并在 Agg 后端下可直接运行（输出 PNG 与脚本同目录）。

---

## 15. 数据来源、许可和引用

- **代码**：MIT（见 `LICENSE`）。
- **ICS 快照数据**：由 `tools/build_snapshot.py` 从 ICS 官方版本化数据
  确定性生成，CC-BY-4.0 发布（见 `LICENSES/CC-BY-4.0.txt` 与 `NOTICE`）。
  数据来源、快照更新和回退政策见 `docs/data-policy.md`。
- **机器可读的出处**：`tools/build-logs/` 内的逐快照生成日志、
  `geophylo/data/snapshots/diff-2024-12_to_2026-06.json` 版本间逐字段 diff
  （由 `tools/make_diff.py` 或 `build_snapshot.py --diff-with` 生成），以及
  `versions.json` 中 2024/12 条目的 `derived_from` 字段；说明见
  `geophylo/data/snapshots/PROVENANCE.md`。
- **设计决策**：[`docs/adr/`](adr/README.md) 下的架构决策记录（ADR-1～ADR-5）
  写明各处的非显然选择和已否决的替代方案。
- **引用**：使用本库请引用 GeoPhylo（`CITATION.cff`），并按 `NOTICE` 要求
  同时引用《国际年代地层表》。

术语约定（全文一致）：`older_ma` 和 `younger_ma` 分别是区间较老边界、较年轻
边界的 Ma 值（`older_ma > younger_ma`）；“轨道”指承载一条 rank 色带的 inset
Axes；“绘制窗口”指 `min_age` 和 `max_age` 指定的裁剪范围。

---

*本文档与代码同步维护；若与代码注释所引用的规范条目冲突，以
[`docs/spec/README.md`](spec/README.md) 索引与本仓库代码为准——仓库之外不存在
需要查阅的“开发文档”。*

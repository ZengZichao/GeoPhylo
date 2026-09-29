"""性能测试（开发文档 7.6 / 1.5 验收 8）。

口径：把一次完整的"从 Bio.Phylo 树到地质条带"拆成两段分别计时——

* ``T_render``  = ``add_geo_axis()``，本库的绘制路径；
* ``T_adapter`` = ``spec_from_biophylo()``，本库遍历宿主树的适配路径。

同机、Agg 后端、同快照、同 rank 配置。

测量方法
--------
四个约束决定了这里的写法：

1. **计时对象必须与断言命题匹配。** 只计 ``add_geo_axis()`` 不够：它**根本看不到树**
   （只拿 ``spec``），所以"开销与叶节点数无关"对它几乎恒真；真正随叶数增长的是
   ``spec_from_biophylo()``（递归遍历 clade）——``_scan_tree()`` 若写成平方复杂度，
   只计绘制路径的测试仍会全绿。因此两段分别计时、分别断言。
2. **宿主树不在计时循环里重绘。** ``add_geo_axis()`` 不触碰宿主的树 Artist；重绘
   reps+1 次会让这条 advisory 测试吃掉整个套件约 63% 的墙钟（341.4s），却不为断言
   贡献信号。宿主时间范围由 ``_host_xlim()`` 从树的根距离推导，而该推导与
   ``Phylo.draw()`` 的真实结果**逐位相等**（由 ``test_host_xlim_matches_phylo_draw``
   用真实绘制守住）。
3. **断言形式要匹配真实标度。** 以 ``reps=3`` 的中位数直接要求 ``max/min <= 2.0``
   属于错规格的断言，不是库的性能缺陷。实测（本机、独占、reps=9、3 轮）：

   ======  ==========  ==========  =========
   叶节点   T_render    T_adapter   两段合计
   ======  ==========  ==========  =========
   100      ~4.7 ms      ~0.11 ms    ~4.8 ms
   1 000    ~4.8 ms      ~0.87 ms    ~5.7 ms
   10 000   ~5.7 ms     ~10.0 ms     ~15.7 ms
   ======  ==========  ==========  =========

   即 **T_render 平坦、T_adapter 线性（约 1.0 µs/叶，指数 α≈0.97）**。合计在
   100 → 10 000 之间的极差比约 2.6–3.0，而 MAD 只有 0.0002 s，所以这个差异
   **不是噪声，是真实的线性增长**。``ratio <= 2.0`` 这条"绝对平坦"断言在 100 倍
   叶数跨度上对任何非零线性项都不可能成立。
4. **样本量要够**：``reps=3`` 的中位数不稳定，故取 ``reps=9``。

三条判据各自有物理含义：

* **判据 A（绘制路径平坦）**：``T_render`` 三档极差比 ≤ ``MAX_RENDER_RATIO``，
  且仅在极差超出噪声带时判定。这才是「本库绘制开销与叶节点数无关」这条主张应有的
  守卫。
* **判据 B（适配路径不超线性）**：``T_adapter`` 每叶边际成本 ≤
  ``MAX_ADAPTER_US_PER_LEAF``。当前约 1.0 µs/叶，上限留 5× 余量；若遍历退化成
  平方复杂度，边际成本会跳到 ~100 µs/叶量级而被抓住。线性是该遍历的下界
  （每个 clade 至少访问一次），所以这里约束的是"不得超线性"，而非"必须平坦"。
* **判据 C（绝对上限）**：两段合计最大档 ≤ ``TOTAL_CEILING_S``。与噪声无关，
  防住"斜率不大但绝对量已不可用"的退化。

文档表述建议：写成「绘制开销与叶节点数无关；自树构造坐标契约的开销随叶数线性、
约 1 µs/叶」，不要写成笼统的「开销与叶节点数无关」。
"""

from __future__ import annotations

import io
import statistics
import time
from typing import NamedTuple

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import pytest
from Bio import Phylo

from geophylo import CoordinateSpec, add_geo_axis

pytestmark = [pytest.mark.performance]

#: 判据 A：绘制路径（``add_geo_axis``）三档极差比上限。守护"绘制开销与叶数无关"，勿放宽。
MAX_RENDER_RATIO = 2.0

#: 判据 B：适配路径（``spec_from_biophylo``）每叶边际成本上限（微秒）。当前实测约 1.0。
MAX_ADAPTER_US_PER_LEAF = 5.0

#: 判据 C：两段合计最大档的绝对上限（秒）。当前约 0.016 s，留约 3× 余量。
TOTAL_CEILING_S = 0.050

#: 极差需超过噪声带（各档 MAD 最大值的该倍数）才启用比例判据，避免拿噪声当信号。
NOISE_SIGMA = 3.0

LEAF_BUCKETS = (100, 1000, 10000)

#: Bio.Phylo 绘制时对数据坐标域的取景留白（见 ``adapter/biopython.py`` 的 docstring，
#: 亦由 ``test_host_xlim_matches_phylo_draw`` 用真实绘制逐位核对）。
PHYLO_VIEW_PAD_LEFT = 0.05
PHYLO_VIEW_PAD_RIGHT = 1.25


def _balanced_newick(n_leaves: int) -> str:
    """生成 n 叶完全二叉树的 Newick（branch length 恒 0.1，树深决定根距离）。"""
    clusters: list[str] = [f"L{i}:0.1" for i in range(n_leaves)]
    while len(clusters) > 1:
        pairs = [f"({a},{b}):0.1" for a, b in zip(clusters[::2], clusters[1::2], strict=False)]
        if len(clusters) % 2 == 1:
            pairs.append(clusters[-1])
        clusters = pairs
    return clusters[0] + ";"


def _max_root_distance(tree) -> float:
    """树的最大根距离（叶节点到根的距离上界）。单次遍历，10k 叶约 2 ms。"""
    depths = tree.root.depths()
    return max(value for clade, value in depths.items() if clade.is_terminal())


def _host_xlim(tree) -> tuple[float, float]:
    """复现 ``Phylo.draw()`` 会给宿主 Axes 设置的 xlim，而无需真的绘制树。

    ``add_geo_axis()`` 会把 ``host.get_xlim()`` 数值复制给地质轴，从而决定可见区间数，
    所以这个范围必须与真实绘制一致，否则测的就不是同一条路径。一致性由
    ``test_host_xlim_matches_phylo_draw`` 用一次真实的 ``Phylo.draw()`` 守住。
    """
    xmax = _max_root_distance(tree)
    return (-PHYLO_VIEW_PAD_LEFT * xmax, PHYLO_VIEW_PAD_RIGHT * xmax)


class BucketTiming(NamedTuple):
    """一个叶数档的测量结果（均为"一次完整调用"的秒数）。"""

    median_render: float
    render_samples: list[float]
    median_adapter: float
    adapter_samples: list[float]


def _mad(samples: list[float]) -> float:
    center = statistics.median(samples)
    return statistics.median([abs(x - center) for x in samples]) or 1e-6


def _measure(n_leaves: int, *, reps: int = 9) -> BucketTiming:
    """分别测出本库绘制路径与适配路径的耗时样本。

    每轮用新建的空白宿主 Axes（并设置与真实绘制一致的 ``xlim``），以免多条轨道累积在
    同一轴上污染样本。首个样本被导入 / 字体缓存主导（这是墙钟断言抖动的主要
    来源），所以每档多跑一次并不计入统计。原始样本一并返回，失败信息里可直接复核。
    """
    from geophylo.adapter import spec_from_biophylo

    tree = Phylo.read(io.StringIO(_balanced_newick(n_leaves)), "newick")
    tree.root.branch_length = None  # 4.10：根基线必须为零
    host_xlim = _host_xlim(tree)

    render_times: list[float] = []
    adapter_times: list[float] = []
    for _ in range(reps + 1):  # 第 0 次是热身，不进入统计
        fig, ax = plt.subplots(figsize=(8, 6))
        ax.set_xlim(*host_xlim)
        start = time.perf_counter()
        spec = spec_from_biophylo(tree, ax, time_axis="x", age_conversion=1.0, root_age=6.0)
        adapter_times.append(time.perf_counter() - start)
        start = time.perf_counter()
        add_geo_axis(ax, spec=spec, position="bottom", ranks=["Period"])
        render_times.append(time.perf_counter() - start)
        plt.close(fig)

    render_samples = render_times[1:]  # 丢掉热身样本
    adapter_samples = adapter_times[1:]
    return BucketTiming(
        median_render=statistics.median(render_samples),
        render_samples=render_samples,
        median_adapter=statistics.median(adapter_samples),
        adapter_samples=adapter_samples,
    )


def _fmt(values: dict[int, float]) -> str:
    return "{" + ", ".join(f"{k}: {v:.6f}" for k, v in sorted(values.items())) + "}"


def test_host_xlim_matches_phylo_draw() -> None:
    """``_host_xlim()`` 的推导必须与一次真实的 ``Phylo.draw()`` 取景一致。

    本模块用推导值取代了真实绘制（否则 10k 叶单帧绘制就要约 69 s，一条 advisory
    测试会吃掉整个套件一半以上的墙钟）。这个替代只有在取景等价时才是无损的，
    所以用最小档做一次真实绘制来核对——它本身就是回归守卫。
    """
    for n_leaves in (100, 1000):
        tree = Phylo.read(io.StringIO(_balanced_newick(n_leaves)), "newick")
        tree.root.branch_length = None
        expected = _host_xlim(tree)
        fig, ax = plt.subplots(figsize=(8, 6))
        try:
            Phylo.draw(tree, axes=ax, do_show=False)
            actual = tuple(float(v) for v in ax.get_xlim())
        finally:
            plt.close(fig)
        assert actual == pytest.approx(expected, abs=1e-9), (
            f"n={n_leaves}：推导的宿主取景 {expected} 与 Phylo.draw 实际 {actual} 不一致；"
            f"若 Bio.Phylo 的留白规则变了，需同步 _host_xlim()。"
        )


def test_add_geo_axis_cost_independent_of_leaf_count() -> None:
    """绘制路径必须与叶节点数无关（判据 A），且总开销不超线性 / 不超绝对上限（B、C）。"""
    render: dict[int, float] = {}
    adapter: dict[int, float] = {}
    render_mads: dict[int, float] = {}
    samples: dict[int, list[float]] = {}
    for n_leaves in LEAF_BUCKETS:
        timing = _measure(n_leaves)
        render[n_leaves] = max(timing.median_render, 1e-6)
        adapter[n_leaves] = max(timing.median_adapter, 1e-6)
        render_mads[n_leaves] = _mad(timing.render_samples)
        samples[n_leaves] = timing.render_samples

    hi = max(render, key=render.get)
    lo = min(render, key=render.get)
    exceed = render[hi] - render[lo]
    noise_floor = NOISE_SIGMA * max(render_mads.values())
    detail = (
        f"T_render（秒）={_fmt(render)}；T_adapter（秒）={_fmt(adapter)}；"
        f"绘制噪声带 MAD={_fmt(render_mads)}；极差 {exceed:.6f}s vs 噪声门槛 {noise_floor:.6f}s；"
        f"绘制原始样本={samples}"
    )

    # 判据 A（抗噪）：只有当极差明显超出噪声带时，才判定绘制路径真的随叶数增长。
    if exceed > noise_floor:
        ratio = render[hi] / render[lo]
        assert ratio <= MAX_RENDER_RATIO, (
            f"绘制开销随叶数增长：T_render ratio {ratio:.2f}x 超过 {MAX_RENDER_RATIO}x；{detail}"
        )

    # 判据 B：适配路径每叶边际成本不得超线性。
    n_hi, n_lo = max(LEAF_BUCKETS), min(LEAF_BUCKETS)
    us_per_leaf = (adapter[n_hi] - adapter[n_lo]) * 1e6 / (n_hi - n_lo)
    assert us_per_leaf <= MAX_ADAPTER_US_PER_LEAF, (
        f"适配路径每叶边际成本 {us_per_leaf:.2f} µs 超过 {MAX_ADAPTER_US_PER_LEAF} µs"
        f"（疑似超线性退化）；{detail}"
    )

    # 判据 C：合计最大档的绝对上限，与噪声无关。
    total_worst = max(render[k] + adapter[k] for k in LEAF_BUCKETS)
    assert total_worst <= TOTAL_CEILING_S, (
        f"最大档合计增量 {total_worst:.5f}s 超过绝对上限 {TOTAL_CEILING_S}s；{detail}"
    )


def test_interval_count_scaling_near_linear():
    def measure_axis_only(window_max: float, reps: int = 3) -> float:
        times: list[float] = []
        for rep in range(reps + 1):  # 第 0 次热身：首次渲染要建字体/缓存，是主要噪声源
            fig, ax = plt.subplots(figsize=(8, 6))
            ax.set_xlim(window_max, 0)
            spec = CoordinateSpec.absolute(time_axis="x", age_range=(0.0, window_max))
            start = time.perf_counter()
            add_geo_axis(ax, spec=spec, position="bottom", ranks=["Period", "Epoch"])
            ax.figure.canvas.draw()
            elapsed = time.perf_counter() - start
            plt.close(fig)
            if rep == 0:
                continue
            times.append(elapsed)
        return statistics.median(times)

    t_small = measure_axis_only(10.0)  # 区间数量少
    t_large = measure_axis_only(541.0)  # 区间数量多
    ratio = t_large / max(t_small, 1e-6)
    # 近似线性断言：窗口扩大 ~54 倍（可绘区间数量级增加）时耗时增长远小于
    # 二次方；以 20 倍为宽容上限防抖。
    assert ratio <= 20.0, (
        f"区间数量扩展耗时比 {ratio:.1f}x 偏离线性（t_small={t_small:.4f}s t_large={t_large:.4f}s）"
    )

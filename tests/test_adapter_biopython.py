"""Bio.Phylo 适配器集成测试（开发文档 4.10/6.1/7.3）。"""

from __future__ import annotations

from io import StringIO

import matplotlib.pyplot as plt
import pytest
from Bio import Phylo

from geophylo import AxesTypeError, CoordinateError, add_geo_axis
from geophylo.adapter import spec_from_biophylo

SIMPLE = "((A:41.0, B:41.0):22.0, (C:35.0, D:35.0):28.0);"  # 最大根距离 63


@pytest.fixture()
def tree():
    return Phylo.read(StringIO(SIMPLE), "newick")


@pytest.fixture()
def drawn_ax(tree):
    fig, ax = plt.subplots(figsize=(10, 6))
    Phylo.draw(tree, axes=ax, do_show=False)
    return fig, ax


class TestSpecFromBiophylo:
    def test_basic_root_distance_semantics(self, drawn_ax, tree):
        _fig, ax = drawn_ax
        spec = spec_from_biophylo(tree, ax, time_axis="x", age_conversion=1.0, root_age=63.0)
        assert spec.mode == "root_distance"  # 恒定 root_distance（4.10）
        assert spec.root_age == 63.0
        assert spec.age_range == pytest.approx((0.0, 63.0))  # 来自树的数据域

    def test_age_conversion_callable(self, drawn_ax, tree):
        _fig, ax = drawn_ax
        spec = spec_from_biophylo(
            tree, ax, time_axis="x", age_conversion=lambda bl: bl * 2.0, root_age=126.0
        )
        assert spec.age_range == pytest.approx((0.0, 126.0))

    def test_xlim_padding_ignored(self, drawn_ax, tree):
        # 范围推导用树的实际数据域，而不是 view limits（Bio.Phylo 会加 padding）。
        _fig, ax = drawn_ax
        left, right = ax.get_xlim()
        assert right - left > 63  # padding 存在
        spec = spec_from_biophylo(tree, ax, time_axis="x", age_conversion=1.0, root_age=63.0)
        assert spec.age_range == pytest.approx((0.0, 63.0))

    def test_non_ultrametric_tree_not_misjudged(self, tree):
        # 叶节点不等深：只要 branch length 齐全就合法。
        tree = Phylo.read(StringIO("((A:10.0, B:40.0):22.0, C:62.0);"), "newick")
        fig, ax = plt.subplots(figsize=(8, 5))
        spec = spec_from_biophylo(tree, ax, time_axis="x", age_conversion=1.0, root_age=62.0)
        assert spec.age_range == pytest.approx((0.0, 62.0))
        plt.close(fig)

    def test_missing_branch_length_rejected_with_node_list(self, tree):
        # 根之外至少两个节点缺 branch length，错误消息必须把问题节点列全。
        for clade in tree.find_clades():
            if clade is not tree.root and clade.name in ("A", "C"):
                clade.branch_length = None
        fig, ax = plt.subplots(figsize=(8, 5))
        with pytest.raises(CoordinateError, match="问题节点"):
            spec_from_biophylo(tree, ax, time_axis="x", age_conversion=1.0, root_age=63.0)
        plt.close(fig)

    def test_negative_branch_length_rejected(self, tree):
        for clade in tree.find_clades():
            if clade.name == "A":
                clade.branch_length = -1.0
        fig, ax = plt.subplots(figsize=(8, 5))
        with pytest.raises(CoordinateError, match="负"):
            spec_from_biophylo(tree, ax, time_axis="x", age_conversion=1.0, root_age=63.0)
        plt.close(fig)

    def test_unit_depth_fallback_rejected_by_default(self, tree):
        for clade in tree.find_clades():
            if clade is not tree.root:
                clade.branch_length = None
        fig, ax = plt.subplots(figsize=(8, 5))
        with pytest.raises(CoordinateError, match="等深回退"):
            spec_from_biophylo(tree, ax, time_axis="x", age_conversion=1.0, root_age=4.0)
        plt.close(fig)

    def test_unit_depth_allowed_warns_not_time(self, tree):
        for clade in tree.find_clades():
            if clade is not tree.root:
                clade.branch_length = None
        fig, ax = plt.subplots(figsize=(8, 5))
        with pytest.warns(UserWarning, match="不是时间单位"):
            spec = spec_from_biophylo(
                tree, ax, time_axis="x", age_conversion=1.0, root_age=4.0, allow_unit_depth=True
            )
        assert spec.age_range[0] >= 0
        plt.close(fig)

    def test_all_nan_branch_lengths_not_unit_depth(self, tree):
        # 等深回退只指「全部缺失（None）」；全 NaN 是数据错误，即使
        # allow_unit_depth=True 也必须报 CoordinateError，不得静默容忍。
        import math

        for clade in tree.find_clades():
            if clade is not tree.root:
                clade.branch_length = math.nan
        fig, ax = plt.subplots(figsize=(8, 5))
        with pytest.raises(CoordinateError, match="非有限"):
            spec_from_biophylo(
                tree, ax, time_axis="x", age_conversion=1.0, root_age=4.0, allow_unit_depth=True
            )
        plt.close(fig)

    def test_partial_nan_with_missing_rejected(self, tree):
        # 部分缺失 + 部分非法：既不是等深回退，也不是合法数据 → 报错。
        import math

        for clade in tree.find_clades():
            if clade is not tree.root:
                clade.branch_length = None
        for clade in tree.find_clades():
            if clade.name == "A":
                clade.branch_length = math.nan
        fig, ax = plt.subplots(figsize=(8, 5))
        with pytest.raises(CoordinateError, match="问题节点"):
            spec_from_biophylo(tree, ax, time_axis="x", age_conversion=1.0, root_age=63.0)
        plt.close(fig)

    def test_non_numeric_root_branch_length_rejected_as_public_error(self, tree):
        # 非数值的根 branch_length 不得以原始 ValueError/TypeError 冒泡（4.7）。
        tree.root.branch_length = "long"
        fig, ax = plt.subplots(figsize=(8, 5))
        with pytest.raises(CoordinateError):
            spec_from_biophylo(tree, ax, time_axis="x", age_conversion=1.0, root_age=63.0)
        plt.close(fig)

    def test_nonzero_root_branch_length_rejected(self, tree):
        tree.root.branch_length = 7.0
        fig, ax = plt.subplots(figsize=(8, 5))
        with pytest.raises(CoordinateError, match="两条修复路径"):
            spec_from_biophylo(tree, ax, time_axis="x", age_conversion=1.0, root_age=63.0)
        plt.close(fig)

    def test_zero_root_branch_length_allowed(self, tree):
        tree.root.branch_length = 0.0
        fig, ax = plt.subplots(figsize=(8, 5))
        spec = spec_from_biophylo(tree, ax, time_axis="x", age_conversion=1.0, root_age=63.0)
        assert spec.age_range == pytest.approx((0.0, 63.0))
        plt.close(fig)

    def test_missing_age_conversion_rejected(self, drawn_ax, tree):
        _fig, ax = drawn_ax
        # age_conversion 是语义前提：作为必填关键字参数在签名层强制。
        with pytest.raises(TypeError, match="age_conversion"):
            spec_from_biophylo(tree, ax, time_axis="x", root_age=63.0)  # type: ignore[call-arg]

    def test_bad_age_conversion_rejected(self, drawn_ax, tree):
        _fig, ax = drawn_ax
        with pytest.raises(CoordinateError):
            spec_from_biophylo(tree, ax, time_axis="x", age_conversion=-1.0, root_age=63.0)

    def test_root_age_too_small_rejected(self, drawn_ax, tree):
        _fig, ax = drawn_ax
        with pytest.raises(CoordinateError, match="root_age"):
            spec_from_biophylo(tree, ax, time_axis="x", age_conversion=1.0, root_age=10.0)

    def test_log_axis_rejected(self, tree):
        fig, ax = plt.subplots(figsize=(8, 5))
        ax.set_xscale("log")
        with pytest.raises(AxesTypeError):
            spec_from_biophylo(tree, ax, time_axis="x", age_conversion=1.0, root_age=63.0)
        plt.close(fig)

    def test_bad_time_axis_rejected(self, drawn_ax, tree):
        _fig, ax = drawn_ax
        with pytest.raises(CoordinateError):
            spec_from_biophylo(tree, ax, time_axis="z", age_conversion=1.0, root_age=63.0)  # type: ignore[arg-type]


class TestEndToEnd:
    def test_tree_plus_axis_integration(self, drawn_ax, tree):
        _fig, ax = drawn_ax
        spec = spec_from_biophylo(tree, ax, time_axis="x", age_conversion=1.0, root_age=63.0)
        result = add_geo_axis(ax, spec=spec, position="bottom", ranks=["Period", "Epoch"])
        fig = ax.figure
        fig.canvas.draw()
        # patch 几何断言：色块必须整体落在树的根距离坐标系（spec 声明的数据域）
        # 内。这是 add_geo_axis 几何路径上唯一的有效 patch 断言，必须保持为真正的
        # 合取——`or True` 之类的尾巴会让它恒真失效；ruff 的 SIM222 正守着这一类
        # 短路写法。
        rects = [a for a in result.artists if type(a).__name__ == "Rectangle"]
        assert rects
        data_lo = min(spec.age_to_data(spec.age_range[0]), spec.age_to_data(spec.age_range[1]))
        data_hi = max(spec.age_to_data(spec.age_range[0]), spec.age_to_data(spec.age_range[1]))
        for rect in rects:
            left, right = sorted((float(rect.get_x()), float(rect.get_x() + rect.get_width())))
            assert left >= data_lo - 1e-9, f"色块左界 {left} 越出数据域下界 {data_lo}"
            assert right <= data_hi + 1e-9, f"色块右界 {right} 越出数据域上界 {data_hi}"
            assert right > left - 1e-9, "色块宽度为负"
        host_xlim = ax.get_xlim()
        for rect in rects:
            assert min(rect.get_x(), rect.get_x() + rect.get_width()) >= min(host_xlim) - 1e-6

"""极坐标时间环测试（开发文档 4.8/5.3/6.3，experimental marker）。"""

from __future__ import annotations

import math
from io import StringIO

import matplotlib.pyplot as plt
import numpy as np
import pytest
from Bio import Phylo

from geophylo import (
    AxesTypeError,
    CoordinateError,
    GeoAxisResult,
    InvalidRadiusError,
    InvalidRankError,
    Timescale,
    add_geo_ring,
)
from geophylo.adapter import radial_spec_from_biophylo
from geophylo.coordinate.radial import RadialSpec

pytestmark = [pytest.mark.experimental]

NEWICK = "((A:41.0, B:41.0):22.0, (C:35.0, D:35.0):28.0);"


def _rectangles(artists):
    """环段 Artist（``result.artists`` 里同时有 Text 标签）。"""
    return [a for a in artists if type(a).__name__ == "Rectangle"]


def _radial_extents(patches):
    """每个环段的 ``(bottom, top)``；顺带断言 height 恒为正（半径倒置回归）。"""
    spans = []
    for patch in patches:
        bottom, height = float(patch.get_y()), float(patch.get_height())
        assert height > 0.0, f"环段 height 必须为正，得到 {height!r}（半径倒置回归）"
        spans.append((bottom, bottom + height))
    return spans


@pytest.fixture()
def polar_ax():
    fig = plt.figure(figsize=(8, 8))
    ax = fig.add_subplot(111, projection="polar")
    return fig, ax


@pytest.fixture()
def radial(polar_ax):
    return radial_spec_from_biophylo(
        Phylo.read(StringIO(NEWICK), "newick"),
        age_conversion=1.0,
        root_age=63.0,
        r_inner=0.0,
        r_outer=1.0,
        theta_range=(0.0, 2 * np.pi),
    )


class TestInputValidation:
    def test_non_polar_axes_rejected(self):
        fig, ax = plt.subplots(figsize=(6, 4))
        spec = RadialSpec(age_range=(0.0, 63.0), radius_range=(0.0, 1.0), theta_range=(0.0, 1.0))
        with pytest.raises(AxesTypeError, match="极坐标"):
            add_geo_ring(ax, spec=spec, rank="Period")
        plt.close(fig)

    def test_multi_rank_rejected_with_note(self, polar_ax, radial):
        _fig, ax = polar_ax
        with pytest.raises(InvalidRankError, match="单一 rank"):
            add_geo_ring(ax, spec=radial, rank=["Period", "Epoch"])  # type: ignore[arg-type]

    def test_result_field_mapping(self, polar_ax, radial):
        _fig, ax = polar_ax
        result = add_geo_ring(ax, spec=radial, rank="Period")
        # host_ax 与 geo_ax 同为传入的极坐标 Axes（4.8 返回值字段映射）。
        assert result.host_ax is ax and result.geo_ax is ax
        assert isinstance(result, GeoAxisResult)

    def test_band_outside_rlim_rejected_and_reported(self, polar_ax, radial):
        _fig, ax = polar_ax
        ax.set_rlim(0.0, 0.5)  # 用户已把视野缩到 0.5
        rlim_before = ax.get_ylim()
        with pytest.raises(InvalidRadiusError) as excinfo:
            add_geo_ring(ax, spec=radial, rank="Period", band=(0.92, 1.0))
        message = str(excinfo.value)
        assert "rlim" in message and "0.5" in message and "1.0" in message
        assert ax.get_ylim() == rlim_before  # 视野不被修改

    def test_band_data_unit(self, polar_ax, radial):
        _fig, ax = polar_ax
        result = add_geo_ring(ax, spec=radial, rank="Period", band=(0.9, 1.0), band_unit="data")
        assert result.artists


class TestRingGeometry:
    def test_full_theta_coverage_per_interval(self, polar_ax, radial):
        # 每个地质时间区间在角度上覆盖完整 theta_range（不按年龄缩窄）。
        _fig, ax = polar_ax
        add_geo_ring(ax, spec=radial, rank="Period", band=(0.9, 1.0))
        widths = [p.get_width() for p in ax.patches]
        assert widths
        expected = radial.theta_range[1] - radial.theta_range[0]
        assert all(math.isclose(w, expected, abs_tol=1e-9) for w in widths)

    def test_partial_circle(self, polar_ax):
        _fig, ax = polar_ax
        spec = radial_spec_from_biophylo(
            Phylo.read(StringIO(NEWICK), "newick"),
            age_conversion=1.0,
            root_age=63.0,
            r_inner=0.0,
            r_outer=1.0,
            theta_range=(0.0, math.pi / 2),  # 四分之一圆
        )
        _result = add_geo_ring(ax, spec=spec, rank="Period")
        widths = [p.get_width() for p in ax.patches]
        assert widths  # 零 patch 的退化渲染不得静默通过
        assert all(math.isclose(w, math.pi / 2, abs_tol=1e-9) for w in widths)

    def test_ring_uses_spec_radius_mapping(self, polar_ax, radial):
        # 4.9 一致性契约：环段半径由 spec 给出（band == 完整半径范围时逐点
        # 与树的映射一致），且 height 恒为正。
        _fig, ax = polar_ax
        add_geo_ring(ax, spec=radial, rank="Period", band=(0.0, 1.0))
        assert ax.patches
        for patch in ax.patches:
            assert patch.get_height() > 0.0
            assert radial.radius_to_age(patch.get_y()) <= 63.0 + 1e-9


class TestBandGeometryDrivesRingRadii:
    """``band``/``band_unit`` 必须参与几何计算，而不只参与校验。"""

    @staticmethod
    def _spec():
        return RadialSpec(
            age_range=(0.0, 300.0),
            radius_range=(0.0, 1.0),
            theta_range=(0.0, math.pi / 2),
        )

    @pytest.mark.parametrize("band", [(0.92, 1.0), (0.05, 0.15), (0.25, 0.75)])
    def test_all_segments_stay_inside_band(self, polar_ax, band):
        _fig, ax = polar_ax
        spec = self._spec()
        add_geo_ring(ax, spec=spec, rank="Period", band=band)
        spans = _radial_extents(ax.patches)
        assert spans, "环带内未绘制任何环段"
        inner, outer = spec.band_radius(band)
        for lo, hi in spans:
            assert lo >= inner - 1e-12 and hi <= outer + 1e-12, (lo, hi, inner, outer)

    def test_different_bands_give_different_geometry(self, polar_ax):
        # 最小复现：band 若只参与校验而不参与几何，两组 band 会产出逐字节相同的矩形。
        _fig, _ax = polar_ax
        spec = self._spec()
        collected = {}
        for band in ((0.92, 1.0), (0.05, 0.15)):
            fig = plt.figure(figsize=(6, 6))
            axes = fig.add_subplot(111, projection="polar")
            add_geo_ring(axes, spec=spec, rank="Period", band=band, label=False)
            collected[band] = _radial_extents(axes.patches)
            plt.close(fig)
        assert collected[(0.92, 1.0)] != collected[(0.05, 0.15)]
        # 且各自落在自己的环带里（不是同一套全半径几何）。
        assert min(lo for lo, _ in collected[(0.05, 0.15)]) >= 0.05 - 1e-12
        assert max(hi for _, hi in collected[(0.05, 0.15)]) <= 0.15 + 1e-12
        assert min(lo for lo, _ in collected[(0.92, 1.0)]) >= 0.92 - 1e-12

    def test_age_range_endpoints_map_to_band_edges(self, polar_ax):
        # 环带值域 = spec.age_range：max_age → 环带内缘、min_age → 外缘。
        _fig, ax = polar_ax
        spec = self._spec()
        add_geo_ring(ax, spec=spec, rank="Period", band=(0.4, 0.9))
        spans = _radial_extents(ax.patches)
        assert min(lo for lo, _ in spans) == pytest.approx(0.4, abs=1e-12)
        assert max(hi for _, hi in spans) == pytest.approx(0.9, abs=1e-12)

    def test_narrow_window_does_not_rescale_the_band(self, polar_ax):
        # 窗口只裁剪「哪些区间被画出」，不重标环上的半径刻度：否则同一个半径在
        # 环上与在树上会对应两个年龄，违反 4.9 一致性契约。
        _fig, ax = polar_ax
        spec = self._spec()  # age_range = (0, 300)
        add_geo_ring(ax, spec=spec, rank="Period", band=(0.0, 1.0), min_age=0.0, max_age=100.0)
        spans = _radial_extents(ax.patches)
        # 窗口年轻端 0 Ma 仍在 r=1.0；被裁剪的最老片段停在 r(100 Ma) 处
        # （age_to_radius(100) = (300-100)/300 = 2/3），而不是被拉伸回环带内缘
        # r=0——拉伸等价于按窗口重标半径刻度，会让同一个半径在环上与树上对应
        # 两个年龄。
        assert max(hi for _, hi in spans) == pytest.approx(1.0, abs=1e-12)
        assert spec.age_to_radius(100.0) == pytest.approx(2.0 / 3.0, abs=1e-12)
        assert min(lo for lo, _ in spans) == pytest.approx(2.0 / 3.0, abs=1e-12)

    def test_band_unit_data_is_honoured(self, polar_ax):
        _fig, ax = polar_ax
        # 用户把径向视野扩到数据单位量级（本库不调用 set_rlim，由用户负责）。
        ax.set_rlim(0.0, 20.0)
        spec = RadialSpec(
            age_range=(0.0, 300.0),
            radius_range=(10.0, 20.0),
            theta_range=(0.0, math.pi / 2),
        )
        add_geo_ring(ax, spec=spec, rank="Period", band=(12.0, 16.0), band_unit="data")
        spans = _radial_extents(ax.patches)
        assert min(lo for lo, _ in spans) == pytest.approx(12.0, abs=1e-12)
        assert max(hi for _, hi in spans) == pytest.approx(16.0, abs=1e-12)

    def test_segment_bottom_is_the_older_boundary(self, polar_ax):
        # 半径随年龄单调递减，所以每个环段的 bottom 必须是**较老**边界的半径、
        # height 必须是 r(younger) - r(older) > 0，否则即为半径倒置。
        _fig, ax = polar_ax
        spec = self._spec()
        band = (0.3, 0.8)
        add_geo_ring(ax, spec=spec, rank="Period", band=band)
        inner, outer = band
        fragments = []
        for interval in Timescale().iter_intervals(ranks=["Period"], min_age=0.0, max_age=300.0):
            older = min(interval.older_ma, 300.0)
            younger = max(interval.younger_ma, 0.0)
            if older > younger + 1e-12:
                fragments.append((older, younger))
        assert fragments
        expected = sorted(
            (
                spec.age_to_radius(older, radius_range=band),
                spec.age_to_radius(younger, radius_range=band),
            )
            for older, younger in fragments
        )
        assert expected[0][0] < expected[0][1]  # 较老边界在更小的半径上
        actual = sorted(
            (float(p.get_y()), float(p.get_y()) + float(p.get_height())) for p in ax.patches
        )
        assert actual == pytest.approx(expected, abs=1e-12)
        assert all(outer + 1e-12 >= hi and lo >= inner - 1e-12 for lo, hi in actual)

    def test_update_moves_the_ring(self, polar_ax):
        _fig, ax = polar_ax
        spec = self._spec()
        result = add_geo_ring(ax, spec=spec, rank="Period", band=(0.9, 1.0), key="ring")
        before = _radial_extents(_rectangles(result.artists))
        result.update(band=(0.1, 0.2))
        after = _radial_extents(_rectangles(result.artists))
        assert max(hi for _, hi in after) <= 0.2 + 1e-12
        assert min(lo for lo, _ in before) >= 0.9 - 1e-12

    def test_single_interval_and_degenerate_window(self, polar_ax, radial):
        # 极窄窗口 [0, 2] Ma：Paleogene（0–66 Ma）与窗口相交，裁剪后覆盖整个
        # 默认环带 [0.9, 1.0]。断言的是这个具体几何（而不是「返回对象非 None」）。
        _fig, ax = polar_ax
        result = add_geo_ring(ax, spec=radial, rank="Period", min_age=0.0, max_age=2.0)
        assert isinstance(result, GeoAxisResult)
        rects = _rectangles(result.artists)
        assert len(rects) == 1
        bottom = float(rects[0].get_y())
        top = bottom + float(rects[0].get_height())
        # 环带的值域是 spec.age_range（不是绘制窗口）：2 Ma → 0.9 + (63-2)/63*0.1，
        # 0 Ma → 1.0。缩小窗口不改变环上的半径刻度（与树保持同一映射）。
        assert bottom == pytest.approx(0.9 + (63.0 - 2.0) / 63.0 * 0.1, abs=1e-12)
        assert top == pytest.approx(1.0, abs=1e-12)

    def test_single_interval_visible(self, polar_ax, radial):
        _fig, ax = polar_ax
        # 窗口 [30, 40]（spec 域 0–63 Ma 内）：只有 Paleogene 与窗口相交。
        add_geo_ring(ax, spec=radial, rank="Period", min_age=30.0, max_age=40.0)
        assert len(ax.patches) == 1


class TestNoRadialViewModification:
    def test_set_rlim_and_rorigin_never_called(self, polar_ax, radial, monkeypatch):
        _fig, ax = polar_ax

        def _forbidden(*args, **kwargs):  # pragma: no cover - 触发即失败
            raise AssertionError("add_geo_ring 不得修改径向视野（set_rlim/set_rorigin）")

        monkeypatch.setattr(ax, "set_rlim", _forbidden)
        monkeypatch.setattr(ax, "set_rorigin", _forbidden)
        add_geo_ring(ax, spec=radial, rank="Period", band=(0.92, 1.0))


class TestCircularTreeRecipe:
    """6.3 环形树配方端到端：树与环共用同一 RadialSpec。"""

    def test_recipe_end_to_end(self, polar_ax):
        _fig, ax = polar_ax
        tree = Phylo.read(StringIO(NEWICK), "newick")
        radial = radial_spec_from_biophylo(
            tree,
            age_conversion=1.0,
            root_age=63.0,
            r_inner=0.0,
            r_outer=1.0,
            theta_range=(0.0, math.pi / 2),
        )
        theta_0, theta_1 = radial.theta_range
        leaves = tree.get_terminals()
        theta = {
            id(leaf): theta_0 + (theta_1 - theta_0) * i / len(leaves)
            for i, leaf in enumerate(leaves)
        }
        radius = {}
        root_offset = tree.root.branch_length or 0.0
        assert root_offset == 0.0  # 4.10：适配器已强制根基线为 None/0
        radius = {}
        node_ages = []
        for clade in tree.find_clades(order="postorder"):
            age = radial.root_age - (tree.distance(clade) - root_offset)
            node_ages.append((clade, age))
            radius[id(clade)] = radial.age_to_radius(age)
            if clade.clades:
                theta[id(clade)] = float(np.mean([theta[id(c)] for c in clade.clades]))
        for clade in tree.find_clades():
            for child in clade.clades:
                ax.plot(
                    [theta[id(clade)], theta[id(child)]],
                    [radius[id(clade)], radius[id(child)]],
                    color="black",
                    lw=0.8,
                )
        add_geo_ring(ax, spec=radial, rank="Period", band=(0.0, 1.0))
        # 「环与树逐点一致」必须与树的真实量比较：树上每个节点所在半径
        # 反查回年龄，等于该节点的 tree.distance() 推算年龄。
        for clade, age in node_ages:
            assert radial.radius_to_age(radius[id(clade)]) == pytest.approx(age, abs=1e-9)
        # 环段边界半径与树使用同一个映射（band 取完整半径范围时逐点重合）。
        ring_edges = sorted(
            {round(float(p.get_y()), 9) for p in ax.patches}
            | {round(float(p.get_y()) + float(p.get_height()), 9) for p in ax.patches}
        )
        from_ring = [radial.radius_to_age(r) for r in ring_edges]
        assert all(0.0 <= age <= 63.0 + 1e-9 for age in from_ring)
        assert from_ring == sorted(from_ring, reverse=True)  # 半径升序 ↔ 年龄降序

    def test_zero_root_offset_required(self):
        # 4.10：根 branch_length 非零时环形适配器同样拒绝。
        tree = Phylo.read(StringIO(NEWICK), "newick")
        tree.root.branch_length = 5.0
        fig = plt.figure(figsize=(6, 6))
        fig.add_subplot(111, projection="polar")
        with pytest.raises(CoordinateError):
            radial_spec_from_biophylo(
                tree,
                age_conversion=1.0,
                root_age=63.0,
                r_inner=0.0,
                r_outer=1.0,
                theta_range=(0.0, 1.0),
            )
        plt.close(fig)


class TestKeyedUpdateContract:
    """带 key 的幂等更新与 update() 渲染参数契约（4.5/4.8）。"""

    def test_same_key_updates_in_place(self, polar_ax, radial):
        _fig, ax = polar_ax
        r1 = add_geo_ring(ax, spec=radial, rank="Period", key="ring", band=(0.9, 1.0))
        n_before = len(r1.artists)
        r2 = add_geo_ring(ax, spec=radial, rank="Period", key="ring", band=(0.8, 1.0))
        assert r2 is r1
        assert len(r2.artists) == n_before  # 原地重建，不叠加
        assert r2.params["band"] == (0.8, 1.0)

    def test_update_accepts_band_and_rotate_labels(self, polar_ax, radial):
        _fig, ax = polar_ax
        result = add_geo_ring(ax, spec=radial, rank="Period", key="ring")
        result.update(band=(0.7, 0.95), rotate_labels=True)
        assert result.params["band"] == (0.7, 0.95)
        assert result.params["rotate_labels"] is True

    @pytest.mark.parametrize(
        "kwargs",
        [
            dict(ranks=["Epoch"]),
            dict(band_unit="data"),
            dict(min_age=5000.0),
            dict(alpha=5.0),
            dict(band=(0.5, 0.2)),  # 倒置
            dict(thickness_ratio=0.2),  # 线性轨道专用参数不属于环
            dict(bogus=1),
        ],
    )
    def test_update_rejects_non_render_or_out_of_domain(self, polar_ax, radial, kwargs):
        from geophylo import GeophyloError

        _fig, ax = polar_ax
        result = add_geo_ring(ax, spec=radial, rank="Period", key="ring")
        with pytest.raises(GeophyloError):
            result.update(**kwargs)

    def test_failed_update_is_non_destructive(self, polar_ax, radial):
        _fig, ax = polar_ax
        result = add_geo_ring(ax, spec=radial, rank="Period", key="ring", band=(0.9, 1.0))
        n_before = len(result.artists)
        band_before = result.params["band"]
        with pytest.raises(InvalidRadiusError):
            result.update(band=(0.995, 0.995))
        assert len(result.artists) == n_before
        assert result.params["band"] == band_before


class TestRotateLabelsRadialAlignment:
    """rotate_labels=True 时标签沿半径方向对齐：rotation == degrees(theta_center)。"""

    def test_radial_rotation_matches_theta_center(self, polar_ax, radial):
        _fig, ax = polar_ax
        spec = RadialSpec(
            age_range=(0.0, 300.0),
            radius_range=(0.0, 1.0),
            theta_range=(0.0, math.pi / 3),  # theta_center = 30°
        )
        result = add_geo_ring(ax, spec=spec, rank="Period", rotate_labels=True)
        texts = [t for t in result.artists if hasattr(t, "get_text") and t.get_text()]
        assert texts
        for text in texts:
            assert float(text.get_rotation()) == pytest.approx(30.0, abs=1e-9)

    def test_rotation_offset_added_on_top(self, polar_ax):
        _fig, ax = polar_ax
        spec = RadialSpec(
            age_range=(0.0, 300.0),
            radius_range=(0.0, 1.0),
            theta_range=(0.0, math.pi),  # theta_center = 90°
        )
        result = add_geo_ring(ax, spec=spec, rank="Period", rotate_labels=True, rotation=15.0)
        texts = [t for t in result.artists if hasattr(t, "get_text") and t.get_text()]
        assert texts
        for text in texts:
            assert float(text.get_rotation()) == pytest.approx(105.0, abs=1e-9)

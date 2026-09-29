"""CoordinateSpec 契约测试（开发文档 4.3，坐标语义真值表）。"""

from __future__ import annotations

import matplotlib.pyplot as plt
import pytest

from geophylo import (
    AxesTypeError,
    CoordinateError,
    CoordinateSpec,
    InvalidRangeError,
    Timescale,
    add_geo_axis,
)

ANALYTIC_TOL = 1e-9


class TestConstruction:
    def test_valid_both_modes(self):
        absolute = CoordinateSpec.absolute(time_axis="x", age_range=(0.0, 100.0))
        root = CoordinateSpec.root_distance(time_axis="y", age_range=(0.0, 100.0), root_age=100.0)
        assert absolute.mode == "absolute_age" and absolute.root_age is None
        assert root.mode == "root_distance" and root.root_age == 100.0

    @pytest.mark.parametrize(
        "kwargs",
        [
            dict(time_axis="z", mode="absolute_age", age_range=(0.0, 10.0)),
            dict(time_axis="x", mode="diagonal", age_range=(0.0, 10.0)),
            dict(time_axis="x", mode="absolute_age", age_range=(10.0, 10.0)),
            dict(time_axis="x", mode="absolute_age", age_range=(10.0, 5.0)),
            dict(time_axis="x", mode="absolute_age", age_range=(-1.0, 10.0)),
            dict(time_axis="x", mode="absolute_age", age_range=(0.0, 10.0), root_age=5.0),
            dict(time_axis="x", mode="root_distance", age_range=(0.0, 10.0)),
            dict(time_axis="x", mode="root_distance", age_range=(0.0, 10.0), root_age=-1.0),
            dict(time_axis="x", mode="root_distance", age_range=(0.0, float("nan")), root_age=10.0),
            dict(time_axis="x", mode="absolute_age", age_range=(0.0, float("inf"))),
        ],
    )
    def test_illegal_construction(self, kwargs):
        with pytest.raises((CoordinateError, InvalidRangeError)):
            CoordinateSpec(**kwargs)

    def test_frozen(self):
        spec = CoordinateSpec.absolute(time_axis="x", age_range=(0.0, 10.0))
        with pytest.raises(Exception):
            spec.mode = "root_distance"  # type: ignore[misc]


class TestAgeToData:
    def test_absolute_mode_matches_analytic(self):
        spec = CoordinateSpec.absolute(time_axis="x", age_range=(0.0, 541.0))
        for age in (0.0, 66.0, 251.902, 538.8, 541.0):
            assert spec.age_to_data(age) == pytest.approx(age, abs=ANALYTIC_TOL)

    def test_root_distance_mode_matches_analytic(self):
        root_age = 100.0
        spec = CoordinateSpec.root_distance(
            time_axis="x", age_range=(0.0, root_age), root_age=root_age
        )
        for age in (0.0, 25.0, 66.0, 100.0):
            assert spec.age_to_data(age) == pytest.approx(root_age - age, abs=ANALYTIC_TOL)

    def test_domain_outside_rejected(self):
        spec = CoordinateSpec.absolute(time_axis="x", age_range=(0.0, 100.0))
        for bad in (-0.1, 100.1, float("nan"), float("inf")):
            with pytest.raises(CoordinateError):
                spec.age_to_data(bad)

    def test_negative_root_distance_rejected(self):
        spec = CoordinateSpec.root_distance(time_axis="x", age_range=(0.0, 66.0), root_age=50.0)
        with pytest.raises(CoordinateError, match="根距离"):
            spec.age_to_data(66.0)  # 66 > root_age → 负根距离

    def test_bool_rejected(self):
        spec = CoordinateSpec.absolute(time_axis="x", age_range=(0.0, 10.0))
        with pytest.raises(CoordinateError):
            spec.age_to_data(True)


class TestTruthTable:
    """真值表：同一年龄的 patch 数据坐标与轴方向无关（仅显示方向不同）。"""

    def test_patch_data_coords_identical_under_inversion(self):
        # 真值表：同一年龄的 patch 数据坐标只由 spec 决定，与宿主轴方向无关。循环
        # 变量必须真的进入断言，且每轮都要创建 patch，否则"与轴方向无关"这一承诺
        # 根本没被检验——只遍历却不比较的两轮是恒真的。这里正向/反向两条宿主轴上
        # 各画一遍真实轨道：
        #   (1) 两轮 patch 数据坐标逐项相同（视图不变性）；
        #   (2) 该坐标等于数据层年龄经 spec 映射出的独立真值（不是自证恒等）；
        #   (3) 同一数据点在两条轴上的像素位置相反（显示方向）。
        # (2) 对"渲染层把数据坐标算错"敏感；(1)(3) 对"把视图方向烘焙进数据坐标"敏感。
        spec = CoordinateSpec.absolute(time_axis="x", age_range=(0.0, 541.0))

        def render(ax):
            ax.plot([520, 5], [1, 2])
            result = add_geo_axis(ax, spec=spec, ranks=["Period"])
            ax.figure.canvas.draw()
            return sorted(
                (
                    round(min(float(r.get_x()), float(r.get_x()) + float(r.get_width())), 6),
                    round(abs(float(r.get_width())), 6),
                )
                for r in result.artists
                if type(r).__name__ == "Rectangle"
            )

        fig_normal, ax_normal = plt.subplots(figsize=(6, 4))
        ax_normal.set_xlim(0, 541)
        normal_coords = render(ax_normal)
        fig_inverted, ax_inverted = plt.subplots(figsize=(6, 4))
        ax_inverted.set_xlim(541, 0)
        inverted_coords = render(ax_inverted)

        assert normal_coords, "未创建任何 patch——真值表退化为空集"
        assert normal_coords == inverted_coords, (
            "同一区间在正向/反向宿主轴上的 patch 数据坐标必须逐项相同"
        )
        # 与数据层独立比对：期望的 (左界, 宽度) 由 Timescale 区间经 spec 映射得出。
        min_age, max_age = spec.age_range
        expected: list[tuple[float, float]] = []
        for interval in Timescale().iter_intervals(ranks=["Period"], min_age=0.0, max_age=541.0):
            older = min(float(interval.older_ma), max_age)
            younger = max(float(interval.younger_ma), min_age)
            if older <= younger:
                continue
            a, b = spec.age_to_data(older), spec.age_to_data(younger)
            expected.append((round(min(a, b), 6), round(abs(b - a), 6)))
        expected.sort()
        assert normal_coords == expected, "patch 数据坐标与数据层年龄映射不符（渲染层算错了？）"
        # 数据坐标相同，但反向宿主轴把它们摆到相反的像素位置。
        anchor = spec.age_to_data(500.0)
        px_normal = ax_normal.transData.transform((anchor, 0))[0]
        px_inverted = ax_inverted.transData.transform((anchor, 0))[0]
        assert px_normal != px_inverted, "正反向宿主轴的显示位置必须相反"
        plt.close(fig_normal)
        plt.close(fig_inverted)

    def test_display_direction_differs(self):
        spec = CoordinateSpec.absolute(time_axis="x", age_range=(0.0, 541.0))
        _, ax = plt.subplots(figsize=(6, 4))
        ax.set_xlim(541, 0)
        old_px = ax.transData.transform((spec.age_to_data(500.0), 0))[0]
        young_px = ax.transData.transform((spec.age_to_data(50.0), 0))[0]
        assert old_px < young_px  # 反向视图：越老越靠左


class TestFromDataLimits:
    def test_inference_refused_by_default(self, inverted_fig_ax):
        _fig, ax = inverted_fig_ax
        with pytest.raises(CoordinateError, match="acknowledge_inference"):
            CoordinateSpec.from_data_limits(ax, mode="absolute_age", time_axis="x")

    def test_root_distance_requires_root_age(self, inverted_fig_ax):
        _fig, ax = inverted_fig_ax
        with pytest.raises(CoordinateError, match="root_age"):
            CoordinateSpec.from_data_limits(
                ax, mode="root_distance", time_axis="x", acknowledge_inference=True
            )

    def test_absolute_age_rejects_root_age(self, inverted_fig_ax):
        _fig, ax = inverted_fig_ax
        with pytest.raises(CoordinateError):
            CoordinateSpec.from_data_limits(
                ax, mode="absolute_age", time_axis="x", root_age=100.0, acknowledge_inference=True
            )

    def test_inverted_limits_normalized(self, inverted_fig_ax):
        _fig, ax = inverted_fig_ax
        spec = CoordinateSpec.from_data_limits(
            ax, mode="absolute_age", time_axis="x", acknowledge_inference=True
        )
        # 反向轴 get_xlim() 返回 (541, 0)；推断按数值大小归一化。
        assert spec.age_range == pytest.approx((0.0, 541.0))

    def test_y_axis_inference(self):
        _, ax = plt.subplots(figsize=(6, 4))
        ax.set_ylim(0, 251.902)
        spec = CoordinateSpec.from_data_limits(
            ax, mode="absolute_age", time_axis="y", acknowledge_inference=True
        )
        assert spec.age_range == pytest.approx((0.0, 251.902))

    def test_log_axis_rejected(self):
        _, ax = plt.subplots(figsize=(6, 4))
        ax.set_xscale("log")
        with pytest.raises(AxesTypeError):
            CoordinateSpec.from_data_limits(
                ax, mode="absolute_age", time_axis="x", acknowledge_inference=True
            )

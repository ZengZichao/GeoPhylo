"""``add_geo_axis()`` 参数校验、副作用、布局与文本几何测试（规范 4.4/4.5/4.6/5.1/5.2/7.1/7.4）。"""

from __future__ import annotations

import matplotlib.pyplot as plt
import pytest

from geophylo import (
    AxesTypeError,
    CoordinateError,
    CoordinateSpec,
    GeoAxisResult,
    InvalidRangeError,
    InvalidRankError,
    Timescale,
    add_geo_axis,
)
from geophylo.render.linear import MIN_TRACK_THICKNESS_PX, compute_track_layout

STATE_ATTRS = (
    "xlim",
    "ylim",
    "xscale",
    "yscale",
    "autoscalex_on",
    "autoscaley_on",
    "datalim",
)


def host_state(ax):
    return {
        "xlim": tuple(ax.get_xlim()),
        "ylim": tuple(ax.get_ylim()),
        "xscale": ax.get_xscale(),
        "yscale": ax.get_yscale(),
        "autoscalex_on": ax.get_autoscalex_on(),
        "autoscaley_on": ax.get_autoscaley_on(),
        "datalim": tuple(round(v, 9) for v in ax.dataLim.bounds),
    }


class TestInputValidation:
    def test_position_time_axis_mismatch(self, inverted_fig_ax):
        _fig, ax = inverted_fig_ax
        spec = CoordinateSpec.absolute(time_axis="x", age_range=(0.0, 541.0))
        with pytest.raises(CoordinateError, match='time_axis="y"'):
            add_geo_axis(ax, spec=spec, position="left")

    def test_log_axis_rejected(self):
        _fig, ax = plt.subplots(figsize=(6, 4))
        ax.set_xscale("log")
        spec = CoordinateSpec.absolute(time_axis="x", age_range=(1.0, 541.0))
        with pytest.raises(AxesTypeError, match="linear"):
            add_geo_axis(ax, spec=spec)

    def test_category_axis_rejected(self):
        _fig, ax = plt.subplots(figsize=(6, 4))
        ax.plot(["a", "b"], [1, 2])
        spec = CoordinateSpec.absolute(time_axis="x", age_range=(0.0, 10.0))
        with pytest.raises(AxesTypeError):
            add_geo_axis(ax, spec=spec)

    def test_ranks_rejections(self, inverted_fig_ax):
        _fig, ax = inverted_fig_ax
        spec = CoordinateSpec.absolute(time_axis="x", age_range=(0.0, 541.0))
        with pytest.raises(InvalidRankError, match="空"):
            add_geo_axis(ax, spec=spec, ranks=[])
        with pytest.raises(InvalidRankError, match="重复"):
            add_geo_axis(ax, spec=spec, ranks=["Period", "Period"])
        with pytest.raises(InvalidRankError, match="period"):
            add_geo_axis(ax, spec=spec, ranks=["period"])
        with pytest.raises(InvalidRankError, match="Precambrian"):
            add_geo_axis(ax, spec=spec, ranks=["Precambrian"])

    def test_thickness_ratio_bounds(self, inverted_fig_ax):
        _fig, ax = inverted_fig_ax
        spec = CoordinateSpec.absolute(time_axis="x", age_range=(0.0, 541.0))
        for bad in (0.0, -0.1, 0.6):
            with pytest.raises(InvalidRangeError, match="thickness_ratio"):
                add_geo_axis(ax, spec=spec, thickness_ratio=bad)

    def test_window_outside_age_range_rejected(self, inverted_fig_ax):
        _fig, ax = inverted_fig_ax
        spec = CoordinateSpec.absolute(time_axis="x", age_range=(0.0, 100.0))
        with pytest.raises(InvalidRangeError, match="age_range"):
            add_geo_axis(ax, spec=spec, max_age=541.0)

    def test_missing_spec_rejected(self, inverted_fig_ax):
        _fig, ax = inverted_fig_ax
        with pytest.raises(CoordinateError, match="CoordinateSpec"):
            add_geo_axis(ax, spec=None)  # type: ignore[arg-type]


class TestSideEffects:
    def test_host_state_unchanged(self, inverted_fig_ax):
        _fig, ax = inverted_fig_ax
        ax.set_xlim(541, 0)
        before = host_state(ax)
        spec = CoordinateSpec.absolute(time_axis="x", age_range=(0.0, 541.0))
        result = add_geo_axis(ax, spec=spec, ranks=["Period", "Epoch"], tick_style="ages")
        after = host_state(ax)
        for name in STATE_ATTRS:
            assert before[name] == after[name], f"宿主 Axes 的 {name} 被改动"
        # 本库未向宿主添加 Artist（inset 轨道挂在宿主之下，但 host_ax.artists 不变）。
        assert result.host_ax is ax
        assert isinstance(result, GeoAxisResult)

    def test_data_lim_bbox_identical(self, inverted_fig_ax):
        _fig, ax = inverted_fig_ax
        before = ax.dataLim.frozen().bounds
        spec = CoordinateSpec.absolute(time_axis="x", age_range=(0.0, 541.0))
        add_geo_axis(ax, spec=spec)
        after = ax.dataLim.frozen().bounds
        for b, a in zip(before, after, strict=True):
            assert abs(b - a) <= 1e-12


class TestTrackGeometry:
    def test_first_rank_on_near_side(self, inverted_fig_ax):
        _fig, ax = inverted_fig_ax
        spec = CoordinateSpec.absolute(time_axis="x", age_range=(0.0, 541.0))
        result = add_geo_axis(ax, spec=spec, ranks=["Period", "Epoch"])
        fig = ax.figure
        fig.canvas.draw()
        rects = [a for a in result.artists if type(a).__name__ == "Rectangle"]
        assert rects, "未绘制色块"
        # 按 geo_ax 纵向位置把矩形分成两条堆叠轨道（Period 一条、Epoch 一条）。
        track_bottoms = sorted({round(float(r.get_y()), 6) for r in rects})
        assert len(track_bottoms) == 2, f"应恰有两条堆叠轨道，实际 {track_bottoms}"

        def band_at(y):
            return [r for r in rects if round(float(r.get_y()), 6) == y]

        # 独立于渲染层辨认哪条轨道是 Period：Period 区间条数来自数据层。按高度阈值
        # （如 get_height()>0.4）过滤不可靠——两轨道高 0.5556 与 0.4444 都 >0.4，
        # 过滤后挑不出 Period 带，堆叠方向被调换也判不出。
        period_count = len(
            list(Timescale().iter_intervals(ranks=["Period"], min_age=0.0, max_age=541.0))
        )
        assert period_count > 0, "数据层未返回任何 Period 区间"
        period_tracks = [y for y in track_bottoms if len(band_at(y)) == period_count]
        assert len(period_tracks) == 1, (
            f"无法用数据层 Period 条数（{period_count}）唯一定位轨道："
            f"轨道矩形数={[(y, len(band_at(y))) for y in track_bottoms]}"
        )
        period_y = period_tracks[0]
        epoch_y = next(y for y in track_bottoms if y != period_y)
        # 堆叠方向：position='bottom' 时第一个 rank（Period）在近侧（贴宿主、
        # geo_ax 顶部，y 更大）。调换 linear.py 的 direction 会让这一条变红。
        assert period_y > epoch_y, (
            f"Period 带（y={period_y}）必须比 Epoch 带（y={epoch_y}）更靠近宿主 Axes；"
            "轨道堆叠顺序被调换"
        )
        # 取代恒真的 ``track_height > 0``：两条轨道必须严丝合缝铺满 geo_ax 的 [0,1]，
        # 既无空隙也无重叠（几何退化会在这里变红）。
        bottoms = [float(r.get_y()) for r in rects]
        tops = [float(r.get_y()) + float(r.get_height()) for r in rects]
        assert min(bottoms) == pytest.approx(0.0, abs=1e-6)
        assert max(tops) == pytest.approx(1.0, abs=1e-6)
        # 两条轨道只在边界处相接：Epoch 顶 == Period 底，无交叠。
        assert max(b for b in bottoms if b == epoch_y or b < period_y) <= period_y + 1e-9

    def test_clipping_to_window(self, inverted_fig_ax):
        _fig, ax = inverted_fig_ax
        spec = CoordinateSpec.absolute(time_axis="x", age_range=(0.0, 541.0))
        result = add_geo_axis(ax, spec=spec, ranks=["Period"], min_age=100.0, max_age=300.0)
        rects = [a for a in result.artists if type(a).__name__ == "Rectangle"]
        assert rects
        for rect in rects:
            assert rect.get_x() >= 100.0 - 1e-9 and rect.get_x() + rect.get_width() <= 300.0 + 1e-9

    def test_ediacaran_partial_overlap_drawn_clipped(self, inverted_fig_ax):
        # 4.1 窗口相交语义：Ediacaran（~635–538.8）与 [0, 541] 相交，可见片段
        # 被裁剪到窗口内（538.8–541）而不是丢掉或画到 Axes 外。
        _fig, ax = inverted_fig_ax
        spec = CoordinateSpec.absolute(time_axis="x", age_range=(0.0, 541.0))
        result = add_geo_axis(ax, spec=spec, ranks=["Period"])
        rects = [a for a in result.artists if type(a).__name__ == "Rectangle"]
        ediacaran = [r for r in rects if abs(r.get_x() - 538.8) < 1e-6]
        assert ediacaran, "Ediacaran 与窗口相交的部分未绘制"
        assert ediacaran[0].get_width() == pytest.approx(541.0 - 538.8)

    def test_all_positions_align(self):
        for position in ("bottom", "top", "left", "right"):
            fig, ax = plt.subplots(figsize=(6, 6))
            ax.set_xlim(0, 541)
            spec = CoordinateSpec.absolute(
                time_axis="x" if position in ("bottom", "top") else "y",
                age_range=(0.0, 541.0),
            )
            result = add_geo_axis(ax, spec=spec, position=position, ranks=["Period"])
            fig.canvas.draw()
            host = ax.get_window_extent()
            track = result.geo_ax.get_window_extent()
            thickness = track.height if position in ("bottom", "top") else track.width
            assert thickness == pytest.approx(
                host.height * 0.12 if position in ("bottom", "top") else host.width * 0.12, rel=1e-2
            )
            plt.close(fig)

    def test_zero_width_clip_fragment_skipped(self, inverted_fig_ax):
        # 绘制期裁剪产生的零宽片段跳过 Artist。
        _fig, ax = inverted_fig_ax
        spec = CoordinateSpec.absolute(time_axis="x", age_range=(0.0, 538.8000001))
        result = add_geo_axis(ax, spec=spec, ranks=["Period"])
        widths = [r.get_width() for r in result.artists if type(r).__name__ == "Rectangle"]
        assert all(w > 1e-9 for w in widths)


class TestLayoutInvariants:
    def test_thickness_conservation(self):
        ranks = ["Period", "Epoch", "Age"]
        fracs = compute_track_layout(ranks, 0.12, MIN_TRACK_THICKNESS_PX, 100.0, 6.0)
        assert sum(fracs) == pytest.approx(0.12)
        assert all(f > 0 for f in fracs)

    def test_feasibility_precheck(self):
        # min_frac × len(ranks) > total_thickness：分配前显式拒绝。
        with pytest.raises(InvalidRangeError, match="不足以容纳"):
            compute_track_layout(
                ["Period", "Epoch", "Age"], 0.01, MIN_TRACK_THICKNESS_PX, 100.0, 6.0
            )

    def test_insufficient_richness_counterexample(self):
        # 5.2 反例：total=0.1、min_frac=0.04（host_span=1.5in、dpi=100、min_px=6）
        # —— 三条轨道共需 0.12 > 0.1，可行性预检必须在分配前拒绝。
        with pytest.raises(InvalidRangeError):
            compute_track_layout(
                ["Period", "Epoch", "Age"], 0.1, MIN_TRACK_THICKNESS_PX, 100.0, 1.5
            )

    def test_raise_message_contains_numbers(self):
        with pytest.raises(InvalidRangeError) as excinfo:
            compute_track_layout(["Period", "Epoch"], 0.001, MIN_TRACK_THICKNESS_PX, 100.0, 6.0)
        assert "thickness_ratio" in str(excinfo.value)

    def test_label_visibility_baseline(self, inverted_fig_ax):
        # 1.5 验收 5：12×8、label_size=6、双轨道基准图上隐藏比例 ≤ 20%。
        _fig, ax = inverted_fig_ax
        spec = CoordinateSpec.absolute(time_axis="x", age_range=(0.0, 541.0))
        result = add_geo_axis(ax, spec=spec, ranks=["Period", "Epoch"], label_size=6.0)
        fig = ax.figure
        fig.canvas.draw()  # 触发精确标签布局（draw_event）
        fig.canvas.draw()  # savefig 路径同样经过 draw_event
        candidates = len(result._label_items)
        assert candidates > 0
        assert result.labels_hidden / candidates <= 0.20


class TestTicksRendered:
    def test_boundaries_style_artists(self, inverted_fig_ax):
        _fig, ax = inverted_fig_ax
        spec = CoordinateSpec.absolute(time_axis="x", age_range=(0.0, 541.0))
        result = add_geo_axis(ax, spec=spec, ranks=["Period"], tick_style="boundaries")
        texts = [a for a in result.artists if type(a).__name__ == "Text"]
        tick_values = [t for t in texts if t.get_text() and t.get_text() not in ("Ma",)]
        assert tick_values, "刻度数值未渲染"
        assert any(t.get_text() == "Ma" for t in texts)
        assert any(t.get_text() == "66" for t in texts)
        assert not any(t.get_text() == "66.0" for t in texts)

    def test_none_style_no_ticks(self, inverted_fig_ax):
        _fig, ax = inverted_fig_ax
        spec = CoordinateSpec.absolute(time_axis="x", age_range=(0.0, 541.0))
        result = add_geo_axis(ax, spec=spec, ranks=["Period"], tick_style="none")
        texts = [a for a in result.artists if type(a).__name__ == "Text"]
        assert not any(t.get_text() == "Ma" for t in texts)

    def test_tick_max_count_hard_cap(self, inverted_fig_ax):
        _fig, ax = inverted_fig_ax
        spec = CoordinateSpec.absolute(time_axis="x", age_range=(0.0, 541.0))
        result = add_geo_axis(
            ax, spec=spec, ranks=["Period", "Epoch"], tick_style="ages", tick_max_count=5
        )
        texts = [
            a
            for a in result.artists
            if type(a).__name__ == "Text" and a.get_text() not in ("Ma",) and a.get_text()
        ]
        numeric = [t for t in texts if t.get_text().replace(".", "").isdigit()]
        assert len(numeric) <= 5

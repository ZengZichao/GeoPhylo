"""生命周期与副作用测试（开发文档 4.5/7.4）：key 注册表、update/sync/finalize/remove/restore。"""

from __future__ import annotations

import matplotlib.pyplot as plt
import pytest

from geophylo import CoordinateError, CoordinateSpec, add_geo_axis, remove_all
from geophylo.render.result import lookup_track

SPEC = dict(time_axis="x", age_range=(0.0, 541.0))


def make_spec():
    return CoordinateSpec.absolute(**SPEC)


class TestKeyRegistry:
    def test_key_none_creates_independent_tracks(self, inverted_fig_ax):
        _fig, ax = inverted_fig_ax
        r1 = add_geo_axis(ax, spec=make_spec(), key=None)
        r2 = add_geo_axis(ax, spec=make_spec(), key=None)
        assert r1 is not r2
        assert r1.geo_ax is not r2.geo_ax

    def test_same_key_updates_in_place(self, inverted_fig_ax):
        _fig, ax = inverted_fig_ax
        spec = make_spec()
        r1 = add_geo_axis(ax, spec=spec, key="k")
        n_before = len(r1.artists)
        stale = list(r1.geo_ax.patches)
        r2 = add_geo_axis(ax, spec=spec, key="k", ranks=["Era"])
        assert r1 is r2
        # `r1 is r2` 已成立时，比较 r1/r2 各自的长度是恒真的。真正的契约是
        # "原地重建、不叠加"：与同参数的新鲜渲染逐项一致，且旧 Artist 已全部摘除
        # （范式见 test_polar.py:201-207 的 n_before）。
        _fig_ref, ax_ref = plt.subplots(figsize=(12, 8))
        ax_ref.plot([520, 5], [1, 2])
        ax_ref.set_xlim(541, 0)
        fresh = add_geo_axis(ax_ref, spec=make_spec(), ranks=["Era"])
        assert len(r2.artists) == len(fresh.artists) != n_before
        assert len(r2.geo_ax.patches) == len(fresh.geo_ax.patches)
        assert not [patch for patch in stale if patch in r2.geo_ax.patches]
        assert lookup_track(ax, "k") is r1

    def test_same_key_different_spec_rejected(self, inverted_fig_ax):
        _fig, ax = inverted_fig_ax
        add_geo_axis(ax, spec=make_spec(), key="k")
        other = CoordinateSpec.absolute(time_axis="x", age_range=(0.0, 100.0))
        with pytest.raises(CoordinateError, match="remove"):
            add_geo_axis(ax, spec=other, key="k")

    def test_remove_releases_key(self, inverted_fig_ax):
        _fig, ax = inverted_fig_ax
        result = add_geo_axis(ax, spec=make_spec(), key="k")
        result.remove()
        assert lookup_track(ax, "k") is None
        fresh = add_geo_axis(ax, spec=make_spec(), key="k")
        assert fresh is not result

    def test_remove_all(self, inverted_fig_ax):
        _fig, ax = inverted_fig_ax
        add_geo_axis(ax, spec=make_spec(), key="a")
        add_geo_axis(ax, spec=make_spec(), key="b")
        assert remove_all(ax) == 2
        assert remove_all(ax) == 0

    def test_remove_removes_artists_and_disconnected_callback(self, inverted_fig_ax):
        _fig, ax = inverted_fig_ax
        result = add_geo_axis(ax, spec=make_spec(), key="k")
        geo_ax = result.geo_ax
        result.remove()
        assert result.artists == []
        assert geo_ax not in ax.figure.axes  # inset 已从 figure 移除
        # 回调断开：再次 draw 不报错、不重建。
        n_before = len(result.artists)
        ax.figure.canvas.draw()
        assert len(result.artists) == n_before


class TestUpdate:
    def test_update_rejects_spec_position_timescale(self, inverted_fig_ax):
        _fig, ax = inverted_fig_ax
        result = add_geo_axis(ax, spec=make_spec(), key="k")
        for kwargs in (dict(spec=make_spec()), dict(position="top"), dict(timescale=None)):
            with pytest.raises(CoordinateError, match="remove"):
                result.update(**kwargs)

    def test_update_rejects_unknown_params(self, inverted_fig_ax):
        _fig, ax = inverted_fig_ax
        result = add_geo_axis(ax, spec=make_spec())
        with pytest.raises(CoordinateError, match="渲染参数"):
            result.update(root_age=5.0)

    def test_update_returns_self_and_applies(self, inverted_fig_ax):
        _fig, ax = inverted_fig_ax
        result = add_geo_axis(ax, spec=make_spec(), ranks=["Period"])
        returned = result.update(ranks=["Era"], thickness_ratio=0.2)
        assert returned is result
        assert result.params["ranks"] == ("Era",)
        assert result.params["thickness_ratio"] == 0.2

    def test_update_resets_diagnostics(self, inverted_fig_ax):
        _fig, ax = inverted_fig_ax
        spec = make_spec()
        result = add_geo_axis(ax, spec=spec, ranks=["Period", "Epoch"])
        result.relayout(precise=True)
        before = (result.labels_shortened, result.labels_rotated, result.labels_hidden)
        result.update(ranks=["Period"])
        after = (result.labels_shortened, result.labels_rotated, result.labels_hidden)
        # Period 单 rank 比 Period+Epoch 更宽裕：hidden 计数不得增加。
        assert after[2] <= before[2], f"诊断反而恶化：{before} → {after}"
        # "被重置"必须与状态比较才有意义（`assert tuple is not None` 恒真）：
        # update() 之后的诊断要与同参数新鲜渲染的诊断逐项相同。
        _fig_ref, ax_ref = plt.subplots(figsize=(12, 8))
        ax_ref.plot([520, 5], [1, 2])
        ax_ref.set_xlim(541, 0)
        fresh = add_geo_axis(ax_ref, spec=make_spec(), ranks=["Period"])
        reference = (fresh.labels_shortened, fresh.labels_rotated, fresh.labels_hidden)
        assert after == reference, f"update() 后诊断未回到新鲜渲染的状态：{after} != {reference}"
        assert all(isinstance(value, (int, bool)) for value in after)


class TestSyncAndFinalize:
    def test_sync_realigns_track_to_host(self, inverted_fig_ax):
        _fig, ax = inverted_fig_ax
        result = add_geo_axis(ax, spec=make_spec())
        ax.set_xlim(300.0, 0.0)
        result.sync()
        assert result.geo_ax.get_xlim() == ax.get_xlim()

    def test_finalize_freezes_auto_relayout(self, inverted_fig_ax):
        _fig, ax = inverted_fig_ax
        result = add_geo_axis(ax, spec=make_spec(), ranks=["Period", "Epoch"])
        result.finalize()
        assert result._finalized
        # draw 后不再自动重排（隐藏计数保持 finalize 时的值）。
        fig = ax.figure
        fig.canvas.draw()
        hidden_after_draw = result.labels_hidden
        fig.canvas.draw()
        assert result.labels_hidden == hidden_after_draw


class TestRestore:
    def test_restore_after_explicit_host_change(self, inverted_fig_ax):
        _fig, ax = inverted_fig_ax
        result = add_geo_axis(ax, spec=make_spec(), preserve_axes_state=False)
        before = tuple(ax.get_xlim())
        ax.set_xlim(100.0, 0.0)
        result.restore()
        assert tuple(ax.get_xlim()) == before

    def test_restore_recovers_scale(self, inverted_fig_ax):
        _fig, ax = inverted_fig_ax
        result = add_geo_axis(ax, spec=make_spec(), preserve_axes_state=False)
        ax.set_yscale("log")
        result.restore()
        assert ax.get_yscale() == "linear"


class TestVerticalTracks:
    def test_left_position_time_axis_y(self):
        fig, ax = plt.subplots(figsize=(8, 6))
        ax.set_xlim(0, 10)
        ax.set_ylim(541, 0)
        spec = CoordinateSpec.absolute(time_axis="y", age_range=(0.0, 541.0))
        result = add_geo_axis(ax, spec=spec, position="left", ranks=["Period"])
        fig.canvas.draw()
        rects = [a for a in result.artists if type(a).__name__ == "Rectangle"]
        assert rects
        # 时间沿 y：单 rank 的色块在厚度方向（x）铺满整个轨道 [0, 1]，
        # 时间维（y）按数据单位跨越窗口宽度。
        rect = rects[0]
        assert rect.get_width() == pytest.approx(1.0)
        assert rect.get_height() > 1.0
        plt.close(fig)


class TestUpdateValidation:
    """update() 与创建路径共用同一套取值域约束（4.4/4.7/4.11）。"""

    @pytest.mark.parametrize(
        "kwargs",
        [
            dict(alpha=7.5),
            dict(alpha=-0.1),
            dict(label_size=-2.0),
            dict(label_size=0.0),
            dict(thickness_ratio=0.9),
            dict(thickness_ratio=-0.3),
            dict(tick_max_count=0),
            dict(border_width=-1.0),
        ],
    )
    def test_update_rejects_out_of_range_values(self, inverted_fig_ax, kwargs):
        from geophylo import GeophyloError

        _fig, ax = inverted_fig_ax
        result = add_geo_axis(ax, spec=make_spec(), ranks=["Period"])
        with pytest.raises(GeophyloError):  # 公共异常，而非原始 ValueError
            result.update(**kwargs)

    @pytest.mark.parametrize("kwargs", [dict(label_color=123), dict(border_color=None)])
    def test_update_rejects_bad_types(self, inverted_fig_ax, kwargs):
        _fig, ax = inverted_fig_ax
        result = add_geo_axis(ax, spec=make_spec(), ranks=["Period"])
        with pytest.raises(CoordinateError):
            result.update(**kwargs)

    def test_failed_update_is_non_destructive(self, inverted_fig_ax):
        _fig, ax = inverted_fig_ax
        result = add_geo_axis(ax, spec=make_spec(), ranks=["Period"], tick_style="boundaries")
        artists_before = list(result.artists)
        params_before = dict(result.params)
        with pytest.raises(Exception):
            result.update(alpha=42.0)
        # 原 Artist 全部保留、原参数未被污染。
        assert len(result.artists) == len(artists_before)
        assert result.params == params_before

    def test_add_geo_axis_rejects_non_string_colors(self, inverted_fig_ax):
        _fig, ax = inverted_fig_ax
        with pytest.raises(CoordinateError, match="label_color"):
            add_geo_axis(ax, spec=make_spec(), label_color=123)  # type: ignore[arg-type]
        with pytest.raises(CoordinateError, match="border_color"):
            add_geo_axis(ax, spec=make_spec(), border_color=3.14)  # type: ignore[arg-type]

    def test_add_geo_axis_rejects_non_string_skip(self, inverted_fig_ax):
        _fig, ax = inverted_fig_ax
        with pytest.raises(CoordinateError, match="skip"):
            add_geo_axis(ax, spec=make_spec(), skip=["Jurassic", 42])  # type: ignore[list-item]


class TestSyncThicknessReallocation:
    """sync() 的第二层语义：物理尺寸变化后重排厚度；空间不足保持上次布局（4.5/5.1）。"""

    def test_sync_keeps_allocation_conserved(self, inverted_fig_ax):
        _fig, ax = inverted_fig_ax
        result = add_geo_axis(ax, spec=make_spec(), ranks=["Epoch", "Age"], key="k")
        result.sync()
        assert result.sync_degraded is False
        assert result._last_fracs is not None
        # 总量守恒：各 rank 厚度之和恒等于 thickness_ratio。
        assert sum(result._last_fracs) == pytest.approx(result.params["thickness_ratio"])

    def test_shrink_below_min_px_marks_degraded_and_keeps_layout(self, inverted_fig_ax):
        _fig, ax = inverted_fig_ax
        result = add_geo_axis(ax, spec=make_spec(), ranks=["Epoch", "Age"])
        fracs_before = list(result._last_fracs)
        n_before = len(result.artists)
        ax.figure.set_size_inches(0.5, 0.3)  # 远小于 2×min_px 所需空间
        result.sync()
        assert result.sync_degraded is True
        assert result._last_fracs == fracs_before  # 保持上次布局
        assert len(result.artists) == n_before  # 不清空轨道

    def test_failed_sync_does_not_raise_in_draw(self, inverted_fig_ax):
        _fig, ax = inverted_fig_ax
        add_geo_axis(ax, spec=make_spec(), ranks=["Epoch", "Age"], key="k")
        ax.figure.set_size_inches(0.5, 0.3)
        ax.figure.canvas.draw()  # draw_event 中的 sync 不得中断渲染

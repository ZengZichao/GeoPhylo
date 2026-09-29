"""``add_geo_axis()``：面向 Matplotlib Axes 的线性地质时间轴（规范 4.4/5.1/5.2）。

实现只使用 inset Axes（ADR-2）：轨道 Axes 的 bounds 用 ``host_ax.transAxes``
指定，其数据坐标范围从宿主 Axes **复制数值但不共享**，既保持几何对齐，又避免
宿主 autoscale 反过来改变轨道范围。

ADR-2 记录见 ``docs/adr/ADR-2-inset-axes-for-tracks.md``。
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, Literal, cast

import matplotlib.colors
import matplotlib.text as mtext
from matplotlib.lines import Line2D
from matplotlib.patches import Rectangle

from ..coordinate.spec import CoordinateSpec
from ..exceptions import CoordinateError, InvalidRangeError
from ..timescale import Timescale
from ..validation import (
    BORDERS,
    POSITIONS,
    TICK_STYLES,
    check_position_time_axis,
    normalize_ranks,
    require_age_window,
    require_bool,
    require_choice,
    require_linear_numeric_axes,
    require_number,
)
from .labels import (
    LabelItem,
    apply_label_degradation,
    auto_label_color,
    estimate_text_size,
    measure_text_size,
    time_axis_index_for,
)
from .result import GeoAxisResult, _require_skip_names, lookup_track, register_track
from .ticks import (
    cap_ticks,
    dedupe_ages,
    fill_ages_style,
    filter_by_pixel_distance,
    format_age,
)

if TYPE_CHECKING:  # pragma: no cover
    from matplotlib.axes import Axes

__all__ = [
    "MIN_LABEL_LENGTH_PX",
    "MIN_TRACK_THICKNESS_PX",
    "RANK_WEIGHTS",
    "add_geo_axis",
    "compute_track_layout",
]

# 轨道最小厚度（像素）；暴露为模块级常量，便于测试与用户按字体大小调整。
MIN_TRACK_THICKNESS_PX = 6.0

# 标签的最小时间维像素长度：裁剪后落在轨道上不足半个像素的贴边片段不再
# 产出名称标签——它的名字只能靠溢出到相邻区间或轨道外来显示。
MIN_LABEL_LENGTH_PX = 0.5

# 权重只包含五个核心 rank（契约）；权重仅作初始分配，随后按最小像素厚度校正。
RANK_WEIGHTS = {"Eon": 0.8, "Era": 1.0, "Period": 1.2, "Epoch": 1.5, "Age": 2.0}

# 5.2 的排列方向：第一个 rank 最靠近数据区（near 侧）。
_NEAR_FRACTION_START = {"bottom": 1.0, "top": 0.0, "left": 1.0, "right": 0.0}

# 5.1 的边框位置语义：near 指靠近宿主数据区的一侧，far 指背离数据区的一侧。
_NEAR_SIDE = {"bottom": "top", "top": "bottom", "left": "right", "right": "left"}

# 标签隐藏优先级：rank 越靠核心越优先保留（数值小者优先）。
RANK_PRIORITY = {"Eon": 0, "Era": 1, "Period": 2, "Epoch": 3, "Age": 4}


def compute_track_layout(
    ranks: Sequence[str],
    total_thickness: float,
    min_px: float,
    dpi: float,
    host_span_in: float,
) -> list[float]:
    """返回每个 rank 的厚度比例；权重仅作初始分配（规范 5.2）。

    两条不变量：可行性预检在分配之前完成（``min_frac × len(ranks) >``
    ``total_thickness`` 时抛 ``InvalidRangeError``）；总量守恒（各 rank 厚度
    之和恒等于 ``total_thickness``）。
    """
    weights = [RANK_WEIGHTS[r] for r in ranks]
    total = sum(weights)
    min_frac = (min_px / dpi) / host_span_in
    if min_frac * len(ranks) > total_thickness + 1e-12:
        raise InvalidRangeError(
            f"thickness_ratio={total_thickness} 不足以容纳 {len(ranks)} 条轨道"
            f"（每条至少 {min_frac:.4f}，共 {min_frac * len(ranks):.4f}）；"
            "请增大 thickness_ratio 或减少 rank 数量"
        )
    raw = [total_thickness * w / total for w in weights]
    deficit = sum(max(0.0, min_frac - t) for t in raw)
    if deficit <= 1e-12:
        return raw
    slack = [max(0.0, t - min_frac) for t in raw]
    total_slack = sum(slack)
    # 可行性预检已保证 deficit <= total_slack：从超出最小厚度的轨道中按富余量
    # 比例回收 deficit，不会把任何轨道压到 min_frac 之下，且总量守恒。
    return [
        max(min_frac, t) - deficit * (s / total_slack) for t, s in zip(raw, slack, strict=False)
    ]


def add_geo_axis(
    ax: Axes,
    *,
    spec: CoordinateSpec,
    position: Literal["bottom", "top", "left", "right"] = "bottom",
    ranks: str | Sequence[str] | None = None,
    timescale: Timescale | None = None,
    thickness_ratio: float = 0.12,
    min_age: float | None = None,
    max_age: float | None = None,
    fill: bool = True,
    alpha: float = 1.0,
    label: bool = True,
    label_size: float = 6.0,
    label_color: str = "auto",
    skip: Sequence[str] | None = None,
    abbreviate: bool = True,
    border: Literal["none", "near", "far", "both"] = "both",
    border_width: float = 0.5,
    border_color: str = "black",
    rotation: float = 0.0,
    tick_style: Literal["none", "boundaries", "ages"] = "none",
    tick_max_count: int = 10,
    key: str | None = None,
    preserve_axes_state: bool = True,
) -> GeoAxisResult:
    """在宿主 Axes 内叠加地质时间条带，返回 ``GeoAxisResult``（ADR-3）。

    ``position`` 唯一决定时间轴方向：``bottom``/``top`` → 时间沿 x，
    ``left``/``right`` → 时间沿 y；``spec.time_axis`` 只作一致性校验。
    ``ranks=None`` 归一化为 ``("Period",)``；``timescale=None`` 使用默认内置快照。

    ADR-3 记录见 ``docs/adr/ADR-3-result-object-not-axes.md``。
    """
    # ---- 参数校验（4.4 输入约束与拒绝行为）------------------------------
    require_linear_numeric_axes(ax)
    if not isinstance(spec, CoordinateSpec):
        raise CoordinateError(
            f"spec 必须是 CoordinateSpec，得到 {type(spec).__name__}；"
            "坐标语义的唯一真值来源不能省略"
        )
    position = cast(
        Literal["bottom", "top", "left", "right"],
        require_choice("position", position, POSITIONS),
    )
    check_position_time_axis(position, spec.time_axis)
    ranks_tuple = normalize_ranks(ranks)
    thickness = require_number(
        "thickness_ratio", thickness_ratio, minimum=0.0, maximum=0.5, exclude_minimum=True
    )
    assert thickness is not None  # allow_none=False：缺失时已抛 InvalidRangeError
    require_bool("fill", fill)
    require_bool("label", label)
    require_bool("abbreviate", abbreviate)
    require_bool("preserve_axes_state", preserve_axes_state)
    require_number("alpha", alpha, minimum=0.0, maximum=1.0)
    require_number("label_size", label_size, minimum=0.0, exclude_minimum=True)
    require_number("border_width", border_width, minimum=0.0)
    require_number("rotation", rotation)
    if (
        isinstance(tick_max_count, bool)
        or not isinstance(tick_max_count, int)
        or tick_max_count < 1
    ):
        raise InvalidRangeError(f"tick_max_count 必须是正整数，得到 {tick_max_count!r}")
    require_choice("border", border, BORDERS)
    require_choice("tick_style", tick_style, TICK_STYLES)
    if not isinstance(label_color, str):
        raise CoordinateError(f'label_color 必须是字符串或 "auto"，得到 {label_color!r}')
    if not isinstance(border_color, str):
        raise CoordinateError(f"border_color 必须是字符串，得到 {border_color!r}")
    if key is not None and not isinstance(key, str):
        raise CoordinateError(f"key 必须是字符串或 None，得到 {key!r}")
    window = require_age_window(
        min_age, max_age, spec_min=spec.age_range[0], spec_max=spec.age_range[1]
    )
    if timescale is not None and not isinstance(timescale, Timescale):
        raise CoordinateError(
            f"timescale 必须是 Timescale 或 None，得到 {type(timescale).__name__}"
        )
    skip_names = _require_skip_names("skip", skip) if skip is not None else ()

    # ---- 幂等与重复调用策略（4.5）---------------------------------------
    params: dict = dict(
        ranks=ranks_tuple,
        thickness_ratio=float(thickness),
        min_age=float(window[0]),
        max_age=float(window[1]),
        fill=fill,
        alpha=float(alpha),
        label=label,
        label_size=float(label_size),
        label_color=label_color,
        skip=skip_names,
        abbreviate=abbreviate,
        border=border,
        border_width=float(border_width),
        border_color=border_color,
        rotation=float(rotation),
        tick_style=tick_style,
        tick_max_count=int(tick_max_count),
    )
    if key is not None:
        existing = lookup_track(ax, key)
        if existing is not None:
            if existing.spec != spec:
                raise CoordinateError(
                    f"key={key!r} 已存在于该宿主 Axes 上且绑定了不同的 spec；"
                    "坐标语义不可原地更新，请 remove() 后重新 add_geo_axis()"
                )
            if existing.position != position:
                raise CoordinateError(
                    f"key={key!r} 已存在于该宿主 Axes 上且 position={existing.position!r}；"
                    "position 不可原地更新，请 remove() 后重新 add_geo_axis()"
                )
            return existing.update(**params)

    timescale = timescale if timescale is not None else Timescale()

    result = _LinearResult(
        host_ax=ax,
        position=position,
        timescale=timescale,
        params=params,
        spec=spec,
        key=key,
        preserved=preserve_axes_state,
    )
    result.rebuild()
    register_track(result)
    return result


class _LinearResult(GeoAxisResult):
    """线性轨道的重建与标签布局实现（私有）。"""

    def __init__(self, *, host_ax, position, timescale, params, spec, key, preserved) -> None:
        self._timescale = timescale
        self._last_fracs: list[float] | None = None
        geo_ax = self._make_track_axes(host_ax, position, params["thickness_ratio"])
        super().__init__(
            host_ax=host_ax,
            geo_ax=geo_ax,
            artists=[],
            spec=spec,
            key=key,
            position=position,
            params=dict(params),
            rebuild=self.rebuild,
            preserved=preserved,
        )
        self._label_items: list[LabelItem] = []
        self.attach_draw_callback()

    # -- 轨道 Axes（5.1）---------------------------------------------------

    @staticmethod
    def _make_track_axes(host_ax, position, thickness_ratio, pad=0.0):
        """按 position 在宿主 Axes 内创建一个轨道 Axes（inset，唯一默认）。"""
        t = thickness_ratio
        if position == "bottom":
            bounds = (0.0, pad, 1.0, t)
        elif position == "top":
            bounds = (0.0, 1.0 - t - pad, 1.0, t)
        elif position == "left":
            bounds = (pad, 0.0, t, 1.0)
        else:  # "right"
            bounds = (1.0 - t - pad, 0.0, t, 1.0)
        # bounds 就是宿主 Axes 的比例：``inset_axes`` 的默认 transform 已是
        # ``transAxes``，显式再传一次 ``transAxes`` 与之完全等价（matplotlib
        # 3.10+ 的 ``Axes.inset_axes`` 源码：``if transform is None: transform =
        # self.transAxes``），既不会也不会双重换算。thickness_ratio 以宿主
        # Axes 尺寸为基准，不随宿主数值范围漂移。
        geo_ax = host_ax.inset_axes(bounds)
        geo_ax.set_axis_off()
        return geo_ax

    def _align_track_to_host(self) -> None:
        """把轨道的时间维数据范围设为与宿主相同，另一维固定为 [0, 1]。

        轨道数据范围复制宿主数值但不共享（不用 sharex），因此宿主后续
        autoscale 不会把轨道范围拉走；同时 ``spec.age_to_data()`` 的数值可以
        直接用作轨道上的数据坐标，不需要二次变换。
        """
        if self.spec.time_axis == "x":
            self.geo_ax.set_xlim(self.host_ax.get_xlim())  # 复制数值
            self.geo_ax.set_ylim(0.0, 1.0)
        else:
            self.geo_ax.set_ylim(self.host_ax.get_ylim())
            self.geo_ax.set_xlim(0.0, 1.0)

    def _host_span_inches(self, dpi: float) -> float:
        """宿主 Axes 在厚度方向上的物理尺寸（英寸）：水平轨道取高度，垂直取宽度。"""
        bbox = self.host_ax.get_window_extent()
        span_px = bbox.height if self.position in ("bottom", "top") else bbox.width
        return span_px / dpi

    def _compute_allocation(self, params: dict):
        """按当前 dpi 与宿主物理尺寸执行 5.2 的厚度分配（可能抛 ``InvalidRangeError``）。"""
        dpi = self.host_ax.figure.dpi
        host_span_in = self._host_span_inches(dpi)
        fracs = compute_track_layout(
            params["ranks"],
            float(params["thickness_ratio"]),
            MIN_TRACK_THICKNESS_PX,
            dpi,
            host_span_in,
        )
        return fracs, dpi, host_span_in

    # -- update 预检与 sync（4.5/5.1）---------------------------------------

    def _precheck_update(self, merged: dict) -> None:
        """提交新参数前预检厚度分配可行性；失败抛 ``InvalidRangeError`` 且不改动状态。"""
        self._compute_allocation(merged)

    def sync(self) -> None:
        """宿主 limits 或物理尺寸变化后：重对齐轨道数据范围并重排轨道厚度。

        其二（4.5/5.1）：用当前尺寸重新执行 5.2 的厚度分配（仍受 ``min_px``
        与总量守恒约束）；若重新分配因空间不足失败，保持上次布局并在
        ``sync_degraded`` 诊断位记录，不中断绘制。
        """
        super().sync()  # 重对齐轨道时间维数据范围（基类语义其一）
        try:
            fracs, _dpi, _span = self._compute_allocation(self.params)
        except InvalidRangeError:
            self.sync_degraded = True
            return
        self.sync_degraded = False
        if (
            self._last_fracs is None
            or len(fracs) != len(self._last_fracs)
            or any(abs(a - b) > 1e-12 for a, b in zip(fracs, self._last_fracs, strict=False))
        ):
            self.rebuild()

    # -- 重建 --------------------------------------------------------------

    def rebuild(self) -> None:
        """（重）绘制本轨道的全部 Artist；供创建、``update()`` 与 ``sync()`` 复用。

        厚度分配在清理旧 Artist **之前**计算：可行性不满足时抛
        ``InvalidRangeError``，失败路径不留下被清空的轨道。
        """
        p = self.params
        fracs = self._compute_allocation(p)[0]
        self._last_fracs = list(fracs)
        for artist in list(self.artists):
            try:
                artist.remove()
            except (NotImplementedError, ValueError):  # pragma: no cover
                pass
        self.artists = []
        self._label_items = []
        self.geo_ax.set_axis_off()
        self._align_track_to_host()
        self.sync_degraded = False

        window_lo, window_hi = float(p["min_age"]), float(p["max_age"])

        # 排列方向：从 near 侧向 far 侧依次排列，第一个 rank 最靠近数据区。
        # fracs 是相对宿主的比例（和恒等于 thickness_ratio）；轨道 Axes 自身的
        # 厚度维是 [0, 1]，因此带内坐标须按 / thickness_ratio 归一化。
        thickness = float(p["thickness_ratio"])
        near = _NEAR_FRACTION_START[self.position]
        direction = -1.0 if near == 1.0 else 1.0
        bands: list[tuple[float, float]] = []
        offset = 0.0
        for frac in fracs:
            span = frac / thickness
            start = near + direction * offset
            end = near + direction * (offset + span)
            bands.append((min(start, end), max(start, end)))
            offset += span

        for rank, (band_lo, band_hi) in zip(p["ranks"], bands, strict=False):
            intervals = self._window_intervals(rank, window_lo, window_hi)
            thickness_span_px = self._thickness_span_px()
            band_px = (band_hi - band_lo) * thickness_span_px
            if p["fill"]:
                for interval, older, younger in intervals:
                    self._draw_interval_linear(
                        interval,
                        older,
                        younger,
                        band_lo=band_lo,
                        band_hi=band_hi,
                        alpha=float(p["alpha"]),
                    )
            if p["label"]:
                for interval, older, younger in intervals:
                    if interval.name in p["skip"]:
                        continue
                    self._add_label_item(
                        interval,
                        older,
                        younger,
                        band_lo=band_lo,
                        band_hi=band_hi,
                        band_px=band_px,
                    )
            self._draw_borders(band_lo, band_hi)

        if p["tick_style"] != "none":
            self._draw_ticks(window_lo, window_hi)
        self.relayout(precise=False)

    # -- 区间查询与裁剪 ----------------------------------------------------

    def _window_intervals(self, rank: str, window_lo: float, window_hi: float):
        """窗口**相交**语义（4.1）：返回与窗口有交集的完整区间，裁剪到窗口内。

        裁剪产生的零宽片段跳过 Artist，不与非法的零长度源区间混为一谈。
        """
        clipped = []
        for interval in self._timescale.iter_intervals(
            ranks=[rank], min_age=window_lo, max_age=window_hi
        ):
            older = min(interval.older_ma, window_hi)
            younger = max(interval.younger_ma, window_lo)
            if older <= younger + 1e-12:
                continue  # 零宽片段：跳过
            clipped.append((interval, older, younger))
        return clipped

    # -- 色块与边框（5.1）--------------------------------------------------

    def _thickness_span_px(self) -> float:
        bbox = self.geo_ax.get_window_extent()
        return bbox.height if self.spec.time_axis == "x" else bbox.width

    def _draw_interval_linear(self, interval, older, younger, *, band_lo, band_hi, alpha):
        """在轨道 Axes 上绘制一个（已裁剪到窗口的）区间色块。"""
        a = self.spec.age_to_data(older)
        b = self.spec.age_to_data(younger)
        lo, hi = min(a, b), max(a, b)
        # clip_on=True 必须成立：区间已在绘制前被窗口语义裁剪到 [min_age, max_age]，
        # 不存在需要画到 Axes 外的片段；inset Axes 方案自动满足这一前提。
        if self.spec.time_axis == "x":
            rect = Rectangle(
                (lo, band_lo),
                hi - lo,
                band_hi - band_lo,
                facecolor=interval.color,
                edgecolor="none",
                alpha=alpha,
                clip_on=True,
            )
        else:
            rect = Rectangle(
                (band_lo, lo),
                band_hi - band_lo,
                hi - lo,
                facecolor=interval.color,
                edgecolor="none",
                alpha=alpha,
                clip_on=True,
            )
        rect.set_zorder(1)
        self.geo_ax.add_patch(rect)
        self.artists.append(rect)
        return rect

    def _draw_borders(self, band_lo: float, band_hi: float) -> None:
        """按 position 与 border 语义绘制边框（独立 Line2D，而非四边 edgecolor）。

        ``Rectangle(edgecolor=...)`` 会画四条边，无法只画靠近数据区的一侧。
        """
        p = self.params
        border = p["border"]
        if border == "none":
            return
        near = _NEAR_SIDE[self.position]
        far = {"top": "bottom", "bottom": "top", "left": "right", "right": "left"}[near]
        sides = {"both": (near, far), "near": (near,), "far": (far,)}[border]
        near_frac = band_hi if self.position in ("bottom", "left") else band_lo
        far_frac = band_lo if self.position in ("bottom", "left") else band_hi
        a = self.spec.age_to_data(float(p["min_age"]))
        b = self.spec.age_to_data(float(p["max_age"]))
        lo, hi = min(a, b), max(a, b)
        horizontal = self.position in ("bottom", "top")
        for side in sides:
            frac = near_frac if side == near else far_frac
            if horizontal:
                (line,) = self.geo_ax.plot(
                    [lo, hi],
                    [frac, frac],
                    color=p["border_color"],
                    lw=p["border_width"],
                    clip_on=True,
                )
            else:
                (line,) = self.geo_ax.plot(
                    [frac, frac],
                    [lo, hi],
                    color=p["border_color"],
                    lw=p["border_width"],
                    clip_on=True,
                )
            line.set_zorder(2)
            self.artists.append(line)

    # -- 标签（5.2/5.4）----------------------------------------------------

    def _add_label_item(self, interval, older, younger, *, band_lo, band_hi, band_px) -> None:
        p = self.params
        a, b = self.spec.age_to_data(older), self.spec.age_to_data(younger)
        center_age = (older + younger) / 2.0
        center_value = self.spec.age_to_data(center_age)
        if self.spec.time_axis == "x":
            center = (center_value, (band_lo + band_hi) / 2.0)
            x_lo, x_hi = sorted(self.geo_ax.get_xlim())
            total_px = self.geo_ax.get_window_extent().width
            length_px = abs(b - a) / max(1e-12, x_hi - x_lo) * total_px
        else:
            center = ((band_lo + band_hi) / 2.0, center_value)
            y_lo, y_hi = sorted(self.geo_ax.get_ylim())
            total_px = self.geo_ax.get_window_extent().height
            length_px = abs(b - a) / max(1e-12, y_hi - y_lo) * total_px
        base_rotation = float(p["rotation"]) + (0.0 if self.spec.time_axis == "x" else 90.0)
        if length_px < MIN_LABEL_LENGTH_PX:
            # 裁剪后不足半像素的贴边片段（如窗口边界切过 Holocene）不产出名称
            # 标签：它在图面上本就不可辨，标签只能靠越出轨道来显示。
            return
        color = p["label_color"]
        if color == "auto":
            color = auto_label_color(
                interval.color, alpha=float(p["alpha"]), background=_background_hex(self.geo_ax)
            )
        text = mtext.Text(
            center[0],
            center[1],
            interval.name,
            ha="center",
            va="center",
            fontsize=float(p["label_size"]),
            color=color,
            rotation=base_rotation,
            clip_on=False,
            visible=False,
        )
        text.set_zorder(4)
        self.geo_ax.add_artist(text)
        item = LabelItem(
            interval=interval,
            artist=text,
            center=center,
            length_px=length_px,
            thickness_px=band_px,
            base_rotation=base_rotation,
            time_axis_index=time_axis_index_for(self.spec.time_axis),
            rank_priority=RANK_PRIORITY.get(interval.rank, 99),
            sort_key=(RANK_PRIORITY.get(interval.rank, 99), -interval.older_ma, interval.id),
        )
        self._label_items.append(item)
        self.artists.append(text)

    # -- 刻度（4.6）--------------------------------------------------------

    def _draw_ticks(self, window_lo: float, window_hi: float) -> None:
        p = self.params
        boundaries: list[float] = []
        for rank in p["ranks"]:
            for _interval, older, younger in self._window_intervals(rank, window_lo, window_hi):
                boundaries.extend((older, younger))
        ages = dedupe_ages(boundaries)
        if p["tick_style"] == "ages":
            fills = fill_ages_style(ages, min_age=window_lo, max_age=window_hi)
            candidates = [*ages, *fills]
            ages = cap_ticks(ages, fills, tick_max_count=int(p["tick_max_count"]))
            # cap_ticks 的拼接结果（边界 + 补充刻度）不保证有序，而
            # filter_by_pixel_distance 的「保留较老者」契约要求从老到新排序。
            ages = sorted(ages, reverse=True)
        else:
            # ``boundaries`` 样式不受 ``tick_max_count`` 硬上限约束。图上少
            # 一个边界数字会被读者误读为「该处不存在界线」，因此该样式的取舍只
            # 由像素间距决定；被过滤掉的候选数记录在 ``result.ticks_dropped``。
            candidates = list(ages)
            ages = sorted(ages, reverse=True)
        # 任何两个刻度中心间距小于 label_size * 2 像素时保留较老者（4.6 字面契约）。
        min_gap_px = 2.0 * float(p["label_size"])
        if self.spec.time_axis == "x":

            def to_display(age: float) -> float:
                return self.geo_ax.transData.transform((self.spec.age_to_data(age), 0.0))[0]

        else:

            def to_display(age: float) -> float:
                return self.geo_ax.transData.transform((0.0, self.spec.age_to_data(age)))[1]

        ages = filter_by_pixel_distance(ages, to_display=to_display, min_gap_px=min_gap_px)
        ages = [age for age in ages if window_lo - 1e-9 <= age <= window_hi + 1e-9]
        near_side = _NEAR_SIDE[self.position]
        horizontal = self.spec.time_axis == "x"
        tick_len = 0.06
        label_size = float(p["label_size"])
        fontsize = label_size * 0.92
        dpi = float(self.host_ax.figure.dpi)
        track_bbox = self.geo_ax.get_window_extent()
        edge_lo, edge_hi = (
            (float(track_bbox.x0), float(track_bbox.x1))
            if horizontal
            else (float(track_bbox.y0), float(track_bbox.y1))
        )
        # 贴在窗口边缘的刻度数字按内沿对齐，使其包围盒不越出轨道。内沿对齐把
        # 贴边数字整体推进轨道内部，所以只看锚点的"中心间距"过滤
        # （``filter_by_pixel_distance``）不足以保证数字互不粘连：这里按对齐后的
        # **包围盒**再做一次同优先级（从老到新、保留较老者）的过滤，被这一层丢掉
        # 的候选同样计入 ``ticks_dropped``。
        placed: list[tuple[float, str, str]] = []
        boxes: list[tuple[float, float]] = []
        for age in ages:
            text = format_age(age)
            width_px = estimate_text_size(text, fontsize, dpi)[0 if horizontal else 1]
            align, box_lo, box_hi = _tick_placement(
                float(to_display(age)), width_px, edge_lo, edge_hi, horizontal
            )
            if any(box_lo < kept_hi and box_hi > kept_lo for kept_lo, kept_hi in boxes):
                continue  # 与已保留的较老数字粘连：保留较老者（4.6）
            boxes.append((box_lo, box_hi))
            placed.append((age, text, align))
        self.ticks_dropped = max(0, len({round(float(a), 9) for a in candidates}) - len(placed))

        for age, text, align in placed:
            value = self.spec.age_to_data(age)
            if horizontal:
                y_edge = 1.0 if near_side == "top" else 0.0
                direction = -1.0 if near_side == "top" else 1.0
                line = Line2D(
                    [value, value],
                    [y_edge, y_edge + direction * tick_len],
                    color="black",
                    lw=0.5,
                    clip_on=True,
                )
                label = mtext.Text(
                    value,
                    y_edge + direction * (tick_len + 0.02),
                    text,
                    ha=align,
                    va="top" if direction < 0 else "bottom",
                    fontsize=fontsize,
                    color="black",
                    clip_on=False,
                )
            else:
                x_edge = 1.0 if near_side == "right" else 0.0
                direction = -1.0 if near_side == "right" else 1.0
                line = Line2D(
                    [x_edge, x_edge + direction * tick_len],
                    [value, value],
                    color="black",
                    lw=0.5,
                    clip_on=True,
                )
                label = mtext.Text(
                    x_edge + direction * (tick_len + 0.02),
                    value,
                    text,
                    ha="right" if direction < 0 else "left",
                    va=align,
                    fontsize=fontsize,
                    color="black",
                    clip_on=False,
                )
            line.set_zorder(3)
            label.set_zorder(3)
            self.geo_ax.add_line(line)
            self.geo_ax.add_artist(label)
            self.artists.extend((line, label))
        if placed:
            self._draw_unit_label(window_lo, window_hi, to_display, horizontal, near_side, tick_len)

    def _draw_unit_label(
        self,
        window_lo: float,
        window_hi: float,
        to_display,
        horizontal: bool,
        near_side: str,
        tick_len: float,
    ) -> None:
        """``"Ma"`` 单位标签：放在窗口**较老一端的外侧**，背离轨道生长。

        偏移若落在窗口内侧，它会与最老端的刻度数字（``window_hi`` 本身就是候选
        刻度）水平重叠，而单位标签不参与任何碰撞过滤。因此锚点取在轨道边缘之外，
        偏移量按显示像素给出（与字号相关），并用 ``ha``/``va`` 让文本从锚点背离
        轨道延伸，这样不会与任何刻度数字相交；轨道在时间维上退化成一个点时不产出
        单位标签。
        """
        p = self.params
        fontsize = float(p["label_size"]) * 0.92
        dpi = float(self.host_ax.figure.dpi)
        px_old = float(to_display(window_hi))
        px_young = float(to_display(window_lo))
        if abs(px_young - px_old) < 1e-9:
            return
        data_old = self.spec.age_to_data(window_hi)
        data_young = self.spec.age_to_data(window_lo)
        data_per_px = (data_young - data_old) / (px_young - px_old)
        away = 1.0 if px_old >= px_young else -1.0  # 外侧在显示空间的符号
        gap_px = 2.0 + 0.5 * fontsize * dpi / 72.0
        unit_value = data_old + away * gap_px * data_per_px
        if horizontal:
            y_edge = 1.0 if near_side == "top" else 0.0
            direction = -1.0 if near_side == "top" else 1.0
            unit = mtext.Text(
                unit_value,
                y_edge + direction * (tick_len + 0.02),
                "Ma",
                ha="left" if away > 0 else "right",
                va="top" if direction < 0 else "bottom",
                fontsize=fontsize,
                color="black",
                clip_on=False,
            )
        else:
            x_edge = 1.0 if near_side == "right" else 0.0
            direction = -1.0 if near_side == "right" else 1.0
            unit = mtext.Text(
                x_edge + direction * (tick_len + 0.02),
                unit_value,
                "Ma",
                ha="right" if direction < 0 else "left",
                va="bottom" if away > 0 else "top",
                fontsize=fontsize,
                color="black",
                clip_on=False,
            )
        unit.set_zorder(3)
        self.geo_ax.add_artist(unit)
        self.artists.append(unit)

    # -- 标签布局（粗略 / 精确，5.4）---------------------------------------

    def relayout(self, *, precise: bool, renderer=None) -> None:
        """重跑标签布局；``precise=True`` 时基于 renderer 实测包围盒降级。"""
        p = self.params
        items = self._label_items
        if not items:
            self.labels_shortened = self.labels_rotated = False
            self.labels_hidden = 0
            return
        dpi = self.host_ax.figure.dpi
        if precise and renderer is None:
            get_renderer = getattr(self.host_ax.figure.canvas, "get_renderer", None)
            renderer = get_renderer() if callable(get_renderer) else None

        def measure(item: LabelItem, text: str):
            if precise:
                # 不可见 Text 的 get_window_extent 返回 1×1 假值：测量期间强制可见。
                saved_rotation = item.artist.get_rotation()
                was_visible = item.artist.get_visible()
                item.artist.set_rotation(0.0)
                item.artist.set_visible(True)
                item.artist.set_text(text)
                size = measure_text_size(item.artist, renderer)
                item.artist.set_rotation(saved_rotation)
                item.artist.set_visible(was_visible)
                return size
            return estimate_text_size(text, float(p["label_size"]), dpi)

        # 碰撞比较在像素空间进行：先把标签中心换算为显示坐标。
        to_display = self.geo_ax.transData.transform
        for item in items:
            center_px = to_display(item.center)
            item.px_center = (float(center_px[0]), float(center_px[1]))

        # 时间维边界 = 轨道自身矩形在时间维上的像素范围：标签不得越出。
        track_bbox = self.geo_ax.get_window_extent()
        time_bounds_px: tuple[float, float]
        if self.spec.time_axis == "x":
            time_bounds_px = (float(track_bbox.x0), float(track_bbox.x1))
        else:
            time_bounds_px = (float(track_bbox.y0), float(track_bbox.y1))

        shortened, rotated, hidden = apply_label_degradation(
            items,
            measure=measure,
            abbreviate=bool(p["abbreviate"]),
            time_bounds_px=time_bounds_px,
        )
        self.labels_shortened, self.labels_rotated, self.labels_hidden = shortened, rotated, hidden
        inverse = self.geo_ax.transData.inverted()
        for item in items:
            item.final_center = item.center
            if item.visible and item.placed_px != item.px_center:
                # 边缘区间：把夹紧后的像素位置换算回数据坐标（只改时间维）。
                shifted = inverse.transform(item.placed_px)
                if self.spec.time_axis == "x":
                    item.final_center = (float(shifted[0]), item.center[1])
                else:
                    item.final_center = (item.center[0], float(shifted[1]))
            item.artist.set_text(item.text)
            item.artist.set_rotation(item.rotation)
            item.artist.set_position(item.final_center)
            item.artist.set_visible(item.visible)

        if precise and renderer is not None:
            self._drop_labels_below_tick_texts(items, renderer)

    def _drop_labels_below_tick_texts(self, items, renderer) -> None:
        """precise 布局的收尾：可见名若与顶部边界刻度数字相交，沿厚度方向下移脱离。

        边界刻度数字统一贴在条带顶带（4.6）；行高不足（矮面板）时该带会与
        同行的 rank 名字形相交。名只做厚度方向避让：时间维中心与降级结果都不变，
        且只有实测相交的名才移动（行高充裕的布局不受影响）。

        位移轴按 ``spec.time_axis`` 选择：水平轨道（time_axis="x"）沿 y 避让，
        垂直轨道（time_axis="y"）沿 x 避让。
        """
        label_artists = {id(i.artist) for i in items}
        tick_texts = [
            a
            for a in self.artists
            if isinstance(a, mtext.Text) and a.get_visible() and id(a) not in label_artists
        ]
        if not tick_texts:
            return
        if self.spec.time_axis == "x":
            lo, hi = sorted(float(v) for v in self.geo_ax.get_ylim())
            ax_span_px = self.geo_ax.get_window_extent().height
        else:
            lo, hi = sorted(float(v) for v in self.geo_ax.get_xlim())
            ax_span_px = self.geo_ax.get_window_extent().width
        if ax_span_px <= 0:
            return
        for item in items:
            if not item.visible:
                continue
            le = item.artist.get_window_extent(renderer)
            shift_px = 0.0
            for tick_text in tick_texts:
                te = tick_text.get_window_extent(renderer)
                if le.x0 < te.x1 and te.x0 < le.x1 and le.y0 < te.y1 and te.y0 < le.y1:
                    shift_px = max(shift_px, le.y1 - te.y0)
            if shift_px <= 0:
                continue
            cx, cy = item.final_center
            if self.spec.time_axis == "x":
                # 水平轨道：沿 y（厚度方向）避让
                new_cy = max(cy - shift_px / ax_span_px * (hi - lo), min(lo, hi) + 0.05 * (hi - lo))
                item.final_center = (cx, new_cy)
            else:
                # 垂直轨道：沿 x（厚度方向）避让
                new_cx = max(cx - shift_px / ax_span_px * (hi - lo), min(lo, hi) + 0.05 * (hi - lo))
                item.final_center = (new_cx, cy)
            item.artist.set_position(item.final_center)


def _tick_placement(
    px: float, width_px: float, edge_lo: float, edge_hi: float, horizontal: bool
) -> tuple[str, float, float]:
    """刻度数字在时间维上的 ``(对齐方式, 包围盒下沿, 包围盒上沿)``（显示像素）。

    中心对齐会让贴边的数字越出轨道矩形，所以按内沿对齐：``px`` 是锚点的
    显示位置，``width_px`` 是该数字的估算宽度。返回的包围盒用于同优先级
    （从老到新、保留较老者）的粘连检查。
    """
    half = 0.5 * width_px
    center_box = (px - half, px + half)
    if px - half < edge_lo:
        near, far = ("left" if horizontal else "bottom"), (px, px + width_px)
    elif px + half > edge_hi:
        near, far = ("right" if horizontal else "top"), (px - width_px, px)
    else:
        near, far = "center", center_box  # 两个方向在此分支同为居中（RUF034）
    return (near, float(far[0]), float(far[1]))


def _background_hex(geo_ax) -> str:
    """轨道 Axes 的背景色（自动标签对比色用它做合成底色，5.4）。"""
    rgba = geo_ax.get_facecolor()
    r, g, b = (max(0.0, min(1.0, float(c))) for c in rgba[:3])
    return matplotlib.colors.to_hex((r, g, b))

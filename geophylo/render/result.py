"""``GeoAxisResult`` 生命周期与宿主 Axes 状态快照（规范 4.5/5.1）。

key 注册表以宿主 Axes 对象为键的弱引用映射，作用域限定于单个宿主 Axes，
避免 Axes 回收后注册表泄漏。注册表不保证线程安全：并发绘制由调用方串行化。
"""

from __future__ import annotations

import math
import weakref
from collections.abc import Callable, Sequence
from typing import TYPE_CHECKING, Any

import matplotlib.transforms as mtransforms

from ..exceptions import CoordinateError, InvalidRangeError
from ..validation import BORDERS, TICK_STYLES, require_bool, require_number

if TYPE_CHECKING:  # pragma: no cover
    from matplotlib.axes import Axes

__all__ = [
    "AxesState",
    "GeoAxisResult",
    "lookup_track",
    "register_track",
    "release_track",
    "remove_all",
]

# 渲染参数全集（update() 只接受这些）；spec/position/timescale 不可原地更新。
RENDER_PARAMS = (
    "ranks",
    "thickness_ratio",
    "min_age",
    "max_age",
    "fill",
    "alpha",
    "label",
    "label_size",
    "label_color",
    "skip",
    "abbreviate",
    "border",
    "border_width",
    "border_color",
    "rotation",
    "tick_style",
    "tick_max_count",
)
FORBIDDEN_UPDATE_PARAMS = ("spec", "position", "timescale")


def _require_tick_max_count(name: str, value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise InvalidRangeError(f"{name} 必须是正整数，得到 {value!r}")
    return value


def _require_color_str(name: str, value: Any) -> None:
    if not isinstance(value, str):
        raise CoordinateError(f"{name} 必须是字符串，得到 {value!r}")


def _require_skip_names(name: str, value: Any) -> tuple[str, ...]:
    if isinstance(value, str) or not isinstance(value, Sequence):
        raise CoordinateError(f"{name} 必须是字符串序列（不可为单个字符串），得到 {value!r}")
    names = tuple(value)
    for item in names:
        if not isinstance(item, str):
            raise CoordinateError(f"{name} 的元素必须是字符串，得到 {item!r}")
    return names


def validate_render_params(merged: dict[str, Any]) -> None:
    """对合并后的渲染参数做与公共入口一致的取值域校验（4.4/4.11）。

    ``update()`` 与创建路径共用同一套约束：任何非法取值在这里抛公共异常，
    而不是下渗到 Matplotlib 后以原始 ``ValueError`` 冒泡。
    """
    if "thickness_ratio" in merged:
        require_number(
            "thickness_ratio",
            merged["thickness_ratio"],
            minimum=0.0,
            maximum=0.5,
            exclude_minimum=True,
        )
    if "alpha" in merged:
        require_number("alpha", merged["alpha"], minimum=0.0, maximum=1.0)
    if "label_size" in merged:
        require_number("label_size", merged["label_size"], minimum=0.0, exclude_minimum=True)
    if "border_width" in merged:
        require_number("border_width", merged["border_width"], minimum=0.0)
    if "rotation" in merged:
        require_number("rotation", merged["rotation"])
    if "tick_max_count" in merged:
        _require_tick_max_count("tick_max_count", merged["tick_max_count"])
    for name in ("fill", "label", "abbreviate"):
        if name in merged:
            require_bool(name, merged[name])
    if "label_color" in merged:
        _require_color_str("label_color", merged["label_color"])
    if "border_color" in merged:
        _require_color_str("border_color", merged["border_color"])
    if "skip" in merged:
        _require_skip_names("skip", merged["skip"])


class AxesState:
    """宿主 Axes 的视图状态快照（limits、scale、autoscale 与 dataLim 包围盒）。"""

    def __init__(self, ax: Axes) -> None:
        self.xlim = tuple(ax.get_xlim())
        self.ylim = tuple(ax.get_ylim())
        self.xscale = ax.get_xscale()
        self.yscale = ax.get_yscale()
        self.autoscalex_on = ax.get_autoscalex_on()
        self.autoscaley_on = ax.get_autoscaley_on()
        self.datalim = ax.dataLim.frozen()

    def restore_to(self, ax: Axes) -> None:
        ax.set_xlim(*self.xlim)
        ax.set_ylim(*self.ylim)
        ax.set_xscale(self.xscale)
        ax.set_yscale(self.yscale)
        ax.set_autoscalex_on(self.autoscalex_on)
        ax.set_autoscaley_on(self.autoscaley_on)
        ax.dataLim = mtransforms.Bbox.from_bounds(*self.datalim.bounds)

    def matches(self, ax: Axes, *, tol: float = 1e-12) -> bool:
        """当前视图状态是否与本快照一致（浮点容差比较）。"""
        return (
            _bbox_close(ax.get_xlim(), self.xlim, tol)
            and _bbox_close(ax.get_ylim(), self.ylim, tol)
            and ax.get_xscale() == self.xscale
            and ax.get_yscale() == self.yscale
            and ax.get_autoscalex_on() == self.autoscalex_on
            and ax.get_autoscaley_on() == self.autoscaley_on
            and _bbox_close(ax.dataLim, self.datalim, tol)
        )


def _bbox_close(a: Any, b: Any, tol: float) -> bool:
    """比较两个包围盒或两组 limits：``Bbox`` 取其 ``bounds``，序列原样比较。

    空数据 Axes 的 ``dataLim`` 是 ``(inf, inf, -inf, -inf)``：直接相减会得到
    ``inf - inf = nan`` 并抛出 ``RuntimeWarning``，且把"未改动"误判为"已改动"，
    令自动还原失效。这里先做精确相等比较（覆盖同向无穷），再要求两侧
    都是有限值才做容差比较。
    """
    a_bounds = a.bounds if isinstance(a, mtransforms.Bbox) else tuple(a)
    b_bounds = b.bounds if isinstance(b, mtransforms.Bbox) else tuple(b)
    if len(a_bounds) != len(b_bounds):
        return False
    for x, y in zip(a_bounds, b_bounds, strict=False):
        if x == y:  # 同向无穷（未设置数据区间的 dataLim）也算一致
            continue
        if not (math.isfinite(x) and math.isfinite(y)):
            return False
        if abs(x - y) > tol:
            return False
    return True


class GeoAxisResult:
    """访问轨道 Axes、Artist 列表与生命周期方法的唯一入口（ADR-3）。

    ``add_geo_axis()`` 不可链式；调用方通过 ``result.geo_ax`` 访问轨道 Axes。

    ADR-3 记录见 ``docs/adr/ADR-3-result-object-not-axes.md``。
    """

    def __init__(
        self,
        *,
        host_ax: Axes,
        geo_ax: Axes,
        artists: list[Any],
        spec: Any,
        key: str | None,
        position: str,
        params: dict[str, Any],
        rebuild: Callable[[], None],
        sync_extra: Callable[[], None] | None = None,
        polar: bool = False,
        owns_axes: bool = True,
        preserved: bool = True,
    ) -> None:
        self.host_ax = host_ax
        self.geo_ax = geo_ax
        self.artists = artists
        self.spec = spec
        self.key = key
        #: 布局诊断：记录标签降级到哪一步，供用户诊断与测试断言。
        self.labels_shortened: bool = False
        self.labels_rotated: bool = False
        self.labels_hidden: int = 0
        #: 布局诊断：``sync()`` 因空间不足以完成厚度重分配而保持上次布局时为
        #: ``True``（规范 4.5/5.1 的「标签降级诊断通道」记录）。
        self.sync_degraded: bool = False
        #: 刻度诊断：本轮绘制中被抽稀（``tick_style="ages"`` 的
        #: ``tick_max_count`` 上限）或像素间距过滤丢弃的候选刻度年龄数。
        #: ``tick_style="none"`` 时为 ``0``；``tick_style="boundaries"`` 不受
        #: 硬上限约束，只可能由像素间距造成（规范 4.6）。
        self.ticks_dropped: int = 0
        self.position = position
        self.params = dict(params)
        self._rebuild = rebuild
        self._sync_extra = sync_extra
        self._polar = polar
        self._owns_axes = owns_axes
        self._preserved = preserved
        self._state = AxesState(host_ax)
        self._finalized = False
        self._cid: int | None = None
        self._in_draw = False
        self._last_host_limits = (tuple(host_ax.get_xlim()), tuple(host_ax.get_ylim()))
        figure = host_ax.figure
        self._last_fig_size = tuple(
            figure.get_size_inches() if hasattr(figure, "get_size_inches") else (0.0, 0.0)
        )

    # -- draw_event 回调 ---------------------------------------------------

    def attach_draw_callback(self) -> None:
        """注册 draw_event 回调：检测到宿主变化时自动 sync 并做精确标签布局。"""
        self._cid = self.host_ax.figure.canvas.mpl_connect("draw_event", self._on_draw)

    def _on_draw(self, event) -> None:
        figure = self.host_ax.figure
        if self._in_draw or event.canvas is not figure.canvas:
            return
        self._in_draw = True
        try:
            limits = (tuple(self.host_ax.get_xlim()), tuple(self.host_ax.get_ylim()))
            get_size = getattr(figure, "get_size_inches", None)
            size = tuple(get_size()) if callable(get_size) else (0.0, 0.0)
            if limits != self._last_host_limits or size != self._last_fig_size:
                self._last_host_limits = limits
                self._last_fig_size = size
                if not self._polar:
                    self.sync()
            if not self._finalized:
                self.relayout(precise=True)
        finally:
            self._in_draw = False

    # -- 生命周期 ----------------------------------------------------------

    def update(self, **kwargs: Any) -> GeoAxisResult:
        """原地重建本轨道的全部 Artist（不新增轨道、不触碰注册表与其他轨道）。

        只接受渲染参数；``spec``/``position``/``timescale`` 变化意味着坐标语义
        或承载 Axes 变化，传参即抛 ``CoordinateError``。校验与几何预检全部通过
        后才提交新参数：失败的 ``update()`` 不改动任何状态（原 Artist 与原
        参数保持不变）。
        """
        from ..validation import (
            normalize_ranks,
            require_age_window,
            require_choice,
        )

        for name in self._forbidden_update_params():
            if name in kwargs:
                raise CoordinateError(
                    f"update() 不支持原地修改 {name!r}：坐标语义或承载 Axes 的变化会留下"
                    "与新契约不一致的轨道状态；请 remove() 后重新创建"
                )
        unknown = set(kwargs) - self._update_allowed_params()
        if unknown:
            raise CoordinateError(f"update() 只接受渲染参数，得到未知参数 {sorted(unknown)!r}")
        merged = dict(self.params)
        merged.update(kwargs)
        if "ranks" in merged:
            merged["ranks"] = normalize_ranks(merged["ranks"])
        require_age_window(
            merged["min_age"],
            merged["max_age"],
            spec_min=self.spec.age_range[0],
            spec_max=self.spec.age_range[1],
        )
        for name in ("border", "tick_style"):
            if name in merged:
                require_choice(
                    name,
                    merged[name],
                    {
                        "border": BORDERS,
                        "tick_style": TICK_STYLES,
                    }[name],
                )
        validate_render_params(merged)
        self._precheck_update(merged)  # 几何预检失败时抛异常，不提交、不重建
        self.params = merged
        self._rebuild()  # 重建时已重跑粗略布局并刷新布局诊断字段
        return self

    def _forbidden_update_params(self) -> tuple[str, ...]:
        return FORBIDDEN_UPDATE_PARAMS

    def _update_allowed_params(self) -> set[str]:
        """本路径可原地更新的渲染参数全集（子类可收窄或扩充）。"""
        return set(RENDER_PARAMS)

    def _precheck_update(self, merged: dict[str, Any]) -> None:
        """提交新参数前的几何预检；失败抛公共异常且不改动任何状态。"""
        return None

    def sync(self) -> None:
        """宿主 limits 或物理尺寸变化后：重对齐轨道数据范围并重排轨道厚度。"""
        if not self._polar:
            time_axis = self.spec.time_axis
            if time_axis == "x":
                self.geo_ax.set_xlim(self.host_ax.get_xlim())
                self.geo_ax.set_ylim(0.0, 1.0)
            else:
                self.geo_ax.set_ylim(self.host_ax.get_ylim())
                self.geo_ax.set_xlim(0.0, 1.0)
        if self._sync_extra is not None:
            self._sync_extra()

    def relayout(self, *, precise: bool, renderer=None) -> None:
        """重跑标签布局；``precise=True`` 时使用 renderer 实测包围盒。"""
        raise NotImplementedError

    def finalize(self) -> None:
        """立即执行一次精确标签布局并固化（取消后续自动重排）。

        先基于当前 renderer 实测包围盒跑一次精确布局，再冻结后续 draw_event
        自动重排。
        """
        self.relayout(precise=True)
        self._finalized = True

    def remove(self) -> None:
        """移除本库新增的全部 Artist 并断开回调。

        宿主状态还原：仅当宿主视图**仍然**与创建时快照一致时才自动
        ``restore()``——此时还原是幂等的、对用户不可见的清理。若用户在本轨道
        存活期间改动了 limits/scale（缩放、``invert_axes`` 等），这些设置被
        保留，``remove()`` 不做反向改写；确有需要回到创建时刻时显式调用
        ``restore()``。``preserve_axes_state=False`` 时从不自动还原。
        """
        if self._cid is not None:
            self.host_ax.figure.canvas.mpl_disconnect(self._cid)
            self._cid = None
        release_track(self)
        for artist in list(self.artists):
            try:
                artist.remove()
            except (NotImplementedError, ValueError):  # pragma: no cover
                pass
        self.artists = []
        if getattr(self, "_owns_axes", True):
            # 线性轨道的 inset Axes 由本库创建，一并移除；环形路径的 geo_ax 是
            # 用户传入的极坐标 Axes，绝不触碰（规范 4.8）。
            try:
                self.geo_ax.remove()
            except (NotImplementedError, ValueError):  # pragma: no cover
                pass
        # 副作用契约：仅在没有用户改动需要保护时才自动还原宿主状态。
        if self._preserved and self._state.matches(self.host_ax):
            self.restore()

    def restore(self) -> None:
        """按创建时的快照还原宿主 Axes 状态。"""
        self._state.restore_to(self.host_ax)


# --------------------------------------------------------------------------
# key 注册表（以宿主 Axes 为键的弱引用映射）
# --------------------------------------------------------------------------

_registry: weakref.WeakKeyDictionary[Axes, dict[str, GeoAxisResult]] = weakref.WeakKeyDictionary()
# 匿名轨道（key=None）按宿主 Axes 分组存储，remove_all 同时清理两者。
_anonymous: weakref.WeakKeyDictionary[Axes, list[GeoAxisResult]] = weakref.WeakKeyDictionary()


def _axes_table(ax: Axes) -> dict[str, GeoAxisResult]:
    return _registry.setdefault(ax, {})


def _anonymous_list(ax: Axes) -> list[GeoAxisResult]:
    return _anonymous.setdefault(ax, [])


def lookup_track(ax: Axes, key: str) -> GeoAxisResult | None:
    return _axes_table(ax).get(key)


def register_track(result: GeoAxisResult) -> None:
    if result.key is not None:
        _axes_table(result.host_ax)[result.key] = result
    else:
        _anonymous_list(result.host_ax).append(result)


def release_track(result: GeoAxisResult) -> None:
    if result.key is not None:
        table = _registry.get(result.host_ax)
        if table is not None and table.get(result.key) is result:
            del table[result.key]
    else:
        anon = _anonymous.get(result.host_ax)
        if anon is not None:
            try:
                anon.remove(result)
            except ValueError:  # pragma: no cover
                pass


def remove_all(ax: Axes) -> int:
    """清除宿主 Axes 上的全部轨道（含匿名轨道），返回移除数量。"""
    table = _registry.get(ax, {})
    results = list(table.values())
    results.extend(_anonymous.get(ax, []))
    for result in results:
        result.remove()
    table.clear()
    if ax in _anonymous:
        _anonymous[ax].clear()
    return len(results)

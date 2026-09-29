"""``add_geo_ring()``：原生极坐标 Axes 上的地质时间环（规范 4.8/5.3，实验性）。

五条硬约束：只支持单一 rank；只支持原生极坐标 Axes；半径映射与树同源
（环段半径一律由 ``spec.age_to_radius(age, radius_range=band)`` 给出，实现不
另立第二套映射）；``band`` 决定环段占据的径向区间（参与几何计算，不只是参与
校验）；不修改极坐标 Axes 的径向视野（不调用 ``set_rlim()``/``set_rorigin()``）。

``band`` 的语义（与 ``docs/user-guide.*.md`` 第 9.2 节逐字一致）：换算后的环带
``(r_inner, r_outer) = spec.band_radius(band, unit=band_unit)`` 是 ``spec.age_range``
的映射值域——``age_range[1]``（最老）落在 ``r_inner``、``age_range[0]``（最年轻）
落在 ``r_outer``。绘制窗口 ``min_age/max_age`` 只裁剪**哪些区间被画出**，不重标
环上的半径刻度；因此同一半径在环上与在树上对应同一个年龄。让环与树在径向上逐点
重合的办法是令环带等于树的半径范围（``band=(0.0, 1.0)``，或 ``band_unit="data"``
时等于 ``radius_range``）。
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import TYPE_CHECKING, Literal

import matplotlib.projections.polar
import matplotlib.text as mtext

from ..coordinate.radial import RadialSpec
from ..exceptions import (
    AxesTypeError,
    CoordinateError,
    InvalidRadiusError,
    InvalidRankError,
)
from ..timescale import Timescale
from ..validation import require_age_window, require_bool, require_choice, require_number
from .labels import abbreviate_text, auto_label_color
from .result import GeoAxisResult, _require_skip_names, lookup_track, register_track

if TYPE_CHECKING:  # pragma: no cover
    from matplotlib.axes import Axes

__all__ = ["add_geo_ring"]


def add_geo_ring(
    ax: Axes,
    *,
    spec: RadialSpec,
    rank: str,
    band: tuple[float, float] = (0.9, 1.0),
    band_unit: Literal["radial_fraction", "data"] = "radial_fraction",
    timescale: Timescale | None = None,
    min_age: float | None = None,
    max_age: float | None = None,
    fill: bool = True,
    alpha: float = 1.0,
    label: bool = True,
    label_size: float = 5.0,
    skip: Sequence[str] | None = None,
    abbreviate: bool = True,
    rotation: float = 0.0,
    rotate_labels: bool = False,
    key: str | None = None,
) -> GeoAxisResult:
    """在原生极坐标 Axes 上绘制地质时间环，返回 ``GeoAxisResult``。

    环带内任意半径所对应的年龄由
    ``spec.radius_to_age(radius, radius_range=spec.band_radius(band, band_unit))``
    给出（同一条线性映射的值域限制，不另立第二套映射）；角度取自
    ``spec.theta_range``（每个地质时间区间在角度上覆盖完整的 ``theta_range``，
    只在半径上区分）。``band`` 决定环段占据的径向区间：``spec.age_range`` 被
    映射到换算后的 ``(r_inner, r_outer)``，``age_range[1] → r_inner``、
    ``age_range[0] → r_outer``；``min_age/max_age`` 只做裁剪，不重标刻度。
    环段高度恒为正（``age_to_radius`` 随年龄单调递减，较年轻的边界给出较大的
    半径）。返回值中 ``host_ax`` 与 ``geo_ax`` 同为传入的极坐标 Axes；
    ``sync()`` 只重新校验环带是否仍在 ``rlim`` 内；``restore()`` 是空操作。
    """
    if not isinstance(ax, matplotlib.projections.polar.PolarAxes):
        raise AxesTypeError(
            f"add_geo_ring 只支持原生 Matplotlib 极坐标 Axes，得到 {type(ax).__name__}；"
            "iplotx 的 radial 布局在笛卡尔 Axes 上完成，与 PolarAxes 的 rlim 没有"
            "定义好的对应关系，不属于本函数的适用范围（规范 4.8）"
        )
    if not isinstance(spec, RadialSpec):
        raise CoordinateError(f"spec 必须是 RadialSpec，得到 {type(spec).__name__}")
    if isinstance(rank, (list, tuple, set, frozenset)) or not isinstance(rank, str):
        raise InvalidRankError(
            f"rank 必须是单个字符串；实验性时间环只支持单一 rank（多 rank 尚无成立"
            f"的布局模型），得到序列 {rank!r}"
        )
    from ..validation import CORE_RANKS

    if rank not in CORE_RANKS:
        raise InvalidRankError(f"非法 rank {rank!r}；核心 rank 为 {list(CORE_RANKS)!r}")
    require_choice("band_unit", band_unit, ("radial_fraction", "data"), exc=InvalidRadiusError)
    require_bool("fill", fill)
    require_bool("label", label)
    require_bool("rotate_labels", rotate_labels)
    require_bool("abbreviate", abbreviate)
    require_number("alpha", alpha, minimum=0.0, maximum=1.0)
    require_number("label_size", label_size, minimum=0.0, exclude_minimum=True)
    require_number("rotation", rotation)
    if key is not None and not isinstance(key, str):
        raise CoordinateError(f"key 必须是字符串或 None，得到 {key!r}")
    window = require_age_window(
        min_age, max_age, spec_min=spec.age_range[0], spec_max=spec.age_range[1]
    )
    # 入参类型校验与线性路径保持一致
    if timescale is not None and not isinstance(timescale, Timescale):
        raise CoordinateError(
            f"timescale 必须是 Timescale 或 None，得到 {type(timescale).__name__}"
        )
    skip_names = _require_skip_names("skip", skip) if skip is not None else ()
    # band 类型校验：非数值元素在 spec.band_radius 之前即抛公共异常
    if not isinstance(band, (tuple, list)) or len(band) != 2:
        raise InvalidRadiusError(f"band 必须是 (下, 上) 二元组，得到 {band!r}")
    try:
        band_tuple = tuple(float(v) for v in band)
    except (TypeError, ValueError) as exc:
        raise InvalidRadiusError(f"band 的元素必须是数值，得到 {band!r}") from exc

    params: dict = dict(
        ranks=(rank,),
        band=band_tuple,
        band_unit=band_unit,
        min_age=float(window[0]),
        max_age=float(window[1]),
        fill=fill,
        alpha=float(alpha),
        label=label,
        label_size=float(label_size),
        skip=skip_names,
        abbreviate=abbreviate,
        rotation=float(rotation),
        rotate_labels=rotate_labels,
    )
    if key is not None:
        existing = lookup_track(ax, key)
        if existing is not None:
            if existing.spec != spec:
                raise CoordinateError(
                    f"key={key!r} 已存在且绑定了不同的 spec；请 remove() 后重新 add_geo_ring()"
                )
            # band_unit 与 rank/ranks（单 rank 契约）同属创建期语义，不可原地
            # 更新：从幂等更新参数中剔除，而不是让 update() 抛错（否则带 key
            # 的重复调用必然失败）。
            updatable = {
                k: v
                for k, v in params.items()
                if k in existing.params and k not in ("band_unit", "ranks")
            }
            return existing.update(**updatable)

    timescale = timescale if timescale is not None else Timescale()
    result = _PolarResult(ax=ax, timescale=timescale, params=params, spec=spec, key=key)
    result.rebuild()
    register_track(result)
    return result


class _PolarResult(GeoAxisResult):
    """极坐标时间环的重建与校验实现（私有）。"""

    def __init__(self, *, ax, timescale, params, spec, key) -> None:
        self._timescale = timescale
        # 最近一次 ``_validate_band()`` 得到的环带值域 ``(r_inner, r_outer)``：
        # 它是环段半径的唯一值域。
        self._band_domain: tuple[float, float] = (0.0, 0.0)
        # 环形路径不存在 inset Axes：host_ax 与 geo_ax 同为传入的极坐标 Axes，
        # 环段 Artist 直接绘制其上（4.8 返回值字段映射）。
        super().__init__(
            host_ax=ax,
            geo_ax=ax,
            artists=[],
            spec=spec,
            key=key,
            position="ring",
            params=dict(params),
            rebuild=self.rebuild,
            polar=True,
            owns_axes=False,
        )
        self.attach_draw_callback()

    # -- 环带校验 ----------------------------------------------------------

    def _validate_band(self, params: dict) -> tuple[float, float]:
        """换算环带并校验其落在当前 ``rlim`` 内（4.8 硬约束 4）；只读，不改状态。"""
        band_inner, band_outer = self.spec.band_radius(params["band"], unit=params["band_unit"])
        if band_inner >= band_outer:
            raise InvalidRadiusError(f"require r_inner < r_outer, got {band_inner}, {band_outer}")
        # 极坐标 Axes 的 r 限制即 ylim（set_rlim 的配对 getter）。
        r_min, r_max = (float(v) for v in self.geo_ax.get_ylim())
        if band_inner < r_min - 1e-12 or band_outer > r_max + 1e-12:
            raise InvalidRadiusError(
                f"换算后的环带 [{band_inner}, {band_outer}] 落在当前 rlim=[{r_min}, {r_max}] 之外；"
                "本函数不修改极坐标 Axes 的径向视野（不调用 set_rlim/set_rorigin），"
                "请调整 band 或先扩大 rlim"
            )
        return band_inner, band_outer

    def _band_radii(self) -> tuple[float, float]:
        return self._validate_band(self.params)

    # -- 重建 --------------------------------------------------------------

    def relayout(self, *, precise: bool, renderer=None) -> None:
        """环形标签按 ``theta_range`` 中点确定性放置，无降级布局流程。"""
        return None

    def rebuild(self) -> None:
        p = self.params
        # 环带校验在清理旧 Artist 之前执行（4.8 硬约束 4）：失败路径不留下
        # 被清空的轨道。返回值同时是本函数唯一的半径值域（band 必须参与几何
        # 计算，而不只参与校验）。
        band_domain = self._validate_band(self.params)
        for artist in list(self.artists):
            try:
                artist.remove()
            except (NotImplementedError, ValueError):  # pragma: no cover
                pass
        self.artists = []
        self._band_domain = band_domain

        window_lo, window_hi = float(p["min_age"]), float(p["max_age"])
        theta_0, theta_1 = self.spec.theta_range
        theta_center = (theta_0 + theta_1) / 2.0
        theta_width = theta_1 - theta_0

        for interval in self._timescale.iter_intervals(
            ranks=list(p["ranks"]), min_age=window_lo, max_age=window_hi
        ):
            older = min(interval.older_ma, window_hi)
            younger = max(interval.younger_ma, window_lo)
            if older <= younger + 1e-12:
                continue  # 零宽片段：跳过
            if p["fill"]:
                # 半径映射来自 RadialSpec（限制到环带值域），不在此处重算
                # （4.9 一致性契约）。age_to_radius 随年龄单调递减，所以
                # 较年轻的年龄给出较大的半径：bottom = r_older < height 终点
                # r_younger，height 恒为正。
                r_younger = self.spec.age_to_radius(younger, radius_range=band_domain)
                r_older = self.spec.age_to_radius(older, radius_range=band_domain)
                container = self.geo_ax.bar(
                    theta_center,
                    r_younger - r_older,
                    width=theta_width,
                    bottom=r_older,
                    align="center",
                    color=interval.color,
                    alpha=float(p["alpha"]),
                    edgecolor="none",
                )
                self.artists.extend(container.patches)
            if p["label"] and interval.name not in p["skip"]:
                r_mid = (
                    self.spec.age_to_radius(older, radius_range=band_domain)
                    + self.spec.age_to_radius(younger, radius_range=band_domain)
                ) / 2.0
                text = abbreviate_text(interval) if p["abbreviate"] else interval.name
                label_rotation = float(p["rotation"])
                if p["rotate_labels"]:
                    # 沿半径方向自动对齐：极坐标约定角度自正 x 轴逆时针为正，
                    # 屏幕上径向方向即 theta_center 的角度（度）。rotation 作为
                    # 固定偏移叠加（4.8：同时指定时以自动对齐为基准）。
                    label_rotation = math.degrees(theta_center) + float(p["rotation"])
                artist = mtext.Text(
                    theta_center,
                    r_mid,
                    text,
                    ha="center",
                    va="center",
                    fontsize=float(p["label_size"]),
                    color=auto_label_color(
                        interval.color,
                        alpha=float(p["alpha"]),
                        background=_polar_background(self.geo_ax),
                    ),
                    rotation=label_rotation,
                    clip_on=True,
                )
                self.geo_ax.add_artist(artist)
                self.artists.append(artist)
        self.labels_shortened = False
        self.labels_rotated = bool(p["rotate_labels"])
        self.labels_hidden = 0

    # 环形路径的 sync 语义（4.8）：不改任何 limits，只重新校验环带仍在 rlim 内。
    def sync(self) -> None:
        self._band_radii()

    def _forbidden_update_params(self) -> tuple[str, ...]:
        # rank/ranks 单 rank 契约（4.8 硬约束 1）与 band_unit（环带的创建期
        # 单位语义）不可原地更新；timescale/spec 同理。
        return ("spec", "rank", "ranks", "band_unit", "timescale")

    def _update_allowed_params(self) -> set[str]:
        # 环形路径只允许更新创建时已有的渲染参数（band、rotate_labels、
        # fill/alpha/label/label_size/skip/abbreviate/rotation/min_age/max_age）；
        # ranks 与 band_unit 属创建期语义（见 _forbidden_update_params），线性
        # 轨道专用的 thickness_ratio/border*/tick_* 不在环上，一并拒绝。
        return set(self.params) - {"ranks", "band_unit"}

    def _precheck_update(self, merged: dict) -> None:
        band = merged.get("band")
        if band is not None:
            if len(band) != 2:
                raise InvalidRadiusError(f"band 必须是 (下, 上) 二元组，得到 {band!r}")
            self._validate_band(merged)

    def remove(self) -> None:
        """只移除环段 Artist 并断开回调，绝不触碰宿主极坐标状态。"""
        if self._cid is not None:
            self.geo_ax.figure.canvas.mpl_disconnect(self._cid)
            self._cid = None
        from .result import release_track

        release_track(self)
        for artist in list(self.artists):
            try:
                artist.remove()
            except (NotImplementedError, ValueError):  # pragma: no cover
                pass
        self.artists = []

    def restore(self) -> None:
        """环形路径是空操作：契约本就禁止修改宿主径向视野（4.8）。"""
        return None


def _polar_background(ax) -> str:
    import matplotlib.colors

    rgba = ax.get_facecolor()
    r, g, b = (max(0.0, min(1.0, float(c))) for c in rgba[:3])
    return matplotlib.colors.to_hex((r, g, b))

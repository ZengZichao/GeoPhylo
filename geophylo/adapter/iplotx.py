"""iplotx 适配器（实验性）：从 ``TreeArtist`` 构造 ``CoordinateSpec``。

``spec_from_iplotx()`` 通过 ``artist.get_layout()`` 读取布局数据域，其余校验
逻辑与 Bio 侧一致，且同样**恒定产出 ``mode="root_distance"``**（iplotx
horizontal 布局的 x 同样是根距离）。它不接受 ``Axes``，因为 ``Axes`` 里没有
树的坐标信息。radial 布局被明确拒绝（4.8/6.2）。

布局读取按 iplotx 1.8 的公开结构实现（``get_layout()`` 返回 pandas
``DataFrame``，列为 ``_ipx_layout_0/1``、索引为节点），同时保留对旧版
``{节点: (x, y)}`` 字典布局的兼容。根距离基线优先取自树根节点的坐标
（``_ipx_internal_data["root"]``），取不到时回退为时间维最小值（horizontal
/right 布局的根在最小端）；纵向布局（根在最大端）依赖根节点坐标才能得到
正确的符号，回退路径仅对根在最小端的布局成立。
"""

from __future__ import annotations

import math
from collections.abc import Callable
from typing import Literal

from ..coordinate.spec import CoordinateSpec
from ..exceptions import AxesTypeError, CoordinateError
from ..validation import (
    require_linear_numeric_axes,
    require_time_axis,
    resolve_age_conversion,
)

__all__ = ["spec_from_iplotx"]


def spec_from_iplotx(
    artist,
    *,
    time_axis: Literal["x", "y"],
    age_conversion: float | Callable[[float], float],
    root_age: float | None = None,
) -> CoordinateSpec:
    """从 iplotx ``TreeArtist`` 构造 ``mode="root_distance"`` 的 ``CoordinateSpec``（实验性）。"""
    require_time_axis(time_axis)
    if not hasattr(artist, "get_layout") or not hasattr(artist, "axes"):
        raise CoordinateError(
            f"artist 必须是 iplotx 的 TreeArtist（暴露 .axes 与 get_layout()），"
            f"得到 {type(artist).__name__}"
        )
    if root_age is None:
        raise CoordinateError(
            "root_age 必填（根年龄来自外部时间校准结果，本库不接受 branch length "
            "大概率是 Ma 这类假设）"
        )
    if (
        isinstance(root_age, bool)
        or not isinstance(root_age, (int, float))
        or not math.isfinite(float(root_age))
        or float(root_age) < 0
    ):
        raise CoordinateError(f"root_age 必须是非负有限数值，得到 {root_age!r}")
    convert = resolve_age_conversion(age_conversion)  # 与 Bio 侧共用同一份解析

    _reject_radial(artist)

    layout = artist.get_layout()
    positions = _layout_positions(layout)
    if positions is None:
        raise CoordinateError(
            "无法从 TreeArtist.get_layout() 读取节点坐标；请核对其锁定的 iplotx 版本的布局对象结构"
        )
    # 旧版布局可能返回 {node: complex}，对 complex 迭代会抛 TypeError。
    # 先判 isinstance(pair, complex)，再判可迭代元素的复数。
    if any(
        isinstance(pair, complex)
        or (isinstance(pair, (tuple, list)) and any(isinstance(v, complex) for v in pair))
        for pair in positions.values()
    ):
        raise AxesTypeError(
            "检测到 iplotx radial 布局（极坐标形式的布局数据）；"
            "实验性 API 不承诺通过 add_geo_ring()/spec_from_iplotx() 适配 iplotx radial，"
            "环形树请按规范 6.3 的配方在原生极坐标 Axes 上自绘"
        )
    ax = artist.axes
    if ax is not None:
        import matplotlib.projections.polar

        if isinstance(ax, matplotlib.projections.polar.PolarAxes):
            raise AxesTypeError(
                "iplotx radial 布局不支持：宿主 Axes 是极坐标 Axes；环形树请按 6.3 配方自绘"
            )
        require_linear_numeric_axes(ax, name="artist.axes")

    time_values = [pos[0] if time_axis == "x" else pos[1] for pos in positions.values()]
    root_time = _root_time(artist, positions, time_axis, fallback=min(time_values))
    # age_conversion 必须作用在布局的根距离上（branch length 单位 → Ma）：
    # 省略换算会让 age_range 随单位缩放静默错位。
    ma_distances: list[float] = []
    for value in time_values:
        distance = abs(float(value) - root_time)
        ma = float(convert(distance))
        if not math.isfinite(ma) or ma < 0:
            raise CoordinateError(
                f"age_conversion 产生了非法的 Ma 距离 {ma!r}（布局根距离 {distance!r}）；"
                "换算结果必须非负且有限"
            )
        ma_distances.append(ma)
    max_distance = max(ma_distances, default=0.0)
    root = float(root_age)
    min_age = root - max_distance
    if min_age < 0:
        raise CoordinateError(
            f"布局数据域的最大根距离为 {max_distance!r}，超过 root_age={root}；"
            "请核对 root_age 或 age_conversion"
        )
    return CoordinateSpec.root_distance(
        time_axis=time_axis, age_range=(min_age, root), root_age=root
    )


def _reject_radial(artist) -> None:
    """iplotx 1.8 起可通过布局元数据直接识别 radial；旧版走复数坐标检测。"""
    internal = getattr(artist, "_ipx_internal_data", None)
    if isinstance(internal, dict):
        coord_system = internal.get("layout_coordinate_system")
        if coord_system == "polar":
            raise AxesTypeError(
                "检测到 iplotx radial 布局（layout_coordinate_system='polar'）；"
                "实验性 API 不承诺通过 add_geo_ring()/spec_from_iplotx() 适配 iplotx radial，"
                "环形树请按规范 6.3 的配方在原生极坐标 Axes 上自绘"
            )
    get_layout_name = getattr(artist, "get_layout_name", None)
    if callable(get_layout_name):
        try:
            name = get_layout_name()
        except Exception:  # pragma: no cover - 元数据读取失败时交给后续检测
            name = None
        if name == "radial":
            raise AxesTypeError(
                "检测到 iplotx radial 布局（get_layout_name() == 'radial'）；"
                "实验性 API 不承诺通过 add_geo_ring()/spec_from_iplotx() 适配 iplotx radial，"
                "环形树请按规范 6.3 的配方在原生极坐标 Axes 上自绘"
            )


def _root_time(artist, positions: dict, time_axis: str, *, fallback: float) -> float:
    """根节点在时间维上的坐标；取不到根节点时回退到调用方给定的基线。"""
    internal = getattr(artist, "_ipx_internal_data", None)
    root_node = internal.get("root") if isinstance(internal, dict) else None
    if root_node is not None:
        root_pos = positions.get(root_node)
        if root_pos is not None:
            return float(root_pos[0] if time_axis == "x" else root_pos[1])
    return fallback


def _layout_positions(layout) -> dict | None:
    """尽力读取 ``{节点: (x, y)}`` 布局数据（按锁定的 iplotx 版本核对）。

    iplotx >= 1.8：``get_layout()`` 返回 pandas ``DataFrame``（``_ipx_layout_0/1``
    两列，索引为节点）；旧版返回 ``{节点: (x, y)}`` 字典或带 ``.layout`` 等属性
    的对象。三种形态都归一化为字典。
    """
    if hasattr(layout, "to_numpy") and hasattr(layout, "columns"):
        # pandas DataFrame（duck-typing，避免硬依赖 pandas）。
        columns = [c for c in layout.columns if str(c).startswith("_ipx_layout_")]
        if len(columns) < 2:
            columns = list(layout.columns)
        if len(columns) < 2:
            return None
        try:
            values = layout[list(columns[:2])].to_numpy(dtype=float)
        except (TypeError, ValueError):  # pragma: no cover - 非数值布局
            return None
        if values.ndim != 2 or values.shape[1] < 2 or len(values) == 0:
            return None
        return {
            node: (float(row[0]), float(row[1]))
            for node, row in zip(layout.index, values, strict=True)
        }
    for attr in ("layout", "positions", "coords"):
        candidate = getattr(layout, attr, None)
        if isinstance(candidate, dict) and candidate:
            first = next(iter(candidate.values()))
            if isinstance(first, (tuple, list, complex)):
                return candidate
    if isinstance(layout, dict) and layout:
        first = next(iter(layout.values()))
        if isinstance(first, (tuple, list, complex)):
            return layout
    return None

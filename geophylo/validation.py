"""公共参数校验助手（规范 3.2/4.11）。

只校验公共函数参数：类型、取值域与组合合法性。数据文件 schema 校验归
``geophylo.data``，避免形成中央杂物模块。
"""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from typing import Any, cast

from .exceptions import AxesTypeError, CoordinateError, InvalidRangeError, InvalidRankError

CORE_RANKS: tuple[str, ...] = ("Eon", "Era", "Period", "Epoch", "Age")

POSITIONS: tuple[str, ...] = ("bottom", "top", "left", "right")
TIME_AXES: tuple[str, ...] = ("x", "y")
MODES: tuple[str, ...] = ("absolute_age", "root_distance")
BORDERS: tuple[str, ...] = ("none", "near", "far", "both")
TICK_STYLES: tuple[str, ...] = ("none", "boundaries", "ages")
BAND_UNITS: tuple[str, ...] = ("radial_fraction", "data")


def is_real_number(value: Any) -> bool:
    """真数值（int/float，非 bool、非复数）。"""
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def require_number(
    name: str,
    value: Any,
    *,
    allow_none: bool = False,
    minimum: float | None = None,
    maximum: float | None = None,
    exclude_minimum: bool = False,
) -> float | None:
    """校验数值参数：拒绝 bool、NaN 与非有限值；返回 ``float`` 或 ``None``。

    违规抛 :class:`~geophylo.exceptions.InvalidRangeError`。
    """
    if value is None:
        if allow_none:
            return None
        raise InvalidRangeError(f"{name} 不能为 None；请显式给出数值")
    if not is_real_number(value):
        raise InvalidRangeError(f"{name} 必须是数值（int/float），得到 {value!r}；bool 不被接受")
    number = float(value)
    if not math.isfinite(number):
        raise InvalidRangeError(f"{name} 必须是有限值，得到 {value!r}")
    if minimum is not None and (number < minimum or (exclude_minimum and number == minimum)):
        lower = ">" if exclude_minimum else ">="
        raise InvalidRangeError(f"{name}={number} 超出合法下界（{lower}{minimum}）")
    if maximum is not None and number > maximum:
        raise InvalidRangeError(f"{name}={number} 超出合法上界（<={maximum}）")
    return number


def require_bool(name: str, value: Any) -> bool:
    if not isinstance(value, bool):
        raise InvalidRangeError(f"{name} 必须是布尔值，得到 {value!r}")
    return value


def require_choice(
    name: str, value: Any, choices: Sequence[str], *, exc: type = CoordinateError
) -> str:
    if value not in choices:
        raise exc(f"{name}={value!r} 非法；合法取值为 {sorted(choices)!r}")
    return str(value)


def require_time_axis(time_axis: str) -> str:
    return require_choice("time_axis", time_axis, TIME_AXES, exc=CoordinateError)


def check_position_time_axis(position: str, time_axis: str) -> None:
    """``position`` 与 ``spec.time_axis`` 必须配对：bottom/top 沿 x，left/right 沿 y。"""
    expected = "x" if position in ("bottom", "top") else "y"
    if time_axis != expected:
        hint = "bottom/top" if expected == "x" else "left/right"
        raise CoordinateError(
            f"position={position!r} 与 spec.time_axis={time_axis!r} 冲突："
            f'position={position!r} 需要 spec.time_axis="{expected}"；'
            f"请改用 position={hint} 之一，或修正 spec 的 time_axis"
        )


def normalize_ranks(ranks: str | Sequence[str] | None, *, default: bool = True) -> tuple[str, ...]:
    """把 ``ranks`` 规范化为元组；``None`` 归一化为 ``("Period",)``。

    空序列、重复 rank 与非法 rank 都抛 :class:`~geophylo.exceptions.InvalidRankError`；
    rank 为大小写敏感的精确匹配（``"period"`` 不获自动纠正）。
    """
    if ranks is None:
        if default:
            return ("Period",)
        raise InvalidRankError("ranks 不能为 None")
    if isinstance(ranks, str):
        ranks = (ranks,)
    ranks = tuple(ranks)
    if len(ranks) == 0:
        raise InvalidRankError('ranks 为空序列；至少需要一个 rank，或传 None 使用默认 ("Period",)')
    seen: set[str] = set()
    for rank in ranks:
        if not isinstance(rank, str):
            raise InvalidRankError(f"rank 必须是字符串，得到 {rank!r}")
        if rank in seen:
            raise InvalidRankError(f"ranks 含重复元素 {rank!r}；重复 rank 会重复绘制，请去重后传入")
        seen.add(rank)
    illegal = [r for r in ranks if r not in CORE_RANKS]
    if illegal:
        raise InvalidRankError(
            f"非法 rank {illegal!r}；核心 rank 为 {list(CORE_RANKS)!r}（大小写敏感的精确匹配）"
        )
    return ranks


def require_age_window(
    min_age: float | None,
    max_age: float | None,
    *,
    spec_min: float,
    spec_max: float,
) -> tuple[float, float]:
    """校验绘制窗口；``None`` 时沿用 ``spec.age_range``。

    要求 ``0 <= min_age < max_age`` 且窗口落在 ``spec.age_range`` 的合法域内。
    """
    if min_age is None:
        lo = spec_min
    else:
        validated_min = require_number("min_age", min_age, minimum=0.0)
        lo = spec_min if validated_min is None else float(validated_min)
    if max_age is None:
        hi = spec_max
    else:
        validated_max = require_number("max_age", max_age)
        hi = spec_max if validated_max is None else float(validated_max)
    if not lo < hi:
        raise InvalidRangeError(f"要求 0 <= min_age < max_age，得到 min_age={lo}, max_age={hi}")
    if lo < spec_min - 1e-12 or hi > spec_max + 1e-12:
        raise InvalidRangeError(
            f"绘制窗口 [{lo}, {hi}] 超出 spec.age_range=[{spec_min}, {spec_max}] 的合法域；"
            "请扩大 spec.age_range 或缩小绘制窗口"
        )
    return lo, hi


def resolve_age_conversion(
    age_conversion: Any,
) -> Callable[[float], float]:
    """把 ``age_conversion`` 归一为换算函数（两个适配器共用）。

    规范（可核验）：

    * ``age_conversion`` 必填，取值为「每个 branch length 单位对应的 Ma 数」
      或「branch length → Ma」的换算函数；
    * 数值必须是正有限值，否则抛 :class:`~geophylo.exceptions.CoordinateError`
      （``bool`` 被拒，因为它不是数值单位）；
    * 换算函数必须在 ``1.0`` 处给出有限值——早失败探测，避免非法换算一路走到
      树遍历深处才以原始异常冒泡。
    """
    if callable(age_conversion) and not isinstance(age_conversion, type):
        convert = cast("Callable[[float], float]", age_conversion)
    elif is_real_number(age_conversion):
        factor = float(age_conversion)
        if not math.isfinite(factor) or factor <= 0:
            raise CoordinateError(
                f"age_conversion={factor!r} 必须为正有限值（branch length 单位 → Ma）"
            )
        convert = lambda bl: bl * factor  # noqa: E731
    else:
        raise CoordinateError(
            f"age_conversion 必须是 float 或 callable，得到 {age_conversion!r}；"
            "仅凭 root_age 无法把 substitutions/site 之类的单位换算成 Ma"
        )
    probe = convert(1.0)
    try:
        probe_value = float(probe)
    except (TypeError, ValueError) as exc:
        raise CoordinateError(f"age_conversion(1.0) = {probe!r} 不是数值") from exc
    if not math.isfinite(probe_value):
        raise CoordinateError(f"age_conversion(1.0) = {probe!r} 非有限值")
    return convert


def require_linear_numeric_axes(ax: Any, *, name: str = "ax") -> None:
    """要求宿主 Axes 的 x/y 都是数值线性轴，拒绝 log、日期与分类轴。"""
    x_scale = ax.get_xscale()
    y_scale = ax.get_yscale()
    if x_scale != "linear" or y_scale != "linear":
        raise AxesTypeError(
            f"{name} 的轴刻度必须是 linear（x={x_scale!r}, y={y_scale!r}）；"
            "log 轴被拒绝是因为 0 Ma 在 log 轴上无定义"
        )
    for axis_name, axis in (("x", ax.xaxis), ("y", ax.yaxis)):
        get_converter = getattr(axis, "get_converter", None)
        converter = get_converter() if callable(get_converter) else getattr(axis, "units", None)
        if converter is None:
            continue
        type_name = type(converter).__name__
        module = type(converter).__module__ or ""
        if "DateConverter" in type_name or "StrCategoryConverter" in type_name or "dates" in module:
            raise AxesTypeError(
                f"{name} 的 {axis_name} 轴是日期/分类轴（{type_name}），不是数值轴；"
                "地质时间轴要求数值线性轴"
            )

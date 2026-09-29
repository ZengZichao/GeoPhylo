"""``CoordinateSpec``：线性布局的坐标语义唯一真值来源（规范 4.3）。

绘制函数不接受「你猜我的轴是什么」式的默认值；``from_data_limits()`` 是唯一
的范围推断入口，且默认拒绝执行。
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from ..exceptions import CoordinateError, InvalidRangeError
from ..validation import (
    MODES,
    require_linear_numeric_axes,
    require_time_axis,
)
from .transform import age_to_data

if TYPE_CHECKING:  # pragma: no cover
    from matplotlib.axes import Axes

__all__ = ["CoordinateSpec"]


@dataclass(frozen=True)
class CoordinateSpec:
    """声明 ``time_axis``、``mode``、``age_range`` 与 ``root_age`` 的冻结契约。"""

    time_axis: Literal["x", "y"]
    mode: Literal["absolute_age", "root_distance"]
    age_range: tuple[float, float]  # (min_age, max_age)，要求 0 <= min_age < max_age
    root_age: float | None = None  # mode == "root_distance" 时必填，否则必须为 None

    def __post_init__(self) -> None:
        require_time_axis(self.time_axis)
        if self.mode not in MODES:
            raise CoordinateError(
                f'mode={self.mode!r} 非法；合法取值为 ["absolute_age", "root_distance"]'
            )
        lo, hi = self.age_range
        for name, value in (("age_range[0]", lo), ("age_range[1]", hi)):
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise InvalidRangeError(f"{name} 必须是数值，得到 {value!r}")
            if not math.isfinite(float(value)):
                raise InvalidRangeError(f"{name} 必须是有限值，得到 {value!r}")
        lo, hi = float(lo), float(hi)
        if lo < 0:
            raise InvalidRangeError(f"age_range[0]={lo} 不能为负（年龄以 Ma 为单位）")
        if lo >= hi:
            raise InvalidRangeError(f"要求 age_range 满足 min < max，得到 ({lo}, {hi})")
        object.__setattr__(self, "age_range", (lo, hi))
        if self.root_age is not None:
            if isinstance(self.root_age, bool) or not isinstance(self.root_age, (int, float)):
                raise CoordinateError(f"root_age 必须是数值或 None，得到 {self.root_age!r}")
            root = float(self.root_age)
            if not math.isfinite(root) or root < 0:
                raise CoordinateError(f"root_age 必须是非负有限值，得到 {self.root_age!r}")
            object.__setattr__(self, "root_age", root)
        if self.mode == "root_distance" and self.root_age is None:
            raise CoordinateError(
                'mode="root_distance" 时 root_age 必填（根年龄来自外部时间校准结果，'
                "本库不接受 branch length 大概率是 Ma 这类假设）"
            )
        if self.mode == "absolute_age" and self.root_age is not None:
            raise CoordinateError(
                'mode="absolute_age" 时 root_age 必须为 None；根年龄只属于 root_distance 模式'
            )

    # -- 纯函数 -----------------------------------------------------------

    def age_to_data(self, age_ma: float) -> float:
        """年龄 → 数据坐标。不处理轴反向（视图变换已负责）。"""
        return age_to_data(age_ma, mode=self.mode, age_range=self.age_range, root_age=self.root_age)

    # -- 构造入口 ----------------------------------------------------------

    @classmethod
    def absolute(
        cls,
        *,
        time_axis: Literal["x", "y"],
        age_range: tuple[float, float],
    ) -> CoordinateSpec:
        """``absolute_age`` 模式的显式构造入口。"""
        return cls(time_axis=time_axis, mode="absolute_age", age_range=age_range, root_age=None)

    @classmethod
    def root_distance(
        cls,
        *,
        time_axis: Literal["x", "y"],
        age_range: tuple[float, float],
        root_age: float,
    ) -> CoordinateSpec:
        """``root_distance`` 模式的显式构造入口。"""
        return cls(
            time_axis=time_axis, mode="root_distance", age_range=age_range, root_age=root_age
        )

    @classmethod
    def from_data_limits(
        cls,
        ax: Axes,
        *,
        mode: Literal["absolute_age", "root_distance"],
        time_axis: Literal["x", "y"],
        root_age: float | None = None,
        acknowledge_inference: bool = False,
    ) -> CoordinateSpec:
        """唯一的范围推断入口，且默认拒绝执行。

        推断读取宿主 Axes 当前的 view limits（``get_xlim()``/``get_ylim()``）；
        轴被反向时返回的 ``(left, right)`` 可能 ``left > right``，入口统一按
        数值大小归一化为 ``(min, max)`` 后再构造。
        """
        if not acknowledge_inference:
            raise CoordinateError(
                "范围推断被拒绝：从 Axes 数据范围推断 age_range 属于隐式假设。"
                "请显式给出 age_range，或在确认数据范围可信时传 "
                "acknowledge_inference=True 显式确认"
            )
        if mode not in MODES:
            raise CoordinateError(f"mode={mode!r} 非法")
        require_time_axis(time_axis)
        if mode == "root_distance" and root_age is None:
            raise CoordinateError(
                'mode="root_distance" 的范围推断同样必须提供 root_age；'
                "Axes 数值范围本身不携带根年龄信息"
            )
        if mode == "absolute_age" and root_age is not None:
            raise CoordinateError('mode="absolute_age" 时 root_age 必须为 None')
        require_linear_numeric_axes(ax)
        limits = ax.get_xlim() if time_axis == "x" else ax.get_ylim()
        lo, hi = sorted(float(v) for v in limits)
        if mode == "absolute_age":
            if lo < 0:
                raise InvalidRangeError(
                    f"宿主 Axes 数据范围 [{lo}, {hi}] 含负值，无法作为 age_range"
                    "（年龄以 Ma 为单位且非负）"
                )
            return cls.absolute(time_axis=time_axis, age_range=(lo, hi))
        assert root_age is not None  # absolute_age 分支已在上方拒绝 None
        root = float(root_age)
        age_lo, age_hi = root - hi, root - lo
        if age_lo < 0 or age_hi <= 0:
            raise InvalidRangeError(
                f"宿主 Axes 数据范围 [{lo}, {hi}] 在 root_age={root} 下推出非法 age_range "
                f"[{age_lo}, {age_hi}]；root_age 应不小于数据范围上界"
            )
        return cls.root_distance(time_axis=time_axis, age_range=(age_lo, age_hi), root_age=root)

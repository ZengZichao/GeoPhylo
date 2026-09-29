"""年龄 → 数据坐标的纯函数（规范 4.3）。

坐标层不导入任何树库、不导入 ``Timescale``、不读取 ICS 数据，也不感知轴是
否被反向——反向由 Matplotlib 的视图变换负责，在此处再翻转会造成双重翻转。
"""

from __future__ import annotations

import math
from typing import Literal

from ..exceptions import CoordinateError

Mode = Literal["absolute_age", "root_distance"]

__all__ = ["age_to_data"]


def age_to_data(
    age_ma: float,
    *,
    mode: Mode,
    age_range: tuple[float, float],
    root_age: float | None = None,
) -> float:
    """把 Ma 年龄换算为数据坐标。

    - ``absolute_age``：返回 ``age_ma`` 本身；
    - ``root_distance``：返回 ``root_age - age_ma``。

    运行期拒绝 NaN、非有限值、``age_range`` 域外输入，以及 ``root_distance``
    模式下的负根距离和超出 ``root_age`` 的距离，抛 ``CoordinateError``。
    """
    if isinstance(age_ma, bool) or not isinstance(age_ma, (int, float)):
        raise CoordinateError(f"age_ma 必须是数值，得到 {age_ma!r}")
    age = float(age_ma)
    if not math.isfinite(age):
        raise CoordinateError(f"age_ma 必须是有限值，得到 {age_ma!r}")
    lo, hi = age_range
    if age < lo - 1e-12 or age > hi + 1e-12:
        raise CoordinateError(
            f"age_ma={age!r} 超出 spec.age_range=[{lo}, {hi}] 的合法域；"
            "age_range 决定坐标换算的合法性域，绘制窗口决定裁剪边界"
        )
    if mode == "absolute_age":
        return age
    if root_age is None:  # pragma: no cover - 构造期已校验
        raise CoordinateError("root_distance 模式必须有 root_age")
    distance = root_age - age
    if distance < 0 or distance > root_age:
        raise CoordinateError(
            f"age_ma={age!r} 在 root_age={root_age!r} 下产生非法根距离 {distance!r}；"
            "负根距离或超出根年龄的距离无定义"
        )
    return distance

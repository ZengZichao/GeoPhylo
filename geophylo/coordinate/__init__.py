"""坐标层：纯坐标转换，两份契约（线性 ``CoordinateSpec`` 与环形 ``RadialSpec``）。"""

from __future__ import annotations

from .radial import RadialSpec
from .spec import CoordinateSpec
from .transform import age_to_data

__all__ = ["CoordinateSpec", "RadialSpec", "age_to_data"]

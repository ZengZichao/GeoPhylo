"""绘制层：Artist 的构造与生命周期。

``render/linear.py`` 提供 ``add_geo_axis()``；``render/result.py`` 提供
``GeoAxisResult``；``render/ticks.py`` 实现 4.6 的刻度契约；
``render/labels.py`` 负责标签测量、缩写、碰撞与降级；``render/polar.py`` 为
实验性 ``add_geo_ring()``。绘制层不得自行推断树的时间语义，也不绘制树。
"""

from __future__ import annotations

from .linear import add_geo_axis
from .polar import add_geo_ring
from .result import GeoAxisResult, remove_all

__all__ = ["GeoAxisResult", "add_geo_axis", "add_geo_ring", "remove_all"]

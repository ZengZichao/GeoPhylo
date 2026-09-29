"""``RadialSpec``：环形布局的半径↔年龄与角度契约（规范 4.9，实验性）。

半径编码时间（本库的职责），角度编码分类单元顺序（树布局的职责，显式输入，
不推断）。环与树必须在同一个 ``RadialSpec`` 实例下绘制，否则会出现静默错位。

映射规则（可核验，见 ``tests/test_radial_spec.py``）：

* ``age_to_radius()`` 是 ``age_range → radius_range`` 的严格单调递减仿射映射，
  ``max_age`` 落在内半径（根在圆心）、``min_age`` 落在外半径（叶在外缘）；
* 传 ``radius_range=(r_lo, r_hi)`` 得到同一映射在该值域上的仿射限制：
  ``age_to_radius(a, radius_range=(r_lo, r_hi))`` 恒等于
  ``r_lo + (age_to_radius(a) - R0) / (R1 - R0) * (r_hi - r_lo)``，其中
  ``(R0, R1)`` 是完整 ``radius_range``；
* ``radius_to_age()`` 是同一值域上的精确逆：两个方向都必须显式使用同一值域，
  环上半径用 ``band_radius()`` 的返回值求逆，树上半径用完整 ``radius_range``。
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

from ..exceptions import CoordinateError, InvalidRadiusError, InvalidRangeError

__all__ = ["FULL_CIRCLE_TOL", "RadialSpec"]

# 完整圆用容差判定：abs(span - 2π) <= 1e-9。
FULL_CIRCLE_TOL = 1e-9


@dataclass(frozen=True)
class RadialSpec:
    """环形布局的坐标契约与唯一真值来源。

    - ``age_range``：``(min_age, max_age)``,要求 ``0 <= min_age < max_age``；
    - ``radius_range``：``(r_inner, r_outer)``，内半径对应 ``max_age``（根），
      外半径对应 ``min_age``（叶）；
    - ``theta_range``：树占据的角度跨度（弧度），构造时完成正规化与展开；
    - ``root_age``：由外部时间校准结果提供；需要把根距离换算成年龄时必填。
    """

    age_range: tuple[float, float]
    radius_range: tuple[float, float]
    theta_range: tuple[float, float]
    root_age: float | None = None

    def __post_init__(self) -> None:
        for name, value in (
            ("age_range[0]", self.age_range[0]),
            ("age_range[1]", self.age_range[1]),
            ("radius_range[0]", self.radius_range[0]),
            ("radius_range[1]", self.radius_range[1]),
            ("theta_range[0]", self.theta_range[0]),
            ("theta_range[1]", self.theta_range[1]),
        ):
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise InvalidRangeError(f"{name} 必须是数值，得到 {value!r}")
            if not math.isfinite(float(value)):
                raise InvalidRangeError(f"{name} 必须是有限值，得到 {value!r}")
        age_lo, age_hi = float(self.age_range[0]), float(self.age_range[1])
        r_inner, r_outer = float(self.radius_range[0]), float(self.radius_range[1])
        if age_lo < 0:
            raise InvalidRangeError(f"age_range[0]={age_lo} 不能为负（年龄以 Ma 为单位）")
        if age_lo >= age_hi:
            raise InvalidRangeError(f"要求 age_range 满足 min < max，得到 ({age_lo}, {age_hi})")
        if r_inner < 0:
            raise InvalidRadiusError(f"r_inner={r_inner} 不能为负")
        if r_inner >= r_outer:
            raise InvalidRadiusError(f"要求 r_inner < r_outer，得到 ({r_inner}, {r_outer})")
        object.__setattr__(self, "age_range", (age_lo, age_hi))
        object.__setattr__(self, "radius_range", (r_inner, r_outer))
        if self.root_age is not None:
            if isinstance(self.root_age, bool) or not isinstance(self.root_age, (int, float)):
                raise CoordinateError(f"root_age 必须是数值或 None，得到 {self.root_age!r}")
            root = float(self.root_age)
            if not math.isfinite(root) or root < 0:
                raise CoordinateError(f"root_age 必须是非负有限值，得到 {self.root_age!r}")
            object.__setattr__(self, "root_age", root)
        # 角度正规化与展开：按 +2π 的整数倍展开后要求跨度落在 (0, 2π + tol]。
        t0, t1 = float(self.theta_range[0]), float(self.theta_range[1])
        while t1 < t0:
            t1 += 2.0 * math.pi
        span = t1 - t0
        if span <= 0 or span > 2.0 * math.pi + FULL_CIRCLE_TOL:
            raise CoordinateError(
                f"theta_range 展开后跨度非法：({self.theta_range[0]}, {self.theta_range[1]}) "
                f"→ 跨度 {span:.12f} rad；要求 0 < 跨度 <= 2π + {FULL_CIRCLE_TOL}"
            )
        object.__setattr__(self, "theta_range", (t0, t1))

    # -- 半径映射（严格单调的线性映射）-------------------------------------

    def _resolve_radius_range(
        self, radius_range: tuple[float, float] | None
    ) -> tuple[float, float]:
        """把可选的值域参数规范为 ``(r_lo, r_hi)``；``None`` 即完整 ``radius_range``。"""
        if radius_range is None:
            return (float(self.radius_range[0]), float(self.radius_range[1]))
        if len(radius_range) != 2:
            raise InvalidRadiusError(f"radius_range 必须是 (下, 上) 二元组，得到 {radius_range!r}")
        lo, hi = radius_range
        for name, value in (("radius_range[0]", lo), ("radius_range[1]", hi)):
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise InvalidRadiusError(f"{name} 必须是数值，得到 {value!r}")
            if not math.isfinite(float(value)):
                raise InvalidRadiusError(f"{name} 必须是有限值，得到 {value!r}")
        lo, hi = float(lo), float(hi)
        if lo >= hi:
            raise InvalidRadiusError(f"要求 radius_range 满足 lo < hi，得到 ({lo}, {hi})")
        return lo, hi

    def age_to_radius(
        self, age_ma: float, *, radius_range: tuple[float, float] | None = None
    ) -> float:
        """``max_age`` 对应内半径（根在圆心），``min_age`` 对应外半径（叶在外缘）。

        ``radius_range`` 是可选的**值域**：默认映射到完整的 ``self.radius_range``
        （树节点用这个），传入 ``band_radius()`` 的返回值则把同一条线性映射限制
        到环带内（时间环用这个）。值域不改变映射的方向与单调性，也不引入第二套
        公式——它是同一映射在子区间上的仿射限制（规范 4.9）。
        """
        age = self._check_age(age_ma)
        min_age, max_age = self.age_range
        r_inner, r_outer = self._resolve_radius_range(radius_range)
        fraction = (max_age - age) / (max_age - min_age)
        return r_inner + fraction * (r_outer - r_inner)

    def radius_to_age(
        self, radius: float, *, radius_range: tuple[float, float] | None = None
    ) -> float:
        """逆映射；映射严格单调，逆在给定值域内唯一。

        ``radius_range`` 必须与求逆时使用的 ``age_to_radius()`` 值域一致：环上
        半径用环带值域求逆，树上半径用完整 ``radius_range`` 求逆。
        """
        if isinstance(radius, bool) or not isinstance(radius, (int, float)):
            raise CoordinateError(f"radius 必须是数值，得到 {radius!r}")
        radius = float(radius)
        if not math.isfinite(radius):
            raise CoordinateError(f"radius 必须是有限值，得到 {radius!r}")
        r_inner, r_outer = self._resolve_radius_range(radius_range)
        if radius < r_inner - 1e-12 or radius > r_outer + 1e-12:
            raise CoordinateError(f"radius={radius!r} 超出 radius_range=[{r_inner}, {r_outer}]")
        min_age, max_age = self.age_range
        return max_age - (radius - r_inner) / (r_outer - r_inner) * (max_age - min_age)

    def band_radius(
        self,
        band: tuple[float, float],
        unit: Literal["radial_fraction", "data"] = "radial_fraction",
    ) -> tuple[float, float]:
        """把环带换算为 ``(r_inner, r_outer)``；单位换算只发生在这里。"""
        if len(band) != 2:
            raise InvalidRadiusError(f"band 必须是 (下, 上) 二元组，得到 {band!r}")
        lo, hi = band
        for name, value in (("band[0]", lo), ("band[1]", hi)):
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise InvalidRadiusError(f"{name} 必须是数值，得到 {value!r}")
            if not math.isfinite(float(value)):
                raise InvalidRadiusError(f"{name} 必须是有限值，得到 {value!r}")
        lo, hi = float(lo), float(hi)
        if lo >= hi:
            raise InvalidRadiusError(f"band 必须满足 band[0] < band[1]（4.8），得到 {band!r}")
        r_inner, r_outer = self.radius_range
        if unit == "radial_fraction":
            if not (0.0 <= lo <= 1.0 and 0.0 <= hi <= 1.0):
                raise InvalidRadiusError(f"band={band!r} 在 radial_fraction 单位下必须落在 [0, 1]")
            return (r_inner + lo * (r_outer - r_inner), r_inner + hi * (r_outer - r_inner))
        if unit == "data":
            if lo < r_inner - 1e-12 or hi > r_outer + 1e-12:
                raise InvalidRadiusError(
                    f"band={band!r} 在 data 单位下必须落在 radius_range=[{r_inner}, {r_outer}] 内"
                )
            return (lo, hi)
        raise InvalidRadiusError(f'band_unit={unit!r} 非法；合法取值为 ["radial_fraction", "data"]')

    def _check_age(self, age_ma: float) -> float:
        if isinstance(age_ma, bool) or not isinstance(age_ma, (int, float)):
            raise CoordinateError(f"age_ma 必须是数值，得到 {age_ma!r}")
        age = float(age_ma)
        if not math.isfinite(age):
            raise CoordinateError(f"age_ma 必须是有限值，得到 {age_ma!r}")
        lo, hi = self.age_range
        if age < lo - 1e-12 or age > hi + 1e-12:
            raise CoordinateError(f"age_ma={age_ma!r} 超出 age_range=[{lo}, {hi}]")
        return age

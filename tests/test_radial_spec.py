"""RadialSpec 契约测试（开发文档 4.9/5.3，experimental marker）。"""

from __future__ import annotations

import math

import pytest

from geophylo import CoordinateError, InvalidRangeError
from geophylo.coordinate.radial import RadialSpec

pytestmark = [pytest.mark.experimental]

ANALYTIC_TOL = 1e-9


@pytest.fixture()
def radial() -> RadialSpec:
    return RadialSpec(
        age_range=(0.0, 100.0),
        radius_range=(0.0, 1.0),
        theta_range=(0.0, math.pi / 2),
        root_age=100.0,
    )


class TestRadiusMapping:
    def test_matches_analytic(self, radial):
        for age in (0.0, 25.0, 66.0, 100.0):
            expected = (100.0 - age) / 100.0 * 1.0
            assert radial.age_to_radius(age) == pytest.approx(expected, abs=ANALYTIC_TOL)

    def test_endpoints(self, radial):
        assert radial.age_to_radius(100.0) == pytest.approx(0.0, abs=ANALYTIC_TOL)  # 根在内半径
        assert radial.age_to_radius(0.0) == pytest.approx(1.0, abs=ANALYTIC_TOL)  # 叶在外半径

    def test_inverse_against_independent_formula(self, radial):
        # 与线性逆映射的解析基准独立比对（不与 age_to_radius 互相套证）。
        r_inner, r_outer = radial.radius_range
        min_age, max_age = radial.age_range
        for r in (r_inner, (r_inner + r_outer) / 2, r_outer):
            expected = max_age - (r - r_inner) / (r_outer - r_inner) * (max_age - min_age)
            assert radial.radius_to_age(r) == pytest.approx(expected, abs=ANALYTIC_TOL)

    def test_roundtrip(self, radial):
        for age in (1.0, 33.0, 99.0):
            assert radial.radius_to_age(radial.age_to_radius(age)) == pytest.approx(
                age, abs=ANALYTIC_TOL
            )

    def test_non_offset_radius_range(self):
        spec = RadialSpec(
            age_range=(10.0, 100.0),
            radius_range=(2.0, 5.0),
            theta_range=(0.0, 1.0),
        )
        assert spec.age_to_radius(100.0) == pytest.approx(2.0)
        assert spec.age_to_radius(10.0) == pytest.approx(5.0)

    def test_domain_rejected(self, radial):
        with pytest.raises(CoordinateError):
            radial.age_to_radius(-0.5)
        with pytest.raises(CoordinateError):
            radial.age_to_radius(150.0)
        with pytest.raises(CoordinateError):
            radial.radius_to_age(1.5)
        with pytest.raises(CoordinateError):
            radial.age_to_radius(float("nan"))


class TestConstruction:
    @pytest.mark.parametrize(
        "kwargs",
        [
            dict(age_range=(100.0, 0.0), radius_range=(0.0, 1.0), theta_range=(0.0, 1.0)),
            dict(age_range=(0.0, 100.0), radius_range=(1.0, 0.5), theta_range=(0.0, 1.0)),
            dict(age_range=(-5.0, 100.0), radius_range=(0.0, 1.0), theta_range=(0.0, 1.0)),
            dict(age_range=(0.0, float("nan")), radius_range=(0.0, 1.0), theta_range=(0.0, 1.0)),
        ],
    )
    def test_illegal(self, kwargs):
        from geophylo import InvalidRadiusError

        with pytest.raises((InvalidRangeError, CoordinateError, InvalidRadiusError)):
            RadialSpec(**kwargs)


class TestThetaNormalization:
    def test_cross_zero_expansion(self):
        # 350° → 10° 按展开解释为 350° → 370°。
        import math

        spec = RadialSpec(
            age_range=(0.0, 10.0),
            radius_range=(0.0, 1.0),
            theta_range=(350.0 * math.pi / 180.0, 10.0 * math.pi / 180.0),
        )
        assert spec.theta_range[1] == pytest.approx(370.0 * math.pi / 180.0, abs=ANALYTIC_TOL)
        assert spec.theta_range[1] - spec.theta_range[0] == pytest.approx(20.0 * math.pi / 180.0)

    def test_full_circle_within_tolerance(self):
        spec = RadialSpec(
            age_range=(0.0, 10.0),
            radius_range=(0.0, 1.0),
            theta_range=(0.0, 2 * math.pi + 5e-10),
        )
        assert spec.theta_range[1] - spec.theta_range[0] <= 2 * math.pi + 1e-9

    def test_span_overflow_rejected(self):
        with pytest.raises(CoordinateError):
            RadialSpec(
                age_range=(0.0, 10.0),
                radius_range=(0.0, 1.0),
                theta_range=(0.0, 2 * math.pi + 1e-3),
            )


class TestBandRadius:
    def test_radial_fraction(self, radial):
        r_inner, r_outer = radial.band_radius((0.92, 1.0))
        assert (r_inner, r_outer) == pytest.approx((0.92, 1.0))

    def test_data_unit(self, radial):
        assert radial.band_radius((0.5, 1.0), unit="data") == (0.5, 1.0)

    def test_fraction_out_of_range(self, radial):
        with pytest.raises(Exception):
            radial.band_radius((-0.1, 1.0))
        with pytest.raises(Exception):
            radial.band_radius((0.0, 1.2))

    def test_data_outside_radius_range(self, radial):
        with pytest.raises(Exception):
            radial.band_radius((0.5, 2.0), unit="data")

    def test_bad_unit(self, radial):
        with pytest.raises(Exception):
            radial.band_radius((0.9, 1.0), unit="parsecs")

    def test_inverted_band_rejected(self, radial):
        # 4.8：band 必须满足 band[0] < band[1]；倒置输入不得返回倒置半径。
        from geophylo import InvalidRadiusError

        with pytest.raises(InvalidRadiusError):
            radial.band_radius((0.9, 0.1))
        with pytest.raises(InvalidRadiusError):
            radial.band_radius((0.5, 0.5))
        with pytest.raises(InvalidRadiusError):
            radial.band_radius((0.8, 0.5), unit="data")

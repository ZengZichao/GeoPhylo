"""数据模型投影测试：Boundary / Interval / BackendMetadata（开发文档 5.6）。"""

from __future__ import annotations

import pytest

from geophylo import Boundary, Interval


def make_boundary(age, qualifier, uncertainty, definition):
    return Boundary(
        age_ma=age, qualifier=qualifier, uncertainty_ma=uncertainty, definition=definition
    )


def make_interval(older, younger, *, older_b=None, younger_b=None, rank="Period", aliases=("J",)):
    return Interval(
        id=f"ics:{rank.lower()}:test",
        source_iri=None,
        name="Test",
        label="Test",
        aliases=tuple(aliases),
        rank=rank,
        rank_class="geochronologic",
        parent_id=None,
        source_parent_id=None,
        status="ratified",
        color="#34B2C9",
        older_boundary=older_b or make_boundary(older, "constrained", 0.2, "gssp"),
        younger_boundary=younger_b
        or make_boundary(younger, "constrained", 0.6, "numeric_estimate"),
    )


class TestBoundary:
    def test_gssp_with_uncertainty_is_constrained(self):
        b = make_boundary(201.4, "constrained", 0.2, "gssp")
        assert b.is_defined and b.effective_uncertainty == pytest.approx(0.2)

    def test_gssp_without_uncertainty_is_defined(self):
        b = make_boundary(635.0, "defined", None, "gssp")
        assert b.is_defined
        assert b.effective_uncertainty is None  # 「未知/未给出」不是 0.0

    def test_unknown_qualifier_returns_none_uncertainty(self):
        b = make_boundary(720.0, "unknown", None, "numeric_estimate")
        assert b.effective_uncertainty is None
        assert not b.is_defined

    def test_present_boundary(self):
        b = make_boundary(0.0, "present", None, "present")
        # present 边界只作标记，不构成数值约束（qualifier 不在 constrained/approximate/unknown 中）
        assert not b.is_numeric
        assert b.definition == "present"

    def test_frozen(self):
        b = make_boundary(1.0, "constrained", None, "gssp")
        with pytest.raises(Exception):
            b.age_ma = 2.0  # type: ignore[misc]


class TestInterval:
    def test_bounds_projection(self):
        interval = make_interval(201.4, 143.1)
        assert interval.bounds == (201.4, 143.1)
        assert interval.older_ma == 201.4
        assert interval.younger_ma == 143.1
        older_b, younger_b = interval.boundaries
        assert older_b.age_ma == 201.4
        assert younger_b.age_ma == 143.1

    def test_has_approximate_boundary_predicate(self):
        interval = make_interval(
            635.0,
            538.8,
            older_b=make_boundary(635.0, "approximate", None, "numeric_estimate"),
            younger_b=make_boundary(538.8, "constrained", 0.6, "numeric_estimate"),
        )
        assert interval.has_approximate_boundary

    def test_has_defined_boundary(self):
        interval = make_interval(
            4567.0,
            4031.0,
            older_b=make_boundary(4567.0, "defined", None, "gssa"),
            younger_b=make_boundary(4031.0, "constrained", 3.0, "gssa"),
        )
        assert interval.has_defined_boundary
        # 谓词一律走属性形式；废弃别名 is_approximate_any() 的行为由
        # tests/test_data_contract.py 里的 pytest.warns 用例专门守着。
        assert not interval.has_approximate_boundary

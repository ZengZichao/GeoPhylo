"""数据查询语义测试（开发文档 4.1/4.2/7.1）。"""

from __future__ import annotations

import pytest

from geophylo import (
    AmbiguousIntervalError,
    IntervalNotFoundError,
    InvalidRangeError,
    InvalidRankError,
    Timescale,
)

EPS = 1e-6  # 4.2 规定的测试 ε（> 1e-9 吸附容差）


class TestFindByAge:
    def test_phanerozoic_boundary_semantics(self, ts):
        # 4.2 第 2 条：精确命中内部边界 → 返回以该边界为 older_ma 的较年轻区间。
        assert ts.find_by_age(66.0, rank="Period").name == "Paleogene"

    def test_boundary_two_sides_outside_tolerance(self, ts):
        # ε = 1e-6（> 吸附容差 1e-9）：两侧按 4.2 第 1 条不等式归属——
        # 66.0 - ε 更年轻 → Paleogene；66.0 + ε 更老 → Cretaceous。
        assert ts.find_by_age(66.0 - EPS, rank="Period").name == "Paleogene"
        assert ts.find_by_age(66.0 + EPS, rank="Period").name == "Cretaceous"

    def test_snap_tolerance_inside(self, ts):
        # 66.0 ± 5e-10 在吸附容差内：两侧均吸附到 66.0 边界 → Paleogene。
        assert ts.find_by_age(66.0 + 5e-10, rank="Period").name == "Paleogene"
        assert ts.find_by_age(66.0 - 5e-10, rank="Period").name == "Paleogene"

    def test_zero_age_youngest(self, ts):
        # 4.2 第 3 条：0.0 显式归入最年轻区间。
        assert ts.find_by_age(0.0).name == "Meghalayan"
        # 容差内正年龄殊途同归。
        assert ts.find_by_age(5e-10).name == "Meghalayan"

    def test_oldest_boundary(self, ts):
        oldest = max(i.older_ma for i in ts.iter_intervals())
        assert ts.find_by_age(oldest).name == "Hadean"  # 恰好吸附 → 最老区间
        assert ts.find_by_age(oldest - EPS).name == "Hadean"  # 命中
        with pytest.raises(IntervalNotFoundError):  # + ε → 越界
            ts.find_by_age(oldest + EPS)

    def test_rank_without_interval_at_age(self, ts):
        # Age 层级在 635-538.8（Ediacaran）无正式 Age：报错并列出可用 rank。
        with pytest.raises(IntervalNotFoundError) as excinfo:
            ts.find_by_age(600.0, rank="Age")
        message = str(excinfo.value)
        assert "600.0" in message and "Age" in message and "Eon" in message

    def test_negative_and_nonfinite_rejected(self, ts):
        for bad in (-1.0, float("nan"), float("inf")):
            with pytest.raises(InvalidRangeError):
                ts.find_by_age(bad)

    def test_bool_rejected(self, ts):
        with pytest.raises(InvalidRangeError):
            ts.find_by_age(True)


class TestGetInterval:
    def test_by_stable_id(self, ts):
        interval = ts.get_interval("ics:period:jurassic")
        assert interval.name == "Jurassic"
        assert interval.boundaries[0].age_ma == pytest.approx(201.4)
        assert interval.boundaries[1].age_ma == pytest.approx(143.1)
        assert interval.bounds == pytest.approx((201.4, 143.1))

    def test_unknown_id_hints_find_by_name(self, ts):
        with pytest.raises(IntervalNotFoundError, match="find_by_name"):
            ts.get_interval("Jurassic")  # 名称不是 ID


class TestFindByName:
    def test_exact_name(self, ts):
        assert ts.find_by_name("Holocene").name == "Holocene"

    def test_casefold_and_substring(self, ts):
        assert ts.find_by_name("holocene").name == "Holocene"
        # 子串语义：完整名 "Jurassic" 也命中 Lower/Middle/Upper Jurassic，需 rank 消歧。
        assert ts.find_by_name("Jurassic", rank="Period").name == "Jurassic"

    def test_alias_channel(self, ts):
        assert ts.find_by_name("J", rank="Period").name == "Jurassic"

    def test_ambiguous_short_query(self, ts):
        # 候选集合从快照读取：名称含 "Upper" 的全部 Epoch。
        expected = sorted(i.id for i in ts.iter_intervals(ranks=["Epoch"]) if "Upper" in i.name)
        assert len(expected) >= 2
        with pytest.raises(AmbiguousIntervalError) as excinfo:
            ts.find_by_name("Upper", rank="Epoch")
        assert sorted(excinfo.value.candidates) == expected

    def test_parent_disambiguates(self, ts):
        upper = ts.find_by_name("Upper", rank="Epoch", parent="ics:period:cretaceous")
        assert upper.name == "Upper Cretaceous"

    def test_no_hit(self, ts):
        with pytest.raises(IntervalNotFoundError):
            ts.find_by_name("Bogus")

    def test_rank_case_sensitive(self, ts):
        with pytest.raises(InvalidRankError):
            ts.find_by_name("Jurassic", rank="period")  # 不做大小写归一化


class TestIterIntervals:
    def test_window_intersection_semantics(self, ts):
        # 窗口语义是相交，不是「起点落在窗口内」：Ediacaran 与 [0, 541] 相交。
        names = [i.name for i in ts.iter_intervals(ranks=["Period"], min_age=0.0, max_age=541.0)]
        assert "Ediacaran" in names
        assert len(names) == 13  # 显传期 12 个 + Ediacaran

    def test_deterministic_sort(self, ts):
        core_order = {"Eon": 0, "Era": 1, "Period": 2, "Epoch": 3, "Age": 4}
        intervals = list(ts.iter_intervals(ranks=["Eon", "Era", "Period", "Epoch", "Age"]))
        keys = [(-i.older_ma, core_order[i.rank], i.id) for i in intervals]
        assert keys == sorted(keys)

    def test_single_rank_accepts_str(self, ts):
        periods = list(ts.iter_intervals(ranks="Period"))
        assert all(i.rank == "Period" for i in periods)
        assert len(periods) == 22  # 显传 12 + Ediacaran + 前寒武纪 9 个 Period

    def test_invalid_ranks(self, ts):
        for bad in ([], ("Period", "Period"), ("period",), ("Super-Eon",)):
            with pytest.raises(InvalidRankError):
                list(ts.iter_intervals(ranks=bad))

    def test_invalid_range(self, ts):
        with pytest.raises(InvalidRangeError):
            list(ts.iter_intervals(min_age=100.0, max_age=50.0))
        with pytest.raises(InvalidRangeError):
            list(ts.iter_intervals(min_age=-1.0, max_age=50.0))


class TestTimescaleFacade:
    def test_default_baseline(self, ts):
        assert ts.version == "2026/06"
        assert ts.ranks == ("Eon", "Era", "Period", "Epoch", "Age")
        assert ts.metadata.has_uncertainty is True
        assert ts.metadata.has_stable_ids is True
        assert ts.metadata.rank_map["Eon"] == "Eon"

    def test_explicit_version(self):
        ts = Timescale(version="2024/12")
        assert ts.version == "2024/12"
        # 2024/12 的 base Olenekian 为 249.9：250.85 归 Induan（2026/06 则归 Olenekian）。
        assert ts.find_by_age(250.85, rank="Age").name == "Induan"

    def test_from_json(self, tmp_path):
        import json

        from geophylo.data.builtin import load_snapshot

        path = tmp_path / "custom.json"
        path.write_text(json.dumps(load_snapshot("2026/06")), encoding="utf-8")
        ts = Timescale.from_json(path)
        assert ts.find_by_age(66.0, rank="Period").name == "Paleogene"

    def test_unknown_backend_string(self):
        with pytest.raises(ValueError, match="backend"):
            Timescale(backend="nope")

    def test_no_duplicate_entry_points(self):
        # 4.1：不提供 named_age / text2age / intervals 别名。
        assert not hasattr(Timescale, "named_age")
        assert not hasattr(Timescale, "text2age")
        assert not hasattr(Timescale, "intervals")


class TestPyroliteBackendAgeSemantics:
    """pyrolite 后端与内置快照后端一致的 4.2 语义（不依赖 pyrolite 安装）。

    用 ``__new__`` 构造最小实例并直接注入区间，锁定「边界值归属于以其为
    ``older_ma`` 的较年轻区间」与 0 Ma 归最年轻区间两条规则。
    """

    @staticmethod
    def _backend_with_intervals():
        from geophylo.data.models import Boundary, Interval
        from geophylo.data.pyrolite_backend import PyroliteBackend

        def interval(name, older, younger):
            return Interval(
                id=f"pyrolite:period:{name.casefold()}",
                source_iri=None,
                name=name,
                label=name,
                aliases=(),
                rank="Period",
                rank_class="geochronologic",
                parent_id=None,
                source_parent_id=None,
                status="unknown",
                color="#888888",
                older_boundary=Boundary(older, "unknown", None, "unknown"),
                younger_boundary=Boundary(younger, "unknown", None, "unknown"),
            )

        backend = PyroliteBackend.__new__(PyroliteBackend)
        backend._intervals = [
            interval("Cretaceous", 145.0, 66.0),
            interval("Paleogene", 66.0, 23.03),
            interval("Neogene", 23.03, 0.0),
        ]
        return backend

    def test_boundary_belongs_to_younger_interval(self):
        backend = self._backend_with_intervals()
        # 66.0 是 Cretaceous/Paleogene 边界 → Paleogene（较年轻区间），不是 Cretaceous。
        assert backend.find_by_age(66.0).name == "Paleogene"

    def test_zero_age_youngest_interval(self):
        backend = self._backend_with_intervals()
        assert backend.find_by_age(0.0).name == "Neogene"

    def test_interior_age(self):
        backend = self._backend_with_intervals()
        assert backend.find_by_age(100.0).name == "Cretaceous"
        assert backend.find_by_age(30.0).name == "Paleogene"

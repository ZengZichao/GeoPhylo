"""pyrolite 实验后端能力声明测试（非阻塞，开发文档 1.4/2.2/7.8）。

pyrolite 未安装时整体跳过；已安装时锁定三条使用规则：
严格 rank 过滤、缺失元数据标记 unknown、版本下界 0.3.7。
"""

from __future__ import annotations

import pytest

pytest.importorskip("pyrolite")

from geophylo import IntervalNotFoundError, InvalidRankError, Timescale


@pytest.fixture(scope="module")
def ts():
    return Timescale(backend="pyrolite")


def test_metadata_capability_declaration(ts):
    meta = ts.metadata
    assert meta.has_stable_ids is False  # 公开表契约没有稳定 ID
    assert meta.has_boundary_definition == "unknown"
    assert meta.rank_map, "rank_map 必须显式给出"


def test_strict_rank_filter_no_fallback(ts):
    # 2.2 规则一：先按真实 Level 过滤再映射，不得走「最具体可用层级」fallback。
    eon = ts.find_by_name("Phanerozoic")
    assert eon is not None
    with pytest.raises(InvalidRankError):
        ts.find_by_name("Ectasian", rank="Epoch")  # Ectasian 属 Period 级


def test_unknown_metadata_marked_not_fabricated(ts):
    # 1.4/2.2 规则二：pyrolite 的公开表没有逐边界的 GSSP/GSSA 状态，因此后端
    # **必须**把 qualifier/definition 都标成 unknown。断言只能用相等，不能用
    # 析取（如 `in ("unknown", "constrained")` /
    # `in ("unknown", "numeric_estimate", "gssp")`）：析取下后端伪造出真实 GSSP
    # 元数据也判通过——恰是该测试要防的情形。
    interval = ts.find_by_age(66.0, rank="Period")
    assert interval.older_boundary.qualifier == "unknown"
    assert interval.older_boundary.definition == "unknown"
    assert interval.younger_boundary.qualifier == "unknown"
    assert interval.younger_boundary.definition == "unknown"
    # 与能力声明自洽：metadata 说不提供边界定义，逐记录结果就不能出现别的取值。
    assert ts.metadata.has_boundary_definition == "unknown"


def test_get_interval_unsupported(ts):
    with pytest.raises(IntervalNotFoundError):
        ts.get_interval("ics:period:jurassic")


def test_iter_window(ts):
    periods = list(ts.iter_intervals(ranks=["Period"], min_age=0.0, max_age=100.0))
    assert periods

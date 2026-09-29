"""数值刻度契约测试（开发文档 4.6）。"""

from __future__ import annotations

import matplotlib.pyplot as plt
import pytest

from geophylo.render.ticks import (
    cap_ticks,
    dedupe_ages,
    fill_ages_style,
    filter_by_pixel_distance,
    format_age,
)

GOLDEN_CASES = [
    (0.0, "0.00"),
    (0.01, "0.01"),
    (0.5, "0.50"),
    (1.0, "1"),
    (66.0, "66"),
    (99.9, "99.9"),
    (100.0, "100"),
    (538.8, "539"),
]


@pytest.mark.parametrize(("age", "expected"), GOLDEN_CASES)
def test_format_age_golden(age, expected):
    assert format_age(age) == expected


def test_dedupe_snap():
    assert dedupe_ages([66.0, 66.0 + 5e-10, 100.0, 251.902]) == pytest.approx(
        [251.902, 100.0, 66.0]
    )


def test_fill_ages_style():
    # 相邻边界间隔超过窗口 20% 的区段补充等距刻度。
    fills = fill_ages_style([0.0, 500.0], min_age=0.0, max_age=541.0)
    assert fills, "应产生补充刻度"
    assert all(0.0 < a < 541.0 for a in fills)
    # 所有间隔都不超过窗口 20%（窗口 [420, 450]、阈值 6，全部间隔 = 6）不补充。
    assert fill_ages_style([426.0, 432.0, 438.0, 444.0], min_age=420.0, max_age=450.0) == []


def test_cap_ticks_precedence():
    # 优先级：rank 边界 > 整十/整百 > 其他中间值；同一层内一律从最老端起取用
    # （boundaries 与 fills 两层的抽样方向统一为"从最老起"）。
    boundaries = [521.0, 509.0, 497.0, 486.85, 358.9]
    fills = [510.0, 500.0, 250.0, 200.0, 100.0, 150.0, 123.4]
    capped = cap_ticks(boundaries, fills, tick_max_count=6)
    assert len(capped) <= 6
    assert set(boundaries) <= set(capped)  # rank 边界优先
    assert capped == sorted(capped, reverse=True)  # 返回值从老到新（dedupe 序）
    assert 510.0 in capped  # 整十层优先于其他中间值，且层内最老者先取
    assert 123.4 not in capped  # 非整十的中间值排在整十之后


def test_cap_ticks_round_tier_is_not_empty():
    # 补刻点是等分值，浮点噪声（30.0 → 29.999999999999996）会让"整十/整百"层级恒为
    # 空集，三级裁剪退化为两级。因此整十判定必须带容差：本该是整十的补刻点
    # 要赢过纯中间值——即使它在数值上更年轻。
    boundaries = [500.0, 400.0]
    noisy_round = 30.0 - 3.552713678800501e-15  # 30.0 的浮点噪声形式
    assert noisy_round != 30.0
    capped = cap_ticks(boundaries, [noisy_round, 12.5], tick_max_count=3)
    assert noisy_round in capped
    assert 12.5 not in capped


def test_is_round_ma_tolerance():
    from geophylo.render.ticks import _is_round_ma

    assert _is_round_ma(30.0)
    assert _is_round_ma(29.999999999999996)
    assert _is_round_ma(300.0000000001)
    assert not _is_round_ma(29.9)  # 真不是整十的不能被判成整十
    assert not _is_round_ma(35.0)
    assert not _is_round_ma(0.0)
    assert not _is_round_ma(-10.0)


def test_pixel_distance_filter_keeps_older():
    _, ax = plt.subplots(figsize=(6, 4))
    ax.set_xlim(0, 541)
    ax.figure.canvas.draw()  # 固定变换

    def to_display(age: float) -> float:
        return ax.transData.transform((age, 0.0))[0]

    # 间距小于 min_gap 的两个刻度保留较老者（Ma 数值更大者）：
    # 66.0 与 66.0-3px（更年轻）→ 保留 66.0。
    younger = 66.0 - 3.0 / (465.0 / 541)
    ages = dedupe_ages([100.0, 66.0, younger])
    kept = filter_by_pixel_distance(ages, to_display=to_display, min_gap_px=2 * 6)
    assert 66.0 in kept
    assert all(younger != a for a in kept)

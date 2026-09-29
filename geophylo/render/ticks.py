"""数值刻度契约的实现（规范 4.6）。

本库不实现自定义 ``Locator``/``Formatter`` 子类：刻度位置按契约在绘制窗口内
显式求值，渲染为手工 ``Line2D``/``Text``（见 ``render/linear.py``）；
``FixedLocator`` + ``FuncFormatter`` 的组合语义仅作为格式化规则的参照实现。
"""

from __future__ import annotations

import math

from ..exceptions import InvalidRangeError

__all__ = ["cap_ticks", "dedupe_ages", "fill_ages_style", "filter_by_pixel_distance", "format_age"]


def format_age(age: float) -> str:
    """确定性格式化规则（黄金样例见规范 4.6）。

    ``0 <= age < 1`` 固定两位小数；``1 <= age < 100`` 固定一位小数、小数部分
    为零时省略小数点与尾零；``age >= 100`` 用整数（四舍五入）。

    注意：``age >= 100`` 取整意味着快照里 251.902 Ma 这样的存储精度无法从
    格式化器直接得到；需要按存储精度输出的调用方应在调用侧覆写格式化规则。
    """
    if age < 0:
        raise InvalidRangeError(f"age 不能为负：{age!r}")
    if age < 1:
        return f"{age:.2f}"
    if age < 100:
        text = f"{age:.1f}"
        if text.endswith(".0"):
            text = text[:-2]
        return text
    return str(math.floor(age + 0.5))


def dedupe_ages(ages, tol: float = 1e-9) -> list[float]:
    """去重并按从老到新（数值降序）排序；容差内视为同一边界。"""
    ordered = sorted({float(a) for a in ages}, reverse=True)
    result: list[float] = []
    for age in ordered:
        if result and abs(result[-1] - age) <= tol:
            continue
        result.append(age)
    return result


def fill_ages_style(
    boundaries: list[float],
    *,
    min_age: float,
    max_age: float,
) -> list[float]:
    """``tick_style="ages"``：对相邻边界间隔超过窗口 20% 的区段补充等距刻度。

    区段被等分为 ``ceil(gap / (0.2 * 窗口宽度))`` 段，只在区段内部补刻度，
    不与既有边界重复。
    """
    window = max_age - min_age
    if window <= 0:
        return []
    threshold = 0.2 * window
    ordered = sorted(boundaries)
    filled: set[float] = set()
    stops = [min_age, *ordered, max_age]
    for lo, hi in zip(stops, stops[1:], strict=False):
        gap = hi - lo
        if gap <= threshold:
            continue
        segments = max(2, math.ceil(gap / threshold))
        step = gap / segments
        for k in range(1, segments):
            value = lo + k * step
            if min_age < value < max_age:
                filled.add(value)
    return sorted(filled, reverse=True)


def _is_round_ma(age: float, *, tol: float = 1e-6) -> bool:
    """整十/整百 Ma（如 10、20、…、100、200、…）。

    判定带容差：``fill_ages_style()`` 的补刻点是区段的等分值 ``lo + k * step``，
    数学上正好是整十的值在浮点上常表现为 ``29.999999999999996`` 这类噪声，
    用 ``age == int(age)`` 精确比较会让整十层级恒为空集。
    """
    if age <= 0:
        return False
    nearest = round(age)
    return abs(age - nearest) <= tol and int(nearest) % 10 == 0


def cap_ticks(
    boundaries: list[float],
    fills: list[float],
    *,
    tick_max_count: int,
) -> list[float]:
    """``tick_max_count`` 是硬上限；裁剪优先级：rank 边界 > 整十/整百 > 中间值。

    两个层级的抽样方向统一为**从最老一端优先**（fills 层若按升序取用会从最年轻
    一端开始，与边界层相反）：

    * ``boundaries`` 超上限时等步长间距采样，索引从最老端起（输入按降序）；
    * ``fills`` 在剩余预算内按整十/整百优先、同级内从最老到最年轻依次取用。

    返回值统一为**从老到新**（数值降序），与 :func:`dedupe_ages` 的序一致，
    因此调用方可以直接把它交给 ``filter_by_pixel_distance``。
    """
    budget = max(1, tick_max_count)
    kept = list(boundaries)
    if len(kept) > budget:
        stride = math.ceil(len(kept) / budget)
        kept = kept[::stride]
        if len(kept) > budget:
            kept = kept[:budget]
    if len(kept) + len(fills) <= budget:
        return sorted(kept + fills, reverse=True)
    round_fills = sorted((a for a in fills if _is_round_ma(a)), reverse=True)
    other_fills = sorted((a for a in fills if not _is_round_ma(a)), reverse=True)
    for age in round_fills:
        if len(kept) >= budget:
            break
        kept.append(age)
    for age in other_fills:
        if len(kept) >= budget:
            break
        kept.append(age)
    return sorted(kept, reverse=True)


def filter_by_pixel_distance(
    ages: list[float],
    *,
    to_display,
    min_gap_px: float,
) -> list[float]:
    """按像素距离过滤：任何两个刻度中心间距小于 ``min_gap_px`` 时保留较老者。

    ``ages`` 须已按从老到新排序；``to_display`` 把年龄映射到显示坐标
    ``(x, y)``（取时间维的像 素位置）。
    """
    kept: list[float] = []
    kept_pixels: list[float] = []
    for age in ages:
        pixel = to_display(age)
        if kept and abs(pixel - kept_pixels[-1]) < min_gap_px:
            continue
        kept.append(age)
        kept_pixels.append(pixel)
    return kept

"""两个数据后端共享的查询语义（规范 4.2/4.3）。

内置快照后端与实验性的 pyrolite 后端必须在同一套规则下回答同一类问题，否则
``Timescale(backend=...)`` 换的是数据源、却悄悄换了语义。本模块把三条易漂移的
规则收在一处，两个后端都从这里取答案：

1. **rank 池**（``core_rank_pool``）：只有 ``rank_class == "geochronologic"`` 的
   区间参与查询；结构节点（Supereon/Subepoch/…）只作 ``parent_id`` 锚点，
   不得成为 ``find_by_age`` 的命中项。
2. **年龄归属**（``resolve_age``）：先按 1e-9 容差吸附到最近边界，再按
   「边界值归属于以其为 ``older_ma`` 的较年轻区间」（左闭右开）判定；多个 rank
   同时命中时返回最具体者（``Age`` > ``Epoch`` > ``Period`` > ``Era`` > ``Eon``）。
3. **名称通道**（``search_by_name``）：``name → aliases → label`` 三通道依次求值，
   前一个通道有命中就不再看后面的通道；每个通道内部**精确匹配优先**，无精确
   命中才回退到子串匹配。

窗口遍历（``select_window`` / ``rank_traversal_order``）另收两条共同规则：
``ranks=None`` 恒等于五个核心 rank（不是"全部行"），年龄窗口带 1e-9 容差，
排序键为 ``(-older_ma, rank 序, id)``。
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence

from ..validation import CORE_RANKS
from .models import Interval

__all__ = [
    "NAME_CHANNELS",
    "RANK_SPECIFICITY",
    "SNAP_TOL",
    "NameSearch",
    "age_hit",
    "core_rank_pool",
    "present_youngest",
    "rank_traversal_order",
    "resolve_age",
    "search_by_name",
    "select_window",
    "snap_to_boundary",
    "specificity_key",
]

# 共享边界归属与吸附所用的容差（规范 7.2 的取值理由：见
# ``geophylo.data.builtin._TOL`` 与 docs/spec/README.md）。
SNAP_TOL = 1e-9

# rank 具体度：数值越小越具体（规范 4.2 第 4 条）。
RANK_SPECIFICITY: dict[str, int] = {"Age": 0, "Epoch": 1, "Period": 2, "Era": 3, "Eon": 4}

# 名称查询的通道顺序（规范 4.3）。
NAME_CHANNELS: tuple[str, ...] = ("name", "aliases", "label")

# ``search_by_name`` 的结果形态：(结论, 命中通道, 命中列表)。
NameSearch = tuple[str, str | None, list[Interval]]


def specificity_key(rank: str) -> int:
    """rank 的具体度排序键；非核心 rank 排在核心 rank 之后。"""
    return RANK_SPECIFICITY.get(rank, len(RANK_SPECIFICITY))


def core_rank_pool(intervals: Iterable[Interval], rank: str | None = None) -> list[Interval]:
    """按 rank 过滤，并始终排除结构节点（``rank_class != "geochronologic"``）。"""
    return [
        interval
        for interval in intervals
        if (rank is None or interval.rank == rank) and interval.rank_class == "geochronologic"
    ]


def snap_to_boundary(age: float, intervals: Iterable[Interval], *, tol: float = SNAP_TOL) -> float:
    """把输入年龄吸附到 ``tol`` 内最近的区间边界上（无命中则原样返回）。"""
    best = age
    best_distance = tol
    for interval in intervals:
        for boundary_age in (interval.older_ma, interval.younger_ma):
            distance = abs(age - boundary_age)
            if distance <= best_distance:
                best = boundary_age
                best_distance = distance
    return best


def age_hit(pool: Sequence[Interval], age: float) -> Interval | None:
    """左闭右开归属：边界值归属于以其为 ``older_ma`` 的较年轻区间。"""
    for interval in sorted(pool, key=lambda i: (specificity_key(i.rank), -i.older_ma, i.id)):
        if interval.older_ma >= age > interval.younger_ma:
            return interval
    return None


def resolve_age(
    pool: Sequence[Interval], age: float, *, tol: float = SNAP_TOL
) -> tuple[Interval | None, float]:
    """吸附 + 归属的合流：返回 ``(命中区间或 None, 吸附后的年龄)``。"""
    snapped = snap_to_boundary(age, pool, tol=tol)
    return age_hit(pool, snapped), snapped


def present_youngest(pool: Sequence[Interval]) -> list[Interval]:
    """``0.0 Ma`` 的合法归属：年轻端就是 0 Ma 或以「present」定义的区间。

    内置快照里两者等价（``younger_ma == 0`` ⟺ ``definition == "present"``，
    实测 0 处不符）；pyrolite 公开表没有 ``definition``，因此按 0 Ma 一侧判定。
    """
    return [
        interval
        for interval in pool
        if interval.younger_ma <= SNAP_TOL or interval.younger_boundary.definition == "present"
    ]


def rank_traversal_order(intervals: Iterable[Interval]) -> list[Interval]:
    """确定性遍历序：从老到新 → rank 序（Eon→Age）→ 稳定 ID。"""
    rank_order = {rank: idx for idx, rank in enumerate(CORE_RANKS)}
    return sorted(
        intervals,
        key=lambda i: (-i.older_ma, rank_order.get(i.rank, len(CORE_RANKS)), i.id),
    )


def select_window(
    intervals: Iterable[Interval],
    ranks: Sequence[str],
    lo: float,
    hi: float,
    *,
    tol: float = SNAP_TOL,
) -> list[Interval]:
    """选出落在 ``[lo, hi]`` 窗口内的区间（含容差）并按 :func:`rank_traversal_order` 排序。"""
    selected = set(ranks)
    chosen = [
        interval
        for interval in intervals
        if interval.rank in selected
        and interval.older_ma >= lo - tol
        and interval.younger_ma <= hi + tol
    ]
    return rank_traversal_order(chosen)


def _channel_field(interval: Interval, channel: str) -> Sequence[str]:
    if channel == "aliases":
        return interval.aliases
    return (str(getattr(interval, channel)),)


def search_by_name(
    pool: Sequence[Interval],
    name: str,
    *,
    case_sensitive: bool = False,
    key: Callable[[Interval], tuple] = lambda i: (-i.older_ma, i.id),
) -> NameSearch:
    """按 ``name → aliases → label`` 三通道查询，通道内精确匹配优先。

    结论取值：``"found"``（唯一命中）、``"ambiguous"``（同通道多命中，需消歧）、
    ``"missing"``（三通道均无匹配）。歧义候选按 ``key`` 排序，保证跨后端确定。
    """

    def matches(text: str, *, exact: bool) -> bool:
        if case_sensitive:
            return text == name if exact else name in text
        folded_name, folded_text = name.casefold(), text.casefold()
        return folded_text == folded_name if exact else folded_name in folded_text

    for channel in NAME_CHANNELS:
        exact_hits = [
            interval
            for interval in pool
            if any(matches(text, exact=True) for text in _channel_field(interval, channel))
        ]
        if len(exact_hits) == 1:
            return ("found", channel, exact_hits)
        if len(exact_hits) >= 2:
            return ("ambiguous", channel, sorted(exact_hits, key=key))
        fuzzy_hits = [
            interval
            for interval in pool
            if any(matches(text, exact=False) for text in _channel_field(interval, channel))
        ]
        if len(fuzzy_hits) == 1:
            return ("found", channel, fuzzy_hits)
        if len(fuzzy_hits) >= 2:
            return ("ambiguous", channel, sorted(fuzzy_hits, key=key))
    return ("missing", None, [])

"""实验性的 pyrolite 只读兼容后端（规范 2.2/8.2）。

三条使用规则（规范 2.2）：

1. 严格 ``rank`` 查询不得走 pyrolite 的 fallback 行为：先按其 DataFrame 的
   真实 ``Level`` 过滤，再映射到核心 rank。
2. 缺失元数据一律标记为 ``unknown``，不得伪造成 ``qualifier="defined"`` 或
   无误差的数值；上游缺少颜色时使用中性的 ``UNKNOWN_COLOR_PLACEHOLDER`` 并在
   构造后发一次 ``UserWarning`` 报告受影响行数。
3. 版本锁定：``pyrolite>=0.3.7``（``MIN_PYROLITE_VERSION``，报错文案与该常量
   同源，不硬编码字面量）。

**查询语义与内置快照后端共享同一份实现**：``find_by_age`` 的 rank 池、
边界归属与吸附容差，``iter_intervals`` 的 ``ranks=None`` 含义（五个核心 rank，
**不是**全部行）与 1e-9 窗口容差，``find_by_name`` 的 ``name → aliases → label``
通道序与精确匹配优先——全部来自 :mod:`geophylo.data._query`。

该后端状态为 **experimental**，其能力声明测试不阻塞发布。
不自动联网，也不静默更新结果。
"""

from __future__ import annotations

import math
import warnings
from collections.abc import Iterator, Sequence

from ..exceptions import (
    AmbiguousIntervalError,
    DataValidationError,
    IntervalNotFoundError,
    InvalidRangeError,
    InvalidRankError,
)
from ..validation import CORE_RANKS, normalize_ranks
from ._query import core_rank_pool, present_youngest, resolve_age, search_by_name, select_window
from .models import BackendMetadata, Boundary, Interval

__all__ = ["MIN_PYROLITE_VERSION", "PyroliteBackend"]

MIN_PYROLITE_VERSION = (0, 3, 7)
MIN_PYROLITE_VERSION_STR = ".".join(str(part) for part in MIN_PYROLITE_VERSION)

# 窗口与吸附容差：与内置快照后端的 ``_TOL`` 同值——贴边区间在两后端必须
# 给出同样的取舍。
_TOL = 1e-9

# 上游行缺少颜色时使用的**中性**占位色：黑色条带在图上读起来像设计选择，
# 而不是「本库不知道这个区间的颜色」。占位色不携带任何年代地层含义，且构造
# 完成后发一次 ``UserWarning`` 报告受影响行数——缺失元数据被标记为未知，而不
# 是被伪造成一个看起来可信的颜色（规范 2.2 规则二）。
UNKNOWN_COLOR_PLACEHOLDER = "#CCCCCC"

# pyrolite Level 名 -> 核心 rank / 结构标记。
_LEVEL_MAP: dict[str, str] = {
    "Supereon": "structural",
    "Eon": "Eon",
    "Era": "Era",
    "Period": "Period",
    "Epoch": "Epoch",
    "Age": "Age",
    "Superepoch": "structural",
    "Subepoch": "structural",
}


def _is_blank(value) -> bool:
    """pyrolite 表中的层级列缺失时为 ``NaN``（float）或空串。"""
    if value is None:
        return True
    try:
        if math.isnan(value):
            return True
    except TypeError:
        pass
    return str(value).strip() == ""


def _colour_to_hex(value: object) -> str | None:
    """把 pyrolite 表里的颜色读成 ``#RRGGBB``；确实无颜色时返回 ``None``。

    实测 pyrolite 0.3.7 的 ``Timescale().data["Color"]`` 是 **RGBA 浮点元组**
    （如 ``(0.6039, 0.8509, 0.8666, 1.0)``），179 行里没有一行是 ``#`` 字符串；
    只接受 ``#`` 开头字符串的判据会把全部行都误判为"缺颜色"并落到中性占位色，
    那既丢掉了真实的 ICS 官方配色，也是一条关于上游数据的假陈述。因此这里同时
    接受十六进制字符串与 3/4 分量的 0–1 浮点序列；只有真正缺失/畸形时才返回
    None，由调用方计数并告警（规则 2：缺失元数据不伪造）。
    """
    if isinstance(value, str):
        text = value.strip()
        if text.startswith("#"):
            digits = text[1:]
            if len(digits) == 3:  # 三位缩写色 → 展开
                digits = "".join(ch * 2 for ch in digits)
            if len(digits) == 6 and all(ch in "0123456789abcdefABCDEF" for ch in digits):
                return f"#{digits.upper()}"
        return None
    if isinstance(value, (tuple, list)) and 3 <= len(value) <= 4:
        try:
            channels = [float(v) for v in value[:3]]
        except (TypeError, ValueError):
            return None
        if all(0.0 <= ch <= 1.0 for ch in channels):  # matplotlib 式 0–1 分量
            return "#" + "".join(f"{round(ch * 255):02X}" for ch in channels)
        # 0–255 形式只有在**整条向量都不小于 1** 时才成立：混尺度输入（如
        # (0.5, 0.5, 2.0)）按 0–255 解释会把 0.5 静默读成 0（近黑），那是比
        # "不认识"更糟的结果——宁可返回 None 让调用方告警，也不猜。
        if all(1.0 <= ch <= 255.0 for ch in channels):
            return "#" + "".join(f"{round(ch):02X}" for ch in channels)
    return None


def _true_rank(row) -> str:
    """按 pyrolite 行的真实层级映射核心 rank，并纠正其前寒武纪层级错标。

    pyrolite 的数据模型没有前寒武纪 Period 槽位：Ectasian 这类 Era 的直接
    细分被标成 Level="Epoch"（Period 父列为空）。本库内置快照（ICS 图表）
    将这些单元定为 Period（如 ``ics:period:ectasian``），因此按「Period 父列
    为空且 Era 父列存在」这一确定性特征把它们纠正回 Period，保证两个后端
    对同一区间的 rank 语义一致（规范 2.2 规则一：先按真实 Level 过滤
    再映射）。

    适用面（固定下来，避免它悄悄变成通用启发式；见
    ``tests/test_timescale_query.py::TestPyroliteRankHeuristic``）：

    * **只**处理 ``Level == "Epoch"`` 且 ``Period`` 列为空/NaN 且 ``Era`` 列
      非空的行；其余行一律按 ``_LEVEL_MAP`` 原样映射；
    * 它不推断父子关系，也不补齐任何缺失的年龄/误差/颜色（那是规则二）；
    * 命中即计数并在构造后发一次 ``UserWarning``（见 ``__init__``），使该
      纠正对使用者可见，而不是静默改写元数据。
    """
    level = str(row.get("Level", "unknown"))
    rank = _LEVEL_MAP.get(level, "structural")
    if rank == "Epoch" and _is_blank(row.get("Period")) and not _is_blank(row.get("Era")):
        return "Period"
    return rank


def _require_pyrolite():
    try:
        import pyrolite
    except ImportError as exc:  # pragma: no cover - 可选依赖缺失
        raise ImportError("pyrolite 后端需要可选依赖 pyrolite；请安装 geophylo[pyrolite]") from exc
    version = getattr(pyrolite, "__version__", "0")
    parts = []
    for chunk in version.split(".")[:3]:
        digits = "".join(c for c in chunk if c.isdigit())
        parts.append(int(digits) if digits else 0)
    while len(parts) < 3:
        parts.append(0)
    if tuple(parts) < MIN_PYROLITE_VERSION:
        raise ImportError(
            f"pyrolite>={MIN_PYROLITE_VERSION_STR} 是本后端的版本下界"
            f"（锚定 2024/12 数据与 Supereon 层级），当前为 {version!r}"
        )
    return pyrolite


def _row_age(where: str, column: str, value) -> float:
    """把上游 ``Start``/``End`` 单元格读成有限数值；非法取值走公共异常。

    ``float()`` 对 ``None``/空串/带单位字符串抛原始 ``TypeError``/``ValueError``，
    会绕过本库「第三方原始异常不得直接冒泡」的契约（规范 4.7）。
    """
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise DataValidationError(
            f"pyrolite 表 {where} 的 {column} 不是数值（{value!r}）；本后端不做外推，也不猜测单位"
        ) from exc
    if not math.isfinite(number):
        raise DataValidationError(
            f"pyrolite 表 {where} 的 {column} 非有限值（{value!r}）；无法建立时间语义"
        )
    return number


class PyroliteBackend:
    """只读兼容后端：包装 ``pyrolite.util.time.Timescale`` 的公开表。

    缺失元数据（稳定 ID、GSSP/GSSA 状态、逐边界误差）一律 ``unknown``；
    ID 通道不可用（``get_interval`` 恒抛 ``IntervalNotFoundError``）。
    """

    def __init__(self) -> None:
        _require_pyrolite()
        from pyrolite.util.time import Timescale as PyroliteTimescale

        self._ts = PyroliteTimescale()
        frame = self._ts.data
        self._intervals: list[Interval] = []
        missing_color = 0
        rank_corrected = 0
        for row_index, row in frame.iterrows():
            name = str(row.get("Name") or "")
            where = f"{name or '<unnamed>'}（第 {row_index} 行）"
            start = _row_age(where, "Start", row["Start"])
            end = _row_age(where, "End", row["End"])
            if not (math.isfinite(start) and math.isfinite(end)):  # pragma: no cover
                continue  # _row_age 已拒绝非有限值；保留分支以防上游改动
            older, younger = max(start, end), min(start, end)
            if older <= younger:
                continue  # 零宽/倒置行：本库不修数据，直接跳过
            colour = _colour_to_hex(row.get("Color"))
            if colour is None:
                missing_color += 1
                colour = UNKNOWN_COLOR_PLACEHOLDER
            rank = _true_rank(row)
            if rank == "Period" and str(row.get("Level", "")) == "Epoch":
                rank_corrected += 1  # _true_rank 的适用面（见其 docstring）
            structural = rank == "structural"
            self._intervals.append(
                Interval(
                    id=f"pyrolite:{rank.lower()}:{name.casefold().replace(' ', '-')}",
                    source_iri=None,
                    name=name,
                    label=name,
                    aliases=(),
                    rank=rank if not structural else str(row.get("Level", "unknown")),
                    rank_class="structural" if structural else "geochronologic",
                    parent_id=None,
                    source_parent_id=None,
                    status="unknown",
                    color=colour,
                    older_boundary=Boundary(
                        age_ma=older,
                        qualifier="unknown",
                        uncertainty_ma=None,
                        definition="unknown",
                    ),
                    younger_boundary=Boundary(
                        age_ma=younger,
                        qualifier="unknown",
                        uncertainty_ma=None,
                        definition="unknown",
                    ),
                )
            )
        if missing_color:
            warnings.warn(
                f"pyrolite 表中 {missing_color} 行缺少颜色：这些区间的条带使用中性占位色 "
                f"{UNKNOWN_COLOR_PLACEHOLDER}，它不代表任何年代地层含义（缺失元数据不"
                "被伪造成可信颜色）；需要配色请使用内置快照后端",
                UserWarning,
                stacklevel=3,
            )
        if rank_corrected:
            warnings.warn(
                f"pyrolite 表中 {rank_corrected} 行按「Level=Epoch 且 Period 父列为空且 "
                "Era 父列非空」的确定性特征被纠正为 Period（该后端没有前寒武纪 Period "
                "槽位）；纠正范围仅限该判据，见 _true_rank 的 docstring",
                UserWarning,
                stacklevel=3,
            )
        self.metadata = BackendMetadata(
            data_version="pyrolite",
            software_version="unknown",
            has_uncertainty=False,
            has_boundary_definition="unknown",
            has_stable_ids=False,
            rank_map=dict(_LEVEL_MAP),
        )

    # -- 协议面 -----------------------------------------------------------

    def get_interval(self, interval_id: str) -> Interval:
        raise IntervalNotFoundError(
            "pyrolite 公开表契约没有稳定 ID，本后端不支持 ID 查询；请改用 find_by_name()"
        )

    def find_by_name(
        self,
        name: str,
        *,
        rank: str | None = None,
        parent: str | None = None,
        case_sensitive: bool = False,
    ) -> Interval:
        if parent is not None:
            raise IntervalNotFoundError("pyrolite 公开表契约没有父子关系，本后端不支持 parent 过滤")
        if not isinstance(name, str) or not name:
            raise IntervalNotFoundError(f"name 必须是非空字符串，得到 {name!r}")

        pool: list[Interval] = self._intervals
        if rank is not None:
            if rank not in CORE_RANKS:
                raise InvalidRankError(f"非法 rank {rank!r}；核心 rank 为 {list(CORE_RANKS)!r}")
            pool = [i for i in pool if i.rank == rank]
        # 通道优先级（name → aliases → label）与精确匹配优先由 ``_query`` 统一
        # 实现，与内置快照后端同语义。
        verdict, _channel, hits = search_by_name(pool, name, case_sensitive=case_sensitive)
        if verdict == "found":
            return hits[0]
        if verdict == "ambiguous":
            raise AmbiguousIntervalError(
                f"名称查询 {name!r} 在 pyrolite 表中命中 {len(hits)} 个候选",
                candidates=[i.id for i in hits],
            )
        if rank is not None:
            # 严格过滤不做「最具体可用层级」回退：名称存在但不在请求的 rank
            # 上时，显式指出真实层级，而不是假装查无此区间。
            _v, _c, matching = search_by_name(self._intervals, name, case_sensitive=case_sensitive)
            if matching:
                true_ranks = sorted({i.rank for i in matching})
                raise InvalidRankError(
                    f"名称 {name!r} 存在于 pyrolite 表，但真实层级为 {true_ranks!r}，"
                    f"与请求的 rank={rank!r} 不符；严格 rank 过滤不做层级回退，"
                    "请改用正确的 rank 或省略 rank 过滤"
                )
        raise IntervalNotFoundError(f"名称 {name!r} 未命中 pyrolite 表中的任何区间")

    def find_by_age(self, age_ma: float, *, rank: str | None = None) -> Interval:
        if isinstance(age_ma, bool) or not isinstance(age_ma, (int, float)):
            raise InvalidRangeError(f"age_ma 必须是数值，得到 {age_ma!r}")
        age = float(age_ma)
        if not math.isfinite(age) or age < 0:
            raise InvalidRangeError(f"age_ma={age_ma!r} 必须是非负有限值")
        if rank is not None and rank not in CORE_RANKS:
            raise InvalidRankError(f"非法 rank {rank!r}；核心 rank 为 {list(CORE_RANKS)!r}")
        # 结构行（Supereon/Superepoch/Subepoch 等）不参与命中判定，且按 rank
        # 具体度而非「最老优先」挑选多 rank 同时命中的区间——与内置后端一致
        # （规范 4.2 第 1、4 条）。
        pool = core_rank_pool(self._intervals, rank)
        if not pool:
            raise IntervalNotFoundError(
                f"age_ma={age_ma!r} 在 rank={rank!r} 下无区间可用；"
                f"可用的 rank 为 {list(CORE_RANKS)!r}"
            )
        # 与内置快照后端一致的 0.0 语义：显式归入最年轻区间（规范 4.2 第 3 条）。
        hit, snapped = resolve_age(pool, age, tol=_TOL)
        if age == 0.0 or snapped == 0.0:
            present = present_youngest(pool)
            if present:
                return min(present, key=lambda i: i.older_ma)
        if hit is not None:
            return hit
        raise IntervalNotFoundError(f"age_ma={age_ma!r} 在 pyrolite 表（rank={rank!r}）中无区间")

    def iter_intervals(
        self,
        *,
        ranks: str | Sequence[str] | None = None,
        min_age: float | None = None,
        max_age: float | None = None,
    ) -> Iterator[Interval]:
        if ranks is None:
            selected: tuple[str, ...] | list[str] = CORE_RANKS
        else:
            selected = normalize_ranks(ranks)
        lo = float(min_age) if min_age is not None else 0.0
        hi = float(max_age) if max_age is not None else math.inf
        if lo >= hi:
            raise InvalidRangeError(f"要求 min_age < max_age，得到 {lo}, {hi}")
        # ``ranks=None`` 表示五个核心 rank（不是「全部行含结构行」），窗口带
        # 1e-9 容差，排序键与内置后端一致。
        return iter(select_window(self._intervals, selected, lo, hi, tol=_TOL))

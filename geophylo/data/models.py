"""数据层模型：``Interval``、``Boundary`` 与 ``BackendMetadata``（规范 2.3/5.6）。"""

from __future__ import annotations

import warnings
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Literal

BoundaryQualifier = Literal["defined", "constrained", "approximate", "present", "unknown"]
BoundaryDefinition = Literal["gssp", "gssa", "numeric_estimate", "present", "unknown"]
Capabilities = bool | Literal["unknown"]

__all__ = ["BackendMetadata", "Boundary", "Interval"]


@dataclass(frozen=True)
class Boundary:
    """区间的一个端点，携带逐边界的定义状态（ADR-5）。

    ``qualifier`` 描述边界**数值的性质**，``definition`` 描述界线的**定义方式**，
    两者正交：同一个 GSSP 界线的数值既可以是带定量误差的估计，也可以是上游
    明示的近似值（图表上的 ``~``）。``uncertainty_ma=None`` 表示上游未给出定量
    误差，**不**表示误差为零。

    ``qualifier`` 的取值口径（生成器侧的唯一真源是
    ``tools/build_snapshot.py::boundary_qualifier``）：``present`` → 年龄 0 的
    顶界；``approximate`` → 上游 ``skos:note "uncertain"``（``~``）；
    ``defined`` → GSSP/GSSA 且无公布误差；``constrained`` → 有公布的 ``±`` 误差；
    ``unknown`` → 既无 ``~`` 也无误差、且不是 GSSP/GSSA 定义。近似与定量误差可以
    共存：此时 ``qualifier="approximate"`` 而 ``uncertainty_ma`` 照旧保留。

    ``source_iri`` 留给能为端点提供稳定 IRI 的后端（如某些外部数据集）；ICS 图表
    把端点写成 blank node，无独立 IRI 可引用，因此两份内置快照里恒为 ``None``
    （区间级 ``Interval.source_iri`` 才是上游概念的可寻址标识）。

    ADR-5 记录见 ``docs/adr/ADR-5-per-boundary-state-model.md``。
    """

    age_ma: float
    qualifier: BoundaryQualifier
    uncertainty_ma: float | None
    definition: BoundaryDefinition
    source_iri: str | None = None

    @property
    def is_defined(self) -> bool:
        """边界由 GSSP/GSSA 定义。"""
        return self.definition in ("gssp", "gssa")

    @property
    def is_numeric(self) -> bool:
        """边界带数值约束（定量误差、``~`` 近似或纯数值估计）。

        ``unknown`` qualifier 不视为带数值约束（与 ``effective_uncertainty``
        返回 ``None`` 的口径一致）。
        """
        return self.qualifier in ("constrained", "approximate") and self.definition in (
            "numeric_estimate",
            "gssp",
            "gssa",
        )

    @property
    def effective_uncertainty(self) -> float | None:
        """``unknown`` 状态返回 ``None`` 而非 ``0.0``。"""
        if self.qualifier == "unknown":
            return None
        return self.uncertainty_ma


@dataclass(frozen=True)
class Interval:
    """一个 ICS 地质时间区间。

    ``older_ma``/``younger_ma`` 由边界投影得到（只读）；写入必须经过
    :class:`Boundary`。``rank_class`` 为 ``"geochronologic"`` 或 ``"structural"``；
    结构节点（如 Precambrian）只作为 ``parent_id`` 锚点存在，不出现在
    ``Timescale.ranks`` 中。
    """

    id: str
    source_iri: str | None
    name: str
    label: str
    aliases: tuple[str, ...]
    rank: str
    rank_class: str
    parent_id: str | None
    source_parent_id: str | None
    status: str
    color: str
    older_boundary: Boundary
    younger_boundary: Boundary

    @property
    def older_ma(self) -> float:
        return self.older_boundary.age_ma

    @property
    def younger_ma(self) -> float:
        return self.younger_boundary.age_ma

    @property
    def bounds(self) -> tuple[float, float]:
        """``(older_ma, younger_ma)``，满足 ``older_ma > younger_ma``。"""
        return (self.older_boundary.age_ma, self.younger_boundary.age_ma)

    @property
    def boundaries(self) -> tuple[Boundary, Boundary]:
        """``(older_boundary, younger_boundary)``，保留逐边界状态。"""
        return (self.older_boundary, self.younger_boundary)

    @property
    def has_approximate_boundary(self) -> bool:
        """任一端点带 ``~`` 近似值（``qualifier == "approximate"``）。

        谓词一律用属性（与 :attr:`has_defined_boundary`、
        :attr:`Boundary.is_defined` 同风格）；旧的方法写法
        :meth:`is_approximate_any` 作为兼容别名保留。
        """
        return any(b.qualifier == "approximate" for b in self.boundaries)

    @property
    def has_defined_boundary(self) -> bool:
        """任一端点由 GSSP/GSSA 定义。"""
        return any(b.is_defined for b in self.boundaries)

    def is_approximate_any(self) -> bool:
        """已废弃的方法别名；请改用 :attr:`has_approximate_boundary`。

        ``docs/user-guide.{en,zh}.md`` 的 API 速览以方法形式收录了这个名字，
        所以保留可调用，同时把 ``Interval`` 的谓词风格统一为属性。
        """
        warnings.warn(
            "Interval.is_approximate_any() 已废弃，请改用属性 "
            "Interval.has_approximate_boundary（谓词统一为属性）",
            DeprecationWarning,
            stacklevel=2,
        )
        return self.has_approximate_boundary


@dataclass(frozen=True)
class BackendMetadata:
    """后端能力声明。

    ``has_*`` 字段类型为 ``bool | Literal["unknown"]``，因为「不知道」与
    「没有」必须可区分。``rank_map`` 给出后端层级名到核心 rank 的显式映射。
    """

    data_version: str
    software_version: str
    has_uncertainty: Capabilities = "unknown"
    has_boundary_definition: Capabilities = "unknown"
    has_stable_ids: Capabilities = "unknown"
    rank_map: Mapping[str, str] = field(default_factory=dict)

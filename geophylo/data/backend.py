"""数据后端协议（规范 2.3）。

核心库只依赖此协议的最小面；内置快照与实验性的 pyrolite 适配都是它的实现。
``identifier`` 只接受稳定 ID 或 ``source_iri``；名称查询走 ``find_by_name()``，
ID 与名称是两条互不重叠的查询通道。
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from typing import Protocol, runtime_checkable

from .models import BackendMetadata, Interval

__all__ = ["TimescaleBackend"]


@runtime_checkable
class TimescaleBackend(Protocol):
    """ICS 时间尺度数据的只读查询协议。"""

    metadata: BackendMetadata

    def get_interval(self, interval_id: str) -> Interval:
        """按稳定 ID 或 ``source_iri`` 查询；未知抛 ``IntervalNotFoundError``。"""
        ...

    def find_by_name(
        self,
        name: str,
        *,
        rank: str | None = None,
        parent: str | None = None,
        case_sensitive: bool = False,
    ) -> Interval:
        """按名称/别名查询；0 命中或 ≥2 命中时抛对应异常。"""
        ...

    def find_by_age(self, age_ma: float, *, rank: str | None = None) -> Interval:
        """按年龄查询；边界归属与吸附容差语义见规范 4.2。"""
        ...

    def iter_intervals(
        self,
        *,
        ranks: str | Sequence[str] | None = None,
        min_age: float | None = None,
        max_age: float | None = None,
    ) -> Iterator[Interval]:
        """返回与 ``[min_age, max_age]`` 窗口**相交**的全部区间，确定性排序。"""
        ...

"""``Timescale``：统一查询门面（规范 4.1）。

用法::

    ts = Timescale()                       # 基线快照（versions.json 标注）
    ts = Timescale(version="2024/12")      # 显式指定已发布的快照版本
    ts = Timescale.from_json("my_ics.json")  # 经 schema 校验的离线时间表
    ts = Timescale(backend="pyrolite")     # 实验性只读兼容后端

不提供 ``named_age()``、``text2age()``、``intervals()`` 这类别名：它们与
``find_by_age()``、``find_by_name()``、``iter_intervals()`` 语义重叠，同时
保留会产生两套并行入口和两套测试口径。
"""

from __future__ import annotations

import json
import warnings
from collections.abc import Iterator, Sequence
from pathlib import Path
from typing import TYPE_CHECKING

from .data.builtin import SnapshotBackend, load_snapshot, snapshot_provenance
from .data.models import BackendMetadata, Interval
from .exceptions import DataValidationError
from .validation import CORE_RANKS

if TYPE_CHECKING:  # pragma: no cover
    from .data.backend import TimescaleBackend

__all__ = ["Timescale"]


class Timescale:
    """ICS 地质年代数据的查询入口。"""

    def __init__(
        self,
        backend: TimescaleBackend | str | None = None,
        *,
        version: str | None = None,
    ) -> None:
        from_index = False
        if isinstance(backend, str):
            if backend != "pyrolite":
                raise ValueError(
                    f"未知的 backend 字符串 {backend!r}；可用值为 'pyrolite'，"
                    "或传入 TimescaleBackend 实例"
                )
            from .data.pyrolite_backend import PyroliteBackend

            backend = PyroliteBackend()
            if version is not None:
                raise ValueError("pyrolite 后端不支持 version 选择；内置快照才支持版本化")
        elif backend is None:
            backend = SnapshotBackend(load_snapshot(version))
            from_index = True
        else:
            # 自定义实例同样拒绝 version 参数，与 pyrolite 分支口径一致
            if version is not None:
                raise ValueError(
                    "传入 TimescaleBackend 实例时不支持 version 选择；version 的数据来自实例本身"
                )
        self._backend = backend
        # 只有经 versions.json 解析出来的载荷才拥有"已发布快照"的出处：离线
        # from_json() 的字节可能与同名版本不同，若仍回报索引里的 payload_sha256
        # 就成了一条虚假出处声明（比缺失披露更糟）。
        self._published = from_index
        self._provenance = self._read_provenance()
        derived = (self._provenance or {}).get("derived_from")
        if derived:
            warnings.warn(
                f"快照版本 {self.version!r} 是推导快照：由 "
                f"{derived.get('chart_version')!r} 按 {derived.get('method')!r} 生成"
                f"（{derived.get('note') or '见 PROVENANCE.md'}）；它不是上游归档，"
                "与基线快照共享来源提交与哈希。完整披露见 "
                "``Timescale.provenance['provenance_document']``。",
                UserWarning,
                stacklevel=2,
            )

    def _read_provenance(self) -> dict | None:
        """内置快照的出处披露；离线/自定义/pyrolite 数据无已发布出处时为 ``None``。"""
        if not self._published or not isinstance(self._backend, SnapshotBackend):
            return None
        try:
            return snapshot_provenance(self.version)
        except DataValidationError:
            # ``from_json()`` 的离线载荷或未被索引收录的版本：不存在可披露的发布出处。
            return None

    @classmethod
    def from_json(cls, path: str | Path) -> Timescale:
        """从离线 JSON 构造；经与内置快照相同的 schema 校验。"""
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls(SnapshotBackend(payload))

    # -- 能力 -------------------------------------------------------------

    @property
    def ranks(self) -> tuple[str, ...]:
        """可用的核心层级：``('Eon', 'Era', 'Period', 'Epoch', 'Age')``。"""
        return CORE_RANKS

    @property
    def metadata(self) -> BackendMetadata:
        return self._backend.metadata

    @property
    def provenance(self) -> dict | None:
        """该实例数据的出处披露。

        返回 ``file``、``payload_sha256``、``derived_from`` 与
        ``provenance_document``（随包发布的 ``PROVENANCE.md`` 全文）；非内置快照
        后端或离线载荷返回 ``None``。装了包的人因此无需回仓库即可读到"这份快照
        是回退推导的"这一事实。
        """
        return dict(self._provenance) if self._provenance else None

    @property
    def version(self) -> str:
        """数据版本（内置快照为 chart_version）。"""
        return str(self._backend.metadata.data_version)

    # -- 查询 -------------------------------------------------------------

    def get_interval(self, interval_id: str) -> Interval:
        """按稳定 ID 查询（唯一接受 ID 的入口）。"""
        return self._backend.get_interval(interval_id)

    def find_by_name(
        self,
        name: str,
        *,
        rank: str | None = None,
        parent: str | None = None,
        case_sensitive: bool = False,
    ) -> Interval:
        """按名称/别名查询（大小写折叠后的子串匹配）。"""
        return self._backend.find_by_name(
            name, rank=rank, parent=parent, case_sensitive=case_sensitive
        )

    def find_by_age(self, age_ma: float, *, rank: str | None = None) -> Interval:
        """按年龄查询；边界归属与吸附容差语义见规范 4.2。"""
        return self._backend.find_by_age(age_ma, rank=rank)

    def iter_intervals(
        self,
        *,
        ranks: str | Sequence[str] | None = None,
        min_age: float | None = None,
        max_age: float | None = None,
    ) -> Iterator[Interval]:
        """返回与窗口**相交**的全部区间，确定性排序（older desc → rank 序 → id 序）。"""
        return self._backend.iter_intervals(ranks=ranks, min_age=min_age, max_age=max_age)

    def __repr__(self) -> str:  # pragma: no cover - 调试便利
        return f"Timescale(version={self.version!r})"

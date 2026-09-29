"""数据层：模型、后端协议、内置快照与实验性 pyrolite 适配。"""

from __future__ import annotations

from .backend import TimescaleBackend
from .builtin import (
    available_versions,
    baseline_version,
    load_snapshot,
    load_versions_index,
    snapshot_provenance,
)
from .models import BackendMetadata, Boundary, Interval

__all__ = [
    "BackendMetadata",
    "Boundary",
    "Interval",
    "TimescaleBackend",
    "available_versions",
    "baseline_version",
    "load_snapshot",
    "load_versions_index",
    "snapshot_provenance",
]

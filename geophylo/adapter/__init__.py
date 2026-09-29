"""适配层：把外部树对象转换为经过校验的坐标契约。

线性路径产出 ``CoordinateSpec``（``spec_from_biophylo()``，稳定 API），环形路径
产出 ``RadialSpec``（``radial_spec_from_biophylo()``，实验性）。适配器不负责
绘制，也不知道时间轴放在哪个位置。
"""

from __future__ import annotations

from .biopython import radial_spec_from_biophylo, spec_from_biophylo

__all__ = ["radial_spec_from_biophylo", "spec_from_biophylo"]


def __getattr__(name: str):  # pragma: no cover - 可选依赖按需导入
    if name == "spec_from_iplotx":
        from .iplotx import spec_from_iplotx

        return spec_from_iplotx
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

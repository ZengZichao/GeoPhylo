"""geophylo：面向 Matplotlib Axes 的地质时间轴可视化库。

**引用约定**：源码注释与 docstring 里的「规范 N.N」（以及紧随其后的裸节号，
如 ``（4.8）``、``（5.2 硬约束）``）一律指随包发布的规范索引
``docs/spec/README.md`` 的同名条目；该索引把每个节号映射到本仓库中承载该
规范性主张的文件/符号。规范内容以仓库内的代码与该索引为准，仓库之外不存在
需要查阅的「开发文档」。

稳定公共 API（规范 1.4 稳定性矩阵）::

    from geophylo import (
        Timescale, Interval, Boundary,            # 数据层
        CoordinateSpec, spec_from_biophylo,       # 坐标层与适配器
        add_geo_axis, GeoAxisResult,              # 绘制层
        TimescaleBackend,                         # 数据后端协议
        GeophyloError,                            # 异常体系（及子类）
    )

实验性符号（``add_geo_ring``、``RadialSpec``、``radial_spec_from_biophylo``、
``spec_from_iplotx``）同样可从顶层导入，但保持 experimental 语义（接口可能
变动）。
``pyrolite_backend`` 不在顶层 re-export，只从 ``geophylo.data.pyrolite_backend``
导入（experimental）。
"""

from __future__ import annotations

from ._version import __version__
from .adapter import radial_spec_from_biophylo, spec_from_biophylo
from .coordinate.radial import RadialSpec
from .coordinate.spec import CoordinateSpec
from .data.backend import TimescaleBackend
from .data.models import BackendMetadata, Boundary, Interval
from .exceptions import (
    AmbiguousIntervalError,
    AxesTypeError,
    CoordinateError,
    DataValidationError,
    GeophyloError,
    IntervalNotFoundError,
    InvalidRadiusError,
    InvalidRangeError,
    InvalidRankError,
)
from .render.linear import add_geo_axis
from .render.polar import add_geo_ring
from .render.result import GeoAxisResult, remove_all
from .timescale import Timescale

__all__ = [
    "AmbiguousIntervalError",
    "AxesTypeError",
    "BackendMetadata",
    "Boundary",
    "CoordinateError",
    "CoordinateSpec",
    "DataValidationError",
    "GeoAxisResult",
    "GeophyloError",
    "Interval",
    "IntervalNotFoundError",
    "InvalidRadiusError",
    "InvalidRangeError",
    "InvalidRankError",
    "RadialSpec",
    "Timescale",
    "TimescaleBackend",
    "__version__",
    "add_geo_axis",
    "add_geo_ring",
    "radial_spec_from_biophylo",
    "remove_all",
    "spec_from_biophylo",
    # 由模块级 __getattr__ 惰性解析（iplotx 为可选依赖），静态导出检查对此误报。
    "spec_from_iplotx",  # codeql[py/undefined-export]
]


def __getattr__(name: str):  # pragma: no cover - 可选依赖按需导入
    if name == "spec_from_iplotx":
        from .adapter.iplotx import spec_from_iplotx

        return spec_from_iplotx
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

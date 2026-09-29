"""geophylo 的公共异常体系（规范 4.7）。

所有公共异常继承 :class:`GeophyloError`。第三方库抛出的原始
``TypeError``/``ValueError`` 不得直接冒泡为公共契约：公开入口必须捕获并转换，
并用 ``raise ... from exc`` 保留原因链。
"""

from __future__ import annotations

__all__ = [
    "AmbiguousIntervalError",
    "AxesTypeError",
    "CoordinateError",
    "DataValidationError",
    "GeophyloError",
    "IntervalNotFoundError",
    "InvalidRadiusError",
    "InvalidRangeError",
    "InvalidRankError",
]


class GeophyloError(Exception):
    """geophylo 所有公共异常的基类。"""


class DataValidationError(GeophyloError):
    """快照 schema、层级、边界、颜色、哈希或共享边界一致性校验失败。

    也包括 ``versions.json`` 索引与快照文件或其 ``payload_sha256`` 不符，
    以及请求未发布的快照版本（消息含可用版本列表）。
    """


class InvalidRankError(GeophyloError):
    """非法 rank、空 ``ranks`` 序列或重复 rank。"""


class IntervalNotFoundError(GeophyloError):
    """按 ID、名称或年龄查不到区间，或该 rank 在该年龄无区间。"""


class AmbiguousIntervalError(IntervalNotFoundError):
    """名称查询命中多个候选。

    ``candidates`` 属性携带候选区间的稳定 ID 列表。
    """

    def __init__(self, message: str, *, candidates: list[str]) -> None:
        super().__init__(message)
        self.candidates = list(candidates)


class InvalidRangeError(GeophyloError):
    """``min_age >= max_age``、负年龄、NaN、``thickness_ratio`` 越界等取值域错误。"""


class InvalidRadiusError(GeophyloError):
    """负半径、``r_inner >= r_outer``、环带落在 ``rlim()`` 之外或 ``radius_range`` 非法。"""


class AxesTypeError(GeophyloError):
    """传入的 Axes 不是数值线性轴，或非极坐标 Axes 传给了极坐标接口。"""


class CoordinateError(GeophyloError):
    """坐标语义缺失或冲突、``age_to_data`` 域外输入、未确认的范围推断。"""

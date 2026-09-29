"""异常体系契约测试（开发文档 4.7）。"""

from __future__ import annotations

import pytest

from geophylo import (
    AmbiguousIntervalError,
    AxesTypeError,
    CoordinateError,
    DataValidationError,
    GeophyloError,
    IntervalNotFoundError,
    InvalidRadiusError,
    InvalidRangeError,
    InvalidRankError,
    Timescale,
)

PUBLIC_EXCEPTIONS = [
    DataValidationError,
    InvalidRankError,
    IntervalNotFoundError,
    AmbiguousIntervalError,
    InvalidRangeError,
    InvalidRadiusError,
    AxesTypeError,
    CoordinateError,
]


@pytest.mark.parametrize("exc_type", PUBLIC_EXCEPTIONS)
def test_all_public_exceptions_inherit_geophylo_error(exc_type):
    assert issubclass(exc_type, GeophyloError)


def test_ambiguous_error_carries_candidates():
    err = AmbiguousIntervalError("hit 2", candidates=["a", "b"])
    assert err.candidates == ["a", "b"]
    assert isinstance(err, IntervalNotFoundError)


def test_error_messages_carry_context():
    # 断言对象必须是**库自己拼出来的**消息：把字符串塞进构造函数、再断言其中含某个
    # 子串，实际检验的是 BaseException.__str__ 的透传。
    with pytest.raises(IntervalNotFoundError) as excinfo:
        Timescale().find_by_name("Nope-Not-An-Interval", rank="Epoch")
    message = str(excinfo.value)
    assert "Nope-Not-An-Interval" in message, message
    assert "Epoch" in message, message
    assert "rank" in message, message
    assert "未命中" in message, message

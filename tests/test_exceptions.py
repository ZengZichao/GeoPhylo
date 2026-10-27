"""异常体系契约测试（开发文档 4.7）。"""

from __future__ import annotations

import re

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
    assert "matches no interval" in message, message


CODE_PATTERN = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z0-9_]+)+$")


@pytest.mark.parametrize("exc_type", PUBLIC_EXCEPTIONS)
def test_every_public_exception_declares_its_own_code(exc_type):
    """每个公共异常自带稳定的机器码，形态为 ``domain.reason``。

    ``code`` 是给调用方和测试分支用的，不随文案与本地化变化，所以它必须是
    类自身的声明，而不是从父类继承下来的空值。
    """
    code = exc_type.code
    assert code, f"{exc_type.__name__} 必须声明非空 code"
    assert CODE_PATTERN.match(code), f"{exc_type.__name__}.code={code!r} 不符合 domain.reason"
    assert code != GeophyloError.code, f"{exc_type.__name__} 未覆盖基类的 code"


def test_public_exception_codes_are_unique():
    codes = [exc.code for exc in PUBLIC_EXCEPTIONS]
    assert len(codes) == len(set(codes)), f"机器码重复：{codes}"
    # 子类必须与父类区分开，否则按码分支时 "未找到" 与 "命中多个" 无法区分。
    assert AmbiguousIntervalError.code != IntervalNotFoundError.code


def test_code_is_readable_from_a_raised_library_error():
    with pytest.raises(IntervalNotFoundError) as excinfo:
        Timescale().find_by_name("Nope-Not-An-Interval", rank="Epoch")
    assert excinfo.value.code == "interval.not_found"


def test_code_can_be_narrowed_per_instance():
    """需要更细判别时，调用点可覆盖类级默认值；不传则沿用类级码。"""
    assert CoordinateError("x").code == "coordinate.spec"
    assert CoordinateError("x", code="coordinate.spec_type").code == "coordinate.spec_type"
    err = AmbiguousIntervalError("x", candidates=["a"], code="interval.ambiguous_rank")
    assert err.code == "interval.ambiguous_rank"
    assert err.candidates == ["a"]

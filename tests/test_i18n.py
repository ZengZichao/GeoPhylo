"""异常与警告消息的本地化契约（默认英文，``GEOPHYLO_LANG=zh`` 切中文）。

守的是两件事：① 默认语言是英文，不读中文的使用者也能读懂报错；
② 中文文案并未删除，``GEOPHYLO_LANG=zh`` 仍能取回。二者都断言，避免"把中文
删掉"和"默认又变回中文"这两种退化。
"""

from __future__ import annotations

import os
import subprocess
import sys

import pytest

from geophylo._i18n import LANG, msg
from geophylo.exceptions import GeophyloError
from geophylo.validation import require_number


def test_default_language_is_english():
    assert not LANG.startswith("zh"), f"默认语言应为英文，实际 {LANG!r}"
    assert msg("hello", "你好") == "hello"


def test_msg_switches_on_env(monkeypatch):
    monkeypatch.setattr("geophylo._i18n.LANG", "zh-CN")
    # msg() 读取模块级 LANG，故直接断言读取结果即可。
    from geophylo import _i18n

    assert _i18n.LANG.startswith("zh")
    assert _i18n.msg("hello", "你好") == "你好"


def test_public_error_message_is_english_by_default():
    from geophylo.exceptions import InvalidRangeError

    with pytest.raises(InvalidRangeError) as excinfo:
        require_number("alpha", "not-a-number")
    text = str(excinfo.value)
    assert "alpha" in text
    assert not any("一" <= ch <= "鿿" for ch in text), f"默认消息不应含中文：{text!r}"
    assert "must be a real number" in text


def test_chinese_message_available_through_env():
    """子进程验证：GEOPHYLO_LANG=zh 时消息确实切回中文。"""
    code = (
        "import geophylo.validation as v\n"
        "from geophylo.exceptions import GeophyloError\n"
        "try:\n"
        "    v.require_number('alpha', 'x')\n"
        "except GeophyloError as exc:\n"
        "    print(str(exc))\n"
    )
    proc = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        env={**os.environ, "GEOPHYLO_LANG": "zh", "MPLBACKEND": "Agg"},
        timeout=60,
    )
    assert proc.returncode == 0, proc.stderr
    out = proc.stdout.strip()
    assert any("一" <= ch <= "鿿" for ch in out), f"GEOPHYLO_LANG=zh 应给出中文，实际 {out!r}"


def test_every_public_exception_still_subclasses_geophylo_error():
    import geophylo.exceptions as exc_mod

    for name in dir(exc_mod):
        obj = getattr(exc_mod, name)
        if isinstance(obj, type) and issubclass(obj, BaseException) and obj is not BaseException:
            assert issubclass(obj, GeophyloError) or obj is GeophyloError, name

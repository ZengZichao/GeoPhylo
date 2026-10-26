"""异常与警告消息的本地化开关（默认英文）。

设计取舍：**内联双语、无消息目录**。每个 ``raise``/``warnings.warn`` 调用点把
英文与中文两条文案都写在原地（``msg(en, zh)``），因此消息可 grep、可 diff，
不需要维护键表；代价是双份字符串。异常上的 ``code`` 机器码与文案解耦，测试
应断言 ``code`` 而不是文案。

默认返回英文（国际读者与英文日志的默认可读性优先）；设 ``GEOPHYLO_LANG=zh``
（任意以 ``zh`` 开头的取值）返回中文。docstring 保持双语，不影响运行时输出。
"""

from __future__ import annotations

import os

__all__ = ["LANG", "msg"]

LANG: str = os.environ.get("GEOPHYLO_LANG", "en").strip().lower()


def msg(en: str, zh: str) -> str:
    """按 ``GEOPHYLO_LANG`` 选择文案：默认英文，``zh*`` 时返回中文。"""
    return zh if LANG.startswith("zh") else en

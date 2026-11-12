"""异常与警告消息的本地化开关（默认英文）。

设计取舍：**内联双语、无消息目录**。每个 ``raise``/``warnings.warn`` 调用点把
英文与中文两条文案都写在原地（``msg(en, zh)``），因此消息可 grep、可 diff，
不需要维护键表；代价是双份字符串。异常上的 ``code`` 机器码与文案解耦，测试
应断言 ``code`` 而不是文案。被内插进文案的**片段本身也必须是双语的**（定位
标签、提示句、缺陷明细等）：它们要写成 ``msg(英文, 中文)`` 再拼进两条文案，
否则中文片段会泄漏进英文条（英文条含 CJK、中文分号拼进英文句子）。

默认返回英文（国际读者与英文日志的默认可读性优先）；设 ``GEOPHYLO_LANG=zh``
（任意以 ``zh`` 开头的取值）返回中文。``LANG`` 在 import 本模块时一次性求值，
所以 ``GEOPHYLO_LANG`` 必须在 ``import geophylo`` **之前**设置（例如用环境变量）；
import 之后再修改不会生效——这一限制同样写在双语用户手册第 12 节。

docstring 目前以中文为主，尚未逐条配英文；这不影响运行时输出（运行时文案由
每个调用点的 ``msg(en, zh)`` 双语内联提供）。
"""

from __future__ import annotations

import os

__all__ = ["LANG", "msg"]

LANG: str = os.environ.get("GEOPHYLO_LANG", "en").strip().lower()


def msg(en: str, zh: str) -> str:
    """按 ``GEOPHYLO_LANG`` 选择文案：默认英文，``zh*`` 时返回中文。"""
    return zh if LANG.startswith("zh") else en

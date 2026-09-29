"""``_colour_to_hex`` 的回归测试（不依赖 pyrolite 是否安装）。

背景：pyrolite 0.3.7 的 ``Timescale().data["Color"]`` 实测是 **RGBA 浮点元组**，
179 行里没有一行是 ``#`` 字符串。因此 ``_colour_to_hex`` 必须接受多种表示法：只认
``#`` 字符串会把全部行判为"缺颜色"并落到中性占位色——既丢掉真实 ICS 配色，也对
上游数据作了假陈述。本文件钉住各表示法的转换，以及"真正缺失时不得伪造"。
"""

from __future__ import annotations

import pytest

from geophylo.data.pyrolite_backend import UNKNOWN_COLOR_PLACEHOLDER, _colour_to_hex


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        # pyrolite 实际给的形态：0–1 的 RGBA 浮点元组
        ((0.6039215686274509, 0.85098039214, 0.8666666666, 1.0), "#9AD9DD"),
        ((0.0, 0.0, 0.0, 1.0), "#000000"),
        ((1.0, 1.0, 1.0), "#FFFFFF"),
        # 0–255 形式同样接受
        ((154.0, 217.0, 221.0), "#9AD9DD"),  # 0–255 形式
        # 十六进制字符串
        ("#9AD9DD", "#9AD9DD"),
        ("  #9ad9dd  ", "#9AD9DD"),
        ("#abc", "#AABBCC"),
    ],
)
def test_supported_colour_representations(value: object, expected: str) -> None:
    assert _colour_to_hex(value) == expected


@pytest.mark.parametrize(
    "value",
    [
        None,
        float("nan"),
        "",
        "9AD9DD",  # 缺 # 前缀不算颜色
        "#12345",  # 位数不对
        "#GGHHII",  # 非十六进制
        (0.5, 0.5),  # 分量不足
        (0.5, 0.5, 300.0),  # 越界：既非 0–1 也非 0–255
        (0.5, 0.5, 2.0),  # 混尺度：不得按 0–255 静默把 0.5 读成 0
        (-0.1, 0.5, 0.5),  # 负分量
        ("x", "y", "z"),
        3,
    ],
)
def test_unusable_values_return_none_rather_than_fabricating(value: object) -> None:
    """返回 None 让调用方计数并告警；绝不把坏值伪装成某种颜色（规则 2）。"""
    # 返回 None 而不是某个颜色值：调用方据此计数并告警（规则 2：缺失元数据不得伪造）。
    assert _colour_to_hex(value) is None


def test_placeholder_is_only_used_for_genuine_gaps() -> None:
    """占位色不得覆盖任何可解析的颜色：否则"缺色计数"就成了假陈述。"""
    parsed = _colour_to_hex((0.6039215686274509, 0.85098039214, 0.8666666666, 1.0))
    assert parsed is not None and parsed != UNKNOWN_COLOR_PLACEHOLDER

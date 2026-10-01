"""iplotx 适配器集成测试（experimental marker；iplotx/ete4 缺失时整体跳过）。

模块级 ``importorskip`` 已经处理"依赖缺失 → 跳过"。因此测试体内任何来自 iplotx
或 geophylo 的异常都是**真故障**，必须让测试失败，而不是被 ``except Exception``
转成 SKIP（SKIP 计数会掩盖回归）。这里只保留一条窄口子——"当前
iplotx 版本没有这个布局"——它只覆盖第三方布局构造调用，且异常类型集合被
tests/test_adapter_iplotx_contract.py 的守卫钉住：geophylo 自身的任何异常都不在
其中，所以适配器报错永远逃不出测试。
"""

from __future__ import annotations

import matplotlib.pyplot as plt
import pytest
from conftest import LAYOUT_CONSTRUCTION_ERRORS

pytestmark = [pytest.mark.experimental]

iplotx = pytest.importorskip("iplotx")

from geophylo import AxesTypeError, CoordinateError  # noqa: E402
from geophylo.adapter import spec_from_iplotx  # noqa: E402

NEWICK = "((A:15.0, B:15.0):9.0, (C:14.0, D:14.0):10.0);"


def _make_artist(layout):
    """构造 iplotx artist；只对"版本不支持该布局"跳过，其余异常照常抛出。"""
    Tree = pytest.importorskip("ete4").Tree
    t = Tree(NEWICK)
    fig, ax = plt.subplots(figsize=(8, 5))
    try:
        artist = iplotx.tree(t, layout=layout, ax=ax, show=False)
    except LAYOUT_CONSTRUCTION_ERRORS as exc:  # 仅第三方布局 API 缺失/改名
        pytest.skip(
            f"iplotx {getattr(iplotx, '__version__', '?')} 无法构造 layout={layout!r}: {exc!r}"
        )
        raise  # 不可达：pytest.skip() 必然抛出；显式再抛保证 artist 在 return 前必然已绑定
    return fig, ax, artist


@pytest.mark.parametrize("layout", ["horizontal", "vertical"])
def test_all_orientations(layout):
    _fig, _ax, artist = _make_artist(layout)
    axis = "x" if layout == "horizontal" else "y"
    spec = spec_from_iplotx(artist, time_axis=axis, age_conversion=1.0, root_age=48.0)
    assert spec.mode == "root_distance"
    assert spec.age_range[0] >= 0
    assert spec.age_range[1] == pytest.approx(48.0)


def test_radial_layout_rejected_explicitly():
    _fig, _ax, artist = _make_artist("radial")
    with pytest.raises((AxesTypeError, CoordinateError), match=r"radial|极坐标"):
        spec_from_iplotx(artist, time_axis="x", age_conversion=1.0, root_age=48.0)


def test_missing_root_age_rejected():
    _fig, _ax, artist = _make_artist("horizontal")
    with pytest.raises(CoordinateError):
        spec_from_iplotx(artist, time_axis="x", age_conversion=1.0)  # type: ignore[arg-type]


def test_strip_axes_baseline():
    # 6.2：基线按 strip_axes=True 断言（宿主脊线与刻度被隐藏）；该默认值由集成测试
    # 锁定，geophylo 自身不依赖也不改变该设置。断言必须真的检查可见性：读一个出厂
    # rcParam 键会恒真且与"是否隐藏"无关。
    _fig, ax, artist = _make_artist("horizontal")
    assert not any(spine.get_visible() for spine in ax.spines.values()), (
        "iplotx 默认应隐藏宿主脊线（strip_axes）；上游默认值变了，或本库改动了宿主 Axes"
    )
    for labels in (ax.get_xticklabels(), ax.get_yticklabels()):
        assert all(not label.get_visible() for label in labels), "iplotx 默认应隐藏宿主刻度标签"

    before = (ax.get_xlim(), ax.get_ylim(), [s.get_visible() for s in ax.spines.values()])
    spec_from_iplotx(artist, time_axis="x", age_conversion=1.0, root_age=48.0)
    after = (ax.get_xlim(), ax.get_ylim(), [s.get_visible() for s in ax.spines.values()])
    assert before == after, "spec_from_iplotx() 不得修改宿主 Axes 的范围或脊线"
    # 宿主 Axes 仍是数值线性轴（geophylo 的前置条件）。
    assert ax.get_xscale() == "linear"

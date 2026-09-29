"""测试夹具：Agg 后端、快照与常用对象。

本文件必须随 sdist 一起发布：`ts`、`snapshot_payload`、
`inverted_fig_ax` 等夹具由它提供，缺了它整套测试在解包目录里直接报错。
tests/test_packaging.py::TestSdistManifest 与 check_wheel.py 一起钉住这一点。
"""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")  # 必须在 pyplot 导入前

import json
import sys
from importlib import resources
from pathlib import Path

import matplotlib.pyplot as plt
import pytest

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if (_PROJECT_ROOT / "geophylo" / "__init__.py").is_file() and str(_PROJECT_ROOT) not in sys.path:
    # sdist 解包后没有安装 geophylo 也要能直接跑套件。追加而不是
    # 插入：已安装的发行物优先，本地源码只作兜底。
    sys.path.append(str(_PROJECT_ROOT))

from geophylo import Timescale  # noqa: E402

SNAPSHOT_PACKAGE = "geophylo.data.snapshots"

#: 可选依赖测试里"这个版本的第三方 API 构造不出该布局"允许转成 SKIP 的**极窄**
#: 异常集合。任何 geophylo 自身异常类型都不在其中，所以适配器
#: 出错永远不会被"跳过"——该不变量由
#: tests/test_adapter_iplotx_contract.py 的守卫测试钉住。
LAYOUT_CONSTRUCTION_ERRORS: tuple[type[BaseException], ...] = (
    AttributeError,
    KeyError,
    NotImplementedError,
)


def pytest_configure(config: pytest.Config) -> None:
    """兜底注册 `experimental` marker（markers 表由发布配置维护）。

    ``--strict-markers`` 下未注册的 marker 会变成收集错误，整套实验性测试直接
    报错；只在配置里确实没有这一项时补登记，重复声明不会覆盖发布配置。
    """
    declared = config.getini("markers")
    if not any(str(item).split(":", 1)[0].strip() == "experimental" for item in declared):
        config.addinivalue_line(
            "markers",
            "experimental: 实验性符号（RadialSpec / add_geo_ring / iplotx）的测试标记",
        )


@pytest.fixture(autouse=True)
def _close_figures():
    """每个测试后关闭全部 Figure，避免 Agg 资源泄漏。"""
    yield
    plt.close("all")


@pytest.fixture(scope="session")
def snapshot_payload() -> dict:
    text = (resources.files(SNAPSHOT_PACKAGE) / "ics_chart-2026-06.json").read_text(
        encoding="utf-8"
    )
    return json.loads(text)


@pytest.fixture(scope="session")
def snapshot_payload_2024() -> dict:
    text = (resources.files(SNAPSHOT_PACKAGE) / "ics_chart-2024-12.json").read_text(
        encoding="utf-8"
    )
    return json.loads(text)


@pytest.fixture(scope="session")
def versions_index() -> dict:
    text = (resources.files(SNAPSHOT_PACKAGE) / "versions.json").read_text(encoding="utf-8")
    return json.loads(text)


@pytest.fixture(scope="session")
def ts() -> Timescale:
    return Timescale()


@pytest.fixture()
def inverted_fig_ax():
    """12×8 英寸、x 轴为反向 Ma 的宿主 Axes（时间校准树常见视图）。"""
    fig, ax = plt.subplots(figsize=(12, 8))
    ax.plot([520, 5], [1, 2])
    ax.set_xlim(541, 0)
    return fig, ax

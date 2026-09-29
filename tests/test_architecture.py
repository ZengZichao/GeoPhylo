"""架构守卫：包 import 图必须无环、且层间边必须向下。

支撑「本库架构健康」这一判断的结构前提是**层次单向 + 无环**：契约基础层在最底，
门面在最上，任何一边反向都会让"改动影响面可推理"失效。这道守卫没法由现有工具
代劳——`ruff` 的 `I` 规则只管导入排序不管方向，`mypy` 只管类型兼容，因此需要
一个专门的架构测试。

层归属的依据是各层 `__init__.py:1` 的自我声明（"数据层"/"坐标层"/"绘制层"/"适配层"）
与 `geophylo/__init__.py` 的稳定性矩阵、`docs/adr/ADR-4`。

三条断言：
① import 图无环；
② 不存在指向更高层的边（层序 = foundation < data/coordinate < render/adapter < facade）；
③ 同一层序上的兄弟层（data 与 coordinate、render 与 adapter）之间不得互相依赖，
   以保证它们可被独立推理与替换。

同层内的边（包 `__init__.py` 汇聚自己的子模块、层内复用）是预期形态，不判为违规。

只用标准库：不引入 `importlib` 依赖图工具，也不要求被测包可导入。
"""

from __future__ import annotations

import ast
from collections import defaultdict
from pathlib import Path
from typing import Final

import pytest

REPO_ROOT: Final = Path(__file__).resolve().parent.parent
PACKAGE_ROOT: Final = REPO_ROOT / "geophylo"

#: 模块 → 所属层。层名取自各层 `__init__.py` 的自我声明，与 LAYER_RANK 的层序对应。
MODULE_LAYER: Final[dict[str, str]] = {
    # 门面层
    "geophylo": "facade",
    "geophylo._version": "facade",
    # 契约基础层（最底层：被大量引用，自身不引用任何内部业务模块）
    "geophylo.exceptions": "foundation",
    "geophylo.validation": "foundation",
    # 数据层
    "geophylo.timescale": "data",
    "geophylo.data": "data",
    "geophylo.data.models": "data",
    "geophylo.data.backend": "data",
    "geophylo.data._query": "data",
    "geophylo.data.builtin": "data",
    "geophylo.data.pyrolite_backend": "data",
    # 坐标层
    "geophylo.coordinate": "coordinate",
    "geophylo.coordinate.spec": "coordinate",
    "geophylo.coordinate.transform": "coordinate",
    "geophylo.coordinate.radial": "coordinate",
    # 绘制层
    "geophylo.render": "render",
    "geophylo.render.linear": "render",
    "geophylo.render.polar": "render",
    "geophylo.render.result": "render",
    "geophylo.render.labels": "render",
    "geophylo.render.ticks": "render",
    # 适配层
    "geophylo.adapter": "adapter",
    "geophylo.adapter.biopython": "adapter",
    "geophylo.adapter.iplotx": "adapter",
}

#: 层序，越大越靠上。data/coordinate 与 render/adapter 各占同一级，由断言③保持互相独立。
LAYER_RANK: Final[dict[str, int]] = {
    "foundation": 0,
    "data": 1,
    "coordinate": 1,
    "render": 2,
    "adapter": 2,
    "facade": 3,
}


def _dotted(path: Path) -> str:
    """文件 → 规范化的点分模块名（`__init__.py` 归并为它所表示的包）。"""
    parts = path.relative_to(REPO_ROOT).with_suffix("").parts
    name = ".".join(parts)
    return name[: -len(".__init__")] if name.endswith(".__init__") else name


def _anchor(module: str, is_package: bool) -> str:
    """`from .x import y` 的解析锚点。

    包（`__init__.py`）里的 `.` 指**它自己**（`geophylo/data/__init__.py` 的
    `from .builtin` 是 `geophylo.data.builtin`）；普通模块里的 `.` 指它的父包。
    把这两者混为一谈会让所有包内相对导入错误上溯到顶层包，凭空造出"向上依赖"。
    """
    return module if is_package else module.rpartition(".")[0]


def _resolve(anchor_pkg: str, level: int, module: str | None) -> str | None:
    """按 PEP 366 解析导入目标，并回退到最近的上层内部模块。

    `level == 0` 是绝对导入（本库两种风格混用，例如 `render/labels.py` 在
    `if TYPE_CHECKING:` 里写 `from geophylo.data.models import Interval`），
    此时绝不能给目标加上当前包前缀。
    """
    if level == 0:
        target = module or ""
    else:
        parts = anchor_pkg.split(".") if anchor_pkg else []
        if level > 1:
            if level - 1 > len(parts):
                return None
            base = ".".join(parts[: len(parts) - (level - 1)])
        else:
            base = anchor_pkg
        target = f"{base}.{module}" if base and module else base

    def normalize(candidate: str) -> str:
        return candidate[: -len(".__init__")] if candidate.endswith(".__init__") else candidate

    target = normalize(target)
    if target in MODULE_LAYER:
        return target
    while target and target not in MODULE_LAYER:
        target = target.rpartition(".")[0]
    return target or None


def _collect_edges() -> dict[str, set[str]]:
    """解析包内全部 .py，返回 {模块: 它 import 到的内部模块集合}。"""
    edges: dict[str, set[str]] = defaultdict(set)
    files = sorted(PACKAGE_ROOT.rglob("*.py"))
    assert files, f"在 {PACKAGE_ROOT} 下没有找到任何 .py 文件"
    for path in files:
        source = path.read_text(encoding="utf-8")
        module = _dotted(path)
        tree = ast.parse(source, str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                targets: list[str | None] = [node.module]
                targets += [
                    f"{node.module}.{alias.name}" if node.module else alias.name
                    for alias in node.names
                ]
                for raw in targets:
                    found = _resolve(_anchor(module, path.name == "__init__.py"), node.level, raw)
                    if found and found != module:
                        edges[module].add(found)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    found = _resolve("", 0, alias.name)
                    if found and found != module:
                        edges[module].add(found)
    return dict(edges)


def _all_modules() -> set[str]:
    return {_dotted(p) for p in PACKAGE_ROOT.rglob("*.py")}


def test_layer_table_covers_every_module() -> None:
    """层表必须覆盖包内每个模块，否则新增文件可以静默绕过本守卫。"""
    present = _all_modules()
    unknown = sorted(present - set(MODULE_LAYER))
    untracked = sorted(set(MODULE_LAYER) - present)
    assert not unknown, f"以下模块没有层归属，请补进 MODULE_LAYER：{unknown}"
    assert not untracked, f"MODULE_LAYER 里的模块已不存在，请清理：{untracked}"


def _edges_by_layer(edges: dict[str, set[str]]) -> list[tuple[str, str, str, str]]:
    """把 import 边展开成 (源, 目标, 源层, 目标层) 四元组，便于按层判定。"""
    return [
        (src, dst, MODULE_LAYER[src], MODULE_LAYER[dst])
        for src, targets in edges.items()
        for dst in targets
        if src in MODULE_LAYER and dst in MODULE_LAYER
    ]


def _upward(rows: list[tuple[str, str, str, str]]) -> list[tuple[str, str, str, str]]:
    return [r for r in rows if LAYER_RANK[r[3]] > LAYER_RANK[r[2]]]


def _sibling(rows: list[tuple[str, str, str, str]]) -> list[tuple[str, str, str, str]]:
    return [r for r in rows if r[2] != r[3] and LAYER_RANK[r[2]] == LAYER_RANK[r[3]]]


def _render(rows: list[tuple[str, str, str, str]]) -> str:
    return "; ".join(f"{s}({sl}) → {d}({dl})" for s, d, sl, dl in sorted(rows))


def test_import_graph_is_acyclic() -> None:
    """断言①：包 import 图无环（DFS 三色标记找回边）。"""
    edges = _collect_edges()
    color: dict[str, int] = dict.fromkeys(MODULE_LAYER, 0)  # 0 white / 1 grey / 2 black
    stack: list[str] = []
    cycles: list[list[str]] = []

    def visit(node: str) -> None:
        color[node] = 1
        stack.append(node)
        for nxt in sorted(edges.get(node, set())):
            if color[nxt] == 1:
                cycles.append([*stack[stack.index(nxt) :], nxt])
            elif color[nxt] == 0:
                visit(nxt)
        stack.pop()
        color[node] = 2

    for module in sorted(MODULE_LAYER):
        if color[module] == 0:
            visit(module)
    assert not cycles, f"import 图出现环：{cycles}"


def test_no_upward_layer_import() -> None:
    """断言②：任何 import 都不得指向更高层。"""
    rows = _edges_by_layer(_collect_edges())
    violations = _upward(rows)
    assert not violations, f"以下 import 指向更高层（低层不得依赖高层）：{_render(violations)}"


def test_sibling_layers_are_independent() -> None:
    """断言③：同一层序的兄弟层之间不得互相依赖。

    `data` 与 `coordinate`、`render` 与 `adapter` 各占同一级。它们一旦互相引用，
    "按层推理改动影响面"就失效了，尽管 import 图仍然无环、也没有向上边。
    """
    rows = _edges_by_layer(_collect_edges())
    violations = _sibling(rows)
    assert not violations, f"兄弟层之间出现耦合：{_render(violations)}"


@pytest.mark.parametrize("layer", sorted(LAYER_RANK))
def test_every_layer_has_at_least_one_module(layer: str) -> None:
    """每一层都必须真实存在，防止层表被悄悄改空而让断言②③退化为永真。"""
    members = sorted(m for m, lay in MODULE_LAYER.items() if lay == layer)
    assert members, f"层 {layer!r} 在层表里没有任何模块"


# ---------------------------------------------------------------------------
# 守卫自检：证明断言②③真的会红，而不是恒真的摆设
#
# 在真实包里注入逆边证明不了这一点：一条 foundation → data 的向上 import 会先造成
# 运行时的循环 import，pytest 在加载 conftest 阶段就 ImportError 退出，断言②根本没
# 机会执行。因此这里用合成边集直接驱动判定函数，把每条规则各自练一次红。
# ---------------------------------------------------------------------------


def test_guard_itself_detects_an_upward_edge() -> None:
    """合成一条 data → render 的向上边：断言②必须报告它。"""
    synthetic = {"geophylo.data.builtin": {"geophylo.render.linear"}}
    rows = _edges_by_layer(synthetic)
    assert len(rows) == 1
    violations = _upward(rows)
    assert len(violations) == 1, f"向上边未被断言②捕获：{rows}"
    assert violations[0][2:] == ("data", "render")
    assert _sibling(rows) == [], "同一条边不该同时被判为兄弟层耦合"


def test_guard_itself_detects_a_sibling_edge() -> None:
    """合成一条 data → coordinate 的同秩跨层边：断言③必须报告它，断言②不该误报。"""
    synthetic = {"geophylo.data.builtin": {"geophylo.coordinate.transform"}}
    rows = _edges_by_layer(synthetic)
    assert _upward(rows) == [], "同秩边不该被判为向上依赖"
    violations = _sibling(rows)
    assert len(violations) == 1, f"兄弟层耦合未被断言③捕获：{rows}"
    assert violations[0][2:] == ("data", "coordinate")


def test_guard_itself_accepts_a_downward_edge() -> None:
    """合成一条合法向下边：两条规则都必须沉默，否则守卫会误伤正常代码。"""
    synthetic = {"geophylo.render.linear": {"geophylo.exceptions", "geophylo.data.models"}}
    rows = _edges_by_layer(synthetic)
    assert _upward(rows) == []
    assert _sibling(rows) == []

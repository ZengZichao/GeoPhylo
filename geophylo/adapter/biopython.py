"""Bio.Phylo 适配器：坐标契约构造器（规范 4.10/6.1）。

适配器的职责是**构造并校验坐标契约**，不是绘制（ADR-4）。
``spec_from_biophylo()`` 恒定产出 ``mode="root_distance"`` 的 ``CoordinateSpec``：
Bio.Phylo 的 ``Phylo.draw()`` 数据坐标是到根的累积 branch length，只有
root_distance 模式与宿主坐标几何对齐；``absolute_age`` 在此坐标系下会静默错位，
因此本适配器不提供该模式。

ADR-4 记录见 ``docs/adr/ADR-4-adapters-build-contracts.md``。
"""

from __future__ import annotations

import math
import warnings
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, Literal

from ..coordinate.radial import RadialSpec
from ..coordinate.spec import CoordinateSpec
from ..exceptions import CoordinateError
from ..validation import (
    require_linear_numeric_axes,
    require_time_axis,
    resolve_age_conversion,
)

if TYPE_CHECKING:  # pragma: no cover
    from matplotlib.axes import Axes

__all__ = ["radial_spec_from_biophylo", "spec_from_biophylo"]


def _import_phylo():
    try:
        from Bio import Phylo
    except ImportError as exc:  # pragma: no cover - 可选依赖缺失
        raise ImportError(
            "Bio.Phylo 适配需要可选依赖 biopython；请安装 geophylo[biopython]"
        ) from exc
    return Phylo


def _resolve_age_conversion(
    age_conversion: float | Callable[[float], float],
) -> Callable[[float], float]:
    """``age_conversion`` 必填：每个 branch length 单位对应的 Ma 数或换算函数。

    实现委托给 :func:`geophylo.validation.resolve_age_conversion`：两个
    适配器共用同一份解析逻辑与同一套早失败探测。
    """
    return resolve_age_conversion(age_conversion)


def _require_positive_span(max_distance: float, *, tree: Any, root: float) -> None:
    """退化树显式诊断：``max_distance == 0`` 时报出真实成因。

    否则 ``age_range=(root, root)`` 会下渗到 :class:`CoordinateSpec` 的
    ``min < max`` 检查，用户只能看到"要求 age_range 满足 min < max"这一与成因
    脱节的报错。合法成因只有两种：只有一个叶（无从累积距离），或所有参与换算
    的 branch length 之和为 0。
    """
    if max_distance > 0:
        return
    leaves = tree.get_terminals()
    lengths = [c.branch_length for c in tree.find_clades() if c is not tree.root]
    raise CoordinateError(
        f"树的最大根距离为 {max_distance!r}（root_age={root!r}）：年龄窗口退化为一个点，"
        "无法建立坐标语义。真实成因：树只有 "
        f"{len(leaves)} 个叶（tip_count={len(leaves)}），或参与换算的 branch length "
        f"全部为 0（{sorted({repr(v) for v in lengths})}）。"
        "单叶树请改用带真实分支长度的树；全零 branch length 请核对时间校准结果"
    )


def _node_label(clade) -> str:
    return clade.name if clade.name else f"<非命名 {type(clade).__name__}>"


def _scan_tree(
    tree: Any,
) -> tuple[bool, dict[int, object], dict[int, float]]:
    """单次先序遍历完成 branch length 校验与父索引。

    返回 ``(是否等深回退, id→父, id→branch length)``。

    - 全部 branch length **缺失（None）** → Bio.Phylo 的等深回退
      （unit-depth fallback），由调用方决定是否容忍；
    - NaN、负值或非数值无论占比多少都是数据错误，直接 ``CoordinateError``
      并列出问题节点（等深回退只指「缺失」，不包括非法数值）；
    - 根 branch_length 非 None 且非零 → ``CoordinateError``（4.10）。
    """
    root_bl = tree.root.branch_length
    if root_bl is not None:
        try:
            root_value = float(root_bl)
        except (TypeError, ValueError) as exc:
            raise CoordinateError(
                f"根节点的 branch_length 不是数值（{root_bl!r}），无法确定时间语义"
            ) from exc
        if root_value != 0.0:
            raise CoordinateError(
                f"根节点的 branch_length={root_bl!r} 非零：Phylo.draw() 与 tree.distance() 会把"
                "根的 branch_length 计入路径，平移「根距离 ↔ 年龄」的对应。两条修复路径："
                "（1）在树对象上将其清零或置 None；"
                "（2）在后续距离计算中显式扣除该值（如环形配方的 root_offset）。"
                "本适配器不允许静默包含，也不允许静默丢弃"
            )

    parents: dict[int, object] = {}
    lengths: dict[int, float] = {}
    problems: list[str] = []
    missing = 0
    invalid = 0
    total = 0
    stack: list[tuple[Any, Any]] = [(tree.root, None)]
    while stack:
        clade, parent = stack.pop()
        if clade is not tree.root:
            total += 1
            if parent is not None:
                parents[id(clade)] = parent
            bl = clade.branch_length
            if bl is None:
                missing += 1
                problems.append(f"{_node_label(clade)}: branch_length 缺失（None）")
            else:
                try:
                    value = float(bl)
                except (TypeError, ValueError) as exc:
                    problems.append(
                        f"{_node_label(clade)}: branch_length 不是数值（{bl!r}；{exc}）"
                    )
                    invalid += 1
                else:
                    if not math.isfinite(value) or value < 0:
                        problems.append(
                            f"{_node_label(clade)}: branch_length 非有限或为负（{bl!r}）"
                        )
                        invalid += 1
                    else:
                        lengths[id(clade)] = value
        for child in clade.clades:
            stack.append((child, clade))

    unit_depth = total > 0 and missing == total and invalid == 0
    if not unit_depth and problems:
        raise CoordinateError(
            "branch length 校验失败（存在缺失、None、NaN 或负值，无法确定时间语义）；"
            "问题节点：\n  - " + "\n  - ".join(problems)
        )
    return unit_depth, parents, lengths


def _accumulate(
    tree: Any, parents: dict[int, object], ma_lengths: dict[int, float]
) -> tuple[dict[int, float], float]:
    """自根向叶累积根距离（根为 0）；返回 ``(id→根距离, 最大根距离)``。"""
    distances: dict[int, float] = {id(tree.root): 0.0}
    max_distance = 0.0
    stack: list[Any] = list(tree.root.clades)
    while stack:
        clade = stack.pop()
        value = distances[id(parents[id(clade)])] + ma_lengths.get(id(clade), 0.0)
        distances[id(clade)] = value
        max_distance = max(max_distance, value)
        stack.extend(clade.clades)
    return distances, max_distance


def _checked_root_and_lengths(tree: Any, *, allow_unit_depth: bool):
    """校验根基线与 branch length；等深回退按需容忍（附「非时间单位」警告）。"""
    unit_depth, parents, lengths = _scan_tree(tree)
    if unit_depth:
        if not allow_unit_depth:
            raise CoordinateError(
                "检测到 Bio.Phylo 的等深回退（unit-depth fallback）：全部 branch length "
                "缺失，数据坐标不含时间信息。如确认仍要继续，请显式传 "
                "allow_unit_depth=True（此时每条分支按长度 1 处理，且需要自行声明"
                "age_conversion 的「非时间单位」性质）"
            )
        warnings.warn(
            "branch length 全部缺失：等深回退的分支长度是拓扑深度（每条为 1），"
            "不是时间单位；由此得到的「根距离 ↔ 年龄」换算没有时间学意义。",
            UserWarning,
            stacklevel=3,
        )
        lengths = {}
        parents = {}
        stack: list[tuple[Any, Any]] = [(tree.root, None)]
        while stack:
            clade, parent = stack.pop()
            if clade is not tree.root:
                parents[id(clade)] = parent
                lengths[id(clade)] = 1.0
            for child in clade.clades:
                stack.append((child, clade))
    return parents, lengths


def spec_from_biophylo(
    tree,
    ax: Axes,
    *,
    time_axis: Literal["x", "y"],
    age_conversion: float | Callable[[float], float],
    root_age: float,
    allow_unit_depth: bool = False,
) -> CoordinateSpec:
    """从 Bio.Phylo 树构造并校验 ``mode="root_distance"`` 的 ``CoordinateSpec``。

    - 恒定产出 ``mode="root_distance"``（6.1 的坐标对齐论证）；
    - ``age_range`` 由 branch length 的实际数据域推导，**不是** view limits
      （Bio.Phylo 会把 xlim 设为约 ``[-0.05 * xmax, 1.25 * xmax]``）；
    - ``ax`` 只用于校验数值线性轴与几何对齐，不作为时间语义的证据；
    - ``max_distance == 0``（单叶树或全零 branch length）被显式拒绝并给出成因，
      而不是下渗为「age_range 要求 min < max」。

    **本适配器不检查超度量性，也不检查叶年龄，这是设计特性而非疏漏**：

    * 灭绝类群（本库的主要应用场景）的叶**本应**落在各自的地层年龄上，
      即 diachronous tips 是正常情形；强制超度量会把这类图判成错误；
    * 代价是坐标语义完全由调用方对 ``age_conversion`` / ``root_age`` 的声明
      负责：若树的 branch length 单位是 substitutions/site 之类的**非时间**
      代换数，而 ``age_conversion`` 给了 ``1.0``，得到的是一张时间上无意义的
      图（``1.0`` 只在 branch length 已经是 Ma 时正确）。此时请给出真实的
      换算率或换算函数，或在时间校准后重绘。
    """
    _import_phylo()
    require_time_axis(time_axis)
    if (
        isinstance(root_age, bool)
        or not isinstance(root_age, (int, float))
        or not math.isfinite(float(root_age))
        or float(root_age) < 0
    ):
        raise CoordinateError(f"root_age 必须是非负有限数值，得到 {root_age!r}")
    convert = _resolve_age_conversion(age_conversion)
    require_linear_numeric_axes(ax)

    parents, lengths = _checked_root_and_lengths(tree, allow_unit_depth=allow_unit_depth)
    ma_lengths: dict[int, float] = {}
    for clade_id, value in lengths.items():
        ma = convert(value)
        if not math.isfinite(ma) or ma < 0:
            raise CoordinateError(
                f"age_conversion 产生了非法的 Ma 长度 {ma!r}（节点 id={clade_id}）；"
                "换算结果必须非负且有限"
            )
        ma_lengths[clade_id] = ma

    _distances, max_distance = _accumulate(tree, parents, ma_lengths)
    root = float(root_age)
    _require_positive_span(max_distance, tree=tree, root=root)
    min_age = root - max_distance
    if min_age < 0:
        raise CoordinateError(
            f"tree 的最大根距离按 age_conversion 换算后为 {max_distance!r} Ma，"
            f"超过 root_age={root}；最老的叶将早于 0 Ma，坐标语义不成立。"
            "请核对 root_age 或 age_conversion"
        )
    return CoordinateSpec.root_distance(
        time_axis=time_axis, age_range=(min_age, root), root_age=root
    )


def radial_spec_from_biophylo(
    tree: Any,
    *,
    age_conversion: float | Callable[[float], float],
    root_age: float,
    r_inner: float,
    r_outer: float,
    theta_range: tuple[float, float],
    allow_unit_depth: bool = False,
) -> RadialSpec:
    """从 Bio.Phylo 树构造 ``RadialSpec``（实验性）。

    与线性侧共享同一套 branch length 校验；``r_inner``/``r_outer`` 是用户为树
    选定的半径范围（绘制决策而非数据属性），必须显式给出。由此得到的
    ``RadialSpec`` 同时是画树与画环的唯一半径来源（4.9 一致性契约）。
    """
    _import_phylo()
    if (
        isinstance(root_age, bool)
        or not isinstance(root_age, (int, float))
        or not math.isfinite(float(root_age))
        or float(root_age) < 0
    ):
        raise CoordinateError(f"root_age 必须是非负有限数值，得到 {root_age!r}")
    convert = _resolve_age_conversion(age_conversion)
    parents, lengths = _checked_root_and_lengths(tree, allow_unit_depth=allow_unit_depth)
    ma_lengths: dict[int, float] = {}
    for clade_id, value in lengths.items():
        ma = convert(value)
        if not math.isfinite(ma) or ma < 0:
            raise CoordinateError(f"age_conversion 产生了非法的 Ma 长度 {ma!r}")
        ma_lengths[clade_id] = ma
    _distances, max_distance = _accumulate(tree, parents, ma_lengths)
    root = float(root_age)
    _require_positive_span(max_distance, tree=tree, root=root)
    min_age = root - max_distance
    if min_age < 0:
        raise CoordinateError(
            f"tree 的最大根距离按 age_conversion 换算后为 {max_distance!r} Ma，"
            f"超过 root_age={root}；最老的叶将早于 0 Ma"
        )
    return RadialSpec(
        age_range=(min_age, root),
        radius_range=(float(r_inner), float(r_outer)),
        theta_range=theta_range,
        root_age=root,
    )

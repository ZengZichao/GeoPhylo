"""环形树配方 + 极坐标地质时间环（规范 6.3，实验性）。

本库不画树（1.3）：树由用户按本配方绘制，树与时间环必须共用同一个
``RadialSpec`` 实例（4.9 一致性契约），否则会出现静默错位。

演示数值取自三叠纪—侏罗纪鱼龙形类的常见地层年龄：根 245.0 Ma，四个属分别
"灭绝"于 225.0 / 230.0 / 196.0 / 155.0 Ma。叶年龄互不相同是**有意为之**：
灭绝类群的叶本就落在各自的地层年龄上（diachronous tips），本库不要求树是
超度量的。数值为合成演示，不代表发表过的时间校准结果。
"""

from __future__ import annotations

from io import StringIO
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
from Bio import Phylo

from geophylo import add_geo_ring
from geophylo.adapter import radial_spec_from_biophylo

# 根节点 branch_length 必须为空（4.10）：distance() 会把根基线计入路径。
# branch length 单位为 Ma，叶处即各自的地层年龄（见模块 docstring）。
NEWICK = """
((Nothosaurus:10.0, Placodus:5.0):10.0,
 (Ichthyosaurus:19.0, Ophthalmosaurus:60.0):30.0);
"""

OUT = Path(__file__).parent / "_output_circular_tree.png"


def main() -> None:
    tree = Phylo.read(StringIO(NEWICK), "newick")

    fig = plt.figure(figsize=(8, 8))
    ax = fig.add_subplot(111, projection="polar")  # 必须是原生极坐标 Axes

    # 1) 先建立唯一的半径↔年龄契约；树与环都从它取值
    # 注意：age_conversion 必须与 tree.distance() 的 branch length 单位一致，
    # 否则 age_range 会随单位缩放静默错位。
    radial = radial_spec_from_biophylo(
        tree,
        age_conversion=1.0,  # branch length 已是 Ma，无需换算
        root_age=245.0,
        r_inner=0.0,
        r_outer=1.0,
        theta_range=(0.0, np.pi / 2),  # 本图只画四分之一圆
    )

    # 2) 角的分配：叶均分整个角域（含两端端点），内部节点取其子节点的角度均值
    theta_0, theta_1 = radial.theta_range
    leaves = tree.get_terminals()
    if len(leaves) <= 1:
        # 单叶树：角域均分会除零，退化为放在角域中点
        theta = {id(leaf): (theta_0 + theta_1) / 2.0 for leaf in leaves}
    else:
        theta = {
            id(leaf): theta_0 + (theta_1 - theta_0) * i / (len(leaves) - 1)
            for i, leaf in enumerate(leaves)
        }
    # 根基线必须为 0/None（radial_spec_from_biophylo 与 4.10 一致地强制），
    # 因此 tree.distance() 就是"到根的累积 Ma 距离"，无需任何显式扣除。
    assert tree.root.branch_length in (None, 0.0), (
        f"根 branch_length={tree.root.branch_length!r} 非零：适配器应当已经拒绝过它"
    )
    radius = {}
    for clade in tree.find_clades(order="postorder"):  # 自叶向根
        age = radial.root_age - tree.distance(clade)  # 根距离 → 年龄
        radius[id(clade)] = radial.age_to_radius(age)  # 唯一的半径映射
        if clade.clades:
            theta[id(clade)] = float(np.mean([theta[id(c)] for c in clade.clades]))

    # 3) 画树：半径来自 radial，角度来自上面的分配
    for clade in tree.find_clades():
        for child in clade.clades:
            ax.plot(
                [theta[id(clade)], theta[id(child)]],
                [radius[id(clade)], radius[id(child)]],
                color="black",
                lw=0.8,
                solid_capstyle="round",
            )
    ax.set_axis_off()

    # 4) 时间环：同一个 radial 实例，因此与树同心、年龄逐点对齐。
    # band=(0.92, 1.0) 表示环段占据轨道最外 8% 的径向区间：绘制窗口
    # [155, 245] Ma 被映射进这条环带（max_age → 0.92、min_age → 1.0）。
    add_geo_ring(ax, spec=radial, rank="Period", band=(0.92, 1.0))
    fig.savefig(OUT, dpi=300)
    print(f"saved {OUT}")


if __name__ == "__main__":
    main()

"""Bio.Phylo 时间校准树 + 线性地质时间轴（稳定 API 路径的端到端示例）。

推荐顺序（规范 5.4）::

    add_geo_axis() -> tight_layout() -> result.finalize() -> savefig()

演示数值取自三叠纪—侏罗纪鱼龙形类的常见地层年龄（根 245.0 Ma；四个属分别
"灭绝"于 225.0 / 230.0 / 196.0 / 155.0 Ma），数值为合成演示，不代表发表过的
时间校准结果。叶年龄互不相同是有意为之：灭绝类群的叶本就落在各自的地层年龄
上（diachronous tips），本库不要求、也不检查树的超度量性。
"""

from __future__ import annotations

from io import StringIO
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
from Bio import Phylo

from geophylo import add_geo_axis, spec_from_biophylo

# 合成时间校准树：branch length 单位为 Ma（真实研究中由外部时间校准给出），
# 根年龄 245.0 Ma 仅作演示，实际数值必须来自已发表的时间校准结果。
# 根节点 branch_length 必须为空（4.10）：Bio.Phylo 会把根基线计入路径。
NEWICK = """
((Nothosaurus:10.0, Placodus:5.0):10.0,
 (Ichthyosaurus:19.0, Ophthalmosaurus:60.0):30.0);
"""

OUT = Path(__file__).parent / "_output_bio_phylo_timetree.png"


def main() -> None:
    tree = Phylo.read(StringIO(NEWICK), "newick")

    fig, ax = plt.subplots(figsize=(12, 8))
    Phylo.draw(tree, axes=ax, do_show=False)  # do_show=False 必须显式给出

    # root_age 来自外部时间校准结果，不能从 root.branch_length 推断；
    # age_conversion 声明 branch length 单位到 Ma 的换算（本树恰为 1）。
    spec = spec_from_biophylo(
        tree,
        ax,
        time_axis="x",
        age_conversion=1.0,
        root_age=245.0,
    )

    result = add_geo_axis(
        ax,
        spec=spec,
        position="bottom",
        ranks=["Period", "Epoch"],
        tick_style="boundaries",
    )
    plt.tight_layout()
    result.finalize()
    fig.savefig(OUT, dpi=300, bbox_inches="tight")
    print(f"saved {OUT}")


if __name__ == "__main__":
    main()

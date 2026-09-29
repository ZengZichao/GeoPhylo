"""iplotx 时间校准树 + 线性地质时间轴（规范 6.2，实验性；需要 iplotx）。

运行前安装可选依赖::

    pip install geophylo[iplotx] ete4

演示树与数值同 ``bio_phylo_timetree.py``：根 245.0 Ma、四个属各自落在三叠纪—
侏罗纪的地层年龄上（叶年龄不同是灭绝类群的正常情形，本库不要求超度量）。
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import iplotx as ipx
import matplotlib.pyplot as plt
from ete4 import Tree

from geophylo import add_geo_axis
from geophylo.adapter import spec_from_iplotx

NEWICK = "((Nothosaurus:10.0, Placodus:5.0):10.0, (Ichthyosaurus:19.0, Ophthalmosaurus:60.0):30.0);"

OUT = Path(__file__).parent / "_output_iplotx_timetree.png"


def main() -> None:
    # ete4 直接接受 Newick 字符串；不要传 StringIO（其解析器从 data.name
    # 猜测格式，StringIO 没有 name 属性会报 AttributeError）。
    t = Tree(NEWICK)

    fig, ax = plt.subplots(figsize=(10, 6))
    artist = ipx.tree(t, layout="horizontal", ax=ax, show=False)  # 返回 TreeArtist

    spec = spec_from_iplotx(artist, time_axis="x", age_conversion=1.0, root_age=245.0)
    result = add_geo_axis(ax, spec=spec, position="bottom", ranks=["Period", "Epoch"])
    plt.tight_layout()  # 规范调用顺序：add_geo_axis -> tight_layout -> finalize
    result.finalize()
    fig.savefig(OUT, dpi=300)
    print(f"saved {OUT}")


if __name__ == "__main__":
    main()

"""地层柱风格的地质时间轴示例：不依赖任何树库的通用 Matplotlib 用法。

演示 ``CoordinateSpec.absolute()`` 显式声明坐标语义（时间沿 x、越老越靠左）
与多秩堆叠轨道；不依赖任何树库。
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np

from geophylo import (
    CoordinateSpec,
    add_geo_axis,
)

OUT = Path(__file__).parent / "_output_stratigraphic_column.png"


def main() -> None:
    window_min, window_max = 0.0, 300.0

    rng = np.random.default_rng(42)
    ages = np.linspace(window_min + 2, window_max - 2, 80)
    values = 60 + 25 * np.sin(ages / 25.0) + rng.normal(0, 3, ages.size)

    fig, ax = plt.subplots(figsize=(12, 6))
    ax.plot(ages, values, color="0.2", lw=0.8)
    ax.fill_between(ages, 0, values, color="0.85")
    ax.set_xlim(window_max, window_min)  # 越老越靠左（时间向右年轻化）
    ax.set_ylim(0, 100)
    ax.set_xlabel("Age (Ma)")
    ax.set_ylabel("Relative sea level (m)")

    # 坐标语义显式声明：绝对年龄、时间沿 x、合法域覆盖绘制窗口。
    spec = CoordinateSpec.absolute(time_axis="x", age_range=(window_min, window_max))

    result = add_geo_axis(
        ax,
        spec=spec,
        position="bottom",
        ranks=["Period", "Epoch"],
        tick_style="ages",
    )
    plt.tight_layout()
    result.finalize()
    fig.savefig(OUT, dpi=300)
    print(f"saved {OUT}")


if __name__ == "__main__":
    main()

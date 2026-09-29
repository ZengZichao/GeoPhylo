"""视觉基准与逐区域结构断言（开发文档 7.5）。

两层防护，缺一不可：

1. **像素层**（``@pytest.mark.mpl_image_compare``）：只有加 ``--mpl`` 才真正做像素
   比较，所以 CI 的门禁命令带着 ``--mpl``。``tolerance=0``：基准图由
   ``python3 tests/update_baselines.py`` 在与 CI 相同的环境里生成并纳入版本管理，
   任何像素差异都是回归。实测 ``tolerance=6`` 下"一整个刻度标签消失"的 RMS 只有
   4.51、"一条网格线消失"1.86，全都判通过——非零容差挡不住丢标签。
2. **结构层**（本文件其余测试，任何 job 都跑，不依赖 ``--mpl``）：把成图上真正
   重要的量——每条色带的左右边界年龄、填充色、轨道堆叠顺序、刻度是否被抽稀、
   标签是否被静默丢弃——与**数据层**（``Timescale`` + ``spec`` 的解析映射）逐项
   对照。字体/字距差异会让像素层在别的 OS 上变红，结构层跨平台稳定，因此它是
   "色带画错 / 标签丢失"的第一道防线。

基准图缺失时 ``test_every_visual_test_has_a_baseline_image`` 直接失败：删掉
``tests/baseline_images/*.png`` 不可能让 CI 变绿（负向控制点）。
"""

from __future__ import annotations

import ast
from io import StringIO
from pathlib import Path

import matplotlib
import matplotlib.colors
import matplotlib.pyplot as plt
import matplotlib.text
import pytest
from Bio import Phylo

from geophylo import CoordinateSpec, Timescale, add_geo_axis
from geophylo.adapter import spec_from_biophylo
from geophylo.render.result import GeoAxisResult

NEWICK = "((A:41.0, B:41.0):22.0, (C:35.0, D:35.0):28.0);"
BASELINE_DIR = Path(__file__).resolve().parent / "baseline_images"
RANKS = ("Period", "Epoch")
# 宽度低于该像素值的色带放不下任何标签：基准图里最窄的"必须有标签"色带是全新世
# 之外的 Q1（≈ 8.5 px），而全新世 0.0117 Ma ≈ 0.04 px。1 px 的分界两侧都留有余量。
MIN_LABELABLE_PX = 1.0
COORD_TOL = 1e-6


def _timetree_figure() -> tuple[plt.Figure, GeoAxisResult]:
    tree = Phylo.read(StringIO(NEWICK), "newick")
    fig, ax = plt.subplots(figsize=(12, 8))
    Phylo.draw(tree, axes=ax, do_show=False)
    spec = spec_from_biophylo(tree, ax, time_axis="x", age_conversion=1.0, root_age=63.0)
    result = add_geo_axis(
        ax, spec=spec, position="bottom", ranks=list(RANKS), tick_style="boundaries"
    )
    result.finalize()
    return fig, result


def _column_figure() -> tuple[plt.Figure, GeoAxisResult]:
    fig, ax = plt.subplots(figsize=(12, 6))
    ax.plot([0, 100, 200, 300], [1, 2, 1.5, 3])
    ax.set_xlim(300, 0)
    spec = CoordinateSpec.absolute(time_axis="x", age_range=(0.0, 300.0))
    result = add_geo_axis(ax, spec=spec, position="bottom", ranks=list(RANKS), tick_style="ages")
    result.finalize()
    return fig, result


_FIXTURES = [
    pytest.param(_timetree_figure, id="timetree"),
    pytest.param(_column_figure, id="column"),
]


# ---------------------------------------------------------------------------
# 1) 像素层
# ---------------------------------------------------------------------------


@pytest.mark.visual
@pytest.mark.mpl_image_compare(
    baseline_dir="baseline_images",
    filename="timetree_geo_axis.png",
    style="mpl20",
    tolerance=0,
    savefig_kwargs={"dpi": 100},
)
def test_visual_timetree_geo_axis():
    fig, _result = _timetree_figure()
    return fig


@pytest.mark.visual
@pytest.mark.mpl_image_compare(
    baseline_dir="baseline_images",
    filename="stratigraphic_geo_axis.png",
    style="mpl20",
    tolerance=0,
    savefig_kwargs={"dpi": 100},
)
def test_visual_stratigraphic_geo_axis():
    fig, _result = _column_figure()
    return fig


def _declared_visual_baselines() -> list[tuple[str, Path]]:
    """AST 扫描 tests/ 下全部 mpl_image_compare 装饰器，解析其基准图路径。

    用 AST 而不是导入模块：新增的视觉测试（无论落在哪个文件）都会被覆盖，也不受
    可选依赖缺失导致 importorskip 的影响。
    """
    tests_dir = Path(__file__).resolve().parent
    found: list[tuple[str, Path]] = []
    for module in sorted(tests_dir.glob("test_*.py")):
        tree = ast.parse(module.read_text(encoding="utf-8"), filename=str(module))
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef):
                continue
            for decorator in node.decorator_list:
                func = decorator.func if isinstance(decorator, ast.Call) else decorator
                name = getattr(func, "id", None) or getattr(func, "attr", None)
                if name != "mpl_image_compare":
                    continue
                keywords = {
                    kw.arg: kw.value
                    for kw in (decorator.keywords if isinstance(decorator, ast.Call) else ())
                }

                def _str_kw(key: str, default: str, _kw: dict = keywords) -> str:
                    value = _kw.get(key)
                    if isinstance(value, ast.Constant) and isinstance(value.value, str):
                        return value.value
                    return default

                filename = _str_kw("filename", f"{node.name}.png")
                baseline_dir = _str_kw("baseline_dir", "baseline_images")
                found.append((f"{module.name}::{node.name}", tests_dir / baseline_dir / filename))
    return found


def test_every_visual_test_has_a_baseline_image():
    """基准图必须存在。

    没有 ``--mpl`` 时 pytest-mpl 只执行函数体；基准图被删除或从未生成都会让
    视觉比较静默失效。这条测试不依赖 ``--mpl``，因此任何 job、任何命令下都会红。
    """
    declared = _declared_visual_baselines()
    assert declared, "tests/ 下没有任何 mpl_image_compare 测试——视觉门禁已失效"
    missing = [
        f"  {test} → {path.relative_to(BASELINE_DIR.parent)}"
        for test, path in declared
        if not path.is_file()
    ]
    assert not missing, "缺少视觉基准图，--mpl 像素比较无法执行：\n" + "\n".join(
        f"{item}（用 python3 tests/update_baselines.py 生成）" for item in missing
    )


# ---------------------------------------------------------------------------
# 2) 结构层：与数据层真值逐项对照
# ---------------------------------------------------------------------------


def _hex(color: object) -> str:
    return matplotlib.colors.to_hex(color).lower()  # type: ignore[arg-type]


def _drawn_bands(result: GeoAxisResult) -> list[tuple[float, float, float, float, str]]:
    """(x_left, x_right, y_bottom, height, hex)，取自真实 Rectangle Artist。"""
    out: list[tuple[float, float, float, float, str]] = []
    for artist in result.artists:
        if type(artist).__name__ != "Rectangle":
            continue
        x0, width = float(artist.get_x()), float(artist.get_width())
        out.append(
            (
                min(x0, x0 + width),
                max(x0, x0 + width),
                float(artist.get_y()),
                float(artist.get_height()),
                _hex(artist.get_facecolor()),
            )
        )
    return out


def _clipped_intervals(
    spec: CoordinateSpec, ranks: tuple[str, ...]
) -> list[tuple[str, float, float, str]]:
    """数据层独立算出"该画出什么"：区间 ∩ spec 域（裁剪，非丢弃）。"""
    min_age, max_age = spec.age_range
    rows: list[tuple[str, float, float, str]] = []
    for interval in Timescale().iter_intervals(ranks=list(ranks)):
        older = min(float(interval.older_boundary.age_ma), max_age)
        younger = max(float(interval.younger_boundary.age_ma), min_age)
        if older <= younger:  # 与 spec 域不相交
            continue
        rows.append((interval.rank, older, younger, _hex(interval.color)))
    return rows


def _expected_band_spans(
    spec: CoordinateSpec, ranks: tuple[str, ...]
) -> list[tuple[float, float, str]]:
    rows = []
    for _rank, older, younger, color in _clipped_intervals(spec, ranks):
        lo, hi = sorted((float(spec.age_to_data(older)), float(spec.age_to_data(younger))))
        rows.append((lo, hi, color))
    return sorted(rows)


def _candidate_tick_ages(spec: CoordinateSpec, ranks: tuple[str, ...]) -> set[float]:
    """候选刻度年龄：区间边界 ∩ spec 域，外加被裁剪出来的两个端点。"""
    min_age, max_age = spec.age_range
    ages = {min_age, max_age}
    for interval in Timescale().iter_intervals(ranks=list(ranks)):
        for side in ("older_boundary", "younger_boundary"):
            age = float(getattr(interval, side).age_ma)
            if min_age <= age <= max_age:
                ages.add(age)
    return ages


def _text_artists(result: GeoAxisResult) -> list[matplotlib.text.Text]:
    return [a for a in result.artists if isinstance(a, matplotlib.text.Text)]


def _classify_texts(result: GeoAxisResult) -> tuple[list, list, list]:
    """(区间标签, 刻度标签, 其它文本)——按数据坐标归属，不读渲染层私有属性。"""
    spec = result.spec
    tick_x = {round(float(spec.age_to_data(age)), 9) for age in _candidate_tick_ages(spec, RANKS)}
    bands = _drawn_bands(result)
    labels: list[matplotlib.text.Text] = []
    ticks: list[matplotlib.text.Text] = []
    other: list[matplotlib.text.Text] = []
    for text in _text_artists(result):
        x, y = float(text.get_position()[0]), float(text.get_position()[1])
        if round(x, 9) in tick_x and text.get_text().strip() != "Ma":
            ticks.append(text)
            continue
        if any(
            lo - COORD_TOL <= x <= hi + COORD_TOL
            and top - COORD_TOL <= y <= top + height + COORD_TOL
            for lo, hi, top, height, _color in bands
        ):
            labels.append(text)
            continue
        other.append(text)
    return labels, ticks, other


@pytest.mark.parametrize("builder", _FIXTURES)
def test_band_geometry_and_colors_match_snapshot(builder):
    """逐区域断言：色带边界、裁剪与填充色必须等于快照真值。

    像素容差抓不到的"某条带缺失 / 换色 / 少了一个 rank 轨道"在这里一定会红。
    """
    fig, result = builder()
    try:
        spec, ranks = result.spec, tuple(result.params["ranks"])
        drawn = sorted((lo, hi, color) for lo, hi, _y, _h, color in _drawn_bands(result))
        expected = _expected_band_spans(spec, ranks)
        assert drawn, "没有画出任何色带 patch"
        assert drawn == expected, (
            f"色带与快照真值不一致（{len(drawn)} drawn vs {len(expected)} expected）；"
            f"缺失={sorted(set(expected) - set(drawn))[:4]} 多余={sorted(set(drawn) - set(expected))[:4]}"
        )
        for _lo, _hi, y, height, _color in _drawn_bands(result):
            assert height > 0, "色带高度必须为正（负高度即退化）"
            assert y >= 0.0 and y + height <= 1.0 + COORD_TOL, (y, height)
    finally:
        plt.close(fig)


def test_period_track_sits_above_epoch_track_for_bottom_position():
    """轨道堆叠顺序：position='bottom' 时 Period 带在 Epoch 带之上。"""
    fig, result = _column_figure()
    try:
        spec = result.spec
        bands = _drawn_bands(result)
        rank_of_track: dict[float, str] = {}
        for y in sorted({round(b[2], 6) for b in bands}):
            spans = sorted((lo, hi, color) for lo, hi, yy, _h, color in bands if round(yy, 6) == y)
            for rank in RANKS:
                if spans == _expected_band_spans(spec, (rank,)):
                    rank_of_track[y] = rank
        assert set(rank_of_track.values()) == set(RANKS), (
            f"两条轨道未能按数据层识别：{rank_of_track}"
        )
        assert min(rank_of_track) < max(rank_of_track)  # 两个 rank 分居不同高度带
        assert rank_of_track[min(rank_of_track)] == "Epoch", "Epoch 轨道必须更靠近宿主 Axes"
        assert rank_of_track[max(rank_of_track)] == "Period"
    finally:
        plt.close(fig)


@pytest.mark.parametrize("builder", _FIXTURES)
def test_labels_and_ticks_are_never_silently_dropped(builder):
    """逐区域断言：标签与刻度不得被静默丢弃（一个刻度标签整体消失时 RMS 仅 4.51，
    像素层仍判通过，只有结构层能抓住它）。

    三条不变量：

    - 每个文本 Artist 必须能归属为"区间标签 / 刻度标签 / 单位标签"之一，出现
      无归属文本即说明渲染层与数据层脱钩；
    - 隐藏（``visible=False``）的区间标签数量必须等于 ``result.labels_hidden``；
    - 刻度标签数 + ``result.ticks_dropped`` 必须等于数据层候选年龄数——抽稀必须
      被记账，标签被静默删除同样会被这里抓住。
    """
    fig, result = builder()
    fig.canvas.draw()
    try:
        labels, ticks, other = _classify_texts(result)
        units = [t for t in other if t.get_text().strip() == "Ma"]
        assert len(units) == 1, f"单位标签必须恰好 1 个，实际 {len(units)}"
        assert not [t for t in other if t not in units], (
            f"存在无法归属到色带/刻度/单位的文本：{[t.get_text() for t in other if t not in units]}"
        )
        assert labels, "轨道里没有任何区间标签"
        hidden = [t for t in labels if not t.get_visible()]
        assert len(hidden) == result.labels_hidden, (
            f"隐藏标签 {len(hidden)} 个与 labels_hidden={result.labels_hidden} 不符"
        )
        candidates = _candidate_tick_ages(result.spec, RANKS)
        assert len(ticks) + result.ticks_dropped == len(candidates), (
            f"刻度标签 {len(ticks)} + 已抽稀 {result.ticks_dropped} != 候选边界 {len(candidates)}"
            "（有刻度被静默丢弃？）"
        )
        transform = result.geo_ax.transData.transform
        for lo, hi, _y, _height, _color in _drawn_bands(result):
            left, right = sorted((transform((lo, 0.0))[0], transform((hi, 0.0))[0]))
            if right - left < MIN_LABELABLE_PX:
                continue  # 放不下标签的退化宽度：由 labels_hidden 语义负责
            center = (left + right) / 2.0
            covered = [
                t
                for t in labels
                if t.get_window_extent().x0 - 1.0 <= center <= t.get_window_extent().x1 + 1.0
            ]
            assert covered, f"宽 {right - left:.1f}px 的色带（数据坐标 {lo}-{hi}）没有任何标签"
    finally:
        plt.close(fig)


@pytest.mark.parametrize("builder", _FIXTURES)
def test_unit_label_present_and_not_clipped(builder):
    """'Ma' 单位标签必须可见且完整落在画布内。"""
    fig, result = builder()
    fig.canvas.draw()
    try:
        units = [t for t in _text_artists(result) if t.get_text().strip() == "Ma"]
        assert units, "缺少 'Ma' 单位标签"
        assert all(t.get_visible() for t in units), "'Ma' 单位标签被隐藏"
        width, height = fig.canvas.get_width_height()
        for text in units:
            box = text.get_window_extent()
            assert box.x0 >= 0.0 and box.x1 <= width, (
                f"'Ma' 标签越出画布横向范围：{box.x0}-{box.x1} / {width}"
            )
            assert box.y0 >= 0.0 and box.y1 <= height, (
                f"'Ma' 标签越出画布纵向范围：{box.y0}-{box.y1} / {height}"
            )
    finally:
        plt.close(fig)

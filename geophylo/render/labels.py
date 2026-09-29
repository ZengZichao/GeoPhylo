"""标签测量、缩写、碰撞与降级（规范 5.2/5.4）。

碰撞检测必须基于 renderer 实测文本包围盒，不允许用字符数估算——估算只用于
``add_geo_axis()`` 调用时的粗略布局，精确布局在 ``draw_event`` 回调或
``finalize()`` 中执行。

两条可核验的边界约束：

* **厚度维是硬约束**：候选标签在*该候选旋转角*下实测出的厚度维尺寸不得超过
  ``LabelItem.thickness_px``，因此旋转标签同样不得越过相邻轨道边界；
* **时间维不得越出轨道**：给出 ``time_bounds_px`` 时，标签中心会沿时间维向内
  夹紧，使包围盒整体落在轨道矩形之内；连夹紧都放不下的候选被拒绝。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import matplotlib.colors

if TYPE_CHECKING:  # pragma: no cover
    from geophylo.data.models import Interval

__all__ = [
    "LabelItem",
    "abbreviate_text",
    "apply_label_degradation",
    "auto_label_color",
    "estimate_text_size",
    "is_figure_abbreviation",
    "measure_text_size",
]

# 可作为图面缩写的 ICS 短代码形态：至多两个字母 + 至多两位数字（如 ``J``、
# ``Ep``、``P1``、``T3``、``b6``、``I1``、``ep10``、``MP1``），且必须整段匹配。
_ABBREVIATION_RE = re.compile(r"[A-Za-z]{1,2}[0-9]{0,2}")
# 图面缩写的硬长度上限（与上面的形态共同构成判定，避免"复合编码"混入）。
_MAX_ABBREVIATION_LEN = 4


def is_figure_abbreviation(alias: str) -> bool:
    """判断快照别名能否作为**图面缩写**使用。

    上游 ``skos:notation`` 同时携带两类值：单段短代码（``J``、``P1``、``b6``）
    与 ICS 图表的复合 ``ccgmShortCode``（如 ``C1c1``、``C2c6c7``：把「子统 +
    阶」两级分组编码拼在一起，读者无法从图面上反解）。复合编码不是缩写，
    不得出现在图上，因此这里只接受**单段**、长度受限的形态：

    * 必须是单段：至多两个字母后紧跟至多两位数字，且整串被该形态覆盖；
    * 长度不超过 ``_MAX_ABBREVIATION_LEN``（4）；
    * 空串与非字符串一律拒绝。

    >>> is_figure_abbreviation("T3")
    True
    >>> is_figure_abbreviation("C2c6c7")
    False
    """
    if not isinstance(alias, str):
        return False
    text = alias.strip()
    if not text or len(text) > _MAX_ABBREVIATION_LEN:
        return False
    return _ABBREVIATION_RE.fullmatch(text) is not None


def abbreviate_text(interval) -> str:
    """取区间首个可用作图面缩写的别名（快照 ``aliases``）；无则回退为全名。

    只采用通过 :func:`is_figure_abbreviation` 的别名，因此上游复合
    ``ccgmShortCode``（如 ``C2c6c7``）永远不会被当成图面缩写；此时回退为
    全名（``interval.name``），不做按词长截断——截断会凭空造出读者不认识
    的记号。
    """
    for alias in interval.aliases:
        if is_figure_abbreviation(alias):
            return alias.strip()
    return interval.name


def auto_label_color(fill_color: str, *, alpha: float = 1.0, background: str = "#FFFFFF") -> str:
    """按合成后的背景色选择黑/白标签色（规范 5.4）。

    只对色块自身的颜色求亮度是不够的：半透明色块的实际呈现是色块与 Axes
    背景（或用户背景色）的合成结果。
    """
    fg = matplotlib.colors.to_rgba(fill_color)
    bg = matplotlib.colors.to_rgba(background)
    rgb = [
        alpha * f + (1.0 - alpha) * b for f, b in zip(fg[:3], bg[:3], strict=False)
    ]  # 先做 alpha 合成

    def linearize(c: float) -> float:
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (linearize(float(c)) for c in rgb)
    luminance = 0.2126 * r + 0.7152 * g + 0.0722 * b  # WCAG 相对亮度
    contrast_black = (luminance + 0.05) / 0.05
    contrast_white = 1.05 / (luminance + 0.05)
    return "black" if contrast_black >= contrast_white else "white"


def estimate_text_size(text: str, label_size: float, dpi: float) -> tuple[float, float]:
    """粗略布局用：按字号与字符数估算文本像素尺寸（精确布局必须实测）。"""
    width = 0.62 * label_size * len(text) * dpi / 72.0
    height = 1.25 * label_size * dpi / 72.0
    return (width, height)


def measure_text_size(artist, renderer) -> tuple[float, float]:
    """精确布局用：以 renderer 实测文本包围盒。"""
    extent = artist.get_window_extent(renderer=renderer)
    return (extent.width, extent.height)


@dataclass
class LabelItem:
    """一个候选标签的布局输入与降级状态（供 ``apply_label_degradation`` 消费）。"""

    interval: Interval  # geophylo.data.models.Interval
    artist: Any  # matplotlib.text.Text（已创建，初始隐藏）
    center: tuple[float, float]  # 数据坐标（区间几何锚点，布局期间不被改写）
    length_px: float  # 时间维可用像素长度（区间在窗口内的宽度）
    thickness_px: float  # 带厚方向可用像素
    base_rotation: float  # 标签自然朝向角（含 rotation 偏移），仅用于判断是否处于该朝向
    time_axis_index: int = 0  # 时间维在显示坐标中的下标，由 spec.time_axis 决定
    text: str = ""
    rotation: float = 0.0
    visible: bool = False
    shortened: bool = False
    rotated: bool = False
    size: tuple[float, float] = (0.0, 0.0)
    px_center: tuple[float, float] = (0.0, 0.0)  # 显示坐标（像素），供碰撞比较
    placed_px: tuple[float, float] = (0.0, 0.0)  # 夹紧后实际落位的显示坐标
    final_center: tuple[float, float] = (0.0, 0.0)  # 最终落位的数据坐标（每轮布局重算）
    extra_extent: tuple[float, float] = (0.0, 0.0)  # 旋转后另一维尺寸
    rank_priority: int = 0
    # 供排序的次级键：rank 越核心越优先，同 rank 内越老越优先。
    sort_key: tuple = field(default_factory=tuple)


def _screen_box(rotation: float, size: tuple[float, float]) -> tuple[float, float]:
    """给定旋转角下标签包围盒的 ``(显示 x 尺寸, 显示 y 尺寸)``。

    ``size`` 一律是**未旋转**的 ``(文本长度, 行高)``：``measure()`` 在测量前会把
    artist 的旋转角归零（见 ``linear.py`` 的 ``measure`` 闭包），
    ``estimate_text_size()`` 同样不随旋转变化。
    """
    width, height = size
    if rotation % 180.0 == 0.0:
        return (width, height)
    return (height, width)


def _oriented_box(
    rotation: float, size: tuple[float, float], base_rotation: float
) -> tuple[float, float]:
    """给定候选旋转角下标签包围盒的 ``(时间维尺寸, 厚度维尺寸)``。

    配对取决于候选角**相对轨道朝向**是否平行，而非候选角本身：文本沿时间轴铺开时
    时间维取文本长度、厚度维取行高；垂直于时间轴时两维互换。水平轨道
    （``base_rotation=0``）下本式退化为旧的 ``rotation in (0, 180)`` 判定，
    行为不变；垂直轨道（``base_rotation=90``）下两维不再被转置。
    """
    width, height = size
    if rotation % 180.0 == base_rotation % 180.0:
        return (width, height)
    return (height, width)


def time_axis_index_for(time_axis: str) -> int:
    """时间维在显示坐标中的下标：``"x"`` 轨道为 0，``"y"`` 轨道为 1。

    必须由 ``spec.time_axis`` 决定，**不能**从 ``base_rotation`` 反推：
    ``base_rotation`` 含公共参数 ``rotation`` 的偏移，``rotation=45`` 的水平轨道
    会让任何按旋转角猜朝向的代码把时间维认错，从而把标签夹到错误的分量上。
    """
    return 0 if time_axis == "x" else 1


def _collides(center: tuple[float, float], screen, placed) -> bool:
    """候选包围盒是否与已放置标签相交（两侧均为显示坐标下的 x/y 尺寸）。"""
    cx, cy = center
    for ox, oy, ow, oh in placed:
        if abs(cx - ox) < (screen[0] + ow) / 2.0 and abs(cy - oy) < (screen[1] + oh) / 2.0:
            return True
    return False


def _fits_own_interval(item: LabelItem, box: tuple[float, float]) -> bool:
    """候选是否放得进自己的区间宽度。"""
    along, across = box
    return along <= item.length_px and across <= item.thickness_px


def _clamp_to_track(
    item: LabelItem, box: tuple[float, float], bounds: tuple[float, float] | None
) -> tuple[float, float] | None:
    """把标签中心沿时间维夹进轨道矩形；放不下时返回 ``None``。

    被夹紧的分量按轨道朝向选取：水平轨道夹 x，垂直轨道夹 y。
    """
    center = item.px_center
    if bounds is None:
        return center
    lo_px, hi_px = bounds
    half = box[0] / 2.0
    if box[0] > hi_px - lo_px:
        return None  # 时间维连整个轨道都放不下：任何位置都会越界
    idx = item.time_axis_index
    clamped = list(center)
    clamped[idx] = min(max(center[idx], lo_px + half), hi_px - half)
    return (clamped[0], clamped[1])


def _candidate_sequence(name: str, abbreviated: str, base_rot: float) -> list[tuple[str, float]]:
    """按规范 5.2 的降级顺序生成候选：全名 → 缩写 → 缩写旋转 → 全名旋转。

    缩写与全名同名时省略第二个候选，避免无意义的重复测量。
    """
    perp_rot = 90.0 if base_rot in (0.0, 180.0) else 0.0
    candidates: list[tuple[str, float]] = [(name, base_rot)]
    if abbreviated != name:
        candidates.append((abbreviated, base_rot))
    candidates.append((abbreviated, perp_rot))
    candidates.append((name, perp_rot))
    return candidates


def _measure_at_rotation(
    item: LabelItem, text: str, rotation: float, measure
) -> tuple[float, float]:
    """临时把 ``item.rotation`` 设为候选角再测量，量完立即还原。

    ``measure()`` 按 item 当前旋转角求值，所以候选的实测尺寸必须在候选角下取；
    还原用 try/finally，保证 measure() 抛错时不残留候选角。
    """
    saved = item.rotation
    item.rotation = rotation
    try:
        return measure(item, text)
    finally:
        item.rotation = saved


def _select_candidate(
    item: LabelItem,
    candidates: list[tuple[str, float]],
    measure,
    bounds: tuple[float, float] | None,
    placed,
) -> tuple[str, float, tuple[float, float], tuple[float, float]] | None:
    """按降级顺序挑第一个可放置的候选；全部不可放置时返回 ``None``（→ 隐藏）。

    两条几何约束对**每个候选的旋转角**求值（不是对 ``item.rotation`` 的旧值，
    否则旋转候选会按未旋转方向判定）：

    * 厚度维硬约束：候选包围盒的厚度维尺寸不得大于 ``item.thickness_px``；
    * 时间维边界：给出 ``bounds`` 时夹紧到轨道矩形内，夹紧后仍放不下则拒绝。

    首选（全名原向）额外要求"放得进自己的区间"，空间不足必须走 ①缩写，不得跳步；
    后续候选只要无碰撞即可接受（自身放得下 = 常规；放不下但与已放置的高优先级标签
    无碰撞 = 溢入同一轨道矩形内空白的窄区间处理）。
    """
    for index, (text, rot) in enumerate(candidates):
        size = _measure_at_rotation(item, text, rot, measure)
        # 用候选角而非恢复后的角度；时间/厚度配对相对轨道朝向求值，屏幕尺寸供碰撞比较。
        box = _oriented_box(rot, size, item.base_rotation)
        screen = _screen_box(rot, size)
        if box[1] > item.thickness_px:
            continue  # 厚度维是硬约束：标签不得越过相邻轨道边界
        center = _clamp_to_track(item, box, bounds)
        if center is None:
            continue  # 时间维越出轨道矩形且无法夹紧
        if index == 0:
            # 首选只在自身区间内放得下且无碰撞时接受；夹紧后的位置同样参与判定。
            if _fits_own_interval(item, box) and not _collides(center, screen, placed):
                return (text, rot, size, center)
            continue
        if not _collides(center, screen, placed):
            return (text, rot, size, center)
    return None


def apply_label_degradation(
    items: list[LabelItem],
    *,
    measure,
    abbreviate: bool,
    time_bounds_px: tuple[float, float] | None = None,
) -> tuple[bool, bool, int]:
    """按 5.2 的降级顺序处理标签：① 缩写 ② 旋转 ③ 隐藏。

    ``measure(item, text)`` 返回当前旋转下的实测或估算尺寸。降级不跳步：
    用户显式 ``abbreviate=False`` 时跳过第①步（显式选择优先于自动降级）。

    放置按优先级贪心（rank 越靠核心越优先保留，同 rank 内越老越优先）：
    候选依次为「全名 → 缩写 → 缩写旋转 → 全名旋转」；自身区间宽度放得下优先，
    自身放不下但与已放置的高优先级标签无碰撞时允许溢入相邻**空白**（窄区间的
    常规图面处理）——"相邻空白"指同一轨道矩形内的空白，不是轨道之外的画布：
    给出 ``time_bounds_px`` 时标签中心沿时间维向内夹紧，包围盒始终落在轨道矩形
    之内（规范 5.2 的时间维边界约束）。仍无位置则隐藏。返回
    ``(labels_shortened, labels_rotated, labels_hidden)``。

    两条几何约束对**每个候选的旋转角**求值（不是对 ``item.rotation`` 的旧值，
    否则旋转候选会按未旋转方向判定）：

    * 厚度维硬约束：候选包围盒的厚度维尺寸不得大于 ``item.thickness_px``；
    * 时间维边界：给出 ``time_bounds_px=(lo, hi)``（显示像素，``lo < hi``，
      即轨道矩形在时间维上的范围）时，标签中心沿时间维向内夹紧到
      ``[lo + w/2, hi - w/2]`` 并写入 ``item.placed_px``；夹紧后仍放不下
      （``w > hi - lo``）的候选被拒绝。未给边界时 ``placed_px`` 等于
      ``px_center``，行为与夹紧前一致。

    候选生成与逐候选求值机制见 ``_candidate_sequence`` 与 ``_select_candidate``。
    """
    for item in items:
        item.text = item.interval.name
        item.rotation = item.base_rotation
        item.shortened = False
        item.rotated = False
        item.visible = False
        item.placed_px = item.px_center

    bounds = None
    if time_bounds_px is not None:
        lo_px, hi_px = float(time_bounds_px[0]), float(time_bounds_px[1])
        if not lo_px < hi_px:
            raise ValueError(f"time_bounds_px 须满足 lo < hi，得到 {time_bounds_px!r}")
        bounds = (lo_px, hi_px)

    order = sorted(items, key=lambda item: item.sort_key)
    placed: list[tuple[float, float, float, float]] = []
    hidden = 0
    for item in order:
        name = item.interval.name
        abbreviated = abbreviate_text(item.interval) if abbreviate else name
        base_rot = item.base_rotation
        chosen = _select_candidate(
            item, _candidate_sequence(name, abbreviated, base_rot), measure, bounds, placed
        )
        if chosen is None:
            item.visible = False
            hidden += 1
            continue
        text, rot, size, center = chosen
        item.text = text
        item.rotation = rot
        item.size = size
        item.shortened = text != name
        item.rotated = rot != base_rot
        item.visible = True
        item.placed_px = center
        screen = _screen_box(rot, size)
        placed.append((center[0], center[1], screen[0], screen[1]))

    shortened = any(item.shortened for item in items)
    rotated = any(item.rotated for item in items)
    return shortened, rotated, hidden

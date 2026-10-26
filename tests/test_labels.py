"""标签测量、缩写闸门、碰撞与降级测试（规范 5.2/5.4）。"""

from __future__ import annotations

import matplotlib.colors
import pytest

from geophylo.render.labels import (
    LabelItem,
    abbreviate_text,
    apply_label_degradation,
    auto_label_color,
    estimate_text_size,
    is_figure_abbreviation,
    time_axis_index_for,
)


def make_interval(name, aliases, older, rank="Period"):
    from geophylo.data.models import Boundary, Interval

    return Interval(
        id=f"ics:{rank.lower()}:{name.casefold()}",
        source_iri=None,
        name=name,
        label=name,
        aliases=tuple(aliases),
        rank=rank,
        rank_class="geochronologic",
        parent_id=None,
        source_parent_id=None,
        status="ratified",
        color="#FFFFFF",
        older_boundary=Boundary(older, "constrained", 0.2, "gssp", None),
        younger_boundary=Boundary(older - 1.0, "constrained", 0.2, "numeric_estimate", None),
    )


class TestAutoLabelColor:
    def test_dark_background_gets_white(self):
        assert auto_label_color("#000000") == "white"

    def test_light_background_gets_black(self):
        assert auto_label_color("#FEEBD2") == "black"

    def test_alpha_composition(self):
        # 半透明色块的实际呈现是与背景的合成结果：淡色 + 低 alpha（白底）→ 黑。
        assert auto_label_color("#FDEDEC", alpha=0.5, background="#FFFFFF") == "black"
        # 深色 + 低 alpha 在白底上变浅 → 黑色标签。
        assert auto_label_color("#000000", alpha=0.1, background="#FFFFFF") == "black"

    def test_returns_valid_contrast_color(self):
        # 断言必须落到具体语义：只能返回黑或白，且返回值的灰度与名字一致。只断言
        # ``to_rgba(auto_label_color(...))`` 是恒真的——to_rgba 永远返回非空 4 元组，
        # 黑白判反、返回任意合法颜色都测不出来。
        color = auto_label_color("#34B2C9")
        assert color in ("black", "white"), f"必须返回黑/白对比色，实际 {color!r}"
        rgba = matplotlib.colors.to_rgba(color)
        assert len(rgba) == 4 and rgba[3] == 1.0
        expected_grey = 0.0 if color == "black" else 1.0
        assert rgba[0] == expected_grey and rgba[1] == expected_grey and rgba[2] == expected_grey


class TestAbbreviationGate:
    """只有**单段短代码**能作为图面缩写；上游复合 ``ccgmShortCode`` 回退全名。"""

    @pytest.mark.parametrize("alias", ["J", "P1", "T3", "c7", "ep10", "MP1", "S4", "Q"])
    def test_single_segment_codes_accepted(self, alias):
        assert is_figure_abbreviation(alias) is True
        interval = make_interval("Gzhelian", [alias], 303.0, rank="Age")
        assert abbreviate_text(interval) == alias

    @pytest.mark.parametrize(
        "alias",
        [
            "C2c6c7",  # 上游 ccgmShortCode：子统 + 阶分组编码
            "C1c1",
            "C2c5",
            "Pennsylvanian",
            "Mississippian",
            "",
            "1234",  # 无字母段
            "abc1",  # 三个字母
            "A123",  # 数字超过两位
        ],
    )
    def test_composite_or_overlong_codes_rejected(self, alias):
        assert is_figure_abbreviation(alias) is False
        interval = make_interval("Upper Pennsylvanian", [alias], 300.0, rank="Epoch")
        assert abbreviate_text(interval) == "Upper Pennsylvanian"

    def test_first_usable_alias_wins_after_a_rejected_one(self):
        # 复合编码排在前面也不得被采用：闸门按形态筛选，不按位置取首个。
        interval = make_interval("Upper Pennsylvanian", ["C2c6c7", "u3"], 300.0, rank="Epoch")
        assert abbreviate_text(interval) == "u3"

    def test_no_aliases_falls_back_to_full_name(self):
        interval = make_interval("Asselian", [], 298.9, rank="Age")
        assert abbreviate_text(interval) == "Asselian"

    def test_non_string_alias_is_not_adopted(self):
        # 快照里不该出现，但闸门必须能拒绝（``is_figure_abbreviation`` 不抛异常）。
        assert is_figure_abbreviation(None) is False  # type: ignore[arg-type]
        interval = make_interval("Weird", [None, "W2"], 200.0)  # type: ignore[list-item]
        assert abbreviate_text(interval) == "W2"


class TestDegradation:
    def _items(
        self, lengths, thickness_px, *, base_rotation=0.0, time_axis="x", names=None, aliases=None
    ):
        items = []
        for k, length in enumerate(lengths):
            name = (names or [f"N{k}" for k in range(len(lengths))])[k]
            item_aliases = tuple(aliases) if aliases is not None else (name[:2],)
            interval = make_interval(name, item_aliases, 500.0 - k)
            item = LabelItem(
                interval=interval,
                artist=None,
                center=(0.0, 0.0),
                px_center=(float(k) * 500.0, 0.0),  # 像素中心彼此远离，隔离碰撞
                length_px=length,
                thickness_px=thickness_px,
                base_rotation=base_rotation,
                time_axis_index=time_axis_index_for(time_axis),
                rank_priority={"Period": 2, "Epoch": 3}[interval.rank],
                sort_key=(
                    {"Period": 2, "Epoch": 3}[interval.rank],
                    -interval.older_ma,
                    interval.id,
                ),
            )
            items.append(item)
        return items

    @staticmethod
    def _measure(item, text):
        return estimate_text_size(text, 6.0, 100.0)

    def test_vertical_track_pairs_thickness_against_line_height(self):
        # 规范 5.2 的两条几何约束必须相对**轨道朝向**求值：垂直轨道上处于自然朝向
        # （rotation == base_rotation == 90）的标签，其厚度维占用行高（10.4px）而非
        # 文本长度（67.2px）。轨道厚 20px 时全名应当直接放得下。
        items = self._items(
            [200.0],
            20.0,
            base_rotation=90.0,
            time_axis="y",
            names=["SomethingLong"],
            aliases=("So",),
        )
        shortened, rotated, hidden = apply_label_degradation(
            items, measure=self._measure, abbreviate=True
        )
        assert items[0].visible and items[0].text == "SomethingLong"
        assert items[0].rotation == 90.0
        assert not shortened and not rotated and hidden == 0

    def test_vertical_and_horizontal_tracks_degrade_identically(self):
        # 同一组区间几何，仅轨道朝向不同 → 降级结果必须一致（时间/厚度配对不得转置）。
        lengths, thickness = [30.0, 120.0, 300.0], 20.0
        names, aliases = ["AlphaLongName", "Beta", "Gamma"], ("Al", "Be", "Ga")
        horiz = self._items(lengths, thickness, names=names, aliases=aliases)
        vert = self._items(
            lengths, thickness, base_rotation=90.0, time_axis="y", names=names, aliases=aliases
        )
        for k, item in enumerate(vert):  # 垂直轨道的像素中心沿 y 铺开
            item.px_center = (0.0, float(k) * 500.0)
        apply_label_degradation(horiz, measure=self._measure, abbreviate=True)
        apply_label_degradation(vert, measure=self._measure, abbreviate=True)
        observed = lambda group: [  # noqa: E731
            (i.text, i.visible, i.shortened, i.rotated) for i in group
        ]
        assert observed(horiz) == observed(vert)

    def test_clamp_acts_on_the_time_component(self):
        # 垂直轨道的时间维是 y：夹紧只能改 y，x 必须保持锚点不动。
        items = self._items(
            [10.0], 20.0, base_rotation=90.0, time_axis="y", names=["N"], aliases=("N",)
        )
        items[0].px_center = (7.0, 1000.0)  # 远在轨道矩形 [0, 100] 之外
        apply_label_degradation(
            items, measure=self._measure, abbreviate=True, time_bounds_px=(0.0, 100.0)
        )
        assert items[0].visible
        assert items[0].placed_px[0] == 7.0  # x（厚度维）未被误夹
        assert 0.0 <= items[0].placed_px[1] <= 100.0  # y（时间维）被夹回轨道内

    def test_label_rotation_does_not_choose_the_time_axis(self):
        """公共参数 rotation 是标签自身倾角，不得被当作轨道朝向来猜时间维。

        水平轨道上 rotation=45 会让任何按 base_rotation 反推朝向的实现把时间维认成 y，
        于是越界标签沿错误的分量被夹紧、实际停在轨道外——"同轨不越界"的保证静默失效。
        """
        items = self._items([10.0], 20.0, base_rotation=45.0, names=["N"], aliases=("N",))
        items[0].px_center = (1000.0, 7.0)  # 远在轨道矩形 [0, 100] 之外，且偏在 x 上
        apply_label_degradation(
            items, measure=self._measure, abbreviate=True, time_bounds_px=(0.0, 100.0)
        )
        assert items[0].visible
        assert 0.0 <= items[0].placed_px[0] <= 100.0  # x（时间维）被夹回轨道内
        assert items[0].placed_px[1] == 7.0  # y（厚度维）保持锚点不动

    def test_abbreviation_degrades_first(self):
        # 全名 67px 放不进 30px，缩写 10.3px 可放下。
        items = self._items([30.0], 40.0, names=["SomethingLong"], aliases=("So",))
        shortened, rotated, hidden = apply_label_degradation(
            items, measure=self._measure, abbreviate=True
        )
        assert items[0].visible and items[0].text == "So"
        assert shortened and not rotated and hidden == 0

    def test_explicit_abbreviate_false_skips_step(self):
        # 用户显式 abbreviate=False：跳过第①步（显式选择优先于自动降级）。
        items = self._items([30.0, 200.0], 50.0, names=["LongNameA", "LongNameB"], aliases=("Lo",))
        _shortened, _rotated, hidden = apply_label_degradation(
            items, measure=self._measure, abbreviate=False
        )
        assert items[0].visible and items[0].rotated  # 显式不缩写 → 只能旋转
        assert items[1].visible and not items[1].rotated  # 200px 直接放得下
        assert hidden == 0

    def test_rotation_second_hide_third(self):
        # 空间不足时依次降级：Alpha 放得下；Beta 缩写后放得下；Gamma 自身放
        # 不下但相邻空白无碰撞 → 溢出放置（缩写优先于旋转）。
        items = self._items(
            [60.0, 15.0, 4.0], 40.0, names=["Alpha", "Beta", "Gamma"], aliases=("Al", "Be", "Ga")
        )
        _s, _r, hidden = apply_label_degradation(items, measure=self._measure, abbreviate=True)
        assert hidden == 0
        assert items[0].visible and not items[0].rotated
        assert items[1].visible and items[1].shortened  # 15px 放不下全名 → 缩写
        assert items[2].visible and items[2].shortened

    def test_hide_when_overflow_collides(self):
        # 两个相邻窄区间：高优先级（更老）者溢出放置，低优先级者无位置 → 隐藏。
        items = self._items(
            [4.0, 4.0], 40.0, names=["OlderNarrow", "YoungerNarrow"], aliases=("ON", "YN")
        )
        items[1].px_center = (items[0].px_center[0] + 10.0, 0.0)
        _s, _r, hidden = apply_label_degradation(items, measure=self._measure, abbreviate=True)
        assert hidden == 1
        assert items[0].visible  # 同 rank 内更老者优先
        assert not items[1].visible

    def test_rotation_used_when_thickness_allows(self):
        # 无缩写可用、长度 12px 放不下 41px 的全名 → 旋转（厚度方向 200px 足够）。
        items = self._items([12.0], 200.0, names=["LongName"], aliases=())
        _s, rotated, _h = apply_label_degradation(items, measure=self._measure, abbreviate=True)
        assert rotated and items[0].rotated and items[0].visible

    def test_collision_hides_lower_priority(self):
        # 两个标签像素中心相同：Epoch（优先级低）被隐藏，Period 保留。
        items = [
            LabelItem(
                interval=make_interval("SomePeriod", ["SP"], 300.0, rank="Period"),
                artist=None,
                center=(0, 0),
                px_center=(0.0, 0.0),
                length_px=200.0,
                thickness_px=40.0,
                base_rotation=0.0,
                rank_priority=2,
                sort_key=(2, -300.0, "p"),
            ),
            LabelItem(
                interval=make_interval("NewerEpoch", ["NE"], 200.0, rank="Epoch"),
                artist=None,
                center=(0, 0),
                px_center=(0.0, 0.0),
                length_px=200.0,
                thickness_px=40.0,
                base_rotation=0.0,
                rank_priority=3,
                sort_key=(3, -200.0, "e1"),
            ),
        ]
        _s, _r, hidden = apply_label_degradation(items, measure=self._measure, abbreviate=True)
        assert hidden == 1
        assert items[0].visible  # rank 更核心者保留
        assert not items[1].visible

    # -- 厚度硬约束必须按*候选旋转角*求值 ----------------------------------

    @staticmethod
    def _measure_wide_text(item, text):
        """实测语义：始终返回**未旋转**文本框（``measure()`` 约定），120×10 px。"""
        return (120.0, 10.0)

    def test_rotated_candidate_rejected_when_rotated_thickness_exceeds_band(self):
        # 最小复现：区间带宽 12 px、文本实测 120×10 px —— 旋转后厚度维需要
        # 120 px，必须拒绝。包围盒若按恢复后的 rotation（=0）计算，旋转候选会被判为
        # 可见（实测 visible=True rotation=90.0），所以厚度必须按候选角求值。
        items = self._items([12.0], 12.0, names=["LongEnoughToNeedRotating"], aliases=())
        _shortened, rotated, hidden = apply_label_degradation(
            items, measure=self._measure_wide_text, abbreviate=True
        )
        assert hidden == 1
        assert items[0].visible is False
        assert items[0].rotated is False
        assert items[0].rotation == items[0].base_rotation  # 没有被留在 90°
        assert rotated is False

    def test_rotated_candidate_accepted_when_rotated_thickness_fits(self):
        # 对照组：厚度维容得下旋转后的文本时，旋转照旧发生——证明上一条测试不是
        # 靠"一律拒绝旋转"通过的。
        items = self._items([12.0], 200.0, names=["LongEnoughToNeedRotating"], aliases=())
        _s, rotated, hidden = apply_label_degradation(
            items, measure=self._measure_wide_text, abbreviate=True
        )
        assert hidden == 0 and rotated
        assert items[0].visible and items[0].rotated
        assert items[0].rotation == 90.0
        # 旋转后沿时间维只占文本高度 10 px：12 px 的区间自身放得下。
        assert items[0].size == (120.0, 10.0)

    def test_unrotated_thickness_still_gates_when_band_is_thin(self):
        # 同一测量函数下，连未旋转方向都放不下厚度 → 一切候选都被拒绝。
        items = self._items([12.0], 4.0, names=["TallText"], aliases=())
        _s, _r, hidden = apply_label_degradation(
            items, measure=self._measure_wide_text, abbreviate=True
        )
        assert hidden == 1 and items[0].visible is False

    # -- 时间维边界（轨道矩形）----------------------------------------------

    def test_edge_label_is_clamped_inside_track_bounds(self):
        # 贴左边缘的标签中心被夹进轨道矩形内：包围盒整体不再越出轨道。
        items = self._items([200.0], 40.0, names=["Edgeward"], aliases=())
        items[0].px_center = (-20.0, 250.0)  # 中心在轨道左界之外
        _s, _r, hidden = apply_label_degradation(
            items,
            measure=lambda item, text: (100.0, 8.0),
            abbreviate=True,
            time_bounds_px=(0.0, 500.0),
        )
        assert hidden == 0 and items[0].visible
        lo, hi = items[0].placed_px
        assert lo == pytest.approx(50.0)  # -20 → 0 + 100/2
        assert hi == pytest.approx(250.0)
        assert items[0].placed_px != items[0].px_center

    def test_label_wider_than_the_track_is_rejected(self):
        # 夹紧也救不了的情况：文本比整条轨道还宽 → 隐藏，而不是画到画框外。
        items = self._items([40.0], 40.0, names=["WiderThanTrack"], aliases=())
        _s, _r, hidden = apply_label_degradation(
            items,
            measure=lambda item, text: (600.0, 8.0),
            abbreviate=True,
            time_bounds_px=(0.0, 500.0),
        )
        assert hidden == 1 and items[0].visible is False

    def test_without_time_bounds_placement_equals_pixel_centre(self):
        # 未给边界（环形/独立调用路径）时 placed_px == px_center，行为不变。
        items = self._items([200.0], 40.0, names=["NoBounds"], aliases=())
        _s, _r, hidden = apply_label_degradation(
            items, measure=lambda item, text: (100.0, 8.0), abbreviate=True
        )
        assert hidden == 0
        assert items[0].placed_px == items[0].px_center

    def test_inverted_time_bounds_rejected(self):
        items = self._items([40.0], 40.0, names=["Bad"], aliases=())
        with pytest.raises(ValueError, match="lo < hi"):
            apply_label_degradation(
                items,
                measure=lambda item, text: (10.0, 8.0),
                abbreviate=True,
                time_bounds_px=(500.0, 0.0),
            )


class TestTrackRegisterAndTruncation:
    """``track_register`` 与 ``fallback_truncation`` 的契约（图 3/图 4 的脚本补丁下沉）。

    两个参数默认关闭，因此上面全部既有用例的行为不变；这里只为显式开启时
    钉住语义：整轨统一语域不改变"能放下就用全名"的判定，前缀截断只在
    降级阶梯末端补位。
    """

    def _items(self, lengths, thickness_px=20.0, names=None, aliases=None):
        items = []
        count = len(lengths)
        for k, length in enumerate(lengths):
            name = (names or [f"Iten{k}" for k in range(count)])[k]
            item_aliases = aliases[k] if aliases is not None else (name[:2],)
            interval = make_interval(name, item_aliases, 500.0 - k)
            items.append(
                LabelItem(
                    interval=interval,
                    artist=None,
                    center=(0.0, 0.0),
                    px_center=(float(k) * 500.0, 0.0),
                    length_px=length,
                    thickness_px=thickness_px,
                    base_rotation=0.0,
                    time_axis_index=time_axis_index_for("x"),
                    rank_priority=2,
                    sort_key=(2, -interval.older_ma, interval.id),
                )
            )
        return items

    @staticmethod
    def _measure(item, text):
        return estimate_text_size(text, 6.0, 100.0)

    def test_interval_register_keeps_the_per_interval_mix(self):
        # 默认：窄区间缩写、宽区间全名——这正是图 3 Epoch 轨出现混排的原因。
        items = self._items(
            [22.0, 300.0], names=["AlphaLongName", "Beta"], aliases=[("Al",), ("Be",)]
        )
        apply_label_degradation(items, measure=self._measure, abbreviate=True)
        assert [item.text for item in items] == ["Al", "Beta"]

    def test_uniform_register_switches_the_whole_track(self):
        # 开启后：同轨只要有一处被迫缩写，全轨统一用代号，不留混排。
        items = self._items(
            [22.0, 300.0], names=["AlphaLongName", "Beta"], aliases=[("Al",), ("Be",)]
        )
        shortened, _rotated, hidden = apply_label_degradation(
            items, measure=self._measure, abbreviate=True, track_register="uniform"
        )
        assert [item.text for item in items] == ["Al", "Be"]
        assert shortened and hidden == 0

    def test_uniform_register_is_inert_when_everything_fits(self):
        # 全名都放得下时不得无故改用代号。
        items = self._items([300.0, 300.0], names=["Alpha", "Beta"], aliases=[("Al",), ("Be",)])
        apply_label_degradation(
            items, measure=self._measure, abbreviate=True, track_register="uniform"
        )
        assert [item.text for item in items] == ["Alpha", "Beta"]

    def test_uniform_register_respects_explicit_abbreviate_false(self):
        # 用户显式关掉缩写时，整轨统一不得越过这一显式选择。
        items = self._items(
            [10.0, 300.0], names=["AlphaLongName", "Beta"], aliases=[("Al",), ("Be",)]
        )
        apply_label_degradation(
            items, measure=self._measure, abbreviate=False, track_register="uniform"
        )
        assert items[0].text == "AlphaLongName"

    def test_truncation_off_by_default(self):
        # 无别名且放不下 → 隐藏（库的默认立场：不凭空造记号）。
        items = self._items([20.0], names=["Aalenian"], aliases=[()])
        _s, _r, hidden = apply_label_degradation(items, measure=self._measure, abbreviate=True)
        assert hidden == 1 and items[0].visible is False

    def test_truncation_recovers_a_label_without_an_alias(self):
        # 开启后："Aalenian" 逐级缩短，最短保留 3 个字符 → "Aal" 放得下。
        items = self._items([20.0], names=["Aalenian"], aliases=[()])
        shortened, _rotated, hidden = apply_label_degradation(
            items, measure=self._measure, abbreviate=True, fallback_truncation=3
        )
        assert hidden == 0 and items[0].visible is True
        assert items[0].text == items[0].interval.name[:3]
        assert shortened is True

    def test_truncation_never_goes_below_the_floor(self):
        # 前缀从 fallback_truncation 个字符起步，放不下才递减，且不短于 2 个字符；
        # 直接对候选生成器求值——阶梯本身是生成器契约，与后续碰撞/旋转无关。
        from geophylo.render.labels import _candidate_sequence

        sequence, strict = _candidate_sequence("Aalenian", "Aalenian", 0.0, 4)
        prefixes = [text for text, _rot in sequence if text != "Aalenian"]
        assert prefixes, "开启 fallback_truncation 后必须生成前缀候选"
        assert prefixes[0] == "Aale", "从 4 个字符起步"
        assert min(len(text) for text in prefixes) == 2, "递减到 2 个字符为止"
        assert 0 in strict and len(strict) == len(prefixes) + 1

    def test_uniform_register_is_per_track_not_per_call(self):
        # 一次 add_geo_axis() 里多条 rank 各占一条轨道；"同轨统一"说的是**一条
        # 条带**，不是这一次调用的全部标签。否则 Period 轨会被 Epoch 轨拖下水，
        # 整张图一起降级成代号。
        items = self._items(
            [300.0, 300.0, 22.0, 300.0],
            names=["Triassic", "Jurassic", "AlphaLongName", "Beta"],
            aliases=[("T",), ("J",), ("Al",), ("Be",)],
        )
        # 前两条放在上轨道（across=0.0），后两条放在下轨道（across=1.0）
        for k, item in enumerate(items):
            item.px_center = (float(k) * 500.0, 0.0)
            item.center = (0.0, 0.0 if k < 2 else 1.0)
        apply_label_degradation(
            items, measure=self._measure, abbreviate=True, track_register="uniform"
        )
        assert [item.text for item in items] == ["Triassic", "Jurassic", "Al", "Be"]

    def test_truncation_runs_after_the_rotate_rung(self):
        # 前缀截断是"造记号"的兜底档，必须排在"读全名"的旋转之后：本可用旋转
        # 读出全名的区间不得被无谓截短。轨道厚度要放得下旋转后的行高（约 41 px），
        # 否则旋转档本身就通不过，谈不上先后。
        items = self._items([12.0], thickness_px=50.0, names=["Aalenian"], aliases=[()])
        shortened, rotated, hidden = apply_label_degradation(
            items, measure=self._measure, abbreviate=True, fallback_truncation=3
        )
        assert hidden == 0 and items[0].text == "Aalenian"
        assert rotated is True and shortened is False

    def test_min_label_gap_keeps_neighbours_apart(self):
        # 默认只判"不相交"：两枚 100 px 宽的标签中心相距 105 px，恰好不重叠即可放置。
        # 给出净距后必须留出 min_label_gap_px，后者沿降级阶梯退让，无处可去即隐藏
        # （旋转候选因厚度维超限被拒，故不会用旋转绕开净距）。
        def build():
            items = self._items(
                [300.0, 300.0],
                thickness_px=20.0,
                names=["Alpha", "Beta"],
                aliases=[("Al",), ("Be",)],
            )
            for k, item in enumerate(items):
                item.px_center = (float(k) * 105.0, 0.0)
            return items

        def measure(item, text):
            return (100.0, 8.0)

        touching = build()
        _s, _r, hidden = apply_label_degradation(touching, measure=measure, abbreviate=True)
        assert hidden == 0, "零净距时相切即可放置"
        assert [item.text for item in touching] == ["Alpha", "Beta"]

        gapped = build()
        _s, _r, hidden = apply_label_degradation(
            gapped, measure=measure, abbreviate=True, min_label_gap_px=10.0
        )
        assert hidden == 1, "净距 10 px 时后者无处可放，应隐藏"

    @pytest.mark.parametrize("bad", [1, 0, -2, True, 3.0])
    def test_truncation_rejects_invalid_floor(self, bad):
        from geophylo.exceptions import InvalidRangeError

        items = self._items([20.0], names=["Aalenian"], aliases=[()])
        with pytest.raises(InvalidRangeError):
            apply_label_degradation(
                items, measure=self._measure, abbreviate=True, fallback_truncation=bad
            )

    def test_unknown_track_register_rejected(self):
        from geophylo.exceptions import InvalidRangeError

        items = self._items([20.0], names=["Aalenian"], aliases=[()])
        with pytest.raises(InvalidRangeError):
            apply_label_degradation(
                items, measure=self._measure, abbreviate=True, track_register="per_track"
            )

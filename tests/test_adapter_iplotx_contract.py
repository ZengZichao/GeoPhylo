"""``spec_from_iplotx()`` 契约测试（实验性，不依赖 iplotx 安装）。

iplotx 未安装的环境（``tests/test_adapter_iplotx.py`` 整体跳过）下，本文件用
fake ``TreeArtist``（只暴露 ``.axes`` 与 ``get_layout()``，必要时再补
``_ipx_internal_data`` / ``get_layout_name()``）锁定适配器自身的契约：
``age_conversion`` 必须作用在布局根距离上（branch length 单位 → Ma），并且
radial 布局的四条拒绝分支必须各自抛 ``AxesTypeError``。

radial 用例只依赖 matplotlib（核心依赖，非可选包），因此在任何 job 里都会
执行；``tests/test_adapter_iplotx.py`` 里那条需要 iplotx/ete4 的集成测试只是
对真库的补充确认（规范 4.8/6.2）。
"""

from __future__ import annotations

import pytest

import geophylo
from geophylo.adapter import spec_from_iplotx

pytestmark = [pytest.mark.experimental]

# horizontal/right 布局的数值坐标（branch length 单位）：radial 拒绝若被绕过，
# 适配器会拿它算出一个 ``root_distance`` 契约而不是报错——正是契约用例要盯住的
# "静默错变换"（mis-transforming）。
_HORIZONTAL_LAYOUT = {"n1": (0.0, 0.0), "n2": (5.0, 1.0), "n3": (2.5, -1.0)}


class _FakeAxis:
    xaxis = type("Axis", (), {"get_converter": staticmethod(lambda: None)})()
    yaxis = type("Axis", (), {"get_converter": staticmethod(lambda: None)})()

    @staticmethod
    def get_xscale() -> str:
        return "linear"

    @staticmethod
    def get_yscale() -> str:
        return "linear"


class _FakeTreeArtist:
    """最小 TreeArtist 桩：horizontal 布局的 ``{节点: (x, y)}`` 字典。"""

    def __init__(self, layout: dict) -> None:
        self.axes = _FakeAxis()
        self._layout = layout

    def get_layout(self) -> dict:
        return self._layout


class _StubTreeArtist(_FakeTreeArtist):
    """带 iplotx 布局元数据的 TreeArtist 桩（radial 拒绝分支用）。

    ``internal`` 模拟 iplotx 1.8 的私有 ``_ipx_internal_data`` 字典；不给时该
    属性不存在，即旧版形态（适配器只能靠复数坐标与宿主 Axes 类型判断）。
    ``layout_name`` 模拟公开的 ``get_layout_name()``，``layout_name_error`` 模拟
    元数据读取失败（适配器据此回落到坐标扫描）；"根本没有这个方法"的旧版形态
    直接用基类 ``_FakeTreeArtist`` 表达。
    """

    def __init__(
        self,
        layout: dict,
        *,
        internal: dict | None = None,
        layout_name: str | None = None,
        layout_name_error: BaseException | None = None,
    ) -> None:
        super().__init__(layout)
        if internal is not None:
            self._ipx_internal_data = internal
        self._stub_layout_name = layout_name
        self._stub_layout_name_error = layout_name_error

    def get_layout_name(self) -> str | None:
        if self._stub_layout_name_error is not None:
            raise self._stub_layout_name_error
        return self._stub_layout_name


@pytest.fixture()
def polar_host_axes():
    """真实 ``PolarAxes`` 宿主：matplotlib 是核心依赖，不引入任何可选包。"""
    from matplotlib.figure import Figure
    from matplotlib.projections.polar import PolarAxes

    fig = Figure()
    ax = fig.add_subplot(111, projection="polar")
    # 前提守卫：适配器用 isinstance 判定，桩给的必须是同一个类，否则用例是空转。
    assert isinstance(ax, PolarAxes), "fixture 未产出极坐标 Axes"
    try:
        yield ax
    finally:
        fig.clf()


class TestAgeConversionApplied:
    def test_factor_applied_to_layout_distances(self):
        # 布局 x ∈ [0, 5]（branch length 单位）；age_conversion=2.0 → 10 Ma。
        artist = _FakeTreeArtist({"n1": (0.0, 0.0), "n2": (5.0, 1.0), "n3": (2.5, -1.0)})
        spec = spec_from_iplotx(artist, time_axis="x", age_conversion=2.0, root_age=100.0)
        assert spec.age_range == pytest.approx((90.0, 100.0))

    def test_callable_applied_per_distance(self):
        artist = _FakeTreeArtist({"n1": (0.0, 0.0), "n2": (5.0, 1.0)})
        spec = spec_from_iplotx(
            artist, time_axis="x", age_conversion=lambda bl: bl * 3.0, root_age=30.0
        )
        assert spec.age_range == pytest.approx((15.0, 30.0))

    def test_nonzero_root_time_offset_handled(self):
        # 布局根不在 0（iplotx 可能加 padding）：以最小值为根距离基线。
        artist = _FakeTreeArtist({"n1": (1.0, 0.0), "n2": (3.0, 1.0)})
        spec = spec_from_iplotx(artist, time_axis="x", age_conversion=2.0, root_age=50.0)
        assert spec.age_range == pytest.approx((46.0, 50.0))

    def test_illegal_conversion_result_rejected(self):
        artist = _FakeTreeArtist({"n1": (0.0, 0.0), "n2": (5.0, 1.0)})
        with pytest.raises(geophylo.CoordinateError, match="age_conversion"):
            spec_from_iplotx(artist, time_axis="x", age_conversion=lambda bl: -bl, root_age=100.0)


class TestRadialRejection:
    """radial 布局拒绝的依赖无关契约（规范 4.8/6.2）。

    集成测试 ``tests/test_adapter_iplotx.py::test_radial_layout_rejected_explicitly``
    需要 iplotx + ete4，缺依赖即整体跳过；本类只依赖 matplotlib，所以在任何 job
    里都执行。每条用例断言**分支专属**的消息片段，且其余分支都保持"不触发"：
    绕过对应守卫后，适配器要么静默算出一个 ``root_distance`` 契约（``pytest.raises``
    直接失败），要么由别的分支报错而消息不匹配——两种情况用例都会变红。
    """

    def test_polar_layout_coordinate_system_rejected(self):
        # 分支 1（iplotx 1.8 主检测路径）：私有元数据标注极坐标系。
        # 名字这里故意留 None，保证只有这一条分支能触发拒绝。
        artist = _StubTreeArtist(
            _HORIZONTAL_LAYOUT,
            internal={"layout_coordinate_system": "polar"},
        )
        with pytest.raises(
            geophylo.AxesTypeError, match=r"layout_coordinate_system='polar'"
        ) as exc:
            spec_from_iplotx(artist, time_axis="x", age_conversion=1.0, root_age=100.0)
        assert isinstance(exc.value, geophylo.GeophyloError), "拒绝必须是公开异常类型"
        assert "6.3" in str(exc.value), "拒绝消息要给出 6.3 的自绘出路"

    def test_radial_layout_name_rejected(self):
        # 分支 2（公开入口）：get_layout_name() == "radial"，元数据里没有 polar 标记。
        artist = _StubTreeArtist(
            _HORIZONTAL_LAYOUT,
            internal={"layout_coordinate_system": "cartesian"},
            layout_name="radial",
        )
        with pytest.raises(geophylo.AxesTypeError, match=r"get_layout_name\(\) == 'radial'"):
            spec_from_iplotx(artist, time_axis="x", age_conversion=1.0, root_age=100.0)

    @pytest.mark.parametrize(
        "layout",
        [
            pytest.param({"n1": (1 + 2j, 3 + 4j), "n2": (2 + 2j, 5 + 4j)}, id="complex-pair"),
            pytest.param({"n1": 1 + 2j, "n2": 2 + 2j}, id="bare-complex"),
        ],
    )
    def test_polar_valued_layout_rejected(self, layout):
        # 分支 3（旧版兼容路径）：没有任何元数据可读，只能靠复数坐标识别
        # ——用基类桩，确保 get_layout_name/_ipx_internal_data 都不存在。
        with pytest.raises(geophylo.AxesTypeError, match="polar-shaped layout data"):
            spec_from_iplotx(
                _FakeTreeArtist(layout), time_axis="x", age_conversion=1.0, root_age=100.0
            )

    def test_polar_host_axes_rejected(self, polar_host_axes):
        # 分支 4：布局数据是实数，但宿主 Axes 是极坐标 —— 数值能算出契约，
        # 但 add_geo_axis() 装不上去，必须在适配阶段就拒绝。
        # require_linear_numeric_axes() 对 PolarAxes 不报错（实测），
        # 所以这条 isinstance 守卫是唯一的拒绝点。
        artist = _FakeTreeArtist(_HORIZONTAL_LAYOUT)
        artist.axes = polar_host_axes
        with pytest.raises(geophylo.AxesTypeError, match="the host Axes is a polar Axes"):
            spec_from_iplotx(artist, time_axis="x", age_conversion=1.0, root_age=100.0)

    def test_cartesian_metadata_not_rejected(self):
        """正向对照：笛卡尔元数据不能被误当 radial 拒掉（否则拒绝逻辑恒真）。"""
        artist = _StubTreeArtist(
            _HORIZONTAL_LAYOUT,
            internal={"layout_coordinate_system": "cartesian"},
            layout_name="horizontal",
        )
        spec = spec_from_iplotx(artist, time_axis="x", age_conversion=2.0, root_age=100.0)
        assert spec.mode == "root_distance"
        assert spec.age_range == pytest.approx((90.0, 100.0))

    def test_unreadable_layout_name_falls_back_to_value_scan(self):
        # 元数据读取失败（except Exception → name=None）时必须回落到复数坐标
        # 扫描，而不是把 radial 当成 horizontal 放过。
        artist = _StubTreeArtist(
            {"n1": (1 + 2j, 3 + 4j), "n2": (2 + 2j, 5 + 4j)},
            layout_name_error=RuntimeError("iplotx 版本不认识这个字段"),
        )
        with pytest.raises(geophylo.AxesTypeError, match="polar-shaped layout data"):
            spec_from_iplotx(artist, time_axis="x", age_conversion=1.0, root_age=100.0)


class TestSkipPolicyForOptionalDependencies:
    """跳过策略守卫：`except Exception → pytest.skip` 会把真实故障转成跳过。

    本文件不依赖 iplotx/ete4，因此在任何 job 里都会执行——正好用来钉住
    tests/test_adapter_iplotx.py 的跳过策略。
    """

    def test_layout_escape_hatch_cannot_swallow_geophylo_errors(self):
        import inspect

        from conftest import LAYOUT_CONSTRUCTION_ERRORS

        assert LAYOUT_CONSTRUCTION_ERRORS, "跳过口子不能是空元组"
        assert Exception not in LAYOUT_CONSTRUCTION_ERRORS, (
            "逃生口子必须窄：Exception/BaseException 会把真故障一起吞掉"
        )
        exported = {
            obj
            for obj in vars(geophylo).values()
            if inspect.isclass(obj)
            and issubclass(obj, geophylo.GeophyloError)
            and obj is not geophylo.GeophyloError
        }
        assert exported, "geophylo 未导出任何异常类，本守卫的前提已变化"
        swallowed = sorted(
            error.__name__ for error in exported if issubclass(error, LAYOUT_CONSTRUCTION_ERRORS)
        )
        assert not swallowed, f"geophylo 自身异常被跳过策略覆盖：{swallowed}"

    def test_integration_test_file_has_no_broad_except(self):
        """AST 检查：集成测试里不得再出现 ``except Exception``/裸 except。"""
        import ast
        from pathlib import Path

        path = Path(__file__).with_name("test_adapter_iplotx.py")
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        broad = [
            node.lineno
            for node in ast.walk(tree)
            if isinstance(node, ast.ExceptHandler)
            and (
                node.type is None
                or (
                    isinstance(node.type, ast.Name)
                    and node.type.id in {"Exception", "BaseException"}
                )
            )
        ]
        assert not broad, f"{path.name} 的宽泛 except 会把真故障变成 SKIP，行号：{broad}"
        # 并且确实只对第三方布局构造开了窄口子：
        guarded = [
            node.lineno
            for node in ast.walk(tree)
            if isinstance(node, ast.ExceptHandler) and node.type is not None
        ]
        assert guarded, f"{path.name} 里的布局可用性豁免消失了——请同步删除跳过策略守卫"

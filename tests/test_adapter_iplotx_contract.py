"""``spec_from_iplotx()`` 契约测试（实验性，不依赖 iplotx 安装）。

iplotx 未安装的环境（``tests/test_adapter_iplotx.py`` 整体跳过）下，本文件用
fake ``TreeArtist``（只暴露 ``.axes`` 与 ``get_layout()``）锁定适配器自身的
契约：``age_conversion`` 必须作用在布局根距离上（branch length 单位 → Ma）。
"""

from __future__ import annotations

import pytest

import geophylo
from geophylo.adapter import spec_from_iplotx

pytestmark = [pytest.mark.experimental]


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

"""异常与警告消息的本地化契约（默认英文，``GEOPHYLO_LANG=zh`` 切中文）。

守的是三件事：① 默认语言是英文，不读中文的使用者也能读懂报错；
② 中文文案并未删除，``GEOPHYLO_LANG=zh`` 仍能取回；③ 被内插进文案的片段
（定位标签、提示句、缺陷明细）本身也是双语的——英文条里不得出现中文/CJK 标点，
中文条里不得出现整段英文，也不得出现 ``msg(en, en)`` 这种"中文条没翻译"的复制
粘贴。③ 是历史回归点：曾经有硬编码中文标签流入英文条，产出
``快照顶层 is missing the required key 'schema_version'`` 这类混合文案。
"""

from __future__ import annotations

import ast
import os
import pathlib
import subprocess
import sys

import pytest

from geophylo._i18n import LANG, msg
from geophylo.exceptions import GeophyloError
from geophylo.validation import require_number

#: 仓库根（未安装本包时子进程要靠它 import geophylo）。
_PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]

#: 仓库根下的运行时代码包（本文件的静态扫描对象）。
_PACKAGE_ROOT = _PROJECT_ROOT / "geophylo"

#: CJK 表意文字 + CJK 标点 + 全角标点（全角分号 ``；`` 在 ``一``-``鿿`` 之外，
#: 而泄漏案例里正是它被拼进了英文句子）。
_CJK_RANGES = (
    ("\u3000", "\u303f"),  # CJK 标点、。〉〈
    ("\u3400", "\u4dbf"),  # 扩展 A
    ("\u4e00", "\u9fff"),  # 基本汉字
    ("\uff00", "\uffef"),  # 全角标点 ；：（）
)


def _cjk(text: str) -> list[str]:
    """返回 ``text`` 中的 CJK/全角标点字符。"""
    return [ch for ch in text if any(lo <= ch <= hi for lo, hi in _CJK_RANGES)]


def test_default_language_is_english():
    assert not LANG.startswith("zh"), f"默认语言应为英文，实际 {LANG!r}"
    assert msg("hello", "你好") == "hello"
    assert not _cjk(msg("hello", "你好"))


def test_msg_switches_on_env(monkeypatch):
    monkeypatch.setattr("geophylo._i18n.LANG", "zh-CN")
    # msg() 读取模块级 LANG，故直接断言读取结果即可。
    from geophylo import _i18n

    assert _i18n.LANG.startswith("zh")
    assert _i18n.msg("hello", "你好") == "你好"


def test_public_error_message_is_english_by_default():
    from geophylo.exceptions import InvalidRangeError

    with pytest.raises(InvalidRangeError) as excinfo:
        require_number("alpha", "not-a-number")
    text = str(excinfo.value)
    assert "alpha" in text
    assert not _cjk(text), f"默认消息不应含中文：{text!r}"
    assert "must be a real number" in text


def test_chinese_message_available_through_env():
    """子进程验证：GEOPHYLO_LANG=zh 时消息确实切回中文。"""
    code = (
        "import geophylo.validation as v\n"
        "from geophylo.exceptions import GeophyloError\n"
        "try:\n"
        "    v.require_number('alpha', 'x')\n"
        "except GeophyloError as exc:\n"
        "    print(str(exc))\n"
    )
    proc = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        env={**os.environ, "GEOPHYLO_LANG": "zh", "MPLBACKEND": "Agg"},
        timeout=60,
    )
    assert proc.returncode == 0, proc.stderr
    out = proc.stdout.strip()
    assert _cjk(out), f"GEOPHYLO_LANG=zh 应给出中文，实际 {out!r}"


def test_every_public_exception_still_subclasses_geophylo_error():
    import geophylo.exceptions as exc_mod

    for name in dir(exc_mod):
        obj = getattr(exc_mod, name)
        if isinstance(obj, type) and issubclass(obj, BaseException) and obj is not BaseException:
            assert issubclass(obj, GeophyloError) or obj is GeophyloError, name


# ---------------------------------------------------------------------------
# ③ 内插片段必须双语：静态扫描 + 端到端实测
# ---------------------------------------------------------------------------


def _msg_callsites():
    """产出运行时代码包里每个 ``msg(en, zh)`` 调用点的 ``(文件, 行号, 英文条形源, 中文条形源, 节点)``。"""
    for path in sorted(_PACKAGE_ROOT.rglob("*.py")):
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "msg"
                and len(node.args) == 2
            ):
                yield (
                    path,
                    node.lineno,
                    ast.get_source_segment(source, node.args[0]) or "",
                    ast.get_source_segment(source, node.args[1]) or "",
                    node,
                )


def test_every_msg_callsite_is_a_genuine_language_pair():
    """``msg()`` 的两条文案必须真的是"英文/中文"两条，而不是复制粘贴。

    回归点：``render/polar.py`` 曾把同一条英文写两遍，中文用户直接看到英文。
    """
    total = 0
    for path, lineno, en_src, zh_src, _node in _msg_callsites():
        total += 1
        site = f"{path.relative_to(_PACKAGE_ROOT.parent)}:{lineno}"
        assert en_src != zh_src, f"{site} 的中/英两条文案完全相同（中文条未翻译）"
        assert not _cjk(en_src), f"{site} 的英文条含 CJK 字符 {_cjk(en_src)!r}：{en_src!r}"
        assert _cjk(zh_src), f"{site} 的中文条不含任何中文：{zh_src!r}"
        # 指向文档的中文条必须指中文手册，英文条必须指英文手册。
        assert "user-guide.zh.md" not in en_src, f"{site} 的英文条指向了中文手册：{en_src!r}"
        assert "user-guide.en.md" not in zh_src, f"{site} 的中文条指向了英文手册：{zh_src!r}"
    assert total > 100, f"扫描到的 msg 调用点过少（{total}），扫描本身可能失效"


def test_labels_interpolated_into_english_text_are_bilingual():
    """内插进英文条的变量必须自身双语，不得被赋成纯中文字面量。

    回归点：``data/builtin.py`` 曾把定位标签硬编码为中文（``"快照顶层"``、
    ``f"区间 {id!r}"``、``hint``、覆盖缺陷明细），``data/pyrolite_backend.py``
    曾把 ``where`` 写成 ``名称（第 N 行）``，于是默认英文模式下输出
    ``快照顶层 is missing the required key 'schema_version'``。
    """
    # 第一遍：找出被赋了"中文字面量"的变量（字面量在 msg 的中文条里不算，
    # 因为那本身就是双语配对的另一半）。
    tainted: dict[str, str] = {}
    for path in sorted(_PACKAGE_ROOT.rglob("*.py")):
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
        chinese_branches: set[int] = set()
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "msg"
            ):
                for arg in node.args[1:]:
                    chinese_branches.update(id(child) for child in ast.walk(arg))
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Assign) and len(node.targets) == 1):
                continue
            target = node.targets[0]
            if not isinstance(target, ast.Name):
                continue
            literals = [
                child
                for child in ast.walk(node.value)
                if isinstance(child, ast.Constant)
                and isinstance(child.value, str)
                and _cjk(child.value)
            ]
            if any(id(item) not in chinese_branches for item in literals):
                tainted[target.id] = f"{path.relative_to(_PACKAGE_ROOT.parent)}:{node.lineno}"
    # 第二遍：这些变量不得出现在任何 msg 英文条里。
    violations = []
    for path, lineno, en_src, _zh, node in _msg_callsites():
        names = {child.id for child in ast.walk(node.args[0]) if isinstance(child, ast.Name)}
        bad = sorted(names & set(tainted))
        if bad:
            violations.append(
                f"{path.relative_to(_PACKAGE_ROOT.parent)}:{lineno} 英文条内插了纯中文变量 "
                f"{bad}（赋值点 {', '.join(tainted[v] for v in bad)}）：{en_src!r}"
            )
    assert not violations, "中文变量泄漏进英文消息：\n" + "\n".join(violations)


def _boundary_payload(age: float) -> dict:
    return {
        "age_ma": age,
        "qualifier": "defined",
        "uncertainty_ma": None,
        "definition": "gssp",
        "source_iri": None,
    }


def _record_payload(interval_id: str, older: float, younger: float, **overrides) -> dict:
    record = {
        "id": interval_id,
        "source_iri": f"urn:example:{interval_id}",
        "name": interval_id.capitalize(),
        "label": interval_id,
        "aliases": [],
        "rank": "Age",
        "rank_class": "geochronologic",
        "parent_id": "parent",
        "source_parent_id": None,
        "status": "ratified",
        "color": "#ABCDEF",
        "older_boundary": _boundary_payload(older),
        "younger_boundary": _boundary_payload(younger),
    }
    record.update(overrides)
    return record


def _interval(interval_id, older, younger, parent, rank="Age"):
    from geophylo.data.models import Boundary, Interval

    return Interval(
        id=interval_id,
        source_iri=f"urn:example:{interval_id}",
        name=interval_id.capitalize(),
        label=interval_id,
        aliases=(),
        rank=rank,
        rank_class="geochronologic"
        if rank in ("Eon", "Era", "Period", "Epoch", "Age")
        else "structural",
        parent_id=parent,
        source_parent_id=None,
        status="ratified",
        color="#ABCDEF",
        older_boundary=Boundary(older, "defined", None, "gssp", None),
        younger_boundary=Boundary(younger, "defined", None, "gssp", None),
    )


def _valid_snapshot() -> dict:
    return {
        "schema_version": 1,
        "chart_version": "test/01",
        "snapshot_revision": 1,
        "generator": {"version": "0"},
        "source": "urn:example:source",
        "license": "MIT",
        "hash": {},
        "intervals": [
            _record_payload("p1", 100.0, 0.0, rank="Period", parent_id=None, name="Parent"),
            _record_payload("a1", 100.0, 50.0, parent_id="p1", name="AgeOne"),
            _record_payload("a2", 50.0, 0.0, parent_id="p1", name="AgeTwo"),
        ],
    }


def _message_battery() -> list[tuple[str, str]]:
    """跑一遍**含内插片段**的失败路径，返回 ``(用例名, 异常消息)``。

    这些用例专门覆盖"标签/明细/hint 由变量内插而成"的消息，静态扫描只能看
    字面量，端到端实测才能证明英文条里真的没有中文、中文条里真的没有整段英文。
    """
    import geophylo.data.builtin as builtin

    def snapshot(**overrides):
        payload = _valid_snapshot()
        payload.update(overrides)
        return payload

    def records(*items):
        return snapshot(intervals=list(items))

    cases: list[tuple[str, object]] = [
        (
            "顶层缺键",
            lambda: builtin.validate_snapshot_payload(
                {k: v for k, v in snapshot().items() if k != "schema_version"}
            ),
        ),
        (
            "记录缺键",
            lambda: builtin.validate_snapshot_payload(
                records(
                    {
                        k: v
                        for k, v in _record_payload("a", 100.0, 0.0).items()
                        if k != "older_boundary"
                    }
                )
            ),
        ),
        (
            "边界定位标签",
            lambda: builtin.validate_snapshot_payload(
                records(_record_payload("a", 100.0, 0.0, older_boundary={"age_ma": 100.0}))
            ),
        ),
        (
            "边界年龄非数值",
            lambda: builtin.validate_snapshot_payload(
                records(
                    _record_payload("a", 100.0, 0.0, older_boundary=dict(_boundary_payload("x")))
                )
            ),
        ),
        (
            "新老端顺序",
            lambda: builtin.validate_snapshot_payload(records(_record_payload("a", 10.0, 20.0))),
        ),
        (
            "颜色格式",
            lambda: builtin.validate_snapshot_payload(
                records(_record_payload("a", 100.0, 0.0, color="black"))
            ),
        ),
        (
            "status 取值域",
            lambda: builtin.validate_snapshot_payload(
                records(_record_payload("a", 100.0, 0.0, status="pending"))
            ),
        ),
        (
            "rank 取值域",
            lambda: builtin.validate_snapshot_payload(
                records(_record_payload("a", 100.0, 0.0, rank="Supera"))
            ),
        ),
        (
            "父子关系",
            lambda: builtin.validate_snapshot_payload(
                records(_record_payload("a", 100.0, 0.0, parent_id="nope"))
            ),
        ),
        (
            "覆盖缺陷-缺口",
            lambda: builtin._check_hierarchy(
                [
                    _interval("p", 100.0, 0.0, None, "Period"),
                    _interval("a", 100.0, 60.0, "p"),
                    _interval("b", 50.0, 0.0, "p"),
                ],
                {
                    i.id: i
                    for i in [
                        _interval("p", 100.0, 0.0, None, "Period"),
                        _interval("a", 100.0, 60.0, "p"),
                        _interval("b", 50.0, 0.0, "p"),
                    ]
                },
            ),
        ),
        (
            "覆盖缺陷-老端",
            lambda: builtin._check_hierarchy(
                (
                    ivals := [
                        _interval("p", 100.0, 0.0, None, "Period"),
                        _interval("a", 95.0, 60.0, "p"),
                        _interval("b", 50.0, 0.0, "p"),
                    ]
                ),
                {i.id: i for i in ivals},
            ),
        ),
        (
            "覆盖缺陷-年轻端",
            lambda: builtin._check_hierarchy(
                (
                    ivals := [
                        _interval("p", 100.0, 0.0, None, "Period"),
                        _interval("a", 100.0, 60.0, "p"),
                        _interval("b", 50.0, 5.0, "p"),
                    ]
                ),
                {i.id: i for i in ivals},
            ),
        ),
    ]

    def id_hint():
        backend = builtin.SnapshotBackend(_valid_snapshot())
        backend.get_interval("ageone")  # 名称被当 ID 查

    cases.append(("ID 提示句", id_hint))

    out: list[tuple[str, str]] = []
    for tag, fn in cases:
        try:
            fn()
        except GeophyloError as exc:
            out.append((tag, str(exc)))
            continue
        raise AssertionError(f"用例 {tag!r} 没有抛异常，已失去回归价值")
    return out


#: 中文条里不得残留的英文句子片段（曾经因单语片段而泄漏）。
_ENGLISH_RESIDUES = (
    "is missing the required key",
    "must be an object",
    "looks like an interval name",
    "does not meet",
    "segment by segment",
    "does not cover",
)

#: 英文条里不得残留的中文片段（历史泄漏点）。
_CHINESE_RESIDUES = (
    "快照顶层",
    "区间记录",
    "区间 ",
    "看起来是名称",
    "不相接",
    "未与父区间",
)


def test_english_messages_carry_no_chinese_fragments():
    """默认英文模式：内插片段不得把中文带进英文消息。"""
    assert not LANG.startswith("zh"), "本用例只在默认英文模式下有效"
    battery = _message_battery()
    assert len(battery) >= 13
    for tag, text in battery:
        assert not _cjk(text), f"用例 {tag!r} 的英文消息含 CJK：{text!r}"
        for fragment in _CHINESE_RESIDUES:
            assert fragment not in text, f"用例 {tag!r} 的英文消息残留中文片段 {fragment!r}"


def test_chinese_messages_are_localised_end_to_end():
    """``GEOPHYLO_LANG=zh``：每条消息都必须是中文，且不残留整段英文句子。"""
    code = (
        "import importlib.util, sys\n"
        "sys.path.insert(0, sys.argv[2])\n"
        "spec = importlib.util.spec_from_file_location('_probe', sys.argv[1])\n"
        "mod = importlib.util.module_from_spec(spec)\n"
        "spec.loader.exec_module(mod)\n"
        "for tag, text in mod._message_battery():\n"
        "    print(tag + '\\x1f' + text)\n"
    )
    proc = subprocess.run(
        [
            sys.executable,
            "-c",
            code,
            str(pathlib.Path(__file__).resolve()),
            str(_PROJECT_ROOT),
        ],
        capture_output=True,
        text=True,
        env={**os.environ, "GEOPHYLO_LANG": "zh", "MPLBACKEND": "Agg"},
        timeout=120,
    )
    assert proc.returncode == 0, proc.stderr
    battery = [line.split("\x1f", 1) for line in proc.stdout.strip().splitlines()]
    assert len(battery) >= 13, proc.stdout
    for tag, text in battery:
        assert _cjk(text), f"用例 {tag!r} 的中文消息没有本地化：{text!r}"
        for fragment in _ENGLISH_RESIDUES:
            assert fragment not in text, f"用例 {tag!r} 的中文消息残留英文句子 {fragment!r}"


@pytest.mark.parametrize(
    ("module_name", "must_contain", "must_not_contain"),
    [
        # 语言开关的真实使用方式：LANG 在 import 时求值，之后再改不生效。
        ("geophylo._i18n", ("import geophylo",), ("docstring 保持双语",)),
        # code= 按实例覆盖是保留能力，当前没有生产调用点。
        ("geophylo.exceptions", ("没有任何",), ("个别调用点需要更细的判别时",)),
    ],
)
def test_module_claims_match_the_code(module_name, must_contain, must_not_contain):
    """模块 docstring 的自述必须与实际行为一致（防止失实声明回归）。"""
    import importlib

    doc = importlib.import_module(module_name).__doc__ or ""
    for fragment in must_contain:
        assert fragment in doc, f"{module_name} 的 docstring 未写明 {fragment!r}"
    for fragment in must_not_contain:
        assert fragment not in doc, f"{module_name} 的 docstring 仍含失实声明 {fragment!r}"

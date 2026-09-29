"""文档数值动态校验（开发文档 7.7）。

用户面向文档（README、docs/）中的边界数值必须来自内置快照，不得手写；示例代码
里也不得出现 ICS 边界值的字面量（演示用的 ``root_age=`` 除外）。

两条纪律：

* 扫描器必须能被证明"会报警"。因此每个检查都拆成纯函数，并各自配一个
  合成反例（planted violation）测试——真实文档恰好干净时，扫描器也不会悄悄变成
  永真断言。
* 不保留指向不存在文件名的死守卫，并且用锚点断言保证 glob 真的读到了快照，
  空集合不会"通过"。
"""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path
from typing import Any

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = Path(PROJECT_ROOT / "geophylo" / "data" / "snapshots")

# 数值模式：<age> Ma，可选 ± <err>。捕获组 1 是年龄值。
_MA_PATTERN = re.compile(r"(\d+(?:\.\d+)?)\s*(?:±\s*\d+(?:\.\d+)?\s*)?Ma")
# 演示用的关键字参数：这些数值是"合成树的根年龄/换算系数"，不是 ICS 边界值。
_ALLOWED_KEYWORDS = frozenset({"root_age", "age_conversion"})
# ``0`` 在示例里是坐标原点/“现在”，不是被手写的 ICS 边界值（快照里 0.0 Ma 只是
# 定义域端点）。除此之外的一切快照边界值都不允许出现在示例常量里。
_TRIVIAL_VALUES = frozenset({0.0})
# 文档确实会引用的关键锚点（缺失即说明快照读取失败，而不是"没有违规"）。
DOCUMENTED_ANCHORS = (66.0, 143.1, 201.4, 251.902, 538.8, 486.85)


@pytest.fixture(scope="module")
def snapshot_ages() -> set[float]:
    ages: set[float] = set()
    for path in sorted(SNAPSHOT.glob("ics_chart-*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        for record in payload["intervals"]:
            for side in ("older_boundary", "younger_boundary"):
                ages.add(float(record[side]["age_ma"]))
    assert ages, f"没有从 {SNAPSHOT} 读到任何边界年龄——扫描会变成永真"
    assert set(DOCUMENTED_ANCHORS) <= ages, "锚点年龄缺失，快照读取或文档基准已漂移"
    return ages


def _markdown_files() -> list[Path]:
    files = [PROJECT_ROOT / "README.md"]
    files.extend((PROJECT_ROOT / "docs").glob("*.md"))
    return [path for path in files if path.exists()]


def ma_violations(text: str, origin: str, ages: set[float]) -> list[str]:
    """纯函数：Markdown 文本里所有 ``<数值> Ma`` 必须属于快照边界集合。"""
    return [
        f"{origin}: {match.group(0)!r} 不在快照边界集合中"
        for match in _MA_PATTERN.finditer(text)
        if float(match.group(1)) not in ages
    ]


def example_violations(source: str, origin: str, ages: set[float]) -> list[str]:
    """纯函数：示例源码里的数值字面量不得等于 ICS 边界年龄。

    用 AST 而不是正则：正则 ``\\b(\\d{2,3}\\.\\d)\\b`` 会漏掉 ``251.902``、
    ``486.85``、``541``、``66`` 这些真实边界值；AST 覆盖一切数值常量，包括
    整数与高小数位。``root_age=`` / ``age_conversion=`` 的演示值按约定豁免。
    """
    tree = ast.parse(source, filename=origin)
    exempt: set[tuple[int, int]] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.keyword) and node.arg in _ALLOWED_KEYWORDS:
            for value in ast.walk(node.value):
                if isinstance(value, ast.Constant) and isinstance(value.value, (int, float)):
                    exempt.add((value.lineno, value.col_offset))
    found: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Constant) or not isinstance(node.value, (int, float)):
            continue
        if isinstance(node.value, bool) or (node.lineno, node.col_offset) in exempt:
            continue
        if float(node.value) in _TRIVIAL_VALUES:
            continue
        if float(node.value) in ages:
            found.append(f"{origin}:{node.lineno} 手写了快照边界值 {node.value!r}")
    return found


def test_all_ma_numbers_come_from_snapshot(snapshot_ages):
    violations: list[str] = []
    checked = 0
    for md in _markdown_files():
        text = md.read_text(encoding="utf-8")
        checked += len(_MA_PATTERN.findall(text))
        violations.extend(ma_violations(text, md.name, snapshot_ages))
    assert checked >= 6, (
        f"文档里的 ``<数值> Ma`` 命中数骤降到 {checked}：正则或文档格式已失效，"
        "本测试随之失去报警能力（当前基线 11 处）"
    )
    assert not violations, "\n".join(violations)


def test_ma_scanner_reports_a_planted_violation(snapshot_ages):
    """扫描器自证：编造的边界值必须被报警，合法值必须放行。"""
    bogus = max(snapshot_ages) + 0.3719
    assert bogus not in snapshot_ages
    hit = ma_violations(f"底界为 {bogus} Ma。", "<synthetic>", snapshot_ages)
    assert len(hit) == 1, f"合成反例没被抓住：{hit}"
    legal = ma_violations("底界为 66.0 Ma。", "<synthetic>", snapshot_ages)
    assert legal == [], f"合法值被误报：{legal}"


def test_examples_avoid_hardwired_boundary_numbers(snapshot_ages):
    violations: list[str] = []
    scanned = 0
    for py in sorted((PROJECT_ROOT / "examples").glob("*.py")):
        source = py.read_text(encoding="utf-8")
        scanned += sum(
            1
            for node in ast.walk(ast.parse(source, filename=str(py)))
            if isinstance(node, ast.Constant) and isinstance(node.value, (int, float))
        )
        violations.extend(example_violations(source, py.name, snapshot_ages))
    assert scanned >= 20, f"示例里的数值常量骤减到 {scanned}：扫描器已无事可做，请检查示例"
    assert not violations, "示例手写了 ICS 边界数值：\n  " + "\n  ".join(violations)


def test_example_scanner_reports_a_planted_violation(snapshot_ages):
    """扫描器自证：把 251.902 / 486.85 / 541 / 66 这类值写进示例必须被抓到。"""
    planted = [66.0, 251.902, 486.85, 538.8]
    source = "ax.set_xlim(0, 251.902)\nboundary = 486.85\nold_style = 66\nroot_age_value = 538.8\n"
    hits = example_violations(source, "<synthetic>", snapshot_ages)
    assert len(hits) == len(planted), f"合成反例应全部被抓，实际 {hits}"
    # root_age= 的演示值是唯一被约定的豁免；写进普通表达式仍应报警。
    exempt = example_violations("spec = f(tree, root_age=538.8)\n", "<synthetic>", snapshot_ages)
    assert exempt == [], exempt
    benign = example_violations(
        "fig, ax = plt.subplots(figsize=(12, 8))\n", "<synthetic>", snapshot_ages
    )
    assert benign == [], benign


def test_snapshot_has_all_documented_key_ages(snapshot_ages):
    # 反向兜底：文档撰写时引用的关键锚点值必须真的存在于快照。
    for anchor in DOCUMENTED_ANCHORS:
        assert anchor in snapshot_ages


# ---------------------------------------------------------------------------
# 开发文档 7.1：参数表与代码逐项一致（参数名、默认值、rank 权重、6 px 下限、
# label_size × 2 像素间距规则）。此前 7.1 把本文件写成可核验方式，但本文件只查
# 快照年龄（7.7），承诺的检查并不存在 —— 以下补上。
# ---------------------------------------------------------------------------

_GUIDES = ("docs/user-guide.en.md", "docs/user-guide.zh.md")
_PARAM_LINE = re.compile(r"^ {4}(?P<name>[a-z_]+)=(?P<value>[^,#\n]+),", re.M)


def _guide_text(relative: str) -> str:
    return (PROJECT_ROOT / relative).read_text(encoding="utf-8")


def _call_block(text: str, func: str) -> str:
    """取出手册代码块里那次带完整参数表的 ``func(...)`` 调用文本。

    文档多处提到 ``add_geo_axis()``（目录锚点、行内引用、单行示例），且围栏代码块之间
    还有别的调用示例，因此按"哪个 ```python 块含 ``label_size=``"来挑，并从调用行读到
    闭合括号为止，而不是做全文括号配对。
    """
    for fence in re.finditer(r"```python\n(.*?)```", text, re.S):
        block = fence.group(1)
        if f"{func}(" not in block or "label_size=" not in block:
            continue
        lines, seen = [], False
        for line in block.splitlines():
            if not seen and f"{func}(" in line:
                seen = True
            if not seen:
                continue
            if line.strip().startswith(")"):
                break
            lines.append(line)
        return "\n".join(lines)
    raise AssertionError(f"{func}：文档里没有含参数表的调用块")


def _documented_defaults(func: str) -> dict[str, Any]:
    """两份手册里 ``func`` 参数块写出的 ``name=literal`` 默认值。"""
    out: dict[str, Any] = {}
    for guide in _GUIDES:
        block = _call_block(_guide_text(guide), func)
        for m in _PARAM_LINE.finditer(block):
            raw = m.group("value").strip()
            try:
                out[m.group("name")] = ast.literal_eval(raw)
            except (ValueError, SyntaxError):
                continue  # 跨行书写或非常量的默认值由 test_packaging 的签名测试覆盖
        assert len(out) >= 12, f"标量默认值只解析出 {len(out)} 个，检查会空转"
    return out


def test_add_geo_axis_parameter_block_matches_signature():
    """手册写出的每个参数名与默认值都必须就是实现的签名。"""
    from inspect import signature

    import geophylo

    params = signature(geophylo.add_geo_axis).parameters
    checked = 0
    for name, documented in _documented_defaults("add_geo_axis").items():
        assert name in params, f"手册写了 `{name}=…`，但 add_geo_axis() 没有这个参数"
        actual = params[name].default
        if isinstance(documented, float) or isinstance(actual, float):
            assert float(actual) == float(documented), (
                f"{name} 默认值：手册 {documented} ≠ 代码 {actual}"
            )
        else:
            assert actual == documented, f"{name} 默认值：手册 {documented} ≠ 代码 {actual}"
        checked += 1
    assert checked >= 12, f"只比对了 {checked} 个参数，不足以覆盖参数表"


def test_documented_render_rules_match_the_library():
    """6 px 下限、label_size × 2 间距、rank 权重与 rank 次序：手册写的必须等于代码。"""
    from geophylo.render.linear import (
        MIN_TRACK_THICKNESS_PX,
        RANK_PRIORITY,
        RANK_WEIGHTS,
    )

    linear = (PROJECT_ROOT / "geophylo" / "render" / "linear.py").read_text(encoding="utf-8")
    for guide in _GUIDES:
        text = _guide_text(guide)
        assert MIN_TRACK_THICKNESS_PX == 6.0
        assert f"{MIN_TRACK_THICKNESS_PX:g} px" in text, "手册未写出当前 6 px 下限"
        assert "label_size × 2" in text
        assert 'min_gap_px = 2.0 * float(p["label_size"])' in linear, "间距规则已不再乘 2"
        # en 用 " / " 分隔、zh 用 "、…和" 分隔，因此逐 rank 抓取，不假设分隔符。
        line = next(
            (ln for ln in text.splitlines() if all(r in ln for r in RANK_WEIGHTS) and "0.8" in ln),
            None,
        )
        assert line, "手册未列出 rank 权重"
        documented = {}
        for rank in RANK_WEIGHTS:
            m = re.search(rf"{rank}[^\d\n]{{0,4}}([\d.]+)", line)
            assert m, f"手册的 rank 权重句里读不到 {rank}：{line[:80]!r}"
            documented[rank] = float(m.group(1))
        assert documented == RANK_WEIGHTS, f"rank 权重：手册 {documented} ≠ 代码 {RANK_WEIGHTS}"
        order = re.search(r"[（(]Eon > Era > Period > Epoch > Age[）)]", text)
        assert order, "手册未写出 rank 优先级次序"
        assert list(RANK_PRIORITY) == ["Eon", "Era", "Period", "Epoch", "Age"], RANK_PRIORITY
        assert sorted(RANK_PRIORITY.values()) == list(range(len(RANK_PRIORITY)))


def test_parameter_block_guard_fires_on_a_planted_mismatch():
    """守卫必须可失败：把参数块里的 label_size 改掉，解析结果就该与签名不符。"""
    from inspect import signature

    import geophylo

    block = _call_block(_guide_text(_GUIDES[0]), "add_geo_axis")
    real = signature(geophylo.add_geo_axis).parameters["label_size"].default

    def parse(text: str) -> float:
        pairs = {
            m.group("name"): ast.literal_eval(m.group("value").strip())
            for m in _PARAM_LINE.finditer(text)
        }
        assert len(pairs) >= 12, f"参数块只解析出 {len(pairs)} 项，反例会空转"
        return float(pairs["label_size"])

    assert parse(block) == float(real), "未篡改时参数块与签名不一致，主测试却报绿？"
    tampered = re.sub(r"^    label_size=[\d.]+,", "    label_size=9.5,", block, count=1, flags=re.M)
    assert tampered != block, "反例未写入，注入是空转"
    assert parse(tampered) != float(real), "篡改默认值后守卫仍不报警，检查是假的"


def _adr_texts() -> dict[str, str]:
    # 只取英文权威版；`*.zh.md` 是中文镜像，结构断言不适用。
    return {
        p.name: p.read_text(encoding="utf-8")
        for p in sorted((PROJECT_ROOT / "docs" / "adr").glob("ADR-*.md"))
        if not p.name.endswith(".zh.md")
    }


def test_every_adr_documents_its_rejected_alternatives():
    """仓库结构约定：每个不显然的选择都在 ADR 里连同被否方案一并记录，需机器校验。"""
    adrs = _adr_texts()
    assert len(adrs) == 5, f"docs/adr 下应有 ADR-1…5 五份，实得 {sorted(adrs)}"
    for name, text in adrs.items():
        assert "## Rejected alternatives" in text, f"{name} 缺少被否方案一节"
        body = text.split("## Rejected alternatives", 1)[1]
        assert body.strip().startswith("-"), f"{name} 的被否方案一节没有列出任何条目"


def test_release_notes_describe_a_two_step_procedure():
    """发布流程是"记录在 RELEASE.md 里的两步"；两步都得在文里。

    RELEASE.md 以英文为权威版本，因此锚定英文标题；中文镜像 RELEASE.zh-CN.md
    不参与本断言。
    """
    text = (PROJECT_ROOT / "RELEASE.md").read_text(encoding="utf-8")
    steps = re.findall(r"^## Step (\d+)", text, re.M)
    assert steps == ["1", "2"], f"RELEASE.md 的步骤标题应为 Step 1/Step 2，实得 {steps}"
    assert "manually" in text, "RELEASE.md 未说明这是维护者手动流程"


def test_boundary_value_domains_match_between_models_and_loader():
    """两个取值域在 geophylo/data/models.py 里声明；声明必须与运行时校验同源。"""
    from typing import get_args

    from geophylo.data import builtin, models

    assert set(get_args(models.BoundaryQualifier)) == builtin._VALID_QUALIFIERS
    assert set(get_args(models.BoundaryDefinition)) == builtin._VALID_DEFINITIONS


def test_documented_repository_structure_guard_fires_on_a_planted_mismatch():
    """三条结构约定都必须可失败：各造一个反例，判据就该不再成立。"""
    adrs = _adr_texts()
    assert all("## Rejected alternatives" in t for t in adrs.values())
    victim = next(iter(sorted(adrs)))
    gutted_adr = adrs[victim].replace("## Rejected alternatives", "## 其它说明", 1)
    assert gutted_adr != adrs[victim], "ADR 反例未写入，注入是空转"
    assert "## Rejected alternatives" not in gutted_adr

    release = (PROJECT_ROOT / "RELEASE.md").read_text(encoding="utf-8")
    steps = re.findall(r"^## Step (\d+)", release, re.M)
    assert steps == ["1", "2"], f"未篡改时 RELEASE 步骤标题就不是两步：{steps}"
    gutted_release = release.replace("## Step 2", "## Appendix B", 1)
    assert re.findall(r"^## Step (\d+)", gutted_release, re.M) != ["1", "2"], "RELEASE 反例是空转"

    from typing import get_args

    from geophylo.data import builtin, models

    quals = set(get_args(models.BoundaryQualifier))
    assert quals == builtin._VALID_QUALIFIERS
    assert quals | {"ratified"} != builtin._VALID_QUALIFIERS, "取值域反例不会让比对变红"

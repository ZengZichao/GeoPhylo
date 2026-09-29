"""数据契约、TTL 真值与校验测试（开发文档 5.6/5.7/7.2）。

三类断言刻意分开：

1. **契约/结构断言**：唯一性、年龄序、父包含、共享边界一致性——它们只看已解析
   出来的记录。
2. **哨兵断言**：记录数、rank 分布、qualifier 分布、若干用户文档引用的科学数值。
   哨兵值必须与 CHANGELOG 同步更新。
3. **TTL 真值断言**：用一套与 ``tools/build_snapshot.py`` 算法**不同**的块级 Turtle
   解析器，从 pinned 输入独立重推全部 358 个边界端点与记录级字段，再与出厂快照
   比对。两类错误在这一类断言下会立刻变红：``skos:note "uncertain"`` 被死分支
   丢弃、qualifier 优先级使 7 条 GSSP 界线的 ``~`` 不可表达。而"重跑生成器与出厂
   文件逐字节相同"那类套证（生成器自己不能证明自己做对了）在这里只作为可复现性
   检查，不作为正确性检查。
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import pytest

from geophylo.data.builtin import (
    canonical_payload_bytes,
    load_snapshot,
    validate_snapshot_payload,
)
from geophylo.exceptions import DataValidationError

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TTL_PATH = PROJECT_ROOT / "tools/source" / "ics-chart-v2026-06.5.ttl"

RANK_SLUGS = {
    "Eon": "eon",
    "Era": "era",
    "Period": "period",
    "Epoch": "epoch",
    "Age": "age",
    "Super-Eon": "super-eon",
    "Sub-Period": "sub-period",
}
STRUCTURAL_RANKS = {"Super-Eon", "Sub-Period"}
ALIAS_PRECEDENCE = {
    "Super-Eon": 0,
    "Eon": 1,
    "Era": 2,
    "Period": 3,
    "Sub-Period": 4,
    "Epoch": 5,
    "Age": 6,
}
# 7 条带 ``~`` 的 GSSP 界线；这些界线的 ``~`` 落在 numeric_estimate 上会被丢弃。
APPROXIMATE_GSSP_AGES = {237.0, 494.2, 497.0, 500.5, 504.5, 506.5, 635.0}
# 哨兵（versions: 2026/06 基线，snapshot_revision 1；更新快照时同步更新并说明）。
SENTINEL_2026 = {
    "total": 179,
    "endpoints": 358,
    "ranks": {
        "Age": 102,
        "Eon": 4,
        "Epoch": 38,
        "Era": 10,
        "Period": 22,
        "Sub-Period": 2,
        "Super-Eon": 1,
    },
    "qualifiers": {
        "approximate": 36,
        "constrained": 208,
        "defined": 97,
        "present": 5,
        "unknown": 12,
    },
}
# 2024/12 不复用 2026/06 的基准对象，否则更新后者会静默改掉前者。
SENTINEL_2024 = {
    "total": SENTINEL_2026["total"],
    "endpoints": SENTINEL_2026["endpoints"],
    "ranks": dict(SENTINEL_2026["ranks"]),
    "qualifiers": dict(SENTINEL_2026["qualifiers"]),
}


def _payload(snapshot: dict) -> list[dict]:
    return snapshot["intervals"]


def _endpoints(snapshot: dict) -> list[dict]:
    return [r[side] for r in _payload(snapshot) for side in ("older_boundary", "younger_boundary")]


def _qualifier_counts(snapshot: dict) -> dict[str, int]:
    counts: dict[str, int] = {}
    for boundary in _endpoints(snapshot):
        counts[boundary["qualifier"]] = counts.get(boundary["qualifier"], 0) + 1
    return counts


# --------------------------------------------------------------------------
# 独立的块级 Turtle 解析（不复用 tools/build_snapshot.py 的行状态机）
# --------------------------------------------------------------------------


def _ttl_blocks(text: str) -> list[tuple[str, str]]:
    """按 Turtle 约定切块：主体在第一列，块以单独一行的 ``.`` 结束。"""
    blocks: list[tuple[str, str]] = []
    subject: str | None = None
    body: list[str] = []
    for line in text.splitlines():
        if line.strip() == "":
            continue
        if not line[0].isspace():
            if subject is not None:
                blocks.append((subject, "\n".join(body)))
            subject = line.rstrip()
            if subject.endswith(" ."):
                subject = subject[:-2].rstrip()
            if subject == ".":
                subject = None
            body = []
            continue
        if line.strip() == ".":
            if subject is not None:
                blocks.append((subject, "\n".join(body)))
            subject = None
            body = []
            continue
        if subject is not None:
            body.append(line)
    if subject is not None:
        blocks.append((subject, "\n".join(body)))
    return blocks


_SUBJECT_NAME = re.compile(r"^([A-Za-z][\w-]*:[A-Za-z0-9_-]+)")
# `a skos:Concept ;` 独占一行；用终止符把 `a skos:ConceptScheme` 排除掉。
_IS_CONCEPT = re.compile(r"(?m)^\s{4}a\s+skos:Concept\s*;")
_HAS_BOUNDARY = re.compile(r"(?s)time:has(Beginning|End)\s*\[(.*?)(?:\s*\])")
_IN_MYA = re.compile(r"ischart:inMYA\s+(-?[0-9][0-9.eE+-]*)")
_MARGIN = re.compile(r"schema:marginOfError\s+(-?[0-9][0-9.eE+-]*)")
_NOTE = re.compile(r'skos:note\s+"([^"]*)"')
_RANK = re.compile(r"(?m)^\s*(?:gts:rank\s+)?rank:([A-Za-z-]+)\s*[,;]?\s*$")
_NOTATION = re.compile(r'skos:notation\s+"((?:[^"\\]|\\.)*)"')
_COLOR = re.compile(r'schema:color\s+"(#[0-9A-Fa-f]{6})"')
_BROADER = re.compile(r"(?m)^\s+skos:broader\s+(\S+)\s*(?:;|,)?\s*$")
_GSSP = re.compile(r"(?m)^\s+gts:ratifiedGSSP\s+true\s*;?\s*$")
_GSSA = re.compile(r"(?m)^\s+gts:ratifiedGSSA\s+true\s*;?\s*$")
_CHANGE_NOTE = re.compile(r'skos:changeNote\s+"((?:[^"\\]|\\.)*)"')


def _broader_local(concept: dict) -> str | None:
    """``skos:broader ischart:X`` 的局部名；无 broader 时为 None。"""
    broader = concept["broader"]
    if not broader or ":" not in broader:
        return None
    return broader.split(":", 1)[1]


_STAMP = re.compile(r"^(\d{4})-(\d{2}):")
_TRANSITION = re.compile(r"has(Beginning|End)\s+([0-9.]+)\s*->\s*([0-9.]+)")


def _pref_label_en(body: str) -> str | None:
    """只在 ``skos:prefLabel`` 的多值列表内找 @en（definition 里也有 @en）。"""
    start = re.search(r"(?m)^\s{4}skos:prefLabel\b", body)
    if not start:
        return None
    tail = body[start.end() :]
    # 多值列表的续行是 8 空格缩进；下一条四空格谓词标志列表结束。
    end = re.search(r"(?m)^ {4}\S", tail)
    section = tail[: end.start()] if end else tail
    m = re.search(r'"((?:[^"\\]|\\.)*)"@en\b', section)
    return json.loads(f'"{m.group(1)}"') if m else None


def ttl_concepts(text: str) -> dict[str, dict]:
    """独立解析 pinned TTL：``{局部名: {ranks, beginning, end, ...}}``。"""
    concepts: dict[str, dict] = {}
    for subject, body in _ttl_blocks(text):
        if not _IS_CONCEPT.search("\n" + body):
            continue
        local = _SUBJECT_NAME.match(subject)
        assert local is not None, subject
        name = local.group(1).split(":", 1)[1]
        boundaries: dict[str, dict] = {}
        for side, content in _HAS_BOUNDARY.findall(body):
            key = "beginning" if side == "Beginning" else "end"
            assert key not in boundaries, f"{name}: 重复的 {key}"
            values = _IN_MYA.findall(content)
            assert len(values) == 1, f"{name}.{key}: inMYA 值数量异常 {values}"
            margins = _MARGIN.findall(content)
            assert len(margins) <= 1, f"{name}.{key}: 多值 marginOfError {margins}"
            notes = _NOTE.findall(content)
            assert all(n == "uncertain" for n in notes), f"{name}.{key}: {notes}"
            boundaries[key] = {
                "mya": float(values[0]),
                "margin": float(margins[0]) if margins else None,
                "uncertain": bool(notes),
            }
        assert set(boundaries) == {"beginning", "end"}, f"{name}: {sorted(boundaries)}"
        concepts[name] = {
            "iri": local.group(1),
            "local": name,
            "ranks": _RANK.findall(body),
            "beginning": boundaries["beginning"],
            "end": boundaries["end"],
            "pref_en": _pref_label_en(body),
            "notation": (_NOTATION.findall(body) or [None])[0],
            "color": (_COLOR.findall(body) or [None])[0],
            "broader": (_BROADER.findall(body) or [None])[0],
            "gssp": bool(_GSSP.search(body)),
            "gssa": bool(_GSSA.search(body)),
            "change_notes": _CHANGE_NOTE.findall(body),
        }
    return concepts


def ttl_stats(concepts: dict[str, dict]) -> dict[str, int]:
    """独立口径的上游陈述计数（与快照 derivation.parse_stats 对照）。"""
    sides = ("beginning", "end")
    return {
        "concept_subjects": len(concepts),
        "ranked_concepts": sum(1 for c in concepts.values() if c["ranks"]),
        "records": sum(len(c["ranks"]) for c in concepts.values()),
        "boundary_values": sum(1 for c in concepts.values() for s in sides),
        "margin_values": sum(
            1 for c in concepts.values() for s in sides if c[s]["margin"] is not None
        ),
        "uncertain_notes": sum(1 for c in concepts.values() for s in sides if c[s]["uncertain"]),
        "change_notes": sum(len(c["change_notes"]) for c in concepts.values()),
    }


def _display_name(concept: dict) -> str:
    if concept["pref_en"]:
        return concept["pref_en"]
    # 与生成器同义但独立实现：在大写开头/数字边界处切分 IRI 局部名。
    tokens = re.findall(r"[A-Z]+(?=[A-Z][a-z])|[A-Z]?[a-z]+|[A-Z]+|[0-9]+", concept["local"])
    return " ".join(tokens)


def _interval_id(rank: str, name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return f"ics:{RANK_SLUGS[rank]}:{slug}"


def _merge_by_age(concepts: dict[str, dict]) -> dict[float, dict]:
    """按年龄合并共享边界：误差取最大、``~`` 取逻辑或（独立实现）。"""
    merged: dict[float, dict] = {}
    for concept in concepts.values():
        for side in ("beginning", "end"):
            node = concept[side]
            slot = merged.setdefault(node["mya"], {"margin": None, "uncertain": False})
            if node["margin"] is not None:
                slot["margin"] = (
                    max(slot["margin"], node["margin"]) if slot["margin"] else node["margin"]
                )
            slot["uncertain"] = slot["uncertain"] or node["uncertain"]
    return merged


def _definition_for(age: float, concepts: dict[str, dict]) -> str:
    if age == 0.0:
        return "present"
    definition = "numeric_estimate"
    for concept in concepts.values():
        if concept["beginning"]["mya"] != age:
            continue
        if concept["gssp"]:
            return "gssp"
        if concept["gssa"]:
            definition = "gssa"
    return definition


def _qualifier_for(definition: str, margin: float | None, uncertain: bool) -> str:
    """ADR-5 的 qualifier 规则（独立实现：``~`` 先于 GSSP/GSSA 判定）。"""
    if definition == "present":
        return "present"
    if uncertain:
        return "approximate"
    if definition in ("gssp", "gssa"):
        return "constrained" if margin is not None else "defined"
    if margin is not None:
        return "constrained"
    return "unknown"


def _apply_declared_repairs(concepts: dict[str, dict], repairs: list[dict], version: str) -> None:
    """把快照声明的确定性修复**逐条独立复核**后应用到 TTL 解析结果上。

    声明里任何一条与 TTL 原文对不上，就是"生成器改写了上游而出处说谎"。
    """
    for repair in repairs:
        concept = concepts.get(repair["concept"])
        assert concept is not None, f"修复指向未知概念：{repair}"
        side = repair["boundary"]
        node = concept[side]
        method = repair["method"]
        if method == "revert-change-note":
            assert version != "2026/06", f"基线快照不该有回退：{repair}"
            note = repair["change_note"]
            assert _STAMP.match(note), f"changeNote 无版本前缀：{note!r}"
            found = [
                (m.group(1), float(m.group(2)), float(m.group(3)))
                for m in _TRANSITION.finditer(note)
            ]
            assert "Beginning" if side == "beginning" else "End", "端点侧必须是 beginning/end"
            expected_side = "Beginning" if side == "beginning" else "End"
            assert (
                expected_side,
                repair["to_mya"],
                repair["from_mya"],
            ) in found, f"回退声明与 changeNote 不符：{repair} vs {found}"
            assert node["mya"] == repair["from_mya"], (
                f"{concept['local']}.{side}: 回退起点应为上游现值 "
                f"{repair['from_mya']}，实际 {node['mya']}"
            )
            node["mya"] = repair["to_mya"]
            if "margin_patch_mya" in repair:
                node["margin"] = repair["margin_patch_mya"]
        elif method == "snap-minority-rounding-variant":
            assert node["mya"] == repair["from_mya"], f"吸附起点与 TTL 不符：{repair}"
            # 独立复核吸附的正当性：被吸附的值在 TTL 里只出现一次，目标值出现在
            # 该概念父级的同一侧界线上（即父-子共用的那条界线），且相差 <= 0.05。
            occurrences = sum(
                1
                for c in concepts.values()
                for s in ("beginning", "end")
                if c[s]["mya"] == repair["from_mya"]
            )
            assert occurrences == 1, (
                f"被吸附值 {repair['from_mya']} 在 TTL 中出现 {occurrences} 次（应为孤例）"
            )
            parent = concepts.get((concept["broader"] or "").split(":")[1])
            assert parent is not None, f"{concept['local']}: 无父级却声明了结构吸附"
            assert parent[side]["mya"] == repair["to_mya"], (
                f"吸附目标应是父级同一侧的界线值 {parent[side]['mya']}，声明却是 {repair['to_mya']}"
            )
            assert abs(repair["to_mya"] - repair["from_mya"]) <= 0.05
            corroborated = sum(
                1
                for c in concepts.values()
                for s in ("beginning", "end")
                if c[s]["mya"] == repair["to_mya"]
            )
            assert corroborated >= 2, f"吸附目标 {repair['to_mya']} 未被佐证（{corroborated} 次）"
            node["mya"] = repair["to_mya"]
        elif method == "same-rank-overlap-children-union":
            assert node["mya"] == repair["from_mya"], f"调和起点与 TTL 不符：{repair}"
            # 独立复核：目标年龄必须等于"较老区间的全部子区间并集终点"，且搬动
            # 时属于旧年龄的误差/近似标记必须被清空。
            kids = [c for c in concepts.values() if _broader_local(c) == concept["local"]]
            assert kids, f"{concept['local']}: 无子区间却声明了子并集调和"
            assert min(c["end"]["mya"] for c in kids) == repair["to_mya"], (
                f"子区间并集终点与声明不符：{repair}"
            )
            if "cleared_margin_of_stale_age" in repair:
                assert node["margin"] == repair["cleared_margin_of_stale_age"], (
                    f"{concept['local']}.end 在 {repair['from_mya']} 的误差不符：{repair}"
                )
                survivors = [
                    other[s]["margin"]
                    for other in concepts.values()
                    for s in ("beginning", "end")
                    if other[s]["mya"] == repair["to_mya"] and other[s]["margin"] is not None
                ]
                assert survivors, f"{repair['to_mya']} Ma 处没有独立误差凭据"
                assert all(m > 0 for m in survivors)
                node["margin"] = None
            node["uncertain"] = False
            node["mya"] = repair["to_mya"]
        else:  # pragma: no cover - 新增修复方法时必须显式登记
            raise AssertionError(f"未知的修复方法：{method}")


def _rank_of(snapshot: dict, interval_id: str) -> str:
    return next(r["rank"] for r in _payload(snapshot) if r["id"] == interval_id)


def _expected_snapshot(snapshot: dict) -> dict[str, dict]:
    """从 pinned TTL 独立重推一份记录字典（含声明过的修复），用于逐字段比对。"""
    concepts = ttl_concepts(TTL_PATH.read_text(encoding="utf-8"))
    _apply_declared_repairs(
        concepts, snapshot["derivation"]["integrity_repairs"], str(snapshot["chart_version"])
    )
    parents = {c["local"]: _broader_local(c) for c in concepts.values()}
    merged = _merge_by_age(concepts)
    # 别名的 casefold 冲突消解（优先级在 ICS 图表确认前保留现状）。
    claimed: dict[str, str] = {}
    expected: dict[str, dict] = {}
    rows = []
    for concept in concepts.values():
        name = _display_name(concept)
        for rank in concept["ranks"]:
            rows.append((rank, _interval_id(rank, name), concept, name))
    for record_rank, record_id, concept, name in sorted(
        rows, key=lambda row: (ALIAS_PRECEDENCE[row[0]], row[1])
    ):
        alias = concept["notation"]
        kept = []
        if alias and alias.casefold() not in claimed:
            claimed[alias.casefold()] = record_id
            kept = [alias]
        age_old = concept["beginning"]["mya"]
        age_young = concept["end"]["mya"]
        parent_local = parents[concept["local"]]
        parent = concepts.get(parent_local) if parent_local else None

        def endpoint(age: float) -> dict:
            shared = merged[age]
            definition = _definition_for(age, concepts)
            return {
                "age_ma": age,
                "qualifier": _qualifier_for(definition, shared["margin"], shared["uncertain"]),
                "uncertainty_ma": shared["margin"],
                "definition": definition,
            }

        expected[record_id] = {
            "id": record_id,
            "name": name,
            "label": name,
            "aliases": kept,
            "rank": record_rank,
            "rank_class": "structural" if record_rank in STRUCTURAL_RANKS else "geochronologic",
            "parent_id": _interval_id(parent["ranks"][0], _display_name(parent))
            if parent
            else None,
            "status": "ratified"
            if (concept["gssp"] or concept["gssa"])
            else ("informal" if re.search(r"Cambrian (Stage|Series)", name) else "unknown"),
            "color": concept["color"],
            "older_boundary": endpoint(age_old),
            "younger_boundary": endpoint(age_young),
        }
    return expected


class TestVersionsIndex:
    def test_index_structure(self, versions_index):
        assert versions_index["baseline"] == "2026/06"
        assert set(versions_index["versions"]) == {"2024/12", "2026/06"}
        for meta in versions_index["versions"].values():
            assert meta["file"].startswith("ics_chart-")
            assert len(meta["payload_sha256"]) == 64
            assert len(meta["provenance_sha256"]) == 64

    def test_unknown_version_lists_available(self):
        with pytest.raises(DataValidationError, match="2024/12"):
            load_snapshot("1999/99")

    def test_payload_hash_matches_index(self, versions_index):
        for version, meta in versions_index["versions"].items():
            snapshot = load_snapshot(version)
            digest = hashlib.sha256(canonical_payload_bytes(snapshot["intervals"])).hexdigest()
            assert digest == meta["payload_sha256"] == snapshot["hash"]["payload_sha256"]

    def test_pinned_input_hash_is_the_vendored_file(self, versions_index):
        """pinned 输入不只是文字声明——versions.json 里的哈希必须等于磁盘字节。"""
        pinned = versions_index["pinned_input"]
        assert pinned["file"] == "tools/source/ics-chart-v2026-06.5.ttl"
        assert (PROJECT_ROOT / pinned["file"]).is_file()
        assert hashlib.sha256(TTL_PATH.read_bytes()).hexdigest() == pinned["sha256"]
        assert TTL_PATH.name == Path(pinned["file"]).name
        for meta in versions_index["versions"].values():
            snapshot = load_snapshot(meta["chart_version"])
            assert snapshot["source"]["source_sha256"] == pinned["sha256"]
            assert snapshot["derivation"]["pinned_input"]["sha256"] == pinned["sha256"]


class TestRecordContract:
    def test_required_keys_present(self, snapshot_payload):
        required = {
            "id",
            "source_iri",
            "name",
            "label",
            "aliases",
            "rank",
            "rank_class",
            "parent_id",
            "source_parent_id",
            "status",
            "color",
            "older_boundary",
            "younger_boundary",
        }
        for record in _payload(snapshot_payload):
            missing = required - set(record)
            assert not missing, f"{record['id']}: 缺少 {missing}"

    def test_boundary_required_keys(self, snapshot_payload):
        for record in _payload(snapshot_payload):
            for side in ("older_boundary", "younger_boundary"):
                assert {
                    "age_ma",
                    "qualifier",
                    "uncertainty_ma",
                    "definition",
                    "source_iri",
                } <= set(record[side])

    def test_schema_and_metadata(self, snapshot_payload):
        assert snapshot_payload["schema_version"] == 1
        assert snapshot_payload["chart_version"] == "2026/06"
        assert snapshot_payload["snapshot_revision"] == 1
        assert isinstance(snapshot_payload["snapshot_revision"], int)
        assert snapshot_payload["license"]["spdx"] == "CC-BY-4.0"
        assert snapshot_payload["source"]["kind"] == "ics-rdf"
        # source 块必须真的带上 PROVENANCE.md 所声称的 tag。
        assert set(snapshot_payload["source"]) == {
            "kind",
            "url",
            "commit",
            "tag",
            "source_sha256",
            "vendored_copy",
        }
        assert snapshot_payload["source"]["tag"] == "v2026-06.5"

    def test_sentinel_counts(self, snapshot_payload, snapshot_payload_2024):
        for snapshot, sentinel in (
            (snapshot_payload, SENTINEL_2026),
            (snapshot_payload_2024, SENTINEL_2024),
        ):
            records = _payload(snapshot)
            assert len(records) == sentinel["total"]
            by_rank: dict[str, int] = {}
            for r in records:
                by_rank[r["rank"]] = by_rank.get(r["rank"], 0) + 1
            assert by_rank == sentinel["ranks"]
            assert _qualifier_counts(snapshot) == sentinel["qualifiers"]
            assert len(_endpoints(snapshot)) == sentinel["endpoints"]


class TestTtlGroundTruth:
    """以上游 TTL 为真值，独立重推全部 358 个端点与记录级字段。"""

    def test_upstream_statement_counts_match_snapshot_declaration(self):
        """无静默丢行：快照自述的上游陈述计数 == 独立计数。"""
        stats = ttl_stats(ttl_concepts(TTL_PATH.read_text(encoding="utf-8")))
        declared = load_snapshot("2026/06")["derivation"]["parse_stats"]
        assert declared == stats
        assert stats["concept_subjects"] == 178  # `a skos:Concept` 主体（含 Pridoli 双 rank）
        assert stats["boundary_values"] == 356  # 178 x 2，与 179 条记录的差异只来自 Pridoli
        assert stats["records"] == 179
        assert stats["uncertain_notes"] == 36
        assert stats["margin_values"] == 206

    @pytest.mark.parametrize("version", ["2026/06", "2024/12"])
    def test_every_endpoint_re_derives_from_the_ttl(self, version):
        snapshot = load_snapshot(version)
        expected = _expected_snapshot(snapshot)
        compared = 0
        for record in _payload(snapshot):
            want = expected[record["id"]]
            for side in ("older_boundary", "younger_boundary"):
                got, exp = record[side], want[side]
                assert set(exp) <= set(got), f"{record['id']}.{side} 键不符"
                for field in ("age_ma", "qualifier", "uncertainty_ma", "definition"):
                    assert got[field] == exp[field], (
                        f"{version} {record['id']}.{side}.{field}："
                        f"出厂 {got[field]!r} vs TTL 独立重推 {exp[field]!r}"
                    )
                compared += 1
        assert compared == SENTINEL_2026["endpoints"]  # 358 个端点全部被真正比较过

    @pytest.mark.parametrize("version", ["2026/06", "2024/12"])
    def test_record_level_fields_match_the_ttl(self, version):
        """零失配字段：id/name/rank/parent/status/color/aliases。"""
        snapshot = load_snapshot(version)
        expected = _expected_snapshot(snapshot)
        mismatches: list[str] = []
        for record in _payload(snapshot):
            want = expected[record["id"]]
            for field in (
                "name",
                "label",
                "rank",
                "rank_class",
                "parent_id",
                "status",
                "color",
                "aliases",
            ):
                if record[field] != want[field]:
                    mismatches.append(
                        f"{record['id']}.{field}: {record[field]!r} != {want[field]!r}"
                    )
            if sorted(record) != sorted(set(record) | set(want)):
                mismatches.append(f"{record['id']} 字段集不符")
        assert mismatches == []
        assert {r["id"] for r in _payload(snapshot)} == set(expected)

    def test_only_the_documented_ages_differ_from_upstream(self):
        """全库仅有的两处 age_ma 改写，必须逐条被 derivation 声明。"""
        concepts = ttl_concepts(TTL_PATH.read_text(encoding="utf-8"))
        snapshot = load_snapshot("2026/06")
        upstream: dict[str, set[float]] = {}
        for concept in concepts.values():
            for rank in concept["ranks"]:
                upstream.setdefault(_interval_id(rank, _display_name(concept)), set()).update(
                    {concept["beginning"]["mya"], concept["end"]["mya"]}
                )
        declared = {
            (r["concept"], r["boundary"], r["from_mya"], r["to_mya"])
            for r in snapshot["derivation"]["integrity_repairs"]
            if r["method"] == "snap-minority-rounding-variant"
        } | {
            (r["concept"], r["boundary"], r["from_mya"], r["to_mya"])
            for r in snapshot["derivation"]["integrity_repairs"]
            if r["method"] == "same-rank-overlap-children-union"
        }
        assert declared == {
            ("Aquitanian", "beginning", 23.03, 23.04),
            ("Ludlow", "end", 419.62, 422.7),
        }, "吸附/调和声明与 TTL 的实际差异与披露不符：需人工复核并更新出处披露"
        for record in _payload(snapshot):
            assert {record["older_boundary"]["age_ma"], record["younger_boundary"]["age_ma"]} <= (
                upstream[record["id"]] | {23.04, 422.7}
            ), record["id"]

    def test_every_upstream_approximate_marker_is_expressible(self):
        """36 条上游 ``~`` 全部落到 qualifier=approximate。"""
        concepts = ttl_concepts(TTL_PATH.read_text(encoding="utf-8"))
        merged = _merge_by_age(concepts)
        ages_with_marker = {age for age, slot in merged.items() if slot["uncertain"]}
        snapshot = load_snapshot("2026/06")
        approximate = {b["age_ma"] for b in _endpoints(snapshot) if b["qualifier"] == "approximate"}
        assert ages_with_marker == approximate
        assert sum(1 for b in _endpoints(snapshot) if b["qualifier"] == "approximate") == 36
        # 那 7 条 GSSP 界线：既是 approximate，又确实由 GSSP 定义（正交性成立）。
        gssp_approximate = {
            b["age_ma"]
            for b in _endpoints(snapshot)
            if b["qualifier"] == "approximate" and b["definition"] == "gssp"
        }
        assert gssp_approximate == APPROXIMATE_GSSP_AGES
        assert {237.0, 494.2, 497.0, 500.5, 504.5, 506.5, 635.0} == APPROXIMATE_GSSP_AGES

    def test_no_upstream_marker_survives_as_exactly_defined(self):
        """回归守卫：若 qualifier 优先级退回旧顺序，这条必然变红。"""
        snapshot = load_snapshot("2026/06")
        for age in APPROXIMATE_GSSP_AGES:
            endpoints = [b for b in _endpoints(snapshot) if b["age_ma"] == age]
            assert endpoints
            for boundary in endpoints:
                assert boundary["qualifier"] == "approximate", (age, boundary)
                assert boundary["qualifier"] != "defined"
                assert boundary["uncertainty_ma"] is None  # 上游此处无 ±

    def test_approximate_never_means_missing_margin(self):
        """``~`` 与 ``±`` 可共存：approximate 端点若上游给了误差，误差必须保留。"""
        concepts = ttl_concepts(TTL_PATH.read_text(encoding="utf-8"))
        merged = _merge_by_age(concepts)
        snapshot = load_snapshot("2026/06")
        for boundary in _endpoints(snapshot):
            if boundary["qualifier"] != "approximate":
                continue
            assert merged[boundary["age_ma"]]["uncertain"] is True
            assert boundary["uncertainty_ma"] == merged[boundary["age_ma"]]["margin"]

    def test_ludlow_margin_was_not_carried_with_the_moved_age(self):
        """419.62 的 ±1.36 不得跟到 422.7；422.7 的 ±1.6 另有独立凭据。"""
        snapshot = load_snapshot("2026/06")
        at_422 = [b for b in _endpoints(snapshot) if b["age_ma"] == 422.7]
        assert at_422
        assert {b["uncertainty_ma"] for b in at_422} == {1.6}
        at_419 = [b for b in _endpoints(snapshot) if b["age_ma"] == 419.62]
        assert {b["uncertainty_ma"] for b in at_419} == {1.36}
        repair = [
            r
            for r in snapshot["derivation"]["integrity_repairs"]
            if r["method"] == "same-rank-overlap-children-union"
        ]
        assert len(repair) == 1
        assert repair[0]["cleared_margin_of_stale_age"] == 1.36
        assert repair[0]["concept"] == "Ludlow"
        # 误差调和不得制造上游没有的误差冲突（写一条"1.6 vs 1.36 取最大值"就是伪造）。
        log = json.loads(
            (PROJECT_ROOT / "tools/build-logs/ics_chart-2026-06.log.json").read_text("utf-8")
        )
        assert log["warnings"] == []

    def test_cretaceous_base_has_no_upstream_margin(self):
        """66.0 Ma 无误差是**上游确实没写**，不是解析器漏读。"""
        concepts = ttl_concepts(TTL_PATH.read_text(encoding="utf-8"))
        paleogene = concepts["Paleogene"]
        assert paleogene["beginning"]["mya"] == 66.0
        assert paleogene["beginning"]["margin"] is None
        snapshot = load_snapshot("2026/06")
        record = next(r for r in _payload(snapshot) if r["id"] == "ics:period:paleogene")
        assert record["older_boundary"]["uncertainty_ma"] is None
        assert record["older_boundary"]["qualifier"] == "defined"
        # 误差缺失绝不被伪造成 0.0。
        assert not any(b["uncertainty_ma"] == 0.0 for b in _endpoints(snapshot))

    def test_derived_names_correspond_to_concepts_without_english_label(self):
        """name/id 由 IRI 局部名推导的记录，恰好是上游无 @en prefLabel 的那些。"""
        concepts = ttl_concepts(TTL_PATH.read_text(encoding="utf-8"))
        snapshot = load_snapshot("2026/06")
        declared = {d["concept"].split(":")[1] for d in snapshot["derivation"]["derived_labels"]}
        without_en = {name for name, c in concepts.items() if not c["pref_en"]}
        assert declared == without_en
        assert without_en, "推导清单为空，断言将失去意义"
        for record in _payload(snapshot):
            local = record["source_iri"].rsplit("/", 1)[-1]
            if local in without_en:
                assert record["name"] == _display_name(concepts[local])
                assert "@" not in (concepts[local]["pref_en"] or "")

    def test_dropped_aliases_are_exactly_the_casefold_collisions(self):
        """被去重丢掉的短代码必须逐条记录，且不含任何未记录的丢失。"""
        concepts = ttl_concepts(TTL_PATH.read_text(encoding="utf-8"))
        snapshot = load_snapshot("2026/06")
        notes = {}
        for concept in concepts.values():
            for rank in concept["ranks"]:
                if concept["notation"]:
                    notes[_interval_id(rank, _display_name(concept))] = concept["notation"]
        claimed: dict[str, str] = {}
        expected_dropped: set[tuple[str, str]] = set()
        expected_kept: dict[str, str] = {}
        for interval_id, notation in sorted(
            notes.items(),
            key=lambda item: (
                ALIAS_PRECEDENCE[_rank_of(snapshot, item[0])],
                item[0],
            ),
        ):
            if notation.casefold() in claimed:
                expected_dropped.add((interval_id, notation))
            else:
                claimed[notation.casefold()] = interval_id
                expected_kept[interval_id] = notation
        recorded = {(d["id"], d["alias"]) for d in snapshot["derivation"]["dropped_aliases"]}
        assert recorded == expected_dropped
        assert len(recorded) == 35
        # 每条被丢弃的代码，其归属者必须确实持有该代码（折叠后同值）。
        shipped_aliases = {r["id"]: r["aliases"] for r in _payload(snapshot)}
        for interval_id, notation in recorded:
            owner = next(
                d["claimed_by"]
                for d in snapshot["derivation"]["dropped_aliases"]
                if d["id"] == interval_id and d["alias"] == notation
            )
            assert any(a.casefold() == notation.casefold() for a in shipped_aliases[owner]), (
                interval_id,
                owner,
            )
            assert interval_id not in shipped_aliases or shipped_aliases[interval_id] == []
        assert {i for i, a in expected_kept.items()} - {
            i for i in shipped_aliases if shipped_aliases[i]
        } == set()

    def test_shared_boundary_marker_propagates_to_every_projection(self):
        """一处 ``~`` 会投影到相邻两条记录：两处必须都是 approximate。"""
        snapshot = load_snapshot("2026/06")
        by_age: dict[float, set[str]] = {}
        for boundary in _endpoints(snapshot):
            by_age.setdefault(boundary["age_ma"], set()).add(boundary["qualifier"])
        for age, qualifiers in by_age.items():
            assert len(qualifiers) == 1, (age, qualifiers)


class TestIntegrity:
    def test_strict_age_ordering(self, snapshot_payload):
        for record in _payload(snapshot_payload):
            older = record["older_boundary"]["age_ma"]
            younger = record["younger_boundary"]["age_ma"]
            assert older > younger, f"{record['id']} 零宽或反向"

    def test_unique_ids_and_names(self, snapshot_payload):
        ids = [r["id"] for r in _payload(snapshot_payload)]
        assert len(ids) == len(set(ids))
        name_rank = [(r["name"].casefold(), r["rank"]) for r in _payload(snapshot_payload)]
        assert len(name_rank) == len(set(name_rank))

    def test_alias_casefold_unique(self, snapshot_payload):
        aliases: dict[str, str] = {}
        for r in _payload(snapshot_payload):
            for alias in r["aliases"]:
                folded = alias.casefold()
                assert folded not in aliases, f"alias {alias!r} 冲突"
                aliases[folded] = r["id"]

    def test_parent_containment_and_existence(self, snapshot_payload):
        by_id = {r["id"]: r for r in _payload(snapshot_payload)}
        for record in _payload(snapshot_payload):
            if record["parent_id"] is None:
                continue
            parent = by_id[record["parent_id"]]
            assert parent["older_boundary"]["age_ma"] >= record["older_boundary"]["age_ma"] - 1e-9
            assert (
                parent["younger_boundary"]["age_ma"] <= record["younger_boundary"]["age_ma"] + 1e-9
            )

    def test_shared_boundary_consistency(self, snapshot_payload):
        shared: dict[float, tuple] = {}
        for record in _payload(snapshot_payload):
            for side in ("older_boundary", "younger_boundary"):
                b = record[side]
                key = round(b["age_ma"], 6)
                signature = (b["age_ma"], b["qualifier"], b["uncertainty_ma"], b["definition"])
                if key in shared:
                    assert shared[key] == signature, f"{record['id']} 共享边界不一致"
                shared.setdefault(key, signature)

    def test_children_union_covers_parents(self, snapshot_payload):
        by_id = {r["id"]: r for r in _payload(snapshot_payload)}
        children: dict[str, list] = {}
        for r in _payload(snapshot_payload):
            if r["parent_id"]:
                children.setdefault(r["parent_id"], []).append(r)
        tol = 1e-9
        for parent_id, kids in children.items():
            if len(kids) < 2:
                continue
            parent = by_id[parent_id]
            merged: list[list[float]] = []
            for kid in sorted(kids, key=lambda r: r["older_boundary"]["age_ma"], reverse=True):
                lo, hi = kid["older_boundary"]["age_ma"], kid["younger_boundary"]["age_ma"]
                if merged and lo >= merged[-1][1] - tol:
                    merged[-1][1] = min(merged[-1][1], hi)
                else:
                    merged.append([lo, hi])
            covered = sum(a - b for a, b in merged)
            span = parent["older_boundary"]["age_ma"] - parent["younger_boundary"]["age_ma"]
            assert covered == pytest.approx(span, abs=tol)

    def test_colors_valid_hex(self, snapshot_payload):
        for record in _payload(snapshot_payload):
            color = record["color"]
            assert color.startswith("#") and len(color) == 7
            int(color[1:], 16)  # 有效十六进制

    def test_boundary_enum_domains(self, snapshot_payload):
        qualifiers = {"defined", "constrained", "approximate", "present", "unknown"}
        definitions = {"gssp", "gssa", "numeric_estimate", "present", "unknown"}
        for record in _payload(snapshot_payload):
            for side in ("older_boundary", "younger_boundary"):
                b = record[side]
                assert b["qualifier"] in qualifiers
                assert b["definition"] in definitions

    def test_approximate_qualifier_reaches_the_public_model(self):
        """加载器不只接受 approximate，还要把它送到 ``Interval`` 上。"""
        from geophylo.data.models import Interval

        intervals: list[Interval] = validate_snapshot_payload(load_snapshot("2026/06"))
        flagged = [i for i in intervals if i.has_approximate_boundary]
        assert len({i.id for i in flagged}) >= 20
        cambrian_2 = next(i for i in intervals if i.id == "ics:age:cambrian-stage-2")
        assert cambrian_2.older_boundary.qualifier == "approximate"
        assert cambrian_2.older_boundary.is_numeric  # ~ 是数值的性质，不是"无信息"
        assert cambrian_2.older_boundary.effective_uncertainty is None
        carniann = next(i for i in intervals if i.id == "ics:age:carnian")
        assert carniann.older_boundary.qualifier == "approximate"
        assert carniann.older_boundary.is_defined  # definition 轴仍是 gssp（正交）
        # 兼容别名仍然可用，但已标记废弃。
        with pytest.warns(DeprecationWarning, match="has_approximate_boundary"):
            assert cambrian_2.is_approximate_any()

    def test_present_youngest_and_structural_nodes(self, snapshot_payload):
        records = _payload(snapshot_payload)
        present = [r for r in records if r["younger_boundary"]["definition"] == "present"]
        assert present, "缺少 present 最年轻边界"
        structural = [r for r in records if r["rank_class"] == "structural"]
        assert {r["name"] for r in structural} == {"Precambrian", "Mississippian", "Pennsylvanian"}


class TestDocStatedValues:
    """开发文档明确给出的科学数值（来自基线快照，不硬编码到业务代码）。"""

    def test_doc_stated_golden_values(self, snapshot_payload):
        by_name = {r["name"]: r for r in _payload(snapshot_payload)}
        # 4.1：find_by_age(66.0) → Paleogene 的锚点。
        paleogene = by_name["Paleogene"]
        assert paleogene["older_boundary"]["age_ma"] == pytest.approx(66.0)
        assert paleogene["rank"] == "Period"
        # 5.6：Phanerozoic 538.8 ±0.6 → present。
        phanerozoic = by_name["Phanerozoic"]
        assert phanerozoic["older_boundary"]["age_ma"] == pytest.approx(538.8)
        assert phanerozoic["older_boundary"]["uncertainty_ma"] == pytest.approx(0.6)
        assert phanerozoic["younger_boundary"]["definition"] == "present"
        # 5.6：Jurassic 201.4 ±0.2 → 143.1 ±0.6（数值估计，非 ~ 近似）。
        jurassic = by_name["Jurassic"]
        assert jurassic["older_boundary"]["age_ma"] == pytest.approx(201.4)
        assert jurassic["older_boundary"]["uncertainty_ma"] == pytest.approx(0.2)
        assert jurassic["younger_boundary"]["age_ma"] == pytest.approx(143.1)
        assert jurassic["younger_boundary"]["uncertainty_ma"] == pytest.approx(0.6)
        assert jurassic["younger_boundary"]["definition"] == "numeric_estimate"
        assert jurassic["younger_boundary"]["qualifier"] == "constrained"
        # 5.6：Cambrian 顶界（Ordovician 底界）486.85 ±1.5。
        ordovician = by_name["Ordovician"]
        assert ordovician["older_boundary"]["age_ma"] == pytest.approx(486.85)
        assert ordovician["older_boundary"]["uncertainty_ma"] == pytest.approx(1.5)
        # 5.7：2026/06 相对 2024/12 的三处边界更新。
        anisian = by_name["Anisian"]
        assert anisian["older_boundary"]["age_ma"] == pytest.approx(247.0)
        wuchiapingian = by_name["Wuchiapingian"]
        assert wuchiapingian["older_boundary"]["age_ma"] == pytest.approx(259.857)
        assert wuchiapingian["older_boundary"]["uncertainty_ma"] == pytest.approx(0.084)

    def test_2024_snapshot_has_reverted_values(self, snapshot_payload_2024):
        by_name = {r["name"]: r for r in _payload(snapshot_payload_2024)}
        assert by_name["Anisian"]["older_boundary"]["age_ma"] == pytest.approx(246.7)
        assert by_name["Olenekian"]["older_boundary"]["age_ma"] == pytest.approx(249.9)
        wuchiapingian = by_name["Wuchiapingian"]
        assert wuchiapingian["older_boundary"]["age_ma"] == pytest.approx(259.51)
        assert wuchiapingian["older_boundary"]["uncertainty_ma"] == pytest.approx(0.21)


class TestBuilderMarkerHandling:
    """单元级守卫：用合成 TTL 片段直接喂解析器。"""

    @staticmethod
    def _builder():
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "build_snapshot_unit", PROJECT_ROOT / "tools" / "build_snapshot.py"
        )
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    FRAGMENT = """@prefix ischart: <http://resource.geosciml.org/classifier/ics/ischart/> .

ischart:FakeStage
    a skos:Concept ;
    gts:rank rank:Age ;
    gts:ratifiedGSSP true ;
    skos:broader ischart:FakeEpoch ;
    skos:notation "f1"^^ischart:ccgmShortCode ;
    skos:prefLabel "Fake Stage"@en ;
    schema:color "#123456"^^ischart:RGBHex ;
    time:hasBeginning
        [
            ischart:inMYA 100.5 ;
            skos:note "uncertain" ;
        ] ;
    time:hasEnd
        [
            ischart:inMYA 95.25 ;
            schema:marginOfError 0.5 ;
        ] ;
.
"""

    def test_uncertain_note_inside_blank_node_is_captured(self):
        """直接复现守卫：谓词已被吃掉，只剩字面量时也必须命中。"""
        module = self._builder()
        concepts = module.parse_ttl(self.FRAGMENT)
        assert concepts["FakeStage"]["beginning"]["uncertain"] is True
        assert concepts["FakeStage"]["end"]["uncertain"] is False
        assert concepts["FakeStage"]["end"]["margin"] == 0.5

    def test_qualifier_precedence_keeps_approximate_for_gssp_boundaries(self):
        """直接复现守卫：GSSP + 无误差 + 有 ``~`` → approximate。"""
        module = self._builder()
        assert module.boundary_qualifier(500.5, "gssp", None, True) == "approximate"
        assert module.boundary_qualifier(500.5, "gssp", None, False) == "defined"
        assert module.boundary_qualifier(500.5, "gssp", 0.4, True) == "approximate"
        assert module.boundary_qualifier(500.5, "numeric_estimate", 0.4, False) == "constrained"
        assert module.boundary_qualifier(500.5, "numeric_estimate", None, False) == "unknown"

    def test_wrapped_value_line_is_accepted(self):
        module = self._builder()
        wrapped = self.FRAGMENT.replace(
            "            ischart:inMYA 100.5 ;",
            "            ischart:inMYA\n                100.5 ;",
        )
        concepts = module.parse_ttl(wrapped)
        assert concepts["FakeStage"]["beginning"]["mya"] == 100.5

    @pytest.mark.parametrize(
        "tampered, expected",
        [
            ('skos:note "approximate" ;', "未预期的 skos:note 值"),
            ("ischart:inMYA 100.5 , 100.6 ;", "无法解析为十进制数"),
            ("ischart:inMYA foo ;", "无法解析为十进制数"),
            ('schema:certainty "high" ;', "未预期的端点谓词"),
        ],
    )
    def test_unparseable_or_unknown_boundary_forms_fail(self, tampered, expected):
        """换写法必须显式失败，绝不静默产出可通过校验的残缺快照。"""
        module = self._builder()
        line = (
            '            skos:note "uncertain" ;'
            if tampered.startswith("skos")
            else (
                "            schema:marginOfError 0.5 ;"
                if tampered.startswith("schema")
                else "            ischart:inMYA 100.5 ;"
            )
        )
        broken = self.FRAGMENT.replace(line, f"            {tampered}")
        with pytest.raises(module.BuildError, match=expected):
            module.parse_ttl(broken)

    def test_concept_missing_boundary_or_rank_fails(self):
        module = self._builder()
        no_end = self.FRAGMENT.replace(
            """    time:hasEnd
        [
            ischart:inMYA 95.25 ;
            schema:marginOfError 0.5 ;
        ] ;
""",
            "",
        )
        with pytest.raises(module.BuildError, match="time:hasEnd"):
            module.select_concepts(module.parse_ttl(no_end))
        no_rank = self.FRAGMENT.replace("    gts:rank rank:Age ;\n", "")
        with pytest.raises(module.BuildError, match="无 gts:rank"):
            module.select_concepts(module.parse_ttl(no_rank))
        odd_rank = self.FRAGMENT.replace("gts:rank rank:Age ;", "gts:rank rank:Chronozone ;")
        with pytest.raises(module.BuildError, match="rank 不在白名单"):
            module.select_concepts(module.parse_ttl(odd_rank))


class TestValidatorRejects:
    @staticmethod
    def _snapshot_with(records):
        return {
            "schema_version": 1,
            "chart_version": "t",
            "snapshot_revision": 1,
            "generator": {"name": "t", "version": "0"},
            "source": {"kind": "ics-rdf", "url": "", "commit": "", "source_sha256": ""},
            "license": {"spdx": "CC-BY-4.0", "file": "", "attribution": "", "citation": ""},
            "hash": {"scope": "", "algorithm": "sha256", "payload_sha256": ""},
            "intervals": records,
        }

    def _base_record(self):
        return {
            "id": "ics:period:x",
            "source_iri": None,
            "name": "X",
            "label": "X",
            "aliases": [],
            "rank": "Period",
            "rank_class": "geochronologic",
            "parent_id": None,
            "source_parent_id": None,
            "status": "ratified",
            "color": "#123456",
            "older_boundary": {
                "age_ma": 10.0,
                "qualifier": "constrained",
                "uncertainty_ma": 0.2,
                "definition": "gssp",
                "source_iri": None,
            },
            "younger_boundary": {
                "age_ma": 5.0,
                "qualifier": "approximate",
                "uncertainty_ma": 0.2,
                "definition": "numeric_estimate",
                "source_iri": None,
            },
        }

    def test_zero_width_rejected(self):
        record = self._base_record()
        record["younger_boundary"]["age_ma"] = 10.0
        with pytest.raises(DataValidationError, match="严格大于"):
            validate_snapshot_payload(self._snapshot_with([record]))

    def test_negative_age_rejected(self):
        record = self._base_record()
        record["younger_boundary"]["age_ma"] = -1.0
        with pytest.raises(DataValidationError, match="非负"):
            validate_snapshot_payload(self._snapshot_with([record]))

    def test_bad_color_rejected(self):
        record = self._base_record()
        record["color"] = "red"
        with pytest.raises(DataValidationError, match="颜色"):
            validate_snapshot_payload(self._snapshot_with([record]))

    def test_missing_key_rejected(self):
        record = self._base_record()
        del record["source_parent_id"]  # 键必须显式出现
        with pytest.raises(DataValidationError, match="必需键"):
            validate_snapshot_payload(self._snapshot_with([record]))

    def test_unknown_parent_rejected(self):
        record = self._base_record()
        record["parent_id"] = "ics:period:missing"
        with pytest.raises(DataValidationError, match="parent_id"):
            validate_snapshot_payload(self._snapshot_with([record]))

    def test_qualifier_outside_domain_rejected(self):
        """枚举域仍在把关：新增 qualifier 取值必须先改模型，不能悄悄塞进数据。"""
        record = self._base_record()
        record["younger_boundary"]["qualifier"] = "defined_approximate"
        with pytest.raises(DataValidationError, match="qualifier"):
            validate_snapshot_payload(self._snapshot_with([record]))

    def test_hash_mismatch_rejected(self, snapshot_payload):
        broken = json.loads(json.dumps(snapshot_payload))
        broken["intervals"][0]["name"] = "Tampered"
        with pytest.raises(DataValidationError, match="payload_sha256"):
            from geophylo.data.builtin import SnapshotBackend

            SnapshotBackend(broken)

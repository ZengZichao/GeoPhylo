#!/usr/bin/env python3
"""ICS RDF (Turtle) -> geophylo snapshot JSON 的确定性生成器。

契约（开发文档 5.6/5.7）：

- 同一输入文件必须产出逐字节相同的 JSON；生成过程不读当前时间。
- 抓取时间 ``retrieved_at`` 只能通过 ``--retrieved-at`` 显式传入，仅写入生成日志，
  绝不写入快照 JSON。
- ``hash.payload_sha256`` 定义为对 ``intervals`` 数组做规范化 JSON 序列化
  （键排序、紧凑分隔符、UTF-8）后的 SHA-256；``hash.provenance_sha256`` 覆盖
  除 ``intervals`` 与 ``hash`` 之外的全部顶层元数据，因此「只改版本标签/来源块」
  也会被独立哈希捕获（两把哈希互相独立）。
- 上游 ``skos:note "uncertain"``（图表上的 ``~``）必须被捕获并进入
  ``qualifier="approximate"``；任何 ``inMYA``/``marginOfError`` 字面量无法解析、
  任何 ``skos:Concept`` 主体缺 rank 或缺 ``hasBeginning``/``hasEnd`` 一律显式
  失败，绝不静默产出残缺快照。
- ``--to 2024/12`` 时，按上游 ``skos:changeNote``（"2026-06: hasBeginning X -> Y"）
  把**晚于**该版本的所有已登记修订回退，并应用文档记录的 Wuchiapingian 误差补丁
  （2024/12 为 259.51 ±0.21，2026/06 为 259.857 ±0.084）。``--to`` 与
  ``--chart-version`` 必须一致，且目标必须是 ``DERIVED_SNAPSHOTS`` 中登记过的
  版本；这样的快照不是独立抓取的上游归档，其推导关系由推导时的**实际**回退条数
  写进 ``versions.json`` 的 ``derived_from`` 字段（见
  ``geophylo/data/snapshots/PROVENANCE.md``）。
- 对上游可被确定性证明的瑕疵（同一条界线的少数派舍入值、同 rank 重叠）的修复
  以「结构等值类」（父-子-兄弟）为判据，而不是全局出现次数；修复清单写入
  快照顶层 ``derivation.integrity_repairs``（``intervals`` 之外，不影响 payload
  哈希），并在吸附/调和之后重新校验父子时间包含。
- ``--diff-with`` 在写完快照后调用 ``tools/make_diff.py`` 的同一套代码，把新
  快照与既有快照之间逐字段的机器可读 diff 写到快照目录。

用法示例::

    python tools/build_snapshot.py \\
        --ttl tools/source/ics-chart-v2026-06.5.ttl \\
        --chart-version 2026/06 --tag v2026-06.5 \\
        --commit 44d1043ecf295cce1be03b3fc5fa95ca65fe770b \\
        --source-sha256 0158959e8fdae2a8bdbb14ca3e424d2370362cd8dfc8af86e7be73c74368b355 \\
        --retrieved-at 2026-09-11T00:00:00Z \\
        --out geophylo/data/snapshots/ics_chart-2026-06.json

    python tools/build_snapshot.py ... --chart-version 2024/12 --to 2024/12 \\
        --out geophylo/data/snapshots/ics_chart-2024-12.json

    python tools/build_snapshot.py ... --out <新快照> --write-index \\
        --diff-with 2024/12   # 同时生成 diff-2024-12_to_<新版本>.json

生成日志默认写入 ``<仓库根>/tools/build-logs/<快照名>.log.json``（与
``docs/data-policy.md`` 的命名规范一致；这些日志是被跟踪的出处工件，
``.gitignore`` 不得忽略它们）。
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
import sys
from collections import Counter
from collections.abc import Mapping
from pathlib import Path

GENERATOR_NAME = "geophylo-snapshot"
# 提取语义（解析、调和、schema）的版本，随快照文件一起发布。只有当*提取语义*
# 变化时才抬升；包版本抬升本身不改这个标签。
GENERATOR_VERSION = "0.1.0"
SCHEMA_VERSION = 1
# 同一 chart_version 下的快照修订号：当提取修正改变 intervals 字节而科学数值
# 不变时抬升。
SNAPSHOT_REVISION = 1

REPO_ROOT = Path(__file__).resolve().parents[1]

ISCHEME_PREFIX = "http://resource.geosciml.org/classifier/ics/ischart/"

# 五个核心 geochronologic rank；其余 rank（Super-Eon、Sub-Period）为结构节点。
CORE_RANKS = ("Eon", "Era", "Period", "Epoch", "Age")
RANK_SLUGS = {
    "Eon": "eon",
    "Era": "era",
    "Period": "period",
    "Epoch": "epoch",
    "Age": "age",
    "Super-Eon": "super-eon",
    "Sub-Period": "sub-period",
}
RANK_CLASS_STRUCTURAL = {"Super-Eon", "Sub-Period"}

# 占位/未命名单元（ICS 图表以斜体显示）：名称可由确定性模式识别。
_PLACEHOLDER_RE = re.compile(r"Cambrian (Stage|Series)")

# 共享边界的容差（开发文档 7.2）。
BOUNDARY_TOL = 1e-9

# 少数派舍入变体的吸附容差：只有落在同一条*结构等值*界线上、且相差不超过
# 0.05 Ma 的两个写法才被视为同一值的末位差异；更大的分歧属于同 rank 重叠
# 调和的范畴，必须显式失败。
ROUNDING_SNAP_TOL = 0.05

# 2026/06 -> 2024/12 回退时，上游 changeNote 只记录了年龄变化，未记录误差变化。
# 开发文档 5.7 明确记载：Wuchiapingian 底界由 259.51 ±0.21 改为 259.857 ±0.084，
# 因此回退到 259.51 Ma 的共享边界必须同时把误差恢复为 0.21 Ma。
# 这是全库唯一硬编码的科学数值，且**不来自** pinned 输入：PROVENANCE.md 与
# docs/data-policy.md 均把它标注为项目自定值，出处为开发文档 5.7。
REVERTED_MARGIN_PATCHES: dict[str, float] = {
    "259.51": 0.21,
}

# 推导快照登记处：只有登记过的版本才能作为 ``--to`` 目标，因此不存在「任意
# --to 都能产出一份来源块自相矛盾的快照」这条路。描述性字段是常量，而
# reverted_boundary_count 由构建时的**实际**回退条数写入。
DERIVED_SNAPSHOTS: dict[str, dict] = {
    "2024/12": {
        "derived_from": {
            "chart_version": "2026/06",
            "method": "revert-upstream-change-notes",
            "source_file": "tools/source/ics-chart-v2026-06.5.ttl",
            "note": (
                "No archived upstream release was fetched: the boundary values were "
                "back-reverted from the skos:changeNotes of the pinned 2026/06 input, "
                "plus the documented Wuchiapingian margin restoration. The source block "
                "is therefore byte-identical to the 2026/06 snapshot. See "
                "geophylo/data/snapshots/PROVENANCE.md and docs/data-policy.md."
            ),
            "generation_log": "tools/build-logs/ics_chart-2024-12.log.json",
        }
    }
}


class BuildError(Exception):
    """快照生成失败（输入不一致或约束被违反）。"""


# --------------------------------------------------------------------------
# TTL 解析
# --------------------------------------------------------------------------

_CONCEPT_RE = re.compile(r"^([A-Za-z][A-Za-z0-9-]*:[A-Za-z0-9_-]+)\s*$")
_PREDICATE_RE = re.compile(r"^    ([A-Za-z][A-Za-z0-9-]*:[A-Za-z0-9_-]+)\s*(.*)$")
_RANK_ITEM_RE = re.compile(r"^\s+rank:([A-Za-z-]+)\s*[,;]?\s*$")
_EN_LABEL_RE = re.compile(r'"((?:[^"\\]|\\.)*)"@en\b')
_NOTATION_RE = re.compile(r'"((?:[^"\\]|\\.)*)"\^\^[A-Za-z0-9-]+:[A-Za-z0-9_-]+')
_ORDER_RE = re.compile(r"sh:order\s+([0-9.]+)")
_COLOR_RE = re.compile(r'schema:color\s+"(#[0-9A-Fa-f]{6})"\^\^')
_BLANK_PREDICATE_RE = re.compile(r"^            ([A-Za-z][A-Za-z0-9-]*:[A-Za-z0-9_-]+)\s*(.*)$")
_BLANK_CLOSE_RE = re.compile(r"^\s*\]\s*;?\s*$")
_BLANK_OPEN_RE = re.compile(r"^\s*\[\s*$")
# Turtle 十进制字面量（可带符号/指数），后跟单个 `;` 或 `,`；整个对象必须被完整
# 消费——多值折行、缺失分号、带 datatype 的写法都落到显式报错分支，而不是被
# 静默漏读。
_DECIMAL = r"[-+]?(?:[0-9]+\.[0-9]*|\.[0-9]+|[0-9]+)(?:[eE][-+]?[0-9]+)?"
_VALUE_RE = re.compile(rf"^\s*({_DECIMAL})\s*(?:[;,]\s*)?$")
# blank node 里 `skos:note` 的对象：谓词已经被 _BLANK_PREDICATE_RE 的 group(1)
# 吃掉，因此这里只匹配剩下的字面量本身——若在这里再要求字面量里含 `skos:note`，
# 就永远匹配不到，图表上的 `~` 会静默丢失。
_STRING_RE = re.compile(r'^\s*"((?:[^"\\]|\\.)*)"\s*(?:[;,]\s*)?$')

# blank node（端点）内允许的谓词白名单；出现未知谓词说明上游改了写法，必须显式
# 失败而不是产出一份「仍能通过全部校验」的残缺快照。
_BOUNDARY_PREDICATES = {
    "ischart:inMYA": "mya",
    "schema:marginOfError": "margin",
    "skos:note": "note",
}


def _expand(term: str, prefix: str, iri: str) -> str:
    """把 ``prefix:Local`` 形式的项展开为完整 IRI。"""
    if term.startswith(prefix):
        return iri + term[len(prefix) + 1 :]
    return term


def _parse_value(where: str, rest: str, *, predicate: str) -> float:
    """把一个数值对象解析为 ``float``，任何偏离都显式失败。"""
    m = _VALUE_RE.match(rest)
    if m is None:
        raise BuildError(f"{where}: {predicate} 的字面量无法解析为十进制数：{rest!r}")
    return float(m.group(1))


def parse_ttl(text: str) -> dict[str, dict]:
    """把 ICS 图表 Turtle 解析为 ``{局部名: 概念字典}``。

    解析器是专用而非通用的，依赖 ICS 图表仓库的固定排版（谓词四空格缩进、端点
    空白节点的谓词十二空格缩进）。它对**任何**偏离排版的写法显式抛
    :class:`BuildError`：未列入白名单的端点谓词、无法解析的数值/字面量、重复的
    ``hasBeginning``/``hasEnd``、写在另一行的对象（值折行会被接受，只要它是唯一
    的对象）。这样「静默产出残缺快照」这条路被堵死。
    """
    concepts: dict[str, dict] = {}
    current: dict | None = None
    predicate: str | None = None
    in_blank: str | None = None
    pending: str | None = None  # 端点谓词的对象落在下一行时暂存语义键

    for raw_line in text.splitlines():
        line = raw_line.rstrip("\n")
        subj = _CONCEPT_RE.match(line)
        if subj:
            if pending is not None:
                raise BuildError(f"{line!r}: 上一行的端点谓词缺少字面量（{pending}）")
            current = {
                "local": subj.group(1).split(":", 1)[1],
                "iri": subj.group(1),
                "rank": None,
                "ranks": [],
                "ratified_gssp": False,
                "ratified_gssa": False,
                "broader": None,
                "notation": None,
                "pref_label_en": None,
                "color": None,
                "order": None,
                "beginning": {"mya": None, "margin": None, "uncertain": False},
                "end": {"mya": None, "margin": None, "uncertain": False},
                "boundary_nodes": [],
                "change_notes": [],
                "is_concept": False,
            }
            concepts[current["local"]] = current
            predicate = None
            in_blank = None
            continue
        if current is None:
            continue

        # 多行 rank 列表（如 Pridoli 同时声明 Age 与 Epoch）。
        rank_item = _RANK_ITEM_RE.match(line)
        if rank_item and predicate == "gts:rank":
            current["ranks"].append(rank_item.group(1))
            continue

        if not in_blank and line.strip() == "a skos:Concept ;":
            current["is_concept"] = True
            continue

        pred = _PREDICATE_RE.match(line)
        if pred and not in_blank:
            predicate = pred.group(1)
            rest = pred.group(2)
            if predicate.endswith(("hasBeginning", "hasEnd")):
                side = "beginning" if predicate.endswith("hasBeginning") else "end"
                if side in current["boundary_nodes"]:
                    raise BuildError(f"{current['iri']}: 重复的 time:{predicate}")
                # 空白节点开到下一行（``[`` 独占一行）或与谓词同行。
                in_blank = side
                current["boundary_nodes"].append(side)
                continue
            if predicate == "gts:rank":
                if rest.strip():
                    current["ranks"].append(rest.split()[0].split(":")[1])
            elif predicate == "gts:ratifiedGSSP":
                current["ratified_gssp"] = "true" in rest
            elif predicate == "gts:ratifiedGSSA":
                current["ratified_gssa"] = "true" in rest
            elif predicate == "skos:broader":
                current["broader"] = rest.split()[0]
            elif predicate == "skos:notation":
                m = _NOTATION_RE.search(line)
                if m:
                    current["notation"] = m.group(1)
            elif predicate == "skos:changeNote":
                m = re.search(r'"((?:[^"\\]|\\.)*)"', line)
                if m:
                    current["change_notes"].append(m.group(1))
                predicate = None
            elif predicate == "sh:order":
                m = _ORDER_RE.search(line)
                if m:
                    current["order"] = float(m.group(1))
            elif predicate == "schema:color":
                m = _COLOR_RE.search(line)
                if m:
                    current["color"] = m.group(1).upper()
            continue

        if in_blank:
            where = f"{current['iri']}[{in_blank}]"
            if _BLANK_OPEN_RE.match(line):
                # `time:hasBeginning` 与 `[` 分行书写（ICS 图表的两种排版之一）。
                if current[in_blank]["mya"] is not None or pending is not None:
                    raise BuildError(f"{where}: 空白节点的 [ 出现在内容之后")
                continue
            if _BLANK_CLOSE_RE.match(line):
                if pending is not None:
                    raise BuildError(f"{where}: 端点谓词缺少字面量（{pending}）")
                node = current[in_blank]
                if node["mya"] is None:
                    raise BuildError(f"{where}: 空白节点缺少 ischart:inMYA")
                in_blank = None
                predicate = None
                continue
            bp = _BLANK_PREDICATE_RE.match(line)
            if bp:
                if pending is not None:
                    raise BuildError(f"{where}: 上一行的端点谓词缺少字面量（{pending}）")
                key = bp.group(1)
                rest = bp.group(2)
                if key not in _BOUNDARY_PREDICATES:
                    raise BuildError(f"{where}: 未预期的端点谓词 {key!r}（白名单外）")
                slot = _BOUNDARY_PREDICATES[key]
                if slot == "mya" and current[in_blank]["mya"] is not None:
                    raise BuildError(f"{where}: 重复的 ischart:inMYA")
                if slot == "margin" and current[in_blank]["margin"] is not None:
                    raise BuildError(f"{where}: 重复的 schema:marginOfError")
                if not rest.strip():
                    pending = slot  # 对象折行到下一行
                    continue
                if slot == "note":
                    m = _STRING_RE.match(rest)
                    if m is None:
                        raise BuildError(f"{where}: skos:note 的字面量无法解析：{rest!r}")
                    if m.group(1) != "uncertain":
                        raise BuildError(
                            f"{where}: 未预期的 skos:note 值 {m.group(1)!r}"
                            '（端点只接受 "uncertain"，即图表上的 ~）'
                        )
                    current[in_blank]["uncertain"] = True
                else:
                    current[in_blank]["margin" if slot == "margin" else "mya"] = _parse_value(
                        where, rest, predicate=key
                    )
                pending = None
                continue
            if pending is not None:  # 折行对象的续行
                if pending == "note":
                    m = _STRING_RE.match(line)
                    if m is None:
                        raise BuildError(f"{where}: skos:note 的折行字面量无法解析：{line!r}")
                    if m.group(1) != "uncertain":
                        raise BuildError(f"{where}: 未预期的 skos:note 值 {m.group(1)!r}")
                    current[in_blank]["uncertain"] = True
                else:
                    value = _parse_value(where, line, predicate=pending)
                    if pending == "mya":
                        current[in_blank]["mya"] = value
                    else:
                        current[in_blank]["margin"] = value
                pending = None
                continue
            raise BuildError(f"{where}: 无法解析的端点行 {line!r}")

        if predicate == "skos:prefLabel":
            m = _EN_LABEL_RE.search(line)
            if m:
                current["pref_label_en"] = json.loads(f'"{m.group(1)}"')
        elif predicate == "sh:order":
            m = _ORDER_RE.search(line)
            if m:
                current["order"] = float(m.group(1))
        elif predicate == "schema:color":
            m = _COLOR_RE.search(line)
            if m:
                current["color"] = m.group(1).upper()
    if pending is not None:
        raise BuildError(f"文件结束时仍有端点谓词未取到字面量（{pending}）")
    return concepts


# --------------------------------------------------------------------------
# changeNote 回退（--to <更早的图表版本>）
# --------------------------------------------------------------------------

_CHANGENOTE_RE = re.compile(r"has(Beginning|End)\s+([0-9.]+)\s*->\s*([0-9.]+)")
_CHANGENOTE_STAMP_RE = re.compile(r"^(\d{4})-(\d{2}):")
CHART_VERSION_RE = re.compile(r"^\d{4}/\d{2}$")


def _version_key(version: str) -> tuple[int, int]:
    """把 ``2026/06`` 变成可比较的 ``(2026, 6)``；格式非法即失败。"""
    if not CHART_VERSION_RE.match(version):
        raise BuildError(f"图表版本格式应为 YYYY/MM，得到 {version!r}")
    year, month = version.split("/")
    if not 1 <= int(month) <= 12:
        raise BuildError(f"图表版本的月份非法：{version!r}")
    return int(year), int(month)


def change_note_stamp(concept: dict, note: str) -> tuple[int, int]:
    """取一条 ``skos:changeNote`` 的版本前缀；无前缀说明上游换了写法，显式失败。"""
    m = _CHANGENOTE_STAMP_RE.match(note)
    if m is None:
        raise BuildError(
            f"{concept['iri']}: 无法解析 skos:changeNote 的版本前缀：{note!r}"
            "（期望形如 '2026-06: hasBeginning 246.7 -> 247.0'）"
        )
    return int(m.group(1)), int(m.group(2))


def revert_change_notes(concepts: dict[str, dict], target: str) -> tuple[list[dict], list[str]]:
    """按上游 ``skos:changeNote`` 把**晚于** ``target`` 的修订回退。

    ``target``（如 ``2024/12``）决定回退集合：只有版本前缀严格晚于 target 的
    changeNote 才被吞掉，因此回退集合由 ``--to`` 本身决定，而不是由某个写死的
    版本字面量决定。任何没有可解析前缀的 changeNote 一律显式失败，因此「上游
    换一种 note 写法就悄悄改变回退范围」这条路被堵死。

    返回 ``(回退记录, 实际应用的修订前缀)``；一条记录形如
    ``{"concept": "Anisian", "boundary": "beginning", "from_mya": 247.0,
    "to_mya": 246.7, "change_note": "2026-06: ..."}``。
    """
    target_key = _version_key(target)
    log: list[dict] = []
    applied: set[str] = set()
    seen: set[tuple[str, str, float]] = set()
    for concept in concepts.values():
        for note in concept["change_notes"]:
            stamp = change_note_stamp(concept, note)
            if stamp <= target_key:
                continue  # 该修订在 target 版（含）之前已生效：保留现值
            applied.add(f"{stamp[0]}-{stamp[1]:02d}")
            matches = list(_CHANGENOTE_RE.finditer(note))
            if not matches:
                raise BuildError(f"{concept['iri']}: changeNote 无可回退的边界陈述：{note!r}")
            for m in matches:
                side, old, new = m.group(1), m.group(2), m.group(3)
                key = "beginning" if side == "Beginning" else "end"
                boundary = concept[key]
                current = boundary["mya"]
                if current is None:
                    raise BuildError(f"{concept['iri']}: changeNote 指向缺失边界（{side}）")
                if abs(current - float(new)) > BOUNDARY_TOL:
                    raise BuildError(f"{concept['iri']}: changeNote 期望现值 {new}，实际 {current}")
                duplicate = (concept["local"], key, float(old))
                if duplicate in seen:
                    raise BuildError(f"{concept['iri']}: 同一端点被两条 changeNote 回退到 {old}")
                seen.add(duplicate)
                boundary["mya"] = float(old)
                margin_patch = None
                if old in REVERTED_MARGIN_PATCHES:
                    margin_patch = REVERTED_MARGIN_PATCHES[old]
                    boundary["margin"] = margin_patch
                entry = {
                    "method": "revert-change-note",
                    "concept": concept["local"],
                    "boundary": key,
                    "from_mya": float(new),
                    "to_mya": float(old),
                    "change_note": note,
                }
                if margin_patch is not None:
                    entry["margin_patch_mya"] = margin_patch
                    entry["margin_patch_source"] = (
                        "REVERTED_MARGIN_PATCHES (development document 5.7; "
                        "not machine-readable upstream, see PROVENANCE.md)"
                    )
                log.append(entry)
    if not log:
        raise BuildError(
            f"--to {target} 没有回退任何边界：目标版本不早于 pinned 输入里的任何一条 "
            f"skos:changeNote 修订。基线快照必须不带 --to 生成。"
        )
    return log, sorted(applied)


# --------------------------------------------------------------------------
# 上游数据瑕疵的确定性修复（结构等值类吸附 + 同 rank 重叠调和）
# --------------------------------------------------------------------------


def _boundary_values(concepts: dict[str, dict]) -> list[float]:
    return [
        concept[side]["mya"]
        for concept in concepts.values()
        for side in ("beginning", "end")
        if concept[side]["mya"] is not None
    ]


def children_index(concepts: dict[str, dict]) -> dict[str, list[str]]:
    """``{父局部名: [子局部名, ...]}``（按 ``skos:broader``）。"""
    children: dict[str, list[str]] = {}
    for concept in concepts.values():
        if concept["broader"]:
            children.setdefault(concept["broader"].split(":")[1], []).append(concept["local"])
    for kids in children.values():
        kids.sort()
    return children


def shared_boundary_classes(concepts: dict[str, dict]) -> list[dict]:
    """按年代地层学结构归并「同一条界线」的端点等价类（吸附判据的来源）。

    一条界线的写法在三种结构关系上必须一致：

    - ``parent-base``：父区间底界 ≡ 其最老子区间的底界；
    - ``parent-top``：父区间顶界 ≡ 其最年亲子区间的顶界；
    - ``sibling-adjacency``：同一父区间下相邻两个子区间的公共界面
      （较老者的顶界 ≡ 较年轻者的底界）。

    只有落在同一类内部的末位差异才是「同一条界线的两种写法」；判据取自这里的
    结构关系而不是全局出现次数，这才使修复与年代地层学而非与数据冗余挂钩
    （Quaternary 的 0.0117/0.0082/0.0042/0.0 之所以安全，是因为它们在各自的结构
    类内部本就一致，而不是因为别处恰好也写了这些值）。
    """
    children = children_index(concepts)
    classes: list[dict] = []
    for parent_local, kids in sorted(children.items()):
        parent = concepts.get(parent_local)
        if parent is None:
            continue
        ordered = sorted(
            (concepts[k] for k in kids), key=lambda c: c["beginning"]["mya"], reverse=True
        )
        oldest = [
            c["local"] for c in ordered if c["beginning"]["mya"] == ordered[0]["beginning"]["mya"]
        ]
        youngest_end = min(c["end"]["mya"] for c in ordered)
        youngest = [c["local"] for c in ordered if c["end"]["mya"] == youngest_end]
        classes.append(
            {
                "kind": "parent-base",
                "parent": parent_local,
                "members": [(parent_local, "beginning")] + [(k, "beginning") for k in oldest],
            }
        )
        classes.append(
            {
                "kind": "parent-top",
                "parent": parent_local,
                "members": [(parent_local, "end")] + [(k, "end") for k in youngest],
            }
        )
        for older, younger in zip(ordered, ordered[1:], strict=False):
            classes.append(
                {
                    "kind": "sibling-adjacency",
                    "parent": parent_local,
                    "members": [(older["local"], "end"), (younger["local"], "beginning")],
                }
            )
    # 根区间（无 broader）没有父类可锚定，但它们的端点仍参与全局计数；此处只保留
    # 有结构关系可依的类。
    return classes


def _describe(members: list[tuple[str, str]]) -> str:
    """把端点成员列表写成 ``Ludfordian.end + Pridoli.beginning`` 形式。"""
    return " + ".join(f"{local}.{side}" for local, side in sorted(members))


def repair_minority_rounding(concepts: dict[str, dict]) -> list[dict]:
    """把结构等值类内的孤立舍入值吸附到被佐证的主流值。

    规则（三条同时成立才修）：

    1. 候选成员落在同一条*结构等值*界线上（见 :func:`shared_boundary_classes`）；
    2. 两个写法相差不超过 ``ROUNDING_SNAP_TOL``（更大的分歧属于重叠调和的范畴，
       必须显式失败）；
    3. 少数派写法在全库只出现一次，主流写法至少出现两次。

    不满足就抛 :class:`BuildError`——绝不猜。吸附后的父子时间包含关系由
    :func:`check_parent_containment` 复验。
    """
    counts = Counter(_boundary_values(concepts))
    repairs: list[dict] = []
    for cls in shared_boundary_classes(concepts):
        values: dict[float, list[tuple[str, str]]] = {}
        for member in cls["members"]:
            mya = concepts[member[0]][member[1]]["mya"]
            if mya is not None:
                values.setdefault(mya, []).append(member)
        if len(values) < 2:
            continue
        if max(values) - min(values) > ROUNDING_SNAP_TOL:
            continue  # 交给同 rank 重叠调和（或显式失败）
        winners = [v for v in values if counts[v] >= 2]
        losers = [v for v in values if counts[v] == 1]
        if not losers:
            raise BuildError(
                f"结构等值类（{cls['kind']} @ {cls['parent']}：{_describe(cls['members'])}）"
                f"内的 {sorted(values)} 无法确定主流值"
                "（需要「唯一写法 vs 被佐证写法」）；请人工裁决"
            )
        if len(winners) != 1:
            raise BuildError(
                f"结构等值类（{cls['kind']} @ {cls['parent']}）的多数值不唯一：{sorted(winners)}；"
                "请人工裁决"
            )
        winner = winners[0]
        for loser in sorted(losers):
            for local, side in values[loser]:
                concepts[local][side]["mya"] = winner
                repairs.append(
                    {
                        "method": "snap-minority-rounding-variant",
                        "concept": local,
                        "boundary": side,
                        "from_mya": loser,
                        "to_mya": winner,
                        "class_kind": cls["kind"],
                        "parent": cls["parent"],
                        "shared_by": _describe(cls["members"]),
                        "upward_writings": {str(loser): 1, str(winner): counts[winner]},
                    }
                )
    return repairs


def _statements_at(concepts: dict[str, dict], age: float) -> list[tuple[str, str, dict]]:
    """列出写在年龄 ``age`` 上的全部端点陈述（概念、侧、端点字典）。"""
    return [
        (concept["local"], side, concept[side])
        for concept in concepts.values()
        for side in ("beginning", "end")
        if concept[side]["mya"] is not None and abs(concept[side]["mya"] - age) <= BOUNDARY_TOL
    ]


def reconcile_same_rank_overlaps(concepts: dict[str, dict]) -> list[dict]:
    """检测并按确定性规则调和同 rank 区间重叠；误差与 ``~`` 不随年龄迁移。

    规则：重叠时优先采信子区间并集终点（如 Ludlow 的 419.62 与其子 stage 并集
    终点 422.7 矛盾）；其余情形显式失败，交由人工裁决（不允许静默改数）。
    搬动年龄时**必须**把该端点上属于原年龄的 ``marginOfError`` 与 ``uncertain``
    一并清空——它们是对**旧值**的陈述，跟着年龄走会在目标年龄上制造一条上游
    从未有过的误差冲突。若目标年龄没有其它独立误差凭据则显式失败（不许凭空
    丢掉不确定度信息）。
    """
    log: list[dict] = []
    children = children_index(concepts)

    for _pass in range(10):
        changed = False
        records = [(rank, concept) for concept in concepts.values() for rank in concept["ranks"]]
        for rank in sorted({r for r, _c in records}):
            group = [c for r, c in records if r == rank]
            group.sort(key=lambda c: c["beginning"]["mya"], reverse=True)
            for older_c, younger_c in zip(group, group[1:], strict=False):
                a_younger = older_c["end"]["mya"]
                b_older = younger_c["beginning"]["mya"]
                # 年龄越大越老：重叠宽度 = b_older - a_younger（较年新区间的
                # 底界比较老区间的顶界更老时，两者时间相交）。
                overlap = b_older - a_younger
                if overlap <= BOUNDARY_TOL:
                    continue
                kids = children.get(older_c["local"], [])
                child_ends = [
                    concepts[k]["end"]["mya"]
                    for k in kids
                    if concepts[k]["end"]["mya"] is not None  # 0.0 是合法值，不能被真值过滤
                ]
                union_end = min(child_ends) if child_ends else None
                if union_end is None or abs(union_end - b_older) > BOUNDARY_TOL:
                    raise BuildError(
                        f"同 rank 重叠且无法确定性调和：{older_c['local']} "
                        f"[{older_c['beginning']['mya']}, {a_younger}] 与 "
                        f"{younger_c['local']}（older={b_older}）；请人工核对上游数据"
                    )
                moved = older_c["end"]
                stale_margin, stale_uncertain = moved["margin"], moved["uncertain"]
                corroborating = [
                    (local, side, node)
                    for local, side, node in _statements_at(concepts, union_end)
                    if (local, side) != (older_c["local"], "end")
                ]
                if stale_margin is not None and not any(
                    node["margin"] is not None for _, _, node in corroborating
                ):
                    raise BuildError(
                        f"{older_c['local']}.end 从 {a_younger} 搬到 {union_end} 会丢弃属于 "
                        f"{a_younger} 的误差 ±{stale_margin}，而 {union_end} Ma 处没有其它误差"
                        "凭据；请人工裁决"
                    )
                moved["mya"] = union_end
                moved["margin"] = None
                moved["uncertain"] = False
                entry = {
                    "method": "same-rank-overlap-children-union",
                    "concept": older_c["local"],
                    "boundary": "end",
                    "from_mya": a_younger,
                    "to_mya": union_end,
                    "overlapping_with": younger_c["local"],
                    "rank": rank,
                    "children_union_members": _describe([(k, "end") for k in sorted(kids)]),
                }
                if stale_margin is not None:
                    entry["cleared_margin_of_stale_age"] = stale_margin
                if stale_uncertain:
                    entry["cleared_uncertain_of_stale_age"] = True
                log.append(entry)
                changed = True
        if not changed:
            return log
    raise BuildError("同 rank 重叠调和未在 10 轮内收敛；请人工核对上游数据")


def check_parent_containment(concepts: dict[str, dict]) -> None:
    """吸附/调和之后复验父子时间包含（层级不得被破坏，故显式校验）。"""
    for concept in concepts.values():
        if not concept["broader"]:
            continue
        parent = concepts.get(concept["broader"].split(":")[1])
        if parent is None:
            raise BuildError(f"{concept['iri']}: 父级 {concept['broader']} 未被收录")
        if concept["beginning"]["mya"] > parent["beginning"]["mya"] + BOUNDARY_TOL or (
            concept["end"]["mya"] < parent["end"]["mya"] - BOUNDARY_TOL
        ):
            raise BuildError(
                f"层级包含被破坏：{concept['iri']} "
                f"[{concept['beginning']['mya']}, {concept['end']['mya']}] 不在父区间 "
                f"{parent['iri']} [{parent['beginning']['mya']}, {parent['end']['mya']}] 之内"
            )


# --------------------------------------------------------------------------
# 边界定义推导与共享边界调和
# --------------------------------------------------------------------------


def reconcile_boundaries(concepts: dict[str, dict]) -> tuple[dict[float, dict], list[str]]:
    """按边界年龄调和共享边界的误差与 ``~`` 标记。

    上游对同一边界可能在多条记录中重复书写；若误差或 ``uncertain`` 标记不一致，
    采用确定性规则：误差取最大值（保守），``uncertain`` 取逻辑或，并记录警告。
    返回 ``({年龄: {"margin": float|None, "uncertain": bool}}, [警告, ...])``。
    """
    merged: dict[float, dict] = {}
    warnings: list[str] = []
    for concept in concepts.values():
        for side, boundary in ((s, concept[s]) for s in ("beginning", "end")):
            age = boundary["mya"]
            if age is None:
                continue
            slot = merged.setdefault(age, {"margin": None, "uncertain": False})
            if boundary["margin"] is not None:
                if (
                    slot["margin"] is not None
                    and abs(slot["margin"] - boundary["margin"]) > BOUNDARY_TOL
                ):
                    warnings.append(
                        f"年龄 {age} 的误差不一致"
                        f"（{slot['margin']} vs {boundary['margin']}），取最大值"
                    )
                    slot["margin"] = max(slot["margin"], boundary["margin"])
                else:
                    slot["margin"] = (
                        max(slot["margin"] or 0.0, boundary["margin"]) or boundary["margin"]
                    )
            if boundary["uncertain"]:
                if slot["uncertain"] is False and slot["margin"] is not None:
                    warnings.append(
                        f"年龄 {age} 同时带 ~ 与 ± 误差（{concept['iri']}.{side}）："
                        "qualifier 记为 approximate，uncertainty_ma 仍保留该误差"
                    )
                slot["uncertain"] = True
    return merged, warnings


def boundary_definition(age: float, concepts: dict[str, dict]) -> str:
    """按共享年龄推导边界定义方式（gssp / gssa / numeric_estimate）。"""
    if abs(age) <= BOUNDARY_TOL:
        return "present"
    definition = "numeric_estimate"
    for concept in concepts.values():
        beginning = concept["beginning"]
        if beginning["mya"] is None or abs(beginning["mya"] - age) > BOUNDARY_TOL:
            continue
        if concept["ratified_gssp"]:
            return "gssp"
        if concept["ratified_gssa"]:
            definition = "gssa"
    return definition


def boundary_qualifier(age: float, definition: str, margin: float | None, uncertain: bool) -> str:
    """按开发文档 5.6 的确定性规则推导 ``qualifier``（ADR-5：与 definition 正交）。

    ``~``（上游 ``skos:note "uncertain"``）先于 ``definition`` 判定：一条 GSSP
    界线的数值**本身**可以是上游明示的近似值，此时把它记成 ``defined``
    （"exactly defined"）就是用 definition 轴吞掉 qualifier 轴——那会让 7 条
    GSSP 界线的 ``~`` 在结构上永远无法表达。
    """
    if definition == "present":
        return "present"
    if uncertain:
        return "approximate"
    if definition in ("gssp", "gssa"):
        return "constrained" if margin is not None else "defined"
    if margin is not None:
        return "constrained"
    return "unknown"


def interval_status(concept: dict) -> str:
    """推导 ``status``：有 ratified 标记为 ratified；占位命名为 informal；其余 unknown。"""
    if concept["ratified_gssp"] or concept["ratified_gssa"]:
        return "ratified"
    if _PLACEHOLDER_RE.search(concept.get("_name", concept["pref_label_en"] or "")):
        return "informal"
    return "unknown"


def interval_id(rank: str, name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return f"ics:{RANK_SLUGS[rank]}:{slug}"


_TOKEN_RE = re.compile(r"[A-Z]+(?=[A-Z][a-z])|[A-Z]?[a-z]+|[A-Z]+|[0-9]+")


def derive_name(local: str) -> str:
    """从上游局部名确定性推导显示名（如 ``LowerJurassic`` → ``Lower Jurassic``）。

    部分 series/epoch 级细分单元（Lower/Middle/Upper 各系、Tarantian、
    Cambrian 占位 Stage 等）在上游 RDF 中没有 @en prefLabel，只有 IRI 局部名。
    """
    return " ".join(_TOKEN_RE.findall(local))


# --------------------------------------------------------------------------
# 组装快照
# --------------------------------------------------------------------------


def canonical_payload(intervals: list[dict]) -> bytes:
    return json.dumps(intervals, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )


def _canonical(obj: object) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )


def provenance_digest(snapshot: Mapping) -> str:
    """对「除 ``intervals`` 与 ``hash`` 之外的全部顶层元数据」做规范化 SHA-256。

    ``payload_sha256`` 只保护科学数值；``provenance_sha256`` 保护的是版本标签、
    来源块、许可声明与推导披露本身，因此「只改 ``chart_version`` 或
    ``source.commit``」这类不改数据字节的篡改也能被独立检出
    （PROVENANCE.md 自述的取舍由此闭合）。
    """
    covered = {key: value for key, value in snapshot.items() if key not in ("intervals", "hash")}
    return hashlib.sha256(_canonical(covered)).hexdigest()


def select_concepts(parsed: dict[str, dict]) -> tuple[dict[str, dict], dict]:
    """挑出区间概念，并对**任何**被丢弃的概念显式失败。

    「有 ``skos:Concept`` 但没有 rank / rank 不在白名单 / 缺端点」的主体一个都
    不能静默跳过：那样「上游换一种写法」就会产出一份仍能通过全部校验的残缺
    快照。
    """
    concepts: dict[str, dict] = {}
    rejected: list[tuple[str, str]] = []
    for concept in parsed.values():
        if not concept["is_concept"]:
            continue  # Collection / datatype / scheme 等主体，本就不是地层单元
        if not concept["ranks"]:
            rejected.append((concept["iri"], "无 gts:rank"))
            continue
        unknown = [r for r in concept["ranks"] if r not in RANK_SLUGS]
        if unknown:
            rejected.append((concept["iri"], f"rank 不在白名单：{unknown}"))
            continue
        missing = [
            f"缺少 time:has{'Beginning' if side == 'beginning' else 'End'}"
            for side in ("beginning", "end")
            if concept[side]["mya"] is None
        ]
        if missing:
            rejected.append((concept["iri"], "；".join(missing)))
            continue
        concepts[concept["local"]] = concept
    if rejected:
        raise BuildError(
            "解析出的 skos:Concept 主体被丢弃（静默产出残缺快照的路径已被堵死）："
            + "；".join(f"{iri} {why}" for iri, why in rejected)
        )
    if not concepts:
        raise BuildError("未能从 TTL 解析出任何概念")
    duplicates = [
        iri for iri, count in Counter(c["iri"] for c in concepts.values()).items() if count > 1
    ]
    if duplicates:  # pragma: no cover - 字典键唯一，防御性
        raise BuildError(f"同一 IRI 出现多条概念记录：{duplicates}")
    stats = {
        "concept_subjects": sum(1 for c in parsed.values() if c["is_concept"]),
        "ranked_concepts": len(concepts),
        "records": sum(len(c["ranks"]) for c in concepts.values()),
        "boundary_values": sum(
            1
            for c in concepts.values()
            for side in ("beginning", "end")
            if c[side]["mya"] is not None
        ),
        "margin_values": sum(
            1
            for c in concepts.values()
            for side in ("beginning", "end")
            if c[side]["margin"] is not None
        ),
        "uncertain_notes": sum(
            1 for c in concepts.values() for side in ("beginning", "end") if c[side]["uncertain"]
        ),
        "change_notes": sum(len(c["change_notes"]) for c in concepts.values()),
    }
    if stats["boundary_values"] != 2 * stats["ranked_concepts"]:
        raise BuildError(f"端点数量与概念数不匹配：{stats}")
    return concepts, stats


def _repo_relative(path: Path) -> str:
    """把路径写成仓库根相对的正斜杠形式（绝对路径会让快照字节随机器变化）。"""
    resolved = path.resolve()
    try:
        return resolved.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return resolved.as_posix()


def build_snapshot(
    ttl_path: Path,
    *,
    chart_version: str,
    tag: str,
    commit: str,
    source_sha256: str,
    to_version: str | None,
) -> tuple[dict, dict]:
    """生成快照字典；第二个返回值是生成日志。"""
    text = ttl_path.read_text(encoding="utf-8")
    concepts, stats = select_concepts(parse_ttl(text))

    log: dict = {
        "chart_version": chart_version,
        "to_version": to_version,
        "warnings": [],
        "reverted_boundaries": [],
        "change_note_stamps_applied": [],
        "integrity_repairs": [],
        "parse_stats": stats,
    }
    derived_from: dict | None = None
    if to_version is not None:
        if to_version != chart_version:
            raise BuildError(
                f"--to {to_version} 与 --chart-version {chart_version} 不一致：一份快照只能"
                "声明它所表示的那个图表版本"
            )
        if to_version not in DERIVED_SNAPSHOTS:
            raise BuildError(
                f"--to {to_version} 未在 DERIVED_SNAPSHOTS 登记：拒绝生成一份 source 块与自身"
                "版本标签矛盾、却无任何披露的快照"
            )
        reverted, applied = revert_change_notes(concepts, to_version)
        log["reverted_boundaries"] = reverted
        log["change_note_stamps_applied"] = applied
        log["integrity_repairs"].extend(reverted)
        # 计数取自本次构建的**实际**回退条数，因此索引里的披露与数据同源。
        derived_from = {
            **DERIVED_SNAPSHOTS[to_version]["derived_from"],
            "generator_flag": f"--to {to_version}",
            "reverted_boundary_count": len(reverted),
        }

    snapping = repair_minority_rounding(concepts)
    overlaps = reconcile_same_rank_overlaps(concepts)
    check_parent_containment(concepts)
    log["integrity_repairs"].extend(snapping)
    log["integrity_repairs"].extend(overlaps)

    merged, warnings = reconcile_boundaries(concepts)
    log["warnings"].extend(warnings)

    intervals: list[dict] = []
    derived_labels: list[dict] = []
    for concept in concepts.values():
        if not concept["pref_label_en"]:
            concept["_name"] = derive_name(concept["local"])
            derived_labels.append({"concept": concept["iri"], "derived_name": concept["_name"]})
        else:
            concept["_name"] = concept["pref_label_en"]
    for concept in concepts.values():
        name = concept["_name"]
        boundaries = []
        for key in ("beginning", "end"):
            raw = concept[key]
            age = raw["mya"]
            if age is None:
                raise BuildError(
                    f"{concept['local']}: 缺少 {'hasBeginning' if key == 'beginning' else 'hasEnd'}"
                )
            shared = merged[age]
            margin = shared["margin"]
            definition = boundary_definition(age, concepts)
            qualifier = boundary_qualifier(age, definition, margin, shared["uncertain"])
            boundaries.append(
                {
                    "age_ma": age,
                    "qualifier": qualifier,
                    "uncertainty_ma": margin,
                    "definition": definition,
                    # 端点级的 per-boundary IRI 由后端（如 pyrolite）在能给出时
                    # 填充；ICS 图表的端点是 blank node，没有可引用的稳定 IRI，
                    # 因此快照里恒为 None（记录在案，见 models.Boundary 文档）。
                    "source_iri": None,
                }
            )
        older, younger = boundaries
        if not older["age_ma"] > younger["age_ma"]:
            raise BuildError(f"{concept['local']}: older_ma 必须严格大于 younger_ma")
        parent_local = concept["broader"].split(":")[1] if concept["broader"] else None
        parent = concepts.get(parent_local) if parent_local else None
        if concept["broader"] and parent is None:
            raise BuildError(f"{concept['local']}: 父级 {concept['broader']} 未被收录")
        # Pridoli 同时声明 Age 与 Epoch（ICS 图表在两个行位显示），为每个声明
        # rank 各生成一条记录；id 含 rank 段因此仍唯一。
        for rank in concept["ranks"]:
            intervals.append(
                {
                    "id": interval_id(rank, name),
                    "source_iri": ISCHEME_PREFIX + concept["local"],
                    "name": name,
                    "label": name,
                    "aliases": [concept["notation"]] if concept["notation"] else [],
                    "rank": rank,
                    "rank_class": "structural"
                    if rank in RANK_CLASS_STRUCTURAL
                    else "geochronologic",
                    "parent_id": interval_id(parent["ranks"][0], parent["_name"])
                    if parent
                    else None,
                    "source_parent_id": _expand(concept["broader"], "ischart", ISCHEME_PREFIX)
                    if concept["broader"]
                    else None,
                    "status": interval_status(concept),
                    "color": concept["color"],
                    "older_boundary": older,
                    "younger_boundary": younger,
                }
            )
        if not concept["color"]:
            raise BuildError(f"{concept['local']}: 缺少 schema:color")

    intervals.sort(key=lambda r: (r["rank"] not in RANK_CLASS_STRUCTURAL, r["rank"], r["id"]))

    # qualifier 分布按**出厂端点**计数（179 条记录 x 2 = 358），不是按概念计数：
    # 它是 ``approximate`` 是否真被捕获的唯一可见指标，因此必须与 payload 同源。
    qualifiers: Counter[str] = Counter(
        record[side]["qualifier"]
        for record in intervals
        for side in ("older_boundary", "younger_boundary")
    )

    # 别名（上游官方短代码）按大小写折叠去重：ICS 图表以大小写区分 epoch 级
    # （如 T3 = Upper Triassic）与 age 级（如 t3 = Anisian）代码，二者折叠后
    # 冲突。消解规则是确定性的：高优先级 rank 保留（Super-Eon < Eon < Era <
    # Period < Sub-Period < Epoch < Age），同 rank 内 id 字典序更小者保留。
    # 这确实会**丢掉**一侧的代码（哪一级应当持有共享短代码，需按 ICS 图表确认），
    # 因此落选清单被同时写进生成日志与快照顶层元数据，而不是只活在一个未跟踪
    # 的日志文件里。
    alias_priority = {
        "Super-Eon": 0,
        "Eon": 1,
        "Era": 2,
        "Period": 3,
        "Sub-Period": 4,
        "Epoch": 5,
        "Age": 6,
    }
    claimed: dict[str, str] = {}
    dropped_aliases: list[dict] = []
    for record in sorted(intervals, key=lambda r: (alias_priority[r["rank"]], r["id"])):
        kept: list[str] = []
        for alias in record["aliases"]:
            folded = alias.casefold()
            if folded in claimed:
                dropped_aliases.append(
                    {
                        "id": record["id"],
                        "alias": alias,
                        "rank": record["rank"],
                        "claimed_by": claimed[folded],
                        "rule": "alias-casefold-precedence",
                    }
                )
            else:
                claimed[folded] = record["id"]
                kept.append(alias)
        record["aliases"] = kept

    payload_sha = hashlib.sha256(canonical_payload(intervals)).hexdigest()
    snapshot: dict = {
        "schema_version": SCHEMA_VERSION,
        "chart_version": chart_version,
        "snapshot_revision": SNAPSHOT_REVISION,
        "generator": {"name": GENERATOR_NAME, "version": GENERATOR_VERSION},
        "source": {
            "kind": "ics-rdf",
            "url": f"https://github.com/i-c-stratigraphy/chart/blob/{commit}/chart.ttl",
            "commit": commit,
            "tag": tag,
            "source_sha256": source_sha256,
            "vendored_copy": f"tools/source/ics-chart-{tag}.ttl",
        },
        "license": {
            "spdx": "CC-BY-4.0",
            "file": "LICENSES/CC-BY-4.0.txt",
            "attribution": "International Commission on Stratigraphy",
            "citation": "Cohen, K.M., Harper, D.A.T., Gibbard, P.L. & Car, N. (2025, updated). "
            "International Chronostratigraphic Chart.",
        },
        "derivation": {
            "pinned_input": {
                "file": _repo_relative(ttl_path),
                "sha256": hashlib.sha256(ttl_path.read_bytes()).hexdigest(),
            },
            "parse_stats": stats,
            "qualifier_counts": dict(sorted(qualifiers.items())),
            "integrity_repairs": log["integrity_repairs"],
            "derived_labels": derived_labels,
            "dropped_aliases": dropped_aliases,
            "alias_precedence": alias_priority,
            "qualifier_rule": (
                "present -> present; uncertain (~) -> approximate; gssp/gssa with a published "
                "margin -> constrained; gssp/gssa without a margin -> defined; numeric estimate "
                "with a margin -> constrained; otherwise unknown"
            ),
        },
        "intervals": intervals,
    }
    if to_version is not None and derived_from is not None:
        snapshot["derived_from"] = derived_from
    snapshot["hash"] = {
        "scope": "payload_sha256: sha256 over canonical JSON of the intervals array only; "
        "provenance_sha256: sha256 over canonical JSON of every top-level block except "
        "intervals and hash",
        "algorithm": "sha256",
        "payload_sha256": payload_sha,
        "provenance_sha256": provenance_digest(snapshot),
    }
    log["interval_count"] = len(intervals)
    log["derived_labels"] = derived_labels
    log["dropped_aliases"] = dropped_aliases
    log["qualifier_counts"] = dict(sorted(qualifiers.items()))
    log["by_rank"] = {
        rank: sum(1 for r in intervals if r["rank"] == rank)
        for rank in sorted({r["rank"] for r in intervals})
    }
    return snapshot, log


def _index_entry(snapshot: Mapping, filename: str, digest: str) -> dict:
    """单个版本在 ``versions.json`` 里的条目（含推导快照的 ``derived_from``）。

    ``derived_from`` 取自快照自身顶层（构建时由**实际**回退条数写入），索引重建
    只是搬运它，不从常量里抄一份可能说谎的计数。
    """
    entry: dict = {
        "file": filename,
        "chart_version": str(snapshot["chart_version"]),
        "snapshot_revision": snapshot["snapshot_revision"],
        "generator": dict(snapshot["generator"]),
        "payload_sha256": digest,
        "provenance_sha256": str(snapshot["hash"]["provenance_sha256"]),
    }
    if "derived_from" in snapshot:
        entry["derived_from"] = snapshot["derived_from"]
    return entry


def _verify_derived_entry(snapshots_dir: Path, version: str, entry: Mapping) -> None:
    """把 ``derived_from.reverted_boundary_count`` 与生成日志的实际条数对齐。"""
    derived = entry.get("derived_from")
    if not derived:
        return
    log_ref = derived.get("generation_log")
    if not log_ref:
        raise SystemExit(f"{version}: derived_from 缺少 generation_log，出处无法复核")
    log_path = REPO_ROOT / log_ref
    if not log_path.is_file():
        raise SystemExit(f"{version}: 生成日志 {log_ref} 不存在（出处链断裂）")
    log = json.loads(log_path.read_text(encoding="utf-8"))
    actual = len(log.get("reverted_boundaries", []))
    declared = derived.get("reverted_boundary_count")
    if declared != actual:
        raise SystemExit(
            f"{version}: derived_from.reverted_boundary_count 说谎（声明 {declared}，"
            f"日志 {log_ref} 实为 {actual} 条）"
        )
    if str(log.get("to_version")) != version:
        raise SystemExit(f"{version}: 生成日志的 to_version={log.get('to_version')!r} 与条目不符")


def _verify_pinned_input(snapshots_dir: Path, entries: Mapping[str, Mapping]) -> dict:
    """两份快照必须声明同一个 pinned 输入，且该输入在磁盘上的哈希必须相符。"""
    seen: dict[str, dict] = {}
    for version, entry in entries.items():
        path = snapshots_dir / str(entry["file"])
        snapshot = json.loads(path.read_text(encoding="utf-8"))
        pinned = snapshot.get("derivation", {}).get("pinned_input")
        if not pinned:
            raise SystemExit(f"{version}: 快照缺少 derivation.pinned_input（无法核验输入哈希）")
        key = str(pinned["file"])
        if key in seen and seen[key] != pinned:
            raise SystemExit(f"同一输入 {key} 被两份快照声明为不同的哈希/元数据")
        seen[key] = dict(pinned)
    if len(seen) != 1:
        raise SystemExit(f"快照来自多个不同的输入：{sorted(seen)}；versions.json 只支持单一输入")
    ((key, pinned),) = seen.items()
    input_path = REPO_ROOT / key
    if not input_path.is_file():
        raise SystemExit(f"pinned 输入 {key} 不在仓库内（出处链断裂）")
    actual = hashlib.sha256(input_path.read_bytes()).hexdigest()
    if actual != pinned["sha256"]:
        raise SystemExit(
            f"pinned 输入 {key} 的 SHA-256 不符（声明 {pinned['sha256']}，实际 {actual}）"
        )
    return {"file": key, "sha256": actual, "bytes": input_path.stat().st_size}


def rebuild_index(snapshots_dir: Path, baseline: str) -> None:
    """按目录内全部快照重建 ``versions.json``（唯一版本索引）。

    重建不只是搬运：它复算并断言两把哈希（``payload_sha256`` 覆盖科学数值、
    ``provenance_sha256`` 覆盖版本标签与来源块），核对 pinned 输入在磁盘上的
    SHA-256，并把 ``derived_from`` 的回退计数与生成日志的实际条数对齐；任何
    不符都直接失败（“披露与数据脱钩”这类问题由此堵死）。
    """
    index: dict = {
        "schema_version": 2,
        "baseline": baseline,
        "versions": {},
    }
    snapshot_re = re.compile(r"ics_chart-\d{4}-\d{2}\.json$")
    for path in sorted(snapshots_dir.glob("ics_chart-*.json")):
        if not snapshot_re.fullmatch(path.name):
            continue
        snapshot = json.loads(path.read_text(encoding="utf-8"))
        version = str(snapshot["chart_version"])
        digest = hashlib.sha256(canonical_payload(snapshot["intervals"])).hexdigest()
        declared = str(snapshot["hash"]["payload_sha256"])
        if digest != declared:
            raise SystemExit(f"{path.name}: payload_sha256 不符（声明 {declared}，实际 {digest}）")
        provenance = str(snapshot["hash"]["provenance_sha256"])
        if provenance != provenance_digest(snapshot):
            raise SystemExit(f"{path.name}: provenance_sha256 不符（元数据被改过而未重算）")
        index["versions"][version] = _index_entry(snapshot, path.name, digest)
    for version, entry in index["versions"].items():
        _verify_derived_entry(snapshots_dir, version, entry)
    index["pinned_input"] = _verify_pinned_input(snapshots_dir, index["versions"])
    index["versions"] = dict(sorted(index["versions"].items()))
    (snapshots_dir / "versions.json").write_text(
        json.dumps(index, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    n_versions = len(index["versions"])
    print(f"重建 {snapshots_dir / 'versions.json'}（{n_versions} 个版本，基线 {baseline}）")


def _load_make_diff():
    """按文件路径加载同目录的 ``make_diff.py``（tools/ 不是包）。"""
    path = Path(__file__).resolve().with_name("make_diff.py")
    spec = importlib.util.spec_from_file_location("geophylo_make_diff", path)
    if spec is None or spec.loader is None:  # pragma: no cover - 安装产物损坏
        raise BuildError(f"无法加载 diff 生成器：{path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_diff(snapshots_dir: Path, *, from_version: str, to_version: str, out: Path) -> Path:
    """生成 ``from_version`` -> ``to_version`` 的机器可读 diff 并写出。"""

    def load(version: str) -> dict:
        filename = f"ics_chart-{version.replace('/', '-')}.json"
        path = snapshots_dir / filename
        if not path.is_file():
            raise BuildError(f"diff 需要的快照不存在：{path}")
        return json.loads(path.read_text(encoding="utf-8"))

    make_diff = _load_make_diff()
    diff = make_diff.build_diff(load(from_version), load(to_version))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(make_diff.serialize(diff), encoding="utf-8")
    summary = diff["summary"]
    print(
        f"写出 {out}（{from_version} -> {to_version}：{summary['fields_changed']} 个字段、"
        f"{summary['records_changed']} 条记录、{summary['boundary_age_changes']} 处边界年龄变化）"
    )
    return out


def diff_filename(from_version: str, to_version: str) -> str:
    """diff 文件的既定命名（随包发布的 diff 工件即按此规则命名）。"""
    return f"diff-{from_version.replace('/', '-')}_to_{to_version.replace('/', '-')}.json"


def default_log_path(snapshot_path: Path) -> Path:
    """生成日志的既定位置与命名（``tools/build-logs/<快照名>.log.json``）。

    以仓库根为锚点而不是当前工作目录：在任意子目录里跑同一条命令，日志都落在
    同一个被跟踪的位置，命名与 ``docs/data-policy.md`` 一致。
    """
    return REPO_ROOT / "tools" / "build-logs" / f"{snapshot_path.stem}.log.json"


_TAG_RE = re.compile(r"^v\d{4}-\d{2}(\.\d+)?$")
_RETRIEVED_AT_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--ttl", type=Path, required=True, help="pinned 的上游 chart.ttl 副本")
    parser.add_argument("--chart-version", required=True, help="快照的 ICS 图表版本，如 2026/06")
    parser.add_argument(
        "--tag",
        required=True,
        help="上游发布 tag（如 v2026-06.5）；写入快照 source.tag 并用于校验 vendored 副本命名",
    )
    parser.add_argument("--commit", required=True, help="上游 chart.ttl 的固定 commit")
    parser.add_argument("--source-sha256", required=True, help="上游 chart.ttl 文件哈希")
    parser.add_argument(
        "--retrieved-at", required=True, help="抓取时间（仅写入生成日志，绝不写入快照）"
    )
    parser.add_argument(
        "--to",
        default=None,
        help="回退目标图表版本（如 2024/12）：只回退晚于该版本的 changeNote 修订，"
        "且必须与 --chart-version 一致并已在 DERIVED_SNAPSHOTS 登记",
    )
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--log-out", type=Path, default=None, help="生成日志输出路径（JSON）")
    parser.add_argument(
        "--write-index",
        action="store_true",
        help="写完快照后按 --out 所在目录内的全部快照重建 versions.json",
    )
    parser.add_argument(
        "--baseline",
        default=None,
        help="重建 versions.json 时标注的基线快照（默认沿用已有的 baseline）",
    )
    parser.add_argument(
        "--diff-with",
        default=None,
        metavar="CHART_VERSION",
        help="写完快照后，生成与该版本快照的机器可读 diff（与 --out 同目录解析文件）",
    )
    parser.add_argument(
        "--diff-out",
        type=Path,
        default=None,
        help="diff 输出路径（默认 --out 同目录下的 diff-<from>_to_<to>.json）",
    )
    args = parser.parse_args(argv)

    if not CHART_VERSION_RE.match(args.chart_version):
        raise SystemExit(f"--chart-version 格式应为 YYYY/MM，得到 {args.chart_version!r}")
    if not _TAG_RE.match(args.tag):
        raise SystemExit(f"--tag 格式应为 vYYYY-MM[.N]，得到 {args.tag!r}")
    if not _RETRIEVED_AT_RE.match(args.retrieved_at):
        raise SystemExit(
            f"--retrieved-at 必须是形如 2026-09-11T00:00:00Z 的 UTC 时间戳，"
            f"得到 {args.retrieved_at!r}"
        )
    vendored = REPO_ROOT / "tools" / "source" / f"ics-chart-{args.tag}.ttl"
    if not vendored.is_file():
        raise SystemExit(f"--tag {args.tag} 与仓库内的 vendored 副本不符：缺少 {vendored}")
    if (args.to is None and args.chart_version in DERIVED_SNAPSHOTS) or (
        args.to is not None and args.to != args.chart_version
    ):
        raise SystemExit(
            f"--chart-version {args.chart_version} 与 --to {args.to} 矛盾：推导快照必须显式"
            "回退（--to 与 --chart-version 同值），基线快照必须不带 --to"
        )
    if args.diff_with == args.chart_version:
        raise SystemExit(
            f"--diff-with {args.diff_with} 与本次生成的快照同版本：diff 是两份*不同*"
            "快照之间的机器可读事实（应在生成较新那一份时指向既有快照）"
        )
    if not args.source_sha256 == hashlib.sha256(args.ttl.read_bytes()).hexdigest():
        raise SystemExit(f"source_sha256 与 {args.ttl} 不符：请核对 --source-sha256")

    snapshot, log = build_snapshot(
        args.ttl,
        chart_version=args.chart_version,
        tag=args.tag,
        commit=args.commit,
        source_sha256=args.source_sha256,
        to_version=args.to,
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(snapshot, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    # 生成日志与快照分离（5.7）：默认写入 tools/build-logs/，绝不进入包数据。
    log_out = args.log_out or default_log_path(args.out)
    log_out.parent.mkdir(parents=True, exist_ok=True)
    log_out.write_text(
        json.dumps(
            {
                "generator": {"name": GENERATOR_NAME, "version": GENERATOR_VERSION},
                "command": ["tools/build_snapshot.py", *argv],
                "retrieved_at": args.retrieved_at,
                "ttl": _repo_relative(args.ttl),
                "out": _repo_relative(args.out),
                "chart_version": args.chart_version,
                "tag": args.tag,
                "commit": args.commit,
                "source_sha256": args.source_sha256,
                **log,
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"写出 {args.out}（{log['interval_count']} 条区间，rank 分布 {log['by_rank']}）")
    print(f"写出 {log_out}（qualifier 分布 {log['qualifier_counts']}）")
    if args.write_index:
        existing_baseline = None
        index_path = args.out.parent / "versions.json"
        if index_path.is_file() and args.baseline is None:
            existing_baseline = json.loads(index_path.read_text(encoding="utf-8")).get("baseline")
        rebuild_index(
            args.out.parent,
            baseline=args.baseline or existing_baseline or str(snapshot["chart_version"]),
        )
    if args.diff_with is not None:
        to_version = str(snapshot["chart_version"])
        write_diff(
            args.out.parent,
            from_version=args.diff_with,
            to_version=to_version,
            out=args.diff_out or args.out.parent / diff_filename(args.diff_with, to_version),
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())

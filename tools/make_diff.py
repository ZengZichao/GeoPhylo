#!/usr/bin/env python3
"""两个内置快照之间的确定性、机器可读 diff 生成器（开发文档 5.7/8.4）。

契约：

- 同一对输入快照必须产出逐字节相同的 JSON；生成过程不读当前时间。
- 头部记录双方的 ``chart_version``、文件名、``payload_sha256`` 与
  ``source_sha256``，因此 diff 可以被独立复核（哈希口径与
  ``geophylo/data/builtin.canonical_payload_bytes`` 完全一致）。
- 覆盖每条受影响记录的**每个**变化字段：记录级字段（``name``、``label``、
  ``aliases``、``rank``、``status``、``color``、``parent_id`` …）逐字段列出；
  边界字段展开为 ``older_boundary.age_ma`` 这类点号路径，避免整块边界被
  当成单一变化。``qualifier`` 在覆盖清单内，因此上游 ``~``（``approximate``）
  的得与失都会出现在 diff 里；``docs/data-policy.md`` 的更新流程正是凭这一
  覆盖度来核验 ``skos:note "uncertain"`` 从 TTL 一路走到 diff、没有中途丢失。
- 新增/删除记录单独列出，不计入变化字段。
- ``boundary_age_changes`` 把同一条共享边界的传播收敛为一条记录：一个边界
  年龄变化 + 它带动的误差/限定词/定义方式变化 + 全部受影响记录 id。
  这一节是文档中「三处边界更新」这类表述的机器可核对来源。
- 排序全部确定：记录按 id、字段按点号路径、边界组按 ``from_age_ma`` 升序。

用法示例::

    python tools/make_diff.py \
        --from geophylo/data/snapshots/ics_chart-2024-12.json \
        --to   geophylo/data/snapshots/ics_chart-2026-06.json \
        --out  geophylo/data/snapshots/diff-2024-12_to_2026-06.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections.abc import Mapping
from pathlib import Path

GENERATOR_NAME = "geophylo-snapshot-diff"
# diff 提取口径的版本：只有当*哪些字段被比较、如何归并*发生变化时才抬升。
GENERATOR_VERSION = "0.1.0"
SCHEMA_VERSION = 1

# 记录里是对象、需要展开成点号路径的字段（其余字段按整体比较）。
BOUNDARY_FIELDS = ("older_boundary", "younger_boundary")
# 共享边界的一致性口径：这四个字段必须逐字段一致（开发文档 7.2）。
_BOUNDARY_SUBKEYS = ("age_ma", "qualifier", "uncertainty_ma", "definition", "source_iri")


class DiffError(Exception):
    """diff 生成失败（输入快照不完整或不成对）。"""


def canonical_payload_bytes(intervals: list[dict] | tuple) -> bytes:
    """与包内实现同口径的规范化 JSON 序列化（键排序、紧凑分隔符、UTF-8）。"""
    return json.dumps(intervals, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )


def payload_sha256(snapshot: Mapping) -> str:
    """按 ``intervals`` 数组计算 payload SHA-256，并与快照自述哈希交叉校验。"""
    declared = str(snapshot.get("hash", {}).get("payload_sha256", ""))
    digest = hashlib.sha256(canonical_payload_bytes(list(snapshot["intervals"]))).hexdigest()
    if declared and declared != digest:
        raise DiffError(
            f"快照 {snapshot.get('chart_version')!r} 的 payload_sha256 不符："
            f"声明 {declared}，实际 {digest}"
        )
    return digest


def _flatten(record: Mapping) -> dict[str, object]:
    """把一条记录压成 ``{字段路径: 值}``；边界字段展开为点号路径。"""
    flat: dict[str, object] = {}
    for key, value in record.items():
        if key in BOUNDARY_FIELDS and isinstance(value, Mapping):
            for sub in _BOUNDARY_SUBKEYS:
                if sub in value:
                    flat[f"{key}.{sub}"] = value[sub]
            for sub, subvalue in value.items():  # 前向兼容：未知的边界子字段
                flat.setdefault(f"{key}.{sub}", subvalue)
        else:
            flat[key] = value
    return flat


def _boundary_groups(
    flat_changes: list[tuple[str, str, object, object]],
    to_records: Mapping[str, Mapping],
) -> list[dict]:
    """把共享边界的逐记录变化收敛成「一处边界变化 + 受影响记录清单」。

    ``flat_changes`` 是 ``(记录 id, 字段路径, 旧值, 新值)`` 的序列。同一处边界
    变化（同一 ``from -> to`` 年龄对）在多条记录里传播时合并为一组；同一数值
    既可作为某条记录的 ``older_boundary`` 又可作为另一条的
    ``younger_boundary``，因此组内不记录单一边界字段，只记录出现过的字段路径。
    误差变化按 (边界字段, 记录 id) 挂到它所属的年龄组上（上游 changeNote 只记
    年龄，2024/12 的误差恢复由生成器的回退补丁产生，见 docs/data-policy.md）。
    """
    groups: dict[tuple[float, float], dict] = {}
    owner: dict[tuple[str, str], dict] = {}
    for interval_id, path, old, new in flat_changes:
        if not path.endswith(".age_ma"):
            continue
        boundary_field = path.split(".", 1)[0]
        boundary = to_records[interval_id][boundary_field]
        if old is None or new is None:
            raise DiffError(f"{interval_id} 的 {path} 变化端不是数值：{old!r} -> {new!r}")
        key = (float(old), float(new))
        group = groups.get(key)
        if group is None:
            group = {
                "from_age_ma": old,
                "to_age_ma": new,
                "uncertainty_ma_from": None,
                "uncertainty_ma_to": None,
                "affected_record_ids": [],
                "affected_fields": [],
                "definitions": set(),
                "qualifiers": set(),
            }
            groups[key] = group
        group["affected_record_ids"].append(interval_id)
        group["affected_fields"].append(path)
        group["definitions"].add(boundary["definition"])
        group["qualifiers"].add(boundary["qualifier"])
        owner[(boundary_field, interval_id)] = group
    for interval_id, path, old, new in flat_changes:
        if not path.endswith(".uncertainty_ma"):
            continue
        group = owner.get((path.split(".", 1)[0], interval_id))
        if group is None:
            raise DiffError(f"{interval_id} 的 {path} 变化找不到对应的边界年龄变化组")
        current = (group["uncertainty_ma_from"], group["uncertainty_ma_to"])
        if current == (None, None):
            group["uncertainty_ma_from"] = old
            group["uncertainty_ma_to"] = new
        elif current != (old, new):
            # 同一处边界变化上出现两种误差迁移：这不是“记哪一条”的口味问题，而是
            # 共享边界不一致或分组错误，因此必须显式失败，绝不静默保留首条。
            raise DiffError(
                f"共享边界 {group['from_age_ma']} -> {group['to_age_ma']} Ma 上有不一致的误差"
                f"变化：{current[0]} -> {current[1]} 与 {old} -> {new}（{interval_id}）"
            )
    ordered = sorted(groups.values(), key=lambda g: (g["from_age_ma"], g["to_age_ma"]))
    result: list[dict] = []
    for group in ordered:
        # 共享边界的 definition/qualifier 必须唯一（加载期一致性校验的口径）。
        if len(group["definitions"]) != 1 or len(group["qualifiers"]) != 1:
            raise DiffError(
                f"共享边界 {group['from_age_ma']} -> {group['to_age_ma']} Ma 的 "
                f"definition/qualifier 在受影响记录间不一致："
                f"{group['definitions']!r} / {group['qualifiers']!r}"
            )
        ids = sorted(set(group["affected_record_ids"]))
        result.append(
            {
                "from_age_ma": group["from_age_ma"],
                "to_age_ma": group["to_age_ma"],
                "definition": next(iter(group["definitions"])),
                "qualifier": next(iter(group["qualifiers"])),
                "uncertainty_ma_from": group["uncertainty_ma_from"],
                "uncertainty_ma_to": group["uncertainty_ma_to"],
                "affected_record_ids": ids,
                "affected_record_count": len(ids),
                "affected_fields": sorted(set(group["affected_fields"])),
            }
        )
    return result


def build_diff(from_snapshot: Mapping, to_snapshot: Mapping) -> dict:
    """生成两份快照的结构化 diff（纯内存，无副作用、不读当前时间）。"""
    for snapshot in (from_snapshot, to_snapshot):
        if "intervals" not in snapshot or "chart_version" not in snapshot:
            raise DiffError("输入快照缺少 chart_version 或 intervals")
    from_records = {r["id"]: r for r in from_snapshot["intervals"]}
    to_records = {r["id"]: r for r in to_snapshot["intervals"]}
    if len(from_records) != len(from_snapshot["intervals"]):
        raise DiffError("起始快照内存在重复 id")
    if len(to_records) != len(to_snapshot["intervals"]):
        raise DiffError("目标快照内存在重复 id")

    shared = sorted(set(from_records) & set(to_records))
    changes: list[dict] = []
    flat_changes: list[tuple[str, str, object, object]] = []
    for interval_id in shared:
        older, newer = from_records[interval_id], to_records[interval_id]
        old_flat, new_flat = _flatten(older), _flatten(newer)
        fields = [
            {
                "path": path,
                "from": old_flat.get(path),
                "to": new_flat.get(path),
            }
            for path in sorted(set(old_flat) | set(new_flat))
            if old_flat.get(path) != new_flat.get(path)
        ]
        if not fields:
            continue
        changes.append(
            {
                "id": interval_id,
                "name": newer["name"],
                "rank": newer["rank"],
                "fields": fields,
            }
        )
        flat_changes.extend(
            (interval_id, field["path"], field["from"], field["to"]) for field in fields
        )

    groups = _boundary_groups(flat_changes, to_records)

    def header(snapshot: Mapping) -> dict:
        return {
            "chart_version": str(snapshot["chart_version"]),
            "file": _snapshot_filename(snapshot),
            "snapshot_revision": snapshot.get("snapshot_revision"),
            "payload_sha256": payload_sha256(snapshot),
            "source_sha256": str(snapshot.get("source", {}).get("source_sha256", "")),
            "interval_count": len(snapshot["intervals"]),
        }

    return {
        "schema_version": SCHEMA_VERSION,
        "generator": {"name": GENERATOR_NAME, "version": GENERATOR_VERSION},
        "from": header(from_snapshot),
        "to": header(to_snapshot),
        "summary": {
            "records_compared": len(shared),
            "records_added": len(to_records) - len(shared),
            "records_removed": len(from_records) - len(shared),
            "records_changed": len(changes),
            "fields_changed": sum(len(c["fields"]) for c in changes),
            "boundary_age_changes": len(groups),
        },
        "boundary_age_changes": groups,
        "changes": changes,
        "added": sorted(set(to_records) - set(from_records)),
        "removed": sorted(set(from_records) - set(to_records)),
    }


def _snapshot_filename(snapshot: Mapping) -> str:
    """快照的文件名（``versions.json`` 与本工具共用的命名规则）。"""
    return f"ics_chart-{str(snapshot['chart_version']).replace('/', '-')}.json"


def serialize(diff: Mapping) -> str:
    """确定性序列化：缩进 2、非 ASCII 不转义、结尾换行（与快照文件同风格）。"""
    return json.dumps(diff, indent=2, ensure_ascii=False) + "\n"


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--from", dest="from_path", type=Path, required=True)
    parser.add_argument("--to", dest="to_path", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)

    diff = build_diff(load(args.from_path), load(args.to_path))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(serialize(diff), encoding="utf-8")
    summary = diff["summary"]
    print(
        f"写出 {args.out}（{diff['from']['chart_version']} -> {diff['to']['chart_version']}："
        f"{summary['fields_changed']} 个字段、{summary['records_changed']} 条记录、"
        f"{summary['boundary_age_changes']} 处边界年龄变化）"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

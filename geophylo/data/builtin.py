"""内置快照的加载、校验与查询后端（规范 2.3/5.6/5.7）。

数据 schema 校验归本模块，不在别处重复。加载即校验：schema、年龄顺序、
父子关系、同 rank 重叠、共享边界一致性和颜色格式，失败抛
``DataValidationError``。
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Iterator, Sequence
from importlib import resources
from typing import Any

from ..exceptions import (
    AmbiguousIntervalError,
    DataValidationError,
    IntervalNotFoundError,
    InvalidRangeError,
    InvalidRankError,
)
from ..validation import CORE_RANKS, normalize_ranks
from ._query import (
    core_rank_pool,
    present_youngest,
    resolve_age,
    search_by_name,
    select_window,
)
from .models import BackendMetadata, Boundary, Interval

__all__ = [
    "RANK_MAP",
    "SNAPSHOT_PACKAGE",
    "SnapshotBackend",
    "available_versions",
    "baseline_version",
    "canonical_payload_bytes",
    "load_snapshot",
    "load_versions_index",
    "snapshot_provenance",
    "validate_snapshot_payload",
]

SNAPSHOT_PACKAGE = "geophylo.data.snapshots"

# 后端层级名到核心 rank 的显式映射；结构节点不通过 ts.ranks 暴露。
RANK_MAP: dict[str, str] = {
    "Eon": "Eon",
    "Era": "Era",
    "Period": "Period",
    "Epoch": "Epoch",
    "Age": "Age",
    "Super-Eon": "structural",
    "Sub-Period": "structural",
}

_TOP_REQUIRED_KEYS = (
    "schema_version",
    "chart_version",
    "snapshot_revision",
    "generator",
    "source",
    "license",
    "hash",
    "intervals",
)
_RECORD_REQUIRED_KEYS = (
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
)
_BOUNDARY_REQUIRED_KEYS = ("age_ma", "qualifier", "uncertainty_ma", "definition", "source_iri")
_VALID_QUALIFIERS = {"defined", "constrained", "approximate", "present", "unknown"}
_VALID_DEFINITIONS = {"gssp", "gssa", "numeric_estimate", "present", "unknown"}
# ``status`` 的取值域：与上游 ``ischart`` 的批准状态一一对应。
# 域外取值（例如上游将来新增的批准状态）必须显式报错，而不是被
# ``str(record["status"])`` 静默接受后进入 ``Interval.status``。
_VALID_STATUSES = {"ratified", "informal", "unknown"}

# 共享边界一致性比较与父子时间包含判断所用的容差（规范 7.2）。
_TOL = 1e-9


def canonical_payload_bytes(intervals: list[dict] | tuple) -> bytes:
    """对 ``intervals`` 数组做规范化 JSON 序列化（键排序、紧凑分隔符、UTF-8）。"""
    return json.dumps(intervals, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )


# --------------------------------------------------------------------------
# 快照文件读取
# --------------------------------------------------------------------------


def load_versions_index() -> dict[str, Any]:
    """读取并校验 ``versions.json``；索引缺失或结构非法即抛 ``DataValidationError``。

    ``versions.json`` 顶层的 ``schema_version`` 是**索引格式**版本（当前 2），与每个快照文件
    顶层的 ``schema_version``（**记录结构**版本，当前 1）不是同一个计数器；本函数只把前者当
    作元数据透传，不参与校验，两个域各自随自己的格式演进。
    """
    try:
        text = (resources.files(SNAPSHOT_PACKAGE) / "versions.json").read_text(encoding="utf-8")
    except FileNotFoundError as exc:  # pragma: no cover - 安装产物损坏
        raise DataValidationError("versions.json 缺失：安装产物不完整") from exc
    index = json.loads(text)
    for key in ("baseline", "versions"):
        if key not in index:
            raise DataValidationError(f"versions.json 缺少必需键 {key!r}")
    for version, meta in index["versions"].items():
        for key in ("file", "payload_sha256"):
            if key not in meta:
                raise DataValidationError(f"versions.json 中 {version!r} 缺少键 {key!r}")
        if not (resources.files(SNAPSHOT_PACKAGE) / meta["file"]).is_file():
            raise DataValidationError(
                f"versions.json 指向的快照文件 {meta['file']!r}（版本 {version!r}）不存在"
            )
    return index


def available_versions() -> list[str]:
    """已发布快照的 chart_version 列表（升序）。"""
    return sorted(load_versions_index()["versions"])


def baseline_version() -> str:
    """``versions.json`` 标注的基线快照版本。"""
    return str(load_versions_index()["baseline"])


def _read_snapshot_file(filename: str) -> dict[str, Any]:
    try:
        text = (resources.files(SNAPSHOT_PACKAGE) / filename).read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise DataValidationError(f"快照文件 {filename!r} 不存在") from exc
    return json.loads(text)


def load_snapshot(version: str | None = None) -> dict[str, Any]:
    """按 chart_version 读取内置快照；``None`` 取基线快照。

    请求未发布的版本抛 ``DataValidationError``，消息含可用版本列表。
    """
    index = load_versions_index()
    if version is None:
        version = index["baseline"]
    meta = index["versions"].get(version)
    if meta is None:
        raise DataValidationError(
            f"未发布的快照版本 {version!r}；可用版本为 {sorted(index['versions'])!r}，"
            "基线快照为 "
            f"{index['baseline']!r}"
        )
    snapshot = _read_snapshot_file(meta["file"])
    expected = meta["payload_sha256"]
    actual = hashlib.sha256(canonical_payload_bytes(snapshot["intervals"])).hexdigest()
    if actual != expected:
        raise DataValidationError(
            f"快照 {version!r} 的 payload_sha256 与 versions.json 不符："
            f"预期 {expected}，实际 {actual}"
        )
    return snapshot


PROVENANCE_FILENAME = "PROVENANCE.md"


def snapshot_provenance(version: str | None = None) -> dict[str, Any]:
    """某个已发布快照的出处披露：机器可读的 ``derived_from`` + 随包发布的文档正文。

    出处披露层不该只活在仓库里：装了包并显式 ``Timescale(version="2024/12")``
    的人也要能读到"这份快照是按上游变更说明回退推导的、不是上游归档"这一
    提示。本函数是那份披露在运行时的唯一消费点——它同时把 ``PROVENANCE.md``
    变成有代码依赖的包数据，因此它从 wheel 里消失时测试即红。

    ``version`` 为 ``None`` 时取基线版本。返回的字典含 ``file``、
    ``payload_sha256``、``derived_from``（非推导快照为 ``None``）与
    ``provenance_document``。版本未发布、或出处文档未随包安装时抛
    ``DataValidationError``。
    """
    index = load_versions_index()
    if version is None:
        version = str(index["baseline"])
    meta = index["versions"].get(version)
    if meta is None:
        raise DataValidationError(
            f"未发布的快照版本 {version!r}；可用版本为 {sorted(index['versions'])!r}"
        )
    doc = resources.files(SNAPSHOT_PACKAGE) / PROVENANCE_FILENAME
    if not doc.is_file():
        raise DataValidationError(
            f"{PROVENANCE_FILENAME} 未随包安装：出处披露缺失（wheel 的 package-data "
            "需包含快照目录下的 *.md）"
        )
    derived = meta.get("derived_from")
    return {
        "version": version,
        "file": str(meta["file"]),
        "payload_sha256": str(meta["payload_sha256"]),
        "derived_from": dict(derived) if isinstance(derived, dict) else None,
        "provenance_document": doc.read_text(encoding="utf-8"),
    }


# --------------------------------------------------------------------------
# schema 与数据完整性校验
# --------------------------------------------------------------------------


def _require_keys(obj: dict, keys: Sequence[str], where: str) -> None:
    for key in keys:
        if key not in obj:
            raise DataValidationError(f"{where} 缺少必需键 {key!r}；全部键必须显式出现")


def _boundary_from_payload(raw: Any, where: str) -> Boundary:
    if not isinstance(raw, dict):
        raise DataValidationError(f"{where} 必须是对象")
    _require_keys(raw, _BOUNDARY_REQUIRED_KEYS, where)
    age = raw["age_ma"]
    if isinstance(age, bool) or not isinstance(age, (int, float)):
        raise DataValidationError(f"{where}.age_ma 必须是数值，得到 {age!r}")
    age = float(age)
    if not math.isfinite(age) or age < 0:
        raise DataValidationError(f"{where}.age_ma 必须是非负有限值，得到 {age!r}")
    uncertainty = raw["uncertainty_ma"]
    if uncertainty is not None:
        if isinstance(uncertainty, bool) or not isinstance(uncertainty, (int, float)):
            raise DataValidationError(f"{where}.uncertainty_ma 必须是数值或 null")
        if not math.isfinite(float(uncertainty)) or float(uncertainty) < 0:
            raise DataValidationError(f"{where}.uncertainty_ma 必须是非负有限值或 null")
    if raw["qualifier"] not in _VALID_QUALIFIERS:
        raise DataValidationError(f"{where}.qualifier 非法：{raw['qualifier']!r}")
    if raw["definition"] not in _VALID_DEFINITIONS:
        raise DataValidationError(f"{where}.definition 非法：{raw['definition']!r}")
    return Boundary(
        age_ma=age,
        qualifier=raw["qualifier"],
        uncertainty_ma=None if uncertainty is None else float(uncertainty),
        definition=raw["definition"],
        source_iri=raw["source_iri"],
    )


def _check_color(color: Any, where: str) -> None:
    if not isinstance(color, str) or len(color) != 7 or color[0] != "#":
        raise DataValidationError(
            f"{where}.color 必须是 #RRGGBB 形式的十六进制颜色，得到 {color!r}"
        )
    if any(c not in "0123456789ABCDEF" for c in color[1:]):
        raise DataValidationError(
            f"{where}.color 必须是 #RRGGBB 形式的十六进制颜色，得到 {color!r}"
        )


def validate_snapshot_payload(snapshot: dict[str, Any]) -> list[Interval]:
    """校验快照并构造 ``Interval`` 列表；任何违规抛 ``DataValidationError``。"""
    _require_keys(snapshot, _TOP_REQUIRED_KEYS, "快照顶层")
    hash_field = snapshot["hash"]
    if not isinstance(hash_field, dict):
        # ``hash`` 是字符串/列表等畸形结构时必须抛公共异常，不能让
        # ``AttributeError`` 逃出公共契约（规范 4.7）。
        raise DataValidationError(f"快照顶层 hash 必须是对象，得到 {type(hash_field).__name__}")
    intervals_raw = snapshot["intervals"]
    if not isinstance(intervals_raw, list) or not intervals_raw:
        raise DataValidationError("intervals 必须是非空数组")

    intervals: list[Interval] = []
    by_id: dict[str, Interval] = {}
    by_source_iri: dict[str, Interval] = {}
    names: set[tuple[str, str]] = set()
    aliases: dict[str, str] = {}

    for record in intervals_raw:
        if not isinstance(record, dict):
            raise DataValidationError("intervals 的每条记录必须是对象")
        _require_keys(record, _RECORD_REQUIRED_KEYS, "区间记录")
        where = f"区间 {record['id']!r}"
        older = _boundary_from_payload(record["older_boundary"], f"{where}.older_boundary")
        younger = _boundary_from_payload(record["younger_boundary"], f"{where}.younger_boundary")
        if not older.age_ma > younger.age_ma:
            raise DataValidationError(
                f"{where} 的 older_ma={older.age_ma} 必须严格大于 younger_ma={younger.age_ma}；"
                "零宽区间属于非法源数据"
            )
        _check_color(record["color"], where)
        if record["status"] not in _VALID_STATUSES:
            raise DataValidationError(
                f"{where} 的 status 非法：{record['status']!r}；"
                f"合法取值为 {sorted(_VALID_STATUSES)!r}"
            )
        if record["rank"] not in RANK_MAP:
            raise DataValidationError(f"{where} 的 rank 非法：{record['rank']!r}")
        expected_class = (
            "geochronologic" if RANK_MAP[record["rank"]] != "structural" else "structural"
        )
        if record["rank_class"] != expected_class:
            raise DataValidationError(
                f"{where} 的 rank_class={record['rank_class']!r} 与 rank={record['rank']!r} 不符"
            )
        interval = Interval(
            id=str(record["id"]),
            source_iri=record["source_iri"],
            name=str(record["name"]),
            label=str(record["label"]),
            aliases=tuple(record["aliases"]),
            rank=str(record["rank"]),
            rank_class=str(record["rank_class"]),
            parent_id=record["parent_id"],
            source_parent_id=record["source_parent_id"],
            status=str(record["status"]),
            color=str(record["color"]),
            older_boundary=older,
            younger_boundary=younger,
        )
        if interval.id in by_id:
            raise DataValidationError(f"区间 ID 重复：{interval.id!r}")
        # source_iri 允许重复：Pridoli 同时是 Age 与 Epoch（上游同一概念在图表
        # 的两个行位显示）；按 source_iri 查询时返回规范序中的首个记录，
        # 因此这里用 setdefault 保留先出现的条目。
        folded = interval.name.casefold()
        if (folded, interval.rank) in names:
            raise DataValidationError(f"rank={interval.rank} 内规范名称重复：{interval.name!r}")
        names.add((folded, interval.rank))
        for alias in interval.aliases:
            key = alias.casefold()
            if key in aliases:
                raise DataValidationError(
                    f"别名 {alias!r} 大小写折叠后不唯一：{aliases[key]!r} 与 {interval.id!r}"
                )
            aliases[key] = interval.id
        by_id[interval.id] = interval
        if interval.source_iri is not None:
            by_source_iri.setdefault(interval.source_iri, interval)
        intervals.append(interval)

    _check_hierarchy(intervals, by_id)
    return intervals


def _check_hierarchy(intervals: list[Interval], by_id: dict[str, Interval]) -> None:
    # 父节点存在、层级无环、子区间被父区间时间包含。
    for interval in intervals:
        parent_id = interval.parent_id
        if parent_id is None:
            continue
        parent = by_id.get(parent_id)
        if parent is None:
            raise DataValidationError(f"区间 {interval.id!r} 的 parent_id {parent_id!r} 不存在")
        if not (
            parent.older_ma >= interval.older_ma - _TOL
            and parent.younger_ma <= interval.younger_ma + _TOL
        ):
            raise DataValidationError(
                f"父区间 {parent.id!r} [{parent.older_ma}, {parent.younger_ma}] 未时间包含子区间 "
                f"{interval.id!r} [{interval.older_ma}, {interval.younger_ma}]"
            )
        visited = {interval.id}
        cursor = parent
        while cursor.parent_id is not None:
            if cursor.id in visited:
                raise DataValidationError(f"层级存在环：{interval.id!r}")
            visited.add(cursor.id)
            nxt = by_id.get(cursor.parent_id)
            if nxt is None:
                break
            cursor = nxt

    # 同 rank 无重叠。
    by_rank: dict[str, list[Interval]] = {}
    for interval in intervals:
        by_rank.setdefault(interval.rank, []).append(interval)
    for rank, group in by_rank.items():
        ordered = sorted(group, key=lambda i: i.older_ma, reverse=True)
        for earlier, later in zip(ordered, ordered[1:], strict=False):
            if later.older_ma > earlier.younger_ma + _TOL:
                raise DataValidationError(
                    f"rank={rank} 存在重叠区间：{earlier.id!r} "
                    f"[{earlier.older_ma}, {earlier.younger_ma}] 与 "
                    f"{later.id!r} [{later.older_ma}, {later.younger_ma}]"
                )

    # 共享边界一致性：同一年龄的边界必须给出相同的 qualifier / uncertainty_ma /
    # definition 三个字段（age_ma 本身是分桶依据，不参与比较）。
    # 分桶键为 round(age_ma, 6)：在 ICS 图表中"同值的两端"就是同一条物理界线
    # （真不相关却恰好同值的情形会被同 rank 重叠检查与父子包含检查先拒掉），
    # 因此这一保守化取舍是有意为之；不一致时报错同时点名冲突的两条记录与两端。
    shared: dict[float, tuple[tuple[str, str], tuple]] = {}
    for interval in intervals:
        for side, boundary in (
            ("older_boundary", interval.older_boundary),
            ("younger_boundary", interval.younger_boundary),
        ):
            key = round(boundary.age_ma, 6)
            signature = (boundary.qualifier, boundary.uncertainty_ma, boundary.definition)
            previous = shared.get(key)
            if previous is not None and previous[1] != signature:
                (prev_id, prev_side) = previous[0]
                raise DataValidationError(
                    f"共享边界 {boundary.age_ma} Ma 的元数据不一致："
                    f"{prev_id}.{prev_side} {previous[1]} 与 "
                    f"{interval.id}.{side} {signature}；"
                    "同一年龄桶内的 qualifier、uncertainty_ma、definition "
                    "三个字段必须完全一致（age_ma 是分桶键，不参与比较）"
                )
            shared.setdefault(key, ((interval.id, side), signature))

    # 完整覆盖：同一父区间下、同一 rank 的子区间（≥2 条）必须**逐段相邻且首尾
    # 对齐**地铺满父区间。"并集宽度 == 父区间宽度"式判据可被等量的间隙 + 等量的
    # 重叠相互抵消而误判通过，因此采用结构化判定：首段 older == 父 older、
    # 末段 younger == 父 younger、相邻段共享边界。
    children: dict[tuple[str, str], list[Interval]] = {}
    for interval in intervals:
        if interval.parent_id is not None:
            children.setdefault((interval.parent_id, interval.rank), []).append(interval)
    for (parent_id, rank), kids in children.items():
        parent = by_id[parent_id]
        if len(kids) < 2:
            continue
        ordered = sorted(kids, key=lambda i: i.older_ma, reverse=True)
        defects: list[str] = []
        if abs(ordered[0].older_ma - parent.older_ma) > _TOL:
            defects.append(
                f"最老子区间 {ordered[0].id} 的老端 {ordered[0].older_ma} 未与父区间老端 "
                f"{parent.older_ma} 对齐"
            )
        if abs(ordered[-1].younger_ma - parent.younger_ma) > _TOL:
            defects.append(
                f"最小子区间 {ordered[-1].id} 的年轻端 {ordered[-1].younger_ma} 未与父区间"
                f"年轻端 {parent.younger_ma} 对齐"
            )
        for older_kid, younger_kid in zip(ordered, ordered[1:], strict=False):
            if abs(older_kid.younger_ma - younger_kid.older_ma) > _TOL:
                defects.append(
                    f"{older_kid.id} 的年轻端 {older_kid.younger_ma} 与 {younger_kid.id} 的"
                    f"老端 {younger_kid.older_ma} 不相接"
                )
        if defects:
            raise DataValidationError(
                f"父区间 {parent_id!r} 的 rank={rank!r} 子区间未逐段完整覆盖：" + "；".join(defects)
            )


# --------------------------------------------------------------------------
# 查询后端
# --------------------------------------------------------------------------


class SnapshotBackend:
    """内置快照后端，实现 :class:`~geophylo.data.backend.TimescaleBackend`。"""

    def __init__(self, snapshot: dict[str, Any]) -> None:
        snapshot = dict(snapshot)
        hash_field = snapshot.get("hash")
        declared = None
        if hash_field is not None:
            if not isinstance(hash_field, dict):
                # 结构异常的 hash 走公共异常，不让 AttributeError 冒泡。
                raise DataValidationError(
                    f"快照顶层 hash 必须是对象，得到 {type(hash_field).__name__}"
                )
            declared = hash_field.get("payload_sha256")
        if declared is not None:
            actual = hashlib.sha256(canonical_payload_bytes(snapshot["intervals"])).hexdigest()
            if actual != declared:
                raise DataValidationError(
                    f"快照 hash.payload_sha256 校验失败：声明 {declared}，实际 {actual}"
                )
        self._intervals = validate_snapshot_payload(snapshot)
        self._by_id = {i.id: i for i in self._intervals}
        # 规范序中的首个记录胜出：source_iri 可重复（Pridoli 双行位），
        # 后写覆盖会让 get_interval() 返回规范序中的最后一条。
        by_iri: dict[str, Interval] = {}
        for interval in self._intervals:
            if interval.source_iri is not None:
                by_iri.setdefault(interval.source_iri, interval)
        self._by_source_iri = by_iri
        self.metadata = BackendMetadata(
            data_version=str(snapshot["chart_version"]),
            software_version=str(snapshot.get("generator", {}).get("version", "0.0.0")),
            has_uncertainty=True,
            has_boundary_definition=True,
            has_stable_ids=True,
            rank_map=dict(RANK_MAP),
        )
        self.chart_version = str(snapshot["chart_version"])

    # -- ID 通道 ----------------------------------------------------------

    def get_interval(self, interval_id: str) -> Interval:
        if not isinstance(interval_id, str):
            raise IntervalNotFoundError(f"interval_id 必须是字符串，得到 {interval_id!r}")
        interval = self._by_id.get(interval_id) or self._by_source_iri.get(interval_id)
        if interval is None:
            hint = ""
            folded = interval_id.casefold()
            match = next((i for i in self._intervals if i.name.casefold() == folded), None)
            if match is not None:
                hint = f"；{interval_id!r} 看起来是名称，请改用 find_by_name()"
            raise IntervalNotFoundError(f"未知的 interval_id {interval_id!r}{hint}")
        return interval

    # -- 名称通道 ---------------------------------------------------------

    def find_by_name(
        self,
        name: str,
        *,
        rank: str | None = None,
        parent: str | None = None,
        case_sensitive: bool = False,
    ) -> Interval:
        if not isinstance(name, str) or not name:
            raise IntervalNotFoundError(f"name 必须是非空字符串，得到 {name!r}")
        pool = self._intervals
        if rank is not None:
            if rank not in CORE_RANKS:
                raise InvalidRankError(f"非法 rank {rank!r}；核心 rank 为 {list(CORE_RANKS)!r}")
            pool = [i for i in pool if i.rank == rank]
        else:
            # rank=None 时默认只搜 geochronologic 区间，结构节点（structural）
            # 不参与歧义计数（文档：结构节点只作 parent_id 锚点存在）。
            pool = [i for i in pool if i.rank_class == "geochronologic"]
        if parent is not None:
            pool = [i for i in pool if i.parent_id == parent]

        # 通道优先级与精确匹配优先的判定由 ``_query.search_by_name`` 统一实现
        # （与 pyrolite 后端共享同一份语义）。
        verdict, channel, hits = search_by_name(pool, name, case_sensitive=case_sensitive)
        if verdict == "found":
            assert channel is not None  # search_by_name 只在有通道时给出 found
            return hits[0]
        if verdict == "ambiguous":
            raise AmbiguousIntervalError(
                f"名称查询 {name!r} 命中 {len(hits)} 个候选："
                + ", ".join(f"{i.name}({i.id})" for i in hits)
                + "；请用 rank= 或 parent= 消歧，或改用 get_interval() 按稳定 ID 精确查询",
                candidates=[i.id for i in hits],
            )
        raise IntervalNotFoundError(
            f"名称 {name!r} 未命中任何区间（name/aliases/label 三个通道均无匹配；"
            f"rank={rank!r}, parent={parent!r}）"
        )

    # -- 年龄通道 ---------------------------------------------------------

    def find_by_age(self, age_ma: float, *, rank: str | None = None) -> Interval:
        if isinstance(age_ma, bool) or not isinstance(age_ma, (int, float)):
            raise InvalidRangeError(f"age_ma 必须是数值，得到 {age_ma!r}")
        age = float(age_ma)
        if not math.isfinite(age):
            raise InvalidRangeError(f"age_ma 必须是有限值，得到 {age_ma!r}")
        if age < 0:
            raise InvalidRangeError(f"age_ma={age} 不能为负；年龄以 Ma 为单位且越大越老")
        if rank is not None and rank not in CORE_RANKS:
            raise InvalidRankError(f"非法 rank {rank!r}；核心 rank 为 {list(CORE_RANKS)!r}")

        pool = core_rank_pool(self._intervals, rank)
        if not pool:
            raise IntervalNotFoundError(
                f"age_ma={age_ma!r} 在 rank={rank!r} 下无区间可用；"
                f"可用的 rank 为 {list(CORE_RANKS)!r}"
            )

        # 0.0 Ma 显式归入最年轻区间（不依赖普通不等式）；吸附到 0.0 的输入按
        # 第 3 条回落（殊途同归）。
        hit, snapped = resolve_age(pool, age)
        if age == 0.0 or snapped == 0.0:
            present = present_youngest(pool)
            if present:
                return min(present, key=lambda i: i.older_ma)
        if hit is not None:
            return hit
        # 吸附容差：与某边界距离 <= 1e-9 的输入先吸附到该边界，再按「边界值归属
        # 于以其为 older_ma 的较年轻区间」归属。多个 rank 同时命中时返回最具体
        # （最靠核心末端）的区间，保证确定性（以上均由 ``_query`` 实现）。
        oldest = max(i.older_ma for i in pool)
        rank_label = repr(rank) if rank is not None else "None"
        raise IntervalNotFoundError(
            f"age_ma={age_ma!r} 超出 rank={rank_label} 的覆盖范围（最老边界 {oldest} Ma，"
            f"可用 rank {list(CORE_RANKS)!r}）；本库不做外推"
        )

    # -- 遍历 -------------------------------------------------------------

    def iter_intervals(
        self,
        *,
        ranks: str | Sequence[str] | None = None,
        min_age: float | None = None,
        max_age: float | None = None,
    ) -> Iterator[Interval]:
        """窗口遍历：``ranks=None`` 即五个核心 rank（与 pyrolite 后端同语义）。"""
        if ranks is None:
            selected = CORE_RANKS
        else:
            selected = normalize_ranks(ranks)
        lo = 0.0 if min_age is None else float(self._validate_bound("min_age", min_age))
        hi = math.inf if max_age is None else float(self._validate_bound("max_age", max_age))
        if lo >= hi:
            raise InvalidRangeError(f"要求 min_age < max_age，得到 min_age={lo}, max_age={hi}")
        return iter(select_window(self._intervals, selected, lo, hi, tol=_TOL))

    @staticmethod
    def _validate_bound(name: str, value: float) -> float:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise InvalidRangeError(f"{name} 必须是数值，得到 {value!r}")
        number = float(value)
        if not math.isfinite(number):
            raise InvalidRangeError(f"{name} 必须是有限值，得到 {value!r}")
        if number < 0:
            raise InvalidRangeError(f"{name}={number} 不能为负")
        return number

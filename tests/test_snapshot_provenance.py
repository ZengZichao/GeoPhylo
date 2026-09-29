"""快照出处工件的防漂移测试（开发文档 5.7/7.7/8.4）。

覆盖四类「披露可以与数据悄悄脱钩」的情形：

- ``diff-2024-12_to_2026-06.json`` 必须与两份快照的当前字节完全对应；
- ``versions.json`` 必须能被 ``rebuild_index()`` 逐字节重现（含 ``derived_from``
  与两把哈希），且它自述的每一项事实都能被独立复核；
- 两份快照与两份生成日志必须是 ``tools/build_snapshot.py`` 对 pinned 输入的真实
  产物（同一命令重跑，快照字节不变）；
- ``PROVENANCE.md`` / ``docs/data-policy.md`` 的叙述必须与工件一致——而且断言
  本身不能是自证的（命中的子串不得躺在否定句里）。

哨兵断言是版本化的基准值：快照更新时必须同步更新并在 CHANGELOG 说明。
"""

from __future__ import annotations

import ast
import copy
import hashlib
import importlib.util
import json
import re
import shutil
import subprocess
from pathlib import Path
from types import ModuleType

import pytest

from geophylo.data.builtin import canonical_payload_bytes

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT_DIR = PROJECT_ROOT / "geophylo" / "data" / "snapshots"
DIFF_PATH = SNAPSHOT_DIR / "diff-2024-12_to_2026-06.json"
BUILD_LOG_DIR = PROJECT_ROOT / "tools" / "build-logs"
TTL_PATH = PROJECT_ROOT / "tools" / "source" / "ics-chart-v2026-06.5.ttl"

# 哨兵：2024/12 -> 2026/06 的三处边界修订（docs/data-policy.md 引用同一组值）。
SENTINEL_AGE_TRANSITIONS = [(246.7, 247.0), (249.9, 250.8), (259.51, 259.857)]
SENTINEL_RECORDS_CHANGED = 9
SENTINEL_FIELDS_CHANGED = 14
SENTINEL_AGE_FIELDS_CHANGED = 10

PINNED = {
    "commit": "44d1043ecf295cce1be03b3fc5fa95ca65fe770b",
    "tag": "v2026-06.5",
    "source_sha256": "0158959e8fdae2a8bdbb14ca3e424d2370362cd8dfc8af86e7be73c74368b355",
    "retrieved_at": "2026-09-11T00:00:00Z",
}

# 出处披露层的组成：这几件必须整层纳入版本控制，否则披露随时会脱钩。
PROVENANCE_LAYER = [
    "geophylo/data/snapshots/PROVENANCE.md",
    "geophylo/data/snapshots/diff-2024-12_to_2026-06.json",
    "tools/make_diff.py",
    "tools/build-logs/ics_chart-2026-06.log.json",
    "tools/build-logs/ics_chart-2024-12.log.json",
    "tests/test_snapshot_provenance.py",
    "docs/adr/ADR-5-per-boundary-state-model.md",
]


def _in_git_checkout() -> bool:
    """当前树是否受 git 管理——解包的发行归档不是，仓库里才是。"""
    git = shutil.which("git")
    if git is None:
        return False
    return (
        subprocess.run(
            [git, "rev-parse", "--is-inside-work-tree"],
            cwd=str(PROJECT_ROOT),
            capture_output=True,
        ).returncode
        == 0
    )


def _load_tool(path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(path.stem, str(path))
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def make_diff() -> ModuleType:
    return _load_tool(PROJECT_ROOT / "tools" / "make_diff.py")


@pytest.fixture(scope="module")
def build_snapshot() -> ModuleType:
    return _load_tool(PROJECT_ROOT / "tools" / "build_snapshot.py")


@pytest.fixture(scope="module")
def shipped_diff() -> dict:
    return json.loads(DIFF_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def pair() -> tuple[dict, dict]:
    def load(name: str) -> dict:
        return json.loads((SNAPSHOT_DIR / name).read_text(encoding="utf-8"))

    return load("ics_chart-2024-12.json"), load("ics_chart-2026-06.json")


def _rehashed(snapshot: dict) -> dict:
    """变异后的快照要重算自述哈希，否则 diff 工具会先拒绝输入（那是对的）。"""
    snapshot["hash"]["payload_sha256"] = hashlib.sha256(
        canonical_payload_bytes(snapshot["intervals"])
    ).hexdigest()
    return snapshot


def _write(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _rehash(snapshot: dict, build_snapshot: ModuleType) -> dict:
    """把两把自述哈希都刷新到与内容一致（用于只测某一条校验）。"""
    snapshot["hash"]["payload_sha256"] = hashlib.sha256(
        canonical_payload_bytes(snapshot["intervals"])
    ).hexdigest()
    snapshot["hash"]["provenance_sha256"] = build_snapshot.provenance_digest(snapshot)
    return snapshot


def _log(version: str) -> dict:
    return json.loads((BUILD_LOG_DIR / f"ics_chart-{version}.log.json").read_text("utf-8"))


class TestDiffArtifactMatchesData:
    def test_regenerated_diff_is_byte_identical(self, make_diff, pair):
        """内存重算 == 随包发布的 diff 文件，逐字节。"""
        regenerated = make_diff.serialize(make_diff.build_diff(pair[0], pair[1]))
        assert regenerated == DIFF_PATH.read_text(encoding="utf-8")

    def test_diff_is_deterministic_across_reloads(self, make_diff, pair):
        first = make_diff.serialize(make_diff.build_diff(*pair))
        reloaded = (
            json.loads((SNAPSHOT_DIR / "ics_chart-2024-12.json").read_text(encoding="utf-8")),
            json.loads((SNAPSHOT_DIR / "ics_chart-2026-06.json").read_text(encoding="utf-8")),
        )
        assert make_diff.serialize(make_diff.build_diff(*reloaded)) == first

    def test_header_records_both_hashes_and_versions(self, make_diff, shipped_diff, pair):
        index = json.loads((SNAPSHOT_DIR / "versions.json").read_text(encoding="utf-8"))
        for side, snapshot in zip(("from", "to"), pair, strict=True):
            header = shipped_diff[side]
            version = str(snapshot["chart_version"])
            digest = make_diff.payload_sha256(snapshot)
            assert header["chart_version"] == version
            assert header["payload_sha256"] == digest
            assert header["payload_sha256"] == snapshot["hash"]["payload_sha256"]
            assert header["payload_sha256"] == index["versions"][version]["payload_sha256"]
            assert header["source_sha256"] == snapshot["source"]["source_sha256"]
            assert header["snapshot_revision"] == 1
        assert shipped_diff["generator"]["name"] == "geophylo-snapshot-diff"
        assert shipped_diff["schema_version"] == 1

    def test_diff_reports_qualifier_changes(self, make_diff, pair):
        """数据政策要求 diff 覆盖 ``~`` 标记——这里证明它确实做得到。

        用真实快照做单字段变异：只把一条记录的 ``qualifier`` 改掉，diff 必须
        把它列为唯一的字段变化（若 ``approximate`` 在快照里永不出现，这条要求
        就无从满足）。
        """
        base = json.loads(json.dumps(pair[1]))
        mutated = json.loads(json.dumps(pair[1]))
        target = next(
            r for r in mutated["intervals"] if r["older_boundary"]["qualifier"] == "approximate"
        )
        target["older_boundary"]["qualifier"] = "defined"
        diff = make_diff.build_diff(base, _rehashed(mutated))
        assert diff["summary"]["fields_changed"] == 1
        assert diff["summary"]["records_changed"] == 1
        assert diff["changes"][0]["fields"][0]["path"] == "older_boundary.qualifier"
        assert diff["changes"][0]["fields"][0]["to"] == "defined"
        # 反向（出厂 -> 丢掉 ``~``）同样必须被 diff 抓到。
        reverse = make_diff.build_diff(_rehashed(mutated), base)
        assert [f["path"] for c in reverse["changes"] for f in c["fields"]] == [
            "older_boundary.qualifier"
        ]

    def test_diff_rejects_conflicting_margin_transitions(self, make_diff, pair):
        """同一边界组上出现第二种误差迁移时不得静默保留首条。"""
        base = json.loads(json.dumps(pair[0]))
        mutated = json.loads(json.dumps(pair[1]))
        by_id = {r["id"]: r for r in base["intervals"]}
        # 人为制造矛盾：在既有的一处年龄变化上挂两种不同的误差迁移。
        group = next(
            (record, by_id[record["id"]])
            for record in mutated["intervals"]
            if record["older_boundary"]["age_ma"] != by_id[record["id"]]["older_boundary"]["age_ma"]
            and record["older_boundary"]["age_ma"] == 247.0
        )
        newer, older = group
        older["older_boundary"]["uncertainty_ma"] = 0.7
        newer["older_boundary"]["uncertainty_ma"] = 0.9
        # 同组第二条记录带着第三种写法，制造不一致。
        for record in mutated["intervals"]:
            if (
                record is not newer
                and record["older_boundary"]["age_ma"] == 247.0
                and by_id[record["id"]]["older_boundary"]["age_ma"] == 246.7
            ):
                record["older_boundary"]["uncertainty_ma"] = 0.11
                by_id[record["id"]]["older_boundary"]["uncertainty_ma"] = 0.22
        with pytest.raises(make_diff.DiffError, match="不一致的误差"):
            make_diff.build_diff(_rehashed(base), _rehashed(mutated))

    def test_diff_rejects_null_age_transition(self, make_diff, pair):
        """``float(None)`` 的崩溃路径必须是显式报错。"""
        base = json.loads(json.dumps(pair[1]))
        mutated = json.loads(json.dumps(pair[1]))
        mutated["intervals"][0]["older_boundary"]["age_ma"] = None
        with pytest.raises(make_diff.DiffError, match="不是数值"):
            make_diff.build_diff(base, _rehashed(mutated))


class TestDiffCompleteness:
    """diff 不得少报或多报任何变化字段。"""

    @staticmethod
    def _independent_changed_fields(from_snapshot: dict, to_snapshot: dict) -> dict[str, set[str]]:
        older = {r["id"]: r for r in from_snapshot["intervals"]}
        newer = {r["id"]: r for r in to_snapshot["intervals"]}
        out: dict[str, set[str]] = {}
        for interval_id in set(older) & set(newer):
            paths = set()
            for key in set(older[interval_id]) | set(newer[interval_id]):
                old_value = older[interval_id].get(key)
                new_value = newer[interval_id].get(key)
                if old_value == new_value:
                    continue
                if key.endswith("_boundary") and isinstance(old_value, dict):
                    paths.update(
                        f"{key}.{sub}"
                        for sub in set(old_value) | set(new_value)
                        if old_value.get(sub) != (new_value or {}).get(sub)
                    )
                else:
                    paths.add(key)
            if paths:
                out[interval_id] = paths
        return out

    def test_every_changed_field_is_listed(self, pair, shipped_diff):
        expected = self._independent_changed_fields(*pair)
        reported = {c["id"]: {f["path"] for f in c["fields"]} for c in shipped_diff["changes"]}
        assert reported == expected
        assert expected, "两份快照已无差异：本类的哨兵断言将失去意义"
        assert set(shipped_diff["added"]) == set()
        assert set(shipped_diff["removed"]) == set()

    def test_summary_counts(self, shipped_diff):
        summary = shipped_diff["summary"]
        assert summary["records_compared"] == 179
        assert summary["records_changed"] == SENTINEL_RECORDS_CHANGED
        assert summary["fields_changed"] == SENTINEL_FIELDS_CHANGED
        assert summary["boundary_age_changes"] == len(SENTINEL_AGE_TRANSITIONS)
        assert summary["records_added"] == 0 and summary["records_removed"] == 0
        age_fields = [
            f
            for change in shipped_diff["changes"]
            for f in change["fields"]
            if f["path"].endswith(".age_ma")
        ]
        assert len(age_fields) == SENTINEL_AGE_FIELDS_CHANGED

    def test_boundary_groups_match_the_three_revisions(self, shipped_diff):
        groups = shipped_diff["boundary_age_changes"]
        assert [(g["from_age_ma"], g["to_age_ma"]) for g in groups] == SENTINEL_AGE_TRANSITIONS
        for group in groups:
            assert group["affected_record_count"] == len(set(group["affected_record_ids"]))
            assert group["affected_record_count"] >= 2  # 共享边界必然跨记录传播
        wuchiapingian = groups[-1]
        assert wuchiapingian["definition"] == "gssp"
        assert wuchiapingian["qualifier"] == "constrained"
        assert (wuchiapingian["uncertainty_ma_from"], wuchiapingian["uncertainty_ma_to"]) == (
            0.21,
            0.084,
        )

    def test_group_record_lists_agree_with_changes(self, shipped_diff):
        for group in shipped_diff["boundary_age_changes"]:
            transition = (group["from_age_ma"], group["to_age_ma"])
            derived = {
                change["id"]
                for change in shipped_diff["changes"]
                if any(
                    f["path"].endswith(".age_ma")
                    and (f["from"], f["to"]) == transition
                    and f["path"] in group["affected_fields"]
                    for f in change["fields"]
                )
            }
            assert derived == set(group["affected_record_ids"])


class TestVersionsIndexProvenance:
    def test_index_rebuild_is_byte_identical(self, build_snapshot, tmp_path):
        """重跑索引生成器不得改变 versions.json 的任何一个字节。"""
        staging = tmp_path / "snapshots"
        staging.mkdir()
        for name in ("ics_chart-2024-12.json", "ics_chart-2026-06.json"):
            shutil.copy(SNAPSHOT_DIR / name, staging / name)
        build_snapshot.rebuild_index(staging, baseline="2026/06")
        assert (staging / "versions.json").read_bytes() == (
            SNAPSHOT_DIR / "versions.json"
        ).read_bytes()

    def test_payload_and_provenance_hashes_hold(self, build_snapshot, pair):
        """两把哈希各自独立覆盖"数据"与"版本标签/来源块"。"""
        for snapshot in pair:
            recomputed = json.loads(json.dumps(snapshot))
            assert (
                build_snapshot.provenance_digest(recomputed)
                == snapshot["hash"]["provenance_sha256"]
            )
        assert pair[0]["hash"]["payload_sha256"] != pair[1]["hash"]["payload_sha256"]

    def test_relabelled_snapshot_is_detected(self, build_snapshot, pair):
        """只改 ``chart_version``/``source.commit`` 也会被 provenance 哈希抓到。"""
        tampered = json.loads(json.dumps(pair[1]))
        tampered["chart_version"] = "2030/01"
        assert build_snapshot.provenance_digest(tampered) != pair[1]["hash"]["provenance_sha256"]
        tampered2 = json.loads(json.dumps(pair[1]))
        tampered2["source"]["commit"] = "0" * 40
        assert build_snapshot.provenance_digest(tampered2) != pair[1]["hash"]["provenance_sha256"]

    def test_rebuild_fails_on_hand_edited_revert_count(self, build_snapshot, tmp_path):
        """手写计数一旦与日志不符，索引重建必须拒绝而不是搬运谎言。"""
        staging = tmp_path / "snapshots"
        staging.mkdir()
        for name in ("ics_chart-2024-12.json", "ics_chart-2026-06.json"):
            shutil.copy(SNAPSHOT_DIR / name, staging / name)
        derived = json.loads((staging / "ics_chart-2024-12.json").read_text("utf-8"))
        derived["derived_from"]["reverted_boundary_count"] = 11
        _rehash(derived, build_snapshot)  # 让 provenance 哈希先闭嘴，只留计数这一处不符
        _write(staging / "ics_chart-2024-12.json", derived)
        with pytest.raises(SystemExit) as excinfo:
            build_snapshot.rebuild_index(staging, baseline="2026/06")
        assert "说谎" in str(excinfo.value)

    def test_rebuild_fails_on_edited_provenance_hash(self, build_snapshot, tmp_path):
        """版本标签被改而哈希没重算时，provenance 哈希这一关就拦住。"""
        staging = tmp_path / "snapshots"
        staging.mkdir()
        for name in ("ics_chart-2024-12.json", "ics_chart-2026-06.json"):
            shutil.copy(SNAPSHOT_DIR / name, staging / name)
        derived = json.loads((staging / "ics_chart-2024-12.json").read_text("utf-8"))
        derived["chart_version"] = "2024/11"  # 只改标签，不改哈希
        _write(staging / "ics_chart-2024-12.json", derived)
        with pytest.raises(SystemExit) as excinfo:
            build_snapshot.rebuild_index(staging, baseline="2026/06")
        assert "provenance_sha256" in str(excinfo.value)

    def test_rebuild_fails_on_edited_pinned_input_hash(self, build_snapshot, tmp_path):
        """versions.json 声称的 pinned 输入哈希必须能在磁盘上复核。"""
        staging = tmp_path / "snapshots"
        staging.mkdir()
        for name in ("ics_chart-2024-12.json", "ics_chart-2026-06.json"):
            snapshot = json.loads((SNAPSHOT_DIR / name).read_text("utf-8"))
            snapshot["derivation"]["pinned_input"]["sha256"] = "f" * 64
            _rehash(snapshot, build_snapshot)
            _write(staging / name, snapshot)
        with pytest.raises(SystemExit) as excinfo:
            build_snapshot.rebuild_index(staging, baseline="2026/06")
        assert "SHA-256 不符" in str(excinfo.value)

    def test_rebuild_fails_when_snapshots_disagree_on_the_input(self, build_snapshot, tmp_path):
        staging = tmp_path / "snapshots"
        staging.mkdir()
        for name in ("ics_chart-2024-12.json", "ics_chart-2026-06.json"):
            shutil.copy(SNAPSHOT_DIR / name, staging / name)
        derived = json.loads((staging / "ics_chart-2024-12.json").read_text("utf-8"))
        derived["derivation"]["pinned_input"]["sha256"] = "a" * 64
        _rehash(derived, build_snapshot)
        _write(staging / "ics_chart-2024-12.json", derived)
        with pytest.raises(SystemExit) as excinfo:
            build_snapshot.rebuild_index(staging, baseline="2026/06")
        assert "不同的哈希" in str(excinfo.value)

    def test_derived_snapshot_declares_its_parent(self):
        index = json.loads((SNAPSHOT_DIR / "versions.json").read_text(encoding="utf-8"))
        derived = index["versions"]["2024/12"]
        assert index["versions"]["2026/06"].get("derived_from") is None
        provenance = derived["derived_from"]
        assert provenance["chart_version"] == "2026/06"
        assert provenance["method"] == "revert-upstream-change-notes"
        assert provenance["source_file"] == "tools/source/ics-chart-v2026-06.5.ttl"
        assert provenance["generator_flag"] == "--to 2024/12"
        assert (PROJECT_ROOT / provenance["generation_log"]).is_file()

    def test_derived_source_block_is_identical_to_parent(self, pair):
        """推导快照的 source 块与母快照逐字节相同——这正是必须披露的事实。"""
        assert pair[0]["source"] == pair[1]["source"]
        assert pair[0]["source"]["commit"] == PINNED["commit"]
        assert pair[0]["source"]["tag"] == PINNED["tag"]

    def test_index_matches_the_snapshot_files(self, build_snapshot):
        index = json.loads((SNAPSHOT_DIR / "versions.json").read_text(encoding="utf-8"))
        for version, meta in index["versions"].items():
            snapshot = json.loads((SNAPSHOT_DIR / meta["file"]).read_text("utf-8"))
            assert meta["chart_version"] == version == snapshot["chart_version"]
            assert meta["snapshot_revision"] == snapshot["snapshot_revision"]
            assert meta["generator"] == snapshot["generator"]
            assert (
                meta["payload_sha256"]
                == build_snapshot.hashlib.sha256(
                    build_snapshot.canonical_payload(snapshot["intervals"])
                ).hexdigest()
            )

    def test_each_chart_version_publishes_a_single_revision(self, pair):
        """快照不携带任何"历史修订"字段：每个 chart 版本只发布一个修订。"""
        for snapshot in pair:
            assert snapshot["snapshot_revision"] == 1
            assert "supersedes" not in snapshot
        index = json.loads((SNAPSHOT_DIR / "versions.json").read_text(encoding="utf-8"))
        for meta in index["versions"].values():
            assert meta["snapshot_revision"] == 1
            assert "supersedes" not in meta


class TestSnapshotsAndLogsAreRealProducts:
    def test_snapshots_regenerate_byte_identically(self, build_snapshot, tmp_path):
        """pinned 输入 + 同一命令 = 与随包发布文件逐字节相同（生成日志的凭据）。"""
        for version, to_version in (("2026/06", None), ("2024/12", "2024/12")):
            snapshot, log = build_snapshot.build_snapshot(
                TTL_PATH,
                chart_version=version,
                tag=PINNED["tag"],
                commit=PINNED["commit"],
                source_sha256=PINNED["source_sha256"],
                to_version=to_version,
            )
            path = SNAPSHOT_DIR / f"ics_chart-{version.replace('/', '-')}.json"
            rendered = json.dumps(snapshot, indent=2, ensure_ascii=False) + "\n"
            assert rendered == path.read_text(encoding="utf-8"), version
            assert log["parse_stats"] == snapshot["derivation"]["parse_stats"]

    def test_end_to_end_cli_reproduces_shipped_artifacts(self, tmp_path):
        """整条 CLI（含索引与日志）在临时目录里重现出厂工件字节。"""
        code = PROJECT_ROOT / "tools" / "build_snapshot.py"
        for version, extra in (("2026/06", []), ("2024/12", ["--to", "2024/12"])):
            out = tmp_path / f"ics_chart-{version.replace('/', '-')}.json"
            argv = [
                "--ttl",
                str(TTL_PATH),
                "--chart-version",
                version,
                "--tag",
                PINNED["tag"],
                "--commit",
                PINNED["commit"],
                "--source-sha256",
                PINNED["source_sha256"],
                "--retrieved-at",
                PINNED["retrieved_at"],
                "--out",
                str(out),
                "--log-out",
                str(tmp_path / f"{out.stem}.log.json"),
                *extra,
            ]
            module = _load_tool(code)
            assert module.main(argv) == 0
            assert out.read_bytes() == (SNAPSHOT_DIR / out.name).read_bytes()
        # 索引与 diff 也从同一条命令链复现（--write-index 需要两份快照同目录）。
        module = _load_tool(code)
        assert (
            module.main(
                [
                    "--ttl",
                    str(TTL_PATH),
                    "--chart-version",
                    "2026/06",
                    "--tag",
                    PINNED["tag"],
                    "--commit",
                    PINNED["commit"],
                    "--source-sha256",
                    PINNED["source_sha256"],
                    "--retrieved-at",
                    PINNED["retrieved_at"],
                    "--out",
                    str(tmp_path / "ics_chart-2026-06.json"),
                    "--log-out",
                    str(tmp_path / "ics_chart-2026-06.log.json"),
                    "--write-index",
                    "--diff-with",
                    "2024/12",
                ]
            )
            == 0
        )
        assert (tmp_path / "versions.json").read_bytes() == (
            SNAPSHOT_DIR / "versions.json"
        ).read_bytes()
        assert (tmp_path / DIFF_PATH.name).read_bytes() == DIFF_PATH.read_bytes()

    def test_wrong_source_hash_fails_the_build(self, tmp_path):
        """--source-sha256 与磁盘上的 vendored 副本不符时直接拒产。"""
        module = _load_tool(PROJECT_ROOT / "tools" / "build_snapshot.py")
        argv = [
            "--ttl",
            str(TTL_PATH),
            "--chart-version",
            "2026/06",
            "--tag",
            PINNED["tag"],
            "--commit",
            PINNED["commit"],
            "--source-sha256",
            "0" * 64,
            "--retrieved-at",
            PINNED["retrieved_at"],
            "--out",
            str(tmp_path / "out.json"),
        ]
        with pytest.raises(SystemExit, match="source_sha256"):
            module.main(argv)
        assert not (tmp_path / "out.json").exists()

    def test_generation_logs_exist_for_both_snapshots(self):
        for version in ("2026-06", "2024-12"):
            path = BUILD_LOG_DIR / f"ics_chart-{version}.log.json"
            assert path.is_file(), f"缺少生成日志 {path.relative_to(PROJECT_ROOT)}"
            log = json.loads(path.read_text(encoding="utf-8"))
            assert log["interval_count"] == 179
            assert log["retrieved_at"] == PINNED["retrieved_at"]
            assert log["out"] == f"geophylo/data/snapshots/ics_chart-{version}.json"
            # 日志必须自述它是怎么被产出的，否则"由上文同一条命令产出"无法核验。
            command = log["command"]
            assert command[0] == "tools/build_snapshot.py"
            assert command[command.index("--chart-version") + 1] == version.replace("-", "/")
            assert command[command.index("--tag") + 1] == PINNED["tag"]
            assert command[command.index("--ttl") + 1] == "tools/source/ics-chart-v2026-06.5.ttl"
            assert log["chart_version"] == version.replace("-", "/")
            assert log["tag"] == PINNED["tag"]
            assert log["commit"] == PINNED["commit"]
            assert log["source_sha256"] == PINNED["source_sha256"]
            assert log["generator"] == {"name": "geophylo-snapshot", "version": "0.1.0"}

    def test_baseline_log_records_no_reverts(self):
        log = _log("2026-06")
        assert log["reverted_boundaries"] == []
        assert log["to_version"] is None
        assert log["by_rank"] == {
            "Age": 102,
            "Eon": 4,
            "Epoch": 38,
            "Era": 10,
            "Period": 22,
            "Sub-Period": 2,
            "Super-Eon": 1,
        }
        # 误差搬家不得制造虚假冲突并写进日志。
        assert log["warnings"] == []
        assert [r["method"] for r in log["integrity_repairs"]] == [
            "snap-minority-rounding-variant",
            "same-rank-overlap-children-union",
        ]
        assert log["qualifier_counts"]["approximate"] == 36

    def test_derived_log_reverts_are_the_diff_age_changes(self, shipped_diff):
        """日志里的回退清单与 diff 里的边界年龄变化是同一批事实的两种表述。"""
        log = _log("2024-12")
        entries = log["reverted_boundaries"]
        assert all(isinstance(e, dict) for e in entries)
        parsed = {(e["to_mya"], e["from_mya"]) for e in entries}
        assert len(entries) == SENTINEL_AGE_FIELDS_CHANGED
        assert parsed == {tuple(t) for t in SENTINEL_AGE_TRANSITIONS}
        assert {e["concept"] for e in entries} >= {"Anisian", "Olenekian", "Wuchiapingian"}
        for entry in entries:
            assert entry["method"] == "revert-change-note"
            assert entry["change_note"].startswith("2026-06:")
            assert entry["boundary"] in {"beginning", "end"}
        from_diff = {
            (f["from"], f["to"])
            for change in shipped_diff["changes"]
            for f in change["fields"]
            if f["path"].endswith(".age_ma")
        }
        assert parsed == from_diff
        assert [g["affected_record_count"] for g in shipped_diff["boundary_age_changes"]] == [
            4,
            2,
            4,
        ]

    def test_derived_log_revert_count_matches_the_index(self):
        """versions.json 里的回退计数 == 日志实长（不是手写常量）。"""
        index = json.loads((SNAPSHOT_DIR / "versions.json").read_text(encoding="utf-8"))
        declared = index["versions"]["2024/12"]["derived_from"]["reverted_boundary_count"]
        assert declared == len(_log("2024-12")["reverted_boundaries"])
        snapshot = json.loads((SNAPSHOT_DIR / "ics_chart-2024-12.json").read_text("utf-8"))
        assert snapshot["derived_from"]["reverted_boundary_count"] == declared
        reverts = [
            r
            for r in snapshot["derivation"]["integrity_repairs"]
            if r["method"] == "revert-change-note"
        ]
        assert len(reverts) == declared

    def test_diff_generator_is_wired_into_build_snapshot(self, build_snapshot, tmp_path):
        """``--diff-with`` 走的是同一份 diff 代码，产物与随包文件一致。"""
        out = tmp_path / DIFF_PATH.name
        build_snapshot.write_diff(
            SNAPSHOT_DIR, from_version="2024/12", to_version="2026/06", out=out
        )
        assert out.read_bytes() == DIFF_PATH.read_bytes()
        assert build_snapshot.diff_filename("2024/12", "2026/06") == DIFF_PATH.name


class TestRevertFlagIsLive:
    """``--to`` 必须真的决定回退集合，而不是被硬编码字面量架空。"""

    @staticmethod
    def _concepts(build_snapshot) -> dict:
        return build_snapshot.parse_ttl(
            (PROJECT_ROOT / "tools" / "source" / "ics-chart-v2026-06.5.ttl").read_text("utf-8")
        )

    def test_target_version_selects_the_revert_set(self, build_snapshot):
        concepts = {k: json.loads(json.dumps(v)) for k, v in self._concepts(build_snapshot).items()}
        reverted, stamps = build_snapshot.revert_change_notes(concepts, "2024/12")
        assert len(reverted) == 10
        assert stamps == ["2026-06"]
        # 2026/12 之后没有任何 changeNote 可比 -> 0 条回退（下条断言它必须显式失败）。
        later = {k: json.loads(json.dumps(v)) for k, v in self._concepts(build_snapshot).items()}
        with pytest.raises(build_snapshot.BuildError, match="没有回退任何边界"):
            build_snapshot.revert_change_notes(later, "2026/12")

    def test_reverting_nothing_fails_loudly(self, build_snapshot):
        concepts = {k: json.loads(json.dumps(v)) for k, v in self._concepts(build_snapshot).items()}
        for target in ("2026/06", "2030/01"):
            scoped = {k: json.loads(json.dumps(v)) for k, v in concepts.items()}
            with pytest.raises(build_snapshot.BuildError, match="没有回退任何边界"):
                build_snapshot.revert_change_notes(scoped, target)

    def test_only_later_change_notes_are_applied(self, build_snapshot):
        """合成两套不同年代的 changeNote：目标版本夹在中间时只回退更晚的那批。"""
        concepts = {
            "Old": {
                "local": "Old",
                "iri": "ischart:Old",
                "ranks": ["Age"],
                "beginning": {"mya": 100.0, "margin": None, "uncertain": False},
                "end": {"mya": 90.0, "margin": None, "uncertain": False},
                "boundary_nodes": ["beginning", "end"],
                "change_notes": ["2025-01: hasBeginning 101.0 -> 100.0"],
                "broader": None,
                "ratified_gssp": False,
                "ratified_gssa": False,
                "pref_label_en": "Old",
                "is_concept": True,
            },
            "New": {
                "local": "New",
                "iri": "ischart:New",
                "ranks": ["Age"],
                "beginning": {"mya": 50.0, "margin": None, "uncertain": False},
                "end": {"mya": 40.0, "margin": None, "uncertain": False},
                "boundary_nodes": ["beginning", "end"],
                "change_notes": ["2026-06: hasBeginning 51.0 -> 50.0"],
                "broader": None,
                "ratified_gssp": False,
                "ratified_gssa": False,
                "pref_label_en": "New",
                "is_concept": True,
            },
        }
        reverted, stamps = build_snapshot.revert_change_notes(concepts, "2025/06")
        assert stamps == ["2026-06"]
        assert [r["concept"] for r in reverted] == ["New"]
        assert concepts["New"]["beginning"]["mya"] == 51.0
        assert concepts["Old"]["beginning"]["mya"] == 100.0  # 更早的修订不回退

    def test_unparsable_change_note_stamp_fails(self, build_snapshot):
        concepts = self._concepts(build_snapshot)
        target = next(c for c in concepts.values() if c["change_notes"])
        target["change_notes"] = ["June: hasBeginning 246.7 -> 247.0"]
        with pytest.raises(build_snapshot.BuildError, match="版本前缀"):
            build_snapshot.revert_change_notes(concepts, "2024/12")

    @staticmethod
    def _argv(tmp_path: Path, *, to: str | None = None, **overrides) -> list[str]:
        flags = {
            "--ttl": str(TTL_PATH),
            "--chart-version": "2026/06",
            "--tag": PINNED["tag"],
            "--commit": PINNED["commit"],
            "--source-sha256": PINNED["source_sha256"],
            "--retrieved-at": PINNED["retrieved_at"],
            "--out": str(tmp_path / "out.json"),
            "--log-out": str(tmp_path / "out.log.json"),
        }
        flags.update(overrides)
        argv = [token for flag, value in flags.items() for token in (flag, str(value))]
        if to is not None:
            argv += ["--to", to]
        return argv

    def test_cli_rejects_to_that_disagrees_with_chart_version(self, build_snapshot, tmp_path):
        """``--to`` 与 ``--chart-version`` 不同值时直接拒产（交叉校验）。"""
        argv = self._argv(tmp_path, **{"--chart-version": "2026/06"}, to="2024/12")
        with pytest.raises(SystemExit, match="矛盾"):
            build_snapshot.main(argv)

    def test_cli_rejects_derived_version_without_to(self, build_snapshot, tmp_path):
        """声明为推导版本却不带 ``--to``：那就是把基线数据贴上更早的标签。"""
        argv = self._argv(tmp_path, **{"--chart-version": "2024/12"})
        with pytest.raises(SystemExit, match="矛盾"):
            build_snapshot.main(argv)

    def test_cli_rejects_to_beyond_the_input_version(self, build_snapshot, tmp_path):
        """``--to 2026/06``（要求"前进到输入自身版本"）不在登记表内，构建必须被挡下。"""
        argv = self._argv(tmp_path, to="2026/06")
        with pytest.raises(build_snapshot.BuildError, match="未在 DERIVED_SNAPSHOTS 登记"):
            build_snapshot.main(argv)
        assert not (tmp_path / "out.json").exists()

    def test_cli_rejects_malformed_flags(self, build_snapshot, tmp_path):
        with pytest.raises(SystemExit, match="格式"):
            build_snapshot.main(self._argv(tmp_path, **{"--chart-version": "bogus"}))
        with pytest.raises(SystemExit, match="tag 格式"):
            build_snapshot.main(self._argv(tmp_path, **{"--tag": "nope"}))
        with pytest.raises(SystemExit, match="UTC"):
            build_snapshot.main(self._argv(tmp_path, **{"--retrieved-at": "yesterday"}))
        with pytest.raises(SystemExit, match="vendored"):
            build_snapshot.main(self._argv(tmp_path, **{"--tag": "v2030-01.0"}))

    def test_unregistered_revert_target_fails_before_writing(self, build_snapshot, tmp_path):
        combined = [
            "--ttl",
            str(TTL_PATH),
            "--chart-version",
            "1999/01",
            "--to",
            "1999/01",
            "--tag",
            PINNED["tag"],
            "--commit",
            PINNED["commit"],
            "--source-sha256",
            PINNED["source_sha256"],
            "--retrieved-at",
            PINNED["retrieved_at"],
            "--out",
            str(tmp_path / "out.json"),
            "--log-out",
            str(tmp_path / "out.log.json"),
        ]
        with pytest.raises(build_snapshot.BuildError, match="未在 DERIVED_SNAPSHOTS 登记"):
            build_snapshot.main(combined)
        assert not (tmp_path / "out.json").exists()

    def test_self_diff_request_is_rejected(self, build_snapshot, tmp_path):
        combined = [
            "--ttl",
            str(TTL_PATH),
            "--chart-version",
            "2024/12",
            "--to",
            "2024/12",
            "--tag",
            PINNED["tag"],
            "--commit",
            PINNED["commit"],
            "--source-sha256",
            PINNED["source_sha256"],
            "--retrieved-at",
            PINNED["retrieved_at"],
            "--out",
            str(tmp_path / "ics_chart-2024-12.json"),
            "--log-out",
            str(tmp_path / "ics_chart-2024-12.log.json"),
            "--diff-with",
            "2024/12",
        ]
        with pytest.raises(SystemExit, match="同版本"):
            build_snapshot.main(combined)
        # 校验发生在写盘之前：不得留下任何工件。
        assert not (tmp_path / "ics_chart-2024-12.json").exists()
        assert not (tmp_path / "ics_chart-2024-12.log.json").exists()


class TestStructuralRepairRule:
    """吸附判据来自结构等值类，而不是"全局谁出现得多"。"""

    @staticmethod
    def _concepts(build_snapshot) -> dict:
        text = (PROJECT_ROOT / "tools" / "source" / "ics-chart-v2026-06.5.ttl").read_text("utf-8")
        concepts, _ = build_snapshot.select_concepts(build_snapshot.parse_ttl(text))
        return concepts

    def test_only_the_aquitanian_rounding_variant_is_snapped(self, build_snapshot):
        concepts = self._concepts(build_snapshot)
        assert concepts["Aquitanian"]["beginning"]["mya"] == 23.03
        repairs = build_snapshot.repair_minority_rounding(concepts)
        assert [(r["concept"], r["from_mya"], r["to_mya"]) for r in repairs] == [
            ("Aquitanian", 23.03, 23.04)
        ]
        # 吸附的凭据是结构关系（Aquitanian 是 Miocene 最老的子区间），不是巧合的计数。
        assert repairs[0]["class_kind"] == "parent-base"
        assert repairs[0]["parent"] == "Miocene"
        assert repairs[0]["upward_writings"] == {"23.03": 1, "23.04": 5}
        assert concepts["Aquitanian"]["beginning"]["mya"] == 23.04

    def test_quaternary_fine_subdivisions_cannot_be_flattened(self, build_snapshot):
        """反例：按全局出现次数裁决会把只出现一次的 0.0042 抹平成 0.0。"""
        concepts = self._concepts(build_snapshot)
        synthetic = copy.deepcopy(concepts)
        synthetic["Meghalayan"]["beginning"]["mya"] = 0.0043  # 全库唯一的一处 0.0043
        occurrences = sum(
            1 for c in synthetic.values() for s in ("beginning", "end") if c[s]["mya"] == 0.0043
        )
        assert occurrences == 1
        # 规则要么修不动（结构与 0.0 无关），要么显式要求人工裁决——绝不静默抹平。
        try:
            repairs = build_snapshot.repair_minority_rounding(synthetic)
        except build_snapshot.BuildError:
            pass
        else:
            assert all(r["concept"] != "Meghalayan" for r in repairs), repairs
        assert synthetic["Meghalayan"]["beginning"]["mya"] == 0.0043
        # 原始数据里 Quaternary 的四个细分边界一个都不该被动。
        pristine = self._concepts(build_snapshot)
        touched = {r["concept"] for r in build_snapshot.repair_minority_rounding(pristine)}
        assert not touched & {
            "Meghalayan",
            "Northgrippian",
            "Greenlandian",
            "Holocene",
            "Quaternary",
        }

    def test_ambiguous_structural_class_fails(self, build_snapshot):
        concepts = self._concepts(build_snapshot)
        # 两个写法各自被佐证两次：没有少数派可判，必须人工裁决而不是"取更近的"。
        concepts["Aquitanian"]["beginning"]["mya"] = 23.03
        concepts["Chattian"]["end"]["mya"] = 23.03
        with pytest.raises(build_snapshot.BuildError, match="无法确定主流值"):
            build_snapshot.repair_minority_rounding(concepts)

    def test_repairs_never_break_parent_containment(self, build_snapshot):
        concepts = self._concepts(build_snapshot)
        build_snapshot.repair_minority_rounding(concepts)
        build_snapshot.reconcile_same_rank_overlaps(concepts)
        build_snapshot.check_parent_containment(concepts)  # 不抛即通过
        # 反向守卫：手工破坏包含关系时必须被抓到。
        concepts["Aquitanian"]["beginning"]["mya"] = 99.0
        with pytest.raises(build_snapshot.BuildError, match="层级包含被破坏"):
            build_snapshot.check_parent_containment(concepts)

    def test_zero_valued_child_end_is_not_treated_as_missing(self, build_snapshot):
        """``if concepts[k]["end"]["mya"]`` 这类真值过滤会把 0.0 当"无值"丢掉。"""
        concepts = self._concepts(build_snapshot)
        concepts["Ludlow"]["end"]["mya"] = 419.62
        concepts["Pridoli"]["beginning"]["mya"] = 422.7
        for local in ("Gorstian", "Ludfordian"):
            concepts[local]["end"]["mya"] = 0.0  # 合法值：子区间一路到 0.0
        # 0.0 必须参与子区间并集 -> 并集终点 0.0 != 422.7 -> 无法确定性调和（显式失败）。
        # 真值过滤会忽略 0.0，误以为并集终点就是 422.7，从而"静默修好"它。
        with pytest.raises(build_snapshot.BuildError, match="无法确定性调和"):
            build_snapshot.reconcile_same_rank_overlaps(concepts)


class TestProvenanceDocumented:
    """叙述性披露的断言不得自证——命中的子串不能躺在否定句里。"""

    TEXT = (SNAPSHOT_DIR / "PROVENANCE.md").read_text(encoding="utf-8")

    def test_derivation_is_denied_in_the_negative_form(self):
        text = self.TEXT
        # 完整否定句必须逐字存在：只取其中的肯定片段，反义改写也能通过。
        assert re.search(
            r"(?i)this snapshot is \*\*not\*\* an extract of an archived 2024/12 upstream release",
            text,
        ), "PROVENANCE.md 缺少对『不是 2024/12 上游归档抽取』的显式否定句"
        # 而且全文不得出现任何"它就是上游归档"的正面声称。
        affirmative = re.findall(
            r"(?i)(?<!not )\b(is|was)\s+(?:indeed\s+)?an extract of an archived 2024/12",
            text,
        )
        assert affirmative == [], affirmative
        hedged = re.findall(r"(?i)an archived 2024/12 upstream release", text)
        assert len(hedged) >= 1

    def test_declared_hashes_match_the_artifacts(self):
        """PROVENANCE.md 表格里的哈希必须是工件的真值（叙述与数据不得脱钩）。"""
        text = self.TEXT
        index = json.loads((SNAPSHOT_DIR / "versions.json").read_text(encoding="utf-8"))
        quoted = set(re.findall(r"\b[0-9a-f]{64}\b", text))
        assert quoted, "PROVENANCE.md 未引用任何 SHA-256，交叉核对失去意义"
        truths = {
            PINNED["source_sha256"],
            index["versions"]["2026/06"]["payload_sha256"],
            index["versions"]["2024/12"]["payload_sha256"],
        }
        assert quoted <= truths, quoted - truths
        for meta in index["versions"].values():
            assert meta["payload_sha256"] in quoted
        assert PINNED["source_sha256"] in quoted
        assert PINNED["tag"] in text
        assert PINNED["commit"] in text

    def test_provenance_commands_are_the_recorded_argv(self):
        """文档里给出的复现命令必须与生成日志记录的 argv 逐 token 相同。

        「日志由上文同一条命令产出」这句话如果只能靠人读，就会悄悄失真；这里把它
        变成断言：PROVENANCE.md 的每条 ``` 围栏命令都必须在某份日志里逐字存在。
        """
        documented = []
        for block in re.findall(r"```(.*?)```", self.TEXT, re.DOTALL):
            tokens = block.replace("\\\n", " ").split()
            if tokens[:1] == ["python"]:
                tokens = tokens[1:]
            if tokens[:1] == ["tools/build_snapshot.py"]:
                documented.append(tokens)
        assert len(documented) == 2, f"PROVENANCE.md 应各写一条基线/推导命令：{documented}"
        recorded = {
            log["chart_version"]: log["command"]
            for log in (_log(v) for v in ("2026-06", "2024-12"))
        }
        for argv in documented:
            version = argv[argv.index("--chart-version") + 1]
            assert version in recorded, f"命令声称的版本 {version} 没有对应日志"
            assert argv == recorded[version], (argv, recorded[version])

    def test_data_policy_qualifier_rule_includes_the_approximate_input(self):
        """docs/data-policy.md 的 qualifier 规则必须写出 ``~``/uncertain 输入。

        data-policy.md 以英文为权威版本（中文镜像为 data-policy.zh.md），
        条目锚点与措辞断言两种语言都接受。
        """
        policy = (PROJECT_ROOT / "docs" / "data-policy.md").read_text(encoding="utf-8")
        # 条目的边界是「下一条顶层项目符号」，不是某个武断的字符数：规则条目
        # 要同时写清三个输入、优先级和分布，长度会变，边界语义不会。
        rule = re.search(r"(?ms)^-\s*(?:边界\s*|Boundary )`qualifier`.*?(?=^-\s|\Z)", policy)
        assert rule, "docs/data-policy.md 找不到 qualifier 规则条目"
        clause = rule.group(0)
        # 语义检查而不是「整条 bullet 里凑巧两个词都在」——后者正是自证：
        # 1) 输入清单里必须点名 uncertain 与 ~；2) 必须有一条**编号规则步骤**把 ~
        # 映射到 approximate。
        head = re.split(r"(?m)^\s*1\.", clause, maxsplit=1)[0]
        assert "uncertain" in head and "~" in head, (
            f"qualifier 规则的输入清单里没有写出 uncertain/`~`：{head}"
        )
        assert re.search(
            r"(?m)^\s*\d+\.\s*[^\n]{0,60}`~`[^\n]{0,60}→[^\n]{0,60}`approximate`", clause
        ), "qualifier 规则缺少「上游写了 ~ → approximate」这条编号步骤"
        # 正交性也必须写下来：definition 轴不得吞掉 qualifier 轴。
        assert re.search(r"(?s)先于\*\*?\s*GSSP|正交性|takes precedence|orthogonality", clause), (
            "规则没有写明 ~ 先于 GSSP/GSSA 判定"
        )

    def test_provenance_names_the_generation_log_convention(self):
        """文档里的日志命名规范必须与实际文件名一致。"""
        policy = (PROJECT_ROOT / "docs" / "data-policy.md").read_text(encoding="utf-8")
        actual = {p.name for p in BUILD_LOG_DIR.glob("*.json")}
        assert actual == {"ics_chart-2026-06.log.json", "ics_chart-2024-12.log.json"}
        for name in actual:
            assert name in policy, f"{name} 未在 data-policy 中登记"
        assert "*.build-log.json" not in policy, "文档仍在描述一个匹配不到任何文件的命名"
        assert "*.log.json" in policy or "log.json" in policy

    def test_gitignore_does_not_hide_the_generation_logs(self):
        """日志是被跟踪的出处工件，.gitignore 不得命中它们。"""
        ignore_path = PROJECT_ROOT / ".gitignore"
        if not _in_git_checkout():
            pytest.skip("解包的发行归档不是 git 工作树，本用例只守护仓库的版本控制")
        ignore = ignore_path.read_text(encoding="utf-8")
        assert "*.build-log.json" not in ignore
        git = shutil.which("git")
        if git is None:  # pragma: no cover - 无 git 的环境
            pytest.skip("git 不可用，无法执行 check-ignore")
        for path in sorted(BUILD_LOG_DIR.glob("*.json")):
            probe = subprocess.run(
                # --no-index：已跟踪的文件在默认口径下永远不会被判为忽略，那会让
                # 本用例变成不可能失败的断言；真正的风险是「规范命中的一份日志一
                # 落地就被静默忽略」，所以必须按 ignore 规则本身来判。
                [
                    git,
                    "check-ignore",
                    "--no-index",
                    "-q",
                    str(path.relative_to(PROJECT_ROOT)),
                ],
                cwd=str(PROJECT_ROOT),
                capture_output=True,
            )
            assert probe.returncode != 0, f"{path.name} 被 .gitignore 忽略了"
        # 前瞻一份「下一版快照的日志」：命名规范不得被任何规则命中。
        probe = subprocess.run(
            [
                git,
                "check-ignore",
                "--no-index",
                "-q",
                "tools/build-logs/ics_chart-2099-12.log.json",
            ],
            cwd=str(PROJECT_ROOT),
            capture_output=True,
        )
        assert probe.returncode != 0, "按规范新增的生成日志会被 .gitignore 静默忽略"

    def test_provenance_discloses_the_project_authored_margin(self):
        """0.21 Ma 的出处必须在包内被明确标为项目自定值，而不是伪装成上游。"""
        text = self.TEXT
        assert "0.21" in text
        assert re.search(
            r"(?i)(development document 5\.7|project-authored|not traceable to a machine-readable upstream statement)",
            text,
        )
        # 占位必须**挂在它所要澄清的那条披露上**，不能是文档里随便某处有个 TODO：
        # 0.21 Ma 的项目自定值、以及"无独立 2024/12 归档版可核验"各需一条。
        blocks = re.findall(
            r"(?i)TODO\(author\)(.*?)(?=\n-\s`{0,1}TODO\(author\)`|\n#{2,}\s|\Z)",
            text,
            re.DOTALL,
        )
        assert blocks, "外部出处仍缺凭据：PROVENANCE.md 必须留下待作者补全的显式占位"
        joined = [block.lower() for block in blocks]
        assert any("0.21" in block for block in joined), (
            "缺一条挂在 ±0.21 Ma 误差补丁上的 TODO(author) 占位"
        )
        # 「上游不发布 2024/12 机器可读快照」有两种合法状态：仍未核验（留 TODO 占位），
        # 或已核验并给出可复核凭据。
        # 只写"我们相信上游没有 2024/12"不算数：必须点名核验日期与具体证据，
        # 否则这条断言本身就是一句无出处的外部主张。
        verified_record = re.search(
            r"(?i)verified[\s*]{0,4}2026-\d{2}-\d{2}[\s\S]{0,900}?(v0\.0\.15|2025-03-12)"
            r"[\s\S]{0,400}?2024/12",
            text,
        )
        assert any("2024/12" in block for block in joined) or verified_record, (
            "「上游不发布 2024/12 机器可读快照」这条外部主张既无 TODO(author) 占位，"
            "也无带日期与具体证据的核验记录"
        )

    def test_loader_ignores_diff_and_provenance_files(self):
        from geophylo.data.builtin import available_versions, load_versions_index

        assert available_versions() == ["2024/12", "2026/06"]
        assert set(load_versions_index()["versions"]) == {"2024/12", "2026/06"}

    def test_versions_index_still_validates_through_the_loader(self):
        from geophylo import Timescale

        assert Timescale(version="2024/12").find_by_name("Anisian").older_ma == pytest.approx(246.7)
        assert Timescale().find_by_name("Anisian").older_ma == pytest.approx(247.0)


# 披露层必须整层纳入版本控制：本用例是常驻回归守卫，任何一条被撤销跟踪就会红。
def test_provenance_layer_is_versioned():
    """披露层必须被 git 跟踪，否则发布归档里的出处只是空话。"""
    git = shutil.which("git")
    if git is None:  # pragma: no cover
        pytest.skip("git 不可用")
    if not _in_git_checkout():
        pytest.skip("解包的发行归档不是 git 工作树，本用例只守护仓库的版本控制")
    tracked = subprocess.run(
        [git, "ls-files"], cwd=str(PROJECT_ROOT), capture_output=True, text=True, check=True
    ).stdout.splitlines()
    missing = [p for p in PROVENANCE_LAYER if p not in tracked]
    assert missing == [], "需要 git add：" + " ".join(missing)


# 生成器正文（``def parse_ttl`` 之后）里允许出现的小数：全部是**已披露数值的说明
# 文字**——注释与 docstring 里复述那个被披露的值——外加那条唯一硬编码的误差补丁。
DISCLOSED_SCIENTIFIC_LITERALS = {
    23.03,
    23.04,
    419.62,
    422.7,
    246.7,
    247.0,
    259.51,
    259.857,
    2026.0,
    5.7,
}

# 形状上命中 ``\d+\.\d+`` 却**不是**科学数值的字面量：逐条登记它出现在哪一行、
# 是什么。登记是显式的、且必须逐条还在源码里（下面断言），所以「新增了一个没人
# 解释的小数」与「登记过时就没人管」都会红。
DISCLOSED_NON_SCIENTIFIC_LITERALS = {
    # 快照 license 块的数据：SPDX 标识符，与年代/误差无关。
    "CC-BY-4.0": "许可证 SPDX 标识（build_snapshot.py 的 license 块）",
    # boundary_qualifier 的 docstring 指向开发文档的章节号，不是数值。
    "开发文档 5.6": "文档章节交叉引用（boundary_qualifier docstring）",
    # --tag 的帮助文本里举例的上游 tag：其数字部分是 tag 文本 v2026-06.5。
    "v2026-06.5": "上游发布 tag 示例文本（--tag 帮助串）",
}

# 可执行代码里（AST 层面，不含注释/docstring/字符串）允许出现的 float 字面量。
# 这条判据补上文本面的漏洞：把 422.7 *写进代码* 而不是写进注释，即使它在文本面
# 已被登记，也会在这里失败。
DISCLOSED_CODE_FLOAT_LITERALS = {
    1e-9: "BOUNDARY_TOL：共享边界比较容差（开发文档 7.2）",
    0.05: "ROUNDING_SNAP_TOL：舍入吸附的结构等值容差",
    0.0: "reconcile_boundaries 中 max() 的单位元，不是任何端点值",
    0.21: "REVERTED_MARGIN_PATCHES：全库唯一硬编码的科学数值（已在 PROVENANCE.md 披露）",
}


def test_builder_has_no_hardcoded_scientific_value_other_than_the_disclosed_patch(
    build_snapshot,
):
    """生成器的唯一硬编码科学数值，仍是那条已披露的误差补丁。"""
    source = (PROJECT_ROOT / "tools" / "build_snapshot.py").read_text(encoding="utf-8")
    offset = source.index("def parse_ttl")
    body = source[offset:]
    body_lines = body.splitlines()
    unexplained: list[tuple[str, str]] = []
    for match in re.finditer(r"(?<![\w.])\d+\.\d+(?![\w.])", body):
        value = float(match.group(0))
        if value <= 1.0:  # 容差/文档小数不算
            continue
        line = body_lines[body[: match.start()].count("\n")]
        if value in DISCLOSED_SCIENTIFIC_LITERALS:
            continue
        if any(phrase in line for phrase in DISCLOSED_NON_SCIENTIFIC_LITERALS):
            continue
        unexplained.append((match.group(0), line.strip()))
    assert not unexplained, (
        f"生成器里出现了新的未登记硬编码数值：{unexplained}；"
        "要么从 pinned 输入推导，要么按 PROVENANCE.md 的口径登记并披露"
    )
    for phrase in DISCLOSED_NON_SCIENTIFIC_LITERALS:
        assert phrase in body, f"非数值登记已过时，请一并清理：{phrase}"
    code_floats = {
        node.value
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Constant) and isinstance(node.value, float)
    }
    assert code_floats == set(DISCLOSED_CODE_FLOAT_LITERALS), sorted(
        code_floats ^ set(DISCLOSED_CODE_FLOAT_LITERALS)
    )
    assert build_snapshot.REVERTED_MARGIN_PATCHES == {"259.51": 0.21}


def test_builder_does_not_read_the_clock():
    """确定性契约：生成器不读当前时间。"""
    source = (PROJECT_ROOT / "tools" / "build_snapshot.py").read_text(encoding="utf-8")
    assert not re.search(r"(?m)^\s*(import|from)\s+(datetime|time)\b", source), source

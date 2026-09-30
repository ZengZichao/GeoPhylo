"""打包、发行清单与文档一致性测试（开发文档 7.7/8.5）。

包含：package-data 存在性（importlib.resources）、许可与发行清单（MANIFEST.in）、
发布元数据（DOI/版本串）、CI 门禁命令自审、以及示例脚本的实际执行与图像内容检查。

写法规则：对配置一律**解析后断言语义**（tomllib / yaml / 清单
匹配器），不对 pyproject 原文做子串匹配——在别的段落里出现同一个词、或注释掉
一行，都不该让结论翻转。"构建产物里到底有没有这些文件"由
tests/packaging/check_wheel.py 对真实 wheel/sdist 检查（CI 的 packaging job），
本文件再用合成工件对同一套逻辑做正/负向测试。
"""

from __future__ import annotations

import fnmatch
import importlib.resources
import importlib.util
import io
import json
import re
import runpy
import tarfile
import time
import tomllib
import zipfile
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.image
import matplotlib.pyplot as plt
import pytest

pytestmark = [pytest.mark.packaging]

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PLACEHOLDER_MARKER = "REPLACE_AT_FIRST_RELEASE"
PLACEHOLDER_DOI = f"10.5281/zenodo.{PLACEHOLDER_MARKER}"

# sdist 必须自带"从发行包复核生成链"所需的全部材料——NOTICE 与
# docs/data-policy.md 都做了这个承诺。缺 tests/conftest.py 时，解包后整套测试报错。
SDIST_REQUIRED = (
    "README.md",
    "README.zh-CN.md",
    "LICENSE",
    "NOTICE",
    "CHANGELOG.md",
    "CHANGELOG.zh-CN.md",
    "CITATION.cff",
    "CONTRIBUTING.md",
    "CONTRIBUTING.zh-CN.md",
    "RELEASE.md",
    "RELEASE.zh-CN.md",
    "MANIFEST.in",
    ".zenodo.json",
    "pyproject.toml",
    "LICENSES/CC-BY-4.0.txt",
    "docs/data-policy.md",
    "docs/data-policy.zh.md",
    "docs/user-guide.en.md",
    "docs/user-guide.zh.md",
    "docs/adr/README.md",
    "docs/adr/README.zh.md",
    "docs/adr/ADR-1-bundled-snapshots-over-pyrolite.zh.md",
    "docs/adr/ADR-2-inset-axes-for-tracks.zh.md",
    "docs/adr/ADR-3-result-object-not-axes.zh.md",
    "docs/adr/ADR-4-adapters-build-contracts.zh.md",
    "docs/adr/ADR-5-per-boundary-state-model.zh.md",
    "examples/bio_phylo_timetree.py",
    "examples/stratigraphic_column.py",
    "examples/circular_tree.py",
    "tests/conftest.py",
    "tests/test_visual.py",
    "tests/test_packaging.py",
    "tests/packaging/check_wheel.py",
    "tests/update_baselines.py",
    "tests/baseline_images/timetree_geo_axis.png",
    "tests/baseline_images/stratigraphic_geo_axis.png",
    "tests/baseline_images_min/timetree_geo_axis.png",
    "tests/baseline_images_min/stratigraphic_geo_axis.png",
    "tools/build_snapshot.py",
    "tools/make_diff.py",
    "tools/source/ics-chart-v2026-06.5.ttl",
    "tools/build-logs/ics_chart-2026-06.log.json",
    "tools/build-logs/ics_chart-2024-12.log.json",
    "geophylo/data/snapshots/PROVENANCE.md",
    "geophylo/data/snapshots/ics_chart-2026-06.json",
    "geophylo/data/snapshots/ics_chart-2024-12.json",
    "geophylo/data/snapshots/versions.json",
    "geophylo/data/snapshots/diff-2024-12_to_2026-06.json",
    ".github/workflows/ci.yml",
)
# 不该进包的：本地缓存与示例输出（PNG 由测试重跑生成）。
SDIST_FORBIDDEN = (
    "examples/_output_bio_phylo_timetree.png",
    ".pytest_cache/v/cache/lastfailed",
    "geophylo/__pycache__/__init__.cpython-311.pyc",
    "dist/geophylo-0.1.0.tar.gz",
)


def _pyproject() -> dict:
    return tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8"))


def _requirement_names(requirements: list[str]) -> set[str]:
    return {re.split(r"[<>=!;\[\s]", item, maxsplit=1)[0].strip() for item in requirements}


def _manifest_rules() -> list[tuple[str, ...]]:
    """把 MANIFEST.in 解析成 (directive, *patterns) 列表，忽略注释与空行。"""
    lines = (PROJECT_ROOT / "MANIFEST.in").read_text(encoding="utf-8").splitlines()
    return [
        tuple(line.split()) for line in lines if line.strip() and not line.lstrip().startswith("#")
    ]


def sdist_includes(relative_path: str, rules: list[tuple[str, ...]] | None = None) -> bool:
    """按 MANIFEST.in 语义判断相对路径是否进 sdist（简化但保守的匹配器）。

    支持 include / recursive-include / graft 三类收录指令与 exclude /
    global-exclude / prune 三类排除指令，排除优先（与 setuptools 一致）。
    """
    path = relative_path.replace("\\", "/")
    while path.startswith("./"):
        path = path[2:]
    rules = rules if rules is not None else _manifest_rules()
    included = False
    for directive, *patterns in rules:
        kind = directive.lower()
        if kind == "include":
            included |= any(fnmatch.fnmatch(path, pattern) for pattern in patterns)
        elif kind == "recursive-include" and len(patterns) >= 2:
            directory = patterns[0].strip("/")
            if path == directory or path.startswith(directory + "/"):
                relative = path[len(directory) + 1 :]
                included |= any(
                    fnmatch.fnmatch(relative, glob) or fnmatch.fnmatch(Path(relative).name, glob)
                    for glob in patterns[1:]
                )
        elif kind == "graft":
            included |= any(path.startswith(pattern.strip("/") + "/") for pattern in patterns)
    if not included:
        return False
    for directive, *patterns in rules:
        kind = directive.lower()
        if kind == "exclude" and any(fnmatch.fnmatch(path, pattern) for pattern in patterns):
            return False
        if kind == "global-exclude" and any(
            fnmatch.fnmatch(Path(path).name, pattern) for pattern in patterns
        ):
            return False
        if kind == "prune" and any(
            path.startswith(pattern.strip("/") + "/") for pattern in patterns
        ):
            return False
    return True


def _load_check_wheel():
    script = PROJECT_ROOT / "tests" / "packaging" / "check_wheel.py"
    spec = importlib.util.spec_from_file_location("geophylo_check_wheel", script)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestPackageData:
    def test_snapshots_readable_via_importlib_resources(self):
        from geophylo.data import builtin

        files = importlib.resources.files(builtin.SNAPSHOT_PACKAGE)
        for name in ("versions.json", "ics_chart-2026-06.json", "ics_chart-2024-12.json"):
            assert (files / name).is_file(), f"缺少 package-data: {name}"

    def test_timescale_loads_from_installed_layout(self):
        from geophylo import Timescale

        assert Timescale().find_by_age(66.0, rank="Period").name == "Paleogene"


class TestLicenseFiles:
    def test_notice_and_licenses_exist(self):
        assert (PROJECT_ROOT / "NOTICE").is_file()
        assert (PROJECT_ROOT / "LICENSE").is_file()
        ccby = PROJECT_ROOT / "LICENSES" / "CC-BY-4.0.txt"
        assert ccby.is_file()
        text = ccby.read_text(encoding="utf-8")
        assert "Attribution 4.0 International" in text

    def test_every_license_cited_by_notice_ships_with_the_package(self):
        """NOTICE 指向 LICENSES/CC-BY-4.0.txt，它就必须真的进发行物。"""
        notice = (PROJECT_ROOT / "NOTICE").read_text(encoding="utf-8")
        cited = sorted(set(re.findall(r"LICENSES/[\w.\-]+", notice)))
        assert cited, "NOTICE 未引用 LICENSES/ —— 本测试的前提已不成立，请同步更新"
        declared = list(_pyproject()["project"].get("license-files", []))
        for path in cited:
            assert (PROJECT_ROOT / path).is_file(), f"NOTICE 指向不存在的 {path}"
            shipped = any(
                fnmatch.fnmatch(path, pattern) or fnmatch.fnmatch(Path(path).name, pattern)
                for pattern in declared
            ) or sdist_includes(path)
            assert shipped, (
                f"{path} 被 NOTICE 引用，却既不在 [project.license-files]={declared} "
                "也不在 MANIFEST.in 里"
            )

    def test_notice_cites_ics(self):
        notice = (PROJECT_ROOT / "NOTICE").read_text(encoding="utf-8")
        assert "International Commission on Stratigraphy" in notice
        assert "CC BY 4.0" in notice

    def test_repo_scaffolding_present(self):
        for name in (
            "CONTRIBUTING.md",
            "CHANGELOG.md",
            "CITATION.cff",
            "RELEASE.md",
            ".zenodo.json",
            "MANIFEST.in",
            "pyproject.toml",
            "README.md",
            "docs/data-policy.md",
            "docs/adr/README.md",
            "geophylo/data/snapshots/PROVENANCE.md",
            ".github/workflows/ci.yml",
        ):
            assert (PROJECT_ROOT / name).is_file(), f"缺少 {name}"


class TestSdistManifest:
    """sdist 必须可自测：清单缺一项，解包后整套测试就整片报错。"""

    def test_every_required_file_is_covered_by_the_manifest(self):
        uncovered = [name for name in SDIST_REQUIRED if not sdist_includes(name)]
        assert not uncovered, "MANIFEST.in 未覆盖这些文件（sdist 解包后无法自测）：" + ", ".join(
            uncovered
        )

    def test_every_required_file_actually_exists_in_the_repo(self):
        missing = [name for name in SDIST_REQUIRED if not (PROJECT_ROOT / name).is_file()]
        assert not missing, "清单要求但仓库里没有的文件（先 git add）：" + ", ".join(missing)

    def test_build_artifacts_and_paper_material_are_excluded(self):
        included = [name for name in SDIST_FORBIDDEN if sdist_includes(name)]
        assert not included, "不该进 sdist 的文件被收进来了：" + ", ".join(included)


class TestArtifactCheckerLogic:
    """对 check_wheel.collect_problems() 做正/负向测试（可执行语义）。"""

    @staticmethod
    def _make_dist(root: Path, *, wheel_members: set[str], sdist_members: set[str]) -> Path:
        dist = root / "dist"
        dist.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(dist / "geophylo-0.0.0-py3-none-any.whl", "w") as zf:
            for name in sorted(wheel_members):
                zf.writestr(name, "x")
        with tarfile.open(dist / "geophylo-0.0.0.tar.gz", "w:gz") as tf:
            for name in sorted(sdist_members):
                info = tarfile.TarInfo(f"geophylo-0.0.0/{name}")
                info.size = 1
                tf.addfile(info, io.BytesIO(b"x"))
        return dist

    @staticmethod
    def _complete_members() -> tuple[set[str], set[str]]:
        check = _load_check_wheel()
        licenses = ("LICENSE", "NOTICE", "LICENSES/CC-BY-4.0.txt")
        wheel = set(check.WHEEL_REQUIRED) | {
            f"geophylo-0.0.0.dist-info/licenses/{name}" for name in licenses
        }
        sdist = set(check.SDIST_REQUIRED) | set(check.WHEEL_REQUIRED) | set(licenses)
        return wheel, sdist

    def test_complete_artifacts_pass(self, tmp_path: Path) -> None:
        check = _load_check_wheel()
        wheel, sdist = self._complete_members()
        dist = self._make_dist(tmp_path, wheel_members=wheel, sdist_members=sdist)
        assert check.collect_problems(dist) == []

    @pytest.mark.parametrize("needle", ["licenses/LICENSE", "licenses/NOTICE", "CC-BY-4.0.txt"])
    def test_missing_license_text_fails_wheel_check(self, tmp_path: Path, needle: str) -> None:
        """负向控制：任一份许可文本缺席都必须变红（门槛不能只靠 NOTICE 满足）。"""
        check = _load_check_wheel()
        wheel, sdist = self._complete_members()
        wheel = {name for name in wheel if needle not in name}
        dist = self._make_dist(tmp_path, wheel_members=wheel, sdist_members=sdist)
        problems = check.collect_problems(dist)
        wanted = needle.split("/")[-1]
        assert any("wheel" in problem and wanted in problem for problem in problems), problems

    def test_missing_sdist_selftest_material_fails(self, tmp_path: Path) -> None:
        """负向控制：sdist 少一个 tests/conftest.py 必须被拒绝。"""
        check = _load_check_wheel()
        wheel, sdist = self._complete_members()
        sdist = {name for name in sdist if name != "tests/conftest.py"}
        dist = self._make_dist(tmp_path, wheel_members=wheel, sdist_members=sdist)
        problems = check.collect_problems(dist)
        assert any("sdist" in problem and "conftest" in problem for problem in problems), problems

    def test_checker_and_manifest_agree(self) -> None:
        """check_wheel 的必装清单必须被 MANIFEST.in 覆盖，否则两边各自漂移。"""
        check = _load_check_wheel()
        uncovered = [name for name in check.SDIST_REQUIRED if not sdist_includes(name)]
        assert not uncovered, "MANIFEST.in 未覆盖 check_wheel 要求的文件：" + ", ".join(uncovered)


class TestReleaseMetadata:
    """可用性元数据的一致性：这类漂移不会让任何功能测试失败，所以显式钉住。"""

    def test_no_placeholder_repository_url(self):
        for name in ("pyproject.toml", "CITATION.cff", ".zenodo.json"):
            text = (PROJECT_ROOT / name).read_text(encoding="utf-8")
            assert "github.com/geophylo/geophylo" not in text, name
            assert "https://github.com/ZengZichao/GeoPhylo" in text, name

    def test_version_agrees_across_release_files(self):
        from geophylo import __version__

        pyproject = _pyproject()
        cff = re.search(
            r"^version:\s*(\S+)\s*$",
            (PROJECT_ROOT / "CITATION.cff").read_text(encoding="utf-8"),
            re.MULTILINE,
        )
        zenodo = json.loads((PROJECT_ROOT / ".zenodo.json").read_text(encoding="utf-8"))
        assert cff is not None, "CITATION.cff 缺少 version 字段"
        # 版本串五处一致：守卫要把 CHANGELOG 也算进来，漏一处就会静默漂移。
        changelog = (PROJECT_ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
        head = re.search(
            r"^## \[(\S+)\] - (?:\d{4}-\d{2}-\d{2}|unreleased)", changelog, re.MULTILINE
        )
        assert head is not None, (
            "CHANGELOG.md 的版本标题格式变了，守卫需同步更新（发布前写 unreleased，发布后写日期）"
        )
        assert (
            __version__
            == pyproject["project"]["version"]
            == cff.group(1)
            == zenodo["version"]
            == head.group(1)
        ), "版本号在 _version.py / pyproject / CITATION.cff / .zenodo.json / CHANGELOG 之间漂移"

    def test_deposit_metadata_describes_the_same_work(self):
        """归档元数据必须与仓库题名、署名一致，并且用合法的 CFF 键名。

        Zenodo 的存档题名直接取 `.zenodo.json`／`CITATION.cff`；两者若不一致，
        引用记录就自相矛盾。CFF 1.2 的人物键名
        是 `family-names`／`given-names`，写成 `name-family` 会被 GitHub 的引用
        面板渲染成空姓名。题名在此钉死，改名必须是有意的。
        """
        expected = (
            "GeoPhylo: reproducible geological timescale axes for Matplotlib, with an "
            "explicit coordinate-semantics contract and version-pinned ICS snapshots"
        )
        cff_text = (PROJECT_ROOT / "CITATION.cff").read_text(encoding="utf-8")
        zenodo = json.loads((PROJECT_ROOT / ".zenodo.json").read_text(encoding="utf-8"))
        cff_title = re.search(r"^title:\s*\"?([^\n]+)\"?\s*$", cff_text, re.MULTILINE)
        assert cff_title is not None, "CITATION.cff 缺少 title 字段"
        # 引号是 YAML 的写法，不是题名的一部分；不去掉就会永远对不上。
        title = cff_title.group(1).strip().strip('"').strip()
        assert title == expected, "CITATION.cff 题名与既定题名不一致"
        assert zenodo["title"] == expected, ".zenodo.json 题名与既定题名不一致"
        assert "name-family" not in cff_text and "name-given" not in cff_text, (
            "CFF 人物键名写反了：应为 family-names / given-names"
        )
        authors_block = cff_text.split("references:")[0]
        assert (
            authors_block.count("family-names:") == 1 and authors_block.count("given-names:") == 1
        )
        for name in ("Zeng", "Zichao", "0000-0001-6553-970X"):
            assert name in authors_block, f"CITATION.cff 作者缺少 {name}"

    def test_doi_is_placeholder_or_real_doi(self):
        """与 RELEASE.md 的流程一致，不把"尚未发布"钉成不变量。

        发布前：DOI 是占位串，且 RELEASE.md 记录了它的粘贴位置；
        发布后：占位串必须从全仓消失（即 RELEASE.md 的发布后复核）。
        两种状态都通过本测试，所以填入真实 Concept DOI 之后 CI 不会因此变红。
        """
        dois = _citation_dois()
        assert len(dois) == 1, f"CITATION.cff 应恰好声明一个 DOI，实际 {dois}"
        doi = dois[0]
        release_doc = (PROJECT_ROOT / "RELEASE.md").read_text(encoding="utf-8")
        if doi == PLACEHOLDER_DOI:
            assert PLACEHOLDER_MARKER in release_doc, (
                "DOI 仍是占位串，但 RELEASE.md 未记录填写位置——发布流程与元数据脱钩"
            )
            assert "conceptdoi" not in (PROJECT_ROOT / ".zenodo.json").read_text(
                encoding="utf-8"
            ), "DOI 由 Zenodo 生成，.zenodo.json 里不该手写 conceptdoi"
            return
        assert re.fullmatch(r"10\.\d{4,9}/[\w.\-]+", doi), f"既不是占位串也不是合法 DOI：{doi!r}"

    def test_placeholder_absent_once_doi_is_filled(self):
        """发布后复核：真实 DOI 已填入时占位串必须彻底消失。

        与上一条合起来才是闭环：占位阶段合法，填好之后立刻变红——"占位阶段"
        不是永久不变量，发布流程无需为此改动测试。扫描范围与
        RELEASE.md 的"发布后复核"命令逐字一致：RELEASE.md（流程文档本身）与
        CHANGELOG.md（历史记录）允许保留该串，本测试文件也必然含它。
        """
        dois = _citation_dois()
        assert len(dois) == 1
        if dois[0] == PLACEHOLDER_DOI:
            pytest.skip("concept DOI 尚未铸造（发布前状态）；发布后本测试自动转为生效")
        here = Path(__file__).resolve()
        offenders = sorted(
            str(path.relative_to(PROJECT_ROOT))
            for path in PROJECT_ROOT.rglob("*")
            if path.is_file()
            and path.resolve() != here
            and ".git" not in path.parts
            and ".mimosa" not in path.parts  # 本地 AI 工具状态，.gitignore 内，不入库
            and path.name
            not in {"RELEASE.md", "RELEASE.zh-CN.md", "CHANGELOG.md", "CHANGELOG.zh-CN.md"}
            and PLACEHOLDER_MARKER in _safe_read(path)
        )
        assert not offenders, "真实 DOI 已填入，但占位串仍残留：" + ", ".join(offenders)

    def test_ics_reference_year_agrees_between_notice_and_snapshots(self):
        """ICS 引用年份（2025）与图表版本（2026/06）不得混写。"""
        notice = (PROJECT_ROOT / "NOTICE").read_text(encoding="utf-8")
        assert "& Car, N. (2025, updated)." in notice
        assert "(2026, updated)" not in notice
        for snapshot in sorted(
            (PROJECT_ROOT / "geophylo" / "data" / "snapshots").glob("ics_chart-*.json")
        ):
            citation = json.loads(snapshot.read_text(encoding="utf-8"))["license"]["citation"]
            assert "Cohen, K.M., Harper, D.A.T., Gibbard, P.L. & Car, N. (2025, updated)." in (
                citation
            ), snapshot.name


def _citation_dois() -> list[str]:
    text = (PROJECT_ROOT / "CITATION.cff").read_text(encoding="utf-8")
    block = re.search(r"^identifiers:\n((?:[ \t#].*\n)*)", text, re.MULTILINE)
    assert block is not None, "CITATION.cff 缺少 identifiers 段"
    return re.findall(r"type:\s*doi\s*\n\s*value:\s*(\S+)", block.group(1))


def _safe_read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return ""


SPEC_INDEX = PROJECT_ROOT / "docs" / "spec" / "README.md"
EXPORT_DOC_CORPUS = (
    "README.md",
    "docs/user-guide.en.md",
    "docs/user-guide.zh.md",
    "docs/spec/README.md",
)


def _spec_row(entry_id: str) -> str:
    rows = [
        line
        for line in _safe_read(SPEC_INDEX).splitlines()
        if line.strip().startswith(f"| {entry_id} |")
    ]
    assert len(rows) == 1, f"规范索引里 '{entry_id}' 行数为 {len(rows)}，无法定位稳定性矩阵"
    return rows[0]


def _matrix_columns(row: str) -> tuple[set[str], set[str]]:
    """把 1.4 行的第二列拆成（稳定符号集, 实验性符号集）。

    先按表格竖线切列再在列内解析：该行的来源列与校验列也含反引号词（如
    ``experimental``），不做列切分会把标记名当成 API 符号。规范索引以英文为
    权威版本（列头写 "experimental symbols"），中文镜像写 "实验性符号"，两种
    分隔词都接受。
    """
    cols = [c.strip() for c in row.split("|")]
    body = next((c for c in cols if "实验性符号" in c or "experimental symbols" in c), None)
    assert body is not None, "1.4 行不再同时声明稳定 API 与实验性符号，矩阵结构已变"
    marker = "实验性符号" if "实验性符号" in body else "experimental symbols"
    stable_part, experimental_part = body.split(marker, 1)
    names = lambda seg: set(re.findall(r"`([A-Za-z_][A-Za-z0-9_]*)`", seg))  # noqa: E731
    stable, experimental = names(stable_part), names(experimental_part)
    assert stable and experimental, "1.4 行解析出空集合，本测试会空转"
    return stable, experimental


class TestStabilityMatrix:
    """规范索引 1.4 行承诺的「顶层导出面」校验。"""

    def test_matrix_symbols_are_all_exported_at_top_level(self):
        import geophylo

        stable, experimental = _matrix_columns(_spec_row("1.4"))
        assert not (stable & experimental), f"同一符号既列稳定又列实验性：{stable & experimental}"
        for name in sorted(stable | experimental):
            assert name in geophylo.__all__, f"{name} 在稳定性矩阵里声明，却不在 __all__ 中"
            assert hasattr(geophylo, name), f"{name} 声明为顶层 API，但 geophylo.{name} 取不到"

    def test_experimental_marker_is_declared_and_used(self):
        markers = [
            str(item).split(":", 1)[0].strip()
            for item in _pyproject()["tool"]["pytest"]["ini_options"]["markers"]
        ]
        assert "experimental" in markers, "pyproject 未声明 experimental marker，1.4 行落空"
        used = [
            p.name
            for p in sorted((PROJECT_ROOT / "tests").glob("test_*.py"))
            if "pytest.mark.experimental" in _safe_read(p)
        ]
        assert used, "marker 已声明但没有任何测试模块使用它"

    def test_every_exported_symbol_is_documented(self):
        import geophylo

        corpus = "\n".join(_safe_read(PROJECT_ROOT / rel) for rel in EXPORT_DOC_CORPUS)
        # __version__ 是发行属性而非 API 面，手册里只讲版本查询方式、不逐名列举。
        undocumented = [
            name for name in geophylo.__all__ if name != "__version__" and name not in corpus
        ]
        assert not undocumented, f"导出但文档从未提及：{undocumented}"

    def test_export_surface_guard_fires_on_a_planted_mismatch(self):
        """守卫必须可失败：矩阵里把 GeophyloError 改成不存在的名字，就该被判为未导出。"""
        import geophylo

        row = _spec_row("1.4")
        stable, experimental = _matrix_columns(row)

        def missing(text: str) -> set[str]:
            declared, _ = _matrix_columns(text)
            return declared - set(geophylo.__all__)

        assert not missing(row), "未篡改时矩阵已含未导出符号，主测试却报绿？"
        tampered = row.replace("`GeophyloError`", "`GeophyloException`", 1)
        assert tampered != row, "反例未写入，注入是空转"
        assert missing(tampered) == {"GeophyloException"}, "改名后守卫仍不报警，检查是假的"
        assert "GeophyloError" in stable and "add_geo_ring" in experimental


class TestBuildConfiguration:
    """构建配置语义（解析后断言，不对原文做子串匹配）。"""

    def test_snapshots_and_py_typed_are_declared_as_package_data(self):
        package_data = _pyproject()["tool"]["setuptools"]["package-data"]
        assert "py.typed" in package_data.get("geophylo", []), package_data
        snapshots = package_data.get("geophylo.data.snapshots", [])
        assert any("json" in glob for glob in snapshots), f"快照未声明为 package-data: {snapshots}"

    def test_optional_extras_declare_their_real_runtime_needs(self):
        extras = {
            name: list(value)
            for name, value in _pyproject()["project"]["optional-dependencies"].items()
        }
        assert set(extras) >= {"biopython", "iplotx", "pyrolite", "test", "dev"}
        assert "ete4" in _requirement_names(extras["iplotx"]), (
            f"iplotx extra 必须补 ete4（iplotx 运行时 import 它却不声明）：{extras['iplotx']}"
        )
        assert "iplotx" in _requirement_names(extras["iplotx"])
        assert "pyrolite" in _requirement_names(extras["pyrolite"])
        assert "biopython" in _requirement_names(extras["biopython"])
        assert {"pytest", "pytest-mpl", "biopython", "packaging"} <= _requirement_names(
            extras["test"]
        )
        assert {"ruff", "mypy", "build"} <= _requirement_names(extras["dev"])
        assert any(item.startswith("geophylo[") for item in extras["dev"]), (
            "dev extra 必须包含 geophylo[test]，否则 .[dev] 装不上测试依赖"
        )

    def test_build_system_supports_pep639_license_files(self):
        requires = _pyproject()["build-system"]["requires"]
        spec = next((item for item in requires if item.lower().startswith("setuptools")), None)
        assert spec is not None, f"build-system.requires 未声明 setuptools：{requires}"
        floor = re.search(r">=\s*(\d+)", spec)
        assert floor and int(floor.group(1)) >= 77, (
            f"license-files（PEP 639）需要 setuptools>=77，实际声明 {spec!r}"
        )
        license_value = _pyproject()["project"]["license"]
        assert isinstance(license_value, str), (
            "license 必须是 SPDX 表达式字符串；表形式 license = {file = …} 已弃用"
        )
        assert license_value == "MIT"
        assert not any(
            classifier.startswith("License ::")
            for classifier in _pyproject()["project"].get("classifiers", [])
        ), "PEP 639：SPDX license 与 License :: 分类器互斥，二者只能留一"
        declared = _pyproject()["project"].get("license-files", [])
        assert any("LICENSES" in pattern for pattern in declared), (
            f"[project] license-files 必须覆盖 LICENSES/*，实际 {declared}"
        )

    def test_ci_gate_commands_match_the_declared_policy(self):
        """自审 CI：门禁命令与注释声称的语义必须逐项对上。"""
        import yaml

        ci = yaml.safe_load((PROJECT_ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8"))
        jobs = ci["jobs"]

        def run_commands(job: dict) -> list[str]:
            return [
                step["run"]
                for step in job.get("steps", [])
                if isinstance(step, dict) and "run" in step
            ]

        blocking = {name: job for name, job in jobs.items() if not job.get("continue-on-error")}
        gates = [
            command
            for job in blocking.values()
            for command in run_commands(job)
            if "pytest" in command and "not performance" in command
        ]
        assert len(gates) >= 3, (
            f"阻塞门禁命令应该覆盖 core-current/core-min/optional（实际 {len(gates)} 条）"
        )
        assert all("--mpl" in command for command in gates), (
            "所有阻塞门禁都必须带 --mpl，否则视觉比较永不执行"
        )
        for command in gates:
            assert "not experimental" not in command, f"阻塞门禁不得排除实验性测试：{command}"
        advisory = {
            name
            for name, job in jobs.items()
            if job.get("continue-on-error")
            or any(
                step.get("continue-on-error")
                for step in job.get("steps", [])
                if isinstance(step, dict)
            )
        }
        assert {"performance", "core-pre"} <= advisory, (
            f"注释声称非阻塞的 job 必须真的 continue-on-error，实际 {sorted(advisory)}"
        )
        for job in jobs.values():
            for command in run_commands(job):
                assert "|| true" not in command, f"`|| true` 会把失败吞成绿：{command}"
        matrix = jobs["optional"]["strategy"]["matrix"]["include"]
        assert any(
            {"biopython", "pyrolite", "iplotx"}
            <= {part.strip() for part in str(row["extras"]).split(",")}
            for row in matrix
        ), "必须有一个 job 同时装齐 biopython+pyrolite+iplotx"
        minimal = "\n".join(run_commands(jobs["core-min"]))
        for package in ("pytest", "pytest-mpl", "biopython"):
            assert f'"{package}==' in minimal, f"core-min 没有把 {package} 钉到下界"

    def test_contributing_advertises_the_lint_commands_ci_actually_runs(self):
        """CONTRIBUTING.md 教给贡献者的 lint/type 命令，必须是 ci.yml 真跑的那些。

        此处曾写 `ruff check .`，而 CI 跑的是四棵显式子树：照文档执行的贡献者会
        得到与门禁不一致的告警集合。文档口径与门禁口径必须锁死，否则两者各自漂移。
        """
        import yaml

        ci_text = (PROJECT_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
        ci = yaml.safe_load(ci_text)
        gate_cmds = {
            line.strip()
            for job in ci["jobs"].values()
            for step in job.get("steps", [])
            if isinstance(step, dict) and "run" in step
            for line in str(step["run"]).splitlines()
            if line.strip().startswith(("ruff ", "mypy"))
        }
        assert gate_cmds, "ci.yml 里找不到 ruff/mypy 门禁命令，检查该 workflow 是否被改写"

        contributing = (PROJECT_ROOT / "CONTRIBUTING.md").read_text(encoding="utf-8")
        advertised = {c.strip() for c in re.findall(r"`(ruff [^`]+|mypy[^`]*)`", contributing)}
        assert advertised, "CONTRIBUTING.md 不再声明任何 lint 命令，检查该文档是否被改写"
        unknown = sorted(advertised - gate_cmds)
        assert not unknown, (
            "CONTRIBUTING.md 声明的门禁命令不在 ci.yml 实际执行的集合里："
            + ", ".join(unknown)
            + f"；ci.yml 实跑 {sorted(gate_cmds)}"
        )
        # 反向也要成立：门禁里真正执行的静态检查都该在文档里有交代
        for command in sorted(gate_cmds):
            if command.startswith("ruff"):
                assert any(command in a for a in advertised), f"ci.yml 跑了 {command}，文档却没提"


def _decorator_name(decorator):
    """取装饰器名字，兼容 `@x`、`@x()` 与 `@m.x(...)` 三种写法。"""
    node = decorator.func if hasattr(decorator, "func") else decorator
    return getattr(node, "id", None) or getattr(node, "attr", None)


class TestSuiteHygiene:
    """测试资产自身也不能养死代码：零引用的辅助函数同样要被抓出来。"""

    def test_every_conftest_fixture_is_used(self):
        import ast

        conftest = PROJECT_ROOT / "tests" / "conftest.py"
        tree = ast.parse(conftest.read_text(encoding="utf-8"), filename=str(conftest))
        defined, autouse = set(), set()
        for node in tree.body:
            if not isinstance(node, ast.FunctionDef):
                continue
            fixtures = [dec for dec in node.decorator_list if _decorator_name(dec) == "fixture"]
            if not fixtures:
                continue
            defined.add(node.name)
            if any(
                isinstance(dec, ast.Call)
                and any(
                    kw.arg == "autouse" and getattr(kw.value, "value", False) for kw in dec.keywords
                )
                for dec in fixtures
            ):
                autouse.add(node.name)
        assert defined, "conftest 里没有任何夹具，测试套件不可能自洽"
        corpus = "\n".join(
            path.read_text(encoding="utf-8")
            for path in sorted((PROJECT_ROOT / "tests").glob("*.py"))
            if path != conftest
        )
        unused = sorted(
            name
            for name in defined
            if name not in autouse and not re.search(rf"\b{re.escape(name)}\b", corpus)
        )
        assert not unused, "conftest 里的死夹具（要么用要么删）：" + ", ".join(unused)

    def test_visual_baseline_images_are_all_referenced(self):
        """基准图不能有孤儿：删了测试却没删图，会让人误以为仍有覆盖。"""
        import ast

        declared: set[str] = set()
        for module in sorted((PROJECT_ROOT / "tests").glob("test_*.py")):
            tree = ast.parse(module.read_text(encoding="utf-8"), filename=str(module))
            for node in ast.walk(tree):
                if not isinstance(node, ast.FunctionDef):
                    continue
                for decorator in node.decorator_list:
                    if _decorator_name(decorator) != "mpl_image_compare":
                        continue
                    for keyword in decorator.keywords:
                        if keyword.arg == "filename" and isinstance(keyword.value, ast.Constant):
                            declared.add(str(keyword.value.value))
        on_disk = {path.name for path in (PROJECT_ROOT / "tests" / "baseline_images").glob("*.png")}
        assert declared, "没有任何测试声明基准图文件名——视觉回归已失效"
        assert declared <= on_disk, f"声明了但磁盘上没有的基准图：{sorted(declared - on_disk)}"
        assert on_disk <= declared, f"存在无人引用的基准图（孤儿）：{sorted(on_disk - declared)}"


def _run_example(name: str) -> Path:
    """在进程内实际执行示例脚本，返回它写出的 PNG 路径。

    7.7 要求示例在 CI 中**被执行**；只断言"PNG 存在"等于没断言——磁盘上早已
    存在的旧文件也能通过。因此先删除上一轮产物，再要求它被重新写出。
    """
    script = PROJECT_ROOT / "examples" / name
    output = PROJECT_ROOT / "examples" / f"_output_{script.stem}.png"
    output.unlink(missing_ok=True)
    start = time.time()
    runpy.run_path(str(script), run_name="__main__")
    assert output.is_file(), f"{name} 没有写出 {output.name}"
    assert output.stat().st_mtime >= start - 5.0, f"{output.name} 不是本次运行生成的"
    return output


def _assert_rendered_figure(output: Path, *, min_colors: int = 8) -> None:
    """图像内容检查：断言不能停在"文件存在"。

    只用 matplotlib 自带的 PNG 读取器，不引入新依赖。检查：尺寸非退化、确有墨迹、
    量化后至少 ``min_colors`` 种颜色——色带缺失或被刷成单一颜色会立刻变红。
    """
    array = matplotlib.image.imread(str(output))
    # matplotlib 的 PNG 读取器返回 [0,1] 浮点数组；不换算成 0–255 的话下面的
    # 阈值判断会恒真（"任何像素 < 250"），检查就成了摆设。
    if array.dtype.kind == "f":
        array = array * 255.0
    height, width = array.shape[:2]
    assert (width, height) >= (400, 240), f"{output.name} 尺寸退化：{width}x{height}"
    rgb = array[..., :3]
    opaque = array[..., 3] > 128 if array.shape[-1] == 4 else None
    ink = rgb if opaque is None else rgb[opaque]
    assert (ink < 250).any(axis=-1).mean() > 0.01, f"{output.name} 几乎全白（渲染结果为空图？）"
    quantized = (ink // 8).astype("int32").reshape(-1, 3)
    distinct = len({tuple(px) for px in quantized})
    assert distinct >= min_colors, (
        f"{output.name} 只有 {distinct} 种量化颜色（要求 ≥{min_colors}）：色带疑似缺失或被统一着色"
    )


class TestExamplesRun:
    def test_bio_phylo_example_runs(self):
        pytest.importorskip("Bio")
        _assert_rendered_figure(_run_example("bio_phylo_timetree.py"))
        plt.close("all")

    def test_stratigraphic_example_runs(self):
        _assert_rendered_figure(_run_example("stratigraphic_column.py"), min_colors=16)
        plt.close("all")

    def test_circular_tree_example_runs(self):
        pytest.importorskip("Bio")
        _assert_rendered_figure(_run_example("circular_tree.py"))
        plt.close("all")

    def test_iplotx_example_requires_optional_dep(self):
        pytest.importorskip("iplotx")  # 未装 iplotx 时整体跳过；CI 的 optional-all 会真的跑
        _assert_rendered_figure(_run_example("iplotx_timetree.py"))
        plt.close("all")

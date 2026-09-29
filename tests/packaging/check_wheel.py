"""清洁安装检查脚本（由 CI 的 packaging job 在隔离 venv 中调用）。

用法::

    python tests/packaging/check_wheel.py <dist 目录>

校验三件事：

1. 安装产物可导入、快照 package-data 完整、payload 哈希可复现；
2. **wheel** 里代码许可（LICENSE/NOTICE）与数据许可全文（LICENSES/CC-BY-4.0.txt）
   各自独立存在——三类文本逐条断言，绝不写成 `"CC-BY-4.0" in name or
   name.endswith("NOTICE")`：那样的门槛 NOTICE 单独就能满足，CC-BY 全文不进任何
   发行物也照样 exit 0；
3. **sdist** 自带整套可自测的材料：tests/conftest.py、视觉基准图、tools/（pinned
   TTL + 生成器 + 构建日志）、docs/、LICENSES/、发布元数据。缺任何一项，
   "从发行包复核生成链"的承诺就落空。

内容检查放在 `collect_problems()` 里（纯函数，不依赖安装状态），
tests/test_packaging.py 用它对合成工件做负向测试。
"""

from __future__ import annotations

import hashlib
import sys
import tarfile
import zipfile
from pathlib import Path

# wheel 必须携带的库内文件。
WHEEL_REQUIRED = (
    "geophylo/py.typed",
    "geophylo/data/snapshots/versions.json",
    "geophylo/data/snapshots/ics_chart-2026-06.json",
    "geophylo/data/snapshots/ics_chart-2024-12.json",
    "geophylo/data/snapshots/diff-2024-12_to_2026-06.json",
    "geophylo/data/snapshots/PROVENANCE.md",
)
# 许可合规：两类文本各自独立必需。
WHEEL_LICENSES = (
    ("LICENSE", "代码 MIT 许可正文"),
    ("NOTICE", "ICS 数据归属声明"),
    ("CC-BY-4.0.txt", "数据 CC BY 4.0 许可正文（NOTICE 指向它）"),
)
# sdist 必须能自测：解包后 `pytest` 需要的全部材料。
SDIST_REQUIRED = (
    "pyproject.toml",
    "MANIFEST.in",
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
    ".zenodo.json",
    "LICENSES/CC-BY-4.0.txt",
    "docs/data-policy.md",
    "docs/data-policy.zh.md",
    "docs/spec/README.md",
    "docs/spec/README.zh.md",
    "docs/adr/README.md",
    "docs/adr/README.zh.md",
    "tests/conftest.py",
    "tests/test_visual.py",
    "tests/packaging/check_wheel.py",
    "tests/baseline_images/timetree_geo_axis.png",
    "tests/baseline_images/stratigraphic_geo_axis.png",
    "tools/build_snapshot.py",
    "tools/make_diff.py",
    "tools/source/ics-chart-v2026-06.5.ttl",
    "tools/build-logs/ics_chart-2026-06.log.json",
    "examples/bio_phylo_timetree.py",
    "geophylo/data/snapshots/ics_chart-2026-06.json",
    "geophylo/data/snapshots/PROVENANCE.md",
    ".github/workflows/ci.yml",
)


def _member_names(archive: Path) -> set[str]:
    """wheel(zip) 与 sdist(tar.gz) 的统一成员视图（成员名保持归档内的原样）。"""
    if archive.suffix == ".whl" or zipfile.is_zipfile(archive):
        with zipfile.ZipFile(archive) as zf:
            return {name for name in zf.namelist() if not name.endswith("/")}
    with tarfile.open(archive, "r:gz") as tf:
        return {member.name for member in tf.getmembers() if member.isfile()}


def _matches(names: set[str], required: str) -> bool:
    return any(name == required or name.endswith("/" + required) for name in names)


def collect_problems(dist: Path) -> list[str]:
    """只检查工件内容，返回问题清单（空列表 == 通过）。"""
    wheels = sorted(dist.glob("*.whl"))
    sdists = sorted(dist.glob("*.tar.gz"))
    if not wheels or not sdists:
        return [f"dist 目录缺少 wheel 或 sdist：{dist}"]

    problems: list[str] = []
    wheel_names = _member_names(wheels[0])
    sdist_names = _member_names(sdists[0])

    for required in WHEEL_REQUIRED:
        if not _matches(wheel_names, required):
            problems.append(f"wheel 缺少 package-data: {required}")
    # 逐条独立断言，绝不写成 `A in names or B in names`。
    for needle, why in WHEEL_LICENSES:
        if not any(needle in name for name in wheel_names):
            problems.append(f"wheel 缺少 {needle}（{why}）")
        if not any(needle in name for name in sdist_names):
            problems.append(f"sdist 缺少 {needle}（{why}）")
    for required in SDIST_REQUIRED:
        if not _matches(sdist_names, required):
            problems.append(f"sdist 缺少 {required}（解包后无法自测）")
    return problems


def check_installed_library() -> list[str]:
    """安装产物可用 + 快照哈希可复现（必须在清洁 venv 里调用才有意义）。"""
    problems: list[str] = []
    try:
        from geophylo import Timescale
        from geophylo.data.builtin import canonical_payload_bytes, load_snapshot
    except Exception as exc:  # pragma: no cover - 只在真正的清洁室里触发
        return [f"无法导入已安装的 geophylo: {exc!r}"]

    try:
        ts = Timescale()
        if ts.find_by_age(66.0, rank="Period").name != "Paleogene":
            problems.append("Timescale().find_by_age(66.0) 结果不符合预期")
        if Timescale(version="2024/12").version != "2024/12":
            problems.append("Timescale(version='2024/12') 版本串不符")
    except Exception as exc:  # pragma: no cover
        problems.append(f"随包快照查询失败: {exc!r}")

    for version in ("2026/06", "2024/12"):
        try:
            snapshot = load_snapshot(version)
            digest = hashlib.sha256(canonical_payload_bytes(snapshot["intervals"])).hexdigest()
            if digest != snapshot["hash"]["payload_sha256"]:
                problems.append(f"快照 {version} 的 payload 哈希不可复现")
        except Exception as exc:  # pragma: no cover
            problems.append(f"快照 {version} 加载失败: {exc!r}")
    return problems


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: check_wheel.py <dist-dir>", file=sys.stderr)
        return 2
    dist = Path(argv[1])
    problems = collect_problems(dist) + check_installed_library()
    if problems:
        for problem in problems:
            print(f"FAIL: {problem}", file=sys.stderr)
        return 1
    wheels = sorted(dist.glob("*.whl"))
    sdists = sorted(dist.glob("*.tar.gz"))
    print(f"check_wheel: {wheels[0].name} 与 {sdists[0].name} 校验通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

"""重新生成视觉基准图（官方更新路径）。

用法（在仓库根目录）::

    python3 tests/update_baselines.py            # 重新生成全部基准图
    python3 tests/update_baselines.py --dry-run  # 只报告将写入哪些文件

为什么需要它：`pytest --mpl` 的门禁语义是"当前渲染必须等于已提交的基准图"，
所以基准图必须由**与 CI 相同的环境**（同 OS、同 matplotlib 版本、同字体）生成，
否则门禁会在别人的机器上永久变红。本脚本把 pytest-mpl 的
``--mpl-generate-path`` 输出原子地复制进 ``tests/baseline_images/``，
不改动任何测试代码。

纪律（见 docs/user-guide / RELEASE.md）：
1. 更新基准图必须与它对应的渲染改动在同一个 commit 里，PR 里附上图像 diff；
2. 只有视觉断言（test_visual.py 的逐区域结构断言）全绿时才允许刷新基准；
3. 不要在 Linux 之外刷新基准图后单独提交——CI 的 runner 是 ubuntu-latest。
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
BASELINE_DIR = TESTS_DIR / "baseline_images"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dry-run", action="store_true", help="只列出会更新的基准图，不写入")
    parser.add_argument(
        "--test",
        action="append",
        default=None,
        help="只重新生成匹配的测试（可重复），例如 --test test_visual_timetree_geo_axis",
    )
    args = parser.parse_args(argv)

    expression = " or ".join(args.test) if args.test else "visual"
    with tempfile.TemporaryDirectory(prefix="geophylo-baselines-") as tmp:
        outdir = Path(tmp)
        command = [
            sys.executable,
            "-m",
            "pytest",
            "-m",
            expression,
            "--mpl",
            f"--mpl-generate-path={outdir}",
            "-q",
            "-p",
            "no:cacheprovider",
        ]
        print("$", " ".join(command))
        completed = subprocess.run(command, cwd=TESTS_DIR.parent, check=False)
        generated = sorted(outdir.glob("*.png"))
        if not generated:
            print(
                "没有生成任何基准图：pytest-mpl 需要安装（.[test] extra），"
                "且测试必须带 @pytest.mark.mpl_image_compare。",
                file=sys.stderr,
            )
            return completed.returncode or 1
        for png in generated:
            target = BASELINE_DIR / png.name
            if args.dry_run:
                print(f"[dry-run] 会写入 {target.relative_to(TESTS_DIR.parent)}")
                continue
            BASELINE_DIR.mkdir(parents=True, exist_ok=True)
            shutil.copy2(png, target)
            print(f"已更新 {target.relative_to(TESTS_DIR.parent)}")
    if args.dry_run:
        return 0
    print(
        "\n基准图已更新。请用 `git diff --stat tests/baseline_images` 复核，"
        "并在 PR 描述里附上渲染改动的理由。"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

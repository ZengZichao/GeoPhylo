#!/usr/bin/env python3
"""Run a script whose file name contains non-ASCII characters, from an ASCII shell.

Some projects keep source files under names that are not pure ASCII. On a system
where typing those characters is awkward (a headless CI worker, a remote box
without an input method, a shell where tab completion is unreliable), invoking
such a script normally means fighting the path. This launcher takes the name as
a command-line argument instead, locates the file under a directory, and runs it
verbatim with ``runpy`` — the target sees exactly the interpreter, the working
directory and the environment it would have seen when called directly.

Usage::

    python examples/figures/run_script.py --stem <name-stem>
    python examples/figures/run_script.py --path <explicit/path/to/script.py>

``--stem`` is matched against file names anywhere under ``--scripts-dir``
(default: the current directory), so the caller only ever types ASCII.
``--out-dir`` is forwarded to the target as ``GEOPHYLO_FIGURE_OUT_DIR`` for
scripts that honour that variable; without it the target writes wherever it
normally would.

Nothing about any particular project is encoded here: this is a generic
shim, and the caller supplies the stem.
"""

from __future__ import annotations

import argparse
import os
import runpy
import sys
from pathlib import Path


def discover(root: Path, stem: str) -> Path | None:
    """Return the first file under ``root`` whose name ends with ``<stem>.py``."""
    matches = sorted(
        path
        for path in root.rglob(f"*{stem}.py")
        if path.is_file() and path.name != Path(__file__).name
    )
    return matches[0] if matches else None


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run a non-ASCII-named Python script without typing its name."
    )
    parser.add_argument(
        "--stem",
        help="file-name stem to look for (matched as *<stem>.py under --scripts-dir)",
    )
    parser.add_argument(
        "--path",
        help="explicit path to the script; skips discovery entirely",
    )
    parser.add_argument(
        "--scripts-dir",
        default=".",
        help="directory to search in (default: current directory)",
    )
    parser.add_argument(
        "--out-dir",
        default=None,
        help="forwarded to the target as GEOPHYLO_FIGURE_OUT_DIR",
    )
    parser.add_argument(
        "--show",
        action="store_true",
        help="print the resolved script path and exit without running it",
    )
    args = parser.parse_args()

    if args.path:
        script = Path(args.path).expanduser().resolve()
        if not script.is_file():
            sys.exit(f"no such script: {script}")
    elif args.stem:
        root = Path(args.scripts_dir).expanduser().resolve()
        if not root.is_dir():
            sys.exit(f"--scripts-dir is not a directory: {root}")
        script = discover(root, args.stem)
        if script is None:
            sys.exit(f"no file matching *{args.stem}.py under {root}")
    else:
        sys.exit("give either --stem or --path")

    if args.show:
        print(script)
        return 0

    if args.out_dir is not None:
        out_dir = Path(args.out_dir).expanduser().resolve()
        out_dir.mkdir(parents=True, exist_ok=True)
        os.environ["GEOPHYLO_FIGURE_OUT_DIR"] = str(out_dir)

    print(f"[run_script] {script}", flush=True)
    runpy.run_path(str(script), run_name="__main__")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""把 geophylo 里的异常/警告文案改写成 msg(en, zh) 双语形式。

用法：``python tools/migrate_i18n.py <file.py> <map.json>``

map.json 形如 ``{"48": "f\"{name} must not be None\"", ...}``，键是**原始文件**里
消息实参起始处的行号，值是英文文案的 Python 字面量源码。脚本用 AST 定位每条
``raise``/``warnings.warn`` 的消息实参，把**原中文片段逐字保留**为第二参数，
因此不会误伤相邻代码；一次遍历按偏移倒序替换，行号不会互相干扰。
"""

from __future__ import annotations

import ast
import json
import pathlib
import sys


def message_spans(src: str) -> list[tuple[int, int, int]]:
    """返回 (start, end, lineno)：每条 raise/warn 的消息实参的源码区间。"""
    tree = ast.parse(src)
    spans: list[tuple[int, int, int]] = []
    for node in ast.walk(tree):
        target = None
        if isinstance(node, ast.Raise) and isinstance(node.exc, ast.Call):
            target = node.exc.args[0] if node.exc.args else None
        elif (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "warn"
        ):
            target = node.args[0] if node.args else None
        if target is None:
            continue
        seg = ast.get_source_segment(src, target)
        if seg is None:  # pragma: no cover - 跨行复杂表达式
            continue
        # 用 ast 的 col_offset 定位更稳：逐行累加。
        lines = src.splitlines(keepends=True)
        offset = sum(len(line) for line in lines[: target.lineno - 1]) + target.col_offset
        end = offset + len(seg)
        assert src[offset:end] == seg, (target.lineno, seg[:40])
        spans.append((offset, end, target.lineno))
    return sorted(set(spans), reverse=True)


def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__)
        return 2
    path = pathlib.Path(sys.argv[1])
    mapping = json.loads(pathlib.Path(sys.argv[2]).read_text(encoding="utf-8"))
    src = path.read_text(encoding="utf-8")
    spans = message_spans(src)
    seen: set[int] = set()
    for offset, end, lineno in spans:
        key = str(lineno)
        if key not in mapping:
            continue
        seen.add(lineno)
        zh = src[offset:end]
        en = mapping[key].strip()
        src = src[:offset] + f"msg({en}, {zh})" + src[end:]
    missing = set(mapping) - {str(n) for n in seen}
    if missing:
        print(f"警告：map 中未命中的行号 {sorted(int(m) for m in missing)}")
    path.write_text(src, encoding="utf-8")
    print(f"{path}: 已改写 {len(seen)} 处")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

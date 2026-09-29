"""运行时出处披露的回归测试。

推导快照必须在运行时就让人看到"这是回退推导的快照、不是上游归档"：光靠仓库里的
`PROVENANCE.md`、或者一个没有代码消费的 `derived_from` 字段，都做不到这一点。
本文件把这几件事钉住：

1. 基线快照的出处可读，且 ``derived_from`` 为空；
2. 推导快照既在 ``provenance`` 里给出机器可读出处，又在构造时发一次 UserWarning；
3. 出处文档缺失时 ``snapshot_provenance`` 抛 ``DataValidationError``——披露由此
   变成有代码依赖的运行时读取项，而不是只躺在仓库里；wheel 侧的打包正确性由
   ``tests/test_packaging.py`` 的构建产物断言负责（实测：本文档随
   ``MANIFEST.in`` + ``include-package-data`` 进 wheel，单删 package-data 的
   ``*.md`` 不会让它消失，故不在此处假装那条是承重测试）。
4. 离线 `from_json()` 的载荷不回报索引里的哈希（避免虚假出处声明）。
"""

from __future__ import annotations

import json
import warnings
from pathlib import Path

import pytest

from geophylo import Timescale
from geophylo.data import builtin, snapshot_provenance
from geophylo.exceptions import DataValidationError

DERIVED_VERSION = "2024/12"


def test_baseline_provenance_is_readable_and_not_derived() -> None:
    ts = Timescale()
    prov = ts.provenance
    assert prov is not None, "基线快照应能读到出处披露"
    assert prov["derived_from"] is None, "基线快照不应被标为推导产物"
    assert prov["version"] == ts.version
    assert prov["payload_sha256"] == snapshot_provenance()["payload_sha256"]
    assert len(prov["provenance_document"]) > 500, "出处文档正文应随包可读"
    assert "supersedes" not in prov, "单一修订的快照不应携带历史修订字段"


def test_derived_snapshot_exposes_provenance_and_warns_once() -> None:
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        ts = Timescale(version=DERIVED_VERSION)
    derived = [
        w for w in caught if issubclass(w.category, UserWarning) and "推导快照" in str(w.message)
    ]
    assert len(derived) == 1, (
        f"构造推导快照应恰好发一次警告，实际 {[str(w.message)[:60] for w in caught]}"
    )
    assert derived[0].filename == __file__, "警告应指向调用方（stacklevel 被改坏时会失败）"
    prov = ts.provenance
    assert prov is not None and prov["derived_from"] is not None
    assert prov["derived_from"]["chart_version"], "derived_from 必须说明从哪个版本推导"
    assert prov["derived_from"]["method"], "derived_from 必须说明推导方法"
    assert "not" in prov["provenance_document"].lower(), "文档应显式否认上游归档身份"


def test_missing_provenance_document_is_a_hard_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """PROVENANCE.md 不在安装产物里时必须报错，而不是静默少一份披露。"""
    real_files = builtin.resources.files

    class _Stripped:
        def __truediv__(self, name: str):
            target = real_files(builtin.SNAPSHOT_PACKAGE) / name
            if name == builtin.PROVENANCE_FILENAME:

                class _Missing:
                    def is_file(self) -> bool:
                        return False

                return _Missing()
            return target

    monkeypatch.setattr(builtin.resources, "files", lambda pkg: _Stripped())
    with pytest.raises(DataValidationError, match=r"PROVENANCE\.md"):
        snapshot_provenance()
    # 真实路径仍可读，证明上面的报错来自缺失分支而非测试环境损坏。
    assert Path(real_files(builtin.SNAPSHOT_PACKAGE) / builtin.PROVENANCE_FILENAME).is_file()


def test_offline_payload_does_not_inherit_published_hashes(tmp_path: Path) -> None:
    """离线载荷的 chart_version 可能与已发布版本同名；此时不得回报索引哈希。"""
    source = Path(builtin.__file__).resolve().parent / "snapshots" / "ics_chart-2026-06.json"
    payload = json.loads(source.read_text(encoding="utf-8"))
    offline = tmp_path / "offline.json"
    offline.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    ts = Timescale.from_json(offline)
    assert ts.version == "2026/06"
    assert ts.provenance is None, "非经 versions.json 加载的实例不得声称已发布出处"
    assert Timescale(backend=None).provenance is not None, "对照组：经索引加载者有出处"

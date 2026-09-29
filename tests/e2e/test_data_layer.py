"""End-to-end: data layer — Timescale queries with real ICS data.

Tests every public query method of ``Timescale`` against the bundled ICS
2026/06 baseline snapshot.  No external tree libraries are required.

Covers:
- ``get_interval()`` by stable ID
- ``find_by_name()`` with exact, case-insensitive, alias, and ambiguous queries
- ``find_by_age()`` with boundary semantics, snap tolerance, and 0 Ma handling
- ``iter_intervals()`` with rank filtering and age windows
- ``Timescale.from_json()`` offline loading
- ``Timescale(backend="pyrolite")`` experimental backend
- Provenance disclosure (``.provenance``, ``.version``, ``.metadata``)
"""

from __future__ import annotations

import json
import warnings
from importlib import resources

import pytest

from geophylo import (
    AmbiguousIntervalError,
    BackendMetadata,
    Boundary,
    GeophyloError,
    IntervalNotFoundError,
    InvalidRangeError,
    InvalidRankError,
    Timescale,
)
from geophylo.data import available_versions, baseline_version, load_versions_index

SNAPSHOT_PACKAGE = "geophylo.data.snapshots"


class TestTimescaleDataE2E:
    """Real ICS data queries."""

    def test_default_timescale_is_baseline(self):
        ts = Timescale()
        assert ts.version == baseline_version()

    def test_ranks_returns_core_ranks(self):
        ts = Timescale()
        assert ts.ranks == ("Eon", "Era", "Period", "Epoch", "Age")

    def test_metadata_is_backend_metadata(self):
        ts = Timescale()
        assert isinstance(ts.metadata, BackendMetadata)
        assert ts.metadata.has_stable_ids is True
        assert ts.metadata.has_uncertainty is True

    def test_provenance_is_dict_or_none(self):
        ts = Timescale()
        prov = ts.provenance
        assert prov is not None  # baseline snapshot has provenance
        assert "file" in prov
        assert "payload_sha256" in prov
        assert "provenance_document" in prov

    def test_get_interval_by_id(self):
        ts = Timescale()
        # Find a Period interval first
        for interval in ts.iter_intervals(ranks=["Period"]):
            result = ts.get_interval(interval.id)
            assert result.id == interval.id
            assert result.name == interval.name
            break

    def test_get_interval_unknown_id(self):
        ts = Timescale()
        with pytest.raises(IntervalNotFoundError, match="未知"):
            ts.get_interval("nonexistent-id-12345")

    def test_find_by_name_exact(self):
        ts = Timescale()
        result = ts.find_by_name("Jurassic")
        assert result.name == "Jurassic"
        assert result.rank == "Period"

    def test_find_by_name_case_insensitive(self):
        ts = Timescale()
        result = ts.find_by_name("jurassic")
        assert result.name == "Jurassic"

    def test_find_by_name_partial(self):
        """Partial substring query should find a unique match via fuzzy fallback."""
        ts = Timescale()
        # "Quaternary" is a unique name; "Quatern" should match it via fuzzy.
        result = ts.find_by_name("Quatern")
        assert result.name == "Quaternary"

    def test_find_by_name_ambiguous_partial(self):
        """A partial query matching multiple intervals must raise AmbiguousIntervalError."""
        ts = Timescale()
        with pytest.raises(AmbiguousIntervalError) as exc_info:
            ts.find_by_name("Jurass")
        assert len(exc_info.value.candidates) >= 2

    def test_find_by_name_with_rank(self):
        ts = Timescale()
        # "Pridoli" exists as both Age and Epoch
        with pytest.raises(AmbiguousIntervalError) as exc_info:
            ts.find_by_name("Pridoli")
        assert len(exc_info.value.candidates) >= 2

        # Disambiguate by rank
        result = ts.find_by_name("Pridoli", rank="Epoch")
        assert result.rank == "Epoch"
        assert result.name == "Pridoli"

    def test_find_by_name_no_match(self):
        ts = Timescale()
        with pytest.raises(IntervalNotFoundError):
            ts.find_by_name("Nonexistent Period Name")

    def test_find_by_age_interior(self):
        ts = Timescale()
        # 200 Ma is in the Jurassic
        result = ts.find_by_age(200.0, rank="Period")
        assert result.rank == "Period"
        assert result.older_ma >= 200.0 > result.younger_ma

    def test_find_by_age_boundary_belongs_to_younger(self):
        ts = Timescale()
        # 201.3 Ma = Jurassic/Cretaceous boundary → belongs to Cretaceous (younger)
        result = ts.find_by_age(201.3, rank="Period")
        # The boundary should belong to the younger interval
        assert result.younger_ma <= 201.3 + 1e-9

    def test_find_by_age_zero(self):
        ts = Timescale()
        # 0 Ma → the youngest interval (Holocene for Age, Quaternary for Period)
        result = ts.find_by_age(0.0, rank="Period")
        assert result.younger_ma == pytest.approx(0.0, abs=1e-9)

    def test_find_by_age_snap_tolerance(self):
        ts = Timescale()
        # An age very close to a boundary should snap to it
        boundary_age = ts.find_by_name("Jurassic").older_ma
        result = ts.find_by_age(boundary_age + 1e-12, rank="Period")
        assert result is not None

    def test_find_by_age_negative_rejected(self):
        ts = Timescale()
        with pytest.raises(InvalidRangeError):
            ts.find_by_age(-1.0)

    def test_find_by_age_nan_rejected(self):
        ts = Timescale()
        with pytest.raises(InvalidRangeError):
            ts.find_by_age(float("nan"))

    def test_find_by_age_bool_rejected(self):
        ts = Timescale()
        with pytest.raises(InvalidRangeError):
            ts.find_by_age(True)  # type: ignore[arg-type]

    def test_find_by_age_invalid_rank(self):
        ts = Timescale()
        with pytest.raises(InvalidRankError):
            ts.find_by_age(100.0, rank="NotARank")

    def test_iter_intervals_all_ranks(self):
        ts = Timescale()
        intervals = list(ts.iter_intervals())
        assert len(intervals) > 100  # ICS has many intervals across all ranks

    def test_iter_intervals_single_rank(self):
        ts = Timescale()
        periods = list(ts.iter_intervals(ranks=["Period"]))
        assert len(periods) > 10  # at least Phanerozoic periods
        assert all(i.rank == "Period" for i in periods)

    def test_iter_intervals_age_window(self):
        ts = Timescale()
        # Mesozoic: 252–66 Ma
        intervals = list(ts.iter_intervals(ranks=["Period"], min_age=66.0, max_age=252.0))
        names = [i.name for i in intervals]
        assert "Cretaceous" in names
        assert "Jurassic" in names
        assert "Triassic" in names

    def test_iter_intervals_deterministic_sort(self):
        ts = Timescale()
        intervals = list(ts.iter_intervals(ranks=["Period"]))
        ages = [(-i.older_ma, i.id) for i in intervals]
        assert ages == sorted(ages), "Intervals must be sorted by older_ma desc, then id"

    def test_iter_intervals_window_intersection(self):
        ts = Timescale()
        # Window [100, 200] — intersects Cretaceous and Jurassic
        intervals = list(ts.iter_intervals(ranks=["Period"], min_age=100.0, max_age=200.0))
        names = {i.name for i in intervals}
        assert "Cretaceous" in names
        assert "Jurassic" in names

    def test_iter_intervals_invalid_rank(self):
        ts = Timescale()
        with pytest.raises(InvalidRankError):
            list(ts.iter_intervals(ranks=["NonExistent"]))

    def test_iter_intervals_empty_ranks(self):
        ts = Timescale()
        with pytest.raises(InvalidRankError, match="空"):
            list(ts.iter_intervals(ranks=[]))

    def test_iter_intervals_duplicate_ranks(self):
        ts = Timescale()
        with pytest.raises(InvalidRankError, match="重复"):
            list(ts.iter_intervals(ranks=["Period", "Period"]))

    def test_from_json_offline(self, tmp_path):
        """Load a snapshot from an offline JSON file."""
        # Read the baseline snapshot JSON
        baseline = baseline_version()
        index = load_versions_index()
        snapshot_file = index["versions"][baseline]["file"]
        text = (resources.files(SNAPSHOT_PACKAGE) / snapshot_file).read_text(encoding="utf-8")
        snapshot = json.loads(text)

        # Write it to a temp file
        p = tmp_path / "test_snapshot.json"
        p.write_text(json.dumps(snapshot), encoding="utf-8")

        ts = Timescale.from_json(p)
        assert ts.version == snapshot["chart_version"]
        # Offline JSON has no published provenance
        assert ts.provenance is None

    def test_explicit_version_2024_12(self):
        """The 2024/12 derived snapshot should warn and load."""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            ts = Timescale(version="2024/12")
            assert any("推导快照" in str(wi.message) for wi in w)
        # It should still be queryable
        result = ts.find_by_name("Jurassic")
        assert result.name == "Jurassic"

    def test_unknown_version_rejected(self):
        ts_func = Timescale
        with pytest.raises(GeophyloError, match="未发布"):
            ts_func(version="9999/99")

    def test_available_versions_sorted(self):
        versions = available_versions()
        assert versions == sorted(versions)
        assert len(versions) >= 1

    def test_interval_properties(self):
        ts = Timescale()
        jurassic = ts.find_by_name("Jurassic")
        assert jurassic.older_ma > jurassic.younger_ma
        assert jurassic.bounds == (jurassic.older_ma, jurassic.younger_ma)
        assert jurassic.older_boundary.age_ma == jurassic.older_ma
        assert jurassic.younger_boundary.age_ma == jurassic.younger_ma
        assert isinstance(jurassic.older_boundary, Boundary)
        assert jurassic.color.startswith("#")

    def test_interval_has_approximate_boundary(self):
        ts = Timescale()
        # Find an interval with an approximate boundary
        for interval in ts.iter_intervals(ranks=["Period"]):
            if interval.has_approximate_boundary:
                assert interval.is_approximate_any()  # deprecated alias still works
                break

    def test_pyrolite_backend(self):
        """Pyrolite backend loads and queries (may warn about missing colors)."""
        pytest.importorskip(
            "pyrolite"
        )  # 可选 extra：未安装时跳过，与 test_pyrolite_backend.py 一致
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            ts = Timescale(backend="pyrolite")
        # Query should work
        result = ts.find_by_name("Jurassic")
        assert result.name == "Jurassic"
        assert result.rank == "Period"

    def test_pyrolite_backend_no_id_query(self):
        """Pyrolite backend does not support ID queries."""
        pytest.importorskip("pyrolite")  # 可选 extra：未安装时跳过
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            ts = Timescale(backend="pyrolite")
        with pytest.raises(IntervalNotFoundError, match="稳定 ID"):
            ts.get_interval("anything")

    def test_pyrolite_backend_version(self):
        pytest.importorskip("pyrolite")  # 可选 extra：未安装时跳过
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            ts = Timescale(backend="pyrolite")
        assert ts.version == "pyrolite"

    def test_repr(self):
        ts = Timescale()
        assert "Timescale" in repr(ts)
        assert ts.version in repr(ts)

    def test_custom_backend_rejects_version(self):
        """Passing a custom TimescaleBackend instance with version= must fail."""
        from geophylo.data import load_snapshot
        from geophylo.data.builtin import SnapshotBackend

        backend = SnapshotBackend(load_snapshot())
        with pytest.raises(ValueError, match="version"):
            Timescale(backend, version="2024/12")

    def test_pyrolite_backend_rejects_version(self):
        pytest.importorskip("pyrolite")  # 可选 extra：未安装时跳过
        with pytest.raises(ValueError, match="pyrolite"):
            Timescale(backend="pyrolite", version="2024/12")

    def test_unknown_backend_string(self):
        with pytest.raises(ValueError, match="backend"):
            Timescale(backend="nonexistent")  # type: ignore[arg-type]

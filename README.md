# geophylo

English | [中文](README.zh-CN.md)

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.23060662.svg)](https://doi.org/10.5281/zenodo.23060662)

A geological timescale visualisation library for Matplotlib Axes. It ships the
ICS (International Commission on Stratigraphy) International Chronostratigraphic
Chart as reproducible, version-pinned built-in snapshots and overlays them onto
time-calibrated trees — or onto any plot whose x- or y-axis is time in Ma
(millions of years ago).

The R ecosystem has `deeptime`, which provides `coord_geo()` for ggplot2 and
ggtree; `geophylo` brings the equivalent capability to the Matplotlib ecosystem.
The library puts **coordinate-semantics correctness and reproducibility** first:
whenever the coordinate semantics cannot be determined, it raises an explicit
error instead of guessing silently.

## Feature overview

- **Reproducible ICS data access**: `Timescale` reads the versioned snapshots
  distributed with the package, covering the five core geochronologic ranks:
  Eon, Era, Period, Epoch and Age. Snapshots preserve per-boundary `~`
  approximate values, quantitative uncertainties (`±`), and GSSP (Global
  Boundary Stratotype Section and Point) / GSSA (Global Standard
  Stratigraphic Age) definition states. `Timescale(version="2024/12")` opts
  into the historical snapshot.
- **Linear geological time axes**: `add_geo_axis()` overlays geological time
  strips inside the host Axes using inset tracks, with multi-rank tracks,
  numeric ticks, automatic label degradation and automatic contrast colors,
  while guaranteeing that the host Axes' view state is left untouched.
- **Explicit coordinate contract**: `CoordinateSpec` (with `absolute_age` and
  `root_distance` modes) is the single source of truth for coordinate
  semantics; `spec_from_biophylo()` builds and validates the contract from a
  Bio.Phylo tree.
- **Radial layout (experimental)**: `RadialSpec` + `add_geo_ring()` overlay a
  geological time ring on native polar Axes; `radial_spec_from_biophylo()` is
  the radial adapter entry point. These APIs are experimental; their
  signatures are not frozen.
- **Strong contract-driven exception hierarchy**: every public exception
  inherits from `GeophyloError`. `AmbiguousIntervalError` is a subclass of
  `IntervalNotFoundError`; the inheritance is kept for compatibility with
  existing `except` clauses, so code should catch `AmbiguousIntervalError`
  before `IntervalNotFoundError`. See the "Exceptions and catch order"
  section of the user guide.

## Documentation

- [User guide](docs/user-guide.en.md) (full tutorial, parameter reference,
  FAQ and troubleshooting)
- [中文使用文档](docs/user-guide.zh.md)（完整教程、参数详解、FAQ 和排错指南）
- [Data policy](docs/data-policy.md) (provenance, licensing, update and
  rollback of the ICS snapshots)
- [Architecture decision records](docs/adr/README.md) (ADR-1…ADR-5: non-obvious
  choices and the alternatives they rejected)

## Installation

> The PyPI release is not published yet: the `pip install` commands below that
> name the package will fail to resolve until then. Install from the source
> tree with `pip install .`; for a full test environment use
> `pip install -e ".[test]"`.

```bash
pip install geophylo            # core (matplotlib + numpy only)
pip install "geophylo[biopython]"   # Bio.Phylo adapter
pip install "geophylo[iplotx]"      # iplotx adapter (experimental)
pip install "geophylo[pyrolite]"    # experimental read-only pyrolite backend
pip install "geophylo[test]"        # tests
```

## Quick start: a Bio.Phylo timetree

```python
from io import StringIO

import matplotlib.pyplot as plt
from Bio import Phylo

from geophylo import add_geo_axis, spec_from_biophylo

tree = Phylo.read(StringIO("((A:15.0, B:15.0):9.0, (C:14.0, D:14.0):10.0);"), "newick")

fig, ax = plt.subplots(figsize=(12, 8))
Phylo.draw(tree, axes=ax, do_show=False)

# root_age comes from an external time-calibration result; age_conversion
# declares the unit conversion from branch lengths to Ma.
spec = spec_from_biophylo(tree, ax, time_axis="x", age_conversion=1.0, root_age=48.0)

result = add_geo_axis(ax, spec=spec, position="bottom",
                      ranks=["Period", "Epoch"], tick_style="boundaries")
plt.tight_layout()
result.finalize()   # run once before savefig: exact label layout, then freeze
fig.savefig("timetree_with_geo.png", dpi=300)
```

## Quick start: any Matplotlib plot (stratigraphic-column style)

```python
import matplotlib.pyplot as plt
from geophylo import CoordinateSpec, add_geo_axis

fig, ax = plt.subplots(figsize=(12, 6))
ax.plot([0, 300], [0, 1])  # any plot content
spec = CoordinateSpec.absolute(time_axis="x", age_range=(0.0, 300.0))
result = add_geo_axis(ax, spec=spec, position="bottom", ranks=["Period"])
plt.tight_layout()
result.finalize()
```

The library never infers coordinate ranges on its own. The only inference
entry point is `CoordinateSpec.from_data_limits()`:

```python
CoordinateSpec.from_data_limits(ax, mode=..., time_axis=...,
                                acknowledge_inference=True)
```

The default call raises `CoordinateError`; the caller must pass
`acknowledge_inference=True` explicitly to acknowledge the inference.

## Quick start: querying the data

```python
from geophylo import Timescale

ts = Timescale()                              # baseline snapshot
ts.find_by_age(66.0, rank="Period").name      # 'Paleogene'
ts.get_interval("ics:period:jurassic").bounds # (older_ma, younger_ma)
list(ts.iter_intervals(ranks=["Epoch"], min_age=0, max_age=66))
```

## Circular trees (experimental)

See [examples/circular_tree.py](examples/circular_tree.py). The tree is drawn
by the user, and the tree and `add_geo_ring()` must share the same
`RadialSpec` instance, so that the age at a given radius on the ring and the
age at the same radius on the tree agree by construction.

## Data provenance and licensing

The bundled snapshots are generated deterministically from the ICS official
versioned data (CC-BY-4.0) by `tools/build_snapshot.py`, distributed with the
package, and append-only. The machine-readable field-level diff between
versions is `geophylo/data/snapshots/diff-2024-12_to_2026-06.json` (generated
by `tools/make_diff.py`); per-snapshot generation logs live in
`tools/build-logs/`; the provenance of the derived `2024/12` snapshot is
documented in
[`geophylo/data/snapshots/PROVENANCE.md`](geophylo/data/snapshots/PROVENANCE.md).

For citation and attribution of the ICS data, see [NOTICE](NOTICE) and
[docs/data-policy.md](docs/data-policy.md). The library's source code is
released under the MIT license (see [LICENSE](LICENSE)); the licenses of the
third-party data files are independent of the code license.

## Compatibility

- Python 3.11–3.14; Matplotlib ≥ 3.10, < 4; NumPy ≥ 1.25.
- The library runs headless (Agg backend). Examples are all organised as
  `add_geo_axis() → tight_layout() → finalize() → savefig()`.

## Development

```bash
pip install -e ".[dev]"
pytest                       # full test suite (blocking gate)
pytest -m "not experimental" # stable API only
ruff check geophylo tests tools examples
mypy
```

The release procedure (public GitHub repository + Zenodo DOI) is described in
[RELEASE.md](RELEASE.md).

## Author & Citation

- **Author**: Zichao Zeng (曾子超) —
  Email: zengzichao@sjtu.edu.cn —
  ORCID: [0000-0001-6553-970X](https://orcid.org/0000-0001-6553-970X) —
  School of Life Sciences and Biotechnology, Shanghai Jiao Tong University.

If you use geophylo in your research, please cite it (see
[CITATION.cff](CITATION.cff) for the machine-readable citation record;
concept DOI `10.5281/zenodo.23060662`, version DOI
`10.5281/zenodo.23060663` for v0.1.0) and, as required by the CC BY
4.0 license, cite the International Chronostratigraphic Chart separately (see
[NOTICE](NOTICE) for the required attribution).

## License

Source code: MIT ([LICENSE](LICENSE)). Bundled ICS chart data: CC-BY-4.0
([LICENSES/CC-BY-4.0.txt](LICENSES/CC-BY-4.0.txt), attribution in
[NOTICE](NOTICE)).

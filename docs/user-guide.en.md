# GeoPhylo User Guide

**Version**: corresponds to GeoPhylo 0.1.0 (including the experimental symbols)
**Requirements**: Python 3.11–3.14 · Matplotlib ≥ 3.10, < 4 · NumPy ≥ 1.25
**中文版文档**：[user-guide.zh.md](user-guide.zh.md)

---

## Contents

1. [Introduction](#1-introduction)
2. [Installation](#2-installation)
3. [Quick start in five minutes](#3-quick-start-in-five-minutes)
4. [Core concept: the coordinate-semantics contract](#4-core-concept-the-coordinate-semantics-contract)
5. [Querying the data: Timescale](#5-querying-the-data-timescale)
6. [Linear geological time strips: add_geo_axis()](#6-linear-geological-time-strips-add_geo_axis)
7. [The GeoAxisResult lifecycle](#7-the-geoaxisresult-lifecycle)
8. [Bio.Phylo adapter: spec_from_biophylo()](#8-biophylo-adapter-spec_from_biophylo)
9. [Radial time rings (experimental): RadialSpec and add_geo_ring()](#9-radial-time-rings-experimental-radialspec-and-add_geo_ring)
10. [iplotx adapter (experimental)](#10-iplotx-adapter-experimental)
11. [The pyrolite backend (experimental)](#11-the-pyrolite-backend-experimental)
12. [Exceptions and troubleshooting](#12-exceptions-and-troubleshooting)
13. [FAQ](#13-faq)
14. [Example scripts](#14-example-scripts)
15. [Data provenance, licence and citation](#15-data-provenance-licence-and-citation)

---

## 1. Introduction

`geophylo` is a geological timescale visualisation library for Matplotlib: it
overlays the International Chronostratigraphic Chart (ICS) — shipped as
**reproducible, versioned snapshots** — onto time-calibrated phylogenies
(timetrees) or any figure whose axes are expressed in Ma (millions of years).

The R package `deeptime` provides this capability to ggplot2/ggtree through
`coord_geo()`; `geophylo` fills the same niche in the Python/Matplotlib
ecosystem, with **coordinate-semantics correctness and reproducibility** as its
first design priority:

- **If the coordinate semantics cannot be determined, the library raises — it
  never guesses.** Every public entry point validates the semantics explicitly;
  inference is only available through a single entry point that requires an
  explicit `acknowledge_inference=True`.
- **Snapshots are append-only and hash-verified.** ICS data ships as versioned
  JSON snapshots whose SHA-256 payload hash is checked on load; the same
  snapshot version always answers queries identically.
- **Your figure is never mutated.** Time strips live in inset track Axes; the
  host Axes' limits, scales, autoscale flags and `dataLim` are field-for-field
  identical before and after the call.
- **Strongly typed public exceptions.** Everything inherits from
  `GeophyloError`; raw third-party `TypeError`/`ValueError` instances never
  escape a public entry point.

**Explicit non-goals**: GeoPhylo does not draw trees (rectangular trees are
drawn by Bio.Phylo or iplotx; circular trees follow the recipe in section 9),
does not infer time calibration, and never updates data over the network.

---

## 2. Installation

```bash
pip install geophylo                 # core (Matplotlib + NumPy only)
pip install "geophylo[biopython]"    # Bio.Phylo adapter (stable API)
pip install "geophylo[iplotx]"       # iplotx adapter (experimental)
pip install "geophylo[pyrolite]"     # experimental read-only data backend
pip install "geophylo[test,dev]"     # tests, lint, type checks
```

Install from source (development mode):

```bash
git clone <repository-url> geophylo
cd geophylo
pip install -e ".[dev]"
pytest                # full suite
pytest -m "not experimental"   # stable API scope only
```

Headless environments (servers, CI) work out of the box via the Agg backend.

---

## 3. Quick start in five minutes

### 3.1 A Bio.Phylo timetree with geological time strips

```python
from io import StringIO

import matplotlib.pyplot as plt
from Bio import Phylo

from geophylo import add_geo_axis, spec_from_biophylo

tree = Phylo.read(
    StringIO("((A:15.0, B:15.0):9.0, (C:14.0, D:14.0):10.0);"), "newick"
)

fig, ax = plt.subplots(figsize=(12, 8))
Phylo.draw(tree, axes=ax, do_show=False)

# root_age comes from an external time calibration; age_conversion declares
# the unit of the branch lengths (1.0 = already in Ma).
spec = spec_from_biophylo(tree, ax, time_axis="x", age_conversion=1.0, root_age=48.0)

result = add_geo_axis(ax, spec=spec, position="bottom",
                      ranks=["Period", "Epoch"], tick_style="boundaries")
plt.tight_layout()
result.finalize()   # run the precise label layout now, then freeze it
fig.savefig("timetree_with_geo.png", dpi=300)
```

The recommended call order is **`add_geo_axis()` → `tight_layout()` →
`result.finalize()` → `savefig()`**: text extents can only be measured once the
figure has its final size, and `finalize()` runs the precise label layout
immediately and freezes it.

### 3.2 Any Matplotlib figure (stratigraphic-column style)

No tree library required — just annotate a figure whose x-axis is in Ma:

```python
import matplotlib.pyplot as plt
from geophylo import CoordinateSpec, add_geo_axis

fig, ax = plt.subplots(figsize=(10, 4))
# ... draw your data on ax (x in Ma; call ax.invert_xaxis() for 0 on the right) ...

# Declare explicitly: time along x, absolute-age mode, semantic range 0-298.9 Ma
# (the Carboniferous-Permian boundary in the bundled ICS snapshot)
spec = CoordinateSpec.absolute(time_axis="x", age_range=(0.0, 298.9))
result = add_geo_axis(ax, spec=spec, position="bottom", ranks=["Period"])
result.finalize()
fig.savefig("strat_column.png", dpi=300)
```

### 3.3 Querying the data (no plotting)

```python
from geophylo import Timescale

ts = Timescale()                               # baseline snapshot (2026/06)
ts.find_by_age(66.0, rank="Period").name       # 'Paleogene'
ts.get_interval("ics:period:jurassic").bounds  # (older_ma, younger_ma)
list(ts.iter_intervals(ranks=["Epoch"], min_age=0, max_age=66))
```

---

## 4. Core concept: the coordinate-semantics contract

### 4.1 Why a CoordinateSpec

The time axis of a timetree figure can carry two different meanings:

- **absolute age** (`absolute_age`): every axis value is an age in Ma;
- **distance from the root** (`root_distance`): every axis value is the
  accumulated branch length from the root, which differs from Ma by a scale
  factor and a root-age anchor.

Visually the two can look identical; conflating them silently displaces or
rescales the geological strips — a scientific error. GeoPhylo's answer: the
semantics are declared in a frozen `CoordinateSpec` that is the single source
of truth; drawing functions consume it and never guess.

### 4.2 Constructors

```python
from geophylo import CoordinateSpec

# Absolute-age mode: root_age must be None
spec = CoordinateSpec.absolute(time_axis="x", age_range=(0.0, 300.0))

# Root-distance mode: root_age is required (from an external time calibration)
spec = CoordinateSpec.root_distance(time_axis="x", age_range=(0.0, 100.0),
                                    root_age=100.0)

# Direct construction follows the same validation rules
spec = CoordinateSpec(time_axis="x", mode="root_distance",
                      age_range=(0.0, 48.0), root_age=48.0)
```

| Field | Meaning | Constraint |
| --- | --- | --- |
| `time_axis` | which axis carries time | `"x"` or `"y"` |
| `mode` | coordinate mode | `"absolute_age"` or `"root_distance"` |
| `age_range` | semantic range `(min_age, max_age)` | `0 <= min_age < max_age`; defines the domain of valid conversions |
| `root_age` | root age (Ma) | required in `root_distance` mode; must be `None` in `absolute_age` mode |

> **`age_range` versus the drawing window**: `age_range` is the declared
> semantic range (the domain of valid conversions); `min_age`/`max_age` are the
> window of one particular draw (the clipping bounds). The window may be
> narrower than `age_range` but must lie inside it.

### 4.3 Age to data coordinates

`spec.age_to_data(age_ma)` is a pure function:

- `absolute_age` mode: returns `age_ma` itself;
- `root_distance` mode: returns `root_age - age_ma`.

It does **not** handle axis inversion — `ax.invert_xaxis()` and friends are
view transforms owned by Matplotlib. The patch data coordinates for a given age
are identical under normal and inverted views; only the display direction
changes. Out-of-domain input (NaN, out of range, negative root distance)
raises `CoordinateError`.

### 4.4 Truth table

| `mode` | `time_axis` | Axis direction | `age_to_data(age)` | Display |
| --- | --- | --- | --- | --- |
| `absolute_age` | `x` | normal | `age` | older to the right |
| `absolute_age` | `x` | inverted | `age` | older to the left |
| `absolute_age` | `y` | normal | `age` | older towards the top |
| `absolute_age` | `y` | inverted | `age` | older towards the bottom |
| `root_distance` | `x` | normal | `root_age - age` | root left, leaves right |
| `root_distance` | `x` | inverted | `root_age - age` | root right, leaves left |
| `root_distance` | `y` | normal | `root_age - age` | root bottom, leaves top |
| `root_distance` | `y` | inverted | `root_age - age` | root top, leaves bottom |

Display-direction recommendation: keep the direction consistent across one
set of figures and aligned with the stratigraphic convention (older to the
left / bottom) — draw horizontal timetrees in `root_distance` mode with the
**normal** view (root left, leaves right) and `absolute_age` axes on `x` with
the **inverted** view; use the mirrored directions only for a specific layout
reason.

### 4.5 Range inference (rejected by default)

Inferring `age_range` from the Axes data range is an implicit assumption and
raises `CoordinateError` by default. To opt in explicitly:

```python
spec = CoordinateSpec.from_data_limits(
    ax, mode="absolute_age", time_axis="x",
    acknowledge_inference=True,   # "I accept this inference"
)
```

Inference reads the host's **view limits** (`get_xlim()`/`get_ylim()`) and
normalises inverted axes by numeric magnitude. In `root_distance` mode a
`root_age` is still required.

---

## 5. Querying the data: Timescale

### 5.1 Construction and versions

```python
from geophylo import Timescale

ts = Timescale()                    # baseline snapshot (annotated in versions.json)
ts = Timescale(version="2024/12")   # any published historical snapshot
ts = Timescale.from_json("my.json") # offline custom table (same schema validation)
ts = Timescale(backend="pyrolite")  # experimental read-only backend (section 11)

ts.version        # e.g. '2026/06'
ts.ranks          # ('Eon', 'Era', 'Period', 'Epoch', 'Age')
ts.metadata       # BackendMetadata (data version, capabilities, rank map)
```

`geophylo.data.builtin.available_versions()` lists the published versions.
Requesting an unpublished version raises `DataValidationError` (the message
lists what is available).

### 5.2 The three query channels

**By stable ID** (the only entry point that accepts IDs):

```python
ts.get_interval("ics:period:jurassic")
ts.get_interval("ics:period:jurassic").bounds       # (older_ma, younger_ma)
ts.get_interval("ics:period:jurassic").boundaries   # (Boundary, Boundary)
```

Passing a *name* raises `IntervalNotFoundError` with a hint to use
`find_by_name()`.

**By name/alias** (case-folded substring matching; channel priority
name → aliases → label):

```python
ts.find_by_name("Holocene")
ts.find_by_name("Jurassic")                                 # exact name, unique hit
ts.find_by_name("cambrian", case_sensitive=False)           # case-insensitive exact match
ts.find_by_name("Upper", rank="Epoch", parent="ics:period:cretaceous")  # disambiguate by rank+parent
```

Zero hits raise `IntervalNotFoundError`; two or more raise
`AmbiguousIntervalError` (`exc.candidates` carries the candidate IDs).

**By age** (semantics in 5.3):

```python
ts.find_by_age(66.0, rank="Period").name    # 'Paleogene'
ts.find_by_age(66.0, rank="Era").name       # 'Cenozoic'
ts.find_by_age(0.0).name                    # youngest interval
```

### 5.3 Age boundary semantics (`find_by_age`)

1. Normal case: return the interval satisfying `older_ma >= age > younger_ma`;
2. Exact boundary hit: the boundary belongs to the **younger** interval whose
   `older_ma` equals it (66.0 Ma → Paleogene, not Cretaceous);
3. `0.0` Ma: explicitly mapped to the youngest interval;
4. Beyond the oldest boundary of the rank: `IntervalNotFoundError`; no
   extrapolation;
5. Float snapping: inputs within 1e-9 of a boundary are snapped to it first.

### 5.4 Iteration (window **intersection** semantics)

```python
for interval in ts.iter_intervals(ranks=["Period", "Epoch"],
                                  min_age=100.0, max_age=200.0):
    print(interval.name, interval.bounds, interval.color)
```

Returns **all intervals intersecting the window, unclipped** (straddling
intervals are included; drawing clips them), in the deterministic order
`older_ma` descending → rank order (Eon > Era > Period > Epoch > Age) → `id`.
`ranks=None` means all five core ranks.

### 5.5 Interval and per-boundary states

```python
iv = ts.get_interval("ics:period:cretaceous")
iv.name, iv.rank, iv.parent_id, iv.color
iv.older_ma, iv.younger_ma        # boundary values in Ma (older larger)
iv.bounds                         # (older_ma, younger_ma)
old_b, yng_b = iv.boundaries      # Boundary objects
old_b.qualifier        # 'constrained' | 'defined' | 'approximate' | 'present' | 'unknown'
old_b.uncertainty_ma   # quantitative error (± Ma) or None (None ≠ 0!)
old_b.definition       # 'gssp' | 'gssa' | 'numeric_estimate' | 'present' | 'unknown'
old_b.is_defined                  # defined by a GSSP/GSSA?
iv.is_approximate_any()           # any endpoint carries a ~ approximate value
iv.has_defined_boundary           # any endpoint defined by GSSP/GSSA
```

Structural nodes (e.g. `Precambrian`, `Super-Eon`) exist only as `parent_id`
anchors; they never appear in `ts.ranks` and are never drawn.

---

## 6. Linear geological time strips: add_geo_axis()

### 6.1 Full signature

```python
result = add_geo_axis(
    ax,                          # host Axes (positional)
    *,                           # everything below is keyword-only
    spec,                        # CoordinateSpec, required
    position="bottom",           # "bottom" | "top" | "left" | "right"
    ranks=None,                  # None → ("Period",); str or sequence
    timescale=None,              # None → bundled baseline snapshot
    thickness_ratio=0.12,        # track stack thickness as a fraction of the host, (0, 0.5]
    min_age=None,                # drawing window; None → spec.age_range
    max_age=None,
    fill=True,                   # fill with official ICS colours
    alpha=1.0,                   # fill opacity, [0, 1]
    label=True,                  # draw interval name labels
    label_size=6.0,              # label font size (pt)
    label_color="auto",          # "auto" picks black/white from the composited background
    skip=None,                   # interval names to skip
    abbreviate=True,             # allow official short codes when space is tight
    border="both",               # "none" | "near" | "far" | "both"
    border_width=0.5,
    border_color="black",
    rotation=0.0,                # fixed label rotation (degrees)
    tick_style="none",           # "none" | "boundaries" | "ages"
    tick_max_count=10,           # tick-count cap (tick_style="ages" only)
    key=None,                    # track identity for idempotent updates (7.2)
    preserve_axes_state=True,    # promise not to mutate the host view state
)
```

### 6.2 Parameter notes

**`position`** chooses the host edge and **uniquely** determines the time
direction: `bottom`/`top` → time along x; `left`/`right` → time along y.
`spec.time_axis` is validated for consistency: `position="left"` with
`spec.time_axis="x"` raises `CoordinateError` (the message states the correct
pairing).

**`ranks`** supports multi-level tracks. Ordering: **the first rank is nearest
the data region** (the near side). With `ranks=["Period", "Epoch"]` at
`position="bottom"`, Period sits above Epoch. Track thicknesses start from
weights (Eon 0.8 / Era 1.0 / Period 1.2 / Epoch 1.5 / Age 2.0) and are
corrected so every track reaches a minimum thickness of 6 px; if the space
cannot honour the minimum for all tracks, `InvalidRangeError` is raised (the
feasibility pre-check runs before allocation). The 6 px floor is a *runtime*
constant, not a hard-coded literal inside the layout: it is
`geophylo.render.linear.MIN_TRACK_THICKNESS_PX` and the layout function takes it
as its `min_px` argument, so callers with unusual font sizes or figure sizes can
pass a different floor to `compute_track_layout()`. `add_geo_axis()` always uses
the module-level value. Empty sequences, duplicates and illegal ranks
(case-sensitive; `"period"` is not corrected) raise `InvalidRankError`.

**`min_age` / `max_age` (the drawing window)**: intervals intersecting the
window are **clipped** to the window bounds; intervals that straddle a window
edge contribute their visible part (intersection semantics — nothing is
silently dropped). The window must lie inside `spec.age_range`.

**`tick_style` (numeric ticks)**:

- `"none"` (default): colour blocks and labels only;
- `"boundaries"`: ticks at interval boundaries inside the window, deduplicated
  and filtered by pixel distance (when two tick centres are closer than
  `label_size × 2` px the older one is kept). This style is **not** subject to
  `tick_max_count`: dropping a boundary number would make the reader believe no
  boundary exists there, so the count is governed by spacing only. The number of
  candidates that did not survive is reported on `result.ticks_dropped`;
- `"ages"`: additionally fills sparse segments (gaps > 20 % of the window)
  with equidistant ticks, capped by the `tick_max_count` limit
  (priority: rank boundaries > whole-ten/whole-hundred Ma > others; within each
  tier the oldest candidates are kept first). `result.ticks_dropped` counts what
  the cap and the spacing filter removed.

The spacing filter runs twice: once on tick *centres* (`label_size × 2` px) and
once on the *measured text boxes* after edge alignment (see the overflow rules
below), always keeping the older of a colliding pair. A tick label that touches
the window edge is aligned to the inner edge instead of being centred, so it
cannot spill out of the track rectangle; if that aligned box would touch a
neighbouring number, the younger number is dropped rather than fused with it.

Ticks always display Ma values (also in `root_distance` mode, converted back
through the contract) plus a `"Ma"` unit label, which sits *outside* the track at
the oldest end of the window and never overlaps a tick number. Formatting is
deterministic: `0 ≤ age < 1` two decimals; `1 ≤ age < 100` one decimal (integral
values drop the decimal point); `age ≥ 100` integer. Examples: `0.0 → "0.00"`,
`1.0 → "1"`, `66.0 → "66"`, `538.8 → "539"`.

**Label degradation ladder** (applied in a fixed order, no step skipped):
① abbreviate → ② rotate → ③ hide (core ranks and older ages are kept first).
The outcome is reported in `result.labels_shortened / labels_rotated /
labels_hidden`. Two rules bound what abbreviation may do:

- only a *single-segment short code* from the snapshot `aliases` is adopted as a
  figure abbreviation — one or two letters followed by up to two digits, at most
  4 characters (`J`, `P1`, `T3`, `c7`). Composite ICS `ccgmShortCode` values that
  pack a sub-series and a stage together (`C2c6c7`, `C1c1`, `C2c5`) are codes,
  not abbreviations: readers cannot decode them from the chart, so such intervals
  are labelled with their **full name** instead. Abbreviation is skipped
  entirely when the user passes `abbreviate=False`;
- collision detection uses renderer-measured text extents, and both geometric
  constraints are evaluated *at the rotation of each candidate*. The
  thickness dimension is a hard constraint: no label — rotated or not — crosses
  into a neighbouring track band. In the time dimension a label may overflow its
  own interval into empty space *inside the same track rectangle*, and a label
  touching the window edge is clamped so its box stays inside that rectangle.
  Nothing is ever drawn outside the track rectangle; if a label cannot fit even
  after clamping, it is hidden. Edge fragments whose clipped width is below
  `MIN_LABEL_LENGTH_PX` (0.5 px) produce no name label at all.

**`label_color="auto"`** first alpha-composites the block colour onto the track
background, then applies the WCAG relative-luminance contrast rule to choose
black or white — labels stay readable on translucent fills.

### 6.3 The side-effect contract

With `preserve_axes_state=True` (the default), `add_geo_axis()` does **not
modify any host view state**: `get_xlim()/get_ylim()/get_xscale()/get_yscale()/
get_autoscale*_on()/dataLim` are field-for-field identical before and after the
call. The strip lives in an independent Axes created by `host_ax.inset_axes()`
whose data ranges copy the host numerically without sharing them.
`preserve_axes_state=False` is the explicit opt-out that allows host mutations
(`result.restore()` reverts them).

`remove()` honours the same promise in the other direction: it restores the
creation-time snapshot **only while the host view still matches that snapshot**,
i.e. when the restore is an invisible no-op for the user. If the user changed
limits, scales or inverted the axes while the track was alive, `remove()` keeps
those settings and only cleans up the artists this library added — going back to
the creation-time view then requires an explicit `result.restore()`.

---

## 7. The GeoAxisResult lifecycle

### 7.1 Five lifecycle methods

```python
result = add_geo_axis(ax, spec=spec)

result.update(ranks=["Period", "Epoch"], alpha=0.8)  # rebuild in place (returns self)
result.sync()        # re-align after host limits / physical size changes
result.finalize()    # run the precise label layout now and freeze it
result.remove()      # remove all artists, disconnect the callback, release the key
result.restore()     # restore the host Axes state snapshot taken at creation
```

- **`update()`** accepts rendering parameters only (`ranks`, `thickness_ratio`,
  `min_age/max_age`, `fill`, `alpha`, `label`, `label_size`, `label_color`,
  `skip`, `abbreviate`, `border*`, `rotation`, `tick_style`,
  `tick_max_count`). `spec`, `position` and `timescale` are **not** updatable —
  they change the coordinate semantics or the carrying Axes, so passing them
  raises `CoordinateError`. All value-domain checks and a geometry pre-check
  run before anything is committed: a rejected `update()` leaves the previous
  strip (artists and parameters) completely untouched.
- **`sync()`** has two layers: ① re-copy the track's time-dimension data range
  from the host; ② re-run the thickness allocation against the current physical
  size (still honouring the 6 px minimum and exact conservation). When the
  space is insufficient, the last consistent layout is kept and
  `result.sync_degraded` is set to `True`. The `draw_event` callback registered
  by `add_geo_axis()` calls `sync()` automatically whenever it detects host
  limit or figure-size changes, and re-runs the precise label layout until
  `finalize()`.
- **`finalize()`** disables further automatic re-layout (use before `savefig`).
  `remove()` disconnects the callback so nothing leaks.
- **`remove()`** removes the artists this library added, disconnects the
  callback and releases the key. It also reverts the host snapshot, but only
  when the host view is *still* identical to that snapshot; view changes made
  while the track was alive are kept (see §6.3).
- **`restore()`** reverts the host snapshot unconditionally — the explicit way
  back to the creation-time view after the user has zoomed or inverted axes.

### 7.2 The key registry (idempotent updates)

```python
r1 = add_geo_axis(ax, spec=spec, key="main")
r2 = add_geo_axis(ax, spec=spec, key="main", ranks=["Era"])   # in-place update
assert r1 is r2
r1.remove()                                                    # key released
add_geo_axis(ax, spec=spec, key="main")                        # brand-new track

from geophylo import remove_all
remove_all(ax)   # remove every track on this host, returns the count
```

Re-adding the same `key`: different `spec` or `position` raises
`CoordinateError`; otherwise the call is equivalent to `update()`. The registry
is a weak-keyed map per host Axes (garbage-collected with the Axes) and is not
thread-safe, consistent with Matplotlib's single-threaded figure assumption.

---

## 8. Bio.Phylo adapter: spec_from_biophylo()

```python
from geophylo.adapter import spec_from_biophylo

spec = spec_from_biophylo(
    tree,                    # a Bio.Phylo tree object
    ax,                      # the Axes where the tree is (or will be) drawn
    time_axis="x",
    age_conversion=1.0,      # Ma per branch-length unit; or a callable
    root_age=48.0,           # root age from an external time calibration
    allow_unit_depth=False,  # tolerate the unit-depth fallback?
)
```

Key behaviours:

- **Always produces a `mode="root_distance"` contract** — `Phylo.draw()` data
  coordinates are accumulated branch lengths, so only root-distance semantics
  align with the host geometry. Callers needing an absolute-age coordinate
  system should build the `CoordinateSpec` themselves.
- **Branch lengths are fully validated**: missing (`None`), NaN, negative and
  non-finite values raise `CoordinateError` listing the offending nodes. Only
  lengths that are **all missing (None)** constitute Bio.Phylo's unit-depth
  fallback (coordinates are topological depth, not time) — rejected unless
  `allow_unit_depth=True`, in which case a `UserWarning` still notes that the
  conversion carries no chronological meaning. NaN/negative lengths are **data
  errors** and are never tolerated, even with `allow_unit_depth=True`.
- **The root branch length must be 0 or None**: `Phylo.draw()` and
  `tree.distance()` include the root length in path distances, shifting the
  root-distance ↔ age correspondence. A non-zero root length raises
  `CoordinateError` with two explicit remedies (zero it on the tree, or
  subtract it explicitly in downstream distance computations).
- **`age_conversion` is required**: a `float` (linear scale) or
  `callable(bl) -> Ma`. Units such as substitutions/site cannot be converted to
  Ma by assumption — this parameter is a semantic precondition.
- **`age_range` derives from the tree's actual data domain**, not the padded
  view limits (Bio.Phylo pads xlim by roughly 5 %/25 %). If the oldest leaf
  would be younger than 0 Ma, `CoordinateError` is raised.
- **`ax` is used for two things only**: validating a numeric-linear axes
  (log/date/category axes raise `AxesTypeError`) and reading the current data
  range. It is never evidence of time semantics.

---

## 9. Radial time rings (experimental): RadialSpec and add_geo_ring()

> The symbols below are experimental: the API may change, their tests carry the
> `experimental` marker, and `pytest -m "not experimental"` excludes them.

### 9.1 RadialSpec: radius encodes time, angle encodes order

```python
import numpy as np
from geophylo import RadialSpec

radial = RadialSpec(
    age_range=(0.0, 63.0),         # (min_age, max_age)
    radius_range=(0.0, 1.0),       # (r_inner, r_outer): inner radius ↔ max_age (root)
    theta_range=(0.0, 2 * np.pi),  # angular span of the tree (radians, CCW from +x)
    root_age=63.0,                 # required when converting root distances to ages
)

radial.age_to_radius(63.0)   # 0.0 (root at the centre)
radial.age_to_radius(0.0)    # 1.0 (leaves at the rim)
radial.radius_to_age(0.5)    # 31.5 (strictly monotonic linear inverse)
radial.band_radius((0.9, 1.0))             # band → (r_inner, r_outer)
radial.band_radius((0.5, 1.0), unit="data")
```

**Consistency contract (the crux)**: the tree and the ring must be drawn under
the **same** `RadialSpec` instance — every tree node positioned with
`radial.age_to_radius(node_age)`, every band converted by the same instance.
Drawing the tree with its own radii and the ring with another mapping silently
misaligns them and is forbidden.

Natural inputs that cross zero (e.g. 350° → 10°) are unwrapped in `+2π`
multiples; a full circle is accepted within `abs(span − 2π) ≤ 1e-9`.

### 9.2 add_geo_ring()

```python
from geophylo import add_geo_ring

result = add_geo_ring(
    ax,                    # a native Matplotlib polar Axes
    spec=radial,           # RadialSpec
    rank="Period",         # a single rank (experimental limitation; sequences raise InvalidRankError)
    band=(0.9, 1.0),       # radial interval the ring occupies (drives geometry)
    band_unit="radial_fraction",  # or "data" (same units as radius_range)
    min_age=None, max_age=None,   # drawing window; None → spec.age_range
    fill=True, alpha=1.0, label=True, label_size=5.0,
    skip=None, abbreviate=True,
    rotation=0.0,          # fixed label rotation
    rotate_labels=False,   # True: align labels along the radius (rotation added as offset)
    key=None,              # idempotent updates
)
```

Five hard constraints:

1. **A single rank only** (no established layout model exists for multi-rank
   rings);
2. **Native polar Axes only** (Cartesian Axes raise `AxesTypeError`; iplotx's
   radial layout lives on Cartesian Axes and is out of scope);
3. **The radius mapping is shared with the tree**: the age at any ring radius is
   given by
   `spec.radius_to_age(r, radius_range=spec.band_radius(band, band_unit))` — the
   same linear map restricted to a codomain; the implementation never derives a
   second mapping;
4. **`band` takes part in the geometry** (it is not merely validated):
   `spec.age_range` is mapped onto the converted band `(r_inner, r_outer)`, with
   `max_age → r_inner` and `min_age → r_outer`. Every segment therefore lies
   inside the band and has a positive height (a younger boundary gives a larger
   radius). `min_age`/`max_age` only clip *which* intervals are drawn — they
   never rescale the ring, so a radius corresponds to the same age on the ring
   and on the tree. To make ring and tree coincide radially, give the band the
   tree's radius range (`band=(0.0, 1.0)`, or `band_unit="data"` with
   `band=radius_range`);
5. **The radial view is never modified**: `set_rlim()`/`set_rorigin()` are never
   called; a band falling outside the current `rlim` raises
   `InvalidRadiusError` reporting both the current limits and the request.

Return-value mapping: `host_ax` and `geo_ax` are both the polar Axes you
passed; `sync()` only re-validates the band against the current rlim;
`restore()` is a no-op (the ring never touches host state); `remove()` removes
only the ring artists and never deletes the polar Axes you own.

### 9.3 The circular-tree recipe (you draw the tree)

```python
import numpy as np
from io import StringIO
import matplotlib.pyplot as plt
from Bio import Phylo
from geophylo import add_geo_ring
from geophylo.adapter import radial_spec_from_biophylo

tree = Phylo.read(StringIO("((A:41.0, B:41.0):22.0, (C:35.0, D:35.0):28.0);"), "newick")
radial = radial_spec_from_biophylo(
    tree, age_conversion=1.0, root_age=63.0,
    r_inner=0.0, r_outer=1.0, theta_range=(0.0, 2 * np.pi),
)

fig = plt.figure(figsize=(8, 8))
ax = fig.add_subplot(111, projection="polar")

# 1) Draw the tree: leaves share the angular span in order, internal nodes take
#    the mean angle of their children; radii always come from the spec.
leaves = tree.get_terminals()
theta = {id(leaf): radial.theta_range[0]
         + (radial.theta_range[1] - radial.theta_range[0]) * i / len(leaves)
         for i, leaf in enumerate(leaves)}
root_offset = tree.root.branch_length or 0.0
radius = {}
for clade in tree.find_clades(order="postorder"):
    age = radial.root_age - (tree.distance(clade) - root_offset)
    radius[id(clade)] = radial.age_to_radius(age)
    if clade.clades:
        theta[id(clade)] = float(np.mean([theta[id(c)] for c in clade.clades]))
for clade in tree.find_clades():
    for child in clade.clades:
        ax.plot([theta[id(clade)], theta[id(child)]],
                [radius[id(clade)], radius[id(child)]], color="black", lw=0.8)

# 2) Draw the ring: the same RadialSpec instance guarantees point-for-point
#    consistency between the ring's age at a radius and the tree's.
result = add_geo_ring(ax, spec=radial, rank="Period", band=(0.92, 1.0))
fig.savefig("circular_tree.png", dpi=300)
```

`radial_spec_from_biophylo()` shares the linear side's branch-length validation
(unit-depth fallback and non-zero root lengths included); `r_inner`/`r_outer`
are your drawing decision for how much room the tree gets and must be given
explicitly.

---

## 10. iplotx adapter (experimental)

```python
import iplotx as ipx
from geophylo import spec_from_iplotx, add_geo_axis

artist = ipx.tree(tree, layout="horizontal")   # tree: ete4/Biopython/DendroPy
spec = spec_from_iplotx(artist, time_axis="x", age_conversion=1.0, root_age=48.0)
add_geo_axis(artist.axes, spec=spec, position="bottom")
```

- Layout data are read through `artist.get_layout()`; `age_conversion` is
  applied to the layout root distances (branch-length units → Ma).
- Always produces `mode="root_distance"`; use `time_axis="y"` for
  `layout="vertical"`.
- **Radial layouts are rejected explicitly** (`AxesTypeError`): iplotx radial
  draws on Cartesian Axes, which has no defined correspondence with a polar
  `rlim`; draw circular trees with the recipe in section 9.3 instead.

---

## 11. The pyrolite backend (experimental)

```python
from geophylo import Timescale

ts = Timescale(backend="pyrolite")   # requires pip install "geophylo[pyrolite]"
ts.find_by_name("Ectasian")
```

- A read-only wrapper around the public table of
  `pyrolite.util.time.Timescale`; never goes online, never silently updates.
- Version-locked to `pyrolite>=0.3.7` (anchored to the 2024/12 data and the
  Supereon level).
- Limited capabilities: no stable IDs (`get_interval()` always raises
  `IntervalNotFoundError`), no parent relations (`parent=` unsupported), no
  GSSP/uncertainty metadata (reported as `unknown`, never fabricated).
- Query semantics are **shared with the bundled backend by construction** — both
  answer from `geophylo.data._query`: structural rows (`Supereon`, `Subepoch`,
  the Carboniferous `Sub-Period`s) never become a `find_by_age()` hit; a
  boundary value belongs to the younger interval (left-closed, right-open);
  `0.0 Ma` maps to the youngest interval; when several ranks match, the most
  specific one wins; `iter_intervals(ranks=None)` means the five core ranks (not
  every row) and the window carries the same `1e-9` tolerance; `find_by_name()`
  walks the `name → aliases → label` channels with exact matches taking priority.
  These were measured against `pyrolite 0.3.7`, not inferred from the source.
- The bundled snapshots remain the default and recommended source
  ([ADR-1](adr/ADR-1-bundled-snapshots-over-pyrolite.md)); the pyrolite backend
  exists for cross-checking.
- Rows that carry no colour upstream are drawn with the neutral placeholder
  `#CCCCCC` and reported once by a `UserWarning` at construction time; a missing
  value is never presented as a credible ICS colour.

---

## 12. Exceptions and troubleshooting

All public exceptions inherit from `geophylo.GeophyloError`. Messages contain
the failing parameter, its actual value, and a fix suggestion.

| Exception | Typical trigger | What to do |
| --- | --- | --- |
| `DataValidationError` | snapshot schema/hash/shared-boundary failure; unpublished version requested | check `available_versions()`; validate custom JSON against the bundled schema; never hand-edit snapshots |
| `InvalidRankError` | rank typo, empty/duplicate `ranks`, a sequence passed to `add_geo_ring` | core ranks are `Eon/Era/Period/Epoch/Age`, case-sensitive |
| `IntervalNotFoundError` | ID/name/age not found; no interval of that rank at that age | names go to `find_by_name()`; ages beyond the snapshot are refused by design |
| `AmbiguousIntervalError` | a name matches several candidates (e.g. `"Upper"`) | add `rank=` or `parent=`, or pick an ID from `exc.candidates` |

**Catch order matters**: `AmbiguousIntervalError` is a *subclass* of
`IntervalNotFoundError` (kept for backwards compatibility with code that only
catches "not found"), so `except IntervalNotFoundError` also swallows "matched
several". Put the `except AmbiguousIntervalError` clause **first** whenever the
two cases call for different handling.

| `InvalidRangeError` | `min_age >= max_age`, negative ages, NaN, `thickness_ratio` out of range, `tick_max_count < 1`, insufficient track space | follow the legal domain stated in the message |
| `InvalidRadiusError` | inverted/out-of-range `band`; band outside the current `rlim` | adjust `band`, or widen the view with `ax.set_rlim()` first |
| `AxesTypeError` | log/date/category axes; non-polar Axes passed to `add_geo_ring`; iplotx radial layout | use linear numeric axes / a native polar axes |
| `CoordinateError` | `position` vs `spec.time_axis` conflict; `root_age` missing or forbidden; unacknowledged inference; out-of-domain `age_to_data` | fix the `CoordinateSpec` or the parameter pairing as suggested |

**General checklist**:

1. `CoordinateError: position ... spec.time_axis ...` → pair `bottom/top` with
   `"x"` and `left/right` with `"y"`;
2. Strip looks empty → check that the window `min_age/max_age` intersects your
   data range; axis inversion is legal and only changes direction;
3. `InvalidRangeError: thickness_ratio ...` → fewer ranks, a larger
   `thickness_ratio`, or a bigger figure;
4. Too many hidden labels → more space (`thickness_ratio`), manual `skip=`,
   or split across two tracks;
5. Tree and strip misaligned → make sure the strip uses the `spec` produced by
   `spec_from_biophylo()` (root-distance semantics) and that the root
   `branch_length` has been zeroed.

---

## 13. FAQ

**Q1: Can `add_geo_axis()` move my data points or change the axis limits?**
No. The strip lives on an inset Axes; the host's limits, scale, autoscale flags
and `dataLim` are unchanged field-for-field (asserted by tests). This is also
why the library does not reserve external space for you — use
`constrained_layout` or subplots when you want an outside strip.

**Q2: Why can't I just pass `position="bottom"` and let the library figure out
the semantics?**
Because the same axis can carry two different scientific meanings (Ma vs.
root distance), and guessing wrong is a scientific error. The library requires
an explicit `spec`; even inference must pass through
`CoordinateSpec.from_data_limits(..., acknowledge_inference=True)`.

**Q3: Does `invert_xaxis()` need special handling?**
No. `age_to_data()` is a pure function; inversion only affects the display
direction, never the patch data coordinates. That is why all eight rows of the
truth table (4.4) share one implementation.

**Q4: What is the difference between `age_range` and `min_age/max_age`?**
`age_range` is the declared semantic range (the conversion domain);
`min_age/max_age` are the clipping window of one draw. To draw only 0–66 Ma
while the host covers more: keep `spec.age_range` matched to the axis and pass
`min_age=0, max_age=66`.

**Q5: Does the timescale data update itself?**
Never. Snapshots ship with the package and are append-only; new ICS data
arrives as a **new snapshot version** selected explicitly with
`Timescale(version=...)`. That is what keeps every figure reproducible years
later.

**Q6: Can I stack several strips?**
Yes. `ranks=["Period", "Epoch"]` draws two tracks at once; or combine
different `position` values (e.g. one strip at the bottom, one at the left).
Repeated calls with the same `key` update in place instead of stacking.

**Q7: Can I recolour or rotate the labels?**
`label_color="auto"` (default) picks black/white from the composited
background; any colour name or hex value works too. `rotation` sets a fixed
angle; vertical tracks automatically add a 90° base rotation.

**Q8: Why do I have to draw the circular tree myself?**
The angle encodes taxon order — a tree-layout responsibility the library does
not infer. The recipe in 9.3 is about 30 lines and guarantees the ring shares
the tree's radius mapping.

**Q9: Are the iplotx adapter and the ring features stable?**
They are experimental symbols (the `experimental` marker): fully tested but not
API-frozen. `spec_from_biophylo()` + `add_geo_axis()` belongs to the stable API.

**Q10: How do I reproduce the example figures?**
See `examples/` in the repository: every boundary value and colour is read from
the bundled snapshot — nothing is hand-written — so re-running a script with its
own output path and `dpi` reproduces the same figure.

**Q11: Why is the base of the Cretaceous 143.1 Ma (and the top of the Berriasian
137.05 Ma) rather than the widely quoted GTS2012 values 145.0 and 139.8?**
The two values in this snapshot come from the **GTS2020 time calibration**
carried by the ICS chart version they were built from (`rdfs:isDefinedBy
ts:gts2020` on the corresponding boundary node in the pinned upstream TTL); they
are not transcription errors. 145.0 / 139.8 are GTS2012 calibrations and should
not be mixed with them. When a figure is read against an older table, state the
source in the caption: every number GeoPhylo draws comes from the bundled
snapshot's `chart_version` (check it with `Timescale().metadata.data_version`).

**Q12: Why does the snapshot stop at 4567 Ma instead of the 4600 that many
time scales start from?**
The Hadean / Precambrian older boundary is 4567.0 Ma upstream (the pinned TTL
describes it as `A time period from 4567 to 4031 million years ago`), and
GeoPhylo never edits upstream values. If your axis should start at 4600, declare
it explicitly: `CoordinateSpec.absolute(time_axis="x", age_range=(0.0, 4600.0))`
with `max_age=4600.0`. The interval between 4567 and 4600 then stays empty — a
direct consequence of never fabricating a unit the source does not give; say so
in the caption.

**Q13: The Carboniferous Mississippian / Pennsylvanian are classified as
`structural` — how do I draw that two-fold division?**
The ICS chart carries them at the `Sub-Period` level, which ADR-5 classifies as
structural: they never enter `Timescale.ranks`, nor the default pools of
`find_by_age()` / `iter_intervals()`, and `ranks=["Sub-Period"]` raises
`InvalidRankError`. What you *can* draw is the level the snapshot really
carries: the six Epoch rows Lower / Middle / Upper Mississippian (358.86 to
323.4 Ma) and Lower / Middle / Upper Pennsylvanian (323.4 to 298.9 Ma). For
instance, add an Epoch track over the Carboniferous window:

```python
add_geo_axis(ax, spec=spec, position="bottom", ranks=["Period", "Epoch"],
             min_age=298.9, max_age=358.86)
```

The Epoch track gives the Mississippian / Pennsylvanian division and its
subdivisions (their figure abbreviations fall back to full names, because their
aliases are composite `ccgmShortCode` values — see §6.2).
`find_by_name("Mississippian")` raises `AmbiguousIntervalError` by design (three
Epoch candidates); disambiguate with `rank=` / `parent=` or use an ID such as
`ics:epoch:lower-mississippian`.

**Q14: The `"Ma"` unit label sits outside the coloured strip — is that a
placement bug?**
No, it is the documented anchor: the label is pinned to the **older end of the
window** and offset away from the track by a gap measured in display pixels
(`_draw_unit_label()` in `geophylo/render/linear.py`), so it can never collide
with the oldest tick numeral. Where that lands in figure space depends on your
host axis: if the host has padding beyond the window's older end (the usual
`ax.set_xlim(0, 300)` with matplotlib's default 5% margin), the label appears
inside the track footprint, near its edge; if the window's older end *is* the
track edge (`ax.set_xlim(300, 0)` with no margin), the label sits just outside
the track, in the figure margin, with `clip_on=False`. It is never clipped by
the track. To put it elsewhere, label the axis yourself: read the older-end age
from the snapshot and write the unit text on your axis.

---

## 14. Example scripts

| Script | Content |
| --- | --- |
| `examples/bio_phylo_timetree.py` | Bio.Phylo timetree + Period/Epoch strips (primary use case) |
| `examples/stratigraphic_column.py` | tree-free usage, stratigraphic-column style (`CoordinateSpec.absolute`) |
| `examples/circular_tree.py` | circular-tree recipe + polar time ring (experimental) |
| `examples/iplotx_timetree.py` | iplotx `TreeArtist` adapter (experimental, needs `geophylo[iplotx]`) |

Run any example:

```bash
python examples/bio_phylo_timetree.py
```

All examples follow the `add_geo_axis() → tight_layout() → finalize() →
savefig()` order and run headless on Agg (PNG output next to the script).

---

## 15. Data provenance, licence and citation

- **Code**: MIT (see `LICENSE`).
- **ICS snapshot data**: generated deterministically from the official
  versioned ICS data by `tools/build_snapshot.py`, released CC-BY-4.0 (see
  `LICENSES/CC-BY-4.0.txt` and `NOTICE`). Provenance, update and rollback
  policies: `docs/data-policy.md`.
- **Machine-readable provenance**: per-snapshot generation logs in
  `tools/build-logs/`, the cross-version field-level diff
  `geophylo/data/snapshots/diff-2024-12_to_2026-06.json` (generated by
  `tools/make_diff.py`, or by `build_snapshot.py --diff-with`), and the
  `derived_from` entry of the 2024/12 record in `versions.json`, explained in
  `geophylo/data/snapshots/PROVENANCE.md`.
- **Design rationale**: the architecture decision records in [`docs/adr/`](adr/README.md)
  (ADR-1 … ADR-5) document the non-obvious choices and their rejected
  alternatives.
- **Citation**: if you use GeoPhylo in research, cite it (`CITATION.cff`) and
  cite the ICS International Chronostratigraphic Chart as requested in
  `NOTICE`.

Terminology used consistently in this guide: `older_ma`/`younger_ma` are the
Ma values of an interval's older/younger boundaries (`older_ma > younger_ma`);
a *track* is the inset Axes carrying one rank's colour band; the *drawing
window* is the `min_age`/`max_age` clipping range.

---

*This guide is maintained alongside the code; where it conflicts with the
normative entries referenced by the source comments, the index at
[`docs/spec/README.md`](spec/README.md) and the code in this repository
prevail. There is no design document outside the repository to consult.*

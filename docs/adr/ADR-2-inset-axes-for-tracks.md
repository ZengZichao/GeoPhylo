# ADR-2: Draw tracks on inset Axes rather than overlaying artists on the host Axes

- **Status**: Accepted (in force since 0.1.0)
- **Date of record**: 2026-09-11
- **Code**: `geophylo/render/linear.py` (`_make_track_axes`,
  `_align_track_to_host`), `geophylo/render/polar.py`,
  `geophylo/render/result.py` (`AxesState`), `tests/test_visual.py`,
  `tests/test_add_geo_axis.py`

## Context

A geological time strip has to sit flush against a host panel and share its
time dimension, but the host panel belongs to the user: it may be a tree, a
stratigraphic column, or a scatter plot, and its limits, scale, autoscale flags
and `dataLim` are load-bearing for whatever else is drawn there. Two ways to
attach a strip exist in Matplotlib:

1. Add `Rectangle`/`Text` artists directly to the host `Axes`, using the host's
   data coordinates.
2. Create a child (inset) `Axes` positioned by the host's axes fraction and let
   it own the strip's artists.

Option (1) is what a hand-drawn strip does, and it is what the wrapper has to
prove it does *not* do: `Rectangle` patches added to a host `Axes` extend
`dataLim`, so drawing a strip from 0 to 541 Ma would silently rescale a panel
that only spanned 0 to 66 Ma. Option (2) additionally gives each track its own
independent second dimension (a thickness axis in `[0, 1]`), which a flat
overlay cannot express.

## Decision

Every track is rendered in an inset `Axes` created by
`host_ax.inset_axes(bounds)`; the overlay route is not implemented at all.

- `bounds` are given in host axes-fraction coordinates. As of Matplotlib ≥ 3.10
  `inset_axes` already uses `transAxes`, so the transform is deliberately *not*
  passed again (doing so double-converts).
- `thickness_ratio` is a fraction of the *host* box, so track geometry follows
  the host as the figure is resized, while staying in physical pixels for the
  layout maths (`MIN_TRACK_THICKNESS_PX`, label fitting).
- The track's time-range is **copied numerically** from the host
  (`set_xlim(host.get_xlim())`) and *not* shared via `sharex`, so a later host
  autoscale cannot drag the track along; the perpendicular range is pinned to
  `[0, 1]`. Because the numbers are copied, `spec.age_to_data()` output can be
  used directly as track data coordinates with no second transform.
- The host's view state is snapshotted in `AxesState` (limits, both scales, both
  autoscale flags, frozen `dataLim`) before anything is drawn and restored on
  `remove()`/`restore()`; `AxesState.matches()` is the assertion the tests use.
- The inset strategy is specific to the linear tracks. Polar rings deliberately
  do **not** get an inset: `add_geo_ring()` draws into the caller's own polar
  `Axes` (`geophylo/render/polar.py`, `owns_axes=False`), because the ring's
  radii are defined against the radial view the user already set on that Axes;
  the result object therefore owns no axes of its own and `remove()` leaves the
  host's view state untouched.

## Rejected alternatives

- **Overlay patches on the host `Axes`.** Rejected: pollutes `dataLim` and the
  host's artist list, cannot express a thickness dimension, and makes the
  "leaves the host untouched" contract unprovable.
- **`sharex`/`sharey` between host and track.** Rejected: sharing is
  bidirectional at autoscale time, so a later host rescale would silently
  rewrite the track's range and break the recorded `CoordinateSpec`. Numeric
  copying plus an explicit `sync()` keeps the direction of control one-way.
- **A `axes.dividers`/`aux_axes` style layout object.** Rejected: not available
  in the supported Matplotlib range (≥ 3.10, < 4) as a stable API, and it
  re-enters the same `dataLim` problem for the artists.
- **Asking the user to reserve space manually** (e.g. pre-shrinking the host).
  Rejected: `tight_layout` and `finalize()` ordering would then be a user
  burden; the inset plus `pad` keeps the geometry a library responsibility.

## Consequences

- The strip is a real `Axes` (`result.geo_ax`), so users can style it directly
  (spines, ticks, zorder) without reaching into the host.
- Every drawn artist is addressable and removable as a set, which is what makes
  `remove()` exact and idempotent.
- Track geometry must be recomputed whenever the host changes, hence the
  `draw_event` callback, `sync()`, and the `finalize()` step that freezes
  precise label layout before `savefig`.
- Pixel-based layout means output geometry depends on `dpi`; the shipped
  examples therefore fix `dpi` explicitly.
- The host-untouched property is a *tested* contract, not documentation: the
  visual and lifecycle tests compare `AxesState` field by field.

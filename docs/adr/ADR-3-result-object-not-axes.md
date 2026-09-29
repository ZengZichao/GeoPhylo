# ADR-3: Return a `GeoAxisResult` object instead of the host `Axes`

- **Status**: Accepted (in force since 0.1.0)
- **Date of record**: 2026-09-11
- **Code**: `geophylo/render/result.py`, `geophylo/render/linear.py`
  (`add_geo_axis`), `geophylo/render/polar.py` (`add_geo_ring`),
  `tests/test_lifecycle.py`

## Context

`add_geo_axis()` has to hand something back. Returning the host `Axes` — the
convention many Matplotlib helpers borrow from `plt.plot` — is attractive
because it "enables chaining", but here it is actively misleading: the object
the call created is *not* the host, the host was deliberately left unmodified
(ADR-2), and the strip needs a lifecycle (re-layout on host change, explicit
freezing before `savefig`, teardown). A plain `Axes` return would also leave the
created track undiscoverable once the function exits, because callers have no
way to know which child axes was added.

## Decision

Return a dedicated result object, `GeoAxisResult`, as the single entry point to
the track's axes, artists and lifecycle.

- Attributes expose state: `host_ax`, `geo_ax`, `artists`, `spec`, `position`,
  `key`, `params`, plus the layout diagnostics
  `labels_shortened`, `labels_rotated`, `labels_hidden`, `sync_degraded`.
- Methods manage lifecycle: `update(**params)`, `sync()`, `relayout()`,
  `finalize()`, `remove()`, `restore()`, `attach_draw_callback()`.
- The call is explicitly **not** chainable (`add_geo_axis(...).plot(...)` is not
  a thing); `update()` returns the same result object so parameter edits can be
  repeated, and `add_geo_axis(...)` returns the object itself.
- `finalize()` must be called after `tight_layout()`/`fig.canvas.draw()` and
  before `savefig()`; it runs the precise label layout once and freezes it. The
  shipped examples follow
  `add_geo_axis() → tight_layout() → finalize() → savefig()`.
- Each result registers itself in a per-host weak-reference table keyed by the
  optional `key` argument (`register_track`, `lookup_track`, `release_track`,
  `remove_all`), so tracks are findable and idempotently replaceable without
  returning the host.

## Rejected alternatives

- **Return the host `Axes`.** Rejected: the host was not modified, so returning
  it implies the wrong thing; and the created track plus its degradation
  diagnostics would be unreachable.
- **Return the track `Axes` only.** Rejected: callers could style it but not
  re-layout, freeze, or remove it, and nothing would carry the host↔track
  pairing that `sync()` needs.
- **Return a `tuple[GeoAxis, list[Artist]]` (the `axhline`-style answer).**
  Rejected: no place for parameters, diagnostics or lifecycle; the second call
  would have no way to know what the first one did.
- **Return `None` and require `lookup_track(ax, key)`.** Rejected: makes the
  common case awkward and hides the degradation statistics that figures and
  tests must assert on.
- **Make every method return `self` for fluent chaining.** Rejected: chaining
  across a `finalize()`-before-`savefig()` boundary hides the ordering
  requirement the contract depends on; only `update()` returns the object.

## Consequences

- The documented call order is a real requirement, and misuse shows up as a
  visibly unfrozen layout rather than an exception; the user guide states the
  order in every example.
- The object is the only place layout degradation is reported, which is what
  makes the ≤ 20 % hidden-label acceptance criterion machine-checkable.
- Holding references to a host `Axes` requires care with figure teardown, hence
  the weak-reference registry and `remove_all()`.
- Tests assert against the object rather than against pixels for lifecycle
  behaviour, which keeps the side-effect contract (`AxesState.matches`) cheap to
  verify.

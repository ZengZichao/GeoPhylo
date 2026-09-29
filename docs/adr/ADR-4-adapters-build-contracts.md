# ADR-4: Adapters build and validate coordinate contracts; they do not draw

- **Status**: Accepted (in force since 0.1.0; iplotx and radial entries
  are experimental)
- **Date of record**: 2026-09-11
- **Code**: `geophylo/adapter/biopython.py`, `geophylo/adapter/iplotx.py`,
  `geophylo/coordinate/spec.py`, `geophylo/coordinate/radial.py`,
  `tests/test_adapter_biopython.py`, `tests/test_adapter_iplotx_contract.py`

## Context

The point of the library is that a timetree axis says what it means: either
absolute age, or distance from the root (see the truth table in the user
guide §4). Tree libraries encode that geometry implicitly — `Bio.Phylo`'s
`Phylo.draw()` plots cumulative branch length, `iplotx`'s horizontal layout does
the same through `get_layout()` — and nothing in those libraries knows about
`CoordinateSpec`. The question is where the translation lives and what an
adapter is allowed to do.

## Decision

An adapter's job is to **construct and validate a coordinate contract**, never
to draw.

- `spec_from_biophylo(tree, ax, *, time_axis, age_conversion, root_age)` returns
  a `CoordinateSpec`; it draws nothing and adds no artists. Rendering stays
  behind `add_geo_axis(spec=...)`, so the same rendering path serves bundled
  snapshots, offline JSON and adapters alike.
- It always produces `mode="root_distance"`. `Phylo.draw()`'s data coordinates
  *are* cumulative distance from the root, so `absolute_age` in that frame would
  silently misplace every interval; rather than offer a mode that can be wrong,
  the adapter does not offer it.
- It validates the tree before deriving anything: the root's `branch_length`
  must be `None` or exactly zero (a non-zero root branch length shifts the whole
  root-distance↔age mapping, and `tree.distance()` counts it), every branch
  length must be present, numeric, finite and non-negative — collected and
  reported together as one `CoordinateError` — and `age_conversion` must declare
  how branch lengths map to Ma so the mode choice is a stated fact rather than a
  guess.
- `spec_from_iplotx()` mirrors the same rules and reads the layout through
  `artist.get_layout()`; it accepts no `Axes` at all because an `Axes` carries
  no tree-coordinate information. It rejects radial layouts explicitly, and
  `radial_spec_from_biophylo()` covers the radial case as a separate entry
  point.
- Non-ultrametric trees are supported deliberately: leaves at fossil
  first/last appearances are the normal case for this figure type, so the
  adapter validates units and reachability rather than requiring equal
  root-to-leaf distances.

## Rejected alternatives

- **`add_geo_axis_to_tree(tree, ax, ...)` convenience drawing.** Rejected:
  it would fuse two contracts (tree layout freedom, strip lifecycle) and
  hide the mode decision the library exists to expose. No `adapter →
  render` drawing edge exists: adapters build contracts, and the caller
  always writes the drawing step.
- **Infer `absolute_age` vs `root_distance` from the axes limits.** Rejected:
  both modes can produce the same numeric range; inference would be a guess, and
  the library's rule is that ambiguous coordinate semantics raise
  `CoordinateError` instead of guessing. `CoordinateSpec.from_data_limits()` is
  the only inference entry point and demands `acknowledge_inference=True`.
- **Let the adapter accept an already-drawn `Axes` and read the artists back.**
  Rejected: Matplotlib does not preserve tree topology in artist coordinates, so
  the recovery would be lossy and unverifiable — hence `spec_from_iplotx()`
  refuses an `Axes` and reads the layout object instead.
- **One generic adapter taking any tree object duck-typed on `.root`**.
  Rejected: the two supported libraries differ exactly where correctness matters
  (ultrametricity assumptions, layout ownership, radial support), so a single
  signature would have to branch on both anyway.

## Consequences

- Adapters are pure functions of their inputs, testable without a figure: the
  contract tests assert the produced `mode`, `age_range` and `root_age`, and the
  iplotx path is tested through a fake `TreeArtist`.
- Users always write the drawing step themselves, so tree-drawing libraries
  remain replaceable (`Bio.Phylo`, `iplotx`, hand-rolled).
- Optional dependencies stay optional: importing `geophylo` never imports
  `Bio`/`iplotx`; an adapter raises `ImportError` with the extra to install.
- Third-party failures must not leak as raw `TypeError`/`ValueError`: the
  adapters convert them into `CoordinateError` with the cause chain preserved
  (see the error-handling contract in `geophylo/exceptions.py`).
- Because there is no absolute-age adapter path, an absolute-age timetree axis
  must be built explicitly with `CoordinateSpec.absolute(...)`.

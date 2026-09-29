# Contributing to geophylo

English | [中文](CONTRIBUTING.zh-CN.md)

## Development environment

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

## Quality gates (release-blocking checks)

- `pytest -m "not performance" -v --mpl --mpl-baseline-path=tests/baseline_images`:
  the blocking gate command (authoritative definition in the comment at the top
  of `.github/workflows/ci.yml`). Unit, data-contract, integration, lifecycle,
  visual-baseline and packaging tests must all pass; tests for experimental
  symbols are inside the gate too.
- `pytest -m "not experimental and not performance"`: slice by stability —
  stable APIs only — to rule out interference unrelated to experimental symbols.
- `pytest -m performance`: the library's incremental cost must not grow
  significantly with the leaf count. It is a separate job because it times
  three tiers (100 / 1,000 / 10,000 leaves; the 10,000-leaf tier measures only
  the library's incremental time and does not redraw the host tree), and its
  timing assertion is sensitive to shared-runner noise, so it must not block
  the release gate. The criteria and the signal-to-noise rule are documented in
  the `tests/test_performance.py` module docstring.
- `pytest tests/test_architecture.py`: the package import graph must be
  **acyclic**, every edge must point to a lower layer, and sibling layers
  (data/coordinate, render/adapter) must not depend on each other. This guards
  the architectural premise of "reason about change impact layer by layer";
  `ruff`'s `I` rules only order imports and know nothing about direction, so
  the assertion has to be explicit. When adding a module, extend the
  `MODULE_LAYER` table in `tests/test_architecture.py` at the same time —
  otherwise the test fails with "no layer assignment".
- `ruff check geophylo tests tools examples`,
  `ruff format --check geophylo tests tools examples`, `mypy`: zero warnings.
  The scope is verbatim identical to the Lint/Type check steps of
  `.github/workflows/ci.yml`; before committing, run ruff format once locally
  over the same scope (without --check).
- Examples are actually executed in CI, not merely syntax-checked.

## The contract triangle

The public API contract (`docs/spec/README.md`, section 4), the test cases
(section 7) and the implementation notes (section 5) form a triangle of
cross-references. Whenever you change one of the three, re-check the other two
in the same change.

## Snapshots and data

- Released snapshots are **append-only**; the update procedure is described in
  `docs/data-policy.md`.
- A snapshot update must update the sentinel assertions at the same time and
  list the data change separately in the CHANGELOG.
- Boundary values in user-facing documents (README, docs/, examples/) must come
  from the snapshots and are verified by the documentation-value tests — never
  transcribed by hand.

## Commits

- Use conventional commits: `feat:`, `fix:`, `data:`, `docs:` and `test:`.
- Visual baseline images must pass code review before they are overwritten by
  hand.

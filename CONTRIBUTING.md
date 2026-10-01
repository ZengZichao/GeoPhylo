# Contributing to GeoPhylo

English | [中文](CONTRIBUTING.zh-CN.md)

## Development environment

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

### Local pre-commit hooks (optional but recommended)

`.pre-commit-config.yaml` mirrors the lint gate described below. It is not
required to contribute - CI is authoritative - but it is the same set of
checks, so a hook failure is a real failure rather than a local-environment
artefact.

```bash
pip install pre-commit
pre-commit install            # once; then it runs on every commit
pre-commit run --all-files    # run over the whole tree
```

The hooks deliberately run the same commands in check-only mode (no `--fix`),
so "already clean" and "cleaned just now" stay distinguishable. If a hook and
CI disagree, CI wins and the configuration is what needs fixing.

Note that the dev extra pins the lint tools with upper bounds (ruff>=0.6,<1
and mypy>=1.11,<2). The pins exist because the gate runs the formatter in
check mode plus a zero-warning type check: without them, a formatter release
can turn the gate red for reasons that have nothing to do with your change,
and local and CI can resolve to different tool versions. Raise a bound
deliberately, after running the gate locally with the new version.

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

## Visual baselines

- `tests/baseline_images/` is generated with the current dependency stack
  (`python3 tests/update_baselines.py`) and is what every blocking gate compares
  against.
- `tests/baseline_images_min/` holds the same two figures rendered under the
  **minimum** dependency stack (oldest Python, `matplotlib==3.10.*`,
  `numpy==1.25.*`); the core-min CI job copies them over `tests/baseline_images/`
  before running the gate, because the 3.10 Agg output differs from the current
  one at the antialiasing level and the tolerance is zero. Regenerate them in a
  minimum-deps environment the same way:
  `MPLBACKEND=Agg pytest tests/test_visual.py --mpl --mpl-baseline-path=tests/baseline_images --mpl-results-path=<dir>`,
  then copy `<dir>/*/result.png` into `tests/baseline_images_min/` (pytest-mpl's
  `--mpl-generate-path` output does not match its compare pipeline under
  matplotlib 3.10).
- Visual baseline images must pass code review before they are overwritten by
  hand.

## Commits

- Use conventional commits: `feat:`, `fix:`, `data:`, `docs:` and `test:`.

## Upgrading GitHub Actions to a new major version

`.github/dependabot.yml` blocks `version-update:semver-major` for the
`github-actions` ecosystem. That block is a **delay, not a veto**: it keeps an
unreviewed runtime swap out of the default branch, and it also means no
Dependabot PR will ever remind you that a major landed. Someone has to move
the pin by hand, or the repository silently sits on a runtime that eventually
gets retired.

Currently pinned by hand:

| Action | Pinned | Latest checked |
| ------ | ------ | -------------- |
| `actions/checkout` | v7 | 2026-07-20 |
| `actions/setup-python` | v7 | 2026-07-20 |
| `github/codeql-action` | v4 | 2026-09-22 |

Procedure for a new major:

1. Confirm the tag exists and read its release notes:
   `gh api repos/OWNER/ACTION/releases/latest`.
2. Check the new major's runner requirement (Node runtime, runner image)
   against what the workflows use.
3. Open a pull request bumping every `uses:` in `.github/workflows/*.yml`.
4. Wait for a fully green CI before merging. Do not relax the `ignore` block
   as a shortcut - if the major genuinely cannot be adopted yet, say so in a
   comment on the block so the next person knows it was considered.

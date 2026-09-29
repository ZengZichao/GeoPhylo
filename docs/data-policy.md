# Data policy: provenance, licensing, snapshot updates and rollback

English | [中文](data-policy.zh.md)

This document describes the data provenance, generation method, licensing
compliance and update procedure of the ICS snapshots bundled with `geophylo`
(see the [specification index](spec/README.md), sections 5.7 and 8.4).

## Provenance

- The bundled snapshots are generated directly from the ICS official versioned
  data, **not copied a second time from `pyrolite`**.
- Pinned source (both snapshots share the same pinned input):
  - Repository: `i-c-stratigraphy/chart`
  - Tag: `v2026-06.5` (the official `2026-06` chart release)
  - Commit: `44d1043ecf295cce1be03b3fc5fa95ca65fe770b`
  - File: `chart.ttl`
  - Upstream file SHA-256:
    `0158959e8fdae2a8bdbb14ca3e424d2370362cd8dfc8af86e7be73c74368b355`
  - Vendored copy: `tools/source/ics-chart-v2026-06.5.ttl`
- "Pinned input" is not a prose claim but a machine-checkable triple assertion:
  the top-level `pinned_input.{file,sha256,bytes}` of `versions.json` == the
  SHA-256 of the copy archived in the repository == the `source.source_sha256`
  of both snapshots == the result of comparing `--source-sha256` against the
  bytes actually read at build time. Any mismatch rejects the output outright.
- The guard code lives in `tools/build_snapshot.py::rebuild_index` and
  `tests/test_snapshot_provenance.py`; the latter includes tamper-must-fail
  cases.
- Mapping between chart versions and snapshot files (each chart layout publishes
  exactly one revision):
  - `2026/06` (baseline snapshot, marked in `versions.json`) →
    `ics_chart-2026-06.json` (`snapshot_revision` 1)
  - `2024/12` → `ics_chart-2024-12.json` (`snapshot_revision` 1)

Wording note: `2026/06` is this project's **baseline snapshot**, not "the
current version". ICS keeps publishing new chart editions; no snapshot is the
current version.

The citation year and the chart edition are two different things; in this
repository they are recorded separately and must not be conflated:

- Citation year: **2025** (Cohen, K. M., Harper, D. A. T., Gibbard, P. L. & Car,
  N. (2025, updated). *The ICS International Chronostratigraphic Chart this
  decade.*). The `license.citation` of both snapshots, `NOTICE`, and the dataset
  reference entry of `CITATION.cff` all use 2025.
- Chart edition: **2026/06** (upstream tag `v2026-06.5`), recorded in the
  snapshots' `chart_version`, in `versions.json`, and in the `edition` field of
  the dataset reference in `CITATION.cff`.

## Deterministic generation

`tools/build_snapshot.py` generates snapshots under the contracts of the
[specification index](spec/README.md), sections 5.6 and 5.7:

- The same input file produces byte-identical JSON. Generation does not read the
  current time — neither `datetime` nor `time` is imported. `retrieved-at` must
  be passed explicitly and is written only to the generation log, never into the
  snapshot itself.
- `hash.payload_sha256` is defined as the SHA-256 of the canonical JSON
  serialisation of the `intervals` array (sorted keys, compact separators,
  UTF-8). `versions.json` is the single version index. The top-level
  `schema_version` of `versions.json` (currently 2) is the **index format**
  version and is not the same counter as the per-snapshot top-level
  `schema_version` (currently 1, the **record structure** version); each evolves
  with its own format.
- `hash.provenance_sha256` covers all top-level metadata **except `intervals`
  and `hash`**: `chart_version`, `snapshot_revision`, `source`, `license`,
  `derivation` and `derived_from`. The two hashes split the disclosure between
  them: `payload_sha256` protects the scientific values, `provenance_sha256`
  protects the version labels and the provenance block itself, so rewriting
  metadata alone also leaves a hash trace. `rebuild_index()` recomputes and
  asserts both hashes.
- The generation log records: the full command line (`command`), `--chart-version`,
  `--to`, `--tag`, `--commit`, `--source-sha256`, fetch time, upstream statement
  counts (`parse_stats`), the boundary rollback list, the repair list
  (`integrity_repairs`), the name-derivation list, the alias-deduplication list,
  the qualifier distribution and warnings.
- Generation-log naming convention: `tools/build-logs/<snapshot-name>.log.json`,
  i.e. `ics_chart-2026-06.log.json` and `ics_chart-2024-12.log.json`. The default
  log path is anchored at the **repository root** (`default_log_path()`), so
  running the same command from any subdirectory lands in the same place. These
  logs are tracked in the repository as provenance artefacts: `.gitignore` must
  not ignore them, and no ignore rule that matches
  `tools/build-logs/*.log.json` may be introduced. This clause is normative.
- The generation logs of both snapshots are archived in `tools/build-logs/`,
  produced by the same command as above. Re-running `tools/build_snapshot.py`
  must reproduce the snapshots byte-for-byte
  (`tests/test_snapshot_provenance.py` asserts this), so the `retrieved_at`,
  `out` and `command` fields in the logs are checkable literals too.
- The machine-readable diff between versions is generated by
  `tools/make_diff.py`. After writing a snapshot, `build_snapshot.py
  --diff-with <version>` can also produce that file, provided `--diff-with`
  differs from this run's `--chart-version` — equal values are rejected. The
  baseline-vs-derived diff is archived as
  `geophylo/data/snapshots/diff-2024-12_to_2026-06.json`.
  - The header records both sides' chart version, `snapshot_revision`,
    `payload_sha256` and `source_sha256`; the body lists field-by-field changes
    for every affected record.
  - The `boundary_age_changes` section collapses the propagation of one shared
    boundary across multiple records into a single change; two different
    uncertainty migrations on the same shared boundary fail explicitly — the
    first one is never silently kept.
  - The file must not be edited by hand: `tests/test_snapshot_provenance.py`
    recomputes it in memory and compares it with the shipped bytes.

### Derivation of the 2024/12 snapshot

The upstream changeNotes (`skos:changeNote "2026-06: hasBeginning 246.7 ->
247.0"` etc.) record three boundary updates in 2026/06 relative to 2024/12:

1. Triassic base Anisian: 246.7 → 247.0 Ma
2. base Olenekian: 249.9 → 250.8 Ma
3. Permian base Wuchiapingian: 259.51 ±0.21 → 259.857 ±0.084 Ma

`--to 2024/12` rolls these changeNotes back one by one and restores the
uncertainty of the Wuchiapingian base (0.084 → 0.21; the upstream changeNote
recorded the age change but not the uncertainty change).

`--to` is the **sole decider** of the rollback set: the filter must not embed
any concrete chart-version literal, otherwise `--to` would not participate in
the decision and every value would produce the same "rolled-back" data. The
rules:

- What is rolled back are changeNotes whose version prefix is **strictly
  newer** than `--to`; earlier revisions stay in force.
- Every changeNote must carry a `YYYY-MM:` prefix, otherwise the build fails.
  An upstream rewording cannot silently change the rollback scope.
- `--to` must equal `--chart-version`, and the target must be a version
  registered in `DERIVED_SNAPSHOTS`; if not a single boundary is rolled back the
  build fails — relabelling baseline data as an earlier version is forbidden.
  Hence `--to 2026/06`, `--to 2030/01`, `--to 1999/01` and `--to nonsense` all
  refuse to build.
- `derived_from.reverted_boundary_count` is written from the **actual** number
  of boundaries rolled back in this build, and `rebuild_index()` reconciles it
  against the real length of `reverted_boundaries` in the generation log;
  a mismatch rejects the index rebuild. Counts always come from the build
  result, never from hand-written constants.

This snapshot is **not** fetched from an upstream 2024/12 archived release; it
is derived by rolling back the same pinned input, so its `source` block is
byte-identical to that of 2026/06. The fact is machine-visible:

- The `2024/12` entry of `versions.json` carries `derived_from`, with fields for
  the parent version, derivation method, generator switches, pinned input file,
  number of reverted boundaries and the generation-log path.
  `build_snapshot.py` writes it into the snapshot top level at build time and
  `rebuild_index()` carries it over, so the fields cannot be lost and their
  content must not be edited by hand.
- The human-readable account is `geophylo/data/snapshots/PROVENANCE.md`.
- Non-reverted changes: any upstream revision without a `skos:changeNote` keeps
  its 2026/06 value in this snapshot. The completeness of the derivation is
  bounded by upstream's own change log.
- The premise "the ICS chart repository does not publish a machine-readable
  2024/12 Turtle snapshot" is an **external factual claim**: this repository
  cannot verify it while offline, so `PROVENANCE.md` flags such claims
  explicitly; readers should treat them as disclosed assumptions, not
  established facts.

### Deterministic reconciliation of upstream data flaws

The generator repairs only those upstream flaws that deterministic rules can
prove; every repair is recorded in the generation log and in the snapshot's
top-level `derivation.integrity_repairs` (that field sits outside `intervals`,
so it does not change the payload hash but ships with the package):

- **Minority rounding-variant absorption** (`snap-minority-rounding-variant`):
  the criterion is a **structural equivalence class** — the three structural
  relations of one and the same boundary: parent base ≡ oldest child base;
  parent top ≡ youngest child top; the common surface of adjacent children of
  the same parent.
  - Activation conditions: the two spellings within a class differ by at most
    0.05, the minority spelling appears exactly once repository-wide, and the
    majority spelling appears at least twice (e.g. the Aquitanian base 23.03 vs
    the Miocene base and its four same-boundary records at 23.04).
  - The criterion only looks at structural equivalence classes, never at global
    counts: global counting has nothing to do with chronostratigraphy and would
    treat the Quaternary values 0.0117, 0.0082, 0.0042 and 0.0 as
    "minorities". Those values are safe because they are internally consistent
    within their own structural classes. With insufficient evidence the build
    fails — the builder does not guess. After absorption,
    `check_parent_containment()` re-verifies parent–child temporal containment.
- **Same-rank overlap reconciliation**
  (`same-rank-overlap-children-union`): on overlap, if the union endpoint of the
  older interval's children equals the base of the younger interval, the
  generator trusts the children's endpoints (in the 2026/06 upstream data,
  Ludlow's endpoint 419.62 contradicts the union endpoint of its child stages,
  422.7). In all other cases the build fails explicitly and the decision is left
  to a human; silently rewriting numbers is not allowed. The union computation
  uses `is not None`; `0.0` is a legitimate endpoint value.
  - When an age is moved, the `marginOfError` and the
    `skos:note "uncertain"` belonging to the old age at that endpoint are
    **cleared at the same time**, because they are statements about the old
    value. Carrying them along would fabricate an "1.6 vs 1.36" uncertainty
    conflict at 422.7 that upstream never had.
  - Clearing is allowed only if independent uncertainty evidence exists at the
    target age (the ±1.6 at 422.7 is written at both the Ludfordian top and the
    Pridoli base); otherwise the build fails.
- The generator fails explicitly on unparseable endpoint literals, endpoint
  predicates outside the whitelist, missing `hasBeginning` or `hasEnd`, and
  `skos:Concept` subjects without `gts:rank` — it never silently produces a
  crippled snapshot that "still passes all validations".
  `derivation.parse_stats` self-reports the upstream statement counts, and
  `tests/test_data_contract.py` re-verifies them with an independent parser
  (178 concept subjects, 356 endpoint values, 206 uncertainties, 36 `~` marks).

### Deterministic derivation of upstream metadata

- `status`: a `ratifiedGSSP/GSSA` marker → `ratified`; placeholder naming
  (Cambrian Stage/Series) → `informal`; otherwise `unknown` (honest absence, no
  fabrication).
- Boundary `definition`: age 0 → `present`; the boundary is a base and any
  same-base record has a ratified GSSP → `gssp`; GSSA → `gssa`; otherwise
  `numeric_estimate`.
- Boundary `qualifier` (`tools/build_snapshot.py::boundary_qualifier`) has
  **three** inputs: `definition`, the upstream `schema:marginOfError` (`±`) and
  `skos:note "uncertain"` (the chart's `~`). The rules, in order:
  1. `definition == present` → `present`;
  2. upstream wrote `~` → `approximate`. **This rule takes precedence over**
     the GSSP/GSSA decision: the value of a GSSP boundary can itself be an
     upstream-declared approximation, and recording it as `defined` ("exactly
     defined") would let the definition axis swallow the qualifier axis,
     violating the orthogonality declared in ADR-5;
  3. GSSP/GSSA with a published `±` → `constrained`; GSSP/GSSA without `±` →
     `defined`;
  4. non-GSSP/GSSA with `±` → `constrained`;
  5. everything else → `unknown`.
- `~` and `±` can coexist: then `qualifier == "approximate"` while
  `uncertainty_ma` is kept as-is — neither erases the other (in the pinned
  input, none of the current 36 `~` marks comes with a `±`).
- The qualifier distribution of both shipped snapshots is
  `approximate 36 / constrained 208 / defined 97 / unknown 12 / present 5`
  (358 endpoints in total), matching one-to-one the 36
  `skos:note "uncertain"` marks in the TTL.
- Some subdivisions have no `@en prefLabel` upstream — e.g. the Lower, Middle
  and Upper series names and the Tarantian and the Cambrian placeholder stages.
  Display names are derived deterministically from the IRI local name
  (`LowerJurassic` → `Lower Jurassic`), and the derivation list is recorded in
  the log and in `derivation.derived_labels` (26 entries). These strings
  **also determine the `id`** and are part of the externally stable contract
  surface: an ID such as `ics:period:lower-jurassic` is this project's derived
  value, not an upstream identifier; changing the derivation rule changes IDs
  and is therefore a data change.
- The official short codes (notations) become `aliases`; ICS distinguishes
  epoch-level (`T3`) from age-level (`t3`) codes by case. On case-folding
  conflicts the winner is decided by rank priority (Super-Eon < Eon < Era <
  Period < Sub-Period < Epoch < Age), then by lexicographic `id` within a rank,
  and the losers are recorded one by one in `derivation.dropped_aliases`
  (35 entries) and in the generation log. **This is a deliberate data loss**:
  the `aliases` of 35 records such as `ics:age:anisian` are therefore empty,
  and `find_by_name("T3")` only matches the epoch-level record. Which rank
  should own a shared code needs confirmation against the ICS chart; until
  then the priority is not changed, but the loss list must stay visible in the
  package.
- `Pridoli` is declared both as an Age and as an Epoch (officially so; the chart
  shows it in two rows), and the snapshot generates one record per declared rank
  (`ics:age:pridoli` and `ics:epoch:pridoli`).
- Endpoint-level `source_iri` is always `null`: the ICS chart writes endpoints
  as blank nodes with no addressable stable IRI; the field is reserved for
  external backends that can provide endpoint IRIs. The interval-level
  `source_iri`
  (`http://resource.geosciml.org/classifier/ics/ischart/<Concept>`) is the
  addressable identifier of the upstream concept.

## Snapshot update procedure

1. Update the pinned input under `tools/source/`, recording the new tag, commit
   and SHA-256.
2. Generate the new snapshot and the machine-readable diff. The diff covers
   boundaries, uncertainties, `~` marks (`qualifier`), names, ranks, colors,
   status, and added/removed intervals. `make_diff.py`'s `_BOUNDARY_SUBKEYS`
   includes `qualifier`, so both the gain and the loss of `~` enter the diff and
   the approximate-mark semantics cannot be silently lost between versions.
3. Run the integrity, TTL-ground-truth and visual regression tests; update the
   sentinel assertions (record counts, per-rank counts, qualifier distribution)
   and describe the change in the CHANGELOG.
4. Release. **The `intervals` of a released snapshot are append-only**: a new
   chart layout = a new file + a new `versions.json` entry; fixing an extraction
   defect within the same layout = bumping that file's `snapshot_revision`, with
   the reason recorded in the CHANGELOG and PROVENANCE. Older snapshots must be
   kept and remain selectable via `Timescale(version=...)`. Scientific data
   changes trigger at least a minor release; corrected transcriptions must be
   listed separately in the CHANGELOG.
5. `generator.version` marks "which extraction semantics", not "which package
   version", so bumping the package version does not change this label; it is
   bumped only when the extraction semantics (parsing, reconciliation, schema)
   change.

## Licensing compliance

- The official ICS chart data is published under **CC-BY-4.0**, copyright and
  attribution International Commission on Stratigraphy. The snapshots' `license`
  metadata, `LICENSES/CC-BY-4.0.txt` and `NOTICE` record the attribution and
  citation requirements; both the sdist and the wheel carry these files.
- This library's code is released under MIT; the code license does not cover
  the third-party data files.
- `ete4` (GPL-3.0-or-later) is **not** a required dependency of this library: it
  is pulled in only when the user explicitly installs the optional extra
  `geophylo[iplotx]` (iplotx imports it at runtime without declaring it, so this
  library adds it to that extra). The core installation and the MIT code itself
  contain no GPL components.
- The library imports `pyrolite` only when `geophylo[pyrolite]` is installed,
  using it as an optional runtime backend; `pyrolite`'s data does not enter this
  library's artefacts.

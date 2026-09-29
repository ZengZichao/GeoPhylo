# Snapshot provenance

Machine-readable counterpart: the `derived_from` block of each entry in
[`versions.json`](versions.json) (read it with
`geophylo.data.builtin.load_versions_index()`). Narrative version:
[`docs/data-policy.md`](../../../docs/data-policy.md). Reproduction commands:
[`tools/build_snapshot.py`](../../../tools/build_snapshot.py) and
[`tools/make_diff.py`](../../../tools/make_diff.py); the logs of the runs that
produced the files in this directory are in
[`tools/build-logs/`](../../../tools/build-logs/).

## `ics_chart-2026-06.json` — fetched, not derived

Generated directly from the pinned upstream release:

| Field | Value |
| --- | --- |
| Upstream repository | `https://github.com/i-c-stratigraphy/chart` |
| Tag | `v2026-06.5` (the official 2026/06 chart release) |
| Commit | `44d1043ecf295cce1be03b3fc5fa95ca65fe770b` |
| Input file | `chart.ttl`, vendored as `tools/source/ics-chart-v2026-06.5.ttl` |
| Input SHA-256 | `0158959e8fdae2a8bdbb14ca3e424d2370362cd8dfc8af86e7be73c74368b355` |
| `snapshot_revision` | 1 |
| `hash.payload_sha256` (shipped) | `4e5603d30aa397c86d469077a8ede7bd454470d3a31d179b2544debb05861fb0` |

Reproduction (the exact argv recorded in
`tools/build-logs/ics_chart-2026-06.log.json`, run from the repository root):

```
python tools/build_snapshot.py \
    --ttl tools/source/ics-chart-v2026-06.5.ttl \
    --chart-version 2026/06 --tag v2026-06.5 \
    --commit 44d1043ecf295cce1be03b3fc5fa95ca65fe770b \
    --source-sha256 0158959e8fdae2a8bdbb14ca3e424d2370362cd8dfc8af86e7be73c74368b355 \
    --retrieved-at 2026-09-11T00:00:00Z \
    --out geophylo/data/snapshots/ics_chart-2026-06.json \
    --write-index --diff-with 2024/12
```

`payload_sha256` is a SHA-256 over the canonical JSON serialization of the
`intervals` array only (sorted keys, compact separators, UTF-8). Metadata
outside that array — including this file, the `source` block and the `license`
citation — is not covered by the hash and may be corrected without changing
any scientific value.

## `ics_chart-2024-12.json` — **derived**, not fetched

This snapshot is **not** an extract of an archived 2024/12 upstream release.
The ICS chart repository does not publish a machine-readable 2024/12 Turtle
snapshot, so the file was produced from the *same pinned 2026/06 input* by
applying the upstream `skos:changeNote` entries in reverse:

```
python tools/build_snapshot.py \
    --ttl tools/source/ics-chart-v2026-06.5.ttl \
    --chart-version 2024/12 --to 2024/12 --tag v2026-06.5 \
    --commit 44d1043ecf295cce1be03b3fc5fa95ca65fe770b \
    --source-sha256 0158959e8fdae2a8bdbb14ca3e424d2370362cd8dfc8af86e7be73c74368b355 \
    --retrieved-at 2026-09-11T00:00:00Z \
    --out geophylo/data/snapshots/ics_chart-2024-12.json
```

| Field | Value |
| --- | --- |
| `snapshot_revision` | 1 |
| `hash.payload_sha256` (shipped) | `ef099225bc1ef356e45f95cd1c74eb89f8498ea2f3392250a8273c08a7591c14` |
| Generation log | `tools/build-logs/ics_chart-2024-12.log.json` |

Consequences a reader must know:

1. **The `source` block is byte-identical to the 2026/06 snapshot**, including
   the `v2026-06.5` tag, the commit and the input hash. It describes the input
   that was *read*, not the chart edition that is *represented*. Treat it as
   the provenance of the derivation, not as a claim that a 2024/12 release was
   downloaded.
2. Only the boundary values that the upstream change notes mention were
   rolled back — 10 boundary-age fields across 9 records, coming from 3
   distinct chart-level revisions (base Anisian, base Olenekian, base
   Wuchiapingian). Counting the uncertainty fields as well, the diff lists
   14 field changes in total (10 age fields + 4 uncertainty fields); every
   one of them is listed field by field in the diff artifact section below.
   The full list is the `reverted_boundaries` array of
   `tools/build-logs/ics_chart-2024-12.log.json` and the
   `boundary_age_changes` array of
   [`diff-2024-12_to_2026-06.json`](diff-2024-12_to_2026-06.json).
3. The Wuchiapingian base additionally carries a documented margin
   restoration (259.857 ± 0.084 → 259.51 ± 0.21 Ma): upstream change notes
   record age changes only, never margin changes, so the 0.21 Ma value comes
   from the project's documented revert patch (development document 5.7,
   encoded as `REVERTED_MARGIN_PATCHES` in `tools/build_snapshot.py`) rather
   than from the change notes. It is the one number in this snapshot that is
   not traceable to a machine-readable upstream statement — a
   **project-authored value**, and it is presented as such wherever the
   2024/12 Wuchiapingian base is quoted.
4. Any upstream correction that was *not* annotated with a `skos:changeNote`
   is therefore silently present in this snapshot at its 2026/06 value. The
   derivation can only be as complete as upstream's own change log; it is a
   best-effort reconstruction of the 2024/12 chart, not a byte-exact archive of
   it.

## Credentials pending (unverified external claims)

One statement below is now verified against the upstream project and carries its
credential; the other still rests on a source that is not in this repository and
is marked open rather than presented as established fact.

- **Verified 2026-09-21** — the premise that the ICS chart repository publishes no
  machine-readable 2024/12 Turtle snapshot, which is the sole reason this file is
  derived rather than fetched, was checked against the project's own release
  listing (`github.com/i-c-stratigraphy/chart`, releases API, 2026-09-21). The
  listing carries no 2024/12 tag: its oldest entries are the `v0.0.x` series, whose
  earliest recorded release is `v0.0.15` dated 2025-03-12, and the first
  chart-edition tags are the `v2026-06*` series. A 2024/12 chart edition is
  therefore unobtainable as machine-readable upstream data, so the derivation below
  is the only available reconstruction. Re-check the listing if upstream ever
  back-fills history.

- `TODO(author)` — the ± 0.21 Ma margin restored at the base of the
  Wuchiapingian (item 3 above) is project-authored. Its stated source, the
  development document §5.7, is not shipped with the code. Attach the
  credential (an upstream issue/commit/chart-PDF reference that records
  259.51 ± 0.21) or keep labelling the value as a project decision in the
  documentation and `docs/data-policy.md`.

## Diff artifact

[`diff-2024-12_to_2026-06.json`](diff-2024-12_to_2026-06.json) is generated,
never edited: `python tools/make_diff.py --from ... --to ... --out ...` (or
`--diff-with 2024/12` on `build_snapshot.py`). It records both payload hashes
and both chart versions in its header and lists every changed field of every
affected record. `tests/test_snapshot_provenance.py` regenerates it in memory
and fails if it differs from the shipped file byte-for-byte, so the diff cannot
drift from the snapshots it claims to describe.

## Immutability

Published snapshots are append-only: the extractor semantics are labelled by
`generator.version`, and that label is deliberately *not* bumped when the
package version rises, because bumping it would rewrite bytes inside
already-published data files. The label reads `0.1.0` for both shipped files,
covering the qualifier extraction rules (`skos:note "uncertain"` becomes
`qualifier="approximate"`), the qualifier precedence, the structural-equivalence
snapping and the "margin does not travel with the age" rule
(`tools/build_snapshot.py`). A new chart edition is a new file plus a new
`versions.json` entry, never an edit of an existing one.

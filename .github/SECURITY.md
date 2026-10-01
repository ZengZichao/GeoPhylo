# Security Policy

## Supported versions

GeoPhylo is pre-1.0 (`0.1.0`). Only the latest released tag receives security
fixes; older tags are not patched.

| Version | Supported |
| ------- | --------- |
| 0.1.x   | yes       |
| < 0.1   | no        |

## Reporting a vulnerability

**Do not open a public issue for a security problem.**

Report it privately through GitHub's private vulnerability reporting:

1. Go to <https://github.com/ZengZichao/GeoPhylo/security/advisories/new>.
2. Describe the issue, the affected version, and a minimal reproducer.
3. You will get an acknowledgement within 7 days.

If private reporting is unavailable to you, mail
`zengzichao@sjtu.edu.cn` with the subject `SECURITY: geophylo` and the same
information. Please do not include the detail in a public issue or a pull
request while the report is being triaged.

## What counts as a vulnerability here

- Code execution or arbitrary file access through untrusted input passed into
  the public API (`Timescale`, `CoordinateSpec`, `add_geo_axis`, `add_geo_ring`).
- Path traversal or unsafe deserialization in the data layer, in particular in
  `geophylo.data` and the bundled-snapshot loader.
- Anything in `geophylo/data/snapshots/*.json` that lets a third party alter
  the geological values the library reports. The bundled snapshots are
  reproducibility artefacts: their integrity is a correctness property, so an
  attacker-controlled snapshot diff is in scope, not merely a data-quality bug.

Not vulnerabilities (please report these as ordinary bugs):

- A wrong or out-of-date geological boundary value. Raise a normal issue and
  cite the ICS source; the snapshot update path is documented in
  `docs/data-policy.md`.
- Crashes or incorrect output from malformed `Bio.Phylo` trees that the caller
  constructed.
- Failures to install from PyPI or to resolve an optional integration.

## Bundled third-party data

The International Chronostratigraphic Chart snapshots redistributed in
`geophylo/data/snapshots/` are third-party data under CC-BY-4.0, not code
authored here. See `NOTICE` and `docs/data-policy.md` for attribution and the
update procedure.

## Disclosure

The maintainer aims to acknowledge a report within 7 days and to release or
disclose a fix within 90 days of a confirmed report. Credit is offered in the
advisory unless you prefer otherwise.

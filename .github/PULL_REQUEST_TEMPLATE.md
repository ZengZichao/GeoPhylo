## What this changes

<!-- One or two sentences. If this closes an issue, write "Closes #NN". -->

## Why

<!-- The problem, not the solution. Link the issue if there is one. -->

## Checklist

- [ ] The CI gate passes locally: the blocking command, run over the same four
      subtrees CI uses.
- [ ] New or changed public behaviour is reflected in `CHANGELOG.md` and
      `CHANGELOG.zh-CN.md`.
- [ ] Public API changes are reflected in `docs/user-guide.en.md` and
      `docs/user-guide.zh.md`.
- [ ] Non-obvious choices are recorded as an ADR in `docs/adr/` (both
      languages) rather than left in a commit message.
- [ ] If this touches CI, the change still satisfies
      `tests/test_packaging.py::test_ci_gate_commands_match_the_declared_policy`.
- [ ] If this touches bundled ICS data, `docs/data-policy.md` is updated and
      `tools/build-logs/` holds the new provenance record.
- [ ] `pre-commit` runs clean if you have it installed. It is not required,
      but the hooks are the same checks CI runs.

## Verification

<!--
State what you actually ran and what the result was. If you could not run
something, say so explicitly rather than implying it passed.
-->

```
<command>
<result>
```

## Notes for the maintainer

<!-- Optional. Anything the reviewer should look at first. -->

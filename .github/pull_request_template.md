## Summary

<!-- What changed? -->

## Scope

<!-- What is intentionally in or out of scope? -->

## Verification

- [ ] `uv run --frozen --all-extras pytest`
- [ ] `uv run --frozen agent-permit scan . --ci --exclude "tests/fixtures/**"`
- [ ] `python3 tools/release_check.py` when release-facing behavior changed
- [ ] Dashboard lint/build when dashboard code changed

## Safety

- [ ] No raw secrets, private traces, customer data, or generated `.agent-permit/` run directories are committed.
- [ ] New scanner findings include file and line evidence when possible.
- [ ] New rules include fixtures or tests.
- [ ] Deep Agent changes preserve bounded evidence access and citation checks.

## Docs

- [ ] README or docs updated when commands, outputs, artifacts, or public behavior changed.

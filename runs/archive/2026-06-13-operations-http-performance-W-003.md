# Run ID

2026-06-13-operations-http-performance-W-003

## Plan path

/Users/hernando_zhao/codex/worker-workspaces/stock_dashboard/20260613-stabilize-operations-http-performance-c090a7/plans/active/plan-20260613-operations-http-performance.md

## Hop ID

W-003

## Work item ID

W-003

## Goal

Add a repeatable shell performance probe for operations API and served page response budgets, with parser self-test and optional runtime commit verification.

## Non-goals

- Do not publish or verify the real runtime in this hop; W-004 performs the post-publish runtime check.
- Do not change release verifier behavior or operations API implementation.
- Do not add long-running integration checks to the default test suite.

## Plan evidence

W-003 follows W-001 and W-002 by providing a reusable command that W-004 can run against the published candidate runtime.

## Files expected to change

- `scripts/verify-operations-performance.sh`
- `plans/active/plan-20260613-operations-http-performance.md`
- `runs/archive/2026-06-13-operations-http-performance-W-003.md` after closeout

## Implementation steps

1. Inspect existing project script style for Bash options, argument parsing, and output conventions.
2. Add `scripts/verify-operations-performance.sh` with `--self-test`, `--api-base-url`, `--frontend-url`, `--runtime-root`, `--expected-commit`, `--max-api-seconds`, and `--max-page-seconds`.
3. Probe the portfolios detail endpoint, replay detail endpoint, and frontend page shell with `curl` timing in normal mode.
4. Fail non-zero when any configured budget is exceeded or when runtime commit verification is requested and does not match.
5. Keep `--self-test` local and deterministic without network calls.
6. Run the W-003 acceptance gate.

## Acceptance criteria

- `bash scripts/verify-operations-performance.sh --self-test` exits 0.
- Normal mode defines the endpoints and budget checks W-004 needs.
- Runtime commit verification checks the published runtime only when both runtime root and expected commit are supplied.
- The script prints concrete timing/source lines and fails non-zero on budget or commit mismatch.

## Acceptance Type

command_exit_0

## Acceptance Spec

cmd:bash scripts/verify-operations-performance.sh --self-test

## Planned Evidence

- MiMo run-plan review result.
- MiMo code-review result.
- Self-test command and exit code.

## Actual Evidence

- Added executable `scripts/verify-operations-performance.sh`.
- Script probes portfolios detail, replay detail, and frontend page shell in normal mode with curl timing and non-zero exit on budget failure.
- Script supports `--runtime-root` plus `--expected-commit` by checking `output/releases/latest-successful.commit`.
- Deterministic self-test covers budget pass/fail, commit match, commit mismatch, missing commit file, and URL normalization without network calls.
- Acceptance gate passed: `bash scripts/verify-operations-performance.sh --self-test` exited 0 with `[perf:self-test] ok`.

## Risk and rollback notes

Primary risk is a probe that appears to validate runtime performance but checks the wrong commit or silently ignores timing failures. Mitigation is explicit expected-commit checking and a deterministic self-test for budget comparison behavior. Rollback is deleting the script and removing W-004's dependency on it.

## Gate plan

Run `bash scripts/verify-operations-performance.sh --self-test`.

## MiMo plan-review result

Passed. MiMo found no blocking, material, or minor drift from W-003.

## Codex escalation plan-review result

Not required for W-003. This hop adds a verification probe script but does not publish, change deployment mechanics, change credentials, or alter release state.

## Implementation summary

Added a Bash performance probe with configurable API/frontend URLs, sample symbol, API/page budgets, curl timeout, runtime root, and expected commit. Normal mode checks the portfolios detail endpoint, replay detail endpoint, and frontend shell, printing concrete timing lines and returning non-zero on any request/budget failure. `--self-test` runs local-only assertions for parser-adjacent helper behavior.

## MiMo code-review result

Passed. MiMo found no blocking or material issues. Minor suggestions were addressed by using a local normalized expected-commit variable and adding self-test coverage for a missing `latest-successful.commit` file; focused MiMo re-review found no remaining findings.

## Codex escalation code-review result

Not required for W-003 unless implementation expands into publish or release verifier behavior.

## Gate results

Passed: `bash scripts/verify-operations-performance.sh --self-test` exited 0 with `[perf:self-test] ok`. `bash -n scripts/verify-operations-performance.sh` also exited 0.

## Plan update summary

W-003 completed and plan evidence updated.

## Plan archive result

Not applicable for W-003; the full plan remains active until all work items complete.

## Archive and merge result

Archived for later commit. The branch will not merge until W-004 passes because the plan is being executed in full-plan mode.

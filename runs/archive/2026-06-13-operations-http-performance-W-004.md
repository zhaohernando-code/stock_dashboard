# Run ID

2026-06-13-operations-http-performance-W-004

## Plan path

/Users/hernando_zhao/codex/worker-workspaces/stock_dashboard/20260613-stabilize-operations-http-performance-c090a7/plans/archive/plan-20260613-operations-http-performance.md

## Hop ID

W-004

## Work item ID

W-004

## Goal

Publish the clean candidate with source backup enabled, verify real served local and canonical operations/page responses meet the plan budgets, and stop before merge with evidence if the candidate is unhealthy or too slow.

## Non-goals

- Do not change implementation code in this hop unless a verification blocker is found.
- Do not skip source backup.
- Do not merge or push before the pre-merge runtime gate passes.
- Do not run unrelated long integration suites as a substitute for served runtime timing evidence.

## Plan evidence

W-004 is the pre-merge live runtime gate for the full W-001 to W-003 change set. The plan requires source-backup publish, expected commit verification, local 5s/2s budget checks, canonical 8s checks, timing evidence, and rollback evidence only if the candidate publish makes runtime unhealthy.

## Files expected to change

- `plans/active/plan-20260613-operations-http-performance.md`
- `scripts/publish-local-runtime.sh` because live verification exposed a stale LaunchAgent cleanup blocker
- `scripts/start-local-frontend.sh` because live verification exposed a slow static-server Node resolver path
- `tests/test_publish_script_static.py`
- `runs/archive/2026-06-13-operations-http-performance-W-004.md` after closeout

## Implementation steps

1. Confirm all W-001 to W-003 changes and run records are committed into a clean candidate worktree.
2. Capture the candidate commit with `git rev-parse HEAD`.
3. Publish with `ASHARE_PUBLISH_BACKUP_MODE=source ASHARE_PUBLISH_REFRESH_MODE=skip bash scripts/publish-local-runtime.sh` and capture the backup path plus release manifest path.
4. Run `bash scripts/verify-operations-performance.sh --api-base-url http://127.0.0.1:8000 --frontend-url http://127.0.0.1:5173 --runtime-root /Users/hernando_zhao/codex/runtime/projects/ashare-dashboard --expected-commit <candidate-commit> --max-api-seconds 5 --max-page-seconds 2` as a post-verifier served runtime sanity check.
5. Record local API first-request timing numbers from the current publish release verifier manifest `api_warmups` for portfolios and replay, because release verification is the first operations warmup after backend restart and the later performance probe is already warmed.
6. Record canonical timing evidence from actual canonical fetches. Release verifier manifest timings may be used for operations endpoints only when they come from the current publish's real fetch/warmup pass; frontend page timing must come from a fresh canonical served-page request. Ensure operations/page checks are within 8s.
7. If the candidate is unhealthy after publish, record the backup path and rollback command, execute rollback only when needed to restore health while preserving runtime `data` and `output`, repair in-scope publish/restart blockers if found, and stop before merge if the final candidate cannot pass.
8. If the candidate is only over budget but runtime remains healthy, preserve evidence, mark W-004 failed, and stop before merge without rollback.

## Acceptance criteria

- Candidate publish used `ASHARE_PUBLISH_BACKUP_MODE=source` and `ASHARE_PUBLISH_REFRESH_MODE=skip`.
- Backup path and release manifest path are recorded.
- Performance probe ran against the published runtime with the expected candidate commit.
- Current publish release verifier local portfolios/replay warmup timings are each <= 5s, and the local frontend shell in the post-verifier performance probe is <= 2s.
- Canonical operations/page checks are each <= 8s using concrete timing evidence from current real canonical fetches, not stale manifest inspection.
- Failures stop before merge and include rollback evidence when the candidate is unhealthy.
- Source-backup rollback instructions preserve runtime `data` and `output`.

## Acceptance Type

manual

## Acceptance Spec

manual:candidate publish used ASHARE_PUBLISH_BACKUP_MODE=source and ASHARE_PUBLISH_REFRESH_MODE=skip; backup path captured; current release verifier local operations warmup timings recorded for portfolios/replay and meet 5s; performance probe ran after publish with runtime root and expected commit and local page meets 2s; canonical operations/page checks meet 8s; failures stop before merge with rollback evidence when needed

## Planned Evidence

- MiMo run-plan review result.
- Codex escalation plan-review result because W-004 touches publish/runtime behavior.
- Candidate commit SHA.
- Publish command, backup path, and release manifest path.
- Current release verifier manifest `api_warmups` local timings for portfolios/replay.
- Local post-verifier performance probe command and timing output.
- Canonical timing evidence and budget comparison.
- Publish restart/rollback blocker evidence if a live gate exposes one.
- MiMo code/closeout review result.
- Codex escalation closeout review result.

## Actual Evidence

- Intermediate candidate `6a9e4bbd4dc3505fd664591c3e4f7a20ff06e0f5` published with `ASHARE_PUBLISH_BACKUP_MODE=source ASHARE_PUBLISH_REFRESH_MODE=skip`.
- Source backup captured at `/Users/hernando_zhao/codex/runtime/projects/ashare-dashboard.backups/20260612T172514Z-6a9e4bb`.
- Intermediate publish failed before writing the candidate release manifest: backend health timed out at `http://127.0.0.1:8000/health`; `latest-successful.commit` remained `d4430e6734f9160e156712103c47979279586a07`.
- Runtime was restored with a data/output-preserving source rollback from that backup and LaunchAgent restart. The backend later recovered, but diagnosis showed the publish restart path could leave a stale uvicorn process alive without a usable health response.
- W-004 repair added stale non-listening backend/frontend process cleanup to `restart_agent` and changed the source-backup rollback hint to preserve runtime `data` and `output`.
- W-004 also changed `start-local-frontend.sh` so the static dist server resolves Node with `--no-default-requirements`; the 5173 server does not need `node:sqlite`, and that resolver probe was observed lingering during LaunchAgent startup.
- Final candidate `7cf160a1bffdb0576e9557bf2b8d4ac560fb4a7f` was published with `ASHARE_PUBLISH_BACKUP_MODE=source ASHARE_PUBLISH_REFRESH_MODE=skip`.
- Final source backup captured at `/Users/hernando_zhao/codex/runtime/projects/ashare-dashboard.backups/20260612T183845Z-7cf160a`.
- Final release manifest written at `/Users/hernando_zhao/codex/runtime/projects/ashare-dashboard/output/releases/20260612T183949Z-7cf160a1bffd/manifest.json`; deploy verification passed `19 passed, 0 failed`.
- Current publish release verifier timing evidence met budgets: portfolios local warmup `0.012s`, portfolios canonical warmup `0.788s`, replay local warmup `0.011s`, replay canonical warmup `0.283s`.
- Served shape check for `http://127.0.0.1:8000/dashboard/operations/details?section=portfolios&sample_symbol=600519.SH` returned `section=portfolios`, `portfolios_type=list`, and `portfolio_count=24`.
- Post-publish local performance probe passed for expected runtime commit `7cf160a1bffdb0576e9557bf2b8d4ac560fb4a7f`: portfolios `0.011950s`, replay `0.004691s`, frontend shell `0.001394s`.
- TTL+62s local performance probe also passed for the same runtime commit: portfolios `0.041142s`, replay `0.030639s`, frontend shell `0.014154s`.
- Fresh canonical page timing for `https://hernando-zhao.cn/projects/ashare-dashboard/` was `0.110308s`, within the 8s canonical budget.

## Risk and rollback notes

Primary risk is publishing an unhealthy candidate or mistaking a stale runtime for the candidate. Mitigation is source backup, expected commit verification, and timing checks tied to the candidate commit. If runtime becomes unhealthy, restore source files from the backup while preserving runtime `data` and `output`, then restart LaunchAgents before stopping or retrying. If only performance budgets fail while runtime remains healthy, stop before merge and do not rollback unless evidence shows the candidate harmed the served runtime.

## Gate plan

Manual gate described by the W-004 acceptance spec.

## MiMo plan-review result

Passed. Initial MiMo review found no blocking or material issue. Minor clarification accepted: canonical timing evidence must be actual timing from current fetches, with release verifier manifest timing acceptable only for operations endpoints when it was produced by the current publish pass; frontend timing requires a fresh canonical served-page fetch. Focused MiMo re-review after the local first-request evidence change also found no blocking/material issue.

## Codex escalation plan-review result

Material finding accepted and re-reviewed. Codex noted that the publish flow runs release verification and operations prewarm before the later local performance probe, so the performance probe alone would not prove the plan's post-restart, no-manual-cache-hit local API budget. W-004 was revised to use the current publish release verifier `api_warmups` local durations for portfolios/replay as first operations timing evidence, while keeping the performance probe for runtime commit and served-page sanity. Focused Codex re-review confirmed the previous material finding is closed and reported no blocking/material issue.

## Implementation summary

W-004 live verification exposed two in-scope publish-path blockers. First, LaunchAgent restart cleanup only killed port holders, so a stale uvicorn/node child that did not bind the port could survive and leave served requests failing or hanging. `publish-local-runtime.sh` now terminates stale backend/frontend runtime processes by expected command pattern between `launchctl bootout` and `launchctl bootstrap`, and its source-backup rollback hint preserves runtime `data` and `output`. Second, the frontend static server wrapper used the default Node resolver requirement set, including `node:sqlite`; `start-local-frontend.sh` now resolves Node with `--no-default-requirements` because the dist server only needs standard HTTP/file modules.

## MiMo code-review result

Passed. Broad W-004 review found no blocking/material issues. Focused marker/TTL review passed after release-marker side effects and cache TTL defaults were repaired. Final runtime-cache and shape-fix re-reviews also found no blocking/material issues; MiMo confirmed the `section=portfolios` detail payload now preserves the frontend contract as a top-level `portfolios` list.

## Codex escalation code-review result

Passed after fixes. Codex reviews found and closed two material blockers during W-004: release verification was still writing latest-successful markers before final deploy verification, and the lightweight portfolios detail initially returned a nested `portfolios.portfolios` shape. The final focused Codex re-review reported no blocking/material findings and marked W-004 merge-ready based on the inspected code and passing/runtime evidence.

## Gate results

Passed.

- `python3 -m pytest -q tests/test_frontend_projections.py tests/test_dashboard_operations_views.py tests/test_operations.py tests/test_release_verifier.py tests/test_publish_script_static.py` passed with `50 passed, 12 deselected, 6 subtests passed in 5.93s`.
- `bash scripts/verify-operations-performance.sh --self-test && bash -n scripts/publish-local-runtime.sh && bash -n scripts/start-local-backend.sh && bash -n scripts/start-local-frontend.sh && bash -n scripts/verify-operations-performance.sh` passed.
- `ASHARE_PUBLISH_BACKUP_MODE=source ASHARE_PUBLISH_REFRESH_MODE=skip bash scripts/publish-local-runtime.sh` passed for final candidate `7cf160a1bffdb0576e9557bf2b8d4ac560fb4a7f`.
- Post-publish performance probes and served shape checks passed with the timing evidence recorded above.

## Plan update summary

W-004 set to `done`; top-level plan status set to `archived`.

## Plan archive result

Plan archived to `plans/archive/plan-20260613-operations-http-performance.md` after all work items reached `done`.

## Archive and merge result

Run archived to `runs/archive/2026-06-13-operations-http-performance-W-004.md`. The branch is ready for final fast-forward merge and push; final runtime publish must be repeated after the docs-only archive commit so runtime commit markers match the merged source commit.

---
schema_version: 1
plan_id: "plan-20260613-operations-http-performance"
title: "Stabilize Operations HTTP Performance"
status: "archived"
created_at: "2026-06-13"
source_request: "Use reviewed-plan-generator then plan-run-loop to fix unstable slow HTTP/page responses for the stock dashboard operations area."
target_repo: "/Users/hernando_zhao/codex/projects/stock_dashboard"
owner: "user"
review_rounds: 3
---

# Plan: Stabilize Operations HTTP Performance

## Compaction-Resistant Summary

Goal: make stock dashboard operations HTTP requests and served page responses stable at normal speeds after publish/restart.
Scope: optimize operations detail API behavior, harden release verifier against duplicate cold calls, and add repeatable performance verification.
Hard boundaries: do not change stock strategy semantics, auth policy, database schema, or long-running refresh behavior unless directly required for response stability.
Key dependencies: FastAPI operations routes, release verifier, runtime publish path, existing runtime LaunchAgents, and local/canonical tunnel health.
Major risks: accidentally changing user-visible operations payloads, masking real regressions with loose timeouts, or relying only on warmed cache.
Approval state: user approved all subsequent execution and requested no approval-related blocking.

## Goal

Bring the current operations-related API and page response path back to stable, normal latency for real local and canonical served traffic. The fix should address the known release verifier timeout and the underlying slow/cold `operations/details` behavior instead of only increasing a timeout.

## Problem / Rationale

Recent diagnosis showed `GET /dashboard/operations/details?section=portfolios&sample_symbol=600519.SH` can exceed the release verifier's 20s request timeout in the long-lived runtime backend, especially after publish or restart. The direct builder is much faster, but the route currently builds the full operations dashboard before returning only the portfolios detail. The release verifier also warms operations endpoints and then fetches them again for fingerprinting, which can re-trigger cold behavior or let short-lived cache entries expire. This leaves publish verification and the served dashboard vulnerable to intermittent slow responses.

## Scope

### In Scope

- Make `section=portfolios` detail use a lighter code path that avoids unrelated operations dashboard sections.
- Preserve existing response shape needed by the frontend and tests.
- Make release verification reuse warmed operations payloads or otherwise avoid duplicate cold operations fetches.
- Add a repeatable local performance verification command for operations API and served page checks.
- Publish to runtime and verify local and canonical served responses after merge.

### Out of Scope

- Changing stock selection, paper-tracking, simulation, or shortpick strategy semantics.
- Database schema migrations.
- Auth policy or beta allowlist changes.
- Replacing the full operations dashboard product design.
- Optimizing unrelated endpoints outside the operations dashboard path.

## Assumptions and Dependencies

- Runtime backend and frontend LaunchAgents remain the supported served environment.
- `scripts/publish-local-runtime.sh` remains the canonical source-to-runtime publish path and is expected to run non-interactively in this environment.
- Execute this plan in full-plan mode: W-001 through W-003 must not be merged to `main` independently; W-004 is the pre-merge live runtime gate for the whole change set.
- W-004 publish must use `ASHARE_PUBLISH_BACKUP_MODE=source` so an unhealthy candidate can be restored with the source rollback command printed by `publish-local-runtime.sh`; the rollback command must preserve runtime `data` and `output`.
- For W-004, get the expected runtime commit from the clean candidate worktree with `git rev-parse HEAD` immediately before publish.
- For W-004 failures, a performance-only budget miss means mark W-004 failed and stop before merge while preserving evidence; runtime rollback is required only when the candidate publish makes the served runtime unhealthy, such as backend crash, startup failure, or `ECONNREFUSED`.
- Local API base URL is `http://127.0.0.1:8000/` and local frontend URL is `http://127.0.0.1:5173/`.
- Canonical URL is `https://hernando-zhao.cn/projects/ashare-dashboard/`.
- "Normal speed" for this plan means the current publish's release verifier records local operations detail warmup timings within 5s after backend restart without relying on a previous manual cache hit, the local served page shell returns within 2s, and canonical operations/page checks return within 8s under the existing tunnel.

## Work Items

| ID | Status | Order | Depends On | Task | Deliverable | Acceptance Type | Acceptance Spec | Evidence |
|----|--------|-------|------------|------|-------------|-----------------|-----------------|----------|
| W-001 | done | 1 | - | Split the portfolios operations detail path from the full operations dashboard build while preserving frontend-visible payload shape; keep the existing `/dashboard/operations/details?section=portfolios` URL and route contract. | Lightweight `section=portfolios` builder and focused regression tests. | test_pass | cmd:python3 -m pytest -q tests/test_dashboard_operations_views.py tests/test_frontend_projections.py tests/test_operations.py | Run `2026-06-13-operations-http-performance-W-001`; MiMo plan/code reviews found no blocking/material issues; gate passed with `17 passed, 12 deselected, 6 subtests passed in 5.22s`. |
| W-002 | done | 2 | W-001 | Harden release verifier so operations warmup payloads are reused for fingerprint/audit and duplicate cold requests are eliminated; if a warmup payload is missing, perform one explicit bounded fetch and mark the result as a warmup miss. | Release verifier change plus tests proving no second cold operations fetch is needed when warmup succeeds. | test_pass | cmd:python3 -m pytest -q tests/test_release_verifier.py tests/test_publish_script_static.py | Run `2026-06-13-operations-http-performance-W-002`; MiMo and Codex reviews closed with no blocking/material issues after Codex test-gap fix; gate passed with `23 passed in 0.24s`. |
| W-003 | done | 3 | W-001,W-002 | Add a repeatable performance probe for operations API and served page response budgets; the probe must check the portfolios detail endpoint, the replay detail endpoint, and the frontend page shell with curl timing and non-zero exit on budget breach, and must support runtime commit verification when given a runtime root and expected commit. | `scripts/verify-operations-performance.sh` with parser self-test and runtime commit-check support. | command_exit_0 | cmd:bash scripts/verify-operations-performance.sh --self-test | Run `2026-06-13-operations-http-performance-W-003`; MiMo plan/code reviews found no blocking/material issues; `bash -n` passed; self-test passed with `[perf:self-test] ok`. |
| W-004 | done | 4 | W-003 | Publish the candidate with source backup enabled and verify real served local/canonical responses meet the defined budgets before merge; if canonical verification fails, record timing evidence, restore runtime with a data/output-preserving source rollback when the published build is unhealthy, repair in-scope publish/restart blockers if found, and stop before merge if the final candidate cannot pass. | Runtime publication, LaunchAgent restart hardening if required, canonical verifier result, local/canonical timing evidence, and clean pre-merge closeout. | manual | manual:candidate publish used ASHARE_PUBLISH_BACKUP_MODE=source and ASHARE_PUBLISH_REFRESH_MODE=skip; backup path captured; current release verifier local operations warmup timings recorded for portfolios/replay and meet 5s; performance probe ran after publish with runtime root and expected commit and local page meets 2s; canonical operations/page checks meet 8s; failures stop before merge with rollback evidence when needed | Run `2026-06-13-operations-http-performance-W-004`; final candidate `7cf160a1bffdb0576e9557bf2b8d4ac560fb4a7f` published with source backup `/Users/hernando_zhao/codex/runtime/projects/ashare-dashboard.backups/20260612T183845Z-7cf160a`; release verifier passed 19/19 with local warmups portfolios 0.012s and replay 0.011s; served shape check returned `portfolios_type=list` and count 24; post-publish probes passed immediately and after TTL+62s; canonical operations/page timings were within 8s; MiMo/Codex reviews closed with no blocking/material issues. |

## Acceptance Criteria & Validation Gates

### Overall Acceptance Criteria

- `section=portfolios` no longer depends on building unrelated operations sections such as replay, manual queue, factor observation, sector exposure, policy governance, or simulation workspace.
- Release verifier no longer performs duplicate cold operations fetches after warmup for the same endpoint payloads.
- A repeatable local performance probe exists and fails when API/page responses exceed configured budgets.
- After merge and publish, local operations API and served frontend page meet the latency budgets in this plan, with local API evidence taken from the current publish verifier's first operations warmup timings rather than a later manually warmed request.
- Canonical served route remains healthy and does not regress to `ECONNREFUSED` or operations verifier timeout.
- The final merge happens only after W-004 live runtime verification passes.

### Validation Gates

- `python3 -m pytest -q tests/test_dashboard_operations_views.py tests/test_frontend_projections.py tests/test_operations.py`
- `python3 -m pytest -q tests/test_release_verifier.py tests/test_publish_script_static.py`
- `bash scripts/verify-operations-performance.sh --self-test`
- `ASHARE_PUBLISH_BACKUP_MODE=source ASHARE_PUBLISH_REFRESH_MODE=skip bash scripts/publish-local-runtime.sh`
- Current publish release verifier manifest `api_warmups` records local portfolios/replay warmup durations <= 5s as the post-restart first operations timing evidence.
- `bash scripts/verify-operations-performance.sh --api-base-url http://127.0.0.1:8000 --frontend-url http://127.0.0.1:5173 --runtime-root /Users/hernando_zhao/codex/runtime/projects/ashare-dashboard --expected-commit <candidate-commit> --max-api-seconds 5 --max-page-seconds 2`
- Manual canonical timing checks for the published route and operations API, with actual timing numbers recorded.

## Risks and Mitigations

- Risk: a lighter portfolios builder changes payload fields expected by the frontend. Mitigation: compare existing tests, add field-shape assertions, and keep compatibility projections intact.
- Risk: verifier reuse hides a canonical/local mismatch. Mitigation: reuse only payloads already fetched from both local and canonical URLs, and keep fingerprint comparison on those payloads.
- Risk: performance probe is flaky on a temporarily busy machine. Mitigation: allow configurable budgets while keeping default budgets aligned with the user-facing target.
- Risk: publish verification still fails due an unrelated endpoint. Mitigation: record exact failing endpoint and do not claim completion until operations/page response budgets pass.

## Open Questions

- None blocking. The plan treats 5s local API, 2s local page shell, and 8s canonical checks as the initial "normal speed" budgets unless later evidence proves stricter budgets are safe.

## Revision History

- 2026-06-13: draft created by Codex for reviewed-plan-generator workflow.
- 2026-06-13: review round 1 accepted MiMo feedback; clarified route contract, performance probe scope, verifier warmup fallback, and W-004 failure handling.
- 2026-06-13: review round 2 accepted Codex escalation feedback; made W-004 a full-plan pre-merge live gate, moved real runtime commit verification to W-004, and required source-backup rollback.
- 2026-06-13: review round 3 accepted MiMo minor clarifications and marked the plan approved for execution under the user's blanket approval.
- 2026-06-13: Codex started W-001, changed top-level status from approved to executing, and set W-001 from pending to in_progress.
- 2026-06-13: Codex completed W-001, changed W-001 from in_progress to done, and recorded MiMo review plus targeted test evidence.
- 2026-06-13: Codex started W-002, changed W-002 from pending to in_progress after W-001 completion.
- 2026-06-13: Codex completed W-002, changed W-002 from in_progress to done, and recorded MiMo/Codex review plus release verifier test evidence.
- 2026-06-13: Codex started W-003, changed W-003 from pending to in_progress after W-002 completion.
- 2026-06-13: Codex completed W-003, changed W-003 from in_progress to done, and recorded MiMo review plus performance probe self-test evidence.
- 2026-06-13: Codex started W-004, changed W-004 from pending to in_progress after W-003 completion.
- 2026-06-13: Codex accepted W-004 escalation feedback and clarified that local API budget evidence must use current publish release verifier warmup timings because the post-publish probe runs after verifier prewarm.
- 2026-06-13: W-004 candidate publish exposed stale LaunchAgent restart cleanup, unsafe source-rollback hint, and slow frontend Node resolver blockers; Codex repaired those publish-path blockers within W-004 before rerunning the live gate.
- 2026-06-13: Codex completed W-004 after source-backup publish, real served shape/performance verification, and MiMo/Codex closeout reviews found no blocking/material issues.
- 2026-06-13: Codex archived the plan after all work items reached done.

## External Review Log

| Round | Reviewer | Finding | Severity | Disposition | Reason | Affected IDs |
|-------|----------|---------|----------|-------------|--------|--------------|
| 1 | MiMo | W-003 performance probe script contract was under-specified. | minor | accepted | Added endpoint list, curl timing expectation, and non-zero exit semantics to W-003. | W-003,W-004 |
| 1 | MiMo | W-001 lightweight builder lacked an implementation boundary. | minor | accepted | Added requirement to keep the existing operations details URL and route contract. | W-001 |
| 1 | MiMo | 5s/2s/8s budgets may be loose without actual timing evidence. | minor | accepted | Added requirement to record actual timing numbers during W-004. | W-003,W-004 |
| 1 | MiMo | W-002 warmup payload reuse lacked fallback behavior. | minor | accepted | Added one bounded fetch with warmup-miss marking when warmup payload is unavailable. | W-002 |
| 1 | MiMo | W-004 lacked a failure branch for canonical verification failures. | major | accepted | Added stop-before-merge behavior and runtime rollback evidence requirement when the published build is unhealthy. | W-004 |
| 1 | MiMo | Publish script non-interactive assumption was implicit. | minor | accepted | Added explicit non-interactive publish assumption. | W-004 |
| 2 | Codex | W-004 was incompatible with per-hop merge order and contained circular `origin/main contains the fix` evidence. | blocking | accepted | Added full-plan no-early-merge assumption, made W-004 the pre-merge live gate, and removed circular origin/main evidence from W-004. | W-004 |
| 2 | Codex | W-003 could validate the wrong runtime before publish. | major | accepted | Changed W-003 to deliver a self-tested probe and moved real runtime expected-commit verification to W-004 after publish. | W-003,W-004 |
| 2 | Codex | Runtime rollback was under-specified because publish defaults to backup skip. | major | accepted | Required `ASHARE_PUBLISH_BACKUP_MODE=source`, backup path capture, and explicit rsync rollback evidence on unhealthy publish. | W-004 |
| 2 | Codex | Plan was draft and untracked, so not executable yet. | major | accepted | Plan remains in the worktree for review, will be marked approved after review completion, and will be tracked/committed with run records. | W-004 |
| 3 | MiMo | W-004 should distinguish performance-only budget miss from an unhealthy candidate publish and should name the candidate commit source. | minor | accepted | Added explicit failure handling semantics and `git rev-parse HEAD` as the expected commit source before publish. | W-003,W-004 |

## User Review Notes

- The user requested plan generation followed by plan-run-loop execution for this fix in the active thread goal.
- The user explicitly approved all subsequent actions and asked not to block the goal on approval.

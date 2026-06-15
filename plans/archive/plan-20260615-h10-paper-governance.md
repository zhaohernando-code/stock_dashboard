---
schema_version: 1
plan_id: "plan-20260615-h10-paper-governance"
title: "H10 Paper Governance"
status: "archived"
created_at: "2026-06-15"
source_request: "Generate and land a reviewed governance plan for deciding how the H10 quiet rank2 benchmark enters Short Pick Lab V2 paper tracking governance, using reviewed-plan-generator and plan-run-loop from generation through implementation."
target_repo: "/Users/hernando_zhao/codex/worker-workspaces/stock_dashboard/20260615-h10-paper-governance-150154"
owner: "user"
review_rounds: 3
---

# Plan: H10 Paper Governance

## Compaction-Resistant Summary

Goal: turn the H10 quiet rank2 fixed85/fixed80 benchmark into governed future true-forward observation candidate readiness, without treating it as already promoted paper tracking.
Hard scope: no historical paper-row backfill, no delayed buy, no fixed90 promotion, no broad strategy search, no investment/production claim.
Key dependency: existing H10 replay, parameter-significance, robustness, execution-decomposition, and rank-ablation evidence.
Main solution: add a machine-checkable H10 paper-governance artifact that consumes rank-ablation, parameter-significance, robustness, and execution-decomposition evidence; update paper ledger contracts for H10 IDs; expose governance state without fake rows; and document the disposition from prior no-promotion to future true-forward observation only.
Major risks: confusing backtest returns with true-forward paper evidence, weakening turnover gates, stale active plan docs, runtime publish drift, and overfitting to the 2023-2026 sample.
Approval state: MiMo and Codex round 2 passed for the main plan. W-001/W-002/W-003 completed with required review and gate evidence. W-004 completed runtime publish and served API verification; the plan is archived after closeout.

## Goal

Land a governed, recoverable decision package for Short Pick Lab V2 that preserves the H10 quiet rank2 benchmark as the current future true-forward observation candidate line while keeping the paper ledger strictly true-forward and avoiding any claim that historical replay rows are already paper tracking.

## Problem / Rationale

The current V2 paper-tracking contract was created before the H10 quiet rank2 benchmark existed. It still describes an empty candidate set from the older June 12 selection artifact and only allows the old V2 config IDs in the ledger schema. Since then, the H10 line produced much stronger evidence: fixed85 rank2 reached about +271.2% total return, about 53.96% annualized return, and large market excess in the same historical window, while fixed80 remains the capital-shadow comparator.

Without a governance layer, the project has two bad failure modes: the promising H10 benchmark can be forgotten by later agents, or it can be prematurely treated as real paper-tracking performance even though the ledger has not written true-forward rows. The plan must separate historical evidence, future observation eligibility, and actual paper-ledger rows, and it must explicitly carry forward the prior robustness decision that fixed85/fixed80 were not promoted to paper tracking by the previous plan.

## Source Requirement Coverage

| Source ID | Source Requirement | Plan Coverage | Coverage Status | Scope Decision | Evidence Required |
|-----------|--------------------|---------------|-----------------|----------------|-------------------|
| SRC-001 | Use reviewed-plan-generator and plan-run-loop from plan generation through landing. | W-001,W-002,W-003,W-004 | covered | in-scope | Schema-v1 plan validation, MiMo plan/run reviews, Codex escalation reviews where required, archived run docs, final plan archive. |
| SRC-002 | Preserve the H10 quiet rank2 fixed85/fixed80 benchmark as durable strategy memory and future comparator. | W-001,W-003 | covered | in-scope | H10 paper-governance artifact and durable doc name fixed85 as primary and fixed80 as capital shadow, while recording the prior no-promotion decision and its new forward-observation-only disposition. |
| SRC-003 | Do not backfill historical replay as true-forward paper tracking. | W-001,W-002,W-003 | covered | in-scope | Contract, schema tests, governance artifact, and read model state all state `future_true_forward_only_no_historical_backfill`. |
| SRC-004 | Keep the no-delayed-buy rule: choose candidate/fallback on the declared day or skip. | W-001,W-002 | covered | in-scope | Paper ledger schema/tests and governance artifact preserve allowed actions and forbidden delayed-entry actions. |
| SRC-005 | Enforce user qualification gates: strategies that do not beat the market or annualize below 30% are not acceptable. | W-001,W-003 | covered | in-scope | Governance validator checks market excess and annualized-return floor for future-observation candidates and also requires source robustness recommendation, risk flags, and prior no-promotion disposition to be recorded rather than bypassed. |
| SRC-006 | Keep fixed90 as diagnostic only unless a separate turnover-gate governance plan changes the rule. | W-001,W-002,W-003 | covered | in-scope | Governance artifact, schema tests, and durable docs mark fixed90 blocked/diagnostic and disallow fixed90 paper-ledger rows. |
| SRC-007 | Keep V2 focused on paper tracking and historical replay; do not add a parameter-search UI or new broad strategy direction. | W-001,W-002,W-003 | covered | in-scope | Changed files avoid new frontend search controls and docs list broad search as out of scope. |
| SRC-008 | Distinguish historical evidence from real paper evidence and avoid investment, production, or auto-trading claims. | W-001,W-002,W-003 | covered | in-scope | Claim ceiling remains `research_observation`; evidence basis distinguishes historical governance from true-forward paper ledger; artifact rejects claims that historical replay created paper rows or performance. |
| SRC-009 | Because this touches schema contracts and governance state, obtain independent external review before implementation and before merge. | W-001,W-002,W-003,W-004 | covered | in-scope | MiMo plus Codex escalation review results recorded in this plan, per-hop run docs, and closeout notes; blocking findings must be accepted or explicitly rejected before execution continues. |

## Production Path Fidelity

| Path ID | User / Production Path | Validation Path | Responsibility Owner | Test Setup / Bypass | Fidelity Status | Evidence Required |
|---------|------------------------|-----------------|----------------------|---------------------|-----------------|-------------------|
| PF-001 | Operator generates H10 paper-governance evidence through `python3 -m ashare_evidence.cli shortpick-v2-h10-paper-governance` against existing H10 artifacts. | Parser/unit tests plus `bash scripts/run-shortpick-v2-h10-paper-governance.sh`, which regenerates prerequisite H10 replay, parameter-significance, robustness, execution, and rank-ablation artifacts, builds governance evidence, validates it, and verifies the durable doc marker. | CLI governance command | none | matches_product_path | Runner exits 0, writes `output/shortpick-v2-h10-paper-governance-artifact.json`, writes the published durable artifact copy under `docs/archive/`, validates the artifact, and verifies the archive doc marker. |
| PF-002 | Future V2 paper ledger rows are accepted or rejected through the paper-tracking ledger schema and read model. | Jsonschema and read-model tests with H10 fixed85/fixed80 rows, plus fixed90 rejection tests. | Paper ledger contract/read model | controlled fixture ledger rows, because no true-forward H10 ledger exists yet | controlled_simulation | Tests prove H10 candidate IDs are allowed for future rows, fixed90 is blocked, and delayed actions are rejected. |
| PF-003 | User-visible `/shortpick-lab-v2/paper-tracking` reads prepared artifacts and must not synthesize paper rows from historical replay. | TestClient API/read-model tests with missing ledger and governance artifact present, plus served verification after runtime publish. | FastAPI V2 paper-tracking read model | env vars point tests to temp artifacts; artifact resolver itself is exercised, and published docs artifact covers runtime path | controlled_simulation | API payload has zero records, true-forward evidence basis, governance status, no historical-row fallback. |
| PF-004 | Runtime deployment serves the committed backend/frontend behavior after live-facing code changes. | `bash scripts/verify-shortpick-v2-h10-paper-governance-runtime.sh` runs default gates, requires a clean committed worktree, publishes with refresh skipped, and verifies the served V2 paper-tracking API governance state. | Runtime publish script and LaunchAgent services | none | matches_product_path | Verification script exits 0 after publish and served API checks confirm H10 governance state with zero historical paper rows. |

## Scope

### In Scope

- Add a schema-backed H10 paper-governance artifact and validator.
- Add CLI support to build and validate the H10 paper-governance artifact from regenerated H10 rank-ablation, parameter-significance, robustness, and execution evidence artifacts.
- Record source robustness `not_ready_for_paper_tracking`, high-risk flags, and prior durable no-promotion decision as explicit governance inputs with forward-observation-only disposition.
- Update paper-tracking contract/schema/read-model tests so fixed85 and fixed80 can be future forward-observation paper configs, while fixed90 remains diagnostic-only.
- Expose governance state in the V2 paper-tracking read model without writing historical ledger rows.
- Generate real local governance evidence from the runtime DB/artifacts and record the decision in durable docs.
- Add repeatable scripts for real governance evidence generation and live-facing runtime verification.
- Run focused tests, policy-sensitive checks required by hooks, external reviews, runtime publish, and served verification appropriate for live-facing changes.

### Out of Scope

- No historical paper-ledger backfill.
- No buy-delay rule.
- No fixed90 promotion or turnover-gate weakening.
- No broad strategy search, new rank widening, dynamic exit, ma-accel, entry-quality rerank, or pool-hot relaxation.
- No portfolio recommendation, investment advice, production trading claim, or automated order path.
- No parameter-search UI.

## Assumptions and Dependencies

- The runtime SQLite DB at `/Users/hernando_zhao/codex/runtime/projects/ashare-dashboard/data/ashare_dashboard.db` is the local real-data source for H10 artifact regeneration.
- H10 horizon remains fixed at 10 trading days based on prior V1/V2 evidence and is not reopened here.
- The H10 fixed85 primary and fixed80 capital-shadow IDs are the only forward-observation candidates in this governance plan.
- A true-forward writer may be built later, but this plan must not create fake paper rows to simulate it.
- Schema and read-model changes are live-facing and therefore require a clean committed source tree, runtime publish, and served verification before closeout.
- The durable governance artifact must be copied into a published source path, not only `output/`, because the publish script excludes `output/`.
- The existing completed robustness plan still sitting under `plans/active` is stale hygiene debt; this plan does not depend on executing it again.

## Work Items

| ID | Status | Order | Depends On | Task | Deliverable | Acceptance Type | Acceptance Spec | Evidence |
|----|--------|-------|------------|------|-------------|-----------------|-----------------|----------|
| W-001 | done | 1 | - | Add the H10 paper-governance artifact contract, builder, validator, CLI entrypoints, and repeatable generation/verification scripts. | `src/ashare_evidence/shortpick_v2_h10_paper_governance.py`, schema, CLI parser/main handlers, `scripts/run-shortpick-v2-h10-paper-governance.sh`, `scripts/verify-shortpick-v2-h10-paper-governance-runtime.sh`, focused tests | test_pass | cmd:bash -n scripts/run-shortpick-v2-h10-paper-governance.sh && bash -n scripts/verify-shortpick-v2-h10-paper-governance-runtime.sh && PYTHONPATH=src python3 -m pytest -q tests/test_shortpick_v2_h10_paper_governance.py tests/test_shortpick_v2_h10_artifact_validation.py | W-001 gate passed: `20 passed in 0.84s`; `ruff check` passed; MiMo code review PASS; Codex escalation code review PASS after candidate-boundary and return self-certification fixes. |
| W-002 | done | 2 | W-001 | Update V2 paper-tracking contract/schema/read model so H10 fixed85/fixed80 can be future ledger configs while fixed90 and delayed-entry remain blocked. | Paper contract/schema/read-model/test updates with governance state and zero-row missing-ledger projection | test_pass | cmd:PYTHONPATH=src python3 -m pytest -q tests/test_shortpick_v2_paper_tracking_contract.py tests/test_shortpick_v2_read_model_api.py | W-002 gate passed: `17 passed in 1.43s`; combined W-001/W-002 gate passed: `28 passed in 1.39s`; related ruff passed; MiMo final code review PASS; Codex escalation code review PASS after ledger schema validation, required ledger policy, and delayed-entry test fixes. |
| W-003 | done | 3 | W-001,W-002 | Generate real H10 paper-governance evidence from the runtime DB and regenerated H10 artifacts, then record the durable governance decision. | `output/shortpick-v2-h10-paper-governance-artifact.json`, `docs/archive/SHORTPICK_LAB_V2_H10_PAPER_GOVERNANCE_ARTIFACT_2026-06-15.json`, and archive doc update | command_exit_0 | cmd:bash scripts/run-shortpick-v2-h10-paper-governance.sh | W-003 acceptance passed: regenerated H10 replay/selection/parameter-significance/rank-ablation/robustness/execution artifacts from runtime DB, validated source artifacts with 25 checks and 0 failures, built and validated governance artifacts with 32 checks and 0 failures, wrote the docs/archive artifact copy, and verified the durable marker. Artifact summary: fixed85/fixed80 future-observation-only candidates, fixed90 diagnostic-only, zero true-forward rows, no backfill/no delayed buy, `research_observation`; MiMo and Codex artifact reviews PASS after marker punctuation and W-004 wording minors were fixed. |
| W-004 | done | 4 | W-001,W-002,W-003 | Run closeout gates, publish committed live-facing changes to runtime, and verify the served V2 paper-tracking governance state. | Focused/default gate evidence, runtime publish evidence, served API verification, archived plan/run docs | command_exit_0 | cmd:bash scripts/verify-shortpick-v2-h10-paper-governance-runtime.sh | W-004 acceptance passed from clean committed tree after declaring/installing the `jsonschema` runtime dependency: default pytest `911 passed, 173 deselected, 6 subtests passed`, policy audit `status=pass`, frontend build succeeded, runtime publish succeeded, deploy verification `19 passed, 0 failed`, and served `/shortpick-lab-v2/paper-tracking/summary` returned zero rows with fixed85/fixed80 candidates and fixed90 diagnostic rejection. |

## Acceptance Criteria & Validation Gates

### Overall Acceptance Criteria

- The H10 fixed85 benchmark is recorded as the primary future-observation candidate, and fixed80 is recorded as the capital-shadow future-observation candidate.
- The governance artifact proves market outperformance and annualized return at or above 30% before granting future-observation eligibility.
- The governance artifact records source robustness `not_ready_for_paper_tracking`, high-risk flags, and the prior durable no-promotion decision, then gives a forward-observation-only disposition with no historical paper-performance claim.
- The governance artifact consumes parameter-significance evidence or fails validation when that source is missing.
- The artifact and docs explicitly say historical replay is not true-forward paper performance.
- Fixed90 remains diagnostic-only and cannot appear in active paper-ledger rows under this plan.
- V2 paper-tracking projection can expose governance readiness while returning zero records when no true-forward ledger exists.
- The implementation is reviewed by MiMo and Codex escalation because schema contracts and governance state are touched.
- Live-facing changes are published and verified from the real served runtime before final closeout.

### Validation Gates

- `python3 $CODEX_HOME/skills/reviewed-plan-generator/scripts/validate_plan.py plans/active/plan-20260615-h10-paper-governance.md`
- MiMo plan review and Codex escalation plan review report no unresolved blocking findings.
- MiMo run-plan/code review and Codex escalation run/code review report no unresolved blocking findings.
- `bash -n scripts/run-shortpick-v2-h10-paper-governance.sh`
- `bash -n scripts/verify-shortpick-v2-h10-paper-governance-runtime.sh`
- `PYTHONPATH=src python3 -m pytest -q tests/test_shortpick_v2_h10_paper_governance.py tests/test_shortpick_v2_h10_artifact_validation.py`
- `PYTHONPATH=src python3 -m pytest -q tests/test_shortpick_v2_paper_tracking_contract.py tests/test_shortpick_v2_read_model_api.py`
- `bash scripts/run-shortpick-v2-h10-paper-governance.sh` regenerates H10 evidence, builds and validates the paper-governance artifact, writes the published docs artifact copy, and verifies the durable doc marker with explicit failure messages.
- `bash scripts/verify-shortpick-v2-h10-paper-governance-runtime.sh` runs default `pytest`, policy audit, requires a clean committed worktree, publishes with refresh skipped, and verifies the served V2 paper-tracking API.
- Runtime publish with refresh skipped succeeds and served V2 paper-tracking verification confirms governance state without historical paper rows.

## Risks and Mitigations

- Risk: H10 historical performance is mistaken for true-forward paper performance. Mitigation: artifact evidence basis remains historical governance evidence, paper ledger evidence basis remains true-forward only, source `not_ready_for_paper_tracking` and high-risk flags are preserved, and read model returns zero records until a ledger exists.
- Risk: fixed90 headline return tempts turnover-gate weakening. Mitigation: schema, validator, and docs mark fixed90 diagnostic-only and reject fixed90 paper rows.
- Risk: read-model tests use fixture artifacts that do not match runtime behavior. Mitigation: pair fixture tests with a runtime artifact generation command and served API verification after publish.
- Risk: schema changes break older June 12 V2 artifacts. Mitigation: preserve old config IDs and add H10 IDs without deleting legacy compatibility.
- Risk: plan/run state becomes unrecoverable after context compaction. Mitigation: use schema-v1 plan, run docs, state files, archived run records, and durable docs.
- Risk: runtime publish encounters the known 5173 service outage pattern. Mitigation: use the project publish script, then verify served output; if the service is down, repair the runtime service before claiming closeout.

## Open Questions

- None for execution. Fixed90 promotion, true-forward writer implementation, and a future parameter-search UI require separate user decisions.

## Revision History

| Round | Date | Change | Author |
|-------|------|--------|--------|
| 0 | 2026-06-15 | Initial draft for H10 paper governance generation-through-landing workflow. | Codex |
| 1 | 2026-06-15 | Accepted MiMo and Codex review findings by binding real artifact generation, runtime publish, and served verification into executable acceptance scripts; clarified published docs artifact path because runtime publish excludes `output/`. | Codex |
| 2 | 2026-06-15 | Recorded MiMo and Codex round 2 PASS and marked the plan approved for execution under the user's generation-through-landing instruction. | Codex |
| 2 | 2026-06-15 | Started plan-run-loop execution for W-001; plan status changed to executing and W-001 to in_progress. | Codex |
| 3 | 2026-06-15 | Accepted W-001 run-plan review findings: governance must preserve prior no-promotion/risk-flag disposition, consume parameter-significance evidence, and add script syntax gates. | Codex |
| 4 | 2026-06-15 | Completed W-001: added H10 paper-governance artifact/schema/CLI/scripts/tests, fixed code-review blockers for exact fixed85/fixed80 candidates and summary-backed return gates, and recorded MiMo/Codex PASS evidence. | Codex |
| 5 | 2026-06-15 | Started W-002 plan-run-loop execution; W-002 status changed to in_progress after W-001 archive. | Codex |
| 6 | 2026-06-15 | Completed W-002: exposed H10 fixed85/fixed80 governance readiness with zero missing-ledger records, added schema-backed ledger validation, required ledger policy, fixed90 and delayed-entry fail-closed coverage, and recorded MiMo/Codex PASS evidence. | Codex |
| 7 | 2026-06-15 | Started W-003 plan-run-loop execution; W-003 status changed to in_progress after W-002 archive. | Codex |
| 8 | 2026-06-15 | Completed W-003: generated real H10 paper-governance evidence from runtime DB, published the docs/archive governance artifact copy, verified the durable marker, fixed review minors, and recorded MiMo/Codex PASS evidence. | Codex |
| 9 | 2026-06-15 | Started W-004 plan-run-loop execution; W-004 status changed to in_progress after W-003 archive. | Codex |
| 10 | 2026-06-15 | Completed W-004: fixed runtime dependency declaration, ran clean-tree runtime publish, verified deploy checks and served paper-tracking governance summary, and recorded MiMo/Codex PASS evidence. | Codex |
| 11 | 2026-06-15 | Archived completed full-plan document from `plans/active/` to `plans/archive/` after all work items passed. | Codex |

## External Review Log

| Round | Reviewer | Finding | Severity | Disposition | Reason | Affected IDs |
|-------|----------|---------|----------|-------------|--------|--------------|
| 1 | MiMo | W-004 acceptance spec did not include runtime publish or served verification despite PF-004 and deliverable requiring them. | blocking | accepted | Replaced W-004 acceptance with `scripts/verify-shortpick-v2-h10-paper-governance-runtime.sh`, which must run default gates, require clean committed source, publish with refresh skipped, and verify served API governance state. | W-004,PF-004 |
| 1 | MiMo | W-003 acceptance only validated an existing artifact and grepped docs; it did not prove real generation or clearly validate archive doc creation. | major | accepted | Replaced W-003 acceptance with `scripts/run-shortpick-v2-h10-paper-governance.sh`, which must regenerate H10 artifacts, build governance output, copy the published docs artifact, validate it, and verify the archive marker with explicit messages. | W-003,PF-001 |
| 1 | MiMo | W-003 chained validation and doc grep made failure attribution ambiguous. | major | accepted | The generation runner must provide explicit step labels and failure messages; W-003 now delegates the multi-step gate to that script. | W-003 |
| 1 | MiMo | PF-001 mentioned the generation CLI, but no work item acceptance proved the generation command. | minor | accepted | W-003 generation runner now covers the production generation command and validation. | PF-001,W-003 |
| 1 | MiMo | PF-002/PF-003 controlled simulation mitigation depended on W-004 served verification, which was missing. | minor | accepted | W-004 served verification is now an executable acceptance script. | PF-002,PF-003,W-004 |
| 1 | MiMo | W-004 all-tests gate could be noisy if the default suite has known failures. | minor | rejected | Project AGENTS and pre-push contract require default fast pytest for code changes; no known default-suite failure is currently accepted as baseline. | W-004 |
| 1 | MiMo | SRC-009 review evidence path was vague. | note | accepted | SRC-009 evidence now names plan, per-hop run docs, and closeout notes with blocking-finding disposition requirements. | SRC-009 |
| 1 | Codex | W-003 did not prove real artifact generation and could pass only after an unproven side path created the file. | blocking | accepted | W-003 now uses a generation runner that includes the real CLI generation path before validation. | W-003,PF-001 |
| 1 | Codex | W-004 did not bind publish and served API verification into concrete acceptance evidence. | blocking | accepted | W-004 now uses a runtime verification script that includes publish and served API checks. | W-004,PF-004 |
| 1 | Codex | Draft lifecycle, zero review rounds, and empty review log make the plan non-executable until dispositions are recorded and status advances. | blocking | accepted | Review dispositions are recorded in round 1; status remains draft for re-review and will advance to reviewed/approved only after review passes. | plan-lifecycle |
| 2 | MiMo | Round 1 concerns are closed; W-003 and W-004 now bind real generation, docs artifact, runtime publish, and served verification into executable acceptance. | note | accepted | No blocking, major, or material issues remain. | W-003,W-004,PF-001,PF-004 |
| 2 | Codex | Round 1 blockers are closed; plan validation passes and lifecycle can move into reviewed/approved. | note | accepted | No blocking or material issues remain. | W-003,W-004,plan-lifecycle |
| 3 | Codex | W-001 could bypass the existing `not_ready_for_paper_tracking` and prior no-promotion boundary if it only checked return gates. | blocking | accepted | W-001 now requires the artifact/schema/validator to record source robustness recommendation, risk flags, prior durable decision reference, and forward-observation-only disposition with no historical paper claim. | W-001,SRC-002,SRC-005,SRC-008 |
| 3 | Codex | W-001 source coverage missed parameter-significance even though the main plan names it as a key dependency. | major | accepted | Parameter-significance is now a required W-001 input for builder/CLI/schema/source refs/validator and W-003 regeneration. | W-001,PF-001 |
| 3 | Codex | W-001 acceptance did not prove the two generated scripts are syntactically valid. | major | accepted | W-001 acceptance now includes `bash -n` for both generation and runtime verification scripts before focused pytest. | W-001,PF-001,PF-004 |
| 3 | MiMo | W-002 final evidence review found no blocker, major, or minor issues after fixes; H10 governance remains zero-row metadata and fixed90/delayed entries fail closed. | note | accepted | W-002 code review PASS recorded in run doc and plan evidence. | W-002,PF-002,PF-003 |
| 3 | Codex | W-002 initially accepted schema-invalid ledger fixtures and left `row_contract.ledger_policy` optional; delayed-entry read-model coverage was missing. | major | accepted | Added JSON Schema validation in the read model, required `ledger_policy`, converted the fixture to schema-valid, and added read-model fixed90/delayed-action rejection tests. Codex re-review reported no remaining blocker/major/minor. | W-002,PF-002,PF-003 |
| 3 | MiMo | W-003 run-plan and artifact reviews found no blocker or major issues; artifact and docs satisfy fixed85/fixed80 future-observation-only, fixed90 diagnostic-only, zero true-forward rows, no backfill/no delayed buy, and research-only constraints. | minor | accepted | Marker punctuation ambiguity was fixed so the durable marker line exactly contains `H10 paper governance; future true-forward only; fixed90 diagnostic only`. | W-003,PF-001 |
| 3 | Codex | W-003 artifact review found no blocker or major issues, but noted the champion doc wording preclaimed W-004 reran the robustness path before W-004 had executed. | minor | accepted | Updated the durable champion doc to say the benchmark-focused robustness path was run without preclaiming W-004 runtime publish/served verification. | W-003,PF-001,PF-004 |
| 3 | MiMo | W-004 run-plan review required explicit PF-003 TestClient/read-model evidence attribution; final code/artifact review found no blocker or major issues. | major | accepted | W-004 run doc now states PF-003 is covered by default pytest including `tests/test_shortpick_v2_read_model_api.py`; final sharded review passed. | W-004,PF-003,PF-004 |
| 3 | Codex | W-004 run-plan review found served verification needed exact fixed85/fixed80 candidate matching and fixed90 candidate exclusion; final code review passed. | major | accepted | Runtime verification script now requires exact candidate IDs, rejects fixed90 in candidates, and refuses non-`skip` refresh mode. | W-004,PF-004,SRC-006 |

## User Review Notes

- User requested no approval prompts during execution and explicitly asked to run the governance plan from generation through landing.
- This 2026-06-15 instruction is treated as approval to execute the reviewed plan.

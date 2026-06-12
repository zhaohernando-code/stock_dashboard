# Short Pick Lab V2 Backend Read Model Run

Status: Completed and archived after Phase 6 implementation
Owner: stock_dashboard
Created: 2026-06-12
Source plan: `docs/contracts/SHORTPICK_LAB_V2_PLAN_2026-06-12.md`

## Objective

Implement Phase 6 of the Short Pick Lab V2 plan: add separate backend read APIs for `试验田v2` without mixing v1 Short Pick Lab semantics.

The read model must support the two planned v2 user-facing modules:

| Module | Backend contract |
| --- | --- |
| 纸面追踪 | Return a v2 paper-tracking read model anchored to the Phase 5 contract and Phase 4 selected configs. If no true-forward v2 ledger artifact exists yet, return a contract-ready empty projection instead of inferring rows from v1. |
| 历史回放 | Return a summarized read model from the precomputed Phase 3 replay artifact and Phase 4 rule-selection artifact. |

## Scope

| Area | Planned change |
| --- | --- |
| Read-model service | Add a v2-specific read-model module that loads and validates precomputed v2 artifacts. |
| API routes | Add separate `shortpick-lab-v2` read endpoints for paper tracking and historical replay. |
| Response schema | Add v2 response models with research labels, source artifact refs, selected configs, summaries, and bounded samples. |
| Tests | Cover successful artifact-backed replay reads, contract-ready empty paper tracking, artifact fail-closed behavior, and route registration. |
| Plan status | Update Phase 6 status after implementation evidence exists, then archive this run document. |

## Non-Scope

| Non-scope | Boundary |
| --- | --- |
| Frontend tab | Phase 7 only. No React, CSS, or frontend API client changes in this run. |
| Paper ledger writer | No creation, backfill, mutation, or refresh of v2 paper rows. |
| Dynamic replay | API/page reads must not run `shortpick-v2-replay` or fetch market data. |
| v1 paper ledger reuse | V2 paper tracking must not infer account state from `/shortpick-lab/paper-tracking`. |
| Parameter UI | No exposed parameter grid or config mutation. |
| Production claims | Keep `claim_ceiling=research_observation` and paper/research language. |

## Intended API Shape

| Endpoint | Purpose |
| --- | --- |
| `GET /shortpick-lab-v2/paper-tracking` | Full v2 paper tracking read model. |
| `GET /shortpick-lab-v2/paper-tracking/summary` | Same contract without row payloads. |
| `GET /shortpick-lab-v2/historical-replay` | Summarized Phase 3/4 historical account replay read model with bounded decision samples. |

Artifact paths should be configurable by environment variables and fall back to the current runtime `output/` artifact names:

| Artifact | Environment variable | Runtime fallback |
| --- | --- | --- |
| Replay artifact | `ASHARE_SHORTPICK_V2_REPLAY_ARTIFACT` | `output/shortpick-v2-replay-artifact-20260612.json` |
| Rule-selection artifact | `ASHARE_SHORTPICK_V2_RULE_SELECTION_ARTIFACT` | `output/shortpick-v2-rule-selection-artifact-20260612.json` |
| Paper ledger artifact | `ASHARE_SHORTPICK_V2_PAPER_TRACKING_LEDGER_ARTIFACT` | `output/shortpick-v2-paper-tracking-ledger.json` |

Missing required source artifacts should fail closed with the existing artifact-read API error style. Loaded artifacts should be checked against their declared family, schema version, status, evidence basis, claim ceiling, and role/config constraints before any successful read-model response.

The contract-ready empty paper projection should still return the eligible selected and baseline config list from the Phase 4 selection artifact, so the frontend can display "selected but no true-forward rows yet" without deriving rows from v1.

Top-level research labeling fields should include `claim_ceiling`, `evidence_basis`, `ui_language`, and `data_disclaimer`.

The paper-tracking read model must keep `2026-05-08` as the explicit tracking start anchor in both empty and ledger-backed projections.

## Acceptance

| Rule | Status | Evidence target |
| --- | --- | --- |
| Separate semantic domain | Done | Routes use `shortpick-lab-v2` and v2 read-model helpers only. |
| Historical replay is precomputed | Done | Historical endpoint reads Phase 3/4 JSON artifacts and does not call replay generation or market-data refresh. |
| Paper tracking does not fake rows | Done | Missing v2 ledger returns contract-ready empty records, not v1-derived rows. |
| Start anchor preserved | Done | Paper-tracking responses keep the Phase 5 `2026-05-08` tracking start date. |
| No delayed-buy action introduced | Done | API projection keeps allowed actions from the Phase 5 contract and does not add delayed-entry fields. |
| Research labeling preserved | Done | Responses expose `claim_ceiling=research_observation` and paper/research labels. |
| Schema validation on load | Done | Loaded v2 artifacts are checked against the declared v2 schema family/version and hard semantic constraints before success responses. |
| Historical replay fail-closed | Done | Missing or invalid replay/selection artifacts return the same non-success fail-closed API style. |
| Fail closed | Done | Missing/invalid required artifacts return non-success API status instead of partial silent success. |
| Focused tests pass | Done | New v2 read-model/API tests pass. |
| Required project gates pass | Done | Default fast pytest and policy audit pass before merge. |

## Review Plan

MiMo should review this run plan before implementation for drift against:

- `docs/contracts/SHORTPICK_LAB_V2_PLAN_2026-06-12.md`
- `docs/contracts/SHORTPICK_LAB_V2_PAPER_TRACKING_CONTRACT_2026-06-12.md`
- Phase 3 replay and Phase 4 selection artifact contracts

After implementation, MiMo should review the code for semantic mixing, dynamic replay risk, overclaiming, and route/API boundary drift.

## Closeout Evidence

| Evidence | Result |
| --- | --- |
| MiMo run-plan review | PASS; no blocking drift. Suggestions on schema checks, config list, env var names, and research labels were incorporated before implementation. |
| MiMo post-implementation review | PASS; no blocking drift. Suggestions on paper-ledger positive-path test and explicit `2026-05-08`/fail-closed run text were incorporated. |
| Focused v2 suite | `python3 -m pytest -q tests/test_shortpick_v2_replay.py tests/test_shortpick_v2_rule_selection.py tests/test_shortpick_v2_paper_tracking_contract.py tests/test_shortpick_v2_read_model_api.py` -> 22 passed. |
| Default fast regression | `python3 -m pytest -q` -> 806 passed, 1 skipped, 171 deselected, 6 subtests passed. |
| Policy audit | `PYTHONPATH=src python3 -m ashare_evidence.cli policy-audit --fail-on-new-unclassified --fail-on-direct-config-read --fail-on-formula-side-effects --fail-on-missing-config-lineage` -> pass. |
| Merge status | Pending until branch is fast-forwarded into `main` and pushed. |

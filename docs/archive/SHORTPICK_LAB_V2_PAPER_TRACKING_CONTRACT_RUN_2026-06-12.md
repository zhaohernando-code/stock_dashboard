# Short Pick Lab V2 Paper Tracking Contract Run

Status: Completed and archived after Phase 5 implementation
Owner: stock_dashboard
Created: 2026-06-12
Source plan: `docs/contracts/SHORTPICK_LAB_V2_PLAN_2026-06-12.md`
Source selection artifact: `/Users/hernando_zhao/codex/runtime/projects/ashare-dashboard/output/shortpick-v2-rule-selection-artifact-20260612.json`
Target phase: Phase 5 - Paper tracking contract

## Goal

Define the forward `试验田v2` paper-tracking contract: ledger semantics, row shape, start-window policy, allowed actions, account-state fields, and evidence labels for the selected Phase 4 configurations.

This run should complete the plan's Phase 5 outcome: define forward v2 ledger semantics starting from the v1-aligned tracking window. It should not write paper-tracking rows, backfill ledger data, add backend APIs, add frontend tabs, refresh market data, call models, or start services.

## Alignment Constraints

| Constraint | Run interpretation |
| --- | --- |
| Paper-tracking alignment | The contract must use the v1-aligned planning start window, currently `2026-05-08`, and explicitly record any source gaps instead of silently shifting start dates. |
| Separate semantic domain | Define a v2-specific paper ledger schema and contract; do not retrofit or write the existing Short Pick Lab paper ledger. |
| No delayed entry | Signal-day decisions remain `buy_primary`, `buy_fallback`, or `skip`; if declared entry cannot be executed, the row must record fallback or skip, not a later discretionary buy. |
| Account realism | Ledger rows must carry cash, quantity, board-lot, position, entry, exit, and reason fields sufficient to reconstruct the account path. |
| Historical-first promotion | Only Phase 4 selected configs can be eligible for the first v2 paper contract; baseline/control rows may be tracked separately if explicitly labeled. |
| Research labeling | Contract and schema must label v2 paper tracking as research/paper evidence only, not production trading or investment advice. |
| Efficiency boundary | Future API/UI should read prepared v2 ledger/projection data; this phase defines the contract and does not implement dynamic page computation. |

## Selected Config Scope

The first paper contract should carry these Phase 4-selected configurations:

| Role | Config ID |
| --- | --- |
| Phase 5 contract candidate | `conservative_cash_reserve_60k_top5_v1` |
| Phase 5 contract candidate | `fixed_notional_40k_top5_v1` |
| Baseline/control | `top1_or_skip_v1` |

`top3_fallback_v1` remains a holdout and `position_cap_utilization_top5_v1` remains rejected by Phase 4. They should not appear as active Phase 5 candidates unless a later governed artifact changes that decision.

## Files To Change

| File | Action | Purpose |
| --- | --- | --- |
| `docs/contracts/SHORTPICK_LAB_V2_PAPER_TRACKING_CONTRACT_2026-06-12.md` | Add | Human-readable contract for v2 paper tracking semantics and non-goals. |
| `docs/contracts/registry/schemas/shortpick_v2_paper_tracking_ledger.schema.json` | Add | Machine-readable ledger artifact and row schema. |
| `tests/test_shortpick_v2_paper_tracking_contract.py` | Add | Validate schema examples, reject delayed entry, and assert key contract markers. |
| `docs/contracts/SHORTPICK_LAB_V2_PLAN_2026-06-12.md` | Update at closeout | Mark Phase 5 as Done only after contract/schema/tests/review/gates pass. |
| `docs/contracts/SHORTPICK_LAB_V2_PAPER_TRACKING_CONTRACT_RUN_2026-06-12.md` | Move at closeout | Archive this run plan under `docs/archive/` after implementation and review. |

## Implementation Steps

1. Add the human-readable contract.
   - Define paper-tracking scope, source selection artifact, selected configs, baseline/control behavior, and start date policy.
   - Define row lifecycle: signal decision, entry, holding/marking, exit, and blocked/missing data states.
   - Define action taxonomy and explicitly forbid delayed entry.
   - Define source-gap behavior: record `source_gap`/`not_observed` states instead of shifting the start window.
   - Define research labels and UI/API read-only expectations for later phases.

2. Add the ledger schema.
   - Top-level artifact should include metadata, source selection artifact, tracking window, selected configs, account contract, row contract, records, summary, leakage audit, and research labeling.
   - Row schema should require config ID, signal date, decision date, action, reason, selected rank, symbol, entry trade date, quantity, cash before/after, position state, and evidence basis.
   - Action enum must exclude delayed entry.

3. Add focused tests.
   - Validate a minimal empty contract ledger artifact.
   - Validate a buy row and a skip row.
   - Prove `delay_buy` or any later-entry action is schema-invalid.
   - Assert the contract document includes `2026-05-08`, selected config IDs, and no-DB-write/no-API/no-frontend boundary language.

4. Run post-implementation review and local gates.
   - Ask MiMo to review code/document risk and whether final changes drift from this run plan.
   - Run targeted pytest for the new contract tests.
   - Run default fast pytest and policy audit before push.

5. Close out.
   - Mark Phase 5 as Done in the main v2 plan with contract/schema references.
   - Archive this run document under `docs/archive/`.
   - Merge to `main`, push to `origin/main`, then remove this worktree and temporary prompt files.

## Validation Plan

| Check | Purpose |
| --- | --- |
| MiMo pre-implementation review | Confirm this run plan does not drift from Phase 5. |
| Focused pytest | Confirm schema examples and no-delayed-entry rejection. |
| MiMo post-implementation review | Confirm contract/schema risk and drift from this run plan. |
| Project pre-push hook | Run default fast regression and policy audit before push. |

## Out Of Scope

| Out-of-scope item | Reason |
| --- | --- |
| Writing v2 paper-tracking rows | This phase defines the contract only; writing begins in a later implementation after read model boundaries are clear. |
| Backfilling historical replay as paper tracking | Would mix historical replay evidence with true forward tracking. |
| Backend read API | Belongs to Phase 6. |
| Frontend `试验田v2` tab | Belongs to Phase 7. |
| Runtime publish | No live-facing code or UI is being activated in this phase. |
| DB writes, refreshes, model calls, or server startup | Phase 5 contract work is documentation/schema/test only. |

## Completion Criteria

| Criterion | Status |
| --- | --- |
| Run plan reviewed by MiMo with no blocking plan-drift issue | Done |
| Human-readable paper tracking contract added | Done |
| Ledger schema added | Done |
| Focused tests added and passing | Done |
| Post-implementation MiMo review has no blocking issue | Done |
| Default fast pytest and policy audit pass | Done |
| Main v2 plan Phase 5 updated to Done with contract/schema references | Done |
| Run document archived | Done |
| Branch merged to `main`, pushed to `origin/main`, and worktree cleaned | Pending until final git closeout after this archive is committed |

## Closeout Evidence

| Evidence | Result |
| --- | --- |
| MiMo run-plan review | No blocking drift from the v2 plan Phase 5. |
| Focused pytest | `python3 -m pytest -q tests/test_shortpick_v2_paper_tracking_contract.py` passed: 5 passed. |
| Contract document | Added `docs/contracts/SHORTPICK_LAB_V2_PAPER_TRACKING_CONTRACT_2026-06-12.md`. |
| Ledger schema | Added `docs/contracts/registry/schemas/shortpick_v2_paper_tracking_ledger.schema.json`. |
| Contract assertions | Tests validate empty ledger, buy row, skip row, delayed-entry rejection, unselected-config rejection, and required boundary text. |
| MiMo post-implementation review | Sharded read-only review completed; result: no blocking issues. |
| Default fast regression | `python3 -m pytest -q` passed: 800 passed, 1 skipped, 171 deselected, 6 subtests passed. |
| Policy audit | `PYTHONPATH=src python3 -m ashare_evidence.cli policy-audit --fail-on-new-unclassified --fail-on-direct-config-read --fail-on-formula-side-effects --fail-on-missing-config-lineage` passed. |

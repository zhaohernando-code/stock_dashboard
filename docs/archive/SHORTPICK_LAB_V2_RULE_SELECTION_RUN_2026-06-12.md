# Short Pick Lab V2 Rule Selection Run

Status: Completed and archived after Phase 4 implementation
Owner: stock_dashboard
Created: 2026-06-12
Source plan: `docs/contracts/SHORTPICK_LAB_V2_PLAN_2026-06-12.md`
Source replay artifact: `/Users/hernando_zhao/codex/runtime/projects/ashare-dashboard/output/shortpick-v2-replay-artifact-20260612.json`
Target phase: Phase 4 - Candidate rule selection

## Goal

Produce the first governed `shortpick_v2_rule_selection_artifact` for `试验田v2` by reading the Phase 3 replay artifact and choosing a bounded set of v2 configurations for Phase 5 paper-tracking contract design.

This run should complete the plan's Phase 4 outcome: choose a small set of v2 configurations based on replay evidence and governance rules. It should not start paper tracking, create a v2 ledger, add backend read APIs, add frontend tabs, refresh market data, call models, or write runtime DB rows.

## Alignment Constraints

| Constraint | Run interpretation |
| --- | --- |
| Historical-first promotion | Only Phase 3 replay evidence can drive the selection. No UI parameter search or ad hoc manual override is allowed. |
| Bounded promoted set | Select at most two configurations for Phase 5 contract design; keep other passing configurations as holdouts. |
| Research labeling | Selected configurations are `phase5_contract_candidate` only. They are not live paper tracking, production proof, or investment advice. |
| Separate semantic domain | Add a v2-specific selection artifact and optional schema; do not write v1 paper-tracking rows or extend existing v1 APIs. |
| Candidate quality and account path stay separate | Selection uses account-level replay metrics only; it does not reinterpret candidate-level forward returns as account NAV. |
| No delayed entry | Selection may only consume Phase 3 results whose action taxonomy excludes delayed entry. |
| Efficiency boundary | Read the existing replay JSON once and emit a small selection JSON. No market-bar reload or dynamic replay is needed. |

## Selection Policy

The first selector should be deterministic and conservative. It should fail closed if the input artifact is missing, invalid, not `shortpick_v2_replay_artifact`, not `historical_account_replay`, or does not include the required Phase 3 rule results.

Initial gate thresholds:

| Gate | Threshold | Intent |
| --- | --- | --- |
| Signal count | `>= 300` | Avoid selecting from a tiny replay window. |
| Trade count | `>= 180` | Avoid selecting rules with too few completed buys. |
| Skip ratio | `<= 0.60` | Avoid configurations that usually cannot deploy capital. |
| Total return | `> 0` | Require positive account-level historical return after costs. |
| Max drawdown | `>= -0.35` | Reject configurations with excessive account drawdown. |
| Mean invested ratio | `>= 0.25` | Avoid rules that appear safe only because they rarely invest. |
| Turnover | `<= 80` | Avoid the most churn-heavy rule variants in the initial promoted set. |
| Required reason counts | Present | Ensure buy/fallback/skip attribution exists before promotion. |

Ranking among gate-passing configurations should be risk-first:

1. Higher max drawdown value is better, meaning less negative drawdown.
2. Higher total return is better.
3. Lower skip ratio is better.
4. Lower turnover is better.
5. Higher trade count is better.

The selector should choose at most two configurations. Based on the Phase 3 artifact snapshot, the expected selected set is:

| Config | Expected role | Rationale |
| --- | --- | --- |
| `conservative_cash_reserve_60k_top5_v1` | Selected for Phase 5 contract design | Best drawdown among high-trade-count candidates, positive return, moderate utilization. |
| `fixed_notional_40k_top5_v1` | Selected for Phase 5 contract design | Strong trade count and positive return with bounded fixed-notional sizing. |

`top1_or_skip_v1` should be retained as a strict baseline/control, not promoted, because its skip ratio is too high. Passing-but-not-selected configs should remain holdouts due to the bounded-set rule.

## Files To Change

| File | Action | Purpose |
| --- | --- | --- |
| `docs/contracts/registry/schemas/shortpick_v2_rule_selection_artifact.schema.json` | Add | Define the selection artifact envelope and result rows. |
| `src/ashare_evidence/shortpick_v2_rule_selection.py` | Add | Offline selector and writer for Phase 4. |
| `src/ashare_evidence/cli.py` | Update | Add `shortpick-v2-rule-selection` to read a replay artifact and write a selection artifact. |
| `tests/test_shortpick_v2_rule_selection.py` | Add | Cover gate pass/fail, bounded selection, baseline retention, schema shape, and read-only behavior. |
| `docs/contracts/SHORTPICK_LAB_V2_PLAN_2026-06-12.md` | Update at closeout | Mark Phase 4 as Done only after implementation, post-implementation MiMo review, gates, and selection artifact generation pass. |
| `docs/contracts/SHORTPICK_LAB_V2_RULE_SELECTION_RUN_2026-06-12.md` | Move at closeout | Archive this run plan under `docs/archive/` after implementation and review. |

## Runtime Artifact

| Artifact | Policy |
| --- | --- |
| `/Users/hernando_zhao/codex/runtime/projects/ashare-dashboard/output/shortpick-v2-rule-selection-artifact-20260612.json` | Generated from the Phase 3 replay artifact; kept as Phase 4 evidence, not committed to git. |

The selector should not read the runtime SQLite database. Its only runtime input should be the Phase 3 replay JSON artifact.

## Implementation Steps

1. Add the selection artifact schema.
   - Include metadata, source replay artifact reference, selection policy version, gate thresholds, selected configs, baseline configs, holdout configs, rejected configs, and leakage/research labels.
   - Keep `claim_ceiling=research_observation` or a similarly bounded label that does not imply active paper tracking.

2. Add `shortpick_v2_rule_selection.py`.
   - Load and validate the replay artifact shape defensively.
   - Compute gate results per replay config from account-level summary metrics.
   - Retain `top1_or_skip_v1` as a baseline/control when present.
   - Rank gate-passing configs by the declared risk-first order and select at most two.
   - Emit deterministic selection, holdout, and rejection reasons.

3. Add CLI support.
   - Add `shortpick-v2-rule-selection`.
   - Include options for replay artifact path, output path, maximum selected count, and optional generated-at timestamp.
   - Default output should be an ignored `output/shortpick-v2-rule-selection-artifact.json` path.

4. Add focused tests.
   - Validate that the expected two configs are selected from a representative Phase 3 replay fixture.
   - Validate that high-skip or high-drawdown configs are rejected or held out for deterministic reasons.
   - Validate max-selected enforcement.
   - Validate baseline/control retention.
   - Validate schema-compatible envelope and no paper-tracking activation claim.

5. Generate the runtime selection artifact.
   - Read `/Users/hernando_zhao/codex/runtime/projects/ashare-dashboard/output/shortpick-v2-replay-artifact-20260612.json`.
   - Write `/Users/hernando_zhao/codex/runtime/projects/ashare-dashboard/output/shortpick-v2-rule-selection-artifact-20260612.json`.
   - Validate the generated artifact against the new schema.

6. Run post-implementation review and local gates.
   - Ask MiMo to review code risk and whether the final changes drift from this run plan.
   - Run targeted pytest for the new selection tests.
   - Run JSON/schema validation for the generated runtime selection artifact.
   - Run default fast pytest and policy audit before push.

7. Close out.
   - Mark Phase 4 as Done in the main v2 plan with the selection artifact path and chosen config IDs.
   - Archive this run document under `docs/archive/`.
   - Merge to `main`, push to `origin/main`, then remove this worktree and temporary prompt files.

## Validation Plan

| Check | Purpose |
| --- | --- |
| MiMo pre-implementation review | Confirm this run plan does not drift from Phase 4. |
| Focused pytest | Confirm selector gates, ranking, bounded selection, and baseline retention. |
| Runtime selection artifact generation | Prove Phase 4 produces fixed selection evidence from the Phase 3 replay artifact. |
| JSON Schema validation | Confirm runtime selection artifact matches its schema. |
| MiMo post-implementation review | Confirm code risk and drift from this run plan. |
| Project pre-push hook | Run default fast regression and policy audit before push. |

## Out Of Scope

| Out-of-scope item | Reason |
| --- | --- |
| New replay simulation or market-bar refresh | Phase 4 consumes the existing Phase 3 replay artifact only. |
| Forward paper tracking ledger | Belongs to Phase 5. |
| Backend read API | Belongs to Phase 6. |
| Frontend `试验田v2` tab | Belongs to Phase 7. |
| Runtime publish | No live-facing code or UI is being activated in this phase. |
| DB writes, refreshes, model calls, or server startup | Phase 4 uses existing fixed artifact data only. |

## Completion Criteria

| Criterion | Status |
| --- | --- |
| Run plan reviewed by MiMo with no blocking plan-drift issue | Done |
| Selection artifact schema added | Done |
| Offline v2 rule selector added | Done |
| CLI command added | Done |
| Focused tests added and passing | Done |
| Runtime selection artifact generated under runtime output | Done |
| Runtime selection artifact validates against schema | Done |
| Post-implementation MiMo review has no blocking issue | Done |
| Main v2 plan Phase 4 updated to Done with selected config IDs | Done |
| Run document archived | Done |
| Branch merged to `main`, pushed to `origin/main`, and worktree cleaned | Pending until final git closeout after this archive is committed |

## Closeout Evidence

| Evidence | Result |
| --- | --- |
| MiMo run-plan review | No blocking drift from the v2 plan Phase 4 or replay design boundary. |
| Focused pytest | `python3 -m pytest -q tests/test_shortpick_v2_rule_selection.py` passed: 6 passed. |
| Runtime selection artifact generation | `shortpick-v2-rule-selection` generated `/Users/hernando_zhao/codex/runtime/projects/ashare-dashboard/output/shortpick-v2-rule-selection-artifact-20260612.json` from the Phase 3 replay artifact. |
| Selected configs | `conservative_cash_reserve_60k_top5_v1`, `fixed_notional_40k_top5_v1`. |
| Baseline / holdout / rejected | Baseline: `top1_or_skip_v1`; holdout: `top3_fallback_v1`; rejected: `position_cap_utilization_top5_v1`. |
| Schema validation | Runtime selection artifact validates against `docs/contracts/registry/schemas/shortpick_v2_rule_selection_artifact.schema.json`. |
| MiMo post-implementation review | Sharded read-only review completed; result: no blocking issues. |
| Default fast regression | `python3 -m pytest -q` passed: 795 passed, 1 skipped, 171 deselected, 6 subtests passed. |
| Policy audit | `PYTHONPATH=src python3 -m ashare_evidence.cli policy-audit --fail-on-new-unclassified --fail-on-direct-config-read --fail-on-formula-side-effects --fail-on-missing-config-lineage` passed. |

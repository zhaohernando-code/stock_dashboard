# Short Pick Lab V2 Replay Artifact Run

Status: Completed and archived after Phase 3 implementation
Owner: stock_dashboard
Created: 2026-06-12
Source plan: `docs/contracts/SHORTPICK_LAB_V2_PLAN_2026-06-12.md`
Design contract: `docs/contracts/SHORTPICK_LAB_V2_REPLAY_DESIGN_2026-06-12.md`
Target phase: Phase 3 - Replay artifact generation

## Goal

Produce the first fixed historical `shortpick_v2_replay_artifact` for `试验田v2` and add the reproducible offline generator that creates it.

This run should complete the plan's Phase 3 outcome: produce fixed historical results for selected rule families over adequate data. It should not select promoted strategies, add paper tracking, add backend APIs, add frontend tabs, write runtime DB rows, or publish live-facing code.

## Alignment Constraints

| Constraint | Run interpretation |
| --- | --- |
| Separate semantic domain | Add a v2-specific generator and artifact family; do not extend v1 paper-tracking or replay API responses. |
| Historical-first promotion | Generate replay evidence only; do not mark any rule as promoted or paper-tracking eligible beyond schema-level gate output. |
| No delayed entry | The simulator can only emit `buy_primary`, `buy_fallback`, or `skip`; no delayed or discretionary later-day entry path. |
| Account realism | Model initial cash, board-lot rounding, position caps, cash reserve, limit-up entry block, cash release, and mechanical exits. |
| Efficiency boundary | Load fixed market series once per replay build and reuse candidate pools across rule configurations. |
| Research labeling | Keep `claim_ceiling=research_observation` unless a later phase explicitly promotes a configuration. |

## Files To Change

| File | Action | Purpose |
| --- | --- | --- |
| `src/ashare_evidence/shortpick_v2_replay.py` | Add | Offline v2 replay artifact builder and writer. |
| `src/ashare_evidence/cli.py` | Update | Add a `shortpick-v2-replay` CLI command to generate the artifact. |
| `tests/test_shortpick_v2_replay.py` | Add | Unit tests for action taxonomy, board-lot/account behavior, schema shape, and writer behavior. |
| `docs/contracts/SHORTPICK_LAB_V2_PLAN_2026-06-12.md` | Update at closeout | Mark Phase 3 as Done only after implementation, post-implementation MiMo review, gates, and artifact generation pass. |
| `docs/contracts/SHORTPICK_LAB_V2_REPLAY_ARTIFACT_RUN_2026-06-12.md` | Move at closeout | Archive this run plan under `docs/archive/` after implementation and review. |

## Runtime Artifact

| Artifact | Policy |
| --- | --- |
| `/Users/hernando_zhao/codex/runtime/projects/ashare-dashboard/output/shortpick-v2-replay-artifact-20260612.json` | Generated from the runtime SQLite database with the worktree CLI; kept as the Phase 3 evidence artifact, not committed to git. |

The artifact should use the runtime database as the source of current fixed market data. It should not refresh market data, call models, start servers, or write DB rows.

## Implementation Steps

1. Add `shortpick_v2_replay.py`.
   - Reuse existing fixed daily-series loading and account eligibility helpers.
   - Build one deterministic ranked candidate pool per signal day from the low-turnover uptrend strategy family.
   - Reuse loaded market series and candidate pools across all v2 rule configurations.
   - Simulate account-level actions, positions, cash, exits, NAV, skipped signals, and reason counts.
   - Emit an artifact matching `shortpick_v2_replay_artifact.schema.json`.

2. Add the bounded initial rule matrix.
   - Include `top1_or_skip`, `topn_fallback`, `fixed_notional_lot_rounding`, `position_cap_utilization`, and `conservative_cash_reserve`.
   - Use a default account profile of CNY 200,000 initial cash, CNY currency, 100-share board lots, and new-retail-cash account eligibility.
   - Keep every configuration predeclared and deterministic.

3. Add CLI support.
   - Add `shortpick-v2-replay`.
   - Include options for database URL, start/end date, output path, initial cash, entry price source, horizon days, pool limit, rank limit, and account profile.
   - Default output should be an ignored `output/shortpick-v2-replay-artifact.json` path; runtime generation will pass an absolute runtime output path.

4. Add focused tests.
   - Validate no action other than `buy_primary`, `buy_fallback`, or `skip` can appear in produced decision samples.
   - Validate board-lot rounding and insufficient-cash skip behavior.
   - Validate generated artifact fields match the v2 schema's required envelope.
   - Validate writer output is valid JSON.

5. Generate the runtime artifact.
   - Run the new CLI against `/Users/hernando_zhao/codex/runtime/projects/ashare-dashboard/data/ashare_dashboard.db`.
   - Use an output path under `/Users/hernando_zhao/codex/runtime/projects/ashare-dashboard/output/`.
   - Validate the generated artifact against `shortpick_v2_replay_artifact.schema.json`.

6. Run post-implementation review and local gates.
   - Ask MiMo to review code risk and whether the final changes drift from this run plan.
   - Run targeted pytest for the new v2 replay tests.
   - Run the JSON/schema validation command for the generated runtime artifact.
   - Let the project pre-push hook run the default fast regression and policy audit on final push.

7. Close out.
   - Mark Phase 3 as Done in the main v2 plan with the runtime artifact path and validation summary.
   - Archive this run document under `docs/archive/`.
   - Merge to `main`, push to `origin/main`, then remove this worktree and temporary prompt files.

## Validation Plan

| Check | Purpose |
| --- | --- |
| MiMo pre-implementation review | Confirm this run plan does not drift from Phase 3. |
| Focused pytest | Confirm replay builder behavior and artifact writer shape. |
| Runtime artifact generation | Prove Phase 3 produces fixed historical results from runtime data. |
| JSON Schema validation | Confirm runtime artifact matches `shortpick_v2_replay_artifact.schema.json`. |
| MiMo post-implementation review | Confirm code risk and drift from this run plan. |
| Project pre-push hook | Run default fast regression and policy audit before push. |

## Out Of Scope

| Out-of-scope item | Reason |
| --- | --- |
| Strategy promotion or choosing final v2 winners | Belongs to Phase 4 after replay evidence exists. |
| Forward paper tracking ledger | Belongs to Phase 5. |
| Backend read API | Belongs to Phase 6. |
| Frontend `试验田v2` tab | Belongs to Phase 7. |
| Runtime publish | No live-facing code or UI is being activated in this phase. |
| DB writes, refreshes, model calls, or server startup | Phase 3 uses existing fixed local data only. |

## Completion Criteria

| Criterion | Status |
| --- | --- |
| Run plan reviewed by MiMo with no blocking plan-drift issue | Done |
| Offline v2 replay builder added | Done |
| CLI command added | Done |
| Focused tests added and passing | Done |
| Runtime artifact generated under runtime output | Done |
| Runtime artifact validates against schema | Done |
| Post-implementation MiMo review has no blocking issue | Done |
| Main v2 plan Phase 3 updated to Done with artifact reference | Done |
| Run document archived | Done |
| Branch merged to `main`, pushed to `origin/main`, and worktree cleaned | Pending until final git closeout after this archive is committed |

## Closeout Evidence

| Evidence | Result |
| --- | --- |
| MiMo run-plan review | No blocking drift from the v2 plan Phase 3 or replay design contract. |
| Focused pytest | `python3 -m pytest -q tests/test_shortpick_v2_replay.py` passed: 5 passed. |
| Runtime artifact generation | `shortpick-v2-replay` generated `/Users/hernando_zhao/codex/runtime/projects/ashare-dashboard/output/shortpick-v2-replay-artifact-20260612.json` from the existing runtime SQLite database; 721 signal days, 761 trade days, five rule-family results; final measured runtime 93.90 seconds. |
| Schema validation | Runtime artifact validates against `docs/contracts/registry/schemas/shortpick_v2_replay_artifact.schema.json`. Empty-scope fail-closed behavior also validates with `blocked` status and one result entry. |
| MiMo post-implementation review | Initial review found one P1 around empty signal scopes and schema `minItems`; code was tightened to blocked status with a preserved result entry, tested, schema-validated, and re-reviewed. Final result: no blocking issues. |
| Default fast regression | `python3 -m pytest -q` passed: 789 passed, 1 skipped, 171 deselected, 6 subtests passed. |
| Policy audit | `PYTHONPATH=src python3 -m ashare_evidence.cli policy-audit --fail-on-new-unclassified --fail-on-direct-config-read --fail-on-formula-side-effects --fail-on-missing-config-lineage` passed. |

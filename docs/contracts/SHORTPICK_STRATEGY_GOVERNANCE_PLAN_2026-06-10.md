# Short Pick Strategy Governance Plan 2026-06-10

Status: round21_replay_feedback_governance_source_wiring_completed_ds_review_passed
Owner: codex
Created: 2026-06-10
Scope: Short Pick Lab strategy retirement, retrospective replay, new diagnostic controls, and long-horizon evaluation governance

## Purpose

This plan converts the first-month short-pick forward-validation review into an implementation-ready governance backlog.

It does not change strategy code, runtime data, frontend behavior, production weights, or paper-tracking rows by itself. It establishes the required contract before implementation so that future work can retire weak strategies, add diagnostic controls, backfill historical evidence, and display results without contaminating true forward validation.

## Current Background

The current decision context comes from three sources:

- The first-month analysis report generated at `/Users/hernando_zhao/codex/runtime/projects/ashare-dashboard/output/analytics/20260610-stock-strategy-forward-report/report.html`.
- The existing Short Pick Lab and Phase 5 contracts in `DECISIONS.md`, `PROCESS.md`, and `docs/contracts/PHASE5_RESEARCH_CONTRACT.md`.
- The independent DeepSeek review of the proposed governance direction.

Key facts:

- Forward paper tracking has run for about one month, from `2026-05-08` through `2026-06-09`.
- The latest completed shortpick run in the analysis was `2026-06-09`, while the latest completed 10-day signal window was only `2026-05-25`.
- `frozen_paper_primary` 10-day completed rows showed positive mean but negative median: mean around `+10.4%`, median around `-3.0%`, win rate around `45.5%`, with strong tail dependence.
- Northern Huachuang repeated-loss behavior exposed a missing governance feature: the frozen rule has no feedback from recent same-symbol losses, repeated exposure, or post-entry drawdown.
- Existing project contracts already prohibit using historical expectations to replace real forward evidence. Historical replay can inform research, but true forward tracking starts only after a rule is defined.
- The project also has a registry-first rule for new artifact families, event IDs, or interface contracts. New strategy governance artifacts must be registered before implementation.

## Scheme Summary

The next governance package should adopt four principles.

1. Weak strategies are retired, not silently erased.
   - Remove them from active generation, hot-path frontend views, and daily compute.
   - Preserve a durable retirement artifact that records why they were retired and which evidence snapshot supported the decision.

2. New diagnostic controls can be backfilled, but their evidence must be labeled.
   - Historical long-window backtest is allowed.
   - Retrospective forward replay over the already-observed forward window is allowed.
   - Neither can be represented as true forward tracking.

3. True forward evidence is protected as a separate ledger.
   - A new control becomes true-forward eligible only from the date its rule and registry entries are created.
   - Frontend displays must not merge retrospective and true-forward rows into the same status, color, or headline metric.

4. Further strategy questions map back to Phase 5 gates.
   - The core objective remains long-run rotating-strategy return.
   - Evaluation must prioritize after-cost excess return, 20/40-day maturity, median, win rate, drawdown, tail dependence, and stability versus registered baselines such as random pool and cooldown control.
   - If this plan conflicts with `docs/contracts/PHASE5_RESEARCH_CONTRACT.md` or `DECISIONS.md`, the Phase 5 contract and decision log take precedence.

## Implementation Plan

### P0 - Governance Contract

| ID | Work Item | Status | Notes |
| --- | --- | --- | --- |
| P0.1 | Create this governance plan | completed | This document defines the background, strategy, implementation checklist, and acceptance criteria. |
| P0.2 | DeepSeek review of this plan | completed | Read-only DeepSeek review found no blocking contradiction and recommended acceptance with nonblocking followups. |
| P0.3 | Add `DECISIONS.md` entry for the governance direction | completed | Added 2026-06-10 decision entry covering retirement protocol, retrospective replay labeling, registry-first implementation, transition behavior, and Phase 5 gate alignment. |
| P0.4 | Define strategy retirement thresholds | completed | Round 2 defines minimum maturity, historical, forward, baseline, tail-risk, and diagnostic-value gates. |
| P0.5 | Define retrospective replay labeling contract | completed | Round 2 defines evidence-basis labels, required metadata, leakage status, and display prohibitions. |
| P0.6 | Define evaluation-baseline policy | completed | Round 2 defines baseline eligibility and restricts baseline claims until registry artifacts exist. |
| P0.7 | Define transition rule before implementation | completed | Round 2 states existing strategies remain unchanged until registry, artifacts, and display support exist. |
| P0.8 | Define un-retirement protocol | completed | Round 2 defines `retired -> observe` recovery conditions and forbids direct return to active/frozen. |

### P1 - Registry And Artifact Contracts

| ID | Work Item | Status | Notes |
| --- | --- | --- | --- |
| P1.1 | Register `strategy_retirement:v1` artifact family | completed | Registered machine artifact family `shortpick_strategy_retirement` with schema `docs/contracts/registry/schemas/shortpick_strategy_retirement.schema.json`. The display alias remains `strategy_retirement:v1`. |
| P1.2 | Register `forward_validation_retrospective:v1` artifact family | completed | Registered machine artifact family `shortpick_forward_validation_retrospective` with `retrospective: true`, source feature cutoff, replay generation time, and leakage-audit status. |
| P1.3 | Register `evaluation_baseline_random_pool:v1` | completed | Registered as an allowed `baseline_id` in `shortpick_evaluation_baseline` and as a registry maturity-domain ID. Runtime evidence remains pending. |
| P1.4 | Register `evaluation_baseline_cooldown_control:v1` | completed | Registered as an allowed `baseline_id` in `shortpick_evaluation_baseline` and as a registry maturity-domain ID. Runtime evidence remains pending. |
| P1.5 | Register control group IDs and rule signatures | completed | Registered initial control-group IDs: `control_same_symbol_cooldown:v1`, `control_drawdown_reversal_filter:v1`, and `control_repeated_exposure_limit:v1`. Actual `rule_signature` values must be generated by P3 implementations from deterministic rule definitions. |
| P1.6 | Add or extend JSON Schema where the registry requires machine validation | completed | Added schemas for retirement, retrospective forward replay, and evaluation baselines under `docs/contracts/registry/schemas/`. |
| P1.7 | Define leakage audit checklist | completed | Leakage status is now schema-bound as `passed`, `failed`, `blocked`, or `not_run`; retrospective replay cannot be trusted for evaluation unless this status is explicit. |

### P2 - Strategy Retirement Flow

| ID | Work Item | Status | Notes |
| --- | --- | --- | --- |
| P2.1 | Inventory active shortpick strategies and controls | completed | Added `docs/contracts/SHORTPICK_STRATEGY_INVENTORY_2026-06-10.md`, separating true-forward paper tracking, generated overlay-only rows, historical/replay-only variants, and configured dormant controls. |
| P2.2 | Compute retirement evidence pack per strategy | completed | Added a read-only builder in `src/ashare_evidence/shortpick_strategy_governance.py` that aggregates paper-tracking rows into evidence packs with evidence basis, forward mean/median/win rate, completed sample count, additive drawdown, tail dependence, same-symbol loss repeats, and optional historical/baseline evidence references. It does not mark `retired`, write runtime data, or change frontend/API behavior. |
| P2.3 | Mark candidates as `active`, `observe`, `retire_candidate`, or `retired` | completed | Added a read-only status recommendation layer. Metrics alone can only produce `active`, `observe`, or `retire_candidate`; `retired` requires a valid `strategy_retirement:v1` / `shortpick_strategy_retirement` artifact plus `decision_log_ref`. No runtime state is persisted in this round. |
| P2.4 | Remove retired strategies from active generation | partial | Added a read-only generation eligibility filter that excludes only `recommended_status=retired` by default and keeps `retire_candidate`, `observe`, and `untracked` eligible. Archive rebuild can explicitly pass `include_retired=True`. Runtime generation wiring remains pending until a real retirement artifact source exists. |
| P2.5 | Remove retired strategies from primary frontend views | partial | Added a read-only view projection helper that sends `retired` rows to archive and keeps `active`, `observe`, and `retire_candidate` in primary projection. It deliberately omits heavy horizon evidence and retirement artifact refs. Frontend/runtime wiring remains pending. |
| P2.6 | Preserve archived statistics and evidence refs | completed | Added a read-only archive record helper that builds audit records only from archive rows and preserves signal counts, completed sample counts, horizon summaries, historical evidence refs, baseline refs, and retirement artifact refs. It does not delete or persist data. |

### P3 - New Diagnostic Controls

| ID | Work Item | Status | Notes |
| --- | --- | --- | --- |
| P3.1 | Same-symbol cooldown control | completed_partial_runtime_wiring_pending | Added a deterministic rule builder and pure input-to-output cooldown helper. It blocks candidates only from prior completed same-symbol negative outcomes, uses longer cooldown after severe losses, emits `rule_signature`, and labels evidence basis. Historical/replay generation, true-forward wiring, and frontend display remain pending. |
| P3.2 | Drawdown/reversal filter control | completed_partial_runtime_wiring_pending | Added a deterministic rule builder and pure input-to-output filter helper. It uses only signal-date-or-prior technical feature snapshots, blocks on recent drawdown, short-window breakdown plus price-vs-MA weakness, or high-level reversal triggers, emits `rule_signature`, and labels evidence basis. Feature generation, historical/replay artifacts, true-forward wiring, and frontend display remain pending. |
| P3.3 | Repeated exposure limit control | completed_partial_runtime_wiring_pending | Added a deterministic rule builder and pure input-to-output exposure-limit helper. It defaults to symbol grouping, supports explicit group fields such as symbol plus industry for later governed use, ignores same-day/future exposure rows, emits `rule_signature`, and labels evidence basis. Runtime generation wiring, historical/replay artifacts, true-forward tracking, and frontend display remain pending. |
| P3.4 | Historical backtest generation | completed_partial_runner_wiring_pending | Added a deterministic historical-backtest generation request builder. It creates `shortpick-portfolio-backtest` request plans for rule-signature and entry-source combinations, labels `evidence_basis=historical_backtest`, marks `true_forward_tracking_eligible=false`, forbids paper-tracking writes, and does not execute backtests or write files. Runner wiring and artifact persistence remain pending. |
| P3.5 | Retrospective forward replay generation | completed_partial_runner_wiring_pending | Added a deterministic retrospective-forward-replay request builder. It derives observed start/end from `paper_tracking.items`, includes only signal dates strictly before `rule_defined_at`, labels `evidence_basis=retrospective_forward_replay`, marks `retrospective=true`, forbids paper-tracking writes, and does not execute replay or write files. Runner wiring and artifact persistence remain pending. |
| P3.6 | True forward tracking start | completed_partial_runtime_wiring_pending | Added a deterministic true-forward activation-plan helper. It allows only registered control IDs with `rule_signature` and `rule_defined_at`, sets `tracking_start_date` no earlier than both the requested start and rule definition date, labels `evidence_basis=true_forward_tracking`, forbids retroactive backfill, and does not write tracking rows. Runtime paper-ledger wiring remains pending. |

### P4 - Frontend And Reporting

| ID | Work Item | Status | Notes |
| --- | --- | --- | --- |
| P4.1 | Add strategy status labels | completed_partial_display_wiring_pending | Added backend view-projection label metadata for governance status and evidence basis, plus frontend label/color helpers for active, observe, retire-candidate, retired, historical-only, retrospective-only, and true-forward states. API/page wiring remains pending. |
| P4.2 | Add separate display sections for evidence basis | completed_partial_display_wiring_pending | Added backend view-projection sections that split true-forward tracking, retrospective replay, and historical backtest rows while preserving primary/archive membership in each section. API/page wiring remains pending. |
| P4.3 | Add retirement archive view or archive summary rows | completed_partial_display_wiring_pending | Added archive summary rows grouped by evidence basis, strategy family, and entry-price source while preserving detailed archive records. API/page wiring remains pending. |
| P4.4 | Add leakage and coverage notes | completed_partial_display_wiring_pending | Added leakage/coverage note metadata to strategy view projection and archive records. Retrospective rows default to showing signal-date cutoff policy and leakage audit status. API/page wiring remains pending. |
| P4.5 | Update analytical report generation | completed_partial_page_rendering_pending | Added replay readout/report projection that reads strategy governance recommendations, view sections, archive summaries, and leakage notes from governance contract fields. `/shortpick-lab/replay-feedback` now builds a read-only governance source from the already loaded paper-tracking ledger when no persisted governance payload exists. Page rendering remains pending. |

## Retirement Threshold Draft

The first implementation should not retire a strategy only because a single recent metric is bad. Retirement requires a deterministic rule such as:

- Historical after-cost excess return is persistently negative under the account-executable universe.
- Completed forward evidence is mature enough for the strategy class.
- Forward mean and median are both negative, or median and win rate are materially worse than registered baselines.
- The strategy fails tail-dependence checks, such as positive mean being explained by one or two outliers while median and drawdown remain weak.
- The strategy does not provide unique diagnostic value that justifies continued compute.

Until the `strategy_retirement:v1` artifact writer, evidence packet generation, and `DECISIONS.md` record exist in P2, no strategy may be marked `retired`. The only allowed interim states are `active`, `observe`, or `retire_candidate`.

Minimum evidence gates should be conservative:

- One-stock controls: at least 10 completed 10-day rows before retirement is allowed.
- 20/40-day claims: not allowed until those horizons have mature completed rows.
- Historical replay: must pass account-executable, benchmark, cost, and source-cutoff checks.
- Any exception must be logged as `observe` or `retire_candidate`, not `retired`.

The implementation of P0.4 must quantify ambiguous phrases before any strategy can be retired:

- `persistently negative` must become a concrete rolling-window or calendar-slice rule.
- `materially worse than registered baselines` must specify margin, sample count, and confidence or stability basis.
- `unique diagnostic value` must state why a strategy remains worth compute even if it is not a promotion candidate.

Round 2 makes the first machine-checkable threshold draft explicit. A strategy can be marked `retire_candidate` when all of the following hold:

- Maturity gate:
  - One-stock strategy/control: at least 10 completed 10-day rows.
  - Multi-row strategy/control: at least 30 completed 10-day candidate rows and at least 10 distinct signal dates.
  - Long-horizon retirement for 20/40-day claims is blocked until the matching horizon has completed rows across at least 10 distinct signal dates.
- Historical gate:
  - Account-executable historical replay shows after-cost excess return below `0` in the full window and in at least two of the last three calendar-month or rolling-60-trading-day slices.
  - If historical evidence is missing, stale, not account-executable, or missing cost/benchmark definitions, the strategy can only be `observe`.
- Forward gate:
  - Completed true-forward evidence has stock-return median below `0`.
  - Either stock-return mean is below `0`, or positive mean is explained by tail dependence.
  - Win rate is below `45%` for one-stock strategies, or materially below the registered random-pool baseline once that baseline exists.
- Tail-risk gate:
  - Worst completed 10-day return is below `-8%`, or max drawdown / worst-tail evidence fails the strategy's documented risk envelope.
  - If a single best observation contributes more than half of positive mean excess, the result must be flagged as tail-dependent and cannot be promoted.
- Baseline gate:
  - Until `evaluation_baseline_random_pool:v1` and `evaluation_baseline_cooldown_control:v1` are registered, baseline comparisons are advisory only.
  - After registration, retirement can cite a baseline only when sample basis, horizon, entry price source, cost, and benchmark are aligned.
- Diagnostic-value gate:
  - A poor-performing strategy can stay `observe` if it tests a unique execution, exposure, or model-risk hypothesis that no other active control covers.

A strategy can move from `retire_candidate` to `retired` only after `strategy_retirement:v1` exists, the evidence packet is generated, and `DECISIONS.md` records the decision. `retired` cannot be produced directly from raw query results.

Retirement is not permanent deletion from project memory. A later un-retirement path is allowed only when:

- The strategy has a new rule version or a new mature evidence packet.
- The original `strategy_retirement:v1` artifact remains linked.
- The recovered strategy starts as `observe`, not `active` or `frozen`.
- The decision log records why the previous blocker no longer applies.

## Retrospective Replay Contract Draft

Retrospective replay is useful, but it must be labeled as post-hoc.

Required labels:

- `evidence_basis=historical_backtest`
- `evidence_basis=retrospective_forward_replay`
- `evidence_basis=true_forward_tracking`

Evidence-basis definitions:

- `historical_backtest`: long-window replay over historical market data before the observed paper-tracking period. It may support research ranking but is not a paper-ledger row.
- `retrospective_forward_replay`: post-hoc replay over dates that already occurred in the paper-tracking era before the rule was registered. It can answer "what would this deterministic rule have done under point-in-time inputs?" but cannot be described as contemporaneous forward tracking.
- `true_forward_tracking`: paper tracking that starts on or after `rule_defined_at` and after the control ID, rule signature, and artifact family are registered.

Required metadata for retrospective replay:

- `retrospective=true`
- `rule_defined_at`
- `signal_date`
- `feature_cutoff_at`
- `generated_at`
- `leakage_audit_status`
- `leakage_audit_reasons`
- `source_tables_or_artifacts`
- `entry_price_source`
- `benchmark_definition`
- `cost_definition`
- `control_group_id`
- `rule_signature`
- `evidence_basis`

Leakage audit must be defined before implementation. At minimum it should check:

- Feature values are sourced at or before `feature_cutoff_at`.
- Strategy thresholds were not fitted on the same retrospective outcome window unless explicitly marked as tuned research.
- Market data, benchmark data, industry/theme labels, and eligibility filters do not use future-only information for the signal date.
- Replay artifacts preserve generation time separately from signal time.

Forbidden behavior:

- Do not insert retrospective rows as if they were true paper-tracking rows.
- Do not display retrospective rows in the same headline as true-forward rows without a basis split.
- Do not use future-known outcomes to tune thresholds and then describe the replay as unbiased.
- Do not call a replayed control "frozen" for dates before the rule was registered.

Display policy:

- Historical, retrospective, and true-forward rows must be visually separated by section or basis label.
- A combined table is allowed only when `evidence_basis` is a visible column and default grouping keeps true-forward rows separate.
- Headline metrics for promotion or retirement must default to true-forward rows; retrospective rows can appear only as supporting research evidence.
- Any retrospective replay over thresholds tuned after seeing outcomes must be labeled `tuned_research`, not `validation`.

## Evaluation Baseline Policy

Baseline comparisons are useful only when their sample basis matches the strategy being judged.

Required baseline statuses:

- `baseline_candidate`: defined in a plan or doc, not registered; may not be used in promotion or retirement gates.
- `baseline_registered`: has registry ID and schema, but may not have enough completed evidence; can be shown as pending.
- `baseline_active`: has registered artifact family, aligned evidence basis, and enough completed rows for comparison.
- `baseline_retired`: no longer used for current gates but retained for historical audit.

Initial baseline IDs:

- `evaluation_baseline_random_pool:v1`
- `evaluation_baseline_cooldown_control:v1`

Baseline usage rules:

- A baseline must use the same horizon, entry price source, benchmark, cost definition, universe eligibility, and evidence basis as the strategy comparison.
- Random pool is a noise and opportunity-cost reference, not proof of investable superiority.
- Cooldown control is an exposure-governance reference, not a replacement strategy by itself.
- Baseline comparisons before P1 registry completion must be described as advisory and cannot drive `retired` or `promoted` status.

## Transition Rule

Round 2 locks transition behavior while this governance work is still contract-only.

- Existing strategy generation, paper tracking, frontend labels, replay projections, and runtime data remain unchanged until a later implementation round changes them.
- No strategy may be hidden from active views solely because this plan exists.
- No retrospective rows may be inserted into the true paper-tracking ledger before the retrospective artifact contract exists.
- No new control can be called true-forward until its ID, rule signature, and artifact family have been registered.
- Existing bad-looking controls can be manually discussed as weak, but their durable status remains unchanged until the retirement flow exists.

## Un-Retirement Protocol

Retirement is reversible only through a governed recovery path.

Allowed recovery path:

1. Keep the original `strategy_retirement:v1` artifact linked.
2. Create a new evidence packet with a new rule version or materially new mature evidence.
3. Record which original retirement blocker no longer applies.
4. Move status from `retired` to `observe`.
5. Require a new true-forward observation period before any `active`, `frozen`, or promotion-candidate status.

Forbidden recovery:

- A retired strategy cannot return directly to `active`, `frozen`, or production candidate.
- A retrospective replay alone cannot un-retire a strategy.
- A renamed strategy with identical rule signature cannot bypass the retirement artifact.

## Further Questions Mapping

The report's Further Questions should be interpreted through the existing Phase 5 gates.

| Question | Governance Answer | Gate Or Contract Mapping |
| --- | --- | --- |
| Should open-entry become primary? | Keep as conditional v2 candidate only. It needs sustained 1/3/5-day advantage and no 20-day deterioration before promotion. | Primary horizon and execution-price evidence. |
| Should cooldown be by symbol, industry, or theme? | Start with symbol. Add industry/theme only after classification and exposure evidence are stable. | Exposure and concentration governance. |
| What should promotion optimize? | Long-run after-cost excess return first, then median, win rate, drawdown, tail dependence, and stability versus registered baselines. | Phase 5 `after_cost_profitability`, confidence interval, regime stability, and baseline gates. |

## Acceptance Criteria

This plan is accepted only when all of the following are true:

1. DeepSeek completes a read-only review of this document and does not find a blocking contradiction with existing project contracts.
2. The plan clearly separates retirement, retrospective replay, and true forward tracking.
3. The plan contains implementation items with explicit completion status.
4. The plan defines retirement thresholds before allowing active strategy deletion.
5. The plan requires registry-first artifact and control-group definitions before implementation.
6. The plan maps future strategy evaluation back to Phase 5 gates instead of creating a parallel evaluation system.
7. No runtime database, live service, frontend route, strategy code, or generated validation data is changed by this planning task.
8. Transition behavior is explicit: until artifact writers, runtime data, and frontend display support exist, existing strategy generation and display semantics remain unchanged.

## DeepSeek Review Result

DeepSeek performed a read-only review of this plan against `DECISIONS.md` and `docs/contracts/PHASE5_RESEARCH_CONTRACT.md`.

Result:

- Blocking issues: none.
- Recommendation: accept the plan for the next phase.
- Nonblocking followups incorporated into this document:
  - Quantify `persistently negative` before implementation.
  - Derive retrospective replay start date from the paper-tracking ledger instead of hard-coding it.
  - Add an un-retirement protocol.
  - Define leakage audit checks.
  - Propose explicit v1 control IDs before registry implementation.
  - State transition behavior before retirement flow exists.

DeepSeek then performed a second read-only Round 1 review after the `DECISIONS.md` entry was added.

Round 1 result:

- Blocking issues: none.
- Recommendation: update plan status and merge Round 1.
- Required pre-merge updates incorporated into this document:
  - Mark P0.3 as `completed`.
  - Explicitly block `retired` status until P0.4 quantifies machine-checkable thresholds.
  - Record this second DeepSeek review result.
  - State that Phase 5 contract and decision log take precedence if contracts conflict.

## Round 2 Review Result

Status: completed DeepSeek review.

Round 2 scope:

- P0.4 retirement threshold draft.
- P0.5 retrospective replay labeling contract.
- P0.6 evaluation baseline policy.
- P0.7 transition rule.
- P0.8 un-retirement protocol.

DeepSeek result:

- Blocking issues: none.
- Merge recommendation: merge and push after updating this status record.
- Key confirmations: P0.4-P0.8 do not conflict with `DECISIONS.md` or `docs/contracts/PHASE5_RESEARCH_CONTRACT.md`; retrospective replay is separated from true forward tracking; baseline claims remain advisory until registry-backed; transition language does not imply runtime, data, frontend, or strategy-code changes.
- Nonblocking follow-ups retained for later implementation: explain the source of the `-8%` tail threshold, treat 10 completed one-stock rows as a thin but conservative minimum because all gates must pass together, and convert schema-bound leakage status into executable checks when P3/P4 lands.

## Round 3 Review Result

Status: completed DeepSeek review.

Round 3 scope:

- P1.1-P1.4 registry entries for retirement, retrospective replay, and evaluation baselines.
- P1.5 registry entries for initial diagnostic control IDs.
- P1.6-P1.7 schema contracts for required fields, evidence basis, leakage status, and event refs.

Round 3 changed only registry, schema, and this plan document. It does not create retirement artifacts, generate replay data, alter strategy code, write paper-tracking rows, or change frontend/API behavior.

DeepSeek result:

- Blocking issues: none.
- Merge recommendation: merge and push Round 3.
- Key confirmations: P1.1-P1.7 are honestly scoped to registry/schema contracts; the dual ID convention is acceptable under the current registry structure; new schemas are sufficient first contracts for retirement, retrospective replay, and baselines; `retired` remains blocked until P2 artifact writing, evidence packets, and `DECISIONS.md` logging exist; no contradiction was found with `DECISIONS.md` or `docs/contracts/PHASE5_RESEARCH_CONTRACT.md`.
- Nonblocking follow-ups retained for P3/P4: add runtime artifact families/events before diagnostic controls produce data, decide whether schema `$id` values need full URIs, document why replay can span multiple horizons while baseline comparison is one horizon at a time, and ensure P3 retrospective generation turns `leakage_audit_status` from `not_run` into `passed`, `failed`, or `blocked`.

## Round 4 Review Result

Status: completed DeepSeek review.

Round 4 scope:

- P2.1 inventory of current shortpick strategies and controls.
- New inventory file: `docs/contracts/SHORTPICK_STRATEGY_INVENTORY_2026-06-10.md`.
- Source basis: `src/ashare_evidence/shortpick_lab.py`, `src/ashare_evidence/default_policy_configs.py`, `src/ashare_evidence/api.py`, and frontend shortpick display helpers.

Round 4 changed only documentation. It does not mark any strategy as `retired`, compute retirement evidence packs, delete strategies, write runtime data, or change frontend/API behavior.

DeepSeek result:

- Blocking issues: none.
- Merge recommendation: merge and push Round 4.
- Key confirmations: the inventory covers all 12 active paper-tracking roles; it correctly separates generated overlay-only rows, replay-only variants, and configured dormant controls; it does not imply retirement, runtime, data, frontend, or API changes; no contradiction was found with `DECISIONS.md`, `docs/contracts/PHASE5_RESEARCH_CONTRACT.md`, or the Round 3 registry/schema contracts.
- Nonblocking follow-ups retained for P2.2 or later: clarify the intentional dormancy of standalone low-turnover control config, and keep the stop8 replay-only legacy second variant separate from the active non-stop legacy second paper control.

## Round 5 Review Result

Status: completed DeepSeek review.

Round 5 scope:

- P2.2 read-only retirement evidence-pack builder.
- New module: `src/ashare_evidence/shortpick_strategy_governance.py`.
- New tests: `tests/test_shortpick_strategy_governance.py`.

Round 5 adds code for evidence aggregation only. It does not mark candidates as `active`, `observe`, `retire_candidate`, or `retired`; does not create `strategy_retirement:v1` artifacts; does not remove any strategy from active generation; does not write runtime data; and does not change frontend/API behavior.

DeepSeek result:

- Blocking issues: none.
- Merge recommendation: merge and push Round 5.
- Key confirmations: the builder is pure input-to-output and read-only; pack-level `decision_status` remains `not_evaluated`; `evidence_basis` is explicit and schema-limited to `true_forward_tracking`, `retrospective_forward_replay`, or `historical_backtest`; `source_rank=0` remains distinct from a missing rank; and missing structured entry-source data no longer falls back to Chinese UI text parsing.
- Nonblocking follow-up retained for later consumer work: if a downstream view combines multiple evidence bases, it must de-duplicate by `strategy_id + evidence_basis` or otherwise keep basis visible.

## Round 6 Review Result

Status: completed DeepSeek review.

Round 6 scope:

- P2.3 read-only strategy governance status recommendation layer.
- Extended module: `src/ashare_evidence/shortpick_strategy_governance.py`.
- Extended tests: `tests/test_shortpick_strategy_governance.py`.

Round 6 computes recommended statuses only. It does not persist status to the database, does not create retirement artifacts, does not append `DECISIONS.md`, does not remove strategies from active generation, and does not change frontend/API behavior.

DeepSeek result:

- Blocking issues: none.
- Merge recommendation: merge and push Round 6.
- Key confirmations: `retired` cannot be produced by metrics alone; a valid retirement artifact and `decision_log_ref` are both required; `retire_candidate` requires all configured maturity, historical, forward, win-rate, tail-risk, and ready-baseline gates; immature or incomplete evidence falls to `observe`; and non-triggering strategies stay `active`.
- Nonblocking follow-ups retained for future hardening: add tests for positive baseline gap blocking `retire_candidate`, mixed negative/positive forward signals, incomplete retirement artifacts, list-form artifact lookup, empty packs, and primary-horizon fallback.

## Round 7 Review Result

Status: completed DeepSeek review.

Round 7 scope:

- P2.4 read-only generation eligibility filter helper.
- Extended module: `src/ashare_evidence/shortpick_strategy_governance.py`.
- Extended tests: `tests/test_shortpick_strategy_governance.py`.

Round 7 adds a helper only. It does not wire the helper into the active shortpick generation path, because there is not yet a real persisted retirement artifact source. No strategy is removed from generation by this round alone.

DeepSeek result:

- Blocking issues: none.
- Merge recommendation: merge and push Round 7.
- Key confirmations: the filter excludes only `recommended_status=retired` when `include_retired=False`; it preserves `retire_candidate`, `observe`, and `untracked`; archive rebuilds can opt in with `include_retired=True`; and fallback strategy-id mismatch fails open as `untracked` rather than incorrectly excluding a strategy.
- Nonblocking follow-ups retained for future wiring: make the `decision_policy` string reflect archive mode when `include_retired=True`, align fallback `family` priority with evidence-pack strategy-id derivation, add the LLM family fallback to generation-item derivation, and add cross-path strategy-id consistency tests.

## Round 8 Review Result

Status: completed DeepSeek review.

Round 8 scope:

- P2.5 read-only primary/archive view projection helper.
- Extended module: `src/ashare_evidence/shortpick_strategy_governance.py`.
- Extended tests: `tests/test_shortpick_strategy_governance.py`.

Round 8 adds a helper only. It does not change frontend code, API routes, runtime data, or served dashboard behavior.

DeepSeek result:

- Blocking issues: none.
- Merge recommendation: merge and push Round 8.
- Key confirmations: only `recommended_status=retired` enters archive; `active`, `observe`, and `retire_candidate` remain in primary; projection is intentionally lightweight and excludes `primary_horizon_summary` and `retirement_artifact_ref`; and this should be marked helper-complete with runtime/frontend wiring pending.

## Round 9 Review Result

Status: completed DeepSeek review.

Round 9 scope:

- P2.6 read-only archive record helper.
- Extended module: `src/ashare_evidence/shortpick_strategy_governance.py`.
- Extended tests: `tests/test_shortpick_strategy_governance.py`.

Round 9 adds a helper only. It does not write database rows, change frontend/API behavior, or delete source evidence.

DeepSeek result:

- Blocking issues: none.
- Merge recommendation: merge and push Round 9.
- Key confirmations: archive records are built only from `archive_items`; primary rows are ignored; retired strategy records preserve signal counts, completed observations, horizon summaries, historical evidence refs, baseline refs, and retirement artifact refs; and the helper is pure input-to-output with no side effects.

## Round 10 Review Result

Status: completed DeepSeek review.

Round 10 scope:

- P3.1 same-symbol cooldown deterministic rule builder.
- P3.1 pure same-symbol cooldown control helper.
- Extended module: `src/ashare_evidence/shortpick_strategy_governance.py`.
- Extended tests: `tests/test_shortpick_strategy_governance.py`.

Round 10 adds a helper only. It does not generate historical backtests, create retrospective forward replay artifacts, start true-forward tracking, write database rows, change frontend/API behavior, or alter active shortpick generation.

DeepSeek result:

- Blocking issues: none.
- Merge recommendation: merge and push Round 10.
- Key confirmations: the helper ignores same-day or future outcomes and only uses prior completed negative same-symbol outcomes; `leakage_policy` matches implementation; all new functions are pure input-to-output; `evidence_basis` is explicit and does not disguise replay as true forward; tests cover stable rule signatures, invalid windows, normal and severe cooldown windows, wrong-horizon exclusion, symbol separation, and same-day/future leakage guards.
- Nonblocking follow-ups retained for later hardening: add empty input tests, threshold-equality tests, and explicit default-rule-path tests.

## Round 11 Review Result

Status: completed DeepSeek review.

Round 11 scope:

- P3.2 drawdown/reversal deterministic rule builder.
- P3.2 pure drawdown/reversal filter helper.
- Extended module: `src/ashare_evidence/shortpick_strategy_governance.py`.
- Extended tests: `tests/test_shortpick_strategy_governance.py`.

Round 11 adds a helper only. It does not generate feature snapshots, historical backtests, retrospective forward replay artifacts, true-forward tracking rows, database writes, frontend/API changes, or active shortpick generation changes.

DeepSeek result:

- Blocking issues: none.
- Merge recommendation: merge and push Round 11.
- Key confirmations: the helper uses only feature snapshots with `feature_date <= signal_date`; future features are counted and ignored; all functions remain pure input-to-output; no paper-tracking rows are generated; tests cover deterministic signatures, invalid lookback validation, all three trigger families, future feature exclusion, missing feature coverage, and leakage audit labels.

## Round 12 Review Result

Status: completed DeepSeek review.

Round 12 scope:

- P3.3 repeated-exposure deterministic rule builder.
- P3.3 pure repeated-exposure limit helper.
- Extended module: `src/ashare_evidence/shortpick_strategy_governance.py`.
- Extended tests: `tests/test_shortpick_strategy_governance.py`.

Round 12 adds a helper only. It does not wire active generation, generate historical backtests, produce retrospective replay artifacts, start true-forward tracking, write paper-tracking rows, or change frontend/API behavior.

DeepSeek result:

- Blocking issues: none.
- Merge recommendation: merge and push Round 12.
- Key confirmations: the helper uses only exposure signal rows before candidate `signal_date`; same-day and future exposure rows are ignored and counted; functions remain pure input-to-output; no tracking rows are generated; tests cover deterministic signatures, invalid limits, same-symbol window blocking, same-day/future signal exclusion, explicit group fields, missing group-key behavior, and existing cooldown/filter leakage boundaries.
- Nonblocking follow-up retained for later hardening: decide whether cooldown/exposure signal-day windows should count all candidate signal dates or only same-symbol / same-group signal dates when a runtime replay implementation chooses final evaluation semantics.

## Round 13 Review Result

Status: completed DeepSeek review.

Round 13 scope:

- P3.4 historical-backtest generation request builder.
- Extended module: `src/ashare_evidence/shortpick_strategy_governance.py`.
- Extended tests: `tests/test_shortpick_strategy_governance.py`.

Round 13 adds a request-plan helper only. It does not execute `shortpick-portfolio-backtest`, write output artifacts, write database rows, generate paper-tracking rows, or change frontend/API behavior.

DeepSeek result:

- Blocking issues: none.
- Merge recommendation: merge and push Round 13.
- Key confirmations: the helper only validates inputs and constructs request dictionaries with deterministic request IDs, argv, and output paths; labels clearly separate `historical_backtest` from true forward evidence; top-level and per-request `paper_tracking_write_policy=forbidden` and `true_forward_tracking_eligible=false` reduce downstream confusion risk; tests cover determinism, read-only policy labels, entry-source expansion, missing rule-signature skip behavior, and key input validation.
- Nonblocking follow-ups retained for later hardening: add explicit tests for `min_signal_symbol_count <= 0`, empty `control_rules`, and `same_close_proxy`; implement the actual runner only after artifact persistence and leakage-audit handling are defined.

## Round 14 Review Result

Status: completed DeepSeek review.

Round 14 scope:

- P3.5 retrospective-forward-replay generation request builder.
- Extended module: `src/ashare_evidence/shortpick_strategy_governance.py`.
- Extended tests: `tests/test_shortpick_strategy_governance.py`.

Round 14 adds a request-plan helper only. It does not execute replay, write output artifacts, write database rows, generate paper-tracking rows, or change frontend/API behavior.

DeepSeek result:

- Blocking issues: none.
- Merge recommendation: merge and push Round 14.
- Key confirmations: the helper derives the observed paper-tracking start/end from `paper_tracking.items`; it keeps only replay signal dates strictly before `rule_defined_at`; it explicitly labels the result as `retrospective_forward_replay`, `retrospective=true`, `true_forward_tracking_eligible=false`, and `paper_tracking_write_policy=forbidden`; and tests cover window derivation, missing identity blocking, missing `rule_defined_at` blocking, no-prior-date blocking, and deterministic request generation.
- Nonblocking follow-up retained for future precision work: `rule_defined_at` is date-truncated, so same-day signals are conservatively excluded. A later replay runner can move to full datetime comparison only if feature timestamps and paper ledger timestamps support that precision.

## Round 15 Review Result

Status: completed DeepSeek review.

Round 15 scope:

- P3.6 true-forward tracking activation-plan helper.
- Extended module: `src/ashare_evidence/shortpick_strategy_governance.py`.
- Extended tests: `tests/test_shortpick_strategy_governance.py`.

Round 15 adds an activation-plan helper only. It does not write paper-tracking rows, execute generation, run retrospective replay, or change frontend/API behavior.

DeepSeek result:

- Blocking issues: none.
- Merge recommendation: merge and push Round 15.
- Key confirmations: the helper gates activation on `control_group_id`, `rule_signature`, and `rule_defined_at`; unregistered control IDs are blocked; `tracking_start_date` is `max(tracking_started_at, rule_defined_at)`; `evidence_basis=true_forward_tracking` is paired with `retrospective=false` and `retroactive_backfill_allowed=false`; and tests cover normal activation, missing identity or definition time, unregistered control blocking, determinism, and input validation.
- Nonblocking follow-up retained for runtime wiring: the current artifact family reference points to the existing paper-tracking ledger concept rather than a newly registered dedicated artifact family; if the project later creates a dedicated true-forward artifact family, the activation plan should be wired to that registered family before writing rows.

## Round 16 Review Result

Status: completed DeepSeek sharded review.

Round 16 scope:

- P4.1 backend strategy-status and evidence-basis display metadata in `project_shortpick_strategy_view_sections`.
- P4.1 frontend label/color helper functions in `frontend/src/components/shortpickLabLabels.ts`.
- Extended tests: `tests/test_shortpick_strategy_governance.py` and `tests/test_frontend_shortpick_static.py`.

Round 16 adds labels and projection metadata only. It does not create a new API route, wire governance projection into a live page, write runtime data, or change active strategy generation.

DeepSeek result:

- Blocking issues: none.
- Merge recommendation: merge and push Round 16.
- Key confirmations: backend projection now adds stable `status_display` and `evidence_basis_display` metadata while preserving the rule that `retired` rows go only to archive; frontend helpers cover active, observe, retire-candidate, retired, historical-only, retrospective-only, true-forward, historical-backtest, retrospective-forward-replay, and true-forward-tracking labels; tests cover known labels, fallback labels, helper presence, and legacy projection/archive behavior.
- Nonblocking follow-up retained for P4.2/P4.3: actual page display still requires an API or report data source that carries these projection rows; until then, the helper must not be presented as live UI evidence.

## Round 17 Review Result

Status: completed DeepSeek review.

Round 17 scope:

- P4.2 backend evidence-basis display sections in `project_shortpick_strategy_view_sections`.
- Extended tests: `tests/test_shortpick_strategy_governance.py`.

Round 17 adds projection metadata only. It does not create an API route, wire a live page, write runtime data, or alter active strategy generation.

DeepSeek result:

- Blocking issues: none.
- Merge recommendation: merge and push Round 17.
- Key confirmations: primary/archive splitting remains unchanged; `evidence_basis_sections` groups all projected rows by true-forward tracking, retrospective replay, historical backtest, and unknown basis order; each section preserves item-level `view_section` plus `primary_count` and `archive_count`; and tests cover section order, retrospective primary/archive mixed counts, and old retired-only archive behavior.
- Nonblocking follow-up retained for P4.3/P4.4: the page/API layer still needs to render these sections explicitly and show leakage/coverage notes before users can rely on the separation in the dashboard.

## Round 18 Review Result

Status: completed DeepSeek review.

Round 18 scope:

- P4.3 archive summary rows in `build_shortpick_strategy_archive_records`.
- Extended tests: `tests/test_shortpick_strategy_governance.py`.

Round 18 adds archive summary metadata only. It does not create an API route, wire a live page, write runtime data, or alter active strategy generation.

DeepSeek result:

- Blocking issues: none.
- Merge recommendation: merge and push Round 18.
- Key confirmations: archive detail `records` remain intact; `summary_rows` are grouped by evidence basis, strategy family, and entry-price source; only `archive_items` contribute to summary rows; date ranges, signal counts, completed observation counts, and retirement artifact counts are aggregated correctly; and tests cover empty archive summaries, multi-strategy aggregation, evidence-basis ordering, and preserved detail records.
- Nonblocking follow-up retained for P4.4/P4.5: summary rows still need page/API presentation plus leakage and coverage notes before they are dashboard-visible.

## Round 19 Review Result

Status: completed DeepSeek review.

Round 19 scope:

- P4.4 leakage and coverage note metadata in `project_shortpick_strategy_view_sections`.
- P4.4 archive preservation and fallback note construction in `build_shortpick_strategy_archive_records`.
- Extended tests: `tests/test_shortpick_strategy_governance.py`.

Round 19 adds projection/archive metadata only. It does not create an API route, wire a live page, write runtime data, execute leakage audits, or alter active strategy generation.

DeepSeek result:

- Blocking issues: none.
- Merge recommendation: merge and push Round 19.
- Key confirmations: projection rows now carry `leakage_coverage_note`; retrospective rows default missing `source_feature_cutoff_policy` to `signal_date_available_inputs_only`, default leakage status to `not_run`, and require display; archive records preserve projection notes or build a fallback from evidence packs; and tests cover retrospective notes, default cutoff policy, archive preservation, and archive fallback behavior.
- Nonblocking follow-up retained for P4.5: report/API/page surfaces still need to read and render these metadata fields before users can rely on them in the dashboard.

## Round 20 Review Result

Status: completed DeepSeek review.

Round 20 scope:

- P4.5 `strategy_governance_reporting` projection in `build_shortpick_replay_decision_projection`.
- API replay-feedback projection passthrough for existing `strategy_governance` payloads.
- Extended tests: `tests/test_shortpick_replay_readout.py`.

Round 20 adds readout/report metadata only. It does not create a new runtime writer, execute backtests, execute leakage audits, write paper-tracking rows, or alter active strategy generation.

DeepSeek result:

- Blocking issues: none.
- Merge recommendation: merge and push Round 20.
- Key confirmations: the report projection reads `recommended_status`, `evidence_basis`, `archive_records.summary_rows`, and `leakage_coverage_note` from governance contract inputs; missing governance inputs return `missing_artifact` with `may_infer_status_from_role_name=false`; API assembly only passes through existing `strategy_governance` data from replay feedback or overall payload; tests cover both missing and present governance inputs, including deliberate `tracking_role` distractors.
- Nonblocking follow-up retained for later display work: persisted report artifacts and dashboard pages still need to provide/render `strategy_governance` payloads before the new projection is visible to end users.

## Round 21 Review Result

Status: completed DeepSeek review.

Round 21 scope:

- Read-only API source wiring for `strategy_governance` inside replay-feedback projection.
- `_build_shortpick_strategy_governance_projection` fallback from already loaded paper-tracking ledger.
- Extended tests: `tests/test_shortpick_replay_api_projection.py`.

Round 21 makes the report governance projection source-backed in `/shortpick-lab/replay-feedback`. It does not write DB rows, execute backtests, execute leakage audits, create retirement artifacts, write paper-tracking rows, or alter active strategy generation.

DeepSeek result:

- Blocking issues: none.
- Merge recommendation: merge and push Round 21.
- Key confirmations: `_build_shortpick_strategy_governance_projection` uses only in-memory paper-tracking data and pure governance projection helpers; `_attach_shortpick_replay_decision_projection` prefers existing `strategy_governance` payloads and only falls back to the paper-tracking ledger when absent; empty ledgers return `missing_source` and do not infer status from role names; tests cover normal ledger projection plus empty-ledger behavior.
- Nonblocking follow-up retained for later display work: dashboard pages still need to render `strategy_governance_reporting` for users.

## Validation To Run For This Planning Task

- `git status --short --branch`
- `PYTHONPATH=src python3 -m pytest tests/test_shortpick_strategy_governance.py`
- `python3 -m compileall -q src/ashare_evidence/shortpick_strategy_governance.py`
- `python3 -m json.tool` for modified registry and added schema files
- `PYTHONPATH=src python3 -m pytest tests/test_contract_registry.py`
- `PYTHONPATH=src python3 -m ashare_evidence.cli contract-registry-check --registry docs/contracts/registry/autonomous_flow_registry.v1.json --docs docs/contracts/SHORTPICK_STRATEGY_GOVERNANCE_PLAN_2026-06-10.md --fail-on-unregistered --fail-on-deprecated`
- `PYTHONPATH=src python3 -m ashare_evidence.cli contract-registry-check --registry docs/contracts/registry/autonomous_flow_registry.v1.json --docs docs/contracts/SHORTPICK_STRATEGY_INVENTORY_2026-06-10.md --fail-on-unregistered --fail-on-deprecated`
- Markdown inspection for required sections: background, summary, implementation status, and acceptance criteria.
- DeepSeek read-only review against this file, `DECISIONS.md`, and `docs/contracts/PHASE5_RESEARCH_CONTRACT.md`.

## Current Completion State

| Area | Status |
| --- | --- |
| Worktree created | completed |
| Plan document drafted | completed |
| DECISIONS entry added | completed |
| Round 1 DeepSeek review | completed |
| P0 governance protocols drafted | completed |
| Round 2 DeepSeek review | completed |
| P1 registry contracts drafted | completed |
| Round 3 DeepSeek review | completed |
| P2.1 strategy/control inventory | completed |
| Round 4 DeepSeek review | completed |
| P2.2 evidence-pack builder | completed |
| Round 5 DeepSeek review | completed |
| P2.3 status recommendation layer | completed |
| Round 6 DeepSeek review | completed |
| P2.4 generation filter helper | completed_partial_runtime_wiring_pending |
| Round 7 DeepSeek review | completed |
| P2.5 view projection helper | completed_partial_frontend_wiring_pending |
| Round 8 DeepSeek review | completed |
| P2.6 archive record helper | completed |
| Round 9 DeepSeek review | completed |
| P3.1 same-symbol cooldown helper | completed_partial_runtime_wiring_pending |
| Round 10 DeepSeek review | completed |
| P3.2 drawdown/reversal filter helper | completed_partial_runtime_wiring_pending |
| Round 11 DeepSeek review | completed |
| P3.3 repeated exposure limit helper | completed_partial_runtime_wiring_pending |
| Round 12 DeepSeek review | completed |
| P3.4 historical backtest request builder | completed_partial_runner_wiring_pending |
| Round 13 DeepSeek review | completed |
| P3.5 retrospective forward replay request builder | completed_partial_runner_wiring_pending |
| Round 14 DeepSeek review | completed |
| P3.6 true forward tracking activation plan | completed_partial_runtime_wiring_pending |
| Round 15 DeepSeek review | completed |
| P4.1 strategy status labels | completed_partial_display_wiring_pending |
| Round 16 DeepSeek review | completed |
| P4.2 evidence-basis display sections | completed_partial_display_wiring_pending |
| Round 17 DeepSeek review | completed |
| P4.3 archive summary rows | completed_partial_display_wiring_pending |
| Round 18 DeepSeek review | completed |
| P4.4 leakage and coverage notes | completed_partial_display_wiring_pending |
| Round 19 DeepSeek review | completed |
| P4.5 analytical report governance projection | completed_partial_page_rendering_pending |
| Round 20 DeepSeek review | completed |
| Replay-feedback governance source wiring | completed_partial_page_rendering_pending |
| Round 21 DeepSeek review | completed |
| Runtime behavior changed | completed_for_read_only_replay_feedback_projection |
| Registry changed | completed |
| Strategy code changed | completed_for_read_only_governance_builder_status_layer_filter_view_projection_archive_same_symbol_cooldown_drawdown_reversal_repeated_exposure_helpers_historical_backtest_request_builder_retrospective_forward_replay_request_builder_true_forward_activation_plan_status_label_projection_evidence_basis_sections_archive_summary_rows_leakage_coverage_notes_report_governance_projection_and_replay_feedback_source_wiring |
| Frontend helper code changed | completed_for_strategy_status_and_evidence_basis_label_helpers |
| Runtime data changed | not_started |
| DeepSeek plan review | completed |

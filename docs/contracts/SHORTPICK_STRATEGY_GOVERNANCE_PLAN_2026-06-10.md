# Short Pick Strategy Governance Plan 2026-06-10

Status: paper_effect_chart_theme_strategy_filter_published_runtime_verified
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
   - Controls that operate on the frozen ranked pool must use `filter_ranked_pool_select_first_allowed`: start from the frozen strategy's ranked candidate pool, apply the control as a filter, and select only the highest-ranked candidate that passes. A blocked original rank1 is audit metadata, not a buy row.

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
| P2.3 | Mark candidates as `active`, `observe`, `retire_candidate`, or `retired` | completed_runtime_artifact_source_wired_ds_reviewed | Added a read-only status recommendation layer. Metrics alone can only produce `active`, `observe`, or `retire_candidate`; `retired` requires a valid `strategy_retirement:v1` / `shortpick_strategy_retirement` artifact plus `decision_log_ref`. Round 38 adds a retirement artifact writer; Round 39 wires runtime/API artifact-source discovery into status recommendation projection and paper-tracking governance partition. |
| P2.4 | Remove retired strategies from active generation | completed_generation_path_wired_ds_reviewed | Added a read-only generation eligibility filter that excludes only `recommended_status=retired` by default and keeps `retire_candidate`, `observe`, and `untracked` eligible. Archive rebuild can explicitly pass `include_retired=True`. Round 39 lets API projections consume retirement artifacts. Round 40 wires the active shortpick market-factor generation paths to read the runtime retirement artifact source, apply the eligibility filter before validation/commit, delete excluded in-transaction candidates, and report `generation_governance` in overlay summaries. |
| P2.5 | Remove retired strategies from primary frontend views | completed_runtime_frontend_wired_published_verified | Initial Round 8 helper sent `retired` rows to archive. Later rounds completed runtime/frontend wiring: Round 29 added paper-tracking governance partitioning, Round 30 rendered deprecated/archive buckets, P4.1-P4.5 added governance/evidence-basis reporting, and Rounds 21-24 published and runtime-verified the replay-feedback governance projection. The later Round 28 amendment also moves `retire_candidate` and `inventory_archived` rows out of the primary paper-tracking view; P2.7 tracks the remaining continued-advancement/generation question separately. |
| P2.6 | Preserve archived statistics and evidence refs | completed | Added a read-only archive record helper that builds audit records only from archive rows and preserves signal counts, completed sample counts, horizon summaries, historical evidence refs, baseline refs, and retirement artifact refs. It does not delete or persist data. |

### P3 - New Diagnostic Controls

| ID | Work Item | Status | Notes |
| --- | --- | --- | --- |
| P3.1 | Same-symbol cooldown control | completed_true_forward_runtime_wired_ds_reviewed | Added a deterministic rule builder and pure input-to-output cooldown helper. Round 54 wires it into daily runtime as a true-forward filter-and-reselect control over the frozen low-turnover ranked pool. Runtime state reads only same-control, post-`rule_defined_at` completed negative outcomes plus the true-forward signal-date calendar; it emits `rule_signature`, `evidence_basis=true_forward_tracking`, and selected/blocked-ranked metadata. Historical/replay generation remains separately labeled. |
| P3.2 | Drawdown/reversal filter control | completed_true_forward_runtime_wired_ds_reviewed | Added a deterministic rule builder and pure input-to-output filter helper. Round 54 wires it into daily runtime as a true-forward filter-and-reselect control over the frozen low-turnover ranked pool. Signal-date drawdown/reversal features are computed from signal-date-or-prior daily bars and persisted into candidate payload metadata; retrospective artifacts remain separate from true-forward rows. |
| P3.3 | Repeated exposure limit control | completed_true_forward_runtime_wired_ds_reviewed | Added a deterministic rule builder and pure input-to-output exposure-limit helper. Round 54 wires it into daily runtime as a true-forward filter-and-reselect control over the frozen low-turnover ranked pool. Runtime state reads only same-control, post-`rule_defined_at` prior signal rows and ignores same-day/future exposure rows. |
| P3.4 | Historical backtest generation | completed_filter_reselect_semantics_wired | Added a deterministic historical-backtest generation request builder. Round 34 added a gated runner and artifact persistence path. Round 35 adds explicit executable portfolio strategy mappings for the three registered P3 controls. Round 52 corrects these mappings to use filter-and-reselect semantics: for each signal day, only the highest-ranked allowed candidate is selected, and stateful controls use prior selected rows rather than treating every allowed row as a buy. |
| P3.5 | Retrospective forward replay generation | completed_filter_reselect_runtime_ranked_pool_replay_materialized | Added a deterministic retrospective-forward-replay request builder. Round 36 added a replay runner and artifact persistence path. Round 51 generated ready runtime artifacts, but the user clarified that controls are alternative filter-and-reselect strategies, not allowed/blocked overlays on already-selected paper rows. Round 52 therefore superseded the Round 51 artifacts as strategy evidence: replay results require a ranked candidate pool and output one selected row per signal date per control, or an explicit no-trade row if all ranked candidates are blocked. Round 53 reconstructs the frozen low-turnover ranked candidate pools from signal-date market bars, reruns the three P3 runtime replay artifacts, and verifies all three are `ready`. |
| P3.6 | True forward tracking start | completed_true_forward_runtime_wired_ds_reviewed | Added a deterministic true-forward activation-plan helper. Round 54 wires the registered controls into the live market-factor generation path from `rule_defined_at=2026-06-10` onward. Runtime candidate insertion remains forward-only and does not backfill paper rows; retrospective combined-ledger artifacts remain historical evidence only. |

### P4 - Frontend And Reporting

| ID | Work Item | Status | Notes |
| --- | --- | --- | --- |
| P4.1 | Add strategy status labels | published_runtime_verified | Added backend view-projection label metadata for governance status and evidence basis, plus frontend label/color helpers for active, observe, retire-candidate, retired, historical-only, retrospective-only, and true-forward states. The replay decision page now renders strategy governance projection labels; runtime and canonical browser verification completed for the UI path. |
| P4.2 | Add separate display sections for evidence basis | published_runtime_verified | Added backend view-projection sections that split true-forward tracking, retrospective replay, and historical backtest rows while preserving primary/archive membership in each section. The replay decision page now renders evidence-basis summary; runtime and canonical browser verification completed for the UI path. |
| P4.3 | Add retirement archive view or archive summary rows | published_runtime_verified | Added archive summary rows grouped by evidence basis, strategy family, and entry-price source while preserving detailed archive records. The replay decision page now renders archive fallback rows; runtime and canonical browser verification completed for the UI path. |
| P4.4 | Add leakage and coverage notes | published_runtime_verified | Added leakage/coverage note metadata to strategy view projection and archive records. Retrospective rows default to showing signal-date cutoff policy and leakage audit status. The replay decision page now renders audit rows; runtime and canonical browser verification completed for the UI path. |
| P4.5 | Update analytical report generation | published_runtime_verified | Added replay readout/report projection that reads strategy governance recommendations, view sections, archive summaries, and leakage notes from governance contract fields. `/shortpick-lab/replay-feedback` builds a read-only governance source from the already loaded paper-tracking ledger when no persisted governance payload exists, and the Shortpick replay decision page renders it. Runtime and canonical browser verification completed for the UI path. |
| P4.6 | Add paper-tracking strategy effect charts | published_runtime_verified | Adds the `策略纸面对照效果` chart panel directly inside `纸面跟踪记录（正式策略与对照组）`. The chart uses `机械5日`, `机械10日`, and `止盈止损` as ECharts series, excludes meaningless 1日/3日 exits, and links chart clicks to the existing record-group and exit-result table filters. The chart source follows current search/group/entry filters but intentionally ignores the table's exit-result filter so all three series remain comparable after linkage. DeepSeek review found no blockers; publish verification passed 19/19, and browser verification confirmed the chart panel, series legend, and table-filter linkage in the live dashboard. |
| P4.7 | Correct paper effect chart UX and theme behavior | published_runtime_verified | Removes the implementation-description sentence from the chart header and tooltip content, adds a cumulative-chart strategy selector that defaults to `冻结策略` when present, and moves chart colors/surfaces/tooltips to shared CSS variables plus a reusable ECharts theme-revision helper so canvas charts redraw on light/dark theme changes. DeepSeek review found the initial tooltip wording blocker, the wording was removed, and the follow-up review marked the change mergeable. Publish verification passed 19/19, and browser verification confirmed live dark/light rendering plus strategy switching. |

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

- Do not insert retrospective rows as if they were true-forward rows. A retrospective row may share the same combined ledger/table as true-forward rows (per the Round 28 amendment) only when it carries a non-null `evidence_basis` plus the `retrospective=true` flag and is never represented, queried, aggregated, or counted as `true_forward_tracking`.
- Do not display retrospective rows in the same headline as true-forward rows without a basis split.
- Do not use future-known outcomes to tune thresholds and then describe the replay as unbiased.
- Do not call a replayed control "frozen" for dates before the rule was registered.

Display policy:

- Historical, retrospective, and true-forward rows must be visually separated by section or basis label.
- A combined table is allowed only when `evidence_basis` is a visible column and default grouping keeps true-forward rows separate.
- Headline metrics for promotion or retirement must default to true-forward rows; retrospective rows can appear only as supporting research evidence.
- Any retrospective replay over thresholds tuned after seeing outcomes must be labeled `tuned_research`, not `validation`.
- Per the Round 28 amendment, retrospective backfill rows are stored in the same combined ledger/table as their true-forward counterparts so the user gets a convenient side-by-side comparison, but every row keeps a mandatory `evidence_basis` and the retrospective rows carry a `pairing_key` (`control_group_id` + `rule_signature` + `symbol` + `signal_date`) that links each replay row to its matching true-forward row without merging the two bases.

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
- The Round 28 amendment authorizes the first implementation round that intentionally changes display and advancement behavior: once that round lands, evidence-based hiding from the primary frontend is driven by `recommended_status` (not merely by the plan's existence), so it remains consistent with the rule above that no strategy is hidden solely because this plan exists.

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

## Round 22 Review Result

Status: completed DeepSeek review.

Round 22 scope:

- Frontend rendering of `overall.strategy_governance_reporting` in `ReplayDecisionReadout`.
- Type exposure for `strategy_governance_reporting`.
- Extended static frontend test coverage.

Round 22 makes governance projection visible in the Shortpick replay decision UI. It does not write runtime data, execute backtests, execute leakage audits, create retirement artifacts, or alter active strategy generation.

DeepSeek result:

- Blocking issues: none.
- Merge recommendation: merge and push Round 22.
- Key confirmations: the page renders a visible strategy governance projection section with primary/archive counts, status counts, evidence sections, and leakage/coverage or archive rows; missing governance projection states that the page will not infer status from `tracking_role` or role name; type/static tests cover the new field and visible text.
- Nonblocking finding addressed before merge: the table fallback header was changed from `泄漏 / 覆盖` to `审计 / 归档` so archive fallback rows are not mislabeled.
- Browser verification: local Vite + API run with controlled replay endpoint fixtures rendered `策略治理投影`, `页面不按 tracking_role 推断`, `读取 recommended_status，不读取 role name`, `审计 / 归档`, and `retro-candidate`; screenshot saved at `/tmp/round22-shortpick-governance-ui-mocked-clean.png`.
- Remaining follow-up: live deployment verification is required before claiming user-visible production availability.

## Round 23 Publish Result

Status: completed local runtime publish and canonical browser verification.

Publish scope:

- Published commit `b6948c8fff828895f0c85f0af86a4ed93a1cee3f` to local runtime `/Users/hernando_zhao/codex/runtime/projects/ashare-dashboard`.
- Used `ASHARE_PUBLISH_REFRESH_MODE=skip` because this round only changed frontend rendering and read-only projection code.
- First canonical release verifier attempt timed out while fingerprinting local API JSON, after runtime sync and LaunchAgent restart had already completed. The root cause has not yet been investigated and may affect later full canonical publish verification. The follow-up local publish closeout succeeded and wrote `output/releases/local-20260610T075038Z-b6948c8.json`; this is accepted as an interim closeout for this UI-path publish, not as a replacement for full canonical verifier health.

Verification evidence:

- Runtime manifest `latest-successful.commit` now points to `b6948c8fff828895f0c85f0af86a4ed93a1cee3f`.
- Runtime health passed at `http://127.0.0.1:8000/health`; runtime frontend served asset hash `assets/index-2b30162a.js`.
- Canonical `https://hernando-zhao.cn/projects/ashare-dashboard/` with dev auth served the same new asset hash `assets/index-2b30162a.js`.
- Playwright against runtime frontend `http://127.0.0.1:5173/?view=shortpick&shortpickTab=replay` with controlled replay endpoint fixtures rendered `策略治理投影`, `页面不按 tracking_role 推断`, `读取 recommended_status，不读取 role name`, `审计 / 归档`, and `retro-candidate`; no page errors or console errors; screenshot `/tmp/round22-shortpick-governance-ui-runtime.png`.
- Playwright against canonical frontend `https://hernando-zhao.cn/projects/ashare-dashboard/?view=shortpick&shortpickTab=replay` with dev auth and controlled replay endpoint fixtures rendered the same governance projection UI; no page errors or console errors; screenshot `/tmp/round22-shortpick-governance-ui-canonical.png`.

Data-source caveat:

- The real runtime `/shortpick-lab/replay-feedback` response currently does not include `overall.strategy_governance_reporting`, so the unmocked page may still show the guarded missing-projection state until runtime data contains a paper-tracking/governance source suitable for the Round 21 fallback.
- When real runtime data eventually includes `overall.strategy_governance_reporting`, the already-published frontend code path should render the projection without another UI code change. A follow-up round must still verify that transition against unmocked runtime data before claiming full real-data end-to-end completion.

## Round 24 Review Result

Status: completed DeepSeek review.

Round 24 scope:

- Added `_build_shortpick_replay_aggregate_feedback_response(session)` so `/shortpick-lab/replay-feedback` enriches an existing ready frontend projection through `_attach_shortpick_replay_decision_projection(...)` instead of returning the stale projection payload directly.
- Kept cache fallback behavior unchanged when no ready frontend projection exists.
- Added a focused regression test proving a ready replay feedback projection still goes through enrichment and does not fall back to the replay feedback cache.

Runtime verification before merge:

- A temporary worktree API on `127.0.0.1:18081`, pointed at the runtime SQLite database, returned `overall.strategy_governance_reporting` from the real old ready projection path.
- Observed governance projection values: `status=ready`, `primary_count=32`, `archive_count=0`, `sections=1`, `may_infer_status_from_role_name=false`.

DeepSeek result:

- Blocking issues: none.
- Merge recommendation: can merge and publish.
- Key confirmations: old ready projections are copied and enriched without mutating the stored projection payload; `overall.update(...)` only overwrites known decision-projection keys while preserving unrelated fields; repeated enrichment is request-local and effectively idempotent.
- Nonblocking follow-up: `/shortpick-lab/replay-feedback` now performs artifact reads plus paper-tracking ledger/governance calculations even when a ready projection exists. Add a short TTL cache if this endpoint becomes a hot path.

Publish and real-data verification:

- Published commit `ec959e918ef715fab4ed938aca7000fa125a355e` to local runtime with `ASHARE_PUBLISH_REFRESH_MODE=skip` and `ASHARE_PUBLISH_VERIFY_MODE=local`; release manifest `output/releases/local-20260610T080441Z-ec959e9.json`.
- Runtime manifest `latest-successful.commit` points to `ec959e918ef715fab4ed938aca7000fa125a355e`.
- Real local API `http://127.0.0.1:8000/shortpick-lab/replay-feedback` returned `overall.strategy_governance_reporting` with `status=ready`, `primary_count=32`, `sections=1`, and `may_infer_status_from_role_name=false`.
- Real canonical API `https://hernando-zhao.cn/projects/ashare-dashboard/api/shortpick-lab/replay-feedback` with dev auth returned the same governance projection values.
- Playwright against real local frontend `http://127.0.0.1:5173/?view=shortpick&shortpickTab=replay` rendered `策略治理投影`, `页面不按 tracking_role 推断`, `读取 recommended_status，不读取 role name`, `主区策略`, and count `32`; no page errors or console errors; screenshot `/tmp/round24-shortpick-governance-real-local.png`.
- Playwright against real canonical frontend `https://hernando-zhao.cn/projects/ashare-dashboard/?view=shortpick&shortpickTab=replay` with dev auth rendered the same real-data governance projection UI; no page errors or console errors; screenshot `/tmp/round24-shortpick-governance-real-canonical.png`.

## Round 25 Review Result

Status: completed DeepSeek review after blocker repair.

Round 25 scope:

- Hardened `src/ashare_evidence/release_verifier.py` so raw `TimeoutError` / `OSError` from URL requests are reported as `ReleaseVerificationError` with method, URL, and timeout seconds.
- Added explicit operations `sample_symbol` handling for bounded `/dashboard/operations/*` verifier endpoints.
- Added a two-stage operations verifier flow: first warm local and canonical operations endpoints with `--operations-warmup-timeout-seconds`, then run the normal shorter API fingerprint comparison on warmed caches.
- Added `api_warmups`, request endpoints, durations, and payload byte counts to the release manifest so slow verifier endpoints are auditable.
- Updated `scripts/publish-local-runtime.sh` to pass the release operations sample/warmup settings, pause scheduled refresh before publish, wait for scheduled refresh lock/process quiescence, restore the LaunchAgent through `cleanup_on_exit`, and acquire an atomic `mkdir`-based publish lock.
- Added regression/static tests for timeout wrapping, operations endpoint sampling, manifest warmup records, publish quiescence, verifier arguments, and atomic publish locking.

Investigation evidence:

- Direct local endpoint probes showed cold operations details could exceed the old 20-second verifier budget; with an active scheduled refresh, `/dashboard/operations/details?section=portfolios&sample_symbol=600519.SH` exceeded even a 90-second warmup timeout.
- Process inspection during the timeout showed `phase5-daily-refresh --analysis-only` and scheduled-refresh wrapper processes running with `run.lock` held by the scheduled refresh. This confirmed the full verifier must not run concurrently with DB-heavy scheduled refresh.
- Because the current runtime had an active scheduled refresh, the full canonical verifier was not forced in this worktree. The new publish script now waits for quiescence and refuses to publish if the DB-heavy refresh remains active past `ASHARE_PUBLISH_SCHEDULED_REFRESH_QUIESCE_TIMEOUT_SECONDS`.

Verification evidence:

- `PYTHONPATH=src python3 -m pytest tests/test_release_verifier.py tests/test_publish_script_static.py` passed (`19 passed`).
- `bash -n scripts/publish-local-runtime.sh` passed.
- `python3 -m compileall -q src/ashare_evidence/release_verifier.py` passed.
- `python3 -m ruff check src/ashare_evidence/release_verifier.py tests/test_release_verifier.py tests/test_publish_script_static.py` passed.
- `git diff --check` passed.

DeepSeek result:

- Initial DS review: release verifier warmup/sample/duration changes were reasonable; publish pause/wait/resume ordering had no fatal issue, but the existing publish lock was a merge-blocking TOCTOU risk.
- Follow-up fix: changed publish locking to atomic `mkdir "$PUBLISH_LOCK_DIR"` with stale-lock recovery and test coverage.
- DS rereview: the publish-lock blocker is resolved; no remaining must-fix issue before merge.
- Nonblocking DS followups: trap setup could be moved closer to lock acquisition in a later cleanup; stale-lock recovery can be tightened further for highly automated concurrent publish scenarios; `_request_text` and `_request_bytes` could share a helper.

## Round 26 Review Result

Status: completed DeepSeek review.

Round 26 scope:

- Added a short module-level TTL cache for `_build_shortpick_replay_aggregate_feedback_response(...)` so repeated `/shortpick-lab/replay-feedback` reads do not repeatedly enrich ready replay projections with artifact reads and paper-tracking/governance calculations.
- Default TTL is `15` seconds via `ASHARE_SHORTPICK_REPLAY_AGGREGATE_FEEDBACK_TTL_SECONDS`; values `<=0` disable the cache.
- Cached payloads are protected with `copy.deepcopy` on write and read so callers cannot mutate the cached object.
- Added `_clear_shortpick_replay_aggregate_feedback_cache()` for deterministic tests.
- Added a regression test proving TTL hits avoid repeated enrichment, returned payloads are independent copies, and TTL expiry refreshes the enriched response.

Verification evidence:

- `PYTHONPATH=src python3 -m pytest tests/test_shortpick_replay_api_projection.py` passed (`5 passed`).
- `python3 -m compileall -q src/ashare_evidence/api.py` passed.
- `python3 -m ruff check src/ashare_evidence/api.py tests/test_shortpick_replay_api_projection.py` passed.
- `git diff --check` passed.

DeepSeek result:

- Blocking issues: none.
- Correctness and permission review: the endpoint already returns the same aggregate payload for all authenticated stock users, so the single-key cache does not add a cross-user leak; a 15-second freshness window is acceptable for the read-only dashboard use case and can be disabled.
- Concurrency review: module-level lock protects cache tuple reads/writes and deepcopy prevents object pollution.
- Nonblocking followups: cold/expired concurrent requests can still stampede and compute the same payload more than once; the miss path does two deep copies; tests do not yet cover TTL disabled, fallback cache source, or concurrent request behavior.

Publish and runtime verification:

- Published merge commit `4b9ac44ec337d8ed958702bfa82feb004aea1516` to local runtime with `ASHARE_PUBLISH_REFRESH_MODE=skip`, `ASHARE_PUBLISH_VERIFY_MODE=canonical`, `ASHARE_RELEASE_TIMEOUT_SECONDS=25`, and `ASHARE_RELEASE_OPERATIONS_WARMUP_TIMEOUT_SECONDS=90`.
- Canonical release parity verifier passed and wrote manifest `/Users/hernando_zhao/codex/runtime/projects/ashare-dashboard/output/releases/20260610T084401Z-4b9ac44ec337/manifest.json`; `api_warmups` captured 8 operations endpoints.
- Post-deploy verification passed (`19 passed, 0 failed`), backend health passed at `http://127.0.0.1:8000/health`, and frontend health passed at `http://127.0.0.1:5173/`.
- Real local API `/shortpick-lab/replay-feedback` returned HTTP 200 with `overall.strategy_governance_reporting.status=ready`, `primary_count=32`, `archive_count=0`, and `source_policy=read_governance_projection_not_role_names`.
- Consecutive local API calls demonstrated the runtime TTL cache effect: first call `5.483s`, second call `0.085s`, same payload size.
- Real canonical API `https://hernando-zhao.cn/projects/ashare-dashboard/api/shortpick-lab/replay-feedback` with dev auth returned HTTP 200 and the same governance status/source policy.

## Round 27 Review Result

Status: completed DeepSeek review.

Round 27 scope:

- Consolidated the nonblocking test-hardening follow-ups that earlier DeepSeek rounds retained for later (Round 6 status-recommendation gates, Round 10 same-symbol cooldown, Round 13 historical-backtest request builder).
- Extended tests only: `tests/test_shortpick_strategy_governance.py` (12 new tests, 51 -> 63).

Round 27 adds tests only. It does not change strategy code, registry, schemas, runtime data, frontend, or API behavior, so it stays inside the contract-only transition rule.

New test coverage:

- Round 6: positive registered baseline gap blocks `retire_candidate` and falls to `observe`; mixed positive-mean / negative-median tail-dependent evidence still reaches `retire_candidate`; an incomplete retirement artifact missing `decision_log_ref` cannot produce `retired`; list-form `{"artifacts": [...]}` retirement source resolves to `retired`; empty/missing packs return `strategy_count=0`; a requested `primary_horizon_days` with no matching summary falls back to the first horizon summary instead of dropping to `observe`.
- Round 10: same-symbol cooldown handles empty inputs with zero counts and a default rule signature; the default-rule path uses `cooldown_signal_days=5` and `control_same_symbol_cooldown:v1`; threshold-equality boundaries are pinned (a `-0.08` outcome equals the severe threshold and selects the longer severe window; a `0.0` outcome equals `loss_return_threshold` and is excluded as a non-loss).
- Round 13: `min_signal_symbol_count <= 0` raises; empty `control_rules` yields zero requests; `same_close_proxy` is accepted as an entry-price source and produces a single labeled request.

Verification evidence:

- `PYTHONPATH=src python3 -m pytest tests/test_shortpick_strategy_governance.py` passed (`63 passed`).
- `PYTHONPATH=src python3 -m pytest` fast suite passed (`727 passed, 1 skipped, 161 deselected, 6 subtests passed`).
- `python3 -m ruff check tests/test_shortpick_strategy_governance.py` passed.
- `python3 -m compileall -q tests/test_shortpick_strategy_governance.py` passed.
- `git diff --check` passed.

DeepSeek result:

- Blocking issues: none.
- Merge recommendation: merge.
- Key confirmations: all 12 new tests assert behavior the implementation in `src/ashare_evidence/shortpick_strategy_governance.py` actually produces, verified gate-by-gate (baseline blocker branch, tail-dependence conjunct, retirement-authority requirement, list-form artifact lookup branch, empty-pack comprehension, horizon fallback, cooldown threshold-equality `<=` / `>=` boundaries, entry-source set membership); the tests are genuine new-boundary coverage rather than tautological restatements or duplicates of existing assertions; and the test-only change implies no runtime, data, frontend, or strategy-code change.

## Round 28 Intent-Clarification Amendment

Status: requirements recorded; runtime implementation started in later rounds.

This round does not change code, runtime, data, frontend, registry, or schemas. It records the project owner's clarified original intent so later implementation rounds do not drift from it. The owner confirmed three goals and resolved two open questions that the prior rounds had deliberately left to a decision.

Owner intent (verbatim sense):

1. Add more credible control/comparison lines from the current data.
2. There are too many poorly-performing or meaningless control groups; archive their data and display so they are no longer shown on the primary frontend and are no longer advanced.
3. New lines must first run historical backtest, then backfill data inside paper tracking, but with an extra label.

Resolved decisions:

- Decision A (cleanup semantics for poorly-performing controls). "Cleanup" means: remove the control from the **primary frontend display and from continued advancement**, while **retaining its data** and **migrating or marking it into a deprecated/archived bucket** with a **regression guard** so it cannot silently re-enter active generation or the primary view.
  - Mapping to existing status model: `active` and `observe` remain in the primary view (still under watch). Evidence-based `retire_candidate` and `retired` are moved to the deprecated/archived bucket, are not advanced, and keep their data.
  - This is stricter than the original P2.5 (which only archived `retired`). The amendment intentionally also removes `retire_candidate` from the primary frontend, because the owner wants poorly-performing controls hidden once the evidence is clear, not only after a full durable retirement artifact exists.
  - The durable `retired` record still requires a `strategy_retirement:v1` artifact plus `decision_log_ref`; the un-retirement protocol still governs any return to `active`/`frozen`. The deprecated bucket is the regression guard: leaving it requires the governed recovery path, never an automatic re-promotion.
  - "Meaningless/redundant" controls (distinct from poorly-performing ones) are out of scope for the metric retirement gates and are handled as a separate inventory-driven archival decision; they must not be force-fit into the performance gates, and the diagnostic-value gate still protects a weak control that tests a unique hypothesis.

- Decision B (retrospective backfill location). Backfilled retrospective data is stored in the **same combined ledger/table** as the true-forward rows (so the frontend can display a convenient comparison), **not** in a physically separate ledger. The anti-leakage guarantee is preserved by labeling rather than by physical separation:
  - Every row carries a mandatory non-null `evidence_basis`; retrospective rows also carry `retrospective=true`, `rule_defined_at`, and the leakage-audit fields.
  - Retrospective rows are never represented, queried, aggregated, or counted as `true_forward_tracking`. True-forward headline, promotion, and retirement metrics filter to `evidence_basis=true_forward_tracking` by default.
  - Each retrospective row carries a `pairing_key` (`control_group_id` + `rule_signature` + `symbol` + `signal_date`) linking it to its matching true-forward row for side-by-side comparison.
  - This supersedes the earlier "physically separate ledger" reading of the retrospective contract while keeping all of its leakage protections.

New implementation requirement items (status `not_started`, scoped for later runtime/data rounds):

| ID | Work Item | Status | Notes |
| --- | --- | --- | --- |
| P2.7 | Deprecated/archived display bucket plus regression guard | published_runtime_verified | Round 29 added the paper-tracking governance partition; Round 30 moves evidence-based `retire_candidate` and `retired` rows out of the paper-tracking primary frontend table and latest simulated trade surface into a collapsed deprecated/archive bucket. Round 56 closes continued-advancement/generation wiring: `retire_candidate`, `retired`, and `inventory_archived` are all treated as deprecated generation statuses and are excluded from active market-factor generation unless an explicit archive/diagnostic rebuild opt-in is passed. Runtime publish and visible page verification completed at commit `85c9add48a4d70f94cbede9da1f7b3c12b877d3a`. |
| P2.8 | Redundant/meaningless control inventory archival | published_runtime_verified | Round 31 added an inventory-driven archival decision helper, generation exclusion, paper-tracking deprecated-bucket partitioning, API summary fields, and frontend status fallback for `inventory_archived`. Round 56 adds a durable `shortpick_control_inventory_archive` artifact source, reads it in both paper-tracking API projection and active generation governance, exposes artifact/decision counts to the frontend, and preserves the rule that only `decision_basis=inventory_diagnostic_value` with allowed reason codes can archive a redundant control. Runtime publish and visible page verification completed at commit `85c9add48a4d70f94cbede9da1f7b3c12b877d3a`. |
| P3.7 | Labeled combined-ledger retrospective backfill with true-forward pairing | completed_filter_reselect_runtime_materialized_api_verified | Round 32 added a combined-ledger backfill preparation helper that materializes already-produced retrospective replay rows with mandatory `evidence_basis=retrospective_forward_replay`, `retrospective=true`, `rule_defined_at`, leakage-audit fields, deterministic `pairing_key`, and headline-safe true-forward basis filtering. Round 36 adds replay artifact rows that can feed this helper. Round 37 adds an artifact-only combined-ledger writer/CLI that persists labeled combined rows without writing the database. Round 41 wires runtime artifact-store discovery into `/shortpick-lab/paper-tracking` as a separate `combined_ledger` API block without merging retrospective rows into primary `items`; DeepSeek-reviewed hardening restricts combined-ledger artifact rows to `true_forward_tracking` or `retrospective_forward_replay`. Round 42 adds frontend types and a separate paper-tracking display block for `combined_ledger` rows with visible evidence-basis labels. Round 43 published and served-verified the frontend/API shape. Round 44 adds automatic discovery/materialization from ready governance replay artifacts. Round 51's 777-row overlay artifact was removed in Round 52. Round 53 materializes the corrected filter-and-reselect runtime combined ledger with 66 retrospective rows from three ready replay artifacts. |
| P3.8 | New credible control/comparison line build-out | completed_historical_gate_ranked_pool_replay_and_combined_ledger_runtime_verified | Round 33 added a credible-control comparison-line build-out plan for the three registered P3 controls and the two registered P1 baselines. Round 34 added the historical-backtest runner and evidence artifact persistence path. Round 35 adds executable control-to-portfolio strategy mappings for the three registered P3 controls. Round 45 adds a CLI to generate the credible-control comparison request plan from paper-tracking JSON without executing jobs or writing rows. Round 46 lets the existing historical-backtest and retrospective-replay execution CLIs consume the Round 45 nested credible-control plan shape directly. Round 47 lets the credible-control planner consume the historical-backtest runner aggregate output field `evidence` directly as gate input. Round 48 generated a current runtime credible-control plan, but the full three-request historical gate execution was interrupted after several minutes without writing an artifact. Round 49 adds request selectors to the historical-backtest and retrospective-replay execution CLIs. Round 50 passed the three runtime historical gates. Round 53 regenerates replay from reconstructed frozen ranked pools and materializes a corrected combined-ledger artifact visible from the runtime API. Paper-ledger writes remain intentionally not used; true-forward tracking still starts only in real forward time. |

These items remain blocked by the remaining runtime preconditions called out in earlier rounds: runtime/frontend wiring must exist before backfilled comparison rows are displayed as normal dashboard evidence. Round 34 removed the generic historical-backtest runner/artifact gap; Round 35 removed the missing P3 historical control-mapping gap for the three registered controls; Round 36 removes the retrospective replay runner/artifact gap without writing runtime ledger rows. Round 37 adds combined-ledger artifact materialization, but not DB/API/frontend consumption. Round 38 adds the `strategy_retirement:v1` artifact writer and aligns its schema with the existing retired-status authority check. Round 39 wires retirement artifact discovery into API governance projections and paper-tracking partitioning. Round 40 wires the same runtime retirement artifact source into active shortpick market-factor generation exclusion. Round 41 starts combined-ledger runtime/API consumption by exposing a separate artifact-backed `combined_ledger` block from paper tracking while deliberately keeping `items` as true-forward paper-tracking rows only.

## Round 29 Review Result

Status: completed DeepSeek review and merged before this Round 30 continuation.

Round 29 scope:

- Added `partition_paper_tracking_rows_by_governance(...)` and `GOVERNANCE_DEPRECATED_VIEW_STATUSES` to the Short Pick governance helper layer.
- Wired the governance partition into `_build_shortpick_paper_tracking_ledger(...)`, annotating paper-tracking rows with `governance_status`, `governance_strategy_id`, `governance_view_section`, and a `strategy_governance` summary block.
- Kept the change additive: no strategy was hidden, stopped, deleted, or backfilled in Round 29. The live ledger path passes no historical after-cost evidence, so deprecated count remains zero until governed evidence exists.
- Added partition tests plus paper-tracking API regression assertions.

Round 29 merge evidence:

- Commit `5cfd0b0` (`Wire governance partition into primary paper-tracking ledger (Round 29)`) was merged into main by `e35c4f9`.
- The plan document was not updated by that handoff round, so Round 30 records this durable status reconciliation.

## Round 30 Review Result

Status: completed DeepSeek review, merged, pushed, and runtime published.

Round 30 scope:

- Added frontend paper-tracking governance types for per-row governance fields and the `strategy_governance` summary.
- Added frontend helper functions `primaryPaperTrackingRows(...)`, `deprecatedPaperTrackingRows(...)`, and `paperTrackingGovernanceViewSection(...)`.
- The helper treats `governance_view_section=deprecated` and the fallback statuses `retire_candidate` / `retired` as deprecated, so a row cannot silently re-enter the primary frontend if the backend omits `governance_view_section`.
- Updated `PaperTrackingTab` so the main table, mobile list, counts, mechanical exit metrics, and latest simulated trade surface use primary rows only.
- Added a collapsed `已归档 / 废弃观察桶` table that retains deprecated row visibility without placing those rows in the primary surface.
- Added regression tests proving helper-level primary/deprecated partitioning, status-only deprecated fallback, and latest simulated trade fallback away from archived rows.

Verification evidence:

- `PYTHONPATH=src python3 -m pytest tests/test_frontend_shortpick_paper_tracking_helpers.py tests/test_frontend_shortpick_static.py tests/test_shortpick_strategy_governance.py` passed (`72 passed`).
- `npm --prefix frontend run build -- --mode production` passed.
- `PYTHONPATH=src python3 -m unittest tests.test_shortpick_lab_paper_tracking` passed (`6 tests`).
- `python3 -m ruff check tests/test_frontend_shortpick_paper_tracking_helpers.py tests/test_frontend_shortpick_static.py` passed.
- `git diff --check` passed.

DeepSeek result:

- Initial review found no broad UI blocker but identified a real regression risk: if a row had `governance_status=retire_candidate` / `retired` but no `governance_view_section=deprecated`, the first implementation could leak it into the primary frontend.
- Follow-up fix added status fallback classification and targeted tests for status-only deprecated rows plus latest simulated trade filtering.
- DeepSeek rereview confirmed the blocker is fixed and found no remaining merge-blocking issue.
- Nonblocking note retained: `latestPaperTrackingChoices(...)` and `latestFrozenPaperTrackingChoices(...)` assume their caller passes primary rows; production call sites now do that, and helper tests cover the intended calling contract.

Merge and publish evidence:

- Commit `71c6297` (`Add shortpick deprecated frontend bucket`) was merged into main by `ba79122`.
- Runtime publish was rerun with `ASHARE_PUBLISH_MAX_WAIT_SECONDS=180` after backend startup exceeded the default 30-second health window.
- Deploy verifier passed (`19 passed, 0 failed`), runtime frontend matched the repo build, backend health passed at `http://127.0.0.1:8000/health`, and frontend health passed at `http://127.0.0.1:5173/`.
- Scheduled refresh was resumed by the publish script after verification.

## Round 31 Review Result

Status: implementation completed; DeepSeek review passed; merged, pushed, and runtime published.

Round 31 scope:

- Added `build_shortpick_redundant_control_archive_decisions(...)` for inventory-driven archival of redundant or meaningless controls.
- Kept the path separate from performance retirement gates: archival requires `decision_basis=inventory_diagnostic_value` and an allowed inventory reason code; performance-style or missing-basis attempts are blocked.
- Extended `filter_shortpick_generation_eligible_items(...)` so `inventory_archived` controls are excluded from continued advancement by default, while archive rebuilds can opt in with `include_inventory_archived=True`.
- Extended `partition_paper_tracking_rows_by_governance(...)` so inventory-archived rows move to the deprecated bucket and carry `governance_archive_basis` plus the inventory decision payload.
- Wired the API paper-tracking ledger to evaluate `market_control_contract.inventory_archive_decisions` when present and expose inventory archive policy/count fields under `strategy_governance`.
- Added frontend fallback/label support for `inventory_archived`, so status-only archived rows cannot silently re-enter the primary paper-tracking surface.

DeepSeek result:

- Initial DeepSeek review found three merge-blocking gaps: strategy governance projection did not yet apply inventory archive decisions, API strategy projection did not pass those decisions into the view projection, and frontend latest-choice helpers still accepted deprecated/status-only rows when called directly.
- The implementation was updated to apply inventory archive decisions in `project_shortpick_strategy_view_sections(...)`, wire those decisions through `_build_shortpick_strategy_governance_projection(...)`, and make `latestPaperTrackingChoices(...)` plus `latestFrozenPaperTrackingChoices(...)` filter to primary rows internally.
- DeepSeek rereview returned `PASS`. One shard noted it could not independently inspect `project_shortpick_strategy_view_sections(...)`, but the source-code shard confirmed the original blockers were closed and found no remaining merge blocker.

Verification evidence before merge:

- `PYTHONPATH=src python3 -m pytest tests/test_shortpick_strategy_governance.py tests/test_shortpick_lab_paper_tracking.py tests/test_shortpick_replay_api_projection.py tests/test_frontend_shortpick_paper_tracking_helpers.py tests/test_frontend_shortpick_static.py` passed (`83 passed, 6 deselected`).
- `python3 -m ruff check src/ashare_evidence/shortpick_strategy_governance.py src/ashare_evidence/api.py tests/test_shortpick_strategy_governance.py tests/test_shortpick_lab_paper_tracking.py tests/test_shortpick_replay_api_projection.py tests/test_frontend_shortpick_paper_tracking_helpers.py tests/test_frontend_shortpick_static.py` passed.
- `python3 -m compileall -q src/ashare_evidence/shortpick_strategy_governance.py src/ashare_evidence/api.py` passed.
- `git diff --check` passed.
- `npm --prefix frontend run build -- --mode production` passed with the existing Vite chunk-size warning only.

Merge and publish evidence:

- Commit `97e5144` (`Add shortpick inventory archive governance path`) was merged into main by `0c4a245`.
- `git push origin main` completed; the pre-push hook passed stock_dashboard fast regression (`737 passed, 161 deselected, 6 subtests passed`) and policy governance audit.
- Runtime publish completed from release source `0c4a245ba019eb2bdf8ec4823f911783714fb2d5` with `ASHARE_PUBLISH_REFRESH_MODE=skip` and `ASHARE_PUBLISH_MAX_WAIT_SECONDS=180`.
- Deploy verifier passed (`19 passed, 0 failed`), runtime frontend matched the repo build, backend health passed at `http://127.0.0.1:8000/health`, and frontend health passed at `http://127.0.0.1:5173/`.
- Runtime API check confirmed `strategy_governance.inventory_archive_policy=inventory_diagnostic_value_archive_separate_from_performance_retirement`, `deprecated_status_set` includes `inventory_archived`, and current real-data inventory archive count remains `0`.
- Playwright CLI loaded the published frontend at `http://127.0.0.1:5173/?view=shortpick&shortpickTab=paper-tracking&symbol=002028.SZ`; the Short Pick Lab paper-tracking page rendered successfully.

## Round 32 Review Result

Status: implementation completed; DeepSeek review passed; merged and pushed.

Round 32 scope:

- Added `build_shortpick_combined_ledger_retrospective_backfill(...)` as a preparation/materialization layer for P3.7. It accepts already-produced retrospective replay rows plus optional true-forward rows and a replay request, then returns combined-ledger-ready rows without writing the database.
- Retrospective rows are forced to `evidence_basis=retrospective_forward_replay`, `retrospective=true`, `true_forward_tracking_eligible=false`, `headline_metric_eligible=false`, and `paper_tracking_write_policy=combined_ledger_backfill_only_with_evidence_basis`.
- The helper requires `control_group_id`, `rule_signature`, `rule_defined_at`, `signal_date`, and `symbol`; it blocks rows whose `signal_date` is not strictly before `rule_defined_at`, preserving the retrospective/true-forward boundary.
- Each valid retrospective row gets a deterministic `pairing_key` using `control_group_id|rule_signature|symbol|signal_date` plus a deterministic `combined_ledger_row_id`.
- Added `filter_shortpick_combined_ledger_rows_by_evidence_basis(...)` so headline/promotion/retirement queries can default to `evidence_basis=true_forward_tracking` and exclude retrospective rows by construction.

DeepSeek result:

- Blocking issues: none.
- Merge recommendation: merge.
- Key confirmations: the backfill preparation helper forces retrospective rows to `evidence_basis=retrospective_forward_replay`, `retrospective=true`, `rule_defined_at`, leakage-audit metadata, deterministic `pairing_key`, and no database write policy; it blocks rows whose `signal_date` is not strictly before `rule_defined_at`; and the basis-filter helper defaults headline-safe queries to `evidence_basis=true_forward_tracking`.
- Nonblocking suggestions: add explicit tests for empty inputs and true-forward inputs with a non-true-forward basis, and consider later duplicate-`pairing_key` diagnostics for repeated backfills.
- Follow-up applied before merge: added tests for empty input behavior and true-forward input rows carrying a retrospective basis. Duplicate pairing-key diagnostics remain a later hardening option because no runtime writer exists yet.

Verification evidence before merge:

- `PYTHONPATH=src python3 -m pytest tests/test_shortpick_strategy_governance.py` passed (`77 passed`).
- `python3 -m ruff check src/ashare_evidence/shortpick_strategy_governance.py tests/test_shortpick_strategy_governance.py` passed.
- `python3 -m compileall -q src/ashare_evidence/shortpick_strategy_governance.py tests/test_shortpick_strategy_governance.py` passed.
- `git diff --check` passed.

Merge evidence:

- Commit `c9a61fe` (`Add shortpick combined ledger backfill preparation`) was merged into main by `4c21ff7`.
- `git push origin main` completed; the pre-push hook passed stock_dashboard fast regression (`743 passed, 161 deselected, 6 subtests passed`) and policy governance audit.
- No runtime publish was required because Round 32 added read-only helper logic, tests, and planning documentation only; it did not change API routes, frontend runtime, database rows, LaunchAgents, or user-visible served behavior.

## Round 33 Review Result

Status: implementation completed; DeepSeek review passed; merged and pushed.

Round 33 scope:

- Added `build_shortpick_credible_control_comparison_line_plan(...)` for P3.8. It creates the three registered control-line definitions (`control_same_symbol_cooldown:v1`, `control_drawdown_reversal_filter:v1`, `control_repeated_exposure_limit:v1`) from deterministic P3.1-P3.3 rule builders.
- The plan attaches the two registered P1 baseline IDs (`evaluation_baseline_random_pool:v1`, `evaluation_baseline_cooldown_control:v1`) and rejects unregistered baseline IDs.
- The helper reuses P3.4/P3.5/P3.6 builders to produce historical backtest request plans, retrospective forward replay requests, and true-forward activation plans from the current paper-tracking observed date context.
- The helper enforces the P3.8 gate: a line is `ready_for_retrospective_backfill` only when supplied historical backtest evidence explicitly has `status=ready|passed`, `evidence_basis=historical_backtest`, `gate_status=passed`, and `leakage_audit_status=passed`; otherwise paper-tracking backfill remains blocked.
- The helper remains read-only: `paper_tracking_write_policy=plan_only_no_backfill_rows_written`, `runtime_dependency_status=runner_and_writer_required_before_rows_exist`.

DeepSeek result:

- Blocking issues: none.
- Merge recommendation: merge.
- Key confirmations: the helper generates the three registered control lines, attaches the two registered baselines, delegates to the historical backtest / retrospective replay / true-forward activation request builders, and stays no-write/no-runtime-exposure through top-level and child plan policies.
- DeepSeek noted one nonblocking strictness suggestion: require `evidence_basis=historical_backtest` explicitly instead of defaulting missing basis to historical. This was applied before merge.
- DeepSeek rereview confirmed the strict basis check closes the suggestion and introduces no new blocker.

Verification evidence before merge:

- `PYTHONPATH=src python3 -m pytest tests/test_shortpick_strategy_governance.py` passed (`82 passed`).
- `python3 -m ruff check src/ashare_evidence/shortpick_strategy_governance.py tests/test_shortpick_strategy_governance.py` passed.
- `python3 -m compileall -q src/ashare_evidence/shortpick_strategy_governance.py tests/test_shortpick_strategy_governance.py` passed.
- `git diff --check` passed.

Merge evidence:

- Commit `5ab1bc2` (`Add shortpick credible control line buildout plan`) was merged into main by `e9786b9`.
- `git push origin main` completed; the pre-push hook passed stock_dashboard fast regression (`748 passed, 161 deselected, 6 subtests passed`) and policy governance audit.
- No runtime publish was required because Round 33 added read-only helper logic, tests, and planning documentation only; it did not change API routes, frontend runtime, database rows, LaunchAgents, or user-visible served behavior.

## Round 34 Review Result

Status: implementation completed locally; targeted tests passed; DeepSeek review passed; ready to merge.

Round 34 scope:

- Added `shortpick_strategy_backtest_runner.py`, a gated historical-backtest execution layer for governance request plans. It consumes P3.4 request objects, executes the existing portfolio backtest only when the request carries an explicit executable `portfolio_strategies` mapping, writes the raw portfolio backtest payload beside the governance evidence artifact, and writes a `shortpick_historical_backtest_evidence` envelope with `evidence_basis=historical_backtest`.
- Added the CLI command `shortpick-governance-historical-backtest --request-path ... [--output-dir ...]` so a generated request plan or single request JSON can be executed by automation instead of only by Python callers.
- Added a guard against fake P3 evidence: current credible-control requests without executable strategy mappings are persisted as `status=blocked`, `gate_status=blocked`, `leakage_audit_status=blocked`, and `gate_reasons=["no_executable_control_backtest_mapping"]`. These artifacts cannot satisfy P3.8's historical gate and therefore cannot unlock retrospective paper-ledger backfill.
- Converted leakage audit from a static statement into an executable date-window check: `data_scope.signal_date_from/to` must remain inside the request `start_date/end_date`; otherwise the evidence records `leakage_audit_status=failed` and the historical gate is blocked.
- Kept paper tracking untouched: `paper_tracking_write_policy=forbidden`, `true_forward_tracking_eligible=false`, and no combined-ledger rows are written.

Process adjustment recorded this round:

- Do not create a second post-merge documentation-only closeout branch for every implementation round. Record merge/publish evidence in the final response or batch it in a later documentation pass.
- Run one DS review for code/behavior changes; skip DS for documentation-only evidence updates unless the doc changes alter governance policy.
- For helper-only changes, run targeted tests in the task worktree and rely on the pre-push fast regression after merge; avoid duplicating the same targeted suite on `main` unless merge conflicts or runtime behavior changed.
- Publish and browser-verify only when API/frontend/LaunchAgent/runtime data paths changed.

DeepSeek result:

- Initial DS review verdict: merge, with one actionable blocker noted before merge: `leakage_audit_status=passed` was a static claim and did not verify the returned data window.
- The blocker was fixed by adding runtime leakage-window validation and a regression test for both `signal_date_from_before_requested_start` and `signal_date_to_after_requested_end`.
- DS rereview verdict: merge. Blocking issues: none. Nonblocking suggestion to cover the `signal_date_to` branch was closed by expanding the same regression test before merge.

Verification evidence before merge:

- `pytest tests/test_shortpick_portfolio_backtest.py tests/test_shortpick_strategy_governance.py` passed (`89 passed`).
- `python3 -m ruff check src/ashare_evidence/shortpick_strategy_backtest_runner.py src/ashare_evidence/cli.py tests/test_shortpick_portfolio_backtest.py` passed.
- `python3 -m compileall -q src/ashare_evidence/shortpick_strategy_backtest_runner.py src/ashare_evidence/cli.py tests/test_shortpick_portfolio_backtest.py` passed.
- `git diff --check` passed.

Remaining blockers after Round 34:

- P3 controls still need explicit executable control-to-backtest mappings. Until then their historical evidence remains blocked rather than passed.
- Retrospective replay execution and combined-ledger writer remain pending before P3.7/P3.8 can create labeled backfill rows.

Round 34 merge evidence:

- Commit `fe68a81` (`Add shortpick governance historical backtest runner`) was merged into main by `7b1ef3a`.
- `git push origin main` completed; the pre-push hook passed stock_dashboard fast regression (`752 passed, 161 deselected, 6 subtests passed`) and policy governance audit.
- No runtime publish was required because Round 34 added offline runner/CLI/test/docs only; it did not change API routes, frontend runtime, database rows, LaunchAgents, or served user-visible behavior.

## Round 35 Review Result

Status: implementation completed locally; targeted tests passed; DeepSeek review passed; ready to merge.

Round 35 scope:

- Added three explicit executable historical portfolio strategy mappings for the registered P3 controls:
  - `control_same_symbol_cooldown_low_turnover_uptrend`
  - `control_drawdown_reversal_low_turnover_uptrend`
  - `control_repeated_exposure_low_turnover_uptrend`
- The mappings use the existing low-turnover uptrend historical candidate stream, then apply the corresponding P3 control logic before portfolio simulation:
  - same-symbol cooldown uses only prior completed same-symbol outcomes before each signal date;
  - drawdown/reversal filtering uses signal-date-or-prior market features;
  - repeated exposure limiting uses only prior signal rows in the configured signal-day window.
- `build_shortpick_historical_backtest_generation_requests(...)` now attaches the appropriate `portfolio_strategies` value for each registered P3 control request. Unknown or external controls without mappings still produce an empty mapping and remain blocked by the Round 34 runner.
- The runner evidence path remains no-write for paper tracking: `paper_tracking_write_policy=forbidden`, `true_forward_tracking_eligible=false`, and no retrospective or true-forward ledger rows are created.

Verification evidence before DeepSeek:

- `pytest tests/test_shortpick_portfolio_backtest.py tests/test_shortpick_strategy_governance.py` passed (`93 passed`).
- `python3 -m ruff check src/ashare_evidence/shortpick_portfolio_backtest.py src/ashare_evidence/shortpick_strategy_governance.py tests/test_shortpick_portfolio_backtest.py tests/test_shortpick_strategy_governance.py` passed.
- `python3 -m compileall -q src/ashare_evidence/shortpick_portfolio_backtest.py src/ashare_evidence/shortpick_strategy_governance.py tests/test_shortpick_portfolio_backtest.py tests/test_shortpick_strategy_governance.py` passed.
- `git diff --check` passed.

DeepSeek result:

- Sharded DS review completed with final PASS / merge verdict.
- Confirmed runner evidence remains no-write for paper tracking and cannot directly open retrospective backfill.
- DS requested stronger coverage proving that all three registered P3 controls receive generated mappings and that the portfolio backtest actually invokes the control helpers instead of ordinary base strategy pass-through. That coverage was added before merge:
  - governance request test now asserts all three control-to-portfolio mappings;
  - portfolio monkeypatch test now asserts same-symbol cooldown, drawdown/reversal, and repeated-exposure helpers are each called with `evidence_basis=historical_backtest`.

Remaining blockers after Round 35:

- Retrospective replay execution and combined-ledger writer remain pending before P3.7/P3.8 can create labeled backfill rows.
- Runtime/frontend exposure of new comparison lines remains pending until retrospective rows exist with explicit evidence-basis labels.

Round 35 merge evidence:

- Commit `0589af9` (`Add shortpick P3 control backtest mappings`) was merged into main by `356d423`.
- `git push origin main` completed; the pre-push hook passed stock_dashboard fast regression (`756 passed, 161 deselected, 6 subtests passed`) and policy governance audit.
- No runtime publish was required because Round 35 added offline strategy mapping/test/docs only; it did not change API routes, frontend runtime, database rows, LaunchAgents, or served user-visible behavior.

## Round 36 Review Result

Status: implementation completed locally; targeted tests passed; DeepSeek review passed after blocker repair; ready to merge.

Round 36 scope:

- Added `shortpick_strategy_replay_runner.py`, an artifact-only retrospective replay execution layer for P3.5. It consumes generated retrospective replay requests plus paper-tracking JSON and writes `shortpick_retrospective_forward_replay` artifacts.
- The runner applies the registered P3 control logic to replay candidates:
  - same-symbol cooldown uses completed prior outcomes from `validation_by_horizon`;
  - drawdown/reversal uses `drawdown_reversal_features`, `signal_features`, or top-level signal-date features;
  - repeated exposure uses replay candidate rows and the existing prior-signal control helper.
- Replay rows are explicitly labeled: `evidence_basis=retrospective_forward_replay`, `retrospective=true`, `true_forward_tracking_eligible=false`, `headline_metric_eligible=false`, `source_feature_cutoff_policy=signal_date_available_inputs_only`, and `paper_tracking_write_policy=forbidden`.
- Added CLI command `shortpick-governance-retrospective-replay --request-path ... --paper-tracking-path ... [--output-dir ...]`.
- The runner blocks unsafe request windows where `replay_end_date >= rule_defined_at`, so retrospective rows cannot include signal dates on or after rule definition.
- The runner rejects requests that try to set `true_forward_tracking_eligible=true` or `headline_metric_eligible=true`, and blocked outputs still force no-write / not-headline labels.
- Auxiliary control data for cooldown and drawdown replay is limited to paper rows whose `signal_date` is inside the replay window and strictly before `rule_defined_at`; empty drawdown feature rows no longer count as feature coverage.
- Verified replay rows can feed `build_shortpick_combined_ledger_retrospective_backfill(...)` without writing the database.

Verification evidence after blocker repair:

- `pytest tests/test_shortpick_strategy_governance.py tests/test_shortpick_portfolio_backtest.py` passed (`99 passed`).
- `python3 -m ruff check src/ashare_evidence/shortpick_strategy_replay_runner.py src/ashare_evidence/cli.py tests/test_shortpick_strategy_governance.py tests/test_shortpick_portfolio_backtest.py` passed.
- `python3 -m compileall -q src/ashare_evidence/shortpick_strategy_replay_runner.py src/ashare_evidence/cli.py tests/test_shortpick_strategy_governance.py tests/test_shortpick_portfolio_backtest.py` passed.
- `git diff --check` passed.

DeepSeek review evidence:

- Initial sharded DS review rejected the draft because cooldown/drawdown auxiliary data was not limited to replay scope and because tampered true-forward/headline request fields were not explicitly blocked.
- The runner was updated to scope auxiliary paper rows with `replay_start_date <= signal_date <= replay_end_date` and `signal_date < rule_defined_at`, reject true-forward/headline tampering, and avoid treating empty drawdown feature rows as ready coverage.
- DS re-review returned MERGE: both blockers resolved, no residual blocking issues, and new tests cover cooldown auxiliary scope, drawdown auxiliary scope, and true-forward/headline tampering.

Remaining blockers after Round 36:

- Runtime combined-ledger writer remains pending before replay artifacts become durable paper-tracking rows.
- Runtime/frontend exposure of new comparison lines remains pending until labeled retrospective rows exist in the combined ledger.

## Round 37 Review Result

Status: implementation completed locally; targeted tests passed; DeepSeek review passed; ready to merge.

Round 37 scope:

- Added `shortpick_combined_ledger_writer.py`, an artifact-only materialization layer for P3.7. It consumes one or more ready `shortpick_retrospective_forward_replay` artifacts and optional true-forward rows.
- The writer delegates row normalization to `build_shortpick_combined_ledger_retrospective_backfill(...)`, then writes a `shortpick_combined_ledger_backfill` artifact with mandatory evidence-basis labels and true-forward headline filter metadata.
- Added CLI command `shortpick-governance-combined-ledger-backfill --replay-artifact-path ... --output-path ...`.
- The writer remains no-DB/no-paper-write: `write_policy=artifact_only_no_database_or_paper_tracking_write`; runtime API/frontend consumption remains a later task.
- Added unit and CLI tests covering replay-artifact materialization, retrospective labels, true-forward filtering, and written artifact shape.

Verification evidence before DeepSeek:

- `pytest tests/test_shortpick_strategy_governance.py tests/test_shortpick_portfolio_backtest.py` passed (`101 passed`).
- `python3 -m ruff check src/ashare_evidence/shortpick_combined_ledger_writer.py src/ashare_evidence/cli.py tests/test_shortpick_strategy_governance.py tests/test_shortpick_portfolio_backtest.py` passed.
- `python3 -m compileall -q src/ashare_evidence/shortpick_combined_ledger_writer.py src/ashare_evidence/cli.py tests/test_shortpick_strategy_governance.py tests/test_shortpick_portfolio_backtest.py` passed.
- `git diff --check` passed.

DeepSeek review evidence:

- Sharded DS review completed with final PASS / merge verdict.
- Source/CLI shard confirmed the writer only writes JSON artifacts, records no-DB/no-paper-write policy, blocks unsupported or not-ready replay artifacts, and keeps retrospective rows behind evidence-basis filtering.
- Test shard confirmed coverage for the basic materialization path, retrospective non-headline labels, true-forward filtering, and blocked replay rows not entering the combined ledger.
- Plan shard confirmed the documentation is honest that DB/API/frontend consumption remains pending. Nonblocking follow-up: add broader multi-replay duplicate-edge tests if this artifact writer becomes a hot runtime path.

Remaining blockers after Round 37:

- Runtime API/frontend wiring remains pending before the new combined-ledger artifact is visible in the stock dashboard.
- A separate durable strategy-retirement artifact writer remains pending before any strategy is durably hidden or retired from generation.

## Round 38 Review Result

Status: implementation completed locally; targeted tests passed; DeepSeek review passed; ready to merge.

Round 38 scope:

- Added `shortpick_strategy_retirement_writer.py`, a governed writer for `shortpick_strategy_retirement` / `strategy_retirement:v1` artifacts.
- The writer only records a ready retirement artifact when the target strategy already has `recommended_status=retire_candidate`, `decision_log_ref`, non-empty `evidence_snapshot_refs`, `retired_at`, and supported evidence-basis refs.
- The writer emits `shortpick.strategy_retirement.recorded.v1` in `event_refs` and produces artifacts directly consumable by `build_shortpick_strategy_status_recommendations(...)` as retirement authority.
- Updated `shortpick_strategy_retirement.schema.json` to include `artifact_id` and `status`, matching the status recommendation layer's existing retirement-authority requirements.
- Added CLI command `shortpick-governance-retirement-artifact --evidence-pack-path ... --status-recommendation-path ... --strategy-id ... --decision-log-ref ... --evidence-snapshot-ref ... --retired-at ... --output-path ...`.

Verification evidence:

- `pytest tests/test_shortpick_strategy_governance.py tests/test_shortpick_portfolio_backtest.py tests/test_contract_registry.py` passed (`109 passed`).
- `python3 -m ruff check src/ashare_evidence/shortpick_strategy_retirement_writer.py src/ashare_evidence/cli.py tests/test_shortpick_strategy_governance.py tests/test_shortpick_portfolio_backtest.py` passed.
- `python3 -m compileall -q src/ashare_evidence/shortpick_strategy_retirement_writer.py src/ashare_evidence/cli.py tests/test_shortpick_strategy_governance.py tests/test_shortpick_portfolio_backtest.py` passed.
- `git diff --check` passed.
- DeepSeek sharded review returned `PASS/MERGE`: it confirmed the writer/CLI are gated by `recommended_status=retire_candidate`, emit only governance JSON artifacts without database or paper-tracking writes, and align with the schema plus status-recommendation retirement authority. One non-blocking note observed that the schema enum still includes `active`/`observe` for `strategy_status_before`, while the writer runtime blocks those statuses.

Remaining blockers after Round 38:

- Runtime artifact discovery/source wiring remains pending before active generation or frontend views automatically consume retirement artifacts.
- Physical deletion of retired strategies remains intentionally blocked until archive/statistics retention and runtime consumption are verified end to end.

## Round 39 Review Result

Status: implementation completed locally; targeted tests passed; DeepSeek review passed; ready to merge.

Round 39 scope:

- Added `shortpick_strategy_retirement` to the runtime artifact folder map as `shortpick_strategy_retirements`.
- Added `write_shortpick_strategy_retirement_artifact_record(...)` and `read_shortpick_strategy_retirement_artifacts(...)` so runtime code can discover ready/recorded retirement artifacts from the configured artifact root without scanning arbitrary output paths.
- The reader ignores blocked, malformed, non-object, incomplete, or duplicate-`artifact_id` artifacts and reports `artifact_count`, `ignored_count`, and source directories for diagnostics.
- Wired `/shortpick-lab/paper-tracking` governance partition and replay-feedback governance projection to pass runtime retirement artifacts into `build_shortpick_strategy_status_recommendations(...)`.
- Passed the same artifact source into archive-record generation so retired rows retain their retirement artifact refs and summary counts.

Verification evidence:

- `python3 -m pytest tests/test_research_artifact_store.py tests/test_shortpick_replay_api_projection.py tests/test_shortpick_lab_paper_tracking.py` passed for the default fast subset (`14 passed, 7 deselected`).
- `python3 -m pytest -m runtime_integration tests/test_shortpick_lab_paper_tracking.py::ShortpickLabPaperTrackingTests::test_paper_tracking_reads_retirement_artifact_source_for_governance_partition` passed.
- `python3 -m ruff check src/ashare_evidence/artifact_store_core.py src/ashare_evidence/research_artifact_store.py src/ashare_evidence/api.py tests/test_research_artifact_store.py tests/test_shortpick_replay_api_projection.py tests/test_shortpick_lab_paper_tracking.py` passed.
- `python3 -m compileall -q src/ashare_evidence/artifact_store_core.py src/ashare_evidence/research_artifact_store.py src/ashare_evidence/api.py tests/test_research_artifact_store.py tests/test_shortpick_replay_api_projection.py tests/test_shortpick_lab_paper_tracking.py` passed.
- `git diff --check` passed.
- DeepSeek sharded review returned `PASS/MERGE`; it confirmed reader filtering, API source propagation, and plan scope honesty. The first shard noted a non-blocking duplicate-artifact count risk when runtime and legacy roots both contain the same `artifact_id`; the follow-up fix added `artifact_id` de-duplication and a ready+blocked+duplicate regression test.
- Focused DeepSeek re-review of the de-duplication fix returned `PASS/MERGE`, confirming duplicates enter `ignored` and do not inflate `artifact_count` or the returned `artifacts` list.

Remaining blockers after Round 39:

- Active shortpick generation still does not call `filter_shortpick_generation_eligible_items(...)` with the runtime retirement artifact source, so this round affects runtime governance display/partitioning but not future generation exclusion.
- Physical deletion of retired strategies remains intentionally blocked until archive/statistics retention and generation exclusion are both verified end to end.

## Round 40 Review Result

Status: implementation completed locally; targeted tests passed; DeepSeek re-review passed; ready to merge.

Round 40 scope:

- Wired active shortpick market-factor generation to read runtime `shortpick_strategy_retirement` artifacts from the session-derived artifact root.
- Added a generation-governance pass for both daily market-factor overlay generation and intraday same-day control generation.
- The generation pass converts inserted market-factor candidates into canonical strategy specs, calls `filter_shortpick_generation_eligible_items(...)`, deletes excluded `retired` candidates in the same transaction before validation/commit, and leaves `retire_candidate`, `observe`, and `untracked` strategies eligible.
- Overlay summaries now include `generation_governance` with artifact-source counts, eligible/excluded counts, excluded strategy ids, and exclusion reasons.
- Added an authority guard so a malformed/mixed artifact source cannot turn an explicitly non-retired `recommended_status` such as `observe` or `retire_candidate` into a generation exclusion.
- This round does not physically delete historical data, does not write fake forward rows, does not retire by metrics alone, and does not change retrospective/true-forward evidence labels.

Verification evidence:

- `python3 -m pytest tests/test_shortpick_strategy_governance.py tests/test_research_artifact_store.py` passed (`98 passed`).
- `python3 -m pytest -m runtime_integration tests/test_shortpick_lab.py tests/test_shortpick_lab_paper_tracking.py` passed (`33 passed`). The runtime generation test writes one real retired artifact plus explicit `observe` and `retire_candidate` artifact-source counterexamples, and verifies only the retired strategy is excluded.
- `python3 -m ruff check src/ashare_evidence/shortpick_lab.py tests/test_shortpick_lab.py` passed.
- `python3 -m compileall -q src/ashare_evidence/shortpick_lab.py tests/test_shortpick_lab.py` passed.
- `git diff --check` passed.

Remaining blockers after Round 40:

- Physical deletion of retired strategies remains intentionally blocked until archive/statistics retention and generation exclusion are verified against the user-visible runtime data set.
- Runtime data remains unchanged by this round; a live scheduled run or explicit runtime publish/verification step is still required before claiming a served dashboard has observed the new exclusion behavior.

Initial DeepSeek review result:

- Result: `BLOCK`.
- Blocker 1: runtime tests did not explicitly cover `retire_candidate`, `observe`, or `untracked` strategies staying eligible.
- Blocker 2: generation artifact-source consumption did not have an explicit guard/test for malformed or mixed non-retired status entries.
- Fix applied before re-review: `_shortpick_generation_retirement_artifact_is_retired_authority(...)` now ignores artifacts that explicitly carry a non-retired recommendation, and the runtime generation test now includes `observe` and `retire_candidate` artifact-source counterexamples while leaving untracked strategies naturally eligible.

DeepSeek re-review result:

- Result: `PASS/MERGE`.
- Confirmation: the runtime test now writes one retired artifact plus `observe` and `retire_candidate` counterexamples, verifies only one strategy is excluded, and verifies the non-retired controls remain in generated candidates.
- Confirmation: the authority guard requires `strategy_id`, `decision_log_ref`, and no explicit non-retired status; malformed or mixed non-retired entries do not become generation exclusions.

## Round 41 Review Result

Status: implementation completed locally; targeted tests passed; DeepSeek re-review passed; ready to merge.

Round 41 scope:

- Added `shortpick_combined_ledger_backfill` to the runtime artifact folder map as `shortpick_combined_ledgers`.
- Added `write_shortpick_combined_ledger_backfill_artifact_record(...)` and `read_shortpick_combined_ledger_backfill_artifacts(...)` so runtime code can discover ready combined-ledger artifacts from the session-derived artifact root.
- The reader accepts only ready `shortpick_combined_ledger_backfill` artifacts with `ledger_mode=combined_paper_tracking_ledger`, the required true-forward headline filter policy, and non-empty `combined_rows` where every row has `combined_ledger_row_id` plus `evidence_basis`.
- Wired `/shortpick-lab/paper-tracking` to expose a top-level `combined_ledger` projection with `rows`, `true_forward_rows`, `retrospective_rows`, basis counts, artifact counts, ignored counts, and duplicate-row counts.
- Retrospective rows remain artifact-backed only and are not merged into the primary paper-tracking `items` list. This round does not write database rows, does not fake historical rows as true-forward tracking, and does not change frontend rendering.

Verification evidence before DeepSeek:

- `python3 -m pytest tests/test_research_artifact_store.py tests/test_shortpick_replay_api_projection.py` passed (`15 passed`).
- `python3 -m pytest -m runtime_integration tests/test_shortpick_lab_paper_tracking.py` passed (`8 passed`).
- `python3 -m ruff check src/ashare_evidence/artifact_store_core.py src/ashare_evidence/research_artifact_store.py src/ashare_evidence/api.py tests/test_research_artifact_store.py tests/test_shortpick_lab_paper_tracking.py` passed.
- `python3 -m compileall -q src/ashare_evidence/artifact_store_core.py src/ashare_evidence/research_artifact_store.py src/ashare_evidence/api.py tests/test_research_artifact_store.py tests/test_shortpick_lab_paper_tracking.py` passed.
- `git diff --check` passed.

Initial DeepSeek review result:

- Result: `BLOCK`.
- Blocker: the combined-ledger artifact reader only required non-empty `evidence_basis` instead of enforcing the allowed combined-ledger basis values, and the negative tests did not directly cover blocked artifacts, missing row identity, missing basis, and duplicate artifact IDs.
- Fix applied before re-review: `_is_ready_shortpick_combined_ledger_backfill_artifact(...)` now allows only `true_forward_tracking` and `retrospective_forward_replay`; the artifact-store test now writes blocked, duplicate, missing `combined_ledger_row_id`, missing `evidence_basis`, and unknown-basis artifacts and verifies only the single ready artifact is returned.

DeepSeek re-review result:

- Result: `PASS/MERGE`.
- Confirmation: the reader's evidence-basis whitelist resolves the initial blocker; the negative test directly covers the blocked/duplicate/missing/unknown-basis cases; and the paper-tracking API test proves a retrospective combined-ledger artifact does not populate primary `items`.

Remaining blockers after Round 41:

- Frontend paper-tracking display still needs to render the `combined_ledger` block with evidence-basis separation before users can inspect the new comparison rows in the dashboard.
- Runtime data generation remains artifact-only until governed jobs produce real combined-ledger backfill artifacts for the runtime artifact root.
- Served runtime/canonical verification is still required before claiming the user-visible dashboard shows combined-ledger rows.

## Round 42 Review Result

Status: implementation completed locally; build/static checks passed; DeepSeek review passed; browser verification blocked; ready to merge.

Round 42 scope:

- Added frontend TypeScript types for `combined_ledger` and combined-ledger rows in `ShortpickPaperTrackingResponse`.
- Added a separate `组合 Ledger 回放对照` block to the paper-tracking tab that renders artifact count, ignored count, duplicate row count, combined row count, true-forward count, retrospective count, and a table of combined-ledger rows.
- The table displays `evidence_basis` through the existing strategy evidence-basis label/color helpers and does not reuse or mutate the primary paper-tracking `items` data source.
- Added static frontend coverage that locks the `combinedLedgerRows = combinedLedger?.rows ?? []` source, the evidence-basis label call, the combined-ledger title, and the visible "not merged into items" copy.

Verification evidence before DeepSeek:

- `python3 -m pytest tests/test_frontend_shortpick_static.py tests/test_frontend_shortpick_paper_tracking_helpers.py` passed (`6 passed`) after `npm ci` installed local frontend verification dependencies.
- `python3 -m ruff check tests/test_frontend_shortpick_static.py` passed.
- `python3 -m compileall -q tests/test_frontend_shortpick_static.py` passed.
- `npm run build` passed (`tsc --noEmit -p tsconfig.app.json && vite build`); Vite emitted only the existing large-chunk warning.
- `git diff --check` passed.

Browser verification limitation:

- A local Vite dev server was started on `http://127.0.0.1:5179/` and a mock paper-tracking API server was started on `http://127.0.0.1:18082/`.
- The Browser plugin rejected navigation to the local URL with `apiBase=http://127.0.0.1:18082` as a Browser URL policy block and explicitly instructed not to attempt the same outcome through alternate browser surfaces or workarounds.
- Therefore this round cannot claim browser, served runtime, or canonical verification. A later publish/verification round must use an allowed route or real runtime artifact data.

DeepSeek review result:

- Result: `PASS/MERGE`.
- Confirmation: the paper-tracking primary table still uses `tracking.items -> primaryPaperTrackingRows(rows) -> displayRows`; `combinedLedgerRows` reads only `tracking.combined_ledger.rows` and is rendered in an independent `组合 Ledger 回放对照` card.
- Confirmation: `evidence_basis` is visibly rendered through `strategyEvidenceBasisLabel(item.evidence_basis)` and the UI text states retrospective rows come from `combined_ledger` artifacts while headline/default true-forward logic remains separate.
- Confirmation: static tests and plan updates are sufficient for merge, and the plan honestly records that Browser URL policy blocked visual/browser verification.

Remaining blockers after Round 42:

- DeepSeek review passed.
- Served runtime/canonical verification was pending at Round 42 merge time and was closed in Round 43.
- Runtime data generation remains artifact-only until governed jobs produce real combined-ledger backfill artifacts for the runtime artifact root.

## Round 43 Publish Closeout For Combined-Ledger Frontend

Status: completed and merged.

Background:

- Round 42 changed user-visible frontend rendering, but Browser-plugin visual verification was blocked by URL policy when using a mock `apiBase` endpoint.
- The global runtime rule requires live-facing changes to be published to `/Users/hernando_zhao/codex/runtime/projects/ashare-dashboard` and verified against served output before the work can be called closed.

Implementation and verification:

- Published merge commit `a6b245ce3f53ec7ae404a4a23161eff958872682` to the local runtime.
- The publish that acquired the runtime lock wrote local release manifest `/Users/hernando_zhao/codex/runtime/projects/ashare-dashboard/output/releases/local-20260611T053042Z-a6b245c.json` and updated `/Users/hernando_zhao/codex/runtime/projects/ashare-dashboard/output/releases/latest-successful.commit` to `a6b245ce3f53ec7ae404a4a23161eff958872682`.
- Local runtime frontend `http://127.0.0.1:5173/` served `assets/index-c2e8a0e9.css` and `assets/index-c8c805d0.js`.
- Canonical authenticated entry `https://hernando-zhao.cn/projects/ashare-dashboard/` served the same asset names.
- Local and canonical served JS asset `assets/index-c8c805d0.js` contains the new `组合 Ledger 回放对照` title and the visible evidence-basis warning `后验回放行仅来自 combined_ledger artifact`.
- Local runtime `/health` returned `{"status":"ok","database_url":"sqlite:////Users/hernando_zhao/codex/runtime/projects/ashare-dashboard/data/ashare_dashboard.db"}`.
- Local and canonical authenticated `/api/shortpick-lab/paper-tracking` returned the `combined_ledger` top-level block; current runtime data has `combined_artifacts=0` and `combined_rows=0`, so this verifies API shape and served frontend code, not real combined-ledger data population.

Verification limits:

- This round did not rerun the Browser-plugin visual flow because Round 42's Browser policy block explicitly forbade attempting the same mock-route outcome through alternate browser surfaces.
- The publish manifest is `verification_mode=local`; canonical release parity was instead checked by direct authenticated served asset/API probes.
- Runtime data generation remains pending until governed jobs create real combined-ledger backfill artifacts under the runtime artifact root.

DeepSeek review result:

- Result: `PASS`.
- Confirmation: the Round 43 closeout does not overstate the local release manifest as a canonical release verifier pass.
- Confirmation: the document clearly records that current runtime combined-ledger data is still empty (`combined_artifacts=0`, `combined_rows=0`) and that this round only verifies served frontend code and API shape.
- Confirmation: the update is mergeable as a documentation closeout and preserves the Browser-policy limitation.

## Round 44 Combined-Ledger Discovery Materializer

Status: completed DeepSeek review and ready to merge.

Round 44 scope:

- Registered a standard artifact folder mapping for `shortpick_retrospective_forward_replay` as `shortpick_retrospective_replays`.
- Added `discover_shortpick_retrospective_forward_replay_artifacts(root=...)`, which scans the standard replay folder plus legacy `replays`, accepts only ready governance replay artifacts with `artifact_type=shortpick_retrospective_forward_replay`, `evidence_basis=retrospective_forward_replay`, `retrospective=true`, `paper_tracking_write_policy=forbidden`, required rule identity, and non-empty rows.
- Added `materialize_shortpick_combined_ledger_from_artifact_root(...)`, which uses discovery output to produce a `shortpick_combined_ledger_backfill` artifact under the runtime artifact root when ready replay inputs exist.
- Added CLI command `shortpick-governance-combined-ledger-materialize` with `--database-url` artifact-root derivation, optional `--artifact-root`, optional `--true-forward-path`, optional `--output-path`, and opt-in `--write-blocked`.
- The materializer remains artifact-only: it does not write the database, does not write primary paper-tracking rows, and does not let retrospective rows enter headline metrics.

Verification evidence before DeepSeek:

- Focused tests passed: `python3 -m pytest tests/test_shortpick_strategy_governance.py::test_combined_ledger_discovery_reads_only_ready_governance_replay_artifacts tests/test_shortpick_strategy_governance.py::test_combined_ledger_materializer_writes_runtime_artifact_from_discovery_root tests/test_shortpick_portfolio_backtest.py::test_cli_governance_combined_ledger_materialize_discovers_runtime_replay_artifacts`.
- Related regression passed: `python3 -m pytest tests/test_shortpick_strategy_governance.py tests/test_shortpick_portfolio_backtest.py tests/test_research_artifact_store.py tests/test_shortpick_lab_paper_tracking.py` (`115 passed, 8 deselected`).
- `python3 -m ruff check src/ashare_evidence/artifact_store_core.py src/ashare_evidence/shortpick_combined_ledger_writer.py src/ashare_evidence/cli.py tests/test_shortpick_strategy_governance.py tests/test_shortpick_portfolio_backtest.py` passed.
- `python3 -m compileall -q src/ashare_evidence/artifact_store_core.py src/ashare_evidence/shortpick_combined_ledger_writer.py src/ashare_evidence/cli.py tests/test_shortpick_strategy_governance.py tests/test_shortpick_portfolio_backtest.py` passed.
- `git diff --check` passed.
- Runtime dry run from the worktree against `sqlite:////Users/hernando_zhao/codex/runtime/projects/ashare-dashboard/data/ashare_dashboard.db` returned `status=blocked`, `source_artifacts=0`, `ignored=39`, `retrospective_count=0`, `combined_row_count=0`, and `artifact_written=false`. This confirms the command does not fabricate combined rows from old replay-alignment artifacts.

Remaining blockers after Round 44:

- Real runtime combined-ledger rows still require ready `shortpick_retrospective_forward_replay` governance artifacts under the runtime artifact root.
- P3.8 still needs governed replay artifact production from credible-control comparison requests before the new materializer can create non-empty runtime combined-ledger artifacts.

DeepSeek review result:

- Result: `PASS`.
- Confirmation: discovery is strict enough to reject blocked, wrong-basis, legacy `replay_alignment`, duplicate, and unreadable artifacts before combined-ledger materialization.
- Confirmation: the new materializer and CLI remain artifact-only and do not write the database, primary paper-tracking rows, or headline true-forward metrics.
- Confirmation: tests and plan coverage are sufficient for this round; the remaining blocker is upstream production of ready governance replay artifacts.

## Round 45 Credible-Control Request Plan CLI

Status: implementation completed locally; targeted tests passed; DeepSeek re-review passed; ready to merge.

Round 45 scope:

- Added CLI command `shortpick-governance-credible-control-plan`.
- The command reads a paper-tracking JSON object, requires `--rule-defined-at`, accepts optional historical evidence, generated timestamp, historical backtest window overrides, tracking start date, entry-price sources, baseline IDs, and optional output path.
- The command calls `build_shortpick_credible_control_comparison_line_plan(...)` and outputs a plan containing historical backtest requests, retrospective replay requests, true-forward activation plan, and per-line historical gate status.
- This round does not execute historical backtests, does not execute retrospective replay, does not write combined-ledger artifacts, and does not write database or primary paper-tracking rows. The CLI command is also marked plan-only so it skips the generic database initialization path.

Verification evidence before DeepSeek:

- Focused tests passed: `python3 -m pytest tests/test_shortpick_portfolio_backtest.py::test_cli_governance_credible_control_plan_writes_request_plan tests/test_shortpick_portfolio_backtest.py::test_cli_governance_credible_control_plan_skips_database_initialization tests/test_shortpick_strategy_governance.py::test_credible_control_comparison_line_plan_generates_three_registered_lines_with_backtest_gate`.
- Related regression passed: `python3 -m pytest tests/test_shortpick_portfolio_backtest.py tests/test_shortpick_strategy_governance.py` (`109 passed`).
- `python3 -m ruff check src/ashare_evidence/cli.py tests/test_shortpick_portfolio_backtest.py` passed.
- `python3 -m compileall -q src/ashare_evidence/cli.py tests/test_shortpick_portfolio_backtest.py` passed.
- `git diff --check` passed.
- Runtime dry run using local runtime `/shortpick-lab/paper-tracking` exported to `/tmp/round45-paper-tracking.json` returned `status=blocked`, `line_count=3`, `ready_line_count=0`, `historical_requests=3`, `retrospective_requests=3`, `activation_count=3`, `paper_tracking_write_policy=plan_only_no_backfill_rows_written`, and `runtime_dependency_status=runner_and_writer_required_before_rows_exist`.

Remaining blockers after Round 45:

- Historical backtest gate evidence must be generated and passed before any credible-control line is allowed to unlock retrospective backfill.
- The generated retrospective replay request plan still needs a governed execution step that writes ready `shortpick_retrospective_forward_replay` artifacts under the runtime artifact root.

DeepSeek review result:

- Initial read-only DeepSeek review returned `PASS`, confirming the command does not call `session_scope`, historical backtest runners, retrospective replay runners, combined-ledger writers, or database-backed paper-tracking writers. It noted one side-effect risk: the generic CLI prelude could still call `init_database(None)` for this plan-only command.
- The follow-up fix added `PLAN_ONLY_COMMANDS = {"shortpick-governance-credible-control-plan"}` before generic database initialization and a regression test proving `init_database` is not called for this command.
- Focused DeepSeek re-review returned `PASS / MERGE`, confirming the DB initialization side effect is closed and there are no BLOCK files.

## Round 46 Credible-Control Plan Executor Bridge

Status: implementation completed locally; targeted tests passed; DeepSeek review passed; ready to merge.

Round 46 scope:

- Added a small CLI request-extraction helper so governance execution commands can consume either the legacy top-level request shapes or the Round 45 nested credible-control plan shape.
- `shortpick-governance-historical-backtest` now accepts `historical_backtest_plan.requests` directly from a credible-control plan JSON.
- `shortpick-governance-retrospective-replay` now accepts `retrospective_replay_plan.requests` directly from a credible-control plan JSON.
- This round does not change strategy logic, does not write database paper-tracking rows, and does not materialize combined-ledger artifacts. It only removes the manual JSON-splitting step between Round 45 request planning and the existing governed execution CLIs.

Verification evidence before DeepSeek:

- Focused tests passed: `python3 -m pytest tests/test_shortpick_portfolio_backtest.py::test_cli_governance_historical_backtest_runs_credible_control_plan_file tests/test_shortpick_portfolio_backtest.py::test_cli_governance_retrospective_replay_runs_credible_control_plan_file`.
- Related CLI regression passed: `python3 -m pytest tests/test_shortpick_portfolio_backtest.py` (`18 passed`).
- Governance builder regression passed: `python3 -m pytest tests/test_shortpick_strategy_governance.py` (`93 passed`).
- `python3 -m ruff check src/ashare_evidence/cli.py tests/test_shortpick_portfolio_backtest.py` passed.
- `python3 -m compileall -q src/ashare_evidence/cli.py tests/test_shortpick_portfolio_backtest.py` passed.
- `git diff --check` passed.

Remaining blockers after Round 46:

- Historical backtest gate evidence still needs to be generated against runtime data and inspected for pass/block status.
- Ready retrospective replay artifacts still need to be produced under the runtime artifact root before Round 44 materialization can produce non-empty combined-ledger rows.
- True-forward runtime tracking and frontend exposure remain pending until governed artifacts exist.

DeepSeek review result:

- DeepSeek read-only review returned `PASS`.
- Confirmation: the request extraction helper preserves old single-request and top-level `requests` input compatibility while adding direct support for Round 45 nested credible-control plan shapes.
- Confirmation: the diff only changes request extraction before existing historical-backtest and retrospective-replay runners; it does not add database writes, paper-tracking writes, or combined-ledger materialization.
- Nonblocking suggestion retained for later: add an explicit CLI test for old top-level `{"requests": [...]}` input shape, although the code path remains straightforward and existing old single-request tests still pass.

## Round 47 Historical Evidence Aggregate Compatibility

Status: implementation completed locally; targeted tests passed; DeepSeek review passed; ready to merge.

Round 47 scope:

- The credible-control planner already accepts historical evidence keyed by `rule_signature`, keyed by `control_group_id`, or listed under `artifacts`.
- The historical-backtest runner returns an aggregate object with per-control artifacts under the `evidence` field.
- This round lets `_historical_backtest_evidence_for_rule(...)` also scan `evidence`, so the output of `shortpick-governance-historical-backtest` can be used directly as `--historical-evidence-path` for `shortpick-governance-credible-control-plan`.
- This round does not execute runtime backtests, does not write paper-tracking rows, and does not change any strategy rule or gate threshold.

Verification evidence before DeepSeek:

- Focused tests passed: `python3 -m pytest tests/test_shortpick_strategy_governance.py::test_credible_control_comparison_line_plan_accepts_runner_evidence_aggregate tests/test_shortpick_strategy_governance.py::test_credible_control_comparison_line_plan_allows_backfill_only_after_passed_historical_gate`.
- Governance regression passed: `python3 -m pytest tests/test_shortpick_strategy_governance.py` (`94 passed`).
- `python3 -m ruff check src/ashare_evidence/shortpick_strategy_governance.py tests/test_shortpick_strategy_governance.py` passed.
- `python3 -m compileall -q src/ashare_evidence/shortpick_strategy_governance.py tests/test_shortpick_strategy_governance.py` passed.
- `git diff --check` passed.

Remaining blockers after Round 47:

- Historical backtest gate evidence still needs to be generated against runtime data and reviewed for pass/block status.
- Ready retrospective replay artifacts still need runtime production before combined-ledger materialization can produce non-empty rows.

DeepSeek review result:

- DeepSeek read-only review returned `PASS / MERGE`.
- Confirmation: adding `evidence` scanning is only input compatibility; `_credible_control_historical_gate(...)` remains unchanged and still requires `status=ready|passed`, `evidence_basis=historical_backtest`, `gate_status=passed`, and `leakage_audit_status=passed`.
- Confirmation: unrelated evidence is not accepted because list items still must match by `rule_signature` or `control_group_id`, then pass the unchanged gate.
- Nonblocking note: if both `artifacts` and `evidence` exist, the existing first-match order now checks `artifacts` first and `evidence` second. Runtime runner aggregates use `evidence`, so this is not a blocker.

## Round 48 Runtime Historical Gate Attempt

Status: runtime attempt documented; DeepSeek doc-honesty review passed; ready to merge.

Round 48 scope:

- Used the current local runtime `/shortpick-lab/paper-tracking` API response as the source paper-tracking snapshot.
- Generated a current credible-control plan with `shortpick-governance-credible-control-plan`.
- Attempted to execute the generated nested `historical_backtest_plan.requests` through `shortpick-governance-historical-backtest`.
- This round did not change repository code and did not write database or paper-tracking rows.

Runtime artifacts:

- Paper-tracking snapshot: `/Users/hernando_zhao/codex/runtime/projects/ashare-dashboard/output/analytics/20260611-credible-control-runtime/paper-tracking.json`.
- Credible-control plan: `/Users/hernando_zhao/codex/runtime/projects/ashare-dashboard/output/analytics/20260611-credible-control-runtime/credible-control-plan.json`.
- Planned historical gate output directory: `/Users/hernando_zhao/codex/runtime/projects/ashare-dashboard/output/shortpick-governance-backtests/20260611T1433-runtime-gate`.

Runtime result:

- The generated plan returned `status=blocked`, `line_count=3`, `ready_line_count=0`, `blocked_line_count=3`, `historical_requests=3`, `retrospective_requests=3`, and `activation_count=3`.
- The historical gate batch process was still CPU-active after several minutes but had not written any evidence artifact or output file content. It was terminated to avoid leaving an opaque long-running batch process.
- The transient zero-byte `historical-backtest-evidence.json` file from the interrupted shell redirection was removed. The planned historical output directory remains empty.

Remaining blockers after Round 48:

- Historical gate execution must be rerun in a sharded or more observable mode, preferably one control request at a time with per-request timing and artifact checks.
- Until ready historical evidence exists, no credible-control line may unlock retrospective replay or combined-ledger materialization.
- Ready retrospective replay artifacts still need runtime production before combined-ledger materialization can produce non-empty rows.

DeepSeek review result:

- DeepSeek read-only doc-honesty review returned `PASS`.
- Confirmation: the document clearly distinguishes successful plan generation from incomplete historical evidence generation.
- Confirmation: it does not claim the runtime historical gate passed; it records `status=blocked`, `ready_line_count=0`, and the empty output directory.
- Confirmation: the next blocker, sharded or more observable per-request historical gate execution, is reasonable.

## Round 49 Governance Request Selectors

Status: implementation completed locally; targeted tests passed; DeepSeek review passed; ready to merge.

Round 49 scope:

- Added reusable request filtering for governance execution CLIs.
- `shortpick-governance-historical-backtest` now accepts repeatable `--request-id` and `--control-group-id` filters after reading either a single request, a top-level `requests` payload, or the nested `historical_backtest_plan.requests` payload.
- `shortpick-governance-retrospective-replay` now accepts the same filters for nested `retrospective_replay_plan.requests`.
- This is the concrete follow-up to Round 48: runtime historical gate execution can now be run one control request at a time instead of as one opaque three-request batch.
- This round does not change strategy logic, gate thresholds, database writes, paper-tracking writes, or combined-ledger materialization.

Verification evidence before DeepSeek:

- Focused tests passed: `python3 -m pytest tests/test_shortpick_portfolio_backtest.py::test_cli_governance_historical_backtest_filters_nested_plan_by_control_group_id tests/test_shortpick_portfolio_backtest.py::test_cli_governance_retrospective_replay_filters_nested_plan_by_request_id`.
- Related CLI regression passed: `python3 -m pytest tests/test_shortpick_portfolio_backtest.py` (`20 passed`).
- `python3 -m ruff check src/ashare_evidence/cli.py tests/test_shortpick_portfolio_backtest.py` passed.
- `python3 -m compileall -q src/ashare_evidence/cli.py tests/test_shortpick_portfolio_backtest.py` passed.
- `git diff --check` passed.

Remaining blockers after Round 49:

- Run the runtime historical gate request shards one at a time using `--control-group-id` or `--request-id`.
- Only if a control line receives ready historical evidence may retrospective replay be executed for that line.
- Combined-ledger materialization remains blocked until ready retrospective replay artifacts exist.

DeepSeek review result:

- DeepSeek read-only review returned `PASS/MERGE`.
- Confirmation: old single-request, top-level `requests`, and nested plan request extraction remain compatible.
- Confirmation: `--request-id` and `--control-group-id` only filter request dictionaries before handing them to the existing runners; runner, gate, database, paper-tracking, and combined-ledger behavior are unchanged.
- Confirmation: the nested-plan selector tests prove ignored requests are not executed.

## Round 50 Runtime Historical Gate Completion

Status: implementation completed locally; runtime historical gate artifacts generated; tests passed; DeepSeek review passed; ready to merge.

Round 50 scope:

- Optimized the shared shortpick daily-series loader by selecting only the columns needed to build `_Series` instead of hydrating full `Stock` and `MarketBar` ORM objects for every 1d bar.
- Added an `include_golden_cross` option to `_context_for_signal_day(...)` while keeping the default behavior unchanged. Golden-cross moving-average features are still computed for `momentum_volume_golden_cross_10_200`; portfolio eligibility and regime aggregation paths now skip those unused 10/200 calculations.
- Kept market-factor eligible-day counting on its prior index/date basis so the performance fix does not change that sample-count semantics.
- Used the Round 49 request selectors to execute the three credible-control historical gate requests one control at a time against the runtime database.
- Rebuilt the credible-control comparison plan with the resulting historical evidence aggregate.

Runtime artifacts:

- Source paper-tracking snapshot: `/Users/hernando_zhao/codex/runtime/projects/ashare-dashboard/output/analytics/20260611-credible-control-runtime/paper-tracking.json`.
- Original credible-control plan: `/Users/hernando_zhao/codex/runtime/projects/ashare-dashboard/output/analytics/20260611-credible-control-runtime/credible-control-plan.json`.
- Historical evidence aggregate: `/Users/hernando_zhao/codex/runtime/projects/ashare-dashboard/output/analytics/20260611-credible-control-runtime/perf/historical-backtest-evidence.aggregate.json`.
- Historical-gate-passed credible-control plan: `/Users/hernando_zhao/codex/runtime/projects/ashare-dashboard/output/analytics/20260611-credible-control-runtime/perf/credible-control-plan.historical-gate-passed.json`.
- Per-control historical backtest artifacts: `/Users/hernando_zhao/codex/runtime/projects/ashare-dashboard/output/shortpick-governance-backtests/20260611T1512-runtime-gate-perf/`.

Runtime result:

- The aggregate historical evidence returned `status=ready`, `evidence_count=3`, `passed_count=3`, and `blocked_count=0`.
- The three passed controls are `control_same_symbol_cooldown:v1`, `control_drawdown_reversal_filter:v1`, and `control_repeated_exposure_limit:v1`.
- Each evidence item reports `gate_status=passed` and `leakage_audit_status=passed`.
- The regenerated credible-control plan returned `status=ready`, `line_count=3`, `ready_line_count=3`, `blocked_line_count=0`, and all three lines set `paper_tracking_backfill_policy=allowed_after_historical_backtest_gate_passed`.
- This round created runtime artifacts only. It did not write database rows, did not append paper-tracking rows, did not materialize combined-ledger artifacts, and did not change true-forward tracking status.

Verification evidence before DeepSeek:

- Related regression passed: `python3 -m pytest tests/test_shortpick_portfolio_backtest.py tests/test_shortpick_strategy_slices.py tests/test_shortpick_strategy_governance.py` (`119 passed`).
- Static checks passed: `python3 -m ruff check src/ashare_evidence/shortpick_market_factor_study.py src/ashare_evidence/shortpick_portfolio_backtest.py`.
- Compile checks passed: `python3 -m compileall -q src/ashare_evidence/shortpick_market_factor_study.py src/ashare_evidence/shortpick_portfolio_backtest.py`.
- `git diff --check` passed.

Remaining blockers after Round 50:

- Execute governed retrospective replay for the three now-unlocked credible-control lines.
- Materialize combined-ledger retrospective rows only from ready replay artifacts with visible `evidence_basis=retrospective_forward_replay`.
- Keep true-forward tracking separate until rule-defined tracking starts in real forward time.
- Frontend exposure of these new control comparison lines remains pending until replay artifacts and combined-ledger materialization exist.

DeepSeek review result:

- DeepSeek read-only review returned `PASS/MERGE`.
- Confirmation: column loading preserves `_Series` construction while avoiding full ORM hydration.
- Confirmation: `include_golden_cross` remains backward-compatible by default, non-golden strategy ranking paths do not read golden-cross fields, and the golden-cross strategy still computes the 10/200 features.
- Confirmation: portfolio eligible-day and regime aggregation only need context existence and non-golden regime fields, so skipping unused golden-cross calculations there is semantically safe.
- Confirmation: Round 50 documentation is honest: the 3/3 passed runtime historical gate only unlocks historical-gate status and does not claim paper-tracking writes, combined-ledger materialization, true-forward status changes, or frontend exposure.
- Nonblocking suggestions addressed before merge: extracted `GOLDEN_CROSS_STRATEGY` in the market-factor study module and documented that hot paths should pass `include_golden_cross=False` when they do not read golden-cross fields.

## Round 51 Runtime Replay And Combined-Ledger Completion

Status: runtime replay artifacts generated; combined-ledger materialized; API and frontend verified; DeepSeek review passed; ready to merge.

Round 51 scope:

- Consumed the Round 50 historical-gate-passed credible-control plan.
- Ran all three nested `retrospective_replay_plan.requests` through `shortpick-governance-retrospective-replay`.
- Wrote ready `shortpick_retrospective_forward_replay` artifacts under the actually served runtime artifact root: `/Users/hernando_zhao/codex/runtime/projects/ashare-dashboard/data/runtime-artifacts/shortpick_retrospective_replays/`.
- Ran `shortpick-governance-combined-ledger-materialize` against `/Users/hernando_zhao/codex/runtime/projects/ashare-dashboard/data/runtime-artifacts`.
- Wrote a ready `shortpick_combined_ledger_backfill` artifact under `/Users/hernando_zhao/codex/runtime/projects/ashare-dashboard/data/runtime-artifacts/shortpick_combined_ledgers/`.
- Verified the live backend `/shortpick-lab/paper-tracking` and served frontend page at `http://127.0.0.1:5173/shortpick-lab?tab=paper-tracking`.

Runtime artifacts:

- Replay aggregate stdout: `/Users/hernando_zhao/codex/runtime/projects/ashare-dashboard/output/analytics/20260611-credible-control-runtime/replay/retrospective-replay.runtime-artifacts.aggregate.json`.
- Combined-ledger materialization stdout: `/Users/hernando_zhao/codex/runtime/projects/ashare-dashboard/output/analytics/20260611-credible-control-runtime/replay/combined-ledger-materialize.runtime-artifacts.aggregate.json`.
- Runtime replay artifacts:
  - `/Users/hernando_zhao/codex/runtime/projects/ashare-dashboard/data/runtime-artifacts/shortpick_retrospective_replays/shortpick-retrospective-forward-replay-request:f5bd43aac9146f02.json`.
  - `/Users/hernando_zhao/codex/runtime/projects/ashare-dashboard/data/runtime-artifacts/shortpick_retrospective_replays/shortpick-retrospective-forward-replay-request:b714d0e13817d7d4.json`.
  - `/Users/hernando_zhao/codex/runtime/projects/ashare-dashboard/data/runtime-artifacts/shortpick_retrospective_replays/shortpick-retrospective-forward-replay-request:3a4186dff6c24b5e.json`.
- Runtime combined-ledger artifact: `/Users/hernando_zhao/codex/runtime/projects/ashare-dashboard/data/runtime-artifacts/shortpick_combined_ledgers/shortpick-combined-ledger-backfill:c886e25ac71e2a36.json`.
- Frontend verification screenshot: `/Users/hernando_zhao/codex/runtime/projects/ashare-dashboard/output/analytics/20260611-credible-control-runtime/replay/shortpick-paper-tracking-combined-ledger.png`.

Runtime result:

- Replay aggregate returned `status=ready`, `request_count=3`, `artifact_count=3`, `ready_count=3`, and `blocked_count=0`.
- Each replay artifact had `input_candidate_count=260`, `replay_row_count=260`, `leakage_audit_status=passed`, `paper_tracking_write_policy=forbidden`, and `true_forward_tracking_eligible=false`.
- Combined-ledger materialization returned `status=ready`, `artifact_count=3` from replay discovery, `combined_row_count=777`, `retrospective_count=777`, `true_forward_count=0`, and `blocked_row_count=3`.
- The three blocked rows were duplicate `combined_ledger_row_id` rows removed by the materializer's duplicate guard. The dedup rate was `3 / 780`, about `0.38%`. There were no blocked replay sources.
- The live backend returned `combined_ledger.status=ready`, `artifact_count=1`, `rows=777`, `retrospective_count=777`, and `true_forward_count=0`.
- The served frontend rendered the `组合 Ledger 回放对照` block with `artifact 数 1`, `组合行 777`, `真实前向 0`, and `后验回放 777`, plus visible evidence-basis rows labeled `后验前向回放`.

Scope guard:

- This round wrote runtime artifacts only.
- It did not write database rows.
- It did not append primary paper-tracking rows.
- It did not make retrospective rows headline-eligible.
- It did not start true-forward tracking; true-forward tracking remains allowed only from real forward time after rule definition.

Remaining blockers after Round 51:

- True-forward credible-control tracking still needs the daily runtime generation path to emit real future rows from the registered rule start.
- Promotion/retirement decisions must continue to default to true-forward rows and use retrospective rows only as supporting research evidence.

DeepSeek review result:

- DeepSeek read-only review returned `PASS/MERGE`.
- Confirmation: Round 51 documentation is honest and does not claim database writes, primary paper-tracking writes, headline eligibility, or true-forward tracking.
- Confirmation: the evidence chain is sufficient to move P3.5/P3.7/P3.8 to runtime verified: three ready replay artifacts, a ready combined-ledger artifact with 777 retrospective rows, live API projection, and served frontend rendering.
- Confirmation: `blocked_row_count=3` is not blocking because the rows were duplicate `combined_ledger_row_id` rows removed by the materializer, with no blocked replay sources.
- Nonblocking suggestion incorporated before merge: record the dedup rate so future runs can detect unexpected duplicate growth.

## Round 52 - Filter-And-Reselect Semantic Correction

User clarification on 2026-06-11 changed the governing definition for the three P3 controls.

Correct definition:

- The frozen strategy first produces a ranked candidate pool for the signal day.
- Each control is an alternative strategy over that same ranked pool.
- For each control, scan candidates by original frozen rank and buy only the first candidate that passes the control.
- If rank1 is blocked, it is retained as audit metadata and rank2/rank3 can become the actual selected row.
- If no ranked candidate passes, the control has a no-trade event for that signal day.

Impact on Round 51:

- Round 51 artifacts are valid only as diagnostic allowed/blocked overlays over already-present paper-tracking rows.
- They are not valid evidence for the intended control strategies because they do not reselect from the ranked pool.
- The following runtime artifacts are therefore superseded for strategy evidence and must not be read by API/frontend projections after Round 52:
  - `/Users/hernando_zhao/codex/runtime/projects/ashare-dashboard/data/runtime-artifacts/shortpick_retrospective_replays/shortpick-retrospective-forward-replay-request:f5bd43aac9146f02.json`
  - `/Users/hernando_zhao/codex/runtime/projects/ashare-dashboard/data/runtime-artifacts/shortpick_retrospective_replays/shortpick-retrospective-forward-replay-request:b714d0e13817d7d4.json`
  - `/Users/hernando_zhao/codex/runtime/projects/ashare-dashboard/data/runtime-artifacts/shortpick_retrospective_replays/shortpick-retrospective-forward-replay-request:3a4186dff6c24b5e.json`
  - `/Users/hernando_zhao/codex/runtime/projects/ashare-dashboard/data/runtime-artifacts/shortpick_combined_ledgers/shortpick-combined-ledger-backfill:c886e25ac71e2a36.json`

Reusable data:

- Runtime `shortpick_candidates` rows are reusable because they preserve same-run candidate pools and `source_rank` for market-factor overlays.
- Historical market bars and validation snapshots remain reusable.
- Round 51 replay/combined-ledger JSON rows are not reusable as strategy result rows; at most they can be manually referenced as obsolete diagnostic overlay evidence.

Implemented in Round 52:

- Retrospective replay runner now requires `ranked_candidates` or `ranked_candidate_pools` input and blocks old `paper_tracking.items`-only inputs with `missing_ranked_candidate_pool`.
- Retrospective replay runner now emits `selection_policy=filter_ranked_pool_select_first_allowed`.
- Same-symbol cooldown and repeated-exposure replay are evaluated sequentially by signal date using prior selected rows, so stateful controls no longer count every allowed candidate as if it were bought.
- Drawdown/reversal replay filters all ranked candidates for the day and keeps only the first allowed candidate.
- Historical P3 control mappings now output one selected row per signal day, not all allowed rows.
- Combined-ledger artifact discovery now accepts only replay artifacts with `selection_policy=filter_ranked_pool_select_first_allowed`.
- Combined-ledger artifact store now accepts only combined-ledger artifacts with the same `selection_policy`, so old Round 51 combined-ledger JSON is ignored even before physical cleanup.
- Physical cleanup removed the four superseded Round 51 runtime JSON files from `shortpick_retrospective_replays` and `shortpick_combined_ledgers`.
- Live backend verification after cleanup returned `combined_ledger.artifact_count=0`, `combined_row_count=0`, `true_forward_count=0`, and `retrospective_count=0`, so the obsolete 777-row overlay output is no longer served.

Acceptance criteria for Round 52:

- Focused tests pass for historical control mappings, retrospective replay CLI, combined-ledger materialization, and artifact-store filtering.
- Live artifact cleanup removed the four superseded Round 51 runtime JSON files so the frontend cannot display obsolete 777-row overlay output.
- Backend `/shortpick-lab/paper-tracking` returns no combined-ledger rows from the superseded Round 51 artifact after cleanup.
- DeepSeek review returned `PASS/MERGE`; its only note was the now-completed physical cleanup of stale runtime JSON files.

## Round 53 - Runtime Ranked-Pool Replay Materialization

Round 53 scope:

- Build a runtime replay input layer for the corrected user definition: `frozen ranked pool -> apply control filter -> buy highest original-rank candidate that passes`.
- Do not reuse other control families as a proxy for the frozen ranked pool.
- Do not write paper-tracking rows or database rows.
- Regenerate served runtime artifacts only after old overlay artifacts have been removed.

Implemented in Round 53:

- Added `shortpick_ranked_pool_replay_input.py` to reconstruct the frozen low-turnover ranked candidate pools from signal-date market bars.
- The reconstruction uses `baseline_family=frozen_paper_low_turnover_uptrend_v4`, `ranking_family=liquid_low_turnover_20d_uptrend`, `pool_limit=120`, and the configured rank limit.
- The reconstruction emits replay-only candidate rows with candidate rank, signal-date drawdown/reversal features, and stock-return `validation_by_horizon` needed by cooldown state.
- The retrospective replay CLI now uses `--database-url` to enrich paper-tracking JSON with reconstructed ranked pools unless `--skip-ranked-pool-reconstruction` is passed.
- The drawdown/reversal replay runner now reads signal features from ranked candidate pools as well as primary paper-tracking items.
- Runtime generation performance was optimized from roughly one minute to about 8 seconds by loading only the replay date window instead of the full 2.6GB runtime DB history.

Runtime artifacts generated in Round 53:

- Replay aggregate: `/Users/hernando_zhao/codex/runtime/projects/ashare-dashboard/output/analytics/20260611-credible-control-runtime/replay/retrospective-replay.runtime-artifacts.aggregate.json`
  - `status=ready`
  - `request_count=3`
  - `artifact_count=3`
  - `ready_count=3`
  - `blocked_count=0`
  - Each control has `input_candidate_count=132`, `replay_row_count=22`, and `no_trade_signal_count=0`.
- Served replay artifact directory: `/Users/hernando_zhao/codex/runtime/projects/ashare-dashboard/data/runtime-artifacts/shortpick_retrospective_replays/`
  - Contains three corrected replay JSON artifacts. They reuse the request artifact IDs from the request plan, but their contents are newly regenerated under `selection_policy=filter_ranked_pool_select_first_allowed`.
- Combined-ledger aggregate: `/Users/hernando_zhao/codex/runtime/projects/ashare-dashboard/output/analytics/20260611-credible-control-runtime/replay/combined-ledger-materialize.runtime-artifacts.aggregate.json`
  - `status=ready`
  - `source_replay_artifact_count=3`
  - `ready_replay_artifact_count=3`
  - `retrospective_count=66`
  - `combined_row_count=66`
  - `blocked_row_count=0`
- Served combined-ledger artifact: `/Users/hernando_zhao/codex/runtime/projects/ashare-dashboard/data/runtime-artifacts/shortpick_combined_ledgers/shortpick-combined-ledger-backfill:7aa7556ac3fa3195.json`

Verification in Round 53:

- `python3 -m pytest tests/test_shortpick_portfolio_backtest.py tests/test_shortpick_strategy_governance.py -q` passed with `116 passed`.
- `python3 -m compileall -q src/ashare_evidence/shortpick_ranked_pool_replay_input.py src/ashare_evidence/shortpick_strategy_replay_runner.py src/ashare_evidence/cli.py` passed.
- Runtime replay CLI completed in about `real 7.95s`.
- Runtime API verification via `http://127.0.0.1:8000/shortpick-lab/paper-tracking` returned `combined_ledger.status=ready`, `artifact_count=1`, `combined_row_count=66`, `true_forward_count=0`, and `retrospective_count=66`.
- Browser automation was not available in the local Node REPL because Playwright is not installed; live API route verification is the served-route check for this round.
- DeepSeek sharded read-only review returned `PASS/MERGE` for code semantics and final `PASS`; no blocking issues were reported.

Acceptance criteria for Round 53:

- Corrected replay artifacts are generated from the frozen low-turnover ranked pool, not from another control family's persisted rows.
- Each P3 control produces one selected retrospective row per signal day under `filter_ranked_pool_select_first_allowed`.
- Corrected combined-ledger artifact is visible to the runtime API as retrospective evidence only.
- No database rows or primary paper-tracking rows are written.
- Old Round 51 overlay artifact contents remain removed; any current same request artifact filenames are regenerated corrected artifacts.

## Round 54 - True-Forward Control Runtime Wiring

Round 54 scope:

- Wire the three P3 controls into the daily market-factor overlay runtime as true-forward controls.
- Use the clarified user definition: start from the frozen low-turnover ranked pool, apply the control filter, then insert only the original-rank highest allowed candidate.
- Do not read retrospective replay artifacts or combined-ledger artifacts for runtime decisions.
- Do not mutate existing runtime database rows or backfill paper-tracking rows during this implementation round.

Implemented in Round 54:

- Added true-forward runtime tracking roles and families:
  - `market_factor_control_same_symbol_cooldown_low_turnover_uptrend`
  - `market_factor_control_drawdown_reversal_low_turnover_uptrend`
  - `market_factor_control_repeated_exposure_low_turnover_uptrend`
- Added these roles to the paper-control contract and paper-control horizon set so future runtime candidates use the same 10-day paper tracking surface.
- Added signal-date drawdown/reversal feature generation to market-factor contexts using only signal-date-or-prior daily bars.
- Added runtime ranked-pool candidate row generation for the frozen low-turnover ranked pool.
- Added runtime filter-and-reselect insertion that writes at most one candidate per P3 control, with `evidence_basis=true_forward_tracking`, `rule_defined_at=2026-06-10`, `rule_signature`, `selection_policy=filter_ranked_pool_select_first_allowed`, and blocked-higher-ranked metadata in payload.
- Same-symbol cooldown runtime state now reads only post-rule, same-tracking-role completed negative outcomes and a post-rule runtime signal-date calendar.
- Repeated exposure runtime state now reads only post-rule, same-tracking-role prior signal rows.
- Drawdown/reversal runtime state reads signal-date feature rows from the ranked pool, not from future outcome or retrospective artifacts.
- Added regression coverage for:
  - normal runtime insertion of all three P3 controls,
  - drawdown rank1 block causing rank2 selection,
  - cooldown/repeated-exposure same-control post-rule state causing rank2 selection,
  - pre-rule dirty rows being ignored,
  - cooldown helper support for an external signal-date calendar.

Verification in Round 54:

- `pytest -q tests/test_shortpick_lab.py -m runtime_integration` passed with `28 passed`.
- `pytest -q tests/test_shortpick_strategy_governance.py tests/test_shortpick_lab_paper_tracking.py -k 'combined_ledger or true_forward or retrospective or same_symbol_cooldown or drawdown_reversal or repeated_exposure'` passed with `45 passed, 59 deselected`.
- `ruff check src/ashare_evidence/shortpick_lab.py src/ashare_evidence/shortpick_strategy_governance.py tests/test_shortpick_lab.py tests/test_shortpick_strategy_governance.py` passed.
- `python3 -m py_compile src/ashare_evidence/shortpick_lab.py src/ashare_evidence/shortpick_strategy_governance.py` passed.
- DeepSeek review:
  - Initial broad read-only review hit `error_max_budget_usd` before a conclusion.
  - Sharded review passed the main production-code shard and governance/test shards; one shard raised a cross-file concern that pure governance helpers rely on callers for identity isolation.
  - Round 54 added a dedicated runtime state-isolation test covering that concern.
  - Final DeepSeek arbitration returned `PASS/MERGE` with no blocking finding.

Acceptance criteria for Round 54:

- Daily runtime can generate true-forward rows for the three P3 controls from the frozen low-turnover ranked pool.
- A blocked rank1 is stored as audit metadata; it is not inserted as a buy row for that control.
- Stateful controls read only same-control, post-rule true-forward state.
- Retrospective artifacts and combined-ledger artifacts remain research evidence and are not consulted for runtime selection.
- No existing runtime database rows, replay artifacts, or paper-tracking rows are changed by this implementation round.

## Round 55 - Plan Status Reconciliation

Round 55 scope:

- Reconcile stale plan statuses after Round 54 without changing runtime code or data.
- Mark items complete only when later rounds already supplied implementation, frontend/runtime wiring, and verification evidence.
- Preserve real remaining blockers instead of hiding them under a broad "completed" label.

Implemented in Round 55:

- Updated P2.5 from `partial` to `completed_runtime_frontend_wired_published_verified`.
- The completion basis is the later implementation chain already recorded in this plan:
  - Round 29 wired paper-tracking governance partitioning into the API ledger.
  - Round 30 rendered deprecated/archive buckets and removed deprecated rows from latest simulated trade choices.
  - P4.1-P4.5 added strategy labels, evidence-basis sections, archive summaries, leakage/coverage notes, and report projection.
  - Rounds 21-24 published and runtime-verified the replay-feedback governance projection.
- Kept P2.7 as not fully complete because the plan still separates frontend hiding from the remaining continued-advancement/generation policy for `retire_candidate`.
- Kept P2.8 as not fully complete because no durable real inventory decision source has yet supplied explicit `inventory_diagnostic_value` decisions.

Verification in Round 55:

- `rg` evidence check across `src`, `frontend`, `tests`, and this plan confirmed the runtime/API/frontend governance projection and deprecated-bucket code paths exist.
- No code, runtime data, registry, artifact, or frontend file was changed in this round.
- DeepSeek read-only review returned `PASS/MERGE`; it agreed that P2.5 can be marked complete and that P2.7/P2.8 should remain explicitly open.

Acceptance criteria for Round 55:

- P2.5 no longer appears as a stale partial item.
- Remaining `partial/pending` statuses distinguish real blockers from already-completed frontend/runtime view wiring.
- This round remains documentation-only and does not claim new runtime behavior.

## Round 56 - Close Open Governance Items

Round 56 scope:

- Close the remaining user-visible P2.7/P2.8 governance items without opening another broad analysis round.
- Make deprecated strategy/control decisions affect both display and continued generation.
- Add a durable runtime source for inventory-driven archival decisions so the frontend can show real archived-control counts.

Implemented in Round 56:

- `filter_shortpick_generation_eligible_items(...)` now treats `retire_candidate`, `retired`, and `inventory_archived` as deprecated generation statuses. `retire_candidate` no longer silently continues active generation; archive/diagnostic rebuilds can still opt in explicitly.
- `project_shortpick_strategy_view_sections(...)` now sends all deprecated statuses, including `retire_candidate`, to the archive section.
- Added durable `shortpick_control_inventory_archive` artifact read/write support under runtime artifact roots.
- Added `shortpick_control_inventory_archive_items_from_artifacts(...)` so inventory artifact rows feed the existing diagnostic-value archival gates without duplicating decision logic.
- Wired inventory archive artifacts into `/shortpick-lab/paper-tracking` and active market-factor generation governance.
- Added frontend type fields and a visible paper-tracking metric for inventory archive decisions and artifact count.
- Added `inventory_archive_decision_count` to the paper-tracking governance summary so the UI can show a durable archival decision even when the current paper-tracking ledger has no matching historical row for that archived control.

Verification in Round 56 before DeepSeek review:

- `pytest -q tests/test_research_artifact_store.py::ResearchArtifactStoreTests::test_shortpick_control_inventory_archive_source_reads_only_ready_artifacts tests/test_shortpick_strategy_governance.py -k 'generation_filter or strategy_view_projection or inventory_archive' tests/test_shortpick_lab_paper_tracking.py -k 'inventory_archive or retirement_artifact_source' tests/test_shortpick_lab.py::ShortpickLabTests::test_market_factor_overlay_excludes_retired_generation_strategy tests/test_frontend_shortpick_static.py::FrontendShortpickStaticTests::test_shortpick_lab_is_independent_research_surface` passed.
- `pytest -q tests/test_shortpick_strategy_governance.py tests/test_shortpick_lab_paper_tracking.py tests/test_research_artifact_store.py -k 'shortpick or inventory or generation_filter or strategy_view_projection'` passed.
- `python3 -m compileall -q src/ashare_evidence` passed.
- `npm run build` in `frontend/` passed.
- DeepSeek flash diff review returned `PASS/MERGE`. Nonblocking observation: generation filtering and the source summary expose slightly different ready-artifact lists; this is harmless because filtering still uses only generation-authoritative `retire_candidate|retired` statuses, while the summary reports source visibility.
- Follow-up visible-count patch passed `pytest -q tests/test_shortpick_lab_paper_tracking.py::ShortpickLabPaperTrackingTests::test_paper_tracking_reads_inventory_archive_artifact_source_for_deprecated_bucket tests/test_frontend_shortpick_static.py`, `ruff check src/ashare_evidence/api.py tests/test_shortpick_lab_paper_tracking.py tests/test_frontend_shortpick_static.py`, and `git diff --check`.
- DeepSeek flash review of the visible-count patch returned `PASS/MERGE`.
- Push hook on merge to `main` passed `784 passed, 167 deselected, 6 subtests passed`, plus policy governance audit `pass`.
- Runtime publish synced commit `85c9add48a4d70f94cbede9da1f7b3c12b877d3a`; release parity manifest was written at `/Users/hernando_zhao/codex/runtime/projects/ashare-dashboard/output/releases/20260611T130134Z-85c9add48a4d/manifest.json`, and `latest-successful.commit` points to the same commit.
- Post-deploy synchronous refresh was terminated after the release had already been verified and persisted because the refresh process produced no output and no CPU for several minutes; `scripts/verify-deploy.sh` was run manually afterward and passed `19 passed, 0 failed`.
- Local and canonical authenticated `/shortpick-lab/paper-tracking/summary` returned `inventory_archive_decision_count=1`, `inventory_archive_artifact_source.artifact_count=1`, and `inventory_archive_artifact_source.decision_count=1`.
- Canonical browser verification at `https://hernando-zhao.cn/projects/ashare-dashboard/?view=shortpick&shortpickTab=paperTracking` rendered the visible metric card as `库存归档决策 1` with secondary text `artifact 1`.

Acceptance criteria for Round 56:

- P2.7 no longer has continued-generation wiring pending.
- P2.8 no longer depends on a missing real inventory decision source.
- The paper-tracking page can show inventory archive counts from durable artifacts.
- Runtime DB paper-tracking rows are not mutated by the code change; durable inventory decisions are supplied through artifacts.

Post-merge paper-tracking record-group correction:

- The three retrospective control display names (`同股冷却过滤`, `回撤/反转过滤`, `重复暴露限制`) remain in the existing `记录分组` filter rather than a separate rule-name filter.
- Paper-tracking rows now render the same record-group display field with `paperTrackingRecordGroupLabel(item)`, so retrospective replay rows show the concrete control name while preserving the underlying governance `tracking_group` for statistics and headline eligibility.
- Verification: `pytest -q tests/test_frontend_shortpick_static.py tests/test_frontend_shortpick_paper_tracking_helpers.py`, `npm run build`, and `git diff --check` passed. A focused DeepSeek read-only review returned `PASS`.

Post-merge retrospective-control exit-track correction:

- The three retrospective filter-and-reselect controls keep only meaningful paper exit tracks in `纸面跟踪记录（正式策略与对照组）`: `机械5日`, `机械10日`, and `止盈止损`.
- `机械1日` and `机械3日` are no longer projected as display tracks for these retrospective control rows. Shorter completed horizons can still inform the conservative `止盈止损` proxy trigger timing when they cross the configured paper risk thresholds.
- The `止盈止损` proxy remains visibly retrospective: it is derived from completed horizon returns because the combined-ledger artifacts do not contain a full daily high/low path, and it keeps retrospective evidence labels instead of mutating raw artifacts or true-forward paper rows.
- DeepSeek read-only review found no blocking issues and said the change can merge; it recommended direct tests for take-profit and 10-day fallback proxy branches, which were added before merge.
- Verification before merge: `pytest -q tests/test_shortpick_lab_paper_tracking.py -m runtime_integration`, `pytest -q tests/test_frontend_shortpick_paper_tracking_helpers.py tests/test_frontend_shortpick_static.py`, `ruff check src/ashare_evidence/api.py tests/test_shortpick_lab_paper_tracking.py`, `python3 -m compileall -q src/ashare_evidence/api.py`, and `git diff --check` passed.
- Browser verification then exposed a frontend fallback leak: when a retrospective replay row had only a completed 1-day or 3-day horizon and no display exit track yet, the table still rendered the generic `1日/3日` fallback. A hotfix changed the frontend helper so retrospective rows without a meaningful display track show `等待窗口` and `收益 --`, while ordinary non-retrospective rows keep the old completed-horizon fallback. DeepSeek reviewed this hotfix and found no blocking issue.
- Hotfix verification: `pytest -q tests/test_frontend_shortpick_paper_tracking_helpers.py tests/test_frontend_shortpick_static.py`, `pytest -q tests/test_shortpick_lab_paper_tracking.py -m runtime_integration`, `npm run build`, `ruff check`, and `git diff --check` passed.

## Validation To Run For This Planning Task

## Paper-Tracking Chart And Timeout Follow-Up - 2026-06-11

Scope:

- Move the cumulative-return strategy selector into the `累计纸面收益` chart card, make its default `冻结策略`, and prevent the selector from being squeezed/truncated.
- Add a card-level selector to `策略退出效果排名` with `均值`, `中位收益`, and `胜率`; default metric is `均值`.
- Keep chart-to-table linkage useful without trapping the chart in a single-strategy view: charts now ignore record-group and exit-result filters, and the chart panel exposes `清除图表联动筛选`.
- Reduce paper-tracking timeout risk without dropping rows: full ledger uses the long-running frontend request behavior, the backend SQL query no longer has the historical 1000-row safety cap, and `/shortpick-lab/paper-tracking/summary` no longer returns full combined-ledger row arrays.

Measured request facts before publish:

- Canonical direct paper-tracking route via a same-origin proxy made 4 startup data requests: `/auth/context`, `/dashboard/shell`, `/stocks/002028.SZ/dashboard`, and `/shortpick-lab/paper-tracking`; `/dashboard/scheduled-refresh-status` then started its periodic polling.
- The slow path is not broad tab fan-out. The observed bottleneck is the full `/shortpick-lab/paper-tracking` ledger, which measured about `76.5s` once during concurrent/proxy validation and `9.2s` on a follow-up direct canonical sample, with a `2.7MB` response.
- Local TestClient compact summary after the change returns `items=[]` and combined-ledger counts only, with no `rows`, `true_forward_rows`, or `retrospective_rows`.

Verification:

- `PYTHONPATH=src python3 -m unittest tests.test_frontend_shortpick_static tests.test_shortpick_lab_paper_tracking`
- `python3 -m py_compile src/ashare_evidence/api.py`
- `git diff --check`
- `npm run build`

Status:

- Implementation completed in task worktree `task/20260611-paper-tracking-selector-and-timeout-ea420a`.
- DeepSeek initial review found two blockers: compact summary still performed full combined-ledger row projection before discarding output, and the removed SQL row cap lacked an explicit regression guard. Both were fixed.
- DeepSeek focused re-review passed after the fix and found no remaining blocker before merge.
- Runtime publish pending after merge.


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
| P2.3 status recommendation layer + retirement artifact writer + runtime artifact source | completed_runtime_artifact_source_wired_ds_reviewed |
| Round 6 DeepSeek review | completed |
| P2.4 generation filter helper + active generation wiring | completed_generation_path_wired_ds_reviewed |
| Round 7 DeepSeek review | completed |
| P2.5 view projection helper | completed_runtime_frontend_wired_published_verified |
| Round 8 DeepSeek review | completed |
| P2.6 archive record helper | completed |
| Round 9 DeepSeek review | completed |
| P3.1 same-symbol cooldown helper | completed_true_forward_runtime_wired_ds_reviewed |
| Round 10 DeepSeek review | completed |
| P3.2 drawdown/reversal filter helper | completed_true_forward_runtime_wired_ds_reviewed |
| Round 11 DeepSeek review | completed |
| P3.3 repeated exposure limit helper | completed_true_forward_runtime_wired_ds_reviewed |
| Round 12 DeepSeek review | completed |
| P3.4 historical backtest request builder + runner + P3 mappings | completed_filter_reselect_semantics_wired |
| Round 13 DeepSeek review | completed |
| P3.5 retrospective forward replay request builder + runner | completed_filter_reselect_runtime_ranked_pool_replay_materialized |
| Round 14 DeepSeek review | completed |
| P3.6 true forward tracking activation plan | completed_true_forward_runtime_wired_ds_reviewed |
| Round 15 DeepSeek review | completed |
| P4.1 strategy status labels | published_runtime_verified |
| Round 16 DeepSeek review | completed |
| P4.2 evidence-basis display sections | published_runtime_verified |
| Round 17 DeepSeek review | completed |
| P4.3 archive summary rows | published_runtime_verified |
| Round 18 DeepSeek review | completed |
| P4.4 leakage and coverage notes | published_runtime_verified |
| Round 19 DeepSeek review | completed |
| P4.5 analytical report governance projection | published_runtime_verified |
| Round 20 DeepSeek review | completed |
| Replay-feedback governance source wiring | published_runtime_verified |
| Round 21 DeepSeek review | completed |
| Frontend governance projection rendering | published_runtime_verified |
| Round 22 DeepSeek review | completed |
| Runtime publish and canonical browser verification | completed |
| Replay-feedback ready projection enrichment | published_runtime_verified_real_data |
| Round 24 DeepSeek review | completed |
| Release verifier timeout governance | completed_ds_reviewed_pending_publish_verifier_quiescence |
| Round 25 DeepSeek review | completed |
| Replay-feedback aggregate TTL cache | published_runtime_verified |
| Round 26 DeepSeek review | completed |
| Governance test hardening (Round 6/10/13 follow-ups) | completed |
| Round 27 DeepSeek review | completed |
| Intent-clarification amendment (Round 28) | requirements_recorded_runtime_implementation_started |
| Round 29 paper-tracking governance partition | completed_merged_plan_reconciled |
| Round 30 frontend deprecated bucket | published_runtime_verified |
| P2.7 deprecated display bucket + regression guard | published_runtime_verified |
| P2.8 redundant/meaningless control archival | published_runtime_verified |
| P3.7 labeled combined-ledger retrospective backfill + artifact writer + API source projection + frontend display | completed_filter_reselect_runtime_materialized_api_verified |
| P3.8 new credible control/comparison line build-out | completed_historical_gate_ranked_pool_replay_and_combined_ledger_runtime_verified |
| Round 54 true-forward control runtime wiring | completed_ds_reviewed_ready_to_merge |
| Round 55 plan status reconciliation | completed_ds_reviewed_ready_to_merge |
| Round 56 open governance items closeout | published_runtime_verified |
| Retrospective control exit-track display correction | ds_reviewed_ready_to_merge_publish |
| Runtime behavior changed | round56_deprecated_generation_statuses_excluded_and_inventory_archive_artifact_source_wired_no_runtime_db_mutation_published_verified |
| Registry changed | completed |
| Strategy code changed | completed_for_read_only_governance_builder_status_layer_filter_view_projection_archive_same_symbol_cooldown_drawdown_reversal_repeated_exposure_helpers_historical_backtest_request_builder_retrospective_forward_replay_request_builder_true_forward_activation_plan_combined_ledger_backfill_preparation_credible_control_line_buildout_plan_status_label_projection_evidence_basis_sections_archive_summary_rows_leakage_coverage_notes_report_governance_projection_replay_feedback_source_wiring_round54_true_forward_control_runtime_generation_and_round56_deprecated_generation_inventory_artifact_source |
| Frontend helper code changed | completed_for_strategy_status_evidence_basis_label_helpers_governance_projection_rendering_round30_deprecated_bucket_filtering_round31_inventory_archived_fallback_and_round56_inventory_archive_source_metric |
| Runtime data changed | corrected_replay_and_combined_ledger_artifacts_regenerated_in_round53_round54_and_round55_no_database_or_paper_tracking_writes_round56_added_runtime_inventory_archive_artifact_under_runtime_artifact_root |
| DeepSeek plan review | round56_pass_merge |

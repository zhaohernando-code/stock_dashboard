# Short Pick Strategy Governance Plan 2026-06-10

Status: round2_p0_protocols_completed_ds_review_passed
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
| P1.1 | Register `strategy_retirement:v1` artifact family | pending | Required fields should include strategy ID, version, retirement reason, evidence snapshot refs, archived-at timestamp, and replacement guidance. |
| P1.2 | Register `forward_validation_retrospective:v1` artifact family | pending | Must carry `retrospective: true`, source feature cutoff, replay generation time, and leakage-audit status. |
| P1.3 | Register `evaluation_baseline_random_pool:v1` | pending | Required before promotion or retirement logic cites random-pool outperformance or underperformance. |
| P1.4 | Register `evaluation_baseline_cooldown_control:v1` | pending | Required before promotion or retirement logic cites cooldown-control stability. |
| P1.5 | Register control group IDs and rule signatures | pending | Proposed initial IDs: `control_same_symbol_cooldown:v1`, `control_drawdown_reversal_filter:v1`, and `control_repeated_exposure_limit:v1`. |
| P1.6 | Add or extend JSON Schema where the registry requires machine validation | pending | Markdown-only descriptions are insufficient before implementation. |
| P1.7 | Define leakage audit checklist | pending | Retrospective replay must specify automated leakage checks before artifacts are trusted for evaluation. |

### P2 - Strategy Retirement Flow

| ID | Work Item | Status | Notes |
| --- | --- | --- | --- |
| P2.1 | Inventory active shortpick strategies and controls | pending | Include frozen lines, market-factor controls, LLM control, random pool, top3, offensive, cooldown, intraday, and historical-only variants. |
| P2.2 | Compute retirement evidence pack per strategy | pending | Include historical after-cost excess, forward mean/median/win rate, completed sample count, drawdown, tail dependence, and baseline comparison. |
| P2.3 | Mark candidates as `active`, `observe`, `retire_candidate`, or `retired` | pending | `retired` requires a `strategy_retirement:v1` artifact and decision-log entry. |
| P2.4 | Remove retired strategies from active generation | pending | Retired strategies should not consume daily compute unless explicitly requested for archive rebuild. |
| P2.5 | Remove retired strategies from primary frontend views | pending | Archive summaries remain visible in an audit or research archive view. |
| P2.6 | Preserve archived statistics and evidence refs | pending | Do not physically erase all evidence from the only auditable source of truth. |

### P3 - New Diagnostic Controls

| ID | Work Item | Status | Notes |
| --- | --- | --- | --- |
| P3.1 | Same-symbol cooldown control | pending | First version should operate by symbol. Suggested starting window: 5 or 10 trading days, with longer cooldown after a negative completed trade. |
| P3.2 | Drawdown/reversal filter control | pending | Blocks entries after short-window breakdown, high-level reversal, or recent drawdown threshold. Thresholds must be policy-governed. |
| P3.3 | Repeated exposure limit control | pending | Limits repeated concentration by symbol first, then optionally by industry or theme after stable classification exists. |
| P3.4 | Historical backtest generation | pending | Long-window deterministic backtest under existing account-executable universe rules. |
| P3.5 | Retrospective forward replay generation | pending | Replays from the paper-tracking ledger start date through the rule creation date using only signal-date available features. The current observed start is `2026-05-08`, but implementation must derive it from data. |
| P3.6 | True forward tracking start | pending | Starts only after control IDs, rule signatures, and artifact family contracts exist. |

### P4 - Frontend And Reporting

| ID | Work Item | Status | Notes |
| --- | --- | --- | --- |
| P4.1 | Add strategy status labels | pending | Status values should distinguish active, observe, retired, historical-only, retrospective-only, and true-forward. |
| P4.2 | Add separate display sections for evidence basis | pending | Historical backtest, retrospective replay, and true forward should not share a single headline as if they were the same evidence. |
| P4.3 | Add retirement archive view or archive summary rows | pending | Retired strategies should remain explainable without staying in the active compute path. |
| P4.4 | Add leakage and coverage notes | pending | Retrospective rows must show source cutoff and leakage audit status. |
| P4.5 | Update analytical report generation | pending | Future reports should read the new artifact contracts instead of inferring status from role names. |

## Retirement Threshold Draft

The first implementation should not retire a strategy only because a single recent metric is bad. Retirement requires a deterministic rule such as:

- Historical after-cost excess return is persistently negative under the account-executable universe.
- Completed forward evidence is mature enough for the strategy class.
- Forward mean and median are both negative, or median and win rate are materially worse than registered baselines.
- The strategy fails tail-dependence checks, such as positive mean being explained by one or two outliers while median and drawdown remain weak.
- The strategy does not provide unique diagnostic value that justifies continued compute.

Until the `strategy_retirement:v1` artifact family and required registry entries are implemented in P1, no strategy may be marked `retired`. The only allowed interim states are `active`, `observe`, or `retire_candidate`.

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
8. Transition behavior is explicit: until the registry and retirement artifacts exist, existing strategy generation and display semantics remain unchanged.

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
- Nonblocking follow-ups retained for P1: explain the source of the `-8%` tail threshold, treat 10 completed one-stock rows as a thin but conservative minimum because all gates must pass together, and convert leakage-audit text into executable checks when P1.7 lands.

## Validation To Run For This Planning Task

- `git status --short --branch`
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
| Runtime behavior changed | not_started |
| Registry changed | not_started |
| Strategy code changed | not_started |
| Runtime data changed | not_started |
| DeepSeek plan review | completed |

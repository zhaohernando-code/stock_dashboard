# Shortpick Model Exploration Workbench P1 Handoff

Date: 2026-07-03

Status: active implementation handoff

Owner: stock_dashboard / Short Pick research governance

## Purpose

This document is the next implementation contract after the P0 validation boundary work. The goal is to build the first real slice of the independent model exploration mechanism, not to keep extending the legacy `factor_observation` / `weight_sweep` diagnostic path.

The mechanism must answer:

- Can the system discover candidate models that repeatedly identify future strong stocks in historical walk-forward validation?
- Which feature groups and model specs survive out-of-sample, overfitting, execution, and winner-dependency gates?
- Which candidates should be killed, observed, paper-tracked, or eventually promoted?

The mechanism must not answer this by copying known strong-stock traits from 生益科技 or any other post-hoc winner.

## Completion Status / 完成状态

| Item | Status | Evidence / next action |
|---|---|---|
| P0 research validation storage boundary | completed | Existing branch writes legacy validation outputs to `research_validation/*` artifacts instead of runtime DB business tables. |
| Legacy factor validation guardrails | completed | Existing factor validation / weight-sweep path is diagnostic-only and blocks promotion. |
| Independent model exploration mechanism | in_progress | P1 matrix foundation and governed model spec registry exist, but no candidate prediction artifact or model comparison report exists yet. |
| P1 objective universe-date snapshot | foundation_completed | `src/ashare_evidence/model_exploration_snapshot.py` builds `model_exploration_input_snapshot` and `universe_date_matrix` from runtime DB read-only `Stock` / `MarketBar` facts, not from recommendation rows. |
| P1 PIT feature matrix | foundation_completed | `pit_feature_matrix` rows are keyed by `symbol` x `as_of_date`; tests assert feature cutoff stays at or before `as_of_date` and winner identity is not used. |
| P1 label matrix | foundation_completed | `executable_label_matrix` emits benchmark-aware forward labels and blocks missing benchmark labels instead of self-benchmarking. |
| P1 model spec registry | foundation_completed | `src/ashare_evidence/model_spec_registry.py` defines stable model specs, feature groups, bounded hyperparameter grids, dynamic-weight governance requirements and production-effect blocks. |
| P1 candidate runner | not_started | Produce candidate predictions from model specs over walk-forward train/test splits. |
| P1 comparison report | not_started | Write kill/observe/promote-blocked reports with OOS, PBO/DSR, winner-dependency and execution gates. |
| Dashboard/runtime integration | blocked | Do not expose new workbench results to live dashboard until approved projection artifacts exist. |

## Non-Negotiable Boundaries

- Runtime DB remains a read-only input source for research.
- Validation results, candidate scores, labels, model configs, trial rows and comparison reports must be artifacts under `research_validation/*`, not runtime DB business rows.
- Primary research rows must come from an objective universe and as-of dates, not from `recommendation_rows`, active watchlist membership, `factor_observation`, `recommendation_payload.factor_breakdown`, or previous winners.
- Existing legacy factor validation artifacts may be used only as diagnostic comparators.
- A model candidate cannot change policy config, recommendation generation, paper tracking, simulation policy, or dashboard claims.
- Missing benchmark data, insufficient samples, insufficient windows, stale quotes, execution infeasibility or blocked governance must fail closed.

## Required P1 Data Flow

```text
runtime DB read-only facts
  -> model_exploration_input_snapshot
  -> universe_date_matrix
  -> pit_feature_matrix
  -> executable_label_matrix
  -> model_spec_registry
  -> walk_forward_model_candidate_run
  -> model_comparison_report
  -> governance promotion gate
  -> dashboard approved projection, only after gate approval
```

## P1 Artifact Families

Add these artifact families under the existing `research_validation` namespace. The exact folder names may follow existing artifact-store conventions, but the family names must remain machine-addressable.

| Artifact family | Required status after P1 | Required purpose |
|---|---|---|
| `model_exploration_input_snapshot` | implemented | Freeze read-only source ranges, universe rules, as-of dates, benchmark availability, source hashes and data gaps. |
| `universe_date_matrix` | implemented | One row per eligible `symbol` x `as_of_date`; this is the primary row generator. |
| `pit_feature_matrix` | implemented | One feature row per matrix row; all features must be point-in-time and versioned. |
| `executable_label_matrix` | implemented | Forward labels using executable entry/exit assumptions, benchmark excess return and cost assumptions. |
| `model_spec_registry` | implemented | Governed model definitions, feature groups, hyperparameters and allowed search spaces. |
| `walk_forward_model_candidate_run` | not_started | Candidate model predictions, train/test windows, purge/embargo metadata and split-level metrics. |
| `model_comparison_report` | not_started | Model ranking, kill reasons, OOS metrics, PBO/DSR diagnostics, winner-dependency and promotion blockers. |

## Required Module Shape

Prefer new modules instead of extending `factor_observation.py` further.

| Module | Responsibility |
|---|---|
| `src/ashare_evidence/model_exploration_snapshot.py` | Build the source snapshot and objective universe-date matrix from runtime DB read-only facts. |
| `src/ashare_evidence/model_feature_matrix.py` | Build point-in-time features for each `symbol` x `as_of_date` row. |
| `src/ashare_evidence/model_label_matrix.py` | Build executable forward-return labels and benchmark-relative labels. |
| `src/ashare_evidence/model_spec_registry.py` | Define first governed model specs and feature groups. |
| `src/ashare_evidence/model_candidate_runner.py` | Run walk-forward model candidates and write prediction artifacts. |
| `src/ashare_evidence/model_comparison_report.py` | Build comparison, kill, blocker and claim-ceiling reports. |

Existing modules may be reused for shared helpers, artifact writing, date utilities and market-bar access. Do not make `factor_observation.py` the orchestration entrypoint for the model workbench.

## Universe-Date Matrix Contract

Each row must include:

- `symbol`
- `as_of_date`
- `stock_name`
- `board`
- `industry_code` / `industry_name` when available
- `eligible_for_account_profile`
- `eligibility_reasons`
- `has_market_bar`
- `has_benchmark_bar`
- `is_st`
- `is_suspended_or_stale`
- `limit_state`
- `tradable_lot_size`
- `source_lineage`

Minimum gates:

| Gate | Threshold |
|---|---:|
| unique symbols | `>= 500` preferred, `< 200` blocks model claims |
| as-of dates | `>= 120` preferred, `< 60` blocks model claims |
| total rows | `>= 60,000` preferred, `< 12,000` blocks model claims |
| benchmark coverage | `>= 95%` for official excess-return labels |

If the local runtime DB cannot meet these thresholds, P1 should still write artifacts, but `claim_ceiling` must remain `data_coverage_blocked`.

## Feature Matrix Contract

P1 must implement at least these feature groups:

| Group | Minimum features |
|---|---|
| price_momentum | `return_3d`, `return_5d`, `return_10d`, `return_20d`, `return_40d`, benchmark-relative returns |
| reversal_overheat | `return_1d`, gap/open proxy if available, distance from 20d high, distance from 40d high |
| volatility_risk | `volatility_10d`, `volatility_20d`, max drawdown 20d/40d |
| liquidity | average amount 10d/20d, turnover if available, zero-volume count, stale-bar count |
| execution | limit-up/down risk proxy, board lot efficiency, suspension/stale flags, T+1 availability proxy |
| regime | benchmark trend, benchmark volatility, size-style proxy when CSI300/CSI1000 are available |
| crowding | symbol recent exposure count, industry concentration, winner-dependency flags |

Feature rows must include:

- `feature_version`
- `feature_group_versions`
- `source_cutoff_at_or_before_as_of`
- `missing_feature_flags`
- `diagnostic_only_features`

No feature may use forward returns, validation labels, recommendation scores, or post-hoc winner identity.

## Label Matrix Contract

P1 labels must be executable and benchmark-aware.

Minimum labels:

- `forward_return_5d`
- `forward_return_10d`
- `forward_return_20d`
- `benchmark_return_5d`
- `benchmark_return_10d`
- `benchmark_return_20d`
- `excess_return_5d`
- `excess_return_10d`
- `excess_return_20d`
- `net_excess_return_10d_after_costs`
- `top_quantile_label_10d`
- `tradability_status`
- `label_block_reasons`

Blocked label conditions:

- Missing entry or exit bar.
- Missing benchmark bar for official excess-return labels.
- Suspended or stale quote.
- Unbuyable limit-up entry under the declared entry assumption.
- Unsellable limit-down exit under the declared exit assumption.
- Board/account ineligible.

## Initial Model Spec Registry

P1 should include deterministic and simple statistical candidates before any complex model.

| Model spec id | Type | Purpose |
|---|---|---|
| `baseline_momentum_10d_turnover_cooldown_v1` | deterministic baseline | Recreate the current family as a controlled baseline, not a promoted strategy. |
| `ranked_feature_linear_v1` | regularized linear/rank model | Combine feature groups with fixed training windows and bounded coefficients. |
| `ranked_tree_shallow_v1` | shallow tree / gradient boosting if dependency exists | Capture nonlinear interactions without deep overfit. |
| `regime_conditioned_linear_v1` | two-stage bounded model | Allow slow regime-conditioned weights only after enough windows exist. |

Every spec must declare:

- allowed feature groups
- training window length
- prediction horizon
- hyperparameter grid
- purge days
- embargo days
- max trials
- monotonic or sign constraints where applicable
- cost model
- account profile
- promotion gates

## Walk-Forward Validation Contract

Minimum protocol:

- Train on past windows only.
- Test on later windows only.
- Purge overlapping label windows.
- Embargo after training/test boundaries.
- Never tune on the final holdout slice.
- Record all tried model specs and hyperparameters, not only winners.

Minimum metrics:

- Rank IC by split and horizon.
- ICIR.
- Positive IC rate.
- Top/bottom quantile spread.
- Net excess return after costs.
- Turnover and capacity proxies.
- Max drawdown of simulated top-k portfolio.
- Winner-dependency: remove top 1 symbol, top 3 symbols, top 1 date, top 1 month and recompute.
- Regime stability by benchmark trend/volatility bucket.

Promotion remains blocked unless:

- OOS Rank IC `> 0.02`
- ICIR `> 0.35`
- Positive IC months `>= 55%`
- Top quantile net excess is positive after costs
- Deflated Sharpe confidence `>= 95%`
- PBO `<= 10%`
- Alpha t-stat or multiple-testing equivalent `>= 3.0`
- Cost stress remains positive under `2x` costs
- Winner-dependency checks do not collapse the result

## Comparison Report Contract

The report must make the result understandable without reading raw artifacts.

Required sections:

- `summary`: artifact ids, data coverage, run status, claim ceiling.
- `candidate_leaderboard`: model spec id, OOS metrics, gates, blocker ids.
- `baseline_comparison`: current deterministic baseline vs candidate models under the same windows.
- `overfit_diagnostics`: PBO/DSR/multiple comparison readout.
- `winner_dependency`: contribution concentration and recomputed results after removing top contributors.
- `execution_diagnostics`: blocked rows, limit/suspension/cost/capacity impact.
- `kill_list`: candidates rejected with concrete reasons.
- `next_research_questions`: bounded follow-up hypotheses, not broad brainstorming.

## Tests Required For P1

At minimum:

- Artifact store accepts new artifact families and rejects unsupported families. Completed by `tests/test_research_artifact_store.py`.
- Universe-date matrix does not use recommendation rows as the primary row source. Completed by `tests/test_model_exploration_snapshot.py`.
- Feature matrix rejects future data and marks missing sources. Foundation completed by `tests/test_model_exploration_snapshot.py`.
- Label matrix blocks missing benchmark labels instead of falling back to self-benchmark. Completed by `tests/test_model_exploration_snapshot.py`.
- Model spec registry has stable ids and bounded search spaces. Completed by `tests/test_model_spec_registry.py`.
- Candidate runner records all trials and cannot emit production promotion.
- Comparison report blocks claims when coverage/windows/OOS/PBO/DSR gates fail.

Default `python3 -m pytest -q` should remain fast. Slow full-matrix or long replay tests must be separate integration commands.

## Explicit Non-Goals For P1

- No live dashboard promotion.
- No policy config update.
- No production recommendation weight update.
- No paper-tracking migration.
- No claim that any candidate is executable alpha.
- No broad hyperparameter search outside registered model specs.
- No dynamic weights unless the model spec declares the function and the OOS gates pass.

## Handoff Instruction For Development Sessions

When a development session resumes this work, it must state which P1 artifact family it is implementing first and update the Completion Status table above. A session must not mark the independent model exploration mechanism complete until all P1 artifacts exist, tests pass, and the comparison report shows the mechanism can kill or block weak candidates without dashboard/runtime side effects.

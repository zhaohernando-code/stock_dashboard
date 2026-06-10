# Shortpick Strategy Inventory 2026-06-10

Status: round4_p2_1_inventory_completed_ds_review_passed
Owner: codex
Scope: Current Short Pick Lab strategy/control inventory for retirement-governance planning

## Purpose

This inventory completes P2.1 of `docs/contracts/SHORTPICK_STRATEGY_GOVERNANCE_PLAN_2026-06-10.md`.

It is not a retirement decision and does not change strategy code, generated data, paper-tracking rows, frontend/API behavior, or runtime scheduling. Its job is to define the current strategy/control universe so later P2 evidence packs do not mix true paper tracking, generated overlay candidates, and historical/replay-only variants.

## Source Files Reviewed

- `src/ashare_evidence/shortpick_lab.py`: strategy contract functions, market-factor overlay insertion, candidate payload fields, tracking roles, and labels.
- `src/ashare_evidence/default_policy_configs.py`: frozen strategy version/family and market-factor control configuration.
- `src/ashare_evidence/api.py`: paper-tracking ledger group mapping and inclusion rules.
- `frontend/src/components/shortpickLabPaperTracking.ts`: frontend paper-tracking group labels and sort order.
- `frontend/src/components/shortpickLabReplayMetrics.ts`: historical/replay portfolio strategy display mapping.

## Inventory Rules

- `true_forward_tracking` inventory means the role is included by `_build_shortpick_paper_tracking_ledger()` and can appear in the paper-tracking ledger when rows exist.
- `generated_overlay_only` means the candidate can be generated as a market-factor overlay candidate but is not included in strict paper tracking unless a registered paper-control role maps to it.
- `historical_or_replay_only` means the item is visible through replay/backtest/report surfaces, not as contemporaneous paper tracking.
- `configured_dormant` means config or helper code exists, but no current insertion path or paper-ledger role was found in the reviewed files.
- No item may be marked `retired` from this inventory alone. Retirement still requires `shortpick_strategy_retirement`, an evidence packet, and a `DECISIONS.md` entry.

## True Forward Paper-Tracking Inventory

| Inventory Item | Tracking Group | Tracking Role | Baseline Family / Source | Entry Basis | Current Governance Status | Source Evidence |
| --- | --- | --- | --- | --- | --- | --- |
| Frozen low-turnover uptrend v1 | `frozen_strategy` | `frozen_paper_primary` | `frozen_paper_low_turnover_uptrend_v4` | next trading-day close | active paper tracking | `shortpick_frozen_paper_strategy_contract()`, `insert_shortpick_market_factor_overlay_candidates()`, `_shortpick_tracking_group_for_role()` |
| Frozen low-turnover uptrend v2 open entry | `frozen_strategy_v2` | `market_factor_control_low_turnover_uptrend_next_open_entry` | `liquid_low_turnover_20d_uptrend_next_open_entry` | next trading-day open, with near-limit-up fill guard | active paper control | `default_policy_configs.py`, `insert_shortpick_market_factor_overlay_candidates()`, `_shortpick_tracking_group_for_role()` |
| LLM paper control | `llm_paper_control` | `llm_paper_control_primary` | LLM selected candidate after account filter | same entry/exit tracks as frozen v1 | active paper control | `shortpick_llm_paper_control_contract()`, `select_shortpick_llm_paper_control_candidate()`, `_build_shortpick_paper_tracking_ledger()` |
| Offensive top1 control | `market_factor_control` | `market_factor_control_offensive_top1` | `momentum_10d_turnover_rank` rank 1 | next trading-day close | active paper control | `shortpick_market_factor_paper_control_contracts()`, `insert_shortpick_market_factor_overlay_candidates()` |
| Cooldown top1 control | `market_factor_control` | `market_factor_control_cooldown_top1` | `momentum_10d_turnover_cooldown_rank` rank 1 | next trading-day close | active paper control | `shortpick_market_factor_paper_control_contracts()`, `insert_shortpick_market_factor_overlay_candidates()` |
| Deterministic random pool control | `market_random_control` | `market_factor_control_random_pool` | `momentum_pool_deterministic_random_control` | next trading-day close | active paper baseline | `shortpick_market_factor_paper_control_contracts()`, `_deterministic_shortpick_market_factor_random_item()`, `_shortpick_tracking_group_for_role()` |
| Top3 equal-weight control | `market_factor_control` | `market_factor_control_top3_equal_weight` | `momentum_10d_turnover_top3_equal_weight` ranks 1-3 | next trading-day close, equal-weight display | active paper control | `shortpick_market_factor_paper_control_contracts()`, `insert_shortpick_market_factor_overlay_candidates()` |
| Golden-cross control | `market_factor_control` | `market_factor_control_golden_cross_10_200` | `momentum_volume_golden_cross_10_200` | next trading-day close | active paper control when a signal exists | `shortpick_market_factor_paper_control_contracts()`, `insert_shortpick_market_factor_overlay_candidates()` |
| Legacy second-candidate control | `market_factor_control` | `market_factor_control_legacy_second_candidate` | `momentum_10d_turnover_legacy_second_candidate` | next trading-day close | active paper control when gate passes | `shortpick_market_factor_paper_control_contracts()`, `insert_shortpick_market_factor_overlay_candidates()` |
| Strong-breadth rank2 control | `market_factor_control` | `market_factor_control_strong_breadth_rank2` | `momentum_10d_amount_turnover_strong_breadth_rank2` | next trading-day close | active paper control when gate passes | `default_policy_configs.py`, `shortpick_market_factor_paper_control_contracts()`, `insert_shortpick_market_factor_overlay_candidates()` |
| No-limit-chase low-turnover control | `market_factor_control` | `market_factor_control_no_limit_chase_low_turnover_uptrend` | `liquid_low_turnover_20d_uptrend_no_limit_chase` | next trading-day close | active paper control when filtered candidate exists | `default_policy_configs.py`, `shortpick_market_factor_paper_control_contracts()`, `insert_shortpick_market_factor_overlay_candidates()` |
| Intraday same-day low-turnover control | `market_factor_control` | `market_factor_control_intraday_same_day_entry` | `liquid_low_turnover_20d_uptrend_intraday_same_day_entry` | same-day intraday current price with near-limit-up skip | active intraday paper control when scheduled slot runs | `run_shortpick_intraday_same_day_control()`, `insert_shortpick_intraday_same_day_candidate()`, `shortpick_market_factor_paper_control_contracts()` |

## Generated Overlay But Not Strict Paper Tracking

| Inventory Item | Tracking Role | Baseline Family / Source | Current Governance Status | Source Evidence |
| --- | --- | --- | --- | --- |
| Default cooldown ranks 2-6 | `control` | `momentum_10d_turnover_cooldown_rank` ranks 2-6 | generated overlay candidates, not included in strict paper ledger by role | `insert_shortpick_market_factor_overlay_candidates()` assigns `control` except rank 1 |
| Offensive ranks 2-6 | `control` | `momentum_10d_turnover_rank` ranks 2-6 | generated overlay candidates, not included in strict paper ledger by role | `insert_shortpick_market_factor_overlay_candidates()` assigns `control` except rank 1 |

These rows can still influence lab views and candidate history. They should not be treated as true paper-control evidence unless a later implementation registers and maps explicit tracking roles.

## Historical Or Replay-Only Inventory

| Inventory Item | Strategy / Family | Basis | Current Governance Status | Source Evidence |
| --- | --- | --- | --- | --- |
| Low-turnover uptrend portfolio replay | `low_turnover_20d_uptrend_liquid_top120` / `frozen_paper_low_turnover_uptrend_v4` | historical/replay portfolio readout | supporting evidence for frozen v1, not a new true-forward row | `replayPortfolioControlFamilyRows()` |
| Legacy second-candidate stop8 replay | `ret10_turnover_second_market_positive_cooldown_stop8` / `momentum_10d_turnover_legacy_second_candidate_stop8` | historical/replay portfolio readout | replay-only variant unless separately registered for paper tracking | `replayPortfolioControlFamilyRows()` |
| Strong-breadth rank2 stop12 replay | `ret10_amount_turnover_strong_breadth_rank2_stop12` / `momentum_10d_amount_turnover_strong_breadth_rank2` | historical/replay portfolio readout | supporting replay for active paper control | `replayPortfolioControlFamilyRows()` |
| Top3 equal-weight portfolio replay | `ret10_turnover_top3_market_positive_cooldown_equal_weight` / `momentum_10d_turnover_top3_equal_weight` | historical/replay portfolio readout | supporting replay for active paper control | `replayPortfolioControlFamilyRows()` |
| Golden-cross replay | `momentum_volume_golden_cross_10_200` | historical/replay portfolio readout | supporting replay for active paper control | `replayPortfolioControlFamilyRows()` |
| Raw offensive replay | `ret10_turnover` / `momentum_10d_turnover_rank` | historical/replay market and portfolio readout | supporting replay for offensive controls | `MARKET_PORTFOLIO_STRATEGY_CONFIGS` |
| Cooldown replay | `ret10_turnover_cooldown` / `momentum_10d_turnover_cooldown_rank` | historical/replay market and portfolio readout | supporting replay for cooldown controls | `MARKET_PORTFOLIO_STRATEGY_CONFIGS` |

## Configured But Not Active Paper-Ledger Inventory

| Inventory Item | Config Role / Family | Current Governance Status | Source Evidence |
| --- | --- | --- | --- |
| Standalone low-turnover uptrend control | `market_factor_control_low_turnover_uptrend` / `liquid_low_turnover_20d_uptrend` | embedded into frozen v1 selection; no standalone paper-ledger role found | `default_policy_configs.py`, `SHORTPICK_MARKET_FACTOR_PAPER_CONTROL_ROLES` |
| Quiet breakout rank2 | `market_factor_control_quiet_breakout_rank2` / `quiet_20d_5d_breakout_rank2` | configured and scored by helper branches, but no current insertion path or paper-ledger role found | `default_policy_configs.py`, `_rank_shortpick_market_factor_pool()`, `_upsert_shortpick_market_factor_candidate()` |

## Retirement Governance Implications

- P2 evidence packs must use the inventory category as part of the evidence key. A replay-only item cannot be retired from true-forward tracking because it never had true-forward tracking.
- Strict paper-tracking retirement candidates must be evaluated by `tracking_group`, `tracking_role`, `baseline_family`, entry basis, and horizon. Combining v1 next-close with v2 next-open would contaminate evidence.
- Generated overlay-only ranks 2-6 should first be classified as active display candidates or archive-only research rows before any compute deletion.
- Configured dormant items should not consume runtime compute unless a later implementation adds insertion and paper-ledger roles.
- The Northern Huachuang repeated-loss issue maps primarily to frozen v1/v2 and same-family low-turnover controls; it should not be generalized to LLM or random baselines without per-role evidence.

## Acceptance Checks

- This file inventories current known strategy/control surfaces and separates paper tracking from replay-only evidence.
- Each inventory category has source-code evidence.
- No retirement, deletion, data mutation, or frontend/runtime behavior change is introduced.
- P2.2 can use this file to decide which evidence packs need to be computed first.

## DeepSeek Review Result

Status: completed DeepSeek review.

Result:

- Blocking issues: none.
- Merge recommendation: merge and push Round 4.
- Key confirmations: all 12 active paper-tracking roles are present; generated overlay ranks 2-6 are correctly excluded from strict paper tracking; configured dormant low-turnover and quiet-breakout controls are correctly separated; replay-only rows match the frontend replay configuration; no retirement/runtime/data/frontend behavior is implied.
- Nonblocking follow-ups for P2.2 or later: clarify whether the standalone low-turnover control config is intentionally dormant, and keep the stop8 replay variant separate from the active legacy second-candidate paper control when computing evidence packs.

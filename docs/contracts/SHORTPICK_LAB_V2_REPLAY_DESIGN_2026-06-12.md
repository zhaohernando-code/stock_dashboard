# Short Pick Lab V2 Replay Design

Status: Contract draft ready for producer implementation
Owner: stock_dashboard
Created: 2026-06-12
Source plan: `docs/contracts/SHORTPICK_LAB_V2_PLAN_2026-06-12.md`
Schema: `docs/contracts/registry/schemas/shortpick_v2_replay_artifact.schema.json`

## Purpose

This document defines the first replay artifact contract for `试验田v2`.

V2 replay evidence answers an account-path question: under fixed account constraints, what would the account buy, skip, hold, and realize? It does not replace the existing Short Pick Lab paper-tracking ledger, and it must not mix candidate-level v1 forward returns with v2 account-level NAV claims.

This is a design contract only. It does not build a replay engine, generate replay results, expose APIs, or add frontend tabs.

## Artifact Family

| Field | Value |
| --- | --- |
| Artifact family | `shortpick_v2_replay_artifact` |
| Schema version | `v1` |
| Evidence basis | `historical_account_replay` |
| Claim ceiling | `research_observation` until promotion gates and forward paper tracking exist |
| Intended producer | Offline replay job in a later phase |
| Intended consumers | Future v2 read API and future `试验田v2 -> 历史回放` view |
| UI/API execution policy | Read-only projection of precomputed artifacts |

## Boundary From Existing Short Pick Lab

| Existing lab concept | V2 treatment |
| --- | --- |
| Candidate/paper rows | May be used only through a v2 candidate-source projection contract. |
| Candidate forward return | Input evidence and diagnostic context only; not an account NAV result. |
| Paper-tracking ledger | Not extended or overloaded by v2 replay. |
| Historical replay feedback | Not treated as v2 account replay unless projected into this artifact family. |
| Frontend components | May be reused later as presentation primitives only. |

The v2 artifact must carry its own `artifact_id`, `data_scope`, `input_contracts`, `rule_matrix`, `results`, `promotion_gate`, and `leakage_audit`. A consumer must be able to determine the account rules and sample basis without reading v1 UI state.

## Fixed Input Domains

| Domain | Required contract |
| --- | --- |
| Candidate source | A deterministic ranked-pool projection with signal date, rank, symbol, name, source role/family, and source feature cutoff. |
| Account profile | Default planning profile starts from CNY 200,000 total cash and new-retail-cash account eligibility. |
| Market bars | Daily bars used for entry, marking, exit, limit-up/down checks, and liquidity diagnostics. |
| Cost model | Buy/sell transaction cost assumptions and sell stamp-tax assumptions must be explicit. |
| Board lot model | Minimum board lot defaults to 100 shares and quantity must be rounded down to board-lot multiples. |
| Entry assumption | Entry price source must be one of the declared entry sources and must be tied to the signal date. |
| Exit assumption | Holding window, mechanical exit, risk exit, and unfillable exit handling must be explicit. |
| Leakage boundary | All buy/fallback/skip decisions may use only signal-day-or-earlier features. |

## Action Taxonomy

Only these signal-day actions are valid:

| Action | Meaning |
| --- | --- |
| `buy_primary` | Buy the highest-ranked candidate when it passes account and execution constraints. |
| `buy_fallback` | Buy a lower-ranked candidate allowed by a predeclared fallback policy. |
| `skip` | Buy nothing for the signal day because no candidate satisfies the fixed rules. |

No later-day discretionary entry is allowed. If a signal cannot be bought under the fixed rule on the declared entry date, the rule must either select an eligible fallback candidate or record a skip.

## Initial Rule-Family Matrix

These rule families are the first design matrix. They are not promoted strategies, and later replay evidence must choose a small governed subset before any user-visible paper tracking.

| Family | Required behavior | Main diagnostic question |
| --- | --- | --- |
| `top1_or_skip` | Buy rank 1 only if executable; otherwise skip. | How much of the original signal survives realistic execution? |
| `topn_fallback` | Scan rank 1 through a fixed TopN and buy the first executable candidate. | Does ranked fallback improve deployability without destroying selection quality? |
| `fixed_notional_lot_rounding` | Target a fixed notional sleeve, then round quantity down to board lots. | How much does board-lot rounding change exposure and returns? |
| `position_cap_utilization` | Use cash up to fixed per-position and portfolio caps, rounded to board lots. | Can cash utilization improve without concentrating the account? |
| `conservative_cash_reserve` | Keep a fixed cash reserve and reject buys that would breach it. | Does lower utilization reduce drawdown and forced concentration? |

Nominal share price must not become a standalone selection thesis. Lower share prices can only affect whether a fixed execution rule can use capital efficiently after board-lot rounding, position caps, liquidity checks, and drawdown metrics are applied.

## Required Output Domains

| Output domain | Purpose |
| --- | --- |
| Metadata | Identify the artifact, schema, status, generation time, plan reference, and claim ceiling. |
| Data scope | Declare signal window, trade-day count, series count, account profile, and coverage gaps. |
| Input contracts | Declare candidate-source, market-data, cost, entry, exit, and account assumptions. |
| Rule matrix | Declare every tested configuration before results are interpreted. |
| Results | Provide account-level summaries per configuration. |
| Decision samples | Provide bounded signal-day examples for buy/fallback/skip explainability. |
| Reason counts | Count deterministic action reasons such as insufficient cash, board-lot minimum, position cap, limit-up block, missing bar, or no fallback. |
| NAV/position refs | Point to detailed NAV, position, trade, and decision tables when they are too large for the artifact envelope. |
| Promotion gate | Declare whether a configuration is only observed, blocked, or eligible for later paper-tracking consideration. |
| Leakage audit | Prove decisions used only allowed source data. |

## Summary Metrics

Every replay result should expose at least:

| Metric | Meaning |
| --- | --- |
| `signal_count` | Number of signal days considered. |
| `trade_count` | Number of completed buys. |
| `skip_count` | Number of signal days with no buy. |
| `fallback_trade_count` | Number of buys from a fallback rank. |
| `final_nav` | Account NAV at the end of replay. |
| `total_return` | Account-level return from initial cash. |
| `max_drawdown` | Account NAV drawdown. |
| `mean_invested_ratio` | Average invested capital divided by account NAV. |
| `max_position_count` | Highest simultaneous open position count. |
| `turnover` | Account turnover under the rule. |
| `reason_counts` | Deterministic buy/fallback/skip reason counts. |

Candidate-level mean/median returns may be referenced only as source diagnostics. V2 headline metrics should remain account-level.

## Promotion Gate

Historical replay alone cannot make a production claim. A replay configuration can become a v2 paper-tracking candidate only when its artifact shows:

| Gate | Requirement |
| --- | --- |
| Data adequacy | Enough signal days, completed trades, market-regime coverage, and explicit gap reporting. |
| Execution realism | Board-lot, cash, position cap, entry, exit, and cost assumptions are present. |
| Explainability | Buy/fallback/skip reason counts and samples are present. |
| Risk visibility | Drawdown, cash utilization, concentration, and skipped-ratio metrics are present. |
| Leakage audit | Status is `passed`; blocked or not-run leakage audit cannot promote. |
| Bounded selection | Only a small governed subset may move to paper tracking in a later phase. |

## Efficiency Contract

V2 replay should be an offline/precomputed artifact workflow:

- Fixed market series and candidate pools should be loaded once per replay run and reused across rule configurations.
- The future page/API should read prepared artifacts or projections, not run replay or fetch market data on request.
- Large tables should be stored as referenced artifacts; the main envelope should carry bounded samples and summaries.

## Validation Notes For Later Producers

Later implementation should validate artifacts against `shortpick_v2_replay_artifact.schema.json` before publishing them to any UI-facing projection.

The first producer implementation should fail closed when:

- delayed or discretionary later-day entry appears as an action;
- candidate source lacks signal-date cutoff metadata;
- market bars are missing for required entry/exit windows;
- account constraints are incomplete;
- leakage audit is failed, blocked, or not run for any promoted configuration;
- the artifact tries to claim production or investment-advice status.

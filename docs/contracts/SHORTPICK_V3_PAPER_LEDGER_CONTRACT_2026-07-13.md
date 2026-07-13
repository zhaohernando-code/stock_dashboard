# Shortpick v3 Paper Ledger Contract

Status: implemented and runtime verification pending
Effective date: 2026-07-13
Common tracking start: 2026-07-08

## Product Invariants

- Every dashboard-visible v3 strategy starts from CNY 200,000 on 2026-07-08.
- Strategy accounts are independent. Cash, positions, NAV, orders, and exits cannot leak across strategies.
- Historical replay returns are never copied into the paper ledger.
- A daily candidate source is retained by signal date. A new refresh cannot overwrite the source or plan history for an earlier signal date.
- Frozen plans execute on the declared next-trading-day close. The fill uses the actual close, 100-share board lots, buy costs, available cash, and the configured concentration cap.
- Open positions retain the strategy's 20-trading-day horizon and accepted dynamic exit policy.
- Buy and sell fills become transaction rows and update the account curve on the same refresh.

## Synchronized Start Repair

The original implementation generated only the latest plan and never transitioned a due plan into a fill. The 2026-07-08 and 2026-07-09 candidate sources were therefore reconstructed from point-in-time features without forward labels so all eight strategies can be compared from one start date.

These reconstructed sources and their fills are marked `synchronized_start_backfill`. They are valid for a common-window paper comparison but must not be mislabeled as sources captured live on their signal date. Sources retained by the daily refresh use `daily_forward_capture`.

## State Contract

The persisted paper state contains:

- `records`: successful buy and sell fills shown in the transaction table;
- `account_states`: one cash account, positions, and NAV points per strategy;
- `planned_orders`: frozen orders that have not reached an executable market close;
- `plan_history`: append-only signal-date plan batches;
- `execution_events`: deterministic reasons for orders that cannot fill;
- `source_coverage`: common start/end and strategy coverage evidence.

## Acceptance Checks

- All eight strategy accounts report `tracking_start_date=2026-07-08`.
- At least one completed market day after the first executable signal produces transaction rows.
- The transaction table, cumulative return curves, drawdown comparison, cash, and positions come from the same persisted account state.
- Re-running the refresh is deterministic and does not duplicate fills.
- The next scheduled refresh retains earlier daily candidate sources and settles due frozen orders before producing the next plan.

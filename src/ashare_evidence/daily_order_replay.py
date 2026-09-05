"""Offline daily-bar execution audit with decision-time cash and share reservations.

This kernel deliberately makes no economic-return or exchange-fill certification.
It records price-only NAV; corporate actions require a separate verified ledger.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from decimal import ROUND_DOWN, Decimal
from typing import Any


def reserve_limit_order(
    *,
    symbol: str,
    signal_day: str,
    limit: float,
    budget: float,
    cash: float,
    buy_cost: float,
    lot_size: int,
) -> dict[str, Any] | None:
    """Reserve from observable cash; execution prices cannot resize a planned order."""
    price = float(Decimal(str(limit)).quantize(Decimal("0.01"), rounding=ROUND_DOWN))
    if price <= 0 or cash <= 0 or budget <= 0:
        return None
    quantity = int(min(budget, cash) / (price * (1 + buy_cost)) / lot_size) * lot_size
    if quantity <= 0:
        return None
    return {
        "symbol": symbol,
        "signal_day": signal_day,
        "limit": price,
        "shares": quantity,
        "reserved_cash": quantity * price * (1 + buy_cost),
    }


def executable_daily_bar(bar: dict[str, Any] | None) -> bool:
    """Flat bars are conservatively rejected because daily data cannot prove queues."""
    return bool(
        bar
        and bar["volume"] > 0
        and 0 < bar["low"] < bar["high"]
        and bar["low"] <= bar["open"] <= bar["high"]
        and bar["low"] <= bar["close"] <= bar["high"]
    )


def replay_reserved_daily_orders(
    *,
    calendar: list[str],
    decisions: list[dict[str, Any]],
    bars: dict[str, dict[str, dict[str, Any]]],
    initial_cash: float,
    decision_nav_fraction: float,
    hold_sessions: int,
    max_symbol_nav: float,
    max_signal_price: float,
    lot_size: int,
    buy_cost: float,
    sell_cost: float,
) -> dict[str, Any]:
    """Audit an externally frozen decision list; no ranking or signal policy is inferred."""
    decisions_by_day: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in decisions:
        decisions_by_day[row["as_of_date"]].append(row)
    calendar = sorted(set(calendar))
    if not calendar:
        raise ValueError("an explicit evaluation calendar is required")
    cash = float(initial_cash)
    pending: list[dict[str, Any]] = []
    positions: list[dict[str, Any]] = []
    ledger: list[dict[str, Any]] = []
    nav_rows: list[dict[str, Any]] = []
    signal_days = 0
    for index, day in enumerate(calendar):
        # Orders were reserved at the preceding signal close, before any future sale.
        for plan in pending:
            bar = bars.get(plan["symbol"], {}).get(day)
            cash += plan["reserved_cash"]
            if executable_daily_bar(bar) and bar["low"] < plan["limit"]:
                spent = plan["shares"] * plan["limit"] * (1 + buy_cost)
                cash -= spent
                position = {
                    **plan,
                    "entry_day": day,
                    "entry_index": index,
                    "entry_cost": spent,
                    "last_close": bar["close"],
                }
                positions.append(position)
                ledger.append(
                    {
                        **plan,
                        "day": day,
                        "action": "buy",
                        "price": plan["limit"],
                        "cost": plan["shares"] * plan["limit"] * buy_cost,
                    }
                )
            else:
                ledger.append({**plan, "day": day, "action": "cancel", "reason": "no_verified_limit_fill"})
        pending = []
        kept = []
        for position in positions:
            bar = bars.get(position["symbol"], {}).get(day)
            if bar:
                position["last_close"] = bar["close"]
            age = index - position["entry_index"]
            if age >= hold_sessions and executable_daily_bar(bar):
                gross = position["shares"] * bar["open"]
                cash += gross * (1 - sell_cost)
                ledger.append(
                    {
                        "day": day,
                        "signal_day": position["signal_day"],
                        "entry_day": position["entry_day"],
                        "symbol": position["symbol"],
                        "shares": position["shares"],
                        "action": "sell",
                        "price": bar["open"],
                        "cost": gross * sell_cost,
                        "holding_sessions": age,
                        "pnl": gross * (1 - sell_cost) - position["entry_cost"],
                    }
                )
            else:
                kept.append(position)
                if age >= hold_sessions:
                    ledger.append(
                        {
                            "day": day,
                            "symbol": position["symbol"],
                            "action": "defer_exit",
                            "holding_sessions": age,
                            "reason": "missing_or_flat_daily_bar",
                        }
                    )
        positions = kept
        market_values: dict[str, float] = defaultdict(float)
        for position in positions:
            market_values[position["symbol"]] += position["shares"] * position["last_close"]
        nav = cash + sum(market_values.values())
        if day in decisions_by_day and index + 1 < len(calendar):
            signal_days += 1
            for row in decisions_by_day[day]:
                symbol = row["symbol"]
                bar = bars.get(symbol, {}).get(day)
                if not (
                    symbol.startswith(("600", "601", "603", "605", "000", "001", "002", "003"))
                    and symbol.endswith((".SH", ".SZ"))
                    and bar
                    and 0 < bar["close"] <= max_signal_price
                ):
                    ledger.append({"day": day, "symbol": symbol, "action": "skip", "reason": "eligibility_or_price"})
                    continue
                order = reserve_limit_order(
                    symbol=symbol,
                    signal_day=day,
                    limit=bar["close"],
                    budget=nav * decision_nav_fraction,
                    cash=cash,
                    buy_cost=buy_cost,
                    lot_size=lot_size,
                )
                if order is None:
                    ledger.append({"day": day, "symbol": symbol, "action": "skip", "reason": "cash_or_board_lot"})
                    continue
                symbol_reserved = sum(p["shares"] * p["limit"] for p in pending if p["symbol"] == symbol)
                if market_values[symbol] + symbol_reserved + order["shares"] * order["limit"] > nav * max_symbol_nav:
                    ledger.append({"day": day, "symbol": symbol, "action": "skip", "reason": "symbol_concentration"})
                    continue
                cash -= order["reserved_cash"]
                pending.append(order)
                ledger.append({**order, "day": day, "action": "plan", "execution_day": calendar[index + 1]})
        reserved = sum(p["reserved_cash"] for p in pending)
        reconciled_nav = cash + reserved + sum(market_values.values())
        if cash < -1e-7 or abs(reconciled_nav - nav) > 1e-7:
            raise AssertionError("cash reservation / NAV accounting failure")
        nav_rows.append(
            {
                "day": day,
                "nav": nav,
                "cash": cash,
                "reserved_cash": reserved,
                "invested": sum(market_values.values()),
                "positions": len(positions),
                "max_symbol_weight": max(market_values.values(), default=0) / nav,
                "stale_marks": sum(day not in bars.get(p["symbol"], {}) for p in positions),
            }
        )
    pnl_by_symbol: dict[str, float] = defaultdict(float)
    for order in ledger:
        if order["action"] == "sell":
            pnl_by_symbol[order["symbol"]] += order["pnl"]
    for position in positions:
        pnl_by_symbol[position["symbol"]] += position["shares"] * position["last_close"] - position["entry_cost"]
    if abs(sum(pnl_by_symbol.values()) - (nav_rows[-1]["nav"] - initial_cash)) > 1e-7:
        raise AssertionError("lot P&L differs from account NAV")
    peak = initial_cash
    max_dd = 0.0
    underwater = longest_recovery = 0
    for row in nav_rows:
        peak = max(peak, row["nav"])
        max_dd = min(max_dd, row["nav"] / peak - 1)
        underwater = underwater + 1 if row["nav"] < peak - 1e-8 else 0
        longest_recovery = max(longest_recovery, underwater)
    half_years: dict[str, list[float]] = {}
    prior_nav = initial_cash
    for row in nav_rows:
        key = row["day"][:4] + ("-H1" if int(row["day"][5:7]) <= 6 else "-H2")
        half_years.setdefault(key, [prior_nav, row["nav"]])[1] = row["nav"]
        prior_nav = row["nav"]
    return {
        "summary": {
            "final_nav": nav_rows[-1]["nav"],
            "net_price_return": nav_rows[-1]["nav"] / initial_cash - 1,
            "max_drawdown": max_dd,
            "longest_underwater_sessions": longest_recovery,
            "unrecovered_at_end": underwater > 0,
            "signal_review_days": signal_days,
            "max_closed_holding_sessions": max(
                (r["holding_sessions"] for r in ledger if r["action"] == "sell"), default=0
            ),
            "max_open_holding_sessions": max((len(calendar) - 1 - p["entry_index"] for p in positions), default=0),
            "order_counts": dict(Counter(r["action"] for r in ledger)),
            "costs": sum(r.get("cost", 0) for r in ledger),
            "open_lots": len(positions),
            "max_symbol_weight": max(r["max_symbol_weight"] for r in nav_rows),
            "stale_mark_sessions": sum(r["stale_marks"] > 0 for r in nav_rows),
            "half_year_returns": {k: v[1] / v[0] - 1 for k, v in half_years.items()},
        },
        "ledger": ledger,
        "nav_rows": nav_rows,
        "pnl_by_symbol": dict(pnl_by_symbol),
        "open_positions": positions,
        "pending_orders": pending,
        "claim_ceiling": "reused_history_price_only_daily_bar_proxy_not_independent_or_total_return",
    }

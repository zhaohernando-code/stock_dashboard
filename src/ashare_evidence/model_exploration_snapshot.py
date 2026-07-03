from __future__ import annotations

import hashlib
import json
from datetime import UTC, date, datetime
from math import sqrt
from pathlib import Path
from statistics import mean, pstdev
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ashare_evidence.models import MarketBar, Stock
from ashare_evidence.research_artifact_store import write_research_validation_artifact

MODEL_EXPLORATION_PROTOCOL_VERSION = "shortpick_model_exploration_p1:v1"
MODEL_EXPLORATION_FEATURE_VERSION = "shortpick_model_pit_feature_matrix:v1"
MODEL_EXPLORATION_LABEL_VERSION = "shortpick_model_executable_label_matrix:v1"
MODEL_EXPLORATION_ACCOUNT_PROFILE = "new_retail_cash_account"
DEFAULT_BENCHMARK_SYMBOL = "000300.SH"
DEFAULT_HORIZONS = (5, 10, 20)


def _stable_digest(payload: Any) -> str:
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _safe_float(value: Any, default: float = 0.0) -> float:
    if isinstance(value, bool) or value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _pct_change(current: float, previous: float) -> float | None:
    if previous == 0:
        return None
    return current / previous - 1


def _mean(values: list[float]) -> float:
    return mean(values) if values else 0.0


def _std(values: list[float]) -> float:
    return pstdev(values) if len(values) > 1 else 0.0


def _observed_day(value: datetime) -> date:
    return value.date()


def _bar_row(stock: Stock, bar: MarketBar) -> dict[str, Any]:
    return {
        "id": bar.id,
        "bar_key": bar.bar_key,
        "stock_id": stock.id,
        "symbol": stock.symbol,
        "observed_at": bar.observed_at,
        "observed_date": _observed_day(bar.observed_at),
        "open_price": float(bar.open_price),
        "high_price": float(bar.high_price),
        "low_price": float(bar.low_price),
        "close_price": float(bar.close_price),
        "volume": float(bar.volume),
        "amount": float(bar.amount),
        "turnover_rate": bar.turnover_rate,
        "total_mv": bar.total_mv,
        "circ_mv": bar.circ_mv,
        "pe_ttm": bar.pe_ttm,
        "pb": bar.pb,
        "lineage_hash": bar.lineage_hash,
    }


def _is_benchmark_stock(stock: Stock) -> bool:
    profile = stock.profile_payload or {}
    return stock.symbol in {"000300.SH", "000905.SH", "000852.SH"} or str(profile.get("industry") or "") == "benchmark"


def _is_st_stock(stock: Stock) -> bool:
    profile = stock.profile_payload or {}
    name = str(stock.name or profile.get("name") or "")
    return bool(profile.get("is_st")) or name.upper().startswith(("ST", "*ST"))


def _board(stock: Stock) -> str:
    profile = stock.profile_payload or {}
    if profile.get("board"):
        return str(profile["board"])
    ticker = str(stock.ticker or stock.symbol.split(".")[0])
    if ticker.startswith(("688", "689")):
        return "STAR"
    if ticker.startswith(("300", "301")):
        return "ChiNext"
    if ticker.startswith(("8", "4")):
        return "BSE"
    if ticker.startswith(("600", "601", "603", "605", "000", "001", "002", "003")):
        return "main_board"
    return "unknown"


def _account_eligibility(stock: Stock) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    if stock.status != "active":
        reasons.append("stock_status_not_active")
    if stock.delisted_date is not None:
        reasons.append("delisted")
    if _is_st_stock(stock):
        reasons.append("st_or_special_treatment")
    if _is_benchmark_stock(stock):
        reasons.append("benchmark_index_not_stock_candidate")
    if _board(stock) != "main_board":
        reasons.append("not_new_retail_main_board")
    return not reasons, reasons


def _limit_state(current: dict[str, Any], previous: dict[str, Any] | None) -> str:
    if previous is None:
        return "unknown_no_previous_bar"
    daily_return = _pct_change(_safe_float(current["close_price"]), _safe_float(previous["close_price"]))
    if daily_return is None:
        return "unknown_previous_close_zero"
    if daily_return >= 0.095:
        return "limit_up_like"
    if daily_return <= -0.095:
        return "limit_down_like"
    return "normal"


def _window(values: list[float], size: int) -> list[float]:
    return values[-size:] if len(values) >= size else values[:]


def _return_from(closes: list[float], horizon: int) -> float | None:
    if len(closes) <= horizon:
        return None
    return _pct_change(closes[-1], closes[-horizon - 1])


def _features_for_bars(
    *,
    symbol: str,
    as_of_day: date,
    bars_until_as_of: list[dict[str, Any]],
    benchmark_until_as_of: list[dict[str, Any]],
    universe_row_id: str,
    source_snapshot_id: str,
) -> dict[str, Any]:
    closes = [_safe_float(row["close_price"]) for row in bars_until_as_of]
    highs = [_safe_float(row["high_price"]) for row in bars_until_as_of]
    amounts = [_safe_float(row["amount"]) for row in bars_until_as_of]
    volumes = [_safe_float(row["volume"]) for row in bars_until_as_of]
    returns = [
        value
        for index in range(1, len(closes))
        if (value := _pct_change(closes[index], closes[index - 1])) is not None
    ]
    benchmark_closes = [_safe_float(row["close_price"]) for row in benchmark_until_as_of]
    current = bars_until_as_of[-1]
    previous = bars_until_as_of[-2] if len(bars_until_as_of) >= 2 else None
    daily_return = _pct_change(_safe_float(current["close_price"]), _safe_float(previous["close_price"])) if previous else None
    avg_amount_20d = _mean(_window(amounts, 20))
    feature_values = {
        "price_momentum": {
            "return_3d": _return_from(closes, 3),
            "return_5d": _return_from(closes, 5),
            "return_10d": _return_from(closes, 10),
            "return_20d": _return_from(closes, 20),
            "return_40d": _return_from(closes, 40),
            "benchmark_return_20d": _return_from(benchmark_closes, 20),
        },
        "reversal_overheat": {
            "return_1d": daily_return,
            "distance_from_20d_high": closes[-1] / max(_window(highs, 20) or [closes[-1]]) - 1 if closes[-1] else None,
            "distance_from_40d_high": closes[-1] / max(_window(highs, 40) or [closes[-1]]) - 1 if closes[-1] else None,
        },
        "volatility_risk": {
            "volatility_10d": _std(_window(returns, 10)) * sqrt(10),
            "volatility_20d": _std(_window(returns, 20)) * sqrt(20),
            "max_drawdown_20d": closes[-1] / max(_window(highs, 20) or [closes[-1]]) - 1 if closes[-1] else None,
            "max_drawdown_40d": closes[-1] / max(_window(highs, 40) or [closes[-1]]) - 1 if closes[-1] else None,
        },
        "liquidity": {
            "avg_amount_10d": _mean(_window(amounts, 10)),
            "avg_amount_20d": avg_amount_20d,
            "avg_volume_20d": _mean(_window(volumes, 20)),
            "turnover_rate": current.get("turnover_rate"),
            "zero_volume_count_20d": sum(1 for value in _window(volumes, 20) if value <= 0),
        },
        "execution": {
            "limit_state": _limit_state(current, previous),
            "suspension_or_stale_proxy": _safe_float(current.get("volume")) <= 0,
            "t_plus_1_required": True,
            "board_lot_size": 100,
        },
        "regime": {
            "benchmark_return_10d": _return_from(benchmark_closes, 10),
            "benchmark_return_20d": _return_from(benchmark_closes, 20),
            "benchmark_volatility_20d": _std(
                [
                    value
                    for index in range(1, len(benchmark_closes))
                    if (value := _pct_change(benchmark_closes[index], benchmark_closes[index - 1])) is not None
                ][-20:]
            )
            * sqrt(20),
        },
        "crowding": {
            "amount_vs_20d_avg": _safe_float(current.get("amount")) / max(avg_amount_20d, 1.0),
            "symbol_recent_exposure_count": 0,
            "winner_identity_used": False,
        },
    }
    row = {
        "row_id": f"feature:{symbol}:{as_of_day.isoformat()}",
        "universe_row_id": universe_row_id,
        "symbol": symbol,
        "as_of_date": as_of_day.isoformat(),
        "feature_version": MODEL_EXPLORATION_FEATURE_VERSION,
        "feature_group_versions": {
            "price_momentum": "v1",
            "reversal_overheat": "v1",
            "volatility_risk": "v1",
            "liquidity": "v1",
            "execution": "v1",
            "regime": "v1",
            "crowding": "v1",
        },
        "source_input_snapshot_id": source_snapshot_id,
        "source_cutoff_at_or_before_as_of": True,
        "latest_feature_bar_date": as_of_day.isoformat(),
        "missing_feature_flags": _missing_feature_flags(feature_values, benchmark_until_as_of),
        "diagnostic_only_features": [],
        "feature_values": feature_values,
    }
    row["row_digest"] = _stable_digest(row)
    return row


def _missing_feature_flags(feature_values: dict[str, Any], benchmark_until_as_of: list[dict[str, Any]]) -> list[str]:
    flags: list[str] = []
    if len(benchmark_until_as_of) < 21:
        flags.append("limited_benchmark_history")
    for group_name, group in feature_values.items():
        if isinstance(group, dict) and any(value is None for value in group.values()):
            flags.append(f"{group_name}_partial")
    return sorted(set(flags))


def _label_for_row(
    *,
    symbol: str,
    as_of_day: date,
    stock_bars: list[dict[str, Any]],
    stock_index: int,
    benchmark_bars: list[dict[str, Any]],
    benchmark_by_day: dict[date, int],
    horizons: tuple[int, ...],
    universe_row_id: str,
    source_snapshot_id: str,
) -> dict[str, Any]:
    current = stock_bars[stock_index]
    current_close = _safe_float(current["close_price"])
    benchmark_index = benchmark_by_day.get(as_of_day)
    labels: dict[str, Any] = {}
    block_reasons: set[str] = set()
    if benchmark_index is None:
        block_reasons.add("missing_benchmark_entry_bar")

    for horizon in horizons:
        stock_exit = stock_bars[stock_index + horizon] if stock_index + horizon < len(stock_bars) else None
        benchmark_exit = (
            benchmark_bars[benchmark_index + horizon]
            if benchmark_index is not None and benchmark_index + horizon < len(benchmark_bars)
            else None
        )
        stock_return = _pct_change(_safe_float(stock_exit["close_price"]), current_close) if stock_exit else None
        benchmark_return = None
        if benchmark_index is not None and benchmark_exit is not None:
            benchmark_entry_close = _safe_float(benchmark_bars[benchmark_index]["close_price"])
            benchmark_return = _pct_change(_safe_float(benchmark_exit["close_price"]), benchmark_entry_close)
        if stock_exit is None:
            block_reasons.add(f"missing_stock_exit_bar_{horizon}d")
        if benchmark_exit is None:
            block_reasons.add(f"missing_benchmark_exit_bar_{horizon}d")
        labels[f"forward_return_{horizon}d"] = stock_return
        labels[f"benchmark_return_{horizon}d"] = benchmark_return
        labels[f"excess_return_{horizon}d"] = (
            stock_return - benchmark_return if stock_return is not None and benchmark_return is not None else None
        )

    if _safe_float(current.get("volume")) <= 0:
        block_reasons.add("suspended_or_stale_entry")
    if _limit_state(current, stock_bars[stock_index - 1] if stock_index > 0 else None) == "limit_up_like":
        block_reasons.add("unbuyable_limit_up_entry")

    excess_10d = labels.get("excess_return_10d")
    net_excess_10d = excess_10d - 0.001 if excess_10d is not None else None
    labels["net_excess_return_10d_after_costs"] = net_excess_10d
    labels["top_quantile_label_10d"] = net_excess_10d is not None and net_excess_10d > 0
    label_status = "ready" if not block_reasons and labels.get("excess_return_10d") is not None else "blocked"
    row = {
        "row_id": f"label:{symbol}:{as_of_day.isoformat()}",
        "universe_row_id": universe_row_id,
        "symbol": symbol,
        "as_of_date": as_of_day.isoformat(),
        "label_version": MODEL_EXPLORATION_LABEL_VERSION,
        "source_input_snapshot_id": source_snapshot_id,
        "entry_price_source": "same_day_close_research_proxy",
        "exit_price_source": "future_close_research_proxy",
        "cost_assumption": {"round_trip_cost": 0.001, "stress_multiplier": 2.0},
        "tradability_status": "blocked" if block_reasons else "tradable_research_proxy",
        "label_block_reasons": sorted(block_reasons),
        "label_status": label_status,
        "labels": labels,
    }
    row["row_digest"] = _stable_digest(row)
    return row


def _bars_by_stock(session: Session) -> tuple[dict[str, Stock], dict[str, list[dict[str, Any]]]]:
    stocks = list(session.scalars(select(Stock).order_by(Stock.symbol.asc(), Stock.id.asc())).all())
    stocks_by_symbol = {stock.symbol: stock for stock in stocks}
    bars = list(
        session.scalars(select(MarketBar).where(MarketBar.timeframe == "1d").order_by(MarketBar.observed_at, MarketBar.id))
    )
    by_symbol: dict[str, list[dict[str, Any]]] = {symbol: [] for symbol in stocks_by_symbol}
    for bar in bars:
        stock = next((candidate for candidate in stocks if candidate.id == bar.stock_id), None)
        if stock is None:
            continue
        by_symbol.setdefault(stock.symbol, []).append(_bar_row(stock, bar))
    for rows in by_symbol.values():
        rows.sort(key=lambda row: (row["observed_date"], row["id"]))
    return stocks_by_symbol, by_symbol


def build_model_exploration_p1_artifacts(
    session: Session,
    *,
    validation_run_id: str,
    as_of_dates: list[date] | None = None,
    benchmark_symbol: str = DEFAULT_BENCHMARK_SYMBOL,
    horizons: tuple[int, ...] = DEFAULT_HORIZONS,
    min_history_days: int = 2,
    max_as_of_dates: int | None = None,
) -> dict[str, dict[str, Any]]:
    stocks_by_symbol, bars_by_symbol = _bars_by_stock(session)
    benchmark_bars = bars_by_symbol.get(benchmark_symbol, [])
    benchmark_by_day = {row["observed_date"]: index for index, row in enumerate(benchmark_bars)}
    eligible_symbols: list[str] = []
    stock_metadata: list[dict[str, Any]] = []
    for symbol, stock in sorted(stocks_by_symbol.items()):
        eligible, reasons = _account_eligibility(stock)
        if eligible and bars_by_symbol.get(symbol):
            eligible_symbols.append(symbol)
        stock_metadata.append(
            {
                "symbol": symbol,
                "stock_id": stock.id,
                "stock_name": stock.name,
                "board": _board(stock),
                "status": stock.status,
                "eligible_for_account_profile": eligible,
                "eligibility_reasons": reasons,
                "bar_count": len(bars_by_symbol.get(symbol, [])),
            }
        )

    candidate_days = set(as_of_dates or [])
    if not candidate_days:
        for symbol in eligible_symbols:
            rows = bars_by_symbol.get(symbol, [])
            for index, row in enumerate(rows):
                if index + 1 >= min_history_days:
                    candidate_days.add(row["observed_date"])
    ordered_days = sorted(candidate_days)
    if max_as_of_dates is not None:
        ordered_days = ordered_days[-max_as_of_dates:]

    source_digest = _stable_digest(
        {
            "validation_run_id": validation_run_id,
            "benchmark_symbol": benchmark_symbol,
            "eligible_symbols": eligible_symbols,
            "as_of_dates": [day.isoformat() for day in ordered_days],
            "horizons": horizons,
            "stock_metadata": stock_metadata,
        }
    )
    input_snapshot_id = f"model-exploration-input-snapshot-{source_digest[:16]}"
    universe_rows: list[dict[str, Any]] = []
    feature_rows: list[dict[str, Any]] = []
    label_rows: list[dict[str, Any]] = []

    for symbol in eligible_symbols:
        stock = stocks_by_symbol[symbol]
        rows = bars_by_symbol[symbol]
        index_by_day = {row["observed_date"]: index for index, row in enumerate(rows)}
        for as_of_day in ordered_days:
            stock_index = index_by_day.get(as_of_day)
            if stock_index is None or stock_index + 1 < min_history_days:
                continue
            current = rows[stock_index]
            previous = rows[stock_index - 1] if stock_index > 0 else None
            universe_row = {
                "row_id": f"universe:{symbol}:{as_of_day.isoformat()}",
                "symbol": symbol,
                "as_of_date": as_of_day.isoformat(),
                "stock_name": stock.name,
                "board": _board(stock),
                "industry_code": (stock.profile_payload or {}).get("industry_code"),
                "industry_name": (stock.profile_payload or {}).get("industry"),
                "eligible_for_account_profile": True,
                "account_profile": MODEL_EXPLORATION_ACCOUNT_PROFILE,
                "eligibility_reasons": [],
                "has_market_bar": True,
                "has_benchmark_bar": as_of_day in benchmark_by_day,
                "is_st": _is_st_stock(stock),
                "is_suspended_or_stale": _safe_float(current.get("volume")) <= 0,
                "limit_state": _limit_state(current, previous),
                "tradable_lot_size": 100,
                "source_lineage": {
                    "stock_id": stock.id,
                    "market_bar_id": current["id"],
                    "market_bar_key": current["bar_key"],
                    "market_bar_lineage_hash": current.get("lineage_hash"),
                },
            }
            universe_row["row_digest"] = _stable_digest(universe_row)
            universe_rows.append(universe_row)
            bars_until_as_of = rows[: stock_index + 1]
            benchmark_until_as_of = [
                row for row in benchmark_bars if row["observed_date"] <= as_of_day
            ]
            feature_rows.append(
                _features_for_bars(
                    symbol=symbol,
                    as_of_day=as_of_day,
                    bars_until_as_of=bars_until_as_of,
                    benchmark_until_as_of=benchmark_until_as_of,
                    universe_row_id=universe_row["row_id"],
                    source_snapshot_id=input_snapshot_id,
                )
            )
            label_rows.append(
                _label_for_row(
                    symbol=symbol,
                    as_of_day=as_of_day,
                    stock_bars=rows,
                    stock_index=stock_index,
                    benchmark_bars=benchmark_bars,
                    benchmark_by_day=benchmark_by_day,
                    horizons=horizons,
                    universe_row_id=universe_row["row_id"],
                    source_snapshot_id=input_snapshot_id,
                )
            )

    universe_digest = _stable_digest(universe_rows)
    feature_digest = _stable_digest(feature_rows)
    label_digest = _stable_digest(label_rows)
    universe_artifact_id = f"universe-date-matrix-{universe_digest[:16]}"
    feature_artifact_id = f"pit-feature-matrix-{feature_digest[:16]}"
    label_artifact_id = f"executable-label-matrix-{label_digest[:16]}"
    generated_at = datetime.now(UTC).isoformat()
    common = {
        "validation_run_id": validation_run_id,
        "generated_at": generated_at,
        "source_db_snapshot_id": source_digest[:16],
        "source_data_time_range": {
            "as_of_start": ordered_days[0].isoformat() if ordered_days else None,
            "as_of_end": ordered_days[-1].isoformat() if ordered_days else None,
        },
        "code_version": "unresolved_local_checkout",
        "config_version": MODEL_EXPLORATION_PROTOCOL_VERSION,
        "storage_boundary": "research_validation_artifact_store_only",
        "promotion_status": "blocked_from_production",
    }
    input_snapshot = {
        **common,
        "artifact_type": "model_exploration_input_snapshot",
        "schema_version": "model_exploration_input_snapshot.v1",
        "artifact_id": input_snapshot_id,
        "feature_version": MODEL_EXPLORATION_FEATURE_VERSION,
        "label_version": MODEL_EXPLORATION_LABEL_VERSION,
        "validation_protocol": {
            "protocol_version": MODEL_EXPLORATION_PROTOCOL_VERSION,
            "primary_row_source": "objective_universe_x_as_of_date",
            "forbidden_primary_sources": [
                "recommendation_rows",
                "active_watchlist",
                "factor_observation_rows",
                "recommendation_payload.factor_breakdown",
                "post_hoc_winner_identity",
            ],
            "benchmark_symbol": benchmark_symbol,
            "horizons": list(horizons),
        },
        "gate_readout": _matrix_gate_readout(len(eligible_symbols), len(ordered_days), len(universe_rows)),
        "claim_ceiling": "data_coverage_blocked"
        if len(eligible_symbols) < 200 or len(ordered_days) < 60 or len(universe_rows) < 12000
        else "model_research_input_only",
        "stock_metadata": stock_metadata,
        "eligible_symbol_count": len(eligible_symbols),
        "as_of_date_count": len(ordered_days),
        "universe_row_count": len(universe_rows),
        "benchmark_symbol": benchmark_symbol,
        "artifact_refs": {
            "universe_date_matrix": universe_artifact_id,
            "pit_feature_matrix": feature_artifact_id,
            "executable_label_matrix": label_artifact_id,
        },
    }
    universe_matrix = {
        **common,
        "artifact_type": "universe_date_matrix",
        "schema_version": "universe_date_matrix.v1",
        "artifact_id": universe_artifact_id,
        "feature_version": "not_applicable_universe_matrix",
        "label_version": "not_applicable_universe_matrix",
        "source_input_snapshot_id": input_snapshot_id,
        "validation_protocol": input_snapshot["validation_protocol"],
        "gate_readout": _matrix_gate_readout(len(eligible_symbols), len(ordered_days), len(universe_rows)),
        "claim_ceiling": input_snapshot["claim_ceiling"],
        "row_count": len(universe_rows),
        "row_content_digest": universe_digest,
        "rows": universe_rows,
    }
    feature_matrix = {
        **common,
        "artifact_type": "pit_feature_matrix",
        "schema_version": "pit_feature_matrix.v1",
        "artifact_id": feature_artifact_id,
        "feature_version": MODEL_EXPLORATION_FEATURE_VERSION,
        "label_version": "not_applicable_feature_matrix",
        "source_input_snapshot_id": input_snapshot_id,
        "source_universe_date_matrix_id": universe_artifact_id,
        "validation_protocol": input_snapshot["validation_protocol"],
        "gate_readout": _feature_gate_readout(feature_rows),
        "claim_ceiling": "feature_matrix_only",
        "row_count": len(feature_rows),
        "row_content_digest": feature_digest,
        "feature_groups": [
            "price_momentum",
            "reversal_overheat",
            "volatility_risk",
            "liquidity",
            "execution",
            "regime",
            "crowding",
        ],
        "rows": feature_rows,
    }
    label_matrix = {
        **common,
        "artifact_type": "executable_label_matrix",
        "schema_version": "executable_label_matrix.v1",
        "artifact_id": label_artifact_id,
        "feature_version": "not_applicable_label_matrix",
        "label_version": MODEL_EXPLORATION_LABEL_VERSION,
        "source_input_snapshot_id": input_snapshot_id,
        "source_universe_date_matrix_id": universe_artifact_id,
        "validation_protocol": input_snapshot["validation_protocol"],
        "gate_readout": _label_gate_readout(label_rows),
        "claim_ceiling": "label_matrix_only",
        "row_count": len(label_rows),
        "row_content_digest": label_digest,
        "rows": label_rows,
    }
    return {
        "model_exploration_input_snapshot": input_snapshot,
        "universe_date_matrix": universe_matrix,
        "pit_feature_matrix": feature_matrix,
        "executable_label_matrix": label_matrix,
    }


def _matrix_gate_readout(unique_symbols: int, as_of_dates: int, total_rows: int) -> dict[str, Any]:
    blockers: list[str] = []
    if unique_symbols < 200:
        blockers.append("insufficient_unique_symbols_for_model_claims")
    if as_of_dates < 60:
        blockers.append("insufficient_as_of_dates_for_model_claims")
    if total_rows < 12000:
        blockers.append("insufficient_universe_date_rows_for_model_claims")
    return {
        "gate_status": "blocked" if blockers else "research_input_ready",
        "promotion_status": "blocked_from_production",
        "claim_ceiling": "data_coverage_blocked" if blockers else "model_research_input_only",
        "blocking_gate_ids": blockers,
        "thresholds": {
            "minimum_unique_symbols_for_claims": 200,
            "minimum_as_of_dates_for_claims": 60,
            "minimum_total_rows_for_claims": 12000,
        },
    }


def _feature_gate_readout(rows: list[dict[str, Any]]) -> dict[str, Any]:
    blockers = [] if rows else ["missing_feature_rows"]
    return {
        "gate_status": "blocked" if blockers else "feature_matrix_ready",
        "promotion_status": "blocked_from_production",
        "claim_ceiling": "feature_matrix_only",
        "blocking_gate_ids": blockers,
    }


def _label_gate_readout(rows: list[dict[str, Any]]) -> dict[str, Any]:
    ready_rows = sum(1 for row in rows if row.get("label_status") == "ready")
    blockers: list[str] = []
    if not rows:
        blockers.append("missing_label_rows")
    if ready_rows < len(rows):
        blockers.append("blocked_or_partial_label_rows")
    return {
        "gate_status": "blocked" if blockers else "label_matrix_ready",
        "promotion_status": "blocked_from_production",
        "claim_ceiling": "label_matrix_only",
        "blocking_gate_ids": blockers,
        "ready_row_count": ready_rows,
        "row_count": len(rows),
    }


def write_model_exploration_p1_artifacts(
    artifacts: dict[str, dict[str, Any]],
    *,
    artifact_root: str | Path | None = None,
) -> dict[str, Path]:
    root = Path(artifact_root) if artifact_root else None
    written: dict[str, Path] = {}
    for artifact_type, payload in artifacts.items():
        written[artifact_type] = write_research_validation_artifact(
            artifact_type,
            str(payload["artifact_id"]),
            payload,
            root=root,
        )
    return written

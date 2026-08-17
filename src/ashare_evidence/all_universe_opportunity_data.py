from __future__ import annotations

import gzip
import json
import sqlite3
from collections import defaultdict
from pathlib import Path
from statistics import mean, pstdev
from typing import Any

from ashare_evidence.external_inventory_rerank import _z_scores
from ashare_evidence.rolling_account_execution_snapshot import stable_digest

SCHEMA_VERSION = "all_universe_opportunity_dataset.v1"
BUY_COST_BPS = 20.0
SELL_COST_BPS = 25.0


def invariant_main_board_symbol(symbol: str) -> bool:
    ticker, separator, exchange = symbol.partition(".")
    if not separator:
        return False
    if exchange == "SH":
        return ticker.startswith(("600", "601", "603", "605"))
    if exchange == "SZ":
        return ticker.startswith(("000", "001", "002", "003"))
    return False


def _load_single_database(
    database_path: Path, *, end: str
) -> tuple[dict[str, dict[str, dict[str, Any]]], dict[str, str], set[str]]:
    connection = sqlite3.connect(f"file:{database_path}?immutable=1", uri=True)
    rows = connection.execute(
        """
        SELECT s.symbol, s.name, substr(m.observed_at, 1, 10),
               m.close_price, m.amount, m.turnover_rate
        FROM market_bars m JOIN stocks s ON s.id = m.stock_id
        WHERE m.timeframe = '1d' AND substr(m.observed_at, 1, 10) <= ?
        ORDER BY s.symbol, m.observed_at
        """,
        (end,),
    ).fetchall()
    benchmark_days = {
        str(row[0])
        for row in connection.execute(
            """
            SELECT substr(m.observed_at, 1, 10)
            FROM market_bars m JOIN stocks s ON s.id = m.stock_id
            WHERE m.timeframe = '1d' AND s.symbol = '000300.SH'
              AND substr(m.observed_at, 1, 10) <= ?
            ORDER BY m.observed_at
            """,
            (end,),
        ).fetchall()
    }
    connection.close()
    bars: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    names: dict[str, str] = {}
    for symbol, name, day, close, amount, turnover in rows:
        symbol = str(symbol)
        if not invariant_main_board_symbol(symbol):
            continue
        names[symbol] = str(name or symbol)
        bars[symbol][str(day)] = {
            "day": str(day),
            "close": float(close),
            "amount": float(amount or 0.0),
            "turnover": float(turnover or 0.0),
        }
    if not benchmark_days:
        raise ValueError("CSI300 trading calendar missing from hot database")
    return dict(bars), names, benchmark_days


def _load_bars(
    historical_database: Path, hot_database: Path, *, end: str
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, str], list[str]]:
    historical, historical_names, historical_days = _load_single_database(historical_database, end=end)
    hot, hot_names, hot_days = _load_single_database(hot_database, end=end)
    merged: dict[str, dict[str, dict[str, Any]]] = {symbol: dict(rows) for symbol, rows in historical.items()}
    for symbol, rows in hot.items():
        merged.setdefault(symbol, {}).update(rows)
    bars = {symbol: [rows[day] for day in sorted(rows)] for symbol, rows in merged.items()}
    return bars, {**historical_names, **hot_names}, sorted(historical_days | hot_days)


def _load_v3_quality(execution_snapshot_path: Path, recent_snapshot_path: Path) -> dict[tuple[str, str], float]:
    with gzip.open(execution_snapshot_path, "rt", encoding="utf-8") as handle:
        historical = json.load(handle)
    quality: dict[tuple[str, str], float] = {}
    for row in historical["inputs"]["candidate_inventory_rows"]:
        rank = min(20, max(1, int(float(row["rank"]))))
        quality[(str(row["as_of_date"]), str(row["symbol"]))] = 1.0 - (rank - 1) / 19.0
    with gzip.open(recent_snapshot_path, "rt", encoding="utf-8") as handle:
        recent = json.load(handle)
    if recent["artifact_id"] != "recent-hotspot-pit-76f7e40234875927":
        raise ValueError("unexpected recent PIT snapshot")
    for row in recent["rows"]:
        rank = row.get("v3_top20_rank")
        if rank is not None:
            quality[(str(row["signal_day"]), str(row["symbol"]))] = 1.0 - (int(rank) - 1) / 19.0
    return quality


def _load_recent_eligibility(recent_snapshot_path: Path) -> dict[tuple[str, str], bool]:
    with gzip.open(recent_snapshot_path, "rt", encoding="utf-8") as handle:
        recent = json.load(handle)
    return {
        (str(row["signal_day"]), str(row["symbol"])): bool(row["personally_eligible"])
        for row in recent["rows"]
    }


def _maximum_drawdown(values: list[float]) -> float:
    peak = values[0]
    drawdown = 0.0
    for value in values:
        peak = max(peak, value)
        drawdown = min(drawdown, value / peak - 1.0)
    return drawdown


def _raw_features(rows: list[dict[str, Any]], *, index: int) -> dict[str, float] | None:
    if index < 60:
        return None
    closes = [float(row["close"]) for row in rows[index - 60 : index + 1]]
    if min(closes) <= 0.0:
        return None
    amounts = [float(row["amount"]) for row in rows[index - 19 : index + 1]]
    turnovers = [float(row["turnover"]) for row in rows[index - 19 : index + 1]]
    daily_returns = [closes[position] / closes[position - 1] - 1.0 for position in range(41, 61)]
    amount20 = mean(amounts)
    turnover20 = mean(turnovers)
    return_3d = closes[-1] / closes[-4] - 1.0
    return_5d = closes[-1] / closes[-6] - 1.0
    return {
        "signal_close": closes[-1],
        "return_1d": closes[-1] / closes[-2] - 1.0,
        "return_3d": return_3d,
        "return_5d": return_5d,
        "return_10d": closes[-1] / closes[-11] - 1.0,
        "return_20d": closes[-1] / closes[-21] - 1.0,
        "return_3d_minus_return_5d": return_3d - return_5d,
        "distance_from_20d_high": closes[-1] / max(closes[-20:]) - 1.0,
        "maximum_drawdown_20d": _maximum_drawdown(closes[-20:]),
        "volatility_20d": pstdev(daily_returns),
        "close_vs_sma5": closes[-1] / mean(closes[-5:]) - 1.0,
        "close_vs_sma10": closes[-1] / mean(closes[-10:]) - 1.0,
        "amount_1d_vs_20d": amounts[-1] / max(amount20, 1.0) - 1.0,
        "amount_5d_vs_20d": mean(amounts[-5:]) / max(amount20, 1.0) - 1.0,
        "turnover_1d_vs_20d": turnovers[-1] / max(turnover20, 0.000001) - 1.0,
        "turnover_5d_vs_20d": mean(turnovers[-5:]) / max(turnover20, 0.000001) - 1.0,
        "turnover_rate": turnovers[-1],
    }


def _percentile(rows: list[dict[str, Any]], key: str) -> dict[str, float]:
    ordered = sorted(rows, key=lambda row: (float(row[key]), str(row["symbol"])))
    denominator = max(1, len(ordered) - 1)
    return {str(row["symbol"]): index / denominator for index, row in enumerate(ordered)}


def _attach_label(
    row: dict[str, Any],
    *,
    bars: dict[str, list[dict[str, Any]]],
    indices: dict[str, dict[str, int]],
    trading_days: list[str],
    trading_day_indices: dict[str, int],
) -> dict[str, Any]:
    output = dict(row)
    output.update(
        {
            "entry_date": None,
            "exit_date": None,
            "entry_status": "pending_forward_window",
            "label_available_day": None,
            "net_return_5d": None,
            "maximum_adverse_return_5d": None,
            "downside_label": None,
        }
    )
    day_position = trading_day_indices.get(str(row["signal_day"]))
    if day_position is None or day_position + 6 >= len(trading_days):
        return output
    entry_day = trading_days[day_position + 1]
    exit_day = trading_days[day_position + 6]
    symbol = str(row["symbol"])
    symbol_indices = indices[symbol]
    if entry_day not in symbol_indices or exit_day not in symbol_indices:
        output["entry_status"] = "blocked_missing_common_trading_day_bar"
        return output
    entry_index = symbol_indices[entry_day]
    exit_index = symbol_indices[exit_day]
    symbol_bars = bars[symbol]
    entry = float(symbol_bars[entry_index]["close"])
    output["entry_date"] = entry_day
    output["exit_date"] = exit_day
    if entry / float(row["signal_close"]) - 1.0 >= 0.095:
        output["entry_status"] = "blocked_limit_up_like"
        return output
    if entry > 200.0:
        output["entry_status"] = "blocked_entry_price_above_200"
        return output
    path_indices = [symbol_indices.get(day) for day in trading_days[day_position + 1 : day_position + 7]]
    if any(index is None for index in path_indices):
        output["entry_status"] = "blocked_incomplete_common_day_path"
        return output
    exit_price = float(symbol_bars[exit_index]["close"])
    net_return = exit_price * (1.0 - SELL_COST_BPS / 10000.0) / (
        entry * (1.0 + BUY_COST_BPS / 10000.0)
    ) - 1.0
    adverse = min(float(symbol_bars[index]["close"]) / entry - 1.0 for index in path_indices if index is not None)
    output.update(
        {
            "entry_status": "tradable_research_proxy",
            "label_available_day": exit_day,
            "net_return_5d": net_return,
            "maximum_adverse_return_5d": adverse,
            "downside_label": int(adverse <= -0.05),
        }
    )
    return output


def _prefilter(rows: list[dict[str, Any]], *, top_k: int) -> list[dict[str, Any]]:
    if not rows:
        return []
    components = {
        "return_1d": _z_scores([float(row["return_1d"]) for row in rows]),
        "acceleration": _z_scores([float(row["return_3d_minus_return_5d"]) for row in rows]),
        "recovery_space": _z_scores([-float(row["distance_from_20d_high"]) for row in rows]),
        "amount": _z_scores([float(row["amount_1d_vs_20d"]) for row in rows]),
        "turnover": _z_scores([float(row["turnover_1d_vs_20d"]) for row in rows]),
    }
    for index, row in enumerate(rows):
        row["prefilter_score"] = (
            0.30 * components["return_1d"][index]
            + 0.25 * components["acceleration"][index]
            + 0.15 * components["recovery_space"][index]
            + 0.10 * components["amount"][index]
            + 0.10 * components["turnover"][index]
            + 0.10 * float(row["v3_soft_quality"])
        )
    return sorted(rows, key=lambda row: (-float(row["prefilter_score"]), str(row["symbol"])))[:top_k]


def build_all_universe_opportunity_dataset(
    *,
    historical_database: Path,
    hot_database: Path,
    execution_snapshot_path: Path,
    recent_snapshot_path: Path,
    design: dict[str, Any],
    data_source_amendment: dict[str, Any],
) -> dict[str, Any]:
    if data_source_amendment.get("status") != "frozen_data_source_correction_before_corrected_broad_evaluation":
        raise ValueError("all-universe data source amendment is not frozen")
    end = str(design["data_contract"]["recent_diagnostic_to"])
    bars, names, trading_days = _load_bars(historical_database, hot_database, end=end)
    indices = {symbol: {row["day"]: index for index, row in enumerate(rows)} for symbol, rows in bars.items()}
    v3_quality = _load_v3_quality(execution_snapshot_path, recent_snapshot_path)
    recent_eligibility = _load_recent_eligibility(recent_snapshot_path)
    trading_day_indices = {day: index for index, day in enumerate(trading_days)}
    recent_from = str(design["data_contract"]["recent_diagnostic_from"])
    minimum_price = float(design["outer_eligibility"]["minimum_signal_day_unadjusted_price_cny"])
    maximum_price = float(design["outer_eligibility"]["maximum_signal_day_unadjusted_price_cny"])
    rule = design["opportunity_rule"]
    candidates: list[dict[str, Any]] = []
    daily_audits: list[dict[str, Any]] = []
    symbols = sorted(bars)
    for day in trading_days:
        if day < "2023-02-20":
            continue
        eligible: list[dict[str, Any]] = []
        for symbol in symbols:
            index = indices[symbol].get(day)
            if index is None:
                continue
            features = _raw_features(bars[symbol], index=index)
            if features is None or not minimum_price <= features["signal_close"] <= maximum_price:
                continue
            if day >= recent_from and not recent_eligibility.get((day, symbol), False):
                continue
            eligible.append(
                {
                    "signal_day": day,
                    "symbol": symbol,
                    "stock_name": names[symbol],
                    "historical_st_status": "point_in_time_unknown" if day < recent_from else "recent_snapshot_eligible",
                    "v3_soft_quality": v3_quality.get((day, symbol), 0.0),
                    **features,
                }
            )
        if not eligible:
            continue
        percentile_fields = {
            "return_20d_percentile": _percentile(eligible, "return_20d"),
            "amount_1d_vs_20d_percentile": _percentile(eligible, "amount_1d_vs_20d"),
            "turnover_rate_percentile": _percentile(eligible, "turnover_rate"),
            "volatility_20d_percentile": _percentile(eligible, "volatility_20d"),
        }
        qualified: list[dict[str, Any]] = []
        for row in eligible:
            symbol = str(row["symbol"])
            row.update({key: values[symbol] for key, values in percentile_fields.items()})
            if (
                row["return_1d"] >= float(rule["minimum_return_1d"])
                and row["maximum_drawdown_20d"] <= float(rule["maximum_drawdown_20d"])
                and row["return_3d_minus_return_5d"] >= float(rule["minimum_return_3d_minus_return_5d"])
            ):
                qualified.append(row)
        selected = _prefilter(qualified, top_k=int(rule["prefilter_top_k"]))
        candidates.extend(
            _attach_label(
                row,
                bars=bars,
                indices=indices,
                trading_days=trading_days,
                trading_day_indices=trading_day_indices,
            )
            for row in selected
        )
        daily_audits.append(
            {
                "signal_day": day,
                "outer_eligible_count": len(eligible),
                "rule_qualified_count": len(qualified),
                "prefilter_count": len(selected),
            }
        )
    material = {
        "artifact_type": "all_universe_opportunity_dataset",
        "schema_version": SCHEMA_VERSION,
        "status": "ready_historical_st_lineage_unknown",
        "claim_ceiling": "offline_mechanism_research_not_account_eligible_historical_replay",
        "source_historical_database_name": historical_database.name,
        "source_recent_database_name": hot_database.name,
        "source_recent_snapshot_id": design["data_contract"]["recent_snapshot_id"],
        "source_execution_snapshot_id": design["data_contract"]["historical_v3_snapshot_id"],
        "source_data_amendment_digest": stable_digest(data_source_amendment),
        "observed_from": daily_audits[0]["signal_day"],
        "observed_to": daily_audits[-1]["signal_day"],
        "candidate_row_count": len(candidates),
        "signal_day_count": len(daily_audits),
        "historical_st_status_point_in_time": False,
        "future_static_status_backfill_used": False,
        "network_access_during_build": False,
        "daily_audits": daily_audits,
        "rows": candidates,
    }
    digest = stable_digest(material)
    return {"artifact_id": f"all-universe-opportunity-dataset-{digest[:16]}", **material, "content_digest": digest}


def write_gzip_dataset(path: Path, payload: dict[str, Any]) -> None:
    material = {key: value for key, value in payload.items() if key not in {"artifact_id", "content_digest"}}
    if stable_digest(material) != payload.get("content_digest"):
        raise ValueError("all-universe opportunity dataset digest mismatch")
    rendered = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        with gzip.open(path, "rb") as handle:
            if handle.read() != rendered:
                raise ValueError(f"immutable dataset already exists: {path}")
        return
    with path.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as compressed:
            compressed.write(rendered)


def load_gzip_dataset(path: Path) -> dict[str, Any]:
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        payload = json.load(handle)
    material = {key: value for key, value in payload.items() if key not in {"artifact_id", "content_digest"}}
    if stable_digest(material) != payload.get("content_digest"):
        raise ValueError("all-universe opportunity dataset digest mismatch")
    return payload

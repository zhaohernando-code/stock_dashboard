from __future__ import annotations

import gzip
import json
import sqlite3
from collections import defaultdict
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from ashare_evidence.model_candidate_runner import _fit_model, _grid_trials, _stable_digest, _top_k_picks_by_date
from ashare_evidence.model_exploration_snapshot import build_model_exploration_p1_artifacts
from ashare_evidence.model_spec_registry import build_model_spec_registry_artifact
from ashare_evidence.models import MarketBar, Stock
from ashare_evidence.rolling_account_execution_snapshot import stable_digest
from ashare_evidence.shortpick_strategy_lab_v3_projection import (
    FORWARD_REPLACEMENT_INVENTORY_TOP_K,
    V3_MODEL_SPEC_ID,
    _model_spec_by_id,
    _projection_prediction,
    _signal_block_reasons,
)

SCHEMA_VERSION = "recent_hotspot_pit_snapshot.v1"
DIAGNOSTIC_SCHEMA_VERSION = "recent_hotspot_miss_attribution.v1"
BUY_COST_BPS = 20.0
SELL_COST_BPS = 25.0


def _read_design(path: Path) -> dict[str, Any]:
    design = json.loads(path.read_text(encoding="utf-8"))
    expected = "frozen_after_named_case_schema_preflight_before_broad_outcome_evaluation"
    if design.get("status") != expected:
        raise ValueError("recent hotspot diagnostic design is not frozen")
    return design


def _trading_days(session: Session, *, start: date, end: date, benchmark_symbol: str = "000300.SH") -> list[date]:
    stock = session.scalar(select(Stock).where(Stock.symbol == benchmark_symbol).limit(1))
    if stock is None:
        raise ValueError(f"benchmark stock missing: {benchmark_symbol}")
    values = session.scalars(
        select(MarketBar.observed_at)
        .where(
            MarketBar.stock_id == stock.id,
            MarketBar.timeframe == "1d",
            MarketBar.observed_at >= datetime.combine(start, datetime.min.time(), tzinfo=UTC),
            MarketBar.observed_at <= datetime.combine(end, datetime.max.time(), tzinfo=UTC),
        )
        .order_by(MarketBar.observed_at, MarketBar.id)
    )
    return sorted({value.date() for value in values})


def _signal_bars(database_path: Path, *, start: str, end: str) -> dict[tuple[str, str], dict[str, float | None]]:
    connection = sqlite3.connect(f"file:{database_path}?immutable=1", uri=True)
    rows = connection.execute(
        """
        SELECT s.symbol, substr(m.observed_at, 1, 10), m.close_price, m.amount, m.turnover_rate
        FROM market_bars m JOIN stocks s ON s.id = m.stock_id
        WHERE m.timeframe = '1d'
          AND substr(m.observed_at, 1, 10) >= ?
          AND substr(m.observed_at, 1, 10) <= ?
        ORDER BY m.observed_at, s.symbol
        """,
        (start, end),
    ).fetchall()
    connection.close()
    return {
        (str(symbol), str(day)): {
            "close": float(close),
            "amount": None if amount is None else float(amount),
            "turnover_rate": None if turnover is None else float(turnover),
        }
        for symbol, day, close, amount, turnover in rows
    }


def flatten_recovery_features(row: dict[str, Any]) -> dict[str, float]:
    values = row.get("feature_values") or {}
    momentum = values.get("price_momentum") or {}
    reversal = values.get("reversal_overheat") or {}
    risk = values.get("volatility_risk") or {}
    liquidity = values.get("liquidity") or {}
    crowding = values.get("crowding") or {}
    cross = values.get("cross_sectional") or {}
    avg_amount_10d = float(liquidity.get("avg_amount_10d") or 0.0)
    avg_amount_20d = float(liquidity.get("avg_amount_20d") or 0.0)
    amount_1d_vs_20d = float(crowding.get("amount_vs_20d_avg") or 0.0) - 1.0
    return {
        "return_3d": float(momentum.get("return_3d") or 0.0),
        "return_5d": float(momentum.get("return_5d") or 0.0),
        "return_10d": float(momentum.get("return_10d") or 0.0),
        "return_20d": float(momentum.get("return_20d") or 0.0),
        "return_40d": float(momentum.get("return_40d") or 0.0),
        "return_1d": float(reversal.get("return_1d") or 0.0),
        "distance_from_20d_high": float(reversal.get("distance_from_20d_high") or 0.0),
        "maximum_drawdown_20d": float(risk.get("max_drawdown_20d") or 0.0),
        "volatility_20d": float(risk.get("volatility_20d") or 0.0),
        "turnover_rate": float(liquidity.get("turnover_rate") or 0.0),
        "amount_1d_vs_20d": amount_1d_vs_20d,
        "amount_5d_vs_20d": float(cross.get("amount_10d_vs_20d") or 0.0),
        "return_5d_percentile": float(cross.get("return_5d_percentile") or 0.0),
        "return_20d_percentile": float(cross.get("return_20d_percentile") or 0.0),
        "turnover_rate_percentile": float(cross.get("turnover_rate_percentile") or 0.0),
        "amount_vs_20d_avg_percentile": float(cross.get("amount_vs_20d_avg_percentile") or 0.0),
        "industry_return_5d_excess": float(cross.get("industry_return_5d_excess") or 0.0),
        "industry_return_20d_excess": float(cross.get("industry_return_20d_excess") or 0.0),
        "benchmark_return_20d": float((values.get("regime") or {}).get("benchmark_return_20d") or 0.0),
        "amount_10d_vs_20d_raw": avg_amount_10d / max(avg_amount_20d, 1.0) - 1.0,
    }


def _daily_v3_projection(
    feature_rows: list[dict[str, Any]], *, registry: dict[str, Any], signal_day: str
) -> dict[str, Any]:
    spec = _model_spec_by_id(registry, V3_MODEL_SPEC_ID)
    params = _grid_trials(spec.get("hyperparameter_grid") or {})[0]
    policy = spec.get("selection_policy") or {}
    horizon = int(spec.get("prediction_horizon_days") or 20)
    top_k = max(1, int(float(policy.get("top_k") or 3)))
    fitted = _fit_model([], model_spec=spec, params=params)
    fitted_digest = _stable_digest({"model_spec_id": V3_MODEL_SPEC_ID, "signal_date": signal_day, "fitted_model": fitted})
    predictions = [
        _projection_prediction(
            feature_row=row,
            spec=spec,
            params=params,
            selection_policy=policy,
            trial_id=f"{V3_MODEL_SPEC_ID}:trial-000",
            fitted_model=fitted,
            fitted_model_digest=fitted_digest,
            horizon_days=horizon,
        )
        for row in feature_rows
    ]
    selected = _top_k_picks_by_date(predictions, top_k=top_k, selection_policy=policy, params=params)
    inventory = _top_k_picks_by_date(
        predictions,
        top_k=FORWARD_REPLACEMENT_INVENTORY_TOP_K,
        selection_policy=policy,
        params=params,
    )
    block_reasons = _signal_block_reasons(predictions, selection_policy=policy, params=params)
    allowed = sorted(
        (row for row in predictions if row.get("selection_allowed", True)),
        key=lambda row: (-float(row["score"]), str(row["symbol"])),
    )
    raw_rank = {str(row["symbol"]): index + 1 for index, row in enumerate(allowed)}
    return {
        "predictions": predictions,
        "selected": selected,
        "inventory": inventory,
        "block_reasons": block_reasons,
        "raw_rank": raw_rank,
    }


def _archive_validation(projected: dict[str, Any], *, path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"status": "archive_missing", "passed": None, "path": str(path)}
    archived = json.loads(path.read_text(encoding="utf-8"))
    trial = next(row for row in archived["trial_diagnostics"] if row["model_spec_id"] == V3_MODEL_SPEC_ID)

    def identity(rows: list[dict[str, Any]]) -> list[tuple[str, int]]:
        return [(str(row["symbol"]), int(float(row["rank"]))) for row in rows]

    observed_selected = identity(projected["selected"])
    expected_selected = identity(trial.get("selected_top_k_picks_by_date") or [])
    observed_inventory = identity(projected["inventory"])
    expected_inventory = identity(trial.get("ranked_candidate_inventory_by_date") or [])
    observed_blocks = sorted(str(value) for value in projected["block_reasons"])
    expected_blocks = sorted(str(value) for value in trial.get("signal_block_reasons") or [])
    passed = (
        observed_selected == expected_selected
        and observed_inventory == expected_inventory
        and observed_blocks == expected_blocks
    )
    return {
        "status": "passed" if passed else "failed",
        "passed": passed,
        "path": str(path),
        "selected_match": observed_selected == expected_selected,
        "inventory_match": observed_inventory == expected_inventory,
        "block_reason_match": observed_blocks == expected_blocks,
        "expected_selected": expected_selected,
        "observed_selected": observed_selected,
    }


def build_recent_hotspot_pit_snapshot(
    *,
    hot_database: Path,
    daily_source_directory: Path,
    design_path: Path,
) -> dict[str, Any]:
    design = _read_design(design_path)
    start = date.fromisoformat(design["data_contract"]["recent_requested_from"])
    end = date.fromisoformat(design["data_contract"]["recent_to"])
    engine = create_engine(f"sqlite:///file:{hot_database}?mode=ro&uri=true")
    with Session(engine) as session:
        trading_days = _trading_days(session, start=start, end=end)
        artifacts = build_model_exploration_p1_artifacts(
            session,
            validation_run_id="hotspot-recovery-recent-pit-20260817",
            as_of_dates=trading_days,
            horizons=(5, 10),
            entry_price_source="next_close",
        )
    engine.dispose()
    feature_matrix = artifacts["pit_feature_matrix"]
    label_by_key = {
        (str(row["symbol"]), str(row["as_of_date"])): row
        for row in artifacts["executable_label_matrix"]["rows"]
    }
    bars = _signal_bars(hot_database, start=trading_days[0].isoformat(), end=trading_days[-1].isoformat())
    registry = build_model_spec_registry_artifact(
        validation_run_id="hotspot-recovery-recent-pit-20260817",
        source_input_snapshot_id=str(feature_matrix["source_input_snapshot_id"]),
    )
    by_day: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in feature_matrix["rows"]:
        by_day[str(row["as_of_date"])].append(row)
    compact_rows: list[dict[str, Any]] = []
    daily_audits: list[dict[str, Any]] = []
    price_excluded = 0
    for day in sorted(by_day):
        projection = _daily_v3_projection(by_day[day], registry=registry, signal_day=day)
        selected_rank = {str(row["symbol"]): int(float(row["rank"])) for row in projection["selected"]}
        inventory_rank = {str(row["symbol"]): int(float(row["rank"])) for row in projection["inventory"]}
        validation = _archive_validation(projection, path=daily_source_directory / f"{day}.json")
        if validation["passed"] is False:
            raise ValueError(f"recent PIT V3 projection differs from archived source for {day}: {validation}")
        daily_audits.append(
            {
                "signal_day": day,
                "signal_block_reasons": projection["block_reasons"],
                "selected_count": len(projection["selected"]),
                "inventory_count": len(projection["inventory"]),
                "archive_validation": validation,
            }
        )
        for row in by_day[day]:
            symbol = str(row["symbol"])
            bar = bars.get((symbol, day)) or {}
            close = float(bar.get("close") or 0.0)
            personally_eligible = 0.0 < close <= 200.0
            price_excluded += int(not personally_eligible)
            label = label_by_key[(symbol, day)]
            compact_rows.append(
                {
                    "signal_day": day,
                    "symbol": symbol,
                    "stock_name": row.get("stock_name") or symbol,
                    "industry_name": row.get("industry_name"),
                    "board": row.get("board"),
                    "signal_close": close,
                    "personally_eligible": personally_eligible,
                    "personal_exclusion_reasons": [] if personally_eligible else ["price_above_200_or_invalid"],
                    "v3_raw_rank": projection["raw_rank"].get(symbol),
                    "v3_top20_rank": inventory_rank.get(symbol),
                    "v3_top3_rank": selected_rank.get(symbol),
                    "v3_market_cash_switch": bool(projection["block_reasons"]),
                    "v3_signal_block_reasons": projection["block_reasons"],
                    "entry_date": label.get("entry_date"),
                    "entry_status": (label.get("entry_execution") or {}).get("status"),
                    "entry_block_reasons": (label.get("entry_execution") or {}).get("block_reasons") or [],
                    "exit_date_5d": (label.get("exit_dates_by_horizon") or {}).get("5"),
                    "exit_date_10d": (label.get("exit_dates_by_horizon") or {}).get("10"),
                    "forward_return_5d": (label.get("labels") or {}).get("forward_return_5d"),
                    "excess_return_5d": (label.get("labels") or {}).get("excess_return_5d"),
                    "forward_return_10d": (label.get("labels") or {}).get("forward_return_10d"),
                    "excess_return_10d": (label.get("labels") or {}).get("excess_return_10d"),
                    "features": flatten_recovery_features(row),
                    "source_feature_row_digest": row.get("row_digest"),
                    "source_label_row_digest": label.get("row_digest"),
                }
            )
    material = {
        "artifact_type": "recent_hotspot_pit_snapshot",
        "schema_version": SCHEMA_VERSION,
        "status": "ready_retrospective_diagnostic_only",
        "claim_ceiling": "outcome_aware_recent_mechanism_diagnostic_not_independent_validation",
        "source_design_digest": stable_digest(design),
        "source_database_name": hot_database.name,
        "source_input_snapshot_id": artifacts["model_exploration_input_snapshot"]["artifact_id"],
        "source_feature_matrix_id": feature_matrix["artifact_id"],
        "source_label_matrix_id": artifacts["executable_label_matrix"]["artifact_id"],
        "requested_from": start.isoformat(),
        "observed_from": trading_days[0].isoformat(),
        "observed_to": trading_days[-1].isoformat(),
        "trading_day_count": len(trading_days),
        "row_count": len(compact_rows),
        "price_excluded_row_count": price_excluded,
        "daily_audits": daily_audits,
        "rows": compact_rows,
        "network_access_during_build": False,
        "v3_signal_changed": False,
        "paper_tracking_changed": False,
    }
    digest = stable_digest(material)
    return {"artifact_id": f"recent-hotspot-pit-{digest[:16]}", **material, "content_digest": digest}


def _percentile_map(rows: list[dict[str, Any]], key: str) -> dict[str, float]:
    ordered = sorted(rows, key=lambda row: (float(row[key]), str(row["symbol"])))
    denominator = max(1, len(ordered) - 1)
    return {str(row["symbol"]): index / denominator for index, row in enumerate(ordered)}


def miss_stage(row: dict[str, Any]) -> str:
    if not row.get("personally_eligible"):
        return "not_personally_eligible"
    if row.get("v3_market_cash_switch"):
        return "v3_market_cash_switch"
    if row.get("v3_top3_rank") is not None:
        if row.get("entry_status") == "tradable_research_proxy":
            return "captured_executable_v3_top3"
        return "v3_top3_execution_or_position_block"
    if row.get("v3_top20_rank") is not None:
        return "v3_top20_but_below_top3"
    return "outside_v3_top20"


def analyze_recent_hotspot_misses(snapshot: dict[str, Any], *, design: dict[str, Any]) -> dict[str, Any]:
    rows_by_day: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in snapshot["rows"]:
        if (
            row.get("personally_eligible")
            and row.get("entry_status") == "tradable_research_proxy"
            and row.get("forward_return_5d") is not None
            and row.get("excess_return_5d") is not None
        ):
            enriched = dict(row)
            enriched["net_return_5d"] = float(row["forward_return_5d"]) - (BUY_COST_BPS + SELL_COST_BPS) / 10000.0
            enriched["net_excess_return_5d"] = float(row["excess_return_5d"]) - (
                BUY_COST_BPS + SELL_COST_BPS
            ) / 10000.0
            rows_by_day[str(row["signal_day"])].append(enriched)
    winners: list[dict[str, Any]] = []
    for day in sorted(rows_by_day):
        current = rows_by_day[day]
        percentiles = _percentile_map(current, "net_excess_return_5d")
        for row in current:
            percentile = percentiles[str(row["symbol"])]
            broad = percentile >= 0.90
            strong = broad and row["net_return_5d"] >= 0.03 and row["net_excess_return_5d"] >= 0.02
            if broad:
                winners.append(
                    {
                        "signal_day": day,
                        "symbol": row["symbol"],
                        "stock_name": row["stock_name"],
                        "industry_name": row.get("industry_name"),
                        "net_return_5d": row["net_return_5d"],
                        "net_excess_return_5d": row["net_excess_return_5d"],
                        "daily_net_excess_percentile": percentile,
                        "strong_hotspot": strong,
                        "miss_stage": miss_stage(row),
                        "v3_raw_rank": row.get("v3_raw_rank"),
                        "v3_top20_rank": row.get("v3_top20_rank"),
                        "v3_top3_rank": row.get("v3_top3_rank"),
                        "entry_date": row.get("entry_date"),
                    }
                )
    stage_counts: dict[str, int] = defaultdict(int)
    strong_stage_counts: dict[str, int] = defaultdict(int)
    for row in winners:
        stage_counts[str(row["miss_stage"])] += 1
        if row["strong_hotspot"]:
            strong_stage_counts[str(row["miss_stage"])] += 1
    named_symbols = set(design["evaluation"]["named_cases"])
    named_cases = [
        {
            "signal_day": row["signal_day"],
            "symbol": row["symbol"],
            "stock_name": row["stock_name"],
            "signal_close": row["signal_close"],
            "entry_date": row.get("entry_date"),
            "entry_status": row.get("entry_status"),
            "forward_return_5d": row.get("forward_return_5d"),
            "excess_return_5d": row.get("excess_return_5d"),
            "v3_raw_rank": row.get("v3_raw_rank"),
            "v3_top20_rank": row.get("v3_top20_rank"),
            "v3_top3_rank": row.get("v3_top3_rank"),
            "v3_market_cash_switch": row.get("v3_market_cash_switch"),
            "features": row["features"],
        }
        for row in snapshot["rows"]
        if row["symbol"] in named_symbols and row["signal_day"] >= "2026-07-20"
    ]
    material = {
        "artifact_type": "recent_hotspot_miss_attribution",
        "schema_version": DIAGNOSTIC_SCHEMA_VERSION,
        "status": "complete_retrospective_diagnostic_only",
        "source_snapshot_id": snapshot["artifact_id"],
        "evaluated_signal_day_count": len(rows_by_day),
        "evaluated_row_count": sum(len(rows) for rows in rows_by_day.values()),
        "broad_winner_count": len(winners),
        "strong_hotspot_count": sum(row["strong_hotspot"] for row in winners),
        "strong_hotspot_unique_symbol_count": len({row["symbol"] for row in winners if row["strong_hotspot"]}),
        "v3_market_cash_switch_signal_day_count": len(
            {
                row["signal_day"]
                for row in snapshot["rows"]
                if row.get("personally_eligible") and row.get("v3_market_cash_switch")
            }
        ),
        "broad_winner_stage_counts": dict(sorted(stage_counts.items())),
        "strong_hotspot_stage_counts": dict(sorted(strong_stage_counts.items())),
        "v3_top3_capture_rate_broad": (
            stage_counts.get("captured_executable_v3_top3", 0) / len(winners) if winners else None
        ),
        "winners": winners,
        "named_case_rows": named_cases,
        "claim_ceiling": "descriptive_outcome_aware_attribution_not_strategy_validation",
        "v3_signal_changed": False,
        "paper_tracking_changed": False,
    }
    digest = stable_digest(material)
    return {"artifact_id": f"recent-hotspot-attribution-{digest[:16]}", **material, "content_digest": digest}


def write_gzip_artifact(path: Path, payload: dict[str, Any]) -> None:
    material = {key: value for key, value in payload.items() if key not in {"artifact_id", "content_digest"}}
    if stable_digest(material) != payload.get("content_digest"):
        raise ValueError("recent hotspot PIT artifact digest mismatch")
    path.parent.mkdir(parents=True, exist_ok=True)
    rendered = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    if path.exists():
        with gzip.open(path, "rb") as handle:
            if handle.read() != rendered:
                raise ValueError(f"immutable artifact already exists: {path}")
        return
    with path.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as compressed:
            compressed.write(rendered)


def load_gzip_artifact(path: Path) -> dict[str, Any]:
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        payload = json.load(handle)
    material = {key: value for key, value in payload.items() if key not in {"artifact_id", "content_digest"}}
    if stable_digest(material) != payload.get("content_digest"):
        raise ValueError("recent hotspot PIT artifact digest mismatch")
    return payload


def write_json_artifact(path: Path, payload: dict[str, Any]) -> None:
    material = {key: value for key, value in payload.items() if key not in {"artifact_id", "content_digest"}}
    if stable_digest(material) != payload.get("content_digest"):
        raise ValueError("recent hotspot diagnostic artifact digest mismatch")
    rendered = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_text(encoding="utf-8") != rendered:
        raise ValueError(f"immutable artifact already exists: {path}")
    path.write_text(rendered, encoding="utf-8")

#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path
from typing import Any

from ashare_evidence.db import session_scope
from ashare_evidence.shortpick_portfolio_backtest import build_shortpick_portfolio_backtest

STAGES = (
    ("recent_full_pool", "2026-03-01", "2026-05-12"),
    ("one_year", "2025-05-12", "2026-05-12"),
    ("full_window", "2023-04-13", "2026-05-12"),
)
ENTRY_PRICE_SOURCES = ("next_close", "next_open", "same_close_proxy")


def _summary_row(stage: str, entry_price_source: str, payload: dict[str, Any]) -> dict[str, Any]:
    recommended = (payload.get("comparison") or {}).get("recommended") or {}
    leading = (
        ((payload.get("results") or {}).get("daily_rolling_5x10k") or {})
        .get("low_turnover_20d_uptrend_liquid_top120", {})
        .get("summary", {})
    )
    data_scope = payload.get("data_scope") or {}
    production = payload.get("production_evidence") or {}
    return {
        "stage": stage,
        "entry_price_source": entry_price_source,
        "signal_day_count": data_scope.get("signal_day_count"),
        "stock_like_series_count": data_scope.get("stock_like_series_count"),
        "recommended_mode": recommended.get("mode"),
        "recommended_strategy": recommended.get("strategy"),
        "recommended_label": recommended.get("label"),
        "recommended_trade_count": recommended.get("trade_count"),
        "recommended_total_return": recommended.get("total_return"),
        "recommended_excess_total_return": recommended.get("excess_total_return"),
        "recommended_max_drawdown": recommended.get("max_drawdown"),
        "leading_trade_count": leading.get("trade_count"),
        "leading_total_return": leading.get("total_return"),
        "leading_excess_total_return": leading.get("excess_total_return"),
        "leading_max_drawdown": leading.get("max_drawdown"),
        "leading_status": production.get("status"),
        "leading_failed_checks": production.get("failed_check_ids"),
    }


def _markdown_report(rows: list[dict[str, Any]]) -> str:
    lines = [
        "# Shortpick Staged Backtest Summary",
        "",
        "Entry sources:",
        "- `next_close`: 原冻结口径，信号日后下一交易日收盘买入。",
        "- `next_open`: 信号日后下一交易日开盘买入，开盘接近涨停时不假设成交。",
        "- `same_close_proxy`: 14点同日买入的日线代理，使用信号日收盘价近似盘中价；只做诊断，不等同真实14:00快照。",
        "",
        "| Stage | Entry | Signals | Universe | Recommended | Rec Excess | Rec DD | Frozen Excess | Frozen DD | Frozen Status |",
        "|---|---:|---:|---:|---|---:|---:|---:|---:|---|",
    ]
    for row in rows:
        lines.append(
            "| {stage} | {entry} | {signals} | {universe} | {rec} | {rec_excess} | {rec_dd} | {frozen_excess} | {frozen_dd} | {status} |".format(
                stage=row["stage"],
                entry=row["entry_price_source"],
                signals=row.get("signal_day_count"),
                universe=row.get("stock_like_series_count"),
                rec=row.get("recommended_strategy"),
                rec_excess=_fmt_pct(row.get("recommended_excess_total_return")),
                rec_dd=_fmt_pct(row.get("recommended_max_drawdown")),
                frozen_excess=_fmt_pct(row.get("leading_excess_total_return")),
                frozen_dd=_fmt_pct(row.get("leading_max_drawdown")),
                status=row.get("leading_status"),
            )
        )
    return "\n".join(lines) + "\n"


def _fmt_pct(value: Any) -> str:
    if value is None:
        return ""
    return f"{float(value) * 100:.1f}%"


def main() -> int:
    parser = argparse.ArgumentParser(description="Run staged Short Pick Lab portfolio backtests.")
    parser.add_argument("--database-url", default=None)
    parser.add_argument("--output-dir", default="output/shortpick-staged-backtests")
    parser.add_argument("--stage", action="append", choices=[stage[0] for stage in STAGES], default=None)
    parser.add_argument("--entry-price-source", action="append", choices=list(ENTRY_PRICE_SOURCES), default=None)
    parser.add_argument("--min-signal-symbol-count", type=int, default=1000)
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    selected_stages = [stage for stage in STAGES if args.stage is None or stage[0] in set(args.stage)]
    selected_entries = tuple(args.entry_price_source or ENTRY_PRICE_SOURCES)
    rows: list[dict[str, Any]] = []
    artifacts: list[dict[str, str]] = []

    with session_scope(args.database_url) as session:
        for stage_name, start, end in selected_stages:
            for entry_price_source in selected_entries:
                payload = build_shortpick_portfolio_backtest(
                    session,
                    start_date=date.fromisoformat(start),
                    end_date=date.fromisoformat(end),
                    entry_price_source=entry_price_source,
                    min_signal_symbol_count=args.min_signal_symbol_count,
                )
                filename = f"{stage_name}-{entry_price_source}.json"
                path = output_dir / filename
                path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
                rows.append(_summary_row(stage_name, entry_price_source, payload))
                artifacts.append({"stage": stage_name, "entry_price_source": entry_price_source, "path": str(path)})
                print(rows[-1], flush=True)

    summary = {"rows": rows, "artifacts": artifacts}
    (output_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    (output_dir / "summary.md").write_text(_markdown_report(rows), encoding="utf-8")
    print({"summary_json": str(output_dir / "summary.json"), "summary_md": str(output_dir / "summary.md")}, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

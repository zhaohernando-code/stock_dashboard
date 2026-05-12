#!/usr/bin/env python3
from __future__ import annotations

import argparse
import time
from datetime import date

from ashare_evidence.db import session_scope
from ashare_evidence.shortpick_lab import (
    ShortpickMarketFactorUniverseError,
    _bulk_upsert_shortpick_market_bars,
    _existing_shortpick_bar_count_for_day,
    _parse_day,
    _require_shortpick_tushare_credential,
    _sync_shortpick_tushare_stock_master,
    _tushare_rows,
)


def _trade_dates(session, *, start_date: date, end_date: date) -> list[date]:
    rows = _tushare_rows(
        session,
        api_name="trade_cal",
        params={
            "exchange": "SSE",
            "start_date": start_date.strftime("%Y%m%d"),
            "end_date": end_date.strftime("%Y%m%d"),
        },
        fields="exchange,cal_date,is_open,pretrade_date",
    )
    days: list[date] = []
    for row in rows:
        if str(row.get("is_open")) not in {"1", "1.0", "True", "true"} and row.get("is_open") != 1:
            continue
        day = _parse_day(row.get("cal_date"))
        if day is not None:
            days.append(day)
    return sorted(set(days))


def _tushare_rows_with_retries(
    session,
    *,
    api_name: str,
    params: dict[str, str],
    fields: str,
    attempts: int,
    retry_sleep_seconds: float,
) -> list[dict]:
    last_rows: list[dict] = []
    for attempt in range(1, max(1, int(attempts)) + 1):
        rows = _tushare_rows(session, api_name=api_name, params=params, fields=fields)
        if rows:
            return rows
        last_rows = rows
        if attempt < attempts and retry_sleep_seconds > 0:
            print(f"{api_name} returned empty rows for {params}; retry {attempt}/{attempts}", flush=True)
            time.sleep(float(retry_sleep_seconds))
    return last_rows


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill Short Pick Lab full eligible Tushare daily history.")
    parser.add_argument("--database-url", default=None)
    parser.add_argument("--start-date", required=True)
    parser.add_argument("--end-date", required=True)
    parser.add_argument("--sleep-seconds", type=float, default=0.25)
    parser.add_argument("--retry-attempts", type=int, default=4)
    parser.add_argument("--retry-sleep-seconds", type=float, default=5.0)
    parser.add_argument("--max-days", type=int, default=None)
    args = parser.parse_args()

    start_date = date.fromisoformat(args.start_date)
    end_date = date.fromisoformat(args.end_date)
    if end_date < start_date:
        raise SystemExit("--end-date must be >= --start-date")

    with session_scope(args.database_url) as session:
        _require_shortpick_tushare_credential(session)
        eligible_stocks, stock_summary = _sync_shortpick_tushare_stock_master(session, end_date)
        stocks_by_symbol = {stock.symbol: stock for stock in eligible_stocks}
        stock_ids = {int(stock.id) for stock in eligible_stocks if stock.id is not None}
        expected_floor = max(1, int(len(eligible_stocks) * 0.85))
        trade_days = _trade_dates(session, start_date=start_date, end_date=end_date)
        if args.max_days is not None:
            trade_days = trade_days[: max(0, int(args.max_days))]
        print(
            {
                "eligible_symbol_count": len(eligible_stocks),
                "stock_summary": stock_summary,
                "trade_day_count": len(trade_days),
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "expected_floor": expected_floor,
            },
            flush=True,
        )
        refreshed = 0
        skipped = 0
        for index, trade_day in enumerate(trade_days, start=1):
            existing_count = _existing_shortpick_bar_count_for_day(
                session,
                trade_day=trade_day,
                stock_ids=stock_ids,
            )
            if existing_count >= expected_floor:
                skipped += 1
                print(f"[{index}/{len(trade_days)}] skip {trade_day} existing={existing_count}", flush=True)
                continue
            trade_date = trade_day.strftime("%Y%m%d")
            market_rows = _tushare_rows_with_retries(
                session,
                api_name="daily",
                params={"trade_date": trade_date},
                fields="ts_code,trade_date,open,high,low,close,vol,amount",
                attempts=args.retry_attempts,
                retry_sleep_seconds=args.retry_sleep_seconds,
            )
            basic_rows = _tushare_rows_with_retries(
                session,
                api_name="daily_basic",
                params={"trade_date": trade_date},
                fields="ts_code,trade_date,turnover_rate,total_mv,circ_mv,pe_ttm,pb",
                attempts=args.retry_attempts,
                retry_sleep_seconds=args.retry_sleep_seconds,
            )
            if not market_rows:
                raise ShortpickMarketFactorUniverseError(f"Tushare daily returned no rows for {trade_date}.")
            if not basic_rows:
                raise ShortpickMarketFactorUniverseError(f"Tushare daily_basic returned no rows for {trade_date}.")
            upserted = _bulk_upsert_shortpick_market_bars(
                session,
                stocks_by_symbol=stocks_by_symbol,
                market_rows=market_rows,
                basic_rows=basic_rows,
                trade_day=trade_day,
            )
            if upserted < expected_floor:
                raise ShortpickMarketFactorUniverseError(
                    f"Tushare full universe upsert for {trade_date} was too small: {upserted} < {expected_floor}."
                )
            session.commit()
            refreshed += 1
            print(f"[{index}/{len(trade_days)}] upsert {trade_day} rows={upserted}", flush=True)
            if args.sleep_seconds > 0:
                time.sleep(float(args.sleep_seconds))
        print({"refreshed_day_count": refreshed, "skipped_day_count": skipped}, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

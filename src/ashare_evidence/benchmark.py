from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, date, datetime, time, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ashare_evidence.akshare_timeout import call_akshare_function
from ashare_evidence.lineage import build_lineage
from ashare_evidence.models import MarketBar, Stock
from ashare_evidence.stock_master import DEFAULT_AKSHARE_TIMEOUT_SECONDS, akshare_runtime_ready, resolve_stock_profile

CSI_BENCHMARKS: dict[str, dict[str, str]] = {
    "CSI300": {"symbol": "000300.SH", "label": "沪深300"},
    "CSI500": {"symbol": "000905.SH", "label": "中证500"},
    "CSI1000": {"symbol": "000852.SH", "label": "中证1000"},
}

DEFAULT_BENCHMARK_ID = "CSI300"

SHANGHAI_TZ_OFFSET = time(15, 0)

_CSI_AKSHARE_SYMBOLS: dict[str, str] = {
    "000300.SH": "sh000300",
    "000905.SH": "sh000905",
    "000852.SH": "sh000852",
}


def _parse_index_day(raw: Any) -> date | None:
    if raw is None:
        return None
    if isinstance(raw, datetime):
        return raw.date()
    if isinstance(raw, date):
        return raw
    digits = "".join(c for c in str(raw) if c.isdigit())
    if len(digits) != 8:
        return None
    return date(int(digits[0:4]), int(digits[4:6]), int(digits[6:8]))


def _to_float_safe(raw: Any) -> float | None:
    if raw is None:
        return None
    try:
        return float(str(raw).replace(",", ""))
    except (TypeError, ValueError):
        return None


def _tushare_index_rows(
    session: Session,
    *,
    symbol: str,
    start_day: date,
    end_day: date,
) -> list[dict[str, Any]]:
    # Import lazily to keep the benchmark module independent from the broader
    # analysis pipeline during module initialization.
    from ashare_evidence.analysis_pipeline import _tushare_rows

    rows = _tushare_rows(
        session,
        api_name="index_daily",
        params={
            "ts_code": symbol,
            "start_date": start_day.strftime("%Y%m%d"),
            "end_date": end_day.strftime("%Y%m%d"),
        },
        fields="ts_code,trade_date,open,high,low,close,vol,amount",
    )
    return [
        {
            "date": row.get("trade_date"),
            "open": row.get("open"),
            "high": row.get("high"),
            "low": row.get("low"),
            "close": row.get("close"),
            "volume": row.get("vol"),
            "amount": row.get("amount"),
        }
        for row in rows
    ]


def _akshare_index_rows(*, akshare_code: str) -> list[dict[str, Any]]:
    if not akshare_runtime_ready():
        return []
    frame = call_akshare_function(
        "stock_zh_index_daily",
        kwargs={"symbol": akshare_code},
        timeout_seconds=DEFAULT_AKSHARE_TIMEOUT_SECONDS,
    )
    if frame is None or getattr(frame, "empty", False):
        return []
    return list(frame.to_dict(orient="records"))


def _latest_index_day(rows: list[dict[str, Any]]) -> date | None:
    parsed_days = [trade_day for row in rows if (trade_day := _parse_index_day(row.get("date"))) is not None]
    return max(parsed_days, default=None)


def _upsert_index_rows(
    session: Session,
    *,
    stock: Stock,
    symbol: str,
    provider_name: str,
    provider_symbol: str,
    rows: list[dict[str, Any]],
    start_day: date,
) -> int:
    processed = 0
    for row in rows:
        trade_day = _parse_index_day(row.get("date"))
        if trade_day is None or trade_day < start_day:
            continue
        open_price = _to_float_safe(row.get("open"))
        high_price = _to_float_safe(row.get("high"))
        low_price = _to_float_safe(row.get("low"))
        close_price = _to_float_safe(row.get("close"))
        volume = _to_float_safe(row.get("volume"))
        amount = _to_float_safe(row.get("amount"))
        if None in {open_price, high_price, low_price, close_price}:
            continue
        observed_at = datetime.combine(trade_day, SHANGHAI_TZ_OFFSET)
        bar_key = f"bar-{stock.ticker.lower()}-1d-{trade_day:%Y%m%d}"
        existing = session.scalar(select(MarketBar).where(MarketBar.bar_key == bar_key))
        dataset = "index_daily" if provider_name == "tushare" else "stock_zh_index_daily"
        source_uri = (
            f"tushare://index_daily/{symbol}?trade_date={trade_day:%Y%m%d}"
            if provider_name == "tushare"
            else f"akshare://stock_zh_index_daily/{provider_symbol}?date={trade_day:%Y%m%d}"
        )
        bar_lineage = build_lineage(
            {"bar_key": bar_key, "source": f"{provider_name}_{dataset}"},
            source_uri=source_uri,
            license_tag="tushare-pro" if provider_name == "tushare" else "akshare-public-web",
            usage_scope="internal_research",
            redistribution_scope="limited-display",
        )
        values = {
            "bar_key": bar_key,
            "stock_id": stock.id,
            "timeframe": "1d",
            "observed_at": observed_at,
            "open_price": float(open_price),
            "high_price": float(high_price),
            "low_price": float(low_price),
            "close_price": float(close_price),
            "volume": float(volume or 0.0),
            "amount": float(amount or 0.0),
            "turnover_rate": None,
            "adj_factor": None,
            "raw_payload": {
                "provider_name": provider_name,
                "dataset": dataset,
                "symbol": provider_symbol,
            },
            **bar_lineage,
        }
        if existing is None:
            session.add(MarketBar(**values))
        else:
            for key, value in values.items():
                setattr(existing, key, value)
        processed += 1
    session.flush()
    return processed


def _ensure_index_stock(session: Session, symbol: str) -> Stock:
    existing = session.scalar(select(Stock).where(Stock.symbol == symbol))
    if existing is not None:
        return existing
    profile = resolve_stock_profile(session, symbol=symbol)
    ticker, _, exchange = symbol.partition(".")
    lineage = build_lineage(
        {"symbol": symbol, "name": profile.name},
        source_uri=f"akshare://stock_zh_index_daily/{symbol}",
        license_tag="akshare-public-web",
        usage_scope="internal_research",
        redistribution_scope="limited-display",
    )
    stock = Stock(
        symbol=symbol,
        ticker=ticker,
        exchange=exchange.upper(),
        name=profile.name or symbol,
        provider_symbol=symbol,
        listed_date=profile.listed_date,
        status="active",
        profile_payload={"source": profile.source, "industry": profile.industry},
        **lineage,
    )
    session.add(stock)
    session.flush()
    return stock


def sync_benchmark_index_bars(
    session: Session,
    *,
    lookback_days: int = 400,
    required_through: date | None = None,
    progress: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    today = datetime.now(UTC).date()
    start_day = today - timedelta(days=lookback_days)
    required_day = required_through or today
    result: dict[str, Any] = {
        "status": "error",
        "required_through": required_day.isoformat(),
        "symbols": {},
    }
    for symbol, akshare_code in _CSI_AKSHARE_SYMBOLS.items():
        attempts: list[dict[str, Any]] = []
        try:
            stock = _ensure_index_stock(session, symbol)
            try:
                rows = _tushare_index_rows(session, symbol=symbol, start_day=start_day, end_day=today)
            except Exception as exc:
                rows = []
                attempts.append({"provider_name": "tushare", "status": "error", "reason": str(exc)})
            else:
                latest_day = _latest_index_day(rows)
                attempts.append(
                    {
                        "provider_name": "tushare",
                        "status": "ok",
                        "row_count": len(rows),
                        "latest_trade_day": latest_day.isoformat() if latest_day else None,
                    }
                )
            provider_name = "tushare"
            provider_symbol = symbol
            if _latest_index_day(rows) is None or _latest_index_day(rows) < required_day:
                try:
                    akshare_rows = _akshare_index_rows(akshare_code=akshare_code)
                except Exception as exc:
                    akshare_rows = []
                    attempts.append({"provider_name": "akshare", "status": "error", "reason": str(exc)})
                else:
                    latest_day = _latest_index_day(akshare_rows)
                    attempts.append(
                        {
                            "provider_name": "akshare",
                            "status": "ok",
                            "row_count": len(akshare_rows),
                            "latest_trade_day": latest_day.isoformat() if latest_day else None,
                        }
                    )
                if (_latest_index_day(akshare_rows) or date.min) > (_latest_index_day(rows) or date.min):
                    rows = akshare_rows
                    provider_name = "akshare"
                    provider_symbol = akshare_code
            if not rows:
                result["symbols"][symbol] = {"status": "empty", "bars": 0, "attempts": attempts}
                continue
            processed = _upsert_index_rows(
                session,
                stock=stock,
                symbol=symbol,
                provider_name=provider_name,
                provider_symbol=provider_symbol,
                rows=rows,
                start_day=start_day,
            )
            latest_trade_day = _latest_index_day(rows)
            status = "ok" if latest_trade_day is not None and latest_trade_day >= required_day else "stale"
            result["symbols"][symbol] = {
                "status": status,
                "bars": processed,
                "provider_name": provider_name,
                "latest_trade_day": latest_trade_day.isoformat() if latest_trade_day else None,
                "required_through": required_day.isoformat(),
                "attempts": attempts,
            }
            if progress:
                progress(f"{symbol} ({provider_name}): {processed} bars")
        except Exception as exc:
            result["symbols"][symbol] = {"status": "error", "reason": str(exc), "attempts": attempts}
    successful = sum(1 for item in result["symbols"].values() if item.get("status") == "ok")
    result["status"] = "ok" if successful == len(_CSI_AKSHARE_SYMBOLS) else "partial" if successful else "error"
    result["primary_ready"] = result["symbols"].get(CSI_BENCHMARKS[DEFAULT_BENCHMARK_ID]["symbol"], {}).get(
        "status"
    ) == "ok"
    return result


def benchmark_symbols() -> list[str]:
    return [item["symbol"] for item in CSI_BENCHMARKS.values()]


def benchmark_close_maps(session: Session) -> dict[str, dict[Any, float]]:
    rows = session.execute(
        select(Stock.symbol, MarketBar.observed_at, MarketBar.close_price)
        .join(MarketBar, MarketBar.stock_id == Stock.id)
        .where(Stock.symbol.in_(benchmark_symbols()), MarketBar.timeframe == "1d")
        .order_by(Stock.symbol.asc(), MarketBar.observed_at.asc())
    ).all()
    by_symbol: dict[str, dict[Any, float]] = {symbol: {} for symbol in benchmark_symbols()}
    for symbol, observed_at, close_price in rows:
        by_symbol[str(symbol)][observed_at.date()] = float(close_price)
    return by_symbol


def benchmark_context_summary(session: Session) -> dict[str, Any]:
    close_maps = benchmark_close_maps(session)
    items: list[dict[str, Any]] = []
    available = 0
    for benchmark_id, definition in CSI_BENCHMARKS.items():
        symbol = definition["symbol"]
        series = close_maps.get(symbol, {})
        latest_day = max(series) if series else None
        if series:
            available += 1
        items.append(
            {
                "benchmark_id": benchmark_id,
                "symbol": symbol,
                "label": definition["label"],
                "bar_count": len(series),
                "latest_trade_day": latest_day.isoformat() if latest_day else None,
                "status": "available" if series else "missing",
            }
        )
    status = "available" if close_maps.get(CSI_BENCHMARKS[DEFAULT_BENCHMARK_ID]["symbol"]) else "pending_index_bars"
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "primary_benchmark": DEFAULT_BENCHMARK_ID,
        "primary_symbol": CSI_BENCHMARKS[DEFAULT_BENCHMARK_ID]["symbol"],
        "primary_label": CSI_BENCHMARKS[DEFAULT_BENCHMARK_ID]["label"],
        "research_benchmarks": items,
        "available_benchmark_count": available,
        "status": status,
        "note": (
            "主展示 benchmark 采用沪深300；研究 artifact 同时保留沪深300、中证500、中证1000。"
            if status == "available"
            else "CSI 指数日线尚未完整入库；研究结论不得只依赖旧的观察池等权 proxy。"
        ),
    }

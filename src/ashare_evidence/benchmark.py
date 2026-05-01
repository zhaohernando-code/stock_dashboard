from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, date, datetime, time, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ashare_evidence.lineage import build_lineage
from ashare_evidence.models import MarketBar, Stock
from ashare_evidence.stock_master import resolve_stock_profile

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


def _akshare_index_module() -> Any | None:
    try:
        import akshare as ak  # type: ignore[import-untyped]
        return ak
    except Exception:
        return None


def sync_benchmark_index_bars(
    session: Session,
    *,
    lookback_days: int = 400,
    progress: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    ak = _akshare_index_module()
    if ak is None:
        return {"status": "skipped", "reason": "akshare_unavailable"}
    result: dict[str, Any] = {"status": "ok", "symbols": {}}
    today = datetime.now(UTC).date()
    start_day = today - timedelta(days=lookback_days)
    for symbol, akshare_code in _CSI_AKSHARE_SYMBOLS.items():
        try:
            stock = _ensure_index_stock(session, symbol)
            frame = ak.stock_zh_index_daily(symbol=akshare_code)
            if frame is None or getattr(frame, "empty", False):
                result["symbols"][symbol] = {"status": "empty", "bars": 0}
                continue
            inserted = 0
            for row in frame.to_dict(orient="records"):
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
                existing = session.scalar(
                    select(MarketBar).where(MarketBar.bar_key == bar_key)
                )
                bar_lineage = build_lineage(
                    {"bar_key": bar_key, "source": "akshare_stock_zh_index_daily"},
                    source_uri=f"akshare://stock_zh_index_daily/{akshare_code}?date={trade_day:%Y%m%d}",
                    license_tag="akshare-public-web",
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
                        "provider_name": "akshare",
                        "dataset": "stock_zh_index_daily",
                        "symbol": akshare_code,
                    },
                    **bar_lineage,
                }
                if existing is None:
                    session.add(MarketBar(**values))
                else:
                    for k, v in values.items():
                        setattr(existing, k, v)
                inserted += 1
            session.flush()
            result["symbols"][symbol] = {"status": "ok", "bars": inserted}
            if progress:
                progress(f"{symbol} ({akshare_code}): {inserted} bars")
        except Exception as exc:
            result["symbols"][symbol] = {"status": "error", "reason": str(exc)}
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

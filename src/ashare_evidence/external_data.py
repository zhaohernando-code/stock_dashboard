from __future__ import annotations

from typing import Any


def fetch_external_data(symbol: str) -> dict[str, Any]:
    result: dict[str, Any] = {
        "news_flow": [],
        "stock_news": [],
        "macro_news": [],
        "sector_flow": [],
        "fund_flow_rank": {},
        "source": "无外部数据源",
    }

    # 1. 个股信息流（新浪/东方财富）
    try:
        import akshare as ak  # type: ignore[import-untyped]

        df = ak.stock_individual_info_flow(symbol=symbol)
        if df is not None and not df.empty:
            records = df.head(10).to_dict(orient="records")
            result["news_flow"] = [
                {"title": str(r.get("title", r.get("note", ""))), "time": str(r.get("time", r.get("datetime", "")))}
                for r in records
            ]
            result["source"] = "AKShare（新浪/东方财富）"
    except Exception:
        pass

    # 2. 东财个股新闻（含新闻内容摘要）
    try:
        import akshare as ak  # type: ignore[import-untyped]

        df = ak.stock_news_em(symbol=symbol)
        if df is not None and not df.empty:
            records = df.head(10).to_dict(orient="records")
            result["stock_news"] = [
                {
                    "title": str(r.get("新闻标题", "")),
                    "content": str(r.get("新闻内容", ""))[:200],
                    "time": str(r.get("发布时间", "")),
                    "source": str(r.get("文章来源", "")),
                }
                for r in records
            ]
            if not result["source"].startswith("AKShare"):
                result["source"] = "AKShare（东方财富+新浪）"
    except Exception:
        pass

    # 3. 财新主流媒体新闻（宏观/行业热点）
    try:
        import akshare as ak  # type: ignore[import-untyped]

        df = ak.stock_news_main_cx()
        if df is not None and not df.empty:
            records = df.head(15).to_dict(orient="records")
            result["macro_news"] = [
                {"title": str(r.get("summary", ""))[:150], "tag": str(r.get("tag", ""))}
                for r in records
            ]
    except Exception:
        pass

    # 4. 板块资金流向排名
    try:
        import akshare as ak  # type: ignore[import-untyped]

        df = ak.stock_sector_fund_flow_rank(indicator="今日")
        if df is not None and not df.empty:
            records = df.head(8).to_dict(orient="records")
            result["sector_flow"] = [
                {
                    "sector": str(r.get("名称", "")),
                    "net_flow": str(r.get("主力净流入-净额", "")),
                    "net_rate": str(r.get("主力净流入-净占比", "")),
                }
                for r in records
            ]
    except Exception:
        pass

    # 5. 全市场个股资金流排名（判断相对位置）
    try:
        import akshare as ak  # type: ignore[import-untyped]

        df = ak.stock_individual_fund_flow_rank(indicator="今日")
        if df is not None and not df.empty:
            target = df[df["代码"] == symbol]
            if not target.empty:
                row = target.iloc[0].to_dict()
                result["fund_flow_rank"] = {
                    "rank": row.get("序号"),
                    "net_flow": str(row.get("主力净流入-净额", "")),
                    "net_rate": str(row.get("主力净流入-净占比", "")),
                }
    except Exception:
        pass

    return result

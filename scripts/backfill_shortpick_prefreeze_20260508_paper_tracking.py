from __future__ import annotations

import argparse
from datetime import UTC, date, datetime
from typing import Any

from ashare_evidence.db import init_database, session_scope
from ashare_evidence.models import ShortpickCandidate, ShortpickExperimentRun
from ashare_evidence.shortpick_lab import (
    SHORTPICK_INFORMATION_MODE,
    SHORTPICK_MARKET_FACTOR_COOLDOWN_TOP1_CONTROL_ROLE,
    SHORTPICK_MARKET_FACTOR_LEGACY_SECOND_CONTROL_ROLE,
    SHORTPICK_MARKET_FACTOR_OFFENSIVE_TOP1_CONTROL_ROLE,
    SHORTPICK_MARKET_FACTOR_RANDOM_POOL_CONTROL_ROLE,
    SHORTPICK_MARKET_FACTOR_TOP3_EQUAL_WEIGHT_CONTROL_ROLE,
)

RUN_KEY = "shortpick-prefreeze-paper-seed-2026-05-08"
SOURCE_URI = "output/shortpick-mainboard-new-retail-tushare-20260510.db"


SEED_ROWS: list[dict[str, Any]] = [
    {
        "role": "frozen_paper_primary",
        "group": "frozen",
        "priority": "market_factor_frozen_paper",
        "symbol": "601138.SH",
        "name": "工业富联",
        "label": "低换手上升趋势",
        "rank": 1,
        "close": 63.28,
        "ret1": -1.4,
        "ret10": 3.0,
        "ret20": 20.3,
        "turnover": 0.8165,
        "thesis": "2026-05-08 收盘后冻结主线盘前可用标的；低换手且20日趋势向上，供 2026-05-11 收盘纸面入场跟踪。",
    },
    {
        "role": SHORTPICK_MARKET_FACTOR_LEGACY_SECOND_CONTROL_ROLE,
        "group": "market_control",
        "priority": "market_factor_paper_control",
        "symbol": "001336.SZ",
        "name": "楚环科技",
        "label": "旧主线：第二候选",
        "rank": 1,
        "close": 30.13,
        "ret1": 1.9,
        "ret10": 14.5,
        "ret20": 18.8,
        "turnover": 6.1861,
        "thesis": "2026-05-08 收盘后旧主线第二候选对照，按 2026-05-11 收盘纸面入场跟踪。",
    },
    {
        "role": SHORTPICK_MARKET_FACTOR_OFFENSIVE_TOP1_CONTROL_ROLE,
        "group": "market_control",
        "priority": "market_factor_paper_control",
        "symbol": "600105.SH",
        "name": "永鼎股份",
        "label": "动量换手第1名",
        "rank": 1,
        "close": 49.94,
        "ret1": 5.1,
        "ret10": 20.7,
        "ret20": 65.3,
        "turnover": 14.2761,
        "thesis": "2026-05-08 收盘后动量换手第1名对照，按 2026-05-11 收盘纸面入场跟踪。",
    },
    {
        "role": SHORTPICK_MARKET_FACTOR_COOLDOWN_TOP1_CONTROL_ROLE,
        "group": "market_control",
        "priority": "market_factor_paper_control",
        "symbol": "001336.SZ",
        "name": "楚环科技",
        "label": "降追高第1名",
        "rank": 1,
        "close": 30.13,
        "ret1": 1.9,
        "ret10": 14.5,
        "ret20": 18.8,
        "turnover": 6.1861,
        "thesis": "2026-05-08 收盘后降追高第1名对照，按 2026-05-11 收盘纸面入场跟踪。",
    },
    {
        "role": SHORTPICK_MARKET_FACTOR_TOP3_EQUAL_WEIGHT_CONTROL_ROLE,
        "group": "market_control",
        "priority": "market_factor_paper_control",
        "symbol": "600105.SH",
        "name": "永鼎股份",
        "label": "前三名等权组合",
        "rank": 1,
        "close": 49.94,
        "ret1": 5.1,
        "ret10": 20.7,
        "ret20": 65.3,
        "turnover": 14.2761,
        "thesis": "2026-05-08 收盘后前三名等权组合第1只，按 2026-05-11 收盘纸面入场跟踪。",
    },
    {
        "role": SHORTPICK_MARKET_FACTOR_TOP3_EQUAL_WEIGHT_CONTROL_ROLE,
        "group": "market_control",
        "priority": "market_factor_paper_control",
        "symbol": "001336.SZ",
        "name": "楚环科技",
        "label": "前三名等权组合",
        "rank": 2,
        "close": 30.13,
        "ret1": 1.9,
        "ret10": 14.5,
        "ret20": 18.8,
        "turnover": 6.1861,
        "thesis": "2026-05-08 收盘后前三名等权组合第2只，按 2026-05-11 收盘纸面入场跟踪。",
    },
    {
        "role": SHORTPICK_MARKET_FACTOR_TOP3_EQUAL_WEIGHT_CONTROL_ROLE,
        "group": "market_control",
        "priority": "market_factor_paper_control",
        "symbol": "600249.SH",
        "name": "两面针",
        "label": "前三名等权组合",
        "rank": 3,
        "close": 6.36,
        "ret1": 7.1,
        "ret10": 7.8,
        "ret20": -2.9,
        "turnover": 9.222,
        "thesis": "2026-05-08 收盘后前三名等权组合第3只，按 2026-05-11 收盘纸面入场跟踪。",
    },
    {
        "role": SHORTPICK_MARKET_FACTOR_RANDOM_POOL_CONTROL_ROLE,
        "group": "market_random",
        "priority": "market_factor_paper_control",
        "symbol": "600515.SH",
        "name": "海南机场",
        "label": "同池随机基线",
        "rank": 1,
        "close": 3.55,
        "ret1": 2.0,
        "ret10": -2.2,
        "ret20": -0.3,
        "turnover": 1.6739,
        "thesis": "2026-05-08 收盘后同池随机基线对照，按 2026-05-11 收盘纸面入场跟踪。",
    },
]


def _payload(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "tracking_role": row["role"],
        "paper_tracking_seed": "prefreeze_20260508_open_watchlist",
        "paper_tracking_signal_date": "2026-05-08",
        "paper_tracking_entry_date": "2026-05-11",
        "paper_tracking_source_uri": SOURCE_URI,
        "selection_label": row["label"],
        "market_factor_overlay": {
            "source_rank": row["rank"],
            "seed_group": row["group"],
            "close_price": row["close"],
            "return_1d_pct": row["ret1"],
            "return_10d_pct": row["ret10"],
            "return_20d_pct": row["ret20"],
            "turnover_rate": row["turnover"],
        },
    }


def backfill(database_url: str) -> dict[str, int]:
    init_database(database_url)
    inserted = 0
    updated = 0
    now = datetime.now(UTC)
    with session_scope(database_url) as session:
        run = session.query(ShortpickExperimentRun).filter_by(run_key=RUN_KEY).one_or_none()
        summary_payload = {
            "market_factor_overlay": {
                "seeded_from": SOURCE_URI,
                "seed_reason": "2026-05-08 收盘盘前可用名单，供 2026-05-11 首个交易日纸面入场。",
                "frozen_paper_strategy": {
                    "inserted": True,
                    "gate_pass": True,
                    "symbol": "601138.SH",
                    "name": "工业富联",
                    "source": "prefreeze_20260508_open_watchlist",
                },
            }
        }
        if run is None:
            run = ShortpickExperimentRun(
                run_key=RUN_KEY,
                run_date=date(2026, 5, 8),
                prompt_version="prefreeze-paper-seed-20260508-v1",
                information_mode=SHORTPICK_INFORMATION_MODE,
                status="completed",
                trigger_source="manual_prefreeze_seed",
                triggered_by="root",
                started_at=now,
                completed_at=now,
                model_config={"source": SOURCE_URI, "seed": "prefreeze_20260508_open_watchlist"},
                summary_payload=summary_payload,
            )
            session.add(run)
            session.flush()
            inserted += 1
        else:
            run.summary_payload = summary_payload
            run.completed_at = run.completed_at or now
            updated += 1

        for row in SEED_ROWS:
            candidate_key = f"{RUN_KEY}:{row['role']}:{row['rank']}:{row['symbol']}"
            candidate = session.query(ShortpickCandidate).filter_by(candidate_key=candidate_key).one_or_none()
            payload = _payload(row)
            if candidate is None:
                session.add(
                    ShortpickCandidate(
                        run_id=run.id,
                        round_id=None,
                        candidate_key=candidate_key,
                        symbol=row["symbol"],
                        name=row["name"],
                        normalized_theme=row["label"],
                        horizon_trading_days=10,
                        confidence=None,
                        thesis=row["thesis"],
                        catalysts=[row["label"]],
                        invalidation=["仅作为纸面跟踪种子，不作为实时买卖建议。"],
                        risks=["冻结前候选回填，需在页面中和后续正式批次分开理解。"],
                        sources_payload=[{"title": "2026-05-08 盘前可用名单样本库", "url": SOURCE_URI}],
                        novelty_note="由 2026-05-08 收盘样本库回填，用于补齐 2026-05-11 入场纸面记录。",
                        limitations=["该记录来自冻结切换前的盘前可用名单，只用于纸面跟踪连续性。"],
                        convergence_group=row["group"],
                        research_priority=row["priority"],
                        parse_status="parsed",
                        is_system_external=False,
                        candidate_payload=payload,
                    )
                )
                inserted += 1
            else:
                candidate.name = row["name"]
                candidate.normalized_theme = row["label"]
                candidate.thesis = row["thesis"]
                candidate.research_priority = row["priority"]
                candidate.parse_status = "parsed"
                candidate.candidate_payload = payload
                updated += 1

    return {"inserted": inserted, "updated": updated}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database-url", default="sqlite:///data/ashare_dashboard.db")
    args = parser.parse_args()
    result = backfill(args.database_url)
    print(result)


if __name__ == "__main__":
    main()

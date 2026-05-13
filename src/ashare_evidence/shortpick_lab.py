from __future__ import annotations

import hashlib
import html as html_lib
import json
import math
import os
import re
import signal
import subprocess
import tempfile
import threading
from collections import defaultdict
from collections.abc import Iterable
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any, Protocol
from urllib import request
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ashare_evidence.akshare_timeout import call_akshare_function
from ashare_evidence.analysis_pipeline import (
    _close_timestamp,
    _fetch_daily_bars_akshare,
    _fetch_daily_bars_tushare,
    _json_safe,
    _parse_day,
    _to_float,
    _tushare_rows,
)
from ashare_evidence.benchmark import CSI_BENCHMARKS, benchmark_close_maps, sync_benchmark_index_bars
from ashare_evidence.db import utcnow
from ashare_evidence.http_client import urlopen
from ashare_evidence.lineage import build_lineage
from ashare_evidence.llm_service import OpenAICompatibleTransport, route_model
from ashare_evidence.market_rules import ACCOUNT_PROFILE_NEW_RETAIL_CASH, account_trade_eligibility
from ashare_evidence.models import (
    MarketBar,
    ModelApiKey,
    ProviderCredential,
    Recommendation,
    SectorMembership,
    ShortpickCandidate,
    ShortpickConsensusSnapshot,
    ShortpickExperimentRun,
    ShortpickModelRound,
    ShortpickValidationSnapshot,
    Stock,
    WatchlistFollow,
)
from ashare_evidence.recommendation_selection import recommendation_recency_ordering
from ashare_evidence.research_artifact_store import artifact_root_from_database_url, write_shortpick_lab_artifact
from ashare_evidence.runtime_config import get_builtin_llm_executor_config, resolve_llm_key_candidates
from ashare_evidence.shortpick_policy import SHORTPICK_FROZEN_STRATEGY_CONFIG
from ashare_evidence.stock_master import DEFAULT_AKSHARE_TIMEOUT_SECONDS, akshare_runtime_ready, resolve_stock_profile

SHORTPICK_PROMPT_VERSION = "native_web_open_discovery_v1"
SHORTPICK_INFORMATION_MODE = "native_web_open_discovery"
SHORTPICK_DEFAULT_HORIZONS = [1, 3, 5, 10, 20]
SHORTPICK_OFFICIAL_VALIDATION_MODE = "after_close_t_plus_1_close_entry_v1"
SHORTPICK_LEGACY_VALIDATION_MODE = "legacy_previous_close_entry"
SHORTPICK_SIGNAL_REACTION_MODE = "signal_reaction_close_to_close"
SHORTPICK_OFFICIAL_TRADEABILITY_STATUS = "tradeable"
SHORTPICK_TRADEABILITY_BLOCKED_PRIORITY = "tradeability_blocked"
SHORTPICK_DIAGNOSTIC_CANDIDATE_BUCKET = "diagnostic"
SHORTPICK_NORMAL_CANDIDATE_BUCKET = "normal"
SHORTPICK_DIAGNOSTIC_VALIDATION_STATUSES = {
    "pending_market_data",
    "pending_entry_bar",
    "suspended_or_no_current_bar",
    "entry_unfillable_limit_up",
    "tradeability_uncertain",
}
SHORTPICK_PRIMARY_BENCHMARK_ID = "CSI300"
SHORTPICK_RESEARCH_BENCHMARK_IDS = ["CSI1000"]
SHORTPICK_BENCHMARK_DIMENSION_HS300 = "hs300"
SHORTPICK_BENCHMARK_DIMENSION_CSI1000 = "csi1000"
SHORTPICK_BENCHMARK_DIMENSION_SECTOR = "sector_equal_weight"
SHORTPICK_BENCHMARK_DIMENSIONS = [
    SHORTPICK_BENCHMARK_DIMENSION_HS300,
    SHORTPICK_BENCHMARK_DIMENSION_CSI1000,
    SHORTPICK_BENCHMARK_DIMENSION_SECTOR,
]
SHORTPICK_MIN_SECTOR_PEER_SYMBOLS = 2
SHORTPICK_TARGET_SECTOR_PEER_SYMBOLS = 10
SHORTPICK_CODEX_TIMEOUT_SECONDS = 240
SHORTPICK_SOURCE_CHECK_TIMEOUT_SECONDS = 3
SHORTPICK_SOURCE_CHECK_RETRY_ATTEMPTS = 2
SHORTPICK_SEARXNG_TIMEOUT_SECONDS = 12
SHORTPICK_DEEPSEEK_SEARCH_TIMEOUT_SECONDS = 180
SHORTPICK_DEEPSEEK_MIN_SEARCH_RESULTS = 3
SHORTPICK_DEEPSEEK_QUERY_RETRY_ATTEMPTS = 2
SHORTPICK_LOBECHAT_SEARXNG_URL_ENV = "SHORTPICK_LOBECHAT_SEARXNG_URL"
SHORTPICK_LOBECHAT_SEARXNG_DEFAULT_URL = "http://127.0.0.1:18080"
_SHORTPICK_MARKET_FACTOR_CONFIG = SHORTPICK_FROZEN_STRATEGY_CONFIG["market_factor"]
_SHORTPICK_PAPER_TRACKING_CONFIG = SHORTPICK_FROZEN_STRATEGY_CONFIG["paper_tracking"]
_SHORTPICK_CONTROL_CONFIG = SHORTPICK_FROZEN_STRATEGY_CONFIG["controls"]
SHORTPICK_MARKET_FACTOR_POOL_LIMIT = int(_SHORTPICK_MARKET_FACTOR_CONFIG["pool_limit"])
SHORTPICK_MARKET_FACTOR_RANK_LIMIT = int(_SHORTPICK_MARKET_FACTOR_CONFIG["rank_limit"])
SHORTPICK_MARKET_FACTOR_DEFAULT_FAMILY = str(_SHORTPICK_MARKET_FACTOR_CONFIG["default_family"])
SHORTPICK_MARKET_FACTOR_OFFENSIVE_FAMILY = str(_SHORTPICK_MARKET_FACTOR_CONFIG["offensive_family"])
SHORTPICK_MARKET_FACTOR_RANDOM_CONTROL_FAMILY = str(_SHORTPICK_MARKET_FACTOR_CONFIG["random_control_family"])
SHORTPICK_MARKET_FACTOR_COOLDOWN_RET1_PENALTY = float(_SHORTPICK_MARKET_FACTOR_CONFIG["cooldown_ret1_penalty"])
SHORTPICK_FROZEN_PAPER_FAMILY = str(SHORTPICK_FROZEN_STRATEGY_CONFIG["family"])
SHORTPICK_FROZEN_PAPER_VERSION = str(SHORTPICK_FROZEN_STRATEGY_CONFIG["version"])
SHORTPICK_FROZEN_PAPER_STOP_LOSS_PCT = float(_SHORTPICK_PAPER_TRACKING_CONFIG["stop_loss_pct"])
SHORTPICK_FROZEN_PAPER_TAKE_PROFIT_PCT = float(_SHORTPICK_PAPER_TRACKING_CONFIG["take_profit_pct"])
SHORTPICK_FROZEN_PAPER_PEAK_GIVEBACK_PCT = float(_SHORTPICK_PAPER_TRACKING_CONFIG["peak_giveback_pct"])
SHORTPICK_FROZEN_PAPER_WEAK_REBOUND_RETURN_PCT = float(_SHORTPICK_PAPER_TRACKING_CONFIG["weak_rebound_return_pct"])
SHORTPICK_FROZEN_PAPER_CHECK_START_DAY = int(_SHORTPICK_PAPER_TRACKING_CONFIG["check_start_trading_day"])
SHORTPICK_FROZEN_PAPER_MAX_HOLDING_DAYS = int(_SHORTPICK_PAPER_TRACKING_CONFIG["max_holding_trading_days"])
SHORTPICK_FROZEN_PAPER_REQUIRED_FORWARD_DAYS = int(_SHORTPICK_PAPER_TRACKING_CONFIG["required_forward_trading_days"])
SHORTPICK_FROZEN_PAPER_SOURCE_RANK = int(_SHORTPICK_PAPER_TRACKING_CONFIG["source_rank"])
SHORTPICK_FROZEN_PAPER_POOL_RET1_MAX = float(_SHORTPICK_PAPER_TRACKING_CONFIG["pool_ret1_max"])
SHORTPICK_FROZEN_PAPER_UNIVERSE_RET10_MIN = float(_SHORTPICK_PAPER_TRACKING_CONFIG["universe_ret10_min"])
SHORTPICK_LLM_PAPER_CONTROL_ROLE = "llm_paper_control_primary"
SHORTPICK_LLM_PAPER_CONTROL_VERSION = str(_SHORTPICK_CONTROL_CONFIG["llm_paper_control_version"])
_SHORTPICK_STRONG_BREADTH_RANK2_CONFIG = _SHORTPICK_CONTROL_CONFIG["strong_breadth_rank2"]
SHORTPICK_MARKET_FACTOR_OFFENSIVE_TOP1_CONTROL_ROLE = "market_factor_control_offensive_top1"
SHORTPICK_MARKET_FACTOR_COOLDOWN_TOP1_CONTROL_ROLE = "market_factor_control_cooldown_top1"
SHORTPICK_MARKET_FACTOR_RANDOM_POOL_CONTROL_ROLE = "market_factor_control_random_pool"
SHORTPICK_MARKET_FACTOR_TOP3_EQUAL_WEIGHT_CONTROL_ROLE = "market_factor_control_top3_equal_weight"
SHORTPICK_MARKET_FACTOR_GOLDEN_CROSS_CONTROL_ROLE = "market_factor_control_golden_cross_10_200"
SHORTPICK_MARKET_FACTOR_LEGACY_SECOND_CONTROL_ROLE = "market_factor_control_legacy_second_candidate"
SHORTPICK_MARKET_FACTOR_STRONG_BREADTH_RANK2_CONTROL_ROLE = str(_SHORTPICK_STRONG_BREADTH_RANK2_CONFIG["role"])
SHORTPICK_MARKET_FACTOR_STRONG_BREADTH_RANK2_FAMILY = str(_SHORTPICK_STRONG_BREADTH_RANK2_CONFIG["family"])
SHORTPICK_MARKET_FACTOR_STRONG_BREADTH_RANK2_SOURCE_RANK = int(_SHORTPICK_STRONG_BREADTH_RANK2_CONFIG["source_rank"])
SHORTPICK_MARKET_FACTOR_STRONG_BREADTH_RANK2_BREADTH10_MIN = float(_SHORTPICK_STRONG_BREADTH_RANK2_CONFIG["breadth10_min"])
SHORTPICK_MARKET_FACTOR_STRONG_BREADTH_RANK2_POOL_RET1_MAX = float(_SHORTPICK_STRONG_BREADTH_RANK2_CONFIG["pool_ret1_max"])
SHORTPICK_MARKET_FACTOR_STRONG_BREADTH_RANK2_POOL_RET10_MIN = float(_SHORTPICK_STRONG_BREADTH_RANK2_CONFIG["pool_ret10_min"])
_SHORTPICK_STRONG_BREADTH_RANK2_WEIGHTS = _SHORTPICK_STRONG_BREADTH_RANK2_CONFIG["weights"]
SHORTPICK_MARKET_FACTOR_STRONG_BREADTH_RANK2_RET10_WEIGHT = float(_SHORTPICK_STRONG_BREADTH_RANK2_WEIGHTS["return_10d"])
SHORTPICK_MARKET_FACTOR_STRONG_BREADTH_RANK2_AMOUNT_WEIGHT = float(_SHORTPICK_STRONG_BREADTH_RANK2_WEIGHTS["amount"])
SHORTPICK_MARKET_FACTOR_STRONG_BREADTH_RANK2_TURNOVER_WEIGHT = float(_SHORTPICK_STRONG_BREADTH_RANK2_WEIGHTS["turnover_rate"])
SHORTPICK_MARKET_FACTOR_STRONG_BREADTH_RANK2_RET1_PENALTY = float(_SHORTPICK_STRONG_BREADTH_RANK2_WEIGHTS["return_1d_penalty"])
_SHORTPICK_LOW_TURNOVER_UPTREND_CONFIG = _SHORTPICK_CONTROL_CONFIG["low_turnover_uptrend"]
SHORTPICK_MARKET_FACTOR_LOW_TURNOVER_UPTREND_CONTROL_ROLE = str(_SHORTPICK_LOW_TURNOVER_UPTREND_CONFIG["role"])
SHORTPICK_MARKET_FACTOR_LOW_TURNOVER_UPTREND_FAMILY = str(_SHORTPICK_LOW_TURNOVER_UPTREND_CONFIG["family"])
SHORTPICK_MARKET_FACTOR_LOW_TURNOVER_UPTREND_POOL_LIMIT = int(_SHORTPICK_LOW_TURNOVER_UPTREND_CONFIG["pool_limit"])
SHORTPICK_MARKET_FACTOR_LOW_TURNOVER_UPTREND_BREADTH10_MIN = float(_SHORTPICK_LOW_TURNOVER_UPTREND_CONFIG["breadth10_min"])
SHORTPICK_MARKET_FACTOR_LOW_TURNOVER_UPTREND_RETURN20_MIN = float(_SHORTPICK_LOW_TURNOVER_UPTREND_CONFIG["return_20d_min"])
_SHORTPICK_LOW_TURNOVER_UPTREND_WEIGHTS = _SHORTPICK_LOW_TURNOVER_UPTREND_CONFIG["weights"]
SHORTPICK_MARKET_FACTOR_LOW_TURNOVER_UPTREND_RET20_WEIGHT = float(_SHORTPICK_LOW_TURNOVER_UPTREND_WEIGHTS["return_20d"])
SHORTPICK_MARKET_FACTOR_LOW_TURNOVER_UPTREND_AMOUNT_WEIGHT = float(_SHORTPICK_LOW_TURNOVER_UPTREND_WEIGHTS["amount"])
SHORTPICK_MARKET_FACTOR_LOW_TURNOVER_UPTREND_TURNOVER_PENALTY = float(_SHORTPICK_LOW_TURNOVER_UPTREND_WEIGHTS["turnover_rate_penalty"])
_SHORTPICK_NO_LIMIT_CHASE_LOW_TURNOVER_CONFIG = _SHORTPICK_CONTROL_CONFIG["no_limit_chase_low_turnover_uptrend"]
SHORTPICK_MARKET_FACTOR_NO_LIMIT_CHASE_LOW_TURNOVER_CONTROL_ROLE = str(_SHORTPICK_NO_LIMIT_CHASE_LOW_TURNOVER_CONFIG["role"])
SHORTPICK_MARKET_FACTOR_NO_LIMIT_CHASE_LOW_TURNOVER_FAMILY = str(_SHORTPICK_NO_LIMIT_CHASE_LOW_TURNOVER_CONFIG["family"])
SHORTPICK_MARKET_FACTOR_NO_LIMIT_CHASE_RETURN1_MAX = float(_SHORTPICK_NO_LIMIT_CHASE_LOW_TURNOVER_CONFIG["return_1d_max"])
_SHORTPICK_OPEN_ENTRY_LOW_TURNOVER_CONFIG = _SHORTPICK_CONTROL_CONFIG["open_entry_low_turnover_uptrend"]
SHORTPICK_MARKET_FACTOR_OPEN_ENTRY_LOW_TURNOVER_CONTROL_ROLE = str(_SHORTPICK_OPEN_ENTRY_LOW_TURNOVER_CONFIG["role"])
SHORTPICK_MARKET_FACTOR_OPEN_ENTRY_LOW_TURNOVER_FAMILY = str(_SHORTPICK_OPEN_ENTRY_LOW_TURNOVER_CONFIG["family"])
SHORTPICK_ENTRY_PRICE_SOURCE_CLOSE = "next_close"
SHORTPICK_ENTRY_PRICE_SOURCE_OPEN = str(_SHORTPICK_OPEN_ENTRY_LOW_TURNOVER_CONFIG["entry_price_source"])
_SHORTPICK_INTRADAY_SAME_DAY_CONFIG = _SHORTPICK_CONTROL_CONFIG["intraday_same_day_low_turnover_uptrend"]
SHORTPICK_MARKET_FACTOR_INTRADAY_SAME_DAY_CONTROL_ROLE = str(_SHORTPICK_INTRADAY_SAME_DAY_CONFIG["role"])
SHORTPICK_MARKET_FACTOR_INTRADAY_SAME_DAY_FAMILY = str(_SHORTPICK_INTRADAY_SAME_DAY_CONFIG["family"])
SHORTPICK_ENTRY_PRICE_SOURCE_INTRADAY = str(_SHORTPICK_INTRADAY_SAME_DAY_CONFIG["entry_price_source"])
_SHORTPICK_QUIET_BREAKOUT_CONFIG = _SHORTPICK_CONTROL_CONFIG["quiet_breakout_rank2"]
SHORTPICK_MARKET_FACTOR_QUIET_BREAKOUT_CONTROL_ROLE = str(_SHORTPICK_QUIET_BREAKOUT_CONFIG["role"])
SHORTPICK_MARKET_FACTOR_QUIET_BREAKOUT_FAMILY = str(_SHORTPICK_QUIET_BREAKOUT_CONFIG["family"])
SHORTPICK_MARKET_FACTOR_QUIET_BREAKOUT_POOL_LIMIT = int(_SHORTPICK_QUIET_BREAKOUT_CONFIG["pool_limit"])
SHORTPICK_MARKET_FACTOR_QUIET_BREAKOUT_SOURCE_RANK = int(_SHORTPICK_QUIET_BREAKOUT_CONFIG["source_rank"])
SHORTPICK_MARKET_FACTOR_QUIET_BREAKOUT_RETURN10_MIN = float(_SHORTPICK_QUIET_BREAKOUT_CONFIG["return_10d_min"])
SHORTPICK_MARKET_FACTOR_QUIET_BREAKOUT_RETURN1_MAX = float(_SHORTPICK_QUIET_BREAKOUT_CONFIG["return_1d_max"])
_SHORTPICK_QUIET_BREAKOUT_WEIGHTS = _SHORTPICK_QUIET_BREAKOUT_CONFIG["weights"]
SHORTPICK_MARKET_FACTOR_QUIET_BREAKOUT_RET20_WEIGHT = float(_SHORTPICK_QUIET_BREAKOUT_WEIGHTS["return_20d"])
SHORTPICK_MARKET_FACTOR_QUIET_BREAKOUT_RET5_WEIGHT = float(_SHORTPICK_QUIET_BREAKOUT_WEIGHTS["return_5d"])
SHORTPICK_MARKET_FACTOR_QUIET_BREAKOUT_LOW_ABS_RET1_WEIGHT = float(_SHORTPICK_QUIET_BREAKOUT_WEIGHTS["low_abs_return_1d"])
SHORTPICK_MARKET_FACTOR_QUIET_BREAKOUT_AMOUNT_WEIGHT = float(_SHORTPICK_QUIET_BREAKOUT_WEIGHTS["amount"])
SHORTPICK_MARKET_FACTOR_PAPER_CONTROL_ROLES = {
    SHORTPICK_MARKET_FACTOR_OFFENSIVE_TOP1_CONTROL_ROLE,
    SHORTPICK_MARKET_FACTOR_COOLDOWN_TOP1_CONTROL_ROLE,
    SHORTPICK_MARKET_FACTOR_RANDOM_POOL_CONTROL_ROLE,
    SHORTPICK_MARKET_FACTOR_TOP3_EQUAL_WEIGHT_CONTROL_ROLE,
    SHORTPICK_MARKET_FACTOR_GOLDEN_CROSS_CONTROL_ROLE,
    SHORTPICK_MARKET_FACTOR_LEGACY_SECOND_CONTROL_ROLE,
    SHORTPICK_MARKET_FACTOR_STRONG_BREADTH_RANK2_CONTROL_ROLE,
    SHORTPICK_MARKET_FACTOR_NO_LIMIT_CHASE_LOW_TURNOVER_CONTROL_ROLE,
    SHORTPICK_MARKET_FACTOR_OPEN_ENTRY_LOW_TURNOVER_CONTROL_ROLE,
    SHORTPICK_MARKET_FACTOR_INTRADAY_SAME_DAY_CONTROL_ROLE,
}
SHORTPICK_MARKET_FACTOR_BREADTH10_THRESHOLD = float(_SHORTPICK_MARKET_FACTOR_CONFIG["breadth10_threshold"])
SHORTPICK_MARKET_FACTOR_POOL_RET10_THRESHOLD = float(_SHORTPICK_MARKET_FACTOR_CONFIG["pool_ret10_threshold"])
SHORTPICK_MARKET_FACTOR_EXCLUDED_SYMBOLS = {
    "000300.SH",
    "000905.SH",
    "000852.SH",
    "399300.SZ",
    *(definition["symbol"] for definition in CSI_BENCHMARKS.values()),
}
SHORTPICK_MARKET_FACTOR_MIN_FULL_UNIVERSE_SIZE = int(os.getenv("SHORTPICK_MARKET_FACTOR_MIN_FULL_UNIVERSE_SIZE", "1000"))
SHORTPICK_MARKET_FACTOR_FULL_SYNC_LOOKBACK_DAYS = int(os.getenv("SHORTPICK_MARKET_FACTOR_FULL_SYNC_LOOKBACK_DAYS", "90"))
SHORTPICK_MARKET_FACTOR_FULL_SYNC_MIN_TRADE_DAYS = int(os.getenv("SHORTPICK_MARKET_FACTOR_FULL_SYNC_MIN_TRADE_DAYS", "45"))
SHORTPICK_MARKET_FACTOR_COARSE_SCREEN_SIZE = int(os.getenv("SHORTPICK_MARKET_FACTOR_COARSE_SCREEN_SIZE", "800"))
SHORTPICK_MARKET_FACTOR_HOT_INDUSTRY_LIMIT = int(os.getenv("SHORTPICK_MARKET_FACTOR_HOT_INDUSTRY_LIMIT", "12"))
SHORTPICK_MARKET_FACTOR_HOT_INDUSTRY_MIN_SYMBOLS = int(os.getenv("SHORTPICK_MARKET_FACTOR_HOT_INDUSTRY_MIN_SYMBOLS", "5"))
SUSPICIOUS_SOURCE_PATTERNS = (
    re.compile(r"(?:123456|234567|345678|456789|987654|876543)"),
    re.compile(r"(.)\1{5,}"),
    re.compile(r"(?:xxxx|abc123|example|placeholder|dummy)", re.IGNORECASE),
)
RETRYABLE_FAILURE_CATEGORIES = {"retryable_search_failure", "retryable_parse_failure"}


def shortpick_frozen_paper_strategy_contract() -> dict[str, Any]:
    return {
        "status": "frozen_paper_tracking",
        "version": SHORTPICK_FROZEN_PAPER_VERSION,
        "family": SHORTPICK_FROZEN_PAPER_FAMILY,
        "label": "冻结纸面策略：低换手上升趋势四轨监测",
        "mode": "每日滚动 5x1万，次一交易日收盘买入；所有持有天数均按交易日计算",
        "pool_rule": f"先按成交额和换手率取流动性靠前的 {SHORTPICK_MARKET_FACTOR_LOW_TURNOVER_UPTREND_POOL_LIMIT} 只候选",
        "selection_rule": "当全市场10日上涨占比不低于45%时，选择20日趋势向上、成交额较高且换手率相对不拥挤的第1名",
        "risk_rule": "同一入场信号并行监测机械5日、机械10日、5-10日条件检查、10%触达止盈四条退出轨道",
        "monitoring_tracks": [
            {
                "key": "mechanical_5d",
                "label": "机械5日",
                "description": "次一交易日收盘买入，持有5个交易日后按收盘退出。",
                "holding_days": 5,
                "uses_trading_days": True,
            },
            {
                "key": "mechanical_10d",
                "label": "机械10日",
                "description": "次一交易日收盘买入，持有10个交易日后按收盘退出。",
                "holding_days": SHORTPICK_FROZEN_PAPER_MAX_HOLDING_DAYS,
                "uses_trading_days": True,
            },
            {
                "key": "conditional_5_to_10d",
                "label": "5日后条件检查",
                "description": "至少持有5个交易日；第5日至第10日每日收盘检查趋势转弱、从高点回撤扩大或8%收盘止损，触发则退出，否则第10日退出。",
                "check_start_day": SHORTPICK_FROZEN_PAPER_CHECK_START_DAY,
                "max_holding_days": SHORTPICK_FROZEN_PAPER_MAX_HOLDING_DAYS,
                "close_stop_loss_pct": SHORTPICK_FROZEN_PAPER_STOP_LOSS_PCT,
                "peak_giveback_pct": SHORTPICK_FROZEN_PAPER_PEAK_GIVEBACK_PCT,
                "uses_trading_days": True,
            },
            {
                "key": "take_profit_10pct",
                "label": "10%触达止盈",
                "description": "买入后10个交易日内，若日内最高价触达买入价上方10%，按+10%止盈价退出；未触达则第10日收盘退出。",
                "take_profit_pct": SHORTPICK_FROZEN_PAPER_TAKE_PROFIT_PCT,
                "max_holding_days": SHORTPICK_FROZEN_PAPER_MAX_HOLDING_DAYS,
                "execution_assumption": "daily_high_touch_price",
                "uses_trading_days": True,
            },
        ],
        "gate": {
            "breadth10_min": SHORTPICK_MARKET_FACTOR_LOW_TURNOVER_UPTREND_BREADTH10_MIN,
            "return_20d_min": SHORTPICK_MARKET_FACTOR_LOW_TURNOVER_UPTREND_RETURN20_MIN,
        },
        "required_forward_trading_days": SHORTPICK_FROZEN_PAPER_REQUIRED_FORWARD_DAYS,
        "frozen_at": "2026-05-11",
        "scope_note": "LLM自由选股保留为对照组；冻结策略不因纸面跟踪期间的回测表现调整参数。",
    }


def shortpick_llm_paper_control_contract() -> dict[str, Any]:
    return {
        "status": "paper_control_tracking",
        "version": SHORTPICK_LLM_PAPER_CONTROL_VERSION,
        "role": SHORTPICK_LLM_PAPER_CONTROL_ROLE,
        "label": "LLM纸面对照：每日固定规则选1只",
        "mode": "从当日LLM自由推荐池中，先按新开户普通现金账户口径过滤，再按冻结排序规则选出1只；所有持有天数均按交易日计算",
        "account_profile": ACCOUNT_PROFILE_NEW_RETAIL_CASH,
        "account_filter_rule": "仅允许沪深主板普通A股；排除科创板、创业板、北交所、ST/退市风险类标的。",
        "selection_rule": "先过滤到新开户普通现金账户可买范围；再优先跨模型同票，其次同模型重复、跨模型同题材、单模型高置信、系统外新视角；再按来源质量、置信度、来源数量、股票代码和候选ID稳定排序。",
        "monitoring_rule": "和冻结策略使用同一入场口径与四条退出轨道，避免从LLM推荐池中事后挑选。",
        "monitoring_tracks": shortpick_frozen_paper_strategy_contract()["monitoring_tracks"],
        "required_forward_trading_days": SHORTPICK_FROZEN_PAPER_REQUIRED_FORWARD_DAYS,
        "frozen_at": "2026-05-09",
        "scope_note": "全量LLM推荐池继续保留为研究样本；只有先满足账户可买范围、再按本规则提前标记的1只股票进入严格交易对照。",
    }


def shortpick_market_factor_paper_control_contracts() -> dict[str, Any]:
    return {
        "status": "paper_control_tracking",
        "version": str(_SHORTPICK_CONTROL_CONFIG["market_factor_control_version"]),
        "label": "市场因子纸面对照：同池简单选法",
        "mode": "和冻结策略使用同一个动量成交量Top40候选池，每个规则每天最多提前固定1只；所有持有天数均按交易日计算。",
        "monitoring_rule": "和冻结策略使用同一入场口径与四条退出轨道，用于判断冻结策略是否强过同池简单选法。",
        "monitoring_tracks": shortpick_frozen_paper_strategy_contract()["monitoring_tracks"],
        "controls": [
            {
                "role": SHORTPICK_MARKET_FACTOR_OFFENSIVE_TOP1_CONTROL_ROLE,
                "label": "动量换手第1名",
                "selection_rule": "动量成交量Top40池内，按10日涨幅排名与换手率排名相加后取第1名。",
            },
            {
                "role": SHORTPICK_MARKET_FACTOR_COOLDOWN_TOP1_CONTROL_ROLE,
                "label": "降追高第1名",
                "selection_rule": "同一Top40池内，用10日涨幅和换手率排序，同时扣减当日涨幅排名，取第1名。",
            },
            {
                "role": SHORTPICK_MARKET_FACTOR_RANDOM_POOL_CONTROL_ROLE,
                "label": "同池随机基线",
                "selection_rule": "同一Top40池内，用运行日期和股票代码做确定性哈希，提前固定1只，不看结果。",
            },
            {
                "role": SHORTPICK_MARKET_FACTOR_TOP3_EQUAL_WEIGHT_CONTROL_ROLE,
                "label": "前三名等权组合",
                "selection_rule": "市场转正且候选池不过热时，按10日动量与换手排序取前3名；每日纸面资金在3只之间等权分配。",
                "allocation_rule": "同一信号日等权观察；每只候选仍按同一入场口径和四条退出轨道记录。",
            },
            {
                "role": SHORTPICK_MARKET_FACTOR_GOLDEN_CROSS_CONTROL_ROLE,
                "label": "10/200日金叉过滤",
                "selection_rule": "按原动量成交量Top40候选顺序，选择第一个在信号日出现10日均线上穿200日均线的标的；没有触发则不出信号。",
            },
            {
                "role": SHORTPICK_MARKET_FACTOR_LEGACY_SECOND_CONTROL_ROLE,
                "label": "旧主线：第二候选四轨",
                "selection_rule": "保留原冻结主线作为对照：在市场转正且候选池不过热时，取10日动量与换手排序的第2名。",
            },
            {
                "role": SHORTPICK_MARKET_FACTOR_STRONG_BREADTH_RANK2_CONTROL_ROLE,
                "label": "强广度低追高二候选",
                "selection_rule": "动量成交量Top40池内，仅在全市场10日上涨占比不低于55%、Top40池10日平均涨幅不低于6%、Top40池1日平均涨幅不高于6%时，按10日涨幅、成交额、换手率综合排序并扣减当日涨幅，取第2名。",
            },
            {
                "role": SHORTPICK_MARKET_FACTOR_NO_LIMIT_CHASE_LOW_TURNOVER_CONTROL_ROLE,
                "label": "可执行风控版",
                "selection_rule": "沿用冻结低换手上升趋势排序，但排除信号日涨幅达到9.5%及以上的候选，再取第1名；用于并行观察非涨停追高过滤后的可执行表现。",
            },
            {
                "role": SHORTPICK_MARKET_FACTOR_OPEN_ENTRY_LOW_TURNOVER_CONTROL_ROLE,
                "label": "次日开盘买入版",
                "selection_rule": "沿用冻结低换手上升趋势第1名，只把入场价格从次一交易日收盘改为次一交易日开盘；若次日开盘价接近涨停，则不假设开盘可成交。",
                "entry_rule": "次一交易日开盘买入；开盘直接接近涨停时标记为不可假设成交。",
            },
            {
                "role": SHORTPICK_MARKET_FACTOR_INTRADAY_SAME_DAY_CONTROL_ROLE,
                "label": "14点同日买入版",
                "selection_rule": "交易日下午用实时行情替代当日收盘价，沿用冻结低换手上升趋势选股规则；推荐生成后再读取一次当前价作为纸面买入价。",
                "entry_rule": "信号日盘中当前价买入；若当前价接近涨停，则跳过该候选，不假设可以买入。",
                "target_publish_time": str(_SHORTPICK_INTRADAY_SAME_DAY_CONFIG["target_publish_time"]),
            },
        ],
        "scope_note": "单票分析当前覆盖不足，且历史LLM过滤/硬否决没有证明增益；暂不升入冻结真实跟踪，只保留为后续研究方向。",
    }


@dataclass(frozen=True)
class _ShortpickPeerCandidate:
    symbol: str
    name: str


LIMIT_UP_BANDS = {
    "default": 0.10,
    "star_or_chinext": 0.20,
    "beijing": 0.30,
    "st": 0.05,
}
SHORTPICK_SECTOR_PEER_UNIVERSE: dict[str, list[tuple[str, str]]] = {
    "C 制造业": [
        ("000333.SZ", "美的集团"),
        ("000651.SZ", "格力电器"),
        ("000725.SZ", "京东方A"),
        ("002371.SZ", "北方华创"),
        ("002415.SZ", "海康威视"),
        ("002475.SZ", "立讯精密"),
        ("300750.SZ", "宁德时代"),
        ("600031.SH", "三一重工"),
        ("600309.SH", "万华化学"),
        ("600660.SH", "福耀玻璃"),
    ],
    "制造业": [
        ("000333.SZ", "美的集团"),
        ("000651.SZ", "格力电器"),
        ("000725.SZ", "京东方A"),
        ("002371.SZ", "北方华创"),
        ("002415.SZ", "海康威视"),
        ("002475.SZ", "立讯精密"),
        ("300750.SZ", "宁德时代"),
        ("600031.SH", "三一重工"),
        ("600309.SH", "万华化学"),
        ("600660.SH", "福耀玻璃"),
    ],
    "半导体": [
        ("688981.SH", "中芯国际"),
        ("688012.SH", "中微公司"),
        ("688008.SH", "澜起科技"),
        ("688396.SH", "华润微"),
        ("688126.SH", "沪硅产业"),
        ("688072.SH", "拓荆科技"),
        ("688256.SH", "寒武纪"),
        ("002371.SZ", "北方华创"),
        ("300604.SZ", "长川科技"),
        ("603986.SH", "兆易创新"),
    ],
    "semiconductor": [
        ("688981.SH", "中芯国际"),
        ("688012.SH", "中微公司"),
        ("688008.SH", "澜起科技"),
        ("688396.SH", "华润微"),
        ("688126.SH", "沪硅产业"),
        ("688072.SH", "拓荆科技"),
        ("688256.SH", "寒武纪"),
        ("002371.SZ", "北方华创"),
        ("300604.SZ", "长川科技"),
        ("603986.SH", "兆易创新"),
    ],
    "通信设备": [
        ("000063.SZ", "中兴通讯"),
        ("000938.SZ", "紫光股份"),
        ("002281.SZ", "光迅科技"),
        ("002463.SZ", "沪电股份"),
        ("300308.SZ", "中际旭创"),
        ("300394.SZ", "天孚通信"),
        ("300502.SZ", "新易盛"),
        ("300628.SZ", "亿联网络"),
        ("600487.SH", "亨通光电"),
        ("600522.SH", "中天科技"),
    ],
    "电力设备": [
        ("002074.SZ", "国轩高科"),
        ("002129.SZ", "TCL中环"),
        ("002202.SZ", "金风科技"),
        ("002459.SZ", "晶澳科技"),
        ("002466.SZ", "天齐锂业"),
        ("002812.SZ", "恩捷股份"),
        ("300014.SZ", "亿纬锂能"),
        ("300274.SZ", "阳光电源"),
        ("300750.SZ", "宁德时代"),
        ("601012.SH", "隆基绿能"),
    ],
    "锂电池": [
        ("002074.SZ", "国轩高科"),
        ("002460.SZ", "赣锋锂业"),
        ("002466.SZ", "天齐锂业"),
        ("002709.SZ", "天赐材料"),
        ("002812.SZ", "恩捷股份"),
        ("300014.SZ", "亿纬锂能"),
        ("300037.SZ", "新宙邦"),
        ("300073.SZ", "当升科技"),
        ("300750.SZ", "宁德时代"),
        ("600884.SH", "杉杉股份"),
    ],
    "证券": [
        ("000166.SZ", "申万宏源"),
        ("000776.SZ", "广发证券"),
        ("002736.SZ", "国信证券"),
        ("600030.SH", "中信证券"),
        ("600061.SH", "国投资本"),
        ("600109.SH", "国金证券"),
        ("600837.SH", "海通证券"),
        ("600958.SH", "东方证券"),
        ("601688.SH", "华泰证券"),
        ("601995.SH", "中金公司"),
    ],
    "保险": [
        ("000627.SZ", "天茂集团"),
        ("601318.SH", "中国平安"),
        ("601319.SH", "中国人保"),
        ("601336.SH", "新华保险"),
        ("601601.SH", "中国太保"),
        ("601628.SH", "中国人寿"),
        ("601688.SH", "华泰证券"),
        ("600030.SH", "中信证券"),
        ("600837.SH", "海通证券"),
        ("000776.SZ", "广发证券"),
    ],
    "汽车整车": [
        ("000625.SZ", "长安汽车"),
        ("000800.SZ", "一汽解放"),
        ("000957.SZ", "中通客车"),
        ("002594.SZ", "比亚迪"),
        ("600006.SH", "东风汽车"),
        ("600104.SH", "上汽集团"),
        ("600418.SH", "江淮汽车"),
        ("600686.SH", "金龙汽车"),
        ("601127.SH", "赛力斯"),
        ("601633.SH", "长城汽车"),
    ],
    "白酒": [
        ("000568.SZ", "泸州老窖"),
        ("000596.SZ", "古井贡酒"),
        ("000799.SZ", "酒鬼酒"),
        ("000858.SZ", "五粮液"),
        ("002304.SZ", "洋河股份"),
        ("600519.SH", "贵州茅台"),
        ("600559.SH", "老白干酒"),
        ("600702.SH", "舍得酒业"),
        ("600779.SH", "水井坊"),
        ("603369.SH", "今世缘"),
    ],
    "IT服务": [
        ("000938.SZ", "紫光股份"),
        ("002230.SZ", "科大讯飞"),
        ("002410.SZ", "广联达"),
        ("300033.SZ", "同花顺"),
        ("300168.SZ", "万达信息"),
        ("300212.SZ", "易华录"),
        ("300253.SZ", "卫宁健康"),
        ("300454.SZ", "深信服"),
        ("600570.SH", "恒生电子"),
        ("688111.SH", "金山办公"),
    ],
    "F 批发零售": [
        ("000417.SZ", "合肥百货"),
        ("000785.SZ", "居然之家"),
        ("002024.SZ", "ST易购"),
        ("002419.SZ", "天虹股份"),
        ("600693.SH", "东百集团"),
        ("600697.SH", "欧亚集团"),
        ("600729.SH", "重庆百货"),
        ("600827.SH", "百联股份"),
        ("600859.SH", "王府井"),
        ("601933.SH", "永辉超市"),
    ],
    "批发零售": [
        ("000417.SZ", "合肥百货"),
        ("000785.SZ", "居然之家"),
        ("002024.SZ", "ST易购"),
        ("002419.SZ", "天虹股份"),
        ("600693.SH", "东百集团"),
        ("600697.SH", "欧亚集团"),
        ("600729.SH", "重庆百货"),
        ("600827.SH", "百联股份"),
        ("600859.SH", "王府井"),
        ("601933.SH", "永辉超市"),
    ],
    "G 运输仓储": [
        ("000089.SZ", "深圳机场"),
        ("600009.SH", "上海机场"),
        ("600018.SH", "上港集团"),
        ("600029.SH", "南方航空"),
        ("600115.SH", "中国东航"),
        ("601006.SH", "大秦铁路"),
        ("601111.SH", "中国国航"),
        ("601816.SH", "京沪高铁"),
        ("601872.SH", "招商轮船"),
        ("601919.SH", "中远海控"),
    ],
    "运输仓储": [
        ("000089.SZ", "深圳机场"),
        ("600009.SH", "上海机场"),
        ("600018.SH", "上港集团"),
        ("600029.SH", "南方航空"),
        ("600115.SH", "中国东航"),
        ("601006.SH", "大秦铁路"),
        ("601111.SH", "中国国航"),
        ("601816.SH", "京沪高铁"),
        ("601872.SH", "招商轮船"),
        ("601919.SH", "中远海控"),
    ],
    "航天装备": [
        ("000768.SZ", "中航西飞"),
        ("002025.SZ", "航天电器"),
        ("002179.SZ", "中航光电"),
        ("300775.SZ", "三角防务"),
        ("600118.SH", "中国卫星"),
        ("600316.SH", "洪都航空"),
        ("600760.SH", "中航沈飞"),
        ("600893.SH", "航发动力"),
        ("688586.SH", "江航装备"),
        ("688682.SH", "霍莱沃"),
    ],
    "其他电子": [
        ("000725.SZ", "京东方A"),
        ("002138.SZ", "顺络电子"),
        ("002241.SZ", "歌尔股份"),
        ("002371.SZ", "北方华创"),
        ("002415.SZ", "海康威视"),
        ("002475.SZ", "立讯精密"),
        ("300408.SZ", "三环集团"),
        ("300433.SZ", "蓝思科技"),
        ("600584.SH", "长电科技"),
        ("603986.SH", "兆易创新"),
    ],
    "专业工程": [
        ("002051.SZ", "中工国际"),
        ("002140.SZ", "东华科技"),
        ("002469.SZ", "三维化学"),
        ("002542.SZ", "中化岩土"),
        ("300284.SZ", "苏交科"),
        ("600170.SH", "上海建工"),
        ("600248.SH", "陕建股份"),
        ("600491.SH", "龙元建设"),
        ("601186.SH", "中国铁建"),
        ("601390.SH", "中国中铁"),
    ],
    "综合": [
        ("000009.SZ", "中国宝安"),
        ("000839.SZ", "中信国安"),
        ("000987.SZ", "越秀资本"),
        ("600051.SH", "宁波联合"),
        ("600082.SH", "海泰发展"),
        ("600620.SH", "天宸股份"),
        ("600624.SH", "复旦复华"),
        ("600647.SH", "同达创业"),
        ("600730.SH", "中国高科"),
        ("600811.SH", "东方集团"),
    ],
}


class ShortpickExecutor(Protocol):
    provider_name: str
    model_name: str
    executor_kind: str

    def complete(self, prompt: str) -> str:
        ...


@dataclass(frozen=True)
class StaticShortpickExecutor:
    provider_name: str
    model_name: str
    executor_kind: str
    answer: str

    def complete(self, prompt: str) -> str:
        return self.answer


@dataclass(frozen=True)
class CodexCliShortpickExecutor:
    codex_bin: str
    model_name: str
    provider_name: str = "openai"
    executor_kind: str = "isolated_codex_cli"

    def complete(self, prompt: str) -> str:
        with tempfile.TemporaryDirectory(prefix="ashare-shortpick-codex-") as cwd:
            output_path = Path(cwd) / "answer.txt"
            command = [
                self.codex_bin,
                "exec",
                "-C",
                cwd,
                "--skip-git-repo-check",
                "-s",
                "read-only",
                "-m",
                self.model_name,
                "-o",
                str(output_path),
                "-",
            ]
            completed = subprocess.run(
                command,
                input=prompt,
                text=True,
                capture_output=True,
                check=False,
                timeout=SHORTPICK_CODEX_TIMEOUT_SECONDS,
                env=_isolated_codex_env(),
            )
            if completed.returncode != 0:
                detail = (completed.stderr or completed.stdout or "unknown codex execution error").strip()
                raise RuntimeError(f"isolated Codex shortpick execution failed: {detail}")
            answer = output_path.read_text(encoding="utf-8").strip()
        if not answer:
            raise RuntimeError("isolated Codex shortpick execution returned an empty answer.")
        return answer


@dataclass(frozen=True)
class SearxngSearchClient:
    base_url: str
    timeout_seconds: int = SHORTPICK_SEARXNG_TIMEOUT_SECONDS
    result_limit: int = 5

    def search(self, query: str) -> list[dict[str, Any]]:
        trimmed = query.strip()
        if not trimmed:
            return []
        params = urlencode({"q": trimmed, "format": "json", "language": "zh-CN"})
        http_request = request.Request(
            f"{self.base_url.rstrip('/')}/search?{params}",
            headers={"User-Agent": "ashare-shortpick-lab-lobechat-searxng/1.0"},
        )
        with urlopen(http_request, timeout=self.timeout_seconds, disable_proxies=True) as response:
            payload = json.loads(response.read().decode("utf-8"))
        results: list[dict[str, Any]] = []
        for item in payload.get("results") or []:
            if not isinstance(item, dict):
                continue
            url = _coerce_text(item.get("url"))
            if not url:
                continue
            results.append(
                {
                    "title": _coerce_text(item.get("title")) or url,
                    "url": url,
                    "published_at": _coerce_text(item.get("publishedDate") or item.get("pubdate") or item.get("published_at")),
                    "why_it_matters": _coerce_text(item.get("content") or item.get("metadata") or ""),
                    "search_query": trimmed,
                    "search_engine": _coerce_text(item.get("engine") or ""),
                    "search_score": item.get("score"),
                }
            )
            if len(results) >= self.result_limit:
                break
        return results


@dataclass(frozen=True)
class SogouSearchFallbackClient:
    timeout_seconds: int = SHORTPICK_SEARXNG_TIMEOUT_SECONDS
    result_limit: int = 5

    def search(self, query: str) -> list[dict[str, Any]]:
        trimmed = query.strip()
        if not trimmed:
            return []
        params = urlencode({"query": trimmed})
        http_request = request.Request(
            f"https://www.sogou.com/web?{params}",
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36"
                ),
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.5",
            },
        )
        with urlopen(http_request, timeout=self.timeout_seconds) as response:
            payload = response.read().decode("utf-8", errors="ignore")
        return _parse_sogou_search_results(payload, query=trimmed, limit=self.result_limit)


@dataclass(frozen=True)
class ShortpickSearchFallbackChain:
    primary: SearxngSearchClient
    fallbacks: tuple[Any, ...] = ()

    def search(self, query: str) -> list[dict[str, Any]]:
        errors: list[str] = []
        for client in (self.primary, *self.fallbacks):
            try:
                results = client.search(query)
            except Exception as exc:
                errors.append(f"{client.__class__.__name__}: {str(exc)[:160]}")
                continue
            if results:
                return results
        if errors:
            raise RuntimeError("; ".join(errors))
        return []


def _parse_sogou_search_results(payload: str, *, query: str, limit: int) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for match in re.finditer(r'<div class="vrwrap"[^>]*>.*?</div>\s*</div>', payload, re.S):
        block = match.group(0)
        anchor = re.search(r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', block, re.S)
        if anchor is None:
            continue
        raw_url = html_lib.unescape(anchor.group(1)).strip()
        if not raw_url or raw_url.startswith("javascript:"):
            continue
        if raw_url.startswith("/sogou?"):
            continue
        url = f"https://www.sogou.com{raw_url}" if raw_url.startswith("/") else raw_url
        title = _strip_search_html(anchor.group(2)) or url
        snippet = _strip_search_html(block)
        if not title and not snippet:
            continue
        results.append(
            {
                "title": title,
                "url": url,
                "published_at": _extract_search_date(snippet),
                "why_it_matters": snippet[:600],
                "search_query": query,
                "search_engine": "sogou_web_fallback",
                "search_score": None,
            }
        )
        if len(results) >= limit:
            break
    return results


def _strip_search_html(value: str) -> str:
    text = re.sub(r"<script.*?</script>", " ", value, flags=re.S | re.I)
    text = re.sub(r"<style.*?</style>", " ", text, flags=re.S | re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html_lib.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def _extract_search_date(value: str) -> str | None:
    match = re.search(r"(20\d{2}[-年./]\d{1,2}[-月./]\d{1,2}日?)", value)
    if match:
        return match.group(1)
    return None


@dataclass(frozen=True)
class DeepseekLobeChatSearchShortpickExecutor:
    key_id: int | None
    provider_name: str
    model_name: str
    base_url: str
    api_key: str
    searxng_url: str | None = None
    executor_kind: str = "deepseek_tool_search_lobechat_searxng_v1"
    search_client: SearxngSearchClient | None = None

    def complete(self, prompt: str) -> str:
        transport = OpenAICompatibleTransport()
        search_client = self.search_client or SearxngSearchClient(
            self.searxng_url
            or os.environ.get(SHORTPICK_LOBECHAT_SEARXNG_URL_ENV)
            or SHORTPICK_LOBECHAT_SEARXNG_DEFAULT_URL
        )
        if self.search_client is None:
            search_client = ShortpickSearchFallbackChain(
                primary=search_client,
                fallbacks=(SogouSearchFallbackClient(),),
            )
        plan_raw = transport.complete(
            base_url=self.base_url,
            api_key=self.api_key,
            model_name=self.model_name,
            prompt=_build_deepseek_search_plan_prompt(prompt),
            system=(
                "你正在执行独立 A 股短线研究实验。你当前不能直接联网。"
                "你的任务是先自主决定需要搜索哪些公开信息，不要输出股票推荐，只输出 JSON。"
            ),
        )
        plan = _extract_json_with_one_llm_repair(
            transport=transport,
            base_url=self.base_url,
            api_key=self.api_key,
            model_name=self.model_name,
            raw_answer=plan_raw,
            stage="search_plan_json_repair",
        )
        queries = _coerce_search_queries(plan.get("search_queries") or plan.get("queries"))
        if not queries:
            raise RuntimeError("deepseek search planning produced no search queries.")

        search_results: list[dict[str, Any]] = []
        seen_urls: set[str] = set()
        search_attempts: list[dict[str, Any]] = []
        for query in queries:
            for result in _search_with_retries(search_client, query, attempts=search_attempts):
                url = str(result.get("url") or "").strip()
                if not url or url in seen_urls:
                    continue
                seen_urls.add(url)
                search_results.append(result)

        if len(search_results) < SHORTPICK_DEEPSEEK_MIN_SEARCH_RESULTS:
            for query in _expand_deepseek_queries(queries):
                for result in _search_with_retries(search_client, query, attempts=search_attempts):
                    url = str(result.get("url") or "").strip()
                    if not url or url in seen_urls:
                        continue
                    seen_urls.add(url)
                    search_results.append(result)
                if len(search_results) >= SHORTPICK_DEEPSEEK_MIN_SEARCH_RESULTS:
                    break

        if len(search_results) < SHORTPICK_DEEPSEEK_MIN_SEARCH_RESULTS:
            raise RuntimeError(
                _format_deepseek_search_failure(
                    failure_stage="search_result_scarcity",
                    queries=queries,
                    search_attempts=search_attempts,
                    usable_result_count=len(search_results),
                )
            )

        final_raw = transport.complete(
            base_url=self.base_url,
            api_key=self.api_key,
            model_name=self.model_name,
            prompt=_build_deepseek_final_prompt(prompt=prompt, plan=plan, search_results=search_results),
            system=(
                "你正在执行独立 A 股短线研究实验。不要读取本地项目、数据库、代码库或历史推荐。"
                "你只能基于用户问题和系统提供的公开搜索结果进行分析；sources_used 必须来自这些搜索结果，不能编造 URL。只输出 JSON。"
            ),
        )
        final_answer = _repair_final_answer_json_if_needed(
            transport=transport,
            base_url=self.base_url,
            api_key=self.api_key,
            model_name=self.model_name,
            raw_answer=final_raw,
        )
        return _attach_deepseek_search_trace(
            final_answer,
            plan=plan,
            search_results=search_results,
            search_attempts=search_attempts,
            executor_kind=self.executor_kind,
        )


@dataclass(frozen=True)
class OpenAICompatibleShortpickExecutor:
    key_id: int | None
    provider_name: str
    model_name: str
    base_url: str
    api_key: str
    executor_kind: str = "configured_api_key_native_web_search"

    def complete(self, prompt: str) -> str:
        raise RuntimeError(
            "configured OpenAI-compatible DeepSeek API is not a valid shortpick native-web executor; "
            "DeepSeek official API does not provide web search. Use deepseek_tool_search_lobechat_searxng_v1."
        )


def _isolated_codex_env() -> dict[str, str]:
    env: dict[str, str] = {}
    for key, value in os.environ.items():
        if key.startswith("ASHARE_") or key in {"PYTHONPATH", "DATABASE_URL"}:
            continue
        if key in {"PATH", "HOME", "LANG"} or key.startswith(("LC_", "SSL_")) or key in {
            "HTTP_PROXY",
            "HTTPS_PROXY",
            "ALL_PROXY",
            "NO_PROXY",
        }:
            env[key] = value
    if "PATH" not in env:
        env["PATH"] = "/usr/bin:/bin:/usr/sbin:/sbin"
    return env


def build_shortpick_prompt(*, run_date: date, round_index: int, provider_name: str, model_name: str) -> str:
    return f"""
本会话仅用于研究不同大模型在公开网络信息环境下，对 A 股短线机会进行自由发现的能力，不作为真实交易建议或下单依据。

请不要使用任何本地项目、股票看板数据库、自选池、历史推荐或内部结构化数据。你可以自行使用公开网络信息、搜索、新闻、公告、市场热点、产业信息或其他你认为有价值的公开资料。

任务日期：{run_date.isoformat()}，时区：Asia/Shanghai。
目标市场：中国 A 股全市场。
目标周期：未来 1-10 个交易日。
模型轮次：{provider_name}:{model_name} 第 {round_index} 轮。

请尽量保持独立判断，不需要迎合常规量化框架。你可以选择热点题材、事件催化、资金关注、产业变化、政策变化、公告变化或其他你认为有短线意义的方向。

只输出 JSON，不要加代码块：
{{
  "as_of_date": "{run_date.isoformat()}",
  "information_mode": "native_web_open_discovery",
  "primary_pick": {{
    "symbol": "000000.SZ",
    "name": "...",
    "theme": "...",
    "horizon_trading_days": 5,
    "confidence": 0.0,
    "thesis": "...",
    "catalysts": ["..."],
    "invalidation": ["..."],
    "risks": ["..."]
  }},
  "sources_used": [
    {{
      "title": "...",
      "url": "...",
      "published_at": "...",
      "why_it_matters": "..."
    }}
  ],
  "topic_analysis": {{
    "primary_topic": {{
      "topic_cluster_id": "short_stable_english_slug",
      "label_zh": "中文题材标签",
      "confidence": 0.0,
      "reason": "为什么这个候选属于该题材",
      "supporting_evidence_refs": [0],
      "driver_types": ["policy", "price_change", "earnings", "contract_order", "market_hotspot", "industry_chain"]
    }},
    "secondary_topics": [],
    "new_topic_proposal": null,
    "not_topic_reason": null
  }},
  "topic_verification": {{
    "verdict": "supported",
    "confidence": 0.0,
    "unsupported_claims": [],
    "suggested_topic_cluster_id": null
  }},
  "alternative_picks": [],
  "novelty_note": "这个推荐与常规历史数据/量化视角相比，可能提供的新视角是什么",
  "limitations": ["..."]
}}
""".strip()


def _build_deepseek_search_plan_prompt(prompt: str) -> str:
    return f"""
你将参与一个短投推荐研究实验，但你不能直接联网，也不能读取本地项目或数据库。

请仅基于下面的研究任务，决定你为了完成任务会自主搜索哪些公开网络信息。不要推荐股票，不要编造搜索结果。

输出 JSON，不要加代码块：
{{
  "search_queries": [
    "A股 今日 短线 热点 题材 公开新闻",
    "..."
  ],
  "search_intent": "你为什么选择这些搜索方向",
  "limitations": ["当前回答只生成搜索计划，不代表最终结论"]
}}

研究任务：
{prompt}
""".strip()


def _build_deepseek_final_prompt(*, prompt: str, plan: dict[str, Any], search_results: list[dict[str, Any]]) -> str:
    search_backend = _deepseek_search_backend_label(search_results)
    evidence = {
        "search_plan": plan,
        "search_backend": search_backend,
        "source_policy": "sources_used must be selected only from search_results urls; do not invent urls",
        "search_results": search_results[:20],
    }
    return f"""
请继续完成下面的短投推荐研究任务。

你不能直接联网。以下公开搜索结果来自你上一轮自主规划的搜索查询，由系统通过 LobeChat/SearXNG 执行。你可以自由判断哪些结果有用，也可以在 limitations 中说明搜索结果不足，但最终 sources_used 只能引用 search_results 中真实出现的 URL，不能编造 URL。

搜索证据 JSON：
{json.dumps(evidence, ensure_ascii=False, indent=2)}

研究任务：
{prompt}
""".strip()


def _extract_json_with_one_llm_repair(
    *,
    transport: OpenAICompatibleTransport,
    base_url: str,
    api_key: str,
    model_name: str,
    raw_answer: str,
    stage: str,
) -> dict[str, Any]:
    try:
        return extract_shortpick_json(raw_answer)
    except ValueError:
        repaired = transport.complete(
            base_url=base_url,
            api_key=api_key,
            model_name=model_name,
            prompt=_build_json_repair_prompt(raw_answer, stage=stage),
            system="只修复 JSON 格式，不要新增事实、股票、来源或解释。只输出 JSON。",
        )
        return extract_shortpick_json(repaired)


def _repair_final_answer_json_if_needed(
    *,
    transport: OpenAICompatibleTransport,
    base_url: str,
    api_key: str,
    model_name: str,
    raw_answer: str,
) -> str:
    try:
        extract_shortpick_json(raw_answer)
        return raw_answer
    except ValueError:
        repaired = transport.complete(
            base_url=base_url,
            api_key=api_key,
            model_name=model_name,
            prompt=_build_json_repair_prompt(raw_answer, stage="final_answer_json_repair"),
            system="只修复 JSON 格式，不要新增事实、股票、来源或解释。只输出 JSON。",
        )
        extract_shortpick_json(repaired)
        return repaired


def _build_json_repair_prompt(raw_answer: str, *, stage: str) -> str:
    return f"""
下面内容应该是一个 JSON 对象，但解析失败。请只做格式修复，不要新增或删除事实，不要编造 URL。

阶段：{stage}

原始内容：
{raw_answer[:12000]}
""".strip()


def _search_with_retries(
    search_client: SearxngSearchClient,
    query: str,
    *,
    attempts: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    last_error: str | None = None
    for attempt_index in range(1, SHORTPICK_DEEPSEEK_QUERY_RETRY_ATTEMPTS + 1):
        try:
            results = search_client.search(query)
            attempts.append(
                {
                    "query": query,
                    "attempt": attempt_index,
                    "status": "success",
                    "result_count": len(results),
                }
            )
            return results
        except Exception as exc:  # pragma: no cover - exercised through integration backends.
            last_error = str(exc)[:240]
            attempts.append(
                {
                    "query": query,
                    "attempt": attempt_index,
                    "status": "failed",
                    "error": last_error,
                }
            )
    raise RuntimeError(f"LobeChat/SearXNG query failed after retries: {query}: {last_error}")


def _expand_deepseek_queries(queries: list[str]) -> list[str]:
    expanded: list[str] = []
    for query in queries:
        for suffix in (" 公告 新闻 A股", " 产业链 价格 政策 A股", " 短线 催化 证券"):
            item = f"{query}{suffix}"[:180]
            if item not in queries and item not in expanded:
                expanded.append(item)
        if len(expanded) >= 5:
            break
    return expanded


def _format_deepseek_search_failure(
    *,
    failure_stage: str,
    queries: list[str],
    search_attempts: list[dict[str, Any]],
    usable_result_count: int,
) -> str:
    payload = {
        "failure_stage": failure_stage,
        "usable_result_count": usable_result_count,
        "required_result_count": SHORTPICK_DEEPSEEK_MIN_SEARCH_RESULTS,
        "search_queries": queries,
        "search_attempts": search_attempts,
        "policy": "fail_closed_no_pure_reasoning_fallback",
    }
    return f"LobeChat/SearXNG returned insufficient usable search results: {json.dumps(payload, ensure_ascii=False)}"


def _coerce_search_queries(value: Any) -> list[str]:
    items = value if isinstance(value, list) else []
    queries: list[str] = []
    for item in items:
        text = _coerce_text(item)
        if not text or text in queries:
            continue
        queries.append(text[:180])
        if len(queries) >= 5:
            break
    return queries


def _attach_deepseek_search_trace(
    raw_answer: str,
    *,
    plan: dict[str, Any],
    search_results: list[dict[str, Any]],
    search_attempts: list[dict[str, Any]],
    executor_kind: str,
) -> str:
    parsed = extract_shortpick_json(raw_answer)
    search_backend = _deepseek_search_backend_label(search_results)
    allowed_urls = {str(item.get("url") or "").strip() for item in search_results if item.get("url")}
    used_urls = {
        str(source.get("url") or "").strip()
        for source in (parsed.get("sources_used") if isinstance(parsed.get("sources_used"), list) else [])
        if isinstance(source, dict) and source.get("url")
    }
    unexpected_urls = sorted(url for url in used_urls if url not in allowed_urls)
    if unexpected_urls:
        raise RuntimeError(
            _format_deepseek_search_failure(
                failure_stage="final_source_not_in_search_results",
                queries=_coerce_search_queries(plan.get("search_queries") or plan.get("queries")),
                search_attempts=search_attempts,
                usable_result_count=len(search_results),
            )
            + f"; unexpected_source_urls={unexpected_urls[:5]}"
        )
    parsed["_executor_trace"] = {
        "executor_kind": executor_kind,
        "search_backend": search_backend,
        "search_queries": _coerce_search_queries(plan.get("search_queries") or plan.get("queries")),
        "search_result_count": len(search_results),
        "search_result_urls": [str(item.get("url") or "") for item in search_results[:20] if item.get("url")],
        "search_engines": sorted(
            {
                str(item.get("search_engine") or "unknown")
                for item in search_results
                if item.get("search_engine")
            }
        ),
        "search_attempts": search_attempts,
        "repair_policy": "bounded_repair_fail_closed",
    }
    return json.dumps(parsed, ensure_ascii=False, indent=2)


def _deepseek_search_backend_label(search_results: list[dict[str, Any]]) -> str:
    engines = {str(item.get("search_engine") or "") for item in search_results}
    if "sogou_web_fallback" in engines:
        return "lobechat_searxng_with_sogou_fallback"
    return "lobechat_searxng"


def _shortpick_deepseek_round_timeout_seconds() -> int:
    raw_value = os.getenv(
        "ASHARE_SHORTPICK_DEEPSEEK_ROUND_TIMEOUT_SECONDS",
        str(SHORTPICK_DEEPSEEK_SEARCH_TIMEOUT_SECONDS),
    )
    try:
        return max(1, int(raw_value))
    except ValueError:
        return SHORTPICK_DEEPSEEK_SEARCH_TIMEOUT_SECONDS


def _shortpick_executor_round_timeout_seconds(executor: ShortpickExecutor) -> int | None:
    if executor.executor_kind == "deepseek_tool_search_lobechat_searxng_v1":
        return _shortpick_deepseek_round_timeout_seconds()
    return None


@contextmanager
def _shortpick_executor_round_timeout(executor: ShortpickExecutor):
    timeout_seconds = _shortpick_executor_round_timeout_seconds(executor)
    if timeout_seconds is None or threading.current_thread() is not threading.main_thread():
        yield
        return

    def _raise_timeout(signum: int, frame: Any) -> None:
        raise TimeoutError(f"{executor.executor_kind} round timed out after {timeout_seconds}s.")

    previous_handler = signal.getsignal(signal.SIGALRM)
    signal.signal(signal.SIGALRM, _raise_timeout)
    previous_timer = signal.setitimer(signal.ITIMER_REAL, timeout_seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, previous_timer[0], previous_timer[1])
        signal.signal(signal.SIGALRM, previous_handler)


def default_shortpick_executors(session: Session) -> list[ShortpickExecutor]:
    executors: list[ShortpickExecutor] = []
    builtin = get_builtin_llm_executor_config()
    if builtin.get("enabled") and builtin.get("transport_kind") == "codex_cli" and builtin.get("codex_bin"):
        executors.append(
            CodexCliShortpickExecutor(
                codex_bin=str(builtin["codex_bin"]),
                model_name=str(builtin["model_name"]),
                provider_name=str(builtin.get("provider_name") or "openai"),
            )
        )
    elif builtin.get("enabled") and builtin.get("transport_kind") == "openai_api":
        executors.append(
            OpenAICompatibleShortpickExecutor(
                key_id=None,
                provider_name=str(builtin.get("provider_name") or "openai"),
                model_name=str(builtin["model_name"]),
                base_url=str(builtin["base_url"]),
                api_key=str(builtin["api_key"]),
                executor_kind="builtin_openai_api_native_web",
            )
        )
    deepseek = next(
        (key for key in resolve_llm_key_candidates(session) if "deepseek" in key.provider_name.lower() or "deepseek" in key.base_url.lower()),
        None,
    )
    if deepseek is not None:
        executors.append(_executor_from_key(deepseek))
    return executors


def _executor_from_key(key: ModelApiKey) -> DeepseekLobeChatSearchShortpickExecutor:
    return DeepseekLobeChatSearchShortpickExecutor(
        key_id=key.id,
        provider_name=key.provider_name,
        model_name=key.model_name,
        base_url=key.base_url,
        api_key=key.api_key,
    )


def _should_auto_topic_backfill(executors: list[ShortpickExecutor]) -> bool:
    return any(not isinstance(executor, StaticShortpickExecutor) for executor in executors)


def run_shortpick_experiment(
    session: Session,
    *,
    run_date: date | None = None,
    rounds_per_model: int = 5,
    triggered_by: str | None = None,
    trigger_source: str = "manual_api",
    executors: list[ShortpickExecutor] | None = None,
) -> dict[str, Any]:
    target_date = run_date or datetime.now(UTC).date()
    normalized_rounds = max(1, min(int(rounds_per_model), 10))
    started_at = utcnow()
    run = ShortpickExperimentRun(
        run_key=f"shortpick:{target_date.isoformat()}:{started_at:%Y%m%d%H%M%S%f}",
        run_date=target_date,
        prompt_version=SHORTPICK_PROMPT_VERSION,
        information_mode=SHORTPICK_INFORMATION_MODE,
        status="running",
        trigger_source=trigger_source,
        triggered_by=triggered_by,
        started_at=started_at,
        completed_at=None,
        failed_at=None,
        model_config={
            "rounds_per_model": normalized_rounds,
            "native_web_search": True,
            "controlled_search": False,
            "market_factor_overlay": {
                "enabled": True,
                "frozen_paper_strategy": shortpick_frozen_paper_strategy_contract(),
                "default_family": SHORTPICK_MARKET_FACTOR_DEFAULT_FAMILY,
                "offensive_family": SHORTPICK_MARKET_FACTOR_OFFENSIVE_FAMILY,
                "pool_limit": SHORTPICK_MARKET_FACTOR_POOL_LIMIT,
                "rank_limit": SHORTPICK_MARKET_FACTOR_RANK_LIMIT,
                "consensus_scope": "llm_candidates_only",
            },
        },
        summary_payload={},
    )
    session.add(run)
    session.flush()

    active_executors = executors if executors is not None else default_shortpick_executors(session)
    run.model_config = {
        **dict(run.model_config or {}),
        "models": [
            {
                "provider_name": executor.provider_name,
                "model_name": executor.model_name,
                "executor_kind": executor.executor_kind,
            }
            for executor in active_executors
        ],
    }
    session.commit()
    session.refresh(run)
    if not active_executors:
        run.status = "failed"
        run.failed_at = utcnow()
        run.summary_payload = {"error": "No shortpick executor is available."}
        session.commit()
        session.refresh(run)
        return serialize_shortpick_run(session, run, include_raw=True)

    for executor in active_executors:
        for round_index in range(1, normalized_rounds + 1):
            _execute_shortpick_round(session, run, executor, round_index)

    if _should_auto_topic_backfill(active_executors):
        normalize_shortpick_candidate_topics(session, run_id=run.id)
    consensus = build_shortpick_consensus(session, run)
    llm_paper_control = select_shortpick_llm_paper_control_candidate(session, run)
    market_factor_overlay = insert_shortpick_market_factor_overlay_candidates(session, run)
    validation_result = validate_shortpick_run(session, run.id, horizons=SHORTPICK_DEFAULT_HORIZONS)
    completed_count = session.scalar(
        select(func.count(ShortpickModelRound.id)).where(
            ShortpickModelRound.run_id == run.id,
            ShortpickModelRound.status == "completed",
        )
    ) or 0
    failed_count = session.scalar(
        select(func.count(ShortpickModelRound.id)).where(
            ShortpickModelRound.run_id == run.id,
            ShortpickModelRound.status == "failed",
        )
    ) or 0
    parse_failed_count = session.scalar(
        select(func.count(ShortpickCandidate.id)).where(
            ShortpickCandidate.run_id == run.id,
            ShortpickCandidate.parse_status == "parse_failed",
        )
    ) or 0
    run.status = "completed" if completed_count else "failed"
    run.completed_at = utcnow() if completed_count else None
    run.failed_at = None if completed_count else utcnow()
    run.summary_payload = {
        "completed_round_count": completed_count,
        "failed_round_count": failed_count,
        "parse_failed_count": parse_failed_count,
        "candidate_count": session.scalar(select(func.count(ShortpickCandidate.id)).where(ShortpickCandidate.run_id == run.id)) or 0,
        "consensus_priority": consensus.research_priority,
        "llm_paper_control": llm_paper_control,
        "market_factor_overlay": market_factor_overlay,
        "boundary": "independent_research_lab_no_main_pool_write",
        **dict(validation_result.get("summary") or {}),
    }
    session.commit()
    session.refresh(run)
    return serialize_shortpick_run(session, run, include_raw=True)


def run_shortpick_intraday_same_day_control(
    session: Session,
    *,
    run_date: date | None = None,
    triggered_by: str | None = None,
    trigger_source: str = "scheduled_intraday_cli",
) -> dict[str, Any]:
    """Run the time-boxed same-day entry control without LLM rounds.

    The 14:00 SLA is incompatible with the full multi-model discovery run, so
    this path only runs the already-frozen deterministic market-factor rule and
    a broad realtime quote snapshot.
    """

    target_date = run_date or datetime.now(UTC).date()
    started_at = utcnow()
    run = ShortpickExperimentRun(
        run_key=f"shortpick-intraday-same-day:{target_date.isoformat()}:{started_at:%Y%m%d%H%M%S%f}",
        run_date=target_date,
        prompt_version="intraday_same_day_low_turnover_v1",
        information_mode=SHORTPICK_INFORMATION_MODE,
        status="running",
        trigger_source=trigger_source,
        triggered_by=triggered_by,
        started_at=started_at,
        completed_at=None,
        failed_at=None,
        model_config={
            "rounds_per_model": 0,
            "native_web_search": False,
            "controlled_search": False,
            "market_factor_overlay": {
                "enabled": True,
                "mode": "intraday_same_day_control",
                "frozen_paper_strategy": shortpick_frozen_paper_strategy_contract(),
                "family": SHORTPICK_MARKET_FACTOR_INTRADAY_SAME_DAY_FAMILY,
                "entry_price_source": SHORTPICK_ENTRY_PRICE_SOURCE_INTRADAY,
                "target_publish_time": str(_SHORTPICK_INTRADAY_SAME_DAY_CONFIG["target_publish_time"]),
            },
        },
        summary_payload={},
    )
    session.add(run)
    session.flush()
    try:
        overlay = insert_shortpick_intraday_same_day_candidate(session, run)
        if overlay.get("status") == "failed":
            raise RuntimeError(str(overlay.get("reason") or "intraday same-day control failed"))
        run.status = "completed"
        run.completed_at = utcnow()
        run.failed_at = None
        run.summary_payload = {
            "completed_round_count": 0,
            "failed_round_count": 0,
            "parse_failed_count": 0,
            "candidate_count": session.scalar(select(func.count(ShortpickCandidate.id)).where(ShortpickCandidate.run_id == run.id)) or 0,
            "market_factor_overlay": overlay,
            "boundary": "intraday_same_day_control_no_llm_no_main_pool_write",
        }
    except Exception as exc:
        run.status = "failed"
        run.failed_at = utcnow()
        run.summary_payload = {"error": str(exc), "boundary": "intraday_same_day_control_no_llm_no_main_pool_write"}
    session.commit()
    session.refresh(run)
    return serialize_shortpick_run(session, run, include_raw=True)


def insert_shortpick_intraday_same_day_candidate(session: Session, run: ShortpickExperimentRun) -> dict[str, Any]:
    removed = _delete_existing_market_factor_overlay_candidates(session, run_id=run.id)
    universe_sync = _sync_shortpick_market_factor_universe(session, run.run_date, include_run_date=False)
    quote_snapshot = _fetch_shortpick_intraday_spot_quotes(
        symbols=_shortpick_intraday_universe_symbols(session, run.run_date)
    )
    contexts, diagnostics = _shortpick_market_factor_intraday_contexts(session, run.run_date, quote_snapshot)
    pool = _shortpick_market_factor_pool(contexts)
    if not pool:
        quote_status = str(quote_snapshot.get("status") or "")
        result = {
            "status": "failed" if quote_status in {"error", "unavailable", "empty"} else "skipped",
            "reason": "intraday_quote_unavailable" if quote_status in {"error", "unavailable", "empty"} else "no_intraday_market_factor_pool",
            "removed_existing_candidate_count": removed,
            "market_data_sync": universe_sync,
            "quote_snapshot": quote_snapshot.get("summary", {}),
            **diagnostics,
        }
        run.summary_payload = {**dict(run.summary_payload or {}), "market_factor_overlay": result}
        session.flush()
        return result

    universe_ret10_mean = _mean_or_none([float(item["return_10d"]) for item in contexts])
    breadth10 = _positive_rate([float(item["return_10d"]) for item in contexts])
    pool_ret1_mean = _mean_or_none([float(item["return_1d"]) for item in pool])
    pool_ret10_mean = _mean_or_none([float(item["return_10d"]) for item in pool])
    frozen_gate_pass = bool(
        breadth10 is not None and breadth10 >= SHORTPICK_MARKET_FACTOR_LOW_TURNOVER_UPTREND_BREADTH10_MIN
    )
    regime = {
        "universe_ret10_mean": universe_ret10_mean,
        "breadth10": breadth10,
        "pool_ret1_mean": pool_ret1_mean,
        "pool_ret10_mean": pool_ret10_mean,
        "frozen_paper_gate_pass": frozen_gate_pass,
        "frozen_paper_gate": shortpick_frozen_paper_strategy_contract()["gate"],
        "interpretation": "盘中同日入场对照；只用于比较入场时点，不改变冻结主线。",
    }
    low_turnover_pool = sorted(
        contexts,
        key=lambda item: (float(item["amount"]), float(item["turnover_rate"])),
        reverse=True,
    )[:SHORTPICK_MARKET_FACTOR_LOW_TURNOVER_UPTREND_POOL_LIMIT]
    low_turnover_ranked = [
        item
        for item in _rank_shortpick_market_factor_pool(
            low_turnover_pool,
            family=SHORTPICK_MARKET_FACTOR_LOW_TURNOVER_UPTREND_FAMILY,
        )
        if float(item.get("return_20d") or 0.0) > SHORTPICK_MARKET_FACTOR_LOW_TURNOVER_UPTREND_RETURN20_MIN
    ]
    inserted: list[dict[str, Any]] = []
    excluded_entry_unfillable: list[dict[str, Any]] = []
    if frozen_gate_pass and low_turnover_ranked:
        for source_rank, ranked_item in enumerate(low_turnover_ranked, start=1):
            selected = {
                **ranked_item,
                "_pool_limit_override": SHORTPICK_MARKET_FACTOR_LOW_TURNOVER_UPTREND_POOL_LIMIT,
            }
            entry_quote_snapshot = _fetch_shortpick_intraday_spot_quotes(symbols=[str(selected["symbol"])])
            entry_quote = (entry_quote_snapshot.get("quotes") or {}).get(str(selected["symbol"])) or selected.get(
                "_intraday_selection_quote"
            )
            if isinstance(entry_quote, dict):
                selected["_intraday_entry_quote"] = entry_quote
                selected["_intraday_entry_price"] = entry_quote.get("price") or selected.get("close")
            else:
                selected["_intraday_entry_quote"] = selected.get("_intraday_selection_quote")
                selected["_intraday_entry_price"] = selected.get("close")
            if _is_shortpick_intraday_limit_up_entry_risk(selected):
                excluded_entry_unfillable.append(
                    {
                        "symbol": selected.get("symbol"),
                        "name": selected.get("name"),
                        "source_rank": source_rank,
                        "entry_price": selected.get("_intraday_entry_price"),
                        "previous_close": (
                            selected.get("_intraday_entry_quote", {}).get("previous_close")
                            if isinstance(selected.get("_intraday_entry_quote"), dict)
                            else None
                        ),
                        "reason": "entry_unfillable_limit_up",
                    }
                )
                continue
            candidate = _upsert_shortpick_market_factor_candidate(
                session,
                run=run,
                item=selected,
                family=SHORTPICK_MARKET_FACTOR_INTRADAY_SAME_DAY_FAMILY,
                rank=1,
                pool=low_turnover_pool,
                regime=regime,
                source_rank=source_rank,
                tracking_role=SHORTPICK_MARKET_FACTOR_INTRADAY_SAME_DAY_CONTROL_ROLE,
            )
            inserted.append(
                {
                    "candidate_id": candidate.id,
                    "symbol": candidate.symbol,
                    "name": candidate.name,
                    "baseline_family": SHORTPICK_MARKET_FACTOR_INTRADAY_SAME_DAY_FAMILY,
                    "rank": 1,
                    "source_rank": source_rank,
                    "tracking_role": SHORTPICK_MARKET_FACTOR_INTRADAY_SAME_DAY_CONTROL_ROLE,
                    "entry_price_source": SHORTPICK_ENTRY_PRICE_SOURCE_INTRADAY,
                    "entry_price": selected.get("_intraday_entry_price"),
                    "score": selected.get("_market_factor_score"),
                }
            )
            break
    result = {
        "status": "inserted" if inserted else "skipped",
        "reason": None if inserted else "frozen_gate_or_rank_not_triggered",
        "removed_existing_candidate_count": removed,
        "inserted_candidate_count": len(inserted),
        "pool_limit": SHORTPICK_MARKET_FACTOR_LOW_TURNOVER_UPTREND_POOL_LIMIT,
        "families": [SHORTPICK_MARKET_FACTOR_INTRADAY_SAME_DAY_FAMILY],
        "frozen_paper_strategy": {
            **shortpick_frozen_paper_strategy_contract(),
            "gate_pass": frozen_gate_pass,
            "inserted": bool(inserted),
        },
        "market_factor_paper_controls": shortpick_market_factor_paper_control_contracts(),
        "regime": regime,
        "market_data_sync": universe_sync,
        "quote_snapshot": quote_snapshot.get("summary", {}),
        "excluded_entry_unfillable_count": len(excluded_entry_unfillable),
        "excluded_entry_unfillable": excluded_entry_unfillable[:10],
        "candidates": inserted,
        **diagnostics,
    }
    run.summary_payload = {**dict(run.summary_payload or {}), "market_factor_overlay": result}
    session.flush()
    return result


def _shortpick_intraday_universe_symbols(session: Session, run_date: date) -> list[str]:
    cutoff = datetime.combine(run_date, datetime.min.time()).replace(tzinfo=UTC)
    start_cutoff = datetime.combine(
        run_date - timedelta(days=SHORTPICK_MARKET_FACTOR_FULL_SYNC_LOOKBACK_DAYS),
        datetime.min.time(),
    ).replace(tzinfo=UTC)
    rows = session.execute(
        select(Stock, MarketBar)
        .join(MarketBar, MarketBar.stock_id == Stock.id)
        .where(MarketBar.timeframe == "1d", MarketBar.observed_at >= start_cutoff, MarketBar.observed_at < cutoff)
        .order_by(Stock.symbol.asc(), MarketBar.observed_at.asc(), MarketBar.id.asc())
    ).all()
    bars_by_symbol: dict[str, list[MarketBar]] = defaultdict(list)
    stocks_by_symbol: dict[str, Stock] = {}
    for stock, bar in rows:
        stocks_by_symbol[stock.symbol] = stock
        bars_by_symbol[stock.symbol].append(bar)
    return [
        symbol
        for symbol in sorted(bars_by_symbol)
        if symbol in stocks_by_symbol
        and _stock_eligible_for_shortpick_market_factor(stocks_by_symbol[symbol], run_date=run_date)
        and len(_dedupe_market_factor_bars(bars_by_symbol[symbol])) >= 20
    ]


def _execute_shortpick_round(
    session: Session,
    run: ShortpickExperimentRun,
    executor: ShortpickExecutor,
    round_index: int,
) -> None:
    started_at = utcnow()
    round_record = ShortpickModelRound(
        run_id=run.id,
        round_key=f"{run.run_key}:{executor.provider_name}:{executor.model_name}:{round_index}",
        provider_name=executor.provider_name,
        model_name=executor.model_name,
        executor_kind=executor.executor_kind,
        round_index=round_index,
        status="running",
        raw_answer=None,
        parsed_payload={},
        sources_payload=[],
        artifact_id=None,
        error_message=None,
        started_at=started_at,
        completed_at=None,
    )
    session.add(round_record)
    session.commit()
    round_record_id = round_record.id
    session.refresh(run)
    prompt = build_shortpick_prompt(
        run_date=run.run_date,
        round_index=round_index,
        provider_name=executor.provider_name,
        model_name=executor.model_name,
    )
    raw_answer: str | None = None
    try:
        with _shortpick_executor_round_timeout(executor):
            raw_answer = executor.complete(prompt)
        round_record.raw_answer = raw_answer
        parsed = extract_shortpick_json(raw_answer)
        sources = _normalize_sources(parsed.get("sources_used"))
        source_failure = _web_source_integrity_failure(executor=executor, parsed=parsed, sources=sources)
        if source_failure:
            raise RuntimeError(source_failure)
        round_record.parsed_payload = parsed
        round_record.sources_payload = sources
        round_record.status = "completed"
        round_record.completed_at = utcnow()
        round_record.artifact_id = f"shortpick-round:{round_record.id}"
        _write_round_artifact(session, run, round_record, prompt=prompt)
        _delete_parse_failed_candidates_for_round(session, round_record.id)
        _candidate_from_round(session, run, round_record, parsed, parse_status="parsed")
    except Exception as exc:
        session.rollback()
        round_record = session.get(ShortpickModelRound, round_record_id)
        if round_record is None:
            return
        round_record.status = "failed"
        round_record.error_message = str(exc)
        round_record.completed_at = utcnow()
        round_record.artifact_id = f"shortpick-round:{round_record.id}"
        round_record.raw_answer = raw_answer
        _write_round_artifact(session, run, round_record, prompt=prompt)
        _candidate_from_round(
            session,
            run,
            round_record,
            {
                "primary_pick": {
                    "symbol": "PARSE_FAILED",
                    "name": "解析失败",
                    "theme": "parse_failed",
                    "thesis": str(exc),
                },
                "sources_used": [],
                "limitations": [str(exc)],
            },
            parse_status="parse_failed",
        )
    session.flush()


def extract_shortpick_json(raw_answer: str) -> dict[str, Any]:
    text = raw_answer.strip()
    candidates = [text]
    if "```" in text:
        for block in text.split("```"):
            block = block.strip()
            if not block or block.lower() == "json":
                continue
            candidates.append(block.removeprefix("json").strip())
    first = text.find("{")
    last = text.rfind("}")
    if first >= 0 and last > first:
        candidates.append(text[first : last + 1])
    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    raise ValueError("shortpick answer did not contain a JSON object")


def _web_source_integrity_failure(*, executor: ShortpickExecutor, parsed: dict[str, Any], sources: list[dict[str, Any]]) -> str | None:
    if executor.executor_kind not in {
        "isolated_codex_cli",
        "deepseek_tool_search_lobechat_searxng_v1",
        "configured_api_key_native_web_search",
        "builtin_openai_api_native_web",
    }:
        return None
    if parsed.get("unable_to_search") is True:
        return f"{executor.provider_name} reported it was unable to search."
    if not sources:
        return f"{executor.provider_name} web executor returned no sources."
    status_counts: dict[str, int] = {}
    for source in sources:
        status = str(source.get("credibility_status") or "unchecked")
        status_counts[status] = status_counts.get(status, 0) + 1
    if not any(status in {"verified", "reachable_restricted"} for status in status_counts):
        return f"{executor.provider_name} web executor returned no reachable sources: {status_counts}."
    return None


def _shortpick_failure_category(error_message: str | None) -> str | None:
    if not error_message:
        return None
    normalized = error_message.lower()
    if (
        "searxng returned no usable search results" in normalized
        or "insufficient usable search results" in normalized
        or "final_source_not_in_search_results" in normalized
        or "search planning produced no search queries" in normalized
    ):
        return "retryable_search_failure"
    if "did not contain a json object" in normalized or "parse" in normalized or "json" in normalized:
        return "retryable_parse_failure"
    if "no shortpick executor is available" in normalized or "executor" in normalized and "not available" in normalized:
        return "configuration_failure"
    return "round_execution_failure"


def _round_retryable(round_record: ShortpickModelRound) -> bool:
    return (
        round_record.status == "failed"
        and _shortpick_failure_category(round_record.error_message) in RETRYABLE_FAILURE_CATEGORIES
    )


def _delete_parse_failed_candidates_for_round(session: Session, round_id: int) -> int:
    candidates = session.scalars(
        select(ShortpickCandidate).where(
            ShortpickCandidate.round_id == round_id,
            (ShortpickCandidate.parse_status == "parse_failed") | (ShortpickCandidate.symbol == "PARSE_FAILED"),
        )
    ).all()
    if not candidates:
        return 0
    candidate_ids = [candidate.id for candidate in candidates]
    snapshots = session.scalars(
        select(ShortpickValidationSnapshot).where(ShortpickValidationSnapshot.candidate_id.in_(candidate_ids))
    ).all()
    for snapshot in snapshots:
        session.delete(snapshot)
    for candidate in candidates:
        session.delete(candidate)
    session.flush()
    return len(candidates)


def _cleanup_superseded_parse_failed_candidates(session: Session, *, run_id: int) -> int:
    completed_rounds = session.scalars(
        select(ShortpickModelRound.id).where(
            ShortpickModelRound.run_id == run_id,
            ShortpickModelRound.status == "completed",
        )
    ).all()
    removed = 0
    for round_id in completed_rounds:
        removed += _delete_parse_failed_candidates_for_round(session, int(round_id))
    return removed


def _candidate_from_round(
    session: Session,
    run: ShortpickExperimentRun,
    round_record: ShortpickModelRound,
    parsed: dict[str, Any],
    *,
    parse_status: str,
) -> ShortpickCandidate:
    pick = parsed.get("primary_pick") if isinstance(parsed.get("primary_pick"), dict) else {}
    symbol = _normalize_symbol(str(pick.get("symbol") or "PARSE_FAILED"))
    name = str(pick.get("name") or symbol).strip()[:64] or symbol
    theme = str(pick.get("theme") or _infer_theme(pick) or "").strip() or None
    thesis = _coerce_text(pick.get("thesis"))
    catalysts = _coerce_string_list(pick.get("catalysts"))
    sources_payload = list(round_record.sources_payload or _normalize_sources(parsed.get("sources_used")))
    for source in sources_payload:
        source.update(_source_support_check(source, theme=theme, thesis=thesis, catalysts=catalysts))
    base_candidate_key = f"shortpick-candidate:{round_record.id}"
    existing_count = session.scalar(
        select(func.count(ShortpickCandidate.id)).where(ShortpickCandidate.candidate_key.like(f"{base_candidate_key}%"))
    ) or 0
    candidate = ShortpickCandidate(
        run_id=run.id,
        round_id=round_record.id,
        candidate_key=base_candidate_key if existing_count == 0 else f"{base_candidate_key}:retry-{existing_count + 1}",
        symbol=symbol,
        name=name,
        normalized_theme=theme,
        horizon_trading_days=_coerce_int(pick.get("horizon_trading_days")),
        confidence=_coerce_float(pick.get("confidence")),
        thesis=thesis,
        catalysts=catalysts,
        invalidation=_coerce_string_list(pick.get("invalidation")),
        risks=_coerce_string_list(pick.get("risks")),
        sources_payload=sources_payload,
        novelty_note=_coerce_text(parsed.get("novelty_note")),
        limitations=_coerce_string_list(parsed.get("limitations")),
        convergence_group=None,
        research_priority="pending_consensus",
        parse_status=parse_status,
        is_system_external=_is_system_external(session, symbol),
        candidate_payload={
            "information_mode": parsed.get("information_mode"),
            "alternative_picks": parsed.get("alternative_picks") if isinstance(parsed.get("alternative_picks"), list) else [],
            "topic_normalization": _normalize_shortpick_topic(parsed),
            "model": {
                "provider_name": round_record.provider_name,
                "model_name": round_record.model_name,
                "round_index": round_record.round_index,
            },
        },
    )
    session.add(candidate)
    session.flush()
    return candidate


def insert_shortpick_market_factor_overlay_candidates(session: Session, run: ShortpickExperimentRun) -> dict[str, Any]:
    """Attach the production market-factor strategy candidates to a shortpick run.

    The overlay is inserted after LLM consensus. It is intentionally stored as
    first-class candidates so it can use the same forward validation surface,
    while consensus metrics continue to describe only independent LLM picks.
    """

    universe_sync = _sync_shortpick_market_factor_universe(session, run.run_date)
    removed = _delete_existing_market_factor_overlay_candidates(session, run_id=run.id)
    contexts, diagnostics = _shortpick_market_factor_contexts(session, run.run_date)
    pool = _shortpick_market_factor_pool(contexts)
    if not pool:
        result = {
            "status": "skipped",
            "reason": "no_market_factor_pool",
            "removed_existing_candidate_count": removed,
            "market_data_sync": universe_sync,
            **diagnostics,
        }
        run.summary_payload = {**dict(run.summary_payload or {}), "market_factor_overlay": result}
        session.flush()
        return result

    universe_ret10_mean = _mean_or_none([float(item["return_10d"]) for item in contexts])
    breadth10 = _positive_rate([float(item["return_10d"]) for item in contexts])
    pool_ret1_mean = _mean_or_none([float(item["return_1d"]) for item in pool])
    pool_ret10_mean = _mean_or_none([float(item["return_10d"]) for item in pool])
    regime_gate_pass = bool(
        (breadth10 is not None and breadth10 >= SHORTPICK_MARKET_FACTOR_BREADTH10_THRESHOLD)
        or (pool_ret10_mean is not None and pool_ret10_mean >= SHORTPICK_MARKET_FACTOR_POOL_RET10_THRESHOLD)
    )
    legacy_second_gate_pass = bool(
        universe_ret10_mean is not None
        and universe_ret10_mean >= SHORTPICK_FROZEN_PAPER_UNIVERSE_RET10_MIN
        and pool_ret1_mean is not None
        and pool_ret1_mean <= SHORTPICK_FROZEN_PAPER_POOL_RET1_MAX
    )
    frozen_gate_pass = bool(
        breadth10 is not None and breadth10 >= SHORTPICK_MARKET_FACTOR_LOW_TURNOVER_UPTREND_BREADTH10_MIN
    )
    strong_breadth_rank2_gate_pass = bool(
        breadth10 is not None
        and breadth10 >= SHORTPICK_MARKET_FACTOR_STRONG_BREADTH_RANK2_BREADTH10_MIN
        and pool_ret1_mean is not None
        and pool_ret1_mean <= SHORTPICK_MARKET_FACTOR_STRONG_BREADTH_RANK2_POOL_RET1_MAX
        and pool_ret10_mean is not None
        and pool_ret10_mean >= SHORTPICK_MARKET_FACTOR_STRONG_BREADTH_RANK2_POOL_RET10_MIN
    )
    regime = {
        "universe_ret10_mean": universe_ret10_mean,
        "breadth10": breadth10,
        "pool_ret1_mean": pool_ret1_mean,
        "pool_ret10_mean": pool_ret10_mean,
        "breadth10_threshold": SHORTPICK_MARKET_FACTOR_BREADTH10_THRESHOLD,
        "pool_ret10_threshold": SHORTPICK_MARKET_FACTOR_POOL_RET10_THRESHOLD,
        "gate_pass": regime_gate_pass,
        "frozen_paper_gate_pass": frozen_gate_pass,
        "legacy_second_gate_pass": legacy_second_gate_pass,
        "strong_breadth_rank2_gate_pass": strong_breadth_rank2_gate_pass,
        "strong_breadth_rank2_gate": {
            "breadth10_min": SHORTPICK_MARKET_FACTOR_STRONG_BREADTH_RANK2_BREADTH10_MIN,
            "pool_ret1_max": SHORTPICK_MARKET_FACTOR_STRONG_BREADTH_RANK2_POOL_RET1_MAX,
            "pool_ret10_min": SHORTPICK_MARKET_FACTOR_STRONG_BREADTH_RANK2_POOL_RET10_MIN,
            "source_rank": SHORTPICK_MARKET_FACTOR_STRONG_BREADTH_RANK2_SOURCE_RANK,
        },
        "frozen_paper_gate": shortpick_frozen_paper_strategy_contract()["gate"],
        "interpretation": "仅作仓位/环境诊断，不过滤候选；避免在小样本上过拟合。",
    }
    inserted: list[dict[str, Any]] = []
    frozen_ranked = _rank_shortpick_market_factor_pool(pool, family=SHORTPICK_MARKET_FACTOR_OFFENSIVE_FAMILY)
    low_turnover_pool = sorted(
        contexts,
        key=lambda item: (float(item["amount"]), float(item["turnover_rate"])),
        reverse=True,
    )[:SHORTPICK_MARKET_FACTOR_LOW_TURNOVER_UPTREND_POOL_LIMIT]
    low_turnover_ranked = [
        item
        for item in _rank_shortpick_market_factor_pool(
            low_turnover_pool,
            family=SHORTPICK_MARKET_FACTOR_LOW_TURNOVER_UPTREND_FAMILY,
        )
        if float(item.get("return_20d") or 0.0) > SHORTPICK_MARKET_FACTOR_LOW_TURNOVER_UPTREND_RETURN20_MIN
    ]
    if frozen_gate_pass and low_turnover_ranked:
        frozen_item = {
            **low_turnover_ranked[0],
            "_pool_limit_override": SHORTPICK_MARKET_FACTOR_LOW_TURNOVER_UPTREND_POOL_LIMIT,
        }
        candidate = _upsert_shortpick_market_factor_candidate(
            session,
            run=run,
            item=frozen_item,
            family=SHORTPICK_FROZEN_PAPER_FAMILY,
            rank=1,
            pool=low_turnover_pool,
            regime=regime,
            source_rank=1,
            tracking_role="frozen_paper_primary",
        )
        inserted.append(
            {
                "candidate_id": candidate.id,
                "symbol": candidate.symbol,
                "name": candidate.name,
                "baseline_family": SHORTPICK_FROZEN_PAPER_FAMILY,
                "rank": 1,
                "source_rank": 1,
                "tracking_role": "frozen_paper_primary",
                "score": frozen_item.get("_market_factor_score"),
            }
        )
        open_entry_candidate = _upsert_shortpick_market_factor_candidate(
            session,
            run=run,
            item=frozen_item,
            family=SHORTPICK_MARKET_FACTOR_OPEN_ENTRY_LOW_TURNOVER_FAMILY,
            rank=1,
            pool=low_turnover_pool,
            regime=regime,
            source_rank=1,
            tracking_role=SHORTPICK_MARKET_FACTOR_OPEN_ENTRY_LOW_TURNOVER_CONTROL_ROLE,
        )
        inserted.append(
            {
                "candidate_id": open_entry_candidate.id,
                "symbol": open_entry_candidate.symbol,
                "name": open_entry_candidate.name,
                "baseline_family": SHORTPICK_MARKET_FACTOR_OPEN_ENTRY_LOW_TURNOVER_FAMILY,
                "rank": 1,
                "source_rank": 1,
                "tracking_role": SHORTPICK_MARKET_FACTOR_OPEN_ENTRY_LOW_TURNOVER_CONTROL_ROLE,
                "entry_price_source": SHORTPICK_ENTRY_PRICE_SOURCE_OPEN,
                "score": frozen_item.get("_market_factor_score"),
            }
        )
        no_limit_chase_ranked = [
            (index, item)
            for index, item in enumerate(low_turnover_ranked, start=1)
            if not _is_shortpick_no_limit_chase_risk(item)
        ]
        if no_limit_chase_ranked:
            source_rank, no_limit_chase_raw_item = no_limit_chase_ranked[0]
            no_limit_chase_item = {
                **no_limit_chase_raw_item,
                "_pool_limit_override": SHORTPICK_MARKET_FACTOR_LOW_TURNOVER_UPTREND_POOL_LIMIT,
            }
            candidate = _upsert_shortpick_market_factor_candidate(
                session,
                run=run,
                item=no_limit_chase_item,
                family=SHORTPICK_MARKET_FACTOR_NO_LIMIT_CHASE_LOW_TURNOVER_FAMILY,
                rank=1,
                pool=low_turnover_pool,
                regime=regime,
                source_rank=source_rank,
                tracking_role=SHORTPICK_MARKET_FACTOR_NO_LIMIT_CHASE_LOW_TURNOVER_CONTROL_ROLE,
            )
            inserted.append(
                {
                    "candidate_id": candidate.id,
                    "symbol": candidate.symbol,
                    "name": candidate.name,
                    "baseline_family": SHORTPICK_MARKET_FACTOR_NO_LIMIT_CHASE_LOW_TURNOVER_FAMILY,
                    "rank": 1,
                    "source_rank": source_rank,
                    "tracking_role": SHORTPICK_MARKET_FACTOR_NO_LIMIT_CHASE_LOW_TURNOVER_CONTROL_ROLE,
                    "excluded_return_1d_gte": SHORTPICK_MARKET_FACTOR_NO_LIMIT_CHASE_RETURN1_MAX,
                    "score": no_limit_chase_item.get("_market_factor_score"),
                }
            )
    if legacy_second_gate_pass and len(frozen_ranked) >= 2:
        legacy_item = frozen_ranked[1]
        candidate = _upsert_shortpick_market_factor_candidate(
            session,
            run=run,
            item=legacy_item,
            family="momentum_10d_turnover_legacy_second_candidate",
            rank=1,
            pool=pool,
            regime=regime,
            source_rank=2,
            tracking_role=SHORTPICK_MARKET_FACTOR_LEGACY_SECOND_CONTROL_ROLE,
        )
        inserted.append(
            {
                "candidate_id": candidate.id,
                "symbol": candidate.symbol,
                "name": candidate.name,
                "baseline_family": "momentum_10d_turnover_legacy_second_candidate",
                "rank": 1,
                "source_rank": 2,
                "tracking_role": SHORTPICK_MARKET_FACTOR_LEGACY_SECOND_CONTROL_ROLE,
                "score": legacy_item.get("_market_factor_score"),
            }
        )
    for family in (SHORTPICK_MARKET_FACTOR_DEFAULT_FAMILY, SHORTPICK_MARKET_FACTOR_OFFENSIVE_FAMILY):
        ranked = _rank_shortpick_market_factor_pool(pool, family=family)[:SHORTPICK_MARKET_FACTOR_RANK_LIMIT]
        for rank, item in enumerate(ranked, start=1):
            tracking_role = "control"
            if family == SHORTPICK_MARKET_FACTOR_DEFAULT_FAMILY and rank == 1:
                tracking_role = SHORTPICK_MARKET_FACTOR_COOLDOWN_TOP1_CONTROL_ROLE
            if family == SHORTPICK_MARKET_FACTOR_OFFENSIVE_FAMILY and rank == 1:
                tracking_role = SHORTPICK_MARKET_FACTOR_OFFENSIVE_TOP1_CONTROL_ROLE
            candidate = _upsert_shortpick_market_factor_candidate(
                session,
                run=run,
                item=item,
                family=family,
                rank=rank,
                pool=pool,
                regime=regime,
                tracking_role=tracking_role,
            )
            inserted.append(
                {
                    "candidate_id": candidate.id,
                    "symbol": candidate.symbol,
                    "name": candidate.name,
                    "baseline_family": family,
                    "rank": rank,
                    "tracking_role": tracking_role,
                    "score": item.get("_market_factor_score"),
                }
            )
    random_item = _deterministic_shortpick_market_factor_random_item(pool, run_date=run.run_date)
    if random_item is not None:
        candidate = _upsert_shortpick_market_factor_candidate(
            session,
            run=run,
            item=random_item,
            family=SHORTPICK_MARKET_FACTOR_RANDOM_CONTROL_FAMILY,
            rank=1,
            pool=pool,
            regime=regime,
            source_rank=int(random_item.get("_pool_source_rank") or 1),
            tracking_role=SHORTPICK_MARKET_FACTOR_RANDOM_POOL_CONTROL_ROLE,
        )
        inserted.append(
            {
                "candidate_id": candidate.id,
                "symbol": candidate.symbol,
                "name": candidate.name,
                "baseline_family": SHORTPICK_MARKET_FACTOR_RANDOM_CONTROL_FAMILY,
                "rank": 1,
                "source_rank": int(random_item.get("_pool_source_rank") or 1),
                "tracking_role": SHORTPICK_MARKET_FACTOR_RANDOM_POOL_CONTROL_ROLE,
                "score": random_item.get("_market_factor_score"),
            }
        )
    if frozen_gate_pass:
        top3_ranked = _rank_shortpick_market_factor_pool(pool, family=SHORTPICK_MARKET_FACTOR_OFFENSIVE_FAMILY)[:3]
        if len(top3_ranked) >= 3:
            for rank, item in enumerate(top3_ranked, start=1):
                candidate = _upsert_shortpick_market_factor_candidate(
                    session,
                    run=run,
                    item=item,
                    family="momentum_10d_turnover_top3_equal_weight",
                    rank=rank,
                    pool=pool,
                    regime=regime,
                    source_rank=rank,
                    tracking_role=SHORTPICK_MARKET_FACTOR_TOP3_EQUAL_WEIGHT_CONTROL_ROLE,
                )
                inserted.append(
                    {
                        "candidate_id": candidate.id,
                        "symbol": candidate.symbol,
                        "name": candidate.name,
                        "baseline_family": "momentum_10d_turnover_top3_equal_weight",
                        "rank": rank,
                        "source_rank": rank,
                        "tracking_role": SHORTPICK_MARKET_FACTOR_TOP3_EQUAL_WEIGHT_CONTROL_ROLE,
                        "allocation_weight": round(1.0 / 3.0, 6),
                        "score": item.get("_market_factor_score"),
                    }
                )
    if strong_breadth_rank2_gate_pass:
        strong_ranked = _rank_shortpick_market_factor_pool(pool, family=SHORTPICK_MARKET_FACTOR_STRONG_BREADTH_RANK2_FAMILY)
        if len(strong_ranked) >= SHORTPICK_MARKET_FACTOR_STRONG_BREADTH_RANK2_SOURCE_RANK:
            strong_item = strong_ranked[SHORTPICK_MARKET_FACTOR_STRONG_BREADTH_RANK2_SOURCE_RANK - 1]
            candidate = _upsert_shortpick_market_factor_candidate(
                session,
                run=run,
                item=strong_item,
                family=SHORTPICK_MARKET_FACTOR_STRONG_BREADTH_RANK2_FAMILY,
                rank=1,
                pool=pool,
                regime=regime,
                source_rank=SHORTPICK_MARKET_FACTOR_STRONG_BREADTH_RANK2_SOURCE_RANK,
                tracking_role=SHORTPICK_MARKET_FACTOR_STRONG_BREADTH_RANK2_CONTROL_ROLE,
            )
            inserted.append(
                {
                    "candidate_id": candidate.id,
                    "symbol": candidate.symbol,
                    "name": candidate.name,
                    "baseline_family": SHORTPICK_MARKET_FACTOR_STRONG_BREADTH_RANK2_FAMILY,
                    "rank": 1,
                    "source_rank": SHORTPICK_MARKET_FACTOR_STRONG_BREADTH_RANK2_SOURCE_RANK,
                    "tracking_role": SHORTPICK_MARKET_FACTOR_STRONG_BREADTH_RANK2_CONTROL_ROLE,
                    "score": strong_item.get("_market_factor_score"),
                }
            )
    golden_item = next((item for item in pool if item.get("golden_cross_10_200")), None)
    if golden_item is not None:
        source_rank = int(golden_item.get("_pool_source_rank") or (pool.index(golden_item) + 1))
        golden_item = {
            **golden_item,
            "_market_factor_score": round(1.0 / max(source_rank, 1), 6),
        }
        candidate = _upsert_shortpick_market_factor_candidate(
            session,
            run=run,
            item=golden_item,
            family="momentum_volume_golden_cross_10_200",
            rank=1,
            pool=pool,
            regime=regime,
            source_rank=source_rank,
            tracking_role=SHORTPICK_MARKET_FACTOR_GOLDEN_CROSS_CONTROL_ROLE,
        )
        inserted.append(
            {
                "candidate_id": candidate.id,
                "symbol": candidate.symbol,
                "name": candidate.name,
                "baseline_family": "momentum_volume_golden_cross_10_200",
                "rank": 1,
                "source_rank": source_rank,
                "tracking_role": SHORTPICK_MARKET_FACTOR_GOLDEN_CROSS_CONTROL_ROLE,
                "score": golden_item.get("_market_factor_score"),
            }
        )
    result = {
        "status": "inserted",
        "removed_existing_candidate_count": removed,
        "inserted_candidate_count": len(inserted),
        "pool_limit": SHORTPICK_MARKET_FACTOR_POOL_LIMIT,
        "rank_limit": SHORTPICK_MARKET_FACTOR_RANK_LIMIT,
        "families": [
            SHORTPICK_FROZEN_PAPER_FAMILY,
            SHORTPICK_MARKET_FACTOR_DEFAULT_FAMILY,
            SHORTPICK_MARKET_FACTOR_OFFENSIVE_FAMILY,
            SHORTPICK_MARKET_FACTOR_RANDOM_CONTROL_FAMILY,
            "momentum_10d_turnover_top3_equal_weight",
            "momentum_volume_golden_cross_10_200",
            "momentum_10d_turnover_legacy_second_candidate",
            SHORTPICK_MARKET_FACTOR_STRONG_BREADTH_RANK2_FAMILY,
            SHORTPICK_MARKET_FACTOR_NO_LIMIT_CHASE_LOW_TURNOVER_FAMILY,
            SHORTPICK_MARKET_FACTOR_OPEN_ENTRY_LOW_TURNOVER_FAMILY,
        ],
        "frozen_paper_strategy": {
            **shortpick_frozen_paper_strategy_contract(),
            "gate_pass": frozen_gate_pass,
            "inserted": any(item.get("tracking_role") == "frozen_paper_primary" for item in inserted),
        },
        "market_factor_paper_controls": shortpick_market_factor_paper_control_contracts(),
        "regime": regime,
        "market_data_sync": universe_sync,
        "candidates": inserted,
        **diagnostics,
    }
    run.summary_payload = {**dict(run.summary_payload or {}), "market_factor_overlay": result}
    session.flush()
    return result


def _shortpick_limit_band_for_symbol(symbol: str, name: str | None = None) -> float:
    normalized_name = str(name or "")
    if "ST" in normalized_name.upper():
        return LIMIT_UP_BANDS["st"]
    if symbol.endswith(".BJ"):
        return LIMIT_UP_BANDS["beijing"]
    if symbol.startswith(("300", "301", "688", "689")):
        return LIMIT_UP_BANDS["star_or_chinext"]
    return LIMIT_UP_BANDS["default"]


def _is_shortpick_no_limit_chase_risk(item: dict[str, Any]) -> bool:
    return float(item.get("return_1d") or 0.0) >= SHORTPICK_MARKET_FACTOR_NO_LIMIT_CHASE_RETURN1_MAX


def _is_shortpick_intraday_limit_up_entry_risk(item: dict[str, Any]) -> bool:
    quote = item.get("_intraday_entry_quote")
    if not isinstance(quote, dict):
        quote = item.get("_intraday_selection_quote")
    if not isinstance(quote, dict):
        quote = {}
    entry_price = _coerce_float(quote.get("price")) or _coerce_float(item.get("_intraday_entry_price")) or _coerce_float(
        item.get("close")
    )
    previous_close = _coerce_float(quote.get("previous_close"))
    if previous_close is None:
        return_pct = _coerce_float(quote.get("return_pct"))
        if return_pct is None and entry_price is not None and item.get("return_1d") is not None:
            item_return = _coerce_float(item.get("return_1d"))
            if item_return is not None and item_return > -0.99:
                previous_close = entry_price / (1.0 + item_return)
    limit_band = _shortpick_limit_band_for_symbol(str(item.get("symbol") or ""), str(item.get("name") or ""))
    if entry_price is not None and previous_close is not None and previous_close > 0:
        return (entry_price / previous_close - 1.0) >= limit_band * 0.95
    return_pct = _coerce_float(quote.get("return_pct"))
    if return_pct is not None:
        return (return_pct / 100.0) >= limit_band * 0.95
    return False


def _delete_existing_market_factor_overlay_candidates(session: Session, *, run_id: int) -> int:
    candidates = session.scalars(
        select(ShortpickCandidate).where(
            ShortpickCandidate.run_id == run_id,
            ShortpickCandidate.candidate_key.like(f"shortpick-market-factor:{run_id}:%"),
        )
    ).all()
    if not candidates:
        return 0
    candidate_ids = [candidate.id for candidate in candidates]
    snapshots = session.scalars(
        select(ShortpickValidationSnapshot).where(ShortpickValidationSnapshot.candidate_id.in_(candidate_ids))
    ).all()
    for snapshot in snapshots:
        session.delete(snapshot)
    for candidate in candidates:
        session.delete(candidate)
    session.flush()
    return len(candidates)


def _shortpick_market_factor_contexts(session: Session, run_date: date) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    cutoff = datetime.combine(run_date, datetime.max.time()).replace(tzinfo=UTC)
    start_cutoff = datetime.combine(
        run_date - timedelta(days=SHORTPICK_MARKET_FACTOR_FULL_SYNC_LOOKBACK_DAYS),
        datetime.min.time(),
    ).replace(tzinfo=UTC)
    rows = session.execute(
        select(Stock, MarketBar)
        .join(MarketBar, MarketBar.stock_id == Stock.id)
        .where(MarketBar.timeframe == "1d", MarketBar.observed_at >= start_cutoff, MarketBar.observed_at <= cutoff)
        .order_by(Stock.symbol.asc(), MarketBar.observed_at.asc(), MarketBar.id.asc())
    ).all()
    stocks_by_symbol: dict[str, Stock] = {}
    bars_by_symbol: dict[str, list[MarketBar]] = defaultdict(list)
    for stock, bar in rows:
        stocks_by_symbol[stock.symbol] = stock
        bars_by_symbol[stock.symbol].append(bar)

    contexts: list[dict[str, Any]] = []
    for symbol, bars in bars_by_symbol.items():
        stock = stocks_by_symbol[symbol]
        if not _stock_eligible_for_shortpick_market_factor(stock, run_date=run_date):
            continue
        unique_bars = _dedupe_market_factor_bars(bars)
        if len(unique_bars) < 21:
            continue
        latest = unique_bars[-1]
        if latest.close_price <= 0 or latest.amount <= 0:
            continue
        context = _market_factor_context_from_bars(stock, unique_bars)
        if context is not None:
            contexts.append(context)

    latest_day = max((item["latest_trade_day"] for item in contexts), default=None)
    current_contexts = [item for item in contexts if item["latest_trade_day"] == latest_day] if latest_day else []
    screened_contexts, screen_summary = _shortpick_market_factor_coarse_screen(current_contexts)
    return screened_contexts, {
        "run_date": run_date.isoformat(),
        "latest_trade_day": latest_day,
        "raw_symbol_count": len(bars_by_symbol),
        "eligible_symbol_count": len(screened_contexts),
        "full_eligible_symbol_count": len(current_contexts),
        "stale_symbol_count": max(len(contexts) - len(current_contexts), 0),
        "coarse_screen": screen_summary,
    }


def _shortpick_market_factor_intraday_contexts(
    session: Session,
    run_date: date,
    quote_snapshot: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    cutoff = datetime.combine(run_date, datetime.min.time()).replace(tzinfo=UTC)
    start_cutoff = datetime.combine(
        run_date - timedelta(days=SHORTPICK_MARKET_FACTOR_FULL_SYNC_LOOKBACK_DAYS),
        datetime.min.time(),
    ).replace(tzinfo=UTC)
    rows = session.execute(
        select(Stock, MarketBar)
        .join(MarketBar, MarketBar.stock_id == Stock.id)
        .where(MarketBar.timeframe == "1d", MarketBar.observed_at >= start_cutoff, MarketBar.observed_at < cutoff)
        .order_by(Stock.symbol.asc(), MarketBar.observed_at.asc(), MarketBar.id.asc())
    ).all()
    quotes = quote_snapshot.get("quotes") if isinstance(quote_snapshot.get("quotes"), dict) else {}
    stocks_by_symbol: dict[str, Stock] = {}
    bars_by_symbol: dict[str, list[MarketBar]] = defaultdict(list)
    for stock, bar in rows:
        stocks_by_symbol[stock.symbol] = stock
        bars_by_symbol[stock.symbol].append(bar)

    contexts: list[dict[str, Any]] = []
    missing_quote_count = 0
    for symbol, bars in bars_by_symbol.items():
        stock = stocks_by_symbol[symbol]
        if not _stock_eligible_for_shortpick_market_factor(stock, run_date=run_date):
            continue
        quote = quotes.get(symbol)
        if not isinstance(quote, dict):
            missing_quote_count += 1
            continue
        price = _coerce_float(quote.get("price"))
        amount = _coerce_float(quote.get("amount"))
        if price is None or price <= 0 or amount is None or amount <= 0:
            missing_quote_count += 1
            continue
        unique_bars = _dedupe_market_factor_bars(bars)
        if len(unique_bars) < 20:
            continue
        open_price = _coerce_float(quote.get("open")) or price
        high_price = _coerce_float(quote.get("high")) or max(open_price, price)
        low_price = _coerce_float(quote.get("low")) or min(open_price, price)
        synthetic = MarketBar(
            bar_key=f"synthetic-intraday-{symbol}-{run_date.isoformat()}",
            stock_id=stocks_by_symbol[symbol].id,
            timeframe="1d",
            observed_at=datetime.combine(run_date, datetime.max.time()).replace(tzinfo=UTC),
            open_price=float(open_price),
            high_price=float(high_price),
            low_price=float(low_price),
            close_price=float(price),
            volume=float(_coerce_float(quote.get("volume")) or 0.0),
            amount=float(amount),
            turnover_rate=_coerce_float(quote.get("turnover_rate")),
            raw_payload={"synthetic_intraday_quote": quote},
        )
        context = _market_factor_context_from_bars(stock, [*unique_bars, synthetic])
        if context is None:
            continue
        context["_intraday_selection_quote"] = quote
        context["_intraday_quote_source"] = quote_snapshot.get("source_kind")
        contexts.append(context)

    screened_contexts, screen_summary = _shortpick_market_factor_coarse_screen(contexts)
    return screened_contexts, {
        "run_date": run_date.isoformat(),
        "latest_trade_day": run_date.isoformat(),
        "intraday_quote_status": quote_snapshot.get("status"),
        "intraday_quote_generated_at": quote_snapshot.get("generated_at"),
        "raw_symbol_count": len(bars_by_symbol),
        "eligible_symbol_count": len(screened_contexts),
        "full_eligible_symbol_count": len(contexts),
        "missing_quote_count": missing_quote_count,
        "stale_symbol_count": 0,
        "intraday_same_day": True,
        "coarse_screen": screen_summary,
    }


def _fetch_shortpick_intraday_spot_quotes(*, symbols: Iterable[str] | None = None) -> dict[str, Any]:
    requested_symbols = {str(symbol).strip().upper() for symbol in symbols or [] if str(symbol).strip()}
    generated_at = utcnow().isoformat()
    timeout_seconds = max(
        90,
        int(
            os.getenv(
                "SHORTPICK_INTRADAY_SPOT_TIMEOUT_SECONDS",
                os.getenv("ASHARE_SHORTPICK_INTRADAY_SPOT_TIMEOUT_SECONDS", str(DEFAULT_AKSHARE_TIMEOUT_SECONDS)),
            )
        ),
    )
    if requested_symbols:
        direct_snapshot = _fetch_shortpick_intraday_eastmoney_quotes(
            sorted(requested_symbols),
            generated_at=generated_at,
            timeout_seconds=timeout_seconds,
        )
        if direct_snapshot.get("status") == "ok":
            return direct_snapshot
    if not akshare_runtime_ready():
        return {
            "status": "unavailable",
            "generated_at": generated_at,
            "source_kind": "akshare_stock_zh_a_spot_em",
            "quotes": {},
            "summary": {"status": "unavailable", "reason": "akshare_runtime_not_ready"},
        }
    try:
        frame = call_akshare_function(
            "stock_zh_a_spot_em",
            timeout_seconds=timeout_seconds,
        )
    except Exception as exc:
        return {
            "status": "error",
            "generated_at": generated_at,
            "source_kind": "akshare_stock_zh_a_spot_em",
            "quotes": {},
            "summary": {"status": "error", "reason": str(exc)[:200]},
        }
    if frame is None or getattr(frame, "empty", False):
        return {
            "status": "empty",
            "generated_at": generated_at,
            "source_kind": "akshare_stock_zh_a_spot_em",
            "quotes": {},
            "summary": {"status": "empty", "reason": "spot_quote_frame_empty"},
        }
    quotes: dict[str, dict[str, Any]] = {}
    for row in frame.to_dict(orient="records"):
        symbol = _shortpick_symbol_from_spot_code(row.get("代码") or row.get("code"))
        if symbol is None or (requested_symbols and symbol not in requested_symbols):
            continue
        price = _coerce_float(row.get("最新价") or row.get("price"))
        if price is None or price <= 0:
            continue
        quotes[symbol] = {
            "symbol": symbol,
            "name": row.get("名称") or row.get("name"),
            "price": price,
            "open": _coerce_float(row.get("今开") or row.get("open")),
            "high": _coerce_float(row.get("最高") or row.get("high")),
            "low": _coerce_float(row.get("最低") or row.get("low")),
            "previous_close": _coerce_float(row.get("昨收") or row.get("pre_close")),
            "return_pct": _coerce_float(row.get("涨跌幅") or row.get("pct_chg")),
            "volume": _coerce_float(row.get("成交量") or row.get("volume")),
            "amount": _coerce_float(row.get("成交额") or row.get("amount")),
            "turnover_rate": _coerce_float(row.get("换手率") or row.get("turnover_rate")),
            "captured_at": generated_at,
            "provider": "akshare",
        }
    status = "ok" if quotes else "empty"
    return {
        "status": status,
        "generated_at": generated_at,
        "source_kind": "akshare_stock_zh_a_spot_em",
        "quotes": quotes,
        "summary": {
            "status": status,
            "requested_symbol_count": len(requested_symbols),
            "quote_count": len(quotes),
            "generated_at": generated_at,
            "source_kind": "akshare_stock_zh_a_spot_em",
        },
    }


def _fetch_shortpick_intraday_eastmoney_quotes(
    symbols: list[str],
    *,
    generated_at: str,
    timeout_seconds: int,
) -> dict[str, Any]:
    fields = "f12,f14,f2,f17,f15,f16,f18,f5,f6,f8,f3"
    quotes: dict[str, dict[str, Any]] = {}
    errors: list[str] = []
    for offset in range(0, len(symbols), 80):
        batch = symbols[offset : offset + 80]
        secids = ",".join(_shortpick_eastmoney_secid(symbol) for symbol in batch if _shortpick_eastmoney_secid(symbol))
        if not secids:
            continue
        query = urlencode({"fltt": "2", "invt": "2", "fields": fields, "secids": secids})
        payload: dict[str, Any] | None = None
        for host in ("https://push2.eastmoney.com", "https://push2delay.eastmoney.com"):
            url = f"{host}/api/qt/ulist.np/get?{query}"
            try:
                with urlopen(url, timeout=timeout_seconds, disable_proxies=True) as response:
                    payload = json.loads(response.read().decode("utf-8", errors="replace"))
                break
            except Exception as exc:
                errors.append(f"{host}: {str(exc)[:120]}")
        if payload is None:
            continue
        for row in ((payload.get("data") or {}).get("diff") or []):
            symbol = _shortpick_symbol_from_spot_code(row.get("f12"))
            if symbol is None:
                continue
            price = _coerce_float(row.get("f2"))
            if price is None or price <= 0:
                continue
            quotes[symbol] = {
                "symbol": symbol,
                "name": row.get("f14"),
                "price": price,
                "open": _coerce_float(row.get("f17")),
                "high": _coerce_float(row.get("f15")),
                "low": _coerce_float(row.get("f16")),
                "previous_close": _coerce_float(row.get("f18")),
                "return_pct": _coerce_float(row.get("f3")),
                "volume": _coerce_float(row.get("f5")),
                "amount": _coerce_float(row.get("f6")),
                "turnover_rate": _coerce_float(row.get("f8")),
                "captured_at": generated_at,
                "provider": "eastmoney_push2",
            }
    status = "ok" if quotes else "empty"
    summary: dict[str, Any] = {
        "status": status,
        "requested_symbol_count": len(symbols),
        "quote_count": len(quotes),
        "generated_at": generated_at,
        "source_kind": "eastmoney_push2_ulist_direct",
    }
    if errors:
        summary["errors"] = errors[:3]
    return {
        "status": status,
        "generated_at": generated_at,
        "source_kind": "eastmoney_push2_ulist_direct",
        "quotes": quotes,
        "summary": summary,
    }


def _shortpick_eastmoney_secid(symbol: str) -> str | None:
    code, _, exchange = symbol.partition(".")
    if not re.fullmatch(r"\d{6}", code):
        return None
    if exchange == "SH":
        return f"1.{code}"
    if exchange == "SZ":
        return f"0.{code}"
    return None


def _shortpick_symbol_from_spot_code(raw_code: Any) -> str | None:
    code = str(raw_code or "").strip()
    if not re.fullmatch(r"\d{6}", code):
        return None
    if code.startswith(("4", "8", "9")):
        return f"{code}.BJ"
    if code.startswith(("5", "6", "7")):
        return f"{code}.SH"
    return f"{code}.SZ"


class ShortpickMarketFactorUniverseError(RuntimeError):
    pass


def _shortpick_tushare_credential(session: Session) -> ProviderCredential | None:
    return session.scalar(
        select(ProviderCredential).where(
            ProviderCredential.provider_name == "tushare",
            ProviderCredential.enabled.is_(True),
        )
    )


def _require_shortpick_tushare_credential(session: Session) -> ProviderCredential:
    credential = _shortpick_tushare_credential(session)
    if credential is None or not str(credential.access_token or "").strip():
        raise ShortpickMarketFactorUniverseError("Tushare token is required for full eligible shortpick universe sync.")
    return credential


def _shortpick_symbol_from_tushare_code(raw_code: Any) -> str | None:
    value = str(raw_code or "").strip().upper()
    if not value:
        return None
    ticker, _, exchange = value.partition(".")
    if not re.fullmatch(r"\d{6}", ticker):
        return None
    if exchange in {"SH", "SZ", "BJ"}:
        return f"{ticker}.{exchange}"
    if exchange == "SSE":
        return f"{ticker}.SH"
    if exchange == "SZSE":
        return f"{ticker}.SZ"
    if exchange == "BSE":
        return f"{ticker}.BJ"
    return _shortpick_symbol_from_spot_code(ticker)


def _shortpick_exchange_from_symbol(symbol: str) -> str:
    _, _, exchange = symbol.partition(".")
    return exchange or "SH"


def _shortpick_tushare_stock_profile(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "industry": row.get("industry"),
        "market": row.get("market"),
        "market_board": row.get("market"),
        "exchange": row.get("exchange"),
        "list_status": row.get("list_status"),
        "profile_source": "tushare_stock_basic_full_universe",
    }


def _shortpick_stock_row_eligible(row: dict[str, Any], *, run_date: date) -> bool:
    symbol = _shortpick_symbol_from_tushare_code(row.get("ts_code"))
    if symbol is None:
        return False
    profile = {
        "name": row.get("name"),
        "listed_date": _parse_day(row.get("list_date")),
        "profile_payload": _shortpick_tushare_stock_profile(row),
    }
    eligibility = account_trade_eligibility(
        symbol,
        stock_profile=profile,
        account_profile=ACCOUNT_PROFILE_NEW_RETAIL_CASH,
        as_of=run_date,
    )
    return bool(eligibility["tradable"])


def _upsert_shortpick_tushare_stock(session: Session, row: dict[str, Any], *, run_date: date) -> Stock | None:
    symbol = _shortpick_symbol_from_tushare_code(row.get("ts_code"))
    if symbol is None:
        return None
    if symbol in SHORTPICK_MARKET_FACTOR_EXCLUDED_SYMBOLS:
        return None
    name = str(row.get("name") or symbol).strip()
    listed_date = _parse_day(row.get("list_date"))
    profile_payload = _shortpick_tushare_stock_profile(row)
    if not _shortpick_stock_row_eligible(row, run_date=run_date):
        return None

    existing = session.scalar(select(Stock).where(Stock.symbol == symbol))
    ticker = symbol.split(".", 1)[0]
    exchange = _shortpick_exchange_from_symbol(symbol)
    stock_payload = {
        "symbol": symbol,
        "name": name,
        "listed_date": listed_date.isoformat() if listed_date else None,
        "profile_payload": profile_payload,
    }
    lineage = build_lineage(
        stock_payload,
        source_uri=f"tushare://stock_basic/{symbol}",
        license_tag="tushare-pro",
        usage_scope="internal_research",
        redistribution_scope="limited-display",
    )
    if existing is None:
        stock = Stock(
            symbol=symbol,
            ticker=ticker,
            exchange=exchange,
            name=name,
            provider_symbol=symbol,
            listed_date=listed_date,
            delisted_date=None,
            status="active",
            profile_payload=profile_payload,
            **lineage,
        )
        session.add(stock)
        session.flush()
        return stock

    existing.ticker = ticker
    existing.exchange = exchange
    existing.name = name
    existing.provider_symbol = symbol
    existing.listed_date = listed_date
    existing.delisted_date = None
    existing.status = "active"
    existing.profile_payload = {**dict(existing.profile_payload or {}), **profile_payload}
    for key, value in lineage.items():
        setattr(existing, key, value)
    session.flush()
    return existing


def _sync_shortpick_tushare_stock_master(session: Session, run_date: date) -> tuple[list[Stock], dict[str, Any]]:
    _require_shortpick_tushare_credential(session)
    rows = _tushare_rows(
        session,
        api_name="stock_basic",
        params={"list_status": "L"},
        fields="ts_code,symbol,name,industry,list_date,exchange,market,list_status",
    )
    if not rows:
        raise ShortpickMarketFactorUniverseError("Tushare stock_basic returned no rows for full eligible universe.")

    eligible: list[Stock] = []
    excluded_count = 0
    for row in rows:
        if _shortpick_stock_row_eligible(row, run_date=run_date):
            stock = _upsert_shortpick_tushare_stock(session, row, run_date=run_date)
            if stock is not None and _stock_eligible_for_shortpick_market_factor(stock, run_date=run_date):
                eligible.append(stock)
        else:
            excluded_count += 1
    session.flush()
    unique = {stock.symbol: stock for stock in eligible}
    eligible = [unique[symbol] for symbol in sorted(unique)]
    if len(eligible) < SHORTPICK_MARKET_FACTOR_MIN_FULL_UNIVERSE_SIZE:
        raise ShortpickMarketFactorUniverseError(
            "Full eligible shortpick universe is unexpectedly small: "
            f"{len(eligible)} < {SHORTPICK_MARKET_FACTOR_MIN_FULL_UNIVERSE_SIZE}."
        )
    return eligible, {
        "tushare_stock_basic_rows": len(rows),
        "account_eligible_symbol_count": len(eligible),
        "excluded_symbol_count": excluded_count,
    }


def _shortpick_recent_tushare_trade_dates(session: Session, run_date: date, *, include_run_date: bool) -> list[date]:
    start_date = run_date - timedelta(days=SHORTPICK_MARKET_FACTOR_FULL_SYNC_LOOKBACK_DAYS)
    rows = _tushare_rows(
        session,
        api_name="trade_cal",
        params={
            "exchange": "SSE",
            "start_date": start_date.strftime("%Y%m%d"),
            "end_date": run_date.strftime("%Y%m%d"),
        },
        fields="exchange,cal_date,is_open,pretrade_date",
    )
    if not rows:
        raise ShortpickMarketFactorUniverseError("Tushare trade_cal returned no rows for full universe sync.")
    days = []
    for row in rows:
        if str(row.get("is_open")) not in {"1", "1.0", "True", "true"} and row.get("is_open") != 1:
            continue
        trade_day = _parse_day(row.get("cal_date"))
        if trade_day is None:
            continue
        if not include_run_date and trade_day >= run_date:
            continue
        if include_run_date and trade_day > run_date:
            continue
        days.append(trade_day)
    days = sorted(set(days))
    if len(days) < 21:
        raise ShortpickMarketFactorUniverseError(f"Tushare trade calendar only returned {len(days)} open days.")
    return days[-max(21, SHORTPICK_MARKET_FACTOR_FULL_SYNC_MIN_TRADE_DAYS) :]


def _existing_shortpick_bar_count_for_day(session: Session, *, trade_day: date, stock_ids: set[int]) -> int:
    if not stock_ids:
        return 0
    observed_at = _close_timestamp(trade_day)
    total = 0
    stock_id_list = sorted(stock_ids)
    for offset in range(0, len(stock_id_list), 800):
        chunk = stock_id_list[offset : offset + 800]
        total += (
            session.scalar(
                select(func.count(MarketBar.id)).where(
                    MarketBar.timeframe == "1d",
                    MarketBar.observed_at == observed_at,
                    MarketBar.stock_id.in_(chunk),
                )
            )
            or 0
        )
    return total


def _bulk_upsert_shortpick_market_bars(
    session: Session,
    *,
    stocks_by_symbol: dict[str, Stock],
    market_rows: list[dict[str, Any]],
    basic_rows: list[dict[str, Any]],
    trade_day: date,
) -> int:
    basic_by_symbol: dict[str, dict[str, Any]] = {}
    for row in basic_rows:
        symbol = _shortpick_symbol_from_tushare_code(row.get("ts_code"))
        if symbol:
            basic_by_symbol[symbol] = row

    records: list[tuple[str, dict[str, Any]]] = []
    for row in market_rows:
        symbol = _shortpick_symbol_from_tushare_code(row.get("ts_code"))
        stock = stocks_by_symbol.get(symbol or "")
        if stock is None:
            continue
        open_price = _to_float(row.get("open"))
        high_price = _to_float(row.get("high"))
        low_price = _to_float(row.get("low"))
        close_price = _to_float(row.get("close"))
        volume = _to_float(row.get("vol"))
        amount = _to_float(row.get("amount"))
        if None in {open_price, high_price, low_price, close_price, volume, amount}:
            continue
        basic = basic_by_symbol.get(symbol or "", {})
        ticker = stock.ticker or str(symbol).split(".", 1)[0]
        bar_key = f"bar-{ticker.lower()}-1d-{trade_day:%Y%m%d}"
        raw_payload = {
            **_json_safe(row),
            "daily_basic": _json_safe(basic),
            "provider_name": "tushare",
            "dataset": "daily+daily_basic",
            "shortpick_full_universe_sync": True,
        }
        values = {
            "stock_id": stock.id,
            "timeframe": "1d",
            "observed_at": _close_timestamp(trade_day),
            "open_price": float(open_price),
            "high_price": float(high_price),
            "low_price": float(low_price),
            "close_price": float(close_price),
            "volume": float(volume),
            "amount": float(amount) * 1000.0,
            "turnover_rate": ((_to_float(basic.get("turnover_rate")) or 0.0) / 100.0) if basic else None,
            "adj_factor": None,
            "total_mv": _to_float(basic.get("total_mv")),
            "circ_mv": _to_float(basic.get("circ_mv")),
            "pe_ttm": _to_float(basic.get("pe_ttm")),
            "pb": _to_float(basic.get("pb")),
            "raw_payload": raw_payload,
            **build_lineage(
                {"symbol": symbol, "trade_date": trade_day.isoformat(), "raw_payload": raw_payload},
                source_uri=f"tushare://daily/{symbol}?trade_date={trade_day:%Y%m%d}",
                license_tag="tushare-pro",
                usage_scope="internal_research",
                redistribution_scope="limited-display",
            ),
        }
        records.append((bar_key, values))

    existing_by_key: dict[str, MarketBar] = {}
    keys = [key for key, _ in records]
    for offset in range(0, len(keys), 800):
        chunk = keys[offset : offset + 800]
        existing_by_key.update({bar.bar_key: bar for bar in session.scalars(select(MarketBar).where(MarketBar.bar_key.in_(chunk))).all()})

    upserted = 0
    for bar_key, values in records:
        existing = existing_by_key.get(bar_key)
        if existing is None:
            session.add(MarketBar(bar_key=bar_key, **values))
        else:
            for key, value in values.items():
                setattr(existing, key, value)
        upserted += 1
    session.flush()
    return upserted


def _sync_shortpick_tushare_market_bars(
    session: Session,
    *,
    run_date: date,
    eligible_stocks: list[Stock],
    include_run_date: bool,
) -> dict[str, Any]:
    trade_days = _shortpick_recent_tushare_trade_dates(session, run_date, include_run_date=include_run_date)
    stocks_by_symbol = {stock.symbol: stock for stock in eligible_stocks}
    stock_ids = {int(stock.id) for stock in eligible_stocks if stock.id is not None}
    refreshed_days: list[str] = []
    skipped_days = 0
    total_upserted = 0
    expected_floor = max(1, int(len(eligible_stocks) * 0.85))
    for trade_day in trade_days:
        existing_count = _existing_shortpick_bar_count_for_day(session, trade_day=trade_day, stock_ids=stock_ids)
        if existing_count >= expected_floor:
            skipped_days += 1
            continue
        trade_date = trade_day.strftime("%Y%m%d")
        market_rows = _tushare_rows(
            session,
            api_name="daily",
            params={"trade_date": trade_date},
            fields="ts_code,trade_date,open,high,low,close,vol,amount",
        )
        basic_rows = _tushare_rows(
            session,
            api_name="daily_basic",
            params={"trade_date": trade_date},
            fields="ts_code,trade_date,turnover_rate,total_mv,circ_mv,pe_ttm,pb",
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
        total_upserted += upserted
        refreshed_days.append(trade_day.isoformat())
        session.commit()

    return {
        "trade_day_count": len(trade_days),
        "trade_day_start": trade_days[0].isoformat() if trade_days else None,
        "trade_day_end": trade_days[-1].isoformat() if trade_days else None,
        "skipped_current_day_count": skipped_days,
        "skipped_current_count": skipped_days,
        "refreshed_day_count": len(refreshed_days),
        "refreshed_days": refreshed_days[-10:],
        "upserted_bar_count": total_upserted,
    }


def _sync_shortpick_market_factor_universe(session: Session, run_date: date, *, include_run_date: bool = True) -> dict[str, Any]:
    if os.getenv("SHORTPICK_MARKET_FACTOR_SYNC", "1").strip().lower() in {"0", "false", "no"}:
        return {"status": "disabled"}
    eligible, stock_master_summary = _sync_shortpick_tushare_stock_master(session, run_date)
    session.commit()
    bar_summary = _sync_shortpick_tushare_market_bars(
        session,
        run_date=run_date,
        eligible_stocks=eligible,
        include_run_date=include_run_date,
    )
    return {
        "status": "ok",
        "source": "tushare_full_eligible_new_retail_cash_mainboard",
        "target_date": run_date.isoformat(),
        "include_run_date": include_run_date,
        "eligible_symbol_count": len(eligible),
        "minimum_required_eligible_symbol_count": SHORTPICK_MARKET_FACTOR_MIN_FULL_UNIVERSE_SIZE,
        **stock_master_summary,
        **bar_summary,
    }


def _stock_eligible_for_shortpick_market_factor(stock: Stock, *, run_date: date) -> bool:
    symbol = str(stock.symbol or "").upper()
    ticker = symbol.split(".", 1)[0]
    if symbol in SHORTPICK_MARKET_FACTOR_EXCLUDED_SYMBOLS:
        return False
    if not symbol.endswith((".SH", ".SZ", ".BJ")) or not ticker.isdigit() or len(ticker) != 6:
        return False
    if stock.status and stock.status != "active":
        return False
    if stock.delisted_date is not None and stock.delisted_date <= run_date:
        return False
    name = str(stock.name or "").upper()
    if "ST" in name or "退" in name:
        return False
    eligibility = account_trade_eligibility(
        stock.symbol,
        stock_profile=stock,
        account_profile=ACCOUNT_PROFILE_NEW_RETAIL_CASH,
        as_of=run_date,
    )
    return bool(eligibility["tradable"])


def _dedupe_market_factor_bars(bars: list[MarketBar]) -> list[MarketBar]:
    by_day: dict[date, MarketBar] = {}
    for bar in bars:
        by_day[bar.observed_at.date()] = bar
    return [by_day[day] for day in sorted(by_day)]


def _market_factor_context_from_bars(stock: Stock, bars: list[MarketBar]) -> dict[str, Any] | None:
    latest = bars[-1]
    previous = bars[-2]
    five_back = bars[-6]
    ten_back = bars[-11]
    twenty_back = bars[-21]
    if previous.close_price <= 0 or five_back.close_price <= 0 or ten_back.close_price <= 0 or twenty_back.close_price <= 0:
        return None
    return_1d = (latest.close_price / previous.close_price) - 1
    profile = stock.profile_payload if isinstance(stock.profile_payload, dict) else {}
    turnover_rate = latest.turnover_rate
    if turnover_rate is None:
        turnover_rate = 0.0
    context = {
        "symbol": stock.symbol,
        "name": stock.name,
        "industry": profile.get("industry") or profile.get("sector") or "",
        "latest_trade_day": latest.observed_at.date().isoformat(),
        "close": float(latest.close_price),
        "amount": float(latest.amount or 0.0),
        "turnover_rate": float(turnover_rate or 0.0),
        "return_1d": return_1d,
        "return_5d": (latest.close_price / five_back.close_price) - 1,
        "return_10d": (latest.close_price / ten_back.close_price) - 1,
        "return_20d": (latest.close_price / twenty_back.close_price) - 1,
        "abs_return_1d": abs(return_1d),
        "bars": len(bars),
        **_shortpick_golden_cross_features(bars, short_window=10, long_window=200),
    }
    if any(
        not math.isfinite(float(context[key]))
        for key in ("amount", "turnover_rate", "return_1d", "return_5d", "return_10d", "return_20d", "abs_return_1d")
    ):
        return None
    return context


def _shortpick_context_industry(item: dict[str, Any]) -> str:
    value = str(item.get("industry") or "").strip()
    return value if value else "未分类"


def _shortpick_manual_focus_industry_keywords() -> list[str]:
    raw = os.getenv("SHORTPICK_MARKET_FACTOR_FOCUS_INDUSTRIES", "").strip()
    if not raw:
        return []
    return [token.strip().lower() for token in re.split(r"[,，;；\\s]+", raw) if token.strip()]


def _shortpick_metric_rank_maps(contexts: list[dict[str, Any]], keys: Iterable[str]) -> dict[str, dict[str, float]]:
    result: dict[str, dict[str, float]] = {}
    for key in keys:
        values: list[tuple[str, float]] = []
        for item in contexts:
            value = item.get(key)
            if value is None:
                continue
            numeric = float(value)
            if math.isfinite(numeric):
                values.append((str(item["symbol"]), numeric))
        values.sort(key=lambda row: row[1])
        if len(values) <= 1:
            result[key] = {symbol: 0.5 for symbol, _ in values}
            continue
        ranks: dict[str, float] = {}
        denominator = float(len(values) - 1)
        for index, (symbol, _) in enumerate(values):
            ranks[symbol] = round(index / denominator, 6)
        result[key] = ranks
    return result


def _shortpick_market_factor_coarse_screen(contexts: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Reduce the full eligible universe to a deterministic research candidate set.

    The full 2999-ish new-retail eligible universe remains the source of truth.
    This stage only limits downstream strategy/backtest work by selecting hot
    industries plus liquidity/momentum reserves, all using same-day available
    market data.
    """

    full_count = len(contexts)
    cap = max(SHORTPICK_MARKET_FACTOR_LOW_TURNOVER_UPTREND_POOL_LIMIT, SHORTPICK_MARKET_FACTOR_COARSE_SCREEN_SIZE)
    if full_count <= cap:
        return contexts, {
            "coarse_screen_enabled": False,
            "coarse_screen_reason": "full_universe_within_cap",
            "coarse_screen_size": full_count,
            "coarse_screen_cap": cap,
            "full_eligible_symbol_count": full_count,
            "hot_industries": [],
        }

    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in contexts:
        groups[_shortpick_context_industry(item)].append(item)

    industry_scores: list[dict[str, Any]] = []
    for industry, items in groups.items():
        if len(items) < SHORTPICK_MARKET_FACTOR_HOT_INDUSTRY_MIN_SYMBOLS:
            continue
        ret10_values = [float(item["return_10d"]) for item in items]
        ret5_values = [float(item["return_5d"]) for item in items]
        amount_values = [float(item["amount"]) for item in items]
        breadth10 = _positive_rate(ret10_values) or 0.0
        score = (sum(ret10_values) / len(ret10_values)) + 0.5 * (sum(ret5_values) / len(ret5_values)) + 0.05 * breadth10
        industry_scores.append(
            {
                "industry": industry,
                "symbol_count": len(items),
                "score": round(score, 6),
                "return_10d_mean": round(sum(ret10_values) / len(ret10_values), 6),
                "return_5d_mean": round(sum(ret5_values) / len(ret5_values), 6),
                "breadth10": round(breadth10, 6),
                "amount_mean": round(sum(amount_values) / len(amount_values), 2),
            }
        )
    industry_scores.sort(
        key=lambda item: (
            float(item["score"]),
            float(item["breadth10"]),
            float(item["amount_mean"]),
            int(item["symbol_count"]),
        ),
        reverse=True,
    )
    hot_industries = [str(item["industry"]) for item in industry_scores[:SHORTPICK_MARKET_FACTOR_HOT_INDUSTRY_LIMIT]]
    focus_keywords = _shortpick_manual_focus_industry_keywords()

    selected_symbols: set[str] = set()
    for item in contexts:
        industry = _shortpick_context_industry(item)
        industry_lower = industry.lower()
        if industry in hot_industries or any(keyword in industry_lower for keyword in focus_keywords):
            selected_symbols.add(str(item["symbol"]))

    reserve = max(100, cap // 4)
    selected_symbols.update(str(item["symbol"]) for item in sorted(contexts, key=lambda item: float(item["amount"]), reverse=True)[:reserve])
    selected_symbols.update(str(item["symbol"]) for item in sorted(contexts, key=lambda item: float(item["return_10d"]), reverse=True)[:reserve])
    selected_symbols.update(str(item["symbol"]) for item in sorted(contexts, key=lambda item: float(item["return_20d"]), reverse=True)[:reserve])

    rank_maps = _shortpick_metric_rank_maps(contexts, ("amount", "return_10d", "return_20d", "turnover_rate", "abs_return_1d"))
    scored: list[dict[str, Any]] = []
    for item in contexts:
        symbol = str(item["symbol"])
        industry_bonus = 0.15 if _shortpick_context_industry(item) in hot_industries else 0.0
        focus_bonus = 0.10 if focus_keywords and any(keyword in _shortpick_context_industry(item).lower() for keyword in focus_keywords) else 0.0
        low_abs_ret1_rank = 1.0 - rank_maps.get("abs_return_1d", {}).get(symbol, 0.5)
        score = (
            0.30 * rank_maps.get("return_20d", {}).get(symbol, 0.5)
            + 0.25 * rank_maps.get("return_10d", {}).get(symbol, 0.5)
            + 0.25 * rank_maps.get("amount", {}).get(symbol, 0.5)
            + 0.10 * low_abs_ret1_rank
            + industry_bonus
            + focus_bonus
        )
        scored.append(
            {
                **item,
                "_coarse_screen_score": round(score, 6),
                "_coarse_screen_industry_hot": _shortpick_context_industry(item) in hot_industries,
                "_coarse_screen_initial_match": symbol in selected_symbols,
            }
        )

    scored.sort(
        key=lambda item: (
            bool(item.get("_coarse_screen_initial_match")),
            float(item["_coarse_screen_score"]),
            float(item["return_20d"]),
            float(item["amount"]),
            str(item["symbol"]),
        ),
        reverse=True,
    )
    screened = scored[:cap]
    return screened, {
        "coarse_screen_enabled": True,
        "coarse_screen_method": "hot_industry_plus_liquidity_momentum_reserves_v1",
        "coarse_screen_cap": cap,
        "coarse_screen_size": len(screened),
        "full_eligible_symbol_count": full_count,
        "hot_industry_limit": SHORTPICK_MARKET_FACTOR_HOT_INDUSTRY_LIMIT,
        "hot_industry_min_symbols": SHORTPICK_MARKET_FACTOR_HOT_INDUSTRY_MIN_SYMBOLS,
        "hot_industries": industry_scores[:SHORTPICK_MARKET_FACTOR_HOT_INDUSTRY_LIMIT],
        "manual_focus_industry_keywords": focus_keywords,
    }


def _shortpick_market_factor_pool(contexts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ranked = sorted(
        contexts,
        key=lambda item: (
            float(item["return_1d"]),
            float(item["amount"]),
            float(item["turnover_rate"]),
            float(item["return_10d"]),
        ),
        reverse=True,
    )
    return [
        {
            **item,
            "_pool_source_rank": index,
        }
        for index, item in enumerate(ranked[:SHORTPICK_MARKET_FACTOR_POOL_LIMIT], start=1)
    ]


def _shortpick_golden_cross_features(bars: list[MarketBar], *, short_window: int, long_window: int) -> dict[str, Any]:
    current_index = len(bars) - 1
    if current_index < long_window:
        return {
            "golden_cross_10_200": False,
            "ma10": None,
            "ma200": None,
            "previous_ma10": None,
            "previous_ma200": None,
        }
    current_short = _shortpick_bar_moving_average(bars, current_index, short_window)
    current_long = _shortpick_bar_moving_average(bars, current_index, long_window)
    previous_short = _shortpick_bar_moving_average(bars, current_index - 1, short_window)
    previous_long = _shortpick_bar_moving_average(bars, current_index - 1, long_window)
    golden_cross = (
        current_short is not None
        and current_long is not None
        and previous_short is not None
        and previous_long is not None
        and current_short > current_long
        and previous_short <= previous_long
    )
    return {
        "golden_cross_10_200": golden_cross,
        "ma10": current_short,
        "ma200": current_long,
        "previous_ma10": previous_short,
        "previous_ma200": previous_long,
    }


def _shortpick_bar_moving_average(bars: list[MarketBar], index: int, window: int) -> float | None:
    if index - window + 1 < 0:
        return None
    closes = [float(bar.close_price) for bar in bars[index - window + 1 : index + 1] if bar.close_price > 0]
    if len(closes) != window:
        return None
    return sum(closes) / float(window)


def _rank_shortpick_market_factor_pool(pool: list[dict[str, Any]], *, family: str) -> list[dict[str, Any]]:
    ranked: list[dict[str, Any]] = []
    for item in pool:
        scored = dict(item)
        ret10_rank = _rank_percentile(pool, "return_10d", item)
        ret20_rank = _rank_percentile(pool, "return_20d", item)
        amount_rank = _rank_percentile(pool, "amount", item)
        turnover_rank = _rank_percentile(pool, "turnover_rate", item)
        ret1_rank = _rank_percentile(pool, "return_1d", item)
        low_abs_ret1_rank = 1.0 - _rank_percentile(pool, "abs_return_1d", item)
        score = ret10_rank + turnover_rank
        if family == SHORTPICK_MARKET_FACTOR_DEFAULT_FAMILY:
            score -= SHORTPICK_MARKET_FACTOR_COOLDOWN_RET1_PENALTY * ret1_rank
        if family == SHORTPICK_MARKET_FACTOR_STRONG_BREADTH_RANK2_FAMILY:
            score = (
                SHORTPICK_MARKET_FACTOR_STRONG_BREADTH_RANK2_RET10_WEIGHT * ret10_rank
                + SHORTPICK_MARKET_FACTOR_STRONG_BREADTH_RANK2_AMOUNT_WEIGHT * amount_rank
                + SHORTPICK_MARKET_FACTOR_STRONG_BREADTH_RANK2_TURNOVER_WEIGHT * turnover_rank
                - SHORTPICK_MARKET_FACTOR_STRONG_BREADTH_RANK2_RET1_PENALTY * ret1_rank
            )
        if family == SHORTPICK_MARKET_FACTOR_LOW_TURNOVER_UPTREND_FAMILY:
            score = (
                SHORTPICK_MARKET_FACTOR_LOW_TURNOVER_UPTREND_RET20_WEIGHT * ret20_rank
                + SHORTPICK_MARKET_FACTOR_LOW_TURNOVER_UPTREND_AMOUNT_WEIGHT * amount_rank
                - SHORTPICK_MARKET_FACTOR_LOW_TURNOVER_UPTREND_TURNOVER_PENALTY * turnover_rank
            )
        if family == SHORTPICK_MARKET_FACTOR_QUIET_BREAKOUT_FAMILY:
            score = (
                SHORTPICK_MARKET_FACTOR_QUIET_BREAKOUT_RET20_WEIGHT * ret20_rank
                + SHORTPICK_MARKET_FACTOR_QUIET_BREAKOUT_RET5_WEIGHT * _rank_percentile(pool, "return_5d", item)
                + SHORTPICK_MARKET_FACTOR_QUIET_BREAKOUT_LOW_ABS_RET1_WEIGHT * low_abs_ret1_rank
                + SHORTPICK_MARKET_FACTOR_QUIET_BREAKOUT_AMOUNT_WEIGHT * amount_rank
            )
        scored.update(
            {
                "_market_factor_score": round(score, 6),
                "_ret10_rank_percentile": ret10_rank,
                "_ret20_rank_percentile": ret20_rank,
                "_amount_rank_percentile": amount_rank,
                "_turnover_rank_percentile": turnover_rank,
                "_ret1_rank_percentile": ret1_rank,
                "_low_abs_ret1_rank_percentile": low_abs_ret1_rank,
            }
        )
        ranked.append(scored)
    return sorted(
        ranked,
        key=lambda item: (
            float(item["_market_factor_score"]),
            float(item["return_10d"]),
            float(item["amount"]),
            float(item["turnover_rate"]),
        ),
        reverse=True,
    )


def _deterministic_shortpick_market_factor_random_item(pool: list[dict[str, Any]], *, run_date: date) -> dict[str, Any] | None:
    if not pool:
        return None
    scored: list[tuple[str, int, dict[str, Any]]] = []
    for index, item in enumerate(pool, start=1):
        digest = hashlib.sha256(f"{run_date.isoformat()}:{item.get('symbol')}:shortpick-random-pool-v1".encode()).hexdigest()
        enriched = dict(item)
        enriched.update(
            {
                "_market_factor_score": 0.0,
                "_pool_source_rank": index,
                "_random_control_hash": digest[:16],
            }
        )
        scored.append((digest, index, enriched))
    return min(scored, key=lambda row: (row[0], row[1]))[2]


def _rank_percentile(pool: list[dict[str, Any]], key: str, item: dict[str, Any]) -> float:
    values = sorted(float(row[key]) for row in pool if row.get(key) is not None and math.isfinite(float(row[key])))
    if len(values) <= 1:
        return 0.5
    value = float(item[key])
    lower = sum(1 for candidate in values if candidate < value)
    equal = sum(1 for candidate in values if candidate == value)
    return round((lower + (equal - 1) / 2) / (len(values) - 1), 6)


def _upsert_shortpick_market_factor_candidate(
    session: Session,
    *,
    run: ShortpickExperimentRun,
    item: dict[str, Any],
    family: str,
    rank: int,
    pool: list[dict[str, Any]],
    regime: dict[str, Any],
    source_rank: int | None = None,
    tracking_role: str = "control",
) -> ShortpickCandidate:
    family_label = _shortpick_market_factor_family_label(family)
    candidate_key = f"shortpick-market-factor:{run.id}:{family}:{rank}"
    is_frozen_paper = family == SHORTPICK_FROZEN_PAPER_FAMILY
    is_random_control = family == SHORTPICK_MARKET_FACTOR_RANDOM_CONTROL_FAMILY
    if is_frozen_paper:
        thesis = (
            f"{family_label}：先按成交额和换手率取流动性靠前的 {SHORTPICK_MARKET_FACTOR_LOW_TURNOVER_UPTREND_POOL_LIMIT} 只候选，"
            "再选择20日趋势向上、成交额较高且换手率相对不拥挤的第1名；同一入场信号并行监测机械5日、机械10日、条件检查和10%止盈四条退出轨道。"
        )
    elif tracking_role == SHORTPICK_MARKET_FACTOR_TOP3_EQUAL_WEIGHT_CONTROL_ROLE:
        thesis = (
            f"{family_label}第 {rank} 名：市场转正且候选池不过热时，"
            "每日纸面资金在10日动量与换手排序前三名之间等权分配。"
        )
    elif tracking_role == SHORTPICK_MARKET_FACTOR_GOLDEN_CROSS_CONTROL_ROLE:
        thesis = (
            f"{family_label}：按动量成交量候选顺序筛选，选择第 {source_rank or rank} 个出现10日均线上穿200日均线的标的。"
        )
    elif tracking_role == SHORTPICK_MARKET_FACTOR_STRONG_BREADTH_RANK2_CONTROL_ROLE:
        thesis = (
            f"{family_label}：仅在市场10日上涨广度、Top40池10日动量和当日不过热同时满足时启动，"
            f"按10日动量、成交额、换手率综合排序并扣减当日涨幅，取第 {source_rank or rank} 名。"
        )
    elif tracking_role == SHORTPICK_MARKET_FACTOR_LEGACY_SECOND_CONTROL_ROLE:
        thesis = (
            f"{family_label}：保留旧冻结主线作为对照；市场转正且候选池不过热时，"
            f"取10日动量与换手排序第 {source_rank or rank} 名。"
        )
    elif tracking_role == SHORTPICK_MARKET_FACTOR_LOW_TURNOVER_UPTREND_CONTROL_ROLE:
        thesis = (
            f"{family_label}：市场广度不弱时，从流动性靠前标的中选择20日趋势向上、换手率相对不拥挤的第1名，"
            "用于验证非拥挤趋势是否优于短线追涨。"
        )
    elif tracking_role == SHORTPICK_MARKET_FACTOR_NO_LIMIT_CHASE_LOW_TURNOVER_CONTROL_ROLE:
        thesis = (
            f"{family_label}：沿用冻结低换手上升趋势排序，但排除信号日涨幅达到 "
            f"{SHORTPICK_MARKET_FACTOR_NO_LIMIT_CHASE_RETURN1_MAX:.1%} 及以上的候选，"
            f"取过滤后的第 {source_rank or rank} 名作为可执行风控对照。"
        )
    elif tracking_role == SHORTPICK_MARKET_FACTOR_OPEN_ENTRY_LOW_TURNOVER_CONTROL_ROLE:
        thesis = (
            f"{family_label}：沿用冻结低换手上升趋势第 {source_rank or rank} 名，"
            "只把入场价格从次一交易日收盘改为次一交易日开盘；若开盘价接近涨停，则不假设开盘可成交。"
        )
    elif tracking_role == SHORTPICK_MARKET_FACTOR_INTRADAY_SAME_DAY_CONTROL_ROLE:
        thesis = (
            f"{family_label}：交易日下午用实时行情替代当日收盘价，沿用冻结低换手上升趋势第 {source_rank or rank} 名，"
            "并在推荐生成后再读取一次当前价作为纸面买入价。"
        )
    elif tracking_role == SHORTPICK_MARKET_FACTOR_QUIET_BREAKOUT_CONTROL_ROLE:
        thesis = (
            f"{family_label}：从当日波动较小且流动性靠前的池子里，选择10日不弱、当日不过热的第 {source_rank or rank} 名，"
            "用于验证安静突破是否能作为次级对照。"
        )
    elif is_random_control:
        thesis = (
            f"{family_label}：先按当日动量成交量扩大到 {SHORTPICK_MARKET_FACTOR_POOL_LIMIT} 只候选，"
            f"再用日期和股票代码确定性抽取第 {source_rank or rank} 个池内标的，作为不看结果的同池基线。"
        )
    else:
        thesis = (
            f"{family_label}第 {rank} 名：先按当日动量成交量扩大到 {SHORTPICK_MARKET_FACTOR_POOL_LIMIT} 只候选，"
            "再用10日动量与换手率排序，并保留对当日追高的诊断。"
        )
    payload = {
        "information_mode": SHORTPICK_INFORMATION_MODE,
        "experiment_mode": "live_market_factor_overlay",
        "candidate_origin": "market_factor_overlay",
        "baseline_family": family,
        "tracking_role": tracking_role,
        "frozen_paper_strategy": shortpick_frozen_paper_strategy_contract() if is_frozen_paper else None,
        "topic_normalization": {
            "topic_cluster_id": "market_factor_shortpick",
            "label_zh": f"策略候选：{family_label}",
            "topic_confidence": 1.0,
            "normalization_method": "system_factor_overlay_v1",
            "status": "system_strategy",
            "reason": "来自历史回放后冻结的纸面策略，不使用新闻语义。" if is_frozen_paper else "来自历史回放后的市场因子对照，不使用新闻语义。",
        },
        "market_factor_overlay": {
            "rank": rank,
            "source_rank": source_rank or rank,
            "score": item.get("_market_factor_score"),
            "family": family,
            "family_label": family_label,
            "tracking_role": tracking_role,
            "pool_limit": SHORTPICK_MARKET_FACTOR_POOL_LIMIT,
            "rank_limit": SHORTPICK_MARKET_FACTOR_RANK_LIMIT,
            "pool_symbol_count": len(pool),
            "latest_trade_day": item.get("latest_trade_day"),
            "return_1d": item.get("return_1d"),
            "return_5d": item.get("return_5d"),
            "return_10d": item.get("return_10d"),
            "return_20d": item.get("return_20d"),
            "abs_return_1d": item.get("abs_return_1d"),
            "amount": item.get("amount"),
            "turnover_rate": item.get("turnover_rate"),
            "ret10_rank_percentile": item.get("_ret10_rank_percentile"),
            "ret20_rank_percentile": item.get("_ret20_rank_percentile"),
            "amount_rank_percentile": item.get("_amount_rank_percentile"),
            "turnover_rank_percentile": item.get("_turnover_rank_percentile"),
            "ret1_rank_percentile": item.get("_ret1_rank_percentile"),
            "low_abs_ret1_rank_percentile": item.get("_low_abs_ret1_rank_percentile"),
            "random_control_hash": item.get("_random_control_hash"),
            "golden_cross_10_200": item.get("golden_cross_10_200"),
            "ma10": item.get("ma10"),
            "ma200": item.get("ma200"),
            "previous_ma10": item.get("previous_ma10"),
            "previous_ma200": item.get("previous_ma200"),
            "no_limit_chase_return_1d_max": (
                SHORTPICK_MARKET_FACTOR_NO_LIMIT_CHASE_RETURN1_MAX
                if tracking_role == SHORTPICK_MARKET_FACTOR_NO_LIMIT_CHASE_LOW_TURNOVER_CONTROL_ROLE
                else None
            ),
            "entry_price_source": (
                SHORTPICK_ENTRY_PRICE_SOURCE_OPEN
                if tracking_role == SHORTPICK_MARKET_FACTOR_OPEN_ENTRY_LOW_TURNOVER_CONTROL_ROLE
                else SHORTPICK_ENTRY_PRICE_SOURCE_INTRADAY
                if tracking_role == SHORTPICK_MARKET_FACTOR_INTRADAY_SAME_DAY_CONTROL_ROLE
                else SHORTPICK_ENTRY_PRICE_SOURCE_CLOSE
            ),
            "intraday_quote": item.get("_intraday_selection_quote"),
            "intraday_entry_quote": item.get("_intraday_entry_quote"),
            "regime": regime,
        },
    }
    if tracking_role == SHORTPICK_MARKET_FACTOR_OPEN_ENTRY_LOW_TURNOVER_CONTROL_ROLE:
        payload["paper_tracking_entry_price_source"] = SHORTPICK_ENTRY_PRICE_SOURCE_OPEN
    if tracking_role == SHORTPICK_MARKET_FACTOR_INTRADAY_SAME_DAY_CONTROL_ROLE:
        signal_date = str(item.get("latest_trade_day") or run.run_date.isoformat())
        payload["paper_tracking_entry_price_source"] = SHORTPICK_ENTRY_PRICE_SOURCE_INTRADAY
        payload["paper_tracking_signal_date"] = signal_date
        payload["paper_tracking_entry_date"] = signal_date
        payload["paper_tracking_entry_price"] = item.get("_intraday_entry_price")
        payload["paper_tracking_entry_quote"] = item.get("_intraday_entry_quote")
    candidate = ShortpickCandidate(
        run_id=run.id,
        round_id=None,
        candidate_key=candidate_key,
        symbol=str(item["symbol"]),
        name=str(item["name"])[:64],
        normalized_theme=f"策略候选：{family_label}",
        horizon_trading_days=(
            SHORTPICK_FROZEN_PAPER_MAX_HOLDING_DAYS
            if is_frozen_paper or tracking_role in SHORTPICK_MARKET_FACTOR_PAPER_CONTROL_ROLES
            else 5
        ),
        confidence=float(item.get("_market_factor_score") or 0.0),
        thesis=thesis,
        catalysts=[
            f"10日涨幅 {float(item['return_10d']):.2%}",
            f"当日成交额 {float(item['amount']) / 100000000:.2f} 亿元",
            f"换手率 {float(item['turnover_rate']):.2f}",
        ],
        invalidation=[
            "条件检查轨道中收盘亏损达到8%触发纸面止损" if is_frozen_paper else "放量后次日承接不足",
            "短线趋势转弱或跌破前一交易日收盘",
        ],
        risks=[
            "冻结纸面策略候选，不代表生产级证明" if is_frozen_paper else "纯市场因子候选，不包含新闻语义核验",
            "高动量标的可能面临追高回撤",
            "10%触达止盈轨道使用日线最高价近似盘中触达，不等于真实逐笔成交" if is_frozen_paper else "作为对照组，不替代冻结纸面策略",
        ],
        sources_payload=[],
        novelty_note=(
            "冻结为正式纸面跟踪主策略；LLM自由选股和其他市场因子候选保留为对照组。"
            if is_frozen_paper
            else "作为对照组参与试验田验证，LLM自由选股继续保留为对照组。"
        ),
        limitations=["不读取未来信息；不使用盘后新增新闻；只基于截至运行日期的日线行情。"],
        convergence_group="market_factor",
        research_priority=(
            "market_factor_frozen_paper"
            if is_frozen_paper
            else "market_factor_random_pool_control"
            if is_random_control
            else "market_factor_default"
            if family == SHORTPICK_MARKET_FACTOR_DEFAULT_FAMILY
            else "market_factor_strong_breadth_rank2"
            if tracking_role == SHORTPICK_MARKET_FACTOR_STRONG_BREADTH_RANK2_CONTROL_ROLE
            else "market_factor_low_turnover_uptrend"
            if tracking_role == SHORTPICK_MARKET_FACTOR_LOW_TURNOVER_UPTREND_CONTROL_ROLE
            else "market_factor_no_limit_chase_low_turnover_uptrend"
            if tracking_role == SHORTPICK_MARKET_FACTOR_NO_LIMIT_CHASE_LOW_TURNOVER_CONTROL_ROLE
            else "market_factor_open_entry_low_turnover_uptrend"
            if tracking_role == SHORTPICK_MARKET_FACTOR_OPEN_ENTRY_LOW_TURNOVER_CONTROL_ROLE
            else "market_factor_intraday_same_day_low_turnover_uptrend"
            if tracking_role == SHORTPICK_MARKET_FACTOR_INTRADAY_SAME_DAY_CONTROL_ROLE
            else "market_factor_quiet_breakout"
            if tracking_role == SHORTPICK_MARKET_FACTOR_QUIET_BREAKOUT_CONTROL_ROLE
            else "market_factor_offensive"
        ),
        parse_status="parsed",
        is_system_external=_is_system_external(session, str(item["symbol"])),
        candidate_payload=payload,
    )
    session.add(candidate)
    session.flush()
    return candidate


def _shortpick_market_factor_family_label(family: str) -> str:
    if family == SHORTPICK_FROZEN_PAPER_FAMILY:
        return "低换手上升趋势"
    if family == SHORTPICK_MARKET_FACTOR_DEFAULT_FAMILY:
        return "10日动量换手降追高"
    if family == SHORTPICK_MARKET_FACTOR_OFFENSIVE_FAMILY:
        return "10日动量换手排序"
    if family == SHORTPICK_MARKET_FACTOR_RANDOM_CONTROL_FAMILY:
        return "同池随机基线"
    if family == "momentum_10d_turnover_top3_equal_weight":
        return "前三名等权组合"
    if family == "momentum_volume_golden_cross_10_200":
        return "10/200日金叉过滤"
    if family == "momentum_10d_turnover_legacy_second_candidate":
        return "旧主线第二候选"
    if family == SHORTPICK_MARKET_FACTOR_STRONG_BREADTH_RANK2_FAMILY:
        return "强广度低追高二候选"
    if family == SHORTPICK_MARKET_FACTOR_LOW_TURNOVER_UPTREND_FAMILY:
        return "低换手上升趋势"
    if family == SHORTPICK_MARKET_FACTOR_NO_LIMIT_CHASE_LOW_TURNOVER_FAMILY:
        return "可执行风控版"
    if family == SHORTPICK_MARKET_FACTOR_OPEN_ENTRY_LOW_TURNOVER_FAMILY:
        return "次日开盘买入版"
    if family == SHORTPICK_MARKET_FACTOR_INTRADAY_SAME_DAY_FAMILY:
        return "14点同日买入版"
    if family == SHORTPICK_MARKET_FACTOR_QUIET_BREAKOUT_FAMILY:
        return "安静突破二候选"
    return "动量成交量"


def _is_market_factor_overlay_candidate(candidate: ShortpickCandidate) -> bool:
    payload = candidate.candidate_payload if isinstance(candidate.candidate_payload, dict) else {}
    return (
        payload.get("candidate_origin") == "market_factor_overlay"
        or str(payload.get("baseline_family") or "").startswith("momentum_10d_turnover")
        or candidate.candidate_key.startswith("shortpick-market-factor:")
    )


def _normalize_shortpick_topic(parsed: dict[str, Any]) -> dict[str, Any]:
    raw = parsed.get("topic_analysis")
    verification = parsed.get("topic_verification") if isinstance(parsed.get("topic_verification"), dict) else {}
    if not isinstance(raw, dict):
        return {
            "topic_cluster_id": "unclassified",
            "label_zh": "未归类题材",
            "topic_confidence": 0.0,
            "normalization_method": "ai_structured_missing",
            "status": "unclassified",
            "reason": "Model output did not include structured topic_analysis.",
        }
    primary = raw.get("primary_topic") if isinstance(raw.get("primary_topic"), dict) else {}
    topic_id = _stable_topic_slug(primary.get("topic_cluster_id") or primary.get("label_zh"))
    label = _coerce_text(primary.get("label_zh")) or topic_id.replace("_", " ")
    confidence = _coerce_float(primary.get("confidence")) or 0.0
    evidence_refs = primary.get("supporting_evidence_refs")
    if not isinstance(evidence_refs, list):
        evidence_refs = []
    driver_types = [
        _stable_topic_slug(item)
        for item in (primary.get("driver_types") if isinstance(primary.get("driver_types"), list) else [])
        if _coerce_text(item)
    ]
    if not topic_id or topic_id in {"none", "null", "unclassified"}:
        return {
            "topic_cluster_id": "unclassified",
            "label_zh": "未归类题材",
            "topic_confidence": confidence,
            "normalization_method": "ai_structured_v1",
            "status": "unclassified",
            "reason": _coerce_text(raw.get("not_topic_reason")) or "AI topic classifier did not provide a usable topic id.",
            "raw_topic_analysis": raw,
            "topic_verification": verification,
        }
    verification_verdict = _coerce_text(verification.get("verdict"))
    verification_confidence = _coerce_float(verification.get("confidence"))
    verification_supported = verification_verdict in {None, "supported"} or (
        verification_verdict == "partially_supported" and (verification_confidence or 0.0) >= 0.65
    )
    status = "classified" if confidence >= 0.5 and verification_supported else "topic_uncertain"
    return {
        "topic_cluster_id": topic_id,
        "label_zh": label,
        "topic_confidence": max(0.0, min(1.0, confidence)),
        "topic_keywords": _coerce_string_list(primary.get("topic_keywords")),
        "topic_drivers": driver_types,
        "topic_evidence_refs": [item for item in evidence_refs if isinstance(item, int)],
        "normalization_method": "ai_structured_v1",
        "status": status,
        "reason": _coerce_text(primary.get("reason")),
        "secondary_topics": raw.get("secondary_topics") if isinstance(raw.get("secondary_topics"), list) else [],
        "new_topic_proposal": raw.get("new_topic_proposal") if isinstance(raw.get("new_topic_proposal"), dict) else None,
        "topic_verification": verification,
        "raw_topic_analysis": raw,
    }


def _stable_topic_slug(value: Any) -> str:
    text = _coerce_text(value)
    if not text:
        return ""
    lowered = text.lower().strip()
    cleaned = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "_", lowered)
    cleaned = re.sub(r"_+", "_", cleaned).strip("_")
    return cleaned[:80]


def _candidate_topic(candidate: ShortpickCandidate) -> dict[str, Any]:
    payload = candidate.candidate_payload if isinstance(candidate.candidate_payload, dict) else {}
    topic = payload.get("topic_normalization") if isinstance(payload.get("topic_normalization"), dict) else {}
    return topic


def _candidate_topic_key(candidate: ShortpickCandidate) -> str:
    topic = _candidate_topic(candidate)
    topic_id = _coerce_text(topic.get("topic_cluster_id"))
    if topic_id and topic_id != "unclassified" and topic.get("status") != "topic_uncertain":
        return topic_id
    return "unclassified"


def _candidate_topic_label(candidate: ShortpickCandidate) -> str:
    topic = _candidate_topic(candidate)
    label = _coerce_text(topic.get("label_zh"))
    if label:
        return label
    return candidate.normalized_theme or "未归类题材"


def normalize_shortpick_candidate_topics(
    session: Session,
    *,
    run_id: int | None = None,
    force: bool = False,
    classifier: Any | None = None,
) -> dict[str, Any]:
    query = select(ShortpickCandidate).where(
        ShortpickCandidate.parse_status == "parsed",
        ShortpickCandidate.symbol != "PARSE_FAILED",
    )
    if run_id is not None:
        query = query.where(ShortpickCandidate.run_id == run_id)
    candidates = session.scalars(query.order_by(ShortpickCandidate.id.asc())).all()
    updated: list[dict[str, Any]] = []
    skipped = 0
    failed: list[dict[str, Any]] = []
    for candidate in candidates:
        existing = _candidate_topic(candidate)
        if not force and _coerce_text(existing.get("topic_cluster_id")) and existing.get("status") not in {None, "unclassified"}:
            skipped += 1
            continue
        packet = _shortpick_topic_candidate_packet(session, candidate)
        try:
            normalized = classifier(packet) if classifier is not None else _classify_shortpick_topic_with_ai(packet)
        except Exception as exc:
            failed.append({"candidate_id": candidate.id, "symbol": candidate.symbol, "error": str(exc)[:240]})
            normalized = {
                "topic_cluster_id": "unclassified",
                "label_zh": candidate.normalized_theme or "未归类题材",
                "topic_confidence": 0.0,
                "normalization_method": "ai_backfill_failed",
                "status": "unclassified",
                "reason": str(exc)[:240],
            }
        payload = dict(candidate.candidate_payload or {})
        payload["topic_normalization"] = normalized
        candidate.candidate_payload = payload
        updated.append(
            {
                "candidate_id": candidate.id,
                "symbol": candidate.symbol,
                "topic_cluster_id": normalized.get("topic_cluster_id"),
                "status": normalized.get("status"),
            }
        )
    session.flush()
    return {
        "candidate_count": len(candidates),
        "updated_count": len(updated),
        "skipped_count": skipped,
        "failed_count": len(failed),
        "updated": updated,
        "failed": failed,
    }


def _shortpick_topic_candidate_packet(session: Session, candidate: ShortpickCandidate) -> dict[str, Any]:
    round_record = session.get(ShortpickModelRound, candidate.round_id) if candidate.round_id else None
    return {
        "candidate_id": candidate.id,
        "run_id": candidate.run_id,
        "symbol": candidate.symbol,
        "name": candidate.name,
        "raw_theme": candidate.normalized_theme,
        "thesis": candidate.thesis,
        "catalysts": list(candidate.catalysts or []),
        "risks": list(candidate.risks or []),
        "limitations": list(candidate.limitations or []),
        "sources": [
            {
                "index": index,
                "title": source.get("title"),
                "url": source.get("url"),
                "why_it_matters": source.get("why_it_matters"),
                "authority_class": source.get("authority_class"),
                "credibility_status": source.get("credibility_status"),
            }
            for index, source in enumerate(candidate.sources_payload or [])
            if isinstance(source, dict)
        ],
        "model": {
            "provider_name": round_record.provider_name if round_record is not None else None,
            "model_name": round_record.model_name if round_record is not None else None,
            "executor_kind": round_record.executor_kind if round_record is not None else None,
        },
    }


def _classify_shortpick_topic_with_ai(packet: dict[str, Any]) -> dict[str, Any]:
    transport, base_url, api_key, model_name = route_model("shortpick_topic_normalization")
    raw = transport.complete(
        base_url=base_url,
        api_key=api_key,
        model_name=model_name,
        prompt=_build_shortpick_topic_backfill_prompt(packet),
        system=(
            "你是 A 股短投试验田的题材归一化器。"
            "只能基于输入候选包判断题材，不要联网，不要新增事实。只输出 JSON。"
        ),
    )
    parsed = extract_shortpick_json(raw)
    return _normalize_topic_classifier_response(parsed)


def _build_shortpick_topic_backfill_prompt(packet: dict[str, Any]) -> str:
    return f"""
请把下面短投试验田候选归入一个语义稳定的题材簇。不要使用人工标签，不要按硬关键词机械匹配；要判断驱动是否真的一致。

输出 JSON，不要代码块：
{{
  "topic_analysis": {{
    "primary_topic": {{
      "topic_cluster_id": "stable_english_slug",
      "label_zh": "中文题材标签",
      "confidence": 0.0,
      "reason": "为什么属于该题材",
      "supporting_evidence_refs": [0],
      "driver_types": ["policy", "price_change", "earnings", "contract_order", "market_hotspot", "industry_chain"],
      "topic_keywords": ["..."]
    }},
    "secondary_topics": [],
    "new_topic_proposal": null,
    "not_topic_reason": null
  }},
  "topic_verification": {{
    "verdict": "supported",
    "confidence": 0.0,
    "unsupported_claims": [],
    "suggested_topic_cluster_id": null
  }}
}}

候选包：
{json.dumps(packet, ensure_ascii=False, indent=2)[:12000]}
""".strip()


def _normalize_topic_classifier_response(parsed: dict[str, Any]) -> dict[str, Any]:
    if isinstance(parsed.get("topic_analysis"), dict):
        normalized = _normalize_shortpick_topic(parsed)
    else:
        normalized = _normalize_shortpick_topic(
            {
                "topic_analysis": {
                    "primary_topic": parsed.get("primary_topic") if isinstance(parsed.get("primary_topic"), dict) else parsed,
                    "secondary_topics": parsed.get("secondary_topics") if isinstance(parsed.get("secondary_topics"), list) else [],
                    "new_topic_proposal": parsed.get("new_topic_proposal") if isinstance(parsed.get("new_topic_proposal"), dict) else None,
                    "not_topic_reason": parsed.get("not_topic_reason"),
                },
                "topic_verification": parsed.get("topic_verification") if isinstance(parsed.get("topic_verification"), dict) else {},
            }
        )
    normalized["normalization_method"] = "ai_backfill_v1"
    return normalized


def build_shortpick_consensus(session: Session, run: ShortpickExperimentRun) -> ShortpickConsensusSnapshot:
    candidates = session.scalars(
        select(ShortpickCandidate).where(ShortpickCandidate.run_id == run.id).order_by(ShortpickCandidate.id.asc())
    ).all()
    consensus_candidates = [item for item in candidates if not _is_market_factor_overlay_candidate(item)]
    parsed = [item for item in consensus_candidates if item.parse_status == "parsed" and item.symbol != "PARSE_FAILED"]
    total = max(len(parsed), 1)
    symbol_counts: dict[str, int] = {}
    theme_counts: dict[str, int] = {}
    topic_labels: dict[str, str] = {}
    model_by_symbol: dict[str, set[str]] = {}
    model_counts_by_symbol: dict[str, dict[str, int]] = {}
    model_by_theme: dict[str, set[str]] = {}
    source_hosts: set[str] = set()
    all_source_urls: set[str] = set()
    source_status_counts: dict[str, int] = {}
    for candidate in parsed:
        symbol_counts[candidate.symbol] = symbol_counts.get(candidate.symbol, 0) + 1
        topic_key = _candidate_topic_key(candidate)
        if topic_key != "unclassified":
            theme_counts[topic_key] = theme_counts.get(topic_key, 0) + 1
            topic_labels.setdefault(topic_key, _candidate_topic_label(candidate))
        round_record = session.get(ShortpickModelRound, candidate.round_id) if candidate.round_id else None
        if round_record is not None:
            model_by_symbol.setdefault(candidate.symbol, set()).add(round_record.provider_name)
            model_counts_by_symbol.setdefault(candidate.symbol, {})
            model_counts_by_symbol[candidate.symbol][round_record.provider_name] = (
                model_counts_by_symbol[candidate.symbol].get(round_record.provider_name, 0) + 1
            )
            if topic_key != "unclassified":
                model_by_theme.setdefault(topic_key, set()).add(round_record.provider_name)
        for source in candidate.sources_payload:
            credibility = str(source.get("credibility_status") or "unchecked")
            source_status_counts[credibility] = source_status_counts.get(credibility, 0) + 1
            url = str(source.get("url") or "").strip()
            if not url:
                continue
            all_source_urls.add(url)
            source_hosts.add(_host_from_url(url))
    max_symbol_count = max(symbol_counts.values(), default=0)
    max_theme_count = max(theme_counts.values(), default=0)
    stock_convergence = max_symbol_count / total
    theme_convergence = max_theme_count / total
    source_diversity = min(len(source_hosts) / max(len(all_source_urls), 1), 1.0) if all_source_urls else 0.0
    model_independence = max((len(models) for models in model_by_symbol.values()), default=0) / max(
        len({candidate.candidate_payload.get("model", {}).get("provider_name") for candidate in parsed}),
        1,
    )
    novelty_score = sum(1 for item in parsed if item.is_system_external) / total
    cross_model_symbols = sorted(symbol for symbol, models in model_by_symbol.items() if len(models) >= 2)
    same_model_repeat_symbols = sorted(
        symbol
        for symbol, provider_counts in model_counts_by_symbol.items()
        if any(count >= 2 for count in provider_counts.values())
    )
    cross_model_themes = sorted(theme for theme, models in model_by_theme.items() if len(models) >= 2)
    priority = (
        "cross_model_same_symbol"
        if cross_model_symbols
        else "cross_model_same_topic"
        if cross_model_themes
        else "divergent_novel"
    )
    leader_symbols = [symbol for symbol, count in symbol_counts.items() if count == max_symbol_count and count > 0]
    leader_themes = [theme for theme, count in theme_counts.items() if count == max_theme_count and count > 0]
    topic_registry = [
        {
            "topic_cluster_id": topic_id,
            "label_zh": topic_labels.get(topic_id, topic_id),
            "candidate_count": theme_counts.get(topic_id, 0),
            "provider_count": len(model_by_theme.get(topic_id, set())),
            "status": "active" if topic_id in cross_model_themes else "candidate",
            "source": "ai_structured_topic_normalization",
        }
        for topic_id in sorted(theme_counts)
    ]
    for candidate in parsed:
        round_record = session.get(ShortpickModelRound, candidate.round_id) if candidate.round_id else None
        provider_name = round_record.provider_name if round_record is not None else ""
        topic_key = _candidate_topic_key(candidate)
        source_quality_ok = any(
            str(source.get("credibility_status") or "") in {"verified", "reachable_restricted"}
            for source in candidate.sources_payload
        )
        if candidate.symbol in cross_model_symbols:
            candidate.convergence_group = "stock"
            candidate.research_priority = "cross_model_same_symbol"
        elif candidate.symbol in same_model_repeat_symbols and model_counts_by_symbol.get(candidate.symbol, {}).get(provider_name, 0) >= 2:
            candidate.convergence_group = "stock"
            candidate.research_priority = "same_model_repeat_symbol"
        elif topic_key in cross_model_themes:
            candidate.convergence_group = "theme"
            candidate.research_priority = "cross_model_same_topic"
        elif (candidate.confidence or 0.0) >= 0.65 and source_quality_ok and candidate.is_system_external:
            candidate.convergence_group = "conviction"
            candidate.research_priority = "single_model_high_conviction"
        elif candidate.is_system_external:
            candidate.convergence_group = "novel"
            candidate.research_priority = "divergent_novel"
        else:
            candidate.convergence_group = "low"
            candidate.research_priority = "watch_only"
    generated_at = utcnow()
    summary_payload = {
        "leader_symbols": leader_symbols,
        "leader_themes": leader_themes,
        "leader_theme_labels": {theme: topic_labels.get(theme, theme) for theme in leader_themes},
        "priority_score": None,
        "priority_method": "explicit_consensus_categories_v1",
        "cross_model_symbols": cross_model_symbols,
        "same_model_repeat_symbols": same_model_repeat_symbols,
        "cross_model_themes": cross_model_themes,
        "cross_model_theme_labels": {theme: topic_labels.get(theme, theme) for theme in cross_model_themes},
        "topic_registry": topic_registry,
        "candidate_count": len(consensus_candidates),
        "excluded_market_factor_overlay_candidate_count": len(candidates) - len(consensus_candidates),
        "parsed_candidate_count": len(parsed),
        "source_credibility_counts": source_status_counts,
        "interpretation": "模型一致性只代表研究优先级，不代表交易建议。",
    }
    snapshot_key = f"shortpick-consensus:{run.id}"
    snapshot = session.scalar(select(ShortpickConsensusSnapshot).where(ShortpickConsensusSnapshot.snapshot_key == snapshot_key))
    if snapshot is None:
        snapshot = ShortpickConsensusSnapshot(
            run_id=run.id,
            snapshot_key=snapshot_key,
            artifact_id=snapshot_key,
            generated_at=generated_at,
            status="completed" if parsed else "insufficient_parsed_rounds",
            stock_convergence=stock_convergence,
            theme_convergence=theme_convergence,
            source_diversity=source_diversity,
            model_independence=model_independence,
            novelty_score=novelty_score,
            research_priority=priority,
            summary_payload=summary_payload,
        )
        session.add(snapshot)
    else:
        snapshot.generated_at = generated_at
        snapshot.status = "completed" if parsed else "insufficient_parsed_rounds"
        snapshot.stock_convergence = stock_convergence
        snapshot.theme_convergence = theme_convergence
        snapshot.source_diversity = source_diversity
        snapshot.model_independence = model_independence
        snapshot.novelty_score = novelty_score
        snapshot.research_priority = priority
        snapshot.summary_payload = summary_payload
    session.flush()
    _write_consensus_artifact(session, run, snapshot)
    return snapshot


def select_shortpick_llm_paper_control_candidate(session: Session, run: ShortpickExperimentRun) -> dict[str, Any]:
    candidates = session.scalars(
        select(ShortpickCandidate).where(ShortpickCandidate.run_id == run.id).order_by(ShortpickCandidate.id.asc())
    ).all()
    parsed = [
        candidate
        for candidate in candidates
        if candidate.parse_status == "parsed"
        and candidate.symbol != "PARSE_FAILED"
        and not _is_market_factor_overlay_candidate(candidate)
    ]
    for candidate in parsed:
        payload = dict(candidate.candidate_payload or {})
        if payload.get("tracking_role") == SHORTPICK_LLM_PAPER_CONTROL_ROLE:
            payload.pop("tracking_role", None)
        payload.pop("llm_paper_control", None)
        candidate.candidate_payload = payload
    if not parsed:
        result = {
            **shortpick_llm_paper_control_contract(),
            "status": "no_eligible_llm_candidate",
            "selected": False,
            "reason": "no_parsed_llm_candidate",
        }
        run.summary_payload = {**dict(run.summary_payload or {}), "llm_paper_control": result}
        session.flush()
        return result

    eligible: list[ShortpickCandidate] = []
    excluded_examples: list[dict[str, Any]] = []
    excluded_count = 0
    for candidate in parsed:
        eligibility = account_trade_eligibility(
            candidate.symbol,
            stock_profile={"name": candidate.name},
            account_profile=ACCOUNT_PROFILE_NEW_RETAIL_CASH,
            as_of=run.run_date,
        )
        if eligibility["tradable"]:
            eligible.append(candidate)
            continue
        excluded_count += 1
        if len(excluded_examples) < 12:
            excluded_examples.append(
                {
                    "candidate_id": candidate.id,
                    "symbol": candidate.symbol,
                    "name": candidate.name,
                    "board": eligibility["board"],
                    "board_label": eligibility["board_label"],
                    "reason": eligibility["reason"],
                }
            )
    if not eligible:
        result = {
            **shortpick_llm_paper_control_contract(),
            "status": "no_eligible_llm_candidate",
            "selected": False,
            "reason": "no_account_eligible_llm_candidate",
            "raw_candidate_count": len(parsed),
            "eligible_candidate_count": 0,
            "excluded_candidate_count": excluded_count,
            "excluded_examples": excluded_examples,
        }
        run.summary_payload = {**dict(run.summary_payload or {}), "llm_paper_control": result}
        session.flush()
        return result

    providers_by_symbol: dict[str, set[str]] = {}
    provider_counts_by_symbol: dict[str, dict[str, int]] = {}
    providers_by_theme: dict[str, set[str]] = {}
    for candidate in eligible:
        round_record = session.get(ShortpickModelRound, candidate.round_id) if candidate.round_id else None
        provider_name = round_record.provider_name if round_record is not None else "unknown"
        topic_key = _candidate_topic_key(candidate)
        providers_by_symbol.setdefault(candidate.symbol, set()).add(provider_name)
        provider_counts_by_symbol.setdefault(candidate.symbol, {})
        provider_counts_by_symbol[candidate.symbol][provider_name] = provider_counts_by_symbol[candidate.symbol].get(provider_name, 0) + 1
        if topic_key != "unclassified":
            providers_by_theme.setdefault(topic_key, set()).add(provider_name)

    priority_rank = {
        "cross_model_same_symbol": 50,
        "same_model_repeat_symbol": 40,
        "cross_model_same_topic": 30,
        "single_model_high_conviction": 20,
        "divergent_novel": 10,
        "watch_only": 0,
    }

    def score_components(candidate: ShortpickCandidate) -> dict[str, Any]:
        round_record = session.get(ShortpickModelRound, candidate.round_id) if candidate.round_id else None
        provider_name = round_record.provider_name if round_record is not None else "unknown"
        topic_key = _candidate_topic_key(candidate)
        provider_counts = provider_counts_by_symbol.get(candidate.symbol, {})
        source_quality_count = sum(
            1
            for source in candidate.sources_payload
            if str(source.get("credibility_status") or "") in {"verified", "reachable_restricted"}
        )
        return {
            "priority_rank": priority_rank.get(candidate.research_priority, 0),
            "symbol_provider_count": len(providers_by_symbol.get(candidate.symbol, set())),
            "same_provider_repeat_count": provider_counts.get(provider_name, 0),
            "theme_provider_count": len(providers_by_theme.get(topic_key, set())) if topic_key != "unclassified" else 0,
            "source_quality_count": source_quality_count,
            "confidence": float(candidate.confidence or 0.0),
            "source_count": len(candidate.sources_payload or []),
            "symbol": candidate.symbol,
            "candidate_id": candidate.id,
            "original_research_priority": candidate.research_priority,
        }

    def sort_key(candidate: ShortpickCandidate) -> tuple[Any, ...]:
        score = score_components(candidate)
        return (
            -int(score["priority_rank"]),
            -int(score["symbol_provider_count"]),
            -int(score["same_provider_repeat_count"]),
            -int(score["theme_provider_count"]),
            -int(score["source_quality_count"]),
            -float(score["confidence"]),
            -int(score["source_count"]),
            str(score["symbol"]),
            int(score["candidate_id"]),
        )

    ranked = sorted(eligible, key=sort_key)
    selected = ranked[0]
    components = score_components(selected)
    selected_eligibility = account_trade_eligibility(
        selected.symbol,
        stock_profile={"name": selected.name},
        account_profile=ACCOUNT_PROFILE_NEW_RETAIL_CASH,
        as_of=run.run_date,
    )
    payload = dict(selected.candidate_payload or {})
    payload["tracking_role"] = SHORTPICK_LLM_PAPER_CONTROL_ROLE
    payload["llm_paper_control"] = {
        **shortpick_llm_paper_control_contract(),
        "selected": True,
        "selection_rank": 1,
        "selection_score_components": components,
        "account_eligibility": selected_eligibility,
        "selected_at": utcnow().isoformat(),
    }
    selected.candidate_payload = payload
    result = {
        **shortpick_llm_paper_control_contract(),
        "status": "selected",
        "selected": True,
        "candidate_id": selected.id,
        "symbol": selected.symbol,
        "name": selected.name,
        "selection_score_components": components,
        "account_eligibility": selected_eligibility,
        "raw_candidate_count": len(parsed),
        "eligible_candidate_count": len(eligible),
        "excluded_candidate_count": excluded_count,
        "excluded_examples": excluded_examples,
    }
    run.summary_payload = {**dict(run.summary_payload or {}), "llm_paper_control": result}
    session.flush()
    return result


def validate_shortpick_run(
    session: Session,
    run_id: int,
    *,
    horizons: list[int] | None = None,
) -> dict[str, Any]:
    run = session.get(ShortpickExperimentRun, run_id)
    if run is None:
        raise LookupError(f"Shortpick run {run_id} not found.")
    target_horizons = horizons or SHORTPICK_DEFAULT_HORIZONS
    removed_superseded_parse_failures = _cleanup_superseded_parse_failed_candidates(session, run_id=run_id)
    candidates = session.scalars(
        select(ShortpickCandidate).where(ShortpickCandidate.run_id == run_id).order_by(ShortpickCandidate.id.asc())
    ).all()
    parsed_candidates = [
        candidate
        for candidate in candidates
        if candidate.parse_status == "parsed" and candidate.symbol != "PARSE_FAILED"
    ]
    historical_replay = run.information_mode == "historical_replay"
    benchmark_sync = (
        {"status": "historical_replay_existing_only", "reason": "Historical replay never fetches current benchmark data."}
        if historical_replay
        else _sync_shortpick_benchmarks(session)
        if parsed_candidates
        else {"status": "skipped", "reason": "no_parsed_candidates"}
    )
    updated = 0
    for candidate in parsed_candidates:
        market_sync = (
            {"status": "historical_replay_existing_only", "reason": "Historical replay never fetches current market data."}
            if historical_replay
            else _sync_shortpick_candidate_market_data(session, candidate)
        )
        benchmark_maps = benchmark_close_maps(session)
        for horizon in target_horizons:
            _upsert_validation_snapshot(
                session,
                run,
                candidate,
                int(horizon),
                benchmark_maps=benchmark_maps,
                market_sync=market_sync,
            )
            updated += 1
    display_gate = _apply_shortpick_candidate_display_gates(session, run_id=run_id)
    summary = {
        **_shortpick_validation_summary(session, run_id=run_id),
        "candidate_display_gate": display_gate,
        "removed_superseded_parse_failed_count": removed_superseded_parse_failures,
    }
    run.summary_payload = {
        **dict(run.summary_payload or {}),
        **summary,
        "benchmark_sync": benchmark_sync,
    }
    session.flush()
    return {"run_id": run_id, "updated_validation_count": updated, "horizons": target_horizons, "summary": summary}


def validate_recent_shortpick_runs(
    session: Session,
    *,
    days: int = 30,
    limit: int = 20,
    horizons: list[int] | None = None,
) -> dict[str, Any]:
    """Refresh validation snapshots for recent completed short-pick lab runs."""

    target_horizons = horizons or SHORTPICK_DEFAULT_HORIZONS
    cutoff = datetime.now(UTC).date() - timedelta(days=max(1, int(days)))
    run_limit = max(1, min(int(limit), 100))
    runs = session.scalars(
        select(ShortpickExperimentRun)
        .where(
            ShortpickExperimentRun.status == "completed",
            ShortpickExperimentRun.run_date >= cutoff,
        )
        .order_by(ShortpickExperimentRun.run_date.desc(), ShortpickExperimentRun.id.desc())
        .limit(run_limit)
    ).all()
    refreshed: list[dict[str, Any]] = []
    for run in runs:
        result = validate_shortpick_run(session, run.id, horizons=target_horizons)
        refreshed.append(
            {
                "run_id": run.id,
                "run_key": run.run_key,
                "run_date": run.run_date.isoformat(),
                "updated_validation_count": result["updated_validation_count"],
                "summary": result["summary"],
            }
        )
    return {
        "refreshed_run_count": len(refreshed),
        "days": max(1, int(days)),
        "limit": run_limit,
        "horizons": target_horizons,
        "runs": refreshed,
    }


def retry_failed_shortpick_rounds(
    session: Session,
    run_id: int,
    *,
    max_rounds: int | None = None,
) -> dict[str, Any]:
    run = session.get(ShortpickExperimentRun, run_id)
    if run is None:
        raise LookupError(f"Shortpick run {run_id} not found.")
    failed_rounds = session.scalars(
        select(ShortpickModelRound)
        .where(ShortpickModelRound.run_id == run_id, ShortpickModelRound.status == "failed")
        .order_by(ShortpickModelRound.id.asc())
    ).all()
    retryable_rounds = [round_record for round_record in failed_rounds if _round_retryable(round_record)]
    if max_rounds is not None:
        retryable_rounds = retryable_rounds[: max(1, int(max_rounds))]
    executors = default_shortpick_executors(session)
    retried: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for round_record in retryable_rounds:
        executor = _matching_executor_for_round(executors, round_record)
        if executor is None:
            skipped.append(
                {
                    "round_id": round_record.id,
                    "round_index": round_record.round_index,
                    "provider_name": round_record.provider_name,
                    "model_name": round_record.model_name,
                    "reason": "configuration_failure",
                }
            )
            continue
        retried.append(_retry_existing_shortpick_round(session, run, round_record, executor))

    if retried:
        if _should_auto_topic_backfill(executors):
            normalize_shortpick_candidate_topics(session, run_id=run.id)
        consensus = build_shortpick_consensus(session, run)
        llm_paper_control = select_shortpick_llm_paper_control_candidate(session, run)
        market_factor_overlay = insert_shortpick_market_factor_overlay_candidates(session, run)
        validation_result = validate_shortpick_run(session, run.id, horizons=SHORTPICK_DEFAULT_HORIZONS)
        completed_count = session.scalar(
            select(func.count(ShortpickModelRound.id)).where(
                ShortpickModelRound.run_id == run.id,
                ShortpickModelRound.status == "completed",
            )
        ) or 0
        failed_count = session.scalar(
            select(func.count(ShortpickModelRound.id)).where(
                ShortpickModelRound.run_id == run.id,
                ShortpickModelRound.status == "failed",
            )
        ) or 0
        parse_failed_count = session.scalar(
            select(func.count(ShortpickCandidate.id)).where(
                ShortpickCandidate.run_id == run.id,
                ShortpickCandidate.parse_status == "parse_failed",
            )
        ) or 0
        run.status = "completed" if completed_count else "failed"
        run.completed_at = utcnow() if completed_count else None
        run.failed_at = None if completed_count else utcnow()
        run.summary_payload = {
            **dict(run.summary_payload or {}),
            "completed_round_count": completed_count,
            "failed_round_count": failed_count,
            "parse_failed_count": parse_failed_count,
            "candidate_count": session.scalar(select(func.count(ShortpickCandidate.id)).where(ShortpickCandidate.run_id == run.id)) or 0,
            "consensus_priority": consensus.research_priority,
            "llm_paper_control": llm_paper_control,
            "market_factor_overlay": market_factor_overlay,
            "boundary": "independent_research_lab_no_main_pool_write",
            **dict(validation_result.get("summary") or {}),
        }
    session.flush()
    return {
        "run_id": run_id,
        "retryable_failed_round_count": len(retryable_rounds),
        "retried_round_count": len(retried),
        "skipped_round_count": len(skipped),
        "retried": retried,
        "skipped": skipped,
        "run": serialize_shortpick_run(session, run, include_raw=True),
    }


def _matching_executor_for_round(executors: list[ShortpickExecutor], round_record: ShortpickModelRound) -> ShortpickExecutor | None:
    for executor in executors:
        if (
            executor.provider_name == round_record.provider_name
            and executor.model_name == round_record.model_name
            and executor.executor_kind == round_record.executor_kind
        ):
            return executor
    for executor in executors:
        if executor.provider_name == round_record.provider_name and executor.model_name == round_record.model_name:
            return executor
    return None


def _retry_existing_shortpick_round(
    session: Session,
    run: ShortpickExperimentRun,
    round_record: ShortpickModelRound,
    executor: ShortpickExecutor,
) -> dict[str, Any]:
    round_id = round_record.id
    retry_started_at = utcnow()
    previous_artifact_id = round_record.artifact_id
    previous_error = round_record.error_message
    previous_status = round_record.status
    previous_raw_answer = round_record.raw_answer
    retry_history = list((round_record.parsed_payload or {}).get("_retry_history") or [])
    retry_history.append(
        {
            "artifact_id": previous_artifact_id,
            "error_message": previous_error,
            "status": previous_status,
            "raw_answer": previous_raw_answer,
            "retried_at": retry_started_at.isoformat(),
            "failure_category": _shortpick_failure_category(previous_error),
        }
    )
    round_record.status = "running"
    round_record.error_message = None
    round_record.raw_answer = None
    round_record.sources_payload = []
    round_record.parsed_payload = {"_retry_history": retry_history}
    round_record.started_at = retry_started_at
    round_record.completed_at = None
    round_record.artifact_id = f"shortpick-round:{round_record.id}:retry-{retry_started_at:%Y%m%d%H%M%S%f}"
    session.commit()
    session.refresh(round_record)

    prompt = build_shortpick_prompt(
        run_date=run.run_date,
        round_index=round_record.round_index,
        provider_name=executor.provider_name,
        model_name=executor.model_name,
    )
    raw_answer: str | None = None
    try:
        raw_answer = executor.complete(prompt)
        parsed = extract_shortpick_json(raw_answer)
        sources = _normalize_sources(parsed.get("sources_used"))
        source_failure = _web_source_integrity_failure(executor=executor, parsed=parsed, sources=sources)
        if source_failure:
            raise RuntimeError(source_failure)
        parsed["_retry_history"] = retry_history
        round_record.raw_answer = raw_answer
        round_record.parsed_payload = parsed
        round_record.sources_payload = sources
        round_record.status = "completed"
        round_record.completed_at = utcnow()
        round_record.error_message = None
        _write_round_artifact(session, run, round_record, prompt=prompt)
        _delete_parse_failed_candidates_for_round(session, round_record.id)
        _candidate_from_round(session, run, round_record, parsed, parse_status="parsed")
    except Exception as exc:
        session.rollback()
        round_record = session.get(ShortpickModelRound, round_id)
        if round_record is None:
            return {"round_id": None, "status": "missing_after_retry", "error_message": str(exc)}
        round_record.status = "failed"
        round_record.error_message = str(exc)
        round_record.completed_at = utcnow()
        round_record.raw_answer = raw_answer
        round_record.parsed_payload = {"_retry_history": retry_history}
        _write_round_artifact(session, run, round_record, prompt=prompt)
    session.flush()
    return {
        "round_id": round_record.id,
        "round_index": round_record.round_index,
        "provider_name": round_record.provider_name,
        "model_name": round_record.model_name,
        "status": round_record.status,
        "previous_artifact_id": previous_artifact_id,
        "previous_error_message": previous_error,
        "failure_category": _shortpick_failure_category(previous_error),
    }


def _upsert_validation_snapshot(
    session: Session,
    run: ShortpickExperimentRun,
    candidate: ShortpickCandidate,
    horizon: int,
    *,
    benchmark_maps: dict[str, dict[Any, float]] | None = None,
    market_sync: dict[str, Any] | None = None,
    include_sector_benchmark: bool = True,
) -> ShortpickValidationSnapshot:
    existing = session.scalar(
        select(ShortpickValidationSnapshot).where(
            ShortpickValidationSnapshot.candidate_id == candidate.id,
            ShortpickValidationSnapshot.horizon_days == horizon,
        )
    )
    if existing is None:
        existing = ShortpickValidationSnapshot(
            candidate_id=candidate.id,
            horizon_days=horizon,
            status="pending_market_data",
            validation_payload={},
        )
        session.add(existing)
        session.flush()
    candidate_metadata = _shortpick_candidate_validation_metadata(candidate)
    bars = _daily_bars_for_symbol(session, candidate.symbol)
    if not bars:
        existing.status = "pending_market_data"
        _clear_validation_metrics(existing)
        existing.validation_payload = {
            "reason": "No daily bars found for candidate symbol.",
            "validation_mode": SHORTPICK_OFFICIAL_VALIDATION_MODE,
            "official_validation": False,
            "tradeability_status": "pending_market_data",
            "market_data_sync": market_sync or {},
            **candidate_metadata,
        }
        return existing

    round_record = session.get(ShortpickModelRound, candidate.round_id) if candidate.round_id else None
    signal_available_at = _shortpick_signal_available_at(run, round_record)
    signal_trade_day = signal_available_at.date()
    entry_price_source = _shortpick_entry_price_source(candidate)
    same_day_intraday_entry = entry_price_source == SHORTPICK_ENTRY_PRICE_SOURCE_INTRADAY
    latest_bar_day = bars[-1].observed_at.date()
    if latest_bar_day < signal_trade_day or (latest_bar_day == signal_trade_day and not same_day_intraday_entry):
        existing.status = "suspended_or_no_current_bar" if latest_bar_day < signal_trade_day else "pending_forward_window"
        _clear_validation_metrics(existing)
        existing.validation_payload = {
            "reason": (
                f"No completed tradeable entry close after signal day {signal_trade_day.isoformat()}; "
                f"latest daily bar is {latest_bar_day.isoformat()}."
            ),
            "validation_mode": SHORTPICK_OFFICIAL_VALIDATION_MODE,
            "official_validation": False,
            "tradeability_status": "suspended_or_no_current_bar" if latest_bar_day < signal_trade_day else "pending_market_data",
            "signal_available_at": signal_available_at.isoformat(),
            "signal_trade_day": signal_trade_day.isoformat(),
            "latest_trade_day": latest_bar_day.isoformat(),
            "market_data_sync": market_sync or {},
            **candidate_metadata,
        }
        return existing

    def is_entry_bar(bar: MarketBar) -> bool:
        bar_day = bar.observed_at.date()
        return bar_day >= signal_trade_day if same_day_intraday_entry else bar_day > signal_trade_day

    entry_index = next((idx for idx, bar in enumerate(bars) if is_entry_bar(bar)), None)
    if entry_index is None:
        existing.status = "pending_entry_bar"
        _clear_validation_metrics(existing)
        existing.validation_payload = {
            "reason": "No completed entry bar after signal availability.",
            "validation_mode": SHORTPICK_OFFICIAL_VALIDATION_MODE,
            "official_validation": False,
            "tradeability_status": "pending_market_data",
            "signal_available_at": signal_available_at.isoformat(),
            "signal_trade_day": signal_trade_day.isoformat(),
            "market_data_sync": market_sync or {},
            **candidate_metadata,
        }
        return existing

    tradeability = _shortpick_entry_tradeability(candidate=candidate, bars=bars, entry_index=entry_index)
    entry_price = _shortpick_entry_execution_price(candidate=candidate, entry=bars[entry_index])
    if tradeability["tradeability_status"] != SHORTPICK_OFFICIAL_TRADEABILITY_STATUS:
        entry = bars[entry_index]
        existing.status = str(tradeability["tradeability_status"])
        existing.entry_at = entry.observed_at
        existing.entry_close = entry_price
        existing.exit_at = None
        existing.exit_close = None
        existing.stock_return = None
        existing.benchmark_return = None
        existing.excess_return = None
        existing.max_favorable_return = None
        existing.max_drawdown = None
        existing.validation_payload = {
            "validation_mode": SHORTPICK_OFFICIAL_VALIDATION_MODE,
            "official_validation": False,
            "tradeability_status": tradeability["tradeability_status"],
            "tradeability_evidence": tradeability,
            "signal_available_at": signal_available_at.isoformat(),
            "signal_trade_day": signal_trade_day.isoformat(),
            "entry_trade_day": entry.observed_at.date().isoformat(),
            "entry_price": entry_price,
            "entry_price_source": entry_price_source,
            "market_data_sync": market_sync or {},
            **candidate_metadata,
        }
        return existing

    exit_index = entry_index + horizon
    if exit_index >= len(bars):
        available_forward_bars = max(len(bars) - entry_index - 1, 0)
        existing.status = "pending_forward_window"
        existing.entry_at = bars[entry_index].observed_at
        existing.entry_close = entry_price
        existing.exit_at = None
        existing.exit_close = None
        existing.stock_return = None
        existing.benchmark_return = None
        existing.excess_return = None
        existing.max_favorable_return = None
        existing.max_drawdown = None
        existing.validation_payload = {
            "available_forward_bars": available_forward_bars,
            "required_forward_bars": horizon,
            "pending_reason": (
                f"Official entry close after signal availability is {bars[entry_index].observed_at.isoformat()}; "
                f"needs {horizon} forward trading-day close(s), currently has {available_forward_bars}."
            ),
            "validation_mode": SHORTPICK_OFFICIAL_VALIDATION_MODE,
            "official_validation": False,
            "tradeability_status": SHORTPICK_OFFICIAL_TRADEABILITY_STATUS,
            "tradeability_evidence": tradeability,
            "signal_available_at": signal_available_at.isoformat(),
            "signal_trade_day": signal_trade_day.isoformat(),
            "entry_trade_day": bars[entry_index].observed_at.date().isoformat(),
            "entry_price": entry_price,
            "entry_price_source": entry_price_source,
            "market_data_sync": market_sync or {},
            **candidate_metadata,
        }
        return existing
    window = bars[entry_index : exit_index + 1]
    entry = window[0]
    exit_bar = window[-1]
    returns = [(bar.close_price / entry_price) - 1 for bar in window if entry_price]
    stock_return = (exit_bar.close_price / entry_price) - 1 if entry_price else None
    benchmark_maps = benchmark_maps or benchmark_close_maps(session)
    benchmark_returns = _shortpick_benchmark_returns(
        benchmark_maps=benchmark_maps,
        entry_day=entry.observed_at.date(),
        exit_day=exit_bar.observed_at.date(),
    )
    primary = _shortpick_primary_benchmark()
    primary_return = benchmark_returns.get(primary["symbol"], {}).get("return")
    benchmark_dimensions = _shortpick_benchmark_dimensions(
        session,
        candidate=candidate,
        stock_return=stock_return,
        benchmark_returns=benchmark_returns,
        entry_day=entry.observed_at.date(),
        exit_day=exit_bar.observed_at.date(),
        include_sector_benchmark=include_sector_benchmark,
    )
    frozen_exit_tracks = (
        _shortpick_frozen_exit_track_results(candidate=candidate, window=window, benchmark_maps=benchmark_maps)
        if horizon == SHORTPICK_FROZEN_PAPER_MAX_HOLDING_DAYS
        else []
    )
    if primary_return is None:
        existing.status = "pending_benchmark_data"
    else:
        existing.status = "completed"
    existing.entry_at = entry.observed_at
    existing.exit_at = exit_bar.observed_at
    existing.entry_close = entry_price
    existing.exit_close = exit_bar.close_price
    existing.stock_return = stock_return
    existing.benchmark_return = primary_return
    existing.excess_return = None if stock_return is None or primary_return is None else stock_return - primary_return
    existing.max_favorable_return = max(returns) if returns else None
    existing.max_drawdown = min(returns) if returns else None
    existing.validation_payload = {
        "benchmark": primary,
        "benchmark_returns": benchmark_returns,
        "benchmark_dimensions": benchmark_dimensions,
        "available_benchmark_dimensions": [
            key for key, value in benchmark_dimensions.items() if value.get("status") == "available"
        ],
        "validation_mode": SHORTPICK_OFFICIAL_VALIDATION_MODE,
        "official_validation": primary_return is not None,
        "tradeability_status": SHORTPICK_OFFICIAL_TRADEABILITY_STATUS,
        "tradeability_evidence": tradeability,
        "signal_available_at": signal_available_at.isoformat(),
        "signal_trade_day": signal_trade_day.isoformat(),
        "entry_trade_day": entry.observed_at.date().isoformat(),
        "exit_trade_day": exit_bar.observed_at.date().isoformat(),
        "entry_price": entry_price,
        "entry_price_source": entry_price_source,
        "paper_tracking_exit_tracks": frozen_exit_tracks,
        "paper_tracking_exit_track_note": (
            "All holding windows are counted in trading days; 10% take-profit uses daily high touch as a paper-tracking approximation."
            if frozen_exit_tracks
            else None
        ),
        "market_data_sync": market_sync or {},
        "note": "后验验证只读取行情，不回写主量化推荐或模拟盘。",
        **candidate_metadata,
    }
    return existing


def _shortpick_candidate_validation_metadata(candidate: ShortpickCandidate) -> dict[str, Any]:
    payload = candidate.candidate_payload if isinstance(candidate.candidate_payload, dict) else {}
    metadata: dict[str, Any] = {
        "experiment_mode": payload.get("experiment_mode"),
        "baseline_family": payload.get("baseline_family") or "llm",
        "candidate_origin": payload.get("candidate_origin") or "llm_open_discovery",
        "official_sample_eligible": payload.get("official_sample_eligible", True),
    }
    for key in ("source_packet_id", "source_packet_hash", "leakage_audit_status", "leakage_audit_reasons"):
        if key in payload:
            metadata[key] = payload.get(key)
    return metadata


def _shortpick_signal_available_at(
    run: ShortpickExperimentRun,
    round_record: ShortpickModelRound | None,
) -> datetime:
    """Return the effective signal timestamp for validation.

    Historical backfills and tests can create a run_date in the past while the
    actual row is inserted much later. In that case, treat the requested
    run_date as an after-close signal day instead of letting test/runtime repair
    timestamps push the entry arbitrarily forward.
    """

    candidate_time = round_record.completed_at if round_record is not None and round_record.completed_at else None
    candidate_time = candidate_time or run.completed_at or run.started_at
    if run.trigger_source != "scheduled_cli" and candidate_time.date() != run.run_date:
        return datetime(run.run_date.year, run.run_date.month, run.run_date.day, 15, 30, tzinfo=UTC)
    return candidate_time


def _shortpick_entry_tradeability(
    *,
    candidate: ShortpickCandidate,
    bars: list[MarketBar],
    entry_index: int,
) -> dict[str, Any]:
    entry = bars[entry_index]
    previous = bars[entry_index - 1] if entry_index > 0 else None
    limit_band = _infer_shortpick_limit_band(candidate)
    entry_price_source = _shortpick_entry_price_source(candidate)
    entry_price = _shortpick_entry_execution_price(candidate=candidate, entry=entry)
    evidence: dict[str, Any] = {
        "tradeability_status": SHORTPICK_OFFICIAL_TRADEABILITY_STATUS,
        "entry_price_source": entry_price_source,
        "entry_price": entry_price,
        "entry_open": entry.open_price,
        "entry_high": entry.high_price,
        "entry_low": entry.low_price,
        "entry_close": entry.close_price,
        "entry_trade_day": entry.observed_at.date().isoformat(),
        "inferred_limit_band": limit_band,
    }
    if previous is not None:
        day_return = (entry.close_price / previous.close_price) - 1 if previous.close_price else None
        open_return = (entry.open_price / previous.close_price) - 1 if previous.close_price else None
        evidence.update(
            {
                "previous_close": previous.close_price,
                "previous_trade_day": previous.observed_at.date().isoformat(),
                "entry_day_return": day_return,
                "entry_open_return": open_return,
            }
        )
        one_price = (
            _float_near(entry.open_price, entry.high_price)
            and _float_near(entry.high_price, entry.low_price)
            and _float_near(entry.low_price, entry.close_price)
        )
        if (
            entry_price_source == SHORTPICK_ENTRY_PRICE_SOURCE_OPEN
            and open_return is not None
            and open_return >= limit_band * 0.95
        ):
            evidence["tradeability_status"] = "entry_unfillable_limit_up"
            evidence["reason"] = "Entry open appears to be near limit-up, so open-entry research cannot assume a fill."
        elif (
            entry_price_source == SHORTPICK_ENTRY_PRICE_SOURCE_INTRADAY
            and entry_price is not None
            and previous.close_price
            and (entry_price / previous.close_price) - 1 >= limit_band * 0.95
        ):
            evidence["tradeability_status"] = "entry_unfillable_limit_up"
            evidence["reason"] = "Intraday entry price appears to be near limit-up, so same-day paper tracking cannot assume a fill."
        elif day_return is not None and one_price and day_return >= limit_band * 0.95:
            evidence["tradeability_status"] = "entry_unfillable_limit_up"
            evidence["reason"] = "Entry day appears to be one-price limit-up, so official validation cannot assume a fill."
    else:
        evidence["tradeability_status"] = "tradeability_uncertain"
        evidence["reason"] = "No previous close exists to infer limit-up fillability."
    return evidence


def _shortpick_entry_price_source(candidate: ShortpickCandidate) -> str:
    payload = candidate.candidate_payload if isinstance(candidate.candidate_payload, dict) else {}
    source = str(payload.get("paper_tracking_entry_price_source") or "")
    if source == SHORTPICK_ENTRY_PRICE_SOURCE_OPEN:
        return SHORTPICK_ENTRY_PRICE_SOURCE_OPEN
    if source == SHORTPICK_ENTRY_PRICE_SOURCE_INTRADAY:
        return SHORTPICK_ENTRY_PRICE_SOURCE_INTRADAY
    overlay = payload.get("market_factor_overlay") if isinstance(payload.get("market_factor_overlay"), dict) else {}
    if str(overlay.get("entry_price_source") or "") == SHORTPICK_ENTRY_PRICE_SOURCE_OPEN:
        return SHORTPICK_ENTRY_PRICE_SOURCE_OPEN
    if str(overlay.get("entry_price_source") or "") == SHORTPICK_ENTRY_PRICE_SOURCE_INTRADAY:
        return SHORTPICK_ENTRY_PRICE_SOURCE_INTRADAY
    return SHORTPICK_ENTRY_PRICE_SOURCE_CLOSE


def _shortpick_entry_execution_price(*, candidate: ShortpickCandidate, entry: MarketBar) -> float | None:
    source = _shortpick_entry_price_source(candidate)
    if source == SHORTPICK_ENTRY_PRICE_SOURCE_OPEN:
        return entry.open_price
    if source == SHORTPICK_ENTRY_PRICE_SOURCE_INTRADAY:
        payload = candidate.candidate_payload if isinstance(candidate.candidate_payload, dict) else {}
        captured = _coerce_float(payload.get("paper_tracking_entry_price"))
        return captured if captured is not None and captured > 0 else entry.close_price
    return entry.close_price


def _infer_shortpick_limit_band(candidate: ShortpickCandidate) -> float:
    return _shortpick_limit_band_for_symbol(candidate.symbol, candidate.name)


def _float_near(left: float | None, right: float | None, *, tolerance: float = 1e-6) -> bool:
    if left is None or right is None:
        return False
    return abs(float(left) - float(right)) <= tolerance


def _is_frozen_paper_tracking_candidate(candidate: ShortpickCandidate) -> bool:
    payload = candidate.candidate_payload if isinstance(candidate.candidate_payload, dict) else {}
    return (
        candidate.research_priority == "market_factor_frozen_paper"
        or payload.get("tracking_role") == "frozen_paper_primary"
        or payload.get("frozen_paper_strategy") is not None
    )


def _is_llm_paper_control_candidate(candidate: ShortpickCandidate) -> bool:
    payload = candidate.candidate_payload if isinstance(candidate.candidate_payload, dict) else {}
    return payload.get("tracking_role") == SHORTPICK_LLM_PAPER_CONTROL_ROLE or payload.get("llm_paper_control") is not None


def _is_market_factor_paper_control_candidate(candidate: ShortpickCandidate) -> bool:
    payload = candidate.candidate_payload if isinstance(candidate.candidate_payload, dict) else {}
    return str(payload.get("tracking_role") or "") in SHORTPICK_MARKET_FACTOR_PAPER_CONTROL_ROLES


def _is_paper_tracking_exit_track_candidate(candidate: ShortpickCandidate) -> bool:
    return (
        _is_frozen_paper_tracking_candidate(candidate)
        or _is_llm_paper_control_candidate(candidate)
        or _is_market_factor_paper_control_candidate(candidate)
    )


def _close_return(entry_price: float | None, exit_price: float | None) -> float | None:
    if not entry_price or exit_price is None:
        return None
    return (exit_price / entry_price) - 1


def _shortpick_exit_track_payload(
    *,
    key: str,
    label: str,
    entry: MarketBar,
    entry_price: float | None,
    entry_price_source: str,
    window: list[MarketBar],
    exit_index: int,
    exit_price: float | None,
    exit_reason: str,
    benchmark_maps: dict[str, dict[date, float]],
    execution_assumption: str = "close_price",
) -> dict[str, Any]:
    exit_bar = window[exit_index]
    stock_return = _close_return(entry_price, exit_price)
    close_returns = [
        _close_return(entry_price, bar.close_price)
        for bar in window[: exit_index + 1]
        if entry_price and bar.close_price is not None
    ]
    benchmark_returns = _shortpick_benchmark_returns(
        benchmark_maps=benchmark_maps,
        entry_day=entry.observed_at.date(),
        exit_day=exit_bar.observed_at.date(),
    )
    primary = _shortpick_primary_benchmark()
    primary_return = benchmark_returns.get(primary["symbol"], {}).get("return")
    return {
        "key": key,
        "label": label,
        "entry_trade_day": entry.observed_at.date().isoformat(),
        "exit_trade_day": exit_bar.observed_at.date().isoformat(),
        "holding_trading_days": exit_index,
        "entry_price": entry_price,
        "entry_price_source": entry_price_source,
        "entry_open": entry.open_price,
        "entry_close": entry.close_price,
        "exit_price": exit_price,
        "exit_close": exit_bar.close_price,
        "exit_reason": exit_reason,
        "execution_assumption": execution_assumption,
        "stock_return": stock_return,
        "benchmark_return": primary_return,
        "excess_return": None if stock_return is None or primary_return is None else stock_return - primary_return,
        "max_favorable_return": max(close_returns) if close_returns else None,
        "max_drawdown": min(close_returns) if close_returns else None,
        "benchmark": primary,
    }


def _shortpick_conditional_exit_index(window: list[MarketBar], *, entry_price: float | None = None) -> tuple[int, str]:
    max_index = min(SHORTPICK_FROZEN_PAPER_MAX_HOLDING_DAYS, len(window) - 1)
    start_index = min(SHORTPICK_FROZEN_PAPER_CHECK_START_DAY, max_index)
    for index in range(start_index, max_index + 1):
        current = window[index]
        if not entry_price or current.close_price is None:
            continue
        stock_return = (current.close_price / entry_price) - 1
        if stock_return <= -SHORTPICK_FROZEN_PAPER_STOP_LOSS_PCT:
            return index, "close_stop_loss_8pct"
        recent = [bar.close_price for bar in window[max(0, index - 2) : index + 1] if bar.close_price is not None]
        recent_avg = sum(recent) / len(recent) if recent else None
        previous_close = window[index - 1].close_price if index > 0 else None
        if recent_avg is not None and previous_close is not None and current.close_price < recent_avg and current.close_price < previous_close:
            return index, "trend_check_failed_after_day5"
        peak_close = max((bar.close_price for bar in window[: index + 1] if bar.close_price is not None), default=None)
        if (
            peak_close
            and (current.close_price / peak_close) - 1 <= -SHORTPICK_FROZEN_PAPER_PEAK_GIVEBACK_PCT
            and stock_return < SHORTPICK_FROZEN_PAPER_WEAK_REBOUND_RETURN_PCT
        ):
            return index, "peak_giveback_or_weak_rebound"
    return max_index, "max_10d_reached"


def _shortpick_frozen_exit_track_results(
    *,
    candidate: ShortpickCandidate,
    window: list[MarketBar],
    benchmark_maps: dict[str, dict[date, float]],
) -> list[dict[str, Any]]:
    if not _is_paper_tracking_exit_track_candidate(candidate):
        return []
    if len(window) <= SHORTPICK_FROZEN_PAPER_MAX_HOLDING_DAYS:
        return []
    entry = window[0]
    entry_price = _shortpick_entry_execution_price(candidate=candidate, entry=entry)
    entry_price_source = _shortpick_entry_price_source(candidate)
    max_index = SHORTPICK_FROZEN_PAPER_MAX_HOLDING_DAYS
    tracks = [
        _shortpick_exit_track_payload(
            key="mechanical_5d",
            label="机械5日",
            entry=entry,
            entry_price=entry_price,
            entry_price_source=entry_price_source,
            window=window,
            exit_index=SHORTPICK_FROZEN_PAPER_CHECK_START_DAY,
            exit_price=window[SHORTPICK_FROZEN_PAPER_CHECK_START_DAY].close_price,
            exit_reason="mechanical_5d_close",
            benchmark_maps=benchmark_maps,
        ),
        _shortpick_exit_track_payload(
            key="mechanical_10d",
            label="机械10日",
            entry=entry,
            entry_price=entry_price,
            entry_price_source=entry_price_source,
            window=window,
            exit_index=max_index,
            exit_price=window[max_index].close_price,
            exit_reason="mechanical_10d_close",
            benchmark_maps=benchmark_maps,
        ),
    ]
    conditional_index, conditional_reason = _shortpick_conditional_exit_index(
        window[: max_index + 1],
        entry_price=entry_price,
    )
    tracks.append(
        _shortpick_exit_track_payload(
            key="conditional_5_to_10d",
            label="5日后条件检查",
            entry=entry,
            entry_price=entry_price,
            entry_price_source=entry_price_source,
            window=window,
            exit_index=conditional_index,
            exit_price=window[conditional_index].close_price,
            exit_reason=conditional_reason,
            benchmark_maps=benchmark_maps,
        )
    )
    take_profit_price = entry_price * (1 + SHORTPICK_FROZEN_PAPER_TAKE_PROFIT_PCT) if entry_price else None
    take_profit_index = max_index
    take_profit_reason = "max_10d_reached"
    take_profit_exit_price = window[max_index].close_price
    if take_profit_price is not None:
        for index, bar in enumerate(window[1 : max_index + 1], start=1):
            if bar.high_price is not None and bar.high_price >= take_profit_price:
                take_profit_index = index
                take_profit_reason = "take_profit_10pct_touched"
                take_profit_exit_price = take_profit_price
                break
    tracks.append(
        _shortpick_exit_track_payload(
            key="take_profit_10pct",
            label="10%触达止盈",
            entry=entry,
            entry_price=entry_price,
            entry_price_source=entry_price_source,
            window=window,
            exit_index=take_profit_index,
            exit_price=take_profit_exit_price,
            exit_reason=take_profit_reason,
            benchmark_maps=benchmark_maps,
            execution_assumption="daily_high_touch_price" if take_profit_reason == "take_profit_10pct_touched" else "close_price",
        )
    )
    return tracks


def _daily_bars_for_symbol(session: Session, symbol: str) -> list[MarketBar]:
    stock = session.scalar(select(Stock).where(Stock.symbol == symbol))
    if stock is None:
        return []
    return session.scalars(
        select(MarketBar)
        .where(MarketBar.stock_id == stock.id, MarketBar.timeframe == "1d")
        .order_by(MarketBar.observed_at.asc(), MarketBar.id.asc())
    ).all()


def _sync_shortpick_benchmarks(session: Session) -> dict[str, Any]:
    existing = benchmark_close_maps(session)
    today = datetime.now(UTC).date()
    current = {
        definition["symbol"]: max(existing.get(definition["symbol"], {}) or {}, default=None)
        for definition in _shortpick_benchmark_definitions()
    }
    if current and all(day is not None and day >= today for day in current.values()):
        return {
            "status": "existing_current",
            "latest_trade_days": {symbol: day.isoformat() for symbol, day in current.items() if day is not None},
        }
    try:
        return sync_benchmark_index_bars(session)
    except Exception as exc:
        return {"status": "error", "reason": str(exc)}


def _sync_shortpick_candidate_market_data(session: Session, candidate: ShortpickCandidate) -> dict[str, Any]:
    existing_bars = _daily_bars_for_symbol(session, candidate.symbol)
    latest_day = existing_bars[-1].observed_at.date() if existing_bars else None
    if latest_day is not None and latest_day >= datetime.now(UTC).date():
        return {"status": "existing_current", "bars": len(existing_bars), "latest_trade_day": latest_day.isoformat()}
    try:
        stock = _ensure_shortpick_stock(session, candidate)
        fetch = _fetch_shortpick_daily_market_data(session, candidate.symbol)
        upserted = _upsert_shortpick_market_bars(session, stock=stock, bars=fetch.bars)
    except Exception as exc:
        return {
            "status": "error",
            "reason": str(exc),
            "existing_bars": len(existing_bars),
            "latest_trade_day": latest_day.isoformat() if latest_day else None,
        }
    refreshed_bars = _daily_bars_for_symbol(session, candidate.symbol)
    refreshed_latest_day = refreshed_bars[-1].observed_at.date() if refreshed_bars else None
    return {
        "status": "ok",
        "provider_name": fetch.provider_name,
        "upserted_bars": upserted,
        "bars": len(refreshed_bars),
        "latest_trade_day": refreshed_latest_day.isoformat() if refreshed_latest_day else None,
    }


def _ensure_shortpick_stock(session: Session, candidate: ShortpickCandidate) -> Stock:
    existing = session.scalar(select(Stock).where(Stock.symbol == candidate.symbol))
    profile = resolve_stock_profile(session, symbol=candidate.symbol, preferred_name=candidate.name)
    ticker, _, market = candidate.symbol.partition(".")
    exchange = market.upper() if market else ("SH" if ticker.startswith(("5", "6", "9")) else "SZ")
    if existing is not None:
        existing.name = profile.name or candidate.name or existing.name
        existing.provider_symbol = existing.provider_symbol or candidate.symbol
        existing.listed_date = existing.listed_date or profile.listed_date
        profile_payload = dict(existing.profile_payload or {})
        profile_payload.update(
            {
                "shortpick_profile_source": profile.source,
                "industry": profile.industry or profile_payload.get("industry"),
                "template_key": profile.template_key or profile_payload.get("template_key"),
            }
        )
        existing.profile_payload = profile_payload
        session.flush()
        return existing
    stock_payload = {
        "symbol": candidate.symbol,
        "name": profile.name or candidate.name or candidate.symbol,
        "listed_date": profile.listed_date,
        "profile_source": profile.source,
    }
    lineage = build_lineage(
        stock_payload,
        source_uri=f"shortpick://stock/{candidate.symbol}",
        license_tag="internal-derived",
        usage_scope="internal_research",
        redistribution_scope="none",
    )
    stock = Stock(
        symbol=candidate.symbol,
        ticker=ticker,
        exchange=exchange,
        name=str(stock_payload["name"]),
        provider_symbol=candidate.symbol,
        listed_date=profile.listed_date,
        delisted_date=None,
        status="active",
        profile_payload={
            "industry": profile.industry,
            "template_key": profile.template_key,
            "profile_source": profile.source,
            "shortpick_lab_only": True,
        },
        **lineage,
    )
    session.add(stock)
    session.flush()
    return stock


def _fetch_shortpick_daily_market_data(session: Session, symbol: str) -> Any:
    for fetcher in (_fetch_daily_bars_tushare, lambda active_session, active_symbol: _fetch_daily_bars_akshare(active_symbol)):
        try:
            result = fetcher(session, symbol)
        except Exception:
            result = None
        if result is not None and result.bars:
            return result
    raise RuntimeError(f"{symbol} shortpick market sync returned no daily bars.")


def _upsert_shortpick_market_bars(session: Session, *, stock: Stock, bars: list[dict[str, Any]]) -> int:
    upserted = 0
    for bar_record in bars:
        bar_key = str(bar_record["bar_key"])
        existing = session.scalar(select(MarketBar).where(MarketBar.bar_key == bar_key))
        values = {
            "stock_id": stock.id,
            "timeframe": bar_record["timeframe"],
            "observed_at": bar_record["observed_at"],
            "open_price": bar_record["open_price"],
            "high_price": bar_record["high_price"],
            "low_price": bar_record["low_price"],
            "close_price": bar_record["close_price"],
            "volume": bar_record["volume"],
            "amount": bar_record["amount"],
            "turnover_rate": bar_record.get("turnover_rate"),
            "adj_factor": bar_record.get("adj_factor"),
            "total_mv": bar_record.get("total_mv"),
            "circ_mv": bar_record.get("circ_mv"),
            "pe_ttm": bar_record.get("pe_ttm"),
            "pb": bar_record.get("pb"),
            "raw_payload": {
                **dict(bar_record.get("raw_payload") or {}),
                "shortpick_lab_only": True,
            },
            "source_uri": bar_record["source_uri"],
            "license_tag": bar_record["license_tag"],
            "usage_scope": bar_record["usage_scope"],
            "redistribution_scope": bar_record["redistribution_scope"],
            "lineage_hash": bar_record["lineage_hash"],
        }
        if existing is None:
            session.add(MarketBar(bar_key=bar_key, **values))
        else:
            for key, value in values.items():
                setattr(existing, key, value)
        upserted += 1
    session.flush()
    return upserted


def _shortpick_primary_benchmark() -> dict[str, str]:
    definition = CSI_BENCHMARKS[SHORTPICK_PRIMARY_BENCHMARK_ID]
    return {
        "benchmark_id": SHORTPICK_PRIMARY_BENCHMARK_ID,
        "symbol": definition["symbol"],
        "label": definition["label"],
    }


def _shortpick_benchmark_definitions() -> list[dict[str, str]]:
    definitions = [_shortpick_primary_benchmark()]
    seen = {definitions[0]["symbol"]}
    for benchmark_id in SHORTPICK_RESEARCH_BENCHMARK_IDS:
        definition = CSI_BENCHMARKS.get(benchmark_id)
        if definition is None or definition["symbol"] in seen:
            continue
        seen.add(definition["symbol"])
        definitions.append(
            {
                "benchmark_id": benchmark_id,
                "symbol": definition["symbol"],
                "label": definition["label"],
            }
        )
    return definitions


def _shortpick_benchmark_returns(
    *,
    benchmark_maps: dict[str, dict[Any, float]],
    entry_day: date,
    exit_day: date,
) -> dict[str, dict[str, Any]]:
    returns: dict[str, dict[str, Any]] = {}
    for definition in _shortpick_benchmark_definitions():
        close_map = benchmark_maps.get(definition["symbol"], {})
        benchmark_return = _return_between_close_map(close_map, entry_day=entry_day, exit_day=exit_day)
        returns[definition["symbol"]] = {
            **definition,
            "return": benchmark_return,
            "status": "available" if benchmark_return is not None else "missing_window",
        }
    return returns


def _benchmark_dimension_from_index(
    *,
    dimension_key: str,
    definition: dict[str, str],
    stock_return: float | None,
    benchmark_return: float | None,
) -> dict[str, Any]:
    status = "available" if benchmark_return is not None else "pending_benchmark_data"
    reason = None if benchmark_return is not None else f"{definition['label']} missing entry or exit benchmark close."
    return {
        "dimension_key": dimension_key,
        "benchmark_id": definition["benchmark_id"],
        "label": definition["label"],
        "benchmark_label": definition["label"],
        "symbol": definition["symbol"],
        "symbol_or_scope": definition["symbol"],
        "benchmark_return": benchmark_return,
        "excess_return": (
            None if stock_return is None or benchmark_return is None else stock_return - benchmark_return
        ),
        "status": status,
        "reason": reason,
    }


def _stock_sector_identity(session: Session, symbol: str) -> dict[str, Any] | None:
    stock = session.scalar(select(Stock).where(Stock.symbol == symbol))
    if stock is None:
        return None
    membership = session.scalar(
        select(SectorMembership)
        .where(SectorMembership.stock_id == stock.id, SectorMembership.is_primary.is_(True))
        .order_by(SectorMembership.effective_from.desc(), SectorMembership.id.desc())
    )
    if membership is not None:
        return {
            "source": "sector_membership",
            "stock_id": stock.id,
            "sector_code": membership.sector.sector_code,
            "label": membership.sector.name,
        }
    profile_payload = stock.profile_payload if isinstance(stock.profile_payload, dict) else {}
    template_key = profile_payload.get("template_key")
    industry = profile_payload.get("industry")
    if not template_key and not industry:
        return None
    sector_code = f"profile:{template_key or industry}"
    return {
        "source": "profile_payload",
        "stock_id": stock.id,
        "sector_code": sector_code,
        "template_key": template_key,
        "industry": industry,
        "label": str(industry or template_key),
    }


def _sector_identity_match_text(sector_identity: dict[str, Any]) -> str:
    parts = [
        sector_identity.get("sector_code"),
        sector_identity.get("label"),
        sector_identity.get("template_key"),
        sector_identity.get("industry"),
    ]
    text = " ".join(str(part) for part in parts if part)
    return text.replace("profile:", "").replace("Ⅱ", "").lower()


def _representative_sector_peers(sector_identity: dict[str, Any], *, exclude_symbol: str) -> list[tuple[str, str]]:
    match_text = _sector_identity_match_text(sector_identity)
    peers: list[tuple[str, str]] = []
    for key, symbols in SHORTPICK_SECTOR_PEER_UNIVERSE.items():
        normalized_key = key.replace("Ⅱ", "").lower()
        if normalized_key not in match_text and match_text not in normalized_key:
            continue
        for symbol, name in symbols:
            normalized_symbol = _normalize_symbol(symbol)
            if normalized_symbol == exclude_symbol:
                continue
            if normalized_symbol not in [item[0] for item in peers]:
                peers.append((normalized_symbol, name))
        if len(peers) >= SHORTPICK_TARGET_SECTOR_PEER_SYMBOLS:
            break
    return peers[:SHORTPICK_TARGET_SECTOR_PEER_SYMBOLS]


def _sector_peer_symbols_from_db(session: Session, candidate: ShortpickCandidate, sector_identity: dict[str, Any]) -> list[str]:
    if sector_identity["source"] == "sector_membership":
        memberships = session.scalars(
            select(SectorMembership).where(
                SectorMembership.sector.has(sector_code=sector_identity["sector_code"]),
                SectorMembership.is_primary.is_(True),
            )
        ).all()
        symbols = [membership.stock.symbol for membership in memberships if membership.stock.symbol != candidate.symbol]
        return sorted(set(symbols))

    stocks = session.scalars(select(Stock).where(Stock.symbol != candidate.symbol)).all()
    symbols: list[str] = []
    target_template = sector_identity.get("template_key")
    target_industry = sector_identity.get("industry")
    for stock in stocks:
        profile_payload = stock.profile_payload if isinstance(stock.profile_payload, dict) else {}
        if target_template and profile_payload.get("template_key") == target_template:
            symbols.append(stock.symbol)
            continue
        if target_industry and profile_payload.get("industry") == target_industry:
            symbols.append(stock.symbol)
    return sorted(set(symbols))


def _sector_peer_symbols(session: Session, candidate: ShortpickCandidate, sector_identity: dict[str, Any]) -> list[str]:
    symbols = set(_sector_peer_symbols_from_db(session, candidate, sector_identity))
    for symbol, _name in _representative_sector_peers(sector_identity, exclude_symbol=candidate.symbol):
        symbols.add(symbol)
    return sorted(symbols)


def _ensure_shortpick_sector_peer_universe(
    session: Session,
    *,
    candidate: ShortpickCandidate,
    sector_identity: dict[str, Any],
    entry_day: date,
    exit_day: date,
) -> dict[str, Any]:
    representatives = _representative_sector_peers(sector_identity, exclude_symbol=candidate.symbol)
    if not representatives:
        return {"status": "skipped", "reason": "no_representative_sector_universe"}
    attempted = 0
    refreshed = 0
    errors: list[dict[str, str]] = []
    for symbol, name in representatives:
        close_map = _close_map_for_symbol(session, symbol)
        if _return_between_close_map(close_map, entry_day=entry_day, exit_day=exit_day) is not None:
            continue
        attempted += 1
        try:
            peer_stock = _ensure_shortpick_stock(session, _ShortpickPeerCandidate(symbol=symbol, name=name))  # type: ignore[arg-type]
            profile_payload = dict(peer_stock.profile_payload or {})
            profile_payload.update(
                {
                    "shortpick_sector_peer_universe": True,
                    "shortpick_sector_peer_scope": sector_identity["sector_code"],
                    "industry": profile_payload.get("industry") or sector_identity.get("industry") or sector_identity.get("label"),
                    "template_key": profile_payload.get("template_key") or sector_identity.get("template_key"),
                }
            )
            peer_stock.profile_payload = profile_payload
            fetch = _fetch_shortpick_daily_market_data(session, symbol)
            refreshed += _upsert_shortpick_market_bars(session, stock=peer_stock, bars=fetch.bars)
        except Exception as exc:
            errors.append({"symbol": symbol, "reason": str(exc)})
    return {
        "status": "ok" if not errors else "partial",
        "target_peer_symbol_count": len(representatives),
        "attempted_refresh_count": attempted,
        "upserted_bar_count": refreshed,
        "errors": errors[:5],
    }


def _close_map_for_symbol(session: Session, symbol: str) -> dict[date, float]:
    rows = session.execute(
        select(MarketBar.observed_at, MarketBar.close_price)
        .join(Stock, MarketBar.stock_id == Stock.id)
        .where(Stock.symbol == symbol, MarketBar.timeframe == "1d")
        .order_by(MarketBar.observed_at.asc())
    ).all()
    return {observed_at.date(): float(close_price) for observed_at, close_price in rows}


def _sector_equal_weight_return(
    session: Session,
    *,
    peer_symbols: list[str],
    entry_day: date,
    exit_day: date,
) -> tuple[float | None, list[str]]:
    returns: list[float] = []
    contributing_symbols: list[str] = []
    for symbol in peer_symbols:
        peer_return = _return_between_close_map(_close_map_for_symbol(session, symbol), entry_day=entry_day, exit_day=exit_day)
        if peer_return is None:
            continue
        returns.append(peer_return)
        contributing_symbols.append(symbol)
    return (_mean_or_none(returns), contributing_symbols)


def _shortpick_sector_benchmark_dimension(
    session: Session,
    *,
    candidate: ShortpickCandidate,
    stock_return: float | None,
    entry_day: date,
    exit_day: date,
) -> dict[str, Any]:
    sector_identity = _stock_sector_identity(session, candidate.symbol)
    if sector_identity is None:
        return {
            "dimension_key": SHORTPICK_BENCHMARK_DIMENSION_SECTOR,
            "benchmark_id": SHORTPICK_BENCHMARK_DIMENSION_SECTOR,
            "label": "同板块",
            "benchmark_label": "同板块",
            "symbol": None,
            "symbol_or_scope": None,
            "benchmark_return": None,
            "excess_return": None,
            "status": "pending_sector_mapping",
            "reason": "缺板块映射，暂不能构造同板块等权基准。",
            "peer_symbol_count": 0,
            "contributing_peer_symbol_count": 0,
        }
    initial_peer_symbols = _sector_peer_symbols_from_db(session, candidate, sector_identity)
    _initial_return, initial_contributing_symbols = _sector_equal_weight_return(
        session,
        peer_symbols=initial_peer_symbols,
        entry_day=entry_day,
        exit_day=exit_day,
    )
    if len(initial_contributing_symbols) < SHORTPICK_MIN_SECTOR_PEER_SYMBOLS:
        peer_universe_sync = _ensure_shortpick_sector_peer_universe(
            session,
            candidate=candidate,
            sector_identity=sector_identity,
            entry_day=entry_day,
            exit_day=exit_day,
        )
    else:
        peer_universe_sync = {
            "status": "skipped",
            "reason": "existing_sector_peers_available",
            "contributing_peer_symbol_count": len(initial_contributing_symbols),
        }
    peer_symbols = _sector_peer_symbols(session, candidate, sector_identity)
    if len(peer_symbols) < SHORTPICK_MIN_SECTOR_PEER_SYMBOLS:
        return {
            "dimension_key": SHORTPICK_BENCHMARK_DIMENSION_SECTOR,
            "benchmark_id": SHORTPICK_BENCHMARK_DIMENSION_SECTOR,
            "label": f"同板块：{sector_identity['label']}",
            "benchmark_label": f"同板块：{sector_identity['label']}",
            "symbol": None,
            "symbol_or_scope": sector_identity["sector_code"],
            "benchmark_return": None,
            "excess_return": None,
            "status": "pending_sector_peer_baseline",
            "reason": f"同板块可用同行样本 {len(peer_symbols)}/{SHORTPICK_MIN_SECTOR_PEER_SYMBOLS}，暂不能构造等权基准。",
            "peer_symbol_count": len(peer_symbols),
            "contributing_peer_symbol_count": 0,
            "peer_symbols": peer_symbols,
            "peer_universe_target_count": SHORTPICK_TARGET_SECTOR_PEER_SYMBOLS,
            "peer_universe_sync": peer_universe_sync,
        }
    benchmark_return, contributing_symbols = _sector_equal_weight_return(
        session,
        peer_symbols=peer_symbols,
        entry_day=entry_day,
        exit_day=exit_day,
    )
    status = "available" if benchmark_return is not None else "pending_sector_peer_baseline"
    return {
        "dimension_key": SHORTPICK_BENCHMARK_DIMENSION_SECTOR,
        "benchmark_id": SHORTPICK_BENCHMARK_DIMENSION_SECTOR,
        "label": f"同板块：{sector_identity['label']}",
        "benchmark_label": f"同板块：{sector_identity['label']}",
        "symbol": None,
        "symbol_or_scope": sector_identity["sector_code"],
        "benchmark_return": benchmark_return,
        "excess_return": None if stock_return is None or benchmark_return is None else stock_return - benchmark_return,
        "status": status,
        "reason": None if status == "available" else "同板块同行缺少入场或退出日附近的日线收盘。",
        "peer_symbol_count": len(peer_symbols),
        "contributing_peer_symbol_count": len(contributing_symbols),
        "peer_symbols": peer_symbols,
        "contributing_peer_symbols": contributing_symbols,
        "peer_universe_target_count": SHORTPICK_TARGET_SECTOR_PEER_SYMBOLS,
        "peer_universe_sync": peer_universe_sync,
    }


def _shortpick_benchmark_dimensions(
    session: Session,
    *,
    candidate: ShortpickCandidate,
    stock_return: float | None,
    benchmark_returns: dict[str, dict[str, Any]],
    entry_day: date,
    exit_day: date,
    include_sector_benchmark: bool = True,
) -> dict[str, dict[str, Any]]:
    hs300 = _shortpick_primary_benchmark()
    csi1000_definition = {
        "benchmark_id": "CSI1000",
        "symbol": CSI_BENCHMARKS["CSI1000"]["symbol"],
        "label": CSI_BENCHMARKS["CSI1000"]["label"],
    }
    dimensions = {
        SHORTPICK_BENCHMARK_DIMENSION_HS300: _benchmark_dimension_from_index(
            dimension_key=SHORTPICK_BENCHMARK_DIMENSION_HS300,
            definition=hs300,
            stock_return=stock_return,
            benchmark_return=benchmark_returns.get(hs300["symbol"], {}).get("return"),
        ),
        SHORTPICK_BENCHMARK_DIMENSION_CSI1000: _benchmark_dimension_from_index(
            dimension_key=SHORTPICK_BENCHMARK_DIMENSION_CSI1000,
            definition=csi1000_definition,
            stock_return=stock_return,
            benchmark_return=benchmark_returns.get(csi1000_definition["symbol"], {}).get("return"),
        ),
    }
    dimensions[SHORTPICK_BENCHMARK_DIMENSION_SECTOR] = (
        _shortpick_sector_benchmark_dimension(
            session,
            candidate=candidate,
            stock_return=stock_return,
            entry_day=entry_day,
            exit_day=exit_day,
        )
        if include_sector_benchmark
        else {
            "dimension_key": SHORTPICK_BENCHMARK_DIMENSION_SECTOR,
            "benchmark_id": SHORTPICK_BENCHMARK_DIMENSION_SECTOR,
            "label": "同板块",
            "benchmark_label": "同板块",
            "symbol": None,
            "symbol_or_scope": None,
            "benchmark_return": None,
            "excess_return": None,
            "status": "historical_replay_existing_only",
            "reason": "Historical replay does not fetch or expand sector peer universe.",
            "peer_symbol_count": 0,
            "contributing_peer_symbol_count": 0,
        }
    )
    return dimensions


def _benchmark_dimensions_payload(snapshot: ShortpickValidationSnapshot) -> dict[str, dict[str, Any]]:
    payload = _validation_payload(snapshot)
    dimensions = payload.get("benchmark_dimensions")
    if isinstance(dimensions, dict):
        return {
            str(key): dict(value)
            for key, value in dimensions.items()
            if isinstance(value, dict)
        }
    legacy_returns = payload.get("benchmark_returns") if isinstance(payload.get("benchmark_returns"), dict) else {}
    primary = payload.get("benchmark") if isinstance(payload.get("benchmark"), dict) else _shortpick_primary_benchmark()
    primary_symbol = str(primary.get("symbol") or CSI_BENCHMARKS[SHORTPICK_PRIMARY_BENCHMARK_ID]["symbol"])
    primary_label = str(primary.get("label") or CSI_BENCHMARKS[SHORTPICK_PRIMARY_BENCHMARK_ID]["label"])
    primary_return = snapshot.benchmark_return
    csi1000_symbol = CSI_BENCHMARKS["CSI1000"]["symbol"]
    raw_csi1000 = legacy_returns.get(csi1000_symbol) if isinstance(legacy_returns.get(csi1000_symbol), dict) else {}
    csi1000_return = raw_csi1000.get("return") if isinstance(raw_csi1000, dict) else None
    return {
        SHORTPICK_BENCHMARK_DIMENSION_HS300: {
            "dimension_key": SHORTPICK_BENCHMARK_DIMENSION_HS300,
            "benchmark_id": str(primary.get("benchmark_id") or SHORTPICK_PRIMARY_BENCHMARK_ID),
            "label": primary_label,
            "benchmark_label": primary_label,
            "symbol": primary_symbol,
            "symbol_or_scope": primary_symbol,
            "benchmark_return": primary_return,
            "excess_return": snapshot.excess_return,
            "status": "available" if primary_return is not None else "pending_benchmark_data",
            "reason": None if primary_return is not None else "沪深300缺少入场或退出窗口行情。",
        },
        SHORTPICK_BENCHMARK_DIMENSION_CSI1000: {
            "dimension_key": SHORTPICK_BENCHMARK_DIMENSION_CSI1000,
            "benchmark_id": "CSI1000",
            "label": CSI_BENCHMARKS["CSI1000"]["label"],
            "benchmark_label": CSI_BENCHMARKS["CSI1000"]["label"],
            "symbol": csi1000_symbol,
            "symbol_or_scope": csi1000_symbol,
            "benchmark_return": csi1000_return,
            "excess_return": None if snapshot.stock_return is None or csi1000_return is None else snapshot.stock_return - csi1000_return,
            "status": "available" if csi1000_return is not None else "pending_benchmark_data",
            "reason": None if csi1000_return is not None else "中证1000缺少入场或退出窗口行情。",
        },
    }


def _benchmark_dimension_payload(
    snapshot: ShortpickValidationSnapshot,
    dimension_key: str = SHORTPICK_BENCHMARK_DIMENSION_HS300,
) -> dict[str, Any] | None:
    return _benchmark_dimensions_payload(snapshot).get(dimension_key)


def _return_between_close_map(close_map: dict[Any, float], *, entry_day: date, exit_day: date) -> float | None:
    if not close_map:
        return None
    entry_close = _close_on_or_after(close_map, entry_day)
    exit_close = _close_on_or_after(close_map, exit_day)
    if entry_close in {None, 0} or exit_close is None:
        return None
    return float(exit_close) / float(entry_close) - 1


def _close_on_or_after(close_map: dict[Any, float], target_day: date) -> float | None:
    for trade_day in sorted(close_map):
        if trade_day >= target_day:
            return close_map[trade_day]
    return None


def _clear_validation_metrics(snapshot: ShortpickValidationSnapshot) -> None:
    snapshot.entry_at = None
    snapshot.exit_at = None
    snapshot.entry_close = None
    snapshot.exit_close = None
    snapshot.stock_return = None
    snapshot.benchmark_return = None
    snapshot.excess_return = None
    snapshot.max_favorable_return = None
    snapshot.max_drawdown = None


def _shortpick_validation_summary(session: Session, *, run_id: int) -> dict[str, Any]:
    validations = session.scalars(
        select(ShortpickValidationSnapshot)
        .join(ShortpickCandidate, ShortpickValidationSnapshot.candidate_id == ShortpickCandidate.id)
        .where(ShortpickCandidate.run_id == run_id)
        .order_by(ShortpickValidationSnapshot.horizon_days.asc(), ShortpickValidationSnapshot.id.asc())
    ).all()
    status_counts: dict[str, int] = {}
    by_horizon: dict[int, list[ShortpickValidationSnapshot]] = {}
    completed: list[ShortpickValidationSnapshot] = []
    official_completed: list[ShortpickValidationSnapshot] = []
    official_total = 0
    diagnostic_total = 0
    for validation in validations:
        status_counts[validation.status] = status_counts.get(validation.status, 0) + 1
        by_horizon.setdefault(validation.horizon_days, []).append(validation)
        if validation.status == "completed":
            completed.append(validation)
        if _validation_is_official(validation):
            official_total += 1
            if validation.status == "completed":
                official_completed.append(validation)
        else:
            diagnostic_total += 1
    horizon_summary: dict[str, dict[str, Any]] = {}
    for horizon, items in sorted(by_horizon.items()):
        official_items = [item for item in items if _validation_is_official(item)]
        completed_items = [item for item in official_items if item.status == "completed"]
        stock_returns = [float(item.stock_return) for item in completed_items if item.stock_return is not None]
        excess_returns = [float(item.excess_return) for item in completed_items if item.excess_return is not None]
        benchmark_metrics = {
            dimension_key: _validation_benchmark_metric_summary(completed_items, dimension_key=dimension_key)
            for dimension_key in SHORTPICK_BENCHMARK_DIMENSIONS
        }
        horizon_summary[str(horizon)] = {
            "validation_count": len(items),
            "official_sample_count": len(official_items),
            "completed_count": len(completed_items),
            "mean_stock_return": _mean_or_none(stock_returns),
            "mean_excess_return": _mean_or_none(excess_returns),
            "benchmark_metrics": benchmark_metrics,
            "positive_excess_rate": (
                round(sum(1 for item in excess_returns if item > 0) / len(excess_returns), 6)
                if excess_returns
                else None
            ),
        }
    return {
        "validation_status_counts": status_counts,
        "completed_validation_count": len(completed),
        "official_sample_count": official_total,
        "completed_official_sample_count": len(official_completed),
        "diagnostic_or_pending_sample_count": diagnostic_total,
        "measured_candidate_count": len({item.candidate_id for item in completed}),
        "measured_official_candidate_count": len({item.candidate_id for item in official_completed}),
        "validation_by_horizon": horizon_summary,
        "primary_benchmark": _shortpick_primary_benchmark(),
        "benchmark_dimensions": _shortpick_benchmark_dimension_options(),
        "official_validation_mode": SHORTPICK_OFFICIAL_VALIDATION_MODE,
    }


def _mean_or_none(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 6) if values else None


def _shortpick_benchmark_dimension_options() -> list[dict[str, str]]:
    return [
        {"dimension_key": SHORTPICK_BENCHMARK_DIMENSION_HS300, "label": "沪深300"},
        {"dimension_key": SHORTPICK_BENCHMARK_DIMENSION_CSI1000, "label": "中证1000"},
        {"dimension_key": SHORTPICK_BENCHMARK_DIMENSION_SECTOR, "label": "同板块"},
    ]


def _validation_benchmark_metric_summary(
    validations: list[ShortpickValidationSnapshot],
    *,
    dimension_key: str,
) -> dict[str, Any]:
    excess_returns: list[float] = []
    benchmark_returns: list[float] = []
    pending_reasons: dict[str, int] = {}
    available_count = 0
    for validation in validations:
        dimension = _benchmark_dimension_payload(validation, dimension_key)
        if dimension is None:
            pending_reasons["missing_dimension"] = pending_reasons.get("missing_dimension", 0) + 1
            continue
        if dimension.get("status") != "available":
            reason = str(dimension.get("reason") or dimension.get("status") or "pending_benchmark_data")
            pending_reasons[reason] = pending_reasons.get(reason, 0) + 1
            continue
        available_count += 1
        if dimension.get("excess_return") is not None:
            excess_returns.append(float(dimension["excess_return"]))
        if dimension.get("benchmark_return") is not None:
            benchmark_returns.append(float(dimension["benchmark_return"]))
    return {
        "dimension_key": dimension_key,
        "available_count": available_count,
        "mean_benchmark_return": _mean_or_none(benchmark_returns),
        "mean_excess_return": _mean_or_none(excess_returns),
        "trimmed_mean_excess_return": _trimmed_mean_or_none(excess_returns),
        "positive_excess_rate": _positive_rate(excess_returns),
        "pending_reasons": pending_reasons,
    }


def _validation_payload(snapshot: ShortpickValidationSnapshot) -> dict[str, Any]:
    return dict(snapshot.validation_payload or {})


def _validation_mode(snapshot: ShortpickValidationSnapshot) -> str:
    return str(_validation_payload(snapshot).get("validation_mode") or SHORTPICK_LEGACY_VALIDATION_MODE)


def _validation_tradeability_status(snapshot: ShortpickValidationSnapshot) -> str:
    return str(_validation_payload(snapshot).get("tradeability_status") or "unknown")


def _validation_is_official(snapshot: ShortpickValidationSnapshot) -> bool:
    payload = _validation_payload(snapshot)
    return (
        payload.get("validation_mode") == SHORTPICK_OFFICIAL_VALIDATION_MODE
        and payload.get("official_validation") is True
        and payload.get("tradeability_status") == SHORTPICK_OFFICIAL_TRADEABILITY_STATUS
    )


def _candidate_is_diagnostic(validations: list[ShortpickValidationSnapshot]) -> bool:
    if not validations:
        return False
    if any(_validation_is_official(validation) for validation in validations):
        return False
    statuses = {validation.status for validation in validations}
    return bool(statuses & SHORTPICK_DIAGNOSTIC_VALIDATION_STATUSES)


def _candidate_display_bucket(validations: list[ShortpickValidationSnapshot]) -> str:
    return SHORTPICK_DIAGNOSTIC_CANDIDATE_BUCKET if _candidate_is_diagnostic(validations) else SHORTPICK_NORMAL_CANDIDATE_BUCKET


def _candidate_diagnostic_reason(validations: list[ShortpickValidationSnapshot]) -> str | None:
    for validation in validations:
        if validation.status not in SHORTPICK_DIAGNOSTIC_VALIDATION_STATUSES:
            continue
        payload = _validation_payload(validation)
        reason = payload.get("pending_reason") or payload.get("reason")
        if reason:
            return str(reason)
        return validation.status
    return None


def _shortpick_validations_by_candidate(
    session: Session,
    candidates: list[ShortpickCandidate],
) -> dict[int, list[ShortpickValidationSnapshot]]:
    candidate_ids = [candidate.id for candidate in candidates]
    if not candidate_ids:
        return {}
    rows = session.scalars(
        select(ShortpickValidationSnapshot)
        .where(ShortpickValidationSnapshot.candidate_id.in_(candidate_ids))
        .order_by(ShortpickValidationSnapshot.horizon_days.asc(), ShortpickValidationSnapshot.id.asc())
    ).all()
    by_candidate: dict[int, list[ShortpickValidationSnapshot]] = {candidate_id: [] for candidate_id in candidate_ids}
    for row in rows:
        by_candidate.setdefault(row.candidate_id, []).append(row)
    return by_candidate


def _apply_shortpick_candidate_display_gates(session: Session, *, run_id: int) -> dict[str, Any]:
    candidates = session.scalars(
        select(ShortpickCandidate)
        .where(
            ShortpickCandidate.run_id == run_id,
            ShortpickCandidate.parse_status == "parsed",
            ShortpickCandidate.symbol != "PARSE_FAILED",
        )
        .order_by(ShortpickCandidate.id.asc())
    ).all()
    validations_by_candidate = _shortpick_validations_by_candidate(session, candidates)
    blocked: list[str] = []
    restored: list[str] = []
    for candidate in candidates:
        validations = validations_by_candidate.get(candidate.id, [])
        payload = dict(candidate.candidate_payload or {})
        display_gate = dict(payload.get("display_gate") or {})
        if _candidate_is_diagnostic(validations):
            if candidate.research_priority != SHORTPICK_TRADEABILITY_BLOCKED_PRIORITY:
                display_gate.setdefault("previous_research_priority", candidate.research_priority)
                display_gate.setdefault("previous_convergence_group", candidate.convergence_group)
            display_gate.update(
                {
                    "status": SHORTPICK_TRADEABILITY_BLOCKED_PRIORITY,
                    "display_bucket": SHORTPICK_DIAGNOSTIC_CANDIDATE_BUCKET,
                    "reason": _candidate_diagnostic_reason(validations),
                    "updated_at": utcnow().isoformat(),
                }
            )
            payload["display_gate"] = display_gate
            candidate.candidate_payload = payload
            candidate.research_priority = SHORTPICK_TRADEABILITY_BLOCKED_PRIORITY
            candidate.convergence_group = SHORTPICK_DIAGNOSTIC_CANDIDATE_BUCKET
            blocked.append(candidate.symbol)
            continue

        if display_gate.get("status") == SHORTPICK_TRADEABILITY_BLOCKED_PRIORITY:
            previous_priority = str(display_gate.get("previous_research_priority") or "divergent_novel")
            previous_group = display_gate.get("previous_convergence_group")
            payload["display_gate"] = {
                **display_gate,
                "status": "restored",
                "display_bucket": SHORTPICK_NORMAL_CANDIDATE_BUCKET,
                "restored_at": utcnow().isoformat(),
            }
            candidate.candidate_payload = payload
            candidate.research_priority = previous_priority
            candidate.convergence_group = str(previous_group) if previous_group else None
            restored.append(candidate.symbol)
    session.flush()
    return {
        "blocked_candidate_count": len(blocked),
        "restored_candidate_count": len(restored),
        "blocked_symbols": blocked,
        "restored_symbols": restored,
        "blocked_statuses": sorted(SHORTPICK_DIAGNOSTIC_VALIDATION_STATUSES),
    }


def serialize_shortpick_run(
    session: Session,
    run: ShortpickExperimentRun,
    *,
    include_raw: bool,
    include_candidates: bool = True,
    compact_summary: bool = False,
) -> dict[str, Any]:
    rounds = session.scalars(
        select(ShortpickModelRound).where(ShortpickModelRound.run_id == run.id).order_by(ShortpickModelRound.id.asc())
    ).all()
    candidates = session.scalars(
        select(ShortpickCandidate).where(ShortpickCandidate.run_id == run.id).order_by(ShortpickCandidate.id.asc())
    ).all()
    summary = {
        **dict(run.summary_payload or {}),
        **_run_operational_summary(session, run, rounds=rounds, candidates=candidates),
    }
    return {
        "id": run.id,
        "run_key": run.run_key,
        "run_date": run.run_date,
        "prompt_version": run.prompt_version,
        "information_mode": run.information_mode,
        "status": run.status,
        "trigger_source": run.trigger_source,
        "triggered_by": run.triggered_by,
        "started_at": run.started_at,
        "completed_at": run.completed_at,
        "failed_at": run.failed_at,
        "model_config": dict(run.model_config or {}),
        "summary": _compact_run_summary(summary) if compact_summary else summary,
        "rounds": [
            serialize_shortpick_round(item, include_raw=include_raw)
            for item in rounds
        ],
        "consensus": _serialize_consensus(
            session.scalar(
                select(ShortpickConsensusSnapshot)
                .where(ShortpickConsensusSnapshot.run_id == run.id)
                .order_by(ShortpickConsensusSnapshot.id.desc())
            )
        ),
        "candidates": [
            serialize_shortpick_candidate(session, item, include_raw=include_raw)
            for item in candidates
        ] if include_candidates else [],
    }


def _compact_run_summary(summary: dict[str, Any]) -> dict[str, Any]:
    output = dict(summary)
    source_packet = output.get("source_packet")
    if isinstance(source_packet, dict):
        packet = dict(source_packet)
        packet.pop("official_sources", None)
        packet.pop("diagnostic_sources", None)
        packet.pop("rejected_sources", None)
        output["source_packet"] = packet
    output.pop("replay_feedback", None)
    return output


def _run_operational_summary(
    session: Session,
    run: ShortpickExperimentRun,
    *,
    rounds: list[ShortpickModelRound],
    candidates: list[ShortpickCandidate],
) -> dict[str, Any]:
    failed_rounds = [round_record for round_record in rounds if round_record.status == "failed"]
    retryable_failed = [round_record for round_record in failed_rounds if _round_retryable(round_record)]
    parsed_candidates = [candidate for candidate in candidates if candidate.parse_status == "parsed" and candidate.symbol != "PARSE_FAILED"]
    validations_by_candidate = _shortpick_validations_by_candidate(session, parsed_candidates)
    normal_candidates = [
        candidate
        for candidate in parsed_candidates
        if _candidate_display_bucket(validations_by_candidate.get(candidate.id, [])) == SHORTPICK_NORMAL_CANDIDATE_BUCKET
    ]
    diagnostic_candidates = [
        candidate
        for candidate in parsed_candidates
        if _candidate_display_bucket(validations_by_candidate.get(candidate.id, [])) == SHORTPICK_DIAGNOSTIC_CANDIDATE_BUCKET
    ]
    validations = session.scalars(
        select(ShortpickValidationSnapshot).where(
            ShortpickValidationSnapshot.candidate_id.in_([candidate.id for candidate in parsed_candidates])
        )
    ).all() if parsed_candidates else []
    completed_validation_count = sum(1 for validation in validations if validation.status == "completed")
    official_validations = [validation for validation in validations if _validation_is_official(validation)]
    completed_official_validation_count = sum(1 for validation in official_validations if validation.status == "completed")
    operational_status = run.status
    if run.status == "completed" and failed_rounds:
        operational_status = "partial_completed"
    if run.status == "completed" and retryable_failed:
        operational_status = "retryable_failures"
    return {
        "operational_status": operational_status,
        "parsed_candidate_count": len(parsed_candidates),
        "normal_candidate_count": len(normal_candidates),
        "diagnostic_candidate_count": len(diagnostic_candidates),
        "failed_candidate_count": len(candidates) - len(parsed_candidates),
        "retryable_failed_round_count": len(retryable_failed),
        "has_retryable_failed_rounds": bool(retryable_failed),
        "validation_total_count": len(validations),
        "validation_completed_count": completed_validation_count,
        "official_validation_total_count": len(official_validations),
        "official_validation_completed_count": completed_official_validation_count,
        "validation_completion_rate": round(completed_validation_count / len(validations), 6) if validations else None,
        "official_validation_completion_rate": (
            round(completed_official_validation_count / len(official_validations), 6)
            if official_validations
            else None
        ),
        "failed_rounds": [
            {
                "id": round_record.id,
                "provider_name": round_record.provider_name,
                "model_name": round_record.model_name,
                "round_index": round_record.round_index,
                "failure_category": _shortpick_failure_category(round_record.error_message),
                "retryable": _round_retryable(round_record),
                "error_message": round_record.error_message,
            }
            for round_record in failed_rounds
        ],
    }


def serialize_shortpick_round(round_record: ShortpickModelRound, *, include_raw: bool) -> dict[str, Any]:
    pick = round_record.parsed_payload.get("primary_pick") if isinstance(round_record.parsed_payload, dict) else {}
    return {
        "id": round_record.id,
        "round_key": round_record.round_key,
        "provider_name": round_record.provider_name,
        "model_name": round_record.model_name,
        "executor_kind": round_record.executor_kind,
        "round_index": round_record.round_index,
        "status": round_record.status,
        "symbol": _normalize_symbol(str(pick.get("symbol") or "")) if isinstance(pick, dict) and pick.get("symbol") else None,
        "stock_name": str(pick.get("name") or "") if isinstance(pick, dict) else None,
        "theme": str(pick.get("theme") or "") if isinstance(pick, dict) else None,
        "thesis": str(pick.get("thesis") or "") if isinstance(pick, dict) else None,
        "confidence": _coerce_float(pick.get("confidence")) if isinstance(pick, dict) else None,
        "sources": round_record.sources_payload,
        "artifact_id": round_record.artifact_id,
        "failure_category": _shortpick_failure_category(round_record.error_message),
        "retryable": _round_retryable(round_record),
        "retry_history": (round_record.parsed_payload or {}).get("_retry_history", []) if include_raw else [],
        "error_message": round_record.error_message if include_raw else None,
        "raw_answer": round_record.raw_answer if include_raw else None,
        "started_at": round_record.started_at,
        "completed_at": round_record.completed_at,
    }


def serialize_shortpick_candidate(session: Session, candidate: ShortpickCandidate, *, include_raw: bool) -> dict[str, Any]:
    round_record = session.get(ShortpickModelRound, candidate.round_id) if candidate.round_id else None
    payload = candidate.candidate_payload if isinstance(candidate.candidate_payload, dict) else {}
    topic_normalization = payload.get("topic_normalization") if isinstance(payload.get("topic_normalization"), dict) else {}
    validations = session.scalars(
        select(ShortpickValidationSnapshot)
        .where(ShortpickValidationSnapshot.candidate_id == candidate.id)
        .order_by(ShortpickValidationSnapshot.horizon_days.asc())
    ).all()
    display_bucket = _candidate_display_bucket(validations)
    return {
        "id": candidate.id,
        "candidate_key": candidate.candidate_key,
        "run_id": candidate.run_id,
        "round_id": candidate.round_id,
        "symbol": candidate.symbol,
        "name": candidate.name,
        "normalized_theme": candidate.normalized_theme,
        "topic_normalization": topic_normalization,
        "horizon_trading_days": candidate.horizon_trading_days,
        "confidence": candidate.confidence,
        "thesis": candidate.thesis,
        "catalysts": list(candidate.catalysts or []),
        "invalidation": list(candidate.invalidation or []),
        "risks": list(candidate.risks or []),
        "sources": list(candidate.sources_payload or []),
        "novelty_note": candidate.novelty_note,
        "limitations": list(candidate.limitations or []),
        "convergence_group": candidate.convergence_group,
        "research_priority": candidate.research_priority,
        "parse_status": candidate.parse_status,
        "is_system_external": candidate.is_system_external,
        "display_bucket": display_bucket,
        "diagnostic_reason": (
            _candidate_diagnostic_reason(validations)
            if display_bucket == SHORTPICK_DIAGNOSTIC_CANDIDATE_BUCKET
            else None
        ),
        "validations": [
            _serialize_validation(item)
            for item in validations
        ],
        "raw_round": serialize_shortpick_round(round_record, include_raw=include_raw) if round_record is not None else None,
        "tracking_role": payload.get("tracking_role"),
        "llm_paper_control": dict(payload.get("llm_paper_control") or {}),
        "experiment_mode": payload.get("experiment_mode"),
        "baseline_family": payload.get("baseline_family"),
        "source_packet_id": payload.get("source_packet_id"),
        "source_packet_hash": payload.get("source_packet_hash"),
        "leakage_audit_status": payload.get("leakage_audit_status"),
        "leakage_audit_reasons": list(payload.get("leakage_audit_reasons") or []),
        "official_sample_eligible": payload.get("official_sample_eligible"),
        "exclusion_reason": payload.get("exclusion_reason"),
        "universe_membership": dict(payload.get("universe_membership") or {}),
        "evidence_mapping": dict(payload.get("evidence_mapping") or {}),
    }


def list_shortpick_runs(
    session: Session,
    *,
    status: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    information_mode: str | None = None,
    limit: int = 20,
    offset: int = 0,
    include_raw: bool = False,
    include_candidates: bool = True,
    compact_summary: bool = False,
) -> dict[str, Any]:
    normalized_limit = max(1, min(int(limit), 100))
    normalized_offset = max(0, int(offset))
    query = select(ShortpickExperimentRun)
    if information_mode is not None:
        query = query.where(ShortpickExperimentRun.information_mode == information_mode)
    if status:
        query = query.where(ShortpickExperimentRun.status == status)
    if date_from is not None:
        query = query.where(ShortpickExperimentRun.run_date >= date_from)
    if date_to is not None:
        query = query.where(ShortpickExperimentRun.run_date <= date_to)
    total = session.scalar(select(func.count()).select_from(query.subquery())) or 0
    runs = session.scalars(
        query.order_by(ShortpickExperimentRun.started_at.desc(), ShortpickExperimentRun.id.desc())
        .limit(normalized_limit)
        .offset(normalized_offset)
    ).all()
    return {
        "generated_at": utcnow(),
        "items": [
            serialize_shortpick_run(
                session,
                run,
                include_raw=include_raw,
                include_candidates=include_candidates,
                compact_summary=compact_summary,
            )
            for run in runs
        ],
        "total": total,
        "limit": normalized_limit,
        "offset": normalized_offset,
    }


def get_shortpick_run(session: Session, run_id: int, *, include_raw: bool) -> dict[str, Any]:
    run = session.get(ShortpickExperimentRun, run_id)
    if run is None:
        raise LookupError(f"Shortpick run {run_id} not found.")
    return serialize_shortpick_run(session, run, include_raw=include_raw)


def list_shortpick_candidates(
    session: Session,
    *,
    run_id: int | None = None,
    model: str | None = None,
    priority: str | None = None,
    validation_status: str | None = None,
    limit: int = 100,
    include_raw: bool = False,
) -> dict[str, Any]:
    query = select(ShortpickCandidate).order_by(ShortpickCandidate.created_at.desc(), ShortpickCandidate.id.desc()).limit(limit)
    if run_id is not None:
        query = query.where(ShortpickCandidate.run_id == run_id)
    if priority:
        query = query.where(ShortpickCandidate.research_priority == priority)
    candidates = session.scalars(query).all()
    if model:
        normalized_model = model.lower()
        candidates = [
            item for item in candidates
            if (
                round_record := (session.get(ShortpickModelRound, item.round_id) if item.round_id else None)
            ) is not None
            and (normalized_model in round_record.provider_name.lower() or normalized_model in round_record.model_name.lower())
        ]
    if validation_status:
        candidates = [
            item for item in candidates
            if any(
                validation.status == validation_status
                for validation in session.scalars(
                    select(ShortpickValidationSnapshot).where(ShortpickValidationSnapshot.candidate_id == item.id)
                ).all()
            )
        ]
    return {"generated_at": utcnow(), "items": [serialize_shortpick_candidate(session, item, include_raw=include_raw) for item in candidates]}


def list_shortpick_validation_queue(
    session: Session,
    *,
    run_id: int | None = None,
    status: str | None = None,
    horizon: int | None = None,
    model: str | None = None,
    symbol: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    normalized_limit = max(1, min(int(limit), 200))
    normalized_offset = max(0, int(offset))
    query = (
        select(ShortpickValidationSnapshot, ShortpickCandidate, ShortpickExperimentRun, ShortpickModelRound)
        .join(ShortpickCandidate, ShortpickValidationSnapshot.candidate_id == ShortpickCandidate.id)
        .join(ShortpickExperimentRun, ShortpickCandidate.run_id == ShortpickExperimentRun.id)
        .outerjoin(ShortpickModelRound, ShortpickCandidate.round_id == ShortpickModelRound.id)
        .where(ShortpickCandidate.parse_status == "parsed", ShortpickCandidate.symbol != "PARSE_FAILED")
    )
    if run_id is not None:
        query = query.where(ShortpickCandidate.run_id == run_id)
    if status:
        query = query.where(ShortpickValidationSnapshot.status == status)
    if horizon is not None:
        query = query.where(ShortpickValidationSnapshot.horizon_days == int(horizon))
    if symbol:
        query = query.where(ShortpickCandidate.symbol == _normalize_symbol(symbol))
    if date_from is not None:
        query = query.where(ShortpickExperimentRun.run_date >= date_from)
    if date_to is not None:
        query = query.where(ShortpickExperimentRun.run_date <= date_to)
    if model:
        normalized_model = model.lower()
        query = query.where(
            func.lower(ShortpickModelRound.provider_name).contains(normalized_model)
            | func.lower(ShortpickModelRound.model_name).contains(normalized_model)
        )
    total = session.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = session.execute(
        query.order_by(
            ShortpickExperimentRun.run_date.desc(),
            ShortpickValidationSnapshot.status.asc(),
            ShortpickValidationSnapshot.horizon_days.asc(),
            ShortpickCandidate.id.desc(),
        )
        .limit(normalized_limit)
        .offset(normalized_offset)
    ).all()
    return {
        "generated_at": utcnow(),
        "items": [
            _serialize_validation_queue_item(validation, candidate, run, round_record)
            for validation, candidate, run, round_record in rows
        ],
        "total": total,
        "limit": normalized_limit,
        "offset": normalized_offset,
    }


def build_shortpick_model_feedback(session: Session) -> dict[str, Any]:
    rounds = session.scalars(select(ShortpickModelRound).order_by(ShortpickModelRound.id.asc())).all()
    candidates = session.scalars(
        select(ShortpickCandidate).where(ShortpickCandidate.parse_status == "parsed", ShortpickCandidate.symbol != "PARSE_FAILED")
    ).all()
    model_keys = sorted(
        {
            (round_record.provider_name, round_record.model_name, round_record.executor_kind)
            for round_record in rounds
        }
    )
    items: list[dict[str, Any]] = []
    for provider_name, model_name, executor_kind in model_keys:
        model_rounds = [
            round_record
            for round_record in rounds
            if (
                round_record.provider_name,
                round_record.model_name,
                round_record.executor_kind,
            )
            == (provider_name, model_name, executor_kind)
        ]
        round_ids = {round_record.id for round_record in model_rounds}
        model_candidates = [candidate for candidate in candidates if candidate.round_id in round_ids]
        source_counts: dict[str, int] = {}
        for candidate in model_candidates:
            for source in candidate.sources_payload or []:
                status = str(source.get("credibility_status") or "unchecked")
                source_counts[status] = source_counts.get(status, 0) + 1
        validation_rows = _validation_feedback_rows(session, model_candidates)
        completed_round_count = sum(1 for round_record in model_rounds if round_record.status == "completed")
        failed_round_count = sum(1 for round_record in model_rounds if round_record.status == "failed")
        unique_symbol_runs = {
            (candidate.run_id, candidate.symbol)
            for candidate in model_candidates
        }
        official_rows = [row for row in validation_rows if _validation_is_official(row["validation"])]
        completed_official_rows = [
            row for row in official_rows
            if row["validation"].status == "completed"
        ]
        items.append(
            {
                "provider_name": provider_name,
                "model_name": model_name,
                "executor_kind": executor_kind,
                "round_count": len(model_rounds),
                "completed_round_count": completed_round_count,
                "failed_round_count": failed_round_count,
                "retryable_failed_round_count": sum(1 for round_record in model_rounds if _round_retryable(round_record)),
                "parse_failed_candidate_count": _parse_failed_count_for_rounds(session, round_ids),
                "candidate_row_count": len(model_candidates),
                "candidate_horizon_row_count": len(validation_rows),
                "unique_symbol_run_count": len(unique_symbol_runs),
                "official_sample_count": len(official_rows),
                "completed_official_sample_count": len(completed_official_rows),
                "success_rate": round(completed_round_count / len(model_rounds), 6) if model_rounds else None,
                "source_credibility_counts": source_counts,
                "validation_by_horizon": _feedback_groups(validation_rows, key_fn=lambda row: str(row["validation"].horizon_days), label_fn=lambda row: f"{row['validation'].horizon_days}日"),
                "validation_by_priority": _feedback_groups(validation_rows, key_fn=lambda row: row["candidate"].research_priority, label_fn=lambda row: row["candidate"].research_priority),
                "validation_by_theme": _feedback_groups(
                    validation_rows,
                    key_fn=lambda row: _candidate_topic_key(row["candidate"]),
                    label_fn=lambda row: _candidate_topic_label(row["candidate"]),
                    limit=12,
                ),
            }
        )
    all_validation_rows = _validation_feedback_rows(session, candidates)
    completed_official_rows = [
        row
        for row in all_validation_rows
        if _validation_is_official(row["validation"]) and row["validation"].status == "completed"
    ]
    return {
        "generated_at": utcnow(),
        "models": items,
        "overall": {
            "run_count": session.scalar(select(func.count(ShortpickExperimentRun.id))) or 0,
            "round_count": len(rounds),
            "candidate_count": len(candidates),
            "validation_count": session.scalar(select(func.count(ShortpickValidationSnapshot.id))) or 0,
            "unique_symbol_run_count": len({(candidate.run_id, candidate.symbol) for candidate in candidates}),
            "official_validation_mode": SHORTPICK_OFFICIAL_VALIDATION_MODE,
            "benchmark_dimensions": _shortpick_benchmark_dimension_options(),
            "evaluation_checkpoints": _shortpick_evaluation_checkpoints(completed_official_rows),
            "baseline_status": _shortpick_baseline_status(completed_official_rows),
            "boundary": "independent_research_lab_no_main_pool_write",
        },
    }


def get_shortpick_candidate(session: Session, candidate_id: int, *, include_raw: bool) -> dict[str, Any]:
    candidate = session.get(ShortpickCandidate, candidate_id)
    if candidate is None:
        raise LookupError(f"Shortpick candidate {candidate_id} not found.")
    return serialize_shortpick_candidate(session, candidate, include_raw=include_raw)


def _serialize_validation_queue_item(
    validation: ShortpickValidationSnapshot,
    candidate: ShortpickCandidate,
    run: ShortpickExperimentRun,
    round_record: ShortpickModelRound | None,
) -> dict[str, Any]:
    validation_payload = _serialize_validation(validation)
    benchmark_dimensions = dict(validation_payload.get("benchmark_dimensions") or {})
    required_forward_bars = validation_payload.get("required_forward_bars")
    if validation.status == "pending_forward_window" and required_forward_bars is None:
        required_forward_bars = validation.horizon_days
    return {
        "validation_id": validation.id,
        "candidate_id": candidate.id,
        "run_id": run.id,
        "run_key": run.run_key,
        "run_date": run.run_date,
        "provider_name": round_record.provider_name if round_record is not None else None,
        "model_name": round_record.model_name if round_record is not None else None,
        "executor_kind": round_record.executor_kind if round_record is not None else None,
        "round_index": round_record.round_index if round_record is not None else None,
        "symbol": candidate.symbol,
        "name": candidate.name,
        "normalized_theme": candidate.normalized_theme,
        "research_priority": candidate.research_priority,
        "convergence_group": candidate.convergence_group,
        "horizon_days": validation.horizon_days,
        "status": validation.status,
        "entry_at": validation.entry_at,
        "exit_at": validation.exit_at,
        "entry_close": validation.entry_close,
        "exit_close": validation.exit_close,
        "stock_return": validation.stock_return,
        "benchmark_return": validation.benchmark_return,
        "excess_return": validation.excess_return,
        "max_favorable_return": validation.max_favorable_return,
        "max_drawdown": validation.max_drawdown,
        "benchmark_symbol": validation_payload.get("benchmark_symbol"),
        "benchmark_label": validation_payload.get("benchmark_label"),
        "benchmark_dimensions": benchmark_dimensions,
        "validation_mode": validation_payload.get("validation_mode") or _validation_mode(validation),
        "official_validation": _validation_is_official(validation),
        "tradeability_status": validation_payload.get("tradeability_status") or _validation_tradeability_status(validation),
        "tradeability_evidence": validation_payload.get("tradeability_evidence") or {},
        "available_forward_bars": validation_payload.get("available_forward_bars"),
        "required_forward_bars": required_forward_bars,
        "pending_reason": validation_payload.get("pending_reason") or validation_payload.get("reason"),
        "market_data_sync": validation_payload.get("market_data_sync") or {},
        "experiment_mode": validation_payload.get("experiment_mode"),
        "source_packet_id": validation_payload.get("source_packet_id"),
        "source_packet_hash": validation_payload.get("source_packet_hash"),
        "leakage_audit_status": validation_payload.get("leakage_audit_status"),
        "leakage_audit_reasons": list(validation_payload.get("leakage_audit_reasons") or []),
        "baseline_family": validation_payload.get("baseline_family"),
        "official_sample_eligible": validation_payload.get("official_sample_eligible"),
    }


def _validation_feedback_rows(session: Session, candidates: list[ShortpickCandidate]) -> list[dict[str, Any]]:
    if not candidates:
        return []
    candidate_by_id = {candidate.id: candidate for candidate in candidates}
    validations = session.scalars(
        select(ShortpickValidationSnapshot).where(ShortpickValidationSnapshot.candidate_id.in_(candidate_by_id))
    ).all()
    return [
        {"validation": validation, "candidate": candidate_by_id[validation.candidate_id]}
        for validation in validations
        if validation.candidate_id in candidate_by_id
    ]


def _parse_failed_count_for_rounds(session: Session, round_ids: set[int]) -> int:
    if not round_ids:
        return 0
    return session.scalar(
        select(func.count(ShortpickCandidate.id)).where(
            ShortpickCandidate.round_id.in_(round_ids),
            ShortpickCandidate.parse_status == "parse_failed",
        )
    ) or 0


def _feedback_groups(
    rows: list[dict[str, Any]],
    *,
    key_fn: Any,
    label_fn: Any,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    labels: dict[str, str] = {}
    for row in rows:
        key = str(key_fn(row))
        grouped.setdefault(key, []).append(row)
        labels.setdefault(key, str(label_fn(row)))
    output: list[dict[str, Any]] = []
    for key, group_rows in grouped.items():
        validations = [row["validation"] for row in group_rows]
        official_rows = [row for row in group_rows if _validation_is_official(row["validation"])]
        official_validations = [row["validation"] for row in official_rows]
        completed = [validation for validation in official_validations if validation.status == "completed"]
        stock_returns = [float(validation.stock_return) for validation in completed if validation.stock_return is not None]
        excess_returns = [float(validation.excess_return) for validation in completed if validation.excess_return is not None]
        benchmark_metrics = {
            dimension_key: _validation_benchmark_metric_summary(completed, dimension_key=dimension_key)
            for dimension_key in SHORTPICK_BENCHMARK_DIMENSIONS
        }
        favorable_returns = [
            float(validation.max_favorable_return)
            for validation in completed
            if validation.max_favorable_return is not None
        ]
        drawdowns = [float(validation.max_drawdown) for validation in completed if validation.max_drawdown is not None]
        status_counts: dict[str, int] = {}
        for validation in validations:
            status_counts[validation.status] = status_counts.get(validation.status, 0) + 1
        output.append(
            {
                "group_key": key,
                "label": labels[key],
                "sample_count": len(validations),
                "official_sample_count": len(official_validations),
                "unique_symbol_run_count": len({(row["candidate"].run_id, row["candidate"].symbol) for row in group_rows}),
                "completed_validation_count": len(completed),
                "completed_official_sample_count": len(completed),
                "mean_stock_return": _mean_or_none(stock_returns),
                "mean_excess_return": _mean_or_none(excess_returns),
                "trimmed_mean_excess_return": _trimmed_mean_or_none(excess_returns),
                "benchmark_metrics": benchmark_metrics,
                "positive_excess_rate": (
                    round(sum(1 for item in excess_returns if item > 0) / len(excess_returns), 6)
                    if excess_returns
                    else None
                ),
                "max_drawdown": min(drawdowns) if drawdowns else None,
                "max_favorable_return": max(favorable_returns) if favorable_returns else None,
                "status_counts": status_counts,
            }
        )
    output.sort(key=lambda item: (item["completed_official_sample_count"], item["official_sample_count"], item["sample_count"], item["label"]), reverse=True)
    return output[:limit] if limit is not None else output


def _shortpick_evaluation_checkpoints(rows: list[dict[str, Any]]) -> dict[str, Any]:
    horizon_rows = [row for row in rows if row["validation"].horizon_days == 5]
    unique_5d = {
        (row["candidate"].run_id, row["candidate"].symbol)
        for row in horizon_rows
    }
    excess_returns = [
        float(row["validation"].excess_return)
        for row in horizon_rows
        if row["validation"].excess_return is not None
    ]
    checkpoints = {
        "checkpoint_a_30_unique_symbol_3d": _checkpoint_status(rows, horizon=3, required_unique_symbol_runs=30),
        "checkpoint_b_50_unique_symbol_5d": _checkpoint_status(rows, horizon=5, required_unique_symbol_runs=50),
        "checkpoint_c_100_unique_symbol_5d": _checkpoint_status(rows, horizon=5, required_unique_symbol_runs=100),
    }
    status = "not_ready"
    if len(unique_5d) >= 50 and excess_returns:
        status = "pass" if (_trimmed_mean_or_none(excess_returns) or 0.0) > 0 and _positive_rate(excess_returns) >= 0.55 else "fail"
    return {
        "status": status,
        "official_5d_unique_symbol_run_count": len(unique_5d),
        "official_5d_trimmed_mean_excess_return": _trimmed_mean_or_none(excess_returns),
        "official_5d_positive_excess_rate": _positive_rate(excess_returns),
        "checkpoints": checkpoints,
        "policy": "no_model_capability_claim_until_checkpoint_b_and_baselines_ready",
    }


def _checkpoint_status(rows: list[dict[str, Any]], *, horizon: int, required_unique_symbol_runs: int) -> dict[str, Any]:
    unique_symbol_runs = {
        (row["candidate"].run_id, row["candidate"].symbol)
        for row in rows
        if row["validation"].horizon_days == horizon
    }
    return {
        "horizon_days": horizon,
        "required_unique_symbol_runs": required_unique_symbol_runs,
        "completed_unique_symbol_runs": len(unique_symbol_runs),
        "status": "ready" if len(unique_symbol_runs) >= required_unique_symbol_runs else "not_ready",
    }


def _shortpick_baseline_status(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    unique_symbol_runs = {
        (row["candidate"].run_id, row["candidate"].symbol)
        for row in rows
        if row["validation"].horizon_days == 5
    }
    readiness = "not_ready" if len(unique_symbol_runs) < 50 else "needs_peer_universe"
    return [
        {
            "baseline_id": "random_same_market_cap_bucket",
            "status": readiness,
            "required_data": "candidate market-cap bucket peer universe with matching entry/exit bars",
        },
        {
            "baseline_id": "momentum_volume_baseline",
            "status": readiness,
            "required_data": "tradable universe momentum and volume snapshots before signal availability",
        },
        {
            "baseline_id": "topic_peer_baseline",
            "status": readiness,
            "required_data": "AI-normalized topic peer set with same validation windows",
        },
    ]


def _positive_rate(values: list[float]) -> float | None:
    if not values:
        return None
    return round(sum(1 for item in values if item > 0) / len(values), 6)


def _trimmed_mean_or_none(values: list[float]) -> float | None:
    if not values:
        return None
    if len(values) < 5:
        return _mean_or_none(values)
    ordered = sorted(values)
    return _mean_or_none(ordered[1:-1])


def _serialize_consensus(snapshot: ShortpickConsensusSnapshot | None) -> dict[str, Any] | None:
    if snapshot is None:
        return None
    return {
        "id": snapshot.id,
        "snapshot_key": snapshot.snapshot_key,
        "artifact_id": snapshot.artifact_id,
        "generated_at": snapshot.generated_at,
        "status": snapshot.status,
        "stock_convergence": snapshot.stock_convergence,
        "theme_convergence": snapshot.theme_convergence,
        "source_diversity": snapshot.source_diversity,
        "model_independence": snapshot.model_independence,
        "novelty_score": snapshot.novelty_score,
        "research_priority": snapshot.research_priority,
        "summary": dict(snapshot.summary_payload or {}),
    }


def _serialize_validation(snapshot: ShortpickValidationSnapshot) -> dict[str, Any]:
    payload = dict(snapshot.validation_payload or {})
    benchmark = payload.get("benchmark") if isinstance(payload.get("benchmark"), dict) else _shortpick_primary_benchmark()
    benchmark_returns = payload.get("benchmark_returns") if isinstance(payload.get("benchmark_returns"), dict) else {}
    benchmark_dimensions = _benchmark_dimensions_payload(snapshot)
    required_forward_bars = payload.get("required_forward_bars")
    if snapshot.status == "pending_forward_window" and required_forward_bars is None:
        required_forward_bars = snapshot.horizon_days
    pending_reason = payload.get("pending_reason") or payload.get("reason")
    if snapshot.status == "pending_forward_window" and not pending_reason:
        available_forward_bars = payload.get("available_forward_bars")
        if available_forward_bars is None:
            available_forward_bars = 0
        pending_reason = (
            f"Official entry close after signal availability is {snapshot.entry_at.isoformat() if snapshot.entry_at else 'entry close'}; "
            f"needs {required_forward_bars} forward trading-day close(s), currently has {available_forward_bars}."
        )
    return {
        "id": snapshot.id,
        "horizon_days": snapshot.horizon_days,
        "status": snapshot.status,
        "entry_at": snapshot.entry_at,
        "exit_at": snapshot.exit_at,
        "entry_close": snapshot.entry_close,
        "exit_close": snapshot.exit_close,
        "stock_return": snapshot.stock_return,
        "benchmark_return": snapshot.benchmark_return,
        "excess_return": snapshot.excess_return,
        "max_favorable_return": snapshot.max_favorable_return,
        "max_drawdown": snapshot.max_drawdown,
        "benchmark_symbol": benchmark.get("symbol"),
        "benchmark_label": benchmark.get("label"),
        "benchmark_returns": benchmark_returns,
        "benchmark_dimensions": benchmark_dimensions,
        "available_benchmark_dimensions": [
            key for key, value in benchmark_dimensions.items() if value.get("status") == "available"
        ],
        "validation_mode": payload.get("validation_mode") or SHORTPICK_LEGACY_VALIDATION_MODE,
        "official_validation": _validation_is_official(snapshot),
        "tradeability_status": payload.get("tradeability_status") or "unknown",
        "tradeability_evidence": payload.get("tradeability_evidence") or {},
        "available_forward_bars": payload.get("available_forward_bars"),
        "required_forward_bars": required_forward_bars,
        "pending_reason": pending_reason,
        "market_data_sync": payload.get("market_data_sync") or {},
        "experiment_mode": payload.get("experiment_mode"),
        "source_packet_id": payload.get("source_packet_id"),
        "source_packet_hash": payload.get("source_packet_hash"),
        "leakage_audit_status": payload.get("leakage_audit_status"),
        "leakage_audit_reasons": list(payload.get("leakage_audit_reasons") or []),
        "baseline_family": payload.get("baseline_family"),
        "official_sample_eligible": payload.get("official_sample_eligible"),
    }


def _write_round_artifact(
    session: Session,
    run: ShortpickExperimentRun,
    round_record: ShortpickModelRound,
    *,
    prompt: str,
) -> None:
    root = _artifact_root(session)
    write_shortpick_lab_artifact(
        artifact_id=str(round_record.artifact_id),
        root=root,
        payload={
            "artifact_id": round_record.artifact_id,
            "artifact_type": "shortpick_lab",
            "run_key": run.run_key,
            "round_key": round_record.round_key,
            "prompt_version": run.prompt_version,
            "information_mode": run.information_mode,
            "prompt": prompt,
            "provider_name": round_record.provider_name,
            "model_name": round_record.model_name,
            "executor_kind": round_record.executor_kind,
            "status": round_record.status,
            "raw_answer": round_record.raw_answer,
            "parsed_payload": round_record.parsed_payload,
            "sources": round_record.sources_payload,
            "error_message": round_record.error_message,
            "generated_at": utcnow().isoformat(),
            "boundary": "independent_research_lab_no_main_pool_write",
        },
    )


def _write_consensus_artifact(
    session: Session,
    run: ShortpickExperimentRun,
    snapshot: ShortpickConsensusSnapshot,
) -> None:
    root = _artifact_root(session)
    write_shortpick_lab_artifact(
        artifact_id=str(snapshot.artifact_id),
        root=root,
        payload={
            "artifact_id": snapshot.artifact_id,
            "artifact_type": "shortpick_lab",
            "run_key": run.run_key,
            "snapshot_key": snapshot.snapshot_key,
            "generated_at": snapshot.generated_at.isoformat(),
            "scores": {
                "stock_convergence": snapshot.stock_convergence,
                "theme_convergence": snapshot.theme_convergence,
                "source_diversity": snapshot.source_diversity,
                "model_independence": snapshot.model_independence,
                "novelty_score": snapshot.novelty_score,
            },
            "research_priority": snapshot.research_priority,
            "summary": snapshot.summary_payload,
            "boundary": "model_consensus_is_research_priority_not_trade_confidence",
        },
    )


def _artifact_root(session: Session) -> Path:
    bind = session.get_bind()
    return artifact_root_from_database_url(bind.url.render_as_string(hide_password=False) if bind else None)


def _normalize_symbol(value: str) -> str:
    text = value.strip().upper()
    if text in {"", "NONE"}:
        return "PARSE_FAILED"
    match = re.search(r"(\d{6})(?:\.(SH|SZ|BJ))?", text)
    if not match:
        return text[:32]
    ticker = match.group(1)
    suffix = match.group(2)
    if not suffix:
        suffix = "SH" if ticker.startswith(("5", "6", "9")) else "SZ"
    return f"{ticker}.{suffix}"


def _coerce_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _coerce_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _coerce_float(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _coerce_int(value: Any) -> int | None:
    try:
        if value is None or value == "":
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _normalize_sources(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    sources: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        source = {
            "title": _coerce_text(item.get("title")),
            "url": _coerce_text(item.get("url")),
            "published_at": _coerce_text(item.get("published_at")),
            "why_it_matters": _coerce_text(item.get("why_it_matters") or item.get("relevance")),
        }
        source.update(_source_credibility(source["url"]))
        sources.append(source)
    return sources


def _source_credibility(url: str | None) -> dict[str, Any]:
    normalized = (url or "").strip()
    checked_at = utcnow().isoformat()
    authority_class = _source_authority_class(normalized)
    if not normalized:
        return {
            "credibility_status": "missing_url",
            "credibility_reason": "source omitted url",
            "authority_class": authority_class,
            "checked_at": checked_at,
        }
    parsed = urlparse(normalized)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return {
            "credibility_status": "suspicious",
            "credibility_reason": "invalid url format",
            "authority_class": authority_class,
            "checked_at": checked_at,
        }
    if _looks_like_placeholder_url(normalized):
        return {
            "credibility_status": "suspicious",
            "credibility_reason": "placeholder-like url pattern",
            "authority_class": authority_class,
            "checked_at": checked_at,
        }
    if parsed.hostname and parsed.hostname.endswith(".example"):
        return {
            "credibility_status": "suspicious",
            "credibility_reason": "reserved example domain",
            "authority_class": authority_class,
            "checked_at": checked_at,
        }
    result = _probe_source_url(normalized, checked_at=checked_at)
    result["authority_class"] = authority_class
    return result


def _source_authority_class(url: str) -> str:
    hostname = (urlparse(url).hostname or "").lower()
    if not hostname:
        return "aggregator_or_unknown"
    if hostname.endswith(("sse.com.cn", "szse.cn", "bse.cn", "cninfo.com.cn")):
        return "exchange_or_company_disclosure"
    if hostname.endswith(("cs.com.cn", "stcn.com", "cnstock.com", "zqrb.cn")):
        return "designated_disclosure_media"
    if hostname.endswith(("eastmoney.com", "hexun.com", "cls.cn", "yicai.com", "21jingji.com", "caixin.com")):
        return "mainstream_financial_media"
    if hostname.endswith(("mysteel.com", "smm.cn", "cinn.cn", "ofweek.com", "gg-lb.com")):
        return "vertical_industry_media"
    if hostname.endswith(("pdf.dfcfw.com", "research.cicc.com", "cmschina.com")):
        return "broker_research_or_pdf"
    if hostname.endswith(("xueqiu.com", "guba.eastmoney.com", "weibo.com")):
        return "community_or_forum"
    return "aggregator_or_unknown"


def _source_support_check(
    source: dict[str, Any],
    *,
    theme: str | None,
    thesis: str | None,
    catalysts: list[str],
) -> dict[str, Any]:
    source_text = " ".join(
        item
        for item in [
            _coerce_text(source.get("title")),
            _coerce_text(source.get("why_it_matters")),
            _coerce_text(source.get("url")),
        ]
        if item
    )
    claim_text = " ".join(item for item in [theme, thesis, *catalysts] if item)
    source_terms = _support_terms(source_text)
    claim_terms = _support_terms(claim_text)
    overlap = sorted(source_terms & claim_terms)
    if overlap:
        return {
            "support_status": "supported_by_source_text",
            "support_evidence_terms": overlap[:12],
        }
    return {
        "support_status": "weak_or_unverified_source_support",
        "support_evidence_terms": [],
    }


def _support_terms(text: str) -> set[str]:
    normalized = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]+", " ", text.lower())
    terms = {item for item in normalized.split() if len(item) >= 2}
    chinese = re.findall(r"[\u4e00-\u9fff]{2,}", normalized)
    for phrase in chinese:
        terms.add(phrase)
        terms.update(phrase[index : index + 2] for index in range(max(len(phrase) - 1, 0)))
        terms.update(phrase[index : index + 3] for index in range(max(len(phrase) - 2, 0)))
    return terms


def _looks_like_placeholder_url(url: str) -> bool:
    return any(pattern.search(url) for pattern in SUSPICIOUS_SOURCE_PATTERNS)


def _probe_source_url(url: str, *, checked_at: str) -> dict[str, Any]:
    for method in ("HEAD", "GET"):
        for attempt in range(1, SHORTPICK_SOURCE_CHECK_RETRY_ATTEMPTS + 1):
            http_request = request.Request(
                url,
                headers={
                    "User-Agent": "ashare-shortpick-lab-source-check/1.0",
                    **({"Range": "bytes=0-0"} if method == "GET" else {}),
                },
                method=method,
            )
            try:
                with urlopen(
                    http_request,
                    timeout=SHORTPICK_SOURCE_CHECK_TIMEOUT_SECONDS,
                    disable_proxies=True,
                ) as response:
                    status = int(getattr(response, "status", 200) or 200)
                return {
                    "credibility_status": "verified" if status < 400 else "unreachable",
                    "credibility_reason": f"{method} HTTP {status}",
                    "http_status": status,
                    "attempt_count": attempt,
                    "checked_at": checked_at,
                }
            except HTTPError as exc:
                if method == "HEAD" and exc.code in {403, 405}:
                    break
                if exc.code in {401, 403}:
                    return {
                        "credibility_status": "reachable_restricted",
                        "credibility_reason": f"{method} HTTP {exc.code}",
                        "http_status": exc.code,
                        "attempt_count": attempt,
                        "checked_at": checked_at,
                    }
                return {
                    "credibility_status": "unreachable",
                    "credibility_reason": f"{method} HTTP {exc.code}",
                    "http_status": exc.code,
                    "attempt_count": attempt,
                    "checked_at": checked_at,
                }
            except (TimeoutError, URLError, OSError) as exc:
                if attempt < SHORTPICK_SOURCE_CHECK_RETRY_ATTEMPTS:
                    continue
                if method == "HEAD":
                    break
                return {
                    "credibility_status": "unreachable",
                    "credibility_reason": str(getattr(exc, "reason", exc))[:160],
                    "attempt_count": attempt,
                    "checked_at": checked_at,
                }
    return {
        "credibility_status": "unchecked",
        "credibility_reason": "source check skipped",
        "attempt_count": SHORTPICK_SOURCE_CHECK_RETRY_ATTEMPTS,
        "checked_at": checked_at,
    }


def _infer_theme(pick: dict[str, Any]) -> str | None:
    catalysts = _coerce_string_list(pick.get("catalysts"))
    if catalysts:
        return catalysts[0][:128]
    thesis = _coerce_text(pick.get("thesis"))
    return thesis[:80] if thesis else None


def _is_system_external(session: Session, symbol: str) -> bool:
    if symbol == "PARSE_FAILED":
        return True
    active_follow = session.scalar(
        select(WatchlistFollow).where(WatchlistFollow.symbol == symbol, WatchlistFollow.status == "active")
    )
    if active_follow is not None:
        return False
    recommended = session.scalar(
        select(Recommendation.id)
        .join(Stock)
        .where(Stock.symbol == symbol)
        .order_by(*recommendation_recency_ordering())
        .limit(1)
    )
    return recommended is None


def _host_from_url(url: str) -> str:
    stripped = url.replace("https://", "").replace("http://", "")
    return stripped.split("/", 1)[0].lower()

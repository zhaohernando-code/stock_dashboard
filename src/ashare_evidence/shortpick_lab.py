from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
from typing import Any, Protocol
from urllib import request
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ashare_evidence.analysis_pipeline import _fetch_daily_bars_akshare, _fetch_daily_bars_tushare
from ashare_evidence.benchmark import CSI_BENCHMARKS, benchmark_close_maps, sync_benchmark_index_bars
from ashare_evidence.db import utcnow
from ashare_evidence.http_client import urlopen
from ashare_evidence.lineage import build_lineage
from ashare_evidence.llm_service import OpenAICompatibleTransport, route_model
from ashare_evidence.models import (
    MarketBar,
    ModelApiKey,
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
from ashare_evidence.stock_master import resolve_stock_profile

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
SUSPICIOUS_SOURCE_PATTERNS = (
    re.compile(r"(?:123456|234567|345678|456789|987654|876543)"),
    re.compile(r"(.)\1{5,}"),
    re.compile(r"(?:xxxx|abc123|example|placeholder|dummy)", re.IGNORECASE),
)
RETRYABLE_FAILURE_CATEGORIES = {"retryable_search_failure", "retryable_parse_failure"}


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
    keep_prefixes = ("PATH", "HOME", "LANG", "LC_", "SSL_", "HTTP_", "HTTPS_", "ALL_PROXY", "NO_PROXY")
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
    evidence = {
        "search_plan": plan,
        "search_backend": "lobechat_searxng",
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
        "search_backend": "lobechat_searxng",
        "search_queries": _coerce_search_queries(plan.get("search_queries") or plan.get("queries")),
        "search_result_count": len(search_results),
        "search_result_urls": [str(item.get("url") or "") for item in search_results[:20] if item.get("url")],
        "search_attempts": search_attempts,
        "repair_policy": "bounded_repair_fail_closed",
    }
    return json.dumps(parsed, ensure_ascii=False, indent=2)


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
        "boundary": "independent_research_lab_no_main_pool_write",
        **dict(validation_result.get("summary") or {}),
    }
    session.commit()
    session.refresh(run)
    return serialize_shortpick_run(session, run, include_raw=True)


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
    parsed = [item for item in candidates if item.parse_status == "parsed" and item.symbol != "PARSE_FAILED"]
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
        "candidate_count": len(candidates),
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
    benchmark_sync = _sync_shortpick_benchmarks(session) if parsed_candidates else {"status": "skipped", "reason": "no_parsed_candidates"}
    updated = 0
    for candidate in parsed_candidates:
        market_sync = _sync_shortpick_candidate_market_data(session, candidate)
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
        }
        return existing

    round_record = session.get(ShortpickModelRound, candidate.round_id) if candidate.round_id else None
    signal_available_at = _shortpick_signal_available_at(run, round_record)
    signal_trade_day = signal_available_at.date()
    latest_bar_day = bars[-1].observed_at.date()
    if latest_bar_day <= signal_trade_day:
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
        }
        return existing

    entry_index = next((idx for idx, bar in enumerate(bars) if bar.observed_at.date() > signal_trade_day), None)
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
        }
        return existing

    tradeability = _shortpick_entry_tradeability(candidate=candidate, bars=bars, entry_index=entry_index)
    if tradeability["tradeability_status"] != SHORTPICK_OFFICIAL_TRADEABILITY_STATUS:
        entry = bars[entry_index]
        existing.status = str(tradeability["tradeability_status"])
        existing.entry_at = entry.observed_at
        existing.entry_close = entry.close_price
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
            "market_data_sync": market_sync or {},
        }
        return existing

    exit_index = entry_index + horizon
    if exit_index >= len(bars):
        available_forward_bars = max(len(bars) - entry_index - 1, 0)
        existing.status = "pending_forward_window"
        existing.entry_at = bars[entry_index].observed_at
        existing.entry_close = bars[entry_index].close_price
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
            "market_data_sync": market_sync or {},
        }
        return existing
    window = bars[entry_index : exit_index + 1]
    entry = window[0]
    exit_bar = window[-1]
    returns = [(bar.close_price / entry.close_price) - 1 for bar in window if entry.close_price]
    stock_return = (exit_bar.close_price / entry.close_price) - 1 if entry.close_price else None
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
    )
    if primary_return is None:
        existing.status = "pending_benchmark_data"
    else:
        existing.status = "completed"
    existing.entry_at = entry.observed_at
    existing.exit_at = exit_bar.observed_at
    existing.entry_close = entry.close_price
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
        "market_data_sync": market_sync or {},
        "note": "后验验证只读取行情，不回写主量化推荐或模拟盘。",
    }
    return existing


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
    evidence: dict[str, Any] = {
        "tradeability_status": SHORTPICK_OFFICIAL_TRADEABILITY_STATUS,
        "entry_open": entry.open_price,
        "entry_high": entry.high_price,
        "entry_low": entry.low_price,
        "entry_close": entry.close_price,
        "entry_trade_day": entry.observed_at.date().isoformat(),
        "inferred_limit_band": limit_band,
    }
    if previous is not None:
        day_return = (entry.close_price / previous.close_price) - 1 if previous.close_price else None
        evidence.update(
            {
                "previous_close": previous.close_price,
                "previous_trade_day": previous.observed_at.date().isoformat(),
                "entry_day_return": day_return,
            }
        )
        one_price = (
            _float_near(entry.open_price, entry.high_price)
            and _float_near(entry.high_price, entry.low_price)
            and _float_near(entry.low_price, entry.close_price)
        )
        if day_return is not None and one_price and day_return >= limit_band * 0.95:
            evidence["tradeability_status"] = "entry_unfillable_limit_up"
            evidence["reason"] = "Entry day appears to be one-price limit-up, so official validation cannot assume a fill."
    else:
        evidence["tradeability_status"] = "tradeability_uncertain"
        evidence["reason"] = "No previous close exists to infer limit-up fillability."
    return evidence


def _infer_shortpick_limit_band(candidate: ShortpickCandidate) -> float:
    symbol = candidate.symbol.upper()
    name = candidate.name.upper()
    if "ST" in name:
        return LIMIT_UP_BANDS["st"]
    if symbol.endswith(".BJ"):
        return LIMIT_UP_BANDS["beijing"]
    ticker = symbol.split(".", 1)[0]
    if ticker.startswith(("300", "301", "688")):
        return LIMIT_UP_BANDS["star_or_chinext"]
    return LIMIT_UP_BANDS["default"]


def _float_near(left: float | None, right: float | None, *, tolerance: float = 1e-6) -> bool:
    if left is None or right is None:
        return False
    return abs(float(left) - float(right)) <= tolerance


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
) -> dict[str, dict[str, Any]]:
    hs300 = _shortpick_primary_benchmark()
    csi1000_definition = {
        "benchmark_id": "CSI1000",
        "symbol": CSI_BENCHMARKS["CSI1000"]["symbol"],
        "label": CSI_BENCHMARKS["CSI1000"]["label"],
    }
    return {
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
        SHORTPICK_BENCHMARK_DIMENSION_SECTOR: _shortpick_sector_benchmark_dimension(
            session,
            candidate=candidate,
            stock_return=stock_return,
            entry_day=entry_day,
            exit_day=exit_day,
        ),
    }


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


def serialize_shortpick_run(session: Session, run: ShortpickExperimentRun, *, include_raw: bool) -> dict[str, Any]:
    rounds = session.scalars(
        select(ShortpickModelRound).where(ShortpickModelRound.run_id == run.id).order_by(ShortpickModelRound.id.asc())
    ).all()
    candidates = session.scalars(
        select(ShortpickCandidate).where(ShortpickCandidate.run_id == run.id).order_by(ShortpickCandidate.id.asc())
    ).all()
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
        "summary": {
            **dict(run.summary_payload or {}),
            **_run_operational_summary(session, run, rounds=rounds, candidates=candidates),
        },
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
        ],
    }


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
    }


def list_shortpick_runs(
    session: Session,
    *,
    status: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    limit: int = 20,
    offset: int = 0,
    include_raw: bool = False,
) -> dict[str, Any]:
    normalized_limit = max(1, min(int(limit), 100))
    normalized_offset = max(0, int(offset))
    query = select(ShortpickExperimentRun)
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
        "items": [serialize_shortpick_run(session, run, include_raw=include_raw) for run in runs],
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

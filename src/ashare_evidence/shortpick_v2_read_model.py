from __future__ import annotations

import copy
import json
import os
import threading
import time
from datetime import UTC, date, datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from ashare_evidence.shortpick_v2_h10_paper_governance import (
    ENTRY_POLICY as H10_PAPER_GOVERNANCE_ENTRY_POLICY,
)
from ashare_evidence.shortpick_v2_h10_paper_governance import (
    H10_QUIET_CAPITAL_SHADOW_CONFIG_ID,
    H10_QUIET_CHAMPION_CONFIG_ID,
    H10_QUIET_DIAGNOSTIC_90K_CONFIG_ID,
    H10_QUIET_PAPER_CANDIDATE_CONFIG_IDS,
    SHORTPICK_V2_H10_PAPER_GOVERNANCE_ARTIFACT_FAMILY,
    validate_shortpick_v2_h10_paper_governance_payload,
)
from ashare_evidence.shortpick_v2_h10_paper_governance import (
    LEDGER_POLICY as H10_PAPER_GOVERNANCE_LEDGER_POLICY,
)
from ashare_evidence.shortpick_v2_h10_paper_governance import (
    PAPER_TRACKING_STATUS as H10_PAPER_GOVERNANCE_PAPER_TRACKING_STATUS,
)
from ashare_evidence.shortpick_v2_h10_paper_governance import (
    RECOMMENDATION_STATUS as H10_PAPER_GOVERNANCE_RECOMMENDATION_STATUS,
)

SHORTPICK_V2_REPLAY_ARTIFACT_FAMILY = "shortpick_v2_replay_artifact"
SHORTPICK_V2_RULE_SELECTION_ARTIFACT_FAMILY = "shortpick_v2_rule_selection_artifact"
SHORTPICK_V2_PAPER_TRACKING_LEDGER_FAMILY = "shortpick_v2_paper_tracking_ledger"
SHORTPICK_V2_SCHEMA_VERSION = "v1"
SHORTPICK_V2_CLAIM_CEILING = "research_observation"
SHORTPICK_V2_REPLAY_EVIDENCE_BASIS = "historical_account_replay"
SHORTPICK_V2_SELECTION_EVIDENCE_BASIS = "historical_account_replay_selection"
SHORTPICK_V2_PAPER_EVIDENCE_BASIS = "true_forward_tracking"
SHORTPICK_V2_RULE_SELECTION_POLICY_VERSION = "shortpick_v2_rule_selection_v2"
SHORTPICK_V2_PAPER_CONTRACT_REF = "docs/contracts/SHORTPICK_LAB_V2_PAPER_TRACKING_CONTRACT_2026-06-12.md"
SHORTPICK_V2_TRACKING_START_DATE = "2026-05-08"
SHORTPICK_V2_DEFAULT_INITIAL_CASH = 200_000.0
SHORTPICK_V2_DEFAULT_BOARD_LOT_SIZE = 100
SHORTPICK_V2_SELECTED_CONFIG_IDS: tuple[str, ...] = ()
SHORTPICK_V2_BASELINE_CONFIG_IDS = ("top1_or_skip_v1",)
SHORTPICK_V2_HOLDOUT_CONFIG_IDS: tuple[str, ...] = ()
SHORTPICK_V2_REJECTED_CONFIG_IDS = (
    "top3_fallback_v1",
    "fixed_notional_40k_top5_v1",
    "position_cap_utilization_top5_v1",
    "conservative_cash_reserve_60k_top5_v1",
)
SHORTPICK_V2_ALLOWED_ACTIONS = ("buy_primary", "buy_fallback", "skip")
SHORTPICK_V2_FORBIDDEN_ACTIONS = ("delay_buy", "later_buy", "retry_buy", "discretionary_buy")

SHORTPICK_V2_REPLAY_ARTIFACT_ENV = "ASHARE_SHORTPICK_V2_REPLAY_ARTIFACT"
SHORTPICK_V2_RULE_SELECTION_ARTIFACT_ENV = "ASHARE_SHORTPICK_V2_RULE_SELECTION_ARTIFACT"
SHORTPICK_V2_PAPER_TRACKING_LEDGER_ARTIFACT_ENV = "ASHARE_SHORTPICK_V2_PAPER_TRACKING_LEDGER_ARTIFACT"
SHORTPICK_V2_H10_PAPER_GOVERNANCE_ARTIFACT_ENV = "ASHARE_SHORTPICK_V2_H10_PAPER_GOVERNANCE_ARTIFACT"

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SHORTPICK_V2_REPLAY_ARTIFACT_CANDIDATES = (
    Path("output/shortpick-v2-replay-artifact-20260612.json"),
    Path("output/shortpick-v2-replay-artifact.json"),
)
SHORTPICK_V2_RULE_SELECTION_ARTIFACT_CANDIDATES = (
    Path("output/shortpick-v2-rule-selection-artifact-20260612.json"),
    Path("output/shortpick-v2-rule-selection-artifact.json"),
)
SHORTPICK_V2_PAPER_TRACKING_LEDGER_ARTIFACT_CANDIDATES = (
    Path("output/shortpick-v2-paper-tracking-ledger.json"),
)
SHORTPICK_V2_PAPER_TRACKING_LEDGER_SCHEMA_PATH = (
    PROJECT_ROOT / "docs/contracts/registry/schemas/shortpick_v2_paper_tracking_ledger.schema.json"
)
SHORTPICK_V2_H10_PAPER_GOVERNANCE_ARTIFACT_CANDIDATES = (
    Path("docs/archive/SHORTPICK_LAB_V2_H10_PAPER_GOVERNANCE_ARTIFACT_2026-06-15.json"),
    Path("output/shortpick-v2-h10-paper-governance-artifact.json"),
)
SHORTPICK_V2_DECISION_SAMPLE_LIMIT_MAX = 40
SHORTPICK_V2_PAPER_DISPLAY_REPLAY_ROW_LIMIT = 240
SHORTPICK_V2_PAPER_DISPLAY_MIN_SIGNAL_SYMBOL_COUNT = 45
SHORTPICK_V2_PAPER_DISPLAY_LOOKBACK_DAYS = 120
SHORTPICK_V2_PAPER_DISPLAY_SOURCE_ID = "quiet_breakout_rank2_poolhot10_mtw"
SHORTPICK_V2_PAPER_DISPLAY_SOURCE_LABEL = "安静突破 Rank2：热度池达标时取第 2 名，周一、周二、周三触发"
SHORTPICK_V2_PAPER_DISPLAY_CACHE_TTL_SECONDS = float(
    os.getenv("ASHARE_SHORTPICK_V2_PAPER_DISPLAY_CACHE_TTL_SECONDS", "300")
)
_paper_display_replay_cache_lock = threading.Lock()
_paper_display_replay_cache: dict[
    tuple[Any, ...],
    tuple[float, list[dict[str, Any]], dict[str, Any], list[dict[str, Any]]],
] = {}


def build_shortpick_v2_historical_replay_read_model(
    *,
    sample_limit: int = 20,
    replay_artifact_path: str | Path | None = None,
    rule_selection_artifact_path: str | Path | None = None,
    paper_governance_artifact_path: str | Path | None = None,
) -> dict[str, Any]:
    """Build the read-only v2 historical replay projection from precomputed artifacts."""
    bounded_sample_limit = _bounded_sample_limit(sample_limit)
    replay_path = _resolve_artifact_path(
        explicit_path=replay_artifact_path,
        env_var=SHORTPICK_V2_REPLAY_ARTIFACT_ENV,
        candidates=SHORTPICK_V2_REPLAY_ARTIFACT_CANDIDATES,
    )
    selection_path = _resolve_artifact_path(
        explicit_path=rule_selection_artifact_path,
        env_var=SHORTPICK_V2_RULE_SELECTION_ARTIFACT_ENV,
        candidates=SHORTPICK_V2_RULE_SELECTION_ARTIFACT_CANDIDATES,
    )
    governance_path = _resolve_artifact_path(
        explicit_path=paper_governance_artifact_path,
        env_var=SHORTPICK_V2_H10_PAPER_GOVERNANCE_ARTIFACT_ENV,
        candidates=SHORTPICK_V2_H10_PAPER_GOVERNANCE_ARTIFACT_CANDIDATES,
    )
    paper_governance_artifact = _read_optional_paper_governance_artifact(governance_path)
    try:
        replay_artifact = _read_json_artifact(replay_path, label="shortpick v2 replay")
        selection_artifact = _read_json_artifact(selection_path, label="shortpick v2 rule selection")
    except LookupError:
        if paper_governance_artifact is None:
            raise
        return _h10_only_historical_replay_read_model(
            paper_governance_artifact=paper_governance_artifact,
            governance_path=governance_path,
            replay_path=replay_path,
            selection_path=selection_path,
            decision_sample_limit=bounded_sample_limit,
        )
    _validate_replay_artifact(replay_artifact)
    _validate_rule_selection_artifact(selection_artifact)
    _validate_replay_selection_alignment(replay_artifact, selection_artifact)

    result_by_config = _replay_results_by_config(replay_artifact)
    selected_configs = (
        _paper_governance_config_readouts(paper_governance_artifact)
        if paper_governance_artifact is not None
        else _config_readouts(
            selection_artifact.get("selected_configs"),
            result_by_config=result_by_config,
            decision_sample_limit=bounded_sample_limit,
        )
    )
    baseline_configs = _config_readouts(
        selection_artifact.get("baseline_configs"),
        result_by_config=result_by_config,
        decision_sample_limit=bounded_sample_limit,
    )
    holdout_configs = _config_readouts(
        selection_artifact.get("holdout_configs"),
        result_by_config=result_by_config,
        decision_sample_limit=bounded_sample_limit,
    )
    rejected_configs = _config_readouts(
        selection_artifact.get("rejected_configs"),
        result_by_config=result_by_config,
        decision_sample_limit=bounded_sample_limit,
    )
    if paper_governance_artifact is not None:
        baseline_configs = _legacy_strategy_search_readouts(baseline_configs, legacy_role="legacy_baseline_control")
        holdout_configs = _legacy_strategy_search_readouts(holdout_configs, legacy_role="legacy_holdout")
        rejected_configs = _legacy_strategy_search_readouts(rejected_configs, legacy_role="legacy_rejected")
    diagnostic_configs = _paper_governance_diagnostic_readouts(paper_governance_artifact)
    data_scope = replay_artifact.get("data_scope") if isinstance(replay_artifact.get("data_scope"), dict) else {}
    h10_strategy_inventory = _h10_strategy_inventory(paper_governance_artifact, governance_path)
    status = "ready" if paper_governance_artifact is not None else str(selection_artifact.get("status") or "blocked")
    return {
        "generated_at": _now_iso(),
        "status": status,
        "claim_ceiling": SHORTPICK_V2_CLAIM_CEILING,
        "evidence_basis": SHORTPICK_V2_SELECTION_EVIDENCE_BASIS,
        "ui_language": (
            "试验田v2历史回放展示预计算账户路径研究观察；H10 quiet champion 为当前固定对标线。"
            if paper_governance_artifact is not None
            else "试验田v2历史回放仅展示预计算账户路径研究观察。"
        ),
        "data_disclaimer": (
            "历史回放读取固定来源文件；H10 历史收益只用于研究对标，不计为真实前向纸面收益。"
            if paper_governance_artifact is not None
            else "历史回放读取固定来源文件，不构成投资建议，不代表生产交易能力。"
        ),
        "source_artifacts": {
            "replay": _artifact_ref(replay_artifact, replay_path),
            "rule_selection": _artifact_ref(selection_artifact, selection_path),
            "h10_paper_governance": (
                _artifact_ref(paper_governance_artifact, governance_path)
                if paper_governance_artifact is not None
                else {
                    "path": str(governance_path),
                    "status": "missing",
                    "artifact_family": SHORTPICK_V2_H10_PAPER_GOVERNANCE_ARTIFACT_FAMILY,
                }
            ),
        },
        "data_scope": data_scope,
        "selection_policy": selection_artifact.get("selection_policy") or {},
        "summary": {
            "selected_config_count": len(selected_configs),
            "baseline_config_count": len(baseline_configs),
            "holdout_config_count": len(holdout_configs) + len(diagnostic_configs),
            "rejected_config_count": len(rejected_configs),
            "signal_day_count": data_scope.get("signal_day_count"),
            "trade_day_count": data_scope.get("trade_day_count"),
            "coverage_status": data_scope.get("coverage_status"),
            "decision_sample_limit": bounded_sample_limit,
            "h10_strategy_inventory": h10_strategy_inventory,
            "legacy_strategy_search_context": (
                {
                    "status": "reference_only",
                    "source": "older_strategy_search_artifacts",
                    "note": "旧 strategy-search 结果只作为历史弱结果参照，不属于 H10 quiet champion 同窗候选。",
                }
                if paper_governance_artifact is not None
                else None
            ),
        },
        "selected_configs": selected_configs,
        "baseline_configs": baseline_configs,
        "holdout_configs": [*holdout_configs, *diagnostic_configs],
        "rejected_configs": rejected_configs,
        "leakage_audit": {
            "status": "passed",
            "replay": replay_artifact.get("leakage_audit") or {},
            "rule_selection": selection_artifact.get("leakage_audit") or {},
            "h10_governance": (paper_governance_artifact or {}).get("leakage_audit") or {},
            "read_model_policy": (
                "read_only_precomputed_artifacts_with_h10_governance_overlay_no_dynamic_replay"
                if paper_governance_artifact is not None
                else "read_only_precomputed_artifacts_no_dynamic_replay"
            ),
        },
        "research_labeling": _research_labeling(
            evidence_basis=SHORTPICK_V2_SELECTION_EVIDENCE_BASIS,
            ui_language="试验田v2历史回放仅展示预计算账户路径研究观察。",
        ),
        "event_refs": [
            "shortpick_v2.phase6.backend_read_model.historical_replay",
            str(replay_artifact.get("artifact_id") or ""),
            str(selection_artifact.get("artifact_id") or ""),
            str((paper_governance_artifact or {}).get("artifact_id") or ""),
        ],
    }


def build_shortpick_v2_paper_tracking_read_model(
    *,
    include_records: bool = True,
    session: Any | None = None,
    rule_selection_artifact_path: str | Path | None = None,
    ledger_artifact_path: str | Path | None = None,
    paper_governance_artifact_path: str | Path | None = None,
) -> dict[str, Any]:
    """Build the read-only v2 paper tracking projection without deriving rows from v1."""
    selection_path = _resolve_artifact_path(
        explicit_path=rule_selection_artifact_path,
        env_var=SHORTPICK_V2_RULE_SELECTION_ARTIFACT_ENV,
        candidates=SHORTPICK_V2_RULE_SELECTION_ARTIFACT_CANDIDATES,
    )
    selection_artifact = _read_json_artifact(selection_path, label="shortpick v2 rule selection")
    _validate_rule_selection_artifact(selection_artifact)
    ledger_path = _resolve_artifact_path(
        explicit_path=ledger_artifact_path,
        env_var=SHORTPICK_V2_PAPER_TRACKING_LEDGER_ARTIFACT_ENV,
        candidates=SHORTPICK_V2_PAPER_TRACKING_LEDGER_ARTIFACT_CANDIDATES,
    )
    governance_path = _resolve_artifact_path(
        explicit_path=paper_governance_artifact_path,
        env_var=SHORTPICK_V2_H10_PAPER_GOVERNANCE_ARTIFACT_ENV,
        candidates=SHORTPICK_V2_H10_PAPER_GOVERNANCE_ARTIFACT_CANDIDATES,
    )
    paper_governance_artifact = _read_optional_paper_governance_artifact(governance_path)
    if ledger_path.exists():
        ledger_artifact = _read_json_artifact(ledger_path, label="shortpick v2 paper tracking ledger")
        _validate_paper_tracking_ledger_artifact(ledger_artifact)
        _validate_paper_tracking_selection_alignment(
            ledger_artifact,
            selection_artifact,
            paper_governance_artifact=paper_governance_artifact,
        )
        return _paper_tracking_ledger_read_model(
            ledger_artifact,
            ledger_path=ledger_path,
            selection_artifact=selection_artifact,
            selection_path=selection_path,
            paper_governance_artifact=paper_governance_artifact,
            governance_path=governance_path,
            include_records=include_records,
            session=session,
        )
    return _contract_ready_paper_tracking_read_model(
        selection_artifact=selection_artifact,
        selection_path=selection_path,
        ledger_path=ledger_path,
        paper_governance_artifact=paper_governance_artifact,
        governance_path=governance_path,
        include_records=include_records,
        session=session,
    )


def _h10_only_historical_replay_read_model(
    *,
    paper_governance_artifact: dict[str, Any],
    governance_path: Path,
    replay_path: Path,
    selection_path: Path,
    decision_sample_limit: int,
) -> dict[str, Any]:
    selected_configs = _paper_governance_config_readouts(paper_governance_artifact)
    diagnostic_configs = _paper_governance_diagnostic_readouts(paper_governance_artifact)
    analysis_scope = (
        paper_governance_artifact.get("analysis_scope")
        if isinstance(paper_governance_artifact.get("analysis_scope"), dict)
        else {}
    )
    data_scope = {
        "signal_date_from": analysis_scope.get("signal_date_from"),
        "signal_date_to": analysis_scope.get("signal_date_to"),
        "signal_day_count": None,
        "trade_day_count": None,
        "coverage_status": "h10_governance_summary_only",
    }
    return {
        "generated_at": _now_iso(),
        "status": "ready",
        "claim_ceiling": SHORTPICK_V2_CLAIM_CEILING,
        "evidence_basis": "h10_governance_summary_only",
        "ui_language": "试验田v2历史回放展示 H10 quiet champion 固定对标统计。",
        "data_disclaimer": "H10 历史收益只用于研究对标，不计为真实前向纸面收益。",
        "source_artifacts": {
            "replay": {
                "path": str(replay_path),
                "status": "missing",
                "artifact_family": SHORTPICK_V2_REPLAY_ARTIFACT_FAMILY,
            },
            "rule_selection": {
                "path": str(selection_path),
                "status": "missing",
                "artifact_family": SHORTPICK_V2_RULE_SELECTION_ARTIFACT_FAMILY,
            },
            "h10_paper_governance": _artifact_ref(paper_governance_artifact, governance_path),
        },
        "data_scope": data_scope,
        "selection_policy": {
            "policy_version": SHORTPICK_V2_RULE_SELECTION_POLICY_VERSION,
            "source": "h10_paper_governance_summary_only",
        },
        "summary": {
            "selected_config_count": len(selected_configs),
            "baseline_config_count": 0,
            "holdout_config_count": len(diagnostic_configs),
            "rejected_config_count": 0,
            "signal_day_count": data_scope.get("signal_day_count"),
            "trade_day_count": data_scope.get("trade_day_count"),
            "coverage_status": data_scope.get("coverage_status"),
            "decision_sample_limit": decision_sample_limit,
            "h10_strategy_inventory": _h10_strategy_inventory(paper_governance_artifact, governance_path),
        },
        "selected_configs": selected_configs,
        "baseline_configs": [],
        "holdout_configs": diagnostic_configs,
        "rejected_configs": [],
        "leakage_audit": {
            "status": "passed",
            "h10_governance": paper_governance_artifact.get("leakage_audit") or {},
            "read_model_policy": "h10_governance_summary_only_no_dynamic_replay",
        },
        "research_labeling": _research_labeling(
            evidence_basis="h10_governance_summary_only",
            ui_language="试验田v2历史回放展示 H10 quiet champion 固定对标统计。",
        ),
        "event_refs": [
            "shortpick_v2.phase6.backend_read_model.historical_replay.h10_summary_only",
            str(paper_governance_artifact.get("artifact_id") or ""),
        ],
    }


def _contract_ready_paper_tracking_read_model(
    *,
    selection_artifact: dict[str, Any],
    selection_path: Path,
    ledger_path: Path,
    paper_governance_artifact: dict[str, Any] | None,
    governance_path: Path,
    include_records: bool,
    session: Any | None,
) -> dict[str, Any]:
    paper_governance = _paper_governance_projection(paper_governance_artifact, governance_path)
    selected_configs = (
        _paper_governance_config_readouts(paper_governance_artifact)
        if paper_governance_artifact is not None
        else _paper_config_readouts(selection_artifact.get("selected_configs"))
    )
    baseline_configs = _paper_config_readouts(selection_artifact.get("baseline_configs"))
    is_blocked = not selected_configs
    summary = {
        "record_count": 0,
        "buy_count": 0,
        "skip_count": 0,
        "source_gap_count": 0,
        "selected_config_count": len(selected_configs),
        "baseline_config_count": len(baseline_configs),
        "tracking_start_date": SHORTPICK_V2_TRACKING_START_DATE,
        "paper_governance_status": paper_governance.get("recommendation_status") if paper_governance else None,
        "paper_tracking_status": paper_governance.get("paper_tracking_status") if paper_governance else None,
    }
    paper_display = _paper_tracking_display_projection(
        records=[],
        selected_configs=selected_configs,
        baseline_configs=baseline_configs,
        paper_governance=paper_governance,
        summary=summary,
        session=session,
        include_display_rows=include_records,
    )
    _merge_paper_display_summary(summary, paper_display)
    payload: dict[str, Any] = {
        "generated_at": _now_iso(),
        "status": "blocked" if is_blocked else "contract_ready",
        "current_status": (
            "blocked"
            if is_blocked
            else (
                str(paper_governance.get("recommendation_status") or H10_PAPER_GOVERNANCE_RECOMMENDATION_STATUS)
                if paper_governance
                else "contract_ready"
            )
        ),
        "current_message": (
            "No v2 config currently qualifies under market-outperformance and annualized-return gates."
            if is_blocked
            else (
                "H10 governance is ready for future observation, but no true-forward v2 paper ledger rows exist yet."
                if paper_governance
                else "V2 paper tracking writer has not produced true-forward rows yet."
            )
        ),
        "claim_ceiling": SHORTPICK_V2_CLAIM_CEILING,
        "evidence_basis": SHORTPICK_V2_PAPER_EVIDENCE_BASIS,
        "ui_language": "试验田v2纸面追踪仅展示账户路径纸面研究证据。",
        "data_disclaimer": (
            "当前为空投影：没有通过大盘超额收益和 30% 年化门槛的 v2 候选配置。"
            if is_blocked
            else (
                "当前为空投影：H10 fixed85/fixed80 已进入未来观察候选，但没有真实前向 v2 paper ledger rows。历史回放不计为纸面追踪收益。"
                if paper_governance
                else "当前为空投影：已固定候选配置，但没有真实前向 v2 paper ledger rows。"
            )
        ),
        "source_contract_ref": SHORTPICK_V2_PAPER_CONTRACT_REF,
        "source_artifacts": {
            "rule_selection": _artifact_ref(selection_artifact, selection_path),
            "paper_ledger": {
                "path": str(ledger_path),
                "status": "missing",
                "artifact_family": SHORTPICK_V2_PAPER_TRACKING_LEDGER_FAMILY,
            },
            "paper_governance": (
                _artifact_ref(paper_governance_artifact, governance_path)
                if paper_governance_artifact is not None
                else {
                    "path": str(governance_path),
                    "status": "missing",
                    "artifact_family": SHORTPICK_V2_H10_PAPER_GOVERNANCE_ARTIFACT_FAMILY,
                }
            ),
        },
        "tracking_window": _tracking_window_contract(),
        "account_contract": _account_contract(selection_artifact, paper_governance_artifact=paper_governance_artifact),
        "row_contract": _row_contract(paper_governance_artifact=paper_governance_artifact),
        "selected_configs": selected_configs,
        "baseline_configs": baseline_configs,
        "paper_governance": paper_governance,
        "paper_display": paper_display,
        "summary": summary,
        "leakage_audit": {
            "status": "passed",
            "read_model_policy": "no_v1_paper_tracking_fallback_no_dynamic_replay",
            "notes": [
                (
                    "Missing v2 paper ledger is represented as blocked empty records when no config qualifies."
                    if is_blocked
                    else "Missing v2 paper ledger is represented as contract_ready empty records."
                ),
                "Rows are not inferred from the existing Short Pick Lab v1 paper tracking ledger.",
                "H10 governance state is metadata only and does not create paper ledger rows.",
            ],
        },
        "research_labeling": _research_labeling(
            evidence_basis=SHORTPICK_V2_PAPER_EVIDENCE_BASIS,
            ui_language="试验田v2纸面追踪仅展示账户路径纸面研究证据。",
        ),
        "event_refs": [
            (
                "shortpick_v2.phase6.backend_read_model.paper_tracking_blocked"
                if is_blocked
                else "shortpick_v2.phase6.backend_read_model.paper_tracking_contract_ready"
            ),
            str(selection_artifact.get("artifact_id") or ""),
        ],
    }
    payload["records"] = []
    return payload


def _paper_tracking_ledger_read_model(
    ledger_artifact: dict[str, Any],
    *,
    ledger_path: Path,
    selection_artifact: dict[str, Any],
    selection_path: Path,
    paper_governance_artifact: dict[str, Any] | None,
    governance_path: Path,
    include_records: bool,
    session: Any | None,
) -> dict[str, Any]:
    records = [record for record in ledger_artifact.get("records") or [] if isinstance(record, dict)]
    paper_governance = _paper_governance_projection(paper_governance_artifact, governance_path)
    selected_configs = (
        _paper_governance_config_readouts(paper_governance_artifact)
        if paper_governance_artifact is not None
        else _paper_config_readouts(selection_artifact.get("selected_configs"))
    )
    baseline_configs = _paper_config_readouts(selection_artifact.get("baseline_configs"))
    summary = dict(ledger_artifact.get("summary") or _records_summary(records))
    paper_display = _paper_tracking_display_projection(
        records=records,
        selected_configs=selected_configs,
        baseline_configs=baseline_configs,
        paper_governance=paper_governance,
        summary=summary,
        session=session,
        include_display_rows=include_records,
    )
    _merge_paper_display_summary(summary, paper_display)
    payload: dict[str, Any] = {
        "generated_at": _now_iso(),
        "status": str(ledger_artifact.get("status") or "active"),
        "current_status": str(ledger_artifact.get("status") or "active"),
        "current_message": None,
        "claim_ceiling": SHORTPICK_V2_CLAIM_CEILING,
        "evidence_basis": SHORTPICK_V2_PAPER_EVIDENCE_BASIS,
        "ui_language": "试验田v2纸面追踪仅展示账户路径纸面研究证据。",
        "data_disclaimer": "纸面追踪是研究观察，不构成投资建议或生产交易自动化。",
        "source_contract_ref": str(ledger_artifact.get("source_contract_ref") or SHORTPICK_V2_PAPER_CONTRACT_REF),
        "source_artifacts": {
            "rule_selection": _artifact_ref(selection_artifact, selection_path),
            "paper_ledger": _artifact_ref(ledger_artifact, ledger_path),
            "paper_governance": (
                _artifact_ref(paper_governance_artifact, governance_path)
                if paper_governance_artifact is not None
                else {
                    "path": str(governance_path),
                    "status": "missing",
                    "artifact_family": SHORTPICK_V2_H10_PAPER_GOVERNANCE_ARTIFACT_FAMILY,
                }
            ),
        },
        "tracking_window": ledger_artifact.get("tracking_window") or _tracking_window_contract(),
        "account_contract": ledger_artifact.get("account_contract")
        or _account_contract(selection_artifact, paper_governance_artifact=paper_governance_artifact),
        "row_contract": ledger_artifact.get("row_contract")
        or _row_contract(paper_governance_artifact=paper_governance_artifact),
        "selected_configs": selected_configs,
        "baseline_configs": baseline_configs,
        "paper_governance": paper_governance,
        "paper_display": paper_display,
        "summary": summary,
        "leakage_audit": ledger_artifact.get("leakage_audit")
        or {
            "status": "passed",
            "read_model_policy": "v2_paper_ledger_only",
        },
        "research_labeling": ledger_artifact.get("research_labeling")
        or _research_labeling(
            evidence_basis=SHORTPICK_V2_PAPER_EVIDENCE_BASIS,
            ui_language="试验田v2纸面追踪仅展示账户路径纸面研究证据。",
        ),
        "event_refs": ledger_artifact.get("event_refs") or ["shortpick_v2.phase6.backend_read_model.paper_tracking"],
    }
    payload["records"] = records if include_records else []
    return payload


def _paper_tracking_display_projection(
    *,
    records: list[dict[str, Any]],
    selected_configs: list[dict[str, Any]],
    baseline_configs: list[dict[str, Any]],
    paper_governance: dict[str, Any],
    summary: dict[str, Any],
    session: Any | None,
    include_display_rows: bool,
) -> dict[str, Any]:
    true_forward_rows = [_paper_display_row_from_ledger(record) for record in records] if include_display_rows else []
    if include_display_rows:
        replay_rows, coverage, account_curves = _paper_display_replay_rows_from_session(
            session=session,
            active_config_ids=_paper_display_active_config_ids(selected_configs),
        )
    else:
        replay_rows = []
        account_curves = []
        coverage = _empty_paper_display_coverage()
        coverage["source_status"] = "summary_rows_omitted"
        coverage["source_status_label"] = "摘要接口不返回明细行，也不执行回放重算"
    coverage["true_forward_record_count"] = len(records)
    coverage["account_curve_scope"] = "回放账户曲线"
    if true_forward_rows:
        true_forward_account_curves = _paper_display_account_curves_from_session(
            session=session,
            rows=[*replay_rows, *true_forward_rows],
        )
        if true_forward_account_curves:
            account_curves = true_forward_account_curves
            coverage["account_curve_scope"] = "回放与真实前向合并账户曲线"
        else:
            coverage["account_curve_scope"] = "回放账户曲线，真实前向暂缺行情估值"
    internal_display_rows = _sorted_display_rows([*true_forward_rows, *replay_rows])[
        :SHORTPICK_V2_PAPER_DISPLAY_REPLAY_ROW_LIMIT
    ]
    table_rows = _paper_display_visible_rows(internal_display_rows) if include_display_rows else []
    action_counts = _display_action_counts(internal_display_rows)
    latest_trade = _latest_display_trade(internal_display_rows)
    status_label = "纸面追踪运行中" if records else "等待真实前向记录"
    if not selected_configs:
        status_label = "暂未进入纸面追踪"
    return {
        "title": "试验田v2纸面追踪",
        "status_label": status_label,
        "subtitle": "这里展示的是纸面追踪主视图；2026-05-08 起补齐的历史区间统一标记为“回放”。",
        "latest_trade": latest_trade,
        "strategy_explanation": _paper_display_strategy_explanation(
            selected_configs=selected_configs,
            baseline_configs=baseline_configs,
            paper_governance=paper_governance,
        ),
        "charts": [
            {
                "title": "覆盖情况",
                "subtitle": "回放行用于补齐观察窗口，不计入真实前向纸面收益。",
                "kind": "bar",
                "data": [
                    {"name": "真实前向记录", "value": int(coverage.get("true_forward_record_count") or 0)},
                    {"name": "回放展示行", "value": int(coverage.get("replay_row_count") or 0)},
                    {"name": "数据缺口行", "value": int(coverage.get("source_gap_count") or 0)},
                ],
            },
            {
                "title": "动作分布",
                "subtitle": "只允许当天买入首选、当天买入候补或不买入；没有延迟买入。",
                "kind": "bar",
                "data": [
                    {"name": "买入首选", "value": action_counts.get("buy_primary", 0)},
                    {"name": "买入候补", "value": action_counts.get("buy_fallback", 0)},
                    {"name": "不买入", "value": action_counts.get("skip", 0)},
                    {"name": "数据缺口", "value": action_counts.get("source_gap", 0)},
                ],
            },
        ],
        "table": {
            "title": "模拟交易明细",
            "columns": [
                {"key": "signal_date", "label": "信号日"},
                {"key": "tracking_tag", "label": "记录类型"},
                {"key": "strategy_text", "label": "策略"},
                {"key": "action_text", "label": "动作"},
                {"key": "stock_text", "label": "标的"},
                {"key": "selected_rank_text", "label": "入选位置"},
                {"key": "quantity_text", "label": "数量"},
                {"key": "cash_after_text", "label": "剩余现金"},
                {"key": "exit_state_text", "label": "退出状态"},
                {"key": "exit_date_text", "label": "退出日"},
                {"key": "return_text", "label": "收益"},
                {"key": "note", "label": "说明"},
            ],
            "rows": table_rows,
            "empty_text": "暂无可展示的纸面追踪记录。",
        },
        "account_curves": account_curves,
        "coverage": coverage,
        "summary_cards": [
            {"label": "真实前向记录", "value": str(int(summary.get("record_count") or 0))},
            {"label": "回放展示行", "value": str(int(coverage.get("replay_row_count") or 0))},
            {"label": "覆盖起点", "value": str(coverage.get("coverage_start") or SHORTPICK_V2_TRACKING_START_DATE)},
            {"label": "最新来源信号日", "value": str(coverage.get("latest_source_signal_date") or "暂无")},
        ],
    }


def _paper_display_replay_rows_from_session(
    *,
    session: Any | None,
    active_config_ids: tuple[str, ...],
) -> tuple[list[dict[str, Any]], dict[str, Any], list[dict[str, Any]]]:
    if session is None:
        coverage = _empty_paper_display_coverage()
        coverage["source_status"] = "no_market_data_session"
        coverage["source_status_label"] = "未连接本地行情库，无法生成回放补齐行"
        return [], coverage, []
    cache_key = _paper_display_replay_cache_key(session, active_config_ids)
    if isinstance(cache_key, tuple):
        now = time.monotonic()
        with _paper_display_replay_cache_lock:
            cached = _paper_display_replay_cache.get(cache_key)
            if cached is not None and now - cached[0] <= SHORTPICK_V2_PAPER_DISPLAY_CACHE_TTL_SECONDS:
                return copy.deepcopy(cached[1]), copy.deepcopy(cached[2]), copy.deepcopy(cached[3])
    else:
        return [], cache_key, []

    try:
        rows, coverage, account_curves = _build_paper_display_replay_rows_from_session(
            session=session,
            active_config_ids=active_config_ids,
        )
    except Exception:
        coverage = _empty_paper_display_coverage()
        coverage["source_status"] = "replay_generation_error"
        coverage["source_status_label"] = "回放展示生成失败；真实前向记录不受影响，请稍后重试或检查本地行情库"
        return [], coverage, []

    now = time.monotonic()
    with _paper_display_replay_cache_lock:
        expired_cache_keys = [
            existing_key
            for existing_key, cached in _paper_display_replay_cache.items()
            if now - cached[0] > SHORTPICK_V2_PAPER_DISPLAY_CACHE_TTL_SECONDS
        ]
        for existing_key in expired_cache_keys:
            _paper_display_replay_cache.pop(existing_key, None)
        _paper_display_replay_cache[cache_key] = (
            now,
            copy.deepcopy(rows),
            copy.deepcopy(coverage),
            copy.deepcopy(account_curves),
        )
    return rows, coverage, account_curves


def _paper_display_replay_cache_key(
    session: Any,
    active_config_ids: tuple[str, ...],
) -> tuple[Any, ...] | dict[str, Any]:
    try:
        from sqlalchemy import func, select

        from ashare_evidence.models import MarketBar

        bind = session.get_bind()
        database_identity = str(getattr(bind, "url", "unknown"))
        latest_observed_at = session.execute(
            select(func.max(MarketBar.observed_at)).where(MarketBar.timeframe == "1d")
        ).scalar_one()
    except Exception:
        coverage = _empty_paper_display_coverage()
        coverage["source_status"] = "market_data_read_error"
        coverage["source_status_label"] = "读取本地行情库失败，无法生成回放补齐行"
        return coverage
    return (
        database_identity,
        tuple(active_config_ids),
        latest_observed_at.isoformat() if hasattr(latest_observed_at, "isoformat") else str(latest_observed_at or ""),
    )


def _build_paper_display_replay_rows_from_session(
    *,
    session: Any,
    active_config_ids: tuple[str, ...],
) -> tuple[list[dict[str, Any]], dict[str, Any], list[dict[str, Any]]]:
    coverage = _empty_paper_display_coverage()
    coverage["true_forward_record_count"] = 0
    rule_configs = _paper_display_rule_configs(active_config_ids)
    if not rule_configs:
        coverage["source_status"] = "no_active_h10_config"
        coverage["source_status_label"] = "当前没有可进入纸面观察的 H10 候选策略"
        return [], coverage, []

    from ashare_evidence.market_rules import ACCOUNT_PROFILE_NEW_RETAIL_CASH, filter_account_eligible_series
    from ashare_evidence.shortpick_market_factor_study import ENTRY_PRICE_SOURCE_NEXT_CLOSE, INDEX_SYMBOLS
    from ashare_evidence.shortpick_portfolio_backtest import _trade_days
    from ashare_evidence.shortpick_ranked_pool_replay_input import _load_daily_series_for_replay_window
    from ashare_evidence.shortpick_v2_replay import (
        DEFAULT_COST_BPS,
        DEFAULT_STAMP_TAX_BPS,
        build_shortpick_v2_replay_artifact_from_series,
    )
    from ashare_evidence.shortpick_v2_strategy_search import build_h10_quiet_champion_strategy_search_candidate_sources

    start_date = date.fromisoformat(SHORTPICK_V2_TRACKING_START_DATE)
    latest_market_day = _latest_daily_market_bar_day(session)
    if latest_market_day is None or latest_market_day < start_date:
        coverage["source_status"] = "no_market_data_after_start"
        coverage["source_status_label"] = "本地行情库没有覆盖 2026-05-08 之后的数据"
        coverage["coverage_end"] = latest_market_day.isoformat() if latest_market_day is not None else None
        coverage["latest_source_signal_date"] = coverage["coverage_end"]
        return [], coverage, []
    raw_series_by_symbol = _load_daily_series_for_replay_window(
        session,
        start_date=start_date - timedelta(days=SHORTPICK_V2_PAPER_DISPLAY_LOOKBACK_DAYS),
        end_date=latest_market_day,
    )
    series_by_symbol, account_eligibility = filter_account_eligible_series(
        raw_series_by_symbol,
        account_profile=ACCOUNT_PROFILE_NEW_RETAIL_CASH,
        include_index_symbols=INDEX_SYMBOLS,
    )
    latest_bar_day = _latest_series_day(series_by_symbol)
    if latest_bar_day is None or latest_bar_day < start_date:
        coverage["source_status"] = "no_market_data_after_start"
        coverage["source_status_label"] = "本地行情库没有覆盖 2026-05-08 之后的数据"
        coverage["coverage_end"] = latest_bar_day.isoformat() if latest_bar_day is not None else None
        coverage["latest_source_signal_date"] = coverage["coverage_end"]
        return [], coverage, []
    latest_bar_day = min(latest_bar_day, latest_market_day)

    available_signal_days = _trade_days(
        series_by_symbol,
        start_date=start_date,
        end_date=latest_bar_day,
        min_symbol_count=SHORTPICK_V2_PAPER_DISPLAY_MIN_SIGNAL_SYMBOL_COUNT,
    )
    coverage["coverage_end"] = (
        available_signal_days[-1].isoformat() if available_signal_days else latest_bar_day.isoformat()
    )
    coverage["latest_source_signal_date"] = coverage["coverage_end"]
    coverage["available_source_signal_dates"] = [day.isoformat() for day in available_signal_days]
    coverage["available_source_signal_day_count"] = len(available_signal_days)
    coverage["source_status"] = "ready" if available_signal_days else "no_eligible_signal_days"
    coverage["source_status_label"] = (
        "已读取本地行情库生成回放覆盖"
        if available_signal_days
        else "本地行情库存在数据，但没有达到策略可用的信号日"
    )
    coverage["account_profile_label"] = str(account_eligibility.get("account_profile_label") or "新开户普通现金账户")
    if not available_signal_days:
        return [], coverage, []

    candidate_sources = build_h10_quiet_champion_strategy_search_candidate_sources(
        series_by_symbol,
        signal_days=available_signal_days,
        pool_limit=40,
        rank_limit=6,
        source_ids=(SHORTPICK_V2_PAPER_DISPLAY_SOURCE_ID,),
    )
    display_source = next(
        (source for source in candidate_sources if source.source_id == SHORTPICK_V2_PAPER_DISPLAY_SOURCE_ID),
        None,
    )
    if display_source is None:
        coverage["source_status"] = "missing_h10_replay_source"
        coverage["source_status_label"] = "缺少 H10 安静突破回放源，已按数据缺口保留信号日"
        rows = [
            _paper_display_gap_row(
                signal_date,
                config.config_id,
                reason_text="缺少 H10 安静突破回放源，无法生成当天动作判断。",
                note="该信号日保留为覆盖缺口，避免把源缺失误读成策略结果。",
            )
            for signal_date in coverage["available_source_signal_dates"]
            for config in rule_configs
        ]
        _finalize_paper_display_coverage(
            coverage,
            rows,
            active_config_ids=tuple(config.config_id for config in rule_configs),
        )
        return rows, coverage, []
    display_trade_days = _trade_days(
        series_by_symbol,
        start_date=start_date,
        end_date=latest_bar_day + timedelta(days=80),
        min_symbol_count=SHORTPICK_V2_PAPER_DISPLAY_MIN_SIGNAL_SYMBOL_COUNT,
    )
    replay_artifact = build_shortpick_v2_replay_artifact_from_series(
        series_by_symbol,
        signal_days=available_signal_days,
        trade_days=display_trade_days,
        selections=display_source.selections,
        start_date=start_date,
        end_date=latest_bar_day,
        initial_cash=SHORTPICK_V2_DEFAULT_INITIAL_CASH,
        entry_price_source=ENTRY_PRICE_SOURCE_NEXT_CLOSE,
        horizon_days=10,
        pool_limit=40,
        rank_limit=6,
        cost_bps=DEFAULT_COST_BPS,
        stamp_tax_bps=DEFAULT_STAMP_TAX_BPS,
        account_profile=str(account_eligibility.get("account_profile") or ACCOUNT_PROFILE_NEW_RETAIL_CASH),
        stock_like_series_count=len([symbol for symbol in series_by_symbol if symbol not in INDEX_SYMBOLS]),
        coverage_notes=["纸面追踪显示投影只读生成，不刷新行情、不写入 ledger。"],
        rule_configs=rule_configs,
        decision_sample_limit=len(available_signal_days),
    )
    rows = _paper_display_rows_from_replay_artifact(
        replay_artifact,
        active_config_ids=tuple(config.config_id for config in rule_configs),
        available_signal_dates=coverage["available_source_signal_dates"],
        symbol_names={
            symbol: str(getattr(series, "name", "") or symbol)
            for symbol, series in series_by_symbol.items()
        },
        series_by_symbol=series_by_symbol,
        trade_days=display_trade_days,
    )
    _finalize_paper_display_coverage(
        coverage,
        rows,
        active_config_ids=tuple(config.config_id for config in rule_configs),
    )
    account_curves = _paper_display_account_curves_from_rows(
        rows,
        series_by_symbol=series_by_symbol,
        trade_days=display_trade_days,
        initial_cash=SHORTPICK_V2_DEFAULT_INITIAL_CASH,
    )
    coverage["account_curve_count"] = len(account_curves)
    return rows, coverage, account_curves


def _paper_display_rows_from_replay_artifact(
    replay_artifact: dict[str, Any],
    *,
    active_config_ids: tuple[str, ...],
    available_signal_dates: list[str],
    symbol_names: dict[str, str],
    series_by_symbol: dict[str, Any],
    trade_days: list[date],
) -> list[dict[str, Any]]:
    result_by_config = _replay_results_by_config(replay_artifact)
    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for config_id in active_config_ids:
        result = result_by_config.get(config_id) or {}
        for decision in result.get("decision_samples") or []:
            if not isinstance(decision, dict):
                continue
            signal_date = str(decision.get("signal_date") or "")
            if not signal_date or signal_date not in available_signal_dates:
                continue
            seen.add((signal_date, config_id))
            rows.append(
                _paper_display_row_from_replay_decision(
                    decision,
                    config_id,
                    symbol_names=symbol_names,
                    series_by_symbol=series_by_symbol,
                    trade_days=trade_days,
                )
            )
    for signal_date in available_signal_dates:
        for config_id in active_config_ids:
            if (signal_date, config_id) in seen:
                continue
            rows.append(_paper_display_gap_row(signal_date, config_id))
    return rows


def _finalize_paper_display_coverage(
    coverage: dict[str, Any],
    rows: list[dict[str, Any]],
    *,
    active_config_ids: tuple[str, ...],
) -> None:
    replay_dates = sorted(
        {str(row.get("signal_date") or "") for row in rows if row.get("source_state") != "source_gap"}
    )
    gap_dates = sorted({str(row.get("signal_date") or "") for row in rows if row.get("source_state") == "source_gap"})
    row_pairs = {
        (str(row.get("signal_date") or ""), str(row.get("config_id") or ""))
        for row in rows
        if row.get("signal_date") and row.get("config_id")
    }
    expected_pairs = {
        (str(signal_date), config_id)
        for signal_date in coverage.get("available_source_signal_dates") or []
        for config_id in active_config_ids
    }
    coverage["covered_signal_dates"] = replay_dates
    coverage["gap_signal_dates"] = gap_dates
    coverage["replay_row_count"] = len(
        [row for row in rows if row.get("tracking_tag") == "回放" and row.get("source_state") != "source_gap"]
    )
    coverage["source_gap_count"] = len([row for row in rows if row.get("source_state") == "source_gap"])
    coverage["row_or_gap_accounting_passed"] = set(coverage["available_source_signal_dates"]) <= (
        set(replay_dates) | set(gap_dates)
    )
    coverage["available_source_signal_config_count"] = len(expected_pairs)
    coverage["row_or_gap_config_accounting_passed"] = expected_pairs <= row_pairs


def _paper_display_row_from_replay_decision(
    decision: dict[str, Any],
    config_id: str,
    *,
    symbol_names: dict[str, str],
    series_by_symbol: dict[str, Any],
    trade_days: list[date],
) -> dict[str, Any]:
    action = str(decision.get("action") or "skip")
    symbol = str(decision.get("symbol") or "")
    quantity = _optional_int(decision.get("quantity"))
    cash_before = _optional_float(decision.get("cash_before"))
    cash_after = _optional_float(decision.get("cash_after"))
    signal_date = str(decision.get("signal_date") or "")
    exit_projection = _paper_display_exit_projection(
        decision,
        series_by_symbol=series_by_symbol,
        trade_days=trade_days,
    )
    return {
        "row_id": f"replay:{signal_date}:{config_id}",
        "signal_date": signal_date,
        "signal_date_text": signal_date or "未知日期",
        "tracking_tag": "回放",
        "tracking_tag_tone": "warning",
        "config_id": config_id,
        "strategy_text": _paper_config_label(config_id),
        "symbol": symbol,
        "action": action,
        "action_text": _paper_action_label(action),
        "reason_text": _paper_reason_label(str(decision.get("reason") or "")),
        "stock_text": _stock_display_text(symbol, symbol_names=symbol_names),
        "selected_rank_text": _rank_display_text(decision.get("selected_rank")),
        "quantity": quantity,
        "quantity_text": _quantity_text(quantity),
        "cash_before": cash_before,
        "cash_before_text": _format_cny(cash_before),
        "cash_after": cash_after,
        "cash_after_text": _format_cny(cash_after),
        **exit_projection,
        "source_state": "observed",
        "note": "回放：不计入真实前向收益。",
    }


def _paper_display_gap_row(
    signal_date: str,
    config_id: str,
    *,
    reason_text: str = "本地数据不足以生成完整入场或持有期回放。",
    note: str = "该信号日保留为覆盖缺口，避免把缺失数据误读成策略结果。",
) -> dict[str, Any]:
    return {
        "row_id": f"replay-gap:{signal_date}:{config_id}",
        "signal_date": signal_date,
        "signal_date_text": signal_date,
        "tracking_tag": "回放",
        "tracking_tag_tone": "warning",
        "config_id": config_id,
        "strategy_text": _paper_config_label(config_id),
        "action": "source_gap",
        "action_text": "数据缺口",
        "reason_text": reason_text,
        "stock_text": "无",
        "selected_rank_text": "无",
        "quantity": 0,
        "quantity_text": "0 股",
        "cash_before": None,
        "cash_before_text": "暂无",
        "cash_after": None,
        "cash_after_text": "暂无",
        "entry_date": None,
        "entry_date_text": "未入场",
        "exit_date": None,
        "exit_date_text": "未入场",
        "exit_state": "not_entered",
        "exit_state_text": "未入场",
        "exit_reason_text": "未入场",
        "holding_days_text": "无",
        "return": None,
        "return_text": "暂无",
        "source_state": "source_gap",
        "note": note,
    }


def _paper_display_row_from_ledger(record: dict[str, Any]) -> dict[str, Any]:
    action = str(record.get("decision_action") or "skip")
    symbol = str(record.get("symbol") or "")
    quantity = _optional_int(record.get("quantity"))
    cash_before = _optional_float(record.get("cash_before"))
    cash_after = _optional_float(record.get("cash_after"))
    signal_date = str(record.get("signal_date") or "")
    stock_return = _optional_float(record.get("stock_return"))
    exit_trade_date = str(record.get("exit_trade_date") or record.get("exit_date") or "")
    exit_reason = str(record.get("exit_reason") or "")
    return {
        "row_id": str(record.get("record_id") or f"ledger:{signal_date}:{record.get('config_id') or ''}"),
        "signal_date": signal_date,
        "signal_date_text": signal_date or "未知日期",
        "tracking_tag": "真实前向",
        "tracking_tag_tone": "success",
        "config_id": str(record.get("config_id") or ""),
        "strategy_text": _paper_config_label(str(record.get("config_id") or "")),
        "symbol": symbol,
        "action": action,
        "action_text": _paper_action_label(action),
        "reason_text": _paper_reason_label(str(record.get("reason") or "")),
        "stock_text": _stock_display_text(symbol, symbol_names={}),
        "selected_rank_text": _rank_display_text(record.get("selected_rank")),
        "quantity": quantity,
        "quantity_text": _quantity_text(quantity),
        "cash_before": cash_before,
        "cash_before_text": _format_cny(cash_before),
        "cash_after": cash_after,
        "cash_after_text": _format_cny(cash_after),
        "entry_date": record.get("entry_trade_date"),
        "entry_date_text": str(record.get("entry_trade_date") or "未入场"),
        "exit_date": exit_trade_date or None,
        "exit_date_text": exit_trade_date or "等待退出",
        "exit_state": "completed" if exit_trade_date else "pending",
        "exit_state_text": "已退出" if exit_trade_date else "等待退出",
        "exit_reason_text": _paper_exit_reason_label(exit_reason),
        "holding_days_text": "按 ledger 记录",
        "return": stock_return,
        "return_text": _format_percent(stock_return),
        "source_state": str(record.get("source_state") or "observed"),
        "note": "真实前向：来自 v2 ledger。",
    }


def _paper_display_strategy_explanation(
    *,
    selected_configs: list[dict[str, Any]],
    baseline_configs: list[dict[str, Any]],
    paper_governance: dict[str, Any],
) -> dict[str, Any]:
    selected_labels = [_paper_config_label(str(row.get("config_id") or "")) for row in selected_configs]
    baseline_labels = [_paper_config_label(str(row.get("config_id") or "")) for row in baseline_configs]
    if not selected_labels:
        selected_text = "当前没有通过治理门槛并进入纸面观察的 v2 候选策略。"
    else:
        selected_text = "；".join(selected_labels)
    risk_text = "H10 候选仍带有开放风险，必须继续用真实前向记录验证。"
    if paper_governance.get("high_risk_flag_count"):
        risk_text = "H10 候选仍有高风险标记，当前只能作为未来观察，不是生产可用结论。"
    return {
        "title": "策略说明",
        "items": [
            {
                "label": "选股策略",
                "value": SHORTPICK_V2_PAPER_DISPLAY_SOURCE_LABEL,
            },
            {
                "label": "买入策略",
                "value": (
                    "20 万初始资金；8.5 万方案和 8 万方案分别按目标金额买入，必须满足 100 股整手；"
                    "首选买不了时只允许当天候补，否则不买。"
                ),
            },
            {
                "label": "当前观察策略",
                "value": selected_text,
            },
            {
                "label": "对照策略",
                "value": "；".join(baseline_labels) if baseline_labels else "暂无对照策略。",
            },
            {
                "label": "禁止动作",
                "value": "不允许延迟买入、隔天补买、重试买入；9 万方案仅保留诊断，不进入纸面追踪。",
            },
            {
                "label": "证据口径",
                "value": "带“回放”标签的记录只用于补齐观察窗口，不计入真实前向纸面收益。",
            },
            {
                "label": "风险提示",
                "value": risk_text,
            },
        ],
    }


def _paper_display_rule_configs(active_config_ids: tuple[str, ...]) -> tuple[Any, ...]:
    from ashare_evidence.shortpick_v2_replay import ShortpickV2RuleConfig

    configs: list[Any] = []
    for config_id in active_config_ids:
        target_notional = _paper_config_target_notional(config_id)
        if target_notional is None:
            continue
        configs.append(
            ShortpickV2RuleConfig(
                config_id=config_id,
                family="fixed_notional_lot_rounding",
                candidate_rank_limit=5,
                fallback_enabled=True,
                target_mode="fixed_notional",
                target_notional=target_notional,
                allowed_actions=("buy_primary", "buy_fallback", "skip"),
            )
        )
    return tuple(configs)


def _paper_display_active_config_ids(selected_configs: list[dict[str, Any]]) -> tuple[str, ...]:
    allowed = set(H10_QUIET_PAPER_CANDIDATE_CONFIG_IDS)
    return tuple(
        config_id
        for config_id in (str(row.get("config_id") or "") for row in selected_configs)
        if config_id in allowed
    )


def _paper_config_target_notional(config_id: str) -> float | None:
    return {
        H10_QUIET_CHAMPION_CONFIG_ID: 85_000.0,
        H10_QUIET_CAPITAL_SHADOW_CONFIG_ID: 80_000.0,
    }.get(config_id)


def _paper_config_label(config_id: str) -> str:
    labels = {
        H10_QUIET_PAPER_CANDIDATE_CONFIG_IDS[0]: "8.5 万目标买入方案",
        H10_QUIET_PAPER_CANDIDATE_CONFIG_IDS[1]: "8 万目标买入方案",
        "top1_or_skip_v1": "首位候选对照策略",
        "conservative_cash_reserve_60k_top5_v1": "保留 6 万现金的旧候选策略",
        "fixed_notional_40k_top5_v1": "4 万目标买入旧候选策略",
    }
    return labels.get(config_id, "未命名策略")


def _paper_action_label(action: str) -> str:
    return {
        "buy_primary": "买入首选",
        "buy_fallback": "买入候补",
        "skip": "不买入",
        "source_gap": "数据缺口",
        "not_observed": "未观察",
    }.get(action, "未识别动作")


def _paper_reason_label(reason: str) -> str:
    return {
        "bought_primary": "首选标的满足资金和整手要求。",
        "bought_fallback": "首选不满足要求，改买当天候补标的。",
        "insufficient_cash": "可用现金不足，无法买满一手。",
        "board_lot_minimum": "不足 100 股整手要求。",
        "cash_reserve": "触发现金保留约束。",
        "position_count_cap": "持仓数量已经达到上限。",
        "position_value_cap": "单一标的仓位上限已满。",
        "limit_up_unfillable": "入场日涨停不可成交。",
        "no_ranked_candidates": "当天没有满足 H10 安静突破条件的候选。",
        "no_executable_candidate": "当天候选都不满足买入约束。",
    }.get(reason, "按既定规则完成判断。")


def _paper_exit_reason_label(reason: str) -> str:
    return {
        "mechanical_horizon": "机械10日退出",
        "mechanical_10d": "机械10日退出",
        "take_profit": "止盈退出",
        "stop_loss": "止损退出",
        "trailing_stop": "移动止损退出",
        "": "等待退出",
    }.get(reason, "按既定规则退出")


def _paper_display_exit_projection(
    decision: dict[str, Any],
    *,
    series_by_symbol: dict[str, Any],
    trade_days: list[date],
) -> dict[str, Any]:
    action = str(decision.get("action") or "")
    symbol = str(decision.get("symbol") or "")
    signal_date = str(decision.get("signal_date") or "")
    if action not in {"buy_primary", "buy_fallback"}:
        return {
            "entry_date": None,
            "entry_date_text": "未入场",
            "exit_date": None,
            "exit_date_text": "未入场",
            "exit_state": "not_entered",
            "exit_state_text": "未入场",
            "exit_reason_text": "未入场",
            "holding_days_text": "无",
            "return": None,
            "return_text": "暂无",
        }
    try:
        signal_day = date.fromisoformat(signal_date)
    except ValueError:
        return _paper_display_pending_exit_projection("信号日缺失")
    if signal_day not in trade_days:
        return _paper_display_pending_exit_projection("等待入场日")
    entry_index = trade_days.index(signal_day) + 1
    if entry_index >= len(trade_days):
        return _paper_display_pending_exit_projection("等待入场日")
    entry_day = trade_days[entry_index]
    exit_index = entry_index + 10
    if exit_index >= len(trade_days):
        return {
            "entry_date": entry_day.isoformat(),
            "entry_date_text": entry_day.isoformat(),
            "exit_date": None,
            "exit_date_text": "等待10日窗口",
            "exit_state": "pending",
            "exit_state_text": "等待10日窗口",
            "exit_reason_text": "机械10日未到期",
            "holding_days_text": "未满10个交易日",
            "return": None,
            "return_text": "暂无",
        }
    exit_day = trade_days[exit_index]
    series = series_by_symbol.get(symbol)
    entry_close = _series_close_on_day(series, entry_day)
    exit_close = _series_close_on_day(series, exit_day)
    stock_return = (
        round(float(exit_close) / float(entry_close) - 1.0, 6)
        if entry_close not in {None, 0} and exit_close is not None
        else None
    )
    if stock_return is None:
        return {
            "entry_date": entry_day.isoformat(),
            "entry_date_text": entry_day.isoformat(),
            "exit_date": exit_day.isoformat(),
            "exit_date_text": exit_day.isoformat(),
            "exit_state": "source_gap",
            "exit_state_text": "退出数据缺口",
            "exit_reason_text": "缺少入场或退出价",
            "holding_days_text": "10个交易日",
            "return": None,
            "return_text": "暂无",
        }
    return {
        "entry_date": entry_day.isoformat(),
        "entry_date_text": entry_day.isoformat(),
        "exit_date": exit_day.isoformat(),
        "exit_date_text": exit_day.isoformat(),
        "exit_state": "completed",
        "exit_state_text": "已按10日退出",
        "exit_reason_text": "机械10日退出",
        "holding_days_text": "10个交易日",
        "return": stock_return,
        "return_text": _format_percent(stock_return),
    }


def _paper_display_pending_exit_projection(reason_text: str) -> dict[str, Any]:
    return {
        "entry_date": None,
        "entry_date_text": reason_text,
        "exit_date": None,
        "exit_date_text": "等待10日窗口",
        "exit_state": "pending",
        "exit_state_text": "等待10日窗口",
        "exit_reason_text": reason_text,
        "holding_days_text": "未满10个交易日",
        "return": None,
        "return_text": "暂无",
    }


def _series_close_on_day(series: Any, target_day: date) -> float | None:
    if series is None:
        return None
    index = getattr(series, "by_day", {}).get(target_day)
    bars = getattr(series, "bars", None)
    if index is None or not bars:
        return None
    try:
        return float(bars[index].close)
    except (IndexError, TypeError, ValueError):
        return None


def _paper_display_account_curves_from_rows(
    rows: list[dict[str, Any]],
    *,
    series_by_symbol: dict[str, Any],
    trade_days: list[date],
    initial_cash: float,
) -> list[dict[str, Any]]:
    latest_observed_day = _latest_series_day(series_by_symbol)
    if latest_observed_day is None:
        return []
    observed_trade_days = [day for day in trade_days if day <= latest_observed_day]
    if not observed_trade_days:
        return []

    grouped_rows: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        if row.get("action") not in {"buy_primary", "buy_fallback"}:
            continue
        if _optional_int(row.get("quantity")) is None or _optional_int(row.get("quantity")) <= 0:
            continue
        config_id = str(row.get("config_id") or "")
        if not config_id:
            continue
        grouped_rows.setdefault(config_id, []).append(row)

    curves: list[dict[str, Any]] = []
    for config_id, config_rows in grouped_rows.items():
        entries: list[dict[str, Any]] = []
        for row in sorted(config_rows, key=lambda item: str(item.get("entry_date") or item.get("signal_date") or "")):
            entry_day = _parse_iso_date_or_none(row.get("entry_date"))
            if entry_day is None or entry_day > latest_observed_day:
                continue
            symbol = str(row.get("symbol") or "")
            quantity = _optional_int(row.get("quantity"))
            if not symbol or quantity is None or quantity <= 0:
                continue
            entry_close = _series_close_on_day(series_by_symbol.get(symbol), entry_day)
            cash_before = _optional_float(row.get("cash_before"))
            cash_after = _optional_float(row.get("cash_after"))
            entry_cost = (
                max(float(cash_before) - float(cash_after), 0.0)
                if cash_before is not None and cash_after is not None
                else 0.0
            )
            if entry_cost <= 0 and entry_close is not None:
                entry_cost = float(quantity) * float(entry_close)
            if entry_cost <= 0:
                continue
            entries.append(
                {
                    "entry_day": entry_day,
                    "exit_day": _parse_iso_date_or_none(row.get("exit_date")),
                    "symbol": symbol,
                    "quantity": quantity,
                    "entry_cost": entry_cost,
                    "stock_return": _optional_float(row.get("return")),
                    "last_close": entry_close,
                }
            )
        if not entries:
            continue

        entry_days = {entry["entry_day"] for entry in entries}
        entries_by_day: dict[date, list[dict[str, Any]]] = {}
        for entry in entries:
            entries_by_day.setdefault(entry["entry_day"], []).append(entry)
        first_entry_day = min(entry_days)
        account_days = [day for day in observed_trade_days if day >= first_entry_day]

        cash = float(initial_cash)
        peak_nav = float(initial_cash)
        open_positions: list[dict[str, Any]] = []
        points: list[dict[str, Any]] = []
        completed_trade_count = 0
        for day in account_days:
            for entry in entries_by_day.get(day, []):
                cash -= float(entry["entry_cost"])
                open_positions.append(dict(entry))

            position_value = 0.0
            for position in open_positions:
                close = _series_close_on_day(series_by_symbol.get(str(position["symbol"])), day)
                if close is None:
                    close = position.get("last_close") or (
                        float(position["entry_cost"]) / float(position["quantity"])
                    )
                else:
                    position["last_close"] = close
                position_value += float(position["quantity"]) * float(close)

            nav = cash + position_value
            peak_nav = max(peak_nav, nav)
            drawdown = nav / peak_nav - 1.0 if peak_nav else 0.0
            points.append(
                {
                    "date": day.isoformat(),
                    "nav": round(nav, 2),
                    "account_return": round(nav / float(initial_cash) - 1.0, 6) if initial_cash else 0.0,
                    "drawdown": round(drawdown, 6),
                    "cash": round(cash, 2),
                    "position_value": round(position_value, 2),
                    "open_position_count": len(open_positions),
                }
            )

            remaining_positions: list[dict[str, Any]] = []
            for position in open_positions:
                exit_day = position.get("exit_day")
                if exit_day is not None and exit_day <= day:
                    stock_return = position.get("stock_return")
                    if stock_return is None:
                        close = _series_close_on_day(series_by_symbol.get(str(position["symbol"])), day)
                        stock_return = (
                            float(close) * float(position["quantity"]) / float(position["entry_cost"]) - 1.0
                            if close is not None and position["entry_cost"]
                            else 0.0
                        )
                    cash += float(position["entry_cost"]) * (1.0 + float(stock_return))
                    completed_trade_count += 1
                else:
                    remaining_positions.append(position)
            open_positions = remaining_positions

        if not points:
            continue
        latest_point = points[-1]
        curves.append(
            {
                "strategy": _paper_config_label(config_id),
                "initial_cash": round(float(initial_cash), 2),
                "latest_nav": latest_point["nav"],
                "latest_return": latest_point["account_return"],
                "max_drawdown": min(point["drawdown"] for point in points),
                "point_count": len(points),
                "completed_trade_count": completed_trade_count,
                "points": points,
            }
        )
    return sorted(curves, key=lambda curve: str(curve.get("strategy") or ""))


def _paper_display_account_curves_from_session(
    *,
    session: Any | None,
    rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if session is None or not rows:
        return []
    try:
        from ashare_evidence.market_rules import ACCOUNT_PROFILE_NEW_RETAIL_CASH, filter_account_eligible_series
        from ashare_evidence.shortpick_market_factor_study import INDEX_SYMBOLS
        from ashare_evidence.shortpick_portfolio_backtest import _trade_days
        from ashare_evidence.shortpick_ranked_pool_replay_input import _load_daily_series_for_replay_window

        start_date = date.fromisoformat(SHORTPICK_V2_TRACKING_START_DATE)
        latest_market_day = _latest_daily_market_bar_day(session)
        if latest_market_day is None or latest_market_day < start_date:
            return []
        raw_series_by_symbol = _load_daily_series_for_replay_window(
            session,
            start_date=start_date - timedelta(days=SHORTPICK_V2_PAPER_DISPLAY_LOOKBACK_DAYS),
            end_date=latest_market_day,
        )
        series_by_symbol, _account_eligibility = filter_account_eligible_series(
            raw_series_by_symbol,
            account_profile=ACCOUNT_PROFILE_NEW_RETAIL_CASH,
            include_index_symbols=INDEX_SYMBOLS,
        )
        latest_bar_day = _latest_series_day(series_by_symbol)
        if latest_bar_day is None or latest_bar_day < start_date:
            return []
        trade_days = _trade_days(
            series_by_symbol,
            start_date=start_date,
            end_date=min(latest_bar_day, latest_market_day),
            min_symbol_count=SHORTPICK_V2_PAPER_DISPLAY_MIN_SIGNAL_SYMBOL_COUNT,
        )
        return _paper_display_account_curves_from_rows(
            rows,
            series_by_symbol=series_by_symbol,
            trade_days=trade_days,
            initial_cash=SHORTPICK_V2_DEFAULT_INITIAL_CASH,
        )
    except Exception:
        return []


def _parse_iso_date_or_none(value: Any) -> date | None:
    if isinstance(value, date):
        return value
    if not isinstance(value, str) or not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _latest_display_trade(display_rows: list[dict[str, Any]]) -> dict[str, Any]:
    buys = [row for row in display_rows if row.get("action") in {"buy_primary", "buy_fallback"}]
    row = buys[0] if buys else (display_rows[0] if display_rows else None)
    if row is None:
        return {
            "title": "最新模拟交易",
            "tag": "暂无记录",
            "summary": "暂无可展示的模拟交易。",
            "items": [],
        }
    return {
        "title": "最新模拟交易",
        "tag": row.get("tracking_tag"),
        "summary": f"{row.get('signal_date_text')}：{row.get('action_text')}，{row.get('stock_text')}。",
        "items": [
            {"label": "信号日", "value": row.get("signal_date_text")},
            {"label": "记录类型", "value": row.get("tracking_tag")},
            {"label": "策略", "value": row.get("strategy_text")},
            {"label": "动作", "value": row.get("action_text")},
            {"label": "标的", "value": row.get("stock_text")},
            {"label": "数量", "value": row.get("quantity_text")},
            {"label": "剩余现金", "value": row.get("cash_after_text")},
            {"label": "退出", "value": row.get("exit_state_text")},
            {"label": "收益", "value": row.get("return_text")},
        ],
        "note": row.get("note"),
    }


def _paper_display_visible_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    visible_rows: list[dict[str, Any]] = []
    for index, row in enumerate(rows, start=1):
        visible_rows.append(
            {
                "row_key": f"paper-display-row-{index}",
                "signal_date": row.get("signal_date"),
                "signal_date_text": row.get("signal_date_text"),
                "tracking_tag": row.get("tracking_tag"),
                "tracking_tag_tone": row.get("tracking_tag_tone"),
                "strategy_text": row.get("strategy_text"),
                "action_text": row.get("action_text"),
                "reason_text": row.get("reason_text"),
                "stock_text": row.get("stock_text"),
                "selected_rank_text": row.get("selected_rank_text"),
                "quantity_text": row.get("quantity_text"),
                "cash_before_text": row.get("cash_before_text"),
                "cash_after_text": row.get("cash_after_text"),
                "entry_date_text": row.get("entry_date_text"),
                "exit_date_text": row.get("exit_date_text"),
                "exit_state_text": row.get("exit_state_text"),
                "exit_reason_text": row.get("exit_reason_text"),
                "holding_days_text": row.get("holding_days_text"),
                "return_text": row.get("return_text"),
                "note": row.get("note"),
            }
        )
    return visible_rows


def _sorted_display_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        rows,
        key=lambda row: (
            str(row.get("signal_date") or ""),
            str(row.get("tracking_tag") or ""),
            str(row.get("row_id") or ""),
        ),
        reverse=True,
    )


def _display_action_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        action = str(row.get("action") or "unknown")
        counts[action] = counts.get(action, 0) + 1
    return counts


def _merge_paper_display_summary(summary: dict[str, Any], paper_display: dict[str, Any]) -> None:
    coverage = paper_display.get("coverage") if isinstance(paper_display.get("coverage"), dict) else {}
    summary["true_forward_record_count"] = int(summary.get("record_count") or 0)
    summary["replay_record_count"] = int(coverage.get("replay_row_count") or 0)
    summary["display_source_gap_count"] = int(coverage.get("source_gap_count") or 0)
    summary["coverage_start"] = coverage.get("coverage_start")
    summary["coverage_end"] = coverage.get("coverage_end")
    summary["latest_source_signal_date"] = coverage.get("latest_source_signal_date")
    summary["row_or_gap_accounting_passed"] = coverage.get("row_or_gap_accounting_passed")
    summary["row_or_gap_config_accounting_passed"] = coverage.get("row_or_gap_config_accounting_passed")


def _empty_paper_display_coverage() -> dict[str, Any]:
    return {
        "coverage_start": SHORTPICK_V2_TRACKING_START_DATE,
        "coverage_end": None,
        "latest_source_signal_date": None,
        "source_status": "not_loaded",
        "source_status_label": "尚未生成回放覆盖",
        "account_profile_label": "新开户普通现金账户",
        "available_source_signal_dates": [],
        "available_source_signal_day_count": 0,
        "covered_signal_dates": [],
        "gap_signal_dates": [],
        "replay_row_count": 0,
        "source_gap_count": 0,
        "true_forward_record_count": 0,
        "row_or_gap_accounting_passed": False,
        "available_source_signal_config_count": 0,
        "row_or_gap_config_accounting_passed": False,
    }


def _latest_series_day(series_by_symbol: dict[str, Any]) -> date | None:
    days = [
        bar.day
        for symbol, series in series_by_symbol.items()
        if symbol and getattr(series, "bars", None)
        for bar in series.bars
    ]
    return max(days) if days else None


def _latest_daily_market_bar_day(session: Any) -> date | None:
    from sqlalchemy import func, select

    from ashare_evidence.models import MarketBar

    latest_observed_at = session.execute(
        select(func.max(MarketBar.observed_at)).where(MarketBar.timeframe == "1d")
    ).scalar_one()
    if latest_observed_at is None:
        return None
    if hasattr(latest_observed_at, "date"):
        return latest_observed_at.date()
    return None


def _stock_display_text(symbol: str, *, symbol_names: dict[str, str]) -> str:
    if not symbol:
        return "无"
    name = symbol_names.get(symbol)
    if name and name != symbol:
        return f"{name}（{symbol}）"
    return symbol


def _rank_display_text(value: object) -> str:
    rank = _optional_int(value)
    return "无" if rank is None else f"第 {rank} 位"


def _quantity_text(value: int | None) -> str:
    return "0 股" if value is None else f"{value} 股"


def _format_cny(value: float | None) -> str:
    if value is None:
        return "暂无"
    return f"{value:,.0f} 元"


def _format_percent(value: float | None) -> str:
    if value is None:
        return "暂无"
    return f"{value * 100:+.1f}%"


def _optional_int(value: object) -> int | None:
    try:
        if value is None:
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _optional_float(value: object) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _resolve_artifact_path(
    *,
    explicit_path: str | Path | None,
    env_var: str,
    candidates: tuple[Path, ...],
) -> Path:
    if explicit_path is not None:
        return Path(explicit_path).expanduser()
    configured = os.getenv(env_var)
    if configured:
        return Path(configured).expanduser()
    candidate_paths: list[Path] = []
    for candidate in candidates:
        candidate_paths.append(candidate)
        candidate_paths.append(PROJECT_ROOT / candidate)
    for candidate_path in candidate_paths:
        if candidate_path.exists():
            return candidate_path
    return PROJECT_ROOT / candidates[0]


def _read_json_artifact(path: Path, *, label: str) -> dict[str, Any]:
    if not path.exists():
        raise LookupError(f"{label} artifact is missing: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"{label} artifact is not valid JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"{label} artifact root must be a JSON object: {path}")
    return payload


def _read_optional_paper_governance_artifact(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    artifact = _read_json_artifact(path, label="shortpick v2 h10 paper governance")
    validation = validate_shortpick_v2_h10_paper_governance_payload(artifact)
    if validation["status"] != "passed":
        failed_ids = [
            str(check.get("check_id"))
            for check in validation.get("checks") or []
            if isinstance(check, dict) and not check.get("passed")
        ]
        raise ValueError(f"h10 paper governance artifact validation failed: {failed_ids}")
    return artifact


def _validate_replay_artifact(artifact: dict[str, Any]) -> None:
    _require_field(artifact, "artifact_family", SHORTPICK_V2_REPLAY_ARTIFACT_FAMILY, "replay")
    _require_field(artifact, "schema_version", SHORTPICK_V2_SCHEMA_VERSION, "replay")
    _require_field(artifact, "status", "ready", "replay")
    _require_field(artifact, "claim_ceiling", SHORTPICK_V2_CLAIM_CEILING, "replay")
    _require_field(artifact, "evidence_basis", SHORTPICK_V2_REPLAY_EVIDENCE_BASIS, "replay")
    leakage = artifact.get("leakage_audit") if isinstance(artifact.get("leakage_audit"), dict) else {}
    if leakage.get("status") != "passed":
        raise ValueError("replay leakage_audit.status must be passed")
    result_by_config = _replay_results_by_config(artifact)
    missing = sorted(set(_all_phase6_config_ids()) - set(result_by_config))
    if missing:
        raise ValueError(f"replay artifact is missing required v2 configs: {missing}")


def _validate_rule_selection_artifact(artifact: dict[str, Any]) -> None:
    _require_field(artifact, "artifact_family", SHORTPICK_V2_RULE_SELECTION_ARTIFACT_FAMILY, "rule selection")
    _require_field(artifact, "schema_version", SHORTPICK_V2_SCHEMA_VERSION, "rule selection")
    if artifact.get("status") not in {"ready", "blocked"}:
        raise ValueError("rule selection status must be ready or blocked")
    _require_field(artifact, "claim_ceiling", SHORTPICK_V2_CLAIM_CEILING, "rule selection")
    _require_field(artifact, "evidence_basis", SHORTPICK_V2_SELECTION_EVIDENCE_BASIS, "rule selection")
    policy = artifact.get("selection_policy") if isinstance(artifact.get("selection_policy"), dict) else {}
    if policy.get("policy_version") != SHORTPICK_V2_RULE_SELECTION_POLICY_VERSION:
        raise ValueError(f"rule selection policy_version must be {SHORTPICK_V2_RULE_SELECTION_POLICY_VERSION}")
    leakage = artifact.get("leakage_audit") if isinstance(artifact.get("leakage_audit"), dict) else {}
    if leakage.get("status") != "passed":
        raise ValueError("rule selection leakage_audit.status must be passed")
    required_config_ids = tuple(policy.get("required_config_ids") or _all_phase6_config_ids())
    if set(required_config_ids) != set(_all_phase6_config_ids()):
        raise ValueError("rule selection required_config_ids must match the v2 config universe")
    _require_section_config_ids(artifact, "baseline_configs", SHORTPICK_V2_BASELINE_CONFIG_IDS)
    _validate_rule_selection_sections(artifact, required_config_ids=required_config_ids)


def _validate_replay_selection_alignment(
    replay_artifact: dict[str, Any],
    selection_artifact: dict[str, Any],
) -> None:
    source_replay = selection_artifact.get("source_replay_artifact")
    if not isinstance(source_replay, dict):
        raise ValueError("rule selection source_replay_artifact must be present")
    if source_replay.get("artifact_id") != replay_artifact.get("artifact_id"):
        raise ValueError("rule selection source_replay_artifact.artifact_id does not match replay artifact")


def _validate_paper_tracking_ledger_artifact(artifact: dict[str, Any]) -> None:
    active_config_ids = _ledger_active_config_ids(artifact)
    _validate_paper_tracking_active_config_ids(active_config_ids)
    _validate_paper_tracking_ledger_schema(artifact)
    _require_field(artifact, "artifact_family", SHORTPICK_V2_PAPER_TRACKING_LEDGER_FAMILY, "paper tracking ledger")
    _require_field(artifact, "schema_version", SHORTPICK_V2_SCHEMA_VERSION, "paper tracking ledger")
    _require_field(artifact, "claim_ceiling", SHORTPICK_V2_CLAIM_CEILING, "paper tracking ledger")
    _require_field(artifact, "evidence_basis", SHORTPICK_V2_PAPER_EVIDENCE_BASIS, "paper tracking ledger")
    status = artifact.get("status")
    if status not in {"contract_ready", "active", "blocked"}:
        raise ValueError("paper tracking ledger status must be contract_ready, active, or blocked")
    tracking_window = artifact.get("tracking_window") if isinstance(artifact.get("tracking_window"), dict) else {}
    if tracking_window.get("start_date") != SHORTPICK_V2_TRACKING_START_DATE:
        raise ValueError(f"paper tracking ledger tracking_window.start_date must be {SHORTPICK_V2_TRACKING_START_DATE}")
    records = artifact.get("records")
    if not isinstance(records, list):
        raise ValueError("paper tracking ledger records must be a list")
    for record in records:
        if not isinstance(record, dict):
            raise ValueError("paper tracking ledger record must be an object")
        _validate_paper_tracking_record(record, active_config_ids=active_config_ids)


@lru_cache(maxsize=1)
def _paper_tracking_ledger_schema_validator() -> Draft202012Validator:
    try:
        schema = json.loads(SHORTPICK_V2_PAPER_TRACKING_LEDGER_SCHEMA_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(
            f"paper tracking ledger schema is not readable: {SHORTPICK_V2_PAPER_TRACKING_LEDGER_SCHEMA_PATH}"
        ) from exc
    if not isinstance(schema, dict):
        raise ValueError("paper tracking ledger schema root must be a JSON object")
    return Draft202012Validator(schema)


def _validate_paper_tracking_ledger_schema(artifact: dict[str, Any]) -> None:
    errors = sorted(
        _paper_tracking_ledger_schema_validator().iter_errors(artifact),
        key=lambda error: list(error.absolute_path),
    )
    if not errors:
        return
    details = []
    for error in errors[:5]:
        path = ".".join(str(part) for part in error.absolute_path) or "<root>"
        details.append(f"{path}: {error.message}")
    raise ValueError(f"paper tracking ledger schema validation failed: {'; '.join(details)}")


def _validate_paper_tracking_record(record: dict[str, Any], *, active_config_ids: tuple[str, ...]) -> None:
    config_id = str(record.get("config_id") or "")
    if config_id not in active_config_ids:
        raise ValueError(f"paper tracking record config_id is not active for Phase 6: {config_id}")
    signal_date = str(record.get("signal_date") or "")
    try:
        signal_day = date.fromisoformat(signal_date)
    except ValueError as exc:
        raise ValueError(f"paper tracking record signal_date must be ISO date: {signal_date}") from exc
    tracking_start = date.fromisoformat(SHORTPICK_V2_TRACKING_START_DATE)
    if signal_day < tracking_start:
        raise ValueError(
            f"paper tracking record signal_date must be on or after {SHORTPICK_V2_TRACKING_START_DATE}: "
            f"{signal_date}"
        )
    action = str(record.get("decision_action") or "")
    if action not in SHORTPICK_V2_ALLOWED_ACTIONS:
        raise ValueError(f"paper tracking record decision_action is not allowed: {action}")
    if action in SHORTPICK_V2_FORBIDDEN_ACTIONS:
        raise ValueError(f"paper tracking record contains delayed-entry action: {action}")
    evidence_basis = str(record.get("evidence_basis") or "")
    if evidence_basis != SHORTPICK_V2_PAPER_EVIDENCE_BASIS:
        raise ValueError("paper tracking record evidence_basis must be true_forward_tracking")


def _validate_paper_tracking_selection_alignment(
    ledger_artifact: dict[str, Any],
    selection_artifact: dict[str, Any],
    *,
    paper_governance_artifact: dict[str, Any] | None = None,
) -> None:
    selected_ids = (
        _paper_governance_selected_config_ids(paper_governance_artifact)
        if paper_governance_artifact is not None
        else _section_config_ids(selection_artifact.get("selected_configs"))
    )
    baseline_ids = _section_config_ids(selection_artifact.get("baseline_configs"))
    account_contract = ledger_artifact.get("account_contract")
    if isinstance(account_contract, dict):
        ledger_selected = account_contract.get("selected_config_ids")
        if isinstance(ledger_selected, list) and tuple(ledger_selected) != selected_ids:
            raise ValueError("paper tracking ledger selected_config_ids do not match rule selection artifact")
        ledger_baseline = account_contract.get("baseline_config_ids")
        if isinstance(ledger_baseline, list) and tuple(ledger_baseline) != baseline_ids:
            raise ValueError("paper tracking ledger baseline_config_ids do not match rule selection artifact")


def _require_field(artifact: dict[str, Any], field: str, expected: object, label: str) -> None:
    if artifact.get(field) != expected:
        raise ValueError(f"{label} {field} must be {expected}")


def _require_section_config_ids(
    artifact: dict[str, Any],
    section: str,
    expected: tuple[str, ...],
) -> None:
    actual = _section_config_ids(artifact.get(section))
    if actual != expected:
        raise ValueError(f"rule selection {section} must be {list(expected)}")


def _validate_rule_selection_sections(
    artifact: dict[str, Any],
    *,
    required_config_ids: tuple[str, ...],
) -> None:
    section_expectations = {
        "selected_configs": ("phase5_contract_candidate", "passed"),
        "baseline_configs": ("baseline_control", "baseline_control"),
        "holdout_configs": ("holdout", "passed"),
        "rejected_configs": ("rejected", "failed"),
    }
    seen: list[str] = []
    for section, (expected_role, expected_gate_status) in section_expectations.items():
        rows = artifact.get(section)
        if not isinstance(rows, list):
            raise ValueError(f"rule selection {section} must be a list")
        for row in rows:
            if not isinstance(row, dict):
                raise ValueError(f"rule selection {section} rows must be objects")
            config_id = str(row.get("config_id") or "")
            seen.append(config_id)
            if row.get("role") != expected_role:
                raise ValueError(f"rule selection {section} role must be {expected_role}")
            if row.get("gate_status") != expected_gate_status:
                raise ValueError(f"rule selection {section} gate_status must be {expected_gate_status}")
    if len(seen) != len(set(seen)):
        raise ValueError("rule selection config ids must not be duplicated across sections")
    if set(seen) != set(required_config_ids):
        raise ValueError("rule selection sections must cover every required v2 config exactly once")
    selected_ids = _section_config_ids(artifact.get("selected_configs"))
    if selected_ids and artifact.get("status") != "ready":
        raise ValueError("rule selection with selected configs must be ready")
    if not selected_ids and artifact.get("status") != "blocked":
        raise ValueError("rule selection without selected configs must be blocked")


def _section_config_ids(rows: object) -> tuple[str, ...]:
    if not isinstance(rows, list):
        return ()
    return tuple(str(row.get("config_id") or "") for row in rows if isinstance(row, dict))


def _replay_results_by_config(artifact: dict[str, Any]) -> dict[str, dict[str, Any]]:
    results = artifact.get("results")
    if not isinstance(results, list) or not results:
        raise ValueError("replay artifact must contain results")
    by_config: dict[str, dict[str, Any]] = {}
    for result in results:
        if not isinstance(result, dict):
            continue
        config_id = str(result.get("config_id") or "")
        if config_id:
            by_config[config_id] = result
    if not by_config:
        raise ValueError("replay artifact results do not contain config_id rows")
    return by_config


def _config_readouts(
    selection_rows: object,
    *,
    result_by_config: dict[str, dict[str, Any]],
    decision_sample_limit: int,
) -> list[dict[str, Any]]:
    rows = [row for row in selection_rows or [] if isinstance(row, dict)]
    output: list[dict[str, Any]] = []
    for row in rows:
        config_id = str(row.get("config_id") or "")
        replay_result = result_by_config.get(config_id) or {}
        output.append(
            {
                "config_id": config_id,
                "role": str(row.get("role") or ""),
                "selection_rank": row.get("selection_rank"),
                "gate_status": row.get("gate_status"),
                "reason": row.get("reason"),
                "summary": replay_result.get("summary") or row.get("summary") or {},
                "selection_summary": row.get("summary") or {},
                "reason_counts": replay_result.get("reason_counts") or {},
                "decision_samples": list(replay_result.get("decision_samples") or [])[:decision_sample_limit],
            }
        )
    return output


def _paper_config_readouts(selection_rows: object) -> list[dict[str, Any]]:
    rows = [row for row in selection_rows or [] if isinstance(row, dict)]
    return [
        {
            "config_id": str(row.get("config_id") or ""),
            "role": str(row.get("role") or ""),
            "selection_rank": row.get("selection_rank"),
            "gate_status": row.get("gate_status"),
            "reason": row.get("reason"),
            "summary": row.get("summary") or {},
            "selection_summary": row.get("summary") or {},
            "reason_counts": {},
            "decision_samples": [],
        }
        for row in rows
    ]


def _legacy_strategy_search_readouts(rows: list[dict[str, Any]], *, legacy_role: str) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        selection_summary = dict(item.get("selection_summary") or {})
        selection_summary["legacy_context"] = "older_strategy_search_reference_only"
        item["role"] = legacy_role
        item["gate_status"] = "legacy_reference"
        item["reason"] = "旧 strategy-search 结果只作为历史弱结果参照，不属于 H10 quiet champion 同窗候选。"
        item["selection_summary"] = selection_summary
        output.append(item)
    return output


def _paper_governance_config_readouts(artifact: dict[str, Any] | None) -> list[dict[str, Any]]:
    if artifact is None:
        return []
    rows = [row for row in artifact.get("candidate_configs") or [] if isinstance(row, dict)]
    return [
        {
            "config_id": str(row.get("config_id") or ""),
            "role": str(row.get("role") or ""),
            "selection_rank": index,
            "gate_status": "passed",
            "reason": "h10_paper_governance_future_observation_candidate",
            "summary": row.get("summary") or {},
            "selection_summary": row.get("qualification_checks") or {},
            "reason_counts": {},
            "decision_samples": [],
        }
        for index, row in enumerate(rows, start=1)
    ]


def _paper_governance_diagnostic_readouts(artifact: dict[str, Any] | None) -> list[dict[str, Any]]:
    if artifact is None:
        return []
    rows = [row for row in artifact.get("diagnostic_configs") or [] if isinstance(row, dict)]
    return [
        {
            "config_id": str(row.get("config_id") or ""),
            "role": str(row.get("role") or "diagnostic"),
            "selection_rank": index,
            "gate_status": "diagnostic_only",
            "reason": str(row.get("blocked_reason") or "diagnostic_only"),
            "summary": row.get("summary") or {},
            "selection_summary": {
                "diagnostic_only": row.get("diagnostic_only") is True,
                "paper_tracking_eligible": row.get("paper_tracking_eligible") is True,
                "target_notional": row.get("target_notional"),
                "blocked_reason": row.get("blocked_reason"),
            },
            "reason_counts": {},
            "decision_samples": [],
        }
        for index, row in enumerate(rows, start=1)
    ]


def _h10_strategy_inventory(artifact: dict[str, Any] | None, path: Path) -> dict[str, Any]:
    if artifact is None:
        return {
            "status": "missing",
            "source_path": str(path),
            "qualified_config_ids": [],
            "diagnostic_config_ids": [],
            "benchmark_config_id": None,
            "capital_shadow_config_id": None,
        }
    analysis_scope = artifact.get("analysis_scope") if isinstance(artifact.get("analysis_scope"), dict) else {}
    governance_policy = artifact.get("governance_policy") if isinstance(artifact.get("governance_policy"), dict) else {}
    source_validation = artifact.get("source_validation") if isinstance(artifact.get("source_validation"), dict) else {}
    qualification_floor = (
        governance_policy.get("qualification_floor")
        if isinstance(governance_policy.get("qualification_floor"), dict)
        else {}
    )
    candidate_rows = [row for row in artifact.get("candidate_configs") or [] if isinstance(row, dict)]
    diagnostic_rows = [row for row in artifact.get("diagnostic_configs") or [] if isinstance(row, dict)]
    return {
        "status": "ready",
        "source_path": str(path),
        "source_artifact_id": artifact.get("artifact_id"),
        "horizon_days": analysis_scope.get("horizon_days"),
        "initial_cash": analysis_scope.get("initial_cash"),
        "signal_date_from": analysis_scope.get("signal_date_from"),
        "signal_date_to": analysis_scope.get("signal_date_to"),
        "paper_tracking_start_date": analysis_scope.get("paper_tracking_start_date"),
        "benchmark_config_id": analysis_scope.get("primary_config_id"),
        "capital_shadow_config_id": analysis_scope.get("capital_shadow_config_id"),
        "qualified_config_ids": [str(row.get("config_id") or "") for row in candidate_rows],
        "diagnostic_config_ids": [str(row.get("config_id") or "") for row in diagnostic_rows],
        "rank2_support_label": (
            source_validation.get("rank_ablation", {}).get("rank2_support_label")
            if isinstance(source_validation.get("rank_ablation"), dict)
            else None
        ),
        "min_annualized_return": qualification_floor.get("min_annualized_return"),
        "must_beat_market": qualification_floor.get("must_beat_market"),
        "claim_policy": governance_policy.get("claim_policy"),
        "fixed90_policy": governance_policy.get("fixed90_policy"),
    }


def _paper_governance_projection(artifact: dict[str, Any] | None, path: Path) -> dict[str, Any]:
    if artifact is None:
        return {}
    recommendation = artifact.get("recommendation") if isinstance(artifact.get("recommendation"), dict) else {}
    ledger_overlay = (
        artifact.get("ledger_contract_overlay")
        if isinstance(artifact.get("ledger_contract_overlay"), dict)
        else {}
    )
    disposition = artifact.get("source_disposition") if isinstance(artifact.get("source_disposition"), dict) else {}
    selected_config_ids = _paper_governance_selected_config_ids(artifact)
    diagnostic_rejected_config_ids = [
        str(config_id)
        for config_id in ledger_overlay.get("diagnostic_rejected_config_ids") or []
        if isinstance(config_id, str) and config_id
    ]
    return {
        "artifact_id": artifact.get("artifact_id"),
        "path": str(path),
        "status": recommendation.get("status") or H10_PAPER_GOVERNANCE_RECOMMENDATION_STATUS,
        "recommendation_status": recommendation.get("status") or H10_PAPER_GOVERNANCE_RECOMMENDATION_STATUS,
        "paper_tracking_status": recommendation.get("paper_tracking_status")
        or H10_PAPER_GOVERNANCE_PAPER_TRACKING_STATUS,
        "claim_ceiling": artifact.get("claim_ceiling"),
        "evidence_basis": artifact.get("evidence_basis"),
        "candidate_config_ids": list(selected_config_ids),
        "selected_config_ids": list(selected_config_ids),
        "diagnostic_rejected_config_ids": diagnostic_rejected_config_ids,
        "ledger_policy": ledger_overlay.get("ledger_policy") or H10_PAPER_GOVERNANCE_LEDGER_POLICY,
        "entry_policy": ledger_overlay.get("entry_policy") or H10_PAPER_GOVERNANCE_ENTRY_POLICY,
        "record_backfill_allowed": ledger_overlay.get("record_backfill_allowed") is True,
        "current_true_forward_record_count": int(ledger_overlay.get("current_true_forward_record_count") or 0),
        "risk_flag_count": disposition.get("risk_flag_count"),
        "high_risk_flag_count": disposition.get("high_risk_flag_count"),
        "governance_disposition": disposition.get("governance_disposition"),
    }


def _paper_governance_selected_config_ids(artifact: dict[str, Any] | None) -> tuple[str, ...]:
    if artifact is None:
        return ()
    ledger_overlay = (
        artifact.get("ledger_contract_overlay")
        if isinstance(artifact.get("ledger_contract_overlay"), dict)
        else {}
    )
    selected = tuple(
        str(config_id)
        for config_id in ledger_overlay.get("selected_config_ids") or []
        if isinstance(config_id, str) and config_id
    )
    return selected or H10_QUIET_PAPER_CANDIDATE_CONFIG_IDS


def _artifact_ref(artifact: dict[str, Any], path: Path) -> dict[str, Any]:
    return {
        "path": str(path),
        "artifact_id": artifact.get("artifact_id") or artifact.get("ledger_id"),
        "artifact_family": artifact.get("artifact_family"),
        "schema_version": artifact.get("schema_version"),
        "status": artifact.get("status"),
        "claim_ceiling": artifact.get("claim_ceiling"),
        "evidence_basis": artifact.get("evidence_basis"),
    }


def _tracking_window_contract() -> dict[str, Any]:
    return {
        "start_date": SHORTPICK_V2_TRACKING_START_DATE,
        "start_policy": "v1_aligned_forward_window",
        "source_gap_policy": "record_source_gap_or_not_observed_without_shifting_start_date",
        "backfill_policy": "historical_replay_rows_must_not_be_backfilled_as_true_forward_tracking",
    }


def _account_contract(
    selection_artifact: dict[str, Any],
    *,
    paper_governance_artifact: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "initial_cash": SHORTPICK_V2_DEFAULT_INITIAL_CASH,
        "currency": "CNY",
        "board_lot_size": SHORTPICK_V2_DEFAULT_BOARD_LOT_SIZE,
        "account_profile": "new_retail_cash_account",
        "selected_config_ids": list(
            _paper_governance_selected_config_ids(paper_governance_artifact)
            if paper_governance_artifact is not None
            else _section_config_ids(selection_artifact.get("selected_configs"))
        ),
        "baseline_config_ids": list(_section_config_ids(selection_artifact.get("baseline_configs"))),
        "selection_policy": SHORTPICK_V2_RULE_SELECTION_POLICY_VERSION,
    }


def _row_contract(*, paper_governance_artifact: dict[str, Any] | None = None) -> dict[str, Any]:
    ledger_overlay = (
        paper_governance_artifact.get("ledger_contract_overlay")
        if paper_governance_artifact is not None
        and isinstance(paper_governance_artifact.get("ledger_contract_overlay"), dict)
        else {}
    )
    return {
        "allowed_signal_actions": list(SHORTPICK_V2_ALLOWED_ACTIONS),
        "forbidden_signal_actions": list(SHORTPICK_V2_FORBIDDEN_ACTIONS),
        "entry_policy": ledger_overlay.get("entry_policy")
        or "declared_entry_date_only_fallback_or_skip_no_delayed_entry",
        "ledger_policy": ledger_overlay.get("ledger_policy") or "future_true_forward_only_no_historical_backfill",
        "source_gap_policy": "record_source_gap_or_not_observed",
    }


def _records_summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    buy_count = sum(1 for record in records if str(record.get("decision_action") or "").startswith("buy_"))
    skip_count = sum(1 for record in records if record.get("decision_action") == "skip")
    source_gap_count = sum(1 for record in records if record.get("source_state") in {"source_gap", "not_observed"})
    return {
        "record_count": len(records),
        "buy_count": buy_count,
        "skip_count": skip_count,
        "source_gap_count": source_gap_count,
        "tracking_start_date": SHORTPICK_V2_TRACKING_START_DATE,
    }


def _research_labeling(*, evidence_basis: str, ui_language: str) -> dict[str, Any]:
    return {
        "claim_ceiling": SHORTPICK_V2_CLAIM_CEILING,
        "evidence_basis": evidence_basis,
        "ui_language": ui_language,
        "data_disclaimer": "纸面研究观察，不构成投资建议、生产证明或自动交易承诺。",
    }


def _bounded_sample_limit(sample_limit: int) -> int:
    return max(0, min(int(sample_limit), SHORTPICK_V2_DECISION_SAMPLE_LIMIT_MAX))


def _active_paper_config_ids() -> tuple[str, ...]:
    return (*SHORTPICK_V2_SELECTED_CONFIG_IDS, *SHORTPICK_V2_BASELINE_CONFIG_IDS)


def _ledger_active_config_ids(artifact: dict[str, Any]) -> tuple[str, ...]:
    account_contract = artifact.get("account_contract") if isinstance(artifact.get("account_contract"), dict) else {}
    selected = account_contract.get("selected_config_ids")
    baseline = account_contract.get("baseline_config_ids")
    if isinstance(selected, list) or isinstance(baseline, list):
        return tuple(
            str(config_id)
            for config_id in [*(selected or []), *(baseline or [])]
            if isinstance(config_id, str) and config_id
        )
    return _active_paper_config_ids()


def _validate_paper_tracking_active_config_ids(active_config_ids: tuple[str, ...]) -> None:
    if H10_QUIET_DIAGNOSTIC_90K_CONFIG_ID in active_config_ids:
        raise ValueError("paper tracking ledger must not activate fixed90 diagnostic config")
    allowed = {
        *SHORTPICK_V2_SELECTED_CONFIG_IDS,
        *SHORTPICK_V2_BASELINE_CONFIG_IDS,
        *SHORTPICK_V2_HOLDOUT_CONFIG_IDS,
        *SHORTPICK_V2_REJECTED_CONFIG_IDS,
        *H10_QUIET_PAPER_CANDIDATE_CONFIG_IDS,
    }
    unknown = sorted(set(active_config_ids) - allowed)
    if unknown:
        raise ValueError(f"paper tracking ledger active config_id is not governed: {unknown}")


def _all_phase6_config_ids() -> tuple[str, ...]:
    return (
        *SHORTPICK_V2_SELECTED_CONFIG_IDS,
        *SHORTPICK_V2_BASELINE_CONFIG_IDS,
        *SHORTPICK_V2_HOLDOUT_CONFIG_IDS,
        *SHORTPICK_V2_REJECTED_CONFIG_IDS,
    )


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()

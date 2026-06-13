from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

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
SHORTPICK_V2_DECISION_SAMPLE_LIMIT_MAX = 40


def build_shortpick_v2_historical_replay_read_model(
    *,
    sample_limit: int = 20,
    replay_artifact_path: str | Path | None = None,
    rule_selection_artifact_path: str | Path | None = None,
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
    replay_artifact = _read_json_artifact(replay_path, label="shortpick v2 replay")
    selection_artifact = _read_json_artifact(selection_path, label="shortpick v2 rule selection")
    _validate_replay_artifact(replay_artifact)
    _validate_rule_selection_artifact(selection_artifact)
    _validate_replay_selection_alignment(replay_artifact, selection_artifact)

    result_by_config = _replay_results_by_config(replay_artifact)
    selected_configs = _config_readouts(
        selection_artifact.get("selected_configs"),
        result_by_config=result_by_config,
        decision_sample_limit=bounded_sample_limit,
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
    data_scope = replay_artifact.get("data_scope") if isinstance(replay_artifact.get("data_scope"), dict) else {}
    return {
        "generated_at": _now_iso(),
        "status": str(selection_artifact.get("status") or "blocked"),
        "claim_ceiling": SHORTPICK_V2_CLAIM_CEILING,
        "evidence_basis": SHORTPICK_V2_SELECTION_EVIDENCE_BASIS,
        "ui_language": "试验田v2历史回放仅展示预计算账户路径研究观察。",
        "data_disclaimer": "历史回放读取固定 artifact，不构成投资建议，不代表生产交易能力。",
        "source_artifacts": {
            "replay": _artifact_ref(replay_artifact, replay_path),
            "rule_selection": _artifact_ref(selection_artifact, selection_path),
        },
        "data_scope": data_scope,
        "selection_policy": selection_artifact.get("selection_policy") or {},
        "summary": {
            "selected_config_count": len(selected_configs),
            "baseline_config_count": len(baseline_configs),
            "holdout_config_count": len(holdout_configs),
            "rejected_config_count": len(rejected_configs),
            "signal_day_count": data_scope.get("signal_day_count"),
            "trade_day_count": data_scope.get("trade_day_count"),
            "coverage_status": data_scope.get("coverage_status"),
            "decision_sample_limit": bounded_sample_limit,
        },
        "selected_configs": selected_configs,
        "baseline_configs": baseline_configs,
        "holdout_configs": holdout_configs,
        "rejected_configs": rejected_configs,
        "leakage_audit": {
            "status": "passed",
            "replay": replay_artifact.get("leakage_audit") or {},
            "rule_selection": selection_artifact.get("leakage_audit") or {},
            "read_model_policy": "read_only_precomputed_artifacts_no_dynamic_replay",
        },
        "research_labeling": _research_labeling(
            evidence_basis=SHORTPICK_V2_SELECTION_EVIDENCE_BASIS,
            ui_language="试验田v2历史回放仅展示预计算账户路径研究观察。",
        ),
        "event_refs": [
            "shortpick_v2.phase6.backend_read_model.historical_replay",
            str(replay_artifact.get("artifact_id") or ""),
            str(selection_artifact.get("artifact_id") or ""),
        ],
    }


def build_shortpick_v2_paper_tracking_read_model(
    *,
    include_records: bool = True,
    rule_selection_artifact_path: str | Path | None = None,
    ledger_artifact_path: str | Path | None = None,
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
    if ledger_path.exists():
        ledger_artifact = _read_json_artifact(ledger_path, label="shortpick v2 paper tracking ledger")
        _validate_paper_tracking_ledger_artifact(ledger_artifact)
        _validate_paper_tracking_selection_alignment(ledger_artifact, selection_artifact)
        return _paper_tracking_ledger_read_model(
            ledger_artifact,
            ledger_path=ledger_path,
            selection_artifact=selection_artifact,
            selection_path=selection_path,
            include_records=include_records,
        )
    return _contract_ready_paper_tracking_read_model(
        selection_artifact=selection_artifact,
        selection_path=selection_path,
        ledger_path=ledger_path,
        include_records=include_records,
    )


def _contract_ready_paper_tracking_read_model(
    *,
    selection_artifact: dict[str, Any],
    selection_path: Path,
    ledger_path: Path,
    include_records: bool,
) -> dict[str, Any]:
    selected_configs = _paper_config_readouts(selection_artifact.get("selected_configs"))
    baseline_configs = _paper_config_readouts(selection_artifact.get("baseline_configs"))
    is_blocked = not selected_configs
    payload: dict[str, Any] = {
        "generated_at": _now_iso(),
        "status": "blocked" if is_blocked else "contract_ready",
        "current_status": "blocked" if is_blocked else "contract_ready",
        "current_message": (
            "No v2 config currently qualifies under market-outperformance and annualized-return gates."
            if is_blocked
            else "V2 paper tracking writer has not produced true-forward rows yet."
        ),
        "claim_ceiling": SHORTPICK_V2_CLAIM_CEILING,
        "evidence_basis": SHORTPICK_V2_PAPER_EVIDENCE_BASIS,
        "ui_language": "试验田v2纸面追踪仅展示账户路径纸面研究证据。",
        "data_disclaimer": (
            "当前为空投影：没有通过大盘超额收益和 30% 年化门槛的 v2 候选配置。"
            if is_blocked
            else "当前为空投影：已固定候选配置，但没有真实前向 v2 paper ledger rows。"
        ),
        "source_contract_ref": SHORTPICK_V2_PAPER_CONTRACT_REF,
        "source_artifacts": {
            "rule_selection": _artifact_ref(selection_artifact, selection_path),
            "paper_ledger": {
                "path": str(ledger_path),
                "status": "missing",
                "artifact_family": SHORTPICK_V2_PAPER_TRACKING_LEDGER_FAMILY,
            },
        },
        "tracking_window": _tracking_window_contract(),
        "account_contract": _account_contract(selection_artifact),
        "row_contract": _row_contract(),
        "selected_configs": selected_configs,
        "baseline_configs": baseline_configs,
        "summary": {
            "record_count": 0,
            "buy_count": 0,
            "skip_count": 0,
            "source_gap_count": 0,
            "selected_config_count": len(selected_configs),
            "baseline_config_count": len(baseline_configs),
            "tracking_start_date": SHORTPICK_V2_TRACKING_START_DATE,
        },
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
    if include_records:
        payload["records"] = []
    return payload


def _paper_tracking_ledger_read_model(
    ledger_artifact: dict[str, Any],
    *,
    ledger_path: Path,
    selection_artifact: dict[str, Any],
    selection_path: Path,
    include_records: bool,
) -> dict[str, Any]:
    records = [record for record in ledger_artifact.get("records") or [] if isinstance(record, dict)]
    selected_configs = _paper_config_readouts(selection_artifact.get("selected_configs"))
    baseline_configs = _paper_config_readouts(selection_artifact.get("baseline_configs"))
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
        },
        "tracking_window": ledger_artifact.get("tracking_window") or _tracking_window_contract(),
        "account_contract": ledger_artifact.get("account_contract") or _account_contract(selection_artifact),
        "row_contract": ledger_artifact.get("row_contract") or _row_contract(),
        "selected_configs": selected_configs,
        "baseline_configs": baseline_configs,
        "summary": ledger_artifact.get("summary") or _records_summary(records),
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
    if include_records:
        payload["records"] = records
    return payload


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
    active_config_ids = _ledger_active_config_ids(artifact)
    for record in records:
        if not isinstance(record, dict):
            raise ValueError("paper tracking ledger record must be an object")
        _validate_paper_tracking_record(record, active_config_ids=active_config_ids)


def _validate_paper_tracking_record(record: dict[str, Any], *, active_config_ids: tuple[str, ...]) -> None:
    config_id = str(record.get("config_id") or "")
    if config_id not in active_config_ids:
        raise ValueError(f"paper tracking record config_id is not active for Phase 6: {config_id}")
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
) -> None:
    selected_ids = _section_config_ids(selection_artifact.get("selected_configs"))
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


def _account_contract(selection_artifact: dict[str, Any]) -> dict[str, Any]:
    return {
        "initial_cash": SHORTPICK_V2_DEFAULT_INITIAL_CASH,
        "currency": "CNY",
        "board_lot_size": SHORTPICK_V2_DEFAULT_BOARD_LOT_SIZE,
        "selected_config_ids": list(_section_config_ids(selection_artifact.get("selected_configs"))),
        "baseline_config_ids": list(_section_config_ids(selection_artifact.get("baseline_configs"))),
        "selection_policy": SHORTPICK_V2_RULE_SELECTION_POLICY_VERSION,
    }


def _row_contract() -> dict[str, Any]:
    return {
        "allowed_signal_actions": list(SHORTPICK_V2_ALLOWED_ACTIONS),
        "forbidden_signal_actions": list(SHORTPICK_V2_FORBIDDEN_ACTIONS),
        "entry_policy": "no_delayed_entry_choose_declared_day_fallback_or_skip",
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


def _all_phase6_config_ids() -> tuple[str, ...]:
    return (
        *SHORTPICK_V2_SELECTED_CONFIG_IDS,
        *SHORTPICK_V2_BASELINE_CONFIG_IDS,
        *SHORTPICK_V2_HOLDOUT_CONFIG_IDS,
        *SHORTPICK_V2_REJECTED_CONFIG_IDS,
    )


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from ashare_evidence.research_artifact_store import (
    artifact_path,
    write_shortpick_combined_ledger_backfill_artifact_record,
)
from ashare_evidence.shortpick_strategy_governance import (
    build_shortpick_combined_ledger_retrospective_backfill,
    filter_shortpick_combined_ledger_rows_by_evidence_basis,
)
from ashare_evidence.shortpick_strategy_replay_runner import FILTER_RESELECT_SELECTION_POLICY

RETROSPECTIVE_REPLAY_ARTIFACT_TYPE = "shortpick_retrospective_forward_replay"


def run_shortpick_combined_ledger_backfill_artifact(
    replay_artifacts: list[dict[str, Any]],
    *,
    true_forward_rows: list[dict[str, Any]] | None = None,
    generated_at: str | None = None,
    output_path: str | Path | None = None,
) -> dict[str, Any]:
    """Materialize replay artifacts into a labeled combined-ledger artifact.

    The writer persists a JSON artifact only. It does not write database or paper
    tracking rows; a later runtime integration can load the artifact explicitly.
    """

    normalized_true_forward_rows = _normalize_true_forward_rows(true_forward_rows or [], generated_at=generated_at)
    retrospective_rows: list[dict[str, Any]] = []
    blocked_sources: list[dict[str, Any]] = []
    blocked_rows: list[dict[str, Any]] = []
    source_refs: list[str] = []

    for index, replay in enumerate(replay_artifacts):
        if not isinstance(replay, dict):
            blocked_sources.append({"source_index": index, "blocker": "replay_artifact_not_object"})
            continue
        source_ref = _source_ref(replay, index=index)
        source_refs.append(source_ref)
        if str(replay.get("evidence_basis") or "") != "retrospective_forward_replay":
            blocked_sources.append(
                {
                    "source_index": index,
                    "source_ref": source_ref,
                    "blocker": "replay_artifact_has_unsupported_evidence_basis",
                    "evidence_basis": replay.get("evidence_basis"),
                }
            )
            continue
        if str(replay.get("status") or "") != "ready":
            blocked_sources.append(
                {
                    "source_index": index,
                    "source_ref": source_ref,
                    "blocker": "replay_artifact_not_ready",
                    "status": replay.get("status"),
                }
            )
            continue
        prepared = build_shortpick_combined_ledger_retrospective_backfill(
            [dict(row) for row in replay.get("rows") or [] if isinstance(row, dict)],
            replay_request=dict(replay.get("request") or {}),
            generated_at=generated_at,
            source_artifact_ref=source_ref,
        )
        retrospective_rows.extend(prepared.get("retrospective_rows") or [])
        blocked_rows.extend(
            {
                **dict(row),
                "source_ref": source_ref,
            }
            for row in prepared.get("blocked_rows") or []
            if isinstance(row, dict)
        )

    combined_rows = _dedupe_rows([*normalized_true_forward_rows, *retrospective_rows], blocked_rows=blocked_rows)
    true_forward_filter = filter_shortpick_combined_ledger_rows_by_evidence_basis(
        combined_rows,
        evidence_basis="true_forward_tracking",
    )
    retrospective_filter = filter_shortpick_combined_ledger_rows_by_evidence_basis(
        combined_rows,
        evidence_basis="retrospective_forward_replay",
    )
    payload = {
        "artifact_id": _combined_ledger_artifact_id(source_refs, combined_rows),
        "artifact_type": "shortpick_combined_ledger_backfill",
        "version": "shortpick-combined-ledger-backfill-v1",
        "status": "ready" if retrospective_filter["selected_count"] else "blocked",
        "ledger_mode": "combined_paper_tracking_ledger",
        "write_policy": "artifact_only_no_database_or_paper_tracking_write",
        "paper_tracking_write_policy": "combined_ledger_artifact_only_no_database_write",
        "headline_metric_filter_policy": "true_forward_queries_must_filter_evidence_basis_true_forward_tracking",
        "evidence_basis_policy": "mandatory_non_null_basis_with_true_forward_default_filters",
        "generated_at": generated_at,
        "source_replay_artifact_count": len(replay_artifacts),
        "selection_policy": FILTER_RESELECT_SELECTION_POLICY,
        "ready_replay_artifact_count": len(replay_artifacts) - len(blocked_sources),
        "blocked_source_count": len(blocked_sources),
        "true_forward_count": true_forward_filter["selected_count"],
        "retrospective_count": retrospective_filter["selected_count"],
        "combined_row_count": len(combined_rows),
        "blocked_row_count": len(blocked_rows),
        "source_refs": source_refs,
        "combined_rows": combined_rows,
        "true_forward_rows": true_forward_filter["rows"],
        "retrospective_rows": retrospective_filter["rows"],
        "blocked_sources": blocked_sources,
        "blocked_rows": blocked_rows,
    }
    if output_path is not None:
        path = write_shortpick_combined_ledger_backfill_artifact(payload, output_path=output_path)
        payload = {**payload, "artifact": {"path": str(path)}}
    return payload


def discover_shortpick_retrospective_forward_replay_artifacts(
    *,
    root: str | Path,
) -> dict[str, Any]:
    artifacts: list[dict[str, Any]] = []
    ignored: list[dict[str, str]] = []
    seen_artifact_ids: set[str] = set()
    source_dirs = _retrospective_replay_artifact_dirs(root=Path(root))

    for directory in source_dirs:
        if not directory.exists():
            continue
        for target in sorted(directory.glob("*.json")):
            try:
                payload = _load_json_object(target)
            except (OSError, ValueError, json.JSONDecodeError) as exc:
                ignored.append({"path": str(target), "reason": f"unreadable_json:{type(exc).__name__}"})
                continue
            if not _is_ready_retrospective_replay_artifact(payload):
                ignored.append({"path": str(target), "reason": "not_ready_retrospective_forward_replay_artifact"})
                continue
            artifact_id = str(payload.get("artifact_id") or "")
            if artifact_id in seen_artifact_ids:
                ignored.append({"path": str(target), "reason": "duplicate_artifact_id"})
                continue
            seen_artifact_ids.add(artifact_id)
            artifact_payload = dict(payload)
            artifact_payload["artifact"] = {**dict(artifact_payload.get("artifact") or {}), "path": str(target)}
            artifacts.append(artifact_payload)

    return {
        "status": "ready",
        "source": "shortpick_retrospective_forward_replay_artifact_discovery",
        "source_dirs": [str(path) for path in source_dirs],
        "artifact_count": len(artifacts),
        "ignored_count": len(ignored),
        "ignored": ignored,
        "artifacts": artifacts,
    }


def materialize_shortpick_combined_ledger_from_artifact_root(
    *,
    root: str | Path,
    true_forward_rows: list[dict[str, Any]] | None = None,
    generated_at: str | None = None,
    output_path: str | Path | None = None,
    write_blocked: bool = False,
) -> dict[str, Any]:
    root_path = Path(root)
    discovery = discover_shortpick_retrospective_forward_replay_artifacts(root=root_path)
    payload = run_shortpick_combined_ledger_backfill_artifact(
        [dict(item) for item in discovery["artifacts"] if isinstance(item, dict)],
        true_forward_rows=true_forward_rows,
        generated_at=generated_at,
    )
    payload = {
        **payload,
        "source_discovery": {
            "source": discovery["source"],
            "source_dirs": discovery["source_dirs"],
            "artifact_count": discovery["artifact_count"],
            "ignored_count": discovery["ignored_count"],
            "ignored": discovery["ignored"],
        },
    }
    should_write = payload.get("status") == "ready" or write_blocked
    if output_path is not None and should_write:
        path = write_shortpick_combined_ledger_backfill_artifact(payload, output_path=output_path)
        return {**payload, "artifact": {"path": str(path)}}
    if output_path is None and should_write:
        path = write_shortpick_combined_ledger_backfill_artifact_record(payload, root=root_path)
        return {**payload, "artifact": {"path": str(path)}}
    return payload


def write_shortpick_combined_ledger_backfill_artifact(payload: dict[str, Any], *, output_path: str | Path) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    return path


def load_shortpick_combined_ledger_inputs(
    replay_artifact_paths: list[str | Path],
    *,
    true_forward_path: str | Path | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    replay_artifacts = [_load_json_object(path) for path in replay_artifact_paths]
    true_forward_rows = _load_true_forward_rows(true_forward_path) if true_forward_path is not None else []
    return replay_artifacts, true_forward_rows


def _normalize_true_forward_rows(rows: list[dict[str, Any]], *, generated_at: str | None) -> list[dict[str, Any]]:
    if not rows:
        return []
    prepared = build_shortpick_combined_ledger_retrospective_backfill(
        [],
        true_forward_rows=rows,
        generated_at=generated_at,
    )
    return [dict(row) for row in prepared.get("true_forward_rows") or [] if isinstance(row, dict)]


def _dedupe_rows(rows: list[dict[str, Any]], *, blocked_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    selected: dict[str, dict[str, Any]] = {}
    for index, row in enumerate(rows):
        row_id = str(row.get("combined_ledger_row_id") or "")
        if not row_id:
            blocked_rows.append({"row_index": index, "blocker": "missing_combined_ledger_row_id"})
            continue
        if row_id in selected:
            blocked_rows.append({"row_index": index, "combined_ledger_row_id": row_id, "blocker": "duplicate_combined_ledger_row_id"})
            continue
        selected[row_id] = row
    return list(selected.values())


def _load_json_object(path: str | Path) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _load_true_forward_rows(path: str | Path) -> list[dict[str, Any]]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return [dict(item) for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        rows = payload.get("rows")
        if rows is None:
            rows = payload.get("items")
        if isinstance(rows, list):
            return [dict(item) for item in rows if isinstance(item, dict)]
    raise ValueError(f"{path} must contain a JSON list or an object with rows/items")


def _source_ref(replay: dict[str, Any], *, index: int) -> str:
    artifact = replay.get("artifact") if isinstance(replay.get("artifact"), dict) else {}
    return str(artifact.get("path") or replay.get("artifact_id") or f"replay-artifact:{index}")


def _retrospective_replay_artifact_dirs(*, root: Path) -> tuple[Path, ...]:
    standard_dir = artifact_path(RETROSPECTIVE_REPLAY_ARTIFACT_TYPE, "__index__", root=root).parent
    legacy_replays_dir = root / "replays"
    return tuple(dict.fromkeys((standard_dir, legacy_replays_dir)))


def _is_ready_retrospective_replay_artifact(payload: dict[str, Any]) -> bool:
    rows = payload.get("rows")
    request = payload.get("request")
    return bool(
        payload.get("status") == "ready"
        and payload.get("artifact_type") == RETROSPECTIVE_REPLAY_ARTIFACT_TYPE
        and payload.get("artifact_id")
        and payload.get("evidence_basis") == "retrospective_forward_replay"
        and payload.get("retrospective") is True
        and payload.get("selection_policy") == FILTER_RESELECT_SELECTION_POLICY
        and payload.get("paper_tracking_write_policy") == "forbidden"
        and isinstance(request, dict)
        and request.get("control_group_id")
        and request.get("rule_signature")
        and request.get("rule_defined_at")
        and isinstance(rows, list)
        and rows
    )


def _combined_ledger_artifact_id(source_refs: list[str], rows: list[dict[str, Any]]) -> str:
    encoded = json.dumps(
        {
            "source_refs": source_refs,
            "row_ids": [row.get("combined_ledger_row_id") for row in rows],
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    return "shortpick-combined-ledger-backfill:" + hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:16]

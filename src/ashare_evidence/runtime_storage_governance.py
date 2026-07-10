from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ashare_evidence.model_candidate_runner import _load_artifact_metadata_without_rows

RUNTIME_STORAGE_GOVERNANCE_SCHEMA_VERSION = "runtime_storage_governance.v1"
RUNTIME_STORAGE_ARCHIVE_MANIFEST_VERSION = "runtime_storage_archive_manifest.v1"


def load_runtime_storage_policy(path: str | Path) -> dict[str, Any]:
    policy_path = Path(path)
    payload = json.loads(policy_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("runtime storage policy must be a JSON object")
    if payload.get("schema_version") != RUNTIME_STORAGE_GOVERNANCE_SCHEMA_VERSION:
        raise ValueError(f"unsupported runtime storage policy schema: {payload.get('schema_version')!r}")
    return payload


def audit_runtime_storage(
    *,
    artifact_root: str | Path,
    policy: dict[str, Any],
) -> dict[str, Any]:
    root = Path(artifact_root).resolve()
    research_root = root / "research_validation"
    blocking_gate_ids: list[str] = []
    if not research_root.is_dir():
        blocking_gate_ids.append("runtime_storage:research_root_missing")

    pinned_by_path = {
        _normalized_relative_path(item["relative_path"]): item for item in policy.get("pinned_artifacts") or []
    }
    archive_folders = {
        _normalized_relative_path(path).split("/", 1)[-1] for path in policy.get("archive_unpinned_folders") or []
    }
    all_files = sorted(path for path in research_root.rglob("*") if path.is_file()) if research_root.exists() else []
    pinned: list[dict[str, Any]] = []
    archive_candidates: list[dict[str, Any]] = []
    compact_evidence: list[dict[str, Any]] = []

    seen_paths: set[str] = set()
    for path in all_files:
        relative = path.relative_to(root).as_posix()
        seen_paths.add(relative)
        pin = pinned_by_path.get(relative)
        if pin is not None:
            pinned.append(_file_readout(path, root=root, role=str(pin.get("role") or "pinned_reusable")))
            expected_id = str(pin.get("artifact_id") or "")
            if expected_id and expected_id not in path.name:
                blocking_gate_ids.append("runtime_storage:pinned_artifact_id_path_mismatch")
            continue
        folder = path.relative_to(research_root).parts[0]
        if folder in archive_folders:
            archive_candidates.append(_file_readout(path, root=root, role="archive_unpinned_derived_payload"))
        else:
            compact_evidence.append(_file_readout(path, root=root, role="compact_research_evidence"))

    for relative, pin in pinned_by_path.items():
        if relative not in seen_paths and bool(pin.get("required", True)):
            blocking_gate_ids.append("runtime_storage:required_pinned_artifact_missing")

    for item in policy.get("required_files") or []:
        path = root / _normalized_relative_path(item["relative_path"])
        if not path.is_file():
            blocking_gate_ids.append("runtime_storage:required_lineage_file_missing")

    lineage_readout = _audit_canonical_feature_lineage(root=root, policy=policy)
    blocking_gate_ids.extend(lineage_readout["blocking_gate_ids"])

    pinned_bytes = sum(int(item["size_bytes"]) for item in pinned)
    archive_candidate_bytes = sum(int(item["size_bytes"]) for item in archive_candidates)
    compact_evidence_bytes = sum(int(item["size_bytes"]) for item in compact_evidence)
    online_bytes = pinned_bytes + archive_candidate_bytes + compact_evidence_bytes
    max_online_bytes = int(policy.get("max_online_research_bytes") or 0)
    max_compact_bytes = int(policy.get("max_compact_evidence_bytes") or 0)
    if archive_candidates:
        blocking_gate_ids.append("runtime_storage:archive_candidates_present_online")
    if max_online_bytes and online_bytes > max_online_bytes:
        blocking_gate_ids.append("runtime_storage:online_research_size_exceeded")
    if max_compact_bytes and compact_evidence_bytes > max_compact_bytes:
        blocking_gate_ids.append("runtime_storage:compact_evidence_size_exceeded")

    blocking_gate_ids = sorted(set(blocking_gate_ids))
    return {
        "artifact_type": "runtime_storage_governance_audit",
        "schema_version": RUNTIME_STORAGE_GOVERNANCE_SCHEMA_VERSION,
        "generated_at": datetime.now(UTC).isoformat(),
        "gate_status": "passed" if not blocking_gate_ids else "blocked",
        "blocking_gate_ids": blocking_gate_ids,
        "artifact_root": str(root),
        "research_root": str(research_root),
        "limits": {
            "max_online_research_bytes": max_online_bytes,
            "max_compact_evidence_bytes": max_compact_bytes,
        },
        "online": {
            "total_bytes": online_bytes,
            "pinned_bytes": pinned_bytes,
            "compact_evidence_bytes": compact_evidence_bytes,
            "archive_candidate_bytes": archive_candidate_bytes,
            "pinned_file_count": len(pinned),
            "compact_evidence_file_count": len(compact_evidence),
            "archive_candidate_file_count": len(archive_candidates),
        },
        "pinned_artifacts": pinned,
        "archive_candidates": archive_candidates,
        "lineage": lineage_readout,
    }


def archive_runtime_storage_candidates(
    *,
    artifact_root: str | Path,
    policy: dict[str, Any],
    archive_root: str | Path,
    apply: bool = False,
    compression_level: int = 1,
    zstd_binary: str = "zstd",
) -> dict[str, Any]:
    if compression_level < 1 or compression_level > 19:
        raise ValueError("compression_level must be between 1 and 19")
    audit = audit_runtime_storage(artifact_root=artifact_root, policy=policy)
    non_cleanup_blockers = [
        gate_id
        for gate_id in audit["blocking_gate_ids"]
        if gate_id
        not in {
            "runtime_storage:archive_candidates_present_online",
            "runtime_storage:online_research_size_exceeded",
        }
    ]
    if non_cleanup_blockers:
        raise ValueError("runtime storage archive blocked by policy violations: " + ", ".join(non_cleanup_blockers))

    root = Path(artifact_root).resolve()
    destination_root = Path(archive_root).resolve()
    candidates = [root / item["relative_path"] for item in audit["archive_candidates"]]
    result: dict[str, Any] = {
        "artifact_type": "runtime_storage_archive_run",
        "schema_version": RUNTIME_STORAGE_ARCHIVE_MANIFEST_VERSION,
        "generated_at": datetime.now(UTC).isoformat(),
        "apply": apply,
        "artifact_root": str(root),
        "archive_root": str(destination_root),
        "compression": {"format": "zstd", "level": compression_level, "threads": 1},
        "planned_file_count": len(candidates),
        "planned_source_bytes": sum(path.stat().st_size for path in candidates),
        "archived_files": [],
    }
    if not apply:
        result["planned_files"] = [str(path.relative_to(root)) for path in candidates]
        return result

    zstd_path = shutil.which(zstd_binary)
    if zstd_path is None:
        raise FileNotFoundError(f"zstd binary not found: {zstd_binary}")
    destination_root.mkdir(parents=True, exist_ok=True)
    manifest_path = destination_root / "archive-manifest.json"
    for source in candidates:
        archived = archive_verified_file_with_zstd(
            source=source,
            source_root=root,
            archive_root=destination_root,
            compression_level=compression_level,
            zstd_binary=zstd_path,
        )
        result["archived_files"].append(archived)
        _write_json_atomic(manifest_path, result)
    result["completed_at"] = datetime.now(UTC).isoformat()
    result["archived_file_count"] = len(result["archived_files"])
    result["archived_source_bytes"] = sum(int(item["source_size_bytes"]) for item in result["archived_files"])
    result["archive_bytes"] = sum(int(item["archive_size_bytes"]) for item in result["archived_files"])
    result["post_archive_audit"] = audit_runtime_storage(artifact_root=root, policy=policy)
    _write_json_atomic(manifest_path, result)
    return result


def archive_verified_file_with_zstd(
    *,
    source: str | Path,
    source_root: str | Path,
    archive_root: str | Path,
    compression_level: int = 1,
    zstd_binary: str = "zstd",
) -> dict[str, Any]:
    if compression_level < 1 or compression_level > 19:
        raise ValueError("compression_level must be between 1 and 19")
    zstd_path = shutil.which(zstd_binary)
    if zstd_path is None:
        raise FileNotFoundError(f"zstd binary not found: {zstd_binary}")
    source_path = Path(source).resolve()
    source_root_path = Path(source_root).resolve()
    try:
        source_path.relative_to(source_root_path)
    except ValueError as exc:
        raise ValueError(f"source must be contained by source_root: {source_path}") from exc
    return _archive_file_with_zstd(
        source=source_path,
        source_root=source_root_path,
        archive_root=Path(archive_root).resolve(),
        compression_level=compression_level,
        zstd_binary=zstd_path,
    )


def _audit_canonical_feature_lineage(*, root: Path, policy: dict[str, Any]) -> dict[str, Any]:
    contract = policy.get("canonical_feature_lineage") or {}
    if not contract:
        return {"status": "not_configured", "blocking_gate_ids": []}
    feature_path = root / _normalized_relative_path(contract["feature_matrix_relative_path"])
    blockers: list[str] = []
    if not feature_path.is_file():
        return {
            "status": "blocked",
            "blocking_gate_ids": ["runtime_storage:canonical_feature_matrix_missing"],
        }
    metadata = _load_artifact_metadata_without_rows(feature_path)
    expected = {
        "artifact_id": contract.get("artifact_id"),
        "source_input_snapshot_id": contract.get("source_input_snapshot_id"),
        "source_universe_date_matrix_id": contract.get("logical_universe_reference_id"),
        "row_content_digest": contract.get("row_content_digest"),
    }
    mismatches = {
        key: {"expected": value, "actual": metadata.get(key)}
        for key, value in expected.items()
        if value is not None and metadata.get(key) != value
    }
    if mismatches:
        blockers.append("runtime_storage:canonical_feature_lineage_mismatch")
    if contract.get("universe_reference_materialization") != "logical_only_not_materialized_by_streaming_rebuild":
        blockers.append("runtime_storage:universe_materialization_contract_missing")
    if metadata.get("code_version") == "unresolved_local_checkout" and not contract.get(
        "historical_code_version_unresolved"
    ):
        blockers.append("runtime_storage:unresolved_code_version_not_acknowledged")
    return {
        "status": "acknowledged_partial_reproducibility" if not blockers else "blocked",
        "blocking_gate_ids": blockers,
        "feature_matrix_path": str(feature_path),
        "metadata": metadata,
        "contract": contract,
        "mismatches": mismatches,
    }


def _archive_file_with_zstd(
    *,
    source: Path,
    source_root: Path,
    archive_root: Path,
    compression_level: int,
    zstd_binary: str,
) -> dict[str, Any]:
    relative = source.relative_to(source_root)
    destination = archive_root / Path(f"{relative.as_posix()}.zst")
    metadata_path = destination.with_suffix(destination.suffix + ".metadata.json")
    destination.parent.mkdir(parents=True, exist_ok=True)
    source_size = source.stat().st_size
    source_mtime = source.stat().st_mtime
    source_sha256 = _sha256_file(source)

    if destination.exists() and metadata_path.exists():
        archived_metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        if archived_metadata.get("source_sha256") != source_sha256:
            raise ValueError(f"existing archive digest does not match source: {destination}")
    else:
        temp_destination = destination.with_suffix(destination.suffix + ".tmp")
        temp_destination.unlink(missing_ok=True)
        subprocess.run(
            [
                zstd_binary,
                "--threads=1",
                f"-{compression_level}",
                "--no-progress",
                "--force",
                str(source),
                "-o",
                str(temp_destination),
            ],
            check=True,
        )
        subprocess.run([zstd_binary, "--test", "--no-progress", str(temp_destination)], check=True)
        os.replace(temp_destination, destination)
        os.utime(destination, (source_mtime, source_mtime))
        _write_json_atomic(
            metadata_path,
            {
                "schema_version": "runtime_storage_archived_file.v1",
                "source_relative_path": relative.as_posix(),
                "source_size_bytes": source_size,
                "source_mtime": source_mtime,
                "source_sha256": source_sha256,
                "archive_path": str(destination),
                "archive_size_bytes": destination.stat().st_size,
                "compression": {"format": "zstd", "level": compression_level, "threads": 1},
            },
        )
    subprocess.run([zstd_binary, "--test", "--no-progress", str(destination)], check=True)
    source.unlink()
    return {
        "source_relative_path": relative.as_posix(),
        "source_size_bytes": source_size,
        "source_sha256": source_sha256,
        "archive_path": str(destination),
        "archive_size_bytes": destination.stat().st_size,
        "metadata_path": str(metadata_path),
    }


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(4 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _file_readout(path: Path, *, root: Path, role: str) -> dict[str, Any]:
    return {
        "relative_path": path.relative_to(root).as_posix(),
        "size_bytes": path.stat().st_size,
        "role": role,
    }


def _normalized_relative_path(value: str) -> str:
    path = Path(str(value))
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"runtime storage policy path must be relative and contained: {value!r}")
    return path.as_posix().lstrip("./")


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temp, path)

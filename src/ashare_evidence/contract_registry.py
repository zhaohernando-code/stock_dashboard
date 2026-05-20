from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

DEFAULT_REGISTRY_PATH = Path("docs/contracts/registry/autonomous_flow_registry.v1.json")

_CODE_SPAN_RE = re.compile(r"`([^`\n]+)`")
_EVENT_ID_RE = re.compile(r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+\.v\d+$")
_INTERFACE_ID_RE = re.compile(r"^iface\.[a-z0-9-]+\.[a-z0-9-]+\.v\d+$")
_ARTIFACT_PREFIXES = (
    "phase5_",
    "rolling_",
    "validation_",
    "portfolio_",
    "replay_",
    "frontend_",
    "manual_",
    "shortpick_",
    "autonomous_",
    "runtime_",
    "recommendation_",
    "artifact_",
)
_PROPOSED_REGISTERED_CONTEXT = (
    "registered dependency",
    "registered dependencies",
    "registered id",
    "registered ids",
    "已注册依赖",
    "正式依赖",
)
_NEGATED_CONTEXT = ("不得", "不能", "禁止", "不允许", "not ", "cannot", "must not")
_DEPRECATED_CONTEXT = (
    "deprecated",
    "replacement",
    "替代",
    "旧写法",
    "迁移检查",
    "不允许",
    "不得",
    "禁止",
)
_FIELD_NAME_TOKENS = {
    "artifact_family",
    "artifact_families",
    "recommendation_key",
    "validation_mode",
    "manual_llm_layer",
    "source_artifact_refs",
    "source_refs",
}
_LOCK_DOMAIN_TOKENS = {
    "artifact_data",
    "runtime_publish",
    "autonomous_flow",
}


@dataclass(frozen=True)
class RegistryIssue:
    code: str
    message: str
    path: str | None = None
    line: int | None = None
    token: str | None = None
    replacement: str | None = None


def load_registry(path: str | Path = DEFAULT_REGISTRY_PATH) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def validate_registry_structure(registry: dict[str, Any]) -> list[RegistryIssue]:
    issues: list[RegistryIssue] = []
    required_top_level = (
        "registry_version",
        "generated_from",
        "events",
        "artifact_families",
        "interfaces",
        "deprecated_ids",
        "maturity_domains",
        "claim_ceiling_levels",
    )
    for key in required_top_level:
        if key not in registry:
            issues.append(RegistryIssue("registry_missing_key", f"registry missing top-level key: {key}", token=key))

    _validate_items(
        registry,
        issues,
        section="events",
        required=("id", "status", "provider", "consumers", "min_payload_fields", "maturity"),
    )
    _validate_items(
        registry,
        issues,
        section="artifact_families",
        required=("id", "status", "schema_ref", "provider", "consumers", "maturity"),
    )
    _validate_items(
        registry,
        issues,
        section="interfaces",
        required=("id", "status", "provider", "consumer", "contract_objects", "maturity"),
    )
    _validate_items(registry, issues, section="deprecated_ids", required=("id", "replacement", "status"))
    _validate_items(registry, issues, section="maturity_domains", required=("id", "status", "maturity"))
    _validate_items(registry, issues, section="claim_ceiling_levels", required=("id", "status", "rank"))

    registered_ids = _registered_ids(registry)
    for item in registry.get("deprecated_ids") or []:
        if not isinstance(item, dict):
            continue
        replacement = item.get("replacement")
        if replacement not in registered_ids:
            issues.append(
                RegistryIssue(
                    "deprecated_replacement_unregistered",
                    f"deprecated replacement is not registered: {replacement}",
                    token=str(item.get("id")),
                    replacement=str(replacement),
                )
            )
    return issues


def check_contract_registry(
    *,
    registry_path: str | Path = DEFAULT_REGISTRY_PATH,
    docs: list[str | Path],
    fail_on_unregistered: bool = False,
    fail_on_deprecated: bool = False,
) -> dict[str, Any]:
    registry = load_registry(registry_path)
    registry_issues = validate_registry_structure(registry)
    doc_paths = _expand_doc_paths(docs)
    scan_issues = _scan_documents(registry, doc_paths)

    fatal_codes = {"registry_missing_key", "registry_item_missing_key", "registry_section_invalid"}
    if fail_on_unregistered:
        fatal_codes.add("unregistered_id")
    if fail_on_deprecated:
        fatal_codes.add("deprecated_id")
    fatal_codes.add("proposed_registered_dependency")
    status = "fail" if any(issue.code in fatal_codes for issue in [*registry_issues, *scan_issues]) else "pass"

    all_issues = [*registry_issues, *scan_issues]
    return {
        "status": status,
        "registry_path": str(registry_path),
        "doc_count": len(doc_paths),
        "issue_count": len(all_issues),
        "issues": [asdict(issue) for issue in all_issues],
        "registered_id_count": len(_registered_ids(registry)),
        "deprecated_id_count": len(_deprecated_ids(registry)),
    }


def _validate_items(
    registry: dict[str, Any],
    issues: list[RegistryIssue],
    *,
    section: str,
    required: tuple[str, ...],
) -> None:
    items = registry.get(section)
    if not isinstance(items, list):
        issues.append(RegistryIssue("registry_section_invalid", f"registry section must be a list: {section}", token=section))
        return
    seen: set[str] = set()
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            issues.append(
                RegistryIssue(
                    "registry_section_invalid",
                    f"registry item must be an object: {section}[{index}]",
                    token=f"{section}[{index}]",
                )
            )
            continue
        item_id = item.get("id")
        if isinstance(item_id, str):
            if item_id in seen:
                issues.append(RegistryIssue("registry_duplicate_id", f"duplicate registry id: {item_id}", token=item_id))
            seen.add(item_id)
        for key in required:
            if key not in item:
                issues.append(
                    RegistryIssue(
                        "registry_item_missing_key",
                        f"registry item missing key: {section}[{index}].{key}",
                        token=str(item_id or f"{section}[{index}]"),
                    )
                )


def _registered_ids(registry: dict[str, Any]) -> set[str]:
    ids: set[str] = set()
    for section in ("events", "artifact_families", "interfaces", "maturity_domains"):
        for item in registry.get(section) or []:
            if isinstance(item, dict) and item.get("status") == "registered" and isinstance(item.get("id"), str):
                ids.add(item["id"])
    for item in registry.get("claim_ceiling_levels") or []:
        if isinstance(item, dict) and item.get("status") == "registered" and isinstance(item.get("id"), str):
            ids.add(item["id"])
    return ids


def _deprecated_ids(registry: dict[str, Any]) -> dict[str, str]:
    replacements: dict[str, str] = {}
    for item in registry.get("deprecated_ids") or []:
        if isinstance(item, dict) and isinstance(item.get("id"), str):
            replacements[item["id"]] = str(item.get("replacement") or "")
    return replacements


def _expand_doc_paths(values: list[str | Path]) -> list[Path]:
    paths: list[Path] = []
    for value in values:
        path = Path(value)
        if path.is_dir():
            paths.extend(sorted(child for child in path.rglob("*.md") if child.is_file()))
        elif path.is_file():
            paths.append(path)
    return paths


def _scan_documents(registry: dict[str, Any], paths: list[Path]) -> list[RegistryIssue]:
    registered = _registered_ids(registry)
    deprecated = _deprecated_ids(registry)
    issues: list[RegistryIssue] = []
    for path in paths:
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            for token in _extract_registry_like_ids(line, registered, deprecated):
                if token.startswith("proposed_"):
                    if _proposed_id_is_registered_dependency_context(line):
                        issues.append(
                            RegistryIssue(
                                "proposed_registered_dependency",
                                f"proposed id is described as a registered dependency: {token}",
                                path=str(path),
                                line=line_number,
                                token=token,
                            )
                        )
                    continue
                if token in deprecated:
                    if _deprecated_id_is_allowed_context(line, replacement=deprecated[token]):
                        continue
                    issues.append(
                        RegistryIssue(
                            "deprecated_id",
                            f"deprecated registry id referenced: {token}",
                            path=str(path),
                            line=line_number,
                            token=token,
                            replacement=deprecated[token],
                        )
                    )
                    continue
                if token not in registered:
                    issues.append(
                        RegistryIssue(
                            "unregistered_id",
                            f"registry-like id is not registered: {token}",
                            path=str(path),
                            line=line_number,
                            token=token,
                        )
                    )
    return issues


def _extract_registry_like_ids(line: str, registered: set[str], deprecated: dict[str, str]) -> list[str]:
    tokens: list[str] = []
    for match in _CODE_SPAN_RE.finditer(line):
        value = match.group(1).strip()
        if not value or " " in value or "/" in value:
            continue
        if value in _FIELD_NAME_TOKENS or value in _LOCK_DOMAIN_TOKENS:
            continue
        if "." in value and value.split(".", 1)[0] in registered:
            continue
        if value in registered or value in deprecated or value.startswith("proposed_"):
            if value in {"proposed_event", "proposed_artifact_family", "proposed_interface", "proposed_*"}:
                continue
            tokens.append(value)
        elif _INTERFACE_ID_RE.match(value):
            tokens.append(value)
        elif _EVENT_ID_RE.match(value) and "." in value:
            tokens.append(value)
        elif _is_artifact_family_like(value):
            tokens.append(value)
    return tokens


def _is_artifact_family_like(value: str) -> bool:
    if not re.match(r"^[a-z][a-z0-9_]*$", value):
        return False
    if value.endswith(("_id", "_ids", "_ref", "_refs", "_status", "_at", "_version", "_count", "_ratio", "_action")):
        return False
    return value.startswith(_ARTIFACT_PREFIXES)


def _proposed_id_is_registered_dependency_context(line: str) -> bool:
    normalized = line.lower()
    if any(marker in normalized for marker in _NEGATED_CONTEXT):
        return False
    return any(marker in normalized for marker in _PROPOSED_REGISTERED_CONTEXT) or "| registered" in normalized


def _deprecated_id_is_allowed_context(line: str, *, replacement: str) -> bool:
    normalized = line.lower()
    return replacement in line or any(marker in normalized for marker in _DEPRECATED_CONTEXT)

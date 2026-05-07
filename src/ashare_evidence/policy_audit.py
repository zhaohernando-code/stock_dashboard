from __future__ import annotations

import ast
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = PROJECT_ROOT / "src" / "ashare_evidence"
FRONTEND_ROOT = PROJECT_ROOT / "frontend" / "src"

AUDIT_VERSION = "policy-governance-audit-v1"

FORMULA_MODULES = (
    SRC_ROOT / "formulae.py",
)

DIRECT_CONFIG_ALLOWED = {
    SRC_ROOT / "models.py",
    SRC_ROOT / "policy_config_loader.py",
    SRC_ROOT / "policy_audit.py",
}

GOVERNED_CLASSIFICATIONS = [
    {
        "id": "data_quality_scoring",
        "classification": "tunable_policy",
        "scope": "stock_dashboard",
        "config_key": "data_quality.scoring_v1",
        "owner": "data_quality",
        "source": "default_policy_configs.py",
        "reason": "Data quality weights and thresholds are now governed by a versioned default config.",
    },
    {
        "id": "signal_fusion_formula",
        "classification": "formula",
        "scope": "signal_engine",
        "config_key": "signal_engine.fusion_v1",
        "owner": "signal_engine",
        "source": "formulae.py + default_policy_configs.py",
        "reason": "Fusion weight, penalty, confidence, and model-result math is pure-function based and parameterized.",
    },
    {
        "id": "phase5_simulation_constraints",
        "classification": "stable_rule",
        "scope": "phase5",
        "config_key": "phase5.simulation_policy_v1",
        "owner": "phase5",
        "source": "phase2/phase5_contract.py + default_policy_configs.py",
        "reason": "Simulation constraints remain code-contract governed and are mirrored for visibility.",
    },
    {
        "id": "shortpick_validation_boundary",
        "classification": "research_assumption",
        "scope": "shortpick_lab",
        "config_key": "shortpick_lab.validation_v1",
        "owner": "shortpick_lab",
        "source": "shortpick_lab.py + default_policy_configs.py",
        "reason": "Validation horizons, benchmarks, and blocked display buckets are explicitly classified.",
    },
    {
        "id": "frontend_display_threshold_boundary",
        "classification": "allowed_literal",
        "scope": "frontend",
        "config_key": "frontend.display_v1",
        "owner": "frontend",
        "source": "frontend/src + backend status projection",
        "reason": "Frontend must consume backend status projections instead of hardcoding business thresholds.",
    },
]


def _python_files(root: Path) -> list[Path]:
    return [path for path in root.rglob("*.py") if "__pycache__" not in path.parts]


def _relative(path: Path) -> str:
    return str(path.resolve().relative_to(PROJECT_ROOT.resolve()))


def _direct_config_read_violations() -> list[dict[str, Any]]:
    violations: list[dict[str, Any]] = []
    for path in _python_files(SRC_ROOT):
        if path in DIRECT_CONFIG_ALLOWED:
            continue
        text = path.read_text(encoding="utf-8")
        lower_text = text.lower()
        if (
            "PolicyConfigVersion" in text
            or "from policy_config_versions" in lower_text
            or "delete from policy_config_versions" in lower_text
            or "update policy_config_versions" in lower_text
            or "insert into policy_config_versions" in lower_text
            or "session.add(PolicyConfigVersion" in text
            or "session.merge(PolicyConfigVersion" in text
        ):
            violations.append(
                {
                    "file": _relative(path),
                    "reason": "Business code must use policy_config_loader instead of reading or writing policy_config_versions directly.",
                }
            )
    return violations


def _formula_side_effect_violations() -> list[dict[str, Any]]:
    forbidden_names = {"Session", "select", "os", "getenv", "datetime", "date", "requests", "urlopen", "urllib"}
    violations: list[dict[str, Any]] = []
    for path in FORMULA_MODULES:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    root_name = alias.name.split(".")[0]
                    if root_name in forbidden_names:
                        violations.append({"file": _relative(path), "line": node.lineno, "name": alias.name})
            elif isinstance(node, ast.ImportFrom):
                module_root = (node.module or "").split(".")[0]
                if module_root in forbidden_names or any(alias.name in forbidden_names for alias in node.names):
                    violations.append({"file": _relative(path), "line": node.lineno, "name": node.module})
            elif isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Name) and func.id in forbidden_names:
                    violations.append({"file": _relative(path), "line": node.lineno, "name": func.id})
                if isinstance(func, ast.Attribute) and func.attr in {"now", "utcnow", "getenv", "request", "urlopen"}:
                    violations.append({"file": _relative(path), "line": node.lineno, "name": func.attr})
    return violations


def _config_lineage_violations() -> list[dict[str, Any]]:
    required_markers = {
        SRC_ROOT / "signal_engine_parts" / "recommendation.py": "policy_config_versions",
        SRC_ROOT / "operations.py": "policy_governance",
    }
    violations: list[dict[str, Any]] = []
    for path, marker in required_markers.items():
        text = path.read_text(encoding="utf-8")
        if marker not in text:
            violations.append({"file": _relative(path), "missing_marker": marker})
    return violations


def build_policy_audit_report() -> dict[str, Any]:
    direct_config_read_violations = _direct_config_read_violations()
    formula_side_effect_violations = _formula_side_effect_violations()
    config_lineage_violations = _config_lineage_violations()
    hard_constraint_failures = {
        "direct_config_read": direct_config_read_violations,
        "formula_side_effects": formula_side_effect_violations,
        "missing_config_lineage": config_lineage_violations,
        "new_unclassified": [],
    }
    status = "pass" if not any(hard_constraint_failures.values()) else "fail"
    return {
        "audit_version": AUDIT_VERSION,
        "generated_at": datetime.now(UTC).isoformat(),
        "status": status,
        "classified_items": GOVERNED_CLASSIFICATIONS,
        "classification_counts": {
            classification: sum(1 for item in GOVERNED_CLASSIFICATIONS if item["classification"] == classification)
            for classification in sorted({item["classification"] for item in GOVERNED_CLASSIFICATIONS})
        },
        "hard_constraint_failures": hard_constraint_failures,
        "allowlist_policy": {
            "status": "explicit_classification_required",
            "note": "New governed literals or formulas must be added to the classified registry, default config, or a documented allowlist before closeout.",
        },
    }


def write_policy_audit_report(path: Path | None = None) -> Path:
    target = path or PROJECT_ROOT / "output" / "policy-governance-audit.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(build_policy_audit_report(), ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    return target


def assert_policy_audit(
    *,
    fail_on_new_unclassified: bool,
    fail_on_direct_config_read: bool,
    fail_on_formula_side_effects: bool,
    fail_on_missing_config_lineage: bool,
) -> dict[str, Any]:
    report = build_policy_audit_report()
    failures = report["hard_constraint_failures"]
    enabled_failures: list[str] = []
    if fail_on_new_unclassified and failures["new_unclassified"]:
        enabled_failures.append("new_unclassified")
    if fail_on_direct_config_read and failures["direct_config_read"]:
        enabled_failures.append("direct_config_read")
    if fail_on_formula_side_effects and failures["formula_side_effects"]:
        enabled_failures.append("formula_side_effects")
    if fail_on_missing_config_lineage and failures["missing_config_lineage"]:
        enabled_failures.append("missing_config_lineage")
    if enabled_failures:
        joined = ", ".join(enabled_failures)
        raise RuntimeError(f"policy audit failed: {joined}")
    return report

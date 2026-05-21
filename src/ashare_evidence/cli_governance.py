from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ashare_evidence.contract_registry import DEFAULT_REGISTRY_PATH, check_contract_registry
from ashare_evidence.policy_audit import assert_policy_audit, write_policy_audit_report
from ashare_evidence.process_hardening import parse_line_budget, run_process_hardening_check
from ashare_evidence.process_hardening_evidence import check_required_evidence, parse_required_evidence
from ashare_evidence.process_hardening_line_margin import (
    check_line_budget_warning_margins,
    parse_line_budget_warning_margin,
)
from ashare_evidence.process_hardening_source import check_forbidden_source_tokens, parse_forbidden_source_token


def add_governance_parsers(subparsers: Any) -> None:
    policy_audit = subparsers.add_parser("policy-audit", help="Run constants, formula, and tunable-policy governance checks.")
    policy_audit.add_argument("--write-report", action="store_true")
    policy_audit.add_argument("--report-path", default=None)
    policy_audit.add_argument("--fail-on-new-unclassified", action="store_true")
    policy_audit.add_argument("--fail-on-direct-config-read", action="store_true")
    policy_audit.add_argument("--fail-on-formula-side-effects", action="store_true")
    policy_audit.add_argument("--fail-on-missing-config-lineage", action="store_true")

    contract_registry_check = subparsers.add_parser(
        "contract-registry-check",
        help="Check contract documents against the autonomous-flow JSON registry without runtime side effects.",
    )
    contract_registry_check.add_argument("--registry", default=str(DEFAULT_REGISTRY_PATH))
    contract_registry_check.add_argument("--docs", action="append", required=True)
    contract_registry_check.add_argument("--fail-on-unregistered", action="store_true")
    contract_registry_check.add_argument("--fail-on-deprecated", action="store_true")

    process_hardening_check = subparsers.add_parser(
        "process-hardening-check",
        help="Check explicit autonomous-flow process docs and line budgets without runtime side effects.",
    )
    process_hardening_check.add_argument("--evaluation-doc", action="append", required=True)
    process_hardening_check.add_argument("--line-budget", action="append", required=True)
    process_hardening_check.add_argument("--line-budget-warning-margin", action="append", default=[])
    process_hardening_check.add_argument("--required-evidence", action="append", default=[])
    process_hardening_check.add_argument("--forbidden-source-token", action="append", default=[])
    process_hardening_check.add_argument("--fail-on-warning", action="store_true")
    process_hardening_check.add_argument("--require-clean-git-status", action="store_true")
    process_hardening_check.add_argument("--git-root", default=".")


def handle_policy_audit_command(args: Any) -> int:
    try:
        payload = assert_policy_audit(
            fail_on_new_unclassified=args.fail_on_new_unclassified,
            fail_on_direct_config_read=args.fail_on_direct_config_read,
            fail_on_formula_side_effects=args.fail_on_formula_side_effects,
            fail_on_missing_config_lineage=args.fail_on_missing_config_lineage,
        )
    except RuntimeError as exc:
        payload = assert_policy_audit(
            fail_on_new_unclassified=False,
            fail_on_direct_config_read=False,
            fail_on_formula_side_effects=False,
            fail_on_missing_config_lineage=False,
        )
        _print_json(payload)
        print(str(exc))
        return 1
    if args.write_report:
        path = write_policy_audit_report(None if args.report_path is None else Path(args.report_path))
        payload = {**payload, "report_path": str(path)}
    _print_json(payload)
    return 0


def handle_contract_registry_check_command(args: Any) -> int:
    payload = check_contract_registry(
        registry_path=args.registry,
        docs=args.docs,
        fail_on_unregistered=args.fail_on_unregistered,
        fail_on_deprecated=args.fail_on_deprecated,
    )
    _print_json(payload)
    return 0 if payload["status"] == "pass" else 1


def handle_governance_command(args: Any) -> int | None:
    if args.command == "policy-audit":
        return handle_policy_audit_command(args)
    if args.command == "contract-registry-check":
        return handle_contract_registry_check_command(args)
    if args.command == "process-hardening-check":
        return handle_process_hardening_check_command(args)
    return None


def handle_process_hardening_check_command(args: Any) -> int:
    try:
        line_budgets = [parse_line_budget(raw_value) for raw_value in args.line_budget]
    except ValueError as exc:
        _print_json(_parse_error_payload("line_budget_parse_error", exc))
        return 1
    try:
        required_evidence = [parse_required_evidence(raw_value) for raw_value in args.required_evidence]
    except ValueError as exc:
        _print_json(_parse_error_payload("required_evidence_parse_error", exc))
        return 1
    try:
        warning_margins = [
            parse_line_budget_warning_margin(raw_value) for raw_value in args.line_budget_warning_margin
        ]
    except ValueError as exc:
        _print_json(_parse_error_payload("line_budget_warning_margin_parse_error", exc))
        return 1
    try:
        forbidden_source_tokens = [
            parse_forbidden_source_token(raw_value) for raw_value in args.forbidden_source_token
        ]
    except ValueError as exc:
        _print_json(_parse_error_payload("forbidden_source_token_parse_error", exc))
        return 1
    payload = run_process_hardening_check(
        evaluation_docs=args.evaluation_doc,
        line_budgets=line_budgets,
        fail_on_warning=args.fail_on_warning,
        require_clean_git_status=args.require_clean_git_status,
        git_root=args.git_root,
    )
    evidence_payload = check_required_evidence(required_evidence)
    margin_payload = check_line_budget_warning_margins(payload["line_budgets"], warning_margins)
    source_payload = check_forbidden_source_tokens(forbidden_source_tokens)
    issues = [
        *payload["issues"],
        *evidence_payload["issues"],
        *margin_payload["issues"],
        *source_payload["issues"],
    ]
    has_error = any(issue["severity"] == "error" for issue in issues)
    has_warning = any(issue["severity"] == "warning" for issue in issues)
    payload = {
        **payload,
        "status": "fail" if has_error or (args.fail_on_warning and has_warning) else "pass",
        "issue_count": len(issues),
        "issues": issues,
        "required_evidence": evidence_payload["required_evidence"],
        "line_budget_warning_margins": margin_payload["line_budget_warning_margins"],
        "forbidden_source_tokens": source_payload["forbidden_source_tokens"],
    }
    _print_json(payload)
    return 0 if payload["status"] == "pass" else 1


def _print_json(payload: Any) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))


def _parse_error_payload(code: str, exc: ValueError) -> dict[str, Any]:
    return {
        "status": "fail",
        "issue_count": 1,
        "issues": [{"severity": "error", "code": code, "message": str(exc)}],
        "checked_docs": [],
        "line_budgets": [],
        "required_evidence": [],
        "line_budget_warning_margins": [],
        "forbidden_source_tokens": [],
    }

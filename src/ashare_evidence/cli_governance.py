from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ashare_evidence.contract_registry import DEFAULT_REGISTRY_PATH, check_contract_registry
from ashare_evidence.policy_audit import assert_policy_audit, write_policy_audit_report
from ashare_evidence.process_hardening import parse_line_budget, run_process_hardening_check


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
    process_hardening_check.add_argument("--fail-on-warning", action="store_true")


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
        payload = {
            "status": "fail",
            "issue_count": 1,
            "issues": [
                {
                    "severity": "error",
                    "code": "line_budget_parse_error",
                    "message": str(exc),
                }
            ],
            "checked_docs": [],
            "line_budgets": [],
        }
        _print_json(payload)
        return 1
    payload = run_process_hardening_check(
        evaluation_docs=args.evaluation_doc,
        line_budgets=line_budgets,
        fail_on_warning=args.fail_on_warning,
    )
    _print_json(payload)
    return 0 if payload["status"] == "pass" else 1


def _print_json(payload: Any) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))

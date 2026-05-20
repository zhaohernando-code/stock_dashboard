from __future__ import annotations

import inspect
from typing import get_args

import ashare_evidence.autonomous_flow_scheduler_action_contract as contract_module
from ashare_evidence.autonomous_flow_scheduler_action_contract import (
    get_phase5_scheduler_action_contract,
    list_phase5_scheduler_action_contracts,
)
from ashare_evidence.autonomous_flow_scheduler_plan import Phase5SchedulerAction


def test_all_scheduler_actions_have_contracts() -> None:
    actions = set(get_args(Phase5SchedulerAction))
    contracts = list_phase5_scheduler_action_contracts()

    assert {contract.action for contract in contracts} == actions
    assert len(contracts) == len(actions)


def test_contracts_declare_planned_effects_for_all_actions() -> None:
    expected_effects = {
        "continue_tracking": ("keep_cycle_open_for_next_tick",),
        "rebuild_projection": ("schedule_projection_rebuild",),
        "retry_failed_step": ("schedule_retry",),
        "open_recovery_ticket": ("prepare_recovery_ticket",),
        "block_cycle": ("mark_cycle_blocked",),
        "redesign": ("schedule_redesign_review",),
        "none": ("no_op",),
    }

    for action, planned_effects in expected_effects.items():
        assert get_phase5_scheduler_action_contract(action).planned_effects == planned_effects


def test_no_op_and_continue_tracking_do_not_allow_durable_writes() -> None:
    for action in ("none", "continue_tracking"):
        contract = get_phase5_scheduler_action_contract(action)

        assert contract.execution_strategy == "observe_only"
        assert contract.allowed_side_effects == ("none",)
        assert contract.durable_outputs == ()
        assert contract.may_close_cycle is False


def test_actionable_contracts_declare_inputs_and_durable_outputs() -> None:
    registered_outputs = {
        "frontend_projection_manifest",
        "phase5_cycle_ledger",
        "phase5_recovery_ticket",
        "phase5_scheduler_diagnostic",
        "phase5_scheduler_execution_ledger",
    }
    for action in (
        "rebuild_projection",
        "retry_failed_step",
        "open_recovery_ticket",
        "redesign",
        "block_cycle",
    ):
        contract = get_phase5_scheduler_action_contract(action)

        assert "cycle_id" in contract.required_inputs
        assert contract.durable_outputs
        assert set(contract.durable_outputs) <= registered_outputs
        assert contract.allowed_side_effects != ("none",)


def test_block_cycle_may_close_cycle_without_executing_closeout() -> None:
    contract = get_phase5_scheduler_action_contract("block_cycle")

    assert contract.may_close_cycle is True
    assert contract.planned_effects == ("mark_cycle_blocked",)
    assert contract.durable_outputs == ("phase5_cycle_ledger",)


def test_contract_lookup_is_stable_and_has_no_artifact_root_input() -> None:
    before = list_phase5_scheduler_action_contracts()

    contract = get_phase5_scheduler_action_contract("open_recovery_ticket")

    assert contract.action == "open_recovery_ticket"
    assert before == list_phase5_scheduler_action_contracts()
    assert "artifact_root" not in contract.required_inputs


def test_contract_module_has_no_runtime_io_or_clock_dependencies() -> None:
    source = inspect.getsource(contract_module)

    for token in ("datetime", "time.", "Path(", "open(", "mkdir(", "read_text(", "write_text("):
        assert token not in source

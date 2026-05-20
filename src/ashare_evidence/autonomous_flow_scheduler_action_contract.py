from __future__ import annotations

from collections.abc import Iterable
from typing import Literal, get_args

from pydantic import BaseModel, ConfigDict, Field

from ashare_evidence.autonomous_flow_scheduler_plan import Phase5SchedulerAction

Phase5SchedulerExecutionStrategy = Literal[
    "observe_only",
    "prepare_projection_rebuild",
    "prepare_retry",
    "prepare_recovery_ticket",
    "prepare_cycle_block",
    "prepare_redesign_review",
]
Phase5SchedulerActionPreflightStatus = Literal["ready", "blocked"]


class Phase5SchedulerActionContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    action: Phase5SchedulerAction
    execution_strategy: Phase5SchedulerExecutionStrategy
    planned_effects: tuple[str, ...] = Field(default_factory=tuple)
    required_inputs: tuple[str, ...] = Field(default_factory=tuple)
    allowed_side_effects: tuple[str, ...] = Field(default_factory=tuple)
    durable_outputs: tuple[str, ...] = Field(default_factory=tuple)
    may_close_cycle: bool = False


class Phase5SchedulerActionPreflightResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    action: Phase5SchedulerAction
    status: Phase5SchedulerActionPreflightStatus
    missing_inputs: tuple[str, ...] = Field(default_factory=tuple)
    unauthorized_side_effects: tuple[str, ...] = Field(default_factory=tuple)
    durable_outputs: tuple[str, ...] = Field(default_factory=tuple)
    may_close_cycle: bool = False
    reason: str

    @property
    def ready(self) -> bool:
        return self.status == "ready"


_CONTRACTS: dict[Phase5SchedulerAction, Phase5SchedulerActionContract] = {
    "continue_tracking": Phase5SchedulerActionContract(
        action="continue_tracking",
        execution_strategy="observe_only",
        planned_effects=("keep_cycle_open_for_next_tick",),
        required_inputs=("cycle_id", "scheduler_followup_plan"),
        allowed_side_effects=("none",),
    ),
    "rebuild_projection": Phase5SchedulerActionContract(
        action="rebuild_projection",
        execution_strategy="prepare_projection_rebuild",
        planned_effects=("schedule_projection_rebuild",),
        required_inputs=("cycle_id", "projection_manifest_ref", "projection_staleness_reason"),
        allowed_side_effects=("record_scheduler_execution_intent", "write_projection_artifact"),
        durable_outputs=("frontend_projection_manifest",),
    ),
    "retry_failed_step": Phase5SchedulerActionContract(
        action="retry_failed_step",
        execution_strategy="prepare_retry",
        planned_effects=("schedule_retry",),
        required_inputs=("cycle_id", "failed_step", "retry_reason"),
        allowed_side_effects=("record_scheduler_execution_intent",),
        durable_outputs=("phase5_scheduler_execution_ledger",),
    ),
    "open_recovery_ticket": Phase5SchedulerActionContract(
        action="open_recovery_ticket",
        execution_strategy="prepare_recovery_ticket",
        planned_effects=("prepare_recovery_ticket",),
        required_inputs=("cycle_id", "failure_class", "blocking_reasons"),
        allowed_side_effects=("record_scheduler_execution_intent", "write_recovery_ticket"),
        durable_outputs=("phase5_recovery_ticket",),
    ),
    "block_cycle": Phase5SchedulerActionContract(
        action="block_cycle",
        execution_strategy="prepare_cycle_block",
        planned_effects=("mark_cycle_blocked",),
        required_inputs=("cycle_id", "blocking_reasons", "closeout_preconditions"),
        allowed_side_effects=("record_scheduler_execution_intent", "write_cycle_closeout"),
        durable_outputs=("phase5_cycle_ledger",),
        may_close_cycle=True,
    ),
    "redesign": Phase5SchedulerActionContract(
        action="redesign",
        execution_strategy="prepare_redesign_review",
        planned_effects=("schedule_redesign_review",),
        required_inputs=("cycle_id", "design_gate_reason", "blocking_reasons"),
        allowed_side_effects=("record_scheduler_execution_intent", "record_scheduler_diagnostic"),
        durable_outputs=("phase5_scheduler_diagnostic",),
    ),
    "none": Phase5SchedulerActionContract(
        action="none",
        execution_strategy="observe_only",
        planned_effects=("no_op",),
        required_inputs=("cycle_id", "scheduler_followup_plan"),
        allowed_side_effects=("none",),
    ),
}


def get_phase5_scheduler_action_contract(
    action: Phase5SchedulerAction,
) -> Phase5SchedulerActionContract:
    return _CONTRACTS[action]


def list_phase5_scheduler_action_contracts() -> tuple[Phase5SchedulerActionContract, ...]:
    return tuple(_CONTRACTS[action] for action in get_args(Phase5SchedulerAction))


def preflight_phase5_scheduler_action(
    action: Phase5SchedulerAction,
    *,
    provided_input_names: Iterable[str],
    requested_side_effects: Iterable[str] = (),
) -> Phase5SchedulerActionPreflightResult:
    contract = get_phase5_scheduler_action_contract(action)
    provided_inputs = set(provided_input_names)
    requested_effects = set(requested_side_effects)

    missing_inputs = tuple(input_name for input_name in contract.required_inputs if input_name not in provided_inputs)
    unauthorized_side_effects = _unauthorized_side_effects(
        requested_effects=requested_effects,
        allowed_side_effects=contract.allowed_side_effects,
    )
    status: Phase5SchedulerActionPreflightStatus = (
        "blocked" if missing_inputs or unauthorized_side_effects else "ready"
    )

    return Phase5SchedulerActionPreflightResult(
        action=action,
        status=status,
        missing_inputs=missing_inputs,
        unauthorized_side_effects=unauthorized_side_effects,
        durable_outputs=contract.durable_outputs,
        may_close_cycle=contract.may_close_cycle,
        reason=_preflight_reason(
            status=status,
            missing_inputs=missing_inputs,
            unauthorized_side_effects=unauthorized_side_effects,
        ),
    )


def _unauthorized_side_effects(
    *,
    requested_effects: set[str],
    allowed_side_effects: tuple[str, ...],
) -> tuple[str, ...]:
    if allowed_side_effects == ("none",):
        return tuple(effect for effect in sorted(requested_effects) if effect != "none")

    allowed = set(allowed_side_effects)
    return tuple(effect for effect in sorted(requested_effects) if effect not in allowed)


def _preflight_reason(
    *,
    status: Phase5SchedulerActionPreflightStatus,
    missing_inputs: tuple[str, ...],
    unauthorized_side_effects: tuple[str, ...],
) -> str:
    if status == "ready":
        return "scheduler action preflight passed"
    if missing_inputs and unauthorized_side_effects:
        return "scheduler action preflight blocked by missing inputs and unauthorized side effects"
    if missing_inputs:
        return "scheduler action preflight blocked by missing inputs"
    return "scheduler action preflight blocked by unauthorized side effects"

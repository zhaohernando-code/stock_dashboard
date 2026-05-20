from __future__ import annotations

from ashare_evidence.autonomous_flow_scheduler_action_contract import preflight_phase5_scheduler_action


def test_action_preflight_is_ready_for_required_inputs_and_allowed_side_effects() -> None:
    result = preflight_phase5_scheduler_action(
        "rebuild_projection",
        provided_input_names={
            "cycle_id",
            "projection_manifest_ref",
            "projection_staleness_reason",
        },
        requested_side_effects={"record_scheduler_execution_intent", "write_projection_artifact"},
    )

    assert result.status == "ready"
    assert result.ready is True
    assert result.missing_inputs == ()
    assert result.unauthorized_side_effects == ()
    assert result.durable_outputs == ("frontend_projection_manifest",)
    assert result.may_close_cycle is False


def test_action_preflight_blocks_missing_required_inputs() -> None:
    result = preflight_phase5_scheduler_action(
        "open_recovery_ticket",
        provided_input_names={"cycle_id", "blocking_reasons"},
        requested_side_effects={"write_recovery_ticket"},
    )

    assert result.status == "blocked"
    assert result.ready is False
    assert result.missing_inputs == ("failure_class",)
    assert result.unauthorized_side_effects == ()
    assert result.reason == "scheduler action preflight blocked by missing inputs"


def test_action_preflight_blocks_unauthorized_side_effects() -> None:
    result = preflight_phase5_scheduler_action(
        "retry_failed_step",
        provided_input_names={"cycle_id", "failed_step", "retry_reason"},
        requested_side_effects={"record_scheduler_execution_intent", "write_recovery_ticket"},
    )

    assert result.status == "blocked"
    assert result.missing_inputs == ()
    assert result.unauthorized_side_effects == ("write_recovery_ticket",)
    assert result.reason == "scheduler action preflight blocked by unauthorized side effects"


def test_action_preflight_reports_combined_blockers() -> None:
    result = preflight_phase5_scheduler_action(
        "redesign",
        provided_input_names={"cycle_id"},
        requested_side_effects={"write_recovery_ticket"},
    )

    assert result.status == "blocked"
    assert result.missing_inputs == ("design_gate_reason", "blocking_reasons")
    assert result.unauthorized_side_effects == ("write_recovery_ticket",)
    assert result.reason == "scheduler action preflight blocked by missing inputs and unauthorized side effects"


def test_action_preflight_allows_none_side_effect_contracts_only_to_do_nothing() -> None:
    no_requested_effects = preflight_phase5_scheduler_action(
        "continue_tracking",
        provided_input_names={"cycle_id", "scheduler_followup_plan"},
    )
    explicit_none = preflight_phase5_scheduler_action(
        "none",
        provided_input_names={"cycle_id", "scheduler_followup_plan"},
        requested_side_effects={"none"},
    )
    unauthorized_write = preflight_phase5_scheduler_action(
        "continue_tracking",
        provided_input_names={"cycle_id", "scheduler_followup_plan"},
        requested_side_effects={"none", "record_scheduler_execution_intent"},
    )

    assert no_requested_effects.status == "ready"
    assert explicit_none.status == "ready"
    assert unauthorized_write.status == "blocked"
    assert unauthorized_write.unauthorized_side_effects == ("record_scheduler_execution_intent",)


def test_action_preflight_inherits_closeout_boundary_from_contract() -> None:
    result = preflight_phase5_scheduler_action(
        "block_cycle",
        provided_input_names={"cycle_id", "blocking_reasons", "closeout_preconditions"},
        requested_side_effects={"write_cycle_closeout"},
    )

    assert result.status == "ready"
    assert result.durable_outputs == ("phase5_cycle_ledger",)
    assert result.may_close_cycle is True


def test_action_preflight_does_not_mutate_input_sets() -> None:
    provided_inputs = {"cycle_id", "failed_step", "retry_reason"}
    requested_effects = {"record_scheduler_execution_intent"}

    result = preflight_phase5_scheduler_action(
        "retry_failed_step",
        provided_input_names=provided_inputs,
        requested_side_effects=requested_effects,
    )

    assert result.status == "ready"
    assert provided_inputs == {"cycle_id", "failed_step", "retry_reason"}
    assert requested_effects == {"record_scheduler_execution_intent"}

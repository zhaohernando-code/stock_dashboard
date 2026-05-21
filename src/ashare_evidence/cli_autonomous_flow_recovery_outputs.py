from __future__ import annotations

from argparse import Namespace
from typing import Any

from ashare_evidence.scheduler_recovery_followup_executor import (
    apply_phase5_scheduler_recovery_followup_intent,
)
from ashare_evidence.scheduler_recovery_followup_intent import (
    read_phase5_scheduler_recovery_followup_intent,
)


def handle_attempt_recovery_followup_intent_output(
    args: Namespace,
    *,
    print_json: Any,
) -> int:
    intent = read_phase5_scheduler_recovery_followup_intent(
        cycle_id=args.cycle_id,
        root=args.artifact_root,
    )
    print_json(intent.model_dump(mode="json"))
    return 4 if intent.intent_status == "blocked" else 0


def handle_attempt_recovery_followup_apply_output(
    args: Namespace,
    *,
    print_json: Any,
) -> int:
    intent = read_phase5_scheduler_recovery_followup_intent(
        cycle_id=args.cycle_id,
        root=args.artifact_root,
    )
    result = apply_phase5_scheduler_recovery_followup_intent(
        intent,
        created_at=args.created_at,
        root=args.artifact_root,
    )
    print_json(result.model_dump(mode="json"))
    return 4 if result.apply_status == "blocked" else 0

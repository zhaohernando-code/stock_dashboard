from __future__ import annotations

from ashare_evidence.claim_ceiling import (
    CLAIM_CEILING_BLOCKED,
    CLAIM_CEILING_PAPER_TRACKING_CANDIDATE,
    CLAIM_CEILING_RESEARCH_OBSERVATION,
    CLAIM_CEILING_VALIDATED_READOUT,
    GATE_STATUS_DEGRADED,
    GATE_STATUS_INSUFFICIENT_EVIDENCE,
    GATE_STATUS_PASSED,
    evaluate_claim_ceiling,
)


def test_missing_validation_blocks_user_visible_claims() -> None:
    result = evaluate_claim_ceiling(
        validation_status=None,
        simulation_boundary="simulation_only",
        staleness_status="fresh",
        publish_verification_status="verified",
    )

    assert result["gate_status"] == GATE_STATUS_INSUFFICIENT_EVIDENCE
    assert result["claim_ceiling"] == CLAIM_CEILING_BLOCKED
    assert result["incomplete_gate_ids"] == ["validation_status"]
    assert "actionable_recommendation" in result["forbidden_claims"]


def test_stale_projection_degrades_to_research_observation() -> None:
    result = evaluate_claim_ceiling(
        validation_status="validated",
        simulation_boundary="artifact_backed_validation",
        staleness_status="stale",
        publish_verification_status="verified",
    )

    assert result["gate_status"] == GATE_STATUS_DEGRADED
    assert result["claim_ceiling"] == CLAIM_CEILING_RESEARCH_OBSERVATION
    assert result["failing_gate_ids"] == ["staleness_status"]
    assert result["next_action"] == "retry"


def test_unverified_publish_cannot_reach_validated_readout() -> None:
    result = evaluate_claim_ceiling(
        validation_status="validated",
        simulation_boundary="artifact_backed_validation",
        staleness_status="fresh",
        publish_verification_status="pending",
    )

    assert result["gate_status"] == GATE_STATUS_DEGRADED
    assert result["claim_ceiling"] == CLAIM_CEILING_PAPER_TRACKING_CANDIDATE
    assert result["incomplete_gate_ids"] == ["publish_verification_status"]
    assert "production_win_rate_commitment" in result["forbidden_claims"]


def test_manual_llm_disagreement_never_lifts_ceiling() -> None:
    result = evaluate_claim_ceiling(
        validation_status="validated",
        simulation_boundary="artifact_backed_validation",
        staleness_status="fresh",
        publish_verification_status="verified",
        manual_llm_disagreement=True,
    )

    assert result["gate_status"] == GATE_STATUS_DEGRADED
    assert result["claim_ceiling"] == CLAIM_CEILING_RESEARCH_OBSERVATION
    assert result["failing_gate_ids"] == ["manual_llm_disagreement"]
    assert "automatic_promotion" in result["forbidden_claims"]


def test_simulation_only_stays_at_paper_tracking_candidate() -> None:
    result = evaluate_claim_ceiling(
        validation_status="validated",
        simulation_boundary="simulation_only",
        staleness_status="fresh",
        publish_verification_status="verified",
    )

    assert result["gate_status"] == GATE_STATUS_DEGRADED
    assert result["claim_ceiling"] == CLAIM_CEILING_PAPER_TRACKING_CANDIDATE
    assert "describe_simulation_boundary" in result["allowed_claims"]
    assert "live_trading_recommendation" in result["forbidden_claims"]


def test_validated_readout_requires_validation_boundary_freshness_and_publish() -> None:
    result = evaluate_claim_ceiling(
        {
            "gate_id": "phase5_claim_ceiling",
            "cycle_id": "phase5-cycle-2026-05-20",
            "validation_status": "validated",
            "simulation_boundary": "artifact_backed_validation",
            "staleness_status": "fresh",
            "publish_verification_status": "verified",
            "source_refs": ["artifact://phase5-gate-readout/test"],
        }
    )

    assert result["gate_status"] == GATE_STATUS_PASSED
    assert result["claim_ceiling"] == CLAIM_CEILING_VALIDATED_READOUT
    assert result["failing_gate_ids"] == []
    assert result["incomplete_gate_ids"] == []
    assert result["next_action"] == "none"
    assert result["gate_id"] == "phase5_claim_ceiling"
    assert result["cycle_id"] == "phase5-cycle-2026-05-20"
    assert result["source_refs"] == ["artifact://phase5-gate-readout/test"]

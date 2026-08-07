from __future__ import annotations

from datetime import datetime

import numpy as np

from ashare_evidence.official_facts_static_ablation import (
    OfficialRiskEvent,
    PastOnlyRidgeResidualizer,
    official_fact_risk_severity,
    official_risk_signal,
)


def test_official_risk_taxonomy_suppresses_resolved_or_positive_titles() -> None:
    assert official_fact_risk_severity("关于收到立案调查告知书的公告") == (1.0, "立案调查")
    assert official_fact_risk_severity("关于重大诉讼的公告") == (0.7, "重大诉讼")
    assert official_fact_risk_severity("关于解除冻结的公告") == (0.0, None)
    assert official_fact_risk_severity("关于减持计划完成的公告") == (0.0, None)


def test_official_signal_excludes_information_after_decision_cutoff() -> None:
    events = [
        OfficialRiskEvent(
            symbol="600000.SH",
            available_from=datetime.fromisoformat("2024-01-02T23:59:59.999999+08:00"),
            severity=1.0,
            normalized_event_id="same-day-after-cutoff",
            revision_id="v1",
            title="立案调查",
            rule="立案调查",
        ),
        OfficialRiskEvent(
            symbol="600000.SH",
            available_from=datetime.fromisoformat("2024-01-01T23:59:59.999999+08:00"),
            severity=0.7,
            normalized_event_id="prior-day",
            revision_id="v1",
            title="重大诉讼",
            rule="重大诉讼",
        ),
    ]
    score, matched = official_risk_signal(
        events,
        decision_cutoff=datetime.fromisoformat("2024-01-02T23:59:59+08:00"),
    )
    assert score > 0
    assert [row.normalized_event_id for row in matched] == ["prior-day"]


def test_residualizer_predicts_before_current_date_update() -> None:
    model = PastOnlyRidgeResidualizer(feature_count=1)
    current = np.asarray([[0.0], [1.0]])
    assert model.predict(current).tolist() == [0.0, 0.0]
    model.update(current, np.asarray([0.0, 1.0]), as_of_date="2024-01-01")
    predicted = model.predict(np.asarray([[1.0]]))
    assert 0.0 < predicted[0] < 1.0
    assert model.fit_end == "2024-01-01"

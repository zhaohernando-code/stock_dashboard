from __future__ import annotations

import pytest

from ashare_evidence.external_inventory_rerank import _ridge_predictions, _z_scores


def test_inventory_rerank_z_scores_are_cross_sectional() -> None:
    assert _z_scores([1.0, 1.0]) == [0.0, 0.0]
    values = _z_scores([1.0, 2.0, 3.0])
    assert sum(values) == pytest.approx(0.0)
    assert values[2] > values[1] > values[0]


def test_ridge_predictions_fit_once_for_current_inventory() -> None:
    predictions = _ridge_predictions(
        [[1.0], [2.0], [3.0], [4.0]],
        [0.1, 0.2, 0.3, 0.4],
        [[2.5], [3.5]],
        alpha=0.1,
    )
    assert predictions[1] > predictions[0]

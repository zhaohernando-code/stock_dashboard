from __future__ import annotations

from ashare_evidence.v3_market_confirmed_lifecycle import negative_context_confirmed


def test_negative_context_requires_global_and_mapped_sector_weakness() -> None:
    state = {
        "breadth_5d": 0.3,
        "breadth_20d": 0.6,
        "mean_return_5d": -0.05,
        "mean_return_20d": 0.02,
        "by_sector_name": {
            "电子": {
                "return_5d": -0.08,
                "relative_5d": -0.03,
            }
        },
    }

    confirmed, audit = negative_context_confirmed(
        sector_state=state,
        industry_name="半导体",
        require_sector_weakness=True,
    )

    assert confirmed is True
    assert audit["global_weakness"] is True
    assert audit["sector_weakness"] is True


def test_global_only_variant_does_not_require_sector_mapping() -> None:
    state = {
        "breadth_5d": 0.3,
        "breadth_20d": 0.6,
        "mean_return_5d": -0.05,
        "mean_return_20d": 0.02,
        "by_sector_name": {},
    }

    confirmed, audit = negative_context_confirmed(
        sector_state=state,
        industry_name="未映射行业",
        require_sector_weakness=False,
    )

    assert confirmed is True
    assert audit["sector_mapping_available"] is False

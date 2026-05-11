from __future__ import annotations

from copy import deepcopy
from typing import Any

from ashare_evidence.default_policy_configs import (
    POLICY_SCOPE_SHORTPICK_LAB,
    SHORTPICK_FROZEN_STRATEGY_CONFIG_KEY,
    default_policy_config_payload,
)

SHORTPICK_FROZEN_STRATEGY_CONFIG: dict[str, Any] = default_policy_config_payload(
    POLICY_SCOPE_SHORTPICK_LAB,
    SHORTPICK_FROZEN_STRATEGY_CONFIG_KEY,
)


def shortpick_frozen_strategy_config() -> dict[str, Any]:
    return deepcopy(SHORTPICK_FROZEN_STRATEGY_CONFIG)


def shortpick_market_factor_config() -> dict[str, Any]:
    return deepcopy(SHORTPICK_FROZEN_STRATEGY_CONFIG["market_factor"])


def shortpick_paper_tracking_config() -> dict[str, Any]:
    return deepcopy(SHORTPICK_FROZEN_STRATEGY_CONFIG["paper_tracking"])


def shortpick_control_config() -> dict[str, Any]:
    return deepcopy(SHORTPICK_FROZEN_STRATEGY_CONFIG["controls"])

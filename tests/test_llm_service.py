from __future__ import annotations

from ashare_evidence.llm_service import DEEPSEEK_V4_PRO, AnthropicCompatibleTransport, route_model


def test_shortpick_historical_replay_routes_to_deepseek_v4_pro(monkeypatch) -> None:
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "test-key")
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://api.deepseek.test/anthropic")

    transport, base_url, api_key, model_name = route_model("shortpick_historical_replay")

    assert isinstance(transport, AnthropicCompatibleTransport)
    assert base_url == "https://api.deepseek.test/anthropic"
    assert api_key == "test-key"
    assert model_name == DEEPSEEK_V4_PRO

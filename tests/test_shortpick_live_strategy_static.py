from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_live_shortpick_strategy_overlay_is_explicit_and_lock_aware() -> None:
    source = (REPO_ROOT / "src" / "ashare_evidence" / "shortpick_lab.py").read_text(encoding="utf-8")

    assert "SHORTPICK_MARKET_FACTOR_DEFAULT_FAMILY" in source
    assert "SHORTPICK_MARKET_FACTOR_OFFENSIVE_FAMILY" in source
    assert "insert_shortpick_market_factor_overlay_candidates(session, run)" in source
    assert "consensus_scope" in source
    assert "llm_candidates_only" in source
    assert "_sync_shortpick_market_factor_universe" in source
    assert "session.commit()" in source
    assert "skipped_current_count" in source
    assert "market_factor_overlay" in source


def test_frontend_labels_live_strategy_groups_with_readable_text() -> None:
    source = (REPO_ROOT / "frontend" / "src" / "components" / "ShortpickLabView.tsx").read_text(encoding="utf-8")

    assert "策略默认" in source
    assert "进攻对照" in source
    assert "10日动量换手降追高" in source
    assert "10日动量换手排序" in source
    assert "market_factor_default" in source
    assert "market_factor_offensive" in source

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from ashare_evidence.external_context_news_research import build_news_title_snapshot, normalize_news_title_rows


def test_news_titles_are_relevance_filtered_and_lagged() -> None:
    rows = [
        {"title": "某某科技芯片项目投产", "pub_time": "2026-01-02 10:00:00", "src": "财联社", "url": "u1"},
        {"title": "完全无关的生活资讯", "pub_time": "2026-01-02 11:00:00", "src": "财联社", "url": "u2"},
    ]
    normalized, audit = normalize_news_title_rows(
        rows,
        company_names=["某某科技"],
        industry_names=["半导体"],
        retrieved_at=datetime(2026, 1, 3, tzinfo=UTC),
    )
    assert len(normalized) == 1
    assert normalized[0]["available_at"] == "2026-01-02T11:00:00+08:00"
    assert normalized[0]["relevance"]["company_names"] == ["某某科技"]
    assert normalized[0]["relevance"]["topics"] == ["semiconductor"]
    assert audit["unique_raw_row_count"] == 2


def test_news_snapshot_keeps_titles_but_no_article_body() -> None:
    payload = build_news_title_snapshot(
        raw_batches=[
            {
                "source": "新华网",
                "window_start": "2026-01-01T00:00:00+08:00",
                "window_end": "2026-01-01T23:59:59+08:00",
                "row_count": 1,
                "rows": [
                    {"title": "美联储降息预期升温", "pub_time": "2026-01-01 08:00:00", "src": "新华网"}
                ],
            }
        ],
        company_names=[],
        industry_names=[],
        retrieved_at=datetime(2026, 1, 3, tzinfo=UTC),
        source_endpoint="https://example.invalid",
    )
    assert payload["quality"]["relevant_record_count"] == 1
    assert payload["quality"]["article_body_saved_count"] == 0
    assert "content" not in payload["normalized"]["records"][0]


def test_future_news_availability_is_rejected() -> None:
    with pytest.raises(ValueError, match="future news title"):
        normalize_news_title_rows(
            [{"title": "芯片", "pub_time": "2026-01-02 10:00:00", "src": "财联社"}],
            company_names=[],
            industry_names=[],
            retrieved_at=datetime(2026, 1, 2, 2, 0, tzinfo=UTC),
        )

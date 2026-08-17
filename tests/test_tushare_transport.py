from __future__ import annotations

import http.client
import json
from unittest.mock import patch

import pytest

from ashare_evidence.tushare_transport import post_tushare, secure_tushare_base_url


class _Response:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def read(self) -> bytes:
        return b'{"code":0,"data":{"fields":[],"items":[]}}'


def test_tushare_official_legacy_url_is_upgraded_before_token_transmission() -> None:
    assert secure_tushare_base_url("http://api.tushare.pro") == "https://api.tushare.pro"
    with pytest.raises(ValueError, match="HTTPS"):
        secure_tushare_base_url("http://example.invalid")
    with pytest.raises(ValueError, match="official HTTPS"):
        secure_tushare_base_url("https://example.invalid")


def test_post_tushare_uses_https_and_keeps_token_inside_request_body() -> None:
    observed = {}

    def fake_urlopen(request, *, timeout):
        observed["url"] = request.full_url
        observed["payload"] = json.loads(request.data)
        observed["timeout"] = timeout
        return _Response()

    with patch("ashare_evidence.tushare_transport.urlopen", side_effect=fake_urlopen):
        payload = post_tushare(
            base_url="http://api.tushare.pro",
            token="secret-token",
            api_name="forecast",
            params={"ann_date": "20260814"},
            fields="ts_code,ann_date",
        )

    assert payload["code"] == 0
    assert observed["url"] == "https://api.tushare.pro"
    assert observed["payload"]["token"] == "secret-token"
    assert observed["timeout"] == 8


def test_post_tushare_treats_incomplete_response_as_transient_empty_result() -> None:
    class IncompleteResponse(_Response):
        def read(self) -> bytes:
            raise http.client.IncompleteRead(b"partial")

    with patch("ashare_evidence.tushare_transport.urlopen", return_value=IncompleteResponse()):
        payload = post_tushare(
            base_url="https://api.tushare.pro",
            token="secret-token",
            api_name="forecast_vip",
            params={"period": "20260630"},
        )

    assert payload is None

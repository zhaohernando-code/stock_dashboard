from __future__ import annotations

import gzip
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ashare_evidence.release_verifier import (
    API_ENDPOINTS,
    BANNED_USER_VISIBLE_TERMS,
    REQUIRED_TRACK_TERMS,
    ReleaseVerificationError,
    _api_payload_pair_for_fingerprint,
    _record_api_fingerprint,
    _request_bytes,
    _request_text,
    audit_user_visible_operations_text,
    build_release_manifest,
    endpoint_with_operations_sample_symbol,
    extract_asset_references,
    fingerprint_payload,
    merge_operations_audit_payload,
    normalize_payload_for_fingerprint,
    _write_release_manifest,
)


class ReleaseVerifierTests(unittest.TestCase):
    def test_extract_asset_references_parses_entry_and_vendor_assets(self) -> None:
        html = """
        <html>
          <head>
            <link rel="stylesheet" href="/projects/ashare-dashboard/assets/index-abc123.css" />
            <link rel="modulepreload" href="/projects/ashare-dashboard/assets/vendor-antd-abc123.js" />
            <script type="module" src="/projects/ashare-dashboard/assets/index-def456.js"></script>
            <script type="module" src="/projects/ashare-dashboard/assets/index-def456.js"></script>
          </head>
        </html>
        """

        assets = extract_asset_references(html)

        self.assertEqual(
            assets,
            [
                {
                    "name": "assets/index-abc123.css",
                    "ref": "/projects/ashare-dashboard/assets/index-abc123.css",
                },
                {
                    "name": "assets/vendor-antd-abc123.js",
                    "ref": "/projects/ashare-dashboard/assets/vendor-antd-abc123.js",
                },
                {
                    "name": "assets/index-def456.js",
                    "ref": "/projects/ashare-dashboard/assets/index-def456.js",
                },
            ],
        )

    def test_request_bytes_decompresses_gzip_for_asset_hashing(self) -> None:
        expected = b"console.log('dashboard ready')"

        class Response:
            headers = {"content-encoding": "gzip"}

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return None

            def read(self):
                return gzip.compress(expected)

        class Opener:
            def open(self, request, timeout):
                self.request = request
                self.timeout = timeout
                return Response()

        opener = Opener()
        payload = _request_bytes(
            opener,
            "https://example.test/assets/index.js",
            timeout=20,
            headers={"Accept-Encoding": "gzip"},
        )

        self.assertEqual(payload, expected)
        self.assertEqual(opener.request.get_header("Accept-encoding"), "gzip")
        self.assertEqual(opener.timeout, 20)

    def test_normalize_payload_for_fingerprint_ignores_runtime_noise(self) -> None:
        left = {
            "generated_at": "2026-04-26T00:00:00+00:00",
            "session_key": "left",
            "overview": {
                "last_market_data_at": "2026-04-26T08:00:00+08:00",
                "note": "same",
            },
            "items": [{"symbol": "600519.SH", "updated_at": "2026-04-26T01:00:00+00:00"}],
        }
        right = {
            "generated_at": "2026-04-27T00:00:00+00:00",
            "session_key": "right",
            "overview": {
                "last_market_data_at": "2026-04-27T08:00:00+08:00",
                "note": "same",
            },
            "items": [{"symbol": "600519.SH", "updated_at": "2026-04-27T01:00:00+00:00"}],
        }

        self.assertEqual(
            normalize_payload_for_fingerprint(left),
            normalize_payload_for_fingerprint(right),
        )
        self.assertEqual(fingerprint_payload(left), fingerprint_payload(right))

    def test_normalize_payload_for_fingerprint_ignores_data_latency_seconds(self) -> None:
        left = {
            "overview": {
                "run_health": {
                    "note": "已同步 4 只标的的 5 分钟行情，新增或更新 9 根 K 线。",
                    "status": "warn",
                }
            },
            "today_at_a_glance": {"refresh_status": "warn"},
            "simulation_workspace": {
                "session": {
                    "data_latency_seconds": 32889,
                    "intraday_source_status": {
                        "data_latency_seconds": 32889,
                        "fallback_used": True,
                        "message": "已同步 4 只标的的 5 分钟行情，新增或更新 8 根 K 线。",
                        "provider_label": "AKShare 分钟兜底",
                        "source_kind": "akshare_hist_min_em",
                        "status": "stale",
                    },
                }
            }
        }
        right = {
            "overview": {
                "run_health": {
                    "note": "当前未获取新的实时分钟行情，继续使用本地已缓存的 5 分钟真实数据。",
                    "status": "pass",
                }
            },
            "today_at_a_glance": {"refresh_status": "pass"},
            "simulation_workspace": {
                "session": {
                    "data_latency_seconds": 32890,
                    "intraday_source_status": {
                        "data_latency_seconds": 32890,
                        "fallback_used": False,
                        "message": "已同步 4 只标的的 5 分钟行情，新增或更新 6 根 K 线。",
                        "provider_label": "本地已缓存 5 分钟数据",
                        "source_kind": "cached_5min",
                        "status": "stale",
                    },
                }
            }
        }

        self.assertEqual(
            normalize_payload_for_fingerprint(left),
            normalize_payload_for_fingerprint(right),
        )
        self.assertEqual(fingerprint_payload(left), fingerprint_payload(right))

    def test_normalize_payload_for_fingerprint_ignores_performance_launch_gate_current_value(self) -> None:
        left = {
            "overview": {"launch_readiness": {"warning_gate_count": 4}},
            "launch_gates": [
                {
                    "gate": "刷新与性能预算",
                    "status": "warn",
                    "current_value": "stock 19.4ms / ops 213.0ms / ops payload 153.2kb",
                }
            ]
        }
        right = {
            "overview": {"launch_readiness": {"warning_gate_count": 3}},
            "launch_gates": [
                {
                    "gate": "刷新与性能预算",
                    "status": "pass",
                    "current_value": "stock 5.3ms / ops 131.2ms / ops payload 153.2kb",
                }
            ]
        }

        self.assertEqual(
            normalize_payload_for_fingerprint(left),
            normalize_payload_for_fingerprint(right),
        )
        self.assertEqual(fingerprint_payload(left), fingerprint_payload(right))

    def test_normalize_payload_for_fingerprint_ignores_performance_threshold_observed(self) -> None:
        left = {
            "performance_thresholds": [
                {
                    "metric": "模拟交易运营面板构建延迟",
                    "observed": 236.1,
                    "status": "warn",
                    "target": 320.0,
                    "unit": "ms",
                }
            ]
        }
        right = {
            "performance_thresholds": [
                {
                    "metric": "模拟交易运营面板构建延迟",
                    "observed": 131.2,
                    "status": "pass",
                    "target": 320.0,
                    "unit": "ms",
                }
            ]
        }

        self.assertEqual(
            normalize_payload_for_fingerprint(left),
            normalize_payload_for_fingerprint(right),
        )
        self.assertEqual(fingerprint_payload(left), fingerprint_payload(right))

    def test_operations_text_audit_requires_dual_track_and_blocks_regression_terms(self) -> None:
        good_payload = {
            "simulation_workspace": {
                "manual_track": {"label": "用户轨道"},
                "model_track": {"label": "模型轨道"},
                "session": {"auto_execute_note": "当前仅 Web 模拟盘支持自动执行，不会触发真实交易。"},
                "model_advices": [{"policy_note": "模型轨道会先生成研究建议，再进入模拟复盘。"}],
            }
        }

        good_audit = audit_user_visible_operations_text(good_payload)
        self.assertTrue(good_audit["passed"])
        self.assertEqual(good_audit["missing_required_terms"], [])
        self.assertEqual(good_audit["banned_hits"], [])

        bad_payload = {
            "simulation_workspace": {
                "manual_track": {"label": "用户轨道"},
                "session": {"auto_execute_note": "模型轨道建议（Phase 5 baseline）仍在迁移，manifest 待核对。"},
            }
        }
        bad_audit = audit_user_visible_operations_text(bad_payload)
        self.assertFalse(bad_audit["passed"])
        self.assertIn("模型轨道", bad_audit["combined_text"])
        self.assertIn("模型轨道", REQUIRED_TRACK_TERMS)
        self.assertIn("Phase 5 baseline", bad_audit["banned_hits"])
        self.assertIn("manifest", BANNED_USER_VISIBLE_TERMS)

    def test_release_verifier_uses_bounded_operations_endpoints(self) -> None:
        self.assertNotIn("/dashboard/operations", API_ENDPOINTS.values())
        self.assertIn("/dashboard/operations/summary", API_ENDPOINTS.values())
        self.assertIn("/dashboard/operations/details?section=portfolios", API_ENDPOINTS.values())
        self.assertIn("/dashboard/operations/details?section=replay", API_ENDPOINTS.values())
        self.assertIn("/dashboard/operations/details?section=manual_queue", API_ENDPOINTS.values())
        self.assertIn("/dashboard/operations/details?section=factor_observation", API_ENDPOINTS.values())
        self.assertIn("/dashboard/operations/details?section=sector_exposure", API_ENDPOINTS.values())
        self.assertIn("/dashboard/operations/details?section=policy_governance", API_ENDPOINTS.values())
        self.assertIn("/dashboard/operations/details?section=simulation_workspace", API_ENDPOINTS.values())

    def test_release_verifier_adds_operations_sample_symbol_to_bounded_endpoints(self) -> None:
        self.assertEqual(
            endpoint_with_operations_sample_symbol(
                "/dashboard/operations/details?section=replay",
                "002028.sz",
            ),
            "/dashboard/operations/details?section=replay&sample_symbol=002028.SZ",
        )
        self.assertEqual(
            endpoint_with_operations_sample_symbol(
                "/dashboard/operations/details?section=replay&sample_symbol=600519.SH",
                "002028.SZ",
            ),
            "/dashboard/operations/details?section=replay&sample_symbol=600519.SH",
        )
        self.assertEqual(
            endpoint_with_operations_sample_symbol("/dashboard/candidates", "002028.SZ"),
            "/dashboard/candidates",
        )

    def test_request_text_wraps_raw_timeout_errors(self) -> None:
        class TimeoutOpener:
            def open(self, _request, *, timeout: int):  # noqa: ANN001
                raise TimeoutError("timed out")

        with self.assertRaisesRegex(
            ReleaseVerificationError,
            r"GET http://127.0.0.1:8000/slow failed after 3s: timed out",
        ):
            _request_text(TimeoutOpener(), "http://127.0.0.1:8000/slow", timeout=3)

    def test_operations_fingerprint_reuses_warmed_payloads_without_fetching_again(self) -> None:
        warmup_payloads = {
            "local_payload": {"section": "portfolios", "portfolios": []},
            "canonical_payload": {"section": "portfolios", "portfolios": []},
            "local_duration_seconds": 1.2,
            "canonical_duration_seconds": 1.4,
        }

        with patch(
            "ashare_evidence.release_verifier._timed_request_json",
            side_effect=AssertionError("warmup payload should satisfy operations fingerprint"),
        ):
            payload_pair = _api_payload_pair_for_fingerprint(
                endpoint="/dashboard/operations/details?section=portfolios",
                anonymous_opener=object(),
                canonical_opener=object(),
                local_url="http://127.0.0.1:8000/dashboard/operations/details?section=portfolios",
                canonical_url="https://example.test/api/dashboard/operations/details?section=portfolios",
                timeout=20,
                headers={},
                warmup_payloads=warmup_payloads,
            )

        self.assertEqual(payload_pair["local_payload"], warmup_payloads["local_payload"])
        self.assertEqual(payload_pair["canonical_payload"], warmup_payloads["canonical_payload"])
        self.assertEqual(payload_pair["local_duration_seconds"], 1.2)
        self.assertEqual(payload_pair["canonical_duration_seconds"], 1.4)
        self.assertEqual(payload_pair["local_source"], "warmup")
        self.assertEqual(payload_pair["canonical_source"], "warmup")

    def test_operations_fingerprint_falls_back_once_per_missing_side(self) -> None:
        calls: list[str] = []
        local_url = "http://127.0.0.1:8000/dashboard/operations/details?section=portfolios"
        canonical_url = "https://example.test/api/dashboard/operations/details?section=portfolios"

        def fake_timed_request(
            _opener,
            url: str,
            *,
            timeout: int,
            headers: dict[str, str],
        ) -> tuple[dict[str, str], float]:
            calls.append(url)
            self.assertEqual(timeout, 20)
            self.assertEqual(headers, {"X-Test": "1"})
            return {"source": "fallback", "url": url}, 0.5

        with patch("ashare_evidence.release_verifier._timed_request_json", side_effect=fake_timed_request):
            payload_pair = _api_payload_pair_for_fingerprint(
                endpoint="/dashboard/operations/details?section=portfolios",
                anonymous_opener=object(),
                canonical_opener=object(),
                local_url=local_url,
                canonical_url=canonical_url,
                timeout=20,
                headers={"X-Test": "1"},
                warmup_payloads={
                    "local_payload": {"source": "warmup"},
                    "local_duration_seconds": 1.1,
                },
            )

        self.assertEqual(calls, [canonical_url])
        self.assertEqual(payload_pair["local_payload"], {"source": "warmup"})
        self.assertEqual(payload_pair["canonical_payload"]["source"], "fallback")
        self.assertEqual(payload_pair["local_source"], "warmup")
        self.assertEqual(payload_pair["canonical_source"], "warmup_miss")

        calls.clear()
        with patch("ashare_evidence.release_verifier._timed_request_json", side_effect=fake_timed_request):
            payload_pair = _api_payload_pair_for_fingerprint(
                endpoint="/dashboard/operations/details?section=portfolios",
                anonymous_opener=object(),
                canonical_opener=object(),
                local_url=local_url,
                canonical_url=canonical_url,
                timeout=20,
                headers={"X-Test": "1"},
                warmup_payloads={
                    "canonical_payload": {"source": "warmup"},
                    "canonical_duration_seconds": 1.3,
                },
            )

        self.assertEqual(calls, [local_url])
        self.assertEqual(payload_pair["local_payload"]["source"], "fallback")
        self.assertEqual(payload_pair["canonical_payload"], {"source": "warmup"})
        self.assertEqual(payload_pair["local_source"], "warmup_miss")
        self.assertEqual(payload_pair["canonical_source"], "warmup")

    def test_warmed_payload_fingerprint_mismatch_still_fails_and_writes_snapshots(self) -> None:
        api_fingerprints: dict[str, dict[str, object]] = {}
        snapshot_paths: dict[str, str] = {}
        warmup_payloads = {
            "local_payload": {"section": "portfolios", "portfolios": [{"portfolio_key": "local"}]},
            "canonical_payload": {"section": "portfolios", "portfolios": [{"portfolio_key": "canonical"}]},
            "local_duration_seconds": 1.2,
            "canonical_duration_seconds": 1.4,
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_root = Path(temp_dir)

            with patch(
                "ashare_evidence.release_verifier._timed_request_json",
                side_effect=AssertionError("warmup payload should satisfy operations fingerprint"),
            ):
                payload_pair = _api_payload_pair_for_fingerprint(
                    endpoint="/dashboard/operations/details?section=portfolios",
                    anonymous_opener=object(),
                    canonical_opener=object(),
                    local_url="http://127.0.0.1:8000/dashboard/operations/details?section=portfolios",
                    canonical_url="https://example.test/api/dashboard/operations/details?section=portfolios",
                    timeout=20,
                    headers={},
                    warmup_payloads=warmup_payloads,
                )

            with self.assertRaisesRegex(
                ReleaseVerificationError,
                r"API fingerprint mismatch for /dashboard/operations/details\?section=portfolios",
            ):
                _record_api_fingerprint(
                    endpoint="/dashboard/operations/details?section=portfolios",
                    slug="dashboard-operations-portfolios",
                    request_endpoint="/dashboard/operations/details?section=portfolios&sample_symbol=600519.SH",
                    local_url="http://127.0.0.1:8000/dashboard/operations/details?section=portfolios",
                    canonical_url="https://example.test/api/dashboard/operations/details?section=portfolios",
                    local_payload=payload_pair["local_payload"],
                    canonical_payload=payload_pair["canonical_payload"],
                    local_duration_seconds=payload_pair["local_duration_seconds"],
                    canonical_duration_seconds=payload_pair["canonical_duration_seconds"],
                    local_source=payload_pair["local_source"],
                    canonical_source=payload_pair["canonical_source"],
                    artifact_root=artifact_root,
                    snapshot_paths=snapshot_paths,
                    api_fingerprints=api_fingerprints,
                )

            local_snapshot = Path(snapshot_paths["local_dashboard-operations-portfolios"])
            canonical_snapshot = Path(snapshot_paths["canonical_dashboard-operations-portfolios"])
            self.assertEqual(
                json.loads(local_snapshot.read_text(encoding="utf-8"))["portfolios"][0]["portfolio_key"],
                "local",
            )
            self.assertEqual(
                json.loads(canonical_snapshot.read_text(encoding="utf-8"))["portfolios"][0]["portfolio_key"],
                "canonical",
            )
            fingerprint = api_fingerprints["/dashboard/operations/details?section=portfolios"]
            self.assertFalse(fingerprint["match"])
            self.assertEqual(fingerprint["local_source"], "warmup")
            self.assertEqual(fingerprint["canonical_source"], "warmup")

    def test_operations_text_audit_payload_merge_preserves_required_and_banned_terms(self) -> None:
        summary = {
            "overview": {
                "run_health": {"note": "运营复盘概要。"},
                "launch_readiness": {"note": "当前只读概要。"},
            },
            "portfolios": [],
        }
        portfolios = {
            "section": "portfolios",
            "generated_at": "2026-06-04T00:00:00+00:00",
            "portfolios": [
                {"mode_label": "用户轨道", "strategy_summary": "人工确认后进入模拟复盘。"},
                {"mode_label": "模型轨道", "strategy_summary": "manifest 不能出现在用户可见文本。"},
            ],
        }

        merged = merge_operations_audit_payload(None, summary)
        merged = merge_operations_audit_payload(merged, portfolios)
        audit = audit_user_visible_operations_text(merged)

        self.assertFalse(audit["passed"])
        self.assertEqual(audit["missing_required_terms"], [])
        self.assertIn("manifest", audit["banned_hits"])

    def test_build_release_manifest_records_previous_successful_manifest(self) -> None:
        manifest = build_release_manifest(
            release_id="20260426T123000Z-abcdef123456",
            commit_sha="abcdef1234567890",
            released_at="2026-04-26T12:30:00+00:00",
            repo_root=Path("/repo"),
            runtime_root=Path("/runtime"),
            local_frontend_url="http://127.0.0.1:5174/",
            local_api_base_url="http://127.0.0.1:8000/",
            canonical_base_url="https://hernando-zhao.cn/projects/ashare-dashboard/",
            artifact_root=Path("/repo/output/releases/20260426T123000Z-abcdef123456"),
            previous_successful_manifest={
                "manifest_path": "/repo/output/releases/older/manifest.json",
                "commit_sha": "oldercommit",
            },
            asset_sets={"all_match": True},
            api_warmups={"/dashboard/operations/details?section=portfolios": {"local_duration_seconds": 12.3}},
            api_fingerprints={"/dashboard/operations/summary": {"match": True}},
            operations_text_audit={"match": True},
            artifact_paths={"local_dashboard_operations": "/tmp/local-dashboard-operations.json"},
        )

        self.assertEqual(manifest["status"], "passed")
        self.assertEqual(
            manifest["rollback"]["previous_successful_manifest_path"],
            "/repo/output/releases/older/manifest.json",
        )
        self.assertEqual(manifest["rollback"]["previous_successful_commit_sha"], "oldercommit")
        self.assertEqual(
            manifest["manifest_path"],
            "/repo/output/releases/20260426T123000Z-abcdef123456/manifest.json",
        )
        self.assertEqual(
            manifest["api_warmups"],
            {"/dashboard/operations/details?section=portfolios": {"local_duration_seconds": 12.3}},
        )

    def test_write_release_manifest_can_skip_latest_successful_update(self) -> None:
        manifest = {"status": "passed", "commit_sha": "candidate"}
        with tempfile.TemporaryDirectory() as temp_dir:
            output_root = Path(temp_dir)
            manifest_path = output_root / "20260613T000000Z-candidate" / "manifest.json"

            _write_release_manifest(
                manifest_path,
                output_root,
                manifest,
                update_latest_successful=False,
            )

            self.assertEqual(json.loads(manifest_path.read_text(encoding="utf-8")), manifest)
            self.assertFalse((output_root / "latest-successful.json").exists())

    def test_write_release_manifest_updates_latest_successful_by_default(self) -> None:
        manifest = {"status": "passed", "commit_sha": "candidate"}
        with tempfile.TemporaryDirectory() as temp_dir:
            output_root = Path(temp_dir)
            manifest_path = output_root / "20260613T000000Z-candidate" / "manifest.json"

            _write_release_manifest(manifest_path, output_root, manifest)

            self.assertEqual(json.loads(manifest_path.read_text(encoding="utf-8")), manifest)
            self.assertEqual(
                json.loads((output_root / "latest-successful.json").read_text(encoding="utf-8")),
                manifest,
            )


if __name__ == "__main__":
    unittest.main()

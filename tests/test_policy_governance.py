from __future__ import annotations

import copy
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import delete

from ashare_evidence.api import create_app
from ashare_evidence.cli import main
from ashare_evidence.data_quality import build_data_quality_summary
from ashare_evidence.db import init_database, session_scope
from ashare_evidence.default_policy_configs import (
    DATA_QUALITY_CONFIG_KEY,
    POLICY_SCOPE_STOCK_DASHBOARD,
    default_policy_config_payload,
)
from ashare_evidence.models import NewsEntityLink, NewsItem, PolicyConfigVersion
from ashare_evidence.policy_audit import assert_policy_audit, build_policy_audit_report
from ashare_evidence.policy_config_loader import (
    activate_policy_config_version,
    build_policy_governance_summary,
    compute_policy_config_checksum,
    create_policy_config_version,
    get_active_policy_config,
    list_policy_config_versions,
)
from tests.fixtures import seed_watchlist_fixture


class PolicyGovernanceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database_url = f"sqlite:///{Path(self.temp_dir.name) / 'policy-governance.db'}"
        init_database(self.database_url)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_default_policy_config_is_active_without_database_override(self) -> None:
        with session_scope(self.database_url) as session:
            config = get_active_policy_config(
                session,
                scope=POLICY_SCOPE_STOCK_DASHBOARD,
                config_key=DATA_QUALITY_CONFIG_KEY,
            )

        self.assertEqual(config["source"], "code_default")
        self.assertEqual(config["version"], "code-default")
        self.assertEqual(config["checksum"], compute_policy_config_checksum(config["payload"]))

    def test_draft_does_not_apply_until_activated_and_activation_retires_prior_active(self) -> None:
        payload = default_policy_config_payload(POLICY_SCOPE_STOCK_DASHBOARD, DATA_QUALITY_CONFIG_KEY)
        draft_payload = copy.deepcopy(payload)
        draft_payload["news_coverage"]["missing_news_score"] = 0.72

        with session_scope(self.database_url) as session:
            create_policy_config_version(
                session,
                scope=POLICY_SCOPE_STOCK_DASHBOARD,
                config_key=DATA_QUALITY_CONFIG_KEY,
                version="2026-05-07-draft",
                payload=draft_payload,
                reason="Raise missing-news soft ceiling after validation review.",
                evidence_refs=["artifact://policy-test"],
                created_by="root",
            )
            self.assertEqual(
                get_active_policy_config(
                    session,
                    scope=POLICY_SCOPE_STOCK_DASHBOARD,
                    config_key=DATA_QUALITY_CONFIG_KEY,
                )["payload"]["news_coverage"]["missing_news_score"],
                0.65,
            )
            activate_policy_config_version(
                session,
                scope=POLICY_SCOPE_STOCK_DASHBOARD,
                config_key=DATA_QUALITY_CONFIG_KEY,
                version="2026-05-07-draft",
                approved_by="root",
            )
            active = get_active_policy_config(
                session,
                scope=POLICY_SCOPE_STOCK_DASHBOARD,
                config_key=DATA_QUALITY_CONFIG_KEY,
            )

        self.assertEqual(active["source"], "database")
        self.assertEqual(active["payload"]["news_coverage"]["missing_news_score"], 0.72)

    def test_active_data_quality_config_changes_runtime_projection_and_records_lineage(self) -> None:
        payload = default_policy_config_payload(POLICY_SCOPE_STOCK_DASHBOARD, DATA_QUALITY_CONFIG_KEY)
        payload["news_coverage"]["missing_news_score"] = 0.72
        with session_scope(self.database_url) as session:
            seed_watchlist_fixture(session, symbols=("600519.SH",))
            session.execute(delete(NewsEntityLink))
            session.execute(delete(NewsItem))
            create_policy_config_version(
                session,
                scope=POLICY_SCOPE_STOCK_DASHBOARD,
                config_key=DATA_QUALITY_CONFIG_KEY,
                version="2026-05-07-active",
                payload=payload,
                reason="Test active data-quality config projection.",
                evidence_refs=["artifact://data-quality-test"],
                created_by="root",
                status="active",
                approved_by="root",
            )

        with session_scope(self.database_url) as session:
            summary = build_data_quality_summary(session, symbols=["600519.SH"])

        item = summary["items"][0]
        self.assertEqual(item["news_coverage"]["score"], 0.72)
        self.assertEqual(summary["policy_config_versions"][DATA_QUALITY_CONFIG_KEY]["version"], "2026-05-07-active")
        self.assertIn(DATA_QUALITY_CONFIG_KEY, item["policy_config_versions"])

    def test_config_versions_require_reason_and_payload_schema(self) -> None:
        with session_scope(self.database_url) as session:
            with self.assertRaises(ValueError):
                create_policy_config_version(
                    session,
                    scope=POLICY_SCOPE_STOCK_DASHBOARD,
                    config_key=DATA_QUALITY_CONFIG_KEY,
                    version="missing-reason",
                    payload=default_policy_config_payload(POLICY_SCOPE_STOCK_DASHBOARD, DATA_QUALITY_CONFIG_KEY),
                    reason="",
                )
            with self.assertRaises(ValueError):
                create_policy_config_version(
                    session,
                    scope=POLICY_SCOPE_STOCK_DASHBOARD,
                    config_key=DATA_QUALITY_CONFIG_KEY,
                    version="missing-payload-key",
                    payload={"weights": {}},
                    reason="Malformed payload must fail.",
                )

    def test_active_policy_config_is_immutable_after_activation(self) -> None:
        payload = default_policy_config_payload(POLICY_SCOPE_STOCK_DASHBOARD, DATA_QUALITY_CONFIG_KEY)
        with session_scope(self.database_url) as session:
            record = create_policy_config_version(
                session,
                scope=POLICY_SCOPE_STOCK_DASHBOARD,
                config_key=DATA_QUALITY_CONFIG_KEY,
                version="2026-05-07-immutable",
                payload=payload,
                reason="Immutability test.",
                status="active",
                approved_by="root",
            )
            record.payload = {**payload, "weights": {**payload["weights"], "profile": 0.1}}
            with self.assertRaisesRegex(ValueError, "Active policy config versions are immutable"):
                session.flush()
            session.rollback()

    def test_policy_governance_summary_can_omit_large_payload_details(self) -> None:
        with session_scope(self.database_url) as session:
            summary = build_policy_governance_summary(session, include_details=False)

        self.assertGreaterEqual(summary["default_config_count"], 1)
        self.assertNotIn("payload", summary["active_configs"][0])
        self.assertIn("checksum", summary["active_configs"][0])

    def test_policy_audit_hard_constraints_and_cli(self) -> None:
        report = assert_policy_audit(
            fail_on_new_unclassified=True,
            fail_on_direct_config_read=True,
            fail_on_formula_side_effects=True,
            fail_on_missing_config_lineage=True,
        )
        self.assertEqual(report["status"], "pass")
        self.assertEqual(main(["policy-audit", "--fail-on-direct-config-read"]), 0)

    def test_policy_governance_api_exposes_active_history_and_audit(self) -> None:
        with session_scope(self.database_url) as session:
            create_policy_config_version(
                session,
                scope=POLICY_SCOPE_STOCK_DASHBOARD,
                config_key=DATA_QUALITY_CONFIG_KEY,
                version="2026-05-07-history",
                payload=default_policy_config_payload(POLICY_SCOPE_STOCK_DASHBOARD, DATA_QUALITY_CONFIG_KEY),
                reason="API history test.",
                created_by="root",
            )

        client = TestClient(create_app(self.database_url, enable_background_ops_tick=False))
        active = client.get("/policy-governance/active")
        history = client.get("/policy-governance/history")
        audit = client.get("/policy-governance/audit")

        self.assertEqual(active.status_code, 200)
        self.assertGreaterEqual(active.json()["default_config_count"], 1)
        self.assertEqual(history.status_code, 200)
        self.assertGreaterEqual(len(history.json()["items"]), 1)
        self.assertEqual(audit.status_code, 200)
        self.assertEqual(audit.json()["status"], build_policy_audit_report()["status"])

    def test_policy_config_table_exists_after_init(self) -> None:
        with session_scope(self.database_url) as session:
            self.assertEqual(session.query(PolicyConfigVersion).count(), len(list_policy_config_versions(session)))


if __name__ == "__main__":
    unittest.main()

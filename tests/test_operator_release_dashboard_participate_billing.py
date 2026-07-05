from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "materialize_operator_release_dashboard.py"


def load_module():
    spec = importlib.util.spec_from_file_location("materialize_operator_release_dashboard", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class OperatorReleaseDashboardParticipateBillingTests(unittest.TestCase):
    def test_dashboard_materializes_into_current_repo_published_root(self) -> None:
        module = load_module()

        self.assertEqual(SCRIPT_PATH.parents[1], module.RUN_SERVICES_ROOT)
        self.assertEqual(SCRIPT_PATH.parents[1] / ".codex-studio" / "published", module.PUBLISHED_ROOT)

    def test_dashboard_release_channel_path_falls_back_to_shared_workspace_when_local_registry_is_missing(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="operator-dashboard-release-channel-") as temp_dir:
            shared_workspace = Path(temp_dir) / "shared"
            shared_run_services = shared_workspace / "chummer.run-services"
            shared_release_channel = shared_run_services / "Chummer.Portal" / "downloads" / "RELEASE_CHANNEL.generated.json"
            shared_release_channel.parent.mkdir(parents=True, exist_ok=True)
            shared_release_channel.write_text(
                json.dumps({"status": "published", "version": "run-20260705-040324"}) + "\n",
                encoding="utf-8",
            )

            with mock.patch.object(module, "SHARED_WORKSPACE_ROOT", shared_workspace), \
                mock.patch.object(module, "SHARED_REGISTRY_ROOT", shared_workspace / "chummer-hub-registry" / ".codex-studio" / "published"), \
                mock.patch.object(module, "SHARED_RUN_SERVICES_ROOT", shared_run_services), \
                mock.patch.object(module, "REGISTRY_ROOT", Path(temp_dir) / "missing-registry"):
                self.assertEqual(shared_release_channel, module.resolve_release_channel_path())

    def test_dashboard_surfaces_participate_billing_honesty_gate(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="operator-dashboard-") as temp_dir:
            published = Path(temp_dir) / "published"
            published.mkdir(parents=True, exist_ok=True)
            completion = Path(temp_dir) / "completion"
            completion.mkdir(parents=True, exist_ok=True)
            registry = Path(temp_dir) / "registry"
            registry.mkdir(parents=True, exist_ok=True)

            receipts = {
                published / "EXTERNAL_DISTRIBUTION_MIRROR_PROOF.generated.json": {"status": "pass"},
                published / "RULESET_READINESS.generated.json": {"status": "pass", "rulesets": {}},
                published / "CHUMMER_PUBLIC_ROUTE_PROOF.generated.json": {"status": "pass", "base_url": "https://chummer.run"},
                completion / "UI_FRAME_INTEGRITY.generated.json": {"status": "pass", "base_url": "https://chummer.run", "summary": {"checked_pages": 1, "failure_count": 0}},
                published / "DESIGN_QUALITY_GATE.generated.json": {"status": "pass", "verdict": "READY"},
                published / "PUBLIC_COPY_LEAK_GATE.generated.json": {"status": "pass", "verdict": "READY"},
                published / "PARTICIPATE_BILLING_HONESTY.generated.json": {"status": "pass", "verdict": "READY"},
                published / "ACCOUNT_HANDOFF_RUNTIME_CONFIG.generated.json": {
                    "status": "pass",
                    "verdict": "READY",
                    "billing": {"mode": "external_handoff_configured"},
                    "release_upload": {"mode": "default_single_operator"},
                },
                published / "PUBLIC_EDGE_POSTDEPLOY_GATE.generated.json": {
                    "status": "pass",
                    "generatedAtUtc": "2026-06-24T08:05:00Z",
                    "releaseManifestVersion": "run-20260624-080000",
                    "visibleVersion": "Version run-20260624-080000",
                    "navigationStatus": "pass",
                    "pwaStaticStatus": "pass",
                    "mobileLedgerStatus": "pass",
                    "mobileLedgerPayloadStatus": "opt_in_required",
                    "readyMobileHandoffStatus": "pass",
                    "participateIframeShellStatus": "pass",
                    "flagshipHorizonsStatus": "pass",
                },
                published / "RELEASE_READY.generated.json": {"status": "pass", "verdict": "RELEASE_READY"},
                published / "FINAL_GOLD_JANITOR.generated.json": {"status": "pass", "verdict": "GOLD_READY"},
                published / "GOOGLE_OAUTH_LINKING_PROOF.generated.json": {"status": "pass"},
                published / "WINDOWS_INSTALLER_VISUAL_AUDIT.generated.json": {
                    "status": "fail",
                    "artifact": {
                        "fileName": "chummer-avalonia-win-x64-installer.exe",
                        "sha256": "promoted-sha",
                    },
                    "visualAuditSource": {
                        "status": "pass",
                        "artifactSha256": "stale-sha",
                    },
                    "failures": ["Windows installer visual audit source digest does not match promoted installer"],
                },
                published / "WINDOWS_INSTALLER_VISUAL_AUDIT_INTAKE_REQUEST.generated.json": {
                    "status": "external_artifact_required",
                    "promoted_installer": {
                        "file_name": "chummer-avalonia-win-x64-installer.exe",
                        "sha256": "promoted-sha",
                    },
                    "operator_request": {
                        "summary": "Run the promoted Windows installer on a native Windows host and provide the gold proof bundle."
                    },
                    "last_discovery": {
                        "gold_proof_zip": {"status": "not_found"},
                        "visual_sources": {"matching_promoted_count": 0},
                    },
                    "import_command": "python3 scripts/import_windows_installer_gold_proof_artifact.py windows-installer-gold-proof.zip --verify",
                },
                registry / "RELEASE_CHANNEL.generated.json": {
                    "status": "published",
                    "version": "run-20260624-080000",
                    "publishedAt": "2026-06-24T08:00:00Z",
                    "channel": "stable",
                    "supportabilityState": "supported",
                },
            }
            for path, payload in receipts.items():
                path.write_text(json.dumps(payload) + "\n", encoding="utf-8")

            with mock.patch.object(module, "PUBLISHED_ROOT", published), \
                mock.patch.object(module, "COMPLETION_ROOT", completion), \
                mock.patch.object(module, "REGISTRY_ROOT", registry):
                payload = module.build_payload()

        self.assertEqual("pass", payload["status"])
        self.assertEqual("NIGHTLY_HANDOFF_READY", payload["verdict"])
        self.assertFalse(payload["release_readiness"]["full_release_ready"])
        self.assertTrue(payload["release_readiness"]["nightly_handoff_ready"])
        self.assertEqual(
            ["windows_installer_visual_audit"],
            payload["release_readiness"]["full_release_blockers"],
        )
        self.assertIn("participate_billing_honesty", payload["checks"])
        self.assertTrue(payload["checks"]["participate_billing_honesty"]["pass"])
        self.assertIn("account_handoff_runtime_config", payload["checks"])
        self.assertTrue(payload["checks"]["account_handoff_runtime_config"]["pass"])
        self.assertEqual(payload["account_handoffs"]["billing_mode"], "external_handoff_configured")
        self.assertIn("public_edge_postdeploy_gate", payload["checks"])
        self.assertTrue(payload["checks"]["public_edge_postdeploy_gate"]["pass"])
        self.assertEqual("2026-06-24T08:05:00Z", payload["checks"]["public_edge_postdeploy_gate"]["generated_at_utc"])
        self.assertEqual(payload["public_edge"]["mobile_ledger_payload_status"], "opt_in_required")
        self.assertIn("google_oauth_linking_proof", payload["checks"])
        self.assertFalse(payload["checks"]["google_oauth_linking_proof"]["release_blocking"])
        self.assertEqual("pass", payload["google_oauth_linking"]["status"])
        self.assertIn("windows_installer_visual_audit", payload["checks"])
        self.assertFalse(payload["checks"]["windows_installer_visual_audit"]["release_blocking"])
        self.assertIn("windows_installer_visual_audit_intake_request", payload["checks"])
        self.assertFalse(payload["checks"]["windows_installer_visual_audit_intake_request"]["release_blocking"])
        self.assertTrue(payload["checks"]["windows_installer_visual_audit_intake_request"]["pass"])
        self.assertEqual(payload["windows_installer_visual_audit"]["artifact_sha256"], "promoted-sha")
        self.assertEqual(payload["windows_installer_visual_audit"]["visual_source_artifact_sha256"], "stale-sha")
        self.assertEqual(payload["windows_installer_visual_audit"]["matching_promoted_visual_source_count"], 0)
        self.assertEqual(
            payload["windows_installer_visual_audit"]["import_command"],
            "python3 scripts/import_windows_installer_gold_proof_artifact.py windows-installer-gold-proof.zip --verify",
        )

    def test_dashboard_surfaces_google_oauth_operator_handoff_context(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="operator-dashboard-google-oauth-") as temp_dir:
            published = Path(temp_dir) / "published"
            published.mkdir(parents=True, exist_ok=True)
            completion = Path(temp_dir) / "completion"
            completion.mkdir(parents=True, exist_ok=True)
            registry = Path(temp_dir) / "registry"
            registry.mkdir(parents=True, exist_ok=True)

            receipts = {
                published / "EXTERNAL_DISTRIBUTION_MIRROR_PROOF.generated.json": {"status": "pass"},
                published / "RULESET_READINESS.generated.json": {"status": "pass", "rulesets": {}},
                published / "CHUMMER_PUBLIC_ROUTE_PROOF.generated.json": {"status": "pass", "base_url": "https://chummer.run"},
                completion / "UI_FRAME_INTEGRITY.generated.json": {"status": "pass", "base_url": "https://chummer.run", "summary": {"checked_pages": 1, "failure_count": 0}},
                published / "DESIGN_QUALITY_GATE.generated.json": {"status": "pass", "verdict": "READY"},
                published / "PUBLIC_COPY_LEAK_GATE.generated.json": {"status": "pass", "verdict": "READY"},
                published / "PARTICIPATE_BILLING_HONESTY.generated.json": {"status": "pass", "verdict": "READY"},
                published / "ACCOUNT_HANDOFF_RUNTIME_CONFIG.generated.json": {"status": "pass", "verdict": "READY"},
                published / "PUBLIC_EDGE_POSTDEPLOY_GATE.generated.json": {"status": "pass"},
                published / "RELEASE_READY.generated.json": {"status": "fail", "verdict": "NOT_RELEASE_READY"},
                published / "FINAL_GOLD_JANITOR.generated.json": {"status": "fail", "verdict": "NOT_GOLD"},
                published / "GOOGLE_OAUTH_LINKING_PROOF.generated.json": {
                    "status": "fail",
                    "failures": [
                        "operator_end_to_end_evidence: missing operator evidence receipt: /tmp/operator-evidence.json",
                        "operator_request_artifacts: operator ask delivery is stale; resend current ask: python3 resend-google",
                    ],
                    "operator_end_to_end_evidence": {
                        "pass": False,
                        "exists": False,
                        "path": "/tmp/operator-evidence.json",
                    },
                    "operator_request_artifacts": {
                        "pass": True,
                        "request_status": "operator_action_required",
                        "request_receipt_path": "/tmp/operator-request.generated.json",
                        "operator_ask_text_path": "/tmp/CURRENT_GOOGLE_OAUTH_LINKING_OPERATOR_ASK.txt",
                        "operator_ask_metadata_path": "/tmp/CURRENT_GOOGLE_OAUTH_LINKING_OPERATOR_ASK.generated.json",
                        "operator_evidence_template_path": "/tmp/GOOGLE_OAUTH_LINKING_OPERATOR_EVIDENCE.template.generated.json",
                        "operator_ask_receipt_name": "google-oauth-linking-operator-ask.receipt.json",
                        "operator_ask_send_command": "python3 send-google",
                        "operator_ask_resend_command": "python3 resend-google",
                        "operator_ask_delivery_status": "sent",
                        "operator_ask_delivery_generated_at_utc": "2026-07-05T09:35:52Z",
                        "operator_ask_delivery_receipt_path": "/tmp/google-ask.receipt.json",
                        "operator_ask_delivery_matches_current_text": False,
                        "operator_ask_delivery_needs_resend": True,
                        "preferred_drop_path": "/tmp/google-proof.zip",
                        "import_command": "python3 scripts/import_google_oauth_linking_operator_evidence_artifact.py /tmp/google-proof.zip --verify",
                        "auto_import_watch_command": "python3 scripts/auto_import_google_oauth_linking_operator_evidence.py --wait-seconds 900",
                        "post_import_verify_command": "python3 scripts/verify_google_oauth_linking_proof.py --require-pass",
                    },
                },
                published / "WINDOWS_INSTALLER_VISUAL_AUDIT.generated.json": {"status": "fail"},
                published / "WINDOWS_INSTALLER_VISUAL_AUDIT_INTAKE_REQUEST.generated.json": {"status": "external_artifact_required"},
                registry / "RELEASE_CHANNEL.generated.json": {
                    "status": "published",
                    "version": "run-20260705-040324",
                    "publishedAt": "2026-07-05T04:05:30Z",
                    "channel": "preview",
                    "supportabilityState": "preview_supported",
                },
            }
            for path, payload in receipts.items():
                path.write_text(json.dumps(payload) + "\n", encoding="utf-8")

            with mock.patch.object(module, "PUBLISHED_ROOT", published), \
                mock.patch.object(module, "COMPLETION_ROOT", completion), \
                mock.patch.object(module, "REGISTRY_ROOT", registry):
                payload = module.build_payload()
                markdown = module.build_markdown(payload)

        self.assertEqual("fail", payload["checks"]["google_oauth_linking_proof"]["status"])
        self.assertFalse(payload["checks"]["google_oauth_linking_proof"]["release_blocking"])
        self.assertEqual("operator_action_required", payload["google_oauth_linking"]["request_status"])
        self.assertEqual("/tmp/operator-request.generated.json", payload["google_oauth_linking"]["request_receipt_path"])
        self.assertEqual("/tmp/operator-evidence.json", payload["google_oauth_linking"]["operator_evidence_path"])
        self.assertEqual("python3 send-google", payload["google_oauth_linking"]["operator_ask_send_command"])
        self.assertEqual("python3 resend-google", payload["google_oauth_linking"]["operator_ask_resend_command"])
        self.assertEqual("sent", payload["google_oauth_linking"]["operator_ask_delivery_status"])
        self.assertFalse(payload["google_oauth_linking"]["operator_ask_delivery_matches_current_text"])
        self.assertTrue(payload["google_oauth_linking"]["operator_ask_delivery_needs_resend"])
        self.assertEqual("/tmp/google-proof.zip", payload["google_oauth_linking"]["preferred_drop_path"])
        self.assertIn("import_google_oauth_linking_operator_evidence_artifact.py", payload["google_oauth_linking"]["import_command"])
        self.assertIn("auto_import_google_oauth_linking_operator_evidence.py", payload["google_oauth_linking"]["auto_import_watch_command"])
        self.assertIn("## Google OAuth Handoff", markdown)
        self.assertIn("`python3 resend-google`", markdown)

    def test_dashboard_full_release_blockers_include_release_ready_when_release_gate_fails(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="operator-dashboard-release-ready-") as temp_dir:
            published = Path(temp_dir) / "published"
            published.mkdir(parents=True, exist_ok=True)
            completion = Path(temp_dir) / "completion"
            completion.mkdir(parents=True, exist_ok=True)
            registry = Path(temp_dir) / "registry"
            registry.mkdir(parents=True, exist_ok=True)

            receipts = {
                published / "EXTERNAL_DISTRIBUTION_MIRROR_PROOF.generated.json": {"status": "pass"},
                published / "RULESET_READINESS.generated.json": {"status": "pass", "rulesets": {}},
                published / "CHUMMER_PUBLIC_ROUTE_PROOF.generated.json": {"status": "pass", "base_url": "https://chummer.run"},
                completion / "UI_FRAME_INTEGRITY.generated.json": {"status": "pass", "base_url": "https://chummer.run", "summary": {"checked_pages": 1, "failure_count": 0}},
                published / "DESIGN_QUALITY_GATE.generated.json": {"status": "pass", "verdict": "READY"},
                published / "PUBLIC_COPY_LEAK_GATE.generated.json": {"status": "pass", "verdict": "READY"},
                published / "PARTICIPATE_BILLING_HONESTY.generated.json": {"status": "pass", "verdict": "READY"},
                published / "ACCOUNT_HANDOFF_RUNTIME_CONFIG.generated.json": {"status": "pass", "verdict": "READY"},
                published / "PUBLIC_EDGE_POSTDEPLOY_GATE.generated.json": {"status": "pass"},
                published / "RELEASE_READY.generated.json": {"status": "fail", "verdict": "NOT_RELEASE_READY"},
                published / "FINAL_GOLD_JANITOR.generated.json": {"status": "fail", "verdict": "NOT_GOLD"},
                published / "GOOGLE_OAUTH_LINKING_PROOF.generated.json": {"status": "pass"},
                published / "WINDOWS_INSTALLER_VISUAL_AUDIT.generated.json": {"status": "fail"},
                published / "WINDOWS_INSTALLER_VISUAL_AUDIT_INTAKE_REQUEST.generated.json": {"status": "external_artifact_required"},
                registry / "RELEASE_CHANNEL.generated.json": {
                    "status": "published",
                    "version": "run-20260624-080000",
                    "publishedAt": "2026-06-24T08:00:00Z",
                    "channel": "preview",
                    "supportabilityState": "preview_supported",
                },
            }
            for path, payload in receipts.items():
                path.write_text(json.dumps(payload) + "\n", encoding="utf-8")

            with mock.patch.object(module, "PUBLISHED_ROOT", published), \
                mock.patch.object(module, "COMPLETION_ROOT", completion), \
                mock.patch.object(module, "REGISTRY_ROOT", registry):
                payload = module.build_payload()

        self.assertEqual("pass", payload["status"])
        self.assertEqual("NIGHTLY_HANDOFF_READY", payload["verdict"])
        self.assertEqual(
            ["release_ready", "windows_installer_visual_audit"],
            payload["release_readiness"]["full_release_blockers"],
        )

    def test_dashboard_requires_public_edge_postdeploy_gate(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="operator-dashboard-edge-") as temp_dir:
            published = Path(temp_dir) / "published"
            published.mkdir(parents=True, exist_ok=True)
            completion = Path(temp_dir) / "completion"
            completion.mkdir(parents=True, exist_ok=True)
            registry = Path(temp_dir) / "registry"
            registry.mkdir(parents=True, exist_ok=True)

            receipts = {
                published / "EXTERNAL_DISTRIBUTION_MIRROR_PROOF.generated.json": {"status": "pass"},
                published / "RULESET_READINESS.generated.json": {"status": "pass", "rulesets": {}},
                published / "CHUMMER_PUBLIC_ROUTE_PROOF.generated.json": {"status": "pass", "base_url": "https://chummer.run"},
                completion / "UI_FRAME_INTEGRITY.generated.json": {"status": "pass", "base_url": "https://chummer.run", "summary": {"checked_pages": 1, "failure_count": 0}},
                published / "DESIGN_QUALITY_GATE.generated.json": {"status": "pass", "verdict": "READY"},
                published / "PUBLIC_COPY_LEAK_GATE.generated.json": {"status": "pass", "verdict": "READY"},
                published / "PARTICIPATE_BILLING_HONESTY.generated.json": {"status": "pass", "verdict": "READY"},
                published / "ACCOUNT_HANDOFF_RUNTIME_CONFIG.generated.json": {"status": "pass", "verdict": "READY"},
                published / "RELEASE_READY.generated.json": {"status": "pass", "verdict": "RELEASE_READY"},
                published / "FINAL_GOLD_JANITOR.generated.json": {"status": "pass", "verdict": "GOLD_READY"},
                published / "GOOGLE_OAUTH_LINKING_PROOF.generated.json": {"status": "pass"},
                registry / "RELEASE_CHANNEL.generated.json": {
                    "status": "published",
                    "version": "run-20260624-080000",
                    "publishedAt": "2026-06-24T08:00:00Z",
                    "channel": "preview",
                    "supportabilityState": "preview_supported",
                },
            }
            for path, payload in receipts.items():
                path.write_text(json.dumps(payload) + "\n", encoding="utf-8")

            with mock.patch.object(module, "PUBLISHED_ROOT", published), \
                mock.patch.object(module, "COMPLETION_ROOT", completion), \
                mock.patch.object(module, "REGISTRY_ROOT", registry):
                payload = module.build_payload()

        self.assertEqual("fail", payload["status"])
        self.assertEqual("OPERABLE_RELEASE_BLOCKED", payload["verdict"])
        self.assertIn("public_edge_postdeploy_gate", payload["failures"])
        self.assertFalse(payload["checks"]["public_edge_postdeploy_gate"]["pass"])


if __name__ == "__main__":
    unittest.main()

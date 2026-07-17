from __future__ import annotations

import importlib.util
import io
import json
import os
import re
import shutil
import tempfile
import time
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "materialize_release_ready_receipt.py"
VERIFY_SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "release" / "verify_chummer6_release_ready.sh"


def load_module():
    spec = importlib.util.spec_from_file_location("materialize_release_ready_receipt", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.WORKSPACE_PORTAL_RELEASE_CHANNEL_CANDIDATES = ()
    module.CURRENT_AUXILIARY_RELEASE_RECEIPTS = ()
    module.RELEASE_VERIFIER_GATE_RECEIPTS = ()
    # Most unit tests below exercise release-ready aggregation independently of
    # the production Google OAuth receipt verifier.  Preserve the production
    # implementation for the dedicated binding tests while keeping legacy
    # fixtures from silently depending on whatever operator receipt happens to
    # be present in the checkout.
    module._production_google_oauth_receipt_validation_failures = (
        module.google_oauth_receipt_validation_failures
    )
    module.google_oauth_receipt_validation_failures = lambda _path: []
    module._test_release_execution_environment = {
        "CHUMMER_PUBLIC_BASE_URL": "https://chummer.run",
        "CHUMMER_RELEASE_READY_SKIP_GOOGLE_OAUTH_RUNTIME_REFRESH": "0",
        "CHUMMER_RELEASE_READY_SKIP_WINDOWS_RUNTIME_REFRESH": "0",
        "CHUMMER_RELEASE_READY_GATE_TIMEOUT_SECONDS": "900",
        "CHUMMER_RELEASE_READY_GUIDE_GATE_TIMEOUT_SECONDS": "1800",
        "CHUMMER_RELEASE_READY_GATE_KILL_AFTER_SECONDS": "30",
        "CHUMMER_PUBLIC_EDGE_PLAYWRIGHT_REUSE_MAX_AGE_HOURS": "24",
        "CHUMMER_PUBLIC_EDGE_TIMEOUT_SECONDS": "60",
        "PATH": module.TRUSTED_PATH,
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONNOUSERSITE": "1",
        "BASH_ENV": "",
        "ENV": "",
        "CDPATH": "",
        "PYTHONPATH": "",
        "PYTHONHOME": "",
        "NODE_PATH": "",
        "NODE_OPTIONS": "",
        "PYTHONSTARTUP": "",
        "PYTHONINSPECT": "",
        "LD_PRELOAD": "",
        "LD_LIBRARY_PATH": "",
    }
    module.current_release_execution_environment = lambda environment=None: {
        key: str((environment or module._test_release_execution_environment).get(key) or "")
        for key in module.RELEASE_EXECUTION_ENV_KEYS
    }
    module._production_authoritative_controller_environment = (
        module.authoritative_controller_environment
    )
    module.authoritative_controller_environment = lambda *_args, **kwargs: {
        **module._test_release_execution_environment,
        module.RELEASE_READY_MATERIALIZER_ACTIVE_ENV: "1",
        "CHUMMER_SKIP_CODEX_HANDOFF_MATERIALIZER": "1",
        "CHUMMER_ALLOW_UNSIGNED_PUBLIC_RELEASE": "1",
        module.SKIP_GOOGLE_OAUTH_RUNTIME_REFRESH_ENV: (
            "1"
            if kwargs.get("skip_google_oauth_runtime_refresh")
            else module._test_release_execution_environment[
                module.SKIP_GOOGLE_OAUTH_RUNTIME_REFRESH_ENV
            ]
        ),
        module.SKIP_WINDOWS_RUNTIME_REFRESH_ENV: (
            "1"
            if kwargs.get("skip_windows_runtime_refresh")
            else module._test_release_execution_environment[
                module.SKIP_WINDOWS_RUNTIME_REFRESH_ENV
            ]
        ),
    }
    return module


def passing_public_edge_postdeploy_payload(module) -> dict[str, object]:
    payload: dict[str, object] = {
        field: None for field in module.PUBLIC_EDGE_POSTDEPLOY_REQUIRED_FIELDS
    }
    payload.update(
        {
            "contractName": module.PUBLIC_EDGE_POSTDEPLOY_CONTRACT_NAME,
            "status": "pass",
            "pwaOfflineCacheStatus": "pass",
            "pwaOfflineCacheArtifactContract": "chummer.pwa_offline_cache.v2",
            "pwaOfflineCacheCacheVersion": "v17",
            "pwaOfflineCacheNavigationPolicy": "network_only",
            "pwaOfflineCachePrivateStateScope": "open_tab_only",
            "pwaOfflineCacheStaticPaths": [
                "/manifest.player.webmanifest",
                "/manifest.gm.webmanifest",
                "/mobile.css",
                "/mobile-turn-companion.js",
            ],
            "pwaOfflineCacheOfflineRoleFallbacks": [
                {
                    "role": "Player",
                    "path": "/mobile/player",
                    "status": 503,
                    "cache_control": "private, no-store",
                    "private_projection_restored": False,
                },
                {
                    "role": "GameMaster",
                    "path": "/mobile/gm",
                    "status": 503,
                    "cache_control": "private, no-store",
                    "private_projection_restored": False,
                },
            ],
            "pwaOfflineCacheQueryBearingRequestsCached": False,
            "pwaOfflineCachePrivateNavigationCached": False,
            "pwaOfflineCachePrivateApiCached": False,
            "pwaOfflineCachePersonalizedLedgerCached": False,
            "pwaOfflineCacheLegacyPrivateCachePrefixesPurged": [
                "chummer-shell-play-shell-",
                "chummer-media-play-shell-",
                "chummer-media-meta-play-shell-",
            ],
            "pwaOfflineCacheUnrelatedCachePreserved": True,
            "frontdoorNavigationStatus": "pass",
            "frontdoorNavigationMobileArtifactContract": "chummer.frontdoor_mobile_launch.v2",
            "frontdoorNavigationAnchorArtifactContract": "chummer.frontdoor_mobile_anchor_redirect.v2",
            "frontdoorNavigationFinalUrl": "https://chummer.run/mobile/player",
            "frontdoorNavigationGmRoute": "/mobile/gm",
            "frontdoorNavigationGmFinalUrl": "https://chummer.run/mobile/gm",
            "frontdoorNavigationAnchorEntryUrl": "https://chummer.run/#turn-runsite-card",
            "frontdoorNavigationAnchorFinalUrl": "https://chummer.run/mobile/player#turn-runsite-card",
            "frontdoorNavigationAnchorFinalPath": "/mobile/player",
            "frontdoorNavigationAnchorFinalHash": "#turn-runsite-card",
            "frontdoorNavigationAnchorFailure": "",
            "frontdoorNavigationPlayerSessionHandoffUrl": "https://chummer.run/mobile/player?sessionId=[redacted]&role=Player",
            "frontdoorNavigationGmSessionHandoffUrl": "https://chummer.run/mobile/gm?sessionId=[redacted]&role=GameMaster",
        }
    )
    for field in (
        "frontdoorNavigationPrivateIdentityRedacted",
        "frontdoorNavigationVisiblePlayerUrlPrivateIdentityAbsent",
        "frontdoorNavigationPlayerSessionContextPresent",
        "frontdoorNavigationPlayerDeviceContextPresent",
        "frontdoorNavigationPlayerSessionHandoffPrivateIdentityRedacted",
        "frontdoorNavigationGmRouteSessionIdPresent",
        "frontdoorNavigationGmRoutePrivateIdentityRedacted",
        "frontdoorNavigationVisibleGmUrlPrivateIdentityAbsent",
        "frontdoorNavigationGmSessionContextPresent",
        "frontdoorNavigationGmDeviceContextPresent",
        "frontdoorNavigationGmSessionHandoffPrivateIdentityRedacted",
        "frontdoorNavigationAnchorPrivateIdentityRedacted",
        "frontdoorNavigationAnchorVisibleUrlPrivateIdentityAbsent",
        "frontdoorNavigationAnchorSessionContextPresent",
        "frontdoorNavigationAnchorDeviceContextPresent",
    ):
        payload[field] = True
    return payload


def popen_with_output(process: mock.Mock, stdout: str, stderr: str = ""):
    process.wait.return_value = 0

    def fake_popen(*_args, **kwargs):
        kwargs["stdout"].write(stdout.encode("utf-8"))
        kwargs["stdout"].flush()
        kwargs["stderr"].write(stderr.encode("utf-8"))
        kwargs["stderr"].flush()
        return process

    return fake_popen


def passing_verifier_evidence(module) -> dict[str, object]:  # noqa: ANN001
    cached = getattr(module, "_test_passing_verifier_evidence", None)
    if isinstance(cached, dict):
        return cached
    python_path = Path(module.sys.executable).resolve()
    bash_path = Path("/usr/bin/bash").resolve()
    timeout_path = Path("/usr/bin/timeout").resolve()
    gate_specs = [
        [
            gate_name,
            f"{python_path} {SCRIPT_PATH}",
            str(Path.cwd()),
            "900",
            str(SCRIPT_PATH),
        ]
        for gate_name in module.REQUIRED_RELEASE_VERIFIER_GATES
    ]
    plan = module.build_release_execution_plan(
        gate_specs,
        [
            ["bash_lc", str(bash_path)],
            ["python3", str(python_path)],
            ["timeout", str(timeout_path)],
        ],
        [str(Path.cwd())],
        environment=module._test_release_execution_environment,
        run_nonce="a" * 64,
    )
    start_binding = module.current_release_verifier_replay_binding(
        execution_plan=plan,
        binding_phase="start",
    )
    lines = [
        module.RELEASE_EXECUTION_PLAN_PREFIX
        + json.dumps(plan, sort_keys=True, separators=(",", ":")),
        module.RELEASE_VERIFIER_START_BINDING_PREFIX
        + json.dumps(start_binding, sort_keys=True, separators=(",", ":")),
    ]
    execution_bindings: list[dict[str, object]] = []
    for gate_name in module.REQUIRED_RELEASE_VERIFIER_GATES:
        lines.append(f"START {gate_name} timeout=900s")
        prebinding = module.current_gate_execution_prebinding(
            plan,
            gate_name,
            start_binding,
        )
        execution_binding = module.complete_gate_execution_binding(plan, prebinding)
        execution_bindings.append(execution_binding)
        lines.append(
            module.RELEASE_GATE_EXECUTION_BINDING_PREFIX
            + json.dumps(execution_binding, sort_keys=True, separators=(",", ":"))
        )
        lines.append(
            f"PASS {gate_name} execution_binding_sha256="
            f"{execution_binding['binding_sha256']}"
        )
    final_binding = module.current_release_verifier_replay_binding(
        execution_plan=plan,
        binding_phase="final",
        execution_bindings=execution_bindings,
        direct_receipt_bindings=[],
    )
    lines.extend(
        [
            module.RELEASE_VERIFIER_REPLAY_BINDING_PREFIX
            + json.dumps(final_binding, sort_keys=True, separators=(",", ":")),
            "RELEASE READY",
        ]
    )
    evidence: dict[str, object] = {
        "plan": plan,
        "start_binding": start_binding,
        "execution_bindings": execution_bindings,
        "receipt_bindings": [],
        "final_binding": final_binding,
        "stdout": "\n".join(lines) + "\n",
    }
    module._test_passing_verifier_evidence = evidence
    return evidence


def passing_verifier_output(module) -> str:  # noqa: ANN001
    return str(passing_verifier_evidence(module)["stdout"])


def live_controller_result(
    module,  # noqa: ANN001
    *,
    stdout: str | None = None,
    stderr: str = "",
    returncode: int = 0,
    timed_out: bool = False,
) -> dict[str, object]:
    """Test-only in-memory controller boundary; never a replay authority path."""

    selected_stdout = passing_verifier_output(module) if stdout is None else stdout
    validated: dict[str, object] = {}
    if returncode == 0 and passing_verifier_output(module) in selected_stdout:
        evidence = passing_verifier_evidence(module)
        validated = {
            **evidence["final_binding"],
            "start_binding": evidence["start_binding"],
            "run_start_generated_at_utc": evidence["start_binding"]["generated_at_utc"],
            "gate_receipt_bindings": evidence["receipt_bindings"],
            "gate_execution_bindings": evidence["execution_bindings"],
            "execution_plan": evidence["plan"],
        }
    return {
        "authority_scope": module.AUTHORITATIVE_CONTROLLER_SCOPE,
        "authoritative": True,
        "diagnostic": False,
        "test_only": False,
        "returncode": returncode,
        "timed_out": timed_out,
        "stdout": selected_stdout,
        "stderr": stderr,
        "validated_release_binding": validated,
        "external_write_authorized": False,
    }


class MaterializeReleaseReadyReceiptTests(unittest.TestCase):
    def test_release_ready_receipt_materializes_into_current_repo(self) -> None:
        module = load_module()

        self.assertEqual(SCRIPT_PATH.parents[1], module.RUN_SERVICES_ROOT)
        self.assertEqual(
            SCRIPT_PATH.parents[1] / "scripts" / "verify_chummer6_release_ready.sh",
            module.VERIFY_SCRIPT,
        )
        self.assertEqual(
            SCRIPT_PATH.parents[1] / ".codex-studio" / "published" / "RELEASE_READY.generated.json",
            module.OUTPUT_PATH,
        )

    def test_repo_local_verifier_runs_windows_precheck_before_desktop_gold(self) -> None:
        module = load_module()
        text = module.VERIFY_SCRIPT.read_text(encoding="utf-8")

        self.assertIn("CHUMMER_RELEASE_READY_STOP_ON_PRECHECK_FAILURE", text)
        self.assertTrue((module.RUN_SERVICES_ROOT / "scripts" / "verify_flagship_product_readiness_gate.py").is_file())
        self.assertIn("verify_flagship_product_readiness_gate.py", text)
        self.assertLess(
            text.index("verify_windows_installer_visual_audit"),
            text.index("verify_chummer6_desktop_gold"),
        )

    def test_main_writes_pass_receipt_from_successful_release_verifier(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="release-ready-receipt-") as temp_dir:
            output_path = Path(temp_dir) / "RELEASE_READY.generated.json"

            process = mock.Mock(pid=1234, returncode=0)
            process.communicate.return_value = ("RELEASE READY\n", "")

            with (
                mock.patch.object(module, "OUTPUT_PATH", output_path),
                mock.patch.object(module, "current_release_truth_launch_blockers", return_value=[]),
                mock.patch.object(module, "source_binding_failures", return_value=[]),
                mock.patch.object(module, "current_git_head", return_value="abc123"),
                mock.patch.object(module, "resolve_workspace_root", return_value=module.ROOT),
                mock.patch.object(module.subprocess, "Popen", return_value=process) as popen,
            ):
                result = module.main()

            self.assertEqual(0, result)
            popen_env = popen.call_args.kwargs["env"]
            self.assertEqual(str(module.RUN_SERVICES_ROOT), popen_env["CHUMMER_RUN_SERVICES_ROOT"])
            self.assertEqual(str(module.ROOT), popen_env["CHUMMER_WORKSPACE_ROOT"])
            self.assertTrue(popen_env["CHUMMER_PUBLIC_EDGE_EXPECTED_HEAD"])
            payload = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual("pass", payload["status"])
            self.assertEqual("RELEASE_READY", payload["verdict"])
            self.assertEqual(0, payload["returncode"])
            self.assertFalse(payload["timed_out"])
            self.assertEqual(module.TIMEOUT_SECONDS, payload["timeout_seconds"])
            self.assertEqual([], payload["failed_gates"])
            self.assertEqual([], payload["release_truth_blockers"])
            self.assertTrue(payload["source_binding"]["pass"])
            self.assertTrue(payload["source_binding"]["verifier_accepts_current_root"])
            self.assertIn("CHUMMER_PUBLIC_EDGE_EXPECTED_HEAD=", payload["command"])

    def test_main_writes_fail_receipt_when_release_verifier_times_out(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="release-ready-timeout-") as temp_dir:
            output_path = Path(temp_dir) / "RELEASE_READY.generated.json"
            timeout = module.subprocess.TimeoutExpired(
                cmd=["bash", str(module.VERIFY_SCRIPT)],
                timeout=module.TIMEOUT_SECONDS,
                output=b"RUN verify_live_surface_parity\nFAIL verify_live_surface_parity\nstill running\n",
                stderr=b"",
            )

            process = mock.Mock(pid=1234, returncode=None)
            process.communicate.side_effect = [
                timeout,
                (b"RUN verify_live_surface_parity\nFAIL verify_live_surface_parity\nstill running\n", b""),
            ]

            with (
                mock.patch.object(module, "OUTPUT_PATH", output_path),
                mock.patch.object(module, "current_release_truth_launch_blockers", return_value=[]),
                mock.patch.object(module, "source_binding_failures", return_value=[]),
                mock.patch.object(module, "current_git_head", return_value="abc123"),
                mock.patch.object(module, "resolve_workspace_root", return_value=module.ROOT),
                mock.patch.object(module.subprocess, "Popen", return_value=process),
                mock.patch.object(module.os, "killpg") as killpg,
            ):
                result = module.main()

            self.assertEqual(0, result)
            payload = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual("fail", payload["status"])
            self.assertEqual("NOT_RELEASE_READY", payload["verdict"])
            self.assertEqual(124, payload["returncode"])
            self.assertTrue(payload["timed_out"])
            self.assertEqual(["verify_live_surface_parity"], payload["failed_gates"])
            self.assertIn(f"verify_release_ready timed out after {module.TIMEOUT_SECONDS}s", payload["failures"])
            self.assertIn("last release-ready gate before timeout: verify_live_surface_parity", payload["failures"])
            self.assertIn("FAIL verify_live_surface_parity", payload["failures"])
            self.assertEqual(["RUN verify_live_surface_parity"], payload["progress"])

    def test_main_writes_fail_receipt_when_verifier_targets_wrong_repo(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="release-ready-source-binding-") as temp_dir:
            output_path = Path(temp_dir) / "RELEASE_READY.generated.json"
            failure = "release verifier is bound to a different checkout"

            with (
                mock.patch.object(module, "OUTPUT_PATH", output_path),
                mock.patch.object(module, "current_release_truth_launch_blockers", return_value=[]),
                mock.patch.object(module, "source_binding_failures", return_value=[failure]),
                mock.patch.object(module, "current_git_head", return_value="abc123"),
                mock.patch.object(module, "resolve_workspace_root", return_value=module.ROOT),
                mock.patch.object(module.subprocess, "Popen") as popen,
            ):
                result = module.main()

            self.assertEqual(0, result)
            popen.assert_not_called()
            payload = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual("fail", payload["status"])
            self.assertEqual("NOT_RELEASE_READY", payload["verdict"])
            self.assertEqual(78, payload["returncode"])
            self.assertFalse(payload["timed_out"])
            self.assertIn(failure, payload["failures"])
            self.assertFalse(payload["source_binding"]["pass"])

    def test_main_surfaces_release_truth_blockers_when_release_verifier_fails(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="release-ready-truth-") as temp_dir:
            output_path = Path(temp_dir) / "RELEASE_READY.generated.json"

            process = mock.Mock(pid=1234, returncode=1)
            process.communicate.return_value = (
                "RUN verify_release_channel\n"
                "FAIL verify_release_channel: release channel channel is preview, not a flagship stable lane\n",
                "",
            )

            with (
                mock.patch.object(module, "OUTPUT_PATH", output_path),
                mock.patch.object(
                    module,
                    "current_release_truth_launch_blockers",
                    return_value=[
                        "release channel channel is preview, not a flagship stable lane",
                        "google oauth operator evidence is still missing: /tmp/operator-evidence.json",
                    ],
                ),
                mock.patch.object(module, "source_binding_failures", return_value=[]),
                mock.patch.object(module, "current_git_head", return_value="abc123"),
                mock.patch.object(module, "resolve_workspace_root", return_value=module.ROOT),
                mock.patch.object(module.subprocess, "Popen", return_value=process),
            ):
                result = module.main()

            self.assertEqual(0, result)
            payload = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual("fail", payload["status"])
            self.assertEqual(["verify_release_channel"], payload["failed_gates"])
            self.assertEqual(
                [
                    "release channel channel is preview, not a flagship stable lane",
                    "google oauth operator evidence is still missing: /tmp/operator-evidence.json",
                ],
                payload["release_truth_blockers"],
            )
            self.assertEqual(2, payload["release_truth_blocker_count"])

    def test_source_binding_allows_override_aware_verifier(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="release-ready-binding-aware-") as temp_dir:
            verifier = Path(temp_dir) / "verify.sh"
            verifier.write_text(
                'run_services_root="${CHUMMER_RUN_SERVICES_ROOT:-$root/chummer.run-services}"\n',
                encoding="utf-8",
            )

            with mock.patch.object(module, "VERIFY_SCRIPT", verifier):
                self.assertEqual([], module.source_binding_failures())

    def test_resolve_workspace_root_prefers_shared_workspace_when_local_siblings_are_missing(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="release-ready-workspace-root-") as temp_dir:
            local_root = Path(temp_dir) / "local"
            shared_root = Path(temp_dir) / "shared"
            (shared_root / "chummer-hub-registry" / "scripts" / "release").mkdir(parents=True, exist_ok=True)
            (shared_root / "chummer-hub-registry" / "scripts" / "release" / "verify_release_channel.sh").write_text(
                "#!/usr/bin/env bash\n",
                encoding="utf-8",
            )

            with (
                mock.patch.object(module, "ROOT", local_root),
                mock.patch.object(module, "SHARED_WORKSPACE_ROOT", shared_root),
            ):
                self.assertEqual(shared_root, module.resolve_workspace_root())


if __name__ == "__main__":
    unittest.main()

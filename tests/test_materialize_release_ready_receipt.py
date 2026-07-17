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
    module._production_source_binding_failures = module.source_binding_failures
    module._production_current_git_head = module.current_git_head
    module._test_release_execution_environment = {
        "CHUMMER_PUBLIC_BASE_URL": "https://chummer.run",
        "CHUMMER_PUBLIC_EDGE_EXPECTED_HEAD": "a" * 40,
        "CHUMMER_RUN_SERVICES_ROOT": str(module.RUN_SERVICES_ROOT),
        "CHUMMER_BLAZOR_REQUIRE_LOCAL_E2E": "0",
        "CHUMMER_BLAZOR_REQUIRE_SELF_HOST_E2E": "0",
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
    external_write_authorized: bool = False,
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
        "external_write_authorized": external_write_authorized,
    }


class MaterializeReleaseReadyReceiptTests(unittest.TestCase):
    def test_release_controller_outputs_and_binds_the_current_checkout(self) -> None:
        module = load_module()

        self.assertEqual(SCRIPT_PATH.parents[1], module.RUN_SERVICES_ROOT)
        self.assertEqual(SCRIPT_PATH.parents[2], module.ROOT)
        self.assertEqual(
            module.RUN_SERVICES_ROOT
            / ".codex-studio"
            / "published"
            / "RELEASE_READY.generated.json",
            module.OUTPUT_PATH,
        )
        self.assertEqual(
            module.ROOT / "scripts" / "release" / "verify_chummer6_release_ready.sh",
            module.VERIFY_SCRIPT,
        )
        self.assertTrue(
            module.supported_release_controller_command().startswith(
                f"CHUMMER_RUN_SERVICES_ROOT={module.RUN_SERVICES_ROOT} "
            )
        )

    def test_shared_launcher_must_dispatch_the_environment_selected_checkout(self) -> None:
        module = load_module()
        verify = module._production_source_binding_failures
        with tempfile.TemporaryDirectory(prefix="release-controller-source-binding-") as temp_dir:
            launcher = Path(temp_dir) / "verify_chummer6_release_ready.sh"
            launcher.write_text(
                module.AUTHORITATIVE_RELEASE_LAUNCHER_SOURCE,
                encoding="utf-8",
            )
            self.assertEqual([], verify(launcher))

            launcher.write_text(
                """#!/usr/bin/python3 -I
from pathlib import Path
ROOT = Path("/docker/chummercomplete")
MATERIALIZER = ROOT / "chummer.run-services/scripts/materialize_release_ready_receipt.py"
""",
                encoding="utf-8",
            )
            failures = verify(launcher)

        self.assertTrue(any("RUN_SERVICES_ROOT" in failure for failure in failures))
        self.assertTrue(any("legacy-checkout-bound" in failure for failure in failures))

    def test_shared_launcher_rejects_unsafe_sanitizer_body(self) -> None:
        module = load_module()
        verify = module._production_source_binding_failures
        with tempfile.TemporaryDirectory(prefix="release-controller-unsafe-sanitizer-") as temp_dir:
            launcher = Path(temp_dir) / "verify_chummer6_release_ready.sh"
            unsafe = module.AUTHORITATIVE_RELEASE_LAUNCHER_SOURCE.replace(
                "    ambient = dict(os.environ)\n",
                "    return dict(os.environ)\n    ambient = dict(os.environ)\n",
                1,
            )
            launcher.write_text(unsafe, encoding="utf-8")

            failures = verify(launcher)

        self.assertTrue(any("template exactly" in failure for failure in failures))

    def test_shared_launcher_rejects_shadowed_imports_and_builtins(self) -> None:
        module = load_module()
        verify = module._production_source_binding_failures
        with tempfile.TemporaryDirectory(prefix="release-controller-shadowed-import-") as temp_dir:
            launcher = Path(temp_dir) / "verify_chummer6_release_ready.sh"
            shadowed = module.AUTHORITATIVE_RELEASE_LAUNCHER_SOURCE.replace(
                "from pathlib import Path\n",
                "from pathlib import Path\nos = object()\nsys = object()\nPath = object\nstr = repr\n",
                1,
            )
            launcher.write_text(shadowed, encoding="utf-8")

            failures = verify(launcher)

        self.assertTrue(any("template exactly" in failure for failure in failures))

    def test_shared_launcher_rejects_extra_launch_side_effects(self) -> None:
        module = load_module()
        verify = module._production_source_binding_failures
        with tempfile.TemporaryDirectory(prefix="release-controller-extra-launch-") as temp_dir:
            launcher = Path(temp_dir) / "verify_chummer6_release_ready.sh"
            mutated = module.AUTHORITATIVE_RELEASE_LAUNCHER_SOURCE.replace(
                "    os.chdir(RUN_SERVICES_ROOT)\n",
                "    environment.update(os.environ)\n    os.chdir(RUN_SERVICES_ROOT)\n",
                1,
            )
            launcher.write_text(mutated, encoding="utf-8")

            failures = verify(launcher)

        self.assertTrue(any("template exactly" in failure for failure in failures))

    def test_shared_launcher_rejects_decoy_bindings_around_a_legacy_execve(self) -> None:
        module = load_module()
        verify = module._production_source_binding_failures
        with tempfile.TemporaryDirectory(prefix="release-controller-decoy-dispatch-") as temp_dir:
            launcher = Path(temp_dir) / "verify_chummer6_release_ready.sh"
            launcher.write_text(
                """#!/usr/bin/python3 -I
import os
import sys
from pathlib import Path
RUN_SERVICES_ROOT = Path(os.environ["CHUMMER_RUN_SERVICES_ROOT"]).resolve()
MATERIALIZER = RUN_SERVICES_ROOT / "scripts" / "materialize_release_ready_receipt.py"
TRUSTED_PYTHON = "/usr/bin/python3"
def controller_environment():
    return {}
def launch():
    environment = controller_environment()
    os.execve(
        TRUSTED_PYTHON,
        [
            TRUSTED_PYTHON,
            "-I",
            "/docker/chummercomplete/chummer.run-services/scripts/materialize_release_ready_receipt.py",
            "--run-authoritative-controller",
            *sys.argv[1:],
        ],
        environment,
    )
launch()
""",
                encoding="utf-8",
            )

            failures = verify(launcher)

        self.assertTrue(any("str(MATERIALIZER)" in failure for failure in failures))
        self.assertTrue(
            any("executable dispatch is legacy-checkout-bound" in failure for failure in failures)
        )

    def test_shared_launcher_rejects_unsanitized_or_non_authoritative_execve(self) -> None:
        module = load_module()
        verify = module._production_source_binding_failures
        with tempfile.TemporaryDirectory(prefix="release-controller-unsafe-dispatch-") as temp_dir:
            launcher = Path(temp_dir) / "verify_chummer6_release_ready.sh"
            launcher.write_text(
                """#!/usr/bin/python3 -I
import os
import sys
from pathlib import Path
RUN_SERVICES_ROOT = Path(os.environ["CHUMMER_RUN_SERVICES_ROOT"]).resolve()
MATERIALIZER = RUN_SERVICES_ROOT / "scripts" / "materialize_release_ready_receipt.py"
TRUSTED_PYTHON = "/usr/bin/python3"
def controller_environment():
    return {}
def launch():
    environment = dict(os.environ)
    os.execve(
        TRUSTED_PYTHON,
        [TRUSTED_PYTHON, "-I", str(MATERIALIZER), *sys.argv[1:]],
        environment,
    )
launch()
""",
                encoding="utf-8",
            )

            failures = verify(launcher)

        self.assertTrue(any("--run-authoritative-controller" in failure for failure in failures))
        self.assertTrue(
            any("environment must come directly" in failure for failure in failures)
        )

    def test_shared_launcher_rejects_materializer_shadowing_in_launch(self) -> None:
        module = load_module()
        verify = module._production_source_binding_failures
        with tempfile.TemporaryDirectory(prefix="release-controller-shadowed-dispatch-") as temp_dir:
            launcher = Path(temp_dir) / "verify_chummer6_release_ready.sh"
            launcher.write_text(
                """#!/usr/bin/python3 -I
import os
import sys
from pathlib import Path
RUN_SERVICES_ROOT = Path(os.environ["CHUMMER_RUN_SERVICES_ROOT"]).resolve()
MATERIALIZER = RUN_SERVICES_ROOT / "scripts" / "materialize_release_ready_receipt.py"
TRUSTED_PYTHON = "/usr/bin/python3"
def controller_environment():
    return {}
def launch(MATERIALIZER="/docker/chummercomplete/chummer.run-services/scripts/materialize_release_ready_receipt.py"):
    environment = controller_environment()
    os.execve(
        TRUSTED_PYTHON,
        [
            TRUSTED_PYTHON,
            "-I",
            str(MATERIALIZER),
            "--run-authoritative-controller",
            *sys.argv[1:],
        ],
        environment,
    )
launch()
""",
                encoding="utf-8",
            )

            failures = verify(launcher)

        self.assertTrue(any("must not be shadowed" in failure for failure in failures))
        self.assertTrue(any("legacy-checkout-bound" in failure for failure in failures))

    def test_controller_environment_binds_current_checkout_and_git_head(self) -> None:
        module = load_module()
        with (
            mock.patch.object(module, "source_binding_failures", return_value=[]),
            mock.patch.object(module, "current_git_head", return_value="a" * 40),
        ):
            sanitized = module._production_authoritative_controller_environment(
                {
                    "PATH": module.TRUSTED_PATH,
                    "PYTHONDONTWRITEBYTECODE": "1",
                }
            )

        self.assertEqual(
            str(module.RUN_SERVICES_ROOT),
            sanitized["CHUMMER_RUN_SERVICES_ROOT"],
        )
        self.assertEqual("a" * 40, sanitized["CHUMMER_PUBLIC_EDGE_EXPECTED_HEAD"])
        self.assertEqual(
            sanitized["CHUMMER_PUBLIC_EDGE_EXPECTED_HEAD"],
            module.current_release_execution_environment(sanitized)[
                "CHUMMER_PUBLIC_EDGE_EXPECTED_HEAD"
            ],
        )

    def test_bad_launcher_fails_before_head_or_controller_plan_construction(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="release-controller-early-binding-") as temp_dir:
            output_path = Path(temp_dir) / "RELEASE_READY.generated.json"
            with (
                mock.patch.object(module, "OUTPUT_PATH", output_path),
                mock.patch.object(
                    module,
                    "authoritative_controller_environment",
                    side_effect=lambda **kwargs: (
                        module._production_authoritative_controller_environment(
                            {"PATH": module.TRUSTED_PATH},
                            **kwargs,
                        )
                    ),
                ),
                mock.patch.object(
                    module,
                    "source_binding_failures",
                    return_value=["shared release launcher executable dispatch is legacy-checkout-bound"],
                ),
                mock.patch.object(module, "current_git_head") as current_head,
                mock.patch.object(
                    module,
                    "run_authoritative_release_controller",
                ) as controller,
            ):
                result = module.main()

            payload = json.loads(output_path.read_text(encoding="utf-8"))

        self.assertEqual(78, result)
        current_head.assert_not_called()
        controller.assert_not_called()
        self.assertEqual("fail", payload["status"])
        self.assertFalse(payload["authoritative"])
        self.assertIn("legacy-checkout-bound", payload["materialization_error"]["reason"])

    def test_public_edge_activation_blocker_is_projected_as_deployment_artifact_and_next_action(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="release-ready-public-edge-activation-") as temp_dir:
            root = Path(temp_dir)
            blockers_path = root / "RELEASE_BLOCKERS.generated.json"
            blockers_path.write_text(
                json.dumps(
                    {
                        "generated_at": "2026-07-13T08:00:00Z",
                        "root_blockers": [
                            {
                                "id": "release_truth:public_edge_postdeploy_gate",
                                "blocker_class": "deployment_activation_proof_required",
                                "local_surface_regression": False,
                                "activation_authority_required": True,
                                "post_activation_proof_required": True,
                                "runtime_overlay_root": "/overlay/active/app",
                                "staged_overlay_root": "/overlay/next/app",
                                "staged_overlay_receipt_path": "/published/overlay-stage.json",
                                "staged_overlay_status": "pass",
                                "activation_transaction_journal_path": "/overlay/.activation.json",
                                "activation_transaction_journal_exists": False,
                                "external_prerequisite": "Obtain explicit activation authority.",
                                "verify_command": "python3 verify-public-edge.py",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            published = root / "published"
            published.mkdir()
            with (
                mock.patch.object(module, "RELEASE_BLOCKERS_JSON", blockers_path),
                mock.patch.object(module, "PUBLISHED_ROOT", published),
                mock.patch.object(module, "CURRENT_AUXILIARY_RELEASE_RECEIPTS", ()),
            ):
                artifacts = module.current_blocking_gate_artifacts(
                    refresh_windows_runtime_receipts=False
                )

        public_edge = artifacts["public_edge_postdeploy_gate"]
        self.assertEqual("deployment_activation_proof_required", public_edge["blocker_class"])
        self.assertFalse(public_edge["local_surface_regression"])
        self.assertTrue(public_edge["activation_authority_required"])
        self.assertTrue(public_edge["post_activation_proof_required"])
        self.assertEqual("/overlay/next/app", public_edge["staging_root"])
        self.assertFalse(public_edge["activation_transaction_journal_exists"])

        actions = module.release_ready_next_actions(artifacts, {}, artifacts["release_truth_root"])
        self.assertTrue(any("Obtain explicit public-edge activation authority" in item for item in actions))
        self.assertTrue(any("do not restamp" in item for item in actions))

    def test_synthetic_complete_gate_transcript_is_diagnostic_and_never_authoritative(self) -> None:
        module = load_module()
        raw = passing_verifier_output(module).encode("utf-8")
        diagnostic = module.validate_release_verifier_replay_binding(raw.decode("utf-8"))

        self.assertFalse(diagnostic["authoritative"])
        self.assertTrue(diagnostic["diagnostic"])
        self.assertTrue(diagnostic["test_only"])
        self.assertEqual(module.DIAGNOSTIC_AUTHORITY_SCOPE, diagnostic["authority_scope"])

        with tempfile.TemporaryDirectory(prefix="release-ready-replay-") as temp_dir:
            path = Path(temp_dir) / "verifier.stdout"
            path.write_bytes(raw)
            path.chmod(0o600)
            with self.assertRaisesRegex(
                ValueError,
                "diagnostic-only; detached signed execution-attestation trust is not enrolled",
            ):
                module.load_replayed_release_verifier_output(
                    path,
                    module.hashlib.sha256(raw).hexdigest(),
                )

    def test_pure_binding_cli_is_explicitly_diagnostic_and_test_only(self) -> None:
        module = load_module()
        stdout = io.StringIO()
        with (
            mock.patch.object(
                module,
                "current_release_verifier_replay_binding",
                return_value={"synthetic": "binding"},
            ),
            redirect_stdout(stdout),
        ):
            result = module.main(["--emit-release-verifier-binding"])

        payload = json.loads(stdout.getvalue())
        self.assertEqual(0, result)
        self.assertFalse(payload["authoritative"])
        self.assertTrue(payload["diagnostic"])
        self.assertTrue(payload["test_only"])
        self.assertEqual(module.DIAGNOSTIC_AUTHORITY_SCOPE, payload["authority_scope"])
        self.assertEqual({"synthetic": "binding"}, payload["artifact"])

    def test_hash_bound_replay_rejects_mismatch_incomplete_and_duplicate_matrices(self) -> None:
        module = load_module()
        complete = passing_verifier_output(module)
        first_gate = module.REQUIRED_RELEASE_VERIFIER_GATES[0]
        fixtures = {
            "incomplete": "RELEASE READY\n",
            "duplicate": complete.replace(
                f"START {first_gate} timeout=900s\n",
                f"START {first_gate} timeout=900s\nSTART {first_gate} timeout=900s\n",
                1,
            ),
        }
        with tempfile.TemporaryDirectory(prefix="release-ready-replay-invalid-") as temp_dir:
            for name, text in fixtures.items():
                path = Path(temp_dir) / f"{name}.stdout"
                raw = text.encode("utf-8")
                path.write_bytes(raw)
                path.chmod(0o600)
                with self.subTest(name=name), self.assertRaises(ValueError):
                    module.load_replayed_release_verifier_output(
                        path,
                        module.hashlib.sha256(raw).hexdigest(),
                    )

            mismatch = Path(temp_dir) / "mismatch.stdout"
            mismatch.write_text("RELEASE READY\n", encoding="utf-8")
            mismatch.chmod(0o600)
            with self.assertRaisesRegex(ValueError, "SHA-256 mismatch"):
                module.load_replayed_release_verifier_output(mismatch, "0" * 64)

    def test_hash_bound_replay_rejects_release_manifest_drift_after_capture(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="release-ready-replay-drift-") as temp_dir:
            root = Path(temp_dir)
            registry = root / "registry"
            registry.mkdir()
            manifest_path = registry / "RELEASE_CHANNEL.generated.json"
            verifier_dir = root / "verifier"
            verifier_dir.mkdir()
            transcript_dir = root / "transcripts"
            transcript_dir.mkdir()
            verifier_path = verifier_dir / "verify-release.sh"
            published_at = module.now_iso()
            verifier_path.write_text("#!/usr/bin/env bash\n", encoding="utf-8")
            manifest_path.write_text(
                json.dumps(
                    {
                        "status": "published",
                        "version": "run-one",
                        "channel": "preview",
                        "supportabilityState": "review_required",
                        "rolloutState": "public_release_review_required",
                        "publishedAt": published_at,
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            with (
                mock.patch.object(module, "REGISTRY_PUBLISHED_ROOT", registry),
                mock.patch.object(module, "VERIFY_SCRIPT", verifier_path),
            ):
                transcript = transcript_dir / "verifier.stdout"
                raw = passing_verifier_output(module).encode("utf-8")
                transcript.write_bytes(raw)
                transcript.chmod(0o600)

                manifest_path.write_text(
                    json.dumps(
                        {
                            "status": "published",
                            "version": "run-two",
                            "channel": "preview",
                            "supportabilityState": "review_required",
                            "rolloutState": "public_release_review_required",
                            "publishedAt": published_at,
                        }
                    )
                    + "\n",
                    encoding="utf-8",
                )
                with self.assertRaisesRegex(ValueError, "does not match current truth"):
                    module.load_replayed_release_verifier_output(
                        transcript,
                        module.hashlib.sha256(raw).hexdigest(),
                    )

    def test_execution_plan_rejects_incomplete_compound_entrypoint_coverage(self) -> None:
        module = load_module()
        python_path = Path(module.sys.executable).resolve()
        bash_path = Path("/usr/bin/bash").resolve()
        timeout_path = Path("/usr/bin/timeout").resolve()
        with tempfile.TemporaryDirectory(prefix="release-plan-compound-coverage-") as temp_dir:
            root = Path(temp_dir)
            first = root / "first.py"
            second = root / "second.py"
            first.write_text("print('first')\n", encoding="utf-8")
            second.write_text("print('second')\n", encoding="utf-8")
            gate_specs = [
                [
                    gate_name,
                    (
                        f"{python_path} {first} && {python_path} {second}"
                        if index == 0
                        else f"{python_path} {first}"
                    ),
                    str(Path.cwd()),
                    "900",
                    str(first),
                ]
                for index, gate_name in enumerate(module.REQUIRED_RELEASE_VERIFIER_GATES)
            ]
            with self.assertRaisesRegex(ValueError, "literal code paths are not exactly covered"):
                module.build_release_execution_plan(
                    gate_specs,
                    [
                        ["bash_lc", str(bash_path)],
                        ["python3", str(python_path)],
                        ["timeout", str(timeout_path)],
                    ],
                    [str(root)],
                    environment=module._test_release_execution_environment,
                )

    def test_execution_binding_rejects_entrypoint_changed_and_restored_during_gate(self) -> None:
        module = load_module()
        python_path = Path(module.sys.executable).resolve()
        bash_path = Path("/usr/bin/bash").resolve()
        timeout_path = Path("/usr/bin/timeout").resolve()
        with tempfile.TemporaryDirectory(prefix="release-plan-change-restore-") as temp_dir:
            root = Path(temp_dir)
            entrypoint = root / "gate.py"
            original = b"print('trusted gate')\n"
            entrypoint.write_bytes(original)
            original_stat = entrypoint.stat()
            gate_specs = [
                [
                    gate_name,
                    f"{python_path} {entrypoint}",
                    str(Path.cwd()),
                    "900",
                    str(entrypoint),
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
                [str(root)],
                environment=module._test_release_execution_environment,
                run_nonce="c" * 64,
            )
            start_binding = module.current_release_verifier_replay_binding(
                execution_plan=plan,
                binding_phase="start",
            )
            gate_name = "verify_package_boundaries"
            prebinding = module.current_gate_execution_prebinding(
                plan,
                gate_name,
                start_binding,
            )
            entrypoint.write_bytes(b"print('substituted gate')\n")
            entrypoint.write_bytes(original)
            module.os.utime(
                entrypoint,
                ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns),
            )
            self.assertNotEqual(
                prebinding["execution_inputs"][-1]["identity"]["ctime_ns"],
                entrypoint.stat().st_ctime_ns,
            )
            with self.assertRaisesRegex(ValueError, "entrypoint drifted|changed during gate"):
                module.complete_gate_execution_binding(plan, prebinding)

    def test_execution_plan_rejects_unsafe_environment_and_symlink_ancestor(self) -> None:
        module = load_module()
        unsafe = dict(module._test_release_execution_environment)
        unsafe["PYTHONPATH"] = "/tmp/injected"
        with self.assertRaisesRegex(ValueError, "PYTHONPATH must be unset"):
            module.validate_release_execution_environment(unsafe)
        unsafe = dict(module._test_release_execution_environment)
        unsafe["CHUMMER_PUBLIC_BASE_URL"] = "https://chummer.run;touch-pwned"
        with self.assertRaisesRegex(ValueError, r"clean HTTP\(S\) origin"):
            module.validate_release_execution_environment(unsafe)
        unsafe = dict(module._test_release_execution_environment)
        unsafe["CHUMMER_RUN_SERVICES_ROOT"] = "/tmp/other-checkout"
        with self.assertRaisesRegex(ValueError, "must equal the current checkout"):
            module.validate_release_execution_environment(unsafe)
        unsafe = dict(module._test_release_execution_environment)
        unsafe["CHUMMER_PUBLIC_EDGE_EXPECTED_HEAD"] = "main"
        with self.assertRaisesRegex(ValueError, "must be a full Git commit"):
            module.validate_release_execution_environment(unsafe)
        with tempfile.TemporaryDirectory(prefix="release-plan-symlink-ancestor-") as temp_dir:
            root = Path(temp_dir)
            real = root / "real"
            real.mkdir()
            entrypoint = real / "gate.py"
            entrypoint.write_text("print('gate')\n", encoding="utf-8")
            linked = root / "linked"
            linked.symlink_to(real, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, "symlink component"):
                module.regular_file_execution_identity(linked / "gate.py")

    def test_controller_environment_rejects_path_and_function_injection_and_hashes_secrets(self) -> None:
        module = load_module()
        sanitize = module._production_authoritative_controller_environment
        base = {
            "PATH": module.TRUSTED_PATH,
            "PYTHONDONTWRITEBYTECODE": "1",
            "TEABLE_API_TOKEN": "test-secret-value",
            "UNLISTED_SECRET": "must-not-be-inherited",
        }

        with tempfile.TemporaryDirectory(prefix="release-controller-path-") as temp_dir:
            writable_bin = Path(temp_dir) / "bin"
            writable_bin.mkdir()
            with self.assertRaisesRegex(ValueError, "rejects inherited or user-writable PATH"):
                sanitize({**base, "PATH": f"{writable_bin}:/usr/bin:/bin"})
        with self.assertRaisesRegex(ValueError, "rejects inherited Bash functions"):
            sanitize({**base, "BASH_FUNC_injected%%": "() { exit 0; }"})

        with (
            mock.patch.object(module, "source_binding_failures", return_value=[]),
            mock.patch.object(module, "current_git_head", return_value="a" * 40),
        ):
            sanitized = sanitize(base)
        self.assertEqual(module.TRUSTED_PATH, sanitized["PATH"])
        self.assertNotIn("UNLISTED_SECRET", sanitized)
        self.assertEqual("test-secret-value", sanitized["TEABLE_API_TOKEN"])
        digests = module.controller_environment_value_digests(sanitized)
        self.assertNotIn("test-secret-value", json.dumps(digests, sort_keys=True))
        self.assertEqual(
            module.hashlib.sha256(b"test-secret-value").hexdigest(),
            digests["TEABLE_API_TOKEN"],
        )
        python_path = Path(module.sys.executable).resolve()
        plan = module.build_release_execution_plan(
            [
                [
                    gate_name,
                    f"{python_path} {SCRIPT_PATH}",
                    str(Path.cwd()),
                    "900",
                    str(SCRIPT_PATH),
                ]
                for gate_name in module.REQUIRED_RELEASE_VERIFIER_GATES
            ],
            [
                ["bash_noprofile_norc", str(Path("/usr/bin/bash").resolve())],
                ["python3", str(python_path)],
            ],
            [str(Path.cwd())],
            environment=module.current_release_execution_environment(sanitized),
            controller_environment=sanitized,
            run_nonce="e" * 64,
        )
        self.assertNotIn("test-secret-value", json.dumps(plan, sort_keys=True))
        self.assertEqual(
            digests["TEABLE_API_TOKEN"],
            plan["controller_environment_value_sha256"]["TEABLE_API_TOKEN"],
        )
        teable_gate = next(
            gate
            for gate in plan["gates"]
            if gate["name"] == "verify_teable_important_work_sync"
        )
        ordinary_gate = next(
            gate for gate in plan["gates"] if gate["name"] == "verify_package_boundaries"
        )
        self.assertIn("TEABLE_API_TOKEN", teable_gate["environment_keys"])
        self.assertNotIn("TEABLE_API_TOKEN", ordinary_gate["environment_keys"])

    def test_gate_environments_are_provider_scoped_and_all_outputs_redact_credentials(self) -> None:
        module = load_module()
        provider_environment = {
            **module._test_release_execution_environment,
            **{
                key: f"credential-{index}-{key.lower()}"
                for index, key in enumerate(sorted(module.RELEASE_PROVIDER_ENV_KEYS), start=1)
            },
        }
        for gate_name in module.REQUIRED_RELEASE_VERIFIER_GATES:
            child_environment = module.controller_gate_environment(
                gate_name,
                provider_environment,
            )
            expected = module.RELEASE_GATE_PROVIDER_ENV_KEYS.get(gate_name, frozenset())
            observed = set(child_environment) & set(module.RELEASE_PROVIDER_ENV_KEYS)
            with self.subTest(gate=gate_name):
                self.assertEqual(set(expected), observed)

        secret_environment = {
            key: f"secret-value-{index}-{key.lower()}"
            for index, key in enumerate(sorted(module.RELEASE_SECRET_ENV_KEYS), start=1)
        }
        encoded_secret = "credential/value with spaces+query?&="
        secret_environment["TEABLE_API_TOKEN"] = encoded_secret
        mixed_case_secret = "Ab/C"
        secret_environment["GITHUB_TOKEN"] = mixed_case_secret
        encoded_secret_values = {
            module.quote(encoded_secret, safe=""),
            module.quote_plus(encoded_secret, safe=""),
        }
        encoded_mixed_case_secret = module.quote(mixed_case_secret, safe="")
        case_different_lookalike = "ab%2fC"
        raw_header_token = "derived-authorization-token-987654321"
        emitted = "\n".join(
            [
                *(f"{key}={value}" for key, value in secret_environment.items()),
                f"Authorization: Bearer {raw_header_token}",
                "x-api-key=derived-api-key-123456789",
                "token=derived-query-token-123456789",
                *(f"https://example.invalid/proof?opaque={value}" for value in encoded_secret_values),
                f"https://example.invalid/proof?opaque={encoded_mixed_case_secret}",
                f"https://example.invalid/public?opaque={case_different_lookalike}",
            ]
        )
        redacted = module.redact_release_output(emitted, secret_environment)
        for value in secret_environment.values():
            self.assertNotIn(value, redacted)
        self.assertNotIn(raw_header_token, redacted)
        self.assertNotIn("derived-api-key-123456789", redacted)
        self.assertNotIn("derived-query-token-123456789", redacted)
        for encoded_value in encoded_secret_values:
            self.assertNotIn(encoded_value, redacted)
        self.assertNotIn(encoded_mixed_case_secret, redacted)
        self.assertIn(case_different_lookalike, redacted)
        self.assertGreaterEqual(redacted.count("[REDACTED]"), len(secret_environment) + 3)

        with tempfile.TemporaryDirectory(prefix="release-controller-redaction-") as temp_dir:
            gate_environment = {
                "PATH": module.TRUSTED_PATH,
                "PYTHONDONTWRITEBYTECODE": "1",
                "PYTHONNOUSERSITE": "1",
                "CHUMMER_RELEASE_READY_GATE_KILL_AFTER_SECONDS": "1",
                **secret_environment,
            }
            result = module.run_controller_gate_command(
                {
                    "command": "/usr/bin/env",
                    "cwd": temp_dir,
                    "timeout_seconds": 5,
                },
                gate_environment,
            )
        self.assertEqual(0, result["returncode"])
        for value in secret_environment.values():
            self.assertNotIn(value, result["stdout"])
            self.assertNotIn(value, result["stderr"])
        self.assertIn("[REDACTED]", result["stdout"])

    def test_isolated_python_launcher_ignores_workspace_startup_module(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="release-controller-python-isolation-") as temp_dir:
            root = Path(temp_dir)
            startup_marker = root / "startup-module-ran"
            result_path = root / "result.txt"
            (root / "sitecustomize.py").write_text(
                (
                    "from pathlib import Path\n"
                    f"Path({str(startup_marker)!r}).write_text('unexpected', encoding='utf-8')\n"
                ),
                encoding="utf-8",
            )
            (root / "helper.py").write_text("VALUE = 'isolated'\n", encoding="utf-8")
            target = root / "target.py"
            target.write_text(
                (
                    "from helper import VALUE\n"
                    "from pathlib import Path\n"
                    f"Path({str(result_path)!r}).write_text(VALUE, encoding='utf-8')\n"
                ),
                encoding="utf-8",
            )
            result = module.run_controller_gate_command(
                {
                    "command": module.isolated_python_command(target),
                    "cwd": str(root),
                    "timeout_seconds": 5,
                },
                {
                    "PATH": module.TRUSTED_PATH,
                    "PYTHONDONTWRITEBYTECODE": "1",
                    "PYTHONNOUSERSITE": "1",
                    "CHUMMER_RELEASE_READY_GATE_KILL_AFTER_SECONDS": "1",
                },
            )
            result_text = result_path.read_text(encoding="utf-8")
            startup_marker_exists = startup_marker.exists()

        self.assertEqual(0, result["returncode"])
        self.assertEqual("isolated", result_text)
        self.assertFalse(startup_marker_exists)

    def test_python_wrapper_rejects_shell_hooks_and_wrong_interpreter_never_goes_green(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="release-wrapper-function-") as temp_dir:
            root = Path(temp_dir)
            marker = root / "overridden-builtin-ran"
            bash_env_marker = root / "bash-env-ran"
            python_startup_marker = root / "python-startup-ran"
            (root / "sitecustomize.py").write_text(
                (
                    "from pathlib import Path\n"
                    f"Path({str(python_startup_marker)!r}).write_text('unexpected', encoding='utf-8')\n"
                ),
                encoding="utf-8",
            )
            bash_env = root / "bash-env.sh"
            bash_env.write_text(
                f"/usr/bin/touch {bash_env_marker}\n",
                encoding="utf-8",
            )
            bash_override_env = root / "bash-override-env.sh"
            bash_override_env.write_text(
                (
                    f"exec() {{ /usr/bin/touch {marker}; return 0; }}\n"
                    f"exit() {{ /usr/bin/touch {marker}; return 0; }}\n"
                    "export -f exec exit\n"
                ),
                encoding="utf-8",
            )
            function_environment = {
                "PATH": module.TRUSTED_PATH,
                "BASH_FUNC_exec%%": (
                    f"() {{ /usr/bin/touch {marker}; return 0; }}"
                ),
                "BASH_FUNC_exit%%": (
                    f"() {{ /usr/bin/touch {marker}; return 0; }}"
                ),
            }

            cases = {
                "direct_exported_functions": (
                    [str(VERIFY_SCRIPT_PATH), "--help"],
                    function_environment,
                ),
                "forced_bash_exported_functions": (
                    ["/usr/bin/bash", str(VERIFY_SCRIPT_PATH), "--help"],
                    function_environment,
                ),
                "direct_bash_env": (
                    [str(VERIFY_SCRIPT_PATH), "--help"],
                    {"PATH": module.TRUSTED_PATH, "BASH_ENV": str(bash_env)},
                ),
                "direct_python_startup_path": (
                    [str(VERIFY_SCRIPT_PATH), "--help"],
                    {"PATH": module.TRUSTED_PATH, "PYTHONPATH": str(root)},
                ),
                "forced_wrong_interpreter": (
                    ["/usr/bin/bash", str(VERIFY_SCRIPT_PATH), "--help"],
                    {"PATH": module.TRUSTED_PATH},
                ),
                "direct_python_bypass": (
                    [str(module.TRUSTED_PYTHON), str(VERIFY_SCRIPT_PATH), "--help"],
                    {"PATH": module.TRUSTED_PATH},
                ),
                "forced_bash_env_builtin_overrides": (
                    ["/usr/bin/bash", str(VERIFY_SCRIPT_PATH), "--help"],
                    {
                        "PATH": module.TRUSTED_PATH,
                        "BASH_ENV": str(bash_override_env),
                    },
                ),
            }
            for name, (command, environment) in cases.items():
                completed = module.subprocess.run(
                    command,
                    env=environment,
                    capture_output=True,
                    check=False,
                    text=True,
                )
                combined_lines = [
                    line.strip()
                    for line in (completed.stdout + completed.stderr).splitlines()
                    if line.strip()
                ]
                with self.subTest(name=name):
                    self.assertNotEqual(0, completed.returncode)
                    self.assertFalse(
                        any(
                            line.startswith(module.RELEASE_EXECUTION_PLAN_PREFIX)
                            or line.startswith(module.RELEASE_VERIFIER_REPLAY_BINDING_PREFIX)
                            for line in combined_lines
                        )
                    )
                    self.assertNotIn(module.READY_MARKER, combined_lines)

            self.assertFalse(marker.exists())
            self.assertFalse(bash_env_marker.exists())
            self.assertFalse(python_startup_marker.exists())

        clean_help = module.subprocess.run(
            [str(VERIFY_SCRIPT_PATH), "--help"],
            env={"PATH": module.TRUSTED_PATH},
            capture_output=True,
            check=False,
            text=True,
        )
        self.assertEqual(0, clean_help.returncode)
        self.assertIn("Materialize the release-ready receipt", clean_help.stdout)

    def test_forced_bash_exit_zero_hook_cannot_emit_controller_authority(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="release-wrapper-forced-bash-exit-") as temp_dir:
            hook = Path(temp_dir) / "bash-env.sh"
            hook.write_text("exit 0\n", encoding="utf-8")
            completed = module.subprocess.run(
                ["/usr/bin/bash", str(VERIFY_SCRIPT_PATH), "--help"],
                env={"PATH": module.TRUSTED_PATH, "BASH_ENV": str(hook)},
                capture_output=True,
                check=False,
                text=True,
            )

        combined_lines = [
            line.strip()
            for line in (completed.stdout + completed.stderr).splitlines()
            if line.strip()
        ]
        self.assertEqual(0, completed.returncode)
        self.assertNotIn(module.READY_MARKER, combined_lines)
        self.assertFalse(
            any(
                line.startswith(module.RELEASE_EXECUTION_PLAN_PREFIX)
                or line.startswith(module.RELEASE_VERIFIER_START_BINDING_PREFIX)
                or line.startswith(module.RELEASE_VERIFIER_REPLAY_BINDING_PREFIX)
                for line in combined_lines
            )
        )

    def test_execution_binding_rejects_higher_ancestor_swap_and_restore(self) -> None:
        module = load_module()
        python_path = Path(module.sys.executable).resolve()
        bash_path = Path("/usr/bin/bash").resolve()
        with tempfile.TemporaryDirectory(prefix="release-plan-ancestor-swap-") as temp_dir:
            code_root = Path(temp_dir) / "code"
            parent = code_root / "level-one"
            leaf_dir = parent / "level-two"
            leaf_dir.mkdir(parents=True)
            entrypoint = leaf_dir / "gate.py"
            entrypoint.write_text("print('trusted gate')\n", encoding="utf-8")
            gate_specs = [
                [
                    gate_name,
                    f"{python_path} {entrypoint}",
                    str(Path.cwd()),
                    "900",
                    str(entrypoint),
                ]
                for gate_name in module.REQUIRED_RELEASE_VERIFIER_GATES
            ]
            plan = module.build_release_execution_plan(
                gate_specs,
                [
                    ["bash_noprofile_norc", str(bash_path)],
                    ["python3", str(python_path)],
                ],
                [str(code_root)],
                environment=module._test_release_execution_environment,
                run_nonce="d" * 64,
            )
            start_binding = module.current_release_verifier_replay_binding(
                execution_plan=plan,
                binding_phase="start",
            )
            prebinding = module.current_gate_execution_prebinding(
                plan,
                "verify_package_boundaries",
                start_binding,
            )
            moved = code_root / "level-one.saved"
            parent.rename(moved)
            moved.rename(parent)

            with self.assertRaisesRegex(ValueError, "entrypoint drifted|changed during gate"):
                module.complete_gate_execution_binding(plan, prebinding)

    def test_governed_snapshot_rejects_transitive_helper_mutate_and_restore(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="release-governed-helper-restore-") as temp_dir:
            repository = Path(temp_dir) / "repo"
            helper = repository / "scripts" / "shared_helper.py"
            helper.parent.mkdir(parents=True)
            original = b"VALUE = 'trusted'\n"
            helper.write_bytes(original)
            git_env = {
                "PATH": module.TRUSTED_PATH,
                "HOME": str(Path(temp_dir) / "home"),
            }
            Path(git_env["HOME"]).mkdir()

            def git(*arguments: str) -> None:
                completed = module.subprocess.run(
                    [str(module.TRUSTED_GIT), "-C", str(repository), *arguments],
                    env=git_env,
                    capture_output=True,
                    check=False,
                )
                self.assertEqual(0, completed.returncode, completed.stderr.decode())

            git("init", "--quiet")
            git("add", "scripts/shared_helper.py")
            git(
                "-c",
                "user.name=Release Test",
                "-c",
                "user.email=release-test@example.invalid",
                "commit",
                "--quiet",
                "-m",
                "govern helper",
            )
            recorded = module.current_governed_code_snapshot((repository,), git_env)
            original_stat = helper.stat()
            helper.write_bytes(b"VALUE = 'substituted'\n")
            helper.write_bytes(original)
            module.os.utime(
                helper,
                ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns),
            )

            with self.assertRaisesRegex(ValueError, "governed code snapshot drifted"):
                module.validate_governed_code_snapshot(
                    recorded,
                    (repository,),
                    git_env,
                )

    def test_governed_snapshot_rejects_unborn_external_authority_without_fallback(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="release-unborn-authority-") as temp_dir:
            repository = Path(temp_dir) / "external-authority"
            repository.mkdir()
            home = Path(temp_dir) / "home"
            home.mkdir()
            environment = {"PATH": module.TRUSTED_PATH, "HOME": str(home)}
            completed = module.subprocess.run(
                [str(module.TRUSTED_GIT), "init", "--quiet", str(repository)],
                env=environment,
                capture_output=True,
                check=False,
            )
            self.assertEqual(0, completed.returncode, completed.stderr.decode())
            (repository / "release_gate.py").write_text(
                "print('untracked authority')\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(
                ValueError,
                "no enrolled Git HEAD.*live untracked digest fallback is not accepted",
            ):
                module.current_governed_code_snapshot(
                    (repository,),
                    environment,
                )

    def test_governed_snapshot_rejects_deep_directory_swap_execute_and_restore(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="release-governed-directory-swap-") as temp_dir:
            repository = Path(temp_dir) / "repo"
            helper = repository / "package" / "deep" / "helper.py"
            helper.parent.mkdir(parents=True)
            marker = repository / "alternate-helper-ran"
            helper.write_text("VALUE = 'trusted'\n", encoding="utf-8")
            git_env = {
                "PATH": module.TRUSTED_PATH,
                "HOME": str(Path(temp_dir) / "home"),
            }
            Path(git_env["HOME"]).mkdir()

            def git(*arguments: str) -> None:
                completed = module.subprocess.run(
                    [str(module.TRUSTED_GIT), "-C", str(repository), *arguments],
                    env=git_env,
                    capture_output=True,
                    check=False,
                )
                self.assertEqual(0, completed.returncode, completed.stderr.decode())

            git("init", "--quiet")
            git("add", "package/deep/helper.py")
            git(
                "-c",
                "user.name=Release Test",
                "-c",
                "user.email=release-test@example.invalid",
                "commit",
                "--quiet",
                "-m",
                "govern deep helper",
            )
            recorded = module.current_governed_code_snapshot((repository,), git_env)
            trusted_package = repository / "package"
            saved_package = repository / "package.trusted"
            trusted_package.rename(saved_package)
            alternate_helper = trusted_package / "deep" / "helper.py"
            alternate_helper.parent.mkdir(parents=True)
            alternate_helper.write_text(
                f"from pathlib import Path\nPath({str(marker)!r}).write_text('ran')\n",
                encoding="utf-8",
            )
            executed = module.subprocess.run(
                [str(module.TRUSTED_PYTHON), str(alternate_helper)],
                env={"PATH": module.TRUSTED_PATH, "PYTHONNOUSERSITE": "1"},
                capture_output=True,
                check=False,
            )
            self.assertEqual(0, executed.returncode, executed.stderr.decode())
            shutil.rmtree(trusted_package)
            saved_package.rename(trusted_package)

            self.assertEqual("ran", marker.read_text(encoding="utf-8"))
            with self.assertRaisesRegex(ValueError, "governed code snapshot drifted"):
                module.validate_governed_code_snapshot(
                    recorded,
                    (repository,),
                    git_env,
                )

    def test_governed_snapshot_rejects_untracked_and_ignored_code_inputs(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="release-governed-untracked-") as temp_dir:
            repository = Path(temp_dir) / "repo"
            repository.mkdir()
            (repository / ".gitignore").write_text("ignored/\n", encoding="utf-8")
            tracked = repository / "tracked.py"
            tracked.write_text("VALUE = 1\n", encoding="utf-8")
            git_env = {
                "PATH": module.TRUSTED_PATH,
                "HOME": str(Path(temp_dir) / "home"),
            }
            Path(git_env["HOME"]).mkdir()

            def git(*arguments: str) -> None:
                completed = module.subprocess.run(
                    [str(module.TRUSTED_GIT), "-C", str(repository), *arguments],
                    env=git_env,
                    capture_output=True,
                    check=False,
                )
                self.assertEqual(0, completed.returncode, completed.stderr.decode())

            git("init", "--quiet")
            git("add", ".gitignore", "tracked.py")
            git(
                "-c",
                "user.name=Release Test",
                "-c",
                "user.email=release-test@example.invalid",
                "commit",
                "--quiet",
                "-m",
                "govern base",
            )
            ignored_helper = repository / "ignored" / "helper.py"
            ignored_helper.parent.mkdir()
            ignored_helper.write_text("VALUE = 'ignored code'\n", encoding="utf-8")
            untracked_runner = repository / "scripts" / "release_runner"
            untracked_runner.parent.mkdir()
            untracked_runner.write_text("#!/usr/bin/dash\n", encoding="utf-8")

            with self.assertRaisesRegex(
                ValueError,
                "ignored/helper.py.*scripts/release_runner",
            ):
                module.current_governed_code_snapshot((repository,), git_env)

    def test_governed_output_exclusions_are_reasoned_and_never_cover_entrypoints(self) -> None:
        module = load_module()
        self.assertTrue(
            all(prefix and reason for prefix, reason in module.GOVERNED_CODE_EXCLUDED_OUTPUTS)
        )
        self.assertFalse(module.governed_code_path(".codex-studio/helper.py"))
        self.assertTrue(module.governed_code_path("node_modules/injected.js"))
        self.assertTrue(
            module.governed_restored_dependency_path("node_modules/injected.js")
        )
        for spec in module.canonical_release_gate_specs(
            module._test_release_execution_environment
        ):
            for entrypoint in spec["entrypoints"]:
                repository = module.governed_repository_root(Path(str(entrypoint)))
                relative = str(Path(str(entrypoint)).relative_to(repository))
                with self.subTest(gate=spec["name"], entrypoint=entrypoint):
                    self.assertTrue(module.governed_code_path(relative))

    def test_controller_gate_is_nonlogin_and_login_profile_cannot_bypass_command(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="release-controller-nonlogin-") as temp_dir:
            root = Path(temp_dir)
            home = root / "home"
            home.mkdir()
            (home / ".bash_profile").write_text("exit 0\n", encoding="utf-8")
            marker = root / "command-ran"
            result = module.run_controller_gate_command(
                {
                    "command": f"printf executed > {marker}",
                    "cwd": str(root),
                    "timeout_seconds": 5,
                },
                {
                    "HOME": str(home),
                    "PATH": module.TRUSTED_PATH,
                    "CHUMMER_RELEASE_READY_GATE_KILL_AFTER_SECONDS": "1",
                },
            )
            marker_value = marker.read_text(encoding="utf-8")

        self.assertEqual(0, result["returncode"])
        self.assertEqual("executed", marker_value)
        self.assertEqual(
            [str(module.TRUSTED_BASH), "--noprofile", "--norc", "-c"],
            result["argv"][:4],
        )
        self.assertNotIn("-l", result["argv"])
        self.assertNotIn("--login", result["argv"])

    def test_canonical_gold_gates_do_not_delegate_to_login_shell_wrappers(self) -> None:
        module = load_module()
        specs = {
            str(spec["name"]): spec
            for spec in module.canonical_release_gate_specs(
                module._test_release_execution_environment
            )
        }
        expected_prefix = module.shlex.join(module.TRUSTED_PYTHON_ISOLATED_PREFIX)
        for gate_name, former_wrapper in (
            ("verify_chummer6_desktop_gold", "verify_chummer6_desktop_gold.sh"),
            ("verify_chummer6_blazor_gold", "verify_chummer6_blazor_gold.sh"),
        ):
            command = str(specs[gate_name]["command"])
            entrypoints = [str(value) for value in specs[gate_name]["entrypoints"]]
            with self.subTest(gate=gate_name):
                self.assertNotIn(former_wrapper, command)
                self.assertFalse(any(former_wrapper in value for value in entrypoints))
                self.assertNotIn("bash -lc", command)
                self.assertNotIn("bash --login", command)
                self.assertIn(expected_prefix, command)

        base_blazor = specs["verify_chummer6_blazor_gold"]
        base_blazor_entrypoints = set(str(value) for value in base_blazor["entrypoints"])
        conditional_paths = {
            str(module.RUN_SERVICES_ROOT / "scripts" / "e2e-ui.sh"),
            str(module.ROOT / "chummer-presentation" / "scripts" / "e2e-portal.sh"),
            str(
                module.ROOT
                / "chummer-presentation"
                / "scripts"
                / "release"
                / "verify_blazor_self_host_workbench_freshness.sh"
            ),
        }
        self.assertEqual(7, len(base_blazor_entrypoints))
        self.assertFalse(base_blazor_entrypoints & conditional_paths)

        conditional_environment = {
            **module._test_release_execution_environment,
            "CHUMMER_BLAZOR_REQUIRE_LOCAL_E2E": "1",
            "CHUMMER_BLAZOR_REQUIRE_SELF_HOST_E2E": "1",
        }
        with (
            mock.patch.object(module, "source_binding_failures", return_value=[]),
            mock.patch.object(module, "current_git_head", return_value="a" * 40),
        ):
            sanitized_conditional_environment = (
                module._production_authoritative_controller_environment(
                    {
                        "PATH": module.TRUSTED_PATH,
                        "CHUMMER_BLAZOR_REQUIRE_LOCAL_E2E": "1",
                        "CHUMMER_BLAZOR_REQUIRE_SELF_HOST_E2E": "1",
                    }
                )
            )
        self.assertEqual("1", sanitized_conditional_environment["CHUMMER_BLAZOR_REQUIRE_LOCAL_E2E"])
        self.assertEqual(
            "1",
            sanitized_conditional_environment["CHUMMER_BLAZOR_REQUIRE_SELF_HOST_E2E"],
        )
        conditional_specs = {
            str(spec["name"]): spec
            for spec in module.canonical_release_gate_specs(conditional_environment)
        }
        conditional_blazor = conditional_specs["verify_chummer6_blazor_gold"]
        conditional_entrypoints = set(
            str(value) for value in conditional_blazor["entrypoints"]
        )
        self.assertEqual(10, len(conditional_entrypoints))
        self.assertTrue(conditional_paths <= conditional_entrypoints)
        self.assertTrue(
            all(path in str(conditional_blazor["command"]) for path in conditional_paths)
        )
        self.assertIn("failures=()", str(conditional_blazor["command"]))
        self.assertIn("BLAZOR NOT GOLD", str(conditional_blazor["command"]))
        self.assertNotIn("bash -lc", str(conditional_blazor["command"]))
        for blazor_spec in (base_blazor, conditional_blazor):
            syntax = module.subprocess.run(
                [
                    str(module.TRUSTED_BASH),
                    "--noprofile",
                    "--norc",
                    "-n",
                    "-c",
                    str(blazor_spec["command"]),
                ],
                env={"PATH": module.TRUSTED_PATH},
                capture_output=True,
                check=False,
                text=True,
            )
            self.assertEqual(0, syntax.returncode, syntax.stderr)

        invalid_environment = dict(module._test_release_execution_environment)
        invalid_environment["CHUMMER_BLAZOR_REQUIRE_LOCAL_E2E"] = "true"
        with self.assertRaisesRegex(ValueError, "CHUMMER_BLAZOR_REQUIRE_LOCAL_E2E.*0 or 1"):
            module.validate_release_execution_environment(invalid_environment)

        gate_specs = [
            [
                str(spec["name"]),
                str(spec["command"]),
                str(spec["cwd"]),
                str(spec["timeout_seconds"]),
                "|".join(str(value) for value in spec["entrypoints"]),
            ]
            for spec in specs.values()
        ]
        plan = module.build_release_execution_plan(
            gate_specs,
            [
                ["bash_noprofile_norc", str(module.TRUSTED_BASH)],
                ["python3", str(module.TRUSTED_PYTHON)],
                ["node", str(module.TRUSTED_NODE)],
                ["git", str(module.TRUSTED_GIT)],
            ],
            [str(module.ROOT), "/docker/fleet/repos/chummer-media-factory"],
            environment=module._test_release_execution_environment,
            controller_environment=module._test_release_execution_environment,
            run_nonce="f" * 64,
        )
        self.assertEqual(len(module.REQUIRED_RELEASE_VERIFIER_GATES), plan["gate_count"])
        conditional_plan = module.build_release_execution_plan(
            [
                [
                    str(spec["name"]),
                    str(spec["command"]),
                    str(spec["cwd"]),
                    str(spec["timeout_seconds"]),
                    "|".join(str(value) for value in spec["entrypoints"]),
                ]
                for spec in conditional_specs.values()
            ],
            [
                ["bash_noprofile_norc", str(module.TRUSTED_BASH)],
                ["python3", str(module.TRUSTED_PYTHON)],
                ["node", str(module.TRUSTED_NODE)],
                ["git", str(module.TRUSTED_GIT)],
            ],
            [str(module.ROOT), "/docker/fleet/repos/chummer-media-factory"],
            environment=conditional_environment,
            controller_environment=conditional_environment,
            run_nonce="e" * 64,
        )
        conditional_plan_blazor = next(
            gate
            for gate in conditional_plan["gates"]
            if gate["name"] == "verify_chummer6_blazor_gold"
        )
        self.assertEqual(10, len(conditional_plan_blazor["entrypoints"]))

    def test_controller_rejects_and_extinguishes_same_pgid_background_descendant(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="release-controller-same-pgid-") as temp_dir:
            root = Path(temp_dir)
            pid_path = root / "background.pid"
            result = module.run_controller_gate_command(
                {
                    "command": (
                        f"/usr/bin/sleep 60 & child=$!; "
                        f"printf '%s' \"$child\" > {module.shlex.quote(str(pid_path))}"
                    ),
                    "cwd": str(root),
                    "timeout_seconds": 5,
                },
                {
                    "PATH": module.TRUSTED_PATH,
                    "PYTHONDONTWRITEBYTECODE": "1",
                    "PYTHONNOUSERSITE": "1",
                    "CHUMMER_RELEASE_READY_GATE_KILL_AFTER_SECONDS": "1",
                },
            )
            child_pid = int(pid_path.read_text(encoding="utf-8"))
            try:
                self.assertEqual(125, result["returncode"])
                self.assertTrue(result["containment_violation"])
                self.assertIn(child_pid, result["lingering_descendant_pids"])
                identity = module.process_identity(child_pid)
                self.assertFalse(
                    module.process_identity_is_live(identity) if identity is not None else False
                )
            finally:
                identity = module.process_identity(child_pid)
                if identity is not None and module.process_identity_is_live(identity):
                    os.kill(child_pid, module.signal.SIGKILL)
                    try:
                        os.waitpid(child_pid, 0)
                    except ChildProcessError:
                        pass

    def test_controller_rejects_and_extinguishes_setsid_double_fork_descendant(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="release-controller-double-fork-") as temp_dir:
            root = Path(temp_dir)
            daemon_pid_path = root / "daemon.pid"
            daemon_script = root / "double_fork.py"
            daemon_script.write_text(
                "\n".join(
                    [
                        "import os",
                        "import sys",
                        "import time",
                        "from pathlib import Path",
                        "first = os.fork()",
                        "if first:",
                        "    os.waitpid(first, 0)",
                        "    sys.exit(0)",
                        "os.setsid()",
                        "second = os.fork()",
                        "if second:",
                        "    time.sleep(0.1)",
                        "    os._exit(0)",
                        f"Path({str(daemon_pid_path)!r}).write_text(str(os.getpid()))",
                        "time.sleep(60)",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            result = module.run_controller_gate_command(
                {
                    "command": (
                        f"{module.TRUSTED_PYTHON} "
                        f"{module.shlex.quote(str(daemon_script))}"
                    ),
                    "cwd": str(root),
                    "timeout_seconds": 5,
                },
                {
                    "PATH": module.TRUSTED_PATH,
                    "PYTHONDONTWRITEBYTECODE": "1",
                    "PYTHONNOUSERSITE": "1",
                    "CHUMMER_RELEASE_READY_GATE_KILL_AFTER_SECONDS": "1",
                },
            )
            daemon_pid = int(daemon_pid_path.read_text(encoding="utf-8"))
            try:
                self.assertEqual(125, result["returncode"])
                self.assertTrue(result["containment_violation"])
                self.assertIn(daemon_pid, result["lingering_descendant_pids"])
                identity = module.process_identity(daemon_pid)
                self.assertFalse(
                    module.process_identity_is_live(identity) if identity is not None else False
                )
            finally:
                identity = module.process_identity(daemon_pid)
                if identity is not None and module.process_identity_is_live(identity):
                    os.kill(daemon_pid, module.signal.SIGKILL)
                    try:
                        os.waitpid(daemon_pid, 0)
                    except ChildProcessError:
                        pass

    def test_authoritative_process_containment_fails_closed_when_unsupported(self) -> None:
        module = load_module()
        with mock.patch.object(module.sys, "platform", "darwin"):
            with self.assertRaisesRegex(ValueError, "requires Linux procfs"):
                module.ensure_authoritative_process_containment()

    def test_controller_timeout_kills_the_gate_process_group(self) -> None:
        module = load_module()
        process = mock.Mock(pid=4321, returncode=None)
        process.poll.side_effect = [None, None]
        process.wait.return_value = 0
        with (
            mock.patch.object(module.subprocess, "Popen", return_value=process) as popen,
            mock.patch.object(module.os, "killpg") as killpg,
            mock.patch.object(module.time, "monotonic", side_effect=[0, 2, 2, 2]),
        ):
            result = module.run_controller_gate_command(
                {
                    "command": "sleep 60",
                    "cwd": str(Path.cwd()),
                    "timeout_seconds": 1,
                },
                {
                    "PATH": module.TRUSTED_PATH,
                    "CHUMMER_RELEASE_READY_GATE_KILL_AFTER_SECONDS": "2",
                },
            )

        self.assertEqual(124, result["returncode"])
        self.assertTrue(result["timed_out"])
        self.assertTrue(popen.call_args.kwargs["start_new_session"])
        killpg.assert_called_once_with(4321, module.signal.SIGTERM)

    def test_default_controller_blocks_external_write_gate_before_any_execution(self) -> None:
        module = load_module()
        plan = {
            "external_write_gates": ["verify_teable_important_work_sync"],
            "external_write_authorized": False,
        }
        with (
            mock.patch.object(
                module,
                "authoritative_release_execution_plan",
                return_value=plan,
            ) as plan_builder,
            mock.patch.object(module, "validate_release_execution_plan"),
            mock.patch.object(
                module,
                "current_release_verifier_replay_binding",
                return_value={
                    "generated_at_utc": module.now_iso(),
                    "authority_sha256": "a" * 64,
                },
            ),
            mock.patch.object(module, "run_controller_gate_command") as execute_gate,
        ):
            result = module.run_authoritative_release_controller(
                module._test_release_execution_environment,
                external_write_authorized=False,
            )

        plan_builder.assert_called_once_with(
            mock.ANY,
            external_write_authorized=False,
            process_containment={
                "mode": module.PROCESS_CONTAINMENT_MODE,
                "authoritative": True,
                "subreaper": True,
                "procfs": "/proc",
            },
        )
        execute_gate.assert_not_called()
        self.assertEqual(77, result["returncode"])
        self.assertNotIn(module.READY_MARKER, result["stdout"].splitlines())
        self.assertIn(module.NOT_READY_MARKER, result["stdout"].splitlines())
        self.assertIn(module.EXTERNAL_WRITE_AUTHORIZATION_FLAG, result["stderr"])
        self.assertEqual(
            [],
            module.controller_external_write_blockers(
                {**plan, "external_write_authorized": True}
            ),
        )
        with mock.patch.object(
            module,
            "build_release_execution_plan",
            return_value={"plan": "captured"},
        ) as build_plan:
            captured = module.authoritative_release_execution_plan(
                module._test_release_execution_environment,
                external_write_authorized=True,
                process_containment={
                    "mode": module.PROCESS_CONTAINMENT_MODE,
                    "authoritative": True,
                    "subreaper": True,
                    "procfs": "/proc",
                },
            )
        self.assertEqual({"plan": "captured"}, captured)
        self.assertTrue(build_plan.call_args.kwargs["external_write_authorized"])
        self.assertEqual(
            ("verify_teable_important_work_sync",),
            tuple(build_plan.call_args.kwargs["external_write_gates"]),
        )

    def test_controller_rejects_release_authority_mutation_between_start_and_final(self) -> None:
        module = load_module()
        evidence = passing_verifier_evidence(module)
        start_binding = dict(evidence["start_binding"])
        mutated_final_binding = dict(evidence["final_binding"])
        mutated_final_binding["release_version"] = "mutated-during-controller-run"
        containment = {
            "mode": module.PROCESS_CONTAINMENT_MODE,
            "authoritative": True,
            "subreaper": True,
            "procfs": "/proc",
        }
        passing_gate_result = {
            "returncode": 0,
            "timed_out": False,
            "stdout": "",
            "stderr": "",
            "process_containment": containment,
            "containment_violation": False,
        }

        with (
            mock.patch.object(module, "ensure_authoritative_process_containment", return_value=containment),
            mock.patch.object(
                module,
                "authoritative_release_execution_plan",
                return_value=evidence["plan"],
            ),
            mock.patch.object(module, "validate_release_execution_plan"),
            mock.patch.object(
                module,
                "current_release_verifier_replay_binding",
                side_effect=[start_binding, mutated_final_binding],
            ),
            mock.patch.object(
                module,
                "current_gate_execution_prebinding",
                side_effect=lambda _plan, gate, _start: {"gate": gate},
            ),
            mock.patch.object(
                module,
                "complete_gate_execution_binding",
                side_effect=list(evidence["execution_bindings"]),
            ),
            mock.patch.object(
                module,
                "run_controller_gate_command",
                return_value=passing_gate_result,
            ),
            mock.patch.object(
                module,
                "validate_gate_execution_bindings",
                side_effect=lambda _plan, bindings, **_kwargs: bindings,
            ),
            mock.patch.object(
                module,
                "validate_release_gate_receipt_bindings",
                return_value=[],
            ),
            mock.patch.object(module, "validate_release_verifier_binding_payload"),
        ):
            result = module.run_authoritative_release_controller(
                module._test_release_execution_environment,
                external_write_authorized=True,
            )

        self.assertEqual(1, result["returncode"])
        self.assertEqual({}, result["validated_release_binding"])
        self.assertIn("authority drifted between start and final", result["stderr"])
        self.assertNotIn(module.READY_MARKER, result["stdout"].splitlines())
        self.assertIn(module.NOT_READY_MARKER, result["stdout"].splitlines())

    def test_strict_replay_state_machine_rejects_moved_duplicate_and_trailing_events(self) -> None:
        module = load_module()
        valid = passing_verifier_output(module)
        lines = valid.splitlines()
        plan_index = next(
            index
            for index, line in enumerate(lines)
            if line.startswith(module.RELEASE_EXECUTION_PLAN_PREFIX)
        )
        start_index = next(
            index
            for index, line in enumerate(lines)
            if line.startswith(module.RELEASE_VERIFIER_START_BINDING_PREFIX)
        )
        first_gate_index = next(
            index
            for index, line in enumerate(lines)
            if line.startswith("START verify_chummer6_desktop_gold ")
        )
        first_execution_index = next(
            index
            for index, line in enumerate(lines)
            if line.startswith(module.RELEASE_GATE_EXECUTION_BINDING_PREFIX)
        )
        final_index = next(
            index
            for index, line in enumerate(lines)
            if line.startswith(module.RELEASE_VERIFIER_REPLAY_BINDING_PREFIX)
        )
        cases: dict[str, list[str]] = {}
        duplicate_start = list(lines)
        duplicate_start.insert(start_index + 1, lines[start_index])
        cases["duplicate_start"] = duplicate_start
        moved_execution = list(lines)
        execution_line = moved_execution.pop(first_execution_index)
        moved_execution.insert(first_gate_index + 2, execution_line)
        cases["execution_after_pass"] = moved_execution
        final_before_gates = list(lines)
        final_line = final_before_gates.pop(final_index)
        final_before_gates.insert(first_gate_index, final_line)
        cases["final_before_gates"] = final_before_gates
        trailing = list(lines)
        trailing.append("PASS trailing execution_binding_sha256=" + "0" * 64)
        cases["trailing_after_ready"] = trailing
        authority_before_plan = list(lines)
        authority_before_plan.insert(plan_index, lines[start_index])
        cases["authority_before_plan"] = authority_before_plan
        for name, case_lines in cases.items():
            with self.subTest(name=name), self.assertRaises(ValueError):
                module.validate_release_verifier_replay_binding("\n".join(case_lines) + "\n")

    def test_strict_replay_requires_direct_receipt_between_execution_and_pass(self) -> None:
        module = load_module()
        evidence = passing_verifier_evidence(module)
        first_gate = module.REQUIRED_RELEASE_VERIFIER_GATES[0]
        first_execution = evidence["execution_bindings"][0]
        direct = {
            "gate": first_gate,
            "binding_sha256": "d" * 64,
            "captured_at_utc": first_execution["captured_after_at_utc"],
        }
        final_binding = module.current_release_verifier_replay_binding(
            execution_plan=evidence["plan"],
            binding_phase="final",
            execution_bindings=evidence["execution_bindings"],
            direct_receipt_bindings=[direct],
        )
        lines = str(evidence["stdout"]).splitlines()
        final_index = next(
            index
            for index, line in enumerate(lines)
            if line.startswith(module.RELEASE_VERIFIER_REPLAY_BINDING_PREFIX)
        )
        lines[final_index] = (
            module.RELEASE_VERIFIER_REPLAY_BINDING_PREFIX
            + json.dumps(final_binding, sort_keys=True, separators=(",", ":"))
        )
        first_execution_index = next(
            index
            for index, line in enumerate(lines)
            if line.startswith(module.RELEASE_GATE_EXECUTION_BINDING_PREFIX)
        )
        direct_line = (
            module.RELEASE_VERIFIER_GATE_RECEIPT_BINDING_PREFIX
            + json.dumps(direct, sort_keys=True, separators=(",", ":"))
        )
        lines.insert(first_execution_index + 1, direct_line)
        with (
            mock.patch.object(
                module,
                "RELEASE_VERIFIER_GATE_RECEIPTS",
                ((first_gate, "test", Path("/tmp/test"), "test", (), ()),),
            ),
            mock.patch.object(
                module,
                "validate_release_gate_receipt_bindings",
                return_value=[direct],
            ),
        ):
            module.validate_release_verifier_replay_binding("\n".join(lines) + "\n")
            moved = list(lines)
            moved_direct = moved.pop(first_execution_index + 1)
            moved.insert(first_execution_index + 2, moved_direct)
            with self.assertRaisesRegex(ValueError, "RELEASE_GATE_RECEIPT_BINDING|direct receipt"):
                module.validate_release_verifier_replay_binding("\n".join(moved) + "\n")

    def test_direct_receipt_binding_rejects_receipt_byte_drift_after_gate_pass(self) -> None:
        module = load_module()
        observed_at = module.datetime(2026, 7, 13, 12, 0, tzinfo=module.UTC)
        observed_text = observed_at.isoformat().replace("+00:00", "Z")
        with tempfile.TemporaryDirectory(prefix="release-ready-direct-binding-drift-") as temp_dir:
            root = Path(temp_dir)
            registry = root / "registry"
            registry.mkdir()
            receipt_path = root / "DIRECT_GATE.generated.json"
            verifier_path = root / "verify-release.sh"
            program_path = root / "gate-verifier.py"
            verifier_path.write_text("#!/usr/bin/env bash\n", encoding="utf-8")
            program_path.write_text("# current verifier\n", encoding="utf-8")
            (registry / "RELEASE_CHANNEL.generated.json").write_text(
                json.dumps(
                    {
                        "status": "published",
                        "version": "run-current",
                        "channel": "preview",
                        "supportabilityState": "review_required",
                        "rolloutState": "public_release_review_required",
                        "publishedAt": observed_text,
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            receipt = {
                "contract_name": "test.direct_gate.v1",
                "status": "pass",
                "generated_at_utc": observed_text,
                "failures": [],
            }
            receipt_path.write_text(json.dumps(receipt) + "\n", encoding="utf-8")
            with (
                mock.patch.object(module, "REGISTRY_PUBLISHED_ROOT", registry),
                mock.patch.object(module, "VERIFY_SCRIPT", verifier_path),
                mock.patch.object(
                    module,
                    "RELEASE_VERIFIER_BOUND_PROGRAMS",
                    (("test_gate_verifier", program_path),),
                ),
                mock.patch.object(
                    module,
                    "RELEASE_VERIFIER_GATE_RECEIPTS",
                    (
                        (
                            "verify_test_direct_gate",
                            "test_direct_gate",
                            receipt_path,
                            "test.direct_gate.v1",
                            (),
                            (),
                        ),
                    ),
                ),
                mock.patch.object(
                    module,
                    "direct_receipt_semantic_validation_failures",
                    wraps=module.direct_receipt_semantic_validation_failures,
                ) as semantic_validation,
            ):
                captured = module.current_release_gate_receipt_binding(
                    "verify_test_direct_gate",
                    now=observed_at,
                )
                self.assertIsNotNone(captured)
                semantic_validation.assert_called_once_with(
                    "verify_test_direct_gate",
                    receipt,
                    receipt_path,
                    observed_at=observed_at,
                )
                receipt["projection"] = "mutated after PASS"
                receipt_path.write_text(json.dumps(receipt) + "\n", encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "direct receipt binding drifted"):
                    module.validate_release_gate_receipt_bindings(
                        [captured],
                        now=observed_at,
                    )

    def test_release_verifier_binding_requires_release_published_timestamp(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="release-ready-missing-published-at-") as temp_dir:
            root = Path(temp_dir)
            registry = root / "registry"
            registry.mkdir()
            verifier_path = root / "verify-release.sh"
            program_path = root / "gate-verifier.py"
            verifier_path.write_text("#!/usr/bin/env bash\n", encoding="utf-8")
            program_path.write_text("# current verifier\n", encoding="utf-8")
            (registry / "RELEASE_CHANNEL.generated.json").write_text(
                json.dumps(
                    {
                        "status": "published",
                        "version": "run-current",
                        "channel": "preview",
                        "supportabilityState": "review_required",
                        "rolloutState": "public_release_review_required",
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            with (
                mock.patch.object(module, "REGISTRY_PUBLISHED_ROOT", registry),
                mock.patch.object(module, "VERIFY_SCRIPT", verifier_path),
                mock.patch.object(
                    module,
                    "RELEASE_VERIFIER_BOUND_PROGRAMS",
                    (("test_gate_verifier", program_path),),
                ),
            ):
                with self.assertRaisesRegex(ValueError, "publishedAt is missing or invalid"):
                    module.current_release_verifier_replay_binding()

    def test_direct_receipts_dispatch_to_available_contract_validators(self) -> None:
        module = load_module()
        observed_at = module.datetime(2026, 7, 13, 12, 0, tzinfo=module.UTC)
        receipt_path = Path("/tmp/DIRECT_GATE.generated.json")
        cases = (
            ("verify_supply_chain_evidence", "supply_chain_receipt_validation_failures"),
            (
                "verify_public_edge_observability_release",
                "public_edge_observability_release_blocking_reasons",
            ),
            (
                "verify_windows_installer_visual_audit_intake_request",
                "windows_visual_audit_release_blocking_reasons",
            ),
            (
                "verify_flagship_product_readiness",
                "flagship_product_readiness_gate_semantic_failures",
            ),
            (
                "verify_public_edge_postdeploy_gate",
                "public_edge_postdeploy_release_blocking_reasons",
            ),
            ("verify_google_oauth_linking_proof", "google_oauth_receipt_validation_failures"),
        )
        for gate_name, validator_name in cases:
            with (
                self.subTest(gate=gate_name),
                mock.patch.object(
                    module,
                    validator_name,
                    return_value=[f"{gate_name} semantic failure"],
                ) as validator,
            ):
                failures = module.direct_receipt_semantic_validation_failures(
                    gate_name,
                    {"status": "pass"},
                    receipt_path,
                    observed_at=observed_at,
                )

            self.assertEqual([f"{gate_name} semantic failure"], failures)
            validator.assert_called_once()

    def test_windows_direct_receipt_semantics_accept_clean_pass_and_retain_failures(self) -> None:
        module = load_module()
        observed_at = module.datetime(2026, 7, 13, 12, 0, tzinfo=module.UTC)
        promoted_digest = "a" * 64
        passing_receipt = {
            "status": "pass",
            "failures": [],
            "failed_gates": [],
            "artifact": {"sha256": promoted_digest},
            "visualAuditSource": {"artifactSha256": promoted_digest},
        }

        self.assertEqual(
            [],
            module.direct_receipt_semantic_validation_failures(
                "verify_windows_installer_visual_audit_intake_request",
                passing_receipt,
                Path("/tmp/WINDOWS_INSTALLER_VISUAL_AUDIT.generated.json"),
                observed_at=observed_at,
            ),
        )
        self.assertEqual(
            ["recorded Windows verification failure"],
            module.windows_visual_audit_release_blocking_reasons(
                {
                    **passing_receipt,
                    "failures": ["recorded Windows verification failure"],
                }
            ),
        )
        mismatch_reasons = module.windows_visual_audit_release_blocking_reasons(
            {
                **passing_receipt,
                "visualAuditSource": {"artifactSha256": "b" * 64},
            }
        )
        self.assertTrue(any("instead of promoted digest" in reason for reason in mismatch_reasons))

    def test_direct_receipt_binding_rejects_stale_pass_receipt(self) -> None:
        module = load_module()
        observed_at = module.datetime(2026, 7, 13, 12, 0, tzinfo=module.UTC)
        stale_at = observed_at - module.timedelta(hours=25)
        published_at = observed_at - module.timedelta(hours=26)
        with tempfile.TemporaryDirectory(prefix="release-ready-direct-binding-stale-") as temp_dir:
            root = Path(temp_dir)
            registry = root / "registry"
            registry.mkdir()
            receipt_path = root / "DIRECT_GATE.generated.json"
            verifier_path = root / "verify-release.sh"
            program_path = root / "gate-verifier.py"
            verifier_path.write_text("#!/usr/bin/env bash\n", encoding="utf-8")
            program_path.write_text("# current verifier\n", encoding="utf-8")
            (registry / "RELEASE_CHANNEL.generated.json").write_text(
                json.dumps(
                    {
                        "status": "published",
                        "version": "run-current",
                        "channel": "preview",
                        "supportabilityState": "review_required",
                        "rolloutState": "public_release_review_required",
                        "publishedAt": published_at.isoformat().replace("+00:00", "Z"),
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            receipt_path.write_text(
                json.dumps(
                    {
                        "contract_name": "test.direct_gate.v1",
                        "status": "pass",
                        "generated_at_utc": stale_at.isoformat().replace("+00:00", "Z"),
                        "failures": [],
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            with (
                mock.patch.object(module, "REGISTRY_PUBLISHED_ROOT", registry),
                mock.patch.object(module, "VERIFY_SCRIPT", verifier_path),
                mock.patch.object(
                    module,
                    "RELEASE_VERIFIER_BOUND_PROGRAMS",
                    (("test_gate_verifier", program_path),),
                ),
                mock.patch.object(
                    module,
                    "RELEASE_VERIFIER_GATE_RECEIPTS",
                    (
                        (
                            "verify_test_direct_gate",
                            "test_direct_gate",
                            receipt_path,
                            "test.direct_gate.v1",
                            (),
                            (),
                        ),
                    ),
                ),
            ):
                with self.assertRaisesRegex(ValueError, "direct receipt is stale"):
                    module.current_release_gate_receipt_binding(
                        "verify_test_direct_gate",
                        now=observed_at,
                    )

    def test_direct_receipt_binding_validation_cli_preserves_canonical_order(self) -> None:
        module = load_module()
        bindings = [{"gate": "verify_first"}, {"gate": "verify_second"}]
        argv: list[str] = []
        for binding in bindings:
            argv.extend(
                [
                    "--validate-release-gate-receipt-binding-json",
                    json.dumps(binding),
                ]
            )
        argv.extend(["--release-execution-plan-json", "{}"])
        with mock.patch.object(
            module,
            "validate_release_gate_receipt_bindings",
            return_value=bindings,
        ) as validate_mock:
            result = module.main(argv)

        self.assertEqual(0, result)
        validate_mock.assert_called_once_with(
            bindings,
            execution_plan={},
            execution_bindings=[],
            require_execution_binding=True,
        )

    def test_google_direct_binding_rejects_placeholder_screenshot_bytes(self) -> None:
        module = load_module()
        observed_at = module.datetime(2026, 7, 13, 12, 0, tzinfo=module.UTC)
        observed_text = observed_at.isoformat().replace("+00:00", "Z")
        with tempfile.TemporaryDirectory(prefix="release-ready-google-placeholder-") as temp_dir:
            root = Path(temp_dir)
            published = root / "published"
            registry = root / "registry"
            run_services = root / "run-services"
            imported = (
                run_services
                / ".state"
                / "google_oauth_linking_operator_evidence"
                / "imported"
            )
            for directory in (published, registry, imported):
                directory.mkdir(parents=True, exist_ok=True)
            verifier_path = root / "verify-release.sh"
            program_path = root / "gate-verifier.py"
            verifier_path.write_text("#!/usr/bin/env bash\n", encoding="utf-8")
            program_path.write_text("# current verifier\n", encoding="utf-8")
            (registry / "RELEASE_CHANNEL.generated.json").write_text(
                json.dumps(
                    {
                        "status": "published",
                        "version": "run-current",
                        "channel": "preview",
                        "supportabilityState": "review_required",
                        "rolloutState": "public_release_review_required",
                        "publishedAt": observed_text,
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            evidence_path = published / "GOOGLE_OAUTH_LINKING_OPERATOR_EVIDENCE.generated.json"
            request_path = published / "GOOGLE_OAUTH_LINKING_OPERATOR_EVIDENCE_REQUEST.generated.json"
            proof_path = published / "GOOGLE_OAUTH_LINKING_PROOF.generated.json"
            screenshots = [imported / "linked.png", imported / "returned.png"]
            for screenshot in screenshots:
                screenshot.write_bytes(b"ok")
            evidence_path.write_text("{}\n", encoding="utf-8")
            request_path.write_text("{}\n", encoding="utf-8")
            proof_path.write_text(
                json.dumps(
                    {
                        "contract_name": "chummer.run.google_oauth_linking_proof",
                        "status": "pass",
                        "generated_at_utc": observed_text,
                        "failures": [],
                        "operator_end_to_end_evidence": {
                            "pass": True,
                            "path": str(evidence_path),
                            "observed_at_utc": observed_text,
                            "screenshot_paths": [str(path) for path in screenshots],
                        },
                        "operator_request_artifacts": {
                            "request_receipt_path": str(request_path),
                            "release_version": "run-current",
                            "release_channel": "preview",
                        },
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            with (
                mock.patch.object(module, "PUBLISHED_ROOT", published),
                mock.patch.object(module, "REGISTRY_PUBLISHED_ROOT", registry),
                mock.patch.object(module, "RUN_SERVICES_ROOT", run_services),
                mock.patch.object(module, "VERIFY_SCRIPT", verifier_path),
                mock.patch.object(
                    module,
                    "RELEASE_VERIFIER_BOUND_PROGRAMS",
                    (("test_gate_verifier", program_path),),
                ),
                mock.patch.object(
                    module,
                    "RELEASE_VERIFIER_GATE_RECEIPTS",
                    (
                        (
                            "verify_google_oauth_linking_proof",
                            "google_oauth_linking_proof",
                            proof_path,
                            "chummer.run.google_oauth_linking_proof",
                            (),
                            (),
                        ),
                    ),
                ),
            ):
                with self.assertRaisesRegex(ValueError, "not a substantive PNG proof"):
                    module.current_release_gate_receipt_binding(
                        "verify_google_oauth_linking_proof",
                        now=observed_at,
                    )

    def test_global_verifier_reserves_extended_timeout_for_guide_convergence(self) -> None:
        module = load_module()
        script = VERIFY_SCRIPT_PATH.read_text(encoding="utf-8")
        specs = module.canonical_release_gate_specs(module._test_release_execution_environment)
        by_name = {str(item["name"]): item for item in specs}

        self.assertEqual(module.REQUIRED_RELEASE_VERIFIER_GATES, tuple(by_name))
        self.assertEqual(1800, by_name["verify_guide_convergence"]["timeout_seconds"])
        self.assertTrue(
            all(
                item["timeout_seconds"] == 900
                for item in specs
                if item["name"] != "verify_guide_convergence"
            )
        )
        self.assertTrue(script.startswith("#!/usr/bin/python3 -I\n"))
        self.assertEqual(
            '__python_launcher__ = ("chummer-release-controller",)',
            script.splitlines()[1],
        )
        self.assertIn('TRUSTED_PYTHON = "/usr/bin/python3"', script)
        self.assertIn('TRUSTED_PYTHON,\n            "-I",\n            str(MATERIALIZER)', script)
        self.assertIn("if sys.flags.isolated != 1:", script)
        self.assertIn('"--run-authoritative-controller"', script)
        self.assertIn("os.execve(", script)
        self.assertNotIn(" -lc ", script)
        self.assertIn('name.startswith("BASH_FUNC_")', script)
        self.assertIn('"BASH_ENV"', script)
        self.assertIn('ambient["PATH"] = TRUSTED_PATH', script)
        self.assertIn('ambient["PYTHONNOUSERSITE"] = "1"', script)
        self.assertNotIn("\nexec ", script)
        self.assertNotIn("\nexit ", script)
        self.assertEqual(
            2,
            len(by_name["verify_supply_chain_evidence"]["entrypoints"]),
        )
        self.assertEqual(
            2,
            len(by_name["verify_ea_operator_readiness"]["entrypoints"]),
        )
        self.assertNotIn(
            "--allow-recoverable-wrapper-blockers",
            by_name["verify_flagship_product_readiness"]["command"],
        )
        self.assertTrue(by_name["verify_teable_important_work_sync"]["external_write"])

    def test_flagship_gate_with_non_wrapper_release_truth_blockers_is_not_recoverable(self) -> None:
        module = load_module()

        self.assertFalse(
            module.flagship_product_readiness_recoverable(
                {
                    "contract_name": module.FLAGSHIP_PRODUCT_READINESS_GATE_CONTRACT_NAME,
                    "status": "fail",
                    "verdict": "NOT_FLAGSHIP_PRODUCT_READY",
                    "pass": False,
                    "summary": {
                        "contract_name": "fleet.flagship_product_readiness",
                        "status": "fail",
                        "pass": False,
                        "completion_audit_status": "pass",
                        "flagship_readiness_audit_status": "pass",
                        "missing_count": 0,
                        "scoped_missing_count": 0,
                        "coverage_gap_keys": [],
                        "scoped_coverage_gap_keys": [],
                        "launch_critical_nested_blockers": [
                            "release channel channel is preview, not a flagship stable lane",
                            "release channel supportability is not gold_supported",
                            "release channel rollout is promoted_preview, not public_stable",
                            "Windows installer visual audit source digest does not match promoted installer",
                        ],
                    },
                }
            )
        )

    def test_flagship_gate_with_failed_nested_audits_and_only_wrapper_echo_is_not_recoverable(self) -> None:
        module = load_module()

        self.assertFalse(
            module.flagship_product_readiness_recoverable(
                {
                    "contract_name": module.FLAGSHIP_PRODUCT_READINESS_GATE_CONTRACT_NAME,
                    "status": "fail",
                    "verdict": "NOT_FLAGSHIP_PRODUCT_READY",
                    "pass": False,
                    "summary": {
                        "contract_name": "fleet.flagship_product_readiness",
                        "status": "fail",
                        "pass": False,
                        "completion_audit_status": "fail",
                        "flagship_readiness_audit_status": "fail",
                        "missing_count": 0,
                        "scoped_missing_count": 0,
                        "coverage_gap_keys": [],
                        "scoped_coverage_gap_keys": [],
                        "launch_critical_nested_blockers": [
                            "final gold janitor state is 'fail'",
                            "final gold janitor verdict is 'NOT_GOLD'",
                            "live-backed gold claim is not allowed",
                        ],
                    },
                }
            )
        )

    def test_flagship_gate_with_passed_nested_audits_and_exact_wrapper_echo_is_recoverable(self) -> None:
        module = load_module()

        payload = {
            "contract_name": module.FLAGSHIP_PRODUCT_READINESS_GATE_CONTRACT_NAME,
            "status": "fail",
            "verdict": "NOT_FLAGSHIP_PRODUCT_READY",
            "pass": False,
            "summary": {
                "contract_name": "fleet.flagship_product_readiness",
                "status": "fail",
                "pass": False,
                "completion_audit_status": "pass",
                "flagship_readiness_audit_status": "pass",
                "missing_count": 0,
                "scoped_missing_count": 0,
                "coverage_gap_keys": [],
                "scoped_coverage_gap_keys": [],
                "launch_critical_nested_blockers": [
                    "final gold janitor state is 'fail'",
                    "final gold janitor verdict is 'NOT_GOLD'",
                    "live-backed gold claim is not allowed",
                ],
            },
        }

        self.assertTrue(module.flagship_product_readiness_recoverable(payload))

        for field, unsafe_value in (
            ("completion_audit_status", "fail"),
            ("completion_audit_status", None),
            ("flagship_readiness_audit_status", "fail"),
            ("flagship_readiness_audit_status", None),
        ):
            adversarial = json.loads(json.dumps(payload))
            adversarial["summary"][field] = unsafe_value
            self.assertFalse(module.flagship_product_readiness_recoverable(adversarial))

        unsafe_status = json.loads(json.dumps(payload))
        unsafe_status["status"] = "pass"
        unsafe_status["verdict"] = "FLAGSHIP_PRODUCT_READY"
        self.assertFalse(module.flagship_product_readiness_recoverable(unsafe_status))

        for field, unsafe_value in (
            ("status", "pass"),
            ("pass", True),
            ("pass", None),
            ("verdict", "FLAGSHIP_PRODUCT_READY"),
        ):
            adversarial = json.loads(json.dumps(payload))
            adversarial["summary"][field] = unsafe_value
            self.assertFalse(module.flagship_product_readiness_recoverable(adversarial))

    def test_flagship_gate_with_unexpected_verdict_is_not_recoverable(self) -> None:
        module = load_module()

        self.assertFalse(
            module.flagship_product_readiness_recoverable(
                {
                    "contract_name": module.FLAGSHIP_PRODUCT_READINESS_GATE_CONTRACT_NAME,
                    "status": "pass",
                    "verdict": "NOT_FLAGSHIP_PRODUCT_READY",
                    "summary": {
                        "contract_name": "fleet.flagship_product_readiness",
                        "completion_audit_status": "pass",
                        "flagship_readiness_audit_status": "pass",
                        "missing_count": 0,
                        "scoped_missing_count": 0,
                        "coverage_gap_keys": [],
                        "scoped_coverage_gap_keys": [],
                        "launch_critical_nested_blockers": [
                            "release channel channel is preview, not a flagship stable lane",
                        ],
                    },
                }
            )
        )

    def test_flagship_receipt_failure_reasons_include_deduplicated_coverage_gaps(self) -> None:
        module = load_module()

        reasons = module.receipt_failure_reasons(
            {
                "contract_name": module.FLAGSHIP_PRODUCT_READINESS_GATE_CONTRACT_NAME,
                "coverage_gap_keys": ["desktop_client"],
                "scoped_coverage_gap_keys": ["desktop_client"],
                "summary": {
                    "contract_name": "fleet.flagship_product_readiness",
                    "coverage_gap_keys": ["desktop_client"],
                    "scoped_coverage_gap_keys": ["desktop_client"],
                    "launch_critical_nested_blockers": [
                        "release channel channel is preview, not a flagship stable lane",
                    ],
                },
            },
            "flagship product readiness receipt failed",
        )

        self.assertEqual(
            [
                "release channel channel is preview, not a flagship stable lane",
                "flagship readiness coverage gap remains: desktop_client",
            ],
            reasons,
        )

    def test_non_flagship_receipt_does_not_relabel_generic_coverage_gap(self) -> None:
        module = load_module()

        reasons = module.receipt_failure_reasons(
            {
                "contract_name": "example.generic_gate",
                "coverage_gap_keys": ["desktop_client"],
            },
            "generic gate failed",
        )

        self.assertEqual(["generic gate failed"], reasons)

    def test_receipt_failure_reasons_surface_supply_chain_blocker_codes(self) -> None:
        module = load_module()

        reasons = module.receipt_failure_reasons(
            {
                "status": "fail",
                "blockers": [
                    "container_vulnerability_audit:not_available",
                    "provenance:not_available",
                ],
            },
            "supply chain receipt is not pass",
        )

        self.assertEqual(
            [
                "container_vulnerability_audit:not_available",
                "provenance:not_available",
            ],
            reasons,
        )

    def test_help_exits_before_running_global_release_verifier(self) -> None:
        module = load_module()
        stdout = io.StringIO()
        with mock.patch.object(module.subprocess, "Popen") as popen, redirect_stdout(stdout):
            with self.assertRaises(SystemExit) as raised:
                module.main(["--help"])

        self.assertEqual(0, raised.exception.code)
        popen.assert_not_called()
        self.assertIn("Materialize the release-ready receipt", stdout.getvalue())

    def test_enrich_operator_ask_delivery_state_skips_resend_when_request_not_required(self) -> None:
        module = load_module()

        artifacts = module.enrich_operator_ask_delivery_state(
            {
                "request_status": "not_required",
                "operator_ask_message_sha256": "a" * 64,
                "operator_ask_delivery_text_sha256": "b" * 64,
                "operator_ask_delivery_text_preview": "Old operator ask said proof was still missing.",
                "operator_ask_send_command": "python3 resend-google",
                "import_command": "python3 import-google",
                "auto_import_watch_command": "python3 watch-google",
                "post_import_commands": ["python3 verify-google"],
                "preferred_drop_path": "/tmp/google-proof.zip",
            }
        )

        self.assertFalse(artifacts["operator_ask_delivery_current_text_comparable"])
        self.assertFalse(artifacts["operator_ask_delivery_matches_current_text"])
        self.assertFalse(artifacts["operator_ask_delivery_needs_resend"])
        self.assertEqual("", artifacts["operator_ask_resend_command"])
        self.assertTrue(artifacts["operator_ask_delivery_historical_only"])
        self.assertEqual("", artifacts["operator_ask_delivery_text_preview"])
        self.assertEqual(
            "Old operator ask said proof was still missing.",
            artifacts["operator_ask_delivery_historical_text_preview"],
        )
        self.assertEqual("", artifacts["operator_ask_send_command"])
        self.assertEqual("", artifacts["import_command"])
        self.assertEqual("", artifacts["auto_import_watch_command"])
        self.assertEqual([], artifacts["post_import_commands"])
        self.assertEqual("", artifacts["preferred_drop_path"])
        self.assertTrue(artifacts["operator_action_historical_only"])
        self.assertEqual(
            {
                "operator_ask_send_command": "python3 resend-google",
                "import_command": "python3 import-google",
                "auto_import_watch_command": "python3 watch-google",
                "post_import_commands": ["python3 verify-google"],
                "preferred_drop_path": "/tmp/google-proof.zip",
            },
            artifacts["operator_action_historical_artifacts"],
        )

    def test_main_writes_pass_receipt_from_successful_release_verifier(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="release-ready-receipt-") as temp_dir:
            output_path = Path(temp_dir) / "RELEASE_READY.generated.json"

            with (
                mock.patch.object(module, "OUTPUT_PATH", output_path),
                mock.patch.object(
                    module,
                    "run_authoritative_release_controller",
                    return_value=live_controller_result(module),
                ) as controller_mock,
                mock.patch.object(module, "current_blocking_gate_artifacts", return_value={}),
                mock.patch.object(module, "current_receipt_states", return_value={}),
                mock.patch.object(
                    module,
                    "current_release_truth_root_context",
                    return_value={
                        "root_blocker_ids": [],
                        "root_blockers": [],
                        "root_blockers_generated_at": "",
                        "stable_promotion_command": "",
                        "post_promotion_verify_command": "",
                        "root_release_truth_source": "",
                    },
                ),
                mock.patch.object(
                    module,
                    "release_ready_next_actions",
                    return_value=["Review optional Windows proof handoff."],
                ),
                mock.patch.object(module, "load_json", return_value={}),
            ):
                result = module.main()

            self.assertEqual(0, result)
            payload = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual("pass", payload["status"])
            self.assertEqual("RELEASE_READY", payload["verdict"])
            self.assertEqual(module.supported_release_controller_command(), payload["command"])
            self.assertNotIn("bash", payload["command"])
            self.assertEqual(0, payload["returncode"])
            self.assertFalse(payload["timed_out"])
            self.assertEqual(module.TIMEOUT_SECONDS, payload["timeout_seconds"])
            self.assertTrue(payload["saw_release_ready_marker"])
            self.assertEqual([], payload["not_release_ready_markers"])
            self.assertEqual([], payload["failed_gates"])
            self.assertEqual([], payload["nextActions"])
            self.assertEqual(
                ["Review optional Windows proof handoff."],
                payload["advisoryActions"],
            )
            self.assertEqual(list(module.REQUIRED_RELEASE_VERIFIER_GATES), payload["started_gates"])
            self.assertEqual(list(module.REQUIRED_RELEASE_VERIFIER_GATES), payload["completed_gates"])
            self.assertEqual(module.REQUIRED_RELEASE_VERIFIER_GATES[-1], payload["last_started_gate"])
            self.assertEqual(module.REQUIRED_RELEASE_VERIFIER_GATES[-1], payload["last_completed_gate"])
            self.assertEqual(
                module.RELEASE_VERIFIER_REPLAY_BINDING_CONTRACT,
                payload["release_verifier_binding"]["contract_name"],
            )
            self.assertEqual([], payload["root_blockers"])
            env = controller_mock.call_args.args[0]
            self.assertIsInstance(env, dict)
            self.assertEqual("1", env.get(module.RELEASE_READY_MATERIALIZER_ACTIVE_ENV))
            self.assertEqual("1", env.get("CHUMMER_SKIP_CODEX_HANDOFF_MATERIALIZER"))
            self.assertEqual("0", env[module.SKIP_GOOGLE_OAUTH_RUNTIME_REFRESH_ENV])
            self.assertEqual("0", env[module.SKIP_WINDOWS_RUNTIME_REFRESH_ENV])
            self.assertTrue(payload["authoritative"])
            self.assertFalse(payload["diagnostic"])
            self.assertEqual(
                {
                    "google_oauth": "refresh_live_proof",
                    "windows_installer": "refresh_runtime_receipts",
                },
                payload["proof_refresh_policy"],
            )

    def test_main_rejects_diagnostic_pass_shaped_controller_result(self) -> None:
        module = load_module()
        diagnostic_result = live_controller_result(module)
        diagnostic_result.update(
            {
                "authority_scope": module.DIAGNOSTIC_AUTHORITY_SCOPE,
                "authoritative": False,
                "diagnostic": True,
                "test_only": True,
            }
        )
        with tempfile.TemporaryDirectory(prefix="release-ready-diagnostic-result-") as temp_dir:
            output_path = Path(temp_dir) / "RELEASE_READY.generated.json"
            with (
                mock.patch.object(module, "OUTPUT_PATH", output_path),
                mock.patch.object(
                    module,
                    "run_authoritative_release_controller",
                    return_value=diagnostic_result,
                ),
                mock.patch.object(module, "current_blocking_gate_artifacts", return_value={}),
                mock.patch.object(module, "current_receipt_states", return_value={}),
                mock.patch.object(
                    module,
                    "current_release_truth_root_context",
                    return_value={
                        "root_blocker_ids": [],
                        "root_blockers": [],
                        "root_blockers_generated_at": "",
                        "stable_promotion_command": "",
                        "post_promotion_verify_command": "",
                        "root_release_truth_source": "",
                    },
                ),
                mock.patch.object(module, "release_ready_next_actions", return_value=[]),
                mock.patch.object(module, "load_json", return_value={}),
                mock.patch.object(module, "converge_release_truth_projection") as projection,
            ):
                result = module.main()

            payload = json.loads(output_path.read_text(encoding="utf-8"))

        self.assertEqual(0, result)
        self.assertEqual("fail", payload["status"])
        self.assertFalse(payload["authoritative"])
        self.assertTrue(payload["diagnostic"])
        self.assertTrue(payload["test_only"])
        self.assertIn(
            "FAIL release_verifier_binding: result did not originate from the live controller",
            payload["failures"],
        )
        projection.assert_not_called()

    def test_failed_receipt_keeps_actions_blocking(self) -> None:
        module = load_module()
        payload = {"status": "fail"}

        module.apply_release_ready_actions(payload, ["Resolve the failed gate."])

        self.assertEqual(["Resolve the failed gate."], payload["nextActions"])
        self.assertEqual([], payload["advisoryActions"])

    def test_main_propagates_receipt_only_proof_refresh_policy(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="release-ready-reuse-proofs-") as temp_dir:
            output_path = Path(temp_dir) / "RELEASE_READY.generated.json"
            with (
                mock.patch.object(module, "OUTPUT_PATH", output_path),
                mock.patch.object(
                    module,
                    "run_authoritative_release_controller",
                    return_value=live_controller_result(
                        module,
                        external_write_authorized=True,
                    ),
                ) as controller_mock,
                mock.patch.object(module, "current_blocking_gate_artifacts", return_value={}),
                mock.patch.object(module, "current_receipt_states", return_value={}),
                mock.patch.object(
                    module,
                    "current_release_truth_root_context",
                    return_value={
                        "root_blocker_ids": [],
                        "root_blockers": [],
                        "root_blockers_generated_at": "",
                        "stable_promotion_command": "",
                        "post_promotion_verify_command": "",
                        "root_release_truth_source": "",
                    },
                ),
                mock.patch.object(module, "release_ready_next_actions", return_value=[]),
                mock.patch.object(module, "load_json", return_value={}),
            ):
                result = module.main(
                    [
                        module.EXTERNAL_WRITE_AUTHORIZATION_FLAG,
                        "--skip-google-oauth-runtime-refresh",
                        "--skip-windows-runtime-refresh",
                    ]
                )

            self.assertEqual(0, result)
            env = controller_mock.call_args.args[0]
            self.assertEqual("1", env[module.SKIP_GOOGLE_OAUTH_RUNTIME_REFRESH_ENV])
            self.assertEqual("1", env[module.SKIP_WINDOWS_RUNTIME_REFRESH_ENV])
            self.assertTrue(
                controller_mock.call_args.kwargs["external_write_authorized"]
            )
            payload = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual(
                module.supported_release_controller_command(
                    external_write_authorized=True,
                    skip_google_oauth_runtime_refresh=True,
                    skip_windows_runtime_refresh=True,
                ),
                payload["command"],
            )
            self.assertIn(module.EXTERNAL_WRITE_AUTHORIZATION_FLAG, payload["command"])
            self.assertIn("--skip-google-oauth-runtime-refresh", payload["command"])
            self.assertIn("--skip-windows-runtime-refresh", payload["command"])
            self.assertTrue(payload["external_release_writes_authorized"])
            self.assertEqual(
                {
                    "google_oauth": "verify_existing_receipts",
                    "windows_installer": "verify_existing_receipts",
                },
                payload["proof_refresh_policy"],
            )

    def test_main_writes_fail_receipt_when_release_verifier_times_out(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="release-ready-timeout-") as temp_dir:
            output_path = Path(temp_dir) / "RELEASE_READY.generated.json"

            with (
                mock.patch.object(module, "OUTPUT_PATH", output_path),
                mock.patch.object(
                    module,
                    "run_authoritative_release_controller",
                    return_value=live_controller_result(
                        module,
                        stdout="START verify_live_surface_parity timeout=900s\nstill running\n",
                        returncode=124,
                        timed_out=True,
                    ),
                ),
                mock.patch.object(module, "current_blocking_gate_artifacts", return_value={}),
                mock.patch.object(module, "current_receipt_states", return_value={}),
                mock.patch.object(
                    module,
                    "current_release_truth_root_context",
                    return_value={
                        "root_blocker_ids": [],
                        "root_blockers": [],
                        "root_blockers_generated_at": "",
                        "stable_promotion_command": "",
                        "post_promotion_verify_command": "",
                        "root_release_truth_source": "",
                    },
                ),
                mock.patch.object(module, "release_ready_next_actions", return_value=[]),
                mock.patch.object(module, "load_json", return_value={}),
            ):
                result = module.main()

            self.assertEqual(0, result)
            payload = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual("fail", payload["status"])
            self.assertEqual("NOT_RELEASE_READY", payload["verdict"])
            self.assertEqual(module.supported_release_controller_command(), payload["command"])
            self.assertNotIn("bash", payload["command"])
            self.assertEqual(124, payload["returncode"])
            self.assertTrue(payload["timed_out"])
            self.assertIn(f"verify_release_ready timed out after {module.TIMEOUT_SECONDS}s", payload["failures"])
            self.assertIn("verify_release_ready last started gate: verify_live_surface_parity", payload["failures"])
            self.assertEqual(["verify_release_ready"], payload["failed_gates"])
            self.assertEqual(["verify_live_surface_parity"], payload["started_gates"])
            self.assertEqual([], payload["completed_gates"])
            self.assertEqual("verify_live_surface_parity", payload["last_started_gate"])
            self.assertEqual("", payload["last_completed_gate"])
            self.assertEqual([], payload["root_blockers"])

    def test_controller_gate_terminates_child_group_on_sigterm(self) -> None:
        module = load_module()

        process = mock.Mock(pid=1234, returncode=None)
        process.poll.return_value = None
        original_sigint = module.signal.getsignal(module.signal.SIGINT)
        original_sigterm = module.signal.getsignal(module.signal.SIGTERM)

        signal_sent = False

        def fake_poll() -> None:
            nonlocal signal_sent
            if not signal_sent:
                signal_sent = True
                handler = module.signal.getsignal(module.signal.SIGTERM)
                assert callable(handler)
                handler(module.signal.SIGTERM, None)
            return None

        process.poll.side_effect = fake_poll
        process.wait.return_value = 0

        with (
            mock.patch.object(module.subprocess, "Popen", return_value=process),
            mock.patch.object(module.os, "killpg") as killpg,
        ):
            with self.assertRaises(SystemExit) as raised:
                module.run_controller_gate_command(
                    {
                        "command": "true",
                        "cwd": str(Path.cwd()),
                        "timeout_seconds": 7,
                    },
                    {
                        "CHUMMER_RELEASE_READY_GATE_KILL_AFTER_SECONDS": "3",
                    },
                )

        self.assertEqual(128 + module.signal.SIGTERM, raised.exception.code)
        killpg.assert_called_once_with(1234, module.signal.SIGTERM)
        self.assertIs(module.signal.getsignal(module.signal.SIGINT), original_sigint)
        self.assertIs(module.signal.getsignal(module.signal.SIGTERM), original_sigterm)

    def test_main_skips_global_verifier_when_current_receipts_already_block_release(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="release-ready-current-blockers-") as temp_dir:
            output_path = Path(temp_dir) / "RELEASE_READY.generated.json"
            release_blockers_path = Path(temp_dir) / "RELEASE_BLOCKERS.generated.json"
            release_blockers_path.write_text(
                json.dumps(
                    {
                        "generated_at": "2026-07-06T05:18:22Z",
                        "blockers": [
                            {
                                "blocker_id": "release_posture:non_flagship_channel",
                                "stable_promotion_command": "bash /tmp/promote-stable.sh",
                                "post_promotion_verify_command": "python3 /tmp/post-verify.py",
                            },
                            {
                                "blocker_id": "release_truth:windows_installer_visual_audit",
                            },
                        ],
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            with (
                mock.patch.object(module, "OUTPUT_PATH", output_path),
                mock.patch.object(module, "RELEASE_BLOCKERS_JSON", release_blockers_path),
                mock.patch.object(module, "current_blocker_precheck_enabled", return_value=True),
                mock.patch.object(
                    module,
                    "collect_current_blocking_failures",
                    return_value=[
                        "FAIL release_channel: release channel supportability is not gold_supported",
                        "FAIL windows_installer_visual_audit: Windows installer visual audit source digest does not match promoted installer",
                    ],
                ),
                mock.patch.object(
                    module,
                    "current_blocking_gate_artifacts",
                    return_value={
                        "google_oauth_linking_proof": {
                            "request_receipt_path": "/tmp/google-request.json",
                            "proof_operator_action_still_required": True,
                            "operator_ask_delivery_needs_resend": True,
                            "operator_ask_resend_command": "python3 resend-google",
                            "import_command": "python3 import-google",
                            "required_operator_evidence_path": "/tmp/google-evidence.json",
                        },
                        "windows_installer_visual_audit": {
                            "preferred_drop_path": "/tmp/windows-proof.zip",
                            "request_operator_action_still_required": True,
                            "operator_ask_delivery_needs_resend": True,
                            "operator_ask_resend_command": "python3 resend-windows",
                            "import_command": "python3 import-windows",
                            "stage_windows_visual_proof_handoff_next_actions": ["Capture fresh Windows proof on the native host."],
                        },
                    },
                ),
                mock.patch.object(
                    module,
                    "current_receipt_states",
                    return_value={
                        "release_channel": {
                            "path": "/tmp/RELEASE_CHANNEL.generated.json",
                            "exists": False,
                            "load_status": "missing",
                            "status": "",
                            "contract_name": "",
                            "generated_at_utc": "",
                            "summary_readiness_load_status": "",
                        },
                    },
                ),
                mock.patch.object(module.subprocess, "Popen") as popen,
            ):
                result = module.main()

            self.assertEqual(0, result)
            popen.assert_not_called()
            payload = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual("fail", payload["status"])
            self.assertEqual("NOT_RELEASE_READY", payload["verdict"])
            self.assertEqual(module.supported_release_controller_command(), payload["command"])
            self.assertNotIn("bash", payload["command"])
            self.assertIsNone(payload["returncode"])
            self.assertFalse(payload["timed_out"])
            self.assertTrue(payload["global_verifier_skipped_due_current_blockers"])
            self.assertIn(
                "FAIL release_channel: release channel supportability is not gold_supported",
                payload["failures"],
            )
            self.assertEqual(
                "current receipts already prove launch blockers",
                payload["global_verifier_skip_reason"],
            )
            self.assertEqual(["release_channel", "windows_installer_visual_audit"], payload["failed_gates"])
            self.assertEqual(
                {
                    "path": "/tmp/RELEASE_CHANNEL.generated.json",
                    "exists": False,
                    "load_status": "missing",
                    "status": "",
                    "contract_name": "",
                    "generated_at_utc": "",
                    "summary_readiness_load_status": "",
                },
                payload["current_receipt_states"]["release_channel"],
            )
            self.assertEqual(
                ["release_posture:non_flagship_channel", "release_truth:windows_installer_visual_audit"],
                payload["root_blocker_ids"],
            )
            self.assertEqual(
                [
                    {
                        "blocker_id": "release_posture:non_flagship_channel",
                        "stable_promotion_command": "bash /tmp/promote-stable.sh",
                        "post_promotion_verify_command": "python3 /tmp/post-verify.py",
                        "id": "release_posture:non_flagship_channel",
                    },
                    {
                        "blocker_id": "release_truth:windows_installer_visual_audit",
                        "id": "release_truth:windows_installer_visual_audit",
                    },
                ],
                payload["root_blockers"],
            )
            self.assertEqual("2026-07-06T05:18:22Z", payload["root_blockers_generated_at"])
            self.assertEqual("bash /tmp/promote-stable.sh", payload["stable_promotion_command"])
            self.assertEqual("python3 /tmp/post-verify.py", payload["post_promotion_verify_command"])
            self.assertEqual(str(release_blockers_path), payload["root_release_truth_source"])
            self.assertIn("Resend the current Google OAuth operator ask: python3 resend-google", payload["nextActions"])
            self.assertIn("When the Google OAuth evidence bundle is ready, import it: python3 import-google", payload["nextActions"])
            self.assertIn(
                "That --verify import reruns the full intake-request post-import gate chain, not just the first verifier.",
                payload["nextActions"],
            )
            self.assertIn("Resend the current Windows proof operator ask: python3 resend-windows", payload["nextActions"])
            self.assertIn("Capture fresh Windows proof on the native host.", payload["nextActions"])
            self.assertTrue(any("promote the live release channel" in item for item in payload["nextActions"]))
            self.assertTrue(any("Stable promotion command:" in item for item in payload["nextActions"]))
            self.assertTrue(any("publish-download-bundle.sh" in item for item in payload["nextActions"]))
            self.assertEqual("/tmp/google-request.json", payload["blocking_gate_artifacts"]["google_oauth_linking_proof"]["request_receipt_path"])
            self.assertEqual("/tmp/windows-proof.zip", payload["blocking_gate_artifacts"]["windows_installer_visual_audit"]["preferred_drop_path"])

    def test_collect_current_blocking_failures_reports_malformed_flagship_gate_receipt(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="release-ready-flagship-gate-invalid-") as temp_dir:
            root = Path(temp_dir)
            published = root / "published"
            registry = root / "registry"
            published.mkdir(parents=True, exist_ok=True)
            registry.mkdir(parents=True, exist_ok=True)

            (registry / "RELEASE_CHANNEL.generated.json").write_text(
                json.dumps(
                    {
                        "status": "published",
                        "version": "run-test",
                        "channel": "stable",
                        "supportabilityState": "gold_supported",
                        "rolloutState": "public_stable",
                        "publishedAt": module.now_iso(),
                    }
                ),
                encoding="utf-8",
            )
            (published / "FLAGSHIP_PRODUCT_READINESS_GATE.generated.json").write_text("{not json}\n", encoding="utf-8")
            (published / "PUBLIC_EDGE_POSTDEPLOY_GATE.generated.json").write_text(
                json.dumps(passing_public_edge_postdeploy_payload(module)),
                encoding="utf-8",
            )
            (published / "WINDOWS_INSTALLER_VISUAL_AUDIT.generated.json").write_text(
                json.dumps({"status": "pass"}),
                encoding="utf-8",
            )
            (published / "GOOGLE_OAUTH_LINKING_PROOF.generated.json").write_text(
                json.dumps({"status": "pass"}),
                encoding="utf-8",
            )

            with (
                mock.patch.object(module, "PUBLISHED_ROOT", published),
                mock.patch.object(module, "REGISTRY_PUBLISHED_ROOT", registry),
            ):
                failures = module.collect_current_blocking_failures()
                states = module.current_receipt_states()

        self.assertEqual(
            [
                f"FAIL flagship_product_readiness: flagship_product_readiness receipt is malformed: {published / 'FLAGSHIP_PRODUCT_READINESS_GATE.generated.json'}",
            ],
            failures,
        )
        self.assertEqual("invalid", states["flagship_product_readiness"]["load_status"])
        self.assertTrue(states["flagship_product_readiness"]["exists"])

    def test_current_precheck_surfaces_auxiliary_supply_chain_and_observability_receipts(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="release-ready-auxiliary-gates-") as temp_dir:
            root = Path(temp_dir)
            published = root / "published"
            registry = root / "registry"
            published.mkdir(parents=True, exist_ok=True)
            registry.mkdir(parents=True, exist_ok=True)

            (registry / "RELEASE_CHANNEL.generated.json").write_text(
                json.dumps(
                    {
                        "status": "published",
                        "version": "run-test",
                        "channel": "stable",
                        "supportabilityState": "gold_supported",
                        "rolloutState": "public_stable",
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            (published / "FLAGSHIP_PRODUCT_READINESS_GATE.generated.json").write_text(
                json.dumps(
                    {
                        "contract_name": module.FLAGSHIP_PRODUCT_READINESS_GATE_CONTRACT_NAME,
                        "status": "pass",
                        "verdict": module.FLAGSHIP_PRODUCT_READY_VERDICT,
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            for name in (
                "GOOGLE_OAUTH_LINKING_PROOF.generated.json",
                "PUBLIC_EDGE_POSTDEPLOY_GATE.generated.json",
                "WINDOWS_INSTALLER_VISUAL_AUDIT.generated.json",
            ):
                (published / name).write_text(
                    json.dumps({"status": "pass"}) + "\n",
                    encoding="utf-8",
                )

            supply_chain = published / "SUPPLY_CHAIN_RELEASE_GATE.generated.json"
            supply_chain.write_text(
                json.dumps(
                    {
                        "status": "fail",
                        "verdict": "SUPPLY_CHAIN_BLOCKED",
                        "blockers": ["provenance:not_available"],
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            observability = published / "PUBLIC_EDGE_OBSERVABILITY_RELEASE_GATE.generated.json"
            observability.write_text(
                json.dumps(
                    {
                        "status": "fail",
                        "verdict": "OBSERVABILITY_RELEASE_BLOCKED",
                        "failures": ["operator_proof: operator proof is missing"],
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            with (
                mock.patch.object(module, "PUBLISHED_ROOT", published),
                mock.patch.object(module, "REGISTRY_PUBLISHED_ROOT", registry),
                mock.patch.object(
                    module,
                    "CURRENT_AUXILIARY_RELEASE_RECEIPTS",
                    (
                        ("supply_chain_evidence", supply_chain),
                        ("public_edge_observability_release", observability),
                    ),
                ),
                mock.patch.object(module, "current_blocking_gate_artifacts", return_value={}),
                mock.patch.object(
                    module,
                    "public_edge_postdeploy_release_blocking_reasons",
                    return_value=[],
                ),
            ):
                failures = module.collect_current_blocking_failures()
                states = module.current_receipt_states()

        self.assertEqual(
            [
                "FAIL supply_chain_evidence: provenance:not_available",
                "FAIL public_edge_observability_release: operator_proof: operator proof is missing",
            ],
            failures,
        )
        self.assertEqual("fail", states["supply_chain_evidence"]["status"])
        self.assertEqual("SUPPLY_CHAIN_BLOCKED", states["supply_chain_evidence"]["verdict"])
        self.assertEqual("fail", states["public_edge_observability_release"]["status"])
        self.assertEqual(
            "OBSERVABILITY_RELEASE_BLOCKED",
            states["public_edge_observability_release"]["verdict"],
        )

    def test_current_precheck_rejects_pass_observability_receipt_bound_to_old_release(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="release-ready-observability-drift-") as temp_dir:
            root = Path(temp_dir)
            published = root / "published"
            registry = root / "registry"
            published.mkdir(parents=True)
            registry.mkdir(parents=True)

            manifest_path = registry / "RELEASE_CHANNEL.generated.json"
            manifest_path.write_text(
                json.dumps(
                    {
                        "status": "published",
                        "version": "run-current",
                        "channel": "stable",
                        "supportabilityState": "gold_supported",
                        "rolloutState": "public_stable",
                        "publishedAt": module.now_iso(),
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            (published / "FLAGSHIP_PRODUCT_READINESS_GATE.generated.json").write_text(
                json.dumps(
                    {
                        "contract_name": module.FLAGSHIP_PRODUCT_READINESS_GATE_CONTRACT_NAME,
                        "status": "pass",
                        "verdict": module.FLAGSHIP_PRODUCT_READY_VERDICT,
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            for name in (
                "GOOGLE_OAUTH_LINKING_PROOF.generated.json",
                "PUBLIC_EDGE_POSTDEPLOY_GATE.generated.json",
                "WINDOWS_INSTALLER_VISUAL_AUDIT.generated.json",
            ):
                (published / name).write_text(
                    json.dumps({"status": "pass"}) + "\n",
                    encoding="utf-8",
                )

            observability = published / "PUBLIC_EDGE_OBSERVABILITY_RELEASE_GATE.generated.json"
            observability.write_text(
                json.dumps(
                    {
                        "contract_name": module.PUBLIC_EDGE_OBSERVABILITY_GATE_CONTRACT_NAME,
                        "status": "pass",
                        "verdict": module.PUBLIC_EDGE_OBSERVABILITY_READY_VERDICT,
                        "generated_at_utc": module.now_iso(),
                        "failure_count": 0,
                        "failures": [],
                        "release_candidate": {
                            "sha256": "0" * 64,
                            "version": "run-old",
                            "channel": "stable",
                        },
                        "checks": [
                            {"id": check_id, "status": "pass"}
                            for check_id in (
                                "runtime:program",
                                "runtime:readiness",
                                "runtime:instruments",
                                "runtime:middleware",
                                "runtime:compose",
                                "release_candidate",
                                "policy",
                                "operator_proof",
                            )
                        ],
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            with (
                mock.patch.object(module, "PUBLISHED_ROOT", published),
                mock.patch.object(module, "REGISTRY_PUBLISHED_ROOT", registry),
                mock.patch.object(
                    module,
                    "CURRENT_AUXILIARY_RELEASE_RECEIPTS",
                    (("public_edge_observability_release", observability),),
                ),
                mock.patch.object(module, "current_blocking_gate_artifacts", return_value={}),
                mock.patch.object(
                    module,
                    "public_edge_postdeploy_release_blocking_reasons",
                    return_value=[],
                ),
            ):
                failures = module.collect_current_blocking_failures()
                states = module.current_receipt_states()

        self.assertTrue(
            any(
                "release_candidate.sha256 does not match current release bytes" in failure
                for failure in failures
            )
        )
        self.assertEqual("fail", states["public_edge_observability_release"]["status"])
        self.assertEqual("pass", states["public_edge_observability_release"]["raw_status"])
        self.assertTrue(states["public_edge_observability_release"]["semantic_failures"])

    def test_replay_mode_keeps_current_blocker_precheck_enabled(self) -> None:
        module = load_module()
        args = module.parse_args(
            [
                "--global-verifier-output",
                "/tmp/release-verifier.stdout",
                "--global-verifier-output-sha256",
                "a" * 64,
            ]
        )

        self.assertTrue(module.current_blocker_precheck_enabled(args))

    def test_current_receipt_states_refreshes_default_flagship_gate_before_loading(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="release-ready-flagship-gate-refresh-") as temp_dir:
            root = Path(temp_dir)
            published = root / "published"
            registry = root / "registry"
            published.mkdir(parents=True, exist_ok=True)
            registry.mkdir(parents=True, exist_ok=True)

            (registry / "RELEASE_CHANNEL.generated.json").write_text(
                json.dumps(
                    {
                        "status": "published",
                        "version": "run-test",
                        "channel": "stable",
                        "supportabilityState": "gold_supported",
                        "rolloutState": "public_stable",
                        "publishedAt": module.now_iso(),
                    }
                ),
                encoding="utf-8",
            )
            gate_path = published / "FLAGSHIP_PRODUCT_READINESS_GATE.generated.json"
            gate_path.write_text(
                json.dumps(
                    {
                        "generated_at_utc": "2026-07-06T05:00:00Z",
                        "status": "fail",
                        "launch_critical_nested_blocker_count": 9,
                        "coverage_gap_keys": ["stale_gap"],
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            for name in (
                "GOOGLE_OAUTH_LINKING_PROOF.generated.json",
                "PUBLIC_EDGE_POSTDEPLOY_GATE.generated.json",
                "WINDOWS_INSTALLER_VISUAL_AUDIT.generated.json",
            ):
                (published / name).write_text(json.dumps({"status": "pass"}) + "\n", encoding="utf-8")

            def fake_run(args, **_kwargs):
                if args[:2] == ["python3", "scripts/verify_flagship_product_readiness_gate.py"]:
                    gate_path.write_text(
                        json.dumps(
                            {
                                "generated_at_utc": "2026-07-06T05:35:00Z",
                                "status": "fail",
                                "launch_critical_nested_blocker_count": 6,
                                "coverage_gap_keys": [],
                            }
                        )
                        + "\n",
                        encoding="utf-8",
                    )
                return mock.Mock(returncode=0, stdout="", stderr="")

            with (
                mock.patch.object(module, "PUBLISHED_ROOT", published),
                mock.patch.object(module, "REGISTRY_PUBLISHED_ROOT", registry),
                mock.patch.object(module, "DEFAULT_FLAGSHIP_PRODUCT_READINESS_GATE_PATH", gate_path),
                mock.patch.object(
                    module,
                    "DEFAULT_FLAGSHIP_PRODUCT_READINESS_GATE_REFRESH_COMMAND",
                    [
                        "python3",
                        "scripts/verify_flagship_product_readiness_gate.py",
                        "--summary-output",
                        str(gate_path),
                    ],
                ),
                mock.patch.object(module.subprocess, "run", side_effect=fake_run) as run,
            ):
                states = module.current_receipt_states()

        run.assert_called_once()
        self.assertEqual(
            "2026-07-06T05:35:00Z",
            states["flagship_product_readiness"]["generated_at_utc"],
        )
        self.assertEqual("fail", states["flagship_product_readiness"]["status"])

    def test_current_receipt_states_fail_close_pass_shaped_receipts_and_preserve_raw_status(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="release-ready-receipt-states-fail-close-") as temp_dir:
            root = Path(temp_dir)
            published = root / "published"
            registry = root / "registry"
            published.mkdir(parents=True, exist_ok=True)
            registry.mkdir(parents=True, exist_ok=True)

            (registry / "RELEASE_CHANNEL.generated.json").write_text(
                json.dumps(
                    {
                        "status": "published",
                        "version": "run-test",
                        "channel": "stable",
                        "supportabilityState": "gold_supported",
                        "rolloutState": "public_stable",
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            (published / "FLAGSHIP_PRODUCT_READINESS_GATE.generated.json").write_text(
                json.dumps(
                    {
                        "contract_name": module.FLAGSHIP_PRODUCT_READINESS_GATE_CONTRACT_NAME,
                        "generated_at_utc": "2026-07-07T11:14:19Z",
                        "status": "pass",
                        "verdict": module.FLAGSHIP_PRODUCT_NOT_READY_VERDICT,
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            (published / "WINDOWS_INSTALLER_VISUAL_AUDIT.generated.json").write_text(
                json.dumps(
                    {
                        "status": "pass",
                        "generated_at_utc": "2026-07-07T11:13:50Z",
                        "failures": [
                            "Windows installer visual audit source digest does not match promoted installer",
                        ],
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            for name in (
                "GOOGLE_OAUTH_LINKING_PROOF.generated.json",
                "PUBLIC_EDGE_POSTDEPLOY_GATE.generated.json",
            ):
                (published / name).write_text(
                    json.dumps({"status": "pass"}) + "\n",
                    encoding="utf-8",
                )

            with (
                mock.patch.object(module, "PUBLISHED_ROOT", published),
                mock.patch.object(module, "REGISTRY_PUBLISHED_ROOT", registry),
                mock.patch.object(module, "refresh_flagship_product_readiness_gate") as refresh_mock,
            ):
                states = module.current_receipt_states()

        refresh_mock.assert_called_once_with(published / "FLAGSHIP_PRODUCT_READINESS_GATE.generated.json")
        self.assertEqual("fail", states["flagship_product_readiness"]["status"])
        self.assertEqual("pass", states["flagship_product_readiness"]["raw_status"])
        self.assertEqual("fail", states["windows_installer_visual_audit"]["status"])
        self.assertEqual("pass", states["windows_installer_visual_audit"]["raw_status"])

    def test_release_ready_next_actions_dedupes_google_and_windows_resend_when_nested_actions_already_carry_same_command(self) -> None:
        module = load_module()

        actions = module.release_ready_next_actions(
            {
                "google_oauth_linking_proof": {
                    "proof_operator_action_still_required": True,
                    "operator_ask_delivery_needs_resend": True,
                    "operator_ask_resend_command": "python3 resend-google",
                    "next_actions": [
                        "Resend the current Google operator ask before waiting for more evidence: python3 resend-google",
                    ],
                },
                "windows_installer_visual_audit": {
                    "request_operator_action_still_required": True,
                    "operator_ask_delivery_needs_resend": True,
                    "operator_ask_resend_command": "python3 resend-windows",
                    "next_actions": [
                        "Resend the current Windows proof operator ask before waiting for more evidence: python3 resend-windows",
                    ],
                },
            },
            {
                "status": "published",
                "channel": "stable",
                "version": "run-test",
                "supportabilityState": "gold_supported",
                "rolloutState": "public_stable",
            },
        )

        self.assertEqual(
            [
                "Resend the current Google operator ask before waiting for more evidence: python3 resend-google",
                "Resend the current Windows proof operator ask before waiting for more evidence: python3 resend-windows",
            ],
            actions,
        )

    def test_release_ready_next_actions_exposes_prepared_but_unsent_windows_ask(self) -> None:
        module = load_module()

        actions = module.release_ready_next_actions(
            {
                "windows_installer_visual_audit": {
                    "pass": False,
                    "request_operator_action_still_required": True,
                    "operator_ask_delivery_receipt_exists": False,
                    "operator_ask_send_command": "python3 send-windows",
                },
            },
            {
                "status": "published",
                "channel": "stable",
                "version": "run-test",
                "supportabilityState": "gold_supported",
                "rolloutState": "public_stable",
            },
        )

        self.assertEqual(
            ["Send the prepared current Windows proof operator ask: python3 send-windows"],
            actions,
        )

    def test_release_ready_next_actions_include_windows_stage_proof_locator_hints(self) -> None:
        module = load_module()

        actions = module.release_ready_next_actions(
            {
                "windows_installer_visual_audit": {
                    "pass": False,
                    "request_operator_action_still_required": True,
                    "auto_import_receipt_path": "/tmp/WINDOWS_INSTALLER_VISUAL_AUDIT_AUTO_IMPORT.generated.json",
                    "auto_import_stage_visual_proof_receipt_count": 8,
                    "auto_import_stage_visual_proof_receipt_note": (
                        "Stage/nightly Windows proof receipts were found, but none match the promoted installer digest."
                    ),
                    "auto_import_stale_stage_visual_proof_receipts": [
                        {"path": "/tmp/stage-a/WINDOWS_INSTALLER_VISUAL_PROOF.generated.json"},
                        {"path": "/tmp/stage-b/WINDOWS_INSTALLER_VISUAL_PROOF.generated.json"},
                    ],
                },
            },
            {
                "status": "published",
                "channel": "stable",
                "version": "run-test",
                "supportabilityState": "gold_supported",
                "rolloutState": "public_stable",
            },
        )

        self.assertIn(
            "Review surfaced Windows stage/nightly proof hints in /tmp/WINDOWS_INSTALLER_VISUAL_AUDIT_AUTO_IMPORT.generated.json; visual-proof receipts=8, startup-smoke receipts=0. Use them only to locate old capture output for recapture or bundle packaging. Stage/nightly Windows proof receipts were found, but none match the promoted installer digest.",
            actions,
        )
        self.assertIn(
            "Sample stale Windows proof hint paths: /tmp/stage-a/WINDOWS_INSTALLER_VISUAL_PROOF.generated.json; /tmp/stage-b/WINDOWS_INSTALLER_VISUAL_PROOF.generated.json",
            actions,
        )

    def test_release_ready_next_actions_prefers_windows_primary_receipt_actions_over_stage_handoff_duplicates(self) -> None:
        module = load_module()

        actions = module.release_ready_next_actions(
            {
                "windows_installer_visual_audit": {
                    "pass": False,
                    "request_operator_action_still_required": True,
                    "auto_import_receipt_path": "/tmp/WINDOWS_INSTALLER_VISUAL_AUDIT_AUTO_IMPORT.generated.json",
                    "auto_import_stage_visual_proof_receipt_count": 8,
                    "auto_import_stage_visual_proof_receipt_note": (
                        "Stage/nightly Windows proof receipts were found, but none match the promoted installer digest."
                    ),
                    "auto_import_stale_stage_visual_proof_receipts": [
                        {"path": "/tmp/stage-a/WINDOWS_INSTALLER_VISUAL_PROOF.generated.json"},
                        {"path": "/tmp/stage-b/WINDOWS_INSTALLER_VISUAL_PROOF.generated.json"},
                    ],
                    "import_command": "python3 import-windows",
                    "stage_windows_visual_proof_handoff_next_actions": [
                        "On a real Windows host, open the repo checkout that contains the capture script and run powershell.",
                        "Confirm WINDOWS_INSTALLER_VISUAL_PROOF.generated.json is written under /tmp/stage.",
                    ],
                    "next_actions": [
                        "Review surfaced Windows stage/nightly proof hints in /tmp/WINDOWS_INSTALLER_VISUAL_AUDIT_AUTO_IMPORT.generated.json; visual-proof receipts=8, startup-smoke receipts=0. Stage/nightly Windows proof receipts were found, but none match the promoted installer digest. Use them only to locate old capture output for recapture or bundle packaging.",
                        "Sample stale Windows proof hint paths: /tmp/stage-a/WINDOWS_INSTALLER_VISUAL_PROOF.generated.json; /tmp/stage-b/WINDOWS_INSTALLER_VISUAL_PROOF.generated.json",
                        "Preferred remote path: run the native Windows proof runner from a controlled Windows host; it captures native Windows evidence only and does not publish downloads.",
                        "If proof came from a remote Windows runner, import it with: python3 import-windows",
                    ],
                },
            },
            {
                "status": "published",
                "channel": "stable",
                "version": "run-test",
                "supportabilityState": "gold_supported",
                "rolloutState": "public_stable",
            },
        )

        self.assertIn(
            "Preferred remote path: run the native Windows proof runner from a controlled Windows host; it captures native Windows evidence only and does not publish downloads.",
            actions,
        )
        self.assertIn(
            "If proof came from a remote Windows runner, import it with: python3 import-windows",
            actions,
        )
        self.assertIn(
            "Review surfaced Windows stage/nightly proof hints in /tmp/WINDOWS_INSTALLER_VISUAL_AUDIT_AUTO_IMPORT.generated.json; visual-proof receipts=8, startup-smoke receipts=0. Stage/nightly Windows proof receipts were found, but none match the promoted installer digest. Use them only to locate old capture output for recapture or bundle packaging.",
            actions,
        )
        self.assertIn(
            "Sample stale Windows proof hint paths: /tmp/stage-a/WINDOWS_INSTALLER_VISUAL_PROOF.generated.json; /tmp/stage-b/WINDOWS_INSTALLER_VISUAL_PROOF.generated.json",
            actions,
        )
        self.assertNotIn(
            "When the Windows gold proof bundle is ready, import it: python3 import-windows",
            actions,
        )
        self.assertNotIn(
            "On a real Windows host, open the repo checkout that contains the capture script and run powershell.",
            actions,
        )
        self.assertNotIn(
            "Confirm WINDOWS_INSTALLER_VISUAL_PROOF.generated.json is written under /tmp/stage.",
            actions,
        )

    def test_release_ready_next_actions_skips_google_follow_up_when_google_proof_is_already_green(self) -> None:
        module = load_module()

        actions = module.release_ready_next_actions(
            {
                "google_oauth_linking_proof": {
                    "pass": True,
                    "proof_operator_action_still_required": False,
                    "operator_ask_delivery_needs_resend": True,
                    "operator_ask_resend_command": "python3 resend-google",
                    "import_command": "python3 import-google",
                    "required_operator_evidence_path": "/tmp/google-evidence.json",
                    "next_actions": ["Do not keep this once Google is green."],
                },
                "windows_installer_visual_audit": {
                    "pass": False,
                    "request_operator_action_still_required": True,
                    "operator_ask_delivery_needs_resend": True,
                    "operator_ask_resend_command": "python3 resend-windows",
                },
            },
            {
                "status": "published",
                "channel": "stable",
                "version": "run-test",
                "supportabilityState": "gold_supported",
                "rolloutState": "public_stable",
            },
        )

        self.assertNotIn("Resend the current Google OAuth operator ask: python3 resend-google", actions)
        self.assertNotIn("When the Google OAuth evidence bundle is ready, import it: python3 import-google", actions)
        self.assertNotIn("Required Google OAuth operator evidence receipt: /tmp/google-evidence.json", actions)
        self.assertIn("Resend the current Windows proof operator ask: python3 resend-windows", actions)

    def test_release_ready_next_actions_skips_google_follow_up_when_google_is_effectively_green(self) -> None:
        module = load_module()

        actions = module.release_ready_next_actions(
            {
                "google_oauth_linking_proof": {
                    "pass": False,
                    "release_truth_effective_pass": True,
                    "proof_operator_action_still_required": False,
                    "operator_ask_delivery_needs_resend": True,
                    "operator_ask_resend_command": "python3 resend-google",
                    "import_command": "python3 import-google",
                    "required_operator_evidence_path": "/tmp/google-evidence.json",
                    "next_actions": ["Do not keep this once Google is effectively green."],
                },
                "windows_installer_visual_audit": {
                    "pass": False,
                    "request_operator_action_still_required": True,
                    "operator_ask_delivery_needs_resend": True,
                    "operator_ask_resend_command": "python3 resend-windows",
                },
            },
            {
                "status": "published",
                "channel": "stable",
                "version": "run-test",
                "supportabilityState": "gold_supported",
                "rolloutState": "public_stable",
            },
        )

        self.assertNotIn("Resend the current Google OAuth operator ask: python3 resend-google", actions)
        self.assertNotIn("When the Google OAuth evidence bundle is ready, import it: python3 import-google", actions)
        self.assertNotIn("Required Google OAuth operator evidence receipt: /tmp/google-evidence.json", actions)
        self.assertIn("Resend the current Windows proof operator ask: python3 resend-windows", actions)

    def test_release_ready_next_actions_include_explicit_stable_publish_command(self) -> None:
        module = load_module()

        actions = module.release_ready_next_actions(
            {
                "windows_installer_visual_audit": {
                    "pass": False,
                    "request_operator_action_still_required": True,
                    "stage_release_build_handoff_path": "/tmp/current-live-shelf/RELEASE_BUILD_HANDOFF.generated.json",
                },
            },
            {
                "status": "published",
                "channel": "preview",
                "version": "run-test",
                "publishedAt": "2026-07-06T00:00:00Z",
                "supportabilityState": "preview_supported",
                "rolloutState": "promoted_preview",
            },
        )

        self.assertIn(
            "After the missing operator proofs are green, promote the live release channel to a public stable lane with gold_supported supportability.",
            actions,
        )
        self.assertTrue(any(item.startswith("Stable promotion command: RELEASE_CHANNEL=public_stable ") for item in actions))
        self.assertTrue(any("RELEASE_VERSION=run-test" in item for item in actions))
        self.assertTrue(any("RELEASE_PUBLISHED_AT=2026-07-06T00:00:00Z" in item for item in actions))
        self.assertTrue(any("publish-download-bundle.sh" in item for item in actions))
        self.assertTrue(any("/tmp/current-live-shelf" in item for item in actions))
        self.assertTrue(any("materialize_release_ready_receipt.py --force-global-verifier" in item for item in actions))
        self.assertTrue(any("materialize_codex_flagship_handoff.py --timestamp" in item for item in actions))

    def test_current_blocking_gate_artifacts_collects_google_and_windows_request_details(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="release-ready-blocking-artifacts-") as temp_dir:
            root = Path(temp_dir)
            published = root / "published"
            published.mkdir(parents=True, exist_ok=True)
            snapshot_audit = root / "PUBLIC_RELEASE_SNAPSHOT_READONLY_AUDIT.generated.json"
            release_blockers_path = root / "RELEASE_BLOCKERS.generated.json"
            watcher_state_path = root / "state" / "windows_installer_gold_proof_watcher.generated.json"
            telegram_root = root / "telegram"
            telegram_root.mkdir(parents=True, exist_ok=True)
            google_ask_text_path = root / "CURRENT_GOOGLE_OAUTH_LINKING_OPERATOR_ASK.txt"
            google_ask_metadata_path = root / "CURRENT_GOOGLE_OAUTH_LINKING_OPERATOR_ASK.generated.json"
            google_ask_text_path.write_text("google ask current\n", encoding="utf-8")
            google_ask_metadata_path.write_text("{}\n", encoding="utf-8")
            windows_current_message_path = root / "CURRENT_WINDOWS_INSTALLER_VISUAL_AUDIT_OPERATOR_ASK.txt"
            windows_current_metadata_path = root / "CURRENT_WINDOWS_INSTALLER_VISUAL_AUDIT_OPERATOR_ASK.generated.json"
            release_blockers_path.write_text(
                json.dumps(
                    {
                        "generated_at": "2026-07-06T05:18:22Z",
                        "blockers": [
                            {
                                "blocker_id": "release_posture:non_flagship_channel",
                                "stable_promotion_command": "bash /tmp/promote-stable.sh",
                                "post_promotion_verify_command": "python3 /tmp/post-verify.py",
                            },
                            {
                                "blocker_id": "release_truth:windows_installer_visual_audit",
                            },
                        ],
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            snapshot_audit.write_text(
                json.dumps(
                    {
                        "status": "pass",
                        "verdict": "SNAPSHOT_CONSISTENT_NOT_LAUNCH_READY",
                        "summary": "Snapshot is internally consistent with current launch truth, but the release is not launch-ready.",
                        "expected_top_level_blocker_ids": [
                            "release_posture:non_flagship_channel",
                            "release_truth:windows_installer_visual_audit",
                        ],
                        "expected_release_truth_blockers": ["windows_installer_visual_audit"],
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            (published / "GOOGLE_OAUTH_LINKING_PROOF.generated.json").write_text(
                json.dumps(
                    {
                        "contract_name": "chummer.run.google_oauth_linking_proof",
                        "proof_contract_version": 2,
                        "status": "fail",
                        "base_url": "https://chummer.run",
                        "quick_handoff_probe": {"pass": True},
                        "signed_in_link_handoff": {"status": "operator_required", "pass": False},
                        "operator_end_to_end_evidence": {
                            "pass": False,
                            "exists": False,
                            "path": "/tmp/operator-evidence.json",
                            "failures": ["missing operator evidence receipt: /tmp/operator-evidence.json"],
                        },
                        "failures": [
                            "operator_end_to_end_evidence: missing operator evidence receipt: /tmp/operator-evidence.json",
                        ],
                        "operator_request_artifacts": {
                            "pass": True,
                            "request_receipt_path": "/tmp/google-request.json",
                            "required_operator_evidence_path": "/tmp/operator-evidence.json",
                            "operator_ask_text_path": str(google_ask_text_path),
                            "operator_ask_metadata_path": str(google_ask_metadata_path),
                            "operator_evidence_template_path": "/tmp/GOOGLE_OAUTH_LINKING_OPERATOR_EVIDENCE.template.generated.json",
                            "operator_ask_send_command": f"python3 scripts/send_telegram_message_via_ea.py --text-file {google_ask_text_path} --receipt-name google.receipt.json",
                            "operator_ask_receipt_name": "google.receipt.json",
                            "failures": [],
                        },
                        "next_actions": [
                            "Capture a real browser-backed Google linking proof receipt at /tmp/operator-evidence.json.",
                        ],
                    }
                ),
                encoding="utf-8",
            )
            (published / "WINDOWS_INSTALLER_VISUAL_AUDIT_INTAKE_REQUEST.generated.json").write_text(
                json.dumps(
                    {
                        "contract_name": "chummer.windows_installer_visual_audit_intake_request.v1",
                        "generated_at_utc": "2026-07-04T21:20:00Z",
                        "status": "external_artifact_required",
                        "provider": "native_windows_operator",
                        "release_channel_receipt_path": "/tmp/RELEASE_CHANNEL.generated.json",
                        "release_version": "run-test",
                        "release_channel": "stable",
                        "request_receipt_path": str(published / "WINDOWS_INSTALLER_VISUAL_AUDIT_INTAKE_REQUEST.generated.json"),
                        "promoted_installer_sha256": "a" * 64,
                        "preferred_drop_path": "/tmp/windows-proof.zip",
                        "preferred_zip_name": "windows-proof.zip",
                        "required_zip_filename": "windows-proof.zip",
                        "preferred_extracted_visual_dir": "/tmp/windows-proof-dir",
                        "current_blocker": {"receipt": "/tmp/WINDOWS_INSTALLER_VISUAL_AUDIT.generated.json"},
                        "operator_request": {
                            "summary": "Run the promoted Windows installer on a native Windows host and provide the gold proof bundle.",
                            "required_surfaces": ["install-progress", "completion"],
                            "required_dpi_scales": ["1.0", "1.5"],
                            "required_host_class_prefix": "native-windows",
                            "powershell_commands": ["one", "two"],
                        },
                        "operator_telegram_draft": {
                            "message_path": str(root / "windows-ask.txt"),
                            "metadata_path": str(root / "windows-ask.generated.json"),
                            "current_message_path": str(windows_current_message_path),
                            "current_metadata_path": str(windows_current_metadata_path),
                            "send_command": f"python3 scripts/send_telegram_message_via_ea.py --text-file {windows_current_message_path} --receipt-name windows.receipt.json",
                            "receipt_name": "windows.receipt.json",
                            "message_preview": "Windows operator ask preview",
                            "message_sha256": module.hashlib.sha256("windows ask current\n".encode("utf-8")).hexdigest(),
                        },
                        "artifact_intake": {
                            "discover_command": "python3 discover",
                            "discover_visual_source_command": "python3 discover-visual",
                            "preferred_extracted_visual_dir": "/tmp/windows-proof-dir",
                            "watcher_launch_mode": "python_subprocess_start_new_session",
                            "watcher_state_path": str(root / "state" / "windows_installer_gold_proof_watcher.generated.json"),
                            "watcher_pid_file": str(root / "state" / "windows_installer_gold_proof_watcher.pid"),
                            "watcher_log_path": str(root / "state" / "windows_installer_gold_proof_auto_import_watch.log"),
                            "watcher_start_command": (
                                "python3 watcher-start "
                                f"--intake-request {published / 'WINDOWS_INSTALLER_VISUAL_AUDIT_INTAKE_REQUEST.generated.json'}"
                            ),
                            "watcher_status_command": (
                                "python3 watcher-status "
                                f"--intake-request {published / 'WINDOWS_INSTALLER_VISUAL_AUDIT_INTAKE_REQUEST.generated.json'}"
                            ),
                            "watcher_stop_command": (
                                "python3 watcher-stop "
                                f"--intake-request {published / 'WINDOWS_INSTALLER_VISUAL_AUDIT_INTAKE_REQUEST.generated.json'}"
                            ),
                            "import_command": (
                                "python3 scripts/import_windows_installer_gold_proof_artifact.py "
                                "bundle.zip "
                                f"--intake-request {published / 'WINDOWS_INSTALLER_VISUAL_AUDIT_INTAKE_REQUEST.generated.json'} "
                                "--verify"
                            ),
                            "auto_import_command": (
                                "python3 scripts/auto_import_windows_installer_gold_proof.py "
                                f"--intake-request {published / 'WINDOWS_INSTALLER_VISUAL_AUDIT_INTAKE_REQUEST.generated.json'}"
                            ),
                            "auto_import_watch_command": (
                                "python3 scripts/auto_import_windows_installer_gold_proof.py "
                                f"--intake-request {published / 'WINDOWS_INSTALLER_VISUAL_AUDIT_INTAKE_REQUEST.generated.json'} "
                                "--wait-seconds 900"
                            ),
                            "auto_import_roots": ["/tmp"],
                            "post_import_verify_command": "python3 scripts/verify_windows_installer_visual_audit.py --output .codex-studio/published/WINDOWS_INSTALLER_VISUAL_AUDIT.generated.json",
                            "post_import_verify_note": "The --verify import reruns the full intake-request post-import gate chain, not just the first verifier.",
                        },
                        "expected_artifact_patterns": [
                            "*windows-installer-gold-proof*.zip",
                            "*WINDOWS_INSTALLER_VISUAL_AUDIT.source.json",
                            "windows-proof.zip",
                        ],
                        "drop_roots_checked": [
                            "/tmp/windows-proof-drop",
                            "/tmp",
                        ],
                        "post_import_gates": [
                            "python3 scripts/verify_windows_installer_visual_audit.py --output .codex-studio/published/WINDOWS_INSTALLER_VISUAL_AUDIT.generated.json",
                            "python3 scripts/materialize_windows_installer_visual_audit_intake_request.py --output .codex-studio/published/WINDOWS_INSTALLER_VISUAL_AUDIT_INTAKE_REQUEST.generated.json",
                            "python3 scripts/verify_windows_installer_visual_audit_intake_request.py",
                            "python3 scripts/materialize_release_ready_receipt.py --force-global-verifier",
                            "python3 scripts/materialize_operator_release_dashboard.py",
                            "python3 scripts/final_gold_janitor.py --skip-materializers",
                            "python3 ../scripts/release/_release_gate_common.py",
                            "python3 ../scripts/attempt_flagship_public_stable_promotion.py --output ../.codex-studio/published/FLAGSHIP_PUBLIC_STABLE_PROMOTION_ATTEMPT.generated.json",
                            "python3 ../scripts/materialize_chummer_flagship_surface_stack.py --output ../.codex-studio/published/CHUMMER_FLAGSHIP_SURFACE_STACK.generated.json",
                            "python3 ../scripts/verify_chummer_flagship_surface_stack.py --receipt ../.codex-studio/published/CHUMMER_FLAGSHIP_SURFACE_STACK.generated.json --require-flagship-pass",
                            "python3 ../scripts/materialize_codex_flagship_handoff.py --timestamp \"$(date --iso-8601=seconds)\"",
                        ],
                        "secrets_redacted": True,
                        "direct_telegram_sent": False,
                    }
                ),
                encoding="utf-8",
            )
            (root / "windows-ask.txt").write_text("windows ask current\n", encoding="utf-8")
            (root / "windows-ask.generated.json").write_text(
                json.dumps(
                    {
                        "request_receipt_path": str(published / "WINDOWS_INSTALLER_VISUAL_AUDIT_INTAKE_REQUEST.generated.json"),
                        "message_sha256": module.hashlib.sha256("windows ask current\n".encode("utf-8")).hexdigest(),
                        "receipt_name": "windows.receipt.json",
                        "send_command": f"python3 scripts/send_telegram_message_via_ea.py --text-file {windows_current_message_path} --receipt-name windows.receipt.json",
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            windows_current_message_path.write_text("windows ask current\n", encoding="utf-8")
            windows_current_metadata_path.write_text(
                json.dumps(
                    {
                        "request_receipt_path": str(published / "WINDOWS_INSTALLER_VISUAL_AUDIT_INTAKE_REQUEST.generated.json"),
                        "current_message_path": str(windows_current_message_path),
                        "message_sha256": module.hashlib.sha256("windows ask current\n".encode("utf-8")).hexdigest(),
                        "receipt_name": "windows.receipt.json",
                        "send_command": f"python3 scripts/send_telegram_message_via_ea.py --text-file {windows_current_message_path} --receipt-name windows.receipt.json",
                        "preferred_drop_path": "/tmp/windows-proof.zip",
                        "promoted_installer_sha256": "a" * 64,
                        "secrets_redacted": True,
                        "source_message_path": str(root / "windows-ask.txt"),
                        "source_metadata_path": str(root / "windows-ask.generated.json"),
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            (telegram_root / "google.receipt.json").write_text(
                json.dumps(
                    {
                        "status": "sent",
                        "generated_at_utc": "2026-07-04T20:58:05Z",
                        "text_sha256": module.hashlib.sha256("google ask stale\n".encode("utf-8")).hexdigest(),
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            (telegram_root / "windows.receipt.json").write_text(
                json.dumps(
                    {
                        "status": "sent",
                        "generated_at_utc": "2026-07-04T20:58:05Z",
                        "text_sha256": module.hashlib.sha256("windows ask stale\n".encode("utf-8")).hexdigest(),
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            (published / "WINDOWS_INSTALLER_VISUAL_AUDIT_AUTO_IMPORT.generated.json").write_text(
                json.dumps(
                    {
                        "status": "fail",
                        "generated_at_utc": "2026-07-06T02:31:45Z",
                        "artifact": "/tmp/windows-installer-gold-proof-a.zip",
                        "import_failure": {
                            "type": "BadZipFile",
                            "message": "File is not a zip file",
                            "code": None,
                        },
                        "summary": "Selected Windows installer gold-proof artifact failed import validation.",
                        "actionable_candidate_count": 0,
                        "matching_promoted_directory_candidate_count": 0,
                        "matching_promoted_zip_candidate_count": 0,
                        "stale_directory_candidate_count": 11,
                        "stage_like_stale_directory_candidate_count": 1,
                        "stage_visual_proof_receipt_count": 8,
                        "matching_promoted_stage_visual_proof_receipt_count": 0,
                        "stale_stage_visual_proof_receipt_count": 8,
                        "suppressed_stale_stage_visual_proof_receipt_count": 3,
                        "stage_startup_smoke_receipt_count": 2,
                        "matching_promoted_stage_startup_smoke_receipt_count": 1,
                        "stale_stage_startup_smoke_receipt_count": 1,
                        "suppressed_stale_stage_startup_smoke_receipt_count": 0,
                        "matching_promoted_stage_startup_smoke_receipts": [
                            {
                                "path": "/tmp/chummer6-ui-publishfix/Docker/Downloads/startup-smoke/startup-smoke-avalonia-win-x64.receipt.json",
                                "matches_promoted_installer": True,
                            },
                        ],
                        "stale_stage_startup_smoke_receipts": [
                            {
                                "path": "/tmp/stale/startup-smoke-avalonia-win-x64.receipt.json",
                                "matches_promoted_installer": False,
                            },
                        ],
                        "stale_stage_visual_proof_receipts": [
                            {
                                "path": "/tmp/chummer6-ui-publishfix/Docker/Downloads/WINDOWS_INSTALLER_VISUAL_PROOF.generated.json",
                                "matches_promoted_installer": False,
                            },
                            {
                                "path": "/tmp/chummer6-ui-publishfix/.codex-studio/published/WINDOWS_INSTALLER_VISUAL_PROOF.generated.json",
                                "matches_promoted_installer": False,
                            },
                        ],
                        "stage_visual_proof_receipt_note": (
                            "Stage/nightly Windows proof receipts were found, but none match the promoted installer digest."
                        ),
                        "stage_startup_smoke_receipt_note": (
                            "Matching stage/nightly Windows startup-smoke receipts were found for the promoted installer digest. Startup is already proven for those staged bytes; only the visual-audit bundle still needs packaging or recapture. Additional digest-mismatched startup-smoke receipts were summarized separately."
                        ),
                        "stale_directory_digest_summary": [
                            {
                                "artifact_sha256": "c41d17cea200060b0940f37f18eea6b0bd407c447cd9cd62a8e140e965bc6a51",
                                "count": 9,
                                "stage_like_count": 0,
                                "sample_path": "/tmp/windows-installer-gold-proof-27864339393",
                                "latest_source_updated_at_utc": "2026-06-20T07:35:15.1148329Z",
                            },
                            {
                                "artifact_sha256": "c5691dcdb5176394e9529985bf85022577a593098b3eddeda50d9d91af914c5b",
                                "count": 2,
                                "stage_like_count": 1,
                                "sample_path": "/tmp/chummer-run-services-browserfix3",
                                "latest_source_updated_at_utc": "2026-06-21T17:44:15.3027652Z",
                            },
                        ],
                        "directory_candidate_note": (
                            "Complete extracted proof directories were found, but none match the promoted installer digest. "
                            "Digest-mismatched directories were summarized separately."
                        ),
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            watcher_state_path.parent.mkdir(parents=True, exist_ok=True)
            watcher_state_path.write_text(
                json.dumps(
                    {
                        "generated_at_utc": "2026-07-06T15:00:00Z",
                        "status": "running",
                        "pid": 1111,
                        "process_alive": True,
                        "matching_process_pids": [1111],
                        "matching_process_count": 1,
                        "duplicate_process_pids": [],
                        "duplicate_process_count": 0,
                        "note": "stale watcher snapshot",
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            portal_downloads = root / "Chummer.Portal" / "downloads"
            portal_downloads.mkdir(parents=True, exist_ok=True)
            (portal_downloads / "RELEASE_BUILD_HANDOFF.generated.json").write_text(
                json.dumps(
                    {
                        "generated_at": "2026-07-05T05:17:26Z",
                        "stage_dir": "/tmp/chummer-public-downloads-bundle-live-check",
                        "stage_proof_complete": False,
                        "blockers": [
                            "Windows visual proof is still outstanding for the staged installer bytes.",
                        ],
                        "windows_exit_gate_refresh": {
                            "status": "failed",
                            "json_path": "/tmp/chummer-public-downloads-bundle-live-check/UI_WINDOWS_DESKTOP_EXIT_GATE.generated.json",
                            "blocking_mode": "external_only",
                        },
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            (portal_downloads / "WINDOWS_INSTALLER_VISUAL_PROOF_HANDOFF.generated.json").write_text(
                json.dumps(
                    {
                        "status": "ready_for_windows_host",
                        "summary": "Windows desktop exit gate failed: Windows installer visual proof is missing; capture progress and completion screenshots on a Windows host.",
                        "visual_proof_path": "/tmp/chummer-public-downloads-bundle-live-check/WINDOWS_INSTALLER_VISUAL_PROOF.generated.json",
                        "next_actions": [
                            "Capture the staged Windows installer progress and completion screenshots on a real Windows host.",
                        ],
                        "operator_artifact_intake": {
                            "preferred_drop_root": "/tmp/chummer-public-downloads-bundle-live-check",
                            "preferred_visual_proof_receipt_path": "/tmp/chummer-public-downloads-bundle-live-check/WINDOWS_INSTALLER_VISUAL_PROOF.generated.json",
                            "preferred_screenshot_dir": "/tmp/chummer-public-downloads-bundle-live-check/windows-installer-visual-proof",
                            "post_copy_verify_command": "bash /tmp/re-run-exit-gate.sh",
                        },
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            def fake_watcher_status(*_args, **_kwargs):
                watcher_state_path.write_text(
                    json.dumps(
                        {
                            "generated_at_utc": "2026-07-06T15:37:34Z",
                            "status": "running",
                            "pid": 2086931,
                            "process_alive": True,
                            "matching_process_pids": [2086931],
                            "matching_process_count": 1,
                            "duplicate_process_pids": [],
                            "duplicate_process_count": 0,
                            "note": "watcher discovered by pid file or process scan",
                        }
                    )
                    + "\n",
                    encoding="utf-8",
                )
                return mock.Mock(returncode=0, stdout="", stderr="")

            with (
                mock.patch.object(module, "PUBLISHED_ROOT", published),
                mock.patch.object(module, "RUN_SERVICES_ROOT", root),
                mock.patch.object(module, "TELEGRAM_TEXT_DELIVERY_ROOT", telegram_root),
                mock.patch.object(module, "PUBLIC_RELEASE_SNAPSHOT_READONLY_AUDIT", snapshot_audit),
                mock.patch.object(module, "RELEASE_BLOCKERS_JSON", release_blockers_path),
                mock.patch.object(
                    module,
                    "verify_google_oauth_linking_proof_receipt",
                    return_value=(
                        True,
                        {
                            "status": "pass",
                            "issues": [],
                            "operator_request_artifacts_pass": True,
                            "operator_evidence_pass": False,
                        },
                    ),
                ),
                mock.patch.object(
                    module,
                    "verify_windows_visual_intake_request_receipt",
                    return_value=(
                        True,
                        {
                            "status": "pass",
                            "issues": [],
                            "recovery_pack_pass": True,
                            "operator_action_still_required": True,
                        },
                    ),
                ),
                mock.patch.object(module.subprocess, "run", side_effect=fake_watcher_status),
            ):
                artifacts = module.current_blocking_gate_artifacts()

        self.assertEqual(
            "SNAPSHOT_CONSISTENT_NOT_LAUNCH_READY",
            artifacts["public_release_snapshot_readonly_audit"]["verdict"],
        )
        self.assertEqual(
            ["release_posture:non_flagship_channel", "release_truth:windows_installer_visual_audit"],
            artifacts["public_release_snapshot_readonly_audit"]["expected_top_level_blocker_ids"],
        )
        self.assertEqual(
            {
                "root_blocker_ids": [
                    "release_posture:non_flagship_channel",
                    "release_truth:windows_installer_visual_audit",
                ],
                "root_blockers": [
                    {
                        "blocker_id": "release_posture:non_flagship_channel",
                        "stable_promotion_command": "bash /tmp/promote-stable.sh",
                        "post_promotion_verify_command": "python3 /tmp/post-verify.py",
                        "id": "release_posture:non_flagship_channel",
                    },
                    {
                        "blocker_id": "release_truth:windows_installer_visual_audit",
                        "id": "release_truth:windows_installer_visual_audit",
                    },
                ],
                "root_blockers_generated_at": "2026-07-06T05:18:22Z",
                "stable_promotion_command": "bash /tmp/promote-stable.sh",
                "post_promotion_verify_command": "python3 /tmp/post-verify.py",
                "root_release_truth_source": str(release_blockers_path),
            },
            artifacts["release_truth_root"],
        )
        self.assertEqual("/tmp/google-request.json", artifacts["google_oauth_linking_proof"]["request_receipt_path"])
        self.assertEqual("pass", artifacts["google_oauth_linking_proof"]["proof_verifier_status"])
        self.assertTrue(artifacts["google_oauth_linking_proof"]["request_artifacts_pass"])
        self.assertTrue(artifacts["google_oauth_linking_proof"]["proof_operator_request_artifacts_pass"])
        self.assertTrue(artifacts["google_oauth_linking_proof"]["proof_operator_action_still_required"])
        self.assertFalse(artifacts["google_oauth_linking_proof"]["proof_operator_evidence_pass"])
        self.assertFalse(artifacts["google_oauth_linking_proof"]["pass"])
        self.assertTrue(artifacts["google_oauth_linking_proof"]["operator_ask_delivery_current_text_comparable"])
        self.assertFalse(artifacts["google_oauth_linking_proof"]["operator_ask_delivery_matches_current_text"])
        self.assertTrue(artifacts["google_oauth_linking_proof"]["operator_ask_delivery_needs_resend"])
        self.assertEqual(
            ["Capture a real browser-backed Google linking proof receipt at /tmp/operator-evidence.json."],
            artifacts["google_oauth_linking_proof"]["next_actions"],
        )
        self.assertEqual(
            f"python3 scripts/send_telegram_message_via_ea.py --text-file {google_ask_text_path} --receipt-name google.receipt.json",
            artifacts["google_oauth_linking_proof"]["operator_ask_resend_command"],
        )
        self.assertIn(
            "operator action still required until Google OAuth operator evidence exists: /tmp/operator-evidence.json",
            artifacts["google_oauth_linking_proof"]["failures"],
        )
        self.assertNotIn(
            f"google oauth operator ask delivery is stale; resend current ask: python3 scripts/send_telegram_message_via_ea.py --text-file {google_ask_text_path} --receipt-name google.receipt.json",
            artifacts["google_oauth_linking_proof"]["failures"],
        )
        self.assertEqual("/tmp/windows-proof.zip", artifacts["windows_installer_visual_audit"]["preferred_drop_path"])
        self.assertFalse(artifacts["windows_installer_visual_audit"]["preferred_drop_path_exists"])
        self.assertEqual("windows-proof.zip", artifacts["windows_installer_visual_audit"]["preferred_zip_name"])
        self.assertEqual("windows-proof.zip", artifacts["windows_installer_visual_audit"]["required_zip_filename"])
        self.assertEqual(
            "/tmp/windows-proof-dir",
            artifacts["windows_installer_visual_audit"]["preferred_extracted_visual_dir"],
        )
        self.assertFalse(
            artifacts["windows_installer_visual_audit"]["preferred_extracted_visual_dir_exists"]
        )
        self.assertEqual("windows.receipt.json", artifacts["windows_installer_visual_audit"]["operator_ask_receipt_name"])
        self.assertEqual("python3 discover", artifacts["windows_installer_visual_audit"]["discover_command"])
        self.assertEqual(
            "python3 discover-visual",
            artifacts["windows_installer_visual_audit"]["discover_visual_source_command"],
        )
        self.assertIn(
            "auto_import_windows_installer_gold_proof.py",
            artifacts["windows_installer_visual_audit"]["auto_import_command"],
        )
        self.assertIn(
            "verify_windows_installer_visual_audit.py",
            artifacts["windows_installer_visual_audit"]["post_import_verify_command"],
        )
        self.assertEqual(
            [
                "*windows-installer-gold-proof*.zip",
                "*WINDOWS_INSTALLER_VISUAL_AUDIT.source.json",
                "windows-proof.zip",
            ],
            artifacts["windows_installer_visual_audit"]["expected_artifact_patterns"],
        )
        self.assertEqual(
            ["/tmp/windows-proof-drop", "/tmp"],
            artifacts["windows_installer_visual_audit"]["drop_roots_checked"],
        )
        self.assertEqual("pass", artifacts["windows_installer_visual_audit"]["request_verifier_status"])
        self.assertTrue(artifacts["windows_installer_visual_audit"]["request_recovery_pack_pass"])
        self.assertTrue(artifacts["windows_installer_visual_audit"]["request_operator_action_still_required"])
        self.assertTrue(artifacts["windows_installer_visual_audit"]["operator_ask_delivery_current_text_comparable"])
        self.assertFalse(artifacts["windows_installer_visual_audit"]["operator_ask_delivery_matches_current_text"])
        self.assertTrue(artifacts["windows_installer_visual_audit"]["operator_ask_delivery_needs_resend"])
        self.assertEqual(
            str(watcher_state_path),
            artifacts["windows_installer_visual_audit"]["watcher_state_receipt_path"],
        )
        self.assertEqual(
            "2026-07-06T15:37:34Z",
            artifacts["windows_installer_visual_audit"]["watcher_state_receipt_generated_at_utc"],
        )
        self.assertEqual(2086931, artifacts["windows_installer_visual_audit"]["watcher_pid"])
        self.assertEqual(
            str(published / "WINDOWS_INSTALLER_VISUAL_AUDIT_AUTO_IMPORT.generated.json"),
            artifacts["windows_installer_visual_audit"]["auto_import_receipt_path"],
        )
        self.assertEqual(
            "fail",
            artifacts["windows_installer_visual_audit"]["auto_import_receipt_status"],
        )
        self.assertEqual(
            "2026-07-06T02:31:45Z",
            artifacts["windows_installer_visual_audit"]["auto_import_receipt_generated_at_utc"],
        )
        self.assertEqual(
            "/tmp/windows-installer-gold-proof-a.zip",
            artifacts["windows_installer_visual_audit"]["auto_import_artifact"],
        )
        self.assertEqual(
            "BadZipFile",
            artifacts["windows_installer_visual_audit"]["auto_import_import_failure_type"],
        )
        self.assertEqual(
            "File is not a zip file",
            artifacts["windows_installer_visual_audit"]["auto_import_import_failure_message"],
        )
        self.assertIsNone(artifacts["windows_installer_visual_audit"]["auto_import_import_failure_code"])
        self.assertEqual(
            "Selected Windows installer gold-proof artifact failed import validation.",
            artifacts["windows_installer_visual_audit"]["auto_import_import_failure_summary"],
        )
        self.assertEqual(11, artifacts["windows_installer_visual_audit"]["auto_import_stale_directory_candidate_count"])
        self.assertEqual(1, artifacts["windows_installer_visual_audit"]["auto_import_stage_like_stale_directory_candidate_count"])
        self.assertEqual(8, artifacts["windows_installer_visual_audit"]["auto_import_stage_visual_proof_receipt_count"])
        self.assertEqual(0, artifacts["windows_installer_visual_audit"]["auto_import_matching_promoted_stage_visual_proof_receipt_count"])
        self.assertEqual(8, artifacts["windows_installer_visual_audit"]["auto_import_stale_stage_visual_proof_receipt_count"])
        self.assertEqual(3, artifacts["windows_installer_visual_audit"]["auto_import_suppressed_stale_stage_visual_proof_receipt_count"])
        self.assertEqual(2, artifacts["windows_installer_visual_audit"]["auto_import_stage_startup_smoke_receipt_count"])
        self.assertEqual(1, artifacts["windows_installer_visual_audit"]["auto_import_matching_promoted_stage_startup_smoke_receipt_count"])
        self.assertEqual(1, artifacts["windows_installer_visual_audit"]["auto_import_stale_stage_startup_smoke_receipt_count"])
        self.assertEqual(
            2,
            len(artifacts["windows_installer_visual_audit"]["auto_import_stale_stage_visual_proof_receipts"]),
        )
        self.assertEqual(
            "Stage/nightly Windows proof receipts were found, but none match the promoted installer digest.",
            artifacts["windows_installer_visual_audit"]["auto_import_stage_visual_proof_receipt_note"],
        )
        self.assertIn(
            "Startup is already proven",
            artifacts["windows_installer_visual_audit"]["auto_import_stage_startup_smoke_receipt_note"],
        )
        self.assertEqual(
            2,
            len(artifacts["windows_installer_visual_audit"]["auto_import_stale_directory_digest_summary"]),
        )
        self.assertEqual(
            "Complete extracted proof directories were found, but none match the promoted installer digest. Digest-mismatched directories were summarized separately.",
            artifacts["windows_installer_visual_audit"]["auto_import_directory_candidate_note"],
        )
        self.assertNotIn(
            f"windows installer operator ask delivery is stale; resend current ask: python3 scripts/send_telegram_message_via_ea.py --text-file {windows_current_message_path} --receipt-name windows.receipt.json",
            artifacts["windows_installer_visual_audit"]["failures"],
        )
        self.assertEqual(
            ["Capture the staged Windows installer progress and completion screenshots on a real Windows host."],
            artifacts["windows_installer_visual_audit"]["stage_windows_visual_proof_handoff_next_actions"],
        )
        self.assertEqual(
            f"python3 scripts/send_telegram_message_via_ea.py --text-file {windows_current_message_path} --receipt-name windows.receipt.json",
            artifacts["windows_installer_visual_audit"]["operator_ask_resend_command"],
        )
        self.assertEqual(
            str(portal_downloads / "RELEASE_BUILD_HANDOFF.generated.json"),
            artifacts["windows_installer_visual_audit"]["stage_release_build_handoff_path"],
        )
        self.assertTrue(artifacts["windows_installer_visual_audit"]["stage_release_build_handoff_exists"])
        self.assertEqual("fail", artifacts["windows_installer_visual_audit"]["stage_release_build_handoff_status"])
        self.assertEqual(
            "failed",
            artifacts["windows_installer_visual_audit"]["stage_windows_exit_gate_refresh_status"],
        )
        self.assertEqual(
            str(portal_downloads / "WINDOWS_INSTALLER_VISUAL_PROOF_HANDOFF.generated.json"),
            artifacts["windows_installer_visual_audit"]["stage_windows_visual_proof_handoff_path"],
        )
        self.assertTrue(artifacts["windows_installer_visual_audit"]["stage_windows_visual_proof_handoff_exists"])
        self.assertEqual(
            "ready_for_windows_host",
            artifacts["windows_installer_visual_audit"]["stage_windows_visual_proof_handoff_status"],
        )
        self.assertEqual(
            "/tmp/chummer-public-downloads-bundle-live-check/WINDOWS_INSTALLER_VISUAL_PROOF.generated.json",
            artifacts["windows_installer_visual_audit"]["stage_windows_visual_proof_preferred_receipt_path"],
        )
        self.assertEqual(
            "/tmp/chummer-public-downloads-bundle-live-check/windows-installer-visual-proof",
            artifacts["windows_installer_visual_audit"]["stage_windows_visual_proof_preferred_screenshot_dir"],
        )

    def test_current_blocking_gate_artifacts_fail_close_pass_shaped_snapshot_audit_status(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="release-ready-snapshot-audit-fail-close-") as temp_dir:
            root = Path(temp_dir)
            published = root / "published"
            published.mkdir(parents=True, exist_ok=True)
            snapshot_audit = root / "PUBLIC_RELEASE_SNAPSHOT_READONLY_AUDIT.generated.json"
            release_blockers_path = root / "RELEASE_BLOCKERS.generated.json"

            snapshot_audit.write_text(
                json.dumps(
                    {
                        "status": "pass",
                        "generated_at_utc": "2026-07-07T11:14:10Z",
                        "verdict": "SNAPSHOT_CONSISTENT_NOT_LAUNCH_READY",
                        "summary": "Contradictory pass-shaped audit payload",
                        "failures": ["nested release truth contradiction"],
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            release_blockers_path.write_text(
                json.dumps(
                    {
                        "generated_at": "2026-07-07T11:14:10Z",
                        "root_blockers": [
                            {"blocker_id": "release_posture:non_flagship_channel"},
                            {"blocker_id": "release_truth:windows_installer_visual_audit"},
                        ],
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            with (
                mock.patch.object(module, "PUBLISHED_ROOT", published),
                mock.patch.object(module, "PUBLIC_RELEASE_SNAPSHOT_READONLY_AUDIT", snapshot_audit),
                mock.patch.object(module, "RELEASE_BLOCKERS_JSON", release_blockers_path),
            ):
                artifacts = module.current_blocking_gate_artifacts(
                    refresh_windows_runtime_receipts=False
                )

        audit = artifacts["public_release_snapshot_readonly_audit"]
        self.assertEqual("fail", audit["status"])
        self.assertEqual("pass", audit["raw_status"])
        self.assertFalse(audit["pass"])

    def test_current_blocking_gate_artifacts_refreshes_windows_auto_import_before_watcher_state(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="release-ready-windows-auto-import-refresh-") as temp_dir:
            root = Path(temp_dir)
            published = root / "published"
            telegram_root = root / "telegram"
            published.mkdir(parents=True, exist_ok=True)
            telegram_root.mkdir(parents=True, exist_ok=True)
            watcher_state_path = root / "state" / "windows_installer_gold_proof_watcher.generated.json"
            auto_import_path = published / "WINDOWS_INSTALLER_VISUAL_AUDIT_AUTO_IMPORT.generated.json"
            release_blockers_path = root / "RELEASE_BLOCKERS.generated.json"

            release_blockers_path.write_text(
                json.dumps({"generated_at": "2026-07-06T05:18:22Z", "root_blockers": []}) + "\n",
                encoding="utf-8",
            )
            (published / "WINDOWS_INSTALLER_VISUAL_AUDIT.generated.json").write_text(
                json.dumps({"status": "fail"}) + "\n",
                encoding="utf-8",
            )
            auto_import_path.write_text(
                json.dumps(
                    {
                        "status": "waiting_for_artifact",
                        "generated_at_utc": "2026-07-06T15:00:00Z",
                        "actionable_candidate_count": 0,
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            watcher_state_path.parent.mkdir(parents=True, exist_ok=True)
            watcher_state_path.write_text(
                json.dumps(
                    {
                        "generated_at_utc": "2026-07-06T15:00:00Z",
                        "status": "running",
                        "pid": 1111,
                        "process_alive": True,
                        "matching_process_pids": [1111],
                        "matching_process_count": 1,
                        "duplicate_process_pids": [],
                        "duplicate_process_count": 0,
                        "note": "stale watcher snapshot",
                        "auto_import_receipt_status": "waiting_for_artifact",
                        "auto_import_receipt_generated_at_utc": "2026-07-06T15:00:00Z",
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            (published / "WINDOWS_INSTALLER_VISUAL_AUDIT_INTAKE_REQUEST.generated.json").write_text(
                json.dumps(
                    {
                        "preferred_drop_path": "/tmp/windows-proof.zip",
                        "operator_telegram_draft": {
                            "current_message_path": str(root / "windows-ask.txt"),
                            "current_metadata_path": str(root / "windows-ask.generated.json"),
                            "receipt_name": "windows.receipt.json",
                            "message_preview": "Windows operator ask preview",
                        },
                        "artifact_intake": {
                            "watcher_state_path": str(watcher_state_path),
                            "watcher_status_command": "python3 watcher-status --intake-request /tmp/intake.json",
                            "auto_import_command": "python3 auto-import --intake-request /tmp/intake.json",
                        },
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            (root / "windows-ask.txt").write_text("windows ask current\n", encoding="utf-8")
            (root / "windows-ask.generated.json").write_text("{}\n", encoding="utf-8")
            run_calls: list[tuple[list[str], Path | None, dict[str, str] | None]] = []

            def fake_run(args, **kwargs):
                command = list(args)
                env = kwargs.get("env")
                run_calls.append((command, kwargs.get("cwd"), env if isinstance(env, dict) else None))
                if command[:2] == ["python3", "auto-import"]:
                    auto_import_path.write_text(
                        json.dumps(
                            {
                                "status": "waiting_for_artifact",
                                "generated_at_utc": "2026-07-06T15:24:12Z",
                                "actionable_candidate_count": 0,
                            }
                        )
                        + "\n",
                        encoding="utf-8",
                    )
                elif command[:2] == ["python3", "watcher-status"]:
                    watcher_state_path.write_text(
                        json.dumps(
                            {
                                "generated_at_utc": "2026-07-06T15:24:14Z",
                                "status": "running",
                                "pid": 2086931,
                                "process_alive": True,
                                "matching_process_pids": [2086931],
                                "matching_process_count": 1,
                                "duplicate_process_pids": [],
                                "duplicate_process_count": 0,
                                "note": "watcher discovered by pid file or process scan",
                                "auto_import_receipt_status": "waiting_for_artifact",
                                "auto_import_receipt_generated_at_utc": "2026-07-06T15:24:12Z",
                            }
                        )
                        + "\n",
                        encoding="utf-8",
                    )
                return mock.Mock(returncode=0, stdout="", stderr="")

            with (
                mock.patch.object(module, "PUBLISHED_ROOT", published),
                mock.patch.object(module, "RUN_SERVICES_ROOT", root),
                mock.patch.object(module, "TELEGRAM_TEXT_DELIVERY_ROOT", telegram_root),
                mock.patch.object(module, "RELEASE_BLOCKERS_JSON", release_blockers_path),
                mock.patch.object(module.subprocess, "run", side_effect=fake_run),
            ):
                artifacts = module.current_blocking_gate_artifacts()

        self.assertEqual(
            str(auto_import_path),
            artifacts["windows_installer_visual_audit"]["auto_import_receipt_path"],
        )
        self.assertEqual(
            "2026-07-06T15:24:12Z",
            artifacts["windows_installer_visual_audit"]["auto_import_receipt_generated_at_utc"],
        )
        self.assertEqual(
            "2026-07-06T15:24:14Z",
            artifacts["windows_installer_visual_audit"]["watcher_state_receipt_generated_at_utc"],
        )
        self.assertEqual(["python3", "auto-import"], run_calls[0][0][:2])
        self.assertEqual(["python3", "watcher-status"], run_calls[1][0][:2])
        self.assertEqual(root, run_calls[0][1])
        self.assertEqual(root, run_calls[1][1])
        for _command, _cwd, env in run_calls:
            self.assertIsInstance(env, dict)
            self.assertTrue(str(env.get("TMPDIR") or "").strip())

    def test_current_blocking_gate_artifacts_can_reuse_existing_windows_runtime_receipts(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="release-ready-windows-runtime-reuse-") as temp_dir:
            root = Path(temp_dir)
            published = root / "published"
            telegram_root = root / "telegram"
            published.mkdir(parents=True, exist_ok=True)
            telegram_root.mkdir(parents=True, exist_ok=True)
            watcher_state_path = root / "state" / "windows_installer_gold_proof_watcher.generated.json"
            auto_import_path = published / "WINDOWS_INSTALLER_VISUAL_AUDIT_AUTO_IMPORT.generated.json"
            release_blockers_path = root / "RELEASE_BLOCKERS.generated.json"

            release_blockers_path.write_text(
                json.dumps({"generated_at": "2026-07-06T05:18:22Z", "root_blockers": []}) + "\n",
                encoding="utf-8",
            )
            (published / "WINDOWS_INSTALLER_VISUAL_AUDIT.generated.json").write_text(
                json.dumps({"status": "fail"}) + "\n",
                encoding="utf-8",
            )
            auto_import_path.write_text(
                json.dumps(
                    {
                        "status": "waiting_for_artifact",
                        "generated_at_utc": "2026-07-06T15:24:12Z",
                        "actionable_candidate_count": 0,
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            watcher_state_path.parent.mkdir(parents=True, exist_ok=True)
            watcher_state_path.write_text(
                json.dumps(
                    {
                        "generated_at_utc": "2026-07-06T15:24:14Z",
                        "status": "running",
                        "pid": 2086931,
                        "process_alive": True,
                        "matching_process_pids": [2086931],
                        "matching_process_count": 1,
                        "duplicate_process_pids": [],
                        "duplicate_process_count": 0,
                        "note": "watcher discovered by pid file or process scan",
                        "auto_import_receipt_status": "waiting_for_artifact",
                        "auto_import_receipt_generated_at_utc": "2026-07-06T15:24:12Z",
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            (published / "WINDOWS_INSTALLER_VISUAL_AUDIT_INTAKE_REQUEST.generated.json").write_text(
                json.dumps(
                    {
                        "preferred_drop_path": "/tmp/windows-proof.zip",
                        "operator_telegram_draft": {
                            "current_message_path": str(root / "windows-ask.txt"),
                            "current_metadata_path": str(root / "windows-ask.generated.json"),
                            "receipt_name": "windows.receipt.json",
                            "message_preview": "Windows operator ask preview",
                        },
                        "artifact_intake": {
                            "watcher_state_path": str(watcher_state_path),
                            "watcher_status_command": "python3 watcher-status --intake-request /tmp/intake.json",
                            "auto_import_command": "python3 auto-import --intake-request /tmp/intake.json",
                        },
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            (root / "windows-ask.txt").write_text("windows ask current\n", encoding="utf-8")
            (root / "windows-ask.generated.json").write_text("{}\n", encoding="utf-8")

            with (
                mock.patch.object(module, "PUBLISHED_ROOT", published),
                mock.patch.object(module, "RUN_SERVICES_ROOT", root),
                mock.patch.object(module, "TELEGRAM_TEXT_DELIVERY_ROOT", telegram_root),
                mock.patch.object(module, "RELEASE_BLOCKERS_JSON", release_blockers_path),
                mock.patch.object(module.subprocess, "run") as run_mock,
            ):
                artifacts = module.current_blocking_gate_artifacts(
                    refresh_windows_runtime_receipts=False
                )

        self.assertEqual(
            "2026-07-06T15:24:12Z",
            artifacts["windows_installer_visual_audit"]["auto_import_receipt_generated_at_utc"],
        )
        self.assertEqual(
            "2026-07-06T15:24:14Z",
            artifacts["windows_installer_visual_audit"]["watcher_state_receipt_generated_at_utc"],
        )
        run_mock.assert_not_called()

    def test_refresh_flagship_product_readiness_gate_sets_tmpdir_env(self) -> None:
        module = load_module()

        with mock.patch.object(module.subprocess, "run", return_value=mock.Mock(returncode=0)) as run_mock:
            module.refresh_flagship_product_readiness_gate(module.DEFAULT_FLAGSHIP_PRODUCT_READINESS_GATE_PATH)

        env = run_mock.call_args.kwargs.get("env")
        self.assertIsInstance(env, dict)
        self.assertTrue(str(env.get("TMPDIR") or "").strip())

    def test_collect_current_blocking_failures_skips_recoverable_flagship_gate_when_other_blockers_exist(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="release-ready-current-blocker-collapse-") as temp_dir:
            root = Path(temp_dir)
            published = root / "published"
            registry = root / "registry"
            published.mkdir(parents=True, exist_ok=True)
            registry.mkdir(parents=True, exist_ok=True)

            (registry / "RELEASE_CHANNEL.generated.json").write_text(
                json.dumps(
                    {
                        "status": "published",
                        "version": "run-test",
                        "channel": "preview",
                        "supportabilityState": "preview_supported",
                        "rolloutState": "promoted_preview",
                    }
                ),
                encoding="utf-8",
            )
            (published / "FLAGSHIP_PRODUCT_READINESS_GATE.generated.json").write_text(
                json.dumps(
                    {
                        "contract_name": "chummer.flagship_product_readiness_gate.v1",
                        "status": "fail",
                        "verdict": "NOT_FLAGSHIP_PRODUCT_READY",
                        "pass": False,
                        "summary": {
                            "contract_name": "fleet.flagship_product_readiness",
                            "status": "fail",
                            "pass": False,
                            "completion_audit_status": "pass",
                            "flagship_readiness_audit_status": "pass",
                            "missing_count": 0,
                            "scoped_missing_count": 0,
                            "coverage_gap_keys": [],
                            "scoped_coverage_gap_keys": [],
                            "launch_critical_nested_blockers": [
                                "final gold janitor state is 'fail'",
                                "final gold janitor verdict is 'NOT_GOLD'",
                                "live-backed gold claim is not allowed",
                            ],
                        },
                    }
                ),
                encoding="utf-8",
            )
            (published / "PUBLIC_EDGE_POSTDEPLOY_GATE.generated.json").write_text(
                json.dumps(passing_public_edge_postdeploy_payload(module)),
                encoding="utf-8",
            )
            (published / "WINDOWS_INSTALLER_VISUAL_AUDIT.generated.json").write_text(
                json.dumps(
                    {
                        "status": "fail",
                        "artifact": {
                            "sha256": "a" * 64,
                        },
                        "visualAuditSource": {
                            "artifactSha256": "b" * 64,
                            "path": "/tmp/WINDOWS_INSTALLER_VISUAL_AUDIT.source.json",
                        },
                        "failures": [
                            "Windows installer visual audit source digest does not match promoted installer",
                        ],
                    }
                ),
                encoding="utf-8",
            )

            with (
                mock.patch.object(module, "PUBLISHED_ROOT", published),
                mock.patch.object(module, "REGISTRY_PUBLISHED_ROOT", registry),
            ):
                failures = module.collect_current_blocking_failures()

        self.assertIn(
            "FAIL release_channel: release channel channel is preview, not a flagship stable lane",
            failures,
        )
        self.assertIn(
            "FAIL release_channel: release channel supportability is not gold_supported",
            failures,
        )
        self.assertIn(
            "FAIL release_channel: release channel rollout is promoted_preview, not public_stable",
            failures,
        )
        self.assertIn(
            "FAIL windows_installer_visual_audit: Windows installer visual audit source digest does not match promoted installer",
            failures,
        )
        self.assertIn(
            "FAIL windows_installer_visual_audit: windows installer visual audit source still targets "
            f"{'b' * 64} instead of promoted digest {'a' * 64}: /tmp/WINDOWS_INSTALLER_VISUAL_AUDIT.source.json",
            failures,
        )
        self.assertFalse(any(item.startswith("FAIL flagship_product_readiness:") for item in failures))

    def test_collect_current_blocking_failures_ignores_recoverable_flagship_gate_when_it_is_the_only_blocker(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="release-ready-flagship-only-cycle-") as temp_dir:
            root = Path(temp_dir)
            published = root / "published"
            registry = root / "registry"
            published.mkdir(parents=True, exist_ok=True)
            registry.mkdir(parents=True, exist_ok=True)

            (registry / "RELEASE_CHANNEL.generated.json").write_text(
                json.dumps(
                    {
                        "status": "published",
                        "version": "run-test",
                        "channel": "stable",
                        "supportabilityState": "gold_supported",
                        "rolloutState": "public_stable",
                    }
                ),
                encoding="utf-8",
            )
            (published / "FLAGSHIP_PRODUCT_READINESS_GATE.generated.json").write_text(
                json.dumps(
                    {
                        "contract_name": "chummer.flagship_product_readiness_gate.v1",
                        "status": "fail",
                        "verdict": "NOT_FLAGSHIP_PRODUCT_READY",
                        "pass": False,
                        "summary": {
                            "contract_name": "fleet.flagship_product_readiness",
                            "status": "fail",
                            "pass": False,
                            "completion_audit_status": "pass",
                            "flagship_readiness_audit_status": "pass",
                            "missing_count": 0,
                            "scoped_missing_count": 0,
                            "coverage_gap_keys": [],
                            "scoped_coverage_gap_keys": [],
                            "launch_critical_nested_blockers": [
                                "final gold janitor state is 'fail'",
                                "final gold janitor verdict is 'NOT_GOLD'",
                            ],
                        },
                    }
                ),
                encoding="utf-8",
            )
            (published / "PUBLIC_EDGE_POSTDEPLOY_GATE.generated.json").write_text(
                json.dumps(passing_public_edge_postdeploy_payload(module)),
                encoding="utf-8",
            )
            (published / "WINDOWS_INSTALLER_VISUAL_AUDIT.generated.json").write_text(
                json.dumps({"status": "pass"}),
                encoding="utf-8",
            )
            (published / "GOOGLE_OAUTH_LINKING_PROOF.generated.json").write_text(
                json.dumps({"status": "pass"}),
                encoding="utf-8",
            )

            with (
                mock.patch.object(module, "PUBLISHED_ROOT", published),
                mock.patch.object(module, "REGISTRY_PUBLISHED_ROOT", registry),
            ):
                failures = module.collect_current_blocking_failures()

        self.assertEqual([], failures)

    def test_collect_current_blocking_failures_includes_missing_windows_gold_proof_artifact(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="release-ready-windows-proof-missing-") as temp_dir:
            root = Path(temp_dir)
            published = root / "published"
            registry = root / "registry"
            published.mkdir(parents=True, exist_ok=True)
            registry.mkdir(parents=True, exist_ok=True)

            (registry / "RELEASE_CHANNEL.generated.json").write_text(
                json.dumps(
                    {
                        "status": "published",
                        "version": "run-test",
                        "channel": "stable",
                        "supportabilityState": "gold_supported",
                        "rolloutState": "public_stable",
                    }
                ),
                encoding="utf-8",
            )
            (published / "FLAGSHIP_PRODUCT_READINESS_GATE.generated.json").write_text(
                json.dumps({"status": "pass"}),
                encoding="utf-8",
            )
            (published / "PUBLIC_EDGE_POSTDEPLOY_GATE.generated.json").write_text(
                json.dumps(passing_public_edge_postdeploy_payload(module)),
                encoding="utf-8",
            )
            (published / "WINDOWS_INSTALLER_VISUAL_AUDIT.generated.json").write_text(
                json.dumps(
                    {
                        "status": "fail",
                        "artifact": {
                            "sha256": "a" * 64,
                        },
                        "visualAuditSource": {
                            "artifactSha256": "b" * 64,
                            "path": "/tmp/WINDOWS_INSTALLER_VISUAL_AUDIT.source.json",
                        },
                        "failures": [
                            "Windows installer visual audit source digest does not match promoted installer",
                        ],
                    }
                ),
                encoding="utf-8",
            )
            (published / "WINDOWS_INSTALLER_VISUAL_AUDIT_INTAKE_REQUEST.generated.json").write_text(
                json.dumps(
                    {
                        "contract_name": "chummer.windows_installer_visual_audit_intake_request.v1",
                        "preferred_drop_path": "/tmp/windows-proof.zip",
                        "preferred_zip_name": "windows-proof.zip",
                        "required_zip_filename": "windows-proof.zip",
                    }
                ),
                encoding="utf-8",
            )

            with (
                mock.patch.object(module, "PUBLISHED_ROOT", published),
                mock.patch.object(module, "REGISTRY_PUBLISHED_ROOT", registry),
                mock.patch.object(
                    module,
                    "verify_windows_visual_intake_request_receipt",
                    return_value=(
                        True,
                        {
                            "status": "pass",
                            "issues": [],
                            "recovery_pack_pass": True,
                            "operator_action_still_required": True,
                        },
                    ),
                ),
            ):
                failures = module.collect_current_blocking_failures()

        self.assertIn(
            "FAIL windows_installer_visual_audit: Windows installer visual audit source digest does not match promoted installer",
            failures,
        )
        self.assertIn(
            "FAIL windows_installer_visual_audit: windows installer gold proof artifact is still missing: /tmp/windows-proof.zip",
            failures,
        )

    def test_collect_current_blocking_failures_includes_google_oauth_linking_proof(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="release-ready-google-oauth-blocker-") as temp_dir:
            root = Path(temp_dir)
            published = root / "published"
            registry = root / "registry"
            published.mkdir(parents=True, exist_ok=True)
            registry.mkdir(parents=True, exist_ok=True)

            (registry / "RELEASE_CHANNEL.generated.json").write_text(
                json.dumps(
                    {
                        "status": "published",
                        "version": "run-test",
                        "channel": "stable",
                        "supportabilityState": "gold_supported",
                        "rolloutState": "public_stable",
                    }
                ),
                encoding="utf-8",
            )
            (published / "FLAGSHIP_PRODUCT_READINESS_GATE.generated.json").write_text(
                json.dumps({"status": "pass"}),
                encoding="utf-8",
            )
            (published / "PUBLIC_EDGE_POSTDEPLOY_GATE.generated.json").write_text(
                json.dumps(passing_public_edge_postdeploy_payload(module)),
                encoding="utf-8",
            )
            (published / "WINDOWS_INSTALLER_VISUAL_AUDIT.generated.json").write_text(
                json.dumps({"status": "pass"}),
                encoding="utf-8",
            )
            (published / "GOOGLE_OAUTH_LINKING_PROOF.generated.json").write_text(
                json.dumps(
                    {
                        "status": "fail",
                        "failures": [
                            "operator_end_to_end_evidence: missing operator evidence receipt: /tmp/operator-evidence.json",
                        ],
                    }
                ),
                encoding="utf-8",
            )

            with (
                mock.patch.object(module, "PUBLISHED_ROOT", published),
                mock.patch.object(module, "REGISTRY_PUBLISHED_ROOT", registry),
            ):
                failures = module.collect_current_blocking_failures()

        self.assertEqual(
            [
                "FAIL google_oauth_linking_proof: operator_end_to_end_evidence: missing operator evidence receipt: /tmp/operator-evidence.json",
            ],
            failures,
        )

    def test_collect_current_blocking_failures_skips_effectively_green_google_oauth(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="release-ready-google-oauth-effective-pass-") as temp_dir:
            root = Path(temp_dir)
            published = root / "published"
            registry = root / "registry"
            published.mkdir(parents=True, exist_ok=True)
            registry.mkdir(parents=True, exist_ok=True)

            (registry / "RELEASE_CHANNEL.generated.json").write_text(
                json.dumps(
                    {
                        "status": "published",
                        "version": "run-test",
                        "channel": "stable",
                        "supportabilityState": "gold_supported",
                        "rolloutState": "public_stable",
                    }
                ),
                encoding="utf-8",
            )
            (published / "FLAGSHIP_PRODUCT_READINESS_GATE.generated.json").write_text(
                json.dumps({"status": "pass"}),
                encoding="utf-8",
            )
            (published / "PUBLIC_EDGE_POSTDEPLOY_GATE.generated.json").write_text(
                json.dumps(passing_public_edge_postdeploy_payload(module)),
                encoding="utf-8",
            )
            (published / "WINDOWS_INSTALLER_VISUAL_AUDIT.generated.json").write_text(
                json.dumps({"status": "pass"}),
                encoding="utf-8",
            )
            (published / "GOOGLE_OAUTH_LINKING_PROOF.generated.json").write_text(
                json.dumps(
                    {
                        "status": "fail",
                        "quick_handoff_probe": {"pass": True},
                        "signed_in_link_handoff": {"status": "fail", "pass": False},
                        "operator_end_to_end_evidence": {"pass": True, "exists": True},
                        "operator_request_artifacts": {"request_status": "not_required"},
                        "failures": [
                            "signed_in_link_handoff: /home returned 302, expected 200",
                            "signed_in_link_handoff: /auth/google/link did not produce a complete Google OAuth redirect contract",
                        ],
                    }
                ),
                encoding="utf-8",
            )

            with (
                mock.patch.object(module, "PUBLISHED_ROOT", published),
                mock.patch.object(module, "REGISTRY_PUBLISHED_ROOT", registry),
            ):
                failures = module.collect_current_blocking_failures()

        self.assertEqual([], failures)

    def test_collect_current_blocking_failures_skips_google_oauth_when_effective_status_is_not_required(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="release-ready-google-oauth-stale-request-") as temp_dir:
            root = Path(temp_dir)
            published = root / "published"
            registry = root / "registry"
            published.mkdir(parents=True, exist_ok=True)
            registry.mkdir(parents=True, exist_ok=True)

            (registry / "RELEASE_CHANNEL.generated.json").write_text(
                json.dumps(
                    {
                        "status": "published",
                        "version": "run-test",
                        "channel": "stable",
                        "supportabilityState": "gold_supported",
                        "rolloutState": "public_stable",
                    }
                ),
                encoding="utf-8",
            )
            (published / "FLAGSHIP_PRODUCT_READINESS_GATE.generated.json").write_text(
                json.dumps({"status": "pass"}),
                encoding="utf-8",
            )
            (published / "PUBLIC_EDGE_POSTDEPLOY_GATE.generated.json").write_text(
                json.dumps(passing_public_edge_postdeploy_payload(module)),
                encoding="utf-8",
            )
            (published / "WINDOWS_INSTALLER_VISUAL_AUDIT.generated.json").write_text(
                json.dumps({"status": "pass"}),
                encoding="utf-8",
            )
            (published / "GOOGLE_OAUTH_LINKING_PROOF.generated.json").write_text(
                json.dumps(
                    {
                        "status": "fail",
                        "quick_handoff_probe": {"pass": True},
                        "signed_in_link_handoff": {"status": "fail", "pass": False},
                        "operator_end_to_end_evidence": {"pass": True, "exists": True},
                        "operator_request_artifacts": {
                            "request_status": "operator_action_required",
                            "request_effective_status": "not_required",
                        },
                        "failures": [
                            "signed_in_link_handoff: /home returned 302, expected 200",
                            "signed_in_link_handoff: /auth/google/link did not produce a complete Google OAuth redirect contract",
                        ],
                    }
                ),
                encoding="utf-8",
            )

            with (
                mock.patch.object(module, "PUBLISHED_ROOT", published),
                mock.patch.object(module, "REGISTRY_PUBLISHED_ROOT", registry),
            ):
                failures = module.collect_current_blocking_failures()

        self.assertEqual([], failures)

    def test_google_oauth_release_truth_effective_pass_accepts_user_paused_signin_automation(self) -> None:
        module = load_module()

        self.assertTrue(
            module.google_oauth_release_truth_effective_pass(
                {
                    "status": "fail",
                    "operator_request_artifacts": {
                        "request_status": "not_required",
                        "request_effective_status": "not_required",
                        "operator_action_still_required": False,
                    },
                    "failures": [
                        "auth_signin_automation_paused: paused by user request on 2026-07-08",
                    ],
                }
            )
        )

    def test_collect_current_blocking_failures_skips_user_paused_google_oauth(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="release-ready-google-oauth-paused-user-request-") as temp_dir:
            root = Path(temp_dir)
            published = root / "published"
            registry = root / "registry"
            published.mkdir(parents=True, exist_ok=True)
            registry.mkdir(parents=True, exist_ok=True)

            (registry / "RELEASE_CHANNEL.generated.json").write_text(
                json.dumps(
                    {
                        "status": "published",
                        "version": "run-test",
                        "channel": "stable",
                        "supportabilityState": "gold_supported",
                        "rolloutState": "public_stable",
                    }
                ),
                encoding="utf-8",
            )
            (published / "FLAGSHIP_PRODUCT_READINESS_GATE.generated.json").write_text(
                json.dumps({"status": "pass"}),
                encoding="utf-8",
            )
            (published / "PUBLIC_EDGE_POSTDEPLOY_GATE.generated.json").write_text(
                json.dumps(passing_public_edge_postdeploy_payload(module)),
                encoding="utf-8",
            )
            (published / "WINDOWS_INSTALLER_VISUAL_AUDIT.generated.json").write_text(
                json.dumps({"status": "pass"}),
                encoding="utf-8",
            )
            (published / "GOOGLE_OAUTH_LINKING_PROOF.generated.json").write_text(
                json.dumps(
                    {
                        "status": "fail",
                        "operator_request_artifacts": {
                            "request_status": "not_required",
                            "request_effective_status": "not_required",
                            "operator_action_still_required": False,
                        },
                        "failures": [
                            "auth_signin_automation_paused: paused by user request on 2026-07-08",
                        ],
                    }
                ),
                encoding="utf-8",
            )

            with (
                mock.patch.object(module, "PUBLISHED_ROOT", published),
                mock.patch.object(module, "REGISTRY_PUBLISHED_ROOT", registry),
            ):
                failures = module.collect_current_blocking_failures()

        self.assertEqual([], failures)

    def test_collect_current_blocking_failures_rejects_pass_shaped_google_oauth_receipt_with_failures(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="release-ready-google-oauth-pass-shaped-failures-") as temp_dir:
            root = Path(temp_dir)
            published = root / "published"
            registry = root / "registry"
            published.mkdir(parents=True, exist_ok=True)
            registry.mkdir(parents=True, exist_ok=True)

            (registry / "RELEASE_CHANNEL.generated.json").write_text(
                json.dumps(
                    {
                        "status": "published",
                        "version": "run-test",
                        "channel": "stable",
                        "supportabilityState": "gold_supported",
                        "rolloutState": "public_stable",
                    }
                ),
                encoding="utf-8",
            )
            (published / "FLAGSHIP_PRODUCT_READINESS_GATE.generated.json").write_text(
                json.dumps({"status": "pass"}),
                encoding="utf-8",
            )
            (published / "PUBLIC_EDGE_POSTDEPLOY_GATE.generated.json").write_text(
                json.dumps(passing_public_edge_postdeploy_payload(module)),
                encoding="utf-8",
            )
            (published / "WINDOWS_INSTALLER_VISUAL_AUDIT.generated.json").write_text(
                json.dumps({"status": "pass"}),
                encoding="utf-8",
            )
            (published / "GOOGLE_OAUTH_LINKING_PROOF.generated.json").write_text(
                json.dumps(
                    {
                        "status": "pass",
                        "quick_handoff_probe": {"pass": True},
                        "signed_in_link_handoff": {"status": "fail", "pass": False},
                        "operator_end_to_end_evidence": {"pass": True, "exists": True},
                        "operator_request_artifacts": {"request_status": "not_required"},
                        "failures": [
                            "operator_end_to_end_evidence: missing operator evidence receipt: /tmp/operator-evidence.json",
                        ],
                    }
                ),
                encoding="utf-8",
            )

            with (
                mock.patch.object(module, "PUBLISHED_ROOT", published),
                mock.patch.object(module, "REGISTRY_PUBLISHED_ROOT", registry),
            ):
                failures = module.collect_current_blocking_failures()

        self.assertEqual(
            [
                "FAIL google_oauth_linking_proof: operator_end_to_end_evidence: missing operator evidence receipt: /tmp/operator-evidence.json",
            ],
            failures,
        )

    def test_collect_current_blocking_failures_ignores_public_edge_preflight_only_failure(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="release-ready-public-edge-preflight-") as temp_dir:
            root = Path(temp_dir)
            published = root / "published"
            registry = root / "registry"
            published.mkdir(parents=True, exist_ok=True)
            registry.mkdir(parents=True, exist_ok=True)

            (registry / "RELEASE_CHANNEL.generated.json").write_text(
                json.dumps(
                    {
                        "status": "published",
                        "version": "run-test",
                        "channel": "stable",
                        "supportabilityState": "gold_supported",
                        "rolloutState": "public_stable",
                    }
                ),
                encoding="utf-8",
            )
            (published / "FLAGSHIP_PRODUCT_READINESS_GATE.generated.json").write_text(
                json.dumps(
                    {
                        "contract_name": "chummer.flagship_product_readiness_gate.v1",
                        "status": "pass",
                        "verdict": "FLAGSHIP_PRODUCT_READY",
                        "summary": {
                            "contract_name": "fleet.flagship_product_readiness",
                            "completion_audit_status": "pass",
                            "flagship_readiness_audit_status": "pass",
                            "missing_count": 0,
                            "scoped_missing_count": 0,
                            "coverage_gap_keys": [],
                            "scoped_coverage_gap_keys": [],
                            "launch_critical_nested_blockers": [],
                        },
                    }
                ),
                encoding="utf-8",
            )
            (published / "PUBLIC_EDGE_POSTDEPLOY_GATE.generated.json").write_text(
                json.dumps(
                    {
                        "status": "fail",
                        "preflightStatus": "fail",
                        "preflightBlockingLockCount": 1,
                        "failures": ["public-edge deploy preflight is not pass"],
                    }
                ),
                encoding="utf-8",
            )
            (published / "WINDOWS_INSTALLER_VISUAL_AUDIT.generated.json").write_text(
                json.dumps({"status": "pass"}),
                encoding="utf-8",
            )
            (published / "GOOGLE_OAUTH_LINKING_PROOF.generated.json").write_text(
                json.dumps({"status": "pass"}),
                encoding="utf-8",
            )

            with (
                mock.patch.object(module, "PUBLISHED_ROOT", published),
                mock.patch.object(module, "REGISTRY_PUBLISHED_ROOT", registry),
            ):
                failures = module.collect_current_blocking_failures()

        self.assertEqual([], failures)

    def test_collect_current_blocking_failures_rejects_stale_pass_public_edge_schema(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="release-ready-public-edge-stale-schema-") as temp_dir:
            root = Path(temp_dir)
            published = root / "published"
            registry = root / "registry"
            published.mkdir(parents=True, exist_ok=True)
            registry.mkdir(parents=True, exist_ok=True)

            (registry / "RELEASE_CHANNEL.generated.json").write_text(
                json.dumps(
                    {
                        "status": "published",
                        "version": "run-test",
                        "channel": "stable",
                        "supportabilityState": "gold_supported",
                        "rolloutState": "public_stable",
                    }
                ),
                encoding="utf-8",
            )
            (published / "FLAGSHIP_PRODUCT_READINESS_GATE.generated.json").write_text(
                json.dumps({"status": "pass"}),
                encoding="utf-8",
            )
            (published / "PUBLIC_EDGE_POSTDEPLOY_GATE.generated.json").write_text(
                json.dumps(
                    {
                        "contractName": "chummer.public_edge_postdeploy_gate.v1",
                        "status": "pass",
                        "generatedAtUtc": "2026-07-04T00:00:00Z",
                        "frontdoorNavigationStatus": "pass",
                    }
                ),
                encoding="utf-8",
            )
            (published / "WINDOWS_INSTALLER_VISUAL_AUDIT.generated.json").write_text(
                json.dumps({"status": "pass"}),
                encoding="utf-8",
            )
            (published / "GOOGLE_OAUTH_LINKING_PROOF.generated.json").write_text(
                json.dumps({"status": "pass"}),
                encoding="utf-8",
            )

            with (
                mock.patch.object(module, "PUBLISHED_ROOT", published),
                mock.patch.object(module, "REGISTRY_PUBLISHED_ROOT", registry),
            ):
                failures = module.collect_current_blocking_failures()

        self.assertTrue(any("public_edge_postdeploy_gate receipt missing current fields:" in item for item in failures))
        self.assertTrue(any("frontdoorNavigationAnchorArtifactContract" in item for item in failures))
        self.assertTrue(any("frontdoorNavigationAnchorFinalPath" in item for item in failures))

    def test_public_edge_release_blocking_reasons_reject_v1_raw_identity_and_private_cache(self) -> None:
        module = load_module()
        payload = {field: None for field in module.PUBLIC_EDGE_POSTDEPLOY_REQUIRED_FIELDS}
        payload.update(
            {
                "contractName": module.PUBLIC_EDGE_POSTDEPLOY_CONTRACT_NAME,
                "status": "pass",
                "pwaOfflineCacheStatus": "pass",
                "pwaOfflineCacheArtifactContract": "chummer.pwa_offline_cache.v1",
                "pwaOfflineCacheStaticPaths": ["/mobile/player?sessionId=private-session"],
                "pwaOfflineCachePrivateApiCached": True,
                "frontdoorNavigationStatus": "pass",
                "frontdoorNavigationMobileArtifactContract": "chummer.frontdoor_mobile_launch.v1",
                "frontdoorNavigationAnchorArtifactContract": "chummer.frontdoor_mobile_anchor_redirect.v1",
                "frontdoorNavigationFinalUrl": "https://chummer.run/mobile/player?sessionId=private-session",
                "frontdoorNavigationGmRoute": "/mobile/gm?sessionId=private-session",
                "frontdoorNavigationGmFinalUrl": "https://chummer.run/mobile/gm?deviceId=private-device",
                "frontdoorNavigationAnchorEntryUrl": "https://chummer.run/#turn-runsite-card",
                "frontdoorNavigationAnchorFinalUrl": "https://chummer.run/mobile/player?sessionId=private-session#turn-runsite-card",
            }
        )

        reasons = module.public_edge_postdeploy_release_blocking_reasons(payload)

        self.assertIn(
            "public_edge_postdeploy_gate pwaOfflineCacheArtifactContract is not chummer.pwa_offline_cache.v2",
            reasons,
        )
        self.assertIn(
            "public_edge_postdeploy_gate frontdoorNavigationMobileArtifactContract is not chummer.frontdoor_mobile_launch.v2",
            reasons,
        )
        self.assertIn("public-edge postdeploy front-door evidence contains raw private identity", reasons)
        self.assertIn("public-edge postdeploy PWA offline static cache contains a private or query-bearing route", reasons)
        self.assertIn("public-edge postdeploy PWA offline cache did not prove private API responses remain uncached", reasons)

    def test_public_edge_release_blocking_reasons_reject_unexpected_gate_contract(self) -> None:
        module = load_module()

        reasons = module.public_edge_postdeploy_release_blocking_reasons(
            {"contractName": "chummer.public_edge_postdeploy_gate.v0", "status": "pass"}
        )

        self.assertEqual(
            ["public_edge_postdeploy_gate receipt contract is not chummer.public_edge_postdeploy_gate.v1"],
            reasons,
        )

    def test_collect_current_blocking_failures_fails_closed_on_workspace_portal_release_channel_drift(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="release-ready-workspace-portal-drift-") as temp_dir:
            root = Path(temp_dir)
            published = root / "published"
            registry = root / "registry"
            portal = root / "workspace-portal"
            published.mkdir(parents=True, exist_ok=True)
            registry.mkdir(parents=True, exist_ok=True)
            portal.mkdir(parents=True, exist_ok=True)

            (registry / "RELEASE_CHANNEL.generated.json").write_text(
                json.dumps(
                    {
                        "status": "published",
                        "version": "run-test",
                        "channel": "stable",
                        "supportabilityState": "gold_supported",
                        "rolloutState": "public_stable",
                    }
                ),
                encoding="utf-8",
            )
            (published / "FLAGSHIP_PRODUCT_READINESS_GATE.generated.json").write_text(
                json.dumps(
                    {
                        "contract_name": "chummer.flagship_product_readiness_gate.v1",
                        "status": "pass",
                        "verdict": "FLAGSHIP_PRODUCT_READY",
                        "summary": {
                            "contract_name": "fleet.flagship_product_readiness",
                            "completion_audit_status": "pass",
                            "flagship_readiness_audit_status": "pass",
                            "missing_count": 0,
                            "scoped_missing_count": 0,
                            "coverage_gap_keys": [],
                            "scoped_coverage_gap_keys": [],
                            "launch_critical_nested_blockers": [],
                        },
                    }
                ),
                encoding="utf-8",
            )
            (published / "PUBLIC_EDGE_POSTDEPLOY_GATE.generated.json").write_text(
                json.dumps(passing_public_edge_postdeploy_payload(module)),
                encoding="utf-8",
            )
            (published / "WINDOWS_INSTALLER_VISUAL_AUDIT.generated.json").write_text(
                json.dumps({"status": "pass"}),
                encoding="utf-8",
            )
            (published / "GOOGLE_OAUTH_LINKING_PROOF.generated.json").write_text(
                json.dumps({"status": "pass"}),
                encoding="utf-8",
            )

            drift_path = portal / "RELEASE_CHANNEL.generated.json"
            drift_path.write_text(
                json.dumps(
                    {
                        "status": "published",
                        "version": "run-old",
                        "channel": "stable",
                        "supportabilityState": "gold_supported",
                        "rolloutState": "public_stable",
                    }
                ),
                encoding="utf-8",
            )

            with (
                mock.patch.object(module, "PUBLISHED_ROOT", published),
                mock.patch.object(module, "REGISTRY_PUBLISHED_ROOT", registry),
                mock.patch.object(module, "WORKSPACE_PORTAL_RELEASE_CHANNEL_CANDIDATES", (drift_path,)),
            ):
                failures = module.collect_current_blocking_failures()

        self.assertEqual(1, len(failures))
        self.assertIn("FAIL release_channel: workspace portal release channel artifact", failures[0])
        self.assertIn(module.display_path(drift_path), failures[0])
        self.assertIn("local channel=stable, version=run-old", failures[0])
        self.assertIn("authoritative channel=stable, version=run-test", failures[0])

    def test_collect_current_blocking_failures_dedupes_workspace_portal_alias_paths(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="release-ready-workspace-portal-alias-") as temp_dir:
            root = Path(temp_dir)
            published = root / "published"
            registry = root / "registry"
            portal = root / "workspace-portal"
            published.mkdir(parents=True, exist_ok=True)
            registry.mkdir(parents=True, exist_ok=True)
            portal.mkdir(parents=True, exist_ok=True)

            (registry / "RELEASE_CHANNEL.generated.json").write_text(
                json.dumps(
                    {
                        "status": "published",
                        "version": "run-test",
                        "channel": "stable",
                        "supportabilityState": "gold_supported",
                        "rolloutState": "public_stable",
                    }
                ),
                encoding="utf-8",
            )
            (published / "FLAGSHIP_PRODUCT_READINESS_GATE.generated.json").write_text(
                json.dumps(
                    {
                        "contract_name": "chummer.flagship_product_readiness_gate.v1",
                        "status": "pass",
                        "verdict": "FLAGSHIP_PRODUCT_READY",
                        "summary": {
                            "contract_name": "fleet.flagship_product_readiness",
                            "completion_audit_status": "pass",
                            "flagship_readiness_audit_status": "pass",
                            "missing_count": 0,
                            "scoped_missing_count": 0,
                            "coverage_gap_keys": [],
                            "scoped_coverage_gap_keys": [],
                            "launch_critical_nested_blockers": [],
                        },
                    }
                ),
                encoding="utf-8",
            )
            (published / "PUBLIC_EDGE_POSTDEPLOY_GATE.generated.json").write_text(
                json.dumps(passing_public_edge_postdeploy_payload(module)),
                encoding="utf-8",
            )
            (published / "WINDOWS_INSTALLER_VISUAL_AUDIT.generated.json").write_text(
                json.dumps({"status": "pass"}),
                encoding="utf-8",
            )
            (published / "GOOGLE_OAUTH_LINKING_PROOF.generated.json").write_text(
                json.dumps({"status": "pass"}),
                encoding="utf-8",
            )

            drift_path = portal / "RELEASE_CHANNEL.generated.json"
            drift_path.write_text(
                json.dumps(
                    {
                        "status": "published",
                        "version": "run-old",
                        "channel": "stable",
                        "supportabilityState": "gold_supported",
                        "rolloutState": "public_stable",
                    }
                ),
                encoding="utf-8",
            )
            alias_path = portal / "RELEASE_CHANNEL.alias.generated.json"
            alias_path.symlink_to(drift_path)

            with (
                mock.patch.object(module, "PUBLISHED_ROOT", published),
                mock.patch.object(module, "REGISTRY_PUBLISHED_ROOT", registry),
                mock.patch.object(module, "WORKSPACE_PORTAL_RELEASE_CHANNEL_CANDIDATES", (drift_path, alias_path)),
            ):
                failures = module.collect_current_blocking_failures()

        self.assertEqual(1, len(failures))
        self.assertIn(module.display_path(drift_path), failures[0])

    def test_collect_current_blocking_failures_uses_public_release_snapshot_runtime_override(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="release-ready-public-edge-runtime-") as temp_dir:
            root = Path(temp_dir)
            published = root / "published"
            registry = root / "registry"
            snapshot = root / "PUBLIC_RELEASE_SNAPSHOT.generated.json"
            published.mkdir(parents=True, exist_ok=True)
            registry.mkdir(parents=True, exist_ok=True)

            (registry / "RELEASE_CHANNEL.generated.json").write_text(
                json.dumps(
                    {
                        "status": "published",
                        "version": "run-test",
                        "channel": "stable",
                        "supportabilityState": "gold_supported",
                        "rolloutState": "public_stable",
                    }
                ),
                encoding="utf-8",
            )
            (published / "FLAGSHIP_PRODUCT_READINESS_GATE.generated.json").write_text(
                json.dumps(
                    {
                        "contract_name": "chummer.flagship_product_readiness_gate.v1",
                        "status": "pass",
                        "summary": {
                            "contract_name": "fleet.flagship_product_readiness",
                            "completion_audit_status": "pass",
                            "flagship_readiness_audit_status": "pass",
                            "missing_count": 0,
                            "scoped_missing_count": 0,
                            "coverage_gap_keys": [],
                            "scoped_coverage_gap_keys": [],
                            "launch_critical_nested_blockers": [],
                        },
                    }
                ),
                encoding="utf-8",
            )
            (published / "PUBLIC_EDGE_POSTDEPLOY_GATE.generated.json").write_text(
                json.dumps(passing_public_edge_postdeploy_payload(module)),
                encoding="utf-8",
            )
            (published / "WINDOWS_INSTALLER_VISUAL_AUDIT.generated.json").write_text(
                json.dumps({"status": "pass"}),
                encoding="utf-8",
            )
            (published / "GOOGLE_OAUTH_LINKING_PROOF.generated.json").write_text(
                json.dumps({"status": "pass"}),
                encoding="utf-8",
            )
            snapshot.write_text(
                json.dumps(
                    {
                        "release_truth": {
                            "public_edge_postdeploy_gate": {
                                "status": "fail",
                                "verdict": "RUNTIME_PREFLIGHT_FAIL",
                                "runtime_override_applied": True,
                                "runtime_override_reason": "Current mounted public-edge preflight status=fail. activeLockCount=2 foreignLockCount=2 staleForeignLockCount=2.",
                                "runtime_observation": {
                                    "status": "fail",
                                    "overlay_root": "/tmp/public-edge-overlay/app",
                                    "blocking_findings": [
                                        "active_build_lane: bash pid 191868 matches build-chummer6-linux",
                                        "public_edge_overlay_marker_missing: overlay .codex-studio/runtime/PUBLIC_EDGE_PORTAL_OVERLAY_BUILD_INFO.generated.json missing markers",
                                    ],
                                },
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )

            with (
                mock.patch.object(module, "PUBLISHED_ROOT", published),
                mock.patch.object(module, "REGISTRY_PUBLISHED_ROOT", registry),
                mock.patch.object(module, "PUBLIC_RELEASE_SNAPSHOT", snapshot),
            ):
                failures = module.collect_current_blocking_failures()

        self.assertIn(
            "FAIL public_edge_postdeploy_gate: public_edge_postdeploy_gate release truth verdict is RUNTIME_PREFLIGHT_FAIL",
            failures,
        )
        self.assertIn(
            "FAIL public_edge_postdeploy_gate: Current mounted public-edge preflight status=fail. activeLockCount=2 foreignLockCount=2 staleForeignLockCount=2.",
            failures,
        )
        self.assertIn(
            "FAIL public_edge_postdeploy_gate: public_edge_overlay_marker_missing: overlay .codex-studio/runtime/PUBLIC_EDGE_PORTAL_OVERLAY_BUILD_INFO.generated.json missing markers",
            failures,
        )

    def test_collect_current_blocking_failures_rejects_flagship_gate_unexpected_verdict(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="release-ready-flagship-gate-verdict-") as temp_dir:
            root = Path(temp_dir)
            published = root / "published"
            registry = root / "registry"
            published.mkdir(parents=True, exist_ok=True)
            registry.mkdir(parents=True, exist_ok=True)

            (registry / "RELEASE_CHANNEL.generated.json").write_text(
                json.dumps(
                    {
                        "status": "published",
                        "version": "run-test",
                        "channel": "stable",
                        "supportabilityState": "gold_supported",
                        "rolloutState": "public_stable",
                    }
                ),
                encoding="utf-8",
            )
            (published / "FLAGSHIP_PRODUCT_READINESS_GATE.generated.json").write_text(
                json.dumps(
                    {
                        "contract_name": "chummer.flagship_product_readiness_gate.v1",
                        "status": "pass",
                        "verdict": "NOT_FLAGSHIP_PRODUCT_READY",
                        "summary": {
                            "contract_name": "fleet.flagship_product_readiness",
                            "completion_audit_status": "pass",
                            "flagship_readiness_audit_status": "pass",
                            "missing_count": 0,
                            "scoped_missing_count": 0,
                            "coverage_gap_keys": [],
                            "scoped_coverage_gap_keys": [],
                            "launch_critical_nested_blockers": [],
                        },
                    }
                ),
                encoding="utf-8",
            )
            (published / "PUBLIC_EDGE_POSTDEPLOY_GATE.generated.json").write_text(
                json.dumps(passing_public_edge_postdeploy_payload(module)),
                encoding="utf-8",
            )
            (published / "WINDOWS_INSTALLER_VISUAL_AUDIT.generated.json").write_text(
                json.dumps({"status": "pass"}),
                encoding="utf-8",
            )
            (published / "GOOGLE_OAUTH_LINKING_PROOF.generated.json").write_text(
                json.dumps({"status": "pass"}),
                encoding="utf-8",
            )

            with (
                mock.patch.object(module, "PUBLISHED_ROOT", published),
                mock.patch.object(module, "REGISTRY_PUBLISHED_ROOT", registry),
            ):
                failures = module.collect_current_blocking_failures()

        self.assertEqual(
            [
                "FAIL flagship_product_readiness: "
                "flagship_product_readiness gate has unexpected verdict "
                "(expected FLAGSHIP_PRODUCT_READY)"
            ],
            failures,
        )

    def test_collect_current_blocking_failures_rejects_pass_shaped_flagship_gate_with_failed_gates(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="release-ready-flagship-gate-failed-gates-") as temp_dir:
            root = Path(temp_dir)
            published = root / "published"
            registry = root / "registry"
            published.mkdir(parents=True, exist_ok=True)
            registry.mkdir(parents=True, exist_ok=True)

            (registry / "RELEASE_CHANNEL.generated.json").write_text(
                json.dumps(
                    {
                        "status": "published",
                        "version": "run-test",
                        "channel": "stable",
                        "supportabilityState": "gold_supported",
                        "rolloutState": "public_stable",
                    }
                ),
                encoding="utf-8",
            )
            (published / "FLAGSHIP_PRODUCT_READINESS_GATE.generated.json").write_text(
                json.dumps(
                    {
                        "contract_name": "chummer.flagship_product_readiness_gate.v1",
                        "status": "pass",
                        "verdict": "FLAGSHIP_PRODUCT_READY",
                        "failed_gates": ["verify_flagship_product_readiness"],
                        "summary": {
                            "contract_name": "fleet.flagship_product_readiness",
                            "completion_audit_status": "pass",
                            "flagship_readiness_audit_status": "pass",
                            "missing_count": 0,
                            "scoped_missing_count": 0,
                            "coverage_gap_keys": [],
                            "scoped_coverage_gap_keys": [],
                            "launch_critical_nested_blockers": [],
                        },
                    }
                ),
                encoding="utf-8",
            )
            (published / "PUBLIC_EDGE_POSTDEPLOY_GATE.generated.json").write_text(
                json.dumps(passing_public_edge_postdeploy_payload(module)),
                encoding="utf-8",
            )
            (published / "WINDOWS_INSTALLER_VISUAL_AUDIT.generated.json").write_text(
                json.dumps({"status": "pass"}),
                encoding="utf-8",
            )
            (published / "GOOGLE_OAUTH_LINKING_PROOF.generated.json").write_text(
                json.dumps({"status": "pass"}),
                encoding="utf-8",
            )

            with (
                mock.patch.object(module, "PUBLISHED_ROOT", published),
                mock.patch.object(module, "REGISTRY_PUBLISHED_ROOT", registry),
            ):
                failures = module.collect_current_blocking_failures()

        self.assertEqual(
            [
                "FAIL flagship_product_readiness: verify_flagship_product_readiness",
            ],
            failures,
        )

    def test_main_preserves_public_release_snapshot_truth_gate_failure(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="release-ready-snapshot-truth-") as temp_dir:
            output_path = Path(temp_dir) / "RELEASE_READY.generated.json"
            snapshot_audit = Path(temp_dir) / "PUBLIC_RELEASE_SNAPSHOT_READONLY_AUDIT.generated.json"
            snapshot_audit.write_text(
                json.dumps(
                    {
                        "status": "pass",
                        "verdict": "SNAPSHOT_CONSISTENT_NOT_LAUNCH_READY",
                        "summary": "Snapshot is internally consistent with current launch truth, but the release is not launch-ready.",
                        "expected_top_level_blocker_ids": [
                            "release_posture:non_flagship_channel",
                            "release_truth:windows_installer_visual_audit",
                        ],
                        "expected_release_truth_blockers": ["windows_installer_visual_audit"],
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            process = mock.Mock(pid=1234, returncode=1)
            stdout = (
                "FAIL verify_public_release_snapshot_truth\n"
                "public_stable_conflicts_with_final_gold\n\n"
                "NOT RELEASE READY\n"
                "verify_public_release_snapshot_truth\n"
            )

            with mock.patch.object(module, "OUTPUT_PATH", output_path), \
                mock.patch.object(module, "PUBLIC_RELEASE_SNAPSHOT_READONLY_AUDIT", snapshot_audit), \
                mock.patch.object(module, "refresh_watcher_state", return_value={}), \
                mock.patch.object(
                    module,
                    "current_blocking_gate_artifacts",
                    return_value={
                        "public_release_snapshot_readonly_audit": {
                            "verdict": "SNAPSHOT_CONSISTENT_NOT_LAUNCH_READY",
                        }
                    },
                ), \
                mock.patch.object(module, "current_receipt_states", return_value={}), \
                mock.patch.object(
                    module,
                    "current_release_truth_root_context",
                    return_value={
                        "root_blocker_ids": [],
                        "root_blockers": [],
                        "root_blockers_generated_at": "",
                        "stable_promotion_command": "",
                        "post_promotion_verify_command": "",
                        "root_release_truth_source": "",
                    },
                ), \
                mock.patch.object(module, "release_ready_next_actions", return_value=[]), \
                mock.patch.object(
                    module,
                    "run_authoritative_release_controller",
                    return_value=live_controller_result(
                        module,
                        stdout=stdout,
                        returncode=1,
                    ),
                ):
                result = module.main()

            self.assertEqual(0, result)
            payload = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual("fail", payload["status"])
            self.assertEqual("NOT_RELEASE_READY", payload["verdict"])
            self.assertEqual(1, payload["returncode"])
            self.assertIn("FAIL verify_public_release_snapshot_truth", payload["failures"])
            self.assertIn("verify_public_release_snapshot_truth", payload["failures"])
            self.assertEqual(["verify_public_release_snapshot_truth", "verify_release_ready"], payload["failed_gates"])
            self.assertEqual(
                "SNAPSHOT_CONSISTENT_NOT_LAUNCH_READY",
                payload["blocking_gate_artifacts"]["public_release_snapshot_readonly_audit"]["verdict"],
            )

    def test_main_fails_closed_when_successful_exit_still_prints_failures(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="release-ready-contradictory-success-") as temp_dir:
            output_path = Path(temp_dir) / "RELEASE_READY.generated.json"

            process = mock.Mock(pid=1234, returncode=0)
            stdout = (
                "FAIL verify_public_edge_postdeploy_gate\n"
                "public edge postdeploy gate is missing\n\n"
                + passing_verifier_output(module)
            )

            with (
                mock.patch.object(module, "OUTPUT_PATH", output_path),
                mock.patch.object(module, "refresh_watcher_state", return_value={}),
                mock.patch.object(module, "current_blocking_gate_artifacts", return_value={}),
                mock.patch.object(module, "current_receipt_states", return_value={}),
                mock.patch.object(
                    module,
                    "current_release_truth_root_context",
                    return_value={
                        "root_blocker_ids": [],
                        "root_blockers": [],
                        "root_blockers_generated_at": "",
                        "stable_promotion_command": "",
                        "post_promotion_verify_command": "",
                        "root_release_truth_source": "",
                    },
                ),
                mock.patch.object(module, "release_ready_next_actions", return_value=[]),
                mock.patch.object(
                    module,
                    "run_authoritative_release_controller",
                    return_value=live_controller_result(module, stdout=stdout),
                ),
            ):
                result = module.main()

            self.assertEqual(0, result)
            payload = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual("fail", payload["status"])
            self.assertEqual("NOT_RELEASE_READY", payload["verdict"])
            self.assertEqual(0, payload["returncode"])
            self.assertFalse(payload["timed_out"])
            self.assertIn("FAIL verify_public_edge_postdeploy_gate", payload["failures"])
            self.assertEqual(["verify_public_edge_postdeploy_gate"], payload["failed_gates"])

    def test_main_fails_closed_when_successful_exit_has_workspace_portal_release_channel_drift(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="release-ready-drift-success-") as temp_dir:
            root = Path(temp_dir)
            output_path = root / "RELEASE_READY.generated.json"
            registry = root / "registry"
            portal = root / "workspace-portal"
            registry.mkdir(parents=True, exist_ok=True)
            portal.mkdir(parents=True, exist_ok=True)

            (registry / "RELEASE_CHANNEL.generated.json").write_text(
                json.dumps(
                    {
                        "status": "published",
                        "version": "run-test",
                        "channel": "stable",
                        "supportabilityState": "gold_supported",
                        "rolloutState": "public_stable",
                        "publishedAt": module.now_iso(),
                    }
                ),
                encoding="utf-8",
            )
            drift_path = portal / "RELEASE_CHANNEL.generated.json"
            drift_path.write_text(
                json.dumps(
                    {
                        "status": "published",
                        "version": "run-old",
                        "channel": "stable",
                        "supportabilityState": "gold_supported",
                        "rolloutState": "public_stable",
                    }
                ),
                encoding="utf-8",
            )

            process = mock.Mock(pid=1234, returncode=0)

            with (
                mock.patch.object(module, "OUTPUT_PATH", output_path),
                mock.patch.object(module, "REGISTRY_PUBLISHED_ROOT", registry),
                mock.patch.object(module, "WORKSPACE_PORTAL_RELEASE_CHANNEL_CANDIDATES", (drift_path,)),
                mock.patch.object(module, "current_blocker_precheck_enabled", return_value=False),
                mock.patch.object(module, "refresh_watcher_state", return_value={}),
                mock.patch.object(module, "current_blocking_gate_artifacts", return_value={}),
                mock.patch.object(module, "current_receipt_states", return_value={}),
                mock.patch.object(
                    module,
                    "current_release_truth_root_context",
                    return_value={
                        "root_blocker_ids": [],
                        "root_blockers": [],
                        "root_blockers_generated_at": "",
                        "stable_promotion_command": "",
                        "post_promotion_verify_command": "",
                        "root_release_truth_source": "",
                    },
                ),
                mock.patch.object(module, "release_ready_next_actions", return_value=[]),
                mock.patch.object(
                    module,
                    "run_authoritative_release_controller",
                    return_value=live_controller_result(module),
                ),
            ):
                result = module.main()

            self.assertEqual(0, result)
            payload = json.loads(output_path.read_text(encoding="utf-8"))
        self.assertEqual("fail", payload["status"])
        self.assertEqual("NOT_RELEASE_READY", payload["verdict"])
        self.assertEqual(0, payload["returncode"])
        self.assertTrue(payload["saw_release_ready_marker"])
        self.assertTrue(
            any(
                item.startswith(
                    "FAIL release_channel: workspace portal release channel artifact "
                    f"{module.display_path(drift_path)} disagrees with authoritative registry receipt"
                )
                for item in payload["failures"]
            )
        )
        self.assertEqual(["release_channel"], payload["failed_gates"])

    def test_main_fails_closed_when_successful_exit_prints_not_release_ready_marker(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="release-ready-negative-marker-") as temp_dir:
            output_path = Path(temp_dir) / "RELEASE_READY.generated.json"

            process = mock.Mock(pid=1234, returncode=0)

            with (
                mock.patch.object(module, "OUTPUT_PATH", output_path),
                mock.patch.object(module, "refresh_watcher_state", return_value={}),
                mock.patch.object(module, "current_blocking_gate_artifacts", return_value={}),
                mock.patch.object(module, "current_receipt_states", return_value={}),
                mock.patch.object(
                    module,
                    "current_release_truth_root_context",
                    return_value={
                        "root_blocker_ids": [],
                        "root_blockers": [],
                        "root_blockers_generated_at": "",
                        "stable_promotion_command": "",
                        "post_promotion_verify_command": "",
                        "root_release_truth_source": "",
                    },
                ),
                mock.patch.object(module, "release_ready_next_actions", return_value=[]),
                mock.patch.object(
                    module,
                    "run_authoritative_release_controller",
                    return_value=live_controller_result(
                        module,
                        stdout="NOT_RELEASE_READY\n",
                    ),
                ),
            ):
                result = module.main()

            self.assertEqual(0, result)
            payload = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual("fail", payload["status"])
            self.assertEqual("NOT_RELEASE_READY", payload["verdict"])
            self.assertEqual(0, payload["returncode"])
            self.assertFalse(payload["saw_release_ready_marker"])
            self.assertEqual(["NOT_RELEASE_READY"], payload["not_release_ready_markers"])
            self.assertIn("verify_release_ready printed NOT_RELEASE_READY marker", payload["failures"])
            self.assertIn("verify_release_ready did not print RELEASE_READY marker", payload["failures"])
            self.assertEqual(["verify_release_ready"], payload["failed_gates"])

    def test_main_fails_closed_when_successful_exit_prints_no_ready_marker(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="release-ready-missing-marker-") as temp_dir:
            output_path = Path(temp_dir) / "RELEASE_READY.generated.json"

            process = mock.Mock(pid=1234, returncode=0)

            with (
                mock.patch.object(module, "OUTPUT_PATH", output_path),
                mock.patch.object(module, "refresh_watcher_state", return_value={}),
                mock.patch.object(module, "current_blocking_gate_artifacts", return_value={}),
                mock.patch.object(module, "current_receipt_states", return_value={}),
                mock.patch.object(
                    module,
                    "current_release_truth_root_context",
                    return_value={
                        "root_blocker_ids": [],
                        "root_blockers": [],
                        "root_blockers_generated_at": "",
                        "stable_promotion_command": "",
                        "post_promotion_verify_command": "",
                        "root_release_truth_source": "",
                    },
                ),
                mock.patch.object(module, "release_ready_next_actions", return_value=[]),
                mock.patch.object(
                    module,
                    "run_authoritative_release_controller",
                    return_value=live_controller_result(
                        module,
                        stdout="all gates clear\n",
                    ),
                ),
            ):
                result = module.main()

            self.assertEqual(0, result)
            payload = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual("fail", payload["status"])
            self.assertEqual("NOT_RELEASE_READY", payload["verdict"])
            self.assertEqual(0, payload["returncode"])
            self.assertFalse(payload["saw_release_ready_marker"])
            self.assertEqual([], payload["not_release_ready_markers"])
            self.assertEqual(["verify_release_ready did not print RELEASE_READY marker"], payload["failures"])
            self.assertEqual(["verify_release_ready"], payload["failed_gates"])

    def test_main_publishes_current_fail_receipt_when_controller_environment_is_rejected(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="release-ready-environment-rejected-") as temp_dir:
            output_path = Path(temp_dir) / "RELEASE_READY.generated.json"
            output_path.write_text(
                json.dumps({"status": "pass", "verdict": "RELEASE_READY"}),
                encoding="utf-8",
            )
            with (
                mock.patch.object(module, "OUTPUT_PATH", output_path),
                mock.patch.object(
                    module,
                    "authoritative_controller_environment",
                    side_effect=ValueError(
                        "release controller rejects inherited or user-writable PATH"
                    ),
                ),
            ):
                result = module.main(["--skip-windows-runtime-refresh"])

            payload = json.loads(output_path.read_text(encoding="utf-8"))
            remaining_names = sorted(path.name for path in output_path.parent.iterdir())

        self.assertEqual(78, result)
        self.assertEqual("chummer.release_ready", payload["contract_name"])
        self.assertEqual("fail", payload["status"])
        self.assertEqual("NOT_RELEASE_READY", payload["verdict"])
        self.assertEqual(78, payload["returncode"])
        self.assertEqual(
            module.supported_release_controller_command(
                skip_windows_runtime_refresh=True,
            ),
            payload["command"],
        )
        self.assertNotIn("bash", payload["command"])
        self.assertFalse(payload["authoritative"])
        self.assertTrue(payload["diagnostic"])
        self.assertFalse(payload["test_only"])
        self.assertEqual(
            ["release_ready_receipt_materializer"],
            payload["failed_gates"],
        )
        self.assertEqual(
            "controller_environment",
            payload["materialization_error"]["phase"],
        )
        self.assertEqual(
            "verify_existing_receipts",
            payload["proof_refresh_policy"]["windows_installer"],
        )
        self.assertEqual(["RELEASE_READY.generated.json"], remaining_names)

    def test_main_durably_removes_prior_pass_before_abrupt_controller_termination(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="release-ready-prior-pass-controller-crash-") as temp_dir:
            output_path = Path(temp_dir) / "RELEASE_READY.generated.json"
            output_path.write_text(
                json.dumps({"status": "pass", "verdict": "RELEASE_READY"}),
                encoding="utf-8",
            )
            with (
                mock.patch.object(module, "OUTPUT_PATH", output_path),
                mock.patch.object(
                    module,
                    "run_authoritative_release_controller",
                    side_effect=SystemExit(137),
                ),
            ):
                with self.assertRaises(SystemExit) as raised:
                    module.main()
                staging_path = module.projection_staging_path()

            self.assertEqual(137, raised.exception.code)
            self.assertFalse(output_path.exists())
            self.assertFalse(staging_path.exists())

    def test_projection_crash_leaves_only_nonce_bound_non_authoritative_staging(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="release-ready-projection-crash-") as temp_dir:
            output_path = Path(temp_dir) / "RELEASE_READY.generated.json"
            output_path.write_text(
                json.dumps({"status": "pass", "verdict": "RELEASE_READY"}),
                encoding="utf-8",
            )
            payload = {
                "contract_name": "chummer.release_ready",
                "status": "pass",
                "verdict": "RELEASE_READY",
                "release_verifier_binding": {
                    "release_channel_sha256": "c" * 64,
                    "release_version": "run-crash-regression",
                },
            }
            execution_plan = {
                "run_nonce": "d" * 64,
                "plan_sha256": "e" * 64,
            }
            with (
                mock.patch.object(module, "OUTPUT_PATH", output_path),
                mock.patch.object(
                    module,
                    "refresh_release_truth_projection",
                    side_effect=SystemExit(137),
                ),
            ):
                staging_path = module.projection_staging_path()
                with self.assertRaises(SystemExit) as raised:
                    module.converge_release_truth_projection(
                        payload,
                        {},
                        module._test_release_execution_environment,
                        execution_plan=execution_plan,
                    )

            self.assertEqual(137, raised.exception.code)
            self.assertFalse(output_path.exists())
            staged = json.loads(staging_path.read_text(encoding="utf-8"))
            self.assertEqual("in_progress", staged["status"])
            self.assertEqual("NOT_RELEASE_READY", staged["verdict"])
            self.assertFalse(staged["authoritative"])
            self.assertEqual(module.DIAGNOSTIC_AUTHORITY_SCOPE, staged["authority_scope"])
            self.assertEqual("d" * 64, staged["projection_staging"]["run_nonce"])
            self.assertEqual("e" * 64, staged["projection_staging"]["execution_plan_sha256"])
            self.assertEqual("c" * 64, staged["projection_staging"]["release_channel_sha256"])
            self.assertEqual(
                "run-crash-regression",
                staged["projection_staging"]["release_version"],
            )

    def test_projection_step_requires_entrypoint_in_plan_governed_repository(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="release-projection-membership-") as temp_dir:
            root = Path(temp_dir)
            bound_repository = root / "bound"
            unbound_repository = root / "unbound"
            for repository in (bound_repository, unbound_repository):
                repository.mkdir()
                (repository / ".git").mkdir()
            bound_script = bound_repository / "projection.py"
            unbound_script = unbound_repository / "projection.py"
            bound_script.write_text("print('bound')\n", encoding="utf-8")
            unbound_script.write_text("print('unbound')\n", encoding="utf-8")
            execution_plan = {
                "run_nonce": "1" * 64,
                "plan_sha256": "2" * 64,
                "external_write_authorized": False,
                "governed_code_snapshot": {
                    "repositories": [
                        {"root": {"path": str(bound_repository)}}
                    ]
                },
            }
            environment = {
                "PATH": module.TRUSTED_PATH,
                "PYTHONDONTWRITEBYTECODE": "1",
                "PYTHONNOUSERSITE": "1",
                "CHUMMER_RELEASE_READY_GATE_KILL_AFTER_SECONDS": "1",
            }

            with self.assertRaisesRegex(ValueError, "repository is not plan-governed"):
                module.projection_step_prebinding(
                    "unbound_projection",
                    module.isolated_python_argv(unbound_script),
                    unbound_repository,
                    environment,
                    execution_plan,
                )
            binding = module.projection_step_prebinding(
                "bound_projection",
                module.isolated_python_argv(bound_script),
                bound_repository,
                environment,
                execution_plan,
            )

        self.assertEqual("1" * 64, binding["run_nonce"])
        self.assertEqual("2" * 64, binding["execution_plan_sha256"])
        self.assertFalse(binding["external_write"])
        self.assertEqual(
            str(module.projection_staging_path()),
            binding["outputs"]["non_authoritative_staging_receipt"],
        )

    def test_refresh_release_truth_projection_disables_recursive_materializers(self) -> None:
        module = load_module()
        completed = {
            "returncode": 0,
            "timed_out": False,
            "stdout": "projection ok\n",
            "stderr": "",
            "process_containment": {
                "mode": module.PROCESS_CONTAINMENT_MODE,
                "authoritative": True,
            },
            "containment_violation": False,
        }

        with mock.patch.object(
            module,
            "run_controller_gate_command",
            return_value=completed,
        ) as run_mock:
            result = module.refresh_release_truth_projection(
                {
                    module.RELEASE_READY_MATERIALIZER_ACTIVE_ENV: "1",
                    module.SKIP_GOOGLE_OAUTH_RUNTIME_REFRESH_ENV: "1",
                    module.SKIP_WINDOWS_RUNTIME_REFRESH_ENV: "1",
                }
            )

        self.assertEqual("pass", result["status"])
        self.assertEqual(0, result["returncode"])
        self.assertIn(str(module.TRUSTED_PYTHON), run_mock.call_args.args[0]["command"])
        run_env = run_mock.call_args.args[1]
        self.assertEqual("1", run_env["CHUMMER_SKIP_RELEASE_WRAPPER_REFRESH"])
        self.assertEqual("1", run_env["CHUMMER_SKIP_CODEX_HANDOFF_MATERIALIZER"])
        self.assertEqual("1", run_env[module.RELEASE_READY_MATERIALIZER_ACTIVE_ENV])
        self.assertEqual("1", run_env[module.SKIP_GOOGLE_OAUTH_RUNTIME_REFRESH_ENV])
        self.assertEqual("1", run_env[module.SKIP_WINDOWS_RUNTIME_REFRESH_ENV])
        self.assertEqual("30", run_env["CHUMMER_RELEASE_READY_GATE_KILL_AFTER_SECONDS"])
        self.assertFalse(set(run_env) & set(module.RELEASE_PROVIDER_ENV_KEYS))

    def test_projection_retry_stays_disabled_without_detached_controller_attestation(self) -> None:
        module = load_module()
        gate_names = list(module.REQUIRED_RELEASE_VERIFIER_GATES)
        evidence = passing_verifier_evidence(module)
        release_verifier_binding = evidence["final_binding"]
        proof_refresh_policy = {
            "google_oauth": "verify_existing_receipts",
            "windows_installer": "verify_existing_receipts",
        }
        payload = {
            "contract_name": "chummer.release_ready",
            "generated_at_utc": module.now_iso(),
            "status": "fail",
            "verdict": "NOT_RELEASE_READY",
            "returncode": 0,
            "timed_out": False,
            "saw_release_ready_marker": True,
            "not_release_ready_markers": [],
            "global_verifier_skipped_due_current_blockers": False,
            "authority_scope": module.AUTHORITATIVE_CONTROLLER_SCOPE,
            "authoritative": True,
            "diagnostic": False,
            "test_only": False,
            "external_release_writes_authorized": False,
            "started_gates": gate_names,
            "completed_gates": gate_names,
            "last_completed_gate": gate_names[-1],
            "failures": ["FAIL release_truth_projection_refresh: phase=final"],
            "failed_gates": ["release_truth_projection_refresh"],
            "release_truth_projection_refresh": {"status": "fail", "phases": []},
            "proof_refresh_policy": proof_refresh_policy,
            "release_verifier_binding": release_verifier_binding,
            "release_execution_plan": evidence["plan"],
            "release_verifier_start_generated_at_utc": evidence["start_binding"][
                "generated_at_utc"
            ],
            "release_verifier_gate_receipt_bindings": evidence["receipt_bindings"],
            "release_verifier_gate_execution_bindings": evidence[
                "execution_bindings"
            ],
            "nextActions": ["Review optional Windows proof handoff."],
        }

        with tempfile.TemporaryDirectory(prefix="release-ready-projection-retry-") as temp_dir:
            output_path = Path(temp_dir) / "RELEASE_READY.generated.json"
            output_path.write_text(json.dumps(payload), encoding="utf-8")

            def fake_convergence(retry_payload, _release_channel, _env):  # noqa: ANN001
                projection = {"status": "pass", "phases": []}
                retry_payload["release_truth_projection_refresh"] = projection
                return projection

            with (
                mock.patch.object(module, "OUTPUT_PATH", output_path),
                mock.patch.object(module, "DEFAULT_OUTPUT_PATH", output_path),
                mock.patch.object(module, "load_json", return_value={}),
                mock.patch.object(
                    module,
                    "converge_release_truth_projection",
                    side_effect=fake_convergence,
                ) as convergence_mock,
                mock.patch.object(module.subprocess, "Popen") as popen_mock,
            ):
                result = module.main(
                    [
                        "--retry-release-truth-projection",
                        "--skip-google-oauth-runtime-refresh",
                        "--skip-windows-runtime-refresh",
                    ]
                )

            self.assertEqual(1, result)
            popen_mock.assert_not_called()
            convergence_mock.assert_not_called()
            retried = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual(payload, retried)
            self.assertIn(
                "projection retry is offline replay and remains disabled until protected "
                "detached controller execution-attestation trust is enrolled",
                module.projection_retry_validation_failures(
                    payload,
                    proof_refresh_policy,
                ),
            )

    def test_projection_retry_rejects_nonprojection_failure(self) -> None:
        module = load_module()
        gate_names = [f"verify_gate_{index}" for index in range(38)]
        payload = {
            "contract_name": "chummer.release_ready",
            "generated_at_utc": module.now_iso(),
            "status": "fail",
            "verdict": "NOT_RELEASE_READY",
            "returncode": 0,
            "timed_out": False,
            "saw_release_ready_marker": True,
            "not_release_ready_markers": [],
            "global_verifier_skipped_due_current_blockers": False,
            "started_gates": gate_names,
            "completed_gates": gate_names,
            "last_completed_gate": gate_names[-1],
            "failures": ["FAIL verify_guide_convergence"],
            "failed_gates": ["verify_guide_convergence"],
            "release_truth_projection_refresh": {"status": "fail"},
            "proof_refresh_policy": {
                "google_oauth": "verify_existing_receipts",
                "windows_installer": "verify_existing_receipts",
            },
        }

        failures = module.projection_retry_validation_failures(
            payload,
            payload["proof_refresh_policy"],
        )

        self.assertIn("receipt contains a failure outside release-truth projection", failures)
        self.assertIn("failed_gates is not projection-only", failures)

    def test_final_projection_convergence_uses_receipt_only_safe_commands(self) -> None:
        module = load_module()
        calls: list[tuple[str, list[str], Path, bool]] = []

        def fake_step(  # noqa: ANN001
            name,
            command,
            cwd,
            env,
            *,
            allow_failure=False,
            execution_plan=None,
        ):
            self.assertIsNone(execution_plan)
            calls.append((name, command, cwd, allow_failure))
            assert env[module.SKIP_GOOGLE_OAUTH_RUNTIME_REFRESH_ENV] == "1"
            assert env[module.SKIP_WINDOWS_RUNTIME_REFRESH_ENV] == "1"
            assert env["CHUMMER_SKIP_RELEASE_WRAPPER_REFRESH"] == "1"
            return {"name": name, "status": "pass", "returncode": 0}

        with mock.patch.object(module, "run_release_truth_projection_step", side_effect=fake_step):
            result = module.converge_release_truth_dependents(
                {
                    module.SKIP_GOOGLE_OAUTH_RUNTIME_REFRESH_ENV: "1",
                    module.SKIP_WINDOWS_RUNTIME_REFRESH_ENV: "1",
                },
                final_pass=True,
            )

        self.assertEqual("pass", result["status"])
        self.assertEqual(
            [
                "mobile_cross_surface_readiness",
                "mobile_release_boundary",
                "mobile_local_release_proof",
                "operator_release_dashboard",
                "final_gold_janitor",
                "flagship_product_readiness",
                "release_truth_projection",
            ],
            [name for name, *_rest in calls],
        )
        flattened = "\n".join(" ".join(command) for _name, command, _cwd, _allow in calls)
        self.assertTrue(
            all(command[0] == str(module.TRUSTED_PYTHON) for _name, command, _cwd, _allow in calls)
        )
        self.assertTrue(
            all(
                tuple(command[: len(module.TRUSTED_PYTHON_ISOLATED_PREFIX)])
                == module.TRUSTED_PYTHON_ISOLATED_PREFIX
                for _name, command, _cwd, _allow in calls
            )
        )
        self.assertIn("--skip-windows-runtime-refresh", flattened)
        self.assertIn("--skip-materializers", flattened)
        self.assertNotIn("google_oauth", flattened)
        self.assertNotIn("send_telegram", flattened)

    def test_main_replaces_provisional_self_blocker_after_passing_verifier(self) -> None:
        module = load_module()
        stale_root = {
            "root_blocker_ids": ["release_truth:release_ready"],
            "root_blockers": [{"id": "release_truth:release_ready"}],
            "root_blockers_generated_at": "2026-07-10T08:00:00Z",
            "stable_promotion_command": "",
            "post_promotion_verify_command": "",
            "root_release_truth_source": "/tmp/RELEASE_BLOCKERS.generated.json",
        }
        clean_root = {
            "root_blocker_ids": [],
            "root_blockers": [],
            "root_blockers_generated_at": "2026-07-10T08:01:00Z",
            "stable_promotion_command": "",
            "post_promotion_verify_command": "",
            "root_release_truth_source": "/tmp/RELEASE_BLOCKERS.generated.json",
        }
        stale_artifacts = {"release_truth_root": stale_root}
        clean_artifacts = {"release_truth_root": clean_root}

        with tempfile.TemporaryDirectory(prefix="release-ready-projection-") as temp_dir:
            output_path = Path(temp_dir) / "RELEASE_READY.generated.json"
            process = mock.Mock(pid=1234, returncode=0)
            process.wait.return_value = 0

            with (
                mock.patch.object(module, "OUTPUT_PATH", output_path),
                mock.patch.object(module, "should_refresh_release_truth_projection", return_value=True),
                mock.patch.object(
                    module,
                    "refresh_release_truth_projection",
                    return_value={"status": "pass", "returncode": 0},
                ),
                mock.patch.object(
                    module,
                    "converge_release_truth_dependents",
                    side_effect=[
                        {"status": "pass", "phase": "wrapper_cycle", "steps": []},
                        {"status": "pass", "phase": "final", "steps": []},
                    ],
                ),
                mock.patch.object(
                    module,
                    "current_blocking_gate_artifacts",
                    side_effect=[stale_artifacts, clean_artifacts, clean_artifacts, clean_artifacts],
                ),
                mock.patch.object(
                    module,
                    "current_release_truth_root_context",
                    side_effect=[stale_root, clean_root, clean_root, clean_root],
                ),
                mock.patch.object(
                    module,
                    "current_receipt_states",
                    side_effect=[
                        {"phase": "provisional"},
                        {"phase": "root"},
                        {"phase": "wrapper_cycle"},
                        {"phase": "converged"},
                    ],
                ),
                mock.patch.object(module, "release_ready_next_actions", return_value=[]),
                mock.patch.object(module, "load_json", return_value={}),
                mock.patch.object(
                    module,
                    "run_authoritative_release_controller",
                    return_value=live_controller_result(module),
                ),
            ):
                result = module.main()

            self.assertEqual(0, result)
            payload = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual("pass", payload["status"])
            self.assertEqual("RELEASE_READY", payload["verdict"])
            self.assertEqual([], payload["root_blocker_ids"])
            self.assertEqual(clean_artifacts, payload["blocking_gate_artifacts"])
            self.assertEqual({"phase": "converged"}, payload["current_receipt_states"])
            self.assertEqual("pass", payload["release_truth_projection_refresh"]["status"])
            self.assertEqual(3, len(payload["release_truth_projection_refresh"]["phases"]))

    def test_current_projection_blocker_forces_not_release_ready(self) -> None:
        module = load_module()
        root_context = {
            "root_blocker_ids": ["release_truth:current_gate"],
            "root_blockers": [{"id": "release_truth:current_gate"}],
            "root_blockers_generated_at": "2026-07-16T12:00:00Z",
            "stable_promotion_command": "",
            "post_promotion_verify_command": "",
            "root_release_truth_source": "/tmp/RELEASE_BLOCKERS.generated.json",
        }
        payload: dict[str, object] = {
            "status": "pass",
            "verdict": "RELEASE_READY",
            "failures": [],
            "failed_gates": [],
        }
        with (
            mock.patch.object(
                module,
                "current_blocking_gate_artifacts",
                return_value={"release_truth_root": root_context},
            ),
            mock.patch.object(
                module,
                "current_release_truth_root_context",
                return_value=root_context,
            ),
            mock.patch.object(module, "current_receipt_states", return_value={}),
            mock.patch.object(module, "release_ready_next_actions", return_value=[]),
        ):
            consistency_failures = module.apply_current_release_truth_projection(
                payload,
                {},
            )

        self.assertEqual("fail", payload["status"])
        self.assertEqual("NOT_RELEASE_READY", payload["verdict"])
        self.assertEqual(["release_truth:current_gate"], payload["root_blocker_ids"])
        self.assertTrue(consistency_failures)
        self.assertIn("current_release_truth", "\n".join(payload["failures"]))
        self.assertTrue(payload["nextActions"])
        self.assertIn("release_truth:current_gate", payload["nextActions"][0])
        self.assertEqual([], payload["advisoryActions"])

    def test_extract_failed_gates_preserves_order_and_removes_duplicates(self) -> None:
        module = load_module()

        failed_gates = module.extract_failed_gates(
            [
                "FAIL verify_public_release_snapshot_truth",
                "verify_public_release_snapshot_truth",
                "FAIL crawl_public_release_surfaces",
                "verify_release_ready timed out after 900s",
            ]
        )

        self.assertEqual(
            [
                "verify_public_release_snapshot_truth",
                "crawl_public_release_surfaces",
                "verify_release_ready",
            ],
            failed_gates,
        )


if __name__ == "__main__":
    unittest.main()

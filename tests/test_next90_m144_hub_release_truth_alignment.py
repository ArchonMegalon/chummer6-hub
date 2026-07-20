from __future__ import annotations

import copy
import importlib.util
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "verify_next90_m144_hub_release_truth_alignment.py"
STATIC_SOURCE_FILES = [
    "Chummer.Run.Api/Services/PublicReleaseManifestService.cs",
    "Chummer.Run.Api/Services/SignedInTrustStatusService.cs",
    "tests/RunServicesSmoke/Program.cs",
    "scripts/ai/verify.sh",
    ".codex-studio/published/HUB_LOCAL_RELEASE_PROOF.generated.json",
    "Chummer.Run.Api/wwwroot/proofs/mac-codex-release/HUB_LOCAL_RELEASE_PROOF.generated.json",
    "Chummer.Portal/downloads/RELEASE_CHANNEL.generated.json",
    "Chummer.Portal/downloads/startup-smoke/startup-smoke-avalonia-linux-x64.receipt.json",
    "Chummer.Portal/downloads/startup-smoke/startup-smoke-avalonia-win-x64.receipt.json",
]


def load_verifier_module():
    spec = importlib.util.spec_from_file_location("m144_hub_release_truth_verifier", SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load M144 Hub release-truth verifier")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def source_files() -> list[str]:
    files = list(STATIC_SOURCE_FILES)
    startup_smoke_root = REPO_ROOT / "Chummer.Portal/downloads/startup-smoke"
    for receipt_path in sorted(startup_smoke_root.glob("startup-smoke-*.receipt.json")):
        files.append(str(receipt_path.relative_to(REPO_ROOT)))
    return files


def public_trust_fixture(
    *,
    declared_status: str = "stale",
    desktop_ready: bool = False,
) -> tuple[dict, list[dict], dict[str, dict]]:
    generated_at = "2026-07-20T00:00:00Z"
    route_truth = [
        {
            "tupleId": "avalonia:linux:linux-x64",
            "artifactId": "linux-installer",
            "routeRole": "primary",
            "promotionState": "promoted",
            "revokeState": "not_revoked",
        },
        {
            "tupleId": "avalonia:windows:win-x64",
            "artifactId": "windows-installer",
            "routeRole": "primary",
            "promotionState": "promoted",
            "revokeState": "not_revoked",
        },
        {
            "tupleId": "avalonia:macos:osx-arm64",
            "artifactId": "",
            "routeRole": "primary",
            "promotionState": "proof_required",
            "revokeState": "not_revoked",
        },
        {
            "tupleId": "blazor-desktop:macos:osx-arm64",
            "artifactId": "",
            "routeRole": "fallback",
            "promotionState": "proof_required",
            "parityPosture": "explicit_fallback",
            "revokeState": "not_revoked",
        },
    ]
    recommended_count = 2 if desktop_ready else 0
    blocked_count = 1 if desktop_ready else 3
    readiness_status = "pass" if desktop_ready else "fail"
    payload = {
        "generatedAt": generated_at,
        "releaseProof": {
            "generatedAt": generated_at,
            "uiLocalizationReleaseGate": {"generatedAt": generated_at},
            "flagshipReadiness": {
                "generatedAt": generated_at,
                "status": readiness_status,
                "desktopClientReady": desktop_ready,
            },
        },
        "publicTrustMetrics": {
            "releaseChannel": {
                "recommendedRouteCount": recommended_count,
                "fallbackRecoveryRouteCount": 0,
                "blockedRouteCount": blocked_count,
                "revokedRouteCount": 0,
                "summary": (
                    f"Channel preview is blocked with {recommended_count} recommended primary routes, "
                    f"0 promoted fallback recovery routes, {blocked_count} blocked routes, and 0 active revocations."
                ),
            },
            "adoptionHealth": {
                "primaryPromotedCount": recommended_count,
                "fallbackRecoveryCount": 0,
                "blockedRouteCount": blocked_count,
                "revokedRouteCount": 0,
                "publicInstallCount": recommended_count,
                "accountLinkedInstallCount": 0,
                "summary": (
                    f"{recommended_count} primary routes are promoted; {recommended_count} are guest-readable, "
                    f"0 require account-linked install handoff, 0 fallback recovery routes are promoted, "
                    f"and {blocked_count} routes are still blocked on proof."
                ),
            },
            "proofFreshness": {
                "status": declared_status,
                "releaseProofGeneratedAt": generated_at,
                "releaseProofAgeSeconds": 0,
                "releaseProofMaxAgeSeconds": 604800,
                "uiLocalizationGeneratedAt": generated_at,
                "uiLocalizationAgeSeconds": 0,
                "uiLocalizationMaxAgeSeconds": 604800,
                "flagshipReadinessGeneratedAt": generated_at,
                "flagshipReadinessAgeSeconds": 0,
                "flagshipReadinessMaxAgeSeconds": 604800,
                "flagshipReadinessStatus": readiness_status,
                "flagshipDesktopClientReady": desktop_ready,
            },
            "revocationFacts": {
                "activeRevocationCount": 0,
                "activeRevocations": [],
            },
        },
    }
    artifacts = {
        "linux-installer": {"installAccessClass": "open_public"},
        "windows-installer": {"installAccessClass": "open_public"},
    }
    return payload, route_truth, artifacts


class Next90M144HubReleaseTruthAlignmentTests(unittest.TestCase):
    def test_public_trust_metrics_demote_promoted_routes_when_proof_is_stale(self) -> None:
        verifier = load_verifier_module()
        payload, route_truth, artifacts = public_trust_fixture()
        errors: list[str] = []

        verifier.verify_public_trust_metrics(payload, route_truth, artifacts, errors)

        self.assertEqual([], errors)

    def test_public_trust_metrics_reject_missing_freshness_status(self) -> None:
        verifier = load_verifier_module()
        payload, route_truth, artifacts = public_trust_fixture()
        payload["publicTrustMetrics"]["proofFreshness"].pop("status")
        errors: list[str] = []

        verifier.verify_public_trust_metrics(payload, route_truth, artifacts, errors)

        self.assertIn("publicTrustMetrics.proofFreshness.status is missing", errors)

    def test_public_trust_metrics_reject_invalid_freshness_status(self) -> None:
        verifier = load_verifier_module()
        payload, route_truth, artifacts = public_trust_fixture(declared_status="unknown")
        errors: list[str] = []

        verifier.verify_public_trust_metrics(payload, route_truth, artifacts, errors)

        self.assertIn("publicTrustMetrics.proofFreshness.status is not canonical", errors)

    def test_public_trust_metrics_reject_stale_status_with_fresh_zero_age_evidence(self) -> None:
        verifier = load_verifier_module()
        payload, route_truth, artifacts = public_trust_fixture(
            declared_status="stale",
            desktop_ready=True,
        )
        errors: list[str] = []

        verifier.verify_public_trust_metrics(payload, route_truth, artifacts, errors)

        self.assertIn(
            "publicTrustMetrics.proofFreshness.status is inconsistent with canonical "
            "timestamps, age budgets, and flagship readiness: expected 'fresh', got 'stale'",
            errors,
        )

    def test_public_trust_metrics_reject_future_evidence_with_zero_age_and_fresh_status(self) -> None:
        verifier = load_verifier_module()
        payload, route_truth, artifacts = public_trust_fixture(
            declared_status="fresh",
            desktop_ready=True,
        )
        future_generated_at = "2026-07-20T00:00:00.001Z"
        payload["releaseProof"]["generatedAt"] = future_generated_at
        payload["publicTrustMetrics"]["proofFreshness"][
            "releaseProofGeneratedAt"
        ] = future_generated_at
        errors: list[str] = []

        verifier.verify_public_trust_metrics(payload, route_truth, artifacts, errors)

        self.assertIn(
            "releaseProof.generatedAt must not be later than release channel generatedAt",
            errors,
        )

    def test_public_trust_metrics_reject_duplicate_tuple_before_aggregation(self) -> None:
        verifier = load_verifier_module()
        payload, route_truth, artifacts = public_trust_fixture()
        route_truth.append(copy.deepcopy(route_truth[0]))
        errors: list[str] = []

        verifier.verify_public_trust_metrics(payload, route_truth, artifacts, errors)

        self.assertIn(
            "desktopTupleCoverage.desktopRouteTruth contains duplicate tupleId "
            "'avalonia:linux:linux-x64' at indexes 0 and 4",
            errors,
        )

    def test_verifier_accepts_repo_local_release_truth_alignment(self) -> None:
        result = subprocess.run(
            ["python3", str(SCRIPT)],
            cwd=REPO_ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        self.assertEqual(result.returncode, 0, msg=result.stderr or result.stdout)
        self.assertIn("next90 m144 hub release truth alignment proof passed", result.stdout)

    def test_verify_script_runs_m144_guard(self) -> None:
        verify_script = (REPO_ROOT / "scripts" / "ai" / "verify.sh").read_text(encoding="utf-8")
        self.assertIn("python3 scripts/verify_next90_m144_hub_release_truth_alignment.py", verify_script)
        self.assertIn("python3 -m unittest tests/test_next90_m144_hub_release_truth_alignment.py", verify_script)

    def test_release_proof_install_routes_match_published_artifact_rows(self) -> None:
        audit_script = (REPO_ROOT / "scripts" / "audit-ui-parity.sh").read_text(encoding="utf-8")
        self.assertIn("proofRoutes includes install routes without published artifacts", audit_script)

        release_catalog_paths = [Path("Chummer.Portal/downloads/RELEASE_CHANNEL.generated.json")]
        materialized_releases_path = Path("Chummer.Portal/downloads/releases.json")
        if (REPO_ROOT / materialized_releases_path).is_file():
            release_catalog_paths.insert(0, materialized_releases_path)

        for relative_path in release_catalog_paths:
            payload = json.loads((REPO_ROOT / relative_path).read_text(encoding="utf-8"))
            artifact_ids = {
                str(item.get("artifactId") or item.get("id") or "").strip()
                for collection_name in ("downloads", "artifacts")
                for item in payload.get(collection_name, [])
                if isinstance(item, dict)
            }
            artifact_ids.discard("")
            proof_routes = (payload.get("releaseProof") or {}).get("proofRoutes") or []
            install_route_ids = {
                str(route).removeprefix("/downloads/install/").split("/", 1)[0]
                for route in proof_routes
                if str(route).startswith("/downloads/install/")
            }

            self.assertTrue(install_route_ids, msg=str(relative_path))
            self.assertTrue(
                install_route_ids.issubset(artifact_ids),
                msg=f"{relative_path} has install proof routes without artifact rows: {sorted(install_route_ids - artifact_ids)}",
            )

    def test_verifier_fails_when_identity_registry_route_drifts(self) -> None:
        with tempfile.TemporaryDirectory(prefix="next90-m144-route-drift-") as temp_dir:
            temp_root = Path(temp_dir)
            self.copy_sources(temp_root)
            release_channel_path = temp_root / "Chummer.Portal/downloads/RELEASE_CHANNEL.generated.json"
            payload = json.loads(release_channel_path.read_text(encoding="utf-8"))
            tuple_id = payload["artifactIdentityRegistry"][0]["tupleId"]
            payload["artifactIdentityRegistry"][0]["publicInstallRoute"] = "/downloads/install/drifted-route"
            release_channel_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

            result = self.run_verifier(temp_root)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn(f"artifactIdentityRegistry tuple {tuple_id} drifted", result.stderr)

    def test_verifier_fails_when_install_recovery_refs_drop_tuple_marker(self) -> None:
        with tempfile.TemporaryDirectory(prefix="next90-m144-proof-ref-") as temp_dir:
            temp_root = Path(temp_dir)
            self.copy_sources(temp_root)
            release_channel_path = temp_root / "Chummer.Portal/downloads/RELEASE_CHANNEL.generated.json"
            payload = json.loads(release_channel_path.read_text(encoding="utf-8"))
            tuple_id = payload["installAwareArtifactRegistry"][0]["tupleId"]
            payload["installAwareArtifactRegistry"][0]["recoveryProofRefs"] = [
                "/downloads/install/avalonia-win-x64-installer"
            ]
            release_channel_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

            result = self.run_verifier(temp_root)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn(f"recoveryProofRefs missing desktopTupleCoverage.desktopRouteTruth[{tuple_id}]", result.stderr)

    def test_verifier_fails_when_release_proof_route_drops_promoted_install_path(self) -> None:
        with tempfile.TemporaryDirectory(prefix="next90-m144-proof-route-") as temp_dir:
            temp_root = Path(temp_dir)
            self.copy_sources(temp_root)
            proof_path = temp_root / ".codex-studio/published/HUB_LOCAL_RELEASE_PROOF.generated.json"
            payload = json.loads(proof_path.read_text(encoding="utf-8"))
            payload["proof_routes"] = [
                route
                for route in payload["proof_routes"]
                if route != "/downloads/install/avalonia-win-x64-installer"
            ]
            proof_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

            result = self.run_verifier(temp_root)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("proof_routes missing required route /downloads/install/avalonia-win-x64-installer", result.stderr)

    def test_verifier_fails_when_stale_startup_smoke_is_not_reflected_in_release_truth(self) -> None:
        with tempfile.TemporaryDirectory(prefix="next90-m144-startup-smoke-") as temp_dir:
            temp_root = Path(temp_dir)
            self.copy_sources(temp_root)
            release_channel_path = temp_root / "Chummer.Portal/downloads/RELEASE_CHANNEL.generated.json"
            payload = json.loads(release_channel_path.read_text(encoding="utf-8"))
            tuple_truth = payload["desktopTupleCoverage"]["desktopRouteTruth"][0]
            tuple_id = tuple_truth["tupleId"]
            payload["supportabilityState"] = "published"
            payload["rolloutState"] = "published"
            payload["message"] = "Shelf is fully live."
            release_channel_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            startup_smoke_path = temp_root / (
                "Chummer.Portal/downloads/startup-smoke/"
                f"startup-smoke-{tuple_truth['head']}-{tuple_truth['rid']}.receipt.json"
            )
            startup_smoke_payload = json.loads(startup_smoke_path.read_text(encoding="utf-8"))
            startup_smoke_payload["artifactSha256"] = "deadbeef" * 8
            startup_smoke_path.write_text(json.dumps(startup_smoke_payload, indent=2), encoding="utf-8")

            result = self.run_verifier(temp_root)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn(tuple_id, result.stderr)
        self.assertIn("must stay review_required", result.stderr)
        self.assertIn("must stay coverage_incomplete", result.stderr)

    def test_verifier_fails_when_public_trust_summary_drifted_from_route_truth(self) -> None:
        with tempfile.TemporaryDirectory(prefix="next90-m144-public-trust-") as temp_dir:
            temp_root = Path(temp_dir)
            self.copy_sources(temp_root)
            release_channel_path = temp_root / "Chummer.Portal/downloads/RELEASE_CHANNEL.generated.json"
            payload = json.loads(release_channel_path.read_text(encoding="utf-8"))
            payload["publicTrustMetrics"]["releaseChannel"]["summary"] = (
                "Channel preview is preview with 2 recommended primary routes, 1 promoted fallback recovery routes, 0 blocked routes, and 0 active revocations."
            )
            release_channel_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

            result = self.run_verifier(temp_root)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("publicTrustMetrics.releaseChannel summary is missing '0 promoted fallback recovery routes'", result.stderr)

    def copy_sources(self, temp_root: Path) -> None:
        for relative_path in source_files():
            source = REPO_ROOT / relative_path
            target = temp_root / relative_path
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)

    def run_verifier(self, temp_root: Path) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env["CHUMMER_NEXT90_M144_ROOT"] = str(temp_root)
        env["CHUMMER_NEXT90_M144_LOCAL_RELEASE_PROOF"] = str(
            temp_root / ".codex-studio/published/HUB_LOCAL_RELEASE_PROOF.generated.json"
        )
        env["CHUMMER_NEXT90_M144_SERVED_RELEASE_PROOF"] = str(
            temp_root / "Chummer.Run.Api/wwwroot/proofs/mac-codex-release/HUB_LOCAL_RELEASE_PROOF.generated.json"
        )
        env["CHUMMER_NEXT90_M144_RELEASE_CHANNEL"] = str(
            temp_root / "Chummer.Portal/downloads/RELEASE_CHANNEL.generated.json"
        )
        env["CHUMMER_NEXT90_M144_STARTUP_SMOKE_ROOT"] = str(
            temp_root / "Chummer.Portal/downloads/startup-smoke"
        )
        return subprocess.run(
            ["python3", str(SCRIPT)],
            cwd=temp_root,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

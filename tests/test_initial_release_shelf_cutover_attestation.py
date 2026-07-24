from __future__ import annotations

import base64
import importlib.util
import json
import hashlib
import os
from pathlib import Path
import shutil
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "attest_initial_release_shelf_cutover.py"


def load_module():
    spec = importlib.util.spec_from_file_location(
        "attest_initial_release_shelf_cutover", SCRIPT
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def write_json(path: Path, payload: object, *, indent: int | None = 2) -> bytes:
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(payload, indent=indent).encode("utf-8") + b"\n"
    path.write_bytes(raw)
    return raw


def write_legacy_shelf(root: Path) -> dict[str, bytes]:
    root.mkdir()
    payloads = {
        "files/chummer-win.exe": b"signed-windows-installer\n",
        "files/chummer-win.payload.zip": b"signed-windows-payload\n",
        "files/chummer-win.payload.zip.json": b'{"downloadUrl":"/downloads/files/chummer-win.payload.zip"}\n',
        "proof/windows/proof.json": b'{"status":"pass"}\n',
        "release-evidence/public-promotion.json": b'{"status":"pass"}\n',
    }
    for relative_path, contents in payloads.items():
        path = root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(contents)
    identity = {
        "version": "nightly-20260722",
        "channel": "preview",
        "publishedAt": "2026-07-22T01:00:00Z",
    }
    downloads = [
        {
            "artifactId": "chummer-win-x64",
            "fileName": "chummer-win.exe",
            "payloadFileName": "chummer-win.payload.zip",
        }
    ]
    write_json(root / "releases.json", {**identity, "downloads": downloads})
    write_json(
        root / "RELEASE_CHANNEL.generated.json",
        {
            "version": identity["version"],
            "channelId": identity["channel"],
            "publishedAt": identity["publishedAt"],
            "artifacts": downloads,
        },
    )
    return payloads


def write_live_publication_scope(module, shelf: Path) -> bytes:
    return write_json(
        shelf / module.PUBLICATION_SCOPE_NAME,
        {
            "deployDir": str(shelf),
            "deployMode": False,
            "externalArtifactPublishVerified": False,
            "generatedAt": "2026-07-12T18:47:54.101249Z",
            "liveVerifyTarget": "",
            "promotedArtifactCount": 4,
            "releaseChannel": "preview",
            # The live compatibility receipt can lag the current manifest.
            "releaseVersion": "run-20260712-174412",
            "requireExternalPublish": False,
            "schema": module.PUBLICATION_SCOPE_SCHEMA,
            "scope": "local_downloads_shelf_only",
            "status": "passed",
            "summary": (
                "A local downloads shelf was updated and verified. "
                "This is not an external desktop artifact upload."
            ),
        },
    )


def prepare_requested(module, tmp_path: Path):
    shelf = tmp_path / "downloads"
    state = tmp_path / "deploy-receipts" / "initial-release-shelf-cutover"
    state.parent.mkdir(mode=0o700)
    payloads = write_legacy_shelf(shelf)
    prestate = module.prepare(shelf, state, "a" * 40)
    start = module.request_start(shelf, state)
    return shelf, state, payloads, prestate, start


def public_download_migration_inputs(module, tmp_path: Path):
    shelf = tmp_path / "downloads"
    write_legacy_shelf(shelf)
    stale_payloads = {
        "files/stale-win.payload.zip": b"stale-unreferenced-payload\n",
        "files/stale-win.payload.zip.json": b'{"status":"stale"}\n',
    }
    for relative, raw in stale_payloads.items():
        path = shelf / relative
        path.write_bytes(raw)
    source_head = "d" * 40
    candidate = tmp_path / "sealed-incumbent-candidate"
    restoration_spec = tmp_path / "manifest-closure-restorations.json"
    restoration_spec_raw = write_json(restoration_spec, [])
    restoration_spec_sha256 = sha256(restoration_spec_raw)
    candidate_receipt = tmp_path / "candidate-materialization.json"
    module.materialize_public_download_migration_candidate(
        shelf,
        candidate,
        source_head,
        restoration_spec,
        restoration_spec_sha256,
        candidate_receipt,
    )
    authority_path = tmp_path / "migration-authority.json"
    authority_materialization = (
        module.materialize_public_download_migration_authority(
            shelf,
            candidate,
            source_head,
            restoration_spec,
            restoration_spec_sha256,
            candidate_receipt,
            sha256(candidate_receipt.read_bytes()),
            authority_path,
        )
    )
    authority_raw = authority_path.read_bytes()
    receipts = tmp_path / "deploy-receipts"
    receipts.mkdir(mode=0o700)
    receipts.chmod(0o700)
    state = receipts / "initial-public-download-migration"
    return {
        "shelf": shelf,
        "candidate": candidate,
        "state": state,
        "source_head": source_head,
        "authority": authority_path,
        "authority_sha256": sha256(authority_raw),
        "candidate_receipt": candidate_receipt,
        "candidate_receipt_sha256": sha256(candidate_receipt.read_bytes()),
        "authority_materialization": authority_materialization,
        "generation_id": "generation-public-download-initial",
        "activation_receipt_id": "activation-public-download-initial",
        "stale_payloads": stale_payloads,
    }


def materialize_committed_cutover(module, shelf: Path, payloads: dict[str, bytes]):
    generation_id = "generation-initial-20260722"
    receipt_id = "activation-initial-20260722"
    generation = shelf / "generations" / generation_id
    generation_payloads = dict(payloads)
    generation_payloads["files/chummer-win.payload.zip.json"] = (
        b'{"downloadUrl":"/downloads/g/generation-initial-20260722/'
        b'install/chummer-win-x64/payload"}\n'
    )
    for relative_path, contents in generation_payloads.items():
        path = generation / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(contents)
    canonical = {
        "generationId": generation_id,
        "version": "nightly-20260722",
        "channelId": "preview",
        "publishedAt": "2026-07-22T01:00:00Z",
        "artifacts": [],
    }
    compatibility = {
        "generationId": generation_id,
        "version": "nightly-20260722",
        "channel": "preview",
        "publishedAt": "2026-07-22T01:00:00Z",
        "downloads": [],
    }
    canonical_raw = write_json(generation / "RELEASE_CHANNEL.generated.json", canonical)
    compatibility_raw = write_json(generation / "releases.json", compatibility)
    inventory = [
        {"path": relative_path, "sha256": sha256(contents)}
        for relative_path, contents in sorted(generation_payloads.items())
    ]
    inventory_digest = sha256(module.canonical_json_bytes(inventory))
    manifests = {
        "canonical": {
            "path": f"/downloads/g/{generation_id}/RELEASE_CHANNEL.generated.json",
            "sha256": sha256(canonical_raw),
        },
        "compatibility": {
            "path": f"/downloads/g/{generation_id}/releases.json",
            "sha256": sha256(compatibility_raw),
        },
    }
    candidate = {
        "schemaVersion": module.CANDIDATE_SCHEMA,
        "generationId": generation_id,
        "releaseVersion": "nightly-20260722",
        "channel": "preview",
        "publishedAt": "2026-07-22T01:00:00Z",
        "manifests": manifests,
        "inventoryDigest": f"sha256:{inventory_digest}",
        "inventory": inventory,
    }
    write_json(generation / "activation-candidate.json", candidate)
    pointer = {
        "schemaVersion": module.POINTER_SCHEMA,
        "generationId": generation_id,
        "releaseVersion": "nightly-20260722",
        "channel": "preview",
        "publishedAt": "2026-07-22T01:00:00Z",
        "manifests": manifests,
        "inventoryDigest": f"sha256:{inventory_digest}",
        "activatedAt": "2026-07-22T01:01:00Z",
        "activationReceiptId": receipt_id,
    }
    pointer_raw = write_json(shelf / "current.json", pointer)
    (shelf / ".release-shelf-layout-v1").write_bytes(module.MARKER_BYTES)
    promotion_lock = shelf / module.LOCK_NAME
    promotion_lock.write_bytes(b"")
    promotion_lock.chmod(0o600)
    write_json(
        shelf / ".release-shelf-writer-policy.json",
        {
            "schemaVersion": module.WRITER_POLICY_SCHEMA,
            "mode": module.WRITER_POLICY_MODE,
        },
    )
    target = base64.b64encode(pointer_raw).decode("ascii")
    identity = {
        "operation": "promotion",
        "previousGenerationId": None,
        "previousPointerSha256": None,
        "generationId": generation_id,
        "activationReceiptId": receipt_id,
        "releaseVersion": "nightly-20260722",
        "channel": "preview",
        "publishedAt": "2026-07-22T01:00:00Z",
        "inventoryDigest": f"sha256:{inventory_digest}",
        "pointerSha256": f"sha256:{sha256(pointer_raw)}",
        "preparedAtUtc": "2026-07-22T01:00:30Z",
        "previousPointerBase64": None,
        "targetPointerBase64": target,
        "exactIncomingDesktopScope": None,
    }
    journal = {
        "schemaVersion": module.INTENT_SCHEMA,
        "state": "prepared",
        "intent": identity,
        "previousPointerBase64": None,
        "targetPointerBase64": target,
    }
    receipt_root = shelf / ".release-shelf-activation-journal" / receipt_id
    intent_raw = write_json(receipt_root / "intent.json", journal)
    write_json(
        receipt_root / "outcome.json",
        {
            "schemaVersion": module.OUTCOME_SCHEMA,
            "state": "committed",
            "activationReceiptId": receipt_id,
            "intentSha256": f"sha256:{sha256(intent_raw[:-1])}",
            "resolvedAtUtc": "2026-07-22T01:01:00Z",
        },
    )
    return generation_id, receipt_id


def materialize_aborted_recovery(module, shelf: Path) -> tuple[str, Path]:
    generation_id = "generation-aborted-20260722"
    receipt_id = "activation-aborted-20260722"
    target_pointer = {
        "schemaVersion": module.POINTER_SCHEMA,
        "generationId": generation_id,
        "releaseVersion": "nightly-20260722",
        "channel": "preview",
        "publishedAt": "2026-07-22T01:00:00Z",
        "manifests": {
            "canonical": {
                "path": f"/downloads/g/{generation_id}/{module.CANONICAL_MANIFEST}",
                "sha256": "1" * 64,
            },
            "compatibility": {
                "path": f"/downloads/g/{generation_id}/{module.COMPATIBILITY_MANIFEST}",
                "sha256": "2" * 64,
            },
        },
        "inventoryDigest": "sha256:" + "3" * 64,
        "activatedAt": "2026-07-22T01:01:00Z",
        "activationReceiptId": receipt_id,
    }
    target_raw = json.dumps(target_pointer, indent=2).encode("utf-8") + b"\n"
    target = base64.b64encode(target_raw).decode("ascii")
    intent = {
        "schemaVersion": module.INTENT_SCHEMA,
        "state": "prepared",
        "intent": {
            "operation": "promotion",
            "previousGenerationId": None,
            "previousPointerSha256": None,
            "generationId": generation_id,
            "activationReceiptId": receipt_id,
            "releaseVersion": "nightly-20260722",
            "channel": "preview",
            "publishedAt": "2026-07-22T01:00:00Z",
            "inventoryDigest": "sha256:" + "3" * 64,
            "pointerSha256": f"sha256:{sha256(target_raw)}",
            "preparedAtUtc": "2026-07-22T01:00:30Z",
            "previousPointerBase64": None,
            "targetPointerBase64": target,
            "exactIncomingDesktopScope": None,
        },
        "previousPointerBase64": None,
        "targetPointerBase64": target,
    }
    receipt_root = shelf / module.JOURNAL_NAME / receipt_id
    intent_raw = write_json(receipt_root / "intent.json", intent)
    write_json(
        receipt_root / "outcome.json",
        {
            "schemaVersion": module.OUTCOME_SCHEMA,
            "state": "aborted",
            "activationReceiptId": receipt_id,
            "intentSha256": f"sha256:{sha256(intent_raw[:-1])}",
            "resolvedAtUtc": "2026-07-22T01:01:00Z",
        },
    )
    write_json(
        shelf / module.POLICY_NAME,
        {
            "schemaVersion": module.WRITER_POLICY_SCHEMA,
            "mode": module.WRITER_POLICY_MODE,
        },
    )
    lock = shelf / module.LOCK_NAME
    lock.write_bytes(b"")
    lock.chmod(0o600)
    return receipt_id, receipt_root


def materialize_later_generation(module, shelf: Path) -> tuple[str, str]:
    previous_raw = (shelf / module.POINTER_NAME).read_bytes()
    previous = json.loads(previous_raw)
    generation_id = "generation-later-20260723"
    receipt_id = "activation-later-20260723"
    generation = shelf / module.GENERATIONS_NAME / generation_id
    generation.mkdir()
    pointer = {
        **previous,
        "generationId": generation_id,
        "publishedAt": "2026-07-23T01:00:00Z",
        "activatedAt": "2026-07-23T01:01:00Z",
        "activationReceiptId": receipt_id,
        "manifests": {
            "canonical": {
                **previous["manifests"]["canonical"],
                "path": f"/downloads/g/{generation_id}/{module.CANONICAL_MANIFEST}",
            },
            "compatibility": {
                **previous["manifests"]["compatibility"],
                "path": f"/downloads/g/{generation_id}/{module.COMPATIBILITY_MANIFEST}",
            },
        },
    }
    pointer_raw = write_json(shelf / module.POINTER_NAME, pointer)
    previous_base64 = base64.b64encode(previous_raw).decode("ascii")
    target_base64 = base64.b64encode(pointer_raw).decode("ascii")
    intent = {
        "schemaVersion": module.INTENT_SCHEMA,
        "state": "prepared",
        "intent": {
            "operation": "promotion",
            "previousGenerationId": previous["generationId"],
            "previousPointerSha256": f"sha256:{sha256(previous_raw)}",
            "generationId": generation_id,
            "activationReceiptId": receipt_id,
            "releaseVersion": pointer["releaseVersion"],
            "channel": pointer["channel"],
            "publishedAt": pointer["publishedAt"],
            "inventoryDigest": pointer["inventoryDigest"],
            "pointerSha256": f"sha256:{sha256(pointer_raw)}",
            "preparedAtUtc": "2026-07-23T01:00:30Z",
            "previousPointerBase64": previous_base64,
            "targetPointerBase64": target_base64,
            "exactIncomingDesktopScope": None,
        },
        "previousPointerBase64": previous_base64,
        "targetPointerBase64": target_base64,
    }
    receipt_root = shelf / module.JOURNAL_NAME / receipt_id
    intent_raw = write_json(receipt_root / "intent.json", intent)
    write_json(
        receipt_root / "outcome.json",
        {
            "schemaVersion": module.OUTCOME_SCHEMA,
            "state": "committed",
            "activationReceiptId": receipt_id,
            "intentSha256": f"sha256:{sha256(intent_raw[:-1])}",
            "resolvedAtUtc": "2026-07-23T01:01:00Z",
        },
    )
    return generation_id, receipt_id


def materialize_valid_rollback(module, shelf: Path) -> tuple[str, str, Path]:
    previous_raw = (shelf / module.POINTER_NAME).read_bytes()
    previous = json.loads(previous_raw)
    initial_receipt = (
        shelf
        / module.JOURNAL_NAME
        / "activation-initial-20260722"
        / "intent.json"
    )
    initial_intent = json.loads(initial_receipt.read_text(encoding="utf-8"))
    initial_pointer = json.loads(
        base64.b64decode(initial_intent["targetPointerBase64"], validate=True)
    )
    generation_id = initial_pointer["generationId"]
    receipt_id = "activation-rollback-20260724"
    pointer = {
        **initial_pointer,
        "activatedAt": "2026-07-24T01:01:00Z",
        "activationReceiptId": receipt_id,
    }
    pointer_raw = write_json(shelf / module.POINTER_NAME, pointer)
    previous_base64 = base64.b64encode(previous_raw).decode("ascii")
    target_base64 = base64.b64encode(pointer_raw).decode("ascii")
    intent = {
        "schemaVersion": module.INTENT_SCHEMA,
        "state": "prepared",
        "intent": {
            "operation": "rollback",
            "previousGenerationId": previous["generationId"],
            "previousPointerSha256": f"sha256:{sha256(previous_raw)}",
            "generationId": generation_id,
            "activationReceiptId": receipt_id,
            "releaseVersion": pointer["releaseVersion"],
            "channel": pointer["channel"],
            "publishedAt": pointer["publishedAt"],
            "inventoryDigest": pointer["inventoryDigest"],
            "pointerSha256": f"sha256:{sha256(pointer_raw)}",
            "preparedAtUtc": "2026-07-24T01:00:30Z",
            "previousPointerBase64": previous_base64,
            "targetPointerBase64": target_base64,
            "exactIncomingDesktopScope": None,
        },
        "previousPointerBase64": previous_base64,
        "targetPointerBase64": target_base64,
    }
    receipt_root = shelf / module.JOURNAL_NAME / receipt_id
    intent_raw = write_json(receipt_root / "intent.json", intent)
    write_json(
        receipt_root / "outcome.json",
        {
            "schemaVersion": module.OUTCOME_SCHEMA,
            "state": "committed",
            "activationReceiptId": receipt_id,
            "intentSha256": f"sha256:{sha256(intent_raw[:-1])}",
            "resolvedAtUtc": "2026-07-24T01:01:00Z",
        },
    )
    return generation_id, receipt_id, receipt_root


def valid_compose_attestation(module, tmp_path: Path) -> dict[str, object]:
    source_root = str(tmp_path / "source")
    build_context = str(tmp_path / "workspace")
    overlay_root = str(tmp_path / "overlay" / "app")
    contexts = {
        "run-services-source": source_root,
        "fleet-media-factory-contracts": str(tmp_path / "fleet-contracts"),
        "design-product": str(tmp_path / "design-product"),
    }

    def build(target: str) -> dict[str, object]:
        return {
            "context": build_context,
            "dockerfile": f"{source_root}/Chummer.Run.Api/Dockerfile",
            "additionalContexts": contexts,
            "target": target,
            "runtimeIdentityConsistent": True,
        }

    return {
        "contractName": module.COMPOSE_CONTRACT,
        "status": "pass",
        "operation": "deploy",
        "projectName": "chummer6-hub",
        "portalImage": "chummer-run-api:local",
        "toolImage": "chummer-install-linking-postgres-tool:local",
        "sourceRoot": source_root,
        "buildContext": build_context,
        "overlayRoot": overlay_root,
        "overlayReadOnly": True,
        "publishedPort": 8091,
        "proxyGates": {
            "CHUMMER_PUBLIC_PLAY_PROXY_ENABLED": "false",
            "CHUMMER_PUBLIC_PLAY_LIVE_SESSION_PROXY_ENABLED": "false",
        },
        "retiredProxyKeysAbsent": True,
        "releaseShelfPosture": {
            "CHUMMER_RELEASE_SHELF_LAYOUT_V1_REQUIRED": "true",
            "CHUMMER_RELEASE_SHELF_INITIAL_MIGRATION_ALLOWED": "false",
        },
        "runtimePolicyChecks": [
            "closed-service-fields",
            "identity",
            "security",
            "resource-limits",
            "command-entrypoint",
            "mounts",
            "ports-health",
            "dependency-network",
            "profiles-tmpfs-restart",
            "critical-environment",
            "release-shelf-operation-posture",
        ],
        "mountCounts": {
            "chummer-portal-volume-init": 5,
            "chummer-portal": 13,
            "chummer-install-linking-postgres-admin": 1,
            "chummer-install-linking-postgres-import": 4,
        },
        "builds": {
            "chummer-portal": build(""),
            "chummer-install-linking-postgres-admin": build(
                "install-linking-postgres-tool-final"
            ),
            "chummer-install-linking-postgres-import": build(
                "install-linking-postgres-tool-final"
            ),
        },
    }


def valid_postdeploy_attestation(module) -> dict[str, object]:
    full_digest = "7" * 64
    children: dict[str, object] = {}
    for name, contract in {
        "preflight": "chummer.public_edge_deploy_preflight.v1",
        "downloads": "chummer.downloads_version_marker.v1",
        "pwaStatic": "chummer.public_pwa_static_assets.v1",
        "mobileLedger": "chummer.mobile_pwa_ledger_boundary.v1",
        "readyMobileHandoff": "chummer.ready_mobile_handoff_contract.v1",
        "participateIframeShell": "chummer.participate_iframe_shell.v1",
    }.items():
        children[name] = {
            "contractName": contract,
            "status": "pass",
            "failures": [],
        }
    children["downloadsStatusBrowser"] = {
        "status": "pass",
        "exitCode": 0,
        "artifact": {
            "contractName": "chummer.downloads_status_e2e.v1",
            "status": "pass",
        },
    }
    children["mobilePwaViewport"] = {
        "status": "pass",
        "exitCode": 0,
        "artifact": {
            "contractName": "chummer.mobile_pwa_viewport_smoke.v1",
            "status": "pass",
        },
    }
    children["frontdoorNavigation"] = {
        "status": "pass",
        "exitCode": 0,
        "mobileArtifact": {
            "contractName": "chummer.frontdoor_mobile_install_boundary.v2",
            "status": "pass",
        },
        "ledgerArtifact": {
            "contractName": "chummer.black_ledger_globe_frontdoor.v1",
            "status": "pass",
        },
        "anchorArtifact": {
            "contractName": "chummer.frontdoor_mobile_anchor_redirect.v2",
            "status": "pass",
        },
        "mobileArtifactPrivacyContractSatisfied": True,
        "ledgerArtifactCurrentContractSatisfied": True,
        "anchorArtifactCurrentContractSatisfied": True,
        "proofClosureStatus": "pass",
        "proofClosureSha256": "9" * 64,
    }
    children["onlineLaunch"] = {
        "contractName": "chummer.online_character_roster_launch.v1",
        "status": "pass",
        "failures": [],
    }
    return {
        "contractName": module.POSTDEPLOY_CONTRACT,
        "status": "pass",
        "generatedAtUtc": "2026-07-22T01:02:00Z",
        "failures": [],
        "skipPreflight": False,
        "skipReleaseVersionMatch": False,
        "strictPreflight": True,
        "strictInvocation": True,
        "strictNoAllowanceInvocation": True,
        "projectionPurpose": "code-deploy",
        "projectionStatus": "review_required",
        "projectionStage": "code_deploy_review_required",
        "codeDeploymentAuthority": True,
        "releaseUploadAuthority": False,
        "releaseReady": False,
        "codeDeployReviewRequiredAuthoritySatisfied": True,
        "expectedFullDeploymentDigestSha256": full_digest,
        "expectedPwaAssetInventorySha256": "8" * 64,
        "pwaAssetInventoryAnchorMatches": True,
        "expectedPwaFullDeploymentDigestSha256": full_digest,
        "pwaFullDeploymentDigestSha256": full_digest,
        "pwaFullDeploymentDigestMatchesExpected": True,
        "downloadsStatusBrowserStatus": "pass",
        "downloadsStatusBrowserExitCode": 0,
        "downloadsStatusBrowserArtifactContract": "chummer.downloads_status_e2e.v1",
        "mobilePwaViewportStatus": "pass",
        "mobilePwaViewportExitCode": 0,
        "mobilePwaViewportArtifactContract": "chummer.mobile_pwa_viewport_smoke.v1",
        "mobilePwaViewportArtifactCurrentContractSatisfied": True,
        "mobilePwaViewportArtifactContractFailures": [],
        "frontdoorNavigationStatus": "pass",
        "frontdoorNavigationExitCode": 0,
        "frontdoorNavigationMobileArtifactContract": (
            "chummer.frontdoor_mobile_install_boundary.v2"
        ),
        "frontdoorNavigationLedgerArtifactContract": (
            "chummer.black_ledger_globe_frontdoor.v1"
        ),
        "frontdoorNavigationAnchorArtifactContract": (
            "chummer.frontdoor_mobile_anchor_redirect.v2"
        ),
        "frontdoorNavigationMobileArtifactInstallContractSatisfied": True,
        "frontdoorNavigationLedgerArtifactCurrentContractSatisfied": True,
        "frontdoorNavigationAnchorArtifactCurrentContractSatisfied": True,
        "frontdoorNavigationProofClosureStatus": "pass",
        "frontdoorNavigationProofClosureSha256": "9" * 64,
        "onlineLaunchStatus": "pass",
        "onlineLaunchContract": "chummer.online_character_roster_launch.v1",
        "onlineLaunchHttpStatus": 200,
        "onlineLaunchHasBlazorMarker": True,
        "roleAliasRouteStatus": "pass",
        "roleAliasRouteContract": "chummer.public_role_alias_routes.v1",
        "childReceipts": children,
    }


def materialize_final_evidence(module, tmp_path: Path):
    producer = tmp_path / "producer"
    producer.mkdir()
    deploy = tmp_path / "deploy-receipts" / "deploy.ABC12345"
    deploy.mkdir(parents=True, mode=0o700)
    deploy.chmod(0o700)
    compose_source = producer / "compose.json"
    postdeploy_source = producer / "postdeploy.json"
    active_source = producer / "active.json"
    write_json(compose_source, valid_compose_attestation(module, tmp_path))
    write_json(postdeploy_source, valid_postdeploy_attestation(module))
    candidate = {
        "containerId": "a" * 64,
        "containerName": "chummer-public-edge-candidate-ABC12345",
        "imageId": "sha256:" + "b" * 64,
    }
    write_json(
        active_source,
        {
            "contractName": module.RUNTIME_AUTHORITY_CONTRACT,
            "status": "pass",
            "generatedAtUtc": "2026-07-22T01:03:00Z",
            "portal": {
                "existed": True,
                **candidate,
                "wasRunning": True,
                "proofAuthorityMountSha256": "c" * 64,
                "proofPublicMountSha256": "c" * 64,
            },
        },
    )
    compose = deploy / module.COMPOSE_EVIDENCE_NAME
    readiness = deploy / module.READINESS_EVIDENCE_NAME
    postdeploy = deploy / module.POSTDEPLOY_EVIDENCE_NAME
    active = deploy / module.RUNTIME_AUTHORITY_EVIDENCE_NAME
    module.snapshot_evidence("compose", compose_source, compose)
    module.record_readiness(
        readiness,
        candidate_container_id=candidate["containerId"],
        candidate_container_name=candidate["containerName"],
        candidate_image_id=candidate["imageId"],
        http_status=200,
        response_sha256="d" * 64,
        running="true",
        health="healthy",
    )
    module.snapshot_evidence("postdeploy", postdeploy_source, postdeploy)
    module.snapshot_evidence("active-runtime", active_source, active)
    return compose, readiness, postdeploy, active, candidate


def test_public_download_migration_activates_clean_generation_without_touching_stale_legacy_bytes(
    tmp_path: Path,
) -> None:
    module = load_module()
    fixture = public_download_migration_inputs(module, tmp_path)

    prestate = module.prepare_public_download_migration(
        fixture["shelf"],
        fixture["state"],
        fixture["candidate"],
        fixture["authority"],
        fixture["authority_sha256"],
        fixture["source_head"],
        fixture["generation_id"],
        fixture["activation_receipt_id"],
    )
    module.request_public_download_migration_start(
        fixture["shelf"],
        fixture["state"],
        fixture["candidate"],
    )
    generation_module = module._load_release_shelf_generation_module()
    generation_module.activate_filesystem(
        fixture["candidate"],
        fixture["shelf"],
        initialize_layout=True,
        generation_id=fixture["generation_id"],
        activated_at="2026-07-23T12:00:00Z",
        activation_receipt_id=fixture["activation_receipt_id"],
    )

    poststate = module.verify_public_download_migration(
        fixture["shelf"],
        fixture["state"],
        fixture["candidate"],
    )

    assert prestate["runtimeProfile"] == "public-download-only"
    assert poststate["classification"] == "committed"
    assert poststate["legacyTopLevelBytesUnchanged"] is True
    assert poststate["excludedLegacyFilesAbsentFromGeneration"] is True
    assert {
        row["path"] for row in poststate["excludedLegacyFiles"]
    } == set(fixture["stale_payloads"])
    for relative, raw in fixture["stale_payloads"].items():
        assert (fixture["shelf"] / relative).read_bytes() == raw
        assert not (
            fixture["shelf"]
            / "generations"
            / fixture["generation_id"]
            / relative
        ).exists()
    assert (
        fixture["shelf"] / "current.json"
    ).is_file()
    assert (
        fixture["shelf"] / ".release-shelf-layout-v1"
    ).read_bytes() == b"v1\n"


def test_public_download_candidate_classifies_live_compatibility_and_private_evidence(
    tmp_path: Path,
) -> None:
    module = load_module()
    shelf = tmp_path / "downloads"
    write_legacy_shelf(shelf)
    publication_scope_raw = write_live_publication_scope(module, shelf)
    excluded = {
        "README.md": b"operator-only shelf notes\n",
        "RELEASE_BUILD_HANDOFF.generated.json": b'{"handoff_only":true}\n',
        "RELEASE_BUILD_HANDOFF.generated.md": b"# Operator handoff\n",
        "UI_WINDOWS_DESKTOP_EXIT_GATE.generated.json": b'{"status":"failed"}\n',
        "WINDOWS_INSTALLER_VISUAL_PROOF.generated.json": b'{"status":"pass"}\n',
        "WINDOWS_INSTALLER_VISUAL_PROOF_HANDOFF.generated.json": (
            b'{"handoff_only":true}\n'
        ),
        "WINDOWS_INSTALLER_VISUAL_PROOF_HANDOFF.generated.md": (
            b"# Windows handoff\n"
        ),
        "external-proof-manifest.json": b'{"schema_version":1}\n',
        "RELEASE_CHANNEL.generated.json.root-backup-20260704T162721Z": (
            b'{"backup":true}\n'
        ),
        "releases.json.root-backup-20260704T162721Z": b'{"backup":true}\n',
        "signing/signing-avalonia-win-x64.receipt.json": b'{"status":"pass"}\n',
        "visual-audit/windows-installer/audit.json": b'{"status":"pass"}\n',
        "windows-installer-visual-proof/windows-installer-progress.png": (
            b"private screenshot bytes"
        ),
    }
    for relative, raw in excluded.items():
        path = shelf / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
    private = tmp_path / "private"
    private.mkdir(mode=0o700)
    private.chmod(0o700)
    candidate = private / "candidate"
    restoration_spec = private / "restorations.json"
    restoration_spec_raw = write_json(restoration_spec, [])
    receipt_path = private / "candidate-materialization.json"

    receipt = module.materialize_public_download_migration_candidate(
        shelf,
        candidate,
        "d" * 40,
        restoration_spec,
        sha256(restoration_spec_raw),
        receipt_path,
    )

    assert (candidate / module.PUBLICATION_SCOPE_NAME).read_bytes() == (
        publication_scope_raw
    )
    assert module.PUBLICATION_SCOPE_NAME in receipt["copiedPaths"]
    assert set(excluded) <= set(receipt["excludedPaths"])
    for relative in excluded:
        assert (shelf / relative).read_bytes() == excluded[relative]
        assert not (candidate / relative).exists()


@pytest.mark.parametrize(
    ("relative", "raw", "match"),
    [
        (
            "private-secrets.json",
            b'{"secret":"must-not-be-classified"}\n',
            "unclassified non-generational path",
        ),
        (
            "PUBLICATION_SCOPE.generated.json",
            b'{"schema":"forged"}\n',
            "publication scope metadata",
        ),
    ],
)
def test_public_download_candidate_rejects_unknown_or_malformed_top_level_metadata(
    tmp_path: Path,
    relative: str,
    raw: bytes,
    match: str,
) -> None:
    module = load_module()
    shelf = tmp_path / "downloads"
    write_legacy_shelf(shelf)
    if relative != module.PUBLICATION_SCOPE_NAME:
        write_live_publication_scope(module, shelf)
    (shelf / relative).write_bytes(raw)
    private = tmp_path / "private"
    private.mkdir(mode=0o700)
    private.chmod(0o700)
    restoration_spec = private / "restorations.json"
    restoration_spec_raw = write_json(restoration_spec, [])
    candidate = private / "candidate"

    with pytest.raises(module.CutoverAttestationError, match=match):
        module.materialize_public_download_migration_candidate(
            shelf,
            candidate,
            "e" * 40,
            restoration_spec,
            sha256(restoration_spec_raw),
            private / "candidate-materialization.json",
        )
    assert not candidate.exists()


def test_public_download_migration_rejects_authority_or_incumbent_candidate_drift(
    tmp_path: Path,
) -> None:
    module = load_module()
    fixture = public_download_migration_inputs(module, tmp_path)
    module.prepare_public_download_migration(
        fixture["shelf"],
        fixture["state"],
        fixture["candidate"],
        fixture["authority"],
        fixture["authority_sha256"],
        fixture["source_head"],
        fixture["generation_id"],
        fixture["activation_receipt_id"],
    )
    fixture["authority"].write_bytes(
        fixture["authority"].read_bytes() + b" "
    )
    with pytest.raises(
        module.CutoverAttestationError,
        match="independent SHA-256 pin",
    ):
        module.request_public_download_migration_start(
            fixture["shelf"],
            fixture["state"],
            fixture["candidate"],
        )

    second_root = tmp_path / "second"
    second_root.mkdir()
    second = public_download_migration_inputs(module, second_root)
    (second["candidate"] / "RELEASE_CHANNEL.generated.json").write_bytes(
        b'{"status":"arbitrary-local-candidate"}\n'
    )
    with pytest.raises(
        module.CutoverAttestationError,
        match="byte-identical",
    ):
        module.prepare_public_download_migration(
            second["shelf"],
            second["state"],
            second["candidate"],
            second["authority"],
            second["authority_sha256"],
            second["source_head"],
            second["generation_id"],
            second["activation_receipt_id"],
        )

    third_root = tmp_path / "third"
    third_root.mkdir()
    third = public_download_migration_inputs(module, third_root)
    third["candidate_receipt"].write_bytes(
        third["candidate_receipt"].read_bytes() + b" "
    )
    with pytest.raises(
        module.CutoverAttestationError,
        match="receipt changed from its SHA-256 pin",
    ):
        module.prepare_public_download_migration(
            third["shelf"],
            third["state"],
            third["candidate"],
            third["authority"],
            third["authority_sha256"],
            third["source_head"],
            third["generation_id"],
            third["activation_receipt_id"],
        )


def test_public_download_migration_repairs_only_exact_manifest_bound_missing_byte(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    module = load_module()
    shelf = tmp_path / "downloads"
    write_legacy_shelf(shelf)
    restored_bytes = b"exact governed incumbent closure repair\n"
    restored_sha256 = sha256(restored_bytes)
    restored_name = "chummer-linux-installer.deb"
    write_json(
        shelf / "aur-packages.json",
        {
            "packages": [
                {
                    "upstreamArtifactFileName": restored_name,
                    "upstreamArtifactSha256": restored_sha256,
                    "upstreamArtifactSizeBytes": len(restored_bytes),
                }
            ]
        },
    )
    source = tmp_path / "trusted-source" / restored_name
    source.parent.mkdir()
    source.write_bytes(restored_bytes)
    candidate = tmp_path / "candidate"
    restored_path = f"files/{restored_name}"
    restorations = [
        {
            "path": restored_path,
            "sha256": restored_sha256,
            "sizeBytes": len(restored_bytes),
            "sourcePath": str(source),
        }
    ]
    source_head = "e" * 40
    restoration_spec = tmp_path / "manifest-closure-restorations.json"
    restoration_spec_raw = write_json(restoration_spec, restorations)
    candidate_receipt = tmp_path / "candidate-materialization.json"
    candidate_command = [
        "materialize-public-download-only-candidate",
        "--shelf-root",
        str(shelf),
        "--candidate-root",
        str(candidate),
        "--source-head",
        source_head,
        "--manifest-closure-restoration-spec",
        str(restoration_spec),
        "--manifest-closure-restoration-spec-sha256",
        sha256(restoration_spec_raw),
        "--output",
        str(candidate_receipt),
    ]
    assert module.main(candidate_command) == 0
    candidate_materialization = json.loads(capsys.readouterr().out)
    candidate_receipt_raw = candidate_receipt.read_bytes()
    assert candidate_receipt_raw == (
        module.canonical_json_bytes(candidate_materialization) + b"\n"
    )
    assert candidate_materialization["candidateRoot"] == str(candidate)
    assert candidate_materialization[
        "manifestClosureRestorations"
    ] == restorations
    assert candidate_materialization[
        "candidateInventory"
    ]["digest"].startswith("sha256:")
    assert (candidate / restored_path).read_bytes() == restored_bytes
    candidate_identity = candidate.stat().st_dev, candidate.stat().st_ino
    candidate_inventory_before = module.inventory_tree(
        candidate,
        skip_top_level_controls=False,
    )

    assert module.main(candidate_command) == 0
    assert json.loads(capsys.readouterr().out) == candidate_materialization
    assert (
        candidate.stat().st_dev,
        candidate.stat().st_ino,
    ) == candidate_identity
    assert module.inventory_tree(
        candidate,
        skip_top_level_controls=False,
    ) == candidate_inventory_before

    authority = tmp_path / "migration-authority.json"
    assert module.main(
        [
            "materialize-public-download-only-authority",
            "--shelf-root",
            str(shelf),
            "--candidate-root",
            str(candidate),
            "--source-head",
            source_head,
            "--manifest-closure-restoration-spec",
            str(restoration_spec),
            "--manifest-closure-restoration-spec-sha256",
            sha256(restoration_spec_raw),
            "--candidate-materialization-receipt",
            str(candidate_receipt),
            "--candidate-materialization-receipt-sha256",
            sha256(candidate_receipt_raw),
            "--output",
            str(authority),
        ]
    ) == 0
    authority_materialization = json.loads(capsys.readouterr().out)
    authority_raw = authority.read_bytes()
    authority_payload = json.loads(authority_raw)
    assert authority_raw == module.canonical_json_bytes(authority_payload) + b"\n"
    assert authority_materialization["sha256"] == sha256(authority_raw)
    assert authority_materialization["manifestClosureRestorationCount"] == 1
    assert authority_payload["candidateMaterialization"] == {
        "receiptPath": str(candidate_receipt),
        "receiptSha256": sha256(candidate_receipt_raw),
        "manifestClosureRestorationSpecSha256": sha256(
            restoration_spec_raw
        ),
        "sourceHead": source_head,
    }
    assert module.main(
        [
            "materialize-public-download-only-authority",
            "--shelf-root",
            str(shelf),
            "--candidate-root",
            str(candidate),
            "--source-head",
            source_head,
            "--manifest-closure-restoration-spec",
            str(restoration_spec),
            "--manifest-closure-restoration-spec-sha256",
            sha256(restoration_spec_raw),
            "--candidate-materialization-receipt",
            str(candidate_receipt),
            "--candidate-materialization-receipt-sha256",
            sha256(candidate_receipt_raw),
            "--output",
            str(authority),
        ]
    ) == 1
    assert "already exists" in capsys.readouterr().err
    state = tmp_path / "receipts" / "migration"
    state.parent.mkdir(mode=0o700)
    state.parent.chmod(0o700)

    prestate = module.prepare_public_download_migration(
        shelf,
        state,
        candidate,
        authority,
        authority_materialization["sha256"],
        source_head,
        "generation-closure-repair",
        "activation-closure-repair",
    )
    module.request_public_download_migration_start(shelf, state, candidate)
    generation_module = module._load_release_shelf_generation_module()
    generation_module.activate_filesystem(
        candidate,
        shelf,
        initialize_layout=True,
        generation_id="generation-closure-repair",
        activation_receipt_id="activation-closure-repair",
    )
    poststate = module.verify_public_download_migration(
        shelf,
        state,
        candidate,
    )

    assert not (shelf / restored_path).exists()
    assert (
        shelf
        / "generations"
        / "generation-closure-repair"
        / restored_path
    ).read_bytes() == restored_bytes
    assert prestate["candidateSnapshot"]["manifestClosureRestorations"] == restorations
    assert prestate["candidateSnapshot"]["governedIncumbentClosureRepair"] is True
    assert poststate["legacyTopLevelBytesUnchanged"] is True


def test_public_download_candidate_preflight_resumes_commit_boundary_crashes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_module()
    shelf = tmp_path / "downloads"
    write_legacy_shelf(shelf)
    private = tmp_path / "private"
    private.mkdir(mode=0o700)
    private.chmod(0o700)
    candidate = private / "candidate"
    restoration_spec = private / "restorations.json"
    restoration_spec_raw = write_json(restoration_spec, [])
    receipt = private / "candidate-materialization.json"
    arguments = (
        shelf,
        candidate,
        "c" * 40,
        restoration_spec,
        sha256(restoration_spec_raw),
        receipt,
    )
    original_rename = module._rename_directory_noreplace_at

    def crash_after_candidate_rename(*args, **kwargs) -> None:
        original_rename(*args, **kwargs)
        raise RuntimeError("simulated crash after candidate rename")

    monkeypatch.setattr(
        module,
        "_rename_directory_noreplace_at",
        crash_after_candidate_rename,
    )
    with pytest.raises(RuntimeError, match="after candidate rename"):
        module.materialize_public_download_migration_candidate(*arguments)
    assert candidate.is_dir()
    assert not receipt.exists()
    candidate_identity = candidate.stat().st_dev, candidate.stat().st_ino

    monkeypatch.setattr(
        module,
        "_rename_directory_noreplace_at",
        original_rename,
    )
    first_receipt = module.materialize_public_download_migration_candidate(
        *arguments
    )
    assert json.loads(receipt.read_bytes()) == first_receipt
    assert (
        candidate.stat().st_dev,
        candidate.stat().st_ino,
    ) == candidate_identity

    receipt.unlink()
    original_publish = module._write_and_publish_unnamed_at

    def crash_after_receipt_publish(*args, **kwargs) -> None:
        original_publish(*args, **kwargs)
        raise RuntimeError("simulated crash after receipt publication")

    monkeypatch.setattr(
        module,
        "_write_and_publish_unnamed_at",
        crash_after_receipt_publish,
    )
    with pytest.raises(RuntimeError, match="after receipt publication"):
        module.materialize_public_download_migration_candidate(*arguments)
    published_receipt_raw = receipt.read_bytes()

    monkeypatch.setattr(
        module,
        "_write_and_publish_unnamed_at",
        original_publish,
    )
    resumed_receipt = module.materialize_public_download_migration_candidate(
        *arguments
    )
    assert resumed_receipt == json.loads(published_receipt_raw)
    assert receipt.read_bytes() == published_receipt_raw
    assert (
        candidate.stat().st_dev,
        candidate.stat().st_ino,
    ) == candidate_identity


def test_public_download_preflight_outputs_cannot_mutate_frozen_inputs(
    tmp_path: Path,
) -> None:
    module = load_module()
    shelf = tmp_path / "downloads"
    write_legacy_shelf(shelf)
    private = tmp_path / "private"
    private.mkdir(mode=0o700)
    private.chmod(0o700)
    candidate = private / "candidate"
    restoration_spec = private / "restorations.json"
    restoration_spec_raw = write_json(restoration_spec, [])
    restoration_sha256 = sha256(restoration_spec_raw)
    shelf_inventory = module.inventory_tree(
        shelf,
        skip_top_level_controls=False,
    )

    with pytest.raises(
        module.CutoverAttestationError,
        match="outside the candidate and release shelf",
    ):
        module.materialize_public_download_migration_candidate(
            shelf,
            candidate,
            "d" * 40,
            restoration_spec,
            restoration_sha256,
            shelf / "candidate-materialization.json",
        )
    assert not candidate.exists()
    assert module.inventory_tree(
        shelf,
        skip_top_level_controls=False,
    ) == shelf_inventory

    candidate_receipt = private / "candidate-materialization.json"
    module.materialize_public_download_migration_candidate(
        shelf,
        candidate,
        "d" * 40,
        restoration_spec,
        restoration_sha256,
        candidate_receipt,
    )
    candidate_inventory = module.inventory_tree(
        candidate,
        skip_top_level_controls=False,
    )
    for forbidden_output in (
        shelf / "migration-authority.json",
        candidate / "migration-authority.json",
    ):
        with pytest.raises(
            module.CutoverAttestationError,
            match="outside the release shelf and frozen candidate",
        ):
            module.materialize_public_download_migration_authority(
                shelf,
                candidate,
                "d" * 40,
                restoration_spec,
                restoration_sha256,
                candidate_receipt,
                sha256(candidate_receipt.read_bytes()),
                forbidden_output,
            )
        assert not forbidden_output.exists()
    assert module.inventory_tree(
        shelf,
        skip_top_level_controls=False,
    ) == shelf_inventory
    assert module.inventory_tree(
        candidate,
        skip_top_level_controls=False,
    ) == candidate_inventory


def test_prepare_and_request_start_bind_complete_legacy_inventory(tmp_path: Path) -> None:
    module = load_module()
    shelf, state, payloads, prestate, start = prepare_requested(module, tmp_path)

    rows = prestate["shelfSnapshot"]["legacyInventory"]["files"]
    assert {row["path"] for row in rows} == {
        *payloads,
        "RELEASE_CHANNEL.generated.json",
        "releases.json",
    }
    assert prestate["shelfSnapshot"]["markerAbsent"] is True
    assert prestate["shelfSnapshot"]["currentPointerAbsent"] is True
    assert prestate["shelfSnapshot"]["generationRewrittenMetadataPaths"] == [
        "files/chummer-win.payload.zip.json"
    ]
    assert start["phase"] == "candidate_start_requested"
    assert (state / "candidate-start-requested.json").is_file()
    assert not (shelf / ".release-shelf-writer-policy.json").exists()


def test_legacy_capture_accepts_equivalent_live_utc_timestamp_spellings_without_rewriting_bytes(
    tmp_path: Path,
) -> None:
    module = load_module()
    shelf = tmp_path / "downloads"
    write_legacy_shelf(shelf)
    canonical_path = shelf / module.CANONICAL_MANIFEST
    compatibility_path = shelf / module.COMPATIBILITY_MANIFEST
    canonical = json.loads(canonical_path.read_text(encoding="utf-8"))
    compatibility = json.loads(compatibility_path.read_text(encoding="utf-8"))
    canonical.update(
        version="run-20260715-140426",
        publishedAt="2026-07-15T14:06:48Z",
    )
    compatibility.update(
        version="run-20260715-140426",
        publishedAt="2026-07-15T14:06:48+00:00",
    )
    canonical_raw = write_json(canonical_path, canonical)
    compatibility_raw = write_json(compatibility_path, compatibility)

    snapshot = module.capture_legacy_snapshot(
        shelf,
        allow_aborted_history=False,
    )

    assert snapshot["manifestIdentity"] == {
        "releaseVersion": "run-20260715-140426",
        "channel": "preview",
        "publishedAt": "2026-07-15T14:06:48Z",
    }
    inventory = {
        row["path"]: row for row in snapshot["legacyInventory"]["files"]
    }
    assert inventory[module.CANONICAL_MANIFEST]["sha256"] == sha256(canonical_raw)
    assert inventory[module.COMPATIBILITY_MANIFEST]["sha256"] == sha256(
        compatibility_raw
    )
    assert canonical_path.read_bytes() == canonical_raw
    assert compatibility_path.read_bytes() == compatibility_raw


@pytest.mark.parametrize(
    "published_at",
    [
        "2026-07-15T14:06:49+00:00",
        "2026-07-15T14:06:48.0000001+00:00",
        "2026-07-15T14:06:48",
        "2026-07-15T16:06:48+02:00",
        "2026-07-15T14:06:99Z",
        123,
        float("nan"),
        float("inf"),
    ],
    ids=[
        "different-instant",
        "different-100ns-instant",
        "naive",
        "non-utc-offset",
        "malformed",
        "wrong-type",
        "non-finite",
        "positive-infinity",
    ],
)
def test_legacy_capture_rejects_non_equivalent_or_noncanonical_manifest_timestamps(
    tmp_path: Path,
    published_at: object,
) -> None:
    module = load_module()
    shelf = tmp_path / "downloads"
    write_legacy_shelf(shelf)
    canonical_path = shelf / module.CANONICAL_MANIFEST
    compatibility_path = shelf / module.COMPATIBILITY_MANIFEST
    canonical = json.loads(canonical_path.read_text(encoding="utf-8"))
    compatibility = json.loads(compatibility_path.read_text(encoding="utf-8"))
    canonical["publishedAt"] = "2026-07-15T14:06:48Z"
    compatibility["publishedAt"] = published_at
    write_json(canonical_path, canonical)
    write_json(compatibility_path, compatibility)

    with pytest.raises(module.CutoverAttestationError):
        module.capture_legacy_snapshot(shelf, allow_aborted_history=False)


def test_legacy_capture_preserves_seventh_fractional_digit_semantics(
    tmp_path: Path,
) -> None:
    module = load_module()
    shelf = tmp_path / "downloads"
    write_legacy_shelf(shelf)
    canonical_path = shelf / module.CANONICAL_MANIFEST
    compatibility_path = shelf / module.COMPATIBILITY_MANIFEST
    canonical = json.loads(canonical_path.read_text(encoding="utf-8"))
    compatibility = json.loads(compatibility_path.read_text(encoding="utf-8"))
    canonical["publishedAt"] = "2026-07-15T14:06:48.1234567Z"
    compatibility["publishedAt"] = "2026-07-15T14:06:48.1234568+00:00"
    write_json(canonical_path, canonical)
    write_json(compatibility_path, compatibility)

    with pytest.raises(
        module.CutoverAttestationError,
        match="legacy release manifests expose different identities",
    ):
        module.capture_legacy_snapshot(shelf, allow_aborted_history=False)

    compatibility["publishedAt"] = "2026-07-15T14:06:48.1234567+00:00"
    write_json(compatibility_path, compatibility)
    snapshot = module.capture_legacy_snapshot(shelf, allow_aborted_history=False)
    assert snapshot["manifestIdentity"]["publishedAt"] == (
        "2026-07-15T14:06:48.1234567Z"
    )

    canonical["publishedAt"] = "2026-07-15T14:06:48.1Z"
    compatibility["publishedAt"] = "2026-07-15T14:06:48.1000000+00:00"
    write_json(canonical_path, canonical)
    write_json(compatibility_path, compatibility)
    snapshot = module.capture_legacy_snapshot(shelf, allow_aborted_history=False)
    assert snapshot["manifestIdentity"]["publishedAt"] == "2026-07-15T14:06:48.1Z"


@pytest.mark.parametrize(
    ("field", "value"),
    [("version", "run-other"), ("channel", "stable")],
)
def test_legacy_capture_still_rejects_other_manifest_identity_mismatches(
    tmp_path: Path,
    field: str,
    value: str,
) -> None:
    module = load_module()
    shelf = tmp_path / "downloads"
    write_legacy_shelf(shelf)
    compatibility_path = shelf / module.COMPATIBILITY_MANIFEST
    compatibility = json.loads(compatibility_path.read_text(encoding="utf-8"))
    compatibility["publishedAt"] = "2026-07-22T01:00:00+00:00"
    compatibility[field] = value
    write_json(compatibility_path, compatibility)

    with pytest.raises(
        module.CutoverAttestationError,
        match="legacy release manifests expose different identities",
    ):
        module.capture_legacy_snapshot(shelf, allow_aborted_history=False)


def test_prepare_recovers_only_exact_empty_state_directory(tmp_path: Path) -> None:
    module = load_module()
    shelf = tmp_path / "downloads"
    write_legacy_shelf(shelf)
    state = tmp_path / "receipts" / "initial-release-shelf-cutover"
    state.mkdir(parents=True, mode=0o700)
    state.chmod(0o700)
    assert (
        module.inspect_deploy_state(shelf, state, "a" * 40)["classification"]
        == "absent"
    )
    assert module.prepare(shelf, state, "a" * 40)["status"] == "pass"

    orphan_state = tmp_path / "other-receipts" / "initial-release-shelf-cutover"
    orphan_state.mkdir(parents=True, mode=0o700)
    orphan_state.parent.chmod(0o700)
    orphan = orphan_state / ".prestate.json.orphan.tmp"
    orphan.write_bytes(b"residue")
    orphan.chmod(0o600)
    with pytest.raises(module.CutoverAttestationError, match="noncanonical"):
        module.prepare(shelf, orphan_state, "a" * 40)


def test_state_publication_crash_leaves_no_named_temp_and_is_resumable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_module()
    shelf = tmp_path / "downloads"
    write_legacy_shelf(shelf)
    state = tmp_path / "receipts" / "initial-release-shelf-cutover"
    state.parent.mkdir(mode=0o700)
    original = module._link_unnamed_file_noreplace_at

    def crash_before_link(*_args, **_kwargs):
        raise module.CutoverAttestationError("simulated publication crash")

    monkeypatch.setattr(module, "_link_unnamed_file_noreplace_at", crash_before_link)
    with pytest.raises(module.CutoverAttestationError, match="simulated"):
        module.prepare(shelf, state, "a" * 40)
    assert state.is_dir()
    assert list(state.iterdir()) == []

    monkeypatch.setattr(module, "_link_unnamed_file_noreplace_at", original)
    assert module.prepare(shelf, state, "a" * 40)["status"] == "pass"


def test_evidence_publication_crash_leaves_no_named_temp(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_module()
    producer = tmp_path / "producer"
    producer.mkdir()
    source = producer / "compose.json"
    write_json(source, valid_compose_attestation(module, tmp_path))
    deploy = tmp_path / "deploy"
    deploy.mkdir(mode=0o700)
    output = deploy / module.COMPOSE_EVIDENCE_NAME
    original = module._link_unnamed_file_noreplace_at

    def crash_before_link(*_args, **_kwargs):
        raise module.CutoverAttestationError("simulated evidence crash")

    monkeypatch.setattr(module, "_link_unnamed_file_noreplace_at", crash_before_link)
    with pytest.raises(module.CutoverAttestationError, match="simulated"):
        module.snapshot_evidence("compose", source, output)
    assert list(deploy.iterdir()) == []

    monkeypatch.setattr(module, "_link_unnamed_file_noreplace_at", original)
    assert module.snapshot_evidence("compose", source, output)["status"] == "pass"


@pytest.mark.parametrize("control_name", [".release-shelf-layout-v1", "CURRENT.JSON"])
def test_prepare_rejects_marker_or_current_with_noncanonical_casing(
    tmp_path: Path, control_name: str
) -> None:
    module = load_module()
    shelf = tmp_path / "downloads"
    write_legacy_shelf(shelf)
    (shelf / control_name).write_text("forged\n", encoding="utf-8")
    state = tmp_path / "receipts" / "initial-release-shelf-cutover"
    state.parent.mkdir(mode=0o700)

    with pytest.raises(module.CutoverAttestationError, match="exact absence"):
        module.prepare(shelf, state, "b" * 40)

    assert not state.exists()


def test_prepare_rejects_unresolved_or_committed_activation_history(tmp_path: Path) -> None:
    module = load_module()
    shelf = tmp_path / "downloads"
    write_legacy_shelf(shelf)
    receipt = shelf / ".release-shelf-activation-journal" / "activation-prior"
    write_json(receipt / "intent.json", {"forged": True})
    state = tmp_path / "receipts" / "initial-release-shelf-cutover"
    state.parent.mkdir(mode=0o700)

    with pytest.raises(module.CutoverAttestationError, match="unresolved"):
        module.prepare(shelf, state, "c" * 40)

    write_json(
        receipt / "outcome.json",
        {
            "schemaVersion": module.OUTCOME_SCHEMA,
            "state": "committed",
            "activationReceiptId": "activation-prior",
            "intentSha256": "sha256:" + "0" * 64,
            "resolvedAtUtc": "2026-07-22T00:59:00Z",
        },
    )
    with pytest.raises(module.CutoverAttestationError):
        module.prepare(shelf, state, "c" * 40)


def test_request_start_rejects_forged_prestate_or_legacy_drift(tmp_path: Path) -> None:
    module = load_module()
    shelf = tmp_path / "downloads"
    write_legacy_shelf(shelf)
    state = tmp_path / "receipts" / "initial-release-shelf-cutover"
    state.parent.mkdir(mode=0o700)
    module.prepare(shelf, state, "d" * 40)
    (shelf / "files" / "chummer-win.exe").write_bytes(b"drift")

    with pytest.raises(module.CutoverAttestationError, match="changed"):
        module.request_start(shelf, state)

    prestate = json.loads((state / "prestate.json").read_text(encoding="utf-8"))
    prestate["shelfSnapshot"]["markerAbsent"] = False
    write_json(state / "prestate.json", prestate)
    with pytest.raises(module.CutoverAttestationError):
        module.request_start(shelf, state)


@pytest.mark.parametrize("phase", ["prepare", "start", "aborted", "poststate"])
def test_receipt_publication_recaptures_exact_shelf_file_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    phase: str,
) -> None:
    module = load_module()
    shelf = tmp_path / "downloads"
    state = tmp_path / "receipts" / "initial-release-shelf-cutover"
    state.parent.mkdir(mode=0o700)
    payloads = write_legacy_shelf(shelf)
    if phase != "prepare":
        module.prepare(shelf, state, "a" * 40)
    if phase in ("aborted", "poststate"):
        module.request_start(shelf, state)
    if phase == "poststate":
        generation_id, _receipt_id = materialize_committed_cutover(
            module, shelf, payloads
        )
        mutation_path = (
            shelf
            / module.GENERATIONS_NAME
            / generation_id
            / "files"
            / "chummer-win.exe"
        )
        target_name = module.POSTSTATE_NAME
    else:
        mutation_path = shelf / "files" / "chummer-win.exe"
        target_name = {
            "prepare": module.PRESTATE_NAME,
            "start": module.START_NAME,
            "aborted": module.ABORTED_NAME,
        }[phase]
    original = module.atomic_write_new_at

    def publish_then_touch(state_root, name, payload):
        original(state_root, name, payload)
        if name == target_name:
            raw = mutation_path.read_bytes()
            mutation_path.write_bytes(raw)

    monkeypatch.setattr(module, "atomic_write_new_at", publish_then_touch)
    operation = {
        "prepare": lambda: module.prepare(shelf, state, "a" * 40),
        "start": lambda: module.request_start(shelf, state),
        "aborted": lambda: module.verify_outcome(shelf, state),
        "poststate": lambda: module.verify_outcome(shelf, state),
    }[phase]
    with pytest.raises(module.CutoverAttestationError, match="changed"):
        operation()


@pytest.mark.parametrize("phase", ["start", "aborted", "poststate"])
def test_inspection_detects_same_byte_nested_file_replacement(
    tmp_path: Path,
    phase: str,
) -> None:
    module = load_module()
    shelf, state, payloads, _prestate, _start = prepare_requested(module, tmp_path)
    mutation_path = shelf / "files" / "chummer-win.exe"
    if phase == "aborted":
        module.verify_outcome(shelf, state)
    elif phase == "poststate":
        generation_id, _receipt_id = materialize_committed_cutover(
            module, shelf, payloads
        )
        module.verify_outcome(shelf, state)
        mutation_path = (
            shelf
            / module.GENERATIONS_NAME
            / generation_id
            / "files"
            / "chummer-win.exe"
        )
    raw = mutation_path.read_bytes()
    mutation_path.write_bytes(raw)
    with pytest.raises(module.CutoverAttestationError, match="changed"):
        module.inspect_deploy_state(shelf, state, "a" * 40)


def test_verify_outcome_accepts_exact_committed_server_journal_and_finalize(
    tmp_path: Path,
) -> None:
    module = load_module()
    shelf, state, payloads, _prestate, _start = prepare_requested(module, tmp_path)
    generation_id, receipt_id = materialize_committed_cutover(module, shelf, payloads)

    poststate = module.verify_outcome(shelf, state)

    assert poststate["classification"] == "committed"
    assert poststate["currentPointer"]["generationId"] == generation_id
    assert poststate["currentPointer"]["activationReceiptId"] == receipt_id
    assert poststate["legacyPayloadPreserved"] is True
    compose, readiness, postdeploy, active, candidate = materialize_final_evidence(
        module, tmp_path
    )
    complete = module.finalize(
        state,
        compose,
        readiness,
        postdeploy,
        active,
        candidate["imageId"],
    )
    assert complete["candidate"] == candidate
    assert complete["generationId"] == generation_id
    assert "ordinaryGovernedDeployVerified" not in complete
    assert "publicationReadinessVerified" not in complete


@pytest.mark.parametrize(
    "mutation",
    [
        "marker-bytes",
        "writer-policy",
        "legacy-payload",
        "outcome-digest",
        "current-bytes",
    ],
)
def test_verify_outcome_rejects_forged_marker_current_receipt_or_preservation(
    tmp_path: Path, mutation: str
) -> None:
    module = load_module()
    shelf, state, payloads, _prestate, _start = prepare_requested(module, tmp_path)
    _generation_id, receipt_id = materialize_committed_cutover(module, shelf, payloads)
    if mutation == "marker-bytes":
        (shelf / ".release-shelf-layout-v1").write_bytes(b"v1\n")
    elif mutation == "writer-policy":
        write_json(
            shelf / ".release-shelf-writer-policy.json",
            {"schemaVersion": module.WRITER_POLICY_SCHEMA, "mode": "legacy"},
        )
    elif mutation == "legacy-payload":
        generation = json.loads((shelf / "current.json").read_text())["generationId"]
        (shelf / "generations" / generation / "files" / "chummer-win.exe").write_bytes(
            b"forged"
        )
    elif mutation == "outcome-digest":
        outcome = shelf / ".release-shelf-activation-journal" / receipt_id / "outcome.json"
        payload = json.loads(outcome.read_text())
        payload["intentSha256"] = "sha256:" + "0" * 64
        write_json(outcome, payload)
    else:
        pointer = json.loads((shelf / "current.json").read_text())
        pointer["releaseVersion"] = "forged"
        write_json(shelf / "current.json", pointer)

    with pytest.raises(module.CutoverAttestationError):
        module.verify_outcome(shelf, state)

    assert not (state / "poststate.json").exists()


@pytest.mark.parametrize("mutation", ["absent", "symlink", "mode", "hardlink", "case"])
def test_committed_cutover_requires_exact_persistent_promotion_lock(
    tmp_path: Path,
    mutation: str,
) -> None:
    module = load_module()
    shelf, state, payloads, _prestate, _start = prepare_requested(module, tmp_path)
    materialize_committed_cutover(module, shelf, payloads)
    lock = shelf / module.LOCK_NAME
    if mutation == "absent":
        lock.unlink()
    elif mutation == "symlink":
        lock.unlink()
        outside = tmp_path / "outside.lock"
        outside.write_bytes(b"")
        outside.chmod(0o600)
        lock.symlink_to(outside)
    elif mutation == "mode":
        lock.chmod(0o644)
    elif mutation == "hardlink":
        os.link(lock, tmp_path / "second.lock")
    else:
        lock.rename(shelf / ".RELEASE-SHELF-PROMOTION.LOCK")

    with pytest.raises((module.CutoverAttestationError, OSError)):
        module.verify_outcome(shelf, state)
    assert not (state / module.POSTSTATE_NAME).exists()


def test_verify_outcome_requires_recovery_while_active_intent_exists(tmp_path: Path) -> None:
    module = load_module()
    shelf, state, _payloads, _prestate, _start = prepare_requested(module, tmp_path)
    write_json(shelf / ".release-shelf-activation-intent.json", {"state": "prepared"})

    with pytest.raises(module.CutoverAttestationError, match="recovery-only"):
        module.verify_outcome(shelf, state)

    assert not (state / "poststate.json").exists()
    assert not (state / "aborted.json").exists()


def test_recovery_classifies_exact_unchanged_legacy_shelf_as_aborted(tmp_path: Path) -> None:
    module = load_module()
    shelf, state, _payloads, prestate, _start = prepare_requested(module, tmp_path)

    aborted = module.verify_outcome(shelf, state)

    assert aborted["classification"] == "aborted"
    assert aborted["legacyShelfUnchanged"] is True
    assert aborted["legacyInventoryDigest"] == prestate["shelfSnapshot"][
        "legacyInventory"
    ]["digest"]
    assert not (state / "poststate.json").exists()


def test_recovered_aborted_journal_is_byte_bound_and_reinspected(
    tmp_path: Path,
) -> None:
    module = load_module()
    shelf, state, _payloads, _prestate, _start = prepare_requested(module, tmp_path)
    _receipt_id, _receipt_root = materialize_aborted_recovery(module, shelf)

    aborted = module.verify_outcome(shelf, state)
    assert aborted["classification"] == "aborted"
    assert (
        module.inspect_deploy_state(shelf, state, "a" * 40)["classification"]
        == "aborted"
    )

    (shelf / module.LOCK_NAME).write_bytes(b"drift")
    with pytest.raises(module.CutoverAttestationError):
        module.inspect_deploy_state(shelf, state, "a" * 40)


@pytest.mark.parametrize("mutation", ["symlink", "non-json", "forged-bytes"])
def test_recovered_aborted_journal_rejects_forged_intent(
    tmp_path: Path,
    mutation: str,
) -> None:
    module = load_module()
    shelf, state, _payloads, _prestate, _start = prepare_requested(module, tmp_path)
    _receipt_id, receipt_root = materialize_aborted_recovery(module, shelf)
    intent_path = receipt_root / "intent.json"
    if mutation == "symlink":
        outside = tmp_path / "intent.json"
        intent_path.rename(outside)
        intent_path.symlink_to(outside)
    elif mutation == "non-json":
        intent_path.write_bytes(b"not-json\n")
    else:
        intent = json.loads(intent_path.read_text(encoding="utf-8"))
        intent["intent"]["pointerSha256"] = "sha256:" + "0" * 64
        forged_raw = write_json(intent_path, intent)
        outcome_path = receipt_root / "outcome.json"
        outcome = json.loads(outcome_path.read_text(encoding="utf-8"))
        outcome["intentSha256"] = f"sha256:{sha256(forged_raw[:-1])}"
        write_json(outcome_path, outcome)

    with pytest.raises((module.CutoverAttestationError, OSError)):
        module.verify_outcome(shelf, state)
    assert not (state / module.ABORTED_NAME).exists()


def test_terminal_outcomes_are_mutually_exclusive(tmp_path: Path) -> None:
    module = load_module()
    shelf, state, payloads, _prestate, _start = prepare_requested(module, tmp_path)
    materialize_committed_cutover(module, shelf, payloads)
    module.verify_outcome(shelf, state)
    with pytest.raises(module.CutoverAttestationError, match="exact prestate/start"):
        module.verify_outcome(shelf, state)

    contradictory = state / module.ABORTED_NAME
    write_json(contradictory, {"forged": True})
    contradictory.chmod(0o600)
    with pytest.raises(module.CutoverAttestationError, match="phase set"):
        module.inspect_deploy_state(shelf, state, "a" * 40)


def test_aborted_terminal_cannot_be_reclassified_committed(tmp_path: Path) -> None:
    module = load_module()
    shelf, state, payloads, _prestate, _start = prepare_requested(module, tmp_path)
    module.verify_outcome(shelf, state)
    materialize_committed_cutover(module, shelf, payloads)
    with pytest.raises(module.CutoverAttestationError, match="exact prestate/start"):
        module.verify_outcome(shelf, state)


def test_second_cutover_against_layout_v1_fails_closed(tmp_path: Path) -> None:
    module = load_module()
    shelf, state, payloads, _prestate, _start = prepare_requested(module, tmp_path)
    materialize_committed_cutover(module, shelf, payloads)
    module.verify_outcome(shelf, state)
    second_state = tmp_path / "receipts" / "second-cutover"
    second_state.parent.mkdir()

    with pytest.raises(module.CutoverAttestationError, match="exact absence"):
        module.prepare(shelf, second_state, "f" * 40)

    assert not second_state.exists()


def write_valid_complete(
    module,
    tmp_path: Path,
    state: Path,
    poststate: dict[str, object],
) -> dict[str, object]:
    assert isinstance(poststate.get("currentPointer"), dict)
    compose, readiness, postdeploy, active, candidate = materialize_final_evidence(
        module, tmp_path
    )
    return module.finalize(
        state,
        compose,
        readiness,
        postdeploy,
        active,
        candidate["imageId"],
    )


def test_inspect_deploy_state_prestart_liveness_and_phase_matrix(tmp_path: Path) -> None:
    module = load_module()
    shelf = tmp_path / "downloads"
    state = tmp_path / "receipts" / "initial-release-shelf-cutover"
    state.parent.mkdir(mode=0o700)
    payloads = write_legacy_shelf(shelf)
    head = "7" * 40

    assert module.inspect_deploy_state(shelf, state, head)["classification"] == "absent"
    first = module.prepare(shelf, state, head)
    assert module.prepare(shelf, state, head) == first
    assert (
        module.inspect_deploy_state(shelf, state, head)["classification"]
        == "prestate-resumable"
    )

    module.request_start(shelf, state)
    assert (
        module.inspect_deploy_state(shelf, state, head)["classification"]
        == "unknown-outcome"
    )
    materialize_committed_cutover(module, shelf, payloads)
    poststate = module.verify_outcome(shelf, state)
    assert (
        module.inspect_deploy_state(shelf, state, head)["classification"]
        == "steady-handoff"
    )
    write_valid_complete(module, tmp_path, state, poststate)
    assert (
        module.inspect_deploy_state(shelf, state, head)["classification"]
        == "complete"
    )


def test_prestate_resume_rejects_source_shelf_or_object_identity_drift(
    tmp_path: Path,
) -> None:
    module = load_module()
    shelf = tmp_path / "downloads"
    state = tmp_path / "receipts" / "initial-release-shelf-cutover"
    state.parent.mkdir(mode=0o700)
    write_legacy_shelf(shelf)
    head = "8" * 40
    module.prepare(shelf, state, head)

    with pytest.raises(module.CutoverAttestationError, match="source HEAD"):
        module.inspect_deploy_state(shelf, state, "9" * 40)

    (shelf / "files" / "chummer-win.exe").write_bytes(b"changed\n")
    with pytest.raises(module.CutoverAttestationError, match="changed"):
        module.inspect_deploy_state(shelf, state, head)


@pytest.mark.parametrize("forgery", ["symlink", "hardlink", "case-alias", "extra"])
def test_state_classifier_rejects_noncanonical_receipt_shapes(
    tmp_path: Path, forgery: str
) -> None:
    module = load_module()
    shelf = tmp_path / "downloads"
    state = tmp_path / "receipts" / "initial-release-shelf-cutover"
    state.parent.mkdir(mode=0o700)
    write_legacy_shelf(shelf)
    head = "a" * 40
    module.prepare(shelf, state, head)
    prestate = state / module.PRESTATE_NAME

    if forgery == "symlink":
        outside = tmp_path / "outside.json"
        prestate.rename(outside)
        prestate.symlink_to(outside)
    elif forgery == "hardlink":
        os.link(prestate, tmp_path / "second-link.json")
    elif forgery == "case-alias":
        prestate.rename(state / "Prestate.json")
    else:
        extra = state / "unexpected.json"
        extra.write_text("{}\n", encoding="utf-8")
        extra.chmod(0o600)

    with pytest.raises(module.CutoverAttestationError):
        module.inspect_deploy_state(shelf, state, head)


def test_complete_state_survives_later_head_and_legitimate_generation(
    tmp_path: Path,
) -> None:
    module = load_module()
    shelf, state, payloads, prestate, _start = prepare_requested(module, tmp_path)
    head = prestate["sourceHead"]
    materialize_committed_cutover(module, shelf, payloads)
    poststate = module.verify_outcome(shelf, state)
    write_valid_complete(module, tmp_path, state, poststate)
    assert module.inspect_deploy_state(shelf, state, head)["classification"] == "complete"

    later_generation, later_receipt = materialize_later_generation(module, shelf)
    assert (shelf / module.GENERATIONS_NAME / later_generation).is_dir()
    assert (shelf / module.JOURNAL_NAME / later_receipt).is_dir()
    assert (
        module.inspect_deploy_state(shelf, state, "b" * 40)["classification"]
        == "complete"
    )


def test_complete_state_survives_valid_later_rollback_to_initial_generation(
    tmp_path: Path,
) -> None:
    module = load_module()
    shelf, state, payloads, _prestate, _start = prepare_requested(module, tmp_path)
    initial_generation, _initial_receipt = materialize_committed_cutover(
        module, shelf, payloads
    )
    poststate = module.verify_outcome(shelf, state)
    write_valid_complete(module, tmp_path, state, poststate)
    materialize_later_generation(module, shelf)
    rollback_generation, _rollback_receipt, _receipt_root = (
        materialize_valid_rollback(module, shelf)
    )
    assert rollback_generation == initial_generation
    assert json.loads((shelf / module.POINTER_NAME).read_text(encoding="utf-8"))[
        "generationId"
    ] == initial_generation
    assert (
        module.inspect_deploy_state(shelf, state, "c" * 40)["classification"]
        == "complete"
    )


@pytest.mark.parametrize("mutation", ["unknown-operation", "rollback-without-previous"])
def test_complete_state_rejects_unknown_or_malformed_later_operation(
    tmp_path: Path,
    mutation: str,
) -> None:
    module = load_module()
    shelf, state, payloads, _prestate, _start = prepare_requested(module, tmp_path)
    materialize_committed_cutover(module, shelf, payloads)
    poststate = module.verify_outcome(shelf, state)
    write_valid_complete(module, tmp_path, state, poststate)
    materialize_later_generation(module, shelf)
    _generation, _receipt, receipt_root = materialize_valid_rollback(module, shelf)
    intent_path = receipt_root / "intent.json"
    intent = json.loads(intent_path.read_text(encoding="utf-8"))
    if mutation == "unknown-operation":
        intent["intent"]["operation"] = "delete"
    else:
        intent["intent"]["previousGenerationId"] = None
        intent["intent"]["previousPointerSha256"] = None
        intent["intent"]["previousPointerBase64"] = None
        intent["previousPointerBase64"] = None
    intent_raw = write_json(intent_path, intent)
    outcome_path = receipt_root / "outcome.json"
    outcome = json.loads(outcome_path.read_text(encoding="utf-8"))
    outcome["intentSha256"] = f"sha256:{sha256(intent_raw[:-1])}"
    write_json(outcome_path, outcome)
    with pytest.raises(module.CutoverAttestationError):
        module.inspect_deploy_state(shelf, state, "c" * 40)


@pytest.mark.parametrize("mutation", ["active-intent", "lock-mode", "marker-hardlink"])
def test_complete_state_requires_safe_generic_bootstrap_controls(
    tmp_path: Path,
    mutation: str,
) -> None:
    module = load_module()
    shelf, state, payloads, _prestate, _start = prepare_requested(module, tmp_path)
    materialize_committed_cutover(module, shelf, payloads)
    poststate = module.verify_outcome(shelf, state)
    write_valid_complete(module, tmp_path, state, poststate)
    if mutation == "active-intent":
        write_json(shelf / module.ACTIVE_INTENT_NAME, {"state": "prepared"})
    elif mutation == "lock-mode":
        (shelf / module.LOCK_NAME).chmod(0o644)
    else:
        os.link(shelf / module.MARKER_NAME, tmp_path / "second-marker")
    with pytest.raises(module.CutoverAttestationError):
        module.inspect_deploy_state(shelf, state, "b" * 40)


@pytest.mark.parametrize(
    ("left", "right", "expected"),
    [
        (b'{"value":true}', b'{"value":1}', False),
        (b'{"value":1}', b'{"value":1.0}', False),
        (b'{"value":1.0}', b'{"value":1e0}', False),
        (b'{"value":1}', b'{"value":1}', True),
    ],
)
def test_idempotence_preserves_json_scalar_and_raw_number_kinds(
    left: bytes, right: bytes, expected: bool
) -> None:
    module = load_module()
    timestamp = b'"generatedAtUtc":"2026-07-22T01:00:00Z",'
    left_receipt = b"{" + timestamp + left[1:]
    right_receipt = b"{" + timestamp + right[1:]
    assert module._idempotent_receipts_equal(left_receipt, right_receipt) is expected


@pytest.mark.parametrize(
    "timestamp",
    [None, "2026-07-22 01:00:00Z", "2026-07-22T01:00:00+01:00"],
)
def test_idempotence_rejects_missing_or_noncanonical_timestamps(
    timestamp: str | None,
) -> None:
    module = load_module()
    existing = {"value": 1}
    if timestamp is not None:
        existing["generatedAtUtc"] = timestamp
    candidate = {"generatedAtUtc": "2026-07-22T01:00:00Z", "value": 1}
    with pytest.raises(module.CutoverAttestationError, match="timestamp"):
        module._idempotent_receipts_equal(
            json.dumps(existing).encode("utf-8"),
            json.dumps(candidate).encode("utf-8"),
        )


def finalizable_state(module, tmp_path: Path) -> Path:
    shelf, state, payloads, _prestate, _start = prepare_requested(module, tmp_path)
    materialize_committed_cutover(module, shelf, payloads)
    module.verify_outcome(shelf, state)
    return state


def test_evidence_snapshots_are_owner_only_immutable_raw_bytes(tmp_path: Path) -> None:
    module = load_module()
    compose, readiness, postdeploy, active, _candidate = materialize_final_evidence(
        module, tmp_path
    )
    for path in (compose, readiness, postdeploy, active):
        assert path.stat().st_mode & 0o777 == 0o600
        assert path.stat().st_nlink == 1

    producer = tmp_path / "producer" / "compose.json"
    snapshotted = compose.read_bytes()
    changed = valid_compose_attestation(module, tmp_path)
    write_json(producer, changed, indent=None)
    assert compose.read_bytes() == snapshotted

    with pytest.raises(module.CutoverAttestationError, match="different bytes"):
        module.snapshot_evidence("compose", producer, compose)


@pytest.mark.parametrize("mutation", ["writable", "hardlink", "case-alias"])
def test_evidence_source_requires_owner_controlled_single_identity(
    tmp_path: Path,
    mutation: str,
) -> None:
    module = load_module()
    source = tmp_path / "compose.json"
    write_json(source, valid_compose_attestation(module, tmp_path))
    if mutation == "writable":
        source.chmod(0o664)
    elif mutation == "hardlink":
        os.link(source, tmp_path / "compose-second.json")
    else:
        write_json(tmp_path / "COMPOSE.JSON", valid_compose_attestation(module, tmp_path))
    deploy = tmp_path / "deploy"
    deploy.mkdir(mode=0o700)
    with pytest.raises(module.CutoverAttestationError):
        module.snapshot_evidence(
            "compose", source, deploy / module.COMPOSE_EVIDENCE_NAME
        )


def test_evidence_source_identity_remains_stable_through_snapshot_publication(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_module()
    source = tmp_path / "compose.json"
    write_json(source, valid_compose_attestation(module, tmp_path))
    deploy = tmp_path / "deploy"
    deploy.mkdir(mode=0o700)
    original = module._atomic_write_evidence_raw

    def publish_then_touch(output, expected_name, raw):
        original(output, expected_name, raw)
        source.write_bytes(source.read_bytes())

    monkeypatch.setattr(module, "_atomic_write_evidence_raw", publish_then_touch)
    with pytest.raises(module.CutoverAttestationError, match="changed"):
        module.snapshot_evidence(
            "compose", source, deploy / module.COMPOSE_EVIDENCE_NAME
        )


@pytest.mark.parametrize("mutation", ["directory-replacement", "bytes", "hardlink"])
def test_complete_reopens_bound_immutable_evidence_set(
    tmp_path: Path,
    mutation: str,
) -> None:
    module = load_module()
    shelf, state, payloads, _prestate, _start = prepare_requested(module, tmp_path)
    materialize_committed_cutover(module, shelf, payloads)
    poststate = module.verify_outcome(shelf, state)
    complete = write_valid_complete(module, tmp_path, state, poststate)
    evidence_root = Path(complete["evidenceDirectory"]["path"])
    if mutation == "directory-replacement":
        retired = evidence_root.with_name(evidence_root.name + ".retired")
        evidence_root.rename(retired)
        evidence_root.mkdir(mode=0o700)
        for name in (
            module.COMPOSE_EVIDENCE_NAME,
            module.READINESS_EVIDENCE_NAME,
            module.POSTDEPLOY_EVIDENCE_NAME,
            module.RUNTIME_AUTHORITY_EVIDENCE_NAME,
        ):
            target = evidence_root / name
            target.write_bytes((retired / name).read_bytes())
            target.chmod(0o600)
    elif mutation == "bytes":
        active = evidence_root / module.RUNTIME_AUTHORITY_EVIDENCE_NAME
        payload = json.loads(active.read_text(encoding="utf-8"))
        payload["generatedAtUtc"] = "2026-07-22T01:04:00Z"
        write_json(active, payload)
        active.chmod(0o600)
    else:
        os.link(
            evidence_root / module.COMPOSE_EVIDENCE_NAME,
            tmp_path / "second-compose-evidence.json",
        )
    with pytest.raises(module.CutoverAttestationError):
        module.inspect_deploy_state(shelf, state, "b" * 40)


def test_state_parent_must_be_owner_only(tmp_path: Path) -> None:
    module = load_module()
    shelf = tmp_path / "downloads"
    write_legacy_shelf(shelf)
    state = tmp_path / "receipts" / "initial-release-shelf-cutover"
    state.parent.mkdir(mode=0o755)
    state.parent.chmod(0o755)
    with pytest.raises(module.CutoverAttestationError, match="state root is unsafe"):
        module.prepare(shelf, state, "a" * 40)
    assert not state.exists()


@pytest.mark.parametrize(
    ("kind", "mutation"),
    [
        ("compose", "extra"),
        ("postdeploy", "extra"),
        ("postdeploy", "bool-as-int"),
        ("postdeploy", "browser-float"),
    ],
)
def test_evidence_snapshot_rejects_forged_fields_and_scalar_types(
    tmp_path: Path, kind: str, mutation: str
) -> None:
    module = load_module()
    deploy = tmp_path / "deploy"
    deploy.mkdir(mode=0o700)
    source = tmp_path / "source.json"
    if kind == "compose":
        payload = valid_compose_attestation(module, tmp_path)
        payload["forged"] = True
    else:
        payload = valid_postdeploy_attestation(module)
        if mutation == "extra":
            payload["forged"] = True
        elif mutation == "bool-as-int":
            payload["strictPreflight"] = 1
        else:
            payload["downloadsStatusBrowserExitCode"] = 0.0
    write_json(source, payload)
    output = deploy / module.EVIDENCE_NAMES[kind]

    with pytest.raises(module.CutoverAttestationError):
        module.snapshot_evidence(kind, source, output)

    assert not output.exists()


def test_finalize_rejects_candidate_mismatch_or_evidence_hardlink(tmp_path: Path) -> None:
    module = load_module()
    state = finalizable_state(module, tmp_path)
    compose, readiness, postdeploy, active, candidate = materialize_final_evidence(
        module, tmp_path
    )
    active_payload = json.loads(active.read_text(encoding="utf-8"))
    active_payload["portal"]["imageId"] = "sha256:" + "e" * 64
    write_json(active, active_payload)
    active.chmod(0o600)
    with pytest.raises(module.CutoverAttestationError, match="identities disagree"):
        module.finalize(
            state,
            compose,
            readiness,
            postdeploy,
            active,
            candidate["imageId"],
        )

    active_payload["portal"]["imageId"] = candidate["imageId"]
    write_json(active, active_payload)
    active.chmod(0o600)
    os.link(compose, tmp_path / "compose-second-link.json")
    with pytest.raises(module.CutoverAttestationError, match="single-link"):
        module.finalize(
            state,
            compose,
            readiness,
            postdeploy,
            active,
            candidate["imageId"],
        )


def test_snapshot_rejects_symlink_source_and_output_case_alias(tmp_path: Path) -> None:
    module = load_module()
    source = tmp_path / "compose-source.json"
    write_json(source, valid_compose_attestation(module, tmp_path))
    source_link = tmp_path / "compose-link.json"
    source_link.symlink_to(source)
    deploy = tmp_path / "deploy"
    deploy.mkdir(mode=0o700)
    output = deploy / module.COMPOSE_EVIDENCE_NAME

    with pytest.raises(module.CutoverAttestationError):
        module.snapshot_evidence("compose", source_link, output)

    alias = deploy / module.COMPOSE_EVIDENCE_NAME.capitalize()
    alias.write_text("{}\n", encoding="utf-8")
    alias.chmod(0o600)
    with pytest.raises(module.CutoverAttestationError, match="casing alias"):
        module.snapshot_evidence("compose", source, output)


def test_descriptor_anchor_rejects_symlink_ancestor_and_root_exchange(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = load_module()
    real_parent = tmp_path / "real-parent"
    real_parent.mkdir()
    source = real_parent / "compose.json"
    write_json(source, valid_compose_attestation(module, tmp_path))
    alias_parent = tmp_path / "alias-parent"
    alias_parent.symlink_to(real_parent, target_is_directory=True)
    deploy = tmp_path / "deploy"
    deploy.mkdir(mode=0o700)

    with pytest.raises(module.CutoverAttestationError, match="symlink component"):
        module.snapshot_evidence(
            "compose",
            alias_parent / "compose.json",
            deploy / module.COMPOSE_EVIDENCE_NAME,
        )

    shelf = tmp_path / "downloads"
    write_legacy_shelf(shelf)
    state = tmp_path / "receipts" / "initial-release-shelf-cutover"
    state.parent.mkdir(mode=0o700)
    original_inventory = module.inventory_tree_fd

    def exchange_root(descriptor: int, *, skip_top_level_controls: bool):
        rows = original_inventory(
            descriptor,
            skip_top_level_controls=skip_top_level_controls,
        )
        shelf.rename(tmp_path / "retired-downloads")
        shelf.mkdir()
        return rows

    monkeypatch.setattr(module, "inventory_tree_fd", exchange_root)
    with pytest.raises(module.CutoverAttestationError, match="changed"):
        module.prepare(shelf, state, "f" * 40)
    assert not state.exists()

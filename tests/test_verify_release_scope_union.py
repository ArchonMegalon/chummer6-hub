from __future__ import annotations

import fcntl
import hashlib
import importlib.util
import json
import mmap
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
from typing import Any, Callable
import zlib

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "verify_release_scope_union.py"
VERSION = "run-20260726-global-stable"
PLATFORMS = {
    "linux": ("linux-x64", "deb"),
    "macos": ("osx-arm64", "dmg"),
    "windows": ("win-x64", "exe"),
}
GATES = {
    "visual": "chummer6-ui.desktop_visual_familiarity_exit_gate",
    "workflow": "chummer6-ui.desktop_workflow_execution_gate",
    "executable": "chummer6-ui.desktop_executable_exit_gate",
}
REGISTRY_PROTECTED_PATHS = (
    "scripts/release/promote_public_stable_release_channel.sh",
    "scripts/materialize_public_release_channel.py",
    "scripts/verify_public_release_channel.py",
)
BINDING_FIELDS = {
    "authority_snapshot_sha256",
    "contract_name",
    "contract_version",
    "manifest_sha256",
    "platform",
    "primary_head",
    "registry_commit",
    "release_decision_sha256",
    "release_scope_decision_sha256",
    "release_version",
    "required_heads",
    "rid",
}


class ProcessAfterWait:
    def __init__(
        self,
        process: Any,
        callback: Callable[[], None],
    ) -> None:
        self._process = process
        self._callback = callback
        self._called = False

    def __getattr__(self, name: str) -> Any:
        return getattr(self._process, name)

    def wait(self, *args: object, **kwargs: object) -> int:
        return_code = self._process.wait(*args, **kwargs)
        if not self._called:
            self._called = True
            self._callback()
        return return_code


def load_real_ui_candidate_routing() -> Any:
    configured = os.environ.get("CHUMMER_UI_CANDIDATE_ROUTING_PATH", "").strip()
    candidates = [
        Path(configured) if configured else None,
        Path(
            "/docker/chummercomplete/.codex-worktrees/"
            "ui-stable-presentation-receipts-20260726/"
            "scripts/ai/candidate_proof_routing.py"
        ),
        Path(
            "/docker/chummercomplete/chummer6-ui/"
            "scripts/ai/candidate_proof_routing.py"
        ),
    ]
    path = next(
        (
            candidate
            for candidate in candidates
            if candidate is not None and candidate.is_file()
        ),
        None,
    )
    if path is None:
        pytest.skip(
            "real chummer6-ui candidate routing checkout is not available"
        )
    spec = importlib.util.spec_from_file_location(
        "real_ui_candidate_proof_routing",
        path,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def load_union_module() -> Any:
    scripts_path = str(ROOT / "scripts")
    if scripts_path not in sys.path:
        sys.path.insert(0, scripts_path)
    spec = importlib.util.spec_from_file_location(
        "release_scope_union_under_test",
        SCRIPT,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def canonical(payload: object) -> bytes:
    return (
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        + "\n"
    ).encode("utf-8")


def write_bytes(path: Path, raw: bytes, mode: int = 0o600) -> bytes:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    path.chmod(mode)
    return raw


def write_json(path: Path, payload: object, mode: int = 0o600) -> bytes:
    return write_bytes(path, canonical(payload), mode)


def create_registry_fixture(repository: Path) -> str:
    for relative in REGISTRY_PROTECTED_PATHS:
        write_bytes(repository / relative, f"{relative}\n".encode(), 0o644)
    subprocess.run(
        ["/usr/bin/git", "init", "-q", str(repository)],
        check=True,
    )
    subprocess.run(
        ["/usr/bin/git", "-C", str(repository), "add", "."],
        check=True,
    )
    commit_environment = {
        **os.environ,
        "GIT_AUTHOR_NAME": "Release Fixture",
        "GIT_AUTHOR_EMAIL": "fixture@example.invalid",
        "GIT_COMMITTER_NAME": "Release Fixture",
        "GIT_COMMITTER_EMAIL": "fixture@example.invalid",
    }
    subprocess.run(
        [
            "/usr/bin/git",
            "-C",
            str(repository),
            "commit",
            "-q",
            "-m",
            "fixture",
        ],
        check=True,
        env=commit_environment,
    )
    return subprocess.run(
        ["/usr/bin/git", "-C", str(repository), "rev-parse", "HEAD"],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    ).stdout.strip()


def decision(platform: str, rid: str) -> dict[str, Any]:
    return {
        "contractName": "chummer.release-scope-decision/v1",
        "contractVersion": 1,
        "decisionId": f"scope-{VERSION}-{platform}",
        "status": "approved",
        "approvedAtUtc": "2026-07-26T12:00:00Z",
        "approvedBy": "Chummer release authority",
        "releaseVersion": VERSION,
        "channel": "public_stable",
        "releaseTarget": "stable",
        "supportOwner": "chummer-release-operations",
        "platforms": [
            {
                "platform": platform,
                "rid": rid,
                "primaryHead": "avalonia",
                "fallbackHeads": [],
                "artifactAccessClass": "open_public",
                "signingRequirement": "signed",
            }
        ],
    }


def candidate_state() -> dict[str, Any]:
    files: dict[str, bytes] = {}
    artifacts: list[dict[str, Any]] = []
    promoted: list[dict[str, Any]] = []
    for platform in ("linux", "windows", "macos"):
        rid, extension = PLATFORMS[platform]
        artifact_id = f"avalonia-{rid}-installer"
        file_name = f"chummer-avalonia-{rid}-installer.{extension}"
        raw = f"{platform}-signed-installer-bytes".encode()
        files[file_name] = raw
        row: dict[str, Any] = {
            "artifactId": artifact_id,
            "head": "avalonia",
            "platform": platform,
            "rid": rid,
            "kind": "installer",
            "fileName": file_name,
            "sha256": hashlib.sha256(raw).hexdigest(),
            "sizeBytes": len(raw),
            "installAccessClass": "open_public",
            "payloadFileName": None,
            "payloadSha256": None,
            "payloadSizeBytes": None,
        }
        if platform == "windows":
            payload_name = "chummer-avalonia-win-x64-payload.zip"
            payload_raw = b"windows-signed-payload-bytes"
            files[payload_name] = payload_raw
            row.update(
                {
                    "payloadFileName": payload_name,
                    "payloadSha256": hashlib.sha256(payload_raw).hexdigest(),
                    "payloadSizeBytes": len(payload_raw),
                }
            )
        artifacts.append(row)
        promoted.append(
            {
                "tupleId": f"avalonia:{platform}:{rid}",
                "head": "avalonia",
                "platform": platform,
                "rid": rid,
                "arch": "arm64" if platform == "macos" else "x64",
                "kind": "installer",
                "artifactId": artifact_id,
            }
        )
    tuples = sorted(f"avalonia:{rid}:{platform}" for platform, (rid, _) in PLATFORMS.items())
    manifest = {
        "version": VERSION,
        "releaseVersion": VERSION,
        "channel": "public_stable",
        "channelId": "public_stable",
        "status": "published",
        "rolloutState": "public_stable",
        "supportabilityState": "gold_supported",
        "generatedAt": "2026-07-26T12:20:00Z",
        "desktopTupleCoverage": {
            "requiredDesktopPlatforms": ["linux", "windows", "macos"],
            "requiredDesktopHeads": ["avalonia"],
            "promotedInstallerTuples": promoted,
            "promotedPlatformHeads": {
                "linux": ["avalonia"],
                "windows": ["avalonia"],
                "macos": ["avalonia"],
            },
            "requiredDesktopPlatformHeadRidTuples": tuples,
            "promotedPlatformHeadRidTuples": tuples,
            "missingRequiredPlatforms": [],
            "missingRequiredHeads": [],
            "missingRequiredPlatformHeadPairs": [],
            "missingRequiredPlatformHeadRidTuples": [],
            "externalProofRequests": [],
            "complete": True,
        },
        "artifacts": artifacts,
    }
    promotion = {
        "contractName": "chummer.run.desktop_release_publication",
        "releaseVersion": VERSION,
        "manifestSha256": "",
        "artifacts": [
            {
                "artifactId": row["artifactId"],
                "fileName": row["fileName"],
                "platform": row["platform"],
                "kind": row["kind"],
                "promotionStatus": "pass",
                "signingStatus": "pass",
                "notarizationStatus": "pass" if row["platform"] == "macos" else "",
                "artifactSha256": row["sha256"],
                "artifactSizeBytes": row["sizeBytes"],
            }
            for row in artifacts
        ],
    }
    return {
        "decisions": {
            platform: decision(platform, rid)
            for platform, (rid, _) in PLATFORMS.items()
        },
        "manifest": manifest,
        "promotion": promotion,
        "files": files,
    }


Mutator = Callable[[dict[str, Any]], None]
ReceiptMutator = Callable[[dict[tuple[str, str], dict[str, Any]]], None]
SigningMutator = Callable[[dict[str, dict[str, Any]]], None]
PostMaterialize = Callable[[dict[str, Any]], None]


def invoke(
    tmp_path: Path,
    *,
    mutate: Mutator | None = None,
    mutate_receipts: ReceiptMutator | None = None,
    mutate_signing: SigningMutator | None = None,
    post_materialize: PostMaterialize | None = None,
    precreate_output: bool = False,
) -> tuple[subprocess.CompletedProcess[str], Path, dict[str, Any]]:
    state = candidate_state()
    if mutate is not None:
        mutate(state)
    registry_repository = tmp_path / "registry-repository"
    for relative in REGISTRY_PROTECTED_PATHS:
        write_bytes(
            registry_repository / relative,
            f"reviewed source: {relative}\n".encode(),
            0o644,
        )
    subprocess.run(
        ["git", "init", "-q", str(registry_repository)],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(registry_repository), "add", "."],
        check=True,
    )
    commit_environment = {
        **os.environ,
        "GIT_AUTHOR_NAME": "Release Fixture",
        "GIT_AUTHOR_EMAIL": "fixture@example.invalid",
        "GIT_COMMITTER_NAME": "Release Fixture",
        "GIT_COMMITTER_EMAIL": "fixture@example.invalid",
        "GIT_AUTHOR_DATE": "2026-07-26T12:00:00Z",
        "GIT_COMMITTER_DATE": "2026-07-26T12:00:00Z",
    }
    subprocess.run(
        [
            "git",
            "-C",
            str(registry_repository),
            "commit",
            "-q",
            "-m",
            "Reviewed Registry fixture",
        ],
        check=True,
        env=commit_environment,
    )
    registry_commit = subprocess.run(
        ["git", "-C", str(registry_repository), "rev-parse", "HEAD"],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    ).stdout.strip()
    files_root = tmp_path / "files"
    for name, raw in state["files"].items():
        write_bytes(files_root / name, raw, 0o644)
    manifest_path = tmp_path / "RELEASE_CHANNEL.generated.json"
    manifest_raw = write_json(manifest_path, state["manifest"], 0o600)
    if not state["promotion"]["manifestSha256"]:
        state["promotion"]["manifestSha256"] = hashlib.sha256(manifest_raw).hexdigest()
    promotion_path = tmp_path / "DESKTOP_RELEASE_PUBLICATION.generated.json"
    write_json(promotion_path, state["promotion"], 0o600)

    decisions: dict[str, dict[str, Any]] = state["decisions"]
    decision_paths: dict[str, Path] = {}
    decision_shas: dict[str, str] = {}
    for platform, payload in decisions.items():
        path = tmp_path / "decisions" / f"{platform}.approved.json"
        raw = write_json(path, payload, 0o600)
        decision_paths[platform] = path
        decision_shas[platform] = hashlib.sha256(raw).hexdigest()

    manifest_sha = hashlib.sha256(manifest_raw).hexdigest()
    review_manifests: dict[str, Path] = {}
    authority_currents: dict[str, Path] = {}
    authority_snapshots: dict[str, Path] = {}
    release_decisions: dict[str, Path] = {}
    review_contexts: dict[str, dict[str, str]] = {}
    for platform, (rid, _) in PLATFORMS.items():
        final_artifact = next(
            row
            for row in state["manifest"]["artifacts"]
            if row["platform"] == platform
        )
        review_manifest = {
            "contractName": "Chummer.Hub.Registry.Contracts",
            "version": VERSION,
            "releaseVersion": VERSION,
            "channel": "public_stable",
            "channelId": "public_stable",
            "status": "published",
            "rolloutState": "public_release_review_required",
            "supportabilityState": "review_required",
            "releaseDecisionStatus": "review_required",
            "generatedAt": "2026-07-26T12:00:00Z",
            "publishedAt": "2026-07-26T12:00:00Z",
            "artifacts": [dict(final_artifact)],
        }
        review_path = tmp_path / "review" / platform / "RELEASE_CHANNEL.json"
        review_raw = write_json(review_path, review_manifest, 0o600)
        review_sha = hashlib.sha256(review_raw).hexdigest()
        release_decision = {
            "contractName": "chummer.preview-release-decision/v1",
            "generatedAt": "2026-07-26T12:01:00Z",
            "status": "review_required",
            "releaseDecisionStatus": "review_required",
            "verdict": "PREVIEW_RELEASE_REVIEW_REQUIRED",
            "releaseVersion": VERSION,
            "releaseScopeDecisionSha256": decision_shas[platform],
            "channel": "public_stable",
            "platforms": [platform],
            "primaryHeadByPlatform": {platform: "avalonia"},
            "fallbackHeadsByPlatform": {platform: []},
            "artifactAccessClass": "open_public",
            "supportOwner": "chummer-release-operations",
            "nextActions": ["Complete global stable union verification."],
            "registryCommit": registry_commit,
            "manifestSha256": review_sha,
            "authoritySnapshotSha256": "",
            "candidateDecisionStatus": "",
            "candidateDecisionSha256": "",
            "manifestGeneratedAt": review_manifest["generatedAt"],
            "scorecardSha256": "",
            "convergenceSha256": "",
            "blockingFindings": [
                {
                    "id": "preview_1",
                    "severity": "release_truth",
                    "summary": "Global stable union verification remains pending.",
                }
            ],
        }
        release_decision_path = (
            tmp_path / "review" / platform / "RELEASE_DECISION.json"
        )
        release_decision_raw = write_json(
            release_decision_path,
            release_decision,
            0o600,
        )
        release_decision_sha = hashlib.sha256(release_decision_raw).hexdigest()
        snapshot_artifact = {
            "artifactId": final_artifact["artifactId"],
            "head": final_artifact["head"],
            "platform": platform,
            "rid": rid,
            "arch": "arm64" if platform == "macos" else "x64",
            "kind": "installer",
            "downloadUrl": (
                f"/downloads/g/{VERSION}/files/{final_artifact['fileName']}"
            ),
            "sha256": final_artifact["sha256"],
            "sizeBytes": final_artifact["sizeBytes"],
            "compatibilityState": "compatible",
            "promotionState": "promoted",
            "publicationScope": "signed-in-and-public",
            "revokeState": "not_revoked",
            "publicInstallRoute": (
                f"/downloads/install/{final_artifact['artifactId']}"
            ),
            "installAccessClass": "open_public",
        }
        snapshot = {
            "authorityContract": "chummer.release-authority-snapshot/v2",
            "releaseVersion": VERSION,
            "channel": "public_stable",
            "status": "published",
            "rolloutState": "public_release_review_required",
            "supportabilityState": "review_required",
            "availablePlatforms": [platform],
            "primaryHeadByPlatform": {platform: "avalonia"},
            "artifactCount": 1,
            "downloadAccessPosture": "open_public",
            "knownIssueSummary": "Global stable union review remains pending.",
            "manifestSha256": review_sha,
            "registryRepository": "ArchonMegalon/chummer6-hub-registry",
            "registryCommit": registry_commit,
            "releaseDecisionStatus": "review_required",
            "releaseDecisionSha256": release_decision_sha,
            "releaseDecisionPath": "RELEASE_DECISION.json",
            "supportOwner": "chummer-release-operations",
            "nextActions": release_decision["nextActions"],
            "artifacts": [snapshot_artifact],
            "manifestPath": "RELEASE_CHANNEL.json",
        }
        snapshot_path = tmp_path / "review" / platform / "SNAPSHOT.json"
        snapshot_raw = write_json(snapshot_path, snapshot, 0o600)
        snapshot_sha = hashlib.sha256(snapshot_raw).hexdigest()
        current = {
            "releaseVersion": VERSION,
            "snapshotSha256": snapshot_sha,
            "decisionSha256": release_decision_sha,
            "status": "review_required",
        }
        current_path = tmp_path / "review" / platform / "CURRENT.json"
        write_json(current_path, current, 0o600)
        review_manifests[platform] = review_path
        authority_currents[platform] = current_path
        authority_snapshots[platform] = snapshot_path
        release_decisions[platform] = release_decision_path
        review_contexts[platform] = {
            "manifestSha256": review_sha,
            "authoritySnapshotSha256": snapshot_sha,
            "releaseDecisionSha256": release_decision_sha,
        }

    receipts: dict[tuple[str, str], dict[str, Any]] = {}
    for platform, (rid, _) in PLATFORMS.items():
        for gate, contract in GATES.items():
            receipts[(platform, gate)] = {
                "contract_name": contract,
                "channelId": "public_stable",
                "releaseVersion": VERSION,
                "status": "pass",
                "summary": f"{platform} {gate} passed",
                "reasons": [],
                "reviews": [],
                "evidence": {"executed": True},
                "campaign_operability_candidate_binding": {
                    "authority_snapshot_sha256": review_contexts[platform][
                        "authoritySnapshotSha256"
                    ],
                    "contract_name": "chummer6-ui.campaign_operability_candidate_binding",
                    "contract_version": 1,
                    "manifest_sha256": review_contexts[platform]["manifestSha256"],
                    "platform": platform,
                    "primary_head": "avalonia",
                    "registry_commit": registry_commit,
                    "release_decision_sha256": review_contexts[platform][
                        "releaseDecisionSha256"
                    ],
                    "release_scope_decision_sha256": decision_shas[platform],
                    "release_version": VERSION,
                    "required_heads": ["avalonia"],
                    "rid": rid,
                },
            }
    if mutate_receipts is not None:
        mutate_receipts(receipts)
    receipt_paths: dict[tuple[str, str], Path] = {}
    for key, payload in receipts.items():
        path = tmp_path / "presentation" / key[0] / f"{key[1]}.json"
        write_json(path, payload, 0o600)
        receipt_paths[key] = path

    signing: dict[str, dict[str, Any]] = {}
    signing_paths: dict[str, Path] = {}
    signing_shas: dict[str, str] = {}
    linux_policy = {
        "memberPath": "signing/policies/AAAAAAAAAAAAAAAA/chummer6-origin.pol",
        "sha256": "a" * 64,
        "sizeBytes": 123,
    }
    linux_keyring = {
        "memberPath": "signing/keyrings/AAAAAAAAAAAAAAAA/chummer6-origin.pgp",
        "sha256": "b" * 64,
        "sizeBytes": 456,
    }
    for platform, (rid, _) in PLATFORMS.items():
        artifact_rows = [
            row for row in state["manifest"]["artifacts"] if row["platform"] == platform
        ]
        artifact = artifact_rows[0]
        base: dict[str, Any] = {
            "contractName": "chummer6-ui.desktop_artifact_signing",
            "contractVersion": 2,
            "generatedAt": "2026-07-26T12:30:00Z",
            "platform": platform,
            "app": "avalonia",
            "rid": rid,
            "releaseChannel": "stable",
            "releaseVersion": VERSION,
            "signingStatus": "pass",
            "notarizationStatus": "pass" if platform == "macos" else None,
            "reason": "",
            "artifacts": [
                {
                    "fileName": row["fileName"],
                    "sha256": row["sha256"],
                    "kind": row["kind"],
                    "signingStatus": "pass",
                    "notarizationStatus": "pass" if platform == "macos" else None,
                }
                for row in artifact_rows
            ],
        }
        if platform == "windows":
            signer = {
                "certificateSha256": "4" * 64,
                "spkiSha256": "5" * 64,
            }
            base.update(
                {
                    "signingBackend": "digicert_keylocker_linux_jsign",
                    "digestAlgorithm": "sha256",
                    "signer": signer,
                    "timestamp": {
                        "protocol": "rfc3161",
                        "url": "http://timestamp.digicert.com",
                        "digestAlgorithm": "sha256",
                        "status": "verified",
                    },
                    "artifactSignatures": [
                        {
                            "artifactFileName": artifact["fileName"],
                            "artifactSha256": artifact["sha256"],
                            "digestAlgorithm": "sha256",
                            "cryptographicVerification": "passed",
                            "signer": signer,
                            "signerChain": {"trusted": True},
                            "timestamp": {
                                "status": "verified",
                                "format": "rfc3161",
                                "digestAlgorithm": "sha256",
                                "chain": {"trusted": True},
                            },
                            "verifier": {
                                "providerIndependent": True,
                                "jsignOutputTrusted": False,
                            },
                        }
                    ],
                    "candidateBindings": [
                        {
                            "artifactRole": "installer",
                            "authenticodeStatus": "pass",
                            "fileName": artifact["fileName"],
                            "sha256": artifact["sha256"],
                            "sizeBytes": artifact["sizeBytes"],
                        },
                        {
                            "artifactRole": "payload",
                            "authenticodeStatus": "not_applicable_payload",
                            "fileName": artifact["payloadFileName"],
                            "sha256": artifact["payloadSha256"],
                            "sizeBytes": artifact["payloadSizeBytes"],
                        },
                    ],
                }
            )
            base["artifacts"] = [
                {
                    "fileName": artifact["fileName"],
                    "sha256": artifact["sha256"],
                    "kind": "installer",
                    "signingStatus": "pass",
                }
            ]
        elif platform == "linux":
            fingerprint = "A" * 40
            signer = {
                "primaryFingerprint": fingerprint,
                "signingFingerprint": fingerprint,
                "longKeyId": fingerprint[-16:],
            }
            base = {
                "app": "avalonia",
                "contractName": "chummer6-ui.desktop_artifact_signing",
                "contractVersion": 2,
                "platform": "linux",
                "rid": "linux-x64",
                "releaseChannel": "stable",
                "releaseVersion": VERSION,
                "generatedAt": "2026-07-26T12:30:00Z",
                "signingStatus": "pass",
                "signingBackend": "debsigs-origin-openpgp",
                "digestAlgorithm": "sha256",
                "signer": signer,
                "artifacts": [
                    {
                        "fileName": artifact["fileName"],
                        "kind": "installer",
                        "sha256": artifact["sha256"],
                        "signingStatus": "pass",
                    }
                ],
                "artifactSignatures": [
                    {
                        "artifactFileName": artifact["fileName"],
                        "artifactSha256": artifact["sha256"],
                        "artifactSizeBytes": artifact["sizeBytes"],
                        "cryptographicVerification": "passed",
                        "digestAlgorithm": "sha256",
                        "signatureType": "origin",
                        "signer": signer,
                        "verifier": {
                            "backend": "debsig-verify",
                            "providerIndependent": True,
                            "positiveExitCode": 0,
                            "policySha256": linux_policy["sha256"],
                            "publicKeyringSha256": linux_keyring["sha256"],
                            "openPgpSignature": {
                                "fingerprint": fingerprint,
                                "primaryFingerprint": fingerprint,
                                "createdAt": "2026-07-26T12:29:00Z",
                                "creationTimestamp": 1785068940,
                                "hashAlgorithm": "sha256",
                            },
                            "tamperNegative": {
                                "mutation": "data-member-byte-flip",
                                "expectedExitCode": 13,
                                "observedExitCode": 13,
                                "status": "rejected",
                            },
                        },
                    }
                ],
                "verificationMaterial": {
                    "policy": linux_policy,
                    "publicKeyring": linux_keyring,
                },
                "tools": {
                    "debsigs": {
                        "binarySha256": "6" * 64,
                        "packageName": "debsigs",
                        "packageVersion": "0.1.26",
                    },
                    "debsigVerify": {
                        "binarySha256": "7" * 64,
                        "packageName": "debsig-verify",
                        "packageVersion": "0.29",
                    },
                    "gpg": {
                        "binarySha256": "8" * 64,
                        "packageName": "gpg",
                        "packageVersion": "2.4.7",
                    },
                    "gpgv": {
                        "binarySha256": "9" * 64,
                        "packageName": "gpgv",
                        "packageVersion": "2.4.7",
                    },
                },
                "source": {
                    "actor": "linux-release",
                    "environment": "linux-deb-signing",
                    "ref": "refs/heads/main",
                    "repository": "ArchonMegalon/chummer6-ui",
                    "runAttempt": "1",
                    "runId": "1001",
                    "sha": "6" * 40,
                    "workflow": (
                        ".github/workflows/linux-native-candidate-export.yml"
                    ),
                },
            }
        signing[platform] = base
    if mutate_signing is not None:
        mutate_signing(signing)
    for platform, payload in signing.items():
        path = tmp_path / "signing" / f"{platform}.receipt.json"
        raw = write_json(path, payload, 0o600)
        signing_paths[platform] = path
        signing_shas[platform] = hashlib.sha256(raw).hexdigest()

    linux_artifact = next(
        row for row in state["manifest"]["artifacts"] if row["platform"] == "linux"
    )
    linux_signing_raw = signing_paths["linux"].read_bytes()
    linux_export = {
        "artifact": {
            "fileName": linux_artifact["fileName"],
            "memberPath": f"files/{linux_artifact['fileName']}",
            "sha256": linux_artifact["sha256"],
            "sizeBytes": linux_artifact["sizeBytes"],
        },
        "contractName": "chummer6-ui.linux-native-candidate-export",
        "contractVersion": 3,
        "generatedAt": "2026-07-26T12:31:00Z",
        "livePredecessorAuthority": {
            "liveReleaseChannelSha256": "c" * 64,
            "nMinusOneReleaseSha256": "d" * 64,
            "selectedTupleSha256": "e" * 64,
        },
        "nonPublishing": True,
        "package": {
            "architecture": "amd64",
            "name": "chummer6-avalonia",
            "version": "6.0.0",
        },
        "publicKeyring": linux_keyring,
        "releaseVersion": VERSION,
        "signingReceipt": {
            "memberPath": "receipts/linux-signing-v2.json",
            "sha256": hashlib.sha256(linux_signing_raw).hexdigest(),
            "sizeBytes": len(linux_signing_raw),
        },
        "source": {
            key: value
            for key, value in signing["linux"]["source"].items()
            if key != "environment"
        },
        "status": "signed",
        "unsignedArtifact": {
            "fileName": linux_artifact["fileName"],
            "memberPath": f"unsigned/{linux_artifact['fileName']}",
            "sha256": "f" * 64,
            "sizeBytes": linux_artifact["sizeBytes"],
        },
        "verificationPolicy": linux_policy,
    }
    linux_export_path = tmp_path / "signing" / "linux-export-v3.json"
    write_json(linux_export_path, linux_export, 0o600)

    mac_artifact = next(
        row for row in state["manifest"]["artifacts"] if row["platform"] == "macos"
    )
    mac_signing_raw = signing_paths["macos"].read_bytes()
    mac_github = {
        "actor": "mac-release",
        "ref": "refs/heads/main",
        "repository": "ArchonMegalon/chummer6-ui",
        "rerunPolicy": "same-actor-only",
        "runAttempt": "1",
        "runId": "1002",
        "sha": "7" * 40,
        "triggeringActor": "mac-release",
        "workflow": ".github/workflows/macos-flagship-evidence.yml",
    }
    mac_live = {
        "liveReleaseChannelSha256": "1" * 64,
        "nMinusOneReleaseSha256": "2" * 64,
        "selectedTupleSha256": "3" * 64,
        "url": "https://chummer.run/downloads/RELEASE_CHANNEL.generated.json",
    }
    mac_authority = {
        "candidateId": "candidate-20260726",
        "contractName": "chummer6-ui.macos-flagship-authority-validation",
        "contractVersion": 2,
        "generationId": "generation-20260726",
        "github": mac_github,
        "livePredecessorAuthority": mac_live,
        "releaseVersion": VERSION,
        "rid": "osx-arm64",
        "status": "pass",
    }
    mac_authority_path = tmp_path / "signing" / "macos-authority.json"
    mac_authority_raw = write_json(mac_authority_path, mac_authority, 0o600)
    notary = {
        "id": "01234567-89ab-cdef-0123-456789abcdef",
        "status": "Accepted",
    }
    notary_path = tmp_path / "signing" / "macos-notary.json"
    notary_raw = write_json(notary_path, notary, 0o600)
    mac_identity = {
        "artifact": {
            "fileName": mac_artifact["fileName"],
            "sha256": mac_artifact["sha256"],
            "sizeBytes": mac_artifact["sizeBytes"],
        },
        "certificate": {
            "developerIdApplicationIdentity": (
                "Developer ID Application: Chummer (ABCDE12345)"
            ),
            "sha256": "a" * 64,
            "spkiSha256": "b" * 64,
            "teamId": "ABCDE12345",
        },
        "contractName": "chummer6-ui.macos-signing-notarization-identity.v1",
        "contractVersion": 1,
        "generatedAtUtc": "2026-07-26T12:32:00Z",
        "notarization": {
            "resultSha256": hashlib.sha256(notary_raw).hexdigest(),
            "status": "Accepted",
            "submissionId": notary["id"],
        },
        "provenance": mac_github,
        "releaseVersion": VERSION,
        "rid": "osx-arm64",
        "signingReceiptSha256": hashlib.sha256(mac_signing_raw).hexdigest(),
        "sourceAuthorityReceiptSha256": hashlib.sha256(
            mac_authority_raw
        ).hexdigest(),
        "status": "pass",
    }
    mac_identity_path = tmp_path / "signing" / "macos-identity.json"
    mac_identity_raw = write_json(mac_identity_path, mac_identity, 0o600)
    mac_aggregate = {
        "candidate": {
            "artifactId": mac_artifact["artifactId"],
            "fileName": mac_artifact["fileName"],
            "sha256": mac_artifact["sha256"],
            "sizeBytes": mac_artifact["sizeBytes"],
        },
        "cleanInstall": {
            "coreStartupReceiptSha256": "4" * 64,
            "gatekeeperAssessment": "pass",
            "installRootClass": "isolated_applications_equivalent",
            "quarantineAssessment": "pass",
            "uninstall": "pass",
        },
        "contractName": "chummer6-ui.macos-flagship-evidence",
        "contractVersion": 3,
        "generatedAtUtc": "2026-07-26T12:33:00Z",
        "github": mac_github,
        "globalCandidateIdentity": {
            "candidateId": "candidate-20260726",
            "generationId": "generation-20260726",
            "previousReleaseVersion": "run-20260725-120000",
            "releaseVersion": VERSION,
            "sourceCommit": mac_github["sha"],
        },
        "inputBindings": {
            "authorityReceiptSha256": hashlib.sha256(
                mac_authority_raw
            ).hexdigest(),
            "cleanStartupReceiptSha256": "7" * 64,
            "completedUpdateStateSha256": "8" * 64,
            "hostedNativeProofConsumptionSha256": "9" * 64,
            "liveReleaseChannelSha256": mac_live[
                "liveReleaseChannelSha256"
            ],
            "manualUpdateStateSha256": "c" * 64,
            "notaryResultSha256": hashlib.sha256(notary_raw).hexdigest(),
            "pendingDeliveryReceiptSha256": "d" * 64,
            "postUpdateStartupReceiptSha256": "e" * 64,
            "predecessorVerificationSha256": "f" * 64,
            "runtimeObservationsSha256": "0" * 64,
            "signingReceiptSha256": hashlib.sha256(mac_signing_raw).hexdigest(),
            "signingIdentityReceiptSha256": hashlib.sha256(
                mac_identity_raw
            ).hexdigest(),
            "stageManifestSha256": "1" * 64,
            "stageOnlyReceiptSha256": "2" * 64,
        },
        "inventorySha256": "5" * 64,
        "livePredecessorAuthority": mac_live,
        "nonPublishing": {
            "countsAsPublicationEvidence": False,
            "evidenceArtifactUploadAllowed": True,
            "publicActivationAttempted": False,
            "publicationAttempted": False,
            "releaseUploadCredentialAccepted": False,
            "releaseUploadAttempted": False,
        },
        "references": {},
        "releaseVersion": VERSION,
        "rid": "osx-arm64",
        "runner": {
            "arch": "arm64",
            "environment": "github-hosted",
            "imageOS": "macos15",
            "imageVersion": "20260726",
            "label": "macos-15",
            "os": "macos",
        },
        "signing": {
            "candidateDmgGatekeeperStatus": "pass",
            "certificateSha256": "a" * 64,
            "certificateSpkiSha256": "b" * 64,
            "developerIdApplicationIdentity": (
                "Developer ID Application: Chummer (ABCDE12345)"
            ),
            "gatekeeperAssessmentsEnabled": True,
            "installedAppGatekeeperStatus": "pass",
            "notarizationStatus": "Accepted",
            "notarySubmissionId": notary["id"],
            "postUpdateAppGatekeeperStatus": "pass",
            "staplerValidationStatus": "pass",
            "signingStatus": "pass",
            "teamId": "ABCDE12345",
        },
        "sourceUnsignedCandidate": {
            "fileName": mac_artifact["fileName"],
            "sha256": "6" * 64,
            "sizeBytes": mac_artifact["sizeBytes"],
        },
        "status": "pass",
        "updateDelivery": {},
    }
    mac_aggregate_path = tmp_path / "signing" / "macos-aggregate.json"
    write_json(mac_aggregate_path, mac_aggregate, 0o600)

    output = tmp_path / "GLOBAL_RELEASE_SCOPE_UNION_VERIFICATION.generated.json"
    artifact_snapshot_root = tmp_path / "artifact-snapshot"
    if precreate_output:
        write_json(output, {"status": "old"})
    command = [
        sys.executable,
        str(SCRIPT),
        "--manifest",
        str(manifest_path),
        "--promotion-evidence",
        str(promotion_path),
        "--files-root",
        str(files_root),
        "--artifact-snapshot-root",
        str(artifact_snapshot_root),
        "--registry-repository",
        str(registry_repository),
        "--expected-release-version",
        VERSION,
    ]
    for platform in PLATFORMS:
        decision_id = decisions[platform]["decisionId"]
        sha = decision_shas[platform]
        command.extend(
            [
                f"--{platform}-decision",
                str(decision_paths[platform]),
                f"--{platform}-decision-sha256",
                sha,
                f"--{platform}-decision-authority",
                f"design://release-scope/{decision_id}/sha256/{sha}",
                f"--{platform}-review-manifest",
                str(review_manifests[platform]),
                f"--{platform}-authority-current",
                str(authority_currents[platform]),
                f"--{platform}-authority-snapshot",
                str(authority_snapshots[platform]),
                f"--{platform}-release-decision",
                str(release_decisions[platform]),
                f"--{platform}-signing-receipt",
                str(signing_paths[platform]),
                f"--{platform}-signing-receipt-sha256",
                signing_shas[platform],
            ]
        )
        for gate in GATES:
            command.extend(
                [
                    f"--{platform}-{gate}-receipt",
                    str(receipt_paths[(platform, gate)]),
                ]
            )
    command.extend(
        [
            "--linux-signed-export-receipt",
            str(linux_export_path),
            "--macos-signing-identity-receipt",
            str(mac_identity_path),
            "--macos-notary-result",
            str(notary_path),
            "--macos-source-authority-receipt",
            str(mac_authority_path),
            "--macos-aggregate-evidence",
            str(mac_aggregate_path),
        ]
    )
    command.extend(["--output", str(output)])
    context = {
        "state": state,
        "registry_repository": registry_repository,
        "registry_commit": registry_commit,
        "manifest": manifest_path,
        "promotion": promotion_path,
        "files_root": files_root,
        "artifact_snapshot_root": artifact_snapshot_root,
        "decisions": decision_paths,
        "review_manifests": review_manifests,
        "authority_currents": authority_currents,
        "authority_snapshots": authority_snapshots,
        "release_decisions": release_decisions,
        "receipts": receipt_paths,
        "signing": signing_paths,
        "linux_export": linux_export_path,
        "mac_identity": mac_identity_path,
        "mac_notary": notary_path,
        "mac_authority": mac_authority_path,
        "mac_aggregate": mac_aggregate_path,
        "command": command,
    }
    if post_materialize is not None:
        post_materialize(context)
    result = subprocess.run(command, capture_output=True, text=True)
    return result, output, context


def test_accepts_only_complete_exact_global_union_and_emits_preparation_receipt(
    tmp_path: Path,
) -> None:
    result, output, context = invoke(tmp_path)
    assert result.returncode == 0, result.stderr
    receipt = json.loads(output.read_text())
    assert receipt["contractName"] == "chummer.release-scope-union-preparation/v1"
    assert receipt["status"] == "prepared"
    assert receipt["authorizesCandidateProduction"] is False
    assert receipt["authorizationStatus"] == (
        "requires_publisher_consumption_receipt"
    )
    assert receipt["verificationPhase"] == "global_candidate_inventory_and_presentation"
    assert receipt["exactIncomingDesktopScope"] == (
        "avalonia:linux:linux-x64,avalonia:macos:osx-arm64,"
        "avalonia:windows:win-x64"
    )
    assert [row["platform"] for row in receipt["scopeDecisions"]] == [
        "linux",
        "macos",
        "windows",
    ]
    assert len(receipt["presentationReceipts"]) == 9
    assert len({row["sha256"] for row in receipt["presentationReceipts"]}) == 9
    assert len(receipt["signingReceipts"]) == 3
    assert receipt["registryCommit"] == context["registry_commit"]
    assert [row["platform"] for row in receipt["reviewAuthorities"]] == [
        "linux",
        "macos",
        "windows",
    ]
    assert len(
        {row["authoritySnapshotSha256"] for row in receipt["reviewAuthorities"]}
    ) == 3
    assert len(receipt["filesRootInventorySha256"]) == 64
    snapshot_root = context["artifact_snapshot_root"]
    snapshot_binding = receipt["artifactSnapshot"]
    assert snapshot_binding["contractName"] == (
        "chummer.release-scope-union-artifact-snapshot/v1"
    )
    assert snapshot_binding["root"] == str(snapshot_root)
    assert snapshot_binding["authorizesCandidateProduction"] is False
    assert snapshot_binding["storagePosture"] == "mutable_audit_snapshot"
    assert snapshot_binding["consumerRequirement"] == (
        "rehash_and_seal_before_publication"
    )
    assert set(path.name for path in snapshot_root.iterdir()) == {
        "objects",
        "ARTIFACT_SNAPSHOT.generated.json",
        "ARTIFACT_SNAPSHOT_COMMIT.generated.json",
    }
    snapshot_manifest_raw = (
        snapshot_root / snapshot_binding["manifestFileName"]
    ).read_bytes()
    snapshot_commit_raw = (
        snapshot_root / snapshot_binding["commitFileName"]
    ).read_bytes()
    assert hashlib.sha256(snapshot_manifest_raw).hexdigest() == (
        snapshot_binding["manifestSha256"]
    )
    assert hashlib.sha256(snapshot_commit_raw).hexdigest() == (
        snapshot_binding["commitSha256"]
    )
    snapshot_manifest = json.loads(snapshot_manifest_raw)
    snapshot_commit = json.loads(snapshot_commit_raw)
    assert snapshot_manifest["status"] == "prepared"
    assert snapshot_manifest["authorizesCandidateProduction"] is False
    assert snapshot_manifest["storagePosture"] == "mutable_audit_snapshot"
    assert snapshot_manifest["consumerRequirement"] == (
        "rehash_and_seal_before_publication"
    )
    assert snapshot_commit["status"] == "committed"
    assert snapshot_commit["authorizesCandidateProduction"] is False
    assert snapshot_commit["authorizationStatus"] == (
        "requires_publisher_consumption_receipt"
    )
    assert snapshot_commit["preparationReceiptFileName"] == output.name
    assert snapshot_commit["snapshotManifestSha256"] == (
        snapshot_binding["manifestSha256"]
    )
    assert snapshot_manifest["transactionId"] == (
        snapshot_commit["transactionId"]
    )
    assert snapshot_commit["transactionId"] == (
        snapshot_binding["transactionId"]
    )
    object_names = {
        path.name
        for path in (snapshot_root / "objects").iterdir()
    }
    assert object_names == {
        row["objectName"]
        for row in snapshot_manifest["artifacts"]
    }
    for row in snapshot_manifest["artifacts"]:
        object_path = snapshot_root / "objects" / row["objectName"]
        assert object_path.stat().st_mode & 0o777 == 0o400
        assert object_path.stat().st_size == row["sizeBytes"]
        assert hashlib.sha256(object_path.read_bytes()).hexdigest() == (
            row["sha256"]
        )
    assert output.stat().st_mode & 0o777 == 0o600
    assert output.read_bytes() == canonical(receipt)


@pytest.mark.parametrize("field", ["releaseVersion", "supportOwner", "approvedBy"])
def test_rejects_cross_decision_authority_drift(tmp_path: Path, field: str) -> None:
    def mutate(state: dict[str, Any]) -> None:
        state["decisions"]["macos"][field] = "drifted-authority"

    result, output, _ = invoke(tmp_path, mutate=mutate)
    assert result.returncode == 1
    assert not output.exists()
    assert "scope" in result.stderr.lower()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("rid", "osx-x64"),
        ("primaryHead", "blazor-desktop"),
        ("fallbackHeads", ["blazor-desktop"]),
        ("artifactAccessClass", "account_required"),
        ("signingRequirement", "preview_unsigned_allowed"),
    ],
)
def test_rejects_any_platform_policy_outside_global_stable_floor(
    tmp_path: Path,
    field: str,
    value: object,
) -> None:
    def mutate(state: dict[str, Any]) -> None:
        state["decisions"]["macos"]["platforms"][0][field] = value

    result, output, _ = invoke(tmp_path, mutate=mutate)
    assert result.returncode == 1
    assert not output.exists()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("status", "draft"),
        ("rolloutState", "promoted_preview"),
        ("supportabilityState", "review_required"),
        ("channel", "preview"),
    ],
)
def test_rejects_manifest_outside_flagship_stable_posture(
    tmp_path: Path,
    field: str,
    value: object,
) -> None:
    def mutate(state: dict[str, Any]) -> None:
        state["manifest"][field] = value

    result, output, _ = invoke(tmp_path, mutate=mutate)
    assert result.returncode == 1
    assert not output.exists()
    assert "manifest" in result.stderr


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("requiredDesktopPlatforms", ["linux", "macos", "windows"]),
        ("requiredDesktopHeads", ["avalonia", "blazor-desktop"]),
        ("missingRequiredPlatforms", ["macos"]),
        ("missingRequiredPlatformHeadPairs", ["avalonia:macos"]),
        ("externalProofRequests", [{"platform": "macos"}]),
        ("complete", False),
    ],
)
def test_rejects_each_incomplete_or_widened_tuple_coverage_claim(
    tmp_path: Path,
    field: str,
    value: object,
) -> None:
    def mutate(state: dict[str, Any]) -> None:
        state["manifest"]["desktopTupleCoverage"][field] = value

    result, output, _ = invoke(tmp_path, mutate=mutate)
    assert result.returncode == 1
    assert "desktopTupleCoverage" in result.stderr
    assert not output.exists()


def test_rejects_promoted_tuple_to_artifact_misbinding(tmp_path: Path) -> None:
    def mutate(state: dict[str, Any]) -> None:
        state["manifest"]["desktopTupleCoverage"]["promotedInstallerTuples"][1][
            "artifactId"
        ] = "avalonia-linux-x64-installer"

    result, output, _ = invoke(tmp_path, mutate=mutate)
    assert result.returncode == 1
    assert not output.exists()


@pytest.mark.parametrize("failure", ["manifest_digest", "manifest_size", "disk_bytes"])
def test_rejects_any_artifact_byte_or_metadata_drift(
    tmp_path: Path,
    failure: str,
) -> None:
    def mutate(state: dict[str, Any]) -> None:
        windows = state["manifest"]["artifacts"][1]
        if failure == "manifest_digest":
            windows["sha256"] = "f" * 64
        elif failure == "manifest_size":
            windows["sizeBytes"] += 1

    def post(context: dict[str, Any]) -> None:
        if failure == "disk_bytes":
            path = context["files_root"] / "chummer-avalonia-win-x64-installer.exe"
            write_bytes(path, b"replaced-after-manifest", 0o644)

    result, output, _ = invoke(tmp_path, mutate=mutate, post_materialize=post)
    assert result.returncode == 1
    assert (
        "bytes disagree with manifest" in result.stderr
        or "promotion evidence does not bind" in result.stderr
    )
    assert not output.exists()


def test_artifact_verification_rechecks_earlier_files_after_later_hashes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_union_module()
    state = candidate_state()
    files_root = tmp_path / "files"
    for name, raw in state["files"].items():
        write_bytes(files_root / name, raw, 0o644)
    first_name = state["manifest"]["artifacts"][0]["fileName"]
    first_path = files_root / first_name
    real_hold = module._hold_stable_file_digest
    hold_count = 0
    raced = False

    def race_earlier_file(
        path: Path,
        label: str,
        **kwargs: object,
    ) -> Any:
        nonlocal hold_count, raced
        held = real_hold(path, label, **kwargs)
        hold_count += 1
        if hold_count == 2:
            original = first_path.read_bytes()
            replacement = (
                (b"x" if original[:1] != b"x" else b"y")
                + original[1:]
            )
            first_path.write_bytes(replacement)
            raced = True
        return held

    monkeypatch.setattr(module, "_hold_stable_file_digest", race_earlier_file)
    with pytest.raises(module.ScopeError, match="changed during held recheck"):
        module._verify_files(state["manifest"], files_root)
    assert raced


def test_post_write_artifact_recheck_removes_receipt_after_late_mutation(
    tmp_path: Path,
) -> None:
    module = load_union_module()
    state = candidate_state()
    files_root = tmp_path / "files"
    for name, raw in state["files"].items():
        write_bytes(files_root / name, raw, 0o644)
    _, _, held_files = module._verify_files(state["manifest"], files_root)
    output_parent = tmp_path / "private-output"
    output_parent.mkdir(mode=0o700)
    output = output_parent / "receipt.json"

    def final_check() -> None:
        for held_file in held_files:
            held_file.recheck()

    try:
        final_check()
        raced_path = files_root / state["manifest"]["artifacts"][0]["fileName"]
        original = raced_path.read_bytes()
        raced_path.write_bytes(
            (b"x" if original[:1] != b"x" else b"y") + original[1:]
        )
        with pytest.raises(
            module.ScopeError,
            match="changed during held recheck",
        ):
            module._write_new(
                output,
                {"status": "pass"},
                post_write_check=final_check,
            )
        assert not output.exists()
    finally:
        for held_file in reversed(held_files):
            held_file.close()


def test_candidate_fifo_is_opened_nonblocking(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_union_module()
    fifo = tmp_path / "candidate.deb"
    os.mkfifo(fifo, mode=0o600)
    real_open = module.os.open
    checked = False

    def assert_nonblocking_open(
        path: object,
        flags: int,
        *args: object,
        **kwargs: object,
    ) -> int:
        nonlocal checked
        if path == fifo.name and "dir_fd" in kwargs:
            assert flags & getattr(os, "O_NONBLOCK", 0)
            checked = True
        return real_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(module.os, "open", assert_nonblocking_open)
    with pytest.raises(
        module.ScopeError,
        match="single-link regular file",
    ):
        module._hold_stable_file_digest(fifo, "candidate FIFO")
    assert checked


@pytest.mark.parametrize("phase", ["initial", "recheck"])
def test_artifact_hash_reads_are_bounded_by_held_size(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    phase: str,
) -> None:
    module = load_union_module()
    path = tmp_path / "candidate.bin"
    write_bytes(path, b"a", 0o600)
    held = (
        module._hold_stable_file_digest(path, "bounded artifact")
        if phase == "recheck"
        else None
    )
    requested_sizes: list[int] = []

    def endless_nonempty_read(_descriptor: int, requested: int) -> bytes:
        requested_sizes.append(requested)
        if len(requested_sizes) > 2:
            raise RuntimeError("read loop was not bounded")
        return b"x" * requested

    monkeypatch.setattr(module.os, "read", endless_nonempty_read)
    try:
        with pytest.raises(
            module.ScopeError,
            match="stable hash|held recheck",
        ):
            if held is None:
                module._hold_stable_file_digest(path, "bounded artifact")
            else:
                held.recheck()
        assert requested_sizes == [2]
    finally:
        if held is not None:
            held.close()


def test_artifact_size_mismatch_is_rejected_before_any_hash_read(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_union_module()
    path = tmp_path / "oversized-candidate.bin"
    with path.open("wb") as stream:
        stream.truncate(8 * 1024 * 1024)
    path.chmod(0o600)
    reads = 0

    def reject_any_read(_descriptor: int, _requested: int) -> bytes:
        nonlocal reads
        reads += 1
        raise AssertionError("mismatched artifact must not be hashed")

    monkeypatch.setattr(module.os, "read", reject_any_read)
    with pytest.raises(module.ScopeError, match="disagree with manifest"):
        module._hold_stable_file_digest(
            path,
            "candidate artifact bytes",
            expected_size=28,
        )
    assert reads == 0


def test_artifact_snapshot_detaches_authorized_bytes_from_live_source_mmap(
    tmp_path: Path,
) -> None:
    module = load_union_module()
    state = candidate_state()
    files_root = tmp_path / "files"
    for name, raw in state["files"].items():
        write_bytes(files_root / name, raw, 0o644)
    first_name = state["manifest"]["artifacts"][0]["fileName"]
    writable = os.open(files_root / first_name, os.O_RDWR)
    mapping = mmap.mmap(
        writable,
        (files_root / first_name).stat().st_size,
    )
    _, inventory_sha256, held = module._verify_files(
        state["manifest"],
        files_root,
    )
    snapshot_root = tmp_path / "artifact-snapshot"
    output = tmp_path / "scope-receipt.json"
    guard = module._materialize_artifact_snapshot(
        root=snapshot_root,
        output=output,
        manifest=state["manifest"],
        held_artifacts=held,
        release_version=VERSION,
        manifest_sha256=hashlib.sha256(
            canonical(state["manifest"])
        ).hexdigest(),
        inventory_sha256=inventory_sha256,
        registry_commit="a" * 40,
    )
    try:
        for snapshot_file in guard.files:
            assert (
                fcntl.fcntl(snapshot_file.descriptor, fcntl.F_GETFL)
                & os.O_ACCMODE
            ) == os.O_RDONLY
        mapping[:8] = b"TAMPERED"
        guard.verify()
        snapshot_manifest = json.loads(
            (
                snapshot_root / "ARTIFACT_SNAPSHOT.generated.json"
            ).read_bytes()
        )
        first_record = next(
            row
            for row in snapshot_manifest["artifacts"]
            if row["sourceFileName"] == first_name
        )
        snapshot_object = (
            snapshot_root
            / "objects"
            / first_record["objectName"]
        )
        assert hashlib.sha256(snapshot_object.read_bytes()).hexdigest() == (
            first_record["sha256"]
        )
        assert (files_root / first_name).read_bytes() != (
            snapshot_object.read_bytes()
        )
    finally:
        guard.close()
        for item in reversed(held):
            item.close()
        mapping.close()
        os.close(writable)


def test_artifact_snapshot_guard_rejects_post_link_object_change(
    tmp_path: Path,
) -> None:
    module = load_union_module()
    state = candidate_state()
    files_root = tmp_path / "files"
    for name, raw in state["files"].items():
        write_bytes(files_root / name, raw, 0o644)
    _, inventory_sha256, held = module._verify_files(
        state["manifest"],
        files_root,
    )
    snapshot_root = tmp_path / "artifact-snapshot"
    guard = module._materialize_artifact_snapshot(
        root=snapshot_root,
        output=tmp_path / "scope-receipt.json",
        manifest=state["manifest"],
        held_artifacts=held,
        release_version=VERSION,
        manifest_sha256=hashlib.sha256(
            canonical(state["manifest"])
        ).hexdigest(),
        inventory_sha256=inventory_sha256,
        registry_commit="b" * 40,
    )
    try:
        object_path = next((snapshot_root / "objects").iterdir())
        object_path.chmod(0o600)
        object_path.write_bytes(b"changed snapshot object\n")
        with pytest.raises(
            module.ScopeError,
            match="release authority changed|snapshot object changed",
        ):
            guard.verify()
    finally:
        guard.close()
        for item in reversed(held):
            item.close()


def test_final_link_boundary_can_only_publish_nonauthorizing_preparation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_union_module()
    state = candidate_state()
    files_root = tmp_path / "files"
    for name, raw in state["files"].items():
        write_bytes(files_root / name, raw, 0o644)
    _, inventory_sha256, held = module._verify_files(
        state["manifest"],
        files_root,
    )
    snapshot_root = tmp_path / "artifact-snapshot"
    output_parent = tmp_path / "private-output"
    output_parent.mkdir(mode=0o700)
    output = output_parent / "preparation.json"
    guard = module._materialize_artifact_snapshot(
        root=snapshot_root,
        output=output,
        manifest=state["manifest"],
        held_artifacts=held,
        release_version=VERSION,
        manifest_sha256=hashlib.sha256(
            canonical(state["manifest"])
        ).hexdigest(),
        inventory_sha256=inventory_sha256,
        registry_commit="c" * 40,
    )
    object_path = next((snapshot_root / "objects").iterdir())
    real_link = module.os.link
    mutated = False

    def link_then_mutate(*args: object, **kwargs: object) -> None:
        nonlocal mutated
        real_link(*args, **kwargs)
        if kwargs.get("dst_dir_fd") is not None:
            destination = args[1]
            if destination == output.name:
                object_path.chmod(0o600)
                object_path.write_bytes(b"changed after final barrier\n")
                mutated = True

    payload = {
        "contractName": "chummer.release-scope-union-preparation/v1",
        "contractVersion": 1,
        "status": "prepared",
        "authorizesCandidateProduction": False,
        "authorizationStatus": "requires_publisher_consumption_receipt",
    }
    monkeypatch.setattr(module.os, "link", link_then_mutate)
    try:
        module._write_new(
            output,
            payload,
            post_write_check=guard.verify,
            mutation_watch=guard.mutation_watch,
        )
        assert mutated
        assert json.loads(output.read_text()) == payload
        assert json.loads(output.read_text())["status"] != "pass"
        assert not json.loads(output.read_text())[
            "authorizesCandidateProduction"
        ]
        with pytest.raises(
            module.ScopeError,
            match="release authority changed|snapshot object changed",
        ):
            guard.verify()
    finally:
        guard.close()
        for item in reversed(held):
            item.close()


def test_complete_uncommitted_snapshot_is_retained_but_nonauthorizing(
    tmp_path: Path,
) -> None:
    module = load_union_module()
    state = candidate_state()
    files_root = tmp_path / "files"
    for name, raw in state["files"].items():
        write_bytes(files_root / name, raw, 0o644)
    _, inventory_sha256, held = module._verify_files(
        state["manifest"],
        files_root,
    )
    snapshot_root = tmp_path / "artifact-snapshot"
    guard = module._materialize_artifact_snapshot(
        root=snapshot_root,
        output=tmp_path / "preparation.json",
        manifest=state["manifest"],
        held_artifacts=held,
        release_version=VERSION,
        manifest_sha256=hashlib.sha256(
            canonical(state["manifest"])
        ).hexdigest(),
        inventory_sha256=inventory_sha256,
        registry_commit="d" * 40,
    )
    try:
        assert snapshot_root.is_dir()
        assert not (tmp_path / "preparation.json").exists()
        snapshot_commit = json.loads(
            (
                snapshot_root
                / "ARTIFACT_SNAPSHOT_COMMIT.generated.json"
            ).read_text()
        )
        assert snapshot_commit["authorizesCandidateProduction"] is False
        assert snapshot_commit["authorizationStatus"] == (
            "requires_publisher_consumption_receipt"
        )
    finally:
        guard.close()
        for item in reversed(held):
            item.close()


@pytest.mark.parametrize("phase", ["partial_objects", "after_snapshot_commit"])
def test_failed_snapshot_publication_retains_nonauthorizing_prefix(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    phase: str,
) -> None:
    module = load_union_module()
    state = candidate_state()
    files_root = tmp_path / "files"
    for name, raw in state["files"].items():
        write_bytes(files_root / name, raw, 0o644)
    _, inventory_sha256, held = module._verify_files(
        state["manifest"],
        files_root,
    )
    snapshot_root = tmp_path / "artifact-snapshot"
    real_link = module.os.link
    link_count = 0

    def fail_snapshot_link(*args: object, **kwargs: object) -> None:
        nonlocal link_count
        link_count += 1
        destination = args[1]
        if phase == "partial_objects" and link_count == 2:
            raise OSError("injected partial object publication failure")
        real_link(*args, **kwargs)
        if (
            phase == "after_snapshot_commit"
            and destination == module.SNAPSHOT_COMMIT_NAME
        ):
            raise OSError("injected post-commit link report failure")

    monkeypatch.setattr(module.os, "link", fail_snapshot_link)
    try:
        with pytest.raises(
            module.ScopeError,
            match="artifact snapshot publication failed",
        ):
            module._materialize_artifact_snapshot(
                root=snapshot_root,
                output=tmp_path / "preparation.json",
                manifest=state["manifest"],
                held_artifacts=held,
                release_version=VERSION,
                manifest_sha256=hashlib.sha256(
                    canonical(state["manifest"])
                ).hexdigest(),
                inventory_sha256=inventory_sha256,
                registry_commit="f" * 40,
            )
        assert snapshot_root.is_dir()
        assert not (tmp_path / "preparation.json").exists()
        snapshot_commit_path = (
            snapshot_root
            / "ARTIFACT_SNAPSHOT_COMMIT.generated.json"
        )
        if snapshot_commit_path.exists():
            snapshot_commit = json.loads(snapshot_commit_path.read_text())
            assert snapshot_commit["authorizesCandidateProduction"] is False
            assert snapshot_commit["authorizationStatus"] == (
                "requires_publisher_consumption_receipt"
            )
    finally:
        for item in reversed(held):
            item.close()


@pytest.mark.parametrize(
    ("phase", "exit_code"),
    [("partial_objects", 91), ("complete_snapshot", 92)],
)
def test_process_death_leaves_only_nonauthorizing_snapshot_prefix(
    tmp_path: Path,
    phase: str,
    exit_code: int,
) -> None:
    module = load_union_module()
    state = candidate_state()
    files_root = tmp_path / "files"
    for name, raw in state["files"].items():
        write_bytes(files_root / name, raw, 0o644)
    _, inventory_sha256, held = module._verify_files(
        state["manifest"],
        files_root,
    )
    snapshot_root = tmp_path / "artifact-snapshot"
    preparation = tmp_path / "preparation.json"
    child = os.fork()
    if child == 0:
        if phase == "partial_objects":
            real_link = module.os.link
            linked = 0

            def exit_after_first_link(
                *args: object,
                **kwargs: object,
            ) -> None:
                nonlocal linked
                real_link(*args, **kwargs)
                linked += 1
                if linked == 1:
                    os._exit(91)

            module.os.link = exit_after_first_link
        module._materialize_artifact_snapshot(
            root=snapshot_root,
            output=preparation,
            manifest=state["manifest"],
            held_artifacts=held,
            release_version=VERSION,
            manifest_sha256=hashlib.sha256(
                canonical(state["manifest"])
            ).hexdigest(),
            inventory_sha256=inventory_sha256,
            registry_commit="1" * 40,
        )
        os._exit(92)
    try:
        _pid, status = os.waitpid(child, 0)
        assert os.waitstatus_to_exitcode(status) == exit_code
        assert snapshot_root.is_dir()
        assert not preparation.exists()
        snapshot_commit_path = (
            snapshot_root
            / "ARTIFACT_SNAPSHOT_COMMIT.generated.json"
        )
        if snapshot_commit_path.exists():
            snapshot_commit = json.loads(snapshot_commit_path.read_text())
            assert snapshot_commit["authorizesCandidateProduction"] is False
            assert snapshot_commit["authorizationStatus"] == (
                "requires_publisher_consumption_receipt"
            )
    finally:
        for item in reversed(held):
            item.close()


@pytest.mark.parametrize(
    ("platform", "field", "value"),
    [
        ("linux", "promotionStatus", "fail"),
        ("windows", "signingStatus", "unsigned"),
        ("macos", "notarizationStatus", "skipped_preview"),
    ],
)
def test_rejects_incomplete_promotion_signing_or_notarization(
    tmp_path: Path,
    platform: str,
    field: str,
    value: str,
) -> None:
    def mutate(state: dict[str, Any]) -> None:
        rid = PLATFORMS[platform][0]
        row = next(
            item for item in state["promotion"]["artifacts"] if rid in item["artifactId"]
        )
        row[field] = value

    result, output, _ = invoke(tmp_path, mutate=mutate)
    assert result.returncode == 1
    assert not output.exists()


@pytest.mark.parametrize(
    ("platform", "field", "value"),
    [
        ("linux", "signingStatus", "unsigned"),
        ("windows", "releaseVersion", "other-release"),
        ("macos", "notarizationStatus", "skipped_preview"),
        ("macos", "platform", "linux"),
    ],
)
def test_rejects_forged_or_mismatched_platform_signing_receipts(
    tmp_path: Path,
    platform: str,
    field: str,
    value: object,
) -> None:
    def mutate_signing(signing: dict[str, dict[str, Any]]) -> None:
        signing[platform][field] = value

    result, output, _ = invoke(tmp_path, mutate_signing=mutate_signing)
    assert result.returncode == 1
    assert f"{platform} signing receipt" in result.stderr
    assert not output.exists()


def test_rejects_signing_receipt_artifact_digest_not_bound_to_manifest(
    tmp_path: Path,
) -> None:
    def mutate_signing(signing: dict[str, dict[str, Any]]) -> None:
        signing["windows"]["artifacts"][0]["sha256"] = "f" * 64

    result, output, _ = invoke(tmp_path, mutate_signing=mutate_signing)
    assert result.returncode == 1
    assert "does not bind exactly one primary manifest artifact" in result.stderr
    assert not output.exists()


def test_rejects_signed_platform_claim_without_per_artifact_signing(
    tmp_path: Path,
) -> None:
    def mutate_signing(signing: dict[str, dict[str, Any]]) -> None:
        signing["linux"]["artifacts"][0]["signingStatus"] = "unsigned"

    result, output, _ = invoke(tmp_path, mutate_signing=mutate_signing)
    assert result.returncode == 1
    assert "artifact" in result.stderr
    assert "is not signed" in result.stderr
    assert not output.exists()


def test_rejects_signing_receipt_digest_drift_from_approved_pin(tmp_path: Path) -> None:
    def post(context: dict[str, Any]) -> None:
        path = context["signing"]["windows"]
        payload = json.loads(path.read_text())
        payload["reason"] = "receipt bytes replaced after approval"
        write_json(path, payload, 0o600)

    result, output, _ = invoke(tmp_path, post_materialize=post)
    assert result.returncode == 1
    assert "windows signing receipt SHA-256 does not match" in result.stderr
    assert not output.exists()


def test_matching_caller_digest_cannot_make_plain_pass_json_authoritative(
    tmp_path: Path,
) -> None:
    def mutate_signing(signing: dict[str, dict[str, Any]]) -> None:
        signing["windows"] = {
            "contractName": "chummer6-ui.desktop_artifact_signing",
            "platform": "windows",
            "app": "avalonia",
            "rid": "win-x64",
            "releaseVersion": VERSION,
            "signingStatus": "pass",
            "artifacts": [],
        }

    result, output, _ = invoke(tmp_path, mutate_signing=mutate_signing)
    assert result.returncode == 1
    assert "contractVersion must be exactly 2" in result.stderr
    assert not output.exists()


def test_accepts_safe_extra_windows_portable_row_while_binding_primary_candidate(
    tmp_path: Path,
) -> None:
    def mutate_signing(signing: dict[str, dict[str, Any]]) -> None:
        receipt = signing["windows"]
        portable_name = "chummer-avalonia-win-x64.exe"
        portable_sha = "e" * 64
        receipt["artifacts"].append(
            {
                "fileName": portable_name,
                "sha256": portable_sha,
                "kind": "portable",
                "signingStatus": "pass",
            }
        )
        signature = json.loads(
            json.dumps(receipt["artifactSignatures"][0])
        )
        signature["artifactFileName"] = portable_name
        signature["artifactSha256"] = portable_sha
        receipt["artifactSignatures"].append(signature)

    result, output, _ = invoke(tmp_path, mutate_signing=mutate_signing)
    assert result.returncode == 0, result.stderr
    assert output.exists()


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("contractVersion",), 1),
        (("signingBackend",), "self_attested"),
        (("artifactSignatures", 0, "cryptographicVerification"), "claimed"),
        (("artifactSignatures", 0, "signerChain", "trusted"), False),
        (("artifactSignatures", 0, "timestamp", "chain", "trusted"), False),
        (("artifactSignatures", 0, "verifier", "providerIndependent"), False),
        (("artifactSignatures", 0, "verifier", "jsignOutputTrusted"), True),
        (("timestamp", "protocol"), "legacy"),
        (("candidateBindings", 1, "sha256"), "f" * 64),
    ],
)
def test_rejects_each_forged_windows_v2_crypto_authority_field(
    tmp_path: Path,
    path: tuple[str | int, ...],
    value: object,
) -> None:
    def mutate_signing(signing: dict[str, dict[str, Any]]) -> None:
        target: Any = signing["windows"]
        for component in path[:-1]:
            target = target[component]
        target[path[-1]] = value

    result, output, _ = invoke(tmp_path, mutate_signing=mutate_signing)
    assert result.returncode == 1
    assert "windows signing receipt" in result.stderr
    assert not output.exists()


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("signer", "primaryFingerprint"), "B" * 40),
        (
            (
                "artifactSignatures",
                0,
                "verifier",
                "tamperNegative",
                "status",
            ),
            "claimed",
        ),
        (
            ("artifactSignatures", 0, "verifier", "providerIndependent"),
            False,
        ),
        (("verificationMaterial", "publicKeyring", "sha256"), "c" * 64),
        (("tools", "debsigVerify", "packageVersion"), "unreviewed"),
        (("source", "workflow"), ".github/workflows/unprotected.yml"),
    ],
)
def test_rejects_each_forged_linux_v2_crypto_authority_field(
    tmp_path: Path,
    path: tuple[str | int, ...],
    value: object,
) -> None:
    def mutate_signing(signing: dict[str, dict[str, Any]]) -> None:
        target: Any = signing["linux"]
        for component in path[:-1]:
            target = target[component]
        target[path[-1]] = value

    result, output, _ = invoke(tmp_path, mutate_signing=mutate_signing)
    assert result.returncode == 1
    assert "linux signing receipt" in result.stderr
    assert not output.exists()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("status", "unsigned"),
        ("nonPublishing", False),
        ("contractVersion", 2),
    ],
)
def test_rejects_forged_linux_signed_export_authority(
    tmp_path: Path,
    field: str,
    value: object,
) -> None:
    def post(context: dict[str, Any]) -> None:
        path = context["linux_export"]
        payload = json.loads(path.read_text())
        payload[field] = value
        write_json(path, payload, 0o600)

    result, output, _ = invoke(tmp_path, post_materialize=post)
    assert result.returncode == 1
    assert "linux signed export" in result.stderr
    assert not output.exists()


@pytest.mark.parametrize(
    ("target", "field", "value"),
    [
        ("aggregate", "staplerValidationStatus", "claimed"),
        ("aggregate", "candidateDmgGatekeeperStatus", "claimed"),
        ("identity", "teamId", "BAD"),
        ("notary", "status", "Rejected"),
        ("authority", "workflow", ".github/workflows/unprotected.yml"),
    ],
)
def test_rejects_forged_macos_identity_notary_staple_or_provenance(
    tmp_path: Path,
    target: str,
    field: str,
    value: object,
) -> None:
    def post(context: dict[str, Any]) -> None:
        if target == "aggregate":
            path = context["mac_aggregate"]
            payload = json.loads(path.read_text())
            payload["signing"][field] = value
        elif target == "identity":
            path = context["mac_identity"]
            payload = json.loads(path.read_text())
            payload["certificate"][field] = value
        elif target == "notary":
            path = context["mac_notary"]
            payload = json.loads(path.read_text())
            payload[field] = value
        else:
            path = context["mac_authority"]
            payload = json.loads(path.read_text())
            payload["github"][field] = value
        write_json(path, payload, 0o600)

    result, output, _ = invoke(tmp_path, post_materialize=post)
    assert result.returncode == 1
    assert "macos" in result.stderr
    assert not output.exists()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("releaseVersion", "other-release"),
        ("manifestSha256", "f" * 64),
    ],
)
def test_rejects_replayed_or_unbound_promotion_evidence(
    tmp_path: Path,
    field: str,
    value: str,
) -> None:
    def mutate(state: dict[str, Any]) -> None:
        state["promotion"][field] = value

    result, output, _ = invoke(tmp_path, mutate=mutate)
    assert result.returncode == 1
    assert "promotion evidence" in result.stderr
    assert not output.exists()


def test_rejects_promotion_artifact_digest_replay(tmp_path: Path) -> None:
    def mutate(state: dict[str, Any]) -> None:
        state["promotion"]["artifacts"][0]["artifactSha256"] = "f" * 64

    result, output, _ = invoke(tmp_path, mutate=mutate)
    assert result.returncode == 1
    assert "promotion evidence does not bind" in result.stderr
    assert not output.exists()


def test_rejects_registry_head_substitution_and_dirty_release_source(
    tmp_path: Path,
) -> None:
    def post(context: dict[str, Any]) -> None:
        source = (
            context["registry_repository"]
            / "scripts/release/promote_public_stable_release_channel.sh"
        )
        source.write_text("dirty release source\n", encoding="utf-8")

    result, output, _ = invoke(tmp_path, post_materialize=post)
    assert result.returncode == 1
    assert "release producer paths must be clean" in result.stderr
    assert not output.exists()


@pytest.mark.parametrize(
    "index_flag",
    ("--assume-unchanged", "--skip-worktree"),
)
def test_rejects_index_flags_hiding_dirty_release_source(
    tmp_path: Path,
    index_flag: str,
) -> None:
    def post(context: dict[str, Any]) -> None:
        repository = context["registry_repository"]
        relative = REGISTRY_PROTECTED_PATHS[0]
        subprocess.run(
            [
                "/usr/bin/git",
                "-C",
                str(repository),
                "update-index",
                index_flag,
                "--",
                relative,
            ],
            check=True,
        )
        (repository / relative).write_text(
            "index flag hidden replacement\n",
            encoding="utf-8",
        )

    result, output, _ = invoke(tmp_path, post_materialize=post)
    assert result.returncode == 1
    assert "release producer paths must be clean" in result.stderr
    assert not output.exists()


def test_rejects_hardlinked_release_source(tmp_path: Path) -> None:
    def post(context: dict[str, Any]) -> None:
        repository = context["registry_repository"]
        source = repository / REGISTRY_PROTECTED_PATHS[0]
        os.link(source, repository / "protected-source-hardlink")

    result, output, _ = invoke(tmp_path, post_materialize=post)
    assert result.returncode == 1
    assert "must be a single-link regular file" in result.stderr
    assert not output.exists()


def test_registry_raw_comparison_ignores_attributes_and_filters(
    tmp_path: Path,
) -> None:
    marker = tmp_path / "untrusted-filter-executed"
    hook = tmp_path / "untrusted-filter"
    write_bytes(
        hook,
        (
            "#!/bin/sh\n"
            f"printf touched > '{marker}'\n"
            "cat\n"
        ).encode(),
        0o700,
    )

    def post(context: dict[str, Any]) -> None:
        repository = context["registry_repository"]
        relative = REGISTRY_PROTECTED_PATHS[0]
        subprocess.run(
            [
                "/usr/bin/git",
                "-C",
                str(repository),
                "update-index",
                "--assume-unchanged",
                "--",
                relative,
            ],
            check=True,
        )
        write_bytes(
            repository / ".git/info/attributes",
            b"scripts/release/* filter=release diff=release\n",
            0o600,
        )
        for key in (
            "filter.release.clean",
            "filter.release.smudge",
            "diff.release.command",
        ):
            subprocess.run(
                [
                    "/usr/bin/git",
                    "-C",
                    str(repository),
                    "config",
                    key,
                    str(hook),
                ],
                check=True,
            )
        (repository / relative).write_text(
            "attribute-filter hidden replacement\n",
            encoding="utf-8",
        )

    result, output, _ = invoke(tmp_path / "fixture", post_materialize=post)
    assert result.returncode == 1
    assert "release producer paths must be clean" in result.stderr
    assert not output.exists()
    assert not marker.exists()


def test_registry_raw_comparison_ignores_replace_refs(tmp_path: Path) -> None:
    malicious_bytes = b"replacement-ref release producer\n"

    def post(context: dict[str, Any]) -> None:
        repository = context["registry_repository"]
        original_commit = context["registry_commit"]
        relative = REGISTRY_PROTECTED_PATHS[0]
        (repository / relative).write_bytes(malicious_bytes)
        subprocess.run(
            ["/usr/bin/git", "-C", str(repository), "add", "--", relative],
            check=True,
        )
        subprocess.run(
            [
                "/usr/bin/git",
                "-C",
                str(repository),
                "-c",
                "user.name=Release Fixture",
                "-c",
                "user.email=fixture@example.invalid",
                "commit",
                "-q",
                "-m",
                "untrusted replacement commit",
            ],
            check=True,
        )
        replacement_commit = subprocess.run(
            ["/usr/bin/git", "-C", str(repository), "rev-parse", "HEAD"],
            check=True,
            text=True,
            stdout=subprocess.PIPE,
        ).stdout.strip()
        subprocess.run(
            [
                "/usr/bin/git",
                "-C",
                str(repository),
                "update-ref",
                "HEAD",
                original_commit,
            ],
            check=True,
        )
        subprocess.run(
            [
                "/usr/bin/git",
                "-C",
                str(repository),
                "replace",
                original_commit,
                replacement_commit,
            ],
            check=True,
        )
        replaced_blob = subprocess.run(
            [
                "/usr/bin/git",
                "-C",
                str(repository),
                "cat-file",
                "blob",
                f"HEAD:{relative}",
            ],
            check=True,
            stdout=subprocess.PIPE,
        ).stdout
        assert replaced_blob == malicious_bytes

    result, output, _ = invoke(tmp_path, post_materialize=post)
    assert result.returncode == 1
    assert "release producer paths must be clean" in result.stderr
    assert not output.exists()


def test_registry_inspection_ignores_path_and_global_git_config_injection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    marker = tmp_path / "untrusted-git-executed"
    fake_bin = tmp_path / "fake-bin"
    fake_git = fake_bin / "git"
    hook = tmp_path / "untrusted-git-hook"
    write_bytes(
        fake_git,
        (
            "#!/bin/sh\n"
            f"printf touched > {marker}\n"
            'exec /usr/bin/git "$@"\n'
        ).encode(),
        0o700,
    )
    write_bytes(
        hook,
        (
            "#!/bin/sh\n"
            f"printf touched > {marker}\n"
            "exit 1\n"
        ).encode(),
        0o700,
    )
    global_config = tmp_path / "untrusted-gitconfig"
    write_bytes(
        global_config,
        (
            "[core]\n"
            f"\tfsmonitor = {hook}\n"
            "[diff]\n"
            f"\texternal = {hook}\n"
        ).encode(),
        0o600,
    )

    def post(_: dict[str, Any]) -> None:
        monkeypatch.setenv("PATH", f"{fake_bin}:{os.environ.get('PATH', '')}")
        monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(global_config))

    result, output, _ = invoke(tmp_path / "fixture", post_materialize=post)
    assert result.returncode == 0, result.stderr
    assert output.is_file()
    assert not marker.exists()


def test_registry_inspection_holds_and_rechecks_checkout_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_union_module()
    repository = tmp_path / "registry"
    expected_commit = create_registry_fixture(repository)
    real_popen = module.subprocess.Popen
    call_count = 0

    def race_after_first_git(*args: object, **kwargs: object) -> Any:
        nonlocal call_count
        call_count += 1
        process = real_popen(*args, **kwargs)
        if call_count != 1:
            return process

        def replace_checkout() -> None:
            repository.rename(tmp_path / "registry-held-original")
            repository.mkdir()

        return ProcessAfterWait(process, replace_checkout)

    monkeypatch.setattr(module.subprocess, "Popen", race_after_first_git)
    with pytest.raises(module.ScopeError, match="changed during Git inspection"):
        module._verify_registry_checkout(repository, expected_commit)


def test_registry_inspection_rejects_subpath_replacement_during_comparison(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_union_module()
    repository = tmp_path / "registry"
    expected_commit = create_registry_fixture(repository)
    real_popen = module.subprocess.Popen
    swapped = False

    def swap_release_subpath(*args: object, **kwargs: object) -> Any:
        nonlocal swapped
        command = args[0] if args else kwargs.get("args")
        if (
            not swapped
            and isinstance(command, list)
            and "cat-file" in command
            and "blob" in command
        ):
            release_directory = repository / "scripts/release"
            release_directory.rename(
                repository / "scripts/release-held-original"
            )
            release_directory.mkdir()
            write_bytes(
                release_directory
                / "promote_public_stable_release_channel.sh",
                b"replacement release producer\n",
                0o644,
            )
            swapped = True
        return real_popen(*args, **kwargs)

    monkeypatch.setattr(module.subprocess, "Popen", swap_release_subpath)
    with pytest.raises(
        module.ScopeError,
        match="changed during protected source comparison",
    ):
        module._verify_registry_checkout(repository, expected_commit)


def test_registry_inspection_rechecks_earlier_producers_after_later_reads(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_union_module()
    repository = tmp_path / "registry"
    expected_commit = create_registry_fixture(repository)
    first_source = repository / REGISTRY_PROTECTED_PATHS[0]
    real_popen = module.subprocess.Popen
    blob_reads = 0
    raced = False

    def mutate_first_source_during_second_blob(
        *args: object,
        **kwargs: object,
    ) -> Any:
        nonlocal blob_reads, raced
        command = args[0] if args else kwargs.get("args")
        process = real_popen(*args, **kwargs)
        if (
            isinstance(command, list)
            and len(command) >= 3
            and command[-3] == "cat-file"
            and command[-2] == "blob"
        ):
            blob_reads += 1
            if blob_reads == 2:
                original = first_source.read_bytes()
                first_source.write_bytes(
                    (b"x" if original[:1] != b"x" else b"y")
                    + original[1:]
                )
                raced = True
        return process

    monkeypatch.setattr(
        module.subprocess,
        "Popen",
        mutate_first_source_during_second_blob,
    )
    with pytest.raises(
        module.ScopeError,
        match="changed during protected source comparison",
    ):
        module._verify_registry_checkout(repository, expected_commit)
    assert raced


def test_registry_comparison_cannot_switch_head_for_blob_reads_and_restore(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_union_module()
    repository = tmp_path / "registry"
    expected_commit = create_registry_fixture(repository)
    relative = REGISTRY_PROTECTED_PATHS[0]
    (repository / relative).write_bytes(b"malicious temporal producer\n")
    subprocess.run(
        ["/usr/bin/git", "-C", str(repository), "add", "--", relative],
        check=True,
    )
    subprocess.run(
        [
            "/usr/bin/git",
            "-C",
            str(repository),
            "-c",
            "user.name=Release Fixture",
            "-c",
            "user.email=fixture@example.invalid",
            "commit",
            "-q",
            "-m",
            "temporal substitution",
        ],
        check=True,
    )
    malicious_commit = subprocess.run(
        ["/usr/bin/git", "-C", str(repository), "rev-parse", "HEAD"],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    ).stdout.strip()
    subprocess.run(
        [
            "/usr/bin/git",
            "-C",
            str(repository),
            "update-ref",
            "HEAD",
            expected_commit,
        ],
        check=True,
    )
    subprocess.run(
        [
            "/usr/bin/git",
            "-C",
            str(repository),
            "reset",
            "-q",
            "--mixed",
            expected_commit,
        ],
        check=True,
    )
    assert (repository / relative).read_bytes() == b"malicious temporal producer\n"

    real_popen = module.subprocess.Popen
    switched = False
    restored = False

    def switch_and_restore_around_git(
        *args: object,
        **kwargs: object,
    ) -> Any:
        nonlocal switched, restored
        command = args[0] if args else kwargs.get("args")
        process = real_popen(*args, **kwargs)
        if (
            not switched
            and isinstance(command, list)
            and command[-3:] == ["rev-parse", "--verify", "HEAD^{commit}"]
        ):
            def switch_head() -> None:
                nonlocal switched
                subprocess.run(
                    [
                        "/usr/bin/git",
                        "-C",
                        str(repository),
                        "update-ref",
                        "HEAD",
                        malicious_commit,
                    ],
                    check=True,
                )
                switched = True

            return ProcessAfterWait(process, switch_head)
        if (
            switched
            and not restored
            and isinstance(command, list)
            and "cat-file" in command
            and "blob" in command
        ):
            def restore_head() -> None:
                nonlocal restored
                subprocess.run(
                    [
                        "/usr/bin/git",
                        "-C",
                        str(repository),
                        "update-ref",
                        "HEAD",
                        expected_commit,
                    ],
                    check=True,
                )
                restored = True

            return ProcessAfterWait(process, restore_head)
        return process

    monkeypatch.setattr(
        module.subprocess,
        "Popen",
        switch_and_restore_around_git,
    )
    with pytest.raises(
        module.ScopeError,
        match="release producer paths must be clean",
    ):
        module._verify_registry_checkout(repository, expected_commit)
    assert switched
    assert restored
    assert (
        subprocess.run(
            ["/usr/bin/git", "-C", str(repository), "rev-parse", "HEAD"],
            check=True,
            text=True,
            stdout=subprocess.PIPE,
        ).stdout.strip()
        == expected_commit
    )


def test_registry_inspection_holds_and_rechecks_absolute_parent_chain(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_union_module()
    authority = tmp_path / "authority"
    repository = authority / "registry"
    expected_commit = create_registry_fixture(repository)
    real_popen = module.subprocess.Popen
    swapped = False

    def swap_parent_after_first_git(*args: object, **kwargs: object) -> Any:
        nonlocal swapped
        process = real_popen(*args, **kwargs)
        if swapped:
            return process

        def replace_parent() -> None:
            nonlocal swapped
            authority.rename(tmp_path / "authority-held-original")
            authority.mkdir()
            (authority / "registry").mkdir()
            swapped = True

        return ProcessAfterWait(process, replace_parent)

    monkeypatch.setattr(
        module.subprocess,
        "Popen",
        swap_parent_after_first_git,
    )
    with pytest.raises(module.ScopeError, match="changed during Git inspection"):
        module._verify_registry_checkout(repository, expected_commit)
    assert swapped


@pytest.mark.parametrize("object_kind", ["commit", "tree"])
def test_registry_inspection_raw_rehashes_objects_mutated_after_fsck(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    object_kind: str,
) -> None:
    module = load_union_module()
    repository = tmp_path / "registry"
    expected_commit = create_registry_fixture(repository)
    if object_kind == "commit":
        object_id = expected_commit
    else:
        object_id = subprocess.run(
            [
                "/usr/bin/git",
                "-C",
                str(repository),
                "rev-parse",
                f"{expected_commit}^{{tree}}",
            ],
            check=True,
            text=True,
            stdout=subprocess.PIPE,
        ).stdout.strip()
    object_path = (
        repository / ".git" / "objects" / object_id[:2] / object_id[2:]
    )
    real_popen = module.subprocess.Popen
    mutated = False

    def mutate_object_after_fsck(*args: object, **kwargs: object) -> Any:
        nonlocal mutated
        command = args[0] if args else kwargs.get("args")
        process = real_popen(*args, **kwargs)
        if (
            not mutated
            and isinstance(command, list)
            and "fsck" in command
        ):
            def corrupt_object() -> None:
                nonlocal mutated
                inflated = zlib.decompress(object_path.read_bytes())
                header, content = inflated.split(b"\0", 1)
                replacement = content[:-1] + bytes([content[-1] ^ 1])
                object_path.chmod(0o600)
                object_path.write_bytes(
                    zlib.compress(header + b"\0" + replacement)
                )
                object_path.chmod(0o444)
                mutated = True

            return ProcessAfterWait(process, corrupt_object)
        return process

    monkeypatch.setattr(
        module.subprocess,
        "Popen",
        mutate_object_after_fsck,
    )
    with pytest.raises(module.ScopeError, match="Git object"):
        module._verify_registry_checkout(repository, expected_commit)
    assert mutated


def test_registry_guard_rereads_reviewed_object_closure(
    tmp_path: Path,
) -> None:
    module = load_union_module()
    repository = tmp_path / "registry"
    expected_commit = create_registry_fixture(repository)
    tree_id = subprocess.run(
        [
            "/usr/bin/git",
            "-C",
            str(repository),
            "rev-parse",
            f"{expected_commit}^{{tree}}",
        ],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    ).stdout.strip()
    object_path = (
        repository / ".git" / "objects" / tree_id[:2] / tree_id[2:]
    )
    guard = module._verify_registry_checkout(repository, expected_commit)
    try:
        inflated = zlib.decompress(object_path.read_bytes())
        header, content = inflated.split(b"\0", 1)
        replacement = content[:-1] + bytes([content[-1] ^ 1])
        object_path.chmod(0o600)
        object_path.write_bytes(
            zlib.compress(header + b"\0" + replacement)
        )
        object_path.chmod(0o444)
        with pytest.raises(
            module.ScopeError,
            match="Git object|release authority changed",
        ):
            guard.verify()
    finally:
        guard.close()


def test_registry_guard_preserves_unrelated_reachable_loose_object(
    tmp_path: Path,
) -> None:
    module = load_union_module()
    repository = tmp_path / "registry"
    create_registry_fixture(repository)
    unrelated = repository / "reachable-unrelated.bin"
    write_bytes(unrelated, b"reachable but not a producer\n", 0o644)
    subprocess.run(
        [
            "/usr/bin/git",
            "-C",
            str(repository),
            "add",
            "--",
            unrelated.name,
        ],
        check=True,
    )
    subprocess.run(
        [
            "/usr/bin/git",
            "-C",
            str(repository),
            "-c",
            "user.name=Release Fixture",
            "-c",
            "user.email=fixture@example.invalid",
            "commit",
            "-q",
            "-m",
            "add reachable non-producer",
        ],
        check=True,
    )
    expected_commit = subprocess.run(
        ["/usr/bin/git", "-C", str(repository), "rev-parse", "HEAD"],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    ).stdout.strip()
    object_id = subprocess.run(
        [
            "/usr/bin/git",
            "-C",
            str(repository),
            "rev-parse",
            f"HEAD:{unrelated.name}",
        ],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    ).stdout.strip()
    object_path = (
        repository / ".git" / "objects" / object_id[:2] / object_id[2:]
    )
    guard = module._verify_registry_checkout(repository, expected_commit)
    try:
        inflated = zlib.decompress(object_path.read_bytes())
        header, content = inflated.split(b"\0", 1)
        replacement = content[:-1] + bytes([content[-1] ^ 1])
        object_path.chmod(0o600)
        object_path.write_bytes(
            zlib.compress(header + b"\0" + replacement)
        )
        object_path.chmod(0o444)
        with pytest.raises(
            module.ScopeError,
            match="Git object graph|release authority changed",
        ):
            guard.verify()
    finally:
        guard.close()


def test_registry_guard_detects_git_object_change_and_restore_aba(
    tmp_path: Path,
) -> None:
    module = load_union_module()
    repository = tmp_path / "registry"
    expected_commit = create_registry_fixture(repository)
    tree_id = subprocess.run(
        [
            "/usr/bin/git",
            "-C",
            str(repository),
            "rev-parse",
            f"{expected_commit}^{{tree}}",
        ],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    ).stdout.strip()
    object_path = (
        repository / ".git" / "objects" / tree_id[:2] / tree_id[2:]
    )
    original = object_path.read_bytes()
    guard = module._verify_registry_checkout(repository, expected_commit)
    try:
        inflated = zlib.decompress(original)
        header, content = inflated.split(b"\0", 1)
        replacement = content[:-1] + bytes([content[-1] ^ 1])
        object_path.chmod(0o600)
        object_path.write_bytes(
            zlib.compress(header + b"\0" + replacement)
        )
        object_path.write_bytes(original)
        object_path.chmod(0o444)
        with pytest.raises(
            module.ScopeError,
            match="release authority changed during receipt commit",
        ):
            guard.verify()
    finally:
        guard.close()


def test_registry_inspection_rejects_symlink_mode_with_matching_regular_bytes(
    tmp_path: Path,
) -> None:
    module = load_union_module()
    repository = tmp_path / "registry"
    create_registry_fixture(repository)
    relative = REGISTRY_PROTECTED_PATHS[0]
    object_id = subprocess.run(
        [
            "/usr/bin/git",
            "-C",
            str(repository),
            "rev-parse",
            f"HEAD:{relative}",
        ],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    ).stdout.strip()
    subprocess.run(
        [
            "/usr/bin/git",
            "-C",
            str(repository),
            "update-index",
            "--cacheinfo",
            "120000",
            object_id,
            relative,
        ],
        check=True,
    )
    subprocess.run(
        [
            "/usr/bin/git",
            "-C",
            str(repository),
            "-c",
            "user.name=Release Fixture",
            "-c",
            "user.email=fixture@example.invalid",
            "commit",
            "-q",
            "-m",
            "symlink-mode substitution",
        ],
        check=True,
    )
    expected_commit = subprocess.run(
        ["/usr/bin/git", "-C", str(repository), "rev-parse", "HEAD"],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    ).stdout.strip()
    assert stat.S_ISREG((repository / relative).lstat().st_mode)
    with pytest.raises(
        module.ScopeError,
        match="source tree mode is not regular",
    ):
        module._verify_registry_checkout(repository, expected_commit)


def test_registry_inspection_rejects_executable_bit_drift(
    tmp_path: Path,
) -> None:
    module = load_union_module()
    repository = tmp_path / "registry"
    expected_commit = create_registry_fixture(repository)
    (repository / REGISTRY_PROTECTED_PATHS[0]).chmod(0o755)
    with pytest.raises(
        module.ScopeError,
        match="release producer paths must be clean",
    ):
        module._verify_registry_checkout(repository, expected_commit)


def test_registry_inspection_matches_git_owner_execute_semantics(
    tmp_path: Path,
) -> None:
    module = load_union_module()
    repository = tmp_path / "registry"
    create_registry_fixture(repository)
    source = repository / REGISTRY_PROTECTED_PATHS[0]
    source.chmod(0o755)
    subprocess.run(
        [
            "/usr/bin/git",
            "-C",
            str(repository),
            "add",
            "--",
            REGISTRY_PROTECTED_PATHS[0],
        ],
        check=True,
    )
    subprocess.run(
        [
            "/usr/bin/git",
            "-C",
            str(repository),
            "-c",
            "user.name=Release Fixture",
            "-c",
            "user.email=fixture@example.invalid",
            "commit",
            "-q",
            "-m",
            "review executable producer",
        ],
        check=True,
    )
    expected_commit = subprocess.run(
        ["/usr/bin/git", "-C", str(repository), "rev-parse", "HEAD"],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    ).stdout.strip()
    source.chmod(0o641)
    status = subprocess.run(
        ["/usr/bin/git", "-C", str(repository), "status", "--porcelain"],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    ).stdout
    assert status
    with pytest.raises(
        module.ScopeError,
        match="release producer paths must be clean",
    ):
        module._verify_registry_checkout(repository, expected_commit)


def test_registry_inspection_supports_held_packed_symbolic_head(
    tmp_path: Path,
) -> None:
    module = load_union_module()
    repository = tmp_path / "registry"
    expected_commit = create_registry_fixture(repository)
    symbolic_name = subprocess.run(
        ["/usr/bin/git", "-C", str(repository), "symbolic-ref", "HEAD"],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    ).stdout.strip()
    subprocess.run(
        ["/usr/bin/git", "-C", str(repository), "pack-refs", "--all"],
        check=True,
    )
    loose_ref = repository / ".git" / symbolic_name
    assert not loose_ref.exists()
    guard = module._verify_registry_checkout(repository, expected_commit)
    try:
        guard.verify()
    finally:
        guard.close()


def test_registry_protected_fifo_is_opened_nonblocking(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_union_module()
    repository = tmp_path / "registry"
    expected_commit = create_registry_fixture(repository)
    source = repository / REGISTRY_PROTECTED_PATHS[0]
    source.unlink()
    os.mkfifo(source, mode=0o600)
    real_open = module.os.open
    checked = False

    def assert_nonblocking_open(
        path: object,
        flags: int,
        *args: object,
        **kwargs: object,
    ) -> int:
        nonlocal checked
        if path == source.name and "dir_fd" in kwargs:
            assert flags & getattr(os, "O_NONBLOCK", 0)
            checked = True
        return real_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(module.os, "open", assert_nonblocking_open)
    with pytest.raises(
        module.ScopeError,
        match="single-link regular file",
    ):
        module._verify_registry_checkout(repository, expected_commit)
    assert checked


def test_registry_inspection_detects_clean_head_switch_restore_aba(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_union_module()
    repository = tmp_path / "registry"
    expected_commit = create_registry_fixture(repository)
    write_bytes(repository / "unprotected.txt", b"alternate commit\n", 0o644)
    subprocess.run(
        ["/usr/bin/git", "-C", str(repository), "add", "unprotected.txt"],
        check=True,
    )
    subprocess.run(
        [
            "/usr/bin/git",
            "-C",
            str(repository),
            "-c",
            "user.name=Release Fixture",
            "-c",
            "user.email=fixture@example.invalid",
            "commit",
            "-q",
            "-m",
            "alternate unprotected commit",
        ],
        check=True,
    )
    alternate_commit = subprocess.run(
        ["/usr/bin/git", "-C", str(repository), "rev-parse", "HEAD"],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    ).stdout.strip()
    subprocess.run(
        [
            "/usr/bin/git",
            "-C",
            str(repository),
            "reset",
            "--hard",
            "-q",
            expected_commit,
        ],
        check=True,
    )
    real_hold = module._hold_stable_file_digest
    switched = False

    def switch_and_restore_after_metadata_hold(
        path: Path,
        label: str,
        **kwargs: object,
    ) -> Any:
        nonlocal switched
        held = real_hold(path, label, **kwargs)
        if label == "Registry symbolic HEAD metadata":
            subprocess.run(
                [
                    "/usr/bin/git",
                    "-C",
                    str(repository),
                    "update-ref",
                    "HEAD",
                    alternate_commit,
                ],
                check=True,
            )
            subprocess.run(
                [
                    "/usr/bin/git",
                    "-C",
                    str(repository),
                    "update-ref",
                    "HEAD",
                    expected_commit,
                ],
                check=True,
            )
            switched = True
        return held

    monkeypatch.setattr(
        module,
        "_hold_stable_file_digest",
        switch_and_restore_after_metadata_hold,
    )
    with pytest.raises(
        module.ScopeError,
        match="Registry .*metadata .*changed during held recheck",
    ):
        module._verify_registry_checkout(repository, expected_commit)
    assert switched
    assert (
        subprocess.run(
            ["/usr/bin/git", "-C", str(repository), "rev-parse", "HEAD"],
            check=True,
            text=True,
            stdout=subprocess.PIPE,
        ).stdout.strip()
        == expected_commit
    )


def test_registry_repository_child_fstat_failure_closes_every_descriptor(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_union_module()
    repository = tmp_path / "registry"
    expected_commit = create_registry_fixture(repository)
    before_fds = set(os.listdir("/proc/self/fd"))
    real_fstat = module.os.fstat
    fstat_calls = 0

    def fail_first_child(descriptor: int) -> os.stat_result:
        nonlocal fstat_calls
        fstat_calls += 1
        if fstat_calls == 2:
            raise OSError("injected child fstat failure")
        return real_fstat(descriptor)

    with monkeypatch.context() as patch:
        patch.setattr(module.os, "fstat", fail_first_child)
        with pytest.raises(
            module.ScopeError,
            match="could not be held safely",
        ):
            module._verify_registry_checkout(repository, expected_commit)
    assert set(os.listdir("/proc/self/fd")) == before_fds


def test_registry_inspection_rejects_corrupt_reachable_git_object(
    tmp_path: Path,
) -> None:
    module = load_union_module()
    repository = tmp_path / "registry"
    expected_commit = create_registry_fixture(repository)
    object_id = subprocess.run(
        [
            "/usr/bin/git",
            "-C",
            str(repository),
            "rev-parse",
            f"{expected_commit}:{REGISTRY_PROTECTED_PATHS[0]}",
        ],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    ).stdout.strip()
    object_path = repository / ".git" / "objects" / object_id[:2] / object_id[2:]
    inflated = zlib.decompress(object_path.read_bytes())
    header, content = inflated.split(b"\0", 1)
    replacement = (
        (b"x" if content[:1] != b"x" else b"y")
        + content[1:]
    )
    object_path.chmod(0o600)
    object_path.write_bytes(zlib.compress(header + b"\0" + replacement))
    object_path.chmod(0o444)
    with pytest.raises(
        module.ScopeError,
        match="Git object graph is invalid",
    ):
        module._verify_registry_checkout(repository, expected_commit)


def test_registry_inspection_ignores_unrelated_parent_directory_churn(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_union_module()
    repository = tmp_path / "registry"
    expected_commit = create_registry_fixture(repository)
    real_popen = module.subprocess.Popen
    churned = False

    def churn_sibling_after_first_git(*args: object, **kwargs: object) -> Any:
        nonlocal churned
        process = real_popen(*args, **kwargs)
        if churned:
            return process

        def churn_sibling() -> None:
            nonlocal churned
            unrelated = tmp_path / "unrelated-entry"
            unrelated.write_bytes(b"unrelated\n")
            unrelated.unlink()
            churned = True

        return ProcessAfterWait(process, churn_sibling)

    monkeypatch.setattr(
        module.subprocess,
        "Popen",
        churn_sibling_after_first_git,
    )
    guard = module._verify_registry_checkout(repository, expected_commit)
    try:
        assert churned
    finally:
        guard.close()


def test_registry_git_control_output_is_byte_bounded(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_union_module()
    repository = tmp_path / "registry"
    expected_commit = create_registry_fixture(repository)
    real_popen = module.subprocess.Popen
    injected = False

    def replace_first_git_with_noisy_process(
        *args: object,
        **kwargs: object,
    ) -> Any:
        nonlocal injected
        if injected:
            return real_popen(*args, **kwargs)
        injected = True
        noisy_command = [
            sys.executable,
            "-c",
            (
                "import os;"
                "os.write(1,b'x'*"
                f"{module.MAX_GIT_CONTROL_OUTPUT_BYTES + 1})"
            ),
        ]
        return real_popen(noisy_command, **kwargs)

    monkeypatch.setattr(
        module.subprocess,
        "Popen",
        replace_first_git_with_noisy_process,
    )
    with pytest.raises(
        module.ScopeError,
        match="output exceeded its bound",
    ):
        module._verify_registry_checkout(repository, expected_commit)
    assert injected


def test_registry_inspection_rejects_shallow_repository(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    create_registry_fixture(source)
    extra = source / "README.md"
    write_bytes(extra, b"second commit\n", 0o644)
    subprocess.run(
        ["/usr/bin/git", "-C", str(source), "add", "README.md"],
        check=True,
    )
    subprocess.run(
        [
            "/usr/bin/git",
            "-C",
            str(source),
            "-c",
            "user.name=Release Fixture",
            "-c",
            "user.email=fixture@example.invalid",
            "commit",
            "-q",
            "-m",
            "second fixture commit",
        ],
        check=True,
    )
    repository = tmp_path / "shallow"
    subprocess.run(
        [
            "/usr/bin/git",
            "clone",
            "-q",
            "--depth=1",
            f"file://{source}",
            str(repository),
        ],
        check=True,
    )
    expected_commit = subprocess.run(
        ["/usr/bin/git", "-C", str(repository), "rev-parse", "HEAD"],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    ).stdout.strip()
    module = load_union_module()
    with pytest.raises(
        module.ScopeError,
        match="shallow .*not allowed",
    ):
        module._verify_registry_checkout(repository, expected_commit)


def test_registry_inspection_rejects_linked_worktree_gitfile(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "registry"
    expected_commit = create_registry_fixture(repository)
    linked = tmp_path / "linked"
    subprocess.run(
        [
            "/usr/bin/git",
            "-C",
            str(repository),
            "worktree",
            "add",
            "-q",
            "--detach",
            str(linked),
            expected_commit,
        ],
        check=True,
    )
    module = load_union_module()
    with pytest.raises(
        module.ScopeError,
        match="linked worktrees and Git metadata indirection are not allowed",
    ):
        module._verify_registry_checkout(linked, expected_commit)


def test_registry_object_root_inventory_is_entry_bounded(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = tmp_path / "registry"
    expected_commit = create_registry_fixture(repository)
    object_root = repository / ".git" / "objects"
    module = load_union_module()
    real_scandir = module.os.scandir

    class FakeEntry:
        name = "aa"
        path = str(object_root / "aa")

        @staticmethod
        def is_symlink() -> bool:
            return False

        @staticmethod
        def is_dir(*, follow_symlinks: bool = True) -> bool:
            return not follow_symlinks or True

        @staticmethod
        def stat(*, follow_symlinks: bool = True) -> os.stat_result:
            assert not follow_symlinks
            return object_root.stat()

    class FakeScandir:
        def __enter__(self) -> object:
            return iter(
                FakeEntry()
                for _ in range(
                    module.MAX_GIT_OBJECT_ROOT_ENTRIES + 1
                )
            )

        def __exit__(self, *_args: object) -> None:
            return None

    def bounded_scandir(path: object) -> object:
        if Path(path) == object_root:
            return FakeScandir()
        return real_scandir(path)

    monkeypatch.setattr(module.os, "scandir", bounded_scandir)
    with pytest.raises(
        module.ScopeError,
        match="object root exceeds its inventory bound",
    ):
        module._verify_registry_checkout(repository, expected_commit)


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("include.path", "/dev/null"),
        ("extensions.worktreeConfig", "true"),
        ("remote.origin.promisor", "true"),
        ("remote.origin.partialCloneFilter", "blob:none"),
    ],
)
def test_registry_inspection_rejects_nonlocal_graph_configuration(
    tmp_path: Path,
    key: str,
    value: str,
) -> None:
    repository = tmp_path / "registry"
    expected_commit = create_registry_fixture(repository)
    subprocess.run(
        ["/usr/bin/git", "-C", str(repository), "config", key, value],
        check=True,
    )
    module = load_union_module()
    with pytest.raises(
        module.ScopeError,
        match="shallow, partial, included, or split Git configuration",
    ):
        module._verify_registry_checkout(repository, expected_commit)


def test_registry_inspection_rejects_partial_clone_extension(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "registry"
    expected_commit = create_registry_fixture(repository)
    config_path = repository / ".git" / "config"
    config_path.write_bytes(
        config_path.read_bytes()
        + b"\n[extensions]\n\tpartialClone = origin\n"
    )
    module = load_union_module()
    with pytest.raises(
        module.ScopeError,
        match="shallow, partial, included, or split Git configuration",
    ):
        module._verify_registry_checkout(repository, expected_commit)


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("fsck.missingEmail", "ignore"),
        ("fsck.skipList", "/dev/null"),
    ],
)
def test_registry_inspection_rejects_local_fsck_policy_configuration(
    tmp_path: Path,
    key: str,
    value: str,
) -> None:
    repository = tmp_path / "registry"
    expected_commit = create_registry_fixture(repository)
    subprocess.run(
        ["/usr/bin/git", "-C", str(repository), "config", key, value],
        check=True,
    )
    module = load_union_module()
    with pytest.raises(
        module.ScopeError,
        match="local Git fsck policy configuration is not allowed",
    ):
        module._verify_registry_checkout(repository, expected_commit)


def test_registry_inspection_rejects_promisor_pack_marker(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "registry"
    expected_commit = create_registry_fixture(repository)
    marker = repository / ".git" / "objects" / "pack" / (
        "pack-" + "a" * 40 + ".promisor"
    )
    write_bytes(marker, b"", 0o600)
    module = load_union_module()
    with pytest.raises(
        module.ScopeError,
        match="promisor packs are not allowed",
    ):
        module._verify_registry_checkout(repository, expected_commit)


@pytest.mark.parametrize(
    ("injection", "message"),
    [
        ("promisor", "promisor packs are not allowed"),
        ("unexpected-root-entry", "object root contains an unexpected entry"),
    ],
)
def test_registry_inspection_rejects_object_store_injection_before_watch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    injection: str,
    message: str,
) -> None:
    repository = tmp_path / "registry"
    expected_commit = create_registry_fixture(repository)
    subprocess.run(
        ["/usr/bin/git", "-C", str(repository), "repack", "-a", "-d", "-q"],
        check=True,
    )
    object_root = repository / ".git" / "objects"
    pack_root = object_root / "pack"
    pack_path = next(
        path for path in pack_root.iterdir() if path.suffix == ".pack"
    )
    injected_path = (
        pack_path.with_suffix(".promisor")
        if injection == "promisor"
        else object_root / "unexpected-after-scan"
    )
    module = load_union_module()
    real_watch = module._MutationWatch
    injected = False

    def inject_before_watch(
        *args: object,
        **kwargs: object,
    ) -> Any:
        nonlocal injected
        write_bytes(injected_path, b"", 0o600)
        injected = True
        return real_watch(*args, **kwargs)

    monkeypatch.setattr(module, "_MutationWatch", inject_before_watch)
    with pytest.raises(module.ScopeError, match=message):
        module._verify_registry_checkout(repository, expected_commit)
    assert injected
    assert injected_path.is_file()


@pytest.mark.parametrize(
    "relative",
    [
        ".git/shallow",
        ".git/info/grafts",
        ".git/objects/info/alternates",
        ".git/objects/info/http-alternates",
    ],
)
def test_registry_guard_rejects_graph_control_absence_aba(
    tmp_path: Path,
    relative: str,
) -> None:
    repository = tmp_path / "registry"
    expected_commit = create_registry_fixture(repository)
    module = load_union_module()
    guard = module._verify_registry_checkout(repository, expected_commit)
    control = repository / relative
    try:
        write_bytes(control, (expected_commit + "\n").encode(), 0o600)
        control.unlink()
        with pytest.raises(
            module.ScopeError,
            match="release authority changed|absence changed",
        ):
            guard.verify()
    finally:
        guard.close()


def test_registry_guard_rejects_local_config_aba(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "registry"
    expected_commit = create_registry_fixture(repository)
    module = load_union_module()
    guard = module._verify_registry_checkout(repository, expected_commit)
    config_path = repository / ".git" / "config"
    original = config_path.read_bytes()
    try:
        config_path.write_bytes(original + b"\n# transient mutation\n")
        config_path.write_bytes(original)
        with pytest.raises(
            module.ScopeError,
            match="release authority changed|configuration changed",
        ):
            guard.verify()
    finally:
        guard.close()


def test_rejects_internally_rehashed_review_bytes_that_differ_from_gold(
    tmp_path: Path,
) -> None:
    def post(context: dict[str, Any]) -> None:
        platform = "windows"
        review_path = context["review_manifests"][platform]
        review = json.loads(review_path.read_text())
        review["artifacts"][0]["sha256"] = "f" * 64
        review_raw = write_json(review_path, review, 0o600)
        review_sha = hashlib.sha256(review_raw).hexdigest()

        decision_path = context["release_decisions"][platform]
        decision = json.loads(decision_path.read_text())
        decision["manifestSha256"] = review_sha
        decision_raw = write_json(decision_path, decision, 0o600)
        decision_sha = hashlib.sha256(decision_raw).hexdigest()

        snapshot_path = context["authority_snapshots"][platform]
        snapshot = json.loads(snapshot_path.read_text())
        snapshot["manifestSha256"] = review_sha
        snapshot["releaseDecisionSha256"] = decision_sha
        snapshot["artifacts"][0]["sha256"] = "f" * 64
        snapshot_raw = write_json(snapshot_path, snapshot, 0o600)
        snapshot_sha = hashlib.sha256(snapshot_raw).hexdigest()

        current_path = context["authority_currents"][platform]
        current = json.loads(current_path.read_text())
        current["snapshotSha256"] = snapshot_sha
        current["decisionSha256"] = decision_sha
        write_json(current_path, current, 0o600)

        for gate in GATES:
            receipt_path = context["receipts"][(platform, gate)]
            receipt = json.loads(receipt_path.read_text())
            binding = receipt["campaign_operability_candidate_binding"]
            binding["manifest_sha256"] = review_sha
            binding["authority_snapshot_sha256"] = snapshot_sha
            binding["release_decision_sha256"] = decision_sha
            write_json(receipt_path, receipt, 0o600)

    result, output, _ = invoke(tmp_path, post_materialize=post)
    assert result.returncode == 1
    assert "final gold artifact identity differs from reviewed bytes" in result.stderr
    assert not output.exists()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("contract_name", "wrong.contract"),
        ("status", "fail"),
        ("channelId", "preview"),
        ("reasons", ["still blocked"]),
    ],
)
def test_rejects_nonpassing_or_wrong_presentation_gate(
    tmp_path: Path,
    field: str,
    value: object,
) -> None:
    def mutate_receipts(receipts: dict[tuple[str, str], dict[str, Any]]) -> None:
        receipts[("windows", "workflow")][field] = value

    result, output, _ = invoke(tmp_path, mutate_receipts=mutate_receipts)
    assert result.returncode == 1
    assert "windows workflow Presentation" in result.stderr
    assert not output.exists()


@pytest.mark.parametrize("field", sorted(BINDING_FIELDS))
def test_rejects_drift_in_every_candidate_binding_field(
    tmp_path: Path,
    field: str,
) -> None:
    def mutate_receipts(receipts: dict[tuple[str, str], dict[str, Any]]) -> None:
        binding = receipts[("macos", "executable")][
            "campaign_operability_candidate_binding"
        ]
        binding[field] = (
            ["blazor-desktop"] if field == "required_heads" else "drifted"
        )

    result, output, _ = invoke(tmp_path, mutate_receipts=mutate_receipts)
    assert result.returncode == 1
    assert "candidate binding disagrees" in result.stderr
    assert not output.exists()


def test_rejects_extra_or_missing_candidate_binding_fields(tmp_path: Path) -> None:
    def extra(receipts: dict[tuple[str, str], dict[str, Any]]) -> None:
        receipts[("linux", "visual")]["campaign_operability_candidate_binding"][
            "unreviewed"
        ] = True

    result, output, _ = invoke(tmp_path, mutate_receipts=extra)
    assert result.returncode == 1
    assert "unexpected field set" in result.stderr
    assert not output.exists()

    second = tmp_path / "missing"
    second.mkdir()

    def missing(receipts: dict[tuple[str, str], dict[str, Any]]) -> None:
        del receipts[("linux", "visual")]["campaign_operability_candidate_binding"][
            "manifest_sha256"
        ]

    result, output, _ = invoke(second, mutate_receipts=missing)
    assert result.returncode == 1
    assert "unexpected field set" in result.stderr
    assert not output.exists()


def test_rejects_release_alias_ambiguity_even_when_values_match(tmp_path: Path) -> None:
    def mutate_receipts(receipts: dict[tuple[str, str], dict[str, Any]]) -> None:
        receipts[("linux", "workflow")]["release_version"] = VERSION

    result, output, _ = invoke(tmp_path, mutate_receipts=mutate_receipts)
    assert result.returncode == 1
    assert "exactly one canonical alias" in result.stderr
    assert not output.exists()


def test_all_nine_receipts_are_generated_by_real_ui_candidate_routing(
    tmp_path: Path,
) -> None:
    routing = load_real_ui_candidate_routing()
    result, _, context = invoke(tmp_path)
    assert result.returncode == 0, result.stderr
    producer_by_gate = {
        "visual": "desktop-visual",
        "workflow": "desktop-workflow",
        "executable": "desktop-executable",
    }
    for platform in PLATFORMS:
        scope_path = context["decisions"][platform]
        snapshot_path = context["authority_snapshots"][platform]
        candidate_context = routing.load_campaign_operability_candidate_context(
            approved_scope_path=scope_path,
            expected_scope_sha256=hashlib.sha256(scope_path.read_bytes()).hexdigest(),
            expected_release_version=VERSION,
            registry_review_seed_path=snapshot_path,
            expected_registry_review_seed_sha256=hashlib.sha256(
                snapshot_path.read_bytes()
            ).hexdigest(),
            bounded_owner="chummer-release-operations",
            next_actions=["Complete global stable union verification."],
            allow_raw_fail_declaration=False,
        )
        for gate in GATES:
            receipt = json.loads(context["receipts"][(platform, gate)].read_text())
            expected_binding = receipt.pop(
                "campaign_operability_candidate_binding"
            )
            decorated = routing.decorate_campaign_operability_candidate_payload(
                producer=producer_by_gate[gate],
                payload=receipt,
                context=candidate_context,
            )
            assert (
                decorated["campaign_operability_candidate_binding"]
                == expected_binding
            )


def test_rejects_reused_receipt_bytes_across_platforms(tmp_path: Path) -> None:
    def post(context: dict[str, Any]) -> None:
        shutil.copyfile(
            context["receipts"][("linux", "visual")],
            context["receipts"][("macos", "visual")],
        )

    result, output, _ = invoke(tmp_path, post_materialize=post)
    assert result.returncode == 1
    assert "byte-distinct" in result.stderr
    assert not output.exists()


@pytest.mark.parametrize("target", ["decision", "receipt", "artifact"])
def test_rejects_symlinked_authority_or_candidate_inputs(
    tmp_path: Path,
    target: str,
) -> None:
    def post(context: dict[str, Any]) -> None:
        if target == "decision":
            path = context["decisions"]["linux"]
        elif target == "receipt":
            path = context["receipts"][("windows", "executable")]
        else:
            path = context["files_root"] / "chummer-avalonia-linux-x64-installer.deb"
        replacement = path.with_suffix(path.suffix + ".real")
        path.rename(replacement)
        path.symlink_to(replacement)

    result, output, _ = invoke(tmp_path, post_materialize=post)
    assert result.returncode == 1
    assert "symlink" in result.stderr or "opened safely" in result.stderr
    assert not output.exists()


def test_rejects_publicly_readable_private_authority_receipt(tmp_path: Path) -> None:
    def post(context: dict[str, Any]) -> None:
        context["receipts"][("macos", "workflow")].chmod(0o644)

    result, output, _ = invoke(tmp_path, post_materialize=post)
    assert result.returncode == 1
    assert "must not be accessible by group or other users" in result.stderr
    assert not output.exists()


def test_rejects_duplicate_or_case_shadowed_manifest_fields(tmp_path: Path) -> None:
    private_field = "PRIVATE-DUPLICATE-FIELD-SENTINEL"

    def post(context: dict[str, Any]) -> None:
        raw = context["manifest"].read_text()
        context["manifest"].write_text(
            raw.replace(
                '"status":"published"',
                (
                    '"status":"published",'
                    f'"{private_field}":1,'
                    f'"{private_field.lower()}":2'
                ),
            )
        )
        context["manifest"].chmod(0o600)

    result, output, _ = invoke(tmp_path, post_materialize=post)
    assert result.returncode == 1
    assert "duplicate or case-shadowed" in result.stderr
    assert private_field not in result.stderr
    assert private_field.lower() not in result.stderr
    assert not output.exists()


def test_output_is_create_only_and_never_overwrites_existing_receipt(
    tmp_path: Path,
) -> None:
    result, output, context = invoke(tmp_path, precreate_output=True)
    assert result.returncode == 1
    assert "output already exists" in result.stderr
    assert json.loads(output.read_text()) == {"status": "old"}
    assert not context["artifact_snapshot_root"].exists()


def test_artifact_snapshot_root_is_create_only(
    tmp_path: Path,
) -> None:
    def precreate_snapshot(context: dict[str, Any]) -> None:
        context["artifact_snapshot_root"].mkdir()

    result, output, _ = invoke(
        tmp_path,
        post_materialize=precreate_snapshot,
    )
    assert result.returncode == 1
    assert "artifact snapshot root already exists" in result.stderr
    assert not output.exists()


def test_artifact_snapshot_root_named_objects_uses_explicit_parent_fds(
    tmp_path: Path,
) -> None:
    def use_objects_basename(context: dict[str, Any]) -> None:
        snapshot_root = tmp_path / "objects"
        command = context["command"]
        argument_index = command.index("--artifact-snapshot-root") + 1
        command[argument_index] = str(snapshot_root)
        context["artifact_snapshot_root"] = snapshot_root

    result, output, context = invoke(
        tmp_path,
        post_materialize=use_objects_basename,
    )
    assert result.returncode == 0, result.stderr
    receipt = json.loads(output.read_text())
    snapshot_root = context["artifact_snapshot_root"]
    assert receipt["artifactSnapshot"]["root"] == str(snapshot_root)
    assert (snapshot_root / "ARTIFACT_SNAPSHOT.generated.json").is_file()
    assert (
        snapshot_root / "ARTIFACT_SNAPSHOT_COMMIT.generated.json"
    ).is_file()
    assert (snapshot_root / "objects").is_dir()


def test_output_final_name_is_absent_until_post_write_check_passes(
    tmp_path: Path,
) -> None:
    module = load_union_module()
    output_parent = tmp_path / "private-output"
    output_parent.mkdir(mode=0o700)
    output = output_parent / "receipt.json"
    callback_path_states: list[bool] = []

    def final_check() -> None:
        callback_path_states.append(output.exists())

    module._write_new(
        output,
        {"status": "pass"},
        post_write_check=final_check,
    )
    assert callback_path_states == [False, False]
    assert output.read_bytes() == canonical({"status": "pass"})


def test_output_commit_fsyncs_parent_after_link(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_union_module()
    output_parent = tmp_path / "private-output"
    output_parent.mkdir(mode=0o700)
    output = output_parent / "receipt.json"
    parent_identity = (
        output_parent.stat().st_dev,
        output_parent.stat().st_ino,
    )
    real_fsync = module.os.fsync
    real_link = module.os.link
    events: list[tuple[str, bool]] = []

    def traced_fsync(descriptor: int) -> None:
        opened = os.fstat(descriptor)
        if (opened.st_dev, opened.st_ino) == parent_identity:
            events.append(("parent_fsync", output.exists()))
        real_fsync(descriptor)

    def traced_link(*args: object, **kwargs: object) -> None:
        events.append(("link_before", output.exists()))
        real_link(*args, **kwargs)
        events.append(("link_after", output.exists()))

    monkeypatch.setattr(module.os, "fsync", traced_fsync)
    monkeypatch.setattr(module.os, "link", traced_link)
    module._write_new(output, {"status": "prepared"})
    assert events == [
        ("parent_fsync", False),
        ("parent_fsync", False),
        ("link_before", False),
        ("link_after", True),
        ("parent_fsync", True),
    ]


def test_post_link_parent_fsync_failure_is_durability_indeterminate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_union_module()
    output_parent = tmp_path / "private-output"
    output_parent.mkdir(mode=0o700)
    output = output_parent / "receipt.json"
    payload = {
        "status": "prepared",
        "authorizationStatus": "requires_publisher_consumption_receipt",
    }
    parent_identity = (
        output_parent.stat().st_dev,
        output_parent.stat().st_ino,
    )
    real_fsync = module.os.fsync
    parent_fsyncs = 0

    def fail_post_link_parent_fsync(descriptor: int) -> None:
        nonlocal parent_fsyncs
        opened = os.fstat(descriptor)
        if (opened.st_dev, opened.st_ino) == parent_identity:
            parent_fsyncs += 1
            if parent_fsyncs == 3:
                raise OSError("injected post-link fsync failure")
        real_fsync(descriptor)

    monkeypatch.setattr(module.os, "fsync", fail_post_link_parent_fsync)
    with pytest.raises(
        module.ScopeError,
        match="durability is indeterminate",
    ):
        module._write_new(output, payload)
    assert output.read_bytes() == canonical(payload)
    with pytest.raises(module.ScopeError, match="output already exists"):
        module._write_new(output, payload)


def test_output_parent_retry_fsyncs_visible_creation_residue(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_union_module()
    first_created = tmp_path / "new-parent"
    output = first_created / "nested" / "preparation.json"
    real_fsync = module.os.fsync
    target_attempts = 0
    injected = False

    def fail_first_created_directory_fsync(descriptor: int) -> None:
        nonlocal target_attempts, injected
        opened = os.fstat(descriptor)
        if first_created.exists():
            target = first_created.stat()
            if (opened.st_dev, opened.st_ino) == (
                target.st_dev,
                target.st_ino,
            ):
                target_attempts += 1
                if not injected:
                    injected = True
                    raise OSError("injected first ancestor fsync failure")
        real_fsync(descriptor)

    monkeypatch.setattr(
        module.os,
        "fsync",
        fail_first_created_directory_fsync,
    )
    with pytest.raises(
        module.ScopeError,
        match="output parent could not be made durable",
    ):
        module._open_private_output_parent(output)
    assert first_created.is_dir()

    parent_fd, parent = module._open_private_output_parent(output)
    try:
        assert parent == output.parent
        assert target_attempts >= 2
    finally:
        os.close(parent_fd)


def test_output_staging_has_no_named_path_visible_to_callback(
    tmp_path: Path,
) -> None:
    module = load_union_module()
    output_parent = tmp_path / "private-output"
    output_parent.mkdir(mode=0o700)
    output = output_parent / "receipt.json"
    observations = 0

    def inspect_private_parent() -> None:
        nonlocal observations
        stages = [
            item
            for item in output_parent.iterdir()
            if item.name.startswith(".scope-union-")
        ]
        assert stages == []
        observations += 1

    module._write_new(
        output,
        {"status": "pass"},
        post_write_check=inspect_private_parent,
    )
    assert observations == 2
    assert output.read_bytes() == canonical({"status": "pass"})


def test_output_second_authority_failure_happens_before_publication(
    tmp_path: Path,
) -> None:
    module = load_union_module()
    output_parent = tmp_path / "private-output"
    output_parent.mkdir(mode=0o700)
    output = output_parent / "receipt.json"
    checks = 0

    def fail_second_check() -> None:
        nonlocal checks
        checks += 1
        if checks == 2:
            raise module.ScopeError("late authority failure")

    with pytest.raises(module.ScopeError, match="late authority failure"):
        module._write_new(
            output,
            {"status": "pass"},
            post_write_check=fail_second_check,
        )
    assert checks == 2
    assert not output.exists()


def test_output_process_exit_during_final_check_cannot_publish_pass(
    tmp_path: Path,
) -> None:
    module = load_union_module()
    output_parent = tmp_path / "private-output"
    output_parent.mkdir(mode=0o700)
    output = output_parent / "receipt.json"
    child = os.fork()
    if child == 0:
        checks = 0

        def exit_during_second_check() -> None:
            nonlocal checks
            checks += 1
            if checks == 2:
                os._exit(91)

        module._write_new(
            output,
            {"status": "pass"},
            post_write_check=exit_during_second_check,
        )
        os._exit(0)
    _pid, status = os.waitpid(child, 0)
    assert os.waitstatus_to_exitcode(status) == 91
    assert not output.exists()


def test_mutation_watch_catches_earlier_authority_change_during_later_check(
    tmp_path: Path,
) -> None:
    module = load_union_module()
    first = tmp_path / "first.bin"
    second = tmp_path / "second.bin"
    write_bytes(first, b"first authority\n", 0o600)
    write_bytes(second, b"second authority\n", 0o600)
    first_held = module._hold_stable_file_digest(first, "first authority")
    second_held = module._hold_stable_file_digest(second, "second authority")
    watch = module._MutationWatch([first, second])
    output_parent = tmp_path / "private-output"
    output_parent.mkdir(mode=0o700)
    output = output_parent / "receipt.json"
    mutated = False

    def sequential_check() -> None:
        nonlocal mutated
        first_held.recheck()
        if not mutated:
            first.write_bytes(b"first mutation!\n")
            mutated = True
        second_held.recheck()

    try:
        with pytest.raises(
            module.ScopeError,
            match="release authority changed during receipt commit",
        ):
            module._write_new(
                output,
                {"status": "pass"},
                post_write_check=sequential_check,
                mutation_watch=watch,
            )
        assert mutated
        assert not output.exists()
    finally:
        watch.close()
        second_held.close()
        first_held.close()


def test_reverse_digest_sweep_detects_preopened_mmap_change(
    tmp_path: Path,
) -> None:
    module = load_union_module()
    first = tmp_path / "first.bin"
    second = tmp_path / "second.bin"
    write_bytes(first, b"APPROVED-FIRST!!", 0o600)
    write_bytes(second, b"APPROVED-SECOND!", 0o600)
    writable = os.open(first, os.O_RDWR)
    mapping = mmap.mmap(writable, first.stat().st_size)
    first_held = module._hold_stable_file_digest(first, "first authority")
    second_held = module._hold_stable_file_digest(second, "second authority")
    watch = module._MutationWatch([first, second])
    output_parent = tmp_path / "private-output"
    output_parent.mkdir(mode=0o700)
    output = output_parent / "receipt.json"
    mutated = False

    def forward_reverse_check() -> None:
        nonlocal mutated
        held = [first_held, second_held]
        for index, item in enumerate(held):
            item.recheck()
            if index == 0 and not mutated:
                mapping[:8] = b"TAMPERED"
                mutated = True
        for item in reversed(held):
            item.recheck()

    try:
        with pytest.raises(
            module.ScopeError,
            match="changed during held recheck",
        ):
            module._write_new(
                output,
                {"status": "pass"},
                post_write_check=forward_reverse_check,
                mutation_watch=watch,
            )
        assert mutated
        assert not output.exists()
    finally:
        watch.close()
        second_held.close()
        first_held.close()
        mapping.close()
        os.close(writable)


def test_mutation_watch_ignores_only_its_output_in_shared_parent(
    tmp_path: Path,
) -> None:
    module = load_union_module()
    shared_parent = tmp_path / "private-shared"
    shared_parent.mkdir(mode=0o700)
    authority = shared_parent / "authority.bin"
    output = shared_parent / "receipt.json"
    write_bytes(authority, b"stable authority\n", 0o600)
    held = module._hold_stable_file_digest(authority, "shared authority")
    watch = module._MutationWatch(
        [authority],
        ignored_paths=[output],
    )

    try:
        module._write_new(
            output,
            {"status": "pass"},
            post_write_check=held.recheck,
            mutation_watch=watch,
        )
        assert output.read_bytes() == canonical({"status": "pass"})
    finally:
        watch.close()
        held.close()


def test_mutation_watch_ignores_unrelated_sibling_churn_but_poison_is_sticky(
    tmp_path: Path,
) -> None:
    module = load_union_module()
    parent = tmp_path / "shared"
    parent.mkdir()
    authority = parent / "authority.bin"
    write_bytes(authority, b"stable authority\n", 0o600)
    watch = module._MutationWatch([authority])
    try:
        unrelated = parent / "unrelated.log"
        unrelated.write_bytes(b"ordinary sibling churn\n")
        unrelated.unlink()
        watch.assert_quiet()

        authority.write_bytes(b"changed authority\n")
        with pytest.raises(
            module.ScopeError,
            match="release authority changed during receipt commit",
        ):
            watch.assert_quiet()
        authority.write_bytes(b"stable authority\n")
        with pytest.raises(
            module.ScopeError,
            match="release authority changed during receipt commit",
        ):
            watch.assert_quiet()
    finally:
        watch.close()


def test_mutation_watch_detects_higher_ancestor_rename_restore_aba(
    tmp_path: Path,
) -> None:
    module = load_union_module()
    authority_root = tmp_path / "authority"
    shelf = authority_root / "shelf"
    shelf.mkdir(parents=True)
    artifact = shelf / "artifact.bin"
    write_bytes(artifact, b"approved bytes\n", 0o600)
    watch = module._MutationWatch([artifact])
    held_root = tmp_path / "authority-held"
    try:
        authority_root.rename(held_root)
        authority_root.mkdir()
        (authority_root / "shelf").mkdir()
        write_bytes(
            authority_root / "shelf" / "artifact.bin",
            b"forged bytes!!\n",
            0o600,
        )
        shutil.rmtree(authority_root)
        held_root.rename(authority_root)
        with pytest.raises(
            module.ScopeError,
            match="release authority changed during receipt commit",
        ):
            watch.assert_quiet()
    finally:
        watch.close()


def test_output_parent_permission_change_during_check_fails_closed(
    tmp_path: Path,
) -> None:
    module = load_union_module()
    output_parent = tmp_path / "private-output"
    output_parent.mkdir(mode=0o700)
    output = output_parent / "receipt.json"
    changed = False

    def change_parent_permissions() -> None:
        nonlocal changed
        if not changed:
            output_parent.chmod(0o777)
            changed = True

    try:
        with pytest.raises(
            module.ScopeError,
            match="output parent permissions changed",
        ):
            module._write_new(
                output,
                {"status": "pass"},
                post_write_check=change_parent_permissions,
            )
        assert changed
        assert not output.exists()
    finally:
        output_parent.chmod(0o700)


def test_output_parent_second_check_failure_prevents_publication(
    tmp_path: Path,
) -> None:
    module = load_union_module()
    output_parent = tmp_path / "private-output"
    output_parent.mkdir(mode=0o700)
    output = output_parent / "receipt.json"
    checks = 0

    def change_parent_after_commit() -> None:
        nonlocal checks
        checks += 1
        if checks == 2:
            output_parent.chmod(0o777)

    try:
        with pytest.raises(
            module.ScopeError,
            match="output parent permissions changed",
        ):
            module._write_new(
                output,
                {"status": "pass"},
                post_write_check=change_parent_after_commit,
            )
        assert checks == 2
        assert not output.exists()
    finally:
        output_parent.chmod(0o700)


def test_output_link_failure_leaves_no_named_receipt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_union_module()
    output_parent = tmp_path / "private-output"
    output_parent.mkdir(mode=0o700)
    output = output_parent / "receipt.json"

    def fail_link(*_args: object, **_kwargs: object) -> None:
        raise OSError("injected final link failure")

    monkeypatch.setattr(module.os, "link", fail_link)
    with pytest.raises(
        module.ScopeError,
        match="could not be committed",
    ):
        module._write_new(output, {"status": "pass"})
    assert not output.exists()


def test_rejects_nonprivate_output_parent(tmp_path: Path) -> None:
    def post(_: dict[str, Any]) -> None:
        tmp_path.chmod(0o755)

    result, output, _ = invoke(tmp_path, post_materialize=post)
    assert result.returncode == 1
    assert "output parent must be caller-owned and private" in result.stderr
    assert not output.exists()


def test_input_parent_identity_swap_is_detected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_union_module()
    path = tmp_path / "private" / "input.json"
    write_json(path, {"status": "pass"})

    def swapped(*_: object, **__: object) -> None:
        raise module.ScopeError("simulated input ancestor swap")

    monkeypatch.setattr(module, "_parent_still_bound", swapped)
    with pytest.raises(module.ScopeError, match="ancestor swap"):
        module._stable_bytes(path, "raced input", private=True)


def test_nul_basename_is_rejected_without_leaking_parent_descriptor(
    tmp_path: Path,
) -> None:
    module = load_union_module()
    before_fds = set(os.listdir("/proc/self/fd"))
    with pytest.raises(module.ScopeError, match="inspected safely"):
        module._hold_stable_file_digest(
            tmp_path / "private-field\0name",
            "NUL candidate",
        )
    assert set(os.listdir("/proc/self/fd")) == before_fds


def test_existing_parent_child_fstat_failure_closes_every_descriptor(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_union_module()
    parent = tmp_path / "authority"
    parent.mkdir()
    path = parent / "input.json"
    before_fds = set(os.listdir("/proc/self/fd"))
    real_fstat = module.os.fstat
    injected = False

    def fail_child_fstat(descriptor: int) -> os.stat_result:
        nonlocal injected
        if not injected:
            injected = True
            raise OSError("injected parent fstat failure")
        return real_fstat(descriptor)

    with monkeypatch.context() as patch:
        patch.setattr(module.os, "fstat", fail_child_fstat)
        with pytest.raises(
            module.ScopeError,
            match="parent could not be opened safely",
        ):
            module._open_existing_parent(path, "injected input")
    assert injected
    assert set(os.listdir("/proc/self/fd")) == before_fds


def test_cleanup_continues_after_one_close_reports_an_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_union_module()
    first_path = tmp_path / "first.bin"
    second_path = tmp_path / "second.bin"
    write_bytes(first_path, b"first\n", 0o600)
    write_bytes(second_path, b"second\n", 0o600)
    first = module._hold_stable_file_digest(first_path, "first")
    second = module._hold_stable_file_digest(second_path, "second")
    descriptors = [
        first.descriptor,
        first.parent_fd,
        second.descriptor,
        second.parent_fd,
    ]
    real_close = module.os.close
    injected = False

    def close_then_report_error(descriptor: int) -> None:
        nonlocal injected
        real_close(descriptor)
        if not injected:
            injected = True
            raise OSError("injected close report")

    monkeypatch.setattr(module.os, "close", close_then_report_error)
    first.close()
    second.close()
    assert injected
    for descriptor in descriptors:
        with pytest.raises(OSError):
            os.fstat(descriptor)


def test_output_parent_identity_swap_removes_partial_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_union_module()
    output_parent = tmp_path / "private-output"
    output_parent.mkdir(mode=0o700)
    output = output_parent / "receipt.json"
    real_stat = module.os.stat

    def raced_stat(path: object, *args: object, **kwargs: object) -> Any:
        observed = real_stat(path, *args, **kwargs)
        if (
            Path(path) == output_parent.absolute()
            and kwargs.get("follow_symlinks") is False
            and "dir_fd" not in kwargs
        ):
            values = list(observed)
            values[1] += 1
            return os.stat_result(values)
        return observed

    monkeypatch.setattr(module.os, "stat", raced_stat)
    with pytest.raises(module.ScopeError, match="parent changed during write"):
        module._write_new(output, {"status": "pass"})
    assert not output.exists()

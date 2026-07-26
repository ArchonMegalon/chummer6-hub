from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any, Callable

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "verify_release_scope_union.py"
VERSION = "run-20260726-global-stable"
REGISTRY_COMMIT = "1" * 40
AUTHORITY_SNAPSHOT_SHA = "2" * 64
RELEASE_DECISION_SHA = "3" * 64
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
        "artifacts": [
            {
                "artifactId": row["artifactId"],
                "promotionStatus": "pass",
                "signingStatus": "pass",
                "notarizationStatus": "pass" if row["platform"] == "macos" else "",
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
PostMaterialize = Callable[[dict[str, Any]], None]


def invoke(
    tmp_path: Path,
    *,
    mutate: Mutator | None = None,
    mutate_receipts: ReceiptMutator | None = None,
    post_materialize: PostMaterialize | None = None,
    precreate_output: bool = False,
) -> tuple[subprocess.CompletedProcess[str], Path, dict[str, Any]]:
    state = candidate_state()
    if mutate is not None:
        mutate(state)
    files_root = tmp_path / "files"
    for name, raw in state["files"].items():
        write_bytes(files_root / name, raw, 0o644)
    manifest_path = tmp_path / "RELEASE_CHANNEL.generated.json"
    manifest_raw = write_json(manifest_path, state["manifest"], 0o600)
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
                    "authority_snapshot_sha256": AUTHORITY_SNAPSHOT_SHA,
                    "contract_name": "chummer6-ui.campaign_operability_candidate_binding",
                    "contract_version": 1,
                    "manifest_sha256": manifest_sha,
                    "platform": platform,
                    "primary_head": "avalonia",
                    "registry_commit": REGISTRY_COMMIT,
                    "release_decision_sha256": RELEASE_DECISION_SHA,
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

    output = tmp_path / "GLOBAL_RELEASE_SCOPE_UNION_VERIFICATION.generated.json"
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
        "--expected-release-version",
        VERSION,
        "--expected-registry-commit",
        REGISTRY_COMMIT,
        "--expected-authority-snapshot-sha256",
        AUTHORITY_SNAPSHOT_SHA,
        "--expected-release-decision-sha256",
        RELEASE_DECISION_SHA,
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
            ]
        )
        for gate in GATES:
            command.extend(
                [
                    f"--{platform}-{gate}-receipt",
                    str(receipt_paths[(platform, gate)]),
                ]
            )
    command.extend(["--output", str(output)])
    context = {
        "state": state,
        "manifest": manifest_path,
        "promotion": promotion_path,
        "files_root": files_root,
        "decisions": decision_paths,
        "receipts": receipt_paths,
        "command": command,
    }
    if post_materialize is not None:
        post_materialize(context)
    result = subprocess.run(command, capture_output=True, text=True)
    return result, output, context


def test_accepts_only_complete_exact_global_union_and_emits_closed_receipt(
    tmp_path: Path,
) -> None:
    result, output, _ = invoke(tmp_path)
    assert result.returncode == 0, result.stderr
    receipt = json.loads(output.read_text())
    assert receipt["contractName"] == "chummer.release-scope-union-verification/v1"
    assert receipt["status"] == "pass"
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
    assert receipt["registryCommit"] == REGISTRY_COMMIT
    assert receipt["authoritySnapshotSha256"] == AUTHORITY_SNAPSHOT_SHA
    assert receipt["releaseDecisionSha256"] == RELEASE_DECISION_SHA
    assert len(receipt["filesRootInventorySha256"]) == 64
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
    assert "bytes disagree with manifest" in result.stderr
    assert not output.exists()


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
    def post(context: dict[str, Any]) -> None:
        raw = context["manifest"].read_text()
        context["manifest"].write_text(
            raw.replace('"status":"published"', '"Status":"published","status":"published"')
        )
        context["manifest"].chmod(0o600)

    result, output, _ = invoke(tmp_path, post_materialize=post)
    assert result.returncode == 1
    assert "duplicate or case-shadowed" in result.stderr
    assert not output.exists()


def test_output_is_create_only_and_never_overwrites_existing_receipt(
    tmp_path: Path,
) -> None:
    result, output, _ = invoke(tmp_path, precreate_output=True)
    assert result.returncode == 1
    assert "output already exists" in result.stderr
    assert json.loads(output.read_text()) == {"status": "old"}

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "verify_release_scope_decision.py"
VERSION = "run-20260721-macos-preview"


def write_json(path: Path, payload: object) -> bytes:
    raw = (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode()
    path.write_bytes(raw)
    path.chmod(0o600)
    return raw


def decision() -> dict[str, object]:
    return {
        "contractName": "chummer.release-scope-decision/v1",
        "contractVersion": 1,
        "decisionId": "scope-run-20260721-macos-preview",
        "status": "approved",
        "approvedAtUtc": "2026-07-21T12:00:00Z",
        "approvedBy": "Release authority",
        "releaseVersion": VERSION,
        "channel": "preview",
        "releaseTarget": "preview",
        "supportOwner": "Chummer release operations",
        "platforms": [
            {
                "platform": "macos",
                "rid": "osx-arm64",
                "primaryHead": "avalonia",
                "fallbackHeads": ["blazor-desktop"],
                "artifactAccessClass": "open_public",
                "signingRequirement": "preview_unsigned_allowed",
            }
        ],
    }


def artifact(artifact_id: str, head: str, kind: str = "installer") -> dict[str, object]:
    extension = "dmg" if kind == "installer" else "tar.gz"
    return {
        "artifactId": artifact_id,
        "head": head,
        "platform": "macos",
        "rid": "osx-arm64",
        "arch": "arm64",
        "kind": kind,
        "fileName": f"{artifact_id}.{extension}",
        "installAccessClass": "open_public",
    }


def invoke(
    tmp_path: Path,
    *,
    scope: dict[str, object] | None = None,
    artifacts: list[dict[str, object]] | None = None,
    evidence: list[dict[str, object]] | None = None,
    preflight: bool = False,
) -> tuple[subprocess.CompletedProcess[str], Path]:
    decision_path = tmp_path / "RELEASE_SCOPE_DECISION.approved.json"
    decision_raw = write_json(decision_path, scope or decision())
    output = tmp_path / "receipt.json"
    command = [
        sys.executable,
        str(SCRIPT),
        "--decision",
        str(decision_path),
        "--expected-sha256",
        hashlib.sha256(decision_raw).hexdigest(),
        "--authority",
        "design://release-scope/scope-run-20260721-macos-preview/sha256/" + hashlib.sha256(decision_raw).hexdigest(),
        "--expected-release-version",
        VERSION,
        "--expected-channel",
        "preview",
        "--expected-platform",
        "macos",
        "--expected-rid",
        "osx-arm64",
        "--expected-heads",
        "avalonia,blazor-desktop",
        "--output",
        str(output),
    ]
    if not preflight:
        rows = artifacts or [
            artifact("avalonia-osx-arm64-installer", "avalonia"),
            artifact("blazor-desktop-osx-arm64-installer", "blazor-desktop"),
        ]
        manifest = tmp_path / "RELEASE_CHANNEL.generated.json"
        write_json(
            manifest,
            {"version": VERSION, "channel": "preview", "artifacts": rows},
        )
        promotion = tmp_path / "public-promotion.json"
        write_json(
            promotion,
            {
                "contractName": "chummer.run.desktop_release_publication",
                "artifacts": evidence
                or [
                    {
                        "artifactId": row["artifactId"],
                        "promotionStatus": "pass",
                        "signingStatus": "skipped_preview",
                        "notarizationStatus": "skipped_preview",
                    }
                    for row in rows
                ],
            },
        )
        command[2:2] = [
            "--manifest",
            str(manifest),
            "--promotion-evidence",
            str(promotion),
        ]
    return subprocess.run(command, capture_output=True, text=True), output


def test_approved_scope_binds_primary_fallback_and_exact_inventory(tmp_path: Path) -> None:
    result, output = invoke(tmp_path)
    assert result.returncode == 0, result.stderr
    receipt = json.loads(output.read_text())
    assert receipt["status"] == "pass"
    assert receipt["verificationPhase"] == "candidate_inventory"
    assert receipt["platforms"][0]["primaryHead"] == "avalonia"
    assert receipt["platforms"][0]["fallbackHeads"] == ["blazor-desktop"]
    assert receipt["exactIncomingDesktopScope"] == (
        "avalonia:macos:osx-arm64,blazor-desktop:macos:osx-arm64"
    )
    assert output.stat().st_mode & 0o777 == 0o600


def test_preflight_projects_exact_runtime_scope_without_manifest(tmp_path: Path) -> None:
    result, output = invoke(tmp_path, preflight=True)
    assert result.returncode == 0, result.stderr
    receipt = json.loads(output.read_text())
    assert receipt["verificationPhase"] == "scope_approval"
    assert receipt["artifactIds"] == []


def test_rejects_undeclared_head_and_missing_fallback_inventory(tmp_path: Path) -> None:
    rows = [artifact("avalonia-osx-arm64-installer", "avalonia")]
    result, output = invoke(tmp_path, artifacts=rows)
    assert result.returncode == 1
    assert "does not exactly match scope" in result.stderr
    assert not output.exists()

    second = tmp_path / "second"
    second.mkdir()
    rows.append(artifact("rogue-osx-arm64-installer", "rogue"))
    result, output = invoke(second, artifacts=rows)
    assert result.returncode == 1
    assert "outside approved head/RID scope" in result.stderr
    assert not output.exists()


def test_rejects_access_or_signing_outside_approved_policy(tmp_path: Path) -> None:
    rows = [
        artifact("avalonia-osx-arm64-installer", "avalonia"),
        artifact("blazor-desktop-osx-arm64-installer", "blazor-desktop"),
    ]
    rows[0]["installAccessClass"] = "account_required"
    result, output = invoke(tmp_path, artifacts=rows)
    assert result.returncode == 1
    assert "unapproved access class" in result.stderr
    assert not output.exists()

    second = tmp_path / "second"
    second.mkdir()
    strict = decision()
    strict["platforms"][0]["signingRequirement"] = "signed"  # type: ignore[index]
    evidence = [
        {
            "artifactId": row["artifactId"],
            "promotionStatus": "pass",
            "signingStatus": "skipped_preview",
            "notarizationStatus": "skipped_preview",
        }
        for row in [
            artifact("avalonia-osx-arm64-installer", "avalonia"),
            artifact("blazor-desktop-osx-arm64-installer", "blazor-desktop"),
        ]
    ]
    result, output = invoke(second, scope=strict, evidence=evidence)
    assert result.returncode == 1
    assert "lacks required signing proof" in result.stderr
    assert not output.exists()


def test_rejects_multi_platform_scope_on_platform_specific_mac_builder(tmp_path: Path) -> None:
    scope = decision()
    scope["platforms"] = [
        {
            "platform": "linux",
            "rid": "linux-x64",
            "primaryHead": "avalonia",
            "fallbackHeads": [],
            "artifactAccessClass": "open_public",
            "signingRequirement": "not_applicable",
        },
        *scope["platforms"],  # type: ignore[list-item]
    ]
    result, output = invoke(tmp_path, scope=scope, preflight=True)
    assert result.returncode == 1
    assert "exactly macos" in result.stderr
    assert not output.exists()


def test_rejects_noncanonical_mac_builder_head_id(tmp_path: Path) -> None:
    scope = decision()
    scope["platforms"][0]["fallbackHeads"] = ["blazor"]  # type: ignore[index]
    result, output = invoke(
        tmp_path,
        scope=scope,
        preflight=True,
    )
    assert result.returncode == 1
    assert "unsupported product head" in result.stderr
    assert not output.exists()


def test_rejects_platform_alias_and_incompatible_rid_in_runtime_decision(
    tmp_path: Path,
) -> None:
    aliased = decision()
    aliased["platforms"][0]["platform"] = "osx"  # type: ignore[index]
    result, output = invoke(tmp_path, scope=aliased, preflight=True)
    assert result.returncode == 1
    assert "canonical supported desktop platform" in result.stderr
    assert not output.exists()

    second = tmp_path / "second"
    second.mkdir()
    mismatched = decision()
    mismatched["platforms"][0]["rid"] = "win-x64"  # type: ignore[index]
    result, output = invoke(second, scope=mismatched, preflight=True)
    assert result.returncode == 1
    assert "incompatible with platform macos" in result.stderr
    assert not output.exists()


def test_rejects_unresolved_approval_or_support_owner(tmp_path: Path) -> None:
    unresolved = decision()
    unresolved["approvedBy"] = "pending"
    result, output = invoke(tmp_path, scope=unresolved, preflight=True)
    assert result.returncode == 1
    assert "resolved release authority owner" in result.stderr
    assert not output.exists()

    second = tmp_path / "second"
    second.mkdir()
    unresolved = decision()
    unresolved["supportOwner"] = "TBD"
    result, output = invoke(second, scope=unresolved, preflight=True)
    assert result.returncode == 1
    assert "resolved release authority owner" in result.stderr
    assert not output.exists()

def test_rejects_digest_drift_before_using_authority(tmp_path: Path) -> None:
    decision_path = tmp_path / "decision.json"
    write_json(decision_path, decision())
    output = tmp_path / "receipt.json"
    base = [
        sys.executable,
        str(SCRIPT),
        "--decision",
        str(decision_path),
        "--expected-sha256",
        "0" * 64,
        "--authority",
        "file:///tmp/decision.json",
        "--output",
        str(output),
    ]
    result = subprocess.run(base, capture_output=True, text=True)
    assert result.returncode == 1
    assert "SHA-256 does not match" in result.stderr
    assert not output.exists()


def test_rejects_mutable_https_authority_without_exact_digest(tmp_path: Path) -> None:
    decision_path = tmp_path / "decision.json"
    raw = write_json(decision_path, decision())
    output = tmp_path / "receipt.json"
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--decision",
            str(decision_path),
            "--expected-sha256",
            hashlib.sha256(raw).hexdigest(),
            "--authority",
            "https://design.example/releases/current-scope.json",
            "--output",
            str(output),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    assert "design://release-scope/<decisionId>/sha256/<decisionSha256>" in result.stderr
    assert not output.exists()


def test_rejects_noncanonical_json_encoding_even_when_digest_matches(
    tmp_path: Path,
) -> None:
    decision_path = tmp_path / "decision.json"
    raw = (json.dumps(decision(), indent=2, ensure_ascii=False) + "\n").encode()
    decision_path.write_bytes(raw)
    decision_path.chmod(0o600)
    digest = hashlib.sha256(raw).hexdigest()
    output = tmp_path / "receipt.json"
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--decision",
            str(decision_path),
            "--expected-sha256",
            digest,
            "--authority",
            f"design://release-scope/scope-run-20260721-macos-preview/sha256/{digest}",
            "--output",
            str(output),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    assert "canonical compact sorted UTF-8 JSON plus LF" in result.stderr
    assert not output.exists()

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "stage-release-candidate-evidence.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("stage_release_candidate_evidence", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _candidate_fixture(tmp_path: Path) -> dict[str, object]:
    channel = "preview"
    version = "run-A"
    files_dir = tmp_path / "files"
    receipt_root = tmp_path / "receipts"
    files_dir.mkdir()
    receipt_root.mkdir()

    definitions = (
        {
            "artifact_id": "avalonia-linux-x64-installer",
            "head": "avalonia",
            "platform": "linux",
            "rid": "linux-x64",
            "file_name": "chummer-avalonia-linux-x64-installer.deb",
            "data": b"run-A-linux-installer",
            "recorded": "2026-07-18T01:00:00+00:00",
        },
        {
            "artifact_id": "avalonia-win-x64-installer",
            "head": "avalonia",
            "platform": "windows",
            "rid": "win-x64",
            "file_name": "chummer-avalonia-win-x64-installer.exe",
            "data": b"run-A-windows-installer",
            "recorded": "2026-07-18T01:01:00+00:00",
        },
    )

    artifacts = []
    tuples = []
    evidence_rows = []
    receipt_payloads: dict[str, dict] = {}
    for definition in definitions:
        artifact_id = str(definition["artifact_id"])
        head = str(definition["head"])
        platform = str(definition["platform"])
        rid = str(definition["rid"])
        file_name = str(definition["file_name"])
        data = bytes(definition["data"])
        digest = _sha256(data)
        (files_dir / file_name).write_bytes(data)
        receipt_name = f"startup-smoke-{head}-{rid}.receipt.json"
        artifacts.append(
            {
                "artifactId": artifact_id,
                "head": head,
                "platform": platform,
                "rid": rid,
                "kind": "installer",
                "fileName": file_name,
                "sha256": digest,
                "channel": channel,
                "version": version,
            }
        )
        tuples.append(
            {
                "tupleId": f"{head}:{platform}:{rid}",
                "artifactId": artifact_id,
                "head": head,
                "platform": platform,
                "rid": rid,
                "kind": "installer",
            }
        )
        receipt_payload = {
            "status": "pass",
            "artifactId": artifact_id,
            "headId": head,
            "platform": platform,
            "rid": rid,
            "channelId": channel,
            "channel": channel,
            "releaseVersion": version,
            "version": version,
            "artifactFileName": file_name,
            "fileName": file_name,
            "artifactPath": str(files_dir / file_name),
            "artifactRelativePath": f"files/{file_name}",
            "artifactSha256": digest,
            "artifactDigest": f"sha256:{digest}",
            "recordedAtUtc": definition["recorded"],
        }
        receipt_payloads[receipt_name] = receipt_payload
        _write_json(receipt_root / receipt_name, receipt_payload)
        evidence_rows.append(
            {
                "artifactId": artifact_id,
                "fileName": file_name,
                "platform": platform,
                "kind": "installer",
                "promotionStatus": "pass",
                "startupSmokeStatus": "pass",
                "startupSmokeReceiptPath": f"startup-smoke/{receipt_name}",
                "artifactSha256": digest,
                "artifactSizeBytes": len(data),
            }
        )

    manifest_path = tmp_path / "RELEASE_CHANNEL.generated.json"
    _write_json(
        manifest_path,
        {
            "channelId": channel,
            "channel": channel,
            "version": version,
            "artifacts": artifacts,
            "desktopTupleCoverage": {"promotedInstallerTuples": tuples},
        },
    )
    evidence_path = tmp_path / "public-promotion.json"
    _write_json(
        evidence_path,
        {
            "contractName": "chummer.run.desktop_release_publication",
            "channel": channel,
            "version": version,
            "artifacts": evidence_rows,
        },
    )
    return {
        "channel": channel,
        "version": version,
        "files_dir": files_dir,
        "receipt_root": receipt_root,
        "receipt_payloads": receipt_payloads,
        "manifest_path": manifest_path,
        "evidence_path": evidence_path,
        "evidence_rows": evidence_rows,
    }


def _stage(module, fixture: dict[str, object], target: Path):
    return module.stage_release_candidate_evidence(
        manifest_path=fixture["manifest_path"],
        files_dir=fixture["files_dir"],
        release_evidence_path=fixture["evidence_path"],
        receipt_roots=[fixture["receipt_root"]],
        target_startup_smoke_dir=target,
    )


def test_exact_candidate_identity_is_staged_without_restamping(tmp_path: Path) -> None:
    module = _load_module()
    fixture = _candidate_fixture(tmp_path)
    target = tmp_path / "staged"

    result = _stage(module, fixture, target)

    assert result["status"] == "pass"
    assert result["channel"] == fixture["channel"]
    assert result["releaseVersion"] == fixture["version"]
    assert result["stagedReceiptCount"] == 2
    for receipt_name, expected_payload in fixture["receipt_payloads"].items():
        assert json.loads((target / receipt_name).read_text(encoding="utf-8")) == expected_payload


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    (
        ("releaseVersion", "run-B", "release version"),
        ("version", "run-B", "release version"),
        ("channelId", "public_stable", "channel"),
        ("artifactSha256", "0" * 64, "artifact digest"),
    ),
)
def test_same_named_receipt_from_another_identity_is_rejected_before_staging(
    tmp_path: Path,
    field: str,
    value: str,
    reason: str,
) -> None:
    module = _load_module()
    fixture = _candidate_fixture(tmp_path)
    receipt_root = fixture["receipt_root"]
    receipt_path = receipt_root / "startup-smoke-avalonia-win-x64.receipt.json"
    payload = json.loads(receipt_path.read_text(encoding="utf-8"))
    payload[field] = value
    _write_json(receipt_path, payload)
    target = tmp_path / "staged"

    with pytest.raises(module.CandidateEvidenceError, match=reason):
        _stage(module, fixture, target)

    assert target.is_dir()
    assert list(target.iterdir()) == []


def test_out_of_scope_receipt_is_not_staged(tmp_path: Path) -> None:
    module = _load_module()
    fixture = _candidate_fixture(tmp_path)
    extra_name = "startup-smoke-avalonia-osx-arm64.receipt.json"
    extra_payload = {
        "status": "pass",
        "channelId": fixture["channel"],
        "releaseVersion": fixture["version"],
        "artifactId": "avalonia-osx-arm64-installer",
        "headId": "avalonia",
        "platform": "macos",
        "rid": "osx-arm64",
        "artifactFileName": "chummer-avalonia-osx-arm64-installer.dmg",
        "artifactSha256": "1" * 64,
    }
    _write_json(fixture["receipt_root"] / extra_name, extra_payload)
    target = tmp_path / "staged"

    _stage(module, fixture, target)

    assert not (target / extra_name).exists()
    assert sorted(path.name for path in target.iterdir()) == sorted(fixture["receipt_payloads"])


def test_stale_or_extra_public_promotion_evidence_fails_closed_and_cleans_stage(
    tmp_path: Path,
) -> None:
    module = _load_module()
    fixture = _candidate_fixture(tmp_path)
    evidence = json.loads(fixture["evidence_path"].read_text(encoding="utf-8"))
    evidence["artifacts"][0]["artifactSha256"] = "2" * 64
    evidence["artifacts"].append(
        {
            "artifactId": "avalonia-osx-arm64-installer",
            "fileName": "chummer-avalonia-osx-arm64-installer.dmg",
            "platform": "macos",
            "kind": "installer",
            "promotionStatus": "pass",
            "startupSmokeStatus": "pass",
            "startupSmokeReceiptPath": "startup-smoke/startup-smoke-avalonia-osx-arm64.receipt.json",
            "artifactSha256": "3" * 64,
            "artifactSizeBytes": 1,
        }
    )
    _write_json(fixture["evidence_path"], evidence)
    target = tmp_path / "staged"

    with pytest.raises(module.CandidateEvidenceError, match="artifact set disagrees"):
        _stage(module, fixture, target)

    assert list(target.iterdir()) == []


def test_public_promotion_digest_must_match_candidate_bytes(tmp_path: Path) -> None:
    module = _load_module()
    fixture = _candidate_fixture(tmp_path)
    evidence = json.loads(fixture["evidence_path"].read_text(encoding="utf-8"))
    evidence["artifacts"][0]["artifactSha256"] = "2" * 64
    _write_json(fixture["evidence_path"], evidence)
    target = tmp_path / "staged"

    with pytest.raises(module.CandidateEvidenceError, match="public evidence digest"):
        _stage(module, fixture, target)

    assert list(target.iterdir()) == []

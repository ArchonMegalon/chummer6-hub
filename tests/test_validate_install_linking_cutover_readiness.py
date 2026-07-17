from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from scripts.validate_install_linking_cutover_readiness import (
    ReadinessValidationError,
    _expected_deployment_identity,
    _read_owner_only_receipt,
    validate_readiness,
)

NOW = datetime(2026, 7, 16, 12, 0, tzinfo=UTC)
SOURCE_FINGERPRINT = "a" * 64
FULL_DEPLOYMENT_DIGEST = "b" * 64


def valid_payload() -> dict[str, object]:
    return {
        "ready": True,
        "status": "ready",
        "generatedAt": NOW.isoformat(),
        "hub": {
            "contractName": "chummer.run.api.deep_readiness.v2",
            "service": "chummer.run.api",
            "ready": True,
            "status": "pass",
            "checks": [
                {
                    "name": "install_linking_store",
                    "passed": True,
                    "status": "pass",
                    "code": "postgres_authority_bound",
                }
            ],
        },
        "playProjection": {"ready": True, "status": "ready"},
        "deploymentIdentity": {
            "ready": True,
            "code": "overlay_identity_bound",
            "sourceFingerprintSha256": SOURCE_FINGERPRINT,
            "fullDeploymentDigestSha256": FULL_DEPLOYMENT_DIGEST,
        },
    }


def test_accepts_current_passing_contract() -> None:
    validate_readiness(
        valid_payload(),
        expected_source_fingerprint_sha256=SOURCE_FINGERPRINT,
        expected_full_deployment_digest_sha256=FULL_DEPLOYMENT_DIGEST,
        not_before_utc=NOW - timedelta(seconds=1),
        now_utc=NOW,
    )


@pytest.mark.parametrize(
    "mutation",
    [
        lambda payload: payload.update(ready=False),
        lambda payload: payload["hub"].update(contractName="chummer.run.api.deep_readiness.v1"),
        lambda payload: payload["hub"]["checks"][0].update(passed=False),
        lambda payload: payload["hub"]["checks"][0].update(code="not_postgres"),
        lambda payload: payload["hub"].update(checks=[]),
        lambda payload: payload.update(playProjection={"ready": False}),
        lambda payload: payload["deploymentIdentity"].update(sourceFingerprintSha256="b" * 64),
        lambda payload: payload["deploymentIdentity"].update(fullDeploymentDigestSha256="c" * 64),
        lambda payload: payload.update(generatedAt="2000-01-01T00:00:00+00:00"),
    ],
)
def test_rejects_false_or_drifted_readiness(mutation) -> None:
    payload = valid_payload()
    mutation(payload)
    with pytest.raises(ReadinessValidationError):
        validate_readiness(
            payload,
            expected_source_fingerprint_sha256=SOURCE_FINGERPRINT,
            expected_full_deployment_digest_sha256=FULL_DEPLOYMENT_DIGEST,
            not_before_utc=NOW - timedelta(seconds=1),
            now_utc=NOW,
        )


def test_receipt_reader_rejects_group_readable_file(tmp_path: Path) -> None:
    receipt = tmp_path / "readiness.json"
    receipt.write_text(json.dumps(valid_payload()), encoding="utf-8")
    receipt.chmod(0o640)

    with pytest.raises(ReadinessValidationError, match="owner-only"):
        _read_owner_only_receipt(receipt)


def test_receipt_reader_rejects_symlink(tmp_path: Path) -> None:
    target = tmp_path / "target.json"
    target.write_text(json.dumps(valid_payload()), encoding="utf-8")
    target.chmod(0o600)
    receipt = tmp_path / "readiness.json"
    receipt.symlink_to(target)

    with pytest.raises(ReadinessValidationError):
        _read_owner_only_receipt(receipt)


@pytest.mark.parametrize(
    "injected",
    ('"ready":false,', '"unrelated":NaN,'),
)
def test_receipt_reader_rejects_ambiguous_json(
    tmp_path: Path,
    injected: str,
) -> None:
    receipt = tmp_path / "readiness.json"
    payload = json.dumps(valid_payload()).replace("{", "{" + injected, 1)
    receipt.write_text(payload, encoding="utf-8")
    receipt.chmod(0o600)

    with pytest.raises(ReadinessValidationError):
        _read_owner_only_receipt(receipt)


@pytest.mark.parametrize(
    "payload",
    (
        '{"sourceFingerprint":{},"sourceFingerprint":{}}',
        '{"sourceFingerprint":{},"unrelated":NaN}',
    ),
)
def test_build_info_reader_rejects_ambiguous_json(
    tmp_path: Path,
    payload: str,
) -> None:
    build_info = tmp_path / "build-info.json"
    build_info.write_text(payload, encoding="utf-8")

    with pytest.raises(ReadinessValidationError):
        _expected_deployment_identity(build_info)

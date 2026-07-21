from __future__ import annotations

import datetime as dt
import hashlib
import json
from pathlib import Path

import pytest

from scripts import accept_live_campaign_release as runner


TARGET = {
    "releaseVersion": "nightly-20260721",
    "generationId": "generation-20260721",
    "manifestSha256": "a" * 64,
    "decisionSha256": "b" * 64,
    "snapshotSha256": "c" * 64,
    "targetPointerSha256": "d" * 64,
}


def canonical(payload: object) -> bytes:
    return (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode()


def write_json(path: Path, payload: object, *, canonical_bytes: bool = True) -> str:
    raw = canonical(payload) if canonical_bytes else (json.dumps(payload, indent=2) + "\n").encode()
    path.write_bytes(raw)
    path.chmod(0o600)
    return hashlib.sha256(raw).hexdigest()


def utc(value: dt.datetime) -> str:
    return value.astimezone(dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def finalization(now: dt.datetime) -> dict[str, object]:
    return {
        "contractName": "chummer.staged-release-owner-finalization/v1",
        "contractVersion": 1,
        "status": "preview_ready",
        "releaseVersion": TARGET["releaseVersion"],
        "generationId": TARGET["generationId"],
        "stageReceiptId": "stage-receipt-test",
        "manifestSha256": TARGET["manifestSha256"],
        "releaseScopeDecisionSha256": "1" * 64,
        "releaseScopeVerificationSha256": "2" * 64,
        "exactIncomingDesktopScope": (
            "avalonia:macos:osx-arm64,blazor-desktop:macos:osx-arm64"
        ),
        "snapshotSha256": TARGET["snapshotSha256"],
        "decisionSha256": TARGET["decisionSha256"],
        "authorityRevisionId": "auth-" + "e" * 64,
        "targetPointerSha256": TARGET["targetPointerSha256"],
        "completedAtUtc": utc(now - dt.timedelta(minutes=10)),
    }


def permit(now: dt.datetime) -> dict[str, object]:
    return {
        "contractName": runner.PERMIT_CONTRACT,
        "contractVersion": 1,
        "status": "approved",
        "secretRedacted": True,
        "permitId": "permit-test-20260721",
        "issuedAtUtc": utc(now - dt.timedelta(minutes=1)),
        "expiresAtUtc": utc(now + dt.timedelta(minutes=20)),
        "allowedOrigin": runner.PRODUCTION_ORIGIN,
        "allowedActions": list(runner.ALLOWED_ACTIONS),
        "releaseBinding": TARGET,
    }


def state(role: str) -> dict[str, object]:
    return {
        "cookies": [
            {
                "name": "session",
                "value": f"opaque-{role}-value",
                "domain": ".chummer.run",
                "path": "/",
            }
        ],
        "origins": [
            {
                "origin": "https://chummer.run",
                "localStorage": [{"name": "opaque-state", "value": f"opaque-{role}"}],
            }
        ],
    }


@pytest.fixture
def bundle(tmp_path: Path) -> dict[str, object]:
    tmp_path.chmod(0o700)
    now = dt.datetime(2026, 7, 21, 12, 0, tzinfo=dt.timezone.utc)
    final_path = tmp_path / "finalization.json"
    final_sha = write_json(final_path, finalization(now))
    permit_path = tmp_path / "permit.json"
    permit_sha = write_json(permit_path, permit(now))
    states: dict[str, tuple[Path, str]] = {}
    for role in sorted(runner.ROLES):
        path = tmp_path / f"{role}.json"
        states[role] = (path, write_json(path, state(role), canonical_bytes=False))
    return {
        "root": tmp_path,
        "now": now,
        "final_path": final_path,
        "final_sha": final_sha,
        "permit_path": permit_path,
        "permit_sha": permit_sha,
        "states": states,
    }


def invoke(bundle: dict[str, object], output: Path | None = None) -> dict[str, object]:
    return runner.build_evidence(
        workspace=bundle["root"],
        finalization_receipt=bundle["final_path"],
        finalization_sha256=bundle["final_sha"],
        storage_states=bundle["states"],
        mutation_permit=bundle["permit_path"],
        mutation_permit_sha256=bundle["permit_sha"],
        evidence_id="multi-account-test-20260721",
        output=output or bundle["root"] / "evidence.json",
        observed_at=bundle["now"],
    )


def test_attention_only_envelope_is_secret_safe_and_mode_0600(bundle: dict[str, object]) -> None:
    output = bundle["root"] / "evidence.json"
    evidence = invoke(bundle, output)
    assert evidence["status"] == "attention_required"
    assert evidence["operationalReadinessClaimAllowed"] is False
    assert evidence["releaseBinding"] == TARGET
    assert evidence["evidenceKind"] == "multi_account_live_journey"
    assert [claim["status"] for claim in evidence["claims"]] == [
        "pass",
        "pass",
        "attention_required",
    ]
    assert output.stat().st_mode & 0o777 == 0o600
    rendered = output.read_text()
    assert "opaque-" not in rendered
    assert str(bundle["root"]) not in rendered
    assert "@girschele.com" not in rendered
    row, ready, _ = runner.acceptance._validate_evidence(
        evidence,
        TARGET,
        runner.EVIDENCE_KIND,
        completed_at=bundle["now"] - dt.timedelta(minutes=10),
        observed_at=bundle["now"],
    )
    assert row["evidenceKind"] == runner.EVIDENCE_KIND
    assert ready is False


def test_shared_storage_state_is_rejected(bundle: dict[str, object]) -> None:
    states = dict(bundle["states"])
    states["bob_runner"] = states["alice_runner"]
    bundle["states"] = states
    with pytest.raises(runner.JourneyError, match="shared_or_duplicate"):
        invoke(bundle)


def test_missing_or_extra_role_is_rejected(bundle: dict[str, object]) -> None:
    states = dict(bundle["states"])
    states.pop("depleted_runner")
    bundle["states"] = states
    with pytest.raises(runner.JourneyError, match="role_denominator"):
        invoke(bundle)


def test_unsafe_storage_mode_is_rejected(bundle: dict[str, object]) -> None:
    path, _ = bundle["states"]["alice_runner"]
    path.chmod(0o644)
    with pytest.raises(runner.acceptance.AcceptanceError, match="mode-0600"):
        invoke(bundle)


def test_symlinked_storage_state_is_rejected(bundle: dict[str, object]) -> None:
    path, digest = bundle["states"]["alice_runner"]
    link = bundle["root"] / "alice-link.json"
    link.symlink_to(path)
    states = dict(bundle["states"])
    states["alice_runner"] = (link, digest)
    bundle["states"] = states
    with pytest.raises(runner.acceptance.AcceptanceError):
        invoke(bundle)


def test_expired_permit_is_rejected(bundle: dict[str, object]) -> None:
    payload = permit(bundle["now"])
    payload["expiresAtUtc"] = utc(bundle["now"] - dt.timedelta(seconds=1))
    bundle["permit_sha"] = write_json(bundle["permit_path"], payload)
    with pytest.raises(runner.JourneyError, match="expired_or_unbounded"):
        invoke(bundle)


def test_release_binding_drift_is_rejected(bundle: dict[str, object]) -> None:
    payload = permit(bundle["now"])
    payload["releaseBinding"] = {**TARGET, "generationId": "wrong-generation"}
    bundle["permit_sha"] = write_json(bundle["permit_path"], payload)
    with pytest.raises(runner.JourneyError, match="mutation_permit:invalid"):
        invoke(bundle)


def test_test_identity_and_nonproduction_state_are_rejected(bundle: dict[str, object]) -> None:
    path, _ = bundle["states"]["gm_campaign"]
    payload = state("gm_campaign")
    payload["origins"][0]["localStorage"][0]["name"] = "X-Test-Identity"
    states = dict(bundle["states"])
    states["gm_campaign"] = (path, write_json(path, payload, canonical_bytes=False))
    bundle["states"] = states
    with pytest.raises(runner.JourneyError, match="unsafe_schema"):
        invoke(bundle)


def test_existing_output_is_not_replaced(bundle: dict[str, object]) -> None:
    output = bundle["root"] / "evidence.json"
    output.write_text("owner data")
    output.chmod(0o600)
    with pytest.raises(runner.acceptance.AcceptanceError):
        invoke(bundle, output)
    assert output.read_text() == "owner data"


def cli_args(bundle: dict[str, object], output: Path) -> list[str]:
    args = [
        "--workspace",
        str(bundle["root"]),
        "--finalization-receipt",
        str(bundle["final_path"]),
        "--expected-finalization-sha256",
        bundle["final_sha"],
        "--mutation-permit",
        str(bundle["permit_path"]),
        "--expected-mutation-permit-sha256",
        bundle["permit_sha"],
        "--evidence-id",
        "multi-account-cli-20260721",
        "--output",
        str(output),
    ]
    for role, (path, digest) in sorted(bundle["states"].items()):
        args.extend(["--storage-state", f"{role}={path}"])
        args.extend(["--storage-state-sha256", f"{role}={digest}"])
    return args


def test_cli_attention_is_nonzero_without_explicit_observation_mode(
    bundle: dict[str, object],
) -> None:
    live_now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
    bundle["final_sha"] = write_json(bundle["final_path"], finalization(live_now))
    bundle["permit_sha"] = write_json(bundle["permit_path"], permit(live_now))
    assert runner.main(cli_args(bundle, bundle["root"] / "gate.json")) == 2
    assert runner.main(
        [
            *cli_args(bundle, bundle["root"] / "observation.json"),
            "--allow-attention-required",
        ]
    ) == 0

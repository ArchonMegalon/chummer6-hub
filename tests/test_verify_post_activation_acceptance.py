from __future__ import annotations

import datetime as dt
import hashlib
import importlib.util
import json
import os
from pathlib import Path

import pytest


SCRIPT = Path(__file__).parents[1] / "scripts" / "verify_post_activation_acceptance.py"
SPEC = importlib.util.spec_from_file_location("verify_post_activation_acceptance", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)

OBSERVED_AT = dt.datetime(2026, 7, 21, 12, 2, tzinfo=dt.timezone.utc)
TARGET = {
    "releaseVersion": "run-test",
    "generationId": "gen-test",
    "manifestSha256": "a" * 64,
    "decisionSha256": "c" * 64,
    "snapshotSha256": "b" * 64,
    "targetPointerSha256": "d" * 64,
}
COMPARED_FIELDS = [
    "releaseVersion",
    "channel",
    "releaseStatus",
    "rolloutState",
    "supportabilityState",
    "availablePlatforms",
    "primaryHeadByPlatform",
    "artifactCount",
    "downloadAccessPosture",
    "knownIssueSummary",
    "manifestSha256",
    "registryCommit",
    "releaseDecisionStatus",
    "releaseDecisionSha256",
]


def _canonical(payload: object) -> bytes:
    return (
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        + "\n"
    ).encode()


def _write(path: Path, payload: object, *, canonical: bool = True) -> str:
    raw = _canonical(payload) if canonical else (json.dumps(payload, indent=2) + "\n").encode()
    path.write_bytes(raw)
    path.chmod(0o600)
    return hashlib.sha256(raw).hexdigest()


def _utc(value: dt.datetime) -> str:
    return value.astimezone(dt.timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )


def _finalization(completed_at: dt.datetime) -> dict[str, object]:
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
        "completedAtUtc": _utc(completed_at),
    }


def _convergence(role: str, generated_at: dt.datetime) -> dict[str, object]:
    route = (
        f"/api/v1/public/release-truth/g/{TARGET['generationId']}"
        if role == "generation"
        else "/api/v1/public/release-truth"
    )
    release_truth = {
        "contractName": "chummer.release-truth-projection/v1",
        "releaseVersion": TARGET["releaseVersion"],
        "channel": "preview",
        "releaseStatus": "published",
        "rolloutState": "complete",
        "supportabilityState": "supported",
        "availablePlatforms": ["windows"],
        "primaryHeadByPlatform": {"windows": "artifact-test"},
        "artifactCount": 1,
        "downloadAccessPosture": "open_public",
        "knownIssueSummary": "No blocking known issues.",
        "manifestSha256": TARGET["manifestSha256"],
        "registryCommit": "4" * 40,
        "releaseDecisionStatus": "preview_ready",
        "releaseDecisionSha256": TARGET["decisionSha256"],
    }
    if role == "generation":
        checked_routes = set(
            MODULE.CONVERGENCE_HELPERS.generation_routes(TARGET["generationId"])
        )
        checked_routes.add(
            f"/downloads/g/{TARGET['generationId']}/install/artifact-test"
        )
    else:
        checked_routes = set(MODULE.CONVERGENCE_HELPERS.DEFAULT_ROUTES)
        checked_routes.add("/downloads/install/artifact-test")
    checked_routes = sorted(checked_routes)
    return {
        "contractName": "chummer.live-release-convergence/v1",
        "contractVersion": 1,
        "generatedAtUtc": _utc(generated_at),
        "verificationMode": "committed_public",
        "status": "pass",
        "mismatchCount": 0,
        "failureCount": 0,
        "mismatches": [],
        "failures": [],
        "releaseVersion": TARGET["releaseVersion"],
        "manifestSha256": TARGET["manifestSha256"],
        "releaseDecisionStatus": "preview_ready",
        "authoritySnapshotSha256": TARGET["snapshotSha256"],
        "releaseDecisionSha256": TARGET["decisionSha256"],
        "authorityRoute": route,
        "checkedRouteCount": len(checked_routes),
        "checkedRoutes": checked_routes,
        "comparedFields": COMPARED_FIELDS,
        "releaseTruth": release_truth,
    }


def _evidence(
    kind: str,
    evidence_id: str,
    generated_at: dt.datetime,
    *,
    status: str = "ready",
    readiness: bool | None = True,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "contractName": "chummer.post-activation-evidence/v1",
        "contractVersion": 1,
        "status": status,
        "secretRedacted": True,
        "evidenceId": evidence_id,
        "evidenceKind": kind,
        "generatedAtUtc": _utc(generated_at),
        "releaseBinding": dict(TARGET),
        "claims": [
            {
                "claimId": f"{kind}-claim",
                "status": "pass",
                "evidenceSha256": "3" * 64,
            }
        ],
    }
    if readiness is not None:
        payload["operationalReadinessClaimAllowed"] = readiness
    return payload


def _manifest(release_truth: dict[str, object]) -> dict[str, object]:
    truth = json.loads(json.dumps(release_truth))
    return {
        "version": TARGET["releaseVersion"],
        "channel": "preview",
        "status": "published",
        "rolloutState": "complete",
        "supportabilityState": "supported",
        "downloadAccessPosture": "open_public",
        "knownIssueSummary": "No blocking known issues.",
        "manifestSha256": TARGET["manifestSha256"],
        "registryCommit": "4" * 40,
        "releaseDecisionStatus": "preview_ready",
        "releaseDecisionSha256": TARGET["decisionSha256"],
        "artifactCount": 1,
        "availablePlatforms": ["windows"],
        "primaryHeadByPlatform": {"windows": "artifact-test"},
        "downloads": [
            {
                "id": "artifact-test",
                "platformId": "windows",
                "head": "artifact-test",
                "installAccessClass": "open_public",
            }
        ],
        "releaseTruth": truth,
    }


def _bundle(
    tmp_path: Path,
    *,
    kinds: tuple[str, ...] = (
        "horizon_live_readiness",
        "multi_account_live_journey",
    ),
    observed_at: dt.datetime = OBSERVED_AT,
) -> dict[str, object]:
    workspace = tmp_path / "workspace"
    workspace.mkdir(mode=0o700, parents=True)
    workspace.chmod(0o700)
    completed_at = observed_at - dt.timedelta(minutes=3)
    generation_at = observed_at - dt.timedelta(minutes=2)
    evidence_at = observed_at - dt.timedelta(minutes=1)
    finalization = workspace / "finalization.json"
    generation = workspace / "generation.json"
    current = workspace / "current.json"
    manifest = workspace / "release-manifest.json"
    generation_payload = _convergence("generation", generation_at)
    current_payload = _convergence("current", observed_at)
    finalization_payload = _finalization(completed_at)
    manifest_payload = _manifest(generation_payload["releaseTruth"])
    bundle: dict[str, object] = {
        "workspace": workspace,
        "finalization": finalization,
        "finalization_sha": _write(finalization, finalization_payload),
        "finalization_payload": finalization_payload,
        "generation": generation,
        "generation_sha": _write(generation, generation_payload),
        "generation_payload": generation_payload,
        "current": current,
        "current_sha": _write(current, current_payload),
        "current_payload": current_payload,
        "manifest": manifest,
        "manifest_sha": _write(manifest, manifest_payload),
        "manifest_payload": manifest_payload,
        "evidence": {},
        "evidence_payloads": {},
        "observed_at": observed_at,
    }
    for index, kind in enumerate(kinds):
        path = workspace / f"evidence-{kind}.json"
        payload = _evidence(kind, f"evidence-{index}", evidence_at)
        digest = _write(path, payload)
        bundle["evidence"][kind] = (path, digest)  # type: ignore[index]
        bundle["evidence_payloads"][kind] = payload  # type: ignore[index]
    return bundle


def _verify(bundle: dict[str, object], *, output: Path | None = None):
    workspace = bundle["workspace"]
    assert isinstance(workspace, Path)
    return MODULE.verify(
        workspace=workspace,
        finalization_receipt=bundle["finalization"],
        finalization_sha256=bundle["finalization_sha"],
        generation_convergence=bundle["generation"],
        generation_convergence_sha256=bundle["generation_sha"],
        current_convergence=bundle["current"],
        current_convergence_sha256=bundle["current_sha"],
        release_manifest=bundle["manifest"],
        release_manifest_file_sha256=bundle["manifest_sha"],
        required_evidence=bundle["evidence"],
        output=output or workspace / "acceptance.json",
        observed_at=bundle["observed_at"],
    )


def _cli_args(bundle: dict[str, object], output: Path) -> list[str]:
    evidence = bundle["evidence"]
    assert isinstance(evidence, dict)
    args = [
        "--workspace",
        str(bundle["workspace"]),
        "--finalization-receipt",
        str(bundle["finalization"]),
        "--expected-finalization-sha256",
        str(bundle["finalization_sha"]),
        "--generation-convergence",
        str(bundle["generation"]),
        "--expected-generation-convergence-sha256",
        str(bundle["generation_sha"]),
        "--current-convergence",
        str(bundle["current"]),
        "--expected-current-convergence-sha256",
        str(bundle["current_sha"]),
        "--release-manifest",
        str(bundle["manifest"]),
        "--expected-release-manifest-file-sha256",
        str(bundle["manifest_sha"]),
    ]
    for kind, (path, digest) in evidence.items():
        args.extend(["--require-evidence", f"{kind}={path}"])
        args.extend(["--evidence-sha256", f"{kind}={digest}"])
    return [*args, "--output", str(output)]


def test_accepts_exact_explicit_denominator_and_writes_canonical_mode_0600(tmp_path: Path):
    kinds = ("horizon_live_readiness", "multi_account_live_journey")
    bundle = _bundle(tmp_path, kinds=kinds)
    output = bundle["workspace"] / "acceptance.json"

    receipt = _verify(bundle, output=output)

    assert receipt["status"] == "accepted"
    assert receipt["requiredEvidenceKinds"] == sorted(kinds)
    assert receipt["evidenceCount"] == 2
    assert output.read_bytes() == _canonical(receipt)
    assert os.stat(output).st_mode & 0o777 == 0o600
    assert set(receipt["inputDigests"]) == {
        "ownerFinalization",
        "generationConvergence",
        "currentConvergence",
        "releaseManifest",
    }


@pytest.mark.parametrize(
    "kinds",
    [
        ("horizon_live_readiness",),
        ("multi_account_live_journey",),
        (
            "horizon_live_readiness",
            "multi_account_live_journey",
            "operator_requested_probe",
        ),
    ],
)
def test_flagship_v1_requires_exact_evidence_kind_policy(
    tmp_path: Path, kinds: tuple[str, ...]
):
    bundle = _bundle(tmp_path, kinds=kinds)

    with pytest.raises(MODULE.AcceptanceError, match="flagship v1 denominator"):
        _verify(bundle)


@pytest.mark.parametrize(
    ("status", "readiness"),
    [("attention_required", True), ("ready", False)],
)
def test_non_ready_evidence_emits_attention_required(
    tmp_path: Path, status: str, readiness: bool | None
):
    bundle = _bundle(tmp_path)
    kind = "horizon_live_readiness"
    path, _ = bundle["evidence"][kind]
    payload = bundle["evidence_payloads"][kind]
    payload["status"] = status
    payload["operationalReadinessClaimAllowed"] = readiness
    bundle["evidence"][kind] = (path, _write(path, payload))

    assert _verify(bundle)["status"] == "attention_required"


def test_operational_readiness_flag_is_required(tmp_path: Path):
    bundle = _bundle(tmp_path)
    kind = "horizon_live_readiness"
    path, _ = bundle["evidence"][kind]
    payload = bundle["evidence_payloads"][kind]
    payload.pop("operationalReadinessClaimAllowed")
    bundle["evidence"][kind] = (path, _write(path, payload))

    with pytest.raises(MODULE.AcceptanceError, match="unexpected field set"):
        _verify(bundle)


@pytest.mark.parametrize("field", tuple(TARGET))
def test_rejects_evidence_target_drift(tmp_path: Path, field: str):
    bundle = _bundle(tmp_path)
    kind = "horizon_live_readiness"
    path, _ = bundle["evidence"][kind]
    payload = bundle["evidence_payloads"][kind]
    payload["releaseBinding"][field] = (
        "f" * 64 if field.endswith("Sha256") else "drift"
    )
    bundle["evidence"][kind] = (path, _write(path, payload))

    with pytest.raises(MODULE.AcceptanceError, match="target drifted"):
        _verify(bundle)


def test_rejects_missing_extra_and_duplicate_kind_denominators(tmp_path: Path):
    bundle = _bundle(tmp_path)
    bundle["evidence"] = {}
    with pytest.raises(MODULE.AcceptanceError, match="flagship v1 denominator"):
        _verify(bundle)

    with pytest.raises(MODULE.AcceptanceError, match="duplicate kind"):
        MODULE._parse_kind_map(["probe=/one", "probe=/two"], "--require-evidence")

    bundle = _bundle(tmp_path / "second")
    output = bundle["workspace"] / "acceptance.json"
    args = _cli_args(bundle, output)
    digest_index = args.index("--evidence-sha256")
    args[digest_index + 1] = args[digest_index + 1].replace(
        "horizon_live_readiness=", "extra_kind="
    )
    assert MODULE.main(args) == 1
    assert not output.exists()


def test_rejects_duplicate_evidence_ids(tmp_path: Path):
    bundle = _bundle(
        tmp_path, kinds=("horizon_live_readiness", "multi_account_live_journey")
    )
    kind = "multi_account_live_journey"
    path, _ = bundle["evidence"][kind]
    payload = bundle["evidence_payloads"][kind]
    payload["evidenceId"] = "evidence-0"
    bundle["evidence"][kind] = (path, _write(path, payload))

    with pytest.raises(MODULE.AcceptanceError, match="duplicate evidenceId"):
        _verify(bundle)


def test_rejects_digest_tamper_and_noncanonical_evidence(tmp_path: Path):
    bundle = _bundle(tmp_path)
    kind = "horizon_live_readiness"
    path, _ = bundle["evidence"][kind]
    bundle["evidence"][kind] = (path, "0" * 64)
    with pytest.raises(MODULE.AcceptanceError, match="SHA-256 mismatch"):
        _verify(bundle)

    bundle = _bundle(tmp_path / "noncanonical")
    path, _ = bundle["evidence"][kind]
    payload = bundle["evidence_payloads"][kind]
    bundle["evidence"][kind] = (path, _write(path, payload, canonical=False))
    with pytest.raises(MODULE.AcceptanceError, match="not canonical JSON"):
        _verify(bundle)


@pytest.mark.parametrize("unsafe", ["symlink", "mode"])
def test_rejects_symlink_and_unsafe_input_modes(tmp_path: Path, unsafe: str):
    bundle = _bundle(tmp_path)
    kind = "horizon_live_readiness"
    path, digest = bundle["evidence"][kind]
    if unsafe == "symlink":
        alias = bundle["workspace"] / "evidence-link.json"
        alias.symlink_to(path)
        bundle["evidence"][kind] = (alias, digest)
    else:
        path.chmod(0o644)

    with pytest.raises(MODULE.AcceptanceError, match="symlink|mode-0600"):
        _verify(bundle)


def test_fifo_input_is_rejected_without_blocking(tmp_path: Path):
    bundle = _bundle(tmp_path)
    fifo = bundle["workspace"] / "evidence.fifo"
    os.mkfifo(fifo, 0o600)
    fifo.chmod(0o600)

    with pytest.raises(MODULE.AcceptanceError, match="mode-0600 regular file"):
        MODULE._stable_file(fifo, bundle["workspace"], "FIFO evidence")


@pytest.mark.parametrize("case", ["unknown", "missing", "stable_ready"])
def test_finalization_schema_is_exact_and_v1_is_preview_only(tmp_path: Path, case: str):
    bundle = _bundle(tmp_path)
    payload = bundle["finalization_payload"]
    if case == "unknown":
        payload["extra"] = True
    elif case == "missing":
        payload.pop("stageReceiptId")
    else:
        payload["status"] = "stable_ready"
    bundle["finalization_sha"] = _write(bundle["finalization"], payload)

    with pytest.raises(MODULE.AcceptanceError, match="field set|preview_ready"):
        _verify(bundle)


@pytest.mark.parametrize(
    "scope",
    [
        {"paths": ["Chummer.exe"]},
        "blazor-desktop:macos:osx-arm64,avalonia:macos:osx-arm64",
        "avalonia:macos:osx-arm64,avalonia:macos:osx-arm64",
        "avalonia:macos",
        "Avalonia:macos:osx-arm64",
    ],
)
def test_finalization_desktop_scope_is_canonical_tuple_string(
    tmp_path: Path, scope: object
):
    bundle = _bundle(tmp_path)
    payload = bundle["finalization_payload"]
    payload["exactIncomingDesktopScope"] = scope
    bundle["finalization_sha"] = _write(bundle["finalization"], payload)

    with pytest.raises(MODULE.AcceptanceError, match="exactIncomingDesktopScope"):
        _verify(bundle)


def test_finalization_requires_canonical_compact_json(tmp_path: Path):
    bundle = _bundle(tmp_path)
    bundle["finalization_sha"] = _write(
        bundle["finalization"], bundle["finalization_payload"], canonical=False
    )

    with pytest.raises(MODULE.AcceptanceError, match="not canonical JSON"):
        _verify(bundle)


@pytest.mark.parametrize(
    "case",
    ["unknown", "denominator", "nested_drift", "unpublished", "failure", "bool_count"],
)
def test_convergence_requires_exact_full_success_semantics(tmp_path: Path, case: str):
    bundle = _bundle(tmp_path)
    payload = bundle["generation_payload"]
    if case == "unknown":
        payload["extra"] = True
    elif case == "denominator":
        payload["checkedRouteCount"] = 3
    elif case == "nested_drift":
        payload["releaseTruth"]["manifestSha256"] = "f" * 64
    elif case == "unpublished":
        payload["releaseTruth"]["releaseStatus"] = "draft"
    elif case == "failure":
        payload["failures"] = ["forged success"]
    else:
        payload["mismatchCount"] = False
    bundle["generation_sha"] = _write(bundle["generation"], payload)

    with pytest.raises(MODULE.AcceptanceError):
        _verify(bundle)


@pytest.mark.parametrize("role", ["generation", "current"])
@pytest.mark.parametrize("case", ["wrong", "missing_install", "multiple_install"])
def test_convergence_route_denominator_is_producer_exact(
    tmp_path: Path, role: str, case: str
):
    bundle = _bundle(tmp_path)
    payload_key = "generation_payload" if role == "generation" else "current_payload"
    path_key = "generation" if role == "generation" else "current"
    sha_key = "generation_sha" if role == "generation" else "current_sha"
    payload = bundle[payload_key]
    routes = list(payload["checkedRoutes"])
    install_prefix = (
        f"/downloads/g/{TARGET['generationId']}/install/"
        if role == "generation"
        else "/downloads/install/"
    )
    install_routes = [route for route in routes if route.startswith(install_prefix)]
    assert len(install_routes) == 1
    if case == "wrong":
        routes[0] = "/bogus"
    elif case == "missing_install":
        routes.remove(install_routes[0])
    else:
        routes.append(f"{install_prefix}artifact-second")
    payload["checkedRoutes"] = sorted(routes)
    payload["checkedRouteCount"] = len(routes)
    bundle[sha_key] = _write(bundle[path_key], payload)

    with pytest.raises(MODULE.AcceptanceError, match="checked-route denominator"):
        _verify(bundle)


def test_manifest_selects_the_only_allowed_install_routes(tmp_path: Path):
    bundle = _bundle(tmp_path)
    manifest = bundle["manifest_payload"]
    manifest["downloads"][0]["id"] = "artifact-other"
    bundle["manifest_sha"] = _write(bundle["manifest"], manifest)

    with pytest.raises(MODULE.AcceptanceError, match="checked-route denominator"):
        _verify(bundle)


@pytest.mark.parametrize("case", ["digest", "native_drift", "truth_drift"])
def test_manifest_is_digest_pinned_and_bound_to_release_truth(
    tmp_path: Path, case: str
):
    bundle = _bundle(tmp_path)
    if case == "digest":
        bundle["manifest_sha"] = "0" * 64
    else:
        manifest = bundle["manifest_payload"]
        if case == "native_drift":
            manifest["status"] = "withdrawn"
        else:
            manifest["releaseTruth"]["knownIssueSummary"] = "Drifted."
        bundle["manifest_sha"] = _write(bundle["manifest"], manifest)

    with pytest.raises(MODULE.AcceptanceError, match="SHA-256|manifest"):
        _verify(bundle)


def test_manifest_accepts_strict_producer_native_pretty_json(tmp_path: Path):
    bundle = _bundle(tmp_path)
    bundle["manifest_sha"] = _write(
        bundle["manifest"], bundle["manifest_payload"], canonical=False
    )

    assert _verify(bundle)["status"] == "accepted"


def test_convergence_accepts_strict_producer_native_pretty_json(tmp_path: Path):
    bundle = _bundle(tmp_path)
    bundle["generation_sha"] = _write(
        bundle["generation"], bundle["generation_payload"], canonical=False
    )
    bundle["current_sha"] = _write(
        bundle["current"], bundle["current_payload"], canonical=False
    )

    assert _verify(bundle)["status"] == "accepted"


def test_generation_and_current_release_truth_must_match_fully(tmp_path: Path):
    bundle = _bundle(tmp_path)
    current = bundle["current_payload"]
    current["releaseTruth"]["knownIssueSummary"] = "A different summary."
    bundle["current_sha"] = _write(bundle["current"], current)

    with pytest.raises(MODULE.AcceptanceError, match="do not converge exactly"):
        _verify(bundle)


@pytest.mark.parametrize("case", ["old_kind", "empty", "duplicate", "bad_digest", "extra"])
def test_evidence_kind_and_nonempty_claim_schema_are_strict(tmp_path: Path, case: str):
    bundle = _bundle(tmp_path)
    kind = "horizon_live_readiness"
    path, _ = bundle["evidence"][kind]
    payload = bundle["evidence_payloads"][kind]
    if case == "old_kind":
        payload["kind"] = payload.pop("evidenceKind")
    elif case == "empty":
        payload["claims"] = []
    elif case == "duplicate":
        payload["claims"].append(dict(payload["claims"][0]))
    elif case == "bad_digest":
        payload["claims"][0]["evidenceSha256"] = "not-a-digest"
    else:
        payload["claims"][0]["path"] = "/secret/path"
    bundle["evidence"][kind] = (path, _write(path, payload))

    with pytest.raises(MODULE.AcceptanceError):
        _verify(bundle)


def test_attention_claim_prevents_acceptance_without_copying_raw_claims(tmp_path: Path):
    bundle = _bundle(tmp_path)
    kind = "horizon_live_readiness"
    path, _ = bundle["evidence"][kind]
    payload = bundle["evidence_payloads"][kind]
    payload["claims"][0]["status"] = "attention_required"
    bundle["evidence"][kind] = (path, _write(path, payload))

    receipt = _verify(bundle)

    assert receipt["status"] == "attention_required"
    row = receipt["evidence"][0]
    assert row["accepted"] is False
    assert row["claimCount"] == 1
    assert len(row["claimSetSha256"]) == 64
    assert "claims" not in row


def test_evidence_timestamp_requires_canonical_z_form(tmp_path: Path):
    bundle = _bundle(tmp_path)
    kind = "horizon_live_readiness"
    path, _ = bundle["evidence"][kind]
    payload = bundle["evidence_payloads"][kind]
    payload["generatedAtUtc"] = payload["generatedAtUtc"].replace("Z", "+00:00")
    bundle["evidence"][kind] = (path, _write(path, payload))

    with pytest.raises(MODULE.AcceptanceError, match="canonical UTC timestamp"):
        _verify(bundle)


def test_current_convergence_must_be_a_post_evidence_fence(tmp_path: Path):
    bundle = _bundle(tmp_path)
    payload = bundle["current_payload"]
    payload["generatedAtUtc"] = _utc(OBSERVED_AT - dt.timedelta(seconds=90))
    bundle["current_sha"] = _write(bundle["current"], payload)

    with pytest.raises(MODULE.AcceptanceError, match="predates .* post-activation evidence"):
        _verify(bundle)


def test_generation_convergence_must_precede_every_evidence(tmp_path: Path):
    bundle = _bundle(tmp_path)
    generation = bundle["generation_payload"]
    generation["generatedAtUtc"] = _utc(OBSERVED_AT - dt.timedelta(seconds=30))
    bundle["generation_sha"] = _write(bundle["generation"], generation)

    with pytest.raises(MODULE.AcceptanceError, match="postdates .* post-activation evidence"):
        _verify(bundle)


def test_generation_convergence_must_follow_finalization(tmp_path: Path):
    bundle = _bundle(tmp_path)
    generation = bundle["generation_payload"]
    generation["generatedAtUtc"] = _utc(OBSERVED_AT - dt.timedelta(minutes=4))
    bundle["generation_sha"] = _write(bundle["generation"], generation)

    with pytest.raises(MODULE.AcceptanceError, match="predates owner finalization"):
        _verify(bundle)


def test_generation_convergence_must_be_fresh(tmp_path: Path):
    bundle = _bundle(tmp_path)
    finalization = bundle["finalization_payload"]
    finalization["completedAtUtc"] = _utc(OBSERVED_AT - dt.timedelta(hours=26))
    bundle["finalization_sha"] = _write(bundle["finalization"], finalization)
    generation = bundle["generation_payload"]
    generation["generatedAtUtc"] = _utc(OBSERVED_AT - dt.timedelta(hours=25))
    bundle["generation_sha"] = _write(bundle["generation"], generation)

    with pytest.raises(MODULE.AcceptanceError, match="generation convergence is stale"):
        _verify(bundle)


def test_current_convergence_must_be_fresh(tmp_path: Path):
    bundle = _bundle(tmp_path)
    finalization = bundle["finalization_payload"]
    finalization["completedAtUtc"] = _utc(OBSERVED_AT - dt.timedelta(hours=26))
    bundle["finalization_sha"] = _write(bundle["finalization"], finalization)
    current = bundle["current_payload"]
    current["generatedAtUtc"] = _utc(OBSERVED_AT - dt.timedelta(hours=25))
    bundle["current_sha"] = _write(bundle["current"], current)
    kind = "horizon_live_readiness"
    path, _ = bundle["evidence"][kind]
    evidence = bundle["evidence_payloads"][kind]
    evidence["generatedAtUtc"] = _utc(OBSERVED_AT - dt.timedelta(hours=23))
    bundle["evidence"][kind] = (path, _write(path, evidence))

    with pytest.raises(MODULE.AcceptanceError, match="CURRENT convergence is stale"):
        _verify(bundle)


def test_output_is_create_exclusive_and_does_not_overwrite(tmp_path: Path):
    bundle = _bundle(tmp_path)
    output = bundle["workspace"] / "acceptance.json"
    output.write_text("keep-me", encoding="utf-8")
    output.chmod(0o600)

    with pytest.raises(MODULE.AcceptanceError, match="already exists"):
        _verify(bundle, output=output)
    assert output.read_text(encoding="utf-8") == "keep-me"
    assert not list(bundle["workspace"].glob(".post-activation-acceptance.tmp-*"))


def test_publish_race_never_unlinks_replacement_target(
    tmp_path: Path, monkeypatch
):
    bundle = _bundle(tmp_path)
    output = bundle["workspace"] / "acceptance.json"

    def racing_link(source, target, *, follow_symlinks):
        assert follow_symlinks is False
        replacement = Path(target)
        replacement.write_text("replacement-wins", encoding="utf-8")
        replacement.chmod(0o600)
        raise FileExistsError("raced")

    monkeypatch.setattr(MODULE.os, "link", racing_link)

    with pytest.raises(MODULE.AcceptanceError, match="already exists"):
        _verify(bundle, output=output)
    assert output.read_text(encoding="utf-8") == "replacement-wins"
    assert not list(bundle["workspace"].glob(".post-activation-acceptance.tmp-*"))


def test_duplicate_json_error_does_not_echo_attacker_key():
    raw = b'{"credential-material":1,"credential-material":2}'

    with pytest.raises(MODULE.AcceptanceError) as raised:
        MODULE._strict_json(raw, "evidence")

    assert "credential-material" not in str(raised.value)


def test_cli_redacts_raw_oserror_details(tmp_path: Path, monkeypatch, capsys):
    bundle = _bundle(tmp_path)
    output = bundle["workspace"] / "acceptance.json"

    def fail_with_oserror(**_kwargs):
        raise OSError("/private/attacker-controlled-path")

    monkeypatch.setattr(MODULE, "verify", fail_with_oserror)

    assert MODULE.main(_cli_args(bundle, output)) == 1
    error = capsys.readouterr().err
    assert error == (
        "post_activation_acceptance:fail: bounded local validation failed\n"
    )
    assert "attacker-controlled" not in error


def test_cli_returns_attention_and_fail_without_partial_output(tmp_path: Path, capsys):
    now = dt.datetime.now(dt.timezone.utc)
    bundle = _bundle(tmp_path, observed_at=now)
    kind = "horizon_live_readiness"
    path, _ = bundle["evidence"][kind]
    payload = bundle["evidence_payloads"][kind]
    payload["status"] = "attention_required"
    bundle["evidence"][kind] = (path, _write(path, payload))
    attention_output = bundle["workspace"] / "attention.json"

    assert MODULE.main(_cli_args(bundle, attention_output)) == 2
    assert json.loads(attention_output.read_text())["status"] == "attention_required"
    assert "post_activation_acceptance:attention_required" in capsys.readouterr().out

    fail_output = bundle["workspace"] / "fail.json"
    args = _cli_args(bundle, fail_output)
    index = args.index("--evidence-sha256")
    args[index + 1] = f"{kind}={'0' * 64}"
    assert MODULE.main(args) == 1
    assert not fail_output.exists()
    assert "post_activation_acceptance:fail:" in capsys.readouterr().err

from __future__ import annotations

import datetime as dt
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import stat
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/materialize_build_ghost_tough_tongue_runtime_config.py"
DEPLOY_HELPER = ROOT / "ops/build-ghost-private-nonprod/deploy-ai-with-rollback.sh"
COMPOSE = ROOT / "docker-compose.build-ghost-private-nonprod.yml"
SPEC = importlib.util.spec_from_file_location("tough_tongue_runtime_config", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def digest(raw: bytes) -> str:
    return f"sha256:{hashlib.sha256(raw).hexdigest()}"


def canonical(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode()


def contract_payload() -> dict[str, object]:
    return {
        "schema": "chummer.build_ghost.tough_tongue.read_only_binding_contract.v2",
        "provider_key": "tough_tongue",
        "base_url": "https://api.toughtongueai.com/api/public",
        "source_type": "provider_documentation",
        "verified_at": "2026-08-23T10:00:00Z",
        "authority": {
            "operator_verified": True,
            "source_ref_sha256": "sha256:" + "a" * 64,
        },
        "slot_cardinality": 6,
        "maximum_snapshot_age_seconds": 900,
        "premium_plan_values": ["premium"],
        "live_avatar_providers": ["anam", "avatario", "heygen", "liveavatar"],
        "documented_get_allowlist": {
            "balance": {"method": "GET", "path": "balance"},
            "subscriptions": {"method": "GET", "path": "subscriptions"},
            "organizations": {"method": "GET", "path": "v2/organizations"},
            "scenario": {"method": "GET", "path": "scenarios/{resource_ref}"},
        },
        "normalization": {
            "plan": "subscriptions.active.product_name",
            "remaining_minutes": "balance.available_minutes",
            "refresh_at": "balance.last_updated",
            "organization": "organizations.id",
            "resource_ownership": "organization_scoped_scenario_readback",
        },
        "unsupported_direct_resources": ["agent", "voice", "function", "avatar"],
    }


def operator_payload(contract_path: Path, contract: dict[str, object]) -> dict[str, object]:
    refs = ["sha256:" + character * 64 for character in "123456"]
    return {
        "schema": "chummer.build_ghost.tough_tongue.runtime_config.v1",
        "account_slots": [
            {"account_ref": ref, "api_key": f"private-read-only-key-{index}", "organization_ref": f"org-{index}"}
            for index, ref in enumerate(refs, start=1)
        ],
        "preferred_account_ref": refs[1],
        "candidate_refs": {
            "agent": "operator-agent-ref",
            "voice": "operator-voice-ref",
            "function": "operator-function-ref",
            "scenario": "operator-scenario-ref",
            "live_avatar": "operator-live-avatar-ref",
        },
        "read_only_contract": {
            "path": str(contract_path),
            "digest": digest(canonical(contract)),
        },
    }


def account_selection_policy(account_refs: list[str]) -> dict[str, object]:
    observed_at = "2026-08-23T13:01:17Z"
    valid_until = "2027-07-23T13:01:17Z"
    qualifying = [account_refs[index] for index in (1, 3, 4, 5)]
    payload: dict[str, object] = {
        "schema": "ea.tough_tongue.operator_premium_grants.v1",
        "generatedAt": "2026-08-23T13:10:00Z",
        "status": "active",
        "sourceType": "user_authority",
        "decisionSequence": 2,
        "decisionEvidenceDigest": "sha256:" + "b" * 64,
        "supersededDecisionEvidenceDigest": "sha256:" + "c" * 64,
        "premiumBasis": "operator_policy_available_minutes_gt_threshold",
        "thresholdComparison": "strictly_greater_than",
        "thresholdMinutes": 1100.0,
        "validityCalendarMonths": 11,
        "identityBasis": "stable_account_ref_sha256",
        "providerPlanLabelBasis": "unproven_by_documented_api",
        "inputAuditEvidenceDigest": "sha256:" + "d" * 64,
        "qualificationObservedAt": observed_at,
        "premiumValidUntil": valid_until,
        "grants": [
            {
                "accountRefSha256": account_ref,
                "qualificationRemainingMinutes": 2425.0,
                "qualificationObservedAt": observed_at,
                "premiumValidUntil": valid_until,
            }
            for account_ref in qualifying
        ],
        "unqualifiedAccountRefs": sorted([account_refs[0], account_refs[2]]),
        "preferredAccountRef": account_refs[3],
        "preferredOrganizationMembershipVerified": True,
        "readyForAccountSelection": True,
        "readyForResourceBinding": False,
        "resourceOwnershipVerified": False,
        "laterBalanceDropRevokesBeforeExpiry": False,
        "identityMismatchRequiresRequalification": True,
        "expiryRequiresRequalification": True,
        "runtimeGatesChanged": False,
        "providerActivationPerformed": False,
        "rawCredentialsPersisted": False,
        "rawIdentifiersPersisted": False,
    }
    payload["evidenceDigest"] = digest(canonical(payload))
    return payload


def write_private_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    path.chmod(0o600)


def inputs(tmp_path: Path) -> tuple[Path, Path, Path, Path, Path, dict[str, object]]:
    tmp_path.chmod(0o700)
    contract = contract_payload()
    source_contract = tmp_path / "operator-contract.json"
    write_private_json(source_contract, contract)
    config = tmp_path / "operator-config.json"
    payload = operator_payload(source_contract, contract)
    write_private_json(config, payload)
    environment = tmp_path / "runtime.env"
    snapshot = tmp_path / "runtime-contract.json"
    receipt = tmp_path / "runtime-receipt.json"
    return config, environment, snapshot, receipt, source_contract, payload


def audit_only_inputs(
    tmp_path: Path,
) -> tuple[Path, Path, Path, Path, Path, Path, dict[str, object], dict[str, object]]:
    config, environment, snapshot, receipt, source_contract, payload = inputs(tmp_path)
    refs = [slot["account_ref"] for slot in payload["account_slots"]]  # type: ignore[index]
    policy = account_selection_policy(refs)
    policy_path = tmp_path / "account-selection-policy.json"
    write_private_json(policy_path, policy)
    payload["preferred_account_ref"] = refs[3]
    payload["candidate_refs"] = {kind: "" for kind in MODULE.CANDIDATE_KINDS}
    payload["account_selection_policy"] = {
        "path": str(policy_path),
        "digest": digest(canonical(policy)),
    }
    for slot in payload["account_slots"]:  # type: ignore[index]
        slot.pop("organization_ref", None)
    write_private_json(config, payload)
    return (
        config, environment, snapshot, receipt, source_contract, policy_path,
        payload, policy,
    )


def usable(path: Path, mode: int) -> bool:
    if not path.exists() or path.is_symlink():
        return False
    metadata = path.stat()
    return (
        stat.S_ISREG(metadata.st_mode)
        and stat.S_IMODE(metadata.st_mode) == mode
        and metadata.st_uid == os.geteuid()
        and metadata.st_nlink == 1
    )


def test_materializes_digest_bound_pair_with_environment_published_last(tmp_path: Path):
    config, environment, snapshot, receipt_path, _, payload = inputs(tmp_path)

    receipt = MODULE.materialize(config, environment, snapshot, receipt_path)

    assert usable(environment, 0o600)
    assert usable(snapshot, 0o400)
    assert usable(receipt_path, 0o600)
    environment_raw = environment.read_bytes()
    contract_raw = snapshot.read_bytes()
    assert receipt["status"] == "ready-for-read-only-probe"
    assert receipt["accountRefCount"] == 6
    assert receipt["organizationContextCount"] == 6
    assert receipt["organizationRefsDigest"].startswith("sha256:")
    assert receipt["providerReadbackVerified"] is False
    assert receipt["stockAvatarMigrationConfigured"] is False
    assert receipt["providerActivationAuthorized"] is False
    assert receipt["providerMutationPerformed"] is False
    assert receipt["environmentFileDigest"] == digest(environment_raw)
    assert receipt["readOnlyContractFileDigest"] == digest(contract_raw)
    assert receipt["publicationOrder"] == ["contract-snapshot", "receipt", "environment"]
    assert receipt["outputDirectoryDevice"] == tmp_path.stat().st_dev
    assert receipt["outputDirectoryInode"] == tmp_path.stat().st_ino
    assert receipt["evidenceDigest"] == digest(
        canonical({key: value for key, value in receipt.items() if key != "evidenceDigest"})
    )
    assert json.loads(contract_raw) == contract_payload()
    environment_text = environment_raw.decode()
    assert f"CHUMMER_BUILD_GHOST_TOUGH_TONGUE_READ_ONLY_BINDING_CONTRACT_FILE={snapshot}" in environment_text
    assert "TOUGH_TONGUE_ORGANIZATION_IDS=org-1;org-2;org-3;org-4;org-5;org-6" in environment_text
    rendered_receipt = receipt_path.read_text(encoding="utf-8")
    for slot in payload["account_slots"]:  # type: ignore[index]
        assert slot["api_key"] not in rendered_receipt
    for candidate in payload["candidate_refs"].values():  # type: ignore[union-attr]
        assert candidate not in rendered_receipt


def test_materializes_account_audit_only_policy_without_resource_candidates(tmp_path: Path):
    config, environment, snapshot, receipt_path, _, _, payload, policy = audit_only_inputs(tmp_path)

    receipt = MODULE.materialize(config, environment, snapshot, receipt_path)

    assert receipt["status"] == "ready-for-read-only-probe"
    assert receipt["bindingCandidatesConfigured"] is False
    assert receipt["stockAvatarMigrationConfigured"] is False
    assert receipt["candidateRefCount"] == 0
    assert receipt["candidateRefDigests"] == {}
    assert receipt["readyForAccountSelection"] is True
    assert receipt["readyForResourceBinding"] is False
    assert receipt["providerPlanLabelReadbackVerified"] is False
    assert receipt["accountSelectionPolicySource"] == "user_authority"
    assert receipt["premiumBasis"] == "operator_policy_available_minutes_gt_threshold"
    assert receipt["premiumThresholdMinutes"] == 1100.0
    assert receipt["premiumValidityCalendarMonths"] == 11
    assert receipt["premiumValidUntil"] == "2027-07-23T13:01:17Z"
    assert receipt["premiumGrantCount"] == 4
    assert receipt["providerReadbackVerified"] is False
    assert receipt["providerActivationAuthorized"] is False
    assert receipt["providerMutationPerformed"] is False
    assert receipt["organizationContextCount"] == 0
    environment_text = environment.read_text(encoding="utf-8")
    for name in MODULE.ENVIRONMENT_NAMES.values():
        assert f"{name}=\n" in environment_text
    assert policy["providerPlanLabelBasis"] == "unproven_by_documented_api"
    assert policy["laterBalanceDropRevokesBeforeExpiry"] is False
    assert policy["readyForResourceBinding"] is False
    rendered = receipt_path.read_text(encoding="utf-8")
    for slot in payload["account_slots"]:  # type: ignore[index]
        assert slot["api_key"] not in rendered


def test_account_audit_only_compose_renders_all_candidates_empty_and_gates_false(tmp_path: Path):
    config, environment_file, snapshot, receipt, _, _, _, _ = audit_only_inputs(tmp_path)
    MODULE.materialize(config, environment_file, snapshot, receipt)
    environment = os.environ.copy()
    for index, name in enumerate(
        (
            "CHUMMER_RUN_SERVICES_REVISION", "CHUMMER_PRESENTATION_REVISION",
            "CHUMMER_CORE_ENGINE_REVISION", "CHUMMER_HUB_REGISTRY_REVISION",
            "CHUMMER_UI_KIT_REVISION", "CHUMMER_MEDIA_FACTORY_REVISION",
        ),
        start=1,
    ):
        environment[name] = str(index) * 40
    for name in (
        "CHUMMER_RUN_SERVICES_SOURCE", "CHUMMER_PRESENTATION_SOURCE",
        "CHUMMER_CORE_ENGINE_SOURCE", "CHUMMER_HUB_REGISTRY_SOURCE",
        "CHUMMER_UI_KIT_SOURCE", "CHUMMER_MEDIA_FACTORY_SOURCE",
    ):
        environment[name] = str(ROOT)
    environment["CHUMMER_BUILD_GHOST_PRIVATE_TOOL_SERVICE_TOKEN"] = "test-tool-token-" + "a" * 32
    environment["CHUMMER_AI_INTERNAL_API_TOKEN"] = "test-ai-token-" + "b" * 32

    result = subprocess.run(
        [
            "docker", "compose", "--env-file", str(environment_file),
            "--project-directory", str(ROOT), "--file", str(COMPOSE),
            "config", "--format", "json",
        ],
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )

    assert result.returncode == 0, result.stderr
    ai = json.loads(result.stdout)["services"]["chummer-build-ghost-ai"]
    for variable_name in MODULE.ENVIRONMENT_NAMES.values():
        assert ai["environment"][variable_name] == ""
    for gate in (
        "CHUMMER_BUILD_GHOST_TOUGH_TONGUE_REMOTE_EXECUTION_ENABLED",
        "CHUMMER_BUILD_GHOST_TOUGH_TONGUE_PRIVATE_CANARY_MUTATIONS_ENABLED",
        "CHUMMER_BUILD_GHOST_TOUGH_TONGUE_CANARY_READ_ONLY_ENABLED",
        "CHUMMER_BUILD_GHOST_TOUGH_TONGUE_CANARY_ACCESS_GRANT_ENABLED",
    ):
        assert ai["environment"][gate] == "false"


def test_account_audit_only_rejects_partial_resource_candidates(tmp_path: Path):
    config, environment, snapshot, receipt, _, _, payload, _ = audit_only_inputs(tmp_path)
    payload["candidate_refs"]["scenario"] = "partial-scenario-ref"  # type: ignore[index]
    write_private_json(config, payload)

    with pytest.raises(MODULE.ConfigError, match="candidate-refs-partial"):
        MODULE.materialize(config, environment, snapshot, receipt)

    assert not environment.exists()
    assert not snapshot.exists()


def test_stock_avatar_migration_accepts_only_voice_scenario_and_avatar_and_stays_unready(tmp_path: Path):
    config, environment, snapshot, receipt_path, _, _, payload, _ = audit_only_inputs(tmp_path)
    payload["candidate_refs"].update(  # type: ignore[union-attr]
        {
            "voice": "Aoede",
            "scenario": "private-stock-scenario-ref",
            "live_avatar": "11111111-2222-4333-8444-555555555555",
        }
    )
    write_private_json(config, payload)

    receipt = MODULE.materialize(config, environment, snapshot, receipt_path)

    assert receipt["bindingCandidatesConfigured"] is False
    assert receipt["stockAvatarMigrationConfigured"] is True
    assert receipt["candidateRefCount"] == 3
    assert set(receipt["candidateRefDigests"]) == {"voice", "scenario", "live_avatar"}
    assert receipt["readyForResourceBinding"] is False
    assert receipt["providerReadbackVerified"] is False
    assert receipt["providerActivationAuthorized"] is False
    assert receipt["providerMutationPerformed"] is False
    assert receipt["nextAction"] == (
        "attach-read-verified-grounded-custom-function-before-any-remote-execution"
    )
    environment_text = environment.read_text(encoding="utf-8")
    assert "CHUMMER_BUILD_GHOST_TOUGH_TONGUE_AGENT_ID=\n" in environment_text
    assert "CHUMMER_BUILD_GHOST_TOUGH_TONGUE_FUNCTION_ID=\n" in environment_text
    assert "CHUMMER_BUILD_GHOST_TOUGH_TONGUE_VOICE_ID=Aoede\n" in environment_text
    assert "CHUMMER_BUILD_GHOST_TOUGH_TONGUE_SCENARIO_ID=private-stock-scenario-ref\n" in environment_text
    assert "CHUMMER_BUILD_GHOST_TOUGH_TONGUE_LIVE_AVATAR_ID=11111111-2222-4333-8444-555555555555\n" in environment_text


@pytest.mark.parametrize("provider", ["avatari0", "unknown-avatar-provider"])
def test_read_only_contract_rejects_misspelled_or_arbitrary_live_avatar_providers(
    tmp_path: Path,
    provider: str,
):
    config, environment, snapshot, receipt, source_contract, payload = inputs(tmp_path)
    contract = contract_payload()
    contract["live_avatar_providers"] = [provider]
    write_private_json(source_contract, contract)
    payload["read_only_contract"]["digest"] = digest(canonical(contract))  # type: ignore[index]
    write_private_json(config, payload)

    with pytest.raises(
        MODULE.ConfigError,
        match="read-only-contract-live-avatar-provider-invalid",
    ):
        MODULE.materialize(config, environment, snapshot, receipt)


def test_account_audit_only_requires_an_active_policy_receipt(tmp_path: Path):
    config, environment, snapshot, receipt, _, payload = inputs(tmp_path)
    payload["candidate_refs"] = {kind: "" for kind in MODULE.CANDIDATE_KINDS}
    write_private_json(config, payload)

    with pytest.raises(MODULE.ConfigError, match="account-selection-policy-required"):
        MODULE.materialize(config, environment, snapshot, receipt)

    assert not environment.exists()


def test_account_audit_only_policy_is_stable_across_slot_reordering(tmp_path: Path):
    config, environment, snapshot, receipt, _, _, payload, _ = audit_only_inputs(tmp_path)
    payload["account_slots"] = list(reversed(payload["account_slots"]))  # type: ignore[index]
    write_private_json(config, payload)

    materialized = MODULE.materialize(config, environment, snapshot, receipt)

    assert materialized["readyForAccountSelection"] is True
    assert materialized["premiumGrantCount"] == 4


def test_account_audit_only_identity_mismatch_requires_requalification(tmp_path: Path):
    config, environment, snapshot, receipt, _, _, payload, _ = audit_only_inputs(tmp_path)
    payload["account_slots"][0]["account_ref"] = "sha256:" + "9" * 64  # type: ignore[index]
    write_private_json(config, payload)

    with pytest.raises(MODULE.ConfigError, match="account-selection-policy-identity-mismatch"):
        MODULE.materialize(config, environment, snapshot, receipt)

    assert not environment.exists()


def test_account_selection_policy_clock_boundary_and_expiry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    config, environment, snapshot, receipt, _, _, _, _ = audit_only_inputs(tmp_path)
    monkeypatch.setattr(
        MODULE,
        "_utc_now",
        lambda: dt.datetime(2027, 7, 23, 13, 1, 16, tzinfo=dt.timezone.utc),
    )
    assert MODULE.materialize(config, environment, snapshot, receipt)[
        "readyForAccountSelection"
    ] is True

    expired_root = tmp_path / "expired"
    expired_root.mkdir(mode=0o700)
    config, environment, snapshot, receipt, _, _, _, _ = audit_only_inputs(expired_root)
    monkeypatch.setattr(
        MODULE,
        "_utc_now",
        lambda: dt.datetime(2027, 7, 23, 13, 1, 17, tzinfo=dt.timezone.utc),
    )
    with pytest.raises(MODULE.ConfigError, match="account-selection-policy-expired"):
        MODULE.materialize(config, environment, snapshot, receipt)


def test_calendar_month_arithmetic_clamps_month_end() -> None:
    assert MODULE._add_calendar_months(
        dt.datetime(2027, 1, 31, 8, tzinfo=dt.timezone.utc), 1
    ) == dt.datetime(2027, 2, 28, 8, tzinfo=dt.timezone.utc)
    assert MODULE._add_calendar_months(
        dt.datetime(2028, 1, 31, 8, tzinfo=dt.timezone.utc), 1
    ) == dt.datetime(2028, 2, 29, 8, tzinfo=dt.timezone.utc)


def test_superseded_policy_is_never_accepted(tmp_path: Path):
    config, environment, snapshot, receipt, _, policy_path, payload, policy = audit_only_inputs(tmp_path)
    policy["status"] = "superseded_before_activation"
    policy["evidenceDigest"] = digest(
        canonical({key: value for key, value in policy.items() if key != "evidenceDigest"})
    )
    write_private_json(policy_path, policy)
    payload["account_selection_policy"]["digest"] = digest(canonical(policy))  # type: ignore[index]
    write_private_json(config, payload)

    with pytest.raises(MODULE.ConfigError, match="account-selection-policy-authority-invalid"):
        MODULE.materialize(config, environment, snapshot, receipt)

    assert not environment.exists()


def test_deploy_helper_requires_policy_bound_audit_only_posture() -> None:
    helper = DEPLOY_HELPER.read_text(encoding="utf-8")

    for clause in (
        ".readyForResourceBinding == false",
        ".providerPlanLabelReadbackVerified == false",
        ".bindingCandidatesConfigured == false",
        ".candidateRefCount == 0",
        ".candidateRefDigests == {}",
        ".readyForAccountSelection == true",
        '.accountSelectionPolicySource == "user_authority"',
        '.premiumBasis == "operator_policy_available_minutes_gt_threshold"',
        ".premiumThresholdMinutes == 1100",
        ".premiumValidityCalendarMonths == 11",
    ):
        assert clause in helper
    assert "if jq -e '.bindingCandidatesConfigured == false'" in helper
    for variable_name in MODULE.ENVIRONMENT_NAMES.values():
        assert f".services[$service].environment.{variable_name} == \"\"" in helper
        assert f".services[$service].environment.{variable_name} != \"\"" in helper


def test_cli_materializes_the_complete_pair_without_printing_private_inputs(tmp_path: Path):
    config, environment, snapshot, receipt, _, payload = inputs(tmp_path)

    result = subprocess.run(
        [
            str(SCRIPT),
            "--config", str(config),
            "--output-env", str(environment),
            "--output-contract", str(snapshot),
            "--receipt", str(receipt),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert "status=ready-for-read-only-probe" in result.stdout
    rendered_output = result.stdout + result.stderr
    for slot in payload["account_slots"]:  # type: ignore[index]
        assert slot["api_key"] not in rendered_output
    for candidate in payload["candidate_refs"].values():  # type: ignore[union-attr]
        assert candidate not in rendered_output
    assert usable(environment, 0o600)
    assert usable(snapshot, 0o400)
    assert usable(receipt, 0o600)


@pytest.mark.parametrize("failed_publication", ("contract", "receipt", "environment"))
def test_fault_before_each_publication_never_leaves_a_usable_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failed_publication: str
):
    config, environment, snapshot, receipt, _, _ = inputs(tmp_path)
    real_publish = MODULE._publish_new
    names = {
        "contract": snapshot.name,
        "receipt": receipt.name,
        "environment": environment.name,
    }

    def fail_selected(parent_fd: int, name: str, raw: bytes, mode: int) -> None:
        if name == names[failed_publication]:
            raise OSError("injected-publication-fault")
        real_publish(parent_fd, name, raw, mode)

    monkeypatch.setattr(MODULE, "_publish_new", fail_selected)
    with pytest.raises(OSError, match="injected-publication-fault"):
        MODULE.materialize(config, environment, snapshot, receipt)

    assert not usable(environment, 0o600)
    if environment.exists():
        assert usable(receipt, 0o600)


@pytest.mark.parametrize("failed_publication", ("contract", "receipt", "environment"))
def test_fault_before_atomic_link_never_leaves_a_published_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failed_publication: str
):
    config, environment, snapshot, receipt, _, _ = inputs(tmp_path)
    selected = {
        "contract": snapshot.name,
        "receipt": receipt.name,
        "environment": environment.name,
    }[failed_publication]
    real_link = MODULE._link_staged_file

    def fail_selected(parent_fd: int, descriptor: int, destination: str) -> None:
        if destination == selected:
            raise OSError("injected-link-fault")
        real_link(parent_fd, descriptor, destination)

    monkeypatch.setattr(MODULE, "_link_staged_file", fail_selected)
    with pytest.raises(OSError, match="injected-link-fault"):
        MODULE.materialize(config, environment, snapshot, receipt)

    assert not usable(environment, 0o600)
    assert not any(path.name.endswith(".tmp") for path in tmp_path.iterdir())


def test_atomic_noreplace_publication_never_overwrites_an_existing_output(
    tmp_path: Path,
):
    existing = tmp_path / "runtime.env"
    existing.write_bytes(b"EXISTING=unchanged\n")
    existing.chmod(0o600)

    parent_fd = os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        with pytest.raises(FileExistsError):
            MODULE._publish_new(
                parent_fd,
                existing.name,
                b"REPLACEMENT=blocked\n",
                0o600,
            )
    finally:
        os.close(parent_fd)

    assert existing.read_bytes() == b"EXISTING=unchanged\n"
    assert existing.stat().st_nlink == 1


@pytest.mark.parametrize("kind", ("agent", "voice", "function", "scenario", "live_avatar"))
def test_preshaped_candidate_digest_is_never_accepted_as_a_raw_ref(
    tmp_path: Path, kind: str
):
    config, environment, snapshot, receipt, source_contract, payload = inputs(tmp_path)
    payload["candidate_refs"][kind] = digest(b"different-live-value")  # type: ignore[index]
    write_private_json(config, payload)

    with pytest.raises(MODULE.ConfigError, match=f"candidate-{kind.replace('_', '-')}-ref-invalid"):
        MODULE.materialize(config, environment, snapshot, receipt)

    assert not environment.exists()
    assert source_contract.exists()


@pytest.mark.parametrize("invalidity", ("authority", "method", "path", "cardinality"))
def test_contract_must_be_exact_get_only_and_operator_verified(
    tmp_path: Path, invalidity: str
):
    config, environment, snapshot, receipt, source_contract, payload = inputs(tmp_path)
    contract = contract_payload()
    if invalidity == "authority":
        contract["authority"]["operator_verified"] = False  # type: ignore[index]
        expected = "read-only-contract-authority-invalid"
    elif invalidity == "method":
        contract["documented_get_allowlist"]["scenario"]["method"] = "POST"  # type: ignore[index]
        expected = "read-only-contract-route-scenario-invalid"
    elif invalidity == "path":
        contract["documented_get_allowlist"]["scenario"]["path"] = "agents/{resource_ref}"  # type: ignore[index]
        expected = "read-only-contract-route-scenario-invalid"
    else:
        contract["slot_cardinality"] = 5
        expected = "read-only-contract-cardinality-invalid"
    write_private_json(source_contract, contract)
    payload["read_only_contract"]["digest"] = digest(canonical(contract))  # type: ignore[index]
    write_private_json(config, payload)

    with pytest.raises(MODULE.ConfigError, match=expected):
        MODULE.materialize(config, environment, snapshot, receipt)

    assert not environment.exists()


def test_operator_config_requires_exactly_six_slots_before_any_output(tmp_path: Path):
    config, environment, snapshot, receipt, _, payload = inputs(tmp_path)
    payload["account_slots"] = payload["account_slots"][:5]  # type: ignore[index]
    write_private_json(config, payload)

    with pytest.raises(MODULE.ConfigError, match="account-slots-invalid"):
        MODULE.materialize(config, environment, snapshot, receipt)

    assert not environment.exists()
    assert not snapshot.exists()


def test_optional_organization_context_is_all_or_none_to_preserve_slot_alignment(tmp_path: Path):
    config, environment, snapshot, receipt, _, payload = inputs(tmp_path)
    del payload["account_slots"][0]["organization_ref"]  # type: ignore[index]
    write_private_json(config, payload)

    with pytest.raises(MODULE.ConfigError, match="organization-refs-partial"):
        MODULE.materialize(config, environment, snapshot, receipt)

    assert not environment.exists()


def test_output_files_must_share_one_private_run_directory(tmp_path: Path):
    config, environment, snapshot, receipt, _, _ = inputs(tmp_path)
    other = tmp_path / "other"
    other.mkdir(mode=0o700)

    with pytest.raises(MODULE.ConfigError, match="output-paths-not-same-private-directory"):
        MODULE.materialize(config, other / environment.name, snapshot, receipt)

    assert not (other / environment.name).exists()


def test_duplicate_config_key_is_rejected_before_any_output(tmp_path: Path):
    config, environment, snapshot, receipt, _, payload = inputs(tmp_path)
    raw = json.dumps(payload, separators=(",", ":"))
    raw = raw[:-1] + ',"schema":"chummer.build_ghost.tough_tongue.runtime_config.v1"}'
    config.write_text(raw, encoding="utf-8")
    config.chmod(0o600)

    with pytest.raises(MODULE.ConfigError, match="operator-config-duplicate-key"):
        MODULE.materialize(config, environment, snapshot, receipt)

    assert not environment.exists()
    assert not receipt.exists()


def test_contract_digest_drift_is_rejected_before_any_output(tmp_path: Path):
    config, environment, snapshot, receipt, _, payload = inputs(tmp_path)
    payload["read_only_contract"]["digest"] = "sha256:" + "0" * 64  # type: ignore[index]
    write_private_json(config, payload)

    with pytest.raises(MODULE.ConfigError, match="read-only-contract-digest-mismatch"):
        MODULE.materialize(config, environment, snapshot, receipt)

    assert not environment.exists()
    assert not snapshot.exists()


def test_operator_config_link_and_weak_mode_are_rejected(tmp_path: Path):
    config, environment, snapshot, receipt, _, _ = inputs(tmp_path)
    link = tmp_path / "linked-config.json"
    link.symlink_to(config)

    with pytest.raises(MODULE.ConfigError, match="operator-config-authority-invalid"):
        MODULE.materialize(link, environment, snapshot, receipt)

    config.chmod(0o644)
    with pytest.raises(MODULE.ConfigError, match="operator-config-authority-invalid"):
        MODULE.materialize(config, environment, snapshot, receipt)
    assert not environment.exists()


def test_intermediate_input_symlink_is_rejected_without_reading_config(tmp_path: Path):
    real = tmp_path / "real"
    real.mkdir(mode=0o700)
    private = real / "private"
    private.mkdir(mode=0o700)
    config, environment, snapshot, receipt, _, _ = inputs(private)
    alias = tmp_path / "alias"
    alias.symlink_to(real, target_is_directory=True)

    with pytest.raises(MODULE.ConfigError, match="operator-config-authority-invalid"):
        MODULE.materialize(
            alias / "private" / config.name,
            environment,
            snapshot,
            receipt,
        )

    assert not environment.exists()


def test_intermediate_output_symlink_is_rejected_before_publication(tmp_path: Path):
    config, _, _, _, _, _ = inputs(tmp_path)
    real = tmp_path / "real-output"
    real.mkdir(mode=0o700)
    private = real / "private"
    private.mkdir(mode=0o700)
    alias = tmp_path / "output-alias"
    alias.symlink_to(real, target_is_directory=True)

    with pytest.raises(MODULE.ConfigError, match="output-parent-authority-invalid"):
        MODULE.materialize(
            config,
            alias / "private" / "runtime.env",
            alias / "private" / "runtime-contract.json",
            alias / "private" / "runtime-receipt.json",
        )

    assert list(private.iterdir()) == []


def test_parent_retarget_between_publications_never_reaches_environment_commit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    run = tmp_path / "run"
    run.mkdir(mode=0o700)
    config, environment, snapshot, receipt, _, _ = inputs(run)
    moved = tmp_path / "moved"
    real_publish = MODULE._publish_new
    publications = 0

    def retarget_after_first(parent_fd: int, name: str, raw: bytes, mode: int) -> None:
        nonlocal publications
        real_publish(parent_fd, name, raw, mode)
        publications += 1
        if publications == 1:
            run.rename(moved)
            run.mkdir(mode=0o700)

    monkeypatch.setattr(MODULE, "_publish_new", retarget_after_first)
    with pytest.raises(MODULE.ConfigError, match="output-parent-changed"):
        MODULE.materialize(config, environment, snapshot, receipt)

    assert (moved / snapshot.name).is_file()
    assert not (moved / environment.name).exists()
    assert list(run.iterdir()) == []


def test_destroy_environment_removes_only_credentials_and_retains_audit_pair(
    tmp_path: Path,
):
    config, environment, snapshot, receipt, _, _ = inputs(tmp_path)
    receipt_payload = MODULE.materialize(config, environment, snapshot, receipt)

    destroy_args = {
        "expected_parent_device": receipt_payload["outputDirectoryDevice"],
        "expected_parent_inode": receipt_payload["outputDirectoryInode"],
        "expected_environment_digest": receipt_payload["environmentFileDigest"],
    }
    assert MODULE.destroy_environment(environment, **destroy_args) is True

    assert not environment.exists()
    assert usable(snapshot, 0o400)
    assert usable(receipt, 0o600)
    assert MODULE.destroy_environment(environment, **destroy_args) is False


def test_destroy_environment_rejects_intermediate_symlink_without_touching_target(
    tmp_path: Path,
):
    real = tmp_path / "real"
    real.mkdir(mode=0o700)
    environment = real / "runtime.env"
    environment.write_text("PRIVATE_TEST_VALUE=opaque\n", encoding="utf-8")
    environment.chmod(0o600)
    alias = tmp_path / "alias"
    alias.symlink_to(real, target_is_directory=True)

    with pytest.raises(
        MODULE.ConfigError,
        match="environment-destroy-parent-authority-invalid",
    ):
        MODULE.destroy_environment(
            alias / environment.name,
            expected_parent_device=real.stat().st_dev,
            expected_parent_inode=real.stat().st_ino,
        )

    assert environment.read_text(encoding="utf-8") == "PRIVATE_TEST_VALUE=opaque\n"


def test_destroy_environment_rejects_parent_retarget_without_touching_either_file(
    tmp_path: Path,
):
    run = tmp_path / "run"
    run.mkdir(mode=0o700)
    config, environment, snapshot, receipt_path, _, _ = inputs(run)
    receipt = MODULE.materialize(config, environment, snapshot, receipt_path)
    original_raw = environment.read_bytes()
    moved = tmp_path / "original"
    run.rename(moved)
    run.mkdir(mode=0o700)
    replacement = run / environment.name
    replacement_raw = b"VICTIM=must-not-be-followed\n"
    replacement.write_bytes(replacement_raw)
    replacement.chmod(0o600)

    with pytest.raises(MODULE.ConfigError, match="environment-destroy-parent-changed"):
        MODULE.destroy_environment(
            environment,
            expected_parent_device=receipt["outputDirectoryDevice"],
            expected_parent_inode=receipt["outputDirectoryInode"],
            expected_environment_digest=receipt["environmentFileDigest"],
        )

    assert (moved / environment.name).read_bytes() == original_raw
    assert replacement.read_bytes() == replacement_raw


def test_destroy_environment_cli_is_secret_quiet_and_keeps_contract_receipt(
    tmp_path: Path,
):
    config, environment, snapshot, receipt, _, payload = inputs(tmp_path)
    receipt_payload = MODULE.materialize(config, environment, snapshot, receipt)

    result = subprocess.run(
        [
            str(SCRIPT), "--destroy-environment", str(environment),
            "--expected-parent-device", str(receipt_payload["outputDirectoryDevice"]),
            "--expected-parent-inode", str(receipt_payload["outputDirectoryInode"]),
            "--expected-environment-digest", receipt_payload["environmentFileDigest"],
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout == "tough_tongue_runtime_environment_destroyed=true\n"
    assert not environment.exists()
    assert snapshot.exists()
    assert receipt.exists()
    rendered = result.stdout + result.stderr
    for slot in payload["account_slots"]:  # type: ignore[index]
        assert slot["api_key"] not in rendered


def test_materialized_contract_is_the_exact_durable_compose_secret_source(
    tmp_path: Path,
):
    config, environment_file, snapshot, receipt, _, payload = inputs(tmp_path)
    MODULE.materialize(config, environment_file, snapshot, receipt)
    environment = os.environ.copy()
    for index, name in enumerate(
        (
            "CHUMMER_RUN_SERVICES_REVISION",
            "CHUMMER_PRESENTATION_REVISION",
            "CHUMMER_CORE_ENGINE_REVISION",
            "CHUMMER_HUB_REGISTRY_REVISION",
            "CHUMMER_UI_KIT_REVISION",
            "CHUMMER_MEDIA_FACTORY_REVISION",
        ),
        start=1,
    ):
        environment[name] = str(index) * 40
    for name in (
        "CHUMMER_RUN_SERVICES_SOURCE",
        "CHUMMER_PRESENTATION_SOURCE",
        "CHUMMER_CORE_ENGINE_SOURCE",
        "CHUMMER_HUB_REGISTRY_SOURCE",
        "CHUMMER_UI_KIT_SOURCE",
        "CHUMMER_MEDIA_FACTORY_SOURCE",
    ):
        environment[name] = str(ROOT)
    environment["CHUMMER_BUILD_GHOST_PRIVATE_TOOL_SERVICE_TOKEN"] = (
        "test-tool-token-" + "a" * 32
    )
    environment["CHUMMER_AI_INTERNAL_API_TOKEN"] = "test-ai-token-" + "b" * 32

    result = subprocess.run(
        [
            "docker", "compose", "--env-file", str(environment_file),
            "--project-directory", str(ROOT), "--file", str(COMPOSE),
            "config", "--format", "json",
        ],
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )

    assert result.returncode == 0, result.stderr
    rendered = json.loads(result.stdout)
    secret = rendered["secrets"][
        "build-ghost-tough-tongue-read-only-binding-contract"
    ]
    assert Path(secret["file"]) == snapshot
    ai = rendered["services"]["chummer-build-ghost-ai"]
    assert ai["environment"][
        "EA_TOUGH_TONGUE_READ_ONLY_BINDING_CONTRACT_DIGEST"
    ] == payload["read_only_contract"]["digest"]  # type: ignore[index]
    for gate in (
        "CHUMMER_BUILD_GHOST_TOUGH_TONGUE_REMOTE_EXECUTION_ENABLED",
        "CHUMMER_BUILD_GHOST_TOUGH_TONGUE_PRIVATE_CANARY_MUTATIONS_ENABLED",
        "CHUMMER_BUILD_GHOST_TOUGH_TONGUE_CANARY_READ_ONLY_ENABLED",
        "CHUMMER_BUILD_GHOST_TOUGH_TONGUE_CANARY_ACCESS_GRANT_ENABLED",
    ):
        assert ai["environment"][gate] == "false"

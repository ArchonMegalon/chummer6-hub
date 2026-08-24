from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]
HELPERS = (
    ROOT / "ops/build-ghost-private-nonprod/deploy-ai-with-rollback.sh",
    ROOT / "ops/build-ghost-private-nonprod/deploy-presentation-with-rollback.sh",
)
RUNTIME_VARIABLES = (
    "CHUMMER_BUILD_GHOST_TOUGH_TONGUE_API_KEYS",
    "CHUMMER_BUILD_GHOST_TOUGH_TONGUE_ACCOUNT_REFS",
    "CHUMMER_BUILD_GHOST_TOUGH_TONGUE_PREFERRED_ACCOUNT_REF",
    "CHUMMER_BUILD_GHOST_TOUGH_TONGUE_AGENT_ID",
    "CHUMMER_BUILD_GHOST_TOUGH_TONGUE_VOICE_ID",
    "CHUMMER_BUILD_GHOST_TOUGH_TONGUE_FUNCTION_ID",
    "CHUMMER_BUILD_GHOST_TOUGH_TONGUE_SCENARIO_ID",
    "CHUMMER_BUILD_GHOST_TOUGH_TONGUE_LIVE_AVATAR_ID",
    "CHUMMER_BUILD_GHOST_TOUGH_TONGUE_AVATAR_PROVIDER",
    "CHUMMER_BUILD_GHOST_TOUGH_TONGUE_AVATAR_NAME",
    "CHUMMER_BUILD_GHOST_TOUGH_TONGUE_AVATAR_ASSET_PATH",
    "CHUMMER_BUILD_GHOST_TOUGH_TONGUE_AVATAR_READBACK_DIGEST",
    "CHUMMER_BUILD_GHOST_TOUGH_TONGUE_AVATAR_READBACK_RECEIPT_JSON",
    "CHUMMER_BUILD_GHOST_TOUGH_TONGUE_MODEL_PROVIDER",
    "CHUMMER_BUILD_GHOST_TOUGH_TONGUE_MODEL_ID",
    "CHUMMER_BUILD_GHOST_TOUGH_TONGUE_ALLOW_LEGACY_CASCADE",
    "CHUMMER_BUILD_GHOST_TOUGH_TONGUE_READ_ONLY_BINDING_CONTRACT_FILE",
    "EA_TOUGH_TONGUE_READ_ONLY_BINDING_CONTRACT_DIGEST",
)


def digest(raw: bytes) -> str:
    return f"sha256:{hashlib.sha256(raw).hexdigest()}"


def canonical(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode()


def write_pair(directory: Path) -> tuple[Path, Path, Path]:
    directory.chmod(0o700)
    environment = directory / "runtime.env"
    contract = directory / "contract.json"
    receipt = directory / "receipt.json"
    environment_raw = b"SAFE_TEST_VALUE=opaque\n"
    contract_raw = b'{"provider_key":"tough_tongue"}\n'
    environment.write_bytes(environment_raw)
    contract.write_bytes(contract_raw)
    payload = {
        "environmentFileDigest": digest(environment_raw),
        "readOnlyContractFileDigest": digest(contract_raw),
        "contractSnapshotMode": "0400",
        "publicationOrder": ["contract-snapshot", "receipt", "environment"],
        "outputDirectoryDevice": directory.stat().st_dev,
        "outputDirectoryInode": directory.stat().st_ino,
    }
    payload["evidenceDigest"] = digest(canonical(payload))
    receipt.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    environment.chmod(0o600)
    contract.chmod(0o400)
    receipt.chmod(0o600)
    return environment, contract, receipt


def verify(helper: Path, environment: Path, contract: Path, receipt: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "bash", "-c",
            'source "$1"; verify_materialized_runtime_pair "$2" "$3" "$4"',
            "runtime-pair-test", str(helper), str(environment), str(contract), str(receipt),
        ],
        check=False,
        capture_output=True,
        text=True,
    )


@pytest.mark.parametrize("helper", HELPERS)
def test_all_three_compose_paths_use_one_complete_operator_config_or_stay_blocked(helper: Path):
    script = helper.read_text(encoding="utf-8")
    assert 'operator_runtime_config_file="${CHUMMER_BUILD_GHOST_TOUGH_TONGUE_OPERATOR_CONFIG_FILE:-}"' in script
    assert 'operator_runtime_evidence_root="${CHUMMER_BUILD_GHOST_TOUGH_TONGUE_RUNTIME_EVIDENCE_ROOT:-}"' in script
    assert '--output-contract "$runtime_contract_file"' in script
    assert 'compose_environment_args=(--env-file "$runtime_environment_file")' in script
    assert 'docker compose "${compose_environment_args[@]}"' in script
    assert 'prepare_operator_runtime_config\n    validate_sources_and_labels' in script
    assert (
        'configured-readback-contract-requires-operator-config' in script
        or 'quarantine_provider_runtime_without_output' in script
    )
    assert 'compose-stock-avatar-readback-drift' in script
    assert '.providerReadbackVerified == false' in script
    assert '.providerActivationAuthorized == false' in script
    assert '.providerMutationPerformed == false' in script
    assert 'EA_TOUGH_TONGUE_READ_ONLY_BINDING_CONTRACT_PATH == "/run/secrets/tough-tongue-read-only-binding-contract.json"' in script
    for variable in RUNTIME_VARIABLES:
        assert variable in script


@pytest.mark.parametrize("helper", HELPERS)
def test_every_bounded_deployer_accepts_only_complete_binding_or_exact_account_audit_only(
    helper: Path,
):
    script = helper.read_text(encoding="utf-8")
    assert '.readyForResourceBinding == false' in script
    assert '.providerPlanLabelReadbackVerified == false' in script
    assert '.bindingCandidatesConfigured == true' in script
    assert '.bindingCandidatesConfigured == false' in script
    assert '.candidateRefCount == 0' in script
    assert '.candidateRefDigests == {}' in script
    assert '.readyForAccountSelection == true' in script
    assert '.accountSelectionPolicySource == "user_authority"' in script
    assert '.premiumBasis == "operator_policy_available_minutes_gt_threshold"' in script
    assert '.premiumThresholdMinutes == 1100' in script
    assert '.premiumValidityCalendarMonths == 11' in script
    assert '.premiumGrantCount > 0' in script
    assert "compose-audit-only-candidates-drift" in script
    assert "compose-binding-candidates-drift" in script
    assert "CHUMMER_BUILD_GHOST_TOUGH_TONGUE_AVATAR_READBACK_RECEIPT_JSON" in script
    for variable in RUNTIME_VARIABLES[3:8]:
        assert f".services[$service].environment.{variable} == \"\"" in script
        assert f".services[$service].environment.{variable} != \"\"" in script


@pytest.mark.parametrize("helper", HELPERS)
def test_configured_contract_and_receipt_are_durable_but_credentials_are_scrubbed(
    helper: Path,
):
    script = helper.read_text(encoding="utf-8")
    assert 'fail "operator-tough-tongue-evidence-root-required"' in script
    assert 'resolved_root="$(realpath -e -- "$operator_runtime_evidence_root")"' in script
    assert '"$operator_runtime_evidence_root/runtime.XXXXXXXXXXXX"' in script
    assert 'runtime_environment_file="$runtime_evidence_dir/runtime.env"' in script
    assert 'runtime_contract_file="$runtime_evidence_dir/read-only-contract.json"' in script
    assert 'runtime_receipt_file="$runtime_evidence_dir/runtime-receipt.json"' in script
    assert 'securely_remove_runtime_environment' in script
    assert '--destroy-environment "$runtime_environment_file"' in script
    assert '--expected-parent-device "$runtime_evidence_device"' in script
    assert '--expected-parent-inode "$runtime_evidence_inode"' in script
    assert '--expected-environment-digest "$runtime_environment_digest"' in script
    assert "environment-cleanup-failed" in script
    assert 'credentials_retained=false' in script
    assert 'shred --force --remove=unlink --zero "$runtime_contract_file"' not in script
    assert 'shred --force --remove=unlink --zero "$runtime_receipt_file"' not in script


@pytest.mark.parametrize("helper", HELPERS)
def test_helper_accepts_only_a_stable_digest_bound_single_inode_pair(
    tmp_path: Path, helper: Path
):
    environment, contract, receipt = write_pair(tmp_path)

    result = verify(helper, environment, contract, receipt)

    assert result.returncode == 0, result.stderr
    assert result.stdout == ""
    assert result.stderr == ""


@pytest.mark.parametrize("helper", HELPERS)
def test_helper_rejects_environment_content_drift_before_compose(
    tmp_path: Path, helper: Path
):
    environment, contract, receipt = write_pair(tmp_path)
    environment.write_bytes(environment.read_bytes() + b"DRIFT=blocked\n")
    environment.chmod(0o600)

    result = verify(helper, environment, contract, receipt)

    assert result.returncode != 0
    assert "stage=operator-tough-tongue-pair-digest-invalid" in result.stderr


@pytest.mark.parametrize("helper", HELPERS)
def test_helper_rejects_linked_environment_left_by_interrupted_publication(
    tmp_path: Path, helper: Path
):
    environment, contract, receipt = write_pair(tmp_path)
    os.link(environment, tmp_path / "interrupted-runtime.tmp")

    result = verify(helper, environment, contract, receipt)

    assert result.returncode != 0
    assert "stage=operator-tough-tongue-environment-authority-invalid" in result.stderr


@pytest.mark.parametrize("helper", HELPERS)
def test_helper_cleanup_never_follows_a_retargeted_runtime_directory(
    tmp_path: Path, helper: Path
):
    run = tmp_path / "run"
    run.mkdir(mode=0o700)
    environment, _, receipt = write_pair(run)
    receipt_payload = json.loads(receipt.read_text(encoding="utf-8"))
    original_raw = environment.read_bytes()
    moved = tmp_path / "original"
    run.rename(moved)
    run.mkdir(mode=0o700)
    replacement = run / environment.name
    replacement_raw = b"VICTIM=must-not-be-followed\n"
    replacement.write_bytes(replacement_raw)
    replacement.chmod(0o600)

    result = subprocess.run(
        [
            "bash", "-c",
            'source "$1"; runtime_environment_file="$2"; '
            'runtime_evidence_device="$3"; runtime_evidence_inode="$4"; '
            'runtime_environment_digest="$5"; securely_remove_runtime_environment',
            "runtime-cleanup-test", str(helper), str(environment),
            str(receipt_payload["outputDirectoryDevice"]),
            str(receipt_payload["outputDirectoryInode"]),
            receipt_payload["environmentFileDigest"],
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "environment-cleanup-failed" in result.stderr
    assert (moved / environment.name).read_bytes() == original_raw
    assert replacement.read_bytes() == replacement_raw


@pytest.mark.parametrize("helper", HELPERS)
def test_helper_rejects_a_receipt_whose_evidence_digest_was_resealed_incorrectly(
    tmp_path: Path, helper: Path
):
    environment, contract, receipt = write_pair(tmp_path)
    payload = json.loads(receipt.read_text(encoding="utf-8"))
    payload["evidenceDigest"] = "sha256:" + "0" * 64
    receipt.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    receipt.chmod(0o600)

    result = verify(helper, environment, contract, receipt)

    assert result.returncode != 0
    assert "stage=operator-tough-tongue-receipt-digest-invalid" in result.stderr

from __future__ import annotations

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
SPEC = importlib.util.spec_from_file_location("tough_tongue_runtime_config", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def digest(raw: bytes) -> str:
    return f"sha256:{hashlib.sha256(raw).hexdigest()}"


def canonical(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode()


def contract_payload() -> dict[str, object]:
    common = {
        "resource_ref": "id",
        "account_ref": "owner.account",
        "organization_ref": "owner.organization",
    }
    return {
        "schema": "ea.tough_tongue.read_only_binding_contract.v1",
        "provider_key": "tough_tongue",
        "base_url": "https://api.toughtongueai.com/api/public",
        "source_type": "provider_documentation",
        "verified_at": "2026-08-23T10:00:00Z",
        "authority": {
            "operator_verified": True,
            "source_ref_sha256": "sha256:" + "a" * 64,
        },
        "premium_plan_values": ["premium"],
        "live_avatar_providers": ["anam", "liveavatar"],
        "routes": {
            "account": {
                "method": "GET",
                "path": "account",
                "selectors": {
                    "account_ref": "account.ref",
                    "organization_ref": "account.organization",
                    "plan_name": "subscription.plan",
                    "live_avatar_entitled": "entitlements.live_avatar",
                },
            },
            "agent": {"method": "GET", "path": "agents/{resource_ref}", "selectors": common},
            "voice": {"method": "GET", "path": "voices/{resource_ref}", "selectors": common},
            "function": {"method": "GET", "path": "functions/{resource_ref}", "selectors": common},
            "scenario": {
                "method": "GET",
                "path": "scenarios/{resource_ref}",
                "selectors": {
                    **common,
                    "live_avatar_ref": "appearance.live_avatar_id",
                    "live_avatar_provider": "appearance.live_avatar_provider",
                    "voice_ref": "voice.id",
                    "function_refs": "functions.ids",
                },
            },
        },
    }


def operator_payload(contract_path: Path, contract: dict[str, object]) -> dict[str, object]:
    refs = ["sha256:" + character * 64 for character in "123"]
    return {
        "schema": "chummer.build_ghost.tough_tongue.runtime_config.v1",
        "account_slots": [
            {"account_ref": refs[0], "api_key": "private-read-only-key-one"},
            {"account_ref": refs[1], "api_key": "private-read-only-key-two"},
            {"account_ref": refs[2], "api_key": "private-read-only-key-three"},
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
    assert receipt["providerReadbackVerified"] is False
    assert receipt["providerActivationAuthorized"] is False
    assert receipt["providerMutationPerformed"] is False
    assert receipt["environmentFileDigest"] == digest(environment_raw)
    assert receipt["readOnlyContractFileDigest"] == digest(contract_raw)
    assert receipt["publicationOrder"] == ["contract-snapshot", "receipt", "environment"]
    assert receipt["evidenceDigest"] == digest(
        canonical({key: value for key, value in receipt.items() if key != "evidenceDigest"})
    )
    assert json.loads(contract_raw) == contract_payload()
    environment_text = environment_raw.decode()
    assert f"CHUMMER_BUILD_GHOST_TOUGH_TONGUE_READ_ONLY_BINDING_CONTRACT_FILE={snapshot}" in environment_text
    rendered_receipt = receipt_path.read_text(encoding="utf-8")
    for slot in payload["account_slots"]:  # type: ignore[index]
        assert slot["api_key"] not in rendered_receipt
    for candidate in payload["candidate_refs"].values():  # type: ignore[union-attr]
        assert candidate not in rendered_receipt


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

    def fail_selected(path: Path, raw: bytes, mode: int) -> None:
        if path.name == names[failed_publication]:
            raise OSError("injected-publication-fault")
        real_publish(path, raw, mode)

    monkeypatch.setattr(MODULE, "_publish_new", fail_selected)
    with pytest.raises(OSError, match="injected-publication-fault"):
        MODULE.materialize(config, environment, snapshot, receipt)

    assert not usable(environment, 0o600)
    if environment.exists():
        assert usable(receipt, 0o600)


@pytest.mark.parametrize("failed_publication", ("contract", "receipt", "environment"))
def test_fault_between_link_and_unlink_is_rejected_by_single_inode_authority(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failed_publication: str
):
    config, environment, snapshot, receipt, _, _ = inputs(tmp_path)
    selected = {
        "contract": snapshot.name,
        "receipt": receipt.name,
        "environment": environment.name,
    }[failed_publication]
    real_unlink = MODULE.os.unlink
    injected = False

    def fail_selected(path: object, *args: object, **kwargs: object) -> None:
        nonlocal injected
        if not injected and isinstance(path, str) and path.startswith(f".{selected}."):
            injected = True
            raise OSError("injected-unlink-fault")
        real_unlink(path, *args, **kwargs)

    monkeypatch.setattr(MODULE.os, "unlink", fail_selected)
    with pytest.raises(OSError, match="injected-unlink-fault"):
        MODULE.materialize(config, environment, snapshot, receipt)

    assert not usable(environment, 0o600)


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


@pytest.mark.parametrize("invalidity", ("authority", "method"))
def test_contract_must_be_exact_get_only_and_operator_verified(
    tmp_path: Path, invalidity: str
):
    config, environment, snapshot, receipt, source_contract, payload = inputs(tmp_path)
    contract = contract_payload()
    if invalidity == "authority":
        contract["authority"]["operator_verified"] = False  # type: ignore[index]
        expected = "read-only-contract-authority-invalid"
    else:
        contract["routes"]["scenario"]["method"] = "POST"  # type: ignore[index]
        expected = "read-only-contract-route-scenario-invalid"
    write_private_json(source_contract, contract)
    payload["read_only_contract"]["digest"] = digest(canonical(contract))  # type: ignore[index]
    write_private_json(config, payload)

    with pytest.raises(MODULE.ConfigError, match=expected):
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

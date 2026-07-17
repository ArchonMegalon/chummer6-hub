from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "validate_public_pwa_proof_authority.py"
AUTHORITY = ROOT / "Chummer.Run.Api/public-pwa-proof-authority.json"
VERIFIER = ROOT / "scripts/verify_public_pwa_static_assets.py"
GENERATOR = ROOT / "scripts/generate_public_play_worker_projection.py"
INVENTORY = ROOT / "Chummer.Run.Api/play-pwa-required-inventory.json"
MIRROR = ROOT / "Chummer.Run.Api/play-pwa-mirrors.json"
PROJECTION = ROOT / "Chummer.Run.Api/play-worker-projection.json"
TEMPLATE = ROOT / "Chummer.Run.Api/service-worker.public-edge.template.js"


def load_module():
    spec = importlib.util.spec_from_file_location("validate_public_pwa_proof_authority", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_validator_source_markers_match_install_only_projection_contract() -> None:
    module = load_module()
    projection = json.loads(PROJECTION.read_text(encoding="utf-8"))
    required_markers = tuple(projection["requiredSourceMarkers"])

    assert required_markers == module.EXPECTED_SOURCE_MARKERS
    assert '"/mobile-install-shell.js"' in required_markers
    assert '"/manifest.observer.webmanifest"' in required_markers
    assert '"/mobile-turn-companion.js"' not in required_markers


def test_current_authority_is_strict_canonical_and_digest_bound() -> None:
    module = load_module()
    receipt = module.validate(
        AUTHORITY,
        VERIFIER,
        GENERATOR,
        INVENTORY,
        MIRROR,
        PROJECTION,
        TEMPLATE,
    )

    assert receipt["contractName"] == module.RECEIPT_CONTRACT_NAME
    assert receipt["contractVersion"] == module.RECEIPT_CONTRACT_VERSION
    assert receipt["status"] == "pass"
    assert tuple(receipt["inputs"]) == (
        "authority",
        "verifier",
        "generator",
        "inventory",
        "mirror",
        "projection",
        "template",
    )
    assert receipt["closedPolicy"] == {
        "policyId": module.POLICY_ID,
        "assetPolicyCount": 12,
        "dependencyPolicyCount": 4,
    }
    for input_receipt in receipt["inputs"].values():
        assert set(input_receipt) == {"path", "sha256", "identity"}
        assert len(input_receipt["sha256"]) == 64
        assert set(input_receipt["identity"]) == {
            "device",
            "inode",
            "size",
            "modifiedTimeNanoseconds",
            "changedTimeNanoseconds",
        }


def validator_command(*, receipt: Path, verifier: Path = VERIFIER) -> list[str]:
    return [
        sys.executable,
        "-I",
        "-S",
        str(SCRIPT),
        "--authority",
        str(AUTHORITY),
        "--verifier",
        str(verifier),
        "--generator",
        str(GENERATOR),
        "--inventory",
        str(INVENTORY),
        "--mirror",
        str(MIRROR),
        "--projection",
        str(PROJECTION),
        "--template",
        str(TEMPLATE),
        "--receipt",
        str(receipt),
    ]


def test_isolated_cli_writes_canonical_duplicate_free_pass_receipt(
    tmp_path: Path,
) -> None:
    module = load_module()
    receipt_path = tmp_path / "receipt.json"

    completed = subprocess.run(
        validator_command(receipt=receipt_path),
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
    payload = receipt_path.read_bytes()
    receipt = module.strict_json_object(payload, label="validation receipt")
    assert receipt["status"] == "pass"
    assert receipt["interpreter"] == {
        "executable": sys.executable,
        "implementation": "cpython",
        "version": list(sys.version_info[:3]),
        "isolated": True,
        "noSite": True,
        "ignoreEnvironment": True,
        "safePath": True,
    }
    assert payload == (json.dumps(receipt, indent=2) + "\n").encode("utf-8")
    assert not tuple(tmp_path.glob(".receipt.json.*.tmp"))


def test_receipt_is_not_replaced_when_validation_fails(tmp_path: Path) -> None:
    receipt_path = tmp_path / "receipt.json"
    original = b"existing receipt must survive\n"
    receipt_path.write_bytes(original)
    verifier = tmp_path / "verifier.py"
    verifier.write_text("drift\n", encoding="utf-8")

    completed = subprocess.run(
        validator_command(receipt=receipt_path, verifier=verifier),
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 1
    assert receipt_path.read_bytes() == original
    assert not tuple(tmp_path.glob(".receipt.json.*.tmp"))


def test_receipt_requires_isolated_no_site_cli(tmp_path: Path) -> None:
    command = validator_command(receipt=tmp_path / "receipt.json")
    del command[1:3]

    completed = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 1
    assert "receipt output requires isolated" in completed.stdout
    assert not (tmp_path / "receipt.json").exists()


def test_receipt_cannot_replace_a_proof_input() -> None:
    completed = subprocess.run(
        validator_command(receipt=AUTHORITY),
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 1
    assert "must not replace a proof input" in completed.stdout


def test_authority_parser_rejects_duplicate_fields() -> None:
    module = load_module()
    with pytest.raises(RuntimeError, match="strict UTF-8 JSON"):
        module.strict_json_object(b'{"contractName":"a","contractName":"b"}\n')


def test_authority_parser_rejects_noncanonical_json() -> None:
    module = load_module()
    with pytest.raises(RuntimeError, match="canonical"):
        module.strict_json_object(b'{"contractName":"a"}\n')


def test_authority_validator_rejects_wrong_typed_count(tmp_path: Path) -> None:
    module = load_module()
    authority = json.loads(
        (ROOT / "Chummer.Run.Api/public-pwa-proof-authority.json").read_text(
            encoding="utf-8"
        )
    )
    authority["assetPolicyCount"] = "12"
    path = tmp_path / "authority.json"
    path.write_text(json.dumps(authority, indent=2) + "\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="assetPolicyCount"):
        module.validate(
            path,
            VERIFIER,
            GENERATOR,
            INVENTORY,
            MIRROR,
            PROJECTION,
            TEMPLATE,
        )


def test_authority_validator_rejects_digest_drift(tmp_path: Path) -> None:
    module = load_module()
    verifier = tmp_path / "verifier.py"
    verifier.write_text("drift\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="verifierSha256"):
        module.validate(
            AUTHORITY,
            verifier,
            GENERATOR,
            INVENTORY,
            MIRROR,
            PROJECTION,
            TEMPLATE,
        )


def test_authority_validator_rejects_stale_verifier_digest(tmp_path: Path) -> None:
    module = load_module()
    authority = json.loads(AUTHORITY.read_text(encoding="utf-8"))
    authority["verifierSha256"] = (
        "b5fa1a2863fe19f57cfe1d56ee6961f1eb92ec48829484ad740942e96d2210d7"
    )
    stale_authority = tmp_path / "stale-authority.json"
    stale_authority.write_text(
        json.dumps(authority, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError, match="verifierSha256"):
        module.validate(
            stale_authority,
            VERIFIER,
            GENERATOR,
            INVENTORY,
            MIRROR,
            PROJECTION,
            TEMPLATE,
        )


@pytest.mark.parametrize(
    ("label", "payload"),
    (
        ("required inventory", b'{"contract":"a","contract":"b"}\n'),
        ("worker projection", b'{"contract":"a","contract":"b"}\n'),
        ("mirror contract", b'{"contract":"a","contract":"b"}\n'),
    ),
)
def test_all_docker_json_contract_parsers_reject_duplicate_fields(
    label: str,
    payload: bytes,
) -> None:
    module = load_module()
    with pytest.raises(RuntimeError, match="strict UTF-8 JSON"):
        module.strict_json_object(payload, label=label)


def test_inventory_validator_rejects_duplicate_rows() -> None:
    module = load_module()
    inventory = json.loads(INVENTORY.read_text(encoding="utf-8"))
    inventory["assets"][-1] = dict(inventory["assets"][0])
    with pytest.raises(RuntimeError, match="duplicate asset identity"):
        module.validate_inventory_contract(inventory)


def test_projection_validator_rejects_extra_schema_field() -> None:
    module = load_module()
    projection = json.loads(PROJECTION.read_text(encoding="utf-8"))
    projection["optimistic"] = True
    with pytest.raises(RuntimeError, match="fields drifted"):
        module.validate_projection_contract(
            projection,
            inventory_sha256="0" * 64,
            template_sha256="0" * 64,
        )


def test_mirror_validator_rejects_wrong_typed_count(tmp_path: Path) -> None:
    module = load_module()
    mirror = json.loads(MIRROR.read_text(encoding="utf-8"))
    mirror["assetPolicyCount"] = "12"
    mirror_path = tmp_path / "play-pwa-mirrors.json"
    mirror_path.write_text(json.dumps(mirror, indent=2) + "\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="assetPolicyCount"):
        module.validate(
            AUTHORITY,
            VERIFIER,
            GENERATOR,
            INVENTORY,
            mirror_path,
            PROJECTION,
            TEMPLATE,
        )

from __future__ import annotations

import base64
import copy
import importlib.util
import json
import struct
import zlib
from datetime import UTC, datetime, timedelta
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "google_oauth_linking_evidence_v2.py"


def load_module():
    spec = importlib.util.spec_from_file_location("google_oauth_linking_evidence_v2_test", SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def write_release(path: Path, *, version: str = "run-20260713-123603") -> None:
    write_json(
        path,
        {
            "version": version,
            "channelId": "preview",
            "supportabilityState": "review_required",
            "rolloutState": "promoted_preview",
            "publishedAt": "2026-07-13T12:38:14Z",
        },
    )


def png_chunk(kind: bytes, data: bytes) -> bytes:
    return (
        struct.pack(">I", len(data))
        + kind
        + data
        + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    )


def write_valid_png(path: Path, *, seed: int) -> None:
    width, height = 640, 360
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    row = bytes((index + seed) % 256 for index in range(width * 3))
    pixels = b"".join(b"\x00" + row for _ in range(height))
    payload = (
        b"\x89PNG\r\n\x1a\n"
        + png_chunk(b"IHDR", ihdr)
        + png_chunk(b"tEXt", (f"proof-{seed}:".encode() + bytes([65 + seed]) * 5000))
        + png_chunk(b"IDAT", zlib.compress(pixels, level=6))
        + png_chunk(b"IEND", b"")
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)


def build_current_request(module, tmp_path: Path, now: datetime) -> tuple[Path, Path, Path, dict]:
    portal = tmp_path / "portal-release.json"
    hub = tmp_path / "hub-release.json"
    live = tmp_path / "live-release.json"
    for path in (portal, hub, live):
        write_release(path)
    release = module.release_authority_binding(
        portal_path=portal,
        hub_path=hub,
        live_capture_path=live,
        live_captured_at_utc=module.isoformat_utc(now),
    )
    assert release["ready"] is True
    programs = module.program_bindings()
    stage_root = tmp_path.resolve()
    request_path = (stage_root / "request.json").resolve()
    evidence_path = (stage_root / "imported" / "evidence.json").resolve()
    proof_path = (stage_root / "proof.json").resolve()
    template_path = (stage_root / "operator-template.json").resolve()
    incoming_root = (stage_root / "incoming").resolve()
    artifact_intake = {
        "dedicated_drop_root": str(incoming_root),
        "auto_import_roots": [str(incoming_root)],
        "post_import_argv_plan": module.fixed_post_import_argv_plan(
            base_url=module.DEFAULT_BASE_URL,
            request_path=request_path,
            evidence_path=evidence_path,
            proof_path=proof_path,
        ),
    }
    request = {
        "contract_name": module.REQUEST_CONTRACT_NAME,
        "generated_at_utc": module.isoformat_utc(now),
        "status": "operator_action_required",
        "base_url": module.DEFAULT_BASE_URL,
        "request_nonce": "ab" * 32,
        "request_binding_sha256": module.request_binding_sha256(
            base_url=module.DEFAULT_BASE_URL,
            release=release,
            programs=programs,
        ),
        "release": release,
        "program_bindings": programs,
        "media_policy": module.media_policy(),
        "required_steps": list(module.REQUIRED_OPERATOR_STEPS),
        "request_receipt_path": str(request_path),
        "required_output_path": str(evidence_path),
        "required_receipt_path": str(evidence_path),
        "required_operator_evidence_path": str(evidence_path),
        "required_proof_path": str(proof_path),
        "template_path": str(template_path),
        "operator_evidence_template_path": str(template_path),
        "operator_message_path": str(stage_root / "operator-ask.txt"),
        "operator_ask_text_path": str(stage_root / "operator-ask.txt"),
        "operator_ask_metadata_path": str(stage_root / "operator-ask.json"),
        "preferred_drop_folder": str(incoming_root),
        "recommended_screenshot_paths": [],
        "materialization_scope": {
            "mode": "staged",
            "root": str(stage_root),
            "self_contained": True,
            "proof_output_path": str(proof_path),
        },
        "artifact_intake": artifact_intake,
        "intake": artifact_intake,
    }
    write_json(request_path, request)
    return request_path, portal, hub, request


def build_evidence(module, tmp_path: Path, now: datetime, request_path: Path, portal: Path, hub: Path) -> tuple[Path, Path, dict]:
    request_payload, request_summary, request_raw, failures = module.verify_request_file(
        request_path,
        portal_release_manifest_path=portal,
        hub_release_manifest_path=hub,
        now=now,
    )
    assert failures == []
    imported_root = tmp_path / "imported"
    image_a = imported_root / "one.png"
    image_b = imported_root / "two.png"
    write_valid_png(image_a, seed=1)
    write_valid_png(image_b, seed=2)
    screenshots = []
    for name, path in (("one.png", image_a), ("two.png", image_b)):
        actual, image_failures = module.inspect_image(path)
        assert image_failures == []
        screenshots.append({"logical_name": name, "path": str(path), **{key: actual[key] for key in ("sha256", "size_bytes", "width", "height", "media_type")}})
    release = request_summary["release"]
    evidence = {
        "contract_name": module.EVIDENCE_CONTRACT_NAME,
        "status": "pass",
        "base_url": module.DEFAULT_BASE_URL,
        "observed_at_utc": module.isoformat_utc(now),
        "request_nonce": request_payload["request_nonce"],
        "request_sha256": module.sha256_bytes(request_raw),
        "release_authority_sha256": module.sha256_json(release),
        "portal_release_manifest_sha256": release["portal"]["manifest_sha256"],
        "hub_release_manifest_sha256": release["hub_registry"]["manifest_sha256"],
        "live_release_manifest_sha256": release["live"]["manifest_sha256"],
        "verified_steps": list(module.REQUIRED_OPERATOR_STEPS),
        "screenshots": screenshots,
    }
    core = module.evidence_core(evidence, [{key: row[key] for key in ("logical_name", "sha256", "size_bytes", "width", "height", "media_type")} for row in screenshots])
    evidence["attestation"] = {
        "contract_name": module.ATTESTATION_CONTRACT_NAME,
        "algorithm": "ed25519",
        "key_id": "untrusted-test-key",
        "role": module.ATTESTATION_ROLE,
        "generated_at_utc": module.isoformat_utc(now),
        **module.attestation_claims(core),
        "signature": base64.b64encode(b"\0" * 64).decode(),
    }
    evidence_path = imported_root / "evidence.json"
    write_json(evidence_path, evidence)
    return evidence_path, imported_root, evidence


def test_code_owned_operator_identity_map_is_empty() -> None:
    module = load_module()
    assert module.TRUSTED_OPERATOR_IDENTITIES == {}


def test_two_byte_ok_files_are_rejected_as_images_and_as_duplicate_proof(
    tmp_path: Path,
) -> None:
    module = load_module()
    now = datetime.now(UTC)
    request_path, portal, hub, _request = build_current_request(module, tmp_path, now)
    evidence_path, imported_root, evidence = build_evidence(module, tmp_path, now, request_path, portal, hub)
    for row in evidence["screenshots"]:
        Path(row["path"]).write_bytes(b"ok")
        row.update({"sha256": module.sha256_bytes(b"ok"), "size_bytes": 2, "width": 0, "height": 0, "media_type": None})
    summary, failures = module.verify_evidence_payload(
        evidence,
        evidence_path=evidence_path,
        request_path=request_path,
        portal_release_manifest_path=portal,
        hub_release_manifest_path=hub,
        allowed_screenshot_root=imported_root,
        require_import_provenance=False,
        now=now,
    )
    assert summary["pass"] is False
    assert any("not a structurally recognizable PNG or JPEG" in item for item in failures)
    assert any("smaller than 4096 bytes" in item for item in failures)
    assert any("digests must be distinct" in item for item in failures)


def test_missing_and_wrong_signer_are_rejected(tmp_path: Path) -> None:
    module = load_module()
    now = datetime.now(UTC)
    request_path, portal, hub, _request = build_current_request(module, tmp_path, now)
    evidence_path, imported_root, evidence = build_evidence(module, tmp_path, now, request_path, portal, hub)
    missing = copy.deepcopy(evidence)
    missing.pop("attestation")
    _summary, failures = module.verify_evidence_payload(
        missing,
        evidence_path=evidence_path,
        request_path=request_path,
        portal_release_manifest_path=portal,
        hub_release_manifest_path=hub,
        allowed_screenshot_root=imported_root,
        require_import_provenance=False,
        now=now,
    )
    assert "detached operator attestation is missing" in failures
    _summary, failures = module.verify_evidence_payload(
        evidence,
        evidence_path=evidence_path,
        request_path=request_path,
        portal_release_manifest_path=portal,
        hub_release_manifest_path=hub,
        allowed_screenshot_root=imported_root,
        require_import_provenance=False,
        now=now,
    )
    assert any("key_id is not allowlisted" in item for item in failures)


def test_stale_request_and_release_replay_are_rejected(tmp_path: Path) -> None:
    module = load_module()
    now = datetime.now(UTC)
    request_path, portal, hub, request = build_current_request(module, tmp_path, now)
    stale = copy.deepcopy(request)
    stale["generated_at_utc"] = module.isoformat_utc(now - module.REQUEST_MAX_AGE - timedelta(minutes=1))
    _summary, failures = module.verify_request_payload(
        stale,
        request_path=request_path,
        portal_release_manifest_path=portal,
        hub_release_manifest_path=hub,
        now=now,
    )
    assert "generated_at_utc is stale" in failures
    write_release(portal, version="run-20260714-replayed")
    _summary, failures = module.verify_request_payload(
        request,
        request_path=request_path,
        portal_release_manifest_path=portal,
        hub_release_manifest_path=hub,
        now=now,
    )
    assert any("release binding does not match" in item for item in failures)
    assert any("portal_and_hub_release_identity_disagree" in item for item in failures)


def test_screenshot_mutation_after_observation_is_rejected(tmp_path: Path) -> None:
    module = load_module()
    now = datetime.now(UTC)
    request_path, portal, hub, _request = build_current_request(module, tmp_path, now)
    evidence_path, imported_root, evidence = build_evidence(module, tmp_path, now, request_path, portal, hub)
    Path(evidence["screenshots"][0]["path"]).write_bytes(b"mutated")
    _summary, failures = module.verify_evidence_payload(
        evidence,
        evidence_path=evidence_path,
        request_path=request_path,
        portal_release_manifest_path=portal,
        hub_release_manifest_path=hub,
        allowed_screenshot_root=imported_root,
        require_import_provenance=False,
        now=now,
    )
    assert any("screenshots[1].sha256 does not match current bytes" in item for item in failures)
    assert any("not a structurally recognizable PNG or JPEG" in item for item in failures)


def test_program_drift_and_intake_command_injection_are_rejected(tmp_path: Path) -> None:
    module = load_module()
    now = datetime.now(UTC)
    request_path, portal, hub, request = build_current_request(module, tmp_path, now)
    forged = copy.deepcopy(request)
    forged["program_bindings"]["proof_verifier"]["sha256"] = "0" * 64
    forged["artifact_intake"]["post_import_commands"] = ["touch /tmp/owned"]
    _summary, failures = module.verify_request_payload(
        forged,
        request_path=request_path,
        portal_release_manifest_path=portal,
        hub_release_manifest_path=hub,
        now=now,
    )
    assert "program_bindings do not match the current verifier/importer bytes" in failures
    assert "artifact_intake.post_import_commands is forbidden" in failures


def test_pytest_import_provenance_is_rejected_even_with_pass_shape(tmp_path: Path) -> None:
    module = load_module()
    now = datetime.now(UTC)
    request_path, portal, hub, _request = build_current_request(module, tmp_path, now)
    evidence_path, imported_root, evidence = build_evidence(module, tmp_path, now, request_path, portal, hub)
    evidence["import_source_artifact"] = str(tmp_path / "test_materialize_suppresses_re0" / "proof.json")
    _summary, failures = module.verify_evidence_payload(
        evidence,
        evidence_path=evidence_path,
        request_path=request_path,
        portal_release_manifest_path=portal,
        hub_release_manifest_path=hub,
        allowed_screenshot_root=imported_root,
        require_import_provenance=False,
        now=now,
    )
    assert "import_source_artifact contains pytest/test-fixture provenance" in failures


def test_forged_pass_proof_is_rebound_to_current_files_and_rejected(tmp_path: Path) -> None:
    module = load_module()
    now = datetime.now(UTC)
    request_path, portal, hub, _request = build_current_request(module, tmp_path, now)
    evidence_path, _imported_root, _evidence = build_evidence(module, tmp_path, now, request_path, portal, hub)
    forged = {
        "contract_name": module.PROOF_CONTRACT_NAME,
        "proof_contract_version": module.PROOF_CONTRACT_VERSION,
        "status": "pass",
        "generated_at_utc": module.isoformat_utc(now),
        "base_url": module.DEFAULT_BASE_URL,
        "bindings": {},
        "quick_handoff_probe": {"pass": True},
        "signed_in_link_handoff": {"status": "pass"},
        "failures": [],
    }
    _summary, failures = module.verify_proof_payload(
        forged,
        request_path=request_path,
        evidence_path=evidence_path,
        portal_release_manifest_path=portal,
        hub_release_manifest_path=hub,
        require_pass=True,
        now=now,
    )
    assert any("evidence: attestation: attestation key_id is not allowlisted" in item for item in failures)
    assert "proof bindings do not match current release/request/evidence/program bytes" in failures
    assert "pass-shaped proof is not backed by current verified evidence" in failures

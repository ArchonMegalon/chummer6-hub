from __future__ import annotations

import base64
import importlib.util
import json
import struct
import zipfile
import zlib
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace


SCRIPT_PATH = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "google_oauth_linking_evidence_v2_cli.py"
)


def load_module():
    spec = importlib.util.spec_from_file_location("google_oauth_linking_evidence_v2_cli_test", SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def write_release(path: Path, *, rollout: str = "public_release_review_required") -> None:
    write_json(
        path,
        {
            "version": "run-20260802-160500",
            "channelId": "preview",
            "supportabilityState": "review_required",
            "rolloutState": rollout,
            "publishedAt": "2026-08-11T04:00:00Z",
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


def request_args(module, tmp_path: Path, *, rollout: str = "public_release_review_required"):
    portal = tmp_path / "portal.json"
    hub = tmp_path / "hub.json"
    live = tmp_path / "live.json"
    write_release(portal, rollout=rollout)
    write_release(hub, rollout=rollout)
    write_release(live, rollout=rollout)
    return SimpleNamespace(
        request=tmp_path / "request.json",
        base_url=module.contract.DEFAULT_BASE_URL,
        portal_release_manifest=portal,
        hub_release_manifest=hub,
        live_release_manifest=live,
        live_captured_at=module.contract.isoformat_utc(datetime.now(UTC)),
        evidence=None,
        proof=None,
        template=None,
        incoming_root=None,
    )


def test_capture_live_manifest_preserves_exact_json_bytes(tmp_path: Path, monkeypatch) -> None:
    module = load_module()
    raw = b'{"version":"run-20260802-160500","channelId":"preview"}\n'
    response = SimpleNamespace(
        content=raw,
        raise_for_status=lambda: None,
    )
    observed: dict[str, object] = {}

    def fake_get(url: str, **kwargs):
        observed.update({"url": url, **kwargs})
        return response

    monkeypatch.setattr(module.requests, "get", fake_get)
    output = tmp_path / "live-release.json"
    result = module.capture_live_manifest("https://example.invalid/release.json", output)

    assert output.read_bytes() == raw
    assert result["sha256"] == module.contract.sha256_bytes(raw)
    assert result["size_bytes"] == len(raw)
    assert observed["allow_redirects"] is False
    assert observed["timeout"] == 30


def test_capture_live_manifest_rejects_non_object_json(tmp_path: Path, monkeypatch) -> None:
    module = load_module()
    response = SimpleNamespace(content=b"[]\n", raise_for_status=lambda: None)
    monkeypatch.setattr(module.requests, "get", lambda *args, **kwargs: response)
    output = tmp_path / "live-release.json"

    try:
        module.capture_live_manifest("https://example.invalid/release.json", output)
    except SystemExit as exc:
        assert "root is not an object" in str(exc)
    else:
        raise AssertionError("non-object release JSON was accepted")
    assert not output.exists()


def test_materialize_request_is_v2_release_and_program_bound_and_reuses_identity(tmp_path: Path) -> None:
    module = load_module()
    args = request_args(module, tmp_path)

    assert module.materialize_request(args) == 0
    first = module.read_json(args.request)
    assert first["contract_name"] == module.contract.REQUEST_CONTRACT_NAME
    assert first["status"] == "operator_action_required"
    assert first["release"]["ready"] is True
    assert first["trusted_operator_identity_count"] == 0
    assert first["program_bindings"]["v2_cli"]["relative_path"].endswith(
        "google_oauth_linking_evidence_v2_cli.py"
    )
    plan = first["artifact_intake"]["post_import_argv_plan"]
    assert all("google_oauth_linking_evidence_v2_cli.py" in row for row in (" ".join(item) for item in plan))
    assert "post_import_commands" not in first

    assert module.materialize_request(args) == 0
    second = module.read_json(args.request)
    assert second["request_nonce"] == first["request_nonce"]
    assert second["generated_at_utc"] == first["generated_at_utc"]
    assert second["request_identity_reused"] is True


def test_materialize_request_fails_closed_without_live_release_capture(tmp_path: Path) -> None:
    module = load_module()
    args = request_args(module, tmp_path)
    args.live_release_manifest = None
    args.live_captured_at = None

    assert module.materialize_request(args) == 1
    payload = module.read_json(args.request)
    assert payload["status"] == "blocked_release_authority"
    assert payload["recovery"]["execution_authority_present"] is False
    assert "live_release_manifest_not_captured" in payload["release"]["blockers"]
    assert payload["artifact_intake"]["post_import_argv_plan"] == []
    assert "import_argv" not in payload["artifact_intake"]


def test_v2_zip_import_binds_real_image_bytes_and_code_provenance(tmp_path: Path) -> None:
    module = load_module()
    args = request_args(module, tmp_path)
    assert module.materialize_request(args) == 0
    request = module.read_json(args.request)
    template = module.read_json(Path(request["template_path"]))

    bundle_root = tmp_path / "bundle"
    first_image = bundle_root / "google-signed-in.png"
    second_image = bundle_root / "google-provider-linked.png"
    write_valid_png(first_image, seed=1)
    write_valid_png(second_image, seed=2)
    template["observed_at_utc"] = module.contract.isoformat_utc(datetime.now(UTC))
    template["screenshots"] = []
    for logical_name, image_path in (
        ("google-signed-in.png", first_image),
        ("google-provider-linked.png", second_image),
    ):
        claims, failures = module.contract.inspect_image(image_path)
        assert failures == []
        template["screenshots"].append(
            {"logical_name": logical_name, "path": logical_name, **claims}
        )
    template["attestation"] = {
        "contract_name": module.contract.ATTESTATION_CONTRACT_NAME,
        "algorithm": "ed25519",
        "key_id": "untrusted-test-key",
        "role": module.contract.ATTESTATION_ROLE,
        "generated_at_utc": module.contract.isoformat_utc(datetime.now(UTC)),
        "signature": base64.b64encode(b"\0" * 64).decode(),
    }
    evidence_source = bundle_root / "GOOGLE_OAUTH_LINKING_OPERATOR_EVIDENCE.generated.json"
    write_json(evidence_source, template)
    archive_path = tmp_path / "operator-evidence.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.write(evidence_source, evidence_source.name)
        archive.write(first_image, first_image.name)
        archive.write(second_image, second_image.name)

    import_args = SimpleNamespace(
        artifact=archive_path,
        request=args.request,
        evidence=None,
        imported_root=tmp_path / "imported-screenshots",
    )
    # The import is expected to remain non-green while no reviewed operator key
    # exists, but the bounded byte/provenance import must still complete.
    assert module.import_evidence(import_args) == 1
    imported = module.read_json(Path(request["required_operator_evidence_path"]))
    assert imported["import_provenance"]["importer_program"] == "v2_cli"
    assert imported["import_provenance"]["importer_program_sha256"] == request["program_bindings"]["v2_cli"]["sha256"]
    assert len(imported["screenshots"]) == 2
    assert all(Path(row["path"]).is_file() for row in imported["screenshots"])


def test_zip_traversal_is_rejected(tmp_path: Path) -> None:
    module = load_module()
    archive_path = tmp_path / "unsafe.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("../escape.json", "{}")
    with zipfile.ZipFile(archive_path) as archive:
        try:
            module.safe_zip_members(archive)
        except SystemExit as exc:
            assert "unsafe zip member path" in str(exc)
        else:
            raise AssertionError("zip traversal was accepted")

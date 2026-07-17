from __future__ import annotations

import importlib.util
import hashlib
import json
import shutil
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "verify_public_pwa_static_assets.py"


def load_module():
    spec = importlib.util.spec_from_file_location("verify_public_pwa_static_assets", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def load_generator_module():
    script = ROOT / "scripts/generate_public_play_worker_projection.py"
    spec = importlib.util.spec_from_file_location(
        "generate_public_play_worker_projection_strict_json_test",
        script,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_verifier_and_generator_reject_duplicate_json_fields() -> None:
    verifier = load_module()
    generator = load_generator_module()
    duplicate = b'{"contract":"a","contract":"b"}\n'
    with pytest.raises(RuntimeError, match="duplicate JSON field"):
        verifier.strict_json_loads(duplicate, label="duplicate verifier input")
    with pytest.raises(RuntimeError, match="duplicate JSON field"):
        generator.strict_json_object(duplicate, label="duplicate generator input")


def readiness_payload(full_deployment_digest_sha256: str) -> bytes:
    return json.dumps(
        {
            "ready": True,
            "status": "ready",
            "deploymentIdentity": {
                "ready": True,
                "code": "overlay_identity_bound",
                "sourceFingerprintSha256": "a" * 64,
                "fullDeploymentDigestSha256": full_deployment_digest_sha256,
            },
        }
    ).encode("utf-8")


def private_response_headers() -> dict[str, str]:
    return {
        "content-type": "application/json",
        "cache-control": "private, no-store, max-age=0",
        "cdn-cache-control": "no-store, max-age=0",
        "cloudflare-cdn-cache-control": "no-store, max-age=0",
        "surrogate-control": "no-store",
        "x-content-type-options": "nosniff",
    }


def test_live_identity_requires_exact_full_deployment_digest(monkeypatch) -> None:
    module = load_module()
    expected = "b" * 64
    monkeypatch.setattr(
        module,
        "fetch",
        lambda _base_url, path, _timeout: (
            200,
            private_response_headers(),
            readiness_payload(expected),
        )
        if path == "/api/ready"
        else pytest.fail(f"unexpected fetch {path}"),
    )
    failures: list[str] = []

    identity = module.verify_live_deployment_identity(
        "https://example.test",
        1.0,
        expected,
        failures,
    )

    assert failures == []
    assert identity["fullDeploymentDigestSha256"] == expected
    assert identity["matchesExpectedFullDeploymentDigest"] is True


def test_live_identity_rejects_different_full_deployment_digest(monkeypatch) -> None:
    module = load_module()
    monkeypatch.setattr(
        module,
        "fetch",
        lambda _base_url, _path, _timeout: (
            200,
            private_response_headers(),
            readiness_payload("c" * 64),
        ),
    )
    failures: list[str] = []

    identity = module.verify_live_deployment_identity(
        "https://example.test",
        1.0,
        "b" * 64,
        failures,
    )

    assert identity["matchesExpectedFullDeploymentDigest"] is False
    assert any("does not match" in failure for failure in failures)


def copy_contract_fixture(tmp_path: Path) -> Path:
    fixture = tmp_path / "workspace" / "chummer.run-services"
    source_api = ROOT / "Chummer.Run.Api"
    target_api = fixture / "Chummer.Run.Api"
    inventory = json.loads((source_api / "play-pwa-required-inventory.json").read_text(encoding="utf-8"))

    def copy_file(source: Path, target: Path) -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)

    copy_file(source_api / "play-pwa-mirrors.json", target_api / "play-pwa-mirrors.json")
    for item in inventory["assets"]:
        copy_file(source_api / item["projection"], target_api / item["projection"])
        copy_file(
            ROOT.parent / "chummer-play" / item["source"],
            fixture.parent / "chummer-play" / item["source"],
        )
    for dependency in inventory["generatorDependencies"]:
        copy_file(ROOT / dependency["path"], fixture / dependency["path"])
    copy_file(ROOT / "docker-compose.public-edge.yml", fixture / "docker-compose.public-edge.yml")
    copy_file(
        source_api / "Services/PublicPlayProxyGateway.cs",
        target_api / "Services/PublicPlayProxyGateway.cs",
    )
    return fixture


def test_current_source_satisfies_local_install_only_digest_closed_contract() -> None:
    module = load_module()

    result = module.verify_source(ROOT)

    assert result["contractName"] == "chummer.public_play_install_assets.v2"
    assert result["status"] == "pass", result["failures"]
    assert result["worker"]["cacheVersion"] == "v19"
    assert result["worker"]["cacheContract"] == "run-api-projection-v2"
    assert result["worker"]["passiveActivation"] is True
    assert result["mirror"]["contract"] == "play-install-mirror-v5"
    assert result["mirror"]["inventoryContract"] == "play-install-mirror-required-inventory-v2"
    assert result["mirror"]["policyId"] == "chummer.public-play-pwa-mirror.v1"
    assert result["mirror"]["assetPolicyCount"] == 12
    assert result["mirror"]["dependencyPolicyCount"] == 4
    assert result["mirror"]["symlinkPolicy"] == "reject_all_components"
    assert result["mirror"]["siblingPlaySourceValidated"] is True
    assert result["mirror"]["generatorReceipt"]["status"] == "pass"
    assert any(item["kind"] == "transform" for item in result["mirror"]["checked"])
    inventory = result["assetDigestInventory"]
    assert inventory["contractName"] == "chummer.public_pwa_asset_digest_inventory.v1"
    assert inventory["assetCount"] == 14
    assert len(inventory["sha256"]) == 64
    assert sum(item["mirrorBound"] is True for item in inventory["assets"]) == 12
    assert {
        item["path"]
        for item in inventory["assets"]
        if item["mirrorBound"] is False
    } == {"/js/mobile-app-handoff.js", "/manifest.webmanifest"}
    assert {item["path"] for item in inventory["assets"]} == {
        "/js/mobile-app-handoff.js",
        "/manifest.webmanifest",
        "/mobile-install-shell.js",
        "/mobile.css",
        "/manifest.play.webmanifest",
        "/manifest.player.webmanifest",
        "/manifest.gm.webmanifest",
        "/manifest.observer.webmanifest",
        "/icons/icon-192.png",
        "/icons/icon-512.png",
        "/icons/icon-192.svg",
        "/icons/icon-512.svg",
        "/service-worker.js",
        "/mobile/service-worker.js",
    }


def test_live_bound_asset_rejects_mime_and_digest_drift() -> None:
    module = load_module()
    expected_payload = b"console.log('expected');\n"
    expected = {
        "path": "/js/mobile-app-handoff.js",
        "contentType": "application/javascript",
        "sha256": hashlib.sha256(expected_payload).hexdigest(),
        "sizeBytes": len(expected_payload),
    }
    failures: list[str] = []

    module.verify_live_bound_asset(
        expected["path"],
        200,
        {"content-type": "text/javascript; charset=utf-8"},
        b"console.log('stale');\n",
        expected,
        failures,
    )

    assert any("MIME differs" in failure for failure in failures)
    assert any("digest differs" in failure for failure in failures)


def test_clean_mobile_player_shell_rejects_redirect_without_serializing_target(
    monkeypatch,
) -> None:
    module = load_module()
    markup = b'<main data-play-surface="install-only" data-live-session="unavailable" data-authority="none"></main>'
    monkeypatch.setattr(
        module,
        "fetch",
        lambda _base_url, _path, _timeout: (
            302,
            {"content-type": "text/html; charset=utf-8", "location": "https://attacker.test/?token=private"},
            b"",
        ),
    )
    failures: list[str] = []

    result = module.verify_clean_mobile_player_shell(
        "https://example.test",
        1.0,
        failures,
    )

    assert result["cleanFinalRoute"] is False
    assert result["redirectRejected"] is True
    assert "finalUrl" not in result
    assert any("redirect or non-200" in failure for failure in failures)


def test_clean_mobile_player_shell_accepts_query_free_no_authority_shell(
    monkeypatch,
) -> None:
    module = load_module()
    markup = b'<main data-play-surface="install-only" data-live-session="unavailable" data-authority="none"></main>'
    monkeypatch.setattr(
        module,
        "fetch",
        lambda _base_url, _path, _timeout: (
            200,
            {"content-type": "text/html; charset=utf-8"},
            markup,
        ),
    )
    failures: list[str] = []

    result = module.verify_clean_mobile_player_shell(
        "https://example.test",
        1.0,
        failures,
    )

    assert failures == []
    assert result["cleanFinalRoute"] is True
    assert result["authorityNone"] is True


@pytest.mark.parametrize(
    "origin",
    [
        "https://user:secret@example.test",
        "https://example.test/path",
        "https://example.test/?token=secret",
        "https://example.test/#fragment",
        "http://example.test",
        "https://example.test:8443",
    ],
)
def test_live_origin_rejects_authority_path_query_fragment_and_unsafe_transport(
    origin: str,
) -> None:
    module = load_module()

    with pytest.raises(RuntimeError, match="base origin"):
        module.validate_clean_origin(origin)


def test_redirect_handler_never_follows_redirect_targets() -> None:
    module = load_module()

    assert module.NoRedirectHandler().redirect_request(
        None,
        None,
        302,
        "Found",
        {"location": "https://attacker.test/?token=secret"},
        "https://attacker.test/?token=secret",
    ) is None


def test_bounded_http_read_rejects_declared_and_streamed_overflow() -> None:
    module = load_module()

    class Response:
        def __init__(self, body: bytes, content_length: str = "") -> None:
            self.body = body
            self.offset = 0
            self.headers = {"Content-Length": content_length}

        def read(self, size: int) -> bytes:
            chunk = self.body[self.offset:self.offset + size]
            self.offset += len(chunk)
            return chunk

    with pytest.raises(RuntimeError, match="byte limit"):
        module.read_bounded_http_body(
            Response(b"", "11"), path="/manifest.webmanifest", limit=10
        )
    with pytest.raises(RuntimeError, match="byte limit"):
        module.read_bounded_http_body(
            Response(b"x" * 11), path="/manifest.webmanifest", limit=10
        )


@pytest.mark.parametrize(
    "markup, expected",
    [
        ('<div sessionId="secret">', ["sessionid"]),
        ('{"access_token":"secret"}', ["accesstoken"]),
        ('<div data-invite-code="secret">', ["invitecode"]),
        ('<div data-device-id="secret">', ["deviceid"]),
        ('token%3Dsecret', ["token"]),
        ('authorization&#x3D;secret', ["authorization"]),
        ('{"\\u0073ession":"secret"}', ["session"]),
        ('{\\"session-id\\":\\"secret\\"}', ["sessionid"]),
        ('const current = bootstrap["sessionId"]', ["sessionid"]),
        ("const current = bootstrap[device_id]", ["deviceid"]),
        ('headers.set("Authorization", credential)', ["authorization"]),
        ('request.setRequestHeader("access-token", credential)', ["accesstoken"]),
        ('node.setAttribute("data-device-id", credential)', ["deviceid"]),
        ("const { access_token, inviteCode: localInvite } = payload", ["accesstoken", "invitecode"]),
        ('const deferredKey = "artifactAccess"', ["artifactaccess"]),
        ("element.dataset.sessionId", ["sessionid"]),
        ("<div data-token></div>", ["token"]),
    ],
)
def test_private_identity_key_detection_is_closed_across_encodings(
    markup: str,
    expected: list[str],
) -> None:
    module = load_module()

    assert module.private_identity_key_findings(markup) == expected


def test_private_identity_key_detection_allows_only_fixed_no_authority_marker() -> None:
    module = load_module()

    assert module.private_identity_key_findings('data-authority="none"') == []
    assert module.private_identity_key_findings('data-authority="session"') == [
        "authority",
        "session",
    ]


def test_private_identity_key_detection_does_not_flag_safe_prose_or_similar_keys() -> None:
    module = load_module()
    markup = """
    <main data-play-surface="install-only"
          data-live-session="unavailable"
          data-authority="none"
          data-role-authority-warning="player">
      <p>Access the companion after session setup and authorization guidance.</p>
      <button aria-label="Session setup">Open</button>
      <script>
        const copy = "Authorization guidance";
        const status = "authorized";
        const accessibility = true;
      </script>
    </main>
    """

    assert module.private_identity_key_findings(markup) == []


def test_verify_live_complete_contract_passes_with_bound_assets_and_stable_identity(
    monkeypatch,
) -> None:
    module = load_module()
    expected_deployment_digest = "b" * 64
    source_failures: list[str] = []
    source_inventory = module.source_asset_digest_inventory(ROOT, source_failures)
    assert source_failures == []
    expected_assets = {
        item["path"]: item
        for item in source_inventory["assets"]
    }
    call_counts: dict[str, int] = {}

    def role_document(path: str) -> bytes:
        role, manifest, title, purpose, capability, target = module.ROLE_DOCUMENTS[path]
        return f"""
        <!doctype html>
        <html>
          <head><link rel="manifest" href="{manifest}"></head>
          <body>
            <main data-play-surface="install-only"
                  data-install-role="{role}"
                  data-live-session="unavailable"
                  data-authority="none">
              <h1>{title}</h1>
              <p>{purpose}</p>
              <p>{capability}</p>
              <a href="{target}">Open role</a>
              <div data-mobile-app-inline-qr></div>
              <p data-role-privacy-warning="{role}">Private table data stays gated.</p>
              <p data-role-authority-warning="{role}">No live authority is granted.</p>
            </main>
          </body>
        </html>
        """.encode("utf-8")

    document_headers = {
        **private_response_headers(),
        "content-type": "text/html; charset=utf-8",
        "content-security-policy": "default-src 'none'; connect-src 'none'",
        "referrer-policy": "no-referrer",
    }

    def fake_fetch(_base_url: str, path: str, _timeout: float):
        call_counts[path] = call_counts.get(path, 0) + 1
        if path == "/api/ready":
            return (
                200,
                private_response_headers(),
                readiness_payload(expected_deployment_digest),
            )
        if path in module.ROLE_DOCUMENTS:
            return 200, document_headers, role_document(path)
        if path in module.LOCAL_ASSETS:
            expected = expected_assets[path]
            payload = (
                ROOT
                / "Chummer.Run.Api"
                / "wwwroot"
                / path.lstrip("/")
            ).read_bytes()
            return (
                200,
                {
                    "content-type": expected["contentType"],
                    "cache-control": expected["cacheControl"],
                    "x-content-type-options": "nosniff",
                },
                payload,
            )
        pytest.fail(f"unexpected fetch {path}")

    monkeypatch.setattr(module, "fetch", fake_fetch)

    result = module.verify_live(
        "https://example.test",
        1.0,
        expected_deployment_digest,
        source_inventory["sha256"],
    )

    assert result["status"] == "pass", result["failures"]
    assert result["failures"] == []
    assert len(result["manifests"]) == len(module.MANIFESTS)
    assert len(result["assets"]) == len(module.LOCAL_ASSETS)
    assert len(result["documents"]) == len(module.ROLE_DOCUMENTS)
    assert result["assetDigestInventory"]["matchesExpected"] is True
    assert result["assetDigestInventory"]["sourceStable"] is True
    assert result["deploymentIdentity"]["stable"] is True
    assert result["cleanMobilePlayerShell"]["privateIdentityAbsent"] is True
    assert all(document["privateIdentityKeysAbsent"] for document in result["documents"])
    assert call_counts["/api/ready"] == 2
    assert call_counts["/mobile/player"] == 2
    assert call_counts["/service-worker.js"] == 2


def test_live_asset_cannot_match_without_inventory_binding() -> None:
    module = load_module()
    payload = b"body{}"
    failures: list[str] = []

    row = module.verify_live_bound_asset(
        "/mobile.css",
        200,
        {
            "content-type": "text/css",
            "cache-control": "public, max-age=300, must-revalidate",
            "x-content-type-options": "nosniff",
        },
        payload,
        {
            "contentType": "text/css",
            "cacheControl": "public, max-age=300, must-revalidate",
            "sha256": hashlib.sha256(payload).hexdigest(),
            "sizeBytes": len(payload),
        },
        failures,
    )

    assert row["matchesExpected"] is False


def test_deployment_identity_change_is_rejected() -> None:
    module = load_module()
    before = {
        "sourceFingerprintSha256": "a" * 64,
        "fullDeploymentDigestSha256": "b" * 64,
        "code": "overlay_identity_bound",
        "ready": True,
    }

    assert module.deployment_identity_is_stable(before, dict(before)) is True
    assert module.deployment_identity_is_stable(
        before,
        {**before, "sourceFingerprintSha256": "c" * 64},
    ) is False


def test_trusted_generator_descriptor_requires_full_seals_and_exact_digest() -> None:
    module = load_module()
    if not hasattr(module.os, "memfd_create") or module.fcntl is None:
        pytest.skip("sealed memfd support is unavailable")
    payload = b"print('trusted generator')\n"
    digest = hashlib.sha256(payload).hexdigest()
    descriptor = module.os.memfd_create(
        "trusted-generator-test",
        flags=getattr(module.os, "MFD_ALLOW_SEALING", 0x0002),
    )
    try:
        module.os.write(descriptor, payload)
        with pytest.raises(RuntimeError, match="not fully sealed"):
            module.read_sealed_inherited_payload(
                descriptor,
                digest,
                label="trusted generator",
                max_bytes=1024,
            )

        required_seals = (
            module.fcntl.F_SEAL_SEAL
            | module.fcntl.F_SEAL_SHRINK
            | module.fcntl.F_SEAL_GROW
            | module.fcntl.F_SEAL_WRITE
        )
        module.fcntl.fcntl(descriptor, module.fcntl.F_ADD_SEALS, required_seals)
        assert module.read_sealed_inherited_payload(
            descriptor,
            digest,
            label="trusted generator",
            max_bytes=1024,
        ) == payload
        with pytest.raises(RuntimeError, match="digest"):
            module.read_sealed_inherited_payload(
                descriptor,
                "0" * 64,
                label="trusted generator",
                max_bytes=1024,
            )
    finally:
        module.os.close(descriptor)


def test_manifest_rejects_query_bearing_role_launch_and_incomplete_icons() -> None:
    module = load_module()
    failures: list[str] = []
    payload = json.loads((ROOT / "Chummer.Run.Api/wwwroot/manifest.gm.webmanifest").read_text(encoding="utf-8"))
    payload["start_url"] = "/mobile/gm?role=GameMaster"
    payload["icons"] = [{"src": "/icons/icon-192.png"}]

    module.verify_manifest(
        "/manifest.gm.webmanifest",
        json.dumps(payload).encode("utf-8"),
        failures,
    )

    assert any("wrong start_url" in failure for failure in failures)
    assert any("query-free" in failure for failure in failures)
    assert any("complete local icon set" in failure for failure in failures)


def test_worker_rejects_forced_activation_and_private_companion_caching() -> None:
    module = load_module()
    failures: list[str] = []
    worker = (ROOT / "Chummer.Run.Api/wwwroot/service-worker.js").read_text(encoding="utf-8")
    drifted = worker.replace(
        "event.waitUntil(precacheCriticalShell());",
        "event.waitUntil(precacheCriticalShell().then(() => self.skipWaiting()));",
    ).replace(
        '["/mobile-install-shell.js",',
        '["/mobile-turn-companion.js", new Set(["application/javascript"])] ,\n  ["/mobile-install-shell.js",',
        1,
    )

    module.verify_worker(drifted.encode("utf-8"), failures)

    assert any("skipWaiting" in failure for failure in failures)
    assert any("private companion script" in failure for failure in failures)


def test_mirror_closure_rejects_projection_byte_drift(tmp_path: Path) -> None:
    module = load_module()
    fixture = copy_contract_fixture(tmp_path)
    projection = fixture / "Chummer.Run.Api/wwwroot/mobile-install-shell.js"
    projection.write_text(projection.read_text(encoding="utf-8") + "\n// drift\n", encoding="utf-8")
    failures: list[str] = []

    module.verify_mirror_closure(fixture, failures)

    assert any("byte drift" in failure for failure in failures)
    assert any("digest drift" in failure for failure in failures)


def mutate_mirror_contract(fixture: Path, mutator) -> list[str]:
    contract_path = fixture / "Chummer.Run.Api/play-pwa-mirrors.json"
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    mutator(contract)
    contract_path.write_text(json.dumps(contract, indent=2) + "\n", encoding="utf-8")
    failures: list[str] = []
    load_module().verify_mirror_closure(fixture, failures)
    return failures


def test_mirror_closure_rejects_deleted_required_asset_row(tmp_path: Path) -> None:
    fixture = copy_contract_fixture(tmp_path)

    failures = mutate_mirror_contract(fixture, lambda contract: contract["assets"].pop())

    assert any("missing required exact asset rows" in failure for failure in failures)
    assert any("row count" in failure for failure in failures)


def test_mirror_closure_rejects_duplicate_asset_row(tmp_path: Path) -> None:
    fixture = copy_contract_fixture(tmp_path)

    failures = mutate_mirror_contract(
        fixture,
        lambda contract: contract["assets"].append(dict(contract["assets"][0])),
    )

    assert any("duplicate exact asset rows" in failure for failure in failures)
    assert any("row count" in failure for failure in failures)


def test_mirror_closure_rejects_extra_undeclared_asset_row(tmp_path: Path) -> None:
    fixture = copy_contract_fixture(tmp_path)

    def add_extra(contract) -> None:
        extra = dict(contract["assets"][0])
        extra.update(
            {
                "source": "src/Chummer.Play.Web/wwwroot/undeclared.js",
                "projection": "wwwroot/undeclared.js",
                "role": "undeclared_asset",
            }
        )
        contract["assets"].append(extra)

    failures = mutate_mirror_contract(fixture, add_extra)

    assert any("extra undeclared exact asset rows" in failure for failure in failures)
    assert any("row count" in failure for failure in failures)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("contentType", "text/plain"),
        ("role", "wrong_role"),
        ("kind", "transform"),
    ],
)
def test_mirror_closure_rejects_required_asset_metadata_drift(
    tmp_path: Path,
    field: str,
    value: str,
) -> None:
    fixture = copy_contract_fixture(tmp_path)

    failures = mutate_mirror_contract(
        fixture,
        lambda contract: contract["assets"][0].__setitem__(field, value),
    )

    assert any(f"{field} drifted from required inventory" in failure for failure in failures)


@pytest.mark.parametrize("mutation", ["delete", "duplicate", "extra", "drift"])
def test_mirror_closure_rejects_generator_dependency_world_drift(
    tmp_path: Path,
    mutation: str,
) -> None:
    fixture = copy_contract_fixture(tmp_path)

    def mutate(contract) -> None:
        dependencies = contract["generator"]["dependencies"]
        if mutation == "delete":
            dependencies.pop()
        elif mutation == "duplicate":
            dependencies.append(dict(dependencies[0]))
        elif mutation == "extra":
            dependencies.append(
                {
                    "path": "scripts/undeclared.py",
                    "kind": "python",
                    "role": "undeclared_dependency",
                    "contentType": "text/x-python",
                    "sha256": "0" * 64,
                }
            )
        else:
            dependencies[0]["contentType"] = "text/plain"

    failures = mutate_mirror_contract(fixture, mutate)

    assert any("generator dependenc" in failure for failure in failures)


@pytest.mark.parametrize("mutation", ["delete", "replace", "extra", "metadata"])
def test_versioned_inventory_policy_rejects_coordinated_self_authorization(
    tmp_path: Path,
    mutation: str,
) -> None:
    fixture = copy_contract_fixture(tmp_path)
    inventory_path = fixture / "Chummer.Run.Api/play-pwa-required-inventory.json"
    config_path = fixture / "Chummer.Run.Api/play-worker-projection.json"
    mirror_path = fixture / "Chummer.Run.Api/play-pwa-mirrors.json"
    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    if mutation == "delete":
        inventory["assets"].pop(0)
    elif mutation == "replace":
        inventory["assets"][0]["source"] = "src/Chummer.Play.Web/wwwroot/replacement.js"
        inventory["assets"][0]["projection"] = "wwwroot/replacement.js"
    elif mutation == "extra":
        extra = dict(inventory["assets"][0])
        extra.update({"source": "src/Chummer.Play.Web/wwwroot/extra.js", "projection": "wwwroot/extra.js", "role": "extra"})
        inventory["assets"].append(extra)
    else:
        inventory["assets"][0]["cacheControl"] = "public, max-age=31536000"
    inventory_path.write_text(json.dumps(inventory, indent=2) + "\n", encoding="utf-8")
    inventory_digest = hashlib.sha256(inventory_path.read_bytes()).hexdigest()
    config = json.loads(config_path.read_text(encoding="utf-8"))
    config["requiredInventorySha256"] = inventory_digest
    config_path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    mirror = json.loads(mirror_path.read_text(encoding="utf-8"))
    mirror["inventorySha256"] = inventory_digest
    mirror["generator"]["inventorySha256"] = inventory_digest
    for dependency in mirror["generator"]["dependencies"]:
        if dependency["role"] == "required_inventory":
            dependency["sha256"] = inventory_digest
        elif dependency["role"] == "projection_config":
            dependency["sha256"] = hashlib.sha256(config_path.read_bytes()).hexdigest()
    mirror["generator"]["configSha256"] = hashlib.sha256(config_path.read_bytes()).hexdigest()
    mirror_path.write_text(json.dumps(mirror, indent=2) + "\n", encoding="utf-8")
    failures: list[str] = []

    load_module().verify_mirror_closure(fixture, failures)

    assert any("must exactly match chummer.public-play-pwa-mirror.v1" in failure for failure in failures)


def test_mirror_closure_rejects_projection_file_symlink(tmp_path: Path) -> None:
    fixture = copy_contract_fixture(tmp_path)
    projection = fixture / "Chummer.Run.Api/wwwroot/mobile.css"
    projection.unlink()
    projection.symlink_to(
        fixture.parent / "chummer-play/src/Chummer.Play.Web/wwwroot/mobile.css"
    )
    failures: list[str] = []

    load_module().verify_mirror_closure(fixture, failures)

    assert any("symlink" in failure and "projection asset" in failure for failure in failures)


def test_mirror_closure_rejects_source_directory_component_symlink(tmp_path: Path) -> None:
    fixture = copy_contract_fixture(tmp_path)
    icons = fixture.parent / "chummer-play/src/Chummer.Play.Web/wwwroot/icons"
    real_icons = icons.with_name("icons-real")
    icons.rename(real_icons)
    icons.symlink_to(real_icons, target_is_directory=True)
    failures: list[str] = []

    load_module().verify_mirror_closure(fixture, failures)

    assert any("symlink" in failure and "source asset" in failure for failure in failures)


def test_mirror_closure_rejects_generator_dependency_symlink(tmp_path: Path) -> None:
    fixture = copy_contract_fixture(tmp_path)
    template = fixture / "Chummer.Run.Api/service-worker.public-edge.template.js"
    real_template = template.with_suffix(".real.js")
    template.rename(real_template)
    template.symlink_to(real_template)
    failures: list[str] = []

    load_module().verify_mirror_closure(fixture, failures)

    assert any("symlink" in failure and "projection_template" in failure for failure in failures)


def test_source_contract_rejects_overrideable_proxy_flags_or_portal_dependency(tmp_path: Path) -> None:
    module = load_module()
    fixture = copy_contract_fixture(tmp_path)
    compose = (ROOT / "docker-compose.public-edge.yml").read_text(encoding="utf-8")
    compose = compose.replace(
        'CHUMMER_PUBLIC_PLAY_PROXY_ENABLED: "false"',
        'CHUMMER_PUBLIC_PLAY_PROXY_ENABLED: "${CHUMMER_PUBLIC_PLAY_PROXY_ENABLED:-false}"',
    ).replace(
        'CHUMMER_PUBLIC_PLAY_LIVE_SESSION_PROXY_ENABLED: "false"',
        'CHUMMER_PUBLIC_PLAY_LIVE_SESSION_PROXY_ENABLED: "${CHUMMER_PUBLIC_PLAY_LIVE_SESSION_PROXY_ENABLED:-false}"',
    ).replace(
        "      chummer-public-blazor:\n        condition: service_healthy",
        "      chummer-play-web:\n        condition: service_healthy\n"
        "      chummer-public-blazor:\n        condition: service_healthy",
    )
    (fixture / "docker-compose.public-edge.yml").write_text(compose, encoding="utf-8")

    result = module.verify_source(fixture)

    assert result["status"] == "fail"
    assert any("CHUMMER_PUBLIC_PLAY_PROXY_ENABLED must be exactly" in failure for failure in result["failures"])
    assert any("CHUMMER_PUBLIC_PLAY_LIVE_SESSION_PROXY_ENABLED must be exactly" in failure for failure in result["failures"])
    assert any("CHUMMER_PUBLIC_PLAY_PROXY_ENABLED must not use interpolation" in failure for failure in result["failures"])
    assert any("CHUMMER_PUBLIC_PLAY_LIVE_SESSION_PROXY_ENABLED must not use interpolation" in failure for failure in result["failures"])
    assert any("must not depend" in failure for failure in result["failures"])


@pytest.mark.parametrize(
    "name",
    (
        "CHUMMER_PUBLIC_PLAY_PROXY_ENABLED",
        "CHUMMER_PUBLIC_PLAY_LIVE_SESSION_PROXY_ENABLED",
    ),
)
def test_source_contract_rejects_duplicate_proxy_declarations(
    tmp_path: Path,
    name: str,
) -> None:
    module = load_module()
    fixture = copy_contract_fixture(tmp_path)
    compose = (ROOT / "docker-compose.public-edge.yml").read_text(encoding="utf-8")
    compose = compose.replace(
        f'{name}: "false"',
        f'{name}: "false"\n      {name}: "true"',
    )
    (fixture / "docker-compose.public-edge.yml").write_text(compose, encoding="utf-8")

    result = module.verify_source(fixture)

    assert result["status"] == "fail"
    assert any("portal environment keys must be unique" in item for item in result["failures"])
    assert any(f"{name} must occur exactly once" in item for item in result["failures"])


def test_source_contract_rejects_explicit_key_with_decoy_false_marker(tmp_path: Path) -> None:
    module = load_module()
    fixture = copy_contract_fixture(tmp_path)
    compose_path = fixture / "docker-compose.public-edge.yml"
    compose = compose_path.read_text(encoding="utf-8").replace(
        '      CHUMMER_PUBLIC_PLAY_PROXY_ENABLED: "false"',
        "      ? CHUMMER_PUBLIC_PLAY_PROXY_ENABLED\n"
        '      : "true"\n'
        '      # CHUMMER_PUBLIC_PLAY_PROXY_ENABLED: "false"',
    )
    compose_path.write_text(compose, encoding="utf-8")

    result = module.verify_source(fixture)

    assert result["status"] == "fail"
    assert any("explicit YAML mapping keys are forbidden" in item for item in result["failures"])
    assert any("CHUMMER_PUBLIC_PLAY_PROXY_ENABLED must be exactly" in item for item in result["failures"])


@pytest.mark.parametrize(
    ("replacement", "expected_failure"),
    (
        ('      CHUMMER_PUBLIC_PLAY_PROXY_ENABLED: &proxy-disabled "false"', "anchors and aliases are forbidden"),
        ('      CHUMMER_PUBLIC_PLAY_PROXY_ENABLED: *proxy-disabled', "anchors and aliases are forbidden"),
        ('      CHUMMER_PUBLIC_PLAY_PROXY_ENABLED: !str "false"', "YAML tags are forbidden"),
        ('      CHUMMER_PUBLIC_PLAY_PROXY_ENABLED: {value: "false"}', "flow mappings are forbidden"),
        (
            '      CHUMMER_PUBLIC_PLAY_PROXY_ENABLED: "${CHUMMER_PUBLIC_PLAY_PROXY_ENABLED:-false}"',
            "must not use interpolation",
        ),
    ),
)
def test_source_contract_rejects_ambiguous_protected_proxy_yaml(
    tmp_path: Path,
    replacement: str,
    expected_failure: str,
) -> None:
    module = load_module()
    fixture = copy_contract_fixture(tmp_path)
    compose_path = fixture / "docker-compose.public-edge.yml"
    compose = compose_path.read_text(encoding="utf-8").replace(
        '      CHUMMER_PUBLIC_PLAY_PROXY_ENABLED: "false"',
        replacement,
    )
    compose_path.write_text(compose, encoding="utf-8")

    result = module.verify_source(fixture)

    assert result["status"] == "fail"
    assert any(expected_failure in item for item in result["failures"])


def test_source_contract_rejects_environment_merge_key(tmp_path: Path) -> None:
    module = load_module()
    fixture = copy_contract_fixture(tmp_path)
    compose_path = fixture / "docker-compose.public-edge.yml"
    compose = compose_path.read_text(encoding="utf-8").replace(
        '      CHUMMER_PUBLIC_PLAY_PROXY_ENABLED: "false"',
        '      <<: *portal-environment\n      CHUMMER_PUBLIC_PLAY_PROXY_ENABLED: "false"',
    )
    compose_path.write_text(compose, encoding="utf-8")

    result = module.verify_source(fixture)

    assert result["status"] == "fail"
    assert any("YAML merge keys are forbidden" in item for item in result["failures"])


def test_yaml_comment_scanner_preserves_hash_inside_doubled_single_quote() -> None:
    module = load_module()

    assert module._yaml_code_without_comment(
        "      SAFE_VALUE: 'it''s # data' # comment"
    ) == "      SAFE_VALUE: 'it''s # data'"


def test_worker_generator_rejects_undeclared_source_drift(tmp_path: Path) -> None:
    fixture = copy_contract_fixture(tmp_path)
    generator_path = fixture / "scripts/generate_public_play_worker_projection.py"
    spec = importlib.util.spec_from_file_location("fixture_worker_generator", generator_path)
    assert spec is not None and spec.loader is not None
    generator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(generator)
    source = fixture.parent / "chummer-play/src/Chummer.Play.Web/wwwroot/service-worker.js"
    source.write_text(source.read_text(encoding="utf-8") + "\n// undeclared drift\n", encoding="utf-8")

    with pytest.raises(RuntimeError, match="source worker digest drifted"):
        generator.render_projection(
            fixture,
            fixture / "Chummer.Run.Api/play-worker-projection.json",
        )


def test_worker_generator_rejects_redeclared_forbidden_template_semantics(tmp_path: Path) -> None:
    fixture = copy_contract_fixture(tmp_path)
    generator_path = fixture / "scripts/generate_public_play_worker_projection.py"
    spec = importlib.util.spec_from_file_location("fixture_worker_generator_forbidden", generator_path)
    assert spec is not None and spec.loader is not None
    generator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(generator)
    config_path = fixture / "Chummer.Run.Api/play-worker-projection.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    template = fixture / config["template"]
    template.write_text(template.read_text(encoding="utf-8") + "\nself.skipWaiting();\n", encoding="utf-8")
    config["templateSha256"] = hashlib.sha256(template.read_bytes()).hexdigest()
    config_path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")

    with pytest.raises(RuntimeError, match="projected worker semantic contract failed"):
        generator.render_projection(fixture, config_path)


def test_worker_generator_independently_rejects_coordinated_inventory_policy_drift(tmp_path: Path) -> None:
    fixture = copy_contract_fixture(tmp_path)
    generator_path = fixture / "scripts/generate_public_play_worker_projection.py"
    spec = importlib.util.spec_from_file_location("fixture_worker_generator_policy", generator_path)
    assert spec is not None and spec.loader is not None
    generator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(generator)
    inventory_path = fixture / "Chummer.Run.Api/play-pwa-required-inventory.json"
    config_path = fixture / "Chummer.Run.Api/play-worker-projection.json"
    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    inventory["assets"].pop(0)
    inventory_path.write_text(json.dumps(inventory, indent=2) + "\n", encoding="utf-8")
    config = json.loads(config_path.read_text(encoding="utf-8"))
    config["requiredInventorySha256"] = hashlib.sha256(inventory_path.read_bytes()).hexdigest()
    config_path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")

    with pytest.raises(RuntimeError, match="must exactly match policy chummer.public-play-pwa-mirror.v1"):
        generator.render_projection(fixture, config_path)


def test_worker_generator_rejects_symlinked_policy_component(tmp_path: Path) -> None:
    fixture = copy_contract_fixture(tmp_path)
    generator_path = fixture / "scripts/generate_public_play_worker_projection.py"
    spec = importlib.util.spec_from_file_location("fixture_worker_generator_symlink", generator_path)
    assert spec is not None and spec.loader is not None
    generator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(generator)
    inventory_path = fixture / "Chummer.Run.Api/play-pwa-required-inventory.json"
    real_inventory = inventory_path.with_suffix(".real.json")
    inventory_path.rename(real_inventory)
    inventory_path.symlink_to(real_inventory)

    with pytest.raises(RuntimeError, match="symlink"):
        generator.render_projection(
            fixture,
            fixture / "Chummer.Run.Api/play-worker-projection.json",
        )

import json
import os
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]
COMPOSE = (ROOT / "docker-compose.build-ghost-private-nonprod.yml").read_text(encoding="utf-8")
CADDY = (ROOT / "ops/build-ghost-private-nonprod/Caddyfile").read_text(encoding="utf-8")
CANARY = (ROOT / "ops/build-ghost-private-nonprod/run-local-canary.sh").read_text(encoding="utf-8")
SENTINEL = ROOT / "ops/build-ghost-private-nonprod/tough-tongue-read-only-binding-contract.unconfigured.json"


def service_block(name: str, next_name: str) -> str:
    return COMPOSE.split(f"\n  {name}:\n", 1)[1].split(f"\n  {next_name}:\n", 1)[0]


def test_private_lane_is_loopback_only_and_remote_execution_is_fail_closed():
    assert '127.0.0.1:${CHUMMER_BUILD_GHOST_PRIVATE_HTTPS_PORT:-8443}:443' in COMPOSE
    assert 'CHUMMER_BUILD_GHOST_TOUGH_TONGUE_REMOTE_EXECUTION_ENABLED: "false"' in COMPOSE
    assert 'CHUMMER_BUILD_GHOST_TOUGH_TONGUE_PRIVATE_CANARY_MUTATIONS_ENABLED: "false"' in COMPOSE
    assert 'CHUMMER_BUILD_GHOST_TOUGH_TONGUE_CANARY_READ_ONLY_ENABLED: "false"' in COMPOSE
    assert 'CHUMMER_BUILD_GHOST_TOUGH_TONGUE_CANARY_ACCESS_GRANT_ENABLED: "false"' in COMPOSE
    assert 'CHUMMER_BUILD_GHOST_PRIVATE_TOOL_TRANSPORT_MODE: provider-body-key-v2' in COMPOSE
    assert "network_mode: host" not in COMPOSE
    presentation = service_block("chummer-build-ghost-presentation", "chummer-build-ghost-ai")
    ai = service_block("chummer-build-ghost-ai", "build-ghost-private-edge")
    edge = COMPOSE.split("\n  build-ghost-private-edge:\n", 1)[1].split("\nvolumes:\n", 1)[0]
    assert "build-ghost-loopback" not in presentation
    assert "build-ghost-loopback" not in ai
    assert "build-ghost-loopback: {}" in edge


def test_governed_provider_slots_are_runtime_only_and_cannot_enable_remote_execution():
    ai = service_block("chummer-build-ghost-ai", "build-ghost-private-edge")
    assert "CHUMMER_BUILD_GHOST_TOUGH_TONGUE_API_KEYS: ${CHUMMER_BUILD_GHOST_TOUGH_TONGUE_API_KEYS:-}" in ai
    assert "CHUMMER_BUILD_GHOST_TOUGH_TONGUE_ACCOUNT_REFS: ${CHUMMER_BUILD_GHOST_TOUGH_TONGUE_ACCOUNT_REFS:-}" in ai
    assert "CHUMMER_BUILD_GHOST_TOUGH_TONGUE_PREFERRED_ACCOUNT_REF: ${CHUMMER_BUILD_GHOST_TOUGH_TONGUE_PREFERRED_ACCOUNT_REF:-}" in ai
    assert "CHUMMER_BUILD_GHOST_TOUGH_TONGUE_AGENT_ID: ${CHUMMER_BUILD_GHOST_TOUGH_TONGUE_AGENT_ID:-}" in ai
    assert "CHUMMER_BUILD_GHOST_TOUGH_TONGUE_VOICE_ID: ${CHUMMER_BUILD_GHOST_TOUGH_TONGUE_VOICE_ID:-}" in ai
    assert "CHUMMER_BUILD_GHOST_TOUGH_TONGUE_FUNCTION_ID: ${CHUMMER_BUILD_GHOST_TOUGH_TONGUE_FUNCTION_ID:-}" in ai
    assert "CHUMMER_BUILD_GHOST_TOUGH_TONGUE_SCENARIO_ID: ${CHUMMER_BUILD_GHOST_TOUGH_TONGUE_SCENARIO_ID:-}" in ai
    assert "CHUMMER_BUILD_GHOST_TOUGH_TONGUE_LIVE_AVATAR_ID: ${CHUMMER_BUILD_GHOST_TOUGH_TONGUE_LIVE_AVATAR_ID:-}" in ai
    assert "EA_TOUGH_TONGUE_READ_ONLY_BINDING_CONTRACT_DIGEST: ${EA_TOUGH_TONGUE_READ_ONLY_BINDING_CONTRACT_DIGEST:-}" in ai
    assert 'CHUMMER_BUILD_GHOST_TOUGH_TONGUE_REMOTE_EXECUTION_ENABLED: "false"' in ai
    assert "toughtongue@" not in COMPOSE
    assert "PREFERRED_ACCOUNT_REF: sha256:" not in ai


def test_default_unconfigured_contract_renders_every_service_fail_closed_without_provider_io():
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
    environment["CHUMMER_BUILD_GHOST_PRIVATE_TOOL_SERVICE_TOKEN"] = "test-tool-token-" + "a" * 32
    environment["CHUMMER_AI_INTERNAL_API_TOKEN"] = "test-ai-token-" + "b" * 32
    for name in tuple(environment):
        if name.startswith("CHUMMER_BUILD_GHOST_TOUGH_TONGUE_") or name == "EA_TOUGH_TONGUE_READ_ONLY_BINDING_CONTRACT_DIGEST":
            environment.pop(name, None)

    result = subprocess.run(
        [
            "docker", "compose", "--project-directory", str(ROOT),
            "--file", str(ROOT / "docker-compose.build-ghost-private-nonprod.yml"),
            "config", "--format", "json",
        ],
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )

    assert result.returncode == 0, result.stderr
    rendered = json.loads(result.stdout)
    assert set(rendered["services"]) == {
        "chummer-build-ghost-presentation",
        "chummer-build-ghost-ai",
        "build-ghost-private-edge",
        "build-ghost-private-trust-export",
    }
    ai = rendered["services"]["chummer-build-ghost-ai"]
    for gate in (
        "CHUMMER_BUILD_GHOST_TOUGH_TONGUE_REMOTE_EXECUTION_ENABLED",
        "CHUMMER_BUILD_GHOST_TOUGH_TONGUE_PRIVATE_CANARY_MUTATIONS_ENABLED",
        "CHUMMER_BUILD_GHOST_TOUGH_TONGUE_CANARY_READ_ONLY_ENABLED",
        "CHUMMER_BUILD_GHOST_TOUGH_TONGUE_CANARY_ACCESS_GRANT_ENABLED",
    ):
        assert ai["environment"][gate] == "false"
    assert ai["environment"]["EA_TOUGH_TONGUE_READ_ONLY_BINDING_CONTRACT_DIGEST"] == ""
    assert ai["environment"]["EA_TOUGH_TONGUE_READ_ONLY_BINDING_CONTRACT_PATH"] == (
        "/run/secrets/tough-tongue-read-only-binding-contract.json"
    )
    secret = rendered["secrets"]["build-ghost-tough-tongue-read-only-binding-contract"]
    assert Path(secret["file"]).resolve() == SENTINEL.resolve()
    assert json.loads(SENTINEL.read_text(encoding="utf-8")) == {
        "schema": "chummer.build_ghost.tough_tongue.read_only_binding_contract.unconfigured.v2",
        "status": "blocked",
    }


def test_runtime_secret_is_required_but_never_defaulted_or_committed():
    required = "${CHUMMER_BUILD_GHOST_PRIVATE_TOOL_SERVICE_TOKEN:?"
    assert COMPOSE.count(required) == 2
    assert "internal-service-token" not in COMPOSE
    assert "packet_access_key:" not in COMPOSE
    assert "sha256:af7b643855bbc2220be40bfadc8cb1e89ecdc324a787c771a353d74e85f01104" in COMPOSE
    assert "sha256:af7b643855bbc2220be40bfadc8cb1e89ecdc324a787c771a353d74e85f01104" in CANARY


def test_packet_store_is_absolute_private_and_presentation_owned():
    assert "CHUMMER_BUILD_GHOST_PACKET_ACCESS_STORE_ROOT: /app/state/build-ghost-packet-access" in COMPOSE
    presentation = service_block("chummer-build-ghost-presentation", "chummer-build-ghost-ai")
    ai = service_block("chummer-build-ghost-ai", "build-ghost-private-edge")
    assert "build-ghost-packet-access:/app/state" in presentation
    assert "build-ghost-packet-access" not in ai


def test_presentation_build_recipe_is_hub_owned_and_source_labeled():
    presentation = service_block("chummer-build-ghost-presentation", "chummer-build-ghost-ai")
    assert "context: ." in presentation
    assert "dockerfile: ops/build-ghost-private-nonprod/Dockerfile.presentation-private-nonprod" in presentation
    for revision in (
        "CHUMMER_RUN_SERVICES_REVISION",
        "CHUMMER_PRESENTATION_REVISION",
        "CHUMMER_CORE_ENGINE_REVISION",
        "CHUMMER_HUB_REGISTRY_REVISION",
        "CHUMMER_UI_KIT_REVISION",
        "CHUMMER_MEDIA_FACTORY_REVISION",
    ):
        assert revision in presentation


def test_ai_image_uses_explicit_core_and_registry_source_contexts():
    ai = service_block("chummer-build-ghost-ai", "build-ghost-private-edge")
    assert "core-engine-source: ${CHUMMER_CORE_ENGINE_SOURCE:?" in ai
    assert "hub-registry-source: ${CHUMMER_HUB_REGISTRY_SOURCE:?" in ai


def test_internal_tls_routes_only_the_bounded_surfaces():
    assert "https://canary.chummer.run" in CADDY
    assert "method POST\n\t\tpath /api/v1/ai/build-ghost/tool" in CADDY
    assert "method POST\n\t\tpath /api/v2/ai/build-ghost/tool" in CADDY
    assert "reverse_proxy chummer-build-ghost-ai:8080" in CADDY
    assert "method POST\n\t\tpath /api/workspaces/import" in CADDY
    assert "^/api/workspaces/[^/]+/build-ghost/tool-access$" in CADDY
    assert "method GET DELETE" in CADDY
    assert "^/api/workspaces/[^/]+$" in CADDY
    assert "https://presentation.canary.chummer.run" in CADDY
    assert "method POST\n\t\tpath /api/internal/build-ghost/tool/resolve" in CADDY
    assert "reverse_proxy chummer-build-ghost-presentation:8080" in CADDY
    assert CADDY.count('header Cache-Control "no-store"') == 4
    assert CADDY.count("handle {\n\t\trespond 404\n\t}") == 2
    assert "/api/v1/ai/build-ghost/explain" not in CADDY
    assert "/api/v1/ai/*" not in CADDY
    assert "handle /api/workspaces/*" not in CADDY
    presentation_host = CADDY.split("https://presentation.canary.chummer.run", 1)[1]
    assert "\n\treverse_proxy" not in presentation_host


def test_ai_trusts_only_the_runtime_local_caddy_root():
    ai = service_block("chummer-build-ghost-ai", "build-ghost-private-edge")
    exporter = COMPOSE.split("\n  build-ghost-private-trust-export:\n", 1)[1].split("\nvolumes:\n", 1)[0]
    assert "caddy-data:" not in ai
    assert "caddy-trust:/caddy-trust:ro" in ai
    assert "SSL_CERT_FILE: /caddy-trust/root.crt" in ai
    assert "network_mode: none" in exporter
    assert "caddy-data:/caddy-data:ro" in exporter
    assert "caddy-trust:/caddy-trust" in exporter
    assert "root.key" not in exporter


def test_local_canary_is_single_use_private_and_self_cleaning():
    assert "synthetic-build-ghost-canary" in CANARY
    assert 'replay_status' in CANARY
    assert 'revoked_status' in CANARY
    assert 'revoked_cache_control' in CANARY
    assert 'terminal_equivalent="true"' in CANARY
    assert 'cmp --silent "$canary_tmp/replay-response.json" "$canary_tmp/revoked-response.json"' in CANARY
    assert 'state-authority.v2.json' in CANARY
    assert (
        'find /app/state/build-ghost-packet-access/pending -maxdepth 1 '
        '-type f -name "*.json"' in CANARY
    )
    assert (
        'find /app/state/build-ghost-packet-access/claims -maxdepth 1 '
        '-type f -name "*.json"' in CANARY
    )
    assert 'find /app/state/build-ghost-packet-access -type f' not in CANARY
    assert 'audit_records' in CANARY
    assert 'revocation_markers' in CANARY
    assert '"410"' in CANARY
    assert 'workspace_closed="true"' in CANARY
    assert 'closed_status' in CANARY
    assert '"404"' in CANARY
    assert 'unknown_key_status' in CANARY
    assert 'wrong_contract_status' in CANARY
    assert 'unknown_field_status' in CANARY
    assert 'provider_unknown_key_status' in CANARY
    assert 'provider_ambiguous_auth_status' in CANARY
    assert 'provider_noncanonical_key_status' in CANARY
    assert '"https://canary.chummer.run:${loopback_port}/api/v2/ai/build-ghost/tool"' in CANARY
    assert 'auth=packet-access-key-body-v2' in CANARY
    assert 'neighbor_status' in CANARY
    assert 'presentation_neighbor_status' in CANARY
    assert '"$neighbor_status" != "404"' in CANARY
    assert '"$presentation_neighbor_status" != "404"' in CANARY
    assert '"$cross_owner_status" != "503"' in CANARY
    assert 'grant_cache_control' in CANARY
    assert '"$grant_cache_control" != "no-store"' in CANARY
    assert 'rg --fixed-strings --file "$canary_tmp/packet-key-patterns.txt"' in CANARY
    assert "TOUGH_TONGUE_REMOTE_EXECUTION_ENABLED" in CANARY
    assert "rm -rf" not in CANARY
    assert "set -x" not in CANARY
    assert "printf '%s' \"$packet_key\"" not in CANARY

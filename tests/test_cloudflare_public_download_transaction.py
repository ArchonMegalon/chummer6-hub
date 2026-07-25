from __future__ import annotations

import copy
import importlib.util
import json
import os
from pathlib import Path
import re
import stat
import sys
from typing import Any, Mapping
import urllib.parse

import pytest


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "cloudflare_public_download_transaction.py"
SPEC = importlib.util.spec_from_file_location(
    "cloudflare_public_download_transaction_test", MODULE_PATH
)
assert SPEC is not None and SPEC.loader is not None
transaction = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = transaction
SPEC.loader.exec_module(transaction)

POSTDEPLOY_MODULE_PATH = (
    ROOT / "scripts" / "verify_public_download_only_postdeploy.py"
)
POSTDEPLOY_SPEC = importlib.util.spec_from_file_location(
    "public_download_only_postdeploy_route_contract_test",
    POSTDEPLOY_MODULE_PATH,
)
assert POSTDEPLOY_SPEC is not None and POSTDEPLOY_SPEC.loader is not None
postdeploy = importlib.util.module_from_spec(POSTDEPLOY_SPEC)
sys.modules[POSTDEPLOY_SPEC.name] = postdeploy
POSTDEPLOY_SPEC.loader.exec_module(postdeploy)

GENERATION_ID = "g-20260724T000000Z-0123456789abcdef"
PROBE_ENDPOINT = (
    f"https://chummer.run/downloads/g/{GENERATION_ID}/releases.json"
)
PROBE_BODY_SHA256 = "a" * 64


def probe_observations() -> list[dict[str, object]]:
    path = f"/downloads/g/{GENERATION_ID}/releases.json"
    return [
        {
            "endpoint": f"https://{hostname}{path}",
            "httpStatus": 200,
            "bodySha256": PROBE_BODY_SHA256,
            "anonymous": True,
        }
        for hostname in transaction.MANAGED_HOSTS
    ]


def base_config() -> dict[str, Any]:
    return {
        "warp-routing": {"enabled": False},
        "originRequest": {"connectTimeout": 30},
        "ingress": [
            {
                "hostname": "private.chummer.run",
                "path": r"^/preserved/(.*)$",
                "service": "http://legacy:8123",
                "originRequest": {"noTLSVerify": False},
            },
            {"hostname": "*.chummer.run", "service": "http://incumbent:8080"},
            {"service": "http_status:404"},
        ],
    }


def resolve_ingress_service(
    config: Mapping[str, Any],
    hostname: str,
    path: str,
) -> str:
    for rule in config["ingress"]:
        rule_hostname = str(rule.get("hostname") or "")
        if rule_hostname:
            hostname_matches = (
                hostname == rule_hostname
                or (
                    rule_hostname.startswith("*.")
                    and hostname.endswith(rule_hostname[1:])
                )
            )
            if not hostname_matches:
                continue
        rule_path = str(rule.get("path") or "")
        if rule_path and re.fullmatch(rule_path, path) is None:
            continue
        return str(rule["service"])
    raise AssertionError("validated ingress must end with a catch-all")


class FakeApi:
    def __init__(
        self,
        config: Mapping[str, Any] | None = None,
        *,
        version: int = 7,
        connector_versions: Mapping[str, int | None] | None = None,
    ) -> None:
        self.config = copy.deepcopy(dict(config or base_config()))
        self.version = version
        self.connector_versions = dict(
            {"connector-a": version}
            if connector_versions is None
            else connector_versions
        )
        self.auto_converge_connectors = True
        self.lose_next_put_response = False
        self.put_calls: list[dict[str, Any]] = []
        self.get_calls = 0
        self.connector_get_calls: list[str] = []

    def _configuration_response(self) -> dict[str, Any]:
        return {
            "success": True,
            "errors": [],
            "messages": [{"code": 1000, "message": "preserve this response"}],
            "result": {
                "config": copy.deepcopy(self.config),
                "version": self.version,
                "source": "cloudflare",
            },
        }

    def get_configuration(self) -> Mapping[str, Any]:
        self.get_calls += 1
        return self._configuration_response()

    def put_configuration(self, config: Mapping[str, Any]) -> Mapping[str, Any]:
        self.put_calls.append(copy.deepcopy(dict(config)))
        self.config = copy.deepcopy(dict(config))
        self.version += 1
        if self.auto_converge_connectors:
            for connector_id, current in self.connector_versions.items():
                if current is not None:
                    self.connector_versions[connector_id] = self.version
        response = self._configuration_response()
        if self.lose_next_put_response:
            self.lose_next_put_response = False
            raise TimeoutError("simulated response loss")
        return response

    def list_connections(self) -> Mapping[str, Any]:
        connector_ids = list(
            reversed(sorted(self.connector_versions))
        )
        result = [
            {"id": connector_id}
            for connector_id in connector_ids
        ]
        return {
            "success": True,
            "errors": [],
            "messages": [],
            "result": result,
            "result_info": {
                "count": len(result),
                "page": 1,
                "per_page": 20,
                "total_count": len(connector_ids),
            },
        }

    def get_connector(self, connector_id: str) -> Mapping[str, Any]:
        self.connector_get_calls.append(connector_id)
        result: dict[str, Any] = {"id": connector_id}
        version = self.connector_versions[connector_id]
        if version is not None:
            result["config_version"] = version
        return {"success": True, "result": result}


class ChangingConnectorApi:
    def __init__(
        self,
        snapshots: list[Mapping[str, int | None]],
    ) -> None:
        self.snapshots = [dict(snapshot) for snapshot in snapshots]
        self.list_calls = 0
        self.current: dict[str, int | None] = {}

    def list_connections(self) -> Mapping[str, Any]:
        index = min(self.list_calls, len(self.snapshots) - 1)
        self.current = dict(self.snapshots[index])
        self.list_calls += 1
        connector_ids = list(reversed(sorted(self.current)))
        result = [
            {"id": connector_id}
            for connector_id in connector_ids
        ]
        return {
            "success": True,
            "errors": [],
            "messages": [],
            "result": result,
            "result_info": {
                "count": len(result),
                "page": 1,
                "per_page": 20,
                "total_count": len(connector_ids),
            },
        }

    def get_connector(self, connector_id: str) -> Mapping[str, Any]:
        result: dict[str, Any] = {"id": connector_id}
        version = self.current[connector_id]
        if version is not None:
            result["config_version"] = version
        return {"success": True, "result": result}


class ScriptedConnectionsApi:
    def __init__(
        self,
        responses: list[Mapping[str, Any]],
        versions: Mapping[str, int | None],
    ) -> None:
        self.responses = [copy.deepcopy(dict(value)) for value in responses]
        self.versions = dict(versions)
        self.list_calls = 0

    def list_connections(self) -> Mapping[str, Any]:
        response = self.responses[self.list_calls]
        self.list_calls += 1
        return response

    def get_connector(self, connector_id: str) -> Mapping[str, Any]:
        result: dict[str, Any] = {"id": connector_id}
        version = self.versions[connector_id]
        if version is not None:
            result["config_version"] = version
        return {"success": True, "result": result}


def connections_response(
    connector_ids: list[str],
    *,
    page: int = 1,
    total_count: int | None = None,
    per_page: int = 20,
) -> dict[str, Any]:
    if total_count is None:
        total_count = len(connector_ids)
    return {
        "success": True,
        "errors": [],
        "messages": [],
        "result": [
            {"id": connector_id} for connector_id in connector_ids
        ],
        "result_info": {
            "count": len(connector_ids),
            "page": page,
            "per_page": per_page,
            "total_count": total_count,
        },
    }


def capture(
    tmp_path: Path, api: FakeApi, *, origin: str = "http://172.17.0.1:8080"
) -> tuple[Path, Path, dict[str, Any]]:
    journal_path = tmp_path / "cloudflare-transaction.json"
    lock_path = tmp_path / "cloudflare-transaction.lock"
    journal = transaction.capture_transaction(
        api,
        account_id="account_123",
        tunnel_id="tunnel-456",
        origin=origin,
        generation_id=GENERATION_ID,
        probe_endpoint=PROBE_ENDPOINT,
        probe_body_sha256=PROBE_BODY_SHA256,
        journal_path=journal_path,
        lock_path=lock_path,
    )
    return journal_path, lock_path, journal


def apply(
    api: FakeApi, journal_path: Path, lock_path: Path
) -> dict[str, Any]:
    return transaction.apply_transaction(
        api,
        journal_path=journal_path,
        lock_path=lock_path,
        attempts=2,
        interval_seconds=0,
        sleep_fn=lambda _: None,
    )


def committed_evidence(tmp_path: Path) -> Path:
    return tmp_path / "cloudflare-committed.json"


def rollback_evidence(tmp_path: Path) -> Path:
    return tmp_path / "cloudflare-rolled-back.json"


def test_plan_prepends_exact_scoped_rules_and_preserves_prior_semantics() -> None:
    prior = base_config()
    prior_copy = copy.deepcopy(prior)
    target = transaction.plan_public_download_config(
        prior, "http://host.docker.internal:8123/"
    )

    assert prior == prior_copy
    assert [rule["hostname"] for rule in target["ingress"][:2]] == [
        "chummer.run",
        "www.chummer.run",
    ]
    for rule in target["ingress"][:2]:
        assert rule == {
            "hostname": rule["hostname"],
            "path": transaction.MANAGED_PATH_RE2,
            "service": "http://host.docker.internal:8123",
        }
        assert "originRequest" not in rule
        assert "httpHostHeader" not in rule
    fail_closed_rules = target["ingress"][
        2 : 2
        + len(transaction.FAIL_CLOSED_PATHS_RE2)
        * len(transaction.MANAGED_HOSTS)
    ]
    assert fail_closed_rules == [
        {
            "hostname": hostname,
            "path": path,
            "service": "http_status:404",
        }
        for path in transaction.FAIL_CLOSED_PATHS_RE2
        for hostname in transaction.MANAGED_HOSTS
    ]
    for rule in fail_closed_rules:
        assert "originRequest" not in rule
        assert "httpHostHeader" not in rule
    preserved_offset = 2 + len(fail_closed_rules)
    assert target["ingress"][preserved_offset:] == prior["ingress"]
    assert target["originRequest"] == prior["originRequest"]
    assert transaction.canonical_json_bytes(
        target["ingress"][preserved_offset:]
    ) == (
        transaction.canonical_json_bytes(prior["ingress"])
    )


@pytest.mark.parametrize(
    ("hostname", "path", "expected_service"),
    [
        (
            "chummer.run",
            "/downloads/install/avalonia-win-x64-installer",
            "http://host.docker.internal:8123",
        ),
        (
            "www.chummer.run",
            "/downloads/install/unknown-installer",
            "http://host.docker.internal:8123",
        ),
        (
            "www.chummer.run",
            "/downloads/install/unknown-installer/payload",
            "http://host.docker.internal:8123",
        ),
        (
            "chummer.run",
            "/downloads/install/unknown-installer/metadata",
            "http://host.docker.internal:8123",
        ),
        (
            "chummer.run",
            "/downloads/install/UNKNOWN-INSTALLER/payload",
            "http_status:404",
        ),
        (
            "chummer.run",
            "/DOWNLOADS/INSTALL/unknown-installer/payload",
            "http_status:404",
        ),
        (
            "chummer.run",
            "/downloads/install/unknown-installer/PAYLOAD",
            "http_status:404",
        ),
        (
            "chummer.run",
            "/downloads/install/unknown-installer/payload/",
            "http_status:404",
        ),
        (
            "chummer.run",
            "/downloads/install/unknown-installer/metadata/extra",
            "http_status:404",
        ),
        (
            "chummer.run",
            "/downloads/install/AVALONIA-WIN-X64-INSTALLER",
            "http_status:404",
        ),
        (
            "chummer.run",
            "/DOWNLOADS/INSTALL/avalonia-win-x64-installer",
            "http_status:404",
        ),
        (
            "chummer.run",
            "/downloads/install/-invalid",
            "http_status:404",
        ),
        (
            "chummer.run",
            "/downloads/install/avalonia-win-x64-installer/",
            "http_status:404",
        ),
        (
            "chummer.run",
            "/downloads/install/..",
            "http_status:404",
        ),
        (
            "chummer.run",
            "/downloads/install/../admin",
            "http_status:404",
        ),
        (
            "www.chummer.run",
            "/downloads/install/avalonia-win-x64-installer/../admin",
            "http_status:404",
        ),
        (
            "www.chummer.run",
            "/downloads/install/avalonia-win-x64-installer/bootstrap.sh",
            "http://incumbent:8080",
        ),
        (
            "chummer.run",
            f"/downloads/g/{GENERATION_ID}/install/test-installer",
            "http://host.docker.internal:8123",
        ),
        (
            "www.chummer.run",
            f"/downloads/g/{GENERATION_ID}/install/test-installer/payload",
            "http://host.docker.internal:8123",
        ),
        (
            "chummer.run",
            f"/downloads/g/{GENERATION_ID}/install/test-installer/metadata",
            "http://host.docker.internal:8123",
        ),
        (
            "chummer.run",
            f"/DOWNLOADS/g/{GENERATION_ID}/install/test-installer/payload",
            "http_status:404",
        ),
        (
            "chummer.run",
            f"/downloads/g/{GENERATION_ID}/INSTALL/test-installer/payload",
            "http_status:404",
        ),
        (
            "chummer.run",
            f"/downloads/g/{GENERATION_ID}/install/TEST-INSTALLER/payload",
            "http_status:404",
        ),
        (
            "chummer.run",
            f"/downloads/g/{GENERATION_ID}/install/test-installer/payload/",
            "http_status:404",
        ),
        (
            "chummer.run",
            f"/downloads/g/{GENERATION_ID}/install/test-installer/private",
            "http_status:404",
        ),
        (
            "chummer.run",
            f"/downloads/g/{GENERATION_ID}/install",
            "http_status:404",
        ),
        (
            "chummer.run",
            "/downloads/g/foo/bar/install/test-installer/payload",
            "http_status:404",
        ),
        (
            "chummer.run",
            "/downloads/files",
            "http_status:404",
        ),
        (
            "www.chummer.run",
            "/DOWNLOADS/FILES/Chummer.zip",
            "http_status:404",
        ),
        (
            "chummer.run",
            "/downloads/files/private/Chummer.zip",
            "http_status:404",
        ),
        (
            "chummer.run",
            f"/downloads/g/{GENERATION_ID}/files/Chummer.zip/",
            "http_status:404",
        ),
        (
            "www.chummer.run",
            f"/downloads/g/{GENERATION_ID}/FILES/Chummer.zip",
            "http_status:404",
        ),
        (
            "chummer.run",
            "/downloads/g/foo/bar/files/Chummer.zip",
            "http_status:404",
        ),
        (
            "www.chummer.run",
            "/downloads/file/incumbent-artifact",
            "http://incumbent:8080",
        ),
        (
            "www.chummer.run",
            f"/downloads/g/{GENERATION_ID}/index.json",
            "http://incumbent:8080",
        ),
        (
            "chummer.run",
            "/api/v1/public/release-truth",
            "http://host.docker.internal:8123",
        ),
        (
            "www.chummer.run",
            "/api/public/release-truth",
            "http://host.docker.internal:8123",
        ),
        (
            "chummer.run",
            f"/api/v1/public/release-truth/g/{GENERATION_ID}",
            "http://host.docker.internal:8123",
        ),
        (
            "www.chummer.run",
            f"/api/public/release-truth/g/{GENERATION_ID}",
            "http://host.docker.internal:8123",
        ),
        (
            "chummer.run",
            "/API/V1/PUBLIC/RELEASE-TRUTH",
            "http_status:404",
        ),
        (
            "chummer.run",
            "/api/v1/public/release-truth/",
            "http_status:404",
        ),
        (
            "chummer.run",
            f"/api/v1/public/release-truth/g/{GENERATION_ID}/extra",
            "http_status:404",
        ),
        (
            "www.chummer.run",
            "/api/v1/public/weekly-pulse",
            "http://incumbent:8080",
        ),
        (
            "www.chummer.run",
            "/unrelated",
            "http://incumbent:8080",
        ),
        (
            "private.chummer.run",
            "/preserved/value",
            "http://legacy:8123",
        ),
    ],
)
def test_composed_ingress_routes_canonical_installs_and_denies_fallthrough(
    hostname: str,
    path: str,
    expected_service: str,
) -> None:
    target = transaction.plan_public_download_config(
        base_config(),
        "http://host.docker.internal:8123/",
    )

    assert resolve_ingress_service(target, hostname, path) == expected_service


@pytest.mark.parametrize("rule_index", [2, 4])
def test_fail_closed_rules_cannot_move_behind_preserved_incumbent(
    rule_index: int,
) -> None:
    prior = base_config()
    target = transaction.plan_public_download_config(
        prior,
        "http://host.docker.internal:8123",
    )
    displaced = target["ingress"].pop(rule_index)
    target["ingress"].insert(-1, displaced)

    with pytest.raises(
        transaction.ValidationError,
        match="fail-closed rules are missing or not first",
    ):
        transaction.validate_planned_config(
            prior,
            target,
            "http://host.docker.internal:8123",
        )


@pytest.mark.parametrize(
    "raw_path",
    [
        "/downloads/install/%2e%2e%2fadmin",
        "/downloads/install/avalonia-win-x64-installer%2f..%2fadmin",
        "/DOWNLOADS/INSTALL/%2E%2E%2Fadmin",
    ],
)
def test_cloudflared_decoded_dot_segment_traversal_is_denied_before_incumbent(
    raw_path: str,
) -> None:
    target = transaction.plan_public_download_config(
        base_config(),
        "http://host.docker.internal:8123",
    )
    decoded_path = urllib.parse.unquote(raw_path)

    assert decoded_path != raw_path
    assert (
        resolve_ingress_service(target, "chummer.run", decoded_path)
        == "http_status:404"
    )


@pytest.mark.parametrize(
    "path",
    [
        "/api/ready/public-downloads",
        "/api/ready",
        "/api/ready/publication",
        "/api/ready/install-linking-authority",
        "/api/v1/install-linking/me",
        "/account/access/install-link",
        "/downloads/install/public-download-only-probe",
        "/downloads/install/avalonia-win-x64-installer",
        "/downloads/install/avalonia-win-x64-installer/payload",
        "/downloads/install/avalonia-win-x64-installer/metadata",
        "/api/v1/public/release-truth",
        "/api/public/release-truth",
        f"/api/v1/public/release-truth/g/{GENERATION_ID}",
        f"/api/public/release-truth/g/{GENERATION_ID}",
        f"/downloads/g/{GENERATION_ID}/releases.json",
        f"/downloads/g/{GENERATION_ID}/RELEASE_CHANNEL.generated.json",
        f"/downloads/g/{GENERATION_ID}/install/test-installer",
        f"/downloads/g/{GENERATION_ID}/install/test-installer/payload",
        f"/downloads/g/{GENERATION_ID}/install/test-installer/metadata",
        f"/downloads/g/{GENERATION_ID}/files/Chummer6-installer.msi",
        f"/downloads/g/{GENERATION_ID}/files/Chummer6-payload.zip",
        f"/downloads/g/{GENERATION_ID}/files/Chummer6-payload.zip.json",
        f"/downloads/g/{GENERATION_ID}/files/Chummer6-sidecar+portable.zip",
        "/downloads/files/Chummer.zip",
        "/downloads/files/Chummer_6.1.0+portable.zip",
        "/downloads/releases.json",
        "/downloads/RELEASE_CHANNEL.generated.json",
    ],
)
def test_managed_regex_includes_only_approved_paths(path: str) -> None:
    transaction.validate_re2_pattern(transaction.MANAGED_PATH_RE2)
    assert transaction.managed_path_matches(path)


@pytest.mark.parametrize(
    "path",
    [
        "/downloads",
        "/downloads/",
        "/downloads/current.json",
        "/downloads/PUBLICATION_SCOPE.generated.json",
        "/downloads/install",
        "/downloads/install/-invalid",
        "/DOWNLOADS/INSTALL/avalonia-win-x64-installer",
        "/downloads/install/AVALONIA-WIN-X64-INSTALLER",
        "/downloads/install/../admin",
        "/downloads/install/%2e%2e%2fadmin",
        "/downloads/install/avalonia-win-x64-installer/extra",
        "/downloads/install/avalonia-win-x64-installer/PAYLOAD",
        "/downloads/install/avalonia-win-x64-installer/METADATA",
        "/downloads/install/avalonia-win-x64-installer/payload/",
        "/downloads/install/avalonia-win-x64-installer/metadata/extra",
        "/downloads/install/avalonia-win-x64-installer?next=/admin",
        "/API/V1/PUBLIC/RELEASE-TRUTH",
        "/api/V1/public/release-truth",
        "/api/v1/Public/release-truth",
        "/api/v1/public/Release-Truth",
        "/api/v1/public/release-truth/",
        "/api/v2/public/release-truth",
        "/api/v1/public/release-truth/private",
        f"/api/v1/public/release-truth/g/{GENERATION_ID}/extra",
        "/downloads/claim/token",
        "/downloads/upload/file",
        "/downloads/personalized/alice",
        "/api/ready/extra",
        "/api/ready/public-downloads/extra",
        "/api/ready/publication/extra",
        "/api/ready/install-linking-authority/extra",
        "/api/v1/install-linking",
        "/api/v1/install-linking/me/extra",
        "/account/access/install-link/extra",
        "/downloads/install/public-download-only-probe/extra",
        "/DOWNLOADS/releases.json",
        "/downloads/g",
        "/downloads/files",
        f"/downloads/g/{GENERATION_ID}/index.json",
        f"/downloads/g/{GENERATION_ID}/files/private/Chummer.zip",
        f"/downloads/g/{GENERATION_ID}/files/Chummer%2fprivate.zip",
        f"/downloads/g/{GENERATION_ID}/install/Chummer.zip",
        f"/downloads/g/{GENERATION_ID}/install/TEST-INSTALLER",
        f"/downloads/g/{GENERATION_ID}/install/test-installer/PAYLOAD",
        f"/downloads/g/{GENERATION_ID}/install/test-installer/METADATA",
        f"/downloads/g/{GENERATION_ID}/install/test-installer/payload/",
        f"/downloads/g/{GENERATION_ID}/install/test-installer/metadata/extra",
        f"/downloads/g/{GENERATION_ID}/payload/Chummer.zip",
        "/downloads/files/private/Chummer.zip",
        "/downloads/files/payload/Chummer.zip",
        "/downloads/files/install/Chummer.zip",
        "/downloads/files/Chummer%2fprivate.zip",
        "/downloads/files/Chummer%252fprivate.zip",
        "/downloads/files/.hidden",
        "/downloads/files/Chummer.zip/",
        "/downloads/install/Chummer.zip",
        "/downloads/payload/Chummer.zip",
        "/downloads/private/Chummer.zip",
    ],
)
def test_managed_regex_excludes_all_unapproved_surfaces(path: str) -> None:
    assert not transaction.managed_path_matches(path)


@pytest.mark.parametrize(
    "artifact_id",
    [
        "avalonia-win-x64-installer",
        "unknown-installer",
        "disabled-installer",
        "revoked-installer",
    ],
)
def test_safe_install_ids_reach_the_governed_runtime_for_authority_decision(
    artifact_id: str,
) -> None:
    assert transaction.managed_path_matches(
        f"/downloads/install/{artifact_id}"
    )


def test_managed_regex_uses_no_known_non_re2_constructs() -> None:
    pattern = transaction.MANAGED_PATH_RE2
    assert "(?" not in pattern
    assert re.search(r"\\[1-9]", pattern) is None
    transaction.validate_re2_pattern(pattern)


def test_managed_control_paths_close_the_strict_postdeploy_contract() -> None:
    required = {
        "/api/ready/public-downloads",
        *postdeploy.UNAVAILABLE_READINESS_PATHS,
        *postdeploy.PRIVATE_PATHS,
        *postdeploy.INSTALL_ROUTE_DENIAL_PATHS,
    }

    assert set(transaction.MANAGED_CONTROL_PATHS) == required
    for path in required:
        assert transaction.managed_path_matches(path)
        assert not transaction.managed_path_matches(f"{path}/extra")


@pytest.mark.parametrize(
    "bad_config",
    [
        None,
        {},
        {"ingress": []},
        {"ingress": ["not-an-object"]},
        {"ingress": [{"service": ""}]},
        {"ingress": [{"hostname": "x", "service": "http://x"}]},
        {"ingress": [{"service": "http_status:404", "originRequest": "bad"}]},
    ],
)
def test_malformed_tunnel_configs_fail_closed(bad_config: Any) -> None:
    with pytest.raises(transaction.ValidationError):
        transaction.validate_tunnel_config(bad_config)


@pytest.mark.parametrize(
    "path",
    [
        transaction.MANAGED_PATH_RE2,
        *transaction.FAIL_CLOSED_PATHS_RE2,
    ],
)
def test_existing_managed_rule_is_rejected_instead_of_duplicated(
    path: str,
) -> None:
    prior = base_config()
    prior["ingress"].insert(
        0,
        {
            "hostname": "chummer.run",
            "path": path,
            "service": "http://old:8080",
        },
    )

    with pytest.raises(transaction.ValidationError, match="already contains"):
        transaction.plan_public_download_config(prior, "http://new:8080")


def test_locally_managed_tunnel_response_is_rejected() -> None:
    api = FakeApi()
    response = api._configuration_response()
    response["result"]["source"] = "local"

    with pytest.raises(transaction.ValidationError, match="remotely managed"):
        transaction.parse_configuration_response(response)


def test_transport_uses_documented_configuration_connection_and_connector_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = transaction.CloudflareTunnelApi(
        api_base="https://api.cloudflare.test/client/v4",
        account_id="account",
        tunnel_id="tunnel",
        auth_headers={"Authorization": "Bearer in-memory-only"},
        timeout_seconds=5,
    )
    calls: list[tuple[str, str, Mapping[str, Any] | None]] = []

    def record(
        method: str, path: str, payload: Mapping[str, Any] | None = None
    ) -> Mapping[str, Any]:
        calls.append((method, path, payload))
        return {"success": True, "result": {}}

    monkeypatch.setattr(api, "_request", record)
    api.get_configuration()
    api.put_configuration(base_config())
    api.list_connections()
    api.get_connector("connector-1")

    prefix = "/accounts/account/cfd_tunnel/tunnel"
    assert calls == [
        ("GET", prefix + "/configurations", None),
        ("PUT", prefix + "/configurations", {"config": base_config()}),
        ("GET", prefix + "/connections", None),
        ("GET", prefix + "/connectors/connector-1", None),
    ]


def test_capture_journals_exact_prior_response_and_owner_only_durable_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    api = FakeApi()
    fsync_calls: list[int] = []
    real_fsync = transaction.os.fsync

    def recording_fsync(fd: int) -> None:
        fsync_calls.append(fd)
        real_fsync(fd)

    monkeypatch.setattr(transaction.os, "fsync", recording_fsync)
    journal_path, lock_path, journal = capture(tmp_path, api)

    disk = transaction.load_journal(journal_path)
    assert disk == journal
    assert disk["priorResponse"] == api._configuration_response()
    assert disk["priorConfig"] == base_config()
    assert disk["priorVersion"] == 7
    assert disk["priorConfigSha256"] == transaction.canonical_sha256(base_config())
    assert stat.S_IMODE(journal_path.stat().st_mode) == 0o600
    assert stat.S_IMODE(lock_path.stat().st_mode) == 0o600
    assert len(fsync_calls) >= 4


def test_capture_requires_at_least_one_preexisting_connector(
    tmp_path: Path,
) -> None:
    api = FakeApi(connector_versions={})

    with pytest.raises(transaction.ConvergenceError, match="no preexisting"):
        capture(tmp_path, api)


def test_connector_capture_accepts_complete_provider_single_page_above_20() -> None:
    all_ids = [f"connector-{index:04d}" for index in range(21)]
    api = ScriptedConnectionsApi(
        [
            connections_response(
                all_ids,
                total_count=len(all_ids),
                per_page=20,
            ),
        ],
        {connector_id: 12 for connector_id in all_ids},
    )

    captured = transaction.capture_preexisting_connectors(api)

    assert api.list_calls == 1
    assert [row["id"] for row in captured] == sorted(all_ids)


@pytest.mark.parametrize(
    "responses,match",
    (
        (
            [
                {
                    **connections_response(["connector-a"]),
                    "result_info": {
                        "count": 1,
                        "page": 1,
                        "per_page": 20,
                    },
                }
            ],
            "result_info shape",
        ),
        (
            [
                {
                    **connections_response(["connector-a"]),
                    "unexpected": True,
                }
            ],
            "response shape",
        ),
        (
            [
                connections_response(
                    [
                        f"connector-{index:04d}"
                        for index in range(
                            transaction.MAX_CURRENT_CONNECTORS + 1
                        )
                    ],
                )
            ],
            "single-page metadata",
        ),
        (
            [
                connections_response(
                    ["connector-a"],
                    page=2,
                )
            ],
            "single-page metadata",
        ),
        (
            [connections_response(["connector-a"], per_page=0)],
            "single-page metadata",
        ),
    ),
)
def test_connector_capture_rejects_response_or_bound_drift(
    responses: list[Mapping[str, Any]],
    match: str,
) -> None:
    api = ScriptedConnectionsApi(
        responses,
        {"connector-a": 12},
    )

    with pytest.raises(transaction.ValidationError, match=match):
        transaction.capture_preexisting_connectors(api)


def test_connector_capture_rejects_incomplete_single_page_metadata() -> None:
    returned = [f"connector-{index:04d}" for index in range(20)]
    api = ScriptedConnectionsApi(
        [
            connections_response(
                returned,
                total_count=len(returned) + 1,
            ),
        ],
        {connector_id: 12 for connector_id in returned},
    )

    with pytest.raises(
        transaction.ValidationError,
        match="invalid or incomplete",
    ):
        transaction.capture_preexisting_connectors(api)


def test_connector_capture_rejects_single_page_duplicates() -> None:
    api = ScriptedConnectionsApi(
        [connections_response(["connector-a", "connector-a"])],
        {"connector-a": 12},
    )

    with pytest.raises(transaction.ValidationError, match="duplicates"):
        transaction.capture_preexisting_connectors(api)


def test_current_connector_convergence_tracks_additions_and_removals() -> None:
    api = ChangingConnectorApi(
        [
            {"connector-original": 11},
            {
                "connector-added": 12,
                "connector-original": 12,
            },
            {"connector-added": 12},
            {"connector-added": 12},
        ]
    )

    receipt = transaction.poll_current_connector_convergence(
        api,
        12,
        attempts=4,
        interval_seconds=0,
        sleep_fn=lambda _seconds: None,
    )

    assert receipt["connectorSetTransitions"] == [
        ["connector-original"],
        ["connector-added", "connector-original"],
        ["connector-added"],
    ]
    assert receipt["attemptsUsed"] == 4
    assert [
        row["id"] for row in receipt["connectorSet"]
    ] == ["connector-added"]
    assert receipt["connectorConvergence"] == [
        {
            "id": "connector-added",
            "configVersionAvailable": True,
            "observedConfigVersion": 12,
            "converged": True,
        }
    ]
    assert (
        transaction.validate_current_connector_convergence_receipt(
            receipt
        )
        == receipt
    )


def test_current_connector_convergence_rejects_an_unstable_set() -> None:
    api = ChangingConnectorApi(
        [
            {"connector-a": 12},
            {"connector-b": 12},
            {"connector-a": 12},
            {"connector-b": 12},
        ]
    )

    with pytest.raises(
        transaction.ConvergenceError,
        match="did not remain stable",
    ):
        transaction.poll_current_connector_convergence(
            api,
            12,
            attempts=4,
            interval_seconds=0,
            sleep_fn=lambda _seconds: None,
        )


def test_current_connector_convergence_rejects_unknown_versions() -> None:
    api = ChangingConnectorApi(
        [
            {"connector-a": None},
            {"connector-a": None},
            {"connector-a": None},
        ]
    )

    with pytest.raises(
        transaction.ConvergenceError,
        match="did not converge",
    ):
        transaction.poll_current_connector_convergence(
            api,
            12,
            attempts=3,
            interval_seconds=0,
            sleep_fn=lambda _seconds: None,
        )


def test_current_connector_receipt_rejects_omitted_added_connector() -> None:
    api = ChangingConnectorApi(
        [
            {"connector-a": 12, "connector-added": 12},
            {"connector-a": 12, "connector-added": 12},
        ]
    )
    receipt = transaction.poll_current_connector_convergence(
        api,
        12,
        attempts=2,
        interval_seconds=0,
        sleep_fn=lambda _seconds: None,
    )
    receipt["connectorSet"] = receipt["connectorSet"][:1]

    with pytest.raises(transaction.ValidationError):
        transaction.validate_current_connector_convergence_receipt(
            receipt
        )


def test_current_connector_receipt_rejects_unknown_version_proof() -> None:
    api = ChangingConnectorApi(
        [
            {"connector-a": 12},
            {"connector-a": 12},
        ]
    )
    receipt = transaction.poll_current_connector_convergence(
        api,
        12,
        attempts=2,
        interval_seconds=0,
        sleep_fn=lambda _seconds: None,
    )
    receipt["connectorSet"][0] = {
        "id": "connector-a",
        "configVersionAvailable": False,
        "configVersion": None,
    }
    receipt["connectorSetSha256"] = transaction.canonical_sha256(
        receipt["connectorSet"]
    )
    receipt["connectorConvergence"][0] = {
        "id": "connector-a",
        "configVersionAvailable": False,
        "observedConfigVersion": None,
        "converged": None,
    }

    with pytest.raises(
        transaction.ValidationError,
        match="lacks exact configuration versions",
    ):
        transaction.validate_current_connector_convergence_receipt(
            receipt
        )


def test_capture_is_no_replace_and_does_not_delete_existing_journal(
    tmp_path: Path,
) -> None:
    api = FakeApi()
    journal_path, lock_path, _ = capture(tmp_path, api)
    original = journal_path.read_bytes()

    with pytest.raises(transaction.JournalError, match="already exists"):
        transaction.capture_transaction(
            api,
            account_id="account_123",
            tunnel_id="tunnel-456",
            origin="http://172.17.0.1:8080",
            generation_id=GENERATION_ID,
            probe_endpoint=PROBE_ENDPOINT,
            probe_body_sha256=PROBE_BODY_SHA256,
            journal_path=journal_path,
            lock_path=lock_path,
        )

    assert journal_path.read_bytes() == original


def test_journal_rejects_schema_or_digest_tampering(tmp_path: Path) -> None:
    api = FakeApi()
    journal_path, _, journal = capture(tmp_path, api)
    journal["targetConfigSha256"] = "0" * 64
    journal_path.write_text(json.dumps(journal), encoding="utf-8")
    os.chmod(journal_path, 0o600)

    with pytest.raises(transaction.ValidationError, match="digest"):
        transaction.load_journal(journal_path)


def test_apply_rechecks_exact_version_and_rejects_same_config_version_drift(
    tmp_path: Path,
) -> None:
    api = FakeApi()
    journal_path, lock_path, _ = capture(tmp_path, api)
    api.version += 1

    with pytest.raises(transaction.DriftError, match="drifted"):
        apply(api, journal_path, lock_path)

    assert api.put_calls == []
    assert journal_path.exists()


def test_apply_rejects_config_drift_without_overwriting_it(tmp_path: Path) -> None:
    api = FakeApi()
    journal_path, lock_path, _ = capture(tmp_path, api)
    api.config["ingress"].insert(
        0, {"hostname": "concurrent.example", "service": "http://other:80"}
    )
    api.version += 1
    concurrent = copy.deepcopy(api.config)

    with pytest.raises(transaction.DriftError):
        apply(api, journal_path, lock_path)

    assert api.config == concurrent
    assert api.put_calls == []
    assert journal_path.exists()


def test_apply_recovers_idempotently_when_put_response_is_lost(
    tmp_path: Path,
) -> None:
    api = FakeApi()
    journal_path, lock_path, captured = capture(tmp_path, api)
    api.lose_next_put_response = True

    applied = apply(api, journal_path, lock_path)

    assert applied["phase"] == "applied"
    assert applied["targetVersion"] == 8
    assert transaction.canonical_sha256(api.config) == captured["targetConfigSha256"]
    assert len(api.put_calls) == 1


def test_apply_polls_every_preexisting_connector(tmp_path: Path) -> None:
    api = FakeApi(connector_versions={"connector-b": 7, "connector-a": 7})
    journal_path, lock_path, _ = capture(tmp_path, api)
    api.connector_get_calls.clear()

    applied = apply(api, journal_path, lock_path)

    assert applied["phase"] == "applied"
    assert [row["id"] for row in applied["connectorConvergence"]] == [
        "connector-a",
        "connector-b",
    ]
    assert set(api.connector_get_calls) == {"connector-a", "connector-b"}


def test_connector_version_mismatch_blocks_apply_completion_and_keeps_journal(
    tmp_path: Path,
) -> None:
    api = FakeApi(connector_versions={"connector-a": 7})
    api.auto_converge_connectors = False
    journal_path, lock_path, _ = capture(tmp_path, api)

    with pytest.raises(transaction.ConvergenceError, match="connector"):
        transaction.apply_transaction(
            api,
            journal_path=journal_path,
            lock_path=lock_path,
            attempts=1,
            interval_seconds=0,
            sleep_fn=lambda _: None,
        )

    assert journal_path.exists()
    assert transaction.load_journal(journal_path)["phase"] == "apply-in-flight"


def test_apply_retry_rejects_same_target_digest_at_a_different_version(
    tmp_path: Path,
) -> None:
    api = FakeApi(connector_versions={"connector-a": 7})
    api.auto_converge_connectors = False
    journal_path, lock_path, _ = capture(tmp_path, api)
    with pytest.raises(transaction.ConvergenceError):
        transaction.apply_transaction(
            api,
            journal_path=journal_path,
            lock_path=lock_path,
            attempts=1,
            interval_seconds=0,
            sleep_fn=lambda _: None,
        )
    api.version += 1

    with pytest.raises(transaction.DriftError):
        apply(api, journal_path, lock_path)

    assert journal_path.exists()


def test_missing_connector_config_version_requires_bound_external_probe(
    tmp_path: Path,
) -> None:
    api = FakeApi(connector_versions={"connector-without-version": None})
    journal_path, lock_path, _ = capture(tmp_path, api)
    applied = apply(api, journal_path, lock_path)
    assert applied["phase"] == "awaiting-external-probe"
    assert applied["connectorConvergence"] == [
        {
            "id": "connector-without-version",
            "configVersionAvailable": False,
            "observedConfigVersion": None,
            "converged": None,
        }
    ]

    with pytest.raises(transaction.ConvergenceError, match="external probe"):
        transaction.commit_transaction(
            api,
            journal_path=journal_path,
            lock_path=lock_path,
            evidence_path=committed_evidence(tmp_path),
        )
    assert journal_path.exists()

    wrong_receipt_path = tmp_path / "wrong-probe.json"
    wrong_receipt_path.write_text(
        json.dumps(
            {
                "schema": transaction.EXTERNAL_PROBE_SCHEMA,
                "accountId": applied["accountId"],
                "tunnelId": applied["tunnelId"],
                "targetConfigSha256": "0" * 64,
                "targetVersion": applied["targetVersion"],
                "connectorIds": ["connector-without-version"],
                "generationId": GENERATION_ID,
                "observations": probe_observations(),
                "observedAt": "2026-07-24T00:00:00Z",
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(transaction.ValidationError, match="targetConfigSha256"):
        transaction.commit_transaction(
            api,
            journal_path=journal_path,
            lock_path=lock_path,
            evidence_path=committed_evidence(tmp_path),
            external_probe_receipt=wrong_receipt_path,
        )
    assert journal_path.exists()

    receipt_path = tmp_path / "probe.json"
    receipt_path.write_text(
        json.dumps(
            {
                "schema": transaction.EXTERNAL_PROBE_SCHEMA,
                "accountId": applied["accountId"],
                "tunnelId": applied["tunnelId"],
                "targetConfigSha256": applied["targetConfigSha256"],
                "targetVersion": applied["targetVersion"],
                "connectorIds": ["connector-without-version"],
                "generationId": GENERATION_ID,
                "observations": probe_observations(),
                "observedAt": "2026-07-24T00:00:00Z",
            }
        ),
        encoding="utf-8",
    )
    committed = transaction.commit_transaction(
        api,
        journal_path=journal_path,
        lock_path=lock_path,
        evidence_path=committed_evidence(tmp_path),
        external_probe_receipt=receipt_path,
    )
    assert committed["phase"] == "committed"
    assert committed["externalProbeReceiptSha256"]
    assert committed["priorResponse"]
    assert committed["appliedResponse"]
    assert committed["rollbackResponse"] is None
    assert not journal_path.exists()
    assert transaction.load_journal(committed_evidence(tmp_path)) == committed
    assert stat.S_IMODE(committed_evidence(tmp_path).stat().st_mode) == 0o600
    put_count = len(api.put_calls)
    retried = transaction.commit_transaction(
        api,
        journal_path=journal_path,
        lock_path=lock_path,
        evidence_path=committed_evidence(tmp_path),
    )
    assert retried == committed
    assert len(api.put_calls) == put_count


@pytest.mark.parametrize(
    ("field", "value", "expected"),
    [
        (
            "endpoint",
            PROBE_ENDPOINT.replace("chummer.run", "www.chummer.run"),
            r"observation\[0\] endpoint mismatch",
        ),
        ("httpStatus", 204, r"observation\[0\].*HTTP 200"),
        ("bodySha256", "b" * 64, r"observation\[0\] body digest mismatch"),
        (
            "generationId",
            "g-20260724T000001Z-fedcba9876543210",
            "generationId mismatch",
        ),
        ("anonymous", False, r"observation\[0\].*strictly anonymous"),
    ],
)
def test_external_probe_is_strictly_bound_to_anonymous_generation_observation(
    tmp_path: Path,
    field: str,
    value: object,
    expected: str,
) -> None:
    api = FakeApi(connector_versions={"connector-without-version": None})
    journal_path, lock_path, _ = capture(tmp_path, api)
    applied = apply(api, journal_path, lock_path)
    receipt = {
        "schema": transaction.EXTERNAL_PROBE_SCHEMA,
        "accountId": applied["accountId"],
        "tunnelId": applied["tunnelId"],
        "targetConfigSha256": applied["targetConfigSha256"],
        "targetVersion": applied["targetVersion"],
        "connectorIds": ["connector-without-version"],
        "generationId": GENERATION_ID,
        "observations": probe_observations(),
        "observedAt": "2026-07-24T00:00:00Z",
    }
    if field == "generationId":
        receipt[field] = value
    else:
        receipt["observations"][0][field] = value
    receipt_path = tmp_path / "tampered-probe.json"
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")

    with pytest.raises(transaction.ValidationError, match=expected):
        transaction.commit_transaction(
            api,
            journal_path=journal_path,
            lock_path=lock_path,
            evidence_path=committed_evidence(tmp_path),
            external_probe_receipt=receipt_path,
        )

    assert journal_path.exists()
    assert not committed_evidence(tmp_path).exists()


def test_rollback_restores_exact_prior_config_and_removes_journal(
    tmp_path: Path,
) -> None:
    api = FakeApi()
    journal_path, lock_path, captured = capture(tmp_path, api)
    apply(api, journal_path, lock_path)

    rolled_back = transaction.rollback_transaction(
        api,
        journal_path=journal_path,
        lock_path=lock_path,
        evidence_path=rollback_evidence(tmp_path),
        attempts=2,
        interval_seconds=0,
        sleep_fn=lambda _: None,
    )

    assert rolled_back["phase"] == "rolled-back"
    assert api.config == captured["priorConfig"]
    assert api.put_calls[-1] == captured["priorConfig"]
    assert not journal_path.exists()
    assert transaction.load_journal(rollback_evidence(tmp_path)) == rolled_back
    assert rolled_back["appliedResponse"]
    assert rolled_back["rollbackResponse"]
    assert stat.S_IMODE(rollback_evidence(tmp_path).stat().st_mode) == 0o600
    put_count = len(api.put_calls)
    retried = transaction.rollback_transaction(
        api,
        journal_path=journal_path,
        lock_path=lock_path,
        evidence_path=rollback_evidence(tmp_path),
    )
    assert retried == rolled_back
    assert len(api.put_calls) == put_count


def test_rollback_accepts_prior_already_restored_without_another_put(
    tmp_path: Path,
) -> None:
    api = FakeApi()
    journal_path, lock_path, captured = capture(tmp_path, api)
    apply(api, journal_path, lock_path)
    api.config = copy.deepcopy(captured["priorConfig"])
    api.version += 1
    put_count = len(api.put_calls)

    transaction.rollback_transaction(
        api,
        journal_path=journal_path,
        lock_path=lock_path,
        evidence_path=rollback_evidence(tmp_path),
    )

    assert len(api.put_calls) == put_count
    assert not journal_path.exists()
    assert rollback_evidence(tmp_path).exists()


def test_rollback_recovers_when_restore_put_response_is_lost(
    tmp_path: Path,
) -> None:
    api = FakeApi()
    journal_path, lock_path, captured = capture(tmp_path, api)
    apply(api, journal_path, lock_path)
    api.lose_next_put_response = True

    transaction.rollback_transaction(
        api,
        journal_path=journal_path,
        lock_path=lock_path,
        evidence_path=rollback_evidence(tmp_path),
        attempts=2,
        interval_seconds=0,
        sleep_fn=lambda _: None,
    )

    assert api.config == captured["priorConfig"]
    assert not journal_path.exists()
    assert rollback_evidence(tmp_path).exists()


def test_rollback_refuses_unrelated_concurrent_edit_and_retains_journal(
    tmp_path: Path,
) -> None:
    api = FakeApi()
    journal_path, lock_path, _ = capture(tmp_path, api)
    apply(api, journal_path, lock_path)
    api.config["ingress"].insert(
        0, {"hostname": "concurrent.example", "service": "http://other:80"}
    )
    api.version += 1
    concurrent = copy.deepcopy(api.config)
    put_count = len(api.put_calls)

    with pytest.raises(transaction.DriftError, match="neither target nor prior"):
        transaction.rollback_transaction(
            api,
            journal_path=journal_path,
            lock_path=lock_path,
            evidence_path=rollback_evidence(tmp_path),
        )

    assert api.config == concurrent
    assert len(api.put_calls) == put_count
    assert journal_path.exists()


def test_commit_rechecks_exact_target_and_refuses_version_drift(
    tmp_path: Path,
) -> None:
    api = FakeApi()
    journal_path, lock_path, _ = capture(tmp_path, api)
    apply(api, journal_path, lock_path)
    api.version += 1

    with pytest.raises(transaction.DriftError, match="drifted"):
        transaction.commit_transaction(
            api,
            journal_path=journal_path,
            lock_path=lock_path,
            evidence_path=committed_evidence(tmp_path),
        )

    assert journal_path.exists()


def test_bearer_is_preferred_and_legacy_global_key_requires_explicit_opt_in() -> None:
    environment = {
        "TOKEN": "bearer-secret",
        "EMAIL": "operator@example.test",
        "GLOBAL": "global-key-secret",
    }
    assert transaction.resolve_auth_headers(
        environment,
        api_token_env="TOKEN",
        allow_legacy_global_key_auth=True,
        legacy_email_env="EMAIL",
        legacy_global_key_env="GLOBAL",
    ) == {"Authorization": "Bearer bearer-secret"}

    with pytest.raises(transaction.ValidationError, match="explicit opt-in"):
        transaction.resolve_auth_headers(
            {"EMAIL": environment["EMAIL"], "GLOBAL": environment["GLOBAL"]},
            api_token_env="TOKEN",
            allow_legacy_global_key_auth=False,
            legacy_email_env="EMAIL",
            legacy_global_key_env="GLOBAL",
        )

    assert transaction.resolve_auth_headers(
        {"EMAIL": environment["EMAIL"], "GLOBAL": environment["GLOBAL"]},
        api_token_env="TOKEN",
        allow_legacy_global_key_auth=True,
        legacy_email_env="EMAIL",
        legacy_global_key_env="GLOBAL",
    ) == {
        "X-Auth-Email": "operator@example.test",
        "X-Auth-Key": "global-key-secret",
    }


def test_api_credentials_are_never_persisted_in_transaction_journal(
    tmp_path: Path,
) -> None:
    token = "bearer-super-secret"
    email = "operator-secret@example.test"
    global_key = "legacy-super-secret"
    transaction.resolve_auth_headers(
        {"TOKEN": token, "EMAIL": email, "GLOBAL": global_key},
        api_token_env="TOKEN",
        allow_legacy_global_key_auth=True,
        legacy_email_env="EMAIL",
        legacy_global_key_env="GLOBAL",
    )
    api = FakeApi()
    journal_path, _, _ = capture(tmp_path, api)
    raw = journal_path.read_text(encoding="utf-8")

    assert token not in raw
    assert email not in raw
    assert global_key not in raw
    assert "Authorization" not in raw
    assert "X-Auth-Key" not in raw

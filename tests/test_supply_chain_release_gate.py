from __future__ import annotations

import codecs
import importlib.util
import hashlib
import json
import os
import shlex
import subprocess
import sys
import time
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import pytest


SCRIPT = Path("/docker/chummercomplete/scripts/release/verify_supply_chain_evidence.py")
PROVENANCE_SCRIPT = Path("/docker/chummercomplete/scripts/release/materialize_build_provenance.py")
COLLECTOR_SCRIPT = Path("/docker/chummercomplete/scripts/release/collect_build_provenance.py")
RELEASE_READY_MATERIALIZER = Path(
    "/docker/chummercomplete/chummer.run-services/scripts/materialize_release_ready_receipt.py"
)
SPEC = importlib.util.spec_from_file_location("verify_supply_chain_evidence", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)
COLLECTOR_SPEC = importlib.util.spec_from_file_location("collect_build_provenance", COLLECTOR_SCRIPT)
assert COLLECTOR_SPEC is not None and COLLECTOR_SPEC.loader is not None
COLLECTOR = importlib.util.module_from_spec(COLLECTOR_SPEC)
sys.modules[COLLECTOR_SPEC.name] = COLLECTOR
COLLECTOR_SPEC.loader.exec_module(COLLECTOR)


def load_release_ready_materializer():
    name = "release_ready_materializer_for_supply_chain_test"
    spec = importlib.util.spec_from_file_location(name, RELEASE_READY_MATERIALIZER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def init_repo(path: Path) -> None:
    subprocess.run(["git", "init", "-q", str(path)], check=True)
    subprocess.run(["git", "-C", str(path), "config", "user.email", "test@example.invalid"], check=True)
    subprocess.run(["git", "-C", str(path), "config", "user.name", "Supply Chain Test"], check=True)


def commit_all(path: Path) -> None:
    subprocess.run(["git", "-C", str(path), "add", "."], check=True)
    subprocess.run(["git", "-C", str(path), "commit", "-qm", "fixture"], check=True)


def assets_payload(project_path: Path, packages: dict[str, tuple[str, dict[str, str]]]) -> dict[str, object]:
    libraries: dict[str, object] = {}
    target_libraries: dict[str, object] = {}
    for package_key, (sha512, dependencies) in packages.items():
        libraries[package_key] = {"type": "package", "sha512": sha512, "path": package_key.lower()}
        target_libraries[package_key] = {"type": "package", "dependencies": dependencies}
    return {
        "version": 3,
        "targets": {"net10.0": target_libraries},
        "libraries": libraries,
        "project": {
            "version": "1.2.3",
            "restore": {"projectPath": str(project_path)},
            "frameworks": {"net10.0": {}},
        },
    }


def make_target(tmp_path: Path, target_id: str = "fixture") -> tuple[object, dict[str, object]]:
    repo = tmp_path / "repo"
    project = repo / "App" / "App.csproj"
    assets = project.parent / "obj" / "project.assets.json"
    assets.parent.mkdir(parents=True)
    project.write_text("<Project Sdk=\"Microsoft.NET.Sdk\" />\n", encoding="utf-8")
    sha512 = __import__("base64").b64encode(bytes(range(64))).decode("ascii")
    payload = assets_payload(
        project,
        {
            "Example.Root/2.0.0": (sha512, {"Example.Child": "1.0.0"}),
            "Example.Child/1.0.0": (sha512, {}),
        },
    )
    assets.write_text(json.dumps(payload), encoding="utf-8")
    target = MODULE.ProjectTarget(
        target_id, "fixture", "chummer-presentation", repo, project
    )
    return target, payload


def test_secret_scan_detects_provider_token_without_leaking_value(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    init_repo(repo)
    secret = "github_pat_" + "A" * 48
    (repo / "settings.json").write_text(json.dumps({"token": secret}), encoding="utf-8")
    commit_all(repo)

    result = MODULE.scan_repository_for_secrets(repo)
    serialized = json.dumps(result)

    assert result["status"] == "fail"
    assert result["findings"][0]["rule_id"] == "github_token"
    assert result["findings"][0]["match"] == "[REDACTED]"
    assert secret not in serialized


def test_secret_scan_accepts_empty_example_configuration(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    init_repo(repo)
    (repo / ".env.example").write_text("API_KEY=\nPASSWORD=changeme\n", encoding="utf-8")
    commit_all(repo)

    result = MODULE.scan_repository_for_secrets(repo)

    assert result["status"] == "pass"
    assert result["findings"] == []


@pytest.mark.parametrize(
    ("relative_path", "content", "expected_rule"),
    [
        (
            "signing.pem",
            "-----BEGIN " + "ENCRYPTED PRIVATE KEY-----\nfixture\n-----END "
            + "ENCRYPTED PRIVATE KEY-----\n",
            "private_key",
        ),
        (
            "signing.asc",
            "-----BEGIN " + "PGP PRIVATE KEY BLOCK-----\nfixture\n-----END "
            + "PGP PRIVATE KEY BLOCK-----\n",
            "pgp_private_key",
        ),
        (".env.production", "PUBLIC_SETTING=enabled\n", "tracked_sensitive_file"),
        ("release-signing.jks", b"\x00fixture-binary-key-container", "tracked_sensitive_file"),
        (
            "runtime-google.json",
            json.dumps(
                {
                    "type": "service_" + "account",
                    "client_email": "fixture@example.invalid",
                    "token_uri": "https://example.invalid/token",
                }
            ),
            "service_account_json",
        ),
        (
            "headers.json",
            json.dumps({"Authorization": "Bearer " + "B" * 40}),
            "authorization_bearer_credential",
        ),
        ("release.json", json.dumps({"access_token": "A" * 40}), "literal_secret_assignment"),
        ("release.yaml", "refresh_token: " + "R" * 40 + "\n", "literal_secret_assignment"),
        (
            "release.toml",
            'connection_string = "Server=db;User Id=runner;Password=' + "P" * 24 + '"\n',
            "literal_secret_assignment",
        ),
    ],
)
def test_secret_scan_v2_fails_closed_for_release_credential_shapes(
    tmp_path: Path,
    relative_path: str,
    content: str | bytes,
    expected_rule: str,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    init_repo(repo)
    path = repo / relative_path
    if isinstance(content, bytes):
        path.write_bytes(content)
    else:
        path.write_text(content, encoding="utf-8")
    commit_all(repo)

    result = MODULE.secret_scan([repo])
    serialized = json.dumps(result)
    findings = result["repositories"][0]["findings"]

    assert MODULE.SECRET_SCAN_ENGINE.endswith(".v2")
    assert result["engine"] == MODULE.SECRET_SCAN_ENGINE
    assert result["scope"] == "git_committed_object_tree"
    assert result["status"] == "fail"
    assert expected_rule in {finding["rule_id"] for finding in findings}
    assert all(finding["match"] == "[REDACTED]" for finding in findings)
    if isinstance(content, str):
        assert content not in serialized
    else:
        assert content.hex() not in serialized


def test_secret_scan_rejects_concrete_secret_in_example_configuration(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    init_repo(repo)
    secret = "S" * 40
    (repo / ".env.example").write_text(f"API_KEY={secret}\n", encoding="utf-8")
    commit_all(repo)

    result = MODULE.secret_scan([repo])
    serialized = json.dumps(result)

    assert result["status"] == "fail"
    assert result["repositories"][0]["findings"][0]["rule_id"] == "literal_secret_assignment"
    assert secret not in serialized


@pytest.mark.parametrize(
    "secret",
    [
        "test-" + "A" * 40,
        "sample-prod-" + "B" * 40,
    ],
)
def test_secret_scan_rejects_real_looking_test_prefixed_configuration_secret(
    tmp_path: Path,
    secret: str,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    init_repo(repo)
    (repo / "settings.json").write_text(
        json.dumps({"api_key": secret}), encoding="utf-8"
    )
    commit_all(repo)

    result = MODULE.scan_repository_for_secrets(repo)

    assert result["status"] == "fail"
    assert result["findings"][0]["rule_id"] == "literal_secret_assignment"
    assert secret not in json.dumps(result)


def test_secret_scan_streams_large_benign_generated_configuration(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(MODULE, "TEXT_SCAN_MAX_BYTES", 64)
    monkeypatch.setattr(MODULE, "STREAM_SCAN_CHUNK_BYTES", 32)
    repo = tmp_path / "repo"
    repo.mkdir()
    init_repo(repo)
    (repo / "inventory.generated.json").write_text(
        json.dumps({"items": ["public-fixture"] * 20}),
        encoding="utf-8",
    )
    commit_all(repo)

    result = MODULE.scan_repository_for_secrets(repo)

    assert result["status"] == "pass"
    assert result["findings"] == []
    assert result["skipped_binary_or_large_files"] == 1


def test_secret_scan_streams_large_configuration_and_redacts_finding(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(MODULE, "TEXT_SCAN_MAX_BYTES", 64)
    monkeypatch.setattr(MODULE, "STREAM_SCAN_CHUNK_BYTES", 32)
    monkeypatch.setattr(MODULE, "STREAM_SCAN_OVERLAP_BYTES", 128)
    repo = tmp_path / "repo"
    repo.mkdir()
    init_repo(repo)
    secret = "Z" * 40
    (repo / "inventory.generated.json").write_text(
        json.dumps({"padding": "x" * 50, "access_token": secret}),
        encoding="utf-8",
    )
    commit_all(repo)

    result = MODULE.scan_repository_for_secrets(repo)
    serialized = json.dumps(result)

    assert result["status"] == "fail"
    assert result["findings"][0]["rule_id"] == "literal_secret_assignment"
    assert result["findings"][0]["match"] == "[REDACTED]"
    assert secret not in serialized


@pytest.mark.parametrize(
    "sentinel",
    [
        "internal-token",
        "local-prompt-foundry-token",
        "local-rule-ghost-token",
    ],
)
def test_secret_scan_allows_reviewed_symbolic_bearer_only_in_test_fixture(
    tmp_path: Path,
    sentinel: str,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    init_repo(repo)
    fixture = repo / "Tests" / "AuthenticationTests.cs"
    fixture.parent.mkdir()
    fixture.write_text(
        f'const string Authorization = "Bearer {sentinel}";\n',
        encoding="utf-8",
    )
    commit_all(repo)

    result = MODULE.scan_repository_for_secrets(repo)

    assert result["status"] == "pass"
    assert result["findings"] == []


def test_secret_scan_rejects_real_looking_test_prefixed_bearer_in_fixture(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    init_repo(repo)
    secret = "test-internal-token-" + "A" * 32
    fixture = repo / "Tests" / "AuthenticationTests.cs"
    fixture.parent.mkdir()
    fixture.write_text(
        f'const string Authorization = "Bearer {secret}";\n',
        encoding="utf-8",
    )
    commit_all(repo)

    result = MODULE.scan_repository_for_secrets(repo)

    assert result["status"] == "fail"
    assert result["findings"][0]["rule_id"] == "authorization_bearer_credential"
    assert secret not in json.dumps(result)


def test_secret_scan_archives_captured_commit_instead_of_symbolic_head(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    init_repo(repo)
    (repo / "README.md").write_text("clean\n", encoding="utf-8")
    commit_all(repo)
    commit, tree, _ = MODULE.git_revision(repo)
    real_popen = MODULE.subprocess.Popen
    commands: list[list[str]] = []

    def recording_popen(command: list[str], **kwargs: object):
        commands.append(command)
        return real_popen(command, **kwargs)

    monkeypatch.setattr(MODULE.subprocess, "Popen", recording_popen)

    result = MODULE.scan_repository_for_secrets(
        repo, expected_commit=commit, expected_tree=tree
    )

    assert result["status"] == "pass"
    archive_command = next(command for command in commands if "archive" in command)
    assert archive_command[-1] == commit
    assert archive_command[-1] != "HEAD"


def test_secret_scan_fails_when_repository_identity_moves_during_scan(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    init_repo(repo)
    (repo / "README.md").write_text("clean\n", encoding="utf-8")
    commit_all(repo)
    commit, tree, dirty = MODULE.git_revision(repo)
    revisions = iter(
        [
            (commit, tree, dirty),
            ("f" * len(commit), "e" * len(tree), False),
        ]
    )
    monkeypatch.setattr(MODULE, "git_revision", lambda _root: next(revisions))

    result = MODULE.scan_repository_for_secrets(repo)

    assert result["status"] == "fail"
    assert result["reason"] == "repository identity changed during the committed-tree scan"


@pytest.mark.parametrize(
    ("constant", "value"),
    [
        ("SECRET_SCAN_MAX_TRACKED_FILES", 0),
        ("SECRET_SCAN_MAX_ARCHIVE_BYTES", 0),
        ("SECRET_SCAN_MAX_ELAPSED_SECONDS", -1),
    ],
)
def test_secret_scan_fails_closed_when_resource_ceiling_is_exceeded(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    constant: str,
    value: int,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    init_repo(repo)
    (repo / "README.md").write_text("clean\n", encoding="utf-8")
    commit_all(repo)
    monkeypatch.setattr(MODULE, constant, value)

    result = MODULE.scan_repository_for_secrets(repo)

    assert result["status"] == "fail"
    assert result["reason"].endswith("SecretScanLimitExceeded")


@pytest.mark.parametrize(
    ("constant", "value"),
    [
        ("SECRET_SCAN_MAX_TRACKED_FILES", 1),
        ("SECRET_SCAN_MAX_ARCHIVE_BYTES", len("clean\n")),
    ],
)
def test_multi_repository_secret_scan_enforces_aggregate_resource_ceiling(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    constant: str,
    value: int,
) -> None:
    repositories: list[Path] = []
    for index in range(2):
        repo = tmp_path / f"repo-{index}"
        repo.mkdir()
        init_repo(repo)
        (repo / "README.md").write_text("clean\n", encoding="utf-8")
        commit_all(repo)
        repositories.append(repo)
    monkeypatch.setattr(MODULE, constant, value)

    result = MODULE.secret_scan(repositories)

    assert result["status"] == "fail"
    assert result["repositories"][0]["status"] == "pass"
    assert result["repositories"][1]["status"] == "fail"
    assert result["repositories"][1]["reason"].endswith(
        "SecretScanLimitExceeded"
    )


def test_secret_scan_rejects_symbolic_bearer_label_outside_test_fixture(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    init_repo(repo)
    source = repo / "Authentication.cs"
    source.write_text(
        'const string Authorization = "Bearer internal-token";\n',
        encoding="utf-8",
    )
    commit_all(repo)

    result = MODULE.scan_repository_for_secrets(repo)

    assert result["status"] == "fail"
    assert result["findings"][0]["rule_id"] == "authorization_bearer_credential"


def test_secret_scan_ignores_incomplete_private_key_markers_in_binary_tool(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    init_repo(repo)
    marker = (
        b"MZ\x00https://fixture:password@example.invalid\x00"
        + b"-----BEGIN "
        + b"PRIVATE KEY-----\x00marker-only\x00-----END "
        + b"PRIVATE KEY-----"
    )
    (repo / "wkhtmltopdf.exe").write_bytes(marker)
    commit_all(repo)

    result = MODULE.scan_repository_for_secrets(repo)

    assert result["status"] == "pass"
    assert result["findings"] == []


def test_secret_scan_detects_complete_private_key_embedded_in_binary_resource(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    init_repo(repo)
    body = __import__("base64").b64encode(b"binary-private-key-fixture" * 8)
    embedded = (
        b"resource-prefix\x00"
        + b"-----BEGIN "
        + b"PRIVATE KEY-----\n"
        + body
        + b"\n-----END "
        + b"PRIVATE KEY-----\x00resource-suffix"
    )
    (repo / "embedded-resource.bin").write_bytes(embedded)
    commit_all(repo)

    result = MODULE.scan_repository_for_secrets(repo)
    serialized = json.dumps(result)

    assert result["status"] == "fail"
    assert result["findings"][0]["rule_id"] == "private_key"
    assert result["findings"][0]["match"] == "[REDACTED]"
    assert body.decode("ascii") not in serialized


@pytest.mark.parametrize(
    ("encoding", "bom"),
    [
        pytest.param("utf-8", codecs.BOM_UTF8, id="utf8-bom"),
        pytest.param("utf-16-le", codecs.BOM_UTF16_LE, id="utf16-le-bom"),
        pytest.param("utf-16-be", codecs.BOM_UTF16_BE, id="utf16-be-bom"),
        pytest.param("utf-16-le", b"", id="utf16-le-bomless"),
        pytest.param("utf-16-be", b"", id="utf16-be-bomless"),
    ],
)
def test_secret_scan_decodes_unicode_configuration_before_scanning(
    tmp_path: Path,
    encoding: str,
    bom: bytes,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    init_repo(repo)
    secret = "U" * 40
    payload = json.dumps({"access_token": secret})
    (repo / "settings.json").write_bytes(bom + payload.encode(encoding))
    commit_all(repo)

    result = MODULE.scan_repository_for_secrets(repo)
    serialized = json.dumps(result)

    assert result["status"] == "fail"
    assert "literal_secret_assignment" in {
        finding["rule_id"] for finding in result["findings"]
    }
    assert all(finding["match"] == "[REDACTED]" for finding in result["findings"])
    assert secret not in serialized


def test_secret_scan_streams_utf16_configuration_with_same_v2_rules(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(MODULE, "TEXT_SCAN_MAX_BYTES", 64)
    monkeypatch.setattr(MODULE, "STREAM_SCAN_CHUNK_BYTES", 32)
    repo = tmp_path / "repo"
    repo.mkdir()
    init_repo(repo)
    secret = "L" * 40
    payload = json.dumps({"padding": "x" * 100, "refresh_token": secret})
    (repo / "settings.json").write_bytes(
        codecs.BOM_UTF16_LE + payload.encode("utf-16-le")
    )
    commit_all(repo)

    result = MODULE.scan_repository_for_secrets(repo)
    serialized = json.dumps(result)

    assert result["status"] == "fail"
    assert "literal_secret_assignment" in {
        finding["rule_id"] for finding in result["findings"]
    }
    assert secret not in serialized


def test_secret_scan_fails_closed_for_unrecognized_config_encoding_but_not_binary(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    init_repo(repo)
    hidden = "opaque-credential-material"
    suspicious_bytes = b"MZ\x00\x01\x02" + hidden.encode("ascii") + b"\x00\xff"
    (repo / "settings.json").write_bytes(suspicious_bytes)
    (repo / "System.Text.Json.dll").write_bytes(suspicious_bytes)
    commit_all(repo)

    result = MODULE.scan_repository_for_secrets(repo)
    serialized = json.dumps(result)

    assert result["status"] == "fail"
    assert [finding["path"] for finding in result["findings"]] == ["settings.json"]
    assert result["findings"][0]["rule_id"] == "suspicious_text_config_encoding"
    assert result["findings"][0]["match"] == "[REDACTED]"
    assert hidden not in serialized


def test_dotnet_audit_parser_surfaces_direct_and_transitive_vulnerabilities() -> None:
    payload = {
        "version": 1,
        "projects": [
            {
                "path": "/tmp/App.csproj",
                "frameworks": [
                    {
                        "framework": "net10.0",
                        "topLevelPackages": [
                            {
                                "id": "Direct.Package",
                                "resolvedVersion": "1.0.0",
                                "vulnerabilities": [{"severity": "high", "advisoryurl": "https://example.invalid/CVE-1"}],
                            }
                        ],
                        "transitivePackages": [
                            {
                                "id": "Child.Package",
                                "resolvedVersion": "2.0.0",
                                "vulnerabilities": [{"severity": "moderate", "advisoryUrl": "https://example.invalid/CVE-2"}],
                            }
                        ],
                    }
                ],
            }
        ],
    }

    vulnerabilities, error = MODULE.parse_dotnet_audit_output(json.dumps(payload))

    assert error is None
    assert [item["dependency_class"] for item in vulnerabilities] == ["direct", "transitive"]
    assert [item["package"] for item in vulnerabilities] == ["Direct.Package", "Child.Package"]


def test_cyclonedx_inventory_is_deterministic_and_contains_hashes_and_graph(tmp_path: Path) -> None:
    target, payload = make_target(tmp_path)

    first = MODULE.build_cyclonedx(target, payload, "a" * 64)
    second = MODULE.build_cyclonedx(target, payload, "a" * 64)

    assert first == second
    assert first["bomFormat"] == "CycloneDX"
    assert first["specVersion"] == "1.5"
    assert len(first["components"]) == 2
    assert all(component["hashes"][0]["alg"] == "SHA-512" for component in first["components"])
    root_dependency = first["dependencies"][0]
    assert len(root_dependency["dependsOn"]) == 2

    relocated = json.loads(json.dumps(payload))
    relocated["project"]["restore"]["projectPath"] = "/different/build/root/App.csproj"
    assert MODULE.dependency_inventory_sha256(payload) == MODULE.dependency_inventory_sha256(relocated)
    assert MODULE.build_cyclonedx(
        target,
        relocated,
        MODULE.dependency_inventory_sha256(relocated),
    ) == MODULE.build_cyclonedx(
        target,
        payload,
        MODULE.dependency_inventory_sha256(payload),
    )


def test_materialize_sbom_fails_closed_when_restore_assets_are_missing(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    project = repo / "App" / "App.csproj"
    project.parent.mkdir(parents=True)
    project.write_text("<Project />", encoding="utf-8")
    target = MODULE.ProjectTarget("missing-assets", "fixture", "fixture", repo, project)

    result = MODULE.materialize_sboms([target], tmp_path / "sbom")

    assert result["status"] == "not_available"
    assert result["targets"][0]["status"] == "not_available"
    assert "restore assets are unavailable" in result["targets"][0]["reason"]


def test_provenance_missing_is_explicitly_not_available(monkeypatch, tmp_path: Path) -> None:
    target, _ = make_target(tmp_path)
    sbom = {"targets": [{"target_id": target.target_id, "status": "pass", "sha256": "b" * 64}]}
    monkeypatch.setattr(MODULE, "expected_shipped_artifacts", lambda *_: ([], []))
    monkeypatch.setattr(MODULE, "git_revision", lambda *_: ("c" * 40, "d" * 40, False))

    result = MODULE.verify_provenance(tmp_path, [target], sbom, tmp_path / "missing.json")

    assert result["status"] == "not_available"
    assert result["receipt_sha256"] == "not_available"
    assert result["assurance"] == "no provenance is synthesized by this verifier"
    assert "build provenance receipt is not available" in result["reason"]


def test_provenance_binds_artifact_source_tree_and_sbom(monkeypatch, tmp_path: Path) -> None:
    target, _ = make_target(tmp_path)
    artifact = {
        "artifact_id": "artifact-1",
        "sha256": "a" * 64,
        "target_id": target.target_id,
        "repository": target.repository,
        "kind": "fixture",
        "name": "artifact.bin",
    }
    sbom = {"targets": [{"target_id": target.target_id, "status": "pass", "sha256": "b" * 64}]}
    monkeypatch.setattr(MODULE, "expected_shipped_artifacts", lambda *_: ([artifact], []))
    monkeypatch.setattr(MODULE, "git_revision", lambda *_: ("c" * 40, "d" * 40, False))
    monkeypatch.setattr(
        MODULE,
        "verify_evidence_attestation",
        lambda *_args, **_kwargs: ({"status": "pass", "key_id": "fixture"}, []),
    )
    started_at = MODULE.utc_now()
    authority_nonce = "9" * 64
    invocation_state = {
        "state_contract_name": "chummer6.build_provenance_invocation_state.v1",
        "builder_id": "fixture-builder",
        "build_type": "fixture",
        "invocation_id": "fixture-1",
        "authority_nonce": authority_nonce,
        "started_at_utc": started_at,
        "source": {
            "repository": target.repository,
            "commit": "c" * 40,
            "tree": "d" * 40,
            "tracked_worktree_dirty": False,
            "worktree_dirty": False,
            "untracked_build_inputs_included": True,
        },
        "subject_declaration": {
            "artifact_id": "artifact-1",
            "artifact_kind": "fixture",
            "artifact_name": "artifact.bin",
            "target_id": target.target_id,
        },
        "sbom": {"sha256": "b" * 64},
        "build_tools": {
            "provenance_generator_sha256": "e" * 64,
            "supply_chain_verifier_sha256": "f" * 64,
        },
    }
    provenance = {
        "contract_name": MODULE.PROVENANCE_CONTRACT_NAME,
        "status": "pass",
        "builder_id": "fixture-builder",
        "build_type": "fixture",
        "invocation_id": "fixture-1",
        "authority_nonce": authority_nonce,
        "build_started_at_utc": started_at,
        "generated_at_utc": MODULE.utc_now(),
        "invocation": {
            "state_contract_name": "chummer6.build_provenance_invocation_state.v1",
            "state_sha256": MODULE.canonical_json_sha256(invocation_state),
            "state": invocation_state,
            "subject_declared_before_build": True,
        },
        "subjects": [
            {
                "artifact_id": "artifact-1",
                "artifact_kind": "fixture",
                "artifact_name": "artifact.bin",
                "artifact_sha256": "a" * 64,
                "target_id": target.target_id,
                "source_repository": target.repository,
                "source_commit": "c" * 40,
                "source_tree": "d" * 40,
                "source_tracked_worktree_dirty": False,
                "source_worktree_dirty": False,
                "source_untracked_build_inputs_included": True,
                "sbom_sha256": "b" * 64,
                "invocation_id": "fixture-1",
                "authority_nonce": authority_nonce,
                "produced_during_invocation": True,
            }
        ],
    }
    provenance_path = tmp_path / "provenance.json"
    provenance_path.write_text(json.dumps(provenance), encoding="utf-8")

    result = MODULE.verify_provenance(tmp_path, [target], sbom, provenance_path)

    assert result["status"] == "pass"
    assert result["failures"] == []
    assert result["receipt_sha256"] == hashlib.sha256(provenance_path.read_bytes()).hexdigest()

    provenance["generated_at_utc"] = "2000-01-01T00:00:00Z"
    provenance_path.write_text(json.dumps(provenance), encoding="utf-8")
    stale = MODULE.verify_provenance(tmp_path, [target], sbom, provenance_path)
    assert stale["status"] == "fail"
    assert stale["receipt_sha256"] == hashlib.sha256(provenance_path.read_bytes()).hexdigest()
    assert any("stale" in failure for failure in stale["failures"])


def test_failing_provenance_aggregate_is_not_described_as_passing(
    monkeypatch,
    tmp_path: Path,
) -> None:
    provenance_path = tmp_path / "BUILD_PROVENANCE.generated.json"
    provenance_path.write_text(
        json.dumps(
            {
                "contract_name": MODULE.PROVENANCE_CONTRACT_NAME,
                "receipt_kind": "aggregate",
                "collector_id": MODULE.PROVENANCE_COLLECTOR_ID,
                "generated_at_utc": "not_available",
                "status": "fail",
                "pass": False,
                "expected_subject_ids": [],
                "subjects": [],
                "invocations": [],
                "failures": ["fixture aggregate is incomplete"],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(MODULE, "expected_shipped_artifacts", lambda *_: ([], []))

    result = MODULE.verify_provenance(tmp_path, [], {"targets": []}, provenance_path)

    assert result["status"] == "fail"
    assert "build provenance aggregate records failures" in result["failures"]
    assert not any("passing build provenance" in failure for failure in result["failures"])


def fixture_source_material_arguments(target: object) -> list[str]:
    arguments: list[str] = []
    material_root = target.repo_root.parent / "fixture-source-materials"
    for repository in (
        "chummer-core-engine",
        "chummer.run-services",
        "chummer-ui-kit",
        "chummer-hub-registry",
        "chummer-media-factory",
        "chummer5a",
    ):
        root = material_root / repository
        if not (root / ".git").exists():
            root.mkdir(parents=True)
            init_repo(root)
            (root / "README.md").write_text(f"# {repository}\n", encoding="utf-8")
            commit_all(root)
        arguments.extend(["--source-material", f"{repository}={root}"])
    return arguments


def provenance_command(
    command: str,
    *,
    target: object,
    artifact: Path,
    state: Path,
    output: Path,
    sbom: Path,
    build_input: Path | None = None,
    invocation_id: str = "fixture-invocation",
    artifact_id: str = "fixture-artifact",
) -> list[str]:
    common = [
        sys.executable,
        str(PROVENANCE_SCRIPT),
        command,
        "--state",
        str(state),
        "--output",
        str(output),
        "--builder-id",
        "fixture-builder",
        "--build-type",
        "fixture-build",
        "--invocation-id",
        invocation_id,
    ]
    if command == "finalize":
        return common
    begin_command = [
        *common,
        "--source-repository",
        target.repository,
        "--source-repo-root",
        str(target.repo_root),
        *fixture_source_material_arguments(target),
        "--build-root",
        str(target.repo_root),
        "--target-id",
        target.target_id,
        "--project-path",
        str(target.project_path.relative_to(target.repo_root)),
        "--artifact-id",
        artifact_id,
        "--artifact-kind",
        "fixture",
        "--artifact-name",
        artifact.name,
        "--artifact-path",
        str(artifact),
        "--sbom-path",
        str(sbom),
    ]
    if build_input is not None:
        begin_command.extend(["--build-input", f"source_snapshot={build_input}"])
    return begin_command


def oci_provenance_command(
    command: str,
    *,
    target: object,
    image_name: str,
    docker_binary: Path,
    state: Path,
    output: Path,
    sbom: Path,
    invocation_id: str = "fixture-oci-invocation",
    artifact_id: str = "fixture-oci-artifact",
) -> list[str]:
    common = [
        sys.executable,
        str(PROVENANCE_SCRIPT),
        command,
        "--state",
        str(state),
        "--output",
        str(output),
        "--builder-id",
        "fixture-oci-builder",
        "--build-type",
        "fixture-oci-build",
        "--invocation-id",
        invocation_id,
    ]
    if command == "finalize":
        return common
    return [
        *common,
        "--source-repository",
        target.repository,
        "--source-repo-root",
        str(target.repo_root),
        *fixture_source_material_arguments(target),
        "--build-root",
        str(target.repo_root),
        "--target-id",
        target.target_id,
        "--project-path",
        str(target.project_path.relative_to(target.repo_root)),
        "--artifact-id",
        artifact_id,
        "--artifact-kind",
        "oci_image",
        "--artifact-name",
        image_name,
        "--artifact-image",
        image_name,
        "--docker-binary",
        str(docker_binary),
        "--sbom-path",
        str(sbom),
    ]


def fake_docker_binary(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    state = tmp_path / "fake-docker-state.json"
    binary = tmp_path / "fake-docker"
    binary.write_text(
        """#!/usr/bin/env python3
import json
import os
from pathlib import Path

payload = json.loads(Path(os.environ["FAKE_DOCKER_STATE"]).read_text(encoding="utf-8"))
print(json.dumps(payload))
""",
        encoding="utf-8",
    )
    binary.chmod(0o755)
    monkeypatch.setenv("FAKE_DOCKER_STATE", str(state))
    return binary, state


def materialize_invocation(
    *,
    target: object,
    root: Path,
    invocation_dir: Path,
    invocation_id: str,
    artifact_id: str,
    artifact: Path,
    artifact_bytes: bytes,
    sbom: Path,
) -> tuple[Path, dict[str, object]]:
    state = root / "states" / f"{invocation_id}.state.json"
    output = invocation_dir / f"{invocation_id}.json"
    begun = subprocess.run(
        provenance_command(
            "begin",
            target=target,
            artifact=artifact,
            state=state,
            output=output,
            sbom=sbom,
            invocation_id=invocation_id,
            artifact_id=artifact_id,
        ),
        text=True,
        capture_output=True,
        check=False,
    )
    assert begun.returncode == 0, begun.stderr
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_bytes(artifact_bytes)
    finalized = subprocess.run(
        provenance_command(
            "finalize",
            target=target,
            artifact=artifact,
            state=state,
            output=output,
            sbom=sbom,
            invocation_id=invocation_id,
            artifact_id=artifact_id,
        ),
        text=True,
        capture_output=True,
        check=False,
    )
    assert finalized.returncode == 0, finalized.stderr
    return output, json.loads(output.read_text(encoding="utf-8"))


def test_build_provenance_generator_binds_artifact_created_inside_invocation(monkeypatch, tmp_path: Path) -> None:
    target, _ = make_target(tmp_path)
    init_repo(target.repo_root)
    commit_all(target.repo_root)
    evidence = tmp_path / "evidence"
    artifact = tmp_path / "dist" / "artifact.bin"
    state = evidence / "state.json"
    output = evidence / "provenance.json"
    sbom = evidence / "sbom" / "fixture.cdx.json"

    begun = subprocess.run(
        provenance_command("begin", target=target, artifact=artifact, state=state, output=output, sbom=sbom),
        text=True,
        capture_output=True,
        check=False,
    )
    assert begun.returncode == 0, begun.stderr
    assert json.loads(output.read_text(encoding="utf-8"))["status"] == "in_progress"
    artifact.parent.mkdir(parents=True)
    artifact.write_bytes(b"artifact produced by fixture build")

    finalized = subprocess.run(
        provenance_command("finalize", target=target, artifact=artifact, state=state, output=output, sbom=sbom),
        text=True,
        capture_output=True,
        check=False,
    )
    assert finalized.returncode == 0, finalized.stderr
    receipt = json.loads(output.read_text(encoding="utf-8"))
    serialized_receipt = json.dumps(receipt, sort_keys=True)
    assert str(tmp_path) not in serialized_receipt
    assert "\\\\" not in serialized_receipt
    assert receipt["invocation"]["public_projection"] == "portable_path_references.v1"
    public_state = receipt["invocation"]["state"]
    assert public_state["source"]["repo_root"] == f"sources/{target.repository}"
    assert public_state["subject_declaration"]["artifact_path"] == f"files/{artifact.name}"
    assert public_state["sbom"]["path"] == f"proof/build-provenance/v1/sbom/{target.target_id}.cdx.json"
    subject = receipt["subjects"][0]
    assert receipt["contract_name"] == MODULE.PROVENANCE_CONTRACT_NAME
    assert receipt["status"] == "pass"
    assert subject["artifact_sha256"] == hashlib.sha256(artifact.read_bytes()).hexdigest()
    assert subject["sbom_sha256"] == hashlib.sha256(sbom.read_bytes()).hexdigest()
    assert subject["produced_during_invocation"] is True
    assert receipt["invocation"]["subject_declared_before_build"] is True

    expected_artifact = {
        "artifact_id": "fixture-artifact",
        "artifact_kind": "fixture",
        "kind": "fixture",
        "name": artifact.name,
        "sha256": subject["artifact_sha256"],
        "target_id": target.target_id,
        "repository": target.repository,
    }
    monkeypatch.setattr(MODULE, "expected_shipped_artifacts", lambda *_: ([expected_artifact], []))
    monkeypatch.setattr(
        MODULE,
        "git_revision",
        lambda *_: (subject["source_commit"], subject["source_tree"], False),
    )
    monkeypatch.setattr(
        MODULE,
        "verify_evidence_attestation",
        lambda *_args, **_kwargs: ({"status": "pass", "key_id": "fixture"}, []),
    )
    verified = MODULE.verify_provenance(
        tmp_path,
        [target],
        {"targets": [{"target_id": target.target_id, "status": "pass", "sha256": subject["sbom_sha256"]}]},
        output,
    )
    assert verified["status"] == "pass"
    assert verified["failures"] == []


def test_build_provenance_generator_binds_oci_image_id_created_inside_invocation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    target, _ = make_target(tmp_path)
    init_repo(target.repo_root)
    commit_all(target.repo_root)
    docker_binary, docker_state = fake_docker_binary(tmp_path, monkeypatch)
    image_name = "fixture/service:local"
    docker_state.write_text(
        json.dumps(
            {
                "Id": "sha256:" + "a" * 64,
                "Created": "2020-01-01T00:00:00Z",
                "Size": 100,
                "RepoTags": [image_name],
            }
        ),
        encoding="utf-8",
    )
    evidence = tmp_path / "evidence"
    state = evidence / "state.json"
    output = evidence / "provenance.json"
    sbom = evidence / "sbom" / "fixture.cdx.json"

    begun = subprocess.run(
        oci_provenance_command(
            "begin",
            target=target,
            image_name=image_name,
            docker_binary=docker_binary,
            state=state,
            output=output,
            sbom=sbom,
        ),
        text=True,
        capture_output=True,
        check=False,
    )
    assert begun.returncode == 0, begun.stderr
    docker_state.write_text(
        json.dumps(
            {
                "Id": "sha256:" + "b" * 64,
                "Created": datetime.now(UTC).isoformat(),
                "Size": 200,
                "RepoTags": [image_name],
            }
        ),
        encoding="utf-8",
    )

    finalized = subprocess.run(
        oci_provenance_command(
            "finalize",
            target=target,
            image_name=image_name,
            docker_binary=docker_binary,
            state=state,
            output=output,
            sbom=sbom,
        ),
        text=True,
        capture_output=True,
        check=False,
    )
    assert finalized.returncode == 0, finalized.stderr
    receipt = json.loads(output.read_text(encoding="utf-8"))
    subject = receipt["subjects"][0]
    assert receipt["status"] == "pass"
    assert subject["artifact_kind"] == "oci_image"
    assert subject["artifact_sha256"] == "b" * 64
    assert subject["artifact_size_bytes"] == 200
    assert receipt["invocation"]["state"]["subject_declaration"]["artifact_image"] == image_name
    assert receipt["invocation"]["state"]["build_tools"]["docker_binary"]["sha256"]
    assert receipt["invocation"]["state"]["build_tools"]["docker_binary"]["path"] == "tools/docker"
    assert str(tmp_path) not in json.dumps(receipt, sort_keys=True)

    subjects, structural_failures = MODULE.validate_invocation_provenance_payload(receipt)
    assert structural_failures == []
    assert MODULE.validate_provenance_subjects_against_expected(
        subjects,
        [
            {
                "artifact_id": "fixture-oci-artifact",
                "kind": "oci_image",
                "name": image_name,
                "sha256": "b" * 64,
                "target_id": target.target_id,
                "repository": target.repository,
            }
        ],
        {
            target.repository: {
                "commit": subject["source_commit"],
                "tree": subject["source_tree"],
            }
        },
        {target.target_id: subject["sbom_sha256"]},
    ) == []


def test_build_provenance_generator_rejects_unchanged_preexisting_oci_image(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    target, _ = make_target(tmp_path)
    init_repo(target.repo_root)
    commit_all(target.repo_root)
    docker_binary, docker_state = fake_docker_binary(tmp_path, monkeypatch)
    image_name = "fixture/service:local"
    docker_state.write_text(
        json.dumps(
            {
                "Id": "sha256:" + "a" * 64,
                "Created": datetime.now(UTC).isoformat(),
                "Size": 100,
                "RepoTags": [image_name],
            }
        ),
        encoding="utf-8",
    )
    evidence = tmp_path / "evidence"
    state = evidence / "state.json"
    output = evidence / "provenance.json"
    sbom = evidence / "sbom" / "fixture.cdx.json"
    begun = subprocess.run(
        oci_provenance_command(
            "begin",
            target=target,
            image_name=image_name,
            docker_binary=docker_binary,
            state=state,
            output=output,
            sbom=sbom,
        ),
        text=True,
        capture_output=True,
        check=False,
    )
    assert begun.returncode == 0, begun.stderr

    finalized = subprocess.run(
        oci_provenance_command(
            "finalize",
            target=target,
            image_name=image_name,
            docker_binary=docker_binary,
            state=state,
            output=output,
            sbom=sbom,
        ),
        text=True,
        capture_output=True,
        check=False,
    )
    assert finalized.returncode == 1
    receipt = json.loads(output.read_text(encoding="utf-8"))
    assert any("digest is unchanged" in failure for failure in receipt["failures"])


def test_build_provenance_generator_rejects_dirty_tracked_source(tmp_path: Path) -> None:
    target, _ = make_target(tmp_path)
    init_repo(target.repo_root)
    commit_all(target.repo_root)
    target.project_path.write_text("<Project><Dirty /></Project>\n", encoding="utf-8")
    artifact = tmp_path / "artifact.bin"
    state = tmp_path / "state.json"
    output = tmp_path / "provenance.json"
    sbom = tmp_path / "fixture.cdx.json"

    result = subprocess.run(
        provenance_command("begin", target=target, artifact=artifact, state=state, output=output, sbom=sbom),
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 1
    receipt = json.loads(output.read_text(encoding="utf-8"))
    assert receipt["status"] == "fail"
    assert any("tracked changes" in failure for failure in receipt["failures"])


def test_build_provenance_generator_rejects_unchanged_preexisting_artifact(tmp_path: Path) -> None:
    target, _ = make_target(tmp_path)
    init_repo(target.repo_root)
    commit_all(target.repo_root)
    artifact = tmp_path / "artifact.bin"
    artifact.write_bytes(b"stale artifact")
    state = tmp_path / "state.json"
    output = tmp_path / "provenance.json"
    sbom = tmp_path / "fixture.cdx.json"
    begun = subprocess.run(
        provenance_command("begin", target=target, artifact=artifact, state=state, output=output, sbom=sbom),
        text=True,
        capture_output=True,
        check=False,
    )
    assert begun.returncode == 0, begun.stderr

    finalized = subprocess.run(
        provenance_command("finalize", target=target, artifact=artifact, state=state, output=output, sbom=sbom),
        text=True,
        capture_output=True,
        check=False,
    )

    assert finalized.returncode == 1
    receipt = json.loads(output.read_text(encoding="utf-8"))
    assert receipt["status"] == "fail"
    assert any("not produced after" in failure or "unchanged" in failure for failure in receipt["failures"])


def test_build_provenance_generator_rejects_touched_preexisting_artifact(tmp_path: Path) -> None:
    target, _ = make_target(tmp_path)
    init_repo(target.repo_root)
    commit_all(target.repo_root)
    artifact = tmp_path / "artifact.bin"
    artifact.write_bytes(b"stale artifact")
    state = tmp_path / "state.json"
    output = tmp_path / "provenance.json"
    sbom = tmp_path / "fixture.cdx.json"
    begun = subprocess.run(
        provenance_command("begin", target=target, artifact=artifact, state=state, output=output, sbom=sbom),
        text=True,
        capture_output=True,
        check=False,
    )
    assert begun.returncode == 0, begun.stderr

    touched_ns = time.time_ns() + 1_000_000_000
    os.utime(artifact, ns=(touched_ns, touched_ns))
    finalized = subprocess.run(
        provenance_command("finalize", target=target, artifact=artifact, state=state, output=output, sbom=sbom),
        text=True,
        capture_output=True,
        check=False,
    )

    assert finalized.returncode == 1
    receipt = json.loads(output.read_text(encoding="utf-8"))
    assert receipt["status"] == "fail"
    assert any("identity and content are unchanged" in failure for failure in receipt["failures"])


def test_build_provenance_finalize_cannot_overwrite_another_invocation(tmp_path: Path) -> None:
    target, _ = make_target(tmp_path)
    init_repo(target.repo_root)
    commit_all(target.repo_root)
    artifact = tmp_path / "artifact.bin"
    state = tmp_path / "state.json"
    output = tmp_path / "provenance.json"
    sbom = tmp_path / "fixture.cdx.json"
    begun = subprocess.run(
        provenance_command("begin", target=target, artifact=artifact, state=state, output=output, sbom=sbom),
        text=True,
        capture_output=True,
        check=False,
    )
    assert begun.returncode == 0, begun.stderr
    other = json.loads(output.read_text(encoding="utf-8"))
    other["invocation_id"] = "newer-invocation"
    output.write_text(json.dumps(other), encoding="utf-8")
    artifact.write_bytes(b"artifact")

    finalized = subprocess.run(
        provenance_command("finalize", target=target, artifact=artifact, state=state, output=output, sbom=sbom),
        text=True,
        capture_output=True,
        check=False,
    )

    assert finalized.returncode == 1
    assert json.loads(output.read_text(encoding="utf-8"))["invocation_id"] == "newer-invocation"


def test_build_provenance_rejects_build_input_drift(tmp_path: Path) -> None:
    target, _ = make_target(tmp_path)
    init_repo(target.repo_root)
    commit_all(target.repo_root)
    artifact = tmp_path / "artifact.bin"
    state = tmp_path / "state.json"
    output = tmp_path / "provenance.json"
    sbom = tmp_path / "fixture.cdx.json"
    build_input = tmp_path / "source-snapshot.json"
    build_input.write_text('{"tree":"first"}\n', encoding="utf-8")
    begun = subprocess.run(
        provenance_command(
            "begin",
            target=target,
            artifact=artifact,
            state=state,
            output=output,
            sbom=sbom,
            build_input=build_input,
        ),
        text=True,
        capture_output=True,
        check=False,
    )
    assert begun.returncode == 0, begun.stderr
    artifact.write_bytes(b"artifact")
    build_input.write_text('{"tree":"changed"}\n', encoding="utf-8")

    finalized = subprocess.run(
        provenance_command("finalize", target=target, artifact=artifact, state=state, output=output, sbom=sbom),
        text=True,
        capture_output=True,
        check=False,
    )

    assert finalized.returncode == 1
    receipt = json.loads(output.read_text(encoding="utf-8"))
    assert any("build input changed" in failure for failure in receipt["failures"])


def test_collector_unions_central_and_public_mac_invocations_and_verifier_accepts_exact_set(
    monkeypatch,
    tmp_path: Path,
) -> None:
    target, _ = make_target(tmp_path)
    init_repo(target.repo_root)
    commit_all(target.repo_root)
    central_invocation_dir = tmp_path / "central" / "invocations"
    public_mac_invocation_dir = (
        tmp_path
        / "chummer.run-services"
        / "Chummer.Portal"
        / "downloads"
        / "proof"
        / "build-provenance"
        / "v1"
        / "invocations"
    )
    sbom_path = tmp_path / "sbom" / "fixture.cdx.json"
    first_path, first = materialize_invocation(
        target=target,
        root=tmp_path,
        invocation_dir=central_invocation_dir,
        invocation_id="fixture-linux",
        artifact_id="artifact-linux",
        artifact=tmp_path / "dist" / "linux.deb",
        artifact_bytes=b"linux artifact",
        sbom=sbom_path,
    )
    second_path, second = materialize_invocation(
        target=target,
        root=tmp_path,
        invocation_dir=public_mac_invocation_dir,
        invocation_id="fixture-mac",
        artifact_id="artifact-mac",
        artifact=tmp_path / "dist" / "mac.dmg",
        artifact_bytes=b"mac artifact",
        sbom=sbom_path,
    )
    first_subject = first["subjects"][0]
    second_subject = second["subjects"][0]

    now = datetime.now(UTC).replace(microsecond=0)
    started_at = (now - timedelta(minutes=30)).isoformat().replace("+00:00", "Z")
    older_generated_at = (now - timedelta(minutes=20)).astimezone(
        timezone(timedelta(hours=14))
    ).isoformat()
    newer_generated_at = (now - timedelta(minutes=10)).isoformat().replace("+00:00", "Z")
    for path, receipt, generated_at in (
        (first_path, first, older_generated_at),
        (second_path, second, newer_generated_at),
    ):
        receipt["build_started_at_utc"] = started_at
        receipt["invocation"]["state"]["started_at_utc"] = started_at
        receipt["invocation"]["state_sha256"] = MODULE.canonical_json_sha256(
            receipt["invocation"]["state"]
        )
        receipt["generated_at_utc"] = generated_at
        path.write_text(json.dumps(receipt), encoding="utf-8")
    artifacts = [
        {
            "artifact_id": "artifact-linux",
            "kind": "fixture",
            "name": "linux.deb",
            "sha256": first_subject["artifact_sha256"],
            "target_id": target.target_id,
            "repository": target.repository,
        },
        {
            "artifact_id": "artifact-mac",
            "kind": "fixture",
            "name": "mac.dmg",
            "sha256": second_subject["artifact_sha256"],
            "target_id": target.target_id,
            "repository": target.repository,
        },
    ]
    revisions = {
        target.repository: {
            "commit": first_subject["source_commit"],
            "tree": first_subject["source_tree"],
            "tracked_worktree_dirty": False,
        }
    }
    sbom_by_target = {target.target_id: first_subject["sbom_sha256"]}

    def reject_second_path_read(_path: Path) -> str:
        raise AssertionError("collector must hash the same captured bytes it parsed")

    monkeypatch.setattr(MODULE, "sha256_file", reject_second_path_read)

    aggregate, hard_failures, selected_ids = COLLECTOR.build_aggregate(
        support=MODULE,
        invocation_dir=[central_invocation_dir, public_mac_invocation_dir],
        artifacts=artifacts,
        revisions=revisions,
        sbom_by_target=sbom_by_target,
        discovery_failures=[],
        max_age_hours=168,
    )
    first_receipt_bytes = first_path.read_bytes()
    second_receipt_bytes = second_path.read_bytes()
    repeated, _, _ = COLLECTOR.build_aggregate(
        support=MODULE,
        invocation_dir=[central_invocation_dir, public_mac_invocation_dir],
        artifacts=artifacts,
        revisions=revisions,
        sbom_by_target=sbom_by_target,
        discovery_failures=[],
        max_age_hours=168,
    )

    assert hard_failures == []
    assert selected_ids == {"fixture-linux", "fixture-mac"}
    assert aggregate == repeated
    assert aggregate["status"] == "pass"
    assert aggregate["generated_at_utc"] == newer_generated_at
    assert [row["invocation_id"] for row in aggregate["invocations"]] == [
        "fixture-linux",
        "fixture-mac",
    ]
    assert first_path.read_bytes() == first_receipt_bytes
    assert second_path.read_bytes() == second_receipt_bytes

    aggregate_path = tmp_path / "BUILD_PROVENANCE.generated.json"
    MODULE.atomic_write_json(aggregate_path, aggregate)
    monkeypatch.setattr(MODULE, "expected_shipped_artifacts", lambda *_: (artifacts, []))
    monkeypatch.setattr(
        MODULE,
        "git_revision",
        lambda *_: (first_subject["source_commit"], first_subject["source_tree"], False),
    )
    monkeypatch.setattr(
        MODULE,
        "verify_evidence_attestation",
        lambda *_args, **_kwargs: ({"status": "pass", "key_id": "fixture"}, []),
    )
    verified = MODULE.verify_provenance(
        tmp_path,
        [target],
        {
            "targets": [
                {
                    "target_id": target.target_id,
                    "status": "pass",
                    "sha256": first_subject["sbom_sha256"],
                }
            ]
        },
        aggregate_path,
    )
    assert verified["status"] == "pass"
    assert verified["subject_count"] == 2
    assert verified["selected_invocation_count"] == 2


def test_collector_fails_closed_on_duplicate_invocation_id_across_roots(tmp_path: Path) -> None:
    target, _ = make_target(tmp_path)
    init_repo(target.repo_root)
    commit_all(target.repo_root)
    central_invocation_dir = tmp_path / "central" / "invocations"
    public_invocation_dir = tmp_path / "public" / "invocations"
    sbom_path = tmp_path / "sbom" / "fixture.cdx.json"
    receipt_path, receipt = materialize_invocation(
        target=target,
        root=tmp_path,
        invocation_dir=central_invocation_dir,
        invocation_id="duplicate-build",
        artifact_id="artifact-linux",
        artifact=tmp_path / "dist" / "linux.deb",
        artifact_bytes=b"linux artifact",
        sbom=sbom_path,
    )
    public_invocation_dir.mkdir(parents=True)
    duplicate_path = public_invocation_dir / receipt_path.name
    duplicate_path.write_bytes(receipt_path.read_bytes())
    subject = receipt["subjects"][0]

    aggregate, hard_failures, _ = COLLECTOR.build_aggregate(
        support=MODULE,
        invocation_dir=[central_invocation_dir, public_invocation_dir],
        artifacts=[
            {
                "artifact_id": "artifact-linux",
                "kind": "fixture",
                "name": "linux.deb",
                "sha256": subject["artifact_sha256"],
                "target_id": target.target_id,
                "repository": target.repository,
            }
        ],
        revisions={
            target.repository: {
                "commit": subject["source_commit"],
                "tree": subject["source_tree"],
                "tracked_worktree_dirty": False,
            }
        },
        sbom_by_target={target.target_id: subject["sbom_sha256"]},
        discovery_failures=[],
        max_age_hours=168,
    )

    assert aggregate["status"] == "fail"
    assert len(hard_failures) == 1
    assert hard_failures[0].startswith("duplicate invocation id duplicate-build:")
    assert str(receipt_path.resolve()) in hard_failures[0]
    assert str(duplicate_path.resolve()) in hard_failures[0]


def test_collector_fails_closed_without_fabricating_missing_subject(tmp_path: Path) -> None:
    target, _ = make_target(tmp_path)
    init_repo(target.repo_root)
    commit_all(target.repo_root)
    invocation_dir = tmp_path / "invocations"
    sbom_path = tmp_path / "sbom" / "fixture.cdx.json"
    _, receipt = materialize_invocation(
        target=target,
        root=tmp_path,
        invocation_dir=invocation_dir,
        invocation_id="fixture-linux",
        artifact_id="artifact-linux",
        artifact=tmp_path / "dist" / "linux.deb",
        artifact_bytes=b"linux artifact",
        sbom=sbom_path,
    )
    subject = receipt["subjects"][0]
    artifacts = [
        {
            "artifact_id": "artifact-linux",
            "kind": "fixture",
            "name": "linux.deb",
            "sha256": subject["artifact_sha256"],
            "target_id": target.target_id,
            "repository": target.repository,
        },
        {
            "artifact_id": "artifact-oci-missing",
            "kind": "oci_image",
            "name": "missing:local",
            "sha256": "a" * 64,
            "target_id": target.target_id,
            "repository": target.repository,
        },
    ]
    aggregate, hard_failures, _ = COLLECTOR.build_aggregate(
        support=MODULE,
        invocation_dir=invocation_dir,
        artifacts=artifacts,
        revisions={
            target.repository: {
                "commit": subject["source_commit"],
                "tree": subject["source_tree"],
                "tracked_worktree_dirty": False,
            }
        },
        sbom_by_target={target.target_id: subject["sbom_sha256"]},
        discovery_failures=[],
        max_age_hours=168,
    )

    assert hard_failures == []
    assert aggregate["status"] == "fail"
    assert aggregate["expected_subject_ids"] == ["artifact-linux", "artifact-oci-missing"]
    assert [item["artifact_id"] for item in aggregate["subjects"]] == ["artifact-linux"]
    assert "missing build provenance subject: artifact-oci-missing" in aggregate["failures"]


def test_collector_empty_input_is_deterministic(tmp_path: Path) -> None:
    central_invocation_dir = tmp_path / "central" / "invocations"
    optional_public_invocation_dir = tmp_path / "public" / "proof" / "invocations"
    arguments = {
        "support": MODULE,
        "invocation_dir": [central_invocation_dir, optional_public_invocation_dir],
        "artifacts": [
            {
                "artifact_id": "artifact-missing",
                "kind": "fixture",
                "name": "missing.bin",
                "sha256": "a" * 64,
                "target_id": "fixture-target",
                "repository": "fixture-repository",
            }
        ],
        "revisions": {
            "fixture-repository": {
                "commit": "b" * 40,
                "tree": "c" * 40,
                "tracked_worktree_dirty": False,
            }
        },
        "sbom_by_target": {"fixture-target": "d" * 64},
        "discovery_failures": [],
        "max_age_hours": 168,
    }

    first, first_hard_failures, _ = COLLECTOR.build_aggregate(**arguments)
    second, second_hard_failures, _ = COLLECTOR.build_aggregate(**arguments)

    assert first == second
    assert first_hard_failures == second_hard_failures == []
    assert first["generated_at_utc"] == "not_available"
    assert first["subjects"] == []
    assert first["failures"] == ["missing build provenance subject: artifact-missing"]
    assert not central_invocation_dir.exists()
    assert not optional_public_invocation_dir.exists()


def test_collector_rejects_non_utf8_receipt_without_crashing(tmp_path: Path) -> None:
    invocation_dir = tmp_path / "invocations"
    invocation_dir.mkdir()
    (invocation_dir / "broken.json").write_bytes(b"\xff\xfe\x00")

    aggregate, hard_failures, _ = COLLECTOR.build_aggregate(
        support=MODULE,
        invocation_dir=invocation_dir,
        artifacts=[
            {
                "artifact_id": "artifact-missing",
                "kind": "fixture",
                "name": "missing.bin",
                "sha256": "a" * 64,
                "target_id": "fixture-target",
                "repository": "fixture-repository",
            }
        ],
        revisions={
            "fixture-repository": {
                "commit": "b" * 40,
                "tree": "c" * 40,
                "tracked_worktree_dirty": False,
            }
        },
        sbom_by_target={"fixture-target": "d" * 64},
        discovery_failures=[],
        max_age_hours=168,
    )

    assert hard_failures == []
    assert aggregate["status"] == "fail"
    assert aggregate["rejected_receipts"][0]["invocation_id"] == "not_available"
    assert "missing build provenance subject: artifact-missing" in aggregate["failures"]


def test_collector_rejects_relaxed_freshness_ceiling() -> None:
    with pytest.raises(SystemExit):
        COLLECTOR.parse_args(["--max-age-hours", "169"])


def test_collector_accepts_repeatable_invocation_directories() -> None:
    args = COLLECTOR.parse_args(
        [
            "--invocation-dir",
            "/evidence/central/invocations",
            "--invocation-dir",
            "/downloads/proof/build-provenance/v1/invocations",
        ]
    )

    assert args.invocation_dir == [
        Path("/evidence/central/invocations"),
        Path("/downloads/proof/build-provenance/v1/invocations"),
    ]


def test_collector_defaults_to_central_and_canonical_public_invocation_directories(
    tmp_path: Path,
) -> None:
    invocation_dirs = COLLECTOR.default_invocation_dirs(tmp_path)

    assert invocation_dirs == [
        tmp_path / ".codex-studio" / "published" / "build-provenance" / "invocations",
        tmp_path
        / "chummer.run-services"
        / "Chummer.Portal"
        / "downloads"
        / "proof"
        / "build-provenance"
        / "v1"
        / "invocations",
    ]
    assert all(not invocation_dir.exists() for invocation_dir in invocation_dirs)


def test_collector_invalidates_prior_pass_before_discovery(monkeypatch, tmp_path: Path) -> None:
    output = tmp_path / "BUILD_PROVENANCE.generated.json"
    output.write_text(
        json.dumps({"contract_name": MODULE.PROVENANCE_CONTRACT_NAME, "status": "pass", "pass": True}),
        encoding="utf-8",
    )
    invocation_dir = tmp_path / "invocations"

    monkeypatch.setattr(COLLECTOR, "load_support", lambda _path: MODULE)

    def fail_discovery(_workspace_root: Path) -> list[object]:
        raise RuntimeError("simulated discovery failure")

    monkeypatch.setattr(MODULE, "default_targets", fail_discovery)

    with pytest.raises(RuntimeError, match="simulated discovery failure"):
        COLLECTOR.main(
            [
                "--workspace-root",
                str(tmp_path),
                "--invocation-dir",
                str(invocation_dir),
                "--output",
                str(output),
            ]
        )

    receipt = json.loads(output.read_text(encoding="utf-8"))
    assert receipt["status"] == "in_progress"
    assert receipt["pass"] is False
    assert receipt["failures"] == ["build provenance aggregation is incomplete"]


def test_invocation_receipt_is_immutable_after_finalize(tmp_path: Path) -> None:
    target, _ = make_target(tmp_path)
    init_repo(target.repo_root)
    commit_all(target.repo_root)
    invocation_dir = tmp_path / "invocations"
    sbom_path = tmp_path / "sbom" / "fixture.cdx.json"
    output, _ = materialize_invocation(
        target=target,
        root=tmp_path,
        invocation_dir=invocation_dir,
        invocation_id="immutable-build",
        artifact_id="immutable-artifact",
        artifact=tmp_path / "dist" / "artifact.bin",
        artifact_bytes=b"immutable artifact",
        sbom=sbom_path,
    )
    before = output.read_bytes()
    state = tmp_path / "states" / "immutable-build.state.json"

    repeated_begin = subprocess.run(
        provenance_command(
            "begin",
            target=target,
            artifact=tmp_path / "dist" / "artifact.bin",
            state=state,
            output=output,
            sbom=sbom_path,
            invocation_id="immutable-build",
            artifact_id="immutable-artifact",
        ),
        text=True,
        capture_output=True,
        check=False,
    )

    assert repeated_begin.returncode == 1
    assert output.read_bytes() == before

    state.unlink()
    repeated_finalize = subprocess.run(
        provenance_command(
            "finalize",
            target=target,
            artifact=tmp_path / "dist" / "artifact.bin",
            state=state,
            output=output,
            sbom=sbom_path,
            invocation_id="immutable-build",
            artifact_id="immutable-artifact",
        ),
        text=True,
        capture_output=True,
        check=False,
    )

    assert repeated_finalize.returncode == 1
    assert output.read_bytes() == before


def test_concurrent_finalizers_can_publish_an_invocation_only_once(tmp_path: Path) -> None:
    target, _ = make_target(tmp_path)
    init_repo(target.repo_root)
    commit_all(target.repo_root)
    artifact = tmp_path / "dist" / "artifact.bin"
    state = tmp_path / "states" / "concurrent-build.state.json"
    output = tmp_path / "invocations" / "concurrent-build.json"
    sbom_path = tmp_path / "sbom" / "fixture.cdx.json"
    command = provenance_command(
        "begin",
        target=target,
        artifact=artifact,
        state=state,
        output=output,
        sbom=sbom_path,
        invocation_id="concurrent-build",
        artifact_id="concurrent-artifact",
    )
    begun = subprocess.run(command, text=True, capture_output=True, check=False)
    assert begun.returncode == 0, begun.stderr
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_bytes(b"concurrently finalized artifact")
    finalize_command = provenance_command(
        "finalize",
        target=target,
        artifact=artifact,
        state=state,
        output=output,
        sbom=sbom_path,
        invocation_id="concurrent-build",
        artifact_id="concurrent-artifact",
    )

    first = subprocess.Popen(finalize_command, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    second = subprocess.Popen(finalize_command, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    first.communicate(timeout=30)
    second.communicate(timeout=30)

    assert sorted([first.returncode, second.returncode]) == [0, 1]
    assert json.loads(output.read_text(encoding="utf-8"))["status"] == "pass"


def test_desktop_discovery_includes_exact_windows_bootstrap_payload(tmp_path: Path) -> None:
    downloads = tmp_path / "chummer.run-services" / "Chummer.Portal" / "downloads"
    files = downloads / "files"
    files.mkdir(parents=True)
    installer = files / "installer.exe"
    payload = files / "payload.zip"
    installer.write_bytes(b"installer")
    payload.write_bytes(b"payload")
    (downloads / "releases.json").write_text(
        json.dumps(
            {
                "downloads": [
                    {
                        "id": "avalonia-win-x64-installer",
                        "head": "avalonia",
                        "fileName": installer.name,
                        "sha256": hashlib.sha256(installer.read_bytes()).hexdigest(),
                        "payloadFileName": payload.name,
                        "payloadSha256": hashlib.sha256(payload.read_bytes()).hexdigest(),
                        "payloadSizeBytes": payload.stat().st_size,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    artifacts, blockers = MODULE.desktop_release_artifacts(tmp_path)

    assert blockers == []
    assert [artifact["artifact_id"] for artifact in artifacts] == [
        "avalonia-win-x64-installer",
        "avalonia-win-x64-installer-payload",
    ]


def test_linux_release_build_invokes_provenance_begin_and_finalize() -> None:
    linux_gate = Path(
        "/docker/chummercomplete/chummer-presentation/scripts/materialize-linux-desktop-exit-gate.sh"
    ).read_text(encoding="utf-8")

    restore_stage = linux_gate.index('CURRENT_STAGE="restore_publish_graph"')
    begin_stage = linux_gate.index('CURRENT_STAGE="begin_build_provenance"', restore_stage)
    publish_stage = linux_gate.index('CURRENT_STAGE="publish_linux_binary"', begin_stage)
    package_stage = linux_gate.index('CURRENT_STAGE="package_linux_artifacts"', publish_stage)
    finalize_stage = linux_gate.index('CURRENT_STAGE="finalize_build_provenance"', package_stage)
    assert restore_stage < begin_stage < publish_stage < package_stage < finalize_stage
    assert '--source-repo-root "$REPO_ROOT"' in linux_gate
    assert linux_gate.count('--source-material "') >= 6
    for repository in (
        "chummer-core-engine",
        "chummer.run-services",
        "chummer-ui-kit",
        "chummer-hub-registry",
        "chummer-media-factory",
        "chummer5a",
    ):
        assert f'--source-material "{repository}=' in linux_gate
    assert '--build-root "$SOURCE_SNAPSHOT_ROOT"' in linux_gate
    assert '--artifact-path "$INSTALLER_PATH"' in linux_gate
    assert '--build-input "source_snapshot_manifest=$SOURCE_SNAPSHOT_MANIFEST_PATH"' in linux_gate
    assert '--output "$BUILD_PROVENANCE_INVOCATION_RECEIPT"' in linux_gate
    assert '"$PYTHON_BIN" "$BUILD_PROVENANCE_COLLECTOR"' in linux_gate
    assert '--invocation-dir "$BUILD_PROVENANCE_INVOCATION_DIR"' in linux_gate
    assert '--output "$BUILD_PROVENANCE_OUTPUT"' in linux_gate
    assert "--allow-incomplete" in linux_gate


def test_blocker_codes_treat_not_available_as_release_blocking() -> None:
    checks = {
        "secret_scan": {"status": "pass"},
        "dependency_vulnerability_audit": {"status": "pass"},
        "sbom": {"status": "pass"},
        "container_vulnerability_audit": {"status": "not_available"},
        "provenance": {"status": "not_available"},
    }

    assert MODULE.blocker_codes(checks) == [
        "container_vulnerability_audit:not_available",
        "provenance:not_available",
    ]


def write_current_container_scan_intake_fixture(
    tmp_path: Path,
    *,
    generated_at: datetime,
) -> tuple[Path, Path, Path, dict[str, object]]:
    workspace = tmp_path.resolve()
    evidence_path = (
        workspace
        / ".codex-studio"
        / "published"
        / "CONTAINER_VULNERABILITY_SCAN_EVIDENCE.json"
    )
    request_path = (
        workspace
        / ".codex-studio"
        / "published"
        / "CONTAINER_VULNERABILITY_SCAN_INTAKE_REQUEST.generated.json"
    )
    watch_path = (
        workspace / ".state" / "container_vulnerability_scan_intake_watch.generated.json"
    )
    intake_root = (
        workspace / ".state" / "incoming_container_vulnerability_scanner" / "trivy"
    )
    docker_path = workspace / "tools" / "docker"
    docker_path.parent.mkdir(parents=True)
    docker_path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    docker_path.chmod(0o755)
    release_dir = SCRIPT.parent
    script_paths = {
        "producer": release_dir / "materialize_container_vulnerability_scan_evidence.py",
        "verifier": release_dir / "verify_supply_chain_evidence.py",
        "request_materializer": release_dir / "materialize_container_vulnerability_scan_intake_request.py",
        "watcher": release_dir / "watch_container_vulnerability_scan_intake.py",
    }
    layout = MODULE._container_scan_intake_layout("trivy", intake_root)
    image_digest = "sha256:" + ("a" * 64)
    freshness = {
        "maximum_scan_age_hours": MODULE.CONTAINER_SCAN_MAX_AGE_HOURS,
        "maximum_database_age_hours": MODULE.CONTAINER_DATABASE_MAX_AGE_HOURS,
        "ceilings_may_only_be_tightened": True,
    }
    basis = {
        "contract_name": MODULE.CONTAINER_SCAN_INTAKE_REQUEST_CONTRACT_NAME,
        "workspace_root": str(workspace),
        "scanner": "trivy",
        "selected_intake_layout": layout,
        "docker": {
            "path": str(docker_path),
            "sha256": MODULE.sha256_file(docker_path),
            "executable": True,
            "size_bytes": docker_path.stat().st_size,
        },
        "release_images": [
            {"image_name": "fixture-api:local", "image_digest": image_digest}
        ],
        "scripts": {
            role: {
                "label": role,
                "path": str(path),
                "sha256": MODULE.sha256_file(path),
            }
            for role, path in script_paths.items()
        },
        "request_output": str(request_path),
        "watch_state": str(watch_path),
        "evidence_output": str(evidence_path),
        "freshness": freshness,
    }
    binding = MODULE.canonical_json_sha256(basis)
    argv = MODULE._container_scan_intake_safe_argv(
        workspace_root=workspace,
        request_path=request_path,
        watch_state_path=watch_path,
        evidence_path=evidence_path,
        scanner="trivy",
        intake_root=intake_root,
        docker_binary=docker_path,
        binding_sha256=binding,
    )
    payload = {
        "contract_name": MODULE.CONTAINER_SCAN_INTAKE_REQUEST_CONTRACT_NAME,
        "status": "ready",
        "verdict": "INTAKE_REQUEST_READY",
        "generated_at_utc": generated_at.isoformat().replace("+00:00", "Z"),
        "network_access_allowed": False,
        "scanner_or_database_install_allowed": False,
        "automatic_import_allowed": False,
        "arbitrary_root_discovery_allowed": False,
        "selected_scanner": "trivy",
        "selected_intake_layout": layout,
        "current_bindings": {
            "binding_algorithm": "sha256-canonical-json-v1",
            "binding_basis": basis,
            "binding_sha256": binding,
        },
        "commands": {"producer_exact_argv": argv["producer_exact"]},
        "failure_count": 0,
        "failures": [],
    }
    request_path.parent.mkdir(parents=True)
    request_path.write_text(json.dumps(payload) + "\n", encoding="utf-8")
    watch_path.parent.mkdir(parents=True, exist_ok=True)
    watch_path.write_text(
        json.dumps(
            {
                "contract_name": MODULE.CONTAINER_SCAN_INTAKE_WATCH_CONTRACT_NAME,
                "status": "waiting_for_external_artifacts",
                "verdict": "WATCH_TIMEOUT",
                "generated_at_utc": generated_at.isoformat().replace("+00:00", "Z"),
                "mode": "validate_only",
                "request_binding_sha256": binding,
                "validation": {
                    "status": "waiting",
                    "missing_roles": [
                        "scanner_binary",
                        "database_artifact",
                        "database_metadata",
                        "cache_dir",
                    ],
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )
    container_check = {
        "status": "not_available",
        "tools": {"trivy": "not_available", "grype": "not_available"},
        "expected_images": [
            {
                "image_name": "fixture-api:local",
                "digest": image_digest,
                "digest_kind": "docker_image_id",
            }
        ],
        "failures": ["offline container scan evidence is unavailable"],
    }
    return request_path, watch_path, evidence_path, container_check


def test_recovery_plan_surfaces_current_validated_intake_and_validate_only_state(
    tmp_path: Path,
) -> None:
    now = datetime(2026, 7, 14, 2, 0, tzinfo=UTC)
    request_path, watch_path, evidence_path, container_check = (
        write_current_container_scan_intake_fixture(tmp_path, generated_at=now)
    )
    checks = {
        "secret_scan": {"status": "pass"},
        "dependency_vulnerability_audit": {"status": "pass"},
        "sbom": {"status": "pass"},
        "container_vulnerability_audit": container_check,
        "provenance": {"status": "fail", "expected_artifacts": [], "failures": []},
    }

    plan = MODULE.recovery_plan(
        tmp_path,
        checks,
        evidence_path,
        tmp_path / "BUILD_PROVENANCE.generated.json",
        current_time=now + timedelta(minutes=1),
    )

    container = plan["container_vulnerability_audit"]
    intake = container["operator_intake_request"]
    assert intake["path"] == str(request_path)
    assert intake["load_status"] == "loaded"
    assert intake["usable"] is True
    assert intake["validity"] == "current_validated_binding"
    assert intake["status"] == "ready"
    assert intake["verdict"] == "INTAKE_REQUEST_READY"
    assert intake["selected_scanner"] == "trivy"
    assert intake["exact_drop_root"].endswith(
        ".state/incoming_container_vulnerability_scanner/trivy"
    )
    assert intake["command_source"] == "reconstructed_from_current_validated_binding"
    assert intake["code_owned_argv"]["validate_now"][1].endswith(
        "watch_container_vulnerability_scan_intake.py"
    )
    assert "--generate-evidence" not in intake["code_owned_argv"]["validate_now"]
    assert "--generate-evidence" in intake["code_owned_argv"][
        "generate_after_validation_approval"
    ]
    assert intake["code_owned_argv"]["verify_after_generation"][1] == str(SCRIPT)
    assert intake["execution_claims"] == {
        "external_artifacts_validated": False,
        "evidence_generation_completed": False,
        "independent_supply_chain_verification_completed": False,
        "release_gate_ready": False,
    }
    watch = intake["validate_only_watch"]
    assert watch["path"] == str(watch_path)
    assert watch["usable"] is True
    assert watch["status"] == "waiting_for_external_artifacts"
    assert watch["mode"] == "validate_only"
    assert watch["missing_roles"] == [
        "cache_dir",
        "database_artifact",
        "database_metadata",
        "scanner_binary",
    ]
    actions = MODULE.next_actions(checks, plan)
    assert any(str(request_path) in action for action in actions)
    assert any("code_owned_argv.validate_now" in action for action in actions)


@pytest.mark.parametrize("failure_mode", ["malformed", "binding_mismatch", "stale"])
def test_recovery_plan_rejects_unusable_intake_and_preserves_generic_template(
    tmp_path: Path,
    failure_mode: str,
) -> None:
    now = datetime(2026, 7, 14, 2, 0, tzinfo=UTC)
    request_path, _watch_path, evidence_path, container_check = (
        write_current_container_scan_intake_fixture(tmp_path, generated_at=now)
    )
    if failure_mode == "malformed":
        request_path.write_text("{", encoding="utf-8")
    else:
        payload = json.loads(request_path.read_text(encoding="utf-8"))
        if failure_mode == "binding_mismatch":
            payload["current_bindings"]["binding_sha256"] = "0" * 64
        else:
            payload["generated_at_utc"] = "2026-07-12T00:00:00Z"
        request_path.write_text(json.dumps(payload) + "\n", encoding="utf-8")
    checks = {
        "secret_scan": {"status": "pass"},
        "dependency_vulnerability_audit": {"status": "pass"},
        "sbom": {"status": "pass"},
        "container_vulnerability_audit": container_check,
        "provenance": {"status": "pass", "expected_artifacts": [], "failures": []},
    }

    plan = MODULE.recovery_plan(
        tmp_path,
        checks,
        evidence_path,
        tmp_path / "BUILD_PROVENANCE.generated.json",
        current_time=now + timedelta(minutes=1),
    )

    container = plan["container_vulnerability_audit"]
    intake = container["operator_intake_request"]
    assert intake["usable"] is False
    assert intake["code_owned_argv"] == {}
    assert "<absolute-existing-scanner-path>" in container["safe_argv_template"]
    actions = MODULE.next_actions(checks, plan)
    assert any("materialize_container_vulnerability_scan_evidence.py" in action for action in actions)


def test_recovery_plan_exposes_offline_scan_inputs_and_oci_provenance_binding(
    tmp_path: Path,
) -> None:
    container_evidence = tmp_path / "CONTAINER_VULNERABILITY_SCAN_EVIDENCE.json"
    provenance_path = tmp_path / "BUILD_PROVENANCE.generated.json"
    provenance_path.write_text('{}\n', encoding="utf-8")
    checks = {
        "container_vulnerability_audit": {
            "status": "not_available",
            "tools": {"trivy": "not_available", "grype": "not_available"},
            "failures": ["offline container scan evidence is unavailable"],
        },
        "provenance": {
            "status": "fail",
            "expected_artifacts": [
                {"artifact_id": "run-services-api"},
                {"artifact_id": "avalonia-win-x64-installer"},
            ],
            "failures": [
                "source repository has tracked changes: chummer.run-services",
                "missing build provenance subject: run-services-api",
                "build provenance is missing subject: avalonia-win-x64-installer",
            ],
        },
    }

    plan = MODULE.recovery_plan(tmp_path, checks, container_evidence, provenance_path)

    container = plan["container_vulnerability_audit"]
    assert container["evidence_exists"] is False
    assert container["path_discovered_scanner_available"] is False
    assert container["network_or_install_permitted"] is False
    assert "--database-artifact" in container["safe_argv_template"]
    assert "--database-metadata" in container["safe_argv_template"]
    provenance = plan["provenance"]
    assert provenance["aggregate_exists"] is True
    assert provenance["supported_artifact_bindings"] == ["regular_file", "oci_image"]
    assert provenance["oci_binding_flags"] == ["--artifact-image", "--docker-binary"]
    assert provenance["dirty_repositories"] == ["chummer.run-services"]
    assert provenance["expected_subjects"] == [
        "avalonia-win-x64-installer",
        "run-services-api",
    ]
    assert provenance["missing_subjects"] == [
        "avalonia-win-x64-installer",
        "run-services-api",
    ]
    assert provenance["synthesis_after_build_permitted"] is False


def test_supply_chain_next_actions_name_real_offline_and_oci_recovery_paths() -> None:
    checks = {
        "secret_scan": {"status": "pass"},
        "dependency_vulnerability_audit": {"status": "pass"},
        "sbom": {"status": "pass"},
        "container_vulnerability_audit": {"status": "not_available"},
        "provenance": {"status": "fail"},
    }

    actions = MODULE.next_actions(checks)

    assert any("materialize_container_vulnerability_scan_evidence.py" in action for action in actions)
    assert any("never" in action and "download" in action for action in actions)
    assert any("materialize_build_provenance.py begin" in action for action in actions)
    assert any("--artifact-image" in action and "--docker-binary" in action for action in actions)


def root_release_ready_supply_chain_gate_command() -> tuple[list[str], dict[str, object], str, str]:
    controller = load_release_ready_materializer()
    environment = controller.authoritative_controller_environment(
        {"PATH": controller.TRUSTED_PATH}
    )
    specs = controller.canonical_release_gate_specs(environment)
    names = [str(spec["name"]) for spec in specs]
    supply_spec = next(
        spec for spec in specs if spec["name"] == "verify_supply_chain_evidence"
    )
    return names, supply_spec, str(supply_spec["command"]), str(controller.TRUSTED_PYTHON)


def test_root_release_ready_wrapper_runs_supply_chain_gate_after_package_boundaries() -> None:
    gate_names, supply_chain_gate, supply_chain_command, _ = root_release_ready_supply_chain_gate_command()
    package_gate = "verify_package_boundaries"
    supply_gate = "verify_supply_chain_evidence"
    core_gate = "verify_core_release_receipts"

    assert package_gate in gate_names
    assert supply_chain_gate["name"] == supply_gate
    assert core_gate in gate_names
    assert gate_names.index(package_gate) < gate_names.index(supply_gate)
    assert gate_names.index(supply_gate) < gate_names.index(core_gate)
    assert supply_chain_command.index("collect_build_provenance.py") < supply_chain_command.index(
        "verify_supply_chain_evidence.py"
    )
    assert "|| collector_status=$?" in supply_chain_command
    assert "|| verifier_status=$?" in supply_chain_command
    assert "exit $collector_status" in supply_chain_command
    assert supply_chain_command.endswith("exit $verifier_status")


def test_root_release_ready_supply_chain_gate_keeps_collector_failure_after_verifier_runs(
    tmp_path: Path,
) -> None:
    _, _, supply_chain_command, trusted_python = root_release_ready_supply_chain_gate_command()
    collector_marker = tmp_path / "collector-ran"
    verifier_marker = tmp_path / "verifier-ran"
    collector = tmp_path / "collector.py"
    verifier = tmp_path / "verifier.py"
    collector.write_text(
        "from pathlib import Path\n"
        f"Path({str(collector_marker)!r}).write_text('ran', encoding='utf-8')\n"
        "raise SystemExit(23)\n",
        encoding="utf-8",
    )
    verifier.write_text(
        "from pathlib import Path\n"
        f"Path({str(verifier_marker)!r}).write_text('ran', encoding='utf-8')\n"
        "raise SystemExit(0)\n",
        encoding="utf-8",
    )
    command = supply_chain_command.replace(
        f"{trusted_python} /docker/chummercomplete/scripts/release/collect_build_provenance.py --workspace-root /docker/chummercomplete",
        f"{shlex.quote(sys.executable)} {shlex.quote(str(collector))}",
    ).replace(
        f"{trusted_python} /docker/chummercomplete/scripts/release/verify_supply_chain_evidence.py --workspace-root /docker/chummercomplete",
        f"{shlex.quote(sys.executable)} {shlex.quote(str(verifier))}",
    )
    assert "/docker/chummercomplete/scripts/release/" not in command

    completed = subprocess.run(
        ["/usr/bin/bash", "--noprofile", "--norc", "-c", command],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 23, completed.stderr
    assert collector_marker.read_text(encoding="utf-8") == "ran"
    assert verifier_marker.read_text(encoding="utf-8") == "ran"

from __future__ import annotations

import importlib.util
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "check_public_edge_deploy_preflight.py"
CUTOVER_SCRIPT = (
    REPO_ROOT / "scripts" / "run_install_linking_postgres_cutover.py"
)
MATERIALIZER_SCRIPT = REPO_ROOT / "scripts/materialize_hub_local_release_proof.py"
COMPOSE_SOURCE_ATTESTOR = (
    REPO_ROOT / "scripts/attest_public_edge_compose_source.py"
)
REGISTRY_RELEASE_PROOF_CONSUMER = (
    REPO_ROOT.parent
    / "chummer-hub-registry/scripts/materialize_public_release_channel.py"
)


def load_module():
    spec = importlib.util.spec_from_file_location("check_public_edge_deploy_preflight", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def load_cutover_module():
    name = "run_install_linking_postgres_cutover_compose_policy_test"
    spec = importlib.util.spec_from_file_location(name, CUTOVER_SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def load_registry_release_proof_consumer():
    spec = importlib.util.spec_from_file_location(
        "chummer_registry_release_proof_consumer_test",
        REGISTRY_RELEASE_PROOF_CONSUMER,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def load_materializer_module():
    spec = importlib.util.spec_from_file_location(
        "chummer_runtime_proof_materializer_lock_test",
        MATERIALIZER_SCRIPT,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def load_compose_source_attestor():
    spec = importlib.util.spec_from_file_location(
        "public_edge_compose_source_attestor_test",
        COMPOSE_SOURCE_ATTESTOR,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def write_valid_runtime_proof(path: Path) -> str:
    proof_payload = json.loads(
        (
            REPO_ROOT
            / ".codex-studio/published/HUB_LOCAL_RELEASE_PROOF.generated.json"
        ).read_text(encoding="utf-8")
    )
    generated_at = datetime.now(UTC).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )
    proof_payload["generatedAt"] = generated_at
    proof_payload["generated_at"] = generated_at
    proof_payload["journeys_passed"] = [
        "install_claim_restore_continue",
        "build_explain_publish",
        "campaign_session_recover_recap",
        "report_cluster_release_notify",
        "organize_community_and_close_loop",
    ]
    proof_payload["proof_routes"] = [
        "/downloads/install/avalonia-linux-x64-installer",
        "/home/access",
        "/home/work",
        "/account/access",
        "/account/work",
        "/account/roster",
        "/account/support",
        "/contact",
        "/downloads",
        "/downloads/install/avalonia-osx-arm64-installer",
        "/downloads/install/avalonia-win-x64-installer",
    ]
    proof_payload["release_channel"] = {
        "status": "available",
        "path": "Chummer.Portal/downloads/RELEASE_CHANNEL.generated.json",
        "channelId": "preview",
        "channel": "preview",
        "version": "run-test",
        "releaseVersion": "run-test",
        "rolloutState": "published",
        "supportabilityState": "review_required",
        "publishedAt": generated_at,
    }
    rendered = json.dumps(proof_payload, indent=2, sort_keys=True) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(rendered, encoding="utf-8")
    path.chmod(0o644)
    return rendered


def write_public_projection_snapshot(
    root: Path,
    runtime_proof_text: str,
) -> tuple[Path, str, str]:
    output_names = (
        "HUB_LOCAL_RELEASE_PROOF.generated.json",
        "HUB_SERVED_RELEASE_PROOF.generated.json",
        "NEXT90_M125_HUB_PUBLIC_SIGNAL_PACKETS.generated.json",
        "NEXT90_M126_HUB_HOSTED_PROOF_CONTRACTS.generated.json",
        "LIVE_PUBLIC_WINDOWS_INSTALLER.generated.json",
        "RELEASE_CHANNEL.generated.json",
        "FLAGSHIP_PRODUCT_READINESS.generated.json",
    )
    release_projection = json.loads(runtime_proof_text)["release_channel"]
    release_channel_payload = (
        json.dumps(
            {
                "status": "published",
                "channelId": release_projection["channelId"],
                "channel": release_projection["channel"],
                "version": release_projection["version"],
                "releaseVersion": release_projection["releaseVersion"],
                "rolloutState": release_projection["rolloutState"],
                "supportabilityState": release_projection["supportabilityState"],
                "publishedAt": release_projection["publishedAt"],
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")
    root.mkdir(parents=True, exist_ok=True)
    payloads = {
        output_names[0]: runtime_proof_text.encode("utf-8"),
        output_names[1]: runtime_proof_text.encode("utf-8"),
        output_names[2]: b'{"status":"pass"}\n',
        output_names[3]: b'{"status":"pass"}\n',
        output_names[4]: b'{"status":"pass"}\n',
        output_names[5]: release_channel_payload,
        output_names[6]: b'{"status":"fail"}\n',
    }
    digests = {
        name: hashlib.sha256(payloads[name]).hexdigest() for name in output_names
    }
    aggregate = hashlib.sha256()
    for name in output_names:
        aggregate.update(name.encode("utf-8"))
        aggregate.update(b"\0")
        aggregate.update(digests[name].encode("ascii"))
        aggregate.update(b"\n")
    snapshot_sha256 = aggregate.hexdigest()
    snapshot_id = f"public-projection-{snapshot_sha256}"
    snapshot_directory = root / snapshot_id
    snapshot_directory.mkdir()
    for name, payload in payloads.items():
        output = snapshot_directory / name
        output.write_bytes(payload)
        output.chmod(0o644)
    manifest = {
        "contractName": "chummer.public_projection_snapshot/v1",
        "status": "pass",
        "projectionStage": "release_upload_ready",
        "codeDeploymentAuthority": True,
        "releaseUploadAuthority": True,
        "candidateImportAuthority": False,
        "snapshotId": snapshot_id,
        "snapshotSha256": snapshot_sha256,
        "authorityInputs": {},
        "outputs": {
            name: {
                "relativePath": name,
                "sha256": digests[name],
                "sizeBytes": len(payloads[name]),
            }
            for name in output_names
        },
    }
    manifest_bytes = (
        json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")
    manifest_name = "PUBLIC_PROJECTION_SNAPSHOT.generated.json"
    (snapshot_directory / manifest_name).write_bytes(manifest_bytes)
    pointer = {
        "contractName": "chummer.public_projection_current/v1",
        "status": "pass",
        "projectionStage": "release_upload_ready",
        "codeDeploymentAuthority": True,
        "releaseUploadAuthority": True,
        "candidateImportAuthority": False,
        "snapshotId": snapshot_id,
        "snapshotSha256": snapshot_sha256,
        "manifestRelativePath": f"{snapshot_id}/{manifest_name}",
        "manifestSha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "outputs": {name: f"{snapshot_id}/{name}" for name in output_names},
    }
    (root / "CURRENT.json").write_text(
        json.dumps(pointer, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    return snapshot_directory / output_names[0], snapshot_id, snapshot_sha256


def write_release_channel_receipt_for_proof(
    path: Path,
    proof_text: str,
) -> str:
    projection = json.loads(proof_text)["release_channel"]
    receipt = {
        "status": "published",
        "channelId": projection["channelId"],
        "channel": projection["channel"],
        "version": projection["version"],
        "releaseVersion": projection["releaseVersion"],
        "rolloutState": projection["rolloutState"],
        "supportabilityState": projection["supportabilityState"],
        "publishedAt": projection["publishedAt"],
    }
    payload = (json.dumps(receipt, indent=2, sort_keys=True) + "\n").encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    path.chmod(0o600)
    return hashlib.sha256(payload).hexdigest()


def runtime_proof_sha256(proof_text: str) -> str:
    return hashlib.sha256(proof_text.encode("utf-8")).hexdigest()


def test_runtime_proof_materializer_writes_under_shared_mutation_lock(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    materializer = load_materializer_module()
    output = tmp_path / "HUB_LOCAL_RELEASE_PROOF.generated.json"
    events: list[str] = []
    lock_active = False

    class RecordingLock:
        def __enter__(self):
            nonlocal lock_active
            assert lock_active is False
            lock_active = True
            events.append("enter")

        def __exit__(self, _exc_type, _exc, _traceback):
            nonlocal lock_active
            assert lock_active is True
            events.append("exit")
            lock_active = False

    materializer._PUBLIC_EDGE_OVERLAY_MODULE = SimpleNamespace(
        PUBLIC_EDGE_MUTATION_LOCK=tmp_path / "public-edge-mutation.lock",
        public_edge_mutation_lock=lambda *, activate, lock_path: RecordingLock()
        if activate
        else pytest.fail("proof publication must activate shared mutation authority")
    )
    original_write = materializer._write_public_json_artifact

    def locked_write(path: Path, text: str) -> bool:
        assert lock_active is True
        return original_write(path, text)

    monkeypatch.setattr(materializer, "_write_public_json_artifact", locked_write)

    def materialize_locked(*_args: str) -> int:
        materializer._publish_runtime_proof_artifacts(
            out_path=output,
            payload={"status": "passed"},
            proof_max_age_seconds=3600,
            proof_max_future_skew_seconds=300,
        )
        return 0

    monkeypatch.setattr(
        materializer,
        "_materialize_under_shared_mutation_lock",
        materialize_locked,
    )
    exit_code = materializer.materialize_with_shared_mutation_lock(
        str(output),
        "https://chummer.run",
        "docker-compose.public-edge.yml",
        "300",
        "true",
    )

    assert exit_code == 0
    assert events == ["enter", "exit"]
    assert lock_active is False
    assert json.loads(output.read_text(encoding="utf-8"))["status"] == "passed"


def test_runtime_proof_materializer_rejects_fifo_without_blocking(
    tmp_path: Path,
) -> None:
    materializer = load_materializer_module()
    path = tmp_path / "runtime-proof.fifo"
    os.mkfifo(path, 0o644)

    assert materializer._stable_regular_file_matches(path, b"{}\n") is False


def test_cli_imports_sibling_contract_under_isolated_python(tmp_path: Path) -> None:
    result = subprocess.run(
        ["/usr/bin/python3", "-I", str(SCRIPT), "--help"],
        cwd=tmp_path,
        env={
            "PATH": "/usr/bin:/bin",
            "HOME": "/nonexistent",
            "LANG": "C",
            "LC_ALL": "C",
        },
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "Fail closed when public-edge rebuild" in result.stdout


def configure_fake_public_pwa_identities(module, source_root: Path) -> dict[str, tuple[str, str]]:
    pins: dict[str, tuple[str, str]] = {}
    for role, relative_path in module.PUBLIC_PWA_PROOF_IDENTITY_PATHS.items():
        path = source_root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = f"{role}-trusted-identity\n".encode("utf-8")
        path.write_bytes(payload)
        pins[role] = (relative_path, hashlib.sha256(payload).hexdigest())
    authority_root = source_root.parent / "reviewed-pwa-authority"
    authority_path = authority_root / module.PUBLIC_PWA_PROOF_AUTHORITY_RELATIVE_PATH
    authority_path.parent.mkdir(parents=True, exist_ok=True)
    authority_path.write_text(
        json.dumps(
            {
                "contractName": module.PUBLIC_PWA_PROOF_AUTHORITY_CONTRACT,
                "policyId": module.PUBLIC_PWA_POLICY_ID,
                "assetPolicyCount": module.PUBLIC_PWA_EXPECTED_ASSET_COUNT,
                "dependencyPolicyCount": module.PUBLIC_PWA_EXPECTED_DEPENDENCY_COUNT,
                "verifierPath": pins["verifier"][0],
                "verifierSha256": pins["verifier"][1],
                "generatorPath": pins["generator"][0],
                "generatorSha256": pins["generator"][1],
                "inventoryPath": pins["policy"][0],
                "inventorySha256": pins["policy"][1],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    source_authority_path = source_root / module.PUBLIC_PWA_PROOF_AUTHORITY_RELATIVE_PATH
    source_authority_path.parent.mkdir(parents=True, exist_ok=True)
    source_authority_path.write_bytes(authority_path.read_bytes())
    for root_name, relative_path in module.expected_public_pwa_input_paths():
        root = source_root if root_name == "run-services" else source_root.parent / "chummer-play"
        path = root / relative_path
        if path.exists():
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(f"fixture:{root_name}:{relative_path}\n".encode("utf-8"))
    module.PUBLIC_PWA_PROOF_AUTHORITY_ROOT = authority_root
    return pins


def write_fake_child_receipt(command: list[str], payload: bytes) -> None:
    descriptor = int(command[command.index("--output-fd") + 1])
    os.ftruncate(descriptor, 0)
    os.lseek(descriptor, 0, os.SEEK_SET)
    offset = 0
    while offset < len(payload):
        offset += os.write(descriptor, payload[offset:])


def copy_current_public_pwa_proof_fixture(module, tmp_path: Path) -> Path:
    source_root = tmp_path / "chummer.run-services"
    play_root = tmp_path / "chummer-play"
    projection_by_source = dict(module.PUBLIC_PWA_ASSET_INPUTS)
    for root_name, relative_path in module.expected_public_pwa_input_paths():
        source = (
            REPO_ROOT / relative_path
            if root_name == "run-services"
            else REPO_ROOT / projection_by_source[relative_path]
        )
        target_root = source_root if root_name == "run-services" else play_root
        target = target_root / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)

    source_worker = play_root / "src/Chummer.Play.Web/wwwroot/service-worker.js"
    source_worker.write_text(
        'const CACHE_VERSION = "v21";\n'
        'const CACHE_CONTRACT = "play-source-v2";\n'
        "const CRITICAL_SHELL_FETCH_ATTEMPTS = 3;\n"
        "const CRITICAL_SHELL_FETCH_RETRY_DELAYS_MS = [250, 750];\n"
        "const CRITICAL_SHELL_FETCH_TIMEOUT_MS = 5000;\n"
        "const CRITICAL_SHELL_RESPONSE_MAX_BYTES = 1024 * 1024;\n"
        "const CRITICAL_SHELL_CACHE_WRITE_TIMEOUT_MS = 5000;\n"
        "const CRITICAL_SHELL_ASSETS = [\n"
        '  "/mobile.css",\n'
        '  "/mobile-install-shell.js",\n'
        '  "/manifest.webmanifest",\n'
        '  "/manifest.observer.webmanifest"\n'
        "];\n"
        "async function fetchCriticalShellAsset(request, controller, timeoutId) {\n"
        "  const response = await fetch(request, { signal: controller.signal });\n"
        "  const body = await response.arrayBuffer();\n"
        "  clearTimeout(timeoutId);\n"
        "  return body;\n"
        "}\n"
        "async function cacheCriticalShellAsset(cache, asset) { return true; }\n"
        "async function precacheCriticalShell() { return true; }\n"
        'self.addEventListener("install", (event) => {\n'
        "  event.waitUntil(precacheCriticalShell());\n"
        "});\n",
        encoding="utf-8",
    )
    projection_config_path = (
        source_root / "Chummer.Run.Api/play-worker-projection.json"
    )
    projection_config = json.loads(
        projection_config_path.read_text(encoding="utf-8")
    )
    projection_config["sourceSha256"] = hashlib.sha256(
        source_worker.read_bytes()
    ).hexdigest()
    projection_config_path.write_text(
        json.dumps(projection_config, indent=2) + "\n",
        encoding="utf-8",
    )

    generator_path = (
        source_root / module.PUBLIC_PWA_PROOF_IDENTITY_PATHS["generator"]
    )
    generator_name = (
        "public_pwa_fixture_generator_"
        + hashlib.sha256(str(source_root).encode("utf-8")).hexdigest()
    )
    generator_spec = importlib.util.spec_from_file_location(
        generator_name,
        generator_path,
    )
    assert generator_spec is not None and generator_spec.loader is not None
    generator = importlib.util.module_from_spec(generator_spec)
    sys.modules[generator_name] = generator
    generator_spec.loader.exec_module(generator)
    generator_receipt = generator.run(
        root=source_root,
        config_path=projection_config_path,
    )
    assert generator_receipt["status"] == "pass"

    module.PUBLIC_PWA_PROOF_AUTHORITY_ROOT = source_root
    return source_root


@pytest.fixture
def public_pwa_workspace() -> Iterator[Path]:
    with tempfile.TemporaryDirectory(
        prefix=".public-pwa-test-",
        dir=REPO_ROOT.parent,
    ) as fixture_dir:
        yield Path(fixture_dir)


def real_subprocess_with_swap(module, mutate):
    real_popen = module.subprocess.Popen
    completed_process = module.subprocess.CompletedProcess

    def run(command, **kwargs):
        timeout = kwargs.pop("timeout")
        kwargs.pop("check", None)
        process = real_popen(command, **kwargs)
        undo = None
        try:
            undo = mutate(command, kwargs)
            return_code = process.wait(timeout=timeout)
            if undo is not None:
                undo()
                undo = None
            return completed_process(command, return_code)
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()
            if undo is not None:
                undo()

    return run


def write_hostile_python_startup_module(path: Path, marker: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "import os\n"
        "import sys\n"
        f"open({str(marker)!r}, 'w', encoding='utf-8').write('executed\\n')\n"
        "if '--output-fd' in sys.argv:\n"
        "    descriptor = int(sys.argv[sys.argv.index('--output-fd') + 1])\n"
        "    payload = b'{\"status\":\"pass\",\"failures\":[\"forged-python-startup\"],\"mirror\":{}}'\n"
        "    os.ftruncate(descriptor, 0)\n"
        "    os.lseek(descriptor, 0, os.SEEK_SET)\n"
        "    os.write(descriptor, payload)\n"
        "os._exit(0)\n",
        encoding="utf-8",
    )


def test_clean_process_list_passes() -> None:
    module = load_module()

    receipt = module.verify(
        [
            "100 1 S 00:01 bash bash",
            "101 1 S 00:02 dotnet dotnet test Chummer.Tests/Chummer.Tests.csproj",
        ],
        allow_stale_foreign_build_locks=False,
        check_source_markers=False,
    )

    assert receipt["status"] == "pass"
    assert receipt["activeLockCount"] == 0
    assert receipt["findings"] == []


def test_active_linux_source_gate_fails_closed() -> None:
    module = load_module()

    receipt = module.verify(
        [
            "362558 1 SNl 10:35:43 docker /usr/bin/docker run bash scripts/build-chummer6-linux.sh --base /work/base",
        ],
        allow_stale_foreign_build_locks=False,
        check_source_markers=False,
    )

    assert receipt["status"] == "fail"
    assert receipt["activeLockCount"] == 1
    assert receipt["staleLookingLockCount"] == 1
    assert receipt["activeLocks"][0]["pid"] == "362558"
    assert receipt["activeLocks"][0]["staleLooking"] == "true"
    assert any(finding["id"] == "active_build_lane" for finding in receipt["findings"])


def test_active_play_or_presentation_build_fails_closed() -> None:
    module = load_module()

    receipt = module.verify(
        [
            "397125 390479 SNl 10:30:16 dotnet dotnet build /work/base/chummer6-ui/Chummer.Presentation/Chummer.Presentation.csproj",
            "3245065 3216459 SNl 00:02:36 dotnet dotnet build src/Chummer.Play.Web/Chummer.Play.Web.csproj",
            "3248886 3245065 R 00:00 csc /usr/lib/dotnet/sdk/10.0.109/Roslyn/bincore/csc @response.rsp",
        ],
        allow_stale_foreign_build_locks=False,
    )

    assert receipt["status"] == "fail"
    assert receipt["activeLockCount"] == 3
    assert receipt["staleLookingLockCount"] == 1
    assert {lock["command"] for lock in receipt["activeLocks"]} == {"dotnet", "csc"}


def test_active_docker_compose_build_fails_closed() -> None:
    module = load_module()

    receipt = module.verify(
        [
            "3041693 3041301 Sl 00:12:14 docker /usr/bin/docker compose -f docker-compose.property.yml -f docker-compose.cloudflared.yml up -d --build --remove-orphans",
        ],
        allow_stale_foreign_build_locks=False,
        check_source_markers=False,
    )

    assert receipt["status"] == "fail"
    assert receipt["activeLockCount"] == 1
    assert receipt["activeLocks"][0]["command"] == "docker"
    matched_patterns = receipt["activeLocks"][0]["matchedPatterns"]
    assert "docker compose" in matched_patterns
    assert "docker-compose" in matched_patterns
    assert any(finding["id"] == "active_build_lane" for finding in receipt["findings"])


def test_recent_or_running_build_lock_is_not_stale_looking() -> None:
    module = load_module()

    receipt = module.verify(
        [
            "3245065 3216459 SNl 00:02:36 dotnet dotnet build src/Chummer.Play.Web/Chummer.Play.Web.csproj",
            "3248886 3245065 R 10:30:16 csc /usr/lib/dotnet/sdk/10.0.109/Roslyn/bincore/csc @response.rsp",
        ],
        allow_stale_foreign_build_locks=False,
    )

    assert receipt["status"] == "fail"
    assert receipt["activeLockCount"] == 2
    assert receipt["staleLookingLockCount"] == 0
    assert {lock["staleLooking"] for lock in receipt["activeLocks"]} == {"false"}


def test_play_runtime_no_build_processes_are_ignored() -> None:
    module = load_module()

    receipt = module.verify(
        [
            "1752005 4160399 SNsl 01:46:42 dotnet /usr/bin/dotnet run --no-launch-profile --project src/Chummer.Play.Web/Chummer.Play.Web.csproj --no-build",
            "1752110 1752005 SNl 01:46:41 Chummer.Play.We /docker/chummercomplete/chummer-play/src/Chummer.Play.Web/bin/Debug/net10.0/Chummer.Play.Web",
        ],
        allow_stale_foreign_build_locks=False,
        check_source_markers=False,
    )

    assert receipt["status"] == "pass"
    assert receipt["activeLockCount"] == 0
    assert receipt["findings"] == []


def test_dotnet_run_without_no_build_still_fails_closed() -> None:
    module = load_module()

    receipt = module.verify(
        [
            "3245065 3216459 SNl 00:02:36 dotnet dotnet run --project src/Chummer.Play.Web/Chummer.Play.Web.csproj",
        ],
        allow_stale_foreign_build_locks=False,
    )

    assert receipt["status"] == "fail"
    assert receipt["activeLockCount"] == 1
    assert receipt["activeLocks"][0]["matchedPatterns"] == "Chummer.Play"


def test_elapsed_day_format_can_be_classified_stale_looking() -> None:
    module = load_module()

    receipt = module.verify(
        [
            "362558 1 SNl 1-00:00:01 docker /usr/bin/docker run bash scripts/build-chummer6-linux.sh --base /work/base",
        ],
        allow_stale_foreign_build_locks=False,
    )

    assert receipt["activeLocks"][0]["elapsedSeconds"] == str(86401)
    assert receipt["activeLocks"][0]["staleLooking"] == "true"


def test_tolerates_stale_foreign_build_locks_when_flagged() -> None:
    module = load_module()

    receipt = module.verify(
        [
            "362558 1 SNl 10:35:43 docker /usr/bin/docker run bash scripts/build-chummer6-linux.sh --base /work/base",
            "397125 390479 SNl 10:30:16 dotnet dotnet build /work/base/chummer6-ui/Chummer.Presentation/Chummer.Presentation.csproj",
        ],
        allow_stale_foreign_build_locks=True,
        check_source_markers=False,
    )

    assert receipt["status"] == "pass"
    assert receipt["activeLockCount"] == 2
    assert receipt["staleForeignLockCount"] == 2
    assert receipt["allowStaleForeignBuildLocks"] is True
    assert receipt["findings"] == []


def test_auto_ignores_super_stale_foreign_build_locks_by_default() -> None:
    module = load_module()

    receipt = module.verify(
        [
            "362558 1 SNl 3-10:35:43 docker /usr/bin/docker run bash scripts/build-chummer6-linux.sh --base /work/base",
            "397125 390479 SNl 2-10:30:16 dotnet dotnet build /work/base/chummer6-ui/Chummer.Presentation/Chummer.Presentation.csproj",
        ],
        allow_stale_foreign_build_locks=False,
        check_source_markers=False,
    )

    assert receipt["status"] == "pass"
    assert receipt["activeLockCount"] == 2
    assert receipt["foreignLockCount"] == 2
    assert receipt["ignoredForeignLockCount"] == 2
    assert receipt["autoIgnoredStaleForeignLockCount"] == 2
    assert receipt["allowStaleForeignBuildLocks"] is False
    assert receipt["findings"] == []


def test_tolerates_active_foreign_build_locks_when_explicitly_allowed() -> None:
    module = load_module()

    receipt = module.verify(
        [
            "3245065 3216459 SNl 00:02:36 dotnet dotnet build /tmp/other-lane/Chummer.Play.Web.csproj",
            "3248886 3245065 R 00:00 csc /usr/lib/dotnet/sdk/10.0.109/Roslyn/bincore/csc @response.rsp",
        ],
        allow_stale_foreign_build_locks=False,
        allow_foreign_build_locks=True,
        check_source_markers=False,
    )

    assert receipt["status"] == "pass"
    assert receipt["activeLockCount"] == 2
    assert receipt["foreignLockCount"] == 2
    assert receipt["ignoredForeignLockCount"] == 2
    assert receipt["foreignLocksIgnored"] is True
    assert receipt["allowForeignBuildLocks"] is True
    assert receipt["findings"] == []


def test_local_scope_stale_lock_stays_blocking_even_with_allow_flag() -> None:
    module = load_module()

    receipt = module.verify(
        [
            f"111111 1 SNl 10:30:00 dotnet dotnet build {REPO_ROOT}/Chummer.Presentation/Chummer.Presentation.csproj",
        ],
        allow_stale_foreign_build_locks=True,
    )

    assert receipt["status"] == "fail"
    assert receipt["staleForeignLockCount"] == 0
    assert receipt["allowStaleForeignBuildLocks"] is True
    assert any(lock.get("buildScope") == "local" for lock in receipt["activeLocks"])
    assert receipt["activeLockCount"] == 1


def test_local_scope_active_lock_stays_blocking_even_with_allow_foreign_flag() -> None:
    module = load_module()

    receipt = module.verify(
        [
            f"3245065 3216459 SNl 00:02:36 dotnet dotnet build {REPO_ROOT}/Chummer.Presentation/Chummer.Presentation.csproj",
        ],
        allow_stale_foreign_build_locks=False,
        allow_foreign_build_locks=True,
    )

    assert receipt["status"] == "fail"
    assert receipt["foreignLockCount"] == 0
    assert receipt["ignoredForeignLockCount"] == 0
    assert receipt["allowForeignBuildLocks"] is True
    assert any(lock.get("buildScope") == "local" for lock in receipt["activeLocks"])
    assert any(finding["id"] == "active_build_lane" for finding in receipt["findings"])


def test_current_source_marker_check_passes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_module()
    module.PUBLIC_EDGE_OPERATIONAL_MIRROR_ROOTS = {}
    monkeypatch.setattr(
        module,
        "execute_public_pwa_static_proof",
        lambda _source_root: {
            "status": "pass",
            "testScope": "source-markers-only",
        },
    )
    runtime_proof = tmp_path / "HUB_LOCAL_RELEASE_PROOF.generated.json"
    proof_text = write_valid_runtime_proof(runtime_proof)
    release_receipt = tmp_path / "RELEASE_CHANNEL.generated.json"
    release_receipt_sha256 = write_release_channel_receipt_for_proof(
        release_receipt,
        proof_text,
    )
    snapshot_root = tmp_path / "public-projection"
    authenticated_proof, _, _ = write_public_projection_snapshot(
        snapshot_root,
        proof_text,
    )

    receipt = module.verify(
        [],
        allow_stale_foreign_build_locks=False,
        source_root=REPO_ROOT,
        public_projection_snapshot_root=snapshot_root,
        runtime_proof_bind_source=authenticated_proof,
        runtime_proof_bind_source_sha256=runtime_proof_sha256(proof_text),
        release_channel_receipt=release_receipt,
        release_channel_receipt_sha256=release_receipt_sha256,
    )

    assert receipt["status"] == "pass"
    assert receipt["sourceRoot"] == str(REPO_ROOT)
    assert receipt["overlayRoot"] == ""
    assert receipt["sourceMarkerChecks"]
    assert receipt["publicPwaStaticProof"]["status"] == "pass"
    assert receipt["publicPwaStaticProof"]["testScope"] == "source-markers-only"
    assert isinstance(receipt["operationalMirrorChecks"], list)
    assert receipt["overlayMarkerChecks"] == []
    assert all(not check["missingMarkers"] for check in receipt["sourceMarkerChecks"])
    checks = {check["path"]: check for check in receipt["sourceMarkerChecks"]}
    assert "Chummer.Run.Api/Views/PublicLanding/Landing.cshtml" in checks
    assert "docker-compose.public-edge.yml" in checks
    assert "Chummer.Run.Api/Program.cs" in checks
    assert "Chummer.Run.Api/Controllers/PublicLandingController.cs" in checks
    assert "Chummer.Run.Api/Views/PublicLanding/MobileProjection.cshtml" in checks
    assert "Chummer.Run.Api/play-worker-projection.json" in checks
    assert "Chummer.Run.Api/play-pwa-required-inventory.json" in checks
    assert "Chummer.Run.Api/public-pwa-proof-authority.json" in checks
    assert "Chummer.Run.Api/play-pwa-mirrors.json" in checks
    assert "scripts/generate_public_play_worker_projection.py" in checks
    compose_contract = receipt["publicPwaComposeContextContract"]
    assert compose_contract["status"] == "pass"
    assert compose_contract["buildContext"] == module.PUBLIC_EDGE_COMPOSE_BUILD_CONTEXT
    assert compose_contract["dockerfile"] == module.PUBLIC_EDGE_COMPOSE_DOCKERFILE
    assert compose_contract["bindings"] == module.PUBLIC_EDGE_COMPOSE_NAMED_CONTEXTS
    assert compose_contract["expectedBindings"] == module.PUBLIC_EDGE_COMPOSE_NAMED_CONTEXTS
    assert all(compose_contract["bindingMatches"].values())
    assert not compose_contract["missingContextNames"]
    assert not compose_contract["unexpectedContextNames"]
    assert not compose_contract["reservedContextNames"]
    assert all(compose_contract["checks"].values())
    assert receipt["publicPwaDockerBuildContract"]["status"] == "pass"
    assert ".codex-design/product/PUBLIC_FEEDBACK_TAXONOMY.yaml" in checks
    assert ".codex-design/product/PUBLIC_FEEDBACK_AND_CONTENT_REGISTRY.yaml" in checks
    assert ".codex-design/product/PUBLIC_SIGNAL_FEEDBACK_ROADMAP_BRIDGE.md" in checks
    assert ".codex-design/product/PUBLIC_SIGNAL_TO_CANON_PIPELINE.md" in checks
    assert ".codex-design/product/ORIGIN_BOOK_STUDIO.md" in checks
    assert ".codex-design/product/public-guides/chummer6-quickstart.md" in checks
    landing_required = checks["Chummer.Run.Api/Views/PublicLanding/Landing.cshtml"]["requiredMarkers"]
    assert 'data-mobile-app-handoff="build-mobile-app-handoff"' in landing_required
    assert 'data-mobile-app-handoff="mobile-app-handoff"' in landing_required
    assert "Target: MobileAppHandoffTarget.Build" in landing_required
    assert "Target: MobileAppHandoffTarget.Play" in landing_required
    assert 'profiles: ["play-private"]' in checks["docker-compose.public-edge.yml"]["requiredMarkers"]
    assert 'CHUMMER_PUBLIC_PLAY_PROXY_ENABLED: "false"' in checks["docker-compose.public-edge.yml"]["requiredMarkers"]
    assert 'CHUMMER_PUBLIC_PLAY_LIVE_SESSION_PROXY_ENABLED: "false"' in checks["docker-compose.public-edge.yml"]["requiredMarkers"]
    assert "${CHUMMER_PUBLIC_PLAY_PROXY_ENABLED" in checks["docker-compose.public-edge.yml"]["forbiddenMarkers"]
    assert "${CHUMMER_PUBLIC_PLAY_LIVE_SESSION_PROXY_ENABLED" in checks["docker-compose.public-edge.yml"]["forbiddenMarkers"]
    assert "${CHUMMER_PUBLIC_PORTAL_APP_OVERLAY_DIR:-/docker/chummercomplete/chummer.run-services/.state/public-edge-portal-overlay/app}:/app:ro" in checks["docker-compose.public-edge.yml"]["requiredMarkers"]
    compose_required = checks["docker-compose.public-edge.yml"]["requiredMarkers"]
    assert 'CHUMMER_PUBLIC_PROJECTION_SNAPSHOT_ROOT: /public-projection' in compose_required
    assert 'CHUMMER_PUBLIC_PROJECTION_SNAPSHOT_REQUIRED: "true"' in compose_required
    assert (
        "${CHUMMER_PUBLIC_EDGE_PROJECTION_SNAPSHOT_ROOT:?Set the authenticated public projection snapshot root}:/public-projection:ro"
        in compose_required
    )
    assert "TryResolveRoleAliasRedirectPath" in checks["Chummer.Run.Api/Program.cs"]["requiredMarkers"]
    program_markers = checks["Chummer.Run.Api/Program.cs"]["requiredMarkers"]
    assert 'path.Equals("/jammer", StringComparison.OrdinalIgnoreCase)' in program_markers
    assert 'context.Response.Headers["Referrer-Policy"] = "no-referrer";' in program_markers
    assert 'context.Response.Headers.CacheControl = "private, no-store, no-cache, max-age=0";' in program_markers
    assert 'context.Response.Redirect($"{redirectPath}#", permanent: false);' in program_markers
    assert "string destination = context.Request.QueryString.HasValue" in checks["Chummer.Run.Api/Program.cs"]["forbiddenMarkers"]
    play_controller_markers = checks["Chummer.Run.Api/Controllers/PublicLandingController.cs"]["requiredMarkers"]
    assert "ResolveCanonicalPlayRoleFromQuery(Request.Query)" in play_controller_markers
    assert 'return Redirect($"/mobile/{canonicalRole}");' in play_controller_markers
    assert '[HttpGet("/jammer")]' in play_controller_markers
    assert '[HttpHead("/jammer")]' in play_controller_markers
    assert 'RedirectToPrivateMobileAlias("/mobile/player")' in play_controller_markers
    assert 'return Redirect($"{targetPath}#");' in play_controller_markers
    assert 'InstallTargetPath: "/mobile/player"' in play_controller_markers
    assert 'InstallTargetPath: "/mobile/gm"' in play_controller_markers
    assert 'InstallTargetPath: "/mobile/observer"' in play_controller_markers
    role_view_markers = checks["Chummer.Run.Api/Views/PublicLanding/MobileProjection.cshtml"]["requiredMarkers"]
    assert "data-mobile-app-inline-qr" in role_view_markers
    assert 'data-role-privacy-warning="@roleProfile.RoleKey"' in role_view_markers
    assert 'data-role-authority-warning="@roleProfile.RoleKey"' in role_view_markers
    generator_markers = checks["scripts/generate_public_play_worker_projection.py"]["requiredMarkers"]
    assert 'GENERATOR_CONTRACT = "play-root-worker-projection-generator-v1"' in generator_markers
    assert "projected worker differs from deterministic output" in generator_markers
    mirror_markers = checks["Chummer.Run.Api/play-pwa-mirrors.json"]["requiredMarkers"]
    assert '"contract": "play-install-mirror-v5"' in mirror_markers
    assert '"inventoryContract": "play-install-mirror-required-inventory-v2"' in mirror_markers
    assert '"policyId": "chummer.public-play-pwa-mirror.v1"' in mirror_markers
    assert '"command": "python3 scripts/generate_public_play_worker_projection.py"' in mirror_markers
    docker_check = checks["Chummer.Run.Api/Dockerfile"]
    docker_markers = docker_check["requiredMarkers"]
    assert "RUN apt-get update" not in docker_markers
    assert "apt-get install -y --no-install-recommends python3" not in docker_markers
    assert "rm -rf /var/lib/apt/lists/*" not in docker_markers
    assert "RUN python3 --version" not in docker_markers
    assert module.PUBLIC_EDGE_DOCKER_PACKAGE_FEED_FROM in docker_markers
    assert module.PUBLIC_EDGE_DOCKER_BUILD_FROM in docker_markers
    assert module.PUBLIC_EDGE_DOCKER_PACKAGE_FEED_PROOF_RECEIPT_COPY in docker_markers
    assert module.PUBLIC_EDGE_DOCKER_PACKAGE_FEED_PYTHON_COPY in docker_markers
    assert module.PUBLIC_EDGE_DOCKER_PACKAGE_FEED_COPY in docker_markers
    assert 'grep -Fq \'const CACHE_VERSION = "v19";\'' in docker_markers
    assert "WORKDIR /proof" in docker_markers
    assert 'RUN ["/usr/local/bin/python3", "-I", "-S"' in docker_markers
    assert '"--receipt", "/proof/public-pwa-proof-authority.receipt.json"' in docker_markers
    assert module.PUBLIC_EDGE_DOCKER_RECEIPT_COPY in docker_markers
    docker_contract = docker_check["dockerBuildContract"]
    assert docker_contract["status"] == "pass"
    assert docker_contract["proofStageCount"] == 1
    assert docker_contract["packageFeedStageCount"] == 1
    assert docker_contract["pythonInvocationCount"] == 1
    assert docker_contract["packageFeedPythonInvocationCount"] == 1
    assert all(docker_contract["checks"].values())
    assert not docker_contract["failures"]
    assert "! grep -Fq 'self.skipWaiting()'" in docker_markers
    assert "mkdir -p /app/state" in docker_markers
    ready_mobile_markers = checks["Chummer.Run.Api/Services/ReadyForTonightService.cs"]["requiredMarkers"]
    assert 'frontdoor_launch_route = "/mobile/player"' in ready_mobile_markers
    assert "role_routes = new[]" in ready_mobile_markers
    assert 'route = "/mobile/player"' in ready_mobile_markers
    assert 'route = "/mobile/gm"' in ready_mobile_markers
    assert 'manifest_path = "/manifest.player.webmanifest"' in ready_mobile_markers
    assert 'manifest_path = "/manifest.gm.webmanifest"' in ready_mobile_markers
    assert 'manifest_start_url = "/mobile/player"' in ready_mobile_markers
    assert 'manifest_start_url = "/mobile/gm"' in ready_mobile_markers
    assert "key: mobile_companion" in checks[".codex-design/product/PUBLIC_FEEDBACK_TAXONOMY.yaml"]["requiredMarkers"]
    assert "key: productlift_public_feedback" in checks[".codex-design/product/PUBLIC_FEEDBACK_AND_CONTENT_REGISTRY.yaml"]["requiredMarkers"]
    assert "# Public signal to canon pipeline" in checks[".codex-design/product/PUBLIC_SIGNAL_TO_CANON_PIPELINE.md"]["requiredMarkers"]
    assert "# ORIGIN BOOK STUDIO" in checks[".codex-design/product/ORIGIN_BOOK_STUDIO.md"]["requiredMarkers"]
    assert "# Chummer6 Quickstart Guide" in checks[".codex-design/product/public-guides/chummer6-quickstart.md"]["requiredMarkers"]
    jammer_manifest_markers = checks[".codex-design/product/PUBLIC_LANDING_MANIFEST.yaml"]["requiredMarkers"]
    assert "- path: /jammer" in jammer_manifest_markers
    assert "placeholder_requirements: no-authority Jammer Companion alias only" in jammer_manifest_markers
    landing_markers = checks["Chummer.Run.Api/Views/PublicLanding/Landing.cshtml"]["requiredMarkers"]
    assert "#turn-runsite-card" in landing_markers
    assert 'const normalizedHash = window.location.hash.split("?")[0];' in landing_markers
    assert 'window.location.replace(`/mobile/player${normalizedHash}`);' in landing_markers
    assert "site-open-chummer-menu__button--disabled" in checks["Chummer.Run.Api/Views/PublicLanding/Landing.cshtml"]["forbiddenMarkers"]
    assert not checks["Chummer.Run.Api/Dockerfile"]["presentForbiddenMarkers"]


def test_public_pwa_static_proof_receipt_is_sanitized_and_bounded(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_module()
    source_root = tmp_path / "private-workspace" / "chummer.run-services"
    source_root.mkdir(parents=True)
    configure_fake_public_pwa_identities(module, source_root)

    def fake_run(command, **kwargs):
        write_fake_child_receipt(
            command,
            json.dumps(
                {
                    "status": "fail",
                    "failures": [
                        f"{source_root}/private/file-{index}: token=must-not-survive " + ("x" * 500)
                        for index in range(module.MAX_PUBLIC_PWA_PROOF_FAILURES + 5)
                    ],
                    "mirror": {},
                }
            ).encode("utf-8"),
        )
        assert kwargs["stdout"] is module.subprocess.DEVNULL
        assert kwargs["stderr"] is module.subprocess.DEVNULL
        assert kwargs["timeout"] == module.PUBLIC_PWA_PROOF_TIMEOUT_SECONDS
        assert command[1:4] == ["-I", "-S", "-c"]
        wrapper_argument = command.index("-c") + 2
        required_descriptors = {
            int(command[wrapper_argument]),
            int(command[wrapper_argument + 3]),
            int(command[command.index("--trusted-generator-fd") + 1]),
            int(command[command.index("--output-fd") + 1]),
            int(command[command.index("--trusted-input-manifest-fd") + 1]),
        }
        assert required_descriptors.issubset(set(kwargs["pass_fds"]))
        assert len(kwargs["pass_fds"]) == len(module.expected_public_pwa_input_paths()) + 5
        assert kwargs["env"]["PYTHONNOUSERSITE"] == "1"
        assert (
            kwargs["preexec_fn"]
            is module.install_public_pwa_child_resource_limits_before_exec
        )
        return module.subprocess.CompletedProcess(command, 1)

    monkeypatch.setattr(module.subprocess, "run", fake_run)

    receipt = module.execute_public_pwa_static_proof(source_root)

    assert receipt["status"] == "fail"
    assert receipt["failuresTruncated"] is True
    assert len(receipt["failures"]) == module.MAX_PUBLIC_PWA_PROOF_FAILURES
    assert receipt["failureCount"] > len(receipt["failures"])
    assert all(len(item) <= module.MAX_PUBLIC_PWA_PROOF_DETAIL_CHARS for item in receipt["failures"])
    rendered = json.dumps(receipt)
    assert str(source_root) not in rendered
    assert "must-not-survive" not in rendered
    assert "token=<redacted>" in rendered


def test_public_pwa_input_snapshot_policy_is_closed_at_25_plus_12() -> None:
    module = load_module()
    expected = module.expected_public_pwa_input_paths()
    assert len(expected) == 37
    assert sum(1 for root, _ in expected if root == "run-services") == 25
    assert sum(1 for root, _ in expected if root == "play") == 12
    assert ("run-services", "Chummer.Run.Api/Dockerfile") in expected
    assert (
        "run-services",
        "scripts/validate_public_pwa_proof_authority.py",
    ) in expected
    assert (
        "run-services",
        "Chummer.Run.Api/wwwroot/js/mobile-app-handoff.js",
    ) in expected
    assert (
        "run-services",
        "Chummer.Run.Api/wwwroot/manifest.webmanifest",
    ) in expected


def test_public_pwa_static_proof_hard_times_out_without_output_capture(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_module()
    source_root = tmp_path / "workspace" / "chummer.run-services"
    source_root.mkdir(parents=True)
    configure_fake_public_pwa_identities(module, source_root)

    def fake_run(command, **kwargs):
        assert kwargs["stdout"] is module.subprocess.DEVNULL
        assert kwargs["stderr"] is module.subprocess.DEVNULL
        raise module.subprocess.TimeoutExpired(command, kwargs["timeout"])

    monkeypatch.setattr(module.subprocess, "run", fake_run)

    receipt = module.execute_public_pwa_static_proof(source_root)

    assert receipt["status"] == "fail"
    assert receipt["checks"]["subprocessCompleted"] is False
    assert any("hard timeout" in failure for failure in receipt["failures"])


def test_public_pwa_static_proof_rejects_oversized_child_receipt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_module()
    source_root = tmp_path / "workspace" / "chummer.run-services"
    source_root.mkdir(parents=True)
    configure_fake_public_pwa_identities(module, source_root)

    def fake_run(command, **kwargs):
        write_fake_child_receipt(
            command,
            b"x" * (module.MAX_PUBLIC_PWA_PROOF_RECEIPT_BYTES + 1),
        )
        assert kwargs["stdout"] is module.subprocess.DEVNULL
        assert kwargs["stderr"] is module.subprocess.DEVNULL
        return module.subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(module.subprocess, "run", fake_run)

    receipt = module.execute_public_pwa_static_proof(source_root)

    assert receipt["status"] == "fail"
    assert any("size limit" in failure for failure in receipt["failures"])


def test_public_pwa_static_proof_rejects_identity_drift_before_execution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_module()
    source_root = tmp_path / "workspace" / "chummer.run-services"
    source_root.mkdir(parents=True)
    pins = configure_fake_public_pwa_identities(module, source_root)
    generator_path = source_root / pins["generator"][0]
    generator_path.write_text("drift\n", encoding="utf-8")
    called = False

    def fake_run(command, **kwargs):
        nonlocal called
        called = True
        return module.subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(module.subprocess, "run", fake_run)

    receipt = module.execute_public_pwa_static_proof(source_root)

    assert receipt["status"] == "fail"
    assert receipt["checks"]["identityPinned"] is False
    assert called is False


def test_public_pwa_static_proof_revalidates_identities_after_execution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_module()
    source_root = tmp_path / "workspace" / "chummer.run-services"
    source_root.mkdir(parents=True)
    pins = configure_fake_public_pwa_identities(module, source_root)

    def fake_run(command, **kwargs):
        write_fake_child_receipt(command, b"{}\n")
        policy_path = source_root / pins["policy"][0]
        policy_path.write_text("changed-during-proof\n", encoding="utf-8")
        return module.subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(module.subprocess, "run", fake_run)

    receipt = module.execute_public_pwa_static_proof(source_root)

    assert receipt["status"] == "fail"
    assert receipt["checks"]["identityPinned"] is True
    assert receipt["checks"]["identityRevalidated"] is False
    assert any("changed during subprocess" in failure for failure in receipt["failures"])


def test_public_pwa_identity_reader_rejects_symlinked_component(tmp_path: Path) -> None:
    module = load_module()
    source_root = tmp_path / "workspace" / "chummer.run-services"
    scripts = source_root / "scripts-real"
    scripts.mkdir(parents=True)
    (scripts / "verify.py").write_text("trusted\n", encoding="utf-8")
    (source_root / "scripts").symlink_to(scripts, target_is_directory=True)

    try:
        module.read_public_pwa_identity_file(source_root, "scripts/verify.py")
    except RuntimeError as exc:
        assert "symlink" in str(exc)
    else:
        raise AssertionError("symlinked identity component was accepted")


def test_public_pwa_program_execution_survives_snapshot_path_swap_and_restore(
    tmp_path: Path,
) -> None:
    module = load_module()
    source = tmp_path / "source" / "verifier.py"
    source.parent.mkdir(parents=True)
    safe_payload = b"VALUE = 'safe'\n"
    source.write_bytes(safe_payload)
    digest = hashlib.sha256(safe_payload).hexdigest()
    binding = module.snapshot_public_pwa_identity(
        "verifier",
        source,
        safe_payload,
        source.stat(),
        digest,
        tmp_path / "authority",
    )
    snapshot = Path(binding["snapshotPath"])

    with module.sealed_public_pwa_program_execution(binding) as execution:
        descriptor = int(execution["descriptor"])
        saved = snapshot.with_suffix(snapshot.suffix + ".saved")
        snapshot.rename(saved)
        snapshot.write_bytes(b"VALUE = 'malicious'\n")
        os.lseek(descriptor, 0, os.SEEK_SET)
        assert os.read(descriptor, len(safe_payload) + 32) == safe_payload
        snapshot.unlink()
        saved.rename(snapshot)

    refreshed = module.refresh_public_pwa_snapshot_binding(binding)
    assert refreshed["status"] == "fail"
    assert refreshed["checks"]["directoryIdentity"] is False


def test_public_pwa_preflight_uses_descriptor_receipt_during_snapshot_swap_and_restore(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_module()
    source_root = tmp_path / "workspace" / "chummer.run-services"
    source_root.mkdir(parents=True)
    configure_fake_public_pwa_identities(module, source_root)

    def fake_run(command, **kwargs):
        assert "--output" not in command
        assert "--output-fd" in command
        verifier_descriptor = int(command[command.index("-c") + 2])
        os.lseek(verifier_descriptor, 0, os.SEEK_SET)
        assert os.read(verifier_descriptor, 1024) == b"verifier-trusted-identity\n"

        snapshot_root = Path(kwargs["env"]["TMPDIR"]) / "authority"
        verifier_snapshot = next(
            path for path in snapshot_root.iterdir() if path.name.startswith("verifier.")
        )
        saved = verifier_snapshot.with_suffix(verifier_snapshot.suffix + ".saved")
        verifier_snapshot.rename(saved)
        verifier_snapshot.write_text("malicious verifier\n", encoding="utf-8")
        forged_path_receipt = Path(kwargs["env"]["TMPDIR"]) / "receipt.json"
        forged_path_receipt.write_text(
            json.dumps({"status": "pass", "failures": ["path-forgery"]}),
            encoding="utf-8",
        )
        write_fake_child_receipt(
            command,
            json.dumps(
                {"status": "fail", "failures": ["descriptor-safe"], "mirror": {}}
            ).encode("utf-8"),
        )
        verifier_snapshot.unlink()
        saved.rename(verifier_snapshot)
        return module.subprocess.CompletedProcess(command, 1)

    monkeypatch.setattr(module.subprocess, "run", fake_run)
    receipt = module.execute_public_pwa_static_proof(source_root)

    assert receipt["status"] == "fail"
    assert receipt["checks"]["verifierSealed"] is True
    assert receipt["checks"]["generatorSealed"] is True
    assert receipt["checks"]["snapshotRevalidated"] is False
    assert receipt["checks"]["identityRevalidated"] is True
    assert receipt["checks"]["receiptDescriptorBound"] is True
    assert receipt["subprocess"]["receiptMode"] == "sealed_inherited_memfd"
    assert any("descriptor-safe" in failure for failure in receipt["failures"])
    assert any("snapshots changed" in failure for failure in receipt["failures"])
    assert all("path-forgery" not in failure for failure in receipt["failures"])


@pytest.mark.parametrize(
    "target_kind",
    ("run_root", "play_root", "run_subdirectory", "run_file"),
)
def test_public_pwa_real_subprocess_rejects_path_swap_and_restore(
    public_pwa_workspace: Path,
    target_kind: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_module()
    source_root = copy_current_public_pwa_proof_fixture(
        module,
        public_pwa_workspace,
    )
    targets = {
        "run_root": source_root,
        "play_root": source_root.parent / "chummer-play",
        "run_subdirectory": source_root / "Chummer.Run.Api/wwwroot",
        "run_file": source_root / "Chummer.Run.Api/wwwroot/mobile.css",
    }
    target = targets[target_kind]

    def mutate(command, kwargs):
        saved = target.with_name(target.name + ".saved")
        target.rename(saved)
        if saved.is_dir():
            target.mkdir()
            (target / "attacker-marker").write_text("replacement\n", encoding="utf-8")
        else:
            target.write_text("replacement\n", encoding="utf-8")

        def undo() -> None:
            if target.is_dir():
                shutil.rmtree(target)
            else:
                target.unlink(missing_ok=True)
            saved.rename(target)

        return undo

    monkeypatch.setattr(
        module.subprocess,
        "run",
        real_subprocess_with_swap(module, mutate),
    )
    receipt = module.execute_public_pwa_static_proof(source_root)

    assert receipt["status"] == "fail"
    assert receipt["checks"]["verifierSealed"] is True
    assert receipt["checks"]["generatorSealed"] is True
    assert receipt["checks"]["inputManifestSealed"] is True
    assert receipt["checks"]["subprocessSucceeded"] is (target_kind != "run_root")
    assert receipt["checks"]["inputManifestBound"] is True
    assert receipt["checks"]["inputReceiptExact"] is True
    assert (
        receipt["checks"]["inputSnapshotRevalidated"] is False
        or receipt["checks"]["rootPathsRevalidated"] is False
    )
    assert any("changed during subprocess" in failure for failure in receipt["failures"])


def test_public_pwa_real_subprocess_ignores_hostile_home_sitecustomize(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_module()
    marker = tmp_path / "sitecustomize-executed"
    with tempfile.TemporaryDirectory(
        prefix=".pwa-site-isolation-",
        dir=REPO_ROOT.parent,
    ) as fixture_dir:
        source_root = copy_current_public_pwa_proof_fixture(
            module,
            Path(fixture_dir),
        )
        real_run = module.subprocess.run

        def run_with_hostile_home(command, **kwargs):
            home = Path(kwargs["env"]["HOME"])
            user_site = (
                home
                / ".local"
                / "lib"
                / f"python{sys.version_info.major}.{sys.version_info.minor}"
                / "site-packages"
            )
            write_hostile_python_startup_module(user_site / "sitecustomize.py", marker)
            return real_run(command, **kwargs)

        monkeypatch.setattr(module.subprocess, "run", run_with_hostile_home)
        receipt = module.execute_public_pwa_static_proof(source_root)

    assert receipt["status"] == "pass"
    assert receipt["checks"]["subprocessSucceeded"] is True
    assert not marker.exists()
    assert "forged-python-startup" not in json.dumps(receipt, sort_keys=True)


def test_public_pwa_real_subprocess_ignores_workspace_argparse_shadow(
    tmp_path: Path,
) -> None:
    module = load_module()
    marker = tmp_path / "argparse-shadow-executed"
    with tempfile.TemporaryDirectory(
        prefix=".pwa-path-isolation-",
        dir=REPO_ROOT.parent,
    ) as fixture_dir:
        source_root = copy_current_public_pwa_proof_fixture(
            module,
            Path(fixture_dir),
        )
        write_hostile_python_startup_module(source_root.parent / "argparse.py", marker)
        receipt = module.execute_public_pwa_static_proof(source_root)

    assert receipt["status"] == "pass"
    assert receipt["checks"]["subprocessSucceeded"] is True
    assert not marker.exists()
    assert "forged-python-startup" not in json.dumps(receipt, sort_keys=True)


def test_public_pwa_real_subprocess_rejects_manifest_fd_substitution(
    public_pwa_workspace: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_module()
    source_root = copy_current_public_pwa_proof_fixture(
        module,
        public_pwa_workspace,
    )
    real_run = module.subprocess.run

    def substitute_manifest_descriptor(command, **kwargs):
        altered = list(command)
        manifest_index = altered.index("--trusted-input-manifest-fd") + 1
        generator_index = altered.index("--trusted-generator-fd") + 1
        altered[manifest_index] = altered[generator_index]
        return real_run(altered, **kwargs)

    monkeypatch.setattr(module.subprocess, "run", substitute_manifest_descriptor)
    receipt = module.execute_public_pwa_static_proof(source_root)

    assert receipt["status"] == "fail"
    assert receipt["checks"]["subprocessCompleted"] is True
    assert receipt["checks"]["inputManifestBound"] is False
    assert any("sealed input manifest" in failure for failure in receipt["failures"])


def test_public_pwa_real_subprocess_rejects_source_root_path_replacement(
    public_pwa_workspace: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_module()
    source_root = copy_current_public_pwa_proof_fixture(
        module,
        public_pwa_workspace,
    )
    replacement_root = (
        public_pwa_workspace / "replacement" / "chummer.run-services"
    )
    (replacement_root / "Chummer.Run.Api").mkdir(parents=True)
    (replacement_root.parent / "chummer-play").mkdir()
    real_run = module.subprocess.run

    def replace_source_root_argument(command, **kwargs):
        altered = list(command)
        altered[altered.index("--source-root") + 1] = str(replacement_root)
        return real_run(altered, **kwargs)

    monkeypatch.setattr(module.subprocess, "run", replace_source_root_argument)
    receipt = module.execute_public_pwa_static_proof(source_root)

    assert receipt["status"] == "fail"
    assert receipt["checks"]["subprocessCompleted"] is True
    assert receipt["checks"]["inputManifestBound"] is False
    assert any("sealed input manifest" in failure for failure in receipt["failures"])


def test_public_pwa_reviewed_sha_authority_is_the_single_code_gate() -> None:
    module = load_module()
    authority = json.loads(
        (REPO_ROOT / module.PUBLIC_PWA_PROOF_AUTHORITY_RELATIVE_PATH).read_text(
            encoding="utf-8"
        )
    )
    preflight_text = SCRIPT.read_text(encoding="utf-8")
    dockerfile_text = (REPO_ROOT / "Chummer.Run.Api/Dockerfile").read_text(encoding="utf-8")

    for role, (path_field, digest_field) in module.PUBLIC_PWA_PROOF_AUTHORITY_FIELDS.items():
        path = REPO_ROOT / authority[path_field]
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        assert authority[digest_field] == digest, role
        assert digest not in preflight_text
        assert digest not in dockerfile_text

    assert (
        "FROM python:3.12-slim@sha256:"
        "c3d81d25b3154142b0b42eb1e61300024426268edeb5b5a26dd7ddf64d9daf28 "
        "AS public-pwa-proof"
    ) in dockerfile_text
    assert 'RUN ["/usr/local/bin/python3", "-I", "-S"' in dockerfile_text
    assert '"--authority", "Chummer.Run.Api/public-pwa-proof-authority.json"' in dockerfile_text
    assert '"--mirror", "Chummer.Run.Api/play-pwa-mirrors.json"' in dockerfile_text
    assert '"--projection", "Chummer.Run.Api/play-worker-projection.json"' in dockerfile_text
    assert '"--template", "Chummer.Run.Api/service-worker.public-edge.template.js"' in dockerfile_text
    assert '"--receipt", "/proof/public-pwa-proof-authority.receipt.json"' in dockerfile_text
    assert (
        'grep -Fq "\\"inventorySha256\\": \\"${inventory_sha}\\"" '
        "public-pwa-proof-authority.json"
    ) not in dockerfile_text
    assert (
        'grep -Fq "\\"generatorSha256\\": \\"${generator_sha}\\"" '
        "public-pwa-proof-authority.json"
    ) not in dockerfile_text
    assert (
        'grep -Fq "\\"verifierSha256\\": \\"${verifier_sha}\\"" '
        "public-pwa-proof-authority.json"
    ) not in dockerfile_text
    assert 'grep -Fq \'"contract": "play-install-mirror-required-inventory-v2"\'' not in dockerfile_text
    assert 'grep -Fq \'"assetPolicyCount": 12\'' not in dockerfile_text
    assert 'grep -Fq \'"dependencyPolicyCount": 4\'' not in dockerfile_text
    assert '"templateSha256": "${template_sha}"' not in dockerfile_text
    assert '"projectionSha256": "${template_sha}"' not in dockerfile_text


def test_public_pwa_dockerfile_has_exact_pinned_validator_stage_and_receipt_dependency() -> None:
    module = load_module()
    contract = module.validate_public_pwa_docker_build_contract(
        REPO_ROOT / "Chummer.Run.Api/Dockerfile"
    )

    assert contract["status"] == "pass"
    assert contract["proofStageCount"] == 1
    assert contract["packageFeedStageCount"] == 1
    assert contract["buildStageCount"] == 1
    assert contract["toolFinalStageCount"] == 1
    assert contract["finalStageCount"] == 1
    assert contract["stageAliases"] == [
        "public-pwa-proof",
        "hub-package-feed",
        "build",
        "install-linking-postgres-tool-final",
        "final",
    ]
    assert contract["stageDependencies"] == {
        "public-pwa-proof": [],
        "hub-package-feed": ["public-pwa-proof"],
        "build": ["hub-package-feed", "public-pwa-proof"],
        "install-linking-postgres-tool-final": ["build"],
        "final": ["build"],
    }
    assert contract["pythonInvocationCount"] == 1
    assert contract["packageFeedPythonInvocationCount"] == 1
    assert contract["checks"] == {
        "exactSyntaxDirective": True,
        "noLateParserDirectives": True,
        "noHeredoc": True,
            "validLogicalInstructions": True,
            "noGlobalInstructions": True,
            "noOnbuildInstructions": True,
            "noAddInstructions": True,
        "exactProofStage": True,
        "exactPackageFeedStage": True,
        "exactStageHeaders": True,
        "singleProofStage": True,
        "proofStageNotDerived": True,
        "exactPackageFeedStageCount": True,
        "exactBuildStage": True,
        "exactBuildStageInstructions": True,
        "exactToolFinalStage": True,
        "exactFinalStage": True,
        "exactStageSetAndOrder": True,
        "defaultStageIsFinal": True,
        "exactReceiptDependency": True,
        "receiptIsFirstBuildInstruction": True,
        "exactPackageFeedProofReceiptDependency": True,
        "exactPackageFeedPythonDependency": True,
        "exactPackageFeedConsumption": True,
        "exactCoreRuntimeFeedConsumption": True,
        "noOtherProofCopies": True,
        "exactToolPublishDependency": True,
        "exactFinalPublishDependency": True,
        "exactLoopbackProbePublishDependency": True,
        "publicImageExcludesOperatorTool": True,
        "exactToolPayloadMode": True,
        "exactFinalPayloadMode": True,
        "exactCopyFromReferences": True,
        "noUnqualifiedCopies": True,
        "namedContextsOnlyInReviewedCopies": True,
        "noMountFromInstructions": True,
        "noNonCopyFromOptions": True,
        "noContextSelectingCopyFromIndirection": True,
        "noContextSelectionContinuations": True,
        "exactRequiredNamedContextCopies": True,
        "packageFeedDependsOnProof": True,
        "buildDependsOnPackageFeed": True,
        "buildDependsOnProof": True,
        "toolFinalDependsOnBuild": True,
        "finalDependsOnBuild": True,
        "allTargetsProofGated": True,
    }
    assert not contract["failures"]


@pytest.mark.parametrize(
    "instruction",
    (
        "COPY --from=hub-registry-source README.md /tmp/unreviewed-hub-input",
        "COPY --from=design-product products/chummer/ /tmp/unreviewed-design-input/",
        "COPY --from=fleet-media-factory-contracts . /tmp/unreviewed-media-input/",
        "COPY --from=run-services-source README.md /tmp/unreviewed-run-input",
        "ADD --from=run-services-source README.md /tmp/unreviewed-add-input",
    ),
)
def test_public_pwa_docker_contract_rejects_every_extra_named_context_copy_or_add(
    tmp_path: Path,
    instruction: str,
) -> None:
    module = load_module()
    source_root = write_complete_marker_source_tree(module, tmp_path / "source")
    dockerfile = source_root / module.PUBLIC_EDGE_DOCKERFILE_RELATIVE_PATH
    original = dockerfile.read_text(encoding="utf-8")
    insertion_stage = (
        module.PUBLIC_EDGE_DOCKER_FINAL_FROM
        if "--from=design-product" in instruction
        else module.PUBLIC_EDGE_DOCKER_TOOL_FINAL_FROM
    ) + "\n"
    assert insertion_stage in original
    dockerfile.write_text(
        original.replace(
            insertion_stage,
            insertion_stage + instruction + "\n"
            if "--from=design-product" in instruction
            else instruction + "\n" + insertion_stage,
            1,
        ),
        encoding="utf-8",
    )

    contract = module.validate_public_pwa_docker_build_contract(dockerfile)

    assert contract["status"] == "fail"
    if instruction.startswith("ADD "):
        assert contract["checks"]["noAddInstructions"] is False
    else:
        assert contract["checks"]["exactRequiredNamedContextCopies"] is False


@pytest.mark.parametrize(
    ("mutation", "failed_check"),
    (
        ("literal_run_mount", "namedContextsOnlyInReviewedCopies"),
        ("variable_run_mount", "noMountFromInstructions"),
        ("onbuild_mount", "noMountFromInstructions"),
        ("onbuild_copy", "namedContextsOnlyInReviewedCopies"),
        ("context_from", "namedContextsOnlyInReviewedCopies"),
        ("stage_alias_collision", "namedContextsOnlyInReviewedCopies"),
        ("arg_context_literal", "namedContextsOnlyInReviewedCopies"),
        ("copy_from_variable", "noContextSelectingCopyFromIndirection"),
        ("noncopy_from_option", "noNonCopyFromOptions"),
        ("case_variant", "namedContextsOnlyInReviewedCopies"),
        ("continuation_variant", "noContextSelectionContinuations"),
        ("heredoc", "noHeredoc"),
    ),
)
def test_public_pwa_docker_contract_rejects_every_other_context_selection_form(
    tmp_path: Path,
    mutation: str,
    failed_check: str,
) -> None:
    module = load_module()
    original = (
        REPO_ROOT / module.PUBLIC_EDGE_DOCKERFILE_RELATIVE_PATH
    ).read_text(encoding="utf-8")
    final_from = module.PUBLIC_EDGE_DOCKER_FINAL_FROM
    reviewed_copy = next(
        instruction
        for instruction in (
            module.PUBLIC_EDGE_DOCKER_EXACT_NAMED_CONTEXT_COPIES_BY_STAGE[
                module.PUBLIC_EDGE_DOCKER_PROOF_STAGE
            ]
        )
        if "validate_public_pwa_proof_authority.py" in instruction
    )
    injected_instructions = {
        "literal_run_mount": (
            "RUN --mount=type=bind,from=run-services-source,"
            "source=.,target=/mnt true"
        ),
        "variable_run_mount": (
            "RUN --mount=type=bind,from=${SOURCE},source=.,target=/mnt true"
        ),
        "onbuild_mount": (
            "ONBUILD RUN --mount=type=bind,from=${SOURCE},"
            "source=.,target=/mnt true"
        ),
        "onbuild_copy": (
            "ONBUILD COPY --from=hub-registry-source "
            "black-ledger/ /tmp/black-ledger/"
        ),
        "context_from": "FROM run-services-source AS bypass",
        "arg_context_literal": "ARG SOURCE=design-product",
        "copy_from_variable": (
            "COPY --from=${SOURCE} README.md /tmp/unreviewed"
        ),
        "noncopy_from_option": (
            "RUN echo --from=run-services-source"
        ),
        "heredoc": "RUN <<EOF\ntrue\nEOF",
    }
    if mutation in injected_instructions:
        mutated = original.replace(
            final_from + "\n",
            final_from + "\n" + injected_instructions[mutation] + "\n",
            1,
        )
    elif mutation == "stage_alias_collision":
        mutated = original.replace(
            final_from,
            final_from.rsplit(" AS ", 1)[0] + " AS design-product",
            1,
        )
    elif mutation == "case_variant":
        mutated = original.replace(
            reviewed_copy,
            reviewed_copy.replace(
                "run-services-source",
                "RUN-SERVICES-SOURCE",
            ),
            1,
        )
    elif mutation == "continuation_variant":
        mutated = original.replace(
            reviewed_copy,
            reviewed_copy.replace(
                "run-services-source",
                "run-services-\\\nsource",
            ),
            1,
        )
    else:  # pragma: no cover - the parameter list is closed above.
        raise AssertionError(f"Unhandled Docker context mutation: {mutation}")
    assert mutated != original
    dockerfile = tmp_path / "Dockerfile"
    dockerfile.write_text(mutated, encoding="utf-8")

    contract = module.validate_public_pwa_docker_build_contract(dockerfile)

    assert contract["status"] == "fail"
    assert contract["checks"][failed_check] is False


@pytest.mark.parametrize(
    "instruction",
    (
        (
            "RUN --mount=type=bind,"
            "source=chummer-hub-registry/black-ledger,"
            "target=/mnt,ro cp -a /mnt /tmp/unreviewed-ledger"
        ),
        "RUN --mount=type=cache,target=/root/.cache true",
        "RUN --mount=type=secret,id=release-key,target=/run/key true",
        "RUN --mount=type=ssh,id=default true",
        (
            "RUN --mount=target=/mnt,"
            "source=chummer-hub-registry/black-ledger,"
            "type=bind,ro cp -a /mnt /tmp/unreviewed-ledger"
        ),
        "RUN --network=none --mount=type=cache,target=/root/.cache true",
        "rUn --MoUnT=TyPe=CaChE,TaRgEt=/root/.cache true",
        "RUN\t--mount=type=cache,target=/root/.cache true",
        "RUN --mount\t=\ttype=ssh,id=default true",
        "RUN --mount=type=cache,\\\n    target=/root/.cache true",
        "RUN \\\n    --mount=type=ssh,id=default true",
        "RUN --mou\\\nnt=type=cache,target=/root/.cache true",
    ),
)
def test_public_pwa_docker_contract_rejects_every_run_mount_form(
    tmp_path: Path,
    instruction: str,
) -> None:
    module = load_module()
    original = (
        REPO_ROOT / module.PUBLIC_EDGE_DOCKERFILE_RELATIVE_PATH
    ).read_text(encoding="utf-8")
    insertion_point = module.PUBLIC_EDGE_DOCKER_RECEIPT_COPY + "\n"
    mutated = original.replace(
        insertion_point,
        insertion_point + instruction + "\n",
        1,
    )
    assert mutated != original
    dockerfile = tmp_path / "Dockerfile"
    dockerfile.write_text(mutated, encoding="utf-8")

    contract = module.validate_public_pwa_docker_build_contract(dockerfile)

    assert contract["status"] == "fail"
    assert contract["checks"]["noMountFromInstructions"] is False
    if "\\\n" in instruction:
        assert contract["checks"]["noContextSelectionContinuations"] is False


@pytest.mark.parametrize(
    "instruction",
    (
        "ONBUILD",
        "ONBUILD RUN true",
        (
            "ONBUILD COPY --from=run-services-source "
            "Chummer.Run.Api/ /tmp/unreviewed/"
        ),
        "ONBUILD ADD https://example.invalid/payload /tmp/payload",
        "ONBUILD RUN --mount=type=cache,target=/root/.cache true",
        "oNbUiLd\tRuN true",
        "ONBUILD " + "\\\n" + "    RUN true",
        "ONBU" + "\\\n" + "ILD RUN true",
    ),
)
def test_public_pwa_docker_contract_rejects_every_onbuild_form(
    tmp_path: Path,
    instruction: str,
) -> None:
    module = load_module()
    original = (
        REPO_ROOT / module.PUBLIC_EDGE_DOCKERFILE_RELATIVE_PATH
    ).read_text(encoding="utf-8")
    insertion_point = module.PUBLIC_EDGE_DOCKER_RECEIPT_COPY + "\n"
    mutated = original.replace(
        insertion_point,
        insertion_point + instruction + "\n",
        1,
    )
    assert mutated != original
    dockerfile = tmp_path / "Dockerfile"
    dockerfile.write_text(mutated, encoding="utf-8")

    contract = module.validate_public_pwa_docker_build_contract(dockerfile)
    records, malformed_continuations = (
        module._docker_logical_instruction_records(mutated)
    )
    shared_findings = module._docker_context_policy_findings(records)

    assert not malformed_continuations
    assert contract["status"] == "fail"
    assert contract["checks"]["noOnbuildInstructions"] is False
    assert shared_findings["onbuildUses"]


@pytest.mark.parametrize(
    ("mutation", "failed_check"),
    (
        ("unreviewed_frontend", "exactSyntaxDirective"),
        ("late_syntax", "noLateParserDirectives"),
        ("escape_backtick", "noLateParserDirectives"),
        ("mixed_whitespace_escape", "noLateParserDirectives"),
    ),
)
def test_public_pwa_docker_contract_rejects_parser_syntax_switches(
    tmp_path: Path,
    mutation: str,
    failed_check: str,
) -> None:
    module = load_module()
    original = (
        REPO_ROOT / module.PUBLIC_EDGE_DOCKERFILE_RELATIVE_PATH
    ).read_text(encoding="utf-8")
    if mutation == "unreviewed_frontend":
        mutated = original.replace(
            module.PUBLIC_EDGE_DOCKERFILE_SYNTAX_DIRECTIVE,
            "# syntax=docker/dockerfile:1.7",
            1,
        )
    elif mutation == "late_syntax":
        mutated = original.replace(
            module.PUBLIC_EDGE_DOCKERFILE_SYNTAX_DIRECTIVE + "\n",
            module.PUBLIC_EDGE_DOCKERFILE_SYNTAX_DIRECTIVE
            + "\n# syntax=docker/dockerfile:1.7\n",
            1,
        )
    elif mutation in {"escape_backtick", "mixed_whitespace_escape"}:
        escape_directive = (
            "# escape=`"
            if mutation == "escape_backtick"
            else "\t#\tescape \t= `"
        )
        mutated = original.replace(
            module.PUBLIC_EDGE_DOCKERFILE_SYNTAX_DIRECTIVE + "\n",
            module.PUBLIC_EDGE_DOCKERFILE_SYNTAX_DIRECTIVE
            + "\n"
            + escape_directive
            + "\n",
            1,
        )
        insertion_point = module.PUBLIC_EDGE_DOCKER_RECEIPT_COPY + "\n"
        mutated = mutated.replace(
            insertion_point,
            insertion_point
            + "RUN --mou`\n"
            + "nt=type=bind,source=chummer-hub-registry/black-ledger,"
            + "target=/mnt cp -a /mnt /tmp/unreviewed-ledger\n",
            1,
        )
    else:  # pragma: no cover - the parameter list is closed above.
        raise AssertionError(f"Unhandled parser directive mutation: {mutation}")
    dockerfile = tmp_path / "Dockerfile"
    dockerfile.write_text(mutated, encoding="utf-8")

    contract = module.validate_public_pwa_docker_build_contract(dockerfile)

    assert contract["status"] == "fail"
    assert contract["checks"][failed_check] is False


def test_public_pwa_primary_context_exposes_no_source_repository() -> None:
    dockerignore = (
        REPO_ROOT / "Chummer.Run.Api" / "Dockerfile.dockerignore"
    ).read_text(encoding="utf-8")

    assert "!chummer-hub-registry" not in dockerignore
    assert dockerignore.splitlines()[:3] == ["*", "", "!.dockerignore"]


@pytest.mark.parametrize(
    ("mutation", "expected_failure"),
    (
        ("attached_comment_or_true", "exact pinned public PWA proof-stage"),
        ("exit_trap", "exact pinned public PWA proof-stage"),
        ("proof_env", "exact pinned public PWA proof-stage"),
        ("proof_arg", "exact pinned public PWA proof-stage"),
        ("shell_c", "exact pinned public PWA proof-stage"),
        ("command_substitution", "exact pinned public PWA proof-stage"),
        ("fake_interpreter", "exact pinned public PWA proof-stage"),
        ("onbuild", "exact pinned public PWA proof-stage"),
        ("derived_proof_stage", "must not be derived"),
        ("json_indirection", "exact pinned public PWA proof-stage"),
        ("mid_file_escape", "parser directives are forbidden"),
        ("extra_stage_instruction", "exact pinned public PWA proof-stage"),
        ("receipt_substitution", "exact proof receipt"),
        ("receipt_wrong_stage", "exact proof receipt"),
        ("global_arg", "exact pinned public PWA proof-stage"),
        ("global_env", "exact pinned public PWA proof-stage"),
        ("global_shell", "exact pinned public PWA proof-stage"),
        ("global_onbuild", "exact pinned public PWA proof-stage"),
        ("heredoc", "heredoc syntax is forbidden"),
        ("appended_default_bypass", "default/last stage must be final"),
        ("extra_independent_stage", "only public-pwa-proof, hub-package-feed"),
        ("detached_package_feed", "exact proof receipt"),
        ("package_feed_python_copy_removed", "pinned Python runtime"),
        ("package_feed_build_copy_removed", "consume the exact validated hub-package-feed"),
        ("package_feed_mutable_sdk", "stage FROM instructions drifted"),
        ("detached_final", "final stage must depend transitively on build"),
        ("direct_final_from_base", "final stage must depend transitively on build"),
        ("removed_build_dependency", "exact proof receipt"),
        ("renamed_build_stage", "only public-pwa-proof, hub-package-feed"),
        ("reordered_stages", "only public-pwa-proof, hub-package-feed"),
        ("duplicate_final_stage", "exactly one named final stage"),
        ("receipt_copy_decoy", "exact proof receipt"),
        ("receipt_copy_as_run_continuation", "exact proof receipt"),
        ("unknown_external_copy_source", "allowed earlier stage or named context"),
        ("numeric_copy_source", "allowed earlier stage or named context"),
        ("wrong_stage_named_context", "allowed earlier stage or named context"),
        ("initializer_copy_moved_to_build", "exact required named-context COPY set"),
        ("receipt_moved_after_publish", "first build-stage instruction"),
        ("final_publish_edge_removed", "exact build publish artifact"),
        (
            "loopback_probe_publish_edge_removed",
            "dedicated loopback probe artifact",
        ),
        (
            "operator_tool_copied_into_public_image",
            "must not include the InstallLinking operator tool",
        ),
        ("tool_publish_edge_removed", "exact tool publish artifact"),
        ("tool_payload_mode_removed", "normalize payload readability exactly once"),
        ("final_payload_mode_removed", "normalize payload readability and isolate state exactly once"),
        ("final_base_replaced", "stage FROM instructions drifted"),
        ("positional_fake_copy_from", "exact build publish artifact"),
        ("split_from_keyword_default_bypass", "default/last stage must be final"),
        ("split_copy_from_option_external", "allowed earlier stage or named context"),
    ),
)
def test_public_pwa_docker_contract_rejects_validator_stage_bypasses(
    tmp_path: Path,
    mutation: str,
    expected_failure: str,
) -> None:
    module = load_module()
    source_root = write_complete_marker_source_tree(module, tmp_path / "source")
    dockerfile = source_root / module.PUBLIC_EDGE_DOCKERFILE_RELATIVE_PATH
    original = dockerfile.read_text(encoding="utf-8")
    proof_from = module.PUBLIC_EDGE_DOCKER_PROOF_STAGE_INSTRUCTIONS[0] + "\n"
    proof_workdir = "WORKDIR /proof\n"
    proof_run = module.PUBLIC_EDGE_DOCKER_PROOF_RUN + "\n"
    receipt_copy = module.PUBLIC_EDGE_DOCKER_RECEIPT_COPY + "\n"
    package_feed_from = module.PUBLIC_EDGE_DOCKER_PACKAGE_FEED_FROM + "\n"
    package_feed_receipt_copy = (
        module.PUBLIC_EDGE_DOCKER_PACKAGE_FEED_PROOF_RECEIPT_COPY + "\n"
    )
    package_feed_python_copy = (
        module.PUBLIC_EDGE_DOCKER_PACKAGE_FEED_PYTHON_COPY + "\n"
    )
    package_feed_build_copy = module.PUBLIC_EDGE_DOCKER_PACKAGE_FEED_COPY + "\n"
    build_from = module.PUBLIC_EDGE_DOCKER_BUILD_FROM + "\n"
    final_from = module.PUBLIC_EDGE_DOCKER_FINAL_FROM + "\n"
    final_build_copies = (
        "COPY --from=build /app/publish .\n",
        "COPY --from=build /app/loopback-probe /app/loopback-probe/\n",
        "COPY --from=build /src/chummer.run-services/.codex-design /app/.codex-design\n",
        "COPY --from=build /src/chummer-hub-registry/black-ledger /app/black-ledger\n",
    )
    tool_publish_copy = module.PUBLIC_EDGE_DOCKER_TOOL_PUBLISH_COPY + "\n"
    tool_payload_mode = module.PUBLIC_EDGE_DOCKER_TOOL_PAYLOAD_MODE_RUN + "\n"
    final_payload_mode = module.PUBLIC_EDGE_DOCKER_FINAL_PAYLOAD_MODE_RUN + "\n"
    assert original.startswith(module.PUBLIC_EDGE_DOCKERFILE_SYNTAX_DIRECTIVE + "\n" + proof_from)
    assert proof_run in original
    assert receipt_copy in original

    if mutation == "attached_comment_or_true":
        mutated = original.replace(proof_run, proof_run.rstrip("\n") + "#ignored || true\n", 1)
    elif mutation == "exit_trap":
        mutated = original.replace(proof_run, "RUN trap 'exit 0' EXIT; " + proof_run[4:], 1)
    elif mutation == "proof_env":
        mutated = original.replace(proof_workdir, proof_workdir + "ENV PYTHONPATH=/fake\n", 1)
    elif mutation == "proof_arg":
        mutated = original.replace(proof_workdir, proof_workdir + "ARG VALIDATOR\n", 1)
    elif mutation == "shell_c":
        mutated = original.replace(
            proof_run,
            'RUN ["/bin/sh", "-c", "/usr/local/bin/python3 -I -S scripts/validate_public_pwa_proof_authority.py"]\n',
            1,
        )
    elif mutation == "command_substitution":
        mutated = original.replace(
            proof_run,
            "RUN $(printf /usr/local/bin/python3) -I -S scripts/validate_public_pwa_proof_authority.py\n",
            1,
        )
    elif mutation == "fake_interpreter":
        mutated = original.replace(
            'RUN ["/usr/local/bin/python3",',
            'RUN ["/proof/fake-python3",',
            1,
        )
    elif mutation == "onbuild":
        mutated = original.replace(proof_workdir, proof_workdir + "ONBUILD RUN true\n", 1)
    elif mutation == "derived_proof_stage":
        mutated = original.replace(
            build_from,
            "FROM public-pwa-proof AS inherited-proof\n" + build_from,
            1,
        )
    elif mutation == "json_indirection":
        mutated = original.replace(
            proof_run,
            'RUN ["/usr/local/bin/python3", "-I", "-S", "-c", "import runpy; runpy.run_path(\\\"scripts/validate_public_pwa_proof_authority.py\\\")"]\n',
            1,
        )
    elif mutation == "mid_file_escape":
        mutated = original.replace(proof_workdir, proof_workdir + "# escape=\\\n", 1)
    elif mutation == "extra_stage_instruction":
        mutated = original.replace(proof_workdir, proof_workdir + "RUN [\"/bin/true\"]\n", 1)
    elif mutation == "receipt_substitution":
        mutated = original.replace(
            receipt_copy,
            receipt_copy.replace(
                "/proof/public-pwa-proof-authority.receipt.json",
                "/proof/substitute.receipt.json",
            ),
            1,
        )
    elif mutation == "receipt_wrong_stage":
        mutated = original.replace(receipt_copy, "", 1)
        mutated = mutated.replace(
            module.PUBLIC_EDGE_DOCKER_FINAL_FROM + "\n",
            module.PUBLIC_EDGE_DOCKER_FINAL_FROM + "\n" + receipt_copy,
            1,
        )
    elif mutation == "global_arg":
        mutated = original.replace(proof_from, "ARG PYTHON_IMAGE\n" + proof_from, 1)
    elif mutation == "global_env":
        mutated = original.replace(proof_from, "ENV PYTHONPATH=/fake\n" + proof_from, 1)
    elif mutation == "global_shell":
        mutated = original.replace(
            proof_from,
            'SHELL ["/bin/sh", "-c"]\n' + proof_from,
            1,
        )
    elif mutation == "global_onbuild":
        mutated = original.replace(proof_from, "ONBUILD RUN true\n" + proof_from, 1)
    elif mutation == "heredoc":
        mutated = original.replace(proof_run, "RUN <<EOF\ntrue\nEOF\n", 1)
    elif mutation == "appended_default_bypass":
        mutated = original.rstrip() + "\n\nFROM scratch AS bypass\n"
    elif mutation == "extra_independent_stage":
        mutated = original.replace(final_from, "FROM scratch AS bypass\n" + final_from, 1)
    elif mutation == "detached_package_feed":
        mutated = original.replace(package_feed_receipt_copy, "", 1)
        mutated = mutated.replace(package_feed_python_copy, "", 1)
    elif mutation == "package_feed_python_copy_removed":
        mutated = original.replace(package_feed_python_copy, "", 1)
    elif mutation == "package_feed_build_copy_removed":
        mutated = original.replace(package_feed_build_copy, "", 1)
    elif mutation == "package_feed_mutable_sdk":
        mutated = original.replace(
            package_feed_from,
            "FROM mcr.microsoft.com/dotnet/sdk:10.0 AS hub-package-feed\n",
            1,
        )
    elif mutation in {"detached_final", "direct_final_from_base"}:
        mutated = original
        for build_copy in final_build_copies:
            mutated = mutated.replace(build_copy, "", 1)
    elif mutation == "removed_build_dependency":
        mutated = original.replace(receipt_copy, "", 1)
    elif mutation == "renamed_build_stage":
        mutated = original.replace(build_from, build_from.replace(" AS build", " AS compile"), 1)
        mutated = mutated.replace("--from=build", "--from=compile")
    elif mutation == "reordered_stages":
        build_start = original.index(build_from)
        final_start = original.index(final_from)
        mutated = (
            original[:build_start]
            + original[final_start:]
            + original[build_start:final_start]
        )
    elif mutation == "duplicate_final_stage":
        mutated = original.rstrip() + "\n\nFROM scratch AS final\n"
    elif mutation == "receipt_copy_decoy":
        mutated = original.replace(receipt_copy, "# " + receipt_copy, 1)
    elif mutation == "receipt_copy_as_run_continuation":
        mutated = original.replace(
            receipt_copy,
            "RUN printf proof-bypass \\\n" + receipt_copy,
            1,
        )
    elif mutation == "unknown_external_copy_source":
        mutated = original.replace(
            final_from,
            final_from + "COPY --from=docker.io/library/alpine:latest /bin/true /bin/true\n",
            1,
        )
    elif mutation == "numeric_copy_source":
        mutated = original.replace(
            final_from,
            final_from + "COPY --from=1 /app/publish /app\n",
            1,
        )
    elif mutation == "wrong_stage_named_context":
        mutated = original.replace(
            final_from,
            final_from
            + "COPY --from=run-services-source Chummer.Run.Api/Chummer.Run.Api.csproj /app/decoy.csproj\n",
            1,
        )
    elif mutation == "initializer_copy_moved_to_build":
        initializer_copy = (
            "COPY --from=run-services-source --chmod=0555 "
            "scripts/initialize-public-edge-volumes.sh "
            "/usr/local/libexec/chummer/initialize-public-edge-volumes.sh\n"
        )
        mutated = original.replace(initializer_copy, "", 1)
        mutated = mutated.replace(build_from, build_from + initializer_copy, 1)
    elif mutation == "receipt_moved_after_publish":
        mutated = original.replace(receipt_copy, "", 1)
        mutated = mutated.replace(final_from, receipt_copy + final_from, 1)
    elif mutation == "final_publish_edge_removed":
        mutated = original.replace(final_build_copies[0], "", 1)
    elif mutation == "loopback_probe_publish_edge_removed":
        mutated = original.replace(final_build_copies[1], "", 1)
    elif mutation == "operator_tool_copied_into_public_image":
        mutated = original.replace(
            final_from,
            final_from
            + "COPY --from=build /app/install-linking-postgres-tool "
            + "/app/operator-tool/\n",
            1,
        )
    elif mutation == "tool_publish_edge_removed":
        mutated = original.replace(tool_publish_copy, "", 1)
    elif mutation == "tool_payload_mode_removed":
        mutated = original.replace(tool_payload_mode, "", 1)
    elif mutation == "final_payload_mode_removed":
        mutated = original.replace(final_payload_mode, "", 1)
    elif mutation == "final_base_replaced":
        mutated = original.replace(final_from, "FROM scratch AS final\n", 1)
    elif mutation == "positional_fake_copy_from":
        mutated = original
        for build_copy in final_build_copies:
            mutated = mutated.replace(build_copy, "", 1)
        mutated = mutated.replace(
            final_from,
            final_from + "COPY local-file --from=build /tmp/decoy\n",
            1,
        )
    elif mutation == "split_from_keyword_default_bypass":
        mutated = original.rstrip() + "\n\nFR\\\nOM scratch AS bypass\n"
    elif mutation == "split_copy_from_option_external":
        mutated = original.replace(
            final_from,
            final_from
            + "COPY --fr\\\nom=docker.io/library/alpine:latest /bin/true /bin/true\n",
            1,
        )
    else:  # pragma: no cover - the parameter list is closed above.
        raise AssertionError(f"Unhandled Docker mutation: {mutation}")

    assert mutated != original
    dockerfile.write_text(mutated, encoding="utf-8")
    findings, checks = module.source_marker_findings(source_root)
    docker_check = next(
        check
        for check in checks
        if check["path"] == module.PUBLIC_EDGE_DOCKERFILE_RELATIVE_PATH
    )

    contract = docker_check["dockerBuildContract"]
    assert contract["status"] == "fail"
    assert any(expected_failure in failure for failure in contract["failures"])
    assert any(
        finding["id"] == "public_edge_source_docker_contract_invalid"
        for finding in findings
    )


@pytest.mark.parametrize(
    "reserved_name",
    (
        "public-pwa-proof",
        "build",
        "final",
        "python:3.12-slim",
        "python:3.12-slim@sha256:c3d81d25b3154142b0b42eb1e61300024426268edeb5b5a26dd7ddf64d9daf28",
        "mcr.microsoft.com/dotnet/sdk:10.0",
        "mcr.microsoft.com/dotnet/aspnet:10.0",
        "docker/dockerfile:1.4",
    ),
)
def test_public_pwa_compose_contract_rejects_reserved_named_context_overrides(
    tmp_path: Path,
    reserved_name: str,
) -> None:
    module = load_module()
    source_root = write_complete_marker_source_tree(module, tmp_path / "source")
    compose = source_root / module.PUBLIC_EDGE_COMPOSE_RELATIVE_PATH
    original = compose.read_text(encoding="utf-8")
    portal_start = original.index("  chummer-portal:\n")
    contexts_start = original.index("      additional_contexts:\n", portal_start)
    insertion = original.index("\n", contexts_start) + 1
    compose.write_text(
        original[:insertion]
        + f'        "{reserved_name}": docker-image://docker.io/library/alpine:latest\n'
        + original[insertion:],
        encoding="utf-8",
    )

    receipt = module.verify(
        [],
        allow_stale_foreign_build_locks=False,
        source_root=source_root,
    )

    contract = receipt["publicPwaComposeContextContract"]
    assert receipt["status"] == "fail"
    assert contract["status"] == "fail"
    assert contract["bindings"] == {
        **module.PUBLIC_EDGE_COMPOSE_NAMED_CONTEXTS,
        reserved_name: "docker-image://docker.io/library/alpine:latest",
    }
    assert contract["expectedBindings"] == module.PUBLIC_EDGE_COMPOSE_NAMED_CONTEXTS
    assert contract["checks"]["noReservedContextNames"] is False
    assert reserved_name in contract["reservedContextNames"]
    assert reserved_name in contract["unexpectedContextNames"]
    assert any(
        finding["id"] == "public_edge_source_compose_context_contract_invalid"
        for finding in receipt["findings"]
    )


@pytest.mark.parametrize("mutation", ("missing", "wrong_value", "unexpected"))
def test_public_pwa_compose_contract_requires_exact_named_context_bindings(
    tmp_path: Path,
    mutation: str,
) -> None:
    module = load_module()
    source_root = write_complete_marker_source_tree(module, tmp_path / "source")
    compose = source_root / module.PUBLIC_EDGE_COMPOSE_RELATIVE_PATH
    original = compose.read_text(encoding="utf-8")
    design_line = (
        "        design-product: "
        f"{module.PUBLIC_EDGE_COMPOSE_NAMED_CONTEXTS['design-product']}\n"
    )
    expected_actual_bindings = dict(module.PUBLIC_EDGE_COMPOSE_NAMED_CONTEXTS)
    run_services_value = module.PUBLIC_EDGE_COMPOSE_NAMED_CONTEXTS[
        "run-services-source"
    ]
    if mutation == "missing":
        mutated = original.replace(design_line, "", 1)
        expected_actual_bindings.pop("design-product")
    elif mutation == "wrong_value":
        portal_start = original.index("  chummer-portal:\n")
        value_start = original.index(run_services_value, portal_start)
        mutated = (
            original[:value_start]
            + "/tmp/unreviewed-run-services"
            + original[value_start + len(run_services_value):]
        )
        expected_actual_bindings["run-services-source"] = "/tmp/unreviewed-run-services"
    elif mutation == "unexpected":
        mutated = original.replace(
            design_line,
            design_line + "        unreviewed-context: /tmp/unreviewed\n",
            1,
        )
        expected_actual_bindings["unreviewed-context"] = "/tmp/unreviewed"
    else:  # pragma: no cover - the parameter list is closed above.
        raise AssertionError(f"Unhandled Compose mutation: {mutation}")
    assert mutated != original
    compose.write_text(mutated, encoding="utf-8")

    receipt = module.verify(
        [],
        allow_stale_foreign_build_locks=False,
        source_root=source_root,
    )

    contract = receipt["publicPwaComposeContextContract"]
    assert receipt["status"] == "fail"
    assert contract["status"] == "fail"
    assert contract["bindings"] == expected_actual_bindings
    assert contract["expectedBindings"] == module.PUBLIC_EDGE_COMPOSE_NAMED_CONTEXTS
    assert contract["checks"]["exactNamedContextBindings"] is False
    assert any(
        finding["id"] == "public_edge_source_compose_context_contract_invalid"
        for finding in receipt["findings"]
    )


@pytest.mark.parametrize(
    "service_name",
    (
        "chummer-install-linking-postgres-admin",
        "chummer-install-linking-postgres-runtime-proof",
        "chummer-install-linking-postgres-import-presence-proof",
        "chummer-install-linking-postgres-import",
    ),
)
@pytest.mark.parametrize("mutation", ("context", "dockerfile", "target", "source"))
def test_public_pwa_compose_contract_closes_operator_build_source_bindings(
    tmp_path: Path,
    service_name: str,
    mutation: str,
) -> None:
    module = load_module()
    source_root = write_complete_marker_source_tree(module, tmp_path / "source")
    compose = source_root / module.PUBLIC_EDGE_COMPOSE_RELATIVE_PATH
    original = compose.read_text(encoding="utf-8")
    service_start = original.index(f"  {service_name}:\n")
    next_service = re.search(r"(?m)^  [A-Za-z0-9_.-]+:\s*$", original[service_start + 3 :])
    service_end = (
        service_start + 3 + next_service.start()
        if next_service is not None
        else len(original)
    )
    block = original[service_start:service_end]
    replacements = {
        "context": (
            f"      context: {module.PUBLIC_EDGE_COMPOSE_BUILD_CONTEXT}",
            "      context: /tmp/unreviewed-build-context",
        ),
        "dockerfile": (
            f"      dockerfile: {module.PUBLIC_EDGE_COMPOSE_DOCKERFILE}",
            "      dockerfile: /tmp/unreviewed.Dockerfile",
        ),
        "target": (
            "      target: install-linking-postgres-tool-final",
            "      target: final",
        ),
        "source": (
            "        run-services-source: "
            + module.PUBLIC_EDGE_COMPOSE_NAMED_CONTEXTS["run-services-source"],
            "        run-services-source: /tmp/unreviewed-run-services",
        ),
    }
    expected, replacement = replacements[mutation]
    assert expected in block
    mutated_block = block.replace(expected, replacement, 1)
    compose.write_text(
        original[:service_start] + mutated_block + original[service_end:],
        encoding="utf-8",
    )

    receipt = module.verify(
        [],
        allow_stale_foreign_build_locks=False,
        source_root=source_root,
    )

    contract = receipt["publicPwaComposeContextContract"]
    assert receipt["status"] == "fail"
    assert contract["status"] == "fail"
    assert contract["serviceContracts"][service_name]["status"] == "fail"
    assert contract["serviceContracts"]["chummer-portal"]["status"] == "pass"


@pytest.mark.parametrize(
    "service_name",
    (
        "chummer-portal",
        "chummer-install-linking-postgres-admin",
        "chummer-install-linking-postgres-runtime-proof",
        "chummer-install-linking-postgres-import-presence-proof",
        "chummer-install-linking-postgres-import",
    ),
)
@pytest.mark.parametrize(
    ("mutation", "failed_check"),
    (
        ("dockerfile_inline", "exactBuildKeys"),
        ("alternate_dockerfile", "exactDockerfile"),
        ("context_selector_arg", "exactBuildArgs"),
    ),
)
def test_public_pwa_compose_contract_rejects_alternate_build_authority(
    tmp_path: Path,
    service_name: str,
    mutation: str,
    failed_check: str,
) -> None:
    module = load_module()
    compose = tmp_path / "docker-compose.public-edge.yml"
    original = (
        REPO_ROOT / module.PUBLIC_EDGE_COMPOSE_RELATIVE_PATH
    ).read_text(encoding="utf-8")
    service_start = original.index(f"  {service_name}:\n")
    next_service = re.search(
        r"(?m)^  [A-Za-z0-9_.-]+:\s*$",
        original[service_start + 3 :],
    )
    service_end = (
        service_start + 3 + next_service.start()
        if next_service is not None
        else len(original)
    )
    block = original[service_start:service_end]
    if mutation == "dockerfile_inline":
        mutated_block = block.replace(
            "    build:\n",
            "    build:\n"
            "      dockerfile_inline: |\n"
            "        FROM scratch\n",
            1,
        )
    elif mutation == "alternate_dockerfile":
        mutated_block = block.replace(
            f"      dockerfile: {module.PUBLIC_EDGE_COMPOSE_DOCKERFILE}\n",
            "      dockerfile: /tmp/unreviewed.Dockerfile\n",
            1,
        )
    elif mutation == "context_selector_arg":
        mutated_block = block.replace(
            "      args:\n",
            "      args:\n"
            "        SOURCE_CONTEXT: run-services-source\n",
            1,
        )
    else:  # pragma: no cover - the parameter list is closed above.
        raise AssertionError(f"Unhandled Compose mutation: {mutation}")
    assert mutated_block != block
    compose.write_text(
        original[:service_start] + mutated_block + original[service_end:],
        encoding="utf-8",
    )

    contract = module.validate_public_pwa_compose_context_contract(compose)
    service_contract = contract["serviceContracts"][service_name]

    assert contract["status"] == "fail"
    assert service_contract["status"] == "fail"
    assert service_contract["checks"][failed_check] is False


def mutate_portal_compose_build_syntax(
    module,
    original: str,
    mutation: str,
) -> str:
    if mutation == "top_level_include":
        return "include:\n  - ./included-build.yml\n\n" + original
    if mutation == "explicit_top_level_duplicate":
        return "? services\n: {}\n" + original
    if mutation == "quoted_top_level_duplicate":
        return '"services": {}\n' + original
    if mutation == "yaml_directive":
        return "%YAML 1.2\n---\n" + original
    if mutation == "yaml_tag_directive":
        return "%TAG !review! tag:example.invalid,2026:\n---\n" + original
    if mutation == "document_start":
        return "---\n" + original
    if mutation == "document_end":
        return "...\n" + original
    if mutation == "direct_sixth_build":
        return original.replace(
            "services:\n",
            "services:\n"
            "  direct-sixth-build:\n"
            "    image: unreviewed.invalid/direct:latest\n"
            "    build:\n"
            "      context: .\n",
            1,
        )
    if mutation == "tabbed_top_level_key":
        return original.replace("services:\n", "\tservices:\n", 1)
    if mutation == "spaced_top_level_key":
        return original.replace("services:\n", "services :\n", 1)
    service_name = "chummer-portal"
    service_start = original.index(f"  {service_name}:\n")
    next_service = re.search(
        r"(?m)^  [A-Za-z0-9_.-]+:\s*$",
        original[service_start + 3 :],
    )
    service_end = (
        service_start + 3 + next_service.start()
        if next_service is not None
        else len(original)
    )
    block = original[service_start:service_end]
    prefix = ""
    build_context_line = (
        f"      context: {module.PUBLIC_EDGE_COMPOSE_BUILD_CONTEXT}\n"
    )
    build_concurrency_line = (
        "        CHUMMER_BUILD_CONCURRENCY: "
        "${CHUMMER_BUILD_CONCURRENCY:-1}\n"
    )
    if mutation == "explicit_pull":
        mutated_block = block.replace(
            "    build:\n",
            "    build:\n      ? pull\n      : true\n",
            1,
        )
    elif mutation == "explicit_dockerfile_inline":
        mutated_block = block.replace(
            "    build:\n",
            "    build:\n"
            "      ? dockerfile_inline\n"
            "      : |\n"
            "          FROM scratch\n",
            1,
        )
    elif mutation == "pull":
        mutated_block = block.replace(
            "    build:\n",
            "    build:\n      pull: true\n",
            1,
        )
    elif mutation == "quoted_build_key":
        mutated_block = block.replace(
            "    build:\n",
            '    "build":\n',
            1,
        )
    elif mutation == "quoted_context_key":
        mutated_block = block.replace(
            build_context_line,
            build_context_line.replace("context:", '"context":', 1),
            1,
        )
    elif mutation == "quoted_nested_key":
        mutated_block = block.replace(
            build_concurrency_line,
            build_concurrency_line.replace(
                "CHUMMER_BUILD_CONCURRENCY:",
                '"CHUMMER_BUILD_CONCURRENCY":',
                1,
            ),
            1,
        )
    elif mutation == "merge":
        prefix = "x-review-build: &review-build\n  pull: true\n\n"
        mutated_block = block.replace(
            "    build:\n",
            "    build:\n      <<: *review-build\n",
            1,
        )
    elif mutation == "anchor":
        mutated_block = block.replace(
            build_context_line,
            build_context_line.replace(
                "context: ",
                "context: &review-context ",
                1,
            ),
            1,
        )
    elif mutation == "alias":
        prefix = (
            "x-review-context: &review-context "
            f"{module.PUBLIC_EDGE_COMPOSE_BUILD_CONTEXT}\n\n"
        )
        mutated_block = block.replace(
            build_context_line,
            "      context: *review-context\n",
            1,
        )
    elif mutation == "tag":
        mutated_block = block.replace(
            build_context_line,
            build_context_line.replace("context: ", "context: !!str ", 1),
            1,
        )
    elif mutation == "duplicate_build_key":
        mutated_block = block.replace(
            "    build:\n",
            '    "build": {}\n    build:\n',
            1,
        )
    elif mutation == "quoted_duplicate_service":
        return (
            original[:service_start]
            + '  "chummer-portal": {}\n'
            + original[service_start:]
        )
    elif mutation == "quoted_service_key":
        mutated_block = block.replace(
            "  chummer-portal:\n",
            '  "chummer-portal":\n',
            1,
        )
    elif mutation == "explicit_service_key":
        mutated_block = block.replace(
            "  chummer-portal:\n",
            "  ? chummer-portal\n  :\n",
            1,
        )
    elif mutation == "explicit_nested_arg":
        mutated_block = block.replace(
            "      args:\n",
            "      args:\n"
            "        ? SOURCE_CONTEXT\n"
            "        : run-services-source\n",
            1,
        )
    elif mutation in {
        "pull_policy",
        "platform",
        "profiles",
        "develop",
        "provider",
        "models",
    }:
        selector_lines = {
            "pull_policy": "    pull_policy: always\n",
            "platform": "    platform: linux/amd64\n",
            "profiles": '    profiles: ["unreviewed-build"]\n',
            "develop": "    develop: {}\n",
            "provider": "    provider: {type: unreviewed}\n",
            "models": "    models: {}\n",
        }
        mutated_block = block.replace(
            "    image: chummer-run-api:local\n",
            "    image: chummer-run-api:local\n"
            + selector_lines[mutation],
            1,
        )
    elif mutation == "image":
        mutated_block = block.replace(
            "    image: chummer-run-api:local\n",
            "    image: unreviewed.invalid/portal:latest\n",
            1,
        )
    elif mutation == "same_file_extends":
        mutated_block = block.replace(
            "    image: chummer-run-api:local\n",
            "    image: chummer-run-api:local\n"
            "    extends:\n"
            "      service: unreviewed-build-parent\n",
            1,
        )
        mutated = (
            original[:service_start]
            + mutated_block
            + original[service_end:]
        )
        return mutated.replace(
            "services:\n",
            "services:\n"
            "  unreviewed-build-parent:\n"
            "    image: unreviewed.invalid/base:latest\n"
            "    build:\n"
            "      context: .\n"
            "      pull: true\n",
            1,
        )
    elif mutation in {
        "external_extends_build_pull",
        "external_extends_pull_policy",
        "external_extends_platform",
    }:
        external_files = {
            "external_extends_build_pull": "external-build-pull.yml",
            "external_extends_pull_policy": "external-pull-policy.yml",
            "external_extends_platform": "external-platform.yml",
        }
        mutated_block = block.replace(
            "    image: chummer-run-api:local\n",
            "    image: chummer-run-api:local\n"
            "    extends:\n"
            f"      file: ./{external_files[mutation]}\n"
            "      service: unreviewed-build-parent\n",
            1,
        )
    else:  # pragma: no cover - the parameter list is closed by callers.
        raise AssertionError(f"Unhandled raw Compose mutation: {mutation}")
    assert mutated_block != block
    return (
        prefix
        + original[:service_start]
        + mutated_block
        + original[service_end:]
    )


@pytest.mark.parametrize(
    "hostile_instruction",
    (
        "RUN find /opt/chummer-core-runtime-feed -type f -delete",
        "RUN curl https://example.invalid/core.nupkg -o /opt/chummer-core-runtime-feed/hostile.nupkg",
        "RUN cp -a /tmp/hostile-feed/. /opt/chummer-core-runtime-feed/",
        "RUN rm -rf /opt/chummer-core-runtime-feed",
    ),
)
def test_exact_build_stage_rejects_post_materialization_feed_mutation(
    tmp_path: Path,
    hostile_instruction: str,
) -> None:
    module = load_module()
    cutover_module = load_cutover_module()
    canonical = (
        REPO_ROOT / "Chummer.Run.Api/Dockerfile"
    ).read_text(encoding="utf-8")
    boundary = (
        "\nFROM mcr.microsoft.com/dotnet/aspnet:10.0@sha256:"
        "1fa23fc4872d95fd71c2833ebe65d7e84a43b2d51a31d119516852f13d9505a7 "
        "AS install-linking-postgres-tool-final\n"
    )
    assert boundary in canonical
    hostile = canonical.replace(
        boundary,
        f"\n{hostile_instruction}{boundary}",
        1,
    )
    dockerfile = tmp_path / "Dockerfile"
    dockerfile.write_text(hostile, encoding="utf-8")

    contract = module.validate_public_pwa_docker_build_contract(dockerfile)

    assert contract["status"] == "fail"
    assert contract["checks"]["exactBuildStageInstructions"] is False
    assert any(
        "exact immutable instruction digest" in failure
        for failure in contract["failures"]
    )
    assert not cutover_module.docker_stage_instruction_contract_matches(
        hostile,
        stage="build",
        expected_count=(
            cutover_module.PUBLIC_EDGE_DOCKER_BUILD_STAGE_INSTRUCTION_COUNT
        ),
        expected_sha256=cutover_module.PUBLIC_EDGE_DOCKER_BUILD_STAGE_SHA256,
    )


def test_cutover_accepts_exact_current_v5_package_plane_and_rejects_open_core_schema() -> None:
    module = load_cutover_module()
    lock_path = REPO_ROOT / "eng/package-plane.lock.json"
    recipe_path = REPO_ROOT / "scripts/ai/bootstrap-hub-package-feed.py"
    authority_path = REPO_ROOT / "eng/core-main-runtime-artifact-authority.json"
    payload = json.loads(lock_path.read_text(encoding="utf-8"))

    assert module.GovernedCutoverRunner._validate_package_plane(
        payload,
        recipe_sha256=hashlib.sha256(recipe_path.read_bytes()).hexdigest(),
        core_authority_sha256=hashlib.sha256(
            authority_path.read_bytes()
        ).hexdigest(),
    ) == 12

    payload["core_runtime"]["unreviewed"] = True
    with pytest.raises(module.CutoverError, match="Core runtime package authority"):
        module.GovernedCutoverRunner._validate_package_plane(
            payload,
            recipe_sha256=hashlib.sha256(recipe_path.read_bytes()).hexdigest(),
            core_authority_sha256=hashlib.sha256(
                authority_path.read_bytes()
            ).hexdigest(),
        )


@pytest.mark.parametrize(
    "mutation",
    ("extra-entry", "mutable-directory", "mutable-file", "symlink"),
)
def test_external_core_bundle_input_is_exact_and_immutable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mutation: str,
) -> None:
    module = load_cutover_module()
    payload = b"reviewed external artifact"
    monkeypatch.setattr(module, "CORE_RUNTIME_BUNDLE_FILE_NAME", "bundle.zip")
    monkeypatch.setattr(module, "CORE_RUNTIME_BUNDLE_DIRECTORY_NAME", "core-input")
    monkeypatch.setattr(module, "CORE_RUNTIME_BUNDLE_SIZE_BYTES", len(payload))
    monkeypatch.setattr(
        module,
        "CORE_RUNTIME_BUNDLE_SHA256",
        hashlib.sha256(payload).hexdigest(),
    )
    source_root = tmp_path / "run-services"
    source_root.mkdir()
    bundle_root = tmp_path / "core-input"
    bundle_root.mkdir(mode=0o755)
    archive = bundle_root / "bundle.zip"
    archive.write_bytes(payload)
    archive.chmod(0o444)
    bundle_root.chmod(0o555)
    inputs = SimpleNamespace(source_root=source_root)

    assert module.validate_core_runtime_bundle_input(inputs) == bundle_root

    if mutation == "extra-entry":
        bundle_root.chmod(0o755)
        (bundle_root / "extra").write_text("hostile", encoding="utf-8")
        bundle_root.chmod(0o555)
    elif mutation == "mutable-directory":
        bundle_root.chmod(0o755)
    elif mutation == "mutable-file":
        archive.chmod(0o644)
    elif mutation == "symlink":
        bundle_root.chmod(0o755)
        archive.unlink()
        archive.symlink_to(tmp_path / "outside.zip")
        bundle_root.chmod(0o555)
    else:  # pragma: no cover - parametrization is closed.
        raise AssertionError(mutation)

    with pytest.raises(module.CutoverError, match="Core runtime bundle"):
        module.validate_core_runtime_bundle_input(inputs)


@pytest.mark.parametrize(
    "mutation",
    ("extra-entry", "mutable-directory", "mutable-file", "changed-bytes"),
)
def test_external_hub_feed_input_is_exact_and_immutable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mutation: str,
) -> None:
    module = load_cutover_module()
    payload = b"reviewed prebuilt Hub feed"
    monkeypatch.setattr(module, "HUB_PACKAGE_FEED_DIRECTORY_NAME", "hub-feed")
    monkeypatch.setattr(
        module,
        "HUB_PACKAGE_FEED_INPUTS",
        {"feed.nupkg": (hashlib.sha256(payload).hexdigest(), len(payload))},
    )
    source_root = tmp_path / "run-services"
    source_root.mkdir()
    feed_root = tmp_path / "hub-feed"
    feed_root.mkdir(mode=0o755)
    package = feed_root / "feed.nupkg"
    package.write_bytes(payload)
    package.chmod(0o444)
    feed_root.chmod(0o555)
    inputs = SimpleNamespace(source_root=source_root)

    assert module.validate_hub_package_feed_input(inputs) == feed_root

    if mutation == "extra-entry":
        feed_root.chmod(0o755)
        (feed_root / "extra").write_text("hostile", encoding="utf-8")
        feed_root.chmod(0o555)
    elif mutation == "mutable-directory":
        feed_root.chmod(0o755)
    elif mutation == "mutable-file":
        package.chmod(0o644)
    elif mutation == "changed-bytes":
        package.chmod(0o644)
        package.write_bytes(b"hostile prebuilt Hub feed")
        package.chmod(0o444)
    else:  # pragma: no cover - parametrization is closed.
        raise AssertionError(mutation)

    with pytest.raises(module.CutoverError, match="Hub package feed"):
        module.validate_hub_package_feed_input(inputs)


@pytest.mark.parametrize(
    "mutation",
    (
        "explicit_pull",
        "explicit_dockerfile_inline",
        "pull",
        "quoted_build_key",
        "quoted_context_key",
        "quoted_nested_key",
        "merge",
        "anchor",
        "alias",
        "tag",
        "duplicate_build_key",
        "quoted_duplicate_service",
        "quoted_service_key",
        "explicit_service_key",
        "explicit_nested_arg",
        "top_level_include",
        "explicit_top_level_duplicate",
        "quoted_top_level_duplicate",
        "yaml_directive",
        "yaml_tag_directive",
        "document_start",
        "document_end",
        "direct_sixth_build",
        "tabbed_top_level_key",
        "spaced_top_level_key",
        "pull_policy",
        "platform",
        "profiles",
        "develop",
        "provider",
        "models",
        "image",
        "same_file_extends",
        "external_extends_build_pull",
        "external_extends_pull_policy",
        "external_extends_platform",
    ),
)
def test_public_pwa_compose_raw_syntax_fails_closed_in_static_and_runtime_policy(
    tmp_path: Path,
    mutation: str,
) -> None:
    module = load_module()
    cutover_module = load_cutover_module()
    original = (
        REPO_ROOT / module.PUBLIC_EDGE_COMPOSE_RELATIVE_PATH
    ).read_text(encoding="utf-8")
    mutated = mutate_portal_compose_build_syntax(
        module,
        original,
        mutation,
    )
    compose = tmp_path / "docker-compose.public-edge.yml"
    compose.write_text(mutated, encoding="utf-8")

    contract = module.validate_public_pwa_compose_context_contract(compose)

    assert contract["status"] == "fail"
    assert contract["serviceContracts"]["chummer-portal"]["status"] == "fail"
    with pytest.raises(
        cutover_module.CutoverError,
        match="raw Compose build authority drifted",
    ):
        cutover_module.require_public_edge_compose_build_syntax(mutated)


@pytest.mark.parametrize(
    "service_name",
    (
        "chummer-portal",
        "chummer-install-linking-postgres-admin",
        "chummer-install-linking-postgres-runtime-proof",
        "chummer-install-linking-postgres-import-presence-proof",
        "chummer-install-linking-postgres-import",
    ),
)
@pytest.mark.parametrize(
    "mutation",
    (
        "extra_selector",
        "image",
        "profiles",
    ),
)
def test_every_governed_service_has_one_exact_raw_selection_contract(
    tmp_path: Path,
    service_name: str,
    mutation: str,
) -> None:
    module = load_module()
    cutover_module = load_cutover_module()
    original = (
        REPO_ROOT / module.PUBLIC_EDGE_COMPOSE_RELATIVE_PATH
    ).read_text(encoding="utf-8")
    image = module.PUBLIC_EDGE_RAW_SERVICE_IMAGES[service_name]
    service_prefix = f"  {service_name}:\n    image: {image}\n"
    assert service_prefix in original
    if mutation == "extra_selector":
        replacement = service_prefix + "    pull_policy: always\n"
    elif mutation == "image":
        replacement = service_prefix.replace(
            f"image: {image}",
            "image: unreviewed.invalid/service:latest",
            1,
        )
    elif mutation == "profiles":
        if service_name == "chummer-portal":
            replacement = (
                service_prefix + '    profiles: ["unreviewed-build"]\n'
            )
        else:
            profile_line = (
                '    profiles: ["install-linking-postgres-admin"]\n'
            )
            service_prefix += profile_line
            assert service_prefix in original
            replacement = service_prefix.replace(
                profile_line,
                '    profiles: ["unreviewed-build"]\n',
                1,
            )
    else:  # pragma: no cover - the parameter list is closed above.
        raise AssertionError(f"Unhandled service mutation: {mutation}")
    mutated = original.replace(service_prefix, replacement, 1)
    assert mutated != original
    compose = tmp_path / "docker-compose.public-edge.yml"
    compose.write_text(mutated, encoding="utf-8")

    contract = module.validate_public_pwa_compose_context_contract(compose)

    assert contract["status"] == "fail"
    assert contract["serviceContracts"][service_name]["status"] == "fail"
    with pytest.raises(
        cutover_module.CutoverError,
        match="raw Compose build authority drifted",
    ):
        cutover_module.require_public_edge_compose_build_syntax(mutated)


def test_static_and_runtime_build_policies_share_one_authority() -> None:
    module = load_module()
    cutover_module = load_cutover_module()

    shared_policy_names = (
        "PUBLIC_EDGE_BUILD_ARG_NAMES",
        "PUBLIC_EDGE_BUILD_KEYS_BY_SERVICE",
        "PUBLIC_EDGE_BUILD_SERVICE_TARGETS",
        "PUBLIC_EDGE_COMPOSE_TOP_LEVEL_KEYS",
        "PUBLIC_EDGE_DOCKER_BUILD_STAGE_INSTRUCTION_COUNT",
        "PUBLIC_EDGE_DOCKER_BUILD_STAGE_SHA256",
        "PUBLIC_EDGE_DOCKER_COPY_STAGE_REFERENCES_BY_STAGE",
        "PUBLIC_EDGE_DOCKER_EXACT_NAMED_CONTEXT_COPIES_BY_STAGE",
        "PUBLIC_EDGE_DOCKER_NAMED_CONTEXTS_BY_STAGE",
        "PUBLIC_EDGE_DOCKER_STAGE_ORDER",
        "PUBLIC_EDGE_NAMED_CONTEXT_NAMES",
        "PUBLIC_EDGE_RAW_SERVICE_IMAGES",
        "PUBLIC_EDGE_RAW_SERVICE_KEYS_BY_SERVICE",
        "PUBLIC_EDGE_RENDERED_BUILD_SERVICE_NAMES",
        "PUBLIC_EDGE_RENDERED_SERVICE_KEYS_BY_SERVICE",
        "PUBLIC_EDGE_SERVICE_PROFILES_BY_SERVICE",
        "docker_context_policy_findings",
        "docker_copy_from_reference",
        "docker_instruction_uses_mount",
        "docker_logical_instruction_records",
        "docker_logical_instructions",
        "dockerfile_parser_directive_findings",
        "docker_stage_instruction_contract_matches",
        "public_edge_compose_build_syntax_failures",
        "public_edge_rendered_compose_failures",
        "rendered_build_contract_matches",
    )
    for name in shared_policy_names:
        assert getattr(module, name) is getattr(cutover_module, name), name
    assert (
        module._docker_context_policy_findings
        is cutover_module.docker_context_policy_findings
    )
    assert (
        module._docker_copy_from_reference
        is cutover_module.docker_copy_from_reference
    )
    assert (
        module._docker_logical_instruction_records
        is cutover_module._docker_logical_instruction_records
    )
    assert (
        cutover_module.EXPECTED_NAMED_CONTEXT_COPY_INSTRUCTIONS_BY_STAGE
        is module.PUBLIC_EDGE_DOCKER_EXACT_NAMED_CONTEXT_COPIES_BY_STAGE
    )
    assert (
        set(module.PUBLIC_EDGE_COMPOSE_BUILD_SERVICE_CONTRACTS)
        == set(cutover_module.PUBLIC_EDGE_BUILD_SERVICE_TARGETS)
    )


def render_synthetic_compose_config(
    compose: Path,
    tmp_path: Path,
) -> subprocess.CompletedProcess[str]:
    synthetic_root = tmp_path / "render-synthetic"
    run_services = synthetic_root / "run-services"
    hub_registry = synthetic_root / "hub-registry"
    design_product = synthetic_root / "design-product"
    fleet_contracts = (
        synthetic_root
        / "fleet-media-factory"
        / "src"
        / "Chummer.Media.Contracts"
    )
    for path in (run_services, hub_registry, design_product, fleet_contracts):
        path.mkdir(parents=True, exist_ok=True)
    environment = {
        "PATH": "/usr/bin:/bin",
        "HOME": str(tmp_path),
        "LANG": "C",
        "LC_ALL": "C",
        "CHUMMER_ACCOUNT_ERASURE_RECEIPT_HMAC_KEY": "0" * 64,
        "CHUMMER_CORE_RUNTIME_BUNDLE_SOURCE": str(
            synthetic_root / "core-runtime-bundle"
        ),
        "CHUMMER_HUB_PACKAGE_FEED_SOURCE": str(
            synthetic_root / "hub-package-feed"
        ),
        "CHUMMER_DATA_PROTECTION_CERTIFICATE_FILE": str(tmp_path / "cert"),
        "CHUMMER_DATA_PROTECTION_CERTIFICATE_PASSWORD_FILE": str(
            tmp_path / "cert-password"
        ),
        "CHUMMER_INSTALL_LINKING_POSTGRES_DATABASE": "cutover",
        "CHUMMER_INSTALL_LINKING_POSTGRES_DNS_NAME": "db.example",
        "CHUMMER_INSTALL_LINKING_POSTGRES_IP": "127.0.0.1",
        "CHUMMER_INSTALL_LINKING_POSTGRES_MIGRATOR_CONNECTION_FILE": str(
            tmp_path / "migrator"
        ),
        "CHUMMER_INSTALL_LINKING_POSTGRES_PORT": "5432",
        "CHUMMER_INSTALL_LINKING_POSTGRES_RUNTIME_CONNECTION_FILE": str(
            tmp_path / "runtime"
        ),
        "CHUMMER_INSTALL_LINKING_POSTGRES_RUNTIME_ROLE": "runtime",
        "CHUMMER_INSTALL_LINKING_POSTGRES_SERVER_CA_FILE": str(tmp_path / "ca"),
        "CHUMMER_PUBLIC_EDGE_PROJECTION_SNAPSHOT_ROOT": str(
            tmp_path / "projection"
        ),
        "CHUMMER_PUBLIC_EDGE_RUNTIME_PROOF_BIND_SOURCE": str(tmp_path / "proof"),
        "CHUMMER_RELEASE_SHELF_INITIAL_MIGRATION_ALLOWED": "false",
        "CHUMMER_RELEASE_SHELF_LAYOUT_V1_REQUIRED": "true",
        "CHUMMER_RUN_CF_TUNNEL_TOKEN_FILE": str(tmp_path / "cloudflare-token"),
        "CHUMMER_PUBLIC_EDGE_BUILD_CONTEXT": str(synthetic_root),
        "CHUMMER_RUN_SERVICES_CONTEXT_DIR": str(run_services),
        "CHUMMER_RUN_SERVICES_SOURCE": str(run_services),
        "CHUMMER_HUB_REGISTRY_SOURCE": str(hub_registry),
        "CHUMMER_DESIGN_PRODUCT_SOURCE": str(design_product),
        "CHUMMER_FLEET_MEDIA_FACTORY_CONTRACTS_SOURCE": str(fleet_contracts),
    }
    return subprocess.run(
        [
            "/usr/bin/docker",
            "compose",
            "--env-file",
            "/dev/null",
            "--profile",
            "*",
            "-f",
            str(compose),
            "config",
            "--format",
            "json",
        ],
        cwd=REPO_ROOT,
        env=environment,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=30,
    )


@pytest.mark.parametrize(
    "mutation",
    (
        "explicit_pull",
        "pull",
        "quoted_build_key",
        "quoted_context_key",
        "quoted_nested_key",
        "merge",
        "anchor",
        "alias",
        "tag",
        "quoted_service_key",
        "explicit_service_key",
        "pull_policy",
        "platform",
        "profiles",
        "same_file_extends",
        "direct_sixth_build",
    ),
)
def test_renderable_compose_syntax_is_rejected_before_runtime_build(
    tmp_path: Path,
    mutation: str,
) -> None:
    module = load_module()
    cutover_module = load_cutover_module()
    original = (
        REPO_ROOT / module.PUBLIC_EDGE_COMPOSE_RELATIVE_PATH
    ).read_text(encoding="utf-8")
    mutated = mutate_portal_compose_build_syntax(
        module,
        original,
        mutation,
    )
    compose = tmp_path / "docker-compose.public-edge.yml"
    compose.write_text(mutated, encoding="utf-8")

    completed = render_synthetic_compose_config(compose, tmp_path)

    assert completed.returncode == 0, completed.stderr
    with pytest.raises(
        cutover_module.CutoverError,
        match="raw Compose build authority drifted",
    ):
        cutover_module.require_public_edge_compose_build_syntax(mutated)


@pytest.mark.parametrize(
    ("mutation", "external_payload", "rendered_path", "expected"),
    (
        (
            "external_extends_build_pull",
            "services:\n"
            "  unreviewed-build-parent:\n"
            "    image: chummer-run-api:local\n"
            "    build:\n"
            "      context: .\n"
            "      pull: true\n",
            ("build", "pull"),
            True,
        ),
        (
            "external_extends_pull_policy",
            "services:\n"
            "  unreviewed-build-parent:\n"
            "    image: chummer-run-api:local\n"
            "    pull_policy: always\n",
            ("pull_policy",),
            "always",
        ),
        (
            "external_extends_platform",
            "services:\n"
            "  unreviewed-build-parent:\n"
            "    image: chummer-run-api:local\n"
            "    platform: linux/amd64\n",
            ("platform",),
            "linux/amd64",
        ),
    ),
)
def test_external_extends_semantics_are_rejected_before_compose(
    tmp_path: Path,
    mutation: str,
    external_payload: str,
    rendered_path: tuple[str, ...],
    expected: object,
) -> None:
    module = load_module()
    cutover_module = load_cutover_module()
    original = (
        REPO_ROOT / module.PUBLIC_EDGE_COMPOSE_RELATIVE_PATH
    ).read_text(encoding="utf-8")
    mutated = mutate_portal_compose_build_syntax(
        module,
        original,
        mutation,
    )
    compose = tmp_path / "docker-compose.public-edge.yml"
    compose.write_text(mutated, encoding="utf-8")
    external_name = {
        "external_extends_build_pull": "external-build-pull.yml",
        "external_extends_pull_policy": "external-pull-policy.yml",
        "external_extends_platform": "external-platform.yml",
    }[mutation]
    (tmp_path / external_name).write_text(
        external_payload,
        encoding="utf-8",
    )

    completed = render_synthetic_compose_config(compose, tmp_path)

    assert completed.returncode == 0, completed.stderr
    selected: object = json.loads(completed.stdout)["services"][
        "chummer-portal"
    ]
    for key in rendered_path:
        assert isinstance(selected, dict)
        selected = selected[key]
    assert selected == expected
    with pytest.raises(
        cutover_module.CutoverError,
        match="raw Compose build authority drifted",
    ):
        cutover_module.require_public_edge_compose_build_syntax(mutated)


def test_top_level_include_cannot_add_a_sixth_governed_build_source(
    tmp_path: Path,
) -> None:
    module = load_module()
    cutover_module = load_cutover_module()
    original = (
        REPO_ROOT / module.PUBLIC_EDGE_COMPOSE_RELATIVE_PATH
    ).read_text(encoding="utf-8")
    mutated = mutate_portal_compose_build_syntax(
        module,
        original,
        "top_level_include",
    )
    compose = tmp_path / "docker-compose.public-edge.yml"
    compose.write_text(mutated, encoding="utf-8")
    (tmp_path / "included-build.yml").write_text(
        "services:\n"
        "  included-sixth-build:\n"
        "    image: unreviewed.invalid/included:latest\n"
        "    build:\n"
        "      context: .\n",
        encoding="utf-8",
    )

    completed = render_synthetic_compose_config(compose, tmp_path)

    assert completed.returncode == 0, completed.stderr
    assert "included-sixth-build" in json.loads(completed.stdout)["services"]
    with pytest.raises(
        cutover_module.CutoverError,
        match="raw Compose build authority drifted",
    ):
        cutover_module.require_public_edge_compose_build_syntax(mutated)


def test_real_compose_interpolation_routes_every_cutover_build_context(
    tmp_path: Path,
) -> None:
    module = load_module()
    synthetic_root = tmp_path / "synthetic"
    run_services = synthetic_root / "run-services"
    hub_registry = synthetic_root / "hub-registry"
    design_product = synthetic_root / "design-product"
    fleet_contracts = (
        synthetic_root
        / "fleet-media-factory"
        / "src"
        / "Chummer.Media.Contracts"
    )
    for path in (run_services, hub_registry, design_product, fleet_contracts):
        path.mkdir(parents=True, exist_ok=True)
    environment = {
        "PATH": "/usr/bin:/bin",
        "HOME": str(tmp_path),
        "LANG": "C",
        "LC_ALL": "C",
        "CHUMMER_ACCOUNT_ERASURE_RECEIPT_HMAC_KEY": "0" * 64,
        "CHUMMER_CORE_RUNTIME_BUNDLE_SOURCE": str(
            synthetic_root / "core-runtime-bundle"
        ),
        "CHUMMER_HUB_PACKAGE_FEED_SOURCE": str(
            synthetic_root / "hub-package-feed"
        ),
        "CHUMMER_DATA_PROTECTION_CERTIFICATE_FILE": str(tmp_path / "cert"),
        "CHUMMER_DATA_PROTECTION_CERTIFICATE_PASSWORD_FILE": str(
            tmp_path / "cert-password"
        ),
        "CHUMMER_INSTALL_LINKING_POSTGRES_DATABASE": "cutover",
        "CHUMMER_INSTALL_LINKING_POSTGRES_DNS_NAME": "db.example",
        "CHUMMER_INSTALL_LINKING_POSTGRES_IP": "127.0.0.1",
        "CHUMMER_INSTALL_LINKING_POSTGRES_MIGRATOR_CONNECTION_FILE": str(
            tmp_path / "migrator"
        ),
        "CHUMMER_INSTALL_LINKING_POSTGRES_PORT": "5432",
        "CHUMMER_INSTALL_LINKING_POSTGRES_RUNTIME_CONNECTION_FILE": str(
            tmp_path / "runtime"
        ),
        "CHUMMER_INSTALL_LINKING_POSTGRES_RUNTIME_ROLE": "runtime",
        "CHUMMER_INSTALL_LINKING_POSTGRES_SERVER_CA_FILE": str(tmp_path / "ca"),
        "CHUMMER_PUBLIC_EDGE_PROJECTION_SNAPSHOT_ROOT": str(
            tmp_path / "projection"
        ),
        "CHUMMER_PUBLIC_EDGE_RUNTIME_PROOF_BIND_SOURCE": str(tmp_path / "proof"),
        "CHUMMER_RELEASE_SHELF_INITIAL_MIGRATION_ALLOWED": "false",
        "CHUMMER_RELEASE_SHELF_LAYOUT_V1_REQUIRED": "true",
        "CHUMMER_RUN_CF_TUNNEL_TOKEN_FILE": str(tmp_path / "cloudflare-token"),
        "CHUMMER_PUBLIC_EDGE_BUILD_CONTEXT": str(synthetic_root),
        "CHUMMER_RUN_SERVICES_CONTEXT_DIR": str(run_services),
        "CHUMMER_RUN_SERVICES_SOURCE": str(run_services),
        "CHUMMER_HUB_REGISTRY_SOURCE": str(hub_registry),
        "CHUMMER_DESIGN_PRODUCT_SOURCE": str(design_product),
        "CHUMMER_FLEET_MEDIA_FACTORY_CONTRACTS_SOURCE": str(fleet_contracts),
    }
    completed = subprocess.run(
        [
            "/usr/bin/docker",
            "compose",
            "--env-file",
            "/dev/null",
            "--profile",
            "*",
            "-f",
            str(REPO_ROOT / "docker-compose.public-edge.yml"),
            "config",
            "--format",
            "json",
        ],
        cwd=REPO_ROOT,
        env=environment,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=30,
    )
    assert completed.returncode == 0, completed.stderr
    rendered = json.loads(completed.stdout)
    expected_contexts = {
        "core-runtime-bundle": str(synthetic_root / "core-runtime-bundle"),
        "hub-package-feed-input": str(
            synthetic_root / "hub-package-feed"
        ),
        "design-product": str(design_product),
        "fleet-media-factory-contracts": str(fleet_contracts),
        "hub-registry-source": str(hub_registry),
        "run-services-source": str(run_services),
    }
    services = (
        "chummer-portal",
        "chummer-install-linking-postgres-admin",
        "chummer-install-linking-postgres-runtime-proof",
        "chummer-install-linking-postgres-import-presence-proof",
        "chummer-install-linking-postgres-import",
    )
    for service_name in services:
        build = rendered["services"][service_name]["build"]
        expected_build_keys = {
            "additional_contexts",
            "args",
            "context",
            "dockerfile",
        }
        if service_name != "chummer-portal":
            expected_build_keys.add("target")
        assert set(build) == expected_build_keys
        assert build["args"] == {
            "CHUMMER_BUILD_CONCURRENCY": "1",
            "CHUMMER_RUNTIME_GID": "1654",
            "CHUMMER_RUNTIME_UID": "1654",
        }
        assert build["context"] == str(synthetic_root)
        assert build["dockerfile"] == str(
            run_services / "Chummer.Run.Api" / "Dockerfile"
        )
        assert build["additional_contexts"] == expected_contexts
        assert build.get("target") == (
            None
            if service_name == "chummer-portal"
            else "install-linking-postgres-tool-final"
        )
    assert module.public_edge_rendered_compose_failures(
        rendered,
        expected_images=module.PUBLIC_EDGE_RAW_SERVICE_IMAGES,
        build_context=str(synthetic_root),
        dockerfile=str(
            run_services / "Chummer.Run.Api" / "Dockerfile"
        ),
        additional_contexts=expected_contexts,
    ) == []


def test_public_pwa_reviewed_authority_rejects_duplicate_fields(tmp_path: Path) -> None:
    module = load_module()
    source_root = tmp_path / "workspace" / "chummer.run-services"
    source_root.mkdir(parents=True)
    configure_fake_public_pwa_identities(module, source_root)
    authority_path = (
        module.PUBLIC_PWA_PROOF_AUTHORITY_ROOT
        / module.PUBLIC_PWA_PROOF_AUTHORITY_RELATIVE_PATH
    )
    authority_text = authority_path.read_text(encoding="utf-8")
    authority_path.write_text(
        authority_text.replace(
            '  "policyId":',
            '  "contractName": "chummer.public-pwa-proof-authority.v1",\n  "policyId":',
            1,
        ),
        encoding="utf-8",
    )

    receipt = module.verify_public_pwa_proof_identities(source_root)

    assert receipt["status"] == "fail"
    assert receipt["authority"]["status"] == "fail"
    assert any("not valid JSON" in failure for failure in receipt["failures"])


def test_preflight_blocks_when_executable_public_pwa_proof_fails(tmp_path: Path) -> None:
    module = load_module()
    source_root = write_complete_marker_source_tree(module, tmp_path / "source")
    module.execute_public_pwa_static_proof = lambda root: {
        "contractName": "chummer.public_edge_pwa_static_preflight.v1",
        "status": "fail",
        "failures": ["bounded failure"],
        "failureCount": 1,
    }

    receipt = module.verify(
        [],
        allow_stale_foreign_build_locks=False,
        source_root=source_root,
    )

    assert receipt["status"] == "fail"
    assert receipt["publicPwaStaticProof"]["status"] == "fail"
    assert any(
        finding["id"] == "public_edge_pwa_static_proof_failed"
        for finding in receipt["findings"]
    )


def test_operational_mirror_check_fails_closed_for_missing_configured_roots(
    tmp_path: Path,
) -> None:
    module = load_module()
    source_root = write_complete_marker_source_tree(module, tmp_path / "source")
    module.PUBLIC_EDGE_OPERATIONAL_MIRROR_ROOTS = {
        "missing_public_edge": tmp_path / "missing-public-edge",
        "missing_participate": tmp_path / "missing-participate",
    }

    findings, checks = module.operational_mirror_findings(REPO_ROOT)

    assert len(checks) == 2
    assert {check["mirror"] for check in checks} == {
        "missing_public_edge",
        "missing_participate",
    }
    assert all(check["rootPresent"] is False for check in checks)
    assert [finding["id"] for finding in findings] == [
        "public_edge_operational_mirror_root_missing",
        "public_edge_operational_mirror_root_missing",
    ]

    receipt = module.verify(
        [],
        allow_stale_foreign_build_locks=False,
        source_root=source_root,
    )

    assert receipt["status"] == "fail"
    assert len(receipt["operationalMirrorChecks"]) == 2
    assert all(
        check["rootPresent"] is False
        for check in receipt["operationalMirrorChecks"]
    )
    assert sum(
        finding["id"] == "public_edge_operational_mirror_root_missing"
        for finding in receipt["findings"]
    ) == 2


def test_preflight_rejects_stale_overridden_operational_mirror_source(
    tmp_path: Path,
) -> None:
    module = load_module()
    canonical_root = write_complete_marker_source_tree(module, tmp_path / "canonical")
    stale_operational_root = write_complete_marker_source_tree(
        module,
        tmp_path / "public-edge-main",
    )
    canonical_home = canonical_root / module.PUBLIC_EDGE_HOME_VIEW_RELATIVE_PATH
    canonical_home.parent.mkdir(parents=True, exist_ok=True)
    canonical_home.write_text("canonical operational projection\n", encoding="utf-8")
    stale_home = stale_operational_root / module.PUBLIC_EDGE_HOME_VIEW_RELATIVE_PATH
    stale_home.parent.mkdir(parents=True, exist_ok=True)
    stale_home.write_text("canonical operational projection\n", encoding="utf-8")
    stale_home.write_text(
        stale_home.read_text(encoding="utf-8") + "stale operational projection\n",
        encoding="utf-8",
    )
    module.RUN_SERVICES_ROOT = canonical_root
    module.PUBLIC_EDGE_OPERATIONAL_MIRROR_ROOTS = {
        "public_edge_main": stale_operational_root,
    }

    receipt = module.verify(
        [],
        allow_stale_foreign_build_locks=False,
        source_root=stale_operational_root,
    )

    assert receipt["sourceRoot"] == str(stale_operational_root.resolve())
    assert receipt["status"] == "fail"
    assert receipt["operationalMirrorChecks"][0]["rootPresent"] is True
    assert receipt["operationalMirrorChecks"][0]["homeViewMatchesCanonical"] is False
    assert any(
        finding["id"] == "public_edge_operational_mirror_home_view_drift"
        for finding in receipt["findings"]
    )


def test_preflight_advertises_fail_closed_operational_mirror_sync_lane(tmp_path: Path) -> None:
    module = load_module()
    source_root = write_complete_marker_source_tree(module, tmp_path / "source")
    module.PUBLIC_EDGE_OPERATIONAL_MIRROR_ROOTS = {}

    receipt = module.verify(
        [],
        allow_stale_foreign_build_locks=False,
        source_root=source_root,
    )

    assert receipt["operationalMirrorSync"] == {
        "checkCommand": "python3 scripts/sync_public_edge_operational_mirrors.py",
        "applyCommand": "python3 scripts/sync_public_edge_operational_mirrors.py --apply",
        "applyRequiresCleanContractedTargets": True,
        "directOverlayCopyAllowed": False,
    }


def test_operational_mirror_check_fails_when_status_contract_is_stale(tmp_path: Path) -> None:
    module = load_module()
    source_root = tmp_path / "source"
    canonical_status = source_root / module.PUBLIC_EDGE_STATUS_VIEW_RELATIVE_PATH
    canonical_status.parent.mkdir(parents=True, exist_ok=True)
    canonical_status.write_text("@model StatusPageViewModel\n<h1>Preview downloads</h1>\n", encoding="utf-8")
    canonical_controller = source_root / module.PUBLIC_EDGE_STATUS_CONTROLLER_RELATIVE_PATH
    canonical_controller.parent.mkdir(parents=True, exist_ok=True)
    canonical_controller.write_text(module.PUBLIC_EDGE_STATUS_CONTROLLER_NEEDLE + "\n", encoding="utf-8")

    mirror_root = tmp_path / "public-edge-main"
    mirror_status = mirror_root / module.PUBLIC_EDGE_STATUS_VIEW_RELATIVE_PATH
    mirror_status.parent.mkdir(parents=True, exist_ok=True)
    mirror_status.write_text("@model StatusPageViewModel\n<h1>Updated</h1>\n", encoding="utf-8")
    mirror_controller = mirror_root / module.PUBLIC_EDGE_STATUS_CONTROLLER_RELATIVE_PATH
    mirror_controller.parent.mkdir(parents=True, exist_ok=True)
    mirror_controller.write_text(module.PUBLIC_EDGE_STALE_STATUS_CONTROLLER_NEEDLE + "\n", encoding="utf-8")
    module.PUBLIC_EDGE_OPERATIONAL_MIRROR_ROOTS = {"public_edge_main": mirror_root}

    findings, checks = module.operational_mirror_findings(source_root)

    assert len(checks) == 1
    assert checks[0]["mirror"] == "public_edge_main"
    assert checks[0]["statusViewMatchesCanonical"] is False
    assert checks[0]["staleStatusHeadingPresent"] is True
    assert checks[0]["statusControllerTitleMatchesCanonical"] is False
    assert checks[0]["staleStatusControllerTitlePresent"] is True
    finding_ids = {finding["id"] for finding in findings}
    assert "public_edge_operational_mirror_status_view_drift" in finding_ids
    assert "public_edge_operational_mirror_stale_status_heading" in finding_ids
    assert "public_edge_operational_mirror_status_controller_drift" in finding_ids
    assert "public_edge_operational_mirror_stale_status_controller_title" in finding_ids


def test_operational_mirror_check_fails_when_critical_public_surfaces_drift(tmp_path: Path) -> None:
    module = load_module()
    source_root = tmp_path / "source"
    canonical_files = {
        module.PUBLIC_EDGE_DOWNLOADS_VIEW_RELATIVE_PATH: "@model DownloadsPageViewModel\nVersion current\n",
        module.PUBLIC_EDGE_LANDING_VIEW_RELATIVE_PATH: "@model LandingPageViewModel\nBuild\nPlay\n",
        module.PUBLIC_EDGE_HOME_VIEW_RELATIVE_PATH: "@model HomePageViewModel\nCurrent\n",
        module.PUBLIC_EDGE_HORIZONS_VIEW_RELATIVE_PATH: "@model HorizonsPageViewModel\nHorizons\n",
        module.PUBLIC_EDGE_STATUS_CONTROLLER_RELATIVE_PATH: module.PUBLIC_EDGE_STATUS_CONTROLLER_NEEDLE + "\ncanonical-controller\n",
        module.PUBLIC_EDGE_SERVICE_WORKER_RELATIVE_PATH: 'const CACHE_VERSION = "v19";\n',
    }
    for relative_path, content in canonical_files.items():
        path = source_root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    mirror_root = tmp_path / "public-edge-main"
    mirror_files = {
        module.PUBLIC_EDGE_DOWNLOADS_VIEW_RELATIVE_PATH: "@model DownloadsPageViewModel\nVersion preview\n",
        module.PUBLIC_EDGE_LANDING_VIEW_RELATIVE_PATH: "@model LandingPageViewModel\nBuild only\n",
        module.PUBLIC_EDGE_HOME_VIEW_RELATIVE_PATH: "@model HomePageViewModel\nStatus\n",
        module.PUBLIC_EDGE_HORIZONS_VIEW_RELATIVE_PATH: "@model HorizonsPageViewModel\nMaintenance\n",
        module.PUBLIC_EDGE_STATUS_CONTROLLER_RELATIVE_PATH: module.PUBLIC_EDGE_STATUS_CONTROLLER_NEEDLE + "\nstale-controller\n",
        module.PUBLIC_EDGE_SERVICE_WORKER_RELATIVE_PATH: 'const CACHE_NAME = "chummer-public-v4";\n',
    }
    for relative_path, content in mirror_files.items():
        path = mirror_root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    module.PUBLIC_EDGE_OPERATIONAL_MIRROR_ROOTS = {"public_edge_main": mirror_root}

    findings, checks = module.operational_mirror_findings(source_root)

    assert len(checks) == 1
    check = checks[0]
    assert check["mirror"] == "public_edge_main"
    assert check["downloadsViewMatchesCanonical"] is False
    assert check["landingViewMatchesCanonical"] is False
    assert check["homeViewMatchesCanonical"] is False
    assert check["horizonsViewMatchesCanonical"] is False
    assert check["publicLandingControllerMatchesCanonical"] is False
    assert check["statusControllerTitleMatchesCanonical"] is True
    assert check["serviceWorkerMatchesCanonical"] is False
    finding_ids = {finding["id"] for finding in findings}
    assert "public_edge_operational_mirror_downloads_view_drift" in finding_ids
    assert "public_edge_operational_mirror_landing_view_drift" in finding_ids
    assert "public_edge_operational_mirror_home_view_drift" in finding_ids
    assert "public_edge_operational_mirror_horizons_view_drift" in finding_ids
    assert "public_edge_operational_mirror_status_controller_drift" in finding_ids
    assert "public_edge_operational_mirror_service_worker_drift" in finding_ids
    assert "public_edge_operational_mirror_stale_status_controller_title" not in finding_ids


def test_source_marker_check_requires_frontdoor_build_play_gate(tmp_path: Path) -> None:
    module = load_module()
    source_root = write_complete_marker_source_tree(module, tmp_path / "source")
    landing = source_root / "Chummer.Run.Api" / "Views" / "PublicLanding" / "Landing.cshtml"
    landing.write_text("Sign in first\nhref=\"/mobile/player\"\n", encoding="utf-8")

    receipt = module.verify(
        [],
        allow_stale_foreign_build_locks=False,
        source_root=source_root,
    )

    assert receipt["status"] == "fail"
    landing_check = next(check for check in receipt["sourceMarkerChecks"] if check["path"] == "Chummer.Run.Api/Views/PublicLanding/Landing.cshtml")
    assert 'data-mobile-app-handoff="build-mobile-app-handoff"' in landing_check["missingMarkers"]
    assert 'data-mobile-app-handoff="mobile-app-handoff"' in landing_check["missingMarkers"]
    assert "Target: MobileAppHandoffTarget.Build" in landing_check["missingMarkers"]
    assert "Target: MobileAppHandoffTarget.Play" in landing_check["missingMarkers"]
    assert 'data-analytics-event="@playAnalyticsEvent"' in landing_check["missingMarkers"]
    assert "#turn-runsite-card" in landing_check["missingMarkers"]
    assert 'const normalizedHash = window.location.hash.split("?")[0];' in landing_check["missingMarkers"]
    assert 'window.location.replace(`/mobile/player${normalizedHash}`);' in landing_check["missingMarkers"]


def test_source_marker_check_requires_default_off_profile_gated_local_play_contract(tmp_path: Path) -> None:
    module = load_module()
    source_root = write_complete_marker_source_tree(module, tmp_path / "source")
    compose = source_root / "docker-compose.public-edge.yml"
    compose.write_text(
        'CHUMMER_PUBLIC_PLAY_PROXY_ENABLED: "${CHUMMER_PUBLIC_PLAY_PROXY_ENABLED:-false}"\n'
        'CHUMMER_PUBLIC_PLAY_LIVE_SESSION_PROXY_ENABLED: "${CHUMMER_PUBLIC_PLAY_LIVE_SESSION_PROXY_ENABLED:-false}"\n',
        encoding="utf-8",
    )

    receipt = module.verify(
        [],
        allow_stale_foreign_build_locks=False,
        source_root=source_root,
    )

    assert receipt["status"] == "fail"
    compose_check = next(check for check in receipt["sourceMarkerChecks"] if check["path"] == "docker-compose.public-edge.yml")
    assert 'profiles: ["play-private"]' in compose_check["missingMarkers"]
    assert 'CHUMMER_PUBLIC_PLAY_PROXY_ENABLED: "false"' in compose_check["missingMarkers"]
    assert 'CHUMMER_PUBLIC_PLAY_LIVE_SESSION_PROXY_ENABLED: "false"' in compose_check["missingMarkers"]
    assert "${CHUMMER_PUBLIC_PLAY_PROXY_ENABLED" in compose_check["presentForbiddenMarkers"]
    assert "${CHUMMER_PUBLIC_PLAY_LIVE_SESSION_PROXY_ENABLED" in compose_check["presentForbiddenMarkers"]
    assert "${CHUMMER_PUBLIC_PORTAL_APP_OVERLAY_DIR:-/docker/chummercomplete/chummer.run-services/.state/public-edge-portal-overlay/app}:/app:ro" in compose_check["missingMarkers"]


def test_source_marker_check_requires_role_specific_mobile_handoff_routes(tmp_path: Path) -> None:
    module = load_module()
    source_root = write_complete_marker_source_tree(module, tmp_path / "source")
    ready_for_tonight = source_root / "Chummer.Run.Api" / "Services" / "ReadyForTonightService.cs"
    ready_for_tonight.write_text(
        "\n".join(
            [
                "playtime_tools",
                "inventory",
                "health",
                "ammo",
                "modifiers",
                "quick_rolls",
                "living_world",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    receipt = module.verify(
        [],
        allow_stale_foreign_build_locks=False,
        source_root=source_root,
    )

    assert receipt["status"] == "fail"
    ready_mobile_check = next(
        check for check in receipt["sourceMarkerChecks"] if check["path"] == "Chummer.Run.Api/Services/ReadyForTonightService.cs"
    )
    assert 'frontdoor_launch_route = "/mobile/player"' in ready_mobile_check["missingMarkers"]
    assert "role_routes = new[]" in ready_mobile_check["missingMarkers"]
    assert 'route = "/mobile/player"' in ready_mobile_check["missingMarkers"]
    assert 'route = "/mobile/gm"' in ready_mobile_check["missingMarkers"]
    assert 'manifest_path = "/manifest.player.webmanifest"' in ready_mobile_check["missingMarkers"]
    assert 'manifest_path = "/manifest.gm.webmanifest"' in ready_mobile_check["missingMarkers"]
    assert 'manifest_start_url = "/mobile/player"' in ready_mobile_check["missingMarkers"]
    assert 'manifest_start_url = "/mobile/gm"' in ready_mobile_check["missingMarkers"]


def test_source_marker_check_requires_role_alias_canonicalization(tmp_path: Path) -> None:
    module = load_module()
    source_root = write_complete_marker_source_tree(module, tmp_path / "source")
    program = source_root / "Chummer.Run.Api" / "Program.cs"
    program.write_text(
        "IPublicPlayPrivateRouteDelegator\n"
        "var combinedReport = new\n"
        "playProjection = projection\n",
        encoding="utf-8",
    )

    receipt = module.verify(
        [],
        allow_stale_foreign_build_locks=False,
        source_root=source_root,
    )

    assert receipt["status"] == "fail"
    program_check = next(check for check in receipt["sourceMarkerChecks"] if check["path"] == "Chummer.Run.Api/Program.cs")
    assert "TryResolveRoleAliasRedirectPath" in program_check["missingMarkers"]
    assert 'path.Equals("/jammer", StringComparison.OrdinalIgnoreCase)' in program_check["missingMarkers"]
    assert 'redirectPath = "/mobile/player";' in program_check["missingMarkers"]
    assert 'redirectPath = "/mobile/gm";' in program_check["missingMarkers"]
    assert 'redirectPath = "/mobile/observer";' in program_check["missingMarkers"]
    assert 'context.Response.Headers["Referrer-Policy"] = "no-referrer";' in program_check["missingMarkers"]
    assert 'context.Response.Headers.CacheControl = "private, no-store, no-cache, max-age=0";' in program_check["missingMarkers"]
    assert 'context.Response.Redirect($"{redirectPath}#", permanent: false);' in program_check["missingMarkers"]


def test_source_marker_check_rejects_query_preserving_role_alias_redirects(tmp_path: Path) -> None:
    module = load_module()
    source_root = write_complete_marker_source_tree(module, tmp_path / "source")
    program = source_root / "Chummer.Run.Api" / "Program.cs"
    program.write_text(
        program.read_text(encoding="utf-8")
        + "\nstring destination = context.Request.QueryString.HasValue\n",
        encoding="utf-8",
    )

    receipt = module.verify(
        [],
        allow_stale_foreign_build_locks=False,
        source_root=source_root,
    )

    assert receipt["status"] == "fail"
    program_check = next(check for check in receipt["sourceMarkerChecks"] if check["path"] == "Chummer.Run.Api/Program.cs")
    assert "string destination = context.Request.QueryString.HasValue" in program_check["presentForbiddenMarkers"]


def test_source_marker_check_requires_canonical_role_bodies_and_worker_generator(tmp_path: Path) -> None:
    module = load_module()
    source_root = write_complete_marker_source_tree(module, tmp_path / "source")
    (source_root / "Chummer.Run.Api/Controllers/PublicLandingController.cs").write_text(
        "public IActionResult PlayProjectionPage()\n",
        encoding="utf-8",
    )
    (source_root / "Chummer.Run.Api/Views/PublicLanding/MobileProjection.cshtml").write_text(
        'data-install-role="@roleProfile.RoleKey"\n',
        encoding="utf-8",
    )
    (source_root / "scripts/generate_public_play_worker_projection.py").write_text(
        'GENERATOR_CONTRACT = "play-root-worker-projection-generator-v1"\n',
        encoding="utf-8",
    )

    receipt = module.verify(
        [],
        allow_stale_foreign_build_locks=False,
        source_root=source_root,
    )

    assert receipt["status"] == "fail"
    checks = {check["path"]: check for check in receipt["sourceMarkerChecks"]}
    assert "ResolveCanonicalPlayRoleFromQuery(Request.Query)" in checks[
        "Chummer.Run.Api/Controllers/PublicLandingController.cs"
    ]["missingMarkers"]
    assert "data-mobile-app-inline-qr" in checks[
        "Chummer.Run.Api/Views/PublicLanding/MobileProjection.cshtml"
    ]["missingMarkers"]
    assert "projected worker differs from deterministic output" in checks[
        "scripts/generate_public_play_worker_projection.py"
    ]["missingMarkers"]


def test_stale_source_marker_check_fails_closed(tmp_path: Path) -> None:
    module = load_module()
    stale_root = tmp_path / "stale"
    stale_root.mkdir()
    for relative_path in module.PUBLIC_EDGE_REQUIRED_SOURCE_MARKERS:
        path = stale_root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("stale source without launch markers\n", encoding="utf-8")

    receipt = module.verify(
        [],
        allow_stale_foreign_build_locks=False,
        source_root=stale_root,
    )

    assert receipt["status"] == "fail"
    assert receipt["activeLockCount"] == 0
    assert any(finding["id"] == "public_edge_source_marker_missing" for finding in receipt["findings"])
    missing = {
        check["path"]: check["missingMarkers"]
        for check in receipt["sourceMarkerChecks"]
        if check["missingMarkers"]
    }
    assert "Chummer.Run.Api/Views/PublicLanding/Downloads.cshtml" in missing
    assert 'data-downloads-release-version="@ManifestVersionText(Model.Manifest)"' in missing["Chummer.Run.Api/Views/PublicLanding/Downloads.cshtml"]
    assert 'data-downloads-release-generation="@ManifestGenerationId(Model.Manifest)"' in missing["Chummer.Run.Api/Views/PublicLanding/Downloads.cshtml"]
    assert 'data-downloads-public-count="@Model.Manifest.Downloads.Count"' in missing["Chummer.Run.Api/Views/PublicLanding/Downloads.cshtml"]
    assert "Public downloads @Model.Manifest.Downloads.Count</span>" in missing["Chummer.Run.Api/Views/PublicLanding/Downloads.cshtml"]
    assert "No public installer listed" in missing["Chummer.Run.Api/Views/PublicLanding/Downloads.cshtml"]
    assert "No public build is available right now" in missing["Chummer.Run.Api/Views/PublicLanding/Downloads.cshtml"]


def test_source_marker_check_requires_public_signal_and_doc_mirror_bundle(tmp_path: Path) -> None:
    module = load_module()
    source_root = write_complete_marker_source_tree(module, tmp_path / "source")
    for relative_path in (
        ".codex-design/product/PUBLIC_FEEDBACK_TAXONOMY.yaml",
        ".codex-design/product/PUBLIC_FEEDBACK_AND_CONTENT_REGISTRY.yaml",
        ".codex-design/product/PUBLIC_SIGNAL_FEEDBACK_ROADMAP_BRIDGE.md",
        ".codex-design/product/PUBLIC_SIGNAL_TO_CANON_PIPELINE.md",
        ".codex-design/product/ORIGIN_BOOK_STUDIO.md",
        ".codex-design/product/public-guides/chummer6-quickstart.md",
    ):
        (source_root / relative_path).unlink()

    receipt = module.verify(
        [],
        allow_stale_foreign_build_locks=False,
        source_root=source_root,
    )

    assert receipt["status"] == "fail"
    checks = {check["path"]: check for check in receipt["sourceMarkerChecks"]}
    assert "key: mobile_companion" in checks[".codex-design/product/PUBLIC_FEEDBACK_TAXONOMY.yaml"]["missingMarkers"]
    assert "key: productlift_public_feedback" in checks[".codex-design/product/PUBLIC_FEEDBACK_AND_CONTENT_REGISTRY.yaml"]["missingMarkers"]
    assert "# Public signal feedback, roadmap, and changelog bridge" in checks[".codex-design/product/PUBLIC_SIGNAL_FEEDBACK_ROADMAP_BRIDGE.md"]["missingMarkers"]
    assert "# Public signal to canon pipeline" in checks[".codex-design/product/PUBLIC_SIGNAL_TO_CANON_PIPELINE.md"]["missingMarkers"]
    assert "# ORIGIN BOOK STUDIO" in checks[".codex-design/product/ORIGIN_BOOK_STUDIO.md"]["missingMarkers"]
    assert "# Chummer6 Quickstart Guide" in checks[".codex-design/product/public-guides/chummer6-quickstart.md"]["missingMarkers"]


def test_overlay_marker_check_requires_public_signal_and_doc_mirror_bundle(tmp_path: Path) -> None:
    module = load_module()
    source_root = write_complete_marker_source_tree(module, tmp_path / "source")
    overlay_root = write_complete_marker_overlay_tree(module, tmp_path / "overlay", source_root)
    for relative_path in (
        ".codex-design/product/PUBLIC_FEEDBACK_TAXONOMY.yaml",
        ".codex-design/product/PUBLIC_FEEDBACK_AND_CONTENT_REGISTRY.yaml",
        ".codex-design/product/PUBLIC_SIGNAL_FEEDBACK_ROADMAP_BRIDGE.md",
        ".codex-design/product/PUBLIC_SIGNAL_TO_CANON_PIPELINE.md",
        ".codex-design/product/ORIGIN_BOOK_STUDIO.md",
        ".codex-design/product/public-guides/chummer6-quickstart.md",
    ):
        (overlay_root / relative_path).unlink()

    receipt = module.verify(
        [],
        allow_stale_foreign_build_locks=False,
        source_root=source_root,
        overlay_root=overlay_root,
        check_overlay_markers=True,
    )

    assert receipt["status"] == "fail"
    assert receipt["overlayRoot"] == str(overlay_root.resolve())
    checks = {check["path"]: check for check in receipt["overlayMarkerChecks"]}
    assert "key: mobile_companion" in checks[".codex-design/product/PUBLIC_FEEDBACK_TAXONOMY.yaml"]["missingMarkers"]
    assert "key: productlift_public_feedback" in checks[".codex-design/product/PUBLIC_FEEDBACK_AND_CONTENT_REGISTRY.yaml"]["missingMarkers"]
    assert "# Public signal feedback, roadmap, and changelog bridge" in checks[".codex-design/product/PUBLIC_SIGNAL_FEEDBACK_ROADMAP_BRIDGE.md"]["missingMarkers"]
    assert "# Public signal to canon pipeline" in checks[".codex-design/product/PUBLIC_SIGNAL_TO_CANON_PIPELINE.md"]["missingMarkers"]
    assert "# ORIGIN BOOK STUDIO" in checks[".codex-design/product/ORIGIN_BOOK_STUDIO.md"]["missingMarkers"]
    assert "# Chummer6 Quickstart Guide" in checks[".codex-design/product/public-guides/chummer6-quickstart.md"]["missingMarkers"]
    assert any(finding["id"] == "public_edge_overlay_marker_missing" for finding in receipt["findings"])


def test_overlay_marker_check_requires_overlay_build_info_receipt(tmp_path: Path) -> None:
    module = load_module()
    source_root = write_complete_marker_source_tree(module, tmp_path / "source")
    overlay_root = write_complete_marker_overlay_tree(module, tmp_path / "overlay", source_root)
    (overlay_root / ".codex-studio/runtime/PUBLIC_EDGE_PORTAL_OVERLAY_BUILD_INFO.generated.json").unlink()

    receipt = module.verify(
        [],
        allow_stale_foreign_build_locks=False,
        source_root=source_root,
        overlay_root=overlay_root,
        check_overlay_markers=True,
    )

    assert receipt["status"] == "fail"
    checks = {check["path"]: check for check in receipt["overlayMarkerChecks"]}
    missing = checks[".codex-studio/runtime/PUBLIC_EDGE_PORTAL_OVERLAY_BUILD_INFO.generated.json"]["missingMarkers"]
    assert '"contractName": "chummer.public_edge_portal_overlay_publish.v1"' in missing
    assert '"landingMarkerStatus": "pass"' in missing
    assert '"landingHasTurnAnchorRedirect": true' in missing
    assert '"landingBrowserRedirectStatus": "pass"' in missing
    assert '"landingBrowserRedirectPathMatches": true' in missing
    assert '"landingBrowserRedirectHashMatches": true' in missing
    assert any(finding["id"] == "public_edge_overlay_marker_missing" for finding in receipt["findings"])


def test_source_marker_check_rejects_stale_portal_worker_docker_guard(tmp_path: Path) -> None:
    module = load_module()
    source_root = write_complete_marker_source_tree(module, tmp_path / "source")
    dockerfile = source_root / "Chummer.Run.Api" / "Dockerfile"
    dockerfile.write_text(
        dockerfile.read_text(encoding="utf-8")
        + "\n"
        + "RUN test -f /app/publish/wwwroot/service-worker.js \\\n"
        + " && grep -q 'const CACHE_NAME = \"chummer-public-v4\";' /app/publish/wwwroot/service-worker.js \\\n"
        + " && ! grep -q 'play-shell-v' /app/publish/wwwroot/service-worker.js\n",
        encoding="utf-8",
    )

    receipt = module.verify(
        [],
        allow_stale_foreign_build_locks=False,
        source_root=source_root,
    )

    assert receipt["status"] == "fail"
    dockerfile_check = next(check for check in receipt["sourceMarkerChecks"] if check["path"] == "Chummer.Run.Api/Dockerfile")
    assert 'grep -q \'const CACHE_NAME = "chummer-public-v4";\'' in dockerfile_check["presentForbiddenMarkers"]
    assert "! grep -q 'play-shell-v'" in dockerfile_check["presentForbiddenMarkers"]
    assert any(finding["id"] == "public_edge_source_marker_forbidden" for finding in receipt["findings"])


def test_source_marker_check_requires_clean_chummer_run_api_publish_guard(tmp_path: Path) -> None:
    module = load_module()
    source_root = write_complete_marker_source_tree(module, tmp_path / "source")
    dockerfile = source_root / "Chummer.Run.Api" / "Dockerfile"
    dockerfile.write_text(
        dockerfile.read_text(encoding="utf-8").replace(
            "RUN rm -rf /src/chummer.run-services/Chummer.Run.Api/bin\n",
            "",
            1,
        ),
        encoding="utf-8",
    )

    receipt = module.verify(
        [],
        allow_stale_foreign_build_locks=False,
        source_root=source_root,
    )

    assert receipt["status"] == "fail"
    dockerfile_check = next(check for check in receipt["sourceMarkerChecks"] if check["path"] == "Chummer.Run.Api/Dockerfile")
    assert (
        "RUN rm -rf /src/chummer.run-services/Chummer.Run.Api/bin"
        in dockerfile_check["missingMarkers"]
    )
    assert any(finding["id"] == "public_edge_source_marker_missing" for finding in receipt["findings"])


def test_source_marker_check_requires_public_edge_state_mountpoint_in_image(tmp_path: Path) -> None:
    module = load_module()
    source_root = write_complete_marker_source_tree(module, tmp_path / "source")
    dockerfile = source_root / "Chummer.Run.Api" / "Dockerfile"
    dockerfile.write_text(
        dockerfile.read_text(encoding="utf-8").replace(
            "mkdir -p /app/state; ",
            "",
        ),
        encoding="utf-8",
    )

    receipt = module.verify(
        [],
        allow_stale_foreign_build_locks=False,
        source_root=source_root,
    )

    assert receipt["status"] == "fail"
    dockerfile_check = next(check for check in receipt["sourceMarkerChecks"] if check["path"] == "Chummer.Run.Api/Dockerfile")
    assert "mkdir -p /app/state" in dockerfile_check["missingMarkers"]
    assert any(finding["id"] == "public_edge_source_marker_missing" for finding in receipt["findings"])


def test_main_checks_default_overlay_root_when_not_explicitly_configured(tmp_path: Path) -> None:
    module = load_module()
    module.PUBLIC_EDGE_OPERATIONAL_MIRROR_ROOTS = {}
    source_root = write_complete_marker_source_tree(module, tmp_path / "source")
    overlay_root = write_complete_marker_overlay_tree(module, tmp_path / "overlay", source_root)
    runtime_proof = tmp_path / "HUB_LOCAL_RELEASE_PROOF.generated.json"
    proof_text = write_valid_runtime_proof(runtime_proof)
    release_receipt = tmp_path / "RELEASE_CHANNEL.generated.json"
    release_receipt_sha256 = write_release_channel_receipt_for_proof(
        release_receipt,
        proof_text,
    )
    output_path = tmp_path / "preflight.json"

    module.process_lines_from_system = lambda: []
    module.resolve_default_source_root = lambda: source_root
    module.resolve_default_overlay_root = lambda: overlay_root
    snapshot_root = tmp_path / "public-projection"
    write_public_projection_snapshot(snapshot_root, proof_text)

    exit_code = module.main(
        [
            "--release-channel-receipt",
            str(release_receipt),
            "--release-channel-receipt-sha256",
            release_receipt_sha256,
            "--runtime-proof-bind-source-sha256",
            runtime_proof_sha256(proof_text),
            "--public-projection-snapshot-root",
            str(snapshot_root),
            "--output",
            str(output_path),
        ]
    )

    assert exit_code == 0
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["status"] == "pass"
    assert payload["overlayRoot"] == str(overlay_root.resolve())
    assert payload["overlayMarkerChecks"]
    assert payload["overlayBuildInfoSourceFingerprint"]["aggregateMatchesCurrentSource"] is True
    checks = {check["path"]: check for check in payload["overlayMarkerChecks"]}
    assert ".codex-studio/runtime/PUBLIC_EDGE_PORTAL_OVERLAY_BUILD_INFO.generated.json" in checks
    assert checks[".codex-studio/runtime/PUBLIC_EDGE_PORTAL_OVERLAY_BUILD_INFO.generated.json"]["missingMarkers"] == []
    assert '"landingBrowserRedirectStatus": "pass"' in checks[".codex-studio/runtime/PUBLIC_EDGE_PORTAL_OVERLAY_BUILD_INFO.generated.json"]["requiredMarkers"]


def test_full_preflight_requires_exact_runtime_proof_bind_source_mode_and_shape(
    tmp_path: Path,
) -> None:
    module = load_module()
    module.PUBLIC_EDGE_OPERATIONAL_MIRROR_ROOTS = {}
    source_root = write_complete_marker_source_tree(module, tmp_path / "source")
    proof_path = tmp_path / "published" / "HUB_LOCAL_RELEASE_PROOF.generated.json"
    proof_path.parent.mkdir(parents=True)

    valid_proof_text = write_valid_runtime_proof(proof_path)
    snapshot_root = tmp_path / "public-projection"
    authenticated_proof, _, _ = write_public_projection_snapshot(
        snapshot_root,
        valid_proof_text,
    )
    release_receipt = tmp_path / "published" / "RELEASE_CHANNEL.generated.json"
    release_receipt_sha256 = write_release_channel_receipt_for_proof(
        release_receipt,
        valid_proof_text,
    )

    receipt = module.verify(
        [],
        allow_stale_foreign_build_locks=False,
        source_root=source_root,
        public_projection_snapshot_root=snapshot_root,
        runtime_proof_bind_source=authenticated_proof,
        runtime_proof_bind_source_sha256=runtime_proof_sha256(valid_proof_text),
        release_channel_receipt=release_receipt,
        release_channel_receipt_sha256=release_receipt_sha256,
    )

    assert receipt["status"] == "pass"
    assert receipt["runtimeProofBindSource"]["status"] == "pass"
    assert receipt["runtimeProofBindSource"]["actualMode"] == "0644"
    assert receipt["runtimeProofBindSource"]["checks"]["pathStillBound"] is True
    assert receipt["runtimeProofBindSource"]["checks"]["semanticContract"] is True
    assert receipt["runtimeProofBindSource"]["checks"]["fresh"] is True
    assert receipt["runtimeProofBindSource"]["checks"]["releaseChannelAvailable"] is True

    invalid_proof = json.loads(valid_proof_text)
    del invalid_proof["release_channel"]["status"]
    proof_path.write_text(json.dumps(invalid_proof, indent=2) + "\n", encoding="utf-8")
    semantic_receipt = module.runtime_proof_bind_source_check(proof_path)
    assert semantic_receipt["status"] == "fail"
    assert semantic_receipt["checks"]["exactMode0644"] is True
    assert semantic_receipt["checks"]["strictJsonObject"] is True
    assert semantic_receipt["checks"]["semanticContract"] is False
    assert semantic_receipt["checks"]["releaseChannelAvailable"] is False

    stale_proof = json.loads(valid_proof_text)
    stale_proof["generatedAt"] = "2000-01-01T00:00:00Z"
    stale_proof["generated_at"] = "2000-01-01T00:00:00Z"
    proof_path.write_text(json.dumps(stale_proof, indent=2) + "\n", encoding="utf-8")
    stale_receipt = module.runtime_proof_bind_source_check(proof_path)
    assert stale_receipt["status"] == "fail"
    assert stale_receipt["checks"]["semanticContract"] is True
    assert stale_receipt["checks"]["fresh"] is False

    proof_path.write_text(
        '{"status":"passed","status":"passed"}\n',
        encoding="utf-8",
    )
    ambiguous_receipt = module.runtime_proof_bind_source_check(proof_path)
    assert ambiguous_receipt["status"] == "fail"
    assert ambiguous_receipt["checks"]["strictJsonObject"] is False

    proof_path.write_text(valid_proof_text, encoding="utf-8")

    authenticated_proof.chmod(0o664)
    receipt = module.verify(
        [],
        allow_stale_foreign_build_locks=False,
        source_root=source_root,
        public_projection_snapshot_root=snapshot_root,
        runtime_proof_bind_source=authenticated_proof,
        runtime_proof_bind_source_sha256=runtime_proof_sha256(valid_proof_text),
        release_channel_receipt=release_receipt,
        release_channel_receipt_sha256=release_receipt_sha256,
    )

    assert receipt["status"] == "fail"
    assert receipt["runtimeProofBindSource"]["checks"]["exactMode0644"] is False
    assert any(
        finding["id"] == "public_edge_runtime_proof_bind_source_invalid"
        for finding in receipt["findings"]
    )

    authenticated_proof.chmod(0o644)
    hardlink_path = tmp_path / "published" / "proof-hardlink.json"
    os.link(proof_path, hardlink_path)
    linked_receipt = module.runtime_proof_bind_source_check(proof_path)
    assert linked_receipt["status"] == "fail"
    assert linked_receipt["checks"]["singleLink"] is False

    proof_path.unlink()
    proof_path.symlink_to(hardlink_path)
    symlink_receipt = module.runtime_proof_bind_source_check(proof_path)
    assert symlink_receipt["status"] == "fail"
    assert symlink_receipt["checks"]["regularFile"] is False


@pytest.mark.parametrize(
    "current_mutation",
    ("empty", "candidate-import-missing", "candidate-import-true"),
)
def test_full_preflight_rejects_tampered_current_without_legacy_fallback(
    tmp_path: Path,
    current_mutation: str,
) -> None:
    module = load_module()
    module.PUBLIC_EDGE_OPERATIONAL_MIRROR_ROOTS = {}
    source_root = write_complete_marker_source_tree(module, tmp_path / "source")
    proof_source = tmp_path / "proof-source.json"
    proof_text = write_valid_runtime_proof(proof_source)
    snapshot_root = tmp_path / "public-projection"
    write_public_projection_snapshot(snapshot_root, proof_text)
    release_receipt = tmp_path / "RELEASE_CHANNEL.generated.json"
    release_receipt_sha256 = write_release_channel_receipt_for_proof(
        release_receipt,
        proof_text,
    )
    current_path = snapshot_root / "CURRENT.json"
    if current_mutation == "empty":
        current: dict[str, object] = {}
    else:
        current = json.loads(current_path.read_text(encoding="utf-8"))
        if current_mutation == "candidate-import-missing":
            del current["candidateImportAuthority"]
        else:
            current["candidateImportAuthority"] = True
    current_path.write_text(
        json.dumps(current, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    runtime_check_called = False

    def reject_legacy_fallback(*_args: object, **_kwargs: object) -> dict[str, object]:
        nonlocal runtime_check_called
        runtime_check_called = True
        raise AssertionError("legacy runtime proof fallback must not run")

    module.runtime_proof_bind_source_check = reject_legacy_fallback
    receipt = module.verify(
        [],
        allow_stale_foreign_build_locks=False,
        source_root=source_root,
        public_projection_snapshot_root=snapshot_root,
        runtime_proof_bind_source_sha256=runtime_proof_sha256(proof_text),
        release_channel_receipt=release_receipt,
        release_channel_receipt_sha256=release_receipt_sha256,
    )

    assert receipt["status"] == "fail"
    assert receipt["publicProjectionSnapshot"]["status"] == "fail"
    assert receipt["runtimeProofBindSource"]["status"] == "fail"
    assert runtime_check_called is False
    assert any(
        finding["id"] == "public_edge_runtime_proof_bind_source_invalid"
        for finding in receipt["findings"]
    )


@pytest.mark.parametrize(
    "route_mutation",
    [
        "forbidden-roster-extension",
        "prefix-reordered",
        "duplicate-installer",
        "installer-suffix-reordered",
    ],
)
def test_runtime_proof_requires_exact_registry_route_contract(
    tmp_path: Path,
    route_mutation: str,
) -> None:
    module = load_module()
    module.PUBLIC_EDGE_OPERATIONAL_MIRROR_ROOTS = {}
    proof_path = tmp_path / "HUB_LOCAL_RELEASE_PROOF.generated.json"
    valid_proof_text = write_valid_runtime_proof(proof_path)
    release_receipt = tmp_path / "RELEASE_CHANNEL.generated.json"
    release_receipt_sha256 = write_release_channel_receipt_for_proof(
        release_receipt,
        valid_proof_text,
    )
    proof = json.loads(valid_proof_text)
    routes = proof["proof_routes"]

    if route_mutation == "forbidden-roster-extension":
        routes.append("/account/roster")
    elif route_mutation == "prefix-reordered":
        routes[1], routes[2] = routes[2], routes[1]
    elif route_mutation == "duplicate-installer":
        routes.append(routes[-1])
    elif route_mutation == "installer-suffix-reordered":
        routes[-2], routes[-1] = routes[-1], routes[-2]
    else:  # pragma: no cover - protected by the parameter list.
        raise AssertionError(f"unexpected route mutation: {route_mutation}")

    proof_path.write_text(
        json.dumps(proof, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    receipt = module.runtime_proof_bind_source_check(
        proof_path,
        runtime_proof_bind_source_sha256=hashlib.sha256(
            proof_path.read_bytes()
        ).hexdigest(),
        release_channel_receipt=release_receipt,
        release_channel_receipt_sha256=release_receipt_sha256,
    )

    assert receipt["status"] == "fail"
    assert receipt["checks"]["canonicalJson"] is True
    assert receipt["checks"]["semanticContract"] is False
    assert any("proof_routes" in failure for failure in receipt["failures"])


def test_runtime_proof_rejects_registry_route_alias_drift(
    tmp_path: Path,
) -> None:
    module = load_module()
    proof_path = tmp_path / "HUB_LOCAL_RELEASE_PROOF.generated.json"
    valid_proof_text = write_valid_runtime_proof(proof_path)
    release_receipt = tmp_path / "RELEASE_CHANNEL.generated.json"
    release_receipt_sha256 = write_release_channel_receipt_for_proof(
        release_receipt,
        valid_proof_text,
    )
    proof = json.loads(valid_proof_text)
    proof["proofRoutes"] = [*proof["proof_routes"], "/account/roster"]
    proof_payload = (json.dumps(proof, indent=2, sort_keys=True) + "\n").encode(
        "utf-8"
    )
    proof_path.write_bytes(proof_payload)

    receipt = module.runtime_proof_bind_source_check(
        proof_path,
        runtime_proof_bind_source_sha256=hashlib.sha256(proof_payload).hexdigest(),
        release_channel_receipt=release_receipt,
        release_channel_receipt_sha256=release_receipt_sha256,
    )

    assert receipt["status"] == "fail"
    assert receipt["checks"]["digestMatchesExpected"] is True
    assert receipt["checks"]["canonicalJson"] is True
    assert receipt["checks"]["semanticContract"] is False
    assert any("alias values drift" in failure for failure in receipt["failures"])


@pytest.mark.skipif(
    not REGISTRY_RELEASE_PROOF_CONSUMER.is_file(),
    reason="multi-repository Registry consumer is not present",
)
def test_runtime_proof_fixture_is_accepted_by_registry_consumer(
    tmp_path: Path,
) -> None:
    proof_path = tmp_path / "HUB_LOCAL_RELEASE_PROOF.generated.json"
    proof = json.loads(write_valid_runtime_proof(proof_path))
    consumer = load_registry_release_proof_consumer()

    normalized = consumer.normalize_release_proof_payload(
        proof,
        source=str(proof_path),
    )

    assert normalized["proofRoutes"] == proof["proof_routes"]
    assert normalized["journeysPassed"] == proof["journeys_passed"]
    assert normalized["baseUrl"] == proof["base_url"]


def test_runtime_proof_capture_never_reads_beyond_max_plus_one(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_module()
    source = tmp_path / "runtime-proof.json"
    source.write_bytes(b"x")
    source.chmod(0o644)
    max_bytes = 17
    requested_sizes: list[int] = []

    def synthetic_growth_read(_descriptor: int, requested_size: int) -> bytes:
        requested_sizes.append(requested_size)
        assert sum(requested_sizes) <= max_bytes + 1
        return b"x" * requested_size

    monkeypatch.setattr(module.os, "read", synthetic_growth_read)

    capture = module._stable_bounded_file_capture(source, max_bytes=max_bytes)

    assert sum(requested_sizes) == max_bytes + 1
    assert len(capture["payload"]) == max_bytes + 1
    assert capture["boundedPayload"] is False


def test_runtime_proof_capture_rejects_fifo_without_blocking(tmp_path: Path) -> None:
    module = load_module()
    source = tmp_path / "runtime-proof.fifo"
    os.mkfifo(source, 0o644)

    capture = module._stable_bounded_file_capture(source, max_bytes=17)

    assert capture["regularFile"] is False
    assert capture["boundedPayload"] is False
    assert capture["payload"] == b""


@pytest.mark.parametrize(
    "pathological_payload",
    [
        b'{"oversizedInteger":' + (b"9" * 5000) + b"}\n",
        b'{"deep":' + (b"[" * 2000) + b"0" + (b"]" * 2000) + b"}\n",
    ],
    ids=["oversized-integer", "excessive-nesting"],
)
def test_runtime_proof_pathological_json_fails_closed_without_exception(
    tmp_path: Path,
    pathological_payload: bytes,
) -> None:
    module = load_module()
    proof_path = tmp_path / "HUB_LOCAL_RELEASE_PROOF.generated.json"
    proof_path.write_bytes(pathological_payload)
    proof_path.chmod(0o644)

    receipt = module.runtime_proof_bind_source_check(proof_path)

    assert receipt["status"] == "fail"
    assert receipt["checks"]["strictJsonObject"] is False
    assert receipt["failures"]
    assert all(
        len(failure) <= module.MAX_RUNTIME_PROOF_DETAIL_CHARS
        for failure in receipt["failures"]
    )


def test_runtime_proof_requires_deterministic_sorted_canonical_json(
    tmp_path: Path,
) -> None:
    module = load_module()
    proof_path = tmp_path / "HUB_LOCAL_RELEASE_PROOF.generated.json"
    valid_proof_text = write_valid_runtime_proof(proof_path)
    release_receipt = tmp_path / "RELEASE_CHANNEL.generated.json"
    release_receipt_sha256 = write_release_channel_receipt_for_proof(
        release_receipt,
        valid_proof_text,
    )
    proof = json.loads(valid_proof_text)
    reversed_proof = dict(reversed(list(proof.items())))
    reversed_payload = (
        json.dumps(reversed_proof, indent=2, sort_keys=False) + "\n"
    ).encode("utf-8")
    proof_path.write_bytes(reversed_payload)

    receipt = module.runtime_proof_bind_source_check(
        proof_path,
        runtime_proof_bind_source_sha256=hashlib.sha256(
            reversed_payload
        ).hexdigest(),
        release_channel_receipt=release_receipt,
        release_channel_receipt_sha256=release_receipt_sha256,
    )

    assert receipt["status"] == "fail"
    assert receipt["checks"]["strictJsonObject"] is True
    assert receipt["checks"]["canonicalJson"] is False
    assert receipt["checks"]["semanticContract"] is True
    assert receipt["sha256"] == hashlib.sha256(reversed_payload).hexdigest()


def test_runtime_proof_requires_independently_pinned_exact_bytes(
    tmp_path: Path,
) -> None:
    module = load_module()
    proof_path = tmp_path / "HUB_LOCAL_RELEASE_PROOF.generated.json"
    valid_proof_text = write_valid_runtime_proof(proof_path)
    release_receipt = tmp_path / "RELEASE_CHANNEL.generated.json"
    release_receipt_sha256 = write_release_channel_receipt_for_proof(
        release_receipt,
        valid_proof_text,
    )
    expected_proof_sha256 = runtime_proof_sha256(valid_proof_text)
    proof = json.loads(valid_proof_text)
    proof["unknownCanonicalField"] = {"value": "must not bypass byte authority"}
    changed_payload = (json.dumps(proof, indent=2, sort_keys=True) + "\n").encode(
        "utf-8"
    )
    proof_path.write_bytes(changed_payload)

    receipt = module.runtime_proof_bind_source_check(
        proof_path,
        runtime_proof_bind_source_sha256=expected_proof_sha256,
        release_channel_receipt=release_receipt,
        release_channel_receipt_sha256=release_receipt_sha256,
    )

    assert receipt["status"] == "fail"
    assert receipt["checks"]["canonicalJson"] is True
    assert receipt["checks"]["semanticContract"] is True
    assert receipt["checks"]["digestMatchesExpected"] is False
    assert receipt["expectedSha256"] == expected_proof_sha256
    assert receipt["sha256"] == hashlib.sha256(changed_payload).hexdigest()


def test_runtime_proof_rejects_noncanonical_expected_digest_text(
    tmp_path: Path,
) -> None:
    module = load_module()
    proof_path = tmp_path / "HUB_LOCAL_RELEASE_PROOF.generated.json"
    valid_proof_text = write_valid_runtime_proof(proof_path)
    release_receipt = tmp_path / "RELEASE_CHANNEL.generated.json"
    release_receipt_sha256 = write_release_channel_receipt_for_proof(
        release_receipt,
        valid_proof_text,
    )
    expected_proof_sha256 = runtime_proof_sha256(valid_proof_text)

    receipt = module.runtime_proof_bind_source_check(
        proof_path,
        runtime_proof_bind_source_sha256=f" {expected_proof_sha256}",
        release_channel_receipt=release_receipt,
        release_channel_receipt_sha256=release_receipt_sha256,
    )

    assert receipt["status"] == "fail"
    assert receipt["checks"]["digestMatchesExpected"] is False
    assert receipt["expectedSha256"] == f" {expected_proof_sha256}"
    assert any("lowercase SHA-256" in failure for failure in receipt["failures"])


def test_runtime_proof_binds_exact_independently_pinned_release_receipt(
    tmp_path: Path,
) -> None:
    module = load_module()
    proof_path = tmp_path / "HUB_LOCAL_RELEASE_PROOF.generated.json"
    valid_proof_text = write_valid_runtime_proof(proof_path)
    release_receipt = tmp_path / "RELEASE_CHANNEL.generated.json"
    release_receipt_sha256 = write_release_channel_receipt_for_proof(
        release_receipt,
        valid_proof_text,
    )

    passing_receipt = module.runtime_proof_bind_source_check(
        proof_path,
        runtime_proof_bind_source_sha256=runtime_proof_sha256(valid_proof_text),
        release_channel_receipt=release_receipt,
        release_channel_receipt_sha256=release_receipt_sha256,
    )
    assert passing_receipt["status"] == "pass"
    assert passing_receipt["checks"]["releaseChannelReceiptStable"] is True
    assert passing_receipt["checks"]["releaseChannelReceiptDigestMatches"] is True
    assert passing_receipt["checks"]["releaseChannelProjectionMatches"] is True
    assert re.fullmatch(r"[0-9a-f]{64}", passing_receipt["sha256"])

    wrong_digest_receipt = module.runtime_proof_bind_source_check(
        proof_path,
        runtime_proof_bind_source_sha256=runtime_proof_sha256(valid_proof_text),
        release_channel_receipt=release_receipt,
        release_channel_receipt_sha256="0" * 64,
    )
    assert wrong_digest_receipt["status"] == "fail"
    assert wrong_digest_receipt["checks"]["releaseChannelReceiptStable"] is True
    assert wrong_digest_receipt["checks"]["releaseChannelReceiptDigestMatches"] is False

    fabricated_proof = json.loads(valid_proof_text)
    fabricated_proof["release_channel"]["version"] = "fabricated-release"
    fabricated_proof["release_channel"]["releaseVersion"] = "fabricated-release"
    proof_path.write_text(
        json.dumps(fabricated_proof, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    fabricated_receipt = module.runtime_proof_bind_source_check(
        proof_path,
        runtime_proof_bind_source_sha256=hashlib.sha256(
            proof_path.read_bytes()
        ).hexdigest(),
        release_channel_receipt=release_receipt,
        release_channel_receipt_sha256=release_receipt_sha256,
    )
    assert fabricated_receipt["status"] == "fail"
    assert fabricated_receipt["checks"]["semanticContract"] is True
    assert fabricated_receipt["checks"]["releaseChannelReceiptDigestMatches"] is True
    assert fabricated_receipt["checks"]["releaseChannelProjectionMatches"] is False


def test_runtime_proof_binds_portable_registry_artifact_authority(
    tmp_path: Path,
) -> None:
    module = load_module()
    proof_path = tmp_path / "HUB_LOCAL_RELEASE_PROOF.generated.json"
    valid_proof_text = write_valid_runtime_proof(proof_path)
    release_receipt = tmp_path / "RELEASE_CHANNEL.generated.json"
    write_release_channel_receipt_for_proof(release_receipt, valid_proof_text)
    registry_commit = "a" * 40
    release_payload = json.loads(release_receipt.read_text(encoding="utf-8"))
    release_payload["registryCommit"] = registry_commit
    release_payload["registry_commit"] = registry_commit
    release_bytes = (
        json.dumps(release_payload, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    release_receipt.write_bytes(release_bytes)
    release_receipt_sha256 = hashlib.sha256(release_bytes).hexdigest()

    proof_payload = json.loads(valid_proof_text)
    proof_payload["release_channel"]["path"] = (
        "artifact://ArchonMegalon/chummer6-hub-registry"
        f"@{registry_commit}/sha256/{release_receipt_sha256}"
    )
    proof_bytes = (
        json.dumps(proof_payload, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    proof_path.write_bytes(proof_bytes)

    passing_receipt = module.runtime_proof_bind_source_check(
        proof_path,
        runtime_proof_bind_source_sha256=hashlib.sha256(proof_bytes).hexdigest(),
        release_channel_receipt=release_receipt,
        release_channel_receipt_sha256=release_receipt_sha256,
    )

    assert passing_receipt["status"] == "pass"
    assert passing_receipt["checks"]["releaseChannelProjectionMatches"] is True

    proof_payload["release_channel"]["path"] = (
        "artifact://ArchonMegalon/chummer6-hub-registry"
        f"@{registry_commit}/sha256/{'0' * 64}"
    )
    tampered_proof_bytes = (
        json.dumps(proof_payload, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    proof_path.write_bytes(tampered_proof_bytes)
    tampered_receipt = module.runtime_proof_bind_source_check(
        proof_path,
        runtime_proof_bind_source_sha256=hashlib.sha256(
            tampered_proof_bytes
        ).hexdigest(),
        release_channel_receipt=release_receipt,
        release_channel_receipt_sha256=release_receipt_sha256,
    )

    assert tampered_receipt["status"] == "fail"
    assert tampered_receipt["checks"]["releaseChannelReceiptDigestMatches"] is True
    assert tampered_receipt["checks"]["releaseChannelProjectionMatches"] is False

    release_payload["registry_commit"] = "b" * 40
    assert (
        module._expected_release_channel_projection(
            release_payload,
            receipt_sha256=release_receipt_sha256,
        )
        is None
    )


def test_full_preflight_cli_requires_independent_release_receipt_binding(
    tmp_path: Path,
) -> None:
    module = load_module()
    release_receipt = tmp_path / "RELEASE_CHANNEL.generated.json"
    release_receipt.write_text("{}\n", encoding="utf-8")

    with pytest.raises(SystemExit) as missing_receipt:
        module.main([])
    assert missing_receipt.value.code == 2

    with pytest.raises(SystemExit) as malformed_proof_digest:
        module.main(
            [
                "--runtime-proof-bind-source-sha256",
                "A" * 64,
            ]
        )
    assert malformed_proof_digest.value.code == 2

    with pytest.raises(SystemExit) as malformed_digest:
        module.main(
            [
                "--runtime-proof-bind-source-sha256",
                "0" * 64,
                "--release-channel-receipt",
                str(release_receipt),
                "--release-channel-receipt-sha256",
                "A" * 64,
            ]
        )
    assert malformed_digest.value.code == 2


@pytest.mark.parametrize("include_overlay", [False, True])
def test_deployment_preflight_argument_shapes_bind_exact_proof_and_receipt_pins(
    tmp_path: Path,
    include_overlay: bool,
) -> None:
    module = load_module()
    source_root = tmp_path / "source"
    overlay_root = tmp_path / "overlay"
    source_root.mkdir()
    overlay_root.mkdir()
    release_receipt = tmp_path / "RELEASE_CHANNEL.generated.json"
    runtime_digest = "1" * 64
    receipt_digest = "2" * 64
    snapshot_root = tmp_path / "public-projection"
    snapshot_root.mkdir()
    authenticated_proof = snapshot_root / "public-projection-test" / (
        "HUB_LOCAL_RELEASE_PROOF.generated.json"
    )
    output = tmp_path / ("full-overlay.json" if include_overlay else "source-only.json")
    captured: list[dict[str, object]] = []

    module.process_lines_from_system = lambda: []
    module.source_marker_findings = lambda _source: ([], [])
    module.execute_public_pwa_static_proof = lambda _source: {"status": "pass"}
    module.source_requires_operational_mirror_check = lambda _source: False
    module.operational_mirror_root_findings = lambda: ([], [])
    module.overlay_marker_findings = lambda _overlay: ([], [])
    module.overlay_build_info_source_fingerprint_check = (
        lambda _source, _overlay: ([], {})
    )
    module.resolve_current_snapshot = lambda selected_root, *, purpose: SimpleNamespace(
        snapshot_id="public-projection-test",
        snapshot_sha256="3" * 64,
        status="pass",
        projection_stage="release_upload_ready",
        code_deployment_authority=True,
        release_upload_authority=True,
        outputs={
            "HUB_LOCAL_RELEASE_PROOF.generated.json": authenticated_proof,
        },
        output_sha256={
            "HUB_LOCAL_RELEASE_PROOF.generated.json": runtime_digest,
        },
    ) if (
        selected_root == snapshot_root
        and purpose == module.PROJECTION_PURPOSE_RELEASE_UPLOAD
    ) else (_ for _ in ()).throw(
        AssertionError("unexpected projection snapshot root")
    )

    def capture_runtime_binding(
        path: Path,
        **kwargs: object,
    ) -> dict[str, object]:
        captured.append({"path": path, **kwargs})
        return {
            "status": "pass",
            "sourcePath": str(path),
            "sha256": runtime_digest,
            "expectedSha256": kwargs["runtime_proof_bind_source_sha256"],
            "releaseChannelReceiptPath": str(kwargs["release_channel_receipt"]),
            "releaseChannelReceiptExpectedSha256": kwargs[
                "release_channel_receipt_sha256"
            ],
            "releaseChannelReceiptActualSha256": receipt_digest,
            "checks": {
                "digestMatchesExpected": True,
                "releaseChannelReceiptDigestMatches": True,
            },
            "failures": [],
        }

    module.runtime_proof_bind_source_check = capture_runtime_binding
    arguments = [
        "--source-root",
        str(source_root),
        "--runtime-proof-bind-source-sha256",
        runtime_digest,
        "--public-projection-snapshot-root",
        str(snapshot_root),
        "--release-channel-receipt",
        str(release_receipt),
        "--release-channel-receipt-sha256",
        receipt_digest,
        "--output",
        str(output),
    ]
    if include_overlay:
        arguments.extend(["--overlay-root", str(overlay_root)])
    else:
        arguments.append("--skip-overlay-marker-check")

    assert module.main(arguments) == 0
    assert captured == [
        {
            "path": authenticated_proof,
            "runtime_proof_bind_source_sha256": runtime_digest,
            "release_channel_receipt": release_receipt,
            "release_channel_receipt_sha256": receipt_digest,
        }
    ]
    receipt = json.loads(output.read_text(encoding="utf-8"))
    proof_binding = receipt["runtimeProofBindSource"]
    assert proof_binding["sha256"] == runtime_digest
    assert proof_binding["expectedSha256"] == runtime_digest
    assert proof_binding["releaseChannelReceiptExpectedSha256"] == receipt_digest
    assert proof_binding["releaseChannelReceiptActualSha256"] == receipt_digest
    assert receipt["overlayRoot"] == (str(overlay_root) if include_overlay else "")


def test_code_deploy_preflight_records_review_required_authority(
    tmp_path: Path,
) -> None:
    module = load_module()
    source_root = tmp_path / "source"
    source_root.mkdir()
    snapshot_root = tmp_path / "public-projection"
    snapshot_root.mkdir()
    authenticated_proof = snapshot_root / "public-projection-test" / (
        "HUB_LOCAL_RELEASE_PROOF.generated.json"
    )
    runtime_digest = "1" * 64
    release_receipt = tmp_path / "RELEASE_CHANNEL.generated.json"
    release_digest = "2" * 64
    purposes: list[str] = []

    module.source_marker_findings = lambda _source: ([], [])
    module.execute_public_pwa_static_proof = lambda _source: {"status": "pass"}
    module.source_requires_operational_mirror_check = lambda _source: False
    module.operational_mirror_root_findings = lambda: ([], [])

    def resolve_projection(selected_root: Path, *, purpose: str) -> SimpleNamespace:
        assert selected_root == snapshot_root
        purposes.append(purpose)
        return SimpleNamespace(
            snapshot_id="public-projection-test",
            snapshot_sha256="3" * 64,
            status="review_required",
            projection_stage="code_deploy_review_required",
            code_deployment_authority=True,
            release_upload_authority=False,
            release_gate_findings=(
                {
                    "gate": "live public Windows installer",
                    "status": "postdeploy_required",
                    "reason": "live Windows installer proof must pass after code deployment",
                },
            ),
            outputs={
                "HUB_LOCAL_RELEASE_PROOF.generated.json": authenticated_proof,
            },
            output_sha256={
                "HUB_LOCAL_RELEASE_PROOF.generated.json": runtime_digest,
            },
        )

    module.resolve_current_snapshot = resolve_projection
    module.runtime_proof_bind_source_check = lambda *_args, **_kwargs: {
        "status": "pass",
        "failures": [],
    }

    receipt = module.verify(
        [],
        False,
        source_root=source_root,
        public_projection_snapshot_root=snapshot_root,
        public_projection_purpose=module.PROJECTION_PURPOSE_CODE_DEPLOY,
        runtime_proof_bind_source=authenticated_proof,
        runtime_proof_bind_source_sha256=runtime_digest,
        release_channel_receipt=release_receipt,
        release_channel_receipt_sha256=release_digest,
    )

    assert receipt["status"] == "pass"
    assert purposes == [module.PROJECTION_PURPOSE_CODE_DEPLOY]
    assert receipt["publicProjectionSnapshot"] == {
        "contractName": "chummer.public_projection_current/v1",
        "status": "pass",
        "purpose": "code-deploy",
        "projectionStatus": "review_required",
        "projectionStage": "code_deploy_review_required",
        "codeDeploymentAuthority": True,
        "releaseUploadAuthority": False,
        "releaseGateFindings": [
            {
                "gate": "live public Windows installer",
                "status": "postdeploy_required",
                "reason": "live Windows installer proof must pass after code deployment",
            }
        ],
        "snapshotRoot": str(snapshot_root),
        "snapshotId": "public-projection-test",
        "snapshotSha256": "3" * 64,
        "runtimeProofPath": str(authenticated_proof),
        "runtimeProofSha256": runtime_digest,
    }


def test_deploy_wires_one_snapshot_to_code_deploy_and_release_receipt() -> None:
    deploy = (REPO_ROOT / "scripts/deploy_public_edge_portal.sh").read_text(
        encoding="utf-8"
    )

    assert 'projection_purpose="code-deploy"' in deploy
    assert 'projection_purpose="candidate-import"' in deploy
    assert '--purpose "$projection_purpose"' in deploy
    assert "--output-name HUB_LOCAL_RELEASE_PROOF.generated.json" in deploy
    assert "--output-name RELEASE_CHANNEL.generated.json" in deploy
    assert "--public-projection-purpose code-deploy" in deploy
    assert "--expect-code-deploy-review-required" in deploy
    assert (
        "new public edge deploy requires the bounded review-required code-deploy snapshot"
        in deploy
    )
    assert (
        "/docker/chummercomplete/chummer-hub-registry/.codex-studio/published/"
        "RELEASE_CHANNEL.generated.json"
    ) not in deploy


def test_public_download_wrapper_passes_only_private_cloudflare_credentials_path() -> None:
    deploy = (REPO_ROOT / "scripts/deploy_public_edge_portal.sh").read_text(
        encoding="utf-8"
    )
    branch = deploy[
        deploy.index("if ((PUBLIC_DOWNLOAD_ONLY_OPERATION == 1)); then") :
        deploy.index('INSTALL_LINKING_CUTOVER_BOUNDARY=""')
    ]

    assert "CHUMMER_PUBLIC_DOWNLOAD_CLOUDFLARE_CREDENTIALS_FILE" in branch
    assert "CHUMMER_PUBLIC_DOWNLOAD_CLOUDFLARE_ACCOUNT_ID" in branch
    assert "CHUMMER_PUBLIC_DOWNLOAD_CLOUDFLARE_TUNNEL_ID" in branch
    assert "^[0-9a-f]{32}$" in branch
    assert (
        "^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-"
        "[0-9a-f]{4}-[0-9a-f]{12}$"
    ) in branch
    assert '"$TRUSTED_REALPATH" -e -- "$PUBLIC_DOWNLOAD_CLOUDFLARE_CREDENTIALS_INPUT"' in branch
    assert "! -f \"$PUBLIC_DOWNLOAD_CLOUDFLARE_CREDENTIALS\"" in branch
    assert "-L \"$PUBLIC_DOWNLOAD_CLOUDFLARE_CREDENTIALS\"" in branch
    assert "! -O \"$PUBLIC_DOWNLOAD_CLOUDFLARE_CREDENTIALS\"" in branch
    assert "'%h'" in branch
    assert "8#$public_download_cloudflare_credentials_mode & 8#077" in branch
    assert "public_download_cloudflare_credentials_size > 65536" in branch
    assert '--cloudflare-credentials-file "$PUBLIC_DOWNLOAD_CLOUDFLARE_CREDENTIALS"' in branch
    assert '--cloudflare-account-id "$PUBLIC_DOWNLOAD_CLOUDFLARE_ACCOUNT_ID"' in branch
    assert '--cloudflare-tunnel-id "$PUBLIC_DOWNLOAD_CLOUDFLARE_TUNNEL_ID"' in branch
    assert "--manifest-closure-restoration-spec" in branch
    assert "--release-candidate-root" in branch
    assert "--candidate-import-authority" in branch
    assert "--candidate-import-authority-sha256" in branch
    assert "--direct-import-receipt" in branch
    assert "--direct-import-receipt-sha256" in branch
    assert "--projection-snapshot-tree-sha256" in branch
    assert "--final-gold-source" in branch
    assert "--fleet-source" in branch
    assert "--operation-root" in branch
    assert "--delivery-phase" in branch
    assert "--migration-state-root" not in branch
    assert "--overlay-staging-root" not in branch
    assert "--transaction-journal" not in branch
    assert "--env-file" not in branch
    assert "--certificate-file" not in branch
    assert "--certificate-password-file" not in branch
    for secret_name in (
        "CLOUDFLARE_API_TOKEN",
        "CF_API_TOKEN",
        "CLOUDFLARE_EMAIL",
        "CLOUDFLARE_GLOBAL_API_KEY",
        "CLOUDFLARE_API_KEY",
    ):
        assert secret_name not in branch

    controller = branch.index(
        'CHUMMER_PUBLIC_EDGE_DEPLOY_LEASE_FD="$deploy_lock_lease_fd"'
    )
    clean_env = branch.rindex('"$TRUSTED_ENV" -i', 0, controller)
    assert clean_env < controller
    controller_environment = branch[clean_env:controller]
    assert "HOME=" not in controller_environment
    assert 'exec {public_download_controller_fd}<"$PUBLIC_DOWNLOAD_CONTROLLER"' in branch
    assert 'exec(code, namespace, namespace)' in branch
    assert "compose_cli stop" not in branch
    assert "docker stop" not in branch


def test_compose_source_capture_rejects_group_or_world_write(tmp_path: Path) -> None:
    attestor = load_compose_source_attestor()
    source = tmp_path / "docker-compose.public-edge.yml"
    source.write_text("services: {}\n", encoding="utf-8")
    source.chmod(0o666)
    receipt_root = tmp_path / "receipts"
    receipt_root.mkdir(mode=0o700)

    with pytest.raises(attestor.ComposeSourceError, match="owner-controlled"):
        attestor.capture(
            source,
            receipt_root / "compose.snapshot.yml",
            receipt_root / "compose-source.json",
        )


@pytest.mark.parametrize("mutation", ["same-inode", "exchange"])
def test_compose_source_guard_rejects_change_after_capture(
    tmp_path: Path,
    mutation: str,
) -> None:
    attestor = load_compose_source_attestor()
    source = tmp_path / "docker-compose.public-edge.yml"
    source.write_text("services: {}\n", encoding="utf-8")
    source.chmod(0o644)
    receipt_root = tmp_path / "receipts"
    receipt_root.mkdir(mode=0o700)
    snapshot = receipt_root / "compose.snapshot.yml"
    receipt = receipt_root / "compose-source.json"
    attestor.capture(source, snapshot, receipt)
    if mutation == "same-inode":
        original = source.stat()
        source.write_bytes(source.read_bytes())
        os.utime(
            source,
            ns=(original.st_atime_ns, original.st_mtime_ns + 1_000_000_000),
        )
    else:
        retired = tmp_path / "retired-compose.yml"
        source.rename(retired)
        source.write_bytes(retired.read_bytes())
        source.chmod(0o644)

    with pytest.raises(attestor.ComposeSourceError, match="changed"):
        attestor.verify(source, snapshot, receipt)


@pytest.mark.parametrize("mutation", ["content", "exchange"])
def test_compose_environment_binding_rejects_drift_without_copying_content(
    tmp_path: Path,
    mutation: str,
) -> None:
    attestor = load_compose_source_attestor()
    source = tmp_path / ".env"
    sentinel = "DATABASE_PASSWORD=credential-like-sentinel\n"
    source.write_text(
        sentinel
        + "CHUMMER_PUBLIC_CANONICAL_ORIGIN=https://chummer.run\n",
        encoding="utf-8",
    )
    source.chmod(0o600)
    receipt_root = tmp_path / "receipts"
    receipt_root.mkdir(mode=0o700)
    receipt = receipt_root / "compose-environment.json"

    captured = attestor.capture_environment(source, receipt)

    assert captured["status"] == "pass"
    assert captured["sourceContentPersisted"] is False
    assert sentinel not in receipt.read_text(encoding="utf-8")
    assert attestor.verify_environment(source, receipt)["status"] == "pass"
    if mutation == "content":
        source.write_text(
            sentinel + "CHUMMER_PUBLIC_CANONICAL_ORIGIN=http://stale.invalid\n",
            encoding="utf-8",
        )
        source.chmod(0o600)
    else:
        retired = tmp_path / "retired.env"
        source.rename(retired)
        source.write_bytes(retired.read_bytes())
        source.chmod(0o600)

    with pytest.raises(attestor.ComposeSourceError, match="changed"):
        attestor.verify_environment(source, receipt)


def test_deploy_seals_every_compose_read_to_one_guarded_snapshot() -> None:
    deploy = (REPO_ROOT / "scripts/deploy_public_edge_portal.sh").read_text(
        encoding="utf-8"
    )
    recovery = (REPO_ROOT / "scripts/public_edge_deploy_recovery.py").read_text(
        encoding="utf-8"
    )

    assert "(8#$COMPOSE_FILE_MODE & 8#022)" in deploy
    assert '"$COMPOSE_SOURCE_ATTESTOR" capture' in deploy
    assert '"$COMPOSE_SOURCE_ATTESTOR" verify' in deploy
    assert '"$COMPOSE_SOURCE_ATTESTOR" capture-environment' in deploy
    assert '"$COMPOSE_SOURCE_ATTESTOR" verify-environment' in deploy
    guard = deploy[
        deploy.index("run_compose_source_guarded() {") :
        deploy.index("run_compose_source_only_guarded() {")
    ]
    command = guard.index('  "$@" || command_status=$?')
    assert guard.index("verify_compose_environment_binding") < command
    assert guard.rindex("verify_compose_environment_binding") > command
    assert '-f "$COMPOSE_SOURCE_SNAPSHOT" --project-directory "$SOURCE_ROOT"' in deploy
    assert (
        'compose_cli() {\n  run_compose_source_guarded "${compose_command[@]}" "$@"\n}'
        in deploy
    )
    assert deploy.count('"${compose_command[@]}"') == 1
    assert "docker_cli compose" not in deploy
    assert '--compose-file "$COMPOSE_SOURCE_SNAPSHOT"' in deploy
    assert (
        'run_compose_source_guarded \\\n'
        '  trusted_source_python "$ROOT_DIR/scripts/verify_public_edge_deploy_source.py"'
        in deploy
    )
    assert '"--project-directory",\n            str(source_root),' in recovery


def test_deploy_bounds_initial_release_shelf_cutover_and_returns_to_steady() -> None:
    deploy = (REPO_ROOT / "scripts/deploy_public_edge_portal.sh").read_text(
        encoding="utf-8"
    )

    assert "deploy|recover|recover-adopt-verified-prior-runtime-baseline" in deploy
    assert "initial-release-shelf-cutover|initial-release-shelf-cutover-recover" in deploy
    assert "configure_compose_operation initial-release-shelf-cutover" in deploy
    assert "configure_compose_operation initial-release-shelf-cutover-recover" in deploy
    assert 'CHUMMER_RELEASE_SHELF_LAYOUT_V1_REQUIRED="$layout_v1_required"' in deploy
    assert (
        'CHUMMER_RELEASE_SHELF_INITIAL_MIGRATION_ALLOWED="$initial_migration_allowed"'
        in deploy
    )
    assert deploy.count('--operation "$COMPOSE_ATTESTATION_OPERATION"') == 3
    request_start = deploy.index(
        'trusted_source_python "$CUTOVER_ATTESTOR" request-start'
    )
    first_candidate_instruction = deploy.index("if ! start_candidate_portal;", request_start)
    assert request_start < first_candidate_instruction
    retirement = deploy.index("cutover candidate retirement", first_candidate_instruction)
    steady_posture = deploy.index("configure_compose_operation deploy", retirement)
    second_candidate_instruction = deploy.index(
        'abort_portal_recreate "steady blue-green candidate creation"',
        steady_posture,
    )
    assert retirement < steady_posture < second_candidate_instruction
    assert 'exec "$SCRIPT_PATH" initial-release-shelf-cutover-recover' in deploy
    assert "initial_release_shelf_cutover_committed_safe_handoff" in deploy
    assert "chummer.initial-release-shelf-cutover-poststate/v1" in deploy
    assert deploy.count('"$CUTOVER_ATTESTOR" verify-outcome') == 1
    assert deploy.count('"$CUTOVER_ATTESTOR" verify-handoff') == 1


def test_cutover_finalize_consumes_only_immediate_owner_only_gate_snapshots() -> None:
    deploy = (REPO_ROOT / "scripts/deploy_public_edge_portal.sh").read_text(
        encoding="utf-8"
    )

    assert deploy.count('--kind compose') == 2
    assert deploy.count('--kind postdeploy') == 1
    assert deploy.count('--kind active-runtime') == 1
    assert '--output "$PUBLICATION_READINESS_ATTESTATION"' in deploy
    assert '--compose-attestation "$FINAL_COMPOSE_ATTESTATION_SNAPSHOT"' in deploy
    assert (
        '--publication-readiness-attestation "$PUBLICATION_READINESS_ATTESTATION"'
        in deploy
    )
    assert (
        '--postdeploy-attestation "$FINAL_POSTDEPLOY_ATTESTATION_SNAPSHOT"'
        in deploy
    )
    assert '--active-runtime-authority "$ACTIVE_RUNTIME_AUTHORITY_SNAPSHOT"' in deploy
    assert '--candidate-image-id "$image_id"' in deploy
    assert '--image-id "$image_id"' not in deploy

    postdeploy_success = deploy.index('if "${postdeploy_command[@]}"; then')
    postdeploy_snapshot = deploy.index('--kind postdeploy', postdeploy_success)
    postdeploy_break = deploy.index("    break", postdeploy_success)
    assert postdeploy_success < postdeploy_snapshot < postdeploy_break

    overlay_complete = deploy.index(
        'public_edge_overlay_transaction.py" complete'
    )
    runtime_snapshot = deploy.index('--kind active-runtime', overlay_complete)
    finalize = deploy.index('"$CUTOVER_ATTESTOR" finalize', runtime_snapshot)
    transaction_retired = deploy.index(
        "deployment_transaction_active=0",
        finalize,
    )
    assert overlay_complete < runtime_snapshot < finalize < transaction_retired

    migration_readiness = deploy.index(
        'if ! verify_candidate_publication_readiness; then'
    )
    final_readiness = deploy.index(
        'if ! capture_candidate_publication_readiness; then',
        migration_readiness,
    )
    readiness_record = deploy.index('"$CUTOVER_ATTESTOR" record-readiness')
    assert readiness_record < migration_readiness < final_readiness


def test_completed_cutover_state_stays_on_ordinary_deploy_path() -> None:
    deploy = (REPO_ROOT / "scripts/deploy_public_edge_portal.sh").read_text(
        encoding="utf-8"
    )

    operation_case = deploy[
        deploy.index('case "$DEPLOY_OPERATION" in', deploy.index("inspect-deploy-state")) :
        deploy.index("container_proof_sha256_by_id()")
    ]
    assert '"$CUTOVER_STATE_CLASSIFICATION" == steady-handoff' in operation_case
    assert '"$CUTOVER_STATE_CLASSIFICATION" == complete' not in operation_case
    assert deploy.count("CUTOVER_STEADY_HANDOFF=1") == 1


def test_lock_only_cli_remains_available_without_runtime_proof_pins(
    tmp_path: Path,
) -> None:
    module = load_module()
    output_path = tmp_path / "lock-only-preflight.json"
    module.process_lines_from_system = lambda: []

    exit_code = module.main(
        [
            "--skip-source-marker-check",
            "--skip-overlay-marker-check",
            "--output",
            str(output_path),
        ]
    )

    assert exit_code == 0
    receipt = json.loads(output_path.read_text(encoding="utf-8"))
    assert receipt["status"] == "pass"
    assert receipt["sourceMarkerChecks"] == []
    assert receipt["runtimeProofBindSource"] == {}


def test_runtime_proof_default_matches_canonical_compose_bind_source() -> None:
    module = load_module()
    compose_text = (REPO_ROOT / "docker-compose.public-edge.yml").read_text(
        encoding="utf-8"
    )

    assert module.PUBLIC_EDGE_PROJECTION_SNAPSHOT_ROOT == Path(
        "/docker/chummercomplete/chummer.run-services/.codex-studio/published"
    )
    assert compose_text.count(
        "${CHUMMER_PUBLIC_EDGE_RUNTIME_PROOF_BIND_SOURCE:?Set the authenticated CURRENT Hub proof output}"
    ) == 2
    assert (
        "/app/wwwroot/proofs/mac-codex-release/HUB_LOCAL_RELEASE_PROOF.generated.json"
        in compose_text
    )
    assert compose_text.count(
        "${CHUMMER_PUBLIC_EDGE_PROJECTION_SNAPSHOT_ROOT:?Set the authenticated public projection snapshot root}"
    ) == 1
    assert not module.PUBLIC_EDGE_PROJECTION_SNAPSHOT_ROOT.is_relative_to(
        module.RUN_SERVICES_ROOT
    ) or module.RUN_SERVICES_ROOT == Path("/docker/chummercomplete/chummer.run-services")


def test_alternate_source_still_checks_canonical_runtime_proof_bind_source(
    tmp_path: Path,
) -> None:
    module = load_module()
    module.PUBLIC_EDGE_OPERATIONAL_MIRROR_ROOTS = {}
    alternate_source = tmp_path / "alternate-clean-source"
    checked_paths: list[Path] = []

    module.source_marker_findings = lambda _source: ([], [])
    module.execute_public_pwa_static_proof = lambda _source: {"status": "pass"}
    module.operational_mirror_findings = lambda _source: ([], [])

    def capture_runtime_proof(path: Path, **_kwargs: object) -> dict[str, object]:
        checked_paths.append(path)
        return {"status": "pass", "sourcePath": str(path)}

    module.runtime_proof_bind_source_check = capture_runtime_proof
    proof_text = write_valid_runtime_proof(tmp_path / "proof-source.json")
    snapshot_root = tmp_path / "public-projection"
    authenticated_proof, _, _ = write_public_projection_snapshot(
        snapshot_root,
        proof_text,
    )

    receipt = module.verify(
        [],
        allow_stale_foreign_build_locks=False,
        source_root=alternate_source,
        public_projection_snapshot_root=snapshot_root,
    )

    assert receipt["status"] == "pass"
    assert checked_paths == [authenticated_proof]
    assert checked_paths[0] != alternate_source / ".codex-studio" / "published" / (
        "HUB_LOCAL_RELEASE_PROOF.generated.json"
    )


def test_main_can_skip_overlay_marker_check(tmp_path: Path) -> None:
    module = load_module()
    module.PUBLIC_EDGE_OPERATIONAL_MIRROR_ROOTS = {}
    source_root = write_complete_marker_source_tree(module, tmp_path / "source")
    overlay_root = tmp_path / "overlay-missing"
    runtime_proof = tmp_path / "HUB_LOCAL_RELEASE_PROOF.generated.json"
    proof_text = write_valid_runtime_proof(runtime_proof)
    release_receipt = tmp_path / "RELEASE_CHANNEL.generated.json"
    release_receipt_sha256 = write_release_channel_receipt_for_proof(
        release_receipt,
        proof_text,
    )
    output_path = tmp_path / "preflight.json"

    module.process_lines_from_system = lambda: []
    module.resolve_default_source_root = lambda: source_root
    module.resolve_default_overlay_root = lambda: overlay_root
    snapshot_root = tmp_path / "public-projection"
    write_public_projection_snapshot(snapshot_root, proof_text)

    exit_code = module.main(
        [
            "--skip-overlay-marker-check",
            "--release-channel-receipt",
            str(release_receipt),
            "--release-channel-receipt-sha256",
            release_receipt_sha256,
            "--runtime-proof-bind-source-sha256",
            runtime_proof_sha256(proof_text),
            "--public-projection-snapshot-root",
            str(snapshot_root),
            "--output",
            str(output_path),
        ]
    )

    assert exit_code == 0
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["status"] == "pass"
    assert payload["overlayRoot"] == ""
    assert payload["overlayMarkerChecks"] == []
    assert payload["overlayBuildInfoSourceFingerprint"] == {}


def test_overlay_build_info_source_fingerprint_check_requires_current_source_match(tmp_path: Path) -> None:
    module = load_module()
    source_root = write_complete_marker_source_tree(module, tmp_path / "source")
    overlay_root = write_complete_marker_overlay_tree(module, tmp_path / "overlay", source_root)
    landing = source_root / "Chummer.Run.Api" / "Views" / "PublicLanding" / "Landing.cshtml"
    landing.write_text(landing.read_text(encoding="utf-8") + "\nsource drift\n", encoding="utf-8")

    receipt = module.verify(
        [],
        allow_stale_foreign_build_locks=False,
        source_root=source_root,
        overlay_root=overlay_root,
        check_overlay_markers=True,
    )

    assert receipt["status"] == "fail"
    assert receipt["overlayBuildInfoSourceFingerprint"]["aggregateMatchesCurrentSource"] is False
    assert "landing" in receipt["overlayBuildInfoSourceFingerprint"]["mismatchedKeys"]
    assert any(finding["id"] == "public_edge_overlay_source_fingerprint_mismatch" for finding in receipt["findings"])


@pytest.mark.parametrize(
    "injected_field",
    ('"status":"fail",', '"unrelated":NaN,'),
)
def test_overlay_build_info_rejects_non_strict_json(
    tmp_path: Path,
    injected_field: str,
) -> None:
    module = load_module()
    source_root = write_complete_marker_source_tree(module, tmp_path / "source")
    overlay_root = write_complete_marker_overlay_tree(module, tmp_path / "overlay", source_root)
    build_info_path = (
        overlay_root
        / ".codex-studio/runtime/PUBLIC_EDGE_PORTAL_OVERLAY_BUILD_INFO.generated.json"
    )
    original = build_info_path.read_text(encoding="utf-8")
    build_info_path.write_text(
        original.replace("{", "{" + injected_field, 1),
        encoding="utf-8",
    )

    findings, check = module.overlay_build_info_source_fingerprint_check(
        source_root,
        overlay_root,
    )

    assert check["aggregateMatchesCurrentSource"] is False
    assert "status" in check["semanticMismatches"]
    assert any(
        finding["id"] == "public_edge_overlay_build_info_contract_invalid"
        for finding in findings
    )


def test_load_json_file_rejects_oversized_and_aliased_inputs(tmp_path: Path) -> None:
    module = load_module()
    oversized = tmp_path / "oversized.json"
    oversized.write_bytes(b"{" + b" " * module.MAX_OVERLAY_BUILD_INFO_BYTES + b"}")
    assert module.load_json_file(oversized) == {}

    source = tmp_path / "source.json"
    source.write_text('{"status":"pass"}\n', encoding="utf-8")
    symlink = tmp_path / "symlink.json"
    symlink.symlink_to(source)
    assert module.load_json_file(symlink) == {}

    hardlink = tmp_path / "hardlink.json"
    os.link(source, hardlink)
    assert module.load_json_file(source) == {}
    assert module.load_json_file(hardlink) == {}


def test_load_json_file_rejects_path_replacement_during_read(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_module()
    path = tmp_path / "build-info.json"
    path.write_text('{"status":"pass"}\n', encoding="utf-8")
    replacement = tmp_path / "replacement.json"
    replacement.write_text('{"status":"replacement"}\n', encoding="utf-8")
    real_read = module.os.read
    replaced = False

    def read_and_replace(descriptor: int, byte_count: int) -> bytes:
        nonlocal replaced
        payload = real_read(descriptor, byte_count)
        if payload and not replaced:
            replaced = True
            os.replace(replacement, path)
        return payload

    monkeypatch.setattr(module.os, "read", read_and_replace)

    assert module.load_json_file(path) == {}


def test_stable_json_reader_rejects_ctime_only_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_module()
    path = tmp_path / "build-info.json"
    path.write_text('{"status":"pass"}\n', encoding="utf-8")
    real_fstat = module.os.fstat
    call_count = 0

    def fstat_with_ctime_drift(descriptor: int):
        nonlocal call_count
        call_count += 1
        identity = real_fstat(descriptor)
        if call_count != 2:
            return identity
        return SimpleNamespace(
            st_dev=identity.st_dev,
            st_ino=identity.st_ino,
            st_size=identity.st_size,
            st_mtime_ns=identity.st_mtime_ns,
            st_ctime_ns=identity.st_ctime_ns + 1,
            st_nlink=identity.st_nlink,
            st_mode=identity.st_mode,
        )

    monkeypatch.setattr(module.os, "fstat", fstat_with_ctime_drift)

    with pytest.raises(RuntimeError, match="changed while it was read"):
        module._read_bounded_regular_file(
            path,
            max_bytes=module.MAX_OVERLAY_BUILD_INFO_BYTES,
        )


def test_overlay_build_info_source_fingerprint_check_catches_status_view_drift(tmp_path: Path) -> None:
    module = load_module()
    source_root = write_complete_marker_source_tree(module, tmp_path / "source")
    overlay_root = write_complete_marker_overlay_tree(module, tmp_path / "overlay", source_root)
    status_view = source_root / "Chummer.Run.Api" / "Views" / "PublicLanding" / "Status.cshtml"
    status_view.write_text(status_view.read_text(encoding="utf-8") + "\nstatus drift\n", encoding="utf-8")

    receipt = module.verify(
        [],
        allow_stale_foreign_build_locks=False,
        source_root=source_root,
        overlay_root=overlay_root,
        check_overlay_markers=True,
    )

    assert receipt["status"] == "fail"
    assert receipt["overlayBuildInfoSourceFingerprint"]["aggregateMatchesCurrentSource"] is False
    assert "status" in receipt["overlayBuildInfoSourceFingerprint"]["mismatchedKeys"]
    assert any(finding["id"] == "public_edge_overlay_source_fingerprint_mismatch" for finding in receipt["findings"])


def test_overlay_build_info_source_fingerprint_check_catches_auth_entry_drift(tmp_path: Path) -> None:
    module = load_module()
    source_root = write_complete_marker_source_tree(module, tmp_path / "source")
    overlay_root = write_complete_marker_overlay_tree(module, tmp_path / "overlay", source_root)
    auth_entry = source_root / "Chummer.Run.Api" / "Views" / "Auth" / "Entry.cshtml"
    auth_entry.write_text(auth_entry.read_text(encoding="utf-8") + "\nauth drift\n", encoding="utf-8")

    receipt = module.verify(
        [],
        allow_stale_foreign_build_locks=False,
        source_root=source_root,
        overlay_root=overlay_root,
        check_overlay_markers=True,
    )

    assert receipt["status"] == "fail"
    assert receipt["overlayBuildInfoSourceFingerprint"]["aggregateMatchesCurrentSource"] is False
    assert "authEntryView" in receipt["overlayBuildInfoSourceFingerprint"]["mismatchedKeys"]
    assert any(finding["id"] == "public_edge_overlay_source_fingerprint_mismatch" for finding in receipt["findings"])


def test_overlay_build_info_source_fingerprint_catches_noncritical_build_input_drift(
    tmp_path: Path,
) -> None:
    module = load_module()
    source_root = write_complete_marker_source_tree(module, tmp_path / "source")
    controller = source_root / "Chummer.Run.Api" / "Controllers" / "PublicLandingController.cs"
    controller.parent.mkdir(parents=True, exist_ok=True)
    controller.write_text("public landing controller\n", encoding="utf-8")
    overlay_root = write_complete_marker_overlay_tree(module, tmp_path / "overlay", source_root)
    controller.write_text(
        controller.read_text(encoding="utf-8") + "\nnoncritical build-input drift\n",
        encoding="utf-8",
    )

    receipt = module.verify(
        [],
        allow_stale_foreign_build_locks=False,
        source_root=source_root,
        overlay_root=overlay_root,
        check_overlay_markers=True,
    )

    fingerprint = receipt["overlayBuildInfoSourceFingerprint"]
    assert receipt["status"] == "fail"
    assert fingerprint["criticalAggregateMatchesCurrentSource"] is True
    assert fingerprint["buildInputsMatchCurrentSource"] is False
    assert fingerprint["aggregateMatchesCurrentSource"] is False
    assert "buildInputAggregateSha256" in fingerprint["mismatchedKeys"]
    assert any(
        finding["id"] == "public_edge_overlay_source_fingerprint_mismatch"
        for finding in receipt["findings"]
    )


def test_overlay_build_info_source_fingerprint_rejects_wrong_algorithm_and_missing_critical_detail(
    tmp_path: Path,
) -> None:
    module = load_module()
    source_root = write_complete_marker_source_tree(module, tmp_path / "source")
    overlay_root = write_complete_marker_overlay_tree(module, tmp_path / "overlay", source_root)
    build_info_path = (
        overlay_root
        / ".codex-studio/runtime/PUBLIC_EDGE_PORTAL_OVERLAY_BUILD_INFO.generated.json"
    )
    payload = json.loads(build_info_path.read_text(encoding="utf-8"))
    payload["sourceFingerprint"]["buildInputs"]["algorithm"] = "sha256-path-only-v0"
    del payload["sourceFingerprint"]["files"]["landing"]
    build_info_path.write_text(json.dumps(payload) + "\n", encoding="utf-8")

    receipt = module.verify(
        [],
        allow_stale_foreign_build_locks=False,
        source_root=source_root,
        overlay_root=overlay_root,
        check_overlay_markers=True,
    )

    fingerprint = receipt["overlayBuildInfoSourceFingerprint"]
    assert receipt["status"] == "fail"
    assert fingerprint["buildInputsMatchCurrentSource"] is False
    assert fingerprint["criticalFileDetailsMatchCurrentSource"] is False
    assert fingerprint["aggregateMatchesCurrentSource"] is False
    assert "sourceFingerprint.buildInputs.algorithm" in fingerprint["missingKeys"]
    assert "sourceFingerprint.files.landing.sha256" in fingerprint["missingKeys"]


def test_overlay_build_info_source_fingerprint_catches_copied_design_payload_drift(
    tmp_path: Path,
) -> None:
    module = load_module()
    source_root = write_complete_marker_source_tree(
        module,
        tmp_path / "chummer.run-services",
    )
    overlay_root = write_complete_marker_overlay_tree(module, tmp_path / "overlay", source_root)
    design_path = source_root / ".codex-design" / "product" / "ORIGIN_BOOK_STUDIO.md"
    design_path.write_text(
        design_path.read_text(encoding="utf-8") + "\npayload drift\n",
        encoding="utf-8",
    )

    receipt = module.verify(
        [],
        allow_stale_foreign_build_locks=False,
        source_root=source_root,
        overlay_root=overlay_root,
        check_overlay_markers=True,
    )

    fingerprint = receipt["overlayBuildInfoSourceFingerprint"]
    assert receipt["status"] == "fail"
    assert fingerprint["criticalAggregateMatchesCurrentSource"] is True
    assert fingerprint["buildInputsMatchCurrentSource"] is True
    assert fingerprint["overlayPayloadInputsMatchCurrentSource"] is False
    assert fingerprint["aggregateMatchesCurrentSource"] is False
    assert "overlayPayloadInputAggregateSha256" in fingerprint["mismatchedKeys"]


def test_overlay_build_info_contract_uses_parsed_top_level_activation_state(
    tmp_path: Path,
) -> None:
    module = load_module()
    source_root = write_complete_marker_source_tree(module, tmp_path / "source")
    overlay_root = write_complete_marker_overlay_tree(module, tmp_path / "overlay", source_root)
    build_info_path = (
        overlay_root
        / ".codex-studio/runtime/PUBLIC_EDGE_PORTAL_OVERLAY_BUILD_INFO.generated.json"
    )
    payload = json.loads(build_info_path.read_text(encoding="utf-8"))
    payload["status"] = "fail"
    payload["activationStatus"] = "staged_only"
    payload["nestedSpoof"] = {
        "status": "pass",
        "activationStatus": "activated",
    }
    build_info_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    receipt = module.verify(
        [],
        allow_stale_foreign_build_locks=False,
        source_root=source_root,
        overlay_root=overlay_root,
        check_overlay_markers=True,
    )

    fingerprint = receipt["overlayBuildInfoSourceFingerprint"]
    assert receipt["status"] == "fail"
    assert fingerprint["aggregateMatchesCurrentSource"] is True
    assert fingerprint["semanticMismatches"] == ["activationStatus", "status"]
    assert any(
        finding["id"] == "public_edge_overlay_build_info_contract_invalid"
        for finding in receipt["findings"]
    )


def test_overlay_build_info_fingerprint_rejects_unbound_overlay_payload_tamper(
    tmp_path: Path,
) -> None:
    module = load_module()
    source_root = write_complete_marker_source_tree(module, tmp_path / "source")
    overlay_root = write_complete_marker_overlay_tree(module, tmp_path / "overlay", source_root)
    (overlay_root / "unverified-tamper.bin").write_text("tampered\n", encoding="utf-8")

    receipt = module.verify(
        [],
        allow_stale_foreign_build_locks=False,
        source_root=source_root,
        overlay_root=overlay_root,
        check_overlay_markers=True,
    )

    fingerprint = receipt["overlayBuildInfoSourceFingerprint"]
    assert receipt["status"] == "fail"
    assert fingerprint["stagedPayloadMatchesRecordedFingerprint"] is False
    assert fingerprint["aggregateMatchesCurrentSource"] is False
    assert "stagedPayloadAggregateSha256" in fingerprint["mismatchedKeys"]


def write_complete_marker_source_tree(module, source_root: Path) -> Path:
    module.execute_public_pwa_static_proof = lambda root: {
        "contractName": "chummer.public_edge_pwa_static_preflight.v1",
        "status": "pass",
        "executionMode": "test_fixture",
        "checks": {
            "verifierPass": True,
            "mirrorContractV5": True,
            "identityPinned": True,
            "identityRevalidated": True,
            "subprocessCompleted": True,
            "subprocessSucceeded": True,
            "inventoryContractV2": True,
            "policyIdentity": True,
            "exactAssetPolicyCount": True,
            "exactDependencyPolicyCount": True,
            "checkedAssetCount": True,
            "symlinkPolicy": True,
            "temporaryRegenerationPass": True,
            "generatorPolicyIdentity": True,
            "generatorAssetPolicyCount": True,
            "generatorDependencyPolicyCount": True,
            "generatorSymlinkPolicy": True,
            "siblingPlaySourceValidated": True,
        },
        "mirrorContract": "play-install-mirror-v5",
        "inventoryContract": "play-install-mirror-required-inventory-v2",
        "policyId": "chummer.public-play-pwa-mirror.v1",
        "checkedAssetCount": 12,
        "failureCount": 0,
        "failures": [],
        "failuresTruncated": False,
        "failureLimit": module.MAX_PUBLIC_PWA_PROOF_FAILURES,
        "detailCharacterLimit": module.MAX_PUBLIC_PWA_PROOF_DETAIL_CHARS,
    }
    source_root.mkdir()
    for relative_path, markers in module.PUBLIC_EDGE_REQUIRED_SOURCE_MARKERS.items():
        path = source_root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(markers) + "\n", encoding="utf-8")
    for relative_path in (
        "Chummer.Run.Api/Chummer.Run.Api.csproj",
        "package-lock.json",
    ):
        path = source_root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes((REPO_ROOT / relative_path).read_bytes())
    # Docker semantics are validated structurally, so this fixture must contain executable
    # instructions rather than a bag of marker strings.
    (source_root / module.PUBLIC_EDGE_DOCKERFILE_RELATIVE_PATH).write_text(
        (REPO_ROOT / module.PUBLIC_EDGE_DOCKERFILE_RELATIVE_PATH).read_text(
            encoding="utf-8"
        ),
        encoding="utf-8",
    )
    (source_root / module.PUBLIC_EDGE_COMPOSE_RELATIVE_PATH).write_text(
        (REPO_ROOT / module.PUBLIC_EDGE_COMPOSE_RELATIVE_PATH).read_text(
            encoding="utf-8"
        ),
        encoding="utf-8",
    )
    for key, relative_path in module.PUBLIC_EDGE_OVERLAY_SOURCE_FINGERPRINT_FILES.items():
        path = source_root / relative_path
        if path.exists():
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"{key}\n", encoding="utf-8")
    return source_root


def write_complete_marker_overlay_tree(module, overlay_root: Path, source_root: Path) -> Path:
    overlay_root.mkdir()
    for relative_path, markers in module.PUBLIC_EDGE_REQUIRED_OVERLAY_MARKERS.items():
        path = overlay_root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        if relative_path == ".codex-studio/runtime/PUBLIC_EDGE_PORTAL_OVERLAY_BUILD_INFO.generated.json":
            path.write_text(
                json.dumps(
                    {
                        "contractName": "chummer.public_edge_portal_overlay_publish.v1",
                        "sourceRoot": str(source_root.resolve()),
                        "status": "pass",
                        "activationStatus": "activated",
                        "verificationStatus": "pass",
                        "landingMarkerStatus": "pass",
                        "landingHasTurnAnchor": True,
                        "landingHasTurnAnchorRedirect": True,
                        "landingHasBuildPublicInstallHandoff": True,
                        "landingHasPlayPublicInstallHandoff": True,
                        "landingRetiredMarkersAbsent": True,
                        "landingBrowserRedirectStatus": "pass",
                        "landingBrowserRedirectEntryUrl": "http://127.0.0.1:5000/#turn-runsite-card",
                        "landingBrowserRedirectFinalUrl": "http://127.0.0.1:5000/mobile/player#turn-runsite-card",
                        "landingBrowserRedirectExpectedPath": "/mobile/player",
                        "landingBrowserRedirectExpectedHash": "#turn-runsite-card",
                        "landingBrowserRedirectExpectedQuery": "",
                        "landingBrowserRedirectFinalQuery": "",
                        "landingBrowserRedirectQueryDropped": True,
                        "landingBrowserRedirectPathMatches": True,
                        "landingBrowserRedirectHashMatches": True,
                        "landingMissingMarkerCount": 0,
                        "landingForbiddenMarkerCount": 0,
                        "sourceFingerprint": module.overlay_source_fingerprint(source_root),
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            continue
        path.write_text("\n".join(markers) + "\n", encoding="utf-8")
    build_info_path = (
        overlay_root
        / ".codex-studio/runtime/PUBLIC_EDGE_PORTAL_OVERLAY_BUILD_INFO.generated.json"
    )
    build_info_payload = json.loads(build_info_path.read_text(encoding="utf-8"))
    (overlay_root / "state").mkdir()
    fingerprint_module = module.load_overlay_fingerprint_module()
    fingerprint_module.ensure_required_compose_mountpoints(overlay_root)
    fingerprint_module.normalize_payload_modes(overlay_root)
    build_info_payload["payloadModeReceipt"] = (
        fingerprint_module.validate_payload_modes(overlay_root)
    )
    build_info_payload["stagedPayloadFingerprint"] = module.overlay_staged_payload_fingerprint(
        overlay_root
    )
    build_info_payload["fullDeploymentDigest"] = (
        fingerprint_module.full_deployment_digest(
            build_info_payload["sourceFingerprint"],
            build_info_payload["stagedPayloadFingerprint"],
        )
    )
    build_info_path.write_text(
        json.dumps(build_info_payload) + "\n",
        encoding="utf-8",
    )
    return overlay_root

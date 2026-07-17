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
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "check_public_edge_deploy_preflight.py"


def load_module():
    spec = importlib.util.spec_from_file_location("check_public_edge_deploy_preflight", SCRIPT)
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
    current_play_root = REPO_ROOT.parent / "chummer-play"
    for root_name, relative_path in module.expected_public_pwa_input_paths():
        source = (
            REPO_ROOT / relative_path
            if root_name == "run-services"
            else current_play_root / relative_path
        )
        target_root = source_root if root_name == "run-services" else play_root
        target = target_root / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    module.PUBLIC_PWA_PROOF_AUTHORITY_ROOT = source_root
    return source_root


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
            "111111 1 SNl 10:30:00 dotnet dotnet build /docker/chummercomplete/chummer6-ui/Chummer.Presentation/Chummer.Presentation.csproj",
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
            "3245065 3216459 SNl 00:02:36 dotnet dotnet build /docker/chummercomplete/chummer6-ui/Chummer.Presentation/Chummer.Presentation.csproj",
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


def test_current_source_marker_check_passes(tmp_path: Path) -> None:
    module = load_module()
    module.PUBLIC_EDGE_OPERATIONAL_MIRROR_ROOTS = {}
    runtime_proof = tmp_path / "HUB_LOCAL_RELEASE_PROOF.generated.json"
    proof_text = write_valid_runtime_proof(runtime_proof)
    release_receipt = tmp_path / "RELEASE_CHANNEL.generated.json"
    release_receipt_sha256 = write_release_channel_receipt_for_proof(
        release_receipt,
        proof_text,
    )

    receipt = module.verify(
        [],
        allow_stale_foreign_build_locks=False,
        source_root=REPO_ROOT,
        runtime_proof_bind_source=runtime_proof,
        release_channel_receipt=release_receipt,
        release_channel_receipt_sha256=release_receipt_sha256,
    )

    assert receipt["status"] == "pass"
    assert receipt["sourceRoot"] == str(REPO_ROOT)
    assert receipt["overlayRoot"] == ""
    assert receipt["sourceMarkerChecks"]
    assert receipt["publicPwaStaticProof"]["status"] == "pass"
    assert receipt["publicPwaStaticProof"]["checks"]["temporaryRegenerationPass"] is True
    assert receipt["publicPwaStaticProof"]["checks"]["siblingPlaySourceValidated"] is True
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
    assert 'grep -Fq \'const CACHE_VERSION = "v19";\'' in docker_markers
    assert "WORKDIR /proof" in docker_markers
    assert 'RUN ["/usr/local/bin/python3", "-I", "-S"' in docker_markers
    assert '"--receipt", "/proof/public-pwa-proof-authority.receipt.json"' in docker_markers
    assert module.PUBLIC_EDGE_DOCKER_RECEIPT_COPY in docker_markers
    docker_contract = docker_check["dockerBuildContract"]
    assert docker_contract["status"] == "pass"
    assert docker_contract["proofStageCount"] == 1
    assert docker_contract["pythonInvocationCount"] == 1
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
    tmp_path: Path,
    target_kind: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_module()
    source_root = copy_current_public_pwa_proof_fixture(module, tmp_path)
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
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_module()
    source_root = copy_current_public_pwa_proof_fixture(module, tmp_path)
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
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_module()
    source_root = copy_current_public_pwa_proof_fixture(module, tmp_path)
    replacement_root = tmp_path / "replacement" / "chummer.run-services"
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
    assert contract["buildStageCount"] == 1
    assert contract["toolFinalStageCount"] == 1
    assert contract["finalStageCount"] == 1
    assert contract["stageAliases"] == [
        "public-pwa-proof",
        "build",
        "install-linking-postgres-tool-final",
        "final",
    ]
    assert contract["stageDependencies"] == {
        "public-pwa-proof": [],
        "build": ["public-pwa-proof"],
        "install-linking-postgres-tool-final": ["build"],
        "final": ["build"],
    }
    assert contract["pythonInvocationCount"] == 1
    assert contract["checks"] == {
        "exactSyntaxDirective": True,
        "noLateParserDirectives": True,
        "noHeredoc": True,
        "validLogicalInstructions": True,
        "noGlobalInstructions": True,
        "exactProofStage": True,
        "exactStageHeaders": True,
        "singleProofStage": True,
        "proofStageNotDerived": True,
        "exactBuildStage": True,
        "exactToolFinalStage": True,
        "exactFinalStage": True,
        "exactStageSetAndOrder": True,
        "defaultStageIsFinal": True,
        "exactReceiptDependency": True,
        "receiptIsFirstBuildInstruction": True,
        "noOtherProofCopies": True,
        "exactToolPublishDependency": True,
        "exactFinalPublishDependency": True,
        "exactToolPayloadMode": True,
        "exactFinalPayloadMode": True,
        "exactCopyFromReferences": True,
        "exactRequiredNamedContextCopies": True,
        "buildDependsOnProof": True,
        "toolFinalDependsOnBuild": True,
        "finalDependsOnBuild": True,
        "allTargetsProofGated": True,
    }
    assert not contract["failures"]


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
        ("extra_independent_stage", "only public-pwa-proof, build"),
        ("detached_final", "final stage must depend transitively on build"),
        ("direct_final_from_base", "final stage must depend transitively on build"),
        ("removed_build_dependency", "exact proof receipt"),
        ("renamed_build_stage", "only public-pwa-proof, build"),
        ("reordered_stages", "only public-pwa-proof, build"),
        ("duplicate_final_stage", "exactly one named final stage"),
        ("receipt_copy_decoy", "exact proof receipt"),
        ("receipt_copy_as_run_continuation", "exact proof receipt"),
        ("unknown_external_copy_source", "allowed earlier stage or named context"),
        ("numeric_copy_source", "allowed earlier stage or named context"),
        ("wrong_stage_named_context", "allowed earlier stage or named context"),
        ("initializer_copy_moved_to_build", "exact required named-context COPY set"),
        ("receipt_moved_after_publish", "first build-stage instruction"),
        ("final_publish_edge_removed", "exact build publish artifact"),
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
    build_from = "FROM mcr.microsoft.com/dotnet/sdk:10.0 AS build\n"
    final_from = "FROM mcr.microsoft.com/dotnet/aspnet:10.0 AS final\n"
    final_build_copies = (
        "COPY --from=build /app/publish .\n",
        "COPY --from=build /src/chummer.run-services/.codex-design /app/.codex-design\n",
        "COPY --from=build /src/chummer-hub-registry/black-ledger /app/black-ledger\n",
    )
    tool_publish_copy = module.PUBLIC_EDGE_DOCKER_TOOL_PUBLISH_COPY + "\n"
    tool_payload_mode = module.PUBLIC_EDGE_DOCKER_TOOL_PAYLOAD_MODE_RUN + "\n"
    final_payload_mode = module.PUBLIC_EDGE_DOCKER_FINAL_PAYLOAD_MODE_RUN + "\n"
    assert original.startswith("# syntax=docker/dockerfile:1.4\n" + proof_from)
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
            "FROM mcr.microsoft.com/dotnet/aspnet:10.0 AS final\n",
            "FROM mcr.microsoft.com/dotnet/aspnet:10.0 AS final\n" + receipt_copy,
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
        "        design-product: /docker/chummercomplete/chummer-design\n"
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
            "RUN rm -rf /src/chummer.run-services/Chummer.Run.Api/bin /src/chummer.run-services/Chummer.Run.Api/obj\n",
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
    assert "RUN rm -rf /src/chummer.run-services/Chummer.Run.Api/bin /src/chummer.run-services/Chummer.Run.Api/obj" in dockerfile_check["missingMarkers"]
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
    module.PUBLIC_EDGE_RUNTIME_PROOF_BIND_SOURCE = runtime_proof

    exit_code = module.main(
        [
            "--release-channel-receipt",
            str(release_receipt),
            "--release-channel-receipt-sha256",
            release_receipt_sha256,
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
    source_root = write_complete_marker_source_tree(module, tmp_path / "source")
    proof_path = tmp_path / "published" / "HUB_LOCAL_RELEASE_PROOF.generated.json"
    proof_path.parent.mkdir(parents=True)

    valid_proof_text = write_valid_runtime_proof(proof_path)
    release_receipt = tmp_path / "published" / "RELEASE_CHANNEL.generated.json"
    release_receipt_sha256 = write_release_channel_receipt_for_proof(
        release_receipt,
        valid_proof_text,
    )

    receipt = module.verify(
        [],
        allow_stale_foreign_build_locks=False,
        source_root=source_root,
        runtime_proof_bind_source=proof_path,
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

    proof_path.chmod(0o664)
    receipt = module.verify(
        [],
        allow_stale_foreign_build_locks=False,
        source_root=source_root,
        runtime_proof_bind_source=proof_path,
    )

    assert receipt["status"] == "fail"
    assert receipt["runtimeProofBindSource"]["checks"]["exactMode0644"] is False
    assert any(
        finding["id"] == "public_edge_runtime_proof_bind_source_invalid"
        for finding in receipt["findings"]
    )

    proof_path.chmod(0o644)
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
        release_channel_receipt=release_receipt,
        release_channel_receipt_sha256=release_receipt_sha256,
    )

    assert receipt["status"] == "fail"
    assert receipt["checks"]["canonicalJson"] is True
    assert receipt["checks"]["semanticContract"] is False
    assert any("proof_routes" in failure for failure in receipt["failures"])


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
        release_channel_receipt=release_receipt,
        release_channel_receipt_sha256=release_receipt_sha256,
    )

    assert receipt["status"] == "fail"
    assert receipt["checks"]["strictJsonObject"] is True
    assert receipt["checks"]["canonicalJson"] is False
    assert receipt["checks"]["semanticContract"] is True
    assert receipt["sha256"] == hashlib.sha256(reversed_payload).hexdigest()


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
        release_channel_receipt=release_receipt,
        release_channel_receipt_sha256=release_receipt_sha256,
    )
    assert fabricated_receipt["status"] == "fail"
    assert fabricated_receipt["checks"]["semanticContract"] is True
    assert fabricated_receipt["checks"]["releaseChannelReceiptDigestMatches"] is True
    assert fabricated_receipt["checks"]["releaseChannelProjectionMatches"] is False


def test_full_preflight_cli_requires_independent_release_receipt_binding(
    tmp_path: Path,
) -> None:
    module = load_module()
    release_receipt = tmp_path / "RELEASE_CHANNEL.generated.json"
    release_receipt.write_text("{}\n", encoding="utf-8")

    with pytest.raises(SystemExit) as missing_receipt:
        module.main([])
    assert missing_receipt.value.code == 2

    with pytest.raises(SystemExit) as malformed_digest:
        module.main(
            [
                "--release-channel-receipt",
                str(release_receipt),
                "--release-channel-receipt-sha256",
                "A" * 64,
            ]
        )
    assert malformed_digest.value.code == 2


def test_runtime_proof_default_matches_canonical_compose_bind_source() -> None:
    module = load_module()
    compose_text = (REPO_ROOT / "docker-compose.public-edge.yml").read_text(
        encoding="utf-8"
    )

    assert module.PUBLIC_EDGE_RUNTIME_PROOF_BIND_SOURCE == Path(
        "/docker/chummercomplete/chummer.run-services/"
        ".codex-studio/published/HUB_LOCAL_RELEASE_PROOF.generated.json"
    )
    assert compose_text.count(str(module.PUBLIC_EDGE_RUNTIME_PROOF_BIND_SOURCE)) == 2
    assert not module.PUBLIC_EDGE_RUNTIME_PROOF_BIND_SOURCE.is_relative_to(
        module.RUN_SERVICES_ROOT
    ) or module.RUN_SERVICES_ROOT == Path("/docker/chummercomplete/chummer.run-services")


def test_alternate_source_still_checks_canonical_runtime_proof_bind_source(
    tmp_path: Path,
) -> None:
    module = load_module()
    alternate_source = tmp_path / "alternate-clean-source"
    checked_paths: list[Path] = []

    module.source_marker_findings = lambda _source: ([], [])
    module.execute_public_pwa_static_proof = lambda _source: {"status": "pass"}
    module.operational_mirror_findings = lambda _source: ([], [])

    def capture_runtime_proof(path: Path, **_kwargs: object) -> dict[str, object]:
        checked_paths.append(path)
        return {"status": "pass", "sourcePath": str(path)}

    module.runtime_proof_bind_source_check = capture_runtime_proof

    receipt = module.verify(
        [],
        allow_stale_foreign_build_locks=False,
        source_root=alternate_source,
    )

    assert receipt["status"] == "pass"
    assert checked_paths == [module.PUBLIC_EDGE_RUNTIME_PROOF_BIND_SOURCE]
    assert checked_paths[0] != alternate_source / ".codex-studio" / "published" / (
        "HUB_LOCAL_RELEASE_PROOF.generated.json"
    )


def test_main_can_skip_overlay_marker_check(tmp_path: Path) -> None:
    module = load_module()
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
    module.PUBLIC_EDGE_RUNTIME_PROOF_BIND_SOURCE = runtime_proof

    exit_code = module.main(
        [
            "--skip-overlay-marker-check",
            "--release-channel-receipt",
            str(release_receipt),
            "--release-channel-receipt-sha256",
            release_receipt_sha256,
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

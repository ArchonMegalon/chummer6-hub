from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import subprocess
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
COMPOSE_FILE_CANDIDATES = [
    REPO_ROOT / "docker-compose.public-edge.yml",
    REPO_ROOT / "docker-compose.yml",
    REPO_ROOT / "docker-compose.yaml",
]
DEFAULT_COMPOSE_FILE = next((item for item in COMPOSE_FILE_CANDIDATES if item.exists()), None)


def detect_compose_base():
    if shutil.which("docker"):
        try:
            subprocess.run(
                ["docker", "compose", "version"],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            return ["docker", "compose"]
        except Exception:
            pass
    if shutil.which("docker-compose"):
        return ["docker-compose"]
    return None


COMPOSE_BASE = detect_compose_base()


def compose_env():
    env = os.environ.copy()
    env.setdefault("TUNNEL_TOKEN", "dummy")
    if "COMPOSE_FILE" not in env and DEFAULT_COMPOSE_FILE is not None:
        env["COMPOSE_FILE"] = str(DEFAULT_COMPOSE_FILE.relative_to(REPO_ROOT))
    return env


def strip_yaml_scalar(value: str):
    stripped = value.strip()
    if stripped == "{}":
        return {}
    if len(stripped) >= 2 and stripped[0] == stripped[-1] and stripped[0] in {"'", '"'}:
        return stripped[1:-1]
    return stripped


def load_compose_subset(path: Path) -> dict[str, object]:
    services: dict[str, dict[str, object]] = {}
    in_services = False
    current_service: dict[str, object] | None = None
    current_section: str | None = None

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.rstrip()
        if not line.strip() or line.lstrip().startswith("#"):
            continue

        if not line.startswith(" "):
            in_services = line.strip() == "services:"
            current_service = None
            current_section = None
            continue

        if not in_services:
            continue

        if line.startswith("  ") and not line.startswith("    "):
            key, separator, rest = line.strip().partition(":")
            if separator and not rest.strip():
                current_service = {}
                services[key] = current_service
                current_section = None
            continue

        if current_service is None:
            continue

        if line.startswith("    ") and not line.startswith("      "):
            key, separator, rest = line.strip().partition(":")
            if not separator:
                continue
            if rest.strip():
                current_service[key] = strip_yaml_scalar(rest)
                current_section = None
                continue

            if key == "volumes":
                current_service[key] = []
            else:
                current_service[key] = {}
            current_section = key
            continue

        if current_section is None or not line.startswith("      "):
            continue

        item = line.strip()
        if current_section == "volumes" and item.startswith("- "):
            volumes = current_service.setdefault("volumes", [])
            if isinstance(volumes, list):
                volumes.append(strip_yaml_scalar(item[2:]))
        elif current_section == "environment" and ":" in item:
            environment = current_service.setdefault("environment", {})
            if isinstance(environment, dict):
                key, _, rest = item.partition(":")
                environment[key.strip()] = strip_yaml_scalar(rest)

    return {"services": services}


def load_compose_payload(path: Path) -> dict[str, object]:
    try:
        import yaml  # type: ignore[import-not-found]

        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
        return loaded if isinstance(loaded, dict) else {}
    except ModuleNotFoundError:
        return load_compose_subset(path)


def run_compose(*args: str) -> subprocess.CompletedProcess[str]:
    if COMPOSE_BASE is not None:
        result = subprocess.run(
            [*COMPOSE_BASE, *args],
            cwd=REPO_ROOT,
            env=compose_env(),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        if result.returncode == 0:
            return result

    compose_file = compose_env().get("COMPOSE_FILE")
    if not compose_file:
        return subprocess.CompletedProcess(
            args=["compose-fallback", *args],
            returncode=1,
            stdout="",
            stderr="COMPOSE_FILE is not configured and no docker compose binary is available",
        )

    compose_path = REPO_ROOT / compose_file
    try:
        payload = load_compose_payload(compose_path)
    except Exception as exc:
        return subprocess.CompletedProcess(
            args=["compose-fallback", *args],
            returncode=1,
            stdout="",
            stderr=f"failed to read compose file {compose_path}: {exc}",
        )

    services = payload.get("services")
    if not isinstance(services, dict):
        return subprocess.CompletedProcess(
            args=["compose-fallback", *args],
            returncode=1,
            stdout="",
            stderr=f"compose file {compose_path} does not define a services mapping",
        )

    if args == ("config", "-q"):
        return subprocess.CompletedProcess(
            args=["compose-fallback", *args],
            returncode=0,
            stdout="",
            stderr="",
        )

    if args == ("config", "--services"):
        service_lines = "\n".join(str(name) for name in services.keys())
        if service_lines:
            service_lines += "\n"
        return subprocess.CompletedProcess(
            args=["compose-fallback", *args],
            returncode=0,
            stdout=service_lines,
            stderr="",
        )

    return subprocess.CompletedProcess(
        args=["compose-fallback", *args],
        returncode=2,
        stdout="",
        stderr=f"compose fallback does not support arguments: {args!r}",
    )


class StackConfigSmokeTests(unittest.TestCase):
    def test_compose_config_validates(self):
        cp = run_compose("config", "-q")
        self.assertEqual(cp.returncode, 0, msg=cp.stderr or cp.stdout)

    def test_compose_defines_services(self):
        cp = run_compose("config", "--services")
        self.assertEqual(cp.returncode, 0, msg=cp.stderr or cp.stdout)
        services = {line.strip() for line in cp.stdout.splitlines() if line.strip()}
        self.assertTrue(services, "docker compose config --services returned no services")
        expected_services = {"overseerr_v2", "seerr_v2", "chummer-run-identity", "chummer-portal"}
        self.assertTrue(
            bool(expected_services & services),
            "expected one of the known stack services to be present",
        )

    def test_public_edge_services_restart_unless_stopped(self):
        public_edge_path = REPO_ROOT / "docker-compose.public-edge.yml"
        if not public_edge_path.exists():
            self.skipTest("docker-compose.public-edge.yml is not present for this repository slice")

        payload = load_compose_payload(public_edge_path)
        services = payload.get("services") or {}

        for service_name in ("chummer-run-identity", "chummer-portal"):
            service = services.get(service_name) or {}
            self.assertEqual(
                service.get("restart"),
                "unless-stopped",
                msg=f"{service_name} should restart automatically after host or docker daemon restarts",
            )

    def test_public_edge_promotes_windows_installer_on_main_shelf(self):
        public_edge_path = REPO_ROOT / "docker-compose.public-edge.yml"
        if not public_edge_path.exists():
            self.skipTest("docker-compose.public-edge.yml is not present for this repository slice")

        payload = load_compose_payload(public_edge_path)
        services = payload.get("services") or {}
        portal = services.get("chummer-portal") or {}
        environment = portal.get("environment") or {}

        self.assertEqual(
            environment.get("CHUMMER_PUBLIC_SKIP_STARTUP_SMOKE_FILTER"),
            "${CHUMMER_PUBLIC_SKIP_STARTUP_SMOKE_FILTER:-true}",
            msg="preview public edge should keep the rolling Windows/Linux nightly shelf visible",
        )
        self.assertEqual(
            environment.get("CHUMMER_PUBLIC_CANON_ROOT"),
            "/app",
            msg="public edge should read baked canonical product truth instead of a drift-prone repo mirror mount",
        )

        volumes = portal.get("volumes") or []
        self.assertNotIn(
            "./:/repo:ro",
            volumes,
            msg="public edge should not keep a live repo mount once canonical product truth is baked into /app",
        )

    def test_public_edge_dockerfile_bakes_design_canon_into_app_product_root(self):
        dockerfile_path = REPO_ROOT / "Chummer.Run.Api" / "Dockerfile"
        if not dockerfile_path.exists():
            self.skipTest("Chummer.Run.Api/Dockerfile is not present for this repository slice")

        dockerfile_text = dockerfile_path.read_text(encoding="utf-8")

        self.assertIn(
            "COPY --from=build /src/chummercomplete/chummer.run-services/.codex-design /app/.codex-design",
            dockerfile_text,
        )
        self.assertIn(
            "COPY chummercomplete/chummer-design/products/chummer/ /app/.codex-design/product/",
            dockerfile_text,
            msg="public edge image should overlay the canonical chummer-design product onto the app product root",
        )

    def test_release_upload_bootstrap_stamps_receipts_with_artifact_identity(self):
        bootstrap_path = (
            REPO_ROOT
            / "Chummer.Run.Api"
            / "wwwroot"
            / "artifacts"
            / "mac-codex-release-pipeline"
            / "bootstrap.sh"
        )
        if not bootstrap_path.exists():
            self.skipTest("mac release-upload bootstrap template is not present for this repository slice")

        bootstrap_text = bootstrap_path.read_text(encoding="utf-8")

        self.assertIn("stamp_startup_smoke_receipt_artifact_identity()", bootstrap_text)
        self.assertIn('payload["artifactFileName"] = artifact_name', bootstrap_text)
        self.assertIn('payload["artifactRelativePath"] = artifact_relative_path', bootstrap_text)
        self.assertIn('payload["artifactSha256"] = artifact_sha', bootstrap_text)
        self.assertIn('payload["artifactDigest"] = f"sha256:{artifact_sha}"', bootstrap_text)
        self.assertIn('payload["artifactDigestSource"] = "artifact_path"', bootstrap_text)
        self.assertIn('payload["artifactId"] = f"{head}-{rid}-{artifact_kind}"', bootstrap_text)
        self.assertIn("stamp_startup_smoke_receipt_artifact_identity \\", bootstrap_text)
        self.assertIn("sync_startup_smoke_receipts_for_local_verifier()", bootstrap_text)
        self.assertIn('sync_startup_smoke_receipts_for_local_verifier "$startup_smoke_dir" "$dist_dir"', bootstrap_text)
        self.assertIn("write_manifest_validation_audit_bundle()", bootstrap_text)
        self.assertIn("manifest-validation-audit.tar.gz", bootstrap_text)
        self.assertIn("If another Codex or operator is assisting, give them this directory or tarball first.", bootstrap_text)
        self.assertIn("write_manifest_validation_audit_bundle \\", bootstrap_text)
        self.assertIn("Audit bundle: ${dist_dir}/manifest-validation-audit", bootstrap_text)
        self.assertIn('python3 - "$verifier_path" "$manifest_path" "$compatibility_manifest_path" <<\'PY\'', bootstrap_text)
        self.assertIn('def derive_verifier_owned_value(name: str, current_value):', bootstrap_text)
        self.assertIn('materializer_path = verifier_path.with_name("materialize_public_release_channel.py")', bootstrap_text)
        self.assertIn("def required_heads_and_platforms(payload: dict)", bootstrap_text)
        self.assertIn('materializer.desktop_tuple_coverage(', bootstrap_text)
        self.assertIn('materializer.desktop_surface_refs(', bootstrap_text)
        self.assertIn('"expected_desktop_surface_ref_rows"', bootstrap_text)
        self.assertIn('"expected_artifact_publication_binding_rows"', bootstrap_text)
        self.assertIn('"expected_registry_boundary_coverage"', bootstrap_text)
        self.assertIn('sync_startup_smoke_receipts_for_local_verifier "$startup_smoke_dir" "$audit_dir"', bootstrap_text)
        self.assertIn("startup-smoke/startup-smoke-*.receipt.json copies in verifier-compatible layout", bootstrap_text)

    def test_mac_bootstrap_captures_post_publish_live_manifest_projection(self):
        bootstrap_path = REPO_ROOT.parent / "chummer-design" / "products" / "chummer" / "maintenance" / "bootstrap-mac-codex-release.sh"
        bootstrap_text = bootstrap_path.read_text(encoding="utf-8")

        self.assertIn("capture_post_publish_manifest_projection()", bootstrap_text)
        self.assertIn('local projection_dir="$dist_dir/post-publish-manifest"', bootstrap_text)
        self.assertIn('curl --fail --silent --show-error --location "$verify_url" -o "$live_manifest"', bootstrap_text)
        self.assertIn("Local canonical manifest reflects the just-built bundle fragment.", bootstrap_text)
        self.assertIn('log "capturing post-publish live manifest projection"', bootstrap_text)
        self.assertIn('capture_post_publish_manifest_projection "$verify_url" "$dist_dir"', bootstrap_text)

    def test_mac_bootstrap_writes_preflight_capacity_abort_receipt(self):
        bootstrap_paths = [
            REPO_ROOT.parent / "chummer-design" / "products" / "chummer" / "maintenance" / "bootstrap-mac-codex-release.sh",
            REPO_ROOT / "Chummer.Run.Api" / "wwwroot" / "artifacts" / "mac-codex-release-pipeline" / "bootstrap.sh",
        ]

        for bootstrap_path in bootstrap_paths:
            bootstrap_text = bootstrap_path.read_text(encoding="utf-8")
            self.assertIn("write_preflight_capacity_abort_receipt()", bootstrap_text)
            self.assertIn('"abortClass": "preflight_capacity_abort"', bootstrap_text)
            self.assertIn('local evidence_dir="$evidence_root/release-evidence"', bootstrap_text)
            self.assertIn('local receipt_path="$evidence_dir/preflight-capacity-abort.json"', bootstrap_text)
            self.assertIn("This run stopped before clone/build/packaging/startup-smoke/upload and does not count as release evidence.", bootstrap_text)
            self.assertIn("practical headroom target", bootstrap_text)

    def test_mac_bootstrap_captures_post_publish_live_manifest_projection(self):
        bootstrap_path = REPO_ROOT.parent / "chummer-design" / "products" / "chummer" / "maintenance" / "bootstrap-mac-codex-release.sh"
        bootstrap_text = bootstrap_path.read_text(encoding="utf-8")

        self.assertIn("capture_post_publish_manifest_projection()", bootstrap_text)
        self.assertIn('local projection_dir="$dist_dir/post-publish-manifest"', bootstrap_text)
        self.assertIn('curl --fail --silent --show-error --location "$verify_url" -o "$live_manifest"', bootstrap_text)
        self.assertIn("Local canonical manifest reflects the just-built bundle fragment.", bootstrap_text)
        self.assertIn('log "capturing post-publish live manifest projection"', bootstrap_text)
        self.assertIn('capture_post_publish_manifest_projection "$verify_url" "$dist_dir"', bootstrap_text)

    def test_publish_download_bundle_recanonicalizes_release_channel_registries(self):
        script_path = REPO_ROOT / "scripts" / "publish-download-bundle.sh"
        script_text = script_path.read_text(encoding="utf-8")

        self.assertIn("bundle_manifest_matches_files()", script_text)
        self.assertIn("Set RELEASE_VERSION and RELEASE_PUBLISHED_AT explicitly for this republish.", script_text)
        self.assertIn('CHUMMER_EXTERNAL_PROOF_BASE_URL="${CHUMMER_EXTERNAL_PROOF_BASE_URL:-https://chummer.run}"', script_text)
        self.assertIn('PUBLIC_SKIP_STARTUP_SMOKE_FILTER="${CHUMMER_PUBLIC_SKIP_STARTUP_SMOKE_FILTER:-}"', script_text)
        self.assertIn('if [[ "${RELEASE_CHANNEL:-preview}" =~ ^[Pp][Rr][Ee][Vv][Ii][Ee][Ww]$ ]]; then', script_text)
        self.assertIn('chummer-blazor-desktop-*-installer.dmg', script_text)
        self.assertIn('bash "$SCRIPT_DIR/generate-releases-manifest.sh"', script_text)
        self.assertIn('bash "$SCRIPT_DIR/verify-releases-manifest.sh" "$DEPLOY_DIR"', script_text)

    def test_latest_nightly_publisher_requires_release_handoff_and_proves_deployed_version_match(self):
        script_path = REPO_ROOT.parent / "chummer-presentation" / "scripts" / "publish-latest-nightly-to-downloads.sh"
        script_text = script_path.read_text(encoding="utf-8")

        self.assertIn('PUBLIC_RELEASE_CHANNEL="${CHUMMER_PUBLIC_DEFAULT_RELEASE_CHANNEL:-preview}"', script_text)
        self.assertIn('ALLOW_STABLE_CHANNEL_FROM_NIGHTLY_PUBLISH="${CHUMMER_ALLOW_STABLE_CHANNEL_FROM_NIGHTLY_PUBLISH:-0}"', script_text)
        self.assertIn("Nightly publisher is the preview handoff lane.", script_text)
        self.assertIn("CHUMMER_ALLOW_STABLE_CHANNEL_FROM_NIGHTLY_PUBLISH=true", script_text)
        self.assertIn('release_channel_manifest="$stage_dir/RELEASE_CHANNEL.generated.json"', script_text)
        self.assertIn('release_channel="$(python3 - "$release_channel_manifest" <<\'PY\'', script_text)
        self.assertIn('if [[ "$release_channel" != "preview" ]]; then', script_text)
        self.assertIn('refresh_release_build_handoff "$latest_stage"', script_text)
        self.assertIn('RELEASE_BUILD_HANDOFF.generated.json', script_text)
        self.assertIn('Nightly stage is missing RELEASE_BUILD_HANDOFF.generated.json', script_text)
        self.assertIn('expected_version="$(', script_text)
        self.assertIn('Nightly stage manifest is missing a non-empty version.', script_text)
        self.assertIn('python3 - "$DEPLOY_DIR/RELEASE_CHANNEL.generated.json" "$expected_version"', script_text)
        self.assertIn("Published downloads shelf version mismatch", script_text)
        self.assertIn("Verified published downloads shelf version:", script_text)

    def test_mac_bootstrap_remote_ui_publish_path_uses_hardened_bundle_publisher(self):
        bootstrap_path = REPO_ROOT.parent / "chummer-design" / "products" / "chummer" / "maintenance" / "bootstrap-mac-codex-release.sh"
        bootstrap_text = bootstrap_path.read_text(encoding="utf-8")
        remote_ui_publish_path = REPO_ROOT.parent / "chummer6-ui" / "scripts" / "publish-download-bundle.sh"
        publish_text = remote_ui_publish_path.read_text(encoding="utf-8")

        self.assertIn('local remote_ui_repo="${CHUMMER_REMOTE_UI_REPO_DIR:-/docker/chummercomplete/chummer6-ui}"', bootstrap_text)
        self.assertIn("bash scripts/publish-download-bundle.sh", bootstrap_text)
        self.assertIn("bundle_manifest_matches_files()", publish_text)
        self.assertIn('CHUMMER_EXTERNAL_PROOF_BASE_URL="${CHUMMER_EXTERNAL_PROOF_BASE_URL:-https://chummer.run}"', publish_text)
        self.assertIn('PUBLIC_SKIP_STARTUP_SMOKE_FILTER="${CHUMMER_PUBLIC_SKIP_STARTUP_SMOKE_FILTER:-}"', publish_text)
        self.assertIn('CHUMMER_PUBLIC_SKIP_STARTUP_SMOKE_FILTER="${CHUMMER_PUBLIC_SKIP_STARTUP_SMOKE_FILTER:-$PUBLIC_SKIP_STARTUP_SMOKE_FILTER}"', publish_text)
        self.assertIn('chummer-blazor-desktop-*-installer.dmg', publish_text)
        self.assertIn("Set RELEASE_VERSION and RELEASE_PUBLISHED_AT explicitly for this republish.", publish_text)
        self.assertIn('CHUMMER_PUBLIC_EDGE_DOWNLOADS_MIRROR_DIRS', publish_text)
        self.assertIn('$REPO_ROOT/../chummer.run-services/Chummer.Portal/downloads', publish_text)
        self.assertIn('$REPO_ROOT/../chummer6-hub/Chummer.Portal/downloads', publish_text)
        self.assertIn('sync_live_downloads_mirror_dir()', publish_text)
        self.assertIn('bash "$SCRIPT_DIR/verify-releases-manifest.sh" "$target_dir/RELEASE_CHANNEL.generated.json" >/dev/null', publish_text)
        self.assertIn('bash "$SCRIPT_DIR/generate-releases-manifest.sh"', publish_text)
        self.assertIn('bash "$SCRIPT_DIR/verify-releases-manifest.sh" "$DEPLOY_DIR"', publish_text)

    def test_shared_http_release_uploader_avoids_bash4_only_array_builtins(self):
        uploader_path = REPO_ROOT.parent / "chummer-presentation" / "scripts" / "publish-download-bundle-http.sh"
        if not uploader_path.exists():
            self.skipTest("shared HTTP release uploader is not present for this repository slice")

        uploader_text = uploader_path.read_text(encoding="utf-8")

        self.assertIn('MANIFEST_PATH="${CHUMMER_RELEASE_UPLOAD_MANIFEST_PATH:-$BUNDLE_DIR/releases.json}"', uploader_text)
        self.assertNotIn("mapfile -t", uploader_text)
        self.assertNotIn("readarray -t", uploader_text)

    def test_verify_release_manifest_scripts_guard_empty_verify_args_for_macos_bash(self):
        script_paths = [
            REPO_ROOT / "scripts" / "verify-releases-manifest.sh",
            REPO_ROOT.parent / "chummer-presentation" / "scripts" / "verify-releases-manifest.sh",
        ]

        for script_path in script_paths:
            self.assertTrue(script_path.exists(), msg=f"missing expected manifest verifier: {script_path}")
            script_text = script_path.read_text(encoding="utf-8")
            self.assertIn('if [[ "${#VERIFY_ARGS[@]}" -gt 0 ]]; then', script_text)
            self.assertIn('python3 "$REGISTRY_ROOT/scripts/verify_public_release_channel.py" "$TARGET"', script_text)

    def test_release_publish_scripts_keep_macos_artifact_gate_behavior(self):
        run_services_gate_paths = {
            REPO_ROOT / "scripts" / "generate-releases-manifest.sh",
            REPO_ROOT / "scripts" / "publish-download-bundle.sh",
        }
        script_paths = [
            REPO_ROOT / "scripts" / "generate-releases-manifest.sh",
            REPO_ROOT / "scripts" / "publish-download-bundle.sh",
            REPO_ROOT / "scripts" / "publish-download-bundle-s3.sh",
            REPO_ROOT.parent / "chummer-presentation" / "scripts" / "generate-releases-manifest.sh",
        ]

        for script_path in script_paths:
            if not script_path.exists():
                self.skipTest(f"release publish script is not present for this repository slice: {script_path}")

            script_text = script_path.read_text(encoding="utf-8")
            if script_path in run_services_gate_paths:
                self.assertIn("CHUMMER_MACOS_PUBLIC_SHELF_ENABLED", script_text)
                self.assertIn("is_public_artifact()", script_text)

    def test_s3_release_publisher_uploads_windows_bootstrap_payload_sidecar(self):
        script_path = REPO_ROOT / "scripts" / "publish-download-bundle-s3.sh"
        script_text = script_path.read_text(encoding="utf-8")

        self.assertIn("-name 'chummer-*-win-*-payload.zip'", script_text)
        self.assertIn("-name 'chummer-*-win-*-payload.zip.json'", script_text)

    def test_shared_release_publish_scripts_support_public_startup_smoke_override_and_canonical_release_proof_origin(self):
        generate_paths = [
            REPO_ROOT.parent / "chummer-presentation" / "scripts" / "generate-releases-manifest.sh",
            REPO_ROOT.parent / "chummer6-ui" / "scripts" / "generate-releases-manifest.sh",
        ]
        publish_paths = [
            REPO_ROOT.parent / "chummer-presentation" / "scripts" / "publish-download-bundle.sh",
            REPO_ROOT.parent / "chummer6-ui" / "scripts" / "publish-download-bundle.sh",
        ]

        for script_path in generate_paths:
            if not script_path.exists():
                self.skipTest(f"missing shared manifest materializer: {script_path}")
            script_text = script_path.read_text(encoding="utf-8")
            self.assertIn("CHUMMER_PUBLIC_SKIP_STARTUP_SMOKE_FILTER", script_text)
            self.assertIn("--skip-startup-smoke-filter", script_text)
            self.assertIn("CHUMMER_EXTERNAL_PROOF_BASE_URL", script_text)
            self.assertIn('sanitized["baseUrl"] = canonical_base_url', script_text)
            self.assertIn('sanitized["base_url"] = canonical_base_url', script_text)

        for script_path in publish_paths:
            if not script_path.exists():
                self.skipTest(f"missing shared bundle publisher: {script_path}")
            script_text = script_path.read_text(encoding="utf-8")
            self.assertIn('PUBLIC_SKIP_STARTUP_SMOKE_FILTER="${CHUMMER_PUBLIC_SKIP_STARTUP_SMOKE_FILTER:-}"', script_text)
            self.assertIn('CHUMMER_EXTERNAL_PROOF_BASE_URL="${CHUMMER_EXTERNAL_PROOF_BASE_URL:-https://chummer.run}"', script_text)

    def test_run_services_manifest_generator_recanonicalizes_verifier_owned_release_channel_surfaces(self):
        script_path = REPO_ROOT / "scripts" / "generate-releases-manifest.sh"
        script_text = script_path.read_text(encoding="utf-8")

        self.assertIn('def derive_verifier_owned_value(name: str, current_value):', script_text)
        self.assertIn('materializer_path = verifier_path.with_name("materialize_public_release_channel.py")', script_text)
        self.assertIn("def fallback_tuple_coverage(local_payload: dict)", script_text)
        self.assertIn('materializer.desktop_surface_refs(', script_text)
        self.assertIn('"expected_external_proof_request_rows"', script_text)
        self.assertIn('"expected_desktop_route_truth_rows"', script_text)
        self.assertIn('"expected_install_aware_artifact_registry_rows"', script_text)
        self.assertIn('"expected_desktop_surface_ref_rows"', script_text)
        self.assertIn('"expected_artifact_identity_registry_rows"', script_text)
        self.assertIn('"expected_artifact_publication_binding_rows"', script_text)
        self.assertIn('"expected_registry_boundary_coverage"', script_text)
        self.assertIn("def assert_desktop_surface_ref_consistency(local_payload: dict)", script_text)
        self.assertIn("desktopSurfaceRefs must not surface proof_required tuples", script_text)
        self.assertIn("assert_desktop_surface_ref_consistency(payload)", script_text)

    def test_run_services_public_bundle_materializer_recanonicalizes_verifier_owned_release_channel_surfaces(self):
        script_path = REPO_ROOT / "scripts" / "materialize-public-downloads-bundle.sh"
        script_text = script_path.read_text(encoding="utf-8")

        self.assertIn('def derive_verifier_owned_value(name: str, current_value):', script_text)
        self.assertIn('materializer_path = verifier_path.with_name("materialize_public_release_channel.py")', script_text)
        self.assertIn("def fallback_tuple_coverage(local_payload: dict)", script_text)
        self.assertIn('materializer.desktop_surface_refs(', script_text)
        self.assertIn('"expected_external_proof_request_rows"', script_text)
        self.assertIn('"expected_desktop_route_truth_rows"', script_text)
        self.assertIn('"expected_install_aware_artifact_registry_rows"', script_text)
        self.assertIn('"expected_desktop_surface_ref_rows"', script_text)
        self.assertIn('"expected_artifact_identity_registry_rows"', script_text)
        self.assertIn('"expected_artifact_publication_binding_rows"', script_text)
        self.assertIn('"expected_registry_boundary_coverage"', script_text)
        self.assertIn("def assert_desktop_surface_ref_consistency(local_payload: dict)", script_text)
        self.assertIn("desktopSurfaceRefs must not surface proof_required tuples", script_text)
        self.assertIn("assert_desktop_surface_ref_consistency(payload)", script_text)

    def test_run_services_public_bundle_materializer_prefers_canonical_release_channel_source(self):
        script_path = REPO_ROOT / "scripts" / "materialize-public-downloads-bundle.sh"
        script_text = script_path.read_text(encoding="utf-8")

        self.assertIn('resolve_public_release_channel_source()', script_text)
        self.assertIn('"$REGISTRY_ROOT/.codex-studio/published/RELEASE_CHANNEL.generated.json"', script_text)
        self.assertIn('PUBLIC_RELEASE_CHANNEL_SOURCE_PATH="$(resolve_public_release_channel_source)"', script_text)
        self.assertIn('detect_auto_disabled_artifact_ids "$combined_files_root" "$PUBLIC_RELEASE_CHANNEL_SOURCE_PATH"', script_text)
        self.assertIn('python3 - "$PUBLIC_RELEASE_CHANNEL_SOURCE_PATH" <<\'PY\'', script_text)

    def test_run_services_release_upload_scripts_avoid_bash4_array_builtins(self):
        script_paths = [
            REPO_ROOT / "scripts" / "generate-releases-manifest.sh",
            REPO_ROOT / "scripts" / "publish-download-bundle.sh",
        ]

        for script_path in script_paths:
            self.assertTrue(script_path.exists(), msg=f"missing expected release script: {script_path}")
            script_text = script_path.read_text(encoding="utf-8")
            self.assertNotIn("mapfile -t", script_text, msg=f"bash 4-only mapfile found in {script_path}")
            self.assertNotIn("readarray -t", script_text, msg=f"bash 4-only readarray found in {script_path}")

    def test_http_release_upload_script_recanonicalizes_bundle_manifests_before_upload(self):
        script_path = REPO_ROOT / "scripts" / "publish-download-bundle-http.sh"
        script_text = script_path.read_text(encoding="utf-8")

        self.assertIn('REGISTRY_ROOT="${CHUMMER_HUB_REGISTRY_ROOT:-/docker/chummercomplete/chummer-hub-registry}"', script_text)
        self.assertIn('canonicalize_release_channel_registries() {', script_text)
        self.assertIn('canonicalize_bundle_release_channel_registries()', script_text)
        self.assertIn('payload["installAwareArtifactRegistry"] = derive_verifier_owned_value(', script_text)
        self.assertEqual(script_text.count('canonicalize_release_channel_registries() {'), 1)
        self.assertEqual(script_text.count('canonicalize_bundle_release_channel_registries() {'), 1)
        self.assertIn('canonicalize_bundle_release_channel_registries\n\nupload_files=()', script_text)

    def test_http_release_upload_verifies_manifest_artifacts_not_hardcoded_platforms(self):
        script_path = REPO_ROOT / "scripts" / "publish-download-bundle-http.sh"
        script_text = script_path.read_text(encoding="utf-8")

        function_body = script_text.split("build_default_verify_routes() {", 1)[1].split("\n}\n", 1)[0]
        self.assertIn('f"{base_url}/status"', function_body)
        self.assertIn('f"{base_url}/help"', function_body)
        self.assertIn('f"{base_url}/contact"', function_body)
        self.assertIn('f"{base_url}/login?next=%2F"', function_body)
        self.assertIn('f"{base_url}/account/billing"', function_body)
        self.assertIn('f"{base_url}/participate"', function_body)
        self.assertIn('f"{base_url}/partizipate"', function_body)
        self.assertIn('f"{base_url}/roadmap"', function_body)
        self.assertIn('payload.get("downloads") or payload.get("artifacts")', function_body)
        self.assertIn('if not isinstance(row, dict) or row.get("disabled") is True:', function_body)
        self.assertIn('routes.append(f"{base_url}/downloads/install/{artifact_id}")', function_body)
        self.assertIn('print("\\n".join(dict.fromkeys(routes)))', function_body)
        self.assertNotIn("avalonia-win-x64-installer", function_body)
        self.assertNotIn("chummer-avalonia-win-x64-installer.exe", function_body)

    def test_mac_bootstrap_verifies_local_canonical_manifest_before_live_publish_check(self):
        bootstrap_path = REPO_ROOT.parent / "chummer-design" / "products" / "chummer" / "maintenance" / "bootstrap-mac-codex-release.sh"
        bootstrap_text = bootstrap_path.read_text(encoding="utf-8")

        self.assertIn('log "verifying local bundle manifest"', bootstrap_text)
        self.assertIn('bash scripts/verify-releases-manifest.sh "$dist_dir/releases.json"', bootstrap_text)
        self.assertIn('log "verifying local canonical release manifest"', bootstrap_text)
        self.assertIn('bash scripts/verify-releases-manifest.sh "$dist_dir/RELEASE_CHANNEL.generated.json"', bootstrap_text)

    def test_http_release_upload_script_recanonicalizes_bundle_manifests_before_upload(self):
        script_path = REPO_ROOT / "scripts" / "publish-download-bundle-http.sh"
        script_text = script_path.read_text(encoding="utf-8")

        self.assertIn('REGISTRY_ROOT="${CHUMMER_HUB_REGISTRY_ROOT:-/docker/chummercomplete/chummer-hub-registry}"', script_text)
        self.assertIn('canonicalize_release_channel_registries() {', script_text)
        self.assertIn('canonicalize_bundle_release_channel_registries()', script_text)
        self.assertIn('payload["installAwareArtifactRegistry"] = derive_verifier_owned_value(', script_text)
        self.assertEqual(script_text.count('canonicalize_release_channel_registries() {'), 1)
        self.assertEqual(script_text.count('canonicalize_bundle_release_channel_registries() {'), 1)
        self.assertIn('canonicalize_bundle_release_channel_registries\n\nupload_files=()', script_text)

    def test_mac_bootstrap_verifies_local_canonical_manifest_before_live_publish_check(self):
        bootstrap_path = REPO_ROOT.parent / "chummer-design" / "products" / "chummer" / "maintenance" / "bootstrap-mac-codex-release.sh"
        bootstrap_text = bootstrap_path.read_text(encoding="utf-8")

        self.assertIn('log "verifying local bundle manifest"', bootstrap_text)
        self.assertIn('bash scripts/verify-releases-manifest.sh "$dist_dir/releases.json"', bootstrap_text)
        self.assertIn('log "verifying local canonical release manifest"', bootstrap_text)
        self.assertIn('bash scripts/verify-releases-manifest.sh "$dist_dir/RELEASE_CHANNEL.generated.json"', bootstrap_text)

    def test_release_upload_bootstrap_can_repair_missing_status_and_verify_dummy_bundle(self):
        bootstrap_path = (
            REPO_ROOT
            / "Chummer.Run.Api"
            / "wwwroot"
            / "artifacts"
            / "mac-codex-release-pipeline"
            / "bootstrap.sh"
        )
        if not bootstrap_path.exists():
            self.skipTest("mac release-upload bootstrap template is not present for this repository slice")

        registry_root = REPO_ROOT.parent / "chummer-hub-registry"
        materializer = registry_root / "scripts" / "materialize_public_release_channel.py"
        verifier = registry_root / "scripts" / "verify_public_release_channel.py"
        if not materializer.exists() or not verifier.exists():
            self.skipTest("registry materializer/verifier scripts are not present for this repository slice")
        known_good_release_channel = REPO_ROOT / "Chummer.Portal" / "downloads" / "RELEASE_CHANNEL.generated.json"
        if not known_good_release_channel.exists():
            self.skipTest("known-good release-channel fixture is not present for this repository slice")

        with tempfile.TemporaryDirectory(prefix="chummer-bootstrap-e2e-") as temp_root:
            temp_path = Path(temp_root)
            files_dir = temp_path / "files"
            startup_smoke_dir = temp_path / "startup-smoke"
            files_dir.mkdir()
            startup_smoke_dir.mkdir()
            published_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

            artifact_path = files_dir / "chummer-avalonia-osx-arm64-installer.dmg"
            artifact_path.write_bytes(b"dummy mac installer payload\n")

            receipt_path = startup_smoke_dir / "startup-smoke-avalonia-osx-arm64.receipt.json"
            receipt_path.write_text(
                json.dumps(
                    {
                        "headId": "avalonia",
                        "version": "dummy-preview",
                        "releaseVersion": "dummy-preview",
                        "channelId": "preview",
                        "platform": "macos",
                        "arch": "arm64",
                        "rid": "osx-arm64",
                        "readyCheckpoint": "pre_ui_event_loop",
                        "hostClass": "macos-host",
                        "processPath": "/tmp/Chummer.Avalonia",
                        "framework": ".NET 10.0.0",
                        "operatingSystem": "macOS Sonoma",
                        "recordedAtUtc": published_at,
                        "startedAtUtc": published_at,
                        "completedAtUtc": published_at,
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            release_fixture = json.loads(known_good_release_channel.read_text(encoding="utf-8"))
            proof_path = temp_path / "release-proof.json"

            source_bootstrap_script = (
                "source <(python3 - <<'PY'\n"
                "from pathlib import Path\n"
                f"path = Path({str(bootstrap_path)!r})\n"
                "lines = path.read_text(encoding='utf-8').splitlines()\n"
                "if lines and lines[-1].strip() == 'main \"$@\"':\n"
                "    lines = lines[:-1]\n"
                "print('\\n'.join(lines))\n"
                "PY\n"
                ")\n"
            )
            stamp_command = (
                "set -euo pipefail\n"
                + source_bootstrap_script
                + f"stamp_startup_smoke_receipt_artifact_identity {shlex.quote(str(receipt_path))} {shlex.quote(str(artifact_path))} avalonia osx-arm64\n"
            )
            stamp = subprocess.run(
                ["bash", "-lc", stamp_command],
                cwd=REPO_ROOT,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            self.assertEqual(stamp.returncode, 0, msg=stamp.stderr or stamp.stdout)

            manifest_path = temp_path / "RELEASE_CHANNEL.generated.json"
            compat_path = temp_path / "releases.json"
            release_fixture["releaseProof"]["status"] = "pass"
            release_fixture["releaseProof"]["generatedAt"] = published_at
            release_fixture["releaseProof"]["generated_at"] = published_at
            ui_gate = release_fixture["releaseProof"].get("uiLocalizationReleaseGate") or {}
            if isinstance(ui_gate, dict):
                ui_gate["generatedAt"] = published_at
                ui_gate["generated_at"] = published_at
            with proof_path.open("w", encoding="utf-8") as handle:
                json.dump(release_fixture["releaseProof"], handle, indent=2)
                handle.write("\n")

            materialize = subprocess.run(
                [
                    "python3",
                    str(materializer),
                    "--downloads-dir",
                    str(files_dir),
                    "--startup-smoke-dir",
                    str(startup_smoke_dir),
                    "--channel",
                    "preview",
                    "--version",
                    "dummy-preview",
                    "--published-at",
                    published_at,
                    "--proof",
                    str(proof_path),
                    "--output",
                    str(manifest_path),
                    "--compat-output",
                    str(compat_path),
                ],
                cwd=REPO_ROOT,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            self.assertEqual(materialize.returncode, 0, msg=materialize.stderr or materialize.stdout)

            verify = subprocess.run(
                ["python3", str(verifier), str(manifest_path)],
                cwd=REPO_ROOT,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            self.assertEqual(verify.returncode, 0, msg=verify.stderr or verify.stdout)

            materialized = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(materialized.get("channel"), "preview")
            self.assertIn("preview", str(materialized.get("rolloutState") or "").lower())

            stamped_receipt = receipt_path.read_text(encoding="utf-8")
            self.assertIn('"status": "pass"', stamped_receipt)

    def test_haproxy_backends_reference_defined_services(self):
        cp = run_compose("config", "--services")
        self.assertEqual(cp.returncode, 0, msg=cp.stderr or cp.stdout)
        services = {line.strip() for line in cp.stdout.splitlines() if line.strip()}
        haproxy_path = REPO_ROOT / "haproxy.cfg"
        if not haproxy_path.exists():
            self.skipTest("haproxy.cfg is not present for this repository slice")

        haproxy_cfg = haproxy_path.read_text(encoding="utf-8")
        upstreams = set(re.findall(r"server\s+\S+\s+([A-Za-z0-9_.-]+):\d+", haproxy_cfg))
        missing = sorted(upstreams - services)

        self.assertEqual(
            missing,
            [],
            msg="haproxy backends missing in compose: " + ", ".join(missing),
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)

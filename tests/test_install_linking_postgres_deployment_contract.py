from __future__ import annotations

import subprocess
import re
import unittest
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
COMPOSE_PATH = ROOT / "docker-compose.public-edge.yml"
ENV_EXAMPLE_PATH = ROOT / ".env.example"
SECURITY_DOC_PATH = ROOT / "docs" / "INSTALL_LINKING_STORE_SECURITY.md"
RUNBOOK_PATH = ROOT / "docs" / "SELF_HOSTED_DOWNLOADS_RUNBOOK.md"
DOCKERFILE_PATH = ROOT / "Chummer.Run.Api" / "Dockerfile"
DOCKERIGNORE_PATH = ROOT / ".dockerignore"


class InstallLinkingPostgresDeploymentContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.compose = yaml.safe_load(COMPOSE_PATH.read_text(encoding="utf-8"))
        cls.services = cls.compose["services"]

    def test_portal_receives_only_owner_file_runtime_credential(self) -> None:
        portal = self.services["chummer-portal"]
        environment = portal["environment"]
        volumes = "\n".join(portal["volumes"])

        self.assertEqual(
            "/run/chummer-secrets/install-linking-postgres-runtime.connection-string",
            environment["CHUMMER_INSTALL_LINKING_POSTGRES_CONNECTION_STRING_FILE"],
        )
        self.assertIn("CHUMMER_INSTALL_LINKING_POSTGRES_RUNTIME_CONNECTION_FILE", volumes)
        self.assertIn(
            ":/run/chummer-secrets/install-linking-postgres-runtime.connection-string:ro",
            volumes,
        )
        self.assertNotIn("MIGRATOR", volumes.upper())
        self.assertNotIn(
            "CHUMMER_INSTALL_LINKING_MIGRATOR_CONNECTION_STRING_FILE",
            environment,
        )

    def test_install_linking_processes_disable_privilege_escalation_and_core_dumps(self) -> None:
        for service_name in (
            "chummer-portal",
            "chummer-install-linking-postgres-admin",
            "chummer-install-linking-postgres-import",
        ):
            with self.subTest(service=service_name):
                service = self.services[service_name]
                self.assertEqual(["ALL"], service["cap_drop"])
                self.assertIn("no-new-privileges:true", service["security_opt"])
                self.assertEqual(0, service["ulimits"]["core"])

    def test_operator_jobs_use_selected_source_and_nonroot_writable_sticky_tmp(self) -> None:
        for service_name in (
            "chummer-install-linking-postgres-admin",
            "chummer-install-linking-postgres-import",
        ):
            with self.subTest(service=service_name):
                service = self.services[service_name]
                build = service["build"]
                self.assertEqual(
                    "${CHUMMER_PUBLIC_EDGE_BUILD_CONTEXT:-/docker/chummercomplete}",
                    build["context"],
                )
                self.assertEqual(
                    "${CHUMMER_RUN_SERVICES_CONTEXT_DIR:-chummer.run-services}/Chummer.Run.Api/Dockerfile",
                    build["dockerfile"],
                )
                self.assertEqual(
                    ["/tmp:rw,noexec,nosuid,nodev,mode=1777"],
                    service["tmpfs"],
                )

    def test_docker_context_includes_every_named_context_input(self) -> None:
        dockerignore = DOCKERIGNORE_PATH.read_text(encoding="utf-8")
        for marker in (
            "!Chummer.InstallLinking.Postgres.Tool/",
            "!Chummer.InstallLinking.Postgres.Tool/Chummer.InstallLinking.Postgres.Tool.csproj",
            "!Chummer.InstallLinking.Postgres.Tool/Program.cs",
            "Chummer.InstallLinking.Postgres.Tool/bin/**",
            "Chummer.InstallLinking.Postgres.Tool/obj/**",
            "!scripts/validate_public_pwa_proof_authority.py",
            "!scripts/verify_public_pwa_static_assets.py",
            "!scripts/generate_public_play_worker_projection.py",
        ):
            self.assertIn(marker, dockerignore)
        self.assertNotIn("!Chummer.InstallLinking.Postgres.Tool/**", dockerignore)

    def test_profile_admin_job_is_overlay_free_and_migrator_only(self) -> None:
        service = self.services["chummer-install-linking-postgres-admin"]
        volumes = "\n".join(service["volumes"])

        self.assertEqual(["install-linking-postgres-admin"], service["profiles"])
        self.assertEqual(["validate"], service["command"])
        self.assertTrue(service["read_only"])
        self.assertEqual("chummer-install-linking-postgres-tool:local", service["image"])
        self.assertEqual("install-linking-postgres-tool-final", service["build"]["target"])
        self.assertNotIn("entrypoint", service)
        self.assertIn("CHUMMER_INSTALL_LINKING_POSTGRES_MIGRATOR_CONNECTION_FILE", volumes)
        self.assertIn(
            ":/run/chummer-secrets/install-linking-postgres-migrator.connection-string:ro",
            volumes,
        )
        self.assertNotIn("CHUMMER_INSTALL_LINKING_POSTGRES_RUNTIME_CONNECTION_FILE", volumes)
        self.assertNotIn("chummer-run-api-state:/app/state", volumes)
        self.assertNotIn(":/app:ro", volumes)
        self.assertIn(
            "CHUMMER_INSTALL_LINKING_POSTGRES_RUNTIME_ROLE",
            service["environment"],
        )

    def test_profile_import_job_requires_explicit_override_and_minimal_state(self) -> None:
        service = self.services["chummer-install-linking-postgres-import"]
        volumes = "\n".join(service["volumes"])

        self.assertEqual(["install-linking-postgres-admin"], service["profiles"])
        self.assertEqual(["refuse-import-without-explicit-command"], service["command"])
        self.assertEqual("chummer-install-linking-postgres-tool:local", service["image"])
        self.assertEqual("install-linking-postgres-tool-final", service["build"]["target"])
        self.assertNotIn("import-local", service["command"])
        self.assertIn("chummer-run-api-state:/app/state", volumes)
        self.assertIn("CHUMMER_DATA_PROTECTION_CERTIFICATE_FILE", volumes)
        self.assertIn("CHUMMER_DATA_PROTECTION_CERTIFICATE_PASSWORD_FILE", volumes)
        self.assertIn("CHUMMER_INSTALL_LINKING_POSTGRES_RUNTIME_CONNECTION_FILE", volumes)
        self.assertIn(
            ":/run/chummer-secrets/install-linking-postgres-runtime.connection-string:ro",
            volumes,
        )
        self.assertNotIn("MIGRATOR", volumes.upper())
        self.assertNotIn(":/app:ro", volumes)

    def test_public_api_image_excludes_the_operator_tool(self) -> None:
        dockerfile = DOCKERFILE_PATH.read_text(encoding="utf-8")
        tool_stage = dockerfile.index("AS install-linking-postgres-tool-final")
        api_stage = dockerfile.index("AS final", tool_stage)

        self.assertIn(
            "COPY --from=build /app/install-linking-postgres-tool .",
            dockerfile[tool_stage:api_stage],
        )
        self.assertNotIn(
            "install-linking-postgres-tool",
            dockerfile[api_stage:],
        )

    def test_compose_does_not_embed_postgres(self) -> None:
        postgres_images = [
            name
            for name, service in self.services.items()
            if str(service.get("image", "")).lower().startswith("postgres:")
        ]

        self.assertEqual([], postgres_images)
        self.assertNotIn("chummer-install-linking-postgres-data", self.compose.get("volumes", {}))

    def test_environment_and_security_docs_define_external_tls_contract(self) -> None:
        env_example = ENV_EXAMPLE_PATH.read_text(encoding="utf-8")
        security_doc = SECURITY_DOC_PATH.read_text(encoding="utf-8")

        for name in (
            "CHUMMER_INSTALL_LINKING_POSTGRES_RUNTIME_CONNECTION_FILE",
            "CHUMMER_INSTALL_LINKING_POSTGRES_MIGRATOR_CONNECTION_FILE",
            "CHUMMER_INSTALL_LINKING_POSTGRES_RUNTIME_ROLE",
        ):
            self.assertIn(name, env_example)
        self.assertIn("managed or externally operated", security_doc)
        self.assertIn("SSL Mode=VerifyFull", security_doc)
        self.assertIn("must already exist", security_doc)
        self.assertIn("point-in-time recovery", security_doc)
        self.assertNotIn("external_rollback_authority_unimplemented", security_doc)

    def test_runbook_has_bounded_exact_cutover_and_fail_closed_recovery(self) -> None:
        runbook = RUNBOOK_PATH.read_text(encoding="utf-8")
        self.assertIn("## Install-linking PostgreSQL authority cutover and recovery", runbook)
        self.assertNotIn("+## Install-linking PostgreSQL authority cutover", runbook)
        section = runbook[runbook.index("## Install-linking PostgreSQL authority cutover") :]
        ordered_markers = (
            '--output "$overlay_publish_receipt"',
            "build --builder default chummer-portal chummer-install-linking-postgres-admin",
            '--output "$prebuild_overlay_preflight_receipt"',
            "cutover_drained=1",
            "stop chummer-run-cloudflared",
            "stop chummer-portal",
            "publish_public_edge_portal_overlay.py --activate --reuse-staging",
            '--output "$overlay_preflight_receipt"',
            '"chummer6-hub-${cutover_id}-prepare"',
            '"chummer6-hub-${cutover_id}-import"',
            '"chummer6-hub-${cutover_id}-validate"',
            "up -d --no-deps --force-recreate \\\n  --wait --wait-timeout 180 chummer-portal",
            "http://127.0.0.1:8080/api/ready",
            "up -d --no-deps --force-recreate \\\n  --wait --wait-timeout 180 \\\n  chummer-run-cloudflared",
            'https://chummer.run/api/ready >"$public_readiness_receipt"',
            "cutover_drained=0",
        )
        positions = []
        cursor = 0
        for marker in ordered_markers:
            position = section.index(marker, cursor)
            positions.append(position)
            cursor = position + len(marker)

        self.assertEqual(sorted(positions), positions)
        self.assertIn(
            "build --builder default chummer-portal chummer-install-linking-postgres-admin",
            section,
        )
        self.assertGreaterEqual(section.count("timeout --kill-after=10s 180s"), 4)
        self.assertIn("timeout --kill-after=30s 3600s", section)
        self.assertIn("timeout --kill-after=30s 3000s", section)
        self.assertIn("timeout --kill-after=30s 1800s", section)
        self.assertIn("verify_public_edge_postdeploy_gate.py", section)
        self.assertNotIn("--self-contained-direct", section)
        self.assertIn("--strict-preflight", section)
        self.assertIn('--release-channel-receipt "$CHUMMER_PUBLIC_EDGE_RELEASE_CHANNEL_RECEIPT"', section)
        self.assertIn('--overlay-root "$active_root"', section)
        self.assertIn('--expected-build-info "$active_build_info"', section)
        self.assertIn("--require-downloads-status-playwright", section)
        self.assertIn("--require-mobile-pwa-viewport-playwright", section)
        self.assertIn("--require-frontdoor-navigation-playwright", section)
        self.assertIn("materialize_install_linking_cutover_boundary.py", section)
        self.assertIn("postgres_pitr_or_governed_recovery", section)
        self.assertIn("restore_prior_mutable_image_tag", section)
        self.assertIn("image_tags_committed=1", section)
        self.assertIn("image_tag_rollback_active=1", section)
        self.assertIn("chummer-install-linking-postgres-tool:local", section)
        self.assertEqual(5, section.count('--candidate-tool-image-id "$candidate_postgres_tool_image_id"'))
        self.assertEqual(3, section.count("--operator-container-image-id"))
        self.assertIn('>"$operator_log" 2>&1 || return', section)
        self.assertNotIn("CHUMMER_INSTALL_LINKING_POSTGRES_OPERATOR_TIMEOUT_SECONDS", section)
        self.assertIn("set -eu", section)
        self.assertIn("umask 077", section)
        self.assertIn("public-edge-mutation.lock", section)
        self.assertIn(
            "cutover_lock_dir=/docker/chummercomplete/.state/public-edge-mutation.lock",
            section,
        )
        self.assertNotIn("cutover_state_dir=", section)
        self.assertIn("trap cutover_cleanup EXIT", section)
        self.assertIn("trap 'exit 129' HUP", section)
        self.assertIn("trap 'exit 130' INT", section)
        self.assertIn("trap 'exit 143' TERM", section)
        self.assertIn('"${docker_command[@]}" rm --force', section)
        self.assertIn("assert_no_operator_jobs", section)
        self.assertIn("chummer-install-linking-readiness.XXXXXX.json", section)
        self.assertIn("chummer-install-linking-public-readiness.XXXXXX.json", section)
        self.assertIn("chummer-install-linking-container-build-info.XXXXXX.json", section)
        self.assertIn('chmod 600 "$readiness_receipt"', section)
        self.assertIn("exec -T chummer-portal", section)
        self.assertGreaterEqual(
            section.count("validate_install_linking_cutover_readiness.py"),
            2,
        )
        self.assertIn("validate_install_linking_cutover_overlay_binding.py", section)
        self.assertIn("publish_public_edge_portal_overlay.py --activate --reuse-staging", section)
        self.assertIn("--release-channel-receipt-sha256", section)
        self.assertIn('--source-root "$source_root" --active-root "$active_root"', section)
        self.assertGreaterEqual(section.count("--wait-timeout 180"), 2)
        self.assertIn("--skip-overlay-marker-check", section)
        self.assertGreaterEqual(section.count("stop chummer-portal"), 1)
        self.assertIn("leave the tunnel stopped", section)
        self.assertIn("point-in-time recovery", section)
        self.assertIn("Rollback is fail-closed", section)
        self.assertIn("protected local floor", section)
        self.assertIn("/usr/bin/bash --noprofile --norc", section)
        self.assertIn("LD_PRELOAD", section)
        self.assertIn("LD_LIBRARY_PATH", section)
        self.assertIn("### Authenticated manual stale-lock recovery", section)
        self.assertIn("recover_public_edge_mutation_lock.py", section)
        self.assertIn("REMOVE_STALE_PUBLIC_EDGE_MUTATION_LOCK", section)
        self.assertIn("REMOVE_ORPHANED_PUBLIC_EDGE_MUTATION_ARTIFACT", section)
        self.assertIn("REMOVE_INCOMPLETE_PUBLIC_EDGE_MUTATION_LOCK", section)
        self.assertIn("--expected-authorization-device", section)
        self.assertIn("--expected-authorization-inode", section)
        self.assertIn("--expected-authorization-mtime-ns", section)
        self.assertIn("--mode orphan", section)
        self.assertIn("--mode incomplete-lock", section)
        self.assertIn("I_VERIFIED_NO_PUBLIC_EDGE_MUTATION_IS_RUNNING", section)
        self.assertIn("chummer.public_edge_mutation_lock_recovery.v1", (
            ROOT / "scripts" / "recover_public_edge_mutation_lock.py"
        ).read_text(encoding="utf-8"))

        shell_start = section.index("```bash\n(\nset -euo pipefail") + len("```bash")
        shell_end = section.index("```", shell_start)
        shell = section[shell_start:shell_end]
        self.assertNotIn('cutover_lock_dir="${RUNBOOK_STATE_DIR', shell)
        self.assertIn(
            ': "${CHUMMER_RUN_SERVICES_SOURCE:?Export the absolute run-services source root used by Compose}"',
            shell,
        )
        self.assertIn(
            ': "${CHUMMER_PUBLIC_PORTAL_APP_OVERLAY_DIR:?Export the absolute portal /app overlay root used by Compose}"',
            shell,
        )
        self.assertIn("normalize_existing_root()", shell)
        self.assertIn('if not raw.startswith("/")', shell)
        self.assertIn("stat.S_ISLNK(metadata.st_mode)", shell)
        self.assertIn("normalized.resolve(strict=True)", shell)
        self.assertIn(
            'export CHUMMER_RUN_SERVICES_SOURCE="$source_root"',
            shell,
        )
        self.assertIn('export CHUMMER_RUN_SERVICES_CONTEXT_DIR="$source_root"', shell)
        self.assertIn('export CHUMMER_PUBLIC_EDGE_BUILD_CONTEXT="$build_context"', shell)
        self.assertIn('cd -- "$source_root"', shell)
        self.assertIn(
            'export CHUMMER_PUBLIC_PORTAL_APP_OVERLAY_DIR="$active_root"',
            shell,
        )
        self.assertIn("chummer-compose-runtime.XXXXXX.json", shell)
        self.assertIn("config --format json", shell)
        self.assertIn("validate_public_edge_compose_runtime.py", shell)
        self.assertIn('--output "$compose_runtime_attestation_receipt"', shell)
        self.assertNotIn("chummer.install_linking.compose_root_binding.v1", shell)
        self.assertIn("set -euo pipefail", shell)
        self.assertNotIn("compose_config_json", shell)
        self.assertIn('CHUMMER_PUBLIC_EDGE_CLEAN_LAUNCH" = 1', shell)
        self.assertIn("CHUMMER_PUBLIC_EDGE_EXPECTED_HEAD", shell)
        self.assertIn("CHUMMER_PUBLIC_EDGE_EXPECTED_UPSTREAM_REF", shell)
        self.assertIn("CHUMMER_PUBLIC_EDGE_AUTHORITY_VERIFIER_SHA256", shell)
        self.assertIn("/usr/bin/sha256sum", shell)
        self.assertIn("verify_public_edge_deploy_authority.py", shell)
        self.assertIn("/usr/bin/env -i", shell)
        self.assertIn("/usr/bin/python3 -I", shell)
        self.assertNotIn("${RUNBOOK_LOG_DIR:-/tmp}", shell)
        self.assertIn(
            ': "${RUNBOOK_LOG_DIR:?Export a persistent cutover receipt directory',
            shell,
        )
        self.assertIn("public-edge-cutover-receipts", shell)
        self.assertIn("mode-0700 symlink-free directory", shell)

        source_export_position = shell.index(
            'export CHUMMER_RUN_SERVICES_SOURCE="$source_root"'
        )
        overlay_export_position = shell.index(
            'export CHUMMER_PUBLIC_PORTAL_APP_OVERLAY_DIR="$active_root"'
        )
        compose_config_position = shell.index(
            "config --format json",
            overlay_export_position,
        )
        trusted_source_position = shell.index(
            '"$trusted_source_verifier"'
        )
        first_selected_source_python_position = shell.index(
            "normalize_existing_root()"
        )
        shared_lock_position = shell.index(
            "cutover_lock_dir=/docker/chummercomplete/.state/public-edge-mutation.lock"
        )
        compose_attestation_position = shell.index(
            "validate_public_edge_compose_runtime.py", compose_config_position
        )
        overlay_publish_position = shell.index(
            "publish_public_edge_portal_overlay.py \\",
            compose_attestation_position,
        )
        first_mutating_docker_position = shell.index(
            "build --builder default chummer-portal chummer-install-linking-postgres-admin",
            overlay_publish_position,
        )
        self.assertLess(source_export_position, compose_config_position)
        self.assertLess(overlay_export_position, compose_config_position)
        self.assertLess(shared_lock_position, compose_config_position)
        self.assertLess(compose_config_position, compose_attestation_position)
        self.assertLess(compose_attestation_position, overlay_publish_position)
        self.assertLess(compose_attestation_position, first_mutating_docker_position)
        self.assertLess(trusted_source_position, first_selected_source_python_position)
        self.assertLess(trusted_source_position, compose_config_position)

        prior_portal_position = shell.index(
            "prior_portal_image_tag_id=", overlay_publish_position
        )
        prior_tool_position = shell.index(
            "prior_postgres_tool_image_tag_id=", prior_portal_position
        )
        rollback_active_position = shell.index(
            "image_tag_rollback_active=1", prior_tool_position
        )
        self.assertLess(rollback_active_position, first_mutating_docker_position)

        staged_position = shell.index('--output "$overlay_publish_receipt"')
        build_position = shell.index(
            "build --builder default chummer-portal chummer-install-linking-postgres-admin",
            staged_position,
        )
        postbuild_position = shell.index('--output "$prebuild_overlay_preflight_receipt"', build_position)
        stop_position = shell.index("stop chummer-portal", postbuild_position)
        activation_position = shell.index(
            "publish_public_edge_portal_overlay.py --activate --reuse-staging",
            stop_position,
        )
        active_preflight_position = shell.index(
            '--output "$overlay_preflight_receipt"', activation_position
        )
        self.assertLess(staged_position, build_position)
        self.assertLess(build_position, postbuild_position)
        self.assertLess(postbuild_position, stop_position)
        self.assertLess(stop_position, activation_position)
        self.assertLess(activation_position, active_preflight_position)
        self.assertIn('--header "@$cf_access_header_file"', shell)
        public_readiness_position = shell.index(
            'https://chummer.run/api/ready >"$public_readiness_receipt"'
        )
        postdeploy_gate_position = shell.index(
            "verify_public_edge_postdeploy_gate.py",
            public_readiness_position,
        )
        commit_position = shell.index("cutover_drained=0", postdeploy_gate_position)
        self.assertLess(public_readiness_position, postdeploy_gate_position)
        self.assertLess(postdeploy_gate_position, commit_position)
        self.assertIn("docker_command=(", shell)
        self.assertIn("/usr/bin/env -i PATH=/usr/bin:/bin LANG=C LC_ALL=C", shell)
        self.assertIn("/usr/bin/docker --context default", shell)
        self.assertIn("CHUMMER_PUBLIC_EDGE_PORT=8091", shell)
        self.assertIn("--published-port 8091", shell)
        self.assertIn("matches = []", shell)
        self.assertIn("matches.append(item)", shell)
        self.assertIn("if len(matches) != 1:", shell)
        timed_docker_calls = re.findall(
            r"/usr/bin/timeout --kill-after=[^\n]*\n?(?:\s+)?\"\$\{docker_command\[@\]\}\"",
            shell,
        )
        self.assertGreaterEqual(len(timed_docker_calls), 15)
        self.assertIsNone(
            re.search(r"/usr/bin/timeout[^\n]*(?:^|\s)docker(?:\s|$)", shell)
        )

        syntax = subprocess.run(
            ["bash", "-n"],
            input=shell,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual("", syntax.stderr)
        self.assertEqual(0, syntax.returncode)


if __name__ == "__main__":
    unittest.main()

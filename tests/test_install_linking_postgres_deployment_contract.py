from __future__ import annotations

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
DEPLOY_PATH = ROOT / "scripts" / "deploy_public_edge_portal.sh"


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
        self.assertIn(
            "CHUMMER_INSTALL_LINKING_POSTGRES_DNS_NAME",
            environment["CHUMMER_INSTALL_LINKING_POSTGRES_EXPECTED_HOST"],
        )
        self.assertIn("CHUMMER_INSTALL_LINKING_POSTGRES_RUNTIME_CONNECTION_FILE", volumes)
        self.assertIn(
            ":/run/chummer-secrets/install-linking-postgres-runtime.connection-string:ro",
            volumes,
        )
        self.assertIn("CHUMMER_INSTALL_LINKING_POSTGRES_SERVER_CA_FILE", volumes)
        self.assertIn(
            ":/run/chummer-secrets/install-linking-postgres-server-ca.pem:ro",
            volumes,
        )
        self.assertIn(
            "CHUMMER_INSTALL_LINKING_POSTGRES_DNS_NAME",
            "\n".join(portal["extra_hosts"]),
        )
        self.assertIn(
            "CHUMMER_INSTALL_LINKING_POSTGRES_IP",
            "\n".join(portal["extra_hosts"]),
        )
        self.assertNotIn("MIGRATOR", volumes.upper())
        self.assertNotIn(
            "CHUMMER_INSTALL_LINKING_MIGRATOR_CONNECTION_STRING_FILE",
            environment,
        )

    def test_reviewed_postgres_address_is_documented_as_stable_and_reattested(self) -> None:
        security = SECURITY_DOC_PATH.read_text(encoding="utf-8")
        runbook = RUNBOOK_PATH.read_text(encoding="utf-8")

        for document in (security, runbook):
            with self.subTest(document=document[:40]):
                normalized = " ".join(document.split())
                self.assertIn("stable across portal and database restarts or recreation", normalized)
                self.assertIn("automatically assigned container address", normalized)
                self.assertIn("complete Compose attestation", normalized)
                self.assertIn("guarded portal deployment", normalized)

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

    def test_activation_parser_uses_the_exact_validated_build_context(self) -> None:
        deploy = DEPLOY_PATH.read_text(encoding="utf-8")
        parser_start = deploy.index(
            "# InstallLinking candidate build-source provenance parser."
        )
        parser_end = deploy.index(
            '  echo "InstallLinking candidate build-source provenance is invalid"',
            parser_start,
        )
        parser = deploy[parser_start:parser_end]

        self.assertIn(
            "select_exact_build_context_provenance",
            parser,
        )
        self.assertIn(
            "bind_exact_build_source_replay",
            parser,
        )
        self.assertIn(
            "build_context.get(\"dockerignoreSha256\")",
            parser,
        )
        self.assertNotIn(
            'provenance.get("canonical-build-context")',
            parser,
        )

    def test_synthetic_replay_is_preflighted_and_forwarded_before_quiesce(
        self,
    ) -> None:
        deploy = DEPLOY_PATH.read_text(encoding="utf-8")
        preflight = deploy.index("--source-replay-preflight")
        quiesce = deploy.index(
            "compose_cli stop chummer-run-cloudflared"
        )
        postquiesce = deploy.index("--post-quiesce-reproof")

        self.assertLess(preflight, quiesce)
        self.assertLess(quiesce, postquiesce)
        self.assertIn(
            '--source-root "$INSTALL_LINKING_POSTQUIESCE_SOURCE_ROOT"',
            deploy,
        )
        self.assertGreaterEqual(
            deploy.count('"${install_linking_source_replay_args[@]}"'),
            2,
        )
        for option in (
            "--synthetic-workspace-root",
            "--build-context-root",
            "--hub-registry-root",
            "--design-product-root",
            "--fleet-media-factory-root",
            "--expected-run-services-content-sha256",
            "--expected-hub-registry-content-sha256",
            "--expected-design-product-content-sha256",
            "--expected-fleet-media-factory-content-sha256",
        ):
            self.assertIn(option, deploy)

    def test_topology_b_authority_blocks_only_fresh_canonical_mutation(
        self,
    ) -> None:
        deploy = DEPLOY_PATH.read_text(encoding="utf-8")
        guard = deploy.index(
            "canonical public edge mutation is blocked while topology-B "
            "downloads authority exists"
        )
        guard_start = deploy.rfind(
            'if [[ "$DEPLOY_OPERATION" == deploy',
            0,
            guard,
        )
        guard_condition_end = deploy.index("then", guard_start)
        condition = deploy[guard_start:guard_condition_end]

        self.assertIn(
            '"$DEPLOY_OPERATION" == initial-release-shelf-cutover',
            condition,
        )
        self.assertIn("RECOVERY_ROUTE_REQUESTED == 0", condition)
        self.assertIn(
            '-e "$PUBLIC_DOWNLOAD_ACTIVE_RUNTIME_AUTHORITY"',
            condition,
        )
        self.assertIn(
            '-L "$PUBLIC_DOWNLOAD_ACTIVE_RUNTIME_AUTHORITY"',
            condition,
        )
        self.assertNotIn(
            "initial-release-shelf-public-download-cutover",
            condition,
        )
        self.assertLess(guard, deploy.index("deploy_lock_active=1"))
        self.assertLess(guard, deploy.index("--source-replay-preflight"))
        self.assertLess(
            guard,
            deploy.index("compose_cli stop chummer-run-cloudflared"),
        )

    def test_docker_context_includes_every_named_context_input(self) -> None:
        dockerignore = DOCKERIGNORE_PATH.read_text(encoding="utf-8")
        for marker in (
            "!Chummer.InstallLinking.Postgres.Tool/",
            "!Chummer.InstallLinking.Postgres.Tool/Chummer.InstallLinking.Postgres.Tool.csproj",
            "!Chummer.InstallLinking.Postgres.Tool/Program.cs",
            "Chummer.InstallLinking.Postgres.Tool/bin/**",
            "Chummer.InstallLinking.Postgres.Tool/obj/**",
            "!Chummer.Run.LoopbackProbe/Chummer.Run.LoopbackProbe.csproj",
            "!Chummer.Run.LoopbackProbe/packages.lock.json",
            "!Chummer.Run.LoopbackProbe/Program.cs",
            "Chummer.Run.LoopbackProbe/bin/**",
            "Chummer.Run.LoopbackProbe/obj/**",
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
        self.assertIn("CHUMMER_INSTALL_LINKING_POSTGRES_SERVER_CA_FILE", volumes)
        self.assertIn(
            ":/run/chummer-secrets/install-linking-postgres-server-ca.pem:ro",
            volumes,
        )
        self.assertIn(
            "CHUMMER_INSTALL_LINKING_POSTGRES_DNS_NAME",
            "\n".join(service["extra_hosts"]),
        )
        self.assertIn(
            "CHUMMER_INSTALL_LINKING_POSTGRES_IP",
            "\n".join(service["extra_hosts"]),
        )
        self.assertNotIn("CHUMMER_INSTALL_LINKING_POSTGRES_RUNTIME_CONNECTION_FILE", volumes)
        self.assertNotIn("chummer-run-api-state:/app/state", volumes)
        self.assertNotIn(":/app:ro", volumes)
        self.assertIn(
            "CHUMMER_INSTALL_LINKING_POSTGRES_RUNTIME_ROLE",
            service["environment"],
        )
        self.assertIn(
            "CHUMMER_INSTALL_LINKING_POSTGRES_DNS_NAME",
            service["environment"]["CHUMMER_INSTALL_LINKING_POSTGRES_EXPECTED_HOST"],
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
        self.assertIn("CHUMMER_INSTALL_LINKING_POSTGRES_SERVER_CA_FILE", volumes)
        self.assertIn(
            ":/run/chummer-secrets/install-linking-postgres-server-ca.pem:ro",
            volumes,
        )
        self.assertIn(
            "CHUMMER_INSTALL_LINKING_POSTGRES_DNS_NAME",
            "\n".join(service["extra_hosts"]),
        )
        self.assertIn(
            "CHUMMER_INSTALL_LINKING_POSTGRES_IP",
            "\n".join(service["extra_hosts"]),
        )
        self.assertNotIn("MIGRATOR", volumes.upper())
        self.assertNotIn(":/app:ro", volumes)
        self.assertIn(
            "CHUMMER_INSTALL_LINKING_POSTGRES_DNS_NAME",
            service["environment"]["CHUMMER_INSTALL_LINKING_POSTGRES_EXPECTED_HOST"],
        )

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
        self.assertIn(
            "COPY --from=build /app/loopback-probe /app/loopback-probe/",
            dockerfile[api_stage:],
        )

        probe_root = ROOT / "Chummer.Run.LoopbackProbe"
        project = (
            probe_root / "Chummer.Run.LoopbackProbe.csproj"
        ).read_text(encoding="utf-8")
        program = (probe_root / "Program.cs").read_text(encoding="utf-8")
        for marker in (
            "<PackageReference",
            "<ProjectReference",
            "<FrameworkReference",
        ):
            self.assertNotIn(marker, project)
        for marker in (
            "Chummer.InstallLinking",
            "Npgsql",
            "Environment.GetEnvironmentVariable",
            "System.Data",
        ):
            self.assertNotIn(marker, program)

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
            "CHUMMER_INSTALL_LINKING_POSTGRES_SERVER_CA_FILE",
            "CHUMMER_INSTALL_LINKING_POSTGRES_DNS_NAME",
            "CHUMMER_INSTALL_LINKING_POSTGRES_IP",
            "CHUMMER_INSTALL_LINKING_POSTGRES_RUNTIME_ROLE",
        ):
            self.assertIn(name, env_example)
        self.assertIn("managed or externally operated", security_doc)
        self.assertIn("SSL Mode=VerifyFull", security_doc)
        self.assertIn("Root Certificate=/run/chummer-secrets/install-linking-postgres-server-ca.pem", security_doc)
        self.assertIn("must exactly match a server-certificate SAN", security_doc)
        self.assertIn("raw-IP `Host` values are not acceptable", security_doc)
        self.assertIn("must already exist", security_doc)
        self.assertIn("point-in-time recovery", security_doc)
        self.assertNotIn("external_rollback_authority_unimplemented", security_doc)

    def test_runbook_requires_governed_cutover_and_fail_closed_recovery(self) -> None:
        runbook = RUNBOOK_PATH.read_text(encoding="utf-8")
        deploy = DEPLOY_PATH.read_text(encoding="utf-8")
        install_heading = "## Install-linking PostgreSQL authority cutover and recovery"
        mode_a_heading = (
            "## Mode A: Legacy/dev filesystem source candidate "
            "(shared mount; never production)"
        )
        self.assertIn(install_heading, runbook)
        self.assertIn(mode_a_heading, runbook)
        section = runbook[
            runbook.index(install_heading) : runbook.index(mode_a_heading)
        ]

        for marker in (
            "### Required DBA boundary before deployment",
            "prepare",
            "import-local --confirm-empty-authority",
            "validate",
            "materialize_install_linking_cutover_boundary.py",
            "postgres_pitr_or_governed_recovery",
            "### Sole production application cutover",
            "durable blue-green transaction",
            "scripts/deploy_public_edge_portal.sh",
            "scripts/deploy_public_edge_portal.sh recover",
            "### Authenticated manual stale-lock recovery",
            "recover_public_edge_mutation_lock.py",
            "REMOVE_STALE_PUBLIC_EDGE_MUTATION_LOCK",
            "REMOVE_ORPHANED_PUBLIC_EDGE_MUTATION_ARTIFACT",
            "REMOVE_INCOMPLETE_PUBLIC_EDGE_MUTATION_LOCK",
            "--expected-authorization-device",
            "--expected-authorization-inode",
            "--expected-authorization-mtime-ns",
            "--mode orphan",
            "--mode incomplete-lock",
            "I_VERIFIED_NO_PUBLIC_EDGE_MUTATION_IS_RUNNING",
        ):
            with self.subTest(required_marker=marker):
                self.assertIn(marker, section)

        for authority in (
            "CHUMMER_PUBLIC_EDGE_CLEAN_LAUNCH=1",
            "CHUMMER_PUBLIC_EDGE_EXPECTED_HEAD",
            "CHUMMER_PUBLIC_EDGE_EXPECTED_UPSTREAM_REF",
            "CHUMMER_PUBLIC_EDGE_AUTHORITY_VERIFIER_SHA256",
            "CHUMMER_PUBLIC_EDGE_RELEASE_CHANNEL_RECEIPT",
            "CHUMMER_PUBLIC_EDGE_RELEASE_CHANNEL_RECEIPT_SHA256",
            "CHUMMER_PUBLIC_EDGE_RUNTIME_PROOF_BIND_SOURCE_SHA256",
            "CHUMMER_PUBLIC_EDGE_RELEASE_CHANNEL",
            "CHUMMER_RUN_SERVICES_SOURCE",
            "CHUMMER_PUBLIC_EDGE_BUILD_CONTEXT",
            "CHUMMER_PUBLIC_PORTAL_APP_OVERLAY_DIR",
            "RUNBOOK_LOG_DIR",
        ):
            with self.subTest(external_authority=authority):
                self.assertIn(authority, section)

        for unsafe_command in (
            "stop chummer-run-cloudflared",
            "stop chummer-portal",
            "publish_public_edge_portal_overlay.py --activate --reuse-staging",
            "up -d --no-deps --force-recreate",
            "--force-recreate",
            "trap cutover_cleanup EXIT",
            "docker_command=(",
            "drain/stop/activate/probe",
            "leave the tunnel stopped",
        ):
            with self.subTest(unsafe_command=unsafe_command):
                self.assertNotIn(unsafe_command, runbook)

        topology = runbook[
            runbook.index("## Recommended Production Topology") :
            runbook.index(install_heading)
        ]
        self.assertIn("Mode C", topology)
        self.assertIn("server-journal-v1", topology)
        self.assertIn("layout-v1 generation", topology)
        self.assertIn(
            "limited to legacy development or source-candidate trees",
            topology,
        )
        self.assertNotIn("Default recommendation: use", topology)

        mode_a = runbook[
            runbook.index(mode_a_heading) :
            runbook.index("## Mode B: Object Storage Deploy")
        ]
        self.assertIn("never production", mode_a_heading)
        self.assertIn("must not be the live production shelf", mode_a)
        self.assertIn("production uses\nMode C staged HTTP publication", mode_a)
        self.assertIn("RUNBOOK_MODE=downloads-sync", mode_a)
        self.assertIn("isolatedCandidateDir", mode_a)

        materializer = (
            ROOT / "scripts" / "materialize_install_linking_cutover_boundary.py"
        ).read_text(encoding="utf-8")
        self.assertIn("importNotRequiredSeededAuthority", materializer)
        self.assertIn(
            "chummer.public_edge_mutation_lock_recovery.v1",
            (ROOT / "scripts" / "recover_public_edge_mutation_lock.py").read_text(
                encoding="utf-8"
            ),
        )
        self.assertIn(
            '--public-release-manifest "$CANONICAL_RELEASE_SHELF_ROOT/'
            'RELEASE_CHANNEL.generated.json"',
            deploy,
        )
        self.assertIn(
            'payload.get("contractName") != '
            '"chummer.public_edge_postdeploy_gate.v2"',
            deploy,
        )


if __name__ == "__main__":
    unittest.main()

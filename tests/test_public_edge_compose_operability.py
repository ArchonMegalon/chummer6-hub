from __future__ import annotations

import copy
import importlib.util
import tempfile
import unittest
from pathlib import Path


SCRIPT_PATH = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "verify_public_edge_compose_operability.py"
)
RUN_SERVICES_VERIFY_PATH = SCRIPT_PATH.parent / "ai" / "verify.sh"
ROOT_RELEASE_READY_WRAPPER_PATH = (
    SCRIPT_PATH.parents[2] / "scripts" / "release" / "verify_chummer6_release_ready.sh"
)
RELEASE_READY_MATERIALIZER_PATH = (
    SCRIPT_PATH.parents[1] / "scripts" / "materialize_release_ready_receipt.py"
)


def load_module():
    spec = importlib.util.spec_from_file_location("verify_public_edge_compose_operability", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class PublicEdgeComposeOperabilityTests(unittest.TestCase):
    def test_operability_validation_is_wired_into_release_gates(self) -> None:
        run_services_verifier = RUN_SERVICES_VERIFY_PATH.read_text(encoding="utf-8")
        root_release_wrapper = ROOT_RELEASE_READY_WRAPPER_PATH.read_text(encoding="utf-8")
        release_ready_materializer = RELEASE_READY_MATERIALIZER_PATH.read_text(
            encoding="utf-8"
        )

        self.assertIn(
            'python3 "$ROOT_DIR/scripts/verify_public_edge_compose_operability.py" >/dev/null',
            run_services_verifier,
        )
        self.assertIn(
            'MATERIALIZER = ROOT / "chummer.run-services/scripts/materialize_release_ready_receipt.py"',
            root_release_wrapper,
        )
        self.assertIn('"--run-authoritative-controller"', root_release_wrapper)
        self.assertIn(
            'spec("verify_public_edge_compose_operability", '
            'f"cd {services} && {python} {services}/scripts/'
            'verify_public_edge_compose_operability.py"',
            release_ready_materializer,
        )

    def test_current_compose_and_runtime_sources_satisfy_operability_contract(self) -> None:
        module = load_module()

        self.assertEqual([], module.validate_compose(module.load_compose()))
        self.assertEqual([], module.validate_runtime_sources())

    def test_missing_healthcheck_fails_closed(self) -> None:
        module = load_module()
        payload = copy.deepcopy(module.load_compose())
        del payload["services"]["chummer-portal"]["healthcheck"]

        self.assertIn(
            "chummer-portal healthcheck is missing",
            module.validate_compose(payload),
        )

    def test_started_only_dependency_fails_closed(self) -> None:
        module = load_module()
        payload = copy.deepcopy(module.load_compose())
        payload["services"]["chummer-run-cloudflared"]["depends_on"]["chummer-portal"] = {
            "condition": "service_started"
        }

        self.assertIn(
            "chummer-run-cloudflared dependency chummer-portal must require service_healthy",
            module.validate_compose(payload),
        )

    def test_missing_memory_ceiling_fails_closed(self) -> None:
        module = load_module()
        payload = copy.deepcopy(module.load_compose())
        del payload["services"]["chummer-play-web"]["mem_limit"]

        failures = module.validate_compose(payload)
        self.assertTrue(any(failure.startswith("chummer-play-web mem_limit") for failure in failures))

    def test_release_storage_initializer_has_no_network(self) -> None:
        module = load_module()
        payload = copy.deepcopy(module.load_compose())
        del payload["services"]["chummer-release-storage-init"]["network_mode"]

        self.assertIn(
            "chummer-release-storage-init network_mode must be none",
            module.validate_compose(payload),
        )

    def test_portal_waits_for_successful_release_storage_initialization(self) -> None:
        module = load_module()
        payload = copy.deepcopy(module.load_compose())
        payload["services"]["chummer-portal"]["depends_on"][
            "chummer-release-storage-init"
        ]["condition"] = "service_started"

        self.assertIn(
            "chummer-portal dependency chummer-release-storage-init must require "
            "service_completed_successfully",
            module.validate_compose(payload),
        )

    def test_portal_waits_for_healthy_internal_prometheus(self) -> None:
        module = load_module()
        payload = copy.deepcopy(module.load_compose())
        payload["services"]["chummer-portal"]["depends_on"][
            "chummer-observability-prometheus"
        ]["condition"] = "service_started"

        self.assertIn(
            "chummer-portal dependency chummer-observability-prometheus must require service_healthy",
            module.validate_compose(payload),
        )

    def test_prometheus_is_immutable_non_root_internal_only_and_otlp_enabled(self) -> None:
        module = load_module()
        payload = copy.deepcopy(module.load_compose())
        service = payload["services"]["chummer-observability-prometheus"]
        service["image"] = "prom/prometheus:latest"
        service["user"] = "0:0"
        service["ports"] = ["9090:9090"]
        service["command"].remove("--web.enable-otlp-receiver")

        failures = module.validate_compose(payload)

        self.assertTrue(any("immutable supported runtime pin" in item for item in failures))
        self.assertIn(
            "chummer-observability-prometheus must run as uid/gid 65532",
            failures,
        )
        self.assertIn(
            "chummer-observability-prometheus must not publish a host port",
            failures,
        )
        self.assertTrue(any("--web.enable-otlp-receiver" in item for item in failures))

    def test_alertmanager_is_immutable_non_root_internal_only_and_secret_file_bound(self) -> None:
        module = load_module()
        payload = copy.deepcopy(module.load_compose())
        service = payload["services"]["chummer-observability-alertmanager"]
        service["image"] = "prom/alertmanager:latest"
        service["user"] = "0:0"
        service["ports"] = ["9093:9093"]
        service["volumes"] = [
            volume
            for volume in service["volumes"]
            if not isinstance(volume, dict)
        ]

        failures = module.validate_compose(payload)

        self.assertTrue(any("immutable supported runtime pin" in item for item in failures))
        self.assertIn(
            "chummer-observability-alertmanager must run as the governed non-root uid/gid",
            failures,
        )
        self.assertIn(
            "chummer-observability-alertmanager must not publish a host port",
            failures,
        )
        self.assertIn(
            "chummer-observability-alertmanager must mount the governed secret directory read-only",
            failures,
        )

    def test_portal_otlp_binding_cannot_be_removed(self) -> None:
        module = load_module()
        payload = copy.deepcopy(module.load_compose())
        del payload["services"]["chummer-portal"]["environment"][
            "OTEL_EXPORTER_OTLP_METRICS_ENDPOINT"
        ]

        self.assertTrue(
            any(
                "OTEL_EXPORTER_OTLP_METRICS_ENDPOINT" in failure
                for failure in module.validate_compose(payload)
            )
        )

    def test_cloudflared_probe_must_verify_an_active_tunnel(self) -> None:
        module = load_module()
        payload = copy.deepcopy(module.load_compose())
        payload["services"]["chummer-run-cloudflared"]["healthcheck"]["test"][-1] = "--help"

        self.assertIn(
            "chummer-run-cloudflared healthcheck is missing required fragment: ready",
            module.validate_compose(payload),
        )

    def test_cloudflared_runtime_must_expose_a_fixed_metrics_endpoint(self) -> None:
        module = load_module()
        payload = copy.deepcopy(module.load_compose())
        payload["services"]["chummer-run-cloudflared"]["command"].remove("0.0.0.0:2000")

        self.assertIn(
            "chummer-run-cloudflared runtime command is missing required fragment: 0.0.0.0:2000",
            module.validate_compose(payload),
        )

    def test_cloudflared_image_must_be_immutable_and_support_native_readiness_checks(
        self,
    ) -> None:
        module = load_module()
        payload = copy.deepcopy(module.load_compose())
        payload["services"]["chummer-run-cloudflared"]["image"] = (
            "cloudflare/cloudflared:2026.7.0"
        )

        failures = module.validate_compose(payload)
        self.assertTrue(
            any(failure.startswith("chummer-run-cloudflared image must use") for failure in failures)
        )

    def test_cloudflared_replica_must_match_the_verified_runtime_pin(self) -> None:
        module = load_module()
        payload = copy.deepcopy(module.load_compose())
        payload["services"]["chummer-run-cloudflared-replica"]["image"] = (
            "cloudflare/cloudflared:2026.7.0"
        )

        self.assertTrue(
            any(
                failure.startswith(
                    "chummer-run-cloudflared-replica image must use"
                )
                for failure in module.validate_compose(payload)
            )
        )

    def test_missing_runtime_health_route_fails_closed(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory() as temp_dir:
            source_path = Path(temp_dir) / "Program.cs"
            source_path.write_text("app.Run();\n", encoding="utf-8")
            original_contracts = module.HEALTH_ROUTE_SOURCE_CONTRACTS
            original_dockerfiles = module.CURL_RUNTIME_DOCKERFILES
            try:
                module.HEALTH_ROUTE_SOURCE_CONTRACTS = {
                    source_path: ('app.MapGet("/health"',),
                }
                module.CURL_RUNTIME_DOCKERFILES = ()
                failures = module.validate_runtime_sources()
            finally:
                module.HEALTH_ROUTE_SOURCE_CONTRACTS = original_contracts
                module.CURL_RUNTIME_DOCKERFILES = original_dockerfiles

        self.assertTrue(any("is missing required marker" in failure for failure in failures))


if __name__ == "__main__":
    unittest.main()

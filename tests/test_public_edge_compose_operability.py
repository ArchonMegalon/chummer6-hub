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

    def test_cloudflared_default_must_support_native_readiness_checks(self) -> None:
        module = load_module()
        payload = copy.deepcopy(module.load_compose())
        payload["services"]["chummer-run-cloudflared"]["image"] = (
            "cloudflare/cloudflared:${CHUMMER_CLOUDFLARED_IMAGE_TAG:-2024.6.1}"
        )

        failures = module.validate_compose(payload)
        self.assertTrue(
            any(failure.startswith("chummer-run-cloudflared image must use") for failure in failures)
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

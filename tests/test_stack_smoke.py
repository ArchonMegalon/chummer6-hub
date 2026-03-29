from __future__ import annotations

import os
import re
import shutil
import subprocess
import unittest
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
    raise RuntimeError("docker compose (plugin) or docker-compose is required")


COMPOSE_BASE = detect_compose_base()


def compose_env():
    env = os.environ.copy()
    env.setdefault("TUNNEL_TOKEN", "dummy")
    if "COMPOSE_FILE" not in env and DEFAULT_COMPOSE_FILE is not None:
        env["COMPOSE_FILE"] = str(DEFAULT_COMPOSE_FILE.relative_to(REPO_ROOT))
    return env


def run_compose(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [*COMPOSE_BASE, *args],
        cwd=REPO_ROOT,
        env=compose_env(),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
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

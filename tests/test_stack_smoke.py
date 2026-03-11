from __future__ import annotations

import os
import re
import shutil
import subprocess
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


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
        self.assertTrue(
            {"overseerr_v2", "seerr_v2"} & services,
            "expected one of overseerr_v2 or seerr_v2 to be present",
        )

    def test_haproxy_backends_reference_defined_services(self):
        cp = run_compose("config", "--services")
        self.assertEqual(cp.returncode, 0, msg=cp.stderr or cp.stdout)
        services = {line.strip() for line in cp.stdout.splitlines() if line.strip()}

        haproxy_cfg = (REPO_ROOT / "haproxy.cfg").read_text(encoding="utf-8")
        upstreams = set(re.findall(r"server\s+\S+\s+([A-Za-z0-9_.-]+):\d+", haproxy_cfg))
        missing = sorted(upstreams - services)

        self.assertEqual(
            missing,
            [],
            msg="haproxy backends missing in compose: " + ", ".join(missing),
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)

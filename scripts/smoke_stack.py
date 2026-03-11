#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, List, Optional, Tuple


REPO_ROOT = Path(__file__).resolve().parents[1]


def detect_compose_base() -> List[str]:
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
    raise SystemExit("docker compose (plugin) or docker-compose is required")


COMPOSE_BASE = detect_compose_base()


def compose_env() -> Dict[str, str]:
    env = os.environ.copy()
    env.setdefault("TUNNEL_TOKEN", "dummy")
    return env


def run(cmd: List[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=REPO_ROOT,
        env=compose_env(),
        check=check,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def compose(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return run([*COMPOSE_BASE, *args], check=check)


def docker(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return run(["docker", *args], check=check)


def parse_json(text: str):
    text = (text or "").strip()
    if not text:
        return None
    return json.loads(text)


def get_services() -> List[str]:
    cp = compose("config", "--services")
    return [line.strip() for line in cp.stdout.splitlines() if line.strip()]


def get_container_id(service: str) -> Optional[str]:
    cp = compose("ps", "-a", "-q", service, check=False)
    ids = [line.strip() for line in cp.stdout.splitlines() if line.strip()]
    return ids[0] if ids else None


def inspect_json(container_id: str, fmt: str):
    cp = docker("inspect", "--format", fmt, container_id)
    return parse_json(cp.stdout)


def read_api_key(config_path: Path) -> Optional[str]:
    if not config_path.exists():
        return None
    try:
        api_key = ET.parse(config_path).getroot().findtext("ApiKey")
        if api_key and api_key.strip():
            return api_key.strip()
    except Exception:
        return None
    return None


def api_key_for_service(service: str) -> Optional[str]:
    mapping = {
        "sonarr": REPO_ROOT / "sonarr" / "config.xml",
        "radarr": REPO_ROOT / "radarr" / "config.xml",
        "prowlarr": REPO_ROOT / "prowlarr" / "config.xml",
    }
    for token, path in mapping.items():
        if token in service:
            return read_api_key(path)
    return None


def normalize_host(host_ip: str) -> str:
    if host_ip in ("", "0.0.0.0"):
        return "127.0.0.1"
    if host_ip == "::":
        return "::1"
    return host_ip


def host_for_url(host: str) -> str:
    if ":" in host and not host.startswith("["):
        return f"[{host}]"
    return host


def published_tcp_bindings(ports: Dict[str, object]) -> List[Tuple[str, str, int]]:
    bindings: List[Tuple[str, str, int]] = []
    if not isinstance(ports, dict):
        return bindings
    for internal, host_bindings in ports.items():
        if not internal.endswith("/tcp") or not host_bindings:
            continue
        for binding in host_bindings:
            host = normalize_host(binding.get("HostIp", ""))
            port = int(binding["HostPort"])
            bindings.append((internal, host, port))
    return bindings


def preferred_http_binding(service: str, ports: Dict[str, object]) -> Optional[Tuple[str, int]]:
    preferred = {
        "qbittorrent": "8080/tcp",
        "prowlarr": "9696/tcp",
        "radarr": "7878/tcp",
        "sonarr": "8989/tcp",
        "flaresolverr": "8191/tcp",
        "overseerr": "5055/tcp",
        "seerr": "5055/tcp",
        "jackett": "9117/tcp",
    }
    for token, internal in preferred.items():
        if token in service and isinstance(ports, dict) and ports.get(internal):
            binding = ports[internal][0]
            return normalize_host(binding.get("HostIp", "")), int(binding["HostPort"])
    for internal, host_bindings in (ports or {}).items():
        if internal.endswith("/tcp") and host_bindings:
            binding = host_bindings[0]
            return normalize_host(binding.get("HostIp", "")), int(binding["HostPort"])
    return None


def tcp_check(host: str, port: int, timeout: float = 2.5) -> None:
    with socket.create_connection((host, port), timeout=timeout):
        return


def http_get(url: str, *, headers: Optional[Dict[str, str]] = None, timeout: float = 4.0) -> Tuple[int, str]:
    request = urllib.request.Request(url, headers=headers or {}, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            status = getattr(response, "status", response.getcode())
            body = response.read(160).decode("utf-8", "ignore")
            return status, body
    except urllib.error.HTTPError as exc:
        body = exc.read(160).decode("utf-8", "ignore")
        return exc.code, body
    except urllib.error.URLError as exc:
        return -1, str(exc.reason)


def http_probe(service: str, ports: Dict[str, object]) -> Tuple[Optional[bool], str]:
    binding = preferred_http_binding(service, ports)
    if binding is None:
        return None, "no published TCP port to probe"

    host, port = binding
    base_url = f"http://{host_for_url(host)}:{port}"

    if "sonarr" in service or "radarr" in service or "prowlarr" in service:
        headers: Dict[str, str] = {}
        api_key = api_key_for_service(service)
        if api_key:
            headers["X-Api-Key"] = api_key
        status, _ = http_get(f"{base_url}/ping", headers=headers)
        if status == 200:
            return True, f"GET /ping -> {status}"
        root_status, _ = http_get(f"{base_url}/")
        if status in (401, 403) and not api_key and root_status in (200, 301, 302, 401, 403, 404, 405):
            return True, f"GET /ping -> {status} without API key; GET / -> {root_status}"
        return False, f"GET /ping -> {status}; GET / -> {root_status}"

    if "overseerr" in service or "seerr" in service:
        status, _ = http_get(f"{base_url}/api/v1/status")
        if status == 200:
            return True, f"GET /api/v1/status -> {status}"
        return False, f"GET /api/v1/status -> {status}"

    if "qbittorrent" in service:
        status, _ = http_get(f"{base_url}/")
        if status in (200, 301, 302, 401, 403):
            return True, f"GET / -> {status}"
        return False, f"GET / -> {status}"

    if "jackett" in service:
        status, _ = http_get(f"{base_url}/")
        if status in (200, 301, 302, 401, 403):
            return True, f"GET / -> {status}"
        return False, f"GET / -> {status}"

    if "flaresolverr" in service:
        status, _ = http_get(f"{base_url}/")
        if status in (200, 400, 404, 405):
            return True, f"GET / -> {status}"
        return False, f"GET / -> {status}"

    status, _ = http_get(f"{base_url}/")
    if status in (200, 301, 302, 400, 401, 403, 404, 405):
        return True, f"GET / -> {status}"
    return False, f"GET / -> {status}"


def main() -> int:
    failures: List[str] = []

    print("== compose config ==")
    cp = compose("config", "-q", check=False)
    if cp.returncode == 0:
        print("PASS docker compose config -q")
    else:
        print("FAIL docker compose config -q")
        if cp.stderr.strip():
            print(cp.stderr.strip())
        return 1

    services = get_services()
    print(f"services: {', '.join(services)}")

    print("\n== live service checks ==")
    for service in services:
        print(f"\n[{service}]")
        container_id = get_container_id(service)
        if not container_id:
            print("  FAIL container not created")
            failures.append(f"{service}: container not created")
            continue

        state = inspect_json(container_id, "{{json .State}}") or {}
        mounts = inspect_json(container_id, "{{json .Mounts}}") or []
        ports = inspect_json(container_id, "{{json .NetworkSettings.Ports}}") or {}

        status = state.get("Status", "unknown")
        running = bool(state.get("Running"))
        health = (state.get("Health") or {}).get("Status", "none")

        print(f"  container: {container_id[:12]}")
        print(f"  state: {status}")
        print(f"  running: {running}")
        print(f"  docker health: {health}")

        if not running:
            failures.append(f"{service}: container state is {status}")
        if health not in ("none", "healthy"):
            failures.append(f"{service}: docker health is {health}")

        bind_mounts = [
            f'{mount.get("Source")} -> {mount.get("Destination")}'
            for mount in mounts
            if mount.get("Type") == "bind"
        ]
        if bind_mounts:
            print("  bind mounts:")
            for mount_desc in bind_mounts:
                print(f"    - {mount_desc}")
        else:
            print("  bind mounts: none")

        tcp_bindings = published_tcp_bindings(ports)
        if tcp_bindings:
            for internal, host, port in tcp_bindings:
                try:
                    tcp_check(host, port)
                    print(f"  tcp {internal} via {host}:{port}: ok")
                except OSError as exc:
                    print(f"  tcp {internal} via {host}:{port}: FAIL ({exc})")
                    failures.append(f"{service}: tcp {internal} via {host}:{port} failed: {exc}")
        else:
            print("  tcp: no published TCP ports")

        probe_ok, probe_message = http_probe(service, ports)
        if probe_ok is None:
            print(f"  http: skipped ({probe_message})")
        elif probe_ok:
            print(f"  http: ok ({probe_message})")
        else:
            print(f"  http: FAIL ({probe_message})")
            failures.append(f"{service}: http probe failed: {probe_message}")

    print("\n== summary ==")
    if failures:
        print("FAIL")
        for item in failures:
            print(f" - {item}")
        return 1

    print("PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

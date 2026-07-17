#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
import shutil
import socket
import subprocess
import tempfile
import threading
import time
from contextlib import AbstractContextManager
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import requests
import yaml


RUN_SERVICES_ROOT = Path(__file__).resolve().parents[1]


def resolve_workspace_root() -> Path:
    raw = os.environ.get("CHUMMER_WORKSPACE_ROOT", "").strip()
    if raw:
        return Path(raw).expanduser()

    candidates = [
        RUN_SERVICES_ROOT.parent,
        Path("/docker/chummercomplete"),
    ]
    for candidate in candidates:
        if (candidate / "chummer-presentation").is_dir() and (candidate / "chummer-core-engine").is_dir():
            return candidate
    return candidates[0]


WORKSPACE_ROOT = resolve_workspace_root()
CHUMMER6_ROOT = WORKSPACE_ROOT / "Chummer6"
CHUMMER_PLAY_ROOT = WORKSPACE_ROOT / "chummer-play"
DEFAULT_COMPLETION_ROOT = WORKSPACE_ROOT / "_completion" / "chummer6_absolute_completion"
DEFAULT_BASE_URL = os.environ.get("CHUMMER_COMPLETION_BASE_URL", "http://127.0.0.1:5099").rstrip("/")
REQUEST_TIMEOUT_SECONDS = 30
LOCAL_HUB_READY_TIMEOUT_SECONDS = 90
_LOCAL_HUB_BUILD_LOCK = threading.Lock()
_LOCAL_HUB_BUILD_READY = False
_LOCAL_PLAY_BUILD_LOCK = threading.Lock()
_LOCAL_PLAY_BUILD_READY = False


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def ensure_completion_root() -> Path:
    raw = os.environ.get("CHUMMER_COMPLETION_DIR", "").strip()
    root = Path(raw) if raw else DEFAULT_COMPLETION_ROOT
    root.mkdir(parents=True, exist_ok=True)
    return root


def completion_path(*parts: str) -> Path:
    return ensure_completion_root().joinpath(*parts)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def write_yaml(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.rstrip() + "\n", encoding="utf-8")


def read_yaml(path: Path) -> Any:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def pick_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        sock.listen(1)
        return int(sock.getsockname()[1])


def wait_for_http(base_url: str, path: str = "/", *, accepted: tuple[int, ...] = (200, 302), timeout_seconds: int = 60) -> None:
    deadline = time.time() + timeout_seconds
    last_error = "no response"
    while time.time() < deadline:
        try:
            response = requests.get(f"{base_url.rstrip('/')}{path}", timeout=5, allow_redirects=False)
            if response.status_code in accepted:
                return
            last_error = f"status {response.status_code}"
        except Exception as exc:
            last_error = str(exc)
        time.sleep(1)

    raise RuntimeError(f"{base_url}{path} did not become ready within {timeout_seconds}s: {last_error}")


def extract_antiforgery_token(html: str) -> str:
    match = re.search(
        r'name="__RequestVerificationToken"\s+type="hidden"\s+value="([^"]+)"',
        html,
        re.IGNORECASE,
    )
    if not match:
        raise RuntimeError("anti-forgery token not found in page")
    return match.group(1)


def extract_first_select_option(html: str, select_name: str) -> str:
    select_match = re.search(
        rf'<select[^>]*name="{re.escape(select_name)}"[^>]*>(.*?)</select>',
        html,
        re.IGNORECASE | re.DOTALL,
    )
    if not select_match:
        raise RuntimeError(f"select {select_name!r} not found in page")

    option_match = re.search(
        r'<option[^>]*value="([^"]+)"[^>]*>',
        select_match.group(1),
        re.IGNORECASE | re.DOTALL,
    )
    if not option_match:
        raise RuntimeError(f"select {select_name!r} did not contain a value option")

    return option_match.group(1)


def slugify_route(route: str) -> str:
    cleaned = route.strip("/") or "index"
    return re.sub(r"[^a-z0-9]+", "-", cleaned.lower()).strip("-") or "index"


def tail_text_file(path: Path, *, max_lines: int = 120) -> str:
    if not path.exists():
        return ""

    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return ""

    if len(lines) > max_lines:
        lines = lines[-max_lines:]

    return "\n".join(lines).strip()


def ensure_local_hub_build() -> None:
    global _LOCAL_HUB_BUILD_READY

    if _LOCAL_HUB_BUILD_READY:
        return

    with _LOCAL_HUB_BUILD_LOCK:
        if _LOCAL_HUB_BUILD_READY:
            return

        result = subprocess.run(
            ["dotnet", "build", "Chummer.Run.Api/Chummer.Run.Api.csproj", "-nologo"],
            cwd=RUN_SERVICES_ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        if result.returncode != 0:
            build_output = (result.stdout or "").strip()
            excerpt = "\n".join(build_output.splitlines()[-120:])
            message = "local hub prebuild failed"
            if excerpt:
                message = f"{message}\n{excerpt}"
            raise RuntimeError(message)

        _LOCAL_HUB_BUILD_READY = True


def ensure_local_play_build() -> None:
    global _LOCAL_PLAY_BUILD_READY

    if _LOCAL_PLAY_BUILD_READY:
        return

    with _LOCAL_PLAY_BUILD_LOCK:
        if _LOCAL_PLAY_BUILD_READY:
            return

        result = subprocess.run(
            ["bash", "scripts/ai/with-package-plane.sh", "build", "src/Chummer.Play.Web/Chummer.Play.Web.csproj", "-nologo"],
            cwd=CHUMMER_PLAY_ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        if result.returncode != 0:
            build_output = (result.stdout or "").strip()
            excerpt = "\n".join(build_output.splitlines()[-120:])
            message = "local play prebuild failed"
            if excerpt:
                message = f"{message}\n{excerpt}"
            raise RuntimeError(message)

        _LOCAL_PLAY_BUILD_READY = True


class TokenIdentityStub(AbstractContextManager["TokenIdentityStub"]):
    def __init__(
        self,
        *,
        access_token: str = "package-proof-token",
        subject_id: str = "subject.package-proof",
        display_name: str = "Package Proof Runner",
        email: str = "package-proof@chummer.run",
        roles: list[str] | None = None,
    ) -> None:
        self.access_token = access_token
        self.subject_id = subject_id
        self.display_name = display_name
        self.email = email
        self.roles = roles or ["member"]
        self.port = pick_free_port()
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def __enter__(self) -> "TokenIdentityStub":
        stub = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, format: str, *args: object) -> None:
                return

            def _send(self, status_code: int, payload: dict[str, Any]) -> None:
                body = json.dumps(payload).encode("utf-8")
                self.send_response(status_code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_POST(self) -> None:  # noqa: N802
                if self.path != "/api/v1/identity/introspect":
                    self._send(404, {"error": "not_found"})
                    return

                length = int(self.headers.get("Content-Length", "0") or "0")
                raw_body = self.rfile.read(length).decode("utf-8") if length else "{}"
                try:
                    payload = json.loads(raw_body or "{}")
                except json.JSONDecodeError:
                    self._send(400, {"error": "bad_json"})
                    return

                self._send(
                    200,
                    {
                        "active": True,
                        "sessionId": "session.package-proof",
                        "subjectId": stub.subject_id,
                        "roles": stub.roles,
                        "expiresAtUtc": (datetime.now(timezone.utc) + timedelta(hours=4)).isoformat(),
                    },
                )

            def do_GET(self) -> None:  # noqa: N802
                prefix = "/api/v1/identity/subjects/"
                if not self.path.startswith(prefix):
                    self._send(404, {"error": "not_found"})
                    return

                subject_id = self.path[len(prefix):]
                if subject_id != stub.subject_id:
                    self._send(404, {"error": "unknown_subject"})
                    return

                self._send(
                    200,
                    {
                        "subjectId": stub.subject_id,
                        "displayName": stub.display_name,
                        "email": stub.email,
                        "roles": stub.roles,
                        "updatedAtUtc": now_iso(),
                    },
                )

        self._server = ThreadingHTTPServer(("127.0.0.1", self.port), Handler)
        self._thread = threading.Thread(target=self._server.serve_forever, name="package-proof-identity-stub", daemon=True)
        self._thread.start()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
        if self._thread is not None:
            self._thread.join(timeout=5)


class StaticHtmlStub(AbstractContextManager["StaticHtmlStub"]):
    def __init__(self, *, html: str, content_type: str = "text/html; charset=utf-8") -> None:
        self.html = html
        self.content_type = content_type
        self.port = pick_free_port()
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def __enter__(self) -> "StaticHtmlStub":
        stub = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, format: str, *args: object) -> None:
                return

            def do_GET(self) -> None:  # noqa: N802
                body = stub.html.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", stub.content_type)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        self._server = ThreadingHTTPServer(("127.0.0.1", self.port), Handler)
        self._thread = threading.Thread(target=self._server.serve_forever, name="static-html-stub", daemon=True)
        self._thread.start()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
        if self._thread is not None:
            self._thread.join(timeout=5)


class LocalHubApp(AbstractContextManager["LocalHubApp"]):
    def __init__(
        self,
        *,
        identity_base_url: str | None = None,
        extra_env: dict[str, str] | None = None,
        no_build: bool = False,
        startup_timeout_seconds: int | None = None,
    ) -> None:
        self.identity_base_url = identity_base_url
        self.extra_env = dict(extra_env or {})
        self.no_build = no_build
        self.startup_timeout_seconds = startup_timeout_seconds or int(os.environ.get("CHUMMER_LOCAL_HUB_START_TIMEOUT_SECONDS", "180"))
        self.port = pick_free_port()
        self.base_url = f"http://127.0.0.1:{self.port}"
        self._process: subprocess.Popen[str] | None = None
        self._temp_root: Path | None = None
        self._log_path: Path | None = None
        self._log_handle: Any | None = None

    @property
    def log_path(self) -> Path | None:
        return self._log_path

    @staticmethod
    def _debug_binary_available() -> bool:
        project_root = RUN_SERVICES_ROOT / "Chummer.Run.Api"
        candidates = [
            project_root / "bin" / "Debug" / "net10.0" / "Chummer.Run.Api",
            project_root / "bin" / "Debug" / "net10.0" / "Chummer.Run.Api.exe",
        ]
        return any(candidate.is_file() for candidate in candidates)

    def _should_skip_build(self) -> bool:
        if not self.no_build:
            return False
        strict = os.environ.get("CHUMMER_LOCAL_HUB_STRICT_NO_BUILD", "").strip().lower()
        if strict in {"1", "true", "yes", "on"}:
            return True
        return self._debug_binary_available()

    def __enter__(self) -> "LocalHubApp":
        ensure_local_hub_build()

        temp_root = Path(tempfile.mkdtemp(prefix="chummer-local-hub-"))
        self._temp_root = temp_root
        self._log_path = temp_root / "hub.log"

        env = os.environ.copy()
        env["ASPNETCORE_ENVIRONMENT"] = "Development"
        env["ASPNETCORE_URLS"] = self.base_url
        env["TMPDIR"] = str(temp_root)
        env["CHUMMER_PUBLIC_CANON_ROOT"] = str(RUN_SERVICES_ROOT)
        if self.identity_base_url:
            env["IDENTITY_SERVICE_BASE_URL"] = self.identity_base_url
        env.update(self.extra_env)

        command = [
            "dotnet",
            "run",
            "--project",
            "Chummer.Run.Api/Chummer.Run.Api.csproj",
            "-nologo",
            "--no-launch-profile",
            "--no-build",
            "--no-restore",
        ]
        if self._should_skip_build():
            command.append("--no-build")

        self._log_handle = self._log_path.open("w", encoding="utf-8")
        self._process = subprocess.Popen(
            command,
            cwd=RUN_SERVICES_ROOT,
            env=env,
            stdout=self._log_handle,
            stderr=subprocess.STDOUT,
            text=True,
        )
        try:
            wait_for_http(self.base_url, "/login", accepted=(200,), timeout_seconds=self.startup_timeout_seconds)
        except Exception as exc:
            raise RuntimeError(f"{exc}\nLocalHubApp log tail:\n{self._read_log_tail()}") from exc
        return self

    def _stop_process(self) -> None:
        if self._process is not None:
            self._process.terminate()
            try:
                self._process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self._process.kill()
                self._process.wait(timeout=10)
        if self._log_handle is not None:
            self._log_handle.close()
        if self._temp_root is not None:
            self._temp_root.cleanup()

    def _read_log_tail(self, line_count: int = 80) -> str:
        if self._log_handle is not None:
            self._log_handle.flush()
        if self._log_path is None or not self._log_path.is_file():
            return "(local hub log is unavailable)"
        lines = self._log_path.read_text(encoding="utf-8", errors="replace").splitlines()
        return "\n".join(lines[-line_count:]) or "(local hub log is empty)"

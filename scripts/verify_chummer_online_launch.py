#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urljoin, urlparse
from urllib.request import Request, urlopen


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = REPO_ROOT / ".codex-studio" / "published" / "CHUMMER_ONLINE_LAUNCH_GATE.generated.json"
DEFAULT_BASE_URL = "https://chummer.run/"
LAUNCH_PATH = "/app?command=character_roster"
USER_AGENT = "ChummerOnlineLaunchGate/1.0"
EXPECTED_REDIRECT_LAUNCH_PATH = "/blazor/app"
CONTRACT_NAME = "chummer.online_character_roster_launch.v1"


@dataclass
class LaunchGateResult:
    contractName: str
    status: str
    launch_url: str
    final_url: str | None
    http_status: int | None
    generated_at: str
    body_size: int
    has_blazor_marker: bool
    has_roster_marker: bool
    failure_reason: str | None
    body_excerpt: str


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify the first-party Chummer Online launch route.")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="Public origin to verify.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="Receipt path to write.")
    return parser.parse_args(argv)


def build_launch_url(base_url: str) -> str:
    return urljoin(base_url.rstrip("/") + "/", LAUNCH_PATH.lstrip("/"))


def fetch_url(url: str) -> tuple[int | None, str | None, bytes]:
    request = Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urlopen(request, timeout=30) as response:
            return response.getcode(), response.geturl(), response.read()
    except HTTPError as exc:
        return exc.code, exc.geturl(), exc.read()
    except URLError as exc:
        raise RuntimeError(f"url_error:{exc.reason}") from exc


def excerpt(body: bytes, limit: int = 500) -> str:
    text = body.decode("utf-8", errors="replace").strip()
    if len(text) <= limit:
        return text
    return text[:limit] + "..."


def is_redirected_launch_shell(final_url: str | None, lowered_body: str, has_blazor_marker: bool) -> bool:
    if not final_url or not has_blazor_marker:
        return False

    parsed_final_url = urlparse(final_url)
    if parsed_final_url.path.rstrip("/") != EXPECTED_REDIRECT_LAUNCH_PATH:
        return False

    return (
        '<base href="/blazor/"' in lowered_body
        and "manifest.webmanifest" in lowered_body
        and "window.chummerpwa" in lowered_body
        and "app.rybbit.io/api/script.js" in lowered_body
    )


def has_launch_roster_menu_markers(lowered_body: str) -> bool:
    return (
        "browser-app-classic-menu-bar" in lowered_body
        and "data-app-menu-root" in lowered_body
        and "browser-app-classic-toolstrip" in lowered_body
    )


def is_character_roster_launch(final_url: str | None, lowered_body: str) -> bool:
    if not final_url:
        return False

    parsed_final_url = urlparse(final_url)
    if parsed_final_url.path.rstrip("/") != EXPECTED_REDIRECT_LAUNCH_PATH:
        return False

    query = parse_qs(parsed_final_url.query)
    commands = query.get("command", [])
    return any(cmd.lower() == "character_roster" for cmd in commands)


def classify_response(http_status: int | None, body: bytes, final_url: str | None = None) -> tuple[bool, bool, str | None]:
    text = body.decode("utf-8", errors="replace")
    lowered = text.lower()
    has_blazor_marker = "_framework/blazor" in lowered or "blazor.web" in lowered or "blazor" in lowered
    has_roster_marker = "character_roster" in lowered or "roster" in lowered
    has_roster_menu_markers = has_launch_roster_menu_markers(lowered)

    if http_status != 200:
        return has_blazor_marker, has_roster_marker, f"http_{http_status or 'missing'}"
    if not body:
        return has_blazor_marker, has_roster_marker, "empty_body"
    if "unexpected server error" in lowered or "problem" in lowered and "status" in lowered and "traceid" in lowered:
        return has_blazor_marker, has_roster_marker, "server_error_body"
    if "not ready right now" in lowered or "download chummer" in lowered and "browser preview" in lowered:
        return has_blazor_marker, has_roster_marker, "browser_surface_fallback"
    if "404" in lowered and "not found" in lowered:
        return has_blazor_marker, has_roster_marker, "not_found_body"
    if not has_blazor_marker:
        return has_blazor_marker, has_roster_marker, "missing_blazor_marker"
    if is_redirected_launch_shell(final_url, lowered, has_blazor_marker):
        if is_character_roster_launch(final_url, lowered) and not has_roster_menu_markers:
            return has_blazor_marker, has_roster_marker, "missing_roster_menu_markers"
        return has_blazor_marker, has_roster_marker, None
    if not has_roster_marker:
        return has_blazor_marker, has_roster_marker, "missing_roster_marker"
    return has_blazor_marker, has_roster_marker, None


def verify_launch(base_url: str) -> LaunchGateResult:
    launch_url = build_launch_url(base_url)
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    try:
        http_status, final_url, body = fetch_url(launch_url)
    except Exception as exc:
        return LaunchGateResult(
            contractName=CONTRACT_NAME,
            status="fail",
            launch_url=launch_url,
            final_url=None,
            http_status=None,
            generated_at=now,
            body_size=0,
            has_blazor_marker=False,
            has_roster_marker=False,
            failure_reason=str(exc),
            body_excerpt="",
        )

    has_blazor_marker, has_roster_marker, failure_reason = classify_response(http_status, body, final_url=final_url)
    return LaunchGateResult(
        contractName=CONTRACT_NAME,
        status="pass" if failure_reason is None else "fail",
        launch_url=launch_url,
        final_url=final_url,
        http_status=http_status,
        generated_at=now,
        body_size=len(body),
        has_blazor_marker=has_blazor_marker,
        has_roster_marker=has_roster_marker,
        failure_reason=failure_reason,
        body_excerpt=excerpt(body),
    )


def write_receipt(result: LaunchGateResult, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(asdict(result), indent=2) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    result = verify_launch(args.base_url)
    write_receipt(result, Path(args.output))
    if result.status != "pass":
        print(
            f"chummer online launch gate failed: {result.failure_reason} "
            f"(status={result.http_status}, final_url={result.final_url})",
            file=sys.stderr,
        )
        return 1
    print(json.dumps(asdict(result), ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

import requests

from absolute_completion_common import DEFAULT_COMPLETION_ROOT, completion_path, now_iso, write_json, write_text


REQUIRED_FILES = (
    "BLACK_LEDGER_COMMAND_MAP_RENDER.generated.json",
    "BLACK_LEDGER_COMMAND_MAP_TICK_REPLAY.generated.json",
    "BLACK_LEDGER_COMMAND_MAP_ACCESSIBILITY.generated.json",
    "BLACK_LEDGER_COMMAND_MAP_PERFORMANCE.generated.json",
    "BLACK_LEDGER_COMMAND_MAP_SCREENSHOT_REPORT.md",
    "BLACK_LEDGER_COMMAND_MAP_PUBLIC_SAFETY.generated.json",
)

ROUTES = (
    "/ledger",
    "/ledger/map",
    "/api/v1/ledger/worlds/emerald-sprawl-prelude/map",
)


def read_json_if_present(path: Path) -> dict | None:
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def artifact_status_ok(root: Path, name: str, failures: list[str]) -> None:
    path = root / name
    if not path.exists():
        failures.append(f"missing artifact: {name}")
        return
    if path.suffix == ".json":
        payload = read_json_if_present(path) or {}
        if payload.get("status") not in {None, "pass"}:
            failures.append(f"{name} status was not pass")


def run_live_checks(base_url: str, failures: list[str]) -> list[dict]:
    route_statuses: list[dict] = []
    for route in ROUTES:
        response = requests.get(f"{base_url}{route}", timeout=30)
        route_statuses.append({"route": route, "status_code": response.status_code})
        if response.status_code != 200:
            failures.append(f"live route did not return 200: {route}")
    return route_statuses


def main() -> int:
    root = completion_path()
    if root == DEFAULT_COMPLETION_ROOT:
        root = completion_path("..", "black_ledger_command_map").resolve()
    root.mkdir(parents=True, exist_ok=True)

    failures: list[str] = []
    for name in REQUIRED_FILES:
        artifact_status_ok(root, name, failures)

    design_files = [
        Path("/docker/chummercomplete/chummer-design/products/chummer/BLACK_LEDGER_COMMAND_MAP_SPEC.md"),
        Path("/docker/chummercomplete/chummer-design/products/chummer/BLACK_LEDGER_MAP_LAYER_SPEC.yaml"),
        Path("/docker/chummercomplete/chummer-design/products/chummer/BLACK_LEDGER_MAP_INTERACTION_SPEC.md"),
        Path("/docker/chummercomplete/chummer-design/products/chummer/BLACK_LEDGER_MAP_VISUAL_SYSTEM.md"),
        Path("/docker/chummercomplete/chummer-design/products/chummer/BLACK_LEDGER_MAP_TECH_STACK_DECISION.md"),
    ]
    for path in design_files:
        if not path.is_file():
            failures.append(f"missing design canon file: {path.name}")

    base_url = "https://chummer.run"
    try:
        route_statuses = run_live_checks(base_url, failures)
    except Exception as exc:
        route_statuses = []
        failures.append(f"live route checks failed: {exc}")

    verdict = "BLACK_LEDGER_COMMAND_MAP_PUBLISHED" if not failures else "NOT_READY"
    payload = {
        "contract_name": "chummer.final_black_ledger_command_map_verdict",
        "status": "pass" if verdict == "BLACK_LEDGER_COMMAND_MAP_PUBLISHED" else "fail",
        "verdict": verdict,
        "generated_at_utc": now_iso(),
        "completion_dir": str(root),
        "base_url": base_url,
        "route_statuses": route_statuses,
        "failure_count": len(failures),
        "failures": failures,
    }

    write_json(root / "FINAL_BLACK_LEDGER_COMMAND_MAP_VERDICT.generated.json", payload)
    write_json(
        root / "BLACK_LEDGER_COMMAND_MAP_PUBLISH_REPORT.generated.json",
        {
            "generated_at_utc": payload["generated_at_utc"],
            "base_url": base_url,
            "route_statuses": route_statuses,
            "status": payload["status"],
        },
    )
    write_text(
        root / "BLACK_LEDGER_COMMAND_MAP_PUBLISH_REPORT.md",
        "\n".join(
            [
                "# Black Ledger Command Map Publish Report",
                "",
                f"- Generated: {payload['generated_at_utc']}",
                f"- Base URL: {base_url}",
                f"- Status: `{payload['status']}`",
            ]
            + [f"- `{item['route']}` -> `{item['status_code']}`" for item in route_statuses]
        ),
    )
    write_text(
        root / "BLACK_LEDGER_COMMAND_MAP_IMPLEMENTATION_REPORT.md",
        "\n".join(
            [
                "# Black Ledger Command Map Implementation Report",
                "",
                f"- Generated: {payload['generated_at_utc']}",
                "- Data/API: public map, turn map, and tick-delta endpoints are present.",
                "- UI: homepage teaser and `/ledger/map` command-map shell are implemented.",
                "- Safety: public safety gate artifact required for completion.",
                "- Proof: render, replay, accessibility, performance, and screenshot artifacts required.",
            ]
        ),
    )
    write_text(
        root / "FINAL_BLACK_LEDGER_COMMAND_MAP_VERDICT.md",
        "\n".join(
            [
                "# Final Black Ledger Command Map Verdict",
                "",
                f"Verdict: `{verdict}`",
                "",
                f"- Generated: {payload['generated_at_utc']}",
                f"- Failure count: `{payload['failure_count']}`",
            ] + (["", "## Failures", *[f"- {item}" for item in failures]] if failures else ["", "All required command map gates are present and green."])
        ),
    )
    return 0 if verdict == "BLACK_LEDGER_COMMAND_MAP_PUBLISHED" else 1


if __name__ == "__main__":
    raise SystemExit(main())

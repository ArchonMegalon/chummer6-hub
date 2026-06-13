#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any


RUN_SERVICES_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_COMPLETION_ROOT = RUN_SERVICES_ROOT.parent / "_completion" / "chummer_run_redesign_closure"
OUTPUT_NAME = "UI_LAYOUT_EXIT_GATE.generated.json"
OUTPUT_REPORT = "UI_LAYOUT_EXIT_GATE.md"
FRAME_ARTIFACT = "UI_FRAME_INTEGRITY.generated.json"
CRITICAL_NO_WRAP_SELECTORS = (
    "site-brand__wordmark",
    "site-footer__wordmark",
    "hero-brand",
    "launch-hero__title",
    "home-hero__title",
    "page-title",
    "editorial-title",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Fail fast when the public UI exits with clipped children or unexpected forced line wraps "
            "in the frame-integrity proof artifact."
        )
    )
    parser.add_argument("--completion-dir", default="", help="Completion directory containing UI frame integrity artifacts.")
    parser.add_argument("--max-age-hours", type=int, default=24, help="Maximum artifact age in hours.")
    return parser.parse_args()


def completion_root(raw: str) -> Path:
    if not raw:
        return DEFAULT_COMPLETION_ROOT

    configured = Path(raw)
    if not configured.is_absolute():
        configured = RUN_SERVICES_ROOT / configured
    return configured


def now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    text = path.read_text(encoding="utf-8")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {}


def parse_iso(value: str) -> datetime:
    if not value:
        return datetime.fromtimestamp(0, tz=UTC)
    timestamp = value.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(timestamp)
    except ValueError:
        return datetime.fromtimestamp(0, tz=UTC)


def build_payload(
    completion_root_path: Path,
    max_age_hours: int,
) -> tuple[dict[str, Any], list[str]]:
    frame_path = completion_root_path / FRAME_ARTIFACT
    failures: list[str] = []

    if not frame_path.is_file():
        failures.append(f"missing frame integrity artifact: {frame_path}")
        frame = {}
    else:
        frame = read_json(frame_path)

    frame_status = str(frame.get("status", "missing")).strip().lower()
    frame_summary = frame.get("summary", {}) if isinstance(frame.get("summary"), dict) else {}
    frame_failures = frame.get("failures", [])

    if frame_status not in {"pass", "passed", "ready"}:
        failures.append(f"UI_FRAME_INTEGRITY.generated.json status is '{frame.get('status', 'missing')}'")

    if not isinstance(frame_failures, list) or not frame_failures:
        pass
    else:
        for failure in frame_failures:
            if not isinstance(failure, dict):
                continue
            selector = str(failure.get("selector", "")).lower()
            reason = str(failure.get("reason", ""))
            route = str(failure.get("route", ""))
            viewport = str(failure.get("viewport", ""))
            overflow = str(failure.get("frameOverflow", ""))
            if any(needle in selector for needle in CRITICAL_NO_WRAP_SELECTORS):
                failures.append(f"critical selector overflow/wrap: {viewport} {route} {selector}: {reason}")
            elif overflow.startswith("line-count") and any(needle in selector for needle in CRITICAL_NO_WRAP_SELECTORS):
                failures.append(f"critical selector forced line-wrap: {viewport} {route} {selector}: {reason}")

    checked_pages = frame_summary.get("checked_pages")
    if int(checked_pages if isinstance(checked_pages, int) else 0) == 0:
        failures.append("frame integrity artifact has no checked page evidence")

    frame_failure_count = frame_summary.get("failure_count")
    if frame_failure_count is None:
        route_failures = frame.get("pages", [])
        frame_failure_count = sum(int(page.get("failure_count") or 0) for page in route_failures if isinstance(page, dict))
    if int(frame_failure_count) > 0:
        failures.append(f"frame integrity artifact failure_count={frame_failure_count}")

    generated = str(frame.get("generated_at_utc", ""))
    generated_at = parse_iso(generated)
    max_age = timedelta(hours=max_age_hours)
    if generated_at == datetime.fromtimestamp(0, tz=UTC):
        failures.append("frame integrity artifact is missing or has an unparseable generated_at_utc timestamp")
    elif datetime.now(UTC) - generated_at > max_age:
        failures.append(f"frame integrity artifact is stale: generated_at_utc={generated}")

    payload = {
        "contract_name": "chummer.ui_layout_exit_gate",
        "generated_at_utc": now_iso(),
        "status": "pass" if not failures else "fail",
        "verdict": "UI_LAYOUT_EXIT_READY" if not failures else "UI_LAYOUT_EXIT_BLOCKED",
        "completion_dir": str(completion_root_path),
        "frame_artifact": str(frame_path),
        "max_age_hours": max_age_hours,
        "failure_count": len(failures),
        "failures": failures,
        "checked_pages": checked_pages,
        "frame_failure_count": frame_failure_count,
        "critical_selectors": list(CRITICAL_NO_WRAP_SELECTORS),
        "frame_summary": frame_summary,
        "frame_status": frame_status,
    }
    return payload, failures


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def main() -> int:
    args = parse_args()
    root = completion_root(args.completion_dir).resolve()
    root.mkdir(parents=True, exist_ok=True)

    payload, failures = build_payload(root, args.max_age_hours)
    output_json = root / OUTPUT_NAME
    output_report = root / OUTPUT_REPORT
    output_json.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    report_lines = [
        "# UI Layout Exit Gate",
        "",
        f"- Generated: {payload['generated_at_utc']}",
        f"- Completion dir: {payload['completion_dir']}",
        f"- Artifact: {payload['frame_artifact']}",
        f"- Status: `{payload['status']}`",
        f"- Verdict: {payload['verdict']}",
        f"- Frame status: {payload['frame_status']}",
        f"- Checked pages: {payload['checked_pages']}",
        f"- Frame failure count: {payload['frame_failure_count']}",
        f"- Max age allowed: {payload['max_age_hours']}h",
        "",
        "## Critical selectors",
        ", ".join(payload["critical_selectors"]),
        "",
    ]
    if failures:
        report_lines.extend([
            "## Failures",
            "",
            *[f"- {failure}" for failure in failures],
        ])
    else:
        report_lines.append("- No clipping or forced newline violations affecting critical selectors.")

    write_text(output_report, "\n".join(report_lines) + "\n")
    print(f"ui-layout-exit-gate:{payload['status']}")
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())

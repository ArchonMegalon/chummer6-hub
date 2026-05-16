#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path
from urllib.parse import urlparse

from absolute_completion_common import completion_path, now_iso, write_json, write_text


CONFIG_KEYS = (
    "FLEET_INTERNAL_API_TOKEN",
    "CHUMMER_BLACK_LEDGER_NEWS_EMAIL_ENABLED",
    "CHUMMER_BLACK_LEDGER_NEWS_EMAIL_POLICY",
    "CHUMMER_BLACK_LEDGER_NEWS_EA_API_TOKEN",
    "CHUMMER_BLACK_LEDGER_NEWS_EA_PRINCIPAL_ID",
    "CHUMMER_BLACK_LEDGER_NEWS_EA_BINDING_ID",
    "CHUMMER_BLACK_LEDGER_NEWS_EA_BASE_URL",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check Black Ledger tick-news runtime configuration without leaking secrets.")
    parser.add_argument("--base-url", default="", help="Optional live Hub base URL. When omitted, checks the current process environment.")
    return parser.parse_args()


def resolve_env(base_url: str) -> dict[str, str]:
    if not base_url:
        return dict(os.environ)
    host = urlparse(base_url).hostname or ""
    if host not in {"127.0.0.1", "localhost", "chummer.run"}:
        raise RuntimeError(f"unsupported base URL for config inspection: {base_url}")
    return inspect_container_env("chummer6-hub-chummer-portal-1")


def inspect_container_env(container_name: str) -> dict[str, str]:
    result = subprocess.run(
        ["docker", "inspect", "--format", "{{range .Config.Env}}{{println .}}{{end}}", container_name],
        check=True,
        capture_output=True,
        text=True,
    )
    env: dict[str, str] = {}
    for line in result.stdout.splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        env[key] = value
    return env


def summarize(env: dict[str, str], base_url: str) -> dict[str, object]:
    rows = []
    for key in CONFIG_KEYS:
        value = env.get(key, "").strip()
        row: dict[str, object] = {
            "key": key,
            "present": bool(value),
        }
        if key.endswith("_ENABLED"):
            row["enabled"] = value.lower() == "true"
        elif key.endswith("_POLICY"):
            row["value"] = value or "unset"
        elif key.endswith("_BASE_URL"):
            row["value"] = value or "unset"
        rows.append(row)

    by_key = {row["key"]: row for row in rows}
    enabled = bool(by_key["CHUMMER_BLACK_LEDGER_NEWS_EMAIL_ENABLED"]["present"]) and bool(by_key["CHUMMER_BLACK_LEDGER_NEWS_EMAIL_ENABLED"].get("enabled"))
    policy_value = str(by_key["CHUMMER_BLACK_LEDGER_NEWS_EMAIL_POLICY"].get("value", "unset"))
    ea_ready = all(bool(by_key[key]["present"]) for key in (
        "CHUMMER_BLACK_LEDGER_NEWS_EA_API_TOKEN",
        "CHUMMER_BLACK_LEDGER_NEWS_EA_PRINCIPAL_ID",
        "CHUMMER_BLACK_LEDGER_NEWS_EA_BINDING_ID",
    ))
    internal_ready = bool(by_key["FLEET_INTERNAL_API_TOKEN"]["present"])
    ok = enabled and policy_value != "disabled" and ea_ready and internal_ready
    return {
        "contract_name": "chummer.black_ledger_tick_news_config_check",
        "status": "pass" if ok else "fail",
        "generated_at_utc": now_iso(),
        "base_url": base_url,
        "rows": rows,
        "checks": {
            "email_enabled": enabled,
            "policy_active": policy_value != "disabled" and policy_value != "unset",
            "ea_dispatch_ready": ea_ready,
            "internal_api_ready": internal_ready,
        },
    }


def emit(summary: dict[str, object]) -> int:
    write_json(completion_path("BLACK_LEDGER_TICK_NEWS_CONFIG_CHECK.generated.json"), summary)
    lines = [
        "# Black Ledger tick-news config check",
        "",
        f"- Generated: {summary['generated_at_utc']}",
        f"- Base URL: {summary['base_url'] or 'process-env'}",
        f"- Status: `{summary['status']}`",
        "",
        "## Checks",
    ]
    checks = summary["checks"]
    assert isinstance(checks, dict)
    for key, value in checks.items():
        lines.append(f"- `{key}`: `{value}`")
    lines.extend(["", "## Variables"])
    rows = summary["rows"]
    assert isinstance(rows, list)
    for row in rows:
        assert isinstance(row, dict)
        detail = f"present={row['present']}"
        if "enabled" in row:
            detail += f", enabled={row['enabled']}"
        if "value" in row:
            detail += f", value={row['value']}"
        lines.append(f"- `{row['key']}`: {detail}")
    write_text(completion_path("BLACK_LEDGER_TICK_NEWS_CONFIG_CHECK.md"), "\n".join(lines))
    print(json.dumps(summary, indent=2))
    return 0 if summary["status"] == "pass" else 1


def main() -> int:
    args = parse_args()
    summary = summarize(resolve_env(args.base_url), args.base_url.rstrip("/"))
    return emit(summary)


if __name__ == "__main__":
    raise SystemExit(main())

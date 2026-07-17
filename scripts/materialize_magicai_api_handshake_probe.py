#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


RUN_SERVICES_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_ROOT = Path(__file__).resolve().parent
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))

from magicai_pool_registry import env_assignments as shared_env_assignments
from magicai_pool_registry import magicai_api_ready_slots as shared_magicai_api_ready_slots

DEFAULT_OUTPUT = RUN_SERVICES_ROOT / ".codex-studio" / "published" / "MAGICAI_API_HANDSHAKE.generated.json"
DEFAULT_ENDPOINT = "https://api.omagic.ai/api/schema/public/?format=json"
DEFAULT_ORIGIN = "https://platform.omagic.ai"
DEFAULT_REFERER = "https://platform.omagic.ai/platform/docs"
USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36"
CONTRACT_NAME = "chummer.magicai_api_handshake_probe.v1"


def now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest() if value else ""


def env_assignments(path: Path) -> dict[str, str]:
    return shared_env_assignments(path)


def magicai_api_ready_slots(repo_root: Path) -> dict[str, str]:
    return shared_magicai_api_ready_slots(env_assignments(repo_root / ".env"))


def choose_slot(repo_root: Path, requested_slot: str | None = None) -> tuple[str | None, str | None]:
    ready = magicai_api_ready_slots(repo_root)
    if requested_slot is not None:
        alias = requested_slot.strip().zfill(2)
        return alias, ready.get(alias)
    if not ready:
        return None, None
    alias = sorted(ready)[0]
    return alias, ready[alias]


def build_request(endpoint: str, api_key: str) -> urllib.request.Request:
    return urllib.request.Request(
        endpoint,
        headers={
            "Accept": "application/json",
            "Origin": DEFAULT_ORIGIN,
            "Referer": DEFAULT_REFERER,
            "User-Agent": USER_AGENT,
            "X-Api-Key": api_key,
        },
        method="GET",
    )


def fetch_probe(request: urllib.request.Request, timeout: int = 60) -> dict[str, Any]:
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8", errors="replace")
            headers = dict(response.headers.items())
            return {
                "status_code": response.status,
                "headers": headers,
                "body": body,
                "url": response.geturl(),
            }
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        return {
            "status_code": exc.code,
            "headers": dict(exc.headers.items()),
            "body": body,
            "url": exc.geturl(),
        }


def summarize_schema_body(body: str) -> dict[str, Any]:
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return {
            "json": False,
            "body_sha256": sha256_text(body),
            "body_size_bytes": len(body.encode("utf-8")),
            "body_excerpt": body[:280],
        }

    paths = payload.get("paths") if isinstance(payload, dict) else {}
    return {
        "json": True,
        "body_sha256": sha256_text(body),
        "body_size_bytes": len(body.encode("utf-8")),
        "top_level_keys": sorted(payload.keys()) if isinstance(payload, dict) else [],
        "openapi": payload.get("openapi") if isinstance(payload, dict) else None,
        "path_count": len(paths) if isinstance(paths, dict) else 0,
        "sample_paths": sorted(list(paths.keys()))[:10] if isinstance(paths, dict) else [],
        "security": payload.get("security") if isinstance(payload, dict) else None,
    }


def materialize(
    repo_root: Path = RUN_SERVICES_ROOT,
    output: Path = DEFAULT_OUTPUT,
    requested_slot: str | None = None,
    endpoint: str = DEFAULT_ENDPOINT,
) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    alias, api_key = choose_slot(repo_root, requested_slot)
    if alias is None or api_key is None:
        payload = {
            "contractName": CONTRACT_NAME,
            "generatedAtUtc": now_iso(),
            "status": "blocked",
            "provider": "magicai",
            "providerSurface": "omagic_api",
            "slot": requested_slot.strip().zfill(2) if requested_slot else None,
            "endpoint": endpoint,
            "noCreditBurnExpected": True,
            "controlledLiveProviderPilot": False,
            "errors": ["magicai_api_key_missing"],
            "goalCompletionClaimAllowed": False,
            "privacy": {
                "rawCredentialExposed": False,
                "envValuesExposed": False,
            },
        }
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return payload

    response = fetch_probe(build_request(endpoint, api_key))
    status_code = int(response.get("status_code") or 0)
    summary = summarize_schema_body(str(response.get("body") or ""))
    passed = status_code == 200 and summary.get("json") is True
    payload = {
        "contractName": CONTRACT_NAME,
        "generatedAtUtc": now_iso(),
        "status": "pass" if passed else "blocked" if status_code in {401, 403} else "failed",
        "provider": "magicai",
        "providerSurface": "omagic_api",
        "slot": alias,
        "endpoint": endpoint,
        "httpStatus": status_code,
        "responseUrl": response.get("url"),
        "responseHeaders": {
            "Content-Type": response.get("headers", {}).get("Content-Type", ""),
            "Allow": response.get("headers", {}).get("Allow", ""),
            "WWW-Authenticate": response.get("headers", {}).get("WWW-Authenticate", ""),
        },
        "summary": summary,
        "noCreditBurnExpected": True,
        "controlledLiveProviderPilot": passed,
        "goalCompletionClaimAllowed": False,
        "privacy": {
            "rawCredentialExposed": False,
            "envValuesExposed": False,
        },
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a no-credit-burn MagicAI API handshake probe.")
    parser.add_argument("--repo-root", type=Path, default=RUN_SERVICES_ROOT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--slot")
    parser.add_argument("--endpoint", default=DEFAULT_ENDPOINT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    payload = materialize(
        repo_root=args.repo_root,
        output=args.output,
        requested_slot=args.slot,
        endpoint=str(args.endpoint),
    )
    print(json.dumps(payload, sort_keys=True))
    return 0 if payload.get("status") == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())

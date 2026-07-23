#!/usr/bin/env python3
"""Verify the serving-only public runtime and its fail-closed private boundary."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
from typing import Any

import requests


CONTRACT_NAME = "chummer.public-download-only-postdeploy/v1"
READINESS_CONTRACT = "chummer.run.api.public_downloads_readiness.v1"
PROBLEM = {
    "type": "https://chummer.run/problems/install-linking-unavailable",
    "title": "Install-linking unavailable.",
    "status": 503,
    "detail": "Install-linking is temporarily unavailable.",
}
UNAVAILABLE_READINESS_PATHS = (
    "/api/ready",
    "/api/ready/publication",
    "/api/ready/install-linking-authority",
)
PRIVATE_PATHS = (
    "/api/v1/install-linking/me",
    "/account/access/install-link",
    "/downloads/install/public-download-only-probe",
)


def load_truth_gate(source_root: Path) -> Any:
    path = source_root / "scripts" / "public_download_shelf_truth_gate.py"
    if not path.is_file() or path.is_symlink():
        raise ValueError("public download truth gate is unavailable")
    spec = importlib.util.spec_from_file_location(
        "chummer_public_download_only_truth_gate",
        path,
    )
    if spec is None or spec.loader is None:
        raise ValueError("public download truth gate could not be loaded")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def get(base_url: str, path: str, timeout: float) -> requests.Response:
    return requests.get(
        base_url.rstrip("/") + path,
        timeout=timeout,
        headers={
            "Accept": "application/json",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
        },
        allow_redirects=False,
    )


def require_json(response: requests.Response, label: str) -> dict[str, Any]:
    try:
        payload = response.json()
    except (requests.JSONDecodeError, ValueError) as exc:
        raise ValueError(f"{label} response is not JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"{label} response is not an object")
    return payload


def verify_control_plane(base_url: str, timeout: float) -> dict[str, Any]:
    serving = get(base_url, "/api/ready/public-downloads", timeout)
    serving_payload = require_json(serving, "public downloads readiness")
    checks = serving_payload.get("checks")
    release_shelf = serving_payload.get("releaseShelf")
    if (
        serving.status_code != 200
        or serving_payload.get("contractName") != READINESS_CONTRACT
        or serving_payload.get("ready") is not True
        or serving_payload.get("status") != "pass"
        or serving_payload.get("servingReady") is not True
        or serving_payload.get("overallReady") is not False
        or serving_payload.get("overallStatus") != "fail"
        or serving_payload.get("publicationReady") is not False
        or not isinstance(checks, list)
        or not isinstance(release_shelf, dict)
        or release_shelf.get("servingReady") is not True
    ):
        raise ValueError("public downloads readiness contract is not serving-only")

    readiness_statuses: dict[str, int] = {}
    for path in UNAVAILABLE_READINESS_PATHS:
        response = get(base_url, path, timeout)
        readiness_statuses[path] = response.status_code
        if response.status_code != 503:
            raise ValueError(f"{path} unexpectedly claimed readiness")

    private_statuses: dict[str, int] = {}
    for path in PRIVATE_PATHS:
        response = get(base_url, path, timeout)
        private_statuses[path] = response.status_code
        content_type = response.headers.get("Content-Type", "").lower()
        if (
            response.status_code != 503
            or not content_type.startswith("application/problem+json")
            or response.headers.get("Cache-Control")
            != "private, no-store, max-age=0"
            or response.headers.get("Pragma") != "no-cache"
            or response.headers.get("Expires") != "0"
            or require_json(response, path) != PROBLEM
        ):
            raise ValueError(f"{path} did not enforce the private 503 boundary")
    return {
        "servingReadiness": serving_payload,
        "unavailableReadinessStatuses": readiness_statuses,
        "privateBoundaryStatuses": private_statuses,
    }


def atomic_write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() or path.is_symlink():
        raise ValueError("postdeploy output must be new")
    body = json.dumps(payload, indent=2, sort_keys=True).encode("utf-8") + b"\n"
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
    )
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb", closefd=True) as handle:
            handle.write(body)
            handle.flush()
            os.fsync(handle.fileno())
        os.link(temporary, path, follow_symlinks=False)
    finally:
        temporary.unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--local-manifest", type=Path, required=True)
    parser.add_argument("--local-canonical-manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=30.0)
    args = parser.parse_args(argv)
    try:
        control_plane = verify_control_plane(args.base_url, args.timeout)
        truth_gate = load_truth_gate(args.source_root)
        download_truth = truth_gate.evaluate(
            base_url=args.base_url,
            local_manifest_path=args.local_manifest,
            local_canonical_manifest_path=args.local_canonical_manifest,
            timeout=args.timeout,
            artifact_probes_enabled=True,
            live_confirmation_count=3,
            live_confirmation_delay_seconds=2.0,
            live_max_samples=6,
        )
        if download_truth.get("status") != "pass":
            raise ValueError("public download shelf truth gate failed")
        payload = {
            "contractName": CONTRACT_NAME,
            "status": "pass",
            "runtimeProfile": "public-download-only",
            "baseUrl": args.base_url.rstrip("/"),
            **control_plane,
            "publicDownloadTruth": download_truth,
        }
        atomic_write(args.output, payload)
    except (OSError, requests.RequestException, ValueError) as exc:
        print(f"public_download_only_postdeploy: {exc}", file=sys.stderr)
        return 1
    print("public_download_only_postdeploy:ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


RUN_SERVICES_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REGISTRY_ROOT = Path("/docker/chummercomplete/chummer-hub-registry/.codex-studio/published")
DEFAULT_OUTPUT = RUN_SERVICES_ROOT / ".codex-studio" / "published" / "EXTERNAL_DISTRIBUTION_MIRROR_PROOF.generated.json"
DEFAULT_PROVIDER_ROOTS = {
    "pcloud": [Path("/mnt/pcloud/Documents/codex-audit/chummer"), Path("/media/pcloud/Documents/codex-audit/chummer")],
    "onedrive": [Path("/mnt/onedrive/Documents/codex-audit/chummer")],
}


def now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def artifact_rows(registry_root: Path) -> list[dict[str, Any]]:
    manifest = read_json(registry_root / "releases.json")
    downloads = manifest.get("downloads")
    if not isinstance(downloads, list):
        raise ValueError(f"{registry_root / 'releases.json'} does not contain a downloads list")
    rows: list[dict[str, Any]] = []
    for item in downloads:
        if not isinstance(item, dict):
            continue
        file_name = str(item.get("fileName") or item.get("file_name") or "").strip()
        sha256 = str(item.get("sha256") or "").strip().lower()
        size = int(item.get("sizeBytes") or item.get("size_bytes") or 0)
        artifact_id = str(item.get("id") or file_name).strip()
        access_class = str(item.get("installAccessClass") or item.get("install_access_class") or "").strip()
        if not file_name or not sha256 or size <= 0:
            continue
        rows.append({"id": artifact_id, "file_name": file_name, "sha256": sha256, "size": size, "access_class": access_class})
    return rows


def verify_path(path: Path, expected_size: int, expected_sha256: str) -> dict[str, Any]:
    if not path.is_file():
        return {"exists": False, "path": str(path), "status": "missing"}
    actual_size = path.stat().st_size
    actual_sha256 = sha256_file(path)
    status = "pass" if actual_size == expected_size and actual_sha256 == expected_sha256 else "fail"
    return {
        "exists": True,
        "path": str(path),
        "size": actual_size,
        "sha256": actual_sha256,
        "status": status,
    }


def verify_local_registry(registry_root: Path, rows: list[dict[str, Any]]) -> dict[str, Any]:
    checks = []
    for row in rows:
        checks.append(
            {
                "id": row["id"],
                **verify_path(registry_root / "files" / row["file_name"], int(row["size"]), str(row["sha256"])),
            }
        )
    return {
        "status": "pass" if checks and all(check["status"] == "pass" for check in checks) else "fail",
        "root": str(registry_root),
        "artifacts": checks,
    }


def verify_provider(name: str, roots: list[Path], rows: list[dict[str, Any]]) -> dict[str, Any]:
    mounted_roots = [root for root in roots if root.exists()]
    checks = []
    for row in rows:
        candidates = [root / "files" / row["file_name"] for root in mounted_roots]
        candidate_checks = [verify_path(path, int(row["size"]), str(row["sha256"])) for path in candidates]
        passing = [check for check in candidate_checks if check["status"] == "pass"]
        checks.append(
            {
                "id": row["id"],
                "file_name": row["file_name"],
                "status": "pass" if passing else "fail",
                "candidates": candidate_checks,
            }
        )
    return {
        "status": "pass" if checks and all(check["status"] == "pass" for check in checks) else "fail",
        "roots": [str(root) for root in roots],
        "mounted_roots": [str(root) for root in mounted_roots],
        "artifacts": checks,
    }


def verify_public_edge(base_url: str, rows: list[dict[str, Any]], timeout: float) -> dict[str, Any]:
    if not base_url:
        return {"status": "skipped", "reason": "no base URL configured", "artifacts": []}
    checks = []
    for row in rows:
        url = f"{base_url.rstrip('/')}/downloads/files/{row['file_name']}"
        request = urllib.request.Request(url, headers={"Range": "bytes=0-0"})
        account_required_handoff = False
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                status_code = int(response.status)
                content_range = response.headers.get("Content-Range") or ""
                content_length = int(response.headers.get("Content-Length") or 0)
                expected_size_seen = content_range.endswith(f"/{row['size']}") or content_length == int(row["size"])
                streamed_size = None
                streamed_sha256 = ""
                if status_code == 200 and not expected_size_seen:
                    digest = hashlib.sha256()
                    size = 0
                    for chunk in iter(lambda: response.read(1024 * 1024), b""):
                        size += len(chunk)
                        digest.update(chunk)
                    streamed_size = size
                    streamed_sha256 = digest.hexdigest()
                    expected_size_seen = size == int(row["size"]) and streamed_sha256 == str(row["sha256"])
                account_required_handoff = (
                    str(row.get("access_class") or "").strip().lower() == "account_required"
                    and status_code == 200
                    and not expected_size_seen
                    and streamed_size is not None
                    and streamed_size < 1024 * 1024
                )
        except (urllib.error.URLError, TimeoutError, ValueError) as exc:
            checks.append({"id": row["id"], "url": url, "status": "fail", "error": str(exc)})
            continue
        checks.append(
            {
                "id": row["id"],
                "url": url,
                "access_class": row.get("access_class"),
                "status_code": status_code,
                "final_url": response.url,
                "content_range": content_range,
                "content_length": content_length,
                "streamed_size": streamed_size,
                "streamed_sha256": streamed_sha256,
                "posture": "account_required_handoff" if account_required_handoff else "direct_download_bytes",
                "status": "pass" if status_code in {200, 206} and (expected_size_seen or account_required_handoff) else "fail",
            }
        )
    return {
        "status": "pass" if checks and all(check["status"] == "pass" for check in checks) else "fail",
        "base_url": base_url,
        "artifacts": checks,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify release artifacts across local, public-edge, pCloud, and OneDrive mirrors.")
    parser.add_argument("--registry-root", default=str(DEFAULT_REGISTRY_ROOT))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--base-url", default=os.environ.get("CHUMMER_PUBLIC_BASE_URL", "http://127.0.0.1:8091"))
    parser.add_argument("--timeout", type=float, default=8.0)
    parser.add_argument("--require-external", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    registry_root = Path(args.registry_root)
    rows = artifact_rows(registry_root)
    providers = {
        "local_registry": verify_local_registry(registry_root, rows),
        "public_edge": verify_public_edge(args.base_url, rows, args.timeout),
    }
    for name, roots in DEFAULT_PROVIDER_ROOTS.items():
        providers[name] = verify_provider(name, roots, rows)

    required = ["local_registry", "public_edge"]
    if args.require_external:
        required.extend(["pcloud", "onedrive"])
    payload = {
        "contract_name": "chummer.external_distribution_mirror_proof",
        "generated_at_utc": now_iso(),
        "registry_root": str(registry_root),
        "external_required": bool(args.require_external),
        "status": "pass" if all(providers[name]["status"] == "pass" for name in required) else "fail",
        "required_providers": required,
        "providers": providers,
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    if payload["status"] != "pass":
        raise SystemExit("external distribution mirror proof failed")
    print("external_distribution_mirror_proof:ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

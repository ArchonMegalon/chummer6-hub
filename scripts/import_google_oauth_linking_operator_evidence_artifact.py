#!/usr/bin/env python3
"""Import a signed Google OAuth operator-evidence bundle without shell authority."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import google_oauth_linking_evidence_v2 as evidence_v2


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent
DEFAULT_BASE_URL = evidence_v2.DEFAULT_BASE_URL
DEFAULT_OPERATOR_EVIDENCE_PATH = evidence_v2.DEFAULT_EVIDENCE_PATH
DEFAULT_IMPORTED_SCREENSHOT_ROOT = evidence_v2.DEFAULT_IMPORTED_SCREENSHOT_ROOT
DEFAULT_INTAKE_REQUEST = evidence_v2.DEFAULT_REQUEST_PATH
OPERATOR_EVIDENCE_CONTRACT_NAME = evidence_v2.EVIDENCE_CONTRACT_NAME
EVIDENCE_FILENAMES = (
    "GOOGLE_OAUTH_LINKING_OPERATOR_EVIDENCE.generated.json",
    "google-oauth-linking-operator-evidence.generated.json",
    "google-oauth-linking-operator-evidence.json",
)


def now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def import_token() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")


def read_json(path: Path) -> dict[str, Any]:
    try:
        payload, _raw = evidence_v2.read_json_object(path)
    except evidence_v2.ContractError as exc:
        raise SystemExit(str(exc)) from exc
    return payload


def load_optional_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        return read_json(path)
    except SystemExit:
        return {}


def load_intake_payload_for_import(
    path: Path | None,
    *,
    portal_release_manifest_path: Path = evidence_v2.DEFAULT_PORTAL_RELEASE_MANIFEST_PATH,
    hub_release_manifest_path: Path = evidence_v2.DEFAULT_HUB_RELEASE_MANIFEST_PATH,
) -> dict[str, Any]:
    if path is None or not path.is_file():
        raise SystemExit(f"intake request not found: {path}")
    payload, _summary, _raw, failures = evidence_v2.verify_request_file(
        path,
        portal_release_manifest_path=portal_release_manifest_path,
        hub_release_manifest_path=hub_release_manifest_path,
    )
    if failures:
        raise SystemExit(
            "Google OAuth intake request is not current/actionable: " + "; ".join(failures)
        )
    if payload.get("status") != "operator_action_required":
        raise SystemExit("Google OAuth intake request is not actionable")
    return payload


def ensure_safe_member(member: str) -> None:
    path = Path(member)
    if path.is_absolute() or ".." in path.parts:
        raise SystemExit(f"unsafe zip member path: {member}")


def extracted_or_directory(source: Path, temp_root: Path) -> tuple[Path, str]:
    if source.is_dir():
        raise SystemExit("v2 operator evidence must be an immutable .zip or explicit JSON receipt, not a directory")
    if not source.is_file():
        raise SystemExit(f"proof artifact not found: {source}")
    if source.suffix.lower() == ".json":
        return source.parent, "json_file"
    if source.suffix.lower() != ".zip":
        raise SystemExit(f"proof artifact must be a .json or .zip: {source}")
    output = temp_root / "google-oauth-linking-operator-evidence"
    output.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(source) as archive:
        for info in archive.infolist():
            ensure_safe_member(info.filename)
            unix_mode = (info.external_attr >> 16) & 0o170000
            if unix_mode == 0o120000:
                raise SystemExit(f"symlink zip member rejected: {info.filename}")
        archive.extractall(output)
    return output, "zip"


def find_evidence_receipt(root: Path, *, explicit_json_source: Path | None = None) -> Path:
    if explicit_json_source is not None and explicit_json_source.is_file():
        payload = read_json(explicit_json_source)
        if payload.get("contract_name") == OPERATOR_EVIDENCE_CONTRACT_NAME:
            return explicit_json_source
    matches: list[Path] = []
    for name in EVIDENCE_FILENAMES:
        matches.extend(path for path in root.rglob(name) if path.is_file())
    unique = sorted(set(matches))
    if len(unique) != 1:
        raise SystemExit(
            f"expected exactly one Google OAuth v2 evidence receipt under {root}; found {len(unique)}"
        )
    return unique[0]


def resolve_screenshot(root: Path, evidence_receipt: Path, raw_path: Any) -> Path:
    raw = str(raw_path or "").strip()
    if not raw:
        raise SystemExit("operator evidence screenshot path is empty")
    candidate = Path(raw)
    if candidate.is_absolute():
        resolved = candidate.resolve()
    else:
        first = evidence_receipt.parent / candidate
        second = root / candidate
        resolved = first.resolve() if first.is_file() else second.resolve()
    try:
        resolved.relative_to(root.resolve())
    except ValueError as exc:
        raise SystemExit(f"operator evidence screenshot escapes the bundle: {raw}") from exc
    if not resolved.is_file() or resolved.is_symlink():
        raise SystemExit(f"operator evidence screenshot is missing or symlinked: {raw}")
    return resolved


def validate_payload(payload: dict[str, Any], evidence_receipt: Path) -> list[dict[str, Any]]:
    failures: list[str] = []
    if payload.get("contract_name") != OPERATOR_EVIDENCE_CONTRACT_NAME:
        failures.append("operator evidence contract is not v2")
    if payload.get("status") != "pass":
        failures.append("operator evidence status is not pass")
    if payload.get("base_url") != DEFAULT_BASE_URL:
        failures.append("operator evidence base_url is not the live Chummer URL")
    rows = payload.get("screenshots")
    if not isinstance(rows, list) or len(rows) < evidence_v2.MINIMUM_SCREENSHOT_COUNT:
        failures.append("operator evidence screenshots are missing or too short")
        rows = []
    if failures:
        raise SystemExit(
            f"invalid Google OAuth operator evidence receipt {evidence_receipt}: "
            + "; ".join(failures)
        )
    return [dict(row) for row in rows if isinstance(row, dict)]


def copy_file(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        raise SystemExit(f"refusing to overwrite imported evidence file: {destination}")
    shutil.copyfile(source, destination)


def _source_artifact_sha256(source: Path) -> str:
    try:
        raw = evidence_v2.read_regular_file_bytes(source, max_bytes=256 * 1024 * 1024)
    except evidence_v2.ContractError as exc:
        raise SystemExit(str(exc)) from exc
    return hashlib.sha256(raw).hexdigest()


def import_artifact(
    source: Path,
    *,
    evidence_path: Path = DEFAULT_OPERATOR_EVIDENCE_PATH,
    imported_screenshot_root: Path = DEFAULT_IMPORTED_SCREENSHOT_ROOT,
    intake_request: Path | None = None,
    portal_release_manifest_path: Path = evidence_v2.DEFAULT_PORTAL_RELEASE_MANIFEST_PATH,
    hub_release_manifest_path: Path = evidence_v2.DEFAULT_HUB_RELEASE_MANIFEST_PATH,
) -> dict[str, Any]:
    intake_request = intake_request or DEFAULT_INTAKE_REQUEST
    _intake_payload = load_intake_payload_for_import(
        intake_request,
        portal_release_manifest_path=portal_release_manifest_path,
        hub_release_manifest_path=hub_release_manifest_path,
    )
    if evidence_v2.is_test_provenance_path(source):
        raise SystemExit("pytest/test-fixture artifact provenance is forbidden for production evidence")
    if source.is_dir():
        raise SystemExit("v2 evidence import requires a .zip or JSON source")
    source_artifact_sha256 = _source_artifact_sha256(source)
    with tempfile.TemporaryDirectory(prefix="google-oauth-linking-evidence-import-") as temp_dir:
        explicit_json_source = source if source.suffix.lower() == ".json" else None
        artifact_root, artifact_kind = extracted_or_directory(source, Path(temp_dir))
        evidence_receipt = find_evidence_receipt(
            artifact_root,
            explicit_json_source=explicit_json_source,
        )
        source_payload, source_receipt_raw = evidence_v2.read_json_object(evidence_receipt)
        screenshot_rows = validate_payload(source_payload, evidence_receipt)
        for row in screenshot_rows:
            row["path"] = str(resolve_screenshot(artifact_root, evidence_receipt, row.get("path")))
        source_payload = {**source_payload, "screenshots": screenshot_rows}
        source_summary, source_failures = evidence_v2.verify_evidence_payload(
            source_payload,
            evidence_path=evidence_receipt,
            request_path=intake_request,
            portal_release_manifest_path=portal_release_manifest_path,
            hub_release_manifest_path=hub_release_manifest_path,
            allowed_screenshot_root=artifact_root,
            require_import_provenance=False,
        )
        if source_failures:
            raise SystemExit(
                "Google OAuth operator evidence failed before import: "
                + "; ".join(source_failures)
            )

        destination_root = imported_screenshot_root / import_token()
        imported_rows: list[dict[str, Any]] = []
        for index, row in enumerate(screenshot_rows, start=1):
            screenshot_source = Path(str(row["path"]))
            destination = destination_root / f"{index:02d}-{row['logical_name']}"
            copy_file(screenshot_source, destination)
            imported_rows.append({**row, "path": str(destination)})

        importer_sha = evidence_v2.program_bindings()["evidence_importer"]["sha256"]
        imported_payload = {
            **source_payload,
            "screenshots": imported_rows,
            "import_provenance": {
                "source_artifact_path": str(source.resolve()),
                "source_artifact_kind": artifact_kind,
                "source_artifact_sha256": source_artifact_sha256,
                "source_receipt_sha256": hashlib.sha256(source_receipt_raw).hexdigest(),
                "importer_program_sha256": importer_sha,
                "imported_at_utc": now_iso(),
            },
        }
        imported_summary, imported_failures = evidence_v2.verify_evidence_payload(
            imported_payload,
            evidence_path=evidence_path,
            request_path=intake_request,
            portal_release_manifest_path=portal_release_manifest_path,
            hub_release_manifest_path=hub_release_manifest_path,
            allowed_screenshot_root=imported_screenshot_root,
            require_import_provenance=True,
        )
        if imported_failures:
            raise SystemExit(
                "Google OAuth operator evidence failed after immutable copy: "
                + "; ".join(imported_failures)
            )
        evidence_path.parent.mkdir(parents=True, exist_ok=True)
        previous_backup_path: Path | None = None
        if evidence_path.exists():
            try:
                previous_raw = evidence_v2.read_regular_file_bytes(
                    evidence_path,
                    max_bytes=8 * 1024 * 1024,
                )
            except evidence_v2.ContractError as exc:
                raise SystemExit(
                    f"existing operator evidence cannot be preserved safely: {exc}"
                ) from exc
            previous_sha256 = hashlib.sha256(previous_raw).hexdigest()
            previous_backup_path = destination_root / f"previous-published-evidence-{previous_sha256}.json"
            previous_backup_path.write_bytes(previous_raw)
        serialized = (json.dumps(imported_payload, indent=2) + "\n").encode("utf-8")
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{evidence_path.name}.",
            suffix=".tmp",
            dir=evidence_path.parent,
        )
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(serialized)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_name, evidence_path)
        finally:
            if os.path.exists(temporary_name):
                os.unlink(temporary_name)

    return {
        "status": "imported",
        "published_evidence_path": str(evidence_path),
        "imported_screenshot_root": str(destination_root),
        "imported_screenshot_paths": [row["path"] for row in imported_rows],
        "source_receipt_path": str(evidence_receipt),
        "source_artifact": str(source),
        "source_artifact_kind": artifact_kind,
        "source_artifact_sha256": source_artifact_sha256,
        "previous_published_evidence_backup": str(previous_backup_path) if previous_backup_path else None,
        "base_url": imported_summary.get("base_url") or DEFAULT_BASE_URL,
    }


def post_import_argv_plan(
    intake_request: Path,
    base_url: str,
    *,
    evidence_path: Path = DEFAULT_OPERATOR_EVIDENCE_PATH,
) -> list[list[str]]:
    # Never read executable commands from the intake JSON.
    return evidence_v2.fixed_post_import_argv_plan(
        base_url=base_url or DEFAULT_BASE_URL,
        request_path=intake_request,
        evidence_path=evidence_path,
    )


def post_import_commands(intake_request: Path, base_url: str) -> list[list[str]]:
    """Compatibility name returning the fixed argv plan, never shell strings."""
    return post_import_argv_plan(intake_request, base_url)


def run_command(argv: list[str], cwd: Path) -> dict[str, Any]:
    completed = subprocess.run(
        argv,
        cwd=cwd,
        shell=False,
        capture_output=True,
        text=True,
        check=False,
    )
    return {
        "argv": argv,
        "returncode": int(completed.returncode),
        "stdout_tail": completed.stdout.splitlines()[-20:],
        "stderr_tail": completed.stderr.splitlines()[-20:],
    }


def run_post_import_chain(
    intake_request: Path,
    base_url: str,
    *,
    evidence_path: Path = DEFAULT_OPERATOR_EVIDENCE_PATH,
) -> tuple[int, list[dict[str, Any]]]:
    results = [
        run_command(argv, ROOT)
        for argv in post_import_argv_plan(
            intake_request,
            base_url,
            evidence_path=evidence_path,
        )
    ]
    failures = [row for row in results if int(row.get("returncode") or 0) != 0]
    return (0 if not failures else 1), results


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Import a signed Google OAuth operator-evidence bundle."
    )
    parser.add_argument("artifact", type=Path)
    parser.add_argument("--evidence-path", type=Path, default=DEFAULT_OPERATOR_EVIDENCE_PATH)
    parser.add_argument("--imported-screenshot-root", type=Path, default=DEFAULT_IMPORTED_SCREENSHOT_ROOT)
    parser.add_argument("--intake-request", type=Path, default=DEFAULT_INTAKE_REQUEST)
    parser.add_argument("--verify", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    summary = import_artifact(
        args.artifact,
        evidence_path=args.evidence_path,
        imported_screenshot_root=args.imported_screenshot_root,
        intake_request=args.intake_request,
    )
    result = dict(summary)
    if args.verify:
        returncode, command_results = run_post_import_chain(
            args.intake_request,
            str(summary.get("base_url") or DEFAULT_BASE_URL),
            evidence_path=args.evidence_path,
        )
        result["postImportArgvPlan"] = command_results
        print(json.dumps(result, indent=2))
        return returncode
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

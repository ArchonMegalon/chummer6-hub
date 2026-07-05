#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import tempfile
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[0]
DEFAULT_IMPORTED_SCREENSHOT_ROOT = ROOT / ".state" / "google_oauth_linking_operator_evidence" / "imported"
VERIFY_MATERIALIZER = ROOT / "scripts" / "materialize_google_oauth_linking_proof.py"
EVIDENCE_FILENAMES = (
    "GOOGLE_OAUTH_LINKING_OPERATOR_EVIDENCE.generated.json",
    "google-oauth-linking-operator-evidence.generated.json",
    "google-oauth-linking-operator-evidence.json",
)

try:
    from materialize_google_oauth_linking_proof import (
        DEFAULT_BASE_URL,
        DEFAULT_OPERATOR_EVIDENCE_PATH,
        OPERATOR_EVIDENCE_CONTRACT_NAME,
    )
except ModuleNotFoundError:
    import sys

    if str(SCRIPT_DIR) not in sys.path:
        sys.path.insert(0, str(SCRIPT_DIR))
    from materialize_google_oauth_linking_proof import (  # type: ignore[no-redef]
        DEFAULT_BASE_URL,
        DEFAULT_OPERATOR_EVIDENCE_PATH,
        OPERATOR_EVIDENCE_CONTRACT_NAME,
    )


def now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def import_token() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"invalid json: {path} ({exc})") from exc
    if not isinstance(payload, dict):
        raise SystemExit(f"json root is not an object: {path}")
    return payload


def ensure_safe_member(member: str) -> None:
    path = Path(member)
    if path.is_absolute() or ".." in path.parts:
        raise SystemExit(f"unsafe zip member path: {member}")


def extracted_or_directory(source: Path, temp_root: Path) -> tuple[Path, str]:
    if source.is_dir():
        return source, "directory"
    if not source.is_file():
        raise SystemExit(f"proof artifact not found: {source}")
    if source.suffix.lower() == ".json":
        return source.parent, "json_file"
    if source.suffix.lower() != ".zip":
        raise SystemExit(f"proof artifact must be a directory, .json, or .zip: {source}")

    output = temp_root / "google-oauth-linking-operator-evidence"
    output.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(source) as archive:
        for member in archive.namelist():
            ensure_safe_member(member)
        archive.extractall(output)
    return output, "zip"


def find_evidence_receipt(root: Path, *, explicit_json_source: Path | None = None) -> Path:
    if explicit_json_source is not None and explicit_json_source.is_file():
        payload = read_json(explicit_json_source)
        if str(payload.get("contract_name") or "").strip() == OPERATOR_EVIDENCE_CONTRACT_NAME:
            return explicit_json_source

    named_matches: list[Path] = []
    for name in EVIDENCE_FILENAMES:
        named_matches.extend(sorted(path for path in root.rglob(name) if path.is_file()))
    if len(named_matches) == 1:
        return named_matches[0]
    if len(named_matches) > 1:
        raise SystemExit(f"multiple operator evidence receipts found: {[str(path) for path in named_matches]}")

    contract_matches: list[Path] = []
    for candidate in sorted(path for path in root.rglob("*.json") if path.is_file()):
        try:
            payload = read_json(candidate)
        except SystemExit:
            continue
        if str(payload.get("contract_name") or "").strip() == OPERATOR_EVIDENCE_CONTRACT_NAME:
            contract_matches.append(candidate)
    if not contract_matches:
        raise SystemExit(f"no Google OAuth operator evidence receipt found under {root}")
    if len(contract_matches) > 1:
        raise SystemExit(f"multiple contract-matching operator evidence receipts found: {[str(path) for path in contract_matches]}")
    return contract_matches[0]


def resolve_screenshot(root: Path, evidence_receipt: Path, raw_path: Any) -> Path:
    raw = str(raw_path or "").strip()
    if not raw:
        raise SystemExit("operator evidence screenshot_paths contains an empty entry")

    candidate = Path(raw)
    if not candidate.is_absolute():
        direct = evidence_receipt.parent / candidate
        if direct.is_file():
            return direct
        direct = root / candidate
        if direct.is_file():
            return direct

    basename = candidate.name
    matches = sorted(path for path in root.rglob(basename) if path.is_file())
    if len(matches) == 1:
        return matches[0]
    if not matches:
        raise SystemExit(f"operator evidence screenshot is missing from artifact bundle: {raw}")
    raise SystemExit(f"operator evidence screenshot path is ambiguous in artifact bundle: {raw}")


def validate_payload(payload: dict[str, Any], evidence_receipt: Path) -> list[str]:
    failures: list[str] = []
    if str(payload.get("contract_name") or "").strip() != OPERATOR_EVIDENCE_CONTRACT_NAME:
        failures.append(f"unexpected operator evidence contract: {payload.get('contract_name') or 'missing'}")
    if str(payload.get("status") or "").strip() != "pass":
        failures.append(f"operator evidence status is {payload.get('status') or 'missing'}, expected pass")
    if not str(payload.get("base_url") or "").strip():
        failures.append("operator evidence base_url is missing")
    screenshot_paths = payload.get("screenshot_paths")
    if not isinstance(screenshot_paths, list) or not screenshot_paths:
        failures.append("operator evidence screenshot_paths is missing")
    if not str(payload.get("observed_at_utc") or payload.get("generated_at_utc") or "").strip():
        failures.append("operator evidence observed_at_utc/generated_at_utc is missing")
    if failures:
        raise SystemExit(
            "invalid Google OAuth operator evidence receipt "
            f"{evidence_receipt}: {'; '.join(failures)}"
        )
    return [str(item).strip() for item in screenshot_paths if str(item).strip()]


def copy_file(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def import_artifact(
    source: Path,
    *,
    evidence_path: Path = DEFAULT_OPERATOR_EVIDENCE_PATH,
    imported_screenshot_root: Path = DEFAULT_IMPORTED_SCREENSHOT_ROOT,
) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="google-oauth-linking-evidence-import-") as temp_dir:
        explicit_json_source = source if source.is_file() and source.suffix.lower() == ".json" else None
        artifact_root, artifact_kind = extracted_or_directory(source, Path(temp_dir))
        evidence_receipt = find_evidence_receipt(artifact_root, explicit_json_source=explicit_json_source)
        payload = read_json(evidence_receipt)
        screenshot_rows = validate_payload(payload, evidence_receipt)
        if artifact_kind == "zip":
            receipt_reference = f"{source}::{evidence_receipt.relative_to(artifact_root)}"
        else:
            receipt_reference = str(evidence_receipt)

        destination_root = imported_screenshot_root / import_token()
        imported_screenshot_paths: list[str] = []
        source_screenshot_paths: list[str] = []
        for index, raw_path in enumerate(screenshot_rows, start=1):
            screenshot_source = resolve_screenshot(artifact_root, evidence_receipt, raw_path)
            filename = Path(str(raw_path)).name or screenshot_source.name or f"screenshot-{index}.png"
            destination = destination_root / f"{index:02d}-{filename}"
            copy_file(screenshot_source, destination)
            imported_screenshot_paths.append(str(destination))
            source_screenshot_paths.append(str(screenshot_source))

        imported_payload = dict(payload)
        imported_payload["screenshot_paths"] = imported_screenshot_paths
        imported_payload["imported_at_utc"] = now_iso()
        imported_payload["import_source_artifact"] = str(source)
        imported_payload["import_source_artifact_kind"] = artifact_kind
        imported_payload["import_source_receipt_path"] = receipt_reference
        imported_payload["import_source_screenshot_paths"] = source_screenshot_paths
        imported_payload["imported_screenshot_root"] = str(destination_root)
        evidence_path.parent.mkdir(parents=True, exist_ok=True)
        evidence_path.write_text(json.dumps(imported_payload, indent=2) + "\n", encoding="utf-8")

    return {
        "status": "imported",
        "published_evidence_path": str(evidence_path),
        "imported_screenshot_root": str(destination_root),
        "imported_screenshot_paths": imported_screenshot_paths,
        "source_receipt_path": receipt_reference,
        "source_artifact": str(source),
        "source_artifact_kind": artifact_kind,
        "base_url": str(imported_payload.get("base_url") or "").strip(),
    }


def run_verifier(base_url: str) -> int:
    completed = subprocess.run(
        [
            "python3",
            str(VERIFY_MATERIALIZER),
            "--base-url",
            base_url or DEFAULT_BASE_URL,
        ],
        cwd=ROOT,
        check=False,
    )
    return int(completed.returncode)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Import a Google OAuth operator-evidence bundle into the published proof path.")
    parser.add_argument("artifact", type=Path, help="Operator evidence bundle directory, JSON receipt, or zip.")
    parser.add_argument("--evidence-path", type=Path, default=DEFAULT_OPERATOR_EVIDENCE_PATH)
    parser.add_argument("--imported-screenshot-root", type=Path, default=DEFAULT_IMPORTED_SCREENSHOT_ROOT)
    parser.add_argument("--verify", action="store_true", help="Rerun the Google OAuth proof materializer after import.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    summary = import_artifact(
        args.artifact,
        evidence_path=args.evidence_path,
        imported_screenshot_root=args.imported_screenshot_root,
    )
    print(json.dumps(summary, indent=2))
    if args.verify:
        return run_verifier(summary.get("base_url") or DEFAULT_BASE_URL)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import verify_windows_installer_visual_audit as visual_audit  # noqa: E402


PUBLISHED_ROOT = ROOT / ".codex-studio" / "published"
DEFAULT_OUTPUT = PUBLISHED_ROOT / "WINDOWS_INSTALLER_VISUAL_AUDIT_INTAKE_REQUEST.generated.json"
DEFAULT_DISCOVERY_ROOTS = (
    Path("/docker/chummercomplete/_staging"),
    Path("/tmp"),
    Path.home() / "Downloads",
    Path.home() / "pCloud Drive" / "EA",
)
DEFAULT_GOLD_PROOF_PATTERN = "*windows-installer-gold-proof*.zip"
DEFAULT_VISUAL_SOURCE_PATTERN = "*WINDOWS_INSTALLER_VISUAL_AUDIT.source.json"
DEFAULT_NIGHTLY_ROOT = Path("/docker/chummercomplete/_staging")


def now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        loaded = json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError:
        return {}
    return loaded if isinstance(loaded, dict) else {}


def sha256_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest().lower()


def normalize_digest(value: Any) -> str:
    return str(value or "").strip().lower().removeprefix("sha256:")


def file_row(path: Path) -> dict[str, Any]:
    stat = path.stat()
    return {
        "path": str(path),
        "name": path.name,
        "size_bytes": stat.st_size,
        "mtime_utc": datetime.fromtimestamp(stat.st_mtime, UTC)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z"),
    }


def discover_files(pattern: str, roots: list[Path]) -> list[Path]:
    results: list[Path] = []
    seen: set[Path] = set()
    for root in roots:
        if not root.exists():
            continue
        candidates = root.rglob(pattern) if root.is_dir() else [root]
        for candidate in candidates:
            if not candidate.is_file():
                continue
            resolved = candidate.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            results.append(candidate)
    return sorted(results, key=lambda item: item.stat().st_mtime, reverse=True)


def visual_source_row(path: Path, promoted_digest: str) -> dict[str, Any]:
    payload = load_json(path)
    digest = normalize_digest(payload.get("artifactSha256") or payload.get("artifactDigest"))
    screenshots = payload.get("screenshots") if isinstance(payload.get("screenshots"), list) else []
    row = file_row(path)
    row.update(
        {
            "status": payload.get("status"),
            "platform": payload.get("platform"),
            "host_class": payload.get("hostClass"),
            "artifact_sha256": digest,
            "matches_promoted_installer": bool(promoted_digest and digest == promoted_digest),
            "screenshot_count": len(screenshots),
            "source_sha256": sha256_file(path),
            "source_updated_at_utc": payload.get("sourceUpdatedAtUtc")
            or payload.get("generatedAt")
            or payload.get("generated_at"),
        }
    )
    return row


def latest_nightly_handoff(nightly_root: Path) -> dict[str, Any]:
    if not nightly_root.exists():
        return {}
    matches = sorted(
        nightly_root.glob("nightly-run-*/WINDOWS_INSTALLER_VISUAL_PROOF_HANDOFF.generated.json"),
        key=lambda item: item.stat().st_mtime,
        reverse=True,
    )
    for match in matches:
        payload = load_json(match)
        if payload:
            return {"path": str(match), **payload}
    return {}


def build_request(
    *,
    release_channel: Path,
    downloads_root: Path,
    startup_receipt: Path,
    source: Path,
    discovery_roots: list[Path],
    nightly_root: Path,
) -> dict[str, Any]:
    audit = visual_audit.build_payload(
        release_channel_path=release_channel,
        downloads_root=downloads_root,
        startup_receipt_path=startup_receipt,
        source_path=source,
    )
    artifact = audit.get("artifact") if isinstance(audit.get("artifact"), dict) else {}
    visual_source = audit.get("visualAuditSource") if isinstance(audit.get("visualAuditSource"), dict) else {}
    promoted_digest = normalize_digest(artifact.get("sha256"))
    visual_digest = normalize_digest(visual_source.get("artifactSha256"))
    gold_proof_candidates = discover_files(DEFAULT_GOLD_PROOF_PATTERN, discovery_roots)
    visual_source_candidates = discover_files(DEFAULT_VISUAL_SOURCE_PATTERN, discovery_roots)
    importable_visual_sources = [
        visual_source_row(path, promoted_digest)
        for path in visual_source_candidates
        if path.resolve() != source.resolve()
    ]
    matching_visual_sources = [row for row in importable_visual_sources if row["matches_promoted_installer"]]
    nightly = latest_nightly_handoff(nightly_root)
    latest_nightly = {}
    if nightly:
        latest_nightly = {
            "status": nightly.get("status"),
            "summary": nightly.get("summary"),
            "handoff_path": nightly.get("path"),
            "release_shelf_root": nightly.get("release_shelf_root"),
            "release_channel_manifest_path": nightly.get("release_channel_manifest_path"),
            "visual_proof_receipt_path": nightly.get("visual_proof_receipt_path"),
            "only_blocker_is_visual_proof": nightly.get("only_blocker_is_visual_proof"),
            "windows_gate_status": nightly.get("windows_gate_status"),
            "windows_gate_reasons": nightly.get("windows_gate_reasons"),
            "windows_installer": nightly.get("windows_installer"),
            "required_screenshots": nightly.get("required_screenshots"),
            "next_actions": nightly.get("next_actions"),
        }

    command_root = "${REPO_ROOT}"
    current_failure = "; ".join(str(item) for item in audit.get("failures") or [])
    return {
        "contract_name": "chummer.windows_installer_visual_audit_intake_request.v1",
        "generated_at_utc": now_iso(),
        "status": "not_required" if audit.get("status") == "pass" else "external_artifact_required",
        "provider": "native_windows_operator",
        "artifact_kind": "windows_installer_gold_proof_bundle",
        "promoted_installer": {
            "file_name": artifact.get("fileName"),
            "sha256": promoted_digest,
            "path": artifact.get("path"),
            "actual_sha256": artifact.get("actualSha256"),
        },
        "current_blocker": {
            "receipt": str(PUBLISHED_ROOT / "WINDOWS_INSTALLER_VISUAL_AUDIT.generated.json"),
            "failure": current_failure,
            "current_visual_source_artifact_sha256": visual_digest,
            "current_visual_source_matches_promoted": bool(promoted_digest and visual_digest == promoted_digest),
            "current_visual_source_path": visual_source.get("path"),
            "current_visual_source_sha256": sha256_file(source) if source.is_file() else "",
        },
        "operator_request": {
            "summary": "Run the promoted Windows installer on a native Windows host and provide the gold proof bundle.",
            "copy_to_windows": [
                "Copy the repository checkout or at least Chummer.Portal/downloads/files, Chummer.Portal/downloads/RELEASE_CHANNEL.generated.json, and scripts to the Windows host.",
                "Do not mark screenshots pass until a human has inspected clipping/readability.",
            ],
            "powershell_commands": [
                f"{command_root}\\scripts\\capture_windows_installer_gold_proof.ps1 -InstallerPath {command_root}\\Chummer.Portal\\downloads\\files\\{artifact.get('fileName')} -DownloadsRoot {command_root}\\Chummer.Portal\\downloads -LaunchInstaller -CaptureVisualAudit -ScaledDpiScale 1.5 -VisualClippingStatus pass -VisualReadabilityStatus pass",
                f"Compress-Archive -Path {command_root}\\Chummer.Portal\\downloads\\startup-smoke\\startup-smoke-avalonia-win-x64.receipt.json,{command_root}\\Chummer.Portal\\downloads\\visual-audit\\windows-installer\\* -DestinationPath windows-installer-gold-proof-{promoted_digest[:12] or 'promoted'}.zip -Force",
            ],
            "required_surfaces": list(visual_audit.REQUIRED_SURFACES),
            "required_dpi_scales": ["1.0", "1.5"],
            "required_host_class_prefix": "native-windows",
        },
        "expected_artifact_patterns": [
            DEFAULT_GOLD_PROOF_PATTERN,
            DEFAULT_VISUAL_SOURCE_PATTERN,
        ],
        "drop_roots_checked": [str(path) for path in discovery_roots],
        "last_discovery": {
            "gold_proof_zip": {
                "status": "found" if gold_proof_candidates else "not_found",
                "count": len(gold_proof_candidates),
                "files": [file_row(path) for path in gold_proof_candidates[:20]],
            },
            "visual_sources": {
                "status": "found" if importable_visual_sources else "not_found",
                "count": len(importable_visual_sources),
                "matching_promoted_count": len(matching_visual_sources),
                "files": importable_visual_sources[:20],
            },
        },
        "latest_nightly_visual_proof_handoff": latest_nightly,
        "import_command": "python3 scripts/import_windows_installer_gold_proof_artifact.py windows-installer-gold-proof.zip --verify",
        "post_import_gates": [
            "python3 scripts/verify_windows_installer_visual_audit.py --output .codex-studio/published/WINDOWS_INSTALLER_VISUAL_AUDIT.generated.json",
            "python3 scripts/materialize_operator_release_dashboard.py",
            "python3 scripts/materialize_release_ready_receipt.py",
            "python3 scripts/final_gold_janitor.py",
            "python3 scripts/verify_flagship_product_readiness_gate.py --summary-output .codex-studio/published/FLAGSHIP_PRODUCT_READINESS_GATE.generated.json",
        ],
        "secrets_redacted": True,
        "direct_telegram_sent": False,
        "direct_telegram_reason": "Not sent without an explicit operator-send instruction in this turn.",
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Materialize an operator intake request for the native Windows installer visual audit.")
    parser.add_argument("--release-channel", type=Path, default=visual_audit.DEFAULT_RELEASE_CHANNEL)
    parser.add_argument("--downloads-root", type=Path, default=visual_audit.DEFAULT_DOWNLOADS_ROOT)
    parser.add_argument("--startup-receipt", type=Path, default=visual_audit.DEFAULT_STARTUP_RECEIPT)
    parser.add_argument("--source", type=Path, default=visual_audit.DEFAULT_SOURCE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--nightly-root", type=Path, default=DEFAULT_NIGHTLY_ROOT)
    parser.add_argument("--discovery-root", action="append", default=None)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    roots = [Path(os.path.expandvars(os.path.expanduser(item))) for item in (args.discovery_root or [])]
    if not roots:
        roots = list(DEFAULT_DISCOVERY_ROOTS)
    payload = build_request(
        release_channel=args.release_channel,
        downloads_root=args.downloads_root,
        startup_receipt=args.startup_receipt,
        source=args.source,
        discovery_roots=roots,
        nightly_root=args.nightly_root,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"windows_installer_visual_audit_intake_request:{payload['status']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

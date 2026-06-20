#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
PUBLISHED_ROOT = ROOT / ".codex-studio" / "published"
DEFAULT_DOWNLOADS_ROOT = ROOT / "Chummer.Portal" / "downloads"
DEFAULT_OUTPUT = PUBLISHED_ROOT / "WINDOWS_INSTALLER_VISUAL_AUDIT.generated.json"
DEFAULT_SOURCE = DEFAULT_DOWNLOADS_ROOT / "visual-audit" / "windows-installer" / "WINDOWS_INSTALLER_VISUAL_AUDIT.source.json"
DEFAULT_STARTUP_RECEIPT = DEFAULT_DOWNLOADS_ROOT / "startup-smoke" / "startup-smoke-avalonia-win-x64.receipt.json"
DEFAULT_RELEASE_CHANNEL = DEFAULT_DOWNLOADS_ROOT / "RELEASE_CHANNEL.generated.json"
REQUIRED_SURFACES = ("install-progress", "completion")
CAPTURE_SCRIPT = "scripts/capture_windows_installer_visual_audit.ps1"
GOLD_PROOF_SCRIPT = "scripts/capture_windows_installer_gold_proof.ps1"


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


def normalized(value: Any) -> str:
    return str(value or "").strip().lower()


def normalized_surface(value: Any) -> str:
    surface = normalized(value).replace("_", "-").replace(" ", "-")
    aliases = {
        "progress": "install-progress",
        "install": "install-progress",
        "splash": "install-progress",
        "install-splash": "install-progress",
        "complete": "completion",
        "install-complete": "completion",
    }
    return aliases.get(surface, surface)


def is_default_dpi(value: Any) -> bool:
    return str(value) in {"1", "1.0", "100", "100%"}


def windows_installer_artifact(release_channel: dict[str, Any]) -> dict[str, Any]:
    for item in release_channel.get("artifacts") or release_channel.get("downloads") or []:
        if not isinstance(item, dict):
            continue
        artifact_id = normalized(item.get("artifactId") or item.get("id"))
        platform = normalized(item.get("platform"))
        kind = normalized(item.get("kind"))
        if artifact_id == "avalonia-win-x64-installer" or (platform == "windows" and kind == "installer"):
            return item
    return {}


def source_screenshot_path(source_path: Path, raw_path: Any) -> Path:
    candidate = Path(str(raw_path or "").strip())
    if not candidate:
        return candidate
    if candidate.is_absolute():
        return candidate
    return source_path.parent / candidate


def screenshot_rows(source_path: Path, source: dict[str, Any]) -> list[dict[str, Any]]:
    rows = source.get("screenshots")
    if not isinstance(rows, list):
        return []
    normalized_rows: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        path = source_screenshot_path(source_path, row.get("path"))
        surface = normalized_surface(row.get("surface"))
        screenshot_sha = sha256_file(path) if path.is_file() else ""
        normalized_rows.append(
            {
                "path": str(path),
                "exists": path.is_file(),
                "sha256": screenshot_sha,
                "dpiScale": row.get("dpiScale"),
                "surface": str(row.get("surface") or "").strip(),
                "canonicalSurface": surface,
                "clippingStatus": normalized(row.get("clippingStatus")),
                "readabilityStatus": normalized(row.get("readabilityStatus")),
                "hostClass": str(row.get("hostClass") or "").strip(),
            }
        )
    return normalized_rows


def build_payload(
    *,
    release_channel_path: Path,
    downloads_root: Path,
    startup_receipt_path: Path,
    source_path: Path,
) -> dict[str, Any]:
    release_channel = load_json(release_channel_path)
    startup_receipt = load_json(startup_receipt_path)
    source = load_json(source_path)
    artifact = windows_installer_artifact(release_channel)
    failures: list[str] = []

    artifact_path = downloads_root / "files" / str(artifact.get("fileName") or "")
    artifact_sha = str(artifact.get("sha256") or "").strip().lower()
    actual_artifact_sha = sha256_file(artifact_path) if artifact_path.is_file() else ""

    if not artifact:
        failures.append("promoted Windows installer artifact is missing from release channel")
    if not artifact_path.is_file():
        failures.append("promoted Windows installer artifact file is missing")
    if artifact_sha and actual_artifact_sha and artifact_sha != actual_artifact_sha:
        failures.append("promoted Windows installer manifest sha256 does not match artifact bytes")

    startup_status = normalized(startup_receipt.get("status"))
    startup_disposition = normalized(startup_receipt.get("verificationDisposition"))
    startup_skip_class = normalized(startup_receipt.get("skipClass"))
    startup_digest = normalized(startup_receipt.get("artifactDigest")).removeprefix("sha256:")
    if not startup_receipt:
        failures.append("Windows startup receipt is missing")
    elif startup_status != "pass":
        failures.append("Windows startup receipt is not a native pass")
    if startup_disposition == "incompatible_host" or startup_skip_class == "incompatible_host":
        failures.append("Windows startup receipt is an incompatible-host skip, not native proof")
    if artifact_sha and startup_digest and startup_digest != artifact_sha:
        failures.append("Windows startup receipt digest does not match promoted installer")

    source_status = normalized(source.get("status"))
    source_platform = normalized(source.get("platform"))
    source_host_class = normalized(source.get("hostClass"))
    source_artifact_sha = normalized(source.get("artifactSha256") or source.get("artifactDigest")).removeprefix("sha256:")
    screenshots = screenshot_rows(source_path, source)
    default_dpi = [row for row in screenshots if is_default_dpi(row.get("dpiScale"))]
    scaled_dpi = [
        row
        for row in screenshots
        if str(row.get("dpiScale")) not in {"", "1", "1.0", "100", "100%"}
    ]

    if not source:
        failures.append(f"Windows installer visual audit source is missing: {source_path}")
    elif source_status != "pass":
        failures.append("Windows installer visual audit source is not pass")
    if source and source_platform != "windows":
        failures.append("Windows installer visual audit source platform is not windows")
    if source and "windows" not in source_host_class and source_host_class != "native":
        failures.append("Windows installer visual audit source is not marked as a native Windows host")
    if artifact_sha and source_artifact_sha and source_artifact_sha != artifact_sha:
        failures.append("Windows installer visual audit source digest does not match promoted installer")
    if source and not source_artifact_sha:
        failures.append("Windows installer visual audit source does not record artifactSha256")
    if not screenshots:
        failures.append("Windows installer visual audit has no screenshots")
    if screenshots and not default_dpi:
        failures.append("Windows installer visual audit has no default-DPI screenshot")
    if screenshots and not scaled_dpi:
        failures.append("Windows installer visual audit has no scaled-DPI screenshot")
    for surface in REQUIRED_SURFACES:
        surface_rows = [row for row in screenshots if row.get("canonicalSurface") == surface]
        if not surface_rows:
            failures.append(f"Windows installer visual audit has no {surface} screenshot")
            continue
        if not any(is_default_dpi(row.get("dpiScale")) for row in surface_rows):
            failures.append(f"Windows installer visual audit has no default-DPI {surface} screenshot")
        if not any(not is_default_dpi(row.get("dpiScale")) and str(row.get("dpiScale")) for row in surface_rows):
            failures.append(f"Windows installer visual audit has no scaled-DPI {surface} screenshot")
    for row in screenshots:
        if not row["exists"]:
            failures.append(f"Windows installer screenshot is missing: {row['path']}")
        if row["clippingStatus"] != "pass":
            failures.append(f"Windows installer screenshot clipping check is not pass: {row['path']}")
        if row["readabilityStatus"] != "pass":
            failures.append(f"Windows installer screenshot readability check is not pass: {row['path']}")
    rows_by_hash: dict[str, set[str]] = {}
    for row in screenshots:
        screenshot_sha = str(row.get("sha256") or "")
        surface = str(row.get("canonicalSurface") or "")
        if screenshot_sha and surface in REQUIRED_SURFACES:
            rows_by_hash.setdefault(screenshot_sha, set()).add(surface)
    for screenshot_sha, surfaces in sorted(rows_by_hash.items()):
        if len(surfaces) > 1:
            failures.append(
                "Windows installer screenshots for distinct required surfaces are byte-identical: "
                f"{screenshot_sha} covers {', '.join(sorted(surfaces))}"
            )

    next_actions = []
    if failures:
        next_actions = [
            "Run the promoted Windows installer on a native Windows host and capture native startup plus installer progress/completion surfaces.",
            "Preferred remote path: trigger GitHub Actions workflow 'Windows Installer Gold Proof' (.github/workflows/windows-installer-gold-proof.yml); it captures native Windows evidence only and does not publish downloads.",
            f"Use PowerShell: {GOLD_PROOF_SCRIPT} -LaunchInstaller -CaptureVisualAudit -ScaledDpiScale 1.5",
            f"Use PowerShell: {CAPTURE_SCRIPT} -LaunchInstaller -CaptureRequiredSet -ScaledDpiScale 1.5 -ClippingStatus pass -ReadabilityStatus pass",
            f"If you need manual capture, run {CAPTURE_SCRIPT} once per surface/DPI for install-progress and completion at default plus scaled DPI.",
            "If progress and completion screenshots are byte-identical, rerun manual capture with the progress dialog visible before accepting the completion dialog.",
            "If proof came from GitHub Actions, import it with: python3 scripts/import_windows_installer_gold_proof_artifact.py windows-installer-gold-proof.zip --verify",
            f"Commit the generated source receipt and screenshots under {source_path.parent}.",
            "Replace the incompatible-host Windows startup-smoke receipt with a native Windows pass for the same promoted installer digest.",
        ]

    return {
        "contract_name": "chummer.windows_installer_visual_audit",
        "generated_at_utc": now_iso(),
        "status": "pass" if not failures else "fail",
        "release": {
            "version": release_channel.get("version") or release_channel.get("releaseVersion"),
            "channel": release_channel.get("channelId") or release_channel.get("channel"),
        },
        "artifact": {
            "artifactId": artifact.get("artifactId") or artifact.get("id"),
            "fileName": artifact.get("fileName"),
            "path": str(artifact_path),
            "sha256": artifact_sha,
            "actualSha256": actual_artifact_sha,
        },
        "startupReceipt": {
            "path": str(startup_receipt_path),
            "status": startup_receipt.get("status"),
            "verificationDisposition": startup_receipt.get("verificationDisposition"),
            "skipClass": startup_receipt.get("skipClass"),
            "artifactDigest": startup_receipt.get("artifactDigest"),
        },
        "visualAuditSource": {
            "path": str(source_path),
            "exists": source_path.is_file(),
            "status": source.get("status"),
            "platform": source.get("platform"),
            "hostClass": source.get("hostClass"),
            "artifactSha256": source.get("artifactSha256") or source.get("artifactDigest"),
            "screenshotCount": len(screenshots),
            "defaultDpiScreenshotCount": len(default_dpi),
            "scaledDpiScreenshotCount": len(scaled_dpi),
            "requiredSurfaces": list(REQUIRED_SURFACES),
        },
        "screenshots": screenshots,
        "failures": failures,
        "nextActions": next_actions,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify native Windows installer visual/DPI audit proof.")
    parser.add_argument("--release-channel", type=Path, default=DEFAULT_RELEASE_CHANNEL)
    parser.add_argument("--downloads-root", type=Path, default=DEFAULT_DOWNLOADS_ROOT)
    parser.add_argument("--startup-receipt", type=Path, default=DEFAULT_STARTUP_RECEIPT)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    payload = build_payload(
        release_channel_path=args.release_channel,
        downloads_root=args.downloads_root,
        startup_receipt_path=args.startup_receipt,
        source_path=args.source,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    if payload["status"] != "pass":
        print("windows_installer_visual_audit:fail")
        return 1
    print("windows_installer_visual_audit:pass")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

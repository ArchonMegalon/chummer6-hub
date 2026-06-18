#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import requests


OUT_PATHS = (
    Path("/docker/chummercomplete/chummer-design/_completion/full_product_every_aspect/PUBLIC_DOWNLOAD_SHELF_TRUTH.generated.json"),
    Path("/docker/chummercomplete/_completion/full_product_every_aspect/PUBLIC_DOWNLOAD_SHELF_TRUTH.generated.json"),
)
DOWNLOAD_DOC = Path("/docker/chummercomplete/Chummer6/DOWNLOAD.md")
STATUS_DOC = Path("/docker/chummercomplete/Chummer6/STATUS.md")
RELEASE_CHANNEL = Path("/docker/chummercomplete/chummer-hub-registry/.codex-studio/published/RELEASE_CHANNEL.generated.json")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    base = args.base_url.rstrip("/")
    downloads = requests.get(f"{base}/downloads", timeout=30)
    status = requests.get(f"{base}/status", timeout=30)
    live_releases_response = requests.get(f"{base}/downloads/releases.json", timeout=30)
    try:
        live_releases = live_releases_response.json()
    except ValueError:
        live_releases = {}
    download_doc = DOWNLOAD_DOC.read_text(encoding="utf-8")
    status_doc = STATUS_DOC.read_text(encoding="utf-8") if STATUS_DOC.exists() else ""
    release_channel_payload = json.loads(RELEASE_CHANNEL.read_text(encoding="utf-8")) if RELEASE_CHANNEL.exists() else {}

    live_download_text = downloads.text.lower()
    live_status_text = status.text.lower()
    live_download_copy_text = (
        live_download_text.replace("max-image-preview", "max-image-robots-directive")
        .replace("max-video-preview", "max-video-robots-directive")
    )
    live_status_copy_text = (
        live_status_text.replace("max-image-preview", "max-image-robots-directive")
        .replace("max-video-preview", "max-video-robots-directive")
    )
    doc_text = download_doc.lower() + "\n" + status_doc.lower()

    windows_live = "windows" in live_download_text
    linux_live = "linux" in live_download_text
    mac_live = "mac" in live_download_text or "macos" in live_status_text
    mac_doc_note = "no public macos" in doc_text or "macos download today" in doc_text or "mac setup-script preview" in live_download_text
    review_required = "review-required" in live_status_text or "review required" in live_status_text
    rollout_state = str(release_channel_payload.get("rolloutState") or release_channel_payload.get("channelId") or "").strip()
    supportability_state = str(release_channel_payload.get("supportabilityState") or "").strip()
    live_channel = str(live_releases.get("channel") or live_releases.get("channelId") or "").strip()
    live_rollout_state = str(live_releases.get("rolloutState") or "").strip()
    live_supportability_state = str(live_releases.get("supportabilityState") or "").strip()
    live_download_channels = sorted(
        {
            str(download.get("channel") or download.get("channelId") or "").strip()
            for download in live_releases.get("downloads") or []
            if isinstance(download, dict)
        }
    )
    release_rollout_states = {"public_stable", "stable"}
    public_stable = rollout_state in release_rollout_states
    gold_supported = supportability_state == "gold_supported"
    live_public_stable = live_channel in release_rollout_states or live_rollout_state in release_rollout_states
    live_gold_supported = live_supportability_state == "gold_supported"
    preview_machine_truth = any(
        value in {"preview", "promoted_preview", "preview_supported"}
        for value in [
            str(release_channel_payload.get("channelId") or "").strip(),
            str(release_channel_payload.get("channel") or "").strip(),
            rollout_state,
            supportability_state,
            live_channel,
            live_rollout_state,
            live_supportability_state,
            *live_download_channels,
        ]
    )
    failures = []
    if review_required:
        failures.append("review-required desktop proof language is still live")
    if not public_stable or not gold_supported:
        failures.append("local release channel is not public_stable/gold_supported")
    if not live_public_stable or not live_gold_supported:
        failures.append("live releases.json is not public_stable/gold_supported")
    if preview_machine_truth:
        failures.append("public download machine truth still contains preview posture")
    if not windows_live or not linux_live:
        failures.append("live downloads page does not mention both Windows and Linux")

    payload = {
        "generated_at_utc": now_iso(),
        "contract_name": "chummer.public_download_shelf_truth",
        "base_url": base,
        "status": "fail" if failures else "pass",
        "live": {
            "downloads_status_code": downloads.status_code,
            "status_status_code": status.status_code,
            "releases_status_code": live_releases_response.status_code,
            "windows_mentioned": windows_live,
            "linux_mentioned": linux_live,
            "mac_mentioned": mac_live,
            "preview_mentioned": "preview" in live_download_copy_text or "preview" in live_status_copy_text,
            "review_required_mentioned": review_required,
            "releases_channel": live_channel,
            "releases_rollout_state": live_rollout_state,
            "releases_supportability_state": live_supportability_state,
            "download_channels": live_download_channels,
        },
        "docs": {
            "download_doc_exists": DOWNLOAD_DOC.exists(),
            "status_doc_exists": STATUS_DOC.exists(),
            "preview_mentioned": "preview" in doc_text,
            "mac_unavailable_mentioned": mac_doc_note,
        },
        "release_channel": {
            "path": str(RELEASE_CHANNEL),
            "channel_id": str(release_channel_payload.get("channelId") or "").strip(),
            "rollout_state": rollout_state,
            "supportability_state": supportability_state,
        },
        "alignment": {
            "public_release_truth_aligned": public_stable and gold_supported,
            "live_public_release_truth_aligned": live_public_stable and live_gold_supported,
            "preview_machine_truth_absent": not preview_machine_truth,
            "windows_linux_truth_aligned": windows_live and linux_live,
            "mac_truth_aligned": mac_live or public_stable,
        },
        "failures": failures,
        "summary": "pass: current download shelf truth is aligned" if not failures else "fail: " + "; ".join(failures),
    }
    for out_path in OUT_PATHS:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload))
    return 0 if payload["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())

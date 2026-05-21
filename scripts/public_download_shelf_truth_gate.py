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
    download_doc = DOWNLOAD_DOC.read_text(encoding="utf-8")
    status_doc = STATUS_DOC.read_text(encoding="utf-8") if STATUS_DOC.exists() else ""
    release_channel_payload = json.loads(RELEASE_CHANNEL.read_text(encoding="utf-8")) if RELEASE_CHANNEL.exists() else {}

    live_download_text = downloads.text.lower()
    live_status_text = status.text.lower()
    doc_text = download_doc.lower() + "\n" + status_doc.lower()

    windows_live = "windows" in live_download_text
    linux_live = "linux" in live_download_text
    mac_live = "mac" in live_download_text or "macos" in live_status_text
    mac_doc_note = "no public macos" in doc_text or "macos download today" in doc_text or "mac setup-script preview" in live_download_text
    review_required = "review-required" in live_status_text or "review required" in live_status_text
    rollout_state = str(release_channel_payload.get("rolloutState") or release_channel_payload.get("channelId") or "").strip()
    supportability_state = str(release_channel_payload.get("supportabilityState") or "").strip()
    public_stable = rollout_state == "public_stable"
    gold_supported = supportability_state == "gold_supported"

    payload = {
        "generated_at_utc": now_iso(),
        "contract_name": "chummer.public_download_shelf_truth",
        "base_url": base,
        "status": "fail" if review_required else "pass",
        "live": {
            "downloads_status_code": downloads.status_code,
            "status_status_code": status.status_code,
            "windows_mentioned": windows_live,
            "linux_mentioned": linux_live,
            "mac_mentioned": mac_live,
            "preview_mentioned": "preview" in live_download_text or "preview" in live_status_text,
            "review_required_mentioned": review_required,
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
            "windows_linux_truth_aligned": windows_live and linux_live,
            "mac_truth_aligned": mac_live or public_stable,
        },
        "summary": (
            "fail: review-required desktop proof language is still live"
            if review_required
            else "pass: public-stable download shelf truth is aligned"
        ),
    }
    for out_path in OUT_PATHS:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload))
    return 0 if payload["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())

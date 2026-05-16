#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import requests


OUT = Path("/docker/chummercomplete/chummer-design/_completion/full_product_every_aspect/PUBLIC_DOWNLOAD_SHELF_TRUTH.generated.json")
DOWNLOAD_DOC = Path("/docker/chummercomplete/Chummer6/DOWNLOAD.md")
STATUS_DOC = Path("/docker/chummercomplete/Chummer6/STATUS.md")


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

    live_download_text = downloads.text.lower()
    live_status_text = status.text.lower()
    doc_text = download_doc.lower() + "\n" + status_doc.lower()

    windows_live = "windows" in live_download_text
    linux_live = "linux" in live_download_text
    mac_unavailable = "no public macos" in doc_text or "macos download today" in doc_text or "mac setup-script preview" in live_download_text
    preview_live = "preview" in live_download_text and "preview" in live_status_text and "preview" in doc_text
    review_required = "review-required" in live_status_text or "review required" in live_status_text

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
            "mac_unavailable_mentioned": "mac" in live_download_text,
            "preview_mentioned": "preview" in live_download_text,
            "review_required_mentioned": review_required,
        },
        "docs": {
            "download_doc_exists": DOWNLOAD_DOC.exists(),
            "status_doc_exists": STATUS_DOC.exists(),
            "preview_mentioned": "preview" in doc_text,
            "mac_unavailable_mentioned": mac_unavailable,
        },
        "alignment": {
            "preview_truth_aligned": preview_live,
            "windows_linux_truth_aligned": windows_live and linux_live,
            "mac_truth_aligned": mac_unavailable,
        },
        "summary": "fail: review-required desktop proof language is still live" if review_required else "pass: public download shelf truth is aligned",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload))
    return 0 if payload["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())

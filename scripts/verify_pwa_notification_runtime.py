#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import re
import sys
from pathlib import Path
from urllib.parse import urljoin

import requests


ROOT = Path(__file__).resolve().parents[1]
SERVICE_WORKER = ROOT / "Chummer.Run.Api" / "wwwroot" / "service-worker.js"
SERVICE_WORKER_REGISTRATION_RE = re.compile(r'serviceWorker\.register\("([^"]*service-worker\.js[^"]*)"')

REQUIRED_MARKERS = (
    'self.addEventListener("push"',
    'self.addEventListener("notificationclick"',
    'self.addEventListener("notificationclose"',
    "self.registration.showNotification(",
    'clients.openWindow',
    'client.postMessage({ type, payload })',
    "normalizeNotificationHref(",
    "tryNormalizeNotificationHref(",
    "normalizeNotificationAssetPath(",
    "tryNormalizeNotificationAssetPath(",
    "resolveNotificationActionHref(",
    "NOTIFICATION_ROUTE_PATHS",
    "NOTIFICATION_ROUTE_PREFIXES",
    "NOTIFICATION_ASSET_PATHS",
    "NOTIFICATION_ASSET_PREFIXES",
    "NOTIFICATION_ASSET_SUFFIXES",
    "isAllowedNotificationHref(",
    "isAllowedNotificationAssetPath(",
    "isPublicRuntimeCacheableRequest(",
    "NON_CACHEABLE_PATH_PREFIXES",
)

def parse_args() -> argparse.Namespace:
  parser = argparse.ArgumentParser(description="Verify the PWA notification runtime and cache boundary.")
  parser.add_argument("--base-url", default="", help="Optional running Hub base URL. When provided, verify the registered service-worker asset too.")
  return parser.parse_args()


def load_service_worker_text(base_url: str) -> str:
  if not base_url:
    return SERVICE_WORKER.read_text(encoding="utf-8")

  base = base_url.rstrip("/")
  service_worker_path = "/service-worker.js"
  mobile_response = requests.get(f"{base}/mobile", timeout=30)
  if getattr(mobile_response, "ok", False):
    match = SERVICE_WORKER_REGISTRATION_RE.search(mobile_response.text)
    if match:
      service_worker_path = html.unescape(match.group(1))

  response = requests.get(urljoin(f"{base}/", service_worker_path.lstrip("/")), timeout=30)
  response.raise_for_status()
  return response.text


def main() -> int:
  args = parse_args()
  text = load_service_worker_text(args.base_url)
  missing = [marker for marker in REQUIRED_MARKERS if marker not in text]
  if missing:
    for marker in missing:
      print(f"service-worker.js missing marker: {marker}", file=sys.stderr)
    return 1
  print("pwa_notification_runtime:ok")
  return 0


if __name__ == "__main__":
  raise SystemExit(main())

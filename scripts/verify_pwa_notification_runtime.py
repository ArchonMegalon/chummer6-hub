#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SERVICE_WORKER = ROOT / "Chummer.Run.Api" / "wwwroot" / "service-worker.js"

REQUIRED_MARKERS = (
    'self.addEventListener("push"',
    'self.addEventListener("notificationclick"',
    'self.addEventListener("notificationclose"',
    "self.registration.showNotification(",
    'clients.openWindow',
    'client.postMessage({ type, payload })',
    "normalizeNotificationHref(",
    "normalizeNotificationAssetPath(",
    "resolveNotificationActionHref(",
    "isPublicRuntimeCacheableRequest(",
    "NON_CACHEABLE_PATH_PREFIXES",
)


def main() -> int:
  text = SERVICE_WORKER.read_text(encoding="utf-8")
  missing = [marker for marker in REQUIRED_MARKERS if marker not in text]
  if missing:
    for marker in missing:
      print(f"service-worker.js missing marker: {marker}", file=sys.stderr)
    return 1
  print("pwa_notification_runtime:ok")
  return 0


if __name__ == "__main__":
  raise SystemExit(main())

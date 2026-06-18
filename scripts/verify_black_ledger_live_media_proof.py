#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
PUBLISHED_ROOT = REPO_ROOT / ".codex-studio" / "published"
OUTPUT_PATH = PUBLISHED_ROOT / "BLACK_LEDGER_LIVE_MEDIA_PROOF.generated.json"
SCREENSHOT_ROOT = PUBLISHED_ROOT / "black-ledger-live-media"
CAPTURE_ATTEMPTS = 3
MIN_SCREENSHOT_BYTES = 100_000


def now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")

NODE_SCRIPT = r"""
const fs = require("fs");
const path = require("path");
const { chromium } = require("playwright");

async function main() {
  const config = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));
  const browser = await chromium.launch({ headless: true });
  const entries = [];
  try {
    for (const viewport of config.viewports) {
      const context = await browser.newContext({
        viewport: { width: viewport.width, height: viewport.height },
        isMobile: !!viewport.mobile,
        hasTouch: !!viewport.mobile,
        userAgent: "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36",
      });
      const page = await context.newPage();
      page.setDefaultNavigationTimeout(90000);
      for (const route of config.routes) {
        const url = `${config.baseUrl}${route.path}`;
        let response = null;
        let lastError = null;
        for (let attempt = 0; attempt < 2; attempt += 1) {
          try {
            response = await page.goto(url, { waitUntil: "domcontentloaded", timeout: 90000 });
            break;
          } catch (error) {
            lastError = error;
          }
        }
        if (!response && lastError) {
          throw lastError;
        }
        if (!response || response.status() !== 200) {
          throw new Error(`Unexpected status ${response ? response.status() : "none"} for ${url}`);
        }
        const bodyText = await page.locator("body").innerText();
        const matchedNeedle = route.needles.find((needle) => bodyText.includes(needle));
        if (!matchedNeedle) {
          throw new Error(`Expected one of [${route.needles.join(", ")}] on ${url}`);
        }
        const visualSignals = await page.evaluate(() => {
          const text = document.body.innerText || "";
          const lower = text.toLowerCase();
          const count = (needle) => lower.split(needle.toLowerCase()).length - 1;
          const media = Array.from(document.querySelectorAll("video,img,picture,canvas,svg,[data-geoscape-panel],[data-geoscape-controls],[data-geoscape-signal-rail]"));
          let largestMediaArea = 0;
          for (const element of media) {
            const rect = element.getBoundingClientRect();
            largestMediaArea = Math.max(largestMediaArea, Math.round(rect.width * rect.height));
          }
          return {
            textLength: text.length,
            blackLedgerMentions: count("Black Ledger"),
            commandMapMentions: count("command map"),
            globeMentions: count("globe"),
            factionMentions: count("faction"),
            pressureMentions: count("pressure"),
            newsreelMentions: count("newsreel"),
            videoMentions: count("video"),
            mediaElementCount: media.length,
            videoElementCount: document.querySelectorAll("video").length,
            imageElementCount: document.querySelectorAll("img,picture").length,
            svgElementCount: document.querySelectorAll("svg").length,
            geoscapePanelCount: document.querySelectorAll("[data-geoscape-panel]").length,
            geoscapeControlCount: document.querySelectorAll("[data-geoscape-controls]").length,
            geoscapeSignalRailCount: document.querySelectorAll("[data-geoscape-signal-rail]").length,
            largestMediaArea,
            viewportArea: window.innerWidth * window.innerHeight,
          };
        });
        const screenshotPath = path.join(config.outputRoot, viewport.name, `${route.label}.png`);
        fs.mkdirSync(path.dirname(screenshotPath), { recursive: true });
        await page.screenshot({ path: screenshotPath, fullPage: true });
        const screenshotBytes = fs.statSync(screenshotPath).size;
        entries.push({
          route: route.path,
          viewport: viewport.name,
          finalUrl: page.url(),
          screenshotPath,
          screenshotBytes,
          visualSignals,
        });
      }
      await context.close();
    }
  } finally {
    await browser.close();
  }
  fs.writeFileSync(process.argv[3], JSON.stringify({ entries }, null, 2) + "\n", "utf8");
}

main().catch((error) => {
  console.error(error && error.stack ? error.stack : String(error));
  process.exit(1);
});
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Capture live Black Ledger flagship screenshots and fail closed if they cannot be proven.")
    parser.add_argument("--base-url", default="https://chummer.run")
    return parser.parse_args()


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def validate_entries(entries: list[dict[str, Any]]) -> tuple[list[str], dict[str, Any]]:
    failures: list[str] = []
    expected_pairs = {
        ("/ledger/map", "desktop"),
        ("/ledger/map", "mobile"),
        ("/ledger/newsroom", "desktop"),
        ("/ledger/newsroom", "mobile"),
        ("/ledger/factions/ashline-circle/promo", "desktop"),
        ("/ledger/factions/ashline-circle/promo", "mobile"),
        ("/ledger/map?replay=turn-1", "desktop"),
        ("/ledger/map?replay=turn-1", "mobile"),
    }
    actual_pairs = {(str(entry.get("route")), str(entry.get("viewport"))) for entry in entries}
    missing_pairs = sorted(expected_pairs - actual_pairs)
    for route, viewport in missing_pairs:
        failures.append(f"missing screenshot capture for {route} on {viewport}")

    media_quality: dict[str, Any] = {
        "screenshot_min_bytes": MIN_SCREENSHOT_BYTES,
        "routes_checked": sorted({str(entry.get("route")) for entry in entries}),
        "viewports_checked": sorted({str(entry.get("viewport")) for entry in entries}),
        "large_visual_centerpiece": False,
        "faction_markers_visible": False,
        "pressure_signals_visible": False,
        "newsreel_or_video_surface_visible": False,
        "geoscape_controls_visible": False,
        "newsroom_route_verified": False,
        "faction_promo_verified": False,
        "replay_route_verified": False,
    }

    for entry in entries:
        route = str(entry.get("route"))
        viewport = str(entry.get("viewport"))
        final_url = str(entry.get("finalUrl") or "")
        screenshot_path = Path(str(entry.get("screenshotPath") or ""))
        screenshot_bytes = int(entry.get("screenshotBytes") or 0)
        if not screenshot_path.is_file():
            failures.append(f"screenshot missing on disk for {route} on {viewport}: {screenshot_path}")
        elif screenshot_bytes < MIN_SCREENSHOT_BYTES:
            failures.append(f"screenshot is too small to prove visual surface for {route} on {viewport}: {screenshot_bytes} bytes")

        signals = entry.get("visualSignals") if isinstance(entry.get("visualSignals"), dict) else {}
        largest_area = int(signals.get("largestMediaArea") or 0)
        viewport_area = int(signals.get("viewportArea") or 1)
        if route == "/ledger/map":
            media_quality["large_visual_centerpiece"] = media_quality["large_visual_centerpiece"] or largest_area >= int(viewport_area * 0.20)
            media_quality["faction_markers_visible"] = media_quality["faction_markers_visible"] or int(signals.get("factionMentions") or 0) >= 6
            media_quality["pressure_signals_visible"] = media_quality["pressure_signals_visible"] or int(signals.get("pressureMentions") or 0) >= 4
            media_quality["newsreel_or_video_surface_visible"] = media_quality["newsreel_or_video_surface_visible"] or (
                int(signals.get("newsreelMentions") or 0) > 0 or int(signals.get("videoMentions") or 0) > 0
            )
            media_quality["geoscape_controls_visible"] = media_quality["geoscape_controls_visible"] or (
                int(signals.get("geoscapePanelCount") or 0) > 0
                and int(signals.get("geoscapeControlCount") or 0) > 0
                and int(signals.get("geoscapeSignalRailCount") or 0) > 0
            )
        elif route == "/ledger/newsroom":
            media_quality["newsroom_route_verified"] = media_quality["newsroom_route_verified"] or (
                "/ledger/newsroom/turn-" in final_url
                and int(signals.get("videoElementCount") or 0) > 0
                and int(signals.get("newsreelMentions") or 0) > 0
            )
            media_quality["newsreel_or_video_surface_visible"] = media_quality["newsreel_or_video_surface_visible"] or int(signals.get("videoElementCount") or 0) > 0
        elif route == "/ledger/factions/ashline-circle/promo":
            media_quality["faction_promo_verified"] = media_quality["faction_promo_verified"] or (
                "/ledger/factions/ashline-circle/promo" in final_url
                and int(signals.get("videoElementCount") or 0) > 0
                and int(signals.get("factionMentions") or 0) > 0
            )
        elif route == "/ledger/map?replay=turn-1":
            media_quality["replay_route_verified"] = media_quality["replay_route_verified"] or (
                "/ledger/map" in final_url
                and int(signals.get("commandMapMentions") or 0) > 0
                and int(signals.get("textLength") or 0) > 0
            )

    for key in (
        "large_visual_centerpiece",
        "faction_markers_visible",
        "pressure_signals_visible",
        "newsreel_or_video_surface_visible",
        "geoscape_controls_visible",
        "newsroom_route_verified",
        "faction_promo_verified",
        "replay_route_verified",
    ):
        if not media_quality[key]:
            failures.append(f"Black Ledger media quality signal failed: {key}")

    return failures, media_quality


def main() -> int:
    args = parse_args()
    base_url = args.base_url.rstrip("/")
    SCREENSHOT_ROOT.mkdir(parents=True, exist_ok=True)
    config = {
        "baseUrl": base_url,
        "outputRoot": str(SCREENSHOT_ROOT),
        "routes": [
            {"path": "/ledger/map", "label": "ledger-map", "needles": ["command map", "Emerald Sprawl", "Pressure"]},
            {"path": "/ledger/newsroom", "label": "ledger-newsroom", "needles": ["Black Ledger Newsroom", "Transcript", "Published:"]},
            {"path": "/ledger/factions/ashline-circle/promo", "label": "ledger-faction-promo", "needles": ["Ashline Circle", "Open watch page", "Open captions"]},
            {"path": "/ledger/map?replay=turn-1", "label": "ledger-replay-turn-1", "needles": ["command map", "Turn 1", "Pressure"]},
        ],
        "viewports": [
            {"name": "desktop", "width": 1440, "height": 900, "mobile": False},
            {"name": "mobile", "width": 390, "height": 844, "mobile": True},
        ],
    }

    with tempfile.TemporaryDirectory(prefix="black-ledger-live-media-") as temp_dir:
        temp_root = Path(temp_dir)
        config_path = temp_root / "config.json"
        script_path = temp_root / "capture.cjs"
        result_path = temp_root / "result.json"
        config_path.write_text(json.dumps(config), encoding="utf-8")
        script_path.write_text(NODE_SCRIPT, encoding="utf-8")
        env = os.environ.copy()
        node_path_entries = [str(REPO_ROOT / "node_modules")]
        if env.get("NODE_PATH"):
            node_path_entries.append(env["NODE_PATH"])
        env["NODE_PATH"] = os.pathsep.join(node_path_entries)
        completed = None
        attempts: list[dict[str, Any]] = []
        for attempt in range(1, CAPTURE_ATTEMPTS + 1):
            completed = subprocess.run(
                ["node", str(script_path), str(config_path), str(result_path)],
                cwd=REPO_ROOT,
                env=env,
                capture_output=True,
                text=True,
            )
            attempts.append(
                {
                    "attempt": attempt,
                    "returncode": completed.returncode,
                    "stdout": completed.stdout.strip(),
                    "stderr": completed.stderr.strip(),
                }
            )
            if completed.returncode == 0:
                break

        payload = {
            "contract_name": "chummer.black_ledger_live_media_proof",
            "generated_at_utc": now_iso(),
            "base_url": base_url,
            "status": "pass" if completed and completed.returncode == 0 else "fail",
            "capture_mode": "playwright_screenshot",
            "attempt_count": len(attempts),
            "stdout": completed.stdout.strip() if completed else "",
            "stderr": completed.stderr.strip() if completed else "",
            "attempts": attempts,
            "screenshots": [],
            "media_quality": {},
            "human_creative_review": {
                "path": "/docker/chummercomplete/chummer-design/products/chummer/FINAL_PRODUCT_DESIGN_REVIEW.md",
                "status": "required",
                "scope": "Large Black Ledger command-map centerpiece, readable faction/pressure signals, newsroom/video presence, desktop and mobile framing."
            },
            "failures": [],
        }
        if completed and completed.returncode == 0 and result_path.is_file():
            payload["screenshots"] = json.loads(result_path.read_text(encoding="utf-8")).get("entries", [])
            failures, media_quality = validate_entries(payload["screenshots"])
            payload["media_quality"] = media_quality
            payload["failures"] = failures
            if failures:
                payload["status"] = "fail"

    write_json(OUTPUT_PATH, payload)
    if payload["status"] != "pass":
        raise SystemExit("black ledger live media proof failed")
    print("black_ledger_live_media_proof:ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

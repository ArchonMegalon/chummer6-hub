#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
PUBLISHED_ROOT = REPO_ROOT / ".codex-studio" / "published"
OUTPUT_PATH = PUBLISHED_ROOT / "BLACK_LEDGER_LIVE_MEDIA_PROOF.generated.json"
SCREENSHOT_ROOT = PUBLISHED_ROOT / "black-ledger-live-media"

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
        const screenshotPath = path.join(config.outputRoot, viewport.name, `${route.label}.png`);
        fs.mkdirSync(path.dirname(screenshotPath), { recursive: true });
        await page.screenshot({ path: screenshotPath, fullPage: true });
        entries.push({ route: route.path, viewport: viewport.name, screenshotPath });
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


def main() -> int:
    args = parse_args()
    base_url = args.base_url.rstrip("/")
    SCREENSHOT_ROOT.mkdir(parents=True, exist_ok=True)
    config = {
        "baseUrl": base_url,
        "outputRoot": str(SCREENSHOT_ROOT),
        "routes": [
            {"path": "/", "label": "home", "needles": ["Open Black Ledger", "Black Ledger command deck", "Turn 1"]},
            {"path": "/ledger/map", "label": "ledger-map", "needles": ["command map", "Emerald Sprawl", "Pressure"]},
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
        completed = subprocess.run(
            ["node", str(script_path), str(config_path), str(result_path)],
            cwd=REPO_ROOT,
            env=env,
            capture_output=True,
            text=True,
        )

        payload = {
            "contract_name": "chummer.black_ledger_live_media_proof",
            "base_url": base_url,
            "status": "pass" if completed.returncode == 0 else "fail",
            "capture_mode": "playwright_screenshot",
            "stdout": completed.stdout.strip(),
            "stderr": completed.stderr.strip(),
            "screenshots": [],
        }
        if completed.returncode == 0 and result_path.is_file():
            payload["screenshots"] = json.loads(result_path.read_text(encoding="utf-8")).get("entries", [])

    write_json(OUTPUT_PATH, payload)
    if payload["status"] != "pass":
        raise SystemExit("black ledger live media proof failed")
    print("black_ledger_live_media_proof:ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

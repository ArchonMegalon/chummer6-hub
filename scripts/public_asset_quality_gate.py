#!/usr/bin/env python3
from __future__ import annotations

import argparse
from html.parser import HTMLParser

import requests

from absolute_completion_common import LocalHubApp, completion_path, now_iso, write_json, write_text


ALLOWED_RASTER_EXTENSIONS = (".png", ".jpg", ".jpeg", ".webp", ".avif")


class ImgParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.images: list[dict[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "img":
            return
        self.images.append({key: value or "" for key, value in attrs})


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify the flagship landing page includes raster imagery with alt text.")
    parser.add_argument("--base-url", default="", help="Optional running Hub base URL. When omitted the script launches a temporary local Hub.")
    parser.add_argument("--route", default="/", help="Public route to verify. Defaults to landing page.")
    return parser.parse_args()


def run(base_url: str, route: str) -> int:
    failures: list[str] = []
    normalized_route = route if route.startswith("/") else f"/{route}"
    response = requests.get(f"{base_url}{normalized_route}", timeout=30)
    response.raise_for_status()
    parser = ImgParser()
    parser.feed(response.text)

    if not parser.images:
        failures.append("no img tags found on the landing page")

    raster_count = 0
    for image in parser.images:
        src = image.get("src", "")
        alt = image.get("alt", "").strip()
        if not alt:
            failures.append(f"img missing alt text: {src or '<empty src>'}")
        if src.lower().endswith(ALLOWED_RASTER_EXTENSIONS):
            raster_count += 1

    if raster_count == 0:
        failures.append("no raster img sources found on the landing page")

    payload = {
        "contract_name": "chummer.public_asset_quality_gate",
        "status": "pass" if not failures else "fail",
        "generated_at_utc": now_iso(),
        "base_url": base_url,
        "route": normalized_route,
        "html_status_code": response.status_code,
        "image_count": len(parser.images),
        "raster_image_count": raster_count,
        "failure_count": len(failures),
        "failures": failures,
    }
    write_json(completion_path("PUBLIC_ASSET_QUALITY_GATE.generated.json"), payload)

    lines = [
        "# Public asset quality gate",
        "",
        f"- Generated: {payload['generated_at_utc']}",
        f"- Base URL: {base_url}",
        f"- Route: `{normalized_route}`",
        f"- Status: `{payload['status']}`",
        f"- Raster image count: `{payload['raster_image_count']}`",
        f"- Failure count: `{payload['failure_count']}`",
    ]
    if failures:
        lines.extend(["", "## Failures", ""])
        lines.extend(f"- {failure}" for failure in failures)
    else:
        lines.extend(["", "Flagship landing imagery uses raster sources with alt text on the public page."])
    write_text(completion_path("PUBLIC_ASSET_QUALITY_GATE.md"), "\n".join(lines))
    return 0 if not failures else 1


def main() -> int:
    args = parse_args()
    if args.base_url:
        return run(args.base_url.rstrip("/"), args.route)

    with LocalHubApp() as app:
        return run(app.base_url, args.route)


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
from __future__ import annotations

import argparse
import io
from html.parser import HTMLParser
import os
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from PIL import Image, ImageFilter, ImageStat

from absolute_completion_common import LocalHubApp, now_iso, write_json, write_text


ALLOWED_RASTER_EXTENSIONS = (".png", ".jpg", ".jpeg", ".webp", ".avif")
DEFAULT_COMPLETION_DIR = Path("/docker/chummercomplete/_completion/chummer_run_redesign_closure")
MAX_UPSCALE_RATIO = 1.25
MIN_HERO_WIDTH = 1600
MIN_BLUR_METRIC = 2.0


class ImgParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.images: list[dict[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "img":
            return
        self.images.append({key: value or "" for key, value in attrs})


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify the flagship landing page includes high-quality raster imagery with alt text.")
    parser.add_argument("--base-url", default="", help="Optional running Hub base URL. When omitted the script launches a temporary local Hub.")
    parser.add_argument("--route", default="/", help="Public route to verify. Defaults to landing page.")
    return parser.parse_args()


def completion_root() -> Path:
    raw = os.environ.get("CHUMMER_COMPLETION_DIR", "").strip()
    return Path(raw) if raw else DEFAULT_COMPLETION_DIR


def completion_path(file_name: str) -> Path:
    root = completion_root()
    root.mkdir(parents=True, exist_ok=True)
    return root / file_name


def parse_dimension(raw: str) -> int | None:
    if not raw:
        return None
    digits = "".join(character for character in raw if character.isdigit())
    return int(digits) if digits else None


def blur_metric(image: Image.Image) -> float:
    grayscale = image.convert("L")
    edges = grayscale.filter(ImageFilter.FIND_EDGES)
    stat = ImageStat.Stat(edges)
    return float(stat.var[0]) if stat.var else 0.0


def image_quality_row(base_url: str, image: dict[str, str]) -> tuple[dict[str, object], list[str]]:
    src = image.get("src", "")
    resolved_src = urljoin(base_url, src)
    response = requests.get(resolved_src, timeout=30)
    response.raise_for_status()
    content_type = response.headers.get("Content-Type", "")
    file_size = len(response.content)

    natural_width: int | None = None
    natural_height: int | None = None
    blur_value: float | None = None
    format_name = content_type or Path(urlparse(resolved_src).path).suffix.lstrip(".")
    warnings: list[str] = []
    failures: list[str] = []
    try:
        with Image.open(io.BytesIO(response.content)) as pil_image:
            natural_width, natural_height = pil_image.size
            blur_value = blur_metric(pil_image)
            format_name = pil_image.format or format_name
    except Exception as exc:
        failures.append(f"unable to inspect image bytes: {resolved_src} ({exc})")

    width_attr = parse_dimension(image.get("width", ""))
    height_attr = parse_dimension(image.get("height", ""))
    style = image.get("style", "")
    rendered_width = width_attr or parse_dimension(style) or natural_width
    rendered_height = height_attr or natural_height
    upscale_ratio = 1.0
    if natural_width and rendered_width:
        upscale_ratio = rendered_width / natural_width

    is_hero_candidate = "hero" in " ".join(
        [image.get("class", ""), image.get("alt", ""), src]
    ).lower()
    overlay_readability = "assumed-pass"
    crop_warning = None
    if not width_attr or not height_attr:
        warnings.append("rendered dimensions inferred from natural image size")
    if upscale_ratio > MAX_UPSCALE_RATIO:
        failures.append(
            f"image appears upscaled beyond {MAX_UPSCALE_RATIO:.2f}x ({upscale_ratio:.2f}x): {resolved_src}"
        )
    if natural_width is None or natural_height is None:
        failures.append(f"natural image dimensions unavailable: {resolved_src}")
    if is_hero_candidate and natural_width is not None and natural_width < MIN_HERO_WIDTH:
        failures.append(
            f"hero image below minimum desktop width {MIN_HERO_WIDTH}px ({natural_width}px): {resolved_src}"
        )
    if blur_value is not None and blur_value < MIN_BLUR_METRIC:
        failures.append(f"image sharpness proxy below threshold ({blur_value:.2f}): {resolved_src}")
    if file_size > 1_500_000:
        warnings.append(f"large image payload ({file_size} bytes)")
    if is_hero_candidate and natural_width and natural_height:
        aspect_ratio = natural_width / max(natural_height, 1)
        if aspect_ratio < 1.2:
            crop_warning = "hero image is unusually tall and may crop poorly on wide screens"
            warnings.append(crop_warning)

    row = {
        "src": src,
        "resolved_src": resolved_src,
        "alt": image.get("alt", "").strip(),
        "natural_width": natural_width,
        "natural_height": natural_height,
        "rendered_width": rendered_width,
        "rendered_height": rendered_height,
        "upscale_ratio": round(upscale_ratio, 3),
        "format": str(format_name).lower(),
        "file_size": file_size,
        "blur_metric": None if blur_value is None else round(blur_value, 3),
        "object_fit": image.get("style", ""),
        "crop_warning": crop_warning,
        "overlay_readability": overlay_readability,
        "status": "pass" if not failures else "fail",
        "warnings": warnings,
    }
    return row, failures


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

    image_rows: list[dict[str, object]] = []
    payload = {
        "contract_name": "chummer.public_asset_quality_gate",
        "generated_at_utc": now_iso(),
        "base_url": base_url,
        "route": normalized_route,
        "html_status_code": response.status_code,
        "image_count": len(parser.images),
        "raster_image_count": raster_count,
        "images": image_rows,
    }

    for image in parser.images:
        src = image.get("src", "")
        if not src.lower().endswith(ALLOWED_RASTER_EXTENSIONS):
            continue
        row, image_failures = image_quality_row(base_url, image)
        image_rows.append(row)
        failures.extend(image_failures)

    payload["status"] = "pass" if not failures else "fail"
    payload["failure_count"] = len(failures)
    payload["failures"] = failures
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
    if image_rows:
        lines.extend(["", "## Image rows", ""])
        for row in image_rows:
            lines.append(
                f"- `{row['resolved_src']}`: status `{row['status']}`, "
                f"natural `{row['natural_width']}x{row['natural_height']}`, "
                f"rendered `{row['rendered_width']}x{row['rendered_height']}`, "
                f"upscale `{row['upscale_ratio']}`, blur `{row['blur_metric']}`"
            )
    if failures:
        lines.extend(["", "## Failures", ""])
        lines.extend(f"- {failure}" for failure in failures)
    else:
        lines.extend(["", "Flagship landing imagery passes raster, alt-text, size, and sharpness checks."])
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

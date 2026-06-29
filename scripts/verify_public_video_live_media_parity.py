#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
import tempfile
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


REPO = Path(__file__).resolve().parents[1]
MEDIA_ROOT = REPO / "Chummer.Run.Api" / "wwwroot" / "media"
OUTPUT = REPO / ".codex-studio" / "published" / "PUBLIC_VIDEO_LIVE_MEDIA_PARITY.generated.json"
VIDEO_EXTENSIONS = {".mp4", ".webm"}
DEFAULT_BASE_URL = "https://chummer.run"


@dataclass(frozen=True)
class DownloadedMedia:
    path: Path
    status_code: int
    headers: dict[str, str]


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def video_files(media_root: Path) -> list[Path]:
    return sorted(
        path
        for path in media_root.rglob("*")
        if path.is_file() and path.suffix.lower() in VIDEO_EXTENSIONS
    )


def public_path_for(media_root: Path, path: Path) -> str:
    return "/" + str(path.relative_to(media_root.parent)).replace("\\", "/")


def receipt_path_for(media_root: Path, path: Path) -> str:
    try:
        return str(path.relative_to(REPO))
    except ValueError:
        return str(Path("media") / path.relative_to(media_root))


def cache_busted_url(base_url: str, public_path: str, digest: str) -> str:
    separator = "&" if "?" in public_path else "?"
    token = f"live-parity-{digest[:16]}"
    return f"{base_url.rstrip('/')}{public_path}{separator}v={urllib.parse.quote(token)}"


def allows_clean_speech_pauses(audio_module: Any, path: Path) -> bool:
    clean_speech_groups = set(getattr(audio_module, "CLEAN_SPEECH_AUDIO_GROUPS", set()))
    return path.stem in clean_speech_groups


def load_audio_module():
    script = REPO / "scripts" / "public_video_audio_quality.py"
    spec = importlib.util.spec_from_file_location("public_video_audio_quality_for_live_parity", script)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"failed to load audio verifier: {script}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def download_file(url: str, output: Path, timeout: int) -> DownloadedMedia:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "chummer-public-video-live-media-parity/1.0",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        output.write_bytes(response.read())
        headers = {key.lower(): value for key, value in response.headers.items()}
        return DownloadedMedia(output, getattr(response, "status", 200), headers)


def verify_file(
    path: Path,
    *,
    media_root: Path,
    base_url: str,
    timeout: int,
    temp_root: Path,
    require_no_store: bool,
    audio_module: Any,
) -> dict[str, Any]:
    local_digest = sha256_file(path)
    local_size = path.stat().st_size
    public_path = public_path_for(media_root, path)
    url = cache_busted_url(base_url, public_path, local_digest)
    downloaded_path = temp_root / f"{local_digest[:16]}-{path.name}"
    downloaded = download_file(url, downloaded_path, timeout)
    downloaded_digest = sha256_file(downloaded.path)
    downloaded_size = downloaded.path.stat().st_size

    clean_speech_pauses = allows_clean_speech_pauses(audio_module, path)
    quality = audio_module.audio_quality(downloaded.path, allow_clean_speech_pauses=clean_speech_pauses)
    probe = audio_module.probe(downloaded.path)
    streams = probe.get("streams") or []
    audio_streams = sum(1 for stream in streams if stream.get("codec_type") == "audio")
    video_streams = sum(1 for stream in streams if stream.get("codec_type") == "video")

    cache_control = downloaded.headers.get("cache-control", "")
    cdn_cache_control = downloaded.headers.get("cdn-cache-control", "")
    cloudflare_cache_control = downloaded.headers.get("cloudflare-cdn-cache-control", "")
    cloudflare_status = downloaded.headers.get("cf-cache-status", "")

    issues: list[str] = []
    if downloaded.status_code < 200 or downloaded.status_code >= 300:
        issues.append(f"http_status_{downloaded.status_code}")
    if downloaded_digest != local_digest:
        issues.append("download_sha256_mismatch")
    if downloaded_size != local_size:
        issues.append("download_size_mismatch")
    if audio_streams != 1:
        issues.append("audio_stream_count")
    if video_streams != 1:
        issues.append("video_stream_count")
    if quality.get("status") != "pass":
        issues.extend(str(reason) for reason in quality.get("reasons") or ["audio_quality_failed"])
    if require_no_store:
        header_blob = " ".join((cache_control, cdn_cache_control, cloudflare_cache_control)).lower()
        if "no-store" not in header_blob:
            issues.append("missing_no_store_cache_header")
        if cloudflare_status.strip().upper() == "HIT":
            issues.append("cloudflare_cache_hit")

    return {
        "file": receipt_path_for(media_root, path),
        "public_path": public_path,
        "url": url,
        "status": "pass" if not issues else "fail",
        "issues": issues,
        "local_sha256": local_digest,
        "download_sha256": downloaded_digest,
        "local_size_bytes": local_size,
        "download_size_bytes": downloaded_size,
        "http_status": downloaded.status_code,
        "headers": {
            "cache_control": cache_control,
            "cdn_cache_control": cdn_cache_control,
            "cloudflare_cdn_cache_control": cloudflare_cache_control,
            "cf_cache_status": cloudflare_status,
        },
        "audio_streams": audio_streams,
        "video_streams": video_streams,
        "clean_speech_pauses_allowed": clean_speech_pauses,
        "quality": quality,
    }


def verify_all(
    *,
    media_root: Path,
    base_url: str,
    timeout: int,
    require_no_store: bool,
    limit: int | None = None,
) -> dict[str, Any]:
    files = video_files(media_root)
    if limit is not None:
        files = files[:limit]
    audio_module = load_audio_module()
    with tempfile.TemporaryDirectory(prefix="chummer-live-video-parity-") as temp:
        temp_root = Path(temp)
        assets = [
            verify_file(
                path,
                media_root=media_root,
                base_url=base_url,
                timeout=timeout,
                temp_root=temp_root,
                require_no_store=require_no_store,
                audio_module=audio_module,
            )
            for path in files
        ]
    issues = [
        f"{asset['public_path']}:{issue}"
        for asset in assets
        for issue in asset.get("issues", [])
    ]
    return {
        "contract_name": "chummer.public_video_live_media_parity.v1",
        "generated_at_utc": utc_now(),
        "status": "pass" if not issues else "fail",
        "base_url": base_url.rstrip("/"),
        "scope": {
            "definition": "all public MP4/WebM files under Chummer.Run.Api/wwwroot/media, downloaded through the public origin with a content-addressed cache-busting query",
            "media_root": str(media_root),
            "file_count": len(files),
            "require_no_store_headers": require_no_store,
        },
        "hard_exit_gate": {
            "download_sha256_must_match_local_asset": True,
            "download_size_must_match_local_asset": True,
            "audio_streams_required": 1,
            "video_streams_required": 1,
            "downloaded_audio_quality_must_pass": True,
            "declared_clean_speech_groups_allow_natural_speech_pauses": True,
            "cache_headers_must_be_no_store": require_no_store,
            "cloudflare_hit_rejected": require_no_store,
        },
        "issues": issues,
        "assets": assets,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify live public video URLs match local assets and pass audio gates.")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--media-root", type=Path, default=MEDIA_ROOT)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--skip-no-store-check", action="store_true")
    parser.add_argument("--limit", type=int, default=None, help="Testing/debug only: verify the first N videos.")
    args = parser.parse_args()

    result = verify_all(
        media_root=args.media_root.resolve(),
        base_url=args.base_url,
        timeout=args.timeout,
        require_no_store=not args.skip_no_store_check,
        limit=args.limit,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": result["status"], "file_count": result["scope"]["file_count"], "out": str(args.output)}, indent=2))
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())

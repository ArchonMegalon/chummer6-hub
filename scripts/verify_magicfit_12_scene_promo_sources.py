#!/usr/bin/env python3
from __future__ import annotations

import json
import hashlib
import subprocess
from datetime import UTC, datetime
from pathlib import Path


WORKSPACE = Path("/docker/chummercomplete")
SOURCE_DIR = WORKSPACE / "_completion" / "magicfit_jama6_promo_12_scenes"
OUT_DIR = WORKSPACE / "_completion" / "magicfit_jama6_promo_12_scenes"
OUT_PATH = OUT_DIR / "MAGICFIT_12_SCENE_PROMO_SOURCE_AUDIT.generated.json"

REQUIRED_IDS = (
    "01_old_way_pain",
    "02_chummer6_reveal",
    "03_build_runner",
    "04_explain_values",
    "05_black_ledger_alive",
    "06_release_truth",
    "07_table_pulse",
    "08_world_reacts",
    "09_karma_forge",
    "10_newsroom",
    "11_play_anywhere",
    "12_hero_ending",
)


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def probe(path: Path) -> dict[str, object]:
    return json.loads(
        subprocess.check_output(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration:stream=codec_type,codec_name,width,height",
                "-of",
                "json",
                str(path),
            ],
            text=True,
        )
    )


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    scenes: list[dict[str, object]] = []
    missing: list[str] = []
    reasons: list[str] = []
    urls: list[str] = []
    file_hashes: list[str] = []
    for scene_id in REQUIRED_IDS:
        path = SOURCE_DIR / f"{scene_id}.mp4"
        sidecar = SOURCE_DIR / f"{scene_id}.magicfit.json"
        if not path.is_file():
            missing.append(scene_id)
            continue
        payload = json.loads(sidecar.read_text(encoding="utf-8")) if sidecar.is_file() else {}
        scene_reasons = []
        if str(payload.get("provider") or "").strip().lower() != "magicfit":
            scene_reasons.append("missing_magicfit_provider_sidecar")
        video_output_url = str(payload.get("video_output_url") or "")
        if not (
            video_output_url.startswith("https://cdn.pushowl.com/magicfit/")
            or video_output_url.startswith("https://media.powlcdn.com/magicfit/")
        ):
            scene_reasons.append("missing_magicfit_cdn_source")
        else:
            urls.append(video_output_url)
        if payload.get("faction_assets_used") is not False:
            scene_reasons.append("faction_free_source_not_proven")
        file_hashes.append(hashlib.sha256(path.read_bytes()).hexdigest())
        media = probe(path)
        duration = float(dict(media.get("format") or {}).get("duration") or 0.0)
        if duration < 4.0:
            scene_reasons.append("scene_too_short")
        if scene_reasons:
            reasons.extend([f"{scene_id}:{reason}" for reason in scene_reasons])
        scenes.append({"scene_id": scene_id, "file": str(path), "sidecar": str(sidecar), "duration_seconds": duration})

    if missing:
        reasons.extend([f"{scene_id}:missing_mp4" for scene_id in missing])
    if len(set(urls)) != len(REQUIRED_IDS):
        reasons.append(f"magicfit_cdn_urls_not_unique:{len(set(urls))}_of_{len(REQUIRED_IDS)}")
    if len(set(file_hashes)) != len(REQUIRED_IDS):
        reasons.append(f"magicfit_source_files_not_unique:{len(set(file_hashes))}_of_{len(REQUIRED_IDS)}")
    payload = {
        "generated_at_utc": utc_now(),
        "status": "pass" if not reasons and len(scenes) == len(REQUIRED_IDS) else "fail",
        "required_scene_count": len(REQUIRED_IDS),
        "found_scene_count": len(scenes),
        "source_dir": str(SOURCE_DIR),
        "unique_magicfit_cdn_url_count": len(set(urls)),
        "unique_file_sha256_count": len(set(file_hashes)),
        "scenes": scenes,
        "blocking_reasons": reasons,
    }
    OUT_PATH.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(OUT_PATH)
    return 0 if payload["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())

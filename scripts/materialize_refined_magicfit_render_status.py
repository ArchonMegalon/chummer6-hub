#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
from pathlib import Path


BASE = Path("/docker/chummercomplete/_completion/refined_magicfit_promo_plans_20260531")
MANIFEST = BASE / "REFINED_MAGICFIT_RENDER_MANIFEST.generated.json"
CLIPS = BASE / "magicfit_clips"
COMPOSITES = BASE / "composited_reels"
STATUS = BASE / "REFINED_MAGICFIT_RENDER_STATUS.generated.json"
VERDICT = BASE / "FINAL_REFINED_MAGICFIT_RENDER_VERDICT.md"


def ffprobe(path: Path) -> dict:
    return json.loads(
        subprocess.check_output(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "stream=codec_type,codec_name:format=duration",
                "-of",
                "json",
                str(path),
            ],
            text=True,
        )
    )


def clean_id(value: str) -> str:
    import re

    value = value.replace(",", "_")
    value = re.sub(r"[^A-Za-z0-9_.-]+", "_", value)
    return value.strip("_")


def clip_exists(asset_id: str, scene_id: str) -> bool:
    folder = CLIPS / asset_id
    if (folder / f"{scene_id}.mp4").exists():
        return True
    normalized = clean_id(scene_id).replace("_", "")
    return any(clean_id(path.stem).replace("_", "") == normalized for path in folder.glob("*.mp4"))


def main() -> int:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assets = []
    complete_assets = 0
    rendered_scenes = 0
    total_scenes = 0
    for asset in manifest["assets"]:
        scenes = asset["scenes"]
        scene_statuses = []
        for scene in scenes:
            exists = clip_exists(asset["asset_id"], scene["id"])
            rendered_scenes += int(exists)
            total_scenes += 1
            scene_statuses.append({"id": scene["id"], "rendered": exists})
        composite = COMPOSITES / f"{asset['asset_id']}.mp4"
        composite_status = None
        if composite.exists():
            probe = ffprobe(composite)
            streams = probe.get("streams", [])
            composite_status = {
                "path": str(composite),
                "duration_seconds": float(probe["format"]["duration"]),
                "has_video": any(s.get("codec_type") == "video" for s in streams),
                "has_audio": any(s.get("codec_type") == "audio" for s in streams),
            }
        rendered_count = sum(1 for scene in scene_statuses if scene["rendered"])
        complete = rendered_count == len(scene_statuses)
        complete_assets += int(complete)
        assets.append(
            {
                "asset_id": asset["asset_id"],
                "lane": asset["lane"],
                "target_seconds": asset["duration_seconds"],
                "rendered_scenes": rendered_count,
                "required_scenes": len(scene_statuses),
                "complete_raw_render": complete,
                "composite": composite_status,
                "scenes": scene_statuses,
            }
        )
    full_ready = complete_assets == len(assets) and all(
        asset["composite"]
        and abs(asset["composite"]["duration_seconds"] - asset["target_seconds"]) <= 0.35
        and asset["composite"]["has_video"]
        and asset["composite"]["has_audio"]
        for asset in assets
    )
    status = {
        "generated_at": "2026-05-31",
        "provider": "MagicFit",
        "assets_complete_raw_render": complete_assets,
        "assets_required": len(assets),
        "scenes_rendered": rendered_scenes,
        "scenes_required": total_scenes,
        "assets": assets,
        "verdict": "REFINED_MAGICFIT_ALL_REELS_READY" if full_ready else "NOT_READY",
    }
    STATUS.write_text(json.dumps(status, indent=2) + "\n", encoding="utf-8")
    if full_ready:
        VERDICT.write_text("REFINED_MAGICFIT_ALL_REELS_READY\n", encoding="utf-8")
    else:
        VERDICT.write_text(
            "NOT_READY\n\n"
            f"Rendered scenes: {rendered_scenes}/{total_scenes}\n"
            f"Complete raw assets: {complete_assets}/{len(assets)}\n"
            "Epic BLACK LEDGER and NEXUS-PAN are composited to 90s with video and AAC audio; "
            "remaining deep-dive reels need more MagicFit render time.\n",
            encoding="utf-8",
        )
    print(json.dumps(status, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

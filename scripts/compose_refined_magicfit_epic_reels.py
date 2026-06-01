#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import subprocess
import tempfile
from pathlib import Path


BASE = Path("/docker/chummercomplete/_completion/refined_magicfit_promo_plans_20260531")
MANIFEST = BASE / "REFINED_MAGICFIT_RENDER_MANIFEST.generated.json"
CLIPS = BASE / "magicfit_clips"
OUT_DIR = BASE / "composited_reels"
STATUS = BASE / "REFINED_MAGICFIT_RENDER_STATUS.generated.json"

EPIC_ASSETS = {"black_ledger_epic_90s", "nexus-pan_epic_90s"}


def shell(args: list[str]) -> str:
    return subprocess.check_output(args, text=True)


def ffprobe_duration(path: Path) -> float:
    data = json.loads(
        shell(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "json",
                str(path),
            ]
        )
    )
    return float(data["format"]["duration"])


def clean_id(value: str) -> str:
    value = value.replace(",", "_")
    value = re.sub(r"[^A-Za-z0-9_.-]+", "_", value)
    value = re.sub(r"_+", "_", value)
    return value.strip("_")


def clip_for(asset_id: str, scene_id: str) -> Path:
    exact = CLIPS / asset_id / f"{scene_id}.mp4"
    if exact.exists():
        return exact
    cleaned = CLIPS / asset_id / f"{clean_id(scene_id)}.mp4"
    if cleaned.exists():
        return cleaned
    prefix = clean_id(scene_id).replace("_", "")
    for candidate in sorted((CLIPS / asset_id).glob("*.mp4")):
        if clean_id(candidate.stem).replace("_", "") == prefix:
            return candidate
    raise FileNotFoundError(f"missing MagicFit clip for {asset_id}/{scene_id}")


def render_scene_segment(src: Path, dst: Path, target_seconds: int) -> dict:
    source_seconds = ffprobe_duration(src)
    stretch = max(target_seconds / source_seconds, 0.01)
    vf = (
        "scale=1280:720:force_original_aspect_ratio=decrease,"
        "pad=1280:720:(ow-iw)/2:(oh-ih)/2,"
        "setsar=1,"
        f"setpts={stretch:.8f}*PTS,"
        f"trim=duration={target_seconds},"
        "fps=30,format=yuv420p"
    )
    subprocess.check_call(
        [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-i",
            str(src),
            "-an",
            "-vf",
            vf,
            "-t",
            str(target_seconds),
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "18",
            str(dst),
        ]
    )
    return {
        "clip": str(src),
        "source_seconds": round(source_seconds, 3),
        "target_seconds": target_seconds,
        "stretch_factor": round(stretch, 4),
    }


def compose_asset(asset: dict) -> dict:
    asset_id = asset["asset_id"]
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    output = OUT_DIR / f"{asset_id}.mp4"
    segments: list[dict] = []
    with tempfile.TemporaryDirectory(prefix=f"{asset_id}_", dir=str(BASE)) as tmp:
        tmp_path = Path(tmp)
        concat = tmp_path / "concat.txt"
        concat_lines: list[str] = []
        for scene in asset["scenes"]:
            src = clip_for(asset_id, scene["id"])
            seg = tmp_path / f"{clean_id(scene['id'])}.segment.mp4"
            segments.append(render_scene_segment(src, seg, int(scene["duration_seconds"])))
            concat_lines.append(f"file '{seg}'\n")
        concat.write_text("".join(concat_lines), encoding="utf-8")
        video_only = tmp_path / "video_only.mp4"
        subprocess.check_call(
            [
                "ffmpeg",
                "-y",
                "-loglevel",
                "error",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(concat),
                "-c",
                "copy",
                str(video_only),
            ]
        )
        target_total = int(asset["duration_seconds"])
        subprocess.check_call(
            [
                "ffmpeg",
                "-y",
                "-loglevel",
                "error",
                "-i",
                str(video_only),
                "-f",
                "lavfi",
                "-t",
                str(target_total),
                "-i",
                "anullsrc=channel_layout=stereo:sample_rate=48000",
                "-map",
                "0:v:0",
                "-map",
                "1:a:0",
                "-vf",
                f"tpad=stop_mode=clone:stop_duration=1,trim=duration={target_total},setpts=PTS-STARTPTS,fps=30,format=yuv420p",
                "-c:v",
                "libx264",
                "-preset",
                "medium",
                "-crf",
                "18",
                "-c:a",
                "aac",
                str(output),
            ]
        )
    actual = ffprobe_duration(output)
    return {
        "asset_id": asset_id,
        "output": str(output),
        "target_seconds": int(asset["duration_seconds"]),
        "actual_seconds": round(actual, 3),
        "scene_count": len(asset["scenes"]),
        "segments": segments,
        "status": "composited" if abs(actual - int(asset["duration_seconds"])) <= 0.35 else "duration_mismatch",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Compose refined MagicFit reels from per-scene clips.")
    parser.add_argument("--all", action="store_true", help="Compose every asset in the refined manifest.")
    parser.add_argument("--asset", action="append", default=[], help="Compose a specific asset id; may be repeated.")
    args = parser.parse_args()
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    selected_ids = {item for item in args.asset if item}
    if args.all:
        selected = list(manifest["assets"])
    elif selected_ids:
        selected = [asset for asset in manifest["assets"] if asset["asset_id"] in selected_ids]
    else:
        selected = [asset for asset in manifest["assets"] if asset["asset_id"] in EPIC_ASSETS]
    results = [compose_asset(asset) for asset in selected]
    expected_count = len(manifest["assets"]) if args.all else len(selected)
    ready_verdict = "REFINED_MAGICFIT_ALL_REELS_COMPOSITED" if args.all else "EPIC_REELS_90S_COMPOSITED"
    summary = {
        "generated_at": "2026-06-01",
        "provider": manifest.get("provider", "MagicFit"),
        "rendered_asset_count": len(results),
        "required_asset_count": expected_count,
        "raw_clip_count": sum(result["scene_count"] for result in results),
        "composited_assets": results,
        "verdict": ready_verdict
        if len(results) == expected_count and all(r["status"] == "composited" for r in results)
        else "NOT_READY",
    }
    STATUS.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0 if summary["verdict"] == ready_verdict else 1


if __name__ == "__main__":
    raise SystemExit(main())

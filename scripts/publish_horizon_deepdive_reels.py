#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import argparse
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


SOURCE_ROOT = Path(os.environ.get("CHUMMER_HORIZON_REEL_SOURCE_ROOT") or "/docker/chummercomplete/_completion/horizon_flagship_reels_20260602/videos")
PUBLIC_ROOT = Path(os.environ.get("CHUMMER_HORIZON_PUBLIC_MEDIA_ROOT") or "/docker/chummercomplete/chummer.run-services/Chummer.Run.Api/wwwroot/media/horizons")
MANIFEST_PATH = PUBLIC_ROOT / "horizon-video-manifest.json"
VOLUME_RE = re.compile(r"(?P<kind>mean|max)_volume:\s*(?P<value>-?inf|-?\d+(?:\.\d+)?)\s*dB")
MIN_MAX_VOLUME_DB = -50.0
MIN_MEAN_VOLUME_DB = -80.0

REELS: list[dict[str, str]] = [
    {
        "horizon_id": "nexus-pan",
        "surface_class": "core_product",
        "title": "NEXUS-PAN 90-second deep dive",
        "source": "nexus_pan_90s_deepdive.mp4",
        "output": "nexus-pan-90s-deepdive.mp4",
        "caption": "NEXUS-PAN keeps device handoffs, reconnects, and shared state honest when table tech drifts.",
    },
    {
        "horizon_id": "nexus-pan",
        "surface_class": "core_product",
        "title": "NEXUS-PAN epic 90-second reel",
        "source": "nexus-pan_epic_90s.mp4",
        "output": "nexus-pan-epic-90s.mp4",
        "caption": "A larger NEXUS-PAN story pass focused on offline truth, reconnect confidence, and trust status.",
    },
    {
        "horizon_id": "alice",
        "surface_class": "core_product",
        "title": "ALICE 90-second deep dive",
        "source": "alice_90s_deepdive.mp4",
        "output": "alice-90s-deepdive.mp4",
        "caption": "ALICE shows build tradeoffs, role fit, and upgrade paths without pretending advice is rules truth.",
    },
    {
        "horizon_id": "karma-forge",
        "surface_class": "expansion_bet",
        "title": "KARMA FORGE 90-second deep dive",
        "source": "karma_forge_90s_deepdive.mp4",
        "output": "karma-forge-90s-deepdive.mp4",
        "caption": "KARMA FORGE turns house-rule pressure into reviewable, reversible, governed rule evolution.",
    },
    {
        "horizon_id": "jackpoint",
        "surface_class": "expansion_bet",
        "title": "JACKPOINT 90-second deep dive",
        "source": "jackpoint_90s_deepdive.mp4",
        "output": "jackpoint-90s-deepdive.mp4",
        "caption": "JACKPOINT turns recap chaos into sourced dossiers, briefings, and share-safe handoffs.",
    },
    {
        "horizon_id": "runsite",
        "surface_class": "expansion_bet",
        "title": "RUNSITE 90-second deep dive",
        "source": "runsite_90s_deepdive.mp4",
        "output": "runsite-90s-deepdive.mp4",
        "caption": "RUNSITE makes locations understandable before the run without claiming VTT or tactical authority.",
    },
    {
        "horizon_id": "runbook-press",
        "surface_class": "expansion_bet",
        "title": "RUNBOOK PRESS 90-second deep dive",
        "source": "runbook_press_90s_deepdive.mp4",
        "output": "runbook-press-90s-deepdive.mp4",
        "caption": "RUNBOOK PRESS turns approved campaign material into consistent primers and books.",
    },
    {
        "horizon_id": "table-pulse",
        "surface_class": "core_product",
        "title": "TABLE PULSE 90-second deep dive",
        "source": "table_pulse_90s_deepdive.mp4",
        "output": "table-pulse-90s-deepdive.mp4",
        "caption": "TABLE PULSE separates GM-controlled live heat from private aftermath coaching.",
    },
    {
        "horizon_id": "black-ledger",
        "surface_class": "expansion_bet",
        "title": "BLACK LEDGER 90-second deep dive",
        "source": "black_ledger_90s_deepdive.mp4",
        "output": "black-ledger-90s-deepdive.mp4",
        "caption": "BLACK LEDGER shows the living city loop: map pressure, faction motion, jobs, and newsreels.",
    },
    {
        "horizon_id": "black-ledger",
        "surface_class": "expansion_bet",
        "title": "BLACK LEDGER epic 90-second reel",
        "source": "black_ledger_epic_90s.mp4",
        "output": "black-ledger-epic-90s.mp4",
        "caption": "A larger BLACK LEDGER story pass for world ticks, mission markets, and newsroom fallout.",
    },
    {
        "horizon_id": "community-hub",
        "surface_class": "expansion_bet",
        "title": "COMMUNITY HUB 90-second deep dive",
        "source": "community_hub_90s_deepdive.mp4",
        "output": "community-hub-90s-deepdive.mp4",
        "caption": "COMMUNITY HUB takes open runs from public board to roster, scheduling, venue handoff, and closeout.",
    },
    {
        "horizon_id": "origin-dossier",
        "surface_class": "core_product",
        "title": "ORIGIN DOSSIER 90-second deep dive",
        "source": "origin_dossier_90s_deepdive.mp4",
        "output": "origin-dossier-90s-deepdive.mp4",
        "caption": "ORIGIN DOSSIER turns approved runner origin canon into dossier media while keeping mechanics truth in Chummer.",
    },
]


def now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def probe(path: Path) -> dict[str, Any]:
    return json.loads(
        subprocess.check_output(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "stream=index,codec_type,codec_name:format=duration,size",
                "-of",
                "json",
                str(path),
            ],
            text=True,
        )
    )


def volume_stats(path: Path) -> dict[str, float]:
    result = subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-nostats",
            "-i",
            str(path),
            "-af",
            "volumedetect",
            "-f",
            "null",
            "-",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg volumedetect failed for {path}: {result.stderr.strip()[-500:]}")
    stats: dict[str, float] = {}
    for match in VOLUME_RE.finditer(result.stderr):
        value = match.group("value")
        stats[f"{match.group('kind')}_volume_db"] = float("-inf") if value == "-inf" else float(value)
    if "mean_volume_db" not in stats or "max_volume_db" not in stats:
        raise RuntimeError(f"ffmpeg volumedetect did not report audio volume for {path}")
    return stats


def write_vtt(path: Path, title: str, caption: str) -> None:
    path.write_text(
        "\n".join(
            [
                "WEBVTT",
                "",
                "00:00:00.000 --> 00:00:08.000",
                title,
                "",
                "00:00:08.000 --> 00:01:30.000",
                caption,
                "",
            ]
        ),
        encoding="utf-8",
    )


def publish_reel(row: dict[str, str]) -> dict[str, Any]:
    source = SOURCE_ROOT / row["source"]
    if not source.is_file():
        raise FileNotFoundError(source)
    target = PUBLIC_ROOT / row["output"]
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    vtt = target.with_suffix(".vtt")
    source_vtt = source.with_suffix(".vtt")
    if source_vtt.is_file():
        shutil.copy2(source_vtt, vtt)
    else:
        write_vtt(vtt, row["title"], row["caption"])
    metadata = probe(target)
    streams = metadata.get("streams", [])
    has_video = any(stream.get("codec_type") == "video" for stream in streams)
    has_audio = any(stream.get("codec_type") == "audio" for stream in streams)
    if not has_video or not has_audio:
        raise RuntimeError(f"{target} must have both video and audio streams")
    audio_stats = volume_stats(target)
    if (
        audio_stats["max_volume_db"] <= MIN_MAX_VOLUME_DB
        or audio_stats["mean_volume_db"] <= MIN_MEAN_VOLUME_DB
    ):
        raise RuntimeError(
            f"{target} audio is silent or placeholder-level "
            f"(mean={audio_stats['mean_volume_db']:.1f}dB, max={audio_stats['max_volume_db']:.1f}dB)"
        )
    return {
        "horizon_id": row["horizon_id"],
        "surface_id": row["horizon_id"],
        "surface_class": row.get("surface_class", "future_horizon"),
        "title": row["title"],
        "public_mp4": f"/media/horizons/{target.name}",
        "public_captions": f"/media/horizons/{vtt.name}",
        "source_completion_file": str(source),
        "caption": row["caption"],
        "duration_seconds": float(metadata["format"]["duration"]),
        "size_bytes": int(metadata["format"].get("size") or target.stat().st_size),
        "has_video": has_video,
        "has_audio": has_audio,
        "audio_mean_volume_db": audio_stats["mean_volume_db"],
        "audio_max_volume_db": audio_stats["max_volume_db"],
        "video_codec": next((stream.get("codec_name") for stream in streams if stream.get("codec_type") == "video"), ""),
        "audio_codec": next((stream.get("codec_name") for stream in streams if stream.get("codec_type") == "audio"), ""),
    }


def main() -> int:
    global SOURCE_ROOT
    parser = argparse.ArgumentParser(description="Publish composed horizon deep-dive reels into public static media.")
    parser.add_argument("--source-root", default=str(SOURCE_ROOT), help="Directory containing composited MP4 reels.")
    parser.add_argument("--only", action="append", default=[], help="Horizon id or output filename to publish; may be repeated.")
    args = parser.parse_args()
    SOURCE_ROOT = Path(args.source_root)
    only = {item for value in args.only for item in value.split(",") if item}
    rows = [
        row
        for row in REELS
        if not only or row["horizon_id"] in only or row["output"] in only or row["source"] in only
    ]
    if not rows:
        raise SystemExit("no reels selected")
    PUBLIC_ROOT.mkdir(parents=True, exist_ok=True)
    assets = [publish_reel(row) for row in rows]
    existing_assets = []
    if MANIFEST_PATH.is_file() and only:
        try:
            existing_manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
            existing_assets = [
                item
                for item in existing_manifest.get("assets", [])
                if isinstance(item, dict) and str(item.get("horizon_id") or "") not in {row["horizon_id"] for row in rows}
            ]
        except (OSError, json.JSONDecodeError):
            existing_assets = []
    merged_assets = existing_assets + assets
    manifest = {
        "contract_name": "chummer.public_product_video_manifest",
        "generated_at_utc": now_iso(),
        "publication_posture": "first_party_static_media_assets_with_audio; legacy /media/horizons path is retained for URL compatibility; surface_class distinguishes core product areas from expansion bets",
        "audio_required": True,
        "source_root": str(SOURCE_ROOT),
        "assets": merged_assets,
    }
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"published": len(assets), "manifest": str(MANIFEST_PATH)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

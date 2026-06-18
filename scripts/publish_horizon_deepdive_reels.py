#!/usr/bin/env python3
from __future__ import annotations

import json
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


SOURCE_ROOT = Path("/docker/chummercomplete/_completion/refined_magicfit_promo_plans_20260531/composited_reels")
PUBLIC_ROOT = Path("/docker/chummercomplete/chummer.run-services/Chummer.Run.Api/wwwroot/media/horizons")
MANIFEST_PATH = PUBLIC_ROOT / "horizon-video-manifest.json"

REELS: list[dict[str, str]] = [
    {
        "horizon_id": "nexus-pan",
        "title": "NEXUS-PAN 90-second deep dive",
        "source": "nexus_pan_90s_deepdive.mp4",
        "output": "nexus-pan-90s-deepdive.mp4",
        "caption": "NEXUS-PAN keeps device handoffs, reconnects, and shared state honest when table tech drifts.",
    },
    {
        "horizon_id": "nexus-pan",
        "title": "NEXUS-PAN epic 90-second reel",
        "source": "nexus-pan_epic_90s.mp4",
        "output": "nexus-pan-epic-90s.mp4",
        "caption": "A larger NEXUS-PAN story pass focused on offline truth, reconnect confidence, and trust status.",
    },
    {
        "horizon_id": "alice",
        "title": "ALICE 90-second deep dive",
        "source": "alice_90s_deepdive.mp4",
        "output": "alice-90s-deepdive.mp4",
        "caption": "ALICE shows build tradeoffs, role fit, and upgrade paths without pretending advice is rules truth.",
    },
    {
        "horizon_id": "karma-forge",
        "title": "KARMA FORGE 90-second deep dive",
        "source": "karma_forge_90s_deepdive.mp4",
        "output": "karma-forge-90s-deepdive.mp4",
        "caption": "KARMA FORGE turns house-rule pressure into reviewable, reversible, governed rule evolution.",
    },
    {
        "horizon_id": "jackpoint",
        "title": "JACKPOINT 90-second deep dive",
        "source": "jackpoint_90s_deepdive.mp4",
        "output": "jackpoint-90s-deepdive.mp4",
        "caption": "JACKPOINT turns recap chaos into sourced dossiers, briefings, and share-safe handoffs.",
    },
    {
        "horizon_id": "runsite",
        "title": "RUNSITE 90-second deep dive",
        "source": "runsite_90s_deepdive.mp4",
        "output": "runsite-90s-deepdive.mp4",
        "caption": "RUNSITE makes locations understandable before the run without claiming VTT or tactical authority.",
    },
    {
        "horizon_id": "runbook-press",
        "title": "RUNBOOK PRESS 90-second deep dive",
        "source": "runbook_press_90s_deepdive.mp4",
        "output": "runbook-press-90s-deepdive.mp4",
        "caption": "RUNBOOK PRESS turns approved campaign material into consistent primers and books.",
    },
    {
        "horizon_id": "table-pulse",
        "title": "TABLE PULSE 90-second deep dive",
        "source": "table_pulse_90s_deepdive.mp4",
        "output": "table-pulse-90s-deepdive.mp4",
        "caption": "TABLE PULSE separates GM-controlled live heat from private aftermath coaching.",
    },
    {
        "horizon_id": "black-ledger",
        "title": "BLACK LEDGER 90-second deep dive",
        "source": "black_ledger_90s_deepdive.mp4",
        "output": "black-ledger-90s-deepdive.mp4",
        "caption": "BLACK LEDGER shows the living city loop: map pressure, faction motion, jobs, and newsreels.",
    },
    {
        "horizon_id": "black-ledger",
        "title": "BLACK LEDGER epic 90-second reel",
        "source": "black_ledger_epic_90s.mp4",
        "output": "black-ledger-epic-90s.mp4",
        "caption": "A larger BLACK LEDGER story pass for world ticks, mission markets, and newsroom fallout.",
    },
    {
        "horizon_id": "community-hub",
        "title": "COMMUNITY HUB 90-second deep dive",
        "source": "community_hub_90s_deepdive.mp4",
        "output": "community-hub-90s-deepdive.mp4",
        "caption": "COMMUNITY HUB takes open runs from public board to roster, scheduling, venue handoff, and closeout.",
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
    write_vtt(vtt, row["title"], row["caption"])
    metadata = probe(target)
    streams = metadata.get("streams", [])
    has_video = any(stream.get("codec_type") == "video" for stream in streams)
    has_audio = any(stream.get("codec_type") == "audio" for stream in streams)
    if not has_video or not has_audio:
        raise RuntimeError(f"{target} must have both video and audio streams")
    return {
        "horizon_id": row["horizon_id"],
        "title": row["title"],
        "public_mp4": f"/media/horizons/{target.name}",
        "public_captions": f"/media/horizons/{vtt.name}",
        "source_completion_file": str(source),
        "caption": row["caption"],
        "duration_seconds": float(metadata["format"]["duration"]),
        "size_bytes": int(metadata["format"].get("size") or target.stat().st_size),
        "has_video": has_video,
        "has_audio": has_audio,
        "video_codec": next((stream.get("codec_name") for stream in streams if stream.get("codec_type") == "video"), ""),
        "audio_codec": next((stream.get("codec_name") for stream in streams if stream.get("codec_type") == "audio"), ""),
    }


def main() -> int:
    PUBLIC_ROOT.mkdir(parents=True, exist_ok=True)
    assets = [publish_reel(row) for row in REELS]
    manifest = {
        "contract_name": "chummer.public_horizon_video_manifest",
        "generated_at_utc": now_iso(),
        "publication_posture": "first_party_static_media_assets_with_audio; not standalone proof that every horizon is shipped",
        "audio_required": True,
        "source_root": str(SOURCE_ROOT),
        "assets": assets,
    }
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"published": len(assets), "manifest": str(MANIFEST_PATH)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

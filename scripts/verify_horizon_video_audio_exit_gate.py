#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


REPO = Path(__file__).resolve().parents[1]
MANIFEST = REPO / "Chummer.Run.Api" / "wwwroot" / "media" / "horizons" / "horizon-video-manifest.json"
AUDIO_REBUILD = REPO / "scripts" / "rebuild_public_video_audio_unmixr.py"
OUTPUT = REPO / ".codex-studio" / "published" / "HORIZON_VIDEO_AUDIO_EXIT_GATE.generated.json"
REBUILD_RECEIPT = Path("/docker/chummercomplete/_completion/public_video_audio_unmixr_20260619/PUBLIC_VIDEO_AUDIO_REBUILD.generated.json")
MIN_VIDEO_DURATION_SECONDS = 89.4
MAX_VIDEO_DURATION_SECONDS = 90.5


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_audio_module() -> Any:
    spec = importlib.util.spec_from_file_location("public_video_audio_rebuild", AUDIO_REBUILD)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load {AUDIO_REBUILD}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def public_path_to_file(public_path: str) -> Path:
    normalized = public_path.strip().split("?", 1)[0].split("#", 1)[0]
    if not normalized.startswith("/media/"):
        raise RuntimeError(f"unexpected_public_media_path:{normalized}")
    return REPO / "Chummer.Run.Api" / "wwwroot" / normalized.lstrip("/")


def rebuild_group_receipts() -> dict[str, dict[str, Any]]:
    if not REBUILD_RECEIPT.is_file():
        return {}
    try:
        payload = json.loads(REBUILD_RECEIPT.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return {
        str(group.get("group_key") or ""): group
        for group in payload.get("groups", [])
        if isinstance(group, dict) and str(group.get("group_key") or "")
    }


def verify_manifest(manifest_path: Path) -> dict[str, Any]:
    audio = load_audio_module()
    group_receipts = rebuild_group_receipts()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assets = [item for item in manifest.get("assets", []) if isinstance(item, dict) and str(item.get("public_mp4") or "")]
    rows: list[dict[str, Any]] = []
    issues: list[str] = []
    seen: set[str] = set()
    for asset in assets:
        public_mp4 = str(asset.get("public_mp4") or "").strip()
        if public_mp4 in seen:
            continue
        seen.add(public_mp4)
        path = public_path_to_file(public_mp4)
        row_issues: list[str] = []
        if not path.is_file():
            row_issues.append("mp4_missing")
            rows.append({"public_mp4": public_mp4, "status": "fail", "issues": row_issues})
            issues.extend(f"{public_mp4}:{issue}" for issue in row_issues)
            continue
        probe = audio.probe(path)
        streams = probe.get("streams") or []
        duration_seconds = float((probe.get("format") or {}).get("duration") or 0.0)
        audio_streams = sum(1 for stream in streams if stream.get("codec_type") == "audio")
        video_streams = sum(1 for stream in streams if stream.get("codec_type") == "video")
        alice_clean_audio = path.name == "alice-90s-deepdive.mp4"
        try:
            quality = audio.audio_quality(path, allow_clean_speech_pauses=alice_clean_audio)
        except TypeError:
            quality = audio.audio_quality(path)
        if not MIN_VIDEO_DURATION_SECONDS <= duration_seconds <= MAX_VIDEO_DURATION_SECONDS:
            row_issues.append("duration_not_90s")
        if audio_streams != 1:
            row_issues.append("audio_stream_count_invalid")
        if video_streams != 1:
            row_issues.append("video_stream_count_invalid")
        if quality.get("status") != "pass":
            row_issues.extend(str(item) for item in quality.get("reasons") or ["audio_quality_failed"])
        if alice_clean_audio:
            alice_receipt = group_receipts.get("alice-90s-deepdive") or {}
            provider = alice_receipt.get("provider") if isinstance(alice_receipt.get("provider"), dict) else {}
            if str(provider.get("voice_policy") or "") != "female_only":
                row_issues.append("alice_voice_policy_requires_female_news_anchor_receipt")
            alice_files = alice_receipt.get("files") if isinstance(alice_receipt.get("files"), list) else []
            alice_styles = {str(item.get("audio_style") or "") for item in alice_files if isinstance(item, dict)}
            alice_clean_audio_style = getattr(audio, "ALICE_CLEAN_AUDIO_STYLE", "clean_audiobook_style_no_bed_no_noise_floor")
            if alice_clean_audio_style not in alice_styles:
                row_issues.append("alice_clean_audiobook_style_receipt_missing")
        row = {
            "public_mp4": public_mp4,
            "title": str(asset.get("title") or ""),
            "status": "fail" if row_issues else "pass",
            "issues": row_issues,
            "duration_seconds": round(duration_seconds, 3),
            "audio_streams": audio_streams,
            "video_streams": video_streams,
            "quality": quality,
        }
        rows.append(row)
        issues.extend(f"{public_mp4}:{issue}" for issue in row_issues)
    return {
        "contract_name": "chummer.horizon_video_audio_exit_gate.v1",
        "generated_at_utc": utc_now(),
        "status": "pass" if not issues else "fail",
        "manifest": str(manifest_path),
        "rebuild_receipt": str(REBUILD_RECEIPT),
        "hard_exit_gate": {
            "duration_seconds_min": MIN_VIDEO_DURATION_SECONDS,
            "duration_seconds_max": MAX_VIDEO_DURATION_SECONDS,
            "audio_streams_required": 1,
            "video_streams_required": 1,
            "silence_gate_dbfs": audio.SILENCE_GATE_DBFS,
            "max_silence_seconds": audio.MAX_SILENCE_SECONDS,
            "max_start_silence_seconds": audio.MAX_EDGE_SILENCE_SECONDS,
            "max_tail_silence_seconds": audio.MAX_EDGE_SILENCE_SECONDS,
            "alice_voice_policy": "female news-anchor voice only",
            "premium_mix_policy": "continuous harmonic bed plus normalized news-anchor narration, except Alice which must use clean audiobook-style speech-only narration with no synthetic bed or noise floor",
        },
        "asset_count": len(rows),
        "issues": issues,
        "assets": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Hard exit gate for all public horizon video audio.")
    parser.add_argument("--manifest", default=str(MANIFEST))
    parser.add_argument("--out", default=str(OUTPUT))
    args = parser.parse_args()
    result = verify_manifest(Path(args.manifest))
    output = Path(args.out)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": result["status"], "asset_count": result["asset_count"], "out": str(output)}, indent=2))
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())

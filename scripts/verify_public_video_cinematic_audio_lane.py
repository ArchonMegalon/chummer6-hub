#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


REPO = Path(__file__).resolve().parents[1]
MEDIA_ROOT = REPO / "Chummer.Run.Api" / "wwwroot" / "media"
OUTPUT = REPO / ".codex-studio" / "published" / "PUBLIC_VIDEO_CINEMATIC_NARRATION_LANE.generated.json"


@dataclass(frozen=True)
class MediaVariant:
    path: Path
    public_path: str
    media_kind: str


@dataclass(frozen=True)
class MediaGroup:
    key: str
    root: Path
    variants: tuple[MediaVariant, ...]


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def public_path(path: Path) -> str:
    relative = path.relative_to(REPO / "Chummer.Run.Api" / "wwwroot")
    return f"/{relative.as_posix()}"


def canonical_key(path: Path) -> str:
    stem = path.stem
    if stem.endswith("-mobile"):
        stem = stem[: -len("-mobile")]
    return stem


def video_groups(media_root: Path) -> list[MediaGroup]:
    buckets: dict[tuple[Path, str], list[MediaVariant]] = {}
    for path in sorted(media_root.rglob("*")):
        if path.suffix.lower() not in {".mp4", ".webm"}:
            continue
        key = canonical_key(path)
        buckets.setdefault((path.parent, key), []).append(
            MediaVariant(path=path, public_path=public_path(path), media_kind=path.suffix.lower().lstrip("."))
        )
    return [
        MediaGroup(key=key, root=root, variants=tuple(variants))
        for (root, key), variants in sorted(buckets.items(), key=lambda item: (str(item[0][0]), item[0][1]))
    ]


def audio_only_assets(media_root: Path) -> list[Path]:
    return sorted(path for path in media_root.rglob("*") if path.suffix.lower() in {".m4a", ".mp3", ".wav", ".ogg"})


def ffprobe(path: Path) -> dict[str, Any]:
    return json.loads(
        subprocess.check_output(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration,size:stream=codec_type,codec_name,width,height,sample_rate,channels,bit_rate",
                "-of",
                "json",
                str(path),
            ],
            text=True,
        )
    )


def source_paths(group: MediaGroup) -> dict[str, Path | None]:
    caption = group.root / f"{group.key}.vtt"
    receipt = group.root / f"{group.key}.receipt.json"
    tour_manifest = group.root / "black-ledger-tour-exports.manifest.json"
    return {
        "caption": caption if caption.is_file() else None,
        "receipt": receipt if receipt.is_file() else None,
        "tour_manifest": tour_manifest if tour_manifest.is_file() and group.key == "black-ledger-3dvista-flythrough" else None,
    }


def read_json(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def caption_segment_count(path: Path | None) -> int:
    if path is None:
        return 0
    return sum(1 for line in path.read_text(encoding="utf-8", errors="ignore").splitlines() if "-->" in line)


def receipt_has_narration_source(receipt: dict[str, Any]) -> bool:
    if not receipt:
        return False
    if str(receipt.get("narration_provider") or "").strip():
        return True
    if str(receipt.get("continuous_audio_track") or "").strip():
        return True
    if isinstance(receipt.get("captions"), list) and receipt["captions"]:
        return True
    for key in ("scene_payloads", "production_scenes", "scene_narration"):
        if isinstance(receipt.get(key), list) and receipt[key]:
            return True
    return False


def ambient_audio_allowed(group: MediaGroup, receipt: dict[str, Any], tour_manifest: dict[str, Any]) -> bool:
    if group.key == "black-ledger-video-globe-idle":
        return str(receipt.get("audio_mode") or "").startswith("first_party_subtle_ambient")
    if group.key == "black-ledger-3dvista-flythrough":
        flythrough = tour_manifest.get("flythrough") if isinstance(tour_manifest.get("flythrough"), dict) else {}
        return "ambient" in str(flythrough.get("audio") or "").lower()
    return False


def voice_direction(group: MediaGroup, has_caption: bool, has_receipt_narration: bool, ambient_only: bool) -> str:
    if ambient_only:
        return "first-party cinematic ambient bed; no gameplay or rules claim rides on the audio"
    if group.key == "alice-90s-deepdive":
        return "calm female guide voice; concise, practical, not chatbot-branded"
    if "origin-dossier" in group.key:
        return "cinematic audiobook narration; intimate runner-story pacing before any build advice"
    if group.root.name == "factions":
        return "short faction teaser narration; noir energy, no rules authority"
    if group.root.name == "newsreels":
        return "broadcast newsroom cadence; clear and current, not melodramatic"
    if has_caption or has_receipt_narration:
        return "premium cinematic narrator over restrained music bed"
    return "audio present; narration source must be added before this asset can claim a spoken lane"


def verify_group(group: MediaGroup) -> dict[str, Any]:
    paths = source_paths(group)
    receipt = read_json(paths["receipt"])
    tour_manifest = read_json(paths["tour_manifest"])
    captions = paths["caption"]
    has_receipt_narration = receipt_has_narration_source(receipt)
    ambient_only = ambient_audio_allowed(group, receipt, tour_manifest)
    caption_count = caption_segment_count(captions)
    issues: list[str] = []
    variants: list[dict[str, Any]] = []

    if not ambient_only and caption_count == 0 and not has_receipt_narration:
        issues.append("missing_cinematic_narration_source")

    for variant in group.variants:
        probe = ffprobe(variant.path)
        streams = probe.get("streams") or []
        audio_streams = [stream for stream in streams if stream.get("codec_type") == "audio"]
        video_streams = [stream for stream in streams if stream.get("codec_type") == "video"]
        duration = float((probe.get("format") or {}).get("duration") or 0.0)
        variant_issues: list[str] = []
        if len(video_streams) != 1:
            variant_issues.append("video_stream_count_invalid")
        if len(audio_streams) < 1:
            variant_issues.append("audio_stream_missing")
        if duration <= 0.0:
            variant_issues.append("duration_invalid")
        issues.extend(f"{variant.public_path}:{issue}" for issue in variant_issues)
        variants.append(
            {
                "public_path": variant.public_path,
                "kind": variant.media_kind,
                "status": "fail" if variant_issues else "pass",
                "issues": variant_issues,
                "duration_seconds": round(duration, 3),
                "video_streams": len(video_streams),
                "audio_streams": len(audio_streams),
                "audio_codecs": [str(stream.get("codec_name") or "") for stream in audio_streams],
            }
        )

    source_mode = "ambient_only" if ambient_only else "captions" if caption_count else "receipt_narration" if has_receipt_narration else "missing"
    return {
        "group_key": group.key,
        "root": str(group.root.relative_to(MEDIA_ROOT)),
        "status": "fail" if issues else "pass",
        "issues": issues,
        "source_mode": source_mode,
        "caption": str(paths["caption"]) if paths["caption"] else "",
        "caption_segments": caption_count,
        "receipt": str(paths["receipt"]) if paths["receipt"] else "",
        "tour_manifest": str(paths["tour_manifest"]) if paths["tour_manifest"] else "",
        "narration_provider": str(receipt.get("narration_provider") or ""),
        "voice": str(receipt.get("voice") or receipt.get("voice_posture") or ""),
        "voice_direction": voice_direction(group, caption_count > 0, has_receipt_narration, ambient_only),
        "variants": variants,
    }


def verify_audio_only(path: Path) -> dict[str, Any]:
    probe = ffprobe(path)
    streams = probe.get("streams") or []
    audio_streams = [stream for stream in streams if stream.get("codec_type") == "audio"]
    duration = float((probe.get("format") or {}).get("duration") or 0.0)
    issues: list[str] = []
    if len(audio_streams) < 1:
        issues.append("audio_stream_missing")
    if duration <= 0.0:
        issues.append("duration_invalid")
    return {
        "public_path": public_path(path),
        "status": "fail" if issues else "pass",
        "issues": issues,
        "duration_seconds": round(duration, 3),
        "audio_streams": len(audio_streams),
        "audio_codecs": [str(stream.get("codec_name") or "") for stream in audio_streams],
    }


def verify(media_root: Path) -> dict[str, Any]:
    groups = [verify_group(group) for group in video_groups(media_root)]
    audio_assets = [verify_audio_only(path) for path in audio_only_assets(media_root)]
    issues: list[str] = []
    for group in groups:
        issues.extend(f"{group['group_key']}:{issue}" for issue in group["issues"])
    for asset in audio_assets:
        issues.extend(f"{asset['public_path']}:{issue}" for issue in asset["issues"])
    return {
        "contract_name": "chummer.public_video_cinematic_narration_lane.v1",
        "generated_at_utc": utc_now(),
        "status": "pass" if not issues else "fail",
        "media_root": str(media_root),
        "policy": {
            "video_assets_require_audio_stream": True,
            "spoken_assets_require_caption_or_receipt_source": True,
            "ambient_only_assets_must_declare_boundary": True,
            "provider_posture": "Use checked-in captions/receipts as the source script. Prefer a verified premium voice provider; fall back only with explicit receipt.",
        },
        "video_group_count": len(groups),
        "audio_only_asset_count": len(audio_assets),
        "issues": issues,
        "video_groups": groups,
        "audio_only_assets": audio_assets,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify all public Chummer video assets have a cinematic audio lane.")
    parser.add_argument("--media-root", default=str(MEDIA_ROOT))
    parser.add_argument("--out", default=str(OUTPUT))
    args = parser.parse_args()
    result = verify(Path(args.media_root))
    output = Path(args.out)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": result["status"], "video_group_count": result["video_group_count"], "out": str(output)}, indent=2))
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())

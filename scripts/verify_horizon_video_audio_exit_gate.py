#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


REPO = Path(__file__).resolve().parents[1]
MANIFEST = REPO / "Chummer.Run.Api" / "wwwroot" / "media" / "horizons" / "horizon-video-manifest.json"
AUDIO_REBUILD = REPO / "scripts" / "rebuild_public_video_audio_unmixr.py"
OUTPUT = REPO / ".codex-studio" / "published" / "HORIZON_VIDEO_AUDIO_EXIT_GATE.generated.json"
PUBLIC_VIDEO_AUDIO_OUT_ROOT_ENV = "CHUMMER_PUBLIC_VIDEO_AUDIO_OUT_ROOT"
PUBLIC_VIDEO_AUDIO_LEGACY_OUT_ROOTS_ENV = "CHUMMER_PUBLIC_VIDEO_AUDIO_LEGACY_OUT_ROOTS"
DEFAULT_REBUILD_ROOT = REPO.parent / "_completion" / "public_video_audio_unmixr"
REBUILD_RECEIPT = Path(os.environ.get(PUBLIC_VIDEO_AUDIO_OUT_ROOT_ENV, "") or DEFAULT_REBUILD_ROOT) / "PUBLIC_VIDEO_AUDIO_REBUILD.generated.json"
LEGACY_REBUILD_RECEIPTS = tuple(
    Path(path.strip()) / "PUBLIC_VIDEO_AUDIO_REBUILD.generated.json"
    for path in re.split(r"[,;:]", os.environ.get(PUBLIC_VIDEO_AUDIO_LEGACY_OUT_ROOTS_ENV, ""))
    if path.strip()
)
PUBLISHED_REBUILD_RECEIPT = REPO / ".codex-studio" / "published" / "PUBLIC_VIDEO_AUDIO_REBUILD.generated.json"
PUBLISHED_CLEANUP_RECEIPTS = (
    REPO / ".codex-studio" / "published" / "PUBLIC_VIDEO_EXISTING_AUDIO_CLEANUP.generated.json",
    REPO / ".codex-studio" / "published" / "PUBLIC_VIDEO_EXISTING_AUDIO_CLEANUP_PASS2.generated.json",
)
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


def load_group_receipts(path: Path) -> dict[str, dict[str, Any]]:
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return {
        str(group.get("group_key") or ""): group
        for group in payload.get("groups", [])
        if isinstance(group, dict) and str(group.get("group_key") or "")
    }


def rebuild_group_receipts() -> dict[str, dict[str, Any]]:
    receipts: dict[str, dict[str, Any]] = {}
    for path in (PUBLISHED_REBUILD_RECEIPT, *LEGACY_REBUILD_RECEIPTS, REBUILD_RECEIPT):
        receipts.update(load_group_receipts(path))
    return receipts


def load_cleanup_file_receipts(paths: tuple[Path, ...]) -> dict[str, dict[str, Any]]:
    receipts: dict[str, dict[str, Any]] = {}
    for path in paths:
        if not path.is_file():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        for item in payload.get("files", []):
            if not isinstance(item, dict):
                continue
            file_path = str(item.get("file") or "").strip()
            group_key = str(item.get("group_key") or "").strip()
            quality = item.get("after_quality") if isinstance(item.get("after_quality"), dict) else item.get("quality")
            if not isinstance(quality, dict) or str(quality.get("status") or "") != "pass":
                continue
            receipt = {"receipt": str(path), "file": file_path, "group_key": group_key, "quality": quality}
            if file_path:
                receipts[file_path] = receipt
                receipts[Path(file_path).name] = receipt
            if group_key:
                receipts[group_key] = receipt
    return receipts


def clean_speech_style_is_current(style: str) -> bool:
    normalized = style.strip().lower()
    return normalized.startswith("clean_") and "no_bed" in normalized and "no_noise" in normalized


def verify_manifest(manifest_path: Path) -> dict[str, Any]:
    audio = load_audio_module()
    group_receipts = rebuild_group_receipts()
    cleanup_file_receipts = load_cleanup_file_receipts(PUBLISHED_CLEANUP_RECEIPTS)
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
        group_key = path.stem
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
        clean_speech_audio = True
        alice_clean_audio = group_key == "alice-90s-deepdive"
        rebuild_receipt = group_receipts.get(group_key) or {}
        try:
            relative_file = str(path.relative_to(REPO))
        except ValueError:
            relative_file = path.name
        cleanup_receipt = (
            cleanup_file_receipts.get(relative_file)
            or cleanup_file_receipts.get(path.name)
            or cleanup_file_receipts.get(group_key)
            or {}
        )
        try:
            quality = audio.audio_quality(path, allow_clean_speech_pauses=False)
        except TypeError:
            quality = audio.audio_quality(path)
        clean_speech_groups = set(getattr(audio, "CLEAN_SPEECH_AUDIO_GROUPS", set()))
        requires_clean_speech_receipt = group_key in clean_speech_groups
        if not MIN_VIDEO_DURATION_SECONDS <= duration_seconds <= MAX_VIDEO_DURATION_SECONDS:
            row_issues.append("duration_not_90s")
        if audio_streams != 1:
            row_issues.append("audio_stream_count_invalid")
        if video_streams != 1:
            row_issues.append("video_stream_count_invalid")
        if quality.get("status") != "pass":
            row_issues.extend(str(item) for item in quality.get("reasons") or ["audio_quality_failed"])
        if clean_speech_audio:
            provider = rebuild_receipt.get("provider") if isinstance(rebuild_receipt.get("provider"), dict) else {}
            receipt_files = rebuild_receipt.get("files") if isinstance(rebuild_receipt.get("files"), list) else []
            matching_file = next(
                (
                    item
                    for item in receipt_files
                    if isinstance(item, dict)
                    and str(item.get("file") or "").endswith(f"/{path.name}")
                    and str(item.get("quality", {}).get("status") if isinstance(item.get("quality"), dict) else "") == "pass"
                ),
                None,
            )
            rebuild_style_is_current = bool(
                matching_file and clean_speech_style_is_current(str(matching_file.get("audio_style") or ""))
            )
            unmixr_rebuild_is_current = (
                bool(rebuild_receipt)
                and str(rebuild_receipt.get("status") or "") == "pass"
                and str(provider.get("provider") or "") == getattr(audio, "UNMIXR_PROVIDER", "unmixr-short-tts")
                and bool(matching_file)
                and rebuild_style_is_current
            )
            existing_audio_cleanup_is_current = bool(cleanup_receipt) or str(quality.get("status") or "") == "pass"

            if requires_clean_speech_receipt and not unmixr_rebuild_is_current:
                if not rebuild_receipt:
                    row_issues.append("clean_speech_unmixr_rebuild_receipt_missing")
                elif str(rebuild_receipt.get("status") or "") != "pass":
                    row_issues.append("clean_speech_unmixr_rebuild_receipt_not_pass")
                elif str(provider.get("provider") or "") != getattr(audio, "UNMIXR_PROVIDER", "unmixr-short-tts"):
                    row_issues.append("clean_speech_requires_unmixr_rebuild_receipt")
                elif not matching_file:
                    row_issues.append("clean_speech_rebuild_file_receipt_missing")
                elif not rebuild_style_is_current:
                    row_issues.append("clean_speech_rebuild_uses_legacy_bed_or_noise_style")
            elif not unmixr_rebuild_is_current and not existing_audio_cleanup_is_current:
                if not rebuild_receipt:
                    row_issues.append("public_video_audio_rebuild_receipt_missing")
                elif str(rebuild_receipt.get("status") or "") != "pass":
                    row_issues.append("public_video_audio_rebuild_receipt_not_pass")
                elif str(provider.get("provider") or "") != getattr(audio, "UNMIXR_PROVIDER", "unmixr-short-tts"):
                    row_issues.append("public_video_audio_requires_unmixr_rebuild_receipt")
                elif not matching_file:
                    row_issues.append("public_video_audio_rebuild_file_receipt_missing")
                elif not rebuild_style_is_current:
                    row_issues.append("public_video_audio_rebuild_uses_legacy_bed_or_noise_style")
        if alice_clean_audio:
            alice_receipt = rebuild_receipt
            provider = alice_receipt.get("provider") if isinstance(alice_receipt.get("provider"), dict) else {}
            if str(provider.get("provider") or "") != getattr(audio, "UNMIXR_PROVIDER", "unmixr-short-tts"):
                row_issues.append("alice_voice_policy_requires_unmixr_receipt")
            if str(provider.get("voice_policy") or "") != getattr(
                audio,
                "ALICE_VOICE_POLICY",
                "unmixr_premium_female_required_no_edge_fallback",
            ):
                row_issues.append("alice_voice_policy_requires_premium_female_no_edge_receipt")
            if str(provider.get("voice_gender") or "").strip().lower() != "female":
                row_issues.append("alice_voice_policy_requires_female_receipt")
            if str(provider.get("voice_quality") or "").strip().lower() != "premium":
                row_issues.append("alice_voice_policy_requires_premium_receipt")
            alice_files = alice_receipt.get("files") if isinstance(alice_receipt.get("files"), list) else []
            alice_styles = {str(item.get("audio_style") or "") for item in alice_files if isinstance(item, dict)}
            alice_clean_audio_style = getattr(audio, "ALICE_CLEAN_AUDIO_STYLE", "clean_audiobook_style_no_bed_no_noise_floor")
            if alice_clean_audio_style not in alice_styles:
                row_issues.append("alice_clean_audiobook_style_receipt_missing")
        row = {
            "public_mp4": public_mp4,
            "group_key": group_key,
            "title": str(asset.get("title") or ""),
            "status": "fail" if row_issues else "pass",
            "issues": row_issues,
            "duration_seconds": round(duration_seconds, 3),
            "audio_streams": audio_streams,
            "video_streams": video_streams,
            "quality": quality,
            "rebuild_receipt_status": str(rebuild_receipt.get("status") or "") if rebuild_receipt else "",
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
            "max_start_silence_seconds": getattr(audio, "MAX_START_SILENCE_SECONDS", audio.MAX_EDGE_SILENCE_SECONDS),
            "planned_tail_silence_seconds": getattr(audio, "NARRATION_END_BEFORE_VIDEO_SECONDS", 0.0),
            "min_tail_silence_seconds": getattr(audio, "MIN_TAIL_SILENCE_SECONDS", 0.0),
            "max_tail_silence_seconds": getattr(audio, "MAX_TAIL_SILENCE_SECONDS", audio.MAX_EDGE_SILENCE_SECONDS),
            "video_fade_out_seconds": getattr(audio, "VIDEO_FADE_OUT_SECONDS", 0.0),
            "video_fade_contract": getattr(audio, "VIDEO_FADE_CONTRACT", ""),
            "alice_voice_policy": "Premium female Unmixr voice required for Alice; Edge TTS fallback is not allowed",
            "clean_speech_receipt_policy": "ALICE, Runsite, Runbook Press, and Table Pulse require a current Unmixr clean-speech receipt; waveform pass metrics or legacy cleanup evidence alone cannot release them",
            "premium_mix_policy": "every public horizon video requires passing measured audio quality plus either a current Unmixr rebuild receipt or current existing-audio cleanup evidence when the asset needed repair; legacy bed/noise styles and dead-air waivers are rejected",
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

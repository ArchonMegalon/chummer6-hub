#!/usr/bin/env python3
from __future__ import annotations

import json
import argparse
import subprocess
from datetime import UTC, datetime
from pathlib import Path


WORKSPACE = Path("/docker/chummercomplete")
SOURCE_DIR = WORKSPACE / "_completion" / "magicfit_jama6_promo_12_scenes"
PUBLIC_DIR = WORKSPACE / "chummer.run-services" / "Chummer.Run.Api" / "wwwroot" / "media" / "promo"
SOURCE_RECEIPT = SOURCE_DIR / "MAGICFIT_12_SCENE_PROMO_SOURCE_AUDIT.generated.json"
PROVIDER_RECEIPT = WORKSPACE / "_completion" / "magicfit_provider" / "MAGICFIT_PROVIDER_VERIFICATION.generated.json"
PUBLIC_RECEIPT = PUBLIC_DIR / "chummer6-flagship-promo.receipt.json"

SCENE_GLOB = "[0-9][0-9]_*.mp4"
TARGET_MP4 = PUBLIC_DIR / "chummer6-flagship-promo.mp4"
TARGET_WEBM = PUBLIC_DIR / "chummer6-flagship-promo.webm"
TARGET_POSTER = PUBLIC_DIR / "chummer6-flagship-promo-poster.png"
TARGET_VTT = PUBLIC_DIR / "chummer6-flagship-promo.vtt"

CAPTIONS = (
    (0, 8, "Too much chaos at the table becomes one calm client workflow."),
    (8, 15, "Open Chummer6 and start from the client, not a marketing page."),
    (15, 23, "Build the runner with dense desktop controls and low-noise screens."),
    (23, 30, "Explain values and rule decisions with visible receipts."),
    (30, 38, "Black Ledger makes the world feel alive without faction detours."),
    (38, 45, "Release truth, provider proof, and audit freshness stay visible."),
    (45, 53, "Table Pulse keeps remote players and GM follow-through aligned."),
    (53, 60, "Remote reactions return as deliberate choices instead of chat noise."),
    (60, 68, "Karma Forge turns feedback into tracked improvements."),
    (68, 75, "Newsreels show campaign movement while the client stays the hero."),
    (75, 83, "Desktop and mobile surfaces point at the same release truth."),
    (83, 90, "Chummer6: build the runner, run the table, move the city."),
)

TARGET_SECONDS = 90.0
TRANSITION_SECONDS = 0.5
SCENE_SECONDS = (TARGET_SECONDS + 11 * TRANSITION_SECONDS) / 12


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def run(*command: str) -> None:
    subprocess.run(command, check=True)


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


def format_ts(seconds: int) -> str:
    minutes, secs = divmod(seconds, 60)
    return f"00:{minutes:02}:{secs:02}.000"


def write_vtt() -> None:
    lines = ["WEBVTT", ""]
    for index, (start, end, text) in enumerate(CAPTIONS, start=1):
        lines.extend([str(index), f"{format_ts(start)} --> {format_ts(end)}", text, ""])
    TARGET_VTT.write_text("\n".join(lines), encoding="utf-8")


def validate_inputs() -> list[Path]:
    if not SOURCE_RECEIPT.is_file():
        raise SystemExit(f"missing source receipt: {SOURCE_RECEIPT}")
    if not PROVIDER_RECEIPT.is_file():
        raise SystemExit(f"missing MagicFit provider receipt: {PROVIDER_RECEIPT}")

    source_receipt = load_json(SOURCE_RECEIPT)
    provider_receipt = load_json(PROVIDER_RECEIPT)
    scenes = sorted(SOURCE_DIR.glob(SCENE_GLOB))
    if len(scenes) != 12:
        raise SystemExit(f"expected 12 scene clips, found {len(scenes)} in {SOURCE_DIR}")
    if source_receipt.get("status") != "pass":
        raise SystemExit("MagicFit source audit is not passing")
    if provider_receipt.get("status") != "verified":
        raise SystemExit("MagicFit provider is not verified")
    return scenes


def validate_public_outputs() -> None:
    for path in (TARGET_MP4, TARGET_WEBM, TARGET_POSTER, TARGET_VTT, PUBLIC_RECEIPT):
        if not path.is_file():
            raise SystemExit(f"missing public promo output: {path}")

    if not TARGET_VTT.read_text(encoding="utf-8").startswith("WEBVTT\n"):
        raise SystemExit("promo captions are not a valid WEBVTT file")

    receipt = load_json(PUBLIC_RECEIPT)
    if receipt.get("status") != "published":
        raise SystemExit("public promo receipt is not published")
    if receipt.get("source_scene_count") != 12:
        raise SystemExit("public promo receipt does not prove 12 source scenes")
    if receipt.get("faction_assets_used") is not False:
        raise SystemExit("public promo receipt does not prove faction-free source")

    mp4 = probe(TARGET_MP4)
    webm = probe(TARGET_WEBM)
    for name, payload in (("mp4", mp4), ("webm", webm)):
        streams = payload.get("streams") or []
        has_video = any(stream.get("codec_type") == "video" for stream in streams)
        has_audio = any(stream.get("codec_type") == "audio" for stream in streams)
        duration = float(dict(payload.get("format") or {}).get("duration") or 0.0)
        if not has_video or not has_audio:
            raise SystemExit(f"{name} promo output is missing video or audio")
        if duration < TARGET_SECONDS - 0.5:
            raise SystemExit(f"{name} promo output is too short: {duration:.3f}s")


def build_master(scenes: list[Path], target: Path) -> None:
    inputs: list[str] = []
    filters: list[str] = []
    for index, scene in enumerate(scenes):
        media = probe(scene)
        duration = float(dict(media.get("format") or {}).get("duration") or 0.0)
        if duration <= 0:
            raise SystemExit(f"cannot read duration for {scene}")
        stretch = SCENE_SECONDS / duration
        inputs.extend(["-i", str(scene)])
        filters.append(
            f"[{index}:v]scale=1280:720:force_original_aspect_ratio=increase,"
            f"crop=1280:720,setsar=1,setpts={stretch:.8f}*PTS,"
            f"trim=duration={SCENE_SECONDS:.6f},setpts=PTS-STARTPTS,"
            f"fps=24,format=yuv420p[v{index}]"
        )
    chain = "[v0]"
    for index in range(1, len(scenes)):
        out = f"[x{index}]"
        offset = index * (SCENE_SECONDS - TRANSITION_SECONDS)
        filters.append(
            f"{chain}[v{index}]xfade=transition=fade:duration={TRANSITION_SECONDS:.3f}:"
            f"offset={offset:.6f}{out}"
        )
        chain = out
    filters.append(
        "aevalsrc='0.055*sin(2*PI*55*t)+0.035*sin(2*PI*110*t)+"
        "0.018*sin(2*PI*(220+20*sin(2*PI*0.04*t))*t)':"
        f"s=48000:d={TARGET_SECONDS:.3f},"
        "afade=t=in:st=0:d=1.5,afade=t=out:st=87.5:d=2.5[a]"
    )
    run(
        "ffmpeg",
        "-y",
        *inputs,
        "-filter_complex",
        ";".join(filters),
        "-map",
        chain,
        "-map",
        "[a]",
        "-t",
        f"{TARGET_SECONDS:.3f}",
        "-c:v",
        "libx264",
        "-preset",
        "medium",
        "-crf",
        "18",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        "160k",
        "-movflags",
        "+faststart",
        str(target),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Build or verify the public Chummer6 flagship promo.")
    parser.add_argument("--check", action="store_true", help="verify inputs and public outputs without rebuilding media")
    args = parser.parse_args()

    scenes = validate_inputs()
    if args.check:
        validate_public_outputs()
        print("CHUMMER6_FLAGSHIP_PROMO_READY")
        return 0

    PUBLIC_DIR.mkdir(parents=True, exist_ok=True)
    build_master(scenes, TARGET_MP4)
    run(
        "ffmpeg",
        "-y",
        "-i",
        str(TARGET_MP4),
        "-c:v",
        "libvpx-vp9",
        "-crf",
        "34",
        "-b:v",
        "0",
        "-c:a",
        "libopus",
        "-b:a",
        "112k",
        "-vf",
        "scale=1280:-2",
        str(TARGET_WEBM),
    )
    run(
        "ffmpeg",
        "-y",
        "-i",
        str(TARGET_MP4),
        "-vf",
        "select=eq(n\\,720)",
        "-frames:v",
        "1",
        "-update",
        "1",
        str(TARGET_POSTER),
    )
    write_vtt()

    mp4_probe = probe(TARGET_MP4)
    receipt = {
        "generated_at_utc": utc_now(),
        "status": "published",
        "asset_id": "chummer6-flagship-promo",
        "render_mode": "ea_magicfit_12_scene_no_factions_90s_edit",
        "old_synthetic_vector_renderer_removed": True,
        "source_scene_count": len(scenes),
        "source_scene_dir": str(SOURCE_DIR),
        "source_receipt": str(SOURCE_RECEIPT),
        "provider_receipt": str(PROVIDER_RECEIPT),
        "faction_assets_used": False,
        "scene_seconds_before_transitions": SCENE_SECONDS,
        "transition_seconds": TRANSITION_SECONDS,
        "continuous_audio_track": "ffmpeg_generated_synthetic_music_bed",
        "public_files": {
            "mp4": str(TARGET_MP4),
            "webm": str(TARGET_WEBM),
            "poster": str(TARGET_POSTER),
            "captions": str(TARGET_VTT),
        },
        "mp4_probe": mp4_probe,
    }
    PUBLIC_RECEIPT.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(PUBLIC_RECEIPT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

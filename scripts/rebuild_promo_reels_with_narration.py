#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import shutil
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


WORKSPACE = Path("/docker/chummercomplete")
PUBLIC_DIR = WORKSPACE / "chummer.run-services" / "Chummer.Run.Api" / "wwwroot" / "media" / "promo"
OUT = WORKSPACE / "_completion" / "promo_video_rework_20260602"
TTS_PYTHON = OUT / "tts_venv" / "bin" / "python"
VOICE = "en-US-GuyNeural"
WIDTH = 1280
HEIGHT = 720
FPS = 24


@dataclass(frozen=True)
class Scene:
    clip: Path
    duration: float
    caption: str
    narration: str
    voice: str | None = None
    voice_treatment: str = "trailer"


@dataclass(frozen=True)
class Reel:
    asset_id: str
    title: str
    render_mode: str
    source_claim: str
    scenes: tuple[Scene, ...]
    voice: str = "en-US-AndrewNeural"
    continuous_voiceover: bool = False


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def run(*command: str, capture: bool = False) -> str:
    completed = subprocess.run(command, check=True, text=True, capture_output=capture)
    return completed.stdout if capture else ""


def probe(path: Path) -> dict[str, Any]:
    return json.loads(
        run(
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration,size:stream=codec_type,codec_name,width,height,sample_rate,channels",
            "-of",
            "json",
            str(path),
            capture=True,
        )
    )


def duration(path: Path) -> float:
    payload = probe(path)
    return float(dict(payload.get("format") or {}).get("duration") or 0.0)


def format_ts(seconds: float) -> str:
    total_ms = int(round(seconds * 1000))
    hours, rem = divmod(total_ms, 3600_000)
    minutes, rem = divmod(rem, 60_000)
    secs, ms = divmod(rem, 1000)
    return f"{hours:02}:{minutes:02}:{secs:02}.{ms:03}"


def write_vtt(path: Path, scenes: tuple[Scene, ...]) -> None:
    lines = ["WEBVTT", ""]
    cursor = 0.0
    for index, scene in enumerate(scenes, start=1):
        start = cursor
        end = cursor + scene.duration
        lines.extend([str(index), f"{format_ts(start)} --> {format_ts(end)}", scene.caption, ""])
        cursor = end
    path.write_text("\n".join(lines), encoding="utf-8")


async def render_edge_tts(text: str, output: Path) -> bool:
    if not TTS_PYTHON.is_file():
        return False
    code = (
        "import asyncio, edge_tts, pathlib, sys\n"
        "async def main():\n"
        "    voice, text, output = sys.argv[1], sys.argv[2], pathlib.Path(sys.argv[3])\n"
        "    communicate = edge_tts.Communicate(text=text, voice=voice, rate='-5%', pitch='-2Hz')\n"
        "    await communicate.save(str(output))\n"
        "asyncio.run(main())\n"
    )
    helper = OUT / "render_edge_tts.py"
    helper.write_text(code, encoding="utf-8")
    try:
        proc = await asyncio.create_subprocess_exec(
            str(TTS_PYTHON),
            str(helper),
            VOICE,
            text,
            str(output),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()
    except Exception:
        return False
    if proc.returncode != 0:
        print(stderr.decode("utf-8", errors="replace"))
        return False
    return output.is_file() and output.stat().st_size > 0


async def render_edge_tts_voice(text: str, output: Path, voice: str) -> bool:
    global VOICE
    old_voice = VOICE
    VOICE = voice
    try:
        return await render_edge_tts(text, output)
    finally:
        VOICE = old_voice


def render_flite_tts(text: str, output: Path) -> None:
    escaped = text.replace("\\", "\\\\").replace("'", "\\'")
    run(
        "ffmpeg",
        "-y",
        "-f",
        "lavfi",
        "-i",
        f"flite=text='{escaped}':voice=slt",
        "-ar",
        "48000",
        "-ac",
        "1",
        str(output),
    )


async def render_narration_files(reel: Reel, work: Path) -> tuple[list[Path], str]:
    narration_dir = work / "narration"
    narration_dir.mkdir(parents=True, exist_ok=True)
    provider = "edge-tts"
    outputs: list[Path] = []
    for index, scene in enumerate(reel.scenes):
        output = narration_dir / f"{index + 1:02}.mp3"
        ok = await render_edge_tts_voice(scene.narration, output, scene.voice or reel.voice)
        if not ok:
            provider = "ffmpeg-flite"
            output = narration_dir / f"{index + 1:02}.wav"
            render_flite_tts(scene.narration, output)
        outputs.append(output)
    return outputs, provider


def full_reel_duration(reel: Reel) -> float:
    return sum(scene.duration for scene in reel.scenes)


async def render_continuous_voiceover(reel: Reel, work: Path) -> tuple[Path, str]:
    narration_dir = work / "narration"
    narration_dir.mkdir(parents=True, exist_ok=True)
    script = " ".join(scene.narration for scene in reel.scenes)
    output = narration_dir / "continuous.mp3"
    ok = await render_edge_tts_voice(script, output, reel.voice)
    if ok:
        return output, "edge-tts-continuous"
    fallback = narration_dir / "continuous.wav"
    render_flite_tts(script, fallback)
    return fallback, "ffmpeg-flite-continuous"


def make_continuous_audio_track(narration: Path, reel: Reel, output: Path) -> None:
    target_len = full_reel_duration(reel)
    narration_len = duration(narration)
    target_vo_len = max(target_len - 7.5, 1.0)
    vo_filter = "atrim=0:{:.3f},asetpts=PTS-STARTPTS".format(target_vo_len)
    if narration_len > target_vo_len:
        speed = min(max(narration_len / target_vo_len, 1.0), 1.55)
        vo_filter = f"atempo={speed:.4f},atrim=0:{target_vo_len:.3f},asetpts=PTS-STARTPTS"
    filters = [
        f"[0:a]{vo_filter},highpass=f=85,lowpass=f=11800,acompressor=threshold=-20dB:ratio=2.6:attack=18:release=180:makeup=2.0,alimiter=limit=0.88[vo0]",
        (
            "aevalsrc='0.014*sin(2*PI*44*t)+0.009*sin(2*PI*88*t)+"
            f"0.005*sin(2*PI*176*t)':s=48000:d={target_len:.3f}[bed]"
        ),
        f"[vo0]adelay=900|900,apad,atrim=0:{target_len:.3f},volume=1.16[vo]",
        f"[bed][vo]amix=inputs=2:duration=first:dropout_transition=0,alimiter=limit=0.92[a]",
    ]
    run(
        "ffmpeg",
        "-y",
        "-i",
        str(narration),
        "-filter_complex",
        ";".join(filters),
        "-map",
        "[a]",
        "-c:a",
        "pcm_s16le",
        str(output),
    )


def make_audio_segment(narration: Path, scene: Scene, output: Path) -> None:
    scene_len = scene.duration
    narration_len = duration(narration)
    target_vo_len = max(scene_len - 0.7, 1.0)
    filters: list[str] = []
    vo_label = "vo0"
    if narration_len > target_vo_len:
        speed = min(max(narration_len / target_vo_len, 1.0), 2.0)
        filters.append(f"[0:a]atempo={speed:.4f},atrim=0:{target_vo_len:.3f},asetpts=PTS-STARTPTS[rawvo]")
    else:
        filters.append(f"[0:a]atrim=0:{target_vo_len:.3f},asetpts=PTS-STARTPTS[rawvo]")
    if scene.voice_treatment == "ork_news":
        filters.append("[rawvo]atempo=0.84,rubberband=pitch=0.70,highpass=f=58,lowpass=f=5900,bass=g=5:f=105:w=0.55,acompressor=threshold=-19dB:ratio=3.8:attack=18:release=230:makeup=4.2,alimiter=limit=0.90[vo0]")
    else:
        filters.append("[rawvo]highpass=f=85,lowpass=f=11800,acompressor=threshold=-20dB:ratio=2.3:attack=18:release=180:makeup=2.0,alimiter=limit=0.88[vo0]")
    filters.append(
        "aevalsrc='0.018*sin(2*PI*55*t)+0.010*sin(2*PI*110*t)+"
        f"0.006*sin(2*PI*220*t)':s=48000:d={scene_len:.3f}[bed]"
    )
    filters.append(f"[{vo_label}]adelay=220|220,apad,atrim=0:{scene_len:.3f},volume=1.22[vo]")
    filters.append(f"[bed][vo]amix=inputs=2:duration=first:dropout_transition=0,alimiter=limit=0.92[a]")
    run(
        "ffmpeg",
        "-y",
        "-i",
        str(narration),
        "-filter_complex",
        ";".join(filters),
        "-map",
        "[a]",
        "-c:a",
        "pcm_s16le",
        str(output),
    )


def make_video_segment(scene: Scene, output: Path) -> None:
    source_duration = duration(scene.clip)
    if source_duration <= 0:
        raise SystemExit(f"cannot read clip duration: {scene.clip}")
    stretch = scene.duration / source_duration
    video_filter = (
        f"scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=increase,"
        f"crop={WIDTH}:{HEIGHT},setsar=1,setpts={stretch:.8f}*PTS,"
        f"trim=duration={scene.duration:.3f},setpts=PTS-STARTPTS,fps={FPS},format=yuv420p"
    )
    font = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf"
    if scene.clip.name == "12_hero_ending.mp4":
        video_filter += (
            f",drawbox=x=w-246:y=36:w=210:h=56:color=black@0.24:t=fill:enable='between(t,1.0,{max(scene.duration - 0.8, 0.5):.2f})'"
            f",drawtext=fontfile={font}:text='trace 87%%':x=w-230:y=48:fontsize=16:fontcolor=76ff9f@0.72:"
            f"shadowcolor=000000@0.45:shadowx=1:shadowy=1:enable='between(t,1.0,{max(scene.duration - 0.8, 0.5):.2f})'"
            f",drawtext=fontfile={font}:text='eyes: remote':x=w-230:y=68:fontsize=13:fontcolor=d7ffe5@0.58:"
            f"shadowcolor=000000@0.35:shadowx=1:shadowy=1:enable='between(t,1.7,{max(scene.duration - 2.2, 0.5):.2f})'"
            f",drawtext=fontfile={font}:text='trace lost':x=w-230:y=68:fontsize=13:fontcolor=ff6b7d@0.62:"
            f"shadowcolor=000000@0.35:shadowx=1:shadowy=1:enable='between(t,{max(scene.duration - 2.0, 0.5):.2f},{max(scene.duration - 0.7, 0.5):.2f})'"
        )
    run(
        "ffmpeg",
        "-y",
        "-i",
        str(scene.clip),
        "-an",
        "-vf",
        video_filter,
        "-t",
        f"{scene.duration:.3f}",
        "-c:v",
        "libx264",
        "-preset",
        "medium",
        "-crf",
        "18",
        str(output),
    )


def concat_segments(video_segments: list[Path], audio_segments: list[Path], output: Path) -> None:
    temp_dir = OUT / "concat" / output.stem
    temp_dir.mkdir(parents=True, exist_ok=True)
    video_list = temp_dir / "video_segments.txt"
    audio_list = temp_dir / "audio_segments.txt"
    video_list.write_text("".join(f"file '{path}'\n" for path in video_segments), encoding="utf-8")
    audio_list.write_text("".join(f"file '{path}'\n" for path in audio_segments), encoding="utf-8")
    joined_video = temp_dir / "joined-video.mp4"
    joined_audio = temp_dir / "joined-audio.wav"
    run("ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(video_list), "-c", "copy", str(joined_video))
    run("ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(audio_list), "-c:a", "pcm_s16le", str(joined_audio))
    run(
        "ffmpeg",
        "-y",
        "-i",
        str(joined_video),
        "-i",
        str(joined_audio),
        "-map",
        "0:v:0",
        "-map",
        "1:a:0",
        "-t",
        "90.000",
        "-c:v",
        "copy",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-movflags",
        "+faststart",
        str(output),
    )
    shutil.rmtree(temp_dir, ignore_errors=True)


def build_reel(reel: Reel) -> dict[str, Any]:
    work = OUT / reel.asset_id
    segments = work / "segments"
    work.mkdir(parents=True, exist_ok=True)
    segments.mkdir(parents=True, exist_ok=True)
    for scene in reel.scenes:
        if not scene.clip.is_file():
            raise SystemExit(f"missing MagicFit source clip: {scene.clip}")
    video_segments: list[Path] = []
    audio_segments: list[Path] = []
    narration_provider = ""
    if reel.continuous_voiceover:
        continuous_narration, narration_provider = asyncio.run(render_continuous_voiceover(reel, work))
    else:
        narration_files, narration_provider = asyncio.run(render_narration_files(reel, work))
    for index, scene in enumerate(reel.scenes):
        video_segment = segments / f"{index + 1:02}.video.mp4"
        audio_segment = segments / f"{index + 1:02}.audio.wav"
        make_video_segment(scene, video_segment)
        if not reel.continuous_voiceover:
            make_audio_segment(narration_files[index], scene, audio_segment)
            audio_segments.append(audio_segment)
        video_segments.append(video_segment)
    if reel.continuous_voiceover:
        continuous_audio = segments / "continuous.audio.wav"
        make_continuous_audio_track(continuous_narration, reel, continuous_audio)
        audio_segments = [continuous_audio]

    target_mp4 = PUBLIC_DIR / f"{reel.asset_id}.mp4"
    target_webm = PUBLIC_DIR / f"{reel.asset_id}.webm"
    target_vtt = PUBLIC_DIR / f"{reel.asset_id}.vtt"
    target_poster = PUBLIC_DIR / f"{reel.asset_id}-poster.png"
    target_receipt = PUBLIC_DIR / f"{reel.asset_id}.receipt.json"
    if reel.continuous_voiceover:
        temp_dir = OUT / "concat" / target_mp4.stem
        temp_dir.mkdir(parents=True, exist_ok=True)
        video_list = temp_dir / "video_segments.txt"
        joined_video = temp_dir / "joined-video.mp4"
        video_list.write_text("".join(f"file '{path}'\n" for path in video_segments), encoding="utf-8")
        run("ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(video_list), "-c", "copy", str(joined_video))
        run(
            "ffmpeg",
            "-y",
            "-i",
            str(joined_video),
            "-i",
            str(audio_segments[0]),
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-t",
            f"{full_reel_duration(reel):.3f}",
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-movflags",
            "+faststart",
            str(target_mp4),
        )
        shutil.rmtree(temp_dir, ignore_errors=True)
    else:
        concat_segments(video_segments, audio_segments, target_mp4)
    run(
        "ffmpeg",
        "-y",
        "-i",
        str(target_mp4),
        "-c:v",
        "libvpx-vp9",
        "-deadline",
        "realtime",
        "-cpu-used",
        "5",
        "-row-mt",
        "1",
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
        str(target_webm),
    )
    run("ffmpeg", "-y", "-i", str(target_mp4), "-ss", "00:00:08", "-frames:v", "1", "-update", "1", str(target_poster))
    write_vtt(target_vtt, reel.scenes)
    mp4_probe = probe(target_mp4)
    receipt = {
        "generated_at_utc": utc_now(),
        "status": "published",
        "asset_id": reel.asset_id,
        "title": reel.title,
        "render_mode": reel.render_mode,
        "source_claim": reel.source_claim,
        "visual_source": "MagicFit scene clips only",
        "narration_provider": narration_provider,
        "voice": reel.voice if narration_provider.startswith("edge-tts") else "ffmpeg flite slt",
        "scene_count": len(reel.scenes),
        "duration_seconds": sum(scene.duration for scene in reel.scenes),
        "continuous_audio_track": "spoken_narration_plus_low_music_bed",
        "scene_narration": [
            {
                "clip": str(scene.clip),
                "duration_seconds": scene.duration,
                "caption": scene.caption,
                "narration": scene.narration,
            }
            for scene in reel.scenes
        ],
        "public_files": {
            "mp4": str(target_mp4),
            "webm": str(target_webm),
            "poster": str(target_poster),
            "captions": str(target_vtt),
        },
        "mp4_probe": mp4_probe,
    }
    target_receipt.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    return receipt


def flagship_reel() -> Reel:
    src = WORKSPACE / "_completion" / "magicfit_jama6_promo_12_scenes"
    clips = [
        "01_old_way_pain.mp4",
        "02_chummer6_reveal.mp4",
        "03_build_runner.mp4",
        "04_explain_values.mp4",
        "05_black_ledger_alive.mp4",
        "06_release_truth.mp4",
        "07_table_pulse.mp4",
        "08_world_reacts.mp4",
        "09_karma_forge.mp4",
        "10_newsroom.mp4",
        "11_play_anywhere.mp4",
        "12_hero_ending.mp4",
    ]
    durations = [8, 7, 8, 7, 8, 7, 8, 7, 8, 7, 8, 7]
    captions = [
        "Stop losing the run between sheets, tabs, and side notes.",
        "Chummer6 brings the table back into one command view.",
        "Build runners with gear, magic, cyberware, and consequences in sight.",
        "Know why the numbers changed before the dice hit the table.",
        "Black Ledger lets the city remember what the crew did.",
        "Prep scenes, NPCs, jobs, handouts, and fallout without rummaging.",
        "Table Pulse turns rising heat into playable pressure.",
        "Remote players can still push the run forward.",
        "Karma Forge keeps house rules table-ready and reversible.",
        "A field report turns aftermath into the next hook.",
        "Desktop, tablet, and phone keep the crew in sync.",
        "When the trace hits 100, the crew is already gone.",
    ]
    narration = [
        "You know this table. Three PDFs open. A runner sheet half finished. The GM asking who actually has the medkit.",
        "Chummer6 pulls the noise into one command view, so the crew can stop hunting for answers and start the run.",
        "Build the runner like a runner: gear, magic, cyberware, contacts, limits, and the little choices that get you paid or killed.",
        "When a number moves, you can follow it. No table argument. No mystery math. Just the sheet doing what it should.",
        "Then the city answers back. Black Ledger tracks heat, districts, jobs, factions, and the consequences your crew left behind.",
        "For the GM, prep becomes playable: scenes, NPCs, handouts, opposition, rewards, downtime, and next-session hooks in reach.",
        "Table Pulse turns pressure into something the table can use: rising heat, hard choices, and moments that feel alive.",
        "Remote players are still in the run. They can react, answer, vote, and push the story forward without derailing the room.",
        "Karma Forge keeps house rules from becoming folklore. Try the change, show the impact, roll it back if the table hates it.",
        "We have a developing situation. The crew is gone, the drones are confused, and one fixer is suddenly unavailable for comment.",
        "Desktop, tablet, phone, home table or remote night: the campaign stays with the crew.",
        "Chummer6 is for crews who want the next run ready before the heat cools. Build the runner. Run the table. Let the city remember.",
    ]
    scenes = tuple(
        Scene(
            src / clip,
            float(duration),
            captions[i],
            narration[i],
            voice="en-US-GuyNeural" if clip == "10_newsroom.mp4" else None,
            voice_treatment="ork_news" if clip == "10_newsroom.mp4" else "trailer",
        )
        for i, (clip, duration) in enumerate(zip(clips, durations))
    )
    return Reel(
        asset_id="chummer6-flagship-promo",
        title="Chummer6 Flagship Promo",
        render_mode="magicfit_fresh_rerender_with_scene_timed_trailer_and_ork_news_voiceover",
        source_claim="12 freshly rerendered MagicFit flagship scene clips with no generated product-name text, scene-timed trailer voiceover, and separate ork newsroom voice",
        scenes=scenes,
        voice="en-US-AndrewNeural",
        continuous_voiceover=False,
    )


def horizons_reel(asset_id: str, title: str, source_claim: str) -> Reel:
    src = WORKSPACE / "_completion" / "horizons_90s_promo" / "magicfit_clips"
    rows = [
        ("01_cold_open_table_chaos.mp4", 6, "The table is alive, but the tools are fighting the table.", "The table is alive, but the tools are fighting it. Chummer6 turns that chaos into one campaign operating surface."),
        ("02_nexus_pan_shared_state.mp4", 8, "NEXUS-PAN keeps shared state steady across devices.", "NEXUS-PAN keeps shared state steady when devices drift, drop, and return mid-session."),
        ("03_alice_build_tradeoffs.mp4", 8, "ALICE explains build tradeoffs before they break play.", "ALICE compares builds, catches role traps, and explains tradeoffs with receipts before play starts."),
        ("04_karma_forge_governed_rules.mp4", 8, "KARMA FORGE makes house rules governed and reversible.", "KARMA FORGE turns house rules into governed packages with impact, history, and rollback."),
        ("05_jackpoint_dossiers_recaps.mp4", 8, "JACKPOINT turns table memory into sharp briefings.", "JACKPOINT turns what happened at the table into briefings, dossiers, and recaps players actually want to read."),
        ("06_runsite_spatial_prep.mp4", 8, "RUNSITE makes mission spaces legible before danger starts.", "RUNSITE makes mission spaces explorable and legible before the action starts."),
        ("07_runbook_press_campaign_books.mp4", 8, "RUNBOOK PRESS turns campaign material into books.", "RUNBOOK PRESS turns campaign material into primers, guides, modules, and season books the table can carry forward."),
        ("08_table_pulse_live_heat.mp4", 8, "TABLE PULSE turns heat into bounded GM-approved reactions.", "TABLE PULSE turns live heat into bounded reactions, remote choices, and GM-approved fallout."),
        ("09_black_ledger_living_world.mp4", 10, "BLACK LEDGER makes the city remember consequences.", "BLACK LEDGER makes the city remember: factions, heat, missions, newsreels, and consequences."),
        ("10_community_hub_open_runs.mp4", 8, "COMMUNITY HUB helps players find runs and close the loop.", "COMMUNITY HUB helps players find runs, pass preflight, get scheduled, and feed outcomes back into the world."),
        ("11_finale_all_horizons.mp4", 10, "All Horizons return to one table and one campaign.", "All Horizons point back to the same table: build the runner, run the scene, shape the world, and make the next session easier to start."),
    ]
    return Reel(
        asset_id=asset_id,
        title=title,
        render_mode="magicfit_per_scene_rebuild_with_spoken_narration",
        source_claim=source_claim,
        scenes=tuple(Scene(src / clip, float(duration), caption, narration) for clip, duration, caption, narration in rows),
    )


def every_wonder_reel() -> Reel:
    src = WORKSPACE / "_completion" / "refined_magicfit_promo_plans_20260531" / "magicfit_clips"
    rows = [
        ("nexus-pan_epic_90s/nexus-pan_epic_01_the_split_truth.mp4", 7, "Every Wonder starts when split screens start slowing the table.", "Every Wonder Horizon starts with the real table problem: split devices, split notes, and a scene that should already be moving."),
        ("nexus_pan_90s_deepdive/nexus_pan_08_rejoin_cleanly.mp4", 7, "NEXUS-PAN recovers session state when players reconnect.", "NEXUS-PAN keeps reconnects calm. Players return with visible state, conflict status, and a clean handoff."),
        ("alice_90s_deepdive/alice_02_variant_compare.mp4", 7, "ALICE compares runner choices before they become table problems.", "ALICE turns build advice into explainable tradeoffs: role fit, survivability, legality, and cost."),
        ("karma_forge_90s_deepdive/karma_forge_03_impact_preview.mp4", 7, "KARMA FORGE previews house-rule impact before approval.", "KARMA FORGE makes house rules inspectable. The GM sees impact before the table commits."),
        ("jackpoint_90s_deepdive/jackpoint_04_dossier_build.mp4", 8, "JACKPOINT turns table events into clean dossiers.", "JACKPOINT turns table events into dossiers, briefings, recaps, and player-safe handouts."),
        ("runsite_90s_deepdive/runsite_02_site_unfolds.mp4", 8, "RUNSITE makes mission spaces readable before contact.", "RUNSITE opens the site before the run starts: routes, hotspots, layers, and GM-only context."),
        ("runbook_press_90s_deepdive/runbook_press_03_book_structure.mp4", 8, "RUNBOOK PRESS shapes campaign material into books.", "RUNBOOK PRESS turns campaign material into structured guides, season books, and handoff-ready exports."),
        ("table_pulse_90s_deepdive/table_pulse_04_remote_packet.mp4", 8, "TABLE PULSE turns heat into governed remote reaction packets.", "TABLE PULSE keeps pressure bounded: live heat, remote packets, opt-outs, and GM approval."),
        ("black_ledger_epic_90s/black_ledger_epic_02_the_globe_wakes.mp4", 8, "BLACK LEDGER lets the world wake up after the run.", "BLACK LEDGER makes the city remember. Factions move, districts heat up, and new jobs emerge."),
        ("black_ledger_90s_deepdive/black_ledger_07_newsroom.mp4", 7, "Newsreels make consequences feel like the city is watching.", "Newsroom clips turn fallout into rumors, pressure, jokes, and hooks the GM can bring back to the table."),
        ("community_hub_90s_deepdive/community_hub_02_open_run_board.mp4", 7, "COMMUNITY HUB brings players to vetted open runs.", "COMMUNITY HUB helps players find tables, pass preflight, schedule cleanly, and close the loop."),
        ("community_hub_90s_deepdive/community_hub_10_community_hero.mp4", 8, "Every Wonder returns to one table and one campaign.", "Every Wonder Horizon is the promise that the campaign can grow without losing the people, scenes, and choices that made it matter."),
    ]
    return Reel(
        asset_id="every-wonder-horizon-promo",
        title="Every Wonder Horizon Promo",
        render_mode="magicfit_refined_deepdive_montage_with_spoken_narration",
        source_claim="12 curated MagicFit-rendered refined deep-dive clips; distinct from the All Horizons teaser",
        scenes=tuple(Scene(src / clip, float(duration), caption, narration) for clip, duration, caption, narration in rows),
    )


def verify_receipt(receipt: dict[str, Any]) -> None:
    public_files = dict(receipt["public_files"])
    mp4 = Path(public_files["mp4"])
    media = probe(mp4)
    streams = media.get("streams") or []
    has_video = any(stream.get("codec_type") == "video" for stream in streams)
    has_audio = any(stream.get("codec_type") == "audio" for stream in streams)
    length = float(dict(media.get("format") or {}).get("duration") or 0.0)
    if not has_video or not has_audio:
        raise SystemExit(f"{mp4} is missing video or audio")
    if length < 89.5:
        raise SystemExit(f"{mp4} is too short: {length:.3f}s")
    for key in ("webm", "poster", "captions"):
        if not Path(public_files[key]).is_file():
            raise SystemExit(f"missing public {key}: {public_files[key]}")


def write_summary(receipts: list[dict[str, Any]]) -> None:
    summary = {
        "contract_name": "chummer.promo_video_rework_20260602",
        "generated_at_utc": utc_now(),
        "status": "pass",
        "reason": "The middle Every Wonder Horizon reel now uses MagicFit scene clips instead of local UI cards, and all rebuilt reels carry spoken feature narration plus a music bed.",
        "assets": [
            {
                "asset_id": receipt["asset_id"],
                "render_mode": receipt["render_mode"],
                "narration_provider": receipt["narration_provider"],
                "scene_count": receipt["scene_count"],
                "duration_seconds": float(dict(receipt["mp4_probe"].get("format") or {}).get("duration") or 0.0),
                "mp4": receipt["public_files"]["mp4"],
            }
            for receipt in receipts
        ],
    }
    (OUT / "PROMO_REWORK_RECEIPT.generated.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Rebuild public promo reels from MagicFit clips with spoken narration.")
    parser.add_argument("--only", default="", help="comma-separated asset ids to rebuild")
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    PUBLIC_DIR.mkdir(parents=True, exist_ok=True)
    reels = [
        flagship_reel(),
        every_wonder_reel(),
        horizons_reel(
            "all-horizons-90s-magicfit-promo",
            "All Horizons 90s MagicFit Promo",
            "11 MagicFit-rendered Horizon scene clips rebuilt with cleaner spoken narration",
        ),
    ]
    if args.only:
        selected = {item.strip() for item in args.only.split(",") if item.strip()}
        reels = [reel for reel in reels if reel.asset_id in selected]
    receipts = [build_reel(reel) for reel in reels]
    for receipt in receipts:
        verify_receipt(receipt)
    write_summary(receipts)
    print("PROMO_REELS_REBUILT_WITH_NARRATION")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

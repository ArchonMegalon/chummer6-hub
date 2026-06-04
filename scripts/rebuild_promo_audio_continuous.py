#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import shutil
import subprocess
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


WORKSPACE = Path("/docker/chummercomplete")
REPO = WORKSPACE / "chummer.run-services"
PUBLIC = REPO / "Chummer.Run.Api" / "wwwroot" / "media" / "promo"
HORIZON_VIDEOS = WORKSPACE / "_completion" / "horizon_flagship_reels_20260602" / "videos"
OUT = WORKSPACE / "_completion" / "promo_audio_continuous_20260602"
TTS_PYTHON = WORKSPACE / "_completion" / "promo_video_rework_20260602" / "tts_venv" / "bin" / "python"
DOCUMENTARY_VOICE = "en-GB-ThomasNeural"
UNMIXR_API_URL = "https://unmixr.com/api/v1/short-tts/"


@dataclass(frozen=True)
class AudioPlan:
    asset_id: str
    video: Path
    title: str
    script: str
    voice: str = DOCUMENTARY_VOICE


SCRIPTS: dict[str, str] = {
    "chummer6-flagship-promo": (
        "The old way always sounds the same. Tabs open. Notes scattered. A runner sheet half remembered. The GM buying time while the table waits for the moment to come back alive. "
        "Chummer6 is built for the instant when preparation has to become play. It gathers the runner, the crew, the scene, the consequence, and the next decision into one surface that can actually survive pressure. "
        "You build with the truth in view: gear, chrome, magic, tradeoffs, and every number explained clearly enough that the table can trust it. "
        "You run with momentum: scenes, handouts, opposition, downtime, hooks, and fallout ready when the room needs them. "
        "And when the city answers, it does not answer as flavor text. It answers with heat, factions, jobs, and consequences the GM can turn into tomorrow night's trouble. "
        "House rules stop living as arguments in old chat logs. Recaps stop dissolving into rumor. The aftermath becomes signal. The signal becomes the next run. "
        "From desktop to tablet to phone, from home table to remote night, Chummer6 is for crews who want the world to remember what they did and still be ready when the next door blows open."
    ),
    "all-horizons-90s-magicfit-promo": (
        "The Horizons are not separate fantasies. They are one answer told from nine angles. What happens when the campaign grows larger than the tools trying to hold it. "
        "NEXUS-PAN keeps the crew connected when devices drift and players return mid-scene. ALICE turns a cool runner idea into a build that can survive contact with the table. "
        "KARMA FORGE gives house rules a governed shape. JACKPOINT gives memory a voice. RUNSITE turns dangerous locations into spaces the crew can actually read before the breach. "
        "RUNBOOK PRESS turns seasons of campaign truth into artifacts worth keeping. TABLE PULSE governs pressure, reaction, and aftermath without stealing the room. "
        "BLACK LEDGER lets the city remember who touched it and what that cost. COMMUNITY HUB helps the right people find the right run and carry the result forward. "
        "Taken together, the Horizons are not noise around the campaign. They are its support systems, its memory, its pressure, its continuity, and its broadcast back into the world. "
        "Nine Horizons. One direction. Less friction, more momentum, and a campaign that keeps getting bigger without losing the human pulse that made it matter."
    ),
    "every-wonder-horizon-promo": (
        "Every Wonder is the promise that scale does not have to cost intimacy. A campaign can spread across devices, sessions, factions, recaps, handoffs, locations, and consequences without losing the feeling of a real table making real choices together. "
        "That kind of growth should feel electrifying, not fragile. The player who returns should know where the scene is. The GM should know what changed, what is private, and what can safely move into the light. "
        "A house rule should earn trust before it lands. A mission site should feel playable before it becomes lethal. A recap should pull the crew back into the story instead of burying them under archive noise. "
        "And after the run, the world should not go still. The city should wake up, react, and begin shaping the next invitation. "
        "Every Wonder is the larger direction behind the Horizons: let the campaign become richer, stranger, and more alive, while the people around the table still feel like they can reach in and play."
    ),
    "nexus_pan_90s_deepdive": (
        "A session never breaks because the fiction failed. It breaks because reality intruded first. A tablet sleeps. A laptop wakes crooked. A player reconnects into a scene already moving. "
        "NEXUS-PAN exists for that dangerous little gap between what the campaign knows and what the people at the table can trust. Presence has to be clear. Change has to be visible. Recovery has to feel calm enough that nobody mistakes panic for drama. "
        "A reconnect should not become a rules argument. A conflict should surface before it hardens into table folklore. Desktop, tablet, phone, remote night, train ride, home table, same campaign, same moment, no scavenger hunt for the truth. "
        "For the GM, the promise is simple: can I trust what I am seeing right now. For the player, it is even simpler: rejoin, catch up, answer the scene, stay in the run. "
        "NEXUS-PAN is continuity with a pulse, built for crews who refuse to lose the night because one device blinked first."
    ),
    "nexus-pan_epic_90s": (
        "Every long campaign eventually becomes a split screen. One player is half a city away. One sheet is stale. The GM has too many windows open and no patience left for false confidence. "
        "The epic version of NEXUS-PAN begins there, with trust as the first dramatic question. Who is connected. What changed. Which state is current enough to act on without breaking the scene. "
        "Packets move. Devices disagree. The table does not need more drama from the software. It needs signal. It needs context. It needs a clear next step before momentum dies. "
        "When conflict appears, the system should expose it cleanly and let the GM make the call before the fiction tears. The campaign should travel with the crew from desk to tablet to train to home table without export rituals, copied files, or wishful thinking. "
        "The returning player should receive the humane version of continuity: where you were, what changed, and what move is waiting. That is the fantasy here. Less ceremony. Less panic. More run."
    ),
    "alice_90s_deepdive": (
        "A flashy runner is easy to imagine and much harder to keep alive. ALICE begins where style collides with table reality, in that narrow space where a character concept either becomes a professional or folds under the first real job. "
        "The question is never just which build looks coolest. It is which build can carry the weight, absorb the tradeoffs, and still feel like the runner the player wanted to bring into the shadows. "
        "The numbers should tell a story. What became sharper. What became fragile. What was quietly sacrificed to buy the trick. Gear is not a shopping list. Chrome is not flavor. Magic is not free. Every choice leaves a shape on the sheet and a consequence in play. "
        "ALICE should not sound like a lecture from above. It should feel like a sharp-eyed coach standing beside the player, pointing at the weak seam before the first bad roll tears it open. "
        "By the end, the runner still belongs completely to the player. They are simply clearer, stronger, and more ready for the table to test them."
    ),
    "karma_forge_90s_deepdive": (
        "Every table invents house rules. Very few tables remember exactly when they did it, who agreed, what broke, or why everyone still argues about it three sessions later. "
        "KARMA FORGE treats a rule change as something powerful enough to deserve ceremony. Name it. Scope it. Preview it. Show the blast radius before anyone mistakes enthusiasm for safety. "
        "A good change should arrive with receipts: who it touches, what it shifts, where it could bend the campaign, and how to reverse it if the table hates what it becomes. Players should react in context, not excavate old chat logs like archaeologists looking for permission. "
        "Campaigns evolve. Their rule environment can evolve with them. But that evolution should feel governed, legible, and reversible, not like a private fork mutating in the dark. "
        "KARMA FORGE is for tables that want custom play without surrendering coherence."
    ),
    "jackpoint_90s_deepdive": (
        "The run is over, but the story is not. The table is laughing, exhausted, and already telling three different versions of what happened. That is where campaigns start losing themselves. "
        "JACKPOINT gives the aftermath a place with shape. Recaps. Briefings. Dossiers. Loose ends. NPC promises. What the players may know. What the GM must keep behind the curtain. "
        "Those truths need different doors. A player-facing briefing should feel like the world speaking back, not like a database export with the serial numbers still attached. A missed player should return to a clean handoff, not a twenty-minute oral history full of contradictions and fading excitement. "
        "As the season grows longer, JACKPOINT keeps memory from collapsing into vibes, screenshots, and disputed recollection. The table still owns the story. JACKPOINT simply gives that story a sharper, more dramatic way to return when next session begins."
    ),
    "runsite_90s_deepdive": (
        "A bad map shrinks a good mission. A flat location turns danger into bookkeeping. RUNSITE is for the kind of space that should feel legible, threatening, and worth arguing about before the first door even opens. "
        "A site unfolds in layers. Approach. Floor plan. Cameras. Exits. Hidden routes. Astral residue. Pressure points. The corners players will immediately try to exploit and the mistakes that will wake the building up around them. "
        "Player view stays readable. GM view keeps the teeth behind the curtain. Hotspots prepare the moments that matter without scripting the route in advance. The crew can scout, fight, improvise, and plan around a place instead of a paragraph. "
        "If they go loud, the site should answer like a living problem. If they go quiet, it should still have texture. RUNSITE makes locations matter before the breach, during the run, and in the memory that follows."
    ),
    "runbook_press_90s_deepdive": (
        "Campaign material accumulates like weather. Notes, districts, NPCs, rulings, handouts, recaps, lore, and all the strange little truths that only make sense after the fifth session have a way of drifting into separate corners. "
        "RUNBOOK PRESS turns that drifting mass into an artifact with intention. A primer. A district guide. A mission packet. A season book. A handoff worthy of the campaign that created it. "
        "Structure matters here. What the players can know. What the GM must protect. What belongs in the appendix. What needs to be findable in five seconds when the room is waiting and the night is already moving. Layout is not decoration. It is retrieval under pressure. "
        "When a new player joins, the book should welcome them into the season. When the campaign ends, it should leave behind something the table wants to keep. RUNBOOK PRESS is not about export. It is about memory made readable."
    ),
    "table_pulse_90s_deepdive": (
        "Pressure is part of the drama, but pressure without boundaries becomes noise. TABLE PULSE exists to keep the room tense, alive, and readable without turning the session into a dashboard performance. "
        "The GM sees the signal first. The system offers pressure, reaction, and aftermath as packets, not commandments. The table can be nudged when a scene needs oxygen and left alone when silence is the better choice. "
        "Players who are not physically in the room can still matter when they join an opposing faction. If they opt in, they can receive a bounded notification, send a reaction, and push back from outside the table without hijacking the moment inside it. After the run, they can receive a focused summary of what happened, who won, and what fallout now belongs to their side. "
        "Consent, quiet hours, opt-outs, and table policy are not decoration around the system. They are the system. A good pulse is felt in the scene, in the aftermath, and in the rising tension of the campaign, while the software itself almost disappears."
    ),
    "black_ledger_90s_deepdive": (
        "Too many campaign cities forget everything by morning. BLACK LEDGER is for the kind of city that keeps score, not on a spreadsheet, but in bruised districts, nervous factions, shifting jobs, and people who suddenly have reason to care what the crew just broke. "
        "After the run, the world should move. Not as homework. As consequence. Heat changes hands. Favors sour. Rumors harden into opportunity. A quiet neighborhood becomes dangerous because the crew made noise there yesterday. "
        "Faction pressure works best when it creates decisions, not encyclopedia weight. The newsroom gives the city a voice: dramatic, biased, occasionally cruel, and just useful enough to become tomorrow night's hook. "
        "By the time the next session begins, the world should already have opinions. BLACK LEDGER is for campaigns where the map remembers, the city pushes back, and the fallout is always looking for a new owner."
    ),
    "community_hub_90s_deepdive": (
        "Finding the right table should not feel harder than surviving the run. COMMUNITY HUB begins with the lonely player, the overworked GM, and the gap between wanting a game and actually getting one to happen without chaos. "
        "Open runs need more than a signup button. They need tone, schedule, safety, expectations, and a reason this particular runner belongs in this particular trouble. Runner preflight should catch problems before anyone is trapped in voice chat waiting for a decision that could have been made yesterday. "
        "A roster is not a list of names. It is chemistry, role fit, availability, consent, and the stubborn practical question of whether this crew can actually meet and play. Scheduling should remove friction, not create another place for the truth to go missing. "
        "The best outcome remains beautifully simple: the right people find the right run, the night actually happens, and the campaign remembers what came out the other side."
    ),
    "black_ledger_epic_90s": (
        "BLACK LEDGER begins with a dead-map problem. The crew leaves a crater in the world, and somehow the city wakes up unchanged. That is not consequence. That is amnesia. "
        "In the epic version, the city comes alive like another character at the table. World ticks turn fallout into motion. A quiet district gets hot. A trusted route turns risky. A favor becomes leverage. A mistake becomes the seed of the next mission. "
        "The mission market starts to feel earned because opportunity no longer drops from the sky. It grows from what the crew actually did. Faction pressure becomes playable tension instead of lore the players are expected to memorize. "
        "And the newsroom gives the whole machine a voice: rumor, spin, fear, mockery, propaganda, and the kind of half-truth runners know how to weaponize. BLACK LEDGER is for campaigns where the city remembers the damage and develops an attitude about it."
    ),
}

VOICE_BY_ASSET: dict[str, str] = {
    asset_id: DOCUMENTARY_VOICE
    for asset_id in [
        "chummer6-flagship-promo",
        "all-horizons-90s-magicfit-promo",
        "every-wonder-horizon-promo",
        "nexus_pan_90s_deepdive",
        "alice_90s_deepdive",
        "karma_forge_90s_deepdive",
        "jackpoint_90s_deepdive",
        "runsite_90s_deepdive",
        "runbook_press_90s_deepdive",
        "table_pulse_90s_deepdive",
        "black_ledger_90s_deepdive",
        "community_hub_90s_deepdive",
        "black_ledger_epic_90s",
        "nexus-pan_epic_90s",
    ]
}


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
    return float((probe(path).get("format") or {}).get("duration") or 0.0)


def unmixr_config() -> dict[str, str] | None:
    api_key = os.environ.get("UNMIXR_API_KEY", "").strip()
    voice_id = os.environ.get("UNMIXR_VOICE_ID", "").strip()
    if not api_key or not voice_id:
        return None
    return {
        "api_key": api_key,
        "voice_id": voice_id,
        "language": os.environ.get("UNMIXR_LANGUAGE", "en-US").strip() or "en-US",
        "speaking_rate": os.environ.get("UNMIXR_SPEAKING_RATE", "medium").strip() or "medium",
        "speaking_pitch": os.environ.get("UNMIXR_SPEAKING_PITCH", "low").strip() or "low",
        "speaking_volume": os.environ.get("UNMIXR_SPEAKING_VOLUME", "medium").strip() or "medium",
    }


def render_unmixr_tts(text: str, output: Path) -> bool:
    config = unmixr_config()
    if config is None:
        return False
    payload = json.dumps(
        {
            "text": text,
            "voice_id": config["voice_id"],
            "language": config["language"],
            "speaking_rate": config["speaking_rate"],
            "speaking_pitch": config["speaking_pitch"],
            "speaking_volume": config["speaking_volume"],
            "output_type": output.suffix.lstrip(".") or "mp3",
            "response_type": "url",
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        UNMIXR_API_URL,
        data=payload,
        headers={
            "Authorization": f"Bearer {config['api_key']}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            body = json.loads(response.read().decode("utf-8"))
        audio_url = str(body.get("audio_url") or "").strip()
        if not audio_url:
            return False
        with urllib.request.urlopen(audio_url, timeout=120) as audio_response:
            output.write_bytes(audio_response.read())
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
        return False
    return output.exists() and output.stat().st_size > 0


def split_script_into_beats(text: str) -> list[str]:
    pieces = [part.strip() for part in re.split(r"(?<=[.!?])\s+", text.strip()) if part.strip()]
    if not pieces:
        return [text.strip()]
    beats: list[str] = []
    pending = ""
    for piece in pieces:
        words = len(piece.split())
        if pending:
            piece = f"{pending} {piece}"
            pending = ""
            words = len(piece.split())
        if words < 8 and beats:
            beats[-1] = f"{beats[-1]} {piece}".strip()
            continue
        if words < 6:
            pending = piece
            continue
        beats.append(piece)
    if pending:
        if beats:
            beats[-1] = f"{beats[-1]} {pending}".strip()
        else:
            beats.append(pending)
    return beats or [text.strip()]


async def render_edge_tts(text: str, voice: str, output: Path) -> bool:
    if not TTS_PYTHON.is_file():
        return False
    helper = OUT / "render_edge_tts_continuous.py"
    helper.write_text(
        "import asyncio, edge_tts, pathlib, sys\n"
        "async def main():\n"
        "    voice, text, output = sys.argv[1], sys.argv[2], pathlib.Path(sys.argv[3])\n"
        "    communicate = edge_tts.Communicate(text=text, voice=voice, rate='-9%', pitch='-7Hz')\n"
        "    await communicate.save(str(output))\n"
        "asyncio.run(main())\n",
        encoding="utf-8",
    )
    proc = await asyncio.create_subprocess_exec(
        str(TTS_PYTHON),
        str(helper),
        voice,
        text,
        str(output),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()
    if proc.returncode != 0:
        print(stderr.decode("utf-8", errors="replace"))
        return False
    return output.exists() and output.stat().st_size > 0


def render_fallback_tts(text: str, output: Path) -> None:
    escaped = text.replace("\\", "\\\\").replace("'", "\\'")
    run("ffmpeg", "-y", "-f", "lavfi", "-i", f"flite=text='{escaped}':voice=slt", "-ar", "48000", "-ac", "1", str(output))


def pause_duration_for(text: str) -> float:
    words = len(text.split())
    tail = text.rstrip()[-1:] if text.rstrip() else ""
    base = 0.16 if words <= 9 else 0.22 if words <= 16 else 0.28
    if tail in "!?":
        base += 0.06
    elif tail == ".":
        base += 0.04
    return min(base, 0.42)


def render_pause(output: Path, seconds: float) -> None:
    run(
        "ffmpeg",
        "-y",
        "-f",
        "lavfi",
        "-i",
        f"anullsrc=r=48000:cl=mono:d={seconds:.3f}",
        "-c:a",
        "pcm_s16le",
        str(output),
    )


def normalize_beat(source: Path, output: Path) -> None:
    run(
        "ffmpeg",
        "-y",
        "-i",
        str(source),
        "-af",
        "afade=t=in:st=0:d=0.03,highpass=f=60,lowpass=f=12000,alimiter=limit=0.96",
        "-ar",
        "48000",
        "-ac",
        "1",
        "-c:a",
        "pcm_s16le",
        str(output),
    )


def concat_audio_parts(parts: list[Path], output: Path) -> None:
    manifest = output.with_suffix(".concat.txt")
    manifest.write_text("".join(f"file '{part}'\n" for part in parts), encoding="utf-8")
    run("ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(manifest), "-c:a", "pcm_s16le", str(output))


def render_stitched_narration(plan: AudioPlan, work: Path) -> tuple[Path, str, str]:
    beats = split_script_into_beats(plan.script)
    beat_dir = work / "beats"
    beat_dir.mkdir(parents=True, exist_ok=True)
    parts: list[Path] = []
    provider = "unmixr-short-tts-beats"
    voice_used = os.environ.get("UNMIXR_VOICE_ID", "").strip() or plan.voice
    for index, beat in enumerate(beats, start=1):
        raw = beat_dir / f"beat-{index:02d}.mp3"
        ok = render_unmixr_tts(beat, raw)
        if not ok:
            provider = "edge-tts-beats"
            voice_used = plan.voice
            raw = beat_dir / f"beat-{index:02d}.mp3"
            ok = asyncio.run(render_edge_tts(beat, plan.voice, raw))
        if not ok:
            provider = "ffmpeg-flite-beats"
            voice_used = "flite-slt"
            raw = beat_dir / f"beat-{index:02d}.wav"
            render_fallback_tts(beat, raw)
        normalized = beat_dir / f"beat-{index:02d}.wav"
        normalize_beat(raw, normalized)
        parts.append(normalized)
        if index < len(beats):
            pause = beat_dir / f"pause-{index:02d}.wav"
            render_pause(pause, pause_duration_for(beat))
            parts.append(pause)
    stitched = work / "continuous-narration.wav"
    concat_audio_parts(parts, stitched)
    return stitched, provider, voice_used


def cinematic_bed_filter(target_duration: float) -> str:
    fade_out = min(2.8, max(target_duration / 3.0, 0.3))
    return (
        "aevalsrc="
        f"'0.030*sin(2*PI*(43+1.7*sin(2*PI*0.05*t))*t)+"
        "0.018*sin(2*PI*(86+2.4*sin(2*PI*0.037*t))*t)+"
        "0.011*sin(2*PI*129*t)+0.007*sin(2*PI*172*t)+0.004*sin(2*PI*258*t)'"
        f":s=48000:d={target_duration:.3f},"
        "highpass=f=32,lowpass=f=3600,bass=g=2.8:f=94:w=0.8,"
        "tremolo=f=0.16:d=0.18,acompressor=threshold=-30dB:ratio=1.8:attack=30:release=280:makeup=1.5,"
        f"afade=t=in:st=0:d={min(1.4, max(target_duration / 3.0, 0.2)):.3f},"
        f"afade=t=out:st={max(target_duration - fade_out, 0):.3f}:d={fade_out:.3f},"
        "volume=1.32[bed]"
    )


def audio_filter_for(narration: Path, target_duration: float) -> str:
    source_duration = duration(narration)
    target_vo = max(target_duration - 3.6, 1.0)
    if source_duration > target_vo:
        tempo = min(max(source_duration / target_vo, 1.0), 1.18)
        prep = f"atempo={tempo:.5f},atrim=0:{target_vo:.3f},asetpts=PTS-STARTPTS"
        fit_mode = f"sped_up_{tempo:.3f}"
    elif source_duration and source_duration < target_vo * 0.94:
        tempo = max(source_duration / target_vo, 0.88)
        prep = f"atempo={tempo:.5f},atrim=0:{target_vo:.3f},asetpts=PTS-STARTPTS"
        fit_mode = f"stretched_{tempo:.3f}"
    else:
        prep = f"atrim=0:{target_vo:.3f},asetpts=PTS-STARTPTS"
        fit_mode = "natural_slow"
    return (
        f"[0:a]{prep},afade=t=in:st=0:d=0.45,afade=t=out:st={max(target_vo - 0.75, 0):.3f}:d=0.75,"
        "highpass=f=72,lowpass=f=9000,bass=g=2.4:f=110:w=0.65,"
        "acompressor=threshold=-22dB:ratio=2.5:attack=20:release=280:makeup=2.2,alimiter=limit=0.87[vo0];"
        f"[vo0]adelay=1200|1200,apad,atrim=0:{target_duration:.3f},volume=1.10[vo];"
        f"{cinematic_bed_filter(target_duration)};"
        "[bed][vo]amix=inputs=2:duration=first:dropout_transition=0,alimiter=limit=0.91[a]"
        f" # {fit_mode}"
    )


def build_audio(narration: Path, target_duration: float, output: Path) -> None:
    filter_complex = audio_filter_for(narration, target_duration).split(" # ", 1)[0]
    run(
        "ffmpeg",
        "-y",
        "-i",
        str(narration),
        "-filter_complex",
        filter_complex,
        "-map",
        "[a]",
        "-c:a",
        "pcm_s16le",
        str(output),
    )


def remux(video: Path, audio: Path, output: Path, target_duration: float) -> None:
    temp = output.with_suffix(".continuous-audio.tmp.mp4")
    run(
        "ffmpeg",
        "-y",
        "-i",
        str(video),
        "-i",
        str(audio),
        "-map",
        "0:v:0",
        "-map",
        "1:a:0",
        "-t",
        f"{target_duration:.3f}",
        "-c:v",
        "copy",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-movflags",
        "+faststart",
        str(temp),
    )
    shutil.move(str(temp), str(output))


def plans(selected: set[str] | None) -> list[AudioPlan]:
    items: list[AudioPlan] = [
        AudioPlan(asset, PUBLIC / f"{asset}.mp4", title, SCRIPTS[asset], voice=VOICE_BY_ASSET[asset])
        for asset, title in [
            ("chummer6-flagship-promo", "Chummer6 Flagship Promo v5 Continuous Audio"),
            ("all-horizons-90s-magicfit-promo", "All Horizons 90s Public Teaser v5 Continuous Audio"),
            ("every-wonder-horizon-promo", "Every Wonder Horizon Promo v5 Continuous Audio"),
        ]
    ]
    for asset in [
        "nexus_pan_90s_deepdive",
        "alice_90s_deepdive",
        "karma_forge_90s_deepdive",
        "jackpoint_90s_deepdive",
        "runsite_90s_deepdive",
        "runbook_press_90s_deepdive",
        "table_pulse_90s_deepdive",
        "black_ledger_90s_deepdive",
        "community_hub_90s_deepdive",
        "black_ledger_epic_90s",
        "nexus-pan_epic_90s",
    ]:
        items.append(AudioPlan(asset, HORIZON_VIDEOS / f"{asset}.mp4", f"{asset} v3 Continuous Audio", SCRIPTS[asset], voice=VOICE_BY_ASSET[asset]))
    if selected:
        items = [item for item in items if item.asset_id in selected]
    return items


def rebuild(plan: AudioPlan) -> dict[str, Any]:
    if not plan.video.exists():
        raise SystemExit(f"missing video: {plan.video}")
    work = OUT / plan.asset_id
    work.mkdir(parents=True, exist_ok=True)
    target_duration = duration(plan.video)
    tts, provider, voice_used = render_stitched_narration(plan, work)
    mixed = work / "continuous-audio.wav"
    build_audio(tts, target_duration, mixed)
    original = work / f"{plan.asset_id}.before-continuous-audio.mp4"
    shutil.copy2(plan.video, original)
    remux(plan.video, mixed, plan.video, target_duration)
    result_probe = probe(plan.video)
    receipt = {
        "generated_at_utc": utc_now(),
        "status": "published",
        "asset_id": plan.asset_id,
        "title": plan.title,
        "video": str(plan.video),
        "previous_video_backup": str(original),
        "audio_mode": "stitched_cinematic_narration_track",
        "narration_provider": provider,
        "voice": voice_used,
        "no_scene_audio_cuts": True,
        "beat_count": len(split_script_into_beats(plan.script)),
        "script": plan.script,
        "script_word_count": len(plan.script.split()),
        "target_duration_seconds": target_duration,
        "narration_duration_seconds": duration(tts),
        "mp4_probe": result_probe,
    }
    (work / "CONTINUOUS_AUDIO_RECEIPT.generated.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description="Replace promo audio with a single slow continuous narration track.")
    parser.add_argument("--only", default="", help="comma-separated asset ids")
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    selected = {part.strip() for part in args.only.split(",") if part.strip()} or None
    receipts = [rebuild(plan) for plan in plans(selected)]
    gate = {
        "generated_at_utc": utc_now(),
        "status": "pass",
        "assets": [],
    }
    for receipt in receipts:
        streams = receipt["mp4_probe"].get("streams") or []
        length = float((receipt["mp4_probe"].get("format") or {}).get("duration") or 0)
        audio = sum(1 for stream in streams if stream.get("codec_type") == "audio")
        video = sum(1 for stream in streams if stream.get("codec_type") == "video")
        item = {
            "asset_id": receipt["asset_id"],
            "duration_seconds": length,
            "audio_streams": audio,
            "video_streams": video,
            "word_count": receipt["script_word_count"],
            "narration_duration_seconds": receipt["narration_duration_seconds"],
            "no_scene_audio_cuts": receipt["no_scene_audio_cuts"],
        }
        if length < 89.5 or audio != 1 or video != 1:
            gate["status"] = "fail"
        gate["assets"].append(item)
    (OUT / "CONTINUOUS_PROMO_AUDIO_GATE.generated.json").write_text(json.dumps(gate, indent=2) + "\n", encoding="utf-8")
    print("CONTINUOUS_PROMO_AUDIO_READY" if gate["status"] == "pass" else "NOT_READY")
    return 0 if gate["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())

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
HORIZON_PUBLIC = REPO / "Chummer.Run.Api" / "wwwroot" / "media" / "horizons"
OUT = WORKSPACE / "_completion" / "promo_audio_continuous_20260602"
TTS_PYTHON = WORKSPACE / "_completion" / "promo_video_rework_20260602" / "tts_venv" / "bin" / "python"
DOCUMENTARY_VOICE = "en-GB-ThomasNeural"
FEMALE_DOCUMENTARY_VOICE = "en-US-JennyNeural"
UNMIXR_API_URL = "https://unmixr.com/api/v1/short-tts/"
UNMIXR_PROMO_VOICE_ENV_KEYS = (
    "UNMIXR_PREMIUM_NARRATOR_VOICE_ID",
    "UNMIXR_NARRATOR_VOICE_ID",
    "UNMIXR_VOICE_ID",
)
HIGH_TONE_CLEANUP_FILTER = "equalizer=f=11730:width_type=h:width=420:g=-48,lowpass=f=10000"
ENV_FILES = (
    WORKSPACE / "chummer.run-services" / ".env",
    Path("/docker/EA/.env"),
    Path("/docker/EA/ea/.env"),
)


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
        "Chummer6 should not feel like a shelf of future brands. It should feel like one product spine. "
        "Start with the workbench. Build the runner, inspect the numbers, understand the sources, and keep the dense rhythm that veteran users expect. "
        "ALICE is part of that base product: build help, rules explanation, tradeoff warnings, and a clearer path from a cool idea to a runner who can survive the table. "
        "Origin Dossier belongs beside it, turning the life behind the stats into contacts, debts, enemies, scars, secrets, and approved canon the campaign can remember. "
        "Ready for Tonight, Runner Passport, Knowledge Fabric, Table Pulse, and GM Cockpit are product areas, not a pile of disconnected Horizons. They help the table return, explain, run, and remember. "
        "The future shelf should be saved for bigger bets: Karma Forge, Black Ledger, publishing, community, and specialized play modes. NEXUS-PAN is continuity and recovery, so it belongs in the product story. "
        "That is the cleaner promise. Build clearly. Run reliably. Remember consequences. Publish only what the table approves."
    ),
    "every-wonder-horizon-promo": (
        "Chummer6 should not ask players to memorize a shelf of labels before they know why the product matters. It starts with one table: runners, rules, scenes, people, and consequences in reach. "
        "Some areas are base product workbenches. ALICE helps with builds and tradeoffs. Origin Dossier turns the life behind the stats into contacts, enemies, debts, scars, and secrets. Table Pulse keeps campaign pressure bounded and playable. "
        "Some ideas are expansion bets, and they should be named honestly. NEXUS-PAN is device continuity. KARMA FORGE is governed rule evolution. BLACK LEDGER is the living city. "
        "Other lanes are clearer when they are called what they are: campaign memory, mission-space prep, publishing, community, and specialized play modes. "
        "The cleaner promise is simple: build clearly, run reliably, remember consequences, and publish only what the table approves."
    ),
    "nexus-pan-90s-deepdive": (
        "A session never breaks because the fiction failed. It breaks because reality intruded first. A tablet sleeps. A laptop wakes crooked. A player reconnects into a scene already moving. "
        "NEXUS-PAN exists for that dangerous little gap between what the campaign knows and what the people at the table can trust. Presence has to be clear. Change has to be visible. Recovery has to feel calm enough that nobody mistakes panic for drama. "
        "A reconnect should not become a rules argument. A conflict should surface before it hardens into table folklore. Desktop, tablet, phone, remote night, train ride, home table, same campaign, same moment, no scavenger hunt for the truth. "
        "For the GM, the promise is simple: can I trust what I am seeing right now. For the player, it is even simpler: rejoin, catch up, answer the scene, stay in the run. "
        "NEXUS-PAN is continuity with a pulse, built for crews who refuse to lose the night because one device blinked first."
    ),
    "nexus-pan-epic-90s": (
        "Every long campaign eventually becomes a split screen. One player is half a city away. One sheet is stale. The GM has too many windows open and no patience left for false confidence. "
        "The epic version of NEXUS-PAN begins there, with trust as the first dramatic question. Who is connected. What changed. Which state is current enough to act on without breaking the scene. "
        "Packets move. Devices disagree. The table does not need more drama from the software. It needs signal. It needs context. It needs a clear next step before momentum dies. "
        "When conflict appears, the system should expose it cleanly and let the GM make the call before the fiction tears. The campaign should travel with the crew from desk to tablet to train to home table without export rituals, copied files, or wishful thinking. "
        "The returning player should receive the humane version of continuity: where you were, what changed, and what move is waiting. That is the fantasy here. Less ceremony. Less panic. More run."
    ),
    "alice-90s-deepdive": (
        "ALICE starts where a stylish runner concept meets the cold math of a real table. The fantasy matters. The look, the attitude, the role in the crew all need to survive contact with initiative, recoil, drain, money, availability, and the kind of mission that punishes vague confidence. "
        "First, she reads the sheet like a professional looking for pressure points. What is the runner actually good at. Where does the build fold. Which weakness is deliberate, and which one only appeared because the numbers were hard to see. "
        "Then she turns tradeoffs into plain language. Chrome buys speed and costs Essence. Magic opens doors and demands discipline. Gear solves problems until legality, concealment, noise, and cash start pushing back. A clever trick is not useful if the table cannot understand when it works. "
        "When the video moves from portrait to choices to warnings, the voice keeps one continuous line of thought: not scene labels, but momentum. We are watching a concept become table-ready, a first draft becoming something the whole crew can trust when the run starts moving. "
        "ALICE does not take authorship away from the player. She keeps the concept intact while making consequences visible early enough to choose them on purpose. The GM gets clearer risk. The player gets a runner who can enter the scene with fewer surprises and better reasons. "
        "The point is not optimization for its own sake. It is confidence. A character who still feels like the person you imagined, but now has a structure strong enough for the shadows to test."
    ),
    "karma-forge-90s-deepdive": (
        "Every table invents house rules. Very few tables remember exactly when they did it, who agreed, what broke, or why everyone still argues about it three sessions later. "
        "KARMA FORGE treats a rule change as something powerful enough to deserve ceremony. Name it. Scope it. Preview it. Show the blast radius before anyone mistakes enthusiasm for safety. "
        "A good change should arrive with receipts: who it touches, what it shifts, where it could bend the campaign, and how to reverse it if the table hates what it becomes. Players should react in context, not excavate old chat logs like archaeologists looking for permission. "
        "Campaigns evolve. Their rule environment can evolve with them. But that evolution should feel governed, legible, and reversible, not like a private fork mutating in the dark. "
        "KARMA FORGE is for tables that want custom play without surrendering coherence."
    ),
    "jackpoint-90s-deepdive": (
        "The run is over, but the story is not. The table is laughing, exhausted, and already telling three different versions of what happened. That is where campaigns start losing themselves. "
        "JACKPOINT gives the aftermath a place with shape. Recaps. Briefings. Dossiers. Loose ends. NPC promises. What the players may know. What the GM must keep behind the curtain. "
        "Those truths need different doors. A player-facing briefing should feel like the world speaking back, not like a database export with the serial numbers still attached. A missed player should return to a clean handoff, not a twenty-minute oral history full of contradictions and fading excitement. "
        "As the season grows longer, JACKPOINT keeps memory from collapsing into vibes, screenshots, and disputed recollection. The table still owns the story. JACKPOINT simply gives that story a sharper, more dramatic way to return when next session begins."
    ),
    "runsite-90s-deepdive": (
        "A bad map shrinks a good mission. A flat location turns danger into bookkeeping. RUNSITE is for the kind of space that should feel legible, threatening, and worth arguing about before the first door even opens. "
        "A site unfolds in layers. Approach. Floor plan. Cameras. Exits. Hidden routes. Astral residue. Pressure points. The corners players will immediately try to exploit and the mistakes that will wake the building up around them. "
        "Player view stays readable. GM view keeps the teeth behind the curtain. Hotspots prepare the moments that matter without scripting the route in advance. The crew can scout, fight, improvise, and plan around a place instead of a paragraph. "
        "If they go loud, the site should answer like a living problem. If they go quiet, it should still have texture. RUNSITE makes locations matter before the breach, during the run, and in the memory that follows."
    ),
    "runbook-press-90s-deepdive": (
        "Campaign material accumulates like weather. Notes, districts, NPCs, rulings, handouts, recaps, lore, and all the strange little truths that only make sense after the fifth session have a way of drifting into separate corners. "
        "RUNBOOK PRESS turns that drifting mass into an artifact with intention. A primer. A district guide. A mission packet. A season book. A handoff worthy of the campaign that created it. "
        "Structure matters here. What the players can know. What the GM must protect. What belongs in the appendix. What needs to be findable in five seconds when the room is waiting and the night is already moving. Layout is not decoration. It is retrieval under pressure. "
        "When a new player joins, the book should welcome them into the season. When the campaign ends, it should leave behind something the table wants to keep. RUNBOOK PRESS is not about export. It is about memory made readable."
    ),
    "table-pulse-90s-deepdive": (
        "Pressure is part of the drama, but pressure without boundaries becomes noise. TABLE PULSE exists to keep the room tense, alive, and readable without turning the session into a dashboard performance. "
        "The GM sees the signal first. The system offers pressure, reaction, and aftermath as packets, not commandments. The table can be nudged when a scene needs oxygen and left alone when silence is the better choice. "
        "Players who are not physically in the room can still matter when they join an opposing faction. If they opt in, they can receive a bounded notification, send a reaction, and push back from outside the table without hijacking the moment inside it. After the run, they can receive a focused summary of what happened, who won, and what fallout now belongs to their side. "
        "Consent, quiet hours, opt-outs, and table policy are not decoration around the system. They are the system. A good pulse is felt in the scene, in the aftermath, and in the rising tension of the campaign, while the software itself almost disappears."
    ),
    "black-ledger-90s-deepdive": (
        "Too many campaign cities forget everything by morning. BLACK LEDGER is for the kind of city that keeps score, not on a spreadsheet, but in bruised districts, nervous factions, shifting jobs, and people who suddenly have reason to care what the crew just broke. "
        "After the run, the world should move. Not as homework. As consequence. Heat changes hands. Favors sour. Rumors harden into opportunity. A quiet neighborhood becomes dangerous because the crew made noise there yesterday. "
        "Faction pressure works best when it creates decisions, not encyclopedia weight. The newsroom gives the city a voice: dramatic, biased, occasionally cruel, and just useful enough to become tomorrow night's hook. "
        "By the time the next session begins, the world should already have opinions. BLACK LEDGER is for campaigns where the map remembers, the city pushes back, and the fallout is always looking for a new owner."
    ),
    "community-hub-90s-deepdive": (
        "Finding the right table should not feel harder than surviving the run. COMMUNITY HUB begins with the lonely player, the overworked GM, and the gap between wanting a game and actually getting one to happen without chaos. "
        "Open runs need more than a signup button. They need tone, schedule, safety, expectations, and a reason this particular runner belongs in this particular trouble. Runner preflight should catch problems before anyone is trapped in voice chat waiting for a decision that could have been made yesterday. "
        "A roster is not a list of names. It is chemistry, role fit, availability, consent, and the stubborn practical question of whether this crew can actually meet and play. Scheduling should remove friction, not create another place for the truth to go missing. "
        "The best outcome remains beautifully simple: the right people find the right run, the night actually happens, and the campaign remembers what came out the other side."
    ),
    "black-ledger-epic-90s": (
        "BLACK LEDGER begins with a dead-map problem. The crew leaves a crater in the world, and somehow the city wakes up unchanged. That is not consequence. That is amnesia. "
        "In the epic version, the city comes alive like another character at the table. World ticks turn fallout into motion. A quiet district gets hot. A trusted route turns risky. A favor becomes leverage. A mistake becomes the seed of the next mission. "
        "The mission market starts to feel earned because opportunity no longer drops from the sky. It grows from what the crew actually did. Faction pressure becomes playable tension instead of lore the players are expected to memorize. "
        "And the newsroom gives the whole machine a voice: rumor, spin, fear, mockery, propaganda, and the kind of half-truth runners know how to weaponize. BLACK LEDGER is for campaigns where the city remembers the damage and develops an attitude about it."
    ),
    "origin-dossier-90s-deepdive": (
        "A runner sheet can tell you what someone can do. It rarely tells you why they keep doing it when the job turns ugly. "
        "Origin Dossier begins in that gap between numbers and motive. It turns biography into playable pressure: contacts who expect something, enemies who remember too much, debts that pull at the wrong moment, and scars that still shape the next decision. "
        "The goal is not to replace the player. It is to give the player sharper material to approve, reject, and bring to the table with confidence. "
        "When the GM needs a hook, the dossier should already know which thread has emotional weight. When the crew needs a reason to care, the past can answer without becoming a lecture. "
        "A good origin does not trap the runner in backstory. It gives the campaign handles. Origin Dossier makes those handles clear, useful, and ready for trouble."
    ),
    "origin-dossier-the-name-she-chose": (
        "Some stories begin with a handle because the old name no longer fits the person walking into the shadows. "
        "The Name She Chose is an Origin Dossier proof of tone: a character history shaped into playable memory, not a generic biography pasted behind the sheet. "
        "The past arrives as pressure. A contact with a reason to call. A debt that was never fully paid. A boundary the runner refuses to cross again. A name that sounds simple until the table learns what it cost. "
        "This is what campaign memory should feel like when it is handled carefully. Approved by the player. Useful to the GM. Dramatic without stealing authorship. "
        "The sheet says what she can do. The dossier helps the table understand why she chose to become this person now."
    ),
    "origin-dossier-the-name-she-chose-20260619": (
        "Some stories begin with a handle because the old name no longer fits the person walking into the shadows. "
        "The Name She Chose is an Origin Dossier proof of tone: a character history shaped into playable memory, not a generic biography pasted behind the sheet. "
        "The past arrives as pressure. A contact with a reason to call. A debt that was never fully paid. A boundary the runner refuses to cross again. A name that sounds simple until the table learns what it cost. "
        "This is what campaign memory should feel like when it is handled carefully. Approved by the player. Useful to the GM. Dramatic without stealing authorship. "
        "The sheet says what she can do. The dossier helps the table understand why she chose to become this person now."
    ),
}

VOICE_BY_ASSET: dict[str, str] = {
    asset_id: DOCUMENTARY_VOICE
    for asset_id in [
        "chummer6-flagship-promo",
        "all-horizons-90s-magicfit-promo",
        "every-wonder-horizon-promo",
        "nexus-pan-90s-deepdive",
        "alice-90s-deepdive",
        "karma-forge-90s-deepdive",
        "jackpoint-90s-deepdive",
        "runsite-90s-deepdive",
        "runbook-press-90s-deepdive",
        "table-pulse-90s-deepdive",
        "black-ledger-90s-deepdive",
        "community-hub-90s-deepdive",
        "black-ledger-epic-90s",
        "nexus-pan-epic-90s",
        "origin-dossier-90s-deepdive",
        "origin-dossier-the-name-she-chose",
        "origin-dossier-the-name-she-chose-20260619",
    ]
}
VOICE_BY_ASSET["alice-90s-deepdive"] = FEMALE_DOCUMENTARY_VOICE


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


def env_or_file(key: str) -> str:
    value = os.environ.get(key, "").strip()
    if value:
        return value
    prefix = f"{key}="
    for env_file in ENV_FILES:
        if not env_file.is_file():
            continue
        for raw_line in env_file.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or not line.startswith(prefix):
                continue
            raw_value = line.split("=", 1)[1].strip()
            if len(raw_value) >= 2 and raw_value[0] == raw_value[-1] and raw_value[0] in {"'", '"'}:
                raw_value = raw_value[1:-1]
            return raw_value.strip()
    return ""


def unmixr_config() -> dict[str, str] | None:
    api_key = env_or_file("UNMIXR_API_KEY")
    voice_id = next((env_or_file(key) for key in UNMIXR_PROMO_VOICE_ENV_KEYS if env_or_file(key)), "")
    if not api_key or not voice_id:
        return None
    return {
        "api_key": api_key,
        "voice_id": voice_id,
        "language": env_or_file("UNMIXR_LANGUAGE") or "en-US",
        "speaking_rate": env_or_file("UNMIXR_PROMO_SPEAKING_RATE") or env_or_file("UNMIXR_SPEAKING_RATE") or "slow",
        "speaking_pitch": env_or_file("UNMIXR_SPEAKING_PITCH") or "low",
        "speaking_volume": env_or_file("UNMIXR_SPEAKING_VOLUME") or "medium",
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
        "    communicate = edge_tts.Communicate(text=text, voice=voice, rate='-8%', pitch='-4Hz', volume='+12%')\n"
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
        f"afade=t=in:st=0:d=0.03,highpass=f=60,{HIGH_TONE_CLEANUP_FILTER},alimiter=limit=0.96",
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
    fade_out = 0.08
    return (
        f"anoisesrc=color=pink:amplitude=0.080:r=48000:d={target_duration:.3f},"
        "highpass=f=320,lowpass=f=3000,bass=g=-12:f=150:w=0.8,treble=g=-4:f=3000:w=0.7,"
        "acompressor=threshold=-31dB:ratio=1.25:attack=35:release=260:makeup=1.0,"
        f"afade=t=in:st=0:d={min(1.4, max(target_duration / 3.0, 0.2)):.3f},"
        f"afade=t=out:st={max(target_duration - fade_out, 0):.3f}:d={fade_out:.3f},"
        "volume=0.62[bed]"
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
        "highpass=f=120,lowpass=f=9000,bass=g=-3.5:f=130:w=0.75,"
        "acompressor=threshold=-22dB:ratio=2.5:attack=20:release=280:makeup=2.2,alimiter=limit=0.87[vo0];"
        f"[vo0]adelay=1200|1200,apad,atrim=0:{target_duration:.3f},volume=1.18[vo];"
        f"{cinematic_bed_filter(target_duration)};"
        f"[bed][vo]amix=inputs=2:duration=longest:dropout_transition=0:normalize=0,{HIGH_TONE_CLEANUP_FILTER},apad,atrim=0:{target_duration:.3f},alimiter=limit=0.91[main];"
        f"anoisesrc=color=white:amplitude=0.180:r=48000:d={target_duration:.3f},"
        "highpass=f=620,lowpass=f=2400,volume=0.65[floor];"
        f"[main][floor]amix=inputs=2:duration=longest:dropout_transition=0:normalize=0,volume=0.72,alimiter=limit=0.76,apad,atrim=0:{target_duration:.3f}[a]"
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
        "-t",
        f"{target_duration:.3f}",
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
        "256k",
        "-shortest",
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
            ("all-horizons-90s-magicfit-promo", "Chummer6 Product Threads Public Teaser v5 Continuous Audio"),
            ("every-wonder-horizon-promo", "Chummer6 Product Spine Promo v5 Continuous Audio"),
        ]
    ]
    for asset in [
        "nexus-pan-90s-deepdive",
        "alice-90s-deepdive",
        "karma-forge-90s-deepdive",
        "jackpoint-90s-deepdive",
        "runsite-90s-deepdive",
        "runbook-press-90s-deepdive",
        "table-pulse-90s-deepdive",
        "black-ledger-90s-deepdive",
        "community-hub-90s-deepdive",
        "black-ledger-epic-90s",
        "nexus-pan-epic-90s",
        "origin-dossier-90s-deepdive",
        "origin-dossier-the-name-she-chose",
        "origin-dossier-the-name-she-chose-20260619",
    ]:
        items.append(AudioPlan(asset, HORIZON_PUBLIC / f"{asset}.mp4", f"{asset} v3 Continuous Audio", SCRIPTS[asset], voice=VOICE_BY_ASSET[asset]))
    if selected:
        items = [item for item in items if item.asset_id in selected]
    return items


def audio_stream_duration(path: Path) -> float:
    data = json.loads(
        run(
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "a:0",
            "-show_entries",
            "stream=duration",
            "-of",
            "json",
            str(path),
            capture=True,
        )
    )
    durations = [float(stream.get("duration") or 0.0) for stream in data.get("streams") or []]
    return max(durations or [0.0])


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
        "voice_posture": "premium_unmixr_narrator_preferred",
        "audio_artifact_cleanup": {
            "high_tone_notch_hz": 11730,
            "lowpass_hz": 10000,
        },
        "no_scene_audio_cuts": True,
        "beat_count": len(split_script_into_beats(plan.script)),
        "script": plan.script,
        "script_word_count": len(plan.script.split()),
        "target_duration_seconds": target_duration,
        "output_audio_duration_seconds": audio_stream_duration(plan.video),
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
            "audio_duration_seconds": receipt["output_audio_duration_seconds"],
            "audio_streams": audio,
            "video_streams": video,
            "word_count": receipt["script_word_count"],
            "narration_duration_seconds": receipt["narration_duration_seconds"],
            "no_scene_audio_cuts": receipt["no_scene_audio_cuts"],
        }
        if length < 89.5 or audio != 1 or video != 1 or float(receipt["output_audio_duration_seconds"]) < length - 0.35:
            gate["status"] = "fail"
        gate["assets"].append(item)
    (OUT / "CONTINUOUS_PROMO_AUDIO_GATE.generated.json").write_text(json.dumps(gate, indent=2) + "\n", encoding="utf-8")
    print("CONTINUOUS_PROMO_AUDIO_READY" if gate["status"] == "pass" else "NOT_READY")
    return 0 if gate["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())

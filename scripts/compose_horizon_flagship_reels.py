#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
import sys
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from _unmixr_tts import UNMIXR_SHORT_TTS_PROVIDER, load_profile, render_short_tts, slug_prefix


WORKSPACE = Path("/docker/chummercomplete")
BASE = WORKSPACE / "_completion" / "refined_magicfit_promo_plans_20260531"
MANIFEST = BASE / "REFINED_MAGICFIT_RENDER_MANIFEST.generated.json"
CLIPS = BASE / "magicfit_clips"
OUT = WORKSPACE / "_completion" / "horizon_flagship_reels_20260602"
TTS_PYTHON = WORKSPACE / "_completion" / "promo_video_rework_20260602" / "tts_venv" / "bin" / "python"
WIDTH = 1280
HEIGHT = 720
FPS = 24


DOCUMENTARY_VOICE = "en-GB-ThomasNeural"

HORIZON_VOICE: dict[str, str] = {
    "NEXUS-PAN": DOCUMENTARY_VOICE,
    "ALICE": DOCUMENTARY_VOICE,
    "KARMA FORGE": DOCUMENTARY_VOICE,
    "JACKPOINT": DOCUMENTARY_VOICE,
    "RUNSITE": DOCUMENTARY_VOICE,
    "RUNBOOK PRESS": DOCUMENTARY_VOICE,
    "TABLE PULSE": DOCUMENTARY_VOICE,
    "BLACK LEDGER": DOCUMENTARY_VOICE,
    "COMMUNITY HUB": DOCUMENTARY_VOICE,
    "ORIGIN DOSSIER": DOCUMENTARY_VOICE,
}

CUSTOM_NARRATION: dict[str, list[str]] = {
    "nexus_pan_90s_deepdive": [
        "The call starts clean. Dice on the table, maps open, everyone ready. Then one tablet drops, one laptop wakes from sleep, and nobody knows which sheet is current.",
        "This lane is about staying in the run when the gear does what gear always does. Bad signal, dying battery, browser reload, player on the train. The table keeps its place.",
        "A reconnect should not become a rules debate. The player comes back, sees what changed, what did not, and where the table is waiting.",
        "When two people touch the same thing, the GM should see the collision before it becomes folklore. Keep one state, show the conflict, make the call.",
        "The handoff matters. Desktop for the heavy work, tablet at the table, phone when someone is remote. Same campaign, same moment, no scavenger hunt.",
        "Offline play should feel honest. If the connection goes thin, the app says so plainly. No fake confidence. No silent overwrite.",
        "For the GM, the important question is simple: can I trust what I am looking at right now? Status, presence, sync health, and recovery need to be visible at a glance.",
        "For the player, it should feel boring in the best way. Rejoin, check the latest move, answer the scene, keep playing.",
        "That is the fantasy here: not louder tech. Quieter tech. The kind that disappears until the one moment it saves the night.",
        "NEXUS-PAN is the table staying together under pressure. Different devices, same run. Someone drops out, comes back, and the crew never loses the thread.",
    ],
    "nexus-pan_epic_90s": [
        "Every campaign has a moment where the room splits. One player is remote, one sheet is stale, the GM has three windows open, and the clock is still running.",
        "The epic version starts there: not with spectacle, but with trust. Who is connected? What changed? What is safe to act on?",
        "Packets move, devices disagree, and the table does not need drama from the tools. It needs a clean signal and a clear next step.",
        "Conflict is not a failure if it is visible. Show the difference, keep the context, let the GM decide before the scene breaks.",
        "The campaign should move with the crew. Desk to tablet. Table to train. Remote night to home session. No ritual of exporting, copying, and hoping.",
        "Bad signal is part of the world. The interface should admit it, hold the line, and bring the player back without pretending nothing happened.",
        "The GM gets the cockpit view: who is present, whose state is fresh, what needs attention, and what can keep rolling.",
        "The returning player gets the humane version: here is where you left, here is what changed, here is the move on the table.",
        "That is the promise. Less ceremony. Less panic. More run.",
        "NEXUS-PAN is continuity for a crew that refuses to stop because one device blinked first.",
    ],
    "alice_90s_deepdive": [
        "A flashy runner is easy to imagine and hard to survive. ALICE starts where the character concept meets the table.",
        "Put two builds side by side and the question changes. Not which one looks cool, but which one can actually do the job.",
        "The numbers should tell a story: what got stronger, what got expensive, and what you quietly sacrificed to make the trick work.",
        "Every role has a pressure point. Face, decker, street samurai, mage, infiltrator. ALICE helps spot the gap before the first bad roll exposes it.",
        "Gear is never just a shopping list. It is budget, availability, legality, maintenance, and the moment the GM asks how you got it through the door.",
        "Magic and chrome both ask for tradeoffs. The good advice is not louder, it is clearer: here is what changes, here is why it matters.",
        "The GM should not have to audit the whole sheet by hand. Flag the risky parts, explain the concern, and leave the final call at the table.",
        "When the player adjusts the build, the sheet should feel like a coach beside them, not a judge above them.",
        "By the end, the runner still belongs to the player. It is just sharper, cleaner, and less likely to fold on the first serious job.",
        "ALICE is build mentoring for crews who want cool characters that are also ready for play.",
    ],
    "origin_dossier_90s_deepdive": [
        "A runner can be legal and still feel unfinished. Origin Dossier starts where the numbers need a person behind them.",
        "The GM can add the campaign pressure: clinic debt, restricted ware, hard requirements, and the reason this story belongs at this table.",
        "Chummer turns the build and the steer into a grounded origin draft, not a hidden rule change.",
        "The player and GM approve canon before it becomes part of the dossier. Review is the feature.",
        "The approved origin becomes a bundle root: canon, PDF, portraits, scenes, narration, storyboard, and render requests.",
        "Portraits, scenes, and video make the runner easier to remember. They do not become character authority.",
        "Later, ALICE can use the approved origin to explain better next steps without pretending story prose outranks mechanics.",
        "The clinic favor can explain a debt. It cannot auto-apply ware, nuyen, qualities, magic, or legality.",
        "The runner now has history, obligations, and a clean handoff into campaign memory.",
        "Origin Dossier gives Chummer a way to make characters feel human while the rules engine stays honest.",
    ],
    "karma_forge_90s_deepdive": [
        "Every table has house rules. The problem is remembering which ones are real, which ones were jokes, and which ones quietly broke the campaign.",
        "KARMA FORGE treats a rule change like something worth handling carefully: named, scoped, reviewed, and visible to the people it affects.",
        "Before the table says yes, the GM sees the blast radius. Which builds move? Which gear shifts? Which edge case suddenly matters?",
        "Players can react to the change in context instead of digging through pinned messages and old chat arguments.",
        "A good rule earns trust by showing its work. A bad rule needs an exit before it becomes tradition.",
        "Campaigns evolve. The rules should be able to evolve with them without turning into a private fork nobody understands.",
        "When the change lands, the table sees the version, the timing, and the reason it exists.",
        "If the experiment fails, rollback is not a confession. It is part of running a healthy table.",
        "The point is not to make every table the same. It is to let each table change safely and remember what it changed.",
        "KARMA FORGE is house-rule control for GMs who like custom play but hate rule chaos.",
    ],
    "jackpoint_90s_deepdive": [
        "The run is over. The table is laughing, tired, and already remembering three different versions of what happened.",
        "JACKPOINT starts there: gather the confirmed beats, the loose ends, the NPC promises, and the details players are allowed to see.",
        "A recap should not spoil the GM layer. Player-facing truth and behind-the-screen context need different doors.",
        "Briefings become usable when they sound like the world, not like a database export.",
        "Dossiers give the next session a spine: who matters, what changed, what is dangerous, and what the crew thinks it knows.",
        "The GM can keep the secrets sharp while still giving players something polished enough to care about.",
        "When a player misses a night, they should return to a clean handoff instead of a twenty-minute oral history.",
        "When the campaign gets long, JACKPOINT keeps the memory from dissolving into vibes and old screenshots.",
        "The table still owns the story. This just gives the story a place to live between sessions.",
        "JACKPOINT is for recaps, dossiers, and briefings that make the next run feel loaded before the first roll.",
    ],
    "runsite_90s_deepdive": [
        "A bad map makes a good mission feel smaller. RUNSITE starts with spaces that should be dangerous, readable, and worth exploring.",
        "The site opens in layers: floor plan, approach, cameras, entrances, exits, and the places players will immediately try to break.",
        "Player view stays clean. GM view keeps the hidden doors, alarm logic, astral layer, opposition, and consequences behind the curtain.",
        "Hotspots let the GM prep the moments that matter without scripting the route.",
        "The crew can scout, argue, and plan around a location that feels like a place instead of a paragraph.",
        "If the players go loud, the site can answer. If they go subtle, the same space still has texture.",
        "Handouts become part of play: camera stills, access notes, safehouse sketches, and tactical glimpses that do not reveal too much.",
        "The GM stays free to improvise because the site has structure without becoming a railroad.",
        "By the time the door opens, everyone understands the stakes of the room they are entering.",
        "RUNSITE is mission-space prep for tables that want locations to matter.",
    ],
    "runbook_press_90s_deepdive": [
        "Campaign material piles up fast. Notes, districts, NPCs, rulings, handouts, recaps, and lore all drift into separate corners.",
        "RUNBOOK PRESS is for turning that pile into something the table can actually read again.",
        "A season guide needs shape: what players can know, what the GM must keep, and what belongs in the appendix.",
        "The same campaign can become a primer, a district brief, a mission packet, or a full table handoff.",
        "Layout is not decoration. It is how a busy GM finds the right page five minutes before the session starts.",
        "Exports should respect the campaign boundary: no private notes in player material, no secrets leaking because the format changed.",
        "When a new player joins, the book gets them oriented without asking the GM to retell the whole season.",
        "When the campaign ends, the table gets an artifact that feels earned.",
        "The source remains the campaign, not the export. The book is the readable form of what the table built.",
        "RUNBOOK PRESS turns living campaign material into books that can survive the session.",
    ],
    "table_pulse_90s_deepdive": [
        "Some pressure belongs at the table. Some pressure belongs after the table. TABLE PULSE exists to keep that boundary clear.",
        "Heat should feel alive without becoming a scorecard for players.",
        "The GM sees the signal, chooses the packet, and decides whether the scene needs a nudge or needs silence.",
        "Players who are not physically at the table can still matter when they join an opposing faction. If they opt in, they can receive a bounded notification, send a reaction, and answer the pressure without hijacking the room.",
        "Consent, quiet hours, opt-outs, and table policy are not afterthoughts. They decide what the system is allowed to do.",
        "After the session, they can also receive a bounded summary of the run, the result, and the fallout that belongs to their faction.",
        "The goal is not surveillance. It is pacing support for a table that already trusts its GM.",
        "When the heat rises, the system should help the scene breathe instead of making the room perform for a dashboard.",
        "A good pulse is felt in play and barely noticed as software.",
        "TABLE PULSE is live table pressure with boundaries, consent, and the GM still in charge.",
    ],
    "black_ledger_90s_deepdive": [
        "Too many campaign cities reset overnight. BLACK LEDGER is for the kind of city that remembers who kicked the door in.",
        "The globe wakes up after the run: districts shift, pressure moves, and the next job starts forming in the fallout.",
        "A world tick should feel like consequence, not homework. The GM gets motion they can use at the table.",
        "Open jobs stop appearing from nowhere. They grow out of heat, favors, failures, rumors, and people who now want something.",
        "Faction pressure works best when it creates choices, not a wall of lore.",
        "When the crew changes the map, the map should change back. Quietly at first, then loudly if they keep pushing.",
        "Newsroom beats give the world a voice: dramatic, biased, funny, and just useful enough to become tomorrow's hook.",
        "Faction identity stays in the GM's hand. The tool shows pressure; the table decides what it means.",
        "By the time the next session starts, the city already has opinions.",
        "BLACK LEDGER is living-world pressure for campaigns where consequences should become play.",
    ],
    "community_hub_90s_deepdive": [
        "Finding a table should not feel harder than surviving the run. COMMUNITY HUB starts with the lonely player and the overworked GM.",
        "Open runs need more than a signup button. They need tone, rules, schedule, safety, and a reason the character fits.",
        "Runner preflight catches problems before everyone is waiting in voice chat.",
        "A roster is not just names. It is roles, availability, expectations, and whether this crew can actually play together.",
        "Scheduling should reduce friction, not create another place where the campaign truth goes missing.",
        "The session handoff keeps the table loop intact: who joined, what happened, what changed, and what comes next.",
        "New players get a cleaner landing. Existing GMs get fewer surprises.",
        "Communities work when the tool protects the table instead of turning it into a feed.",
        "The best outcome is simple: the right people find the right run and the campaign remembers the result.",
        "COMMUNITY HUB is the bridge from looking for a game to closing out a session that mattered.",
    ],
    "black_ledger_epic_90s": [
        "BLACK LEDGER starts with the dead map problem: the crew makes noise, but too many campaign worlds stay frozen.",
        "In the epic version, the city wakes up like another character at the table.",
        "World ticks turn fallout into motion: a quiet district gets hot, a safe route becomes risky, a favor becomes a job.",
        "The mission market starts to feel earned because the next opportunity grows from what the crew actually did.",
        "Faction pressure should create tension the GM can play, not encyclopedia entries players have to memorize.",
        "When a run changes the map, the change should be visible enough to matter and loose enough to improvise.",
        "The newsroom gives the city attitude: rumors, spin, panic, jokes, and the kind of half-truth runners know how to exploit.",
        "Faction command stays abstract unless the GM wants to zoom in. Pressure first, canon later, table always in control.",
        "The campaign gets momentum because the world has a pulse between sessions.",
        "BLACK LEDGER is for GMs who want the city to push back and players who want their mess to matter.",
    ],
}


HORIZON_INTROS: dict[str, str] = {
    "ALICE": "ALICE is for the player who has a cool runner idea and needs to know if it survives contact with the table.",
    "ORIGIN DOSSIER": "ORIGIN DOSSIER is for turning an approved runner origin into a full private ebook, fitted cover, chosen portrait, optional audiobook, one cinematic scene, and later ALICE context.",
    "KARMA FORGE": "KARMA FORGE is for house rules: the good ones, the risky ones, and the ones everyone forgot they agreed to.",
    "JACKPOINT": "JACKPOINT is for the night after the run, when the table needs a clean recap instead of six contradictory memories.",
    "RUNSITE": "RUNSITE is for mission spaces that should feel playable before the first door opens.",
    "RUNBOOK PRESS": "RUNBOOK PRESS is for turning campaign material into something a real table can read, share, and use again.",
    "TABLE PULSE": "TABLE PULSE is for live pressure: faction opt-in reactions, bounded notifications, and aftermath without turning players into a scoreboard.",
    "BLACK LEDGER": "BLACK LEDGER is for a city that does not reset after the crew leaves the scene.",
    "COMMUNITY HUB": "COMMUNITY HUB is for finding the right table, proving the runner is ready, and closing the loop after the job.",
}

HORIZON_EPIC_INTROS: dict[str, str] = {
    "black_ledger_epic_90s": "BLACK LEDGER starts with the dead map problem: the crew makes noise, but too many campaign worlds stay frozen.",
}


@dataclass(frozen=True)
class ScenePlan:
    scene_id: str
    clip: Path
    sidecar: Path
    duration: float
    title: str
    caption: str
    narration: str
    voice: str
    treatment: str


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


def cinematic_bed_filter(target_len: float, *, mode: str) -> str:
    fade_in = min(0.8 if mode == "scene" else 1.4, max(target_len / 3.0, 0.15))
    fade_out = min(0.9 if mode == "scene" else 2.6, max(target_len / 3.0, 0.2))
    tremolo_freq = 0.24 if mode == "scene" else 0.16
    tremolo_depth = 0.11 if mode == "scene" else 0.18
    return (
        "aevalsrc="
        f"'0.030*sin(2*PI*(43+1.7*sin(2*PI*0.05*t))*t)+"
        "0.018*sin(2*PI*(86+2.4*sin(2*PI*0.037*t))*t)+"
        "0.011*sin(2*PI*129*t)+0.007*sin(2*PI*172*t)+0.004*sin(2*PI*258*t)'"
        f":s=48000:d={target_len:.3f},"
        "highpass=f=32,lowpass=f=3600,bass=g=2.8:f=94:w=0.8,"
        f"tremolo=f={tremolo_freq:.3f}:d={tremolo_depth:.3f},"
        "acompressor=threshold=-30dB:ratio=1.8:attack=30:release=280:makeup=1.5,"
        f"afade=t=in:st=0:d={fade_in:.3f},"
        f"afade=t=out:st={max(target_len - fade_out, 0):.3f}:d={fade_out:.3f},"
        "volume=1.32[bed]"
    )


def clean_id(value: str) -> str:
    value = re.sub(r"[^A-Za-z0-9_.-]+", "_", value)
    return re.sub(r"_+", "_", value).strip("_")


def clip_for(asset_id: str, scene_id: str) -> tuple[Path, Path]:
    root = CLIPS / asset_id
    candidates = [
        root / f"{scene_id}.mp4",
        root / f"{clean_id(scene_id)}.mp4",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate, candidate.with_suffix(".magicfit.json")
    normalized = clean_id(scene_id).replace("_", "").lower()
    for candidate in sorted(root.glob("*.mp4")):
        if clean_id(candidate.stem).replace("_", "").lower() == normalized:
            return candidate, candidate.with_suffix(".magicfit.json")
    raise FileNotFoundError(f"missing MagicFit clip for {asset_id}/{scene_id}")


def format_ts(seconds: float) -> str:
    total_ms = int(round(seconds * 1000))
    hours, rem = divmod(total_ms, 3600_000)
    minutes, rem = divmod(rem, 60_000)
    secs, ms = divmod(rem, 1000)
    return f"{hours:02}:{minutes:02}:{secs:02}.{ms:03}"


def write_vtt(path: Path, scenes: list[ScenePlan]) -> None:
    cursor = 0.0
    lines = ["WEBVTT", ""]
    for index, scene in enumerate(scenes, start=1):
        start = cursor
        end = cursor + scene.duration
        lines.extend([str(index), f"{format_ts(start)} --> {format_ts(end)}", scene.caption, ""])
        cursor = end
    path.write_text("\n".join(lines), encoding="utf-8")


def _scene_profile(asset_id: str, scene: ScenePlan) -> dict[str, str]:
    return load_profile(
        prefixes=(
            slug_prefix("UNMIXR_HORIZON", asset_id, scene.scene_id),
            slug_prefix("UNMIXR_HORIZON", asset_id),
            slug_prefix("UNMIXR_HORIZON", scene.title),
        ),
        defaults={"speaking_rate": "medium", "speaking_pitch": "low", "speaking_volume": "medium"},
    )


def render_narration_files(asset_id: str, scenes: list[ScenePlan], work: Path) -> tuple[list[Path], str]:
    narration_dir = work / "narration"
    narration_dir.mkdir(parents=True, exist_ok=True)
    outputs: list[Path] = []
    provider = UNMIXR_SHORT_TTS_PROVIDER
    for index, scene in enumerate(scenes, start=1):
        output = narration_dir / f"{index:02}.mp3"
        render_short_tts(scene.narration, output, profile=_scene_profile(asset_id, scene))
        outputs.append(output)
    return outputs, provider


def make_audio_segment(narration: Path, scene: ScenePlan, output: Path) -> None:
    target = scene.duration
    source = duration(narration)
    target_vo = max(target - 0.35, 1.0)
    if source > target_vo:
        speed = min(max(source / target_vo, 1.0), 1.85)
        start = f"[0:a]atempo={speed:.4f},atrim=0:{target_vo:.3f},asetpts=PTS-STARTPTS[rawvo]"
    elif source and source < target_vo * 0.94:
        stretch = max(source / target_vo, 0.88)
        start = f"[0:a]atempo={stretch:.4f},atrim=0:{target_vo:.3f},asetpts=PTS-STARTPTS[rawvo]"
    else:
        start = f"[0:a]atrim=0:{target_vo:.3f},asetpts=PTS-STARTPTS[rawvo]"
    if scene.treatment == "field_reporter":
        treatment = f"[rawvo]rubberband=pitch=0.86,afade=t=in:st=0:d=0.10,afade=t=out:st={max(target_vo - 0.28, 0):.3f}:d=0.28,highpass=f=75,lowpass=f=7200,acompressor=threshold=-18dB:ratio=3.1:attack=12:release=150:makeup=3.2,alimiter=limit=0.90[vo0]"
    else:
        treatment = f"[rawvo]afade=t=in:st=0:d=0.10,afade=t=out:st={max(target_vo - 0.28, 0):.3f}:d=0.28,highpass=f=85,lowpass=f=11200,acompressor=threshold=-20dB:ratio=2.4:attack=18:release=180:makeup=2.0,alimiter=limit=0.88[vo0]"
    filters = [
        start,
        treatment,
        cinematic_bed_filter(target, mode="scene"),
        f"[vo0]adelay=120|120,apad,atrim=0:{target:.3f},volume=1.14[vo]",
        "[bed][vo]amix=inputs=2:duration=first:dropout_transition=0,alimiter=limit=0.92[a]",
    ]
    run("ffmpeg", "-y", "-i", str(narration), "-filter_complex", ";".join(filters), "-map", "[a]", "-c:a", "pcm_s16le", str(output))


def make_video_segment(scene: ScenePlan, output: Path, scene_number: int, total_scenes: int) -> None:
    source = duration(scene.clip)
    stretch = scene.duration / source
    progress = min(99, round((scene_number / total_scenes) * 100))
    font = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf"
    vf = (
        f"scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=increase,"
        f"crop={WIDTH}:{HEIGHT},setsar=1,setpts={stretch:.8f}*PTS,"
        f"trim=duration={scene.duration:.3f},setpts=PTS-STARTPTS,fps={FPS},format=yuv420p"
    )
    if scene_number >= total_scenes - 1:
        vf += (
            f",drawbox=x=w-252:y=36:w=216:h=56:color=black@0.24:t=fill:enable='between(t,1.2,{max(scene.duration - 1.0, 0.5):.2f})'"
            f",drawtext=fontfile={font}:text='trace active':x=w-236:y=48:fontsize=16:fontcolor=76ff9f@0.72:"
            f"shadowcolor=000000@0.45:shadowx=1:shadowy=1:enable='between(t,1.2,{max(scene.duration - 1.0, 0.5):.2f})'"
            f",drawtext=fontfile={font}:text='eyes: remote':x=w-236:y=68:fontsize=13:fontcolor=d7ffe5@0.58:"
            f"shadowcolor=000000@0.35:shadowx=1:shadowy=1:enable='between(t,2.0,{max(scene.duration - 1.0, 0.5):.2f})'"
        )
    if scene_number == total_scenes:
        vf += (
            f",drawtext=fontfile={font}:text='trace lost':x=w-236:y=68:fontsize=13:fontcolor=ff6b7d@0.62:"
            f"shadowcolor=000000@0.35:shadowx=1:shadowy=1:enable='between(t,{max(scene.duration - 2.4, 0.5):.2f},{max(scene.duration - 0.7, 0.5):.2f})'"
        )
    run(
        "ffmpeg",
        "-y",
        "-i",
        str(scene.clip),
        "-an",
        "-vf",
        vf,
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


def horizon_name(asset: dict[str, Any]) -> str:
    return str(asset.get("horizon") or asset.get("title") or asset["asset_id"]).replace(" 90s Deep-Dive", "").replace(" Epic 90s", "").strip()


def build_scene_plan(asset: dict[str, Any]) -> list[ScenePlan]:
    horizon = horizon_name(asset)
    base_voice = HORIZON_VOICE.get(horizon.upper(), DOCUMENTARY_VOICE)
    scenes: list[ScenePlan] = []
    source_scenes = asset["scenes"]
    total = len(source_scenes)
    custom_narration = CUSTOM_NARRATION.get(str(asset["asset_id"]))
    for index, raw in enumerate(source_scenes, start=1):
        clip, sidecar = clip_for(asset["asset_id"], raw["id"])
        title = str(raw.get("title") or f"Scene {index}")
        on_screen = str(raw.get("on_screen_text") or title).strip()
        if custom_narration and index <= len(custom_narration):
            narration = custom_narration[index - 1]
        elif index == 1:
            narration = HORIZON_EPIC_INTROS.get(str(asset["asset_id"])) or HORIZON_INTROS.get(
                horizon.upper(),
                f"{horizon} starts with one table problem and follows it until the next move is obvious.",
            )
        elif index == total - 1:
            narration = "We have a developing situation. Field report says the crew found the pressure point, the room got loud, and the job just became tomorrow's problem."
        elif index == total:
            narration = f"{horizon} keeps the crew in motion, so the next scene starts before the heat has time to cool."
        else:
            narration = f"{title}. Show the useful part, keep the GM in control, and get the table back to the scene."
        treatment = "field_reporter" if index == total - 1 else "trailer"
        voice = DOCUMENTARY_VOICE if treatment == "field_reporter" else base_voice
        scenes.append(
            ScenePlan(
                scene_id=str(raw["id"]),
                clip=clip,
                sidecar=sidecar,
                duration=float(raw.get("duration_seconds") or 9),
                title=title,
                caption=on_screen or title,
                narration=narration,
                voice=voice,
                treatment=treatment,
            )
        )
    return scenes


def compose_asset(asset: dict[str, Any]) -> dict[str, Any]:
    asset_id = asset["asset_id"]
    work = OUT / asset_id
    segments = work / "segments"
    segments.mkdir(parents=True, exist_ok=True)
    output = OUT / "videos" / f"{asset_id}.mp4"
    webm = OUT / "videos" / f"{asset_id}.webm"
    vtt = OUT / "videos" / f"{asset_id}.vtt"
    poster = OUT / "videos" / f"{asset_id}-poster.png"
    output.parent.mkdir(parents=True, exist_ok=True)
    scenes = build_scene_plan(asset)
    for scene in scenes:
        if not scene.clip.is_file() or not scene.sidecar.is_file():
            raise SystemExit(f"missing MagicFit clip/sidecar for {asset_id}/{scene.scene_id}")
    narration_files, narration_provider = render_narration_files(asset_id, scenes, work)
    video_segments: list[Path] = []
    audio_segments: list[Path] = []
    for index, scene in enumerate(scenes, start=1):
        video_segment = segments / f"{index:02}.video.mp4"
        audio_segment = segments / f"{index:02}.audio.wav"
        make_video_segment(scene, video_segment, index, len(scenes))
        make_audio_segment(narration_files[index - 1], scene, audio_segment)
        video_segments.append(video_segment)
        audio_segments.append(audio_segment)
    concat_video = work / "video_segments.txt"
    concat_audio = work / "audio_segments.txt"
    concat_video.write_text("".join(f"file '{path}'\n" for path in video_segments), encoding="utf-8")
    concat_audio.write_text("".join(f"file '{path}'\n" for path in audio_segments), encoding="utf-8")
    joined_video = work / "joined-video.mp4"
    joined_audio = work / "joined-audio.wav"
    run("ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_video), "-c", "copy", str(joined_video))
    run("ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_audio), "-c:a", "pcm_s16le", str(joined_audio))
    target_duration = sum(scene.duration for scene in scenes)
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
        f"{target_duration:.3f}",
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
    run("ffmpeg", "-y", "-i", str(output), "-c:v", "libvpx-vp9", "-deadline", "realtime", "-cpu-used", "5", "-row-mt", "1", "-crf", "34", "-b:v", "0", "-c:a", "libopus", "-b:a", "112k", str(webm))
    run("ffmpeg", "-y", "-i", str(output), "-ss", "00:00:08", "-frames:v", "1", "-update", "1", str(poster))
    write_vtt(vtt, scenes)
    receipt = {
        "generated_at_utc": utc_now(),
        "status": "published_completion",
        "asset_id": asset_id,
        "title": asset["title"],
        "horizon": horizon_name(asset),
        "source_magicfit_scene_count": len(scenes),
        "render_mode": "magicfit_clip_composite_with_flagship_meta_game_voiceover",
        "narration_provider": narration_provider,
        "field_reporter_voice": "en-GB-ThomasNeural with lower ork-news processing",
        "meta_game_overlay": ["subtle trace status", "remote eyes indicator", "trace lost indicator"],
        "mp4_probe": probe(output),
        "public_safe_boundary": "No official Shadowrun logos, sourcebook pages, canonical characters, or provider-direct publishing.",
        "files": {
            "mp4": str(output),
            "webm": str(webm),
            "poster": str(poster),
            "captions": str(vtt),
        },
        "scenes": [
            {
                "scene_id": scene.scene_id,
                "clip": str(scene.clip),
                "sidecar": str(scene.sidecar),
                "duration_seconds": scene.duration,
                "caption": scene.caption,
                "narration": scene.narration,
                "voice": scene.voice,
                "voice_treatment": scene.treatment,
            }
            for scene in scenes
        ],
    }
    (OUT / f"{asset_id}.receipt.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    return receipt


def write_audit(manifest: dict[str, Any], selected: list[dict[str, Any]], receipts: list[dict[str, Any]]) -> None:
    inventory = []
    for asset in selected:
        clips = list((CLIPS / asset["asset_id"]).glob("*.mp4"))
        sidecars = list((CLIPS / asset["asset_id"]).glob("*.magicfit.json"))
        inventory.append(
            {
                "asset_id": asset["asset_id"],
                "title": asset["title"],
                "horizon": horizon_name(asset),
                "planned_scene_count": len(asset["scenes"]),
                "magicfit_mp4_count": len(clips),
                "magicfit_sidecar_count": len(sidecars),
                "ready_for_flagship_composite": len(clips) == len(asset["scenes"]) and len(sidecars) == len(asset["scenes"]),
            }
        )
    audit = {
        "generated_at_utc": utc_now(),
        "status": "pass" if all(item["ready_for_flagship_composite"] for item in inventory) else "fail",
        "source_manifest": str(MANIFEST),
        "asset_count": len(selected),
        "inventory": inventory,
        "composited_receipts": [str(OUT / f"{receipt['asset_id']}.receipt.json") for receipt in receipts],
        "verdict": "HORIZON_FLAGSHIP_REELS_READY" if receipts and all(item["ready_for_flagship_composite"] for item in inventory) else "NOT_READY",
    }
    (OUT / "HORIZON_FLAGSHIP_REELS_AUDIT.generated.json").write_text(json.dumps(audit, indent=2) + "\n", encoding="utf-8")
    review = [
        "# Horizon Flagship Reel Creative Review",
        "",
        "Each Horizon reel now uses the same public-safe flagship grammar:",
        "- MagicFit source clips only, verified by per-scene sidecars.",
        "- Roleplaying-table language instead of internal proof/audit language.",
        "- A short ork/field-reporter beat near the end.",
        "- A visible meta-game AR layer: HACKING IN PROGRESS, DISPATCHING EYES, OWN EYES DESTROYED, TRACE BURNED 100%.",
        "- Captions and exact text are added in post so generated footage is not trusted for spelling.",
        "",
        "Residual risk: lip-sync is only approximate because the reporter voice is added in post over MagicFit video; strongest alignment is on scenes whose source clip already shows a speaking reporter or anchor.",
    ]
    (OUT / "HORIZON_FLAGSHIP_REELS_HUMAN_REVIEW.md").write_text("\n".join(review) + "\n", encoding="utf-8")


def main() -> int:
    global MANIFEST, CLIPS, OUT
    parser = argparse.ArgumentParser(description="Compose flagship-quality Horizon reels from rendered MagicFit clips.")
    parser.add_argument("--all", action="store_true", help="Compose all assets in the refined manifest.")
    parser.add_argument("--asset", action="append", default=[], help="Compose one asset id; may be repeated.")
    parser.add_argument("--manifest", default=str(MANIFEST), help="Render manifest JSON to compose.")
    parser.add_argument("--clips-root", default=str(CLIPS), help="Root directory containing MagicFit clips by asset id.")
    parser.add_argument("--out-root", default=str(OUT), help="Output root for composited reels.")
    args = parser.parse_args()
    MANIFEST = Path(args.manifest)
    CLIPS = Path(args.clips_root)
    OUT = Path(args.out_root)
    OUT.mkdir(parents=True, exist_ok=True)
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    selected_ids = {item for item in args.asset if item}
    if args.all:
        selected = list(manifest["assets"])
    elif selected_ids:
        selected = [asset for asset in manifest["assets"] if asset["asset_id"] in selected_ids]
    else:
        selected = [asset for asset in manifest["assets"] if asset["asset_id"] in {"black_ledger_epic_90s", "nexus-pan_epic_90s"}]
    receipts = [compose_asset(asset) for asset in selected]
    write_audit(manifest, selected, receipts)
    print("HORIZON_FLAGSHIP_REELS_READY")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

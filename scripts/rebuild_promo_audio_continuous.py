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
REPO = WORKSPACE / "chummer.run-services"
PUBLIC = REPO / "Chummer.Run.Api" / "wwwroot" / "media" / "promo"
HORIZON_VIDEOS = WORKSPACE / "_completion" / "horizon_flagship_reels_20260602" / "videos"
OUT = WORKSPACE / "_completion" / "promo_audio_continuous_20260602"
TTS_PYTHON = WORKSPACE / "_completion" / "promo_video_rework_20260602" / "tts_venv" / "bin" / "python"


@dataclass(frozen=True)
class AudioPlan:
    asset_id: str
    video: Path
    title: str
    script: str
    voice: str = "en-US-GuyNeural"


SCRIPTS: dict[str, str] = {
    "chummer6-flagship-promo": (
        "Every table knows the old problem. The run is ready, but the tools are scattered. "
        "One sheet lives on a laptop, one note hides in chat, and the GM is still hunting for the thing that should already be on screen. "
        "Chummer6 brings the campaign back to the table. Build the runner with gear, magic, cyberware, contacts, and consequences in view. "
        "When a number changes, the table can understand why. When the city reacts, the GM has pressure they can actually play. "
        "Prep becomes scenes, NPCs, handouts, downtime, and hooks in one place. Remote players can stay part of the moment without dragging the room off course. "
        "House rules can be tried, understood, and rolled back before they become folklore. And when the aftermath hits the newsroom, it becomes fuel for the next job. "
        "Desktop, tablet, phone, home table, remote night. Chummer6 is for crews who want the next run ready before the heat cools."
    ),
    "all-horizons-90s-magicfit-promo": (
        "The Horizons are future lanes for the same table problem: campaigns get bigger than the tools holding them. "
        "NEXUS-PAN keeps players connected when devices drift. ALICE helps a runner idea become a build that can survive play. "
        "KARMA FORGE gives house rules a shape the table can trust. JACKPOINT turns the run into recaps, dossiers, and briefings that feel alive. "
        "RUNSITE makes mission spaces readable before the first door opens. RUNBOOK PRESS turns campaign material into books and handoffs that last. "
        "TABLE PULSE keeps heat and reactions bounded, useful, and under GM control. BLACK LEDGER lets the city remember what the crew did. "
        "COMMUNITY HUB helps the right players find the right run and close the loop afterward. "
        "Nine Horizons, one direction: less tool noise, more table momentum, and a campaign that is easier to carry into the next session."
    ),
    "every-wonder-horizon-promo": (
        "Every Wonder Horizon is about growth without losing the table. "
        "A campaign can stretch across devices, sessions, players, handouts, recaps, locations, and living-world consequences. "
        "That growth should feel exciting, not fragile. The player who reconnects should know where the scene is. "
        "The GM should see what changed, what is private, and what can be shared. A house rule should be understood before it lands. "
        "A mission site should be playable before it becomes dangerous. A recap should bring the crew back into the story instead of burying them in notes. "
        "The city should move after the run, and the community should help the next table form cleanly. "
        "Every Wonder is the larger promise: let the campaign expand, while the people, scenes, and choices that made it matter stay close enough to play."
    ),
    "nexus_pan_90s_deepdive": (
        "The session starts clean, then the real world hits. A tablet drops, a laptop wakes from sleep, a remote player reconnects, and suddenly the table needs to know which state is current. "
        "NEXUS-PAN is about continuity under pressure. It should be obvious who is present, what changed, and where the player returns. "
        "A reconnect should not become a rules debate. A conflict should be visible before it becomes table folklore. "
        "Desktop for heavy work, tablet at the table, phone on the move: same campaign, same moment, no scavenger hunt. "
        "Bad signal should be honest. Recovery should be calm. For the GM, the question is simple: can I trust what I am seeing right now. "
        "For the player, the best version is almost boring. Rejoin, catch up, answer the scene, keep playing. "
        "NEXUS-PAN is the crew keeping the thread even when one device blinks first."
    ),
    "nexus-pan_epic_90s": (
        "Every campaign has a split-screen moment. One player is remote, one sheet is stale, the GM has too many windows open, and the clock is still running. "
        "NEXUS-PAN starts with trust. Who is connected. What changed. What is safe to act on. "
        "Packets move, devices disagree, and the table does not need drama from the tools. It needs a clean signal and a clear next step. "
        "When conflict appears, show it with context and let the GM decide before the scene breaks. "
        "The campaign should move with the crew from desk to tablet to train to home table, without exporting, copying, and hoping. "
        "The returning player gets the humane version: here is where you left, here is what changed, here is the move on the table. "
        "Less ceremony. Less panic. More run."
    ),
    "alice_90s_deepdive": (
        "A flashy runner is easy to imagine and hard to survive. ALICE starts where the character concept meets the table. "
        "The question is not which build looks coolest. It is which one can do the job, carry the cost, and still feel like the character the player wanted. "
        "The numbers should tell a story: what got stronger, what became fragile, and what was quietly traded away. "
        "Gear is never just a shopping list. Magic and chrome both ask for choices. Role fit matters before the first bad roll exposes the gap. "
        "ALICE should feel like a coach beside the player, not a judge above them. "
        "By the end, the runner still belongs to the player, but the table can see why the build works and where it needs care."
    ),
    "karma_forge_90s_deepdive": (
        "Every table has house rules. The problem is remembering which ones are real, which ones were jokes, and which ones quietly broke the campaign. "
        "KARMA FORGE treats a rule change like something worth handling carefully. Name it, scope it, preview it, and show who it affects. "
        "Before the table says yes, the GM sees the blast radius. Players can react in context instead of digging through old chat arguments. "
        "A good rule earns trust by showing its work. A bad rule needs an exit before it becomes tradition. "
        "Campaigns evolve, and the rules can evolve with them, without turning into a private fork nobody understands. "
        "KARMA FORGE is for custom play without rule chaos."
    ),
    "jackpoint_90s_deepdive": (
        "The run is over. The table is tired, laughing, and already remembering three different versions of what happened. "
        "JACKPOINT gives the aftermath a place to live. Recaps, dossiers, briefings, loose ends, NPC promises, and the details players are allowed to see. "
        "Player-facing knowledge and GM-only context need different doors. A briefing should sound like the world, not like a database export. "
        "A missed player should return to a clean handoff instead of a twenty-minute oral history. "
        "As the campaign gets long, JACKPOINT keeps memory from dissolving into vibes and old screenshots. "
        "The table still owns the story. This just gives the story a sharper way to come back next session."
    ),
    "runsite_90s_deepdive": (
        "A bad map makes a good mission feel smaller. RUNSITE is for spaces that should be dangerous, readable, and worth exploring. "
        "The site opens in layers: floor plan, approach, cameras, entrances, exits, hidden doors, astral traces, and the places players will immediately try to break. "
        "Player view stays clean while GM view keeps the secrets behind the curtain. "
        "Hotspots help prep the moments that matter without scripting the route. "
        "The crew can scout, argue, and plan around a place instead of a paragraph. "
        "If they go loud, the site answers. If they go quiet, the same space still has texture. "
        "RUNSITE makes locations matter before the first door opens."
    ),
    "runbook_press_90s_deepdive": (
        "Campaign material piles up fast: notes, districts, NPCs, rulings, handouts, recaps, and lore all drifting into separate corners. "
        "RUNBOOK PRESS turns that pile into something the table can read again. "
        "A season guide needs shape. What can players know. What must stay with the GM. What belongs in the appendix. "
        "The same campaign can become a primer, a district brief, a mission packet, or a full handoff. "
        "Layout is not decoration. It is how a busy GM finds the right page five minutes before the session starts. "
        "When a new player joins, the book gets them oriented. When the campaign ends, the table has an artifact that feels earned."
    ),
    "table_pulse_90s_deepdive": (
        "Some pressure belongs at the table. Some pressure belongs after the table. TABLE PULSE exists to keep that boundary clear. "
        "Heat should feel alive without turning players into a scoreboard. The GM sees the signal, chooses the packet, and decides whether the scene needs a nudge or needs silence. "
        "Remote players can answer the moment without hijacking the room. Consent, quiet hours, opt-outs, and table policy decide what the system is allowed to do. "
        "After the session, the useful packet is private: what hit, what dragged, what needs care, and what the GM might try next time. "
        "A good pulse is felt in play and barely noticed as software."
    ),
    "black_ledger_90s_deepdive": (
        "Too many campaign cities reset overnight. BLACK LEDGER is for the kind of city that remembers who kicked the door in. "
        "After the run, districts shift, pressure moves, and the next job starts forming in the fallout. "
        "A world tick should feel like consequence, not homework. Open jobs grow out of heat, favors, failures, rumors, and people who now want something. "
        "Faction pressure works best when it creates choices, not a wall of lore. "
        "Newsroom beats give the city a voice: dramatic, biased, funny, and useful enough to become tomorrow's hook. "
        "By the time the next session starts, the city already has opinions."
    ),
    "community_hub_90s_deepdive": (
        "Finding a table should not feel harder than surviving the run. COMMUNITY HUB starts with the lonely player and the overworked GM. "
        "Open runs need more than a signup button. They need tone, rules, schedule, safety, and a reason the character fits. "
        "Runner preflight catches problems before everyone is waiting in voice chat. "
        "A roster is not just names; it is roles, availability, expectations, and whether this crew can actually play together. "
        "Scheduling should reduce friction, and the session handoff should keep the campaign loop intact. "
        "The best outcome is simple: the right people find the right run, and the campaign remembers the result."
    ),
    "black_ledger_epic_90s": (
        "BLACK LEDGER starts with the dead map problem. The crew makes noise, but too many campaign worlds stay frozen. "
        "In the epic version, the city wakes up like another character at the table. "
        "World ticks turn fallout into motion: a quiet district gets hot, a safe route becomes risky, a favor becomes a job. "
        "The mission market feels earned because the next opportunity grows from what the crew actually did. "
        "Faction pressure creates tension the GM can play, not encyclopedia entries players must memorize. "
        "The newsroom gives the city attitude: rumors, spin, panic, jokes, and half-truths runners know how to exploit. "
        "BLACK LEDGER is for GMs who want the city to push back and players who want their mess to matter."
    ),
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


async def render_edge_tts(text: str, voice: str, output: Path) -> bool:
    if not TTS_PYTHON.is_file():
        return False
    helper = OUT / "render_edge_tts_continuous.py"
    helper.write_text(
        "import asyncio, edge_tts, pathlib, sys\n"
        "async def main():\n"
        "    voice, text, output = sys.argv[1], sys.argv[2], pathlib.Path(sys.argv[3])\n"
        "    communicate = edge_tts.Communicate(text=text, voice=voice, rate='-14%', pitch='-2Hz')\n"
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


def audio_filter_for(narration: Path, target_duration: float) -> str:
    source_duration = duration(narration)
    target_vo = max(target_duration - 3.6, 1.0)
    if source_duration > target_vo:
        tempo = min(max(source_duration / target_vo, 1.0), 1.18)
        prep = f"atempo={tempo:.5f},atrim=0:{target_vo:.3f},asetpts=PTS-STARTPTS"
        fit_mode = f"sped_up_{tempo:.3f}"
    else:
        prep = f"atrim=0:{target_vo:.3f},asetpts=PTS-STARTPTS"
        fit_mode = "natural_slow"
    return (
        f"[0:a]{prep},afade=t=in:st=0:d=0.45,afade=t=out:st={max(target_vo - 0.75, 0):.3f}:d=0.75,"
        "highpass=f=78,lowpass=f=9800,bass=g=1.7:f=118:w=0.55,"
        "acompressor=threshold=-21dB:ratio=2.2:attack=22:release=260:makeup=2.0,alimiter=limit=0.88[vo0];"
        f"[vo0]adelay=1200|1200,apad,atrim=0:{target_duration:.3f},volume=1.12[vo];"
        "aevalsrc='0.010*sin(2*PI*42*t)+0.006*sin(2*PI*84*t)+0.003*sin(2*PI*168*t)'"
        f":s=48000:d={target_duration:.3f},afade=t=in:st=0:d=1.2,afade=t=out:st={max(target_duration - 1.4, 0):.3f}:d=1.4[bed];"
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
        AudioPlan(asset, PUBLIC / f"{asset}.mp4", title, SCRIPTS[asset])
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
        items.append(AudioPlan(asset, HORIZON_VIDEOS / f"{asset}.mp4", f"{asset} v3 Continuous Audio", SCRIPTS[asset]))
    if selected:
        items = [item for item in items if item.asset_id in selected]
    return items


def rebuild(plan: AudioPlan) -> dict[str, Any]:
    if not plan.video.exists():
        raise SystemExit(f"missing video: {plan.video}")
    work = OUT / plan.asset_id
    work.mkdir(parents=True, exist_ok=True)
    target_duration = duration(plan.video)
    tts = work / "continuous-narration.mp3"
    ok = asyncio.run(render_edge_tts(plan.script, plan.voice, tts))
    provider = "edge-tts-continuous"
    if not ok:
        tts = work / "continuous-narration.wav"
        render_fallback_tts(plan.script, tts)
        provider = "ffmpeg-flite-continuous"
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
        "audio_mode": "single_continuous_slow_narration_track",
        "narration_provider": provider,
        "voice": plan.voice,
        "no_scene_audio_cuts": True,
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

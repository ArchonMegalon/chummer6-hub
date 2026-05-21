#!/usr/bin/env python3
from __future__ import annotations

import subprocess
from pathlib import Path


ROOT = Path("/docker/chummercomplete/chummer.run-services/Chummer.Run.Api/wwwroot/media/ledger/factions")
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
FACTIONS = [
    {
        "slug": "ashline-circle",
        "title": "Ashline Circle",
        "primary": "#f09b4c",
        "secondary": "#6b1828",
        "recruitment": "ENTER THE CIRCLE. COMMAND THE ASH.",
        "doctrine": "Ritual supremacy with audited spectacle.",
        "threat": "Arc-fire pressure fronts across ritual wards.",
        "final_order": "REPORT FOR CONSECRATED SERVICE.",
        "territory": "TERRITORY MASK // ASHLINE CRESCENT",
        "control": "CONTROL MODEL // WITNESSED FIRE, GUARANTEED COMPLIANCE",
        "risk": "FAILURE CASE // UNBLESSED CHAOS SPREADS IN PUBLIC",
        "captions": [
            "Power is ordinary. Certified supremacy is the offer.",
            "Ritual fire, gold seal, and disciplined witnesses make the district kneel on cue.",
            "Your oath still answers to the public world tick. That is the flex.",
        ],
    },
    {
        "slug": "barrens-free-wardens",
        "title": "Barrens Free Wardens",
        "primary": "#c2d279",
        "secondary": "#284033",
        "recruitment": "HOLD THE LINE. MAKE THE STREETS OBEY.",
        "doctrine": "Civil defense sold like a military franchise.",
        "threat": "Attrition spirals break any district without convoy steel.",
        "final_order": "ENLIST BEFORE THE LIGHTS GO OUT.",
        "territory": "TERRITORY MASK // WARDEN FLOODWALL CORRIDOR",
        "control": "CONTROL MODEL // FLOODLIGHTS, CONVOYS, PERIMETER FAITH",
        "risk": "FAILURE CASE // THE BLOCK LOSES POWER BEFORE HOPE",
        "captions": [
            "This is not a briefing. It is the order that keeps the district alive.",
            "Floodlights, convoy steel, and stubborn mutual defense turn panic into allegiance.",
            "Protection only counts when the ledger can prove who stood their ground.",
        ],
    },
    {
        "slug": "ghostline-network",
        "title": "Ghostline Network",
        "primary": "#91fff2",
        "secondary": "#0d2333",
        "recruitment": "OWN THE SIGNAL BEFORE THE SIGNAL OWNS YOU.",
        "doctrine": "Narrative control enforced by verified intelligence.",
        "threat": "Signal corruption spreads faster than panic can confess.",
        "final_order": "SEIZE THE CHANNEL. LEAVE NO STATIC.",
        "territory": "TERRITORY MASK // GHOSTLINE SHADOW BAND",
        "control": "CONTROL MODEL // VERIFIED NARRATIVE, COLLAPSED FALSEHOOD",
        "risk": "FAILURE CASE // STATIC BREEDS AN UNCONTESTED LIE",
        "captions": [
            "Rumor is for civilians. Verified narrative is for operators.",
            "The screen glitches, the lie evaporates, and the faction keeps the broadcast crown.",
            "Pressure is public. Secrets remain buried. Control both and you win the city.",
        ],
    },
    {
        "slug": "glass-tower-compact",
        "title": "Glass Tower Compact",
        "primary": "#8ed7ff",
        "secondary": "#1d2f63",
        "recruitment": "ASCEND. OWN THE SKYLINE. DICTATE CALM.",
        "doctrine": "Executive order wrapped in pristine aerial prestige.",
        "threat": "Panic climbs vertically when elite infrastructure blinks.",
        "final_order": "BOARD NOW. RULE FROM ABOVE.",
        "territory": "TERRITORY MASK // GLASS TOWER AERIAL ARC",
        "control": "CONTROL MODEL // SKY-BRIDGES, PREMIUM SHIELD, SILENT PANIC",
        "risk": "FAILURE CASE // THE ELITE FLOOR GOES DARK FIRST",
        "captions": [
            "Security this polished is a recruitment weapon.",
            "Sky-bridges, white-glove retainers, and airborne contracts sell authority before the words land.",
            "Prestige is only real if the next turn can measure the panic you prevented.",
        ],
    },
    {
        "slug": "neon-docks-union",
        "title": "Neon Docks Union",
        "primary": "#72f0ff",
        "secondary": "#0f5160",
        "recruitment": "MOVE THE CITY OR WATCH IT CHOKE.",
        "doctrine": "Freight discipline staged like maritime conquest.",
        "threat": "Every stalled lane becomes a televised oxygen shortage.",
        "final_order": "REPORT TO THE DOCKMASTER OF HISTORY.",
        "territory": "TERRITORY MASK // NEON CHANNEL FREIGHT VEIN",
        "control": "CONTROL MODEL // THROUGHPUT, GANTRY LAW, PORT SUPREMACY",
        "risk": "FAILURE CASE // THE CITY DROWNS IN ITS OWN INVENTORY",
        "captions": [
            "The port is the heartbeat. We decide who gets oxygen.",
            "Cargo towers, cyan beacons, and steel gantries turn logistics into a parade of dominance.",
            "Throughput is not a slogan when the board can watch the pressure move in real time.",
        ],
    },
    {
        "slug": "rust-market-syndicate",
        "title": "Rust Market Syndicate",
        "primary": "#ffb05b",
        "secondary": "#5b2711",
        "recruitment": "BUY IN. TAKE GROUND. OWN THE NIGHT SHIFT.",
        "doctrine": "Acquisition pressure disguised as neighborhood gravity.",
        "threat": "Every idle crate becomes a public leverage point.",
        "final_order": "CLOCK IN. COLLECT THE DISTRICT.",
        "territory": "TERRITORY MASK // RUST EXCHANGE NIGHT GRID",
        "control": "CONTROL MODEL // CREDIT, FREIGHT, WITNESS ACQUISITION",
        "risk": "FAILURE CASE // THE MARKET GOES HUNGRY IN PUBLIC",
        "captions": [
            "Every crate is inventory. Every witness is a customer in waiting.",
            "Debt-orange light, stacked freight, and market thunder make the whole block feel purchasable.",
            "Even this bravado still answers to the turn packet. That is how you know it is real.",
        ],
    },
]


def esc(text: str) -> str:
    return text.replace("\\", "\\\\").replace(":", r"\:").replace("'", r"\'").replace(",", r"\,")


def ffmpeg_color(value: str) -> str:
    return f"0x{value.lstrip('#')}"


def drawtext(text: str, *, size: int, x: str, y: str, color: str, enable: str | None = None, alpha: str | None = None) -> str:
    parts = [
        f"drawtext=fontfile={FONT}",
        f"text='{esc(text)}'",
        f"fontsize={size}",
        f"fontcolor={color}",
        f"x={x}",
        f"y={y}",
        "line_spacing=10",
        "shadowcolor=black@0.65",
        "shadowx=2",
        "shadowy=2",
    ]
    if enable:
        parts.append(f"enable='{enable}'")
    if alpha:
        parts.append(f"alpha={alpha}")
    return ":".join(parts)


def build_filter(
    title: str,
    recruitment: str,
    doctrine: str,
    threat: str,
    final_order: str,
    territory: str,
    control: str,
    risk: str,
    captions: list[str],
    primary: str,
    secondary: str,
) -> str:
    primary_color = ffmpeg_color(primary)
    secondary_color = ffmpeg_color(secondary)
    segments = [
        "[0:v]scale=1920:1080,setsar=1,format=rgba,"
        "zoompan=z='min(1.16,1+0.0012*on)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=450:s=1920x1080:fps=30,"
        "eq=saturation=1.18:contrast=1.12:brightness=0.02[bg]",
        "[1:v]scale=320:-1[logo]",
        "[1:v]scale=170:-1[seal]",
        f"[bg]drawbox=x=70:y=56:w=1780:h=952:color=black@0.20:t=fill,"
        f"drawbox=x=70:y=56:w=1780:h=952:color={primary_color}@0.16:t=3,"
        f"drawbox=x='120+mod(t*340,1330)':y=912:w=420:h=14:color={secondary_color}@0.92:t=fill,"
        f"drawbox=x='1460-mod(t*250,1010)':y=946:w=320:h=10:color={primary_color}@0.78:t=fill,"
        f"drawbox=x='210+mod(t*160,1460)':y=182:w=180:h=6:color={primary_color}@0.50:t=fill,"
        f"drawbox=x='190+mod(t*280,1380)':y=228:w=120:h=4:color={secondary_color}@0.44:t=fill,"
        f"drawbox=x='1700-mod(t*260,1240)':y=246:w=170:h=4:color={primary_color}@0.40:t=fill,"
        f"drawbox=x=1388:y=120:w=360:h=772:color=black@0.26:t=fill:enable='between(t,3.5,9.5)',"
        f"drawbox=x=1388:y=120:w=360:h=772:color={secondary_color}@0.18:t=2:enable='between(t,3.5,9.5)',"
        f"drawbox=x='80+mod(t*620,1840)':y=0:w=14:h=1080:color=white@0.05:t=fill,"
        f"drawbox=x='-220+mod(t*380,2200)':y=520:w=520:h=2:color={primary_color}@0.28:t=fill[stage]",
        "[stage][logo]overlay=x=110:y=102[tmp1]",
        "[tmp1][seal]overlay=x='1670+24*sin(t*2.2)':y='90+8*sin(t*3.1)'[composed]",
    ]
    chain = "[composed]"
    chain += drawtext(title, size=82, x="456", y="110", color="white")
    chain += "," + drawtext("RECRUITMENT BROADCAST // PUBLIC LEDGER SIGNAL", size=26, x="460", y="202", color=primary_color)
    chain += "," + drawtext("TURN 1 PRESSURE VECTOR // BOARD VISIBLE", size=24, x="148", y="888", color="white", enable="between(t,0,12)")
    chain += f",drawbox=x=104:y=280:w=1280:h=84:color=black@0.46:t=fill:enable='between(t,0,3.6)'"
    chain += f",drawbox=x=104:y=280:w=1280:h=84:color={primary_color}@0.30:t=3:enable='between(t,0,3.6)'"
    chain += "," + drawtext(recruitment, size=46, x="128", y="302", color=primary_color, enable="between(t,0,3.6)")
    chain += f",drawbox=x=108:y=632:w=1220:h=198:color=black@0.40:t=fill:enable='between(t,0,3.6)'"
    chain += f",drawbox=x=108:y=632:w=1220:h=198:color={secondary_color}@0.18:t=2:enable='between(t,0,3.6)'"
    chain += "," + drawtext("DISTRICT DOMINANCE WINDOW", size=28, x="124", y="586", color=secondary_color, enable="between(t,0,3.6)")
    chain += "," + drawtext(captions[0], size=46, x="130", y="686", color="white", enable="between(t,0,3.6)")
    chain += f",drawbox=x=1404:y=188:w=296:h=124:color=black@0.44:t=fill:enable='between(t,3.5,6.6)'"
    chain += f",drawbox=x=1404:y=188:w=296:h=124:color={primary_color}@0.24:t=2:enable='between(t,3.5,6.6)'"
    chain += "," + drawtext("THREAT INDEX", size=22, x="1430", y="212", color=primary_color, enable="between(t,3.5,6.6)")
    chain += "," + drawtext(threat, size=25, x="1430", y="252", color="white", enable="between(t,3.5,6.6)")
    chain += f",drawbox=x=120:y=420:w=1240:h=158:color=black@0.44:t=fill:enable='between(t,3.5,6.6)'"
    chain += f",drawbox=x=120:y=420:w=1240:h=158:color={secondary_color}@0.18:t=2:enable='between(t,3.5,6.6)'"
    chain += "," + drawtext("RECRUITMENT SHOCKWAVE", size=28, x="144", y="444", color=secondary_color, enable="between(t,3.5,6.6)")
    chain += "," + drawtext(captions[1], size=42, x="148", y="500", color="white", enable="between(t,3.5,6.6)")
    chain += f",drawbox=x=1404:y=356:w=296:h=182:color=black@0.44:t=fill:enable='between(t,3.5,6.6)'"
    chain += f",drawbox=x=1404:y=356:w=296:h=182:color={primary_color}@0.24:t=2:enable='between(t,3.5,6.6)'"
    chain += "," + drawtext("DOCTRINE", size=22, x="1430", y="380", color=primary_color, enable="between(t,3.5,6.6)")
    chain += "," + drawtext(doctrine, size=25, x="1430", y="420", color="white", enable="between(t,3.5,6.6)")
    chain += f",drawbox=x=119:y=378:w=1242:h=18:color={primary_color}@0.55:t=fill:enable='between(t,3.5,6.6)'"
    chain += f",drawbox=x='160+mod(t*150,1030)':y=378:w=160:h=18:color=white@0.32:t=fill:enable='between(t,3.5,6.6)'"
    chain += f",drawbox=x=1404:y=580:w=296:h=212:color=black@0.44:t=fill:enable='between(t,6.5,9.6)'"
    chain += f",drawbox=x=1404:y=580:w=296:h=212:color={primary_color}@0.24:t=2:enable='between(t,6.5,9.6)'"
    chain += "," + drawtext("WORLD TICK", size=22, x="1430", y="606", color=primary_color, enable="between(t,6.5,9.6)")
    chain += "," + drawtext("PRESSURE LIVE", size=32, x="1430", y="648", color="white", enable="between(t,6.5,9.6)")
    chain += "," + drawtext("PROOF REQUIRED", size=32, x="1430", y="696", color="white", enable="between(t,6.5,9.6)")
    chain += f",drawbox=x=120:y=632:w=1220:h=184:color=black@0.40:t=fill:enable='between(t,6.5,9.6)'"
    chain += f",drawbox=x=120:y=632:w=1220:h=184:color={secondary_color}@0.18:t=2:enable='between(t,6.5,9.6)'"
    chain += "," + drawtext("PROOF OR HUMILIATION", size=28, x="144", y="590", color=secondary_color, enable="between(t,6.5,9.6)")
    chain += "," + drawtext(captions[2], size=42, x="148", y="686", color="white", enable="between(t,6.5,9.6)")
    chain += "," + drawtext(territory, size=24, x="148", y="748", color=primary_color, enable="between(t,6.5,9.6)")
    chain += "," + drawtext(control, size=24, x="148", y="782", color="white", enable="between(t,6.5,9.6)")
    chain += f",drawbox=x=188:y=610:w=18:h=150:color={primary_color}@0.66:t=fill:enable='between(t,6.5,9.6)'"
    chain += f",drawbox=x=188:y=610:w=260:h=18:color={primary_color}@0.66:t=fill:enable='between(t,6.5,9.6)'"
    chain += f",drawbox=x=430:y=730:w=18:h=70:color={primary_color}@0.66:t=fill:enable='between(t,6.5,9.6)'"
    chain += f",drawbox=x=430:y=730:w=250:h=18:color={primary_color}@0.66:t=fill:enable='between(t,6.5,9.6)'"
    chain += f",drawbox=x=662:y=646:w=18:h=112:color={primary_color}@0.66:t=fill:enable='between(t,6.5,9.6)'"
    chain += f",drawbox=x=662:y=646:w=310:h=18:color={primary_color}@0.66:t=fill:enable='between(t,6.5,9.6)'"
    chain += f",drawbox=x=954:y=700:w=18:h=94:color={secondary_color}@0.76:t=fill:enable='between(t,6.5,9.6)'"
    chain += f",drawbox=x=954:y=700:w=240:h=18:color={secondary_color}@0.76:t=fill:enable='between(t,6.5,9.6)'"
    chain += f",drawbox=x=120:y=792:w=1600:h=132:color=black@0.52:t=fill:enable='between(t,9.5,12)'"
    chain += f",drawbox=x=120:y=792:w=1600:h=132:color={primary_color}@0.26:t=3:enable='between(t,9.5,12)'"
    chain += "," + drawtext(final_order, size=52, x="150", y="824", color=primary_color, enable="between(t,9.5,12)")
    chain += "," + drawtext("WATCH THE BOARD MOVE // CLAIM THE DISTRICT", size=30, x="154", y="882", color="white", enable="between(t,9.5,12)")
    chain += "," + drawtext(risk, size=22, x="1060", y="882", color="white", enable="between(t,9.5,12)")
    chain += f",drawbox=x=1040:y=848:w=30:h=30:color={primary_color}@0.80:t=fill:enable='between(t,9.5,12)'"
    chain += f",drawbox=x=1048:y=856:w=14:h=14:color=white@0.92:t=fill:enable='between(t,9.5,12)'"
    chain += f",drawbox=x='132+mod(t*360,1260)':y=946:w=240:h=8:color={primary_color}@0.92:t=fill"
    chain += f",drawbox=x='1620-mod(t*320,1120)':y=964:w=200:h=6:color={secondary_color}@0.82:t=fill"
    chain += f",drawbox=x=0:y=0:w=1920:h=1080:color=white@0.16:t=fill:enable='between(t,3.45,3.58)+between(t,6.45,6.58)+between(t,9.45,9.58)'"
    chain += f",drawbox=x=108:y=910:w=840:h=4:color={primary_color}@0.90:t=fill"
    chain += f",drawbox=x=108:y=932:w=620:h=3:color={secondary_color}@0.86:t=fill[out]"
    segments.append(chain)
    return ";".join(segments)


def run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True)


def generate_for_faction(faction: dict[str, object]) -> None:
    slug = str(faction["slug"])
    title = str(faction["title"])
    primary = str(faction["primary"])
    secondary = str(faction["secondary"])
    recruitment = str(faction["recruitment"])
    doctrine = str(faction["doctrine"])
    threat = str(faction["threat"])
    final_order = str(faction["final_order"])
    territory = str(faction["territory"])
    control = str(faction["control"])
    risk = str(faction["risk"])
    captions = list(faction["captions"])
    bg = ROOT / f"{slug}-bg.svg"
    logo = ROOT / f"{slug}-logo.svg"
    poster = ROOT / f"{slug}-promo-poster.png"
    mp4 = ROOT / f"{slug}-promo.mp4"
    webm = ROOT / f"{slug}-promo.webm"
    filt = build_filter(title, recruitment, doctrine, threat, final_order, territory, control, risk, captions, primary, secondary)

    run([
        "ffmpeg", "-y",
        "-loop", "1", "-i", str(bg),
        "-loop", "1", "-i", str(logo),
        "-filter_complex", filt,
        "-map", "[out]",
        "-t", "12",
        "-r", "30",
        "-c:v", "libx264",
        "-crf", "16",
        "-preset", "slow",
        "-maxrate", "6000k",
        "-bufsize", "12000k",
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        str(mp4),
    ])
    run([
        "ffmpeg", "-y",
        "-loop", "1", "-i", str(bg),
        "-loop", "1", "-i", str(logo),
        "-filter_complex", filt,
        "-map", "[out]",
        "-t", "12",
        "-r", "30",
        "-c:v", "libvpx-vp9",
        "-b:v", "0",
        "-crf", "22",
        "-deadline", "good",
        "-pix_fmt", "yuv420p",
        str(webm),
    ])
    run([
        "ffmpeg", "-y",
        "-i", str(mp4),
        "-vf", "select=eq(n\\,0)",
        "-frames:v", "1",
        "-update", "1",
        str(poster),
    ])


def main() -> int:
    for faction in FACTIONS:
        generate_for_faction(faction)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml


def env_path(name: str, default: Path | str) -> Path:
    return Path(os.environ.get(name) or default).expanduser()


WORKSPACE = env_path("CHUMMER_WORKSPACE_ROOT", "/docker/chummercomplete")
WORK = env_path("CHUMMER_MAGICFIT_REFINED_PLAN_WORK_DIR", WORKSPACE / "_work" / "refined_magicfit_promo_plans_20260531")
OUT = env_path("CHUMMER_MAGICFIT_REFINED_PLAN_OUT_DIR", WORKSPACE / "_completion" / "refined_magicfit_promo_plans_20260531")
DETAILED_ZIP = env_path(
    "CHUMMER_MAGICFIT_DETAILED_SCREENPLAY_ZIP",
    Path.home() / "jammer6_each_horizon_detailed_screenplays_magicfit_20260531.zip",
)
EPIC_ZIP = env_path(
    "CHUMMER_MAGICFIT_EPIC_SCREENPLAY_ZIP",
    Path.home() / "jammer6_epic_rewrite_blackledger_nexuspan_magicfit_20260531.zip",
)

HUMANIZED_CAPTURE_STYLE = (
    "Humanized capture style: ground this like a practical live-action tabletop/product documentary clip, "
    "not a synthetic AI trailer. Use natural lens behavior, believable handheld or tripod camera movement, "
    "slight actor asymmetry, real skin texture, ordinary clothing mixed with restrained cyberpunk props, "
    "messy tabletop details, practical reflections, imperfect focus pulls, and diegetic screens that can be "
    "blurred or replaced later. Keep AR/UI overlays sparse, secondary, and clearly added in post. Prefer one "
    "clear human action over abstract neon spectacle."
)

GLOBAL_NEGATIVE = (
    "flat vector, SVG, static poster, slideshow, generic corporate SaaS ad, no people, dead frame, "
    "plastic faces, waxy skin, over-smoothed faces, uncanny symmetry, identical faces, broken hands, extra fingers, "
    "warped eyes, rubber mouths, unreadable generated text, fake readable UI text, floating HUD clutter, excessive neon fog, "
    "over-sharpened AI trailer look, synthetic bokeh, official Shadowrun logos, official corporate/faction marks, "
    "sourcebook art, sourcebook page layout, real celebrity likeness, watermark, cheap cosplay, cartoonish metahumans"
)


def now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def unzip_once(path: Path) -> None:
    target_marker = WORK / f".{path.stem}.unpacked"
    if target_marker.exists():
        return
    with zipfile.ZipFile(path) as archive:
        archive.extractall(WORK)
    target_marker.parent.mkdir(parents=True, exist_ok=True)
    target_marker.write_text(now_iso() + "\n", encoding="utf-8")


def parse_timecode_duration(timecode: str) -> int:
    match = re.fullmatch(r"(?P<s_m>\d\d):(?P<s_s>\d\d)-(?P<e_m>\d\d):(?P<e_s>\d\d)", timecode.strip())
    if not match:
        return 9
    start = int(match.group("s_m")) * 60 + int(match.group("s_s"))
    end = int(match.group("e_m")) * 60 + int(match.group("e_s"))
    return max(4, min(15, end - start))


def parse_scene_meta(block: str) -> dict[str, Any]:
    yaml_text = re.search(r"```yaml\s*(.*?)```", block, flags=re.DOTALL)
    if not yaml_text:
        return {}
    raw = yaml_text.group(1)
    try:
        loaded = yaml.safe_load(raw)
        return loaded if isinstance(loaded, dict) else {}
    except yaml.YAMLError:
        meta: dict[str, Any] = {}
        for line in raw.splitlines():
            if ":" not in line:
                continue
            key, value = line.split(":", 1)
            meta[key.strip()] = value.strip().strip('"').strip("'")
        return meta


def extract_fenced_after(block: str, label: str) -> str:
    pattern = rf"\*\*{re.escape(label)}[^\n]*\*\*\s*```(?:text|yaml)?\s*(.*?)```"
    match = re.search(pattern, block, flags=re.DOTALL | re.IGNORECASE)
    return match.group(1).strip() if match else ""


def extract_plain_after(block: str, label: str) -> str:
    pattern = rf"\*\*{re.escape(label)}[^\n]*\*\*\s*(.*?)(?=\n\*\*|\n### |\Z)"
    match = re.search(pattern, block, flags=re.DOTALL | re.IGNORECASE)
    return " ".join(match.group(1).strip().split()) if match else ""


def parse_scene_blocks(text: str, heading_prefix: str) -> list[tuple[str, str, str]]:
    pattern = r"(^###? Scene\s+\d+\s+[-—]\s+.*?)(?=^###? Scene\s+\d+\s+[-—]|\Z)"
    matches = re.finditer(pattern, text, flags=re.DOTALL | re.MULTILINE)
    blocks: list[tuple[str, str, str]] = []
    for index, match in enumerate(matches, start=1):
        block = match.group(1)
        heading = block.splitlines()[0].strip("# ").strip()
        scene_match = re.match(r"Scene\s+(\d+)\s+[-—]\s+(.+)", heading, flags=re.IGNORECASE)
        scene_no = scene_match.group(1) if scene_match else f"{index:02d}"
        title = scene_match.group(2).strip() if scene_match else heading
        blocks.append((scene_no.zfill(2), title, block))
    return blocks


def humanize_render_prompt(prompt: str) -> str:
    replacements = {
        "Photoreal cinematic cyberpunk product trailer, realistic metahuman cast, dramatic but premium lighting, practical neon, shallow depth of field, live-action feeling, expressive faces, grounded action, premium production value, humor through performance, real props, table play mixed with elegant futuristic UI overlays added in post.": HUMANIZED_CAPTURE_STYLE,
        "Photoreal cinematic cyberpunk product trailer scene": "Grounded live-action product-documentary scene",
        "Photoreal cinematic cyberpunk epic trailer scene": "Grounded live-action campaign-documentary scene",
        "premium production value": "credible small-crew production value",
        "dramatic but premium lighting": "motivated practical lighting",
        "elegant futuristic UI overlays": "restrained replaceable UI plates",
        "floating data": "subtle screen reflection and practical interface light",
        "translucent data strands": "brief restrained interface reflections",
        "hero push": "measured camera push",
    }
    result = prompt
    for old, new in replacements.items():
        result = result.replace(old, new)
    return " ".join(result.split())


def normalize_render_prompt(prompt: str, fallback_parts: list[str]) -> str:
    base = humanize_render_prompt(prompt.strip() or ". ".join(part for part in fallback_parts if part))
    refinements = [
        HUMANIZED_CAPTURE_STYLE,
        "Refined render plan: render this as one grounded shot or a simple two-shot sequence, not a slideshow or glossy montage.",
        "Show at least one clearly acting person; metahuman traits should be subtle makeup or wardrobe cues, not cartoon prosthetics.",
        "Do not ask the model to generate exact readable UI, captions, logos, or product text; those are added in post.",
        "Keep motion obvious through a hand action, eye-line change, object movement, or camera move that a small crew could actually shoot.",
        "Avoid perfect symmetry, mannequin faces, clean empty rooms, overdesigned HUDs, and surreal neon abstraction.",
        "Public-safe IP boundary: no official Shadowrun logos, no canonical named characters, no sourcebook art.",
    ]
    return " ".join([base, *refinements])


def normalize_negative_prompt(negative: str) -> str:
    terms: list[str] = []
    seen: set[str] = set()
    for part in [negative.strip(), GLOBAL_NEGATIVE]:
        if not part:
            continue
        for term in [item.strip() for item in part.split(",") if item.strip()]:
            key = term.lower()
            if key in seen:
                continue
            seen.add(key)
            terms.append(term)
    return ", ".join(terms)


def detailed_horizon_assets(root: Path) -> list[dict[str, Any]]:
    assets: list[dict[str, Any]] = []
    for screenplay in sorted(root.glob("HORIZON_*_DETAILED_SCREENPLAY.md")):
        text = screenplay.read_text(encoding="utf-8")
        title_line = text.splitlines()[0].lstrip("# ").strip()
        horizon = title_line.split("—", 1)[0].strip()
        focus = extract_plain_after(text, "Horizon focus")
        scenes = []
        for scene_no, title, block in parse_scene_blocks(text, "###"):
            meta = parse_scene_meta(block)
            prompt = extract_fenced_after(block, "MagicFit render prompt")
            negative = normalize_negative_prompt(extract_fenced_after(block, "MagicFit negative prompt"))
            timecode = str(meta.get("timecode") or "00:00-00:09")
            scene_id = f"{horizon.lower().replace('-', '_').replace(' ', '_')}_{scene_no}_{str(meta.get('scene_slug') or title).lower().replace(' ', '_').replace('-', '_')}"
            fallback = [
                f"Photoreal cinematic cyberpunk product trailer scene for {horizon}.",
                f"Scene title: {title}.",
                f"Horizon focus: {focus}.",
                extract_plain_after(block, "Setting / Szenenbild"),
                extract_plain_after(block, "Blocking / Action beat"),
            ]
            scenes.append(
                {
                    "id": scene_id,
                    "scene_number": int(scene_no),
                    "title": title,
                    "timecode": timecode,
                    "duration_seconds": parse_timecode_duration(timecode),
                    "on_screen_text": extract_plain_after(block, "On-screen text / Einblender").strip("`"),
                    "prompt": normalize_render_prompt(prompt, fallback),
                    "negative_prompt": negative,
                }
            )
        assets.append(
            {
                "lane": "detailed_horizon_deepdives",
                "asset_id": f"{horizon.lower().replace('-', '_').replace(' ', '_')}_90s_deepdive",
                "title": f"{horizon} 90s Deep-Dive",
                "horizon": horizon,
                "source_file": str(screenplay),
                "duration_seconds": sum(scene["duration_seconds"] for scene in scenes),
                "scenes": scenes,
            }
        )
    return assets


def epic_assets(root: Path) -> list[dict[str, Any]]:
    assets: list[dict[str, Any]] = []
    for screenplay in [root / "BLACK_LEDGER_EPIC_90S_SCREENPLAY.md", root / "NEXUS_PAN_EPIC_90S_SCREENPLAY.md"]:
        text = screenplay.read_text(encoding="utf-8")
        title_line = text.splitlines()[0].lstrip("# ").strip()
        horizon = title_line.split("—", 1)[0].strip()
        scenes = []
        for scene_no, title, block in parse_scene_blocks(text, "##"):
            meta = parse_scene_meta(block)
            prompt = extract_fenced_after(block, "MagicFit prompt")
            negative = normalize_negative_prompt("")
            timecode = str(meta.get("timecode") or "00:00-00:09")
            scene_id = f"{horizon.lower().replace(' ', '_')}_epic_{scene_no}_{title.lower().replace(' ', '_').replace('-', '_')}"
            fallback = [
                f"Photoreal cinematic cyberpunk epic trailer scene for {horizon}.",
                f"Scene title: {title}.",
                extract_plain_after(block, "Scene description"),
                extract_plain_after(block, "Action"),
            ]
            scenes.append(
                {
                    "id": scene_id,
                    "scene_number": int(scene_no),
                    "title": title,
                    "timecode": timecode,
                    "duration_seconds": parse_timecode_duration(timecode),
                    "on_screen_text": str(meta.get("on_screen_text") or ""),
                    "prompt": normalize_render_prompt(prompt, fallback),
                    "negative_prompt": negative,
                }
            )
        assets.append(
            {
                "lane": "epic_blackledger_nexuspan",
                "asset_id": f"{horizon.lower().replace(' ', '_')}_epic_90s",
                "title": f"{horizon} Epic 90s",
                "horizon": horizon,
                "source_file": str(screenplay),
                "duration_seconds": sum(scene["duration_seconds"] for scene in scenes),
                "scenes": scenes,
            }
        )
    return assets


def main() -> int:
    WORK.mkdir(parents=True, exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)
    unzip_once(DETAILED_ZIP)
    unzip_once(EPIC_ZIP)

    detailed_root = WORK / DETAILED_ZIP.stem
    epic_root = WORK / EPIC_ZIP.stem
    assets = detailed_horizon_assets(detailed_root) + epic_assets(epic_root)
    total_scenes = sum(len(asset["scenes"]) for asset in assets)

    manifest = {
        "contract_name": "chummer.refined_magicfit_promo_plans.render_manifest",
        "generated_at_utc": now_iso(),
        "source_zips": [str(DETAILED_ZIP), str(EPIC_ZIP)],
        "provider": "MagicFit",
        "render_method": "one_clip_per_scene_then_post_composite",
        "render_style_policy": {
            "goal": "reduce AI-generated visual tells while preserving the Chummer6 horizon story",
            "positive_style": HUMANIZED_CAPTURE_STYLE,
            "negative_style": GLOBAL_NEGATIVE,
        },
        "asset_count": len(assets),
        "scene_count": total_scenes,
        "claim_boundary": "These are refined render manifests and scene renders; final public release still requires human creative review.",
        "assets": assets,
    }
    (OUT / "REFINED_MAGICFIT_RENDER_MANIFEST.generated.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    (OUT / "REFINED_MAGICFIT_RENDER_MANIFEST.generated.yaml").write_text(yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8")
    verdict = "READY_TO_RENDER" if total_scenes == 110 else "NOT_READY"
    (OUT / "FINAL_REFINED_MAGICFIT_PLAN_VERDICT.md").write_text(
        f"{verdict}\n\nAssets: {len(assets)}\nScenes: {total_scenes}\nGenerated: {manifest['generated_at_utc']}\n",
        encoding="utf-8",
    )
    print(verdict)
    return 0 if verdict == "READY_TO_RENDER" else 1


if __name__ == "__main__":
    raise SystemExit(main())

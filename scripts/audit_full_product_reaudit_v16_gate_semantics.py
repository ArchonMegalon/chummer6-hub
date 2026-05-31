#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


WORKSPACE = Path("/docker/chummercomplete")
RUN_SERVICES = WORKSPACE / "chummer.run-services"
OUT = WORKSPACE / "_completion" / "full_product_reaudit_v16"
BASE_URL = "https://chummer.run"
LOCAL_BASE_URL = "http://127.0.0.1:8091"


def now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.is_file() else ""


def run(command: list[str]) -> dict[str, Any]:
    completed = subprocess.run(command, cwd=RUN_SERVICES, capture_output=True, text=True)
    return {
        "command": command,
        "returncode": completed.returncode,
        "stdout": completed.stdout[-4000:],
        "stderr": completed.stderr[-4000:],
        "pass": completed.returncode == 0,
    }


def comparable_design_text(path: Path, relative_path: str) -> str:
    text = read_text(path)
    if relative_path != "WEEKLY_PRODUCT_PULSE.generated.json" or not text:
        return text
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return text
    if isinstance(payload, dict):
        payload["generated_at"] = "__normalized_generated_at__"
        return json.dumps(payload, indent=2, sort_keys=False)
    return text


def ffprobe(path: Path) -> dict[str, Any]:
    completed = subprocess.run(
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
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        return {"status": "fail", "stderr": completed.stderr}
    payload = json.loads(completed.stdout)
    streams = payload.get("streams") or []
    return {
        "status": "pass",
        "duration": float(dict(payload.get("format") or {}).get("duration") or 0.0),
        "has_video": any(stream.get("codec_type") == "video" for stream in streams),
        "has_audio": any(stream.get("codec_type") == "audio" for stream in streams),
        "streams": streams,
    }


def check(condition: bool, name: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"name": name, "status": "pass" if condition else "fail", "details": details or {}}


def main() -> int:
    checks: list[dict[str, Any]] = []

    unit_tests = run(["dotnet", "test", "Chummer.Run.sln", "--no-restore"])
    checks.append(check(unit_tests["pass"], "Full .NET product test suite passes", unit_tests))

    canonical_root = WORKSPACE / "chummer-design" / "products" / "chummer"
    mirror_root = RUN_SERVICES / ".codex-design" / "product"
    for relative_path in (
        "PUBLIC_LANDING_MANIFEST.yaml",
        "PUBLIC_FEATURE_REGISTRY.yaml",
        "PUBLIC_NAVIGATION.yaml",
        "PUBLIC_RELEASE_EXPERIENCE.yaml",
        "PUBLIC_DOWNLOADS_POLICY.md",
        "PUBLIC_LANDING_POLICY.md",
        "WEEKLY_PRODUCT_PULSE.generated.json",
        "NEXT_90_DAY_PRODUCT_ADVANCE_REGISTRY.yaml",
        "NEXT_90_DAY_QUEUE_STAGING.generated.yaml",
        "horizons/black-ledger.md",
    ):
        canonical_path = canonical_root / relative_path
        mirror_path = mirror_root / relative_path
        checks.append(check(
            canonical_path.is_file() and mirror_path.is_file(),
            f"{relative_path} exists in canonical design and run-services mirror",
            {"canonical": str(canonical_path), "mirror": str(mirror_path)}))
        checks.append(check(
            comparable_design_text(canonical_path, relative_path) == comparable_design_text(mirror_path, relative_path),
            f"{relative_path} has no canonical design mirror drift",
            {"canonical": str(canonical_path), "mirror": str(mirror_path)}))

    navigation_text = read_text(mirror_root / "PUBLIC_NAVIGATION.yaml")
    expected_nav = [
        "label: Home\n    href: /",
        "label: Get Chummer\n    href: /downloads",
        "label: What works today\n    href: /now",
        "label: Worlds\n    href: /ledger",
        "label: Account\n    href: /signup",
        "label: Help\n    href: /help",
    ]
    checks.append(check(all(item in navigation_text for item in expected_nav), "Flagship public navigation matches original product chrome", {"expected_nav": expected_nav}))

    manifest_text = read_text(mirror_root / "PUBLIC_LANDING_MANIFEST.yaml")
    feature_registry_text = read_text(mirror_root / "PUBLIC_FEATURE_REGISTRY.yaml")
    checks.append(check("path: /ledger" in manifest_text and "purpose: public_worlds_entry" in manifest_text, "Manifest publishes the Worlds/Black Ledger public entry"))
    checks.append(check("path: /progress" in manifest_text, "Manifest publishes the progress route used by public proof surfaces"))
    checks.append(check("/auth/google/start?next=%2Fparticipate%2Fcodex" in manifest_text, "Guided contribution fallback stays on Google start handoff"))
    checks.append(check("href: /account/participation" in feature_registry_text and "registered_href: /account/participation" in feature_registry_text, "Feature registry points guided contribution at the signed-in participation dashboard"))

    release = read_json(OUT / "RELEASE_TRUTH_MATRIX.generated.json")
    checks.append(check(release.get("status") == "pass", "release truth matrix status is pass", release))
    checks.append(check(release.get("gold_claim_allowed") is True, "release truth explicitly allows gold claim after alignment"))
    checks.append(check(release.get("release_manifest", {}).get("version") != "run-20260518-220935", "release version is not stale run-20260518-220935"))
    checks.append(check(release.get("release_manifest", {}).get("proofStatus") == "passed", "release manifest proofStatus is passed"))
    checks.append(check(release.get("release_manifest", {}).get("download_count") == 3, "release manifest has three platform downloads"))
    checks.append(check(all(release.get("live_truth", {}).get("downloads_page", {}).get(key) for key in ("contains_windows", "contains_linux", "contains_macos")), "downloads page proves all platform shelves"))

    routes = read_json(OUT / "LIVE_PUBLIC_ROUTE_PROOF.generated.json")
    route_paths = {str(item.get("path")) for item in routes.get("required_route_results") or []}
    checks.append(check(routes.get("status") == "pass", "live public route proof status is pass"))
    checks.append(check(not routes.get("dead_links") and not routes.get("forbidden_hits"), "live public routes have no dead links or forbidden launch scaffolding"))
    checks.append(check({"/", "/downloads", "/status", "/ledger/newsroom", "/horizons"}.issubset(route_paths), "route proof includes release-critical public routes", {"route_paths": sorted(route_paths)}))

    formport = read_json(OUT / "CLASSIC_FORMPORT_TYPED_BINDING_AUDIT.generated.json")
    requirements = formport.get("requirements") or {}
    checks.append(check(formport.get("status") == "pass" and all(requirements.values()), "Classic FormPort typed requirements all pass", {"requirements": requirements}))
    checks.append(check(not formport.get("generic_projection_hits"), "Classic FormPorts have no preview-json/fact-bucket projection hits"))
    checks.append(check("still depend" not in str(formport.get("summary") or "").lower(), "Classic FormPort summary does not contradict pass verdict"))

    for edition in ("SR4", "SR5", "SR6"):
        text = read_text(OUT / f"FINAL_{edition}_RULE_AUTHORITY_VERDICT.md")
        checks.append(check(f"{edition}_RULE_AUTHORITY_READY" in text, f"{edition} rule authority ready marker present"))
        checks.append(check("Copyright boundary" in text and "pass" in text.lower(), f"{edition} rule authority includes acceptance and copyright boundary"))

    magicfit_text = read_text(OUT / "FINAL_MAGICFIT_PROVIDER_ADAPTER_VERDICT.md")
    magicfit_provider = read_json(WORKSPACE / "_completion" / "magicfit_provider" / "MAGICFIT_PROVIDER_VERIFICATION.generated.json")
    magicfit_source = read_json(WORKSPACE / "_completion" / "magicfit_jama6_promo_12_scenes" / "MAGICFIT_12_SCENE_PROMO_SOURCE_AUDIT.generated.json")
    magicfit_receipt = read_json(RUN_SERVICES / "Chummer.Run.Api" / "wwwroot" / "media" / "promo" / "chummer6-flagship-promo.receipt.json")
    checks.append(check("MAGICFIT_PROVIDER_ADAPTER_READY" in magicfit_text and magicfit_provider.get("status") == "verified", "MagicFit provider verdict is backed by verified provider receipt"))
    checks.append(check(magicfit_source.get("status") == "pass" and magicfit_source.get("found_scene_count") == 12, "MagicFit flagship source audit proves 12 scenes"))
    checks.append(check(magicfit_receipt.get("status") == "published" and magicfit_receipt.get("faction_assets_used") is False, "Flagship public promo receipt is published and faction-free"))
    checks.append(check(magicfit_receipt.get("magicfit_claim_allowed") is True and magicfit_receipt.get("magicfit_final_visual_render_claim") is True and magicfit_receipt.get("visual_scene_count") == 12, "Flagship promo receipt proves MagicFit 12-scene final reel"))

    flagship_reel = run(["python3", "scripts/verify_flagship_promo_12_scene_reel.py", "--asset", "chummer6-flagship-promo"])
    checks.append(check(flagship_reel["pass"], "Flagship promo has 12 visually distinct sampled scenes", flagship_reel))

    for asset_id in ("chummer6-flagship-promo", "every-wonder-horizon-promo"):
        mp4 = RUN_SERVICES / "Chummer.Run.Api" / "wwwroot" / "media" / "promo" / f"{asset_id}.mp4"
        receipt = read_json(RUN_SERVICES / "Chummer.Run.Api" / "wwwroot" / "media" / "promo" / f"{asset_id}.receipt.json")
        probe = ffprobe(mp4)
        checks.append(check(receipt.get("status") == "published", f"{asset_id} has published receipt"))
        checks.append(check(probe.get("status") == "pass" and probe.get("has_video") and probe.get("has_audio") and probe.get("duration", 0) >= 89.5, f"{asset_id} is a 90-second audio/video asset", probe))

    newsroom = run(["python3", "scripts/verify_black_ledger_newsroom_surface.py", "--base-url", BASE_URL])
    checks.append(check(newsroom["pass"], "Black Ledger newsroom live verifier passes", newsroom))
    table = run(["python3", "scripts/verify_table_pulse_connected_lane_surface.py", "--base-url", BASE_URL])
    checks.append(check(table["pass"], "Table Pulse connected live verifier passes", table))
    pwa = run(["python3", "scripts/verify_pwa_notification_runtime.py", "--base-url", BASE_URL])
    checks.append(check(pwa["pass"], "PWA notification runtime verifier passes", pwa))

    for script_name, label in (
        ("scripts/build_chummer6_flagship_promo.py", "flagship promo check mode"),
        ("scripts/build_every_wonder_horizon_promo.py", "Every Wonder Horizon promo check mode"),
    ):
        result = run(["python3", script_name, "--check"])
        checks.append(check(result["pass"], label, result))

    failures = [item for item in checks if item["status"] != "pass"]
    payload = {
        "contract_name": "chummer.full_product_reaudit_v16.gate_semantics_audit",
        "generated_at_utc": now_iso(),
        "status": "pass" if not failures else "fail",
        "verdict": "GATE_SEMANTICS_READY" if not failures else "NOT_READY",
        "check_count": len(checks),
        "failing_count": len(failures),
        "checks": checks,
    }
    (OUT / "GATE_SEMANTICS_AUDIT.generated.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": payload["status"], "failing_count": len(failures)}, indent=2))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())

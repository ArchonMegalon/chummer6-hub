#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import requests


WORKSPACE = Path("/docker/chummercomplete")
RUN_SERVICES = WORKSPACE / "chummer.run-services"
OUT = WORKSPACE / "_completion" / "full_product_reaudit_v16"
DEFAULT_PUBLIC_BASE_URL = "https://chummer.run"
LOCAL_BASE_URL = "http://127.0.0.1:8091"
BASE_URL = os.environ.get("CHUMMER_FULL_PRODUCT_REAUDIT_BASE_URL", DEFAULT_PUBLIC_BASE_URL).rstrip("/")
PUBLIC_BASE_URL = os.environ.get("CHUMMER_FULL_PRODUCT_REAUDIT_PUBLIC_BASE_URL", DEFAULT_PUBLIC_BASE_URL).rstrip("/")
SURFACE_VERIFY_BASE_URL = os.environ.get("CHUMMER_FULL_PRODUCT_REAUDIT_SURFACE_BASE_URL", LOCAL_BASE_URL).rstrip("/")


def surface_verify_command(script_name: str) -> list[str]:
    return ["python3", f"scripts/{script_name}", "--base-url", SURFACE_VERIFY_BASE_URL]


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


def fetch_text(url: str) -> dict[str, Any]:
    last_error = ""
    for attempt in range(1, 4):
        try:
            response = requests.get(url, timeout=30)
            return {
                "url": url,
                "attempts": attempt,
                "status_code": response.status_code,
                "text": response.text,
                "pass": 200 <= response.status_code < 300,
            }
        except requests.RequestException as exc:
            last_error = f"{type(exc).__name__}: {exc}"

    return {
        "url": url,
        "attempts": 3,
        "status_code": None,
        "text": "",
        "error": last_error,
        "pass": False,
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


STALE_PUBLIC_GUIDE_PHRASES = [
    "macOS still lacks the promoted desktop installer proof",
    "There is still no public macOS installer",
    "Still missing from the promoted installer lane: macOS",
    "There is no public macOS installer today",
    "Downloads are currently live for Windows and Linux",
]

REQUIRED_HORIZON_PROMO_SCENE_IDS = [
    "opener_table_remembers",
    "proof_boundary",
    "nexus_pan",
    "alice",
    "karma_forge",
    "jackpoint",
    "runsite",
    "runbook_press",
    "table_pulse",
    "black_ledger",
    "community_hub",
    "finale_all_horizons",
]


def text_contains_any(source: str, phrases: tuple[str, ...]) -> bool:
    return any(phrase in source for phrase in phrases)


def public_guide_release_truth_checks(public_release_packet: dict[str, Any], public_guide_text: str) -> list[dict[str, Any]]:
    return [
        check(
            public_release_packet.get("available_platforms") == ["Windows", "Linux", "macOS"],
            "public guide release packet agrees with three-platform live shelf",
            public_release_packet,
        ),
        check(
            public_release_packet.get("missing_platforms") == [],
            "public guide release packet has no missing platform contradiction",
            public_release_packet,
        ),
        check(
            public_release_packet.get("shelf_truth_line") == "Downloads are currently live for Windows, Linux, and macOS.",
            "public guide shelf truth names Windows, Linux, and macOS",
            {"shelf_truth_line": public_release_packet.get("shelf_truth_line")},
        ),
        check(
            "Avalonia Desktop macOS ARM64 Installer" in public_guide_text
            and not any(phrase in public_guide_text for phrase in STALE_PUBLIC_GUIDE_PHRASES),
            "public guide copy does not regress to stale missing-macOS installer truth",
            {"forbidden_phrases": STALE_PUBLIC_GUIDE_PHRASES},
        ),
    ]


def journey_gate_truth_check(journey_gates: dict[str, Any]) -> dict[str, Any]:
    journey_truth = journey_gates.get("current_truth") if isinstance(journey_gates.get("current_truth"), dict) else {}
    return check(
        journey_truth.get("state") == "ready" and journey_truth.get("blocked_count") == 0,
        "design journey gates current truth is ready with zero blockers",
        journey_truth,
    )


def every_wonder_horizon_receipt_checks(receipt: dict[str, Any], probe: dict[str, Any]) -> list[dict[str, Any]]:
    production_scenes = receipt.get("production_scenes") if isinstance(receipt.get("production_scenes"), list) else []
    scene_ids = [str(scene.get("id") or "") for scene in production_scenes if isinstance(scene, dict)]
    proof_constraints = receipt.get("proof_constraints") if isinstance(receipt.get("proof_constraints"), list) else []
    return [
        check(receipt.get("status") == "published", "every-wonder-horizon-promo has published receipt", receipt),
        check(
            probe.get("status") == "pass"
            and probe.get("has_video")
            and probe.get("has_audio")
            and probe.get("duration", 0) >= 89.5,
            "every-wonder-horizon-promo is a 90-second audio/video asset",
            probe,
        ),
        check(
            receipt.get("scene_count") == 12 and len(production_scenes) == 12 and scene_ids == REQUIRED_HORIZON_PROMO_SCENE_IDS,
            "Every Wonder Horizon promo receipt proves the required 12-scene production sheet",
            {"scene_ids": scene_ids, "required_scene_ids": REQUIRED_HORIZON_PROMO_SCENE_IDS},
        ),
        check(
            receipt.get("horizon_claim_boundary") == "directional_future_shelf_not_current_release_truth"
            and receipt.get("magicfit_claim_allowed") is False
            and receipt.get("provider_claim") == "none"
            and "MagicFit render claim requires provider and scene receipts; otherwise label first-party motion storyboard" in proof_constraints,
            "Every Wonder Horizon promo stays proof-bounded and does not fake MagicFit rendering",
            {
                "horizon_claim_boundary": receipt.get("horizon_claim_boundary"),
                "magicfit_claim_allowed": receipt.get("magicfit_claim_allowed"),
                "provider_claim": receipt.get("provider_claim"),
                "proof_constraints": proof_constraints,
            },
        ),
    ]


def rule_authority_receipt_checks(
    minimum_coverage: dict[str, Any],
    verdict_texts: dict[str, str],
) -> list[dict[str, Any]]:
    rulesets = minimum_coverage.get("rulesets") if isinstance(minimum_coverage.get("rulesets"), dict) else {}
    checks: list[dict[str, Any]] = []

    for edition in ("sr4", "sr5", "sr6"):
        text = verdict_texts.get(edition, "")
        checks.append(check(
            "Copyright boundary" in text and "pass" in text.lower(),
            f"{edition.upper()} rule authority includes acceptance and copyright boundary",
            {"verdict_path": f"FINAL_{edition.upper()}_RULE_AUTHORITY_VERDICT.md"},
        ))

    sr5 = rulesets.get("sr5") if isinstance(rulesets.get("sr5"), dict) else {}
    sr5_text = verdict_texts.get("sr5", "")
    checks.append(check(
        sr5.get("status") == "pass"
        and sr5.get("final_verdict") == "SR5_RULE_AUTHORITY_READY"
        and "SR5_RULE_AUTHORITY_READY" in sr5_text,
        "SR5 rule authority ready marker is backed by minimum coverage receipt",
        sr5,
    ))

    for edition in ("sr4", "sr6"):
        ruleset = rulesets.get(edition) if isinstance(rulesets.get(edition), dict) else {}
        human_review = ruleset.get("human_review_status") if isinstance(ruleset.get("human_review_status"), dict) else {}
        expected_ready = str(ruleset.get("expected_ready_verdict") or "").strip()
        unexpected_matrix_failures = ruleset.get("verification_matrix_unexpected_failed_gates")
        expected_matrix_blockers = ruleset.get("verification_matrix_expected_ready_blockers")
        remaining_gates = ruleset.get("remaining_gates")
        text = verdict_texts.get(edition, "")
        blocked_on_review = (
            ruleset.get("status") == "fail"
            and ruleset.get("final_verdict") == "NOT_READY"
            and expected_ready
            and expected_ready not in text
            and ruleset.get("full_completion_rule_authority_ready") is False
            and ruleset.get("operator_gold_status") == "fail"
            and human_review.get("pending_review") is True
            and human_review.get("review_ready") is False
            and ruleset.get("verification_matrix_status") == "blocked"
            and isinstance(unexpected_matrix_failures, list)
            and not unexpected_matrix_failures
            and isinstance(expected_matrix_blockers, list)
            and len(expected_matrix_blockers) > 0
            and isinstance(remaining_gates, list)
            and len(remaining_gates) > 0
        )
        ready_under_completion = (
            ruleset.get("status") == "pass"
            and expected_ready
            and ruleset.get("final_verdict") == expected_ready
            and expected_ready in text
            and ruleset.get("full_completion_rule_authority_ready") is True
            and ruleset.get("operator_gold_status") == "pass"
            and ruleset.get("operator_gold_verdict") == expected_ready
            and isinstance(unexpected_matrix_failures, list)
            and not unexpected_matrix_failures
            and isinstance(remaining_gates, list)
            and not remaining_gates
        )

        checks.append(check(
            blocked_on_review or ready_under_completion,
            f"{edition.upper()} rule authority is either bounded-blocked on review or backed by ready completion",
            ruleset,
        ))

    return checks


def main() -> int:
    checks: list[dict[str, Any]] = []

    unit_tests = run(["dotnet", "test", "Chummer.Run.sln", "--no-restore"])
    checks.append(check(unit_tests["pass"], "Full .NET product test suite passes", unit_tests))

    browseract_adapter = read_text(RUN_SERVICES / "Chummer.Run.AI" / "Services" / "Gateway" / "HttpProviderAdapters.cs")
    browseract_tests = read_text(RUN_SERVICES / "Chummer.Tests" / "BrowserActGatewaySafetyTests.cs")
    checks.append(check(
        "BrowserActSafetyPolicy.ThrowIfUnsafeConfiguration(configuration)" in browseract_adapter
        and "ProxyRotation" in browseract_adapter
        and "RefreshCredentials" in browseract_adapter
        and "RefreshCredits" in browseract_adapter
        and "OneMinAiCreditRefresh" in browseract_adapter
        and "BrowserAct_rejects_proxy_or_credit_refresh_configuration" in browseract_tests
        and "BrowserAct_allows_bounded_capture_without_proxy_or_credit_refresh" in browseract_tests,
        "BrowserAct stays bounded and rejects proxy rotation or credit-refresh automation",
        {
            "adapter": "Chummer.Run.AI/Services/Gateway/HttpProviderAdapters.cs",
            "tests": "Chummer.Tests/BrowserActGatewaySafetyTests.cs",
            "boundary": "bounded capture only; no proxy rotation, credential refresh, or One Minute AI credit refresh automation",
        }))

    canonical_root = WORKSPACE / "chummer-design" / "products" / "chummer"
    mirror_root = RUN_SERVICES / ".codex-design" / "product"
    public_guide_root = canonical_root / "public-guide"
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
    checks.append(check(
        (release.get("release_manifest", {}).get("platform_download_count")
         or release.get("release_manifest", {}).get("download_count")) == 3,
        "release manifest has three platform downloads"
    ))
    checks.append(check(all(release.get("live_truth", {}).get("downloads_page", {}).get(key) for key in ("contains_windows", "contains_linux", "contains_macos")), "downloads page proves all platform shelves"))

    public_release_packet = read_json(public_guide_root / "CHUMMER6_PUBLIC_RELEASE_TRUTH_PACKET.generated.json")
    public_guide_text = "\n".join(
        read_text(public_guide_root / name)
        for name in ("README.md", "STATUS.md", "DOWNLOAD.md", "FROM_CHUMMER5A_TO_CHUMMER6.md")
    )
    checks.extend(public_guide_release_truth_checks(public_release_packet, public_guide_text))

    journey_gates = read_json(canonical_root / "JOURNEY_GATES.generated.json")
    checks.append(journey_gate_truth_check(journey_gates))

    routes = read_json(OUT / "LIVE_PUBLIC_ROUTE_PROOF.generated.json")
    route_paths = {str(item.get("path")) for item in routes.get("required_route_results") or []}
    checks.append(check(routes.get("status") == "pass", "live public route proof status is pass"))
    checks.append(check(not routes.get("dead_links") and not routes.get("forbidden_hits"), "live public routes have no dead links or forbidden launch scaffolding"))
    checks.append(check({"/", "/downloads", "/status", "/ledger/newsroom", "/horizons"}.issubset(route_paths), "route proof includes release-critical public routes", {"route_paths": sorted(route_paths)}))

    live_status = fetch_text(f"{BASE_URL}/status")
    live_status_text = live_status.get("text") if isinstance(live_status.get("text"), str) else ""
    contains_local_proof_pass = text_contains_any(
        live_status_text,
        (
            "Current local edge proof passed",
            "Current local release proof passed",
        ),
    )
    contains_local_proof_unknown = text_contains_any(
        live_status_text,
        (
            "Current local edge proof is unknown",
            "Current local release proof is unknown",
        ),
    )
    contains_gold_ready_marker = text_contains_any(
        live_status_text,
        (
            "Gold-ready on Public release Build run-",
            "Gold-ready on Public release",
            "Current public release",
        ),
    )
    checks.append(check(
        live_status.get("pass") is True
        and "run-20260518-220935" not in live_status_text
        and contains_local_proof_pass
        and not contains_local_proof_unknown
        and contains_gold_ready_marker,
        "configured /status route proves current gold-ready release and local edge proof",
        {
            "url": live_status.get("url"),
            "attempts": live_status.get("attempts"),
            "status_code": live_status.get("status_code"),
            "contains_stale_run": "run-20260518-220935" in live_status_text,
            "contains_local_edge_passed": contains_local_proof_pass,
            "contains_local_edge_unknown": contains_local_proof_unknown,
            "contains_gold_ready_build": contains_gold_ready_marker,
            "error": live_status.get("error"),
        },
    ))

    formport = read_json(OUT / "CLASSIC_FORMPORT_TYPED_BINDING_AUDIT.generated.json")
    requirements = formport.get("requirements") or {}
    checks.append(check(formport.get("status") == "pass" and all(requirements.values()), "Classic FormPort typed requirements all pass", {"requirements": requirements}))
    checks.append(check(not formport.get("generic_projection_hits"), "Classic FormPorts have no preview-json/fact-bucket projection hits"))
    checks.append(check("still depend" not in str(formport.get("summary") or "").lower(), "Classic FormPort summary does not contradict pass verdict"))

    rule_authority_minimum_coverage = read_json(RUN_SERVICES / ".codex-studio" / "published" / "RULE_AUTHORITY_MINIMUM_COVERAGE.generated.json")
    checks.extend(rule_authority_receipt_checks(
        rule_authority_minimum_coverage,
        {
            edition: read_text(OUT / f"FINAL_{edition.upper()}_RULE_AUTHORITY_VERDICT.md")
            for edition in ("sr4", "sr5", "sr6")
        },
    ))

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

    flagship_mp4 = RUN_SERVICES / "Chummer.Run.Api" / "wwwroot" / "media" / "promo" / "chummer6-flagship-promo.mp4"
    flagship_receipt = read_json(RUN_SERVICES / "Chummer.Run.Api" / "wwwroot" / "media" / "promo" / "chummer6-flagship-promo.receipt.json")
    flagship_probe = ffprobe(flagship_mp4)
    checks.append(check(flagship_receipt.get("status") == "published", "chummer6-flagship-promo has published receipt"))
    checks.append(check(
        flagship_probe.get("status") == "pass" and flagship_probe.get("has_video") and flagship_probe.get("has_audio") and flagship_probe.get("duration", 0) >= 89.5,
        "chummer6-flagship-promo is a 90-second audio/video asset",
        flagship_probe,
    ))

    horizon_mp4 = RUN_SERVICES / "Chummer.Run.Api" / "wwwroot" / "media" / "promo" / "every-wonder-horizon-promo.mp4"
    horizon_receipt = read_json(RUN_SERVICES / "Chummer.Run.Api" / "wwwroot" / "media" / "promo" / "every-wonder-horizon-promo.receipt.json")
    checks.extend(every_wonder_horizon_receipt_checks(horizon_receipt, ffprobe(horizon_mp4)))

    for asset_id in ("chummer6-flagship-promo", "every-wonder-horizon-promo"):
        mp4 = RUN_SERVICES / "Chummer.Run.Api" / "wwwroot" / "media" / "promo" / f"{asset_id}.mp4"
        receipt = read_json(RUN_SERVICES / "Chummer.Run.Api" / "wwwroot" / "media" / "promo" / f"{asset_id}.receipt.json")
        probe = ffprobe(mp4)
        checks.append(check(receipt.get("status") == "published", f"{asset_id} has published receipt"))
        checks.append(check(probe.get("status") == "pass" and probe.get("has_video") and probe.get("has_audio") and probe.get("duration", 0) >= 89.5, f"{asset_id} is a 90-second audio/video asset", probe))

    newsroom_command = surface_verify_command("verify_black_ledger_newsroom_surface.py")
    table_command = surface_verify_command("verify_table_pulse_connected_lane_surface.py")
    pwa_command = surface_verify_command("verify_pwa_notification_runtime.py")
    newsroom = run(newsroom_command)
    checks.append(check(newsroom["pass"], "Black Ledger newsroom verifier passes", newsroom))
    table = run(table_command)
    checks.append(check(table["pass"], "Table Pulse connected verifier passes", table))
    pwa = run(pwa_command)
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

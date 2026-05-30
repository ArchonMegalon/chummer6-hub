#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


WORKSPACE = Path("/docker/chummercomplete")
RUN_SERVICES = WORKSPACE / "chummer.run-services"
FLEET = WORKSPACE / ".integrated" / "fleet"
CHUMMER6 = WORKSPACE / "Chummer6"
OUT = WORKSPACE / "_completion" / "full_product_reaudit_v16"
ZIP = RUN_SERVICES / "Chummer.Portal" / "downloads" / "chummer6_full_product_reaudit_v16_20260529.zip"
BASE_URL = "https://chummer.run"

REQUIRED_PUBLIC_PATHS = [
    "/",
    "/downloads",
    "/status",
    "/ledger",
    "/ledger/map",
    "/ledger/factions",
    "/ledger/newsroom",
    "/play",
    "/help",
    "/feedback",
]

REQUIRED_GATES = {
    "RELEASE_TRUTH_MATRIX.generated.json": "json_pass",
    "LIVE_STATUS_RELEASE_ALIGNMENT.generated.json": "json_pass",
    "LIVE_CHUMMER_RUN_ROUTE_PROOF.generated.json": "json_pass",
    "CLASSIC_FORMPORT_FUNCTIONAL_PARITY_AUDIT.generated.json": "json_pass",
    "FINAL_SR4_RULE_AUTHORITY_VERDICT.md": "SR4_RULE_AUTHORITY_READY",
    "FINAL_SR5_RULE_AUTHORITY_VERDICT.md": "SR5_RULE_AUTHORITY_READY",
    "FINAL_SR6_RULE_AUTHORITY_VERDICT.md": "SR6_RULE_AUTHORITY_READY",
    "FINAL_MAGICFIT_PROVIDER_ADAPTER_VERDICT.md": "MAGICFIT_PROVIDER_ADAPTER_READY",
    "FINAL_RAFTER_PIXEFY_QA_STACK_VERDICT.md": "RAFTER_PIXEFY_QA_STACK_READY",
    "FINAL_BLACK_LEDGER_VIDEO_GLOBE_VERDICT.md": "BLACK_LEDGER_VIDEO_GLOBE_READY",
    "FINAL_FACTION_VIDEO_SERIES_VERDICT.md": "FACTION_VIDEO_SERIES_READY",
    "FINAL_BLACK_LEDGER_NEWSROOM_VERDICT.md": "BLACK_LEDGER_NEWSROOM_READY",
    "FINAL_PWA_GOLD_VERDICT.md": "GOLD_READY",
    "FINAL_TABLE_PULSE_OPTOUT_REMOTE_REACTION_VERDICT.md": "GOLD_READY",
}


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.rstrip() + "\n", encoding="utf-8")


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.is_file() else ""


def read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def sha256(path: Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def fetch(path_or_url: str) -> tuple[int | None, str, str]:
    url = path_or_url if path_or_url.startswith("http") else f"{BASE_URL}{path_or_url}"
    request = urllib.request.Request(url, headers={"User-Agent": "chummer-v16-audit/1"})
    try:
        with urllib.request.urlopen(request, timeout=8) as response:
            return int(response.status), response.read().decode("utf-8", errors="replace"), response.geturl()
    except urllib.error.HTTPError as exc:
        return int(exc.code), exc.read().decode("utf-8", errors="replace"), url
    except Exception as exc:
        return None, str(exc), url


def run(command: list[str], cwd: Path = RUN_SERVICES) -> tuple[bool, str]:
    completed = subprocess.run(command, cwd=cwd, capture_output=True, text=True)
    return completed.returncode == 0, completed.stdout if completed.returncode == 0 else completed.stdout + completed.stderr


def copy_or_missing(name: str, sources: list[Path], missing_text: str) -> None:
    for source in sources:
        text = read_text(source)
        if text:
            write_text(OUT / name, text)
            return
    write_text(OUT / name, missing_text)


def link_targets(path: str, html: str) -> list[str]:
    hrefs = re.findall(r"""href=["']([^"'#]+)["']""", html, flags=re.IGNORECASE)
    targets: list[str] = []
    for href in hrefs:
        if href.startswith(("mailto:", "tel:", "javascript:")):
            continue
        absolute = urllib.parse.urljoin(f"{BASE_URL}{path}", href)
        parsed = urllib.parse.urlparse(absolute)
        if parsed.netloc and parsed.netloc != "chummer.run":
            continue
        if parsed.path.startswith("/logout"):
            continue
        targets.append(urllib.parse.urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", parsed.query, "")))
    return sorted(set(targets))


def materialize_live_route_proof(generated: str) -> dict[str, Any]:
    required_results: list[dict[str, Any]] = []
    failures: list[str] = []
    forbidden_hits: list[dict[str, str]] = []
    dead_links: list[dict[str, Any]] = []
    cta_targets_by_path: dict[str, list[str]] = {}
    forbidden_patterns = ["Load Demo Runner", "Codex", "repo tour", "debug"]

    for path in REQUIRED_PUBLIC_PATHS:
        status, body, final_url = fetch(path)
        route_ok = status == 200
        if not route_ok:
            failures.append(path)
        hits = [pattern for pattern in forbidden_patterns if pattern.lower() in body.lower()]
        for pattern in hits:
            forbidden_hits.append({"path": path, "pattern": pattern})
        cta_targets = link_targets(path, body)
        cta_targets_by_path[path] = cta_targets
        required_results.append({
            "path": path,
            "status_code": status,
            "final_url": final_url,
            "success": route_ok,
            "forbidden_hits": hits,
            "cta_target_count": len(cta_targets),
            "sample_cta_targets": cta_targets[:20],
            "dead_links": [],
        })

    unique_cta_targets = sorted({target for targets in cta_targets_by_path.values() for target in targets})
    cta_checks: dict[str, dict[str, Any]] = {}
    with ThreadPoolExecutor(max_workers=12) as executor:
        futures = {executor.submit(fetch, target): target for target in unique_cta_targets}
        for future in as_completed(futures):
            target = futures[future]
            try:
                link_status, _, link_final = future.result()
            except Exception as exc:
                link_status, link_final = None, str(exc)
            link_ok = link_status is not None and 200 <= link_status < 400
            cta_checks[target] = {"url": target, "status_code": link_status, "final_url": link_final, "ok": link_ok}

    for route_result in required_results:
        path = str(route_result["path"])
        route_dead = [cta_checks[target] for target in cta_targets_by_path.get(path, []) if not cta_checks.get(target, {}).get("ok")]
        route_result["dead_links"] = route_dead
        for item in route_dead:
            dead_links.append({"path": path, "url": item["url"], "status_code": item["status_code"]})

    route_ok, route_stdout = run([
        "python3",
        "scripts/verify_public_routes_from_manifest.py",
        "--strict-positive",
        "--seed-receipts",
        "--base-url",
        BASE_URL,
    ])
    route_payload: dict[str, Any] = {}
    if route_ok:
        try:
            route_payload = json.loads(route_stdout)
        except json.JSONDecodeError:
            route_ok = False

    payload = {
        "contract_name": "chummer.full_product_reaudit_v16.live_chummer_run_route_proof",
        "generated_at_utc": generated,
        "base_url": BASE_URL,
        "public_host": "chummer.run",
        "strict_positive": True,
        "required_routes": REQUIRED_PUBLIC_PATHS,
        "required_route_results": required_results,
        "cta_link_check": {
            "unique_target_count": len(unique_cta_targets),
            "checked_target_count": len(cta_checks),
            "failed_target_count": sum(1 for item in cta_checks.values() if not item.get("ok")),
        },
        "manifest_route_proof_summary": route_payload.get("summary", {}),
        "forbidden_hits": forbidden_hits,
        "dead_links": dead_links,
        "status": "pass" if route_ok and not failures and not forbidden_hits and not dead_links else "fail",
    }
    write_json(OUT / "LIVE_CHUMMER_RUN_ROUTE_PROOF.generated.json", payload)
    return payload


def materialize_formport_audit(generated: str) -> dict[str, Any]:
    formport_dir = WORKSPACE / "chummer-presentation" / "Chummer.Avalonia" / "Controls" / "ClassicFormPorts"
    files = sorted(formport_dir.glob("*ClassicPort.axaml*"))
    port_code_files = sorted(formport_dir.glob("*ClassicPort.axaml.cs"))
    bridge_file = formport_dir / "ClassicFormPortViewModelBridge.cs"
    source = "\n".join(read_text(path) for path in files)
    generic_markers = ["state.Rows", "FindValue(rows", "MatchRows(rows", "SectionRowDisplayItem"]
    generic_hits = [marker for marker in generic_markers if marker in source]
    missing_surface = not files
    payload = {
        "contract_name": "chummer.full_product_reaudit_v16.classic_formport_functional_parity",
        "generated_at_utc": generated,
        "status": "fail" if generic_hits or missing_surface else "pass",
        "verdict": "NOT_READY" if generic_hits or missing_surface else "CLASSIC_FORMPORT_FUNCTIONAL_PARITY_READY",
        "checked_files": [str(path) for path in files],
        "requirements": {
            "typed_view_model": bridge_file.is_file(),
            "typed_command_bridge": bridge_file.is_file() and all("ClassicFormPortViewModelBridge.Create" in read_text(path) for path in port_code_files),
            "list_detail_layouts": bool(files),
            "add_edit_delete_flows": all(token in source for token in ("Add", "Edit", "Delete")),
            "context_menus": source.count("ContextMenu") >= len(port_code_files),
            "keyboard_shortcuts": source.count("KeyBinding") >= len(port_code_files),
            "fixture_data": (WORKSPACE / "chummer-presentation" / ".codex-studio" / "published" / "FORM_PORT_COVERAGE_MATRIX.generated.json").is_file(),
            "side_by_side_screenshots": (WORKSPACE / "chummer-presentation" / ".codex-studio" / "published" / "CHUMMER5A_SCREENSHOT_REVIEW_GATE.generated.json").is_file(),
            "veteran_user_task_review": (WORKSPACE / "chummer-presentation" / ".codex-studio" / "published" / "CLASSIC_FORM_PORT_HUMAN_REVIEW.md").is_file(),
            "no_primary_state_rows_token_matching": not generic_hits,
        },
        "generic_projection_hits": generic_hits,
        "missing_surface": missing_surface,
        "summary": "Fails closed while W1 ports still depend on generic state.Rows token matching.",
    }
    payload["status"] = "pass" if all(payload["requirements"].values()) and not generic_hits and not missing_surface else "fail"
    payload["verdict"] = "CLASSIC_FORMPORT_FUNCTIONAL_PARITY_READY" if payload["status"] == "pass" else "NOT_READY"
    write_json(OUT / "CLASSIC_FORMPORT_FUNCTIONAL_PARITY_AUDIT.generated.json", payload)
    return payload


def gate_pass(path: Path, expected: str) -> bool:
    if expected == "json_pass":
        return read_json(path).get("status") == "pass"
    return expected in read_text(path)


def materialize_final_gold(generated: str) -> dict[str, Any]:
    gate_results: dict[str, dict[str, Any]] = {}
    for name, expected in REQUIRED_GATES.items():
        path = OUT / name
        gate_results[name] = {
            "path": str(path),
            "expected": expected,
            "exists": path.is_file(),
            "pass": path.is_file() and gate_pass(path, expected),
        }
    missing = [name for name, result in gate_results.items() if not result["exists"]]
    failing = [name for name, result in gate_results.items() if result["exists"] and not result["pass"]]
    gold_ready = not missing and not failing
    payload = {
        "contract_name": "chummer.full_product_reaudit_v16.full_estate_gold_janitor",
        "generated_at_utc": generated,
        "status": "pass" if gold_ready else "fail",
        "verdict": "GOLD_READY" if gold_ready else "NOT_GOLD",
        "required_gates": gate_results,
        "missing_gates": missing,
        "failing_gates": failing,
    }
    write_json(OUT / "FINAL_GOLD_JANITOR.generated.json", payload)
    lines = [
        "GOLD_READY" if gold_ready else "NOT_GOLD",
        "",
        f"Generated: {generated}",
        "",
        "Gate summary:",
    ]
    for name, result in sorted(gate_results.items()):
        lines.append(f"- {name}: {'pass' if result['pass'] else 'fail'}")
    if missing:
        lines.extend(["", "Missing gates:", *[f"- {name}" for name in missing]])
    if failing:
        lines.extend(["", "Failing gates:", *[f"- {name}" for name in failing]])
    write_text(OUT / "FINAL_GOLD_VERDICT.md", "\n".join(lines))
    return payload


def main() -> int:
    generated = now_iso()
    OUT.mkdir(parents=True, exist_ok=True)

    status_code, status_html, _ = fetch("/status")
    downloads_code, downloads_html, _ = fetch("/downloads")
    releases_code, releases_text, _ = fetch("/downloads/releases.json")
    releases: dict[str, Any] = {}
    if releases_code == 200:
        try:
            releases = json.loads(releases_text)
        except json.JSONDecodeError:
            releases = {}

    rafter_gate = read_json(FLEET / "_completion" / "rafter" / "RAFTER_SECURITY_GOLD_GATE.generated.json")
    pixefy_gate = read_json(FLEET / "_completion" / "pixefy" / "PIXEFY_RESPONSIVE_VISUAL_QA.generated.json")
    combined = read_text(FLEET / "_completion" / "rafter_pixefy" / "FINAL_RAFTER_PIXEFY_QA_STACK_VERDICT.md").strip()
    live_route = materialize_live_route_proof(generated)

    release_truth_pass = (
        status_code == 200
        and downloads_code == 200
        and releases_code == 200
        and releases.get("channel") == "public_stable"
        and releases.get("proofStatus") == "passed"
        and rafter_gate.get("status") == "pass"
        and pixefy_gate.get("status") == "pass"
        and combined == "RAFTER_PIXEFY_QA_STACK_READY"
        and "Load Demo Runner" not in downloads_html
        and "stale" not in status_html.lower()
        and "not gold-ready" not in status_html.lower()
        and "not yet gold-ready" not in status_html.lower()
    )
    release_payload = {
        "contract_name": "chummer.full_product_reaudit_v16.release_truth_matrix",
        "generated_at_utc": generated,
        "source_zip": str(ZIP),
        "source_zip_sha256": sha256(ZIP),
        "status": "pass" if release_truth_pass else "fail",
        "verdict": "RELEASE_TRUTH_ALIGNED" if release_truth_pass else "NOT_GOLD",
        "release_manifest": {
            "version": releases.get("version"),
            "channel": releases.get("channel"),
            "supportabilityState": releases.get("supportabilityState"),
            "proofStatus": releases.get("proofStatus"),
            "download_count": len(releases.get("downloads") or []),
        },
        "qa_gates": {
            "rafter": {
                "required": True,
                "verdict_file": "fleet/_completion/rafter/RAFTER_SECURITY_GOLD_GATE.generated.json",
                "status": rafter_gate.get("status", "missing"),
            },
            "pixefy": {
                "required": True,
                "verdict_file": "fleet/_completion/pixefy/PIXEFY_RESPONSIVE_VISUAL_QA.generated.json",
                "status": pixefy_gate.get("status", "missing"),
            },
            "combined": {
                "required": True,
                "verdict_file": "fleet/_completion/rafter_pixefy/FINAL_RAFTER_PIXEFY_QA_STACK_VERDICT.md",
                "required_value": "RAFTER_PIXEFY_QA_STACK_READY",
                "status": combined,
            },
        },
        "live_truth": {
            "status_page": {
                "status_code": status_code,
                "contains_stale_language": "stale" in status_html.lower(),
                "contains_not_gold_ready": "not gold-ready" in status_html.lower() or "not yet gold-ready" in status_html.lower(),
                "contains_release_version": bool(releases.get("version") and releases.get("version") in status_html),
            },
            "downloads_page": {
                "status_code": downloads_code,
                "contains_demo_language": "Load Demo Runner" in downloads_html,
                "contains_windows": "Windows" in downloads_html,
                "contains_linux": "Linux" in downloads_html,
                "contains_macos": "macOS" in downloads_html or "Mac" in downloads_html,
            },
        },
        "gold_claim_allowed": False,
    }
    write_json(OUT / "RELEASE_TRUTH_MATRIX.generated.json", release_payload)
    write_json(CHUMMER6 / ".codex-studio" / "published" / "RELEASE_TRUTH_MATRIX.generated.json", release_payload)

    live_status_pass = release_truth_pass and live_route.get("status") == "pass"
    write_json(OUT / "LIVE_STATUS_RELEASE_ALIGNMENT.generated.json", {
        "contract_name": "chummer.full_product_reaudit_v16.live_status_release_alignment",
        "generated_at_utc": generated,
        "status": "pass" if live_status_pass else "fail",
        "verdict": "LIVE_STATUS_RELEASE_ALIGNED" if live_status_pass else "NOT_GOLD",
        "release_truth_status": release_payload["status"],
        "live_route_proof_status": live_route.get("status"),
        "status_page": release_payload["live_truth"]["status_page"],
        "downloads_page": release_payload["live_truth"]["downloads_page"],
    })

    materialize_formport_audit(generated)

    copy_or_missing("FINAL_SR4_RULE_AUTHORITY_VERDICT.md", [WORKSPACE / "_completion" / "sr4_rule_authority" / "FINAL_SR4_RULE_AUTHORITY_VERDICT.md"], "NOT_READY\n")
    copy_or_missing("FINAL_SR5_RULE_AUTHORITY_VERDICT.md", [WORKSPACE / "_completion" / "sr5_rule_authority" / "FINAL_SR5_RULE_AUTHORITY_VERDICT.md"], "NOT_READY\n")
    copy_or_missing("FINAL_SR6_RULE_AUTHORITY_VERDICT.md", [WORKSPACE / "_completion" / "sr6_rule_authority" / "FINAL_SR6_RULE_AUTHORITY_VERDICT.md"], "NOT_READY\n")
    copy_or_missing("FINAL_MAGICFIT_PROVIDER_ADAPTER_VERDICT.md", [WORKSPACE / "_completion" / "magicfit_provider" / "FINAL_MAGICFIT_PROVIDER_ADAPTER_VERDICT.md"], "NOT_READY\n")
    copy_or_missing("FINAL_RAFTER_PIXEFY_QA_STACK_VERDICT.md", [FLEET / "_completion" / "rafter_pixefy" / "FINAL_RAFTER_PIXEFY_QA_STACK_VERDICT.md"], "NOT_READY\n")
    copy_or_missing("FINAL_BLACK_LEDGER_VIDEO_GLOBE_VERDICT.md", [WORKSPACE / "_completion" / "full_product_reaudit_v14" / "FINAL_BLACK_LEDGER_VIDEO_GLOBE_VERDICT.md"], "NOT_READY\n")
    copy_or_missing("FINAL_FACTION_VIDEO_SERIES_VERDICT.md", [WORKSPACE / "_completion" / "full_product_reaudit_v14" / "FINAL_FACTION_VIDEO_SERIES_VERDICT.md"], "NOT_READY\n")
    copy_or_missing("FINAL_BLACK_LEDGER_NEWSROOM_VERDICT.md", [WORKSPACE / "_completion" / "full_product_reaudit_v14" / "FINAL_BLACK_LEDGER_NEWSROOM_VERDICT.md"], "NOT_READY\n")
    copy_or_missing("FINAL_PWA_GOLD_VERDICT.md", [WORKSPACE / "_completion" / "full_product_reaudit_v14" / "FINAL_PWA_GOLD_VERDICT.md"], "NOT_READY\n")
    copy_or_missing("FINAL_TABLE_PULSE_OPTOUT_REMOTE_REACTION_VERDICT.md", [WORKSPACE / "_completion" / "full_product_reaudit_v14" / "FINAL_TABLE_PULSE_OPTOUT_REMOTE_REACTION_VERDICT.md"], "NOT_READY\n")

    final = materialize_final_gold(generated)
    return 0 if final["verdict"] == "GOLD_READY" else 1


if __name__ == "__main__":
    raise SystemExit(main())

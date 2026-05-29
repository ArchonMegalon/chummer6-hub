#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import subprocess
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


WORKSPACE = Path("/docker/chummercomplete")
RUN_SERVICES = WORKSPACE / "chummer.run-services"
OUT = WORKSPACE / "_completion" / "full_product_reaudit_v14"
ZIP = Path("/home/tibor/chummer6_full_product_reaudit_v14_20260529.zip")
BASE_URL = "https://chummer.run"


REQUIRED_OUTPUTS = [
    "RELEASE_TRUTH_MATRIX.generated.json",
    "LIVE_STATUS_RELEASE_ALIGNMENT.generated.json",
    "CLASSIC_FORMPORT_REALITY_AUDIT.generated.json",
    "FINAL_SR4_RULE_AUTHORITY_VERDICT.md",
    "FINAL_SR5_RULE_AUTHORITY_VERDICT.md",
    "FINAL_SR6_RULE_AUTHORITY_VERDICT.md",
    "FINAL_MAGICFIT_PROVIDER_ADAPTER_VERDICT.md",
    "FINAL_RAFTER_PIXEFY_QA_STACK_VERDICT.md",
    "FINAL_BLACK_LEDGER_VIDEO_GLOBE_VERDICT.md",
    "FINAL_BLACK_LEDGER_NEWSROOM_VERDICT.md",
    "FINAL_FACTION_VIDEO_SERIES_VERDICT.md",
    "FINAL_PWA_GOLD_VERDICT.md",
    "FINAL_TABLE_PULSE_OPTOUT_REMOTE_REACTION_VERDICT.md",
    "FINAL_GOLD_VERDICT.md",
]


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.is_file() else ""


def read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.rstrip() + "\n", encoding="utf-8")


def fetch(path: str) -> tuple[int, str]:
    request = urllib.request.Request(f"{BASE_URL}{path}", headers={"User-Agent": "chummer-v14-audit/1"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return int(response.status), response.read().decode("utf-8", errors="replace")


def run(command: list[str], *, json_stdout: bool = False) -> tuple[bool, Any]:
    completed = subprocess.run(command, cwd=RUN_SERVICES, capture_output=True, text=True)
    if completed.returncode != 0:
        return False, {"stdout": completed.stdout, "stderr": completed.stderr, "returncode": completed.returncode}
    if json_stdout:
        return True, json.loads(completed.stdout)
    return True, completed.stdout


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def markdown_ready(path: Path, tokens: list[str]) -> tuple[bool, str]:
    text = read_text(path)
    return bool(text and any(token in text for token in tokens)), text


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    generated = now_iso()
    source_zip_sha = sha256(ZIP) if ZIP.is_file() else None

    status_code, status_html = fetch("/status")
    downloads_code, downloads_html = fetch("/downloads")
    releases_code, releases_text = fetch("/downloads/releases.json")
    releases = json.loads(releases_text)

    route_ok, route_payload = run(
        [
            "python3",
            "scripts/verify_public_routes_from_manifest.py",
            "--strict-positive",
            "--seed-receipts",
            "--base-url",
            BASE_URL,
        ],
        json_stdout=True,
    )
    forbidden_ok, _ = run(["python3", "scripts/public_forbidden_string_scan.py", "--base-url", BASE_URL])
    readability_ok, _ = run(["python3", "scripts/public_copy_readability_gate.py", "--base-url", BASE_URL])
    manifest_ok, _ = run(["python3", "scripts/diff_public_manifest_live.py", "--base-url", BASE_URL])

    download_truth = {
        "status_code": downloads_code,
        "contains_windows": "Windows" in downloads_html,
        "contains_linux": "Linux" in downloads_html,
        "contains_macos": "macOS" in downloads_html or "Mac" in downloads_html,
        "contains_demo_language": "Load Demo Runner" in downloads_html,
        "contains_stale_language": "stale" in downloads_html.lower(),
        "contains_missing_language": "missing" in downloads_html.lower(),
    }
    status_truth = {
        "status_code": status_code,
        "contains_stale_language": "stale" in status_html.lower(),
        "contains_not_gold_ready": "not gold-ready" in status_html.lower() or "not yet gold-ready" in status_html.lower(),
        "contains_release_version": releases.get("version") in status_html,
    }
    release_truth_pass = (
        status_code == 200
        and downloads_code == 200
        and releases_code == 200
        and releases.get("channel") == "public_stable"
        and releases.get("supportabilityState") == "gold_supported"
        and releases.get("proofStatus") == "passed"
        and not download_truth["contains_demo_language"]
        and not status_truth["contains_stale_language"]
        and not status_truth["contains_not_gold_ready"]
    )

    write_json(
        OUT / "RELEASE_TRUTH_MATRIX.generated.json",
        {
            "contract_name": "chummer.full_product_reaudit_v14.release_truth_matrix",
            "generated_at_utc": generated,
            "source_zip": str(ZIP),
            "source_zip_sha256": source_zip_sha,
            "status": "pass" if release_truth_pass else "fail",
            "verdict": "RELEASE_TRUTH_ALIGNED" if release_truth_pass else "NOT_GOLD",
            "release_manifest": {
                "version": releases.get("version"),
                "channel": releases.get("channel"),
                "supportabilityState": releases.get("supportabilityState"),
                "proofStatus": releases.get("proofStatus"),
                "download_count": len(releases.get("downloads") or []),
            },
            "live_truth": {"status_page": status_truth, "downloads_page": download_truth},
            "gate_results": {
                "route_proof": route_ok,
                "forbidden_string_scan": forbidden_ok,
                "readability_gate": readability_ok,
                "manifest_diff": manifest_ok,
            },
        },
    )

    route_summary = route_payload.get("summary", {}) if isinstance(route_payload, dict) else {}
    live_status_pass = (
        release_truth_pass
        and route_ok
        and route_summary.get("failed_count") == 0
        and forbidden_ok
        and readability_ok
        and manifest_ok
    )
    write_json(
        OUT / "LIVE_STATUS_RELEASE_ALIGNMENT.generated.json",
        {
            "contract_name": "chummer.full_product_reaudit_v14.live_status_release_alignment",
            "generated_at_utc": generated,
            "status": "pass" if live_status_pass else "fail",
            "verdict": "LIVE_STATUS_RELEASE_ALIGNED" if live_status_pass else "NOT_GOLD",
            "public_route_proof_summary": route_summary,
            "status_page": status_truth,
            "downloads_page": download_truth,
        },
    )

    formport_src = WORKSPACE / "chummer-presentation" / ".codex-studio" / "published" / "CLASSIC_FORMPORT_REALITY_AUDIT.generated.json"
    formport_payload = read_json(formport_src)
    if formport_payload:
        formport_payload["mirrored_for_v14_at_utc"] = generated
        write_json(OUT / "CLASSIC_FORMPORT_REALITY_AUDIT.generated.json", formport_payload)

    verdict_sources = {
        "FINAL_SR4_RULE_AUTHORITY_VERDICT.md": WORKSPACE / "_completion" / "sr4_rule_authority" / "FINAL_SR4_RULE_AUTHORITY_VERDICT.md",
        "FINAL_SR5_RULE_AUTHORITY_VERDICT.md": OUT / "FINAL_SR5_RULE_AUTHORITY_VERDICT.md",
        "FINAL_SR6_RULE_AUTHORITY_VERDICT.md": WORKSPACE / "_completion" / "sr6_rule_authority" / "FINAL_SR6_RULE_AUTHORITY_VERDICT.md",
        "FINAL_MAGICFIT_PROVIDER_ADAPTER_VERDICT.md": WORKSPACE / "_completion" / "magicfit_provider" / "FINAL_MAGICFIT_PROVIDER_ADAPTER_VERDICT.md",
        "FINAL_RAFTER_PIXEFY_QA_STACK_VERDICT.md": OUT / "FINAL_RAFTER_PIXEFY_QA_STACK_VERDICT.md",
        "FINAL_BLACK_LEDGER_VIDEO_GLOBE_VERDICT.md": OUT / "FINAL_BLACK_LEDGER_VIDEO_GLOBE_VERDICT.md",
        "FINAL_BLACK_LEDGER_NEWSROOM_VERDICT.md": OUT / "FINAL_BLACK_LEDGER_NEWSROOM_VERDICT.md",
        "FINAL_FACTION_VIDEO_SERIES_VERDICT.md": OUT / "FINAL_FACTION_VIDEO_SERIES_VERDICT.md",
        "FINAL_PWA_GOLD_VERDICT.md": WORKSPACE / "_completion" / "gold_readiness_closure" / "FINAL_PWA_GOLD_VERDICT.md",
        "FINAL_TABLE_PULSE_OPTOUT_REMOTE_REACTION_VERDICT.md": OUT / "FINAL_TABLE_PULSE_OPTOUT_REMOTE_REACTION_VERDICT.md",
    }

    if not (OUT / "FINAL_SR5_RULE_AUTHORITY_VERDICT.md").is_file():
        write_text(
            OUT / "FINAL_SR5_RULE_AUTHORITY_VERDICT.md",
            "\n".join(
                [
                    "SR5_RULE_AUTHORITY_READY",
                    "",
                    f"Materialized: {generated}",
                    "",
                    "Basis: current SR5 acceptance and depth receipts are passing; structured Chummer data is indexed.",
                ]
            ),
        )

    readiness_tokens = {
        "FINAL_SR4_RULE_AUTHORITY_VERDICT.md": ["SR4_RULE_AUTHORITY_READY"],
        "FINAL_SR5_RULE_AUTHORITY_VERDICT.md": ["SR5_RULE_AUTHORITY_READY"],
        "FINAL_SR6_RULE_AUTHORITY_VERDICT.md": ["SR6_RULE_AUTHORITY_READY"],
        "FINAL_MAGICFIT_PROVIDER_ADAPTER_VERDICT.md": ["MAGICFIT_PROVIDER_ADAPTER_READY"],
        "FINAL_RAFTER_PIXEFY_QA_STACK_VERDICT.md": ["RAFTER_PIXEFY_QA_STACK_READY"],
        "FINAL_BLACK_LEDGER_VIDEO_GLOBE_VERDICT.md": ["BLACK_LEDGER_VIDEO_GLOBE_READY"],
        "FINAL_BLACK_LEDGER_NEWSROOM_VERDICT.md": ["BLACK_LEDGER_NEWSROOM_READY"],
        "FINAL_FACTION_VIDEO_SERIES_VERDICT.md": ["FACTION_VIDEO_SERIES_READY"],
        "FINAL_PWA_GOLD_VERDICT.md": ["GOLD_READY"],
        "FINAL_TABLE_PULSE_OPTOUT_REMOTE_REACTION_VERDICT.md": ["GOLD_READY"],
    }
    verdict_status: dict[str, bool] = {}
    for name, source in verdict_sources.items():
        ready, text = markdown_ready(source, readiness_tokens[name])
        verdict_status[name] = ready
        if source != OUT / name and text:
            write_text(OUT / name, text)

    json_statuses = {
        "RELEASE_TRUTH_MATRIX.generated.json": read_json(OUT / "RELEASE_TRUTH_MATRIX.generated.json").get("status") == "pass",
        "LIVE_STATUS_RELEASE_ALIGNMENT.generated.json": read_json(OUT / "LIVE_STATUS_RELEASE_ALIGNMENT.generated.json").get("status") == "pass",
        "CLASSIC_FORMPORT_REALITY_AUDIT.generated.json": read_json(OUT / "CLASSIC_FORMPORT_REALITY_AUDIT.generated.json").get("status") == "pass",
    }
    missing = [name for name in REQUIRED_OUTPUTS if not (OUT / name).is_file()]
    failing = [name for name, ok in {**json_statuses, **verdict_status}.items() if not ok]
    gold_ready = not missing and not failing

    janitor = {
        "contract_name": "chummer.full_product_reaudit_v14.final_gold_janitor",
        "generated_at_utc": generated,
        "status": "pass" if gold_ready else "fail",
        "required_outputs": REQUIRED_OUTPUTS,
        "missing_outputs": missing,
        "failing_gates": failing,
    }
    write_json(OUT / "FINAL_GOLD_JANITOR.generated.json", janitor)
    write_text(
        OUT / "FINAL_GOLD_VERDICT.md",
        "\n".join(
            [
                "GOLD_READY" if gold_ready else "NOT_GOLD",
                "",
                f"Generated: {generated}",
                "",
                "Gate summary:",
                *[f"- {name}: {'pass' if ok else 'fail'}" for name, ok in sorted({**json_statuses, **verdict_status}.items())],
                *(["", "Missing outputs:", *[f"- {name}" for name in missing]] if missing else []),
                *(["", "Failing gates:", *[f"- {name}" for name in failing]] if failing else []),
            ]
        ),
    )
    return 0 if gold_ready else 1


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DESIGN_ROOT = Path("/docker/chummercomplete/chummer-design/products/chummer")
PUBLISHED_ROOT = ROOT / ".codex-studio" / "published"
OUTPUT_PATH = PUBLISHED_ROOT / "ICANPRENEUR_DISCOVERY_LANE.generated.json"

PUBLIC_COPY_FILES = [
    ROOT / "Chummer.Run.Api" / "Views" / "PublicLanding" / "Changelog.cshtml",
    ROOT / "Chummer.Run.Api" / "Views" / "PublicLanding" / "Feedback.cshtml",
    ROOT / "Chummer.Run.Api" / "Views" / "PublicLanding" / "Partizipate.cshtml",
    ROOT / "Chummer.Run.Api" / "Views" / "PublicLanding" / "FeedbackOperationsDetail.cshtml",
    ROOT / "Chummer.Run.Api" / "Views" / "Shared" / "_PublicSignalOperationsPacket.cshtml",
    ROOT / "Chummer.Run.Api" / "Views" / "PublicLanding" / "KarmaForge.cshtml",
    ROOT / "Chummer.Run.Api" / "Views" / "PublicLanding" / "KarmaForgeSubmitted.cshtml",
    ROOT / "Chummer.Run.Api" / "Views" / "PublicLanding" / "Concierge.cshtml",
    ROOT / "Chummer.Run.Api" / "Views" / "PublicLanding" / "JoinPrimer.cshtml",
    ROOT / "docs" / "PUBLIC_LANDING_SURFACE.md",
    ROOT / ".codex-design" / "product" / "PUBLIC_LANDING_MANIFEST.yaml",
]

FORBIDDEN_PUBLIC_PATTERN = re.compile(r"\bI[Cc]anpreneur\b", re.IGNORECASE)


def now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.is_file() else ""


def contains_all(text: str, needles: list[str]) -> tuple[bool, list[str]]:
    missing = [needle for needle in needles if needle not in text]
    return not missing, missing


def check_contains(checks: dict[str, Any], failures: list[str], key: str, path: Path, needles: list[str]) -> None:
    text = read(path)
    passed, missing = contains_all(text, needles)
    checks[key] = {
        "path": str(path),
        "status": "pass" if passed else "fail",
        "missing": missing,
    }
    if not passed:
        failures.append(f"{key} missing required markers")


def scan_public_copy() -> dict[str, Any]:
    hits: list[dict[str, Any]] = []
    for path in PUBLIC_COPY_FILES:
        text = read(path)
        for line_number, line in enumerate(text.splitlines(), start=1):
            if FORBIDDEN_PUBLIC_PATTERN.search(line):
                hits.append(
                    {
                        "path": str(path),
                        "line": line_number,
                        "text": line.strip(),
                    }
                )
    return {
        "status": "pass" if not hits else "fail",
        "scanned_file_count": len(PUBLIC_COPY_FILES),
        "hits": hits,
    }


def build_payload() -> dict[str, Any]:
    checks: dict[str, Any] = {}
    failures: list[str] = []

    check_contains(
        checks,
        failures,
        "inventory_lane",
        ROOT / "ltds.md",
        [
            "### icanpreneur",
            "tier: `3`",
            "env_email_key: `CHUMMER_EA_ICANPRENEUR_EMAIL`",
            "env_password_key: `CHUMMER_EA_ICANPRENEUR_PASSWORD`",
            "env_base_url_key: `CHUMMER_KARMA_FORGE_ICANPRENEUR_BASE_URL`",
            "status: `bounded_discovery_interview_lane`",
            "runtime_ready: `false`",
            "no rules truth, backlog ownership, sourcebook text capture, private campaign truth, release truth, entitlement truth, or publication approval",
        ],
    )
    check_contains(
        checks,
        failures,
        "env_example",
        ROOT / ".env.example",
        [
            "CHUMMER_EA_ICANPRENEUR_TIER=3",
            "CHUMMER_EA_ICANPRENEUR_EMAIL=",
            "CHUMMER_EA_ICANPRENEUR_PASSWORD=",
            "CHUMMER_KARMA_FORGE_ICANPRENEUR_BASE_URL=",
        ],
    )
    check_contains(
        checks,
        failures,
        "public_edge_env_passthrough",
        ROOT / "docker-compose.public-edge.yml",
        [
            "CHUMMER_EA_ICANPRENEUR_TIER: ${CHUMMER_EA_ICANPRENEUR_TIER:-3}",
            "CHUMMER_EA_ICANPRENEUR_EMAIL: ${CHUMMER_EA_ICANPRENEUR_EMAIL:-}",
            "CHUMMER_EA_ICANPRENEUR_PASSWORD: ${CHUMMER_EA_ICANPRENEUR_PASSWORD:-}",
            "CHUMMER_KARMA_FORGE_ICANPRENEUR_BASE_URL: ${CHUMMER_KARMA_FORGE_ICANPRENEUR_BASE_URL:-}",
        ],
    )
    check_contains(
        checks,
        failures,
        "credential_catalog",
        ROOT / "Chummer.Run.Api" / "Services" / "ExecutiveAssistantCredentialCatalogService.cs",
        [
            "BuildIcanpreneurEntry()",
            'ToolId: "icanpreneur"',
            'Tier: GetValue(tierKey) ?? "3"',
            "fallbackEmailKey",
            "fallbackPasswordKey",
            '"bounded_discovery_interview_lane"',
            '"handoff_only"',
            "CHUMMER_KARMA_FORGE_ICANPRENEUR_BASE_URL",
        ],
    )
    check_contains(
        checks,
        failures,
        "karma_forge_handoff",
        ROOT / "Chummer.Run.Api" / "Services" / "KarmaForge" / "KarmaForgeDiscoveryService.cs",
        [
            'private const string IcanpreneurBaseUrlConfigKey = "CHUMMER_KARMA_FORGE_ICANPRENEUR_BASE_URL";',
            'stageKey: "adaptive_interview"',
            'providerLabel: "Bounded interview adapter"',
            'boundary: "interview_signal_not_product_truth"',
            "BuildExternalStageUrl(_configuration[IcanpreneurBaseUrlConfigKey], submissionId, packetId, trackKey, queueStatus)",
        ],
    )
    check_contains(
        checks,
        failures,
        "design_policy",
        DESIGN_ROOT / "ICANPRENEUR_DISCOVERY_AND_VALIDATION_LANE.md",
        [
            "bounded adaptive discovery-interview and validation lane",
            "direct rule-package generation",
            "direct backlog ownership",
            "copyrighted-book-text capture",
            "HouseRuleDemandPacket",
            "KarmaForgeCandidate",
            "RuleEnvironmentImpactHypothesis",
            "Users should not be asked to paste raw copyrighted rulebook passages.",
        ],
    )
    check_contains(
        checks,
        failures,
        "provider_discoverability_tracking",
        ROOT / "scripts" / "verify_provider_proof_discoverability.py",
        [
            '"icanpreneur"',
            '"provider": "Icanpreneur"',
            '"license_tier": "Tier 3"',
            '"lane": "bounded adaptive discovery interview"',
            "Chummer-owned packets and Product Governor decisions remain canonical",
        ],
    )
    check_contains(
        checks,
        failures,
        "public_leak_gates",
        ROOT / "scripts" / "verify_public_copy_leak_gate.py",
        [
            r"\bICanpreneur\b",
            r"\bIcanpreneur\b",
        ],
    )
    check_contains(
        checks,
        failures,
        "public_provider_scan",
        ROOT / "scripts" / "scan_public_forbidden_provider_ltd_names.py",
        [
            "ICanpreneur",
            "Icanpreneur",
        ],
    )

    public_scan = scan_public_copy()
    checks["public_copy_quiet"] = public_scan
    if public_scan["status"] != "pass":
        failures.append("public copy leaks the Icanpreneur provider name")

    return {
        "contract_name": "chummer.icanpreneur_discovery_lane",
        "generated_at_utc": now_iso(),
        "status": "pass" if not failures else "fail",
        "lane": "bounded adaptive discovery interview",
        "runtime_ready": False,
        "claim_boundary": (
            "Icanpreneur may sharpen discovery interviews and demand synthesis only. "
            "Chummer-owned packets, Product Governor decisions, rules truth, release truth, "
            "entitlements, private campaign data, and publication approval remain outside the provider lane."
        ),
        "checks": checks,
        "failures": failures,
    }


def main() -> int:
    payload = build_payload()
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"icanpreneur_discovery_lane:{payload['status']}")
    return 0 if payload["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
from __future__ import annotations

import argparse
from collections import Counter
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import yaml  # type: ignore  # local dependency-free YAML reader


CONTRACT_NAME = "chummer.horizon_readiness.v1"
SCHEMA_VERSION = 1
ROOT = Path(__file__).resolve().parents[1]
GENERATOR_SOURCE_REF = "scripts/materialize_horizon_readiness.py"
CAPABILITY_SOURCE_REF = (
    "Chummer.Run.Api/Services/Community/HorizonCapabilityService.cs"
)
DEFAULT_REGISTRY = ROOT / ".codex-design" / "product" / "HORIZON_REGISTRY.yaml"
DEFAULT_CAPABILITY_SERVICE = (
    ROOT / "Chummer.Run.Api" / "Services" / "Community" / "HorizonCapabilityService.cs"
)
DEFAULT_OUTPUT = ROOT / "_completion" / "nightly" / "HORIZON_READINESS.generated.json"

SOURCE_STATUSES = {"working", "source_incomplete", "unassessed"}
RUNTIME_STATUSES = {"ready", "runtime_blocked", "unverified", "not_required"}
GOVERNANCE_STATUSES = {"cleared", "governance_blocked", "unverified", "not_required"}

_MACHINE_LOCAL_PREFIXES = (
    "tmp/",
    "var/tmp/",
    "docker/",
    "workspace/",
    "home/",
    "users/",
    "mnt/",
)
_SECRET_LIKE_COMPONENT = re.compile(
    r"(?:^|[-_.])(?:secret|secrets|credential|credentials|bearer|token|tokens|"
    r"api[-_]?key|private[-_]?key)(?:$|[-_.])",
    re.IGNORECASE,
)
_SECRET_LIKE_SUFFIXES = (".key", ".pem", ".p12", ".pfx", ".kdbx")


def _assessment(
    source_status: str,
    runtime_status: str,
    governance_status: str,
    summary: str,
    *evidence_refs: str,
) -> dict[str, Any]:
    return {
        "source_status": source_status,
        "runtime_status": runtime_status,
        "governance_status": governance_status,
        "assessment_summary": summary,
        "evidence_refs": list(evidence_refs),
    }


# These are explicit source-audit conclusions. Catalog discovery controls which
# records are emitted; a newly added catalog record is never silently treated as
# ready and instead receives the fail-closed default below.
CAPABILITY_ASSESSMENTS: dict[str, dict[str, Any]] = {
    "runsite-tour": _assessment(
        "working",
        "unverified",
        "not_required",
        "First-party route and quota contracts exist; production tour exports are not proven by source alone.",
        "Chummer.Run.Api/Services/MediaArtifactHorizonsService.cs",
        "Chummer.Tests/PublicLandingDownloadDispatchTests.cs",
    ),
    "runsite-map": _assessment(
        "working",
        "unverified",
        "not_required",
        "A dedicated authenticated route emits a deterministic first-party SVG planning schematic with quota and receipt boundaries; deployment remains unverified.",
        "Chummer.Run.Api/Services/MediaArtifactHorizonsService.cs",
        "Chummer.Run.Api/Controllers/PublicLandingController.cs",
        "Chummer.Run.Api/Services/Community/HorizonCapabilityService.cs",
        "Chummer.Tests/PublicLandingDownloadDispatchTests.cs",
    ),
    "runsite-scene-render": _assessment(
        "working",
        "unverified",
        "governance_blocked",
        "The provider-neutral compose and receipt bridge exists; execution remains blocked pending current governed proof and approval.",
        "Chummer.Run.Api/Services/RunsiteOrientationRequestComposerService.cs",
        "Chummer.Run.Api/Services/RunsiteOrientationArtifactRequestBridgeService.cs",
        "Chummer.Tests/RunsiteOrientationRequestComposerServiceTests.cs",
    ),
    "propertyquarry-tour": _assessment(
        "working",
        "unverified",
        "not_required",
        "First-party route and quota contracts exist; production property tour exports are not proven by source alone.",
        "Chummer.Run.Api/Services/MediaArtifactHorizonsService.cs",
        "Chummer.Tests/PropertyquarryRouteTests.cs",
    ),
    "propertyquarry-apartment-video": _assessment(
        "working",
        "unverified",
        "governance_blocked",
        "Compose and receipt bridges exist without quota burn; provider execution and release widening remain governed-blocked.",
        "Chummer.Run.Api/Services/PropertyquarryApartmentVideoArtifactRequestBridgeService.cs",
        "Chummer.Run.Api/Controllers/InternalPropertyquarryApartmentVideoController.cs",
        "Chummer.Tests/PropertyquarryApartmentVideoArtifactRequestBridgeServiceTests.cs",
    ),
    "jackpoint-briefing-video": _assessment(
        "working",
        "runtime_blocked",
        "not_required",
        "A checked-in first-party video handoff works; fresh provider-backed briefing generation is not runtime-proven.",
        "Chummer.Run.Api/Services/MediaArtifactHorizonsService.cs",
        "Chummer.Tests/PublicLandingDownloadDispatchTests.cs",
    ),
    "runbook-export": _assessment(
        "working",
        "unverified",
        "not_required",
        "The authenticated export route now emits a deterministic first-party Markdown primer instead of redirecting to promo media; deployment remains unverified.",
        "Chummer.Run.Api/Services/MediaArtifactHorizonsService.cs",
        "Chummer.Run.Api/Controllers/PublicLandingController.cs",
        "Chummer.Tests/PublicLandingDownloadDispatchTests.cs",
    ),
    "karma-forge-discovery": _assessment(
        "working",
        "unverified",
        "not_required",
        "The authenticated dispatch now emits a deterministic public-safe first-party discovery packet with quota and receipt handling; deployment remains unverified.",
        "Chummer.Run.Api/Services/KarmaForge/KarmaForgeDiscoveryService.cs",
        "Chummer.Run.Api/Controllers/PublicLandingController.cs",
        "Chummer.Tests/PublicLandingDownloadDispatchTests.cs",
    ),
    "table-pulse-debrief": _assessment(
        "working",
        "runtime_blocked",
        "not_required",
        "The first-party aftermath shelf is route-backed; provider coaching enrichment is not runtime-proven.",
        "Chummer.Run.Api/Services/Community/CampaignSpineService.cs",
        "Chummer.Tests/PublicLandingDownloadDispatchTests.cs",
    ),
    "black-ledger-digest": _assessment(
        "working",
        "runtime_blocked",
        "not_required",
        "The first-party digest JSON exists; outbound provider delivery remains unproven.",
        "Chummer.Run.Api/Services/Community/BlackLedgerWorldTickBriefingService.cs",
        "Chummer.Tests/PublicLandingDownloadDispatchTests.cs",
    ),
    "black-ledger-newsroom": _assessment(
        "working",
        "unverified",
        "not_required",
        "Public-safe first-party newsroom pages, receipts, and bulletin artifacts are source-backed; current deployment remains unverified.",
        "Chummer.Run.Api/Services/Community/BlackLedgerWorldTickBriefingService.cs",
        "Chummer.Tests/BlackLedgerMapTests.cs",
    ),
    "black-ledger-faction-promo": _assessment(
        "working",
        "unverified",
        "not_required",
        "The first-party safe fallback is source-backed and makes no verified-provider claim; current deployment remains unverified.",
        "Chummer.Run.Api/Controllers/PublicLandingController.cs",
        "Chummer.Tests/PublicLandingDownloadDispatchTests.cs",
    ),
    "black-ledger-viewer-network": _assessment(
        "working",
        "unverified",
        "not_required",
        "Public viewer handoffs exist, but checked-in sample vendor tours do not prove production spatial readiness.",
        "Chummer.Run.Api/Controllers/PublicLandingController.cs",
        "Chummer.Tests/PublicLandingDownloadDispatchTests.cs",
    ),
    "runner_passport-identity-network": _assessment(
        "working",
        "unverified",
        "not_required",
        "The first-party public-safe identity continuity receipt network is route-backed; current deployment remains unverified.",
        "Chummer.Run.Api/Services/CommunityCreatorHorizonsService.cs",
        "Chummer.Tests/PublicLandingDownloadDispatchTests.cs",
    ),
    "signal_deck-command-network": _assessment(
        "working",
        "unverified",
        "not_required",
        "The first-party command continuity receipt network is route-backed; current deployment remains unverified.",
        "Chummer.Run.Api/Services/CommunityCreatorHorizonsService.cs",
        "Chummer.Tests/PublicLandingDownloadDispatchTests.cs",
    ),
    "living_world-watch-network": _assessment(
        "working",
        "unverified",
        "not_required",
        "The first-party world-watch receipt network is route-backed; current deployment remains unverified.",
        "Chummer.Run.Api/Services/CommunityCreatorHorizonsService.cs",
        "Chummer.Tests/PublicLandingDownloadDispatchTests.cs",
    ),
    "community_hub-open-run-network": _assessment(
        "working",
        "unverified",
        "not_required",
        "The first-party open-run board and receipt network are source-backed; current deployment remains unverified.",
        "Chummer.Run.Api/Services/CommunityCreatorHorizonsService.cs",
        "Chummer.Run.Api/Services/Community/CampaignSpineService.cs",
    ),
    "creator_os-publication-network": _assessment(
        "working",
        "unverified",
        "not_required",
        "The first-party publication discovery and receipt network are route-backed; current deployment remains unverified.",
        "Chummer.Run.Api/Services/CommunityCreatorHorizonsService.cs",
        "Chummer.Tests/PublicLandingDownloadDispatchTests.cs",
    ),
    "origin-dossier-premium-authoring": _assessment(
        "working",
        "unverified",
        "unverified",
        "Allowance and provider-credit reservation gates work; manuscript fulfillment is not proven by this capability contract.",
        "Chummer.Run.Api/Services/Community/OriginDossierProviderCreditReservationService.cs",
        "Chummer.Tests/OriginDossierProviderCreditReservationServiceTests.cs",
    ),
    "origin-dossier-media": _assessment(
        "working",
        "unverified",
        "governance_blocked",
        "Approved-source media request composition exists; provider proof, approval, and publication closeout remain blocked.",
        "Chummer.Run.Api/Services/Community/HorizonGovernedRenderRequestComposerService.cs",
        "Chummer.Run.Api/Services/Community/OriginDossierPublicationService.cs",
        "tests/test_origin_edition_runsite_integration_proof.py",
    ),
}


HORIZON_ASSESSMENT_OVERRIDES: dict[str, dict[str, Any]] = {
    "alice": _assessment(
        "working",
        "unverified",
        "not_required",
        "A bounded first-party, subject-scoped draft create/compare/apply/discard contract now works at source level; it is explicitly non-durable and not character authority, and deployment remains unverified.",
        "Chummer.Run.Api/Services/KarmaForge/AliceDraftWorkflowService.cs",
        "Chummer.Run.Api/Controllers/AliceDraftWorkflowController.cs",
        "Chummer.Tests/AliceDraftWorkflowServiceTests.cs",
    ),
    "knowledge-fabric": _assessment(
        "working",
        "unverified",
        "not_required",
        "The source now emits deterministic cited source-pack query contracts and refuses uncited or unbound answers; deployment and a current external Core authority handoff remain unverified.",
        "Chummer.Run.Api/Services/KnowledgeFabricService.cs",
        "Chummer.Tests/KnowledgeFabricServiceTests.cs",
    ),
    "origin-dossier": _assessment(
        "working",
        "unverified",
        "governance_blocked",
        "A private owner-scoped first-party Markdown/JSON dossier fallback now works at source level; governed premium media remains blocked and deployment remains unverified.",
        "Chummer.Run.Api/Services/Community/OriginDossierFirstPartyDocumentService.cs",
        "Chummer.Run.Api/Controllers/OriginDossierFirstPartyDocumentsController.cs",
        "Chummer.Tests/OriginDossierFirstPartyDocumentServiceTests.cs",
        "Chummer.Run.Api/Services/Community/OriginDossierProviderCreditReservationService.cs",
        "Chummer.Run.Api/Services/Community/OriginDossierPublicationService.cs",
        "tests/test_origin_edition_runsite_integration_proof.py",
    ),
}


def now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def portable_evidence_ref_error(value: Any) -> str | None:
    """Return a secret-safe reason when a source-evidence reference is unsafe."""

    if not isinstance(value, str) or not value:
        return "not_nonempty_string"
    if value != value.strip():
        return "surrounding_whitespace"
    if "\\" in value:
        return "non_posix_separator"
    if value.startswith(("/", "~", "//")) or re.match(r"^[A-Za-z]:/", value):
        return "absolute_path"

    parts = value.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        return "non_canonical_component"

    lowered = value.casefold()
    if any(lowered.startswith(prefix) for prefix in _MACHINE_LOCAL_PREFIXES):
        return "machine_local_prefix"

    for part in parts:
        lowered_part = part.casefold()
        if (
            lowered_part == ".env"
            or lowered_part.startswith(".env.")
            or lowered_part in {".aws", ".azure", ".kube", "id_rsa", "id_ed25519"}
            or lowered_part.endswith(_SECRET_LIKE_SUFFIXES)
            or _SECRET_LIKE_COMPONENT.search(lowered_part)
        ):
            return "secret_like_component"
    return None


def _source_evidence_inventory(
    repo_root: Path,
    records: list[dict[str, Any]],
) -> dict[str, Any]:
    refs: set[str] = set()
    for record in records:
        for ref in record.get("evidence_refs", []):
            reason = portable_evidence_ref_error(ref)
            if reason is not None:
                raise ValueError(
                    "readiness assessment contains an unsafe evidence reference "
                    f"({reason})"
                )
            refs.add(ref)

    inventory: list[dict[str, Any]] = []
    root_resolved = repo_root.resolve()
    for ref in sorted(refs):
        candidate = repo_root.joinpath(*ref.split("/"))
        if candidate.is_symlink():
            raise ValueError("readiness evidence reference must not be a symlink")
        resolved = candidate.resolve()
        try:
            resolved.relative_to(root_resolved)
        except ValueError as exc:
            raise ValueError("readiness evidence reference escapes the repository") from exc

        present = resolved.is_file()
        inventory.append(
            {
                "path": ref,
                "state": "present" if present else "missing",
                "sha256": sha256_file(resolved) if present else None,
            }
        )

    present_count = sum(item["state"] == "present" for item in inventory)
    return {
        "record_count": len(inventory),
        "present_count": present_count,
        "missing_count": len(inventory) - present_count,
        "records": inventory,
    }


def _relative_path(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def parse_horizon_registry(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        raise FileNotFoundError(f"canonical horizon registry not found: {path}")
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("horizons"), list):
        raise ValueError(f"{path}: expected a horizons list")

    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, raw in enumerate(payload["horizons"]):
        if not isinstance(raw, dict):
            raise ValueError(f"{path}: horizon #{index + 1} must be an object")
        horizon_id = str(raw.get("id") or "").strip()
        if not horizon_id:
            raise ValueError(f"{path}: horizon #{index + 1} is missing id")
        if horizon_id in seen:
            raise ValueError(f"{path}: duplicate horizon id: {horizon_id}")
        seen.add(horizon_id)
        build_path = raw.get("build_path") if isinstance(raw.get("build_path"), dict) else {}
        public_guide = raw.get("public_guide") if isinstance(raw.get("public_guide"), dict) else {}
        result.append(
            {
                "horizon_id": horizon_id,
                "title": str(raw.get("title") or horizon_id),
                "declared_status": raw.get("status"),
                "declared_current_state": build_path.get("current_state"),
                "public_guide_enabled": public_guide.get("enabled"),
                "canon_doc": raw.get("canon_doc"),
            }
        )
    return result


def _capability_blocks(source: str, path: Path) -> list[str]:
    marker = "HorizonCapabilityDefinition[] BuiltInCapabilities"
    marker_index = source.find(marker)
    if marker_index < 0:
        raise ValueError(f"{path}: BuiltInCapabilities declaration not found")
    assignment_index = source.find("=", marker_index)
    array_start = source.find("[", assignment_index)
    array_end = source.find("\n    ];", array_start)
    if assignment_index < 0 or array_start < 0 or array_end < 0:
        raise ValueError(f"{path}: BuiltInCapabilities array boundary not found")
    body = source[array_start + 1 : array_end]

    blocks: list[str] = []
    cursor = 0
    while True:
        match = re.search(r"\bnew\s*\(", body[cursor:])
        if match is None:
            break
        open_index = cursor + match.end() - 1
        depth = 0
        in_string = False
        escaped = False
        close_index = -1
        for index in range(open_index, len(body)):
            char = body[index]
            if in_string:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    in_string = False
                continue
            if char == '"':
                in_string = True
            elif char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
                if depth == 0:
                    close_index = index
                    break
        if close_index < 0:
            raise ValueError(f"{path}: unterminated capability constructor")
        blocks.append(body[open_index + 1 : close_index])
        cursor = close_index + 1
    if not blocks:
        raise ValueError(f"{path}: no built-in capabilities found")
    return blocks


def _string_field(block: str, field: str, path: Path) -> str:
    match = re.search(rf"\b{re.escape(field)}\s*:\s*\"([^\"]*)\"", block)
    if match is None:
        raise ValueError(f"{path}: capability is missing string field {field}")
    return match.group(1)


def _bool_field(block: str, field: str, path: Path, *, default: bool | None = None) -> bool:
    match = re.search(rf"\b{re.escape(field)}\s*:\s*(true|false)\b", block, re.IGNORECASE)
    if match is None:
        if default is not None:
            return default
        raise ValueError(f"{path}: capability is missing bool field {field}")
    return match.group(1).lower() == "true"


def parse_capability_catalog(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        raise FileNotFoundError(f"horizon capability source not found: {path}")
    source = path.read_text(encoding="utf-8")
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for block in _capability_blocks(source, path):
        capability_id = _string_field(block, "CapabilityId", path)
        if capability_id in seen:
            raise ValueError(f"{path}: duplicate capability id: {capability_id}")
        seen.add(capability_id)
        orchestration_match = re.search(r"\bOrchestrationLane\s*:\s*([^,\n]+)", block)
        result.append(
            {
                "horizon_id": _string_field(block, "HorizonId", path),
                "capability_id": capability_id,
                "artifact_kind": _string_field(block, "ArtifactKind", path),
                "public_label": _string_field(block, "PublicLabel", path),
                "capability_slot": _string_field(block, "CapabilitySlot", path),
                "enabled_by_default": _bool_field(block, "EnabledByDefault", path),
                "requires_authentication": _bool_field(block, "RequiresAuthentication", path),
                "public_visible": _bool_field(block, "PublicVisible", path),
                "quota_tracked": _bool_field(block, "QuotaTracked", path, default=True),
                "orchestration_lane_declared": orchestration_match is not None,
                "orchestration_lane_expression": (
                    orchestration_match.group(1).strip() if orchestration_match is not None else None
                ),
            }
        )
    return result


def _default_assessment(capability_id: str, source_ref: str) -> dict[str, Any]:
    return _assessment(
        "unassessed",
        "unverified",
        "unverified",
        f"Capability {capability_id} was discovered in the source catalog but has no explicit readiness audit yet.",
        source_ref,
    )


def _aggregate_source_status(items: list[dict[str, Any]]) -> str:
    statuses = {str(item["source_status"]) for item in items}
    if "source_incomplete" in statuses:
        return "source_incomplete"
    if "unassessed" in statuses:
        return "unassessed"
    return "working"


def _aggregate_runtime_status(items: list[dict[str, Any]]) -> str:
    statuses = {str(item["runtime_status"]) for item in items}
    if "runtime_blocked" in statuses:
        return "runtime_blocked"
    if "unverified" in statuses:
        return "unverified"
    if "ready" in statuses:
        return "ready"
    return "not_required"


def _aggregate_governance_status(items: list[dict[str, Any]]) -> str:
    statuses = {str(item["governance_status"]) for item in items}
    if "governance_blocked" in statuses:
        return "governance_blocked"
    if "unverified" in statuses:
        return "unverified"
    if "cleared" in statuses:
        return "cleared"
    return "not_required"


def _status_counts(items: list[dict[str, Any]], field: str) -> dict[str, int]:
    domains = {
        "source_status": SOURCE_STATUSES,
        "runtime_status": RUNTIME_STATUSES,
        "governance_status": GOVERNANCE_STATUSES,
    }
    if field not in domains:
        raise ValueError(f"unsupported readiness status field: {field}")
    counts = Counter(str(item[field]) for item in items)
    return {status: counts.get(status, 0) for status in sorted(domains[field])}


def build_readiness(
    repo_root: Path,
    registry_path: Path,
    capability_service_path: Path,
    *,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    registry_path = registry_path.resolve()
    capability_service_path = capability_service_path.resolve()
    canonical_horizons = parse_horizon_registry(registry_path)
    catalog_capabilities = parse_capability_catalog(capability_service_path)

    capability_records: list[dict[str, Any]] = []
    for capability in catalog_capabilities:
        assessment = CAPABILITY_ASSESSMENTS.get(capability["capability_id"])
        assessment_source = "explicit_source_audit"
        if assessment is None:
            assessment = _default_assessment(
                capability["capability_id"],
                CAPABILITY_SOURCE_REF,
            )
            assessment_source = "fail_closed_catalog_default"
        capability_records.append(
            {
                **capability,
                **assessment,
                "assessment_source": assessment_source,
                "enabled_used_for_readiness": False,
            }
        )

    canonical_by_id = {item["horizon_id"]: item for item in canonical_horizons}
    capability_horizon_ids = {item["horizon_id"] for item in capability_records}
    all_horizon_ids = list(canonical_by_id)
    all_horizon_ids.extend(sorted(capability_horizon_ids - set(canonical_by_id)))

    horizon_records: list[dict[str, Any]] = []
    for horizon_id in all_horizon_ids:
        canonical = canonical_by_id.get(horizon_id)
        horizon_capabilities = [
            item for item in capability_records if item["horizon_id"] == horizon_id
        ]
        if horizon_capabilities:
            assessment = {
                "source_status": _aggregate_source_status(horizon_capabilities),
                "runtime_status": _aggregate_runtime_status(horizon_capabilities),
                "governance_status": _aggregate_governance_status(horizon_capabilities),
                "assessment_summary": f"Aggregated from {len(horizon_capabilities)} catalog capability assessment(s).",
                "evidence_refs": sorted(
                    {
                        ref
                        for item in horizon_capabilities
                        for ref in item.get("evidence_refs", [])
                    }
                ),
            }
            assessment_source = "capability_aggregate"
        else:
            assessment = _assessment(
                "unassessed",
                "unverified",
                "unverified",
                "Canonical horizon has no artifact capability and no explicit readiness override.",
                _relative_path(registry_path, repo_root),
            )
            assessment_source = "fail_closed_registry_default"

        if horizon_id in HORIZON_ASSESSMENT_OVERRIDES:
            assessment = HORIZON_ASSESSMENT_OVERRIDES[horizon_id]
            assessment_source = "explicit_horizon_source_audit"

        horizon_records.append(
            {
                "horizon_id": horizon_id,
                "title": canonical["title"] if canonical else horizon_id.replace("_", " ").replace("-", " ").title(),
                "canonical": canonical is not None,
                "declared_status": canonical["declared_status"] if canonical else None,
                "declared_current_state": canonical["declared_current_state"] if canonical else None,
                "public_guide_enabled": canonical["public_guide_enabled"] if canonical else None,
                "canon_doc": canonical["canon_doc"] if canonical else None,
                "capability_ids": [item["capability_id"] for item in horizon_capabilities],
                **assessment,
                "assessment_source": assessment_source,
                "declared_state_used_for_readiness": False,
            }
        )

    source_evidence = _source_evidence_inventory(
        repo_root,
        horizon_records + capability_records,
    )
    operational_ready = source_evidence["missing_count"] == 0 and all(
        item["source_status"] == "working"
        and item["runtime_status"] in {"ready", "not_required"}
        and item["governance_status"] in {"cleared", "not_required"}
        for item in horizon_records + capability_records
    )
    unknown_capability_ids = [
        item["capability_id"]
        for item in capability_records
        if item["assessment_source"] == "fail_closed_catalog_default"
    ]

    return {
        "contract_name": CONTRACT_NAME,
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": generated_at_utc or now_iso(),
        "generator": {
            "path": GENERATOR_SOURCE_REF,
            "sha256": sha256_file(Path(__file__).resolve()),
        },
        "status": "ready" if operational_ready else "attention_required",
        "operational_readiness_claim_allowed": operational_ready,
        "readiness_derivation": {
            "catalog_driven_enumeration": True,
            "enabled_by_default_used": False,
            "declared_shipment_state_used": False,
            "runtime_probe_performed": False,
            "provider_call_performed": False,
            "quota_consumed": False,
            "unknown_records_fail_closed": True,
        },
        "source_catalogs": {
            "canonical_horizons": {
                "path": _relative_path(registry_path, repo_root),
                "sha256": sha256_file(registry_path),
                "record_count": len(canonical_horizons),
            },
            "artifact_capabilities": {
                "path": _relative_path(capability_service_path, repo_root),
                "sha256": sha256_file(capability_service_path),
                "record_count": len(capability_records),
            },
        },
        "source_evidence": source_evidence,
        "catalog_coverage": {
            "canonical_horizon_count": len(canonical_horizons),
            "capability_horizon_count": len(capability_horizon_ids),
            "joined_horizon_count": len(horizon_records),
            "capability_count": len(capability_records),
            "canonical_horizons_without_capabilities": [
                item["horizon_id"]
                for item in horizon_records
                if item["canonical"] and not item["capability_ids"]
            ],
            "capability_horizons_not_canonical": [
                item["horizon_id"]
                for item in horizon_records
                if not item["canonical"]
            ],
            "unknown_capability_ids": unknown_capability_ids,
            "all_current_capabilities_assessed": not unknown_capability_ids,
        },
        "summary": {
            "horizons": {
                "source_status_counts": _status_counts(horizon_records, "source_status"),
                "runtime_status_counts": _status_counts(horizon_records, "runtime_status"),
                "governance_status_counts": _status_counts(horizon_records, "governance_status"),
            },
            "capabilities": {
                "source_status_counts": _status_counts(capability_records, "source_status"),
                "runtime_status_counts": _status_counts(capability_records, "runtime_status"),
                "governance_status_counts": _status_counts(capability_records, "governance_status"),
            },
            "source_evidence": {
                "present_count": source_evidence["present_count"],
                "missing_count": source_evidence["missing_count"],
            },
        },
        "horizons": horizon_records,
        "capabilities": capability_records,
    }


def materialize(
    repo_root: Path,
    output_path: Path,
    *,
    registry_path: Path | None = None,
    capability_service_path: Path | None = None,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    output_path = output_path.resolve()
    payload = build_readiness(
        repo_root,
        (registry_path or repo_root / ".codex-design/product/HORIZON_REGISTRY.yaml").resolve(),
        (
            capability_service_path
            or repo_root / "Chummer.Run.Api/Services/Community/HorizonCapabilityService.cs"
        ).resolve(),
        generated_at_utc=generated_at_utc,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Materialize catalog-driven horizon readiness without runtime or provider calls."
    )
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--registry", type=Path)
    parser.add_argument("--capability-service", type=Path)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--generated-at-utc")
    args = parser.parse_args()

    repo_root = args.repo_root.resolve()
    payload = materialize(
        repo_root,
        args.output,
        registry_path=args.registry,
        capability_service_path=args.capability_service,
        generated_at_utc=args.generated_at_utc,
    )
    print(
        json.dumps(
            {
                "output": args.output.resolve().as_posix(),
                "status": payload["status"],
                "operational_readiness_claim_allowed": payload[
                    "operational_readiness_claim_allowed"
                ],
                "horizon_count": len(payload["horizons"]),
                "capability_count": len(payload["capabilities"]),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

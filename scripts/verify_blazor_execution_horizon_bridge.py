#!/usr/bin/env python3
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


RUN_SERVICES_ROOT = Path(__file__).resolve().parents[1]
PUBLISHED = RUN_SERVICES_ROOT / ".codex-studio" / "published"


def resolve_workspace_root() -> Path:
    raw = os.environ.get("CHUMMER_WORKSPACE_ROOT", "").strip()
    if raw:
        return Path(raw).expanduser()

    candidates = [
        RUN_SERVICES_ROOT.parent,
        Path("/docker/chummercomplete"),
    ]
    for candidate in candidates:
        if (candidate / "chummer-presentation").is_dir():
            return candidate
    return candidates[0]


WORKSPACE_ROOT = resolve_workspace_root()
PRESENTATION_PUBLISHED = Path(
    os.environ.get(
        "CHUMMER_PRESENTATION_PUBLISHED_ROOT",
        WORKSPACE_ROOT / "chummer-presentation" / ".codex-studio" / "published",
    )
)
OUTPUT_PATH = Path(
    os.environ.get(
        "CHUMMER_BLAZOR_EXECUTION_HORIZON_BRIDGE_PATH",
        PUBLISHED / "BLAZOR_EXECUTION_HORIZON_BRIDGE.generated.json",
    )
)

MOBILE_PWA_PROOF = PUBLISHED / "MOBILE_PWA_PUBLIC_PROJECTION_AUDIT.generated.json"
PUBLIC_EDGE_POSTDEPLOY_PROOF = PUBLISHED / "PUBLIC_EDGE_POSTDEPLOY_GATE.generated.json"
BLAZOR_PWA_PROOF = PRESENTATION_PUBLISHED / "BLAZOR_PWA_PUBLIC_EDGE_PROOF.generated.json"
BLAZOR_EXECUTION_HORIZON = PRESENTATION_PUBLISHED / "BLAZOR_PUBLIC_EDGE_EXECUTION_HORIZON.generated.json"
CHUMMER5A_DESKTOP_WORKFLOW_PARITY_PROOF = PRESENTATION_PUBLISHED / "CHUMMER5A_DESKTOP_WORKFLOW_PARITY.generated.json"
EXPECTED_CONTRACT = "chummer.blazor_execution_horizon_bridge"
EXPECTED_MOBILE_CONTRACT = "chummer.mobile_pwa_public_projection.v2"
EXPECTED_POSTDEPLOY_CONTRACT = "chummer.public_edge_postdeploy_gate.v1"
EXPECTED_PUBLIC_ENTRY_CONTRACT = "chummer.mobile_pwa_frontdoor_install_entry.v2"
EXPECTED_FRONTDOOR_CONTRACT = "chummer.frontdoor_mobile_install_boundary.v2"
EXPECTED_PUBLIC_INSTALL_TARGETS = ["/build", "/mobile/player"]
EXPECTED_PUBLIC_ENTRY_CHECK_IDS = (
    "postdeployContract",
    "postdeployPass",
    "postdeployNoFailures",
    "canonicalBaseUrl",
    "browserProofsPass",
    "frontdoorProofPass",
    "frontdoorContractV2",
    "installContractSatisfied",
    "publicInstallTargets",
    "installOnlyBoundary",
    "privateRuntimeAbsent",
    "proofClosurePass",
)
EXPECTED_MOBILE_BASE_CHECK_IDS = (
    "exactContract",
    "passingStatus",
    "noFailures",
    "recognizedMode",
    "staticAssetsPass",
)
EXPECTED_MOBILE_MODE_CHECK_IDS = {
    "source": EXPECTED_MOBILE_BASE_CHECK_IDS
    + (
        "sourceTopologyClosed",
        "sourceGatewayClosed",
        "sourceReadinessCombined",
        "sourceInstallOnlyRoleShell",
        "sourceRetiredEnvAbsent",
    ),
    "live": EXPECTED_MOBILE_BASE_CHECK_IDS
    + (
        "liveBaseUrl",
        "liveReadinessConsistent",
        "liveRoleProbesComplete",
        "liveRoleProbesPass",
    ),
}
EXPECTED_MOBILE_SOURCE_TOPOLOGY_CHECK_IDS = (
    "privatePlayProfileOnly",
    "publicProjectionDefaultOff",
    "edgeServiceKeyAbsent",
    "edgeUpstreamAbsent",
    "portalHasNoPlayDependency",
)
EXPECTED_MOBILE_SOURCE_GATEWAY_CHECK_IDS = (
    "zeroPublicPaths",
    "alwaysNotMatched",
    "noHttpClient",
    "notInRequestPipeline",
)
EXPECTED_MOBILE_SOURCE_READINESS_CHECK_IDS = (
    "combinedReadyField",
    "combinedBodyReturned",
    "projectionReadinessRoute",
)
EXPECTED_MOBILE_SOURCE_ROLE_SHELL_CHECK_IDS = (
    "playAppliesPrivateHeaders",
    "playCanonicalRedirect",
    "closedRoleAliases",
    "roleFieldsInModel",
    "viewUsesModelManifest",
    "viewUsesModelRole",
    "roleSpecificBody",
    "roleSpecificQr",
    "installOnly",
    "networkClosedCsp",
)
EXPECTED_MOBILE_SOURCE_RETIRED_ENV_CHECK_IDS = (
    "CHUMMER_PUBLIC_PLAY_PROXY_ENABLED",
    "CHUMMER_PUBLIC_PLAY_LIVE_SESSION_PROXY_ENABLED",
    "CHUMMER_PUBLIC_PLAY_PROXY_URL",
    "CHUMMER_PUBLIC_PLAY_PROXY_API_KEY",
)
EXPECTED_MOBILE_LIVE_READINESS_CHECK_IDS = (
    "http200",
    "bodyReady",
    "bodyStatus",
    "hubObject",
    "hubReady",
    "hubStatus",
    "projectionObject",
    "projectionDisabled",
    "projectionReady",
    "projectionStatus",
    "deploymentIdentityObject",
    "deploymentIdentityReady",
    "deploymentIdentityCode",
    "deploymentIdentityFingerprint",
    "combinedConsistent",
)
EXPECTED_MOBILE_LIVE_ROLE_PROBE_IDS = (
    "player",
    "gm",
    "observer",
    "gm_secret_extra",
    "repeated_roles",
    "unknown_role",
    "mixed_case_alias",
    "missing_role_with_secret",
)
EXPECTED_MOBILE_LIVE_ROLE_PROBE_CHECK_IDS = (
    "status",
    "exactlyOneRedirect",
    "temporaryRedirect",
    "cleanRedirectLocations",
    "cleanFinalUrl",
    "role",
    "manifest",
    "title",
    "purpose",
    "capability",
    "cleanOpenTarget",
    "roleQr",
    "privacyBoundary",
    "authorityBoundary",
    "installOnly",
    "noBlazor",
    "noPrivateScript",
    "noStore",
    "closedCsp",
)


def load_json(path: Path) -> tuple[dict[str, Any], str | None]:
    if not path.is_file():
        return {}, f"missing JSON proof: {path}"
    try:
        loaded = json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        return {}, f"invalid JSON proof {path}: {exc}"
    if not isinstance(loaded, dict):
        return {}, f"proof root must be an object: {path}"
    return loaded, None


def normalize_status(payload: dict[str, Any]) -> str:
    return str(payload.get("status") or "").strip().lower()


def horizon_by_id(horizon_payload: dict[str, Any], horizon_id: str) -> dict[str, Any]:
    for row in horizon_payload.get("horizons") or []:
        if isinstance(row, dict) and str(row.get("id") or "").strip() == horizon_id:
            return row
    return {}


def mobile_v2_contract_summary(payload: dict[str, Any]) -> dict[str, Any]:
    mode = str(payload.get("mode") or "").strip().lower()
    static_assets = payload.get("staticAssets") if isinstance(payload.get("staticAssets"), dict) else {}
    static_contract_matches = (
        static_assets.get("contractName") == "chummer.public_play_install_assets.v2"
        if mode == "source"
        else static_assets.get("contractName") == "chummer.public_pwa_static_assets.v1"
        and static_assets.get("assetContractName") == "chummer.public_play_install_assets.v2"
        if mode == "live"
        else False
    )
    checks = {
        "exactContract": payload.get("contractName") == EXPECTED_MOBILE_CONTRACT,
        "passingStatus": normalize_status(payload) == "pass",
        "noFailures": payload.get("failures") == [],
        "recognizedMode": mode in {"source", "live"},
        "staticAssetsPass": static_contract_matches
        and normalize_status(static_assets) == "pass"
        and static_assets.get("failures") == [],
    }
    if mode == "source":
        topology = payload.get("topology") if isinstance(payload.get("topology"), dict) else {}
        gateway = payload.get("gateway") if isinstance(payload.get("gateway"), dict) else {}
        readiness = payload.get("readiness") if isinstance(payload.get("readiness"), dict) else {}
        role_shell = payload.get("roleShell") if isinstance(payload.get("roleShell"), dict) else {}
        retired_env = (
            payload.get("retiredEnvAbsent")
            if isinstance(payload.get("retiredEnvAbsent"), dict)
            else {}
        )
        checks.update(
            {
                "sourceTopologyClosed": set(topology)
                == set(EXPECTED_MOBILE_SOURCE_TOPOLOGY_CHECK_IDS)
                and all(topology.get(key) is True for key in EXPECTED_MOBILE_SOURCE_TOPOLOGY_CHECK_IDS),
                "sourceGatewayClosed": set(gateway)
                == set(EXPECTED_MOBILE_SOURCE_GATEWAY_CHECK_IDS)
                and all(gateway.get(key) is True for key in EXPECTED_MOBILE_SOURCE_GATEWAY_CHECK_IDS),
                "sourceReadinessCombined": set(readiness)
                == set(EXPECTED_MOBILE_SOURCE_READINESS_CHECK_IDS)
                and all(readiness.get(key) is True for key in EXPECTED_MOBILE_SOURCE_READINESS_CHECK_IDS),
                "sourceInstallOnlyRoleShell": set(role_shell)
                == set(EXPECTED_MOBILE_SOURCE_ROLE_SHELL_CHECK_IDS)
                and all(role_shell.get(key) is True for key in EXPECTED_MOBILE_SOURCE_ROLE_SHELL_CHECK_IDS),
                "sourceRetiredEnvAbsent": set(retired_env)
                == set(EXPECTED_MOBILE_SOURCE_RETIRED_ENV_CHECK_IDS)
                and all(retired_env.get(key) is True for key in EXPECTED_MOBILE_SOURCE_RETIRED_ENV_CHECK_IDS),
            }
        )
    elif mode == "live":
        readiness = payload.get("readiness") if isinstance(payload.get("readiness"), dict) else {}
        readiness_checks = readiness.get("checks") if isinstance(readiness.get("checks"), dict) else {}
        role_probes = payload.get("roleProbes") if isinstance(payload.get("roleProbes"), dict) else {}
        checks.update(
            {
                "liveBaseUrl": payload.get("baseUrl") == "https://chummer.run",
                "liveReadinessConsistent": set(readiness_checks)
                == set(EXPECTED_MOBILE_LIVE_READINESS_CHECK_IDS)
                and all(
                    readiness_checks.get(check_id) is True
                    for check_id in EXPECTED_MOBILE_LIVE_READINESS_CHECK_IDS
                ),
                "liveRoleProbesComplete": set(role_probes)
                == set(EXPECTED_MOBILE_LIVE_ROLE_PROBE_IDS),
                "liveRoleProbesPass": bool(role_probes)
                and all(
                    isinstance(probe, dict)
                    and isinstance(probe.get("checks"), dict)
                    and set(probe["checks"])
                    == set(EXPECTED_MOBILE_LIVE_ROLE_PROBE_CHECK_IDS)
                    and all(
                        probe["checks"].get(check_id) is True
                        for check_id in EXPECTED_MOBILE_LIVE_ROLE_PROBE_CHECK_IDS
                    )
                    for probe in role_probes.values()
                ),
            }
        )
    return {
        "contractName": str(payload.get("contractName") or ""),
        "mode": mode,
        "checks": checks,
        "pass": bool(checks) and all(checks.values()),
    }


def frontdoor_install_entry_summary(payload: dict[str, Any]) -> dict[str, Any]:
    def is_sha256(value: Any) -> bool:
        normalized = str(value or "").strip().lower()
        return len(normalized) == 64 and all(character in "0123456789abcdef" for character in normalized)

    public_targets = payload.get("frontdoorNavigationPublicInstallTargets")
    page_errors = payload.get("frontdoorNavigationPageErrors")
    checks = {
        "postdeployContract": payload.get("contractName") == EXPECTED_POSTDEPLOY_CONTRACT,
        "postdeployPass": normalize_status(payload) == "pass",
        "postdeployNoFailures": payload.get("failures") == [],
        "canonicalBaseUrl": payload.get("baseUrl") == "https://chummer.run",
        "browserProofsPass": (
            payload.get("frontdoorNavigationPlaywrightRuntimeResolutionMode")
            == "validated_local_node_modules_exact_lock_version"
            and bool(str(payload.get("frontdoorNavigationPlaywrightPackageVersion") or "").strip())
            and is_sha256(payload.get("frontdoorNavigationPlaywrightPackageJsonSha256"))
            and is_sha256(payload.get("frontdoorNavigationPlaywrightCliSha256"))
        ),
        "frontdoorProofPass": payload.get("frontdoorNavigationStatus") == "pass",
        "frontdoorContractV2": (
            payload.get("frontdoorNavigationMobileArtifactContract")
            == EXPECTED_FRONTDOOR_CONTRACT
        ),
        "installContractSatisfied": (
            payload.get("frontdoorNavigationMobileArtifactInstallContractSatisfied")
            is True
        ),
        "publicInstallTargets": public_targets == EXPECTED_PUBLIC_INSTALL_TARGETS,
        "installOnlyBoundary": (
            payload.get("frontdoorNavigationDeviceRouting")
            == "auto_ua_ch_mobile_direct"
            and payload.get("frontdoorNavigationPlaySurface") == "install-only"
            and payload.get("frontdoorNavigationPlayAuthority") == "none"
            and payload.get("frontdoorNavigationLiveSession") == "unavailable"
            and payload.get("frontdoorNavigationPwaManifestPath")
            == "/manifest.player.webmanifest"
            and payload.get("frontdoorNavigationLiveTurnCompanionShell") is False
        ),
        "privateRuntimeAbsent": (
            payload.get("frontdoorNavigationPrivateBrowserStateKeys") == 0
            and payload.get("frontdoorNavigationPlayApiRequests") == 0
            and payload.get("frontdoorNavigationBlazorCircuitRequests") == 0
            and payload.get("frontdoorNavigationAnalyticsRequests") == 0
            and payload.get("frontdoorNavigationPrivateQueryRequests") == 0
            and page_errors == []
        ),
        "proofClosurePass": (
            payload.get("frontdoorNavigationProofClosureStatus") == "pass"
            and is_sha256(payload.get("frontdoorNavigationProofClosureSha256"))
        ),
    }
    return {
        "contract_name": EXPECTED_PUBLIC_ENTRY_CONTRACT,
        "base_url": str(payload.get("baseUrl") or ""),
        "public_install_targets": public_targets if isinstance(public_targets, list) else [],
        "build_target": "/build",
        "play_target": "/mobile/player",
        "play_surface": str(payload.get("frontdoorNavigationPlaySurface") or ""),
        "play_authority": str(payload.get("frontdoorNavigationPlayAuthority") or ""),
        "live_session": str(payload.get("frontdoorNavigationLiveSession") or ""),
        "pwa_manifest_path": str(payload.get("frontdoorNavigationPwaManifestPath") or ""),
        "checks_pass": all(checks.values()),
        "checks": checks,
    }


def main() -> int:
    failures: list[str] = []
    mobile, mobile_error = load_json(MOBILE_PWA_PROOF)
    public_edge_postdeploy, public_edge_postdeploy_error = load_json(
        PUBLIC_EDGE_POSTDEPLOY_PROOF
    )
    blazor_pwa, blazor_pwa_error = load_json(BLAZOR_PWA_PROOF)
    horizon, horizon_error = load_json(BLAZOR_EXECUTION_HORIZON)
    desktop_parity, desktop_parity_error = load_json(CHUMMER5A_DESKTOP_WORKFLOW_PARITY_PROOF)

    for error in [
        mobile_error,
        public_edge_postdeploy_error,
        blazor_pwa_error,
        horizon_error,
    ]:
        if error:
            failures.append(error)

    mobile_contract = mobile_v2_contract_summary(mobile)
    mobile_public_entry = frontdoor_install_entry_summary(public_edge_postdeploy)
    mobile_pass = mobile_contract["pass"] is True
    mobile_public_entry_holds = mobile_public_entry["checks_pass"] is True
    blazor_pwa_pass = normalize_status(blazor_pwa) in {"pass", "passed", "ready"}
    horizon_pass = normalize_status(horizon) in {"pass", "passed", "ready"}
    near_term = horizon_by_id(horizon, "near_term_hosted_smoke_execution")
    mid_term = horizon_by_id(horizon, "mid_term_full_live_public_edge_execution_matrix")
    boundary = horizon.get("boundary") if isinstance(horizon.get("boundary"), dict) else {}
    near_term_proven = str(near_term.get("status") or "").strip() == "proven"
    mid_term_status = str(mid_term.get("status") or "").strip() or "missing"
    long_term_parity_status = str(desktop_parity.get("status") or "").strip().lower() if not desktop_parity_error else ""
    long_term_proven = (
        long_term_parity_status in {"pass", "passed", "ready"} and mid_term_status == "proven"
    )
    no_smoke_to_full = boundary.get("does_not_upgrade_smoke_to_full") is True
    full_requires_full_receipt = boundary.get("full_scope_requires_current_passing_full_receipt") is True

    if not mobile_pass:
        failures.append("Hub mobile/PWA public projection proof is not passing.")
    if not mobile_public_entry_holds:
        failures.append(
            "Public-edge frontdoor proof does not prove public Build and Play install "
            "handoffs with Play landing on the authority-free /mobile/player install shell."
        )
    if not blazor_pwa_pass:
        failures.append("Blazor hosted PWA public-edge proof is not passing.")
    if not horizon_pass:
        failures.append("Blazor hosted execution horizon receipt is not passing.")
    if not near_term_proven:
        failures.append("Blazor near-term smoke execution horizon is not proven.")
    if not no_smoke_to_full:
        failures.append("Blazor execution horizon does not explicitly block smoke-to-full promotion.")
    if not full_requires_full_receipt:
        failures.append("Blazor execution horizon does not require a current passing full-scope receipt for full-matrix promotion.")

    verdict = (
        "mobile_pwa_and_blazor_smoke_integrated_full_matrix_not_proven"
        if mid_term_status != "proven"
        else (
            "mobile_pwa_and_blazor_full_matrix_and_long_term_browser_parity_integrated"
            if long_term_proven
            else "mobile_pwa_and_blazor_full_matrix_integrated"
        )
    )
    payload = {
        "contract_name": EXPECTED_CONTRACT,
        "status": "fail" if failures else "pass",
        "generated_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "verdict": verdict,
        "proofs": {
            "hub_mobile_pwa_public_projection": {
                "path": str(MOBILE_PWA_PROOF),
                "status": normalize_status(mobile) or "missing",
                "contract_name": mobile_contract["contractName"],
                "mode": mobile_contract["mode"],
                "base_url": mobile_public_entry["base_url"],
                "source_contract": mobile_contract,
                "frontdoor_postdeploy_path": str(PUBLIC_EDGE_POSTDEPLOY_PROOF),
                "public_entry": mobile_public_entry,
                "pass": mobile_pass and mobile_public_entry_holds,
            },
            "blazor_hosted_pwa_public_edge": {
                "path": str(BLAZOR_PWA_PROOF),
                "status": normalize_status(blazor_pwa) or "missing",
                "contract_name": str(blazor_pwa.get("contract_name") or "").strip(),
                "route_lane": str(blazor_pwa.get("route_lane") or "").strip(),
                "pass": blazor_pwa_pass,
            },
            "blazor_hosted_execution_horizon": {
                "path": str(BLAZOR_EXECUTION_HORIZON),
                "status": normalize_status(horizon) or "missing",
                "contract_name": str(horizon.get("contract_name") or "").strip(),
                "near_term_smoke_status": str(near_term.get("status") or "").strip() or "missing",
                "mid_term_full_matrix_status": mid_term_status,
                "mid_term_full_required_workflow_family_count": mid_term.get("required_workflow_family_count", 0),
                "mid_term_full_covered_workflow_family_count": mid_term.get("covered_workflow_family_count", 0),
                "long_term_full_browser_parity_status": "proven" if long_term_proven else "not_proven",
                "long_term_full_browser_parity_proof_status": long_term_parity_status or "missing",
                "long_term_full_browser_parity_path": str(CHUMMER5A_DESKTOP_WORKFLOW_PARITY_PROOF),
                "pass": horizon_pass and near_term_proven and no_smoke_to_full and full_requires_full_receipt,
            },
        },
        "boundaries": {
            "does_not_upgrade_smoke_to_full": no_smoke_to_full,
            "full_matrix_requires_current_passing_full_scope_receipt": full_requires_full_receipt,
            "hub_mobile_pwa_projection_is_not_blazor_full_execution": True,
            "does_not_upgrade_full_matrix_to_long_term_browser_parity": True,
            "long_term_browser_parity_requires_full_matrix_and_desktop_workflow_parity": True,
        },
        "failures": failures,
        "notes": [
            "This Hub bridge keeps mobile/PWA readiness, Blazor PWA installability, and Blazor hosted execution horizons visible together.",
            "A passing bridge does not mean the full live Blazor public-edge execution matrix is proven unless mid_term_full_matrix_status is proven.",
            "Living-world opt-in and Black Ledger mobile projection remain Hub-owned; Blazor hosted execution breadth remains presentation-owned.",
            "Long-term browser parity is only claimed if mid-term execution is proven and desktop workflow parity proof is currently passing.",
        ],
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    if failures:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 1

    print(f"blazor_execution_horizon_bridge:ok {OUTPUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PARITY_CHECKLIST="$ROOT/docs/PARITY_CHECKLIST.md"
PARITY_GENERATOR="$ROOT/scripts/generate-parity-checklist.sh"
DEFAULT_UI_PUBLISHED_DIR="$ROOT/../chummer6-ui/.codex-studio/published"
LEGACY_UI_PUBLISHED_DIR="$ROOT/../chummer-presentation/.codex-studio/published"
UI_PUBLISHED_DIR="${CHUMMER_UI_PUBLISHED_DIR:-$DEFAULT_UI_PUBLISHED_DIR}"
SR4_WORKFLOW_LEDGER_PATH="$ROOT/../chummer6-ui/docs/SR4_WORKFLOW_PARITY_LEDGER.json"
SR6_WORKFLOW_LEDGER_PATH="$ROOT/../chummer6-ui/docs/SR6_WORKFLOW_PARITY_LEDGER.json"

resolve_receipt_path() {
  local file_name="$1"
  local primary="$UI_PUBLISHED_DIR/$file_name"
  if [[ -f "$primary" ]]; then
    echo "$primary"
    return 0
  fi
  if [[ -z "${CHUMMER_UI_PUBLISHED_DIR:-}" ]]; then
    local legacy="$LEGACY_UI_PUBLISHED_DIR/$file_name"
    if [[ -f "$legacy" ]]; then
      echo "$legacy"
      return 0
    fi
  fi
  echo "$primary"
}

WORKFLOW_GATE_RECEIPT="$(resolve_receipt_path "DESKTOP_WORKFLOW_EXECUTION_GATE.generated.json")"
VISUAL_FAMILIARITY_RECEIPT="$(resolve_receipt_path "DESKTOP_VISUAL_FAMILIARITY_EXIT_GATE.generated.json")"

if [[ ! -x "$PARITY_GENERATOR" ]]; then
  echo "parity generator script is missing or not executable: $PARITY_GENERATOR" >&2
  exit 2
fi

if ! command -v rg >/dev/null 2>&1; then
  echo "ripgrep (rg) is required for parity auditing." >&2
  exit 2
fi

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 is required for parity auditing." >&2
  exit 2
fi

if ! bash "$PARITY_GENERATOR"; then
  echo "parity audit failed: parity checklist generation reported drift." >&2
  exit 1
fi

if [[ ! -f "$PARITY_CHECKLIST" ]]; then
  echo "parity audit failed: generated checklist is missing at $PARITY_CHECKLIST" >&2
  exit 1
fi

summary_block="$(awk '/^## Summary/{flag=1; next} /^## /{if(flag){exit}} flag {print}' "$PARITY_CHECKLIST")"
if [[ -z "$summary_block" ]]; then
  echo "parity audit failed: summary block missing in $PARITY_CHECKLIST" >&2
  exit 1
fi
for required_workflow_ledger_path in "$SR4_WORKFLOW_LEDGER_PATH" "$SR6_WORKFLOW_LEDGER_PATH"; do
  if [[ ! -f "$required_workflow_ledger_path" ]]; then
    echo "parity audit failed: required workflow ledger is missing at $required_workflow_ledger_path" >&2
    exit 2
  fi
done

if ! python3 - "$WORKFLOW_GATE_RECEIPT" "$VISUAL_FAMILIARITY_RECEIPT" "$SR4_WORKFLOW_LEDGER_PATH" "$SR6_WORKFLOW_LEDGER_PATH" <<'PY'
import datetime as dt
import json
import os
import pathlib
import re
import sys
import urllib.parse

UTC = dt.timezone.utc
DEFAULT_PROOF_FRESHNESS_MAX_AGE_SECONDS = 24 * 60 * 60
DEFAULT_PROOF_FRESHNESS_MAX_FUTURE_SKEW_SECONDS = 5 * 60
DEFAULT_RELEASE_PROOF_MAX_AGE_SECONDS = 7 * 24 * 60 * 60
DEFAULT_RELEASE_PROOF_MAX_FUTURE_SKEW_SECONDS = 5 * 60
REQUIRED_RELEASE_PROOF_JOURNEYS = (
    "install_claim_restore_continue",
    "build_explain_publish",
    "campaign_session_recover_recap",
    "report_cluster_release_notify",
)
REQUIRED_RELEASE_PROOF_ROUTES = (
    "/downloads/install/avalonia-linux-x64-installer",
    "/home/access",
    "/home/work",
    "/account/work",
    "/account/support",
    "/contact",
)
REQUIRED_LOCALIZATION_SHIPPING_LOCALES = ("en-us", "de-de", "fr-fr", "ja-jp", "pt-br", "zh-cn")
REQUIRED_LOCALIZATION_ACCEPTANCE_GATES = (
    "pseudo_localization",
    "missing_key_fail_fast",
    "top_surface_overflow_checks",
    "locale_smoke_first_launch",
    "locale_smoke_settings",
    "locale_smoke_explain",
    "locale_smoke_updater",
    "locale_smoke_support",
    "non_english_generated_artifact_smoke",
)
REQUIRED_LOCALIZATION_DOMAINS = (
    "app_chrome",
    "install_update_support",
    "explain_receipts",
    "data_rules_names",
    "generated_artifacts",
)
DEFAULT_ALLOWED_RELEASE_PROOF_BASE_URLS = ("https://chummer.run",)


def require_object(value: object, *, message: str) -> dict:
    if not isinstance(value, dict):
        raise SystemExit(message)
    return value


def resolve_alias_value(
    mapping: dict,
    *,
    primary_key: str,
    secondary_key: str,
    field_name: str,
    source: pathlib.Path,
) -> object:
    has_primary = primary_key in mapping
    has_secondary = secondary_key in mapping
    if has_primary and has_secondary and mapping.get(primary_key) != mapping.get(secondary_key):
        raise SystemExit(
            "parity audit failed: "
            f"{field_name} alias values drift between {primary_key} and {secondary_key}: {source}"
        )
    if has_primary:
        return mapping.get(primary_key)
    if has_secondary:
        return mapping.get(secondary_key)
    return None


def require_string_list(value: object, *, message: str) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise SystemExit(message)
    return value


def require_canonical_unique_string_list(
    values: list[str],
    *,
    field_name: str,
    path: pathlib.Path,
) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    duplicates: set[str] = set()
    for index, value in enumerate(values):
        if value != value.strip():
            raise SystemExit(
                f"parity audit failed: {field_name}[{index}] must not include leading/trailing whitespace: {path}"
            )
        token = value.strip()
        if not token:
            raise SystemExit(f"parity audit failed: {field_name}[{index}] must not be blank: {path}")
        normalized.append(token)
        if token in seen:
            duplicates.add(token)
        seen.add(token)
    if duplicates:
        raise SystemExit(
            f"parity audit failed: {field_name} must not contain duplicate ids: {path} ({', '.join(sorted(duplicates))})"
        )
    return normalized


def require_pass_status(value: object, *, message: str) -> None:
    normalized = str(value or "").strip().lower()
    if normalized not in {"pass", "passed", "ready"}:
        raise SystemExit(message + f" (status={normalized or 'missing'})")


def require_non_empty_string(value: object, *, message: str) -> str:
    parsed = str(value or "").strip()
    if not parsed:
        raise SystemExit(message)
    return parsed


def require_int(value: object, *, message: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise SystemExit(message)
    return value


def require_empty_collection(value: object, *, message: str) -> None:
    if isinstance(value, dict):
        if value:
            raise SystemExit(message)
        return
    if isinstance(value, list):
        if value:
            raise SystemExit(message)
        return
    raise SystemExit(message)


def require_int_at_least(value: object, *, minimum: int, message: str) -> int:
    parsed = require_int(value, message=message)
    if parsed < minimum:
        raise SystemExit(f"{message} (value={parsed}, minimum={minimum})")
    return parsed


def require_empty_problem_map(value: object, *, message: str) -> None:
    if not isinstance(value, dict):
        raise SystemExit(message)
    for _, nested in value.items():
        if isinstance(nested, dict):
            if nested:
                raise SystemExit(message)
            continue
        if isinstance(nested, list):
            if nested:
                raise SystemExit(message)
            continue
        if nested not in (None, ""):
            raise SystemExit(message)


def require_true_bool(value: object, *, message: str) -> None:
    if value is not True:
        raise SystemExit(message)


def require_string_map(value: object, *, message: str) -> dict[str, str]:
    mapping = require_object(value, message=message)
    normalized: dict[str, str] = {}
    for raw_key, raw_value in mapping.items():
        if not isinstance(raw_key, str):
            raise SystemExit(message)
        key = raw_key.strip()
        if not key:
            raise SystemExit(message)
        parsed_value = str(raw_value or "").strip()
        if not parsed_value:
            raise SystemExit(message)
        normalized[key] = parsed_value
    return normalized


def normalized_token(value: object) -> str:
    return str(value or "").strip().lower()


def normalize_release_proof_route(raw_route: object, *, field_path: str, source: pathlib.Path) -> str:
    if not isinstance(raw_route, str):
        raise SystemExit(f"parity audit failed: {field_path} must be a string: {source}")
    route = raw_route.strip()
    if not route:
        raise SystemExit(f"parity audit failed: {field_path} must not be blank: {source}")
    if route != raw_route:
        raise SystemExit(
            f"parity audit failed: {field_path} must not include leading/trailing whitespace: {source}"
        )
    if not route.startswith("/"):
        raise SystemExit(f"parity audit failed: {field_path} must be a slash-led route path: {source}")
    if any(character.isspace() for character in route):
        raise SystemExit(f"parity audit failed: {field_path} must not include whitespace: {source}")
    if "?" in route or "#" in route:
        raise SystemExit(
            f"parity audit failed: {field_path} must not include query or fragment segments: {source}"
        )
    if "%" in route or "\\" in route:
        raise SystemExit(
            f"parity audit failed: {field_path} must not include percent-encoded or escaped path characters: {source}"
        )
    if "//" in route:
        raise SystemExit(f"parity audit failed: {field_path} must not include empty path segments: {source}")
    segments = route.split("/")
    if any(segment in {".", ".."} for segment in segments):
        raise SystemExit(f"parity audit failed: {field_path} must not include dot-segment traversal: {source}")
    if route != route.lower():
        raise SystemExit(
            f"parity audit failed: {field_path} must use canonical lowercase route casing: {source}"
        )
    canonical_route = route.lower()
    if canonical_route != "/":
        canonical_route = canonical_route.rstrip("/")
        if not canonical_route:
            canonical_route = "/"
    return canonical_route


def normalize_release_proof_base_url(raw_base_url: object, *, field_path: str, source: pathlib.Path) -> str:
    if not isinstance(raw_base_url, str):
        raise SystemExit(f"parity audit failed: {field_path} must be a string: {source}")
    base_url = raw_base_url.strip()
    if not base_url:
        raise SystemExit(f"parity audit failed: {field_path} must not be blank: {source}")
    if base_url != raw_base_url:
        raise SystemExit(
            f"parity audit failed: {field_path} must not include leading/trailing whitespace: {source}"
        )
    parsed = urllib.parse.urlsplit(base_url)
    scheme = parsed.scheme.lower()
    if scheme not in {"http", "https"}:
        raise SystemExit(
            f"parity audit failed: {field_path} must use http/https scheme: {source}"
        )
    if parsed.query or parsed.fragment:
        raise SystemExit(
            f"parity audit failed: {field_path} must not include query or fragment segments: {source}"
        )
    if parsed.path not in {"", "/"}:
        raise SystemExit(
            f"parity audit failed: {field_path} must be origin-only with no path segments: {source}"
        )
    if not parsed.netloc:
        raise SystemExit(
            f"parity audit failed: {field_path} must include authority host: {source}"
        )
    if parsed.username or parsed.password:
        raise SystemExit(
            f"parity audit failed: {field_path} must not include userinfo credentials: {source}"
        )
    if parsed.netloc != parsed.netloc.lower():
        raise SystemExit(
            f"parity audit failed: {field_path} must use canonical lowercase authority casing: {source}"
        )
    canonical_base_url = f"{scheme}://{parsed.netloc.lower()}"
    if base_url != canonical_base_url:
        raise SystemExit(
            f"parity audit failed: {field_path} must use canonical origin form with no trailing slash: {source}"
        )
    return canonical_base_url


def parse_iso_timestamp(value: object, *, field_path: str, source: pathlib.Path) -> dt.datetime:
    raw = str(value or "").strip()
    if not raw:
        raise SystemExit(f"parity audit failed: {field_path} must be an ISO timestamp: {source}")
    normalized = raw.replace("Z", "+00:00")
    try:
        parsed = dt.datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise SystemExit(f"parity audit failed: {field_path} must be an ISO timestamp: {source}") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def parse_non_negative_int_env(
    raw_value: object,
    *,
    default_value: int,
    field_path: str,
) -> int:
    if raw_value in (None, ""):
        return default_value
    try:
        parsed = int(str(raw_value).strip())
    except (TypeError, ValueError) as exc:
        raise SystemExit(
            f"parity audit failed: {field_path} must be a non-negative integer"
        ) from exc
    if parsed < 0:
        raise SystemExit(
            f"parity audit failed: {field_path} must be a non-negative integer"
        )
    return parsed


def parse_allowed_release_proof_base_urls(raw_value: object) -> tuple[str, ...]:
    if raw_value in (None, ""):
        return DEFAULT_ALLOWED_RELEASE_PROOF_BASE_URLS
    raw_values = [item.strip() for item in str(raw_value).split(",")]
    allowed: list[str] = []
    seen: set[str] = set()
    for index, raw_url in enumerate(raw_values):
        if not raw_url:
            continue
        canonical_url = normalize_release_proof_base_url(
            raw_url,
            field_path=f"allowedReleaseProofBaseUrls[{index}]",
            source=pathlib.Path("<parity-audit-config>"),
        )
        if canonical_url in seen:
            continue
        seen.add(canonical_url)
        allowed.append(canonical_url)
    if not allowed:
        raise SystemExit(
            "parity audit failed: allowed release proof base URL set must contain at least one canonical origin"
        )
    return tuple(allowed)


ALLOWED_RELEASE_PROOF_BASE_URLS = parse_allowed_release_proof_base_urls(
    os.environ.get("CHUMMER_UI_PARITY_ALLOWED_RELEASE_PROOF_BASE_URLS")
    or os.environ.get("CHUMMER_ALLOWED_RELEASE_PROOF_BASE_URLS")
)


def validate_release_channel_proof(release_channel_path: pathlib.Path, release_channel_data: dict) -> None:
    proof = require_object(
        release_channel_data.get("releaseProof"),
        message=(
            "parity audit failed: release-channel nested receipt releaseProof is required: "
            f"{release_channel_path}"
        ),
    )
    proof_status = normalized_token(proof.get("status"))
    if proof_status not in {"pass", "passed", "ready"}:
        raise SystemExit(
            "parity audit failed: release-channel nested receipt releaseProof.status must be pass/passed/ready: "
            f"{release_channel_path} (status={proof_status or 'missing'})"
        )
    proof_generated_at = parse_iso_timestamp(
        resolve_alias_value(
            proof,
            primary_key="generatedAt",
            secondary_key="generated_at",
            field_name="releaseProof.generatedAt",
            source=release_channel_path,
        ),
        field_path="releaseProof.generatedAt",
        source=release_channel_path,
    )
    release_proof_max_age_seconds = parse_non_negative_int_env(
        os.environ.get("CHUMMER_UI_PARITY_RELEASE_PROOF_MAX_AGE_SECONDS")
        or os.environ.get("CHUMMER_RELEASE_PROOF_MAX_AGE_SECONDS"),
        default_value=DEFAULT_RELEASE_PROOF_MAX_AGE_SECONDS,
        field_path="CHUMMER_UI_PARITY_RELEASE_PROOF_MAX_AGE_SECONDS/CHUMMER_RELEASE_PROOF_MAX_AGE_SECONDS",
    )
    release_proof_max_future_skew_seconds = parse_non_negative_int_env(
        os.environ.get("CHUMMER_UI_PARITY_RELEASE_PROOF_MAX_FUTURE_SKEW_SECONDS")
        or os.environ.get("CHUMMER_RELEASE_PROOF_MAX_FUTURE_SKEW_SECONDS"),
        default_value=DEFAULT_RELEASE_PROOF_MAX_FUTURE_SKEW_SECONDS,
        field_path="CHUMMER_UI_PARITY_RELEASE_PROOF_MAX_FUTURE_SKEW_SECONDS/CHUMMER_RELEASE_PROOF_MAX_FUTURE_SKEW_SECONDS",
    )
    release_proof_age_seconds = int((dt.datetime.now(UTC) - proof_generated_at).total_seconds())
    if release_proof_age_seconds > release_proof_max_age_seconds:
        raise SystemExit(
            "parity audit failed: release-channel nested receipt releaseProof.generatedAt is stale: "
            f"{release_channel_path} (age_seconds={release_proof_age_seconds}, max_age_seconds={release_proof_max_age_seconds})"
        )
    if release_proof_age_seconds < -release_proof_max_future_skew_seconds:
        raise SystemExit(
            "parity audit failed: release-channel nested receipt releaseProof.generatedAt is in the future: "
            f"{release_channel_path} (future_skew_seconds={abs(release_proof_age_seconds)}, max_future_skew_seconds={release_proof_max_future_skew_seconds})"
        )
    localization_gate_object = require_object(
        proof.get("uiLocalizationReleaseGate"),
        message=(
            "parity audit failed: release-channel nested receipt releaseProof.uiLocalizationReleaseGate must be an object: "
            f"{release_channel_path}"
        ),
    )
    localization_gate_status = normalized_token(localization_gate_object.get("status"))
    if localization_gate_status not in {"pass", "passed", "ready"}:
        raise SystemExit(
            "parity audit failed: release-channel nested receipt releaseProof.uiLocalizationReleaseGate.status must be pass/passed/ready: "
            f"{release_channel_path} (status={localization_gate_status or 'missing'})"
        )
    localization_gate_generated_at = parse_iso_timestamp(
        resolve_alias_value(
            localization_gate_object,
            primary_key="generatedAt",
            secondary_key="generated_at",
            field_name="releaseProof.uiLocalizationReleaseGate.generatedAt",
            source=release_channel_path,
        ),
        field_path="releaseProof.uiLocalizationReleaseGate.generatedAt",
        source=release_channel_path,
    )
    localization_gate_age_seconds = int((dt.datetime.now(UTC) - localization_gate_generated_at).total_seconds())
    if localization_gate_age_seconds > release_proof_max_age_seconds:
        raise SystemExit(
            "parity audit failed: release-channel nested receipt releaseProof.uiLocalizationReleaseGate.generatedAt is stale: "
            f"{release_channel_path} (age_seconds={localization_gate_age_seconds}, max_age_seconds={release_proof_max_age_seconds})"
        )
    if localization_gate_age_seconds < -release_proof_max_future_skew_seconds:
        raise SystemExit(
            "parity audit failed: release-channel nested receipt releaseProof.uiLocalizationReleaseGate.generatedAt is in the future: "
            f"{release_channel_path} (future_skew_seconds={abs(localization_gate_age_seconds)}, max_future_skew_seconds={release_proof_max_future_skew_seconds})"
        )
    default_key_count = require_int(
        resolve_alias_value(
            localization_gate_object,
            primary_key="defaultKeyCount",
            secondary_key="default_key_count",
            field_name="releaseProof.uiLocalizationReleaseGate.defaultKeyCount",
            source=release_channel_path,
        ),
        message=(
            "parity audit failed: release-channel nested receipt releaseProof.uiLocalizationReleaseGate.defaultKeyCount must be an integer: "
            f"{release_channel_path}"
        ),
    )
    if default_key_count <= 0:
        raise SystemExit(
            "parity audit failed: release-channel nested receipt releaseProof.uiLocalizationReleaseGate.defaultKeyCount must be positive: "
            f"{release_channel_path} (default_key_count={default_key_count})"
        )
    explicit_fallback_runtime = normalized_token(
        resolve_alias_value(
            localization_gate_object,
            primary_key="explicitFallbackRuntime",
            secondary_key="explicit_fallback_runtime",
            field_name="releaseProof.uiLocalizationReleaseGate.explicitFallbackRuntime",
            source=release_channel_path,
        )
    )
    if explicit_fallback_runtime not in {"pass", "passed", "ready"}:
        raise SystemExit(
            "parity audit failed: release-channel nested receipt releaseProof.uiLocalizationReleaseGate.explicitFallbackRuntime must be pass/passed/ready: "
            f"{release_channel_path} (status={explicit_fallback_runtime or 'missing'})"
        )
    signoff_smoke_runner_status = normalized_token(
        resolve_alias_value(
            localization_gate_object,
            primary_key="signoffSmokeRunnerStatus",
            secondary_key="signoff_smoke_runner_status",
            field_name="releaseProof.uiLocalizationReleaseGate.signoffSmokeRunnerStatus",
            source=release_channel_path,
        )
    )
    if signoff_smoke_runner_status not in {"pass", "passed", "ready"}:
        raise SystemExit(
            "parity audit failed: release-channel nested receipt releaseProof.uiLocalizationReleaseGate.signoffSmokeRunnerStatus must be pass/passed/ready: "
            f"{release_channel_path} (status={signoff_smoke_runner_status or 'missing'})"
        )
    shipping_locales = require_canonical_unique_string_list(
        require_string_list(
            resolve_alias_value(
                localization_gate_object,
                primary_key="shippingLocales",
                secondary_key="shipping_locales",
                field_name="releaseProof.uiLocalizationReleaseGate.shippingLocales",
                source=release_channel_path,
            ),
            message=(
                "parity audit failed: release-channel nested receipt releaseProof.uiLocalizationReleaseGate.shippingLocales must be a string array: "
                f"{release_channel_path}"
            ),
        ),
        field_name="releaseProof.uiLocalizationReleaseGate.shippingLocales",
        path=release_channel_path,
    )
    if tuple(shipping_locales) != REQUIRED_LOCALIZATION_SHIPPING_LOCALES:
        raise SystemExit(
            "parity audit failed: release-channel nested receipt releaseProof.uiLocalizationReleaseGate.shippingLocales must equal required flagship locales: "
            f"{release_channel_path} (actual={shipping_locales}, expected={list(REQUIRED_LOCALIZATION_SHIPPING_LOCALES)})"
        )
    acceptance_gates = require_canonical_unique_string_list(
        require_string_list(
            resolve_alias_value(
                localization_gate_object,
                primary_key="acceptanceGates",
                secondary_key="acceptance_gates",
                field_name="releaseProof.uiLocalizationReleaseGate.acceptanceGates",
                source=release_channel_path,
            ),
            message=(
                "parity audit failed: release-channel nested receipt releaseProof.uiLocalizationReleaseGate.acceptanceGates must be a string array: "
                f"{release_channel_path}"
            ),
        ),
        field_name="releaseProof.uiLocalizationReleaseGate.acceptanceGates",
        path=release_channel_path,
    )
    missing_acceptance_gates = sorted(
        gate for gate in REQUIRED_LOCALIZATION_ACCEPTANCE_GATES if gate not in acceptance_gates
    )
    if missing_acceptance_gates:
        raise SystemExit(
            "parity audit failed: release-channel nested receipt releaseProof.uiLocalizationReleaseGate.acceptanceGates is missing required gate ids: "
            f"{release_channel_path} ({', '.join(missing_acceptance_gates)})"
        )
    unexpected_acceptance_gates = sorted(
        gate for gate in acceptance_gates if gate not in REQUIRED_LOCALIZATION_ACCEPTANCE_GATES
    )
    if unexpected_acceptance_gates:
        raise SystemExit(
            "parity audit failed: release-channel nested receipt releaseProof.uiLocalizationReleaseGate.acceptanceGates has unexpected gate ids: "
            f"{release_channel_path} ({', '.join(unexpected_acceptance_gates)})"
        )
    if tuple(acceptance_gates) != REQUIRED_LOCALIZATION_ACCEPTANCE_GATES:
        raise SystemExit(
            "parity audit failed: release-channel nested receipt releaseProof.uiLocalizationReleaseGate.acceptanceGates must preserve canonical gate ordering: "
            f"{release_channel_path} (actual={acceptance_gates}, expected={list(REQUIRED_LOCALIZATION_ACCEPTANCE_GATES)})"
        )
    domain_coverage = require_string_map(
        resolve_alias_value(
            localization_gate_object,
            primary_key="domainCoverage",
            secondary_key="domain_coverage",
            field_name="releaseProof.uiLocalizationReleaseGate.domainCoverage",
            source=release_channel_path,
        ),
        message=(
            "parity audit failed: release-channel nested receipt releaseProof.uiLocalizationReleaseGate.domainCoverage must be a string map: "
            f"{release_channel_path}"
        ),
    )
    missing_domains = sorted(domain for domain in REQUIRED_LOCALIZATION_DOMAINS if domain not in domain_coverage)
    if missing_domains:
        raise SystemExit(
            "parity audit failed: release-channel nested receipt releaseProof.uiLocalizationReleaseGate.domainCoverage is missing required domains: "
            f"{release_channel_path} ({', '.join(missing_domains)})"
        )
    unexpected_domains = sorted(
        domain for domain in domain_coverage if domain not in REQUIRED_LOCALIZATION_DOMAINS
    )
    if unexpected_domains:
        raise SystemExit(
            "parity audit failed: release-channel nested receipt releaseProof.uiLocalizationReleaseGate.domainCoverage has unexpected domains: "
            f"{release_channel_path} ({', '.join(unexpected_domains)})"
        )
    for domain in REQUIRED_LOCALIZATION_DOMAINS:
        if normalized_token(domain_coverage.get(domain)) not in {"pass", "passed", "ready"}:
            raise SystemExit(
                "parity audit failed: release-channel nested receipt releaseProof.uiLocalizationReleaseGate.domainCoverage must be pass/passed/ready for required domain: "
                f"{release_channel_path} ({domain})"
            )
    locale_domain_coverage = require_object(
        resolve_alias_value(
            localization_gate_object,
            primary_key="localeDomainCoverage",
            secondary_key="locale_domain_coverage",
            field_name="releaseProof.uiLocalizationReleaseGate.localeDomainCoverage",
            source=release_channel_path,
        ),
        message=(
            "parity audit failed: release-channel nested receipt releaseProof.uiLocalizationReleaseGate.localeDomainCoverage must be an object: "
            f"{release_channel_path}"
        ),
    )
    missing_locale_domain_coverage = sorted(
        locale for locale in REQUIRED_LOCALIZATION_SHIPPING_LOCALES if locale not in locale_domain_coverage
    )
    if missing_locale_domain_coverage:
        raise SystemExit(
            "parity audit failed: release-channel nested receipt releaseProof.uiLocalizationReleaseGate.localeDomainCoverage is missing shipping locales: "
            f"{release_channel_path} ({', '.join(missing_locale_domain_coverage)})"
        )
    for locale in REQUIRED_LOCALIZATION_SHIPPING_LOCALES:
        locale_domain_map = require_string_map(
            locale_domain_coverage.get(locale),
            message=(
                "parity audit failed: release-channel nested receipt releaseProof.uiLocalizationReleaseGate.localeDomainCoverage locale must map domains to statuses: "
                f"{release_channel_path} ({locale})"
            ),
        )
        for domain in REQUIRED_LOCALIZATION_DOMAINS:
            status = normalized_token(locale_domain_map.get(domain))
            if status not in {"pass", "passed", "ready"}:
                raise SystemExit(
                    "parity audit failed: release-channel nested receipt releaseProof.uiLocalizationReleaseGate.localeDomainCoverage must be pass/passed/ready per locale/domain: "
                    f"{release_channel_path} ({locale}/{domain})"
                )
    blocking_findings_count = require_int(
        resolve_alias_value(
            localization_gate_object,
            primary_key="blockingFindingsCount",
            secondary_key="blocking_findings_count",
            field_name="releaseProof.uiLocalizationReleaseGate.blockingFindingsCount",
            source=release_channel_path,
        ),
        message=(
            "parity audit failed: release-channel nested receipt releaseProof.uiLocalizationReleaseGate.blockingFindingsCount must be an integer: "
            f"{release_channel_path}"
        ),
    )
    blocking_findings = resolve_alias_value(
        localization_gate_object,
        primary_key="blockingFindings",
        secondary_key="blocking_findings",
        field_name="releaseProof.uiLocalizationReleaseGate.blockingFindings",
        source=release_channel_path,
    )
    if not isinstance(blocking_findings, list):
        raise SystemExit(
            "parity audit failed: release-channel nested receipt releaseProof.uiLocalizationReleaseGate.blockingFindings must be a list: "
            f"{release_channel_path}"
        )
    if blocking_findings_count != len(blocking_findings):
        raise SystemExit(
            "parity audit failed: release-channel nested receipt releaseProof.uiLocalizationReleaseGate.blockingFindings length must match count: "
            f"{release_channel_path}"
        )
    if blocking_findings_count != 0:
        raise SystemExit(
            "parity audit failed: release-channel nested receipt releaseProof.uiLocalizationReleaseGate.blockingFindingsCount must equal 0: "
            f"{release_channel_path} (count={blocking_findings_count})"
        )
    translation_backlog_findings_count = require_int(
        resolve_alias_value(
            localization_gate_object,
            primary_key="translationBacklogFindingsCount",
            secondary_key="translation_backlog_findings_count",
            field_name="releaseProof.uiLocalizationReleaseGate.translationBacklogFindingsCount",
            source=release_channel_path,
        ),
        message=(
            "parity audit failed: release-channel nested receipt releaseProof.uiLocalizationReleaseGate.translationBacklogFindingsCount must be an integer: "
            f"{release_channel_path}"
        ),
    )
    translation_backlog_findings = resolve_alias_value(
        localization_gate_object,
        primary_key="translationBacklogFindings",
        secondary_key="translation_backlog_findings",
        field_name="releaseProof.uiLocalizationReleaseGate.translationBacklogFindings",
        source=release_channel_path,
    )
    if not isinstance(translation_backlog_findings, list):
        raise SystemExit(
            "parity audit failed: release-channel nested receipt releaseProof.uiLocalizationReleaseGate.translationBacklogFindings must be a list: "
            f"{release_channel_path}"
        )
    if translation_backlog_findings_count != len(translation_backlog_findings):
        raise SystemExit(
            "parity audit failed: release-channel nested receipt releaseProof.uiLocalizationReleaseGate.translationBacklogFindings length must match count: "
            f"{release_channel_path}"
        )
    if translation_backlog_findings_count != 0:
        raise SystemExit(
            "parity audit failed: release-channel nested receipt releaseProof.uiLocalizationReleaseGate.translationBacklogFindingsCount must equal 0: "
            f"{release_channel_path} (count={translation_backlog_findings_count})"
        )
    locale_summary = resolve_alias_value(
        localization_gate_object,
        primary_key="localeSummary",
        secondary_key="locale_summary",
        field_name="releaseProof.uiLocalizationReleaseGate.localeSummary",
        source=release_channel_path,
    )
    if not isinstance(locale_summary, list):
        raise SystemExit(
            "parity audit failed: release-channel nested receipt releaseProof.uiLocalizationReleaseGate.localeSummary must be a list: "
            f"{release_channel_path}"
        )
    locale_rows: dict[str, dict] = {}
    for index, row in enumerate(locale_summary):
        row_object = require_object(
            row,
            message=(
                "parity audit failed: release-channel nested receipt releaseProof.uiLocalizationReleaseGate.localeSummary rows must be objects: "
                f"{release_channel_path} (index={index})"
            ),
        )
        locale = normalized_token(row_object.get("locale"))
        if not locale:
            raise SystemExit(
                "parity audit failed: release-channel nested receipt releaseProof.uiLocalizationReleaseGate.localeSummary rows must include locale: "
                f"{release_channel_path} (index={index})"
            )
        if locale in locale_rows:
            raise SystemExit(
                "parity audit failed: release-channel nested receipt releaseProof.uiLocalizationReleaseGate.localeSummary must not contain duplicate locales: "
                f"{release_channel_path} ({locale})"
            )
        locale_rows[locale] = row_object
    missing_locale_rows = sorted(
        locale for locale in REQUIRED_LOCALIZATION_SHIPPING_LOCALES if locale not in locale_rows
    )
    if missing_locale_rows:
        raise SystemExit(
            "parity audit failed: release-channel nested receipt releaseProof.uiLocalizationReleaseGate.localeSummary is missing required locales: "
            f"{release_channel_path} ({', '.join(missing_locale_rows)})"
        )
    unexpected_locale_rows = sorted(
        locale for locale in locale_rows if locale not in REQUIRED_LOCALIZATION_SHIPPING_LOCALES
    )
    if unexpected_locale_rows:
        raise SystemExit(
            "parity audit failed: release-channel nested receipt releaseProof.uiLocalizationReleaseGate.localeSummary has unexpected locales: "
            f"{release_channel_path} ({', '.join(unexpected_locale_rows)})"
        )
    for locale in REQUIRED_LOCALIZATION_SHIPPING_LOCALES:
        row = locale_rows[locale]
        untranslated_key_count = require_int(
            resolve_alias_value(
                row,
                primary_key="untranslatedKeyCount",
                secondary_key="untranslated_key_count",
                field_name=f"releaseProof.uiLocalizationReleaseGate.localeSummary.{locale}.untranslatedKeyCount",
                source=release_channel_path,
            ),
            message=(
                "parity audit failed: release-channel nested receipt releaseProof.uiLocalizationReleaseGate.localeSummary locale must include integer untranslated key count: "
                f"{release_channel_path} ({locale})"
            ),
        )
        if untranslated_key_count != 0:
            raise SystemExit(
                "parity audit failed: release-channel nested receipt releaseProof.uiLocalizationReleaseGate.localeSummary must have zero untranslated keys: "
                f"{release_channel_path} ({locale}, untranslated_key_count={untranslated_key_count})"
            )
    proof_base_url = normalize_release_proof_base_url(
        resolve_alias_value(
            proof,
            primary_key="baseUrl",
            secondary_key="base_url",
            field_name="releaseProof.baseUrl",
            source=release_channel_path,
        ),
        field_path="releaseProof.baseUrl",
        source=release_channel_path,
    )
    if proof_base_url not in ALLOWED_RELEASE_PROOF_BASE_URLS:
        raise SystemExit(
            "parity audit failed: release-channel nested receipt releaseProof.baseUrl must match an allowed canonical release origin: "
            f"{release_channel_path} (base_url={proof_base_url}, allowed={', '.join(ALLOWED_RELEASE_PROOF_BASE_URLS)})"
        )
    journeys_passed = resolve_alias_value(
        proof,
        primary_key="journeysPassed",
        secondary_key="journeys_passed",
        field_name="releaseProof.journeysPassed",
        source=release_channel_path,
    )
    journeys = require_string_list(
        journeys_passed,
        message=(
            "parity audit failed: release-channel nested receipt releaseProof.journeysPassed must be a string array: "
            f"{release_channel_path}"
        ),
    )
    normalized_journeys = [normalized_token(journey) for journey in journeys]
    for index, raw_journey in enumerate(journeys):
        stripped_journey = raw_journey.strip()
        if not stripped_journey:
            raise SystemExit(
                "parity audit failed: release-channel nested receipt releaseProof.journeysPassed must not contain blank ids: "
                f"{release_channel_path}"
            )
        if raw_journey != stripped_journey:
            raise SystemExit(
                "parity audit failed: release-channel nested receipt releaseProof.journeysPassed must not include leading/trailing whitespace: "
                f"{release_channel_path} (index={index})"
            )
        if stripped_journey != stripped_journey.lower():
            raise SystemExit(
                "parity audit failed: release-channel nested receipt releaseProof.journeysPassed must use canonical lowercase journey ids: "
                f"{release_channel_path} (index={index}, value={raw_journey!r})"
            )
        if not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", stripped_journey):
            raise SystemExit(
                "parity audit failed: release-channel nested receipt releaseProof.journeysPassed must use canonical journey id tokens: "
                f"{release_channel_path} (index={index}, value={raw_journey!r})"
            )
    duplicate_journeys = sorted(
        journey for journey in set(normalized_journeys) if normalized_journeys.count(journey) > 1
    )
    if duplicate_journeys:
        raise SystemExit(
            "parity audit failed: release-channel nested receipt releaseProof.journeysPassed must not contain duplicate ids: "
            f"{release_channel_path} ({', '.join(duplicate_journeys)})"
        )
    missing_required_journeys = sorted(
        journey for journey in REQUIRED_RELEASE_PROOF_JOURNEYS if journey not in normalized_journeys
    )
    if missing_required_journeys:
        raise SystemExit(
            "parity audit failed: release-channel nested receipt releaseProof.journeysPassed is missing required baseline journey ids: "
            f"{release_channel_path} ({', '.join(missing_required_journeys)})"
        )
    unexpected_journeys = sorted(
        journey for journey in normalized_journeys if journey not in REQUIRED_RELEASE_PROOF_JOURNEYS
    )
    if unexpected_journeys:
        raise SystemExit(
            "parity audit failed: release-channel nested receipt releaseProof.journeysPassed declares unexpected journey ids: "
            f"{release_channel_path} ({', '.join(unexpected_journeys)})"
        )
    proof_routes = resolve_alias_value(
        proof,
        primary_key="proofRoutes",
        secondary_key="proof_routes",
        field_name="releaseProof.proofRoutes",
        source=release_channel_path,
    )
    raw_routes = require_string_list(
        proof_routes,
        message=(
            "parity audit failed: release-channel nested receipt releaseProof.proofRoutes must be a string array: "
            f"{release_channel_path}"
        ),
    )
    normalized_routes: list[str] = []
    for index, raw_route in enumerate(raw_routes):
        normalized_routes.append(
            normalize_release_proof_route(
                raw_route,
                field_path=f"releaseProof.proofRoutes[{index}]",
                source=release_channel_path,
            )
        )
    duplicate_routes = sorted(
        route for route in set(normalized_routes) if normalized_routes.count(route) > 1
    )
    if duplicate_routes:
        raise SystemExit(
            "parity audit failed: release-channel nested receipt releaseProof.proofRoutes must not contain duplicate routes after normalization: "
            f"{release_channel_path} ({', '.join(duplicate_routes)})"
        )
    missing_required_routes = sorted(
        route for route in REQUIRED_RELEASE_PROOF_ROUTES if route not in normalized_routes
    )
    if missing_required_routes:
        raise SystemExit(
            "parity audit failed: release-channel nested receipt releaseProof.proofRoutes is missing required flagship routes: "
            f"{release_channel_path} ({', '.join(missing_required_routes)})"
        )
    unexpected_routes = sorted(
        route for route in normalized_routes if route not in REQUIRED_RELEASE_PROOF_ROUTES
    )
    if unexpected_routes:
        raise SystemExit(
            "parity audit failed: release-channel nested receipt releaseProof.proofRoutes declares unexpected flagship routes: "
            f"{release_channel_path} ({', '.join(unexpected_routes)})"
        )


def require_all_values_equal(
    value: object,
    *,
    expected: str,
    message: str,
) -> None:
    mapping = require_string_map(value, message=message)
    for key, item in mapping.items():
        if item != expected:
            raise SystemExit(f"{message}: {key}={item!r}, expected={expected!r}")


def require_head_marker_statuses_pass(value: object, *, message: str) -> None:
    marker_statuses = require_object(value, message=message)
    for head, markers in marker_statuses.items():
        if not isinstance(head, str):
            raise SystemExit(message)
        marker_map = require_object(markers, message=message)
        for marker, status in marker_map.items():
            if not isinstance(marker, str):
                raise SystemExit(message)
            normalized = str(status or "").strip().lower()
            if normalized != "pass":
                raise SystemExit(
                    f"{message}: {head}.{marker}={normalized or 'missing'}"
                )


def read_receipt(path: pathlib.Path) -> dict:
    if not path.is_file():
        raise SystemExit(f"parity audit failed: required executable receipt is missing: {path}")
    with path.open(encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise SystemExit(f"parity audit failed: executable receipt must be a JSON object: {path}")
    return data


def load_required_family_ids(path: pathlib.Path, *, edition_label: str) -> set[str]:
    ledger = read_receipt(path)
    raw_families = ledger.get("requiredFamilies")
    if not isinstance(raw_families, list):
        raise SystemExit(
            f"parity audit failed: {edition_label} workflow ledger must define requiredFamilies as an array: {path}"
        )
    family_ids: list[str] = []
    for index, family in enumerate(raw_families):
        if not isinstance(family, dict):
            raise SystemExit(
                f"parity audit failed: {edition_label} workflow ledger requiredFamilies[{index}] must be an object: {path}"
            )
        raw_family_id = family.get("id")
        if not isinstance(raw_family_id, str):
            raise SystemExit(
                f"parity audit failed: {edition_label} workflow ledger requiredFamilies[{index}].id must be a string: {path}"
            )
        family_ids.append(raw_family_id)
    return set(
        require_canonical_unique_string_list(
            family_ids,
            field_name=f"{edition_label} workflow required family ids",
            path=path,
        )
    )


def read_status(path: pathlib.Path, data: dict) -> str:
    status = str(data.get("status", "")).strip().lower()
    if status not in {"pass", "passed", "ready"}:
        raise SystemExit(
            f"parity audit failed: executable receipt status must be pass/passed/ready: "
            f"{path} (status={status or 'missing'})"
        )
    return status


def parse_generated_at(path: pathlib.Path, data: dict) -> dt.datetime:
    raw = str(data.get("generatedAt") or data.get("generated_at") or "").strip()
    if not raw:
        raise SystemExit(f"parity audit failed: executable receipt generatedAt/generated_at is missing: {path}")
    normalized = raw.replace("Z", "+00:00")
    try:
        parsed = dt.datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise SystemExit(
            f"parity audit failed: executable receipt generatedAt/generated_at is invalid: {path} ({raw})"
        ) from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def read_release_channel_status(path: pathlib.Path, data: dict) -> str:
    status = str(data.get("status", "")).strip().lower()
    if status not in {"pass", "passed", "ready", "published"}:
        raise SystemExit(
            "parity audit failed: release-channel receipt status must be pass/passed/ready/published: "
            f"{path} (status={status or 'missing'})"
        )
    return status


def read_int_value(
    evidence: dict,
    key: str,
    *,
    default_value: int,
    path: pathlib.Path,
) -> int:
    value = evidence.get(key)
    if value is None:
        return default_value
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise SystemExit(
            f"parity audit failed: receipt evidence field {key} must be an integer when present: {path}"
        ) from exc
    if parsed < 0:
        raise SystemExit(f"parity audit failed: receipt evidence field {key} must be >= 0: {path}")
    return parsed


def resolve_nested_receipt_path(parent_path: pathlib.Path, raw_path: str) -> pathlib.Path:
    nested = pathlib.Path(raw_path).expanduser()
    if not nested.is_absolute():
        nested = (parent_path.parent / nested).resolve()
    return nested


def resolve_release_channel_receipt_path(parent_path: pathlib.Path, evidence: dict) -> pathlib.Path:
    release_channel_path_raw = require_non_empty_string(
        evidence.get("release_channel_path"),
        message=f"parity audit failed: executable receipt release-channel path is missing: {parent_path}",
    )
    resolved_path = resolve_nested_receipt_path(parent_path, release_channel_path_raw)
    override_raw_path = str(os.environ.get("CHUMMER_UI_PARITY_RELEASE_CHANNEL_PATH") or "").strip()
    if not override_raw_path:
        return resolved_path
    override_path = pathlib.Path(override_raw_path).expanduser()
    if not override_path.is_absolute():
        override_path = (pathlib.Path.cwd() / override_path).resolve()
    if not override_path.is_file():
        raise SystemExit(
            "parity audit failed: CHUMMER_UI_PARITY_RELEASE_CHANNEL_PATH must point to an existing release-channel receipt file: "
            f"{override_path}"
        )
    return override_path


def validate_timestamp_freshness(path: pathlib.Path, data: dict, evidence: dict) -> None:
    generated_at = parse_generated_at(path, data)
    max_age_seconds = read_int_value(
        evidence,
        "proof_freshness_max_age_seconds",
        default_value=DEFAULT_PROOF_FRESHNESS_MAX_AGE_SECONDS,
        path=path,
    )
    max_future_skew_seconds = read_int_value(
        evidence,
        "proof_freshness_max_future_skew_seconds",
        default_value=DEFAULT_PROOF_FRESHNESS_MAX_FUTURE_SKEW_SECONDS,
        path=path,
    )
    now = dt.datetime.now(UTC)
    age_seconds = int((now - generated_at).total_seconds())
    if age_seconds > max_age_seconds:
        raise SystemExit(
            "parity audit failed: executable receipt generatedAt/generated_at is stale: "
            f"{path} (age_seconds={age_seconds}, max_age_seconds={max_age_seconds})"
        )
    if age_seconds < -max_future_skew_seconds:
        raise SystemExit(
            "parity audit failed: executable receipt generatedAt/generated_at is in the future: "
            f"{path} (future_skew_seconds={abs(age_seconds)}, max_future_skew_seconds={max_future_skew_seconds})"
        )


def validate_workflow_contract(path: pathlib.Path, data: dict) -> None:
    evidence = require_object(
        data.get("evidence"),
        message=f"parity audit failed: workflow receipt evidence must be a JSON object: {path}",
    )
    flagship_required_heads = set(
        require_string_list(
            evidence.get("flagship_required_desktop_heads"),
            message=f"parity audit failed: workflow receipt flagship_required_desktop_heads must be a string array: {path}",
        )
    )
    required_heads = {"avalonia", "blazor-desktop"}
    missing_required_heads = sorted(required_heads.difference(flagship_required_heads))
    if missing_required_heads:
        raise SystemExit(
            "parity audit failed: workflow receipt is missing required flagship desktop heads: "
            + ", ".join(missing_required_heads)
            + f" ({path})"
        )
    require_empty_collection(
        evidence.get("flagship_missing_or_not_ready_desktop_heads"),
        message=f"parity audit failed: workflow receipt reports missing or non-ready flagship desktop heads: {path}",
    )
    require_empty_collection(
        evidence.get("flagship_missing_canonical_required_desktop_heads"),
        message=f"parity audit failed: workflow receipt reports missing canonical required desktop heads: {path}",
    )
    require_empty_problem_map(
        evidence.get("flagship_head_missing_contract_markers"),
        message=f"parity audit failed: workflow receipt reports missing flagship head contract markers: {path}",
    )
    require_head_marker_statuses_pass(
        evidence.get("flagship_head_contract_marker_statuses"),
        message=f"parity audit failed: workflow receipt reports non-pass flagship head contract markers: {path}",
    )
    require_true_bool(
        evidence.get("release_channel_receipt_exists"),
        message=f"parity audit failed: workflow receipt reports missing release-channel evidence receipt: {path}",
    )
    release_channel_channel_id = require_non_empty_string(
        evidence.get("release_channel_channel_id"),
        message=f"parity audit failed: workflow receipt release-channel channel id is missing: {path}",
    )
    require_non_empty_string(
        evidence.get("release_channel_version"),
        message=f"parity audit failed: workflow receipt release-channel version is missing: {path}",
    )
    release_channel_path = resolve_release_channel_receipt_path(path, evidence)
    release_channel_data = read_receipt(release_channel_path)
    read_release_channel_status(release_channel_path, release_channel_data)
    validate_release_channel_proof(release_channel_path, release_channel_data)
    release_channel_id = require_non_empty_string(
        release_channel_data.get("channelId"),
        message=(
            "parity audit failed: workflow receipt release-channel nested receipt channelId is missing: "
            f"{path} ({release_channel_path})"
        ),
    )
    workflow_release_channel_id = require_non_empty_string(
        evidence.get("release_channel_channel_id"),
        message=f"parity audit failed: workflow receipt release-channel channel id is missing: {path}",
    )
    if release_channel_id != workflow_release_channel_id:
        raise SystemExit(
            "parity audit failed: workflow receipt release-channel channel id drifts from nested receipt: "
            f"{path} ({workflow_release_channel_id}) vs {release_channel_path} ({release_channel_id})"
        )
    release_channel_version = require_non_empty_string(
        release_channel_data.get("version"),
        message=(
            "parity audit failed: workflow receipt release-channel nested receipt version is missing: "
            f"{path} ({release_channel_path})"
        ),
    )
    workflow_release_channel_version = require_non_empty_string(
        evidence.get("release_channel_version"),
        message=f"parity audit failed: workflow receipt release-channel version is missing: {path}",
    )
    if release_channel_version != workflow_release_channel_version:
        raise SystemExit(
            "parity audit failed: workflow receipt release-channel version drifts from nested receipt: "
            f"{path} ({workflow_release_channel_version}) vs {release_channel_path} ({release_channel_version})"
        )
    workflow_release_channel_generated_at = parse_generated_at(
        path,
        {"generatedAt": evidence.get("release_channel_generated_at")},
    )
    release_channel_generated_at = parse_generated_at(release_channel_path, release_channel_data)
    if workflow_release_channel_generated_at != release_channel_generated_at:
        raise SystemExit(
            "parity audit failed: workflow receipt release-channel generated_at drifts from nested receipt generatedAt: "
            f"{path} (evidence_generated_at={workflow_release_channel_generated_at.isoformat()}, "
            f"nested_generated_at={release_channel_generated_at.isoformat()}, "
            f"nested_receipt={release_channel_path})"
        )
    now = dt.datetime.now(UTC)
    release_channel_age_seconds = int((now - release_channel_generated_at).total_seconds())
    max_age_seconds = read_int_value(
        evidence,
        "proof_freshness_max_age_seconds",
        default_value=DEFAULT_PROOF_FRESHNESS_MAX_AGE_SECONDS,
        path=path,
    )
    max_future_skew_seconds = read_int_value(
        evidence,
        "proof_freshness_max_future_skew_seconds",
        default_value=DEFAULT_PROOF_FRESHNESS_MAX_FUTURE_SKEW_SECONDS,
        path=path,
    )
    if release_channel_age_seconds > max_age_seconds:
        raise SystemExit(
            "parity audit failed: workflow receipt release-channel nested receipt generatedAt is stale: "
            f"{path} (age_seconds={release_channel_age_seconds}, "
            f"max_age_seconds={max_age_seconds}, nested_receipt={release_channel_path})"
        )
    if release_channel_age_seconds < -max_future_skew_seconds:
        raise SystemExit(
            "parity audit failed: workflow receipt release-channel nested receipt generatedAt is in the future: "
            f"{path} (future_skew_seconds={abs(release_channel_age_seconds)}, "
            f"max_future_skew_seconds={max_future_skew_seconds}, nested_receipt={release_channel_path})"
        )
    require_all_values_equal(
        evidence.get("workflow_parity_receipt_channel_ids"),
        expected=workflow_release_channel_id,
        message=f"parity audit failed: workflow parity receipt channel ids drift from release-channel channel id: {path}",
    )
    require_empty_collection(
        evidence.get("flagship_gate.headProofs.status_malformed_entries"),
        message=f"parity audit failed: workflow receipt has malformed flagship head proof status keys: {path}",
    )
    require_empty_collection(
        evidence.get("flagship_gate.headProofs.status_non_canonical_keys"),
        message=f"parity audit failed: workflow receipt has non-canonical flagship head proof status keys: {path}",
    )
    require_empty_collection(
        evidence.get("flagship_gate.headProofs.status_duplicate_normalized_keys"),
        message=f"parity audit failed: workflow receipt has duplicate normalized flagship head proof status keys: {path}",
    )
    required_families = require_string_list(
        evidence.get("required_workflow_family_ids"),
        message=f"parity audit failed: workflow receipt required_workflow_family_ids must be a string array: {path}",
    )
    required_families = set(required_families)
    expected_families = load_required_family_ids(
        workflow_ledger_sr4_path,
        edition_label="SR4",
    ).union(
        load_required_family_ids(
            workflow_ledger_sr6_path,
            edition_label="SR6",
        )
    )
    missing_expected = sorted(expected_families.difference(required_families))
    if missing_expected:
        raise SystemExit(
            "parity audit failed: workflow receipt is missing required milestone-2 family ids: "
            + ", ".join(missing_expected)
            + f" ({path})"
        )
    require_empty_collection(
        evidence.get("missing_required_workflow_family_ids"),
        message=f"parity audit failed: workflow receipt reports missing required workflow family ids: {path}",
    )
    require_empty_collection(
        evidence.get("not_ready_required_workflow_family_ids"),
        message=f"parity audit failed: workflow receipt reports non-ready required workflow family ids: {path}",
    )
    require_empty_collection(
        evidence.get("workflow_execution_missing_receipts"),
        message=f"parity audit failed: workflow receipt reports missing execution receipts: {path}",
    )
    require_empty_collection(
        evidence.get("workflow_execution_failing_receipts"),
        message=f"parity audit failed: workflow receipt reports failing execution receipts: {path}",
    )
    require_empty_collection(
        evidence.get("workflow_execution_weak_receipts"),
        message=f"parity audit failed: workflow receipt reports weakly grounded execution receipts: {path}",
    )
    require_empty_collection(
        evidence.get("workflow_family_missing_receipts"),
        message=f"parity audit failed: workflow receipt reports missing workflow-family receipts: {path}",
    )
    require_empty_collection(
        evidence.get("workflow_family_failing_receipts"),
        message=f"parity audit failed: workflow receipt reports failing workflow-family receipts: {path}",
    )
    require_int_at_least(
        evidence.get("workflow_family_receipt_count_checked"),
        minimum=1,
        message=f"parity audit failed: workflow receipt must check at least one workflow-family receipt: {path}",
    )
    require_int_at_least(
        evidence.get("workflow_execution_receipt_count_checked"),
        minimum=1,
        message=f"parity audit failed: workflow receipt must check at least one workflow execution receipt: {path}",
    )
    require_empty_collection(
        evidence.get("missing_required_workflow_family_audit_tests"),
        message=f"parity audit failed: workflow receipt reports missing required workflow-family audit tests: {path}",
    )
    require_pass_status(
        evidence.get("sr4_workflow_parity_status"),
        message=f"parity audit failed: workflow receipt sr4 parity proof is not pass-ready: {path}",
    )
    require_pass_status(
        evidence.get("sr6_workflow_parity_status"),
        message=f"parity audit failed: workflow receipt sr6 parity proof is not pass-ready: {path}",
    )
    require_pass_status(
        evidence.get("chummer5a_workflow_parity_status"),
        message=f"parity audit failed: workflow receipt chummer5a parity proof is not pass-ready: {path}",
    )
    require_pass_status(
        evidence.get("sr4_sr6_frontier_status"),
        message=f"parity audit failed: workflow receipt sr4/sr6 frontier proof is not pass-ready: {path}",
    )
    workflow_parity_proof_max_age_seconds = read_int_value(
        evidence,
        "workflow_parity_proof_max_age_seconds",
        default_value=DEFAULT_PROOF_FRESHNESS_MAX_AGE_SECONDS,
        path=path,
    )
    for prefix, label in (
        ("sr4_workflow_parity", "sr4 workflow parity"),
        ("sr6_workflow_parity", "sr6 workflow parity"),
        ("chummer5a_workflow_parity", "chummer5a workflow parity"),
        ("sr4_sr6_frontier", "sr4/sr6 frontier parity"),
    ):
        nested_path_raw = require_non_empty_string(
            evidence.get(f"{prefix}_path"),
            message=(
                f"parity audit failed: workflow receipt {label} evidence path is missing: {path}"
            ),
        )
        nested_path = resolve_nested_receipt_path(path, nested_path_raw)
        nested_data = read_receipt(nested_path)
        read_status(nested_path, nested_data)
        nested_generated_at = parse_generated_at(
            path,
            {"generatedAt": evidence.get(f"{prefix}_generated_at")},
        )
        nested_receipt_generated_at = parse_generated_at(nested_path, nested_data)
        if nested_receipt_generated_at != nested_generated_at:
            raise SystemExit(
                "parity audit failed: workflow receipt "
                f"{label} evidence generated_at drifts from nested receipt generatedAt: {path} "
                f"(evidence_generated_at={nested_generated_at.isoformat()}, "
                f"nested_generated_at={nested_receipt_generated_at.isoformat()}, "
                f"nested_receipt={nested_path})"
            )
        nested_age_seconds = require_int_at_least(
            evidence.get(f"{prefix}_age_seconds"),
            minimum=0,
            message=(
                f"parity audit failed: workflow receipt {label} evidence age must be an integer >= 0: {path}"
            ),
        )
        if nested_age_seconds > workflow_parity_proof_max_age_seconds:
            raise SystemExit(
                "parity audit failed: workflow receipt "
                f"{label} evidence age exceeds allowed freshness window: {path} "
                f"(age_seconds={nested_age_seconds}, "
                f"max_age_seconds={workflow_parity_proof_max_age_seconds})"
            )
        now = dt.datetime.now(UTC)
        computed_age_seconds = int((now - nested_generated_at).total_seconds())
        nested_receipt_age_seconds = int((now - nested_receipt_generated_at).total_seconds())
        if computed_age_seconds > workflow_parity_proof_max_age_seconds:
            raise SystemExit(
                "parity audit failed: workflow receipt "
                f"{label} evidence generated_at is stale: {path} "
                f"(age_seconds={computed_age_seconds}, "
                f"max_age_seconds={workflow_parity_proof_max_age_seconds})"
            )
        if computed_age_seconds < -DEFAULT_PROOF_FRESHNESS_MAX_FUTURE_SKEW_SECONDS:
            raise SystemExit(
                "parity audit failed: workflow receipt "
                f"{label} evidence generated_at is in the future: {path} "
                f"(future_skew_seconds={abs(computed_age_seconds)}, "
                f"max_future_skew_seconds={DEFAULT_PROOF_FRESHNESS_MAX_FUTURE_SKEW_SECONDS})"
            )
        if nested_receipt_age_seconds > workflow_parity_proof_max_age_seconds:
            raise SystemExit(
                "parity audit failed: workflow receipt "
                f"{label} nested receipt generatedAt is stale: {path} "
                f"(age_seconds={nested_receipt_age_seconds}, "
                f"max_age_seconds={workflow_parity_proof_max_age_seconds}, "
                f"nested_receipt={nested_path})"
            )
        if nested_receipt_age_seconds < -DEFAULT_PROOF_FRESHNESS_MAX_FUTURE_SKEW_SECONDS:
            raise SystemExit(
                "parity audit failed: workflow receipt "
                f"{label} nested receipt generatedAt is in the future: {path} "
                f"(future_skew_seconds={abs(nested_receipt_age_seconds)}, "
                f"max_future_skew_seconds={DEFAULT_PROOF_FRESHNESS_MAX_FUTURE_SKEW_SECONDS}, "
                f"nested_receipt={nested_path})"
            )
    validate_timestamp_freshness(path, data, evidence)


def validate_visual_contract(path: pathlib.Path, data: dict) -> None:
    evidence = require_object(
        data.get("evidence"),
        message=f"parity audit failed: visual receipt evidence must be a JSON object: {path}",
    )
    required_tests = require_canonical_unique_string_list(
        require_string_list(
            evidence.get("required_tests"),
            message=f"parity audit failed: visual receipt required_tests must be a string array: {path}",
        ),
        field_name="visual receipt required_tests",
        path=path,
    )
    expected_required_tests = {
        "Desktop_shell_preserves_chummer5a_familiarity_cues",
        "Desktop_shell_preserves_classic_dense_three_pane_workbench_posture",
        "Theme_tokens_preserve_chummer5a_palette_and_readability",
        "Loaded_runner_preserves_visible_character_tab_posture",
        "Loaded_runner_header_stays_tab_panel_only_without_metric_cards",
        "Loaded_runner_workbench_preserves_legacy_frmcareer_landmarks",
        "Character_creation_preserves_familiar_dense_builder_rhythm",
        "Advancement_and_karma_journal_workflows_preserve_familiar_progression_rhythm",
        "Gear_builder_preserves_familiar_browse_detail_confirm_rhythm",
        "Vehicles_and_drones_builder_preserves_familiar_browse_detail_confirm_rhythm",
        "Cyberware_and_cyberlimb_builder_preserve_legacy_dialog_familiarity_cues",
        "Contacts_diary_and_support_routes_execute_with_public_path_visibility",
        "Magic_workflows_execute_with_specific_dialog_fields_and_confirm_actions",
        "Matrix_workflows_execute_with_specific_dialog_fields_and_confirm_actions",
        "Runtime_backed_menu_bar_preserves_classic_labels_and_clickable_primary_menus",
        "Runtime_backed_toolstrip_preserves_classic_labeled_workbench_actions",
        "Runtime_backed_toolstrip_preserves_flat_classic_toolbar_posture",
        "Runtime_backed_codex_tree_preserves_legacy_left_rail_navigation_posture",
        "Runtime_backed_ruleset_switch_preserves_sr4_sr5_and_sr6_codex_landmarks",
        "Runtime_backed_shell_avoids_modern_dashboard_copy_that_breaks_chummer5a_orientation",
        "Runtime_backed_shell_chrome_stays_enabled_after_runner_load",
        "Standalone_toolstrip_buttons_raise_expected_events",
        "Standalone_menu_bar_buttons_and_menu_commands_raise_expected_events",
        "Standalone_workspace_strip_quick_start_button_raises_expected_event",
        "Standalone_summary_header_tab_buttons_raise_expected_events",
        "Standalone_navigator_tree_selection_raises_workspace_tab_section_and_workflow_events",
        "Standalone_command_dialog_pane_routes_command_selection_field_updates_and_dialog_actions",
        "Standalone_coach_sidecar_copy_button_raises_event_when_launch_uri_is_available",
        "Loaded_runner_main_window_routes_navigation_palette_dialog_and_quick_action_surfaces_end_to_end",
    }
    missing_required_tests = sorted(expected_required_tests.difference(required_tests))
    if missing_required_tests:
        raise SystemExit(
            "parity audit failed: visual receipt is missing required milestone-2 visual tests: "
            + ", ".join(missing_required_tests)
            + f" ({path})"
        )
    unexpected_required_tests = sorted(set(required_tests).difference(expected_required_tests))
    if unexpected_required_tests:
        raise SystemExit(
            "parity audit failed: visual receipt declares unexpected milestone-2 visual tests: "
            + ", ".join(unexpected_required_tests)
            + f" ({path})"
        )
    required_interaction_keys = set(
        require_canonical_unique_string_list(
            require_string_list(
                evidence.get("required_legacy_interaction_keys"),
                message=f"parity audit failed: visual receipt required_legacy_interaction_keys must be a string array: {path}",
            ),
            field_name="visual receipt required_legacy_interaction_keys",
            path=path,
        )
    )
    required_surfaces = {
        "runtimeBackedLegacyWorkbench",
        "legacyDenseBuilderRhythm",
        "legacyCreationWorkflowRhythm",
        "legacyAdvancementWorkflowRhythm",
        "legacyBrowseDetailConfirmRhythm",
        "legacyContactsDiaryRhythm",
        "legacyMagicWorkflowRhythm",
        "legacyMatrixWorkflowRhythm",
        "legacyGearWorkflowRhythm",
        "legacyCyberwareDialogRhythm",
        "legacyVehiclesBuilderRhythm",
        "legacyContactsWorkflowRhythm",
        "legacyDiaryWorkflowRhythm",
    }
    missing_surface_keys = sorted(required_surfaces.difference(required_interaction_keys))
    if missing_surface_keys:
        raise SystemExit(
            "parity audit failed: visual receipt is missing required milestone-2 interaction keys: "
            + ", ".join(missing_surface_keys)
            + f" ({path})"
        )
    unexpected_surface_keys = sorted(required_interaction_keys.difference(required_surfaces))
    if unexpected_surface_keys:
        raise SystemExit(
            "parity audit failed: visual receipt declares unexpected milestone-2 interaction keys: "
            + ", ".join(unexpected_surface_keys)
            + f" ({path})"
        )
    required_visual_status_fields = {
        "runtime_backed_legacy_workbench": "runtime-backed legacy workbench",
        "legacy_dense_builder_rhythm": "legacy dense builder rhythm",
        "legacy_creation_workflow_rhythm": "legacy creation workflow rhythm",
        "legacy_advancement_workflow_rhythm": "legacy advancement workflow rhythm",
        "legacy_browse_detail_confirm_rhythm": "legacy browse-detail-confirm rhythm",
        "legacy_contacts_diary_rhythm": "legacy contacts/diary rhythm",
        "legacy_magic_workflow_rhythm": "legacy magic workflow rhythm",
        "legacy_matrix_workflow_rhythm": "legacy matrix workflow rhythm",
        "legacy_gear_workflow_rhythm": "legacy gear workflow rhythm",
        "legacy_cyberware_dialog_rhythm": "legacy cyberware dialog rhythm",
        "legacy_vehicles_builder_rhythm": "legacy vehicles builder rhythm",
        "legacy_contacts_workflow_rhythm": "legacy contacts workflow rhythm",
        "legacy_diary_workflow_rhythm": "legacy diary workflow rhythm",
        "legacy_familiarity_bridge": "legacy familiarity bridge",
    }
    for key, label in required_visual_status_fields.items():
        require_pass_status(
            evidence.get(key),
            message=f"parity audit failed: visual receipt {label} proof is not pass-ready: {path}",
        )
    require_empty_collection(
        evidence.get("missing_required_legacy_interaction_keys"),
        message=f"parity audit failed: visual receipt reports missing required legacy interaction keys: {path}",
    )
    require_empty_collection(
        evidence.get("flagship_missing_canonical_required_desktop_heads"),
        message=f"parity audit failed: visual receipt reports missing canonical required desktop heads: {path}",
    )
    require_empty_problem_map(
        evidence.get("flagship_head_missing_contract_markers"),
        message=f"parity audit failed: visual receipt reports missing flagship head contract markers: {path}",
    )
    require_head_marker_statuses_pass(
        evidence.get("flagship_head_contract_marker_statuses"),
        message=f"parity audit failed: visual receipt reports non-pass flagship head contract markers: {path}",
    )
    require_true_bool(
        evidence.get("release_channel_receipt_exists"),
        message=f"parity audit failed: visual receipt reports missing release-channel evidence receipt: {path}",
    )
    require_non_empty_string(
        evidence.get("release_channel_channel_id"),
        message=f"parity audit failed: visual receipt release-channel channel id is missing: {path}",
    )
    require_non_empty_string(
        evidence.get("release_channel_version"),
        message=f"parity audit failed: visual receipt release-channel version is missing: {path}",
    )
    release_channel_path = resolve_release_channel_receipt_path(path, evidence)
    release_channel_data = read_receipt(release_channel_path)
    read_release_channel_status(release_channel_path, release_channel_data)
    validate_release_channel_proof(release_channel_path, release_channel_data)
    release_channel_id = require_non_empty_string(
        release_channel_data.get("channelId"),
        message=(
            "parity audit failed: visual receipt release-channel nested receipt channelId is missing: "
            f"{path} ({release_channel_path})"
        ),
    )
    visual_release_channel_id = require_non_empty_string(
        evidence.get("release_channel_channel_id"),
        message=f"parity audit failed: visual receipt release-channel channel id is missing: {path}",
    )
    if release_channel_id != visual_release_channel_id:
        raise SystemExit(
            "parity audit failed: visual receipt release-channel channel id drifts from nested receipt: "
            f"{path} ({visual_release_channel_id}) vs {release_channel_path} ({release_channel_id})"
        )
    release_channel_version = require_non_empty_string(
        release_channel_data.get("version"),
        message=(
            "parity audit failed: visual receipt release-channel nested receipt version is missing: "
            f"{path} ({release_channel_path})"
        ),
    )
    visual_release_channel_version = require_non_empty_string(
        evidence.get("release_channel_version"),
        message=f"parity audit failed: visual receipt release-channel version is missing: {path}",
    )
    if release_channel_version != visual_release_channel_version:
        raise SystemExit(
            "parity audit failed: visual receipt release-channel version drifts from nested receipt: "
            f"{path} ({visual_release_channel_version}) vs {release_channel_path} ({release_channel_version})"
        )
    visual_release_channel_generated_at = parse_generated_at(
        path,
        {"generatedAt": evidence.get("release_channel_generated_at")},
    )
    release_channel_generated_at = parse_generated_at(release_channel_path, release_channel_data)
    if visual_release_channel_generated_at != release_channel_generated_at:
        raise SystemExit(
            "parity audit failed: visual receipt release-channel generated_at drifts from nested receipt generatedAt: "
            f"{path} (evidence_generated_at={visual_release_channel_generated_at.isoformat()}, "
            f"nested_generated_at={release_channel_generated_at.isoformat()}, "
            f"nested_receipt={release_channel_path})"
        )
    now = dt.datetime.now(UTC)
    release_channel_age_seconds = int((now - release_channel_generated_at).total_seconds())
    max_age_seconds = read_int_value(
        evidence,
        "proof_freshness_max_age_seconds",
        default_value=DEFAULT_PROOF_FRESHNESS_MAX_AGE_SECONDS,
        path=path,
    )
    max_future_skew_seconds = read_int_value(
        evidence,
        "proof_freshness_max_future_skew_seconds",
        default_value=DEFAULT_PROOF_FRESHNESS_MAX_FUTURE_SKEW_SECONDS,
        path=path,
    )
    if release_channel_age_seconds > max_age_seconds:
        raise SystemExit(
            "parity audit failed: visual receipt release-channel nested receipt generatedAt is stale: "
            f"{path} (age_seconds={release_channel_age_seconds}, "
            f"max_age_seconds={max_age_seconds}, nested_receipt={release_channel_path})"
        )
    if release_channel_age_seconds < -max_future_skew_seconds:
        raise SystemExit(
            "parity audit failed: visual receipt release-channel nested receipt generatedAt is in the future: "
            f"{path} (future_skew_seconds={abs(release_channel_age_seconds)}, "
            f"max_future_skew_seconds={max_future_skew_seconds}, nested_receipt={release_channel_path})"
        )
    require_empty_collection(
        evidence.get("flagship_gate.headProofs.status_malformed_entries"),
        message=f"parity audit failed: visual receipt has malformed flagship head proof status keys: {path}",
    )
    require_empty_collection(
        evidence.get("flagship_gate.headProofs.status_non_canonical_keys"),
        message=f"parity audit failed: visual receipt has non-canonical flagship head proof status keys: {path}",
    )
    require_empty_collection(
        evidence.get("flagship_gate.headProofs.status_duplicate_normalized_keys"),
        message=f"parity audit failed: visual receipt has duplicate normalized flagship head proof status keys: {path}",
    )
    require_empty_collection(
        evidence.get("missing_theme_tokens"),
        message=f"parity audit failed: visual receipt reports missing required legacy theme tokens: {path}",
    )
    require_pass_status(
        evidence.get("flagship_theme_readability_contrast"),
        message=f"parity audit failed: visual receipt flagship theme/readability proof is not pass-ready: {path}",
    )
    require_pass_status(
        evidence.get("runtime_backed_shell_menu"),
        message=f"parity audit failed: visual receipt runtime-backed shell menu proof is not pass-ready: {path}",
    )
    require_pass_status(
        evidence.get("runtime_backed_menu_bar_labels"),
        message=f"parity audit failed: visual receipt runtime-backed menu bar labels proof is not pass-ready: {path}",
    )
    require_pass_status(
        evidence.get("runtime_backed_toolstrip_actions"),
        message=f"parity audit failed: visual receipt runtime-backed toolstrip actions proof is not pass-ready: {path}",
    )
    require_pass_status(
        evidence.get("runtime_backed_tab_panel_only_header"),
        message=f"parity audit failed: visual receipt runtime-backed tab panel header proof is not pass-ready: {path}",
    )
    require_pass_status(
        evidence.get("runtime_backed_clickable_primary_menus"),
        message=f"parity audit failed: visual receipt runtime-backed clickable menu proof is not pass-ready: {path}",
    )
    require_true_bool(
        evidence.get("loaded_runner_tab_strip_control_present"),
        message=f"parity audit failed: visual receipt loaded runner tab-strip control proof is missing: {path}",
    )
    require_true_bool(
        evidence.get("loaded_runner_tab_posture_control_present"),
        message=f"parity audit failed: visual receipt loaded runner tab-posture control proof is missing: {path}",
    )
    require_empty_collection(
        evidence.get("missing_tests"),
        message=f"parity audit failed: visual receipt reports missing required visual tests: {path}",
    )
    required_screenshots = require_canonical_unique_string_list(
        require_string_list(
            evidence.get("required_screenshots"),
            message=f"parity audit failed: visual receipt required_screenshots must be a string array: {path}",
        ),
        field_name="visual receipt required_screenshots",
        path=path,
    )
    expected_required_screenshots = {
        "01-initial-shell-light.png",
        "02-menu-open-light.png",
        "03-settings-open-light.png",
        "04-loaded-runner-light.png",
        "05-dense-section-light.png",
        "06-dense-section-dark.png",
        "07-loaded-runner-tabs-light.png",
        "08-cyberware-dialog-light.png",
        "09-vehicles-section-light.png",
        "10-contacts-section-light.png",
        "11-diary-dialog-light.png",
        "12-magic-dialog-light.png",
        "13-matrix-dialog-light.png",
        "14-advancement-dialog-light.png",
        "15-creation-section-light.png",
    }
    missing_required_screenshots = sorted(expected_required_screenshots.difference(required_screenshots))
    if missing_required_screenshots:
        raise SystemExit(
            "parity audit failed: visual receipt is missing required milestone-2 screenshots: "
            + ", ".join(missing_required_screenshots)
            + f" ({path})"
        )
    unexpected_required_screenshots = sorted(set(required_screenshots).difference(expected_required_screenshots))
    if unexpected_required_screenshots:
        raise SystemExit(
            "parity audit failed: visual receipt declares unexpected milestone-2 screenshots: "
            + ", ".join(unexpected_required_screenshots)
            + f" ({path})"
        )
    require_empty_collection(
        evidence.get("missing_screenshots"),
        message=f"parity audit failed: visual receipt reports missing required screenshots: {path}",
    )
    require_empty_collection(
        evidence.get("invalid_screenshots"),
        message=f"parity audit failed: visual receipt reports invalid screenshots: {path}",
    )
    require_empty_collection(
        evidence.get("undersized_screenshots"),
        message=f"parity audit failed: visual receipt reports undersized screenshots: {path}",
    )
    require_empty_collection(
        evidence.get("stale_screenshots"),
        message=f"parity audit failed: visual receipt reports stale screenshots: {path}",
    )
    require_empty_collection(
        evidence.get("screenshots_older_than_flagship_receipt"),
        message=f"parity audit failed: visual receipt reports screenshots older than flagship receipt: {path}",
    )
    screenshot_dir_raw = require_non_empty_string(
        evidence.get("screenshot_dir"),
        message=f"parity audit failed: visual receipt screenshot_dir is missing: {path}",
    )
    screenshot_dir = resolve_nested_receipt_path(path, screenshot_dir_raw)
    if not screenshot_dir.is_dir():
        raise SystemExit(
            f"parity audit failed: visual receipt screenshot_dir does not exist: {path} ({screenshot_dir})"
        )
    screenshot_timestamps = require_object(
        evidence.get("screenshot_timestamps"),
        message=f"parity audit failed: visual receipt screenshot_timestamps must be a JSON object: {path}",
    )
    screenshot_receipt_skew_max_seconds = read_int_value(
        evidence,
        "screenshot_receipt_skew_max_seconds",
        default_value=DEFAULT_PROOF_FRESHNESS_MAX_AGE_SECONDS,
        path=path,
    )
    for screenshot_name in expected_required_screenshots:
        screenshot_path = screenshot_dir / screenshot_name
        if not screenshot_path.is_file():
            raise SystemExit(
                "parity audit failed: visual receipt required screenshot file is missing on disk: "
                f"{path} ({screenshot_path})"
            )
        timestamp_raw = screenshot_timestamps.get(screenshot_name)
        screenshot_timestamp = parse_generated_at(
            path,
            {"generatedAt": timestamp_raw},
        )
        screenshot_mtime = dt.datetime.fromtimestamp(
            screenshot_path.stat().st_mtime,
            tz=UTC,
        )
        timestamp_skew_seconds = abs(int((screenshot_mtime - screenshot_timestamp).total_seconds()))
        if timestamp_skew_seconds > screenshot_receipt_skew_max_seconds:
            raise SystemExit(
                "parity audit failed: visual receipt screenshot timestamp drifts from on-disk file mtime: "
                f"{path} (screenshot={screenshot_name}, "
                f"timestamp_skew_seconds={timestamp_skew_seconds}, "
                f"max_skew_seconds={screenshot_receipt_skew_max_seconds})"
            )
    validate_timestamp_freshness(path, data, evidence)


def validate_cross_receipt_alignment(
    workflow_path: pathlib.Path,
    workflow_data: dict,
    visual_path: pathlib.Path,
    visual_data: dict,
) -> None:
    workflow_evidence = require_object(
        workflow_data.get("evidence"),
        message=f"parity audit failed: workflow receipt evidence must be a JSON object: {workflow_path}",
    )
    visual_evidence = require_object(
        visual_data.get("evidence"),
        message=f"parity audit failed: visual receipt evidence must be a JSON object: {visual_path}",
    )
    workflow_release_channel_id = require_non_empty_string(
        workflow_evidence.get("release_channel_channel_id"),
        message=f"parity audit failed: workflow receipt release-channel channel id is missing: {workflow_path}",
    )
    visual_release_channel_id = require_non_empty_string(
        visual_evidence.get("release_channel_channel_id"),
        message=f"parity audit failed: visual receipt release-channel channel id is missing: {visual_path}",
    )
    if workflow_release_channel_id != visual_release_channel_id:
        raise SystemExit(
            "parity audit failed: milestone-2 workflow/visual release-channel ids drift: "
            f"{workflow_path} ({workflow_release_channel_id}) vs "
            f"{visual_path} ({visual_release_channel_id})"
        )
    workflow_release_version = require_non_empty_string(
        workflow_evidence.get("release_channel_version"),
        message=f"parity audit failed: workflow receipt release-channel version is missing: {workflow_path}",
    )
    visual_release_version = require_non_empty_string(
        visual_evidence.get("release_channel_version"),
        message=f"parity audit failed: visual receipt release-channel version is missing: {visual_path}",
    )
    if workflow_release_version != visual_release_version:
        raise SystemExit(
            "parity audit failed: milestone-2 workflow/visual release-channel versions drift: "
            f"{workflow_path} ({workflow_release_version}) vs "
            f"{visual_path} ({visual_release_version})"
        )
    workflow_release_channel_path = resolve_release_channel_receipt_path(workflow_path, workflow_evidence)
    visual_release_channel_path = resolve_release_channel_receipt_path(visual_path, visual_evidence)
    if workflow_release_channel_path != visual_release_channel_path:
        raise SystemExit(
            "parity audit failed: milestone-2 workflow/visual release-channel nested receipt paths drift: "
            f"{workflow_path} ({workflow_release_channel_path}) vs "
            f"{visual_path} ({visual_release_channel_path})"
        )
    workflow_release_channel_generated_at = parse_generated_at(
        workflow_path,
        {"generatedAt": workflow_evidence.get("release_channel_generated_at")},
    )
    visual_release_channel_generated_at = parse_generated_at(
        visual_path,
        {"generatedAt": visual_evidence.get("release_channel_generated_at")},
    )
    if workflow_release_channel_generated_at != visual_release_channel_generated_at:
        raise SystemExit(
            "parity audit failed: milestone-2 workflow/visual release-channel generated_at drift: "
            f"{workflow_path} ({workflow_release_channel_generated_at.isoformat()}) vs "
            f"{visual_path} ({visual_release_channel_generated_at.isoformat()})"
        )


if len(sys.argv) != 5:
    raise SystemExit(
        "parity audit failed: expected workflow receipt path, visual receipt path, SR4 workflow ledger path, and "
        "SR6 workflow ledger path"
    )
workflow_path = pathlib.Path(sys.argv[1])
visual_path = pathlib.Path(sys.argv[2])
workflow_ledger_sr4_path = pathlib.Path(sys.argv[3])
workflow_ledger_sr6_path = pathlib.Path(sys.argv[4])
workflow_data = read_receipt(workflow_path)
visual_data = read_receipt(visual_path)
results = [
    (workflow_path, read_status(workflow_path, workflow_data)),
    (visual_path, read_status(visual_path, visual_data)),
]
validate_workflow_contract(workflow_path, workflow_data)
validate_visual_contract(visual_path, visual_data)
validate_cross_receipt_alignment(workflow_path, workflow_data, visual_path, visual_data)
for path, status in results:
    print(f"receipt ok: {path.name} (status={status})")
PY
then
  exit 1
fi

echo "UI Parity Audit"
echo "==============="
echo "$summary_block" | sed '/^[[:space:]]*$/d'
echo
echo "Parity audit passed: parity oracle coverage and executable UI receipts are synchronized."

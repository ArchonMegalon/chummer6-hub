#!/usr/bin/env python3
from __future__ import annotations

import argparse
import errno
import hashlib
import importlib.util
import json
import os
import re
import stat
import sys
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
ATTESTATION_SUPPORT_SCRIPT = (
    ROOT / "scripts" / "verify_detached_ed25519_attestation.py"
)


def _load_attestation_support():
    spec = importlib.util.spec_from_file_location(
        "chummer_detached_ed25519_attestation_for_observability",
        ATTESTATION_SUPPORT_SCRIPT,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("detached attestation support could not be loaded")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


ATTESTATION_SUPPORT = _load_attestation_support()
DEFAULT_POLICY = ROOT / "ops" / "public-edge-observability-policy.json"
DEFAULT_OPERATOR_PROOF = (
    ROOT
    / ".codex-studio"
    / "published"
    / "PUBLIC_EDGE_OBSERVABILITY_OPERATOR_PROOF.generated.json"
)
DEFAULT_OPERATOR_PROOF_INTAKE_SOURCE = (
    ROOT
    / ".state"
    / "incoming_public_edge_observability_operator_proof"
    / "PUBLIC_EDGE_OBSERVABILITY_OPERATOR_PROOF.generated.json"
)
DEFAULT_INTAKE_REQUEST = (
    ROOT
    / ".codex-studio"
    / "published"
    / "PUBLIC_EDGE_OBSERVABILITY_OPERATOR_PROOF_INTAKE_REQUEST.generated.json"
)
DEFAULT_RELEASE_CHANNEL = ROOT / "Chummer.Portal" / "downloads" / "RELEASE_CHANNEL.generated.json"
DEFAULT_OUTPUT = (
    ROOT
    / ".codex-studio"
    / "published"
    / "PUBLIC_EDGE_OBSERVABILITY_RELEASE_GATE.generated.json"
)

POLICY_CONTRACT = "chummer.public_edge_observability_policy.v1"
OPERATOR_PROOF_CONTRACT = "chummer.public_edge_observability_operator_proof.v1"
OPERATOR_ATTESTATION_CONTRACT = (
    "chummer.public_edge_observability_operator_proof_attestation.v1"
)
INTAKE_REQUEST_CONTRACT = (
    "chummer.public_edge_observability_operator_proof_intake_request.v2"
)
GATE_CONTRACT = "chummer.public_edge_observability_release_gate.v1"
MAX_JSON_BYTES = 1024 * 1024
MAX_RUNTIME_SOURCE_BYTES = 8 * 1024 * 1024
TRUSTED_OPERATOR_KEY_ROOT = ROOT / "ops" / "trusted-observability-attesters"
# Deliberately empty until a reviewed change pins a real external operator key.
# Runtime flags and environment variables cannot extend this authority set.
TRUSTED_OPERATOR_ATTESTERS: dict[str, dict[str, str]] = {}
ATTESTATION_NONCE_RE = re.compile(r"^[0-9a-f]{64}$")

OPERATOR_PROOF_FIELDS = {
    "contract_name",
    "status",
    "generated_at_utc",
    "policy_sha256",
    "release_candidate",
    "runtime_source_fingerprint_sha256",
    "monitor_backend",
    "sli_bindings",
    "alert_route",
}
OPERATOR_PROOF_NESTED_FIELDS = {
    "release_candidate": {"sha256", "version", "channel"},
    "monitor_backend": {"provider", "deployment_id", "binding_status"},
    "sli_bindings": {"availability", "latency", "readiness"},
    "alert_route": {
        "receiver_class",
        "binding_status",
        "delivery_tested_at_utc",
        "delivery_test_result",
    },
}
PLACEHOLDER_IDENTIFIERS = {
    "example",
    "placeholder",
    "replace-me",
    "replace_me",
    "tbd",
    "todo",
    "unknown",
}

DEFAULT_RUNTIME_SOURCES = {
    "program": ROOT / "Chummer.Run.Api" / "Program.cs",
    "readiness": ROOT / "Chummer.Run.Api" / "Services" / "HubDeepReadinessService.cs",
    "instruments": ROOT / "Chummer.Run.Api" / "HubRequestObservability.cs",
    "middleware": ROOT / "Chummer.Run.Api" / "HubRequestObservabilityMiddleware.cs",
    "compose": ROOT / "docker-compose.public-edge.yml",
}

RUNTIME_MARKERS = {
    "program": (
        'app.MapMethods("/api/health"',
        'app.MapMethods("/api/ready"',
        "app.UseRouting();",
        "StatusCodes.Status503ServiceUnavailable",
    ),
    "readiness": (
        "durable_storage_writable",
        "canonical_manifest_missing",
        "canonical_manifest_invalid",
        "canonical_manifest_not_published",
    ),
    "instruments": (
        'CreateCounter<long>("chummer.run.api.requests.completed")',
        'CreateHistogram<double>("chummer.run.api.requests.duration.ms")',
    ),
    "middleware": (
        "ResolveMetricRoute(context)",
        "ResolveMetricMethod(context.Request.Method)",
        "IsSafeForwardedCorrelationId(candidate)",
        "HubRequestObservability.MetricRouteFallback",
        'new("http.route", route)',
        'activity?.SetTag("http.route", route)',
        "RequestsCompleted.Add",
        "RequestDurationMs.Record",
        '"http.status_code"',
    ),
    "compose": (
        "http://127.0.0.1:8080/api/ready",
        "chummer-run-api-state:/app/state",
    ),
}

RUNTIME_FORBIDDEN_MARKERS = {
    "middleware": (
        "context.Request.Path",
        "context.Request.QueryString",
        'new("chummer.correlation_id"',
        'SetTag("url.path"',
        'SetTag("chummer.correlation_id"',
        '["RequestPath"]',
    ),
}


def utc_now() -> datetime:
    return datetime.now(UTC)


def iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def parse_time(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(UTC)


def load_json(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    payload, error, _ = load_json_with_sha256(path)
    return payload, error


def load_json_with_sha256(
    path: Path,
) -> tuple[dict[str, Any] | None, str | None, str | None]:
    payload, error, digest, _ = load_json_snapshot(path)
    return payload, error, digest


def load_json_snapshot(
    path: Path,
) -> tuple[dict[str, Any] | None, str | None, str | None, bytes | None]:
    raw, error = read_regular_file_bytes(path)
    if error is not None or raw is None:
        return None, error, None, raw
    digest = hashlib.sha256(raw).hexdigest()
    try:
        payload = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None, "invalid_json", digest, raw
    if not isinstance(payload, dict):
        return None, "not_an_object", digest, raw
    return payload, None, digest, raw


def read_regular_file_bytes(
    path: Path,
    *,
    max_bytes: int = MAX_JSON_BYTES,
) -> tuple[bytes | None, str | None]:
    """Capture one stable regular-file snapshot without following a final symlink."""

    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags)
    except FileNotFoundError:
        return None, "missing"
    except OSError as exc:
        if exc.errno == errno.ELOOP:
            return None, "symlink_rejected"
        return None, "unreadable"
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode):
            return None, "not_a_regular_file"
        if before.st_size > max_bytes:
            return None, "too_large"

        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = os.read(fd, min(65536, max_bytes + 1 - total))
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
            if total > max_bytes:
                return None, "too_large"

        after = os.fstat(fd)
        stable_fields = ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")
        if any(getattr(before, field) != getattr(after, field) for field in stable_fields):
            return None, "changed_during_read"
        return b"".join(chunks), None
    except OSError:
        return None, "unreadable"
    finally:
        os.close(fd)


def canonical_sha256(value: object) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def canonical_json_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def detached_operator_attestation_path(proof_path: Path) -> Path:
    return proof_path.with_name(proof_path.name + ".attestation.json")


def operator_attestation_bindings(
    *,
    policy_sha256: str,
    release_candidate: dict[str, Any],
    runtime_binding: dict[str, Any],
) -> dict[str, Any]:
    return {
        "policy_sha256": policy_sha256,
        "release_candidate": {
            "sha256": release_candidate.get("sha256"),
            "version": release_candidate.get("version"),
            "channel": release_candidate.get("channel"),
        },
        "runtime_source_fingerprint_sha256": runtime_binding.get(
            "aggregate_sha256"
        ),
    }


def validate_operator_attestation(
    attestation: dict[str, Any],
    *,
    proof_bytes: bytes,
    request: dict[str, Any],
    request_sha256: str,
    expected_bindings: dict[str, Any],
    now: datetime,
) -> tuple[dict[str, Any], list[str]]:
    subject_sha256 = hashlib.sha256(proof_bytes).hexdigest()
    request_nonce = str(request.get("challenge_nonce") or "").lower()
    request_generated_at = parse_time(request.get("generated_at_utc"))
    return ATTESTATION_SUPPORT.verify_detached_attestation(
        attestation,
        contract_name=OPERATOR_ATTESTATION_CONTRACT,
        role="observability_operator",
        exact_claims={
            "subject_sha256": subject_sha256,
            "challenge_nonce": request_nonce,
            "request_sha256": request_sha256,
            "bindings": expected_bindings,
        },
        trusted_identities=TRUSTED_OPERATOR_ATTESTERS,
        trusted_key_root=TRUSTED_OPERATOR_KEY_ROOT,
        now=now,
        max_age=timedelta(hours=24),
        request_generated_at=request_generated_at,
    )


def validate_intake_request(
    request: dict[str, Any],
    *,
    expected_bindings: dict[str, Any],
) -> list[str]:
    failures: list[str] = []
    if request.get("contract_name") != INTAKE_REQUEST_CONTRACT:
        failures.append(f"contract_name must be {INTAKE_REQUEST_CONTRACT}")
    if request.get("status") != "ready" or request.get("verdict") != "INTAKE_REQUEST_READY":
        failures.append("intake request must be ready")
    if request.get("failures") or int(request.get("failure_count") or 0) != 0:
        failures.append("intake request records failures")
    nonce = str(request.get("challenge_nonce") or "").lower()
    if not ATTESTATION_NONCE_RE.fullmatch(nonce):
        failures.append("challenge_nonce must be a 64-character lowercase hex nonce")

    current = request.get("current_bindings")
    current = current if isinstance(current, dict) else {}
    request_bindings = {
        "policy_sha256": (
            current.get("policy", {}).get("sha256")
            if isinstance(current.get("policy"), dict)
            else None
        ),
        "release_candidate": {
            key: (
                current.get("release_candidate", {}).get(key)
                if isinstance(current.get("release_candidate"), dict)
                else None
            )
            for key in ("sha256", "version", "channel")
        },
        "runtime_source_fingerprint_sha256": (
            current.get("runtime_source_binding", {}).get("aggregate_sha256")
            if isinstance(current.get("runtime_source_binding"), dict)
            else None
        ),
    }
    if request_bindings != expected_bindings:
        failures.append("current_bindings do not match current policy, release, and runtime")
    if current.get("binding_sha256") != canonical_sha256(expected_bindings):
        failures.append("current_bindings.binding_sha256 is invalid")
    return failures


def inspect_runtime_sources(
    runtime_sources: dict[str, Path] | None = None,
) -> tuple[list[dict[str, str]], list[str], dict[str, Any]]:
    """Validate and bind one stable byte snapshot of every runtime source."""

    sources = runtime_sources or DEFAULT_RUNTIME_SOURCES
    snapshots: dict[str, dict[str, Any]] = {}
    for source_id in sorted(RUNTIME_MARKERS):
        path = sources.get(source_id)
        if path is None:
            raw = None
            load_error = "missing"
        else:
            raw, load_error = read_regular_file_bytes(
                path,
                max_bytes=MAX_RUNTIME_SOURCE_BYTES,
            )
        snapshots[source_id] = {
            "path": path,
            "raw": raw,
            "load_status": load_error or "loaded",
        }

    checks: list[dict[str, str]] = []
    failures: list[str] = []
    for source_id, markers in RUNTIME_MARKERS.items():
        snapshot = snapshots[source_id]
        raw = snapshot["raw"]
        if raw is None:
            load_status = str(snapshot["load_status"])
            add_check(
                checks,
                failures,
                f"runtime:{source_id}",
                False,
                f"required source is {load_status}",
            )
            continue
        try:
            source = raw.decode("utf-8")
        except UnicodeDecodeError:
            snapshot["load_status"] = "invalid_utf8"
            add_check(
                checks,
                failures,
                f"runtime:{source_id}",
                False,
                "required source is invalid_utf8",
            )
            continue
        missing = [marker for marker in markers if marker not in source]
        forbidden = [
            marker
            for marker in RUNTIME_FORBIDDEN_MARKERS.get(source_id, ())
            if marker in source
        ]
        add_check(
            checks,
            failures,
            f"runtime:{source_id}",
            not missing and not forbidden,
            "required runtime contract is present"
            if not missing and not forbidden
            else (
                f"missing {len(missing)} required runtime marker(s); "
                f"found {len(forbidden)} forbidden high-cardinality/privacy marker(s)"
            ),
        )

    rows: list[dict[str, Any]] = []
    fingerprint_rows: list[dict[str, str | None]] = []
    for source_id in sorted(RUNTIME_MARKERS):
        snapshot = snapshots[source_id]
        path = snapshot["path"]
        raw = snapshot["raw"]
        digest = hashlib.sha256(raw).hexdigest() if raw is not None else None
        load_status = str(snapshot["load_status"])
        rows.append(
            {
                "id": source_id,
                "path": str(path) if path is not None else None,
                "load_status": load_status,
                "sha256": digest,
            }
        )
        fingerprint_rows.append({"id": source_id, "sha256": digest})
    binding = {
        "algorithm": "sha256-canonical-json-v1",
        "aggregate_sha256": canonical_sha256(fingerprint_rows),
        "sources": rows,
    }
    return checks, failures, binding


def runtime_source_binding(
    runtime_sources: dict[str, Path] | None = None,
) -> dict[str, Any]:
    _, _, binding = inspect_runtime_sources(runtime_sources)
    return binding


def release_candidate_binding(
    release_channel_path: Path,
) -> tuple[dict[str, Any], dict[str, Any] | None, str | None, list[str]]:
    payload, load_error, manifest_digest = load_json_with_sha256(release_channel_path)
    binding: dict[str, Any] = {
        "path": str(release_channel_path),
        "load_status": load_error or "loaded",
        "sha256": None,
        "version": None,
        "channel": None,
        "status": None,
        "rollout_state": None,
        "supportability_state": None,
        "published_at_utc": None,
    }
    failures: list[str] = []
    if load_error is not None or payload is None:
        failures.append(f"release channel is {load_error}")
        return binding, payload, load_error, failures

    binding.update(
        {
            "sha256": manifest_digest,
            "version": str(payload.get("releaseVersion") or payload.get("version") or "").strip()
            or None,
            "channel": str(payload.get("channel") or payload.get("channelId") or "").strip()
            or None,
            "status": str(payload.get("status") or "").strip() or None,
            "rollout_state": str(payload.get("rolloutState") or "").strip() or None,
            "supportability_state": str(payload.get("supportabilityState") or "").strip()
            or None,
            "published_at_utc": str(
                payload.get("publishedAt")
                or payload.get("generatedAt")
                or payload.get("generated_at")
                or ""
            ).strip()
            or None,
        }
    )
    if binding["version"] is None:
        failures.append("release version is missing")
    if binding["channel"] is None:
        failures.append("release channel is missing")
    if binding["status"] != "published":
        failures.append("release status must be published")
    if parse_time(binding["published_at_utc"]) is None:
        failures.append("release published timestamp must be timezone-aware")
    return binding, payload, load_error, failures


def add_check(
    checks: list[dict[str, str]],
    failures: list[str],
    check_id: str,
    passed: bool,
    detail: str,
) -> None:
    checks.append(
        {
            "id": check_id,
            "status": "pass" if passed else "fail",
            "detail": detail,
        }
    )
    if not passed:
        failures.append(f"{check_id}: {detail}")


def validate_runtime_contracts(
    runtime_sources: dict[str, Path] | None = None,
) -> tuple[list[dict[str, str]], list[str]]:
    checks, failures, _ = inspect_runtime_sources(runtime_sources)
    return checks, failures


def validate_policy(policy: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    if policy.get("contract_name") != POLICY_CONTRACT:
        failures.append(f"contract_name must be {POLICY_CONTRACT}")
    if policy.get("service") != "chummer.run.api":
        failures.append("service must be chummer.run.api")

    window = policy.get("measurement_window_days")
    if not isinstance(window, int) or window < 7:
        failures.append("measurement_window_days must be an integer of at least 7")

    slis = policy.get("slis")
    if not isinstance(slis, dict):
        failures.append("slis must be an object")
    else:
        availability = slis.get("availability")
        latency = slis.get("latency")
        readiness = slis.get("readiness")
        if not isinstance(availability, dict) or availability.get("metric") != "chummer.run.api.requests.completed":
            failures.append("availability SLI must bind chummer.run.api.requests.completed")
        if not isinstance(latency, dict) or latency.get("metric") != "chummer.run.api.requests.duration.ms":
            failures.append("latency SLI must bind chummer.run.api.requests.duration.ms")
        if not isinstance(latency, dict) or not isinstance(latency.get("threshold_ms"), (int, float)) or latency.get("threshold_ms", 0) <= 0:
            failures.append("latency SLI threshold_ms must be positive")
        if not isinstance(readiness, dict) or readiness.get("route") != "/api/ready" or readiness.get("success_status") != 200:
            failures.append("readiness SLI must bind HTTP 200 on /api/ready")

    dimensions = policy.get("metric_dimensions")
    if not isinstance(dimensions, dict):
        failures.append("metric_dimensions must be an object")
    else:
        allowed_labels = dimensions.get("allowed_labels")
        if not isinstance(allowed_labels, list) or set(allowed_labels) != {
            "http.method",
            "http.route",
            "http.status_code",
        }:
            failures.append(
                "metric_dimensions.allowed_labels must contain only method, route, and status"
            )
        if dimensions.get("route_source") != "matched_route_template":
            failures.append("metric_dimensions.route_source must be matched_route_template")
        if dimensions.get("unmatched_route_value") != "__unmatched__":
            failures.append("metric_dimensions.unmatched_route_value must be __unmatched__")
        if dimensions.get("method_fallback_value") != "OTHER":
            failures.append("metric_dimensions.method_fallback_value must be OTHER")
        for key in ("include_correlation_id", "include_raw_path", "include_query"):
            if dimensions.get(key) is not False:
                failures.append(f"metric_dimensions.{key} must be false")

    evidence_binding = policy.get("evidence_binding")
    expected_evidence_binding = {
        "operator_proof_digest_algorithm": "sha256",
        "release_candidate_digest_source": "release_channel_manifest_bytes",
        "runtime_source_fingerprint_algorithm": "sha256-canonical-json-v1",
    }
    if not isinstance(evidence_binding, dict):
        failures.append("evidence_binding must be an object")
    else:
        for key, expected in expected_evidence_binding.items():
            if evidence_binding.get(key) != expected:
                failures.append(f"evidence_binding.{key} must be {expected}")

    slo = policy.get("slo")
    availability_target = slo.get("availability_percent") if isinstance(slo, dict) else None
    latency_target = slo.get("latency_good_event_percent") if isinstance(slo, dict) else None
    if not isinstance(availability_target, (int, float)) or not 0 < availability_target < 100:
        failures.append("slo.availability_percent must be between 0 and 100")
    if not isinstance(latency_target, (int, float)) or not 0 < latency_target <= 100:
        failures.append("slo.latency_good_event_percent must be between 0 and 100")

    budget = policy.get("error_budget")
    budget_percent = budget.get("availability_percent") if isinstance(budget, dict) else None
    if (
        not isinstance(budget_percent, (int, float))
        or not isinstance(availability_target, (int, float))
        or abs((100.0 - float(availability_target)) - float(budget_percent)) > 1e-9
    ):
        failures.append("error budget must equal 100 minus the availability SLO")
    if not isinstance(budget, dict) or not str(budget.get("promotion_policy") or "").strip():
        failures.append("error budget promotion_policy is required")

    alerts = policy.get("burn_rate_alerts")
    severities: set[str] = set()
    if not isinstance(alerts, list) or not alerts:
        failures.append("burn_rate_alerts must be a non-empty array")
    else:
        for index, alert in enumerate(alerts):
            if not isinstance(alert, dict):
                failures.append(f"burn_rate_alerts[{index}] must be an object")
                continue
            severity = str(alert.get("severity") or "").strip()
            severities.add(severity)
            numeric = (
                alert.get("short_window_minutes"),
                alert.get("long_window_minutes"),
                alert.get("burn_rate_threshold"),
            )
            if any(not isinstance(value, (int, float)) or value <= 0 for value in numeric):
                failures.append(f"burn_rate_alerts[{index}] windows and threshold must be positive")
            elif float(numeric[0]) >= float(numeric[1]):
                failures.append(f"burn_rate_alerts[{index}] short window must be shorter than long window")
    if not {"page", "ticket"}.issubset(severities):
        failures.append("burn_rate_alerts must define page and ticket severities")

    routing = policy.get("alert_routing")
    if not isinstance(routing, dict):
        failures.append("alert_routing must be an object")
    else:
        for key in ("owner", "receiver_class"):
            if not str(routing.get(key) or "").strip():
                failures.append(f"alert_routing.{key} is required")
        for key in ("operator_proof_max_age_hours", "delivery_test_max_age_hours"):
            value = routing.get(key)
            if not isinstance(value, (int, float)) or value <= 0:
                failures.append(f"alert_routing.{key} must be positive")
    return failures


def _unexpected_fields(
    value: dict[str, Any],
    *,
    allowed: set[str],
    path: str,
) -> list[str]:
    unexpected_count = len(set(value) - allowed)
    if unexpected_count == 0:
        return []
    return [f"{path} contains {unexpected_count} unsupported field(s)"]


def _is_placeholder_identifier(value: object) -> bool:
    if not isinstance(value, str):
        return True
    normalized = value.strip().casefold()
    return (
        not normalized
        or normalized in PLACEHOLDER_IDENTIFIERS
        or (normalized.startswith("<") and normalized.endswith(">"))
        or normalized.startswith("replace-")
        or normalized.startswith("replace_")
    )


def validate_operator_proof(
    proof: dict[str, Any],
    *,
    policy: dict[str, Any],
    policy_digest: str,
    release_candidate: dict[str, Any],
    runtime_binding: dict[str, Any],
    now: datetime,
) -> list[str]:
    failures: list[str] = _unexpected_fields(
        proof,
        allowed=OPERATOR_PROOF_FIELDS,
        path="operator_proof",
    )
    if proof.get("contract_name") != OPERATOR_PROOF_CONTRACT:
        failures.append(f"contract_name must be {OPERATOR_PROOF_CONTRACT}")
    if proof.get("status") != "pass":
        failures.append("status must be pass")
    if proof.get("policy_sha256") != policy_digest:
        failures.append("policy_sha256 does not bind the current policy")

    proof_release = proof.get("release_candidate")
    if not isinstance(proof_release, dict):
        failures.append("release_candidate must be an object")
    else:
        failures.extend(
            _unexpected_fields(
                proof_release,
                allowed=OPERATOR_PROOF_NESTED_FIELDS["release_candidate"],
                path="release_candidate",
            )
        )
        for key in ("sha256", "version", "channel"):
            if proof_release.get(key) != release_candidate.get(key):
                failures.append(
                    f"release_candidate.{key} does not bind the current release candidate"
                )

    if (
        proof.get("runtime_source_fingerprint_sha256")
        != runtime_binding.get("aggregate_sha256")
    ):
        failures.append(
            "runtime_source_fingerprint_sha256 does not bind the current runtime sources"
        )

    routing = policy.get("alert_routing")
    routing = routing if isinstance(routing, dict) else {}
    generated_at = parse_time(proof.get("generated_at_utc"))
    if generated_at is None:
        failures.append("generated_at_utc must be a timezone-aware timestamp")
    else:
        if generated_at > now + timedelta(minutes=5):
            failures.append("operator proof timestamp is in the future")
        max_age = float(routing.get("operator_proof_max_age_hours") or 0)
        if generated_at < now - timedelta(hours=max_age):
            failures.append("operator proof is stale")

    backend = proof.get("monitor_backend")
    if not isinstance(backend, dict):
        failures.append("monitor_backend must be an object")
    else:
        failures.extend(
            _unexpected_fields(
                backend,
                allowed=OPERATOR_PROOF_NESTED_FIELDS["monitor_backend"],
                path="monitor_backend",
            )
        )
        for key in ("provider", "deployment_id"):
            if _is_placeholder_identifier(backend.get(key)):
                failures.append(
                    f"monitor_backend.{key} must be a non-placeholder identifier"
                )
        if backend.get("binding_status") != "verified":
            failures.append("monitor_backend.binding_status must be verified")

    bindings = proof.get("sli_bindings")
    if not isinstance(bindings, dict):
        failures.append("sli_bindings must be an object")
    else:
        failures.extend(
            _unexpected_fields(
                bindings,
                allowed=OPERATOR_PROOF_NESTED_FIELDS["sli_bindings"],
                path="sli_bindings",
            )
        )
        for key in ("availability", "latency", "readiness"):
            if bindings.get(key) is not True:
                failures.append(f"sli_bindings.{key} must be true")

    route = proof.get("alert_route")
    if not isinstance(route, dict):
        failures.append("alert_route must be an object")
    else:
        failures.extend(
            _unexpected_fields(
                route,
                allowed=OPERATOR_PROOF_NESTED_FIELDS["alert_route"],
                path="alert_route",
            )
        )
        expected_receiver = routing.get("receiver_class")
        if route.get("receiver_class") != expected_receiver:
            failures.append("alert_route.receiver_class does not match policy")
        if route.get("binding_status") != "verified":
            failures.append("alert_route.binding_status must be verified")
        if route.get("delivery_test_result") != "delivered":
            failures.append("alert_route.delivery_test_result must be delivered")
        tested_at = parse_time(route.get("delivery_tested_at_utc"))
        if tested_at is None:
            failures.append("alert_route.delivery_tested_at_utc must be timezone-aware")
        else:
            if tested_at > now + timedelta(minutes=5):
                failures.append("alert delivery test timestamp is in the future")
            if generated_at is not None and tested_at > generated_at + timedelta(minutes=5):
                failures.append("alert delivery test timestamp is later than operator proof")
            max_age = float(routing.get("delivery_test_max_age_hours") or 0)
            if tested_at < now - timedelta(hours=max_age):
                failures.append("alert delivery test is stale")
    return failures


def build_receipt(
    *,
    policy_path: Path,
    operator_proof_path: Path,
    release_channel_path: Path = DEFAULT_RELEASE_CHANNEL,
    intake_request_path: Path = DEFAULT_INTAKE_REQUEST,
    operator_attestation_path: Path | None = None,
    runtime_sources: dict[str, Path] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    observed_at = (now or utc_now()).astimezone(UTC)
    checks, failures, runtime_binding = inspect_runtime_sources(runtime_sources)
    operator_dependencies: list[str] = []

    release_candidate, _, _, release_failures = release_candidate_binding(
        release_channel_path
    )
    add_check(
        checks,
        failures,
        "release_candidate",
        not release_failures,
        "current release version, channel, and manifest digest are bound"
        if not release_failures
        else "; ".join(release_failures),
    )

    policy, policy_error, policy_digest = load_json_with_sha256(policy_path)
    if policy_error is not None or policy is None:
        add_check(checks, failures, "policy", False, f"policy is {policy_error}")
    else:
        policy_failures = validate_policy(policy)
        add_check(
            checks,
            failures,
            "policy",
            not policy_failures,
            "SLI/SLO/error-budget policy is valid"
            if not policy_failures
            else "; ".join(policy_failures),
        )

    proof, proof_error, proof_digest, proof_bytes = load_json_snapshot(
        operator_proof_path
    )
    if proof_error is not None or proof is None:
        add_check(checks, failures, "operator_proof", False, f"operator proof is {proof_error}")
        operator_dependencies.append(
            "Bind the three SLIs to a real monitoring backend and import a fresh operator proof."
        )
    elif policy is None or policy_digest is None:
        add_check(checks, failures, "operator_proof", False, "policy could not be loaded")
    else:
        proof_failures = validate_operator_proof(
            proof,
            policy=policy,
            policy_digest=policy_digest,
            release_candidate=release_candidate,
            runtime_binding=runtime_binding,
            now=observed_at,
        )
        add_check(
            checks,
            failures,
            "operator_proof",
            not proof_failures,
            "monitor and alert delivery proof is current"
            if not proof_failures
            else "; ".join(proof_failures),
        )
        if proof_failures:
            operator_dependencies.append(
                "Refresh the monitor binding and alert-delivery test, then regenerate operator proof."
            )

    expected_bindings = operator_attestation_bindings(
        policy_sha256=policy_digest or "",
        release_candidate=release_candidate,
        runtime_binding=runtime_binding,
    )
    request, request_error, request_digest, _ = load_json_snapshot(
        intake_request_path
    )
    request_failures: list[str] = []
    if request_error is not None or request is None or request_digest is None:
        request_failures.append(f"intake request is {request_error}")
    else:
        request_failures.extend(
            validate_intake_request(request, expected_bindings=expected_bindings)
        )
    add_check(
        checks,
        failures,
        "operator_intake_request",
        not request_failures,
        "exact current external-proof challenge is valid"
        if not request_failures
        else "; ".join(request_failures),
    )

    attestation_path = operator_attestation_path or detached_operator_attestation_path(
        operator_proof_path
    )
    attestation, attestation_error, attestation_digest, _ = load_json_snapshot(
        attestation_path
    )
    attestation_summary: dict[str, Any] = {
        "contract_name": None,
        "status": "fail",
        "key_id": None,
    }
    attestation_failures: list[str] = []
    if attestation_error is not None or attestation is None:
        attestation_failures.append(f"detached attestation is {attestation_error}")
    elif proof_bytes is None:
        attestation_failures.append("exact operator proof bytes are unavailable")
    elif request is None or request_digest is None or request_failures:
        attestation_failures.append("current intake request challenge is invalid")
    else:
        attestation_summary, attestation_failures = validate_operator_attestation(
            attestation,
            proof_bytes=proof_bytes,
            request=request,
            request_sha256=request_digest,
            expected_bindings=expected_bindings,
            now=observed_at,
        )
    add_check(
        checks,
        failures,
        "operator_attestation",
        not attestation_failures,
        "external operator authority signature is valid and challenge-bound"
        if not attestation_failures
        else "; ".join(attestation_failures),
    )
    if attestation_failures:
        operator_dependencies.append(
            "Obtain a detached Ed25519 attestation from a code-pinned external operator identity for the current intake challenge."
        )

    passed = not failures
    if proof_error == "missing":
        intake_state = "waiting_for_external_proof"
        next_action = (
            "Obtain a real monitoring-backend binding and delivered alert test, then "
            "validate and import that external JSON with "
            "scripts/import_public_edge_observability_operator_proof.py."
        )
    elif proof_error is not None:
        intake_state = "source_rejected"
        next_action = (
            "Replace the rejected canonical proof via the guarded importer; do not edit, "
            "restamp, or repair evidence in place."
        )
    elif any(
        check["id"] in {
            "operator_proof",
            "operator_intake_request",
            "operator_attestation",
        }
        and check["status"] == "fail"
        for check in checks
    ):
        intake_state = "proof_invalid_or_expired"
        next_action = (
            "Run a new real monitor binding and alert-delivery test for the current bindings, "
            "then import the resulting proof; do not restamp prior evidence."
        )
    else:
        intake_state = "proof_verified"
        next_action = "No operator-proof intake action is required."
    return {
        "contract_name": GATE_CONTRACT,
        "status": "pass" if passed else "fail",
        "verdict": "OBSERVABILITY_RELEASE_READY" if passed else "OBSERVABILITY_RELEASE_BLOCKED",
        "generated_at_utc": iso(observed_at),
        "policy": {
            "path": str(policy_path),
            "sha256": policy_digest,
        },
        "release_candidate": release_candidate,
        "runtime_source_binding": runtime_binding,
        "operator_proof": {
            "path": str(operator_proof_path),
            "load_status": proof_error or "loaded",
            "sha256": proof_digest,
            "contract_name": proof.get("contract_name") if proof is not None else None,
            "status": proof.get("status") if proof is not None else None,
            "generated_at_utc": proof.get("generated_at_utc") if proof is not None else None,
            "alert_delivery_tested_at_utc": (
                proof.get("alert_route", {}).get("delivery_tested_at_utc")
                if isinstance(proof, dict) and isinstance(proof.get("alert_route"), dict)
                else None
            ),
            "alert_delivery_test_result": (
                proof.get("alert_route", {}).get("delivery_test_result")
                if isinstance(proof, dict) and isinstance(proof.get("alert_route"), dict)
                else None
            ),
        },
        "operator_intake_request": {
            "path": str(intake_request_path),
            "load_status": request_error or "loaded",
            "sha256": request_digest,
            "contract_name": request.get("contract_name") if request is not None else None,
            "status": request.get("status") if request is not None else None,
            "challenge_nonce": request.get("challenge_nonce") if request is not None else None,
        },
        "operator_attestation": {
            "path": str(attestation_path),
            "load_status": attestation_error or "loaded",
            "sha256": attestation_digest,
            **attestation_summary,
        },
        "operator_intake": {
            "state": intake_state,
            "external_evidence_required": intake_state != "proof_verified",
            "canonical_path": str(operator_proof_path),
            "expected_source_path": str(DEFAULT_OPERATOR_PROOF_INTAKE_SOURCE),
            "required_contract": OPERATOR_PROOF_CONTRACT,
            "required_attestation_contract": OPERATOR_ATTESTATION_CONTRACT,
            "trusted_identity_count": len(TRUSTED_OPERATOR_ATTESTERS),
            "guarded_import_command": (
                "python3 scripts/import_public_edge_observability_operator_proof.py "
                "--import-proof"
            ),
            "sends_alerts": False,
            "configures_monitoring": False,
            "next_action": next_action,
        },
        "checks": checks,
        "failure_count": len(failures),
        "failures": failures,
        "operator_dependencies": operator_dependencies,
    }


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    except BaseException:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass
        raise


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fail closed unless public-edge telemetry, SLO policy, and real operator alert proof agree."
    )
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    parser.add_argument("--operator-proof", type=Path, default=DEFAULT_OPERATOR_PROOF)
    parser.add_argument("--intake-request", type=Path, default=DEFAULT_INTAKE_REQUEST)
    parser.add_argument("--operator-attestation", type=Path)
    parser.add_argument("--release-channel", type=Path, default=DEFAULT_RELEASE_CHANNEL)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    receipt = build_receipt(
        policy_path=args.policy,
        operator_proof_path=args.operator_proof,
        release_channel_path=args.release_channel,
        intake_request_path=args.intake_request,
        operator_attestation_path=args.operator_attestation,
    )
    atomic_write_json(args.output, receipt)
    print(f"public_edge_observability_release_gate:{receipt['status']}")
    return 0 if receipt["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())

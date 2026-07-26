#!/usr/bin/env python3
"""Governed Cloudflare Tunnel ingress transaction for public downloads.

The module deliberately has no Cloudflare SDK dependency.  It exposes pure
configuration planning/validation helpers and a small, durable transaction
state machine that can be driven either from Python or from the CLI.
"""

from __future__ import annotations

import argparse
import copy
import datetime as dt
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import stat
import sys
import time
from types import TracebackType
from typing import Any, Callable, Mapping, Protocol, Sequence
import urllib.error
import urllib.parse
import urllib.request


SCHEMA = "cloudflare-public-download-ingress-transaction/v2"
EXTERNAL_PROBE_SCHEMA = "cloudflare-public-download-external-probe/v2"
PHASES = frozenset(
    {
        "captured",
        "apply-in-flight",
        "applied",
        "awaiting-external-probe",
        "rollback-in-flight",
        "rolled-back",
        "committed",
    }
)
MANAGED_HOSTS = ("chummer.run", "www.chummer.run")
# Go/RE2-compatible: capturing groups only; no lookaround or backreferences.
GENERATION_ID_RE2 = r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}"
PORTABLE_FILE_LEAF_RE2 = r"[A-Za-z0-9][A-Za-z0-9._+-]{0,254}"
PUBLIC_INSTALL_ARTIFACT_ID_RE2 = r"[a-z0-9][a-z0-9-]{0,127}"
PUBLIC_RELEASE_TRUTH_PATH_RE2 = (
    r"/api/(v1/)?public/release-truth(/g/"
    + GENERATION_ID_RE2
    + r")?"
)
CURRENT_PUBLIC_INSTALL_PATH_RE2 = (
    r"/downloads/install/"
    + PUBLIC_INSTALL_ARTIFACT_ID_RE2
    + r"(/(payload|metadata))?"
)
CURRENT_PUBLIC_DOWNLOAD_PATH_RE2 = (
    r"/downloads/get/"
    + PUBLIC_INSTALL_ARTIFACT_ID_RE2
)
GENERATION_PUBLIC_INSTALL_PATH_RE2 = (
    r"/downloads/g/"
    + GENERATION_ID_RE2
    + r"/install/"
    + PUBLIC_INSTALL_ARTIFACT_ID_RE2
    + r"(/(payload|metadata))?"
)
MANAGED_CONTROL_PATHS = (
    "/api/ready/public-downloads",
    "/api/ready",
    "/api/ready/publication",
    "/api/ready/install-linking-authority",
    "/api/v1/install-linking/me",
    "/account/access/install-link",
    "/downloads/install/public-download-only-probe",
)
MANAGED_PUBLIC_PAGE_PATHS = (
    "/downloads",
    "/status",
)
MANAGED_CONTROL_PATH_RE2 = "|".join(MANAGED_CONTROL_PATHS)
MANAGED_PUBLIC_PAGE_PATH_RE2 = "|".join(
    path + r"/?"
    for path in MANAGED_PUBLIC_PAGE_PATHS
)
MANAGED_PATH_RE2 = (
    r"^("
    + MANAGED_PUBLIC_PAGE_PATH_RE2
    + r"|"
    + MANAGED_CONTROL_PATH_RE2
    + r"|"
    + PUBLIC_RELEASE_TRUTH_PATH_RE2
    + r"|"
    + GENERATION_PUBLIC_INSTALL_PATH_RE2
    + r"|"
    + CURRENT_PUBLIC_INSTALL_PATH_RE2
    + r"|"
    + CURRENT_PUBLIC_DOWNLOAD_PATH_RE2
    + r"|/downloads/"
    r"(releases\.json|RELEASE_CHANNEL\.generated\.json|g/"
    + GENERATION_ID_RE2
    + r"/(releases\.json|RELEASE_CHANNEL\.generated\.json|files/"
    + PORTABLE_FILE_LEAF_RE2
    + r")|files/"
    + PORTABLE_FILE_LEAF_RE2
    + r"))$"
)
PUBLIC_INSTALL_SINGLE_SEGMENT_FAIL_CLOSED_RE2 = (
    r"^/[dD][oO][wW][nN][lL][oO][aA][dD][sS]"
    r"/[iI][nN][sS][tT][aA][lL][lL]/[^/]+/?$"
)
PUBLIC_INSTALL_DOT_SEGMENT_FAIL_CLOSED_RE2 = (
    r"^/[dD][oO][wW][nN][lL][oO][aA][dD][sS]"
    r"/[iI][nN][sS][tT][aA][lL][lL]/(.*?/)?\.\.?(/.*)?$"
)
CURRENT_INSTALL_COMPANION_FAIL_CLOSED_RE2 = (
    r"^/[dD][oO][wW][nN][lL][oO][aA][dD][sS]"
    r"/[iI][nN][sS][tT][aA][lL][lL]/[^/]+/"
    r"([pP][aA][yY][lL][oO][aA][dD]"
    r"|[mM][eE][tT][aA][dD][aA][tT][aA])(/.*)?$"
)
CURRENT_DOWNLOAD_NAMESPACE_FAIL_CLOSED_RE2 = (
    r"^/[dD][oO][wW][nN][lL][oO][aA][dD][sS]"
    r"/[gG][eE][tT](/.*)?$"
)
GENERATION_INSTALL_NAMESPACE_FAIL_CLOSED_RE2 = (
    r"^/[dD][oO][wW][nN][lL][oO][aA][dD][sS]/[gG]/(.*?/)?"
    r"[iI][nN][sS][tT][aA][lL][lL](/.*)?$"
)
CURRENT_FILES_NAMESPACE_FAIL_CLOSED_RE2 = (
    r"^/[dD][oO][wW][nN][lL][oO][aA][dD][sS]"
    r"/[fF][iI][lL][eE][sS](/.*)?$"
)
GENERATION_FILES_NAMESPACE_FAIL_CLOSED_RE2 = (
    r"^/[dD][oO][wW][nN][lL][oO][aA][dD][sS]/[gG]/(.*?/)?"
    r"[fF][iI][lL][eE][sS](/.*)?$"
)
RELEASE_TRUTH_NAMESPACE_FAIL_CLOSED_RE2 = (
    r"^/[aA][pP][iI]/([vV]1/)?[pP][uU][bB][lL][iI][cC]"
    r"/[rR][eE][lL][eE][aA][sS][eE]-[tT][rR][uU][tT][hH](/.*)?$"
)
FAIL_CLOSED_PATHS_RE2 = (
    PUBLIC_INSTALL_SINGLE_SEGMENT_FAIL_CLOSED_RE2,
    PUBLIC_INSTALL_DOT_SEGMENT_FAIL_CLOSED_RE2,
    CURRENT_INSTALL_COMPANION_FAIL_CLOSED_RE2,
    CURRENT_DOWNLOAD_NAMESPACE_FAIL_CLOSED_RE2,
    GENERATION_INSTALL_NAMESPACE_FAIL_CLOSED_RE2,
    CURRENT_FILES_NAMESPACE_FAIL_CLOSED_RE2,
    GENERATION_FILES_NAMESPACE_FAIL_CLOSED_RE2,
    RELEASE_TRUTH_NAMESPACE_FAIL_CLOSED_RE2,
)
SAFE_GENERATION_ID = re.compile(r"^" + GENERATION_ID_RE2 + r"$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
JOURNAL_FIELDS = frozenset(
    {
        "schema",
        "phase",
        "accountId",
        "tunnelId",
        "origin",
        "createdAt",
        "updatedAt",
        "priorResponse",
        "priorConfig",
        "priorVersion",
        "priorConfigSha256",
        "targetConfig",
        "targetConfigSha256",
        "targetVersion",
        "generationId",
        "probeEndpoint",
        "probeBodySha256",
        "preexistingConnectors",
        "connectorConvergence",
        "appliedResponse",
        "rollbackResponse",
        "externalProbeReceiptSha256",
    }
)
CONNECTOR_CAPTURE_FIELDS = frozenset(
    {"id", "configVersionAvailable", "configVersion"}
)
CONNECTOR_CONVERGENCE_FIELDS = frozenset(
    {"id", "configVersionAvailable", "observedConfigVersion", "converged"}
)
CURRENT_CONNECTOR_CONVERGENCE_CONTRACT = (
    "cloudflare.current-connector-convergence/v1"
)
CURRENT_CONNECTOR_CONVERGENCE_FIELDS = frozenset(
    {
        "contractName",
        "targetVersion",
        "connectorSet",
        "connectorSetSha256",
        "connectorConvergence",
        "connectorSetTransitions",
        "attemptsUsed",
        "stableObservationsRequired",
    }
)
CONNECTIONS_RESPONSE_FIELDS = frozenset(
    {"success", "errors", "messages", "result", "result_info"}
)
CONNECTIONS_RESULT_INFO_FIELDS = frozenset(
    {"count", "page", "per_page", "total_count"}
)
MAX_CURRENT_CONNECTORS = 1280
MAX_JSON_BYTES = 16 * 1024 * 1024


class TransactionError(RuntimeError):
    """Base class for governed transaction failures."""


class ValidationError(TransactionError):
    """Input, response, or journal validation failed."""


class DriftError(TransactionError):
    """Remote state no longer matches an authorized transaction boundary."""


class ConvergenceError(TransactionError):
    """Cloudflare did not converge to the expected configuration."""


class JournalError(TransactionError):
    """The durable local transaction journal is unsafe or inconsistent."""


class ApiError(TransactionError):
    """A sanitized Cloudflare API operation failed."""


class TunnelApi(Protocol):
    def get_configuration(self) -> Mapping[str, Any]:
        ...

    def put_configuration(self, config: Mapping[str, Any]) -> Mapping[str, Any]:
        ...

    def list_connections(self) -> Mapping[str, Any]:
        ...

    def get_connector(self, connector_id: str) -> Mapping[str, Any]:
        ...


def canonical_json_bytes(value: Any) -> bytes:
    """Return stable UTF-8 JSON bytes or fail on non-JSON/NaN values."""

    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ValidationError("value is not canonical JSON") from exc


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _require_exact_fields(
    value: Mapping[str, Any], expected: frozenset[str], label: str
) -> None:
    actual = frozenset(value)
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        raise ValidationError(
            f"{label} fields mismatch (missing={missing}, extra={extra})"
        )


def _require_identifier(value: Any, label: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", value):
        raise ValidationError(f"{label} must be a non-empty safe identifier")
    return value


def _require_version(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValidationError(f"{label} must be a non-negative integer")
    return value


def validate_origin(origin: str) -> str:
    if not isinstance(origin, str) or not origin:
        raise ValidationError("origin must be a non-empty URL")
    parsed = urllib.parse.urlsplit(origin)
    if parsed.scheme not in {"http", "https"}:
        raise ValidationError("origin scheme must be http or https")
    if not parsed.hostname or parsed.username or parsed.password:
        raise ValidationError("origin must contain only a host and optional port")
    try:
        parsed.port
    except ValueError as exc:
        raise ValidationError("origin port is invalid") from exc
    if parsed.query or parsed.fragment or parsed.path not in {"", "/"}:
        raise ValidationError("origin must not contain a path, query, or fragment")
    return origin[:-1] if origin.endswith("/") else origin


def validate_generation_id(value: Any) -> str:
    if (
        not isinstance(value, str)
        or SAFE_GENERATION_ID.fullmatch(value) is None
        or value in {".", ".."}
        or ".." in value
    ):
        raise ValidationError("generation id is not a traversal-safe opaque token")
    return value


def validate_sha256(value: Any, label: str) -> str:
    if not isinstance(value, str) or SHA256.fullmatch(value) is None:
        raise ValidationError(f"{label} must be a lowercase SHA-256")
    return value


def validate_probe_endpoint(endpoint: Any, generation_id: str) -> str:
    if not isinstance(endpoint, str) or not endpoint:
        raise ValidationError("probe endpoint must be a non-empty URL")
    generation_id = validate_generation_id(generation_id)
    parsed = urllib.parse.urlsplit(endpoint)
    expected_paths = {
        f"/downloads/g/{generation_id}/releases.json",
        f"/downloads/g/{generation_id}/RELEASE_CHANNEL.generated.json",
    }
    if (
        parsed.scheme != "https"
        or parsed.hostname != MANAGED_HOSTS[0]
        or parsed.netloc != parsed.hostname
        or parsed.path not in expected_paths
        or parsed.query
        or parsed.fragment
        or parsed.username
        or parsed.password
        or not managed_path_matches(parsed.path)
    ):
        raise ValidationError(
            "probe endpoint must be the exact canonical generation manifest URL"
        )
    return endpoint


def validate_re2_pattern(pattern: str) -> None:
    """Reject syntax known to be unsupported by Go's regexp/RE2 engine."""

    if not isinstance(pattern, str) or not pattern:
        raise ValidationError("managed path pattern must be a non-empty string")
    unsupported_literals = (
        "(?:",
        "(?=",
        "(?!",
        "(?<=",
        "(?<!",
        "(?P",
        "(?>",
        "\\k",
    )
    if any(fragment in pattern for fragment in unsupported_literals):
        raise ValidationError("managed path pattern is not Go/RE2-compatible")
    if re.search(r"\\[1-9]", pattern):
        raise ValidationError("managed path pattern contains a backreference")
    try:
        re.compile(pattern)
    except re.error as exc:
        raise ValidationError("managed path pattern is invalid") from exc


def managed_path_matches(path: str) -> bool:
    validate_re2_pattern(MANAGED_PATH_RE2)
    return re.fullmatch(MANAGED_PATH_RE2, path) is not None


def validate_tunnel_config(config: Any) -> dict[str, Any]:
    """Validate the shape needed for a lossless ingress rewrite."""

    if not isinstance(config, dict):
        raise ValidationError("tunnel config must be an object")
    canonical_json_bytes(config)
    ingress = config.get("ingress")
    if not isinstance(ingress, list) or not ingress:
        raise ValidationError("tunnel config ingress must be a non-empty array")
    for index, rule in enumerate(ingress):
        if not isinstance(rule, dict):
            raise ValidationError(f"ingress[{index}] must be an object")
        service = rule.get("service")
        if not isinstance(service, str) or not service:
            raise ValidationError(
                f"ingress[{index}].service must be a non-empty string"
            )
        for optional in ("hostname", "path"):
            if optional in rule and (
                not isinstance(rule[optional], str) or not rule[optional]
            ):
                raise ValidationError(
                    f"ingress[{index}].{optional} must be a non-empty string"
                )
        if "originRequest" in rule and not isinstance(rule["originRequest"], dict):
            raise ValidationError(
                f"ingress[{index}].originRequest must be an object"
            )
    last_rule = ingress[-1]
    if "hostname" in last_rule or "path" in last_rule:
        raise ValidationError("tunnel ingress must end with a catch-all rule")
    return config


def _managed_rule(hostname: str, origin: str) -> dict[str, str]:
    return {
        "hostname": hostname,
        "path": MANAGED_PATH_RE2,
        "service": origin,
    }


def _fail_closed_rule(hostname: str, path: str) -> dict[str, str]:
    return {
        "hostname": hostname,
        "path": path,
        "service": "http_status:404",
    }


def plan_public_download_config(
    prior_config: Mapping[str, Any], origin: str
) -> dict[str, Any]:
    """Prepend governed and fail-closed rules without changing prior rules."""

    validate_re2_pattern(MANAGED_PATH_RE2)
    for path in FAIL_CLOSED_PATHS_RE2:
        validate_re2_pattern(path)
    normalized_origin = validate_origin(origin)
    prior = validate_tunnel_config(copy.deepcopy(prior_config))
    existing_managed: list[str] = []
    for rule in prior["ingress"]:
        if (
            rule.get("hostname") in MANAGED_HOSTS
            and rule.get("path")
            in {MANAGED_PATH_RE2, *FAIL_CLOSED_PATHS_RE2}
        ):
            existing_managed.append(str(rule["hostname"]))
    if existing_managed:
        raise ValidationError(
            "tunnel config already contains managed public-download rule(s): "
            + ", ".join(sorted(existing_managed))
        )
    target = copy.deepcopy(prior)
    target["ingress"] = [
        _managed_rule(hostname, normalized_origin) for hostname in MANAGED_HOSTS
    ] + [
        _fail_closed_rule(hostname, path)
        for path in FAIL_CLOSED_PATHS_RE2
        for hostname in MANAGED_HOSTS
    ] + copy.deepcopy(prior["ingress"])
    validate_planned_config(prior, target, normalized_origin)
    return target


def validate_planned_config(
    prior_config: Mapping[str, Any],
    target_config: Mapping[str, Any],
    origin: str,
) -> None:
    """Prove exact rule order, scope, origin behavior, and prior preservation."""

    normalized_origin = validate_origin(origin)
    prior = validate_tunnel_config(copy.deepcopy(prior_config))
    target = validate_tunnel_config(copy.deepcopy(target_config))
    expected_prefix = [
        _managed_rule(hostname, normalized_origin) for hostname in MANAGED_HOSTS
    ] + [
        _fail_closed_rule(hostname, path)
        for path in FAIL_CLOSED_PATHS_RE2
        for hostname in MANAGED_HOSTS
    ]
    if target["ingress"][: len(expected_prefix)] != expected_prefix:
        raise ValidationError(
            "managed and fail-closed rules are missing or not first"
        )
    if target["ingress"][len(expected_prefix) :] != prior["ingress"]:
        raise ValidationError("a preexisting ingress rule changed")
    non_ingress_prior = copy.deepcopy(prior)
    non_ingress_target = copy.deepcopy(target)
    del non_ingress_prior["ingress"]
    del non_ingress_target["ingress"]
    if non_ingress_target != non_ingress_prior:
        raise ValidationError("non-ingress tunnel configuration changed")
    for rule in target["ingress"][: len(expected_prefix)]:
        if "originRequest" in rule or "httpHostHeader" in rule:
            raise ValidationError(
                "managed rules must preserve the request Host header"
            )


class ConfigurationSnapshot:
    def __init__(
        self,
        *,
        response: Mapping[str, Any],
        config: Mapping[str, Any],
        version: int,
    ) -> None:
        self.response = copy.deepcopy(dict(response))
        self.config = copy.deepcopy(dict(config))
        self.version = version
        self.sha256 = canonical_sha256(self.config)


def parse_configuration_response(response: Any) -> ConfigurationSnapshot:
    if not isinstance(response, Mapping):
        raise ValidationError("Cloudflare configuration response must be an object")
    if response.get("success") is not True:
        raise ValidationError("Cloudflare configuration response is unsuccessful")
    result = response.get("result")
    if not isinstance(result, Mapping):
        raise ValidationError("Cloudflare configuration response has no result")
    config = result.get("config")
    validate_tunnel_config(config)
    version = _require_version(result.get("version"), "configuration version")
    source = result.get("source")
    if source is not None and source != "cloudflare":
        raise ValidationError("tunnel configuration is not remotely managed")
    return ConfigurationSnapshot(
        response=copy.deepcopy(dict(response)),
        config=copy.deepcopy(config),
        version=version,
    )


def _parse_connector_result(response: Any, expected_id: str) -> int | None:
    if not isinstance(response, Mapping) or response.get("success") is not True:
        raise ValidationError("Cloudflare connector response is unsuccessful")
    result = response.get("result")
    if not isinstance(result, Mapping):
        raise ValidationError("Cloudflare connector response has no result")
    connector_id = _require_identifier(result.get("id"), "connector id")
    if connector_id != expected_id:
        raise ValidationError("Cloudflare connector response id mismatch")
    if "config_version" not in result or result["config_version"] is None:
        return None
    return _require_version(result["config_version"], "connector config_version")


def _current_connections(api: TunnelApi) -> list[Any]:
    response = api.list_connections()
    if (
        not isinstance(response, Mapping)
        or set(response) != CONNECTIONS_RESPONSE_FIELDS
        or response.get("success") is not True
        or response.get("errors") != []
        or not isinstance(response.get("messages"), list)
    ):
        raise ValidationError(
            "Cloudflare connections response shape is invalid"
        )
    result = response.get("result")
    result_info = response.get("result_info")
    if not isinstance(result, list):
        raise ValidationError(
            "Cloudflare connections result must be an array"
        )
    if not isinstance(result_info, Mapping) or (
        set(result_info) != CONNECTIONS_RESULT_INFO_FIELDS
    ):
        raise ValidationError(
            "Cloudflare connections result_info shape is invalid"
        )
    count = result_info.get("count")
    observed_page = result_info.get("page")
    observed_per_page = result_info.get("per_page")
    total_count = result_info.get("total_count")
    if (
        any(
            isinstance(value, bool) or not isinstance(value, int)
            for value in (
                count,
                observed_page,
                observed_per_page,
                total_count,
            )
        )
        or count != len(result)
        or observed_page != 1
        or observed_per_page < 1
        or observed_per_page > MAX_CURRENT_CONNECTORS
        or total_count != len(result)
        or total_count > MAX_CURRENT_CONNECTORS
    ):
        raise ValidationError(
            "Cloudflare connections single-page metadata is invalid "
            "or incomplete"
        )
    return result


def capture_preexisting_connectors(api: TunnelApi) -> list[dict[str, Any]]:
    result = _current_connections(api)
    connector_ids: list[str] = []
    for row in result:
        if not isinstance(row, Mapping):
            raise ValidationError(
                "Cloudflare connection entry must be an object"
            )
        connector_ids.append(
            _require_identifier(row.get("id"), "connector id")
        )
    if len(connector_ids) != len(set(connector_ids)):
        raise ValidationError(
            "Cloudflare connections response contains duplicates"
        )
    if not connector_ids:
        raise ConvergenceError("tunnel has no preexisting connectors")
    captured: list[dict[str, Any]] = []
    for connector_id in sorted(connector_ids):
        version = _parse_connector_result(
            api.get_connector(connector_id), connector_id
        )
        captured.append(
            {
                "id": connector_id,
                "configVersionAvailable": version is not None,
                "configVersion": version,
            }
        )
    return captured


def poll_connector_convergence(
    api: TunnelApi,
    connectors: Sequence[Mapping[str, Any]],
    target_version: int,
    *,
    attempts: int,
    sleep_fn: Callable[[float], None],
    interval_seconds: float,
) -> list[dict[str, Any]]:
    if attempts < 1:
        raise ValidationError("poll attempts must be positive")
    target_version = _require_version(target_version, "target version")
    connector_ids = [str(row["id"]) for row in connectors]
    pending = set(connector_ids)
    observed: dict[str, dict[str, Any]] = {}
    for attempt in range(attempts):
        for connector_id in sorted(pending):
            version = _parse_connector_result(
                api.get_connector(connector_id), connector_id
            )
            if version is None:
                observed[connector_id] = {
                    "id": connector_id,
                    "configVersionAvailable": False,
                    "observedConfigVersion": None,
                    "converged": None,
                }
                pending.remove(connector_id)
            elif version == target_version:
                observed[connector_id] = {
                    "id": connector_id,
                    "configVersionAvailable": True,
                    "observedConfigVersion": version,
                    "converged": True,
                }
                pending.remove(connector_id)
            else:
                observed[connector_id] = {
                    "id": connector_id,
                    "configVersionAvailable": True,
                    "observedConfigVersion": version,
                    "converged": False,
                }
        if not pending:
            break
        if attempt + 1 < attempts:
            sleep_fn(interval_seconds)
    if pending:
        mismatch = {
            connector_id: observed[connector_id]["observedConfigVersion"]
            for connector_id in sorted(pending)
        }
        raise ConvergenceError(
            f"connector config_version did not converge: {mismatch}"
        )
    return [observed[connector_id] for connector_id in connector_ids]


def poll_current_connector_convergence(
    api: TunnelApi,
    target_version: int,
    *,
    attempts: int,
    sleep_fn: Callable[[float], None],
    interval_seconds: float,
    stable_observations_required: int = 2,
) -> dict[str, Any]:
    """Re-list and converge the connector set that exists now.

    Connector membership is not immutable across a tunnel configuration
    transaction.  A connector captured by an older transaction may have been
    removed, while a newly-added connector must not be omitted from a
    destructive retirement decision.  Success therefore requires the same
    sorted current connector set to be observed converged in consecutive
    polls.  Set changes reset the stability count and are retained in the
    receipt.
    """

    if attempts < 1:
        raise ValidationError("poll attempts must be positive")
    target_version = _require_version(target_version, "target version")
    if (
        isinstance(stable_observations_required, bool)
        or not isinstance(stable_observations_required, int)
        or stable_observations_required < 2
        or stable_observations_required > attempts
    ):
        raise ValidationError(
            "current connector convergence requires at least two bounded "
            "stable observations"
        )
    transitions: list[list[str]] = []
    stable_ids: list[str] | None = None
    stable_observations = 0
    final_capture: list[dict[str, Any]] | None = None
    final_convergence: list[dict[str, Any]] | None = None
    last_mismatch: dict[str, int | None] = {}
    for attempt in range(attempts):
        captured = capture_preexisting_connectors(api)
        connector_ids = [str(row["id"]) for row in captured]
        if not transitions or transitions[-1] != connector_ids:
            transitions.append(connector_ids)
        convergence: list[dict[str, Any]] = []
        mismatch: dict[str, int | None] = {}
        for row in captured:
            connector_id = str(row["id"])
            available = row["configVersionAvailable"]
            observed_version = row["configVersion"]
            converged = (
                observed_version == target_version
                if available
                else None
            )
            convergence.append(
                {
                    "id": connector_id,
                    "configVersionAvailable": available,
                    "observedConfigVersion": observed_version,
                    "converged": converged,
                }
            )
            if not available or not converged:
                mismatch[connector_id] = observed_version
        if mismatch:
            stable_ids = None
            stable_observations = 0
            last_mismatch = mismatch
        else:
            if stable_ids == connector_ids:
                stable_observations += 1
            else:
                stable_ids = connector_ids
                stable_observations = 1
            final_capture = captured
            final_convergence = convergence
            last_mismatch = {}
            if stable_observations >= stable_observations_required:
                receipt = {
                    "contractName": (
                        CURRENT_CONNECTOR_CONVERGENCE_CONTRACT
                    ),
                    "targetVersion": target_version,
                    "connectorSet": copy.deepcopy(final_capture),
                    "connectorSetSha256": canonical_sha256(
                        final_capture
                    ),
                    "connectorConvergence": copy.deepcopy(
                        final_convergence
                    ),
                    "connectorSetTransitions": copy.deepcopy(
                        transitions
                    ),
                    "attemptsUsed": attempt + 1,
                    "stableObservationsRequired": (
                        stable_observations_required
                    ),
                }
                return validate_current_connector_convergence_receipt(
                    receipt
                )
        if attempt + 1 < attempts:
            sleep_fn(interval_seconds)
    if last_mismatch:
        raise ConvergenceError(
            "current connector config_version did not converge: "
            f"{last_mismatch}"
        )
    raise ConvergenceError(
        "current connector set did not remain stable while converged"
    )


def _utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def _validate_connector_capture(rows: Any) -> list[dict[str, Any]]:
    if not isinstance(rows, list):
        raise ValidationError("preexistingConnectors must be an array")
    ids: list[str] = []
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise ValidationError(f"preexistingConnectors[{index}] must be an object")
        _require_exact_fields(
            row, CONNECTOR_CAPTURE_FIELDS, f"preexistingConnectors[{index}]"
        )
        connector_id = _require_identifier(row["id"], "connector id")
        available = row["configVersionAvailable"]
        if not isinstance(available, bool):
            raise ValidationError("configVersionAvailable must be boolean")
        if available:
            _require_version(row["configVersion"], "connector configVersion")
        elif row["configVersion"] is not None:
            raise ValidationError("unavailable connector version must be null")
        ids.append(connector_id)
    if ids != sorted(ids) or len(ids) != len(set(ids)):
        raise ValidationError("preexisting connectors must be unique and sorted")
    return rows


def _validate_connector_convergence(
    rows: Any, connector_ids: Sequence[str], target_version: int | None
) -> list[dict[str, Any]]:
    if not isinstance(rows, list):
        raise ValidationError("connectorConvergence must be an array")
    if not rows:
        return rows
    if target_version is None:
        raise ValidationError("connector convergence requires a target version")
    ids: list[str] = []
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise ValidationError(f"connectorConvergence[{index}] must be an object")
        _require_exact_fields(
            row, CONNECTOR_CONVERGENCE_FIELDS, f"connectorConvergence[{index}]"
        )
        connector_id = _require_identifier(row["id"], "connector id")
        available = row["configVersionAvailable"]
        if not isinstance(available, bool):
            raise ValidationError("connector availability must be boolean")
        if available:
            observed_version = _require_version(
                row["observedConfigVersion"], "observed connector config version"
            )
            if row["converged"] is not True or observed_version != target_version:
                raise ValidationError("available connector is not target-converged")
        elif (
            row["observedConfigVersion"] is not None
            or row["converged"] is not None
        ):
            raise ValidationError("unavailable connector observation is malformed")
        ids.append(connector_id)
    if ids != list(connector_ids):
        raise ValidationError("connector convergence does not cover captured connectors")
    return rows


def validate_current_connector_convergence_receipt(
    value: Any,
) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValidationError(
            "current connector convergence receipt must be an object"
        )
    _require_exact_fields(
        value,
        CURRENT_CONNECTOR_CONVERGENCE_FIELDS,
        "current connector convergence receipt",
    )
    if (
        value["contractName"]
        != CURRENT_CONNECTOR_CONVERGENCE_CONTRACT
    ):
        raise ValidationError(
            "current connector convergence contract mismatch"
        )
    target_version = _require_version(
        value["targetVersion"],
        "current connector target version",
    )
    connector_set = _validate_connector_capture(value["connectorSet"])
    connector_ids = [row["id"] for row in connector_set]
    if not connector_ids:
        raise ValidationError(
            "current connector convergence set must not be empty"
        )
    if canonical_sha256(connector_set) != value["connectorSetSha256"]:
        raise ValidationError(
            "current connector set digest mismatch"
        )
    if any(
        not row["configVersionAvailable"]
        or row["configVersion"] != target_version
        for row in connector_set
    ):
        raise ValidationError(
            "current connector set lacks exact configuration versions"
        )
    convergence = _validate_connector_convergence(
        value["connectorConvergence"],
        connector_ids,
        target_version,
    )
    if len(convergence) != len(connector_set):
        raise ValidationError(
            "current connector convergence is incomplete"
        )
    for captured, observed in zip(
        connector_set,
        convergence,
        strict=True,
    ):
        if (
            captured["configVersionAvailable"]
            != observed["configVersionAvailable"]
            or captured["configVersion"]
            != observed["observedConfigVersion"]
            or (
                captured["configVersionAvailable"]
                and captured["configVersion"] != target_version
            )
        ):
            raise ValidationError(
                "current connector capture and convergence differ"
            )
    transitions = value["connectorSetTransitions"]
    if not isinstance(transitions, list) or not transitions:
        raise ValidationError(
            "current connector set transitions must be non-empty"
        )
    previous: list[str] | None = None
    for index, transition in enumerate(transitions):
        if (
            not isinstance(transition, list)
            or not transition
            or any(
                _require_identifier(
                    connector_id,
                    f"connectorSetTransitions[{index}] id",
                )
                != connector_id
                for connector_id in transition
            )
            or transition != sorted(transition)
            or len(transition) != len(set(transition))
            or transition == previous
        ):
            raise ValidationError(
                "current connector set transition is malformed"
            )
        previous = transition
    if transitions[-1] != connector_ids:
        raise ValidationError(
            "current connector set transition does not end at the "
            "converged set"
        )
    attempts_used = value["attemptsUsed"]
    stable_required = value["stableObservationsRequired"]
    if (
        isinstance(attempts_used, bool)
        or not isinstance(attempts_used, int)
        or isinstance(stable_required, bool)
        or not isinstance(stable_required, int)
        or stable_required < 2
        or attempts_used < stable_required
    ):
        raise ValidationError(
            "current connector convergence poll bounds are invalid"
        )
    return value


def validate_journal(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValidationError("transaction journal must be an object")
    _require_exact_fields(value, JOURNAL_FIELDS, "transaction journal")
    if value["schema"] != SCHEMA:
        raise ValidationError("transaction journal schema mismatch")
    if value["phase"] not in PHASES:
        raise ValidationError("transaction journal phase is invalid")
    _require_identifier(value["accountId"], "account id")
    _require_identifier(value["tunnelId"], "tunnel id")
    origin = validate_origin(value["origin"])
    for field in ("createdAt", "updatedAt"):
        if not isinstance(value[field], str) or not value[field]:
            raise ValidationError(f"{field} must be a non-empty timestamp")
    prior = parse_configuration_response(value["priorResponse"])
    if prior.config != value["priorConfig"] or prior.version != value["priorVersion"]:
        raise ValidationError("journal prior response/config/version mismatch")
    if canonical_sha256(value["priorConfig"]) != value["priorConfigSha256"]:
        raise ValidationError("journal prior config digest mismatch")
    validate_planned_config(value["priorConfig"], value["targetConfig"], origin)
    if canonical_sha256(value["targetConfig"]) != value["targetConfigSha256"]:
        raise ValidationError("journal target config digest mismatch")
    generation_id = validate_generation_id(value["generationId"])
    validate_probe_endpoint(value["probeEndpoint"], generation_id)
    validate_sha256(value["probeBodySha256"], "journal probe body digest")
    target_version = value["targetVersion"]
    if target_version is not None:
        target_version = _require_version(target_version, "target version")
    if value["phase"] in {
        "applied",
        "awaiting-external-probe",
        "committed",
    } and target_version is None:
        raise ValidationError("applied journal must have a target version")
    connectors = _validate_connector_capture(value["preexistingConnectors"])
    connector_ids = [row["id"] for row in connectors]
    convergence = _validate_connector_convergence(
        value["connectorConvergence"], connector_ids, target_version
    )
    if value["phase"] in {"applied", "awaiting-external-probe", "committed"}:
        if len(convergence) != len(connectors):
            raise ValidationError("applied journal lacks connector observations")
    applied_response = value["appliedResponse"]
    if applied_response is not None:
        applied = parse_configuration_response(applied_response)
        if (
            applied.sha256 != value["targetConfigSha256"]
            or target_version is None
            or applied.version != target_version
        ):
            raise ValidationError("journal applied response does not bind the target")
    applied_response_required = value["phase"] in {
        "applied",
        "awaiting-external-probe",
        "committed",
    } or (
        value["phase"] in {"rollback-in-flight", "rolled-back"}
        and target_version is not None
    )
    if applied_response_required and applied_response is None:
        raise ValidationError("post-apply journal lacks the full applied response")
    rollback_response = value["rollbackResponse"]
    if rollback_response is not None:
        rollback = parse_configuration_response(rollback_response)
        if rollback.sha256 != value["priorConfigSha256"]:
            raise ValidationError("journal rollback response does not bind the prior config")
    if value["phase"] == "rolled-back" and rollback_response is None:
        raise ValidationError("rolled-back journal lacks the full rollback response")
    if value["phase"] != "rolled-back" and rollback_response is not None:
        raise ValidationError("non-terminal journal unexpectedly records rollback")
    proof_sha = value["externalProbeReceiptSha256"]
    if proof_sha is not None and (
        not isinstance(proof_sha, str) or SHA256.fullmatch(proof_sha) is None
    ):
        raise ValidationError("external probe receipt digest is invalid")
    if value["phase"] == "committed" and any(
        not row["configVersionAvailable"] for row in convergence
    ) and proof_sha is None:
        raise ValidationError(
            "committed journal with unavailable connector versions lacks proof"
        )
    return value


def _dir_fd(path: Path) -> int:
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise JournalError("journal parent directory is unavailable or unsafe") from exc
    info = os.fstat(fd)
    if not stat.S_ISDIR(info.st_mode):
        os.close(fd)
        raise JournalError("journal parent is not a directory")
    return fd


def _validate_private_file(fd: int, label: str) -> None:
    info = os.fstat(fd)
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        raise JournalError(f"{label} must be a singly-linked regular file")
    if info.st_uid != os.geteuid():
        raise JournalError(f"{label} must be owned by the current user")
    if stat.S_IMODE(info.st_mode) != 0o600:
        raise JournalError(f"{label} mode must be 0600")


class ExclusiveFileLock:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.fd: int | None = None

    def __enter__(self) -> "ExclusiveFileLock":
        if self.path.name in {"", ".", ".."}:
            raise JournalError("lock path is invalid")
        parent_fd = _dir_fd(self.path.parent)
        flags = os.O_RDWR | os.O_CLOEXEC
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        try:
            try:
                self.fd = os.open(
                    self.path.name,
                    flags | os.O_CREAT | os.O_EXCL,
                    0o600,
                    dir_fd=parent_fd,
                )
                os.fchmod(self.fd, 0o600)
                os.fsync(self.fd)
                os.fsync(parent_fd)
            except FileExistsError:
                try:
                    self.fd = os.open(self.path.name, flags, dir_fd=parent_fd)
                except OSError as exc:
                    raise JournalError(
                        "cannot open exclusive transaction lock"
                    ) from exc
            except OSError as exc:
                raise JournalError("cannot open exclusive transaction lock") from exc
        finally:
            os.close(parent_fd)
        assert self.fd is not None
        try:
            _validate_private_file(self.fd, "transaction lock")
        except Exception:
            os.close(self.fd)
            self.fd = None
            raise
        fcntl.flock(self.fd, fcntl.LOCK_EX)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if self.fd is not None:
            fcntl.flock(self.fd, fcntl.LOCK_UN)
            os.close(self.fd)
            self.fd = None


def _journal_payload(journal: Mapping[str, Any]) -> bytes:
    validate_journal(copy.deepcopy(dict(journal)))
    return canonical_json_bytes(journal) + b"\n"


def create_journal_no_replace(path: Path, journal: Mapping[str, Any]) -> None:
    payload = _journal_payload(journal)
    if path.name in {"", ".", ".."}:
        raise JournalError("journal path is invalid")
    parent_fd = _dir_fd(path.parent)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd: int | None = None
    created = False
    try:
        try:
            fd = os.open(path.name, flags, 0o600, dir_fd=parent_fd)
            created = True
        except FileExistsError as exc:
            raise JournalError("transaction journal already exists") from exc
        os.fchmod(fd, 0o600)
        view = memoryview(payload)
        while view:
            written = os.write(fd, view)
            if written <= 0:
                raise JournalError("short journal write")
            view = view[written:]
        os.fsync(fd)
        os.close(fd)
        fd = None
        os.fsync(parent_fd)
    except Exception:
        if fd is not None:
            os.close(fd)
        if created:
            try:
                os.unlink(path.name, dir_fd=parent_fd)
                os.fsync(parent_fd)
            except OSError:
                pass
        raise
    finally:
        os.close(parent_fd)


def replace_journal(path: Path, journal: Mapping[str, Any]) -> None:
    payload = _journal_payload(journal)
    parent_fd = _dir_fd(path.parent)
    temp_name = f".{path.name}.{secrets.token_hex(12)}.tmp"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd: int | None = None
    try:
        existing_flags = os.O_RDONLY | os.O_CLOEXEC
        if hasattr(os, "O_NOFOLLOW"):
            existing_flags |= os.O_NOFOLLOW
        try:
            existing_fd = os.open(path.name, existing_flags, dir_fd=parent_fd)
        except OSError as exc:
            raise JournalError("transaction journal is missing or unsafe") from exc
        try:
            _validate_private_file(existing_fd, "transaction journal")
        finally:
            os.close(existing_fd)
        fd = os.open(temp_name, flags, 0o600, dir_fd=parent_fd)
        os.fchmod(fd, 0o600)
        view = memoryview(payload)
        while view:
            written = os.write(fd, view)
            if written <= 0:
                raise JournalError("short journal update")
            view = view[written:]
        os.fsync(fd)
        os.close(fd)
        fd = None
        os.replace(
            temp_name,
            path.name,
            src_dir_fd=parent_fd,
            dst_dir_fd=parent_fd,
        )
        os.fsync(parent_fd)
    finally:
        if fd is not None:
            os.close(fd)
        try:
            os.unlink(temp_name, dir_fd=parent_fd)
        except OSError:
            pass
        os.close(parent_fd)


def load_journal(path: Path) -> dict[str, Any]:
    parent_fd = _dir_fd(path.parent)
    flags = os.O_RDONLY | os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        try:
            fd = os.open(path.name, flags, dir_fd=parent_fd)
        except OSError as exc:
            raise JournalError("transaction journal is missing or unsafe") from exc
        try:
            _validate_private_file(fd, "transaction journal")
            size = os.fstat(fd).st_size
            if size > MAX_JSON_BYTES:
                raise JournalError("transaction journal exceeds size limit")
            chunks: list[bytes] = []
            remaining = MAX_JSON_BYTES + 1
            while remaining:
                chunk = os.read(fd, min(65536, remaining))
                if not chunk:
                    break
                chunks.append(chunk)
                remaining -= len(chunk)
        finally:
            os.close(fd)
    finally:
        os.close(parent_fd)
    raw = b"".join(chunks)
    if len(raw) > MAX_JSON_BYTES:
        raise JournalError("transaction journal exceeds size limit")
    try:
        parsed = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise JournalError("transaction journal is not valid JSON") from exc
    return validate_journal(parsed)


def remove_journal(path: Path) -> None:
    parent_fd = _dir_fd(path.parent)
    flags = os.O_RDONLY | os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        try:
            fd = os.open(path.name, flags, dir_fd=parent_fd)
        except OSError as exc:
            raise JournalError("transaction journal is missing or unsafe") from exc
        try:
            _validate_private_file(fd, "transaction journal")
        finally:
            os.close(fd)
        os.unlink(path.name, dir_fd=parent_fd)
        os.fsync(parent_fd)
    finally:
        os.close(parent_fd)


def journal_path_present(path: Path) -> bool:
    return path.exists() or path.is_symlink()


def archive_terminal_journal(
    journal_path: Path,
    evidence_path: Path,
    journal: Mapping[str, Any],
) -> dict[str, Any]:
    terminal = validate_journal(copy.deepcopy(dict(journal)))
    if terminal["phase"] not in {"committed", "rolled-back"}:
        raise JournalError("only a terminal journal can be archived")
    if evidence_path == journal_path:
        raise JournalError("terminal evidence path must differ from the live journal")
    if journal_path_present(evidence_path):
        archived = load_journal(evidence_path)
        if canonical_json_bytes(archived) != canonical_json_bytes(terminal):
            raise JournalError("terminal evidence already exists with different bytes")
    else:
        create_journal_no_replace(evidence_path, terminal)
    if journal_path_present(journal_path):
        live = load_journal(journal_path)
        if canonical_json_bytes(live) != canonical_json_bytes(terminal):
            raise JournalError("live terminal journal changed before archival")
        remove_journal(journal_path)
    return terminal


def reconcile_terminal_evidence(
    api: TunnelApi,
    *,
    evidence_path: Path,
    expected_phase: str,
) -> dict[str, Any]:
    evidence = load_journal(evidence_path)
    if evidence["phase"] != expected_phase:
        raise JournalError("terminal evidence phase does not match the requested action")
    current = parse_configuration_response(api.get_configuration())
    if expected_phase == "committed":
        if not _snapshot_matches(
            current,
            evidence["targetConfigSha256"],
            evidence["targetVersion"],
        ):
            raise DriftError("committed terminal evidence no longer matches live config")
    elif expected_phase == "rolled-back":
        rollback = parse_configuration_response(evidence["rollbackResponse"])
        if not _snapshot_matches(current, rollback.sha256, rollback.version):
            raise DriftError("rollback terminal evidence no longer matches live config")
    else:
        raise JournalError("terminal evidence phase is unsupported")
    return evidence


def _update_journal(
    path: Path, journal: Mapping[str, Any], **changes: Any
) -> dict[str, Any]:
    updated = copy.deepcopy(dict(journal))
    updated.update(changes)
    updated["updatedAt"] = _utc_now()
    replace_journal(path, updated)
    return validate_journal(updated)


def _snapshot_matches(
    snapshot: ConfigurationSnapshot, sha256: str, version: int | None = None
) -> bool:
    return snapshot.sha256 == sha256 and (
        version is None or snapshot.version == version
    )


def poll_configuration(
    api: TunnelApi,
    *,
    expected_sha256: str,
    expected_version: int,
    transitional: Sequence[tuple[str, int | None]],
    attempts: int,
    sleep_fn: Callable[[float], None],
    interval_seconds: float,
) -> ConfigurationSnapshot:
    if attempts < 1:
        raise ValidationError("poll attempts must be positive")
    for attempt in range(attempts):
        current = parse_configuration_response(api.get_configuration())
        if _snapshot_matches(current, expected_sha256, expected_version):
            return current
        if not any(
            _snapshot_matches(current, allowed_sha, allowed_version)
            for allowed_sha, allowed_version in transitional
        ):
            raise DriftError(
                "configuration changed outside the authorized transaction"
            )
        if attempt + 1 < attempts:
            sleep_fn(interval_seconds)
    raise ConvergenceError("Cloudflare configuration did not converge")


def capture_transaction(
    api: TunnelApi,
    *,
    account_id: str,
    tunnel_id: str,
    origin: str,
    generation_id: str,
    probe_endpoint: str,
    probe_body_sha256: str,
    journal_path: Path,
    lock_path: Path,
) -> dict[str, Any]:
    account_id = _require_identifier(account_id, "account id")
    tunnel_id = _require_identifier(tunnel_id, "tunnel id")
    origin = validate_origin(origin)
    generation_id = validate_generation_id(generation_id)
    probe_endpoint = validate_probe_endpoint(probe_endpoint, generation_id)
    probe_body_sha256 = validate_sha256(
        probe_body_sha256, "probe body digest"
    )
    with ExclusiveFileLock(lock_path):
        prior = parse_configuration_response(api.get_configuration())
        target = plan_public_download_config(prior.config, origin)
        connectors = capture_preexisting_connectors(api)
        timestamp = _utc_now()
        journal = {
            "schema": SCHEMA,
            "phase": "captured",
            "accountId": account_id,
            "tunnelId": tunnel_id,
            "origin": origin,
            "createdAt": timestamp,
            "updatedAt": timestamp,
            "priorResponse": prior.response,
            "priorConfig": prior.config,
            "priorVersion": prior.version,
            "priorConfigSha256": prior.sha256,
            "targetConfig": target,
            "targetConfigSha256": canonical_sha256(target),
            "targetVersion": None,
            "generationId": generation_id,
            "probeEndpoint": probe_endpoint,
            "probeBodySha256": probe_body_sha256,
            "preexistingConnectors": connectors,
            "connectorConvergence": [],
            "appliedResponse": None,
            "rollbackResponse": None,
            "externalProbeReceiptSha256": None,
        }
        create_journal_no_replace(journal_path, journal)
        return validate_journal(journal)


def _configuration_after_put_or_reget(
    api: TunnelApi,
    *,
    config: Mapping[str, Any],
    expected_sha256: str,
    fallback_sha256: str,
    fallback_version: int | None,
) -> ConfigurationSnapshot:
    try:
        response = api.put_configuration(config)
        snapshot = parse_configuration_response(response)
    except Exception as put_error:
        try:
            snapshot = parse_configuration_response(api.get_configuration())
        except Exception as verify_error:
            raise ApiError(
                "PUT outcome is unknown and configuration re-read failed"
            ) from verify_error
        if snapshot.sha256 != expected_sha256:
            if _snapshot_matches(snapshot, fallback_sha256, fallback_version):
                raise ApiError("PUT failed before changing the configuration") from put_error
            raise DriftError(
                "PUT outcome is unknown and remote configuration is unrelated"
            ) from put_error
    if snapshot.sha256 != expected_sha256:
        raise DriftError("PUT response does not contain the authorized config")
    return snapshot


def apply_transaction(
    api: TunnelApi,
    *,
    journal_path: Path,
    lock_path: Path,
    attempts: int = 30,
    interval_seconds: float = 2.0,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    with ExclusiveFileLock(lock_path):
        journal = load_journal(journal_path)
        starting_phase = journal["phase"]
        if journal["phase"] in {"rollback-in-flight", "rolled-back", "committed"}:
            raise JournalError("transaction phase cannot be applied")
        if journal["phase"] in {"applied", "awaiting-external-probe"}:
            current = parse_configuration_response(api.get_configuration())
            if not _snapshot_matches(
                current,
                journal["targetConfigSha256"],
                journal["targetVersion"],
            ):
                raise DriftError("applied target configuration drifted")
            target_version = journal["targetVersion"]
        else:
            journal = _update_journal(
                journal_path, journal, phase="apply-in-flight"
            )
            # This GET is intentionally the final operation before the PUT.
            current = parse_configuration_response(api.get_configuration())
            if _snapshot_matches(
                current,
                journal["targetConfigSha256"],
                journal["targetVersion"],
            ) and journal["targetVersion"] is not None and starting_phase == "apply-in-flight":
                target_version = current.version
            elif _snapshot_matches(
                current,
                journal["targetConfigSha256"],
            ) and starting_phase == "apply-in-flight" and journal["targetVersion"] is None:
                # Recovery from a PUT whose response was lost before targetVersion
                # could be durably recorded.
                target_version = current.version
            else:
                if not _snapshot_matches(
                    current,
                    journal["priorConfigSha256"],
                    journal["priorVersion"],
                ):
                    raise DriftError(
                        "configuration/version drifted after transaction capture"
                    )
                put_snapshot = _configuration_after_put_or_reget(
                    api,
                    config=journal["targetConfig"],
                    expected_sha256=journal["targetConfigSha256"],
                    fallback_sha256=journal["priorConfigSha256"],
                    fallback_version=journal["priorVersion"],
                )
                target_version = put_snapshot.version
            journal = _update_journal(
                journal_path, journal, targetVersion=target_version
            )
        assert isinstance(target_version, int)
        applied = poll_configuration(
            api,
            expected_sha256=journal["targetConfigSha256"],
            expected_version=target_version,
            transitional=[
                (journal["priorConfigSha256"], journal["priorVersion"])
            ],
            attempts=attempts,
            sleep_fn=sleep_fn,
            interval_seconds=interval_seconds,
        )
        convergence = poll_connector_convergence(
            api,
            journal["preexistingConnectors"],
            target_version,
            attempts=attempts,
            sleep_fn=sleep_fn,
            interval_seconds=interval_seconds,
        )
        needs_external_probe = any(
            not row["configVersionAvailable"] for row in convergence
        )
        phase = (
            "awaiting-external-probe" if needs_external_probe else "applied"
        )
        return _update_journal(
            journal_path,
            journal,
            phase=phase,
            connectorConvergence=convergence,
            appliedResponse=applied.response,
        )


def _read_external_probe(path: Path) -> tuple[dict[str, Any], str]:
    flags = os.O_RDONLY | os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise ValidationError("external probe receipt is unavailable or unsafe") from exc
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_JSON_BYTES:
            raise ValidationError("external probe receipt is not a bounded file")
        chunks: list[bytes] = []
        remaining = MAX_JSON_BYTES + 1
        while remaining:
            chunk = os.read(fd, min(65536, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
    finally:
        os.close(fd)
    raw = b"".join(chunks)
    if len(raw) > MAX_JSON_BYTES:
        raise ValidationError("external probe receipt exceeds size limit")
    try:
        receipt = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValidationError("external probe receipt is not valid JSON") from exc
    return receipt, hashlib.sha256(raw).hexdigest()


def validate_external_probe_receipt(
    receipt: Any, journal: Mapping[str, Any]
) -> None:
    expected_fields = frozenset(
        {
            "schema",
            "accountId",
            "tunnelId",
            "targetConfigSha256",
            "targetVersion",
            "connectorIds",
            "generationId",
            "observations",
            "observedAt",
        }
    )
    if not isinstance(receipt, dict):
        raise ValidationError("external probe receipt must be an object")
    _require_exact_fields(receipt, expected_fields, "external probe receipt")
    if receipt["schema"] != EXTERNAL_PROBE_SCHEMA:
        raise ValidationError("external probe receipt schema mismatch")
    for field in ("accountId", "tunnelId", "targetConfigSha256", "targetVersion"):
        if receipt[field] != journal[field]:
            raise ValidationError(f"external probe receipt {field} mismatch")
    if receipt["generationId"] != journal["generationId"]:
        raise ValidationError("external probe receipt generationId mismatch")
    validate_generation_id(receipt["generationId"])
    canonical_endpoint = validate_probe_endpoint(
        journal["probeEndpoint"], receipt["generationId"]
    )
    canonical_path = urllib.parse.urlsplit(canonical_endpoint).path
    expected_endpoints = [
        f"https://{hostname}{canonical_path}" for hostname in MANAGED_HOSTS
    ]
    observations = receipt["observations"]
    if not isinstance(observations, list) or len(observations) != len(
        expected_endpoints
    ):
        raise ValidationError(
            "external probe must contain one observation per managed host"
        )
    observation_fields = frozenset(
        {"endpoint", "httpStatus", "bodySha256", "anonymous"}
    )
    for index, (observation, expected_endpoint) in enumerate(
        zip(observations, expected_endpoints, strict=True)
    ):
        if not isinstance(observation, dict):
            raise ValidationError(
                f"external probe observation[{index}] must be an object"
            )
        _require_exact_fields(
            observation,
            observation_fields,
            f"external probe observation[{index}]",
        )
        if observation["endpoint"] != expected_endpoint:
            raise ValidationError(
                f"external probe observation[{index}] endpoint mismatch"
            )
        if observation["httpStatus"] != 200:
            raise ValidationError(
                f"external probe observation[{index}] did not return HTTP 200"
            )
        if observation["bodySha256"] != journal["probeBodySha256"]:
            raise ValidationError(
                f"external probe observation[{index}] body digest mismatch"
            )
        validate_sha256(
            observation["bodySha256"], "external probe body digest"
        )
        if observation["anonymous"] is not True:
            raise ValidationError(
                f"external probe observation[{index}] was not strictly anonymous"
            )
    missing_ids = [
        row["id"]
        for row in journal["connectorConvergence"]
        if not row["configVersionAvailable"]
    ]
    if receipt["connectorIds"] != missing_ids:
        raise ValidationError("external probe connector coverage mismatch")
    if not isinstance(receipt["observedAt"], str) or not receipt["observedAt"]:
        raise ValidationError("external probe observedAt is invalid")


def commit_transaction(
    api: TunnelApi,
    *,
    journal_path: Path,
    lock_path: Path,
    evidence_path: Path,
    external_probe_receipt: Path | None = None,
) -> dict[str, Any]:
    with ExclusiveFileLock(lock_path):
        if not journal_path_present(journal_path):
            return reconcile_terminal_evidence(
                api,
                evidence_path=evidence_path,
                expected_phase="committed",
            )
        journal = load_journal(journal_path)
        if journal["phase"] == "committed":
            current = parse_configuration_response(api.get_configuration())
            if not _snapshot_matches(
                current,
                journal["targetConfigSha256"],
                journal["targetVersion"],
            ):
                raise DriftError("committed target configuration drifted")
            return archive_terminal_journal(
                journal_path, evidence_path, journal
            )
        if journal["phase"] not in {"applied", "awaiting-external-probe"}:
            raise JournalError("only an applied transaction can be committed")
        current = parse_configuration_response(api.get_configuration())
        if not _snapshot_matches(
            current,
            journal["targetConfigSha256"],
            journal["targetVersion"],
        ):
            raise DriftError("target configuration drifted before commit")
        needs_external_probe = journal["phase"] == "awaiting-external-probe"
        proof_sha: str | None = None
        if needs_external_probe:
            if external_probe_receipt is None:
                raise ConvergenceError(
                    "connector config_version unavailable; external probe receipt required"
                )
            receipt, proof_sha = _read_external_probe(external_probe_receipt)
            validate_external_probe_receipt(receipt, journal)
        elif external_probe_receipt is not None:
            receipt, proof_sha = _read_external_probe(external_probe_receipt)
            validate_external_probe_receipt(receipt, journal)
        completed = _update_journal(
            journal_path,
            journal,
            phase="committed",
            appliedResponse=current.response,
            externalProbeReceiptSha256=proof_sha,
        )
        return archive_terminal_journal(
            journal_path, evidence_path, completed
        )


def rollback_transaction(
    api: TunnelApi,
    *,
    journal_path: Path,
    lock_path: Path,
    evidence_path: Path,
    attempts: int = 30,
    interval_seconds: float = 2.0,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    with ExclusiveFileLock(lock_path):
        if not journal_path_present(journal_path):
            return reconcile_terminal_evidence(
                api,
                evidence_path=evidence_path,
                expected_phase="rolled-back",
            )
        journal = load_journal(journal_path)
        if journal["phase"] == "committed":
            raise JournalError("transaction phase cannot be rolled back")
        current = parse_configuration_response(api.get_configuration())
        if journal["phase"] == "rolled-back":
            rollback = parse_configuration_response(journal["rollbackResponse"])
            if not _snapshot_matches(current, rollback.sha256, rollback.version):
                raise DriftError("rolled-back prior configuration drifted")
            return archive_terminal_journal(
                journal_path, evidence_path, journal
            )
        if current.sha256 == journal["priorConfigSha256"]:
            completed = _update_journal(
                journal_path,
                journal,
                phase="rolled-back",
                rollbackResponse=current.response,
            )
            return archive_terminal_journal(
                journal_path, evidence_path, completed
            )
        target_is_exact = current.sha256 == journal["targetConfigSha256"] and (
            journal["targetVersion"] is None
            or current.version == journal["targetVersion"]
        )
        if not target_is_exact:
            raise DriftError(
                "rollback refused because remote config is neither target nor prior"
            )
        journal = _update_journal(
            journal_path,
            journal,
            phase="rollback-in-flight",
            targetVersion=current.version,
            appliedResponse=current.response,
        )
        # Re-read immediately before restoring the exact captured config.
        current = parse_configuration_response(api.get_configuration())
        if not _snapshot_matches(
            current,
            journal["targetConfigSha256"],
            journal["targetVersion"],
        ):
            raise DriftError("target configuration drifted before rollback PUT")
        restored = _configuration_after_put_or_reget(
            api,
            config=journal["priorConfig"],
            expected_sha256=journal["priorConfigSha256"],
            fallback_sha256=journal["targetConfigSha256"],
            fallback_version=journal["targetVersion"],
        )
        rolled_back = poll_configuration(
            api,
            expected_sha256=journal["priorConfigSha256"],
            expected_version=restored.version,
            transitional=[
                (journal["targetConfigSha256"], journal["targetVersion"])
            ],
            attempts=attempts,
            sleep_fn=sleep_fn,
            interval_seconds=interval_seconds,
        )
        completed = _update_journal(
            journal_path,
            journal,
            phase="rolled-back",
            rollbackResponse=rolled_back.response,
        )
        return archive_terminal_journal(
            journal_path, evidence_path, completed
        )


class CloudflareTunnelApi:
    def __init__(
        self,
        *,
        api_base: str,
        account_id: str,
        tunnel_id: str,
        auth_headers: Mapping[str, str],
        timeout_seconds: float,
    ) -> None:
        self.api_base = api_base.rstrip("/")
        self.account_id = _require_identifier(account_id, "account id")
        self.tunnel_id = _require_identifier(tunnel_id, "tunnel id")
        self.auth_headers = dict(auth_headers)
        self.timeout_seconds = timeout_seconds
        account = urllib.parse.quote(self.account_id, safe="")
        tunnel = urllib.parse.quote(self.tunnel_id, safe="")
        self.tunnel_path = f"/accounts/{account}/cfd_tunnel/{tunnel}"

    def _request(
        self, method: str, path: str, payload: Mapping[str, Any] | None = None
    ) -> Mapping[str, Any]:
        body = None if payload is None else canonical_json_bytes(payload)
        headers = {
            "Accept": "application/json",
            "User-Agent": "chummer-public-download-cutover/1",
            **self.auth_headers,
        }
        if body is not None:
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(
            self.api_base + path, data=body, headers=headers, method=method
        )
        try:
            with urllib.request.urlopen(
                request, timeout=self.timeout_seconds
            ) as response:
                raw = response.read(MAX_JSON_BYTES + 1)
        except urllib.error.HTTPError as exc:
            raise ApiError(f"Cloudflare API returned HTTP {exc.code}") from exc
        except urllib.error.URLError as exc:
            raise ApiError("Cloudflare API request failed") from exc
        if len(raw) > MAX_JSON_BYTES:
            raise ApiError("Cloudflare API response exceeds size limit")
        try:
            parsed = json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ApiError("Cloudflare API returned invalid JSON") from exc
        if not isinstance(parsed, Mapping):
            raise ApiError("Cloudflare API returned a non-object response")
        return parsed

    def get_configuration(self) -> Mapping[str, Any]:
        return self._request("GET", self.tunnel_path + "/configurations")

    def put_configuration(self, config: Mapping[str, Any]) -> Mapping[str, Any]:
        return self._request(
            "PUT", self.tunnel_path + "/configurations", {"config": config}
        )

    def list_connections(self) -> Mapping[str, Any]:
        return self._request("GET", self.tunnel_path + "/connections")

    def get_connector(self, connector_id: str) -> Mapping[str, Any]:
        connector = urllib.parse.quote(
            _require_identifier(connector_id, "connector id"), safe=""
        )
        return self._request(
            "GET", self.tunnel_path + f"/connectors/{connector}"
        )


def resolve_auth_headers(
    environment: Mapping[str, str],
    *,
    api_token_env: str,
    allow_legacy_global_key_auth: bool,
    legacy_email_env: str,
    legacy_global_key_env: str,
) -> dict[str, str]:
    token = environment.get(api_token_env, "")
    if token:
        return {"Authorization": f"Bearer {token}"}
    email = environment.get(legacy_email_env, "")
    global_key = environment.get(legacy_global_key_env, "")
    if allow_legacy_global_key_auth:
        if not email or not global_key:
            raise ValidationError(
                "legacy auth requires both email and global-key environment values"
            )
        return {"X-Auth-Email": email, "X-Auth-Key": global_key}
    if email or global_key:
        raise ValidationError(
            "legacy global-key credentials require explicit opt-in"
        )
    raise ValidationError("Cloudflare API token is unavailable")


def _summary(journal: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema": journal["schema"],
        "phase": journal["phase"],
        "accountId": journal["accountId"],
        "tunnelId": journal["tunnelId"],
        "priorConfigSha256": journal["priorConfigSha256"],
        "targetConfigSha256": journal["targetConfigSha256"],
        "targetVersion": journal["targetVersion"],
        "connectorConvergence": journal["connectorConvergence"],
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--account-id", required=True)
    parser.add_argument("--tunnel-id", required=True)
    parser.add_argument("--journal", required=True, type=Path)
    parser.add_argument("--lock", required=True, type=Path)
    parser.add_argument(
        "--api-base", default="https://api.cloudflare.com/client/v4"
    )
    parser.add_argument("--api-token-env", default="CLOUDFLARE_API_TOKEN")
    parser.add_argument("--allow-legacy-global-key-auth", action="store_true")
    parser.add_argument("--legacy-email-env", default="CLOUDFLARE_EMAIL")
    parser.add_argument(
        "--legacy-global-key-env", default="CLOUDFLARE_GLOBAL_API_KEY"
    )
    parser.add_argument("--timeout-seconds", type=float, default=20.0)
    subparsers = parser.add_subparsers(dest="command", required=True)
    capture = subparsers.add_parser("capture")
    capture.add_argument("--origin", required=True)
    capture.add_argument("--generation-id", required=True)
    capture.add_argument("--probe-endpoint", required=True)
    capture.add_argument("--probe-body-sha256", required=True)
    apply = subparsers.add_parser("apply")
    apply.add_argument("--poll-attempts", type=int, default=30)
    apply.add_argument("--poll-interval-seconds", type=float, default=2.0)
    rollback = subparsers.add_parser("rollback")
    rollback.add_argument("--poll-attempts", type=int, default=30)
    rollback.add_argument("--poll-interval-seconds", type=float, default=2.0)
    rollback.add_argument("--evidence-output", type=Path, required=True)
    commit = subparsers.add_parser("commit")
    commit.add_argument("--evidence-output", type=Path, required=True)
    commit.add_argument("--external-probe-receipt", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        headers = resolve_auth_headers(
            os.environ,
            api_token_env=args.api_token_env,
            allow_legacy_global_key_auth=args.allow_legacy_global_key_auth,
            legacy_email_env=args.legacy_email_env,
            legacy_global_key_env=args.legacy_global_key_env,
        )
        api = CloudflareTunnelApi(
            api_base=args.api_base,
            account_id=args.account_id,
            tunnel_id=args.tunnel_id,
            auth_headers=headers,
            timeout_seconds=args.timeout_seconds,
        )
        common = {
            "api": api,
            "journal_path": args.journal,
            "lock_path": args.lock,
        }
        if args.command == "capture":
            journal = capture_transaction(
                account_id=args.account_id,
                tunnel_id=args.tunnel_id,
                origin=args.origin,
                generation_id=args.generation_id,
                probe_endpoint=args.probe_endpoint,
                probe_body_sha256=args.probe_body_sha256,
                **common,
            )
        elif args.command == "apply":
            journal = apply_transaction(
                attempts=args.poll_attempts,
                interval_seconds=args.poll_interval_seconds,
                **common,
            )
        elif args.command == "rollback":
            journal = rollback_transaction(
                evidence_path=args.evidence_output,
                attempts=args.poll_attempts,
                interval_seconds=args.poll_interval_seconds,
                **common,
            )
        else:
            journal = commit_transaction(
                evidence_path=args.evidence_output,
                external_probe_receipt=args.external_probe_receipt,
                **common,
            )
        print(json.dumps(_summary(journal), sort_keys=True))
        return 0
    except TransactionError as exc:
        print(f"cloudflare ingress transaction failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Fail-closed contracts for Google OAuth operator evidence.

This module owns Google-specific binding and media rules. Ed25519 trust and
signature verification remain delegated to verify_detached_ed25519_attestation.
"""

from __future__ import annotations

import errno
import hashlib
import json
import os
import secrets
import stat
import struct
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Mapping

_IMPORT_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_IMPORT_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_IMPORT_SCRIPT_DIR))

from verify_detached_ed25519_attestation import (
    canonical_json_bytes,
    parse_time,
    verify_detached_attestation,
)


SCRIPT_DIR = Path(__file__).resolve().parent
RUN_SERVICES_ROOT = SCRIPT_DIR.parent
DEFAULT_BASE_URL = "https://chummer.run"
DEFAULT_PORTAL_RELEASE_MANIFEST_PATH = (
    RUN_SERVICES_ROOT / "Chummer.Portal" / "downloads" / "RELEASE_CHANNEL.generated.json"
)
DEFAULT_HUB_RELEASE_MANIFEST_PATH = (
    RUN_SERVICES_ROOT.parent
    / "chummer-hub-registry"
    / ".codex-studio"
    / "published"
    / "RELEASE_CHANNEL.generated.json"
)
# Compatibility alias for callers that need one local release path. Security
# decisions use release_authority_binding() and therefore never use this alone.
DEFAULT_RELEASE_MANIFEST_PATH = DEFAULT_PORTAL_RELEASE_MANIFEST_PATH
DEFAULT_REQUEST_PATH = (
    RUN_SERVICES_ROOT
    / ".codex-studio"
    / "published"
    / "GOOGLE_OAUTH_LINKING_OPERATOR_EVIDENCE_REQUEST.generated.json"
)
DEFAULT_EVIDENCE_PATH = (
    RUN_SERVICES_ROOT
    / ".codex-studio"
    / "published"
    / "GOOGLE_OAUTH_LINKING_OPERATOR_EVIDENCE.generated.json"
)
DEFAULT_PROOF_PATH = (
    RUN_SERVICES_ROOT
    / ".codex-studio"
    / "published"
    / "GOOGLE_OAUTH_LINKING_PROOF.generated.json"
)
DEFAULT_IMPORTED_SCREENSHOT_ROOT = (
    RUN_SERVICES_ROOT / ".state" / "google_oauth_linking_operator_evidence" / "imported"
)

REQUEST_CONTRACT_NAME = "chummer.run.google_oauth_linking_operator_evidence_request.v2"
EVIDENCE_CONTRACT_NAME = "chummer.run.google_oauth_linking_operator_evidence.v2"
ATTESTATION_CONTRACT_NAME = "chummer.run.google_oauth_linking_operator_attestation.v2"
PROOF_CONTRACT_NAME = "chummer.run.google_oauth_linking_proof"
PROOF_CONTRACT_VERSION = 3
ATTESTATION_ROLE = "google_oauth_linking_operator"

# This is deliberately empty. A production pass is impossible until a reviewed
# public key and digest are committed here. There is no env/CLI trust override.
TRUSTED_OPERATOR_IDENTITIES: Mapping[str, Mapping[str, str]] = {}
TRUSTED_KEY_ROOT = SCRIPT_DIR / "trusted_keys" / "google_oauth_linking"

REQUEST_MAX_AGE = timedelta(hours=24)
OBSERVATION_MAX_AGE = timedelta(hours=4)
PROOF_MAX_AGE = timedelta(minutes=20)
FUTURE_TOLERANCE = timedelta(minutes=5)
MINIMUM_SCREENSHOT_COUNT = 2
MINIMUM_IMAGE_BYTES = 4096
MINIMUM_IMAGE_WIDTH = 640
MINIMUM_IMAGE_HEIGHT = 360
MAXIMUM_IMAGE_BYTES = 50 * 1024 * 1024

REQUIRED_OPERATOR_STEPS = (
    "google_sign_in_completed_to_signed_in_state",
    "existing_account_linked_google",
    "google_sign_in_returned_to_existing_account",
    "linked_provider_visible_on_signed_in_surface",
)

PROGRAM_PATHS: Mapping[str, Path] = {
    "request_materializer": SCRIPT_DIR / "materialize_google_oauth_linking_operator_evidence_request.py",
    "request_verifier": SCRIPT_DIR / "verify_google_oauth_linking_operator_evidence_request.py",
    "evidence_importer": SCRIPT_DIR / "import_google_oauth_linking_operator_evidence_artifact.py",
    "evidence_auto_importer": SCRIPT_DIR / "auto_import_google_oauth_linking_operator_evidence.py",
    "proof_materializer": SCRIPT_DIR / "materialize_google_oauth_linking_proof.py",
    "proof_verifier": SCRIPT_DIR / "verify_google_oauth_linking_proof.py",
    "google_contract_verifier": Path(__file__).resolve(),
    "detached_attestation_verifier": SCRIPT_DIR / "verify_detached_ed25519_attestation.py",
}


class ContractError(RuntimeError):
    """Raised when a code-owned binding cannot be captured safely."""


def utc_now() -> datetime:
    return datetime.now(UTC)


def isoformat_utc(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def is_sha256(value: object) -> bool:
    text = str(value or "").strip().lower()
    return len(text) == 64 and all(character in "0123456789abcdef" for character in text)


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_json(value: object) -> str:
    return sha256_bytes(canonical_json_bytes(value))


def read_regular_file_bytes(path: Path, *, max_bytes: int) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except FileNotFoundError as exc:
        raise ContractError(f"missing regular file: {path}") from exc
    except OSError as exc:
        if exc.errno == errno.ELOOP:
            raise ContractError(f"symlink rejected: {path}") from exc
        raise ContractError(f"unreadable regular file: {path}") from exc
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise ContractError(f"not a regular file: {path}")
        if before.st_size > max_bytes:
            raise ContractError(f"file exceeds {max_bytes} bytes: {path}")
        chunks: list[bytes] = []
        remaining = max_bytes + 1
        while remaining > 0:
            chunk = os.read(descriptor, min(65536, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        data = b"".join(chunks)
        if len(data) > max_bytes:
            raise ContractError(f"file exceeds {max_bytes} bytes: {path}")
        after = os.fstat(descriptor)
        identity_fields = ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")
        if any(getattr(before, field) != getattr(after, field) for field in identity_fields):
            raise ContractError(f"file changed during read: {path}")
        return data
    finally:
        os.close(descriptor)


def read_json_object(path: Path) -> tuple[dict[str, Any], bytes]:
    raw = read_regular_file_bytes(path, max_bytes=8 * 1024 * 1024)
    try:
        payload = json.loads(raw.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ContractError(f"invalid JSON object: {path}") from exc
    if not isinstance(payload, dict):
        raise ContractError(f"JSON root is not an object: {path}")
    return payload, raw


def relative_program_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(RUN_SERVICES_ROOT.resolve()).as_posix()
    except ValueError as exc:
        raise ContractError(f"program escapes run-services root: {path}") from exc


def program_bindings() -> dict[str, dict[str, Any]]:
    bindings: dict[str, dict[str, Any]] = {}
    for name, path in PROGRAM_PATHS.items():
        raw = read_regular_file_bytes(path, max_bytes=4 * 1024 * 1024)
        bindings[name] = {
            "path": str(path.resolve()),
            "relative_path": relative_program_path(path),
            "sha256": sha256_bytes(raw),
            "size_bytes": len(raw),
        }
    return bindings


def release_binding(path: Path = DEFAULT_RELEASE_MANIFEST_PATH) -> dict[str, Any]:
    payload, raw = read_json_object(path)
    release_tuple = {
        "version": str(payload.get("version") or payload.get("releaseVersion") or "").strip(),
        "channel": str(payload.get("channelId") or payload.get("channel") or "").strip(),
        "supportability_state": str(payload.get("supportabilityState") or "").strip(),
        "rollout_state": str(payload.get("rolloutState") or "").strip(),
        "published_at": str(payload.get("publishedAt") or payload.get("published_at") or "").strip(),
    }
    missing = [name for name, value in release_tuple.items() if not value]
    if missing:
        raise ContractError(f"release manifest is missing tuple fields: {', '.join(missing)}")
    return {
        "manifest_path": str(path.resolve()),
        "manifest_sha256": sha256_bytes(raw),
        "manifest_size_bytes": len(raw),
        **release_tuple,
        "tuple_sha256": sha256_json(release_tuple),
    }


def release_authority_binding(
    *,
    portal_path: Path = DEFAULT_PORTAL_RELEASE_MANIFEST_PATH,
    hub_path: Path = DEFAULT_HUB_RELEASE_MANIFEST_PATH,
    live_capture_path: Path | None = None,
    live_captured_at_utc: str | None = None,
) -> dict[str, Any]:
    portal = release_binding(portal_path)
    hub = release_binding(hub_path)
    live: dict[str, Any]
    if live_capture_path is None:
        live = {
            "status": "not_captured",
            "source_url": "https://chummer.run/downloads/RELEASE_CHANNEL.generated.json",
            "capture_path": None,
            "captured_at_utc": None,
        }
    else:
        live = {
            "status": "captured",
            "source_url": "https://chummer.run/downloads/RELEASE_CHANNEL.generated.json",
            "capture_path": str(live_capture_path.resolve()),
            "captured_at_utc": str(live_captured_at_utc or "").strip() or None,
            **release_binding(live_capture_path),
        }

    identity_fields = ("version", "channel", "published_at")
    posture_fields = ("supportability_state", "rollout_state")
    portal_identity = {field: portal.get(field) for field in identity_fields}
    hub_identity = {field: hub.get(field) for field in identity_fields}
    portal_posture = {field: portal.get(field) for field in posture_fields}
    hub_posture = {field: hub.get(field) for field in posture_fields}
    identity_agrees = portal_identity == hub_identity
    posture_agrees = portal_posture == hub_posture
    live_identity_agrees = False
    live_posture_agrees = False
    if live.get("status") == "captured":
        live_identity = {field: live.get(field) for field in identity_fields}
        live_posture = {field: live.get(field) for field in posture_fields}
        live_identity_agrees = live_identity == portal_identity == hub_identity
        live_posture_agrees = live_posture == portal_posture == hub_posture
    blockers: list[str] = []
    if not identity_agrees:
        blockers.append("portal_and_hub_release_identity_disagree")
    if not posture_agrees:
        blockers.append("portal_and_hub_release_posture_disagree")
    if live.get("status") != "captured":
        blockers.append("live_release_manifest_not_captured")
    else:
        if not live_identity_agrees:
            blockers.append("live_release_identity_disagrees")
        if not live_posture_agrees:
            blockers.append("live_release_posture_disagrees")
    return {
        "portal": portal,
        "hub_registry": hub,
        "live": live,
        "identity_fields": list(identity_fields),
        "posture_fields": list(posture_fields),
        "portal_hub_identity_agrees": identity_agrees,
        "portal_hub_posture_agrees": posture_agrees,
        "live_identity_agrees": live_identity_agrees,
        "live_posture_agrees": live_posture_agrees,
        "ready": not blockers,
        "blockers": blockers,
    }


def media_policy() -> dict[str, Any]:
    return {
        "minimum_screenshot_count": MINIMUM_SCREENSHOT_COUNT,
        "minimum_image_bytes": MINIMUM_IMAGE_BYTES,
        "minimum_width": MINIMUM_IMAGE_WIDTH,
        "minimum_height": MINIMUM_IMAGE_HEIGHT,
        "allowed_media_types": ["image/png", "image/jpeg"],
        "distinct_sha256_required": True,
    }


def request_binding_basis(
    *,
    base_url: str,
    release: Mapping[str, Any],
    programs: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "base_url": base_url,
        "release": dict(release),
        "programs": dict(programs),
        "required_operator_steps": list(REQUIRED_OPERATOR_STEPS),
        "media_policy": media_policy(),
        "attestation_contract_name": ATTESTATION_CONTRACT_NAME,
        "attestation_role": ATTESTATION_ROLE,
    }


def request_binding_sha256(
    *,
    base_url: str,
    release: Mapping[str, Any],
    programs: Mapping[str, Any],
) -> str:
    return sha256_json(
        request_binding_basis(base_url=base_url, release=release, programs=programs)
    )


def request_is_fresh(payload: Mapping[str, Any], *, now: datetime) -> bool:
    generated_at = parse_time(payload.get("generated_at_utc"))
    if generated_at is None:
        return False
    return generated_at <= now + FUTURE_TOLERANCE and now - generated_at <= REQUEST_MAX_AGE


def reusable_request_identity(
    previous: Mapping[str, Any] | None,
    *,
    binding_sha256: str,
    now: datetime,
) -> tuple[str, str, bool]:
    previous = previous if isinstance(previous, Mapping) else {}
    nonce = str(previous.get("request_nonce") or "").strip().lower()
    generated_at = str(previous.get("generated_at_utc") or "").strip()
    reusable = (
        previous.get("contract_name") == REQUEST_CONTRACT_NAME
        and previous.get("request_binding_sha256") == binding_sha256
        and len(nonce) == 64
        and all(character in "0123456789abcdef" for character in nonce)
        and request_is_fresh(previous, now=now)
    )
    if reusable:
        return nonce, generated_at, True
    return secrets.token_hex(32), isoformat_utc(now), False


def fixed_post_import_argv_plan(
    *,
    base_url: str,
    request_path: Path,
    evidence_path: Path = DEFAULT_EVIDENCE_PATH,
    proof_path: Path = DEFAULT_PROOF_PATH,
) -> list[list[str]]:
    # This plan is code-owned. Importers must never replace it with JSON strings.
    return [
        [
            "python3",
            "scripts/materialize_google_oauth_linking_operator_evidence_request.py",
            "--output",
            str(request_path),
            "--base-url",
            base_url,
        ],
        [
            "python3",
            "scripts/verify_google_oauth_linking_operator_evidence_request.py",
            "--receipt",
            str(request_path),
        ],
        [
            "python3",
            "scripts/materialize_google_oauth_linking_proof.py",
            "--base-url",
            base_url,
            "--output",
            str(proof_path),
            "--operator-evidence",
            str(evidence_path),
        ],
        [
            "python3",
            "scripts/verify_google_oauth_linking_proof.py",
            "--receipt",
            str(proof_path),
            "--require-pass",
        ],
    ]


def _time_failures(
    value: object,
    *,
    field: str,
    now: datetime,
    max_age: timedelta,
    not_before: datetime | None = None,
) -> tuple[datetime | None, list[str]]:
    parsed = parse_time(value)
    if parsed is None:
        return None, [f"{field} must be a timezone-aware timestamp"]
    failures: list[str] = []
    if parsed > now + FUTURE_TOLERANCE:
        failures.append(f"{field} is in the future")
    if now - parsed > max_age:
        failures.append(f"{field} is stale")
    if not_before is not None and parsed < not_before - FUTURE_TOLERANCE:
        failures.append(f"{field} predates the current request")
    return parsed, failures


def verify_request_payload(
    payload: Mapping[str, Any],
    *,
    request_path: Path,
    portal_release_manifest_path: Path = DEFAULT_PORTAL_RELEASE_MANIFEST_PATH,
    hub_release_manifest_path: Path = DEFAULT_HUB_RELEASE_MANIFEST_PATH,
    now: datetime | None = None,
) -> tuple[dict[str, Any], list[str]]:
    now = (now or utc_now()).astimezone(UTC)
    request_path = request_path.expanduser().resolve(strict=False)
    failures: list[str] = []
    if payload.get("contract_name") != REQUEST_CONTRACT_NAME:
        failures.append(f"contract_name must be {REQUEST_CONTRACT_NAME}")
    if payload.get("base_url") != DEFAULT_BASE_URL:
        failures.append(f"base_url must be {DEFAULT_BASE_URL}")
    _, time_failures = _time_failures(
        payload.get("generated_at_utc"),
        field="generated_at_utc",
        now=now,
        max_age=REQUEST_MAX_AGE,
    )
    failures.extend(time_failures)
    nonce = str(payload.get("request_nonce") or "").strip().lower()
    if len(nonce) != 64 or any(character not in "0123456789abcdef" for character in nonce):
        failures.append("request_nonce must be a 32-byte lowercase hex challenge")
    claimed_request_path = Path(str(payload.get("request_receipt_path") or "")).expanduser().resolve(strict=False)
    if claimed_request_path != request_path:
        failures.append("request_receipt_path does not match the current request path")

    try:
        claimed_release = payload.get("release")
        claimed_release = claimed_release if isinstance(claimed_release, Mapping) else {}
        claimed_live = claimed_release.get("live")
        claimed_live = claimed_live if isinstance(claimed_live, Mapping) else {}
        live_capture_text = str(claimed_live.get("capture_path") or "").strip()
        current_release = release_authority_binding(
            portal_path=portal_release_manifest_path,
            hub_path=hub_release_manifest_path,
            live_capture_path=Path(live_capture_text) if live_capture_text else None,
            live_captured_at_utc=str(claimed_live.get("captured_at_utc") or ""),
        )
    except ContractError as exc:
        current_release = {}
        failures.append(str(exc))
    if claimed_release != current_release:
        failures.append("release binding does not match exact portal/hub/live bytes and tuples")
    expected_status = (
        "operator_action_required"
        if current_release.get("ready") is True
        else "blocked_release_authority"
    )
    if payload.get("status") != expected_status:
        failures.append(f"status must be {expected_status} for the current release authority state")
    if current_release.get("ready") is not True:
        failures.extend(
            f"release_authority: {item}"
            for item in current_release.get("blockers") or []
        )
    claimed_live = current_release.get("live") if isinstance(current_release.get("live"), Mapping) else {}
    if claimed_live.get("status") == "captured":
        _, live_capture_time_failures = _time_failures(
            claimed_live.get("captured_at_utc"),
            field="release.live.captured_at_utc",
            now=now,
            max_age=REQUEST_MAX_AGE,
        )
        failures.extend(live_capture_time_failures)

    try:
        current_programs = program_bindings()
    except ContractError as exc:
        current_programs = {}
        failures.append(str(exc))
    claimed_programs = payload.get("program_bindings")
    if claimed_programs != current_programs:
        failures.append("program_bindings do not match the current verifier/importer bytes")

    expected_binding_sha = request_binding_sha256(
        base_url=DEFAULT_BASE_URL,
        release=current_release,
        programs=current_programs,
    ) if current_release and current_programs else ""
    if payload.get("request_binding_sha256") != expected_binding_sha:
        failures.append("request_binding_sha256 does not match current release/program bindings")
    if payload.get("required_steps") != list(REQUIRED_OPERATOR_STEPS):
        failures.append("required_steps do not match the code-owned operator program")
    if payload.get("media_policy") != media_policy():
        failures.append("media_policy does not match the code-owned image policy")

    evidence_path = Path(
        str(payload.get("required_operator_evidence_path") or DEFAULT_EVIDENCE_PATH)
    ).expanduser().resolve(strict=False)
    proof_path_text = str(payload.get("required_proof_path") or "").strip()
    if not proof_path_text:
        failures.append("required_proof_path is missing")
    proof_path = Path(proof_path_text or DEFAULT_PROOF_PATH).expanduser().resolve(strict=False)
    expected_plan = (
        fixed_post_import_argv_plan(
            base_url=DEFAULT_BASE_URL,
            request_path=request_path,
            evidence_path=evidence_path,
            proof_path=proof_path,
        )
        if current_release.get("ready") is True
        else []
    )
    artifact_intake = payload.get("artifact_intake")
    artifact_intake = artifact_intake if isinstance(artifact_intake, Mapping) else {}
    if payload.get("intake") != artifact_intake:
        failures.append("intake alias does not match artifact_intake")
    if artifact_intake.get("post_import_argv_plan") != expected_plan:
        failures.append(
            "post_import_argv_plan does not match the release-authority-scoped code-owned plan"
        )

    canonical_request_path = DEFAULT_REQUEST_PATH.expanduser().resolve(strict=False)
    staged = request_path != canonical_request_path
    stage_root = request_path.parent
    scope = payload.get("materialization_scope")
    scope = scope if isinstance(scope, Mapping) else {}
    expected_scope_mode = "staged" if staged else "canonical"
    if scope.get("mode") != expected_scope_mode:
        failures.append(f"materialization_scope.mode must be {expected_scope_mode}")
    if scope.get("self_contained") is not staged:
        failures.append(
            f"materialization_scope.self_contained must be {str(staged).lower()}"
        )
    scope_root_text = str(scope.get("root") or "").strip()
    if not scope_root_text or Path(scope_root_text).expanduser().resolve(strict=False) != stage_root:
        failures.append("materialization_scope.root does not match the request directory")
    scope_proof_text = str(scope.get("proof_output_path") or "").strip()
    if not scope_proof_text or Path(scope_proof_text).expanduser().resolve(strict=False) != proof_path:
        failures.append("materialization_scope.proof_output_path does not match required_proof_path")

    if staged:
        staged_path_fields: list[tuple[str, object]] = [
            ("request_receipt_path", payload.get("request_receipt_path")),
            ("required_output_path", payload.get("required_output_path")),
            ("required_receipt_path", payload.get("required_receipt_path")),
            ("required_operator_evidence_path", payload.get("required_operator_evidence_path")),
            ("required_proof_path", payload.get("required_proof_path")),
            ("template_path", payload.get("template_path")),
            ("operator_evidence_template_path", payload.get("operator_evidence_template_path")),
            ("operator_message_path", payload.get("operator_message_path")),
            ("operator_ask_text_path", payload.get("operator_ask_text_path")),
            ("operator_ask_metadata_path", payload.get("operator_ask_metadata_path")),
            ("preferred_drop_folder", payload.get("preferred_drop_folder")),
            ("artifact_intake.dedicated_drop_root", artifact_intake.get("dedicated_drop_root")),
        ]
        staged_path_fields.extend(
            (f"recommended_screenshot_paths[{index}]", value)
            for index, value in enumerate(payload.get("recommended_screenshot_paths") or [])
        )
        staged_path_fields.extend(
            (f"artifact_intake.auto_import_roots[{index}]", value)
            for index, value in enumerate(artifact_intake.get("auto_import_roots") or [])
        )
        preferred_drop_path = str(artifact_intake.get("preferred_drop_path") or "").strip()
        if preferred_drop_path:
            staged_path_fields.append(
                ("artifact_intake.preferred_drop_path", preferred_drop_path)
            )
        for field, value in staged_path_fields:
            text = str(value or "").strip()
            if not text or not _is_within(Path(text), stage_root):
                failures.append(f"{field} escapes the noncanonical request stage root")
        if proof_path == DEFAULT_PROOF_PATH.expanduser().resolve(strict=False):
            failures.append("noncanonical request must not target the canonical proof output")

    if current_release.get("ready") is not True:
        draft = payload.get("operator_telegram_draft")
        draft = draft if isinstance(draft, Mapping) else {}
        materialized_draft = payload.get("operator_telegram_draft_materialized")
        materialized_draft = materialized_draft if isinstance(materialized_draft, Mapping) else {}
        blocked_execution_surfaces = [
            ("send_command", payload.get("send_command")),
            ("import_argv", payload.get("import_argv")),
            ("artifact_intake.discover_command", artifact_intake.get("discover_command")),
            ("artifact_intake.import_argv", artifact_intake.get("import_argv")),
            ("artifact_intake.auto_import_argv", artifact_intake.get("auto_import_argv")),
            ("artifact_intake.auto_import_watch_argv", artifact_intake.get("auto_import_watch_argv")),
            ("artifact_intake.post_import_argv_plan", artifact_intake.get("post_import_argv_plan")),
            ("operator_telegram_draft.send_command", draft.get("send_command")),
            ("operator_telegram_draft.import_command", draft.get("import_command")),
            ("operator_telegram_draft.auto_import_command", draft.get("auto_import_command")),
            ("operator_telegram_draft.auto_import_watch_command", draft.get("auto_import_watch_command")),
            ("operator_telegram_draft_materialized.send_command", materialized_draft.get("send_command")),
            ("operator_telegram_draft_materialized.import_command", materialized_draft.get("import_command")),
            ("operator_telegram_draft_materialized.auto_import_command", materialized_draft.get("auto_import_command")),
            ("operator_telegram_draft_materialized.auto_import_watch_command", materialized_draft.get("auto_import_watch_command")),
        ]
        for field, value in blocked_execution_surfaces:
            if value not in (None, "", []):
                failures.append(f"{field} must be empty while release authority is blocked")

        recovery = payload.get("recovery")
        recovery = recovery if isinstance(recovery, Mapping) else {}
        if recovery.get("status") != "blocked_release_authority":
            failures.append("recovery.status must describe blocked_release_authority")
        if recovery.get("execution_authority_present") is not False:
            failures.append("recovery.execution_authority_present must be false")
        if recovery.get("release_authority_blockers") != list(current_release.get("blockers") or []):
            failures.append("recovery release authority blockers do not match the current release")
        if not str(recovery.get("summary") or "").strip():
            failures.append("recovery.summary is required while release authority is blocked")
        required_conditions = recovery.get("required_conditions")
        if not isinstance(required_conditions, list) or not required_conditions:
            failures.append("recovery.required_conditions must explain how to restore authority")

    for forbidden_field in ("post_import_commands", "post_import_gates"):
        if payload.get(forbidden_field):
            failures.append(f"{forbidden_field} is forbidden; shell commands are not intake authority")
        if artifact_intake.get(forbidden_field):
            failures.append(f"artifact_intake.{forbidden_field} is forbidden")

    summary = {
        "status": "fail" if failures else "pass",
        "contract_name": payload.get("contract_name"),
        "request_path": str(request_path),
        "request_nonce": nonce or None,
        "generated_at_utc": payload.get("generated_at_utc"),
        "request_binding_sha256": payload.get("request_binding_sha256"),
        "release": current_release,
        "program_bindings": current_programs,
    }
    return summary, failures


def verify_request_file(
    request_path: Path = DEFAULT_REQUEST_PATH,
    *,
    portal_release_manifest_path: Path = DEFAULT_PORTAL_RELEASE_MANIFEST_PATH,
    hub_release_manifest_path: Path = DEFAULT_HUB_RELEASE_MANIFEST_PATH,
    now: datetime | None = None,
) -> tuple[dict[str, Any], dict[str, Any], bytes, list[str]]:
    try:
        payload, raw = read_json_object(request_path)
    except ContractError as exc:
        return {}, {}, b"", [str(exc)]
    summary, failures = verify_request_payload(
        payload,
        request_path=request_path,
        portal_release_manifest_path=portal_release_manifest_path,
        hub_release_manifest_path=hub_release_manifest_path,
        now=now,
    )
    summary["request_sha256"] = sha256_bytes(raw)
    summary["request_size_bytes"] = len(raw)
    return payload, summary, raw, failures


def _png_dimensions(data: bytes) -> tuple[int, int] | None:
    if len(data) < 24 or data[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    if data[12:16] != b"IHDR" or struct.unpack(">I", data[8:12])[0] != 13:
        return None
    width, height = struct.unpack(">II", data[16:24])
    return (width, height) if width and height else None


def _jpeg_dimensions(data: bytes) -> tuple[int, int] | None:
    if len(data) < 4 or data[:2] != b"\xff\xd8" or data[-2:] != b"\xff\xd9":
        return None
    offset = 2
    sof_markers = {
        0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7,
        0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF,
    }
    while offset + 4 <= len(data):
        if data[offset] != 0xFF:
            offset += 1
            continue
        while offset < len(data) and data[offset] == 0xFF:
            offset += 1
        if offset >= len(data):
            return None
        marker = data[offset]
        offset += 1
        if marker in {0xD8, 0xD9} or 0xD0 <= marker <= 0xD7:
            continue
        if offset + 2 > len(data):
            return None
        length = struct.unpack(">H", data[offset:offset + 2])[0]
        if length < 2 or offset + length > len(data):
            return None
        if marker in sof_markers:
            if length < 7:
                return None
            height, width = struct.unpack(">HH", data[offset + 3:offset + 7])
            return (width, height) if width and height else None
        offset += length
    return None


def inspect_image(path: Path) -> tuple[dict[str, Any], list[str]]:
    failures: list[str] = []
    try:
        data = read_regular_file_bytes(path, max_bytes=MAXIMUM_IMAGE_BYTES)
    except ContractError as exc:
        return {"path": str(path)}, [str(exc)]
    media_type = ""
    dimensions = _png_dimensions(data)
    if dimensions is not None:
        media_type = "image/png"
    else:
        dimensions = _jpeg_dimensions(data)
        if dimensions is not None:
            media_type = "image/jpeg"
    if not media_type or dimensions is None:
        failures.append("screenshot is not a structurally recognizable PNG or JPEG")
        width = height = 0
    else:
        width, height = dimensions
    if len(data) < MINIMUM_IMAGE_BYTES:
        failures.append(f"screenshot is smaller than {MINIMUM_IMAGE_BYTES} bytes")
    if width < MINIMUM_IMAGE_WIDTH or height < MINIMUM_IMAGE_HEIGHT:
        failures.append(
            f"screenshot dimensions are below {MINIMUM_IMAGE_WIDTH}x{MINIMUM_IMAGE_HEIGHT}"
        )
    return {
        "path": str(path),
        "sha256": sha256_bytes(data),
        "size_bytes": len(data),
        "width": width,
        "height": height,
        "media_type": media_type or None,
    }, failures


def is_test_provenance_path(value: object) -> bool:
    text = str(value or "").replace("\\", "/").lower()
    markers = (
        "/pytest-",
        "/pytest-of-",
        "/.pytest_cache/",
        "/test_",
        "/tests/fixtures/",
        "pytest-current",
    )
    return any(marker in text for marker in markers)


def _resolve_screenshot_path(evidence_root: Path, raw: object) -> Path | None:
    text = str(raw or "").strip()
    if not text:
        return None
    path = Path(text)
    return path if path.is_absolute() else evidence_root / path


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except (OSError, ValueError):
        return False


def screenshot_claims(
    payload: Mapping[str, Any],
    *,
    evidence_root: Path,
    allowed_screenshot_root: Path,
) -> tuple[list[dict[str, Any]], list[str]]:
    rows = payload.get("screenshots")
    failures: list[str] = []
    if not isinstance(rows, list) or len(rows) < MINIMUM_SCREENSHOT_COUNT:
        return [], [f"screenshots must contain at least {MINIMUM_SCREENSHOT_COUNT} entries"]
    claims: list[dict[str, Any]] = []
    seen_names: set[str] = set()
    for index, row in enumerate(rows, start=1):
        if not isinstance(row, Mapping):
            failures.append(f"screenshots[{index}] must be an object")
            continue
        logical_name = str(row.get("logical_name") or "").strip()
        if not logical_name or Path(logical_name).name != logical_name:
            failures.append(f"screenshots[{index}].logical_name must be a basename")
        elif logical_name in seen_names:
            failures.append(f"screenshots[{index}].logical_name is duplicated")
        seen_names.add(logical_name)
        path = _resolve_screenshot_path(evidence_root, row.get("path"))
        if path is None:
            failures.append(f"screenshots[{index}].path is missing")
            continue
        if not _is_within(path, allowed_screenshot_root):
            failures.append(f"screenshots[{index}].path escapes the allowed screenshot root")
        actual, media_failures = inspect_image(path)
        failures.extend(f"screenshots[{index}]: {item}" for item in media_failures)
        claim = {
            "logical_name": logical_name,
            "sha256": actual.get("sha256"),
            "size_bytes": actual.get("size_bytes"),
            "width": actual.get("width"),
            "height": actual.get("height"),
            "media_type": actual.get("media_type"),
        }
        for field, actual_value in claim.items():
            if row.get(field) != actual_value:
                failures.append(f"screenshots[{index}].{field} does not match current bytes")
        claims.append(claim)
    digests = [str(row.get("sha256") or "") for row in claims]
    if len(digests) != len(set(digests)):
        failures.append("screenshot SHA-256 digests must be distinct")
    return claims, failures


def evidence_core(payload: Mapping[str, Any], screenshots: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "contract_name": payload.get("contract_name"),
        "status": payload.get("status"),
        "base_url": payload.get("base_url"),
        "observed_at_utc": payload.get("observed_at_utc"),
        "request_nonce": payload.get("request_nonce"),
        "request_sha256": payload.get("request_sha256"),
        "release_authority_sha256": payload.get("release_authority_sha256"),
        "portal_release_manifest_sha256": payload.get("portal_release_manifest_sha256"),
        "hub_release_manifest_sha256": payload.get("hub_release_manifest_sha256"),
        "live_release_manifest_sha256": payload.get("live_release_manifest_sha256"),
        "verified_steps": payload.get("verified_steps"),
        "screenshots": screenshots,
    }


def attestation_claims(core: Mapping[str, Any]) -> dict[str, Any]:
    screenshot_rows = core.get("screenshots") if isinstance(core.get("screenshots"), list) else []
    return {
        "subject_sha256": sha256_json(core),
        "request_nonce": core.get("request_nonce"),
        "request_sha256": core.get("request_sha256"),
        "release_authority_sha256": core.get("release_authority_sha256"),
        "portal_release_manifest_sha256": core.get("portal_release_manifest_sha256"),
        "hub_release_manifest_sha256": core.get("hub_release_manifest_sha256"),
        "live_release_manifest_sha256": core.get("live_release_manifest_sha256"),
        "screenshot_set_sha256": sha256_json(screenshot_rows),
    }


def verify_evidence_payload(
    payload: Mapping[str, Any],
    *,
    evidence_path: Path,
    request_path: Path = DEFAULT_REQUEST_PATH,
    portal_release_manifest_path: Path = DEFAULT_PORTAL_RELEASE_MANIFEST_PATH,
    hub_release_manifest_path: Path = DEFAULT_HUB_RELEASE_MANIFEST_PATH,
    allowed_screenshot_root: Path = DEFAULT_IMPORTED_SCREENSHOT_ROOT,
    require_import_provenance: bool = True,
    now: datetime | None = None,
) -> tuple[dict[str, Any], list[str]]:
    now = (now or utc_now()).astimezone(UTC)
    request_payload, request_summary, request_raw, request_failures = verify_request_file(
        request_path,
        portal_release_manifest_path=portal_release_manifest_path,
        hub_release_manifest_path=hub_release_manifest_path,
        now=now,
    )
    failures = [f"request: {item}" for item in request_failures]
    if payload.get("contract_name") != EVIDENCE_CONTRACT_NAME:
        failures.append(f"contract_name must be {EVIDENCE_CONTRACT_NAME}")
    if payload.get("status") != "pass":
        failures.append("status must be pass")
    if payload.get("base_url") != DEFAULT_BASE_URL:
        failures.append(f"base_url must be {DEFAULT_BASE_URL}")

    request_generated_at = parse_time(request_payload.get("generated_at_utc"))
    observed_at, observation_failures = _time_failures(
        payload.get("observed_at_utc"),
        field="observed_at_utc",
        now=now,
        max_age=OBSERVATION_MAX_AGE,
        not_before=request_generated_at,
    )
    failures.extend(observation_failures)
    expected_request_sha = sha256_bytes(request_raw) if request_raw else ""
    expected_release = request_summary.get("release") if isinstance(request_summary.get("release"), Mapping) else {}
    exact_fields = {
        "request_nonce": request_payload.get("request_nonce"),
        "request_sha256": expected_request_sha,
        "release_authority_sha256": sha256_json(expected_release) if expected_release else "",
        "portal_release_manifest_sha256": (expected_release.get("portal") or {}).get("manifest_sha256"),
        "hub_release_manifest_sha256": (expected_release.get("hub_registry") or {}).get("manifest_sha256"),
        "live_release_manifest_sha256": (expected_release.get("live") or {}).get("manifest_sha256"),
        "verified_steps": list(REQUIRED_OPERATOR_STEPS),
    }
    for field, expected in exact_fields.items():
        if payload.get(field) != expected:
            failures.append(f"{field} does not match the current request/release binding")

    claims, screenshot_failures = screenshot_claims(
        payload,
        evidence_root=evidence_path.parent,
        allowed_screenshot_root=allowed_screenshot_root,
    )
    failures.extend(screenshot_failures)
    core = evidence_core(payload, claims)
    exact_attestation_claims = attestation_claims(core)
    attestation = payload.get("attestation")
    if not isinstance(attestation, Mapping):
        attestation_summary: dict[str, Any] = {"status": "fail"}
        failures.append("detached operator attestation is missing")
    else:
        attestation_summary, attestation_failures = verify_detached_attestation(
            attestation,
            contract_name=ATTESTATION_CONTRACT_NAME,
            role=ATTESTATION_ROLE,
            exact_claims=exact_attestation_claims,
            trusted_identities=TRUSTED_OPERATOR_IDENTITIES,
            trusted_key_root=TRUSTED_KEY_ROOT,
            now=now,
            max_age=OBSERVATION_MAX_AGE,
            request_generated_at=request_generated_at,
        )
        failures.extend(f"attestation: {item}" for item in attestation_failures)

    provenance = payload.get("import_provenance")
    if require_import_provenance:
        if not isinstance(provenance, Mapping):
            failures.append("import_provenance is missing")
            provenance = {}
        source_path = provenance.get("source_artifact_path")
        if is_test_provenance_path(source_path):
            failures.append("import provenance points to a pytest/test-fixture source")
        if not is_sha256(provenance.get("source_artifact_sha256")):
            failures.append("import provenance source_artifact_sha256 is invalid")
        if not is_sha256(provenance.get("source_receipt_sha256")):
            failures.append("import provenance source_receipt_sha256 is invalid")
        current_importer = request_summary.get("program_bindings", {}).get("evidence_importer", {})
        if provenance.get("importer_program_sha256") != current_importer.get("sha256"):
            failures.append("import provenance importer_program_sha256 is stale")
        _, import_time_failures = _time_failures(
            provenance.get("imported_at_utc"),
            field="imported_at_utc",
            now=now,
            max_age=OBSERVATION_MAX_AGE,
            not_before=observed_at,
        )
        failures.extend(import_time_failures)

    for legacy_field in (
        "import_source_artifact",
        "import_source_receipt_path",
        "import_source_screenshot_paths",
    ):
        value = payload.get(legacy_field)
        values = value if isinstance(value, list) else [value]
        if any(is_test_provenance_path(item) for item in values if item):
            failures.append(f"{legacy_field} contains pytest/test-fixture provenance")

    summary = {
        "status": "fail" if failures else "pass",
        "pass": not failures,
        "path": str(evidence_path),
        "contract_name": payload.get("contract_name"),
        "observed_at_utc": payload.get("observed_at_utc"),
        "request_nonce": payload.get("request_nonce"),
        "request_sha256": payload.get("request_sha256"),
        "release_authority_sha256": payload.get("release_authority_sha256"),
        "portal_release_manifest_sha256": payload.get("portal_release_manifest_sha256"),
        "hub_release_manifest_sha256": payload.get("hub_release_manifest_sha256"),
        "live_release_manifest_sha256": payload.get("live_release_manifest_sha256"),
        "screenshot_claims": claims,
        "attestation": attestation_summary,
        "failures": failures,
    }
    return summary, failures


def verify_evidence_file(
    evidence_path: Path = DEFAULT_EVIDENCE_PATH,
    *,
    request_path: Path = DEFAULT_REQUEST_PATH,
    portal_release_manifest_path: Path = DEFAULT_PORTAL_RELEASE_MANIFEST_PATH,
    hub_release_manifest_path: Path = DEFAULT_HUB_RELEASE_MANIFEST_PATH,
    allowed_screenshot_root: Path = DEFAULT_IMPORTED_SCREENSHOT_ROOT,
    require_import_provenance: bool = True,
    now: datetime | None = None,
) -> tuple[dict[str, Any], dict[str, Any], bytes, list[str]]:
    try:
        payload, raw = read_json_object(evidence_path)
    except ContractError as exc:
        return {}, {"status": "fail", "pass": False, "path": str(evidence_path)}, b"", [str(exc)]
    summary, failures = verify_evidence_payload(
        payload,
        evidence_path=evidence_path,
        request_path=request_path,
        portal_release_manifest_path=portal_release_manifest_path,
        hub_release_manifest_path=hub_release_manifest_path,
        allowed_screenshot_root=allowed_screenshot_root,
        require_import_provenance=require_import_provenance,
        now=now,
    )
    summary["evidence_sha256"] = sha256_bytes(raw)
    summary["evidence_size_bytes"] = len(raw)
    return payload, summary, raw, failures


def current_proof_bindings(
    *,
    request_path: Path = DEFAULT_REQUEST_PATH,
    evidence_path: Path = DEFAULT_EVIDENCE_PATH,
    portal_release_manifest_path: Path = DEFAULT_PORTAL_RELEASE_MANIFEST_PATH,
    hub_release_manifest_path: Path = DEFAULT_HUB_RELEASE_MANIFEST_PATH,
    now: datetime | None = None,
) -> tuple[dict[str, Any], list[str]]:
    request_payload, request_summary, request_raw, request_failures = verify_request_file(
        request_path,
        portal_release_manifest_path=portal_release_manifest_path,
        hub_release_manifest_path=hub_release_manifest_path,
        now=now,
    )
    _, evidence_summary, evidence_raw, evidence_failures = verify_evidence_file(
        evidence_path,
        request_path=request_path,
        portal_release_manifest_path=portal_release_manifest_path,
        hub_release_manifest_path=hub_release_manifest_path,
        now=now,
    )
    bindings = {
        "release": request_summary.get("release") or {},
        "request": {
            "path": str(request_path),
            "sha256": sha256_bytes(request_raw) if request_raw else "",
            "request_nonce": request_payload.get("request_nonce"),
            "request_binding_sha256": request_payload.get("request_binding_sha256"),
            "generated_at_utc": request_payload.get("generated_at_utc"),
        },
        "evidence": {
            "path": str(evidence_path),
            "sha256": sha256_bytes(evidence_raw) if evidence_raw else "",
            "observed_at_utc": evidence_summary.get("observed_at_utc"),
            "attester_key_id": (evidence_summary.get("attestation") or {}).get("key_id"),
        },
        "programs": request_summary.get("program_bindings") or {},
    }
    return bindings, [
        *[f"request: {item}" for item in request_failures],
        *[f"evidence: {item}" for item in evidence_failures],
    ]


def verify_proof_payload(
    payload: Mapping[str, Any],
    *,
    request_path: Path = DEFAULT_REQUEST_PATH,
    evidence_path: Path = DEFAULT_EVIDENCE_PATH,
    portal_release_manifest_path: Path = DEFAULT_PORTAL_RELEASE_MANIFEST_PATH,
    hub_release_manifest_path: Path = DEFAULT_HUB_RELEASE_MANIFEST_PATH,
    require_pass: bool = True,
    now: datetime | None = None,
) -> tuple[dict[str, Any], list[str]]:
    now = (now or utc_now()).astimezone(UTC)
    failures: list[str] = []
    if payload.get("contract_name") != PROOF_CONTRACT_NAME:
        failures.append(f"contract_name must be {PROOF_CONTRACT_NAME}")
    if payload.get("proof_contract_version") != PROOF_CONTRACT_VERSION:
        failures.append(f"proof_contract_version must be {PROOF_CONTRACT_VERSION}")
    if payload.get("base_url") != DEFAULT_BASE_URL:
        failures.append(f"base_url must be {DEFAULT_BASE_URL}")
    _, time_failures = _time_failures(
        payload.get("generated_at_utc"),
        field="generated_at_utc",
        now=now,
        max_age=PROOF_MAX_AGE,
    )
    failures.extend(time_failures)
    current_bindings, binding_failures = current_proof_bindings(
        request_path=request_path,
        evidence_path=evidence_path,
        portal_release_manifest_path=portal_release_manifest_path,
        hub_release_manifest_path=hub_release_manifest_path,
        now=now,
    )
    failures.extend(binding_failures)
    if payload.get("bindings") != current_bindings:
        failures.append("proof bindings do not match current release/request/evidence/program bytes")
    if not isinstance(payload.get("quick_handoff_probe"), Mapping) or payload.get("quick_handoff_probe", {}).get("pass") is not True:
        failures.append("quick_handoff_probe is not pass")
    signed_in = payload.get("signed_in_link_handoff")
    if not isinstance(signed_in, Mapping) or str(signed_in.get("status") or "") not in {"pass", "operator_required"}:
        failures.append("signed_in_link_handoff is not pass/operator_required")
    if require_pass:
        if payload.get("status") != "pass":
            failures.append("proof status is not pass")
        if payload.get("failures"):
            failures.append("proof receipt contains failures")
    if payload.get("status") == "pass" and binding_failures:
        failures.append("pass-shaped proof is not backed by current verified evidence")
    summary = {
        "status": "fail" if failures else "pass",
        "proof_status": payload.get("status"),
        "proof_contract_version": payload.get("proof_contract_version"),
        "current_bindings": current_bindings,
        "failures": failures,
    }
    return summary, failures

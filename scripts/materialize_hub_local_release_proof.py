#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import importlib.util
import json
import os
import stat
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlparse


SCRIPT_DIRECTORY = Path(__file__).resolve().parent
if str(SCRIPT_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIRECTORY))

try:
    from scripts.strict_json_contract import canonical_json_bytes
except ModuleNotFoundError:  # Direct `python3 scripts/...` execution.
    from strict_json_contract import canonical_json_bytes


REPO_ROOT = Path(__file__).resolve().parents[1]
M102_SUCCESSOR_FRONTIER_ID = 2897065929
M102_ACTIVE_FLAGSHIP_FRONTIER_ID = 2594403904
M102_FRONTIER_IDS = [M102_SUCCESSOR_FRONTIER_ID, M102_ACTIVE_FLAGSHIP_FRONTIER_ID]
DEFAULT_FLAGSHIP_READINESS_PATH = REPO_ROOT / ".codex-studio" / "published" / "FLAGSHIP_PRODUCT_READINESS.generated.json"
DEFAULT_HUB_LOCAL_RELEASE_PROOF_PATH = REPO_ROOT / ".codex-studio" / "published" / "HUB_LOCAL_RELEASE_PROOF.generated.json"
DEFAULT_SERVED_HUB_LOCAL_RELEASE_PROOF_PATH = REPO_ROOT / "Chummer.Run.Api" / "wwwroot" / "proofs" / "mac-codex-release" / "HUB_LOCAL_RELEASE_PROOF.generated.json"
DEFAULT_RELEASE_CHANNEL_PATH = REPO_ROOT / "Chummer.Portal" / "downloads" / "RELEASE_CHANNEL.generated.json"
FALLBACK_FLAGSHIP_READINESS_PATH = Path("/docker/fleet/.codex-studio/published/FLAGSHIP_PRODUCT_READINESS.generated.json")
CANONICAL_COMPOSE_FILE = "docker-compose.yml"
CANONICAL_PLAYWRIGHT_TIMEOUT_SECONDS = 120
M141_UI_PACKAGE_ID = "next90-m141-ui-capture-direct-screenshot-and-runtime-proof-for-translator-xml-amendment"
M141_UI_FRONTIER_ID = 2354698282
M141_UI_FLAGSHIP_FRONTIER_ID = 1922169755
PUBLIC_JSON_ARTIFACT_MODE = 0o644
STABLE_READ_CHUNK_BYTES = 1024 * 1024
_PUBLIC_EDGE_OVERLAY_MODULE = None


def iso_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _load_public_edge_overlay_module():
    global _PUBLIC_EDGE_OVERLAY_MODULE
    if _PUBLIC_EDGE_OVERLAY_MODULE is not None:
        return _PUBLIC_EDGE_OVERLAY_MODULE
    module_path = SCRIPT_DIRECTORY / "publish_public_edge_portal_overlay.py"
    spec = importlib.util.spec_from_file_location(
        "chummer_hub_release_proof_public_edge_lock",
        module_path,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(
            f"unable to load shared public-edge mutation authority: {module_path}"
        )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    _PUBLIC_EDGE_OVERLAY_MODULE = module
    return module


@contextmanager
def _public_edge_proof_mutation_lock():
    """Serialize proof replacement with standalone overlay deploy/recovery."""

    overlay = _load_public_edge_overlay_module()
    with overlay.public_edge_mutation_lock(activate=True):
        yield


def _stable_regular_file_matches(path: Path, expected_bytes: bytes) -> bool:
    flags = (
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_NONBLOCK", 0)
    )
    try:
        descriptor = os.open(path, flags)
    except OSError:
        return False

    try:
        before = os.fstat(descriptor)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_nlink != 1
            or stat.S_IMODE(before.st_mode) != PUBLIC_JSON_ARTIFACT_MODE
            or before.st_size != len(expected_bytes)
        ):
            return False

        chunks: list[bytes] = []
        total = 0
        read_budget = len(expected_bytes) + 1
        while total < read_budget:
            chunk = os.read(
                descriptor,
                min(STABLE_READ_CHUNK_BYTES, read_budget - total),
            )
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
        after = os.fstat(descriptor)
    finally:
        os.close(descriptor)

    stable_identity_before = (
        before.st_dev,
        before.st_ino,
        before.st_size,
        before.st_mtime_ns,
        before.st_ctime_ns,
        before.st_mode,
        before.st_nlink,
    )
    stable_identity_after = (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
        after.st_ctime_ns,
        after.st_mode,
        after.st_nlink,
    )
    return stable_identity_before == stable_identity_after and b"".join(chunks) == expected_bytes


def _write_public_json_artifact(path: Path, text: str) -> bool:
    """Atomically materialize one public JSON artifact as an exact regular 0644 file."""

    payload = text.encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    if _stable_regular_file_matches(path, payload):
        return False

    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
    )
    temporary_path = Path(temporary_name)
    stream = None
    try:
        stream = os.fdopen(descriptor, "wb")
        descriptor = -1
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
        os.fchmod(stream.fileno(), PUBLIC_JSON_ARTIFACT_MODE)
        os.fsync(stream.fileno())
        stream.close()
        stream = None

        os.replace(temporary_path, path)
        parent_flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_DIRECTORY", 0)
        parent_descriptor = os.open(path.parent, parent_flags)
        try:
            os.fsync(parent_descriptor)
        finally:
            os.close(parent_descriptor)

        if not _stable_regular_file_matches(path, payload):
            raise RuntimeError(f"public JSON artifact did not settle as regular 0644: {path}")
        return True
    finally:
        if stream is not None:
            stream.close()
        elif descriptor >= 0:
            os.close(descriptor)
        try:
            temporary_path.unlink()
        except FileNotFoundError:
            pass


def _stable_payload(payload: dict) -> dict:
    stable = dict(payload)
    stable.pop("generated_at", None)
    stable.pop("generatedAt", None)
    return stable


def _sorted_unique_strings(values: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        candidate = str(value).strip()
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        ordered.append(candidate)
    return ordered


def _append_reason_details(base_reason: str, details: list[str]) -> str:
    normalized_base = str(base_reason or "").strip()
    normalized_details = [
        str(detail).strip().rstrip(".")
        for detail in details
        if str(detail).strip()
    ]
    if not normalized_base:
        return " ".join(f"{detail}." for detail in normalized_details).strip()
    if normalized_base[-1:] not in {".", "!", "?"}:
        normalized_base += "."
    if not normalized_details:
        return normalized_base
    return normalized_base + " " + " ".join(f"{detail}." for detail in normalized_details)


def _load_existing_payload(path: Path) -> dict | None:
    if not path.is_file():
        return None
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return loaded if isinstance(loaded, dict) else None


def _load_flagship_readiness_payload(path: Path) -> dict | None:
    if not path.is_file():
        return None
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return loaded if isinstance(loaded, dict) else None


def _payload_generated_at(payload: dict | None) -> dt.datetime | None:
    if not isinstance(payload, dict):
        return None
    raw_generated_at = str(payload.get("generatedAt") or payload.get("generated_at") or "").strip() or None
    return _parse_iso_timestamp(raw_generated_at)


def _configured_path(name: str, default: Path) -> Path:
    raw = str(os.environ.get(name) or "").strip()
    return Path(raw) if raw else default


def _canonical_flagship_readiness_source_path() -> Path:
    raw = str(os.environ.get("CHUMMER_FLAGSHIP_PRODUCT_READINESS_PATH") or "").strip()
    if raw:
        return Path(raw)
    if FALLBACK_FLAGSHIP_READINESS_PATH.is_file():
        return FALLBACK_FLAGSHIP_READINESS_PATH
    if DEFAULT_FLAGSHIP_READINESS_PATH.is_file():
        return DEFAULT_FLAGSHIP_READINESS_PATH
    return FALLBACK_FLAGSHIP_READINESS_PATH


def _flagship_readiness_path() -> Path:
    raw = str(os.environ.get("CHUMMER_FLAGSHIP_PRODUCT_READINESS_PATH") or "").strip()
    if raw:
        return Path(raw)
    candidates = [path for path in (DEFAULT_FLAGSHIP_READINESS_PATH, FALLBACK_FLAGSHIP_READINESS_PATH) if path.is_file()]
    if candidates:
        def generated_at(path: Path) -> dt.datetime:
            payload = _load_flagship_readiness_payload(path) or {}
            parsed = _parse_iso_timestamp(str(payload.get("generated_at") or payload.get("generatedAt") or ""))
            return parsed or dt.datetime.min.replace(tzinfo=dt.timezone.utc)

        return max(
            candidates,
            key=lambda path: (generated_at(path), path == DEFAULT_FLAGSHIP_READINESS_PATH),
        )
    return FALLBACK_FLAGSHIP_READINESS_PATH


def _release_channel_path() -> Path:
    for env_name in ("CHUMMER_HUB_RELEASE_CHANNEL_PATH", "CHUMMER_RELEASE_CHANNEL_PATH"):
        raw = str(os.environ.get(env_name) or "").strip()
        if raw:
            return Path(raw)
    return DEFAULT_RELEASE_CHANNEL_PATH


def _parse_int_env(*names: str, default: int) -> int:
    for name in names:
        raw = str(os.environ.get(name) or "").strip()
        if not raw:
            continue
        try:
            value = int(raw)
        except ValueError:
            continue
        if value >= 0:
            return value
    return default


def _public_safe_base_url(base_url: str) -> str:
    candidate = base_url.strip()
    parsed = urlparse(candidate)
    hostname = (parsed.hostname or "").casefold()
    if hostname in {"127.0.0.1", "localhost", "::1"}:
        public_base_url = str(os.environ.get("CHUMMER_PUBLIC_BASE_URL") or "").strip()
        return public_base_url or "https://chummer.run"
    return candidate


def _parse_iso_timestamp(raw_value: str | None) -> dt.datetime | None:
    if not raw_value:
        return None
    normalized = raw_value.strip()
    if not normalized:
        return None
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    try:
        parsed = dt.datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def _payload_is_fresh(payload: dict, *, max_age_seconds: int, max_future_skew_seconds: int) -> bool:
    raw_generated_at = str(payload.get("generatedAt") or payload.get("generated_at") or "").strip() or None
    generated_at = _parse_iso_timestamp(raw_generated_at)
    if generated_at is None:
        return False

    age_seconds = int((dt.datetime.now(dt.timezone.utc) - generated_at).total_seconds())
    if age_seconds < 0:
        return abs(age_seconds) <= max_future_skew_seconds
    return age_seconds <= max_age_seconds


def _release_readiness_reason(value: str) -> str:
    text = value.strip()
    replacements = {
        "flagship product readiness proof did not publish a desktop-client reason.": (
            "flagship product readiness checks did not publish a desktop-client reason."
        ),
    }
    return replacements.get(text, text)


def _load_release_channel_snapshot() -> dict:
    release_channel_path = _release_channel_path()
    try:
        release_channel_label = release_channel_path.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        release_channel_label = str(release_channel_path)
    snapshot = {
        "status": "unavailable",
        "path": release_channel_label,
        "channelId": "",
        "channel": "",
        "version": "",
        "releaseVersion": "",
        "rolloutState": "",
        "supportabilityState": "",
        "publishedAt": "",
    }
    if not release_channel_path.is_file():
        return snapshot

    loaded = _load_existing_payload(release_channel_path)
    if loaded is None:
        snapshot["status"] = "invalid"
        return snapshot

    def strict_alias_value(*keys: str) -> str | None:
        present = [loaded[key] for key in keys if key in loaded]
        if any(not isinstance(value, str) for value in present):
            return None
        normalized = [value.strip() for value in present]
        if len(set(normalized)) > 1:
            return None
        return normalized[0] if normalized else ""

    channel = strict_alias_value("channelId", "channel")
    version = strict_alias_value("releaseVersion", "version")
    rollout_state = strict_alias_value("rolloutState", "rollout_state")
    supportability_state = strict_alias_value("supportabilityState", "supportability_state")
    published_at = (
        strict_alias_value("publishedAt")
        if "publishedAt" in loaded
        else strict_alias_value("generatedAt", "generated_at")
    )
    if None in (channel, version, rollout_state, supportability_state, published_at):
        snapshot["status"] = "invalid"
        return snapshot

    parsed_published_at: dt.datetime | None = None
    if published_at:
        normalized_published_at = published_at[:-1] + "+00:00" if published_at.endswith("Z") else published_at
        try:
            parsed_published_at = dt.datetime.fromisoformat(normalized_published_at)
        except ValueError:
            pass
    binding_is_complete = all(
        (channel, version, rollout_state, supportability_state, published_at)
    ) and parsed_published_at is not None and parsed_published_at.tzinfo is not None
    if not binding_is_complete:
        snapshot["status"] = "invalid"
        return snapshot

    snapshot.update(
        {
            "status": "available",
            "channelId": channel,
            "channel": channel,
            "version": version,
            "releaseVersion": version,
            "rolloutState": rollout_state,
            "supportabilityState": supportability_state,
            "publishedAt": published_at,
        }
    )
    return snapshot


def _published_installer_proof_routes() -> list[str]:
    loaded = _load_existing_payload(_release_channel_path())
    if not isinstance(loaded, dict):
        return [
            "/downloads/install/avalonia-linux-x64-installer",
            "/downloads/install/avalonia-osx-arm64-installer",
            "/downloads/install/avalonia-win-x64-installer",
        ]

    routes: list[str] = []
    for collection_name in ("artifacts", "downloads"):
        collection = loaded.get(collection_name)
        if not isinstance(collection, list):
            continue
        for item in collection:
            if not isinstance(item, dict):
                continue
            artifact_id = str(item.get("artifactId") or item.get("id") or "").strip()
            kind = str(item.get("kind") or "").strip().lower()
            if not artifact_id or kind != "installer":
                continue
            routes.append(f"/downloads/install/{artifact_id}")

    return sorted(_sorted_unique_strings(routes))


def _effective_readiness_override_reason(readiness_payload: dict, coverage_gap_keys: list[str]) -> str:
    if str(readiness_payload.get("status") or "").strip().lower() in {"pass", "passed", "ready"}:
        return ""
    gate_status_override = readiness_payload.get("gate_status_override")
    if not isinstance(gate_status_override, dict):
        return ""

    effective_reason = _release_readiness_reason(str(gate_status_override.get("effective_reason") or "").strip())
    if effective_reason:
        return effective_reason
    base_reason = _release_readiness_reason(str(gate_status_override.get("reason") or "").strip())
    blockers = _sorted_unique_strings(
        [
            str(item).strip()
            for item in gate_status_override.get("launch_critical_nested_blockers") or []
            if str(item).strip()
        ]
    )
    normalized_coverage_gap_keys = _sorted_unique_strings(coverage_gap_keys)
    scoped_coverage_gap_keys = _sorted_unique_strings(
        [
            str(item).strip()
            for item in gate_status_override.get("scoped_coverage_gap_keys") or []
            if str(item).strip()
        ]
    )
    details: list[str] = []
    if blockers:
        details.append("Launch blockers: " + ", ".join(blockers))
    if normalized_coverage_gap_keys:
        details.append("Coverage gaps: " + ", ".join(normalized_coverage_gap_keys))
    if scoped_coverage_gap_keys and scoped_coverage_gap_keys != normalized_coverage_gap_keys:
        details.append("Scoped coverage gaps: " + ", ".join(scoped_coverage_gap_keys))
    return _append_reason_details(base_reason, details)


def _load_flagship_readiness_snapshot() -> dict:
    readiness_path = _flagship_readiness_path()
    default_reason = "flagship product readiness checks did not publish a desktop-client reason."
    snapshot = {
        "status": "unknown",
        "scoped_status": "unknown",
        "generated_at": "",
        "missing_coverage_keys": [],
        "desktop_client_missing": False,
        "reason": default_reason,
        "completion_audit_status": "unknown",
        "completion_audit_reason": "",
        "source_path": str(readiness_path),
    }

    if not readiness_path.is_file():
        return snapshot

    readiness_payload = _load_flagship_readiness_payload(readiness_path)
    if readiness_payload is None:
        return snapshot

    coverage_gap_keys = readiness_payload.get("scoped_warning_keys")
    if not isinstance(coverage_gap_keys, list) or not coverage_gap_keys:
        coverage_gap_keys = readiness_payload.get("warning_keys")
    if not isinstance(coverage_gap_keys, list) or not coverage_gap_keys:
        coverage_gap_keys = readiness_payload.get("scoped_missing_keys")
    if not isinstance(coverage_gap_keys, list) or not coverage_gap_keys:
        coverage_gap_keys = readiness_payload.get("missing_keys")

    readiness_audit = readiness_payload.get("flagship_readiness_audit")
    if (not isinstance(coverage_gap_keys, list) or not coverage_gap_keys) and isinstance(readiness_audit, dict):
        coverage_gap_keys = readiness_audit.get("scoped_coverage_gap_keys")
        if not isinstance(coverage_gap_keys, list) or not coverage_gap_keys:
            coverage_gap_keys = readiness_audit.get("coverage_gap_keys")
        if not isinstance(coverage_gap_keys, list) or not coverage_gap_keys:
            coverage_gap_keys = readiness_audit.get("scoped_warning_coverage_keys")
        if not isinstance(coverage_gap_keys, list) or not coverage_gap_keys:
            coverage_gap_keys = readiness_audit.get("warning_coverage_keys")
        if not isinstance(coverage_gap_keys, list) or not coverage_gap_keys:
            coverage_gap_keys = readiness_audit.get("scoped_missing_coverage_keys")
        if not isinstance(coverage_gap_keys, list) or not coverage_gap_keys:
            coverage_gap_keys = readiness_audit.get("missing_coverage_keys")

    normalized_coverage_gap_keys = [
        str(item).strip()
        for item in coverage_gap_keys or []
        if str(item).strip()
    ]
    completion_audit = readiness_payload.get("completion_audit")
    raw_reason = _release_readiness_reason(
        str(readiness_audit.get("reason") or "").strip()
        if isinstance(readiness_audit, dict)
        else ""
    )
    raw_completion_audit_reason = _release_readiness_reason(
        str(completion_audit.get("reason") or "").strip()
        if isinstance(completion_audit, dict)
        else ""
    )
    effective_override_reason = _effective_readiness_override_reason(readiness_payload, normalized_coverage_gap_keys)
    reason = effective_override_reason or raw_reason or default_reason
    completion_audit_reason = effective_override_reason or raw_completion_audit_reason

    return {
        "status": str(readiness_payload.get("status") or "").strip() or "unknown",
        "scoped_status": str(readiness_payload.get("scoped_status") or "").strip() or "unknown",
        "generated_at": str(readiness_payload.get("generated_at") or "").strip(),
        "missing_coverage_keys": normalized_coverage_gap_keys,
        "desktop_client_missing": "desktop_client" in {item.casefold() for item in normalized_coverage_gap_keys},
        "reason": reason,
        "completion_audit_status": (
            str(completion_audit.get("status") or "").strip()
            if isinstance(completion_audit, dict)
            else "unknown"
        ),
        "completion_audit_reason": completion_audit_reason,
        "source_path": str(readiness_path),
    }


def _resolve_local_flagship_readiness_sync_path(*, out_path: Path) -> Path | None:
    explicit = str(os.environ.get("CHUMMER_LOCAL_FLAGSHIP_READINESS_SYNC_PATH") or "").strip()
    if explicit:
        return Path(explicit)

    if out_path.expanduser().resolve() == DEFAULT_HUB_LOCAL_RELEASE_PROOF_PATH.expanduser().resolve():
        return DEFAULT_FLAGSHIP_READINESS_PATH

    return None


def _sync_local_flagship_readiness_artifact_if_needed(*, out_path: Path, source_path: str) -> None:
    sync_path = _resolve_local_flagship_readiness_sync_path(out_path=out_path)
    if sync_path is None:
        return

    source = Path(source_path)
    if not source.is_file():
        return

    if source.expanduser().resolve() == sync_path.expanduser().resolve():
        return

    source_payload = _load_flagship_readiness_payload(source)
    if source_payload is None:
        return

    existing_payload = _load_existing_payload(sync_path)
    source_generated_at = _payload_generated_at(source_payload)
    existing_generated_at = _payload_generated_at(existing_payload)
    if (
        source_generated_at is not None
        and existing_generated_at is not None
        and source_generated_at < existing_generated_at
    ):
        print(
            "skipped local flagship readiness sync because source is older: "
            f"{sync_path} keeps {existing_generated_at.isoformat()} over {source_generated_at.isoformat()}"
        )
        return
    if existing_payload is not None and existing_payload == source_payload:
        return

    sync_path.parent.mkdir(parents=True, exist_ok=True)
    sync_path.write_text(json.dumps(source_payload, indent=2) + "\n", encoding="utf-8")
    print(f"synced local flagship readiness: {sync_path} <- {source}")


def _resolve_served_release_proof_sync_path(*, out_path: Path) -> Path | None:
    if out_path.expanduser().resolve() == DEFAULT_HUB_LOCAL_RELEASE_PROOF_PATH.expanduser().resolve():
        return DEFAULT_SERVED_HUB_LOCAL_RELEASE_PROOF_PATH
    return None


def _sync_served_release_proof_if_needed(*, out_path: Path) -> None:
    sync_path = _resolve_served_release_proof_sync_path(out_path=out_path)
    if sync_path is None or not out_path.is_file():
        return

    source_text = out_path.read_text(encoding="utf-8")
    if _write_public_json_artifact(sync_path, source_text):
        print(f"synced served hub local proof: {sync_path} <- {out_path}")


def _publish_runtime_proof_artifacts(
    *,
    out_path: Path,
    payload: dict,
    proof_max_age_seconds: int,
    proof_max_future_skew_seconds: int,
) -> bool:
    """Write the canonical and served proof under shared deploy mutation authority."""

    with _public_edge_proof_mutation_lock():
        existing_payload = _load_existing_payload(out_path)
        if (
            existing_payload is not None
            and _stable_payload(existing_payload) == _stable_payload(payload)
            and _payload_is_fresh(
                existing_payload,
                max_age_seconds=proof_max_age_seconds,
                max_future_skew_seconds=proof_max_future_skew_seconds,
            )
        ):
            _write_public_json_artifact(
                out_path,
                canonical_json_bytes(
                    existing_payload,
                    label="hub local release proof",
                ).decode("utf-8"),
            )
            _sync_served_release_proof_if_needed(out_path=out_path)
            return False

        generated_at = iso_now()
        payload["generated_at"] = generated_at
        payload["generatedAt"] = generated_at
        _write_public_json_artifact(
            out_path,
            canonical_json_bytes(
                payload,
                label="hub local release proof",
            ).decode("utf-8"),
        )
        _sync_served_release_proof_if_needed(out_path=out_path)
        return True


def _m141_direct_import_route_receipts() -> list[dict]:
    return [
        {
            "receipt_id": "menu:translator",
            "package_id": M141_UI_PACKAGE_ID,
            "milestone_id": 141,
            "frontier_id": M141_UI_FRONTIER_ID,
            "active_flagship_frontier_id": M141_UI_FLAGSHIP_FRONTIER_ID,
            "summary": "Direct screenshot-backed and runtime-backed proof for the Translator dialog route is current and cited by parity audit rows instead of family-level prose alone.",
            "routes": [
                "translator",
                "source:translator_route",
                "family:custom_data_xml_and_translator_bridge",
            ],
            "surfaces": [
                "menu:translator",
                "dialog.translator",
                "translatorLanePosture",
            ],
            "evidence": [
                "/docker/chummercomplete/chummer6-ui/.codex-studio/published/NEXT90_M141_UI_DIRECT_IMPORT_ROUTE_PROOF.generated.json keeps the direct translator route on current screenshot-backed and runtime-backed proof.",
                "/docker/chummercomplete/chummer6-ui/.codex-studio/published/CHUMMER5A_UI_ELEMENT_PARITY_AUDIT.generated.json cites menu:translator as direct backing for the custom-data XML and translator workflow family.",
            ],
        },
        {
            "receipt_id": "menu:xml_editor",
            "package_id": M141_UI_PACKAGE_ID,
            "milestone_id": 141,
            "frontier_id": M141_UI_FRONTIER_ID,
            "active_flagship_frontier_id": M141_UI_FLAGSHIP_FRONTIER_ID,
            "summary": "Direct screenshot-backed and runtime-backed proof for the XML amendment editor route is current and cited by parity audit rows instead of family-level prose alone.",
            "routes": [
                "xml_amendment_editor",
                "source:xml_amendment_editor_route",
                "family:custom_data_xml_and_translator_bridge",
            ],
            "surfaces": [
                "menu:xml_editor",
                "dialog.xml_editor",
                "xmlEditorLanePosture",
            ],
            "evidence": [
                "/docker/chummercomplete/chummer6-ui/.codex-studio/published/NEXT90_M141_UI_DIRECT_IMPORT_ROUTE_PROOF.generated.json keeps the XML amendment editor route on current screenshot-backed and runtime-backed proof.",
                "/docker/chummercomplete/chummer6-ui/.codex-studio/published/CHUMMER5A_UI_ELEMENT_PARITY_AUDIT.generated.json cites menu:xml_editor as direct backing for the custom-data XML and translator workflow family.",
            ],
        },
        {
            "receipt_id": "menu:hero_lab_importer",
            "package_id": M141_UI_PACKAGE_ID,
            "milestone_id": 141,
            "frontier_id": M141_UI_FRONTIER_ID,
            "active_flagship_frontier_id": M141_UI_FLAGSHIP_FRONTIER_ID,
            "summary": "Direct screenshot-backed and runtime-backed proof for the Hero Lab importer route is current and cited by parity audit rows instead of family-level prose alone.",
            "routes": [
                "hero_lab_importer",
                "source:hero_lab_importer_route",
                "family:legacy_and_adjacent_import_oracles",
            ],
            "surfaces": [
                "menu:hero_lab_importer",
                "dialog.hero_lab_importer",
                "heroLabImportOracleLanePosture",
            ],
            "evidence": [
                "/docker/chummercomplete/chummer6-ui/.codex-studio/published/NEXT90_M141_UI_DIRECT_IMPORT_ROUTE_PROOF.generated.json keeps the Hero Lab importer route on current screenshot-backed and runtime-backed proof.",
                "/docker/chummercomplete/chummer6-ui/.codex-studio/published/CHUMMER5A_UI_ELEMENT_PARITY_AUDIT.generated.json cites menu:hero_lab_importer as direct backing for the legacy and adjacent import-oracle workflow family.",
            ],
        },
        {
            "receipt_id": "workflow:import_oracle",
            "package_id": M141_UI_PACKAGE_ID,
            "milestone_id": 141,
            "frontier_id": M141_UI_FRONTIER_ID,
            "active_flagship_frontier_id": M141_UI_FLAGSHIP_FRONTIER_ID,
            "summary": "Direct screenshot-backed and runtime-backed proof for the adjacent import-oracle workflow is current and cited by parity audit rows instead of family-level prose alone.",
            "routes": [
                "import_oracle",
                "family:legacy_and_adjacent_import_oracles",
            ],
            "surfaces": [
                "workflow:import_oracle",
                "heroLabImportOracleLanePosture",
                "heroLabAdjacentSr6OracleReceipt",
            ],
            "evidence": [
                "/docker/chummercomplete/chummer6-ui/.codex-studio/published/NEXT90_M141_UI_DIRECT_IMPORT_ROUTE_PROOF.generated.json keeps the adjacent import-oracle workflow on current screenshot-backed and runtime-backed proof.",
                "/docker/chummercomplete/chummer6-ui/.codex-studio/published/CHUMMER5A_UI_ELEMENT_PARITY_AUDIT.generated.json cites workflow:import_oracle as direct backing for the legacy and adjacent import-oracle workflow family.",
            ],
        },
    ]


def main() -> int:
    if len(sys.argv) != 6:
        print(
            "usage: materialize_hub_local_release_proof.py <out_path> <base_url> <compose_file> <timeout_seconds> <skip_rebuild>",
            file=sys.stderr,
        )
        return 1

    out_path_text, base_url, compose_file, timeout_seconds, skip_rebuild = sys.argv[1:]
    out_path = Path(out_path_text)
    proof_max_age_seconds = _parse_int_env(
        "CHUMMER_VERIFY_RELEASE_PROOF_MAX_AGE_SECONDS",
        "CHUMMER_RELEASE_PROOF_MAX_AGE_SECONDS",
        default=86400,
    )
    proof_max_future_skew_seconds = _parse_int_env(
        "CHUMMER_VERIFY_RELEASE_PROOF_MAX_FUTURE_SKEW_SECONDS",
        "CHUMMER_RELEASE_PROOF_MAX_FUTURE_SKEW_SECONDS",
        default=300,
    )
    _sync_local_flagship_readiness_artifact_if_needed(
        out_path=out_path,
        source_path=str(_canonical_flagship_readiness_source_path()),
    )
    desktop_client_readiness = _load_flagship_readiness_snapshot()
    release_channel = _load_release_channel_snapshot()
    published_installer_proof_routes = _published_installer_proof_routes()
    additional_installer_proof_routes = [
        route
        for route in published_installer_proof_routes
        if route != "/downloads/install/avalonia-linux-x64-installer"
    ]

    successor_queue_packages = [
        {
            "package_id": "next90-m102-hub-desktop-native-trust",
            "milestone_id": 102,
            "frontier_id": M102_SUCCESSOR_FRONTIER_ID,
            "frontier_ids": M102_FRONTIER_IDS,
            "active_flagship_frontier_id": M102_ACTIVE_FLAGSHIP_FRONTIER_ID,
            "repo": "chummer6-hub",
            "status": "complete",
            "completion_action": "verify_closed_package_only",
            "do_not_reopen_reason": "M102 chummer6-hub desktop-native trust is complete; future shards must verify this receipt, registry row, queue row, and design-queue row instead of reopening the claim/install/update/rollback/support continuation package.",
            "landed_commit": "160af58f",
            "title": "Unify claim, install, update, and support recovery into one desktop-native flow",
            "allowed_paths": [
                "Chummer.Run.Api",
                "scripts",
                "tests",
            ],
            "owned_surfaces": [
                "desktop_native_claim_and_recovery",
                "support_followthrough:install_truth",
            ],
            "exit_criterion": "Claim, update, rollback, recovery, and support followthrough happen from the installer or app, not as browser ritual.",
        },
        {
            "package_id": "next90-m107-hub-artifact-factory",
            "milestone_id": 107,
            "frontier_id": 1421219975,
            "task": "Launch recipe-backed release, fix, support, and publication artifact jobs from approved source packs instead of one-off provider flows.",
            "repo": "chummer6-hub",
            "status": "complete",
            "wave": "W9",
            "completion_action": "verify_closed_package_only",
            "do_not_reopen_reason": "M107 chummer6-hub artifact factory orchestration is complete; future shards must verify this receipt, registry row, Fleet queue row, and design queue row instead of reopening the artifact-factory orchestration and public proof shelf release-bundles package.",
            "landed_commit": "b9e6b52e",
            "title": "Stand up artifact-factory orchestration for release, support, and publication bundles",
            "allowed_paths": [
                "Chummer.Run.Api",
                "scripts",
                "tests",
            ],
            "owned_surfaces": [
                "artifact_factory:orchestration",
                "public_proof_shelf:release_bundles",
            ],
            "exit_criterion": "Release, fix, support, and publication explainers can ship as approved video, audio, preview, and packet bundles from the same underlying release and support truth.",
        },
        {
            "package_id": M141_UI_PACKAGE_ID,
            "milestone_id": 141,
            "frontier_id": M141_UI_FRONTIER_ID,
            "frontier_ids": [M141_UI_FRONTIER_ID, M141_UI_FLAGSHIP_FRONTIER_ID],
            "active_flagship_frontier_id": M141_UI_FLAGSHIP_FRONTIER_ID,
            "repo": "chummer6-ui",
            "status": "complete",
            "completion_action": "verify_closed_package_only",
            "do_not_reopen_reason": "M141 chummer6-ui translator, XML amendment, and Hero Lab direct route proof is complete; future shards must verify the closed-package receipt, focused guard test, runtime-backed screenshot gates, canonical registry row, and queue mirrors instead of reopening this slice.",
            "title": "Capture direct screenshot and runtime proof for translator, XML amendment editor, Hero Lab importer, and adjacent import-oracle routes.",
            "allowed_paths": [
                "Chummer.Tests",
                "scripts",
                ".codex-studio",
            ],
            "owned_surfaces": [
                "menu:translator",
                "menu:xml_editor",
                "menu:hero_lab_importer",
                "workflow:import_oracle",
            ],
            "exit_criterion": "Translator, XML amendment editor, Hero Lab importer, and adjacent import-oracle routes stay grounded by direct screenshot-backed and runtime-backed proof instead of broad family prose.",
        },
        {
            "package_id": "next90-m143-hub-bind-exchange-and-outward-facing-output-routes-to-visible-receipt-or-bou",
            "milestone_id": 143,
            "frontier_id": 4032374688,
            "repo": "chummer6-hub",
            "status": "complete",
            "completion_action": "verify_closed_package_only",
            "do_not_reopen_reason": "M143 chummer6-hub outward-facing route receipts are complete; future shards must verify this receipt, registry row, queue row, and design-queue row instead of reopening the exchange and outward-facing output route contract.",
            "title": "Bind exchange and outward-facing output routes to visible receipt or bounded-failure posture instead of silent optimistic claims.",
            "allowed_paths": [
                "Chummer.Run.Api",
                "scripts",
                "tests",
            ],
            "owned_surfaces": [
                "bind_exchange_and_outward_facing_output_routes_to_visibl:hub",
            ],
            "exit_criterion": "Install recovery, release-bundle proof, creator-publication detail, and federation exchange routes surface a current receipt or bounded review posture instead of silent parity claims.",
        },
        {
            "package_id": "next90-m108-hub-campaign-briefing-bundles",
            "milestone_id": 108,
            "frontier_id": 1639715882,
            "repo": "chummer6-hub",
            "task": "Turn approved campaign primer and mission packs into locale-matched cold-open and briefing requests with audience-safe proof anchors.",
            "status": "complete",
            "wave": "W10",
            "completion_action": "verify_closed_package_only",
            "do_not_reopen_reason": "M108 chummer6-hub campaign briefing bundle composition is complete; future shards must verify the API orchestration service, launcher proof guard, focused tests, and queue/registry rows instead of reopening this package.",
            "landed_commit": "d0a84683",
            "title": "Compose campaign cold-open and mission-briefing bundles from approved packs",
            "allowed_paths": [
                "Chummer.Run.Api",
                "scripts",
                "tests",
            ],
            "owned_surfaces": [
                "campaign_cold_open_pack",
                "mission_briefing_reel",
            ],
            "exit_criterion": "Approved campaign primer and mission packs launch locale-matched cold-open and briefing artifact requests with audience-safe proof anchors and stable public shelf refs.",
        },
        {
            "package_id": "next90-m110-hub-runsite-orientation-requests",
            "milestone_id": 110,
            "frontier_id": 1545739925,
            "repo": "chummer6-hub",
            "task": "Compose governed runsite orientation requests from approved runsite packs, route summaries, and preview-safe pre-session truth.",
            "status": "complete",
            "wave": "W10",
            "completion_action": "verify_closed_package_only",
            "do_not_reopen_reason": "M110 chummer6-hub runsite orientation requests are complete; future shards must verify the governed composition route, generated proof receipts, and queue/registry rows instead of reopening this package.",
            "title": "Compose runsite orientation requests from approved runsite packs and route summaries",
            "allowed_paths": [
                "Chummer.Run.Api",
                "scripts",
                "tests",
            ],
            "owned_surfaces": [
                "runsite_orientation_requests",
                "route_summary:artifact_launch",
            ],
            "exit_criterion": "Compose governed runsite orientation requests from approved runsite packs, route summaries, and preview-safe pre-session truth.",
        },
        {
            "package_id": "next90-m105-hub-workspace-continuity",
            "milestone_id": 105,
            "frontier_id": 4623636482,
            "repo": "chummer6-hub",
            "status": "complete",
            "completion_action": "verify_closed_package_only",
            "do_not_reopen_reason": "M105 chummer6-hub workspace continuity is complete; future shards must verify the workspace restore receipt, registry row, queue row, and design-queue row instead of reopening the workspace restore and entitlement conflict receipt package.",
            "landed_commit": "4d4b3856",
            "title": "Emit provenance and conflict receipts for workspace restore and continuity",
            "allowed_paths": [
                "Chummer.Run.Api",
                "scripts",
                "tests",
            ],
            "owned_surfaces": [
                "workspace_restore:provenance",
                "entitlement_sync:conflict_receipts",
            ],
            "exit_criterion": "Claimed users can restore workspace, entitlement, last context, and safe continuation with explicit stale and conflict posture.",
        },
        {
            "package_id": "next90-m111-hub-support-concierge",
            "milestone_id": 111,
            "frontier_id": 2746902416,
            "repo": "chummer6-hub",
            "status": "complete",
            "completion_action": "verify_closed_package_only",
            "do_not_reopen_reason": "M111 chummer6-hub support concierge is complete; future shards must verify the authenticated concierge packet route, generated proof receipts, verifier, and queue/registry rows instead of reopening this package.",
            "landed_commit": "3fb14923",
            "title": "Emit install-aware release and support concierge packets from installed-build truth",
            "allowed_paths": [
                "Chummer.Run.Api",
                "scripts",
                "tests",
            ],
            "owned_surfaces": [
                "install_aware_support_concierge",
                "release_concierge:hub",
            ],
            "exit_criterion": "Compile support closure and release explainer packets from installed build, channel, and support-case truth.",
        },
        {
            "package_id": "next90-m112-hub-campaign-consequence-truth",
            "work_task_id": "112.1",
            "milestone_id": 112,
            "frontier_id": 4730880976,
            "repo": "chummer6-hub",
            "status": "complete",
            "wave": "W11",
            "completion_action": "verify_closed_package_only",
            "do_not_reopen_reason": "M112 chummer6-hub campaign consequence truth is complete; future shards must verify the governed campaign consequence proof, local release proof receipts, registry row, queue row, and design queue row instead of reopening this package.",
            "landed_commit": "f2b0b5a6",
            "title": "Promote campaign consequence state into governed campaign APIs",
            "task": "Land downtime, aftermath, heat, faction, contact, and reputation state with receipts and return-loop actions.",
            "allowed_paths": [
                "Chummer.Run.Api",
                "scripts",
                "tests",
            ],
            "owned_surfaces": [
                "campaign_memory:consequence_truth",
                "downtime_aftermath:api",
            ],
            "exit_criterion": "Land downtime, aftermath, heat, faction, contact, and reputation state with receipts and return-loop actions.",
        },
        {
            "package_id": "next90-m114-hub-rule-environment-receipts",
            "work_task_id": "114.3",
            "milestone_id": 114,
            "frontier_id": 4934642390,
            "repo": "chummer6-hub",
            "status": "complete",
            "wave": "W12",
            "completion_action": "verify_closed_package_only",
            "do_not_reopen_reason": "M114 chummer6-hub rule-environment receipts are complete; future shards must verify this package receipt, registry row, queue row, and design-queue row instead of reopening the campaign/support/install-aware receipt lane.",
            "task": "Keep campaign, support, and install-aware diagnostics tied to the same rule-environment receipts.",
            "title": "Keep campaign, support, and install-aware diagnostics tied to the same rule-environment receipts",
            "allowed_paths": [
                "Chummer.Run.Api",
                "scripts",
                "tests",
            ],
            "owned_surfaces": [
                "campaign_rule_environment_receipts",
                "support_rule_environment_receipts",
                "install_aware_support_receipts",
            ],
            "exit_criterion": "Keep campaign, support, and install-aware diagnostics tied to the same rule-environment receipts.",
        },
        {
            "package_id": "next90-m117-hub-artifact-shelf-v2",
            "work_task_id": "117.1",
            "milestone_id": 117,
            "frontier_id": 4041187890,
            "repo": "chummer6-hub",
            "status": "complete",
            "wave": "W13",
            "task": "Serve personal, campaign, creator, and public artifact shelves with proof, preview, captions, sibling packets, audience, locale, retention, and publication state.",
            "title": "Build artifact shelf APIs and audience filters",
            "landed_commit": "TO_BE_FILLED_M117_COMMIT",
            "completion_action": "verify_closed_package_only",
            "do_not_reopen_reason": "M117 chummer6-hub artifact shelf APIs and audience filters are complete; future shards must verify the artifact-shelf release-proof receipts, canonical registry row, Fleet queue row, and design queue row instead of reopening the signed-in and public artifact shelf slice.",
            "allowed_paths": [
                "Chummer.Run.Api",
                "scripts",
                "tests",
            ],
            "proof": [
                "/docker/chummercomplete/chummer6-hub/Chummer.Run.Api/Controllers/PublicLandingController.cs",
                "/docker/chummercomplete/chummer6-hub/Chummer.Run.Api/Services/Community/CampaignWorkspaceServerPlaneService.cs",
                "/docker/chummercomplete/chummer6-hub/Chummer.Run.Api/Services/Community/CampaignSpineService.cs",
                "/docker/chummercomplete/chummer6-hub/Chummer.Run.Api/Services/Community/PublicCreatorPublicationDiscoveryService.cs",
                "/docker/chummercomplete/chummer6-hub/Chummer.Run.Api/Services/Community/CreatorPublicationRegistryBridge.cs",
                "/docker/chummercomplete/chummer6-hub/Chummer.Run.Api/Views/PublicLanding/Shelf.cshtml",
                "/docker/chummercomplete/chummer6-hub/tests/RunServicesSmoke/Program.cs",
                "/docker/chummercomplete/chummer6-hub/scripts/materialize_hub_local_release_proof.py",
                "/docker/chummercomplete/chummer6-hub/scripts/verify_next90_m117_hub_artifact_shelf_v2.py",
                "/docker/chummercomplete/chummer6-hub/tests/test_next90_m117_hub_artifact_shelf_v2.py",
                "python3 scripts/verify_next90_m117_hub_artifact_shelf_v2.py",
                "python3 -m unittest tests/test_next90_m117_hub_artifact_shelf_v2.py",
                "bash scripts/ai/run_services_smoke.sh",
            ],
            "owned_surfaces": [
                "artifact_shelf:v2",
                "artifact_audience_filters",
            ],
            "exit_criterion": "Serve personal, campaign, creator, and public artifact shelves with proof, preview, captions, sibling packets, audience, locale, retention, and publication state.",
        },
        {
            "package_id": "next90-m118-hub-organizer-ops",
            "work_task_id": "118.1",
            "milestone_id": 118,
            "frontier_id": 3207603971,
            "repo": "chummer6-hub",
            "status": "complete",
            "wave": "W13",
            "task": "Add roles, rosters, events, permissions, artifact publication, and support escalation contracts for community-scale operations.",
            "title": "Land organizer, league, convention, and season contracts",
            "completion_action": "verify_closed_package_only",
            "do_not_reopen_reason": "M118 chummer6-hub organizer, league, convention, and season contracts are complete; future shards must verify the organizer operations release-proof receipts, canonical registry row, Fleet queue row, and design queue row instead of reopening this governed community-operations slice.",
            "allowed_paths": [
                "Chummer.Run.Api",
                "scripts",
                "tests",
            ],
            "owned_surfaces": [
                "organizer_ops",
                "league_convention_season_ops",
            ],
            "exit_criterion": "Add roles, rosters, events, permissions, artifact publication, and support escalation contracts for community-scale operations.",
        },
        {
            "package_id": "next90-m119-hub-first-session-onboarding",
            "work_task_id": "119.1",
            "milestone_id": 119,
            "frontier_id": 1130567614,
            "repo": "chummer6-hub",
            "status": "complete",
            "wave": "W14",
            "task": "Join install, claim, campaign primer, starter build, briefing, and support-safe recovery into a measured first-session path.",
            "title": "Orchestrate guided first-playable-session onboarding",
            "landed_commit": "TO_BE_FILLED_M119_COMMIT",
            "completion_action": "verify_closed_package_only",
            "do_not_reopen_reason": "M119 chummer6-hub guided first-playable-session onboarding is complete; future shards must verify the first-session records, local release package, canonical registry row, Fleet queue row, and design queue row instead of reopening the install-to-first-session onboarding slice.",
            "allowed_paths": [
                "Chummer.Run.Api",
                "scripts",
                "tests",
            ],
            "proof": [
                "/docker/chummercomplete/chummer6-hub/Chummer.Run.Api/Controllers/CampaignSpineController.cs",
                "/docker/chummercomplete/chummer6-hub/Chummer.Run.Api/Controllers/PublicLandingController.cs",
                "/docker/chummercomplete/chummer6-hub/Chummer.Run.Api/Services/Community/CampaignSpineService.cs",
                "/docker/chummercomplete/chummer6-hub/Chummer.Run.Api/Views/PublicLanding/Landing.cshtml",
                "/docker/chummercomplete/chummer6-hub/Chummer.Run.Api/Views/PublicLanding/Home.cshtml",
                "/docker/chummercomplete/chummer6-hub/Chummer.Run.Api/Views/Accounts/Account.cshtml",
                "/docker/chummercomplete/chummer6-hub/tests/RunServicesSmoke/Program.cs",
                "/docker/chummercomplete/chummer6-hub/scripts/materialize_hub_local_release_proof.py",
                "/docker/chummercomplete/chummer6-hub/scripts/verify_next90_m119_hub_first_session_onboarding.py",
                "/docker/chummercomplete/chummer6-hub/tests/test_next90_m119_hub_first_session_onboarding.py",
                "python3 scripts/verify_next90_m119_hub_first_session_onboarding.py",
                "python3 -m unittest tests/test_next90_m119_hub_first_session_onboarding.py",
                "bash scripts/ai/run_services_smoke.sh",
            ],
            "owned_surfaces": [
                "first_playable_session:onboarding",
                "starter_lane:hub",
            ],
            "exit_criterion": "Join install, claim, campaign primer, starter build, briefing, and support-safe recovery into a measured first-session path.",
        },
        {
            "package_id": "next90-m120-hub-public-launch-health",
            "work_task_id": "120.1",
            "milestone_id": 120,
            "frontier_id": 4442751895,
            "repo": "chummer6-hub",
            "status": "complete",
            "landed_commit": "TO_BE_FILLED_M120_COMMIT",
            "completion_action": "verify_closed_package_only",
            "do_not_reopen_reason": "M120 chummer6-hub public trust and launch-health publication package is complete; future shards must verify the launch-health contract, canonical registry row, queue parity, and local+served proof before reopening this package.",
            "wave": "W14",
            "task": "Compile live, preview, fallback, revoked, fixed, blocked, release checks, support pulse, and adoption health into public status surfaces.",
            "title": "Publish public trust, status, release, and proof-shelf surfaces from registry and governor truth.",
            "allowed_paths": [
                "Chummer.Run.Api",
                "scripts",
                "tests",
            ],
            "proof": [
                "/docker/chummercomplete/chummer6-hub/Chummer.Run.Api/Controllers/PublicLandingController.cs",
                "/docker/chummercomplete/chummer6-hub/Chummer.Run.Api/Controllers/PublicProgressController.cs",
                "/docker/chummercomplete/chummer6-hub/Chummer.Run.Api/ViewModels/SiteViewModels.cs",
                "/docker/chummercomplete/chummer6-hub/Chummer.Run.Api/Views/PublicLanding/Status.cshtml",
                "/docker/chummercomplete/chummer6-hub/tests/RunServicesSmoke/Program.cs",
                "/docker/chummercomplete/chummer6-hub/scripts/materialize_hub_local_release_proof.py",
                "/docker/chummercomplete/chummer6-hub/scripts/verify_next90_m120_hub_public_launch_health.py",
                "/docker/chummercomplete/chummer6-hub/tests/test_next90_m120_hub_public_launch_health.py",
                "python3 scripts/verify_next90_m120_hub_public_launch_health.py",
                "python3 -m unittest tests/test_next90_m120_hub_public_launch_health.py",
                "bash scripts/ai/verify.sh",
            ],
            "owned_surfaces": [
                "public_trust_surface:v3",
                "launch_health:public",
            ],
            "exit_criterion": "Compile live, preview, fallback, revoked, fixed, blocked, release checks, support pulse, and adoption health into public status surfaces.",
        },
        {
            "package_id": "next90-m141-hub-keep-route-support-and-publication-surfaces-from-claiming-parity-for-the",
            "work_task_id": "141.3",
            "milestone_id": 141,
            "frontier_id": 4062147200,
            "repo": "chummer6-hub",
            "status": "complete",
            "completion_action": "verify_closed_package_only",
            "do_not_reopen_reason": "M141 chummer6-hub import-route review-required guard is complete; future shards must verify the route/support/publication proof receipt, canonical registry row, queue mirrors, and local+served Hub proof instead of reopening this slice.",
            "wave": "W22P",
            "task": "Keep route, support, and publication surfaces from claiming parity for these routes unless the direct proof receipts are current.",
            "title": "Keep route, support, and publication surfaces from claiming parity for these routes unless the direct proof receipts are current.",
            "allowed_paths": [
                "Chummer.Run.Api",
                "scripts",
                "tests",
            ],
            "proof": [
                "/docker/chummercomplete/chummer6-hub/Chummer.Run.Api/Services/ImportRouteParityProofGuardService.cs",
                "/docker/chummercomplete/chummer6-hub/Chummer.Run.Api/Services/PublicReleaseManifestService.cs",
                "/docker/chummercomplete/chummer6-hub/Chummer.Run.Api/Services/PublicTrustPulseService.cs",
                "/docker/chummercomplete/chummer6-hub/Chummer.Run.Api/Services/SignedInTrustStatusService.cs",
                "/docker/chummercomplete/chummer6-hub/Chummer.Run.Api/Controllers/PublicLandingController.cs",
                "/docker/chummercomplete/chummer6-hub/Chummer.Run.Api/Controllers/DownloadsCompatibilityController.cs",
                "/docker/chummercomplete/chummer6-hub/Chummer.Run.Api/Controllers/CampaignSpineController.cs",
                "/docker/chummercomplete/chummer6-hub/Chummer.Run.Api/Views/PublicLanding/PublicCreatorPublication.cshtml",
                "/docker/chummercomplete/chummer6-hub/Chummer.Run.Api/Views/PublicLanding/Shelf.cshtml",
                "/docker/chummercomplete/chummer6-hub/scripts/materialize_hub_local_release_proof.py",
                "/docker/chummercomplete/chummer6-hub/scripts/verify_next90_m141_hub_import_route_review_required.py",
                "/docker/chummercomplete/chummer6-hub/tests/test_next90_m141_hub_import_route_review_required.py",
                "/docker/chummercomplete/chummer6-hub/tests/test_hub_local_release_proof_native_support_route.py",
                "/docker/chummercomplete/chummer6-hub/.codex-studio/published/HUB_LOCAL_RELEASE_PROOF.generated.json",
                "python3 scripts/verify_next90_m141_hub_import_route_review_required.py",
                "python3 -m unittest tests/test_next90_m141_hub_import_route_review_required.py",
                "python3 -m unittest tests/test_hub_local_release_proof_native_support_route.py",
                "bash scripts/ai/verify.sh",
            ],
            "owned_surfaces": [
                "keep_route_support_and_publication_surfaces_from_claimin:hub",
            ],
            "exit_criterion": "Keep route, support, and publication surfaces from claiming parity for these routes unless the direct proof receipts are current.",
        },
    ]

    payload = {
        "contract_name": "chummer6-hub.local_release_proof",
        "package_repo": "chummer6-hub",
        "status": "passed",
        "desktop_client_readiness": desktop_client_readiness,
        "release_channel": release_channel,
        "publicTrustSurface": {
            "summary": "This governor-visible trust surface bundle keeps status, current release, downloads, proof shelf, and public pulse routes aligned on the same outward-facing release truth.",
            "statusRoute": "/status",
            "currentReleaseRoute": "/now",
            "downloadsRoute": "/downloads",
            "proofShelfRoute": "/artifacts",
            "weeklyPulseRoute": "/api/public/weekly-pulse",
            "progressPosterRoute": "/api/public/progress-poster.svg",
            "launchHealthLabels": [
                "Live",
                "Preview",
                "Fallback",
                "Revoked",
                "Fixed",
                "Blocked",
                "Proof recency",
                "Support pulse",
                "Adoption health",
            ],
        },
        "successor_queue_package": {
            "package_id": "next90-m105-hub-workspace-continuity",
            "milestone_id": 105,
            "frontier_id": 4623636482,
            "repo": "chummer6-hub",
            "status": "complete",
            "completion_action": "verify_closed_package_only",
            "do_not_reopen_reason": "M105 chummer6-hub workspace continuity is complete; future shards must verify the workspace restore receipt, registry row, queue row, and design-queue row instead of reopening the workspace restore and entitlement conflict receipt package.",
            "landed_commit": "4d4b3856",
            "title": "Emit provenance and conflict receipts for workspace restore and continuity",
            "allowed_paths": [
                "Chummer.Run.Api",
                "scripts",
                "tests",
            ],
            "owned_surfaces": [
                "workspace_restore:provenance",
                "entitlement_sync:conflict_receipts",
            ],
            "exit_criterion": "Claimed users can restore workspace, entitlement, last context, and safe continuation with explicit stale and conflict posture.",
        },
        "successor_queue_packages": successor_queue_packages,
        "successor_queue_packages_by_id": {
            package["package_id"]: dict(package)
            for package in successor_queue_packages
        },
        "base_url": _public_safe_base_url(base_url),
        "compose_file": CANONICAL_COMPOSE_FILE,
        "playwright_timeout_seconds": CANONICAL_PLAYWRIGHT_TIMEOUT_SECONDS,
        "edge_rebuild_skipped": skip_rebuild.lower() in {"1", "true"},
        "journeys_passed": [
            "install_claim_restore_continue",
            "build_explain_publish",
            "campaign_session_recover_recap",
            "report_cluster_release_notify",
            "organize_community_and_close_loop",
        ],
        "proof_routes": _sorted_unique_strings([
            "/downloads/install/avalonia-linux-x64-installer",
            "/home/access",
            "/home/work",
            "/account/access",
            "/account/work",
            "/account/support",
            "/contact",
            "/downloads",
            *additional_installer_proof_routes,
        ]),
        "proof_receipts": [
            {
                "receipt_id": "desktop_native_claim_and_recovery",
                "package_id": "next90-m102-hub-desktop-native-trust",
                "milestone_id": 102,
                "frontier_id": M102_SUCCESSOR_FRONTIER_ID,
                "frontier_ids": M102_FRONTIER_IDS,
                "active_flagship_frontier_id": M102_ACTIVE_FLAGSHIP_FRONTIER_ID,
                "summary": "Claim and recovery continuation now have installer/app-native receipts: guided setup is the default, claim codes are recovery fallback only, and the claimed desktop app can call the grant-bound continuation endpoint without a browser redemption ritual.",
                "routes": [
                    "/downloads/install/avalonia-linux-x64-installer/continue.json",
                    "/api/v1/install-linking/continuation",
                    "/account/access",
                ],
                "surfaces": [
                    "desktop_native_claim_and_recovery",
                    "install_claim_restore_continue",
                    "claimed_install_continuation",
                ],
            },
            {
                "receipt_id": "support_followthrough:install_truth",
                "package_id": "next90-m102-hub-desktop-native-trust",
                "milestone_id": 102,
                "frontier_id": M102_SUCCESSOR_FRONTIER_ID,
                "frontier_ids": M102_FRONTIER_IDS,
                "active_flagship_frontier_id": M102_ACTIVE_FLAGSHIP_FRONTIER_ID,
                "summary": "Support stays with this install path, with installed build, current release, channel, head, platform, fallback, update, and rollback truth attached for the desktop client.",
                "routes": [
                    "/api/v1/install-linking/continuation",
                    "/api/v1/install-linking/continuation/support",
                    "/account/support",
                    "/contact",
                ],
                "surfaces": [
                    "support_followthrough:install_truth",
                    "support_case_install_readiness",
                    "desktop_update_rollback_recovery",
                ],
            },
            {
                "receipt_id": "desktop_client_readiness:bounded_routes",
                "package_id": "next90-m102-hub-desktop-native-trust",
                "milestone_id": 102,
                "frontier_id": M102_SUCCESSOR_FRONTIER_ID,
                "frontier_ids": M102_FRONTIER_IDS,
                "active_flagship_frontier_id": M102_ACTIVE_FLAGSHIP_FRONTIER_ID,
                "summary": "Download, status, publication, continuation, and support routes stay bounded to recovery and support posture until the direct desktop_client flagship proof turns green; the public route family must carry the current readiness gap instead of claiming parity early.",
                "routes": [
                    "/downloads",
                    "/status",
                    "/artifacts",
                    "/artifacts/publications/{publicationId}",
                    "/api/v1/install-linking/continuation",
                    "/api/v1/install-linking/continuation/support",
                ],
                "surfaces": [
                    "desktop_client_readiness:bounded_routes",
                    "desktop_native_claim_and_recovery",
                    "support_followthrough:install_truth",
                    "public_proof_shelf:release_bundles",
                ],
            },
            {
                "receipt_id": "fleet_and_operator_loop:desktop_native_trust",
                "package_id": "next90-m102-hub-desktop-native-trust",
                "milestone_id": 102,
                "frontier_id": M102_SUCCESSOR_FRONTIER_ID,
                "frontier_ids": M102_FRONTIER_IDS,
                "active_flagship_frontier_id": M102_ACTIVE_FLAGSHIP_FRONTIER_ID,
                "summary": "Hub publishes implementation-backed desktop-native trust receipts for the fleet/operator loop: claimed installs stay on grant-bound continuation, support follows installed-build truth, and proof refreshes come from verifier-owned scripts and tests rather than worker-state polling.",
                "routes": [
                    "/api/v1/install-linking/continuation",
                    "/api/v1/install-linking/continuation/support",
                    "/api/v1/install-linking/continuation/update",
                    "/api/v1/install-linking/continuation/rollback",
                ],
                "surfaces": [
                    "fleet_and_operator_loop",
                    "desktop_native_claim_and_recovery",
                    "support_followthrough:install_truth",
                ],
                "evidence": [
                    "/docker/chummercomplete/chummer6-hub/scripts/verify_desktop_native_trust_receipts.py verifies the M102 generated proof package, owned surfaces, grant-bound native routes, and forbidden operator-helper evidence markers.",
                    "/docker/chummercomplete/chummer6-hub/tests/test_desktop_native_trust_receipts.py fails closed when generated proof drops the fleet_and_operator_loop desktop-native trust receipt.",
                    "/docker/chummercomplete/chummer6-hub/tests/RunServicesVerification/InstallLinkingContinuationVerification.cs exercises continuation, support, update, rollback, recovery, callback, receipt-matching, and support-action sanitization on the claimed desktop rail.",
                ],
            },
            {
                "receipt_id": "public_proof_shelf:release_bundles",
                "package_id": "next90-m107-hub-artifact-factory",
                "milestone_id": 107,
                "frontier_id": 1421219975,
                "summary": "Approved release source packs now launch recipe-backed artifact jobs whose preview, caption, packet, audio, and video outputs bind onto stable public release-bundle shelf refs instead of one-off provider flows.",
                "routes": [
                    "/downloads/install/avalonia-linux-x64-installer",
                    "/artifacts/release-bundles/avalonia-linux-x64-installer",
                    "/artifacts/release-bundles/avalonia-linux-x64-installer/preview_card",
                    "/downloads/install/avalonia-win-x64-installer",
                    "/artifacts/release-bundles/avalonia-win-x64-installer",
                    "/artifacts/release-bundles/avalonia-win-x64-installer/preview_card",
                ],
                "surfaces": [
                    "artifact_factory:orchestration",
                    "public_proof_shelf:release_bundles",
                    "build_explain_publish",
                ],
            },
            {
                "receipt_id": "campaign_cold_open_pack",
                "package_id": "next90-m108-hub-campaign-briefing-bundles",
                "milestone_id": 108,
                "frontier_id": 1639715882,
                "summary": "Approved campaign primers now compose locale-matched cold-open artifact requests with audience-safe proof anchors and stable campaign proof shelf refs instead of ad hoc launch packets.",
                "routes": [
                    "/api/internal/artifact-factory/source-pack-batches",
                    "/api/internal/artifact-factory/recipes",
                    "/artifacts/campaigns/{campaignId}/cold-open",
                    "/artifacts/campaigns/{campaignId}/cold-open/preview_card",
                ],
                "surfaces": [
                    "campaign_cold_open_pack",
                    "campaign_onboarding",
                    "artifact_factory:campaign_cold_open",
                ],
                "evidence": [
                    "/docker/chummercomplete/chummer6-hub/Chummer.Run.Api/Services/ArtifactFactoryOrchestrationService.cs composes campaign_cold_open jobs from approved campaign primer packs with explicit audience and locale validation.",
                    "/docker/chummercomplete/chummer6-hub/scripts/launch_artifact_factory_source_pack_batch.py fail-closes campaign cold-open responses that omit audience/locale proof anchors or drift off the stable campaign cold-open shelf.",
                    "/docker/chummercomplete/chummer6-hub/tests/test_artifact_factory_source_pack_launcher.py covers locale-matched campaign cold-open launches and fail-closed proof-anchor drift.",
                ],
            },
            {
                "receipt_id": "mission_briefing_reel",
                "package_id": "next90-m108-hub-campaign-briefing-bundles",
                "milestone_id": 108,
                "frontier_id": 1639715882,
                "summary": "Approved mission packs now compose locale-matched briefing artifact requests with audience-safe proof anchors and stable mission briefing shelf refs before media-factory launch.",
                "routes": [
                    "/api/internal/artifact-factory/source-pack-batches",
                    "/api/internal/artifact-factory/recipes",
                    "/artifacts/missions/{missionId}/briefing",
                    "/artifacts/missions/{missionId}/briefing/preview_card",
                ],
                "surfaces": [
                    "mission_briefing_reel",
                    "campaign_onboarding",
                    "artifact_factory:mission_briefing",
                ],
                "evidence": [
                    "/docker/chummercomplete/chummer6-hub/Chummer.Run.Api/Services/ArtifactFactoryOrchestrationService.cs composes mission_briefing jobs from approved mission packs with explicit audience and locale validation.",
                    "/docker/chummercomplete/chummer6-hub/scripts/launch_artifact_factory_source_pack_batch.py fail-closes mission briefing responses that omit audience/locale proof anchors or drift off the stable mission briefing shelf.",
                    "/docker/chummercomplete/chummer6-hub/tests/test_artifact_factory_source_pack_launcher.py covers locale-matched mission briefing launches and fail-closed proof-anchor drift.",
                ],
            },
            {
                "receipt_id": "runsite_orientation_requests",
                "package_id": "next90-m110-hub-runsite-orientation-requests",
                "milestone_id": 110,
                "frontier_id": 1545739925,
                "summary": "Approved runsite packs now compose governed host clips, tour siblings, audio companions, and preview-safe pre-session truth through one internal runsite orientation request contract before downstream media launch.",
                "routes": [
                    "/api/internal/runsite-orientation/requests",
                    "/artifacts/routes/{routeSummaryId}/{routeSegmentId}",
                ],
                "surfaces": [
                    "runsite_orientation_requests",
                    "runsite_orientation_bundle",
                    "preview_safe_truth:pre_session",
                ],
                "evidence": [
                    "/docker/chummercomplete/chummer6-hub/Chummer.Run.Api/Services/RunsiteOrientationRequestComposerService.cs composes governed runsite orientation bundles from approved packs, route summaries, and preview-safe inspectable truth refs.",
                    "/docker/chummercomplete/chummer6-hub/Chummer.Run.Api/Controllers/InternalRunsiteOrientationController.cs exposes the bounded internal request route and rejects unauthorized or malformed orientation requests.",
                    "/docker/chummercomplete/chummer6-hub/tests/test_runsite_orientation_requests.py covers composed bundle output, preview-safe evidence anchors, duplicate-deduplication rejection, and queue/registry proof drift.",
                ],
            },
            {
                "receipt_id": "route_summary:artifact_launch",
                "package_id": "next90-m110-hub-runsite-orientation-requests",
                "milestone_id": 110,
                "frontier_id": 1545739925,
                "summary": "Route summaries remain the only authority for runsite route previews: route preview artifacts stay inspectable, preview-safe, and route-summary governed even when approved packs provide the rest of the orientation bundle.",
                "routes": [
                    "/api/internal/runsite-orientation/requests",
                    "/artifacts/routes/{routeSummaryId}/{routeSegmentId}",
                ],
                "surfaces": [
                    "route_summary:artifact_launch",
                    "route_preview:inspectable_truth",
                    "runsite_orientation_bundle",
                ],
                "evidence": [
                    "/docker/chummercomplete/chummer6-hub/Chummer.Run.Api/Services/RunsiteOrientationRequestComposerService.cs rejects pack-owned route preview templates and forces route-summary route preview categories to remain inspectable and preview-safe.",
                    "/docker/chummercomplete/chummer6-hub/Chummer.Tests/RunsiteOrientationRequestComposerServiceTests.cs proves route previews stay route-summary governed and that internal authorization still gates the composition route.",
                    "/docker/chummercomplete/chummer6-hub/scripts/verify_runsite_orientation_requests.py fail-closes missing route_summary:artifact_launch proof, weakened closure metadata, or worker-unsafe queue and registry evidence.",
                ],
            },
            {
                "receipt_id": "workspace_restore:provenance",
                "package_id": "next90-m105-hub-workspace-continuity",
                "milestone_id": 105,
                "frontier_id": 4623636482,
                "summary": "Workspace restore continuity emits provenance receipts and typed recovery actions for claimed installs, recent artifacts, rule environments, and restore inventory on the shared account workspace surfaces.",
                "routes": [
                    "/home/work",
                    "/account/roster",
                    "/account/access",
                ],
                "surfaces": [
                    "workspace_restore:provenance",
                    "workspace_restore:recoverable_actions",
                    "workspace_restore",
                    "account_workspace_detail",
                ],
            },
            {
                "receipt_id": "entitlement_sync:conflict_receipts",
                "package_id": "next90-m105-hub-workspace-continuity",
                "milestone_id": 105,
                "frontier_id": 4623636482,
                "summary": "Entitlement drift, stale claims, missing grants, and continue-blocking conflicts emit recoverable receipts and typed account-access actions on the same restore lane instead of falling back to support folklore.",
                "routes": [
                    "/home/work",
                    "/account/roster",
                    "/account/access",
                    "/downloads",
                ],
                "surfaces": [
                    "entitlement_sync:conflict_receipts",
                    "entitlement_sync:recoverable_actions",
                    "entitlement_sync",
                    "workspace_restore",
                ],
            },
            {
                "receipt_id": "install_aware_support_concierge",
                "package_id": "next90-m111-hub-support-concierge",
                "milestone_id": 111,
                "frontier_id": 2746902416,
                "summary": "Hub now compiles authenticated support closure packets from support-case truth, installed build, release channel, claimed install context, and installed-build receipt ids instead of queued support status alone.",
                "routes": [
                    "/api/v1/support/cases/{caseId}/concierge",
                    "/api/v1/install-linking/continuation/support",
                    "/account/support",
                    "/account/access",
                ],
                "surfaces": [
                    "install_aware_support_concierge",
                    "support_case_install_readiness",
                    "support_closure_packets",
                ],
            },
            {
                "receipt_id": "release_concierge:hub",
                "package_id": "next90-m111-hub-support-concierge",
                "milestone_id": 111,
                "frontier_id": 2746902416,
                "summary": "Hub release concierge packets explain why the current or fixed release is correct for the reporter's installed build and channel, while public wrappers stay bounded to first-party support and download routes.",
                "routes": [
                    "/api/v1/support/cases/{caseId}/concierge",
                    "/now",
                    "/status",
                    "/help",
                    "/downloads",
                    "/downloads/install/{artifactId}",
                    "/api/v1/install-linking/continuation",
                ],
                "surfaces": [
                    "release_concierge:hub",
                    "release_explainer_packets",
                    "public_concierge_trust_wrapper",
                ],
            },
            {
                "receipt_id": "campaign_memory:consequence_truth",
                "package_id": "next90-m112-hub-campaign-consequence-truth",
                "milestone_id": 112,
                "frontier_id": 4730880976,
                "summary": "Campaign memory and governed consequence truth now stay on one bounded return-loop lane so heat, faction, contact, reputation, downtime, and aftermath posture remain inspectable on the signed-in work surface.",
                "routes": [
                    "/api/v1/campaign-spine/me/workspaces/{workspaceId}/campaign-memory",
                    "/api/v1/campaign-spine/me/workspaces/{workspaceId}/consequence-truth",
                    "/account/work#campaign-consequences",
                ],
                "surfaces": [
                    "campaign_memory:consequence_truth",
                    "campaign_consequence_truth",
                    "campaign_return_loop",
                ],
            },
            {
                "receipt_id": "downtime_aftermath:api",
                "package_id": "next90-m112-hub-campaign-consequence-truth",
                "milestone_id": 112,
                "frontier_id": 4730880976,
                "summary": "Downtime and aftermath state now ship with governed package receipts, explicit return-loop actions, and one aftermath rail instead of recap prose alone.",
                "routes": [
                    "/api/v1/campaign-spine/me/workspaces/{workspaceId}/aftermath-recap-packages",
                    "/api/v1/campaign-spine/me/workspaces/{workspaceId}/downtime-aftermath",
                    "/account/work#aftermath-packages",
                ],
                "surfaces": [
                    "downtime_aftermath:api",
                    "governed_aftermath_package",
                    "return_loop_action",
                ],
            },
            {
                "receipt_id": "campaign_rule_environment_receipts",
                "package_id": "next90-m114-hub-rule-environment-receipts",
                "milestone_id": 114,
                "frontier_id": 4934642390,
                "summary": "Campaign rules answers, workspace readiness cues, and rule-environment studio lifecycle all keep the same explain-entry receipts visible on signed-in campaign surfaces instead of splitting campaign truth into separate support-only interpretations.",
                "routes": [
                    "/home",
                    "/account/roster",
                    "/api/v1/campaign-spine/me",
                    "/api/v1/campaign-spine/me/rules/{entryId}",
                ],
                "surfaces": [
                    "campaign_rule_environment_receipts",
                    "rules_navigator",
                    "rule_environment_studio:hub",
                ],
                "evidence": [
                    "/docker/chummercomplete/chummer6-hub/Chummer.Run.Api/Services/Community/CampaignSpineService.cs projects rules navigator answers with stable ExplainEntryId values, before/after diffs, and rule-environment studio lifecycle posture on the signed-in campaign rail.",
                    "/docker/chummercomplete/chummer6-hub/tests/RunServicesSmoke/Program.cs proves signed-in account and home surfaces keep grounded rules navigator answers and studio stages visible.",
                    "/docker/chummercomplete/chummer6-hub/scripts/verify_next90_m114_hub_rule_environment_receipts.py fail-closes queue, registry, and proof drift if campaign rule-environment receipts stop sharing the same explain-entry ids with support diagnostics.",
                ],
            },
            {
                "receipt_id": "support_rule_environment_receipts",
                "package_id": "next90-m114-hub-rule-environment-receipts",
                "milestone_id": 114,
                "frontier_id": 4934642390,
                "summary": "Signed-in support assistant answers now carry the same rule-environment explain-entry receipts that campaign surfaces expose, so support questions about visibility, permissions, and campaign return posture cite campaign-owned rules truth instead of parallel help copy.",
                "routes": [
                    "/api/v1/support/cases/assistant",
                    "/home",
                    "/api/v1/campaign-spine/me/rules/{entryId}",
                ],
                "surfaces": [
                    "support_rule_environment_receipts",
                    "support_assistant",
                    "rules_truth",
                ],
                "evidence": [
                    "/docker/chummercomplete/chummer6-hub/Chummer.Run.Api/Services/Support/SupportAssistantService.cs forwards RulesNavigator ExplainEntryId values into support citations for grounded rules questions.",
                    "/docker/chummercomplete/chummer6-hub/Chummer.Control.Contracts/SupportContracts.cs preserves optional citation receipt ids so support routes can name the same explain receipts without inventing a second contract.",
                    "/docker/chummercomplete/chummer6-hub/tests/RunServicesSmoke/Program.cs proves rules-truth assistant answers expose the same explain receipt ids surfaced by campaign rules navigator entries.",
                ],
            },
            {
                "receipt_id": "install_aware_support_receipts",
                "package_id": "next90-m114-hub-rule-environment-receipts",
                "milestone_id": 114,
                "frontier_id": 4934642390,
                "summary": "Install-aware support diagnostics keep installation-scoped support questions on the same receipt-backed rule-environment lane, so signed-in assistant answers can pivot from a linked install back to the grounded campaign or build explain receipt instead of drifting into install-only folklore.",
                "routes": [
                    "/api/v1/support/cases/assistant",
                    "/account/access",
                    "/account/roster",
                    "/home",
                ],
                "surfaces": [
                    "install_aware_support_receipts",
                    "support_assistant",
                    "install_aware_diagnostics",
                ],
                "evidence": [
                    "/docker/chummercomplete/chummer6-hub/Chummer.Run.Api/Services/Support/SupportAssistantService.cs keeps installation-aware rules and build questions tied to open_home and open_work actions while carrying shared explain-entry receipt ids.",
                    "/docker/chummercomplete/chummer6-hub/tests/RunServicesSmoke/Program.cs proves install-aware rules and build assistant requests route back to the signed-in home and work surfaces instead of a detached diagnostic lane.",
                    "/docker/chummercomplete/chummer6-hub/scripts/verify_next90_m114_hub_rule_environment_receipts.py rejects release-proof drift when install-aware support receipts stop naming the shared rule-environment support lane.",
                ],
            },
            {
                "receipt_id": "artifact_shelf:v2",
                "package_id": "next90-m117-hub-artifact-shelf-v2",
                "milestone_id": 117,
                "frontier_id": 4041187890,
                "summary": "Hub now serves one governed artifact shelf lane for signed-in personal, campaign, creator, and public views, keeping recap lineage, publication state, trust posture, and public publication detail on the same inspectable surface instead of splitting them into unrelated routes.",
                "routes": [
                    "/artifacts",
                    "/api/v1/public/artifacts/shelf",
                    "/artifacts/publications/{publicationId}",
                    "/api/v1/public/artifacts/publications/{publicationId}",
                    "/home/work",
                    "/account/roster",
                ],
                "surfaces": [
                    "artifact_shelf:v2",
                    "artifact_shelf_api",
                    "signed_in_return_shelf",
                    "public_creator_discovery",
                    "creator_publication_detail",
                ],
                "evidence": [
                    "/docker/chummercomplete/chummer6-hub/Chummer.Run.Api/Controllers/PublicLandingController.cs serves the governed artifact shelf, public shelf APIs, public creator publication detail route, and signed-in overlay projections from one bounded controller path.",
                    "/docker/chummercomplete/chummer6-hub/Chummer.Run.Api/Services/Community/PublicCreatorPublicationDiscoveryService.cs keeps public creator discovery published-only and manifest-authority-backed before the shared shelf surfaces it.",
                    "/docker/chummercomplete/chummer6-hub/Chummer.Run.Api/Views/PublicLanding/Shelf.cshtml renders signed-in return shelf entries and public creator discovery with audience, publication, trust, discovery, lineage, moderation, and next-step posture kept together.",
                    "/docker/chummercomplete/chummer6-hub/tests/RunServicesSmoke/Program.cs proves personal, campaign, creator, and public artifact views plus the mirrored shelf APIs keep proof, preview, caption, sibling-packet, locale, retention, and publication-state truth visible on the shared shelf.",
                ],
            },
            {
                "receipt_id": "artifact_audience_filters",
                "package_id": "next90-m117-hub-artifact-shelf-v2",
                "milestone_id": 117,
                "frontier_id": 4041187890,
                "summary": "Signed-in artifact shelf filters now fail closed to all, personal, campaign, creator, or public while workspace and campaign projections stamp recap entries with audience and publication posture before the public shelf renders them.",
                "routes": [
                    "/artifacts",
                    "/home/work",
                    "/account/roster",
                ],
                "surfaces": [
                    "artifact_audience_filters",
                    "artifact_view:all",
                    "artifact_view:personal",
                    "artifact_view:campaign",
                    "artifact_view:creator",
                    "artifact_view:public",
                ],
                "evidence": [
                    "/docker/chummercomplete/chummer6-hub/Chummer.Run.Api/Controllers/PublicLandingController.cs normalizes the signed-in view query, filters recap and creator-publication overlays, and falls unknown filters back to the all-views shelf.",
                    "/docker/chummercomplete/chummer6-hub/Chummer.Run.Api/Services/Community/CampaignWorkspaceServerPlaneService.cs and CampaignSpineService.cs stamp creator-linked recap entries with campaign, personal, and creator audience plus publication state before the shelf view filters them.",
                    "/docker/chummercomplete/chummer6-hub/Chummer.Run.Api/Services/Community/CreatorPublicationRegistryBridge.cs requires approved manifest-backed audit authority before creator-publication moderation and publication can widen onto the public shelf.",
                    "/docker/chummercomplete/chummer6-hub/scripts/verify_next90_m117_hub_artifact_shelf_v2.py fail-closes queue, registry, and source-proof drift if artifact shelf audience filtering or signed-in view controls regress.",
                ],
            },
            {
                "receipt_id": "organizer_ops",
                "package_id": "next90-m118-hub-organizer-ops",
                "milestone_id": 118,
                "frontier_id": 3207603971,
                "summary": "Hub now keeps governed organizer operations, roles, roster movement, and signed-in account rail follow-through on one bounded organizer dashboard instead of scattering them across ad hoc operator screens.",
                "routes": [
                    "/api/v1/campaign-spine/me/organizer-ops",
                    "/home/work",
                    "/account/roster",
                ],
                "surfaces": [
                    "organizer_ops",
                    "organizer_roles",
                    "organizer_permissions",
                    "organizer_roster_contracts",
                ],
                "evidence": [
                    "/docker/chummercomplete/chummer6-hub/Chummer.Run.Api/Controllers/CampaignSpineController.cs now serves the organizer operations dashboard from the shared campaign-spine route instead of a detached operator-only endpoint.",
                    "/docker/chummercomplete/chummer6-hub/Chummer.Run.Api/Services/Community/CampaignSpineService.cs now composes organizer roles, permissions, and roster movement from one governed campaign/community projection.",
                    "/docker/chummercomplete/chummer6-hub/tests/RunServicesSmoke/Program.cs proves organizer role assignments, permissions, and governed roster movement survive the shared organizer operations contract and signed-in rails.",
                ],
            },
            {
                "receipt_id": "league_convention_season_ops",
                "package_id": "next90-m118-hub-organizer-ops",
                "milestone_id": 118,
                "frontier_id": 3207603971,
                "summary": "The same governed operations lane now keeps season lanes, artifact publication posture, and support escalation visible together so organizer workflows stay auditable instead of fragmenting across separate admin-only dashboards.",
                "routes": [
                    "/api/v1/campaign-spine/me/organizer-ops",
                    "/home/work",
                    "/account/roster",
                ],
                "surfaces": [
                    "league_convention_season_ops",
                    "season_event_lanes",
                    "artifact_publication:organizer",
                    "support_escalation:organizer",
                ],
                "evidence": [
                    "/docker/chummercomplete/chummer6-hub/Chummer.Run.Api/Services/Community/CampaignSpineService.cs now keeps season lanes, artifact publication posture, and tracked support escalation on the same organizer dashboard instead of splitting them into separate operator notes.",
                    "/docker/chummercomplete/chummer6-hub/Chummer.Run.Api/Views/Accounts/Account.cshtml and /docker/chummercomplete/chummer6-hub/Chummer.Run.Api/Views/PublicLanding/Home.cshtml surface organizer artifact-publication and support-escalation posture on the shared operator rails.",
                    "/docker/chummercomplete/chummer6-hub/tests/RunServicesSmoke/Program.cs proves governed season lanes, artifact publication receipts, and tracked support escalation survive the organizer contract across the same governed operations lane.",
                ],
            },
            {
                "receipt_id": "public_trust_surface:v3",
                "package_id": "next90-m120-hub-public-launch-health",
                "milestone_id": 120,
                "frontier_id": 4442751895,
                "summary": "Public trust now keeps status, current release, downloads, proof shelf, weekly pulse, and the hosted progress poster on one governor-backed public route family instead of splitting launch posture across unrelated pages.",
                "routes": [
                    "/status",
                    "/now",
                    "/downloads",
                    "/artifacts",
                    "/api/public/weekly-pulse",
                    "/api/public/progress-poster.svg",
                ],
                "surfaces": [
                    "public_trust_surface:v3",
                    "weekly_trust_pulse",
                    "proof_shelf_projection",
                    "status_release_guidance",
                ],
                "evidence": [
                    "/docker/chummercomplete/chummer6-hub/Chummer.Run.Api/Controllers/PublicLandingController.cs binds the shared trust pulse and launch-health model onto the hosted status, release, downloads, and proof-shelf surfaces.",
                    "/docker/chummercomplete/chummer6-hub/Chummer.Run.Api/Controllers/PublicProgressController.cs serves the hosted weekly pulse and progress-poster routes from the same public-trust surface contract.",
                    "/docker/chummercomplete/chummer6-hub/Chummer.Run.Api/Views/PublicLanding/Status.cshtml renders the public launch-health card and trust-surface projection instead of leaving governor-backed public posture implicit.",
                    "/docker/chummercomplete/chummer6-hub/tests/RunServicesSmoke/Program.cs proves the status page surfaces the trust pulse, proof shelf guidance, and hosted public launch-health packet on one route family.",
                ],
            },
            {
                "receipt_id": "launch_health:public",
                "package_id": "next90-m120-hub-public-launch-health",
                "milestone_id": 120,
                "frontier_id": 4442751895,
                "summary": "Public launch health now compiles live, preview, fallback, revoked, fixed, blocked, release checks, support pulse, and adoption health from mirrored release and weekly release truth instead of leaving the public status lane to infer them.",
                "routes": [
                    "/status",
                    "/api/public/weekly-pulse",
                    "/api/public/progress-poster.svg",
                ],
                "surfaces": [
                    "launch_health:public",
                    "launch_health_rows",
                    "support_pulse:public",
                    "adoption_health:public",
                ],
                "evidence": [
                    "/docker/chummercomplete/chummer6-hub/Chummer.Run.Api/Controllers/PublicLandingController.cs builds explicit launch-health rows from the public release and release truth.",
                    "/docker/chummercomplete/chummer6-hub/Chummer.Run.Api/ViewModels/SiteViewModels.cs keeps launch-health rows as an explicit status-page projection instead of free-form copy.",
                    "/docker/chummercomplete/chummer6-hub/Chummer.Run.Api/Views/PublicLanding/Status.cshtml renders Model.LaunchHealthRows on the public status lane.",
                    "/docker/chummercomplete/chummer6-hub/tests/RunServicesSmoke/Program.cs fail-closes the status route if the public launch-health rows stop surfacing the mirrored release and weekly release truth.",
                ],
            },
            {
                "receipt_id": "first_playable_session:onboarding",
                "package_id": "next90-m119-hub-first-session-onboarding",
                "milestone_id": 119,
                "frontier_id": 1130567614,
                "summary": "Hub now keeps signed-in install return, first-session workspace seeding, campaign-primer-backed first-session detail, and support-safe recovery in one first-session onboarding path instead of a separate onboarding ritual.",
                "routes": [
                    "/home",
                    "/home/work",
                    "/account/work",
                    "/account/roster",
                    "/api/v1/campaign-spine/me",
                    "/api/v1/campaign-spine/me/workspaces/starter",
                ],
                "surfaces": [
                    "first_playable_session:onboarding",
                    "campaign_onboarding",
                    "install_claim_restore_continue",
                ],
                "evidence": [
                    "/docker/chummercomplete/chummer6-hub/Chummer.Run.Api/Controllers/CampaignSpineController.cs exposes the starter-workspace seeding route so the signed-in first-session path reuses campaign data instead of inventing a second onboarding API.",
                    "/docker/chummercomplete/chummer6-hub/Chummer.Run.Api/Services/Community/CampaignSpineService.cs projects first-playable-session summaries, legal-runner detail, understandable-return detail, and primer-safe publication titles on the same campaign return path.",
                    "/docker/chummercomplete/chummer6-hub/tests/RunServicesSmoke/Program.cs checks landing, home, account, and starter-workspace API surfaces keep the first-session path on the shared campaign projection.",
                ],
            },
            {
                "receipt_id": "starter_lane:hub",
                "package_id": "next90-m119-hub-first-session-onboarding",
                "milestone_id": 119,
                "frontier_id": 1130567614,
                "summary": "The hub-owned first-session path gives signed-in users one calmer route from linked install into first-session detail, build next steps, campaign-primer return, and install support without hiding the next safe action behind deeper admin-only pages.",
                "routes": [
                    "/home/work",
                    "/account/work",
                    "/account/roster",
                    "/account/access",
                    "/contact",
                ],
                "surfaces": [
                    "starter_lane:hub",
                    "first_session:proof_drawer",
                    "starter_build:follow_through",
                ],
                "evidence": [
                    "/docker/chummercomplete/chummer6-hub/Chummer.Run.Api/Views/PublicLanding/Home.cshtml wires first-session workspace seeding to the campaign-spine starter endpoint and keeps first-session detail, build-path next steps, and claimed-device return on the signed-in Home view.",
                    "/docker/chummercomplete/chummer6-hub/Chummer.Run.Api/Views/Accounts/Account.cshtml keeps the selected first-session drawer, legal-runner and return detail, and install support on the shared account work route.",
                    "/docker/chummercomplete/chummer6-hub/Chummer.Run.Api/Controllers/PublicLandingController.cs promotes first-session work as the primary signed-in action when a linked install exists but shared campaign work has not been seeded yet.",
                ],
            },
            *_m141_direct_import_route_receipts(),
            {
                "receipt_id": "keep_route_support_and_publication_surfaces_from_claimin:hub",
                "package_id": "next90-m141-hub-keep-route-support-and-publication-surfaces-from-claiming-parity-for-the",
                "milestone_id": 141,
                "frontier_id": 4062147200,
                "summary": "Route, support, and publication surfaces now keep parity claims review-required until the direct translator, XML amendment, Hero Lab, and adjacent import-route receipts are current, so downloads, status, support, and publication detail routes stay honest about the remaining review-required lane.",
                "routes": [
                    "/downloads",
                    "/status",
                    "/contact",
                    "/account/support",
                    "/artifacts",
                    "/artifacts/publications/{publicationId}",
                    "/api/v1/public/artifacts/publications/{publicationId}",
                ],
                "surfaces": [
                    "keep_route_support_and_publication_surfaces_from_claimin:hub",
                    "public_trust_surface:v3",
                    "support_followthrough:install_truth",
                    "artifact_shelf:v2",
                ],
                "evidence": [
                    "/docker/chummercomplete/chummer6-hub/Chummer.Run.Api/Services/ImportRouteParityProofGuardService.cs requires current local release-proof receipts before translator, XML amendment, Hero Lab, and adjacent import routes can clear the review-required lane.",
                    "/docker/chummercomplete/chummer6-hub/Chummer.Run.Api/Services/PublicReleaseManifestService.cs, PublicTrustPulseService.cs, and SignedInTrustStatusService.cs carry the review-required parity guard onto public release, support, and signed-in trust surfaces.",
                    "/docker/chummercomplete/chummer6-hub/Chummer.Run.Api/Controllers/PublicLandingController.cs, DownloadsCompatibilityController.cs, CampaignSpineController.cs apply the same review-required lane to downloads, status, support, and publication routes.",
                    "/docker/chummercomplete/chummer6-hub/scripts/verify_next90_m141_hub_import_route_review_required.py and tests/test_next90_m141_hub_import_route_review_required.py fail-close queue, registry, and Hub proof drift when route/support/publication surfaces claim parity without the direct import-route receipts.",
                ],
            },
            {
                "receipt_id": "bind_exchange_and_outward_facing_output_routes_to_visibl:hub",
                "package_id": "next90-m143-hub-bind-exchange-and-outward-facing-output-routes-to-visible-receipt-or-bou",
                "milestone_id": 143,
                "frontier_id": 4032374688,
                "summary": "Install recovery exchange, release-bundle proof, creator-publication detail, and campaign federation routes now surface a visible receipt or a bounded-failure posture instead of silent optimistic claims, so output readiness stays inspectable on every outward-facing lane.",
                "routes": [
                    "/downloads/install/{artifactId}/claim.json",
                    "/downloads/install/{artifactId}/continue.json",
                    "/api/v1/install-linking/continuation",
                    "/api/v1/install-linking/continuation/support",
                    "/api/v1/install-linking/continuation/update",
                    "/api/v1/install-linking/continuation/rollback",
                    "/artifacts/release-bundles/{releaseArtifactId}",
                    "/artifacts/release-bundles/{releaseArtifactId}/{format}",
                    "/artifacts/publications/{publicationId}",
                    "/api/v1/public/artifacts/publications/{publicationId}",
                    "/api/public/artifacts/publications/{publicationId}",
                    "/api/v1/campaign-spine/me/workspaces/{workspaceId}/federation-batches",
                ],
                "surfaces": [
                    "bind_exchange_and_outward_facing_output_routes_to_visibl:hub",
                    "desktop_native_claim_and_recovery",
                    "support_followthrough:install_truth",
                    "public_proof_shelf:release_bundles",
                    "creator_publication_detail",
                    "campaign_federation_exchange",
                ],
                "evidence": [
                    "PublicLandingController.cs binds install recovery exchange, release-bundle proof, and creator-publication detail routes to route receipts or bounded review posture.",
                    "InstallLinkingController.cs keeps native claimed-install continuation, support, update, and rollback routes on the same route-receipt or bounded-review contract.",
                    "CampaignFederationOrchestrationService.cs keeps federation batches bounded until every outward-facing source pack carries a live publication-shelf receipt.",
                    "Views/PublicLanding/PublicCreatorPublication.cshtml surfaces the creator-publication route receipt or bounded review posture directly on the public detail page.",
                    "RunServicesSmoke/Program.cs proves native continuation, release-bundle proof, creator-publication detail, and campaign federation routes expose route receipts or bounded review posture instead of silent claims.",
                    "verify_next90_m143_hub_exchange_output_receipts.py and tests/test_next90_m143_hub_exchange_output_receipts.py fail closed when exchange/output route proof, queue truth, or release-proof receipts drift.",
                ],
            },
        ],
    }

    _sync_local_flagship_readiness_artifact_if_needed(
        out_path=out_path,
        source_path=str(desktop_client_readiness.get("source_path") or "").strip(),
    )

    # The proof path is bind-mounted into the public portal. Serialize the final
    # local + served replacement with the same fixed host mutation authority used
    # by standalone deploy and recovery so an atomic rename cannot race container
    # recreation or rollback verification.
    changed = _publish_runtime_proof_artifacts(
        out_path=out_path,
        payload=payload,
        proof_max_age_seconds=proof_max_age_seconds,
        proof_max_future_skew_seconds=proof_max_future_skew_seconds,
    )
    if changed:
        print(f"wrote hub local proof: {out_path}")
    else:
        print(f"hub local proof unchanged and still fresh: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

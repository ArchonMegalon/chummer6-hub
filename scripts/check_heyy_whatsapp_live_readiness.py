#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ENV_PATH = ROOT / ".env"
DEFAULT_CONTAINER = "chummer6-hub-chummer-portal-1"
DEFAULT_INTERNAL_API_BASE_URL = "http://127.0.0.1:8091"
DEFAULT_INTERNAL_API_TIMEOUT_SECONDS = 10.0
DEFAULT_WHATSAPP_WEB_SIDECAR_BASE_URL = "http://127.0.0.1:8098"
DEFAULT_WHATSAPP_WEB_SESSION_REF = "default-wa-web"
DEFAULT_EA_HERTA_LIVE_VERIFIER = "/docker/EA/scripts/verify_whatsapp_web_herta_live_e2e.py"

HEYY_KEYS = (
    "CHUMMER_HEYY_SCAM_CHAT_WHATSAPP_ENABLED",
    "CHUMMER_HEYY_SCAM_CHAT_META_ACCESS_TOKEN",
    "CHUMMER_HEYY_SCAM_CHAT_META_PHONE_NUMBER_ID",
    "CHUMMER_HEYY_SCAM_CHAT_META_GRAPH_VERSION",
    "CHUMMER_HEYY_SCAM_CHAT_EA_BASE_URL",
    "CHUMMER_HEYY_SCAM_CHAT_BLOCKED_EA_DELIVERY_HOSTS",
    "CHUMMER_HEYY_SCAM_CHAT_EA_API_TOKEN",
    "CHUMMER_HEYY_SCAM_CHAT_EA_PRINCIPAL_ID",
    "CHUMMER_HEYY_SCAM_CHAT_EA_BINDING_ID",
    "CHUMMER_HEYY_SCAM_CHAT_EA_WHATSAPP_BINDING_ID",
    "CHUMMER_HEYY_SCAM_CHAT_EA_CHAT_BASE_URL",
    "CHUMMER_HEYY_SCAM_CHAT_EA_CHAT_BEARER_TOKEN",
    "CHUMMER_HEYY_SCAM_CHAT_EA_CF_ACCESS_CLIENT_ID",
    "CHUMMER_HEYY_SCAM_CHAT_EA_CF_ACCESS_CLIENT_SECRET",
    "ANSWERLY_OPENAI_COMPAT_EA_UPSTREAM_BASE_URL",
    "ANSWERLY_OPENAI_COMPAT_EA_UPSTREAM_BEARER_TOKEN",
    "ANSWERLY_OPENAI_COMPAT_EA_CF_ACCESS_CLIENT_ID",
    "ANSWERLY_OPENAI_COMPAT_EA_CF_ACCESS_CLIENT_SECRET",
    "CODEXLIZ_OLLAMA_HOST",
    "CODEXLIZ_CF_ACCESS_CLIENT_ID",
    "CODEXLIZ_CF_ACCESS_CLIENT_SECRET",
    "CHUMMER_HEYY_SCAM_CHAT_EA_MODEL",
    "ANSWERLY_OPENAI_COMPAT_MODEL_ID",
    "CHUMMER_HEYY_SCAM_CHAT_INTERNAL_TOKEN",
    "FLEET_INTERNAL_API_TOKEN",
)

CHANNEL_MESSAGING_KEYS = (
    "CHUMMER_EA_CHANNEL_MESSAGING_EA_BASE_URL",
    "CHUMMER_EA_CHANNEL_MESSAGING_EA_API_TOKEN",
    "CHUMMER_EA_CHANNEL_MESSAGING_EA_PRINCIPAL_ID",
    "CHUMMER_EA_CHANNEL_MESSAGING_EA_BINDING_ID",
    "CHUMMER_EA_CHANNEL_MESSAGING_EA_TELEGRAM_BINDING_ID",
    "CHUMMER_EA_CHANNEL_MESSAGING_EA_WHATSAPP_BINDING_ID",
    "CHUMMER_EA_CHANNEL_MESSAGING_EA_WHATSAPP_WEB_BINDING_ID",
    "CHUMMER_EA_CHANNEL_MESSAGING_EA_WHATSAPP_TRANSPORT",
)

WHATSAPP_WEB_KEYS = (
    "EA_WHATSAPP_WEB_DEFAULT_SESSION_REF",
    "WA_WEB_SESSION_REF",
)

ALL_KEYS = HEYY_KEYS + CHANNEL_MESSAGING_KEYS + WHATSAPP_WEB_KEYS


def load_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values

    for raw in path.read_text(errors="ignore").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def load_container_env(container: str) -> dict[str, str]:
    try:
        raw = subprocess.check_output(
            ["docker", "inspect", container, "--format", "{{json .Config.Env}}"],
            text=True,
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        return {}

    try:
        items = json.loads(raw)
    except json.JSONDecodeError:
        return {}

    values: dict[str, str] = {}
    for item in items:
        if isinstance(item, str) and "=" in item:
            key, value = item.split("=", 1)
            values[key] = value
    return values


def present(values: dict[str, str], key: str) -> bool:
    return bool(str(values.get(key) or "").strip())


def enabled(values: dict[str, str], key: str) -> bool:
    return str(values.get(key) or "").strip().lower() == "true"


def normalize_phone(value: str | None) -> str | None:
    digits = "".join(ch for ch in str(value or "") if ch.isdigit())
    return digits if len(digits) >= 7 else None


def base_url_is_real(values: dict[str, str]) -> bool:
    host = extract_host(str(values.get("CHUMMER_HEYY_SCAM_CHAT_EA_BASE_URL") or ""))
    if not host:
        return False
    return host not in blocked_ea_delivery_hosts(values)


def blocked_ea_delivery_hosts(values: dict[str, str]) -> set[str]:
    default_hosts = {"support-progress-mock", "localhost", "127.0.0.1", "::1"}
    configured = str(values.get("CHUMMER_HEYY_SCAM_CHAT_BLOCKED_EA_DELIVERY_HOSTS") or "").strip()
    raw_hosts = re.split(r"[;,\|\r\n]+", configured) if configured else []
    hosts = {extract_host(value) or value.strip().strip("[]").rstrip("/").lower() for value in raw_hosts if value.strip()}
    return default_hosts | {host for host in hosts if host}


def extract_host(value: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        return ""
    parsed = urllib.parse.urlparse(normalized if "://" in normalized else f"http://{normalized.lstrip('/')}")
    return parsed.hostname.strip("[]").rstrip(".").lower() if parsed.hostname else ""


def resolve_whatsapp_web_session_ref(values: dict[str, str], explicit_session_ref: str | None) -> str:
    explicit = str(explicit_session_ref or "").strip()
    if explicit:
        return explicit
    for key in WHATSAPP_WEB_KEYS:
        configured = str(values.get(key) or "").strip()
        if configured:
            return configured
    return DEFAULT_WHATSAPP_WEB_SESSION_REF


def parse_iso_timestamp(value: object) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(UTC)
    except ValueError:
        return None


def normalize_value(values: dict[str, str], key: str) -> str | None:
    value = str(values.get(key) or "").strip()
    return value or None


def chat_auth_configured(values: dict[str, str]) -> bool:
    bearer = normalize_value(values, "CHUMMER_HEYY_SCAM_CHAT_EA_CHAT_BEARER_TOKEN") or normalize_value(
        values, "ANSWERLY_OPENAI_COMPAT_EA_UPSTREAM_BEARER_TOKEN"
    )
    if bearer:
        return True

    client_id = (
        normalize_value(values, "CHUMMER_HEYY_SCAM_CHAT_EA_CF_ACCESS_CLIENT_ID")
        or normalize_value(values, "ANSWERLY_OPENAI_COMPAT_EA_CF_ACCESS_CLIENT_ID")
        or normalize_value(values, "CODEXLIZ_CF_ACCESS_CLIENT_ID")
    )
    client_secret = (
        normalize_value(values, "CHUMMER_HEYY_SCAM_CHAT_EA_CF_ACCESS_CLIENT_SECRET")
        or normalize_value(values, "ANSWERLY_OPENAI_COMPAT_EA_CF_ACCESS_CLIENT_SECRET")
        or normalize_value(values, "CODEXLIZ_CF_ACCESS_CLIENT_SECRET")
    )
    return bool(client_id and client_secret)


def answerly_verification_state(values: dict[str, str]) -> str:
    state = str(values.get("ANSWERLY_PROVIDER_VERIFICATION_STATE") or "").strip().lower()
    if state in {"verified_full_adapter", "verified_widget_only", "rejected"}:
        return state
    return "unverified"


def answerly_local_compat_ready(values: dict[str, str]) -> bool:
    return (
        enabled(values, "ANSWERLY_ENABLED")
        and enabled(values, "ANSWERLY_SUPPORT_ENABLED")
        and enabled(values, "ANSWERLY_OPENAI_COMPAT_ENABLED")
        and answerly_verification_state(values) == "verified_full_adapter"
        and present(values, "ANSWERLY_OPENAI_COMPAT_API_TOKEN")
    )


def resolve_chat_base_url(values: dict[str, str]) -> str | None:
    explicit_heyy = normalize_value(values, "CHUMMER_HEYY_SCAM_CHAT_EA_CHAT_BASE_URL")
    if explicit_heyy:
        return explicit_heyy

    answerly = normalize_value(values, "ANSWERLY_OPENAI_COMPAT_EA_UPSTREAM_BASE_URL")
    if answerly and chat_auth_configured(values):
        return answerly

    return normalize_value(values, "CODEXLIZ_OLLAMA_HOST")


def raw_chat_route_candidate(values: dict[str, str]) -> str:
    if normalize_value(values, "CHUMMER_HEYY_SCAM_CHAT_EA_CHAT_BASE_URL"):
        return "heyy_chat_base_url"
    if normalize_value(values, "ANSWERLY_OPENAI_COMPAT_EA_UPSTREAM_BASE_URL"):
        return "answerly_upstream"
    if normalize_value(values, "CODEXLIZ_OLLAMA_HOST"):
        return "codexliz_ollama"
    return "unconfigured"


def draft_generation_blocking_reason(values: dict[str, str]) -> str | None:
    if resolve_chat_base_url(values):
        return None

    if normalize_value(values, "ANSWERLY_OPENAI_COMPAT_EA_UPSTREAM_BASE_URL") and not chat_auth_configured(values):
        return "answerly_upstream_auth_missing"

    if not answerly_local_compat_ready(values):
        if answerly_verification_state(values) != "verified_full_adapter":
            return "answerly_local_compat_unverified"
        return "answerly_local_compat_disabled"

    return "no_chat_route_configured"


def inspect_ea_db_binding() -> dict[str, Any]:
    query = (
        "select binding_id, principal_id, connector_name, status, "
        "length(coalesce(nullif(auth_metadata_json ->> 'access_token', ''), '')) > 0 as access_token_present, "
        "length(coalesce(nullif(auth_metadata_json ->> 'phone_number_id', ''), '')) > 0 as phone_number_id_present, "
        "coalesce(auth_metadata_json ->> 'credential_status', '') as credential_status "
        "from connector_bindings "
        "where connector_name ilike '%whatsapp%' or binding_id ilike '%whatsapp%' "
        "order by updated_at desc limit 5;"
    )
    try:
        raw = subprocess.check_output(
            [
                "docker",
                "exec",
                "ea-db",
                "psql",
                "-U",
                "postgres",
                "-d",
                "ea",
                "-t",
                "-A",
                "-F",
                "\t",
                "-c",
                query,
            ],
            text=True,
            stderr=subprocess.DEVNULL,
        )
    except Exception as exc:
        return {"available": False, "error": exc.__class__.__name__, "bindings": []}

    bindings: list[dict[str, Any]] = []
    for line in raw.splitlines():
        parts = line.split("\t")
        if len(parts) != 7:
            continue
        bindings.append(
            {
                "binding_id": parts[0],
                "principal_id": parts[1],
                "connector_name": parts[2],
                "status": parts[3],
                "access_token_present": parts[4].lower() == "t",
                "phone_number_id_present": parts[5].lower() == "t",
                "credential_status": parts[6],
            }
        )
    return {"available": True, "bindings": bindings}


def internal_api_token(values: dict[str, str]) -> str:
    return str(
        values.get("CHUMMER_HEYY_SCAM_CHAT_INTERNAL_TOKEN")
        or values.get("FLEET_INTERNAL_API_TOKEN")
        or ""
    ).strip()


def probe_internal_api(api_base_url: str, token: str) -> dict[str, Any]:
    request = urllib.request.Request(
        f"{api_base_url.rstrip('/')}/api/internal/heyy/scam-chat/conversations?take=1",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=DEFAULT_INTERNAL_API_TIMEOUT_SECONDS) as response:
            payload = json.loads(response.read().decode("utf-8") or "[]")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        return {
            "status": "unreachable",
            "reason": f"http_{exc.code}",
            "detail": detail[:300],
        }
    except Exception as exc:
        return {
            "status": "unreachable",
            "reason": exc.__class__.__name__,
            "detail": str(exc)[:300],
        }

    return {
        "status": "reachable",
        "conversation_count": len(payload) if isinstance(payload, list) else None,
    }


def probe_whatsapp_web_sidecar(base_url: str, session_ref: str) -> dict[str, Any]:
    normalized_base_url = str(base_url or "").strip().rstrip("/")
    normalized_session_ref = str(session_ref or "").strip()
    if not normalized_base_url or not normalized_session_ref:
        return {
            "status": "not_checked",
            "ready": False,
            "reason": "sidecar_probe_unconfigured",
            "session_ref": normalized_session_ref,
        }

    try:
        with urllib.request.urlopen(f"{normalized_base_url}/healthz", timeout=DEFAULT_INTERNAL_API_TIMEOUT_SECONDS) as response:
            health_payload = json.loads(response.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        return {
            "status": "unreachable",
            "ready": False,
            "reason": f"http_{exc.code}",
            "detail": detail[:300],
            "session_ref": normalized_session_ref,
        }
    except Exception as exc:
        return {
            "status": "unreachable",
            "ready": False,
            "reason": exc.__class__.__name__,
            "detail": str(exc)[:300],
            "session_ref": normalized_session_ref,
        }

    status = str(health_payload.get("status") or "").strip() or "unknown"
    reported_session_ref = str(health_payload.get("session_ref") or normalized_session_ref).strip()
    qr_metadata = {"status": "not_checked"}
    if status == "qr_required" and reported_session_ref:
        qr_metadata = probe_whatsapp_web_qr_metadata(normalized_base_url, reported_session_ref)
    ready = bool(health_payload.get("ready")) or status in {"ready", "authenticated", "connected"}
    result = {
        "status": status,
        "ready": ready,
        "reason": "" if ready else status,
        "session_ref": reported_session_ref,
        "ok": bool(health_payload.get("ok")),
        "qr": qr_metadata,
    }
    return result


def probe_whatsapp_web_qr_metadata(base_url: str, session_ref: str) -> dict[str, Any]:
    normalized_base_url = str(base_url or "").strip().rstrip("/")
    normalized_session_ref = str(session_ref or "").strip()
    quoted_session_ref = urllib.parse.quote(normalized_session_ref)
    url = f"{normalized_base_url}/sessions/{quoted_session_ref}/qr"
    try:
        with urllib.request.urlopen(url, timeout=DEFAULT_INTERNAL_API_TIMEOUT_SECONDS) as response:
            payload = json.loads(response.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        return {
            "status": "unavailable",
            "reason": f"http_{exc.code}",
            "detail": detail[:200],
            "raw_qr_included": False,
        }
    except Exception as exc:
        return {
            "status": "unavailable",
            "reason": exc.__class__.__name__,
            "detail": str(exc)[:200],
            "raw_qr_included": False,
        }

    last_qr_at = str(payload.get("last_qr_at") or "").strip()
    last_qr = parse_iso_timestamp(last_qr_at)
    age_seconds = None
    if last_qr is not None:
        age_seconds = max(0, int((datetime.now(UTC) - last_qr).total_seconds()))
    reported_session_ref = str(payload.get("session_ref") or normalized_session_ref)
    reported_quoted_session_ref = urllib.parse.quote(reported_session_ref)
    qr_present = bool(payload.get("qr_present"))
    return {
        "status": str(payload.get("status") or "").strip() or "unknown",
        "ready": bool(payload.get("ready")),
        "qr_present": qr_present,
        "qr_required": bool(payload.get("qr_required")),
        "last_qr_at": last_qr_at,
        "qr_age_seconds": age_seconds,
        "session_ref": reported_session_ref,
        "pair_url": f"{normalized_base_url}/sessions/{reported_quoted_session_ref}/pair" if qr_present else "",
        "qr_svg_url": f"{normalized_base_url}/sessions/{reported_quoted_session_ref}/qr.svg" if qr_present else "",
        "raw_qr_included": False,
    }


def whatsapp_web_operator_next_action(whatsapp_web_sidecar: dict[str, Any] | None) -> dict[str, Any]:
    if not whatsapp_web_sidecar:
        return {"status": "not_needed"}
    if bool(whatsapp_web_sidecar.get("ready")):
        return {"status": "not_needed", "reason": "whatsapp_web_sidecar_ready"}

    qr = whatsapp_web_sidecar.get("qr")
    qr_metadata = qr if isinstance(qr, dict) else {}
    if bool(qr_metadata.get("qr_required")) and bool(qr_metadata.get("qr_present")):
        return {
            "status": "operator_required",
            "reason": "whatsapp_web_qr_scan_required",
            "pair_url": str(qr_metadata.get("pair_url") or ""),
            "qr_svg_url": str(qr_metadata.get("qr_svg_url") or ""),
            "session_ref": str(qr_metadata.get("session_ref") or whatsapp_web_sidecar.get("session_ref") or ""),
            "after_scan": "rerun_heyy_whatsapp_live_readiness",
            "raw_qr_included": False,
        }

    reason = str(whatsapp_web_sidecar.get("reason") or whatsapp_web_sidecar.get("status") or "whatsapp_web_sidecar_not_ready")
    return {
        "status": "blocked",
        "reason": reason,
        "session_ref": str(whatsapp_web_sidecar.get("session_ref") or ""),
        "raw_qr_included": False,
    }


def enrich_operator_next_action_commands(
    report: dict[str, Any],
    *,
    args: argparse.Namespace,
    session_ref: str,
) -> None:
    action = report.get("operator_next_action")
    if not isinstance(action, dict) or action.get("status") != "operator_required":
        return

    readiness_command = ["python3", "scripts/check_heyy_whatsapp_live_readiness.py"]
    if str(args.env_file or "") != str(DEFAULT_ENV_PATH):
        readiness_command.extend(["--env-file", str(args.env_file)])
    if bool(args.skip_container):
        readiness_command.append("--skip-container")
    else:
        readiness_command.extend(["--container", str(args.container)])
    if str(args.recipient or "").strip():
        readiness_command.extend(["--recipient", str(args.recipient).strip()])
    readiness_command.extend(
        [
            "--include-whatsapp-web-sidecar",
            "--whatsapp-web-sidecar-base-url",
            str(args.whatsapp_web_sidecar_base_url or DEFAULT_WHATSAPP_WEB_SIDECAR_BASE_URL),
            "--whatsapp-web-session-ref",
            str(session_ref or ""),
            "--internal-api-base-url",
            str(args.internal_api_base_url or DEFAULT_INTERNAL_API_BASE_URL),
        ]
    )
    action["rerun_readiness_command"] = readiness_command
    action["herta_live_verifier_command"] = [
        "python3",
        DEFAULT_EA_HERTA_LIVE_VERIFIER,
        "--session-api-base-url",
        str(args.whatsapp_web_sidecar_base_url or DEFAULT_WHATSAPP_WEB_SIDECAR_BASE_URL),
        "--session-ref",
        str(session_ref or ""),
    ]


def build_report(
    values: dict[str, str],
    recipient: str | None,
    internal_api: dict[str, Any],
    whatsapp_web_sidecar: dict[str, Any] | None = None,
) -> dict[str, Any]:
    recipient_digits = normalize_phone(recipient)
    ea_base_host = extract_host(str(values.get("CHUMMER_HEYY_SCAM_CHAT_EA_BASE_URL") or ""))
    blocked_delivery_hosts = blocked_ea_delivery_hosts(values)
    ea_base_url_blocked = bool(ea_base_host and ea_base_host in blocked_delivery_hosts)
    meta_ready = (
        enabled(values, "CHUMMER_HEYY_SCAM_CHAT_WHATSAPP_ENABLED")
        and present(values, "CHUMMER_HEYY_SCAM_CHAT_META_ACCESS_TOKEN")
        and present(values, "CHUMMER_HEYY_SCAM_CHAT_META_PHONE_NUMBER_ID")
    )
    ea_ready = (
        enabled(values, "CHUMMER_HEYY_SCAM_CHAT_WHATSAPP_ENABLED")
        and present(values, "CHUMMER_HEYY_SCAM_CHAT_EA_API_TOKEN")
        and present(values, "CHUMMER_HEYY_SCAM_CHAT_EA_PRINCIPAL_ID")
        and (
            present(values, "CHUMMER_HEYY_SCAM_CHAT_EA_WHATSAPP_BINDING_ID")
            or present(values, "CHUMMER_HEYY_SCAM_CHAT_EA_BINDING_ID")
        )
        and base_url_is_real(values)
    )
    chat_base_url = resolve_chat_base_url(values)
    draft_generation_ready = bool(chat_base_url)
    raw_chat_candidate = raw_chat_route_candidate(values)
    draft_blocking_reason = draft_generation_blocking_reason(values)
    local_answerly_ready = answerly_local_compat_ready(values)
    blockers: list[str] = []
    if not enabled(values, "CHUMMER_HEYY_SCAM_CHAT_WHATSAPP_ENABLED"):
        blockers.append("whatsapp_disabled")
    if recipient and not recipient_digits:
        blockers.append("recipient_invalid")
    if not meta_ready and not ea_ready:
        blockers.append("live_provider_unconfigured")
    if internal_api.get("status") != "reachable":
        blockers.append("internal_api_unreachable")
    if whatsapp_web_sidecar is not None and not bool(whatsapp_web_sidecar.get("ready")):
        blockers.append("whatsapp_web_sidecar_not_ready")
    if not draft_generation_ready:
        blockers.append("draft_generation_unconfigured")
        if draft_blocking_reason:
            blockers.append(draft_blocking_reason)

    channel_messaging_ready = (
        present(values, "CHUMMER_EA_CHANNEL_MESSAGING_EA_API_TOKEN")
        and present(values, "CHUMMER_EA_CHANNEL_MESSAGING_EA_PRINCIPAL_ID")
        and (
            present(values, "CHUMMER_EA_CHANNEL_MESSAGING_EA_WHATSAPP_WEB_BINDING_ID")
            or present(values, "CHUMMER_EA_CHANNEL_MESSAGING_EA_WHATSAPP_BINDING_ID")
            or present(values, "CHUMMER_EA_CHANNEL_MESSAGING_EA_BINDING_ID")
        )
        and base_url_is_real({
            "CHUMMER_HEYY_SCAM_CHAT_EA_BASE_URL": values.get("CHUMMER_EA_CHANNEL_MESSAGING_EA_BASE_URL", "")
        })
    )

    return {
        "status": "ready" if not blockers else "blocked",
        "blockers": blockers,
        "recipient": {
            "provided": bool(recipient),
            "digits_present": bool(recipient_digits),
            "valid": bool(recipient_digits),
        },
        "config": {
            "whatsapp_enabled": enabled(values, "CHUMMER_HEYY_SCAM_CHAT_WHATSAPP_ENABLED"),
            "meta_access_token_present": present(values, "CHUMMER_HEYY_SCAM_CHAT_META_ACCESS_TOKEN"),
            "meta_phone_number_id_present": present(values, "CHUMMER_HEYY_SCAM_CHAT_META_PHONE_NUMBER_ID"),
            "ea_base_url_real": base_url_is_real(values),
            "ea_base_url_host": ea_base_host,
            "ea_base_url_blocked": ea_base_url_blocked,
            "blocked_ea_delivery_hosts": sorted(blocked_delivery_hosts),
            "ea_api_token_present": present(values, "CHUMMER_HEYY_SCAM_CHAT_EA_API_TOKEN"),
            "ea_principal_id_present": present(values, "CHUMMER_HEYY_SCAM_CHAT_EA_PRINCIPAL_ID"),
            "ea_whatsapp_binding_present": present(values, "CHUMMER_HEYY_SCAM_CHAT_EA_WHATSAPP_BINDING_ID"),
            "ea_generic_binding_present": present(values, "CHUMMER_HEYY_SCAM_CHAT_EA_BINDING_ID"),
        },
        "providers": {
            "meta_ready": meta_ready,
            "ea_ready": ea_ready,
        },
        "drafting": {
            "chat_base_url_present": bool(chat_base_url),
            "configured_chat_base_url_present": raw_chat_candidate != "unconfigured",
            "chat_auth_configured": chat_auth_configured(values),
            "chat_route": (
                "heyy_chat_base_url"
                if normalize_value(values, "CHUMMER_HEYY_SCAM_CHAT_EA_CHAT_BASE_URL")
                else "answerly_upstream"
                if (
                    normalize_value(values, "ANSWERLY_OPENAI_COMPAT_EA_UPSTREAM_BASE_URL")
                    and chat_auth_configured(values)
                )
                else "codexliz_ollama"
                if normalize_value(values, "CODEXLIZ_OLLAMA_HOST")
                else "unconfigured"
            ),
            "chat_route_candidate": raw_chat_candidate,
            "model_present": bool(
                normalize_value(values, "CHUMMER_HEYY_SCAM_CHAT_EA_MODEL")
                or normalize_value(values, "ANSWERLY_OPENAI_COMPAT_MODEL_ID")
            ),
            "blocking_reason": draft_blocking_reason,
            "answerly_upstream_base_url_present": bool(
                normalize_value(values, "ANSWERLY_OPENAI_COMPAT_EA_UPSTREAM_BASE_URL")
            ),
            "answerly_local_compat_enabled": (
                enabled(values, "ANSWERLY_ENABLED")
                and enabled(values, "ANSWERLY_SUPPORT_ENABLED")
                and enabled(values, "ANSWERLY_OPENAI_COMPAT_ENABLED")
            ),
            "answerly_local_compat_ready": local_answerly_ready,
            "answerly_verification_state": answerly_verification_state(values),
            "ready": draft_generation_ready,
        },
        "internal_api": internal_api,
        "whatsapp_web_sidecar": whatsapp_web_sidecar or {"status": "not_checked", "ready": False},
        "operator_next_action": whatsapp_web_operator_next_action(whatsapp_web_sidecar),
        "channel_messaging": {
            "ea_base_url_real": base_url_is_real({
                "CHUMMER_HEYY_SCAM_CHAT_EA_BASE_URL": values.get("CHUMMER_EA_CHANNEL_MESSAGING_EA_BASE_URL", "")
            }),
            "ea_api_token_present": present(values, "CHUMMER_EA_CHANNEL_MESSAGING_EA_API_TOKEN"),
            "ea_principal_id_present": present(values, "CHUMMER_EA_CHANNEL_MESSAGING_EA_PRINCIPAL_ID"),
            "ea_generic_binding_present": present(values, "CHUMMER_EA_CHANNEL_MESSAGING_EA_BINDING_ID"),
            "ea_whatsapp_binding_present": present(values, "CHUMMER_EA_CHANNEL_MESSAGING_EA_WHATSAPP_BINDING_ID"),
            "ea_whatsapp_web_binding_present": present(values, "CHUMMER_EA_CHANNEL_MESSAGING_EA_WHATSAPP_WEB_BINDING_ID"),
            "ready": channel_messaging_ready,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Check Heyy WhatsApp live-send readiness without printing secrets.")
    parser.add_argument("--env-file", default=str(DEFAULT_ENV_PATH))
    parser.add_argument("--container", default=DEFAULT_CONTAINER)
    parser.add_argument("--recipient", default="")
    parser.add_argument("--skip-container", action="store_true")
    parser.add_argument("--include-ea-db", action="store_true")
    parser.add_argument("--internal-api-base-url", default=DEFAULT_INTERNAL_API_BASE_URL)
    parser.add_argument("--include-whatsapp-web-sidecar", action="store_true")
    parser.add_argument("--whatsapp-web-sidecar-base-url", default=DEFAULT_WHATSAPP_WEB_SIDECAR_BASE_URL)
    parser.add_argument("--whatsapp-web-session-ref", default="")
    args = parser.parse_args()

    env_values = load_env_file(Path(args.env_file))
    container_values = {} if args.skip_container else load_container_env(args.container)
    effective = {**env_values, **{key: value for key, value in container_values.items() if key in ALL_KEYS}}
    token = internal_api_token(effective)
    internal_api = (
        {"status": "unreachable", "reason": "internal_api_token_missing", "detail": ""}
        if not token
        else probe_internal_api(args.internal_api_base_url, token)
    )
    whatsapp_web_session_ref = resolve_whatsapp_web_session_ref(effective, args.whatsapp_web_session_ref)
    sidecar_report = (
        probe_whatsapp_web_sidecar(
            args.whatsapp_web_sidecar_base_url,
            whatsapp_web_session_ref,
        )
        if args.include_whatsapp_web_sidecar
        else None
    )
    report = build_report(effective, args.recipient, internal_api, sidecar_report)
    effective_whatsapp_web_session_ref = str((sidecar_report or {}).get("session_ref") or whatsapp_web_session_ref)
    enrich_operator_next_action_commands(report, args=args, session_ref=effective_whatsapp_web_session_ref)
    report["sources"] = {
        "env_file": str(Path(args.env_file)),
        "env_file_present": Path(args.env_file).exists(),
        "container": None if args.skip_container else args.container,
        "container_env_present": bool(container_values),
        "internal_api_base_url": args.internal_api_base_url,
        "whatsapp_web_sidecar_base_url": args.whatsapp_web_sidecar_base_url if args.include_whatsapp_web_sidecar else "",
        "whatsapp_web_session_ref": effective_whatsapp_web_session_ref if args.include_whatsapp_web_sidecar else "",
        "whatsapp_web_requested_session_ref": whatsapp_web_session_ref if args.include_whatsapp_web_sidecar else "",
        "whatsapp_web_reported_session_ref": str((sidecar_report or {}).get("session_ref") or "")
        if args.include_whatsapp_web_sidecar
        else "",
    }
    if args.include_ea_db:
        report["ea_db"] = inspect_ea_db_binding()

    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] == "ready" else 2


if __name__ == "__main__":
    raise SystemExit(main())

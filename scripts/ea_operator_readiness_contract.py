from __future__ import annotations

from collections.abc import Mapping, Sequence


REQUIRED_COMPONENT_KEYS: tuple[str, ...] = (
    "telegram",
    "google_workspace_oauth",
    "pushbullet",
    "whatsapp",
    "whatsapp_pairing",
    "teable_recovery",
    "mymedia_alexa",
)

STABLE_STATUSES: dict[str, set[str]] = {
    "telegram": {"ready"},
    "google_workspace_oauth": {"pass", "ready_manual_console_check"},
    "pushbullet": {"ready_configured", "ready_live_verified"},
    "whatsapp": {"ready"},
    "whatsapp_pairing": {"ready"},
    "teable_recovery": {"ready"},
    "mymedia_alexa": {"ready", "ready_library_scan_in_progress"},
    "proactive_route": {"ready"},
    "proactive_artifacts": {"ok"},
}

NON_BLOCKING_ATTENTION_STATUSES: dict[str, set[str]] = {
    "pushbullet": {"blocked_setup_required"},
    "onemin_direct_refresh": {"rate_limited"},
}


def component_key(component: Mapping[str, object]) -> str:
    return str(component.get("key") or "").strip()


def component_requires_attention(component: Mapping[str, object]) -> bool:
    if not bool(component.get("probe_ok")):
        return True
    if not bool(component.get("ready")):
        return True
    key = component_key(component)
    status = str(component.get("status") or "").strip()
    stable_statuses = STABLE_STATUSES.get(key, {"ready"})
    return status not in stable_statuses


def component_counts_as_blocked(component: Mapping[str, object]) -> bool:
    if not bool(component.get("probe_ok")) or bool(component.get("ready")):
        return False
    key = component_key(component)
    status = str(component.get("status") or "").strip()
    if status in NON_BLOCKING_ATTENTION_STATUSES.get(key, set()):
        return False
    return True


def pairing_qr_recovery_present(components: Sequence[Mapping[str, object]]) -> bool:
    return any(
        component_key(item) == "whatsapp_pairing"
        and str(item.get("next_action") or "").strip() == "scan_whatsapp_web_qr"
        for item in components
    )


def suppressed_keys(components: Sequence[Mapping[str, object]]) -> set[str]:
    if not pairing_qr_recovery_present(components):
        return set()
    return {
        component_key(item)
        for item in components
        if component_key(item) == "whatsapp" and str(item.get("next_action") or "").strip() == "scan_whatsapp_web_qr"
    }


def effective_components(components: Sequence[Mapping[str, object]]) -> list[Mapping[str, object]]:
    hidden = suppressed_keys(components)
    return [item for item in components if component_key(item) and component_key(item) not in hidden]


def component_keys(components: Sequence[Mapping[str, object]]) -> list[str]:
    return [component_key(item) for item in components if component_key(item)]


def ready_component_keys(components: Sequence[Mapping[str, object]]) -> list[str]:
    return [component_key(item) for item in components if component_key(item) and bool(item.get("ready"))]


def blocked_component_keys(components: Sequence[Mapping[str, object]]) -> list[str]:
    return [
        component_key(item)
        for item in effective_components(components)
        if component_key(item) and component_counts_as_blocked(item)
    ]


def attention_component_keys(components: Sequence[Mapping[str, object]]) -> list[str]:
    return [
        component_key(item)
        for item in effective_components(components)
        if component_key(item) and component_requires_attention(item)
    ]


def probe_failed_component_keys(components: Sequence[Mapping[str, object]]) -> list[str]:
    return [
        component_key(item)
        for item in effective_components(components)
        if component_key(item) and not bool(item.get("probe_ok"))
    ]


def next_actions(components: Sequence[Mapping[str, object]]) -> list[dict[str, str]]:
    actions: list[dict[str, str]] = []
    for item in effective_components(components):
        if not component_requires_attention(item):
            continue
        key = component_key(item)
        action = str(item.get("next_action") or "").strip()
        if not key or not action:
            continue
        actions.append(
            {
                "component_key": key,
                "component_label": str(item.get("label") or "").strip(),
                "action": action,
                "reason": str(item.get("reason") or "").strip(),
                "href": str(item.get("next_action_href") or "").strip(),
                "label": str(item.get("next_action_label") or "").strip(),
                "method": str(item.get("next_action_method") or "").strip(),
            }
        )
    return actions


def advisory_actions(components: Sequence[Mapping[str, object]]) -> list[dict[str, str]]:
    actions: list[dict[str, str]] = []
    for item in effective_components(components):
        if component_requires_attention(item):
            continue
        key = component_key(item)
        action = str(item.get("next_action") or "").strip()
        if not key or not action:
            continue
        actions.append(
            {
                "component_key": key,
                "component_label": str(item.get("label") or "").strip(),
                "action": action,
                "reason": str(item.get("reason") or "").strip(),
                "href": str(item.get("next_action_href") or "").strip(),
                "label": str(item.get("next_action_label") or "").strip(),
                "method": str(item.get("next_action_method") or "").strip(),
            }
        )
    return actions


def runtime_blocking_findings(components: Sequence[Mapping[str, object]]) -> list[str]:
    findings: list[str] = []
    for item in effective_components(components):
        key = component_key(item)
        if not key:
            continue
        status = str(item.get("status") or "").strip() or "unknown"
        if not bool(item.get("probe_ok")):
            findings.append(f"probe_failed:{key}:{status}")
            continue
        if component_counts_as_blocked(item):
            findings.append(f"blocked:{key}:{status}")
    return findings


def runtime_advisory_findings(components: Sequence[Mapping[str, object]]) -> list[str]:
    findings: list[str] = []
    for item in effective_components(components):
        key = component_key(item)
        if not key or not component_requires_attention(item):
            continue
        if not bool(item.get("probe_ok")) or component_counts_as_blocked(item):
            continue
        status = str(item.get("status") or "").strip() or "unknown"
        findings.append(f"attention:{key}:{status}")
    return findings


def runtime_status(components: Sequence[Mapping[str, object]]) -> str:
    if runtime_blocking_findings(components):
        return "blocked"
    if runtime_advisory_findings(components):
        return "degraded"
    return "ready"


def runtime_ready(components: Sequence[Mapping[str, object]]) -> bool:
    return runtime_status(components) == "ready"

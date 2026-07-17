from __future__ import annotations

from typing import Any


FINDING_ACTIONS: dict[str, dict[str, Any]] = {
    "qbittorrent_api_unavailable": {
        "component_key": "qbittorrent",
        "component_label": "qBittorrent WebUI API",
        "action": "restore_qbittorrent_webui_api",
        "label": "Restore qBittorrent WebUI API access",
        "method": "manual",
    },
    "qbittorrent_staging_root_unreadable": {
        "component_key": "qbittorrent_staging",
        "component_label": "qBittorrent staging root",
        "action": "restore_qbittorrent_staging_root",
        "label": "Restore qBittorrent staging root access",
        "method": "manual",
    },
    "qbittorrent_orphan_partials_present": {
        "component_key": "qbittorrent_staging",
        "component_label": "qBittorrent staging hygiene",
        "action": "prune_orphan_partial_files",
        "label": "Prune orphan partial files",
        "method": "manual",
    },
    "qbittorrent_dead_metadata_downloads_present": {
        "component_key": "qbittorrent",
        "component_label": "qBittorrent metadata queue",
        "action": "requeue_or_delete_dead_metadata_downloads",
        "label": "Requeue or delete dead metadata downloads",
        "method": "manual",
    },
    "qbittorrent_dead_stalled_downloads_present": {
        "component_key": "qbittorrent",
        "component_label": "qBittorrent stalled downloads",
        "action": "requeue_or_delete_dead_stalled_downloads",
        "label": "Requeue or delete dead stalled downloads",
        "method": "manual",
    },
    "qbittorrent_long_checking_downloads_present": {
        "component_key": "qbittorrent",
        "component_label": "qBittorrent checking queue",
        "action": "requeue_or_delete_long_checking_downloads",
        "label": "Requeue or delete long checking downloads",
        "method": "manual",
    },
    "qbittorrent_queueing_disabled": {
        "component_key": "qbittorrent",
        "component_label": "qBittorrent runtime guardrails",
        "action": "enable_qbittorrent_queueing",
        "label": "Enable qBittorrent queueing",
        "method": "manual",
    },
    "qbittorrent_active_download_count_exceeds_limit": {
        "component_key": "qbittorrent",
        "component_label": "qBittorrent runtime guardrails",
        "action": "reduce_qbittorrent_active_download_pressure",
        "label": "Reduce qBittorrent active download pressure",
        "method": "manual",
    },
    "qbittorrent_forced_downloads_present": {
        "component_key": "qbittorrent",
        "component_label": "qBittorrent runtime guardrails",
        "action": "clear_qbittorrent_forced_downloads",
        "label": "Clear qBittorrent forced downloads",
        "method": "manual",
    },
}


def runtime_status(blocking_findings: list[str], advisory_findings: list[str]) -> str:
    if blocking_findings:
        return "blocked"
    if advisory_findings:
        return "degraded"
    return "ready"


def runtime_ready(blocking_findings: list[str], advisory_findings: list[str]) -> bool:
    return runtime_status(blocking_findings, advisory_findings) == "ready"


def _action_payload(reason: str) -> dict[str, Any]:
    template = FINDING_ACTIONS.get(reason)
    if not template:
        return {
            "component_key": "unknown",
            "component_label": "Unknown component",
            "action": reason,
            "reason": reason,
            "href": "",
            "label": reason.replace("_", " "),
            "method": "manual",
        }
    return {
        "component_key": template["component_key"],
        "component_label": template["component_label"],
        "action": template["action"],
        "reason": reason,
        "href": "",
        "label": template["label"],
        "method": template["method"],
    }


def next_actions(blocking_findings: list[str]) -> list[dict[str, Any]]:
    return [_action_payload(reason) for reason in blocking_findings]


def advisory_actions(advisory_findings: list[str]) -> list[dict[str, Any]]:
    return [_action_payload(reason) for reason in advisory_findings]

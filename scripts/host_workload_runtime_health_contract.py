from __future__ import annotations

from collections.abc import Sequence


FINDING_ACTIONS: dict[str, dict[str, str]] = {
    "pcloud_cache_mode_not_writes": {
        "component_key": "pcloud_mount",
        "component_label": "pCloud mount cache mode",
        "action": "restart_pcloud_mount_with_write_cache",
        "label": "Restart pCloud mount in writes mode",
        "method": "manual",
    },
    "qbittorrent_write_probe_failed": {
        "component_key": "qbittorrent",
        "component_label": "qBittorrent storage",
        "action": "repair_qbittorrent_save_path",
        "label": "Repair qBittorrent save path",
        "method": "manual",
    },
    "plex_pcloud_namespace_stale": {
        "component_key": "plex",
        "component_label": "Plex pCloud namespace",
        "action": "restart_plex_container",
        "label": "Restart Plex container",
        "method": "manual",
    },
    "plex_alias_paths_unavailable": {
        "component_key": "plex",
        "component_label": "Plex alias paths",
        "action": "repair_plex_alias_paths",
        "label": "Repair Plex alias paths",
        "method": "manual",
    },
    "host_workload_guardrails_probe_failed": {
        "component_key": "host_workload",
        "component_label": "Host workload guardrails",
        "action": "rerun_host_workload_guardrails_probe",
        "label": "Rerun host workload guardrails probe",
        "method": "manual",
    },
    "plex_namespace_restart_deferred_until_idle": {
        "component_key": "plex",
        "component_label": "Plex pCloud namespace",
        "action": "restart_plex_when_idle",
        "label": "Restart Plex after active sessions end",
        "method": "manual",
    },
    "qbittorrent_fast_resume_mismatches_present": {
        "component_key": "qbittorrent",
        "component_label": "qBittorrent resume state",
        "action": "recheck_or_requeue_mismatched_torrents",
        "label": "Recheck or requeue mismatched torrents",
        "method": "manual",
    },
    "recent_qbittorrent_storage_errors_present": {
        "component_key": "qbittorrent",
        "component_label": "qBittorrent storage log",
        "action": "inspect_recent_qbittorrent_storage_errors",
        "label": "Inspect recent qBittorrent storage errors",
        "method": "manual",
    },
    "internxt_container_probe_failed": {
        "component_key": "internxt",
        "component_label": "Internxt mount probe",
        "action": "inspect_internxt_mount_probe",
        "label": "Inspect Internxt mount probe",
        "method": "manual",
    },
    "host_workload_guardrail_failures_present": {
        "component_key": "host_workload",
        "component_label": "Host workload guardrails",
        "action": "inspect_host_workload_guardrail_failures",
        "label": "Inspect host workload guardrail failures",
        "method": "manual",
    },
    "cache_filesystem_below_reserve_threshold": {
        "component_key": "host_workload",
        "component_label": "Host cache reserve",
        "action": "run_media_cache_guard",
        "label": "Run media-cache guard and free cache space",
        "method": "manual",
    },
    "internxt_cache_budget_exceeds_host_headroom": {
        "component_key": "internxt",
        "component_label": "Internxt rclone cache budget",
        "action": "reduce_internxt_cache_budget_and_restart_mount_when_idle",
        "label": "Reduce Internxt cache budget and restart mount when idle",
        "method": "manual",
    },
    "plex_internxt_mirror_failed": {
        "component_key": "internxt_mirror",
        "component_label": "Internxt mirror lane",
        "action": "inspect_plex_internxt_mirror_failure",
        "label": "Inspect Internxt mirror failure",
        "method": "manual",
    },
    "plex_internxt_mirror_progress_stale": {
        "component_key": "internxt_mirror",
        "component_label": "Internxt mirror lane",
        "action": "inspect_plex_internxt_mirror_progress",
        "label": "Inspect Internxt mirror progress",
        "method": "manual",
    },
    "plex_internxt_mirror_status_unavailable": {
        "component_key": "internxt_mirror",
        "component_label": "Internxt mirror lane",
        "action": "inspect_plex_internxt_mirror_status_surface",
        "label": "Inspect Internxt mirror status surface",
        "method": "manual",
    },
}


def runtime_status(blocking_findings: Sequence[str], advisory_findings: Sequence[str]) -> str:
    if list(blocking_findings):
        return "blocked"
    if list(advisory_findings):
        return "degraded"
    return "ready"


def runtime_ready(blocking_findings: Sequence[str], advisory_findings: Sequence[str]) -> bool:
    return runtime_status(blocking_findings, advisory_findings) == "ready"


def _actions(findings: Sequence[str]) -> list[dict[str, str]]:
    actions: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for finding in findings:
        spec = FINDING_ACTIONS.get(str(finding).strip())
        if not spec:
            continue
        key = (spec["component_key"], spec["action"])
        if key in seen:
            continue
        seen.add(key)
        actions.append(
            {
                "component_key": spec["component_key"],
                "component_label": spec["component_label"],
                "action": spec["action"],
                "reason": str(finding).strip(),
                "href": "",
                "label": spec["label"],
                "method": spec["method"],
            }
        )
    return actions


def next_actions(blocking_findings: Sequence[str]) -> list[dict[str, str]]:
    return _actions(blocking_findings)


def advisory_actions(advisory_findings: Sequence[str]) -> list[dict[str, str]]:
    return _actions(advisory_findings)

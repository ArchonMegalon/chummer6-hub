from __future__ import annotations


PASS_SURFACE_STATUSES = {"access_protected", "reachable", "redirecting"}


def blocking_findings(
    *,
    public_surface_configured: bool,
    public_surface_scope: str,
    public_surface_ready: bool,
    public_surface_status: str,
    public_surface_reason: str,
    public_surface_cloudflare_blocked: bool,
) -> list[str]:
    findings: list[str] = []
    if not public_surface_configured:
        findings.append("mymedia_public_surface_not_configured")
    elif public_surface_scope != "public":
        findings.append("mymedia_public_surface_not_public")
    elif not public_surface_ready:
        findings.append(public_surface_reason or "mymedia_public_surface_not_ready")
    elif public_surface_status not in PASS_SURFACE_STATUSES:
        findings.append(f"mymedia_public_surface_status_unexpected:{public_surface_status or 'missing'}")
    elif public_surface_cloudflare_blocked:
        findings.append("mymedia_public_surface_blocked_by_cloudflare")
    return findings


def advisory_findings() -> list[str]:
    return []


def runtime_status(blocking: list[str], advisory: list[str]) -> str:
    if blocking:
        return "blocked"
    if advisory:
        return "degraded"
    return "ready"


def runtime_ready(blocking: list[str], advisory: list[str]) -> bool:
    return runtime_status(blocking, advisory) == "ready"

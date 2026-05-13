#!/usr/bin/env python3
from __future__ import annotations

import re

from absolute_completion_common import RUN_SERVICES_ROOT, WORKSPACE_ROOT, completion_path, now_iso, read_yaml, write_text


MIRROR_MANIFEST_PATH = RUN_SERVICES_ROOT / ".codex-design" / "product" / "PUBLIC_LANDING_MANIFEST.yaml"
CENTRAL_MANIFEST_PATH = WORKSPACE_ROOT / "chummer-design" / "products" / "chummer" / "PUBLIC_LANDING_MANIFEST.yaml"
MIRROR_ROUTE_FAMILY_PATH = RUN_SERVICES_ROOT / ".codex-design" / "product" / "PUBLIC_ROUTE_FAMILY_RECONCILIATION.yaml"
CENTRAL_ROUTE_FAMILY_PATH = WORKSPACE_ROOT / "chummer-design" / "products" / "chummer" / "PUBLIC_ROUTE_FAMILY_RECONCILIATION.yaml"
SURFACE_DOC_PATH = RUN_SERVICES_ROOT / "docs" / "PUBLIC_LANDING_SURFACE.md"
REQUIRED_ROUTES = [
    "/packages",
    "/packages/{packageId}",
    "/packages/{packageId}/vote",
    "/packages/{packageId}/follow",
    "/mobile",
    "/pwa",
    "/play",
    "/player",
    "/gm",
    "/observer",
    "/session",
    "/account/packages",
    "/account/packages/{packageId}",
    "/admin/packages",
    "/downloads/concierge",
    "/now/concierge",
    "/contact/concierge",
    "/join/concierge",
    "/join/primer",
]
REQUIRED_ROUTE_FAMILIES = {
    "packages": {
        "launch_state": "launch_present",
        "public_manifest": True,
        "hub_routes": True,
        "docs_surface": True,
        "route_proof": "live_strict_required",
        "owner_repo": "chummer6-hub-registry",
        "routes": [
            "/packages",
            "/packages/{packageId}",
            "/packages/{packageId}/vote",
            "/packages/{packageId}/follow",
        ],
    },
    "mobile_pwa_play": {
        "launch_state": "preview_present",
        "public_manifest": True,
        "hub_routes": True,
        "docs_surface": True,
        "route_proof": "live_strict_required",
        "owner_repo": "chummer6-mobile",
        "routes": [
            "/mobile",
            "/pwa",
            "/play",
            "/player",
            "/gm",
            "/observer",
            "/session",
        ],
    },
    "account_packages": {
        "launch_state": "account_only",
        "public_manifest": "registered_routes",
        "hub_routes": True,
        "docs_surface": True,
        "route_proof": "account_surface_only",
        "owner_repo": "chummer6-hub",
        "routes": [
            "/account/packages",
            "/account/packages/{packageId}",
        ],
    },
    "admin_packages": {
        "launch_state": "operator_only",
        "public_manifest": False,
        "operator_manifest": True,
        "hub_routes": True,
        "docs_surface": True,
        "route_proof": "operator_surface_only",
        "owner_repo": "chummer6-hub",
        "routes": [
            "/admin/packages",
        ],
    },
}


def manifest_routes(manifest: dict) -> set[str]:
    routes: set[str] = set()
    for key in ("public_routes", "auth_routes", "registered_routes"):
        for route in manifest.get(key) or []:
            if isinstance(route, dict) and isinstance(route.get("path"), str):
                routes.add(route["path"])
    return routes


def route_families(payload: dict) -> dict[str, dict]:
    families = payload.get("route_families") or {}
    return families if isinstance(families, dict) else {}


def main() -> int:
    mirror_manifest = read_yaml(MIRROR_MANIFEST_PATH) or {}
    central_manifest = read_yaml(CENTRAL_MANIFEST_PATH) or {}
    mirror_route_families = read_yaml(MIRROR_ROUTE_FAMILY_PATH) or {}
    central_route_families = read_yaml(CENTRAL_ROUTE_FAMILY_PATH) or {}
    doc_text = SURFACE_DOC_PATH.read_text(encoding="utf-8")

    mirror_routes = manifest_routes(mirror_manifest)
    central_routes = manifest_routes(central_manifest)
    doc_routes = set(re.findall(r"`(/[^`]+)`", doc_text))
    mirror_family_map = route_families(mirror_route_families)
    central_family_map = route_families(central_route_families)

    rows = []
    failures = []
    for route in REQUIRED_ROUTES:
        in_mirror = route in mirror_routes
        in_central = route in central_routes
        in_doc = route in doc_routes
        rows.append((route, in_central, in_mirror, in_doc))
        if not (in_central and in_mirror and in_doc):
            failures.append(route)

    family_rows = []
    for family_name, expected in REQUIRED_ROUTE_FAMILIES.items():
        central_entry = central_family_map.get(family_name)
        mirror_entry = mirror_family_map.get(family_name)
        central_match = isinstance(central_entry, dict) and all(central_entry.get(key) == value for key, value in expected.items())
        mirror_match = isinstance(mirror_entry, dict) and all(mirror_entry.get(key) == value for key, value in expected.items())
        family_routes = expected.get("routes") or []
        doc_match = all(route in doc_routes for route in family_routes)
        family_rows.append((family_name, central_match, mirror_match, doc_match))
        if not (central_match and mirror_match and doc_match):
            failures.append(f"family:{family_name}")

    lines = [
        "# Canon route family reconciliation",
        "",
        f"- Generated: {now_iso()}",
        f"- Status: `{'pass' if not failures else 'fail'}`",
        f"- Required route family count: {len(REQUIRED_ROUTES)}",
        "",
        "## Route family status",
        "",
    ]
    for route, in_central, in_mirror, in_doc in rows:
        lines.append(
            f"- `{route}`: central=`{'yes' if in_central else 'no'}` mirror=`{'yes' if in_mirror else 'no'}` doc=`{'yes' if in_doc else 'no'}`"
        )

    lines.extend(["", "## Route family registry status", ""])
    for family_name, in_central, in_mirror, in_doc in family_rows:
        lines.append(
            f"- `{family_name}`: central_registry=`{'yes' if in_central else 'no'}` mirror_registry=`{'yes' if in_mirror else 'no'}` doc_routes=`{'yes' if in_doc else 'no'}`"
        )

    if failures:
        lines.extend(["", "## Missing from at least one source", ""])
        lines.extend(f"- `{route}`" for route in failures)

    write_text(completion_path("CANON_ROUTE_FAMILY_RECONCILIATION.md"), "\n".join(lines))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())

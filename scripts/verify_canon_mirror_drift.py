#!/usr/bin/env python3
from __future__ import annotations

import re

from absolute_completion_common import RUN_SERVICES_ROOT, completion_path, now_iso, read_yaml, write_text


MANIFEST_PATH = RUN_SERVICES_ROOT / ".codex-design" / "product" / "PUBLIC_LANDING_MANIFEST.yaml"
FEATURE_REGISTRY_PATH = RUN_SERVICES_ROOT / ".codex-design" / "product" / "PUBLIC_FEATURE_REGISTRY.yaml"
SURFACE_DOC_PATH = RUN_SERVICES_ROOT / "docs" / "PUBLIC_LANDING_SURFACE.md"
REQUIRED_DOC_ROUTES = {
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
    "/participate/karma-forge/submitted/{submissionId}",
    "/feedback/operations",
    "/feedback/operations/lookup",
    "/contact/submitted/{caseId}",
    "/account/packages",
    "/account/packages/{packageId}",
    "/admin/packages",
}


def main() -> int:
    manifest = read_yaml(MANIFEST_PATH) or {}
    feature_registry = read_yaml(FEATURE_REGISTRY_PATH) or {}
    surface_doc = SURFACE_DOC_PATH.read_text(encoding="utf-8")

    doc_routes = set(re.findall(r"`(/[^`]+)`", surface_doc))
    manifest_routes = {
        route["path"]
        for key in ("public_routes", "auth_routes", "registered_routes")
        for route in (manifest.get(key) or [])
        if isinstance(route, dict) and isinstance(route.get("path"), str)
    }
    feature_cards = {card.get("id"): card for card in (feature_registry.get("cards") or []) if isinstance(card, dict)}

    missing_doc_routes = sorted(route for route in REQUIRED_DOC_ROUTES if route not in doc_routes)
    missing_manifest_routes = sorted(route for route in REQUIRED_DOC_ROUTES if route not in manifest_routes)
    missing_feature_cards = []
    if feature_cards.get("real_package_browser", {}).get("href") != "/packages":
        missing_feature_cards.append("real_package_browser -> /packages")
    if feature_cards.get("real_mobile_projection", {}).get("href") != "/mobile":
        missing_feature_cards.append("real_mobile_projection -> /mobile")

    failures = missing_doc_routes + missing_manifest_routes + missing_feature_cards
    lines = [
        "# Canon mirror drift report",
        "",
        f"- Generated: {now_iso()}",
        f"- Manifest route count: {len(manifest_routes)}",
        f"- Doc route marker count: {len(doc_routes)}",
        f"- Missing required doc routes: {len(missing_doc_routes)}",
        f"- Missing required manifest routes: {len(missing_manifest_routes)}",
        f"- Missing required feature cards: {len(missing_feature_cards)}",
        "",
        "## Result",
        "",
        "- Status: `pass`" if not failures else "- Status: `fail`",
    ]
    if missing_doc_routes:
        lines.extend(["", "## Missing doc routes", ""] + [f"- `{route}`" for route in missing_doc_routes])
    if missing_manifest_routes:
        lines.extend(["", "## Missing manifest routes", ""] + [f"- `{route}`" for route in missing_manifest_routes])
    if missing_feature_cards:
        lines.extend(["", "## Missing feature cards", ""] + [f"- `{item}`" for item in missing_feature_cards])
    write_text(completion_path("CANON_MIRROR_DRIFT_REPORT.md"), "\n".join(lines))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())

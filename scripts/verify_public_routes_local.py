#!/usr/bin/env python3
from __future__ import annotations

from absolute_completion_common import LocalHubApp
import verify_public_routes_from_manifest as route_proof


def main() -> int:
    with LocalHubApp() as app:
        return route_proof.main(
            [
                "--base-url",
                app.base_url,
                "--manifest",
                ".codex-design/product/PUBLIC_LANDING_MANIFEST.yaml",
                "--output",
                ".codex-studio/published/CHUMMER_PUBLIC_ROUTE_PROOF.generated.json",
            ]
        )


if __name__ == "__main__":
    raise SystemExit(main())
